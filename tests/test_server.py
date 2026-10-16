"""MCP server: tool definitions stay small, tools return one line, preview returns an image."""
import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from asset_agent import Asset, server
from asset_agent.blender import find_blender, run_steps

from .test_pipeline import HERE

TOOL_TOKEN_BUDGET = 2300  # plan: all tool definitions together under ~2k tokens (+ generate, and the job_next/job_submit stage tools)


def run(coro):
    return asyncio.run(coro)


def call(tool_name, **args):
    res = run(server.server.call_tool(tool_name, args))
    blocks = res[0] if isinstance(res, tuple) else res
    blocks = getattr(blocks, "content", blocks)
    return blocks


def text(blocks):
    return "\n".join(b.text for b in blocks if getattr(b, "type", "") == "text")


def test_tool_definitions_fit_token_budget():
    tools = run(server.server.list_tools())
    payload = json.dumps([t.model_dump(exclude_none=True) for t in tools])
    approx_tokens = len(payload) / 4
    assert len(tools) <= 18
    assert approx_tokens < TOOL_TOKEN_BUDGET, f"{approx_tokens:.0f} tokens"


@pytest.fixture(scope="module")
def home(tmp_path_factory):
    fx = tmp_path_factory.mktemp("fx")
    subprocess.run([find_blender(), "-b", "--factory-startup", "-P", str(HERE / "make_fixtures.py"), "--", str(fx)],
                   check=True, capture_output=True)
    h = tmp_path_factory.mktemp("home")
    Asset.create(h / "crate", {"body": fx / "body.glb", "lid": fx / "lid.glb"}, max_tris=1500, tex_size=128).build()
    mp = pytest.MonkeyPatch()
    mp.setenv("ASSET_AGENT_HOME", str(h))
    mp.setenv("ASSET_AGENT_REVIEW_PORT", "0")
    yield h
    mp.undo()


def test_tools_return_one_line(home):
    assert text(call("validate", name="crate")).startswith("ok tris=")
    line = text(call("revise", name="crate", layer="finish", change={"tint": [0.5, 0.5, 1]}))
    assert "rebuilt finish, export" in line and "\n" not in line
    assert "v2:" in text(call("rollback", name="crate"))
    assert text(call("library", query="cra")).startswith("crate: v2")
    err = text(call("validate", name="nope"))
    assert err.startswith("error: KeyError") and "crate" in err and "\n" not in err


def test_preview_is_an_image(home):
    blocks = call("preview", name="crate", size=256)
    img = [b for b in blocks if getattr(b, "type", "") == "image"]
    assert img and img[0].mime_type == "image/png"
    assert (home / "crate" / "preview.png").stat().st_size > 1000


def test_plan_and_rate(home):
    out = text(call("plan", project="obby", brief="chunky low poly", assets={"crate": "a wooden crate"},
                    style={"target_tris": 900}))
    assert out.startswith("project obby (private") and "brief 'chunky low poly'" in out and "target_tris=900" in out, out
    assert "no project" in text(call("rate", name="crate", stars=6))
    a = Asset(home / "crate")
    a.m["project"] = "obby"
    a._save()
    line = text(call("rate", name="crate", stars=8, note="nice planks"))
    assert line.startswith("rated crate v") and "8/10" in line and "\n" not in line, line
    assert "roster 1/1 made: crate(made 8/10)" in text(call("plan", project="obby"))
    assert text(call("rate", name="crate", stars=11)).startswith("error: ValueError")
    assert text(call("plan", project="obby", style={"bogus": 1})).startswith("error: KeyError")


def test_library_lists_vfx_presets(home):
    out = text(call("library", query="rarity"))
    assert "vfx rarity_mythic [rarity,wheel,aura]" in out, out


def test_rate_scores_vfx_presets(home, tmp_path, monkeypatch):
    import shutil
    from asset_agent import vfx
    lib = tmp_path / "presets.json"
    shutil.copy(vfx.library_path(), lib)
    monkeypatch.setenv("ASSET_AGENT_VFX", str(lib))
    assert text(call("rate", name="card_glint", stars=6, note="ok")) == "vfx preset card_glint scored 6/10"
    assert vfx.presets()["card_glint"]["score"] == 6
    assert "card_glint [item,pickup,steal] 6/10" in text(call("library", query="glint"))


def test_revise_recolors_a_preset(home, tmp_path, monkeypatch):
    import shutil
    from asset_agent import vfx
    lib = tmp_path / "presets.json"
    shutil.copy(vfx.library_path(), lib)
    monkeypatch.setenv("ASSET_AGENT_VFX", str(lib))
    line = text(call("revise", name="aura_black_card", layer="preset", change={"recolor": [0.2, 0.4, 1]}))
    assert line.startswith("aura_black_card v") and "\n" not in line, line
    assert vfx.raw_presets()["aura_black_card"]["recolor"] == [0.2, 0.4, 1]


def test_review_window_gets_every_new_version(home, monkeypatch):
    import threading
    from asset_agent import review
    monkeypatch.setattr(review.webbrowser, "open", lambda *a, **k: None)
    line = text(call("revise", name="crate", layer="finish", change={"roughness": 0.4}))
    assert "| review: http://127.0.0.1:" in line and "\n" not in line, line
    item = review.board(home).latest("crate")
    v = Asset(home / "crate").m["version"]
    assert item["v"] == v and Path(item["glb"]).parts[-2:] == (f"v{v}", "crate.glb") and item["line"].startswith("ok tris=")
    threading.Timer(0.3, review.decide, (home, item["id"], "next", 6, "solid planks", "lid too thin"),
                    {"scores": {"shape": 7, "surface": 6, "vfx": None, "function": None, "fit": 7}}).start()
    out = text(call("review", name="crate"))
    assert out.startswith(f"next: crate v{v} rated 6/10 (pros: solid planks; cons: lid too thin)"), out
    assert Asset(home / "crate").m["ratings"][-1] == {"v": v, "stars": 6, "note": "pros: solid planks; cons: lid too thin"}
    assert text(call("review", name="nope")).startswith("error: KeyError")


def test_review_asks_again_for_a_reviewed_version(home, monkeypatch):
    import threading
    from asset_agent import review
    monkeypatch.setattr(review.webbrowser, "open", lambda *a, **k: None)
    v = Asset(home / "crate").m["version"]
    server._queue("crate", "")  # a version already reviewed is queued again: the user is asked again
    item = review.board(home).latest("crate")
    assert item["v"] == v and item["decision"] is None
    threading.Timer(0.5, review.decide, (home, item["id"], "next", 7, "", "lid too thin"),
                    {"scores": {"shape": 7, "surface": 6, "vfx": None, "function": None, "fit": 7}}).start()
    out = text(call("review", name="crate"))
    assert out.startswith(f"next: crate v{v} rated 7/10 (cons: lid too thin)"), out


def test_place_without_upload_builds_it_live(home, monkeypatch, tmp_path):
    from asset_agent import config
    monkeypatch.setenv("ASSET_AGENT_CONFIG", str(tmp_path / "none.json"))  # no Roblox key saved
    for k in ("ROBLOX_API_KEY", "ROBLOX_USER_ID", "ROBLOX_GROUP_ID"):
        monkeypatch.delenv(k, raising=False)
    assert not config.load()
    a = Asset(home / "crate")
    line, script = a.to_studio()
    assert line.startswith("live build (no upload)"), line
    assert "AssetAgentLive" in script and f"crate/v{a.m['version']}/body" in script
    config.save(roblox_upload=True)  # uploads on, but no key: falls back to the live build and says why
    line, script = a.to_studio()
    assert line.startswith("live build (upload failed: Roblox upload isn't set up") and "AssetAgentLive" in script, line
    mesh = a.studio_mesh()
    tallest = max(d["c"][1] + d["size"][1] / 2 for d in mesh["parts"].values()) -         min(d["c"][1] - d["size"][1] / 2 for d in mesh["parts"].values())
    lo, hi = run_steps([{"op": "measure", "src": str(a.path(a.cur("export")["files"]["main"]))}])[0]["stats"]["bbox"]
    assert abs(tallest - (hi[2] - lo[2]) / 0.28) < 0.05, "the live mesh is in studs (0.28 m), the GLB in metres"


def test_upload_accepts_both_moderation_spellings(monkeypatch, tmp_path):
    from asset_agent import roblox
    monkeypatch.setenv("ROBLOX_API_KEY", "k" * 60)
    monkeypatch.setenv("ROBLOX_USER_ID", "1")
    fbx = tmp_path / "a.fbx"
    fbx.write_bytes(b"fbx")
    for state, ok in (("Approved", True), ("MODERATION_STATE_APPROVED", True), ("Reviewing", True), ("Rejected", False)):
        res = {"done": True, "response": {"assetId": "42", "moderationResult": {"moderationState": state}}}
        monkeypatch.setattr(roblox, "_request", lambda *a, **k: res)
        if ok:
            assert roblox.upload(fbx, "a") == "42"
        else:
            with pytest.raises(roblox.RobloxError):
                roblox.upload(fbx, "a")


def test_roblox_fbx_is_in_studs(home):
    """Roblox reads one FBX unit as one stud: the export writes metres / 0.28, not Blender's centimetres."""
    a = Asset(home / "crate")
    fbx = a.root / "export" / "crate.fbx"
    lo, hi = run_steps([{"op": "measure", "src": str(fbx)}])[0]["stats"]["bbox"]  # Blender reads it back in metres
    glo, ghi = run_steps([{"op": "measure", "src": str(a.path(a.cur("export")["files"]["main"]))}])[0]["stats"]["bbox"]
    ratio = (hi[2] - lo[2]) / (ghi[2] - glo[2])
    assert abs(ratio - 1 / (100 * 0.28)) < 0.002, ratio  # on import Blender undoes its cm, leaving 1/(100 x STUD)


def test_animate_queues_a_playable_review(home, monkeypatch):
    from asset_agent import review
    monkeypatch.setattr(review.webbrowser, "open", lambda *a, **k: None)
    line = text(call("animate", name="npc_wave", preset="wave", params={"fx": "sparkles"}))
    assert "| review: http://127.0.0.1:" in line, line
    item = review.board(home).latest("npc_wave")
    assert item["kind"] == "animation" and item["anim"]["frames"] and item["anim"]["rig"] is None
    head = item["anim"]["frames"][0]["Head"]
    assert len(head) == 12 and len(item["anim"]["frames"]) >= 4
    assert "fx" in item["fx"] and item["fx"]["fx"]["type"] == "sparkles"
    err = text(call("animate", name="npc_wave", params={"on": "crate"}))
    assert "isn't an R15 character" in err, err  # a model can't wear an animation


def test_lighting_presets():
    from asset_agent import lighting
    assert "lighting:shader_night" in lighting.catalog()
    s = lighting.script("shader_night")
    assert "BloomEffect" in s and "Atmosphere" in s and "AssetAgentLighting" in s and "ClockTime" in s
    with pytest.raises(KeyError):
        lighting.script("nope")


def test_portable_setup(monkeypatch, tmp_path):
    import json
    from pathlib import Path
    from asset_agent import blender, doctor, studio_client
    # .mcp.json has no machine-specific paths and runs as python -m (no generated .exe)
    cfg = json.loads((Path(__file__).parents[1] / ".mcp.json").read_text())["mcpServers"]
    assert {"asset-agent", "Roblox_Studio"} <= set(cfg)
    for s in cfg.values():
        assert s["command"] == "uv" and "-m" in s["args"] and "env" not in s
        assert not any(":\\" in a or "/Users/" in a for a in s["args"])
    # overrides
    monkeypatch.setenv("ASSET_AGENT_STUDIO_MCP", "/opt/studio-mcp|--stdio")
    p = studio_client.launcher()
    assert p.command == "/opt/studio-mcp" and p.args == ["--stdio"]
    fake = tmp_path / "blender.exe"
    fake.write_text("")
    monkeypatch.setenv("BLENDER_EXE", str(fake))
    assert blender.find_blender() == str(fake)
    monkeypatch.setenv("BLENDER_EXE", str(tmp_path / "missing"))
    with pytest.raises(blender.BlenderError, match="BLENDER_EXE"):
        blender.find_blender()
    monkeypatch.delenv("BLENDER_EXE")
    monkeypatch.delenv("ASSET_AGENT_STUDIO_MCP")
    rows = {name: ok for name, ok, _ in doctor.checks(live=False)}
    assert rows["python"] and rows["packages"] and rows[".mcp.json"] and rows["mcp tools"]


def test_make_asset_asks_for_a_brief_first(tmp_path, monkeypatch):
    from asset_agent import brief
    monkeypatch.setenv("ASSET_AGENT_HOME", str(tmp_path))
    out = text(call("make_asset", name="chest", prompt="a chest"))
    assert "Not generated yet" in out and "Reference image" in out and "Style" in out and "Colours" in out
    assert not (tmp_path / "chest").exists()  # nothing generated
    full = ("a low poly wooden treasure chest with gold trim, iron lock and a curved lid, slightly open, "
            "game asset for a pirate game")
    assert brief.gaps(full, "ref.png", budget="roblox_prop") == []
    assert len(brief.gaps(full, None, budget="roblox_prop")) == 1  # only the reference image
