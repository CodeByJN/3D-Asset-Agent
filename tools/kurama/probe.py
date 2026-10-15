"""Blender: orthographic clay renders of a mesh from 6 axis directions (for finding its orientation).
  blender -b -P tools/kurama/probe.py -- <mesh.glb> <out.png>"""
import math, sys, bpy
from mathutils import Vector
src, out = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
s = bpy.context.scene
s.render.engine = "BLENDER_WORKBENCH"; s.display.shading.light = "STUDIO"
s.world = bpy.data.worlds.new("w"); s.world.color = (0.3, 0.3, 0.32)
s.render.resolution_x = s.render.resolution_y = 400
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); cam.data.type = "ORTHO"; cam.data.ortho_scale = 2.4
s.collection.objects.link(cam); s.camera = cam
views = {"+x": (5, 0, 0), "-x": (-5, 0, 0), "+y": (0, 5, 0), "-y": (0, -5, 0), "+z": (0, 0, 5), "-z": (0, 0, -5)}
files = []
for k, loc in views.items():
    cam.location = loc
    up = Vector((0, 1, 0)) if k in ("+z", "-z") else Vector((0, 0, 1))
    cam.rotation_euler = (-Vector(loc)).to_track_quat("-Z", "Y" if k in ("+z", "-z") else "Z").to_euler()
    s.render.filepath = f"{out}_{k}.png"; bpy.ops.render.render(write_still=True); files.append(f"{out}_{k}.png")
