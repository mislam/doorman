"""Enrollment storage — display names in manifest.json, photos as UUID files."""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST_NAME = "manifest.json"
PHOTOS_DIR_NAME = "photos"
MAX_NAME_LEN = 64
STORE_VERSION = 1


@dataclass
class PhotoRecord:
	id: str
	label: str
	file: str


@dataclass
class PersonRecord:
	id: str
	name: str
	photos: list[PhotoRecord] = field(default_factory=list)


@dataclass
class FaceStore:
	version: int = STORE_VERSION
	people: list[PersonRecord] = field(default_factory=list)


def photos_dir(db_dir: Path) -> Path:
	return db_dir / PHOTOS_DIR_NAME


def manifest_path(db_dir: Path) -> Path:
	return db_dir / MANIFEST_NAME


def validate_display_name(name: str) -> str:
	"""Return a trimmed display name (any printable text; not used in paths)."""
	clean = name.strip()
	if not clean:
		msg = "Name is required"
		raise ValueError(msg)
	if len(clean) > MAX_NAME_LEN:
		msg = f"Name must be at most {MAX_NAME_LEN} characters"
		raise ValueError(msg)
	if any(char in clean for char in "\x00\n\r"):
		msg = "Name contains invalid characters"
		raise ValueError(msg)
	return clean


def _photo_to_dict(photo: PhotoRecord) -> dict[str, str]:
	return {"id": photo.id, "label": photo.label, "file": photo.file}


def _person_to_dict(person: PersonRecord) -> dict[str, object]:
	return {
		"id": person.id,
		"name": person.name,
		"photos": [_photo_to_dict(photo) for photo in person.photos],
	}


def _photo_from_dict(data: dict[str, object]) -> PhotoRecord:
	return PhotoRecord(
		id=str(data["id"]),
		label=str(data["label"]),
		file=str(data["file"]),
	)


def _person_from_dict(data: dict[str, object]) -> PersonRecord:
	photos_raw = data.get("photos", [])
	photos = [_photo_from_dict(photo) for photo in photos_raw if isinstance(photo, dict)]
	return PersonRecord(id=str(data["id"]), name=str(data["name"]), photos=photos)


def load_store(db_dir: Path) -> FaceStore:
	"""Load manifest.json (empty store when missing)."""
	db_dir.mkdir(parents=True, exist_ok=True)
	photos_dir(db_dir).mkdir(parents=True, exist_ok=True)

	path = manifest_path(db_dir)
	if not path.is_file():
		return FaceStore()

	with path.open(encoding="utf-8") as handle:
		raw = json.load(handle)
	people_raw = raw.get("people", []) if isinstance(raw, dict) else []
	people = [_person_from_dict(person) for person in people_raw if isinstance(person, dict)]
	return FaceStore(version=int(raw.get("version", STORE_VERSION)), people=people)


def save_store(store: FaceStore, db_dir: Path) -> None:
	db_dir.mkdir(parents=True, exist_ok=True)
	payload = {
		"version": store.version,
		"people": [_person_to_dict(person) for person in store.people],
	}
	with manifest_path(db_dir).open("w", encoding="utf-8") as handle:
		json.dump(payload, handle, indent=2)
		handle.write("\n")


def find_person_by_id(store: FaceStore, person_id: str) -> PersonRecord | None:
	for person in store.people:
		if person.id == person_id:
			return person
	return None


def find_person_by_name(store: FaceStore, name: str) -> PersonRecord | None:
	display_name = validate_display_name(name)
	for person in store.people:
		if person.name == display_name:
			return person
	return None


def find_or_create_person(store: FaceStore, name: str) -> PersonRecord:
	existing = find_person_by_name(store, name)
	if existing is not None:
		return existing

	person = PersonRecord(id=uuid.uuid4().hex, name=validate_display_name(name))
	store.people.append(person)
	return person


def new_photo_path(db_dir: Path) -> tuple[str, Path]:
	photo_id = uuid.uuid4().hex[:12]
	filename = f"{photo_id}.jpg"
	return photo_id, photos_dir(db_dir) / filename


def register_photo(person: PersonRecord, label: str, photo_path: Path) -> PhotoRecord:
	record = PhotoRecord(id=photo_path.stem, label=label, file=photo_path.name)
	person.photos.append(record)
	return record


def add_photo_from_file(
	store: FaceStore,
	db_dir: Path,
	*,
	person: PersonRecord,
	label: str,
	source: Path,
) -> PhotoRecord:
	_photo_id, dest = new_photo_path(db_dir)
	shutil.copy2(source, dest)
	return register_photo(person, label, dest)


def delete_person(store: FaceStore, db_dir: Path, person_id: str) -> PersonRecord:
	person = find_person_by_id(store, person_id)
	if person is None:
		msg = "Person not found"
		raise KeyError(msg)

	photo_root = photos_dir(db_dir)
	for photo in person.photos:
		(photo_root / photo.file).unlink(missing_ok=True)

	store.people = [entry for entry in store.people if entry.id != person_id]
	return person


def iter_enrollment_photos(db_dir: Path) -> Iterator[tuple[str, Path]]:
	"""Yield ``(display_name, photo_path)`` for gallery build."""
	store = load_store(db_dir)
	photo_root = photos_dir(db_dir)
	for person in store.people:
		for photo in person.photos:
			path = photo_root / photo.file
			if path.is_file():
				yield person.name, path
