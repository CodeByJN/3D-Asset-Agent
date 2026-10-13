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
import colorsys
import copy
import json
import os
from pathlib import Path

KEYS = {"type", "color", "size", "rate"}
# properties measured in studs, scaled by an effect's size
STUD_PROPS = {"Size", "Speed", "Acceleration", "Position", "Width0", "Width1", "CurveSize0", "CurveSize1",
              "TextureLength", "Range", "MinLength", "MaxLength", "Offset", "Scale", "StudsOffset"}
GUI_CLASSES = {"ImageLabel", "TextLabel", "Frame", "UIStroke", "UIGradient", "SurfaceGui"}  # sizes are fractions/pixels
COLOUR_PROPS = {"Color", "ImageColor3", "TextColor3", "Color3"}


def library_path() -> Path:
    return Path(os.environ.get("ASSET_AGENT_VFX") or Path(__file__).parents[2] / "library" / "vfx" / "presets.json")


def uploads() -> dict:
    """texture://name -> rbxassetid://N for our textures that have been uploaded to Roblox."""
    f = library_path().parent / "textures" / "uploads.json"
    return json.loads(f.read_text()) if f.exists() else {}


# Roblox's built-in particle textures stand in for ours until they're uploaded, so an effect is never
# invisible: soft glows and shapes -> sparkles, smoke -> smoke.
STAND_INS = {"smoke": "rbxasset://textures/particles/smoke_main.dds"}
STAND_IN = "rbxasset://textures/particles/sparkles_main.dds"


def resolve_textures(nodes, ids=None):
    """Copy of a node tree with texture://name swapped for its uploaded asset id, or a built-in
    stand-in texture if it hasn't been uploaded yet."""
    ids = uploads() if ids is None else ids
    out = copy.deepcopy(nodes)

    def walk(n):
        for key in ("Texture", "Image", "TextureID"):
            v = (n.get("props") or {}).get(key)
            if isinstance(v, str) and v.startswith("texture://"):
                name = v[len("texture://"):]
                n["props"][key] = ids.get(name) or STAND_INS.get(name, STAND_IN)
        for c in n.get("children") or []:
            walk(c)
    for n in out:
        walk(n)
    return out


def presets() -> dict:
    """The library, with each preset's revisions applied (currently `recolor`: [r,g,b])."""
    out = {}
    for k, v in json.loads(library_path().read_text()).items():
        if k.startswith("_"):
            continue
        if v.get("recolor"):
            v = {**v, "nodes": transform(v["nodes"], rgb=v["recolor"])}
        out[k] = v
    return out


def revise_preset(name: str, note: str = "", **change) -> str:
    """Revise a preset without touching its recipe (recolor=[r,g,b] | None to undo). Each revision is a
    new version; the previous version's settings and grade move into its history."""
    p = library_path()
    d = json.loads(p.read_text())
    if name not in d:
        raise KeyError(f"no preset {name!r}")
    pr = d[name]
    pr.setdefault("history", []).append({"v": pr.get("version", 1), "score": pr.get("score"), "note": pr.get("note"),
                                         "recolor": pr.get("recolor"), "change": change, "why": note})
    for k, v in change.items():
        if v is None:
            pr.pop(k, None)
        else:
            pr[k] = v
    pr["version"] = pr.get("version", 1) + 1
    pr.pop("score", None)
    pr.pop("note", None)
    p.write_text(json.dumps(d, indent=1) + "\n")
    return f"{name} v{pr['version']}: " + ", ".join(f"{k}={v}" for k, v in change.items())


def raw_presets() -> dict:
    return {k: v for k, v in json.loads(library_path().read_text()).items() if not k.startswith("_")}


def save_preset(name: str, preset: dict):  # noqa: E302
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


def _hue_swap(c, hue, s_scale):
    """One colour moved to `hue`: whites stay white, brightness kept, saturation scaled."""
    h, s, v = colorsys.rgb_to_hsv(*c)
    return [round(x, 3) for x in colorsys.hsv_to_rgb(hue, min(1.0, s * s_scale), v)]


def recolour(v, rgb, s_scale=1.0):
    """Swap a colour's hue for rgb's (per keypoint for sequences). Whites and greys stay neutral, light
    and dark shades stay light and dark, and saturation is scaled so the palette lands as vivid as rgb."""
    hue = colorsys.rgb_to_hsv(*rgb)[0]
    if "c3" in v:
        return {"c3": _hue_swap(v["c3"], hue, s_scale)}
    return {"cs": [[p[0], *_hue_swap(p[1:4], hue, s_scale)] for p in v["cs"]]}


def _palette_saturation(nodes):
    """Mean saturation of the tree's coloured (non-white) colours."""
    sats = []

    def walk(n):
        for key, v in (n.get("props") or {}).items():
            if key in COLOUR_PROPS and isinstance(v, dict):
                for c in ([v["c3"]] if "c3" in v else [p[1:4] for p in v.get("cs", [])]):
                    s = colorsys.rgb_to_hsv(*c)[1]
                    if s > 0.2:
                        sats.append(s)
        for ch in n.get("children") or []:
            walk(ch)
    for n in nodes:
        walk(n)
    return sum(sats) / len(sats) if sats else 0


def transform(nodes, k=1.0, rate=1.0, rgb=None):
    """Copy of a node tree with sizes x k, particle counts x rate, colours recoloured to rgb."""
    out = copy.deepcopy(nodes)
    s_scale = 1.0
    if rgb:
        ref = _palette_saturation(nodes)
        s_scale = min(3.0, max(0.3, colorsys.rgb_to_hsv(*rgb)[1] / ref)) if ref else 1.0

    def walk(n):
        props = n.get("props", {})
        for key in list(props):
            if k != 1 and (key in STUD_PROPS or key == "CFrame") and n["class"] not in GUI_CLASSES:
                v = props[key]
                if isinstance(v, dict) and "u2" in v:  # BillboardGui size: the scale parts are studs
                    v = {"u2": [v["u2"][0] * k, v["u2"][1], v["u2"][2] * k, v["u2"][3]]}
                props[key] = _scale_value(v, k)  # CFrame: only its position scales
            if rgb and key in COLOUR_PROPS and isinstance(props[key], dict):
                props[key] = recolour(props[key], rgb, s_scale)
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
