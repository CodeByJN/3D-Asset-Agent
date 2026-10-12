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

from . import config, vfx

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

def _c3(rgb):
    return "Color3.new(" + ",".join(f"{x:.3g}" for x in rgb) + ")"


def _effect_lua(fx) -> str:
    """One effect as Luau statements; `h` is the host part, `s` the model's size in studs."""
    c, z, r = fx["color"], fx["size"], fx["rate"]
    dark = [x * 0.55 for x in c]
    if fx["type"] == "glow":
        return (f"local e=Instance.new('PointLight') e.Color={_c3(c)} e.Range=math.min(60,s*1.5*{z:g}) "
                f"e.Brightness=2*{r:g}")
    tex, life, speed, rate, size, light, accel, trans = {
        "fire": ("fire_main", "0.6,1.2", "2,5", 60, "s*0.12,0", 1, "0,6,0", "0.2,1"),
        "smoke": ("smoke_main", "2,4", "1,2", 8, "s*0.1,s*0.25", 0, "0,1,0", "0.5,1"),
        "sparkles": ("sparkles_main", "0.5,1", "0.5,1.5", 25, "s*0.03,0", 1, "0,0,0", "0,1"),
    }[fx["type"]]
    s0, s1 = size.split(",")
    t0, t1 = trans.split(",")
    return (f"local e=Instance.new('ParticleEmitter') e.Texture='rbxasset://textures/particles/{tex}.dds' "
            f"e.Color=ColorSequence.new({_c3(c)},{_c3(dark)}) e.LightEmission={light} "
            f"e.Lifetime=NumberRange.new({life}) e.Speed=NumberRange.new({speed}) e.Rate={rate}*{r:g} "
            f"e.Size=NumberSequence.new({s0}*{z:g},{s1}*{z:g}) e.Transparency=NumberSequence.new({t0},{t1}) "
            f"e.Acceleration=Vector3.new({accel}) e.SpreadAngle=Vector2.new(15,15)")


def studio_script(name: str, asset_id: str, revision: str, effects: dict) -> str:
    """Compact Luau for Studio's execute_luau. Returns a one-line status string when run."""
    fx_lua = "\n".join(
        f"do {_effect_lua(fx)} e.Name='{n}' e:SetAttribute('AssetAgentVFX',true) e.Parent=h end"
        for n, fx in vfx.resolve(effects).items())
    return f"""local NAME,ID,REV='{name}',{asset_id},'{revision}'
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
for _,d in m:GetDescendants() do if d:GetAttribute('AssetAgentVFX') then d:Destroy() end end
local h=m.PrimaryPart or m:FindFirstChildWhichIsA('BasePart',true)
local _,bs=m:GetBoundingBox() local s=bs.Magnitude
{fx_lua}
return (loaded and 'loaded ' or 'kept model, ')..NAME..' with {len(effects)} effect(s)'"""
