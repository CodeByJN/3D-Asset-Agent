"""Free backend: public Hugging Face Spaces.

text  -> image : black-forest-labs/FLUX.1-schnell   (the Hunyuan Space has text-to-3D disabled)
image -> 3D    : tencent/Hunyuan3D-2  /shape_generation (untextured) or /generation_all (textured)

Works anonymously; set HF_TOKEN (free account) for a larger daily GPU quota.
"""
import os
import shutil
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from .base import GenResult, Generator

IMAGE_SPACE = "black-forest-labs/FLUX.1-schnell"
SHAPE_SPACE = "tencent/Hunyuan3D-2"
# Hunyuan reads the image as the object's front; asking for a front view keeps texture projection aligned.
PROMPT_SUFFIX = ", single object, front view, centered, full object in frame, plain white background, game asset"


def _path(x) -> str:
    """Gradio returns files as a path, a {'path'|'value': path} dict, or a tuple."""
    if isinstance(x, (list, tuple)):
        x = x[0]
    if isinstance(x, dict):
        x = x.get("path") or x.get("value")
    return str(x)


def _one_line(e: Exception) -> str:
    msg = " ".join(str(e).split())
    if "quota" in msg.lower():
        msg += " (set HF_TOKEN from a free Hugging Face account for more daily GPU time)"
    return f"{type(e).__name__}: {msg}"[:300]


class HFSpaces(Generator):
    name = "hf"

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("HF_TOKEN")
        self._pool = ThreadPoolExecutor(max_workers=2)
        self._jobs: dict[str, Future] = {}

    def _client(self, space):
        from gradio_client import Client
        return Client(space, token=self.token, verbose=False)

    def _run(self, prompt, image, textured=False, seed=1234, steps=30, octree_resolution=256):
        from gradio_client import handle_file
        if not image:
            out = self._client(IMAGE_SPACE).predict(
                prompt=prompt + PROMPT_SUFFIX, seed=seed, randomize_seed=False, width=1024, height=1024,
                num_inference_steps=4, api_name="/infer")
            image = _path(out)
        res = self._client(SHAPE_SPACE).predict(
            caption=None, image=handle_file(image), mv_image_front=None, mv_image_back=None,
            mv_image_left=None, mv_image_right=None, steps=steps, guidance_scale=5.0, seed=seed,
            octree_resolution=octree_resolution, check_box_rembg=True, num_chunks=8000, randomize_seed=False,
            api_name="/generation_all" if textured else "/shape_generation")
        mesh = _path(res[1] if textured else res[0])
        stats = res[3] if textured else res[2]
        return mesh, image, stats, textured

    def submit(self, prompt=None, image=None, **opts) -> str:
        job = uuid.uuid4().hex[:12]
        self._jobs[job] = self._pool.submit(self._run, prompt, image, **opts)
        return job

    def poll(self, job: str) -> str:
        f = self._jobs[job]
        if not f.done():
            return "running"
        return f"error: {_one_line(f.exception())}" if f.exception() else "done"

    def download(self, job: str, dest: Path) -> GenResult:
        mesh, image, stats, textured = self._jobs.pop(job).result()
        m = dest / f"mesh{Path(mesh).suffix}"
        shutil.copy(mesh, m)
        i = dest / f"image{Path(image).suffix}"
        shutil.copy(image, i)
        return GenResult(m, i, textured, {"faces": stats.get("number_of_faces") if isinstance(stats, dict) else None})
