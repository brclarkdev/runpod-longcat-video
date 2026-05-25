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
- As of the latest API poll after completion, the temporary hydration Pod still had `desiredStatus: RUNNING` and was still billable at `$0.82/hr`; terminate/delete it after verifying the volume contents.

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
