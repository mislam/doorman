"""CLAHE vs raw preprocessing checks on doorbell fixtures — homelab Docker only."""

from __future__ import annotations

import pytest
from doorbell_fixtures import (
	add_summary_section,
	load_manifest,
	missing_paths,
	read_frame,
)

from frame_enhance import detect_faces
from gallery import Gallery
from recognize import recognize_frames

_preprocessing_lines: list[str] = []

pytestmark = pytest.mark.preprocessing


def _preprocessing_ids() -> list[str]:
	try:
		manifest = load_manifest()
	except FileNotFoundError:
		return []
	cases = manifest.get("preprocessing", [])
	return [case["id"] for case in cases]


def _best_det_score(faces: list[object]) -> float:
	return max((float(face.det_score) for face in faces), default=0.0)


def _best_match_score(result: object) -> float:
	if not result.matches:
		return 0.0
	return max(float(match.score) for match in result.matches)


def _format_preprocessing_result(
	case_id: str,
	*,
	raw_det: float,
	clahe_det: float,
	raw_match: float,
	clahe_match: float,
	match_tolerance: float,
) -> str:
	match_gain = clahe_match - raw_match
	return (
		f"  {case_id:22}  detect {raw_det:.2f}→{clahe_det:.2f}  "
		f"match {raw_match:.2f}→{clahe_match:.2f}  "
		f"(Δ {match_gain:+.2f}, allow −{match_tolerance:.2f})"
	)


@pytest.fixture(scope="module", autouse=True)
def _preprocessing_summary() -> None:
	yield
	if not _preprocessing_lines:
		return
	add_summary_section(
		"Preprocessing (raw vs CLAHE on same frame)",
		list(_preprocessing_lines),
		hint="  CLAHE must not lower match by more than the allow column.",
	)


@pytest.mark.parametrize("case_id", _preprocessing_ids())
def test_clahe_improves_doorbell_frame(
	case_id: str,
	face_app,
	fixture_gallery: Gallery,
) -> None:
	manifest = load_manifest()
	case = next(item for item in manifest["preprocessing"] if item["id"] == case_id)

	frame_rel = case["frame"]
	if missing_paths([frame_rel]):
		pytest.skip(f"Missing preprocessing frame for {case_id}: {frame_rel}")

	frame = read_frame(frame_rel)
	threshold = float(case.get("match_threshold", manifest.get("recognition_threshold", 0.4)))
	match_tolerance = float(case.get("match_tolerance", 0.03))
	expected_names = case.get("expected_names")

	raw_faces = detect_faces(face_app, frame, enhance_mode="off")
	clahe_faces = detect_faces(face_app, frame, enhance_mode="clahe")
	raw_det = _best_det_score(raw_faces)
	clahe_det = _best_det_score(clahe_faces)

	raw_result = recognize_frames(
		[frame],
		fixture_gallery,
		face_app=face_app,
		threshold=threshold,
		enhance_mode="off",
	)
	clahe_result = recognize_frames(
		[frame],
		fixture_gallery,
		face_app=face_app,
		threshold=threshold,
		enhance_mode="clahe",
	)
	raw_match = _best_match_score(raw_result)
	clahe_match = _best_match_score(clahe_result)

	_preprocessing_lines.append(
		_format_preprocessing_result(
			case_id,
			raw_det=raw_det,
			clahe_det=clahe_det,
			raw_match=raw_match,
			clahe_match=clahe_match,
			match_tolerance=match_tolerance,
		),
	)

	if case.get("clahe_must_detect"):
		assert clahe_faces, f"CLAHE found no face in {case_id}"

	if not raw_faces and case.get("clahe_must_detect_when_raw_empty", True):
		assert clahe_faces, f"{case_id}: raw missed face but CLAHE must detect"

	if expected_names is not None:
		assert clahe_result.names == expected_names, (
			f"{case_id}: CLAHE identified {clahe_result.names}, expected {expected_names}"
		)
		if raw_result.names != expected_names:
			assert clahe_result.names == expected_names, (
				f"{case_id}: CLAHE must recover when raw identifies {raw_result.names}"
			)

	min_det_gain = float(case.get("min_det_gain", 0.0))
	if min_det_gain > 0:
		assert clahe_det - raw_det >= min_det_gain, (
			f"{case_id}: det gain {clahe_det - raw_det:.2f} < {min_det_gain:.2f}"
		)

	min_match_gain = float(case.get("min_match_gain", 0.0))
	if min_match_gain > 0:
		assert clahe_match - raw_match >= min_match_gain, (
			f"{case_id}: match gain {clahe_match - raw_match:.2f} < {min_match_gain:.2f}"
		)
	elif min_match_gain == 0.0:
		assert clahe_match + match_tolerance >= raw_match, (
			f"{case_id}: CLAHE match {clahe_match:.2f} worse than raw {raw_match:.2f} "
			f"beyond tolerance {match_tolerance:.2f}"
		)
