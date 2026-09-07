"""Tests for enroll_pose head-pose validation."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from enroll_pose import (
	adjust_yaw,
	enrollment_hint,
	face_distance_hint,
	face_quality_hint,
	face_scene_hint,
	pose_hint,
	read_pose,
)

BASELINE_YAW = 0.0
BASELINE_PITCH = 5.0


def test_read_pose_missing() -> None:
	assert read_pose(SimpleNamespace()) == (0.0, 0.0, 0.0)


def test_read_pose_buffalo_order() -> None:
	face = SimpleNamespace(pose=np.array([10.0, -22.0, 3.0]))
	assert read_pose(face) == (-22.0, 10.0, 3.0)


def test_adjust_yaw_mirrors() -> None:
	assert adjust_yaw(12.0, False) == 12.0
	assert adjust_yaw(12.0, True) == -12.0


def test_center_pose_accepts_frontal() -> None:
	assert pose_hint("center", yaw=5.0, pitch=3.0) is None
	assert (
		pose_hint(
			"center",
			yaw=2.0,
			pitch=6.0,
			baseline_yaw=BASELINE_YAW,
			baseline_pitch=BASELINE_PITCH,
		)
		is None
	)


def test_center_pose_rejects_lingering_tilt() -> None:
	"""After up/down, center must return near the stored baseline — not absolute angles only."""
	assert (
		pose_hint(
			"center",
			yaw=0.0,
			pitch=-10.0,
			baseline_yaw=BASELINE_YAW,
			baseline_pitch=BASELINE_PITCH,
		)
		== "Look straight at the camera"
	)
	assert (
		pose_hint(
			"center",
			yaw=0.0,
			pitch=24.0,
			baseline_yaw=BASELINE_YAW,
			baseline_pitch=BASELINE_PITCH,
		)
		== "Look straight at the camera"
	)


def test_left_pose_needs_negative_yaw_delta() -> None:
	assert (
		pose_hint(
			"left",
			yaw=-15.0,
			pitch=BASELINE_PITCH,
			baseline_yaw=BASELINE_YAW,
			baseline_pitch=BASELINE_PITCH,
		)
		is None
	)
	assert (
		pose_hint(
			"left",
			yaw=-5.0,
			pitch=BASELINE_PITCH,
			baseline_yaw=BASELINE_YAW,
			baseline_pitch=BASELINE_PITCH,
		)
		is not None
	)


def test_left_pose_accepts_large_turn() -> None:
	assert (
		pose_hint(
			"left",
			yaw=-50.0,
			pitch=BASELINE_PITCH,
			baseline_yaw=BASELINE_YAW,
			baseline_pitch=BASELINE_PITCH,
		)
		is None
	)


def test_right_pose_needs_positive_yaw_delta() -> None:
	assert (
		pose_hint(
			"right",
			yaw=15.0,
			pitch=BASELINE_PITCH,
			baseline_yaw=BASELINE_YAW,
			baseline_pitch=BASELINE_PITCH,
		)
		is None
	)


def test_up_pose_needs_higher_pitch() -> None:
	assert (
		pose_hint(
			"up",
			yaw=0.0,
			pitch=21.0,
			baseline_yaw=BASELINE_YAW,
			baseline_pitch=BASELINE_PITCH,
		)
		is None
	)
	assert (
		pose_hint(
			"up",
			yaw=0.0,
			pitch=18.0,
			baseline_yaw=BASELINE_YAW,
			baseline_pitch=BASELINE_PITCH,
		)
		is not None
	)


def test_up_pose_accepts_extra_tilt() -> None:
	"""No upper pitch cap — once past the minimum tilt, any further look-up is fine."""
	assert (
		pose_hint(
			"up",
			yaw=0.0,
			pitch=40.0,
			baseline_yaw=BASELINE_YAW,
			baseline_pitch=BASELINE_PITCH,
		)
		is None
	)


def test_down_pose_needs_lower_pitch() -> None:
	assert (
		pose_hint(
			"down",
			yaw=0.0,
			pitch=-11.0,
			baseline_yaw=BASELINE_YAW,
			baseline_pitch=BASELINE_PITCH,
		)
		is None
	)
	assert (
		pose_hint(
			"down",
			yaw=0.0,
			pitch=-8.0,
			baseline_yaw=BASELINE_YAW,
			baseline_pitch=BASELINE_PITCH,
		)
		is not None
	)


def _valid_face_kps() -> np.ndarray:
	return np.array(
		[[25, 28], [55, 28], [40, 40], [30, 58], [50, 58]],
		dtype=np.float32,
	)


def test_face_distance_hint_phone_rejects_far_face() -> None:
	face = SimpleNamespace(
		det_score=0.99,
		bbox=np.array([200, 200, 270, 270], dtype=np.float32),
		kps=np.array(
			[[210, 220], [260, 220], [235, 240], [220, 255], [250, 255]],
			dtype=np.float32,
		),
	)
	assert face_distance_hint(face, 480, 480, strict=True) == "Move closer"
	assert face_distance_hint(face, 480, 480, strict=False) is None


def test_face_distance_hint_phone_accepts_near_face() -> None:
	kps = np.array(
		[[140, 180], [300, 180], [220, 250], [170, 330], [270, 330]],
		dtype=np.float32,
	)
	face = SimpleNamespace(
		det_score=0.99,
		bbox=np.array([120, 150, 320, 360], dtype=np.float32),
		kps=kps,
	)
	assert face_distance_hint(face, 480, 480, strict=True) is None


def test_face_scene_skips_background_when_face_is_far() -> None:
	"""Far phone capture should not mislabel room corners as a busy background."""
	rng = np.random.default_rng(2)
	frame = np.full((480, 480, 3), 230, dtype=np.uint8)
	kps = np.array(
		[[180, 200], [230, 200], [205, 230], [190, 260], [220, 260]],
		dtype=np.float32,
	)
	face = SimpleNamespace(
		det_score=0.99,
		bbox=np.array([160, 180, 250, 280], dtype=np.float32),
		kps=kps,
	)
	x1, y1, x2, y2 = 160, 180, 250, 280
	frame[y1:y2, x1:x2] = rng.integers(120, 200, size=(y2 - y1, x2 - x1, 3), dtype=np.uint8)
	frame[:120, :] = rng.integers(20, 220, size=(120, 480, 3), dtype=np.uint8)
	assert face_scene_hint(face, frame) is None


def test_enrollment_hint_phone_prefers_move_closer_over_background() -> None:
	rng = np.random.default_rng(2)
	frame = np.full((480, 480, 3), 230, dtype=np.uint8)
	kps = np.array(
		[[210, 220], [260, 220], [235, 240], [220, 255], [250, 255]],
		dtype=np.float32,
	)
	face = SimpleNamespace(
		det_score=0.99,
		pose=np.array([5.0, 2.0, 0.0]),
		bbox=np.array([200, 200, 270, 270], dtype=np.float32),
		kps=kps,
	)
	x1, y1, x2, y2 = 200, 200, 270, 270
	frame[y1:y2, x1:x2] = rng.integers(120, 200, size=(y2 - y1, x2 - x1, 3), dtype=np.uint8)
	frame[:120, :] = rng.integers(20, 220, size=(120, 480, 3), dtype=np.uint8)
	assert (
		enrollment_hint(
			face,
			"center",
			480,
			480,
			baseline_yaw=0.0,
			baseline_pitch=5.0,
			mirror_yaw=True,
			frame=frame,
		)
		== "Move closer"
	)


def test_enrollment_preflight_skips_pose_turn() -> None:
	face = SimpleNamespace(
		det_score=0.99,
		pose=np.array([5.0, 2.0, 0.0]),
		bbox=np.array([15, 15, 65, 75], dtype=np.float32),
		kps=_valid_face_kps(),
	)
	assert (
		enrollment_hint(
			face,
			"left",
			80,
			80,
			baseline_yaw=0.0,
			baseline_pitch=5.0,
			preflight=True,
		)
		is None
	)


def test_enrollment_pose_runs_after_environment() -> None:
	face = SimpleNamespace(
		det_score=0.99,
		pose=np.array([5.0, 2.0, 0.0]),
		bbox=np.array([15, 15, 65, 75], dtype=np.float32),
		kps=_valid_face_kps(),
	)
	assert (
		enrollment_hint(
			face,
			"left",
			80,
			80,
			baseline_yaw=0.0,
			baseline_pitch=5.0,
		)
		== "Turn more left"
	)


def test_face_scene_checks_background_on_phone_when_close() -> None:
	rng = np.random.default_rng(2)
	frame = np.full((480, 480, 3), 230, dtype=np.uint8)
	kps = np.array(
		[[140, 180], [300, 180], [220, 250], [170, 330], [270, 330]],
		dtype=np.float32,
	)
	face = SimpleNamespace(
		det_score=0.99,
		bbox=np.array([120, 150, 320, 360], dtype=np.float32),
		kps=kps,
	)
	x1, y1, x2, y2 = 120, 150, 320, 360
	frame[y1:y2, x1:x2] = rng.integers(120, 200, size=(y2 - y1, x2 - x1, 3), dtype=np.uint8)
	frame[:120, :] = rng.integers(20, 220, size=(120, 480, 3), dtype=np.uint8)
	assert face_scene_hint(face, frame, mirror_yaw=True) == "Use a plain background"


def test_face_quality_accepts_full_face() -> None:
	face = SimpleNamespace(
		det_score=0.99,
		bbox=np.array([15, 15, 65, 75], dtype=np.float32),
		kps=_valid_face_kps(),
	)
	assert face_quality_hint(face, 80, 80) is None


def test_face_quality_accepts_face_filling_frame() -> None:
	"""Bbox may touch frame edges when landmarks are inset — full face still passes."""
	kps = np.array(
		[[120, 180], [280, 180], [200, 260], [150, 320], [250, 320]],
		dtype=np.float32,
	)
	face = SimpleNamespace(
		det_score=0.99,
		bbox=np.array([0, 0, 400, 400], dtype=np.float32),
		kps=kps,
	)
	assert face_quality_hint(face, 400, 400) is None


def test_face_quality_rejects_clipped_landmarks() -> None:
	face = SimpleNamespace(
		det_score=0.99,
		bbox=np.array([15, 0, 65, 40], dtype=np.float32),
		kps=np.array([[25, 0.5], [55, 0.5], [40, 8], [30, 12], [50, 12]], dtype=np.float32),
	)
	assert face_quality_hint(face, 80, 80) == "Show your full face"


def test_face_quality_rejects_forehead_cluster() -> None:
	face = SimpleNamespace(
		det_score=0.99,
		bbox=np.array([15, 15, 65, 75], dtype=np.float32),
		kps=np.array([[25, 20], [55, 20], [40, 28], [30, 30], [50, 30]], dtype=np.float32),
	)
	assert face_quality_hint(face, 80, 80) == "Show your full face"


def test_face_quality_rejects_bbox_hugging_landmarks() -> None:
	"""Eyes or mouth flush with the bbox edge — partial face in frame."""
	face = SimpleNamespace(
		det_score=0.99,
		bbox=np.array([20, 10, 60, 50], dtype=np.float32),
		kps=np.array([[25, 10], [55, 10], [40, 22], [30, 46], [50, 46]], dtype=np.float32),
	)
	assert face_quality_hint(face, 80, 80) == "Show your full face"


def test_enrollment_hint_accepts_extreme_up_pose() -> None:
	"""No upper pitch cap — extreme look-up still passes pose and light up/down quality."""
	face = SimpleNamespace(
		det_score=0.99,
		pose=np.array([40.0, 3.0, 0.0]),
		bbox=np.array([20, 10, 60, 50], dtype=np.float32),
		kps=np.array([[25, 10], [55, 10], [40, 22], [30, 46], [50, 46]], dtype=np.float32),
	)
	assert enrollment_hint(face, "up", 80, 80, baseline_yaw=0.0, baseline_pitch=5.0) is None


def test_face_quality_allows_chin_low_on_up_step() -> None:
	kps = np.array(
		[[25, 28], [55, 28], [40, 40], [30, 78], [50, 78]],
		dtype=np.float32,
	)
	face = SimpleNamespace(
		det_score=0.99,
		bbox=np.array([15, 15, 65, 80], dtype=np.float32),
		kps=kps,
	)
	assert face_quality_hint(face, 80, 80, pose_step="up") is None


def test_enrollment_hint_accepts_valid_up_pose() -> None:
	"""In-range look-up passes after pose gate — nose/chin may sit low in square crop."""
	kps = np.array(
		[[25, 18], [55, 18], [40, 38], [30, 76], [50, 76]],
		dtype=np.float32,
	)
	face = SimpleNamespace(
		det_score=0.99,
		pose=np.array([22.0, 3.0, 0.0]),
		bbox=np.array([15, 12, 65, 78], dtype=np.float32),
		kps=kps,
	)
	assert enrollment_hint(face, "up", 80, 80, baseline_yaw=0.0, baseline_pitch=5.0) is None


def _face_bbox_frame(
	frame: np.ndarray,
	*,
	det_score: float = 0.99,
	margin_div: int = 8,
) -> SimpleNamespace:
	h, w = frame.shape[:2]
	margin = min(h, w) // margin_div
	return SimpleNamespace(
		det_score=det_score,
		bbox=np.array([margin, margin, w - margin, h - margin], dtype=np.float32),
		kps=np.array(
			[
				[w * 0.35, h * 0.38],
				[w * 0.65, h * 0.38],
				[w * 0.50, h * 0.52],
				[w * 0.40, h * 0.68],
				[w * 0.60, h * 0.68],
			],
			dtype=np.float32,
		),
	)


def test_face_scene_rejects_dark_face() -> None:
	frame = np.full((120, 120, 3), 28, dtype=np.uint8)
	face = _face_bbox_frame(frame)
	assert face_scene_hint(face, frame) == "Need better lighting"


def test_face_scene_rejects_blurry_face() -> None:
	frame = np.full((120, 120, 3), 170, dtype=np.uint8)
	face = _face_bbox_frame(frame)
	assert face_scene_hint(face, frame) == "Image is too blurry"


def test_face_scene_accepts_well_lit_sharp_face() -> None:
	rng = np.random.default_rng(0)
	frame = np.full((120, 120, 3), 165, dtype=np.uint8)
	frame[15:105, 15:105] = rng.integers(120, 200, size=(90, 90, 3), dtype=np.uint8)
	face = _face_bbox_frame(frame)
	assert face_scene_hint(face, frame) is None


def test_face_scene_accepts_closeup_on_plain_wall() -> None:
	"""Close-up phone capture: hair silhouette must not count as a busy background."""
	rng = np.random.default_rng(0)
	size = 480
	frame = np.full((size, size, 3), 230, dtype=np.uint8)
	margin = int(size * 0.12)
	inset = int(size * 0.05)
	frame[margin : size - margin, margin : size - margin] = rng.integers(
		40,
		150,
		size=(size - 2 * margin, size - 2 * margin, 3),
		dtype=np.uint8,
	)
	face = SimpleNamespace(
		bbox=np.array(
			[margin + inset, margin + inset, size - margin - inset, size - margin - inset],
			dtype=np.float32,
		),
	)
	assert face_scene_hint(face, frame) is None


def test_face_scene_rejects_busy_background() -> None:
	rng = np.random.default_rng(2)
	frame = np.full((200, 200, 3), 175, dtype=np.uint8)
	face = _face_bbox_frame(frame, margin_div=4)
	x1, y1, x2, y2 = (int(face.bbox[0]), int(face.bbox[1]), int(face.bbox[2]), int(face.bbox[3]))
	frame[y1:y2, x1:x2] = rng.integers(120, 200, size=(y2 - y1, x2 - x1, 3), dtype=np.uint8)
	# Cluttered shelf / doorway above the face — outside the face bbox.
	frame[: max(0, y1 - 5), :, :] = rng.integers(
		20,
		220,
		size=(max(0, y1 - 5), 200, 3),
		dtype=np.uint8,
	)
	assert face_scene_hint(face, frame) == "Use a plain background"
