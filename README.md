# RunPod LongCat-Video Service

Network-volume-first RunPod deployment scaffold for LongCat-Video text-to-video and image-to-video workflows.

Core rule: do not download LongCat weights locally and do not bake them into Docker. Hydrate one RunPod Network Volume once from inside RunPod, then attach that volume to Pods or Serverless workers.

## Paths

Pods mount the network volume at:

```text
/workspace
```

Serverless workers mount it at:

```text
/runpod-volume
```

The app uses `RUNPOD_VOLUME_ROOT` to normalize this:

```bash
# Pod
RUNPOD_VOLUME_ROOT=/workspace

# Serverless
RUNPOD_VOLUME_ROOT=/runpod-volume

LONGCAT_MODEL_DIR=$RUNPOD_VOLUME_ROOT/models/LongCat-Video
HF_HOME=$RUNPOD_VOLUME_ROOT/cache/huggingface
LONGCAT_OUTPUT_DIR=$RUNPOD_VOLUME_ROOT/outputs
LONGCAT_JOB_DIR=$RUNPOD_VOLUME_ROOT/jobs
```

## One-time volume hydration

On a temporary RunPod Pod with the network volume attached:

```bash
bash scripts/hydrate_longcat_volume.sh
```

Important: run this only on a RunPod Pod with the network volume attached. It downloads about 77.6 GiB. The script refuses to run locally unless you explicitly set `RUNPOD_VOLUME_ROOT` and `LONGCAT_ALLOW_LOCAL_HYDRATION=1` for testing.

This downloads `meituan-longcat/LongCat-Video` directly into the RunPod volume.

## RunPod volume management

The user requested `UNPOD_API_KEY`; the scripts also accept `RUNPOD_API_KEY` as a fallback.

List volumes:

```bash
python scripts/runpod_volume.py list
```

Ensure the project volume exists:

```bash
python scripts/runpod_volume.py ensure --name longcat-video-primary --size 250 --datacenter US-KS-2
```

## Pod API mode

```bash
MODE_TO_RUN=pod_api bash scripts/start_api.sh
```

## Serverless mode

Set container command to:

```bash
MODE_TO_RUN=serverless bash scripts/start_api.sh
```

## Health checks

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

## Text-to-video request

```bash
curl -X POST http://localhost:8000/v1/video/text   -H 'Content-Type: application/json'   -d '{"prompt":"A red ball rolls across a wooden table, cinematic lighting.","use_distill":true,"use_refine":false}'
```
