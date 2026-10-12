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


def decimate_to(o, target: int):
    triangulate(o)
    for _ in range(4):
        n = tris(o.data)
        if n <= target:
            break
        mod = o.modifiers.new("decimate", "DECIMATE")
        mod.ratio = max(target / n * 0.98, 0.001)
        apply_modifiers(o)
        triangulate(o)


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
    return {"tris": tris(o.data), "verts": len(o.data.vertices)}


def op_topology(s):
    o = import_any(s["src"])
    before = tris(o.data)
    decimate_to(o, s["params"]["target_tris"])
    export_glb(s["out"], [o])
    return {"tris_in": before, "tris": tris(o.data)}


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


def op_surface(s):
    """Bake base color from a textured source mesh onto the UV'd target (selected-to-active).

    The source is the part's geometry layer (still carrying the generator texture), so a
    reshaped or re-decimated part keeps its texture without regenerating it.
    """
    p = s["params"]
    hi = import_any(s["src"])
    lo = import_any(s["target"])
    size = p["tex_size"]
    img = bpy.data.images.new(f"{s['part']}_basecolor", size, size, alpha=False)
    mat = bpy.data.materials.new(s["part"])
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
    lo.data.materials.clear()
    lo.data.materials.append(mat)

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    lo_min, lo_max = bbox([lo])
    diag = (lo_max - lo_min).length or 1.0
    bpy.ops.object.select_all(action="DESELECT")
    hi.select_set(True)
    lo.select_set(True)
    bpy.context.view_layer.objects.active = lo
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, use_selected_to_active=True,
                        cage_extrusion=0.02 * diag, max_ray_distance=0.1 * diag,
                        margin=p.get("margin", 4))
    Path(s["png"]).parent.mkdir(parents=True, exist_ok=True)
    img.filepath_raw = s["png"]
    img.file_format = "PNG"
    img.save()
    px = np.empty(size * size * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    mean = px.reshape(-1, 4)[:, :3].mean(axis=0)
    bpy.data.objects.remove(hi)
    export_glb(s["out"], [lo])
    return {"tex": size, "mean_rgb": [round(float(c), 3) for c in mean]}


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
    if out.exists():
        shutil.rmtree(out)
    (out / "textures").mkdir(parents=True)
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
        (out / "collision").mkdir()
        for part, src in s["collisions"].items():
            shutil.copy(src, out / "collision" / f"{name}_{part}_collision.glb")
    return {**report, "files": files}


def op_validate(s):
    o = import_any(s["src"])
    return validate([o], s["budget"])


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
