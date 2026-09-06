"""Tests for enroll.build_gallery (InsightFace mocked)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from enroll import build_gallery
from face_store import PersonRecord, load_store, photos_dir, register_photo, save_store
from gallery import load_gallery

_FAKE_IMAGE = np.zeros((64, 64, 3), dtype=np.uint8)


def _person_with_photos(
	db_dir: Path,
	*,
	person_id: str,
	name: str,
	files: list[tuple[str, bytes]],
) -> None:
	store = load_store(db_dir)
	person = PersonRecord(id=person_id, name=name, photos=[])
	photo_root = photos_dir(db_dir)
	photo_root.mkdir(parents=True, exist_ok=True)
	for file_id, content in files:
		path = photo_root / f"{file_id}.jpg"
		path.write_bytes(content)
		register_photo(person, file_id, path)
	store.people.append(person)
	save_store(store, db_dir)


def test_build_gallery_embeds_each_photo(tmp_path: Path) -> None:
	db_dir = tmp_path / "db"
	_person_with_photos(
		db_dir,
		person_id="alice-id",
		name="alice",
		files=[("a", b"a"), ("b", b"b")],
	)

	embedding = np.array([1.0, 0.0, 0.0], dtype=np.float32)
	mock_app = MagicMock()
	mock_app.get.return_value = [SimpleNamespace(det_score=0.99, normed_embedding=embedding)]

	with patch("enroll.cv2.imread", return_value=_FAKE_IMAGE):
		gallery = build_gallery(db_dir, face_app=mock_app, enhance_mode="off")

	assert len(gallery.faces) == 2
	assert {face.name for face in gallery.faces} == {"alice"}
	assert mock_app.get.call_count == 2


def test_build_gallery_skips_photos_without_faces(tmp_path: Path) -> None:
	db_dir = tmp_path / "db"
	_person_with_photos(
		db_dir,
		person_id="bob-id",
		name="bob",
		files=[("empty", b"x"), ("ok", b"y")],
	)

	embedding = np.array([0.0, 1.0], dtype=np.float32)
	mock_app = MagicMock()
	mock_app.get.side_effect = [[], [SimpleNamespace(det_score=0.5, normed_embedding=embedding)]]

	with patch("enroll.cv2.imread", return_value=_FAKE_IMAGE):
		gallery = build_gallery(db_dir, face_app=mock_app, enhance_mode="off")

	assert len(gallery.faces) == 1
	assert gallery.faces[0].photo == "photos/ok.jpg"


def test_build_gallery_save_and_load(tmp_path: Path) -> None:
	db_dir = tmp_path / "db"
	_person_with_photos(
		db_dir,
		person_id="carol-id",
		name="carol",
		files=[("one", b"1")],
	)

	embedding = np.array([0.5, 0.5], dtype=np.float32)
	mock_app = MagicMock()
	mock_app.get.return_value = [SimpleNamespace(det_score=0.9, normed_embedding=embedding)]

	with patch("enroll.cv2.imread", return_value=_FAKE_IMAGE):
		gallery = build_gallery(db_dir, face_app=mock_app, enhance_mode="off")
	path = db_dir / "gallery.pkl"
	from gallery import save_gallery

	save_gallery(gallery, path)
	loaded = load_gallery(path)

	assert len(loaded.faces) == 1
	assert loaded.faces[0].name == "carol"
