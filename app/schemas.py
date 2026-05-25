from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class TextVideoRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    negative_prompt: Optional[str] = Field(default=None, max_length=2000)
    height: int = 480
    width: int = 832
    num_frames: int = 93
    seed: int = 42
    use_distill: bool = True
    use_refine: bool = False

    @field_validator("height", "width")
    @classmethod
    def dimensions_are_safe(cls, value: int) -> int:
        if value < 256 or value > 1024:
            raise ValueError("dimension must be between 256 and 1024")
        if value % 8 != 0:
            raise ValueError("dimension must be divisible by 8")
        return value

    @field_validator("num_frames")
    @classmethod
    def frames_are_safe(cls, value: int) -> int:
        if value != 93:
            raise ValueError("num_frames is fixed at 93 for the initial LongCat service")
        return value


class ImageVideoRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    negative_prompt: Optional[str] = Field(default=None, max_length=2000)
    resolution: str = "480p"
    num_frames: int = 93
    seed: int = 42
    use_distill: bool = True
    use_refine: bool = False
    image_url: Optional[str] = None
    image_base64: Optional[str] = None

    @field_validator("resolution")
    @classmethod
    def resolution_supported(cls, value: str) -> str:
        if value not in {"480p", "720p"}:
            raise ValueError("resolution must be 480p or 720p")
        return value

    @field_validator("num_frames")
    @classmethod
    def frames_are_safe(cls, value: int) -> int:
        if value != 93:
            raise ValueError("num_frames is fixed at 93 for the initial LongCat service")
        return value


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    output_path: Optional[str] = None
    video_url: Optional[str] = None
    object_key: Optional[str] = None
    error: Optional[str] = None
