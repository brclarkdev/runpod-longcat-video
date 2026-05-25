import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import config
from app.job_store import JobStore
from app.longcat_service import LongCatService
from app.schemas import ImageVideoRequest, JobResponse, JobStatus, TextVideoRequest
from app.security import ensure_upload_size

app = FastAPI(title="RunPod LongCat-Video Service")
store = JobStore(config.LONGCAT_JOB_DIR)
executor = ThreadPoolExecutor(max_workers=1)
service: Optional[LongCatService] = None


def get_service() -> LongCatService:
    global service
    if service is None:
        service = LongCatService()
    return service


@app.on_event("startup")
def startup():
    config.LONGCAT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config.LONGCAT_JOB_DIR.mkdir(parents=True, exist_ok=True)
    if config.LOAD_MODEL_ON_STARTUP and not config.SKIP_MODEL_LOAD:
        get_service()


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/ready")
def ready():
    svc = get_service() if config.SKIP_MODEL_LOAD else service
    return {
        "ok": True,
        "skip_model_load": config.SKIP_MODEL_LOAD,
        "load_model_on_startup": config.LOAD_MODEL_ON_STARTUP,
        "model_loaded": bool(svc and svc.loaded),
        "model_dir": str(config.LONGCAT_MODEL_DIR),
        "model_dir_exists": config.LONGCAT_MODEL_DIR.exists(),
        "production_ready_marker": str(config.RUNPOD_VOLUME_ROOT / "longcat_volume.production_ready"),
        "production_ready": (config.RUNPOD_VOLUME_ROOT / "longcat_volume.production_ready").exists(),
        "output_dir": str(config.LONGCAT_OUTPUT_DIR),
    }


@app.post("/v1/model/load")
def load_model():
    svc = get_service()
    return {"ok": True, "model_loaded": svc.loaded, "model_dir": str(config.LONGCAT_MODEL_DIR)}


def _run_text(job_id: str, req: TextVideoRequest):
    store.update(job_id, status=JobStatus.running.value)
    try:
        output = get_service().generate_text_video(job_id=job_id, **req.model_dump())
        store.update(job_id, status=JobStatus.completed.value, output_path=str(output))
    except Exception as exc:
        store.update(job_id, status=JobStatus.failed.value, error=repr(exc))


@app.post("/v1/video/text", status_code=202, response_model=JobResponse)
def submit_text(req: TextVideoRequest):
    job_id = store.create("text", req.model_dump())
    executor.submit(_run_text, job_id, req)
    return JobResponse(job_id=job_id, status=JobStatus.queued)


def _run_image(job_id: str, req: ImageVideoRequest, image_path: Path):
    store.update(job_id, status=JobStatus.running.value)
    try:
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
        store.update(job_id, status=JobStatus.completed.value, output_path=str(output))
    except Exception as exc:
        store.update(job_id, status=JobStatus.failed.value, error=repr(exc))


@app.post("/v1/video/image", status_code=202, response_model=JobResponse)
async def submit_image(
    prompt: str = Form(...),
    negative_prompt: Optional[str] = Form(None),
    resolution: str = Form("480p"),
    num_frames: int = Form(93),
    seed: int = Form(42),
    use_distill: bool = Form(True),
    use_refine: bool = Form(False),
    image: UploadFile = File(...),
):
    if image.content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status_code=400, detail="image must be PNG, JPEG, or WebP")
    req = ImageVideoRequest(prompt=prompt, negative_prompt=negative_prompt, resolution=resolution, num_frames=num_frames, seed=seed, use_distill=use_distill, use_refine=use_refine)
    suffix = Path(image.filename or "input.png").suffix or ".png"
    tmp_dir = config.LONGCAT_OUTPUT_DIR / "uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    data = ensure_upload_size(await image.read())
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=tmp_dir) as f:
        f.write(data)
        image_path = Path(f.name)
    job_id = store.create("image", req.model_dump())
    executor.submit(_run_image, job_id, req, image_path)
    return JobResponse(job_id=job_id, status=JobStatus.queued)


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str):
    record = store.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="job not found")
    return record


@app.get("/v1/jobs/{job_id}/video")
def get_video(job_id: str):
    record = store.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="job not found")
    if record.get("status") != JobStatus.completed.value or not record.get("output_path"):
        raise HTTPException(status_code=409, detail="job is not complete")
    path = Path(record["output_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="output file not found")
    return FileResponse(path)
