# Kurama (Nine-Tails), build() code for the kit. kurama.py puts `R = {...}` (rig.data()) above this.
# One piece() per bone so Studio can pose it; Mark_* pieces are the black chakra-mode markings (decals
# lifted off the body, hidden in the base form); glow_Eyes is Neon. R["only"] = "head" builds just the
# head and jaw (fast face iterations).
import bpy
from mathutils import Matrix


def lin(rgb):
    """Colours below are as they should look in Roblox (sRGB); Blender materials take linear values."""
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)


ORANGE = mat("fur", lin((0.93, 0.43, 0.11)), rough=0.9)
DARKRED = mat("fur_red", lin((0.68, 0.18, 0.12)), rough=0.9)  # the mask down the nose bridge
BRIGHT = mat("fur_bright", lin((0.98, 0.52, 0.14)), rough=0.9)  # brow arcs
BLACK = mat("black", lin((0.05, 0.035, 0.035)), rough=0.6)
MOUTH = mat("mouth", lin((0.42, 0.06, 0.07)))
TONGUE = mat("tongue", lin((0.86, 0.38, 0.44)))
TOOTH = mat("tooth", lin((0.97, 0.95, 0.9)), rough=0.4)
EYE = mat("eye", (1.0, 0.06, 0.03), glow=True)
INK = mat("ink", lin((0.03, 0.02, 0.02)), rough=0.5)
ONLY = R.get("only")


def V(p):
    return Vector(p)


def spike(base, d, r, h, m, n=5):
    """A cone from `base` pointing along d: fur tufts, claws, teeth."""
    o = cone(r, 0, h, m=m, n=n, smooth=True)
    q = Vector((0, 0, 1)).rotation_difference(V(d).normalized())
    o.data.transform(Matrix.Translation(V(base)) @ q.to_matrix().to_4x4())
    return o


def head_xf(objs):
    """Move head pieces into the lunging pose (rig.head_point)."""
    h = R["head"]
    pv, k, off = V(h["pivot"]), h["scale"], V(h["offset"])
    xf = Matrix.Translation(pv + off) @ Matrix.Scale(k, 4) @ Matrix.Translation(-pv)
    for o in objs:
        o.data.transform(xf)
    return objs


def fur(objs, voxel, smooth=10):
    """Fuse a piece's orange shapes into one smooth solid (voxel remesh + smoothing) so they flow into
    each other; other materials stay as they are. Returns [solid, *rest]."""
    def flat(x):
        return [z for y in x for z in flat(y)] if isinstance(x, (list, tuple)) else [x]
    objs = flat(objs)
    solid = [o for o in objs if o.data.materials and o.data.materials[0] == ORANGE]
    rest = [o for o in objs if o not in solid]
    bpy.ops.object.select_all(action="DESELECT")
    for o in solid:
        o.select_set(True)
    bpy.context.view_layer.objects.active = solid[0]
    if len(solid) > 1:
        bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    rm = o.modifiers.new("remesh", "REMESH")
    rm.mode, rm.voxel_size, rm.adaptivity = "VOXEL", voxel, 0.0
    sm = o.modifiers.new("smooth", "SMOOTH")
    sm.factor, sm.iterations = 0.6, smooth
    bpy.ops.object.modifier_apply(modifier="remesh")
    bpy.ops.object.modifier_apply(modifier="smooth")
    o.data.materials.clear()
    o.data.materials.append(ORANGE)
    for f in o.data.polygons:
        f.use_smooth = True
    return [o] + rest


def snap(obj, p, toward):
    """p moved onto obj's surface along the line from p toward `toward` (cast from well outside)."""
    p, c = V(p), V(toward)
    d = (c - p).normalized()
    bpy.context.view_layer.update()
    ok, loc, _, _ = obj.ray_cast(p - d * 40, d)
    return tuple(loc) if ok else tuple(p)


def frame(path, j):
    """Tangent and two normals of a path at sample j."""
    p = [V(x) for x in path]
    t = (p[min(j + 1, len(p) - 1)] - p[max(j - 1, 0)]).normalized()
    up = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
    a = t.cross(up).normalized()
    return t, a, t.cross(a)


def band(c, t, rad, w):
    """Region: a ring `w` wide around an axis t through c (tail and wrist bands)."""
    c, t = V(c), V(t).normalized()
    return lambda p: abs((p - c).dot(t)) <= w / 2 and (p - c).length <= rad


def spiral(c, normal, r0, r1, turns=1.25, n=40):
    """Points of a spiral drawn around c in the plane facing `normal` (chakra seals)."""
    nv = V(normal).normalized()
    a = nv.cross(Vector((0, 0, 1)) if abs(nv.z) < 0.9 else Vector((1, 0, 0))).normalized()
    b = nv.cross(a)
    out = []
    for k in range(n + 1):
        u = k / n
        ang, r = 2 * math.pi * turns * u, r0 + (r1 - r0) * u
        out.append(tuple(V(c) + (a * math.cos(ang) + b * math.sin(ang)) * r))
    return out


def seal(obj, c, normal, radius, w=1.1):
    """Region: a ring with a spiral inside it, drawn where c sits on obj's surface (shoulders, hips, belly)."""
    n = V(normal).normalized()
    s = snap(obj, V(c) + n * 10, c)
    curl = [snap(obj, V(q) + n * 10, V(q) - n) for q in spiral(s, n, 0.5, radius * 0.75)]  # spiral laid on the surface
    return any_of(ring_at(s, radius, w), near(curl, w * 0.5))


# ---------------------------------------------------------------- head and jaw
# One metaball sculpt (after the face ref and Storm 4's Kurama): long tapering muzzle with a nose ridge,
# heavy angry brows, sunken eye sockets, cheek ruffs sweeping back, tall ears grown out of the skull.
# Markings are painted on the surface: black eye sockets and stripes that run up into the black of the
# ears, a black nose, and a long black mouth line with a zigzag of teeth.
def densify(obj):
    """Split every face in four so painted markings get crisp edges (the bake keeps the detail)."""
    import bmesh as _bm
    bm = _bm.new()
    bm.from_mesh(obj.data)
    _bm.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=1, use_grid_fill=True)
    bm.to_mesh(obj.data)
    bm.free()
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


SCLERA = mat("sclera", lin((0.95, 0.95, 0.93)), rough=0.5)


def eye_regions(E, n, sx, slant=22, A=3.6, B=1.45):
    """Regions of a painted anime eye on the surface at E (normal n): the almond, a thick black outline
    heavier on top, the iris circle and its slit pupil. The outer corner tilts up by `slant` degrees."""
    E, n = V(E), V(n).normalized()
    u = Vector((0, 0, 1)).cross(n).normalized() * sx  # inner corner -> outer corner
    v = n.cross(u)
    if v.z < 0:
        v = -v
    a = math.radians(slant)
    u, v = u * math.cos(a) + v * math.sin(a), None
    v = n.cross(u)
    if v.z < 0:
        v = -v

    def local(p):
        d = p - E
        return d.dot(u), d.dot(v), abs(d.dot(n))

    def almond(p, k=1.0, top=1.0):
        x, y, z = local(p)
        if z > 3 or abs(x) > A * k:
            return False
        h = B * k * (1 - (x / (A * k)) ** 2) ** 0.75
        return -h * 0.8 <= y - 0.25 * x / A <= h * top  # the lower lid is flatter, the inner corner lower

    def iris(p):
        x, y, _ = local(p)
        return almond(p) and (x + 0.45) ** 2 + (y - 0.15) ** 2 <= 1.35 ** 2

    def pupil(p):
        x, y, _ = local(p)
        return iris(p) and abs(x + 0.45) <= 0.2 + 0.05 * abs(y)

    return {"almond": almond, "outline": lambda p: almond(p, 1.28, 1.6) and not almond(p), "iris": iris, "pupil": pupil}


def strand(path, r0, r1=0.35, n=9, stiff=2.6):
    """Metaball elements along a curve, thick at the root and tapering to a point: sculpted fur clumps."""
    pts = [V(p) for p in path]
    out = []
    for k in range(n):
        u = k / (n - 1) * (len(pts) - 1)
        i = min(int(u), len(pts) - 2)
        q = pts[i].lerp(pts[i + 1], u - i)
        r = r0 + (r1 - r0) * (k / (n - 1)) ** 0.9
        out.append((tuple(q), (r, r, r), (0, 0, 0), stiff))
    return out


GRIN = [(0, -68.6, 75.0), (1.8, -67.4, 74.9), (3.4, -63.5, 75.0), (4.6, -59, 75.4), (5.6, -55, 76.4),
        (6.6, -51.5, 77.8), (7.6, -48.5, 79.8), (8.4, -46.2, 82.0)]  # half the grin, front centre to the cheek


def head_elements():
    els = [((0, -26, 64), (11, 8, 10)), ((0, -32, 71), (10, 8, 9.5)),  # neck
           ((0, -40, 81), (12.5, 12, 9.5)), ((0, -48, 84.4), (9.5, 7.5, 4.8)),  # broad cranium, forehead
           ((0, -53, 80.2), (7.0, 9, 5.2)), ((0, -60, 78.6), (5.2, 8, 4.0)),  # muzzle tapering to the nose
           ((0, -66, 77.4), (3.6, 4.6, 2.8), (0, 0, 0), 2.6),
           ((0, -55, 82.4), (3.8, 10, 2.4), (8, 0, 0))]  # nose bridge
    for sx in (-1, 1):
        els += [((sx * 5.6, -50, 86.9), (5.6, 3.0, 2.4), (0, sx * 22, 0), 2.4),  # heavy brow overhanging the eye
                ((sx * 9.2, -47, 88.6), (2.4, 2.0, 1.6), (0, sx * 30, 0), 2.4),  # brow flicking up at the outer end
                ((sx * 8.0, -44, 81), (4.2, 6.0, 3.8)),  # cheek
                ((sx * 6.1, -51.6, 83.4), (2.9, 1.5, 1.4), (0, sx * -15, 0), 2.0, True)]  # eye socket under the brow
        # sculpted fur clumps sweeping back off the cheeks and jaw, like flames
        for path, r0 in ((((sx * 9, -46, 79), (sx * 12.5, -40.5, 79.5), (sx * 15.5, -35, 81.5)), 2.8),
                         (((sx * 8.5, -46, 76), (sx * 12, -41, 74), (sx * 15, -35.5, 72.5)), 2.6),
                         (((sx * 10, -44, 83.5), (sx * 13.5, -39.5, 86), (sx * 15.8, -35.5, 89)), 2.2),
                         (((sx * 6, -47, 72.5), (sx * 9, -43, 69.5), (sx * 11.5, -38.5, 67.5)), 2.4)):
            els += strand(path, r0)
        # tall ears: many overlapping flat elements along the ear so it reads as one leaf, not beads
        base, tip = V((sx * 7, -38, 88)), V((sx * 21.5, -33, 117))
        for k in range(12):
            u = k / 11
            w = 5.6 * (1 - u) ** 0.8 + 0.6
            els.append((tuple(base.lerp(tip, u)), (w, 1.6 * (1 - u) + 0.6, w * 1.1), (-8, sx * 27, 0), 2.4))
    return els


def grin_curve(obj):
    """The grin from cheek to cheek, laid on obj's surface."""
    axis = lambda p: (0, p[1], 80)  # noqa: E731
    pts = [(-x, y, z) for x, y, z in reversed(GRIN[1:])] + GRIN
    fine = []
    for a, b in zip(pts, pts[1:]):
        for k in range(4):
            fine.append(tuple(V(a).lerp(V(b), k / 4)))
    fine.append(pts[-1])
    return [V(snap(obj, p, axis(p))) for p in fine]


def build_head():
    els = head_elements()
    rough = blob(els, ORANGE, res=0.4, name="rough")
    curve = grin_curve(rough)  # carve the grin as a real groove, then sculpt again
    bpy.data.objects.remove(rough)
    groove = [(tuple(p), (0.8, 0.9, 0.7), (0, 0, 0), 2.0, True) for p in curve]
    skull = densify(blob(els + groove, ORANGE, res=0.3, name="skull"))
    axis = lambda p: (0, p[1], 80)  # noqa: E731  snap toward the head's long axis
    S = lambda p: snap(skull, p, axis(p))  # noqa: E731

    jaw = densify(blob([((0, -45, 73), (6, 7, 3.6)), ((0, -53, 72), (4.8, 7, 3)), ((0, -61, 72.6), (3.3, 5, 2.3)),
                        ((0, -51, 71.2), (3.4, 6, 2.0))], ORANGE, res=0.3, name="jaw"))

    # Painted after the face refs: a dark red mask down the nose bridge, bright orange brow arcs, black
    # bands that wrap each eye (pointed toward the nose) and sweep up into the ears, white eyes with red
    # irises, a big black nose and a wide grin curling up the cheeks: thick black outline, a row of teeth
    # and two long fangs at the front.
    mouth = within((0, -55, 74.2), (4.6, 12, 1.5))  # inside of the mouth, seen when the jaw drops
    paint(skull, MOUTH, mouth)
    paint(jaw, MOUTH, mouth)

    tops = {y: snap(skull, (0, y, 110), (0, y, 60))[2] for y in range(-70, -25)}
    def mask(p):  # dark red: a wedge down the nose bridge, widening over the forehead, stopping before the ears
        if p.y > -40 or p.z > 91:
            return False
        y = max(-70, min(-26, round(p.y)))
        return abs(p.x) < 1.4 + max(0.0, p.y + 66) * 0.2 and p.z > tops[y] - 2.4 - 0.3 * abs(p.x)
    paint(skull, DARKRED, mask)

    eyes, extra = [], []
    for sx in (-1, 1):
        E = V(S((sx * 5.9, -50.9, 83.5)))
        n = (E - V(axis(E))).normalized()
        brow = [S(p) for p in ((sx * 3.0, -52.8, 86.6), (sx * 5.0, -50.6, 88.4), (sx * 7.4, -48, 89.0), (sx * 9.6, -45.5, 88.2))]
        paint(skull, BRIGHT, near(brow, [0.6, 1.0, 1.0, 0.5]))  # bright brow arc over the eye
        band = [S(p) for p in ((sx * 2.4, -56.5, 81.0), (sx * 3.8, -53.6, 82.0), (sx * 6.0, -51, 83.2),
                               (sx * 8.6, -48.4, 85.0), (sx * 9.0, -43.5, 88.6), (sx * 8.4, -39.5, 90.0))]
        paint(skull, BLACK, near(band, [0.3, 1.5, 2.5, 2.6, 2.2, 1.9]))  # black band round the eye, up to the ear
        ear = [(sx * 7.6, -39, 89), (sx * 10.5, -38, 96), (sx * 14.2, -36.6, 104), (sx * 18, -35, 111), (sx * 20.6, -34, 115.5)]
        front = lambda p: p.y < -38.5 + (p.z - 88) * 0.19  # noqa: E731  the ear's front face only
        inner = near(ear, [3.6, 3.4, 2.7, 1.8, 0.8])
        paint(skull, BLACK, lambda p, f=front, i=inner: f(p) and i(p))
        er = eye_regions(E, n, sx, slant=24, A=3.9, B=1.75)  # white almond, red iris, slit pupil
        paint(skull, SCLERA, er["almond"])
        eyes.append(decal(skull, er["iris"], EYE, lift=0.12, name="iris"))
        extra.append(decal(skull, er["pupil"], BLACK, lift=0.22, name="pupil"))
        for k in range(4):  # real teeth inside the lips for when the jaw opens
            extra.append(spike((sx * (3.0 - 0.35 * k), -50 - 3.8 * k, 76.6 - 0.15 * k), (0, 0, -1),
                               0.6 if k < 3 else 0.85, 1.5 if k < 3 else 2.6, TOOTH))

    # the grin: a carved groove from cheek to cheek, black inside, lined with smooth teeth and two long fangs
    curve = grin_curve(skull)
    paint(skull, BLACK, near(curve, 1.15))
    paint(jaw, BLACK, near(curve, 1.15))
    lens = [(b - a).length for a, b in zip(curve, curve[1:])]
    total = sum(lens)
    def at(s_):  # point and tangent at arc length s_
        for a, b, ln in zip(curve, curve[1:], lens):
            if s_ <= ln:
                return a.lerp(b, s_ / max(ln, 1e-9)), (b - a).normalized()
            s_ -= ln
        return curve[-1], (curve[-1] - curve[-2]).normalized()
    s_ = 1.2
    k = 0
    while s_ < total - 1.2:
        p, t = at(s_)
        up = (Vector((0, 0, 1)) - t * t.z).normalized()
        out = (p - V(axis(p))).normalized()
        fang = abs(abs(s_ - total / 2) - 4.9) < 0.6
        if k % 2 == 0:  # upper tooth hanging from the top of the groove
            h, r = (2.6, 0.7) if fang else (1.25, 0.48)
            extra.append(spike(tuple(p + up * 0.75 - out * 0.15), tuple(-up), r, h, TOOTH, n=8))
        else:  # lower tooth standing up between them
            extra.append(spike(tuple(p - up * 0.75 - out * 0.15), tuple(up), 0.42, 1.05, TOOTH, n=8))
        s_ += 0.65
        k += 1

    tip = V(snap(skull, (0, -90, 78.4), (0, -40, 78.4)))  # the front of the muzzle
    extra.append(ball(2.0, at=tuple(tip + V((0, 0.6, 0.4))), m=BLACK, n=16, scale=(1.75, 1.0, 1.05), smooth=True))  # big nose
    jaw_teeth = [spike((sx * (3.6 - 0.45 * k), -50 - 3.8 * k, 73.4), (0, 0, 1), 0.55, 1.4, TOOTH) for sx in (-1, 1) for k in range(4)]
    tongue = ball(3.4, at=(0, -53, 73.6), m=TONGUE, n=10, scale=(0.9, 2.0, 0.3), smooth=True)

    # chakra mode: three whisker lines on each cheek and a band across the muzzle
    marks = []
    for sx in (-1, 1):
        for k in range(3):
            w = [S((sx * 6.2, -51.5 - 1.6 * k, 79.6 - 1.1 * k)), S((sx * 9.6, -47 - 1.2 * k, 79.6 - 1.2 * k)),
                 S((sx * 12, -43 - 1.0 * k, 79.8 - 1.2 * k))]
            marks.append(near(w, [0.45, 0.5, 0.2]))
    marks.append(lambda p: -59.3 <= p.y <= -58.2 and p.z > 76.5)
    mark = decal(skull, any_of(*marks), INK, lift=0.12, name="mark_skull")

    piece("Skull", head_xf([skull] + extra))
    piece("glow_Eyes", head_xf(eyes))
    piece("Jaw", head_xf([jaw, tongue] + jaw_teeth))
    piece("Mark_Skull", head_xf([mark]))


# ---------------------------------------------------------------- torso
def build_torso():
    spine = [(0, 36, 51), (0, 26, 50), (0, 12, 48), (0, -2, 50), (0, -14, 54), (0, -24, 58)]
    torso = [tube(spine, [3, 14, 13.5, 15, 18, 15], m=ORANGE, n=18, smooth=True)]
    torso.append(ball(15.5, at=(0, -14, 50), m=ORANGE, n=18, scale=(1.05, 1.1, 1.0), smooth=True))  # deep chest
    for sx, y, z, h in ((0, -24, 44, 11), (-0.6, -21, 41, 9), (0.6, -21, 41, 9), (-0.3, -17, 37, 8), (0.3, -17, 37, 8)):
        torso.append(spike((sx * 8, y, z + 4), (sx * 0.5, -0.4, -1), 4.2, h, ORANGE, n=8))  # soft chest ruff
    for sx in (-1, 1):  # shoulder tufts sweeping back
        torso.append(spike((sx * 13, -14, 58), (sx * 0.5, 1, 0.6), 4, 10, ORANGE, n=8))
    body = fur(torso, 0.6)[0]
    # chakra mode: a seal on the belly, a line down the spine, a collar round the neck
    top = [snap(body, (0, y, 90), (0, y, 40)) for y in range(-22, 37, 4)]
    regions = [seal(body, (0, -4, 36), (0, 0, -1), 7.5), near(top, 0.6),
               band((0, -24, 59), (0, -0.8, 0.6), 22, 1.4)]
    piece("Torso", [body])
    piece("Mark_Torso", [decal(body, any_of(*regions), INK, lift=0.15, name="mark_torso")])


# ---------------------------------------------------------------- legs
def build_legs():
    for name, (pv, sx) in R["legs"].items():
        x0 = pv[0]
        if name.startswith("LegF"):
            path = [(x0, -18, 52), (x0 + sx * 3, -12, 34), (x0 + sx * 5, -22, 16), (x0 + sx * 6, -27, 8), (x0 + sx * 6, -29, 4)]
            rad = [12.5, 9.5, 7, 6, 5.6]
            paw = (x0 + sx * 6, -32, 2.8)
            parts = [tube(path, rad, m=ORANGE, n=16, smooth=True)]
            parts.append(ball(12.5, at=(x0 + sx * 1, -16, 49), m=ORANGE, n=16, scale=(0.75, 1.05, 1.15), smooth=True))  # shoulder
            parts.append(spike((x0 + sx * 4, -8, 33), (sx * 0.3, 1, -0.3), 3.6, 9, ORANGE, n=8))  # elbow tuft
            wrist = (path[3], (0, -0.4, 1), rad[3])
            joint = ((x0 + sx * 1, -16, 50), (sx, -0.25, 0.15), 7.5)  # shoulder seal
        else:
            path = [(x0, 22, 46), (x0 + sx * 3, 10, 28), (x0 + sx * 4, 28, 13), (x0 + sx * 4, 25, 4)]
            rad = [10.5, 7.5, 5.2, 5]
            paw = (x0 + sx * 4, 22, 2.8)
            parts = [tube(path, rad, m=ORANGE, n=16, smooth=True)]
            parts.append(ball(13, at=(x0 + sx * 2, 18, 41), m=ORANGE, n=16, scale=(0.8, 1.15, 1.3), smooth=True))  # haunch
            wrist = ((x0 + sx * 4, 27, 10), (0, -0.4, 1), 5.0)
            joint = ((x0 + sx * 2, 18, 42), (sx, 0.1, 0.1), 7.0)  # hip seal
        parts.append(ball(6, at=paw, m=ORANGE, n=14, scale=(1.0, 1.35, 0.55), smooth=True))
        claws = [spike((paw[0] + (k - 1.5) * 2.6, paw[1] - 6.5, 1.8), (0, -1, -0.45), 1.1, 4.5, BLACK, n=6) for k in range(4)]
        leg = fur(parts, 0.45)[0]
        # chakra mode: a seal on the shoulder or hip, a line down the front of the leg, a band at the wrist
        front = [snap(leg, (p[0], p[1] - 20, p[2]), p) for p in path[1:]]
        regions = [seal(leg, joint[0], joint[1], joint[2]), near(front, 0.55),
                   band(wrist[0], wrist[1], wrist[2] + 4, 1.4)]
        piece(name, [leg] + claws)
        piece("Mark_" + name, [decal(leg, any_of(*regions), INK, lift=0.15, name="mark_" + name)])


# ---------------------------------------------------------------- tails: long, slim and smooth, a soft brush at the tip
def build_tails():
    seg = R["seg"]
    for i, tail in enumerate(R["tails"]):
        path, rr = tail["path"], R["tail_r"]
        for k in range(3):
            lo, hi = seg * k, seg * (k + 1)
            parts = [tube(path[lo:hi + 1], rr[lo:hi + 1], m=ORANGE, n=14, smooth=True)]
            if k:  # a ball over the joint so bending never opens a gap
                parts.append(ball(rr[lo] * 1.02, at=path[lo], m=ORANGE, n=14, smooth=True))
            if k == 2:
                t, a, b = frame(path, len(path) - 3)
                tip = V(path[-3])
                for q in range(3):
                    ang = 2 * math.pi * q / 3
                    n_ = a * math.cos(ang) + b * math.sin(ang)
                    parts.append(spike(tuple(tip + n_ * 1.0), tuple(t * 1.0 + n_ * 0.3), 1.8, 6.5, ORANGE, n=8))
            solid = fur(parts, 0.4)[0]
            piece(f"Tail{i + 1}_{k + 1}", [solid])
            # chakra mode: two bands per segment
            regions = []
            for j in (lo + seg // 3, lo + 2 * seg // 3):
                t, _, _ = frame(path, j)
                regions.append(band(path[j], t, rr[j] + 3, 1.3))
            piece(f"Mark_Tail{i + 1}_{k + 1}", [decal(solid, any_of(*regions), INK, lift=0.12, name=f"mark_tail{i}{k}")])


build_head()
if ONLY != "head":
    build_torso()
    build_legs()
    build_tails()
