# Doorface worker — GPU image

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
	PYTHONUNBUFFERED=1 \
	PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
	python3.11 \
	python3.11-venv \
	python3-pip \
	libgl1 \
	libglib2.0-0 \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-vision.txt pyproject.toml ./
COPY main.py settings.py stream.py ./
COPY config/ ./config/

# TODO Phase 1: pip install onnxruntime-gpu + insightface via requirements-vision.txt
RUN python3.11 -m pip install --upgrade pip \
	&& python3.11 -m pip install -r requirements.txt

CMD ["python3.11", "main.py"]

EXPOSE 8768
