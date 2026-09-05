"""Tests for stream.FrameSource (cv2 mocked — no RTSP or vision deps on Mac)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from stream import FrameSource, mask_rtsp_url


def test_mask_rtsp_url_hides_credentials() -> None:
	url = "rtsp://admin:secret@doorbell.test:554/h264Preview_01_sub"
	assert mask_rtsp_url(url) == "rtsp://***@doorbell.test:554/h264Preview_01_sub"


def test_read_latest_returns_frame_on_success() -> None:
	frame = np.zeros((480, 640, 3), dtype=np.uint8)
	cap = MagicMock()
	cap.isOpened.return_value = True
	cap.read.return_value = (True, frame)

	source = FrameSource(url="rtsp://cam/stream")
	source._cap = cap

	result = source.read_latest()

	cap.read.assert_called_once()
	assert result is frame


def test_read_latest_returns_none_when_read_fails() -> None:
	cap = MagicMock()
	cap.isOpened.return_value = True
	cap.read.return_value = (False, None)

	source = FrameSource(url="rtsp://cam/stream")
	source._cap = cap

	assert source.read_latest() is None


@patch("stream.time.sleep")
@patch("stream.cv2.VideoCapture")
def test_open_retries_until_capture_opens(
	mock_capture_cls: MagicMock,
	mock_sleep: MagicMock,
) -> None:
	failing = MagicMock()
	failing.isOpened.return_value = False
	working = MagicMock()
	working.isOpened.return_value = True
	mock_capture_cls.side_effect = [failing, working]

	source = FrameSource(url="rtsp://cam/stream", reconnect_backoff=(0.5, 1.0))
	source.open()

	assert mock_capture_cls.call_count == 2
	working.set.assert_called_once()
	mock_sleep.assert_called_once_with(0.5)
	assert source._cap is working


@patch("stream.time.sleep")
@patch("stream.cv2.VideoCapture")
def test_frames_backoffs_on_read_failure(
	mock_capture_cls: MagicMock,
	mock_sleep: MagicMock,
) -> None:
	frame = np.ones((2, 2, 3), dtype=np.uint8)
	cap = MagicMock()
	cap.isOpened.return_value = True
	mock_capture_cls.return_value = cap
	cap.read.side_effect = [(True, frame), (False, None), (True, frame)]

	source = FrameSource(url="rtsp://cam/stream", reconnect_backoff=(0.1,))
	source.open()

	iterator = source.frames()
	first = next(iterator)
	second = next(iterator)

	assert first is frame
	assert second is frame
	mock_sleep.assert_called_once_with(0.1)


def test_backoff_caps_at_last_delay() -> None:
	source = FrameSource(url="rtsp://cam/stream", reconnect_backoff=(1.0, 2.0, 5.0))
	assert source._next_backoff_delay() == 1.0
	assert source._next_backoff_delay() == 2.0
	assert source._next_backoff_delay() == 5.0
	assert source._next_backoff_delay() == 5.0


@patch("stream.time.sleep")
@patch("stream.cv2.VideoCapture")
def test_open_raises_after_max_attempts(mock_capture_cls: MagicMock, mock_sleep: MagicMock) -> None:
	failing = MagicMock()
	failing.isOpened.return_value = False
	mock_capture_cls.return_value = failing

	source = FrameSource(url="rtsp://cam/stream", reconnect_backoff=(0.1,))
	try:
		source.open(max_attempts=2)
		raise AssertionError("expected ConnectionError")
	except ConnectionError:
		pass

	assert mock_capture_cls.call_count == 2
	assert mock_sleep.call_count == 1


@patch("stream.cv2.VideoCapture")
def test_grab_event_frames_reads_and_closes(mock_capture_cls: MagicMock) -> None:
	frame = np.zeros((2, 2, 3), dtype=np.uint8)
	cap = MagicMock()
	cap.isOpened.return_value = True
	mock_capture_cls.return_value = cap
	cap.read.return_value = (True, frame)

	source = FrameSource(url="rtsp://cam/stream")
	result = source.grab_event_frames(3, connect_attempts=1)

	assert len(result) == 3
	assert source._cap is None
	cap.release.assert_called()
