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
    out["cc_steal_burst"] = preset(  # v2: "could do more" -> bigger flash, second wave, more stars/coins, lingering dust
        "On the thief at the moment of a steal: white flash, double shockwave, rays, stars, a coin shower and gold dust",
        ["action", "steal", "burst"],
        [at("Centre", 0,
            pe("Flash", "glow_hot", cs((0, WHITE), (1, GOLD)), n((0, 1), (0.12, 10), (1, 12)), n((0, 0), (0.25, 0.1), (1, 1)),
               (0.5, 0.5), 0, burst=1, bright=6),
            pe("Shockwave", "shockwave", cs((0, GOLD), (1, GOLD_DEEP)), n((0, 1), (1, 17)), n((0, 0.05), (1, 1)), (0.5, 0.5), 0,
               burst=1, bright=4),
            pe("Shockwave2", "shockwave", cs((0, GREEN), (1, GREEN_DEEP)), n((0, 1), (1, 22)), n((0, 0.2), (1, 1)), (0.65, 0.65), 0,
               burst=1, delay=0.12, bright=3),
            pe("Rays", "rays", cs(GOLD), n((0, 3), (1, 14)), n((0, 0.05), (1, 1)), (0.5, 0.55), 0, burst=2, spin=(-90, 90), bright=5),
            pe("Stars", "sparkle", cs((0, WHITE), (0.4, GOLD), (1, GREEN)), n((0, 2, 0.4), (1, 0)), n((0, 0), (1, 0.3)), (0.6, 1),
               0, speed=(16, 28), spread=(180, 180), drag=5, burst=30, spin=(-120, 120), bright=5),
            pe("Coins", "coin", cs(WHITE), n((0, 1.2, 0.2), (1, 1.2, 0.2)), n((0, 0), (0.85, 0), (1, 1)), (1.1, 1.5), 0,
               speed=(16, 22), spread=(40, 40), accel=(0, -48, 0), burst=14, spin=(-220, 220), light=0, bright=1, locked=False),
            pe("Dust", "glow", cs((0, GOLD), (1, GOLD_DEEP)), n((0, 0.6, 0.2), (1, 0)), n((0, 0.2), (1, 1)), (1.2, 1.8), 0,
               speed=(2, 6), spread=(180, 180), drag=2, burst=26, delay=0.1, bright=3, locked=False))],
        mode="burst", sketch="sparkles")
    out["cc_money_pop"] = preset(  # v2: "could be better" -> cash bills too, ground ring pulse, more shimmer
        "Money generator paying out: coins and cash hop out and fall, a green ring pulses at the base",
        ["base", "income", "generator", "money"],
        [at("Top", 1,
            pe("Coins", "coin", cs(WHITE), n((0, 0.4), (0.15, 1.3, 0.2), (1, 1.2, 0.2)), n((0, 0), (0.8, 0), (1, 1)), (0.9, 1.1),
               3, speed=(11, 14), spread=(18, 18), accel=(0, -40, 0), spin=(-160, 160), light=0, bright=1, locked=False),
            pe("Cash", "cash", cs(WHITE), n((0, 0.6), (0.15, 1.8), (1, 1.6)), n((0, 0), (0.75, 0), (1, 1)), (1.1, 1.4), 1.2,
               speed=(9, 12), spread=(22, 22), accel=(0, -26, 0), drag=0.6, spin=(-90, 90), light=0, bright=1, locked=False),
            pe("Shimmer", "sparkle", cs((0, WHITE), (1, GREEN)), n((0, 0), (0.3, 1.2), (1, 0)), n((0, 0), (1, 0.3)), (0.6, 0.8), 6,
               speed=(3, 6), spread=(30, 30), rot=(-15, 15), bright=5, locked=False)),
         at("Base", -1,
            pe("Ring", "ring", cs((0, GREEN), (1, GREEN_DEEP)), n((0, 2), (1, 7)), n((0, 0.2), (1, 1)), (0.9, 0.9), 1.4, bright=3),
            pe("Pulse", "glow", cs((0, GREEN), (1, GREEN_DEEP)), n((0, 3), (1, 4.5)), FADE_SOFT, (1.1, 1.3), 1.4, bright=2))],
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
    out["cc_rarity_epic"] = preset(  # v2: "lightning too big and doing too much" -> half size, far fewer, fainter
        "Epic prize: purple orb with a few fine crackles of lightning and orbiting sparks", ["rarity", "wheel", "aura", "epic"],
        [orb(PURPLE, PURPLE_DEEP, [
            pe("Bolts", "bolts", cs((0, WHITE), (1, PURPLE)), n((0, 2.6, 0.3), (1, 2.6, 0.3)), flicker(3, 0.4, 0.97), (0.25, 0.3),
               2.5, bright=4, flipbook="Random"),
            pe("Sparks", "sparkle", cs((0, WHITE), (1, PURPLE)), n((0, 0), (0.3, 0.9), (1, 0)), n((0, 0), (1, 0.3)), (0.8, 1.1), 6,
               speed=(1.5, 3), spread=(180, 180), bright=4, locked=False),
            light(PURPLE, 12, 2)], aura_size=5.5)])

    def grand(colour, deep, pillar, flash, ring, embers, rays2, extra=(), aura=7, rays=9):
        """Rare's recipe (graded 9) made majestic: bigger orb, a counter-spinning ray layer, a tall bright
        pillar, a flash every couple of seconds, slow halo rings and rising embers."""
        return orb(colour, deep, [
            pe("Rays2", "rays", rays2, n((0, rays * 0.7), (1, rays * 1.3, 0.5)), n((0, 1), (0.5, 0.7), (1, 1)), (3.5, 4.5), 0.6,
               spin=(12, 20), bright=2),
            pe("Pillar", "glow", pillar, n((0, 3.4), (1, 1.6)), n((0, 0.5), (0.2, 0.2), (1, 1)), (1.3, 1.6), 34,
               speed=(14, 18), spread=(2, 2), bright=4, locked=False),
            pe("Flash", "glow_hot", flash, n((0, 4), (0.2, 10), (1, 12)), n((0, 1), (0.1, 0.2), (1, 1)), (0.7, 0.7), 0.5, bright=5),
            pe("Halo", "ring", ring, n((0, 3), (1, 11)), n((0, 0.4), (0.3, 0.3), (1, 1)), (2, 2.2), 0.6, bright=3),
            pe("Embers", "sparkle", embers, n((0, 0), (0.25, 1.1, 0.3), (1, 0)), n((0, 0), (1, 0.4)), (1.4, 2), 10,
               speed=(2, 4), spread=(25, 25), accel=(0, 1.5, 0), rot=(-20, 20), bright=5, locked=False),
            *extra], aura_size=aura, ray_size=rays)

    out["cc_rarity_legendary"] = preset(  # v2: "doesn't scream legendary" -> the rare recipe made majestic
        "Legendary prize: big gold orb, counter-spinning rays, a tall light pillar, a flash and halo rings",
        ["rarity", "wheel", "aura", "legendary"],
        [grand(GOLD, GOLD_DEEP, cs((0, WHITE), (0.25, GOLD), (1, GOLD_DEEP)), cs((0, WHITE), (1, GOLD)), cs(GOLD),
               cs((0, WHITE), (1, GOLD)), cs((0, (1, 0.95, 0.7)), (1, GOLD_DEEP)), [light(GOLD, 20, 3)])])
    rainbow_cycle = cs(*RAINBOW)
    reverse_rainbow = cs(*[(round(1 - t, 3), c) for t, c in reversed(RAINBOW)])
    out["cc_rarity_mythic"] = preset(  # v2: legendary's grandeur with every layer cycling the rainbow; big lightning removed
        "Mythic prize: the legendary orb in shifting rainbow, with a rainbow pillar and halo rings: the big one",
        ["rarity", "wheel", "aura", "mythic"],
        [grand(RAINBOW, None, rainbow_cycle, cs((0, WHITE), (1, (1, 0.85, 1))), rainbow_cycle, rainbow_cycle, reverse_rainbow,
               [pe("Crackle", "bolts", cs(WHITE), n((0, 2.2, 0.3), (1, 2.2, 0.3)), flicker(11, 0.5, 0.97), (0.2, 0.25), 2,
                   bright=4, flipbook="Random"), light(WHITE, 22, 3)], aura=7.5, rays=10)])
    out["cc_shock_orb"] = preset(  # v2 (v1 got 5): rebuilt like Rei's electric orb (10): tiny, very bright, very short-lived
        "HD lightning orb: many tiny, very bright crackles flickering around a small hot core", ["electric", "lightning", "orb"],
        [at("Centre", 0,
            pe("Core", "glow_hot", cs((0, WHITE), (1, CYAN)), n((0, 1.6, 0.2), (1, 1.6, 0.2)), FADE, (0.25, 0.4), 16, bright=5),
            pe("Crackle", "bolts", cs((0, WHITE), (1, CYAN)), n((0, 2.2, 0.4), (1, 2.2, 0.4)), flicker(5, 0.25, 0.9), (0.15, 0.22),
               40, bright=8, flipbook="Random"),
            pe("Spits", "glow_hot", cs((0, WHITE), (1, CYAN)), n((0, 0.5), (1, 0)), n((0, 0), (1, 0.4)), (0.2, 0.35), 30,
               speed=(2, 5), spread=(180, 180), bright=6, locked=False),
            pe("Halo", "glow", cs((0, CYAN), (1, BLUE_DEEP)), n((0, 3.5), (1, 4.2)), FADE_SOFT, (0.8, 1), 3, bright=1.5),
            light(CYAN, 12, 2))])
    return out


if __name__ == "__main__":
    d = json.loads(LIB.read_text())
    for name, p in effects().items():
        old = d.get(name, {})
        p["version"], p["history"] = old.get("version", 1), old.get("history", [])
        if old and old.get("nodes") != p["nodes"]:  # recipe changed: new version; its old grade stays in history
            p["version"] += 1
            print("updated", name, "-> v%d" % p["version"])
        elif "score" in old:  # unchanged: keep its grade
            p["score"], p["note"] = old["score"], old.get("note")
        d[name] = p
    LIB.write_text(json.dumps(d, indent=1) + "\n")
