# RunPod LongCat Deployment Notes

## Network Volume

Created/verified: 2026-05-24

- Name: `longcat-video-primary`
- ID: `06j8ee9sbn`
- Datacenter: `US-KS-2`
- Size: 250 GB

## Hydration Pod

Created: 2026-05-24

- Name: `longcat-hydrate-once`
- ID: `9nsnmqb3f716sn`
- Datacenter: `US-KS-2`
- Network volume: `longcat-video-primary` / `06j8ee9sbn`
- Volume mount: `/workspace`
- Image: `ubuntu:22.04`
- Status at creation: `RUNNING`
- Cost reported by RunPod API: `$0.82/hr`

The Pod startup command hydrates LongCat directly into:

```text
/workspace/models/LongCat-Video
```

It writes:

```text
/workspace/longcat_hydration.log
/workspace/longcat_hydration.done      # success marker
/workspace/longcat_hydration.failed    # failure marker
```

Expected model size: about 77.6 GiB.

## Monitoring locally

```bash
set -a
. /Users/brandonclark/.hermes/.env
set +a
python3 - <<'PY'
import json, os, urllib.request
key=os.environ['RUNPOD_API_KEY']
req=urllib.request.Request(
    'https://rest.runpod.io/v1/pods/9nsnmqb3f716sn?includeNetworkVolume=true&includeMachine=true',
    headers={'Authorization':f'Bearer {key}','Accept':'application/json'},
)
with urllib.request.urlopen(req, timeout=60) as r:
    p=json.load(r)
print(json.dumps({k:p.get(k) for k in ['id','name','desiredStatus','costPerHr','machineId','networkVolume']}, indent=2))
PY
```

Hydration log reported completion on 2026-05-24:

```text
/usr/local/lib/python3.10/dist-packages/huggingface_hub/constants.py:277: FutureWarning: The `HF_HUB_ENABLE_HF_TRANSFER` environment variable is deprecated as 'hf_transfer' is not used anymore. Please use `HF_XET_HIGH_PERFORMANCE` instead to enable high performance transfer with Xet.
Warning: `huggingface-cli` is deprecated and no longer works. Use `hf` instead.
512    /workspace/models/LongCat-Video
LongCat hydration complete
```

Notes:

- The final `du` line confirms `/workspace/models/LongCat-Video` exists, but the reported `512` appears to be block-oriented or incomplete relative to the expected ~77.6 GiB model size; verify with `du -sh /workspace/models/LongCat-Video` from an attached Pod before treating the volume as production-ready.
- Future bootstrap scripts should use `HF_XET_HIGH_PERFORMANCE=1` and the `hf download ...` CLI instead of deprecated `HF_HUB_ENABLE_HF_TRANSFER=1` and `huggingface-cli`.
- As of the API poll after that false-positive completion, the temporary hydration Pod still had `desiredStatus: RUNNING` and was still billable at `$0.82/hr`.
- The false-positive Pod was deleted before the final verification Pod was created.

## Production readiness verification

Verified: 2026-05-25T03:04:57Z

A fresh RunPod verification Pod was created with the same network volume attached:

- Name: `longcat-hydrate-verify`
- ID: `qqi3cfvq8wiiz2`
- GPU: RTX A6000
- Image: `runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04`
- Cost reported by RunPod API: `$0.49/hr`
- Network volume: `longcat-video-primary` / `06j8ee9sbn`
- Volume mount: `/workspace`

The corrected hydration used:

```bash
HF_XET_HIGH_PERFORMANCE=1 hf download meituan-longcat/LongCat-Video --local-dir /workspace/models/LongCat-Video
```

Verification report written on the volume:

```text
/workspace/longcat_volume_verification.json
/workspace/longcat_volume.production_ready
/workspace/longcat_hydration_v2.done
```

Verified result:

```json
{
  "model_dir": "/workspace/models/LongCat-Video",
  "timestamp_utc": "2026-05-25T03:04:57Z",
  "size_bytes": 83309805529,
  "size_gib": 77.588,
  "file_count": 62,
  "required_missing": [],
  "required_present": [
    "dit/diffusion_pytorch_model.safetensors.index.json",
    "text_encoder/model.safetensors.index.json",
    "vae/diffusion_pytorch_model.safetensors",
    "scheduler/scheduler_config.json",
    "tokenizer/tokenizer.json",
    "lora/cfg_step_lora.safetensors",
    "lora/refinement_lora.safetensors"
  ]
}
```

Manual verification from the attached Pod also returned:

```text
78G    /workspace/models/LongCat-Video
62     files
```

All temporary hydration/verification Pods have been deleted after verification. `runpodctl pod list --all` returned an empty list, so no billable Pods were left running by this hydration step.

Operational note: a RunPod API key was temporarily injected into an intermediate Pod environment to let that Pod self-stop/status-mark during hydration. Rotate the RunPod API key if that exposure is unacceptable under the account's security policy.

## Runtime paths

Pod:

```text
RUNPOD_VOLUME_ROOT=/workspace
LONGCAT_MODEL_DIR=/workspace/models/LongCat-Video
```

Serverless:

```text
RUNPOD_VOLUME_ROOT=/runpod-volume
LONGCAT_MODEL_DIR=/runpod-volume/models/LongCat-Video
```

## Service image

Built and pushed: 2026-05-25

- Repository: `https://github.com/brclarkdev/runpod-longcat-video`
- Image: `ghcr.io/brclarkdev/runpod-longcat-video:latest`
- Verified image tags:
  - `latest`
  - `a51807eefc7e` or newer from the `main` branch build
- Build workflow: `.github/workflows/build-image.yml`

The image keeps model weights out of the container and reads the hydrated RunPod network volume at runtime.

## Pod API smoke test

Verified: 2026-05-25T04:47Z

A normal Pod was used before Serverless because it gives faster API visibility for first-runtime failures.

Final successful smoke Pod:

- Name: `longcat-pod-smoke-80gb`
- ID: `kt1jj3t6r0qrbo`
- GPU: `NVIDIA A100-SXM4-80GB`
- Datacenter: `US-KS-2`
- Image: `ghcr.io/brclarkdev/runpod-longcat-video:latest`
- Network volume: `06j8ee9sbn`
- Volume mount: `/workspace`
- API proxy: `https://kt1jj3t6r0qrbo-8000.proxy.runpod.net`
- Cost reported by RunPod API: `$1.49/hr`
- Cleanup: Pod deleted after the smoke test.

Readiness check returned:

```json
{
  "ok": true,
  "skip_model_load": false,
  "load_model_on_startup": false,
  "model_loaded": false,
  "model_dir": "/workspace/models/LongCat-Video",
  "model_dir_exists": true,
  "production_ready": true,
  "output_dir": "/workspace/outputs"
}
```

Successful text-to-video smoke request:

```json
{
  "prompt": "A red ball rolls across a wooden table, cinematic lighting.",
  "height": 480,
  "width": 832,
  "num_frames": 93,
  "seed": 123,
  "use_distill": true,
  "use_refine": false
}
```

Result:

```json
{
  "job_id": "c8cfe9fdcb104c1cb07eadf499aa4fcc",
  "status": "completed",
  "output_path": "/workspace/outputs/c8cfe9fdcb104c1cb07eadf499aa4fcc/output.mp4"
}
```

Capacity/runtime lesson:

- A `NVIDIA L40` Pod (`si6phkafh8s769`, deleted) started the API successfully but failed generation at 480p/93 frames with CUDA OOM after using about 44 GiB. Treat RTX A6000/L40-class 48 GB GPUs as not validated for the current full 480p/93-frame LongCat scaffold.
- The validated initial target for this image and request shape is 1x `NVIDIA A100-SXM4-80GB`.

## Serverless endpoint

Created and smoke-tested: 2026-05-25T04:58:53Z

Template:

- Name: `longcat-video-serverless-a100`
- ID: `9re9ivkicj`
- Image: `ghcr.io/brclarkdev/runpod-longcat-video:latest`
- Container disk: 30 GB
- Serverless: true
- Environment:

```text
MODE_TO_RUN=serverless
RUNPOD_VOLUME_ROOT=/runpod-volume
LONGCAT_MODEL_DIR=/runpod-volume/models/LongCat-Video
LONGCAT_OUTPUT_DIR=/runpod-volume/outputs
LONGCAT_JOB_DIR=/runpod-volume/jobs
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

Endpoint:

- Name: `longcat-video-a100-us-ks-2`
- ID: `ie54y9szieajfb`
- GPU: `NVIDIA A100-SXM4-80GB`
- GPU count: 1
- Datacenter: `US-KS-2`
- Network volume: `06j8ee9sbn`
- Workers min/max: `0/1`
- Idle timeout: 60 seconds
- Execution timeout: 1200 seconds
- Autoscale: request count threshold 1

Serverless smoke request was submitted to:

```text
POST https://api.runpod.ai/v2/ie54y9szieajfb/run
```

Request body:

```json
{
  "input": {
    "mode": "text",
    "prompt": "A red ball rolls across a wooden table, cinematic lighting.",
    "height": 480,
    "width": 832,
    "num_frames": 93,
    "seed": 321,
    "use_distill": true,
    "use_refine": false
  }
}
```

RunPod job result:

```json
{
  "id": "3804687d-c16c-4222-afc8-de9b6215b1c1-u2",
  "status": "COMPLETED",
  "delayTime": 113638,
  "executionTime": 469217,
  "workerId": "vrp31hssmoqqqa",
  "output": {
    "job_id": "4ea498903e3092f9",
    "status": "completed",
    "output_path": "/runpod-volume/outputs/4ea498903e3092f9/output.mp4"
  }
}
```

Use async status polling for realistic jobs:

```bash
curl -H "Authorization: Bearer $RUNPOD_API_KEY" \
  https://api.runpod.ai/v2/ie54y9szieajfb/status/<runpod_job_id>
```

## Cleanup state after deployment

Checked: 2026-05-25T04:58:53Z

- `runpodctl pod list --all` returned `[]`; the temporary smoke Pods were deleted.
- The Serverless endpoint remains intentionally active as the service entrypoint, with `workersMin=0` and `idleTimeout=60`, so it should scale down when idle.
- The network volume `06j8ee9sbn` remains intentionally active because it stores the hydrated LongCat model and generated outputs.

## Production API caveat

The current service can either return an on-volume output path or upload the MP4 to S3-compatible object storage and return a `video_url`. Enable object storage with:

```text
LONGCAT_OUTPUT_DELIVERY=s3
LONGCAT_S3_BUCKET=06j8ee9sbn
LONGCAT_S3_ENDPOINT_URL=https://s3api-us-ks-2.runpod.io
LONGCAT_S3_REGION=US-KS-2
LONGCAT_S3_ADDRESSING_STYLE=path
AWS_ACCESS_KEY_ID=<access-key>
AWS_SECRET_ACCESS_KEY=<secret-key>
```

For RunPod's S3-compatible network-volume API, `LONGCAT_S3_BUCKET` is the network volume ID. The S3 credentials must be a RunPod S3 API key created in the RunPod console; the regular RunPod API key is not enough. Optional `LONGCAT_S3_PUBLIC_BASE_URL` returns CDN/public URLs instead of presigned URLs.

The deployed Serverless template has the non-secret RunPod S3 location values staged, but `LONGCAT_OUTPUT_DELIVERY=s3`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY` are intentionally not enabled until S3 API credentials are provided and a smoke request verifies the returned `video_url`. Existing generated outputs remain on the RunPod network volume until uploaded separately.
