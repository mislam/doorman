"""Video frame source — on-demand grab with reconnect backoff.

Supports RTSP, HTTP MJPEG, and other URLs OpenCV can open (e.g. ESP32 ``/stream``).
For doorbell events use :meth:`FrameSource.grab_event_frames` (open → read N → close).
:meth:`FrameSource.frames` is an infinite reconnect loop — tests and ad-hoc debugging only.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import quote, urlparse, urlunparse

import cv2

if TYPE_CHECKING:
	import numpy as np
	from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# TCP RTSP is usually faster to connect on doorbell cams than UDP.
os.environ.setdefault(
	"OPENCV_FFMPEG_CAPTURE_OPTIONS",
	"rtsp_transport;tcp|stimeout;10000000",
)

DEFAULT_BACKOFF_SEC: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 30.0)
DEFAULT_WARMUP_FRAMES = 8
RTSP_WARMUP_FRAMES = 30
PREVIEW_RTSP_PRIME_FRAMES = 3
PREVIEW_HTTP_PRIME_FRAMES = 1
_STREAM_CREDENTIALS = re.compile(r"//[^@/]+@")


def warmup_frames_for_url(url: str) -> int:
	"""RTSP doorbell cams often need more priming reads than HTTP MJPEG."""
	if url.lower().startswith("rtsp://"):
		return RTSP_WARMUP_FRAMES
	return DEFAULT_WARMUP_FRAMES


def preview_prime_frames_for_url(url: str) -> int:
	"""Fewer frames for enroll UI — fast first paint, not doorbell-quality grab."""
	if url.lower().startswith("rtsp://"):
		return PREVIEW_RTSP_PRIME_FRAMES
	return PREVIEW_HTTP_PRIME_FRAMES


def mask_stream_url(url: str) -> str:
	"""Hide credentials in stream URLs for log output."""
	return _STREAM_CREDENTIALS.sub("//***@", url)


def build_stream_url(url: str, username: str = "", password: str = "") -> str:
	"""Return *url* with credentials injected; password is URL-encoded at runtime only."""
	if not url:
		return url

	parsed = urlparse(url)
	if not parsed.hostname:
		return url

	host = parsed.hostname
	if parsed.port is not None:
		host = f"{host}:{parsed.port}"

	if username:
		userinfo = f"{quote(username, safe='')}:{quote(password, safe='')}"
		netloc = f"{userinfo}@{host}"
	elif parsed.username is not None:
		return url
	else:
		netloc = host

	return urlunparse(
		(parsed.scheme, netloc, parsed.path or "", parsed.params, parsed.query, parsed.fragment)
	)


@dataclass
class FrameSource:
	"""Grab the newest frame from a video stream; reconnect on failure."""

	url: str
	reconnect_backoff: tuple[float, ...] = DEFAULT_BACKOFF_SEC
	_cap: cv2.VideoCapture | None = field(default=None, init=False, repr=False)
	_backoff_index: int = field(default=0, init=False, repr=False)

	def open(
		self,
		*,
		max_attempts: int | None = None,
		warmup_frames: int = DEFAULT_WARMUP_FRAMES,
	) -> None:
		"""Open the stream, retrying with backoff until connected.

		Args:
			max_attempts: Stop after this many tries and raise ``ConnectionError``.
				Default ``None`` retries forever (dev tools only).
			warmup_frames: Read up to this many frames after connect to prime RTSP decode.
		"""
		attempts = 0
		while max_attempts is None or attempts < max_attempts:
			self.close()
			cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
			cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
			if cap.isOpened():
				self._cap = cap
				self._backoff_index = 0
				if self._warmup_capture(warmup_frames):
					logger.info("Stream connected (%s)", mask_stream_url(self.url))
					return
				self.close()
			else:
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

	def _warmup_capture(self, warmup_frames: int) -> bool:
		"""Read frames until one decodes or warmup attempts are exhausted."""
		cap = self._cap
		if cap is None:
			return False

		for _ in range(max(warmup_frames, 1)):
			ok, frame = cap.read()
			if ok and frame is not None:
				return True
			time.sleep(0.05)
		return False

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


class PreviewStreamHub:
	"""Background RTSP reader — one connection shared by enroll preview and capture."""

	def __init__(self) -> None:
		self._lock = threading.Lock()
		self._latest: NDArray[np.uint8] | None = None
		self._thread: threading.Thread | None = None
		self._stop = threading.Event()
		self._url: str | None = None

	def start(self, url: str) -> None:
		"""Start (or keep) the reader for *url*."""
		if not url:
			return
		if self._thread and self._thread.is_alive() and self._url == url:
			return
		self.stop()
		self._url = url
		self._stop.clear()
		self._thread = threading.Thread(target=self._run, name="preview-stream", daemon=True)
		self._thread.start()

	def stop(self) -> None:
		"""Stop the background reader."""
		self._stop.set()
		thread = self._thread
		if thread and thread.is_alive():
			thread.join(timeout=5)
		self._thread = None
		self._url = None
		with self._lock:
			self._latest = None

	def latest_frame(self) -> NDArray[np.uint8] | None:
		"""Return a copy of the most recent frame, or ``None`` if not ready yet."""
		with self._lock:
			if self._latest is None:
				return None
			return self._latest.copy()

	def wait_for_frame(self, timeout_sec: float = 30.0) -> NDArray[np.uint8] | None:
		"""Block until a frame is available or *timeout_sec* elapses."""
		deadline = time.monotonic() + timeout_sec
		while time.monotonic() < deadline:
			frame = self.latest_frame()
			if frame is not None:
				return frame
			time.sleep(0.05)
		return None

	def _run(self) -> None:
		url = self._url
		if not url:
			return

		source = FrameSource(url=url, reconnect_backoff=(0.5, 1.0, 2.0, 5.0))
		prime_reads = preview_prime_frames_for_url(url)
		while not self._stop.is_set():
			try:
				# Connect quickly; prime loop publishes frames to _latest as they arrive.
				source.open(max_attempts=3, warmup_frames=1)
			except ConnectionError:
				time.sleep(1.0)
				continue

			for _ in range(prime_reads):
				if self._stop.is_set():
					break
				frame = source.read_latest()
				if frame is not None:
					with self._lock:
						self._latest = frame

			while not self._stop.is_set():
				frame = source.read_latest()
				if frame is None:
					break
				with self._lock:
					self._latest = frame
			source.close()

		source.close()


preview_hub = PreviewStreamHub()
