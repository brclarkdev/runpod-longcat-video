import json
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional
from app.schemas import JobStatus


class JobStore:
    def __init__(self, job_dir: Path):
        self.job_dir = job_dir
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._jobs: Dict[str, dict] = {}

    def create(self, mode: str, payload: dict) -> str:
        job_id = uuid.uuid4().hex
        record = {
            "job_id": job_id,
            "mode": mode,
            "status": JobStatus.queued.value,
            "created_at": time.time(),
            "updated_at": time.time(),
            "payload": payload,
            "output_path": None,
            "video_url": None,
            "object_key": None,
            "s3_uri": None,
            "error": None,
        }
        with self._lock:
            self._jobs[job_id] = record
        self._write(record)
        return job_id

    def update(self, job_id: str, **kwargs) -> None:
        with self._lock:
            record = self._jobs[job_id]
            record.update(kwargs)
            record["updated_at"] = time.time()
            copy = dict(record)
        self._write(copy)

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            if job_id in self._jobs:
                return dict(self._jobs[job_id])
        path = self.job_dir / f"{job_id}.json"
        if path.exists():
            return json.loads(path.read_text())
        return None

    def _write(self, record: dict) -> None:
        path = self.job_dir / f"{record['job_id']}.json"
        path.write_text(json.dumps(record, indent=2, sort_keys=True))
