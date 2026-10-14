"""MCP server: tool definitions stay small, tools return one line, preview returns an image."""
import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from asset_agent import Asset, server
from asset_agent.blender import find_blender

from .test_pipeline import HERE

TOOL_TOKEN_BUDGET = 2000  # plan: all tool definitions together under ~2k tokens


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
    assert len(tools) <= 15
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
    threading.Timer(0.3, review.decide, (home, item["id"], "next", 6, "solid planks", "lid too thin")).start()
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
    threading.Timer(0.5, review.decide, (home, item["id"], "next", 7, "", "lid too thin")).start()
    out = text(call("review", name="crate"))
    assert out.startswith(f"next: crate v{v} rated 7/10 (cons: lid too thin)"), out


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
