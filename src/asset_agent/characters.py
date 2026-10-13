"""Characters from real Roblox assets: search the Creator Store, compare candidates, compose an R15 avatar.

For a known character, existing Roblox assets (hair meshes, classic shirts and pants, face decals, whole rigs)
beat modelling from scratch by a wide margin. The flow is two calls:

1. character(name, query): search free Creator Store models, insert the top candidates into
   ServerStorage.AssetAgentCandidates.<name> (scripts stripped), line them up on the lab stage and return a
   labelled contact sheet plus what each candidate offers (rig, shirt, pants, hair, face).
2. character(name, pick={role: candidate #}): compose an R15 avatar in workspace from the chosen parts.
   Roles: body (a whole R15 rig to start from), shirt, pants, hair, face, skin. The recipe is saved to
   assets/<name>/character.json so studio(name) rebuilds it.

Built-in Studio fixes (each cost a round on the Gon test):
- the default R15 head is a dynamic head that hides face decals: faces go on a classic head (SpecialMesh Head)
  welded over the hidden R15 head
- a decal *asset* id is not an image id: textures are resolved through InsertService
- ScaleTo drops hand-made welds: hair stores its offset from the head and is re-welded after scaling
- the Animator rewrites Bone.Transform every step: drive bones through their CFrame
"""
import json
from pathlib import Path

from . import luau, studio_client

LAB = (-200, 0, 600)  # where candidates line up for the contact sheet, away from the game
SPACING = 9
BODY = {"Head", "UpperTorso", "LowerTorso", "Torso", "HumanoidRootPart", "LeftUpperArm", "RightUpperArm",
        "LeftLowerArm", "RightLowerArm", "LeftHand", "RightHand", "LeftUpperLeg", "RightUpperLeg",
        "LeftLowerLeg", "RightLowerLeg", "LeftFoot", "RightFoot", "Left Arm", "Right Arm", "Left Leg", "Right Leg"}
ROLES = ("body", "shirt", "pants", "hair", "face", "skin")


def _json(text: str):
    try:
        return json.loads(text)
    except ValueError:
        raise RuntimeError(" ".join(text.split())[:300])


async def search(s, query: str, n: int = 8) -> list[dict]:
    res = await s.call("search_asset", query=query, scope="creator_store", assetType="Model", priceFilter="free",
                       maxResults=n)
    return [r for r in _json(studio_client._text(res)).get("results", []) if r.get("isFree", True)][:n]


PREP = r"""
local HS=game:GetService('HttpService')
local folder=game.ServerStorage:FindFirstChild('AssetAgentCandidates') or Instance.new('Folder')
folder.Name='AssetAgentCandidates' folder.Parent=game.ServerStorage
local box=folder:FindFirstChild(NAME) or Instance.new('Folder') box.Name=NAME box.Parent=folder
local BODY=HS:JSONDecode(BODYJSON)
local out={}
for i,id in IDS do
 local m=box:FindFirstChild('c'..i)
 if m and not m:IsA('Model') then  -- accessories, parts: wrap so every candidate can be measured and moved
  local w=Instance.new('Model') w.Name=m.Name m.Name=m.ClassName m.Parent=w w.Parent=box m=w
 end
 if m then local ok,err=pcall(function()
  for _,d in m:GetDescendants() do if d:IsA('LuaSourceContainer') then d:Destroy() end end  -- free models can carry scripts
  for _,d in m:GetDescendants() do if d:IsA('BasePart') then d.Anchored=true end end
  local rig=m:FindFirstChildWhichIsA('Humanoid',true)
  local head=nil for _,d in m:GetDescendants() do if d.Name=='Head' and d:IsA('BasePart') then head=d break end end
  local shirt=m:FindFirstChildWhichIsA('Shirt',true) local pants=m:FindFirstChildWhichIsA('Pants',true)
  local face=nil if head then for _,d in head:GetDescendants() do if d:IsA('Decal') then face=d.Texture break end end end
  local faceTex=face
  local hair=0
  if head then for _,d in m:GetDescendants() do
   if d:IsA('BasePart') and not BODY[d.Name] and d.Name~='FakeHead' and d.Name~='ClassicHead' and (d:IsDescendantOf(head)
     or (d.Parent and d.Parent.Name=='Head') or string.find(string.lower(d.Name),'hair') or d.Parent:IsA('Accessory')) then hair+=1 end end end
  local c,sz=m:GetBoundingBox()
  local x=LAB.X+(i-1)*SPACING
  m:PivotTo(CFrame.new(x,LAB.Y,LAB.Z)*CFrame.Angles(0,math.pi,0))
  local face=m:FindFirstChild('HumanoidRootPart',true) or head  -- turn rigs to face the camera (+Z)
  if face and face.CFrame.LookVector.Z<0 then m:PivotTo(m:GetPivot()*CFrame.Angles(0,math.pi,0)) end
  local c2,s2=m:GetBoundingBox() m:PivotTo(m:GetPivot()+Vector3.new(0,LAB.Y-(c2.Position.Y-s2.Y/2),0))
  m.Parent=workspace:FindFirstChild('AssetAgentLineup') or (function() local f=Instance.new('Folder') f.Name='AssetAgentLineup' f.Parent=workspace return f end)()
  local c3,s3=m:GetBoundingBox()
  out[tostring(i)]={rig=rig and rig.RigType.Name or 'none',shirt=shirt and shirt.ShirtTemplate or nil,pants=pants and pants.PantsTemplate or nil,
   face=faceTex,hair=hair,height=s3.Y,cam={x,LAB.Y+math.min(s3.Y,7)*0.55,LAB.Z+9},look={x,LAB.Y+math.min(s3.Y,7)*0.55,LAB.Z}}
 end) if not ok then out[tostring(i)]={error=tostring(err)} end end
end
return HS:JSONEncode(out)"""


def prep_script(name: str, ids: list[str]) -> str:
    x, y, z = LAB
    return (f"local NAME='{name}' local IDS=game:GetService('HttpService'):JSONDecode({luau.data(ids)})\n"
            f"local LAB,SPACING=Vector3.new({x},{y},{z}),{SPACING}\n"
            f"local BODYJSON={luau.data({b: True for b in BODY})}\n" + PREP)


def describe(i: int, r: dict, info: dict) -> str:
    """One line per candidate: what it offers."""
    have = [k for k in ("shirt", "pants", "face") if info.get(k)]
    if info.get("hair"):
        have.append(f"hair x{info['hair']}")
    return f"#{i} {r.get('name', '').strip()[:28]} ({r['assetId']}): {info.get('rig', '?')} rig, {', '.join(have) or 'nothing usable'}, {info.get('height', 0):.1f} studs"


COMPOSE = r"""
local HS,IS=game:GetService('HttpService'),game:GetService('InsertService')
local box=game.ServerStorage.AssetAgentCandidates:FindFirstChild(NAME) or Instance.new('Folder')
local lineup=workspace:FindFirstChild('AssetAgentLineup')
local function cand(i) if not i then return nil end local k='c'..i return (lineup and lineup:FindFirstChild(k)) or box:FindFirstChild(k) end
local BODY=HS:JSONDecode(BODYJSON)
local function headOf(m) for _,d in m:GetDescendants() do if d.Name=='Head' and d:IsA('BasePart') then return d end end end
local function image(tex)  -- a decal asset id is not an image id: resolve it through InsertService
 local id=tonumber(string.match(tex or '','%d+$')) if not id then return tex end
 local ok,m=pcall(function() return IS:LoadAsset(id) end)
 if ok then local d=m:FindFirstChildWhichIsA('Decal',true) local t=d and d.Texture m:Destroy() if t and t~='' then return t end end
 return tex
end
local old=workspace:FindFirstChild(NAME,true) local pivot,parent=old and old:GetPivot(),old and old.Parent or workspace
local bodyM=cand(PICK.body)
local rig
if bodyM and bodyM:FindFirstChildWhichIsA('Humanoid',true) and bodyM:FindFirstChildWhichIsA('Humanoid',true).RigType==Enum.HumanoidRigType.R15 then
 rig=(bodyM:FindFirstChildWhichIsA('Humanoid',true).Parent):Clone()
 for _,d in rig:GetDescendants() do if d:IsA('BasePart') then d.Anchored=false d.CanCollide=false end end
else
 local skin=Color3.new(0.92,0.72,0.57)
 local sm=cand(PICK.skin or PICK.face) local sh=sm and headOf(sm) if sh then skin=sh.Color end
 local d=Instance.new('HumanoidDescription')
 d.HeadColor,d.TorsoColor,d.LeftArmColor,d.RightArmColor,d.LeftLegColor,d.RightLegColor=skin,skin,skin,skin,skin,skin
 rig=game:GetService('Players'):CreateHumanoidModelFromDescription(d,Enum.HumanoidRigType.R15)
end
rig.Name=NAME
if old then old:Destroy() end
if pivot then rig:PivotTo(pivot) else
 local cf=workspace.CurrentCamera.CFrame local at=cf.Position+cf.LookVector*15
 local hit=workspace:Raycast(at+Vector3.new(0,100,0),Vector3.new(0,-1000,0))
 local y=(hit and hit.Position.Y or 0)+rig.Humanoid.HipHeight+rig.HumanoidRootPart.Size.Y/2
 rig:PivotTo(CFrame.lookAt(Vector3.new(at.X,y,at.Z),Vector3.new(cf.Position.X,y,cf.Position.Z)))
end
for role,cls in {shirt='Shirt',pants='Pants'} do
 local m=cand(PICK[role]) local c=m and m:FindFirstChildWhichIsA(cls,true)
 if c then for _,x in rig:GetChildren() do if x:IsA(cls) then x:Destroy() end end c:Clone().Parent=rig end
end
local head=rig.Head
local hm=cand(PICK.hair)
if hm then  -- hair: every non-body visual on the source head, welded at the same offset
 for _,x in rig:GetChildren() do if x:GetAttribute('AssetAgentHair') then x:Destroy() end end
 for _,a in rig:GetChildren() do if a:IsA('Accessory') then a:Destroy() end end
 local sh=headOf(hm)
 for _,p in hm:GetDescendants() do
  if p:IsA('BasePart') and sh and not BODY[p.Name] and p.Name~='FakeHead' and p.Name~='ClassicHead' and p~=sh
    and (p:IsDescendantOf(sh) or (p.Parent and p.Parent.Name=='Head') or string.find(string.lower(p.Name),'hair') or p.Parent:IsA('Accessory')) then
   local q=p:Clone() for _,j in q:GetDescendants() do if j:IsA('JointInstance') or j:IsA('WeldConstraint') or j:IsA('Attachment') and not q:FindFirstChildWhichIsA('Bone',true) then j:Destroy() end end
   local rel=sh.CFrame:ToObjectSpace(p.CFrame)
   q.Anchored=false q.CanCollide=false q.Massless=true q.CanQuery=false
   q.CFrame=head.CFrame*rel q:SetAttribute('AssetAgentHair',true) q:SetAttribute('HairRel',rel) q.Parent=rig
   local w=Instance.new('WeldConstraint') w.Part0=head w.Part1=q w.Parent=q
  end
 end
end
local fm=cand(PICK.face)
if fm then  -- the face goes on a classic head: the R15 dynamic head hides decals
 local sh=headOf(fm) local dec=nil
 if sh then for _,d in sh:GetDescendants() do if d:IsA('Decal') then dec=d break end end end
 if dec then
  local ch=rig:FindFirstChild('ClassicHead') if ch then ch:Destroy() end
  ch=Instance.new('Part') ch.Name='ClassicHead' ch.Size=Vector3.new(2,1,1)*rig:GetScale() ch.Color=head.Color
  ch.CanCollide=false ch.Massless=true ch.CanQuery=false
  local m=Instance.new('SpecialMesh') m.MeshType=Enum.MeshType.Head m.Scale=Vector3.new(1.25,1.25,1.25) m.Parent=ch
  local f=Instance.new('Decal') f.Name='face' f.Face=Enum.NormalId.Front f.Texture=image(dec.Texture) f.Parent=ch
  ch.CFrame=head.CFrame ch.Parent=rig
  local w=Instance.new('WeldConstraint') w.Part0=head w.Part1=ch w.Parent=ch
  head.Transparency=1 head:SetAttribute('Hidden',true)
  for _,d in head:GetChildren() do if d:IsA('Decal') then d:Destroy() end end
 end
end
rig.HumanoidRootPart.Anchored=true
rig.Parent=parent
local n=0 for _,x in rig:GetChildren() do if x:GetAttribute('AssetAgentHair') then n+=1 end end
return 'built '..NAME..': R15'..(PICK.body and (' from #'..PICK.body) or '')..(PICK.shirt and ', shirt #'..PICK.shirt or '')
 ..(PICK.pants and ', pants #'..PICK.pants or '')..(PICK.hair and (', hair #'..PICK.hair..' ('..n..' parts)') or '')..(PICK.face and ', face #'..PICK.face or '')"""


def compose_script(name: str, pick: dict) -> str:
    bad = [k for k in pick if k not in ROLES]
    if bad:
        raise KeyError(f"unknown role(s) {', '.join(bad)}; roles: {', '.join(ROLES)}")
    return (f"local NAME='{name}' local PICK=game:GetService('HttpService'):JSONDecode({luau.data({k: int(v) for k, v in pick.items()})})\n"
            f"local BODYJSON={luau.data({b: True for b in BODY})}\n" + COMPOSE)


def contact_sheet(shots: list[tuple[int, Path]], out: Path, refs: list[str] | None = None, tile: int = 220) -> Path:
    """Candidates side by side, numbered, with reference images first so they can be compared."""
    from PIL import Image, ImageDraw
    tiles = []
    for r in refs or []:
        try:
            tiles.append(("ref", Image.open(r).convert("RGB")))
        except OSError:
            pass
    for i, f in shots:
        tiles.append((f"#{i}", Image.open(f).convert("RGB")))
    if not tiles:
        raise ValueError("nothing to show")
    cols = min(5, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    h = int(tile * 1.25)
    sheet = Image.new("RGB", (cols * tile, rows * h), (24, 25, 30))
    dr = ImageDraw.Draw(sheet)
    for k, (label, im) in enumerate(tiles):
        W, H = im.size
        if label != "ref":  # crop the middle of a viewport shot to the character
            im = im.crop((W / 2 - H * 0.4, H * 0.02, W / 2 + H * 0.4, H * 0.98))
        im.thumbnail((tile, h))
        x, y = (k % cols) * tile, (k // cols) * h
        sheet.paste(im, (x + (tile - im.width) // 2, y + (h - im.height) // 2))
        dr.rectangle([x, y, x + 34, y + 16], fill=(0, 0, 0))
        dr.text((x + 4, y + 2), label, fill=(255, 220, 90))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def blank(path: Path) -> bool:
    """True when Studio returned an empty viewport (its window minimised or hidden): no real image to judge."""
    from PIL import Image, ImageStat
    im = Image.open(path).convert("L").resize((64, 40))
    return ImageStat.Stat(im).stddev[0] < 4


def find(root: Path, query: str | None, pick: dict | None, refs: list[str] | None, n: int = 8):
    """Step 1 (query) or step 2 (pick). Returns (text, image path or None)."""
    root = Path(root)
    name = root.name
    rec_file = root / "character.json"
    rec = json.loads(rec_file.read_text()) if rec_file.exists() else {"name": name}
    if query:
        async def go(s):
            found = await search(s, query, n)
            if not found:
                return [], {}, []
            ids = []
            for i, r in enumerate(found, 1):
                await s.call("insert_asset", assetId=str(r["assetId"]), assetName=f"c{i}", assetType="Model",
                             parentPath=f"game.ServerStorage.AssetAgentCandidates.{name}")
                ids.append(str(r["assetId"]))
            info = _json(await s.luau(prep_script(name, ids)))
            shots = []
            for k, v in info.items():
                if "cam" not in v:
                    continue
                f = root / "candidates" / f"c{k}.png"
                await s.capture(f, v["cam"], v["look"])
                shots.append((int(k), f))
            return found, info, sorted(shots)

        # insert_asset needs the parent folder to exist first
        studio_client.run(lambda s: s.luau(
            "local f=game.ServerStorage:FindFirstChild('AssetAgentCandidates') or Instance.new('Folder') f.Name='AssetAgentCandidates' f.Parent=game.ServerStorage "
            f"local b=f:FindFirstChild('{name}') if b then b:Destroy() end b=Instance.new('Folder') b.Name='{name}' b.Parent=f "
            "local l=workspace:FindFirstChild('AssetAgentLineup') if l then l:Destroy() end return 'ok'"))
        found, info, shots = studio_client.run(go)
        if not found:
            return f"no free Creator Store models for {query!r}", None
        rec.update(query=query, candidates=[{"n": i, "id": r["assetId"], "name": r.get("name", "").strip()}
                                            for i, r in enumerate(found, 1)], refs=refs or rec.get("refs") or [])
        root.mkdir(parents=True, exist_ok=True)
        rec_file.write_text(json.dumps(rec, indent=1))
        sheet = contact_sheet(shots, root / "candidates.png", rec["refs"])
        lines = [describe(i, r, info.get(str(i), {})) for i, r in enumerate(found, 1)]
        warn = " | Studio isn't rendering (bring its window to the front)" if shots and all(blank(f) for _, f in shots) else ""
        return (f"{len(found)} candidates for {query!r} lined up in workspace.AssetAgentLineup{warn}\n" + "\n".join(lines) +
                f"\nnext: character('{name}', pick={{body|shirt|pants|hair|face|skin: #}})"), sheet
    if pick:
        rec["pick"] = {**rec.get("pick", {}), **pick}
        line = studio_client.run(lambda s: s.luau(compose_script(name, rec["pick"])))
        root.mkdir(parents=True, exist_ok=True)
        rec_file.write_text(json.dumps(rec, indent=1))
        return line, None
    return (json.dumps(rec, indent=1) if rec_file.exists() else f"no character {name}: start with query"), None


# ---------------------------------------------------------------- look: check a model in Studio

LOOK = r"""
local m=workspace:FindFirstChild(NAME,true)
if not m then return 'missing' end
local root=m:FindFirstChild('HumanoidRootPart') or m.PrimaryPart
local cf=root and root.CFrame or m:GetPivot()
local c,sz=m:GetBoundingBox()
local h=math.min(sz.Y,9)
local base=Vector3.new(cf.X,c.Position.Y-sz.Y/2,cf.Z)
local head=m:FindFirstChild('ClassicHead') or m:FindFirstChild('Head')
local out={}
for _,v in VIEWS do
 local a=math.rad(v[1]) local dir=cf.LookVector*math.cos(a)+cf.RightVector*math.sin(a)
 local look,cam
 if v[2]=='face' and head then local hc=head.CFrame look=hc.Position cam=hc.Position+hc.LookVector*h*0.55
 else look=base+Vector3.new(0,h*0.5,0) cam=look+dir*(h*0.95+1.5)+Vector3.new(0,h*0.08,0) end
 table.insert(out,string.format('%f,%f,%f,%f,%f,%f',cam.X,cam.Y,cam.Z,look.X,look.Y,look.Z))
end
return table.concat(out,'|')"""

VIEWS = {"front": (0, "body"), "34": (35, "body"), "side": (90, "body"), "back": (180, "body"), "face": (0, "face")}


def look(name: str, out: Path, views: str = "front,34,side,face", refs: list[str] | None = None,
         hide: list[str] | None = None) -> tuple[Path, str]:
    """Shots of a workspace model from named views (front 34 side back face), refs first, in one sheet.
    hide: part names made invisible for the shots (e.g. a raised hand covering the face), restored after."""
    vs = [v.strip() for v in views.split(",") if v.strip()]
    bad = [v for v in vs if v not in VIEWS]
    if bad:
        raise KeyError(f"unknown view(s) {', '.join(bad)}; views: {', '.join(VIEWS)}")
    hide = hide or []
    hide_code = (f"local m=workspace:FindFirstChild('{name}',true) for _,n in game:GetService('HttpService'):JSONDecode({luau.data(hide)}) do "
                 "local p=m and m:FindFirstChild(n,true) if p and p:IsA('BasePart') then p:SetAttribute('LookT',p.Transparency) p.Transparency=1 end end return 'ok'")
    show_code = (f"local m=workspace:FindFirstChild('{name}',true) if m then for _,p in m:GetDescendants() do "
                 "local t=p:GetAttribute('LookT') if t then p.Transparency=t p:SetAttribute('LookT',nil) end end end return 'ok'")

    async def go(s):
        if hide:
            await s.luau(hide_code)
        try:
            raw = await s.luau(f"local NAME='{name}' local VIEWS={{" + ",".join(f"{{{VIEWS[v][0]},'{VIEWS[v][1]}'}}" for v in vs) + "}\n" + LOOK)
            if raw.strip() == "missing":
                raise KeyError(f"no {name} in workspace")
            shots = []
            for i, part in enumerate(raw.strip().split("|")):
                x = [float(t) for t in part.split(",")]
                f = out.parent / f"_look_{name}_{i}.png"
                await s.capture(f, x[:3], x[3:])
                shots.append((i + 1, f))
            return shots
        finally:
            if hide:
                await s.luau(show_code)
    shots = studio_client.run(go)
    sheet = contact_sheet(shots, out, refs)
    note = "Studio isn't rendering: bring its window to the front and look again" if all(blank(f) for _, f in shots) else \
        f"{len(shots)} views: {', '.join(vs)}"
    return sheet, note
