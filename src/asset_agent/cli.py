"""asset-agent: check this machine (doctor), set up and run the GPU shape server, connect to one on another
machine, check status."""
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
    s = sub.add_parser("doctor", help="check everything the harness needs here and say what to fix")
    s.add_argument("--offline", action="store_true", help="skip connecting to Roblox Studio")
    sub.add_parser("studio-mcp", help="run Roblox Studio's MCP server over stdio (used by .mcp.json)")
    sub.add_parser("status", help="what is installed and which backend auto will use")
    s = sub.add_parser("generate", help="concept images -> raw meshes with Hunyuan3D (assets/_raw/<name>/raw.glb)")
    s.add_argument("images", nargs="*", help="concept image files")
    s.add_argument("--prompt", help="text instead of images")
    s.add_argument("--backend", default="auto", choices=["auto", "hf", "local"])
    s.add_argument("--textured", action="store_true", help="ask Hunyuan for its own texture too")
    sub.add_parser("jobs", help="the generate queue")
    s = sub.add_parser("job", help="asset studio jobs: the board, a job's stage, your thumbs up or down")
    s.add_argument("name", nargs="?", help="a job (none: the board)")
    s.add_argument("verdict", nargs="?", choices=["up", "down", "trace"], help="thumbs on its stage, or its trace")
    s.add_argument("--note", default="", help="what to change (down) or what's good (up)")
    s.add_argument("--back-to", help="down: redo from this earlier stage")
    s.add_argument("--stars", type=float, help="at review: rate the asset 1-10 too")
    s = sub.add_parser("quality", help="the quality vault (quality/): sync ratings into notes, export the dataset")
    s.add_argument("action", choices=["sync", "export", "pairs", "summary", "brief"])
    s.add_argument("category", nargs="?", default="prop", help="brief: prop, character, creature, vfx or animation")
    s.add_argument("--all", action="store_true", help="export, pairs: include notes not marked share: true")
    s = sub.add_parser("store", help="grade Creator Store models into the quality vault")
    s.add_argument("action", choices=["search", "gallery", "collect", "grade"])
    s.add_argument("arg", nargs="?", help="search: a query; gallery: a query (default: every ungraded one); "
                   "grade: a JSON file of grades")
    s.add_argument("-n", type=int, default=20, help="search, gallery: how many models")
    s = sub.add_parser("setup", help="install Hunyuan3D-2 for this machine's NVIDIA GPU")
    s.add_argument("--dir", help="install folder (default ~/.asset-agent/Hunyuan3D-2)")
    s.add_argument("--model", choices=gpu.MODELS, help="default: full with 10GB+ VRAM, else mini")
    s.add_argument("--texture", action="store_true",
                   help="also install Hunyuan3D-Paint (needs CUDA Toolkit 12.6, and MSVC on Windows)")
    s = sub.add_parser("serve", help="run the shape server (Ctrl+C stops it)")
    s.add_argument("--remote", action="store_true", help="let other machines connect (requires a key)")
    s.add_argument("--port", type=int, default=8080)
    s.add_argument("--model", choices=gpu.MODELS)
    s.add_argument("--no-flashvdm", action="store_true", help="if the fast decoder errors on your GPU")
    s.add_argument("--texture", action=argparse.BooleanOptionalAction, default=None,
                   help="serve Hunyuan3D-Paint too (default: on if setup --texture ran)")
    s = sub.add_parser("connect", help="use a shape server on another machine")
    s.add_argument("url", help="e.g. http://192.168.1.50:8080")
    s.add_argument("--key", help="printed by `asset-agent serve --remote`")
    s = sub.add_parser("roblox", help="optional: upload assets to Roblox (Open Cloud) so they save with the place")
    s.add_argument("--upload", choices=["on", "off"], help="on: studio() uploads and inserts assets; off (default): builds them live")
    s.add_argument("--user", help="your Roblox user id (the number in your profile URL)")
    s.add_argument("--group", help="upload to a group instead (group id)")
    s.add_argument("--key", help="Open Cloud API key with Assets read+write ('-' or left out: asked for at a prompt)")
    a = p.parse_args(argv)
    try:
        if a.cmd == "doctor":
            from .doctor import report
            text, code = report(live=not a.offline)
            print(text)
            return code
        if a.cmd == "studio-mcp":  # one .mcp.json entry for Windows and macOS: find Studio's proxy, hand it our stdio
            import subprocess
            from .studio_client import StudioError, launcher
            try:
                p = launcher()
            except StudioError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            return subprocess.call([p.command, *p.args])
        if a.cmd == "store":
            from . import store
            print({"search": lambda: store.search(a.arg, a.n), "gallery": lambda: store.gallery(a.arg, a.n),
                   "collect": store.collect, "grade": lambda: store.grade_file(a.arg)}[a.action]())
            return 0
        if a.cmd == "quality":
            import os
            from pathlib import Path
            from . import quality
            if a.action == "sync":
                print(quality.sync(Path(os.environ.get("ASSET_AGENT_HOME", "assets"))))
            elif a.action == "export":
                print(quality.export(include_private=a.all))
            elif a.action == "pairs":
                print(quality.pairs(include_private=a.all))
            elif a.action == "brief":
                print(quality.brief(a.category))
            else:
                print(quality.summary())
            return 0
        if a.cmd == "job":
            import json
            from . import server
            j = server._studio_jobs()
            if not a.name:
                from .jobs import board
                print(board(j))
            elif a.verdict == "trace":
                print("\n".join(f"{e['stage']} {e['kind']}: {json.dumps(e['data'])[:200]}" for e in j.trace(a.name)))
            elif a.verdict:
                try:
                    print(j.approve(a.name, a.verdict == "up", a.note, a.back_to, a.stars))
                except (KeyError, ValueError) as e:
                    print(f"error: {e}", file=sys.stderr)
                    return 1
            else:
                print(j.next(a.name) if j.get(a.name) else f"no job {a.name}")
            return 0
        if a.cmd in ("generate", "jobs"):
            import os
            from pathlib import Path
            from .pipeline import Queue, describe
            q = Queue(Path(os.environ.get("ASSET_AGENT_HOME", "assets")))
            if a.cmd == "generate":
                for kw in [{"image": i} for i in a.images] or [{"prompt": a.prompt}]:
                    q.submit(backend=a.backend, textured=a.textured, background=False, **kw)
                for j in q.drain():  # in this process, so the command finishes when they do
                    print(describe(j))
            else:
                print("\n".join(describe(j) for j in q.jobs()) or "no jobs")
            return 0
        if a.cmd == "status":
            print(status())
        elif a.cmd == "setup":
            print(gpu.setup(a.dir, a.model, a.texture))
        elif a.cmd == "serve":
            return gpu.serve(a.remote, a.port, a.model, not a.no_flashvdm, a.texture)
        elif a.cmd == "connect":
            print(connect(a.url, a.key))
        elif a.cmd == "roblox":
            key = a.key
            if key is None and not config.load().get("roblox_key") and a.upload != "off" or key == "-":  # asked for: no shell quoting to mangle it
                import getpass
                key = getpass.getpass("Open Cloud API key (paste it, then Enter; it stays hidden): ")
            if key is not None:
                key = key.strip().strip("'\"")
                if len(key) < 40:  # names, ids and cut-off pastes; real keys are much longer
                    print(f"error: that key is {len(key)} characters; an Open Cloud API key is much longer. Copy the "
                          "secret shown after Create or Regenerate at create.roblox.com/dashboard/credentials, then "
                          "run `python -m asset_agent roblox --key -` and paste it at the prompt", file=sys.stderr)
                    return 1
            kv = {k: v for k, v in (("roblox_user", a.user), ("roblox_group", a.group), ("roblox_key", key)) if v}
            if a.upload:
                kv["roblox_upload"] = True if a.upload == "on" else None
            c = config.save(**kv)
            print(f"roblox: upload={'on' if c.get('roblox_upload') else 'off (studio() builds assets live)'} "
                  f"user={c.get('roblox_user')} group={c.get('roblox_group')} "
                  f"key={'set' if c.get('roblox_key') else 'missing'} -> {config.path()}")
    except gpu.SetupError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
