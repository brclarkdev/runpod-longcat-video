import os
from pathlib import Path


def volume_root() -> Path:
    explicit = os.environ.get("RUNPOD_VOLUME_ROOT")
    if explicit:
        return Path(explicit)
    if Path("/runpod-volume").exists():
        return Path("/runpod-volume")
    return Path("/workspace")


RUNPOD_VOLUME_ROOT = volume_root()
LONGCAT_MODEL_DIR = Path(os.environ.get("LONGCAT_MODEL_DIR", str(RUNPOD_VOLUME_ROOT / "models" / "LongCat-Video")))
HF_HOME = Path(os.environ.get("HF_HOME", str(RUNPOD_VOLUME_ROOT / "cache" / "huggingface")))
LONGCAT_OUTPUT_DIR = Path(os.environ.get("LONGCAT_OUTPUT_DIR", str(RUNPOD_VOLUME_ROOT / "outputs")))
LONGCAT_JOB_DIR = Path(os.environ.get("LONGCAT_JOB_DIR", str(RUNPOD_VOLUME_ROOT / "jobs")))
SKIP_MODEL_LOAD = os.environ.get("LONGCAT_SKIP_MODEL_LOAD", "0") == "1"
DEFAULT_NEGATIVE_PROMPT = os.environ.get(
    "LONGCAT_DEFAULT_NEGATIVE_PROMPT",
    "Bright tones, overexposed, static, blurred details, subtitles, style, works, paintings, images, static, overall gray, worst quality, low quality, JPEG compression residue, ugly, incomplete, extra fingers, poorly drawn hands, poorly drawn faces, deformed, disfigured, misshapen limbs, fused fingers, still picture, messy background, three legs, many people in the background, walking backwards",
)
