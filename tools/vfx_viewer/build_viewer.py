"""Build the VFX Viewer page: python tools/vfx_viewer/build_viewer.py library/vfx/presets.json <texture dir with map.json> <out dir>."""
import json, shutil, sys
from pathlib import Path
lib, texdir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
presets = {k: v for k, v in json.loads(lib.read_text()).items() if not k.startswith("_")}
order = sorted(presets, key=lambda k: (not k.startswith("rei_"), 0))
presets = {k: presets[k] for k in order}
mapping = json.loads((texdir / "map.json").read_text())
(out / "tex").mkdir(parents=True, exist_ok=True)
for ref, f in mapping.items():
    shutil.copy(texdir / f, out / "tex" / f)
tpl = (Path(__file__).with_name("viewer.template.html")).read_text(encoding="utf-8")
html = tpl.replace("__PRESETS__", json.dumps(presets, separators=(",", ":"))).replace("__TEXTURES__", json.dumps(mapping))
(out / "vfx-viewer.html").write_text(html, encoding="utf-8")
print(len(presets), "presets;", len(mapping), "textures;", (out / "vfx-viewer.html").stat().st_size // 1024, "KB page;",
      sum(p.stat().st_size for p in (out / "tex").iterdir()) // 1024, "KB textures")
