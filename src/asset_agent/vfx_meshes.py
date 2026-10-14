"""Procedural HD meshes for VFX: crystals, planets, rings, blades, bevelled cubes and glowing edges.

A preset uses one as a MeshPart with MeshId "mesh://kind?key=value&..." (e.g. "mesh://crystal?sides=7&seed=3").
Studio builds it as an EditableMesh (no upload needed); the node's Size scales it. Each mesh fits in
a unit box (-0.5..0.5) so Size is its size in studs. Faceted kinds (crystal, blade, cube, shard) use
unshared vertices so every facet catches the light; round kinds (sphere, torus) share vertices.
globe has UVs, so a texture (TextureID texture://map_...) wraps around it. frame and blade_edge are the
glowing edges of a box and of a blade: give them the same Size and CFrame as the body they outline.
"mesh://asset/<name>" is the exported model of an asset (make_asset, import_mesh, build), e.g. a generated hero model.
"""
import math
import random
from pathlib import Path
from urllib.parse import parse_qsl

ROUND = 4  # decimals sent to Studio


def _fit(verts, like=None):
    """Scale and centre vertices into the unit box (the box of `like` when given: edges that outline a
    body keep its proportions, so both take the same Size)."""
    ref = like or verts
    lo = [min(v[i] for v in ref) for i in range(3)]
    hi = [max(v[i] for v in ref) for i in range(3)]
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


def globe(seg=96, rings=48):
    """A UV sphere: smooth, with an equirectangular UV map (u around, v pole to pole) for surface textures."""
    seg, rings = int(seg), int(rings)
    v, uv, f = [], [], []
    for j in range(rings + 1):
        th = math.pi * j / rings
        for i in range(seg + 1):  # the seam column is doubled so the texture wraps cleanly
            ph = 2 * math.pi * i / seg
            v.append((math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph)))
            uv.append((i / seg, j / rings))
    for j in range(rings):
        for i in range(seg):
            a, b = j * (seg + 1) + i, j * (seg + 1) + i + 1
            c, d = a + seg + 1, b + seg + 1
            if j:
                f.append((a, b, c))
            if j < rings - 1:
                f.append((b, d, c))
    return _fit(v), f, uv


def _tube(path, radius, sides=6, closed=False):
    """A thin round tube along a polyline (glowing edges and grooves)."""
    v, f = [], []
    n = len(path)
    for k, p in enumerate(path):
        a = path[(k - 1) % n if closed else max(k - 1, 0)]
        b = path[(k + 1) % n if closed else min(k + 1, n - 1)]
        t = [b[i] - a[i] for i in range(3)]
        ln = math.sqrt(sum(c * c for c in t)) or 1
        t = [c / ln for c in t]
        up = (0, 0, 1) if abs(t[2]) < 0.9 else (1, 0, 0)
        u = [t[1] * up[2] - t[2] * up[1], t[2] * up[0] - t[0] * up[2], t[0] * up[1] - t[1] * up[0]]
        ln = math.sqrt(sum(c * c for c in u)) or 1
        u = [c / ln for c in u]
        w = [t[1] * u[2] - t[2] * u[1], t[2] * u[0] - t[0] * u[2], t[0] * u[1] - t[1] * u[0]]
        for s_ in range(sides):
            ang = 2 * math.pi * s_ / sides
            v.append(tuple(p[i] + radius * (math.cos(ang) * u[i] + math.sin(ang) * w[i]) for i in range(3)))
    for k in range(n if closed else n - 1):
        k2 = (k + 1) % n
        for s_ in range(sides):
            a, b = k * sides + s_, k * sides + (s_ + 1) % sides
            c, d = k2 * sides + s_, k2 * sides + (s_ + 1) % sides
            f += [(a, c, b), (b, c, d)]
    if not closed:  # cap the ends
        for k, flip in ((0, True), (n - 1, False)):
            v.append(path[k])
            m = len(v) - 1
            for s_ in range(sides):
                a, b = k * sides + s_, k * sides + (s_ + 1) % sides
                f.append((m, b, a) if flip else (m, a, b))
    return v, [(a, c, b) for a, b, c in f]  # outward


def _merge(parts):
    v, f = [], []
    for pv, pf in parts:
        f += [(a + len(v), b + len(v), c + len(v)) for a, b, c in pf]
        v += pv
    return v, f


def frame(r=0.025):
    """The 12 glowing edges of a box (outline a Part of the same Size)."""
    h = 0.5
    corners = [(x, y, z) for x in (-h, h) for y in (-h, h) for z in (-h, h)]
    edges = [(a, b) for i, a in enumerate(corners) for b in corners[i + 1:] if sum(a[k] != b[k] for k in range(3)) == 1]
    v, f = _merge(_tube([a, b], r, 6) for a, b in edges)
    return _fit(v, corners), f


def _blade_profile(hook, seg):
    pts = []
    for k in range(seg + 1):
        u = k / seg
        w = math.sin(math.pi * min(1.0, 0.15 + u * 0.95)) * (1 - u) ** 0.35 if u < 1 else 0
        pts.append((hook * u ** 2, u, w))
    return pts


def blade(hook=0.0, thick=0.18, seg=10):
    """A crystal blade along +Y with a diamond cross-section, tapering to a point; hook bends the tip
    sideways (+X) like the curved wings of a star emblem."""
    seg = int(seg)
    v, f = [], []
    for cx, y, w in _blade_profile(hook, seg):
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


def blade_edge(hook=0.0, thick=0.18, seg=24, r=0.012):
    """The glowing outline of blade(hook, thick): both cutting edges, plus a groove down each face."""
    seg = int(seg)
    prof = _blade_profile(hook, seg)
    body = [(cx + s * w * 0.5, y, z * thick * w) for cx, y, w in prof for s, z in ((1, 0), (-1, 0), (0, 1), (0, -1))]
    right = [(cx + w * 0.5, y, 0) for cx, y, w in prof]
    left = [(cx - w * 0.5, y, 0) for cx, y, w in prof]
    outline = left[::-1] + right[1:]
    grooves = [[(cx, y, z * (thick * w + r * 0.5)) for cx, y, w in prof[2:int(seg * 0.8)]] for z in (1, -1)]
    v, f = _merge([_tube(outline, r, 6)] + [_tube(g, r * 0.6, 5) for g in grooves])
    return _fit(v, body), f


KINDS = {"sphere": sphere, "globe": globe, "torus": torus, "crystal": crystal, "blade": blade, "blade_edge": blade_edge,
         "cube": cube, "frame": frame, "shard": shard}


def glb_mesh(path) -> tuple[list, list]:
    """Every triangle in a .glb (node transforms applied), Y up as in Roblox."""
    import json
    import struct
    import numpy as np
    data = Path(path).read_bytes()
    n = struct.unpack_from("<I", data, 12)[0]
    g = json.loads(data[20:20 + n])
    bin_ = data[20 + n + 8:]
    size = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
    dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}

    def acc(i):
        a = g["accessors"][i]
        bv = g["bufferViews"][a["bufferView"]]
        k = size[a["type"]]
        arr = np.frombuffer(bin_, dt[a["componentType"]], a["count"] * k, bv.get("byteOffset", 0) + a.get("byteOffset", 0))
        return arr.reshape(-1, k) if k > 1 else arr

    def local(node):
        if "matrix" in node:
            return np.array(node["matrix"], float).reshape(4, 4).T
        m = np.eye(4)
        x, y, z, w = node.get("rotation", [0, 0, 0, 1])
        m[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
        m[:3, :3] *= node.get("scale", [1, 1, 1])
        m[:3, 3] = node.get("translation", [0, 0, 0])
        return m
    verts, tris = [], []

    def walk(i, parent):
        node = g["nodes"][i]
        m = parent @ local(node)
        for prim in g["meshes"][node["mesh"]]["primitives"] if "mesh" in node else []:
            pos = acc(prim["attributes"]["POSITION"]).astype(float)
            pos = (np.c_[pos, np.ones(len(pos))] @ m.T)[:, :3]
            idx = acc(prim["indices"]).reshape(-1, 3) if "indices" in prim else np.arange(len(pos)).reshape(-1, 3)
            tris.extend(map(tuple, (idx + len(verts)).tolist()))
            verts.extend(map(tuple, pos.tolist()))
        for c in node.get("children", []):
            walk(c, m)
    for i in g["scenes"][g.get("scene", 0)]["nodes"]:
        walk(i, np.eye(4))
    return verts, tris


def asset_mesh(name: str):
    """An asset's exported model (assets/<name>/export/<name>.glb), fitted to the unit box."""
    import os
    f = Path(os.environ.get("ASSET_AGENT_HOME", "assets")) / name / "export" / f"{name}.glb"
    if not f.exists():
        raise ValueError(f"no exported model for asset {name!r} at {f}")
    v, t = glb_mesh(f)
    return _fit(v), t


def build(spec: str):
    """'mesh://crystal?sides=7&seed=2' (or 'crystal?...') -> (vertices, triangles)."""
    spec = spec.removeprefix("mesh://")
    if spec.startswith("asset/"):
        return asset_mesh(spec[6:])
    kind, _, query = spec.partition("?")
    if kind not in KINDS:
        raise ValueError(f"unknown mesh kind {kind!r}: one of {', '.join(KINDS)}")
    return KINDS[kind](**{k: float(v) for k, v in parse_qsl(query)})


def mesh_data(spec: str) -> dict:
    """A mesh for transport to Studio: {v: [x,y,z,...], f: [a,b,c,...] (0-based), uv: [u,v,...] if mapped}."""
    v, f, *uv = build(spec)
    out = {"v": [round(c, ROUND) for p in v for c in p], "f": [i for t in f for i in t]}
    if uv:
        out["uv"] = [round(c, ROUND) for p in uv[0] for c in p]
    return out
