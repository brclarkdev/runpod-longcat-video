import subprocess
import sys
from pathlib import Path

REQUIRED = [
    "dit/diffusion_pytorch_model.safetensors.index.json",
    "text_encoder/model.safetensors.index.json",
    "vae/diffusion_pytorch_model.safetensors",
    "scheduler/scheduler_config.json",
    "tokenizer/tokenizer.json",
    "lora/cfg_step_lora.safetensors",
    "lora/refinement_lora.safetensors",
]


def test_verify_longcat_volume_success(tmp_path: Path):
    for rel in REQUIRED:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    result = subprocess.run([sys.executable, "scripts/verify_longcat_volume.py", str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0
    assert "OK:" in result.stdout


def test_verify_longcat_volume_missing(tmp_path: Path):
    result = subprocess.run([sys.executable, "scripts/verify_longcat_volume.py", str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "Missing files" in result.stderr
