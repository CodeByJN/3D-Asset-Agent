"""Concept image -> raw 3D model: a queue that sends images (or prompts) to Hunyuan3D in the background.

    q = Queue(home)
    job = q.submit(image="concepts/crate.png", name="crate")   # returns at once
    q.jobs()                                                   # queued / generating / raw / failed

Each finished job leaves assets/_raw/<name>/raw.glb (plus the reference image). That raw mesh is what
Claude opens in the Blender MCP server to inspect, clean up and export for Roblox. Jobs run one at a
time (one GPU), in the order they were submitted; the list survives restarts in assets/_raw/jobs.json.
"""
import json
import shutil
import threading
import time
import traceback
from pathlib import Path

from . import generators


class Queue:
    def __init__(self, home: Path):
        self.dir = Path(home) / "_raw"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.file = self.dir / "jobs.json"
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self._jobs = json.loads(self.file.read_text()) if self.file.exists() else []
        for j in self._jobs:  # a restart interrupted these: run them again
            if j["status"] == "generating":
                j["status"] = "queued"
        self.thread = None

    def _save(self):
        self.file.write_text(json.dumps(self._jobs, indent=1))

    def submit(self, image: str | None = None, prompt: str | None = None, name: str | None = None,
               backend: str = "auto", textured: bool = False, seed: int = 1234, background: bool = True) -> dict:
        """Add a job. background=False leaves it for drain() (the CLI runs jobs in its own process)."""
        if not image and not prompt:
            raise ValueError("give an image (concept art) or a prompt")
        if image and not Path(image).exists():
            raise FileNotFoundError(image)
        name = name or (Path(image).stem if image else "_".join(prompt.lower().split()[:3]))
        name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
        with self.lock:
            taken = {j["name"] for j in self._jobs}
            base, k = name, 2
            while name in taken:
                name, k = f"{base}_{k}", k + 1
            job = {"id": len(self._jobs) + 1, "name": name, "image": str(Path(image).resolve()) if image else None,
                   "prompt": prompt, "backend": backend, "textured": textured, "seed": seed,
                   "status": "queued", "submitted": time.time()}
            self._jobs.append(job)
            self._save()
        if background:
            self.start()
        return dict(job)

    def jobs(self, active_only: bool = False) -> list[dict]:
        with self.lock:
            return [dict(j) for j in self._jobs if not active_only or j["status"] in ("queued", "generating")]

    def job(self, key) -> dict:
        with self.lock:
            for j in self._jobs:
                if j["name"] == key or str(j["id"]) == str(key):
                    return dict(j)
        raise KeyError(f"no job {key}")

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
        self.wake.set()

    def _next(self):
        with self.lock:
            for j in self._jobs:
                if j["status"] == "queued":
                    j["status"] = "generating"
                    j["started"] = time.time()
                    self._save()
                    return j
        return None

    def _run(self):
        while True:
            j = self._next()
            if j is None:
                self.wake.clear()
                if not self.wake.wait(5):
                    if not any(x["status"] == "queued" for x in self.jobs()):
                        return
                continue
            self.process(j)

    def drain(self):
        """Run every queued job here, in order, yielding each as it finishes."""
        while (j := self._next()) is not None:
            yield self.process(j)

    def process(self, j: dict):
        """Generate one job's raw mesh (runs on the queue thread; also callable directly)."""
        out = self.dir / j["name"]
        try:
            gen = generators.generate(generators.get(j["backend"]), prompt=j["prompt"], image=j["image"],
                                      textured=j["textured"], seed=j["seed"])
            out.mkdir(parents=True, exist_ok=True)
            raw = out / ("raw" + Path(gen.mesh).suffix.lower())
            shutil.copy(gen.mesh, raw)
            if j["image"]:
                shutil.copy(j["image"], out / ("ref" + Path(j["image"]).suffix.lower()))
            update = {"status": "raw", "raw": str(raw), "seconds": round(time.time() - j["started"])}
        except Exception as e:  # noqa: BLE001 - recorded on the job
            update = {"status": "failed", "error": f"{type(e).__name__}: {' '.join(str(e).split())}"[:300],
                      "trace": traceback.format_exc()[-800:]}
        with self.lock:
            for x in self._jobs:
                if x["id"] == j["id"]:
                    x.update(update)
            self._save()
        return self.job(j["id"])


def describe(j: dict) -> str:
    s = f"#{j['id']} {j['name']}: {j['status']}"
    if j["status"] == "raw":
        s += f" ({j.get('seconds', '?')}s) -> {j['raw']}"
    elif j["status"] == "failed":
        s += f" - {j['error']}"
    elif j["status"] == "generating":
        s += f" ({time.time() - j.get('started', time.time()):.0f}s so far)"
    return s
