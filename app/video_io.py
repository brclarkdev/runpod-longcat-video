from pathlib import Path
import numpy as np
import torch
from torchvision.io import write_video


def write_mp4(frames, output_path: Path, fps: int) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.array(frames)
    if arr.dtype != np.uint8:
        arr = (arr * 255).clip(0, 255).astype(np.uint8)
    tensor = torch.from_numpy(arr)
    write_video(str(output_path), tensor, fps=fps, video_codec="libx264", options={"crf": "18"})
    return output_path
