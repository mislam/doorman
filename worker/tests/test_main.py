"""Tests for main.create_app (/recognize endpoint)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from main import create_app
from recognize import RecognitionResult
from settings import Settings


def test_recognize_endpoint_returns_payload() -> None:
	settings = Settings(_env_file=None, stream_url="rtsp://cam/stream")
	app = create_app(settings)

	with (
		patch("main.warmup_face_app"),
		patch("main.preview_hub"),
		patch("main.recognize_from_settings") as mock_recognize,
	):
		mock_recognize.return_value = RecognitionResult(names=["alice"], unknown=0, matches=[])
		client = TestClient(app)
		response = client.post("/recognize")

	assert response.status_code == 200
	data = response.json()
	assert data["event"] == "doorbell"
	assert data["names"] == ["alice"]
	assert data["unknown"] == 0
	assert "ts" in data


def test_recognize_endpoint_503_when_gallery_missing() -> None:
	settings = Settings(_env_file=None, stream_url="rtsp://cam/stream")
	app = create_app(settings)

	with (
		patch("main.warmup_face_app"),
		patch("main.preview_hub"),
		patch("main.recognize_from_settings", side_effect=FileNotFoundError("no gallery")),
	):
		client = TestClient(app)
		response = client.post("/recognize")

	assert response.status_code == 503
	assert response.json()["detail"] == "no gallery"


def test_health_endpoint() -> None:
	settings = Settings(_env_file=None)
	app = create_app(settings)

	with patch("main.warmup_face_app"), patch("main.preview_hub"):
		client = TestClient(app)
		response = client.get("/health")

	assert response.status_code == 200
	assert response.json() == {"status": "ok"}
