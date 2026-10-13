"""VFX layer: named effects attached to an asset, stored as params only.

Changing an effect never touches the mesh, texture or export: only the Studio script that builds
the effects changes, so a "make the flames blue" revision costs no Blender work and no re-upload.

effect = {type: a preset from library/vfx/presets.json, color [r,g,b] 0-1 (recolours the preset,
keeping its light/dark shading), size (x1, scales studs), rate (x1, scales particle counts)}.

A preset is a tree of real Roblox instances, the same shape Studio has, so presets imported from
Creator Store VFX are lossless and hand-made ones can use everything Roblox offers:
    {tags, use, score, source, mode: loop|burst, sketch, nodes: [node]}
    node = {class, name, props: {Property: value}, attrs: {Attribute: value}, tween, children: [node]}
Values are JSON with tags for Roblox types (see luau.py): {"c3": [r,g,b]}, {"cs": [[t,r,g,b]..]},
{"ns": [[t,v(,env)]..]}, {"nr": [min,max]}, {"v2": ..}, {"v3": ..}, {"cf": [x,y,z,rx,ry,rz]},
{"enum": "Material.Neon"}, {"ref": "Path/To/Attachment"}. Root nodes are parented to the host part.
Bursts: emitters with attribute EmitCount (and EmitDelay seconds) fire Emit(EmitCount) when played.
tween = {time, delay, style, props}: played on the node when the effect plays (rings, flashes).
"""
import copy
import json
import os
from pathlib import Path

KEYS = {"type", "color", "size", "rate"}
# properties measured in studs, scaled by an effect's size
STUD_PROPS = {"Size", "Speed", "Acceleration", "Position", "Width0", "Width1", "CurveSize0", "CurveSize1",
              "TextureLength", "Range", "MinLength", "MaxLength", "Offset", "Scale", "StudsOffset"}
GUI_CLASSES = {"ImageLabel", "TextLabel", "Frame", "UIStroke", "UIGradient", "SurfaceGui"}  # sizes are fractions/pixels
COLOUR_PROPS = {"Color"}


def library_path() -> Path:
    return Path(os.environ.get("ASSET_AGENT_VFX") or Path(__file__).parents[2] / "library" / "vfx" / "presets.json")


def uploads() -> dict:
    """texture://name -> rbxassetid://N for our textures that have been uploaded to Roblox."""
    f = library_path().parent / "textures" / "uploads.json"
    return json.loads(f.read_text()) if f.exists() else {}


def resolve_textures(nodes, ids=None):
    """Copy of a node tree with texture://name swapped for its uploaded asset id ('' if not uploaded)."""
    ids = uploads() if ids is None else ids
    out = copy.deepcopy(nodes)

    def walk(n):
        for key in ("Texture", "Image", "TextureID"):
            v = (n.get("props") or {}).get(key)
            if isinstance(v, str) and v.startswith("texture://"):
                n["props"][key] = ids.get(v[len("texture://"):], "")
        for c in n.get("children") or []:
            walk(c)
    for n in out:
        walk(n)
    return out


def presets() -> dict:
    return {k: v for k, v in json.loads(library_path().read_text()).items() if not k.startswith("_")}


def save_preset(name: str, preset: dict):
    p = library_path()
    d = json.loads(p.read_text())
    d[name] = preset
    p.write_text(json.dumps(d, indent=1) + "\n")


def merge(current: dict, change: dict) -> dict:
    """Apply {effect_name: {fields} | None}. None removes; fields merge into the existing effect."""
    types = presets()
    out = {k: dict(v) for k, v in current.items()}
    for name, spec in change.items():
        if spec is None:
            if name not in out:
                raise KeyError(f"no effect {name!r}; have {', '.join(out) or 'none'}")
            del out[name]
            continue
        if not isinstance(spec, dict):
            raise ValueError(f"effect {name!r} must be a dict like {{'type': 'fire', 'color': [0, 0, 1]}}")
        bad = set(spec) - KEYS
        if bad:
            raise KeyError(f"unknown effect keys {sorted(bad)}; have {sorted(KEYS)}")
        fx = {**out.get(name, {}), **spec}
        fx.setdefault("type", name if name in types else None)
        if fx["type"] not in types:
            raise KeyError(f"effect {name!r} needs a type: {', '.join(types)}")
        out[name] = fx
    return out


# ------------------------------------------------------------ transforms on tagged values

def _scale_value(v, k):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v * k
    if isinstance(v, dict):
        if "ns" in v:
            return {"ns": [[p[0], p[1] * k, *[e * k for e in p[2:]]] for p in v["ns"]]}
        if "nr" in v:
            return {"nr": [x * k for x in v["nr"]]}
        if "v3" in v:
            return {"v3": [x * k for x in v["v3"]]}
        if "v2" in v:
            return {"v2": [x * k for x in v["v2"]]}
        if "cf" in v:
            return {"cf": [x * k for x in v["cf"][:3]] + v["cf"][3:]}
    return v


def recolour(v, rgb):
    """Swap a colour's hue for rgb, keeping its brightness (per keypoint for sequences)."""
    if "c3" in v:
        return {"c3": [round(x * max(v["c3"]), 3) for x in rgb]}
    top = max(max(p[1:4]) for p in v["cs"]) or 1.0
    return {"cs": [[p[0], *[round(x * max(p[1:4]) / top, 3) for x in rgb]] for p in v["cs"]]}


def transform(nodes, k=1.0, rate=1.0, rgb=None):
    """Copy of a node tree with sizes x k, particle counts x rate, colours recoloured to rgb."""
    out = copy.deepcopy(nodes)

    def walk(n):
        props = n.get("props", {})
        for key in list(props):
            if k != 1 and (key in STUD_PROPS or key == "CFrame") and n["class"] not in GUI_CLASSES:
                v = props[key]
                if isinstance(v, dict) and "u2" in v:  # BillboardGui size: the scale parts are studs
                    v = {"u2": [v["u2"][0] * k, v["u2"][1], v["u2"][2] * k, v["u2"][3]]}
                props[key] = _scale_value(v, k)  # CFrame: only its position scales
            if rgb and key in COLOUR_PROPS and isinstance(props[key], dict):
                props[key] = recolour(props[key], rgb)
        if rate != 1 and "Rate" in props:
            props["Rate"] = props["Rate"] * rate
        attrs = n.get("attrs", {})
        if rate != 1 and "EmitCount" in attrs:
            attrs["EmitCount"] = max(1, round(attrs["EmitCount"] * rate))
        if k != 1 and n.get("anim", {}).get("orbit"):
            o = n["anim"]["orbit"]
            n["anim"]["orbit"] = {**o, "radius": o.get("radius", 3) * k, "y": o.get("y", 0) * k}
        tw = n.get("tween")
        if tw and k != 1:
            tw["props"] = {p: _scale_value(v, k) if p in STUD_PROPS else v for p, v in tw["props"].items()}
        for c in n.get("children", []):
            walk(c)
    for n in out:
        walk(n)
    return out


def main_colour(nodes):
    """The first colour in the tree (for previews), as [r,g,b]."""
    stack = list(nodes)
    while stack:
        n = stack.pop(0)
        c = n.get("props", {}).get("Color")
        if isinstance(c, dict):
            return c["c3"] if "c3" in c else c["cs"][0][1:4]
        stack[:0] = n.get("children", [])
    return [1, 1, 1]


def resolve(effects: dict) -> dict:
    """Each effect expanded to its preset's node tree with colour/size/rate applied, plus the
    `sketch` style and main `color` the Blender preview draws."""
    types = presets()
    out = {}
    for name, fx in effects.items():
        p = types[fx["type"]]
        k, rate = fx.get("size", 1.0), fx.get("rate", 1.0)
        nodes = transform(p["nodes"], k, rate, fx.get("color"))
        out[name] = {"type": fx["type"], "mode": p.get("mode", "loop"), "sketch": p.get("sketch", "sparkles"),
                     "color": main_colour(nodes), "size": k, "rate": rate, "nodes": nodes}
    return out


def describe(effects: dict) -> str:
    return ", ".join(f"{n}={fx['type']}" + (f" rgb{tuple(fx['color'])}" if "color" in fx else "")
                     for n, fx in effects.items()) or "none"


def catalog() -> str:
    """One line per preset: name [tags] score use."""
    return "\n".join(f"{n} [{','.join(p.get('tags', []))}]{' ' + str(p['score']) + '/10' if p.get('score') else ''} "
                     f"{p.get('use', '')}" for n, p in presets().items())
