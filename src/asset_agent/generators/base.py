"""Generator interface: submit -> poll -> download, with results cached by request hash."""
import hashlib
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path



class GeneratorError(RuntimeError):
    pass


@dataclass
class GenResult:
    mesh: Path               # GLB
    image: Path | None       # the reference image the shape was made from (for texture projection)
    textured: bool
    meta: dict

    def summary(self) -> str:
        m = self.meta
        return f"gen {m['backend']} {'cached' if m.get('cached') else f'{m['seconds']}s'} faces={m.get('faces', '?')}"


class Generator:
    """Backends implement submit/poll/download. `generate` wraps them with caching."""
    name = "base"

    def submit(self, prompt: str | None = None, image: str | None = None, **opts) -> str:
        raise NotImplementedError

    def poll(self, job: str) -> str:
        """'running' | 'done' | 'error: <one line>'"""
        raise NotImplementedError

    def download(self, job: str, dest: Path) -> GenResult:
        raise NotImplementedError


def request_key(backend: str, prompt, image, opts: dict) -> str:
    img = hashlib.sha256(Path(image).read_bytes()).hexdigest() if image else None
    return hashlib.sha256(json.dumps([backend, prompt, img, opts], sort_keys=True).encode()).hexdigest()[:16]


def generate(gen: Generator, prompt=None, image=None, timeout=600, cache: Path | None = None, **opts) -> GenResult:
    """Blocking generate with a cache: the same request never runs (or costs) twice."""
    if not (prompt or image):
        raise GeneratorError("need a prompt or an image")
    dest = Path(cache or Path.cwd() / "library" / "cache") / request_key(gen.name, prompt, image, opts)
    meta_path = dest / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        img = dest / meta["image"] if meta.get("image") else None
        return GenResult(dest / meta["mesh"], img, meta["textured"], {**meta, "cached": True})
    t = time.time()
    job = gen.submit(prompt=prompt, image=image, **opts)
    while (state := gen.poll(job)) == "running":
        if time.time() - t > timeout:
            raise GeneratorError(f"{gen.name} timed out after {timeout}s")
        time.sleep(2)
    if state != "done":
        raise GeneratorError(state.removeprefix("error: "))
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    res = gen.download(job, tmp)
    res.meta.update(backend=gen.name, prompt=prompt, seconds=round(time.time() - t), textured=res.textured,
                    mesh=res.mesh.name, image=res.image.name if res.image else None)
    (tmp / "meta.json").write_text(json.dumps(res.meta, indent=1))
    shutil.rmtree(dest, ignore_errors=True)
    tmp.rename(dest)
    return GenResult(dest / res.mesh.name, dest / res.image.name if res.image else None, res.textured, res.meta)
