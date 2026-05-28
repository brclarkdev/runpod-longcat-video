import asyncio
import os
from pathlib import Path

from app.security import decode_base64_limited, download_limited

from app import config
from app.longcat_service import LongCatService
from app.output_delivery import deliver_video
from app.schemas import (
    ImageVideoRequest,
    InteractiveVideoRequest,
    LongVideoRequest,
    TextVideoRequest,
    VideoContinuationRequest,
)

_service = None


def get_service():
    global _service
    if _service is None:
        _service = LongCatService()
    return _service


async def handler(event):
    data = event.get("input", {})
    mode = data.get("mode", "text")
    job_id = data.get("job_id") or os.urandom(8).hex()
    try:
        if mode == "text":
            req = TextVideoRequest(**{k: v for k, v in data.items() if k in TextVideoRequest.model_fields})
            output = get_service().generate_text_video(job_id=job_id, **req.model_dump())
            return {"job_id": job_id, "status": "completed", **deliver_video(output, job_id)}

        if mode == "image":
            req = ImageVideoRequest(**{k: v for k, v in data.items() if k in ImageVideoRequest.model_fields})
            image_path = _materialize_image(data, job_id)
            output = get_service().generate_image_video(
                job_id=job_id,
                image_path=image_path,
                prompt=req.prompt,
                negative_prompt=req.negative_prompt,
                resolution=req.resolution,
                num_frames=req.num_frames,
                seed=req.seed,
                use_distill=req.use_distill,
                use_refine=req.use_refine,
            )
            return {"job_id": job_id, "status": "completed", **deliver_video(output, job_id)}

        if mode == "video_continuation":
            req = VideoContinuationRequest(**{k: v for k, v in data.items() if k in VideoContinuationRequest.model_fields})
            output = get_service().generate_video_continuation(job_id=job_id, **req.model_dump())
            return {"job_id": job_id, "status": "completed", **deliver_video(output, job_id)}

        if mode == "long_video":
            req = LongVideoRequest(**{k: v for k, v in data.items() if k in LongVideoRequest.model_fields})
            output = get_service().generate_long_video(job_id=job_id, **req.model_dump())
            return {"job_id": job_id, "status": "completed", **deliver_video(output, job_id)}

        if mode == "interactive":
            req = InteractiveVideoRequest(**{k: v for k, v in data.items() if k in InteractiveVideoRequest.model_fields})
            output = get_service().generate_interactive_video(job_id=job_id, **req.model_dump())
            return {"job_id": job_id, "status": "completed", **deliver_video(output, job_id)}

        raise ValueError("mode must be one of: text, image, video_continuation, long_video, interactive")
    except Exception as exc:
        return {"job_id": job_id, "status": "failed", "error": repr(exc)}


def _materialize_image(data: dict, job_id: str) -> Path:
    upload_dir = config.LONGCAT_OUTPUT_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    if data.get("image_url"):
        suffix = Path(data["image_url"].split("?")[0]).suffix or ".png"
        path = upload_dir / f"{job_id}{suffix}"
        return download_limited(data["image_url"], path)
    if data.get("image_base64"):
        path = upload_dir / f"{job_id}.png"
        return decode_base64_limited(data["image_base64"], path)
    raise ValueError("image jobs require image_url or image_base64")


if __name__ == "__main__":
    mode = os.environ.get("MODE_TO_RUN", "pod_test")
    if mode == "serverless":
        import runpod
        runpod.serverless.start({"handler": handler, "concurrency_modifier": lambda current: 1})
    else:
        sample = {"input": {"mode": "text", "prompt": "A red ball rolls across a wooden table, cinematic lighting.", "use_distill": True, "use_refine": False}}
        print(asyncio.run(handler(sample)))
