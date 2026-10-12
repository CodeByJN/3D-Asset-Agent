"""VFX layer: named effects attached to an asset, stored as params only.

Changing an effect never touches the mesh, texture or export: only the Studio script that adds
the effects changes, so a "make the flames blue" revision costs no Blender work and no re-upload.

effect = {type: a preset from library/vfx/presets.json, color [r,g,b] 0-1 (recolours the preset,
keeping its light/dark shading), size (x1), rate (x1)}.
"""
import json
import os
from pathlib import Path

KEYS = {"type", "color", "size", "rate"}


def library_path() -> Path:
    return Path(os.environ.get("ASSET_AGENT_VFX") or Path(__file__).parents[2] / "library" / "vfx" / "presets.json")


def presets() -> dict:
    return {k: v for k, v in json.loads(library_path().read_text()).items() if not k.startswith("_")}


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


def recolour(keys, rgb):
    """Swap a colour sequence's hue for rgb, keeping each keypoint's relative brightness."""
    top = max(max(c) for _, c in keys) or 1.0
    return [[t, [round(x * max(c) / top, 3) for x in rgb]] for t, c in keys]


def resolve(effects: dict) -> dict:
    """Each effect expanded to its preset's emitters with colour/size/rate applied, plus the
    `sketch` style and main `color` the Blender preview draws."""
    types = presets()
    out = {}
    for name, fx in effects.items():
        p = types[fx["type"]]
        k, rate = fx.get("size", 1.0), fx.get("rate", 1.0)
        emitters = []
        for e in p["emitters"]:
            e = dict(e)
            if e.get("class") == "light":
                if fx.get("color"):
                    e["color"] = list(fx["color"])
                e["range"] = e["range"] * k
            else:
                if fx.get("color"):
                    e["color"] = recolour(e["color"], fx["color"])
                e["size"] = [[t, v * k] for t, v in e["size"]]
                e["rate"] = e["rate"] * rate
            emitters.append(e)
        first = emitters[0]
        main = first["color"] if first.get("class") == "light" else first["color"][0][1]
        out[name] = {"type": fx["type"], "sketch": p.get("sketch", "sparkles"), "color": main,
                     "size": k, "rate": rate, "emitters": emitters}
    return out


def describe(effects: dict) -> str:
    return ", ".join(f"{n}={fx['type']}" + (f" rgb{tuple(fx['color'])}" if "color" in fx else "")
                     for n, fx in effects.items()) or "none"


def catalog() -> str:
    """One line per preset: name [tags] use."""
    return "\n".join(f"{n} [{','.join(p.get('tags', []))}] {p.get('use', '')}" for n, p in presets().items())
