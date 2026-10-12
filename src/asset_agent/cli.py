"""asset-agent: set up and run the GPU shape server, connect to one on another machine, check status."""
import argparse
import sys
from pathlib import Path

from . import config, gpu
from .blender import BlenderError, find_blender
from .generators import local_status


def status() -> str:
    c = config.load()
    try:
        blender = find_blender()
    except BlenderError as e:
        blender = f"not found ({e})"
    g = gpu.detect()
    d = c.get("hunyuan_dir")
    installed = d and gpu.venv_python(Path(d)).exists()
    server = local_status()
    lines = [
        f"config:   {config.path()}",
        f"blender:  {blender}",
        f"gpu:      {g or 'none (fine: use the free hf backend or a remote server)'}",
        f"hunyuan:  {f'{d} ({c.get('model', 'mini')})' if installed else 'not installed here (asset-agent setup)'}",
        f"server:   {config.hunyuan_url()} {server}{' (key set)' if config.hunyuan_key() else ''}",
        f"auto ->   {'local' if server == 'ok' else 'hf (free Spaces)'}",
    ]
    return "\n".join(lines)


def connect(url: str, key: str | None) -> str:
    if "://" not in url:
        url = "http://" + url
    config.save(url=url.rstrip("/"), key=key)
    s = local_status()
    hint = {"wrong key": " (check --key)", "offline": " (is `asset-agent serve --remote` running there?)"}
    return f"saved {config.hunyuan_url()}: {s}{hint.get(s, '')}"


def main(argv=None):
    p = argparse.ArgumentParser(prog="asset-agent", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="what is installed and which backend auto will use")
    s = sub.add_parser("setup", help="install Hunyuan3D-2 for this machine's NVIDIA GPU")
    s.add_argument("--dir", help="install folder (default ~/.asset-agent/Hunyuan3D-2)")
    s.add_argument("--model", choices=gpu.MODELS, help="default: full with 10GB+ VRAM, else mini")
    s = sub.add_parser("serve", help="run the shape server (Ctrl+C stops it)")
    s.add_argument("--remote", action="store_true", help="let other machines connect (requires a key)")
    s.add_argument("--port", type=int, default=8080)
    s.add_argument("--model", choices=gpu.MODELS)
    s.add_argument("--no-flashvdm", action="store_true", help="if the fast decoder errors on your GPU")
    s = sub.add_parser("connect", help="use a shape server on another machine")
    s.add_argument("url", help="e.g. http://192.168.1.50:8080")
    s.add_argument("--key", help="printed by `asset-agent serve --remote`")
    a = p.parse_args(argv)
    try:
        if a.cmd == "status":
            print(status())
        elif a.cmd == "setup":
            print(gpu.setup(a.dir, a.model))
        elif a.cmd == "serve":
            return gpu.serve(a.remote, a.port, a.model, not a.no_flashvdm)
        elif a.cmd == "connect":
            print(connect(a.url, a.key))
    except gpu.SetupError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
