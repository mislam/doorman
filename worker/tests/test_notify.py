"""Tests for notify_ha."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from notify import notify_ha


def test_notify_ha_skips_when_url_empty() -> None:
	with patch("notify.requests.post") as mock_post:
		sent = notify_ha("", {"event": "doorbell"})

	assert sent is False
	mock_post.assert_not_called()


def test_notify_ha_posts_payload() -> None:
	mock_response = MagicMock()
	mock_response.status_code = 200
	mock_response.raise_for_status = MagicMock()

	with patch("notify.requests.post", return_value=mock_response) as mock_post:
		payload = {"event": "doorbell", "names": ["alice"], "unknown": 0}
		sent = notify_ha("https://ha.local/api/webhook/secret", payload)

	assert sent is True
	mock_post.assert_called_once_with(
		"https://ha.local/api/webhook/secret",
		json=payload,
		timeout=10.0,
	)


def test_notify_ha_returns_false_on_request_error() -> None:
	import requests

	with patch("notify.requests.post", side_effect=requests.ConnectionError("connection refused")):
		sent = notify_ha("https://ha.local/api/webhook/secret", {"event": "doorbell"})

	assert sent is False
