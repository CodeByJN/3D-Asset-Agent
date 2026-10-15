"""Creator Store models graded into the quality vault: real examples of good and bad Roblox assets.

search(query, n) reads Roblox's public Creator Store API (search, item details, thumbnails): each model's
triangles, mesh parts, scripts, votes and a 420 px thumbnail. It writes a contact sheet to look at and a pending
list. gallery(query) inserts those models into the open Studio place (Workspace.StoreGallery), each with a sign
and Stars/Pros/Cons/Failures attributes for the user to fill in the Properties panel; collect() reads the grades
back as vault notes (kind "store", grader "human").

Notes link to the item by id and URL. Thumbnails are other creators' images, so they stay in the git-ignored
private folder; a shared note publishes the id, the facts and the grade, never the picture.
"""
import json
import re
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
          grader: str = "human", tags: list[str] | None = None) -> Path:
    """A vault note for one store model (it must have come through search)."""
    pending = json.loads((_dir() / "_pending.json").read_text())
    f = pending[str(asset_id)]
    extra = {k: f[k] for k in ("asset_id", "title", "creator", "verified_creator", "store_category", "tris",
                               "mesh_parts", "scripts", "upvote_pct", "votes", "url", "query") if f.get(k) is not None}
    extra["grader"] = grader
    p = quality.record("store", f"{f['title'][:40]} {asset_id}", 1, stars, note, category or f["category"],
                       "store", extra, Path(f["thumb"]))
    if failures or tags:
        meta, body = quality.read(p)
        meta["failures"] = sorted(set(meta.get("failures") or []) | set(failures or []))
        meta["tags"] = sorted(set(meta.get("tags") or []) | set(tags or []))
        quality.write(p, meta, body)
        quality.relink()
    return p


def grade_file(path: Path) -> str:
    """Grades from a JSON list: [{"id", "stars", "note", "failures"?, "category"?, "grader"?, "tags"?}]."""
    rows = json.loads(Path(path).read_text())
    for r in rows:
        grade(r["id"], r["stars"], r["note"], r.get("failures"), r.get("category"), r.get("grader", "human"), r.get("tags"))
    return f"graded {len(rows)} store models"


# ---------------------------------------------------------------- grading in Studio
LAYOUT = r"""
local HS = game:GetService("HttpService")
local items = HS:JSONDecode([==[%s]==])
local ORIGIN = Vector3.new(0, 0, 1500)  -- away from whatever the place already has
local gallery = workspace:FindFirstChild("StoreGallery") or Instance.new("Folder")
gallery.Name = "StoreGallery"
gallery.Parent = workspace
local placed, have = 0, {}
for _, m in gallery:GetChildren() do  -- one of each asset: drop repeats
	local id = m:GetAttribute("AssetId")
	if id and have[id] then m:Destroy() elseif id then have[id] = true end
end
for _, it in items do  -- adopt the newly inserted models
	local found = workspace:FindFirstChild("store_" .. it.asset_id, true)
	if not found then continue end
	if have[tostring(it.asset_id)] then found:Destroy(); continue end
	local m = Instance.new("Model")
	m.Name = string.format("#%%d %%s", it.n, it.title)
	if found:IsA("Model") or found:IsA("Folder") then
		for _, c in found:GetChildren() do c.Parent = m end
		found:Destroy()
	else
		found.Parent = m
	end
	for _, d in m:GetDescendants() do  -- free-model code never runs here
		if d:IsA("BaseScript") then d.Enabled = false end
		if d:IsA("BasePart") then d.Anchored = true end
	end
	for k, v in {AssetId = tostring(it.asset_id), Stars = 0, Pros = "", Cons = "", Failures = ""} do
		if m:GetAttribute(k) == nil then m:SetAttribute(k, v) end
	end
	local sign = Instance.new("Part")
	sign.Name = "_Sign"; sign.Anchored = true; sign.CanCollide = false; sign.Transparency = 1
	sign.Size = Vector3.new(1, 1, 1)
	local bb = Instance.new("BillboardGui")
	bb.Size = UDim2.fromOffset(280, 64); bb.AlwaysOnTop = true; bb.MaxDistance = 400; bb.Parent = sign
	local t = Instance.new("TextLabel")
	t.Size = UDim2.fromScale(1, 1); t.BackgroundTransparency = 0.25; t.BackgroundColor3 = Color3.new(0, 0, 0)
	t.TextColor3 = Color3.new(1, 1, 1); t.TextScaled = true; t.Font = Enum.Font.GothamBold
	t.Text = string.format("#%%d %%s\n%%s tris | %%s meshes | %%s scripts", it.n, it.title, tostring(it.tris or "?"),
		tostring(it.mesh_parts or 0), tostring(it.scripts or 0))
	t.Parent = bb
	sign.Parent = m
	m.Parent = gallery
	placed += 1
end
-- lay every gallery model out in rows on its own floor, signs above
local x, z, rowDepth, width = 0, 0, 0, 0
for _, m in gallery:GetChildren() do
	if not m:IsA("Model") then continue end
	local sign = m:FindFirstChild("_Sign")
	if sign then sign.Parent = nil end
	local ok, cf, size = pcall(m.GetBoundingBox, m)
	if not ok or size.Magnitude == 0 then cf, size = CFrame.new(), Vector3.new(8, 8, 8) end
	if x > 300 then x = 0; z += rowDepth + 40; rowDepth = 0 end
	local target = ORIGIN + Vector3.new(x + size.X / 2, 1 + size.Y / 2, z + size.Z / 2)
	m:PivotTo(m:GetPivot() + (target - cf.Position))
	if sign then sign.Position = target + Vector3.new(0, size.Y / 2 + 5, 0); sign.Parent = m end
	x += math.max(size.X, 6) + 25
	width = math.max(width, x)
	rowDepth = math.max(rowDepth, size.Z)
end
local floor = gallery:FindFirstChild("_Floor") or Instance.new("Part")
floor.Name = "_Floor"; floor.Anchored = true; floor.Material = Enum.Material.SmoothPlastic
floor.Color = Color3.fromRGB(70, 74, 82); floor.Size = Vector3.new(width + 60, 1, z + rowDepth + 60)
floor.Position = ORIGIN + Vector3.new(width / 2 - 10, 0.5, (z + rowDepth) / 2)
floor.Parent = gallery
local cam = workspace.CurrentCamera
local c = floor.Position
cam.CFrame = CFrame.lookAt(c + Vector3.new(0, 0.35 * floor.Size.X, 0.75 * floor.Size.X), c)
game:GetService("Selection"):Set({})
return "placed " .. placed
"""

COLLECT = r"""
local out = {}
local g = workspace:FindFirstChild("StoreGallery")
for _, m in (g and g:GetChildren() or {}) do
	local stars = m:GetAttribute("Stars")
	if m:IsA("Model") and type(stars) == "number" and stars > 0 then
		table.insert(out, {id = m:GetAttribute("AssetId"), stars = stars, pros = m:GetAttribute("Pros") or "",
			cons = m:GetAttribute("Cons") or "", failures = m:GetAttribute("Failures") or ""})
	end
end
return game:GetService("HttpService"):JSONEncode(out)
"""


def _graded() -> set[str]:
    return {str(m.get("asset_id")) for m, _, _ in quality.notes() if m.get("kind") == "store"}


def gallery(query: str | None = None, n: int = 15) -> str:
    """Put up to n ungraded models (from a search; one query, or every pending one) in the open Studio place."""
    from . import studio_client
    pending = json.loads((_dir() / "_pending.json").read_text()) if (_dir() / "_pending.json").exists() else {}
    done = _graded()
    todo = [f for k, f in pending.items() if k not in done and (query is None or f.get("query") == query)][:n]
    if not todo:
        return "nothing to grade: run `store search <query>` first"
    items = [{**{k: f.get(k) for k in ("asset_id", "title", "tris", "mesh_parts", "scripts")}, "n": i + 1}
             for i, f in enumerate(todo)]

    async def fn(st):
        failed = []
        there = await st.luau('local s = {} for _, d in workspace:GetDescendants() do local id = d.Name:match("^store_(%d+)$") '
                              'or (d:IsA("Model") and d:GetAttribute("AssetId")) if id then table.insert(s, id) end end '
                              'return table.concat(s, ",")')
        there = set(re.findall(r"\d+", there))
        for it in items:
            if str(it["asset_id"]) in there:
                continue
            try:
                await st.call("insert_asset", **st._args("insert_asset", assetId=it["asset_id"],
                                                        assetName=f"store_{it['asset_id']}", assetType="Model"))
            except Exception as e:  # noqa: BLE001 - one bad asset doesn't stop the gallery
                failed.append(f"{it['asset_id']} ({' '.join(str(e).split())[:80]})")
        res = await st.luau(LAYOUT % json.dumps(items))
        return res, failed
    res, failed = studio_client.run(fn)
    return (f"{' '.join(res.split())} of {len(items)} in Workspace.StoreGallery; grade each model's Stars (1-10), "
            f"Pros, Cons and Failures in Properties, then `store collect`" + (f"; failed: {', '.join(failed)}" if failed else ""))


def collect() -> str:
    """Your grades from the Studio gallery into the vault (re-collecting updates them)."""
    from . import studio_client
    text = studio_client.run(lambda st: st.luau(COLLECT))
    rows = json.loads(text[text.index("["):text.rindex("]") + 1])
    for r in rows:
        note = "; ".join(f"{k}: {r[k]}" for k in ("pros", "cons") if r[k].strip())
        fails = [f.strip() for f in r["failures"].replace(";", ",").split(",") if f.strip()]
        grade(int(r["id"]), r["stars"], note, fails)
    return f"collected {len(rows)} grade(s) from the Studio gallery"
