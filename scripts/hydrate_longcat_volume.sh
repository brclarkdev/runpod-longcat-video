#!/usr/bin/env bash
set -euo pipefail

if [[ -d /runpod-volume ]]; then
  export RUNPOD_VOLUME_ROOT="${RUNPOD_VOLUME_ROOT:-/runpod-volume}"
elif [[ -d /workspace ]]; then
  export RUNPOD_VOLUME_ROOT="${RUNPOD_VOLUME_ROOT:-/workspace}"
elif [[ -z "${RUNPOD_VOLUME_ROOT:-}" && "${LONGCAT_ALLOW_LOCAL_HYDRATION:-0}" != "1" ]]; then
  echo "ERROR: no RunPod volume mount found. Run this on a RunPod Pod with a network volume attached, or set RUNPOD_VOLUME_ROOT explicitly and LONGCAT_ALLOW_LOCAL_HYDRATION=1 for testing." >&2
  exit 2
else
  export RUNPOD_VOLUME_ROOT="${RUNPOD_VOLUME_ROOT}"
fi

export LONGCAT_MODEL_DIR="${LONGCAT_MODEL_DIR:-$RUNPOD_VOLUME_ROOT/models/LongCat-Video}"
export HF_HOME="${HF_HOME:-$RUNPOD_VOLUME_ROOT/cache/huggingface}"
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HF_HOME/hub}"

mkdir -p "$LONGCAT_MODEL_DIR" "$HF_HUB_CACHE"
python3 -m pip install -U "huggingface_hub[cli]"

huggingface-cli download meituan-longcat/LongCat-Video --local-dir "$LONGCAT_MODEL_DIR"

python3 "$(dirname "$0")/verify_longcat_volume.py" "$LONGCAT_MODEL_DIR"
du -sh "$LONGCAT_MODEL_DIR"
