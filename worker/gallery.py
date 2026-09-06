"""Face gallery — cached embeddings built from enrollment photos on disk."""

from __future__ import annotations

import pickle
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from face_store import iter_enrollment_photos as iter_stored_photos

if TYPE_CHECKING:
	import numpy as np
	from numpy.typing import NDArray

GALLERY_VERSION = 1
DEFAULT_MODEL = "buffalo_l"


@dataclass
class EnrolledFace:
	"""One embedding from a single enrollment photo."""

	name: str
	embedding: NDArray[np.float32]
	photo: str


@dataclass
class Gallery:
	"""Cached embeddings built from ``db/manifest.json`` + ``db/photos/``."""

	version: int = GALLERY_VERSION
	model: str = DEFAULT_MODEL
	faces: list[EnrolledFace] = field(default_factory=list)


def iter_enrollment_photos(db_dir: Path) -> Iterator[tuple[str, Path]]:
	"""Yield ``(display_name, photo_path)`` for each enrolled photo."""
	yield from iter_stored_photos(db_dir)


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
