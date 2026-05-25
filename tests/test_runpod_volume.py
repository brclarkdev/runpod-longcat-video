import os
import subprocess
import sys


def test_runpod_volume_requires_key(monkeypatch):
    env = dict(os.environ)
    env.pop("UNPOD_API_KEY", None)
    env.pop("RUNPOD_API_KEY", None)
    result = subprocess.run([sys.executable, "scripts/runpod_volume.py", "list"], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "UNPOD_API_KEY" in result.stderr or "UNPOD_API_KEY" in result.stdout
