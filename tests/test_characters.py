"""character() and preview(layer='studio'): the parts that don't need Studio."""
import json

import pytest
from PIL import Image

from asset_agent import characters


def test_contact_sheet_numbers_candidates_after_refs(tmp_path):
    ref = tmp_path / "ref.png"
    Image.new("RGB", (100, 140), (200, 50, 50)).save(ref)
    shots = []
    for i in (1, 2, 3):
        f = tmp_path / f"c{i}.png"
        Image.new("RGB", (400, 300), (40 * i, 90, 140)).save(f)
        shots.append((i, f))
    out = characters.contact_sheet(shots, tmp_path / "sheet.png", [str(ref), str(tmp_path / "missing.png")])
    im = Image.open(out)
    assert im.size == (4 * 220, int(220 * 1.25))  # ref + 3 candidates in one row; unreadable refs are skipped
    assert im.getpixel((110, 140))[0] > 150  # the reference comes first


def test_blank_viewport_is_detected(tmp_path):
    flat, busy = tmp_path / "flat.png", tmp_path / "busy.png"
    Image.new("RGB", (300, 200), (27, 28, 33)).save(flat)
    im = Image.new("RGB", (300, 200))
    im.putdata([((x * 7) % 255, (y * 5) % 255, 90) for y in range(200) for x in range(300)])
    im.save(busy)
    assert characters.blank(flat) and not characters.blank(busy)


def test_compose_script_carries_the_studio_fixes():
    code = characters.compose_script("gon", {"shirt": 2, "hair": "3", "face": 3})
    assert '"hair":3' in code  # picks are numbers
    assert "MeshType.Head" in code and "head.Transparency=1" in code  # faces on a classic head
    assert "IS:LoadAsset" in code  # decal asset ids resolved to images
    assert "HairRel" in code  # hair remembers its offset (re-welded after ScaleTo)
    with pytest.raises(KeyError, match="unknown role"):
        characters.compose_script("gon", {"hat": 1})


def test_prep_strips_scripts_and_wraps_non_models():
    code = characters.prep_script("gon", ["1", "2"])
    assert "LuaSourceContainer" in code and "d:Destroy()" in code
    assert "Instance.new('Model')" in code and "pcall" in code


def test_find_without_query_or_pick(tmp_path):
    text, img = characters.find(tmp_path / "nobody", None, None, None)
    assert "start with query" in text and img is None
    (tmp_path / "gon").mkdir()
    (tmp_path / "gon" / "character.json").write_text(json.dumps({"name": "gon", "pick": {"face": 3}}))
    text, _ = characters.find(tmp_path / "gon", None, None, None)
    assert '"face": 3' in text


def test_look_rejects_unknown_views(tmp_path):
    with pytest.raises(KeyError, match="unknown view"):
        characters.look("gon", tmp_path / "x.png", views="front,top")
