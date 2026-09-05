"""Web enrollment API — live capture, doorbell stream, footage upload."""

from __future__ import annotations

import base64
import logging
import re
import shutil
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from enroll import build_gallery
from gallery import save_gallery
from settings import Settings
from stream import FrameSource, mask_stream_url, preview_hub
from vision_runtime import get_face_app

if TYPE_CHECKING:
	from numpy.typing import NDArray

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
CAPTURE_LABELS = frozenset({"front", "left", "right", "door"})
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})
VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".mkv", ".avi", ".webm"})
SCAN_FRAME_STEP = 15
SCAN_DEDUPE_THRESHOLD = 0.95
SCAN_SESSION_TTL_SEC = 3600
MJPEG_BOUNDARY = b"frame"
MJPEG_INTERVAL_SEC = 0.1
SNAPSHOT_WAIT_SEC = 2.0
MJPEG_FIRST_FRAME_WAIT_SEC = 5.0

router = APIRouter(prefix="/enroll", tags=["enroll"])


@dataclass
class ScanSession:
	created_at: float
	crops: dict[str, Path] = field(default_factory=dict)


_scan_sessions: dict[str, ScanSession] = {}


class RebuildResponse(BaseModel):
	embeddings: int
	people: int
	message: str


class PersonInfo(BaseModel):
	name: str
	photos: list[str]


class CaptureResponse(BaseModel):
	ok: bool
	label: str
	filename: str
	face_count: int
	message: str


class ScanFace(BaseModel):
	id: str
	thumbnail: str = Field(description="data:image/jpeg;base64,...")


class ScanResponse(BaseModel):
	session_id: str
	faces: list[ScanFace]


class SaveCropsRequest(BaseModel):
	session_id: str
	name: str
	face_ids: list[str]


class SaveCropsResponse(BaseModel):
	saved: list[str]
	message: str


def _get_settings(request: Request) -> Settings:
	settings = getattr(request.app.state, "settings", None)
	if settings is None:
		return Settings()
	return settings


def _sanitize_name(name: str) -> str:
	clean = name.strip().lower()
	if not NAME_RE.match(clean):
		msg = "Name must be 1–32 chars: lowercase letters, digits, _ or -"
		raise HTTPException(status_code=400, detail=msg)
	return clean


def _verify_enroll_access(
	request: Request,
	settings: Annotated[Settings, Depends(_get_settings)],
	token: Annotated[str | None, Query()] = None,
) -> None:
	"""Optional token gate when ENROLL_SECRET is set."""
	secret = settings.enroll_secret
	if not secret:
		return

	auth = request.headers.get("authorization", "")
	bearer = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
	if token == secret or bearer == secret:
		return

	raise HTTPException(status_code=401, detail="Invalid or missing enroll token")


def _faces_dir(settings: Settings) -> Path:
	return Path(settings.faces_dir)


def _decode_image(data: bytes) -> NDArray[np.uint8]:
	array = np.frombuffer(data, dtype=np.uint8)
	image = cv2.imdecode(array, cv2.IMREAD_COLOR)
	if image is None:
		raise HTTPException(status_code=400, detail="Could not decode image")
	return image


def _face_count(image: NDArray[np.uint8], face_app: Any) -> int:
	return len(face_app.get(image))


def _crop_face(
	image: NDArray[np.uint8], bbox: NDArray[np.float32], margin: float = 0.2
) -> NDArray[np.uint8]:
	x1, y1, x2, y2 = bbox.astype(int)
	h, w = image.shape[:2]
	pad_x = int((x2 - x1) * margin)
	pad_y = int((y2 - y1) * margin)
	left = max(0, x1 - pad_x)
	top = max(0, y1 - pad_y)
	right = min(w, x2 + pad_x)
	bottom = min(h, y2 + pad_y)
	return image[top:bottom, left:right]


def _thumbnail_base64(image: NDArray[np.uint8], max_size: int = 160) -> str:
	h, w = image.shape[:2]
	scale = min(1.0, max_size / max(h, w))
	if scale < 1.0:
		image = cv2.resize(image, (int(w * scale), int(h * scale)))
	ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
	if not ok:
		raise HTTPException(status_code=500, detail="Failed to encode thumbnail")
	data = base64.b64encode(encoded.tobytes()).decode("ascii")
	return f"data:image/jpeg;base64,{data}"


def _next_photo_path(person_dir: Path, label: str) -> Path:
	person_dir.mkdir(parents=True, exist_ok=True)
	candidate = person_dir / f"{label}.jpg"
	if not candidate.exists():
		return candidate
	for index in range(2, 100):
		candidate = person_dir / f"{label}-{index}.jpg"
		if not candidate.exists():
			return candidate
	msg = f"Too many photos for label {label}"
	raise HTTPException(status_code=400, detail=msg)


def _cleanup_scan_sessions() -> None:
	now = time.time()
	expired = [
		session_id
		for session_id, session in _scan_sessions.items()
		if now - session.created_at > SCAN_SESSION_TTL_SEC
	]
	for session_id in expired:
		session = _scan_sessions.pop(session_id, None)
		if session is not None:
			for path in session.crops.values():
				path.unlink(missing_ok=True)


def _scan_session_dir(session_id: str) -> Path:
	root = Path("config/enroll_sessions") / session_id
	root.mkdir(parents=True, exist_ok=True)
	return root


def _collect_faces_from_frame(
	image: NDArray[np.uint8],
	face_app: Any,
	seen_embeddings: list[NDArray[np.float32]],
	session: ScanSession,
	session_dir: Path,
) -> list[ScanFace]:
	found: list[ScanFace] = []
	for face in face_app.get(image):
		embedding = np.asarray(face.normed_embedding, dtype=np.float32)
		if any(
			float(np.dot(embedding, prior)) >= SCAN_DEDUPE_THRESHOLD for prior in seen_embeddings
		):
			continue

		crop = _crop_face(image, face.bbox)
		if crop.size == 0:
			continue

		face_id = uuid.uuid4().hex[:12]
		crop_path = session_dir / f"{face_id}.jpg"
		if not cv2.imwrite(str(crop_path), crop):
			continue

		seen_embeddings.append(embedding)
		session.crops[face_id] = crop_path
		found.append(ScanFace(id=face_id, thumbnail=_thumbnail_base64(crop)))
	return found


def _scan_image(
	path: Path, face_app: Any, session: ScanSession, session_dir: Path
) -> list[ScanFace]:
	image = cv2.imread(str(path))
	if image is None:
		return []
	seen: list[NDArray[np.float32]] = []
	return _collect_faces_from_frame(image, face_app, seen, session, session_dir)


def _scan_video(
	path: Path, face_app: Any, session: ScanSession, session_dir: Path
) -> list[ScanFace]:
	cap = cv2.VideoCapture(str(path))
	if not cap.isOpened():
		return []

	found: list[ScanFace] = []
	seen: list[NDArray[np.float32]] = []
	frame_index = 0
	try:
		while True:
			ok, frame = cap.read()
			if not ok or frame is None:
				break
			if frame_index % SCAN_FRAME_STEP == 0:
				found.extend(_collect_faces_from_frame(frame, face_app, seen, session, session_dir))
			frame_index += 1
	finally:
		cap.release()
	return found


def _ensure_preview_hub(settings: Settings) -> None:
	if not settings.stream_url:
		raise HTTPException(status_code=503, detail="STREAM_URL is not configured")
	preview_hub.start(settings.capture_stream_url())


def _encode_jpeg(frame: NDArray[np.uint8], quality: int = 80) -> bytes | None:
	ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
	if not ok:
		return None
	return encoded.tobytes()


def _mjpeg_frames(settings: Settings) -> Iterator[bytes]:
	_ensure_preview_hub(settings)
	frame = preview_hub.wait_for_frame(timeout_sec=MJPEG_FIRST_FRAME_WAIT_SEC)
	if frame is None:
		logger.warning("Preview stream produced no frame within %.0fs", MJPEG_FIRST_FRAME_WAIT_SEC)
		return

	while True:
		frame = preview_hub.latest_frame()
		if frame is None:
			time.sleep(0.05)
			continue
		payload = _encode_jpeg(frame)
		if payload is None:
			continue
		yield (
			b"--" + MJPEG_BOUNDARY + b"\r\n"
			b"Content-Type: image/jpeg\r\n"
			b"Content-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload + b"\r\n"
		)
		time.sleep(MJPEG_INTERVAL_SEC)


@router.get("/api/people", dependencies=[Depends(_verify_enroll_access)])
def list_people(settings: Annotated[Settings, Depends(_get_settings)]) -> list[PersonInfo]:
	faces_dir = _faces_dir(settings)
	if not faces_dir.is_dir():
		return []

	people: list[PersonInfo] = []
	for person_dir in sorted(faces_dir.iterdir()):
		if not person_dir.is_dir() or person_dir.name.startswith("."):
			continue
		photos = sorted(
			path.name
			for path in person_dir.iterdir()
			if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
		)
		people.append(PersonInfo(name=person_dir.name, photos=photos))
	return people


@router.delete("/api/people/{name}", dependencies=[Depends(_verify_enroll_access)])
def delete_person(
	name: str,
	settings: Annotated[Settings, Depends(_get_settings)],
) -> dict[str, str]:
	person_name = _sanitize_name(name)
	person_dir = _faces_dir(settings) / person_name
	if not person_dir.is_dir():
		raise HTTPException(status_code=404, detail="Person not found")
	shutil.rmtree(person_dir)
	return {"message": f"Deleted {person_name}"}


@router.post("/api/capture", dependencies=[Depends(_verify_enroll_access)])
async def capture_photo(
	settings: Annotated[Settings, Depends(_get_settings)],
	name: Annotated[str, Form()],
	label: Annotated[str, Form()],
	image: Annotated[UploadFile, File()],
) -> CaptureResponse:
	person_name = _sanitize_name(name)
	capture_label = label.strip().lower()
	if capture_label not in CAPTURE_LABELS:
		raise HTTPException(
			status_code=400, detail=f"Label must be one of: {', '.join(CAPTURE_LABELS)}"
		)

	data = await image.read()
	if not data:
		raise HTTPException(status_code=400, detail="Empty image")

	frame = _decode_image(data)
	face_app = get_face_app()
	count = _face_count(frame, face_app)
	if count == 0:
		return CaptureResponse(
			ok=False,
			label=capture_label,
			filename="",
			face_count=0,
			message="No face detected — try again",
		)
	if count > 1:
		return CaptureResponse(
			ok=False,
			label=capture_label,
			filename="",
			face_count=count,
			message=f"{count} faces detected — one person per photo",
		)

	person_dir = _faces_dir(settings) / person_name
	photo_path = _next_photo_path(person_dir, capture_label)
	if not cv2.imwrite(str(photo_path), frame):
		raise HTTPException(status_code=500, detail="Failed to save photo")

	return CaptureResponse(
		ok=True,
		label=capture_label,
		filename=photo_path.name,
		face_count=1,
		message="Saved",
	)


@router.post("/api/capture/doorbell", dependencies=[Depends(_verify_enroll_access)])
def capture_doorbell(
	settings: Annotated[Settings, Depends(_get_settings)],
	name: Annotated[str, Form()],
	label: Annotated[str, Form()] = "door",
) -> CaptureResponse:
	if not settings.stream_url:
		raise HTTPException(status_code=503, detail="STREAM_URL is not configured")

	person_name = _sanitize_name(name)
	capture_label = label.strip().lower()
	if capture_label not in CAPTURE_LABELS:
		raise HTTPException(
			status_code=400, detail=f"Label must be one of: {', '.join(CAPTURE_LABELS)}"
		)

	preview_hub.start(settings.capture_stream_url())
	frame = preview_hub.latest_frame()
	frames: list[NDArray[np.uint8]] = []
	if frame is not None:
		frames = [frame]
	else:
		source = FrameSource(url=settings.capture_stream_url())
		try:
			frames = source.grab_event_frames(3)
		finally:
			source.close()

	if not frames:
		raise HTTPException(status_code=503, detail="Could not grab frame from doorbell stream")

	face_app = get_face_app()
	best_frame: NDArray[np.uint8] | None = None
	best_faces: list[Any] = []
	for frame in frames:
		faces = face_app.get(frame)
		if len(faces) == 1 and (not best_faces or faces[0].det_score > best_faces[0].det_score):
			best_frame = frame
			best_faces = faces

	if best_frame is None or len(best_faces) != 1:
		count = len(best_faces) if best_faces else 0
		return CaptureResponse(
			ok=False,
			label=capture_label,
			filename="",
			face_count=count,
			message="Need exactly one face at the door — adjust position and retry",
		)

	person_dir = _faces_dir(settings) / person_name
	photo_path = _next_photo_path(person_dir, capture_label)
	if not cv2.imwrite(str(photo_path), best_frame):
		raise HTTPException(status_code=500, detail="Failed to save photo")

	return CaptureResponse(
		ok=True,
		label=capture_label,
		filename=photo_path.name,
		face_count=1,
		message="Saved doorbell frame",
	)


@router.get("/api/snapshot.jpg", dependencies=[Depends(_verify_enroll_access)])
def stream_snapshot(settings: Annotated[Settings, Depends(_get_settings)]) -> Response:
	"""Latest doorbell frame as a single JPEG (fast first paint for enroll UI)."""
	_ensure_preview_hub(settings)
	frame = preview_hub.latest_frame()
	if frame is None:
		frame = preview_hub.wait_for_frame(timeout_sec=SNAPSHOT_WAIT_SEC)
	if frame is None:
		raise HTTPException(
			status_code=503,
			detail=(
				"No frame available from stream — check STREAM_URL and STREAM_USER/STREAM_PASSWORD"
			),
		)

	payload = _encode_jpeg(frame)
	if payload is None:
		raise HTTPException(status_code=500, detail="Failed to encode snapshot")
	return Response(content=payload, media_type="image/jpeg")


@router.get("/stream", dependencies=[Depends(_verify_enroll_access)])
def doorbell_stream(settings: Annotated[Settings, Depends(_get_settings)]) -> StreamingResponse:
	logger.info(
		"MJPEG enroll stream started (%s)",
		mask_stream_url(settings.capture_stream_url()),
	)
	return StreamingResponse(
		_mjpeg_frames(settings),
		media_type=f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY.decode()}",
	)


@router.post("/api/scan", dependencies=[Depends(_verify_enroll_access)])
async def scan_footage(
	settings: Annotated[Settings, Depends(_get_settings)],
	file: Annotated[UploadFile, File()],
) -> ScanResponse:
	_cleanup_scan_sessions()
	suffix = Path(file.filename or "upload").suffix.lower()
	if suffix not in IMAGE_SUFFIXES | VIDEO_SUFFIXES:
		msg = f"Unsupported file type: {suffix or '(none)'}"
		raise HTTPException(status_code=400, detail=msg)

	data = await file.read()
	if not data:
		raise HTTPException(status_code=400, detail="Empty upload")

	session_id = uuid.uuid4().hex
	session_dir = _scan_session_dir(session_id)
	upload_path = session_dir / f"upload{suffix}"
	upload_path.write_bytes(data)

	session = ScanSession(created_at=time.time())
	face_app = get_face_app()
	if suffix in IMAGE_SUFFIXES:
		faces = _scan_image(upload_path, face_app, session, session_dir)
	else:
		faces = _scan_video(upload_path, face_app, session, session_dir)

	upload_path.unlink(missing_ok=True)
	_scan_sessions[session_id] = session

	if not faces:
		shutil.rmtree(session_dir, ignore_errors=True)
		_scan_sessions.pop(session_id, None)
		raise HTTPException(status_code=422, detail="No faces found in upload")

	return ScanResponse(session_id=session_id, faces=faces)


@router.post("/api/save-crops", dependencies=[Depends(_verify_enroll_access)])
def save_crops(
	body: SaveCropsRequest,
	settings: Annotated[Settings, Depends(_get_settings)],
) -> SaveCropsResponse:
	session = _scan_sessions.get(body.session_id)
	if session is None:
		raise HTTPException(status_code=404, detail="Scan session expired — upload again")

	person_name = _sanitize_name(body.name)
	if not body.face_ids:
		raise HTTPException(status_code=400, detail="Select at least one face")

	person_dir = _faces_dir(settings) / person_name
	person_dir.mkdir(parents=True, exist_ok=True)
	saved: list[str] = []

	for index, face_id in enumerate(body.face_ids, start=1):
		crop_path = session.crops.get(face_id)
		if crop_path is None or not crop_path.is_file():
			continue
		dest = person_dir / f"footage-{index}.jpg"
		if dest.exists():
			dest = _next_photo_path(person_dir, "footage")
		shutil.copy2(crop_path, dest)
		saved.append(dest.name)

	if not saved:
		raise HTTPException(status_code=400, detail="No valid face selections")

	return SaveCropsResponse(
		saved=saved,
		message=f"Saved {len(saved)} photo(s) for {person_name}",
	)


@router.post("/api/rebuild", dependencies=[Depends(_verify_enroll_access)])
def rebuild_gallery(settings: Annotated[Settings, Depends(_get_settings)]) -> RebuildResponse:
	faces_dir = _faces_dir(settings)
	if not faces_dir.is_dir():
		raise HTTPException(status_code=404, detail=f"Faces directory not found: {faces_dir}")

	gallery = build_gallery(faces_dir)
	if not gallery.faces:
		raise HTTPException(status_code=422, detail="No faces enrolled")

	gallery_path = Path(settings.gallery_path)
	save_gallery(gallery, gallery_path)
	people = sorted({face.name for face in gallery.faces})
	message = f"Wrote {len(gallery.faces)} embedding(s) for {len(people)} person(s)"
	logger.info(message)
	return RebuildResponse(embeddings=len(gallery.faces), people=len(people), message=message)
