"""Kurama's skeleton in kit coordinates (studs, Z up, faces -Y, his left is +X): joint pivots, each
bone's parent, and the tail curves the model is built along. Pure Python: model.py (in Blender) and
kurama.py (the Studio runtime) both read it, so the mesh and the joints always agree."""
import math

TAIL_ROOT = (0.0, 30.0, 52.0)
TAILS = 9
TAIL_SEGS = 3
TAIL_SAMPLES = 25  # points along each tail; segment k spans samples [8k, 8k+8]


def _add(a, b, k=1.0):
    return tuple(x + k * y for x, y in zip(a, b))


def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return tuple(x / n for x in v)


def _catmull(pts, n):
    """n points on a Catmull-Rom spline through pts (ends clamped)."""
    ext = [pts[0], *pts, pts[-1]]
    out = []
    for i in range(n):
        u = i / (n - 1) * (len(pts) - 1)
        k = min(int(u), len(pts) - 2)
        t = u - k
        p0, p1, p2, p3 = ext[k], ext[k + 1], ext[k + 2], ext[k + 3]
        out.append(tuple(0.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t * t
                                + (-a + 3 * b - 3 * c + d) * t ** 3) for a, b, c, d in zip(p0, p1, p2, p3)))
    return out


def tail_angle(i):
    """Fan angle of tail i from vertical, degrees (+ = his left, +X)."""
    return -105 + 210 * i / (TAILS - 1)


def _fan(deg, back):
    a = math.radians(deg)
    return _norm((math.sin(a), back, math.cos(a)))


def tail_path(i):
    """TAIL_SAMPLES points from the rump out to the tip of tail i: out of the rump, then an S-sweep
    up and outward along its fan angle, the tip flicking outward like a flame."""
    deg = tail_angle(i)
    side = 1 if deg > 0 else -1 if deg < 0 else (1 if i % 2 else -1)
    wig = 22 if i % 2 else -16  # alternate S-bends so neighbours don't run parallel
    back = 0.55 - 0.35 * abs(deg) / 105  # the upright tails lean back over the rump
    p0 = TAIL_ROOT
    p1 = _add(p0, (0, 13, 6))
    p2 = _add(p1, _fan(deg * 0.85 - side * wig * 0.6, back), 44)
    p3 = _add(p2, _fan(deg + side * wig * 0.5, back * 0.5), 44)
    p4 = _add(p3, _fan(deg + side * 45, -0.2 if abs(deg) < 60 else 0.1), 36)
    return _catmull([p0, p1, p2, p3, p4], TAIL_SAMPLES)


def tail_radius(s):
    """Tail thickness at s in [0, 1]: slim at the rump, a fat brush, pointed tip."""
    keys = [(0, 3.8), (0.12, 5.2), (0.5, 6.3), (0.8, 5.2), (0.94, 2.8), (1.0, 0.0)]
    for (s0, r0), (s1, r1) in zip(keys, keys[1:]):
        if s <= s1:
            t = (s - s0) / (s1 - s0)
            t = t * t * (3 - 2 * t)
            return r0 + (r1 - r0) * t
    return 0.0


HEAD = {"pivot": (0.0, -26.0, 62.0), "scale": 1.25, "offset": (0.0, 2.0, -10.0)}


def head_point(p):
    """Where a point modelled on the head lands: the head is modelled small and high, then scaled about
    the neck and dropped forward into a lunging pose."""
    pv, k, off = HEAD["pivot"], HEAD["scale"], HEAD["offset"]
    return tuple(c + k * (x - c) + o for x, c, o in zip(p, pv, off))


LEGS = {  # pivot (shoulder/hip) and the leg's sign (+1 his left)
    "LegFL": ((12.0, -18.0, 52.0), 1), "LegFR": ((-12.0, -18.0, 52.0), -1),
    "LegHL": ((11.0, 22.0, 48.0), 1), "LegHR": ((-11.0, 22.0, 48.0), -1),
}


def bones():
    """{bone: {"parent": name|None, "pivot": (x,y,z)}} in kit coordinates."""
    b = {"Torso": {"parent": None, "pivot": (0.0, 4.0, 50.0)},
         "Skull": {"parent": "Torso", "pivot": (0.0, -26.0, 62.0)},
         "Jaw": {"parent": "Skull", "pivot": head_point((0.0, -44.0, 73.5))}}
    for name, (pv, _) in LEGS.items():
        b[name] = {"parent": "Torso", "pivot": pv}
    seg = (TAIL_SAMPLES - 1) // TAIL_SEGS
    for i in range(TAILS):
        path = tail_path(i)
        for k in range(TAIL_SEGS):
            b[f"Tail{i + 1}_{k + 1}"] = {"parent": "Torso" if k == 0 else f"Tail{i + 1}_{k}", "pivot": path[seg * k]}
    return b


def bone_of(part):
    """The bone a mesh part rides on: Mark_X and glow_X details follow X; eyes follow the head."""
    if part.startswith("glow_"):
        return "Skull"
    return part.removeprefix("Mark_")


def data():
    """Everything model.py needs, as plain JSON-able data."""
    seg = (TAIL_SAMPLES - 1) // TAIL_SEGS
    return {"bones": bones(), "head": HEAD, "legs": {k: [list(p), s] for k, (p, s) in LEGS.items()},
            "tails": [{"path": [list(p) for p in tail_path(i)], "angle": tail_angle(i)} for i in range(TAILS)],
            "tail_r": [tail_radius(j / (TAIL_SAMPLES - 1)) for j in range(TAIL_SAMPLES)], "seg": seg}
