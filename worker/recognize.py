"""Detect faces in stream frames and match against the enrolled gallery."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from gallery import Gallery, load_gallery
from settings import Settings
from stream import FrameSource
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
) -> list[Any] | None:
	"""Return detections from the frame with the most (and highest-scoring) faces."""
	best_faces: list[Any] | None = None
	best_key = (-1, -1.0)

	for frame in frames:
		faces = face_app.get(frame)
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
) -> RecognitionResult:
	"""Detect and match faces in the best frame from *frames*."""
	faces = _pick_best_frame(face_app, frames)
	if not faces:
		return RecognitionResult(names=[], unknown=0, matches=[])

	matches = [_match_detected_face(face, gallery, threshold) for face in faces]
	names = sorted({match.name for match in matches if match.name is not None})
	unknown = sum(1 for match in matches if match.name is None)
	return RecognitionResult(names=names, unknown=unknown, matches=matches)


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

	gallery_path = Path(settings.gallery_path)
	if gallery is None:
		if not gallery_path.is_file():
			msg = f"Gallery not found: {gallery_path} (run enroll first)"
			raise FileNotFoundError(msg)
		gallery = load_gallery(gallery_path)

	app = face_app if face_app is not None else get_face_app(gallery.model)
	source = FrameSource(settings.stream_url)
	frames = source.grab_event_frames(settings.frames_per_event)
	if not frames:
		logger.warning("No frames grabbed from stream")
		return RecognitionResult(names=[], unknown=0, matches=[])

	return recognize_frames(
		frames,
		gallery,
		face_app=app,
		threshold=settings.recognition_threshold,
	)


def result_to_payload(result: RecognitionResult) -> dict[str, object]:
	"""Serialize a recognition result for HTTP / HA webhook payloads."""
	return {
		"event": "doorbell",
		"names": result.names,
		"unknown": result.unknown,
		"ts": datetime.now(UTC).isoformat(),
	}


def log_result(result: RecognitionResult) -> None:
	"""Log recognition output (Phase 1 — stdout only, no HA notify yet)."""
	if result.names:
		logger.info("Recognized: %s (%d unknown)", ", ".join(result.names), result.unknown)
	elif result.unknown:
		logger.info("Unknown visitor (%d face(s))", result.unknown)
	else:
		logger.info("No faces detected")
