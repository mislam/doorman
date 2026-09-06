"""Pytest fixtures shared across doorbell integration test modules."""

from __future__ import annotations

import pytest
from doorbell_fixtures import build_fixture_gallery, insightface_available, say

from gallery import DEFAULT_MODEL, Gallery


@pytest.fixture(scope="session", autouse=True)
def _doorbell_integration_banner() -> None:
	if not insightface_available():
		return
	say("--- doorbell fixture integration ---")


@pytest.fixture(scope="session")
def face_app():
	if not insightface_available():
		pytest.skip("InsightFace not installed — run via homelab Docker (bun run test:integration)")
	from vision_runtime import create_face_app, ensure_onnxruntime_gpu

	providers = ensure_onnxruntime_gpu()
	backend = "CUDA" if "CUDAExecutionProvider" in providers else "CPU"
	say(f"Loading InsightFace {DEFAULT_MODEL} ({backend})...")
	app = create_face_app(DEFAULT_MODEL, quiet=True)
	say("Model ready.")
	return app


@pytest.fixture(scope="session")
def fixture_gallery(face_app) -> Gallery:
	from doorbell_fixtures import load_manifest

	manifest = load_manifest()
	if not manifest.get("enroll", []):
		pytest.skip("manifest.json has no enroll entries")
	try:
		return build_fixture_gallery(face_app)
	except RuntimeError as exc:
		pytest.skip(str(exc))


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
	if not insightface_available():
		return
	from doorbell_fixtures import flush_integration_summary

	flush_integration_summary()
