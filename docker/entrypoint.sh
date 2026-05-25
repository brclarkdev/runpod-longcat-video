#!/usr/bin/env bash
set -euo pipefail

if [[ -d /runpod-volume ]]; then
  export RUNPOD_VOLUME_ROOT="${RUNPOD_VOLUME_ROOT:-/runpod-volume}"
else
  export RUNPOD_VOLUME_ROOT="${RUNPOD_VOLUME_ROOT:-/workspace}"
fi

export LONGCAT_MODEL_DIR="${LONGCAT_MODEL_DIR:-$RUNPOD_VOLUME_ROOT/models/LongCat-Video}"
export HF_HOME="${HF_HOME:-$RUNPOD_VOLUME_ROOT/cache/huggingface}"
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HF_HOME/hub}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME/transformers}"
export LONGCAT_OUTPUT_DIR="${LONGCAT_OUTPUT_DIR:-$RUNPOD_VOLUME_ROOT/outputs}"
export LONGCAT_JOB_DIR="${LONGCAT_JOB_DIR:-$RUNPOD_VOLUME_ROOT/jobs}"
export PYTHONPATH="/opt/LongCat-Video:/app:${PYTHONPATH:-}"

mkdir -p "$LONGCAT_OUTPUT_DIR" "$LONGCAT_JOB_DIR" "$HF_HUB_CACHE"

if [[ "${LONGCAT_SKIP_VOLUME_VERIFY:-0}" != "1" ]]; then
  python3 /app/scripts/verify_longcat_volume.py "$LONGCAT_MODEL_DIR"
fi

exec bash /app/scripts/start_api.sh
