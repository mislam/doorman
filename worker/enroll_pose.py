"""Head-pose checks for guided doorbell enrollment (InsightFace buffalo_l)."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np

PoseStep = Literal["center", "left", "right", "up", "down"]

# buffalo_l pose vector is [pitch, yaw, roll] in degrees (see InsightFace attribute model).
CENTER_YAW_MAX = 12.0
CENTER_PITCH_MAX = 11.0
SIDE_DELTA_MIN = 14.0
SIDE_DELTA_MAX = 42.0
PITCH_DELTA_MIN = 15.0

# Enrollment quality gates — reject clipped / partial faces (forehead-only, chin-only, etc.).
ENROLL_MIN_DET_SCORE = 0.55
ENROLL_LANDMARK_EDGE_MARGIN = 0.02
ENROLL_MIN_FACE_FRAC = 0.10
ENROLL_BBOX_ASPECT_MIN = 0.45
ENROLL_BBOX_ASPECT_MAX = 2.2
ENROLL_MIN_FEATURE_SPAN_RATIO = 0.48
ENROLL_BBOX_LANDMARK_INSET = 0.18
ENROLL_MIN_LANDMARK_RATIO = 0.20


def read_pose(face: Any) -> tuple[float, float, float]:
	"""Return (yaw, pitch, roll) in degrees; zeros when pose is missing."""
	pose = getattr(face, "pose", None)
	if pose is None:
		return 0.0, 0.0, 0.0
	pitch = float(pose[0])
	yaw = float(pose[1])
	roll = float(pose[2])
	return yaw, pitch, roll


def adjust_yaw(yaw: float, mirror: bool) -> float:
	"""Flip yaw for mirrored front-camera frames so left/right hints match the user."""
	return -yaw if mirror else yaw


def pose_hint(
	step: PoseStep,
	yaw: float,
	pitch: float,
	*,
	baseline_yaw: float | None = None,
	baseline_pitch: float | None = None,
) -> str | None:
	"""Return guidance when pose is out of range for *step*, else ``None``."""
	if step == "center":
		if baseline_yaw is not None and baseline_pitch is not None:
			if abs(yaw - baseline_yaw) > CENTER_YAW_MAX:
				return "Face the camera straight on"
			if abs(pitch - baseline_pitch) > CENTER_PITCH_MAX:
				return "Look straight at the camera"
		else:
			if abs(yaw) > CENTER_YAW_MAX:
				return "Face the camera straight on"
			if abs(pitch) > CENTER_PITCH_MAX:
				return "Look straight at the camera"
		return None

	if baseline_yaw is None or baseline_pitch is None:
		return "Hold still"

	yaw_delta = yaw - baseline_yaw
	pitch_delta = pitch - baseline_pitch

	# Signed yaw — tuned for doorbell view (positive delta = subject's left).
	if step == "left":
		if yaw_delta > -SIDE_DELTA_MIN:
			return "Turn more left"
		if yaw_delta < -SIDE_DELTA_MAX:
			return "A bit less left"
		return None

	if step == "right":
		if yaw_delta < SIDE_DELTA_MIN:
			return "Turn more right"
		if yaw_delta > SIDE_DELTA_MAX:
			return "A bit less right"
		return None

	# Pitch relative to center — positive pitch_delta = chin up on this camera.
	if step == "up":
		if pitch_delta < PITCH_DELTA_MIN:
			return "Look up more"
		return None

	if step == "down":
		if pitch_delta > -PITCH_DELTA_MIN:
			return "Look down more"
		return None

	return None


def _face_quality_pitch_step(
	face: Any,
	frame_h: int,
	frame_w: int,
	pose_step: PoseStep,
) -> str | None:
	"""Lighter quality gate for up/down — pose enforces tilt; chin/forehead may sit near edges."""
	det_score = float(getattr(face, "det_score", 0.0))
	if det_score < ENROLL_MIN_DET_SCORE:
		return "Show your full face"

	bbox = np.asarray(getattr(face, "bbox", None), dtype=float)
	if bbox.shape != (4,):
		return "Show your full face"
	x1, y1, x2, y2 = bbox
	bw = x2 - x1
	bh = y2 - y1
	if bw <= 1 or bh <= 1:
		return "Show your full face"

	min_dim = min(frame_h, frame_w)
	if min(bw, bh) < min_dim * ENROLL_MIN_FACE_FRAC:
		return "Move closer"

	kps = getattr(face, "kps", None)
	if kps is None:
		return "Show your full face"
	kps_arr = np.asarray(kps, dtype=float)
	if kps_arr.shape != (5, 2):
		return "Show your full face"

	edge = min(frame_h, frame_w) * ENROLL_LANDMARK_EDGE_MARGIN
	for x, _y in kps_arr:
		if x < edge or x > frame_w - edge:
			return "Show your full face"

	left_eye, right_eye, nose, left_mouth, right_mouth = kps_arr
	eye_y = (left_eye[1] + right_eye[1]) / 2
	mouth_y = (left_mouth[1] + right_mouth[1]) / 2
	if eye_y >= nose[1] - 1 or mouth_y <= nose[1] + 1:
		return "Show your full face"

	inter_eye = float(np.linalg.norm(left_eye - right_eye))
	if inter_eye < 3:
		return "Show your full face"

	# Reject forehead/chin-only clusters; allow natural pitch compression.
	min_span = inter_eye * (0.38 if pose_step in ("up", "down") else ENROLL_MIN_FEATURE_SPAN_RATIO)
	if mouth_y - eye_y < min_span:
		return "Show your full face"

	return None


def face_quality_hint(
	face: Any,
	frame_h: int,
	frame_w: int,
	*,
	pose_step: PoseStep | None = None,
) -> str | None:
	"""Return guidance when the detection looks clipped or incomplete, else ``None``."""
	if pose_step in ("up", "down"):
		return _face_quality_pitch_step(face, frame_h, frame_w, pose_step)

	det_score = float(getattr(face, "det_score", 0.0))
	if det_score < ENROLL_MIN_DET_SCORE:
		return "Show your full face"

	bbox = np.asarray(getattr(face, "bbox", None), dtype=float)
	if bbox.shape != (4,):
		return "Show your full face"
	x1, y1, x2, y2 = bbox
	bw = x2 - x1
	bh = y2 - y1
	if bw <= 1 or bh <= 1:
		return "Show your full face"

	aspect = bw / bh
	if aspect < ENROLL_BBOX_ASPECT_MIN or aspect > ENROLL_BBOX_ASPECT_MAX:
		return "Show your full face"

	min_dim = min(frame_h, frame_w)
	if min(bw, bh) < min_dim * ENROLL_MIN_FACE_FRAC:
		return "Move closer"

	kps = getattr(face, "kps", None)
	if kps is None:
		return "Show your full face"
	kps_arr = np.asarray(kps, dtype=float)
	if kps_arr.shape != (5, 2):
		return "Show your full face"

	edge = min(frame_h, frame_w) * ENROLL_LANDMARK_EDGE_MARGIN
	for index, (x, y) in enumerate(kps_arr):
		if x < edge or x > frame_w - edge:
			return "Show your full face"
		if y < edge and not (pose_step == "down" and index < 2):
			return "Show your full face"
		if y > frame_h - edge and not (pose_step == "up" and index >= 3):
			return "Show your full face"

	left_eye, right_eye, nose, left_mouth, right_mouth = kps_arr
	eye_y = (left_eye[1] + right_eye[1]) / 2
	mouth_y = (left_mouth[1] + right_mouth[1]) / 2
	if eye_y >= nose[1] - 1 or mouth_y <= nose[1] + 1:
		return "Show your full face"

	inter_eye = float(np.linalg.norm(left_eye - right_eye))
	if inter_eye < 3:
		return "Show your full face"
	eye_nose = float(np.linalg.norm((left_eye + right_eye) / 2 - nose))
	nose_mouth = float(np.linalg.norm(nose - (left_mouth + right_mouth) / 2))
	min_span = inter_eye * ENROLL_MIN_LANDMARK_RATIO
	if eye_nose < min_span or nose_mouth < min_span:
		return "Show your full face"

	if mouth_y - eye_y < inter_eye * ENROLL_MIN_FEATURE_SPAN_RATIO:
		return "Show your full face"

	inset = bh * ENROLL_BBOX_LANDMARK_INSET
	if pose_step != "down" and eye_y - y1 < inset:
		return "Show your full face"
	if pose_step != "up" and y2 - mouth_y < inset:
		return "Show your full face"

	return None


def enrollment_hint(
	face: Any,
	pose_step: PoseStep,
	frame_h: int,
	frame_w: int,
	*,
	baseline_yaw: float | None = None,
	baseline_pitch: float | None = None,
	mirror_yaw: bool = False,
) -> str | None:
	"""Pose guidance first; quality only when pose is in range for the step."""
	yaw, pitch, _roll = read_pose(face)
	yaw = adjust_yaw(yaw, mirror_yaw)
	hint = pose_hint(
		pose_step,
		yaw,
		pitch,
		baseline_yaw=baseline_yaw,
		baseline_pitch=baseline_pitch,
	)
	if hint is not None:
		return hint
	return face_quality_hint(face, frame_h, frame_w, pose_step=pose_step)
