"""Runs inside one long-lived headless Blender (blender -b -P bpy_session.py) behind the Blender MCP server.

Reads one JSON command per line on stdin and answers with one line on stdout prefixed by REPLY (Blender
prints its own chatter there too). Meshes stay loaded between commands, one object per name, so Claude
can inspect, clean, check again and export without Blender starting up each time.

Commands: open, list, inspect, cleanup, run, render, export, close. Units: whatever the mesh came in
with until `scale_to` puts it in studs (1 Blender unit = 1 stud from then on).
"""
import contextlib
import io
import json
import math
import sys
import traceback
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

REPLY = "@@asset-agent@@ "
STUD = 0.28  # metres per stud (GLB files are in metres, like the rest of the harness)
ROBLOX = {"max_tris": 20000, "max_tex": 1024, "max_size": 2048}  # per MeshPart / texture / studs


# ---------------------------------------------------------------- helpers
def obj(name):
    o = bpy.data.objects.get(name)
    if o is None or o.type != "MESH":
        raise KeyError(f"no mesh '{name}' open; open it first (have: {', '.join(names()) or 'none'})")
    return o


def names():
    return [o.name for o in bpy.data.objects if o.type == "MESH"]


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def activate(o):
    bpy.ops.object.mode_set(mode="OBJECT") if bpy.context.object and bpy.context.object.mode != "OBJECT" else None
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o


def apply_mods(o):
    activate(o)
    for m in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def dims(o):
    """Size from the vertices (o.dimensions lags behind mesh edits until a depsgraph update)."""
    vs = [v.co for v in o.data.vertices]
    if not vs:
        return Vector((0, 0, 0))
    return Vector([max(v[i] for v in vs) - min(v[i] for v in vs) for i in range(3)])


def textures(o):
    out = []
    for m in o.data.materials:
        if m and m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    out.append({"material": m.name, "image": n.image.name, "size": list(n.image.size)})
    return out


# ---------------------------------------------------------------- commands
def cmd_open(path, name=None, replace=True):
    """Import a .glb/.gltf/.fbx/.obj as one joined mesh called `name` (default: the file's stem)."""
    path = Path(path)
    name = name or path.stem
    if replace and bpy.data.objects.get(name):
        cmd_close(name)
    before = set(bpy.data.objects)
    ext = path.suffix.lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    else:
        raise ValueError(f"can't open {ext} files (glb, gltf, fbx, obj)")
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH" and len(o.data.polygons)]
    if not meshes:
        raise ValueError(f"{path.name} has no mesh")
    for o in meshes:  # bake transforms into the mesh, drop empties and helpers
        o.data.transform(o.matrix_world)
        o.matrix_world = Matrix()
        o.parent = None
    for o in new:
        if o not in meshes:
            bpy.data.objects.remove(o)
    activate(meshes[0])
    for o in meshes:
        o.select_set(True)
    if len(meshes) > 1:
        bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = o.data.name = name
    o["source"] = str(path)
    return cmd_inspect(name)


def cmd_list():
    return {"meshes": [{"name": n, "tris": tris(obj(n))} for n in names()]}


def cmd_inspect(name):
    """Geometry metrics and a Roblox readiness verdict."""
    o = obj(name)
    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    size = Vector([max(v.co[i] for v in bm.verts) - min(v.co[i] for v in bm.verts) for i in range(3)]) if bm.verts else Vector()
    tol = max(size) * 1e-5 if bm.verts else 0
    dup = 0
    if bm.verts:  # vertices sitting on top of another (unwelded seams)
        seen = {}
        for v in bm.verts:
            k = tuple(round(c / tol) for c in v.co) if tol else tuple(v.co)
            dup += k in seen
            seen[k] = 1
    # the shape's topology is judged on a welded copy: exporters split vertices along UV seams on purpose,
    # which would otherwise read as holes and hundreds of pieces
    if dup:
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=tol)
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    loose_v = sum(1 for v in bm.verts if not v.link_edges)
    loose_e = sum(1 for e in bm.edges if not e.link_faces)
    degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
    # normals: how many faces would flip if made consistent (inside-out patches)
    flipped = 0
    if bm.faces:
        before = [f.normal.copy() for f in bm.faces]
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        flipped = sum(1 for f, n in zip(bm.faces, before) if f.normal.dot(n) < 0)
        if flipped > len(bm.faces) / 2:
            flipped = len(bm.faces) - flipped  # the whole mesh was inside out: count the smaller side
    islands = 0
    seen_v = set()
    for v in bm.verts:  # connected pieces
        if v.index in seen_v:
            continue
        islands += 1
        stack = [v]
        seen_v.add(v.index)
        while stack:
            u = stack.pop()
            for e in u.link_edges:
                w = e.other_vert(u)
                if w.index not in seen_v:
                    seen_v.add(w.index)
                    stack.append(w)
    uv = {"layers": [l.name for l in me.uv_layers]}
    if me.uv_layers:
        layer = bm.loops.layers.uv.active
        # rasterise the UV triangles: texels claimed by more than one face = overlap (mirrored or stacked
        # islands, which make a baked texture smear)
        out = n = 0
        G = 512
        owner, shared = {}, set()  # texel -> first face on it; texels a second face also covers
        for f in bm.faces:
            us = [l[layer].uv for l in f.loops]
            for u_ in us:
                n += 1
                out += not (0 <= u_.x <= 1 and 0 <= u_.y <= 1)
            for k in range(1, len(us) - 1):
                a, b, c = us[0], us[k], us[k + 1]
                x0, x1 = int(min(a.x, b.x, c.x) * G), int(max(a.x, b.x, c.x) * G)
                y0, y1 = int(min(a.y, b.y, c.y) * G), int(max(a.y, b.y, c.y) * G)
                d = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y)
                cells = []
                if abs(d) > 1e-12:
                    for gx in range(x0, x1 + 1):
                        for gy in range(y0, y1 + 1):
                            px, py = (gx + 0.5) / G, (gy + 0.5) / G
                            w1 = ((b.y - c.y) * (px - c.x) + (c.x - b.x) * (py - c.y)) / d
                            w2 = ((c.y - a.y) * (px - c.x) + (a.x - c.x) * (py - c.y)) / d
                            if w1 >= 0 and w2 >= 0 and w1 + w2 <= 1:
                                cells.append((gx, gy))
                if not cells:  # smaller than a texel: count its centre
                    cells = [(int((a.x + b.x + c.x) / 3 * G), int((a.y + b.y + c.y) / 3 * G))]
                for cell in cells:
                    if owner.setdefault(cell, f.index) != f.index:
                        shared.add(cell)
        uv.update(outside_0_1=round(out / max(n, 1), 3), coverage=round(len(owner) / (G * G), 3),
                  overlap=round(len(shared) / max(len(owner), 1), 3))  # share of used texels drawn twice
    bm.free()
    t = tris(o)
    tex = textures(o)
    m = {"name": name, "verts": len(me.vertices), "faces": len(me.polygons), "tris": t, "islands": islands,
         "non_manifold_edges": non_manifold, "boundary_edges": boundary, "loose_verts": loose_v,
         "loose_edges": loose_e, "duplicate_verts": dup, "degenerate_faces": degenerate,
         "flipped_faces": flipped, "size": [round(x, 3) for x in size], "units": o.get("units", "source"),
         "uv": uv, "materials": len([x for x in me.materials if x]), "textures": tex}
    issues = []
    if t > ROBLOX["max_tris"]:
        issues.append(f"{t} tris: Roblox meshes take at most {ROBLOX['max_tris']} (decimate)")
    if dup and not me.uv_layers:  # with UVs, split seams are expected; without, it's unwelded geometry
        issues.append(f"{dup} duplicate verts (merge_by_distance)")
    if flipped:
        issues.append(f"{flipped} faces point inward (recalc_normals)")
    if loose_v or loose_e:
        issues.append(f"{loose_v} loose verts, {loose_e} loose edges (delete_loose)")
    if degenerate:
        issues.append(f"{degenerate} zero-area faces (dissolve_degenerate)")
    if non_manifold:
        issues.append(f"{non_manifold} non-manifold edges (merge_by_distance, then remesh if they stay)")
    if boundary:
        issues.append(f"{boundary} open edges / holes (fill_holes, or remesh to seal)")
    if islands > 1:
        issues.append(f"{islands} separate pieces (keep_largest drops floating bits)")
    if not me.uv_layers:
        issues.append("no UVs (uv_unwrap)")
    elif uv.get("overlap", 0) > 0.05:
        issues.append(f"{uv['overlap']:.0%} of the UV space is used twice: a baked texture would smear "
                      "(uv_unwrap before bake_texture)")
    if any(max(x["size"]) > ROBLOX["max_tex"] for x in tex):
        issues.append(f"textures larger than {ROBLOX['max_tex']} px (bake_texture size={ROBLOX['max_tex']})")
    if len(tex) > 1 or m["materials"] > 1:
        issues.append(f"{m['materials']} materials: a MeshPart takes one texture (bake_texture)")
    if m["units"] != "studs":
        issues.append("not sized in studs yet (scale_to)")
    elif max(size) > ROBLOX["max_size"]:
        issues.append(f"{max(size):.0f} studs across: bigger than Roblox allows ({ROBLOX['max_size']})")
    m["issues"] = issues
    m["roblox_ready"] = not [i for i in issues if not i.startswith(("islands", f"{islands} separate"))]
    return m


# cleanup operations: name -> function(o, **params) -> note
def op_merge_by_distance(o, dist=None):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    if dist is None:
        size = max(dims(o)) or 1
        dist = size * 1e-5
    n = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=dist)
    removed = n - len(bm.verts)
    bm.to_mesh(o.data)
    bm.free()
    return f"merged {removed} verts (dist {dist:.2g})"


def op_recalc_normals(o, inside=False):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if inside:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(o.data)
    bm.free()
    return "normals made consistent" + (" (pointing in)" if inside else "")


def op_delete_loose(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    lv = [v for v in bm.verts if not v.link_edges]
    le = [e for e in bm.edges if not e.link_faces]
    bmesh.ops.delete(bm, geom=le, context="EDGES")
    bmesh.ops.delete(bm, geom=[v for v in lv if v.is_valid], context="VERTS")
    bm.to_mesh(o.data)
    bm.free()
    return f"deleted {len(lv)} loose verts, {len(le)} loose edges"


def op_dissolve_degenerate(o, dist=None):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    n = len(bm.faces)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=dist or max(dims(o)) * 1e-6)
    bm.to_mesh(o.data)
    bm.free()
    return f"dissolved {n - len(o.data.polygons)} degenerate faces"


def op_fill_holes(o, sides=0):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    b = [e for e in bm.edges if e.is_boundary]
    res = bmesh.ops.holes_fill(bm, edges=b, sides=sides)
    bm.to_mesh(o.data)
    bm.free()
    return f"filled {len(res['faces'])} holes"


def op_keep_largest(o, count=1):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.verts.ensure_lookup_table()
    comp, groups = {}, []
    for v in bm.verts:
        if v.index in comp:
            continue
        stack, g = [v], []
        comp[v.index] = len(groups)
        while stack:
            u = stack.pop()
            g.append(u)
            for e in u.link_edges:
                w = e.other_vert(u)
                if w.index not in comp:
                    comp[w.index] = len(groups)
                    stack.append(w)
        groups.append(g)
    groups.sort(key=len, reverse=True)
    drop = [v for g in groups[count:] for v in g]
    bmesh.ops.delete(bm, geom=drop, context="VERTS")
    bm.to_mesh(o.data)
    bm.free()
    return f"kept {min(count, len(groups))} of {len(groups)} pieces, dropped {len(drop)} verts"


def op_decimate(o, target_tris=None, ratio=None, planar_angle=None):
    before = tris(o)
    activate(o)
    m = o.modifiers.new("decimate", "DECIMATE")
    if planar_angle:
        m.decimate_type = "DISSOLVE"
        m.angle_limit = math.radians(planar_angle)
    else:
        m.ratio = ratio if ratio else min(1.0, (target_tris or ROBLOX["max_tris"]) / max(before, 1))
        m.use_collapse_triangulate = True
    apply_mods(o)
    return f"{before} -> {tris(o)} tris"


def op_remesh(o, voxel=None, smooth=0):
    """Voxel remesh: watertight, evenly spaced, seals holes and non-manifold edges (loses UVs/textures)."""
    before = tris(o)
    voxel = voxel or max(dims(o)) / 180
    m = o.modifiers.new("remesh", "REMESH")
    m.mode, m.voxel_size = "VOXEL", voxel
    if smooth:
        s = o.modifiers.new("smooth", "SMOOTH")
        s.factor, s.iterations = 0.5, smooth
    apply_mods(o)
    return f"remeshed at {voxel:.3g}: {before} -> {tris(o)} tris (UVs and textures are gone: unwrap and bake again)"


def op_smooth(o, iterations=5, factor=0.5):
    m = o.modifiers.new("smooth", "SMOOTH")
    m.factor, m.iterations = factor, iterations
    apply_mods(o)
    return f"smoothed x{iterations}"


def op_triangulate(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(o.data)
    bm.free()
    return f"triangulated: {len(o.data.polygons)} tris"


def op_shade_smooth(o, angle=40):
    for p in o.data.polygons:
        p.use_smooth = True
    try:
        activate(o)
        bpy.ops.object.shade_auto_smooth(angle=math.radians(angle))
    except Exception:  # older/newer Blender: plain smooth shading is fine
        pass
    return f"smooth shading (sharp above {angle} deg)"


def op_rotate(o, axis="Z", degrees=90):
    o.data.transform(Matrix.Rotation(math.radians(degrees), 4, axis.upper()))
    return f"rotated {degrees} deg about {axis}"


def op_scale_to(o, studs=None, height=None, length=None, axis=None):
    """Size it in studs: `studs` for the longest side, or `height` (Z) / `length` (Y). Then sits it on
    the ground (lowest point z=0) centred on x and y. From here on 1 unit = 1 stud."""
    d = dims(o)
    if height:
        k = height / max(d.z, 1e-9)
    elif length:
        k = length / max(d.y, 1e-9)
    else:
        k = (studs or 10) / max(max(d), 1e-9)
    o.data.transform(Matrix.Scale(k, 4))
    vs = [v.co for v in o.data.vertices]
    lo = Vector([min(v[i] for v in vs) for i in range(3)])
    hi = Vector([max(v[i] for v in vs) for i in range(3)])
    o.data.transform(Matrix.Translation(Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z))))
    o["units"] = "studs"
    d = dims(o)
    return f"scaled x{k:.3g}: {d.x:.1f} x {d.y:.1f} x {d.z:.1f} studs, on the ground"


def op_uv_unwrap(o, method="smart", angle=66, margin=0.004):
    activate(o)
    if not o.data.uv_layers:
        o.data.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    if method == "lightmap":
        bpy.ops.uv.lightmap_pack(PREF_MARGIN_DIV=margin * 10)
    else:
        bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")
    return f"unwrapped ({method})"


def op_bake_texture(o, size=1024, ao=False):
    """Texture prep for Roblox: bake whatever colour the mesh has now (its textures, vertex colours or
    material colours) into ONE image on a fresh non-overlapping UV, with one material using it."""
    activate(o)
    src_uv = o.data.uv_layers.active.name if o.data.uv_layers else None
    target = o.data.uv_layers.new(name="bake")
    img = bpy.data.images.new(f"{o.name}_tex", size, size)
    mats = [m for m in o.data.materials if m] or [bpy.data.materials.new(f"{o.name}_mat")]
    if not o.data.materials:
        o.data.materials.append(mats[0])
    has_vcol = bool(o.data.color_attributes)
    for m in mats:
        m.use_nodes = True
        nt = m.node_tree
        if has_vcol and not any(n.type == "TEX_IMAGE" for n in nt.nodes):  # vertex colours feed the colour
            bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf and not bsdf.inputs["Base Color"].is_linked:
                ca = nt.nodes.new("ShaderNodeVertexColor")
                nt.links.new(ca.outputs["Color"], bsdf.inputs["Base Color"])
        for n in nt.nodes:  # the source textures read the old UVs
            if n.type == "TEX_IMAGE" and src_uv and not n.inputs["Vector"].is_linked:
                uvn = nt.nodes.new("ShaderNodeUVMap")
                uvn.uv_map = src_uv
                nt.links.new(uvn.outputs["UV"], n.inputs["Vector"])
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = img
        nt.nodes.active = t
    o.data.uv_layers.active = target
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 1
    sc.render.bake.margin = 4
    sc.render.bake.use_pass_direct = sc.render.bake.use_pass_indirect = False
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"})
    if ao:  # multiply in ambient occlusion for depth
        ao_img = bpy.data.images.new(f"{o.name}_ao", size, size)
        for m in mats:
            m.node_tree.nodes.active.image = ao_img
        bpy.ops.object.bake(type="AO")
        px, pa = list(img.pixels), list(ao_img.pixels)
        img.pixels = [c * (0.35 + 0.65 * a) if i % 4 != 3 else c for i, (c, a) in enumerate(zip(px, pa))]
    # one clean material on the one UV
    for name in [l.name for l in o.data.uv_layers if l.name != "bake"]:
        o.data.uv_layers.remove(o.data.uv_layers[name])
    o.data.uv_layers["bake"].name = "UVMap"
    o.data.materials.clear()
    m = bpy.data.materials.new(f"{o.name}_baked")
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    t = m.node_tree.nodes.new("ShaderNodeTexImage")
    t.image = img
    m.node_tree.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.8
    o.data.materials.append(m)
    img.pack()
    return f"baked to one {size}px texture{' with AO' if ao else ''}"


OPS = {k[3:]: v for k, v in globals().items() if k.startswith("op_")}


def cmd_cleanup(name, ops):
    """Run ops in order: [{"op": "merge_by_distance"}, {"op": "decimate", "target_tris": 15000}, ...]."""
    o = obj(name)
    notes = []
    for step in ops:
        step = dict(step) if isinstance(step, dict) else {"op": step}
        op = step.pop("op")
        if op not in OPS:
            raise KeyError(f"no op '{op}': {', '.join(OPS)}")
        notes.append(f"{op}: {OPS[op](o, **step)}")
    return {"done": notes, "after": cmd_inspect(name)}


def cmd_run(code, name=None):
    """Run bpy code. In scope: bpy, bmesh, Vector, Matrix, math, obj (the named mesh, if any). Whatever it
    prints comes back, plus the value of `result` if it sets one."""
    ns = {"bpy": bpy, "bmesh": bmesh, "Vector": Vector, "Matrix": Matrix, "math": math,
          "obj": obj(name) if name else None, "result": None}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(code, "<run>", "exec"), ns)
    res = ns.get("result")
    try:
        json.dumps(res)
    except TypeError:
        res = repr(res)
    return {"output": buf.getvalue()[-4000:], "result": res}


def cmd_render(name, out, size=512, views=("front", "side", "back", "34")):
    """Clay-or-texture renders around the mesh, side by side in one PNG."""
    o = obj(name)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "TEXTURE" if textures(o) else "MATERIAL"
    sc.render.resolution_x = sc.render.resolution_y = size
    sc.render.film_transparent = False
    if not sc.world:
        sc.world = bpy.data.worlds.new("w")
    sc.world.color = (0.18, 0.19, 0.22)
    hidden = [x for x in bpy.data.objects if x.type == "MESH" and x != o and not x.hide_render]
    for x in hidden:
        x.hide_render = True
    cam = bpy.data.objects.get("_cam") or bpy.data.objects.new("_cam", bpy.data.cameras.new("_cam"))
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = "ORTHO"
    vs = [o.matrix_world @ v.co for v in o.data.vertices]
    lo = Vector([min(v[i] for v in vs) for i in range(3)])
    hi = Vector([max(v[i] for v in vs) for i in range(3)])
    c, r = (lo + hi) / 2, max(hi - lo)
    cam.data.ortho_scale = r * 1.15
    dirs = {"front": (0, -1, 0.15), "side": (1, 0, 0.15), "back": (0, 1, 0.15), "34": (0.75, -0.75, 0.5),
            "top": (0, -0.01, 1)}
    files = []
    for v in views:
        d = Vector(dirs[v]).normalized()
        cam.location = c + d * r * 3
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        f = f"{out}_{v}.png"
        sc.render.filepath = f
        bpy.ops.render.render(write_still=True)
        files.append(f)
    for x in hidden:
        x.hide_render = False
    return {"files": files}


def cmd_export(name, out_dir, formats=("glb", "fbx")):
    """Write the mesh for Roblox: GLB in metres (the harness's asset pipeline reads these) and FBX in studs
    (Roblox's importer), textures embedded."""
    o = obj(name)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    activate(o)
    studs = o.get("units") == "studs"
    files = {}
    if "glb" in formats:
        k = STUD if studs else 1.0
        o.data.transform(Matrix.Scale(k, 4))
        try:
            p = out_dir / f"{name}.glb"
            bpy.ops.export_scene.gltf(filepath=str(p), export_format="GLB", use_selection=True)
            files["glb"] = str(p)
        finally:
            o.data.transform(Matrix.Scale(1 / k, 4))
    if "fbx" in formats:
        p = out_dir / f"{name}.fbx"
        bpy.ops.export_scene.fbx(filepath=str(p), use_selection=True, object_types={"MESH", "ARMATURE"},
                                 axis_forward="-Z", axis_up="Y", global_scale=0.01 if studs else 1.0,
                                 path_mode="COPY", embed_textures=True, mesh_smooth_type="FACE")
        files["fbx"] = str(p)
    return {"files": files, "units": "studs" if studs else "source (run scale_to first for Roblox)"}


def cmd_close(name):
    o = obj(name)
    me = o.data
    bpy.data.objects.remove(o)
    if me.users == 0:
        bpy.data.meshes.remove(me)
    return {"closed": name}


COMMANDS = {k[4:]: v for k, v in globals().items() if k.startswith("cmd_")}


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    print(REPLY + json.dumps({"ready": True, "blender": bpy.app.version_string}), flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            fn = COMMANDS[msg.pop("cmd")]
            reply = {"ok": True, "result": fn(**msg)}
        except Exception as e:  # noqa: BLE001 - reported back to the caller, the session lives on
            tb = [f for f in traceback.extract_tb(e.__traceback__) if f.filename in ("<run>",)]
            where = f" (line {tb[-1].lineno})" if tb else ""
            reply = {"ok": False, "error": f"{type(e).__name__}{where}: {e}"}
        print(REPLY + json.dumps(reply), flush=True)


main()
