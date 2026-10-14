"""Pipeline steps executed inside headless Blender.

Invoked as: blender -b --factory-startup -P worker.py -- job.json
job.json = {"steps": [{"op": ..., ...}], "result": "<path>"}
Each step starts from an empty scene and reads/writes files only, so steps are independent.
"""
import json
import math
import shutil
import sys
import traceback
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


# ---------------------------------------------------------------- helpers

def reset():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.images,
                 bpy.data.textures, bpy.data.node_groups, bpy.data.cameras, bpy.data.lights,
                 bpy.data.collections):
        for d in list(coll):
            coll.remove(d)


def import_any(path) -> bpy.types.Object:
    """Import a model file and return its meshes joined into one object with identity transform."""
    path = str(path)
    before = set(bpy.data.objects)
    ext = Path(path).suffix.lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise ValueError(f"unsupported format {ext}")
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    if not meshes:
        raise ValueError(f"no mesh in {Path(path).name}")
    for o in meshes:
        if o.data.users > 1:
            o.data = o.data.copy()
        mw = o.matrix_world.copy()
        o.parent = None
        o.data.transform(mw)
        o.matrix_world = Matrix()
    for o in new:
        if o.type != "MESH":
            bpy.data.objects.remove(o)
    if len(meshes) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.object.join()
    weld(meshes[0])
    return meshes[0]


def weld(o, dist=1e-6):
    """glTF splits verts at UV seams; re-join them so decimation can't tear seams open."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=dist)
    bm.to_mesh(o.data)
    bm.free()


def tris(me) -> int:
    return sum(len(p.vertices) - 2 for p in me.polygons)


def triangulate(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(o.data)
    bm.free()


def apply_modifiers(o):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    old = o.data
    o.modifiers.clear()
    o.data = me
    bpy.data.meshes.remove(old)


def decimate_to(o, target: int) -> dict:
    """Collapse-decimate to `target` tris. Dense generator meshes can stall far above it (collapse
    refuses the remaining edges): then voxel-remesh finely and decimate the clean result."""
    triangulate(o)
    info = {}
    for _ in range(8):
        n = tris(o.data)
        if n <= target:
            break
        mod = o.modifiers.new("decimate", "DECIMATE")
        mod.ratio = max(target / n * 0.98, 0.001)
        apply_modifiers(o)
        triangulate(o)
        if tris(o.data) > n * 0.97 and not info:  # stalled
            voxel = (o.dimensions.length or 1.0) / REMESH_RES
            mod = o.modifiers.new("remesh", "REMESH")
            mod.mode, mod.voxel_size = "VOXEL", voxel
            apply_modifiers(o)
            triangulate(o)
            info = {"remeshed": rnd(voxel)}
    return info


REMESH_RES = 200  # stalled decimation: voxel size = diagonal / this (fine enough to keep thin parts)


def export_glb(path, objs):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True)


def bbox(objs):
    pts = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def image_nodes(o):
    for mat in o.data.materials:
        if mat and mat.node_tree:
            for n in mat.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    yield mat, n


# ---------------------------------------------------------------- steps

def op_geometry(s):
    """Import a source mesh, clean it up and apply part transforms. Keeps source UVs/materials."""
    p = s["params"]
    o = import_any(s["src"])
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=p.get("merge_distance", 1e-5))
    bmesh.ops.delete(bm, geom=[e for e in bm.edges if not e.link_faces], context="EDGES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    if p.get("recalc_normals", True):
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if p.get("fit"):  # a swapped-in source takes the old shape's size and base position
        fit_to(bm, p["fit"])
    scale = p.get("scale")
    if scale:
        xs, ys, zs = ([v.co[i] for v in bm.verts] for i in range(3))
        pivot = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                        min(zs) if p.get("pivot", "base") == "base" else (min(zs) + max(zs)) / 2))
        for v in bm.verts:
            v.co = pivot + Vector(tuple(a * b for a, b in zip(v.co - pivot, scale)))
    if p.get("offset"):
        bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector(p["offset"]))
    bm.to_mesh(o.data)
    bm.free()
    export_glb(s["out"], [o])
    return {"tris": tris(o.data), "verts": len(o.data.vertices), "bbox": [list(map(rnd, c)) for c in bbox([o])]}


def rnd(x):
    return round(float(x), 5)


def fit_to(bm, fit):
    """Scale and move bm so its box matches fit {lo, hi, mode}: uniform keeps proportions
    (largest side matches), stretch matches every axis. Bases line up at the box bottom-centre."""
    xs, ys, zs = ([v.co[i] for v in bm.verts] for i in range(3))
    lo, hi = Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))
    t_lo, t_hi = Vector(fit["lo"]), Vector(fit["hi"])
    size, t_size = hi - lo, t_hi - t_lo
    if fit.get("mode") == "stretch":
        sc = Vector(tuple(t / (n or 1.0) for t, n in zip(t_size, size)))
    else:
        sc = Vector((max(t_size) / (max(size) or 1.0),) * 3)
    base = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    t_base = Vector(((t_lo.x + t_hi.x) / 2, (t_lo.y + t_hi.y) / 2, t_lo.z))
    for v in bm.verts:
        v.co = t_base + Vector(tuple(a * b for a, b in zip(v.co - base, sc)))


def op_build(s):
    """Run Claude's modelling code (with the kit, see kit.py) and export one GLB per part: glow
    materials become their own glow_<material> part (Neon in Roblox), everything else is "main".
    Units: the code works in studs; the GLBs are in metres like every other source."""
    sys.path.insert(0, str(Path(__file__).parent))
    import importlib
    import kit
    importlib.reload(kit)
    ns = {k: getattr(kit, k) for k in kit.__all__}
    try:
        exec(compile(s["code"], "<build>", "exec"), ns)
    except Exception as e:
        tb = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == "<build>"]
        raise RuntimeError(f"build code line {tb[-1].lineno if tb else '?'}: {type(e).__name__}: {e}") from None
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH" and len(o.data.polygons)]
    if not objs:
        raise ValueError("the build code made no meshes")
    groups, glow = {}, {}
    rig = any(o.get("part") in kit.R15 for o in objs)
    if rig:
        loose = sorted({o.name for o in objs if o.get("part") not in kit.R15})
        if loose:
            raise ValueError(f"R15 character: tag every piece with body(part, ...); untagged: {', '.join(loose[:8])}")
    for o in objs:
        o.data.transform(o.matrix_world)
        o.matrix_world = Matrix()
        g = next((m for m in o.data.materials if m and m.get("glow")), None)
        part = o.get("part") or (f"glow_{g.name}" if g else "main")
        if g:
            glow[part] = [rnd(c) for c in g.diffuse_color[:3]]
        groups.setdefault(part, []).append(o)
    lo, hi = bbox(objs)
    out = Path(s["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    if rig:
        (out / "rig_mesh.json").write_text(json.dumps(rig_mesh(groups)))
    parts, centres = {}, {}
    for part, group in groups.items():
        bpy.ops.object.select_all(action="DESELECT")
        for o in group:
            o.select_set(True)
        bpy.context.view_layer.objects.active = group[0]
        if len(group) > 1:
            bpy.ops.object.join()
        o = bpy.context.view_layer.objects.active
        o.name = part
        c_lo, c_hi = bbox([o])
        centres[part] = [rnd(x) for x in (c_lo + c_hi) / 2]
        o.data.transform(Matrix.Scale(kit.STUD, 4))
        export_glb(out / f"{part}.glb", [o])
        parts[part] = tris(o.data)
    return {"parts": parts, "glow": glow, "tris": sum(parts.values()), "centres": centres,
            "rig": "r15" if rig else None, "missing": [p for p in kit.R15 if rig and p not in parts],
            "size_studs": [rnd(x) for x in (hi - lo)], "materials": len(bpy.data.materials)}


def rig_mesh(groups) -> dict:
    """{part: [{mat, color, glow, c: centre, size, t: [x,y,z]*3 per triangle around c]}} per material, in rig
    space (Roblox axes: x = -kit x, y = kit z, z = kit y; studs): Studio builds these as MeshParts."""
    out = {}
    for part, group in groups.items():
        by_mat = {}
        for o in group:
            bm = bmesh.new()
            bm.from_mesh(o.data)
            bmesh.ops.triangulate(bm, faces=bm.faces[:])
            for f in bm.faces:
                m = o.data.materials[f.material_index] if o.data.materials else None
                key = m.name if m else "_"
                tri = [(-v.co.x, v.co.z, v.co.y) for v in f.verts]
                by_mat.setdefault(key, {"color": [rnd(c) for c in (m.diffuse_color[:3] if m else (0.8, 0.8, 0.8))],
                                        "glow": bool(m and m.get("glow")), "tris": []})["tris"].append(tri)
            bm.free()
        pieces = []
        for key, d in by_mat.items():
            pts = [p for t in d["tris"] for p in t]
            lo = [min(p[i] for p in pts) for i in range(3)]
            hi = [max(p[i] for p in pts) for i in range(3)]
            c = [(a + b) / 2 for a, b in zip(lo, hi)]
            flat = [round(p[i] - c[i], 3) for t in d["tris"] for p in t for i in range(3)]
            pieces.append({"mat": key, "color": d["color"], "glow": d["glow"], "c": [round(x, 3) for x in c],
                           "size": [round(max(b - a, 0.05), 3) for a, b in zip(lo, hi)], "t": flat})
        out[part] = pieces
    return out


def op_measure(s):
    return {"bbox": [list(map(rnd, c)) for c in bbox([import_any(s["src"])])]}


def op_topology(s):
    o = import_any(s["src"])
    before = tris(o.data)
    info = decimate_to(o, s["params"]["target_tris"])
    export_glb(s["out"], [o])
    return {"tris_in": before, "tris": tris(o.data), **info}


def op_uv(s):
    """Replace all UVs with a fresh non-overlapping layout for baking."""
    p = s["params"]
    o = import_any(s["src"])
    me = o.data
    for layer in list(me.uv_layers):
        me.uv_layers.remove(layer)
    me.uv_layers.new(name="UVMap")
    me.materials.clear()
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(p.get("angle", 66)), island_margin=p.get("margin", 0.02))
    bpy.ops.object.mode_set(mode="OBJECT")
    export_glb(s["out"], [o])
    return {"tris": tris(me)}


def new_image_material(name, size):
    img = bpy.data.images.new(name, size, size, alpha=False)
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except AttributeError:
        pass
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.nodes.active = tex
    return mat, img, tex


def pixels(img):
    px = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(-1, 4)


def bake(sources, target, type, **kw):
    bpy.ops.object.select_all(action="DESELECT")
    for o in sources + [target]:
        o.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.bake(type=type, use_selected_to_active=bool(sources), **kw)


def subject_rect(img, inset=0.02):
    """Object's UV rect (u0, v0, u1, v1) and mean colour in a reference image.
    The object is where alpha is set, else where pixels differ from the corner colour."""
    w, h = img.size
    px = pixels(img).reshape(h, w, 4)
    if px[..., 3].min() < 0.9:
        mask = px[..., 3] > 0.5
    else:
        bg = np.median(px[[0, 0, -1, -1], [0, -1, 0, -1], :3], axis=0)
        mask = np.abs(px[..., :3] - bg).max(axis=2) > 0.08
    rows, cols = np.where(mask.any(1))[0], np.where(mask.any(0))[0]
    if not len(rows):
        return (0.0, 0.0, 1.0, 1.0), px[..., :3].reshape(-1, 3).mean(0)
    u0, v0, u1, v1 = cols[0] / w, rows[0] / h, (cols[-1] + 1) / w, (rows[-1] + 1) / h
    du, dv = (u1 - u0) * inset, (v1 - v0) * inset  # keep background edge pixels out
    return (u0 + du, v0 + dv, u1 - du, v1 - dv), px[mask][:, :3].mean(0)


def projection_source(lo, image_path):
    """Copy of `lo` with the reference image planar-projected from the front (-Y), fitted to the
    object's silhouette in the image. Generators treat the input image as the object's front."""
    hi = lo.copy()
    hi.data = lo.data.copy()
    bpy.context.scene.collection.objects.link(hi)
    me = hi.data
    img = bpy.data.images.load(str(image_path))
    (u0, v0, u1, v1), mean = subject_rect(img)
    b0, b1 = bbox([hi])
    w, h = (b1.x - b0.x) or 1.0, (b1.z - b0.z) or 1.0
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    vi = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", vi)
    u = u0 + (co[vi, 0] - b0.x) / w * (u1 - u0)
    v = v0 + (co[vi, 2] - b0.z) / h * (v1 - v0)
    uv = me.uv_layers.new(name="proj")
    uv.data.foreach_set("uv", np.stack([u, v], 1).ravel())
    mat, _, tex = new_image_material("proj", 4)
    tex.image = img
    uvn = mat.node_tree.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "proj"
    nt = mat.node_tree
    nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
    # Faces turned away from the front would only get smeared edge pixels: fade them to the mean colour.
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs[0])
    absn = nt.nodes.new("ShaderNodeMath")
    absn.operation = "ABSOLUTE"
    nt.links.new(sep.outputs["Y"], absn.inputs[0])
    ramp = nt.nodes.new("ShaderNodeMapRange")  # |n.y| 0.25..0.6 -> 0..1
    ramp.inputs["From Min"].default_value, ramp.inputs["From Max"].default_value = 0.25, 0.6
    nt.links.new(absn.outputs[0], ramp.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    a = next(i for i in mix.inputs if i.name == "A" and i.type == "RGBA")
    b = next(i for i in mix.inputs if i.name == "B" and i.type == "RGBA")
    if not img.is_float:  # byte images report sRGB pixels; sockets take linear colour
        mean = np.where(mean <= 0.04045, mean / 12.92, ((mean + 0.055) / 1.055) ** 2.4)
    a.default_value = (*map(float, mean), 1.0)
    nt.links.new(ramp.outputs[0], mix.inputs[0])
    nt.links.new(tex.outputs["Color"], b)
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    nt.links.new(next(o for o in mix.outputs if o.type == "RGBA"), bsdf.inputs["Base Color"])
    me.materials.clear()
    me.materials.append(mat)
    return hi


AO_DEFAULT = {"bake": 0.0, "project": 0.35, "flat": 0.75, "transfer": 0.0}  # a transferred texture has its AO
TRANSFER_MIN_COVER = 0.85  # share of new verts that must lie near the old surface to bake from it
TRANSFER_TOL = 0.03  # 'near' = within this x the new part's diagonal


def op_surface(s):
    """Make the part's base-color texture on its UV layout. Modes:

    bake    - bake from the textured geometry layer (generator texture), selected-to-active. A
              reshaped or re-decimated part keeps its texture without regenerating it.
    project - planar-project the reference image from the front (shape-only generators).
    flat    - white x ambient occlusion; the colour comes from finish tint (cheap to change).
    (s["transfer"]) - bake the old textured surface onto new geometry/UVs; falls back to project
              when the shapes differ too much (cover < TRANSFER_MIN_COVER) and there's an image.
    auto    - bake if the geometry has a texture, else project if there's an image, else flat.
    """
    p = s["params"]
    size = p["tex_size"]
    hi = import_any(s["src"])
    lo = import_any(s["target"])
    mode = p.get("mode", "auto")
    cover = None
    if s.get("transfer"):  # keep the old texture on new geometry / new UVs
        cover = coverage(hi, lo)
        mode = "transfer" if cover >= TRANSFER_MIN_COVER or not s.get("image") else "project"
    elif mode == "auto":
        mode = "bake" if has_colour(hi) else "project" if s.get("image") else "flat"
    if mode == "project":
        if not s.get("image"):
            raise ValueError("project mode needs an image")
        bpy.data.objects.remove(hi)
        hi = projection_source(lo, s["image"])
    mat, img, _ = new_image_material(f"{s['part']}_basecolor", size)
    lo.data.materials.clear()
    lo.data.materials.append(mat)

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    b0, b1 = bbox([lo])
    diag = (b1 - b0).length or 1.0
    margin = p.get("margin", 4)
    if mode == "flat":
        base = np.ones((size * size, 4), dtype=np.float32)
    else:
        # (cage, max ray) x diagonal. project: the source coincides with the target. transfer: the old
        # surface may sit up to TRANSFER_TOL outside the new one, so the cage must reach past it.
        cage, ray = {"project": (0.01, 0.03), "transfer": (TRANSFER_TOL + 0.01, 0.12)}.get(mode, (0.02, 0.1))
        bake([hi], lo, "DIFFUSE", pass_filter={"COLOR"}, margin=margin,
             cage_extrusion=cage * diag, max_ray_distance=ray * diag)
        base = pixels(img)
    bpy.data.objects.remove(hi)
    ao = p.get("ao", AO_DEFAULT[mode])
    if ao > 0:
        scene.cycles.samples = 16
        bake([], lo, "AO", margin=margin)
        base[:, :3] *= 1 - ao * (1 - pixels(img)[:, :1])
    base[:, 3] = 1
    img.pixels.foreach_set(base.ravel())
    Path(s["png"]).parent.mkdir(parents=True, exist_ok=True)
    img.filepath_raw = s["png"]
    img.file_format = "PNG"
    img.save()
    mean = base[:, :3].mean(axis=0)
    export_glb(s["out"], [lo])
    stats = {"tex": size, "mode": mode, "mean_rgb": [round(float(c), 3) for c in mean]}
    if cover is not None:
        stats["cover"] = round(cover, 3)
    return stats


def has_colour(o) -> bool:
    """True if the mesh carries colour worth baking: an image texture, or materials whose base colours
    aren't all the same plain default (e.g. a script-built model with a material per part)."""
    if any(True for _ in image_nodes(o)):
        return True
    cols = set()
    for mat in o.data.materials:
        bsdf = mat and mat.node_tree and next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        c = tuple(round(x, 2) for x in (bsdf.inputs["Base Color"].default_value[:3] if bsdf else mat.diffuse_color[:3])) if mat else None
        if c is not None:
            cols.add(c)
    return len(cols) > 1 or bool(cols - {(0.8, 0.8, 0.8), (1.0, 1.0, 1.0)})


def coverage(src, target, tol=TRANSFER_TOL):
    """Share of target verts within tol x (target diagonal) of the src surface."""
    tree = BVHTree.FromObject(src, bpy.context.evaluated_depsgraph_get())
    b0, b1 = bbox([target])
    lim = tol * ((b1 - b0).length or 1.0)
    vs = target.data.vertices
    near = sum(1 for v in vs if (hit := tree.find_nearest(v.co))[0] is not None and hit[3] <= lim)
    return near / (len(vs) or 1)


def op_collision(s):
    o = import_any(s["src"])
    bm = bmesh.new()
    for v in o.data.vertices:
        bm.verts.new(v.co)
    res = bmesh.ops.convex_hull(bm, input=bm.verts[:])
    drop = list({g for g in res["geom_interior"] + res["geom_unused"] if isinstance(g, bmesh.types.BMVert)})
    bmesh.ops.delete(bm, geom=drop, context="VERTS")
    me = bpy.data.meshes.new(f"{s['part']}_collision")
    bm.to_mesh(me)
    bm.free()
    hull = bpy.data.objects.new(me.name, me)
    bpy.context.scene.collection.objects.link(hull)
    bpy.data.objects.remove(o)
    decimate_to(hull, s["params"]["max_tris"])
    export_glb(s["out"], [hull])
    return {"tris": tris(hull.data)}


TARGETS = {
    "roblox": ["glb", "fbx"],
    "godot": ["glb"],
    "unity": ["fbx"],
}


def validate(objs, budget):
    per, total, nonman, uv_ok, tex = {}, 0, 0, True, 0
    for o in objs:
        me = o.data
        t = tris(me)
        per[o.name] = t
        total += t
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)  # glTF splits verts at UV seams
        nonman += sum(1 for e in bm.edges if not e.is_manifold)
        bm.free()
        uv_ok &= len(me.uv_layers) > 0
        for _, n in image_nodes(o):
            tex = max(tex, *n.image.size)
    fails = []
    if total > budget["max_tris"]:
        fails.append(f"tris {total}>{budget['max_tris']}")
    fails += [f"{k} tris {t}>{budget['max_part_tris']}" for k, t in per.items() if t > budget["max_part_tris"]]
    if tex > budget["max_tex"]:
        fails.append(f"tex {tex}>{budget['max_tex']}")
    if not uv_ok:
        fails.append("missing uv")
    lo, hi = bbox(objs)
    return {"ok": not fails, "fails": fails, "tris": total, "max_tris": budget["max_tris"], "parts": per,
            "tex": tex, "uv": uv_ok, "non_manifold_edges": nonman,
            "size_m": [round(x, 3) for x in hi - lo]}


def op_export(s):
    """Combine parts, apply finish params (tint/roughness/metallic), scale, validate and export."""
    p, name = s["params"], s["name"]
    out = Path(s["out_dir"])
    for old in [*out.glob(f"{name}.*"), *out.glob(f"textures/{name}_*"), *out.glob(f"collision/{name}_*")]:
        old.unlink()  # only this export's own files: copies saved alongside them survive
    (out / "textures").mkdir(parents=True, exist_ok=True)
    objs = []
    for part, spec in s["parts"].items():
        o = import_any(spec["surface"])
        o.name = o.data.name = part
        f = spec["finish"]
        tint = np.array(f.get("tint", [1, 1, 1]), dtype=np.float32)
        for mat, n in image_nodes(o):
            mat.name = f"{name}_{part}"
            bsdf = next(x for x in mat.node_tree.nodes if x.type == "BSDF_PRINCIPLED")
            bsdf.inputs["Roughness"].default_value = f.get("roughness", 0.8)
            bsdf.inputs["Metallic"].default_value = f.get("metallic", 0.0)
            w, h = n.image.size
            px = np.empty(w * h * 4, dtype=np.float32)
            n.image.pixels.foreach_get(px)
            px = px.reshape(-1, 4)
            px[:, :3] = np.clip(px[:, :3] * tint, 0, 1)
            img = bpy.data.images.new(f"{name}_{part}", w, h, alpha=False)
            img.pixels.foreach_set(px.ravel())
            img.filepath_raw = str(out / "textures" / f"{name}_{part}.png")
            img.file_format = "PNG"
            img.save()
            n.image = img
        objs.append(o)

    lo, hi = bbox(objs)
    s_fac = p["scale_to"] / max(hi - lo) if p.get("scale_to") else 1.0
    base = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    if p.get("keep_origin"):  # a rigged character: pieces stay where the rig's joints are
        s_fac, base = 1.0, Vector((0, 0, 0))
    for o in objs:
        o.data.transform(Matrix.Scale(s_fac, 4) @ Matrix.Translation(-base))
        c_lo, c_hi = bbox([o])
        c = (c_lo + c_hi) / 2  # each part's origin at its own centre (Roblox MeshPart pivot)
        o.data.transform(Matrix.Translation(-c))
        o.location = c
    bpy.context.view_layer.update()

    report = validate(objs, s["budget"])
    files = []
    for fmt in TARGETS[p.get("target", "roblox")]:
        path = out / f"{name}.{fmt}"
        if fmt == "glb":
            export_glb(path, objs)
        else:
            bpy.ops.object.select_all(action="DESELECT")
            for o in objs:
                o.select_set(True)
            bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, object_types={"MESH"},
                                     axis_forward="-Z", axis_up="Y", path_mode="COPY",
                                     embed_textures=True, mesh_smooth_type="FACE")
        files.append(path.name)
    if s.get("collisions"):
        (out / "collision").mkdir(exist_ok=True)
        for part, src in s["collisions"].items():
            shutil.copy(src, out / "collision" / f"{name}_{part}_collision.glb")
    return {**report, "files": files}


PREVIEW_VIEWS = [(0, -1, 0.25), (1, 0, 0.25), (0, 1, 0.25), (1, -1, 0.9)]  # front, right, back, 3/4


def op_preview(s):
    """Render panels with Workbench into one PNG at s["out"].

    s["panels"]: list of {files, shade, view, label, vfx}; default is s["files"] textured from 4 views.
    shade: texture | clay (grey) | wire (grey + edges) | colour (each face one flat colour sampled
    from its texture, x the file's tint in s["tints"]: the low-poly palette view).
    view: index into PREVIEW_VIEWS. vfx: effects drawn as coloured particle blobs (see vfx_blobs).
    layout: grid (2x2, s["size"] square) | strip (one row, each panel s["size"] square).
    Each panel is framed on its own objects.
    """
    strip = s.get("layout") == "strip"
    panels = s.get("panels") or [{"files": s["files"], "shade": "texture", "view": i} for i in range(4)]
    panels = panels if strip else panels[:4]
    px_n = s.get("size", 256) if strip else s.get("size", 256) // 2
    cols_n, rows_n = (len(panels), 1) if strip else (2, 2)
    tints = s.get("tints", {})
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_WORKBENCH"
    except TypeError as e:
        raise RuntimeError(f"no workbench engine: {e}")
    scene.display.shading.light = "STUDIO"
    scene.render.resolution_x = scene.render.resolution_y = px_n
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    tile = np.zeros((rows_n * px_n, cols_n * px_n, 4), dtype=np.float32)
    tmp = Path(s["out"]).with_suffix(".view.png")
    for i, pn in enumerate(panels):
        objs = [import_any(f) for f in pn["files"]]
        lo, hi = bbox(objs)
        shade = pn.get("shade", "texture")
        scene.display.shading.color_type = {"texture": "TEXTURE", "colour": "VERTEX"}.get(shade, "OBJECT")
        extra = vfx_blobs(pn.get("vfx") or {}, lo, hi)
        if extra:  # frame the effects too
            lo, hi = bbox(objs + extra)
        c, ext = (lo + hi) / 2, max(hi - lo)
        for o, f in zip(objs, pn["files"]):
            o.color = (*CLAY, 1.0)
            if shade == "colour":
                face_colours(o, tints.get(f, (1, 1, 1)))
            if shade == "wire":
                w = bpy.data.objects.new(o.name + "_wire", o.data)
                scene.collection.objects.link(w)
                mod = w.modifiers.new("wire", "WIREFRAME")
                mod.thickness = ext * 1.5 / px_n * 0.6  # ~half a pixel: dense meshes read as shading
                w.color = (0.12, 0.22, 0.45, 1.0)
                extra.append(w)
        ortho = ext * (1.7 if pn.get("label") else 1.5)
        cam.data.ortho_scale = ortho
        cam.data.clip_end = ext * 10
        d = Vector(PREVIEW_VIEWS[pn.get("view", 3)]).normalized()
        cam.location = c + d * ext * 3
        cam.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
        if pn.get("label"):
            extra.append(label(pn["label"], cam, ortho, ext))
        scene.render.filepath = str(tmp)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(tmp))
        px = pixels(img).reshape(px_n, px_n, 4)
        bpy.data.images.remove(img)
        row, col = (0, i) if strip else (1 - i // 2, i % 2)  # pixel rows start at the bottom
        tile[row * px_n:(row + 1) * px_n, col * px_n:(col + 1) * px_n] = px
        for o in extra + objs:
            bpy.data.objects.remove(o)
    tmp.unlink()
    if strip:  # thin dark separators between panels
        for k in range(1, cols_n):
            tile[:, k * px_n - 1:k * px_n + 1, :3] = 0.08
    h, w = tile.shape[:2]
    out = bpy.data.images.new("preview", w, h, alpha=False)
    out.pixels.foreach_set(tile.ravel())
    out.filepath_raw = s["out"]
    out.file_format = "PNG"
    out.save()
    return {"size": [w, h]}


def flat_material(name, rgb):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*rgb, 1.0)  # what Workbench shows for untextured surfaces
    return mat


def label(text, cam, ortho, ext):
    """White caption in the top margin of the camera view."""
    cu = bpy.data.curves.new("label", "FONT")
    cu.body = text
    cu.align_x = "CENTER"
    cu.size = ortho * 0.09
    o = bpy.data.objects.new("label", cu)
    bpy.context.scene.collection.objects.link(o)
    o.parent = cam
    o.location = (0, ortho * 0.40, -ext)
    o.color = (0.95, 0.95, 0.95, 1.0)
    cu.materials.append(flat_material("label", (0.95, 0.95, 0.95)))
    return o


# How each effect type is sketched in previews: blob count, radius (x model size), and where they go
# as (x/y spread, z from, z to) in units of the model's half-width / height above its base.
VFX_SKETCH = {"fire": (90, 0.07, (0.9, 0.3, 1.3)), "smoke": (25, 0.10, (0.5, 0.9, 1.6)),
              "sparkles": (40, 0.025, (1.2, 0.0, 1.15)), "glow": (60, 0.03, (1.25, -0.05, 1.1))}


def vfx_blobs(effects, lo, hi):
    """Approximate each effect as a cloud of coloured icospheres (Roblox renders the real thing)."""
    objs = []
    size, base = hi - lo, Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    model = max(size)
    for k, (name, fx) in enumerate(sorted(effects.items())):
        sketch = fx.get("sketch", fx.get("type"))
        n, r, (spread, z0, z1) = VFX_SKETCH.get(sketch, VFX_SKETCH["sparkles"])
        rng = np.random.default_rng(k)
        n = max(1, int(n * fx.get("rate", 1.0) ** 0.5))
        bm = bmesh.new()
        for _ in range(n):
            t = rng.uniform()  # 0 = bottom of the effect, 1 = top
            z = lo.z + size.z * (z0 + (z1 - z0) * t)
            fire = sketch == "fire"
            taper = 1 - 0.5 * t if fire else 1.0
            x = base.x + size.x / 2 * spread * taper * rng.uniform(-1, 1)
            y = base.y + size.y / 2 * spread * taper * rng.uniform(-1, 1)
            rad = model * r * fx.get("size", 1.0) * rng.uniform(0.5, 1.2) * taper
            if fire:  # flame tongues: upright cones
                bmesh.ops.create_cone(bm, cap_ends=True, segments=5, radius1=rad, radius2=0, depth=rad * 3,
                                      matrix=Matrix.Translation((x, y, z)))
            else:
                bmesh.ops.create_icosphere(bm, subdivisions=1, radius=rad, matrix=Matrix.Translation((x, y, z)))
        me = bpy.data.meshes.new(f"vfx_{name}")
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(f"vfx_{name}", me)
        bpy.context.scene.collection.objects.link(o)
        rgb = fx.get("color") or (1, 1, 1)
        o.color = (*rgb, 1.0)
        me.materials.append(flat_material(f"vfx_{name}", rgb))
        objs.append(o)
    return objs


CLAY = (0.72, 0.72, 0.72)


def face_colours(o, tint):
    """Give every face one colour: its texture sampled at the face's UV centre, x tint."""
    me = o.data
    n = len(me.polygons)
    img = next((nd.image for _, nd in image_nodes(o)), None)
    cols = np.tile(np.array([*CLAY, 1.0], dtype=np.float32), (n, 1))
    start, total = np.empty(n, dtype=np.int32), np.empty(n, dtype=np.int32)
    me.polygons.foreach_get("loop_start", start)
    me.polygons.foreach_get("loop_total", total)
    if img is not None and me.uv_layers:
        w, h = img.size
        px = pixels(img).reshape(h, w, 4)
        uv = np.empty(len(me.loops) * 2, dtype=np.float32)
        me.uv_layers.active.data.foreach_get("uv", uv)
        c = np.add.reduceat(uv.reshape(-1, 2), start) / total[:, None]
        x = np.clip((c[:, 0] % 1.0) * w, 0, w - 1).astype(int)
        y = np.clip((c[:, 1] % 1.0) * h, 0, h - 1).astype(int)
        cols = px[y, x].copy()
        rgb = cols[:, :3]  # texture pixels are sRGB; colour attributes are linear
        cols[:, :3] = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    cols[:, :3] *= np.array(tint, dtype=np.float32)
    cols[:, 3] = 1.0
    order = np.argsort(start)  # colour attributes live on corners, not faces: repeat per corner
    per_loop = cols[np.repeat(order, total[order])]
    attr = me.color_attributes.new("face_colour", "FLOAT_COLOR", "CORNER")
    attr.data.foreach_set("color", per_loop.ravel())
    me.color_attributes.active_color = attr


def op_video(s):
    """Encode an image sequence (s["frames"], in order) to an H.264 MP4 at s["fps"] with Blender's ffmpeg."""
    frames = [Path(f) for f in s["frames"]]
    scene = bpy.context.scene
    scene.sequence_editor_create()
    first = bpy.data.images.load(str(frames[0]))
    w, h = first.size
    bpy.data.images.remove(first)
    seqs = scene.sequence_editor
    coll = seqs.strips if hasattr(seqs, "strips") else seqs.sequences  # renamed in Blender 4.4
    try:
        strip = coll.new_image("frames", str(frames[0]), 1, 1, fit_method="FIT")
    except TypeError:
        strip = coll.new_image("frames", str(frames[0]), 1, 1)
    for f in frames[1:]:
        strip.elements.append(f.name)
    scene.frame_start, scene.frame_end = 1, len(frames)
    scene.render.fps = int(s.get("fps", 15))
    k = s.get("width", w) / w  # even dimensions for H.264
    scene.render.resolution_x, scene.render.resolution_y = int(w * k) // 2 * 2, int(h * k) // 2 * 2
    scene.render.resolution_percentage = 100
    if hasattr(scene.render.image_settings, "media_type"):  # Blender 5: pick video before the format
        scene.render.image_settings.media_type = "VIDEO"
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.filepath = s["out"]
    scene.render.use_file_extension = False
    bpy.ops.render.render(animation=True)
    return {"frames": len(frames), "fps": scene.render.fps}


def op_unpack_video(s):
    """Decode a video (s["src"]) to PNG frames in s["out_dir"] at s["width"] pixels wide."""
    scene = bpy.context.scene
    scene.sequence_editor_create()
    seqs = scene.sequence_editor
    coll = seqs.strips if hasattr(seqs, "strips") else seqs.sequences
    try:
        strip = coll.new_movie("clip", s["src"], 1, 1, fit_method="FIT")
    except TypeError:
        strip = coll.new_movie("clip", s["src"], 1, 1)
    n = strip.frame_final_duration
    w, h = strip.elements[0].orig_width, strip.elements[0].orig_height
    k = s.get("width", w) / w
    scene.render.resolution_x, scene.render.resolution_y = int(w * k) // 2 * 2, int(h * k) // 2 * 2
    scene.render.resolution_percentage = 100
    scene.frame_start, scene.frame_end = 1, n
    if hasattr(scene.render.image_settings, "media_type"):
        scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(Path(s["out_dir"]) / "####")
    bpy.ops.render.render(animation=True)
    fps = scene.render.fps / scene.render.fps_base
    return {"frames": n, "fps": round(fps, 3)}


def op_validate(s):
    o = import_any(s["src"])
    return validate([o], s["budget"])


def op_studio_mesh(s):
    """An exported GLB as data Studio builds without an upload (placing it live): per part
    {c: centre, size, v: [x,y,z..] around c, f: [a,b,c..] 0-based, uv: [u,v..], color, tex: png name}.
    Roblox axes (x = -x, y = z, z = y; GLB metres -> studs); uv v flipped (Roblox images start top-left). One vertex
    per (corner, uv) so seams keep their UVs; textures saved next to `out`, at most tex_size px."""
    sys.path.insert(0, str(Path(__file__).parent))
    import kit
    bpy.ops.import_scene.gltf(filepath=s["glb"])
    out = Path(s["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    parts = {}
    for o in [o for o in bpy.data.objects if o.type == "MESH"]:
        me = o.data
        me.transform(Matrix.Scale(1 / kit.STUD, 4) @ o.matrix_world)
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        uvl = bm.loops.layers.uv.active
        verts, uvs, faces, index = [], [], [], {}
        for f in bm.faces:
            tri = []
            for loop in f.loops:
                u = tuple(loop[uvl].uv) if uvl else (0.0, 0.0)
                key = (loop.vert.index, round(u[0], 4), round(u[1], 4))
                if key not in index:
                    co = loop.vert.co
                    index[key] = len(verts)
                    verts.append((-co.x, co.z, co.y))
                    uvs.append((u[0], 1 - u[1]))
                tri.append(index[key])
            faces.append(tri)  # the axis swap is a rotation (det +1): winding stays as it is, like rig_mesh
        bm.free()
        if not faces:
            continue
        lo = [min(p[i] for p in verts) for i in range(3)]
        hi = [max(p[i] for p in verts) for i in range(3)]
        c = [(a + b) / 2 for a, b in zip(lo, hi)]
        part = {"c": [rnd(x) for x in c], "size": [rnd(max(b - a, 0.05)) for a, b in zip(lo, hi)],
                "v": [round(p[i] - c[i], 3) for p in verts for i in range(3)], "f": [i for t in faces for i in t],
                "uv": [round(x, 4) for p in uvs for x in p], "color": [0.8, 0.8, 0.8], "tex": None}
        mat = me.materials[0] if me.materials else None
        bsdf = mat and mat.node_tree and next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf:
            part["color"] = [rnd(x) for x in bsdf.inputs["Base Color"].default_value[:3]]
        img = next((n.image for _, n in image_nodes(o)), None)
        if img and img.size[0]:
            n = min(s.get("tex_size", 256), img.size[0])
            img = img.copy()
            img.scale(n, n)
            img.filepath_raw = str(out.parent / f"{o.name}.png")
            img.file_format = "PNG"
            img.save()
            part["tex"] = f"{o.name}.png"
            part["color"] = [1, 1, 1]  # the texture carries the colour
        parts[o.name] = part
    out.write_text(json.dumps({"units": "studs", "parts": parts}, separators=(",", ":")))
    return {"parts": len(parts), "tris": sum(len(p["f"]) // 3 for p in parts.values())}


OPS = {k[3:]: v for k, v in globals().items() if k.startswith("op_")}


def main():
    job_path = sys.argv[sys.argv.index("--") + 1]
    job = json.loads(Path(job_path).read_text())
    results, error = [], None
    for i, step in enumerate(job["steps"]):
        try:
            reset()
            results.append({"stats": OPS[step["op"]](step)})
        except Exception as e:  # one-line error back to the host
            tb = [f for f in traceback.extract_tb(e.__traceback__) if f.filename.endswith("worker.py")][-1]
            error = f"step {i} {step.get('op')}[{step.get('part', '')}]: {type(e).__name__}: {e} (worker.py:{tb.lineno})"
            error = error.replace("\n", " ")[:300]
            break
    Path(job["result"]).write_text(json.dumps({"results": results, "error": error}))


main()
