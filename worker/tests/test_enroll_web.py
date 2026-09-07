"""Tests for enroll_web API routes."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from fastapi.testclient import TestClient

from enroll_web import _center_square_crop, _primary_enroll_face
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


def _valid_enroll_frame() -> np.ndarray:
	"""BGR frame that passes lighting, sharpness, and plain-background checks."""
	rng = np.random.default_rng(1)
	frame = np.full((80, 80, 3), 165, dtype=np.uint8)
	frame[15:75, 15:65] = rng.integers(120, 200, size=(60, 50, 3), dtype=np.uint8)
	return frame


def _valid_enroll_face(
	*,
	pitch: float = 5.0,
	yaw: float = 3.0,
	roll: float = 0.0,
	det_score: float = 0.99,
) -> SimpleNamespace:
	"""Face with bbox/landmarks that pass enrollment quality checks on an 80×80 frame."""
	kps = np.array(
		[[25, 28], [55, 28], [40, 40], [30, 58], [50, 58]],
		dtype=np.float32,
	)
	return SimpleNamespace(
		det_score=det_score,
		pose=np.array([pitch, yaw, roll]),
		bbox=np.array([15, 15, 65, 75], dtype=np.float32),
		kps=kps,
	)


def _forehead_only_face() -> SimpleNamespace:
	"""Partial face clipped at the top of the frame."""
	kps = np.array(
		[[25, 0.5], [55, 0.5], [40, 6], [30, 10], [50, 10]],
		dtype=np.float32,
	)
	return SimpleNamespace(
		det_score=0.99,
		pose=np.array([5.0, 3.0, 0.0]),
		bbox=np.array([15, 0, 65, 40], dtype=np.float32),
		kps=kps,
	)


def test_list_people_empty(tmp_path: Path) -> None:
	client = _client(_settings(tmp_path))
	response = client.get("/enroll/api/people", headers=_auth_headers())
	assert response.status_code == 200
	assert response.json() == []


def test_enroll_requires_token(tmp_path: Path) -> None:
	client = _client(_settings(tmp_path))
	response = client.get("/enroll/api/people")
	assert response.status_code == 401


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


def test_enroll_person_saves_and_rebuilds(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	db_dir = settings.db_path()
	image = np.zeros((80, 80, 3), dtype=np.uint8)
	_, encoded = __import__("cv2").imencode(".jpg", image)

	embedding = np.array([1.0, 0.0], dtype=np.float32)
	mock_app = MagicMock()
	mock_app.get.return_value = [SimpleNamespace(det_score=0.9, normed_embedding=embedding)]

	with (
		patch("main.warmup_face_app"),
		patch("enroll.create_face_app", return_value=mock_app),
		patch("enroll.cv2.imread", return_value=image),
	):
		response = client.post(
			"/enroll/api/enroll",
			headers=_auth_headers(),
			data={"name": "alice", "source": "live"},
			files=[
				("images", ("one.jpg", BytesIO(encoded.tobytes()), "image/jpeg")),
				("images", ("two.jpg", BytesIO(encoded.tobytes()), "image/jpeg")),
			],
		)

	assert response.status_code == 200
	data = response.json()
	assert data["embeddings"] == 2
	store = load_store(db_dir)
	assert store.people[0].name == "alice"
	assert len(store.people[0].photos) == 2
	assert store.people[0].photos[0].label == "photo-1"
	assert store.people[0].photos[1].label == "photo-2"
	assert settings.gallery_path().is_file()
	assert len(list(photos_dir(db_dir).glob("*.jpg"))) == 2


def test_enroll_replace_requires_confirm_flag(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	db_dir = settings.db_path()
	image = np.zeros((80, 80, 3), dtype=np.uint8)
	_, encoded = __import__("cv2").imencode(".jpg", image)

	embedding = np.array([1.0, 0.0], dtype=np.float32)
	mock_app = MagicMock()
	mock_app.get.return_value = [SimpleNamespace(det_score=0.9, normed_embedding=embedding)]

	with (
		patch("main.warmup_face_app"),
		patch("enroll.create_face_app", return_value=mock_app),
		patch("enroll.cv2.imread", return_value=image),
	):
		first = client.post(
			"/enroll/api/enroll",
			headers=_auth_headers(),
			data={"name": "Alice", "source": "live"},
			files=[("images", ("one.jpg", BytesIO(encoded.tobytes()), "image/jpeg"))],
		)
		assert first.status_code == 200

		conflict = client.post(
			"/enroll/api/enroll",
			headers=_auth_headers(),
			data={"name": "alice", "source": "live", "replace": "false"},
			files=[("images", ("two.jpg", BytesIO(encoded.tobytes()), "image/jpeg"))],
		)

	assert conflict.status_code == 409
	store = load_store(db_dir)
	assert len(store.people) == 1
	assert len(store.people[0].photos) == 1
	assert store.people[0].name == "Alice"


def test_enroll_replace_clears_old_photos(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	db_dir = settings.db_path()
	image = np.zeros((80, 80, 3), dtype=np.uint8)
	_, encoded = __import__("cv2").imencode(".jpg", image)

	embedding = np.array([1.0, 0.0], dtype=np.float32)
	mock_app = MagicMock()
	mock_app.get.return_value = [SimpleNamespace(det_score=0.9, normed_embedding=embedding)]

	with (
		patch("main.warmup_face_app"),
		patch("enroll.create_face_app", return_value=mock_app),
		patch("enroll.cv2.imread", return_value=image),
	):
		first = client.post(
			"/enroll/api/enroll",
			headers=_auth_headers(),
			data={"name": "Alice", "source": "live"},
			files=[
				("images", ("one.jpg", BytesIO(encoded.tobytes()), "image/jpeg")),
				("images", ("two.jpg", BytesIO(encoded.tobytes()), "image/jpeg")),
			],
		)
		assert first.status_code == 200
		old_files = {path.name for path in photos_dir(db_dir).glob("*.jpg")}
		assert len(old_files) == 2

		replaced = client.post(
			"/enroll/api/enroll",
			headers=_auth_headers(),
			data={"name": "alice", "source": "live", "replace": "true"},
			files=[("images", ("three.jpg", BytesIO(encoded.tobytes()), "image/jpeg"))],
		)

	assert replaced.status_code == 200
	store = load_store(db_dir)
	assert len(store.people) == 1
	assert store.people[0].name == "Alice"
	assert len(store.people[0].photos) == 1
	assert store.people[0].photos[0].label == "photo-1"
	new_files = {path.name for path in photos_dir(db_dir).glob("*.jpg")}
	assert len(new_files) == 1
	assert new_files.isdisjoint(old_files)


def test_enroll_footage_uses_footage_labels(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	db_dir = settings.db_path()
	image = np.zeros((80, 80, 3), dtype=np.uint8)
	_, encoded = __import__("cv2").imencode(".jpg", image)

	embedding = np.array([1.0, 0.0], dtype=np.float32)
	mock_app = MagicMock()
	mock_app.get.return_value = [SimpleNamespace(det_score=0.9, normed_embedding=embedding)]

	with (
		patch("main.warmup_face_app"),
		patch("enroll.create_face_app", return_value=mock_app),
		patch("enroll.cv2.imread", return_value=image),
	):
		response = client.post(
			"/enroll/api/enroll",
			headers=_auth_headers(),
			data={"name": "guest", "source": "footage"},
			files=[("images", ("one.jpg", BytesIO(encoded.tobytes()), "image/jpeg"))],
		)

	assert response.status_code == 200
	store = load_store(db_dir)
	assert store.people[0].photos[0].label == "footage-1"


def test_doorbell_pose_check_rejects_turned_center(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	frame = _valid_enroll_frame()
	mock_face = _valid_enroll_face(yaw=30.0)

	with (
		patch("main.warmup_face_app"),
		patch("enroll_web._doorbell_face_probe", return_value=(frame, mock_face, 1)),
	):
		response = client.get(
			"/enroll/api/capture/doorbell/pose?step=center",
			headers=_auth_headers(),
		)

	assert response.status_code == 200
	data = response.json()
	assert data["ok"] is False
	assert data["hint"] is not None


def test_doorbell_pose_check_accepts_center(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	frame = _valid_enroll_frame()
	mock_face = _valid_enroll_face()

	with (
		patch("main.warmup_face_app"),
		patch("enroll_web._doorbell_face_probe", return_value=(frame, mock_face, 1)),
	):
		response = client.get(
			"/enroll/api/capture/doorbell/pose?step=center",
			headers=_auth_headers(),
		)

	assert response.status_code == 200
	assert response.json()["ok"] is True


def test_doorbell_preview_rejects_bad_pose(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	frame = _valid_enroll_frame()
	mock_face = _valid_enroll_face(yaw=30.0)

	with (
		patch("main.warmup_face_app"),
		patch("enroll_web._doorbell_face_probe", return_value=(frame, mock_face, 1)),
	):
		response = client.post(
			"/enroll/api/capture/doorbell/preview?step=center",
			headers=_auth_headers(),
		)

	assert response.status_code == 422


def test_phone_pose_check_accepts_center(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	image = _valid_enroll_frame()
	_, encoded = __import__("cv2").imencode(".jpg", image)
	mock_face = _valid_enroll_face()

	with (
		patch("main.warmup_face_app"),
		patch("enroll_web._image_face_probe", return_value=(mock_face, 1)),
	):
		response = client.post(
			"/enroll/api/capture/phone/pose?step=center",
			headers=_auth_headers(),
			files={"image": ("frame.jpg", BytesIO(encoded.tobytes()), "image/jpeg")},
		)

	assert response.status_code == 200
	assert response.json()["ok"] is True


def test_phone_preflight_accepts_frontal(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	image = _valid_enroll_frame()
	_, encoded = __import__("cv2").imencode(".jpg", image)
	mock_face = _valid_enroll_face(yaw=30.0)

	with (
		patch("main.warmup_face_app"),
		patch("enroll_web._image_face_probe", return_value=(mock_face, 1)),
	):
		response = client.post(
			"/enroll/api/capture/phone/pose?step=left&preflight=true",
			headers=_auth_headers(),
			files={"image": ("frame.jpg", BytesIO(encoded.tobytes()), "image/jpeg")},
		)

	assert response.status_code == 200
	assert response.json()["ok"] is True


def test_phone_pose_check_rejects_turned_center(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	image = _valid_enroll_frame()
	_, encoded = __import__("cv2").imencode(".jpg", image)
	mock_face = _valid_enroll_face(yaw=30.0)

	with (
		patch("main.warmup_face_app"),
		patch("enroll_web._image_face_probe", return_value=(mock_face, 1)),
	):
		response = client.post(
			"/enroll/api/capture/phone/pose?step=center&mirror_yaw=true",
			headers=_auth_headers(),
			files={"image": ("frame.jpg", BytesIO(encoded.tobytes()), "image/jpeg")},
		)

	assert response.status_code == 200
	data = response.json()
	assert data["ok"] is False
	assert data["hint"] is not None


def test_phone_preview_returns_jpeg(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	image = _valid_enroll_frame()
	_, encoded = __import__("cv2").imencode(".jpg", image)
	mock_face = _valid_enroll_face()

	with (
		patch("main.warmup_face_app"),
		patch("enroll_web._image_face_probe", return_value=(mock_face, 1)),
	):
		response = client.post(
			"/enroll/api/capture/phone/preview?step=center",
			headers=_auth_headers(),
			files={"image": ("frame.jpg", BytesIO(encoded.tobytes()), "image/jpeg")},
		)

	assert response.status_code == 200
	assert response.headers["content-type"] == "image/jpeg"
	assert len(response.content) > 0


def test_phone_pose_check_rejects_partial_face(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	image = _valid_enroll_frame()
	_, encoded = __import__("cv2").imencode(".jpg", image)
	mock_face = _forehead_only_face()

	with (
		patch("main.warmup_face_app"),
		patch("enroll_web._image_face_probe", return_value=(mock_face, 1)),
	):
		response = client.post(
			"/enroll/api/capture/phone/pose?step=center",
			headers=_auth_headers(),
			files={"image": ("frame.jpg", BytesIO(encoded.tobytes()), "image/jpeg")},
		)

	assert response.status_code == 200
	data = response.json()
	assert data["ok"] is False
	assert data["hint"] == "Show your full face"


def test_doorbell_pose_check_rejects_partial_face(tmp_path: Path) -> None:
	settings = _settings(tmp_path)
	client = _client(settings)
	frame = _valid_enroll_frame()
	mock_face = _forehead_only_face()

	with (
		patch("main.warmup_face_app"),
		patch("enroll_web._doorbell_face_probe", return_value=(frame, mock_face, 1)),
	):
		response = client.get(
			"/enroll/api/capture/doorbell/pose?step=center",
			headers=_auth_headers(),
		)

	assert response.status_code == 200
	data = response.json()
	assert data["ok"] is False
	assert data["hint"] == "Show your full face"


def test_center_square_crop_landscape() -> None:
	image = np.zeros((80, 120, 3), dtype=np.uint8)
	cropped = _center_square_crop(image)
	assert cropped.shape == (80, 80, 3)


def test_primary_enroll_face_ignores_weak_secondary() -> None:
	primary = SimpleNamespace(det_score=0.95, bbox=np.array([10, 10, 100, 100], dtype=np.float32))
	weak = SimpleNamespace(det_score=0.35, bbox=np.array([200, 200, 220, 220], dtype=np.float32))
	face, count = _primary_enroll_face([primary, weak])
	assert count == 1
	assert face is primary


def test_primary_enroll_face_ignores_small_secondary() -> None:
	primary = SimpleNamespace(det_score=0.9, bbox=np.array([10, 10, 110, 110], dtype=np.float32))
	small = SimpleNamespace(det_score=0.8, bbox=np.array([200, 200, 230, 230], dtype=np.float32))
	face, count = _primary_enroll_face([primary, small])
	assert count == 1
	assert face is primary


def test_primary_enroll_face_rejects_two_strong() -> None:
	a = SimpleNamespace(det_score=0.9, bbox=np.array([10, 10, 100, 100], dtype=np.float32))
	b = SimpleNamespace(det_score=0.88, bbox=np.array([150, 10, 240, 100], dtype=np.float32))
	face, count = _primary_enroll_face([a, b])
	assert count == 2
	assert face is None
