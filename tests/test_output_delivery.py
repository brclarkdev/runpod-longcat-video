import importlib
from pathlib import Path

import pytest


class FakeS3Client:
    def __init__(self):
        self.uploads = []
        self.presigns = []

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        self.uploads.append(
            {
                "filename": filename,
                "bucket": bucket,
                "key": key,
                "extra_args": ExtraArgs,
            }
        )

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.presigns.append(
            {"operation": operation, "params": Params, "expires_in": ExpiresIn}
        )
        return f"https://signed.example/{Params['Bucket']}/{Params['Key']}?expires={ExpiresIn}"


def reload_modules(monkeypatch, **env):
    keys = [
        "LONGCAT_OUTPUT_DELIVERY",
        "LONGCAT_OBJECT_STORAGE_BUCKET",
        "LONGCAT_S3_BUCKET",
        "LONGCAT_OBJECT_STORAGE_ENDPOINT_URL",
        "LONGCAT_S3_ENDPOINT_URL",
        "LONGCAT_OBJECT_STORAGE_PREFIX",
        "LONGCAT_S3_PREFIX",
        "LONGCAT_OBJECT_STORAGE_PRESIGN_EXPIRES",
        "LONGCAT_S3_PRESIGN_EXPIRES",
        "LONGCAT_OBJECT_STORAGE_PUBLIC_BASE_URL",
        "LONGCAT_S3_PUBLIC_BASE_URL",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import app.config as config
    import app.output_delivery as output_delivery

    importlib.reload(config)
    return importlib.reload(output_delivery)


def test_volume_delivery_returns_only_output_path_by_default(monkeypatch, tmp_path):
    output_delivery = reload_modules(monkeypatch)
    video = tmp_path / "output.mp4"
    video.write_bytes(b"mp4")

    result = output_delivery.deliver_video(video, "job-123")

    assert result == {
        "output_path": str(video),
        "video_url": None,
        "object_key": None,
        "s3_uri": None,
    }


def test_s3_delivery_uploads_mp4_and_returns_presigned_url(monkeypatch, tmp_path):
    output_delivery = reload_modules(
        monkeypatch,
        LONGCAT_OUTPUT_DELIVERY="s3",
        LONGCAT_S3_BUCKET="longcat-videos",
        LONGCAT_S3_PREFIX="generated/videos",
        LONGCAT_S3_PRESIGN_EXPIRES="600",
    )
    fake_client = FakeS3Client()
    monkeypatch.setattr(output_delivery, "_s3_client", lambda: fake_client)
    video = tmp_path / "output.mp4"
    video.write_bytes(b"mp4")

    result = output_delivery.deliver_video(video, "job-abc")

    assert fake_client.uploads == [
        {
            "filename": str(video),
            "bucket": "longcat-videos",
            "key": "generated/videos/job-abc/output.mp4",
            "extra_args": {"ContentType": "video/mp4"},
        }
    ]
    assert fake_client.presigns == [
        {
            "operation": "get_object",
            "params": {"Bucket": "longcat-videos", "Key": "generated/videos/job-abc/output.mp4"},
            "expires_in": 600,
        }
    ]
    assert result == {
        "output_path": str(video),
        "video_url": "https://signed.example/longcat-videos/generated/videos/job-abc/output.mp4?expires=600",
        "object_key": "generated/videos/job-abc/output.mp4",
        "s3_uri": "s3://longcat-videos/generated/videos/job-abc/output.mp4",
    }


def test_s3_delivery_uses_public_base_url_when_configured(monkeypatch, tmp_path):
    output_delivery = reload_modules(
        monkeypatch,
        LONGCAT_OUTPUT_DELIVERY="s3",
        LONGCAT_S3_BUCKET="longcat-videos",
        LONGCAT_S3_PREFIX="outputs/",
        LONGCAT_S3_PUBLIC_BASE_URL="https://cdn.example/videos/",
    )
    fake_client = FakeS3Client()
    monkeypatch.setattr(output_delivery, "_s3_client", lambda: fake_client)
    video = tmp_path / "output.mp4"
    video.write_bytes(b"mp4")

    result = output_delivery.deliver_video(video, "job-public")

    assert result["video_url"] == "https://cdn.example/videos/outputs/job-public/output.mp4"
    assert result["s3_uri"] == "s3://longcat-videos/outputs/job-public/output.mp4"
    assert fake_client.presigns == []


def test_runpod_s3_delivery_returns_s3_uri_without_presign(monkeypatch, tmp_path):
    output_delivery = reload_modules(
        monkeypatch,
        LONGCAT_OUTPUT_DELIVERY="s3",
        LONGCAT_S3_BUCKET="06j8ee9sbn",
        LONGCAT_S3_PREFIX="longcat-outputs",
        LONGCAT_S3_ENDPOINT_URL="https://s3api-us-ks-2.runpod.io",
    )
    fake_client = FakeS3Client()
    monkeypatch.setattr(output_delivery, "_s3_client", lambda: fake_client)
    video = tmp_path / "output.mp4"
    video.write_bytes(b"mp4")

    result = output_delivery.deliver_video(video, "job-runpod")

    assert fake_client.uploads[0]["bucket"] == "06j8ee9sbn"
    assert fake_client.presigns == []
    assert result == {
        "output_path": str(video),
        "video_url": None,
        "object_key": "longcat-outputs/job-runpod/output.mp4",
        "s3_uri": "s3://06j8ee9sbn/longcat-outputs/job-runpod/output.mp4",
    }


def test_s3_delivery_requires_bucket(monkeypatch, tmp_path):
    output_delivery = reload_modules(monkeypatch, LONGCAT_OUTPUT_DELIVERY="s3")
    video = tmp_path / "output.mp4"
    video.write_bytes(b"mp4")

    with pytest.raises(RuntimeError, match="LONGCAT_S3_BUCKET"):
        output_delivery.deliver_video(video, "job-missing-bucket")
