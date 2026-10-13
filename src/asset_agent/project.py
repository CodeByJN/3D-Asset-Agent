"""Projects: one per game. A style guide that every asset made for the game inherits, a roster of
planned assets, and 1-10 ratings that tune the defaults so later assets need fewer revisions.

Stored in $ASSET_AGENT_HOME/_projects/<name>/: project.json, refs/ (reference images), ratings.jsonl.
"""
import json
import shutil
import time
from pathlib import Path

# Params the ratings learn from: where each lives in an asset, and how to round the learned value.
LEARNED = {"target_tris": ("topology", 50), "tex_size": ("surface", None), "ao": ("surface", 0.05),
           "roughness": ("finish", 0.05), "metallic": ("finish", 0.05)}
GOOD, BAD = 7, 4  # ratings >= GOOD teach the defaults; notes on ratings <= BAD become "avoid"
# Every project is a private test place. It may use reference art, characters and assets from other
# games and IP as reference; rights are the game maker's business.
PRIVATE = "may use other games' assets and IP as reference"

STYLE_KEYS = ("brief", "budget", "style", "palette", "sizes", "target_tris", "tex_size", "ao",
              "roughness", "metallic")


def projects_dir(home: Path) -> Path:
    return Path(home) / "_projects"


class Project:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.name = self.root.name
        f = self.root / "project.json"
        self.d = json.loads(f.read_text()) if f.exists() else {
            "name": self.name, "brief": "", "budget": "roblox_prop", "style": "project", "palette": [],
            "sizes": {}, "references": [], "assets": {}, "learned": {}}

    @classmethod
    def open(cls, home: Path, name: str, create: bool = False) -> "Project":
        p = cls(projects_dir(home) / name)
        if not create and not (p.root / "project.json").exists():
            have = sorted(x.parent.name for x in projects_dir(home).glob("*/project.json"))
            raise KeyError(f"no project {name!r}; have: {', '.join(have) or 'none'} (plan creates one)")
        return p

    def save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "project.json").write_text(json.dumps(self.d, indent=1))

    # ------------------------------------------------------------ planning

    def update(self, references: list[str] | None = None, assets: dict | list | None = None, **style) -> None:
        """Merge style keys; copy reference images in; add/replace roster entries.

        assets: {name: prompt} or ["name: prompt", "name"]. A None style value clears that key.
        """
        for k, v in style.items():
            if k not in STYLE_KEYS:
                raise KeyError(f"unknown style key {k!r}; have {', '.join(STYLE_KEYS)}")
            if v is None:
                self.d.pop(k, None)
            elif k == "sizes":
                self.d.setdefault("sizes", {}).update(v)
            else:
                self.d[k] = v
        for ref in references or []:
            src = Path(ref)
            if not src.exists():
                raise FileNotFoundError(f"reference {ref} not found")
            dst = self.root / "refs" / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.resolve() != dst.resolve():
                shutil.copy(src, dst)
            rel = dst.relative_to(self.root).as_posix()
            if rel not in self.d["references"]:
                self.d["references"].append(rel)
        if isinstance(assets, list):
            assets = dict((x.split(":", 1) + [""])[:2] for x in assets)
        for name, prompt in (assets or {}).items():
            entry = self.d["assets"].setdefault(name.strip(), {"status": "planned"})
            if prompt and prompt.strip():
                entry["prompt"] = prompt.strip()
        self.save()

    def defaults(self, name: str, prompt: str | None) -> dict:
        """What make_asset should use for `name`: the roster prompt, the brief appended, and the
        style guide's settings (explicit settings win over learned ones)."""
        d, learned = self.d, self.d.get("learned", {})
        prompt = prompt or d["assets"].get(name, {}).get("prompt")
        out = {"prompt": f"{prompt}, {d['brief']}" if prompt and d.get("brief") else prompt,
               "budget": d.get("budget"), "style": d.get("style")}
        for k in LEARNED:
            if d.get(k) is not None or learned.get(k) is not None:
                out[k] = d[k] if d.get(k) is not None else learned[k]
        text = f"{name} {prompt or ''}".lower().replace("_", " ")
        for word, metres in sorted(d.get("sizes", {}).items(), key=lambda kv: -len(kv[0])):
            if word.lower() in text:
                out["scale_to"] = metres
                break
        return out

    def snap(self, color: list[float] | None) -> list[float] | None:
        """Nearest palette colour (keeps a game's colours consistent). No palette: unchanged."""
        pal = self.d.get("palette") or []
        if not pal:
            return color
        if color is None:
            return pal[0]
        return min(pal, key=lambda c: sum((a - b) ** 2 for a, b in zip(c, color)))

    def mark(self, asset: str, **kv):
        self.d["assets"].setdefault(asset, {}).update(kv)
        self.save()

    # ------------------------------------------------------------ ratings

    def ratings(self) -> list[dict]:
        f = self.root / "ratings.jsonl"
        return [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []

    def rate(self, asset: str, version: int, stars: int, note: str, params: dict, prompt: str | None) -> str:
        if not 1 <= stars <= 10:
            raise ValueError("stars must be 1-10")
        rec = {"t": int(time.time()), "asset": asset, "v": version, "stars": stars, "note": note,
               "prompt": prompt, "params": params}
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.root / "ratings.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        before = dict(self.d.get("learned", {}))
        self.d["learned"] = self._learn()
        self.d["assets"].setdefault(asset, {}).update(status="made", stars=stars)
        self.save()
        rs = self.ratings()
        avg = sum(r["stars"] for r in rs) / len(rs)
        changed = [f"{k}->{v}" for k, v in self.d["learned"].items() if before.get(k) != v]
        line = f"rated {asset} v{version} {stars}/10 | {self.name}: {len(rs)} ratings avg {avg:.1f}"
        if len(rs) >= 4:
            half = len(rs) // 2
            old, new = rs[:half], rs[half:]
            line += f" trend {sum(r['stars'] for r in new) / len(new) - sum(r['stars'] for r in old) / len(old):+.1f}"
        if changed:
            line += f" | learned {', '.join(changed)}"
        return line

    def _learn(self) -> dict:
        """Star-weighted average of each param over the well-rated generations (needs 2+)."""
        good = [r for r in self.ratings() if r["stars"] >= GOOD]
        out = {}
        for k, (_, step) in LEARNED.items():
            vals = [(r["params"][k], r["stars"] - GOOD + 1) for r in good if r["params"].get(k) is not None]
            if len(vals) < 2:
                continue
            mean = sum(v * w for v, w in vals) / sum(w for _, w in vals)
            if step is None:  # tex_size: the most-weighted value, not an average
                out[k] = max({v for v, _ in vals}, key=lambda x: sum(w for v, w in vals if v == x))
            else:
                out[k] = round(round(mean / step) * step, 3) if step < 1 else int(round(mean / step) * step)
        return out

    # ------------------------------------------------------------ handoff

    def handoff(self) -> Path:
        """Write HANDOFF.md: everything a fresh conversation needs to carry on this game's assets
        (style guide, ratings, and per asset its spec, build code, version and feedback). Kept up to
        date on every build and rating, so starting a new chat costs one file read, not a replay."""
        home = self.root.parent.parent
        lines = ["# Handoff: " + self.name, "", "Read this first in a new conversation, then carry on.", "",
                 "## Style guide and ratings", "", "```", self.summary(), "```", ""]
        for m in sorted(home.glob("*/manifest.json")):
            d = json.loads(m.read_text())
            if d.get("project") != self.name:
                continue
            lines += [f"## {m.parent.name} (v{d.get('version')})", ""]
            if d.get("spec"):
                lines += [f"- **{k}:** {v}" for k, v in d["spec"].items()]
            if d.get("build"):
                lines.append(f"- **build code:** {(m.parent / d['build']['code']).as_posix()} (edit it and call build again)")
            elif d.get("prompt"):
                lines.append(f"- **prompt:** {d['prompt']}")
            for r in d.get("ratings", [])[-3:]:
                lines.append(f"- rated {r['stars']}/10 on v{r['v']}: {r.get('note') or '(no note)'}")
            lines.append("")
        f = self.root / "HANDOFF.md"
        self.root.mkdir(parents=True, exist_ok=True)
        f.write_text("\n".join(lines), encoding="utf-8")
        return f

    # ------------------------------------------------------------ summary

    def summary(self) -> str:
        """Compact style guide + roster + what the ratings say. Read before making assets."""
        d = self.d
        style = " ".join(f"{k}={d[k]}" for k in ("budget", "style", "target_tris", "tex_size", "ao", "roughness",
                                                   "metallic") if d.get(k) is not None)
        lines = [f"project {self.name} (private: {PRIVATE}): brief {d.get('brief') or '(none)'!r} | {style}"]
        extra = []
        if d.get("palette"):
            extra.append("palette " + " ".join("[" + ",".join(f"{c:g}" for c in col) + "]" for col in d["palette"]))
        if d.get("sizes"):
            extra.append("sizes " + " ".join(f"{k}={v}m" for k, v in d["sizes"].items()))
        if d.get("references"):
            extra.append("refs " + " ".join(str(self.root / r) for r in d["references"]))
        if extra:
            lines.append(" | ".join(extra))
        if d["assets"]:
            made = sum(1 for a in d["assets"].values() if a.get("status") == "made")
            lines.append(f"roster {made}/{len(d['assets'])} made: " + ", ".join(
                f"{n}({a.get('status', 'planned')}{' ' + str(a['stars']) + '/10' if a.get('stars') else ''})"
                for n, a in d["assets"].items()))
        rs = self.ratings()
        if rs:
            avg = sum(r["stars"] for r in rs) / len(rs)
            learned = " ".join(f"{k}={v}" for k, v in d.get("learned", {}).items()) or "nothing yet"
            lines.append(f"ratings {len(rs)} avg {avg:.1f} | learned {learned}")
            liked = [f"{r['note']!r}({r['stars']})" for r in rs if r["stars"] >= GOOD and r["note"]][-5:]
            avoid = [f"{r['note']!r}({r['stars']})" for r in rs if r["stars"] <= BAD and r["note"]][-5:]
            if liked:
                lines.append("liked: " + "; ".join(liked))
            if avoid:
                lines.append("avoid: " + "; ".join(avoid))
        return "\n".join(lines)
