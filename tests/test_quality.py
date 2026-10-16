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


def test_sub_scores_survive_and_make_pairs(vault):
    quality.record("store", "tree a", 1, 8, "pros: clean", "prop", "store",
                   {"query": "tree", "scores": {"shape": 8, "surface": 6}, "genres": ["hangout"], "judged_from": "thumbnail"})
    p = quality.record("store", "tree b", 1, 3, "cons: flat", "prop", "store",
                       {"query": "tree", "scores": {"shape": 7, "surface": 2}, "style_score": 7})
    meta, body = quality.read(p)
    assert meta["scores"] == {"shape": 7, "surface": 2} and "**shape 7 · surface 2 · within its style 7**" in body
    p = quality.record("store", "tree b", 1, 3.5, "cons: flat", "prop", "store", {"query": "tree"})  # re-rated, no scores
    assert quality.read(p)[0]["scores"] == {"shape": 7, "surface": 2}
    with pytest.raises(ValueError):
        quality.clean_scores({"looks": 5})
    assert quality.pairs(include_private=True).startswith("3 pairs")  # overall, shape (by 1) and surface
    rows = [json.loads(x) for x in (vault / "dataset" / "pairs.private.jsonl").read_text().splitlines()]
    assert {r["dimension"] for r in rows} >= {"overall", "surface"} and all("tree_a" in r["chosen"] for r in rows)


def test_extra_vaults_are_read_but_kept_apart(vault, tmp_path, monkeypatch):
    quality.record("asset", "crate", 1, 6, "cons: plain", "prop", "build")
    other = tmp_path / "private_vault"
    quality.write(other / "examples" / "prop" / "ref crate v1.md",
                  {"kind": "reference", "name": "ref crate", "version": 1, "stars": 10, "category": "prop",
                   "scores": {"shape": 9.5, "surface": 10}},
                  "\n# ref crate\n\n## What works\nbevelled planks\n")
    assert len(quality.notes()) == 1  # not named: not read
    monkeypatch.setenv("ASSET_AGENT_VAULTS", str(other))
    assert len(quality.notes()) == 2
    assert "ref crate v1 10/10: bevelled planks" in quality.brief("prop")
    quality.export(include_private=True)
    rows = [json.loads(x) for x in (vault / "dataset" / "ratings.private.jsonl").read_text().splitlines()]
    assert {r["note"] for r in rows} == {"examples/private/asset/crate v1.md", "private_vault/examples/prop/ref crate v1.md"}
