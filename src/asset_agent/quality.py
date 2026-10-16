"""The quality vault: every rating becomes a Markdown note in quality/ (an Obsidian vault in the repo), and
`export` compiles the notes into a dataset (quality/dataset/ratings.jsonl) for evaluation and training.

A note is YAML frontmatter (one `key: <json>` per line, which is valid YAML) plus the reviewer's words:

    ---
    kind: "asset"            asset | vfx | animation
    name: "master_sword"
    version: 5
    stars: 9
    verdict: "good"          good (8+) | mixed | bad (5 or less)
    category: "prop"         prop | character | creature | vfx | animation (edit freely)
    method: "build"          build (modelled in code) | generated (Hunyuan) | character | import
    share: false             true = included in the public dataset export
    ...
    ---

Notes are created and updated by `rate`, and backfilled by `python -m asset_agent quality sync`. Fields
a person edits in Obsidian (category, share, tags, failures) are kept when a note is rewritten.

Unshared notes (the default; test projects use other games' art) live in examples/private/, which git
ignores, so only `share: true` notes and their thumbnails are committed and published. `sync` moves a
note when its share flag changes.
"""
import json
import os
import time
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2] / "quality"
KEEP = ("category", "share", "tags", "failures")  # hand-edited fields survive a rewrite
# The grade beyond the overall stars (all optional; 0-10, half points allowed). A newer grade replaces these.
DIMENSIONS = {
    "shape": "form, silhouette and proportions of the model itself (the mesh)",
    "surface": "texture, colour and materials",
    "vfx": "effects: do they fit and frame the model (blank if it has none)",
    "function": "does it work in a game: scripts, animations, usability (blank if not applicable)",
    "fit": "does it belong in Roblox and in the genres it's for",
}
GRADE = ("scores", "style_score", "genres", "judged_from", "grader")
JUDGED = ("thumbnail", "studio", "review")  # what the grader looked at
THUMB = 256


def verdict(stars: float) -> str:
    return "good" if stars >= 8 else "bad" if stars <= 5 else "mixed"


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)


def read(path: Path) -> tuple[dict, str]:
    """A note's frontmatter and body."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    head, _, body = text[4:].partition("\n---\n")
    meta = {}
    for line in head.splitlines():
        k, sep, v = line.partition(":")
        if sep:
            try:
                meta[k.strip()] = json.loads(v.strip())
            except json.JSONDecodeError:
                meta[k.strip()] = v.strip()
    return meta, body


def write(path: Path, meta: dict, body: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    head = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in meta.items())
    path.write_text(f"---\n{head}\n---\n{body.rstrip()}\n", encoding="utf-8")


def clean_scores(scores: dict | None) -> dict:
    """Sub-scores by dimension, numbers 0-10; unknown dimensions are an error, blanks are dropped."""
    out = {}
    for k, v in (scores or {}).items():
        if k not in DIMENSIONS:
            raise ValueError(f"unknown dimension {k!r}: use {', '.join(DIMENSIONS)}")
        if v in (None, ""):
            continue
        v = float(v)
        if not 0 <= v <= 10:
            raise ValueError(f"{k} must be 0-10, got {v}")
        out[k] = int(v) if v == int(v) else v
    return out


def score_line(meta: dict) -> str:
    """The sub-scores as one readable line under a note's title."""
    parts = [f"{k} {meta['scores'][k]}" for k in DIMENSIONS if k in (meta.get("scores") or {})]
    if meta.get("style_score") is not None:
        parts.append(f"within its style {meta['style_score']}")
    if meta.get("genres"):
        parts.append("fits " + ", ".join(meta["genres"]))
    if meta.get("judged_from"):
        parts.append(f"judged from the {meta['judged_from']}")
    return ("**" + " · ".join(parts) + "**\n\n") if parts else ""


def _feedback(note: str) -> str:
    """The review window's "pros: ...; cons: ...; notes: ..." as sections; anything else as it is."""
    parts = {}
    for chunk in note.split("; "):
        key, sep, val = chunk.partition(": ")
        if sep and key.strip().lower() in ("pros", "cons", "notes"):
            parts[key.strip().lower()] = val.strip()
        elif parts:
            last = list(parts)[-1]
            parts[last] += "; " + chunk
        else:
            parts.setdefault("notes", "")
            parts["notes"] = (parts["notes"] + "; " + chunk).strip("; ")
    out = []
    for key, title in (("pros", "What works"), ("cons", "What's wrong"), ("notes", "Notes")):
        if parts.get(key):
            out.append(f"## {title}\n{parts[key]}\n")
    return "\n".join(out) or "## Notes\n(no notes)\n"


def _note_path(kind: str, name: str, version, shared: bool = False) -> Path:
    return VAULT / "examples" / ("" if shared else "private") / kind / f"{_slug(name)} v{version}.md"


def _existing(kind: str, name: str, version) -> Path | None:
    for shared in (False, True):
        p = _note_path(kind, name, version, shared)
        if p.exists():
            return p
    return None


def record(kind: str, name: str, version, stars: float, note: str = "", category: str | None = None,
           method: str | None = None, extra: dict | None = None, thumb: Path | None = None) -> Path:
    """Write (or rewrite) the note for one rating."""
    found = _existing(kind, name, version)
    old, _ = read(found) if found else ({}, "")
    meta = {"kind": kind, "name": name, "version": version, "stars": stars, "verdict": verdict(stars),
            "category": category or kind, "method": method or "unknown", "share": False, "tags": [],
            "failures": [], "rated": old.get("rated") or time.strftime("%Y-%m-%d")}
    extra = dict(extra or {})
    if "scores" in extra:
        extra["scores"] = clean_scores(extra["scores"])
    meta.update(extra)
    meta.update({k: old[k] for k in KEEP if k in old})
    meta.update({k: old[k] for k in GRADE if k in old and not extra.get(k)})  # a re-rating without them keeps them
    path = _note_path(kind, name, version, bool(meta.get("share")))
    img = ""
    if not (thumb and Path(thumb).exists()) and old.get("image"):
        meta["image"] = old["image"]
        img = f"![[{Path(old['image']).name}]]\n\n"
    if thumb and Path(thumb).exists() and not (kind == "store" and meta.get("share")):
        from PIL import Image
        dest = path.parent.parent / "img" / f"{_slug(name)}-v{version}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        im = Image.open(thumb).convert("RGB")
        im.thumbnail((THUMB, THUMB))
        im.save(dest, optimize=True)
        meta["image"] = f"img/{dest.name}"
        img = f"![[{dest.name}]]\n\n"
    body = f"\n# {name} v{version}: {stars}/10 ({meta['verdict']})\n\n{img}{score_line(meta)}{_feedback(note)}\n{_links(meta)}"
    write(path, meta, body)
    if found and found != path:
        _move_image(found, path, meta)
        found.unlink()
    return path


def _failure_titles() -> dict:
    return {read(p)[0].get("tag", p.stem): p.stem for p in (VAULT / "failures").glob("*.md")}


def _links(meta: dict, titles: dict | None = None) -> str:
    """The note's last line: its standard, and its failure patterns as links (edges in Obsidian's graph)."""
    titles = _failure_titles() if titles is None else titles
    out = f"Standards: [[{_standard(meta.get('category', ''))}]] · [[Rating scale]]\n"
    fails = [f"[[{titles[f]}]]" for f in meta.get("failures") or [] if f in titles]
    return out + (f"Failures: {' · '.join(fails)}\n" if fails else "")


def relink() -> int:
    """Rewrite every example's link lines from its frontmatter (after failures were tagged by hand or by a grade)."""
    titles, n = _failure_titles(), 0
    for meta, body, path in notes():
        kept = "\n".join(ln for ln in body.rstrip().splitlines() if not ln.startswith(("Standards:", "Failures:")))
        new = kept.rstrip() + "\n\n" + _links(meta, titles)
        if new.strip() != body.strip():
            write(path, meta, new)
            n += 1
    return n


def _move_image(src_note: Path, dst_note: Path, meta: dict):
    if meta.get("kind") == "store":  # other creators' thumbnails never leave the private folder
        return
    if meta.get("image"):
        a = src_note.parent.parent / meta["image"]
        b = dst_note.parent.parent / meta["image"]
        if a.exists() and a != b:
            b.parent.mkdir(parents=True, exist_ok=True)
            a.replace(b)


def _standard(category: str) -> str:
    return {"building": "Buildings", "prop": "Props", "character": "Characters", "creature": "Creatures and bosses", "vfx": "VFX",
            "animation": "Animation"}.get(category, "Props")


# ---------------------------------------------------------------- assets
def asset_facts(root: Path) -> dict:
    """What a note records about an asset folder: category, how it was made, its numbers."""
    m = json.loads((root / "manifest.json").read_text())
    if m.get("rig") == "r15":
        category = "character"
    elif m.get("budget_name") == "roblox_boss":
        category = "creature"
    else:
        category = "prop"
    method = ("character" if (root / "character.json").exists() else "build" if m.get("build")
              else "generated" if "prompt" in m else "import")
    stats = m.get("stats", {})
    extra = {"budget": m.get("budget_name"), "project": m.get("project"), "prompt": m.get("prompt"),
             "tris": stats.get("tris") or m.get("tris"), "parts": len(m.get("parts", {}))}
    return {"category": category, "method": method, "extra": {k: v for k, v in extra.items() if v is not None}}


def record_asset(home: Path, name: str, version: int, stars: float, note: str) -> Path:
    root = Path(home) / name
    f = asset_facts(root)
    m = json.loads((root / "manifest.json").read_text())
    thumb = root / "preview.png" if m.get("version") == version else None  # only the version on disk has a preview
    return record("asset", name, version, stars, note, f["category"], f["method"], f["extra"], thumb)


def record_vfx(name: str, preset: dict) -> Path | None:
    if not preset.get("score"):
        return None
    return record("vfx", name, preset.get("version", 1), preset["score"], preset.get("note") or "", "vfx",
                  "imported" if preset.get("source", {}).get("kind") == "creator_store" else "authored",
                  {"tags_preset": preset.get("tags", []), "use": preset.get("use")})


def record_animation(name: str, entry: dict, preset: dict) -> Path:
    return record("animation", name, entry["v"], entry["stars"], entry.get("note", ""), "animation", "procedural",
                  {"description": preset.get("doc") or preset.get("_doc"), "via": entry.get("via")})


# ---------------------------------------------------------------- backfill and export
def relocate() -> int:
    """Move notes whose share flag changed (in Obsidian) between examples/ and examples/private/."""
    moved = 0
    for meta, body, path in notes():
        want = _note_path(meta.get("kind", "asset"), meta.get("name", path.stem), meta.get("version", 1),
                          bool(meta.get("share")))
        if path != want:
            want.parent.mkdir(parents=True, exist_ok=True)
            write(want, meta, body)
            _move_image(path, want, meta)
            path.unlink()
            moved += 1
    return moved


def sync(home: Path) -> str:
    """Notes for every rating already in the repo and assets folder (safe to re-run)."""
    moved = relocate()
    relink()
    n = {"asset": 0, "vfx": 0, "animation": 0}
    for man in sorted(Path(home).glob("*/manifest.json")):
        m = json.loads(man.read_text())
        for r in m.get("ratings", []):
            record_asset(home, man.parent.name, r["v"], r["stars"], r.get("note", ""))
            n["asset"] += 1
    from . import vfx
    for name, p in vfx.raw_presets().items():
        if record_vfx(name, p):
            n["vfx"] += 1
    from . import anim
    for name, p in anim._library().items():
        if name.startswith("_"):
            continue
        for entry in p.get("ratings", []):
            record_animation(name, entry, p)
            n["animation"] += 1
    return (f"vault {VAULT}: " + ", ".join(f"{v} {k}" for k, v in n.items())
            + (f"; moved {moved} note(s) for their share flag" if moved else ""))


def vaults() -> list[Path]:
    """quality/ plus extra vaults named in ASSET_AGENT_VAULTS (folders separated by os.pathsep, relative to the
    repo): e.g. a private vault of reference assets kept out of this repo. Each holds notes in examples/."""
    extra = [Path(p) if Path(p).is_absolute() else VAULT.parent / p
             for p in os.environ.get("ASSET_AGENT_VAULTS", "").split(os.pathsep) if p.strip()]
    return [VAULT] + [v for v in extra if (v / "examples").is_dir()]


def _ref(path: Path) -> str:
    """A note's path for datasets: relative to its vault (extra vaults keep their folder name in front)."""
    for v in vaults():
        if path.is_relative_to(v):
            rel = path.relative_to(v)
            return str(rel if v == VAULT else Path(v.name) / rel).replace("\\", "/")
    return str(path).replace("\\", "/")


def notes() -> list[tuple[dict, str, Path]]:
    """Every rated note: quality/examples/ and each extra vault's examples/."""
    return [(*read(p), p) for v in vaults() for p in sorted((v / "examples").rglob("*.md"))]


def _sections(body: str) -> dict:
    """A note's feedback as {"works", "wrong", "notes"} text."""
    keys = {"What works": "works", "What's wrong": "wrong", "Notes": "notes"}
    out, cur = {}, None
    for line in body.splitlines():
        if line.startswith("## "):
            cur = keys.get(line[3:].strip())
            continue
        if cur and line.strip() and not line.startswith(("Standards:", "Failures:", "![[", "**")):
            out[cur] = (out.get(cur, "") + " " + line.strip()).strip()
    return out


def export(include_private: bool = False) -> str:
    """quality/dataset/ratings.jsonl: one record per shared note, for publishing. include_private writes
    every note to ratings.private.jsonl instead (git-ignored, for local evaluation)."""
    out = VAULT / "dataset" / ("ratings.private.jsonl" if include_private else "ratings.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for meta, body, path in notes():
        if not (meta.get("share") or include_private):
            continue
        row = {k: v for k, v in meta.items() if v not in (None, "", [])}
        row.update(_sections(body), note=_ref(path))
        rows.append(row)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return f"{len(rows)} of {len(notes())} notes -> {out}" + ("" if include_private else " (share: true only)")


def _clip(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def brief(category: str, top: int = 5, examples: int = 3) -> str:
    """A fixed-size digest of the vault for one category (about 300 tokens however many notes there are):
    its most common failures with their fixes, and the best and worst examples in a line each."""
    mine = [(m, b) for m, b, _ in notes() if m.get("category") == category and isinstance(m.get("stars"), (int, float))]
    counts = {}
    for m, _ in mine:
        for f in m.get("failures") or []:
            counts[f] = counts.get(f, 0) + 1
    fixes = {}
    for p in sorted((VAULT / "failures").glob("*.md")):
        meta, body = read(p)
        para = next((p for p in body.split("\n\n") if p.strip().startswith("**Fix.**")), "")
        fix = " ".join(para.strip()[len("**Fix.**"):].split())
        fixes[meta.get("tag", p.stem)] = (p.stem, fix.strip())
    lines = [f"# {category}: {len(mine)} rated examples (standard: {_standard(category)})"]
    worst = sorted(counts.items(), key=lambda kv: -kv[1])[:top]
    if worst:
        lines.append("Common failures:")
        for tag, c in worst:
            title, fix = fixes.get(tag, (tag, ""))
            lines.append(f"- {title} (x{c}): {_clip(fix, 140)}")

    def line(m, b, key):
        s = _sections(b)
        why = s.get(key) or s.get("notes") or ""
        by = " (claude)" if m.get("grader") == "claude" else ""
        return f"- {m.get('name')} v{m.get('version')} {m['stars']}/10{by}: {_clip(why, 110)}"
    ranked = sorted(mine, key=lambda mb: -mb[0]["stars"])
    best = [mb for mb in ranked if mb[0]["stars"] >= 8][:examples]
    bad = [mb for mb in reversed(ranked) if mb[0]["stars"] <= 5][:examples]
    if best:
        lines += ["Best:"] + [line(m, b, "works") for m, b in best]
    if bad:
        lines += ["Worst:"] + [line(m, b, "wrong") for m, b in bad]
    return "\n".join(lines)


def _group(meta: dict):
    """Notes that compete with each other: one store search, or the versions of one of our assets."""
    if meta.get("kind") == "store":
        return ("store", meta.get("query"), meta.get("category"))
    return (meta.get("kind"), meta.get("name"))


def pairs(include_private: bool = False, margin: float = 1) -> str:
    """quality/dataset/pairs.jsonl: preference pairs for reward-model training. Within a group (a store search,
    or an asset's versions) and for one grader, every two notes whose overall stars differ by `margin` or more
    make a pair, as do their sub-scores on each dimension both have."""
    out = VAULT / "dataset" / ("pairs.private.jsonl" if include_private else "pairs.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    groups = {}
    for meta, body, path in notes():
        if not isinstance(meta.get("stars"), (int, float)) or not (meta.get("share") or include_private):
            continue
        ref = _ref(path)
        groups.setdefault((_group(meta), meta.get("grader", "human")), []).append((meta, ref))
    rows = []
    for (group, grader), items in groups.items():
        for i, (a, ra) in enumerate(items):
            for b, rb in items[i + 1:]:
                dims = [("overall", a["stars"], b["stars"])] + [
                    (d, (a.get("scores") or {})[d], (b.get("scores") or {})[d]) for d in DIMENSIONS
                    if d in (a.get("scores") or {}) and d in (b.get("scores") or {})]
                for dim, sa, sb in dims:
                    if abs(sa - sb) >= margin:
                        win, lose = (ra, rb) if sa > sb else (rb, ra)
                        rows.append({"dimension": dim, "chosen": win, "rejected": lose, "margin": abs(sa - sb),
                                     "group": [g for g in group if g], "grader": grader})
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return f"{len(rows)} pairs -> {out}"


def summary() -> str:
    """Counts by kind and verdict, and the most common failure tags."""
    by, fails = {}, {}
    for meta, _, _ in notes():
        k = (meta.get("kind"), meta.get("verdict"))
        by[k] = by.get(k, 0) + 1
        for f in meta.get("failures") or []:
            fails[f] = fails.get(f, 0) + 1
    lines = [f"{k[0]} {k[1]}: {v}" for k, v in sorted(by.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1])))]
    if fails:
        lines.append("failures: " + ", ".join(f"{f} x{c}" for f, c in sorted(fails.items(), key=lambda kv: -kv[1])))
    return "\n".join(lines) or "no notes yet"
