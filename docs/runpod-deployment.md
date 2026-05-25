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

When hydration is complete, the container should exit. Verify the volume from a Pod terminal or via RunPod volume file access, then terminate/delete the temporary hydration Pod if it is still present.

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
