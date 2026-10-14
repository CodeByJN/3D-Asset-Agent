# Kurama (Nine-Tails), build() code for the kit. kurama.py puts `R = {...}` (rig.data()) above this.
# One piece() per bone so Studio can pose it; Mark_* pieces are the black chakra-mode markings
# (hidden in the base form); glow_Eyes is Neon.
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
torso = [tube(spine, [3, 14, 13.5, 15, 18, 15], m=ORANGE, n=16, smooth=True)]
torso.append(ball(15.5, at=(0, -14, 50), m=ORANGE, n=16, scale=(1.05, 1.1, 1.0), smooth=True))  # deep chest
for k, (y, z) in enumerate([(-20, 40), (-24, 43), (-16, 37), (-26, 48)]):  # chest ruff hanging down
    for sx in (-1, 0, 1):
        torso.append(spike((sx * 5, y, z + 4), (sx * 0.4, -0.5, -1), 3.2, 8 + 2 * (k % 2), ORANGE))
for y in range(-14, 30, 7):  # ridge of fur along the back
    torso.append(spike((0, y, 60 + (y < 0) * 3), (0, 1, 0.9), 3.0, 7, DARK))
for sx in (-1, 1):  # shoulder and hip tufts sweeping back
    torso.append(spike((sx * 13, -14, 58), (sx * 0.5, 1, 0.6), 3.5, 10, ORANGE))
    torso.append(spike((sx * 12, 24, 54), (sx * 0.4, 1, 0.5), 3.0, 8, DARK))
piece("Torso", torso)

# ---------------------------------------------------------------- head and jaw
head = [tube([(0, -22, 59), (0, -30, 67), (0, -36, 74)], [12, 10.5, 9.5], m=ORANGE, n=16, smooth=True)]
head.append(ball(11, at=(0, -42, 80), m=ORANGE, n=18, scale=(1.05, 1.1, 0.85), smooth=True))
head.append(tube([(0, -46, 80), (0, -55, 78), (0, -63, 76.5)], [7, 5.2, 3.4], m=ORANGE, n=14, smooth=True))
head.append(ball(1.9, at=(0, -64.6, 77), m=BLACK, n=10, scale=(1.3, 1, 0.9), smooth=True))  # nose
for sx in (-1, 1):
    head.append(box((7, 2.2, 2.2), at=(sx * 5.2, -50, 85.2), rot=(0, sx * -24, sx * 14), m=ORANGE, bevel=0.6))  # brow
    head.append(box((0.5, 0.4, 2.2), at=(sx * 5.1, -52.1, 82.1), rot=(0, sx * -20, 0), m=BLACK))  # slit pupil
    head.append(box((7, 0.8, 1.0), at=(sx * 9.5, -48.6, 84.6), rot=(0, sx * -28, sx * 22), m=BLACK))  # eye line
    head.append(box((4.5, 0.8, 0.9), at=(sx * 3.5, -55.5, 80.3), rot=(0, sx * 18, sx * 12), m=BLACK))  # muzzle line
    for k in range(3):  # cheek fur flaring out and back
        head.append(spike((sx * 9, -44 + k * 3, 74 + k * 2.5), (sx * 1, 0.6, -0.3 + 0.3 * k), 3.2, 10 - k, ORANGE))
    ear = (sx * 6, -38, 86)
    path = [ear, (sx * 9, -37, 96), (sx * 13, -35, 106), (sx * 17, -33, 115)]
    head.append(blade(path, [10, 9, 6, 0], m=ORANGE, fold=0.3, up=(0, -1, 0)))
    head.append(blade([(x, y - 1.0, z) for x, y, z in path], [6.5, 6, 3.6, 0], m=BLACK, fold=0.2, up=(0, -1, 0)))
    for k in range(4):  # upper teeth along the snout, fangs at the front
        y = -48 - k * 4
        head.append(spike((sx * (3.6 - k * 0.3), y, 74.5), (0, 0, -1), 0.9 if k < 3 else 1.2, 2.6 if k < 3 else 4.5, TOOTH))
piece("Skull", head_xf(head))
piece("glow_Eyes", head_xf([ball(1.9, at=(sx * 5.3, -51.6, 82.3), m=EYE, n=10, scale=(1.5, 0.6, 0.75), smooth=True) for sx in (-1, 1)]))

jaw = [tube([(0, -42, 72.5), (0, -52, 71), (0, -61, 71.5)], [5.6, 4.3, 2.8], m=ORANGE, n=14, smooth=True)]
jaw.append(ball(3.6, at=(0, -52, 73.2), m=TONGUE, n=10, scale=(0.9, 2.0, 0.3), smooth=True))
jaw.append(spike((0, -54, 67), (0, 0.4, -1), 2.4, 5, ORANGE))  # chin tuft
for sx in (-1, 1):
    for k in range(4):
        y = -48 - k * 4
        jaw.append(spike((sx * (3.2 - k * 0.3), y, 73.5), (0, 0, 1), 0.8 if k < 3 else 1.1, 2.2 if k < 3 else 4, TOOTH))
    jaw.append(spike((sx * 5, -46, 71), (sx, 0.8, -0.2), 2.4, 7, ORANGE))
piece("Jaw", head_xf(jaw))

# ---------------------------------------------------------------- legs
for name, (pv, sx) in R["legs"].items():
    x0 = pv[0]
    if name.startswith("LegF"):
        path = [(x0, -18, 52), (x0 + sx * 3, -12, 34), (x0 + sx * 5, -22, 16), (x0 + sx * 6, -27, 8), (x0 + sx * 6, -29, 4)]
        rad = [12.5, 9.5, 7, 6, 5.6]
        paw = (x0 + sx * 6, -32, 2.8)
        parts = [tube(path, rad, m=ORANGE, n=14, smooth=True)]
        parts.append(spike((x0 + sx * 4, -8, 33), (sx * 0.3, 1, -0.3), 3.2, 10, ORANGE))  # elbow tuft
        parts.append(spike((x0 + sx * 8, -17, 22), (sx * 1, 0.5, -0.2), 2.6, 7, ORANGE))  # forearm fur
        wrist = (path[3], (0, -0.4, 1))
    else:
        path = [(x0, 22, 46), (x0 + sx * 3, 10, 28), (x0 + sx * 4, 28, 13), (x0 + sx * 4, 25, 4)]
        rad = [10.5, 7.5, 5.2, 5]
        paw = (x0 + sx * 4, 22, 2.8)
        parts = [tube(path, rad, m=ORANGE, n=14, smooth=True)]
        parts.append(ball(13, at=(x0 + sx * 2, 18, 40), m=ORANGE, n=16, scale=(0.8, 1.1, 1.25), smooth=True))  # thigh
        parts.append(spike((x0 + sx * 4, 30, 16), (0, 1, 0.2), 2.6, 8, ORANGE))  # hock tuft
        wrist = ((x0 + sx * 4, 27, 10), (0, -0.4, 1))
    parts.append(ball(6, at=paw, m=ORANGE, n=14, scale=(1.0, 1.35, 0.55), smooth=True))
    for k in range(4):  # black claws curling forward and down
        dx = (k - 1.5) * 2.6
        parts.append(spike((paw[0] + dx, paw[1] - 6.5, 1.8), (0, -1, -0.45), 1.1, 4.5, BLACK, n=6))
    piece(name, parts)
    piece("Mark_" + name, ring(wrist[0], wrist[1], rad[3] + 0.5, 0.75, INK))

# ---------------------------------------------------------------- tails
seg = R["seg"]
for i, tail in enumerate(R["tails"]):
    path, rr = tail["path"], R["tail_r"]
    for k in range(3):
        lo, hi = seg * k, seg * (k + 1)
        pts, rad = path[lo:hi + 1], rr[lo:hi + 1]
        parts = [tube(pts, rad, m=ORANGE, n=14, smooth=True)]
        if k:  # a fur ball over the joint so bending never opens a gap
            parts.append(ball(rr[lo] * 0.98, at=path[lo], m=ORANGE, n=12, smooth=True))
        for j in range(lo + 1, hi):  # tufts flaring out and back along the tail
            if j >= len(path) - 1:
                continue
            t, a, b = frame(path, j)
            r = rr[j]
            for q in range(3):
                ang = 2 * math.pi * (q / 3 + 0.21 * j)
                n_ = a * math.cos(ang) + b * math.sin(ang)
                base = V(path[j]) + n_ * r * 0.75
                parts.append(spike(tuple(base), tuple(n_ * 0.4 + t * 1.0), r * 0.38, r * 1.15,
                                   DARK if q == 0 and j % 2 else ORANGE))
        if k == 2:  # flame-like brush at the tip
            t, a, b = frame(path, len(path) - 3)
            tip = V(path[-3])
            for q in range(4):
                ang = 2 * math.pi * q / 4
                n_ = a * math.cos(ang) + b * math.sin(ang)
                parts.append(spike(tuple(tip + n_ * 1.5), tuple(t * 1.0 + n_ * 0.45), 2.4, 9, ORANGE))
        piece(f"Tail{i + 1}_{k + 1}", parts)
    marks = []  # chakra mode: two black bands on the middle of each tail
    for j in (seg + 2, seg + 4):
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
hm = [ring((0, -57, 76.5), (0, -1, -0.12), 5.4, 0.7, INK)]  # band round the muzzle
for sx in (-1, 1):
    hm.append(box((0.7, 0.7, 9), at=(sx * 7.5, -46, 77), rot=(18, sx * 10, 0), m=INK))  # cheek streaks
piece("Mark_Skull", head_xf(hm))
