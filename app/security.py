import base64
import ipaddress
import socket
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_IMAGE_BYTES = 20 * 1024 * 1024
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv"}


def _is_public_host(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"cannot resolve image_url host: {hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise ValueError(f"image_url resolves to non-public address: {ip}")
    return True


def validate_media_url(url: str, allowed_suffixes: set[str], label: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"{label} must use https")
    if not parsed.hostname:
        raise ValueError(f"{label} must include a hostname")
    _is_public_host(parsed.hostname)
    suffix = Path(parsed.path).suffix.lower()
    if suffix and suffix not in allowed_suffixes:
        raise ValueError(f"{label} has unsupported file type")
    return url


def validate_image_url(url: str) -> str:
    return validate_media_url(url, ALLOWED_IMAGE_SUFFIXES, "image_url")


def validate_video_url(url: str) -> str:
    return validate_media_url(url, ALLOWED_VIDEO_SUFFIXES, "video_url")


def download_limited(url: str, dest: Path, max_bytes: int = MAX_IMAGE_BYTES, media_type: str = "image") -> Path:
    if media_type == "video":
        validate_video_url(url)
    else:
        validate_image_url(url)
    req = Request(url, headers={"User-Agent": "runpod-longcat-video/1.0"})
    with urlopen(req, timeout=30) as resp:
        length = resp.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            raise ValueError("image_url content is too large")
        dest.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with dest.open("wb") as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("image_url content exceeds max image size")
                f.write(chunk)
    return dest


def decode_base64_limited(data: str, dest: Path, max_bytes: int = MAX_IMAGE_BYTES) -> Path:
    if len(data) > max_bytes * 2:
        raise ValueError("image_base64 is too large")
    raw = base64.b64decode(data, validate=True)
    if len(raw) > max_bytes:
        raise ValueError("image_base64 decoded content is too large")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return dest


def ensure_upload_size(data: bytes, max_bytes: int = MAX_IMAGE_BYTES) -> bytes:
    if len(data) > max_bytes:
        raise ValueError("uploaded image is too large")
    return data
