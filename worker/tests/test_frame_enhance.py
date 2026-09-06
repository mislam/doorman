"""Tests for frame_enhance (OpenCV only — runs on Mac)."""

from __future__ import annotations

import numpy as np

from frame_enhance import apply_clahe, detect_faces, iter_frame_variants, normalize_enhance_mode


def test_normalize_enhance_mode_unknown_falls_back_to_off() -> None:
	assert normalize_enhance_mode("CLAHE") == "clahe"
	assert normalize_enhance_mode("bogus") == "off"


def test_apply_clahe_lifts_shadow_region() -> None:
	frame = np.zeros((120, 160, 3), dtype=np.uint8)
	frame[:60, :] = 240  # bright sky
	shadow = np.linspace(4, 14, 160, dtype=np.uint8)
	frame[60:, :] = shadow[np.newaxis, :, np.newaxis]
	roi = frame[70:110, 40:120]

	before = float(roi.mean())
	enhanced = apply_clahe(frame)
	after = float(enhanced[70:110, 40:120].mean())

	assert after > before + 4.0


def test_iter_frame_variants_off_yields_raw_only() -> None:
	frame = np.zeros((8, 8, 3), dtype=np.uint8)
	assert list(iter_frame_variants(frame, "off")) == [frame]


def test_iter_frame_variants_clahe_yields_raw_and_enhanced() -> None:
	frame = np.zeros((32, 32, 3), dtype=np.uint8)
	frame[:, :16] = 220
	variants = list(iter_frame_variants(frame, "clahe"))
	assert len(variants) == 2
	assert variants[0] is frame
	assert variants[1].shape == frame.shape
	assert not np.array_equal(variants[0], variants[1])


def test_detect_faces_prefers_enhanced_variant() -> None:
	frame = np.zeros((16, 16, 3), dtype=np.uint8)

	class FakeFace:
		def __init__(self, det_score: float) -> None:
			self.det_score = det_score

	class FakeApp:
		def __init__(self) -> None:
			self.calls = 0

		def get(self, _frame: np.ndarray) -> list[FakeFace]:
			self.calls += 1
			if self.calls == 1:
				return []
			return [FakeFace(0.8)]

	app = FakeApp()
	faces = detect_faces(app, frame, enhance_mode="clahe")

	assert len(faces) == 1
	assert faces[0].det_score == 0.8
	assert app.calls == 2
