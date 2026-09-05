"""ONNX Runtime / InsightFace GPU bootstrap for homelab Docker."""

from __future__ import annotations

import logging
import os
from typing import Any

from gallery import DEFAULT_MODEL

logger = logging.getLogger(__name__)

_NVIDIA_LIB_MODULES = (
	"nvidia.cudnn.lib",
	"nvidia.cublas.lib",
	"nvidia.cuda_runtime.lib",
	"nvidia.cuda_nvrtc.lib",
)


def _patch_ld_library_path() -> None:
	"""Append pip-installed NVIDIA libs to LD_LIBRARY_PATH (PyTorch does this internally)."""
	dirs: list[str] = []
	for module in _NVIDIA_LIB_MODULES:
		try:
			imported = __import__(module, fromlist=["__file__"])
			lib_dir = os.path.dirname(imported.__file__)
		except (ImportError, TypeError):
			continue
		if lib_dir not in dirs:
			dirs.append(lib_dir)

	if not dirs:
		return

	existing = os.environ.get("LD_LIBRARY_PATH", "")
	prefix = ":".join(dirs)
	os.environ["LD_LIBRARY_PATH"] = f"{prefix}:{existing}" if existing else prefix


def ensure_onnxruntime_gpu() -> list[str]:
	"""Preload CUDA/cuDNN libs before InsightFace creates ONNX sessions."""
	_patch_ld_library_path()
	try:
		import onnxruntime as ort
	except ImportError:
		return []

	preload = getattr(ort, "preload_dlls", None)
	if callable(preload):
		try:
			preload(cuda=True, cudnn=True)
		except (OSError, TypeError):
			try:
				preload()
			except OSError:
				logger.debug("onnxruntime preload_dlls failed", exc_info=True)

	return list(ort.get_available_providers())


def log_inference_providers() -> list[str]:
	"""Log ONNX Runtime providers at worker startup (expect CUDA on homelab)."""
	providers = ensure_onnxruntime_gpu()
	logger.info("ONNX Runtime providers: %s", providers)
	if "CUDAExecutionProvider" not in providers:
		logger.warning(
			"CUDAExecutionProvider unavailable — inference will use CPU (check GPU image and cuDNN)"
		)
	return providers


_cached_face_app: Any | None = None
_cached_face_app_model: str | None = None


def get_face_app(model_name: str = DEFAULT_MODEL) -> Any:
	"""Return a cached InsightFace app (load once — models stay on GPU)."""
	global _cached_face_app, _cached_face_app_model
	if _cached_face_app is None or _cached_face_app_model != model_name:
		logger.info("Loading InsightFace model pack %s", model_name)
		_cached_face_app = create_face_app(model_name)
		_cached_face_app_model = model_name
	return _cached_face_app


def warmup_face_app(model_name: str = DEFAULT_MODEL) -> None:
	"""Load models at worker startup so the first doorbell POST is fast."""
	get_face_app(model_name)


def create_face_app(model_name: str = DEFAULT_MODEL) -> Any:
	"""Load InsightFace detect + embed model on GPU when available."""
	ensure_onnxruntime_gpu()
	from insightface.app import FaceAnalysis

	app = FaceAnalysis(
		name=model_name,
		providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
	)
	app.prepare(ctx_id=0, det_size=(640, 640))
	return app
