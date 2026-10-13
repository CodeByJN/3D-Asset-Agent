"""Objective stats for each benchmark output -> stats.json (meshes via Blender, Studio outputs via Luau)."""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from asset_agent import studio_client  # noqa: E402

HERE = Path(__file__).parent
ROOT = HERE.parent
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
MESH = """import bpy,sys
from mathutils import Vector
f=sys.argv[-1]; bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.fbx(filepath=f)
ms=[o for o in bpy.context.scene.objects if o.type=='MESH']
pts=[o.matrix_world@Vector(c) for o in ms for c in o.bound_box]
h=max(p.z for p in pts)-min(p.z for p in pts)
tris=sum(len(p.vertices)-2 for o in ms for p in o.data.polygons)
mats=len({s.material.name for o in ms for s in o.material_slots if s.material})
print('STATS',tris,round(h,3),len(ms),mats)"""
AURA = """local i=workspace:FindFirstChild(%s) if not i then return '{}' end
local n={} for _,d in i:GetDescendants() do local c=d.ClassName
 if d:IsA('ParticleEmitter') or d:IsA('Beam') or d:IsA('Trail') or d:IsA('Light') or d:IsA('Highlight') or d:IsA('Script') or d:IsA('LocalScript') then n[c]=(n[c] or 0)+1 end end
local rate=0 for _,d in i:GetDescendants() do if d:IsA('ParticleEmitter') then rate+=d.Rate end end
n.total_rate=math.floor(rate) return game:GetService('HttpService'):JSONEncode(n)"""
ANIM = """local k=game.ServerStorage:FindFirstChild(%s) if not k then return '{}' end
local kf,len,poses=0,0,0 for _,c in k:GetChildren() do if c:IsA('Keyframe') then kf+=1 len=math.max(len,c.Time)
 for _,p in c:GetDescendants() do if p:IsA('Pose') then poses+=1 end end end end
return game:GetService('HttpService'):JSONEncode({length=len,keyframes=kf,poses=poses,loop=k.Loop,priority=k.Priority.Name})"""


def mesh(path):
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-expr", MESH, "--", str(path)],
                         capture_output=True, text=True).stdout
    tris, h, objs, mats = re.search(r"STATS (\d+) ([\d.]+) (\d+) (\d+)", out).groups()
    return {"tris": int(tris), "height": float(h), "objects": int(objs), "materials": int(mats), "file": str(path.relative_to(ROOT))}


def studio(code, name):
    return json.loads(studio_client.run(lambda s: s.luau(code % json.dumps(name))) or "{}")


P = {"native": ROOT / "bench/runs/native/palm_tree", "harness": ROOT / "assets/bench_palm_tree/export"}
stats = {
    "palm_tree": {s: {"v1": mesh(P[s] / f), "v2": mesh(P[s] / f.replace(".fbx", "_v2.fbx"))}
                  for s, f in (("native", "palm_tree.fbx"), ("harness", "bench_palm_tree.fbx"))},
    "ssj_aura": {s: {"v1": studio(AURA, f"BenchAura_{s}"), "v2": studio(AURA, f"BenchAura_{s}_v2")} for s in ("native", "harness")},
    "run_anim": {s: {"v1": studio(ANIM, f"BenchRun_{s}"), "v2": studio(ANIM, f"BenchRun_{s}_v2")} for s in ("native", "harness")},
}
(HERE / "stats.json").write_text(json.dumps(stats, indent=1) + "\n")
print(json.dumps(stats))
