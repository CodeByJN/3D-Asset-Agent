# Kurama (Nine-Tails), build() code for the kit. kurama.py puts `R = {...}` (rig.data()) above this.
# One piece() per bone so Studio can pose it; Mark_* pieces are the black chakra-mode markings
# (hidden in the base form); glow_Eyes is Neon.
import bpy
from mathutils import Matrix

def lin(rgb):
    """Colours below are as they should look in Roblox (sRGB); Blender materials take linear values."""
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)


ORANGE = mat("fur", lin((0.93, 0.36, 0.06)), rough=0.9)
DARK = mat("fur_dark", lin((0.78, 0.24, 0.04)), rough=0.9)
BLACK = mat("black", lin((0.06, 0.04, 0.04)), rough=0.6)
MOUTH = mat("mouth", lin((0.45, 0.06, 0.07)))
TONGUE = mat("tongue", lin((0.88, 0.4, 0.45)))
TOOTH = mat("tooth", lin((0.97, 0.95, 0.88)), rough=0.4)
EYE = mat("eye", (1.0, 0.08, 0.03), glow=True)
INK = mat("ink", lin((0.03, 0.02, 0.02)), rough=0.5)


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
    """Fuse a piece's orange shapes into one smooth sculpted solid (voxel remesh + smoothing), so tufts,
    brows, shoulders and paws flow into the body instead of reading as separate primitives. Thin blades
    (ears) and other materials (eyes, teeth, claws, stripes) stay as they are."""
    def flat(x):
        return [z for y in x for z in flat(y)] if isinstance(x, (list, tuple)) else [x]
    objs = flat(objs)
    solid = [o for o in objs if o.data.materials and o.data.materials[0] == ORANGE and not o.name.startswith("blade")]
    rest = [o for o in objs if o not in solid]
    if not solid:
        return rest
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


def frame(path, j):
    """Tangent and two normals of a path at sample j."""
    p = [V(x) for x in path]
    t = (p[min(j + 1, len(p) - 1)] - p[max(j - 1, 0)]).normalized()
    up = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
    a = t.cross(up).normalized()
    return t, a, t.cross(a)


def ring(c, t, rad, w, m, n=20):
    """A thin band around an axis t through c (markings around tails, legs, neck)."""
    t = V(t).normalized()
    up = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
    a = t.cross(up).normalized()
    b = t.cross(a)
    pts = [tuple(V(c) + (a * math.cos(2 * math.pi * k / n) + b * math.sin(2 * math.pi * k / n)) * rad) for k in range(n + 1)]
    return tube(pts, w, m=m, n=5, smooth=True, cap=False)


def side_ring(cx, cy, cz, rad, w, m, n=24, bulge=None):
    """A circle drawn on the flank (facing +-X) hugging a body that bulges out by `bulge(dy, dz)`."""
    pts = []
    for k in range(n + 1):
        a = 2 * math.pi * k / n
        dy, dz = rad * math.cos(a), rad * math.sin(a)
        x = cx + (bulge(dy, dz) if bulge else 0) * (1 if cx > 0 else -1)
        pts.append((x, cy + dy, cz + dz))
    return tube(pts, w, m=m, n=5, smooth=True, cap=False)


# ---------------------------------------------------------------- torso
spine = [(0, 36, 51), (0, 26, 50), (0, 12, 48), (0, -2, 50), (0, -14, 54), (0, -24, 58)]
torso = [tube(spine, [3, 14, 13.5, 15, 18, 15], m=ORANGE, n=18, smooth=True)]
torso.append(ball(15.5, at=(0, -14, 50), m=ORANGE, n=18, scale=(1.05, 1.1, 1.0), smooth=True))  # deep chest
for sx, y, z, h in ((0, -24, 44, 11), (-0.6, -21, 41, 9), (0.6, -21, 41, 9), (-0.3, -17, 37, 8), (0.3, -17, 37, 8)):
    torso.append(spike((sx * 8, y, z + 4), (sx * 0.5, -0.4, -1), 4.2, h, ORANGE, n=8))  # soft chest ruff
for sx in (-1, 1):  # shoulder tufts sweeping back
    torso.append(spike((sx * 13, -14, 58), (sx * 0.5, 1, 0.6), 4, 10, ORANGE, n=8))
piece("Torso", fur(torso, 0.6))

# ---------------------------------------------------------------- head and jaw (after the face ref: long muzzle,
# heavy brows, red slit eyes with black stripes running back to the ears, a black lip line and a toothy grin)
SKULL_C = V((0, -41, 81))
SHELLS = [(V((0, -41, 81)), V((11, 11.5, 9))), (V((0, -47, 84.5)), V((8.8, 8, 4.6)))]  # skull, brow (centre, radii)
MUZZLE = [(-45, 80, 7.2), (-53, 78.5, 5.6), (-61, 76.5, 4.2), (-67, 75.2, 3.0)]  # (y, centre z, radius)


def surf(p, lift=0.35):
    """p pushed out from the skull centre onto the skull/brow surface (plus lift): marks that hug the head."""
    d = (V(p) - SKULL_C).normalized()
    best = 0.0
    for c, r in SHELLS:
        o = SKULL_C - c
        A = sum((d[i] / r[i]) ** 2 for i in range(3))
        B = 2 * sum(o[i] * d[i] / r[i] ** 2 for i in range(3))
        C = sum((o[i] / r[i]) ** 2 for i in range(3)) - 1
        disc = B * B - 4 * A * C
        if disc >= 0:
            best = max(best, (-B + math.sqrt(disc)) / (2 * A))
    return tuple(SKULL_C + d * (best + lift))


def muzzle_at(y):
    for (y0, z0, r0), (y1, z1, r1) in zip(MUZZLE, MUZZLE[1:]):
        if y1 <= y <= y0:
            u = (y - y0) / (y1 - y0)
            return z0 + (z1 - z0) * u, r0 + (r1 - r0) * u
    return MUZZLE[-1][1], MUZZLE[-1][2]


head = [tube([(0, -22, 59), (0, -30, 67), (0, -36, 74)], [12, 10.5, 9.5], m=ORANGE, n=18, smooth=True)]
head.append(ball(11, at=tuple(SHELLS[0][0]), m=ORANGE, n=20, scale=(1, 11.5 / 11, 9 / 11), smooth=True))
head.append(ball(8, at=tuple(SHELLS[1][0]), m=ORANGE, n=18, scale=(1.1, 1.0, 4.6 / 8), smooth=True))  # brow mass
head.append(tube([(0, y, z) for y, z, _ in MUZZLE], [r for _, _, r in MUZZLE], m=ORANGE, n=18, smooth=True))
head.append(ball(1.9, at=(0, -68.0, 76.0), m=BLACK, n=12, scale=(1.25, 0.9, 0.75), smooth=True))  # nose
head.append(ball(4, at=(0, -54, 75.2), m=MOUTH, n=10, scale=(0.9, 2.2, 0.3), smooth=True))  # palate (open jaw)
eyes = []
for sx in (-1, 1):
    E = V(surf((sx * 5.6, -51, 83.4), lift=-1.1))  # set deep under the brow: narrow, slanted, menacing
    head.append(ball(2.4, at=tuple(E), m=TOOTH, n=12, scale=(1.6, 0.5, 0.5), rot=(0, -sx * 30, sx * 20), smooth=True))
    eyes.append(ball(0.95, at=tuple(E + V((0, -0.75, 0))), m=EYE, n=10, scale=(1, 1, 1.15), smooth=True))
    head.append(box((0.3, 0.3, 1.5), at=tuple(E + V((0, -1.75, 0))), rot=(0, -sx * 10, 0), m=BLACK))  # slit pupil
    head.append(tube([tuple(E + V((sx * -3.4, -0.6, -0.9))), tuple(E + V((0, -1.25, -1.05))), tuple(E + V((sx * 3.6, -0.5, 1.2)))],
                     0.32, m=BLACK, n=6, smooth=True))  # dark lower lid line
    head.append(ball(3.6, at=surf((sx * 5.2, -49.5, 86.8), 0.2), m=ORANGE, n=12, scale=(1.4, 0.8, 0.45),
                     rot=(0, -sx * 28, sx * 15), smooth=True))  # heavy brow
    stripe = [surf(p, 0.25) for p in ((sx * 2.6, -54.5, 82.4), (sx * 4.2, -51, 86), (sx * 5.6, -47, 89), (sx * 6.6, -42.5, 90.6),
                                       (sx * 7.0, -38.5, 90.4))]
    head.append(tube(stripe, [0.7, 1.15, 1.1, 0.9, 0.4], m=BLACK, n=8, smooth=True))  # eye stripe up to the ear
    outer = [surf(p, 0.25) for p in ((sx * 8.2, -49.5, 83.6), (sx * 9.8, -46, 84.4), (sx * 10.8, -42, 85.2), (sx * 10.8, -38, 86))]
    head.append(tube(outer, [0.8, 0.85, 0.6, 0.25], m=BLACK, n=8, smooth=True))
    lip = [(sx * 7.6, -44.5, 77.6)]  # the grin curls up at the back
    for y in [-47 - 1.5 * k for k in range(13)]:
        zc, r = muzzle_at(y)
        lip.append((sx * r * 0.8, y, zc - r * 0.6))
    head.append(tube(lip, 0.45, m=BLACK, n=6, smooth=True))
    for k, (x, y, z) in enumerate(lip[2:]):  # zigzag of teeth along the lip, fangs at the front
        big = k >= 10
        up = k % 2 == 1
        head.append(spike((x + sx * 0.15, y, z + (-0.5 if up else 0.5)), (sx * 0.15, 0, 1 if up else -1),
                          0.75 if big else 0.55, 2.4 if big else 1.4, TOOTH, n=5))
    for d, h in (((sx, 0.7, -0.2), 9), ((sx, 0.8, 0.25), 8)):  # two soft cheek tufts
        head.append(spike((sx * 9.6, -43 + 3 * (h == 8), 76 + 4 * (h == 8)), d, 3.4, h, ORANGE, n=8))
    path = [(sx * 7, -37, 88), (sx * 11, -36, 98), (sx * 16, -34, 108), (sx * 21, -32, 116)]  # flat ears, spread wide
    head.append(blade(path, [11, 10, 7, 0], m=ORANGE, fold=0.0, up=(0, -1, 0)))
    head.append(blade([(x, y - 0.6, z) for x, y, z in path[1:]], [6.5, 4.5, 0], m=BLACK, fold=0.0, up=(0, -1, 0)))
piece("Skull", head_xf(fur(head, 0.3)))
piece("glow_Eyes", head_xf(eyes))

jaw = [tube([(0, -43, 73), (0, -52, 71.8), (0, -61, 72), (0, -66, 72.8)], [5.8, 4.5, 3.3, 2.4], m=ORANGE, n=16, smooth=True)]
jaw.append(ball(3.6, at=(0, -53, 74.4), m=TONGUE, n=10, scale=(0.9, 2.0, 0.3), smooth=True))
jaw.append(spike((0, -55, 68.5), (0, 0.4, -1), 2.4, 5, ORANGE, n=8))  # chin tuft
for sx in (-1, 1):
    for k in range(5):
        y = -47 - k * 3.6
        jaw.append(spike((sx * (3.4 - k * 0.3), y, 74.6), (0, 0, 1), 0.7 if k < 4 else 1.0, 1.8 if k < 4 else 3.4, TOOTH, n=5))
piece("Jaw", head_xf(fur(jaw, 0.3)))

# ---------------------------------------------------------------- legs
for name, (pv, sx) in R["legs"].items():
    x0 = pv[0]
    if name.startswith("LegF"):
        path = [(x0, -18, 52), (x0 + sx * 3, -12, 34), (x0 + sx * 5, -22, 16), (x0 + sx * 6, -27, 8), (x0 + sx * 6, -29, 4)]
        rad = [12.5, 9.5, 7, 6, 5.6]
        paw = (x0 + sx * 6, -32, 2.8)
        parts = [tube(path, rad, m=ORANGE, n=16, smooth=True)]
        parts.append(ball(12.5, at=(x0 + sx * 1, -16, 49), m=ORANGE, n=16, scale=(0.75, 1.05, 1.15), smooth=True))  # shoulder
        parts.append(spike((x0 + sx * 4, -8, 33), (sx * 0.3, 1, -0.3), 3.6, 9, ORANGE, n=8))  # elbow tuft
        wrist = (path[3], (0, -0.4, 1))
    else:
        path = [(x0, 22, 46), (x0 + sx * 3, 10, 28), (x0 + sx * 4, 28, 13), (x0 + sx * 4, 25, 4)]
        rad = [10.5, 7.5, 5.2, 5]
        paw = (x0 + sx * 4, 22, 2.8)
        parts = [tube(path, rad, m=ORANGE, n=16, smooth=True)]
        parts.append(ball(13, at=(x0 + sx * 2, 18, 41), m=ORANGE, n=16, scale=(0.8, 1.15, 1.3), smooth=True))  # haunch
        wrist = ((x0 + sx * 4, 27, 10), (0, -0.4, 1))
    parts.append(ball(6, at=paw, m=ORANGE, n=14, scale=(1.0, 1.35, 0.55), smooth=True))
    for k in range(4):  # black claws curling forward and down
        dx = (k - 1.5) * 2.6
        parts.append(spike((paw[0] + dx, paw[1] - 6.5, 1.8), (0, -1, -0.45), 1.1, 4.5, BLACK, n=6))
    piece(name, fur(parts, 0.45))
    piece("Mark_" + name, ring(wrist[0], wrist[1], rad[3] + 0.5, 0.75, INK))

# ---------------------------------------------------------------- tails: long, slim and smooth, a soft brush at the tip
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
        piece(f"Tail{i + 1}_{k + 1}", fur(parts, 0.4))
    marks = []  # chakra mode: two black bands on the middle of each tail
    for j in (seg + 2, seg + 5):
        t, _, _ = frame(path, j)
        marks.append(ring(path[j], t, rr[j] + 0.45, 0.8, INK))
    piece(f"Mark_Tail{i + 1}_2", marks)

# ---------------------------------------------------------------- chakra-mode markings on body and head
def flank(cy, cz):  # how far the torso's side sits out from x = 0 at (y, z): an ellipse-ish body
    return lambda dy, dz: max(0.0, 13.8 - 0.012 * (dz + cz - 52) ** 2 - 0.004 * (dy + cy + 6) ** 2)


marks = []
for sx in (-1, 1):
    for cy, cz, rad in ((-14, 52, 8.5), (22, 47, 7.5)):  # spiral circles on shoulders and hips
        marks.append(side_ring(sx * 0.7, cy, cz, rad, 0.9, INK, bulge=flank(cy, cz)))
        marks.append(side_ring(sx * 0.9, cy, cz, rad * 0.45, 0.7, INK, bulge=flank(cy, cz)))
marks.append(ring((0, -24, 60), (0, -0.8, 0.6), 13.4, 1.0, INK))  # collar
piece("Mark_Torso", marks)
hm = [ring((0, -57, 77.5), (0, -1, -0.15), 5.3, 0.7, INK)]  # band round the muzzle
for sx in (-1, 1):
    hm.append(box((0.7, 0.7, 9), at=(sx * 7.5, -46, 77), rot=(18, sx * 10, 0), m=INK))  # cheek streaks
piece("Mark_Skull", head_xf(hm))
