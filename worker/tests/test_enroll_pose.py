"""Tests for enroll_pose head-pose validation."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from enroll_pose import adjust_yaw, enrollment_hint, face_quality_hint, pose_hint, read_pose

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
