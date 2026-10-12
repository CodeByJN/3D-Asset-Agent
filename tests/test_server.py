"""MCP server: tool definitions stay small, tools return one line, preview returns an image."""
import asyncio
import json
import subprocess

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
    assert len(tools) <= 10
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
    yield h
    mp.undo()


def test_tools_return_one_line(home):
    assert text(call("validate", name="crate")).startswith("ok tris=")
    line = text(call("revise", name="crate", layer="finish", change={"tint": [0.5, 0.5, 1]}))
    assert "rebuilt finish, export" in line and "\n" not in line
    assert "v2:" in text(call("history", name="crate"))
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
    assert out.startswith("project obby: brief 'chunky low poly'") and "target_tris=900" in out, out
    assert "no project" in text(call("rate", name="crate", stars=6))
    a = Asset(home / "crate")
    a.m["project"] = "obby"
    a._save()
    line = text(call("rate", name="crate", stars=8, note="nice planks"))
    assert line.startswith("rated crate v") and "8/10" in line and "\n" not in line, line
    assert "roster 1/1 made: crate(made 8/10)" in text(call("plan", project="obby"))
    assert text(call("rate", name="crate", stars=11)).startswith("error: ValueError")
    assert text(call("plan", project="obby", style={"bogus": 1})).startswith("error: KeyError")
