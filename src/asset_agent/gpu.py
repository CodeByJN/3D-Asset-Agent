"""Hunyuan3D-2 (shape only) on your own NVIDIA GPU: detect, install, serve to this machine or to others.

Texturing is ours (project/flat/bake), so Hunyuan's texture model and its CUDA build are skipped.
"""
import os
import secrets
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config

REPO = "https://github.com/Tencent-Hunyuan/Hunyuan3D-2"
MODELS = {  # name -> (model_path, subfolder); shape VRAM ~5 GB (mini) / ~6 GB (full)
    "mini": ("tencent/Hunyuan3D-2mini", "hunyuan3d-dit-v2-mini-turbo"),
    "full": ("tencent/Hunyuan3D-2", "hunyuan3d-dit-v2-0-turbo"),
}
MIN_VRAM_GB = 6
LAUNCHER = Path(__file__).with_name("hy_serve.py")


class SetupError(RuntimeError):
    pass


@dataclass
class GPU:
    name: str
    vram_gb: float
    cap: tuple[int, int] | None  # CUDA compute capability, e.g. (6, 1) for a 1080 Ti

    def __str__(self):
        cap = f" sm_{self.cap[0]}{self.cap[1]}" if self.cap else ""
        return f"{self.name} {self.vram_gb:.0f}GB{cap}"


def parse_gpu(line: str) -> GPU:
    """One nvidia-smi csv line: name, memory.total (MiB)[, compute_cap]."""
    f = [x.strip() for x in line.split(",")]
    cap = tuple(int(x) for x in f[2].split(".")) if len(f) > 2 and "." in f[2] else None
    return GPU(f[0], round(float(f[1]) / 1024, 1), cap)


def detect() -> GPU | None:
    """The NVIDIA GPU with the most VRAM, or None."""
    for fields in ("name,memory.total,compute_cap", "name,memory.total"):  # old drivers lack compute_cap
        try:
            p = subprocess.run(["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if p.returncode == 0 and p.stdout.strip():
            return max((parse_gpu(l) for l in p.stdout.strip().splitlines()), key=lambda g: g.vram_gb)
    return None


def torch_index(cap) -> str:
    """cu126 still supports Pascal (10-series); Blackwell (50-series, sm_100+) needs cu128."""
    return "cu128" if cap and cap[0] >= 10 else "cu126"


def pick_model(vram_gb: float) -> str:
    return "full" if vram_gb >= 10 else "mini"


def venv_python(d: Path) -> Path:
    return d / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def default_dir() -> Path:
    return config.path().parent / "Hunyuan3D-2"


def _run(cmd, **kw):
    print("$ " + " ".join(map(str, cmd)), flush=True)
    if subprocess.run([str(c) for c in cmd], **kw).returncode:
        raise SetupError(f"failed: {' '.join(map(str, cmd))}")


def setup(d: Path | None = None, model: str | None = None) -> str:
    """Install Hunyuan3D-2 with PyTorch wheels that match this GPU. Safe to re-run."""
    gpu = detect()
    if not gpu:
        raise SetupError("no NVIDIA GPU found (nvidia-smi failed); use backend='hf' (free) instead")
    if gpu.vram_gb < MIN_VRAM_GB:
        raise SetupError(f"{gpu} has under {MIN_VRAM_GB}GB VRAM; use backend='hf' (free) instead")
    uv, git = shutil.which("uv"), shutil.which("git")
    if not (uv and git):
        raise SetupError("needs uv and git on PATH")
    model = model or pick_model(gpu.vram_gb)
    d = Path(d or config.load().get("hunyuan_dir") or default_dir()).expanduser().resolve()
    print(f"GPU: {gpu} -> model {model}, torch {torch_index(gpu.cap)}, folder {d}")
    if not (d / "gradio_app.py").exists():
        _run([git, "clone", "--depth", "1", REPO, d])
    py = venv_python(d)
    if not py.exists():
        _run([uv, "venv", "--python", "3.10", d / ".venv"])
    pip = [uv, "pip", "install", "--python", py]
    _run([*pip, "torch", "torchvision", "--index-url", f"https://download.pytorch.org/whl/{torch_index(gpu.cap)}"])
    _run([*pip, "-r", d / "requirements.txt"])  # torch is already satisfied, so it stays on the wheels above
    _run([*pip, "-e", d])
    _run([py, "-c", "import torch; assert torch.cuda.is_available(), 'CUDA not available'; "
                    "print('torch sees', torch.cuda.get_device_name(0))"])
    config.save(hunyuan_dir=str(d), model=model)
    return f"ok: Hunyuan3D-2 ({model}) installed in {d}. Start it with: asset-agent serve"


def serve_cmd(d: Path, model: str, host: str, port: int, vram_gb: float | None, flashvdm: bool = True) -> list:
    path, sub = MODELS[model]
    cmd = [venv_python(d), LAUNCHER, "--model_path", path, "--subfolder", sub, "--disable_tex",
           "--host", host, "--port", str(port), "--cache-path", d / "gradio_cache"]
    if vram_gb is None or vram_gb < 12:
        cmd.append("--low_vram_mode")
    if flashvdm:
        cmd.append("--enable_flashvdm")
    return cmd


def lan_addresses() -> list[str]:
    """This machine's LAN address and, if Tailscale is running, its tailnet address."""
    out = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the outbound interface
            out.append(s.getsockname()[0])
    except OSError:
        pass
    if ts := shutil.which("tailscale"):
        try:
            p = subprocess.run([ts, "ip", "-4"], capture_output=True, text=True, timeout=5)
            out += [l.strip() for l in p.stdout.splitlines() if l.strip()]
        except (OSError, subprocess.TimeoutExpired):
            pass
    return out


def serve(remote: bool = False, port: int = 8080, model: str | None = None, flashvdm: bool = True) -> int:
    """Run the shape server in the foreground (Ctrl+C stops it).

    remote=False: this machine only, no key. remote=True: listens on the network and requires the key.
    """
    c = config.load()
    d = Path(c.get("hunyuan_dir") or default_dir())
    if not venv_python(d).exists():
        raise SetupError(f"Hunyuan3D-2 not installed in {d}; run: asset-agent setup")
    model = model or c.get("model", "mini")
    gpu = detect()
    env = dict(os.environ)
    if remote:
        key = c.get("key") or config.save(key=secrets.token_urlsafe(18))["key"]
        env["HUNYUAN_KEY"] = key
        print("Remote mode: other machines connect with the key below. Keep it private.")
        for ip in lan_addresses() or ["<this-pc-ip>"]:
            print(f"  asset-agent connect http://{ip}:{port} --key {key}")
        print(f"  browser: http://<address>:{port}/?key={key}")
    else:
        env.pop("HUNYUAN_KEY", None)
    cmd = serve_cmd(d, model, "0.0.0.0" if remote else "127.0.0.1", port, gpu.vram_gb if gpu else None, flashvdm)
    print(f"Starting Hunyuan3D-2 ({model}) on port {port}; the first start downloads the model. Ctrl+C stops it.",
          flush=True)
    try:
        return subprocess.run([str(x) for x in cmd], cwd=d, env=env).returncode
    except KeyboardInterrupt:
        return 0

