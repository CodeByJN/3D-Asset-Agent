"""Modelling kit for build(): small, robust helpers Claude composes into models (runs inside Blender).

Units are studs. Z is up, the model stands on z=0 and faces -Y (front view looks along +Y).
Every helper returns the new object; `at` moves it, `rot` turns it (degrees x, y, z).
Materials: mat(name, rgb) is a flat colour; mat(..., glow=True) is emissive and becomes a Neon part in
Roblox. Shading is flat (low-poly look) unless smooth=True.

  box(size, at, rot, m, bevel)          cone(r1, r2, h, at, rot, m, n)       ball(r, at, m, n, scale)
  rock(r, at, m, detail, rough, seed)   lathe(profile, at, rot, m, n)        tube(path, r, m, n)
  blade(path, width, m, fold, two_sided) extrude(shape, depth, at, rot, m)   mirror(obj), copies(obj, count)
  jitter(obj, amount, seed)             STUD (metres per stud)
"""
import math
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

__all__ = ["mat", "box", "cone", "ball", "rock", "lathe", "tube", "blade", "extrude", "mirror", "copies",
           "jitter", "STUD", "math", "Vector"]
STUD = 0.28  # metres; Roblox imports metres and shows studs


def mat(name, rgb, rough=0.8, metal=0.0, glow=False, strength=3.0):
    """A plain material. glow=True: emissive, exported as its own part and made Neon in Roblox."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except AttributeError:
        pass
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    m.diffuse_color = (*rgb, 1)
    if glow:
        for key in ("Emission Color", "Emission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = (*rgb, 1)
                break
        bsdf.inputs["Emission Strength"].default_value = strength
        m["glow"] = True
    return m


def _place(at=(0, 0, 0), rot=(0, 0, 0)):
    return Matrix.Translation(Vector(at)) @ Euler([math.radians(a) for a in rot]).to_matrix().to_4x4()


def _obj(bm, name, m, at=(0, 0, 0), rot=(0, 0, 0), smooth=False):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.transform(_place(at, rot))
    for p in me.polygons:
        p.use_smooth = smooth
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    if m is not None:
        me.materials.append(m)
    return o


def box(size=(1, 1, 1), at=(0, 0, 0), rot=(0, 0, 0), m=None, bevel=0.0, name="box"):
    """Box of `size`, centred on `at`. bevel: chamfer width in studs (catches light, reads less blocky)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bevel, segments=1, affect="EDGES",
                        profile=0.5, clamp_overlap=True)
    return _obj(bm, name, m, at, rot)


def cone(r1=1.0, r2=0.0, h=2.0, at=(0, 0, 0), rot=(0, 0, 0), m=None, n=8, name="cone", smooth=False):
    """Cylinder/cone/frustum standing on `at` (base radius r1, top radius r2)."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=n, radius1=r1, radius2=max(r2, 1e-4), depth=h)
    bmesh.ops.translate(bm, vec=(0, 0, h / 2), verts=bm.verts)
    if r2 <= 1e-4:
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=2e-4)
    return _obj(bm, name, m, at, rot, smooth)


def ball(r=1.0, at=(0, 0, 0), m=None, n=8, scale=(1, 1, 1), rot=(0, 0, 0), name="ball", smooth=False):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=n, v_segments=max(3, n // 2), radius=r)
    bmesh.ops.scale(bm, vec=Vector(scale), verts=bm.verts)
    return _obj(bm, name, m, at, rot, smooth)


def rock(r=1.0, at=(0, 0, 0), m=None, detail=1, rough=0.25, seed=1, scale=(1, 1, 0.7), rot=(0, 0, 0), name="rock"):
    """Faceted lump: icosphere with each vertex pushed in or out by up to `rough` x r."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=detail, radius=r)
    rnd = random.Random(seed)
    for v in bm.verts:
        v.co *= 1 + rough * (rnd.random() * 2 - 1)
    bmesh.ops.scale(bm, vec=Vector(scale), verts=bm.verts)
    return _obj(bm, name, m, at, rot)


def lathe(profile, at=(0, 0, 0), rot=(0, 0, 0), m=None, n=8, name="lathe", smooth=False):
    """Spin a profile [(radius, z), ...] around Z: pots, trunks, bottles, domes, mushroom caps."""
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        if r <= 1e-4:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), z))
                          for i in range(n)])
    for a, b in zip(rings, rings[1:]):
        _bridge(bm, a, b)
    for ring in (rings[0], rings[-1]):
        if len(ring) > 2:
            bm.faces.new(ring)
    return _obj(bm, name, m, at, rot, smooth)


def _bridge(bm, a, b):
    n = max(len(a), len(b))
    for i in range(n):
        j = (i + 1) % n
        if len(a) == 1:
            bm.faces.new((a[0], b[i], b[j]))
        elif len(b) == 1:
            bm.faces.new((a[i], a[j], b[0]))
        else:
            bm.faces.new((a[i], a[j], b[j], b[i]))


def _frames(path):
    """A (tangent, normal, binormal) frame per path point, parallel-transported so tubes don't twist."""
    pts = [Vector(p) for p in path]
    tans = [((pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()) for i in range(len(pts))]
    up = Vector((0, 0, 1)) if abs(tans[0].z) < 0.9 else Vector((1, 0, 0))
    nrm = tans[0].cross(up).normalized()
    out = []
    for t in tans:
        nrm = (nrm - t * nrm.dot(t)).normalized()
        out.append((t, nrm, t.cross(nrm)))
    return pts, out


def tube(path, r=0.5, m=None, n=6, name="tube", smooth=False, cap=True):
    """Sweep a circle along path [(x,y,z), ...]; r is one radius or one per point (taper to 0 for
    points). Trunks, tails, horns, tentacles, vines, handles."""
    pts, frames = _frames(path)
    rs = r if isinstance(r, (list, tuple)) else [r] * len(pts)
    bm = bmesh.new()
    rings = []
    for p, (t, nv, bv), rad in zip(pts, frames, rs):
        if rad <= 1e-4:
            rings.append([bm.verts.new(p)])
        else:
            rings.append([bm.verts.new(p + (nv * math.cos(2 * math.pi * i / n) + bv * math.sin(2 * math.pi * i / n)) * rad)
                          for i in range(n)])
    for a, b in zip(rings, rings[1:]):
        _bridge(bm, a, b)
    if cap:
        for ring in (rings[0], rings[-1]):
            if len(ring) > 2:
                bm.faces.new(ring)
    return _obj(bm, name, m, (0, 0, 0), (0, 0, 0), smooth)


def blade(path, width=0.5, m=None, fold=0.15, two_sided=True, up=(0, 0, 1), name="blade"):
    """A flat strip along path with a V-fold down its spine: leaves, palm fronds, fins, feathers, wings,
    sword edges. width is one value or one per point (0 = pointed). fold lifts the spine by
    fold x width. two_sided adds back faces (Roblox hides the back of single faces)."""
    pts = [Vector(p) for p in path]
    ws = width if isinstance(width, (list, tuple)) else [width] * len(pts)
    upv = Vector(up).normalized()
    bm = bmesh.new()
    rows = []
    for i, (p, w) in enumerate(zip(pts, ws)):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        side = t.cross(upv)
        side = side.normalized() if side.length > 1e-6 else Vector((1, 0, 0))
        lift = side.cross(t).normalized()
        if w <= 1e-4:
            v = bm.verts.new(p)
            rows.append([v, v, v])
        else:
            rows.append([bm.verts.new(p - side * w / 2), bm.verts.new(p + lift * fold * w), bm.verts.new(p + side * w / 2)])
    for a, b in zip(rows, rows[1:]):
        for k in (0, 1):
            quad = [a[k], a[k + 1], b[k + 1], b[k]]
            uniq = list(dict.fromkeys(quad))
            if len(uniq) >= 3:
                bm.faces.new(uniq)
    if two_sided:
        for f in list(bm.faces):
            vs = [bm.verts.new(v.co) for v in reversed(f.verts)]
            bm.faces.new(vs)
    o = _obj_raw(bm, name, m)
    return o


def _obj_raw(bm, name, m):
    """Like _obj but keeps face winding as built (two-sided strips must not be 'fixed')."""
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    if m is not None:
        me.materials.append(m)
    return o


def extrude(shape, depth=0.2, at=(0, 0, 0), rot=(0, 0, 0), m=None, name="extrude"):
    """A flat outline [(x, z), ...] drawn in the front view, extruded `depth` studs along Y (centred):
    blades, fins, ears, emblems, signs, crystals' faces."""
    bm = bmesh.new()
    front = [bm.verts.new((x, -depth / 2, z)) for x, z in shape]
    back = [bm.verts.new((x, depth / 2, z)) for x, z in shape]
    bm.faces.new(front)
    bm.faces.new(list(reversed(back)))
    n = len(shape)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((front[i], front[j], back[j], back[i]))
    return _obj(bm, name, m, at, rot)


def mirror(obj, axis="X", name=None):
    """A mirrored copy (left/right pairs: arms, ears, wings)."""
    o = obj.copy()
    o.data = obj.data.copy()
    o.name = name or obj.name + "_mirror"
    bpy.context.scene.collection.objects.link(o)
    s = {"X": (-1, 1, 1), "Y": (1, -1, 1), "Z": (1, 1, -1)}[axis]
    o.data.transform(Matrix.Diagonal((*s, 1)))
    o.data.flip_normals()
    return o


def copies(obj, count, axis="Z", center=(0, 0, 0), jitter_deg=0.0, seed=1):
    """count-1 extra copies turned evenly around an axis through `center` (fronds, petals, spikes)."""
    rnd = random.Random(seed)
    out = [obj]
    c = Vector(center)
    for i in range(1, count):
        o = obj.copy()
        o.data = obj.data.copy()
        bpy.context.scene.collection.objects.link(o)
        ang = 2 * math.pi * i / count + math.radians(jitter_deg) * (rnd.random() * 2 - 1)
        rmat = Matrix.Rotation(ang, 4, axis)
        o.data.transform(Matrix.Translation(c) @ rmat @ Matrix.Translation(-c))
        out.append(o)
    return out


def jitter(obj, amount=0.05, seed=1):
    """Nudge every vertex randomly by up to `amount` studs: hand-made, rough, organic surfaces."""
    rnd = random.Random(seed)
    for v in obj.data.vertices:
        v.co += Vector([amount * (rnd.random() * 2 - 1) for _ in range(3)])
    return obj
