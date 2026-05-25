#!/usr/bin/env python3
import os
import sys
from pathlib import Path

REQUIRED_FILES = [
    "dit/diffusion_pytorch_model.safetensors.index.json",
    "text_encoder/model.safetensors.index.json",
    "vae/diffusion_pytorch_model.safetensors",
    "scheduler/scheduler_config.json",
    "tokenizer/tokenizer.json",
    "lora/cfg_step_lora.safetensors",
    "lora/refinement_lora.safetensors",
]


def directory_size_bytes(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


def main() -> int:
    model_dir = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LONGCAT_MODEL_DIR", "")).expanduser()
    if not str(model_dir):
        print("ERROR: LONGCAT_MODEL_DIR is not set and no path argument was provided.", file=sys.stderr)
        return 2
    missing = [rel for rel in REQUIRED_FILES if not (model_dir / rel).is_file()]
    if missing:
        print(f"ERROR: LongCat model directory is incomplete: {model_dir}", file=sys.stderr)
        print("Missing files:", file=sys.stderr)
        for rel in missing:
            print(f"  - {rel}", file=sys.stderr)
        print("Hydrate the RunPod network volume from an attached Pod:", file=sys.stderr)
        print("  bash scripts/hydrate_longcat_volume.sh", file=sys.stderr)
        return 1
    size = directory_size_bytes(model_dir)
    print(f"OK: LongCat model directory verified: {model_dir}")
    print(f"Size: {size / (1024**3):.2f} GiB")
    if size < 70 * 1024**3:
        print("ERROR: size is below expected ~77.6 GiB; download is incomplete or only pointer/index files were written.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
