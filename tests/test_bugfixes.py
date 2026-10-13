"""Bugs found by the native-vs-harness benchmark (docs/BENCHMARK.md)."""
import pytest

from asset_agent import Asset

from .test_pipeline import fixtures  # noqa: F401  (module fixture: builds the test meshes)


def two_colour_obj(d):
    """A script-built style model: two boxes with a plain coloured material each, no texture."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "m.mtl").write_text("newmtl trunk\nKd 0.45 0.25 0.1\nnewmtl leaves\nKd 0.1 0.6 0.15\n")
    v, f = [], []

    def box(x0, y0, z0, x1, y1, z1, mat):
        b = len(v) + 1
        v.extend((x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1))
        f.append(f"usemtl {mat}")
        for q in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
            f.append("f " + " ".join(str(b + i) for i in q))
    box(-0.1, -0.1, 0, 0.1, 0.1, 1.5, "trunk")
    box(-0.6, -0.6, 1.5, 0.6, 0.6, 1.8, "leaves")
    (d / "palm.obj").write_text("mtllib m.mtl\n" + "\n".join(f"v {x} {y} {z}" for x, y, z in v) + "\n" + "\n".join(f) + "\n")
    return d / "palm.obj"


def test_auto_surface_keeps_material_colours(tmp_path):
    a = Asset.create(tmp_path / "palm", {"main": two_colour_obj(tmp_path / "src")}, max_tris=800, tex_size=64)
    a.build()
    s = a.cur("surface[main]")["stats"]
    r, g, b = s["mean_rgb"]
    assert s["mode"] == "bake" and g > r and g > b, s  # coloured, not flat white/grey


def test_failed_revise_changes_nothing(fixtures, tmp_path):  # noqa: F811
    a = Asset.create(tmp_path / "box", {"body": fixtures / "body.glb"}, max_tris=800, tex_size=64)
    a.build()
    before = a.m["params"]["surface"]["body"].copy()
    with pytest.raises(Exception, match="needs an image"):
        a.revise("surface", mode="project")  # no reference image: the rebuild fails
    assert Asset(a.root).m["params"]["surface"]["body"] == before  # the bad setting wasn't kept
    assert a.revise("finish", tint=[1, 0.5, 0.5]).startswith("v2: rebuilt finish, export")  # next revise just works


def test_export_keeps_saved_copies_and_versions(fixtures, tmp_path):  # noqa: F811
    a = Asset.create(tmp_path / "box", {"body": fixtures / "body.glb"}, max_tris=800, tex_size=64)
    a.build()
    (a.root / "export" / "box_mine.fbx").write_text("a copy the user saved")
    a.revise("finish", tint=[0.5, 0.5, 1])
    assert (a.root / "export" / "box_mine.fbx").exists()
    for v in (1, 2):
        assert (a.root / "export" / "versions" / f"v{v}" / "box.fbx").exists()
