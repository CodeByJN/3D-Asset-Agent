"""build(): Claude models in code with the kit; glow parts, versions, errors and the handoff file."""
import pytest

from asset_agent import Asset, roblox
from asset_agent.blender import BlenderError
from asset_agent.make import build_model, kit_help
from asset_agent.project import Project

CARD = """
gold = mat("gold", (1, 0.8, 0.3), metal=0.8, rough=0.3)
box((4, 0.3, 2.6), at=(0, 0, 1.6), m=mat("black", (0.05, 0.05, 0.06)), bevel=0.08)
box((0.9, 0.12, 0.7), at=(-1.1, -0.18, 1.9), m=gold)
tube([(-2, -0.2, 0.3), (0, -0.2, 0.3), (2, -0.2, 0.3)], 0.08, m=mat("rune", (1, 0.2, 0.1), glow=True))
"""


def test_build_versions_glow_and_handoff(tmp_path):
    p = Project.open(tmp_path, "game", create=True)
    line, img = build_model(tmp_path / "card", CARD, spec={"shape": "black card, gold chip, red rune line"}, project=p)
    assert line.startswith("build v1") and "ok tris=" in line and img.exists(), line
    a = Asset(tmp_path / "card")
    assert set(a.m["parts"]) == {"main", "glow_rune"}
    assert a.finish["parts"]["glow_rune"]["tint"] == [1, 0.2, 0.1]
    assert a.cur("surface[main]")["stats"]["mode"] == "bake"  # material colours kept
    script = roblox.studio_script("card", "1", "r", {}, {"glow_rune": [1, 0.2, 0.1]})
    assert "Enum.Material.Neon" in script and "glow_rune" in script
    hand = (p.root / "HANDOFF.md").read_text()
    assert "black card, gold chip" in hand and "build/v1/build.py" in hand

    line, _ = build_model(tmp_path / "card", CARD.replace("glow=True", "glow=False"), project=p)  # v2: no glow
    a = Asset(tmp_path / "card")
    assert line.startswith("build v2") and set(a.m["parts"]) == {"main"}, line
    assert (tmp_path / "card" / "build" / "v1" / "build.py").exists()  # earlier code kept


def test_build_errors_point_at_the_line(tmp_path):
    with pytest.raises(BlenderError, match="line 2"):
        build_model(tmp_path / "bad", "box()\nnope(1)\n")


def test_kit_help_readable_without_blender():
    assert "blade(" in kit_help() and "studs" in kit_help()
