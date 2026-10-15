"""Creator Store models graded into the quality vault: real examples of good and bad Roblox assets.

search(query, n) reads Roblox's public Creator Store API (search, item details, thumbnails): each model's
triangles, mesh parts, scripts, votes and a 420 px thumbnail. It writes a contact sheet to look at and a pending
list; grade(...) then turns a look into a vault note (kind "store", grader "claude" unless a person graded it).

Notes link to the item by id and URL. Thumbnails are other creators' images, so they stay in the git-ignored
private folder; a shared note publishes the id, the facts and the grade, never the picture.
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import quality

API = "https://apis.roblox.com/toolbox-service/v1"
UA = {"User-Agent": "asset-agent/0.1 (quality vault; creator store grading)"}
CATEGORY = {"3d__characters": "character", "characters": "character", "visual-effects": "vfx",
            "animation": "animation", "creatures": "creature"}


def _get(url: str) -> bytes:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def _dir() -> Path:
    return quality.VAULT / "examples" / "private" / "store"


def _ids(query: str, n: int) -> list[int]:
    ids, cursor = [], ""
    while len(ids) < n:
        q = urllib.parse.urlencode({"keyword": query, "limit": min(30, n - len(ids)), "cursor": cursor})
        d = json.loads(_get(f"{API}/marketplace/10?{q}"))
        ids += [x["id"] for x in d.get("data", [])]
        cursor = d.get("nextPageCursor")
        if not cursor or not d.get("data"):
            break
        time.sleep(0.5)  # gentle on a public API
    return ids[:n]


def facts(item: dict) -> dict:
    """What the API says about one model, flattened."""
    a, v = item["asset"], item.get("voting", {})
    tech = a.get("modelTechnicalDetails") or {}
    counts = tech.get("instanceCounts") or {}
    path = a.get("categoryPath") or ""
    return {"asset_id": a["id"], "title": a["name"], "creator": item.get("creator", {}).get("name"),
            "verified_creator": item.get("creator", {}).get("isVerifiedCreator"), "store_category": path,
            "category": next((c for k, c in CATEGORY.items() if path.startswith(k)), "prop"),
            "tris": (tech.get("objectMeshSummary") or {}).get("triangles"), "mesh_parts": counts.get("meshPart"),
            "scripts": a.get("scriptCount", counts.get("script")), "upvote_pct": v.get("upVotePercent"),
            "votes": v.get("voteCount"), "endorsed": a.get("isEndorsed"),
            "url": f"https://create.roblox.com/store/asset/{a['id']}"}


def details(ids: list[int]) -> list[dict]:
    out = []
    for i in range(0, len(ids), 30):
        chunk = ",".join(map(str, ids[i:i + 30]))
        out += [facts(x) for x in json.loads(_get(f"{API}/items/details?assetIds={chunk}")).get("data", [])]
    return out


def _thumbs(ids: list[int]) -> dict[int, str]:
    urls = {}
    for i in range(0, len(ids), 50):
        q = ",".join(map(str, ids[i:i + 50]))
        d = json.loads(_get(f"https://thumbnails.roblox.com/v1/assets?assetIds={q}&size=420x420&format=Png"))
        urls.update({x["targetId"]: x["imageUrl"] for x in d.get("data", []) if x.get("imageUrl")})
    return urls


def search(query: str, n: int = 20) -> str:
    """Fetch n models for a query: thumbnails, facts, a contact sheet (sheet-<query>.png) and the pending list."""
    from PIL import Image, ImageDraw
    items = details(_ids(query, n))
    img_dir = _dir() / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    for aid, url in _thumbs([f["asset_id"] for f in items]).items():
        p = img_dir / f"store-{aid}.png"
        if not p.exists():
            p.write_bytes(_get(url))
    pending = _dir() / "_pending.json"
    old = json.loads(pending.read_text()) if pending.exists() else {}
    for f in items:
        f["query"] = query
        f["thumb"] = str(img_dir / f"store-{f['asset_id']}.png")
        old[str(f["asset_id"])] = f
    pending.write_text(json.dumps(old, indent=1))
    # contact sheet: 5 across, the facts that matter under each
    cols, cell = 5, 300
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 46)), "white")
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(items):
        x, y = i % cols * cell, i // cols * (cell + 46)
        if Path(f["thumb"]).exists():
            im = Image.open(f["thumb"]).convert("RGB")
            im.thumbnail((cell - 8, cell - 8))
            sheet.paste(im, (x + 4, y + 4))
        d.text((x + 4, y + cell - 2), f"#{i + 1} {f['title'][:38]}", fill="black")
        d.text((x + 4, y + cell + 12), f"{f['tris'] or '?'} tris  {f['mesh_parts'] or 0} meshes  "
               f"{f['scripts'] or 0} scripts", fill="black")
        d.text((x + 4, y + cell + 26), f"{f['upvote_pct'] or '?'}% of {f['votes'] or 0}  {f['asset_id']}", fill="gray")
    out = _dir() / f"sheet-{quality._slug(query)}.png"
    sheet.save(out)
    return f"{len(items)} models for {query!r} -> {out}"


def grade(asset_id: int, stars: float, note: str, failures: list[str] | None = None, category: str | None = None,
          grader: str = "claude") -> Path:
    """A vault note for one store model (it must have come through search)."""
    pending = json.loads((_dir() / "_pending.json").read_text())
    f = pending[str(asset_id)]
    extra = {k: f[k] for k in ("asset_id", "title", "creator", "verified_creator", "store_category", "tris",
                               "mesh_parts", "scripts", "upvote_pct", "votes", "url", "query") if f.get(k) is not None}
    extra["grader"] = grader
    p = quality.record("store", f"{f['title'][:40]} {asset_id}", 1, stars, note, category or f["category"],
                       "store", extra, Path(f["thumb"]))
    if failures:
        meta, body = quality.read(p)
        meta["failures"] = sorted(set(meta.get("failures") or []) | set(failures))
        quality.write(p, meta, body)
    return p


def grade_file(path: Path) -> str:
    """Grades from a JSON list: [{"id", "stars", "note", "failures"?, "category"?, "grader"?}]."""
    rows = json.loads(Path(path).read_text())
    for r in rows:
        grade(r["id"], r["stars"], r["note"], r.get("failures"), r.get("category"), r.get("grader", "claude"))
    return f"graded {len(rows)} store models"
