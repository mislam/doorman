"""Tests for settings capture_stream_url."""

from __future__ import annotations

from settings import Settings


def test_capture_stream_url_uses_separate_credentials() -> None:
	settings = Settings(
		_env_file=None,
		stream_url="rtsp://doorbell.test:554/h264Preview_01_sub",
		stream_user="camuser",
		stream_password="p@ss:w0rd!",
	)

	url = settings.capture_stream_url()

	assert "doorbell.test:554" in url
	assert "p@ss:w0rd!" not in url
	assert url.startswith("rtsp://camuser:")


def test_capture_stream_url_plain_http() -> None:
	settings = Settings(
		_env_file=None,
		stream_url="http://mjpeg.test:81/stream",
	)

	assert settings.capture_stream_url() == "http://mjpeg.test:81/stream"
