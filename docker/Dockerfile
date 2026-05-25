FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends     python3.10 python3.10-venv python3-pip     git git-lfs ffmpeg libgl1 libglib2.0-0     build-essential ninja-build curl ca-certificates     && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip setuptools wheel

# LongCat upstream pins CUDA 12.4 PyTorch 2.6.0.
RUN python3 -m pip install     torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0     --index-url https://download.pytorch.org/whl/cu124

RUN python3 -m pip install ninja psutil packaging
RUN python3 -m pip install flash_attn==2.7.4.post1 --no-build-isolation

RUN git clone --single-branch --branch main https://github.com/meituan-longcat/LongCat-Video /opt/LongCat-Video
WORKDIR /opt/LongCat-Video
RUN python3 -m pip install -r requirements.txt

WORKDIR /app
COPY docker/requirements-service.txt /app/docker/requirements-service.txt
RUN python3 -m pip install -r /app/docker/requirements-service.txt

COPY app /app/app
COPY scripts /app/scripts
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh /app/scripts/*.sh || true

ENV PYTHONPATH=/opt/LongCat-Video:/app
ENTRYPOINT ["/entrypoint.sh"]
