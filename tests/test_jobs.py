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
