# RunPod LongCat-Video Network-Volume-First Implementation Plan

Goal: Build LongCat text-to-video and image-to-video workflows on RunPod while avoiding any local model download and minimizing repeated downloads inside RunPod.

Architecture: Use one RunPod Network Volume as the system of record for LongCat model weights, attach that volume to both development Pods and Serverless workers, and keep the Docker image dependency-only. Hydrate the volume exactly once from Hugging Face inside RunPod, then reuse it across Pods/workers/endpoints.

Key RunPod storage facts verified 2026-05-24 from RunPod docs:
- Network volumes persist independently from Pods/workers and retain data after compute terminates.
- Network volumes can be shared across RunPod products.
- For Pods, network volumes replace the default volume disk and usually mount at `/workspace`.
- For Serverless workers, network volumes mount at `/runpod-volume`.
- Network volumes must be attached during Pod deployment; they cannot be attached/detached later without deleting the Pod.
- Network volumes are only available for Pods in Secure Cloud.
- Serverless network volumes reduce cold starts by avoiding model re-downloads, but worker placement must use the volume's selected datacenter.
- RunPod exposes an S3-compatible API for managing network volume files without launching compute in supported regions.
- RunPod Cloud Sync can move Pod data to/from external cloud storage providers like AWS S3, GCS, Azure Blob, Backblaze B2, and Dropbox.

LongCat facts already verified:
- Upstream repo: https://github.com/meituan-longcat/LongCat-Video
- Model repo: https://huggingface.co/meituan-longcat/LongCat-Video
- Model weights are public and not gated.
- LongCat-Video files are about 77.6 GiB.
- Upstream pins CUDA 12.4-compatible PyTorch 2.6.0 and flash-attn 2.7.4.post1.

---

## Revised approach

Do not download LongCat model weights locally.
Do not bake model weights into the Docker image.
Do not benchmark A6000 as a separate milestone.
Do hydrate one RunPod network volume once.
Do reuse the same network volume for:
- interactive Pod development
- API Pod deployment
- Serverless endpoint workers
- output staging if needed

The only required local artifacts are:
- wrapper service source code
- Dockerfile
- deployment scripts
- optional tiny test images/prompts

---

## Recommended RunPod topology

Pick one Secure Cloud datacenter that has the GPU supply you expect to use. If you want to manage files without launching a Pod, choose a datacenter that supports RunPod S3-compatible Network Volume access.

Create one network volume:
- Name: `longcat-video-primary`
- Size: 250 GiB
- Purpose:
  - `/models/LongCat-Video` model weights
  - `/cache/huggingface` Hugging Face cache
  - `/outputs` generated videos, if not immediately uploaded elsewhere
  - `/jobs` job metadata, if using file-backed status

Why 250 GiB:
- LongCat model weights are about 77.6 GiB.
- You need extra space for HF cache temp files, generated outputs, logs, and future Avatar weights if desired.

## Storage layout

Use a path abstraction so the same container works on Pods and Serverless.

Environment variables:
- `RUNPOD_VOLUME_ROOT=/workspace` on Pods
- `RUNPOD_VOLUME_ROOT=/runpod-volume` on Serverless
- `LONGCAT_MODEL_DIR=$RUNPOD_VOLUME_ROOT/models/LongCat-Video`
- `HF_HOME=$RUNPOD_VOLUME_ROOT/cache/huggingface`
- `TRANSFORMERS_CACHE=$RUNPOD_VOLUME_ROOT/cache/huggingface/transformers`
- `HF_HUB_CACHE=$RUNPOD_VOLUME_ROOT/cache/huggingface/hub`
- `LONGCAT_OUTPUT_DIR=$RUNPOD_VOLUME_ROOT/outputs`
- `LONGCAT_JOB_DIR=$RUNPOD_VOLUME_ROOT/jobs`

Expected Pod paths:
- `/workspace/models/LongCat-Video`
- `/workspace/cache/huggingface`
- `/workspace/outputs`
- `/workspace/jobs`

Expected Serverless paths:
- `/runpod-volume/models/LongCat-Video`
- `/runpod-volume/cache/huggingface`
- `/runpod-volume/outputs`
- `/runpod-volume/jobs`

---

## RunPod services to use

### 1. Network Volumes

Primary service for model persistence.

Use for:
- model weights
- HF cache
- generated outputs when outputs need to persist after worker shutdown
- shared job metadata if using simple file-backed queues

Avoid:
- concurrent writes to the same paths from multiple workers
- using the same volume as a high-concurrency database

Concurrency rule:
- Model directory is read-only after hydration.
- Each worker writes to a unique output directory: `$LONGCAT_OUTPUT_DIR/$JOB_ID/`.
- Do not let workers write to the same file.

### 2. S3-compatible API for Network Volumes

Use for management without launching a Pod.

Use cases:
- list volume contents
- download selected generated MP4s
- upload small config files or prompt packs
- copy artifacts between external automation and RunPod volume

Do not use this as the main model hydration path from your local machine; that would still route 77.6 GiB through you. Hydrate from inside RunPod instead.

### 3. Temporary hydration Pod

Use a short-lived Pod only to populate the network volume.

Steps:
1. Create network volume in target datacenter.
2. Launch a temporary Secure Cloud Pod with that volume attached.
3. Run the Hugging Face download inside the Pod.
4. Verify model files.
5. Terminate the Pod, keep the network volume.

This downloads 77.6 GiB once from Hugging Face to RunPod, not to your local environment.

### 4. Pod-first development

Use a Pod attached to the same volume for interactive development.

Use for:
- validating dependency image
- testing model load
- debugging FastAPI service
- verifying T2V/I2V outputs

The same Docker image should support both modes:
- Pod mode: FastAPI or direct handler test
- Serverless mode: RunPod handler

### 5. Serverless endpoint with attached network volume

Use for production once the handler works on a Pod.

Use for:
- autoscaled text/image-to-video jobs
- persistent model access without per-worker download

Settings:
- attach the hydrated network volume under Advanced -> Network Volumes
- max concurrency: 1 per worker
- idle timeout tuned to keep hot workers alive during active work periods
- avoid cold-start downloads entirely

### 6. Cloud Sync / external S3

Use for output delivery, not model hydration unless you already have a LongCat mirror in object storage.

Recommended pattern:
- generated output lands in `$LONGCAT_OUTPUT_DIR/$JOB_ID/output.mp4`
- worker uploads MP4 to external S3/R2/B2 bucket
- API returns a signed URL
- cleanup policy deletes old local volume outputs

This keeps network volume growth under control.

---

## Implementation tasks

### Task 1: Create RunPod network volume

Objective: Create persistent RunPod storage before launching compute.

Console path:
- RunPod Console -> Storage -> New Network Volume

Settings:
- Name: `longcat-video-primary`
- Size: 250 GB
- Datacenter: choose a Secure Cloud datacenter that supports both your target GPU and S3-compatible API.

REST equivalent:
```bash
curl --request POST \
  --url https://rest.runpod.io/v1/networkvolumes \
  --header "Authorization: Bearer $RUNPOD_API_KEY" \
  --header "Content-Type: application/json" \
  --data '{
    "name": "longcat-video-primary",
    "size": 250,
    "dataCenterId": "US-KS-2"
  }'
```

Verification:
- Volume appears in RunPod Storage.
- Record volume ID and datacenter in deployment notes.

### Task 2: Hydrate model volume once from inside RunPod

Objective: Download LongCat weights directly into the network volume, not local disk.

Steps:
1. Deploy a temporary Secure Cloud Pod in the same datacenter.
2. Attach `longcat-video-primary` during Pod creation.
3. Open terminal in the Pod.
4. Run:

```bash
set -euo pipefail
export RUNPOD_VOLUME_ROOT=/workspace
export LONGCAT_MODEL_DIR=$RUNPOD_VOLUME_ROOT/models/LongCat-Video
export HF_HOME=$RUNPOD_VOLUME_ROOT/cache/huggingface
export HF_HUB_CACHE=$HF_HOME/hub

mkdir -p "$LONGCAT_MODEL_DIR" "$HF_HUB_CACHE"
python3 -m pip install -U "huggingface_hub[cli]"
huggingface-cli download meituan-longcat/LongCat-Video --local-dir "$LONGCAT_MODEL_DIR"

du -sh "$LONGCAT_MODEL_DIR"
find "$LONGCAT_MODEL_DIR" -maxdepth 3 -type f | wc -l
```

Expected:
- `du -sh` is roughly 78 GiB.
- Required files exist:
  - `$LONGCAT_MODEL_DIR/dit/diffusion_pytorch_model.safetensors.index.json`
  - `$LONGCAT_MODEL_DIR/text_encoder/model.safetensors.index.json`
  - `$LONGCAT_MODEL_DIR/vae/diffusion_pytorch_model.safetensors`
  - `$LONGCAT_MODEL_DIR/lora/cfg_step_lora.safetensors`
  - `$LONGCAT_MODEL_DIR/lora/refinement_lora.safetensors`

Then terminate the temporary Pod, not the volume.

### Task 3: Add volume verification script

Objective: Make every Pod/worker fail fast if the volume is missing or incomplete.

File:
- Create: `scripts/verify_longcat_volume.py`

Behavior:
- Read `LONGCAT_MODEL_DIR`.
- Check all required files.
- Print model directory size.
- Exit nonzero with clear instructions if missing files.

Required files:
```text
dit/diffusion_pytorch_model.safetensors.index.json
text_encoder/model.safetensors.index.json
vae/diffusion_pytorch_model.safetensors
scheduler/scheduler_config.json
tokenizer/tokenizer.json
lora/cfg_step_lora.safetensors
lora/refinement_lora.safetensors
```

Verification:
```bash
LONGCAT_MODEL_DIR=/workspace/models/LongCat-Video python scripts/verify_longcat_volume.py
```

### Task 4: Build dependency-only Docker image

Objective: Keep the image small enough to build/push reliably and avoid embedding 77.6 GiB of weights.

Files:
- Create: `docker/Dockerfile`
- Create: `docker/entrypoint.sh`
- Create: `docker/requirements-service.txt`

Docker image contains:
- OS packages
- Python 3.10
- CUDA/PyTorch/flash-attn dependencies
- upstream LongCat-Video code cloned into `/opt/LongCat-Video`
- service wrapper code copied into `/app`

Docker image does not contain:
- `/models/LongCat-Video`
- Hugging Face model files
- generated MP4 outputs

Required environment variables in entrypoint:
```bash
if [ -d /runpod-volume ]; then
  export RUNPOD_VOLUME_ROOT=${RUNPOD_VOLUME_ROOT:-/runpod-volume}
else
  export RUNPOD_VOLUME_ROOT=${RUNPOD_VOLUME_ROOT:-/workspace}
fi
export LONGCAT_MODEL_DIR=${LONGCAT_MODEL_DIR:-$RUNPOD_VOLUME_ROOT/models/LongCat-Video}
export HF_HOME=${HF_HOME:-$RUNPOD_VOLUME_ROOT/cache/huggingface}
export HF_HUB_CACHE=${HF_HUB_CACHE:-$HF_HOME/hub}
export LONGCAT_OUTPUT_DIR=${LONGCAT_OUTPUT_DIR:-$RUNPOD_VOLUME_ROOT/outputs}
export LONGCAT_JOB_DIR=${LONGCAT_JOB_DIR:-$RUNPOD_VOLUME_ROOT/jobs}
export PYTHONPATH=/opt/LongCat-Video:/app:$PYTHONPATH
```

Startup must run:
```bash
python /app/scripts/verify_longcat_volume.py
```

### Task 5: Make one dual-mode worker

Objective: Use the same code for Pod development and Serverless deployment.

Files:
- Create: `app/handler.py`
- Create: `app/api.py`
- Create: `app/longcat_service.py`

Modes:
- `MODE_TO_RUN=pod_api`: start FastAPI on port 8000.
- `MODE_TO_RUN=pod_test`: run one local test request and exit.
- `MODE_TO_RUN=serverless`: start `runpod.serverless.start(...)`.

Serverless handler input:
```json
{
  "input": {
    "mode": "text",
    "prompt": "A red ball rolls across a wooden table, cinematic lighting.",
    "seed": 42,
    "use_distill": true,
    "use_refine": false
  }
}
```

Image input options:
- preferred: `image_url` pointing to S3/R2/B2/RunPod S3 object
- acceptable for small tests: base64 image
- avoid huge API payloads

Output behavior:
- write MP4 to `$LONGCAT_OUTPUT_DIR/$JOB_ID/output.mp4`
- return metadata and either:
  - local volume path for Pod mode, or
  - uploaded object URL for production Serverless mode

### Task 6: Use object storage for outputs

Objective: Avoid filling the RunPod network volume with generated videos.

Recommended output flow:
1. Worker writes to `$LONGCAT_OUTPUT_DIR/$JOB_ID/output.mp4`.
2. Worker uploads MP4 to external object storage.
3. Worker returns signed URL or object key.
4. Cleanup job deletes old local output directories.

Supported options:
- AWS S3
- Cloudflare R2 via S3-compatible API
- Backblaze B2
- RunPod Network Volume S3 API for retrieving outputs directly from the volume

Environment variables:
```bash
OUTPUT_BACKEND=s3
S3_ENDPOINT_URL=...
S3_BUCKET=...
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_REGION=auto
```

### Task 7: Deploy Pod API attached to volume

Objective: Run persistent API service without model downloads.

RunPod Pod settings:
- Secure Cloud Pod
- Network Volume: `longcat-video-primary`
- Container image: dependency-only LongCat service image
- Expose HTTP port: 8000
- Env:
  - `MODE_TO_RUN=pod_api`
  - `RUNPOD_VOLUME_ROOT=/workspace`
  - `LONGCAT_MODEL_DIR=/workspace/models/LongCat-Video`

Startup validation:
- The entrypoint verifies the volume.
- Model loads from `/workspace/models/LongCat-Video`.
- No Hugging Face download happens at API startup.

Manual tests:
```bash
curl http://POD_HOST:8000/health
curl http://POD_HOST:8000/ready
curl -X POST http://POD_HOST:8000/v1/video/text \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"A red ball rolls across a wooden table, cinematic lighting.","use_distill":true,"use_refine":false}'
```

### Task 8: Deploy Serverless endpoint attached to volume

Objective: Use RunPod Serverless with no cold-start model download.

Endpoint settings:
- Container image: same dependency-only image
- Advanced -> Network Volumes: attach `longcat-video-primary`
- Env:
  - `MODE_TO_RUN=serverless`
  - `RUNPOD_VOLUME_ROOT=/runpod-volume`
  - `LONGCAT_MODEL_DIR=/runpod-volume/models/LongCat-Video`
- Max worker concurrency: 1
- Use an idle timeout that balances cost vs keeping the model warm.

Handler startup:
- verify model files under `/runpod-volume`
- load LongCat once globally
- process one job at a time

Test request:
```json
{
  "input": {
    "mode": "text",
    "prompt": "A red ball rolls across a wooden table, cinematic lighting.",
    "seed": 42,
    "use_distill": true,
    "use_refine": false
  }
}
```

Expected:
- No model download logs.
- Worker loads model from network volume.
- Output MP4 is written to volume and/or uploaded to object storage.

### Task 9: Cleanup and lifecycle management

Objective: Keep storage predictable.

Rules:
- Model directory is immutable after hydration.
- Outputs older than N days are deleted after upload.
- Temporary uploads are deleted after each job.
- Logs are rotated.

Create:
- `scripts/cleanup_outputs.py`

Suggested defaults:
- delete completed local outputs older than 48 hours
- keep failed job metadata for 7 days
- never delete `$LONGCAT_MODEL_DIR`

---

## What changed from the original plan

Removed:
- A6000 benchmarking milestone
- local model download assumptions
- any suggestion to bake model weights into Docker

Added:
- RunPod Network Volume as source of truth
- RunPod S3-compatible API usage
- Pod-first to Serverless dual-mode worker
- volume hydration Pod
- path abstraction for `/workspace` vs `/runpod-volume`
- object-storage output flow

---

## Immediate next actions

1. Create one `longcat-video-primary` network volume in a RunPod Secure Cloud datacenter.
2. Launch a temporary Pod with that volume attached.
3. Run the one-time Hugging Face download inside RunPod:

```bash
export RUNPOD_VOLUME_ROOT=/workspace
export LONGCAT_MODEL_DIR=$RUNPOD_VOLUME_ROOT/models/LongCat-Video
export HF_HOME=$RUNPOD_VOLUME_ROOT/cache/huggingface
export HF_HUB_CACHE=$HF_HOME/hub
mkdir -p "$LONGCAT_MODEL_DIR" "$HF_HUB_CACHE"
python3 -m pip install -U "huggingface_hub[cli]"
huggingface-cli download meituan-longcat/LongCat-Video --local-dir "$LONGCAT_MODEL_DIR"
du -sh "$LONGCAT_MODEL_DIR"
```

4. Terminate the hydration Pod, keep the volume.
5. Build and deploy the dependency-only service image.
6. Attach the same volume to Pod API or Serverless endpoint.
