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
    from asset_agent import roblox, vfx
    from .test_pipeline import snapshot

    a = Asset.create(tmp_path / "torch", {"body": fixtures / "body.glb"}, max_tris=800, tex_size=128)
    a.build()
    uploads = []
    monkeypatch.setenv("ASSET_AGENT_CONFIG", str(tmp_path / "config.json"))
    (tmp_path / "config.json").write_text('{"roblox_upload": true}')  # uploads are opt-in; live builds are the default
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
    import colorsys
    blue = vfx.resolve({"f": {"type": "fire", "color": [0, 0.3, 1]}})["f"]["color"]
    assert abs(colorsys.rgb_to_hsv(*blue)[0] - colorsys.rgb_to_hsv(0, 0.3, 1)[0]) < 0.01, blue  # flames turned blue
    assert "fire_main" in script and "flames=fire" in line

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


def test_vfx_transforms_and_import():
    from asset_agent import roblox, vfx
    nodes = [{"class": "Attachment", "name": "A0", "props": {"CFrame": {"cf": [0, 2, 0, 0, 90, 0]}}, "children": [
        {"class": "ParticleEmitter", "name": "P", "props": {
            "Size": {"ns": [[0, 1, 0.5], [1, 0, 0]]}, "Speed": {"nr": [2, 4]}, "Rate": 10,
            "Color": {"cs": [[0, 1, 0.5, 0], [1, 0.5, 0.25, 0]]}, "Enabled": False}}]},
        {"class": "Beam", "name": "B", "props": {"Width0": 2, "Attachment0": {"ref": "A0"},
                                                  "Color": {"cs": [[0, 1, 1, 1], [1, 1, 1, 1]]}}},
        {"class": "Part", "name": "Ring", "props": {"Size": {"v3": [4, 0.2, 4]}, "CFrame": {"cf": [1, 0, 0, 0, 0, 0]}},
         "tween": {"time": 0.4, "props": {"Size": {"v3": [8, 0.2, 8]}, "Transparency": 1}}}]
    out = vfx.transform(nodes, k=2, rate=3, rgb=[0, 0, 1])
    a, beam, ring = out
    pe = a["children"][0]["props"]
    assert a["props"]["CFrame"]["cf"] == [0, 4, 0, 0, 90, 0]  # position scales, rotation doesn't
    assert pe["Size"]["ns"] == [[0, 2, 1], [1, 0, 0]] and pe["Speed"]["nr"] == [4, 8] and pe["Rate"] == 30
    assert pe["Color"]["cs"] == [[0, 0, 0, 1], [1, 0, 0, 0.5]]  # hue swapped, brightness kept
    assert beam["props"]["Width0"] == 4 and beam["props"]["Attachment0"] == {"ref": "A0"}
    assert ring["props"]["Size"]["v3"] == [8, 0.4, 8] and ring["tween"]["props"]["Size"]["v3"] == [16, 0.4, 16]
    assert nodes[0]["props"]["CFrame"]["cf"][1] == 2  # input untouched
    assert vfx.main_colour(nodes) == [1, 0.5, 0]

    p = roblox.import_preset({"nodes": nodes, "stats": {"ParticleEmitter": 1}}, use="u", tags=["t"],
                             source={"kind": "creator_store", "asset_id": "1"})
    assert p["mode"] == "burst" and p["nodes"][0]["children"][0]["attrs"]["EmitCount"] == 5
    assert roblox.luau.data({"s": "x"}).startswith("[=[") and roblox.luau.data({"s": "]=]"}).startswith("[==[")


def test_video_from_frames(fixtures, tmp_path):  # noqa: F811
    from asset_agent.blender import run_steps
    out = tmp_path / "clip.mp4"
    frames = [str(fixtures / f) for f in ("body.png", "lid.png", "body.png", "lid.png")]
    res = run_steps([{"op": "video", "frames": frames, "fps": 4, "width": 128, "out": str(out)}])
    assert res[0]["stats"] == {"frames": 4, "fps": 4}
    assert out.stat().st_size > 1000 and out.read_bytes()[4:8] == b"ftyp"  # an MP4 container


def test_aura_scaling_and_textures():
    from asset_agent import roblox, vfx
    nodes = [{"class": "BillboardGui", "name": "T", "props": {"Size": {"u2": [10, 0, 5, 0]}, "StudsOffset": {"v3": [0, 4, 0]}},
              "children": [{"class": "TextLabel", "name": "N", "props": {"Size": {"u2": [1, 0, 0.3, 0]}}}]},
             {"class": "Plane", "name": "P", "props": {"Image": "texture://glow", "Size": {"v2": [6, 6]}},
              "anim": {"orbit": {"radius": 3, "y": 1, "speed": 40}}}]
    out = vfx.transform(nodes, k=2)
    board, plane = out
    assert board["props"]["Size"]["u2"] == [20, 0, 10, 0] and board["props"]["StudsOffset"]["v3"] == [0, 8, 0]
    assert board["children"][0]["props"]["Size"]["u2"] == [1, 0, 0.3, 0]  # GUI fractions don't scale
    assert plane["props"]["Size"]["v2"] == [12, 12] and plane["anim"]["orbit"] == {"radius": 6, "y": 2, "speed": 40}
    res = vfx.resolve_textures(nodes, {"glow": "rbxassetid://5"})
    assert res[1]["props"]["Image"] == "rbxassetid://5" and nodes[1]["props"]["Image"] == "texture://glow"
    assert vfx.resolve_textures(nodes, {})[1]["props"]["Image"] == vfx.STAND_IN  # never invisible
    script = roblox.lab_script("aura_black_card")
    assert "StandIn" in script and "HumanoidRootPart" in script and "animate(rig" in script


def test_procedural_meshes():
    import math
    from asset_agent import roblox, vfx, vfx_meshes
    for spec in ("sphere?sub=3", "sphere?sub=2&noise=0.2&seed=1", "torus?tube=0.02", "crystal?sides=7&seed=3",
                 "blade?hook=0.3", "cube", "shard?seed=4", "globe?seg=24&rings=12", "frame", "blade_edge?hook=0.3"):
        d = vfx_meshes.mesh_data("mesh://" + spec)
        v = [d["v"][i:i + 3] for i in range(0, len(d["v"]), 3)]
        assert len(d["f"]) % 3 == 0 and max(d["f"]) < len(v)
        for ax in range(3):  # fits the unit box, so a node's Size is its size in studs (edges: their body's box)
            ext = max(p[ax] for p in v) - min(p[ax] for p in v)
            assert (1 <= ext < 1.1) if spec.startswith(("frame", "blade_edge")) else math.isclose(ext, 1, abs_tol=2e-3), spec
        # outward winding: the signed volume of a closed outward mesh is positive
        vol = sum(a[0] * (b[1] * c[2] - b[2] * c[1]) + a[1] * (b[2] * c[0] - b[0] * c[2]) + a[2] * (b[0] * c[1] - b[1] * c[0])
                  for a, b, c in ([v[d["f"][i]], v[d["f"][i + 1]], v[d["f"][i + 2]]] for i in range(0, len(d["f"]), 3)))
        assert vol > 0, spec
    uv = vfx_meshes.mesh_data("globe?seg=24&rings=12")["uv"]  # a globe carries one UV per vertex
    assert len(uv) * 3 == len(vfx_meshes.mesh_data("globe?seg=24&rings=12")["v"]) * 2 and 0 <= min(uv) and max(uv) <= 1
    with pytest.raises(ValueError):
        vfx_meshes.build("mesh://teapot")
    nodes = [{"class": "MeshPart", "name": "M", "props": {"MeshId": "mesh://cube?bevel=0.1"},
              "anim": {"orbit": {"radius": 3, "center": [0, 1, 0]}}}]
    meshes = {}
    vfx.resolve_textures(nodes, {}, inline={}, meshes=meshes)
    assert list(meshes) == ["cube?bevel=0.1"] and meshes["cube?bevel=0.1"]["f"]
    assert vfx.transform(nodes, k=2)[0]["anim"]["orbit"]["center"] == [0, 2, 0]
    assert "setMeshes(" in roblox.lab_script("aura_equinox")


def test_recolor_revision(tmp_path, monkeypatch):
    import colorsys
    import shutil
    from asset_agent import vfx
    lib = tmp_path / "presets.json"
    shutil.copy(vfx.library_path(), lib)
    monkeypatch.setenv("ASSET_AGENT_VFX", str(lib))
    before = vfx.raw_presets()["aura_black_card"]
    line = vfx.revise_preset("aura_black_card", "make it red", recolor=[1, 0.12, 0.1])
    assert line.startswith("aura_black_card v") and "recolor" in line
    raw, red = vfx.raw_presets()["aura_black_card"], vfx.presets()["aura_black_card"]
    assert raw["nodes"] == before["nodes"] and raw["history"][-1]["v"] == before["version"]  # recipe untouched
    crown = next(n for n in red["nodes"] if n.get("name") == "Crown")["props"]["Color"]["c3"]
    assert colorsys.rgb_to_hsv(*crown)[0] < 0.03 or colorsys.rgb_to_hsv(*crown)[0] > 0.97, crown  # red now
    title = red["nodes"][0]["children"][1]["children"][0]["props"]["Color"]["cs"]
    assert title[0][1:] == [1, 1, 1]  # white highlight stays white
    vfx.revise_preset("aura_black_card", "back to gold", recolor=None)
    assert vfx.presets()["aura_black_card"]["nodes"] == before["nodes"]  # rolled back exactly


def test_asset_mesh_from_glb(tmp_path, monkeypatch):
    import json
    import struct
    import numpy as np
    from asset_agent import vfx_meshes
    pos = np.array([[0, 0, 0], [2, 0, 0], [0, 1, 0], [0, 0, 4]], np.float32)
    idx = np.array([0, 1, 2, 0, 2, 3], np.uint16)
    binary = pos.tobytes() + idx.tobytes()
    g = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
         "nodes": [{"mesh": 0, "translation": [5, 0, 0]}], "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
         "buffers": [{"byteLength": len(binary)}],
         "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 48}, {"buffer": 0, "byteOffset": 48, "byteLength": 12}],
         "accessors": [{"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3"},
                       {"bufferView": 1, "componentType": 5123, "count": 6, "type": "SCALAR"}]}
    js = json.dumps(g).encode()
    js += b" " * (-len(js) % 4)
    binary += b"\0" * (-len(binary) % 4)
    data = (struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binary)) + struct.pack("<II", len(js), 0x4E4F534A)
            + js + struct.pack("<II", len(binary), 0x004E4942) + binary)
    (tmp_path / "hero" / "export").mkdir(parents=True)
    (tmp_path / "hero" / "export" / "hero.glb").write_bytes(data)
    v, f = vfx_meshes.glb_mesh(tmp_path / "hero" / "export" / "hero.glb")
    assert len(v) == 4 and f == [(0, 1, 2), (0, 2, 3)] and v[1] == (7, 0, 0)  # node translation applied
    monkeypatch.setenv("ASSET_AGENT_HOME", str(tmp_path))
    d = vfx_meshes.mesh_data("mesh://asset/hero")
    assert len(d["f"]) == 6 and max(d["v"]) == 0.5
    with pytest.raises(ValueError):
        vfx_meshes.build("mesh://asset/nothing")
