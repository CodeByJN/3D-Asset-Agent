"""Send an asset to a Roblox Studio test place.

1. Upload the export FBX with Roblox Open Cloud (creates the asset once, then new versions of the
   same asset id). Skipped when the export hasn't changed since the last upload, e.g. VFX-only edits.
2. Write a Luau script for Studio's built-in MCP server (execute_luau, Edit datamodel) that loads
   the asset into workspace (replacing the old copy in place) and (re)builds its effects. When the
   model in the place is already this revision, the script only swaps the effects.

Credentials: ROBLOX_API_KEY + ROBLOX_USER_ID (or ROBLOX_GROUP_ID), or `asset-agent roblox`.
The API key needs the Assets API with read and write access.
"""
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from . import config, luau, vfx

API = "https://apis.roblox.com/assets/v1"


class RobloxError(RuntimeError):
    pass


def creds() -> tuple[str, dict]:
    c = config.load()
    key = os.environ.get("ROBLOX_API_KEY") or c.get("roblox_key")
    user = os.environ.get("ROBLOX_USER_ID") or c.get("roblox_user")
    group = os.environ.get("ROBLOX_GROUP_ID") or c.get("roblox_group")
    if not key or not (user or group):
        raise RobloxError("Roblox upload isn't set up: run `asset-agent roblox --user YOUR_USER_ID --key API_KEY` "
                          "(key from create.roblox.com/dashboard/credentials with Assets read+write)")
    return key, {"groupId": str(group)} if group else {"userId": str(user)}


def _request(method, url, key, body=None, ctype=None):
    req = urllib.request.Request(url, data=body, method=method, headers={"x-api-key": key})
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RobloxError(f"{method} {url.removeprefix(API)} -> {e.code}: {' '.join(e.read().decode(errors='replace').split())[:200]}")


def _multipart(request: dict, path: Path) -> tuple[bytes, str]:
    b = uuid.uuid4().hex
    parts = [f"--{b}\r\nContent-Disposition: form-data; name=\"request\"\r\n\r\n{json.dumps(request)}\r\n".encode(),
             f"--{b}\r\nContent-Disposition: form-data; name=\"fileContent\"; filename=\"{path.name}\"\r\n"
             f"Content-Type: model/fbx\r\n\r\n".encode(), path.read_bytes(), f"\r\n--{b}--\r\n".encode()]
    return b"".join(parts), f"multipart/form-data; boundary={b}"


def upload(fbx: Path, name: str, asset_id: str | None = None, timeout: float = 180) -> str:
    """Create (or, with asset_id, add a version to) a Model asset from an FBX. Returns the asset id."""
    key, creator = creds()
    if asset_id:
        body, ctype = _multipart({"assetType": "Model", "assetId": asset_id}, fbx)
        op = _request("PATCH", f"{API}/assets/{asset_id}", key, body, ctype)
    else:
        body, ctype = _multipart({"assetType": "Model", "displayName": name[:50],
                                  "description": "Made with 3D-Asset-Agent",
                                  "creationContext": {"creator": creator}}, fbx)
        op = _request("POST", f"{API}/assets", key, body, ctype)
    t = time.time()
    while not op.get("done"):
        if time.time() - t > timeout:
            raise RobloxError(f"upload still processing after {timeout:.0f}s ({op.get('path')})")
        time.sleep(2)
        op = _request("GET", f"{API}/{op['path']}", key)
    if "response" not in op:
        raise RobloxError(f"upload failed: {json.dumps(op.get('error') or op.get('status') or op)[:200]}")
    res = op["response"]
    state = res.get("moderationResult", {}).get("moderationState", "")
    if state and state not in ("MODERATION_STATE_APPROVED", "MODERATION_STATE_REVIEWING"):
        raise RobloxError(f"asset {res.get('assetId')} {state}")
    return str(res.get("assetId") or asset_id)


# ---------------------------------------------------------------- Studio script

def studio_script(name: str, asset_id: str, revision: str, effects: dict, glow: dict | None = None) -> str:
    """Compact Luau for Studio's execute_luau. Returns a one-line status string when run.
    glow: {part name: [r,g,b]} parts made Neon in that colour (emissive details)."""
    fx = {n: {"nodes": vfx.resolve_textures(e["nodes"]), "mode": e["mode"]} for n, e in vfx.resolve(effects).items()}
    return luau.BUILD + f"""local NAME,ID,REV,FX='{name}',{asset_id},'{revision}',HS:JSONDecode({luau.data(fx)})
local GLOW=HS:JSONDecode({luau.data(glow or {})})
local m=workspace:FindFirstChild(NAME) local loaded=false
if not(m and m:GetAttribute('AssetAgentRev')==REV) then
 local ok,c=pcall(function() return game:GetService('InsertService'):LoadAsset(ID) end)
 if not ok then return 'LoadAsset('..ID..') failed: '..tostring(c) end
 local k=c:GetChildren() local n=k[1]
 if not(#k==1 and n:IsA('Model')) then n=Instance.new('Model') for _,x in k do x.Parent=n end end
 n.Name=NAME n:SetAttribute('AssetAgentRev',REV)
 for _,p in n:GetDescendants() do if p:IsA('BasePart') then p.Anchored=true end end
 if m then n:PivotTo(m:GetPivot()) m:Destroy() else
  local cf=workspace.CurrentCamera.CFrame local at=cf.Position+cf.LookVector*20
  local bc,bs=n:GetBoundingBox() n:PivotTo(n:GetPivot()+(Vector3.new(at.X,bs.Y/2,at.Z)-bc.Position)) end
 n.Parent=workspace m=n loaded=true end
for _,d in m:GetDescendants() do if d:GetAttribute('AssetAgentVFX') then d:Destroy() end
 local g=d:IsA('BasePart') and GLOW[d.Name] if g then d.Material=Enum.Material.Neon d.Color=Color3.new(g[1],g[2],g[3])
  if d:IsA('MeshPart') then d.TextureID='' end end end
local h=m.PrimaryPart or m:FindFirstChildWhichIsA('BasePart',true)
local n=0 for tag,e in FX do play(build(h,tag,e.nodes)) n+=1 end
return (loaded and 'loaded ' or 'kept model, ')..NAME..' with '..n..' effect(s)'"""


# ---------------------------------------------------------------- VFX lab and import

LAB_AT = (0, 200, 600)  # out of the way of the game: a floating stage above the map
STAND_INS = {"character": (2, 5, 1), "item": (3, 2, 0.3), "rarity": (2, 2, 2), "base": (4, 3, 4), "default": (3, 3, 3)}


def reach(nodes) -> float:
    """Rough radius in studs an effect fills: biggest particle plus how far particles travel."""
    best = 0.0

    def walk(n):
        nonlocal best
        pr = n.get("props", {})
        if n["class"] == "ParticleEmitter":
            size = max((k[1] + (k[2] if len(k) > 2 else 0) for k in pr.get("Size", {}).get("ns", [[0, 1]])), default=1)
            speed = pr.get("Speed", {}).get("nr", [5, 5])[1]
            life = pr.get("Lifetime", {}).get("nr", [1, 1])[1]
            drag = pr.get("Drag", 0)
            travel = speed * (min(life, 1 / drag) if drag else life)
            best = max(best, size / 2 + travel)
        elif n["class"] == "Beam":
            best = max(best, pr.get("Width0", 1), pr.get("Width1", 1))
        for c in n.get("children") or []:
            walk(c)
    for n in nodes:
        walk(n)
    return best


def lab_script(preset: str, effect: dict | None = None, stand_in: str | None = None) -> str:
    """Luau that (re)builds a dark lab stage, applies one preset and plays it. Imported presets play on
    an invisible part the size of their original host (its volume shapes where particles spawn); others
    on a visible stand-in. Returns the camera position and look-at point as 'x,y,z|x,y,z'."""
    p = vfx.presets()[preset]
    host = p.get("host", {}).get("size", {}).get("v3")
    if stand_in is None and not host:
        tags = p.get("tags", [])
        stand_in = next((t for t in ("character", "item", "rarity", "base") if t in tags), "default")
    k = (effect or {}).get("size", 1.0)
    size = [x * k for x in host] if host and stand_in is None else STAND_INS[stand_in]
    hidden = 1 if host and stand_in is None else 0
    fx = vfx.resolve({preset: {"type": preset, **(effect or {})}})[preset]
    fx["nodes"] = vfx.resolve_textures(fx["nodes"])
    x, y, z = LAB_AT
    if p.get("rig") == "character":
        return luau.BUILD + RIG_LAB.format(x=x, y=y, z=z, preset=preset, nodes=luau.data(fx["nodes"]))
    return luau.BUILD + f"""local AT,SZ,FX=Vector3.new({x},{y},{z}),Vector3.new({size[0]:g},{size[1]:g},{size[2]:g}),HS:JSONDecode({luau.data(fx["nodes"])})
local lab=workspace:FindFirstChild('AssetAgentLab') if lab then lab:Destroy() end
lab=Instance.new('Model') lab.Name='AssetAgentLab'
local floor=Instance.new('Part') floor.Name='Floor' floor.Anchored=true floor.Size=Vector3.new(1,1,1)
floor.CFrame=CFrame.new(AT-Vector3.new(0,0.5,0)) floor.Color=Color3.fromRGB(22,24,32) floor.Material=Enum.Material.SmoothPlastic floor.Parent=lab
local h=Instance.new('Part') h.Name='Host' h.Anchored=true h.CanCollide=false h.Size=SZ h.Transparency={hidden}
h.CFrame=CFrame.new(AT+Vector3.new(0,math.max(SZ.Y/2,1),0)) h.Color=Color3.fromRGB(120,128,160) h.Material=Enum.Material.SmoothPlastic h.Parent=lab
local e=math.max(SZ.X,SZ.Y,SZ.Z,5,{min(reach(fx["nodes"]) * 0.5, 80):.3g})  -- particles fade well before full reach
floor.Size=Vector3.new(math.max(80,e*8),1,math.max(80,e*8))
local dir=Vector3.new(1.6,0.7,2.6).Unit
local look=h.Position+Vector3.new(0,e*0.35,0) local cam=look+dir*e*3.5  -- far enough to see the whole effect and its surroundings
local wall=Instance.new('Part') wall.Name='Backdrop' wall.Anchored=true wall.CanCollide=false wall.Size=Vector3.new(e*8,e*5,1)
wall.CFrame=CFrame.lookAt(look-dir*e*3+Vector3.new(0,e*1.5,0),cam+Vector3.new(0,e*1.5,0)) wall.Color=Color3.fromRGB(14,16,24) wall.Material=Enum.Material.SmoothPlastic wall.Parent=lab
lab.Parent=workspace
play(build(h,'{preset}',FX))
return string.format('%g,%g,%g|%g,%g,%g',cam.X,cam.Y,cam.Z,look.X,look.Y,look.Z)"""


# A blocky R15 stand-in (feet on the floor, facing -Z) for auras: layers attach to its parts by name.
RIG = [("HumanoidRootPart", (0, 3, 0), (2, 2, 1)), ("LowerTorso", (0, 2.6, 0), (2, 0.6, 1)),
       ("UpperTorso", (0, 3.5, 0), (2, 1.4, 1)), ("Head", (0, 4.8, 0), (1.2, 1.2, 1.2)),
       ("LeftUpperArm", (-1.5, 3.55, 0), (1, 1.2, 1)), ("RightUpperArm", (1.5, 3.55, 0), (1, 1.2, 1)),
       ("LeftLowerArm", (-1.5, 2.6, 0), (1, 0.8, 1)), ("RightLowerArm", (1.5, 2.6, 0), (1, 0.8, 1)),
       ("LeftHand", (-1.5, 2.05, 0), (1, 0.3, 1)), ("RightHand", (1.5, 2.05, 0), (1, 0.3, 1)),
       ("LeftUpperLeg", (-0.5, 1.75, 0), (1, 1.1, 1)), ("RightUpperLeg", (0.5, 1.75, 0), (1, 1.1, 1)),
       ("LeftLowerLeg", (-0.5, 0.8, 0), (1, 0.8, 1)), ("RightLowerLeg", (0.5, 0.8, 0), (1, 0.8, 1)),
       ("LeftFoot", (-0.5, 0.2, 0), (1, 0.4, 1)), ("RightFoot", (0.5, 0.2, 0), (1, 0.4, 1))]
_RIG_LUA = "{{" + ",".join("{{'%s',Vector3.new(%g,%g,%g),Vector3.new(%g,%g,%g)}}" % (n, *p, *sz) for n, p, sz in RIG) + "}}"  # braces doubled for str.format
RIG_LAB = """local AT=Vector3.new({x},{y},{z})
local lab=workspace:FindFirstChild('AssetAgentLab') if lab then lab:Destroy() end
lab=Instance.new('Model') lab.Name='AssetAgentLab'
local floor=Instance.new('Part') floor.Name='Floor' floor.Anchored=true floor.Size=Vector3.new(120,1,120)
floor.CFrame=CFrame.new(AT-Vector3.new(0,0.5,0)) floor.Color=Color3.fromRGB(16,18,28) floor.Material=Enum.Material.SmoothPlastic floor.Parent=lab
local rig=Instance.new('Model') rig.Name='StandIn' rig.Parent=lab
for _,r in """ + _RIG_LUA + """ do
 local p=Instance.new('Part') p.Name=r[1] p.Anchored=true p.CanCollide=false p.Size=r[3] p.CFrame=CFrame.new(AT+r[2])
 p.Color=Color3.fromRGB(150,156,180) p.Material=Enum.Material.SmoothPlastic p.Transparency=r[1]=='HumanoidRootPart' and 1 or 0 p.Parent=rig
end
lab.Parent=workspace
local h=rig.HumanoidRootPart
local list=build(h,'{preset}',HS:JSONDecode({nodes}))
play(list)
local n=animate(rig,'{preset}',function() return lab.Parent~=nil end)
local look=h.Position+Vector3.new(0,1.6,0) local cam=look+Vector3.new(9,4,17)
return string.format('%g,%g,%g|%g,%g,%g',cam.X,cam.Y,cam.Z,look.X,look.Y,look.Z)"""


def replay_script(slow: float = 1.0) -> str:
    """Luau that replays the lab's current effect: bursts and tweens fire again, at 1/slow speed."""
    return luau.BUILD + f"""SLOW={slow:g}
local lab=workspace:FindFirstChild('AssetAgentLab') if not lab then return 'no lab' end
local l={{}} for _,d in lab:GetDescendants() do if d:GetAttribute('AssetAgentVFX') then table.insert(l,d) end end
for _,d in l do if d:IsA('ParticleEmitter') and d:GetAttribute('EmitCount') then d:Clear() end end
play(l) return 'ok'"""


def serialize_script(path: str) -> str:
    """Luau returning the tagged-JSON tree of the instance at a dot path (e.g. workspace.Pack.Fire)."""
    return luau.SERIALIZE + f"""local i=game for seg in string.gmatch({json.dumps(path)},'[^.]+') do
 i=(i==game and seg=='workspace') and workspace or i:FindFirstChild(seg)
 if not i then return 'not found: '..seg end end
return serialize(i)"""


def list_script(path: str) -> str:
    """Luau listing the effect candidates under a dot path: name and counts of VFX instances."""
    return f"""local i=game for seg in string.gmatch({json.dumps(path)},'[^.]+') do
 i=(i==game and seg=='workspace') and workspace or i:FindFirstChild(seg)
 if not i then return 'not found: '..seg end end
local out={{}}
for _,c in i:GetChildren() do
 local n={{}} for _,d in c:GetDescendants() do
  if d:IsA('ParticleEmitter') or d:IsA('Beam') or d:IsA('Trail') or d:IsA('Light') then n[d.ClassName]=(n[d.ClassName] or 0)+1 end end
 local s={{}} for k,v in n do table.insert(s,k..'='..v) end
 if #s>0 then table.insert(out,c.Name..' ('..table.concat(s,' ')..')') end
end
return table.concat(out,'\\n')"""


def import_preset(serialized: dict, *, use: str, tags: list[str], source: dict) -> dict:
    """Turn SERIALIZE output into a preset. Emitters that start disabled are bursts: they get an
    EmitCount (from their Rate) unless the pack already set one."""
    burst = False

    def walk(n):
        nonlocal burst
        if n["class"] == "ParticleEmitter" and n["props"].get("Enabled") is False:
            burst = True
            attrs = n.setdefault("attrs", {}) or {}
            n["attrs"] = attrs
            attrs.setdefault("EmitCount", max(1, round(n["props"].get("Rate", 20) * 0.5)))
        for c in n.get("children") or []:
            walk(c)
    nodes = serialized["nodes"]
    for n in nodes:
        walk(n)
    out = {"tags": tags, "use": use, "source": source, "mode": "burst" if burst else "loop",
           "sketch": "sparkles", "stats": serialized.get("stats", {}), "nodes": nodes}
    if serialized.get("host"):  # the part it was built on: particles spawn through its volume
        out["host"] = serialized["host"]
    return out


# ---------------------------------------------------------------- R15 characters

def character_script(name: str, rev: str, mesh: dict) -> str:
    """Luau: an R15 rig named `name` (in place of the old one) wearing the character. Each body part's
    pieces (one per material, see worker.rig_mesh) are built in Studio as EditableMesh MeshParts (no
    upload needed), coloured, and welded to that part with the default body hidden, so any R15
    animation plays on it."""
    return f"""local HS,AS=game:GetService('HttpService'),game:GetService('AssetService')
local NAME,REV='{name}','{rev}'
local D=HS:JSONDecode({luau.data(mesh)})
local old=workspace:FindFirstChild(NAME) local pivot=old and old:GetPivot()
if old then old:Destroy() end
local rig=game:GetService('Players'):CreateHumanoidModelFromDescription(Instance.new('HumanoidDescription'),Enum.HumanoidRigType.R15)
rig.Name=NAME rig:SetAttribute('AssetAgentRev',REV)
local root=rig.HumanoidRootPart local up=rig.Humanoid.HipHeight+root.Size.Y/2
if not pivot then
 local cf=workspace.CurrentCamera.CFrame local at=cf.Position+cf.LookVector*15
 local hit=workspace:Raycast(at+Vector3.new(0,100,0),Vector3.new(0,-1000,0))
 local y=(hit and hit.Position.Y or 0)+up
 pivot=CFrame.lookAt(Vector3.new(at.X,y,at.Z),Vector3.new(cf.Position.X,y,cf.Position.Z))
end
rig:PivotTo(pivot)
for _,p in rig:GetDescendants() do
 if p:IsA('BasePart') then p.Transparency=1 end
 if p:IsA('Decal') then p:Destroy() end
end
local base=root.CFrame*CFrame.new(0,-up,0)
local skin=Instance.new('Model') skin.Name='Skin' skin.Parent=rig
local n,tris=0,0
for part,pieces in D do
 for i,pc in pieces do
  local em=AS:CreateEditableMesh() local t=pc.t
  for k=1,#t,9 do
   local a=em:AddVertex(Vector3.new(t[k],t[k+1],t[k+2]))
   local b=em:AddVertex(Vector3.new(t[k+3],t[k+4],t[k+5]))
   local c=em:AddVertex(Vector3.new(t[k+6],t[k+7],t[k+8]))
   em:AddTriangle(a,b,c) tris+=1
  end
  local mp=AS:CreateMeshPartAsync(Content.fromObject(em))
  mp.Name=part..'_'..i mp:SetAttribute('Mat',pc.mat) mp.Size=Vector3.new(pc.size[1],pc.size[2],pc.size[3])
  mp.CFrame=base*CFrame.new(pc.c[1],pc.c[2],pc.c[3])
  mp.Color=Color3.new(pc.color[1],pc.color[2],pc.color[3])
  mp.Material=pc.glow and Enum.Material.Neon or Enum.Material.SmoothPlastic
  mp.Anchored=false mp.CanCollide=false mp.Massless=true mp.CanQuery=false
  mp.Parent=skin
  local w=Instance.new('WeldConstraint') w.Part0=rig[part] w.Part1=mp w.Parent=mp
  n+=1
 end
end
root.Anchored=true
rig.Parent=workspace
return 'built '..NAME..': R15 rig wearing '..n..' mesh parts, '..tris..' tris'"""
