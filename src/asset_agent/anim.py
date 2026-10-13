"""Animation layer: R15 KeyframeSequences from parameters, so "faster, bigger arm swing" is a revision.

An animation is stored as params only (assets/<name>/anim.json): a preset from library/anim/presets.json
plus knobs and per-joint track overrides. Everything else (keyframes, the .rbxmx export, the filmstrip
preview, the Studio script) is generated from those params.

Tracks: {Joint: {channel: spec}}. Channels rx, ry, rz are degrees (Roblox axes: rx+ swings a limb
forward, a knee bends with rx-, an elbow with rx+, rz+ lifts a right arm sideways); x, y, z are studs
(usually LowerTorso: y is bounce). spec is
    number                      constant
    {o, a, p, h}                wave: o + a*cos(2*pi*h*(u - p)), peaks at phase p (0-1 of the cycle)
    [wave, wave, ...]           summed
    {keys: [[u, v, ease]..]}    keys at normalised time u, joined by a spline that keeps moving through
                                them (default) or eased into a key: smooth | linear | in | out |
                                overshoot | snap
IK (Hand and Foot): {"ik": [x, y, z] or {keys: [[u, [x, y, z], ease]..]}, "pole": [x, y, z]} puts the wrist or
ankle at that point (studs, character space: feet on y=0, +X right, -Z forward) and solves the limb; pole is
the way the elbow/knee points. With ik a Foot is set in the world: rx = pitch to the floor (0 = flat,
- = heel up), ry = which way the toes point; it stays flat however the leg moves.
overlap: each joint up the body runs a little behind the one below it (hips lead, chest, shoulders, arms,
hands, head follow), which is what makes motion flow; the overlap knob scales it.
Preset: {use, tags, length (s), loop, priority, mirror: opposite|same|none, base, params, tracks}.
mirror fills each Left joint from its Right one: opposite = half a cycle later (gaits), same = in step.
"""
import copy
import json
import math
import os
from pathlib import Path

PRIORITY = {"Idle": 0, "Movement": 1, "Action": 2, "Action2": 3, "Action3": 4, "Action4": 5, "Core": 1000}
CHANNELS = ("x", "y", "z", "rx", "ry", "rz")
IK_CHANNELS = ("ik", "pole")
# chain depth above the pelvis: how many overlap steps a joint trails the hips by (legs stay exact for contact)
DEPTH = {"UpperTorso": 1, "Head": 3, "UpperArm": 2, "LowerArm": 3, "Hand": 4}
OVERLAP_S = 0.025
FPS = 30
PLANT_EASE_S = 0.1  # foot contact fixes ease in and out over this long either side

# Default R15 in rest pose (measured in a Studio workspace), Roblox space (X right, Y up, faces -Z), feet on y=0.
# All joints have identity rotations, so a Pose CFrame is just the joint's rotation and offset.
# part: (parent, joint pivot, box centre, box size)
_RIGHT = {
    "RightUpperArm": ("UpperTorso", (0.972, 4.037, 0), (1.472, 3.618, 0), (1, 1.24, 1)),
    "RightLowerArm": ("RightUpperArm", (1.472, 3.263, 0), (1.472, 2.988, 0), (1, 1.12, 1)),
    "RightHand": ("RightLowerArm", (1.472, 2.456, 0), (1.472, 2.325, 0), (0.98, 0.32, 1.03)),
    "RightUpperLeg": ("LowerTorso", (0.498, 2.19, 0), (0.498, 1.719, 0), (0.99, 1.36, 0.97)),
    "RightLowerLeg": ("RightUpperLeg", (0.498, 1.269, 0), (0.498, 0.856, 0), (0.99, 1.3, 0.97)),
    "RightFoot": ("RightLowerLeg", (0.498, 0.26, 0), (0.498, 0.154, 0), (1.01, 0.31, 1.0)),
}
RIG = {
    "LowerTorso": ("HumanoidRootPart", (0, 2.19, 0), (0, 2.39, 0), (1.99, 0.4, 1)),
    "UpperTorso": ("LowerTorso", (0, 2.591, 0), (0, 3.44, 0), (1.94, 1.7, 1)),
    "Head": ("UpperTorso", (0, 4.289, 0), (0, 4.864, 0), (1.16, 1.18, 1.16)),
}
for _n, (_par, _pv, _c, _s) in _RIGHT.items():
    RIG[_n] = (_par, _pv, _c, _s)
    RIG["Left" + _n[5:]] = (_par.replace("Right", "Left"), (-_pv[0], *_pv[1:]), (-_c[0], *_c[1:]), _s)
JOINTS = list(RIG)
GROUPS = {"arms": ("UpperArm", "LowerArm", "Hand"), "legs": ("UpperLeg", "LowerLeg", "Foot"),
          "torso": ("LowerTorso", "UpperTorso"), "head": ("Head",)}
KNOBS = {"overlap": 1.0, "speed": 1.0, "amount": 1.0, "arms": 1.0, "legs": 1.0, "torso": 1.0, "head": 1.0, "bounce": 1.0, "lean": 0.0}


def library_path() -> Path:
    return Path(os.environ.get("ASSET_AGENT_ANIM") or Path(__file__).parents[2] / "library" / "anim" / "presets.json")


def presets() -> dict:
    return {k: v for k, v in json.loads(library_path().read_text()).items() if not k.startswith("_")}


def catalog() -> str:
    out = []
    for k, v in presets().items():
        d = resolve({"preset": k})
        out.append(f"{k}: {v.get('use', '')} ({'loop' if d['loop'] else 'one-shot'} {d['length']:.2g}s)")
    return "\n".join(out)


# ---------------------------------------------------------------- resolving a spec into tracks

def _merge_tracks(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for joint, chans in (over or {}).items():
        if chans is None:
            out.pop(joint, None)
            continue
        out.setdefault(joint, {})
        for ch, v in chans.items():
            if v is None:
                out[joint].pop(ch, None)
            else:
                out[joint][ch] = v
    return out


def _flip_vec(spec, shift: float = 0.0):
    """An ik/pole spec mirrored onto the other side: x negated."""
    if isinstance(spec, list):
        return [-spec[0], *spec[1:]]
    return {**spec, "keys": [[k[0], [-k[1][0], *k[1][1:]], *k[2:]] for k in spec["keys"]], "shift": spec.get("shift", 0) + shift}


def _flip(spec, sign: float, shift: float):
    """A channel spec mirrored onto the other side: values times sign, waves shifted by `shift`."""
    if isinstance(spec, (int, float)):
        return spec * sign
    if isinstance(spec, list):
        return [_flip(s, sign, shift) for s in spec]
    if "keys" in spec:
        return {**spec, "keys": [[k[0], k[1] * sign, *k[2:]] for k in spec["keys"]], "shift": spec.get("shift", 0) + shift}
    return {**spec, "o": spec.get("o", 0) * sign, "a": spec.get("a", 0) * sign, "p": spec.get("p", 0) + shift}


def resolve(spec: dict) -> dict:
    """{preset, params, tracks} -> a full definition {length, loop, priority, tracks, params}."""
    lib = presets()
    name = spec.get("preset")
    chain, d = [], {}
    while name:
        if name not in lib:
            raise KeyError(f"no animation preset {name!r}; have: {', '.join(lib)}")
        chain.append(lib[name])
        name = lib[name].get("base")
    for p in reversed(chain):
        d = {**d, **{k: v for k, v in p.items() if k not in ("tracks", "params")},
             "tracks": _merge_tracks(d.get("tracks", {}), p.get("tracks", {})),
             "params": {**d.get("params", {}), **p.get("params", {})}}
    d.setdefault("tracks", {})
    params = {**KNOBS, **d.get("params", {}), **(spec.get("params") or {})}
    for k in ("length", "loop", "priority"):
        if k in params:
            d[k] = params.pop(k)
    d["tracks"] = _merge_tracks(d["tracks"], spec.get("tracks") or {})
    bad = [j for j in d["tracks"] if j not in RIG]
    if bad:
        raise KeyError(f"unknown joint(s) {', '.join(bad)}; joints: {', '.join(JOINTS)}")
    bad = [f"{j}.{c}" for j, ch in d["tracks"].items() for c in ch
           if c not in CHANNELS and not (c in IK_CHANNELS and j.endswith(("Hand", "Foot")))]
    if bad:
        raise KeyError(f"unknown channel(s) {', '.join(bad)}; channels: {', '.join(CHANNELS)} (+ ik, pole on hands/feet)")
    mirror = d.get("mirror", "none")
    if mirror in ("opposite", "same"):
        shift = 0.5 if mirror == "opposite" else 0.0
        for j in [j for j in d["tracks"] if j.startswith("Right")]:
            left = "Left" + j[5:]
            if left not in d["tracks"]:
                d["tracks"][left] = {c: _flip_vec(s, shift) if c in IK_CHANNELS else
                                     _flip(s, -1 if c in ("ry", "rz", "x") else 1, shift)
                                     for c, s in d["tracks"][j].items()}
    d["length"] = float(d.get("length", 1.0)) / max(float(params["speed"]), 0.05)
    d["loop"] = bool(d.get("loop", True))
    d["priority"] = d.get("priority", "Movement" if d["loop"] else "Action")
    d["params"] = params
    return d


# ---------------------------------------------------------------- evaluating tracks

def _ease(kind: str, t: float) -> float:
    if kind == "linear":
        return t
    if kind == "in":
        return t * t
    if kind == "out":
        return 1 - (1 - t) ** 2
    if kind == "snap":
        return 0.0 if t < 1 else 1.0
    if kind == "overshoot":  # out-back: shoots past the key then settles
        c = 1.70158
        return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2
    return t * t * (3 - 2 * t)


def _value(spec, u: float, loop: bool) -> tuple[float, float]:
    """(base, motion) of a channel at normalised time u: motion is what the group knobs scale."""
    if isinstance(spec, (int, float)):
        return float(spec), 0.0
    if isinstance(spec, list):
        parts = [_value(s, u, loop) for s in spec]
        return parts[0][0], sum(p[0] for p in parts[1:]) + sum(p[1] for p in parts)
    if "keys" in spec:
        keys = sorted(spec["keys"], key=lambda k: k[0])
        rest = keys[0][1]
        if spec.get("shift") and loop:  # a mirrored gait: the same keys half a cycle later
            u = (u - spec["shift"]) % 1.0
        return rest, _keys(keys, u, loop, spec.get("ease", "spline")) - rest
    return float(spec.get("o", 0)), spec.get("a", 0) * math.cos(2 * math.pi * spec.get("h", 1) * (u - spec.get("p", 0)))


def _keys(keys, u: float, loop: bool, default: str = "spline", c: int | None = None) -> float:
    """Value of sorted keys [[u, v, ease]..] at u (component c of vector values). Spline segments are
    cubic Hermite with Catmull-Rom tangents, so motion carries through a key instead of stopping on it;
    the ends of a one-shot (and keys with an explicit ease) settle."""
    def val(k):
        return k[1] if c is None else k[1][c]
    if u <= keys[0][0]:
        return val(keys[0])
    if u >= keys[-1][0]:
        return val(keys[-1])
    i = next(i for i in range(1, len(keys)) if u <= keys[i][0])
    a, b = keys[i - 1], keys[i]
    span = b[0] - a[0]
    t = (u - a[0]) / span if span > 0 else 1.0
    ease = b[2] if len(b) > 2 else default
    if ease != "spline":
        return val(a) + (val(b) - val(a)) * _ease(ease, t)

    def tangent(j):
        if 0 < j < len(keys) - 1:
            p, n = keys[j - 1], keys[j + 1]
            return (val(n) - val(p)) / ((n[0] - p[0]) or 1)
        if loop and len(keys) > 2:  # wrap: u=0 and u=1 are the same moment
            p, n = keys[-2], keys[1]
            return (val(n) - val(p)) / ((n[0] + 1 - p[0]) or 1)
        return 0.0
    m0, m1 = tangent(i - 1) * span, tangent(i) * span
    t2, t3 = t * t, t * t * t
    return (2 * t3 - 3 * t2 + 1) * val(a) + (t3 - 2 * t2 + t) * m0 + (-2 * t3 + 3 * t2) * val(b) + (t3 - t2) * m1


def _vec(spec, u: float, loop: bool) -> tuple:
    if isinstance(spec, list):
        return tuple(float(x) for x in spec)
    keys = sorted(spec["keys"], key=lambda k: k[0])
    if spec.get("shift") and loop:
        u = (u - spec["shift"]) % 1.0
    return tuple(_keys(keys, u, loop, spec.get("ease", "spline"), c) for c in range(3))


def _lag(joint: str, d: dict) -> float:
    """How far (normalised time) a joint trails the hips."""
    n = next((v for k, v in DEPTH.items() if joint.endswith(k)), 0)
    return n * OVERLAP_S * d["params"]["overlap"] / d["length"]


def _group_scale(joint: str, ch: str, params: dict) -> float:
    k = params["amount"]
    if joint == "LowerTorso" and ch in ("x", "y", "z"):
        return k * params["bounce"]
    for g, names in GROUPS.items():
        if any(joint.endswith(n) for n in names):
            return k * params[g]
    return k


def pose_at(d: dict, u: float, ground: bool | str = True) -> dict:
    """{joint: [x, y, z, rx, ry, rz]} (studs, degrees) at normalised time u. ground: feet are planted
    with IK, then the body lifts if anything still dips below the floor (a sinking foot is the
    commonest animation artefact); "plant" = IK only, False = raw tracks."""
    out, iks = _raw(d, u)
    if ground and d.get("ground", True):
        # how much each foot must roll and lift to stay out of the floor, eased in and out over
        # neighbouring frames: a foot leaves the floor in a frame or two, so per-frame fixes would pop
        n = max(1, round(PLANT_EASE_S * FPS))
        du = 1.0 / (FPS * d["length"])
        for side in ("Right", "Left"):
            if side + "Foot" in iks:  # an IK foot is already where the author put it
                continue
            toe, heel, lift = 0.0, 0.0, 0.0  # rolling onto the heel and onto the toes ease separately,
            for k in range(-n, n + 1):     # so the hand-over from heel strike to toe-off blends
                uk = u + k * du
                uk = uk % 1.0 if d["loop"] else min(1.0, max(0.0, uk))
                r, l = plant_need(out if k == 0 else _raw(d, uk)[0], side)
                w = 1 - abs(k) / (n + 1)
                toe, heel = max(toe, r * w), min(heel, r * w)
                lift = max(lift, l * w)
            plant_apply(out, side, toe + heel, lift)
        low = lowest(out)
        if low < 0 and ground != "plant":
            out.setdefault("LowerTorso", [0.0] * 6)[1] -= low
    return out


def _raw(d: dict, u: float) -> tuple[dict, dict]:
    """The pose from the tracks alone (with overlap, lean and IK), before the feet are kept out of the floor."""
    out, iks = {}, {}
    for joint, chans in d["tracks"].items():
        vals = [0.0] * 6
        uj = u - _lag(joint, d)
        uj = uj % 1.0 if d["loop"] else max(0.0, uj)
        for ch, spec in chans.items():
            if ch in IK_CHANNELS:
                continue
            base, motion = _value(spec, uj, d["loop"])
            vals[CHANNELS.index(ch)] = base + motion * _group_scale(joint, ch, d["params"])
        out[joint] = vals
        if "ik" in chans:
            iks[joint] = (_vec(chans["ik"], u, d["loop"]), _vec(chans["pole"], u, d["loop"]) if "pole" in chans else None)  # targets are hits: no overlap
    if d["params"]["lean"]:
        out.setdefault("UpperTorso", [0.0] * 6)[3] -= d["params"]["lean"]
    for joint in sorted(iks, key=lambda j: j.endswith("Hand")):  # legs first, then arms on the posed torso
        reach(out, joint, *iks[joint])
    return out, iks


ANKLE_H = RIG["RightFoot"][1][1]  # ankle height with the sole flat on the floor
THIGH = RIG["RightUpperLeg"][1][1] - RIG["RightLowerLeg"][1][1]
SHIN = RIG["RightLowerLeg"][1][1] - ANKLE_H


def _foot_low(world, side):
    return min(p[1] for p in corners(side + "Foot", world[side + "Foot"]))


def plant_need(pose: dict, side: str) -> tuple[float, float]:
    """(roll, lift) that keep one foot out of the floor: first roll the foot toward flat (degrees), as a
    foot rolls onto or off its toes, by the least that clears it; if even flat it's under, lift the
    ankle (studs). Both are zero while the foot is clear, so contact never pops."""
    world = solve(pose)
    if _foot_low(world, side) >= -1e-4:
        return 0.0, 0.0
    trial = {k: list(v) for k, v in pose.items()}
    foot = trial.setdefault(side + "Foot", [0.0] * 6)
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, -world[side + "Foot"][0][1][2]))))
    base = foot[3]
    foot[3] = base - pitch
    under = -_foot_low(solve(trial), side)
    if under <= 1e-4:
        lo, hi = 0.0, 1.0
        for _ in range(16):
            mid = (lo + hi) / 2
            foot[3] = base - pitch * mid
            if _foot_low(solve(trial), side) >= -1e-4:
                hi = mid
            else:
                lo = mid
        return -pitch * hi, 0.0
    return -pitch, under + 0.002


def plant_apply(pose: dict, side: str, roll: float, lift: float):
    """Roll the foot, then lift the ankle with two-bone IK in the leg's swing plane, re-solving the hip
    and knee (rx only; the leg's twist and spread are kept) while the foot keeps its angle."""
    if not roll and not lift:
        return
    hip, knee, foot = (pose.setdefault(side + n, [0.0] * 6) for n in ("UpperLeg", "LowerLeg", "Foot"))
    foot[3] += roll
    if lift <= 0:
        return
    world = solve(pose)
    ankle = _mv(world[side + "LowerLeg"][0], RIG[side + "Foot"][1])
    ankle = tuple(a + b for a, b in zip(ankle, world[side + "LowerLeg"][1]))
    lr, lt = world["LowerTorso"]
    h = tuple(a + b for a, b in zip(_mv(lr, RIG[side + "UpperLeg"][1]), lt))

    def planar(target):
        """(hip, knee) rx in degrees that put the ankle at target, in the leg's swing plane."""
        w = tuple(target[i] - h[i] for i in range(3))
        v = tuple(sum(lr[k][i] * w[k] for k in range(3)) for i in range(3))  # into the pelvis frame
        dist = max(min(math.hypot(v[1], v[2]), THIGH + SHIN - 1e-4), abs(THIGH - SHIN) + 1e-4)
        gamma = math.acos(max(-1.0, min(1.0, (THIGH ** 2 + SHIN ** 2 - dist ** 2) / (2 * THIGH * SHIN))))
        alpha = math.acos(max(-1.0, min(1.0, (THIGH ** 2 + dist ** 2 - SHIN ** 2) / (2 * THIGH * dist))))
        return math.degrees(math.atan2(-v[2], -v[1]) + alpha), -math.degrees(math.pi - gamma)
    # apply the change between solving for where the ankle is and where it must go, so a lift of zero
    # changes nothing (the plane solve ignores the leg's twist and spread, so it isn't exact on its own)
    h0, k0 = planar(ankle)
    h1, k1 = planar((ankle[0], ankle[1] + lift, ankle[2]))
    hip[3] += h1 - h0
    knee[3] += k1 - k0
    foot[3] -= (h1 - h0) + (k1 - k0)  # keep the foot's angle to the ground while the leg re-bends


def _bend_len(u1, u2, e):
    v = tuple(a + b for a, b in zip(u1, _mv(_rot(math.radians(e), 0, 0), u2)))
    return v, math.sqrt(sum(x * x for x in v))


def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return tuple(x / n for x in v) if n > 1e-9 else None


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _euler(r) -> list[float]:
    """Degrees (rx, ry, rz) with Rx*Ry*Rz = r, picking the smaller of the two equivalent solutions."""
    ry = math.asin(max(-1.0, min(1.0, r[0][2])))
    rx = math.atan2(-r[1][2], r[2][2])
    rz = math.atan2(-r[0][1], r[0][0])
    alt = (rx + math.pi, math.pi - ry, rz + math.pi)
    alt = tuple((a + math.pi) % (2 * math.pi) - math.pi for a in alt)
    best = min(((rx, ry, rz), alt), key=lambda e: sum(x * x for x in e))
    return [math.degrees(x) for x in best]


def reach(pose: dict, end: str, target, pole=None, _lifted=False):
    """Two-bone IK: put the wrist (Hand) or ankle (Foot) pivot at `target` (character space) with the
    elbow/knee pointing along `pole`; sets the upper limb's rotation and the lower limb's bend."""
    leg = end.endswith("Foot")
    side = "Right" if end.startswith("Right") else "Left"
    upper, lower = (side + "UpperLeg", side + "LowerLeg") if leg else (side + "UpperArm", side + "LowerArm")
    sgn = 1 if side == "Right" else -1
    pole = pole or ((0.15 * sgn, 0.0, -1.0) if leg else (0.35 * sgn, -1.0, 0.45))
    world = solve(pose)
    pr, pt = world[RIG[upper][0]]
    p_up, p_lo, p_end = RIG[upper][1], RIG[lower][1], RIG[end][1]
    off = pose.get(upper, [0.0] * 6)[:3]
    shoulder = tuple(_mv(pr, tuple(p_up[i] + off[i] for i in range(3)))[i] + pt[i] for i in range(3))
    w = tuple(sum(pr[k][i] * (target[k] - shoulder[k]) for k in range(3)) for i in range(3))  # parent frame
    u1 = tuple(p_lo[i] - p_up[i] for i in range(3))
    u2 = tuple(p_end[i] - p_lo[i] for i in range(3))
    lo_e, hi_e = 0.0, -150.0 if leg else 150.0  # |u1 + Rx(e) u2| shrinks as the joint bends
    dist = math.sqrt(sum(x * x for x in w))
    full = _bend_len(u1, u2, lo_e)[1]
    soft = 0.03 * full  # soft IK: ease into full reach, or the elbow/knee snaps straight in one frame
    if dist > full - soft:
        dist = full - soft * math.exp(-(dist - (full - soft)) / soft)
    dist = max(dist, _bend_len(u1, u2, hi_e)[1])
    for _ in range(40):
        mid = (lo_e + hi_e) / 2
        if _bend_len(u1, u2, mid)[1] > dist:
            lo_e = mid
        else:
            hi_e = mid
    e = (lo_e + hi_e) / 2
    v, _ = _bend_len(u1, u2, e)
    a1, b1 = _unit(v), _unit(w)
    if not b1:
        return
    pl = tuple(sum(pr[k][i] * pole[k] for k in range(3)) for i in range(3))

    def perp(x, axis):
        q = _unit(tuple(x[i] - sum(x[k] * axis[k] for k in range(3)) * axis[i] for i in range(3)))
        return q or _unit(_cross(axis, (0, 0, 1))) or _unit(_cross(axis, (1, 0, 0)))
    # which way the knee juts in the leg's own frame (forward, -Z): taken from the hinge, not the bent
    # shape, since a straight leg's shape doesn't say and its knee would flip from frame to frame
    a2 = perp((0.0, 0.0, -1.0) if leg else u1, a1)  # an arm's elbow sits off the shoulder line: use it
    b2 = perp(pl, b1)
    a3, b3 = _cross(a1, a2), _cross(b1, b2)
    r = tuple(tuple(b1[i] * a1[j] + b2[i] * a2[j] + b3[i] * a3[j] for j in range(3)) for i in range(3))
    pose.setdefault(upper, [0.0] * 6)[3:6] = _euler(r)
    pose.setdefault(lower, [0.0] * 6)[3:6] = [e, 0.0, 0.0]
    if leg:  # with ik the foot is set in the world: rx = pitch to the floor, ry = which way it points
        foot = pose.setdefault(end, [0.0] * 6)
        want = foot[3:6]
        shin = solve(pose)[lower][0]
        world_rot = _mm(_rot(0, math.radians(want[1]), 0), _rot(math.radians(want[0]), 0, 0))
        local = tuple(tuple(sum(shin[k][i] * world_rot[k][j] for k in range(3)) for j in range(3)) for i in range(3))
        foot[3:6] = _euler(local)
        if not _lifted:  # a pitched foot rises until its heel or toe just touches the floor
            pen = -_foot_low(solve(pose), side)
            if pen > 1e-4:
                foot[3:6] = want
                reach(pose, end, (target[0], target[1] + pen, target[2]), pole, _lifted=True)


def _shin_box(side):
    """The shin only above the ankle: the rest of the box sits inside the foot in Roblox."""
    _, ankle, c, s = RIG[side + "LowerLeg"]
    top = c[1] + s[1] / 2
    return (c[0], (top + ankle[1]) / 2, c[2]), (s[0], top - ankle[1], s[2])


def lowest(pose: dict) -> float:
    world = solve(pose)
    return min(p[1] for n in JOINTS for p in corners(
        n, world[n], _shin_box(n[:-8]) if n.endswith("LowerLeg") else None))


def samples(d: dict, fps: int = FPS) -> list[tuple[float, dict]]:
    n = max(4, round(d["length"] * fps))
    return [(d["length"] * i / n, pose_at(d, i / n)) for i in range(n + 1)]


# ---------------------------------------------------------------- forward kinematics on the R15 rig

def _rot(rx, ry, rz):
    """CFrame.Angles(rx, ry, rz) = Rx * Ry * Rz (radians) as a 3x3 row-major matrix."""
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    X = ((1, 0, 0), (0, cx, -sx), (0, sx, cx))
    Y = ((cy, 0, sy), (0, 1, 0), (-sy, 0, cy))
    Z = ((cz, -sz, 0), (sz, cz, 0), (0, 0, 1))
    return _mm(_mm(X, Y), Z)


def _mm(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def _mv(m, v):
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def solve(pose: dict) -> dict:
    """World transform (R, t) of every part: world point = R * rest point + t."""
    world = {"HumanoidRootPart": (((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.0, 0.0, 0.0))}

    def get(name):
        if name in world:
            return world[name]
        parent, pivot, _, _ = RIG[name]
        pr, pt = get(parent)
        x, y, z, rx, ry, rz = pose.get(name, (0,) * 6)
        r = _rot(math.radians(rx), math.radians(ry), math.radians(rz))
        # local: p -> pivot + (x,y,z) + r * (p - pivot), then the parent's transform
        lt = tuple(pivot[i] + (x, y, z)[i] - _mv(r, pivot)[i] for i in range(3))
        world[name] = (_mm(pr, r), tuple(_mv(pr, lt)[i] + pt[i] for i in range(3)))
        return world[name]
    for j in JOINTS:
        get(j)
    return world


def corners(name: str, tf, box=None) -> list[tuple]:
    c, s = box or RIG[name][2:]
    r, t = tf
    out = []
    for dx in (-0.5, 0.5):
        for dy in (-0.5, 0.5):
            for dz in (-0.5, 0.5):
                p = (c[0] + dx * s[0], c[1] + dy * s[1], c[2] + dz * s[2])
                out.append(tuple(a + b for a, b in zip(_mv(r, p), t)))
    return out


# ---------------------------------------------------------------- checks

# fastest a part really turns (deg/s): past this it reads as a glitch. A boxer's arm peaks near 2500,
# a sprinter's knee near 1500; heads and torsos are far slower.
POP_DEG_S = {"Head": 900, "UpperTorso": 900, "LowerTorso": 900, "Arm": 4000, "Hand": 4000, "Leg": 2500, "Foot": 2500}
LIMITS = {"LowerLeg": ("rx", -160, 5, "knee bends backwards"), "LowerArm": ("rx", -5, 165, "elbow bends backwards")}


def check(d: dict, frames=None) -> tuple[dict, list[str]]:
    """Stats {low, high} (lowest/highest point in studs) and warnings a viewer would notice."""
    frames = frames or samples(d)
    warns, low, high = [], 1e9, -1e9
    hit = set()
    lift = max(0.0, -min(lowest(pose_at(d, i / 24, ground="plant")) for i in range(25))) if d.get("ground", True) else 0
    if lift > 0.15:
        warns.append(f"body lifted up to {lift:.1f} studs to keep limbs above the floor (straighten the legs if that floats)")
    for t, pose in frames:
        world = solve(pose)
        low = min(low, lowest(pose))
        high = max(high, max(max(p[1] for p in corners(n, world[n])) for n in JOINTS))
        for j, vals in pose.items():
            for suffix, (ch, lo, hi, msg) in LIMITS.items():
                v = vals[CHANNELS.index(ch)]
                if j.endswith(suffix) and not lo <= v <= hi and (j, msg) not in hit:
                    hit.add((j, msg))
                    warns.append(f"{j} {msg} ({v:.0f} deg at {t:.2f}s)")
    for j in JOINTS:  # pops: a joint jumping in one frame, not a fast move that builds up and slows down
        steps = []
        for (t0, a), (t1, b) in zip(frames, frames[1:]):
            ra, rb = (_rot(*(math.radians(x) for x in p.get(j, (0,) * 6)[3:])) for p in (a, b))
            tr = sum(ra[k][i] * rb[k][i] for i in range(3) for k in range(3))
            steps.append((math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1) / 2)))), t0, t1))
        for i, (step, t0, t1) in enumerate(steps):
            near = max([steps[k][0] for k in (i - 1, i + 1) if 0 <= k < len(steps)] or [0])
            limit = next(v for k, v in POP_DEG_S.items() if k in j)
            if step / max(t1 - t0, 1e-6) > limit or (step > 30 and step > 2.5 * near):
                warns.append(f"{j} pops {step:.0f} deg between {t0:.2f}s and {t1:.2f}s")
                break
    if d["loop"]:
        for j, chans in d["tracks"].items():
            for ch, spec in chans.items():
                if isinstance(spec, dict) and "keys" in spec:
                    ks = sorted(spec["keys"], key=lambda k: k[0])
                    if abs(ks[0][1] - ks[-1][1]) > 1e-6 or ks[0][0] > 0 or ks[-1][0] < 1:
                        warns.append(f"{j}.{ch} keys don't meet at u=0 and u=1: pops when it loops")
    return {"low": low, "high": high}, warns


# ---------------------------------------------------------------- outputs

def _cf(vals) -> tuple:
    x, y, z, rx, ry, rz = vals
    r = _rot(math.radians(rx), math.radians(ry), math.radians(rz))
    return (x, y, z, *[r[i][j] for i in range(3) for j in range(3)])


def rbxmx(name: str, d: dict, frames=None) -> str:
    """The animation as a KeyframeSequence model file (Studio: right-click > Insert from File)."""
    frames = frames or samples(d)
    ref = iter(range(1, 10 ** 9))
    children = {}
    for j in JOINTS:
        children.setdefault(RIG[j][0], []).append(j)
    labels = ("X", "Y", "Z", "R00", "R01", "R02", "R10", "R11", "R12", "R20", "R21", "R22")

    def pose_xml(joint, pose):
        cf = "".join(f"<{k}>{v:.6g}</{k}>" for k, v in zip(labels, _cf(pose.get(joint, (0,) * 6))))
        kids = "".join(pose_xml(c, pose) for c in children.get(joint, []))
        w = 0 if joint == "HumanoidRootPart" else 1
        return (f'<Item class="Pose" referent="RBX{next(ref)}"><Properties><string name="Name">{joint}</string>'
                f'<CoordinateFrame name="CFrame">{cf}</CoordinateFrame><token name="EasingDirection">0</token>'
                f'<token name="EasingStyle">0</token><float name="Weight">{w}</float></Properties>{kids}</Item>')
    kfs = "".join(f'<Item class="Keyframe" referent="RBX{next(ref)}"><Properties><string name="Name">Keyframe</string>'
                  f'<float name="Time">{t:.4f}</float></Properties>{pose_xml("HumanoidRootPart", pose)}</Item>'
                  for t, pose in frames)
    return ('<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">'
            f'<Item class="KeyframeSequence" referent="RBX0"><Properties><string name="Name">{name}</string>'
            f'<bool name="Loop">{"true" if d["loop"] else "false"}</bool>'
            f'<token name="Priority">{PRIORITY.get(d["priority"], 1)}</token></Properties>{kfs}</Item></roblox>')


def studio_script(name: str, d: dict, frames=None) -> str:
    """Luau that builds the KeyframeSequence in ServerStorage.AssetAgentAnimations and plays it on a test
    dummy (workspace.AnimTest_<name>), live in Edit mode and again in Play mode."""
    frames = frames or samples(d)
    data = json.dumps([[round(t, 4), {j: [round(v, 4) for v in p] for j, p in pose.items()}] for t, pose in frames],
                      separators=(",", ":"))
    return f"""local HS=game:GetService('HttpService') local NAME='{name}'
local F=HS:JSONDecode([==[{data}]==])
local TREE=HS:JSONDecode([==[{json.dumps({j: RIG[j][0] for j in JOINTS})}]==])
local folder=game.ServerStorage:FindFirstChild('AssetAgentAnimations') or Instance.new('Folder')
folder.Name='AssetAgentAnimations' folder.Parent=game.ServerStorage
local old=folder:FindFirstChild(NAME) if old then old:Destroy() end
local kfs=Instance.new('KeyframeSequence') kfs.Name=NAME kfs.Loop={'true' if d['loop'] else 'false'}
kfs.Priority=Enum.AnimationPriority.{d['priority']}
for _,f in F do
 local kf=Instance.new('Keyframe') kf.Time=f[1]
 local poses={{}}
 local root=Instance.new('Pose') root.Name='HumanoidRootPart' root.Weight=0 root.Parent=kf poses.HumanoidRootPart=root
 local function get(j)
  if poses[j] then return poses[j] end
  local p=Instance.new('Pose') p.Name=j p.EasingStyle=Enum.PoseEasingStyle.Linear
  local v=f[2][j] or {{0,0,0,0,0,0}}
  p.CFrame=CFrame.new(v[1],v[2],v[3])*CFrame.Angles(math.rad(v[4]),math.rad(v[5]),math.rad(v[6]))
  p.Parent=get(TREE[j]) poses[j]=p return p
 end
 for j in TREE do get(j) end
 kf.Parent=kfs
end
kfs.Parent=folder
local dummy=workspace:FindFirstChild('AnimTest_'..NAME)
if not dummy then
 local hd=Instance.new('HumanoidDescription') local skin=Color3.fromRGB(245,205,150)
 hd.HeadColor,hd.LeftArmColor,hd.RightArmColor,hd.TorsoColor=skin,skin,skin,Color3.fromRGB(60,125,225)
 hd.LeftLegColor,hd.RightLegColor=Color3.fromRGB(70,72,85),Color3.fromRGB(70,72,85)
 dummy=game:GetService('Players'):CreateHumanoidModelFromDescription(hd,Enum.HumanoidRigType.R15)
 dummy.Name='AnimTest_'..NAME
 local cf=workspace.CurrentCamera.CFrame local at=cf.Position+cf.LookVector*15
 local hit=workspace:Raycast(at+Vector3.new(0,100,0),Vector3.new(0,-1000,0))
 dummy:PivotTo(CFrame.new(at.X,(hit and hit.Position.Y or 0)+dummy.Humanoid.HipHeight+dummy.HumanoidRootPart.Size.Y/2,at.Z)*CFrame.Angles(0,math.rad(cf.LookVector.X>0 and 90 or -90),0))
 dummy.Parent=workspace
end
dummy.HumanoidRootPart.Anchored=true
local s=dummy:FindFirstChild('PlayAnim') or Instance.new('Script') s.Name='PlayAnim'
s.Source="local kfs=game.ServerStorage.AssetAgentAnimations:WaitForChild('"..NAME.."') local a=Instance.new('Animation') a.AnimationId=game:GetService('KeyframeSequenceProvider'):RegisterKeyframeSequence(kfs) local an=script.Parent:WaitForChild('Humanoid'):WaitForChild('Animator') local t=an:LoadAnimation(a) t.Looped=true t:Play()"
s.Parent=dummy
-- play it now in Edit mode too: step the Animator every frame until the dummy or a rebuild replaces it
local a=Instance.new('Animation') a.AnimationId=game:GetService('KeyframeSequenceProvider'):RegisterKeyframeSequence(kfs)
local an=dummy.Humanoid:FindFirstChildOfClass('Animator') or Instance.new('Animator',dummy.Humanoid)
for _,t in an:GetPlayingAnimationTracks() do t:Stop(0) end
local tr=an:LoadAnimation(a) tr.Looped=true tr:Play(0)
_G.AssetAgentAnim=_G.AssetAgentAnim or {{}}
if _G.AssetAgentAnim[NAME] then _G.AssetAgentAnim[NAME]:Disconnect() end
_G.AssetAgentAnim[NAME]=game:GetService('RunService').Heartbeat:Connect(function(dt)
 if dummy.Parent then an:StepAnimations(dt) else _G.AssetAgentAnim[NAME]:Disconnect() end end)
return 'built '..NAME..' ('..#kfs:GetKeyframes()..' keyframes) in ServerStorage.AssetAgentAnimations, playing on workspace.'..dummy.Name"""


# ---------------------------------------------------------------- filmstrip preview

COLOURS = {"Head": (250, 205, 70), "UpperTorso": (60, 125, 225), "LowerTorso": (45, 95, 180),
           "Arm": (245, 200, 160), "Hand": (235, 185, 145), "Leg": (95, 100, 120), "Foot": (60, 60, 70)}


def _colour(name):
    for k, c in COLOURS.items():
        if k in name:
            return c
    return (200, 200, 200)


FACES = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))


def key_moments(d: dict, frames: int = 8) -> list[float]:
    """Normalised times to show: a loop evenly; a one-shot on its keys (the poses it was built from:
    contacts, impacts, extremes), thinned to `frames`, since fast hits fall between even frames."""
    if d["loop"]:
        return [i / frames for i in range(frames)]
    us = set()

    def walk(spec):
        if isinstance(spec, list):
            for x in spec:
                if isinstance(x, dict):
                    walk(x)
        elif isinstance(spec, dict) and "keys" in spec:
            us.update(round(k[0], 2) for k in spec["keys"])
    for chans in d["tracks"].values():
        for spec in chans.values():
            walk(spec)
    us = sorted(us | {0.0, 1.0})
    while len(us) > frames:  # drop the key closest to its neighbours
        i = min(range(1, len(us) - 1), key=lambda i: us[i + 1] - us[i - 1])
        us.pop(i)
    return us if len(us) >= 4 else [i / (frames - 1) for i in range(frames)]


def filmstrip(d: dict, out: Path, frames: int = 8, tile: int = 112, title: str = "",
              times: list[float] | None = None) -> Path:
    """Two rows of `frames` poses across the clip: side view (moving right) and three-quarter front."""
    from PIL import Image, ImageDraw
    views = [(1.0, 0.0, 0.0), (0.6, 0.25, -0.76)]  # direction from the character to the camera
    th = int(tile * 1.35)
    head = 16
    us = [t / d["length"] for t in times] if times else key_moments(d, frames)
    frames = len(us)
    img = Image.new("RGB", (tile * frames, th * len(views) + head), (34, 36, 42))
    dr = ImageDraw.Draw(img)
    dr.text((4, 2), title, fill=(220, 220, 220))
    ppu = th / 9.0
    light = (0.4, 0.8, -0.45)
    for f in range(frames):
        u = us[f]
        world = solve(pose_at(d, u))
        for row, c in enumerate(views):
            n = math.sqrt(sum(x * x for x in c))
            c = tuple(x / n for x in c)
            right = (c[2], 0.0, -c[0])  # (-c) x up: screen right for an upright camera
            rn = math.sqrt(right[0] ** 2 + right[2] ** 2)
            right = (right[0] / rn, 0.0, right[2] / rn)
            up = (c[1] * right[2] - c[2] * right[1], c[2] * right[0] - c[0] * right[2], c[0] * right[1] - c[1] * right[0])
            ox, oy = f * tile + tile / 2, head + row * th + th - 0.6 * ppu

            def scr(p):
                return (ox + ppu * sum(a * b for a, b in zip(p, right)), oy - ppu * sum(a * b for a, b in zip(p, up)))
            g0, g1 = scr((-3 * right[0], 0, -3 * right[2])), scr((3 * right[0], 0, 3 * right[2]))
            dr.line([g0, g1], fill=(90, 95, 105), width=1)
            polys = []
            for name in JOINTS:
                pts = corners(name, world[name])
                col = _colour(name)
                if name.startswith("Left"):
                    col = tuple(int(x * 0.78) for x in col)
                for fc in FACES:
                    q = [pts[i] for i in fc]
                    e1 = [q[1][i] - q[0][i] for i in range(3)]
                    e2 = [q[3][i] - q[0][i] for i in range(3)]
                    nrm = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
                    ctr = [sum(p[i] for p in q) / 4 for i in range(3)]
                    box_c = [sum(p[i] for p in pts) / 8 for i in range(3)]
                    if sum((ctr[i] - box_c[i]) * nrm[i] for i in range(3)) < 0:
                        nrm = tuple(-x for x in nrm)
                    if sum(nrm[i] * c[i] for i in range(3)) <= 1e-9:
                        continue
                    ln = math.sqrt(sum(x * x for x in nrm)) or 1
                    shade = 0.55 + 0.45 * max(0.0, sum(nrm[i] / ln * light[i] for i in range(3)))
                    depth = sum(ctr[i] * c[i] for i in range(3))
                    polys.append((depth, [scr(p) for p in q], tuple(min(255, int(x * shade)) for x in col)))
            for _, q, col in sorted(polys, key=lambda p: p[0]):
                dr.polygon(q, fill=col, outline=tuple(int(x * 0.6) for x in col))
        t = u * d["length"]
        dr.text((f * tile + 4, head + 2), f"{t:.2f}s", fill=(170, 170, 170))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


# ---------------------------------------------------------------- stored animations

class Animation:
    """assets/<name>/anim.json: {kind: anim, version, spec: {preset, params, tracks}, history, ratings}."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.file = self.root / "anim.json"
        self.m = json.loads(self.file.read_text()) if self.file.exists() else None

    @staticmethod
    def exists(root: Path) -> bool:
        return (Path(root) / "anim.json").exists()

    def update(self, preset=None, params=None, tracks=None, project=None) -> str:
        new = self.m is None
        if new:
            if not preset and not tracks:
                raise ValueError("a new animation needs a preset (preset='help' lists them) or tracks")
            self.m = {"kind": "anim", "version": 0, "spec": {}, "history": [], "ratings": [], "project": project}
        spec = copy.deepcopy(self.m["spec"])
        if preset:
            spec["preset"] = preset
        if params:
            spec["params"] = {k: v for k, v in {**spec.get("params", {}), **params}.items() if v is not None}
            bad = [k for k in params if k not in KNOBS and k not in ("length", "loop", "priority")]
            if bad:
                raise KeyError(f"unknown param(s) {', '.join(bad)}; params: {', '.join([*KNOBS, 'length', 'loop', 'priority'])}")
        if tracks:
            spec["tracks"] = _merge_tracks(spec.get("tracks", {}), tracks)
        what = "new" if new else ", ".join(
            [f"preset={preset}"] * bool(preset) + [f"{k}={v}" for k, v in (params or {}).items()] +
            ([f"tracks[{', '.join(tracks)}]"] if tracks else []))
        try:
            return self._commit(spec, what)
        except Exception:
            if new:
                self.m = None
            raise

    def _commit(self, spec: dict, what: str) -> str:
        d = resolve(spec)  # raises before anything is saved
        frames = samples(d)
        stats, warns = check(d, frames)
        self.m["version"] += 1
        v = self.m["version"]
        self.m["spec"] = spec
        self.m.setdefault("specs", {})[str(v)] = spec
        self.m["history"].append(f"v{v}: {what}")
        exp = self.root / "export"
        (exp / "versions").mkdir(parents=True, exist_ok=True)
        xml = rbxmx(self.root.name, d, frames)
        (exp / f"{self.root.name}.rbxmx").write_text(xml, encoding="utf-8")
        (exp / "versions" / f"v{v}.rbxmx").write_text(xml, encoding="utf-8")
        filmstrip(d, self.root / "preview.png", title=f"{self.root.name} v{v}")
        self.file.write_text(json.dumps(self.m, indent=1))
        line = (f"anim {self.root.name} v{v}: {d['length']:.2f}s {'loop' if d['loop'] else 'one-shot'} "
                f"{d['priority']}, {len(frames)} keyframes, {len(d['tracks'])} joints, "
                f"height {stats['low']:.1f}..{stats['high']:.1f} studs -> export/{self.root.name}.rbxmx")
        return line + (" | warn: " + "; ".join(warns) if warns else "")

    def resolved(self) -> dict:
        return resolve(self.m["spec"])

    def rollback(self, version: int) -> str:
        spec = self.m.get("specs", {}).get(str(version))
        if spec is None:
            raise KeyError(f"no version {version}; have v1..v{self.m['version']}")
        return self._commit(copy.deepcopy(spec), f"rollback to v{version}")

    def history(self) -> str:
        return "\n".join(self.m["history"])
