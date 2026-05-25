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

## Video delivery

By default, generated videos remain on the attached RunPod volume and responses include only an on-volume `output_path`.

For production/client access, enable S3-compatible object storage delivery. This works with AWS S3, Cloudflare R2, Backblaze B2, MinIO, and other S3-compatible providers.

For the hydrated RunPod network volume in `US-KS-2`, the S3-compatible target is:

```bash
LONGCAT_S3_BUCKET=06j8ee9sbn
LONGCAT_S3_ENDPOINT_URL=https://s3api-us-ks-2.runpod.io
LONGCAT_S3_REGION=US-KS-2
LONGCAT_S3_ADDRESSING_STYLE=path
```

RunPod S3 access requires a separate S3 API key from the RunPod console; the regular RunPod API key is not sufficient. RunPod's S3-compatible network-volume API does not support presigned URLs, so this target returns `s3_uri`/`object_key` for authenticated download instead of a public `video_url`.

Required environment:

```bash
LONGCAT_OUTPUT_DELIVERY=s3
LONGCAT_S3_BUCKET=<bucket-name>
AWS_ACCESS_KEY_ID=<access-key>
AWS_SECRET_ACCESS_KEY=<secret-key>
```

Common optional environment:

```bash
# Object key prefix. Defaults to longcat-outputs.
LONGCAT_S3_PREFIX=longcat-outputs

# Required for R2/B2/MinIO or any non-AWS S3-compatible endpoint.
LONGCAT_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
LONGCAT_S3_REGION=auto

# Presigned URL lifetime in seconds. Defaults to 86400.
LONGCAT_S3_PRESIGN_EXPIRES=86400

# If files are served through a public bucket/CDN, return this URL instead of presigning.
LONGCAT_S3_PUBLIC_BASE_URL=https://cdn.example.com/videos

# Optional for S3-compatible providers that require path-style addressing.
LONGCAT_S3_ADDRESSING_STYLE=path
```

Serverless completion responses then include delivery metadata:

```json
{
  "job_id": "...",
  "status": "completed",
  "output_path": "/runpod-volume/outputs/.../output.mp4",
  "video_url": "https://signed-download-url...",
  "object_key": "longcat-outputs/.../output.mp4",
  "s3_uri": "s3://bucket/longcat-outputs/.../output.mp4"
}
```

For RunPod S3 specifically, `video_url` is `null` because presigned URLs are unsupported. Download with authenticated S3 tooling instead:

```bash
aws s3 cp \
  --region US-KS-2 \
  --endpoint-url https://s3api-us-ks-2.runpod.io \
  s3://06j8ee9sbn/longcat-outputs/<job_id>/output.mp4 \
  ./output.mp4
```

For Pod API mode, `GET /v1/jobs/{job_id}` returns the same fields. The legacy `GET /v1/jobs/{job_id}/video` endpoint still serves the local volume file while the Pod is running.
