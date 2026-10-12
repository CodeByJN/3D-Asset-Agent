"""One call: generate (cached) -> asset folder -> build. Returns one line."""
import json
from pathlib import Path

from . import generators
from .asset import Asset
from .project import Project


def make_asset(root, prompt: str | None = None, image: str | None = None, budget: str | None = None,
               style: str | None = None, color: list[float] | None = None, backend: str = "auto",
               textured: bool = False, seed: int = 1234, project: Project | None = None, **overrides) -> str:
    """Make a game-ready asset from a text prompt or an image.

    style:    project (paint the reference image on from the front) | flat (one colour x AO).
              Ignored when textured=True, which asks the generator for its own texture (more GPU quota).
    color:    RGB 0-1 tint for flat style (snapped to the project palette, if any).
    textured: use the generator's texture and bake it (slower, uses more free quota).
    backend:  auto (your Hunyuan server if it is up, else free hf) | hf | local.
    project:  fills unset arguments from the game's style guide and roster, appends its brief to
              the prompt, and applies its tri/texture/finish/size settings.
    """
    root = Path(root)
    d = project.defaults(root.name, prompt) if project else {}
    gen_prompt = d.get("prompt", prompt)
    budget = budget or d.get("budget") or "roblox_prop"
    style = style or d.get("style") or "project"
    if d.get("tex_size"):
        overrides.setdefault("tex_size", d["tex_size"])
    if project and (color or style == "flat"):
        color = project.snap(color)
    gen = generators.generate(generators.get(backend), prompt=gen_prompt, image=image, textured=textured, seed=seed)
    mode = "bake" if textured else style
    a = Asset.create(root, {"main": gen.mesh}, budget, images={"main": gen.image}, surface_mode=mode, **overrides)
    a.m.update(project=project.name if project else None, prompt=gen_prompt)
    if d.get("target_tris"):
        a.m["params"]["topology"]["main"]["target_tris"] = d["target_tris"]
    if d.get("ao") is not None:
        a.m["params"]["surface"]["main"]["ao"] = d["ao"]
    if d.get("scale_to"):
        a.m["params"]["export"]["scale_to"] = d["scale_to"]
    a._save()
    fin = a.finish
    fin.update({k: d[k] for k in ("roughness", "metallic") if d.get(k) is not None})
    (a.root / "finish.json").write_text(json.dumps(fin, indent=2))
    line = a.revise("finish", part="main", tint=color) if color else a.build()
    if project:
        project.mark(root.name, status="made", prompt=prompt or project.d["assets"].get(root.name, {}).get("prompt"))
    return f"{gen.summary()} | {line}"
