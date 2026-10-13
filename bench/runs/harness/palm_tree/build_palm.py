import bpy, bmesh, math, sys
from mathutils import Vector, Matrix

out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)

def mat(name, rgb):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = 0.85
    return m

M_TRUNK = mat("Trunk", (0.42, 0.27, 0.15))
M_RING = mat("TrunkRing", (0.30, 0.19, 0.10))
M_LEAF = mat("Frond", (0.22, 0.55, 0.16))
M_LEAF2 = mat("FrondDark", (0.13, 0.38, 0.11))
M_NUT = mat("Coconut", (0.30, 0.18, 0.08))

me = bpy.data.meshes.new("bench_palm")
obj = bpy.data.objects.new("bench_palm", me)
bpy.context.collection.objects.link(obj)
for m in (M_TRUNK, M_RING, M_LEAF, M_LEAF2, M_NUT):
    me.materials.append(m)
bm = bmesh.new()

# ---- trunk: segmented, tapered, curved; each segment flares at its base ----
SIDES = 7
SEG = 7
H = 3.6
def spine(t):  # gentle curve in +X
    return Vector((0.55 * t * t, 0.0, H * t))
rings = []
for i in range(SEG):
    t0, t1 = i / SEG, (i + 1) / SEG
    for t, flare in ((t0, 1.18), (t1, 1.0)):
        c = spine(t)
        r = (0.24 - 0.10 * t) * flare
        ring = [bm.verts.new(c + Vector((r * math.cos(a), r * math.sin(a), 0)))
                for a in (2 * math.pi * k / SIDES + i * 0.25 for k in range(SIDES))]
        rings.append((ring, i))
for j in range(len(rings) - 1):
    a, ia = rings[j]
    b, ib = rings[j + 1]
    within = (j % 2 == 0)
    for k in range(SIDES):
        f = bm.faces.new((a[k], a[(k + 1) % SIDES], b[(k + 1) % SIDES], b[k]))
        f.material_index = 0 if within else 1
bm.faces.new(list(reversed(rings[0][0]))).material_index = 0
top = spine(1.0)
cap = bm.verts.new(top + Vector((0, 0, 0.08)))
last = rings[-1][0]
for k in range(SIDES):
    bm.faces.new((last[k], last[(k + 1) % SIDES], cap)).material_index = 0

# ---- fronds: arched, V-folded strips tapering to a point ----
def frond(yaw, pitch, length, width, droop, matidx):
    N = 6
    rot = Matrix.Rotation(yaw, 3, "Z")
    pts = []
    for s in range(N + 1):
        u = s / N
        # arc: rises then droops
        x = length * u
        z = math.sin(pitch) * length * u - droop * u * u * length
        w = width * math.sin(math.pi * min(1.0, u * 1.15 + 0.12)) * (1 - 0.15 * u)
        if s == N:
            w = 0.0
        fold = 0.35 * w
        base = Vector((x, 0, z))
        pts.append((base + Vector((0, 0, fold * 0.6)),
                    base + Vector((0, w, -fold)),
                    base + Vector((0, -w, -fold))))
    vs = []
    for mid, l, r in pts:
        vs.append([bm.verts.new(top + rot @ p) for p in (l, mid, r)])
    for s in range(N):
        a, b = vs[s], vs[s + 1]
        if s == N - 1:
            bm.faces.new((a[0], a[1], b[1])).material_index = matidx
            bm.faces.new((a[1], a[2], b[1])).material_index = matidx
        else:
            bm.faces.new((a[0], a[1], b[1], b[0])).material_index = matidx
            bm.faces.new((a[1], a[2], b[2], b[1])).material_index = matidx

for i in range(8):
    yaw = 2 * math.pi * i / 8 + 0.2
    frond(yaw, 0.55, 2.1, 0.36, 0.95, 2)
for i in range(5):
    yaw = 2 * math.pi * i / 5 + 0.6
    frond(yaw, 1.05, 1.5, 0.30, 0.9, 3)

# ---- coconuts ----
for i in range(4):
    a = 2 * math.pi * i / 4 + 0.4
    c = top + Vector((0.2 * math.cos(a), 0.2 * math.sin(a), -0.18))
    res = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.13,
                                     matrix=Matrix.Translation(c))
    for f in {f for v in res["verts"] for f in v.link_faces}:
        f.material_index = 4

bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(me)
bm.free()
# double-sided look for fronds in Roblox: solidify thin shell
mod = obj.modifiers.new("solid", "SOLIDIFY")
mod.thickness = 0.02
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.modifier_apply(modifier="solid")
bpy.ops.object.shade_flat()
# palette texture: one colour band per material, faces UV'd into their band
cols=[(0.42,0.27,0.15),(0.30,0.19,0.10),(0.22,0.55,0.16),(0.13,0.38,0.11),(0.30,0.18,0.08)]
W=64; img=bpy.data.images.new("bench_palm_palette",W,W)
px=[]
for y in range(W):
    for x in range(W):
        c=cols[min(4,x*5//W)]
        shade=0.8+0.35*(y/W)
        px+= [min(1,c[0]*shade),min(1,c[1]*shade),min(1,c[2]*shade),1]
img.pixels=px
img.filepath_raw=out.replace(".glb","_palette.png"); img.file_format="PNG"; img.save()
uvl=me.uv_layers.new(name="UVMap")
zmin=min(v.co.z for v in me.vertices); zmax=max(v.co.z for v in me.vertices)
for poly in me.polygons:
    u=(poly.material_index+0.5)/5
    for li in poly.loop_indices:
        z=me.vertices[me.loops[li].vertex_index].co.z
        uvl.data[li].uv=(u,0.05+0.9*(z-zmin)/(zmax-zmin))
pal=bpy.data.materials.new("Palm"); pal.use_nodes=True
b=next(n for n in pal.node_tree.nodes if n.type=="BSDF_PRINCIPLED")
b.inputs["Roughness"].default_value=0.85
t=pal.node_tree.nodes.new("ShaderNodeTexImage"); t.image=img; t.interpolation="Closest"
pal.node_tree.links.new(t.outputs["Color"],b.inputs["Base Color"])
me.materials.clear(); me.materials.append(pal)
tris = sum(len(p.vertices) - 2 for p in me.polygons)
print("TRIS", tris, "DIMS", tuple(round(d, 2) for d in obj.dimensions))
bpy.ops.export_scene.gltf(filepath=out, use_selection=True)
