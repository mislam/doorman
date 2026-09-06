"""Build the face gallery from enrollment photos (homelab GPU / InsightFace).

Called by the enroll web UI (/enroll/api/rebuild) and optionally from Docker::

    docker compose exec worker python enroll.py -v
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np

from gallery import DEFAULT_MODEL, EnrolledFace, Gallery, iter_enrollment_photos, save_gallery
from settings import Settings
from vision_runtime import create_face_app, log_inference_providers

if TYPE_CHECKING:
	from numpy.typing import NDArray

logger = logging.getLogger(__name__)


def embed_photo(app: Any, photo_path: Path) -> NDArray[np.float32] | None:
	"""Return a normalized embedding for the best face in *photo_path*, or ``None``."""
	image = cv2.imread(str(photo_path))
	if image is None:
		logger.warning("Could not read image: %s", photo_path)
		return None

	faces = app.get(image)
	if not faces:
		logger.warning("No face detected in %s", photo_path)
		return None

	best = max(faces, key=lambda face: face.det_score)
	return np.asarray(best.normed_embedding, dtype=np.float32)


def build_gallery(
	db_dir: Path,
	*,
	model: str = DEFAULT_MODEL,
	face_app: Any | None = None,
) -> Gallery:
	"""Scan *db_dir* manifest + photos and embed each enrollment photo."""
	app = face_app if face_app is not None else create_face_app(model)
	gallery = Gallery(model=model)
	db_root = db_dir.resolve()

	for name, photo in iter_enrollment_photos(db_dir):
		embedding = embed_photo(app, photo)
		if embedding is None:
			continue

		try:
			photo_ref = str(photo.resolve().relative_to(db_root))
		except ValueError:
			photo_ref = str(photo)

		gallery.faces.append(EnrolledFace(name=name, embedding=embedding, photo=photo_ref))
		logger.info("Enrolled %s from %s", name, photo_ref)

	return gallery


def main() -> None:
	parser = argparse.ArgumentParser(description="Build db/gallery.pkl from enrollment photos")
	parser.add_argument(
		"-v",
		"--verbose",
		action="store_true",
		help="Show per-photo enrollment log lines",
	)
	args = parser.parse_args()

	logging.basicConfig(
		level=logging.INFO if args.verbose else logging.WARNING,
		format="%(levelname)s %(name)s: %(message)s",
	)

	log_inference_providers()
	settings = Settings()
	db_dir = settings.db_path()
	gallery_path = settings.gallery_path()

	if not db_dir.is_dir():
		print(f"Database directory not found: {db_dir}", file=sys.stderr)
		print("Enroll faces via the web UI first.", file=sys.stderr)
		raise SystemExit(1)

	gallery = build_gallery(db_dir)
	if not gallery.faces:
		print(f"No faces enrolled in {db_dir}", file=sys.stderr)
		raise SystemExit(1)

	save_gallery(gallery, gallery_path)
	people = sorted({face.name for face in gallery.faces})
	print(f"Wrote {len(gallery.faces)} embedding(s) for {len(people)} person(s) → {gallery_path}")


if __name__ == "__main__":
	main()
