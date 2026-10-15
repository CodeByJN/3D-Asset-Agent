"""The Blender MCP session: inspect a deliberately broken mesh, clean it, export it for Roblox (real Blender)."""
from pathlib import Path

import pytest

from asset_agent.session import BlenderSession


def dirty_obj(path: Path):
    """A cube whose faces don't share vertices (unwelded), one face turned inside out, a stray edge
    and a small floating cube: what raw generated meshes tend to have."""
    lines, n = [], 0

    def cube(c, s, flip_one=False):
        nonlocal n
        cx, cy, cz = c
        quads = [((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)), ((0, 0, 1), (0, 1, 1), (1, 1, 1), (1, 0, 1)),
                 ((0, 0, 0), (0, 0, 1), (1, 0, 1), (1, 0, 0)), ((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)),
                 ((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)), ((1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0))]
        for k, q in enumerate(quads):
            for v in q:  # four fresh vertices per face: nothing welded
                lines.append(f"v {cx + v[0] * s} {cy + v[1] * s} {cz + v[2] * s}")
            idx = [n + 1, n + 4, n + 3, n + 2] if not (flip_one and k == 0) else [n + 1, n + 2, n + 3, n + 4]
            lines.append("f " + " ".join(map(str, idx)))
            n += 4
    cube((0, 0, 0), 2.0, flip_one=True)
    cube((5, 0, 0), 0.2)
    lines += ["v 9 9 9", "v 9 9 10", f"l {n + 1} {n + 2}"]  # a stray edge
    path.write_text("\n".join(lines) + "\n")
    return path


@pytest.fixture(scope="module")
def s():
    b = BlenderSession()
    yield b
    b.close()


def test_inspect_finds_the_problems(s, tmp_path):
    m = s.call("open", path=str(dirty_obj(tmp_path / "dirty.obj")), name="dirty")
    assert m["duplicate_verts"] > 0
    assert m["loose_edges"] == 1
    assert m["islands"] >= 3
    assert not m["roblox_ready"]
    assert any("duplicate" in i for i in m["issues"])


def test_cleanup_then_export(s, tmp_path):
    s.call("open", path=str(dirty_obj(tmp_path / "dirty.obj")), name="crate")
    r = s.call("cleanup", name="crate", ops=[
        {"op": "merge_by_distance"}, {"op": "delete_loose"}, {"op": "recalc_normals"},
        {"op": "keep_largest"}, {"op": "scale_to", "studs": 4}, {"op": "uv_unwrap"},
        {"op": "bake_texture", "size": 64}])
    m = r["after"]
    assert m["duplicate_verts"] == 0 and m["loose_edges"] == 0 and m["flipped_faces"] == 0
    assert m["islands"] == 1 and m["boundary_edges"] == 0
    assert m["units"] == "studs" and abs(max(m["size"]) - 4) < 0.01
    assert len(m["textures"]) == 1 and m["materials"] == 1
    assert m["roblox_ready"], m["issues"]
    files = s.call("export", name="crate", out_dir=str(tmp_path / "out"))["files"]
    assert Path(files["glb"]).stat().st_size > 0 and Path(files["fbx"]).stat().st_size > 0


def test_run_and_errors(s):
    out = s.call("run", code="print(len(obj.data.vertices)); result = obj.name", name="crate")
    assert out["result"] == "crate"
    with pytest.raises(Exception, match="no mesh"):
        s.call("inspect", name="nope")
    with pytest.raises(Exception, match="ZeroDivisionError"):
        s.call("run", code="1/0")
    assert s.call("list")["meshes"]  # the session survived the errors
