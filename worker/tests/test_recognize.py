"""Tests for recognize (InsightFace mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from gallery import EnrolledFace, Gallery
from recognize import (
	RecognitionResult,
	_match_detected_face,
	recognize_frames,
	recognize_from_settings,
	result_to_payload,
)
from settings import Settings


def _face(embedding: list[float], *, det_score: float = 0.9) -> SimpleNamespace:
	return SimpleNamespace(
		normed_embedding=np.array(embedding, dtype=np.float32),
		det_score=det_score,
	)


def test_match_detected_face_known() -> None:
	gallery = Gallery(
		faces=[
			EnrolledFace(
				name="alice",
				embedding=np.array([1.0, 0.0], dtype=np.float32),
				photo="alice/a.jpg",
			),
			EnrolledFace(
				name="bob",
				embedding=np.array([0.0, 1.0], dtype=np.float32),
				photo="bob/b.jpg",
			),
		],
	)

	match = _match_detected_face(_face([1.0, 0.0]), gallery, threshold=0.4)

	assert match.name == "alice"
	assert match.score == pytest.approx(1.0)
	assert match.det_score == pytest.approx(0.9)


def test_match_detected_face_unknown_below_threshold() -> None:
	gallery = Gallery(
		faces=[
			EnrolledFace(
				name="alice",
				embedding=np.array([1.0, 0.0], dtype=np.float32),
				photo="alice/a.jpg",
			),
		],
	)

	match = _match_detected_face(_face([0.0, 1.0]), gallery, threshold=0.4)

	assert match.name is None
	assert match.score == pytest.approx(0.0)


def test_recognize_frames_picks_frame_with_most_faces() -> None:
	frames = [np.zeros((2, 2, 3), dtype=np.uint8) for _ in range(3)]
	alice_emb = np.array([1.0, 0.0], dtype=np.float32)
	gallery = Gallery(
		faces=[EnrolledFace(name="alice", embedding=alice_emb, photo="alice/a.jpg")],
	)

	mock_app = MagicMock()
	mock_app.get.side_effect = [
		[_face([1.0, 0.0])],
		[_face([1.0, 0.0], det_score=0.5), _face([0.0, 1.0], det_score=0.5)],
		[],
	]

	result = recognize_frames(frames, gallery, face_app=mock_app, threshold=0.4)

	assert result.names == ["alice"]
	assert result.unknown == 1
	assert len(result.matches) == 2


def test_recognize_frames_no_faces() -> None:
	frames = [np.zeros((2, 2, 3), dtype=np.uint8)]
	mock_app = MagicMock()
	mock_app.get.return_value = []

	result = recognize_frames(frames, Gallery(), face_app=mock_app, threshold=0.4)

	assert result == RecognitionResult(names=[], unknown=0, matches=[])


def test_recognize_from_settings_grabs_frames(tmp_path) -> None:
	gallery_path = tmp_path / "gallery.pkl"
	gallery = Gallery(
		faces=[EnrolledFace(name="alice", embedding=np.array([1.0, 0.0]), photo="a.jpg")],
	)
	from gallery import save_gallery

	save_gallery(gallery, gallery_path)

	frame = np.zeros((2, 2, 3), dtype=np.uint8)
	mock_app = MagicMock()
	mock_app.get.return_value = [_face([1.0, 0.0])]

	settings = Settings(
		_env_file=None,
		stream_url="rtsp://cam/stream",
		gallery_path=str(gallery_path),
	)

	with (
		patch("recognize.preview_hub.latest_frame", return_value=None),
		patch("recognize.FrameSource") as mock_source_cls,
	):
		mock_source_cls.return_value.grab_event_frames.return_value = [frame]
		result = recognize_from_settings(settings, face_app=mock_app, gallery=gallery)

	assert result.names == ["alice"]
	mock_source_cls.assert_called_once_with("rtsp://cam/stream")
	mock_source_cls.return_value.grab_event_frames.assert_called_once_with(5)


def test_recognize_from_settings_uses_preview_hub(tmp_path) -> None:
	gallery_path = tmp_path / "gallery.pkl"
	gallery = Gallery(
		faces=[EnrolledFace(name="alice", embedding=np.array([1.0, 0.0]), photo="a.jpg")],
	)
	from gallery import save_gallery

	save_gallery(gallery, gallery_path)

	frame = np.zeros((2, 2, 3), dtype=np.uint8)
	mock_app = MagicMock()
	mock_app.get.return_value = [_face([1.0, 0.0])]

	settings = Settings(
		_env_file=None,
		stream_url="rtsp://cam/stream",
		gallery_path=str(gallery_path),
		frames_per_event=2,
	)

	with (
		patch("recognize.preview_hub.latest_frame", return_value=frame),
		patch("recognize.FrameSource") as mock_source_cls,
		patch("recognize.time.sleep"),
	):
		result = recognize_from_settings(settings, face_app=mock_app, gallery=gallery)

	assert result.names == ["alice"]
	mock_source_cls.assert_not_called()


def test_recognize_from_settings_requires_stream_url() -> None:
	settings = Settings(_env_file=None, stream_url="")

	with pytest.raises(ValueError, match="STREAM_URL"):
		recognize_from_settings(settings, face_app=MagicMock(), gallery=Gallery())


def test_result_to_payload_shape() -> None:
	payload = result_to_payload(RecognitionResult(names=["alice"], unknown=0, matches=[]))

	assert payload["event"] == "doorbell"
	assert payload["names"] == ["alice"]
	assert payload["unknown"] == 0
	assert isinstance(payload["ts"], str)
