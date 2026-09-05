"""Tests for vision_runtime GPU bootstrap (onnxruntime mocked)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from vision_runtime import (
	_patch_ld_library_path,
	ensure_onnxruntime_gpu,
	get_face_app,
	log_inference_providers,
)


def test_ensure_onnxruntime_gpu_preloads_before_providers() -> None:
	mock_ort = MagicMock()
	mock_ort.get_available_providers.return_value = [
		"CUDAExecutionProvider",
		"CPUExecutionProvider",
	]
	mock_ort.preload_dlls = MagicMock()

	with patch.dict("sys.modules", {"onnxruntime": mock_ort}):
		providers = ensure_onnxruntime_gpu()

	mock_ort.preload_dlls.assert_called_once_with(cuda=True, cudnn=True)
	assert providers == ["CUDAExecutionProvider", "CPUExecutionProvider"]


def test_log_inference_providers_warns_without_cuda(caplog) -> None:
	with patch("vision_runtime.ensure_onnxruntime_gpu", return_value=["CPUExecutionProvider"]):
		log_inference_providers()

	assert "CUDAExecutionProvider unavailable" in caplog.text


def test_patch_ld_library_path_adds_nvidia_dirs(monkeypatch) -> None:
	import sys
	from types import ModuleType

	fake = ModuleType("nvidia.cudnn.lib")
	fake.__file__ = "/fake/nvidia/cudnn/lib/__init__.py"
	monkeypatch.setitem(sys.modules, "nvidia.cudnn.lib", fake)
	monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)

	_patch_ld_library_path()

	assert os.environ["LD_LIBRARY_PATH"].startswith("/fake/nvidia/cudnn/lib")


def test_get_face_app_caches_by_model() -> None:
	import vision_runtime

	vision_runtime._cached_face_app = None
	vision_runtime._cached_face_app_model = None
	mock_app = object()

	with patch("vision_runtime.create_face_app", return_value=mock_app) as mock_create:
		first = get_face_app("buffalo_l")
		second = get_face_app("buffalo_l")

	assert first is mock_app
	assert second is mock_app
	mock_create.assert_called_once()
