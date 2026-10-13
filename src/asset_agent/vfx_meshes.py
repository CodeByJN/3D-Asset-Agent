"""Procedural HD meshes for VFX: crystals, planets, rings, blades and bevelled cubes.

A preset uses one as a MeshPart with MeshId "mesh://kind?key=value&..." (e.g. "mesh://crystal?sides=7&seed=3").
Studio builds it as an EditableMesh (no upload needed); the node's Size scales it. Each mesh fits in
a unit box (-0.5..0.5) so Size is its size in studs. Faceted kinds (crystal, blade, cube, shard) use
unshared vertices so every facet catches the light; round kinds (sphere, torus) share vertices.
"""
import math
import random
from urllib.parse import parse_qsl

ROUND = 4  # decimals sent to Studio


def _fit(verts):
    """Scale and centre vertices into the unit box."""
    lo = [min(v[i] for v in verts) for i in range(3)]
    hi = [max(v[i] for v in verts) for i in range(3)]
    return [tuple((v[i] - (lo[i] + hi[i]) / 2) / max(hi[i] - lo[i], 1e-6) for i in range(3)) for v in verts]


def _flat(verts, tris):
    """Unshared vertices: one per triangle corner (hard facets)."""
    out_v, out_f = [], []
    for a, b, c in tris:
        out_f.append((len(out_v), len(out_v) + 1, len(out_v) + 2))
        out_v += [verts[a], verts[b], verts[c]]
    return out_v, out_f


def sphere(sub=4, noise=0.0, seed=0):
    """Icosphere (sub 4 = 5120 tris). noise roughens the surface (rocky moons)."""
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    v = [tuple(x / math.sqrt(sum(c * c for c in p)) for x in p) for p in v]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
         (8, 6, 7), (9, 8, 1)]
    for _ in range(int(sub)):
        mid, nf = {}, []

        def m(a, b):
            k = (min(a, b), max(a, b))
            if k not in mid:
                p = [(v[a][i] + v[b][i]) / 2 for i in range(3)]
                ln = math.sqrt(sum(c * c for c in p))
                v.append(tuple(c / ln for c in p))
                mid[k] = len(v) - 1
            return mid[k]
        for a, b, c in f:
            ab, bc, ca = m(a, b), m(b, c), m(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        f = nf
    if noise:
        rnd = random.Random(int(seed))
        bumps = [(tuple(rnd.uniform(-1, 1) for _ in range(3)), rnd.uniform(2, 6), rnd.uniform(-1, 1)) for _ in range(12)]
        v = [tuple(c * (1 + noise * sum(w * math.sin(fr * sum(p[i] * d[i] for i in range(3)))
                                        for d, fr, w in bumps) / 6) for c in p) for p in v]
    return _fit(v), f


def torus(tube=0.06, seg=128, ring=12):
    """A ring: radius 1, tube radius `tube` (relative), lying flat (in XZ)."""
    v, f = [], []
    seg, ring = int(seg), int(ring)
    for i in range(seg):
        a = 2 * math.pi * i / seg
        for j in range(ring):
            b = 2 * math.pi * j / ring
            r = 1 + tube * math.cos(b)
            v.append((r * math.cos(a), tube * math.sin(b), r * math.sin(a)))
    for i in range(seg):
        for j in range(ring):
            a, b = i * ring + j, ((i + 1) % seg) * ring + j
            c, d = ((i + 1) % seg) * ring + (j + 1) % ring, i * ring + (j + 1) % ring
            f += [(a, d, b), (b, d, c)]
    return _fit(v), f


def crystal(sides=6, tip=0.35, base=0.12, jitter=0.12, seed=0):
    """A faceted crystal column standing on Y: a prism with a pointed top and a short point below.
    jitter makes each facet a little irregular, like real quartz."""
    rnd = random.Random(int(seed))
    sides = int(sides)
    ring = []
    for i in range(sides):
        a = 2 * math.pi * (i + rnd.uniform(-jitter, jitter)) / sides
        r = 1 + rnd.uniform(-jitter, jitter)
        ring.append((r * math.cos(a), r * math.sin(a)))
    h = 1.0
    top_y, bot_y = h / 2 - tip * h, -h / 2 + base * h
    v = [(x, top_y + rnd.uniform(-0.03, 0.03), z) for x, z in ring] + [(x, bot_y, z) for x, z in ring]
    apex = (rnd.uniform(-0.1, 0.1), h / 2, rnd.uniform(-0.1, 0.1))
    v += [apex, (0, -h / 2, 0)]
    t, b = 2 * sides, 2 * sides + 1
    f = []
    for i in range(sides):
        j = (i + 1) % sides
        f += [(i, j, sides + j), (i, sides + j, sides + i), (t, j, i), (b, sides + i, sides + j)]
    return _flat(_fit(v), f)


def blade(hook=0.0, thick=0.18, seg=10):
    """A crystal blade along +Y with a diamond cross-section, tapering to a point; hook bends the tip
    sideways (+X) like the curved wings of a star emblem."""
    seg = int(seg)
    v, f = [], []
    for k in range(seg + 1):
        u = k / seg
        w = math.sin(math.pi * min(1.0, 0.15 + u * 0.95)) * (1 - u) ** 0.35 if u < 1 else 0
        cx = hook * u ** 2
        y = u
        v += [(cx + w * 0.5, y, 0), (cx, y, thick * w), (cx - w * 0.5, y, 0), (cx, y, -thick * w)]
    for k in range(seg):
        for i in range(4):
            a, b = k * 4 + i, k * 4 + (i + 1) % 4
            c, d = a + 4, b + 4
            f += [(a, c, b), (b, c, d)]
    v.append((0, 0, 0))
    root = len(v) - 1
    for i in range(4):
        f.append((root, i, (i + 1) % 4))
    return _flat(_fit(v), f)


def cube(bevel=0.12):
    """A cube with chamfered edges and corners (catches highlights on every edge)."""
    e = 0.5 - bevel
    v, f = [], []

    def quad(a, b, c, d):
        i = len(v)
        v.extend([a, b, c, d])
        f.extend([(i, i + 1, i + 2), (i, i + 2, i + 3)])
    for ax in range(3):
        for s in (-1, 1):
            def p(u, w):
                q = [0, 0, 0]
                q[ax], q[(ax + 1) % 3], q[(ax + 2) % 3] = 0.5 * s, u, w
                return tuple(q)
            pts = [p(-e, -e), p(e, -e), p(e, e), p(-e, e)]
            quad(*(pts if s > 0 else pts[::-1]))
    # edge chamfers and corner triangles: the convex hull of the 24 face corners
    return _flat(*_hull(list({tuple(round(c, 6) for c in x) for x in v})))


def shard(seed=0, sides=5):
    """A small irregular crystal fragment (debris)."""
    rnd = random.Random(int(seed))
    pts = []
    for i in range(int(sides)):
        a = 2 * math.pi * i / int(sides) + rnd.uniform(-0.3, 0.3)
        pts.append((math.cos(a) * rnd.uniform(0.6, 1), rnd.uniform(-0.2, 0.2), math.sin(a) * rnd.uniform(0.6, 1)))
    pts += [(rnd.uniform(-0.2, 0.2), rnd.uniform(1, 1.6), rnd.uniform(-0.2, 0.2)),
            (rnd.uniform(-0.2, 0.2), -rnd.uniform(0.6, 1.1), rnd.uniform(-0.2, 0.2))]
    hv, hf = _hull(pts)
    return _flat(_fit(hv), hf)


def _hull(pts):
    """Convex hull triangles (outward winding) of a small point set: brute force, fine for <60 points."""
    n, faces = len(pts), []
    sub = lambda a, b: (a[0] - b[0], a[1] - b[1], a[2] - b[2])  # noqa: E731
    cross = lambda a, b: (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])  # noqa: E731
    dot = lambda a, b: a[0] * b[0] + a[1] * b[1] + a[2] * b[2]  # noqa: E731
    cen = tuple(sum(p[i] for p in pts) / n for i in range(3))
    seen = set()
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                nrm = cross(sub(pts[j], pts[i]), sub(pts[k], pts[i]))
                if dot(nrm, nrm) < 1e-12:
                    continue
                side = [dot(nrm, sub(pts[m], pts[i])) for m in range(n) if m not in (i, j, k)]
                if all(s <= 1e-9 for s in side) or all(s >= -1e-9 for s in side):
                    tri = (i, j, k) if dot(nrm, sub(cen, pts[i])) < 0 else (i, k, j)
                    key = frozenset(tri)
                    if key not in seen:
                        seen.add(key)
                        faces.append(tri)
    return pts, faces


KINDS = {"sphere": sphere, "torus": torus, "crystal": crystal, "blade": blade, "cube": cube, "shard": shard}


def build(spec: str):
    """'mesh://crystal?sides=7&seed=2' (or 'crystal?...') -> (vertices, triangles)."""
    spec = spec.removeprefix("mesh://")
    kind, _, query = spec.partition("?")
    if kind not in KINDS:
        raise ValueError(f"unknown mesh kind {kind!r}: one of {', '.join(KINDS)}")
    return KINDS[kind](**{k: float(v) for k, v in parse_qsl(query)})


def mesh_data(spec: str) -> dict:
    """A mesh for transport to Studio: {v: [x,y,z,...], f: [a,b,c,...]} (0-based)."""
    v, f = build(spec)
    return {"v": [round(c, ROUND) for p in v for c in p], "f": [i for t in f for i in t]}
