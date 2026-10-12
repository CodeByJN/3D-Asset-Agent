"""Build fixture meshes: a textured crate body and lid as separate GLBs.

Run: blender -b --factory-startup -P tests/make_fixtures.py -- <out_dir>
"""
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix

out = Path(sys.argv[sys.argv.index("--") + 1])
out.mkdir(parents=True, exist_ok=True)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)


def make_part(name, scale, z, cuts, grid):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bm.loops.layers.uv.new("UVMap")
    bmesh.ops.create_cube(bm, size=1.0, calc_uvs=True)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    bmesh.ops.transform(bm, matrix=Matrix.Translation((0, 0, z)) @ Matrix.Diagonal((*scale, 1)), verts=bm.verts[:])
    bm.to_mesh(me)
    bm.free()
    img = bpy.data.images.new(f"{name}_tex", 256, 256)
    img.generated_type = grid
    png = out / f"{name}.png"
    img.save_render(str(png))
    img = bpy.data.images.load(str(png))
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except AttributeError:
        pass
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = img
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(out / f"{name}.glb"), export_format="GLB", use_selection=True)


make_part("body", (1.0, 1.0, 1.2), 0.6, 12, "COLOR_GRID")
make_part("lid", (1.05, 1.05, 0.2), 1.3, 8, "UV_GRID")
print("FIXTURES_OK")
