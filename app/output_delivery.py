from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse

from botocore.config import Config

from app import config


def deliver_video(path: Path, job_id: str) -> dict:
    """Make a generated video retrievable and return delivery metadata."""
    path = Path(path)
    delivery = config.OUTPUT_DELIVERY.lower()
    if delivery in {"", "volume", "local"}:
        return {"output_path": str(path), "video_url": None, "object_key": None, "s3_uri": None}
    if delivery in {"s3", "object_storage", "r2", "b2"}:
        return _deliver_s3(path, job_id)
    raise RuntimeError(f"Unsupported LONGCAT_OUTPUT_DELIVERY={config.OUTPUT_DELIVERY!r}")


def _deliver_s3(path: Path, job_id: str) -> dict:
    bucket = config.OBJECT_STORAGE_BUCKET
    if not bucket:
        raise RuntimeError(
            "LONGCAT_OUTPUT_DELIVERY=s3 requires LONGCAT_S3_BUCKET or LONGCAT_OBJECT_STORAGE_BUCKET"
        )
    key = _object_key(job_id, path.name)
    _s3_client().upload_file(
        str(path),
        bucket,
        key,
        ExtraArgs={"ContentType": _content_type(path)},
    )
    return {
        "output_path": str(path),
        "video_url": _video_url(bucket, key),
        "object_key": key,
        "s3_uri": f"s3://{bucket}/{key}",
    }


def _object_key(job_id: str, filename: str) -> str:
    prefix = config.OBJECT_STORAGE_PREFIX.strip("/")
    key = f"{job_id}/{filename}"
    return f"{prefix}/{key}" if prefix else key


def _video_url(bucket: str, key: str) -> Optional[str]:
    public_base = config.OBJECT_STORAGE_PUBLIC_BASE_URL.rstrip("/")
    if public_base:
        return f"{public_base}/{quote(key)}"
    if _is_runpod_s3_endpoint():
        # RunPod's network-volume S3-compatible API documents
        # GeneratePresignedURL / `aws s3 presign` as unsupported. Return the
        # object key and s3_uri instead of a URL that will 403 for clients.
        return None
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=config.OBJECT_STORAGE_PRESIGN_EXPIRES,
    )


def _is_runpod_s3_endpoint() -> bool:
    parsed = urlparse(str(config.OBJECT_STORAGE_ENDPOINT_URL))
    host = str(parsed.hostname or "")
    return host.endswith(".runpod.io") and host.startswith("s3api-")


def _s3_client():
    import boto3

    kwargs = {}
    if config.OBJECT_STORAGE_REGION:
        kwargs["region_name"] = config.OBJECT_STORAGE_REGION
    if config.OBJECT_STORAGE_ENDPOINT_URL:
        kwargs["endpoint_url"] = config.OBJECT_STORAGE_ENDPOINT_URL
    if config.OBJECT_STORAGE_ADDRESSING_STYLE:
        kwargs["config"] = Config(
            s3={"addressing_style": config.OBJECT_STORAGE_ADDRESSING_STYLE}
        )
    return boto3.client("s3", **kwargs)


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".mp4":
        return "video/mp4"
    if suffix == ".mov":
        return "video/quicktime"
    if suffix == ".webm":
        return "video/webm"
    return "application/octet-stream"
