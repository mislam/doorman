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
from enroll_pose import PoseStep, adjust_yaw, enrollment_hint, read_pose
from face_store import (
	PersonRecord,
	PhotoRecord,
	clear_person_photos,
	find_or_create_person,
	find_person_by_name,
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
from stream import mask_stream_url, preview_hub
from vision_runtime import get_face_app

if TYPE_CHECKING:
	from numpy.typing import NDArray

logger = logging.getLogger(__name__)

PHOTO_LABEL_PREFIX = "photo"
FOOTAGE_LABEL_PREFIX = "footage"
ENROLL_SOURCE_LIVE = "live"
ENROLL_SOURCE_FOOTAGE = "footage"
VALID_POSE_STEPS = frozenset({"center", "left", "right", "up", "down"})
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})
VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".mkv", ".avi", ".webm"})
SCAN_FRAME_STEP = 15
SCAN_DEDUPE_THRESHOLD = 0.95
MJPEG_BOUNDARY = b"frame"
MJPEG_INTERVAL_SEC = 0.1
SNAPSHOT_WAIT_SEC = 2.0
MJPEG_FIRST_FRAME_WAIT_SEC = 5.0
# Ignore tiny/low-confidence second detections (reflections, posters, partial faces).
ENROLL_SECONDARY_MIN_DET = 0.45
ENROLL_SECONDARY_AREA_RATIO = 0.30

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


class PoseCheckResponse(BaseModel):
	ok: bool
	hint: str | None = None
	yaw: float = 0.0
	pitch: float = 0.0
	face_count: int = 0


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


def _center_square_crop(image: NDArray[np.uint8]) -> NDArray[np.uint8]:
	"""Center square crop — matches 1:1 enroll preview (object-cover in square viewport)."""
	h, w = image.shape[:2]
	side = min(h, w)
	y0 = (h - side) // 2
	x0 = (w - side) // 2
	return image[y0 : y0 + side, x0 : x0 + side]


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


def _next_label(person: PersonRecord, prefix: str) -> str:
	existing = {photo.label for photo in person.photos if photo.label.startswith(f"{prefix}-")}
	for index in range(1, 100):
		label = f"{prefix}-{index}"
		if label not in existing:
			return label
	msg = f"Too many {prefix} photos"
	raise HTTPException(status_code=400, detail=msg)


def _next_photo_label(person: PersonRecord) -> str:
	return _next_label(person, PHOTO_LABEL_PREFIX)


def _next_footage_label(person: PersonRecord) -> str:
	return _next_label(person, FOOTAGE_LABEL_PREFIX)


def _normalize_pose_step(step: str | None) -> PoseStep:
	normalized = (step or "center").strip().lower()
	if normalized not in VALID_POSE_STEPS:
		raise HTTPException(
			status_code=400,
			detail=f"step must be one of: {', '.join(sorted(VALID_POSE_STEPS))}",
		)
	return normalized  # type: ignore[return-value]


def _normalize_enroll_source(source: str) -> str:
	normalized = source.strip().lower()
	if normalized not in {ENROLL_SOURCE_LIVE, ENROLL_SOURCE_FOOTAGE}:
		raise HTTPException(
			status_code=400,
			detail=f"source must be {ENROLL_SOURCE_LIVE} or {ENROLL_SOURCE_FOOTAGE}",
		)
	return normalized


def _parse_replace_flag(value: str) -> bool:
	return value.strip().lower() in {"1", "true", "yes"}


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

	if capture_label == FOOTAGE_LABEL_PREFIX:
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

	if from_scan_flag:
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

	face_app = get_face_app()
	count = _face_count(frame, face_app)
	if count == 0:
		return CaptureResponse(
			ok=False,
			label="",
			filename="",
			face_count=0,
			message="No face detected — try again",
		)
	if count > 1:
		return CaptureResponse(
			ok=False,
			label="",
			filename="",
			face_count=count,
			message=f"{count} faces detected — one person per photo",
		)

	store = load_store(_db_dir(settings))
	person = find_or_create_person(store, display_name)
	resolved_label = _next_photo_label(person)
	record = _save_capture_photo(settings, display_name, resolved_label, frame)

	return CaptureResponse(
		ok=True,
		label=resolved_label,
		filename=record.label,
		face_count=1,
		message="Saved",
	)


def _face_bbox_area(face: Any) -> float:
	x1, y1, x2, y2 = face.bbox.astype(float)
	return max(0.0, (x2 - x1) * (y2 - y1))


def _face_rank(face: Any) -> float:
	return float(face.det_score) * _face_bbox_area(face)


def _primary_enroll_face(faces: list[Any]) -> tuple[Any | None, int]:
	"""Pick the person at the door; drop weak extra detections on the same frame."""
	if not faces:
		return None, 0

	ordered = sorted(faces, key=_face_rank, reverse=True)
	primary = ordered[0]
	if len(ordered) == 1:
		return primary, 1

	secondary = ordered[1]
	primary_area = _face_bbox_area(primary)
	secondary_area = _face_bbox_area(secondary)
	if float(secondary.det_score) < ENROLL_SECONDARY_MIN_DET:
		return primary, 1
	if primary_area > 0 and secondary_area < primary_area * ENROLL_SECONDARY_AREA_RATIO:
		return primary, 1

	return None, len(ordered)


def _doorbell_face_probe(
	settings: Settings,
) -> tuple[NDArray[np.uint8] | None, Any | None, int]:
	"""Return best single-face frame from the doorbell preview hub, or face count when ambiguous."""
	if not settings.stream_url:
		raise HTTPException(status_code=503, detail="STREAM_URL is not configured")

	preview_hub.start(settings.capture_stream_url())
	frame = preview_hub.latest_frame()
	if frame is None:
		return None, None, 0

	frame = _center_square_crop(frame)
	face_app = get_face_app()
	best_face, face_count = _primary_enroll_face(face_app.get(frame))
	return frame, best_face, face_count


def _image_face_probe(image: NDArray[np.uint8]) -> tuple[Any | None, int]:
	face_app = get_face_app()
	return _primary_enroll_face(face_app.get(image))


def _pose_check_from_face(
	best_face: Any,
	pose_step: PoseStep,
	*,
	frame_h: int,
	frame_w: int,
	baseline_yaw: float | None = None,
	baseline_pitch: float | None = None,
	mirror_yaw: bool = False,
) -> PoseCheckResponse:
	quality_hint = enrollment_hint(
		best_face,
		pose_step,
		frame_h,
		frame_w,
		baseline_yaw=baseline_yaw,
		baseline_pitch=baseline_pitch,
		mirror_yaw=mirror_yaw,
	)
	yaw, pitch, _roll = read_pose(best_face)
	yaw = adjust_yaw(yaw, mirror_yaw)
	return PoseCheckResponse(
		ok=quality_hint is None,
		hint=quality_hint,
		yaw=yaw,
		pitch=pitch,
		face_count=1,
	)


def _grab_image_one_face(
	image: NDArray[np.uint8],
	*,
	pose_step: PoseStep = "center",
	baseline_yaw: float | None = None,
	baseline_pitch: float | None = None,
	mirror_yaw: bool = False,
) -> tuple[NDArray[np.uint8], Any]:
	best_face, face_count = _image_face_probe(image)

	if face_count == 0:
		raise HTTPException(status_code=422, detail="No face visible")
	if face_count > 1:
		raise HTTPException(status_code=422, detail="One person only")
	if best_face is None:
		raise HTTPException(status_code=422, detail="No face visible")

	h, w = image.shape[:2]
	hint = enrollment_hint(
		best_face,
		pose_step,
		h,
		w,
		baseline_yaw=baseline_yaw,
		baseline_pitch=baseline_pitch,
		mirror_yaw=mirror_yaw,
	)
	if hint is not None:
		raise HTTPException(status_code=422, detail=hint)

	return image, best_face


def _grab_doorbell_one_face(
	settings: Settings,
	*,
	pose_step: PoseStep = "center",
	baseline_yaw: float | None = None,
	baseline_pitch: float | None = None,
) -> tuple[NDArray[np.uint8], Any]:
	"""Return a doorbell frame and its face when exactly one face is detected."""
	frame, best_face, face_count = _doorbell_face_probe(settings)

	if face_count == 0:
		raise HTTPException(
			status_code=422,
			detail="No face visible",
		)
	if face_count > 1:
		raise HTTPException(
			status_code=422,
			detail="One person only",
		)
	if frame is None or best_face is None:
		raise HTTPException(status_code=503, detail="Could not grab frame from doorbell stream")

	h, w = frame.shape[:2]
	hint = enrollment_hint(
		best_face,
		pose_step,
		h,
		w,
		baseline_yaw=baseline_yaw,
		baseline_pitch=baseline_pitch,
	)
	if hint is not None:
		raise HTTPException(status_code=422, detail=hint)

	return frame, best_face


@router.get("/api/capture/doorbell/pose", dependencies=[Depends(_verify_enroll_access)])
def doorbell_pose_check(
	settings: Annotated[Settings, Depends(_get_settings)],
	step: Annotated[str | None, Query()] = None,
	baseline_yaw: Annotated[float | None, Query()] = None,
	baseline_pitch: Annotated[float | None, Query()] = None,
) -> PoseCheckResponse:
	"""Poll head pose for guided live enrollment (no image transfer)."""
	pose_step = _normalize_pose_step(step)
	_frame, best_face, face_count = _doorbell_face_probe(settings)

	if face_count == 0:
		return PoseCheckResponse(ok=False, hint="No face visible")
	if face_count > 1:
		return PoseCheckResponse(ok=False, hint="One person only", face_count=face_count)
	if best_face is None:
		return PoseCheckResponse(ok=False, hint="Connecting to doorbell…")

	h, w = _frame.shape[:2]
	hint = enrollment_hint(
		best_face,
		pose_step,
		h,
		w,
		baseline_yaw=baseline_yaw,
		baseline_pitch=baseline_pitch,
	)
	yaw, pitch, _roll = read_pose(best_face)
	return PoseCheckResponse(
		ok=hint is None,
		hint=hint,
		yaw=yaw,
		pitch=pitch,
		face_count=1,
	)


@router.post("/api/capture/phone/pose", dependencies=[Depends(_verify_enroll_access)])
async def phone_pose_check(
	image: Annotated[UploadFile, File()],
	step: Annotated[str | None, Query()] = None,
	baseline_yaw: Annotated[float | None, Query()] = None,
	baseline_pitch: Annotated[float | None, Query()] = None,
	mirror_yaw: Annotated[bool, Query()] = True,
) -> PoseCheckResponse:
	"""Poll head pose from a phone camera frame (InsightFace on uploaded JPEG)."""
	pose_step = _normalize_pose_step(step)
	data = await image.read()
	if not data:
		raise HTTPException(status_code=400, detail="Empty image")

	frame = _decode_image(data)
	frame = _center_square_crop(frame)
	best_face, face_count = _image_face_probe(frame)

	if face_count == 0:
		return PoseCheckResponse(ok=False, hint="No face visible")
	if face_count > 1:
		return PoseCheckResponse(ok=False, hint="One person only", face_count=face_count)
	if best_face is None:
		return PoseCheckResponse(ok=False, hint="No face visible")

	return _pose_check_from_face(
		best_face,
		pose_step,
		frame_h=frame.shape[0],
		frame_w=frame.shape[1],
		baseline_yaw=baseline_yaw,
		baseline_pitch=baseline_pitch,
		mirror_yaw=mirror_yaw,
	)


@router.post("/api/capture/phone/preview", dependencies=[Depends(_verify_enroll_access)])
async def phone_preview(
	image: Annotated[UploadFile, File()],
	step: Annotated[str | None, Query()] = None,
	baseline_yaw: Annotated[float | None, Query()] = None,
	baseline_pitch: Annotated[float | None, Query()] = None,
	mirror_yaw: Annotated[bool, Query()] = True,
) -> Response:
	"""Validate pose on a phone frame and return the JPEG for client-side staging."""
	pose_step = _normalize_pose_step(step)
	data = await image.read()
	if not data:
		raise HTTPException(status_code=400, detail="Empty image")

	frame = _decode_image(data)
	_validated_frame, _face = _grab_image_one_face(
		frame,
		pose_step=pose_step,
		baseline_yaw=baseline_yaw,
		baseline_pitch=baseline_pitch,
		mirror_yaw=mirror_yaw,
	)
	payload = _encode_jpeg(frame)
	if payload is None:
		raise HTTPException(status_code=500, detail="Failed to encode snapshot")
	return Response(content=payload, media_type="image/jpeg")


@router.post("/api/capture/doorbell/preview", dependencies=[Depends(_verify_enroll_access)])
def doorbell_preview(
	settings: Annotated[Settings, Depends(_get_settings)],
	step: Annotated[str | None, Query()] = None,
	baseline_yaw: Annotated[float | None, Query()] = None,
	baseline_pitch: Annotated[float | None, Query()] = None,
) -> Response:
	"""Grab a doorbell JPEG for client-side staging — does not write to disk."""
	pose_step = _normalize_pose_step(step)
	frame, _face = _grab_doorbell_one_face(
		settings,
		pose_step=pose_step,
		baseline_yaw=baseline_yaw,
		baseline_pitch=baseline_pitch,
	)
	payload = _encode_jpeg(frame)
	if payload is None:
		raise HTTPException(status_code=500, detail="Failed to encode snapshot")
	return Response(content=payload, media_type="image/jpeg")


@router.post("/api/capture/doorbell", dependencies=[Depends(_verify_enroll_access)])
def capture_doorbell(
	settings: Annotated[Settings, Depends(_get_settings)],
	name: Annotated[str, Form()],
	step: Annotated[str | None, Form()] = None,
) -> CaptureResponse:
	display_name = _validate_display_name(name)
	pose_step = _normalize_pose_step(step)
	store = load_store(_db_dir(settings))
	person = find_or_create_person(store, display_name)
	capture_label = _next_photo_label(person)

	try:
		best_frame, _face = _grab_doorbell_one_face(settings, pose_step=pose_step)
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


def _save_enrollment_images(
	settings: Settings,
	display_name: str,
	images: list[NDArray[np.uint8]],
	*,
	source: str,
	replace: bool,
) -> int:
	faces_dir = _db_dir(settings)
	store = load_store(faces_dir)
	existing = find_person_by_name(store, display_name)
	if existing is not None:
		if existing.photos and not replace:
			raise HTTPException(
				status_code=409,
				detail=f"{existing.name} is already enrolled — confirm to replace their photos",
			)
		if existing.photos:
			clear_person_photos(store, faces_dir, existing)
		person = existing
	else:
		person = find_or_create_person(store, display_name)

	label_fn = _next_footage_label if source == ENROLL_SOURCE_FOOTAGE else _next_photo_label

	for frame in images:
		label = label_fn(person)
		_, photo_path = new_photo_path(faces_dir)
		photo_path.parent.mkdir(parents=True, exist_ok=True)
		if not cv2.imwrite(str(photo_path), frame):
			raise HTTPException(status_code=500, detail="Failed to save photo")
		register_photo(person, label, photo_path)

	save_store(store, faces_dir)
	return len(images)


@router.post("/api/enroll", dependencies=[Depends(_verify_enroll_access)])
async def enroll_person(
	settings: Annotated[Settings, Depends(_get_settings)],
	name: Annotated[str, Form()],
	images: Annotated[list[UploadFile], File()],
	source: Annotated[str, Form()] = ENROLL_SOURCE_LIVE,
	replace: Annotated[str, Form()] = "false",
) -> RebuildResponse:
	"""Save staged photos from the browser, then rebuild gallery.pkl."""
	display_name = _validate_display_name(name)
	enroll_source = _normalize_enroll_source(source)
	replace_flag = _parse_replace_flag(replace)
	if not images:
		raise HTTPException(status_code=400, detail="Add at least one photo")

	decoded: list[NDArray[np.uint8]] = []
	for upload in images:
		data = await upload.read()
		if not data:
			raise HTTPException(status_code=400, detail="Empty image")
		decoded.append(_decode_image(data))

	_save_enrollment_images(
		settings,
		display_name,
		decoded,
		source=enroll_source,
		replace=replace_flag,
	)
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
	gallery = build_gallery(db_dir, enhance_mode=settings.frame_enhance)
	if not gallery.faces:
		raise HTTPException(status_code=422, detail="No faces enrolled")

	save_gallery_pickle(gallery, settings.gallery_path())
	people = sorted({face.name for face in gallery.faces})
	message = f"Wrote {len(gallery.faces)} embedding(s) for {len(people)} person(s)"
	logger.info(message)
	return RebuildResponse(embeddings=len(gallery.faces), people=len(people), message=message)
