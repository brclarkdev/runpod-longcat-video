# RunPod LongCat Deployment Notes

## Network Volume

Created/verified: 2026-05-24

- Name: `longcat-video-primary`
- ID: `06j8ee9sbn`
- Datacenter: `US-KS-2`
- Size: 250 GB

## Next step: hydrate the volume

Launch a temporary RunPod Secure Cloud Pod in `US-KS-2` with network volume `longcat-video-primary` attached.

Inside that Pod:

```bash
cd /workspace
# Clone or copy this repo into the Pod, then:
cd runpod-longcat-video
bash scripts/hydrate_longcat_volume.sh
```

The hydration script will download LongCat directly into:

```text
/workspace/models/LongCat-Video
```

Expected model size: about 77.6 GiB.

After hydration succeeds, terminate the temporary Pod but keep the network volume.

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
