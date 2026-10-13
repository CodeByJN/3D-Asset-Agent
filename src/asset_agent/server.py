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
from . import roblox, studio_client, vfx
from .project import Project

server = MCPServer("asset-agent", instructions=(
    "Game-ready 3D assets (Roblox first). For a game, call plan(project) first: its style guide, roster "
    "and what past ratings liked/avoided; pass project= to make_asset. make_asset generates (free or on "
    "your GPU) and returns one line. Fix things with revise (only that layer and what depends on it "
    "rebuilds), not by regenerating. preview only when you must see it (layer='breakdown' shows geometry, "
    "topology, colour, texture). After each make_asset or revise the user looks at, ask for a 1-10 "
    "rating and call rate. studio(name) puts an asset in the user's open Roblox Studio place. VFX: "
    "vfx_lab shows a preset playing in Studio; rate(preset, stars) scores it; vfx_import saves effects "
    "already in the place (e.g. Creator Store packs inserted with Studio's insert_asset) as presets."))


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
def make_asset(name: str, prompt: str | None = None, image: str | None = None, style: str | None = None,
               color: list[float] | None = None, budget: str | None = None, textured: bool = False,
               backend: str = "auto", project: str | None = None) -> str:
    """Generate a game-ready asset from a text prompt or an image path (free, ~1-2 min).
    style: project (paint the generated image on) | flat (one colour, set via color [r,g,b] 0-1).
    budget: roblox_prop | roblox_hero | mobile_prop | godot_lod. backend: auto (your GPU server if up, else free hf) | hf | local.
    project: a game from plan; fills unset args from its style guide (prompt too, if on the roster)."""
    return _make_asset(home() / name, prompt=prompt, image=image, budget=budget, style=style, color=color,
                       backend=backend, textured=textured, project=Project.open(home(), project) if project else None)


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
    finish {roughness, metallic, tint} | vfx {effect_name: {type (vfx preset: see library), color,
    size, rate} or null} | geometry {scale [x,y,z], offset, or a new shape: source
    (mesh path) | prompt | image, keep [scale, texture] (default both)} |
    topology {target_tris} | uv {angle, margin} | surface {mode, image, ao, tex_size} |
    collision {max_tris} | export {scale_to (m), target roblox|godot|unity}.
    A VFX preset or aura: layer "preset" {recolor [r,g,b] or null to undo} (keeps whites, new version)."""
    if layer == "preset":
        return vfx.revise_preset(name, **change)
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
def preview(name: str, size: int = 256, layer: str = "final"):
    """Image. layer: final | geometry | topology | colour | texture | vfx (4 views each) |
    breakdown (labelled row: mesh, topology, colour, texture, vfx). Costs image tokens: use sparingly."""
    try:
        return Image(path=str(_asset(name).preview(min(size, 512), layer)))
    except Exception as e:
        return f"error: {type(e).__name__}: {' '.join(str(e).split())}"[:300]


@tool
def library(query: str = "") -> str:
    """List assets, cached generations and VFX presets whose name, prompt or tags contain query."""
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
    lines += [f"vfx {x}" for x in vfx.catalog().splitlines() if q in x.lower()]
    return "\n".join(lines) or "nothing found"


@tool
def plan(project: str, brief: str | None = None, references: list[str] | None = None,
         assets: dict[str, str] | None = None, style: dict | None = None) -> str:
    """Create or update a game's style guide; returns it with the roster and what ratings taught.
    brief: look appended to every prompt. references: image paths. assets: {name: prompt} to make.
    style: budget, style (project|flat), palette [[r,g,b]], sizes {word: metres}, target_tris,
    tex_size, ao, roughness, metallic."""
    p = Project.open(home(), project, create=True)
    if brief is not None or references or assets or style or not (p.root / "project.json").exists():
        p.update(references=references, assets=assets, **({"brief": brief} if brief is not None else {}),
                 **(style or {}))
    return p.summary()


@tool
def rate(name: str, stars: int, note: str = "") -> str:
    """Rate an asset's current version (or a VFX preset) 1-10 with a short note on what's good or
    wrong. Ratings tune the project's defaults and show up in plan()."""
    if not 1 <= stars <= 10:
        raise ValueError("stars must be 1-10")
    if not (home() / name / "manifest.json").exists() and name in vfx.presets():
        p = vfx.presets()[name]
        p["score"] = stars
        if note:
            p["note"] = note
        vfx.save_preset(name, p)
        return f"vfx preset {name} scored {stars}/10"
    a = _asset(name)
    a.m.setdefault("ratings", []).append({"v": a.m["version"], "stars": stars, "note": note})
    a._save()
    if not a.m.get("project"):
        return f"rated {name} v{a.m['version']} {stars}/10 (no project, so nothing learned)"
    return Project.open(home(), a.m["project"]).rate(name, a.m["version"], stars, note, a.params_snapshot(),
                                                     a.m.get("prompt"))


@server.tool(structured_output=False)
def studio(name: str) -> str:
    """Upload the asset to your Roblox account (only if its model changed) and put it in the open
    Studio place, replacing the old copy, with its effects."""
    try:
        line, script = _asset(name).to_studio()
        try:
            return f"{line} | studio: {studio_client.run(lambda s: s.luau(script))}"
        except studio_client.StudioError as e:
            return f"{line} | Studio not reachable ({e}); run via Roblox Studio MCP execute_luau (Edit):\n{script}"
    except Exception as e:
        return f"error: {type(e).__name__}: {' '.join(str(e).split())}"[:300]


@server.tool(structured_output=False)
def vfx_lab(preset: str, color: list[float] | None = None, size: float = 1.0, rate: float = 1.0,
            stand_in: str | None = None):
    """Play a VFX preset in the open Studio place (a lab stage above the map) and return a screenshot.
    color/size/rate preview a variant. stand_in: character | item | rarity | base | default."""
    try:
        fx = {k: v for k, v in (("color", color), ("size", size), ("rate", rate)) if v not in (None, 1.0)}
        code = roblox.lab_script(preset, fx, stand_in)
        out = home() / "_vfx" / f"{preset}.png"

        async def go(s):
            import asyncio
            cam, look = ([float(x) for x in v.split(",")] for v in (await s.luau(code)).strip().split("|"))
            await asyncio.sleep(0.3 if vfx.presets()[preset].get('mode') == 'burst' else 1.5)  # bursts peak early; loops need to fill in
            return await s.capture(out, cam, look)
        return Image(path=str(studio_client.run(go)))
    except Exception as e:
        return f"error: {type(e).__name__}: {' '.join(str(e).split())}"[:300]


@tool
def vfx_import(path: str, name: str = "", use: str = "", tags: list[str] | None = None,
               asset_id: str | None = None) -> str:
    """Save an effect that's in the open Studio place as VFX preset `name`. path: dot path like
    workspace.Pack.Blast; end it with .* to list the effects under it instead."""
    if path.endswith(".*"):
        return studio_client.run(lambda s: s.luau(roblox.list_script(path[:-2]))) or "no effects found"
    raw = studio_client.run(lambda s: s.luau(roblox.serialize_script(path)))
    try:
        data = json.loads(raw)
    except ValueError:
        raise ValueError(f"Studio said: {' '.join(raw.split())[:200]}")
    name = name or data["name"].lower().replace(" ", "_")
    src = {"kind": "creator_store" if asset_id else "studio", "asset_id": asset_id, "path": path}
    p = roblox.import_preset(data, use=use or data["name"], tags=tags or [], source=src)
    vfx.save_preset(name, p)
    stats = " ".join(f"{k}={v}" for k, v in data.get("stats", {}).items() if v)
    return f"saved vfx preset {name}: {p['mode']}, {stats}"


def main():
    server.run("stdio")


if __name__ == "__main__":
    main()
