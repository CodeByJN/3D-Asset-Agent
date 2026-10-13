"""Record benchmark outputs as GIF frames.

  record.py mesh  <file> <out_dir> [--height studs]     Blender turntable of a mesh file
  record.py aura  <instance path> <out_dir>             Studio frames of an aura on a character
  record.py anim  <KeyframeSequence path> <out_dir>     Studio frames of a run cycle on a blocky R15 puppet
"""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from asset_agent import studio_client  # noqa: E402

BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
HERE = Path(__file__).parent
FRAMES = 24
FPS = 30


def mesh(path, out, height=None):
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([BLENDER, "-b", "--factory-startup", "-P", str(HERE / "turntable.py"), "--",
                    str(Path(path).resolve()), str(out.resolve()), str(FRAMES), str(height or 0)],
                   check=True, capture_output=True)
    return out


async def _frames(s, out, cam, look, n=FRAMES, gap=0.08):
    for i in range(n):
        await s.capture(out / f"f{i:03d}.png", cam, look)
        await asyncio.sleep(gap)


def aura(path, out):
    """Real-time frames of whatever is playing on the character, from the front, 3/4 up."""
    out.mkdir(parents=True, exist_ok=True)
    code = f"""local i=game for seg in string.gmatch({json.dumps(path)},'[^.]+') do
 i=(i==game and seg=='workspace') and workspace or i:FindFirstChild(seg) if not i then return 'missing '..seg end end
local cf,size=i:GetBoundingBox() local root=i:FindFirstChild('HumanoidRootPart')
local c=root and root.CFrame or cf
local look=c.Position+Vector3.new(0,0.5,0) local cam=look+c.LookVector*11+Vector3.new(0,2,0)
return string.format('%g,%g,%g|%g,%g,%g',cam.X,cam.Y,cam.Z,look.X,look.Y,look.Z)"""

    async def go(s):
        r = (await s.luau(code)).strip()
        cam, look = ([float(x) for x in v.split(",")] for v in r.split("|"))
        await asyncio.sleep(1.0)
        await _frames(s, out, cam, look)
    studio_client.run(go)
    return out


def anim(path, out):
    """Pose a blocky R15 puppet frame by frame from the KeyframeSequence (forward kinematics in Luau,
    so it works in Edit mode without publishing the animation)."""
    out.mkdir(parents=True, exist_ok=True)
    setup = (HERE / "puppet.lua").read_text().replace("__KFS__", json.dumps(path))

    async def go(s):
        info = json.loads((await s.luau(setup + "\nreturn setup()")).strip())
        cam, look = info["cam"], info["look"]
        n = max(1, min(60, round(info["length"] * FPS)))  # real-time sampling, so speed differences show
        for i in range(n):
            t = info["length"] * i / n
            await s.luau(setup + f"\nreturn pose({t})")
            await s.capture(out / f"f{i:03d}.png", cam, look)
        await s.luau(setup + "\nreturn cleanup()")
    studio_client.run(go)
    return out


if __name__ == "__main__":
    kind, src, dst = sys.argv[1:4]
    t = time.time()
    if kind == "mesh":
        h = float(sys.argv[sys.argv.index("--height") + 1]) if "--height" in sys.argv else None
        mesh(src, Path(dst), h)
    else:
        {"aura": aura, "anim": anim}[kind](src, Path(dst))
    print(f"{dst} in {time.time() - t:.0f}s")
