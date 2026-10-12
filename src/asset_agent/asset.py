"""Modular asset folder: layers, parts, versions and dirty-layer rebuild.

Layer graph (per part unless noted):
    geometry -> topology -> uv -> surface -> export(global)
    geometry ----------------------^ (bake source)
    geometry -> collision -> export
    finish(global, params only) -> export

Each layer version has a *key* (hash of its params + its inputs' keys, plus the source file
hash for geometry) and a content *hash* of its output file. A layer rebuilds only when its key
changes; an older version with the same key is restored instead of rebuilt (so rollback is exact).
"""
import copy
import hashlib
import json
import shutil
from pathlib import Path

from .blender import BlenderError, run_steps

BUDGETS = json.loads(Path(__file__).with_name("budgets.json").read_text())
PART_LAYERS = ["geometry", "topology", "collision", "uv", "surface"]
DEPS = {"geometry": [], "topology": ["geometry"], "collision": ["geometry"],
        "uv": ["topology"], "surface": ["uv", "geometry"]}
DEFAULT_FINISH = {"roughness": 0.8, "metallic": 0.0, "tint": [1.0, 1.0, 1.0], "parts": {}}
# default per-part colours for flat (untextured) surfaces; changing them is a finish-only revision
PALETTE = [[0.80, 0.52, 0.30], [0.35, 0.55, 0.80], [0.45, 0.70, 0.35], [0.85, 0.75, 0.35], [0.70, 0.40, 0.65]]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


# Bump when worker.py output changes, so existing layers rebuild instead of being reused.
PIPELINE_VERSION = 2


def _key(*parts) -> str:
    return _sha(json.dumps([PIPELINE_VERSION, *parts], sort_keys=True).encode())


def _filehash(path: Path) -> str:
    return _sha(path.read_bytes())


def lk(kind: str, part: str | None = None) -> str:
    return f"{kind}[{part}]" if part else kind


class Asset:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()  # Blender resolves relative image paths differently
        self.m = json.loads((self.root / "manifest.json").read_text())

    # ------------------------------------------------------------ create / io

    @classmethod
    def create(cls, root, sources: dict[str, str | Path], budget: str = "roblox_prop",
               images: dict[str, str | Path] | None = None, surface_mode: str = "auto", **overrides) -> "Asset":
        """Create an asset folder from one source mesh per named part.

        images: optional reference image per part (used by surface_mode "project").
        surface_mode: auto | bake | project | flat (see worker.op_surface).
        """
        root = Path(root)
        if (root / "manifest.json").exists():
            raise FileExistsError(f"{root} already has a manifest")
        (root / "source").mkdir(parents=True, exist_ok=True)
        b = {**BUDGETS[budget], **overrides}
        m = {"name": root.name, "budget_name": budget, "budget": b, "version": 0, "parts": {},
             "params": {"geometry": {}, "topology": {}, "collision": {}, "uv": {}, "surface": {},
                        "export": {"target": b["target"], "scale_to": None}},
             "layers": {}, "history": []}
        (root / "manifest.json").write_text(json.dumps(m))
        (root / "finish.json").write_text(json.dumps(DEFAULT_FINISH, indent=2))
        a = cls(root)
        fin = DEFAULT_FINISH | {"parts": {}}
        for i, (part, src) in enumerate(sources.items()):
            a.m["parts"][part] = {}
            a._set_source(part, src)
            a.m["params"]["geometry"][part] = {}
            a.m["params"]["topology"][part] = {"target_tris": None}  # resolved after first geometry build
            a.m["params"]["collision"][part] = {"max_tris": b["collision_tris"]}
            a.m["params"]["uv"][part] = {"angle": 66, "margin": 0.02}
            a.m["params"]["surface"][part] = {"tex_size": b["tex_size"], "mode": surface_mode, "image": None}
            if images and images.get(part):
                a._set_image(part, images[part])
            if surface_mode == "flat":
                fin["parts"][part] = {"tint": PALETTE[i % len(PALETTE)]}
        (root / "finish.json").write_text(json.dumps(fin, indent=2))
        a._save()
        return a

    def _set_source(self, part, src):
        src = Path(src)
        dst = self.root / "source" / f"{part}-{_filehash(src)[:8]}{src.suffix.lower()}"
        if not dst.exists():
            shutil.copy(src, dst)
        self.m["parts"][part]["source"] = dst.relative_to(self.root).as_posix()

    def _set_image(self, part, img):
        img = Path(img)
        dst = self.root / "source" / f"{part}-ref-{_filehash(img)[:8]}{img.suffix.lower()}"
        if not dst.exists():
            shutil.copy(img, dst)
        self.m["params"]["surface"][part]["image"] = dst.relative_to(self.root).as_posix()

    def _save(self):
        (self.root / "manifest.json").write_text(json.dumps(self.m, indent=1))

    @property
    def finish(self) -> dict:
        return json.loads((self.root / "finish.json").read_text())

    def cur(self, layer: str) -> dict:
        rec = self.m["layers"][layer]
        return rec["versions"][str(rec["current"])]

    def path(self, rel: str) -> Path:
        return self.root / rel

    # ------------------------------------------------------------ planning

    def _plan(self, layer, kind, params, inputs, files, step, cacheable=True):
        """Decide whether `layer` must rebuild. Returns a worker step or None."""
        key = _key(kind, params, inputs)
        rec = self.m["layers"].setdefault(layer, {"current": 0, "versions": {}})
        cur = rec["versions"].get(str(rec["current"]))
        if cur and cur["key"] == key:
            self._reused += 1
            return None
        if cacheable:
            for v, ver in rec["versions"].items():
                if ver["key"] == key and all(self.path(f).exists() for f in ver["files"].values()):
                    rec["current"] = int(v)
                    self._restored.append(layer)
                    return None
        v = max(map(int, rec["versions"]), default=0) + 1
        files = {k: f.format(v=v) for k, f in files.items()}
        ver = {"key": key, "inputs": inputs, "params": copy.deepcopy(params), "files": files, "hash": None, "stats": {}}
        if not cacheable:
            rec["versions"] = {}
        rec["versions"][str(v)] = ver
        rec["current"] = v
        self._rebuilt.append(layer)
        if step is None:
            return None
        step = step(files)
        step["_layer"] = layer
        return step

    def _plan_part(self, kind, part):
        params = self.m["params"][kind][part]
        name = lk(kind, part)
        if kind == "geometry":
            src = self.m["parts"][part]["source"]
            inputs = [_filehash(self.path(src))]
            return self._plan(name, kind, params, inputs, {"glb": f"geometry/{part}@v{{v}}.glb"},
                              lambda f: {"op": "geometry", "part": part, "src": str(self.path(src)),
                                         "out": str(self.path(f["glb"])), "params": params})
        if kind == "surface":
            src_layer, src_ver = lk("geometry", part), None
            if params.get("from_version"):  # rolled back onto newer UVs: transfer the old bake
                src_layer, src_ver = name, params["from_version"]
            src = self.m["layers"][src_layer]["versions"][str(src_ver)] if src_ver else self.cur(src_layer)
            inputs = [self.cur(lk("uv", part))["key"], src["key"]]
            return self._plan(name, kind, params, inputs,
                              {"glb": f"surface/{part}@v{{v}}.glb", "png": f"surface/{part}@v{{v}}.png"},
                              lambda f: {"op": "surface", "part": part, "src": str(self.path(src["files"]["glb"])),
                                         "target": str(self.path(self.cur(lk("uv", part))["files"]["glb"])),
                                         "out": str(self.path(f["glb"])), "png": str(self.path(f["png"])),
                                         "image": str(self.path(params["image"])) if params.get("image") else None,
                                         "transfer": bool(params.get("from_version")),
                                         "params": params})
        dep = lk(DEPS[kind][0], part)
        inputs = [self.cur(dep)["key"]]
        return self._plan(name, kind, params, inputs, {"glb": f"{kind}/{part}@v{{v}}.glb"},
                          lambda f: {"op": kind, "part": part, "src": str(self.path(self.cur(dep)["files"]["glb"])),
                                     "out": str(self.path(f["glb"])), "params": params})

    def _plan_finish_export(self):
        fin = self.finish
        self._plan("finish", "finish", fin, [], {}, None)
        parts = self.m["parts"]
        inputs = [self.cur("finish")["key"], self.m["budget"]] + \
                 [self.cur(lk(k, p))["key"] for p in parts for k in ("surface", "collision")]
        name = self.m["name"]
        files = {"dir": "export", "main": f"export/{name}.{'glb' if self.m['params']['export']['target'] != 'unity' else 'fbx'}"}

        def step(f):
            return {"op": "export", "name": name, "out_dir": str(self.path("export")),
                    "params": self.m["params"]["export"], "budget": self.m["budget"],
                    "parts": {p: {"surface": str(self.path(self.cur(lk("surface", p))["files"]["glb"])),
                                  "finish": {**{k: v for k, v in fin.items() if k != "parts"},
                                             **fin["parts"].get(p, {})}} for p in parts},
                    "collisions": {p: str(self.path(self.cur(lk("collision", p))["files"]["glb"])) for p in parts}}
        return self._plan("export", "export", self.m["params"]["export"], inputs, files, step, cacheable=False)

    def _run(self, steps):
        steps = [s for s in steps if s]
        if not steps:
            return
        layers = [s.pop("_layer") for s in steps]
        for layer, res in zip(layers, run_steps(steps)):
            ver = self.cur(layer)
            ver["stats"] = res["stats"]
            if "glb" in ver["files"] or "main" in ver["files"]:
                ver["hash"] = _filehash(self.path(ver["files"].get("glb") or ver["files"]["main"]))

    def _resolve_targets(self):
        """First build: split the budget's tri count across parts by their geometry tri share."""
        parts = self.m["parts"]
        todo = [p for p in parts if self.m["params"]["topology"][p]["target_tris"] is None]
        if not todo:
            return
        geo = {p: self.cur(lk("geometry", p))["stats"]["tris"] for p in parts}
        total = sum(geo.values()) or 1
        b = self.m["budget"]
        for p in todo:
            self.m["params"]["topology"][p]["target_tris"] = min(
                b["max_part_tris"], max(12, int(b["max_tris"] * geo[p] / total)))

    # ------------------------------------------------------------ public API

    def build(self) -> str:
        """Rebuild out-of-date layers. Returns a one-line diff + validation summary."""
        self._rebuilt, self._restored, self._reused = [], [], 0
        before = self.m["layers"].get("export") and self.cur("export")["stats"].get("tris")
        parts = list(self.m["parts"])
        try:
            self._run([self._plan_part("geometry", p) for p in parts])
            self._resolve_targets()
            self._run([self._plan_part(k, p) for k in ("topology", "collision", "uv", "surface") for p in parts]
                      + [self._plan_finish_export()])
        except BlenderError:
            self.m = json.loads((self.root / "manifest.json").read_text())  # discard the plan
            raise
        exp = self.cur("export")["stats"]
        if self._rebuilt or self._restored:
            self.m["version"] += 1
            line = f"v{self.m['version']}: rebuilt {', '.join(self._rebuilt) or 'nothing'}"
            if self._restored:
                line += f"; restored {', '.join(self._restored)}"
            line += f"; reused {self._reused} layers; tris {before or 0}->{exp['tris']}"
            self.m["history"].append(line)
        else:
            line = f"v{self.m['version']}: up to date"
        self._save()
        return f"{line} | {self.summary()}"

    def summary(self) -> str:
        s = self.cur("export")["stats"]
        status = "ok" if s["ok"] else "FAIL " + "; ".join(s["fails"])
        sz = "x".join(f"{x:g}" for x in s["size_m"])
        return (f"{status} tris={s['tris']}/{s['max_tris']} parts={len(s['parts'])} tex={s['tex']} "
                f"uv={'yes' if s['uv'] else 'no'} nonmanifold={s['non_manifold_edges']} size={sz}m "
                f"-> export/{', '.join(s['files'])}")

    def revise(self, layer: str, part: str | None = None, **change) -> str:
        """Change one layer's params (optionally for one part) and rebuild what's out of date.

        finish:    roughness, metallic, tint
        geometry:  source (new mesh file) or prompt/image (regenerate), keep ["scale","texture"],
                   stretch, scale [x,y,z], pivot, offset, merge_distance
        topology:  target_tris
        uv:        angle, margin
        surface:   mode (auto|bake|project|flat), image (reference image path), ao (0-1), tex_size
        collision: max_tris
        export:    scale_to (metres, longest side), target (roblox|godot|unity)
        """
        if layer == "finish":
            fin = self.finish
            (fin["parts"].setdefault(part, {}) if part else fin).update(change)
            (self.root / "finish.json").write_text(json.dumps(fin, indent=2))
        elif layer == "export":
            self.m["params"]["export"].update(change)
        elif layer in PART_LAYERS:
            for p in [part] if part else list(self.m["parts"]):
                if p not in self.m["parts"]:
                    raise KeyError(f"no part {p!r}; parts: {', '.join(self.m['parts'])}")
                ch = dict(change)
                if layer == "geometry":
                    self._swap_geometry(p, ch)
                if layer == "surface":
                    self.m["params"]["surface"][p].pop("from_version", None)
                    if "image" in ch:
                        self._set_image(p, ch.pop("image"))
                self.m["params"][layer][p].update(ch)
        else:
            raise KeyError(f"unknown layer {layer!r}")
        self._save()
        return self.build()

    def _swap_geometry(self, part, ch):
        """New shape for a part from `source` (a mesh file) or a fresh generation (`prompt` and/or
        `image`, optional `backend`). keep: "scale" fits it to the old shape's box ("stretch": true
        matches every axis, else proportions are kept); "texture" bakes the old texture onto it.
        Default keeps both. Pops the swap keys from ch."""
        keep = ch.pop("keep", ["scale", "texture"])
        stretch = ch.pop("stretch", False)
        backend = ch.pop("backend", "auto")
        prompt, image = ch.pop("prompt", None), ch.pop("image", None)
        if prompt or image:
            from . import generators
            gen = generators.generate(generators.get(backend), prompt=prompt, image=image)
            ch["source"] = gen.mesh
            if "texture" not in keep and gen.image:
                self._set_image(part, gen.image)
        if "source" not in ch:
            return
        geo = self.m["params"]["geometry"][part]
        if "scale" in keep and lk("geometry", part) in self.m["layers"]:
            if geo.get("fit") and not (geo.get("scale") or geo.get("offset")):
                lo, hi = geo["fit"]["lo"], geo["fit"]["hi"]  # swapped before: keep the original box
            else:
                lo, hi = self._bbox(part)  # already includes the old scale/offset, so drop them
            for k in ("scale", "offset", "fit"):
                geo.pop(k, None)
            ch["fit"] = {"lo": lo, "hi": hi, "mode": "stretch" if stretch else "uniform"}
        else:
            geo.pop("fit", None)
        surf = self.m["params"]["surface"][part]
        if "texture" in keep and lk("surface", part) in self.m["layers"]:
            surf.setdefault("from_version", self.m["layers"][lk("surface", part)]["current"])
        else:
            surf.pop("from_version", None)
        self._set_source(part, ch.pop("source"))

    def _bbox(self, part):
        ver = self.cur(lk("geometry", part))
        if "bbox" not in ver["stats"]:  # built before bboxes were recorded
            ver["stats"]["bbox"] = run_steps([{"op": "measure", "src": str(self.path(ver["files"]["glb"]))}])[0]["stats"]["bbox"]
        return ver["stats"]["bbox"]

    def rollback(self, layer: str, version: int, part: str | None = None) -> str:
        """Restore one layer's params from an earlier version and rebuild downstream.

        If the layer's inputs are unchanged since that version, the stored output is restored
        exactly (same hash). A surface rolled back onto newer UVs is re-baked from the old texture.
        """
        name = lk(layer, part)
        ver = self.m["layers"][name]["versions"].get(str(version))
        if ver is None:
            raise KeyError(f"{name} has no v{version}; have {', '.join(self.m['layers'][name]['versions'])}")
        params = copy.deepcopy(ver["params"])
        if layer == "finish":
            (self.root / "finish.json").write_text(json.dumps(params, indent=2))
        elif layer == "export":
            self.m["params"]["export"] = params
        else:
            if layer == "surface" and ver["inputs"][0] != self.cur(lk("uv", part))["key"]:
                params["from_version"] = version
            self.m["params"][layer][part] = params
        self._save()
        return self.build()

    def tints(self) -> dict[str, list[float]]:
        """Each part's finish tint (the part's own, else the asset's)."""
        fin = self.finish
        return {p: fin["parts"].get(p, {}).get("tint") or fin.get("tint") or [1, 1, 1] for p in self.m["parts"]}

    def preview(self, size: int = 256, layer: str = "final") -> Path:
        """Render a 2x2 tile. Returns the PNG path. layer:
        final     - the export, textured, from front, right, back, 3/4
        geometry  - the cleaned source shape in clay, 4 views
        topology  - the game mesh with its edges, 4 views
        colour    - each face in one flat colour from its texture x tint (the palette), 4 views
        texture   - the baked texture on the game mesh (before finish tint), 4 views
        breakdown - geometry | topology / colour | texture, each from 3/4
        """
        layer = {"color": "colour"}.get(layer, layer)
        parts = list(self.m["parts"])

        def files(kind):
            return [str(self.path(self.cur(lk(kind, p))["files"]["glb"])) for p in parts]

        shades = {"geometry": ("geometry", "clay"), "topology": ("topology", "wire"),
                  "colour": ("surface", "colour"), "texture": ("surface", "texture")}
        step = {"op": "preview", "size": size, "out": str(self.root / f"preview{'' if layer == 'final' else '-' + layer}.png")}
        if layer == "final":
            step["files"] = [str(self.path(self.cur("export")["files"]["main"]))]
        elif layer in shades:
            kind, shade = shades[layer]
            step["panels"] = [{"files": files(kind), "shade": shade, "view": i} for i in range(4)]
        elif layer == "breakdown":
            step["panels"] = [{"files": files(k), "shade": sh, "view": 3} for k, sh in shades.values()]
        else:
            raise KeyError(f"unknown preview layer {layer!r}; have final, breakdown, {', '.join(shades)}")
        tints = self.tints()
        step["tints"] = {f: tints[p] for p, f in zip(parts, files("surface"))}
        run_steps([step])
        return Path(step["out"])

    def params_snapshot(self) -> dict:
        """The settings ratings learn from (first part for per-part ones)."""
        p = next(iter(self.m["parts"]))
        fin = self.finish
        surf = self.m["params"]["surface"][p]
        return {"target_tris": self.m["params"]["topology"][p]["target_tris"],
                "tex_size": surf.get("tex_size"), "ao": surf.get("ao"),
                "roughness": fin.get("roughness"), "metallic": fin.get("metallic"),
                "style": surf.get("mode"), "budget": self.m.get("budget_name")}

    def history(self) -> str:
        cur = ", ".join(f"{k}@v{r['current']}" for k, r in self.m["layers"].items())
        return "\n".join(self.m["history"] + [f"current: {cur}"])
