"""Thin bridge to Roblox Studio's own MCP tools, for benchmark runs (both sides get it).

  python bench/luau.py script.lua            run Luau in the open place (Studio's execute_luau, Edit)
  python bench/luau.py -e "return 1+1"       run inline Luau
  python bench/luau.py --capture out.png --camera x,y,z --look x,y,z   viewport screenshot (screen_capture)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from asset_agent import studio_client  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("file", nargs="?")
ap.add_argument("-e", dest="code")
ap.add_argument("--capture")
ap.add_argument("--camera")
ap.add_argument("--look")
a = ap.parse_args()
vec = lambda s: [float(x) for x in s.split(",")] if s else None
if a.capture:
    print(studio_client.run(lambda s: s.capture(Path(a.capture), vec(a.camera), vec(a.look))))
else:
    code = a.code if a.code is not None else Path(a.file).read_text(encoding="utf-8")
    print(studio_client.run(lambda s: s.luau(code)))
