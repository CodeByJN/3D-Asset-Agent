"""Build the VFX Viewer page: python tools/vfx_viewer/build_viewer.py library/vfx/presets.json <texture dir with map.json> <out dir>."""
import json, shutil, sys
from pathlib import Path
lib, texdir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(Path(__file__).parents[2] / "src"))
import os  # noqa: E402
os.environ["ASSET_AGENT_VFX"] = str(lib.resolve())
from asset_agent import vfx  # noqa: E402
presets = vfx.presets()  # revisions (e.g. recolor) applied
order = sorted(presets, key=lambda k: (0 if k.startswith("cc_") else 1 if k.startswith("rei_") else 2))
presets = {k: presets[k] for k in order}
mapping = json.loads((texdir / "map.json").read_text())
(out / "tex").mkdir(parents=True, exist_ok=True)
for ref, f in mapping.items():
    shutil.copy(texdir / f, out / "tex" / f)
own = lib.parent / "textures"  # our generated textures, referenced as texture://<name>
for png in sorted(own.glob("*.png")):
    mapping[f"texture://{png.stem}"] = f"own_{png.name}"
    shutil.copy(png, out / "tex" / f"own_{png.name}")
tpl = (Path(__file__).with_name("viewer.template.html")).read_text(encoding="utf-8")
html = tpl.replace("__PRESETS__", json.dumps(presets, separators=(",", ":"))).replace("__TEXTURES__", json.dumps(mapping))
(out / "vfx-viewer.html").write_text(html, encoding="utf-8")
print(len(presets), "presets;", len(mapping), "textures;", (out / "vfx-viewer.html").stat().st_size // 1024, "KB page;",
      sum(p.stat().st_size for p in (out / "tex").iterdir()) // 1024, "KB textures")
