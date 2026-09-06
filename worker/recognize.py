"""Detect faces in stream frames and match against the enrolled gallery."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import numpy as np

from frame_enhance import detect_faces
from gallery import Gallery, load_gallery
from settings import Settings
from stream import FrameSource, preview_hub
from vision_runtime import get_face_app

if TYPE_CHECKING:
	from numpy.typing import NDArray

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FaceMatch:
	"""One detected face and its best gallery match (if any)."""

	name: str | None
	score: float
	det_score: float


@dataclass(frozen=True)
class RecognitionResult:
	"""Aggregated recognition output for one doorbell event."""

	names: list[str]
	unknown: int
	matches: list[FaceMatch]


def _match_detected_face(face: Any, gallery: Gallery, threshold: float) -> FaceMatch:
	"""Match one InsightFace detection against all enrolled embeddings."""
	embedding = np.asarray(face.normed_embedding, dtype=np.float32)
	det_score = float(face.det_score)

	if not gallery.faces:
		return FaceMatch(name=None, score=0.0, det_score=det_score)

	best_name: str | None = None
	best_score = -1.0
	for enrolled in gallery.faces:
		score = float(np.dot(embedding, enrolled.embedding))
		if score > best_score:
			best_score = score
			best_name = enrolled.name

	name = best_name if best_score >= threshold else None
	return FaceMatch(name=name, score=best_score, det_score=det_score)


def _pick_best_frame(
	face_app: Any,
	frames: list[NDArray[np.uint8]],
	*,
	enhance_mode: str,
) -> list[Any] | None:
	"""Return detections from the frame with the most (and highest-scoring) faces."""
	best_faces: list[Any] | None = None
	best_key = (-1, -1.0)

	for frame in frames:
		faces = detect_faces(face_app, frame, enhance_mode=enhance_mode)
		if not faces:
			continue
		key = (len(faces), sum(float(face.det_score) for face in faces))
		if key > best_key:
			best_key = key
			best_faces = faces

	return best_faces


def recognize_frames(
	frames: list[NDArray[np.uint8]],
	gallery: Gallery,
	*,
	face_app: Any,
	threshold: float,
	enhance_mode: str = "clahe",
) -> RecognitionResult:
	"""Detect and match faces in the best frame from *frames*."""
	faces = _pick_best_frame(face_app, frames, enhance_mode=enhance_mode)
	if not faces:
		return RecognitionResult(names=[], unknown=0, matches=[])

	matches = [_match_detected_face(face, gallery, threshold) for face in faces]
	names = sorted({match.name for match in matches if match.name is not None})
	unknown = sum(1 for match in matches if match.name is None)
	return RecognitionResult(names=names, unknown=unknown, matches=matches)


def _frames_from_preview_hub(count: int) -> list[NDArray[np.uint8]]:
	"""Sample recent preview frames — avoids a second RTSP connection during enroll UI."""
	if count < 1:
		return []

	frames: list[NDArray[np.uint8]] = []
	for index in range(count):
		frame = preview_hub.latest_frame()
		if frame is not None:
			frames.append(frame)
		if index + 1 < count:
			time.sleep(0.15)
	return frames


def recognize_from_settings(
	settings: Settings,
	*,
	face_app: Any | None = None,
	gallery: Gallery | None = None,
) -> RecognitionResult:
	"""Grab RTSP frames and run recognition using *settings*."""
	if not settings.stream_url:
		msg = "STREAM_URL is not set"
		raise ValueError(msg)

	gallery_path = settings.gallery_path()
	if gallery is None:
		if not gallery_path.is_file():
			msg = f"Gallery not found: {gallery_path} (run enroll first)"
			raise FileNotFoundError(msg)
		gallery = load_gallery(gallery_path)

	app = face_app if face_app is not None else get_face_app(gallery.model)
	frames = _frames_from_preview_hub(settings.frames_per_event)
	if not frames:
		source = FrameSource(settings.capture_stream_url())
		try:
			frames = source.grab_event_frames(settings.frames_per_event)
		finally:
			source.close()
	if not frames:
		logger.warning("No frames grabbed from stream")
		return RecognitionResult(names=[], unknown=0, matches=[])

	return recognize_frames(
		frames,
		gallery,
		face_app=app,
		threshold=settings.recognition_threshold,
		enhance_mode=settings.frame_enhance,
	)


def format_notify_message(result: RecognitionResult) -> str:
	"""Human-readable doorbell notification for HA / mobile push."""
	names = result.names
	unknown = result.unknown

	if not names and unknown == 0:
		return "Nobody at the door"

	if names and unknown == 0:
		subject = _format_name_list(names)
		verb = "is" if len(names) == 1 else "are"
		return f"{subject} {verb} at the door"

	if names and unknown > 0:
		subject = _format_name_list(names)
		extra = "someone else" if unknown == 1 else f"{unknown} others"
		return f"{subject} and {extra} at the door"

	if unknown == 1:
		return "Someone's at the door"
	return f"{unknown} people at the door"


def _format_name_list(names: list[str]) -> str:
	if len(names) == 1:
		return names[0]
	if len(names) == 2:
		return f"{names[0]} and {names[1]}"
	return f"{', '.join(names[:-1])}, and {names[-1]}"


def result_to_payload(result: RecognitionResult) -> dict[str, object]:
	"""Serialize a recognition result for HTTP / HA webhook payloads."""
	return {
		"event": "doorbell",
		"names": result.names,
		"unknown": result.unknown,
		"message": format_notify_message(result),
		"ts": datetime.now(UTC).isoformat(),
	}


def log_result(result: RecognitionResult) -> None:
	"""Log recognition output for a doorbell event."""
	if result.names or result.unknown:
		logger.info("%s", format_notify_message(result))
	else:
		logger.info("No faces detected")
