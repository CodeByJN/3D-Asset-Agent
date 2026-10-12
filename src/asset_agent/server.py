"""MCP server: a few high-level tools with one-line results. Images only via preview().

Assets live in $ASSET_AGENT_HOME (default ./assets); generations are cached in ./library/cache.
"""
import functools
import json
import os
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer

from . import generators
from .asset import Asset
from .make import make_asset as _make_asset

server = MCPServer("asset-agent", instructions=(
    "Game-ready 3D assets (Roblox first). make_asset generates for free and returns one line. "
    "Fix things with revise (only that layer and what depends on it rebuilds), not by regenerating. "
    "preview only when you must see it."))


def home() -> Path:
    return Path(os.environ.get("ASSET_AGENT_HOME", "assets"))


def _asset(name: str) -> Asset:
    root = home() / name
    if not (root / "manifest.json").exists():
        have = sorted(p.parent.name for p in home().glob("*/manifest.json"))
        raise KeyError(f"no asset {name!r}; have: {', '.join(have) or 'none'}")
    return Asset(root)


def one_line(fn):
    """Tools return 'error: ...' (one line) instead of tracebacks."""
    @functools.wraps(fn)
    def wrap(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:
            return f"error: {type(e).__name__}: {' '.join(str(e).split())}"[:300]
    return wrap


def tool(fn):
    return server.tool(structured_output=False)(one_line(fn))


@tool
def make_asset(name: str, prompt: str | None = None, image: str | None = None, style: str = "project",
               color: list[float] | None = None, budget: str = "roblox_prop", textured: bool = False,
               backend: str = "hf") -> str:
    """Generate a game-ready asset from a text prompt or an image path (free, ~1-2 min).
    style: project (paint the generated image on) | flat (one colour, set via color [r,g,b] 0-1).
    budget: roblox_prop | roblox_hero | mobile_prop | godot_lod. backend: hf (free) | local."""
    return _make_asset(home() / name, prompt=prompt, image=image, budget=budget, style=style,
                       color=color, backend=backend, textured=textured)


@tool
def import_mesh(name: str, path: str, image: str | None = None, style: str = "auto",
                budget: str = "roblox_prop") -> str:
    """Make an asset from an existing mesh file (glb/fbx/obj), e.g. a free Tripo/Meshy download.
    style: auto (keep its texture) | project (needs image) | flat."""
    a = Asset.create(home() / name, {"main": path}, budget, images={"main": image} if image else None,
                     surface_mode=style)
    return a.build()


@tool
def revise(name: str, layer: str, change: dict, part: str | None = None) -> str:
    """Change one layer; only it and what depends on it rebuild. Layers and keys:
    finish {roughness, metallic, tint} | geometry {scale [x,y,z], offset, source} |
    topology {target_tris} | uv {angle, margin} | surface {mode, image, ao, tex_size} |
    collision {max_tris} | export {scale_to (m), target roblox|godot|unity}."""
    return _asset(name).revise(layer, part=part, **change)


@tool
def rollback(name: str, layer: str, version: int, part: str | None = None) -> str:
    """Restore one layer's settings from an earlier version (see history); exact when inputs match."""
    return _asset(name).rollback(layer, version, part=part)


@tool
def history(name: str) -> str:
    """Version lines and each layer's current version."""
    return _asset(name).history()


@tool
def validate(name: str) -> str:
    """Pass/fail vs the budget: tris, per-part tris, texture size, UVs, manifold, size."""
    return _asset(name).summary()


@server.tool(structured_output=False)
def preview(name: str, size: int = 256):
    """Image of 4 views (front, right, back, 3/4). Costs image tokens: use sparingly."""
    try:
        return Image(path=str(_asset(name).preview(min(size, 512))))
    except Exception as e:
        return f"error: {type(e).__name__}: {' '.join(str(e).split())}"[:300]


@tool
def library(query: str = "") -> str:
    """List assets (and cached generations) whose name or prompt contains query."""
    q = query.lower()
    lines = []
    for m in sorted(home().glob("*/manifest.json")):
        a = Asset(m.parent)
        if q in m.parent.name.lower() and a.m["layers"].get("export"):
            lines.append(f"{m.parent.name}: v{a.m['version']} {a.summary()}")
    for meta in sorted((Path("library") / "cache").glob("*/meta.json")):
        d = json.loads(meta.read_text())
        if q in (d.get("prompt") or "").lower():
            lines.append(f"cached {d['backend']}: {d.get('prompt')!r} -> {meta.parent / d['mesh']}")
    return "\n".join(lines) or "nothing found"


def main():
    server.run("stdio")


if __name__ == "__main__":
    main()
