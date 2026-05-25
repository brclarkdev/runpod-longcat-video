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
LOAD_MODEL_ON_STARTUP = os.environ.get("LONGCAT_LOAD_ON_STARTUP", "0") == "1"
OUTPUT_DELIVERY = os.environ.get("LONGCAT_OUTPUT_DELIVERY", "volume")
OBJECT_STORAGE_BUCKET = os.environ.get("LONGCAT_OBJECT_STORAGE_BUCKET") or os.environ.get("LONGCAT_S3_BUCKET")
OBJECT_STORAGE_PREFIX = os.environ.get("LONGCAT_OBJECT_STORAGE_PREFIX") or os.environ.get("LONGCAT_S3_PREFIX", "longcat-outputs")
OBJECT_STORAGE_ENDPOINT_URL = os.environ.get("LONGCAT_OBJECT_STORAGE_ENDPOINT_URL") or os.environ.get("LONGCAT_S3_ENDPOINT_URL")
OBJECT_STORAGE_REGION = os.environ.get("LONGCAT_OBJECT_STORAGE_REGION") or os.environ.get("LONGCAT_S3_REGION")
OBJECT_STORAGE_PUBLIC_BASE_URL = os.environ.get("LONGCAT_OBJECT_STORAGE_PUBLIC_BASE_URL") or os.environ.get("LONGCAT_S3_PUBLIC_BASE_URL", "")
OBJECT_STORAGE_ADDRESSING_STYLE = os.environ.get("LONGCAT_OBJECT_STORAGE_ADDRESSING_STYLE") or os.environ.get("LONGCAT_S3_ADDRESSING_STYLE", "")
OBJECT_STORAGE_PRESIGN_EXPIRES = int(
    os.environ.get("LONGCAT_OBJECT_STORAGE_PRESIGN_EXPIRES")
    or os.environ.get("LONGCAT_S3_PRESIGN_EXPIRES", "86400")
)
DEFAULT_NEGATIVE_PROMPT = os.environ.get(
    "LONGCAT_DEFAULT_NEGATIVE_PROMPT",
    "Bright tones, overexposed, static, blurred details, subtitles, style, works, paintings, images, static, overall gray, worst quality, low quality, JPEG compression residue, ugly, incomplete, extra fingers, poorly drawn hands, poorly drawn faces, deformed, disfigured, misshapen limbs, fused fingers, still picture, messy background, three legs, many people in the background, walking backwards",
)
