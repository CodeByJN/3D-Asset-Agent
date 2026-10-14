"""`asset-agent doctor`: checks everything the harness needs on this machine (Windows or macOS) and
says exactly what to fix."""
import asyncio
import importlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]


def _blender():
    from .blender import BlenderError, find_blender
    try:
        exe = find_blender()
    except BlenderError as e:
        return False, str(e)
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout
        ver = next((ln.strip() for ln in out.splitlines() if ln.startswith("Blender")), "Blender (version unknown)")
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"{exe} would not run: {e}"
    nums = [int(x) for x in ver.split()[1].split(".")[:2]] if len(ver.split()) > 1 and ver.split()[1][0].isdigit() else [0, 0]
    if nums < [4, 2]:
        return False, f"{ver} at {exe}: needs Blender 4.2 or newer (tested on 5.0)"
    return True, f"{ver} ({exe})"


def _studio_mcp():
    from .studio_client import StudioError, launcher
    try:
        p = launcher()
    except StudioError as e:
        return False, str(e)
    return True, " ".join([p.command, *p.args])


def _studio_live():
    """Connects to Studio's MCP and asks which place is open (needs Studio running)."""
    from . import studio_client

    async def go(s):
        return await asyncio.wait_for(s._studio(), 25)
    try:
        sid = studio_client.run(go)
        return True, f"connected (studio {sid})"
    except Exception as e:  # noqa: BLE001 - reported, not raised
        return None, (f"not connected: {' '.join(str(e).split())[:160]}. Open Roblox Studio with a place, and in "
                      "Assistant > ... > Manage MCP Servers turn on 'Enable Studio as MCP server'")


def _packages():
    missing = [m for m in ("mcp", "numpy", "PIL", "gradio_client") if importlib.util.find_spec(m) is None]
    if missing:
        return False, f"missing {', '.join(missing)}: run `uv sync` in the repo"
    return True, "mcp, numpy, pillow, gradio-client"


def _mcp_config():
    f = ROOT / ".mcp.json"
    if not f.exists():
        return False, f"{f} missing: re-clone the repo"
    servers = json.loads(f.read_text()).get("mcpServers", {})
    want = {"asset-agent", "Roblox_Studio"}
    if not want <= set(servers):
        return False, f".mcp.json lacks {', '.join(want - set(servers))}"
    return True, f"{', '.join(servers)} (approve them when Claude Code asks)"


def _tools():
    try:
        from . import server
        return True, f"{len(server.server._tool_manager._tools)} tools load"
    except Exception as e:  # noqa: BLE001
        return False, f"the MCP server fails to load: {type(e).__name__}: {e}"


def checks(live: bool = True):
    """(name, ok, detail) rows: ok True passes, False must be fixed, None is optional or not running."""
    py = sys.version_info
    rows = [("python", py >= (3, 12), f"{platform.python_version()} ({sys.executable})"),
            ("os", sys.platform in ("win32", "darwin"), f"{platform.system()} {platform.release()}"
             + ("" if sys.platform in ("win32", "darwin") else ": Roblox Studio runs on Windows and macOS only")),
            ("uv", shutil.which("uv") is not None or None, shutil.which("uv") or "not on PATH (https://docs.astral.sh/uv/)"),
            ("packages", *_packages()),
            ("blender", *_blender()),
            (".mcp.json", *_mcp_config()),
            ("mcp tools", *_tools()),
            ("studio mcp", *_studio_mcp())]
    if live and rows[-1][1]:
        rows.append(("studio", *_studio_live()))
    from .studio_client import plugin_state
    ok, detail = plugin_state()  # installs itself on the first review in Studio
    rows.append(("review panel", True if ok else None, detail))
    try:
        from .generators import local_status
        s = local_status()
        rows.append(("gpu server", None if s != "ok" else True,
                     "ok" if s == "ok" else f"{s} (optional: make_asset uses free Hugging Face Spaces without one)"))
    except Exception:  # noqa: BLE001
        pass
    return rows


def report(live: bool = True) -> tuple[str, int]:
    rows = checks(live)
    mark = {True: "ok ", False: "FIX", None: " - "}
    lines = [f"{mark[ok]} {name:<11} {detail}" for name, ok, detail in rows]
    bad = sum(ok is False for _, ok, _ in rows)
    lines.append("all set: open this folder in Claude Code" if not bad else f"{bad} thing(s) to fix above")
    return "\n".join(lines), 1 if bad else 0
