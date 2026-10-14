"""The brief: what to ask the user before spending GPU minutes on a generation, so an asset can be
right on the first shot. make_asset returns these questions instead of generating until the request
covers them (or the user says to go ahead: ready=True)."""
import re

STYLES = ("low poly", "low-poly", "lowpoly", "stylised", "stylized", "realistic", "cartoon", "toon", "anime", "voxel",
          "blocky", "chibi", "pixel", "hand-painted", "hand painted", "semi-realistic", "cel", "minimal", "roblox")
COLOURS = ("red", "orange", "yellow", "gold", "green", "teal", "cyan", "blue", "navy", "purple", "violet", "pink",
           "magenta", "brown", "tan", "beige", "white", "black", "grey", "gray", "silver", "bronze", "copper", "wood",
           "wooden", "stone", "metal", "steel", "iron", "crystal", "glass", "ice", "colour", "color", "palette", "#")
USES = {"roblox_prop", "roblox_hero", "mobile_prop", "godot_lod"}


def gaps(prompt: str | None, image: str | None, color=None, budget: str | None = None, project=None) -> list[str]:
    """Questions the request leaves open (empty when it's ready to generate)."""
    text = (prompt or "").lower()
    guide = project.d if project else {}
    brief = (guide.get("brief") or "").lower()
    out = []
    if not image:
        out.append("Reference image? One object, plain light or transparent background, no glow or effects, "
                   "front or 3/4 view (concept art, a render, a photo). Without one, a picture is generated "
                   "from the text first (slower, shared free quota).")
    if not any(s in text or s in brief for s in STYLES):
        out.append("Style? e.g. low poly, stylised, realistic, cartoon, anime, voxel, or match an existing game.")
    if color is None and not guide.get("palette") and not any(c in text or c in brief for c in COLOURS):
        out.append("Colours and materials? Main colour, accents, anything that glows (glow is added in Roblox).")
    if budget not in USES and not guide.get("budget"):
        out.append("What is it for, and how big? Prop, hero item, character or VFX centrepiece, "
                   "and its size in studs (a Roblox character is about 5 studs tall).")
    if not image and len(re.findall(r"\w+", text)) < 10:
        out.append("Shape details? The silhouette and the 2-3 features it must have (e.g. curled wings, "
                   "a cracked rim, five pillars).")
    return out


def ask(questions: list[str]) -> str:
    return ("Not generated yet: ask the user these (one message), then call again with the answers in "
            "prompt/image/color/budget, or ready=True if they want it as is:\n"
            + "\n".join(f"- {q}" for q in questions))
