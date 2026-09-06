"""Tests for gallery scan and pickle I/O (no InsightFace)."""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pytest

from face_store import PersonRecord, load_store, photos_dir, register_photo, save_store
from gallery import EnrolledFace, Gallery, iter_enrollment_photos, load_gallery, save_gallery


def _person_with_photos(
	db_dir: Path,
	*,
	person_id: str,
	name: str,
	files: list[tuple[str, str]],
) -> None:
	store = load_store(db_dir)
	person = PersonRecord(id=person_id, name=name, photos=[])
	photo_root = photos_dir(db_dir)
	photo_root.mkdir(parents=True, exist_ok=True)
	for file_id, label in files:
		path = photo_root / f"{file_id}.jpg"
		path.write_bytes(b"jpg")
		register_photo(person, label, path)
	store.people.append(person)
	save_store(store, db_dir)


def test_iter_enrollment_photos_reads_manifest(tmp_path: Path) -> None:
	db_dir = tmp_path / "db"
	_person_with_photos(
		db_dir,
		person_id="alice-id",
		name="alice",
		files=[("front", "front"), ("side", "side")],
	)
	_person_with_photos(
		db_dir,
		person_id="bob-id",
		name="bob",
		files=[("one", "one")],
	)

	found = list(iter_enrollment_photos(db_dir))
	assert len(found) == 3
	assert {name for name, _ in found} == {"alice", "bob"}
	assert all(path.parent == photos_dir(db_dir) for _, path in found)


def test_iter_enrollment_photos_empty_when_missing(tmp_path: Path) -> None:
	assert list(iter_enrollment_photos(tmp_path / "missing")) == []


def test_gallery_pickle_roundtrip(tmp_path: Path) -> None:
	gallery = Gallery(
		model="buffalo_l",
		faces=[
			EnrolledFace(
				name="alice",
				embedding=np.array([1.0, 0.0], dtype=np.float32),
				photo="photos/front.jpg",
			),
		],
	)
	path = tmp_path / "gallery.pkl"

	save_gallery(gallery, path)
	loaded = load_gallery(path)

	assert loaded.version == gallery.version
	assert loaded.model == "buffalo_l"
	assert len(loaded.faces) == 1
	assert loaded.faces[0].name == "alice"
	np.testing.assert_array_equal(loaded.faces[0].embedding, gallery.faces[0].embedding)


def test_load_gallery_rejects_wrong_type(tmp_path: Path) -> None:
	path = tmp_path / "bad.pkl"

	with path.open("wb") as handle:
		pickle.dump({"not": "a gallery"}, handle)

	with pytest.raises(TypeError, match="expected Gallery"):
		load_gallery(path)
