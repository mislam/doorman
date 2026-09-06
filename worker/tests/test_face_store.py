"""Tests for face_store enrollment layout."""

from __future__ import annotations

from pathlib import Path

import pytest

from face_store import (
	add_photo_from_file,
	find_or_create_person,
	find_person_by_name,
	iter_enrollment_photos,
	load_store,
	manifest_path,
	photos_dir,
	save_store,
	validate_display_name,
)


def test_validate_display_name_allows_spaces_and_punctuation() -> None:
	assert validate_display_name("  Reefat O'Brien  ") == "Reefat O'Brien"


def test_validate_display_name_rejects_empty() -> None:
	with pytest.raises(ValueError, match="required"):
		validate_display_name("   ")


def test_store_round_trip(tmp_path: Path) -> None:
	db_dir = tmp_path / "db"
	store = load_store(db_dir)
	person = find_or_create_person(store, "Mom & Dad")
	source = tmp_path / "crop.jpg"
	source.write_bytes(b"jpeg")
	add_photo_from_file(store, db_dir, person=person, label="front", source=source)
	save_store(store, db_dir)

	reloaded = load_store(db_dir)
	assert len(reloaded.people) == 1
	assert reloaded.people[0].name == "Mom & Dad"
	assert reloaded.people[0].photos[0].label == "front"
	assert (photos_dir(db_dir) / reloaded.people[0].photos[0].file).is_file()
	assert manifest_path(db_dir).is_file()


def test_find_person_by_name(tmp_path: Path) -> None:
	db_dir = tmp_path / "db"
	store = load_store(db_dir)
	find_or_create_person(store, "Alice")
	save_store(store, db_dir)

	reloaded = load_store(db_dir)
	assert find_person_by_name(reloaded, "Alice") is not None
	assert find_person_by_name(reloaded, "Bob") is None


def test_iter_enrollment_photos(tmp_path: Path) -> None:
	db_dir = tmp_path / "db"
	store = load_store(db_dir)
	person = find_or_create_person(store, "alice")
	source = tmp_path / "crop.jpg"
	source.write_bytes(b"jpeg")
	add_photo_from_file(store, db_dir, person=person, label="front", source=source)
	save_store(store, db_dir)

	found = list(iter_enrollment_photos(db_dir))
	assert found == [("alice", photos_dir(db_dir) / person.photos[0].file)]
