"""MCP server: a few high-level tools with one-line results. Images only via preview().

Assets live in $ASSET_AGENT_HOME (default ./assets); generations are cached in ./library/cache.
"""
import asyncio
import functools
import json
import os
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer

from . import generators, lighting
from .asset import Asset
from .make import build_model, kit_help, make_asset as _make_asset
from . import anim, brief, characters, review as review_board, roblox, studio_client, vfx
from .project import Project

server = MCPServer("asset-agent", instructions=(
    "Game-ready 3D assets (Roblox first). Aim to nail each asset first shot: before building or generating "
    "something new, get the user's brief in one message (reference image, style, colours, use and size, key "
    "shape details); make_asset lists what's missing. For a game, call plan(project) first: its style guide, roster "
    "and what past ratings liked/avoided; pass project=. Best quality: build (you model it in code, ~5s); "
    "make_asset generates organic shapes (slow) and returns one line. Fix things with revise (only that layer and what depends on it "
    "rebuilds), not by regenerating. preview only when you must see it (layer='breakdown' shows geometry, "
    "topology, colour, texture). After each make_asset, build or revise, call review(name): the user "
    "sees it in a browser review window, rates it and presses Regenerate (revise from their notes), Looks good or Place. studio(name) puts an asset in the user's open Roblox Studio place. VFX: "
    "vfx_lab shows a preset playing in Studio; rate(preset, stars) scores it; vfx_lab(import_from=) saves effects "
    "already in the place (e.g. Creator Store packs inserted with Studio's insert_asset) as presets. "
    "Animation: animate (R15 presets or your own tracks; revise by calling it again with what changes). "
    "Concept art: generate(images) queues them for Hunyuan3D (generate() shows progress); clean each raw mesh in the "
    "blender server (open, inspect, cleanup, export), then review and studio. Asset studio jobs: job_next(name) "
    "says what the current stage needs, job_submit hands it in; never skip a stage or give the user's thumbs up."))


def home() -> Path:
    return Path(os.environ.get("ASSET_AGENT_HOME", "assets"))


def _asset(name: str) -> Asset:
    root = home() / name
    if not (root / "manifest.json").exists():
        have = sorted(p.parent.name for p in home().glob("*/manifest.json"))
        raise KeyError(f"no asset {name!r}; have: {', '.join(have) or 'none'}")
    return Asset(root)


def _fx_spec(fx) -> dict:
    """An animation's fx param (a preset name or {type, color, size, rate}) as an effects dict."""
    if not fx:
        return {}
    return vfx.merge({}, {"fx": {"type": fx} if isinstance(fx, str) else fx})


def _rig_mesh(name: str | None) -> dict | None:
    """The body-part pieces of R15 character `name` (worker.rig_mesh), if it's a kit-built one."""
    if not name or not (home() / name / "manifest.json").exists():
        return None
    a = _asset(name)
    if a.m.get("rig") != "r15":
        raise ValueError(f"{name} isn't an R15 character")
    return json.loads((a.root / Path(a.m["build"]["code"]).parent / "rig_mesh.json").read_text())


def _queue(name: str, line: str) -> str:
    """Put the asset's (or animation's) current version in the review window; the line gets its address."""
    try:
        if anim.Animation.exists(home() / name):
            a = anim.Animation(home() / name)
            d = a.resolved()
            payload = {**anim.playback(d), "rig": _rig_mesh(d.get("on")), "on": d.get("on")}
            url = review_board.add(home(), name, a.m["version"], None, line.split(" | ")[0], kind="animation",
                                   fx=vfx.resolve(_fx_spec(d.get("fx"))), anim=payload)
            return f"{line} | review: {url}"
        a = _asset(name)
        v = a.m["version"]
        glb = a.root / "export" / "versions" / f"v{v}" / f"{name}.glb"
        return f"{line} | review: {review_board.add(home(), name, v, glb, a.summary(), fx=vfx.resolve(a.effects))}"
    except Exception as e:  # the review window never breaks making the asset
        return f"{line} | review unavailable: {type(e).__name__}: {e}"[:400]


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
               backend: str = "auto", project: str | None = None, ready: bool = False) -> str:
    """Generate an asset from a text prompt or image path (~2 min). style: project | flat (color
    [r,g,b]). budget: roblox_prop | roblox_hero | mobile_prop | godot_lod. backend: auto | hf | local.
    project: fills unset args from that game's style guide. Asks for missing context first; ready=True skips."""
    proj = Project.open(home(), project) if project else None
    questions = [] if ready else brief.gaps(prompt, image, color, budget, proj)
    if questions:
        return brief.ask(questions)
    return _queue(name, _make_asset(home() / name, prompt=prompt, image=image, budget=budget, style=style, color=color,
                                    backend=backend, textured=textured, project=proj))


_queue_obj = None


def _jobs():
    global _queue_obj
    from .pipeline import Queue
    if _queue_obj is None:
        _queue_obj = Queue(home())
    return _queue_obj


@tool
def generate(images: list[str] | None = None, prompt: str | None = None) -> str:
    """Concept images (or a prompt) -> Hunyuan3D raw meshes in assets/_raw, queued in the background, to
    clean in the blender server. No arguments: the queue."""
    from .pipeline import describe
    q = _jobs()
    if not images and not prompt:
        return "\n".join(describe(j) for j in q.jobs()[-20:]) or "no jobs"
    out = [q.submit(image=img) for img in images or []] or [q.submit(prompt=prompt)]
    return "queued " + "; ".join(describe(j) for j in out) + " | generate() for progress"


@server.tool(structured_output=False)
def build(name: str, code: str, spec: dict | None = None, budget: str | None = None, project: str | None = None):
    """Model it yourself in Python with the kit (code="help" lists it): studs, Z up, faces -Y.
    Write spec first {shape, details, palette (main+accents+glow), pose, size, refs (what to take)}.
    Returns 4 views: check them against spec and rebuild before showing. Again with edited code = next
    version. mat(..., glow=True) parts are Neon in Roblox."""
    try:
        if code.strip() == "help":
            return kit_help()
        line, img = build_model(home() / name, code, spec, budget, Project.open(home(), project) if project else None)
        return [_queue(name, line), Image(path=str(img))]
    except Exception as e:
        return f"error: {type(e).__name__}: {' '.join(str(e).split())}"[:300]


@tool
def import_mesh(name: str, path: str, image: str | None = None, style: str = "auto",
                budget: str = "roblox_prop") -> str:
    """Make an asset from an existing mesh file (glb/fbx/obj), e.g. a free Tripo/Meshy download.
    style: auto (keep its texture) | project (needs image) | flat."""
    a = Asset.create(home() / name, {"main": path}, budget, images={"main": image} if image else None,
                     surface_mode=style)
    return _queue(name, a.build())


@tool
def revise(name: str, layer: str, change: dict, part: str | None = None) -> str:
    """Change one layer; only it and what depends on it rebuild. Layers and keys:
    finish {roughness, metallic, tint} | vfx {effect: {type (a library preset), color, size, rate} | null} |
    geometry {scale, offset, or new shape: source | prompt | image, keep [scale, texture]} |
    topology {target_tris} | uv {angle, margin} | surface {mode auto|bake|project|flat, image, ao, tex_size} |
    collision {max_tris} | export {scale_to (m), target} | preset (name = VFX preset/aura) {recolor [r,g,b] | null}."""
    if layer == "preset":
        return vfx.revise_preset(name, **change)
    return _queue(name, _asset(name).revise(layer, part=part, **change))


@tool
def rollback(name: str, layer: str | None = None, version: int | None = None, part: str | None = None) -> str:
    """No version: the history. Else restore one layer's settings from that version (exact when inputs
    match); for an animation, the whole animation."""
    if anim.Animation.exists(home() / name):
        a = anim.Animation(home() / name)
        return a.history() if version is None else a.rollback(version)
    if version is None:
        return _asset(name).history()
    return _asset(name).rollback(layer, version, part=part)


@tool
def validate(name: str) -> str:
    """Pass/fail vs the budget: tris, per-part tris, texture size, UVs, manifold, size."""
    return _asset(name).summary()


@server.tool(structured_output=False)
def preview(name: str, size: int = 256, layer: str = "final", refs: list[str] | None = None,
            hide: list[str] | None = None):
    """Image. layer: final | geometry | topology | colour | texture | vfx | breakdown, or studio: the
    model in the open place (front, 3/4, side, face) next to refs (image paths); hide: parts in the way."""
    try:
        if layer == "studio":
            sheet, note = characters.look(name, home() / "_look" / f"{name}.png", refs=refs, hide=hide)
            return [note, Image(path=str(sheet))]
        return Image(path=str(_asset(name).preview(min(size, 512), layer)))
    except Exception as e:
        return f"error: {type(e).__name__}: {' '.join(str(e).split())}"[:300]


@server.tool(structured_output=False)
def character(name: str, query: str | None = None, pick: dict | None = None, refs: list[str] | None = None):
    """Known characters from real Roblox assets (don't hand-model their faces or hair). query: free
    Creator Store models lined up, numbered, next to refs. pick {body|shirt|pants|hair|face|skin: #}:
    an R15 avatar from them; animate and studio(on=) work on it."""
    try:
        text, img = characters.find(home() / name, query, pick, refs)
        return [text, Image(path=str(img))] if img else text
    except Exception as e:
        return f"error: {type(e).__name__}: {' '.join(str(e).split())}"[:300]


@server.tool(structured_output=False)
def animate(name: str, preset: str | None = None, params: dict | None = None, tracks: dict | None = None,
            project: str | None = None):
    """R15 animation -> filmstrip + .rbxmx. preset='help' lists presets. Again with only what changes =
    next version. params: speed amount arms legs torso head bounce (x1), lean (deg), length loop, on
    (character), fx (vfx preset).
    tracks {Joint: {rx|ry|rz deg, x|y|z studs: n | {o,a,p,h} wave | {keys:[[u,v,ease]]}}} override joints."""
    try:
        if preset == "help":
            return (anim.catalog() + "\njoints: " + " ".join(anim.JOINTS) +
                    "\nWriting your own (rules learned from ratings):\n" + anim.lessons())
        a = anim.Animation(home() / name)
        if a.m is None and (home() / name / "manifest.json").exists():
            raise ValueError(f"{name} is a model; pick a new name for the animation")
        line = _queue(name, a.update(preset=preset, params=params, tracks=tracks, project=project))
        return [line, Image(path=str(a.root / "preview.png"))]
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
    lines += [f"anim {p.parent.name}: {anim.Animation(p.parent).history().splitlines()[-1]}"
              for p in sorted(home().glob("*/anim.json")) if q in p.parent.name.lower()]
    lines += [f"anim preset {x}" for x in anim.catalog().splitlines() if q in x.lower()]
    from . import refs  # imported references (wiki images), rarest first
    lines += [f"ref {e['dir']}/{e['file']}" + (f" (frames {e['frames']})" if e.get("frames") else "") +
              f": {e['caption'][:90]}" for e in refs.search(home(), query, 12)] if query else []
    return "\n".join(lines) or "nothing found"


@tool
def plan(project: str, brief: str | None = None, references: list[str] | None = None,
         assets: dict[str, str] | None = None, style: dict | None = None) -> str:
    """Create or update a game's style guide; returns it with the roster and what ratings taught.
    brief: look appended to every prompt. references: image paths, or web pages ("url|filter words",
    e.g. the game's wiki) whose images are imported. assets: {name: prompt} to make.
    style: budget, style (project|flat), palette [[r,g,b]], sizes {word: metres}, target_tris,
    tex_size, ao, roughness, metallic."""
    p = Project.open(home(), project, create=True)
    if brief is not None or references or assets or style or not (p.root / "project.json").exists():
        p.update(references=references, assets=assets, **({"brief": brief} if brief is not None else {}),
                 **(style or {}))
    imported = "".join(f"\n{x}" for x in getattr(p, "imported", []))
    return f"{p.summary()}{imported}\nhandoff (for a new chat): {p.handoff()}"


@tool
def rate(name: str, stars: int, note: str = "") -> str:
    """Rate an asset's current version (or a VFX or animation preset) 1-10 with a short note on what's
    good or wrong. Ratings tune the project's defaults and show up in plan() and animate('help')."""
    return _rate(name, stars, note)


def _rate(name: str, stars: int, note: str = "") -> str:
    line = _rate_core(name, stars, note)
    try:  # every rating also becomes a note in the quality vault (quality/); never fails the rating
        _vault_note(name, stars, note)
    except Exception as e:  # noqa: BLE001
        line += f" (vault note failed: {type(e).__name__}: {e})"[:160]
    return line


def _vault_note(name: str, stars: float, note: str):
    from . import quality
    if not (home() / name / "manifest.json").exists() and name in vfx.presets():
        quality.record_vfx(name, vfx.raw_presets()[name])
    elif anim.Animation.exists(home() / name):
        a = anim.Animation(home() / name)
        quality.record("animation", name, a.m["version"], stars, note, "animation", "procedural",
                       {"preset": a.m["spec"].get("preset")})
    elif not (home() / name).exists() and name in anim.presets():
        p = anim._library()[name]
        quality.record_animation(name, p["ratings"][-1], p)
    else:
        quality.record_asset(home(), name, _asset(name).m["version"], stars, note)


def _rate_core(name: str, stars: int, note: str = "") -> str:
    if not 1 <= stars <= 10:
        raise ValueError("stars must be 1-10")
    if not (home() / name / "manifest.json").exists() and name in vfx.presets():
        p = vfx.presets()[name]
        p["score"] = stars
        if note:
            p["note"] = note
        ver = next((t for t in p.get("tags", []) if t[:1] == "v" and t[1:].isdigit()), None)
        p.setdefault("ratings", []).append({"v": ver, "stars": stars, "note": note})  # kept across versions
        vfx.save_preset(name, p)
        return f"vfx preset {name} scored {stars}/10"
    if anim.Animation.exists(home() / name):
        a = anim.Animation(home() / name)
        a.m["ratings"].append({"v": a.m["version"], "stars": stars, "note": note})
        a.file.write_text(json.dumps(a.m, indent=1))
        line = f"rated animation {name} v{a.m['version']} {stars}/10"
        spec = a.m["spec"]
        if spec.get("preset") and not spec.get("tracks"):  # a preset with knobs: the preset learns too
            knobs = ", ".join(f"{k}={v}" for k, v in (spec.get("params") or {}).items())
            anim.rate_preset(spec["preset"], stars, note + (f" (with {knobs})" if knobs else ""), via=name)
            line += f"; noted on preset {spec['preset']}"
        return line
    if not (home() / name).exists() and name in anim.presets():
        return anim.rate_preset(name, stars, note)
    a = _asset(name)
    a.m.setdefault("ratings", []).append({"v": a.m["version"], "stars": stars, "note": note})
    a._save()
    if not a.m.get("project"):
        return f"rated {name} v{a.m['version']} {stars}/10 (no project, so nothing learned)"
    p = Project.open(home(), a.m["project"])
    line = p.rate(name, a.m["version"], stars, note, a.params_snapshot(), a.m.get("prompt"))
    p.handoff()
    return line


@server.tool(structured_output=False)
def studio(name: str, on: str | None = None) -> str:
    """Put the asset in the open Studio place, replacing the old copy, with its effects: built live,
    no upload or key (not saved with the place). R15 characters become a rigged character.
    Animations play on a test dummy, or on character `on`. name 'lighting[:preset]': shader lighting."""
    try:
        return _place(name, on)
    except Exception as e:
        return f"error: {type(e).__name__}: {' '.join(str(e).split())}"[:300]


def _place(name: str, on: str | None = None) -> str:
    if name.startswith("lighting"):
        preset = name.partition(":")[2]
        return studio_client.run(lambda s: s.luau(lighting.script(preset))) if preset else lighting.catalog()
    if anim.Animation.exists(home() / name):
        d = anim.Animation(home() / name).resolved()
        return studio_client.run(lambda s: s.luau(anim.studio_script(name, d, rig=on or d.get("on"))))
    rec = home() / name / "character.json"
    if rec.exists() and json.loads(rec.read_text()).get("pick"):
        return characters.find(home() / name, None, json.loads(rec.read_text())["pick"], None)[0]
    a = _asset(name)
    if a.m.get("rig") == "r15":
        mesh = json.loads((a.root / Path(a.m["build"]["code"]).parent / "rig_mesh.json").read_text())
        rev = f"build v{a.m['build']['v']}"
        return studio_client.run(lambda s: s.luau(roblox.character_script(name, rev, mesh)))
    line, script = a.to_studio()
    try:
        return f"{line} | studio: {studio_client.run(lambda s: s.luau(script))}"
    except studio_client.StudioError as e:
        return f"{line} | Studio not reachable ({e}); run via Roblox Studio MCP execute_luau (Edit):\n{script}"


def _place_from_review(name: str) -> str:
    """The review window's Place button: like studio(name), but Studio must take it."""
    if anim.Animation.exists(home() / name):
        return _place(name)
    a = _asset(name)
    if a.m.get("rig") == "r15":
        return _place(name)
    line, script = a.to_studio()
    return f"{line} | studio: {studio_client.run(lambda s: s.luau(script))}"


review_board.hooks.update(rate=_rate, place=_place_from_review)


def _studio_jobs():
    from . import jobs
    jobs.hooks.update(place=_place_from_review, rate=_rate)
    return jobs.Jobs(home())


@tool
def job_next(name: str = "") -> str:
    """Asset studio: what job `name`'s current stage needs (starts the job at its brief). No name: the
    board. Stages run in order; each waits for the user's thumbs up."""
    from .jobs import board
    return _studio_jobs().next(name) if name else board(_studio_jobs())


@tool
def job_submit(name: str, output: dict) -> str:
    """Hand in the current stage's output (job_next says its shape); its checks run, then it waits for
    the user."""
    return _studio_jobs().submit(name, output)


@server.tool(structured_output=False)
async def review(name: str) -> str:
    """Newest version (model or animation) in the browser review window; waits for the user's
    rating, notes and choice."""
    try:
        if not anim.Animation.exists(home() / name):
            _asset(name)
        _queue(name, "")  # its current version, if not queued yet
        return await asyncio.to_thread(review_board.wait, home(), name)
    except Exception as e:
        return f"error: {type(e).__name__}: {' '.join(str(e).split())}"[:300]


@server.tool(structured_output=False)
def vfx_lab(preset: str, color: list[float] | None = None, size: float = 1.0, rate: float = 1.0,
            stand_in: str | None = None, import_from: str | None = None, use: str = "",
            tags: list[str] | None = None, asset_id: str | None = None):
    """Play a VFX preset in the open Studio place (a lab stage above the map) and return a screenshot.
    color/size/rate preview a variant. stand_in: character | item | rarity | base | default.
    import_from: save the effect at this path (workspace.Pack.Blast) as `preset`; .* lists."""
    try:
        if import_from:
            return _vfx_import(import_from, preset, use, tags, asset_id)
        fx = {k: v for k, v in (("color", color), ("size", size), ("rate", rate)) if v not in (None, 1.0)}
        code = roblox.lab_script(preset, fx, stand_in)
        out = home() / "_vfx" / f"{preset}.png"

        async def go(s):
            import asyncio
            cam, look = ([float(x) for x in v.split(",")] for v in (await s.luau(code)).strip().split("|"))
            await asyncio.sleep(0.3 if vfx.presets()[preset].get('mode') == 'burst' else 2.5)  # bursts peak early; loops need to fill in
            await s.capture(out, cam, look)  # the first capture after a rebuild can return the previous frame
            return await s.capture(out, cam, look)
        return Image(path=str(studio_client.run(go)))
    except Exception as e:
        return f"error: {type(e).__name__}: {' '.join(str(e).split())}"[:300]


def _vfx_import(path: str, name: str = "", use: str = "", tags: list[str] | None = None,
                asset_id: str | None = None) -> str:
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


def _compact(schema):
    """Advertised schemas without what costs tokens and tells the model nothing: titles (they repeat
    the names) and "or null" on optional args (leaving them out already means None)."""
    if isinstance(schema, dict):
        schema.pop("title", None)
        alts = schema.get("anyOf")
        if alts and {"type": "null"} in alts and len(alts) == 2:
            schema.pop("anyOf")
            schema.update(next(a for a in alts if a != {"type": "null"}))
            if schema.get("default", 0) is None:
                schema.pop("default")
        for v in schema.values():
            _compact(v)
    elif isinstance(schema, list):
        for v in schema:
            _compact(v)
    return schema


for _t in server._tool_manager._tools.values():  # arguments are still validated against the full signatures
    _compact(_t.parameters)


def main():
    server.run("stdio")


if __name__ == "__main__":
    main()
