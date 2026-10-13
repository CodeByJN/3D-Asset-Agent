import bpy, bmesh, math
from mathutils import Vector, Matrix
OUT = r"C:\Users\Jordan\Desktop\code\3D-Asset-Agent\bench\runs\native\palm_tree"
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

def mat(name, col):
    m = bpy.data.materials.new(name); m.diffuse_color = (*col, 1)
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*col, 1)
    m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
    return m
M_TRUNK = mat("Trunk", (0.42, 0.26, 0.13))
M_RING = mat("TrunkRing", (0.30, 0.18, 0.09))
M_LEAF = mat("Leaf", (0.16, 0.55, 0.15))
M_LEAF2 = mat("LeafDark", (0.09, 0.38, 0.10))
M_NUT = mat("Coconut", (0.25, 0.15, 0.07))
mats = [M_TRUNK, M_RING, M_LEAF, M_LEAF2, M_NUT]

me = bpy.data.meshes.new("PalmTree"); obj = bpy.data.objects.new("PalmTree", me)
sc.collection.objects.link(obj)
for m in mats: me.materials.append(m)
bm = bmesh.new()

# ---- trunk: curved, tapered, 6 sides, 9 segments with stepped rings
H = 13.0; SEG = 9; SIDES = 6
def spine(t):  # gentle lean in +X
    return Vector((2.2 * t**1.8, 0, H * t))
rings = []
for i in range(SEG + 1):
    t = i / SEG
    c = spine(t)
    r = 0.75 * (1 - t) + 0.38 * t
    ring = []
    for k in range(SIDES):
        a = 2 * math.pi * k / SIDES + (0.25 if i % 2 else 0)
        ring.append(bm.verts.new(c + Vector((math.cos(a) * r, math.sin(a) * r, 0))))
    rings.append(ring)
    # stepped look: a slightly wider ring just below each node
for i in range(SEG):
    for k in range(SIDES):
        k2 = (k + 1) % SIDES
        f = bm.faces.new((rings[i][k], rings[i][k2], rings[i+1][k2], rings[i+1][k]))
        f.material_index = 1 if i % 2 else 0
bm.faces.new(list(reversed(rings[0]))).material_index = 0
top = spine(1.0)
tip = bm.verts.new(top + Vector((0, 0, 0.35)))
for k in range(SIDES):
    bm.faces.new((rings[-1][k], rings[-1][(k+1) % SIDES], tip)).material_index = 1

# ---- fronds: bent, V-folded strips with jagged-ish width
def frond(yaw, pitch_up, length, droop, matidx, nseg=7):
    d = Vector((math.cos(yaw), math.sin(yaw), 0))
    side = Vector((-d.y, d.x, 0))
    pts = []
    for s in range(nseg + 1):
        u = s / nseg
        horiz = length * u
        z = math.sin(pitch_up) * length * u - droop * u * u * length
        centre = top + d * horiz + Vector((0, 0, z + 0.15))
        w = 1.25 * math.sin(math.pi * min(1, u * 1.15)) ** 0.8 if u < 1 else 0
        w = max(w, 0.0)
        fold = 0.25 * w
        mid = bm.verts.new(centre + Vector((0, 0, fold)))
        if s == nseg:
            pts.append((mid, mid, mid)); continue
        l = bm.verts.new(centre + side * w)
        r = bm.verts.new(centre - side * w)
        pts.append((l, mid, r))
    for s in range(nseg):
        l0, m0, r0 = pts[s]; l1, m1, r1 = pts[s+1]
        if s == nseg - 1:
            bm.faces.new((l0, m0, m1)).material_index = matidx
            bm.faces.new((m0, r0, m1)).material_index = matidx
        else:
            if s == 0:
                pass
            bm.faces.new((l0, m0, m1, l1)).material_index = matidx
            bm.faces.new((m0, r0, r1, m1)).material_index = matidx

N = 8
for i in range(N):
    yaw = 2 * math.pi * i / N + 0.2
    upper = i % 2 == 0
    frond(yaw, math.radians(40 if upper else 22), 5.6 if upper else 5.0,
          1.5 if upper else 1.75, 2 if upper else 3)
# two short young fronds pointing up
for i, yaw in enumerate((0.9, 3.9)):
    frond(yaw, math.radians(65), 2.6, 0.55, 2, nseg=4)

bm.normal_update()
bmesh.ops.recalc_face_normals(bm, faces=[f for f in bm.faces if f.material_index in (0, 1)])

# ---- coconuts
for i in range(3):
    a = 2 * math.pi * i / 3 + 0.5
    c = top + Vector((math.cos(a) * 0.45, math.sin(a) * 0.55, -0.55))
    ret = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.42,
                                     matrix=Matrix.Translation(c))
    for v in ret["verts"]:
        for f in v.link_faces: f.material_index = 4

bm.to_mesh(me); bm.free()
# leaves double-sided-ish for Roblox: duplicate leaf faces flipped
bpy.context.view_layer.objects.active = obj; obj.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='DESELECT')
bpy.ops.object.mode_set(mode='OBJECT')
for p in me.polygons: p.select = p.material_index in (2, 3)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.duplicate(); bpy.ops.mesh.flip_normals()
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.remove_doubles(threshold=0.0001) if False else None
bpy.ops.mesh.quads_convert_to_tris()
bpy.ops.uv.smart_project()
bpy.ops.object.mode_set(mode='OBJECT')
for p in me.polygons: p.use_smooth = False
# origin at base
bpy.context.scene.cursor.location = (0, 0, 0)
bpy.ops.object.origin_set(type='ORIGIN_CURSOR')

tris = len(me.polygons)
dims = obj.dimensions
print("TRIS", tris, "DIMS", tuple(round(x, 2) for x in dims))

bpy.ops.export_scene.fbx(filepath=OUT + r"\palm_tree.fbx", use_selection=True,
    apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y',
    mesh_smooth_type='FACE', use_mesh_modifiers=True, add_leaf_bones=False, bake_space_transform=True)

# preview render
cam_d = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cam_d); sc.collection.objects.link(cam)
cam.location = (17, -19, 6); 
cam.rotation_euler = (Vector((0.8, 0, 7.5)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
sc.camera = cam
sun = bpy.data.objects.new("S", bpy.data.lights.new("S", 'SUN')); sun.data.energy = 3
sun.rotation_euler = (0.7, 0.3, 0.8); sc.collection.objects.link(sun)
w = bpy.data.worlds.new("W"); w.color = (0.5, 0.65, 0.85); sc.world = w
sc.render.engine = 'BLENDER_EEVEE' if 'BLENDER_EEVEE' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE_NEXT'
sc.render.resolution_x = 640; sc.render.resolution_y = 800
sc.render.filepath = OUT + r"\preview.png"
bpy.ops.render.render(write_still=True)
