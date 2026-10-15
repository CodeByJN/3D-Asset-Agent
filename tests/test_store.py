"""Creator Store grading: the API's item details flattened, and a grade written as a private vault note."""
import json

from asset_agent import quality, store

ITEM = {"asset": {"id": 47433, "name": "Sword", "categoryPath": "3d__weapons", "scriptCount": 2,
                  "modelTechnicalDetails": {"objectMeshSummary": {"triangles": 198},
                                            "instanceCounts": {"meshPart": 0, "script": 2}}},
        "creator": {"name": "Roblox", "isVerifiedCreator": True}, "voting": {"upVotePercent": 91, "voteCount": 20000}}


def test_grade_writes_a_private_note_and_keeps_the_thumbnail_private(tmp_path, monkeypatch):
    monkeypatch.setattr(quality, "VAULT", tmp_path / "quality")
    f = store.facts(ITEM)
    assert f["tris"] == 198 and f["scripts"] == 2 and f["category"] == "prop" and f["upvote_pct"] == 91
    (store._dir()).mkdir(parents=True)
    (store._dir() / "_pending.json").write_text(json.dumps({"47433": {**f, "thumb": "missing.png"}}))
    p = store.grade(47433, 5, "pros: readable; cons: flat blade", ["missing-detail"])
    meta, body = quality.read(p)
    assert "private" in p.parts and meta["grader"] == "claude" and meta["failures"] == ["missing-detail"]
    assert meta["url"].endswith("/47433") and "## What's wrong\nflat blade" in body
    quality.write(p, {**meta, "share": True, "image": "img/x.png"}, body)
    (p.parent.parent / "img").mkdir(exist_ok=True)
    (p.parent.parent / "img" / "x.png").write_bytes(b"png")
    quality.relocate()
    assert (p.parent.parent / "img" / "x.png").exists()  # the picture stayed private
    assert not (quality.VAULT / "examples" / "img" / "x.png").exists()
