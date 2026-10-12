"""Run pipeline steps in a headless Blender process (blender -b -P worker.py)."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

WORKER = Path(__file__).with_name("worker.py")
DEFAULT_EXE = r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"


class BlenderError(RuntimeError):
    pass


def find_blender() -> str:
    exe = os.environ.get("BLENDER_EXE") or shutil.which("blender") or DEFAULT_EXE
    if not Path(exe).exists():
        raise BlenderError(f"blender not found at {exe}; set BLENDER_EXE")
    return exe


def run_steps(steps: list[dict], timeout: int = 1800) -> list[dict]:
    """Run steps in one Blender process. Returns one result dict per step."""
    with tempfile.TemporaryDirectory() as td:
        job, out = Path(td) / "job.json", Path(td) / "result.json"
        job.write_text(json.dumps({"steps": steps, "result": str(out)}))
        proc = subprocess.run(
            [find_blender(), "-b", "--factory-startup", "-noaudio",
             "--python-exit-code", "1", "-P", str(WORKER), "--", str(job)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
        if not out.exists():
            tail = (proc.stderr.strip() or proc.stdout.strip()).splitlines()[-1:] or ["no output"]
            raise BlenderError(f"blender exited {proc.returncode}: {tail[0][:200]}")
        res = json.loads(out.read_text())
    if res.get("error"):
        raise BlenderError(res["error"])
    return res["results"]
