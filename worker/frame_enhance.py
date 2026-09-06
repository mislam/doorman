"""Frame preprocessing for doorbell backlight (CLAHE on luminance)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import cv2

if TYPE_CHECKING:
	from collections.abc import Iterator

	from numpy.typing import NDArray


VALID_ENHANCE_MODES = frozenset({"off", "clahe"})


def normalize_enhance_mode(mode: str) -> str:
	"""Return a supported enhance mode; unknown values fall back to ``off``."""
	normalized = mode.strip().lower()
	if normalized in VALID_ENHANCE_MODES:
		return normalized
	return "off"


def apply_clahe(
	frame: NDArray,
	*,
	clip_limit: float = 2.0,
	tile_grid_size: tuple[int, int] = (8, 8),
) -> NDArray:
	"""Lift shadows via CLAHE on the L channel (LAB), preserving color."""
	lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
	l_channel, a_channel, b_channel = cv2.split(lab)
	clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
	enhanced_l = clahe.apply(l_channel)
	merged = cv2.merge((enhanced_l, a_channel, b_channel))
	return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def iter_frame_variants(frame: NDArray, enhance_mode: str) -> Iterator[NDArray]:
	"""Yield detection inputs — raw frame, then CLAHE when enabled."""
	yield frame
	if normalize_enhance_mode(enhance_mode) == "clahe":
		yield apply_clahe(frame)


def detect_faces(face_app: object, frame: NDArray, *, enhance_mode: str) -> list[object]:
	"""Run InsightFace on raw and enhanced variants; keep the best detection set."""
	best_faces: list[object] | None = None
	best_key = (-1, -1.0)

	for variant in iter_frame_variants(frame, enhance_mode):
		faces = face_app.get(variant)
		if not faces:
			continue
		key = (len(faces), sum(float(face.det_score) for face in faces))
		if key > best_key:
			best_key = key
			best_faces = list(faces)

	return best_faces or []
