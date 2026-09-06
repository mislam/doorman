"""Shared helpers for doorbell fixture integration tests (homelab Docker)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from enroll import embed_photo
from gallery import DEFAULT_MODEL, EnrolledFace, Gallery

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "doorbell"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
PRIVATE_MANIFEST_PATH = FIXTURE_ROOT / "manifest.private.json"

_LIST_KEYS = ("enroll", "scenarios", "preprocessing")

_summary_sections: list[tuple[str, str, list[str]]] = []


def add_summary_section(title: str, lines: list[str], *, hint: str = "") -> None:
	"""Queue a block for the end-of-run integration summary."""
	if lines:
		_summary_sections.append((title, hint, lines))


def flush_integration_summary() -> None:
	"""Print all queued summary sections (called from conftest at session end)."""
	if not _summary_sections:
		return
	say("\n" + "─" * 56)
	for title, hint, lines in _summary_sections:
		say(f"\n{title}")
		if hint:
			say(hint)
		for line in lines:
			say(line)
	say(
		"\n"
		"detect = face confidence (0–1)   "
		"match = identity score vs gallery; must be ≥ min to assign a name"
	)
	say("─" * 56)


def _merge_manifests(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
	merged = dict(base)
	for key in _LIST_KEYS:
		if key not in overlay:
			continue
		merged[key] = [*merged.get(key, []), *overlay[key]]
	for key, value in overlay.items():
		if key in _LIST_KEYS:
			continue
		merged[key] = value
	return merged


def load_manifest() -> dict[str, Any]:
	if not MANIFEST_PATH.is_file():
		raise FileNotFoundError(f"Missing fixture manifest: {MANIFEST_PATH}")
	manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
	if PRIVATE_MANIFEST_PATH.is_file():
		private = json.loads(PRIVATE_MANIFEST_PATH.read_text(encoding="utf-8"))
		manifest = _merge_manifests(manifest, private)
	return manifest


def say(message: str) -> None:
	"""Print integration progress (flush so docker runs feel responsive)."""
	print(message, flush=True)


def insightface_available() -> bool:
	try:
		import insightface  # noqa: F401
	except ImportError:
		return False
	return True


def resolve_fixture_path(relative_path: str) -> Path:
	return FIXTURE_ROOT / relative_path


def missing_paths(paths: list[str]) -> list[str]:
	return [path for path in paths if not resolve_fixture_path(path).is_file()]


def read_frame(relative_path: str) -> np.ndarray:
	frame = cv2.imread(str(resolve_fixture_path(relative_path)))
	if frame is None:
		raise ValueError(f"Could not read frame fixture: {relative_path}")
	return frame


def build_fixture_gallery(face_app: object) -> Gallery:
	"""Enroll manifest photos into an in-memory gallery (CLAHE path)."""
	manifest = load_manifest()
	enroll_entries = manifest.get("enroll", [])

	gallery = Gallery(model=DEFAULT_MODEL)
	skipped: list[str] = []
	for person in enroll_entries:
		name = person["name"]
		photo_paths = person.get("photos", [])
		if missing_paths(photo_paths):
			continue
		embedded = 0
		for photo_rel in photo_paths:
			photo_path = resolve_fixture_path(photo_rel)
			embedding = embed_photo(face_app, photo_path, enhance_mode="clahe")
			if embedding is None:
				skipped.append(Path(photo_rel).name)
				continue
			embedded += 1
			gallery.faces.append(
				EnrolledFace(name=name, embedding=embedding, photo=photo_rel),
			)
		if photo_paths and not missing_paths(photo_paths) and embedded == 0:
			raise RuntimeError(f"No faces detected in any enrollment photo for {name}")

	if not gallery.faces:
		raise RuntimeError(
			"No enrollment fixture photos on disk "
			"(add JPEGs under tests/fixtures/doorbell/public/)",
		)

	by_name: dict[str, list[str]] = {}
	for face in gallery.faces:
		by_name.setdefault(face.name, []).append(Path(face.photo).name)
	for name, photos in sorted(by_name.items()):
		say(f"Enrolled {name}: {', '.join(photos)}")
	if skipped:
		say(f"Skipped (no face): {', '.join(skipped)}")
	return gallery
