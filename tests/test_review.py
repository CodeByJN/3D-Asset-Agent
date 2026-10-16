"""Review window: queue, Back history, Next/Place decisions and the blocking wait, over real HTTP."""
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from asset_agent import quality, review

GRADE = {"shape": 8, "surface": 7.5, "vfx": None, "function": None, "fit": 9}  # every part scored or n/a


@pytest.fixture
def board(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_AGENT_REVIEW_PORT", "0")
    monkeypatch.setattr(review, "_board", None)
    calls = []

    def rate(name, stars, note, scores=None, na=None):
        calls.append(("rate", name, stars, note))
        assert scores == {"shape": 8, "surface": 7.5, "fit": 9} and na == ["vfx", "function"]
        return f"rated {name} {stars}/10"

    def place(name):
        calls.append(("place", name))
        return f"placed {name}"
    monkeypatch.setattr(review, "hooks", {"rate": rate, "place": place})
    glb = tmp_path / "crate.glb"
    glb.write_bytes(b"glTF fake model")
    return tmp_path, glb, calls


def http(url, path, body=None, token=True):
    base = url.split("/?")[0]
    sep = "&" if "?" in path else "?"
    full = base + path + (f"{sep}t={review.TOKEN}" if token else "")
    req = urllib.request.Request(full, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_queue_page_and_model_are_served(board):
    home, glb, _ = board
    url = review.add(home, "crate", 1, glb, "ok tris=900/1500")
    review.add(home, "crate", 1, glb, "again")  # the same version is queued once...
    assert http(url, "/")[0] == 200 and b"Asset Review" in http(url, "/")[1]
    assert http(url, "/state", token=False)[0] == 401
    items = json.loads(http(url, "/state")[1])["items"]
    assert [(i["name"], i["v"], i["current"], i["has_glb"]) for i in items] == [("crate", 1, True, True)]
    assert "glb" not in items[0]  # no file paths leave the server
    assert http(url, f"/glb/{items[0]['id']}") == (200, b"glTF fake model")
    assert json.loads((home / "_review" / "queue.json").read_text())["items"][0]["line"] == "ok tris=900/1500"


def test_effects_are_served_for_the_viewer(board):
    home, glb, _ = board
    fx = {"aura": {"type": "legendary_blade", "nodes": [{"class": "PointLight", "props": {"Range": 9}}]}}
    url = review.add(home, "crate", 1, glb, "ok", fx=fx)
    item = json.loads(http(url, "/state")[1])["items"][0]
    assert item["has_fx"] and "fx" not in item  # the poll stays small; the page fetches effects once
    assert json.loads(http(url, f"/fx/{item['id']}")[1]) == fx
    assert json.loads(http(url, "/fx/99")[1]) == {}


def test_next_records_the_rating_then_returns_it_to_the_waiting_tool(board):
    home, glb, calls = board
    url = review.add(home, "crate", 1, glb, "ok")
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("line", review.wait(home, "crate", 10, open_page=False)))
    t.start()
    time.sleep(0.2)
    code, body = http(url, "/decide", {"id": 1, "action": "next"})
    assert code == 409 and b"stars" in body  # Next needs a rating
    code, body = http(url, "/decide", {"id": 1, "action": "next", "stars": 6, "scores": GRADE, "pros": "chunky shape",
                                       "cons": "lid too thin"})
    assert code == 200, body
    t.join(5)
    assert calls == [("rate", "crate", 6, "pros: chunky shape; cons: lid too thin")]
    assert out["line"].startswith("next: crate v1 rated 6/10 (pros: chunky shape; cons: lid too thin)")
    assert http(url, "/decide", {"id": 1, "action": "next", "stars": 7, "scores": GRADE})[0] == 409  # decided once
    review.add(home, "crate", 1, glb, "ok")  # ...and again once its review went back to Claude
    assert [i["v"] for i in review.board(home).items] == [1, 1] and review.board(home).latest("crate")["id"] == 2


def test_looks_good_keeps_it_and_notes_reach_the_rating(board):
    home, glb, calls = board
    url = review.add(home, "crate", 1, glb, "ok")
    assert http(url, "/decide", {"id": 1, "action": "keep"})[0] == 409  # a rating first
    code, body = http(url, "/decide", {"id": 1, "action": "keep", "stars": 9, "scores": GRADE, "pros": "great shape",
                                       "notes": "keep the  colours"})
    assert code == 200, body
    assert calls == [("rate", "crate", 9, "pros: great shape; notes: keep the colours")]
    assert review.wait(home, "crate", 1, open_page=False).startswith("kept crate v1 as it is, 9/10")


def test_animations_are_served_with_their_playback(board):
    home, _, _ = board
    payload = {"fps": 30, "length": 1.0, "loop": True, "frames": [{"Head": [1] * 12}], "boxes": {}, "rig": None}
    url = review.add(home, "wave", 2, None, "anim wave v2", kind="animation", anim=payload)
    item = json.loads(http(url, "/state")[1])["items"][0]
    assert item["kind"] == "animation" and item["has_anim"] and not item["has_glb"] and "anim" not in item
    assert json.loads(http(url, f"/anim/{item['id']}")[1]) == payload


def test_place_and_back_history(board):
    home, glb, calls = board
    url = review.add(home, "crate", 1, glb, "ok")
    review.decide(home, 1, "next", 5, scores=GRADE, cons="too plain")
    review.add(home, "crate", 2, glb, "ok")
    review.add(home, "crate", 3, glb, "ok")  # v2 was skipped, never reviewed
    code, body = http(url, "/decide", {"id": 2, "action": "place"})
    assert code == 409 and b"roll crate back to v2" in body  # only the current version can be placed
    code, body = http(url, "/decide", {"id": 3, "action": "place", "stars": 9, "scores": GRADE, "pros": "great"})
    assert code == 200 and json.loads(body)["pending"]  # placing runs on its own thread
    assert review.wait(home, "crate", 5, open_page=False).startswith("placed crate v3 in Studio, 9/10 (pros: great)")
    assert calls[-2:] == [("rate", "crate", 9, "pros: great"), ("place", "crate")]
    items = json.loads(http(url, "/state")[1])["items"]  # Back walks this list, oldest first
    assert [(i["v"], (i["decision"] or {}).get("action"), i["current"]) for i in items] == [
        (1, "next", False), (2, None, False), (3, "place", True)]
    assert review.Board(home).items[0]["decision"]["note"] == "cons: too plain"  # kept across restarts


def test_place_failure_keeps_the_rating_and_the_item_open(board, monkeypatch):
    home, glb, calls = board

    def down(name):
        raise RuntimeError("Studio not reachable")
    monkeypatch.setitem(review.hooks, "place", down)
    review.add(home, "crate", 1, glb, "ok")
    res = review.decide(home, 1, "place", 8, scores=GRADE)
    assert not res["ok"] and "Studio not reachable" in res["error"] and res["lines"] == ["rated crate 8/10"]
    assert review.board(home).get(1)["decision"] is None  # still open: Next or Place again
    assert review.decide(home, 1, "next", 8, scores=GRADE)["ok"] and [c[0] for c in calls] == ["rate"]  # rated once


def test_wait_times_out_and_follows_new_versions(board):
    home, glb, _ = board
    assert review.wait(home, "nope", 0.1, open_page=False).startswith("nothing queued")
    review.add(home, "crate", 1, glb, "ok")
    assert review.wait(home, "crate", 0.2, open_page=False).startswith("still waiting for the review of crate v1")
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("line", review.wait(home, "crate", 10, open_page=False)))
    t.start()
    time.sleep(0.2)
    review.add(home, "crate", 2, glb, "ok")  # a newer version arrives while waiting
    review.decide(home, 2, "next", 4, scores=GRADE, cons="worse")
    t.join(5)
    assert out["line"].startswith("next: crate v2 rated 4/10")


def test_background_place_failure(board, monkeypatch):
    home, glb, calls = board
    gate = threading.Event()

    def slow_down(name):
        gate.wait(5)
        raise RuntimeError("Studio not reachable")
    monkeypatch.setitem(review.hooks, "place", slow_down)
    url = review.add(home, "crate", 1, glb, "ok")
    assert http(url, "/decide", {"id": 1, "action": "place", "stars": 7, "scores": GRADE})[0] == 200
    item = json.loads(http(url, "/state")[1])["items"][0]
    assert item["placing"] and "rated" not in item
    assert http(url, "/decide", {"id": 1, "action": "place"})[0] == 409  # no double press while placing
    gate.set()
    for _ in range(50):
        item = json.loads(http(url, "/state")[1])["items"][0]
        if not item["placing"]:
            break
        time.sleep(0.05)
    assert item["error"] == "rated crate 7/10 | RuntimeError: Studio not reachable" and item["decision"] is None


def test_a_rating_needs_every_part_scored_or_na(board):
    home, glb, calls = board
    url = review.add(home, "crate", 1, glb, "ok")
    code, body = http(url, "/decide", {"id": 1, "action": "keep", "stars": 8, "scores": {"shape": 8}})
    assert code == 409 and b"surface, vfx, function, fit" in body and calls == []
    code, body = http(url, "/decide", {"id": 1, "action": "keep", "stars": 8, "scores": {**GRADE, "fit": 11}})
    assert code == 409 and b"fit must be 0-10" in body
    assert http(url, "/decide", {"id": 1, "action": "keep", "stars": 8, "scores": GRADE})[0] == 200
    state = json.loads(http(url, "/state")[1])
    assert list(state["dimensions"]) == list(quality.DIMENSIONS)
    assert state["items"][0]["decision"]["scores"] == {"shape": 8, "surface": 7.5, "fit": 9}


def test_references_are_graded_into_their_vault_notes(board, tmp_path, monkeypatch):
    home, _, calls = board
    monkeypatch.setattr(quality, "VAULT", tmp_path / "quality")
    vault = tmp_path / "private_vault"
    monkeypatch.setenv("ASSET_AGENT_VAULTS", str(vault))
    (vault / "examples" / "img").mkdir(parents=True)
    (vault / "examples" / "img" / "axe-v1.png").write_bytes(b"\x89PNG fake")
    note = vault / "examples" / "pickaxe" / "axe v1.md"
    quality.write(note, {"kind": "reference", "name": "axe", "version": 1, "stars": 10, "category": "pickaxe",
                         "scores": {}, "image": "img/axe-v1.png"},
                  "\n# axe v1: 10/10 (good)\n\n![[axe-v1.png]]\n\n**not graded by dimension yet**\n\n"
                  "## What works\n\n\n## What's wrong\n\n\n## Notes\n19 mesh pieces, one colour map\n")
    n, url = review.add_references(home, "pickaxe")
    assert n == 1 and review.add_references(home, "pickaxe")[0] == 1 and len(review.board(home).items) == 1
    item = json.loads(http(url, "/state")[1])["items"][0]
    assert item["kind"] == "reference" and item["has_img"] and item["line"] == "19 mesh pieces, one colour map"
    assert http(url, f"/img/{item['id']}") == (200, b"\x89PNG fake")
    assert http(url, "/decide", {"id": item["id"], "action": "grade", "stars": 9, "scores": {"shape": 9}})[0] == 409
    code, body = http(url, "/decide", {"id": item["id"], "action": "grade", "stars": 9, "scores": GRADE,
                                       "pros": "chunky crystal blades", "cons": "grip too plain"})
    assert code == 200, body
    meta, text = quality.read(note)
    assert meta["stars"] == 9 and meta["scores"] == {"shape": 8, "surface": 7.5, "fit": 9}
    assert meta["na"] == ["function", "vfx"] and calls == []  # straight into the note, not an asset rating
    assert "# axe v1: 9/10 (good)" in text and "**shape 8 · surface 7.5 · fit 9**" in text
    assert "not graded" not in text and "19 mesh pieces" in text
    assert quality._sections(text)["works"] == "chunky crystal blades" and quality._sections(text)["wrong"] == "grip too plain"
    assert "axe v1 9/10: chunky crystal blades" in quality.brief("pickaxe")
