"""MCP server: Blender as tools, for cleaning raw generated meshes into game-ready Roblox assets.

One headless Blender stays running (session.py) with the meshes loaded, so Claude can look, fix and look
again cheaply. The intended loop, per raw mesh from the generate queue (asset-agent's generate/jobs):

    open(job or path) -> inspect -> cleanup([...ops]) -> inspect -> render (look) -> export(name)

export hands the result to the asset pipeline (assets/<name>), where review(name) and studio(name) on
the asset-agent server take it from there.
"""
import functools
import json
import os
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer

from .blender import BlenderError
from .session import session

OPS_HELP = (
    "merge_by_distance {dist} | recalc_normals {inside} | delete_loose | dissolve_degenerate | fill_holes "
    "{sides} | keep_largest {count} | decimate {target_tris | ratio | planar_angle} | remesh {voxel, smooth} "
    "(seals holes, drops UVs) | smooth {iterations, factor} | triangulate | shade_smooth {angle} | rotate "
    "{axis, degrees} | scale_to {studs | height | length} (sizes in studs, on the ground) | uv_unwrap {method "
    "smart|lightmap, angle, margin} | bake_texture {size, ao} (one texture, one material)")

server = MCPServer("blender", instructions=(
    "Blender for cleaning raw meshes (e.g. Hunyuan output from asset-agent's generate queue) into Roblox-ready "
    "assets. Loop: open -> inspect -> cleanup with the ops the issues call for -> inspect again -> render to "
    "look -> export. Typical raw-mesh order: merge_by_distance, delete_loose, recalc_normals, keep_largest "
    "(floating bits), fill_holes or remesh (if non-manifold/open), decimate to the tri budget, scale_to the "
    "game size in studs, uv_unwrap, bake_texture 1024, shade_smooth. Roblox limits: 20000 tris per mesh, one "
    "1024 px texture. run executes bpy for anything the ops don't cover."))

def _home() -> Path:
    return Path(os.environ.get("ASSET_AGENT_HOME", "assets"))  # same as the asset-agent server


def _short(m: dict) -> str:
    """inspect() result as a few lines."""
    uv = m["uv"]
    uvs = (f"uv {','.join(uv['layers'])} out-of-0-1 {uv.get('outside_0_1')} cover {uv.get('coverage')} "
           f"overlap {uv.get('overlap')}" if uv["layers"] else "no uv")
    tex = ", ".join(f"{t['image']} {t['size'][0]}x{t['size'][1]}" for t in m["textures"]) or "no textures"
    lines = [f"{m['name']}: {m['tris']} tris, {m['verts']} verts, {m['islands']} piece(s), size "
             f"{' x '.join(map(str, m['size']))} ({m['units']})",
             f"non-manifold {m['non_manifold_edges']}, open edges {m['boundary_edges']}, duplicate verts "
             f"{m['duplicate_verts']}, loose {m['loose_verts']}v/{m['loose_edges']}e, degenerate "
             f"{m['degenerate_faces']}, flipped {m['flipped_faces']}",
             f"{uvs}; {m['materials']} material(s), {tex}",
             ("roblox: ready" if m["roblox_ready"] else "roblox: not ready") +
             (" - " + "; ".join(m["issues"]) if m["issues"] else "")]
    return "\n".join(lines)


def _guard(fn):
    @functools.wraps(fn)
    def wrap(*a, **k):
        try:
            return fn(*a, **k)
        except (BlenderError, KeyError, ValueError, FileNotFoundError) as e:
            return f"error: {' '.join(str(e).split())}"[:400]
    return wrap


@server.tool(name="open", structured_output=False)
@_guard
def open_mesh(source: str, name: str | None = None) -> str:
    """Load a mesh into Blender: a generate job's name or id (its raw.glb), or a .glb/.gltf/.fbx/.obj path.
    Returns inspect() of it."""
    path = Path(source)
    if not path.exists():
        from .pipeline import Queue
        j = Queue(_home()).job(source)
        if j["status"] != "raw":
            return f"job {j['name']} is {j['status']}" + (f": {j.get('error')}" if j.get("error") else "")
        path, name = Path(j["raw"]), name or j["name"]
    return _short(session().call("open", path=str(path.resolve()), name=name or path.stem))


@server.tool(structured_output=False)
@_guard
def inspect(name: str, full: bool = False) -> str:
    """Geometry metrics (tris, non-manifold/open edges, duplicate/loose verts, flipped faces, pieces, UVs,
    materials, textures, size) and what stops it being Roblox-ready. full=True: the raw numbers as JSON."""
    m = session().call("inspect", name=name)
    return json.dumps(m) if full else _short(m)


@server.tool(structured_output=False, description=(
    'Run cleanup ops in order, e.g. [{"op": "merge_by_distance"}, {"op": "decimate", "target_tris": 15000}]. '
    f"Ops: {OPS_HELP}. Returns what each did and inspect() after."))
@_guard
def cleanup(name: str, ops: list) -> str:
    r = session().call("cleanup", name=name, ops=ops)
    return "\n".join(r["done"]) + "\n" + _short(r["after"])


@server.tool(structured_output=False)
@_guard
def run(code: str, name: str | None = None) -> str:
    """Execute bpy code in the session (bpy, bmesh, Vector, Matrix, math; obj = the named mesh). Returns what
    it prints and `result` if set. For anything the cleanup ops don't cover."""
    r = session().call("run", code=code, name=name)
    return (r["output"] or "") + (f"\nresult: {json.dumps(r['result'])}" if r["result"] is not None else "")


@server.tool(structured_output=False)
@_guard
def render(name: str, views: list[str] | None = None, size: int = 384):
    """Look at it: orthographic renders (front, side, back, 34; also top) side by side, textured if it has
    textures, clay otherwise."""
    from PIL import Image as PI
    out = (_home() / "_raw" / name / "render").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    files = session().call("render", name=name, out=str(out), size=size,
                           views=views or ["front", "side", "back", "34"])["files"]
    ims = [PI.open(f).convert("RGB") for f in files]
    sheet = PI.new("RGB", (size * len(ims), size))
    for i, im in enumerate(ims):
        sheet.paste(im, (i * size, 0))
    p = out.with_suffix(".png")
    sheet.save(p)
    return [", ".join(views or ["front", "side", "back", "34"]), Image(path=str(p))]


@server.tool(structured_output=False)
@_guard
def export(name: str, budget: str = "roblox_hero", to_asset: bool = True) -> str:
    """Write it out for Roblox (GLB in metres, FBX in studs, texture embedded) and, with to_asset, make it
    the asset `name` (a new version if it exists) so asset-agent's review(name) and studio(name) work."""
    m = session().call("inspect", name=name)
    blocking = [i for i in m["issues"] if "separate pieces" not in i]
    out = (_home() / "_raw" / name / "clean").resolve()
    files = session().call("export", name=name, out_dir=str(out))["files"]
    line = f"exported {name}: {m['tris']} tris -> {', '.join(Path(f).name for f in files.values())}"
    if blocking:
        line += " | still: " + "; ".join(blocking)
    if not to_asset:
        return line
    from .asset import Asset
    root = _home() / name
    glb = files["glb"]
    if (root / "manifest.json").exists():
        a = Asset(root)
        status = a.revise("geometry", source=glb)
    else:
        a = Asset.create(root, {"main": glb}, budget, surface_mode="auto")
        status = a.build()
    return f"{line}\nasset {name}: {status.splitlines()[0][:300]} | next: review('{name}') or studio('{name}')"


@server.tool(structured_output=False)
@_guard
def meshes() -> str:
    """What's open in the Blender session."""
    ms = session().call("list")["meshes"]
    return "\n".join(f"{m['name']}: {m['tris']} tris" for m in ms) or "nothing open"


def main():
    server.run("stdio")


if __name__ == "__main__":
    main()
