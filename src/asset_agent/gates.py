"""The automatic checks that end each asset-studio stage (jobs.py). A gate reads a stage's output and returns a
JSON report: named checks with pass/fail, the value measured, what was wanted, and the stage that owns a
failure (where the job goes back to). Numbers come from the files (the asset's export stats, the GLB), never
from what the output claims about itself.

    report = gates.run("cleanup", job, {"asset": "crate"}, home)
    report["pass"], report["checks"]
"""
import json
import struct
from pathlib import Path

STUD = 0.28  # metres per stud, as in kit.py
ROUTES = ("claude", "hunyuan", "hybrid", "import")
CATEGORIES = ("prop", "building", "character", "creature", "vfx", "animation")
DESCRIPTION = ("what", "style", "colours", "size_studs", "genre", "use")
SUB_SCORES = {"shape": "shape", "surface": "texture", "fit": "cleanup", "function": "rig", "vfx": "texture"}


def budgets() -> dict:
    return json.loads((Path(__file__).parent / "budgets.json").read_text())


def check(name: str, ok: bool, value=None, want=None, owner: str | None = None, blocking: bool = True) -> dict:
    c = {"name": name, "pass": bool(ok), "value": value, "want": want}
    if owner:
        c["owner"] = owner
    if not blocking:
        c["blocking"] = False
    return c


def report(stage: str, checks: list[dict], **facts) -> dict:
    failed = [c for c in checks if not c["pass"] and c.get("blocking", True)]
    return {"stage": stage, "pass": not failed, "checks": checks, "facts": facts}


def failed(rep: dict) -> list[dict]:
    return [c for c in rep["checks"] if not c["pass"] and c.get("blocking", True)]


def describe(rep: dict) -> str:
    """One line per failed or warned check."""
    out = []
    for c in rep["checks"]:
        if c["pass"]:
            continue
        tag = "FAIL" if c.get("blocking", True) else "warn"
        want = f" (want {c['want']})" if c.get("want") is not None else ""
        out.append(f"{tag} {c['name']}: {c['value']}{want}")
    return "\n".join(out)


# ---------------------------------------------------------------- files
def glb_json(path: Path) -> dict:
    """The JSON chunk of a .glb (no buffers read)."""
    with open(path, "rb") as f:
        magic, _, _ = struct.unpack("<4sII", f.read(12))
        if magic != b"glTF":
            raise ValueError(f"{path.name} isn't a GLB")
        n, kind = struct.unpack("<I4s", f.read(8))
        return json.loads(f.read(n))


def glb_tris(g: dict) -> int:
    acc = g.get("accessors", [])
    tris = 0
    for mesh in g.get("meshes", []):
        for p in mesh.get("primitives", []):
            if p.get("mode", 4) != 4:
                continue
            i = p.get("indices")
            tris += (acc[i]["count"] if i is not None else acc[p["attributes"]["POSITION"]]["count"]) // 3
    return tris


def _asset(home: Path, name: str):
    from .asset import Asset
    root = Path(home) / name
    if not (root / "manifest.json").exists():
        return None
    return Asset(root)


def _export(a) -> dict:
    return a.cur("export")["stats"]


def _glb_of(a) -> Path:
    return a.root / "export" / "versions" / f"v{a.m['version']}" / f"{a.m['name']}.glb"


def _mesh(home: Path, out: dict, owner: str) -> tuple[list[dict], dict]:
    """Checks that an output names an existing asset or mesh file, and its facts."""
    if out.get("asset"):
        a = _asset(home, out["asset"])
        if a is None:
            return [check("asset exists", False, out["asset"], "an asset in assets/", owner)], {}
        s = _export(a)
        return [check("asset exists", True, f"{out['asset']} v{a.m['version']}")], \
            {"asset": out["asset"], "version": a.m["version"], "tris": s["tris"], "built": bool(a.m.get("build"))}
    if out.get("mesh"):
        p = Path(out["mesh"])
        if not p.is_file() or p.stat().st_size == 0:
            return [check("mesh file exists", False, str(p), "a .glb, .fbx or .obj file", owner)], {}
        facts = {"mesh": str(p.resolve())}
        if p.suffix.lower() == ".glb":
            facts["tris"] = glb_tris(glb_json(p))
        return [check("mesh file exists", p.suffix.lower() in (".glb", ".fbx", ".obj"), p.name, ".glb/.fbx/.obj", owner)], facts
    return [check("output names a mesh", False, sorted(out), "asset or mesh", owner)], {}


# ---------------------------------------------------------------- stages
def brief(job: dict, out: dict, home: Path) -> dict:
    imgs = out.get("images") or []
    d = out.get("description") or {}
    details = out.get("details") or []
    route = out.get("route")
    checks = [check("reference images", len(imgs) >= 1, len(imgs), ">= 1"),
              check("images exist", all(Path(i).is_file() for i in imgs),
                    [i for i in imgs if not Path(i).is_file()] or "all", "every path a file")]
    missing = [k for k in DESCRIPTION if not str(d.get(k, "")).strip()]
    checks.append(check("description complete", not missing, missing or "all", ", ".join(DESCRIPTION)))
    try:
        size = float(d.get("size_studs"))
    except (TypeError, ValueError):
        size = 0
    checks.append(check("size in studs", size > 0, d.get("size_studs"), "a number > 0"))
    checks.append(check("key details", 3 <= len(details) <= 5, len(details), "3-5"))
    checks.append(check("category", out.get("category") in CATEGORIES, out.get("category"), "|".join(CATEGORIES)))
    checks.append(check("route", route in ROUTES, route, "|".join(ROUTES)))
    if route == "import":
        checks.append(check("route built yet", False, "import", "VFX/animation jobs come later: use vfx_lab/animate"))
    if route == "hybrid":
        parts = out.get("parts") or {}
        checks.append(check("hybrid split", bool(parts.get("organic")) and bool(parts.get("built")), parts,
                            "parts {organic: [...], built: [...]}"))
    checks.append(check("budget", out.get("budget", "roblox_prop") in budgets(), out.get("budget"), "|".join(budgets())))
    checks.append(check("restated", len(str(out.get("restatement", "")).split()) >= 15,
                        len(str(out.get("restatement", "")).split()), ">= 15 words restating the brief and its standard"))
    return report("brief", checks)


def shape(job: dict, out: dict, home: Path) -> dict:
    route = job["brief"]["route"]
    if route == "hybrid":
        parts = out.get("parts") or {}
        checks, facts = [check("parts", len(parts) >= 2, sorted(parts), ">= 2 (organic and built)", "shape")], {"parts": {}}
        for k, v in parts.items():
            c, f = _mesh(home, {"asset": v} if (Path(home) / v / "manifest.json").exists() else {"mesh": v}, "shape")
            checks += [dict(x, name=f"{k}: {x['name']}") for x in c]
            facts["parts"][k] = f
        return report("shape", checks, **facts)
    checks, facts = _mesh(home, out, "shape")
    if route == "claude" and facts:
        checks.append(check("built in code", facts.get("built", False), facts.get("asset") or facts.get("mesh"),
                            "an asset made with build (route claude)", "shape"))
    return report("shape", checks, **facts)


def _budget(job: dict) -> dict:
    return budgets()[job["brief"].get("budget", "roblox_prop")]


def cleanup(job: dict, out: dict, home: Path) -> dict:
    a = _asset(home, out.get("asset", ""))
    if a is None:
        return report("cleanup", [check("asset exists", False, out.get("asset"),
                                        "the cleaned asset (blender export, or build)", "cleanup")])
    s, b = _export(a), _budget(job)
    longest = max(s["size_m"]) / STUD
    want = float(job["brief"]["description"]["size_studs"])
    checks = [check("tris", s["tris"] <= b["max_tris"], s["tris"], f"<= {b['max_tris']}", "cleanup"),
              check("part tris", all(t <= b["max_part_tris"] for t in s["parts"].values()),
                    max(s["parts"].values(), default=0), f"<= {b['max_part_tris']} per mesh", "cleanup"),
              check("uv", s["uv"], s["uv"], True, "cleanup"),
              check("size", abs(longest - want) <= 0.25 * want, round(longest, 1), f"{want:g} studs +-25%", "cleanup"),
              check("non-manifold edges", s["non_manifold_edges"] == 0, s["non_manifold_edges"], 0, "cleanup",
                    blocking=False)]
    return report("cleanup", checks, asset=a.m["name"], version=a.m["version"], tris=s["tris"],
                  size_studs=round(longest, 2))


def texture(job: dict, out: dict, home: Path) -> dict:
    a = _asset(home, out.get("asset", ""))
    if a is None:
        return report("texture", [check("asset exists", False, out.get("asset"), "the textured asset", "texture")])
    s, b = _export(a), _budget(job)
    flat = [k[len("surface["):-1] or "main" for k in a.m["layers"] if k.startswith("surface")
            and a.cur(k).get("stats", {}).get("mode") == "flat"]
    checks = [check("textured", s["tex"] > 0, s["tex"], "a baked or painted texture", "texture"),
              check("texture size", s["tex"] <= b["max_tex"], s["tex"], f"<= {b['max_tex']} px", "texture"),
              check("no flat surfaces", not flat, flat or "none", "every part textured", "texture")]
    return report("texture", checks, asset=a.m["name"], version=a.m["version"], tex=s["tex"])


def rig(job: dict, out: dict, home: Path) -> dict:
    a = _asset(home, out.get("asset", ""))
    if a is not None:
        glb = _glb_of(a)
        skinned = a.m.get("rig") == "r15" or (glb.exists() and bool(glb_json(glb).get("skins")))
        name = a.m["name"]
    elif out.get("mesh") and Path(out["mesh"]).suffix.lower() == ".glb" and Path(out["mesh"]).is_file():
        skinned, name = bool(glb_json(Path(out["mesh"])).get("skins")), out["mesh"]
    else:
        return report("rig", [check("rigged model exists", False, out, "asset or .glb mesh", "rig")])
    return report("rig", [check("skinned", skinned, skinned, "bones and weights (it moves)", "rig")], model=name)


def critic(job: dict, out: dict, home: Path) -> dict:
    target = float(job["brief"].get("target", 7))
    scores = {k: v for k, v in (out.get("scores") or {}).items() if isinstance(v, (int, float))}
    views = out.get("views") or []
    seen = out.get("details") or {}
    checks = [check("looked at it", bool(views) and all(Path(v).is_file() for v in views), len(views),
                    "render or preview image paths", "critic"),
              check("every key detail judged", all(d in seen for d in job["brief"]["details"]),
                    [d for d in job["brief"]["details"] if d not in seen] or "all", "details {detail: true|false}",
                    "critic")]
    missed = [d for d, ok in seen.items() if not ok]
    checks.append(check("key details present", not missed, missed or "all", "every detail true", "shape"))
    score = out.get("score")
    weakest = min(scores, key=scores.get) if scores else None
    owner = SUB_SCORES.get(weakest, "shape")
    if owner == "rig" and not job["brief"].get("moves"):
        owner = "shape"
    checks.append(check("score", isinstance(score, (int, float)) and score >= target, score, f">= {target:g}", owner))
    return report("critic", checks, scores=scores, score=score, weakest=weakest, notes=out.get("notes", ""))


def place(job: dict, out: dict, home: Path, placed: str = "") -> dict:
    return report("place", [check("placed in Studio", bool(placed) and not placed.startswith("error"),
                                  placed[:200], "studio(name) succeeded", "place")])


GATES = {"brief": brief, "shape": shape, "cleanup": cleanup, "texture": texture, "rig": rig, "critic": critic}


def run(stage: str, job: dict, out: dict, home: Path) -> dict:
    try:
        return GATES[stage](job, out, Path(home))
    except Exception as e:  # noqa: BLE001 - a broken output is a failed check, not a crash
        return report(stage, [check("output readable", False, f"{type(e).__name__}: {e}"[:200], None, stage)])
