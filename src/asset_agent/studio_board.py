"""The asset studio's job board: what the page at /studio shows and what its buttons do (served by review.py's
local server, behind the same token). One card per job; a job's view has its eight stages, each with the
stage's output, the gate report and the stage's history, the 3D model where a stage made one, and the thumbs.
"""
import json
import time
from pathlib import Path

from . import jobs as J

PAGE = Path(__file__).with_name("studio.html")
polled = {"at": 0.0}  # last time an open board asked for the state: job_next opens one only if none is open


def _jobs(home) -> J.Jobs:
    return J.Jobs(home)


def board(home) -> dict:
    polled["at"] = time.time()
    out = []
    for j in _jobs(home).all():
        d = (j["brief"] or {}).get("description") or {}
        out.append({"name": j["name"], "stage": j["stage"], "index": J.STAGES.index(j["stage"]),
                    "status": j["status"], "tries": j["tries"].get(j["stage"], 0), "what": d.get("what", ""),
                    "route": (j["brief"] or {}).get("route"), "updated": j["updated"]})
    return {"stages": list(J.STAGES), "jobs": out}


def files(j: dict) -> list[str]:
    """Images the page may load for a job: the brief's references, then the critic's views."""
    return [*j["outputs"].get("brief", {}).get("images", []), *j["outputs"].get("critic", {}).get("views", [])]


def model(home, j: dict, stage: str) -> Path | None:
    """The model a stage handed in, as it was then (that asset version), or its raw mesh."""
    o = j["outputs"].get(stage) or {}
    if o.get("asset"):
        v = o.get("version")
        if v is None:
            m = Path(home) / o["asset"] / "manifest.json"
            v = json.loads(m.read_text())["version"] if m.exists() else None
        p = Path(home) / o["asset"] / "export" / "versions" / f"v{v}" / f"{o['asset']}.glb"
        return p if p.exists() else None
    if o.get("mesh") and Path(o["mesh"]).suffix.lower() == ".glb" and Path(o["mesh"]).exists():
        return Path(o["mesh"])
    return None


def detail(home, name: str) -> dict | None:
    js = _jobs(home)
    j = js.get(name)
    if j is None:
        return None
    polled["at"] = time.time()
    trace = js.trace(name)
    cur = J.STAGES.index(j["stage"])
    skipped = {e["data"]["stage"] for e in trace if e["kind"] == "skipped"}
    imgs = files(j)
    stages = []
    for i, s in enumerate(J.STAGES):
        gates = [e["data"] for e in trace if e["kind"] == "gate" and e["data"].get("stage") == s]
        if i < cur:
            state = "skipped" if s in skipped else "done"
        elif i == cur:
            state = j["status"]
        else:
            state = "todo"
        out = j["outputs"].get(s)
        if out and s == "brief":
            out = {**out, "images": [imgs.index(p) for p in out.get("images", []) if p in imgs]}
        if out and s == "critic":
            out = {**out, "views": [imgs.index(p) for p in out.get("views", []) if p in imgs]}
        stages.append({"stage": s, "state": state, "output": out, "report": gates[-1] if gates else None,
                       "has_model": model(home, j, s) is not None,
                       "history": [{"kind": e["kind"], "at": e["at"], "data": e["data"]} for e in trace
                                   if e["stage"] == s and e["kind"] != "gate"]})
    vault = ""
    if j["brief"]:
        try:
            from . import quality
            vault = quality.brief(j["brief"]["category"])
        except Exception:  # noqa: BLE001 - the vault is a help, not part of the job
            pass
    return {"name": name, "stage": j["stage"], "status": j["status"], "note": j["note"],
            "tries": j["tries"].get(j["stage"], 0), "max_tries": J.MAX_TRIES, "brief": j["brief"],
            "stages": stages, "vault": vault, "user_stage": j["stage"] in J.USER_STAGES}


def thumbs(home, name: str, body: dict) -> dict:
    try:
        stars = body.get("stars")
        line = _jobs(home).approve(name, bool(body.get("up")), str(body.get("note", "")).strip(),
                                   body.get("back_to") or None, float(stars) if stars else None)
    except (KeyError, ValueError) as e:
        return {"ok": False, "error": str(e)}
    ok = "isn't ready" not in line
    return {"ok": ok, "line": line} if ok else {"ok": False, "error": line}


def wait(home, name: str, timeout: float, open_page=None) -> dict | None:
    """Block until job `name` stops waiting for the user (polls the database, so a thumbs up from the
    CLI counts too). open_page() is called once if no board page is open. Returns the job, or None on
    timeout."""
    js = _jobs(home)
    end = time.time() + timeout
    opened = False
    while True:
        j = js.get(name)
        if j is None or j["status"] not in ("awaiting", "stuck"):
            return j
        if open_page and not opened and time.time() - polled["at"] > 5:
            open_page()
            opened = True
        if time.time() >= end:
            return None
        time.sleep(0.5)
