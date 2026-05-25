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
