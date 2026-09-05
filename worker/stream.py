"""Video frame source — on-demand grab with reconnect backoff.

Supports RTSP, HTTP MJPEG, and other URLs OpenCV can open (e.g. ESP32 ``/stream``).
For doorbell events use :meth:`FrameSource.grab_event_frames` (open → read N → close).
:meth:`FrameSource.frames` is an infinite reconnect loop — tests and ad-hoc debugging only.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import cv2

if TYPE_CHECKING:
	import numpy as np
	from numpy.typing import NDArray

logger = logging.getLogger(__name__)

DEFAULT_BACKOFF_SEC: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 30.0)
_STREAM_CREDENTIALS = re.compile(r"//[^@/]+@")


def mask_stream_url(url: str) -> str:
	"""Hide credentials in stream URLs for log output."""
	return _STREAM_CREDENTIALS.sub("//***@", url)


@dataclass
class FrameSource:
	"""Grab the newest frame from a video stream; reconnect on failure."""

	url: str
	reconnect_backoff: tuple[float, ...] = DEFAULT_BACKOFF_SEC
	_cap: cv2.VideoCapture | None = field(default=None, init=False, repr=False)
	_backoff_index: int = field(default=0, init=False, repr=False)

	def open(self, *, max_attempts: int | None = None) -> None:
		"""Open the stream, retrying with backoff until connected.

		Args:
			max_attempts: Stop after this many tries and raise ``ConnectionError``.
				Default ``None`` retries forever (dev tools only).
		"""
		attempts = 0
		while max_attempts is None or attempts < max_attempts:
			self.close()
			cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
			cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
			if cap.isOpened():
				self._cap = cap
				self._backoff_index = 0
				logger.info("Stream connected (%s)", mask_stream_url(self.url))
				return
			cap.release()
			attempts += 1
			if max_attempts is not None and attempts >= max_attempts:
				break
			delay = self._next_backoff_delay()
			logger.warning(
				"Stream connect failed (%s), retrying in %.1fs",
				mask_stream_url(self.url),
				delay,
			)
			time.sleep(delay)

		raise ConnectionError(f"Failed to open stream ({mask_stream_url(self.url)})")

	def close(self) -> None:
		"""Release the underlying capture."""
		if self._cap is not None:
			self._cap.release()
			self._cap = None

	def read_latest(self) -> NDArray[np.uint8] | None:
		"""Return the newest decoded frame.

		Uses a single read with CAP_PROP_BUFFERSIZE=1 (set in open()). On a live
		stream, draining with repeated grab() would block forever waiting for the
		next frame — OpenCV drops older frames when the buffer is full instead.
		"""
		if self._cap is None or not self._cap.isOpened():
			self.open()

		cap = self._cap
		assert cap is not None

		ok, frame = cap.read()
		if not ok or frame is None:
			return None
		return frame

	def grab_event_frames(
		self,
		count: int,
		*,
		connect_attempts: int = 3,
	) -> list[NDArray[np.uint8]]:
		"""Grab *count* frames for one doorbell event; always closes the stream."""
		if count < 1:
			return []

		frames: list[NDArray[np.uint8]] = []
		try:
			self.open(max_attempts=connect_attempts)
			for _ in range(count):
				frame = self.read_latest()
				if frame is not None:
					frames.append(frame)
		finally:
			self.close()
		return frames

	def frames(self) -> Iterator[NDArray[np.uint8]]:
		"""Yield latest frames forever; reconnect with backoff after read failures.

		For production doorbell handling, use :meth:`grab_event_frames` instead.
		"""
		while True:
			frame = self.read_latest()
			if frame is None:
				logger.warning(
					"Stream read failed (%s), reconnecting in %.1fs",
					mask_stream_url(self.url),
					self._peek_backoff_delay(),
				)
				self.close()
				time.sleep(self._next_backoff_delay())
				continue

			self._backoff_index = 0
			yield frame

	def _peek_backoff_delay(self) -> float:
		if not self.reconnect_backoff:
			return 0.0
		return self.reconnect_backoff[min(self._backoff_index, len(self.reconnect_backoff) - 1)]

	def _next_backoff_delay(self) -> float:
		delay = self._peek_backoff_delay()
		if self._backoff_index < len(self.reconnect_backoff) - 1:
			self._backoff_index += 1
		return delay
