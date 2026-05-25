import asyncio
import importlib


def test_serverless_handler_returns_video_url_from_delivery(monkeypatch, tmp_path):
    import app.handler as handler

    importlib.reload(handler)

    output = tmp_path / "output.mp4"
    output.write_bytes(b"mp4")

    class FakeService:
        def generate_text_video(self, job_id, **payload):
            assert job_id == "job-with-url"
            assert payload["prompt"] == "hello"
            return output

    monkeypatch.setattr(handler, "get_service", lambda: FakeService())
    monkeypatch.setattr(
        handler,
        "deliver_video",
        lambda path, job_id: {
            "output_path": str(path),
            "video_url": "https://signed.example/video.mp4",
            "object_key": f"outputs/{job_id}/output.mp4",
            "s3_uri": f"s3://bucket/outputs/{job_id}/output.mp4",
        },
    )

    result = asyncio.run(
        handler.handler(
            {
                "input": {
                    "mode": "text",
                    "job_id": "job-with-url",
                    "prompt": "hello",
                    "use_distill": True,
                    "use_refine": False,
                }
            }
        )
    )

    assert result == {
        "job_id": "job-with-url",
        "status": "completed",
        "output_path": str(output),
        "video_url": "https://signed.example/video.mp4",
        "object_key": "outputs/job-with-url/output.mp4",
        "s3_uri": "s3://bucket/outputs/job-with-url/output.mp4",
    }
