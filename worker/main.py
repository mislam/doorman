"""Doorface worker entrypoint — run from worker/: python main.py"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException

from recognize import log_result, recognize_from_settings, result_to_payload
from settings import Settings, __version__
from vision_runtime import log_inference_providers, warmup_face_app

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
	"""Build the FastAPI app (POST /recognize)."""
	settings = settings or Settings()

	@asynccontextmanager
	async def lifespan(_app: FastAPI):
		log_inference_providers()
		logger.info("Loading InsightFace models (port opens when this finishes)...")
		warmup_face_app()
		logger.info(
			"Worker ready — POST /recognize on %s:%s",
			settings.worker_host,
			settings.worker_port,
		)
		yield

	app = FastAPI(title="Doorface", version=__version__, lifespan=lifespan)

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
		return result_to_payload(result)

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
		print(json.dumps(result_to_payload(result)))
		return

	app = create_app(settings)
	uvicorn.run(app, host=settings.worker_host, port=settings.worker_port)


if __name__ == "__main__":
	main()
