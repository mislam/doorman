"""Head-pose checks for guided doorbell enrollment (InsightFace buffalo_l)."""

from __future__ import annotations

from typing import Any, Literal

import cv2
import numpy as np

PoseStep = Literal["center", "left", "right", "up", "down"]

# buffalo_l pose vector is [pitch, yaw, roll] in degrees (see InsightFace attribute model).
CENTER_YAW_MAX = 12.0
CENTER_PITCH_MAX = 11.0
SIDE_DELTA_MIN = 10.0
PITCH_DELTA_MIN = 15.0

# Enrollment quality gates — reject clipped / partial faces (forehead-only, chin-only, etc.).
ENROLL_MIN_DET_SCORE = 0.55
ENROLL_LANDMARK_EDGE_MARGIN = 0.02
ENROLL_MIN_FACE_FRAC = 0.10
ENROLL_PHONE_MIN_FACE_FRAC = 0.18
ENROLL_BG_MIN_INTER_EYE_FRAC = 0.14
ENROLL_BBOX_ASPECT_MIN = 0.45
ENROLL_BBOX_ASPECT_MAX = 2.2
ENROLL_MIN_FEATURE_SPAN_RATIO = 0.48
ENROLL_BBOX_LANDMARK_INSET = 0.18
ENROLL_MIN_LANDMARK_RATIO = 0.20

# Scene quality — lighting, sharpness, and background clutter (needs the full frame).
ENROLL_MIN_FACE_LUMA = 52.0
ENROLL_MIN_SHARPNESS = 45.0
ENROLL_BG_CORNER_FRAC = 0.16
ENROLL_BG_FACE_PAD_FRAC = 0.12
ENROLL_BG_RING_PAD_FRAC = 0.45
ENROLL_BG_INNER_EXCLUDE_FRAC = 0.55
ENROLL_SOBEL_THRESHOLD = 35.0
ENROLL_MAX_BG_EDGE_RATIO = 0.17


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
		return None

	if step == "right":
		if yaw_delta < SIDE_DELTA_MIN:
			return "Turn more right"
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


def _face_quality_pose_step(
	face: Any,
	frame_h: int,
	frame_w: int,
	pose_step: PoseStep,
) -> str | None:
	"""Lighter quality gate for pose turns — landmarks may sit near frame edges."""
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
	if pose_step in ("left", "right"):
		for _x, y in kps_arr:
			if y < edge or y > frame_h - edge:
				return "Show your full face"
	elif pose_step in ("up", "down"):
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

	min_span = inter_eye * (0.38 if pose_step in ("up", "down") else ENROLL_MIN_FEATURE_SPAN_RATIO)
	if mouth_y - eye_y < min_span:
		return "Show your full face"

	return None


def _inter_eye_span(face: Any) -> float | None:
	kps = getattr(face, "kps", None)
	if kps is None:
		return None
	kps_arr = np.asarray(kps, dtype=float)
	if kps_arr.shape != (5, 2):
		return None
	left_eye, right_eye, _nose, _left_mouth, _right_mouth = kps_arr
	inter_eye = float(np.linalg.norm(left_eye - right_eye))
	if inter_eye < 3:
		return None
	return inter_eye


def face_distance_hint(
	face: Any,
	frame_h: int,
	frame_w: int,
	*,
	strict: bool = False,
) -> str | None:
	"""Return distance guidance from face bbox size; stricter on phone (``strict=True``)."""
	min_dim = min(frame_h, frame_w)
	bbox = np.asarray(getattr(face, "bbox", None), dtype=float)
	if bbox.shape != (4,):
		return None
	x1, y1, x2, y2 = bbox
	bw = x2 - x1
	bh = y2 - y1
	if bw <= 1 or bh <= 1:
		return None

	min_frac = ENROLL_PHONE_MIN_FACE_FRAC if strict else ENROLL_MIN_FACE_FRAC
	if min(bw, bh) < min_dim * min_frac:
		return "Move closer"
	return None


def face_quality_hint(
	face: Any,
	frame_h: int,
	frame_w: int,
	*,
	pose_step: PoseStep | None = None,
) -> str | None:
	"""Return guidance when the detection looks clipped or incomplete, else ``None``."""
	if pose_step in ("up", "down", "left", "right"):
		return _face_quality_pose_step(face, frame_h, frame_w, pose_step)

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


def _clip_face_bbox(face: Any, frame_h: int, frame_w: int) -> tuple[int, int, int, int]:
	bbox = np.asarray(getattr(face, "bbox", None), dtype=float)
	if bbox.shape != (4,):
		return 0, 0, 0, 0
	x1, y1, x2, y2 = bbox
	return (
		max(0, int(x1)),
		max(0, int(y1)),
		min(frame_w, int(x2)),
		min(frame_h, int(y2)),
	)


def _region_edge_ratio(mag: np.ndarray, mask: np.ndarray) -> float:
	region = mag[mask]
	if region.size < 64:
		return 0.0
	return float(np.sum(region > ENROLL_SOBEL_THRESHOLD)) / float(region.size)


def _background_edge_ratio(gray: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> float:
	"""Edge density in frame corners, or an outer donut when the face fills the view."""
	bw = x2 - x1
	bh = y2 - y1
	if bw < 8 or bh < 8:
		return 0.0

	h, w = gray.shape
	sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
	sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
	mag = np.hypot(sobelx, sobely)

	corner_size = max(16, int(min(h, w) * ENROLL_BG_CORNER_FRAC))
	face_pad = int(max(bw, bh) * ENROLL_BG_FACE_PAD_FRAC)
	fx1 = max(0, x1 - face_pad)
	fy1 = max(0, y1 - face_pad)
	fx2 = min(w, x2 + face_pad)
	fy2 = min(h, y2 + face_pad)

	corner_ratios: list[float] = []
	for corner_y, corner_x in (
		(0, 0),
		(0, w - corner_size),
		(h - corner_size, 0),
		(h - corner_size, w - corner_size),
	):
		if (
			corner_y + corner_size > fy1
			and corner_y < fy2
			and corner_x + corner_size > fx1
			and corner_x < fx2
		):
			continue
		mask = np.zeros(gray.shape, dtype=bool)
		mask[corner_y : corner_y + corner_size, corner_x : corner_x + corner_size] = True
		corner_ratios.append(_region_edge_ratio(mag, mask))

	if corner_ratios:
		return max(corner_ratios)

	# Close-up: corners sit on the face — sample a thin outer ring past hair/shoulders.
	outer_pad = int(max(bw, bh) * ENROLL_BG_RING_PAD_FRAC)
	ox1 = max(0, x1 - outer_pad)
	oy1 = max(0, y1 - outer_pad)
	ox2 = min(w, x2 + outer_pad)
	oy2 = min(h, y2 + outer_pad)
	inner_pad_x = int(bw * ENROLL_BG_INNER_EXCLUDE_FRAC)
	inner_pad_y = int(bh * ENROLL_BG_INNER_EXCLUDE_FRAC)
	ix1 = max(0, x1 - inner_pad_x)
	iy1 = max(0, y1 - inner_pad_y)
	ix2 = min(w, x2 + inner_pad_x)
	iy2 = min(h, y2 + inner_pad_y)

	mask = np.zeros(gray.shape, dtype=bool)
	mask[oy1:oy2, ox1:ox2] = True
	mask[iy1:iy2, ix1:ix2] = False
	return _region_edge_ratio(mag, mask)


def _face_large_enough_for_bg_check(
	face: Any,
	frame_h: int,
	frame_w: int,
	*,
	mirror_yaw: bool,
) -> bool:
	"""Background clutter is only meaningful once the face fills enough of the frame."""
	min_dim = min(frame_h, frame_w)
	bbox = np.asarray(getattr(face, "bbox", None), dtype=float)
	if bbox.shape != (4,):
		return False
	x1, y1, x2, y2 = bbox
	bw = x2 - x1
	bh = y2 - y1
	if bw <= 1 or bh <= 1:
		return False
	if mirror_yaw:
		return min(bw, bh) >= min_dim * ENROLL_PHONE_MIN_FACE_FRAC
	inter_eye = _inter_eye_span(face)
	return inter_eye is not None and inter_eye >= min_dim * ENROLL_BG_MIN_INTER_EYE_FRAC


def face_scene_hint(
	face: Any,
	frame: np.ndarray,
	*,
	mirror_yaw: bool = False,
) -> str | None:
	"""Return guidance for lighting, blur, or busy background; else ``None``."""
	if frame.ndim != 3 or frame.shape[2] != 3:
		return None

	frame_h, frame_w = frame.shape[:2]
	x1, y1, x2, y2 = _clip_face_bbox(face, frame_h, frame_w)
	if x2 - x1 < 8 or y2 - y1 < 8:
		return "Show your full face"

	gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
	crop = gray[y1:y2, x1:x2]

	mean_luma = float(np.mean(crop))
	if mean_luma < ENROLL_MIN_FACE_LUMA:
		return "Need better lighting"

	if crop.shape[0] >= 3 and crop.shape[1] >= 3:
		sharpness = float(cv2.Laplacian(crop, cv2.CV_64F).var())
		if sharpness < ENROLL_MIN_SHARPNESS:
			return "Image is too blurry"

	if not _face_large_enough_for_bg_check(face, frame_h, frame_w, mirror_yaw=mirror_yaw):
		return None

	edge_ratio = _background_edge_ratio(gray, x1, y1, x2, y2)
	if edge_ratio > ENROLL_MAX_BG_EDGE_RATIO:
		return "Use a plain background"

	return None


def enrollment_environment_hint(
	face: Any,
	frame_h: int,
	frame_w: int,
	*,
	mirror_yaw: bool = False,
	frame: np.ndarray | None = None,
) -> str | None:
	"""Distance and scene checks — run on every poll before pose."""
	det_score = float(getattr(face, "det_score", 0.0))
	if det_score < ENROLL_MIN_DET_SCORE:
		return "Show your full face"

	hint = face_distance_hint(face, frame_h, frame_w, strict=mirror_yaw)
	if hint is not None:
		return hint
	if frame is not None:
		return face_scene_hint(face, frame, mirror_yaw=mirror_yaw)
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
	frame: np.ndarray | None = None,
	preflight: bool = False,
) -> str | None:
	"""Environment first, then pose-specific quality and pose (or preflight frontal face only)."""
	hint = enrollment_environment_hint(
		face,
		frame_h,
		frame_w,
		mirror_yaw=mirror_yaw,
		frame=frame,
	)
	if hint is not None:
		return hint

	if preflight:
		return face_quality_hint(face, frame_h, frame_w, pose_step="center")

	yaw, pitch, _roll = read_pose(face)
	yaw = adjust_yaw(yaw, mirror_yaw)
	hint = face_quality_hint(face, frame_h, frame_w, pose_step=pose_step)
	if hint is not None:
		return hint
	return pose_hint(
		pose_step,
		yaw,
		pitch,
		baseline_yaw=baseline_yaw,
		baseline_pitch=baseline_pitch,
	)
