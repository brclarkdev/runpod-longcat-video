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

MODE_TO_RUN="${MODE_TO_RUN:-pod_api}"
case "$MODE_TO_RUN" in
  pod_api)
    exec uvicorn app.api:app --host "${LONGCAT_HOST:-0.0.0.0}" --port "${LONGCAT_PORT:-8000}" --workers 1
    ;;
  pod_test|serverless)
    exec python3 -m app.handler
    ;;
  *)
    echo "Unknown MODE_TO_RUN=$MODE_TO_RUN" >&2
    exit 2
    ;;
esac
