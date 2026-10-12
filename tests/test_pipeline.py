"""Pipeline core tests. Each runs real headless Blender, so the module shares one crate asset."""
import subprocess
from pathlib import Path

import pytest

from asset_agent import Asset, BlenderError, run_steps
from asset_agent.blender import find_blender

HERE = Path(__file__).parent
MESH_LAYERS = ("geometry", "topology", "uv", "surface", "collision")


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    out = tmp_path_factory.mktemp("fixtures")
    subprocess.run([find_blender(), "-b", "--factory-startup", "-P", str(HERE / "make_fixtures.py"), "--", str(out)],
                   check=True, capture_output=True)
    return out


@pytest.fixture(scope="module")
def crate(fixtures, tmp_path_factory):
    root = tmp_path_factory.mktemp("assets") / "crate_01"
    a = Asset.create(root, {"body": fixtures / "body.glb", "lid": fixtures / "lid.glb"},
                     budget="roblox_prop", max_tris=1500, tex_size=256)
    a.first_line = a.build()
    return a


def snapshot(a):
    return {p: (p.stat().st_mtime_ns, p.read_bytes()) for d in MESH_LAYERS for p in (a.root / d).glob("*")}


def test_initial_build(crate):
    line = crate.first_line
    assert line.startswith("v1: rebuilt geometry[body], geometry[lid]"), line
    s = crate.cur("export")["stats"]
    assert s["ok"], line
    assert 1000 < s["tris"] <= 1500
    assert s["tex"] == 256 and s["uv"] and s["non_manifold_edges"] == 0
    assert s["size_m"] == [1.05, 1.05, 1.4]
    assert (crate.root / "export/crate_01.glb").exists() and (crate.root / "export/crate_01.fbx").exists()
    assert len(list((crate.root / "export/collision").glob("*.glb"))) == 2
    for part in ("body", "lid"):  # bake picked up the source texture, not black
        assert sum(crate.cur(f"surface[{part}]")["stats"]["mean_rgb"]) > 0.3


def test_finish_only_touches_no_mesh_or_texture(crate):
    before = snapshot(crate)
    line = crate.revise("finish", roughness=0.2, metallic=0.5, tint=[1.0, 0.6, 0.6])
    assert "rebuilt finish, export;" in line, line
    assert snapshot(crate) == before


def test_part_geometry_edit_rebuilds_only_that_part(crate):
    body = {k: crate.cur(f"{k}[body]")["hash"] for k in MESH_LAYERS}
    lid_rgb = crate.cur("surface[lid]")["stats"]["mean_rgb"]
    line = crate.revise("geometry", part="lid", scale=[1, 1, 2])
    rebuilt = line.split("rebuilt ")[1].split(";")[0].split(", ")
    assert set(rebuilt) == {f"{k}[lid]" for k in MESH_LAYERS} | {"export"}, line
    assert body == {k: crate.cur(f"{k}[body]")["hash"] for k in MESH_LAYERS}
    # texture carried onto the new shape (sides got taller, so the average shifts a little)
    new_rgb = crate.cur("surface[lid]")["stats"]["mean_rgb"]
    assert sum(new_rgb) > 0.3 and max(abs(a - b) for a, b in zip(lid_rgb, new_rgb)) < 0.15, (lid_rgb, new_rgb)
    assert crate.cur("export")["stats"]["size_m"][2] > 1.5


def test_rollback_is_exact(crate):
    rec = crate.m["layers"]["topology[body]"]
    v_old, h_old = rec["current"], crate.cur("topology[body]")["hash"]
    crate.revise("topology", part="body", target_tris=400)
    assert crate.cur("topology[body]")["hash"] != h_old
    line = crate.rollback("topology", v_old, part="body")
    assert "restored topology[body]" in line, line
    assert crate.cur("topology[body]")["hash"] == h_old
    assert "rebuilt" in line and "uv[body]" not in line.split(";")[0], line  # downstream restored, not rebuilt


def test_noop_build(crate):
    assert "up to date" in crate.build()


def test_errors_are_one_line(tmp_path):
    with pytest.raises(BlenderError) as e:
        run_steps([{"op": "geometry", "part": "x", "src": str(tmp_path / "missing.glb"),
                    "out": str(tmp_path / "o.glb"), "params": {}}])
    msg = str(e.value)
    assert "\n" not in msg and len(msg) <= 300 and msg.startswith("step 0 geometry[x]"), msg
