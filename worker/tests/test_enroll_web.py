"""Tests for enroll_web API routes."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from fastapi.testclient import TestClient

from face_store import load_store, photos_dir
from main import create_app
from settings import Settings


def _settings(tmp_path: Path, **overrides: object) -> Settings:
	db = tmp_path / "db"
	db.mkdir()
	return Settings(
		_env_file=None,
		db_dir=str(db),
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
	db_dir = settings.db_path()
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
	assert data["filename"] == "front"
	store = load_store(db_dir)
	assert len(store.people) == 1
	assert store.people[0].name == "alice"
	assert len(list(photos_dir(db_dir).glob("*.jpg"))) == 1


def test_capture_preserves_display_name_with_special_chars(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	db_dir = settings.db_path()
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
			data={"name": "Conor O'Brien", "label": "front"},
			files={"image": ("front.jpg", BytesIO(encoded.tobytes()), "image/jpeg")},
		)

	assert response.status_code == 200
	store = load_store(db_dir)
	assert store.people[0].name == "Conor O'Brien"


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
	db_dir = settings.db_path()
	store = load_store(db_dir)
	from face_store import PersonRecord, register_photo, save_store

	person = PersonRecord(id="person-1", name="alice", photos=[])
	photo_path = photos_dir(db_dir) / "photo-1.jpg"
	photos_dir(db_dir).mkdir(parents=True, exist_ok=True)
	photo_path.write_bytes(b"x")
	register_photo(person, "one", photo_path)
	store.people.append(person)
	save_store(store, db_dir)

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
	assert settings.gallery_path().is_file()


def test_delete_person(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	db_dir = settings.db_path()
	store = load_store(db_dir)
	from face_store import PersonRecord, register_photo, save_store

	person = PersonRecord(id="person-1", name="alice", photos=[])
	photo_path = photos_dir(db_dir) / "photo-1.jpg"
	photos_dir(db_dir).mkdir(parents=True, exist_ok=True)
	photo_path.write_bytes(b"x")
	register_photo(person, "one", photo_path)
	store.people.append(person)
	save_store(store, db_dir)
	client = _client(settings)

	with patch("main.warmup_face_app"):
		response = client.delete("/enroll/api/people/person-1", headers=_auth_headers())

	assert response.status_code == 200
	reloaded = load_store(db_dir)
	assert reloaded.people == []
	assert not photo_path.exists()


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


def test_scan_returns_crops(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	image = np.zeros((120, 120, 3), dtype=np.uint8)
	_, encoded = __import__("cv2").imencode(".jpg", image)

	embedding = np.array([1.0, 0.0], dtype=np.float32)
	mock_face = SimpleNamespace(
		bbox=np.array([20, 20, 100, 100], dtype=np.float32),
		normed_embedding=embedding,
	)
	mock_app = MagicMock()
	mock_app.get.return_value = [mock_face]

	with (
		patch("main.warmup_face_app"),
		patch("enroll_web.get_face_app", return_value=mock_app),
	):
		response = client.post(
			"/enroll/api/scan",
			headers=_auth_headers(),
			files={"file": ("clip.jpg", BytesIO(encoded.tobytes()), "image/jpeg")},
		)

	assert response.status_code == 200
	data = response.json()
	assert "session_id" not in data
	assert len(data["faces"]) == 1
	assert data["faces"][0]["thumbnail"].startswith("data:image/jpeg;base64,")
	assert data["faces"][0]["crop"].startswith("data:image/jpeg;base64,")


def test_capture_footage_saves_crop(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	db_dir = settings.db_path()
	image = np.zeros((80, 80, 3), dtype=np.uint8)
	_, encoded = __import__("cv2").imencode(".jpg", image)

	with patch("main.warmup_face_app"):
		response = client.post(
			"/enroll/api/capture",
			headers=_auth_headers(),
			data={"name": "guest", "label": "footage"},
			files={"image": ("crop.jpg", BytesIO(encoded.tobytes()), "image/jpeg")},
		)

	assert response.status_code == 200
	data = response.json()
	assert data["ok"] is True
	assert data["label"] == "footage-1"
	store = load_store(db_dir)
	assert len(store.people) == 1
	assert store.people[0].name == "guest"
	assert len(list(photos_dir(db_dir).glob("*.jpg"))) == 1


def test_capture_from_scan_skips_detect(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	db_dir = settings.db_path()
	image = np.zeros((80, 80, 3), dtype=np.uint8)
	_, encoded = __import__("cv2").imencode(".jpg", image)

	with patch("main.warmup_face_app"):
		response = client.post(
			"/enroll/api/capture",
			headers=_auth_headers(),
			data={"name": "guest", "label": "front", "from_scan": "1"},
			files={"image": ("front.jpg", BytesIO(encoded.tobytes()), "image/jpeg")},
		)

	assert response.status_code == 200
	data = response.json()
	assert data["ok"] is True
	assert data["label"] == "front"
	store = load_store(db_dir)
	assert store.people[0].photos[0].label == "front"
