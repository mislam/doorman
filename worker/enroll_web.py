"""Web enrollment API — live capture, doorbell stream, footage upload."""

from __future__ import annotations

import base64
import logging
import tempfile
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from enroll import build_gallery
from face_store import (
	PersonRecord,
	PhotoRecord,
	find_or_create_person,
	load_store,
	new_photo_path,
	register_photo,
	save_store,
	validate_display_name,
)
from face_store import (
	delete_person as delete_stored_person,
)
from gallery import save_gallery as save_gallery_pickle
from settings import Settings
from stream import FrameSource, mask_stream_url, preview_hub
from vision_runtime import get_face_app

if TYPE_CHECKING:
	from numpy.typing import NDArray

logger = logging.getLogger(__name__)

CAPTURE_LABELS = frozenset({"front", "left", "right", "door"})
FOOTAGE_LABEL = "footage"
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})
VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".mkv", ".avi", ".webm"})
SCAN_FRAME_STEP = 15
SCAN_DEDUPE_THRESHOLD = 0.95
MJPEG_BOUNDARY = b"frame"
MJPEG_INTERVAL_SEC = 0.1
SNAPSHOT_WAIT_SEC = 2.0
MJPEG_FIRST_FRAME_WAIT_SEC = 5.0

router = APIRouter(prefix="/enroll", tags=["enroll"])


class RebuildResponse(BaseModel):
	embeddings: int
	people: int
	message: str


class PersonInfo(BaseModel):
	id: str
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
	thumbnail: str = Field(description="Small preview — data:image/jpeg;base64,...")
	crop: str = Field(description="Full crop for client-side staging — data:image/jpeg;base64,...")


class ScanResponse(BaseModel):
	faces: list[ScanFace]


def _get_settings(request: Request) -> Settings:
	settings = getattr(request.app.state, "settings", None)
	if settings is None:
		return Settings()
	return settings


def _validate_display_name(name: str) -> str:
	try:
		return validate_display_name(name)
	except ValueError as exc:
		raise HTTPException(status_code=400, detail=str(exc)) from exc


def _save_capture_photo(
	settings: Settings,
	display_name: str,
	capture_label: str,
	frame: NDArray[np.uint8],
) -> PhotoRecord:
	faces_dir = _db_dir(settings)
	store = load_store(faces_dir)
	person = find_or_create_person(store, display_name)
	_, photo_path = new_photo_path(faces_dir)
	photo_path.parent.mkdir(parents=True, exist_ok=True)
	if not cv2.imwrite(str(photo_path), frame):
		raise HTTPException(status_code=500, detail="Failed to save photo")
	record = register_photo(person, capture_label, photo_path)
	save_store(store, faces_dir)
	return record


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


def _db_dir(settings: Settings) -> Path:
	return settings.db_path()


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


def _jpeg_data_url(image: NDArray[np.uint8], quality: int = 90, max_size: int | None = None) -> str:
	h, w = image.shape[:2]
	if max_size is not None:
		scale = min(1.0, max_size / max(h, w))
		if scale < 1.0:
			image = cv2.resize(image, (int(w * scale), int(h * scale)))
	ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
	if not ok:
		raise HTTPException(status_code=500, detail="Failed to encode image")
	data = base64.b64encode(encoded.tobytes()).decode("ascii")
	return f"data:image/jpeg;base64,{data}"


def _thumbnail_base64(image: NDArray[np.uint8], max_size: int = 160) -> str:
	return _jpeg_data_url(image, quality=85, max_size=max_size)


def _next_footage_label(person: PersonRecord) -> str:
	footage_labels = [photo.label for photo in person.photos if photo.label.startswith("footage")]
	if not footage_labels:
		return "footage-1"
	for index in range(1, 100):
		label = f"footage-{index}"
		if label not in footage_labels:
			return label
	msg = "Too many footage photos"
	raise HTTPException(status_code=400, detail=msg)


def _collect_faces_from_frame(
	image: NDArray[np.uint8],
	face_app: Any,
	seen_embeddings: list[NDArray[np.float32]],
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
		seen_embeddings.append(embedding)
		found.append(
			ScanFace(
				id=face_id,
				thumbnail=_thumbnail_base64(crop),
				crop=_jpeg_data_url(crop),
			)
		)
	return found


def _scan_image(path: Path, face_app: Any) -> list[ScanFace]:
	image = cv2.imread(str(path))
	if image is None:
		return []
	seen: list[NDArray[np.float32]] = []
	return _collect_faces_from_frame(image, face_app, seen)


def _scan_video(path: Path, face_app: Any) -> list[ScanFace]:
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
				found.extend(_collect_faces_from_frame(frame, face_app, seen))
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
	faces_dir = _db_dir(settings)
	store = load_store(faces_dir)
	return [
		PersonInfo(
			id=person.id,
			name=person.name,
			photos=[photo.label for photo in person.photos],
		)
		for person in sorted(store.people, key=lambda entry: entry.name.lower())
	]


@router.delete("/api/people/{person_id}", dependencies=[Depends(_verify_enroll_access)])
def delete_person(
	person_id: str,
	settings: Annotated[Settings, Depends(_get_settings)],
) -> dict[str, str]:
	faces_dir = _db_dir(settings)
	store = load_store(faces_dir)
	try:
		person = delete_stored_person(store, faces_dir, person_id)
	except KeyError as exc:
		raise HTTPException(status_code=404, detail="Person not found") from exc
	save_store(store, faces_dir)
	return {"message": f"Deleted {person.name}"}


@router.post("/api/capture", dependencies=[Depends(_verify_enroll_access)])
async def capture_photo(
	settings: Annotated[Settings, Depends(_get_settings)],
	name: Annotated[str, Form()],
	label: Annotated[str, Form()],
	image: Annotated[UploadFile, File()],
	from_scan: Annotated[str, Form()] = "",
) -> CaptureResponse:
	display_name = _validate_display_name(name)
	capture_label = label.strip().lower()
	from_scan_flag = from_scan.strip().lower() in {"1", "true", "yes"}

	data = await image.read()
	if not data:
		raise HTTPException(status_code=400, detail="Empty image")

	frame = _decode_image(data)

	if capture_label == FOOTAGE_LABEL:
		store = load_store(_db_dir(settings))
		person = find_or_create_person(store, display_name)
		resolved_label = _next_footage_label(person)
		record = _save_capture_photo(settings, display_name, resolved_label, frame)
		return CaptureResponse(
			ok=True,
			label=resolved_label,
			filename=record.label,
			face_count=1,
			message="Saved",
		)

	if capture_label not in CAPTURE_LABELS:
		raise HTTPException(
			status_code=400, detail=f"Label must be one of: {', '.join(CAPTURE_LABELS)}"
		)

	if from_scan_flag:
		record = _save_capture_photo(settings, display_name, capture_label, frame)
		return CaptureResponse(
			ok=True,
			label=capture_label,
			filename=record.label,
			face_count=1,
			message="Saved",
		)

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

	record = _save_capture_photo(settings, display_name, capture_label, frame)

	return CaptureResponse(
		ok=True,
		label=capture_label,
		filename=record.label,
		face_count=1,
		message="Saved",
	)


def _grab_doorbell_one_face(settings: Settings) -> NDArray[np.uint8]:
	"""Return a doorbell frame with exactly one detected face."""
	if not settings.stream_url:
		raise HTTPException(status_code=503, detail="STREAM_URL is not configured")

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
	for candidate in frames:
		faces = face_app.get(candidate)
		if len(faces) == 1 and (not best_faces or faces[0].det_score > best_faces[0].det_score):
			best_frame = candidate
			best_faces = faces

	if best_frame is None or len(best_faces) != 1:
		raise HTTPException(
			status_code=422,
			detail="Need exactly one face at the door — adjust position and retry",
		)

	return best_frame


@router.post("/api/capture/doorbell/preview", dependencies=[Depends(_verify_enroll_access)])
def doorbell_preview(settings: Annotated[Settings, Depends(_get_settings)]) -> Response:
	"""Grab a doorbell JPEG for client-side staging — does not write to disk."""
	frame = _grab_doorbell_one_face(settings)
	payload = _encode_jpeg(frame)
	if payload is None:
		raise HTTPException(status_code=500, detail="Failed to encode snapshot")
	return Response(content=payload, media_type="image/jpeg")


@router.post("/api/capture/doorbell", dependencies=[Depends(_verify_enroll_access)])
def capture_doorbell(
	settings: Annotated[Settings, Depends(_get_settings)],
	name: Annotated[str, Form()],
	label: Annotated[str, Form()] = "door",
) -> CaptureResponse:
	display_name = _validate_display_name(name)
	capture_label = label.strip().lower()
	if capture_label not in CAPTURE_LABELS:
		raise HTTPException(
			status_code=400, detail=f"Label must be one of: {', '.join(CAPTURE_LABELS)}"
		)

	try:
		best_frame = _grab_doorbell_one_face(settings)
	except HTTPException as exc:
		if exc.status_code == 422:
			count = 0
			return CaptureResponse(
				ok=False,
				label=capture_label,
				filename="",
				face_count=count,
				message=str(exc.detail),
			)
		raise

	record = _save_capture_photo(settings, display_name, capture_label, best_frame)

	return CaptureResponse(
		ok=True,
		label=capture_label,
		filename=record.label,
		face_count=1,
		message="Saved doorbell frame",
	)


@router.post("/api/enroll", dependencies=[Depends(_verify_enroll_access)])
async def enroll_person(
	settings: Annotated[Settings, Depends(_get_settings)],
	name: Annotated[str, Form()],
	labels: Annotated[list[str], Form()],
	images: Annotated[list[UploadFile], File()],
) -> RebuildResponse:
	"""Save staged photos from the browser, then rebuild gallery.pkl."""
	display_name = _validate_display_name(name)
	if not labels:
		raise HTTPException(status_code=400, detail="Add at least one photo")
	if len(labels) != len(images):
		raise HTTPException(status_code=400, detail="Photo labels and images do not match")

	for capture_label, upload in zip(labels, images, strict=True):
		label = capture_label.strip().lower()
		if label not in CAPTURE_LABELS:
			raise HTTPException(
				status_code=400, detail=f"Label must be one of: {', '.join(CAPTURE_LABELS)}"
			)
		data = await upload.read()
		if not data:
			raise HTTPException(status_code=400, detail="Empty image")
		frame = _decode_image(data)
		_save_capture_photo(settings, display_name, label, frame)

	return rebuild_gallery(settings)


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
	suffix = Path(file.filename or "upload").suffix.lower()
	if suffix not in IMAGE_SUFFIXES | VIDEO_SUFFIXES:
		msg = f"Unsupported file type: {suffix or '(none)'}"
		raise HTTPException(status_code=400, detail=msg)

	data = await file.read()
	if not data:
		raise HTTPException(status_code=400, detail="Empty upload")

	with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
		tmp.write(data)
		upload_path = Path(tmp.name)

	try:
		face_app = get_face_app()
		if suffix in IMAGE_SUFFIXES:
			faces = _scan_image(upload_path, face_app)
		else:
			faces = _scan_video(upload_path, face_app)
	finally:
		upload_path.unlink(missing_ok=True)

	if not faces:
		raise HTTPException(status_code=422, detail="No faces found in upload")

	return ScanResponse(faces=faces)


@router.post("/api/rebuild", dependencies=[Depends(_verify_enroll_access)])
def rebuild_gallery(settings: Annotated[Settings, Depends(_get_settings)]) -> RebuildResponse:
	db_dir = _db_dir(settings)
	gallery = build_gallery(db_dir)
	if not gallery.faces:
		raise HTTPException(status_code=422, detail="No faces enrolled")

	save_gallery_pickle(gallery, settings.gallery_path())
	people = sorted({face.name for face in gallery.faces})
	message = f"Wrote {len(gallery.faces)} embedding(s) for {len(people)} person(s)"
	logger.info(message)
	return RebuildResponse(embeddings=len(gallery.faces), people=len(people), message=message)
