"""Tests for gallery scan and pickle I/O (no InsightFace)."""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pytest

from gallery import EnrolledFace, Gallery, iter_enrollment_photos, load_gallery, save_gallery


def test_iter_enrollment_photos_skips_hidden_and_non_images(tmp_path: Path) -> None:
	alice = tmp_path / "alice"
	alice.mkdir()
	(alice / "front.jpg").write_bytes(b"jpg")
	(alice / "side.png").write_bytes(b"png")
	(alice / "notes.txt").write_text("skip")
	(tmp_path / ".hidden").mkdir()
	(tmp_path / ".hidden" / "secret.jpg").write_bytes(b"jpg")

	bob = tmp_path / "bob"
	bob.mkdir()
	(bob / "one.jpeg").write_bytes(b"jpeg")

	assert list(iter_enrollment_photos(tmp_path)) == [
		("alice", alice / "front.jpg"),
		("alice", alice / "side.png"),
		("bob", bob / "one.jpeg"),
	]


def test_iter_enrollment_photos_empty_when_missing(tmp_path: Path) -> None:
	assert list(iter_enrollment_photos(tmp_path / "missing")) == []


def test_gallery_pickle_roundtrip(tmp_path: Path) -> None:
	gallery = Gallery(
		model="buffalo_l",
		faces=[
			EnrolledFace(
				name="alice",
				embedding=np.array([1.0, 0.0], dtype=np.float32),
				photo="alice/front.jpg",
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
