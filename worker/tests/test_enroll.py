"""Tests for enroll.build_gallery (InsightFace mocked)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from enroll import build_gallery
from gallery import load_gallery

_FAKE_IMAGE = np.zeros((64, 64, 3), dtype=np.uint8)


def test_build_gallery_embeds_each_photo(tmp_path: Path) -> None:
	alice = tmp_path / "alice"
	alice.mkdir()
	(alice / "a.jpg").write_bytes(b"a")
	(alice / "b.jpg").write_bytes(b"b")

	embedding = np.array([1.0, 0.0, 0.0], dtype=np.float32)
	mock_app = MagicMock()
	mock_app.get.return_value = [SimpleNamespace(det_score=0.99, normed_embedding=embedding)]

	with patch("enroll.cv2.imread", return_value=_FAKE_IMAGE):
		gallery = build_gallery(tmp_path, face_app=mock_app)

	assert len(gallery.faces) == 2
	assert {face.name for face in gallery.faces} == {"alice"}
	assert mock_app.get.call_count == 2


def test_build_gallery_skips_photos_without_faces(tmp_path: Path) -> None:
	person = tmp_path / "bob"
	person.mkdir()
	(person / "empty.jpg").write_bytes(b"x")
	(person / "ok.jpg").write_bytes(b"y")

	embedding = np.array([0.0, 1.0], dtype=np.float32)
	mock_app = MagicMock()
	mock_app.get.side_effect = [[], [SimpleNamespace(det_score=0.5, normed_embedding=embedding)]]

	with patch("enroll.cv2.imread", return_value=_FAKE_IMAGE):
		gallery = build_gallery(tmp_path, face_app=mock_app)

	assert len(gallery.faces) == 1
	assert gallery.faces[0].photo == "bob/ok.jpg"


def test_build_gallery_save_and_load(tmp_path: Path) -> None:
	person = tmp_path / "carol"
	person.mkdir()
	(person / "one.jpg").write_bytes(b"1")

	embedding = np.array([0.5, 0.5], dtype=np.float32)
	mock_app = MagicMock()
	mock_app.get.return_value = [SimpleNamespace(det_score=0.9, normed_embedding=embedding)]

	with patch("enroll.cv2.imread", return_value=_FAKE_IMAGE):
		gallery = build_gallery(tmp_path, face_app=mock_app)
	path = tmp_path / "gallery.pkl"
	from gallery import save_gallery

	save_gallery(gallery, path)
	loaded = load_gallery(path)

	assert len(loaded.faces) == 1
	assert loaded.faces[0].name == "carol"
