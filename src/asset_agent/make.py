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


KIT_HELP = None


def kit_help() -> str:
    """The modelling kit's reference (kit.py's docstring), readable without Blender."""
    global KIT_HELP
    if KIT_HELP is None:
        import ast
        KIT_HELP = ast.get_docstring(ast.parse((Path(__file__).parent / "kit.py").read_text(encoding="utf-8")))
    return KIT_HELP


def build_model(root, code: str, spec: dict | None = None, budget: str | None = None,
                project: Project | None = None) -> tuple[str, Path]:
    """Claude models it in code (kit.py) -> one GLB per part -> asset pipeline. A second call with
    edited code is a new version of the same asset (each part's geometry swapped at its own size).
    Returns (one line, path of a 4-view preview to check the model against its spec)."""
    import copy
    import time
    from .blender import run_steps
    root = Path(root)
    builds = root / "build"
    n = len(list(builds.glob("v*/build.py"))) + 1 if builds.exists() else 1
    work = builds / f"v{n}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "build.py").write_text(code, encoding="utf-8")
    t0 = time.time()
    res = run_steps([{"op": "build", "code": code, "out_dir": str(work.resolve())}])[0]["stats"]
    sources = {part: work / f"{part}.glb" for part in res["parts"]}
    if (root / "manifest.json").exists():
        a = Asset(root)
        saved = (copy.deepcopy(a.m), (a.root / "finish.json").read_text())
        for part, src in sources.items():
            if part in a.m["parts"]:
                a._swap_geometry(part, {"source": src, "keep": []})
                a.m["params"]["topology"][part]["target_tris"] = None  # re-split the budget for the new shape
            else:
                a.add_part(part, src)
        for part in [p for p in a.m["parts"] if p not in sources]:
            a.drop_part(part)
    else:
        d = project.defaults(root.name, None) if project else {}
        a = Asset.create(root, sources, budget or d.get("budget") or "roblox_prop", surface_mode="auto")
        saved = None
    fin = a.finish
    for part, rgb in res["glow"].items():  # emissive parts: one flat colour, Neon in Roblox
        a.m["params"]["surface"][part].update(mode="flat", ao=0, tex_size=64)
        fin.setdefault("parts", {}).setdefault(part, {})["tint"] = rgb
    (a.root / "finish.json").write_text(json.dumps(fin, indent=2))
    a.m["build"] = {"v": n, "code": f"build/v{n}/build.py", "size_studs": res["size_studs"]}
    if spec:
        a.m["spec"] = spec
    if project:
        a.m["project"] = project.name
    a._save()
    try:
        line = a.build()
    except Exception:
        if saved:
            a.m = saved[0]
            (a.root / "finish.json").write_text(saved[1])
            a._save()
        raise
    if project:
        project.mark(root.name, status="made")
        project.handoff()
    sz = "x".join(f"{x:.1f}" for x in res["size_studs"])
    head = (f"build v{n} ({time.time() - t0:.0f}s): {sz} studs, parts "
            + ", ".join(f"{p}={t}" for p, t in res["parts"].items()))
    last = (a.m.get("ratings") or [None])[-1]
    tail = f" | last rating {last['stars']}/10: {last['note']}" if last and last.get("note") else ""
    return f"{head} | {line}{tail}", a.preview(384, "final")
