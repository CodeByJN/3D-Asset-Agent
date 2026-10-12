"""Geometry swaps that keep scale + texture, per-layer previews, and projects with ratings."""
import pytest

from asset_agent import Asset
from asset_agent.project import Project

from .test_pipeline import fixtures  # noqa: F401  (module fixture: builds the test meshes)


def test_swap_keeps_scale_and_texture(fixtures, tmp_path):  # noqa: F811
    a = Asset.create(tmp_path / "box", {"body": fixtures / "body.glb"}, max_tris=800, tex_size=128)
    a.build()
    size, rgb = a.cur("export")["stats"]["size_m"], a.cur("surface[body]")["stats"]["mean_rgb"]
    # body2 is the same kind of shape at twice the size, with a different texture
    line = a.revise("geometry", part="body", source=fixtures / "body2.glb")
    assert "rebuilt geometry[body]" in line, line
    s = a.cur("surface[body]")["stats"]
    assert s["mode"] == "transfer" and s["cover"] >= 0.85, s
    assert max(abs(x - y) for x, y in zip(rgb, s["mean_rgb"])) < 0.12, (rgb, s["mean_rgb"])  # old texture kept
    new = a.cur("export")["stats"]["size_m"]
    assert max(new) == pytest.approx(max(size), abs=0.01), (size, new)  # proportions kept, largest side fits

    a.revise("geometry", part="body", source=fixtures / "body2.glb", stretch=True)
    assert a.cur("export")["stats"]["size_m"] == pytest.approx(size, abs=0.01)

    a.revise("geometry", part="body", source=fixtures / "body2.glb", keep=[])
    assert a.cur("export")["stats"]["size_m"][2] > 2.5  # taken as-is
    assert a.cur("surface[body]")["stats"]["mode"] == "bake"  # its own texture, not the old one


def test_swap_falls_back_to_projection(fixtures, tmp_path):  # noqa: F811
    a = Asset.create(tmp_path / "proj", {"body": fixtures / "body.glb"}, max_tris=800, tex_size=128,
                     images={"body": fixtures / "body.png"}, surface_mode="project")
    a.build()
    a.revise("geometry", part="body", source=fixtures / "lid.glb")  # a slab: too unlike the box to bake from
    s = a.cur("surface[body]")["stats"]
    assert s["mode"] == "project" and s["cover"] < 0.85, s


def test_layer_previews(fixtures, tmp_path):  # noqa: F811
    a = Asset.create(tmp_path / "crate", {"body": fixtures / "body.glb", "lid": fixtures / "lid.glb"},
                     max_tris=800, tex_size=128)
    a.build()
    for layer in ("breakdown", "colour", "topology"):
        out = a.preview(128, layer)
        assert out.name == f"preview-{layer}.png" and out.stat().st_size > 1000
    assert set(a.tints()) == {"body", "lid"}
    with pytest.raises(KeyError):
        a.preview(128, "nope")


def test_project_defaults_and_learning(tmp_path):
    p = Project.open(tmp_path, "obby", create=True)
    p.update(brief="chunky low poly, bright flat colours", style="flat", palette=[[1, 0, 0], [0, 0.6, 0]],
             sizes={"tree": 6, "pine tree": 9}, target_tris=600, assets=["oak_tree: a round oak tree", "crate"])
    d = p.defaults("oak_tree", None)
    assert d["prompt"] == "a round oak tree, chunky low poly, bright flat colours"
    assert d["style"] == "flat" and d["target_tris"] == 600 and d["scale_to"] == 6
    assert p.defaults("big", "a pine tree")["scale_to"] == 9  # longest matching size word wins
    assert p.snap([0.1, 0.5, 0.1]) == [0, 0.6, 0]

    base = {"target_tris": 600, "tex_size": 512, "ao": 0.5, "roughness": 0.8, "metallic": 0.0}
    p.rate("oak_tree", 1, 3, "noisy leaves", {**base, "ao": 0.9}, "x")
    p.rate("oak_tree", 2, 9, "clean chunky shape", {**base, "ao": 0.4}, "x")
    line = p.rate("crate", 1, 8, "", {**base, "ao": 0.6, "tex_size": 256}, "y")
    assert "learned" in line and "ao->0.5" in line, line  # (0.4*3 + 0.6*2) / 5, the bad 0.9 ignored
    assert p.d["learned"]["tex_size"] == 512
    assert Project.open(tmp_path, "obby").defaults("crate", "c")["ao"] == 0.5
    s = p.summary()
    assert "liked: 'clean chunky shape'(9)" in s and "avoid: 'noisy leaves'(3)" in s, s
    assert "roster 2/2 made" in s, s
    with pytest.raises(KeyError):
        Project.open(tmp_path, "missing")


def test_vfx_only_change_touches_nothing_else(fixtures, tmp_path, monkeypatch):  # noqa: F811
    from asset_agent import roblox
    from .test_pipeline import snapshot

    a = Asset.create(tmp_path / "torch", {"body": fixtures / "body.glb"}, max_tris=800, tex_size=128)
    a.build()
    uploads = []
    monkeypatch.setattr(roblox, "upload", lambda fbx, name, asset_id=None: uploads.append(asset_id) or "777")
    line, script = a.to_studio()
    assert line.startswith("asset 777 created") and "LoadAsset(ID)" in script and uploads == [None]

    files = snapshot(a)
    export_hash = a.cur("export")["hash"]
    line = a.revise("vfx", flames={"type": "fire", "color": [1, 0.4, 0]})
    assert "rebuilt vfx;" in line and "export" not in line.split(";")[0], line
    line = a.revise("vfx", flames={"color": [0, 0.3, 1]})  # only the colour changes
    assert snapshot(a) == files and a.cur("export")["hash"] == export_hash
    line, script = a.to_studio()
    assert line.startswith("asset 777 unchanged") and uploads == [None], line  # no re-upload
    assert "Color3.new(0,0.3,1)" in script and "fire_main" in script and "flames=fire" in line

    a.rollback("vfx", 2)  # back to orange
    assert a.effects["flames"]["color"] == [1, 0.4, 0]
    a.revise("vfx", flames=None)
    assert a.effects == {}
    with pytest.raises(KeyError):
        a.revise("vfx", boom={"type": "nuke"})

    a.revise("geometry", part="body", scale=[1, 1, 1.5])  # model changed: uploads a new version
    line, _ = a.to_studio()
    assert line.startswith("asset 777 new version uploaded") and uploads == [None, "777"], line


def test_breakdown_strip(fixtures, tmp_path):  # noqa: F811
    a = Asset.create(tmp_path / "s", {"body": fixtures / "body.glb"}, max_tris=800, tex_size=128)
    a.build()
    a.revise("vfx", sparkle={"type": "sparkles"})
    out = a.preview(256, "breakdown")
    png = out.read_bytes()
    w, h = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    assert (w, h) == (5 * 128, 128)
    assert a.preview(128, "vfx").stat().st_size > 1000
