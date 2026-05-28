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

    def _generator(self, seed: int):
        import torch
        generator = torch.Generator(device=self.device)
        generator.manual_seed(seed)
        return generator

    def _frames_to_pil(self, frames):
        import numpy as np
        from PIL import Image
        return [Image.fromarray((frames[i] * 255).astype(np.uint8)) for i in range(frames.shape[0])]

    def _generate_t2v_frames(self, prompt: str, negative_prompt: Optional[str], height: int, width: int, num_frames: int, seed: int, use_distill: bool):
        generator = self._generator(seed)
        if use_distill:
            self.pipe.dit.enable_loras(["cfg_step_lora"])
            output = self.pipe.generate_t2v(
                prompt=prompt,
                negative_prompt=None,
                height=height,
                width=width,
                num_frames=num_frames,
                num_inference_steps=16,
                use_distill=True,
                guidance_scale=1.0,
                generator=generator,
            )[0]
            self.pipe.dit.disable_all_loras()
        else:
            output = self.pipe.generate_t2v(
                prompt=prompt,
                negative_prompt=negative_prompt or config.DEFAULT_NEGATIVE_PROMPT,
                height=height,
                width=width,
                num_frames=num_frames,
                num_inference_steps=50,
                guidance_scale=4.0,
                generator=generator,
            )[0]
        self.torch_gc()
        return output

    def _generate_vc_frames(self, video, prompt: str, negative_prompt: Optional[str], resolution: str, num_frames: int, num_cond_frames: int, seed: int, use_distill: bool):
        generator = self._generator(seed)
        if use_distill:
            self.pipe.dit.enable_loras(["cfg_step_lora"])
            output = self.pipe.generate_vc(
                video=video,
                prompt=prompt,
                resolution=resolution,
                num_frames=num_frames,
                num_cond_frames=num_cond_frames,
                num_inference_steps=16,
                use_distill=True,
                guidance_scale=1.0,
                generator=generator,
                use_kv_cache=True,
                offload_kv_cache=False,
                enhance_hf=False,
            )[0]
            self.pipe.dit.disable_all_loras()
        else:
            output = self.pipe.generate_vc(
                video=video,
                prompt=prompt,
                negative_prompt=negative_prompt or config.DEFAULT_NEGATIVE_PROMPT,
                resolution=resolution,
                num_frames=num_frames,
                num_cond_frames=num_cond_frames,
                num_inference_steps=50,
                guidance_scale=4.0,
                generator=generator,
                use_kv_cache=True,
                offload_kv_cache=False,
                enhance_hf=True,
            )[0]
        self.torch_gc()
        return output

    def _refine_frames(self, prompt: str, stage1_video, seed: int, video=None, num_cond_frames: int = 0, spatial_refine_only: bool = False):
        generator = self._generator(seed)
        self.pipe.dit.enable_loras(["refinement_lora"])
        self.pipe.dit.enable_bsa()
        output = self.pipe.generate_refine(
            video=video,
            prompt=prompt,
            stage1_video=stage1_video,
            num_cond_frames=num_cond_frames,
            num_inference_steps=50,
            generator=generator,
            spatial_refine_only=spatial_refine_only,
        )[0]
        self.pipe.dit.disable_all_loras()
        self.pipe.dit.disable_bsa()
        self.torch_gc()
        return output

    def generate_text_video(self, job_id: str, prompt: str, negative_prompt: Optional[str] = None, height: int = 480, width: int = 832, num_frames: int = 93, seed: int = 42, use_distill: bool = True, use_refine: bool = False) -> Path:
        if config.SKIP_MODEL_LOAD:
            return self._write_placeholder(job_id, "text")
        from app.video_io import write_mp4

        output = self._generate_t2v_frames(prompt, negative_prompt, height, width, num_frames, seed, use_distill)
        fps = 15
        if use_refine:
            stage1_video = self._frames_to_pil(output)
            del output
            output = self._refine_frames(prompt=prompt, stage1_video=stage1_video, seed=seed)
            fps = 30
        return write_mp4(output, self.output_dir / job_id / "output.mp4", fps=fps)

    def generate_image_video(self, job_id: str, image_path: Path, prompt: str, negative_prompt: Optional[str] = None, resolution: str = "480p", num_frames: int = 93, seed: int = 42, use_distill: bool = True, use_refine: bool = False) -> Path:
        if config.SKIP_MODEL_LOAD:
            return self._write_placeholder(job_id, "image")
        import torch
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
            stage1_video = self._frames_to_pil(output)
            del output
            output = self._refine_frames(prompt=prompt, stage1_video=stage1_video, seed=seed, video=input_image, num_cond_frames=1)
            fps = 30
        return write_mp4(output, self.output_dir / job_id / "output.mp4", fps=fps)

    def generate_video_continuation(self, job_id: str, video_path: Path, prompt: str, negative_prompt: Optional[str] = None, resolution: str = "480p", num_frames: int = 93, num_cond_frames: int = 13, seed: int = 42, use_distill: bool = True, use_refine: bool = False, spatial_refine_only: bool = False) -> Path:
        if config.SKIP_MODEL_LOAD:
            return self._write_placeholder(job_id, "video_continuation")
        import cv2
        import numpy as np
        from PIL import Image
        from diffusers.utils import load_video
        from app.video_io import write_mp4

        video = load_video(str(video_path))
        cap = cv2.VideoCapture(str(video_path))
        current_fps = cap.get(cv2.CAP_PROP_FPS) or 15
        cap.release()
        target_fps = 15
        stride = max(1, round(current_fps / target_fps))
        video = video[::stride]
        target_size = video[0].size

        output = self._generate_vc_frames(video, prompt, negative_prompt, resolution, num_frames, num_cond_frames, seed, use_distill)
        output_processed = self._frames_to_pil(output)
        output_processed = [frame.resize(target_size, Image.BICUBIC) for frame in output_processed]
        final_frames = video + output_processed[num_cond_frames:]
        fps = 15

        if use_refine:
            cur_num_cond_frames = num_cond_frames if spatial_refine_only else num_cond_frames * 2
            stage1_video = self._frames_to_pil(output)
            del output
            target_fps = 30
            stride = max(1, round(current_fps / target_fps))
            condition_video = load_video(str(video_path))[::stride]
            refined = self._refine_frames(
                prompt=prompt,
                stage1_video=stage1_video,
                seed=seed,
                video=condition_video,
                num_cond_frames=cur_num_cond_frames,
                spatial_refine_only=spatial_refine_only,
            )
            refined = self._frames_to_pil(refined)
            refined = [frame.resize(target_size, Image.BICUBIC) for frame in refined]
            final_frames = condition_video + refined[cur_num_cond_frames:]
            fps = 15 if spatial_refine_only else 30

        return write_mp4(np.array(final_frames), self.output_dir / job_id / "output.mp4", fps=fps)

    def generate_long_video(self, job_id: str, prompt: str, negative_prompt: Optional[str] = None, height: int = 480, width: int = 832, num_frames: int = 93, num_cond_frames: int = 13, num_segments: int = 1, seed: int = 42, use_distill: bool = True, use_refine: bool = False, spatial_refine_only: bool = False) -> Path:
        if config.SKIP_MODEL_LOAD:
            return self._write_placeholder(job_id, "long_video")
        import numpy as np
        from PIL import Image
        from app.video_io import write_mp4

        initial = self._generate_t2v_frames(prompt, negative_prompt, height, width, num_frames, seed, use_distill)
        current_video = self._frames_to_pil(initial)
        all_frames = list(current_video)
        target_size = current_video[0].size

        for segment_idx in range(num_segments):
            output = self._generate_vc_frames(
                current_video,
                prompt,
                negative_prompt,
                "480p",
                num_frames,
                num_cond_frames,
                seed + segment_idx + 1,
                use_distill,
            )
            new_video = self._frames_to_pil(output)
            new_video = [frame.resize(target_size, Image.BICUBIC) for frame in new_video]
            all_frames.extend(new_video[num_cond_frames:])
            current_video = new_video
            del output

        fps = 15
        final_frames = all_frames
        if use_refine:
            cur_condition_video = None
            cur_num_cond_frames = 0
            start_id = 0
            all_refine_frames = []
            for segment_idx in range(num_segments + 1):
                chunk = all_frames[start_id:start_id + num_frames]
                output_refine = self._refine_frames(
                    prompt="",
                    stage1_video=chunk,
                    seed=seed + 1000 + segment_idx,
                    video=cur_condition_video,
                    num_cond_frames=cur_num_cond_frames,
                    spatial_refine_only=spatial_refine_only,
                )
                new_video = self._frames_to_pil(output_refine)
                all_refine_frames.extend(new_video[cur_num_cond_frames:])
                cur_condition_video = new_video
                cur_num_cond_frames = num_cond_frames if spatial_refine_only else num_cond_frames * 2
                start_id = start_id + num_frames - num_cond_frames
                del output_refine
            final_frames = all_refine_frames
            fps = 15 if spatial_refine_only else 30

        return write_mp4(np.array(final_frames), self.output_dir / job_id / "output.mp4", fps=fps)

    def generate_interactive_video(self, job_id: str, prompts: list[str], negative_prompt: Optional[str] = None, height: int = 480, width: int = 832, num_frames: int = 93, num_cond_frames: int = 13, seed: int = 42, use_distill: bool = True, use_refine: bool = False, spatial_refine_only: bool = False) -> Path:
        if config.SKIP_MODEL_LOAD:
            return self._write_placeholder(job_id, "interactive")
        return self._generate_prompt_sequence(
            job_id=job_id,
            prompts=prompts,
            negative_prompt=negative_prompt,
            height=height,
            width=width,
            num_frames=num_frames,
            num_cond_frames=num_cond_frames,
            seed=seed,
            use_distill=use_distill,
            use_refine=use_refine,
            spatial_refine_only=spatial_refine_only,
        )

    def _generate_prompt_sequence(self, job_id: str, prompts: list[str], negative_prompt: Optional[str], height: int, width: int, num_frames: int, num_cond_frames: int, seed: int, use_distill: bool, use_refine: bool, spatial_refine_only: bool) -> Path:
        import numpy as np
        from PIL import Image
        from app.video_io import write_mp4

        initial = self._generate_t2v_frames(prompts[0], negative_prompt, height, width, num_frames, seed, use_distill)
        current_video = self._frames_to_pil(initial)
        all_frames = list(current_video)
        target_size = current_video[0].size

        for segment_idx, prompt in enumerate(prompts[1:]):
            output = self._generate_vc_frames(
                current_video,
                prompt,
                negative_prompt,
                "480p",
                num_frames,
                num_cond_frames,
                seed + segment_idx + 1,
                use_distill,
            )
            new_video = self._frames_to_pil(output)
            new_video = [frame.resize(target_size, Image.BICUBIC) for frame in new_video]
            all_frames.extend(new_video[num_cond_frames:])
            current_video = new_video
            del output

        fps = 15
        final_frames = all_frames
        if use_refine:
            cur_condition_video = None
            cur_num_cond_frames = 0
            start_id = 0
            all_refine_frames = []
            for segment_idx in range(len(prompts)):
                chunk = all_frames[start_id:start_id + num_frames]
                output_refine = self._refine_frames(
                    prompt="",
                    stage1_video=chunk,
                    seed=seed + 1000 + segment_idx,
                    video=cur_condition_video,
                    num_cond_frames=cur_num_cond_frames,
                    spatial_refine_only=spatial_refine_only,
                )
                new_video = self._frames_to_pil(output_refine)
                all_refine_frames.extend(new_video[cur_num_cond_frames:])
                cur_condition_video = new_video
                cur_num_cond_frames = num_cond_frames if spatial_refine_only else num_cond_frames * 2
                start_id = start_id + num_frames - num_cond_frames
                del output_refine
            final_frames = all_refine_frames
            fps = 15 if spatial_refine_only else 30

        return write_mp4(np.array(final_frames), self.output_dir / job_id / "output.mp4", fps=fps)

    def _write_placeholder(self, job_id: str, mode: str) -> Path:
        path = self.output_dir / job_id / "output.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"LONGCAT_SKIP_MODEL_LOAD placeholder for {mode} job {job_id}\n")
        return path
