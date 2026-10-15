"""The quality vault: rating notes, the private/shared split and the dataset export."""
import json

import pytest

from asset_agent import quality


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setattr(quality, "VAULT", tmp_path / "quality")
    return tmp_path / "quality"


def test_note_keeps_hand_edits_and_moves_when_shared(vault):
    p = quality.record("asset", "crate", 2, 9, "pros: clean; cons: plain lid; notes: add rivets", "prop", "build")
    assert p.parent.parent.name == "private"  # unshared by default: git ignores examples/private
    meta, body = quality.read(p)
    assert meta["verdict"] == "good" and "## What's wrong\nplain lid" in body
    meta.update(share=True, failures=["missing-detail"], category="furniture")  # edited in Obsidian
    quality.write(p, meta, body)
    assert quality.relocate() == 1
    shared = vault / "examples" / "asset" / "crate v2.md"
    assert shared.exists() and not p.exists()
    p2 = quality.record("asset", "crate", 2, 8.5, "pros: clean")  # a re-rating keeps the edits
    meta2, _ = quality.read(p2)
    assert p2 == shared and meta2["failures"] == ["missing-detail"] and meta2["category"] == "furniture"
    assert meta2["verdict"] == "good" and meta2["stars"] == 8.5


def test_export_only_shares_shared_notes(vault):
    quality.record("vfx", "spark", 1, 3, "too dim", "vfx", "authored")
    p = quality.record("animation", "wave", 2, 9, "pros: big and bouncy", "animation", "procedural")
    meta, body = quality.read(p)
    quality.write(p, {**meta, "share": True}, body)
    assert quality.export().startswith("1 of 2")
    rows = [json.loads(line) for line in (vault / "dataset" / "ratings.jsonl").read_text().splitlines()]
    assert rows[0]["name"] == "wave" and rows[0]["works"] == "big and bouncy"
    assert quality.export(include_private=True).startswith("2 of 2")
    assert (vault / "dataset" / "ratings.private.jsonl").exists()


def test_brief_is_bounded_and_ranks(vault):
    (vault / "failures").mkdir(parents=True)
    quality.write(vault / "failures" / "Clipping.md", {"type": "failure", "tag": "clipping"},
                  "\n# Clipping\n\n**Fix.** Check every view.\n")
    for i in range(40):  # however many notes, the brief stays the same size
        p = quality.record("asset", f"crate{i}", 1, (i % 10) + 1, f"cons: lid {i}", "prop", "build")
        meta, body = quality.read(p)
        quality.write(p, {**meta, "failures": ["clipping"]}, body)
    b = quality.brief("prop")
    assert "Clipping (x40): Check every view." in b and len(b.splitlines()) == 1 + 2 + 1 + 3 + 1 + 3
    assert "Best:\n- crate" in b and "Worst:\n- crate" in b and "1/10: lid " in b and " 5/10" not in b
