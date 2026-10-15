"""Blender script: Kurama from the Hunyuan meshes Jordan picked, as one skinned mesh for Roblox.

  blender -b -P tools/kurama/assemble.py -- <out_dir>

1. The body (generated from the body sheet's side view) is turned into kit axes (faces -Y, Z up,
   studs) and scaled to boss size; its nine tails, which Hunyuan laid in one flat sheet, are split
   apart and fanned out around the rump (lowest tails sweep out to the sides, the top one stays up).
2. Its head is cut off and the head generated from the face sheet's 3/4 view takes its place, ears
   lengthened by 40%.
3. Colour: the face sheet's front view is projected onto the front of the head (eyes, black bands,
   nose, teeth, ear insides); the rest is the sheet's orange. Baked into one 1024 texture.
4. A skeleton (Torso, Skull, Jaw, four legs, nine tails in three segments) with smooth weights, so
   Roblox deforms the mesh instead of moving rigid pieces.
Writes <out_dir>/kurama.fbx (studs, armature), kurama.png, rig.json (bones in kit studs), previews.
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
REFS = ROOT / "assets" / "_refs_kurama"
BODY = ROOT / "assets" / "kurama_hy_body_side" / "source" / "main-3fb7112b.glb"
HEAD = ROOT / "assets" / "kurama_hy_sheet_q34" / "source" / "main-2b2de574.glb"
OUT = Path(sys.argv[sys.argv.index("--") + 1])
OUT.mkdir(parents=True, exist_ok=True)

LENGTH = 200.0  # studs nose to tail tip
EAR_STRETCH = 1.4
FUR = (0.74, 0.36, 0.19)  # the sheet's orange (sRGB)
TRIS = {"body": 12000, "head": 7500}


def lin(c):
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def load(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    objs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.data.transform(o.matrix_world)
    o.matrix_world = Matrix()
    o.parent = None
    o.data.materials.clear()
    return o


def decimate(o, tris):
    n = sum(len(p.vertices) - 2 for p in o.data.polygons)
    if n > tris:
        m = o.modifiers.new("dec", "DECIMATE")
        m.ratio = tris / n
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)


def smoothstep(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---------------------------------------------------------------- 1. body into kit axes, boss size
body = load(BODY)
decimate(body, 90000)
body.data.transform(Matrix.Rotation(math.radians(-90), 4, "Z"))  # it faced +X; the kit faces -Y
vs = [v.co for v in body.data.vertices]
lo = Vector([min(v[i] for v in vs) for i in range(3)])
hi = Vector([max(v[i] for v in vs) for i in range(3)])
s = LENGTH / (hi.y - lo.y)
body.data.transform(Matrix.Scale(s, 4) @ Matrix.Translation(Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z))))
vs = [v.co.copy() for v in body.data.vertices]
lo = Vector([min(v[i] for v in vs) for i in range(3)])
hi = Vector([max(v[i] for v in vs) for i in range(3)])
L = hi.y - lo.y
print("BODY", [round(x, 1) for x in lo], [round(x, 1) for x in hi])

# tail root: the top of the rump where the tails leave the body (the body sheet's tails meet at ~62%
# of the length back from the nose, a little above the back line)
y_root = lo.y + 0.615 * L
band = [v for v in vs if abs(v.y - y_root) < 0.02 * L and abs(v.x) < 0.05 * L]
R = Vector((0, y_root, sum(v.z for v in band) / len(band)))
print("TAIL ROOT", [round(x, 1) for x in R])

# ---------------------------------------------------------------- tails: Hunyuan fused them into one
# sheet, so they're replaced: nine leaf-shaped tails like the body sheet's (thin at the root, fat in the
# middle, a pointed tip curling outward), fanned around the back as in its front and top views
R_CUT = 0.06 * L
bm = bmesh.new()
bm.from_mesh(body.data)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y > R.y - 3 and (v.co - R).length > 0.035 * L and v.co.z > 30],
                 context="VERTS")
bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
bm.to_mesh(body.data)
bm.free()


# The replacement tails come from the Hunyuan body made from the sheet's FRONT view: its body was
# squat, but its nine leaf tails are good and already fanned (in the x-z plane behind it). They are cut
# out, leaned back, scaled and set on this body's rump, then split into nine by their fan angle.
FAN_SRC = ROOT / "assets" / "kurama_hy_body_front" / "source" / "main-c58224c9.glb"
FAN_C = Vector((0, 0.28, 0.0))  # where its tails meet, in its own units
FAN_TILT = 30  # degrees the fan leans back
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(FAN_SRC))
src = max([o for o in bpy.data.objects if o not in before and o.type == "MESH"], key=lambda o: len(o.data.vertices))
for o in [o for o in bpy.data.objects if o not in before and o != src]:
    bpy.data.objects.remove(o)
src.data.transform(src.matrix_world)
src.matrix_world = Matrix()
src.parent = None
src.data.materials.clear()
decimate(src, 70000)
bm = bmesh.new()
bm.from_mesh(src.data)
def fan_d(co):
    return Vector((co.x, 0, co.z - FAN_C.z)).length


# only the tails: behind the body and away from where they meet (its own chunky rump stays behind)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not (v.co.y > 0.05 and fan_d(v.co) > 0.3)], context="VERTS")
# fan angle of each vertex about the meeting point, split into nine tails at the widest angle gaps
ang = {v.index: math.degrees(math.atan2(v.co.x, v.co.z - FAN_C.z)) for v in bm.verts}
# nine tails: 1D k-means on the fan angle of the outer half of each tail
outer = [ang[v.index] for v in bm.verts if fan_d(v.co) > 0.5]
lo_a, hi_a = min(outer), max(outer)
centres = [lo_a + (hi_a - lo_a) * (i + 0.5) / 9 for i in range(9)]
for _ in range(30):
    groups_ = [[] for _ in centres]
    for a_ in outer:
        groups_[min(range(9), key=lambda i: abs(a_ - centres[i]))].append(a_)
    centres = [sum(g) / len(g) if g else c for g, c in zip(groups_, centres)]
centres.sort()
cuts = [(a_ + b_) / 2 for a_, b_ in zip(centres, centres[1:])]
print("FAN CENTRES", [round(c, 1) for c in centres])
fan_r = max((Vector((v.co.x, 0, v.co.z - FAN_C.z))).length for v in bm.verts)
k_fan = 0.46 * L / fan_r
xf = (Matrix.Translation(R + Vector((0, 11, 9))) @ Matrix.Rotation(math.radians(-FAN_TILT), 4, "X")
      @ Matrix.Scale(k_fan, 4) @ Matrix.Translation(-FAN_C))
tail_idx = {}
pts_by_tail = [[] for _ in range(len(cuts) + 1)]
for v in bm.verts:
    k_ = sum(1 for c in cuts if ang[v.index] > c)
    d = fan_d(v.co)
    # swing each tail round to its place in an upper fan (out-left, over the top, out-right): the source
    # fanned them all the way round, so the lowest hung down past the hind legs
    c_ = centres[k_]
    target = c_ if abs(c_) <= 95 else math.copysign(95 + (abs(c_) - 95) * 0.25, c_)  # only the low ones swing up
    turn = (target - c_) * smoothstep((d - 0.3) / 0.3)  # roots stay where they meet; the tail bends out
    v.co = FAN_C + Matrix.Rotation(math.radians(turn), 3, "Y") @ (v.co - FAN_C)
    v.co = xf @ v.co
    pts_by_tail[k_].append((d, v.co.copy()))
bm.to_mesh(src.data)
bm.free()
tail_lines = []
for pts in pts_by_tail:
    if not pts:
        continue
    dmax = max(d for d, _ in pts)
    line = [R + Vector((0, 11, 9))]
    for b_ in range(1, 13):
        sel = [p for d, p in pts if dmax * (b_ - 1) / 12 <= d < dmax * b_ / 12]
        if sel:
            line.append(sum(sel, Vector()) / len(sel))
    while len(line) < 4:
        line.append(line[-1] + Vector((0, 1, 1)))
    tail_lines.append(line)
print("TAILS", len(tail_lines), [len(p) for p in pts_by_tail])
# close the cut ends and grow all nine out of one smooth bulb on the rump
bm = bmesh.new()
bm.from_mesh(src.data)
bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0, matrix=Matrix.Translation(R + Vector((0, 13, 10)))
                           @ Matrix.Diagonal((11, 13, 10, 1)))
bm.to_mesh(src.data)
bm.free()
rm = src.modifiers.new("remesh", "REMESH")
rm.mode, rm.voxel_size = "VOXEL", 0.9
sm = src.modifiers.new("smooth", "SMOOTH")
sm.factor, sm.iterations = 0.5, 4
bpy.context.view_layer.objects.active = src
for m in list(src.modifiers):
    bpy.ops.object.modifier_apply(modifier=m.name)
bpy.ops.object.select_all(action="DESELECT")
for o in (body, src):
    o.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.join()

# ---------------------------------------------------------------- 2. the new head
y_nose = lo.y
z_top = max(v.z for v in vs if v.y < R.y)
head_zone = [v for v in vs if v.y < y_nose + 0.17 * L and v.z > 0.45 * z_top]  # not the front paws below it
h_lo = Vector([min(v[i] for v in head_zone) for i in range(3)])
h_hi = Vector([max(v[i] for v in head_zone) for i in range(3)])
y_cut = y_nose + 0.13 * L  # drop the old head forward of here (the new head covers the joint)
bm = bmesh.new()
bm.from_mesh(body.data)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y < y_cut and v.co.z > 0.45 * z_top], context="VERTS")
bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
bm.to_mesh(body.data)
bm.free()

head = load(HEAD)
decimate(head, 60000)
hv = [v.co for v in head.data.vertices]
hl = Vector([min(v[i] for v in hv) for i in range(3)])
hh = Vector([max(v[i] for v in hv) for i in range(3)])
# fit: nose to back of skull along y matched to the old head's length (ears and whiskers stick out)
k = (h_hi.y - h_lo.y) * 1.15 / (hh.y - hl.y)
head.data.transform(Matrix.Translation(Vector((0, h_lo.y, h_lo.z))) @ Matrix.Scale(k, 4)
                    @ Matrix.Translation(Vector((-(hl.x + hh.x) / 2, -hl.y, -hl.z))))
hv = [v.co.copy() for v in head.data.vertices]
hl = Vector([min(v[i] for v in hv) for i in range(3)])
hh = Vector([max(v[i] for v in hv) for i in range(3)])
H = hh - hl
print("HEAD", [round(x, 1) for x in hl], [round(x, 1) for x in hh])

# 3a. colour, step one: project the face sheet's front view onto the head (UV "proj", before the ears
# are stretched so the mapping follows them). Alignment: ear tips left/right and top, chin bottom.
ear_pts = [v for v in hv if v.z > hl.z + 0.75 * H.z]
ex0, ex1 = min(v.x for v in ear_pts), max(v.x for v in ear_pts)
SHEET = {"x0": 6, "x1": 304, "top": 8, "chin": 203, "box": (355, 10, 665, 215)}  # sheet px of the same points
sw, sh_ = SHEET["box"][2] - SHEET["box"][0], SHEET["box"][3] - SHEET["box"][1]
uvp = head.data.uv_layers.new(name="proj")
for loop in head.data.loops:
    co = head.data.vertices[loop.vertex_index].co
    px = SHEET["x0"] + (co.x - ex0) / (ex1 - ex0) * (SHEET["x1"] - SHEET["x0"])
    py = SHEET["chin"] - (co.z - hl.z) / H.z * (SHEET["chin"] - SHEET["top"])
    uvp.data[loop.index].uv = (px / sw, 1 - py / sh_)

# 2b. longer ears: everything above the skull stretches away from the ear roots
z0 = hl.z + 0.62 * H.z
for v in head.data.vertices:
    if v.co.z > z0 - 0.06 * H.z:
        f = smoothstep((v.co.z - (z0 - 0.06 * H.z)) / (0.12 * H.z))
        root = Vector((math.copysign(0.22 * H.x, v.co.x), v.co.y * 0.5 + hl.y * 0.5, z0))
        v.co = v.co.lerp(root + (v.co - root) * EAR_STRETCH, f)
decimate(head, TRIS["head"] * 2)
decimate(body, TRIS["body"] * 2)

# ---------------------------------------------------------------- 3b. bake colour to one texture
sheet_img = bpy.data.images.load(str(REFS / "sheet.jpg"))
crop = bpy.data.images.new("face", sw, sh_)
W, Hh = sheet_img.size
px_all = list(sheet_img.pixels)
x0, y0, x1, y1 = SHEET["box"]
buf = []
for yy in range(sh_ - 1, -1, -1):  # Blender pixels run bottom-up
    sy_ = y0 + yy
    row = (Hh - 1 - sy_) * W
    for xx in range(sw):
        i = (row + x0 + xx) * 4
        buf += px_all[i:i + 4]
crop.pixels = buf

for o in (head, body):
    o.data.uv_layers.new(name="atlas")
tex = bpy.data.images.new("kurama", 1024, 1024)


def bake_material(name, with_face):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    fur = nt.nodes.new("ShaderNodeRGB")
    fur.outputs[0].default_value = (*lin(FUR), 1)
    if with_face:
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "proj"
        img = nt.nodes.new("ShaderNodeTexImage")
        img.image = crop
        img.extension = "EXTEND"
        nt.links.new(uv.outputs[0], img.inputs[0])
        geo = nt.nodes.new("ShaderNodeNewGeometry")  # only faces turned toward the front take the sheet
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Normal"], sep.inputs[0])
        ramp = nt.nodes.new("ShaderNodeMapRange")
        ramp.inputs["From Min"].default_value = -0.15
        ramp.inputs["From Max"].default_value = -0.45
        nt.links.new(sep.outputs["Y"], ramp.inputs["Value"])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        nt.links.new(ramp.outputs[0], mix.inputs["Factor"])
        nt.links.new(fur.outputs[0], mix.inputs["A"])
        nt.links.new(img.outputs["Color"], mix.inputs["B"])
        nt.links.new(mix.outputs["Result"], em.inputs["Color"])
    else:
        nt.links.new(fur.outputs[0], em.inputs["Color"])
    target = nt.nodes.new("ShaderNodeTexImage")
    target.image = tex
    nt.nodes.active = target
    return m


head.data.materials.append(bake_material("head", True))
body.data.materials.append(bake_material("body", False))

# one atlas for both: join first (the bake target is shared), unwrap, bake
bpy.ops.object.select_all(action="DESELECT")
head.select_set(True)
body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.join()
fox = bpy.context.view_layer.objects.active
fox.name = "Kurama"
fox.data.uv_layers.active = fox.data.uv_layers["atlas"]
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.004)
bpy.ops.object.mode_set(mode="OBJECT")
decimate(fox, TRIS["head"] + TRIS["body"])
for p in fox.data.polygons:
    p.use_smooth = True
scene.render.engine = "CYCLES"
scene.cycles.samples = 1
scene.render.bake.margin = 4
bpy.ops.object.bake(type="EMIT")
tex.filepath_raw = str(OUT / "kurama.png")
tex.file_format = "PNG"
tex.save()

# final material: the baked texture
for m in list(fox.data.materials):
    fox.data.materials.pop()
final = bpy.data.materials.new("KuramaFur")
final.use_nodes = True
bsdf = next(n for n in final.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
ti = final.node_tree.nodes.new("ShaderNodeTexImage")
ti.image = tex
final.node_tree.links.new(ti.outputs["Color"], bsdf.inputs["Base Color"])
bsdf.inputs["Roughness"].default_value = 0.85
fox.data.materials.append(final)
while len(fox.data.uv_layers) > 1:
    fox.data.uv_layers.remove(next(u for u in fox.data.uv_layers if u.name != "atlas"))

# ---------------------------------------------------------------- 4. skeleton and weights
V = [v.co.copy() for v in fox.data.vertices]
y_neck = y_cut + 0.04 * L
neck = [v for v in V if abs(v.y - y_neck) < 0.015 * L]
N = Vector((0, y_neck, sum(v.z for v in neck) / max(1, len(neck))))
hx = [v for v in V if v.y < y_cut]
Hc = Vector((0, sum(v.y for v in hx) / len(hx), sum(v.z for v in hx) / len(hx)))
z_mouth = hl.z + 0.28 * H.z  # the grin line sits about a quarter of the way up the head
J = Vector((0, hl.y + 0.62 * H.y, z_mouth))
chin = Vector((0, hl.y + 0.05 * H.y, hl.z + 0.12 * H.z))
bones = {"Torso": (R, N, None), "Skull": (N, Hc, "Torso"), "Jaw": (J, chin, "Skull")}

# legs: the four clusters of verts below the belly, front/back by y, left/right by x
z_belly = 0.36 * max(v.z for v in V if R.y > v.y > y_cut)
legs = {}
for name, fb, sx in (("LegFL", -1, 1), ("LegFR", -1, -1), ("LegHL", 1, 1), ("LegHR", 1, -1)):
    mid_y = (y_cut + R.y) / 2
    pts = [v for v in V if v.z < z_belly and (v.y - mid_y) * fb > 0 and v.x * sx > 0 and y_cut < v.y < R.y + 0.08 * L]
    top = max(pts, key=lambda v: v.z).z
    hip = Vector((sum(v.x for v in pts) / len(pts), sum(v.y for v in pts if v.z > top - 3) / max(1, len([v for v in pts if v.z > top - 3])), top + 6))
    foot = min(pts, key=lambda v: v.z)
    legs[name] = pts
    bones[name] = (hip, Vector((hip.x, foot.y, foot.z + 2)), "Torso")

# tails: three segments along each tail's centre line
for k, line in enumerate(tail_lines):
    n_ = len(line) - 1
    seg = [line[0], line[n_ // 3], line[2 * n_ // 3], line[-1]]
    for j in range(3):
        bones[f"Tail{k + 1}_{j + 1}"] = (seg[j], seg[j + 1], "Torso" if j == 0 else f"Tail{k + 1}_{j}")

# weights: each vertex to its region's bones, blended across joints
arm_data = bpy.data.armatures.new("Rig")
arm = bpy.data.objects.new("Rig", arm_data)
scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
for name, (a, b, parent) in bones.items():
    eb = arm_data.edit_bones.new(name)
    eb.head, eb.tail = a, (b if (b - a).length > 0.5 else a + Vector((0, 0, 1)))
for name, (_, _, parent) in bones.items():
    if parent:
        arm_data.edit_bones[name].parent = arm_data.edit_bones[parent]
bpy.ops.object.mode_set(mode="OBJECT")

groups = {n: fox.vertex_groups.new(name=n) for n in bones}


def seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
    return (p - (a + ab * t)).length


tail_bones = [[f"Tail{k + 1}_{j + 1}" for j in range(3)] for k in range(len(tail_lines))]
for i, p in enumerate(V):
    w = {}
    if p.y < y_cut + 0.03 * L:  # head: skull, the jaw below the grin line toward the front
        t = smoothstep((y_cut + 0.03 * L - p.y) / (0.05 * L))
        jaw = smoothstep((z_mouth - p.z) / 1.5) * smoothstep((J.y - p.y) / 3.0)
        w["Torso"] = 1 - t
        w["Skull"] = t * (1 - jaw)
        w["Jaw"] = t * jaw
    elif p.y > R.y - 0.02 * L and p.z > R.z - 0.08 * L:  # tails (and the root zone)
        best = min(range(len(tail_lines)), key=lambda k: min(seg_dist(p, a, b) for a, b in zip(tail_lines[k], tail_lines[k][1:])))
        line = tail_lines[best]
        jn = min(range(len(line)), key=lambda q: (line[q] - p).length)  # nearest sample along the tail
        d = (p - R).length
        u = jn / (len(line) - 1) * 3  # 0..3 along the three segments
        root = smoothstep((d - 0.03 * L) / (0.06 * L))
        w["Torso"] = 1 - root
        j = min(2, int(u))
        f = u - j
        w[tail_bones[best][j]] = root * (1 - smoothstep(f - 0.5) if j < 2 else 1)
        if j < 2:
            w[tail_bones[best][j + 1]] = root * smoothstep(f - 0.5)
    else:
        leg = None
        for name, pts in legs.items():
            hip = bones[name][0]
            if p.z < hip.z and abs(p.x - hip.x) < 0.07 * L and abs(p.y - hip.y) < 0.09 * L:
                leg = name
        if leg:
            f = smoothstep((bones[leg][0].z - p.z) / 10)
            w[leg] = f
            w["Torso"] = 1 - f
        else:
            w["Torso"] = 1
    tot = sum(w.values()) or 1
    for n, x in w.items():
        if x > 1e-3:
            groups[n].add([i], x / tot, "REPLACE")

fox.parent = arm
mod = fox.modifiers.new("Rig", "ARMATURE")
mod.object = arm

rig = {"bones": {n: {"head": list(a), "tail": list(b), "parent": p} for n, (a, b, p) in bones.items()},
       "root": list(R), "neck": list(N), "length": L, "mouth": list(Vector((0, hl.y - 2, z_mouth + 1))),
       "tails": len(tail_lines)}
(OUT / "rig.json").write_text(json.dumps(rig, indent=1))

# ---------------------------------------------------------------- export (FBX in studs) and previews
bpy.ops.object.select_all(action="DESELECT")
fox.select_set(True)
arm.select_set(True)
bpy.ops.export_scene.fbx(filepath=str(OUT / "kurama.fbx"), use_selection=True, object_types={"MESH", "ARMATURE"},
                         axis_forward="-Z", axis_up="Y", global_scale=0.01, path_mode="COPY", embed_textures=True,
                         mesh_smooth_type="FACE", add_leaf_bones=False, use_armature_deform_only=True)
bpy.ops.export_scene.gltf(filepath=str(OUT / "kurama.glb"), export_format="GLB", use_selection=True)

scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 1000, 700
scene.world = bpy.data.worlds.new("w")
scene.world.color = (0.32, 0.33, 0.36)
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3
sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
scene.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.lens = 45
scene.collection.objects.link(cam)
scene.camera = cam
centre = Vector((0, 0, 60))
head_c = Vector((0, hl.y + 0.4 * H.y, hl.z + 0.45 * H.z))
for name, (pos, look) in {"34": (Vector((-210, -260, 150)), centre), "side": (Vector((-330, 0, 70)), centre),
                          "front": (Vector((0, -340, 90)), centre), "face": (head_c + Vector((-25, -55, 8)), head_c)}.items():
    cam.location = pos
    cam.rotation_euler = (look - pos).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(OUT / f"view_{name}.png")
    bpy.ops.render.render(write_still=True)
print("DONE", len(fox.data.polygons), "faces")
