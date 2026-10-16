"""Asset studio jobs: stages run in order, gates check the files, failures loop back, the user's thumbs move it on."""
import pytest

from asset_agent import Asset, gates, jobs

from .test_pipeline import fixtures  # noqa: F401 - the shared Blender fixture meshes


def brief_out(tmp_path, **over):
    img = tmp_path / "ref.png"
    img.write_bytes(b"png")
    out = {"images": [str(img)],
           "description": {"what": "wooden crate", "style": "low poly", "colours": "brown wood, iron bands",
                           "size_studs": 4, "genre": "adventure", "use": "breakable prop"},
           "details": ["iron corner bands", "lid with a gap", "plank seams"],
           "category": "prop", "route": "claude", "budget": "roblox_prop",
           "restatement": "A low poly brown wooden crate about four studs wide with iron corner bands, a lid with a "
                          "gap and plank seams, held to the Props standard."}
    out.update(over)
    return out


def test_brief_needs_images_and_description(tmp_path):
    j = jobs.Jobs(tmp_path)
    assert "stage 1/8 brief" in j.next("crate")
    line = j.submit("crate", {"description": {"what": "a crate"}, "route": "claude"})
    assert "brief failed (1/3)" in line and "reference images" in line and "description complete" in line
    assert j.get("crate")["stage"] == "brief"
    line = j.submit("crate", brief_out(tmp_path))
    assert "passed its checks" in line and "Route: claude" in line
    kept = j.get("crate")["outputs"]["brief"]["images"][0]
    assert "_jobs" in kept  # the reference is copied into the job


def test_nothing_moves_without_the_users_thumbs(tmp_path):
    j = jobs.Jobs(tmp_path)
    j.next("crate")
    j.submit("crate", brief_out(tmp_path))
    assert "waiting for the user" in j.submit("crate", {"asset": "crate"})
    assert "waiting for the user" in j.next("crate")
    assert "on to shape" == j.approve("crate", True).split(": ")[1]
    assert "isn't ready" in j.approve("crate", True)  # shape hasn't been submitted
    assert "build(name, code, spec)" in j.next("crate")


def test_three_failed_checks_stop_for_the_user(tmp_path):
    j = jobs.Jobs(tmp_path)
    j.next("crate")
    for _ in range(2):
        assert "failed" in j.submit("crate", {})
    assert "stopped for the user" in j.submit("crate", {})
    assert j.get("crate")["status"] == "stuck"
    assert "back to brief" in j.approve("crate", False, "the reference is in Downloads")
    assert "user's note: the reference is in Downloads" in j.next("crate")
    assert j.get("crate")["tries"]["brief"] == 0


def test_critic_sends_it_back_to_the_weakest_stage(tmp_path, monkeypatch):
    j = jobs.Jobs(tmp_path)
    j.next("crate")
    j.submit("crate", brief_out(tmp_path, moves=False))
    j.approve("crate", True)
    for stage in ("shape", "cleanup", "texture"):  # stub the model stages' gates
        monkeypatch.setitem(gates.GATES, stage, lambda job, out, home, s=stage: gates.report(s, [], asset="crate"))
        j.submit("crate", {"asset": "crate"})
        j.approve("crate", True)
    assert j.get("crate")["stage"] == "critic"  # rig skipped: nothing moves
    assert any(e["kind"] == "skipped" for e in j.trace("crate"))
    view = tmp_path / "front.png"
    view.write_bytes(b"png")
    out = {"views": [str(view)], "details": {d: True for d in brief_out(tmp_path)["details"]},
           "scores": {"shape": 8, "surface": 4, "fit": 7}, "score": 5}
    line = j.submit("crate", out)
    assert "back to texture" in line and "score: 5" in line
    assert [e for e in j.trace("crate") if e["kind"] == "loop_back"][-1]["data"]["to"] == "texture"


def test_review_and_place(tmp_path, monkeypatch):
    j = jobs.Jobs(tmp_path)
    j.next("crate")
    j.submit("crate", brief_out(tmp_path))
    j.approve("crate", True)
    for stage in ("shape", "cleanup", "texture", "critic"):
        monkeypatch.setitem(gates.GATES, stage, lambda job, out, home, s=stage: gates.report(s, []))
        j.submit("crate", {"asset": "crate"})
        j.approve("crate", True)
    assert j.get("crate")["status"] == "awaiting"  # review is the user's stage
    rated, placed = [], []
    monkeypatch.setitem(jobs.hooks, "rate", lambda a, s, n: rated.append((a, s)))
    monkeypatch.setitem(jobs.hooks, "place", lambda a: placed.append(a) or "placed crate")
    with pytest.raises(ValueError):
        j.approve("crate", False, back_to="place")
    assert "on to place" in j.approve("crate", True, "great", stars=8)
    assert rated == [("crate", 8)]
    assert "passed" in j.submit("crate", {})
    assert placed == ["crate"]
    assert j.approve("crate", True).endswith("done")


def test_cleanup_and_texture_gates_read_the_asset(fixtures, tmp_path):  # noqa: F811
    Asset.create(tmp_path / "crate", {"body": fixtures / "body.glb", "lid": fixtures / "lid.glb"},
                 max_tris=1500, tex_size=128).build()
    job = {"brief": brief_out(tmp_path)}
    s = Asset(tmp_path / "crate").cur("export")["stats"]
    job["brief"]["description"]["size_studs"] = max(s["size_m"]) / gates.STUD
    rep = gates.run("cleanup", job, {"asset": "crate"}, tmp_path)
    assert rep["pass"], gates.describe(rep)
    assert rep["facts"]["tris"] == s["tris"]
    job["brief"]["description"]["size_studs"] = 100
    rep = gates.run("cleanup", job, {"asset": "crate"}, tmp_path)
    assert [c["name"] for c in gates.failed(rep)] == ["size"]
    rep = gates.run("texture", job, {"asset": "crate"}, tmp_path)
    assert rep["pass"], gates.describe(rep)
    glb = tmp_path / "crate" / "export" / "versions" / "v1" / "crate.glb"
    assert gates.glb_tris(gates.glb_json(glb)) == s["tris"]
    assert not gates.run("rig", job, {"asset": "crate"}, tmp_path)["pass"]
    assert not gates.run("cleanup", job, {"asset": "nope"}, tmp_path)["pass"]


def test_a_stuck_brief_cant_be_accepted_but_a_stuck_stage_can(tmp_path, monkeypatch):
    j = jobs.Jobs(tmp_path)
    j.next("crate")
    for _ in range(3):
        j.submit("crate", {})
    with pytest.raises(ValueError):
        j.approve("crate", True)
    j.approve("crate", False, "here's the reference")
    j.submit("crate", brief_out(tmp_path))
    j.approve("crate", True)
    monkeypatch.setitem(gates.GATES, "shape", lambda job, out, home: gates.report("shape", [gates.check("x", False)]))
    for _ in range(3):
        j.submit("crate", {"asset": "crate", "try": _})
    assert "on to cleanup" in j.approve("crate", True, "good enough")
    assert j.get("crate")["outputs"]["shape"] == {"asset": "crate", "try": 2}


def test_job_board_page_and_thumbs(tmp_path, monkeypatch):
    import json
    import urllib.request
    from asset_agent import review, studio_board
    monkeypatch.setenv("ASSET_AGENT_REVIEW_PORT", "0")
    j = jobs.Jobs(tmp_path)
    j.next("crate")
    j.submit("crate", brief_out(tmp_path))
    page = review.studio_url(tmp_path, "crate")
    base, token = page.split("/studio?t=")
    token = token.split("#")[0]

    def get(path, t=token):
        try:
            with urllib.request.urlopen(f"{base}{path}?t={t}") as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def post(path, body):
        req = urllib.request.Request(f"{base}{path}?t={token}", json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    assert get("/studio")[0] == 200 and b"Asset Studio" in get("/studio")[1]
    assert get("/jobs", "wrong")[0] == 401
    b = json.loads(get("/jobs")[1])
    assert b["jobs"][0]["name"] == "crate" and b["jobs"][0]["status"] == "awaiting"
    d = json.loads(get("/jobs/crate")[1])
    assert d["stages"][0]["state"] == "awaiting" and d["stages"][0]["report"]["pass"]
    assert d["stages"][0]["output"]["images"] == [0]
    assert get("/jobs/crate/file/0") == (200, b"png")  # the brief's reference, from its copy in the job
    assert get("/jobs/crate/file/5")[0] == 404 and get("/jobs/nope")[0] == 404
    assert post("/jobs/crate/thumbs", {"up": False, "note": "", "back_to": "place"})[0] == 409
    code, res = post("/jobs/crate/thumbs", {"up": True, "note": "good"})
    assert code == 200 and "on to shape" in res["line"]
    assert studio_board.wait(tmp_path, "crate", 1)["stage"] == "shape"
