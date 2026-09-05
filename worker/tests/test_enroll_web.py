"""Tests for enroll_web API routes."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from fastapi.testclient import TestClient

from main import create_app
from settings import Settings


def _settings(tmp_path: Path, **overrides: object) -> Settings:
	faces = tmp_path / "faces"
	faces.mkdir()
	return Settings(
		_env_file=None,
		faces_dir=str(faces),
		gallery_path=str(tmp_path / "gallery.pkl"),
		enroll_secret="test-secret",
		stream_url="rtsp://cam/stream",
		**overrides,
	)


def _client(settings: Settings) -> TestClient:
	app = create_app(settings)
	return TestClient(app)


def _auth_headers() -> dict[str, str]:
	return {"Authorization": "Bearer test-secret"}


def test_list_people_empty(tmp_path: Path) -> None:
	client = _client(_settings(tmp_path))
	response = client.get("/enroll/api/people", headers=_auth_headers())
	assert response.status_code == 200
	assert response.json() == []


def test_enroll_requires_token(tmp_path: Path) -> None:
	client = _client(_settings(tmp_path))
	response = client.get("/enroll/api/people")
	assert response.status_code == 401


def test_capture_photo_saves_face(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	image = np.zeros((80, 80, 3), dtype=np.uint8)
	_, encoded = __import__("cv2").imencode(".jpg", image)

	mock_app = MagicMock()
	mock_app.get.return_value = [SimpleNamespace(det_score=0.99)]

	with (
		patch("main.warmup_face_app"),
		patch("enroll_web.get_face_app", return_value=mock_app),
		patch("enroll_web._decode_image", return_value=image),
	):
		response = client.post(
			"/enroll/api/capture",
			headers=_auth_headers(),
			data={"name": "alice", "label": "front"},
			files={"image": ("front.jpg", BytesIO(encoded.tobytes()), "image/jpeg")},
		)

	assert response.status_code == 200
	data = response.json()
	assert data["ok"] is True
	assert data["filename"] == "front.jpg"
	assert (tmp_path / "faces" / "alice" / "front.jpg").is_file()


def test_capture_rejects_no_face(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	image = np.zeros((80, 80, 3), dtype=np.uint8)
	_, encoded = __import__("cv2").imencode(".jpg", image)

	mock_app = MagicMock()
	mock_app.get.return_value = []

	with (
		patch("main.warmup_face_app"),
		patch("enroll_web.get_face_app", return_value=mock_app),
		patch("enroll_web._decode_image", return_value=image),
	):
		response = client.post(
			"/enroll/api/capture",
			headers=_auth_headers(),
			data={"name": "alice", "label": "front"},
			files={"image": ("front.jpg", BytesIO(encoded.tobytes()), "image/jpeg")},
		)

	assert response.status_code == 200
	assert response.json()["ok"] is False


def test_rebuild_gallery(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	alice = tmp_path / "faces" / "alice"
	alice.mkdir()
	(alice / "one.jpg").write_bytes(b"x")

	embedding = np.array([1.0, 0.0], dtype=np.float32)
	mock_app = MagicMock()
	mock_app.get.return_value = [SimpleNamespace(det_score=0.9, normed_embedding=embedding)]
	fake_image = np.zeros((64, 64, 3), dtype=np.uint8)
	client = _client(settings)

	with (
		patch("main.warmup_face_app"),
		patch("enroll.create_face_app", return_value=mock_app),
		patch("enroll.cv2.imread", return_value=fake_image),
	):
		response = client.post("/enroll/api/rebuild", headers=_auth_headers())

	assert response.status_code == 200
	data = response.json()
	assert data["embeddings"] == 1
	assert data["people"] == 1
	assert (tmp_path / "gallery.pkl").is_file()


def test_delete_person(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	alice = tmp_path / "faces" / "alice"
	alice.mkdir()
	(alice / "one.jpg").write_bytes(b"x")
	client = _client(settings)

	with patch("main.warmup_face_app"):
		response = client.delete("/enroll/api/people/alice", headers=_auth_headers())

	assert response.status_code == 200
	assert not alice.exists()


def test_snapshot_returns_jpeg(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	frame = np.zeros((80, 80, 3), dtype=np.uint8)

	with (
		patch("main.warmup_face_app"),
		patch("enroll_web.preview_hub.latest_frame", return_value=frame),
	):
		response = client.get("/enroll/api/snapshot.jpg", headers=_auth_headers())

	assert response.status_code == 200
	assert response.headers["content-type"] == "image/jpeg"
	assert len(response.content) > 0


def test_snapshot_503_when_no_frame(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)

	with (
		patch("main.warmup_face_app"),
		patch("enroll_web.preview_hub.latest_frame", return_value=None),
		patch("enroll_web.preview_hub.wait_for_frame", return_value=None),
	):
		response = client.get("/enroll/api/snapshot.jpg", headers=_auth_headers())

	assert response.status_code == 503
	assert "STREAM_USER" in response.json()["detail"]
