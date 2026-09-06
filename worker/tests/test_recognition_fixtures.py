"""Doorbell footage fixture tests — InsightFace on homelab Docker only."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
import pytest
from doorbell_fixtures import (
	add_summary_section,
	load_manifest,
	missing_paths,
	resolve_fixture_path,
)

from frame_enhance import detect_faces
from gallery import Gallery
from recognize import _match_detected_face, recognize_frames

_scenario_lines: list[str] = []

pytestmark = pytest.mark.integration


def _scenario_ids() -> list[str]:
	try:
		manifest = load_manifest()
	except FileNotFoundError:
		return []
	scenarios = manifest.get("scenarios", [])
	return [scenario["id"] for scenario in scenarios]


def _format_scenario_result(
	scenario_id: str,
	result: Any,
	*,
	threshold: float,
) -> str:
	if result.matches:
		best_det = max(match.det_score for match in result.matches)
		best_match = max(match.score for match in result.matches)
	else:
		best_det = 0.0
		best_match = 0.0
	names = ",".join(result.names) if result.names else "nobody"
	extra = f", {result.unknown} unknown" if result.unknown else ""
	return (
		f"  {scenario_id:22}  detect {best_det:.2f}  "
		f"match {best_match:.2f} (min {threshold:.2f})  → {names}{extra}"
	)


@pytest.fixture(scope="module", autouse=True)
def _scenario_summary(fixture_gallery: Gallery) -> None:
	yield
	if not _scenario_lines:
		return
	lines = list(_scenario_lines)
	lines.append(
		f"  enroll check: {len(fixture_gallery.faces)} gallery photos each matched their owner",
	)
	add_summary_section(
		"Recognition (doorbell frame → who is at the door?)",
		lines,
		hint="  CLAHE on. match must clear min or the person counts as unknown.",
	)


@pytest.mark.parametrize("scenario_id", _scenario_ids())
def test_doorbell_fixture_scenario(
	scenario_id: str,
	face_app,
	fixture_gallery: Gallery,
) -> None:
	manifest = load_manifest()
	scenario = next(item for item in manifest["scenarios"] if item["id"] == scenario_id)

	frame_paths = scenario.get("frames", [])
	missing = missing_paths(frame_paths)
	if missing:
		pytest.skip(f"Missing frame fixtures for {scenario_id}: {', '.join(missing)}")

	expected_names = scenario.get("expected_names", [])
	gallery_names = {face.name for face in fixture_gallery.faces}
	if expected_names and not set(expected_names).issubset(gallery_names):
		pytest.skip(
			f"Enrollment missing for {scenario_id} "
			f"(need {expected_names}, have {sorted(gallery_names)})",
		)

	frames: list[np.ndarray] = []
	for frame_rel in frame_paths:
		frame = cv2.imread(str(resolve_fixture_path(frame_rel)))
		if frame is None:
			pytest.fail(f"Could not read frame fixture: {frame_rel}")
		frames.append(frame)

	threshold = float(scenario.get("min_match_score", 0.4))
	result = recognize_frames(
		frames,
		fixture_gallery,
		face_app=face_app,
		threshold=threshold,
		enhance_mode="clahe",
	)
	_scenario_lines.append(_format_scenario_result(scenario_id, result, threshold=threshold))

	assert result.names == scenario.get("expected_names", [])
	assert result.unknown == scenario.get("unknown", 0)

	if result.matches:
		best_det = max(match.det_score for match in result.matches)
		min_det = float(scenario.get("min_det_score", 0.0))
		assert best_det >= min_det

		best_match = max(match.score for match in result.matches)
		assert best_match >= threshold


def test_fixture_gallery_embeddings_match_threshold(face_app, fixture_gallery: Gallery) -> None:
	"""Sanity-check enroll photos match themselves above the default threshold."""
	manifest = load_manifest()
	threshold = float(manifest.get("recognition_threshold", 0.4))

	for enrolled in fixture_gallery.faces:
		photo_path = resolve_fixture_path(enrolled.photo)
		faces = detect_faces(face_app, cv2.imread(str(photo_path)), enhance_mode="clahe")
		assert faces, f"No face in enrollment photo {enrolled.photo}"
		best_face = max(faces, key=lambda face: face.det_score)
		match = _match_detected_face(best_face, fixture_gallery, threshold)
		assert match.name == enrolled.name
		assert match.score >= threshold
