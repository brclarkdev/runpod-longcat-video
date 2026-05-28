import os
from pathlib import Path
from typing import Optional

from app import config


class LongCatService:
    def __init__(self, checkpoint_dir: Path = config.LONGCAT_MODEL_DIR, output_dir: Path = config.LONGCAT_OUTPUT_DIR):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pipe = None
        self.device = "cuda"
        self._loaded = False
        if not config.SKIP_MODEL_LOAD:
            self.load()

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load(self):
        import torch
        from transformers import AutoTokenizer, UMT5EncoderModel
        from longcat_video.context_parallel import context_parallel_util
        from longcat_video.pipeline_longcat_video import LongCatVideoPipeline
        from longcat_video.modules.scheduling_flow_match_euler_discrete import FlowMatchEulerDiscreteScheduler
        from longcat_video.modules.autoencoder_kl_wan import AutoencoderKLWan
        from longcat_video.modules.longcat_video_dit import LongCatVideoTransformer3DModel

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for LongCat model serving")
        torch_dtype = torch.bfloat16
        cp_split_hw = context_parallel_util.get_optimal_split(1)
        tokenizer = AutoTokenizer.from_pretrained(self.checkpoint_dir, subfolder="tokenizer", torch_dtype=torch_dtype)
        text_encoder = UMT5EncoderModel.from_pretrained(self.checkpoint_dir, subfolder="text_encoder", torch_dtype=torch_dtype)
        vae = AutoencoderKLWan.from_pretrained(self.checkpoint_dir, subfolder="vae", torch_dtype=torch_dtype)
        scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(self.checkpoint_dir, subfolder="scheduler", torch_dtype=torch_dtype)
        dit = LongCatVideoTransformer3DModel.from_pretrained(self.checkpoint_dir, subfolder="dit", cp_split_hw=cp_split_hw, torch_dtype=torch_dtype)
        self.pipe = LongCatVideoPipeline(tokenizer=tokenizer, text_encoder=text_encoder, vae=vae, scheduler=scheduler, dit=dit)
        self.pipe.to(self.device)
        self.pipe.dit.load_lora(os.path.join(self.checkpoint_dir, "lora/cfg_step_lora.safetensors"), "cfg_step_lora")
        self.pipe.dit.load_lora(os.path.join(self.checkpoint_dir, "lora/refinement_lora.safetensors"), "refinement_lora")
        self._loaded = True
        return self

    def torch_gc(self):
        import torch
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()

    def generate_text_video(self, job_id: str, prompt: str, negative_prompt: Optional[str] = None, height: int = 480, width: int = 832, num_frames: int = 93, seed: int = 42, use_distill: bool = True, use_refine: bool = False) -> Path:
        if config.SKIP_MODEL_LOAD:
            return self._write_placeholder(job_id, "text")
        import numpy as np
        import torch
        from PIL import Image
        from app.video_io import write_mp4

        generator = torch.Generator(device=self.device)
        generator.manual_seed(seed)
        if use_distill:
            self.pipe.dit.enable_loras(["cfg_step_lora"])
            output = self.pipe.generate_t2v(prompt=prompt, negative_prompt=None, height=height, width=width, num_frames=num_frames, num_inference_steps=16, use_distill=True, guidance_scale=1.0, generator=generator)[0]
            self.pipe.dit.disable_all_loras()
        else:
            output = self.pipe.generate_t2v(prompt=prompt, negative_prompt=negative_prompt or config.DEFAULT_NEGATIVE_PROMPT, height=height, width=width, num_frames=num_frames, num_inference_steps=50, guidance_scale=4.0, generator=generator)[0]
        self.torch_gc()
        fps = 15
        if use_refine:
            self.pipe.dit.enable_loras(["refinement_lora"])
            stage1_video = [Image.fromarray((output[i] * 255).astype(np.uint8)) for i in range(output.shape[0])]
            del output
            self.pipe.dit.enable_bsa()
            output = self.pipe.generate_refine(prompt=prompt, stage1_video=stage1_video, num_inference_steps=50, generator=generator)[0]
            self.pipe.dit.disable_all_loras()
            self.pipe.dit.disable_bsa()
            self.torch_gc()
            fps = 30
        return write_mp4(output, self.output_dir / job_id / "output.mp4", fps=fps)

    def generate_image_video(self, job_id: str, image_path: Path, prompt: str, negative_prompt: Optional[str] = None, resolution: str = "480p", num_frames: int = 93, seed: int = 42, use_distill: bool = True, use_refine: bool = False) -> Path:
        if config.SKIP_MODEL_LOAD:
            return self._write_placeholder(job_id, "image")
        import numpy as np
        import torch
        from PIL import Image
        from diffusers.utils import load_image
        from app.video_io import write_mp4

        input_image = load_image(str(image_path))
        generator = torch.Generator(device=self.device)
        generator.manual_seed(seed)
        if use_distill:
            self.pipe.dit.enable_loras(["cfg_step_lora"])
            output = self.pipe.generate_i2v(image=input_image, prompt=prompt, negative_prompt=None, resolution=resolution, num_frames=num_frames, num_inference_steps=16, use_distill=True, guidance_scale=1.0, generator=generator)[0]
            self.pipe.dit.disable_all_loras()
        else:
            output = self.pipe.generate_i2v(image=input_image, prompt=prompt, negative_prompt=negative_prompt or config.DEFAULT_NEGATIVE_PROMPT, resolution=resolution, num_frames=num_frames, num_inference_steps=50, guidance_scale=4.0, generator=generator)[0]
        self.torch_gc()
        fps = 15
        if use_refine:
            self.pipe.dit.enable_loras(["refinement_lora"])
            stage1_video = [Image.fromarray((output[i] * 255).astype(np.uint8)) for i in range(output.shape[0])]
            del output
            self.pipe.dit.enable_bsa()
            output = self.pipe.generate_refine(image=input_image, prompt=prompt, stage1_video=stage1_video, num_cond_frames=1, num_inference_steps=50, generator=generator)[0]
            self.pipe.dit.disable_all_loras()
            self.pipe.dit.disable_bsa()
            self.torch_gc()
            fps = 30
        return write_mp4(output, self.output_dir / job_id / "output.mp4", fps=fps)

    # === New generation modes (stubs - implement pipeline calls when available) ===

    def generate_video_continuation(self, job_id: str, prompt: str, input_video: str, negative_prompt: Optional[str] = None, height: int = 480, width: int = 832, num_frames: int = 93, seed: int = 42, use_distill: bool = True, use_refine: bool = False) -> Path:
        if config.SKIP_MODEL_LOAD:
            return self._write_placeholder(job_id, "video_continuation")
        # TODO: Implement using pipeline continuation method when available
        raise NotImplementedError("Video continuation not yet implemented in LongCatService")

    def generate_long_video(self, job_id: str, prompt: str, negative_prompt: Optional[str] = None, height: int = 480, width: int = 832, num_frames: int = 93, seed: int = 42, use_distill: bool = True, use_refine: bool = False) -> Path:
        if config.SKIP_MODEL_LOAD:
            return self._write_placeholder(job_id, "long_video")
        # TODO: Implement long video generation when pipeline supports it
        raise NotImplementedError("Long video generation not yet implemented in LongCatService")

    def generate_interactive_video(self, job_id: str, prompt: str, negative_prompt: Optional[str] = None, height: int = 480, width: int = 832, num_frames: int = 93, seed: int = 42, use_distill: bool = True, use_refine: bool = False) -> Path:
        if config.SKIP_MODEL_LOAD:
            return self._write_placeholder(job_id, "interactive")
        # TODO: Implement interactive video generation when pipeline supports it
        raise NotImplementedError("Interactive video generation not yet implemented in LongCatService")

    def _write_placeholder(self, job_id: str, mode: str) -> Path:
        path = self.output_dir / job_id / "output.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"LONGCAT_SKIP_MODEL_LOAD placeholder for {mode} job {job_id}\n")
        return path
