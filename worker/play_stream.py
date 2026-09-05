"""Quick stream smoke test — grab frames and print stats.

Usage (from repo root):

    bun play-stream -- -v
    bun play-stream -- --frames 30 --save config/snapshot.jpg
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import cv2

from settings import Settings
from stream import FrameSource, mask_stream_url


def main() -> None:
	parser = argparse.ArgumentParser(description="Smoke-test FrameSource against STREAM_URL")
	parser.add_argument(
		"--frames",
		type=int,
		default=10,
		help="How many frames to grab before exiting (default: 10)",
	)
	parser.add_argument(
		"--save",
		type=str,
		default="",
		help="Optional path to write the last frame as JPEG (e.g. config/snapshot.jpg)",
	)
	parser.add_argument(
		"-v",
		"--verbose",
		action="store_true",
		help="Show stream.py reconnect/connect log lines",
	)
	args = parser.parse_args()

	if args.frames < 1:
		print("--frames must be >= 1", file=sys.stderr)
		raise SystemExit(2)

	logging.basicConfig(
		level=logging.INFO if args.verbose else logging.WARNING,
		format="%(levelname)s %(name)s: %(message)s",
	)

	settings = Settings()
	if not settings.stream_url:
		print("STREAM_URL is empty — set it in worker/.env", file=sys.stderr)
		raise SystemExit(1)

	print(f"Stream: {mask_stream_url(settings.stream_url)}")
	print(f"Grabbing {args.frames} frame(s)…\n")

	source = FrameSource(url=settings.stream_url)
	start = time.perf_counter()
	grabbed = source.grab_event_frames(args.frames)

	for i, frame in enumerate(grabbed, start=1):
		h, w = frame.shape[:2]
		elapsed = time.perf_counter() - start
		fps = i / elapsed if elapsed > 0 else 0.0
		print(f"  frame {i:3d}  {w}x{h}  {fps:5.1f} fps (avg)")

	last_frame = grabbed[-1] if grabbed else None

	if args.save and last_frame is not None:
		if cv2.imwrite(args.save, last_frame):
			print(f"\nSaved last frame → {args.save}")
		else:
			print(f"\nFailed to save {args.save}", file=sys.stderr)
			raise SystemExit(1)

	print("\nDone.")


if __name__ == "__main__":
	main()
