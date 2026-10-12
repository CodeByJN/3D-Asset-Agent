"""Original VFX for Steal a Credit Card, written into library/vfx/presets.json.

Built from what the user's grades showed (2026-10-12, 79 effects graded):
  - layered, mostly stationary sprites (core + rays + aura) instead of scattered specks
  - every particle fades in AND out (transparency 1 -> low -> 1) so nothing pops
  - sizes grow over the lifetime; full random rotation plus a slow spin
  - very bright additive glow (Brightness 3-6, LightEmission 1)
  - few particles living 0.5-3 s; flicker curves for electricity
  - our own HD textures only (src/asset_agent/vfx_textures.py), referenced as texture://<name>
Run: python tools/vfx_originals.py
"""
import json
import random
from pathlib import Path

LIB = Path(__file__).parents[1] / "library" / "vfx" / "presets.json"
SRC = {"kind": "original", "by": "claude", "set": "credit-card-v1",
       "notes": "own textures; recipes learned from the user's grades of Rei's pack"}


def cs(*keys):
    """Colour sequence from (t, (r,g,b)) pairs; one colour = constant."""
    if len(keys) == 1:
        keys = ((0, keys[0]), (1, keys[0]))
    return {"cs": [[t, *c] for t, c in keys]}


def n(*keys):
    """Number sequence from (t, value[, envelope]) tuples."""
    return {"ns": [list(k) for k in keys]}


FADE = n((0, 1), (0.35, 0.35), (1, 1))          # in, hold, out
FADE_SOFT = n((0, 1), (0.5, 0.55), (1, 1))
FADE_OUT = n((0, 0), (0.6, 0.1), (1, 1))


def flicker(seed, lo=0.1, hi=0.95, keys=18):
    rnd = random.Random(seed)
    pts = [[0, 1]] + [[round(i / keys, 3), round(rnd.uniform(lo, hi), 3)] for i in range(1, keys)] + [[1, 1]]
    return {"ns": pts}


def pe(name, tex, color, size, transp=FADE, life=(1, 1), rate=5, speed=(0, 0), **kw):
    props = {"Texture": f"texture://{tex}", "Color": color, "Size": size, "Transparency": transp,
             "Lifetime": {"nr": list(life)}, "Rate": rate, "Speed": {"nr": list(speed)},
             "LightEmission": kw.pop("light", 1), "Brightness": kw.pop("bright", 3),
             "Rotation": {"nr": list(kw.pop("rot", (-180, 180)))}}
    if (rs := kw.pop("spin", None)) is not None:
        props["RotSpeed"] = {"nr": list(rs)}
    if (sp := kw.pop("spread", None)) is not None:
        props["SpreadAngle"] = {"v2": list(sp)}
    if (acc := kw.pop("accel", None)) is not None:
        props["Acceleration"] = {"v3": list(acc)}
    for k, v in (("drag", "Drag"), ("z", "ZOffset")):
        if k in kw:
            props[v] = kw.pop(k)
    if kw.pop("locked", True):
        props["LockedToPart"] = True
    if (fb := kw.pop("flipbook", None)):
        props["FlipbookLayout"] = {"enum": "ParticleFlipbookLayout.Grid4x4"}
        props["FlipbookMode"] = {"enum": f"ParticleFlipbookMode.{fb}"}
        props["FlipbookFramerate"] = {"nr": [24, 30]}
        props["FlipbookStartRandom"] = True
    if (shape := kw.pop("shape", None)):
        props["Shape"] = {"enum": f"ParticleEmitterShape.{shape}"}
    attrs = None
    if (count := kw.pop("burst", None)):
        props["Enabled"] = False
        attrs = {"EmitCount": count, **({"EmitDelay": kw.pop("delay")} if "delay" in kw else {})}
    assert not kw, kw
    node = {"class": "ParticleEmitter", "name": name, "props": props}
    if attrs:
        node["attrs"] = attrs
    return node


def at(name, y, *children):
    return {"class": "Attachment", "name": name, "props": {"CFrame": {"cf": [0, y, 0, 0, 0, 0]}}, "children": list(children)}


def light(color, rng=12, bright=2):
    return {"class": "PointLight", "name": "Light", "props": {"Color": {"c3": list(color)}, "Range": rng, "Brightness": bright}}


def preset(use, tags, nodes, mode="loop", host=(2, 2, 2), sketch="glow"):
    return {"tags": tags, "use": use, "source": SRC, "mode": mode, "sketch": sketch,
            "host": {"size": {"v3": list(host)}}, "nodes": nodes}


GOLD, GOLD_DEEP, WHITE = (1, 0.86, 0.42), (1, 0.62, 0.12), (1, 1, 1)
GREEN, GREEN_DEEP = (0.45, 1, 0.5), (0.1, 0.8, 0.3)
RED, RED_DEEP = (1, 0.25, 0.2), (0.85, 0.02, 0.05)
BLUE, BLUE_DEEP, CYAN = (0.45, 0.75, 1), (0.12, 0.35, 1), (0.6, 0.95, 1)
PURPLE, PURPLE_DEEP = (0.8, 0.5, 1), (0.45, 0.1, 0.95)
RAINBOW = ((0, (1, 0.35, 0.35)), (0.2, (1, 0.8, 0.25)), (0.4, (0.4, 1, 0.45)), (0.6, (0.35, 0.8, 1)),
           (0.8, (0.6, 0.45, 1)), (1, (1, 0.4, 0.85)))


def orb(colour, deep, extra=(), aura_size=5, ray_size=6):
    """The 10/10 recipe: soft aura + slow rays + bright core, all stationary, fading in and out."""
    c = cs(*colour) if isinstance(colour[0], tuple) else cs((0, colour), (1, deep))
    return at("Centre", 0,
              pe("Aura", "glow", c, n((0, aura_size * 0.6), (0.5, aura_size * 0.9, 0.3), (1, aura_size, 0.3)),
                 FADE_SOFT, (1.4, 1.8), 3, spin=(-10, 10), bright=2),
              pe("Rays", "rays", c, n((0, ray_size * 0.5), (1, ray_size, 0.4)), FADE_SOFT, (2.5, 3.5), 0.9,
                 spin=(-8, 8), bright=3),
              pe("Core", "glow_hot", cs(WHITE), n((0, 1.4, 0.15), (1, 1.4, 0.15)), FADE, (0.3, 0.5), 12, bright=4),
              *extra)


def effects():
    out = {}
    out["cc_card_glint"] = preset(
        "Stealable card: warm halo, slow rays and the odd crisp glint so it reads as valuable", ["item", "steal", "card"],
        [at("Centre", 0,
            pe("Halo", "glow", cs((0, GOLD), (1, GOLD_DEEP)), n((0, 3), (0.5, 4, 0.4), (1, 4.6, 0.4)), FADE_SOFT, (1.4, 1.8), 2.5,
               spin=(-10, 10), bright=2),
            pe("Rays", "rays", cs(GOLD), n((0, 3), (1, 5.5, 0.4)), FADE_SOFT, (2.6, 3.2), 0.8, spin=(-8, 8), bright=3)),
         pe("Glints", "sparkle", cs((0, WHITE), (1, GOLD)), n((0, 0), (0.3, 1.8, 0.4), (1, 0)), n((0, 0), (1, 0.2)),
            (0.6, 0.8), 1.6, rot=(-12, 12), bright=5)],
        host=(3, 2, 0.3), sketch="sparkles")
    out["cc_steal_burst"] = preset(
        "On the thief at the moment of a steal: white flash, gold shockwave, rays, flying stars and coins", ["action", "steal", "burst"],
        [at("Centre", 0,
            pe("Flash", "glow_hot", cs((0, WHITE), (1, GOLD)), n((0, 1), (0.15, 7), (1, 9)), n((0, 0), (0.25, 0.1), (1, 1)),
               (0.45, 0.45), 0, burst=1, bright=5),
            pe("Shockwave", "shockwave", cs((0, GOLD), (1, GREEN)), n((0, 1), (1, 15)), n((0, 0.05), (1, 1)), (0.5, 0.5), 0,
               burst=1, bright=3),
            pe("Rays", "rays", cs(GOLD), n((0, 2), (1, 11)), n((0, 0.1), (1, 1)), (0.4, 0.45), 0, burst=2, spin=(-60, 60), bright=4),
            pe("Stars", "sparkle", cs((0, GOLD), (1, GREEN)), n((0, 1.6, 0.3), (1, 0)), n((0, 0), (1, 0.3)), (0.55, 0.85), 0,
               speed=(14, 24), spread=(180, 180), drag=5, burst=18, spin=(-90, 90), bright=4),
            pe("Coins", "coin", cs(WHITE), n((0, 1.1), (1, 1.1)), n((0, 0), (0.8, 0), (1, 1)), (0.9, 1.2), 0,
               speed=(14, 18), spread=(35, 35), accel=(0, -45, 0), burst=8, spin=(-200, 200), light=0, bright=1))],
        mode="burst", sketch="sparkles")
    out["cc_money_pop"] = preset(
        "Money generator paying out: coins hop out and fall, with a green shimmer", ["base", "income", "generator", "money"],
        [at("Top", 1,
            pe("Coins", "coin", cs(WHITE), n((0, 0.4), (0.15, 1.2), (1, 1.1)), n((0, 0), (0.8, 0), (1, 1)), (0.9, 1),
               2.5, speed=(10, 13), spread=(15, 15), accel=(0, -40, 0), spin=(-150, 150), light=0, bright=1, locked=False),
            pe("Shimmer", "sparkle", cs((0, WHITE), (1, GREEN)), n((0, 0), (0.3, 1.1), (1, 0)), n((0, 0), (1, 0.3)), (0.5, 0.6), 4,
               speed=(2, 4), spread=(40, 40), rot=(-15, 15), bright=4, locked=False),
            pe("Pulse", "glow", cs((0, GREEN), (1, GREEN_DEEP)), n((0, 2), (1, 3.6)), FADE_SOFT, (1.1, 1.3), 1.2, bright=2))],
        host=(3, 2, 3), sketch="sparkles")
    out["cc_speed_aura"] = preset(
        "Speed upgrades: blue energy rising from the feet with a pulsing ground ring", ["character", "speed", "upgrade"],
        [at("Feet", -2.4,
            pe("Column", "glow", cs((0, CYAN), (1, BLUE_DEEP)), n((0, 2.2), (1, 3.8)), FADE_SOFT, (0.8, 1), 6, speed=(2, 3),
               spread=(5, 5), bright=2),
            pe("Streaks", "sparkle", cs((0, WHITE), (0.4, CYAN), (1, BLUE)), n((0, 0.9, 0.2), (1, 0)), n((0, 0.1), (1, 1)),
               (0.4, 0.6), 28, speed=(7, 11), spread=(12, 12), rot=(-8, 8), bright=4),
            pe("Ring", "ring", cs((0, CYAN), (1, BLUE)), n((0, 1.5), (1, 5.5)), n((0, 0.2), (1, 1)), (0.6, 0.6), 2.2, bright=3))],
        host=(2, 5, 1), sketch="fire")
    out["cc_stolen_alert"] = preset(
        "Over a victim's base when its card is taken: red pulses you can see across the map", ["base", "steal", "alert"],
        [at("Centre", 0,
            pe("Pulse", "shockwave", cs((0, RED), (1, RED_DEEP)), n((0, 2), (1, 13)), n((0, 0.15), (1, 1)), (1, 1), 1.3, bright=3),
            pe("Glow", "glow", cs((0, RED), (1, RED_DEEP)), n((0, 5), (0.5, 7), (1, 5)), FADE_SOFT, (0.8, 0.8), 2.5, bright=3),
            pe("Core", "glow_hot", cs(WHITE), n((0, 1.6), (1, 1.6)), flicker(7, 0.2, 0.9), (0.6, 0.6), 4, bright=4),
            light(RED, 16, 2))],
        sketch="glow")
    out["cc_rarity_rare"] = preset("Rare prize: calm blue orb", ["rarity", "wheel", "aura", "rare"],
                                   [orb(BLUE, BLUE_DEEP, [light(BLUE, 10, 1.5)])])
    out["cc_rarity_epic"] = preset(
        "Epic prize: purple orb with crackling lightning and orbiting sparks", ["rarity", "wheel", "aura", "epic"],
        [orb(PURPLE, PURPLE_DEEP, [
            pe("Bolts", "bolts", cs((0, WHITE), (1, PURPLE)), n((0, 5, 0.4), (1, 5, 0.4)), flicker(3), (0.33, 0.33), 7,
               bright=5, flipbook="Loop"),
            pe("Sparks", "sparkle", cs((0, WHITE), (1, PURPLE)), n((0, 0), (0.3, 0.9), (1, 0)), n((0, 0), (1, 0.3)), (0.8, 1.1), 6,
               speed=(1.5, 3), spread=(180, 180), bright=4, locked=False),
            light(PURPLE, 12, 2)], aura_size=5.5)])
    out["cc_rarity_legendary"] = preset(
        "Legendary prize: gold orb, a light pillar shooting up and a slow shockwave", ["rarity", "wheel", "aura", "legendary"],
        [orb(GOLD, GOLD_DEEP, [
            pe("Pillar", "glow", cs((0, WHITE), (0.3, GOLD), (1, GOLD_DEEP)), n((0, 2.6), (1, 1.2)), n((0, 0.6), (0.2, 0.3), (1, 1)),
               (1, 1.2), 26, speed=(9, 13), spread=(2, 2), bright=3, locked=False),
            pe("Wave", "shockwave", cs(GOLD), n((0, 2), (1, 12)), n((0, 0.2), (1, 1)), (1.2, 1.2), 0.7, bright=3),
            pe("Sparks", "sparkle", cs((0, WHITE), (1, GOLD)), n((0, 0), (0.3, 1.1), (1, 0)), n((0, 0), (1, 0.3)), (0.8, 1.2), 8,
               speed=(2, 5), spread=(60, 60), bright=5, locked=False),
            light(GOLD, 16, 3)], aura_size=6, ray_size=7.5)])
    out["cc_rarity_mythic"] = preset(
        "Mythic prize: rainbow orb with white lightning, a rainbow pillar and shockwaves: the big one",
        ["rarity", "wheel", "aura", "mythic"],
        [orb(RAINBOW, None, [
            pe("Bolts", "bolts", cs(WHITE), n((0, 6, 0.5), (1, 6, 0.5)), flicker(11), (0.33, 0.33), 9, bright=6, flipbook="Loop"),
            pe("Pillar", "glow", cs(*RAINBOW), n((0, 2.8), (1, 1.2)), n((0, 0.6), (0.2, 0.3), (1, 1)), (1, 1.2), 30,
               speed=(10, 14), spread=(2, 2), bright=3, locked=False),
            pe("Wave", "shockwave", cs(*RAINBOW), n((0, 2), (1, 14)), n((0, 0.2), (1, 1)), (1.2, 1.2), 0.9, bright=3),
            light(WHITE, 18, 3)], aura_size=6.5, ray_size=8)])
    out["cc_shock_orb"] = preset(
        "HD lightning orb: hot cyan core with crackling bolts and a thin ring", ["electric", "lightning", "orb"],
        [at("Centre", 0,
            pe("Core", "glow_hot", cs((0, WHITE), (1, CYAN)), n((0, 2, 0.2), (1, 2, 0.2)), FADE, (0.3, 0.5), 14, bright=5),
            pe("Bolts", "bolts", cs((0, WHITE), (1, CYAN)), n((0, 5, 0.5), (1, 5, 0.5)), flicker(5), (0.33, 0.33), 10,
               bright=6, flipbook="Loop"),
            pe("Halo", "glow", cs((0, CYAN), (1, BLUE_DEEP)), n((0, 4.5), (1, 5.5)), FADE_SOFT, (1, 1.2), 3, bright=2),
            pe("Ring", "ring", cs(CYAN), n((0, 4.5), (1, 5)), flicker(9, 0.5, 0.95), (0.5, 0.5), 2, bright=3),
            light(CYAN, 12, 2))])
    return out


if __name__ == "__main__":
    d = json.loads(LIB.read_text())
    for name, p in effects().items():
        old = d.get(name, {})
        if "score" in old:  # keep grades across regenerations
            p["score"], p["note"] = old["score"], old.get("note")
        d[name] = p
        print("wrote", name)
    LIB.write_text(json.dumps(d, indent=1) + "\n")
