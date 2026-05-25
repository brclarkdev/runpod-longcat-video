# RunPod LongCat-Video Service Implementation Plan

Superseded/updated by: `docs/plans/2026-05-24-runpod-longcat-network-volume-first-plan.md`, which removes the A6000 benchmarking milestone and makes RunPod Network Volumes the source of truth for model storage.

> For Hermes: Use subagent-driven-development skill to implement this plan task-by-task.

Goal: Build a RunPod-hosted service that exposes LongCat-Video text-to-video and image-to-video workflows on RTX A6000-class hardware.

Architecture: Package the upstream LongCat-Video repo in a CUDA 12.4 / PyTorch 2.6 container, mount model weights from a persistent RunPod network volume, and expose a small FastAPI + worker service for local pod API usage. Start with one GPU worker and concurrency=1; add a RunPod Serverless handler only after the pod service is stable and benchmarked.

Tech Stack: RunPod RTX A6000, Docker, CUDA 12.4, Python 3.10, PyTorch 2.6.0+cu124, flash-attn 2.7.4.post1, Hugging Face model download, FastAPI, Uvicorn, Pydantic, torchvision/imageio-ffmpeg.

Source facts verified 2026-05-24:
- Upstream repo: https://github.com/meituan-longcat/LongCat-Video
- Model repo: https://huggingface.co/meituan-longcat/LongCat-Video
- Model weights are public / not gated.
- LongCat-Video supports T2V, I2V, video continuation, long video, and Streamlit.
- Upstream requirements include torch==2.6.0, transformers==4.41.0, diffusers==0.35.1, flash-attn==2.7.4.post1, streamlit==1.50.0.
- Upstream install docs pin PyTorch CUDA 12.4 wheels: torch==2.6.0+cu124, torchvision==0.21.0+cu124, torchaudio==2.6.0.
- Hugging Face LongCat-Video files total about 77.6 GiB on disk by HTTP HEAD checks.
- Upstream demo defaults: 480x832, 93 frames, 50 steps normal mode, 16 steps distill mode, 15 fps stage 1, 30 fps refined output.

---

## Target operating model

1. First milestone: RunPod GPU Pod, not Serverless.
   - Reason: LongCat has roughly 77.6 GiB of model assets and long cold starts. A persistent pod with a network volume makes debugging and warm model reuse much easier.
   - Expose FastAPI on pod TCP port 8000.
   - Keep the model loaded in one process.

2. Second milestone: RunPod Serverless worker.
   - Only after pod benchmarks are known.
   - Serverless must pre-bake dependencies in the image and use a network volume or pre-baked model layer; downloading 77.6 GiB on cold start is not acceptable.

3. Hardware strategy.
   - Baseline: 1x RTX A6000 48 GiB.
   - Run with concurrency=1 per GPU.
   - Begin with 480p distill mode before 50-step normal mode or 720p/refine.
   - If A6000 OOMs during full 50-step/refine workloads, use either:
     - 2x A6000 with `torchrun --nproc_per_node=2 ... --context_parallel_size=2`, or
     - disable refinement and expose 480p distill as the production tier.
   - Avoid `--enable_compile` until the non-compiled service is stable; compile can increase warmup time and memory pressure.

4. Storage strategy.
   - RunPod network volume: minimum 150 GiB; preferred 250 GiB.
   - `/workspace/LongCat-Video`: upstream code.
   - `/workspace/models/LongCat-Video`: Hugging Face model weights.
   - `/workspace/outputs`: generated videos.
   - `/workspace/jobs`: request/job metadata.

5. Service API.
   - `GET /health`: process is alive.
   - `GET /ready`: model loaded and CUDA ready.
   - `POST /v1/video/text`: submit text-to-video job.
   - `POST /v1/video/image`: submit image-to-video job with multipart image or image URL.
   - `GET /v1/jobs/{job_id}`: status and output path/URL.
   - `GET /v1/jobs/{job_id}/video`: stream/download mp4.

---

## Implementation tasks

### Task 1: Initialize this project repository

Objective: Create a clean wrapper repository around upstream LongCat-Video without vendoring model weights.

Files:
- Create: `README.md`
- Create: `.gitignore`
- Create: `docs/architecture.md`

Steps:
1. Initialize git if needed:
   - Run: `git init`
2. Add `.gitignore` entries:
   - `weights/`
   - `models/`
   - `outputs/`
   - `.venv/`
   - `__pycache__/`
   - `.pytest_cache/`
   - `.env`
3. Document that upstream LongCat-Video is cloned during image build or into `/workspace/LongCat-Video`, while weights live on `/workspace/models/LongCat-Video`.
4. Verify:
   - Run: `git status --short`
   - Expected: only wrapper repo docs/config files are tracked; no model files.

### Task 2: Create the Docker image definition

Objective: Build a repeatable CUDA 12.4 image compatible with upstream LongCat requirements.

Files:
- Create: `docker/Dockerfile`
- Create: `docker/entrypoint.sh`
- Create: `docker/requirements-service.txt`

Dockerfile requirements:
- Base image: `nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04` or a PyTorch CUDA 12.4 runtime image if available.
- Install OS packages:
  - `python3.10`, `python3.10-venv`, `python3-pip`, `git`, `git-lfs`, `ffmpeg`, `libgl1`, `libglib2.0-0`, `build-essential`, `ninja-build`, `curl`, `ca-certificates`.
- Install PyTorch:
  - `pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124`
- Install flash-attn prerequisites:
  - `pip install ninja psutil packaging`
  - `pip install flash_attn==2.7.4.post1 --no-build-isolation`
- Clone upstream:
  - `git clone --single-branch --branch main https://github.com/meituan-longcat/LongCat-Video /opt/LongCat-Video`
- Install upstream requirements except duplicate torch handling if necessary.
- Install service requirements:
  - `fastapi`, `uvicorn[standard]`, `python-multipart`, `pydantic`, `aiofiles`, `requests`, `huggingface_hub[hf_xet]`, `hf_xet`.

Verification:
- Build locally or on RunPod:
  - `docker build -f docker/Dockerfile -t longcat-runpod:cu124 .`
- Smoke test:
  - `docker run --gpus all --rm longcat-runpod:cu124 python - <<'PY'
import torch
print(torch.__version__)
print(torch.cuda.is_available())
PY`
- Expected: torch 2.6.0+cu124 and CUDA available on a GPU host.

### Task 3: Add model download and verification scripts

Objective: Prepare RunPod network volume once and avoid repeated 77.6 GiB downloads.

Files:
- Create: `scripts/download_models.sh`
- Create: `scripts/verify_models.py`

`download_models.sh` behavior:
- Set `MODEL_DIR=${MODEL_DIR:-/workspace/models/LongCat-Video}`.
- Install/verify the current `hf` CLI from `huggingface_hub`.
- Run:
  - `HF_XET_HIGH_PERFORMANCE=1 hf download meituan-longcat/LongCat-Video --local-dir "$MODEL_DIR"`
- Print total disk usage:
  - `du -sh "$MODEL_DIR"`

`verify_models.py` behavior:
- Check required paths exist:
  - `tokenizer/tokenizer.json`
  - `text_encoder/model.safetensors.index.json`
  - `dit/diffusion_pytorch_model.safetensors.index.json`
  - `vae/diffusion_pytorch_model.safetensors`
  - `scheduler/scheduler_config.json`
  - `lora/cfg_step_lora.safetensors`
  - `lora/refinement_lora.safetensors`
- Fail fast with a clear message if any are missing.

RunPod setup command:
- `MODEL_DIR=/workspace/models/LongCat-Video bash scripts/download_models.sh`
- `python scripts/verify_models.py /workspace/models/LongCat-Video`

Verification:
- Expected model directory size: about 78 GiB.
- Expected script exit code: 0.

### Task 4: Build a minimal LongCat loader module

Objective: Convert upstream Streamlit/demo loading code into reusable service code.

Files:
- Create: `app/longcat_loader.py`
- Test: `tests/test_request_models.py`

Implementation outline:
- Add `LongCatService` class.
- Inputs:
  - `checkpoint_dir: str`
  - `device: str = "cuda"`
  - `enable_compile: bool = False`
- Load:
  - `AutoTokenizer.from_pretrained(checkpoint_dir, subfolder="tokenizer", torch_dtype=torch.bfloat16)`
  - `UMT5EncoderModel.from_pretrained(checkpoint_dir, subfolder="text_encoder", torch_dtype=torch.bfloat16)`
  - `AutoencoderKLWan.from_pretrained(checkpoint_dir, subfolder="vae", torch_dtype=torch.bfloat16)`
  - `FlowMatchEulerDiscreteScheduler.from_pretrained(checkpoint_dir, subfolder="scheduler", torch_dtype=torch.bfloat16)`
  - `LongCatVideoTransformer3DModel.from_pretrained(checkpoint_dir, subfolder="dit", cp_split_hw=context_parallel_util.get_optimal_split(1), torch_dtype=torch.bfloat16)`
- Build `LongCatVideoPipeline` and move it to CUDA.
- Preload LoRAs:
  - `cfg_step_lora`
  - `refinement_lora`
- Add `torch_gc()` after each generation.

Important guardrails:
- Do not use torch distributed inside the API process for the initial 1-GPU service.
- Use the pipeline methods directly, following upstream `run_streamlit.py`, not the `torchrun` demo wrapper.
- Keep one loaded singleton per process.

Verification:
- Unit test request validation without loading GPU model.
- GPU smoke test on RunPod:
  - `python scripts/smoke_load.py --model-dir /workspace/models/LongCat-Video`
- Expected: model loads or gives a clear CUDA OOM. If OOM, move immediately to Task 11 fallback plan.

### Task 5: Implement text-to-video generation function

Objective: Generate an MP4 from a prompt using LongCat T2V.

Files:
- Modify: `app/longcat_loader.py`
- Create: `app/video_io.py`
- Test: `tests/test_video_io.py`

Function signature:
- `generate_text_video(prompt, negative_prompt, height=480, width=832, num_frames=93, seed=42, use_distill=True, use_refine=False) -> Path`

Behavior:
- Create `torch.Generator(device=device)` and seed it.
- If `use_distill=True`:
  - enable `cfg_step_lora`
  - call `pipe.generate_t2v(... num_inference_steps=16, use_distill=True, guidance_scale=1.0, negative_prompt=None)`
  - disable LoRAs.
- Else:
  - call `pipe.generate_t2v(... num_inference_steps=50, guidance_scale=4.0)`.
- If `use_refine=True`:
  - enable `refinement_lora`
  - enable BSA
  - call `pipe.generate_refine(...)`
  - disable LoRAs and BSA
  - write at 30 fps.
- Else write at 15 fps.
- Use `torchvision.io.write_video` with libx264.

Verification:
- Unit test `video_io.write_mp4` with small random frames.
- RunPod smoke test:
  - prompt: `A red ball rolls across a wooden table, cinematic lighting.`
  - settings: 480x832, 93 frames, distill true, refine false.
  - Expected: valid mp4 in `/workspace/outputs`.

### Task 6: Implement image-to-video generation function

Objective: Generate an MP4 from an input image plus prompt.

Files:
- Modify: `app/longcat_loader.py`
- Modify: `app/video_io.py`
- Test: `tests/test_image_inputs.py`

Function signature:
- `generate_image_video(image_path, prompt, negative_prompt, resolution="480p", num_frames=93, seed=42, use_distill=True, use_refine=False) -> Path`

Behavior:
- Load image with `diffusers.utils.load_image`.
- Preserve original target image size for optional final resize, matching upstream demo behavior.
- Use `pipe.generate_i2v(...)` with `resolution` `480p` or `720p`.
- Follow same distill/refine LoRA handling as T2V.

Verification:
- Unit test file type validation.
- RunPod smoke test with a small JPG/PNG.
- Expected: valid mp4 in `/workspace/outputs`.

### Task 7: Add FastAPI request/response layer

Objective: Expose T2V/I2V generation through HTTP.

Files:
- Create: `app/main.py`
- Create: `app/schemas.py`
- Create: `app/job_store.py`
- Test: `tests/test_api_validation.py`

API details:
- `GET /health` returns `{ "ok": true }` without requiring model loaded.
- `GET /ready` returns CUDA availability, model loaded boolean, and model dir.
- `POST /v1/video/text` accepts JSON:
  - `prompt` required
  - `negative_prompt` optional
  - `height` default 480
  - `width` default 832
  - `num_frames` default 93
  - `seed` default 42
  - `use_distill` default true
  - `use_refine` default false
- `POST /v1/video/image` accepts multipart:
  - `image` required
  - `request` JSON form field or flat form fields.
- `GET /v1/jobs/{job_id}` returns status.
- `GET /v1/jobs/{job_id}/video` streams the mp4 when complete.

Initial execution model:
- Use a single background worker thread or process queue.
- Do not run multiple generations concurrently on one A6000.
- API returns `202 Accepted` with job_id immediately.

Verification:
- Start server without model in test mode:
  - `LONGCAT_SKIP_MODEL_LOAD=1 uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Run tests:
  - `pytest -q`
- Expected: validation routes pass.

### Task 8: Add RunPod pod startup scripts

Objective: Make pod startup reproducible.

Files:
- Create: `scripts/start_api.sh`
- Create: `scripts/runpod_pod_setup.md`

`start_api.sh` behavior:
- Export defaults:
  - `LONGCAT_MODEL_DIR=/workspace/models/LongCat-Video`
  - `LONGCAT_OUTPUT_DIR=/workspace/outputs`
  - `LONGCAT_HOST=0.0.0.0`
  - `LONGCAT_PORT=8000`
  - `PYTHONPATH=/opt/LongCat-Video:$PYTHONPATH`
- Verify model files before starting.
- Start Uvicorn:
  - `uvicorn app.main:app --host "$LONGCAT_HOST" --port "$LONGCAT_PORT" --workers 1`

RunPod pod settings:
- GPU: RTX A6000.
- Container image: built image from Task 2.
- Container disk: at least 50 GiB.
- Network volume: 150-250 GiB mounted at `/workspace`.
- Expose HTTP port 8000.
- Environment:
  - `LONGCAT_MODEL_DIR=/workspace/models/LongCat-Video`
  - `LONGCAT_OUTPUT_DIR=/workspace/outputs`

Verification:
- `curl http://POD_HOST:8000/health`
- `curl http://POD_HOST:8000/ready`
- Expected: ready shows CUDA true and model_loaded true after warmup.

### Task 9: Benchmark A6000 viability

Objective: Decide whether single A6000 is production-feasible.

Files:
- Create: `scripts/benchmark.py`
- Create: `docs/benchmarks.md`

Benchmark matrix:
1. T2V 480p distill no refine.
2. T2V 480p normal no refine.
3. T2V 480p distill + refine.
4. I2V 480p distill no refine.
5. I2V 720p distill no refine, if memory allows.

Metrics to record:
- Cold model load time.
- First generation wall time.
- Warm generation wall time.
- Peak VRAM from `torch.cuda.max_memory_allocated()` and `nvidia-smi`.
- Output duration/fps/resolution.
- Whether OOM occurred.

Decision gates:
- If 480p distill peak VRAM fits with at least 2 GiB headroom: proceed with A6000 single-GPU tier.
- If normal/refine OOMs: keep those disabled on A6000 and document them as 2-GPU or larger-GPU features.
- If even 480p distill OOMs: move to 2x A6000 context parallel or a larger VRAM GPU.

### Task 10: Add production safeguards

Objective: Prevent runaway jobs and bad inputs.

Files:
- Modify: `app/schemas.py`
- Modify: `app/main.py`
- Create: `app/security.py`

Safeguards:
- Max prompt length: start with 2,000 characters.
- Allowed image types: PNG/JPEG/WebP.
- Max upload size: start with 20 MiB.
- Clamp T2V dimensions to multiples of 8 and a safe max; start with 480x832 defaults.
- Clamp num_frames to upstream default 93 until benchmarks prove otherwise.
- One job at a time per GPU.
- Job timeout with graceful failure status.
- Clean old uploads/outputs by age or disk threshold.

Verification:
- Tests for invalid dimensions, too-large prompt, missing image, unsupported type.
- Manual test that a second request queues rather than runs concurrently.

### Task 11: Add 2-GPU fallback path if A6000 single-GPU is insufficient

Objective: Provide a known path for full-quality or OOM workloads.

Files:
- Create: `scripts/run_t2v_torchrun.sh`
- Create: `scripts/run_i2v_torchrun.sh`
- Create: `docs/multi_gpu.md`

Fallback commands based on upstream docs:
- T2V:
  - `torchrun --nproc_per_node=2 /opt/LongCat-Video/run_demo_text_to_video.py --context_parallel_size=2 --checkpoint_dir=/workspace/models/LongCat-Video`
- I2V:
  - `torchrun --nproc_per_node=2 /opt/LongCat-Video/run_demo_image_to_video.py --context_parallel_size=2 --checkpoint_dir=/workspace/models/LongCat-Video`

Service approach for multi-GPU:
- Keep the FastAPI pod service for 1-GPU direct pipeline calls.
- For 2-GPU workflows, either:
  - create a separate worker service launched under `torchrun`, or
  - queue jobs to subprocess scripts with JSON-configurable prompts/images.
- Do not mix torch distributed initialization into the first single-process API until needed.

Verification:
- Run upstream torchrun examples on a 2x A6000 pod.
- Record benchmark deltas in `docs/benchmarks.md`.

### Task 12: Add optional RunPod Serverless handler

Objective: Convert the stable pod worker into a serverless endpoint.

Files:
- Create: `runpod/handler.py`
- Create: `runpod/test_input_text.json`
- Create: `runpod/test_input_image.json`
- Create: `docs/runpod_serverless.md`

Handler behavior:
- Load model once at container startup/global scope.
- Accept JSON job input with mode `text` or `image`.
- For image jobs, accept a URL or base64 image; download/decode to temp file.
- Return either:
  - small metadata plus a presigned/uploaded video URL, or
  - base64 only for very small test clips, not production.

Serverless warning:
- Do not rely on cold-start model download.
- Either bake model weights into the image, which creates a very large image, or mount a RunPod network volume if supported by the chosen deployment mode.
- Keep max concurrency at 1 per worker.

Verification:
- Run local handler test.
- Deploy test endpoint.
- Submit one T2V distill job.
- Confirm generated video is retrievable.

---

## Milestone acceptance criteria

Milestone A: Pod smoke test
- Model files downloaded to `/workspace/models/LongCat-Video`.
- API starts on port 8000.
- `/health` and `/ready` return success.
- One 480p T2V distill job completes and returns an MP4.

Milestone B: I2V workflow
- Image upload route accepts PNG/JPEG.
- One 480p I2V distill job completes and returns an MP4.

Milestone C: A6000 benchmark decision
- Benchmarks recorded for T2V/I2V distill and normal/refine attempts.
- Clear decision documented: single A6000 tier vs 2x A6000/full-quality tier.

Milestone D: Production hardening
- Input validation tests pass.
- Queue prevents concurrent GPU jobs.
- Output cleanup policy exists.
- Basic error reporting returns actionable messages.

Milestone E: Optional serverless
- Serverless handler deployed only if cold-start/storage strategy is acceptable.

---

## Initial recommended settings

Use these for the first successful A6000 run:

Text-to-video:
- height: 480
- width: 832
- num_frames: 93
- use_distill: true
- use_refine: false
- num_inference_steps: 16
- guidance_scale: 1.0
- fps: 15

Image-to-video:
- resolution: 480p
- num_frames: 93
- use_distill: true
- use_refine: false
- num_inference_steps: 16
- guidance_scale: 1.0
- fps: 15

Move to normal/refine only after benchmark headroom is confirmed.

---

## Key risks and mitigations

1. A6000 VRAM risk
   - Risk: Full model + text encoder + VAE + LoRA/refine may exceed 48 GiB.
   - Mitigation: Start with 480p distill, no compile, no refine, concurrency=1. Benchmark. Use 2x A6000 context parallel if needed.

2. Cold start / model download risk
   - Risk: 77.6 GiB model download makes cold starts slow and brittle.
   - Mitigation: Use persistent RunPod network volume and a verification script.

3. flash-attn build risk
   - Risk: flash-attn can fail if CUDA/PyTorch/compiler versions mismatch.
   - Mitigation: Pin CUDA 12.4, PyTorch 2.6.0+cu124, flash-attn 2.7.4.post1, install ninja/packaging/psutil first.

4. API timeout risk
   - Risk: Video jobs take minutes.
   - Mitigation: asynchronous job API; do not keep client request open for generation.

5. Multi-GPU complexity risk
   - Risk: upstream demo uses torch distributed for multi-GPU.
   - Mitigation: keep single-GPU API simple; implement separate torchrun worker only if benchmarks require it.

6. Output storage growth
   - Risk: MP4 outputs and temp files fill the network volume.
   - Mitigation: add cleanup by age, job count, or disk usage threshold.

---

## Commands for the first RunPod manual validation

After starting an A6000 pod and attaching a network volume at `/workspace`:

```bash
cd /workspace
git clone --single-branch --branch main https://github.com/meituan-longcat/LongCat-Video
cd LongCat-Video

conda create -n longcat-video python=3.10 -y
conda activate longcat-video
pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
pip install ninja psutil packaging
pip install flash_attn==2.7.4.post1
pip install -r requirements.txt
pip install "huggingface_hub[hf_xet]" hf_xet

HF_XET_HIGH_PERFORMANCE=1 hf download meituan-longcat/LongCat-Video --local-dir /workspace/models/LongCat-Video

torchrun run_demo_text_to_video.py --checkpoint_dir=/workspace/models/LongCat-Video
```

If the final command OOMs on A6000, retry without the full demo path by using the service implementation's 480p distill-only call, then escalate to 2x A6000 if needed.
