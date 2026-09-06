"""Doorface worker entrypoint — run from worker/: python main.py"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from enroll_web import router as enroll_router
from notify import notify_ha
from recognize import log_result, recognize_from_settings, result_to_payload
from settings import Settings, __version__
from stream import preview_hub
from vision_runtime import log_inference_providers, warmup_face_app

logger = logging.getLogger(__name__)

ENROLL_STATIC_DIR = Path(__file__).resolve().parent / "static" / "enroll"


def create_app(settings: Settings | None = None) -> FastAPI:
	"""Build the FastAPI app (POST /recognize)."""
	settings = settings or Settings()

	@asynccontextmanager
	async def lifespan(_app: FastAPI):
		log_inference_providers()
		if settings.stream_url:
			logger.info("Starting enroll preview stream (parallel with model load)...")
			preview_hub.start(settings.capture_stream_url())
		logger.info("Loading InsightFace models (port opens when this finishes)...")
		warmup_face_app()
		logger.info(
			"Worker ready — POST /recognize on %s:%s",
			settings.worker_host,
			settings.worker_port,
		)
		yield
		preview_hub.stop()

	app = FastAPI(title="Doorface", version=__version__, lifespan=lifespan)
	app.state.settings = settings

	@app.get("/health")
	def health() -> dict[str, str]:
		return {"status": "ok"}

	@app.post("/recognize")
	def recognize() -> dict[str, object]:
		try:
			result = recognize_from_settings(settings)
		except (FileNotFoundError, ConnectionError) as exc:
			raise HTTPException(status_code=503, detail=str(exc)) from exc
		except ValueError as exc:
			raise HTTPException(status_code=500, detail=str(exc)) from exc
		except Exception as exc:
			logger.exception("Recognition failed")
			raise HTTPException(status_code=503, detail=str(exc)) from exc

		log_result(result)
		payload = result_to_payload(result)
		notify_ha(settings.ha_webhook_url, payload)
		return payload

	app.include_router(enroll_router)

	if ENROLL_STATIC_DIR.is_dir():
		app.mount(
			"/enroll",
			StaticFiles(directory=ENROLL_STATIC_DIR, html=True),
			name="web",
		)
	else:
		logger.warning("Enroll UI not built — run: bun run build:web")

	return app


def main() -> None:
	parser = argparse.ArgumentParser(description="Doorface worker")
	parser.add_argument(
		"--once",
		action="store_true",
		help="Run recognition once and print JSON (CLI test, no HTTP server)",
	)
	args = parser.parse_args()

	logging.basicConfig(
		level=logging.INFO,
		format="%(levelname)s %(name)s: %(message)s",
	)

	settings = Settings()

	if args.once:
		log_inference_providers()
		try:
			result = recognize_from_settings(settings)
		except (FileNotFoundError, ConnectionError, ValueError) as exc:
			print(str(exc), file=sys.stderr)
			raise SystemExit(1) from exc
		except Exception as exc:
			logger.exception("Recognition failed")
			print(str(exc), file=sys.stderr)
			raise SystemExit(1) from exc

		log_result(result)
		payload = result_to_payload(result)
		notify_ha(settings.ha_webhook_url, payload)
		print(json.dumps(payload))
		return

	app = create_app(settings)
	uvicorn.run(app, host=settings.worker_host, port=settings.worker_port)


if __name__ == "__main__":
	main()
