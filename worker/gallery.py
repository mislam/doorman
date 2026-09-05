"""Face gallery — enrollment photos on disk, cached embeddings in a pickle."""

from __future__ import annotations

import pickle
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	import numpy as np
	from numpy.typing import NDArray

GALLERY_VERSION = 1
DEFAULT_MODEL = "buffalo_l"
PHOTO_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})


@dataclass
class EnrolledFace:
	"""One embedding from a single enrollment photo."""

	name: str
	embedding: NDArray[np.float32]
	photo: str


@dataclass
class Gallery:
	"""Cached embeddings built from ``config/faces/{name}/`` photos."""

	version: int = GALLERY_VERSION
	model: str = DEFAULT_MODEL
	faces: list[EnrolledFace] = field(default_factory=list)


def iter_enrollment_photos(faces_dir: Path) -> Iterator[tuple[str, Path]]:
	"""Yield ``(person_name, photo_path)`` for each image under ``faces_dir/{name}/``."""
	if not faces_dir.is_dir():
		return

	for person_dir in sorted(faces_dir.iterdir()):
		if not person_dir.is_dir() or person_dir.name.startswith("."):
			continue

		name = person_dir.name
		for photo in sorted(person_dir.iterdir()):
			if photo.is_file() and photo.suffix.lower() in PHOTO_SUFFIXES:
				yield name, photo


def save_gallery(gallery: Gallery, path: Path) -> None:
	"""Write gallery to *path* (creates parent dirs)."""
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("wb") as handle:
		pickle.dump(gallery, handle, protocol=pickle.HIGHEST_PROTOCOL)


def load_gallery(path: Path) -> Gallery:
	"""Load gallery from *path*."""
	with path.open("rb") as handle:
		gallery = pickle.load(handle)

	if not isinstance(gallery, Gallery):
		msg = f"expected Gallery in {path}, got {type(gallery).__name__}"
		raise TypeError(msg)

	return gallery
