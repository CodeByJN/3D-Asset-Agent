"""Blender: turntable frames of a mesh file. Args after --: file out_dir frames height(0 = own)."""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

src, out, n, height = sys.argv[sys.argv.index("--") + 1:]
n, height = int(n), float(height)
bpy.ops.wm.read_factory_settings(use_empty=True)
ext = Path(src).suffix.lower()
if ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=src)
elif ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=src)
elif ext == ".obj":
    bpy.ops.wm.obj_import(filepath=src)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
pivot = bpy.data.objects.new("pivot", None)
bpy.context.scene.collection.objects.link(pivot)
for o in bpy.context.scene.objects:
    if o.parent is None and o is not pivot:
        o.parent = pivot
pivot.location = (-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)
bpy.context.view_layer.update()
pivot2 = bpy.data.objects.new("spin", None)
bpy.context.scene.collection.objects.link(pivot2)
pivot.parent = pivot2
h = height or (hi.z - lo.z)
w = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z if not height else 0)
size = max(h, w) * 1.3
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
bpy.context.scene.collection.objects.link(cam)
cam.data.type = "ORTHO"
cam.data.ortho_scale = size
d = size * 2
target = Vector((0, 0, h / 2))
cam.location = target + Vector((0, -d * math.cos(math.radians(12)), d * math.sin(math.radians(12))))
cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.camera = cam
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.5
sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(35))
bpy.context.scene.collection.objects.link(sun)
world = bpy.data.worlds.new("w")
world.use_nodes = True
bg = next(nd for nd in world.node_tree.nodes if nd.type == "BACKGROUND")
bg.inputs[0].default_value = (0.82, 0.86, 0.9, 1)
bg.inputs[1].default_value = 0.9
bpy.context.scene.world = world
ground = bpy.data.meshes.new("g")
ground.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
g = bpy.data.objects.new("ground", ground)
g.scale = (size, size, 1)
bpy.context.scene.collection.objects.link(g)
mat = bpy.data.materials.new("gm")
mat.use_nodes = True
next(nd for nd in mat.node_tree.nodes if nd.type == "BSDF_PRINCIPLED").inputs[0].default_value = (0.55, 0.6, 0.5, 1)
ground.materials.append(mat)
r = bpy.context.scene.render
engines = [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
r.engine = next(e for e in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH") if e in engines)
r.resolution_x = r.resolution_y = 360
try:
    bpy.context.scene.view_settings.view_transform = "Standard"
except TypeError:
    pass
r.image_settings.file_format = "PNG"
for i in range(n):
    pivot2.rotation_euler = (0, 0, 2 * math.pi * i / n)
    r.filepath = str(Path(out) / f"f{i:03d}.png")
    bpy.ops.render.render(write_still=True)
print(f"BENCH height={hi.z - lo.z:.3f} tris={sum(len(p.vertices) - 2 for o in meshes for p in o.data.polygons)}")
