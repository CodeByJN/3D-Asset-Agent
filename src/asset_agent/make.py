"""One call: generate (cached) -> asset folder -> build. Returns one line."""
from pathlib import Path

from . import generators
from .asset import Asset


def make_asset(root, prompt: str | None = None, image: str | None = None, budget: str = "roblox_prop",
               style: str = "project", color: list[float] | None = None, backend: str = "auto",
               textured: bool = False, seed: int = 1234, **overrides) -> str:
    """Make a game-ready asset from a text prompt or an image.

    style:    project (paint the reference image on from the front) | flat (one colour x AO).
              Ignored when textured=True, which asks the generator for its own texture (more GPU quota).
    color:    RGB 0-1 tint for flat style.
    textured: use the generator's texture and bake it (slower, uses more free quota).
    backend:  auto (your Hunyuan server if it is up, else free hf) | hf | local.
    """
    gen = generators.generate(generators.get(backend), prompt=prompt, image=image, textured=textured, seed=seed)
    mode = "bake" if textured else style
    a = Asset.create(Path(root), {"main": gen.mesh}, budget, images={"main": gen.image}, surface_mode=mode, **overrides)
    line = a.revise("finish", part="main", tint=color) if color else a.build()
    return f"{gen.summary()} | {line}"
