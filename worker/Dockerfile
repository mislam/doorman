# Doorface worker — GPU image (CUDA + cuDNN for ONNX Runtime)
# Base matches tasmi-asr pattern: cudnn runtime, not cuda-runtime-only.

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
	PYTHONUNBUFFERED=1 \
	PIP_NO_CACHE_DIR=1 \
	NVIDIA_VISIBLE_DEVICES=all \
	NVIDIA_DRIVER_CAPABILITIES=compute,utility,video

# Skip NVIDIA container license banner on every start (compose CMD / docker run).
ENTRYPOINT []

RUN apt-get update && apt-get install -y --no-install-recommends \
	python3.11 \
	python3.11-venv \
	python3-pip \
	libgl1 \
	libglib2.0-0 \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first — code COPY below keeps pip layer cached across deploys.
COPY requirements.txt requirements-vision.txt pyproject.toml ./
RUN python3.11 -m pip install --upgrade pip \
	&& python3.11 -m pip install -r requirements.txt \
	&& python3.11 -m pip install "onnxruntime-gpu[cuda,cudnn]>=1.19.0,<1.27" \
	&& python3.11 -m pip install "onnx>=1.14.0" tqdm scipy scikit-image \
	&& python3.11 -m pip install --no-deps "insightface==1.0.1" \
	&& python3.11 -c "import onnxruntime as ort; ort.preload_dlls(cuda=True, cudnn=True); providers=ort.get_available_providers(); assert 'CUDAExecutionProvider' in providers, providers" \
	&& python3.11 -c "from insightface.app import FaceAnalysis"

COPY main.py settings.py stream.py gallery.py enroll.py recognize.py vision_runtime.py ./
COPY config/ ./config/

CMD ["python3.11", "main.py"]

EXPOSE 8768
