"""Put Kurama in the open Studio place and install his boss runtime.

The harness places the model (upload + insert, or a live build), then this fits the kit -> Studio
transform from the parts' positions, and writes the rig (joint pivots, axes, tail slam arcs) into the
model as RigData with the scripts: KuramaBoss (module), KuramaBrain (demo loop) and KuramaClient.
"""
import itertools
import json
import math
import time
from pathlib import Path

import numpy as np

import rig

HERE = Path(__file__).parent
NAME = "kurama"


def _luau_str(s: str) -> str:
    level = 1
    while f"]{'=' * level}]" in s:
        level += 1
    return f"[{'=' * level}[{s}]{'=' * level}]"


READ = """local HS=game:GetService('HttpService')
local m=workspace:FindFirstChild('%s') if not m then return 'missing' end
local P=m:GetPivot() local out={} local bottom=math.huge
for _,p in m:GetDescendants() do if p:IsA('BasePart') then
 local r=p:GetAttribute('Rest') if r then p.CFrame=P*r end
 out[p.Name]={p.Position.X,p.Position.Y,p.Position.Z}
 bottom=math.min(bottom,p.Position.Y-p.Size.Y/2) end end
return HS:JSONEncode({parts=out,bottom=bottom})""" % NAME


def fit(kit: dict, world: dict):
    """world ~ s * R @ kit + t over the parts both have, R a signed axis permutation."""
    names = [n for n in kit if n in world]
    A, B = np.array([kit[n] for n in names], float), np.array([world[n] for n in names], float)
    a0, b0 = A.mean(0), B.mean(0)
    best = None
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            R = np.zeros((3, 3))
            for i, (j, sg) in enumerate(zip(perm, signs)):
                R[i, j] = sg
            RA = (A - a0) @ R.T
            s = float(((B - b0) * RA).sum() / (RA * RA).sum())
            err = float((((B - b0) - s * RA) ** 2).sum())
            if s > 0 and (best is None or err < best[0]):
                best = (err, R, s)
    err, R, s = best
    return R, s, b0 - s * R @ a0, math.sqrt(err / len(names))


def _unit(v):
    v = np.array(v, float)
    return v / (np.linalg.norm(v) or 1)


def rig_world(R, s, t) -> dict:
    """The rig in Studio world space (install converts it to the model's pivot space)."""
    P = lambda p: list(s * R @ np.array(p, float) + t)  # noqa: E731
    D = lambda v: list(R @ _unit(v))  # noqa: E731
    bones = rig.bones()
    tails = []
    for i in range(rig.TAILS):
        path = rig.tail_path(i)
        d = _unit(np.subtract(path[12], path[0]))
        h = np.array([d[0], d[1], 0.0])
        h = _unit(h) if np.linalg.norm(h) > 0.3 else np.array([0.0, 1.0, 0.0])
        aim = _unit(h * math.cos(math.radians(28)) + np.array([0, 0, -1.0]) * math.sin(math.radians(28)))
        tails.append({"dir": D(d), "slam": D(aim), "tip": P(path[-3])})
    return {"bones": [{"name": n, "parent": b["parent"], "pivot": P(b["pivot"])} for n, b in bones.items()],
            "F": D((0, -1, 0)), "U": D((0, 0, 1)), "L": D((1, 0, 0)), "tails": tails,
            "mouth": P(rig.head_point((0.0, -72.0, 75.0))), "parts": {}}


INSTALL = r"""local HS=game:GetService('HttpService')
local W=HS:JSONDecode(%(world)s)
local m=workspace:FindFirstChild('%(name)s')
local function v(t) return Vector3.new(t[1],t[2],t[3]) end
local torso
for _,b in W.bones do if b.name=='Torso' then torso=v(b.pivot) end end
local F=v(W.F) local flat=Vector3.new(F.X,0,F.Z).Unit
local G=Vector3.new(torso.X,W.bottom,torso.Z)
local P=CFrame.lookAt(G,G+flat)
m.WorldPivot=P
local function ps(t) local p=P:PointToObjectSpace(v(t)) return {p.X,p.Y,p.Z} end
local function vs(t) local p=P:VectorToObjectSpace(v(t)) return {p.X,p.Y,p.Z} end
local D={F=vs(W.F),U=vs(W.U),L=vs(W.L),mouth=ps(W.mouth),bones={},tails={}}
for _,b in W.bones do table.insert(D.bones,{name=b.name,parent=b.parent,pivot=ps(b.pivot)}) end
for _,t in W.tails do table.insert(D.tails,{dir=vs(t.dir),slam=vs(t.slam),tip=ps(t.tip)}) end
local BONE=W.boneOf
local n=0
for _,p in m:GetDescendants() do if p:IsA('BasePart') and BONE[p.Name] then
 p:SetAttribute('Bone',BONE[p.Name]) p:SetAttribute('Rest',P:ToObjectSpace(p.CFrame)) p.Anchored=true
 if p.Name:sub(1,5)=='Mark_' then p.Transparency=1 end n+=1 end end
for _,k in {'RigData','KuramaBoss','KuramaBrain'} do local x=m:FindFirstChild(k) if x then x:Destroy() end end
local rd=Instance.new('StringValue') rd.Name='RigData' rd.Value=HS:JSONEncode(D) rd.Parent=m
local mod=Instance.new('ModuleScript') mod.Name='KuramaBoss' mod.Source=%(boss)s mod.Parent=m
local br=Instance.new('Script') br.Name='KuramaBrain' br.Source=%(brain)s br.Parent=m
if m:GetAttribute('Demo')==nil then m:SetAttribute('Demo',true) end
local RS=game:GetService('ReplicatedStorage')
if not RS:FindFirstChild('KuramaMove') then local e=Instance.new('RemoteEvent') e.Name='KuramaMove' e.Parent=RS end
local sps=game:GetService('StarterPlayer'):FindFirstChildOfClass('StarterPlayerScripts')
local old=sps:FindFirstChild('KuramaClient') if old then old:Destroy() end
local cl=Instance.new('LocalScript') cl.Name='KuramaClient' cl.Source=%(client)s cl.Parent=sps
return 'installed: '..n..' parts rigged on '..#D.bones..' bones'"""


def install() -> str:
    from asset_agent import server, studio_client
    from asset_agent.asset import Asset
    placed = server._place(NAME)
    a = Asset(server.home() / NAME)
    kit = a.m["build"]["centres"]
    got = json.loads(studio_client.run(lambda s: s.luau(READ)))
    R, s, t, rms = fit(kit, got["parts"])
    if rms > 2.0:
        raise RuntimeError(f"kit -> Studio fit is off by {rms:.1f} studs: parts don't line up")
    W = rig_world(R, s, t)
    W["bottom"] = got["bottom"]
    W["boneOf"] = {p: rig.bone_of(p) for p in got["parts"] if rig.bone_of(p) in rig.bones()}
    code = INSTALL % {"world": _luau_str(json.dumps(W)), "name": NAME,
                      "boss": _luau_str((HERE / "boss.luau").read_text(encoding="utf-8")),
                      "brain": _luau_str((HERE / "brain.luau").read_text(encoding="utf-8")),
                      "client": _luau_str((HERE / "client.luau").read_text(encoding="utf-8"))}
    res = studio_client.run(lambda s_: s_.luau(code))
    return f"{placed}\nfit: scale {s:.3f}, rms {rms:.2f} studs\n{res}"


# Edit-mode previews: a fresh copy of the module (require caches), posed or playing
PREVIEW = r"""local m=workspace:FindFirstChild('%(name)s')
_G.KuramaPreview=_G.KuramaPreview or {}
if _G.KuramaPreview.b then pcall(function() _G.KuramaPreview.b:stop() end) end
local Boss=require(m.KuramaBoss:Clone())
local b=Boss.new(m) _G.KuramaPreview.b=b
%(action)s
local P=m:GetPivot() local D=b.D
local F,U,L=P:VectorToWorldSpace(Vector3.new(unpack(D.F))),P:VectorToWorldSpace(Vector3.new(unpack(D.U))),P:VectorToWorldSpace(Vector3.new(unpack(D.L)))
local look=P.Position+U*%(look_up)s+F*%(look_fwd)s
local cam=look+(F*%(cf)s+L*%(cl)s+U*%(cu)s)
return game:GetService('HttpService'):JSONEncode({cam={cam.X,cam.Y,cam.Z},look={look.X,look.Y,look.Z}})"""

VIEWS = {"3q": dict(cf=190, cl=150, cu=40, look_up=60, look_fwd=0), "front": dict(cf=230, cl=0, cu=20, look_up=60, look_fwd=0),
         "side": dict(cf=0, cl=240, cu=30, look_up=60, look_fwd=0), "wide": dict(cf=330, cl=330, cu=140, look_up=40, look_fwd=200)}


def pose(shots, view="3q") -> str:
    """[(move, t)]: one screenshot per pose, saved under assets/kurama/studio/."""
    from asset_agent import server, studio_client
    out_dir = server.home() / NAME / "studio"

    async def fn(s):
        paths = []
        for move, t in shots:
            info = await s.luau(PREVIEW % {"name": NAME, "action": f"b:pose('{move}',{t})", **VIEWS[view]})
            d = json.loads(info)
            paths.append(str(await s.capture(out_dir / f"{move}_{t:g}_{view}.png", camera=d["cam"], look_at=d["look"])))
        await s.luau(PREVIEW % {"name": NAME, "action": "b:apply({})", **VIEWS[view]})
        return "\n".join(paths)
    return studio_client.run(fn)


def play(move, times, view="3q", chakra=False) -> str:
    """Play a move live in Edit mode and screenshot it at the given seconds."""
    from asset_agent import server, studio_client
    out_dir = server.home() / NAME / "studio"
    action = ("b:setMode('chakra') " if chakra else "") + f"b:start() b:play('{move}')"

    async def fn(s):
        t0 = time.time()
        d = json.loads(await s.luau(PREVIEW % {"name": NAME, "action": action, **VIEWS[view]}))
        paths = []
        for t in times:
            import asyncio
            await asyncio.sleep(max(0.0, t - (time.time() - t0)))
            paths.append(str(await s.capture(out_dir / f"play_{move}_{t:g}_{view}.png", camera=d["cam"], look_at=d["look"])))
        return "\n".join(paths)
    return studio_client.run(fn)


def stop() -> str:
    from asset_agent import studio_client
    return studio_client.run(lambda s: s.luau("if _G.KuramaPreview and _G.KuramaPreview.b then _G.KuramaPreview.b:stop() _G.KuramaPreview.b=nil end return 'stopped'"))
