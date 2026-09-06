#!/usr/bin/env python3
"""Convert doorbell fixture PNGs to JPEG (quality 92, optional downscale)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

DOORBELL_ROOT = Path(__file__).resolve().parents[1] / "worker" / "tests" / "fixtures" / "doorbell"
JPEG_QUALITY = 92
MAX_ENROLL_LONG_EDGE = 1280
MAX_FRAME_LONG_EDGE = 1920


def _downscale(image, max_long_edge: int):
	height, width = image.shape[:2]
	long_edge = max(height, width)
	if long_edge <= max_long_edge:
		return image
	scale = max_long_edge / long_edge
	new_size = (int(width * scale), int(height * scale))
	return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)


def _convert_file(path: Path, *, max_long_edge: int, remove_source: bool) -> Path:
	image = cv2.imread(str(path))
	if image is None:
		raise RuntimeError(f"Could not read image: {path}")

	image = _downscale(image, max_long_edge)
	out_path = path.with_suffix(".jpg")
	if not cv2.imwrite(str(out_path), image, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]):
		raise RuntimeError(f"Could not write image: {out_path}")

	if remove_source and path.suffix.lower() != ".jpg" and path.resolve() != out_path.resolve():
		path.unlink()

	return out_path


def _iter_sources(directory: Path) -> list[Path]:
	if not directory.is_dir():
		return []
	return sorted(
		path
		for path in directory.iterdir()
		if path.is_file()
		and path.suffix.lower() in {".png", ".jpeg", ".jpg"}
		and path.name != ".gitkeep"
	)


def _conversion_dirs() -> list[tuple[Path, int]]:
	prefixes = ("public", "private")
	dirs: list[tuple[Path, int]] = []
	for prefix in prefixes:
		root = DOORBELL_ROOT / prefix
		dirs.append((root / "enroll", MAX_ENROLL_LONG_EDGE))
		dirs.append((root / "frames", MAX_FRAME_LONG_EDGE))
	return dirs


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument(
		"--keep-source",
		action="store_true",
		help="Keep original PNG/JPEG after writing .jpg",
	)
	args = parser.parse_args()

	converted: list[Path] = []
	for directory, max_edge in _conversion_dirs():
		for path in _iter_sources(directory):
			if path.suffix.lower() == ".jpg":
				continue
			converted.append(
				_convert_file(path, max_long_edge=max_edge, remove_source=not args.keep_source),
			)

	for path in converted:
		size_kb = path.stat().st_size // 1024
		print(f"wrote {path.relative_to(DOORBELL_ROOT)} ({size_kb} KB)")

	if not converted:
		print("No PNG/JPEG sources to convert.")
	return 0


if __name__ == "__main__":
	sys.exit(main())
