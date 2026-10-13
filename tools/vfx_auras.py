"""Sol's RNG-style auras: whole-body, layered, themed. Written into library/vfx/presets.json.

Construction studied from a Sovereign clip and the Sol's RNG wiki (not copied): one theme and palette,
a title plate (ornate crest + serif name + odds), flat ornaments that turn (crown overhead, sigils
behind and below), small props in orbit, motes and sparkles, glow on the hands, a coloured light.
Every ornament is our own code-drawn texture (src/asset_agent/vfx_textures.py).
Run: python tools/vfx_auras.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vfx_originals import FADE, FADE_SOFT, LIB, at, cs, light, n, pe  # noqa: E402

GOLD, GOLD_PALE, GOLD_DEEP, WHITE = (1, 0.82, 0.42), (1, 0.93, 0.72), (0.85, 0.55, 0.12), (1, 1, 1)


def plane(name, image, size, cf, color=GOLD, bright=2.5, transp=0.0, attach=None, anim=None):
    """A flat image layer. cf = [x,y,z, rx,ry,rz] relative to its part (degrees)."""
    node = {"class": "Plane", "name": name, "props": {"Image": f"texture://{image}", "Size": {"v2": list(size)},
                                                       "CFrame": {"cf": list(cf)}, "Color": {"c3": list(color)},
                                                       "Brightness": bright, "Transparency": transp}}
    if attach:
        node["attach"] = attach
    if anim:
        node["anim"] = anim
    return node


def title_plate(name, odds, attach="Head", y=4.2, width=11, crest_color=GOLD, text_top=WHITE, text_bottom=GOLD,
                stroke=GOLD_DEEP, odds_color=GOLD_PALE):
    """Billboard over the head: ornate crest, the aura's name in a serif with a gradient and outline,
    and its odds between diamonds."""
    label = lambda nm, text, font, pos, size, color, extra=(): {
        "class": "TextLabel", "name": nm, "props": {
            "Text": text, "FontFace": font, "TextScaled": True, "TextColor3": {"c3": list(color)},
            "BackgroundTransparency": 1, "Size": {"u2": [1, 0, size, 0]}, "Position": {"u2": [0, 0, pos, 0]},
            "AnchorPoint": {"v2": [0, 0.5]}, "ZIndex": 3}, "children": list(extra)}
    return {"class": "BillboardGui", "name": "TitlePlate", "attach": attach, "props": {
        "Size": {"u2": [width, 0, width / 2, 0]}, "StudsOffset": {"v3": [0, y, 0]}, "LightInfluence": 0,
        "MaxDistance": 160, "AlwaysOnTop": False},
        "children": [
            {"class": "ImageLabel", "name": "Crest", "props": {
                "Image": "texture://crest", "ImageColor3": {"c3": list(crest_color)}, "BackgroundTransparency": 1,
                "Size": {"u2": [1, 0, 1, 0]}, "ZIndex": 1}},
            label("Name", name, {"font": "Fondamento"}, 0.42, 0.27, WHITE, [
                {"class": "UIGradient", "name": "Gradient", "props": {"Color": cs((0, text_top), (1, text_bottom)), "Rotation": 90}},
                {"class": "UIStroke", "name": "Stroke", "props": {"Color": {"c3": list(stroke)}, "Thickness": 1.5, "Transparency": 0.1}}]),
            label("Odds", f"◆  {odds}  ◆", {"font": "AccanthisADFStd", "italic": True}, 0.66, 0.11, odds_color)]}


def aura(use, tags, nodes):
    return {"tags": tags, "use": use, "rig": "character", "mode": "loop", "sketch": "glow",
            "source": {"kind": "original", "by": "claude", "set": "auras-v1",
                       "notes": "Sol's RNG-style construction, own textures and theme"},
            "host": {"size": {"v3": [2, 2, 1]}}, "nodes": nodes}


def auras():
    out = {}
    out["aura_black_card"] = aura(
        "BLACK CARD (top wheel tier): crest title, turning crown, card sigil and rune ring behind, floor sigil, "
        "orbiting black cards, gold motes and glowing hands",
        ["aura", "character", "card", "gold", "mythic"],
        [title_plate("BLACK CARD", "1 in 1,000,000,000"),
         plane("Crown", "crown_ring", (6.5, 6.5), [0, 1.9, 0, 90, 0, 0], GOLD, 4, attach="Head", anim={"spin": 22}),
         plane("Sigil", "card_sigil", (9.5, 9.5), [0, 0.7, 1.7, 0, 0, 0], GOLD, 3, 0.1, attach="UpperTorso", anim={"spin": 9}),
         plane("Runes", "rune_ring", (12, 12), [0, 0.7, 1.9, 0, 0, 0], GOLD_PALE, 2.5, 0.25, attach="UpperTorso", anim={"spin": -6}),
         plane("FloorSigil", "card_sigil", (9, 9), [0, -2.95, 0, -90, 0, 0], GOLD, 2, 0.35, attach="HumanoidRootPart",
               anim={"spin": 7, "pulse": {"amp": 0.04, "period": 3}}),
         *[plane(f"Card{i}", "card", (1.7, 1.7), [3.4, 0.5, 0, 0, 90, 0], WHITE, 1.4, attach="HumanoidRootPart",
                 anim={"orbit": {"radius": 3.4, "speed": 40, "phase": i * 120, "y": 0.6}, "bob": {"amp": 0.25, "period": 2.6}})
           for i in range(3)],
         {**at("Body", 0,
               pe("Motes", "glow", cs((0, GOLD_PALE), (1, GOLD)), n((0, 0.35, 0.1), (1, 0)), n((0, 1), (0.25, 0.2), (1, 1)),
                  (2, 3), 12, speed=(1, 2.2), spread=(25, 25), bright=4, locked=False),
               pe("Glints", "sparkle", cs((0, WHITE), (1, GOLD)), n((0, 0), (0.3, 1.2, 0.3), (1, 0)), n((0, 0), (1, 0.3)),
                  (0.6, 0.9), 3, rot=(-15, 15), bright=5),
               light(GOLD, 16, 2)), "attach": "HumanoidRootPart"},
         *[{**at(f"{side}Glow", 0,
                 pe("Glow", "glow_hot", cs((0, WHITE), (1, GOLD)), n((0, 1.1, 0.15), (1, 1.1, 0.15)), FADE, (0.3, 0.45), 9, bright=4)),
            "attach": f"{side}Hand"} for side in ("Left", "Right")]])
    return out


if __name__ == "__main__":
    d = json.loads(LIB.read_text())
    for name, p in auras().items():
        old = d.get(name, {})
        p["version"], p["history"] = old.get("version", 1), old.get("history", [])
        if old and old.get("nodes") != p["nodes"]:
            p["version"] += 1
        elif "score" in old:
            p["score"], p["note"] = old["score"], old.get("note")
        d[name] = p
        print("wrote", name, "v%d" % p["version"])
    LIB.write_text(json.dumps(d, indent=1) + "\n")
