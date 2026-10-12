"""VFX layer: named effects attached to an asset, stored as params only.

Changing an effect never touches the mesh, texture or export: only the Studio script that adds
the effects changes, so a "make the flames blue" revision costs no Blender work and no re-upload.

effect = {type, color [r,g,b] 0-1, size (x1), rate (x1)}; in Roblox each type becomes:
  fire     ParticleEmitter (flames rising from the model's volume)
  smoke    ParticleEmitter (slow puffs from the top)
  sparkles ParticleEmitter (glints around the model)
  glow     PointLight (+ faint sparkles in the preview)
"""
TYPES = {
    "fire": {"color": [1.0, 0.45, 0.1], "size": 1.0, "rate": 1.0},
    "smoke": {"color": [0.45, 0.45, 0.45], "size": 1.0, "rate": 1.0},
    "sparkles": {"color": [1.0, 0.9, 0.4], "size": 1.0, "rate": 1.0},
    "glow": {"color": [1.0, 0.85, 0.55], "size": 1.0, "rate": 1.0},
}
KEYS = {"type", "color", "size", "rate"}


def merge(current: dict, change: dict) -> dict:
    """Apply {effect_name: {fields} | None}. None removes; fields merge into the existing effect."""
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
        fx.setdefault("type", name if name in TYPES else None)
        if fx["type"] not in TYPES:
            raise KeyError(f"effect {name!r} needs a type: {', '.join(TYPES)}")
        out[name] = fx
    return out


def resolve(effects: dict) -> dict:
    """Effects with every field filled from the type defaults."""
    return {n: {**TYPES[fx["type"]], **fx} for n, fx in effects.items()}


def describe(effects: dict) -> str:
    return ", ".join(f"{n}={fx['type']}" + (f" rgb{tuple(fx['color'])}" if "color" in fx else "")
                     for n, fx in effects.items()) or "none"
