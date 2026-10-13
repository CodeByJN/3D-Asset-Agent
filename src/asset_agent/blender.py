"""Run pipeline steps in a headless Blender process (blender -b -P worker.py)."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WORKER = Path(__file__).with_name("worker.py")


class BlenderError(RuntimeError):
    pass


def _installed() -> list[Path]:
    """Blender installs in the usual places for this OS, newest version first."""
    if sys.platform == "win32":
        roots = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        pats = ("Blender Foundation/Blender*/blender.exe", "Programs/Blender Foundation/Blender*/blender.exe",
                "Steam/steamapps/common/Blender/blender.exe")
        found = [p for r in filter(None, roots) for pat in pats for p in Path(r).glob(pat)]
    elif sys.platform == "darwin":
        found = [p for base in (Path("/Applications"), Path.home() / "Applications")
                 for p in base.glob("Blender*.app/Contents/MacOS/Blender")]
    else:
        found = [Path(p) for p in ("/usr/bin/blender", "/snap/bin/blender", "/usr/local/bin/blender")]
        found += list(Path.home().glob("blender*/blender")) + list(Path("/opt").glob("blender*/blender"))

    def version(p):
        return [int(x) for x in re.findall(r"\d+", p.parent.name)] or [0]
    return sorted((p for p in found if p.exists()), key=version, reverse=True)


def find_blender() -> str:
    """BLENDER_EXE, else `blender` on PATH, else the newest standard install."""
    exe = os.environ.get("BLENDER_EXE") or shutil.which("blender") or next(map(str, _installed()), None)
    if not exe or not Path(exe).exists():
        raise BlenderError(f"Blender not found{f' at {exe}' if exe else ''}: install Blender 4.2+ "
                           "(https://www.blender.org/download/) or set BLENDER_EXE to its executable")
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
