"""The asset studio's orchestrator: every asset is a job that moves through fixed stages, one at a time.

    brief -> shape -> cleanup -> texture -> rig -> critic -> review -> place

Claude works a stage (job_next says what it needs, job_submit hands in the output) but never picks the order.
Each submit runs the stage's gate (gates.py); a failed check sends the job back to the stage that owns it, and
after 3 failed checks at one stage it stops and asks the user. A passed gate waits for the user's thumbs up
(approve), which only the user gives: the job board or `python -m asset_agent job`, never an MCP tool.

Jobs live in SQLite (assets/_jobs/jobs.db): the job's state, and an event per submit, gate report, thumbs and
loop-back, which is the full trace of how the asset was made (post-training data).
"""
import json
import shutil
import sqlite3
import time
from pathlib import Path

from . import gates

STAGES = ("brief", "shape", "cleanup", "texture", "rig", "critic", "review", "place")
USER_STAGES = ("review",)  # nothing for Claude to do: the user's review is the stage
MAX_TRIES = 3
hooks = {}  # place(asset) -> line, rate(asset, stars, note) -> line; set by the server

GUIDE = {
    "brief": (
        "job_submit(output={images: [paths], description: {what, style, colours, size_studs, genre, use}, "
        "details: [3-5 things that make it THIS asset], category: prop|building|character|creature, "
        "route: claude|hunyuan|hybrid (quality/standards/Shape routing.md: built to measurements -> claude; face, "
        "muscles, organic -> hunyuan; both -> hybrid with parts {organic: [...], built: [...]}), "
        "budget: roblox_prop|roblox_hero|roblox_boss, moves: true if it needs a rig, target: critic score (7), "
        "restatement: the brief in your words and the standard it will be held to}). Ask the user for anything "
        "missing (images and description are required); don't invent it."),
    "shape": {
        "claude": "Build it in code with build(name, code, spec) from the brief's details and sizes. "
                  "Submit {asset: name}.",
        "hunyuan": "generate(images=[the clean reference]) and wait for the raw mesh (generate() shows progress). "
                   "Submit {mesh: assets/_raw/<name>/raw.glb}.",
        "hybrid": "Organic parts with generate, built parts with build. Submit {parts: {part: raw mesh path or "
                  "asset name}}.",
    },
    "cleanup": "In the blender server: open -> inspect -> cleanup (the ops the issues call for) -> inspect -> "
               "render -> export(name). For a built asset, fix with revise. Join hybrid parts into one asset. "
               "Gate: tris within the budget, UVs, longest side within 25% of size_studs. Submit {asset: name}.",
    "texture": "Every surface textured, one texture <= the budget's size: blender bake_texture, Hunyuan paint, "
               "or revise(name, 'surface', ...). No flat-coloured parts. Submit {asset: name}.",
    "rig": "Bones and weights for how it moves (blender run, or character/animate for R15). Submit {asset: name} "
           "or {mesh: rigged .glb}.",
    "critic": "Judge it against the brief, its standard and the failure notes: render or preview it, then submit "
              "{views: [image paths], details: {each key detail: true|false}, scores: {shape, surface, fit, "
              "function, vfx: 1-10}, score: overall 1-10, notes}. Be the harsh grader: a low score sends it back "
              "to the stage that owns its weakest sub-score.",
    "review": "The user is reviewing it. Nothing to submit: wait for their thumbs up or notes.",
    "place": "Submit {} to place it in the open Studio place (studio(name)); then the user confirms.",
}


class Jobs:
    def __init__(self, home: Path):
        self.home = Path(home)
        self.dir = self.home / "_jobs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db = self.dir / "jobs.db"
        with self._con() as c:
            c.execute("create table if not exists jobs (name text primary key, stage text, status text, "
                      "data text, created real, updated real)")
            c.execute("create table if not exists events (id integer primary key, job text, stage text, "
                      "kind text, data text, at real)")

    def _con(self):
        c = sqlite3.connect(self.db)
        c.row_factory = sqlite3.Row
        return c

    # ------------------------------------------------------------ storage
    def get(self, name: str) -> dict | None:
        with self._con() as c:
            r = c.execute("select * from jobs where name = ?", (name,)).fetchone()
        if r is None:
            return None
        return {"name": r["name"], "stage": r["stage"], "status": r["status"], **json.loads(r["data"]),
                "created": r["created"], "updated": r["updated"]}

    def _job(self, name: str) -> dict:
        j = self.get(name)
        if j is None:
            raise KeyError(f"no job {name!r}; job_next({name!r}) starts one")
        return j

    def _save(self, j: dict):
        data = {k: v for k, v in j.items() if k not in ("name", "stage", "status", "created", "updated")}
        with self._con() as c:
            c.execute("update jobs set stage = ?, status = ?, data = ?, updated = ? where name = ?",
                      (j["stage"], j["status"], json.dumps(data), time.time(), j["name"]))

    def _event(self, j: dict, kind: str, data=None):
        with self._con() as c:
            c.execute("insert into events (job, stage, kind, data, at) values (?, ?, ?, ?, ?)",
                      (j["name"], j["stage"], kind, json.dumps(data), time.time()))

    def create(self, name: str) -> dict:
        if not name or not all(ch.isalnum() or ch in "_-" for ch in name):
            raise ValueError("job names are letters, digits, _ and -")
        now = time.time()
        data = {"brief": None, "outputs": {}, "tries": {}, "report": None, "note": ""}
        with self._con() as c:
            c.execute("insert into jobs values (?, 'brief', 'working', ?, ?, ?)", (name, json.dumps(data), now, now))
        j = self._job(name)
        self._event(j, "created")
        return j

    def all(self) -> list[dict]:
        with self._con() as c:
            names = [r[0] for r in c.execute("select name from jobs order by updated desc")]
        return [self.get(n) for n in names]

    def trace(self, name: str) -> list[dict]:
        with self._con() as c:
            rows = c.execute("select stage, kind, data, at from events where job = ? order by id", (name,)).fetchall()
        return [{"stage": r["stage"], "kind": r["kind"], "data": json.loads(r["data"]), "at": r["at"]} for r in rows]

    # ------------------------------------------------------------ the rules
    def applies(self, j: dict, stage: str) -> bool:
        """Stages a job skips: rig when nothing moves."""
        return not (stage == "rig" and j["brief"] is not None and not j["brief"].get("moves"))

    def _enter(self, j: dict, stage: str):
        j["stage"] = stage
        j["status"] = "awaiting" if stage in USER_STAGES else "working"

    def submit(self, name: str, output: dict) -> str:
        j = self._job(name)
        stage = j["stage"]
        if j["status"] == "done":
            return f"job {name} is done"
        if j["status"] != "working":
            return f"job {name}: {stage} is waiting for the user ({j['status']}); nothing to submit"
        output = dict(output or {})
        self._event(j, "submit", output)
        if stage == "place":
            asset = final_asset(j)
            try:
                placed = hooks["place"](asset)
            except Exception as e:  # noqa: BLE001 - reported as the failed check
                placed = f"error: {type(e).__name__}: {e}"
            output["asset"] = asset
            rep = gates.place(j, output, self.home, placed)
        else:
            if stage == "brief":
                output = self._keep_images(j, output)
            rep = gates.run(stage, j, output, self.home)
        self._event(j, "gate", rep)
        j["report"] = rep
        if rep["pass"]:
            j["outputs"][stage] = {**output, **rep["facts"]}
            if stage == "brief":
                j["brief"] = output
            j["status"], j["note"] = "awaiting", ""
            self._save(j)
            return self._passed(j, rep)
        tries = j["tries"][stage] = j["tries"].get(stage, 0) + 1
        bad = gates.failed(rep)
        if tries >= MAX_TRIES:
            j["status"] = "stuck"
            self._save(j)
            self._event(j, "stuck", {"tries": tries})
            return (f"job {name}: {stage} failed its checks {tries} times; stopped for the user to decide "
                    f"(thumbs up to accept as is, or notes to try again):\n{gates.describe(rep)}")
        owners = [c.get("owner", stage) for c in bad]
        back = min(owners, key=STAGES.index)
        if back != stage:
            self._event(j, "loop_back", {"from": stage, "to": back, "checks": [c["name"] for c in bad]})
            self._enter(j, back)
        self._save(j)
        where = "redo it" if back == stage else f"back to {back}"
        return f"job {name}: {stage} failed ({tries}/{MAX_TRIES}), {where}:\n{gates.describe(rep)}"

    def _keep_images(self, j: dict, out: dict) -> dict:
        """Copy the brief's reference images into the job, so they outlive Downloads folders."""
        refs = self.dir / j["name"] / "refs"
        kept = []
        for i, p in enumerate(out.get("images") or []):
            p = Path(p)
            if p.is_file():
                refs.mkdir(parents=True, exist_ok=True)
                dst = refs / f"{i + 1}_{p.name}"
                if p.resolve() != dst.resolve():
                    shutil.copy(p, dst)
                kept.append(str(dst.resolve()))
            else:
                kept.append(str(p))
        return {**out, "images": kept}

    def _passed(self, j: dict, rep: dict) -> str:
        warn = gates.describe(rep)
        line = f"job {j['name']}: {j['stage']} passed its checks; waiting for the user's thumbs up"
        if j["stage"] == "brief":
            from . import quality
            line += f". Route: {j['brief']['route']}. Show the user your restatement and the route."
            try:
                line += "\n" + quality.brief(j["brief"]["category"])
            except Exception:  # noqa: BLE001 - the vault is a help, not a gate
                pass
        return line + (f"\n{warn}" if warn else "")

    def approve(self, name: str, up: bool, note: str = "", back_to: str | None = None,
                stars: float | None = None) -> str:
        """The user's thumbs on the current stage. Up: next stage. Down: redo this stage (or back_to) with
        the note. At review, stars rates the asset too."""
        j = self._job(name)
        if j["status"] not in ("awaiting", "stuck"):
            return f"job {name}: {j['stage']} isn't ready for a thumbs up yet ({j['status']})"
        stage = j["stage"]
        if stars is not None and hooks.get("rate"):
            asset = final_asset(j)
            if asset:
                hooks["rate"](asset, stars, note)
        self._event(j, "thumbs_up" if up else "thumbs_down", {"note": note, "back_to": back_to, "stars": stars})
        if not up:
            back = back_to or stage
            if back not in STAGES or STAGES.index(back) > STAGES.index(stage):
                raise ValueError(f"back_to must be {stage} or an earlier stage")
            self._enter(j, back)
            j["tries"][back], j["note"] = 0, note
            self._save(j)
            return f"job {name}: back to {back} with the user's note"
        j["tries"][stage], j["note"] = 0, note
        later = [s for s in STAGES[STAGES.index(stage) + 1:] if self.applies(j, s)]
        for s in STAGES[STAGES.index(stage) + 1:STAGES.index(later[0]) if later else None]:
            self._event(j, "skipped", {"stage": s})
        if not later:
            j["status"] = "done"
            self._save(j)
            self._event(j, "done")
            return f"job {name}: done"
        self._enter(j, later[0])
        self._save(j)
        return f"job {name}: on to {later[0]}"

    # ------------------------------------------------------------ what Claude sees
    def next(self, name: str) -> str:
        """What the current stage needs, with the user's note or the failed checks that sent it here."""
        j = self.get(name) or self.create(name)
        stage, i = j["stage"], STAGES.index(j["stage"]) + 1
        head = f"job {name}: stage {i}/{len(STAGES)} {stage} ({j['status']}"
        if j["tries"].get(stage):
            head += f", {j['tries'][stage]}/{MAX_TRIES} failed"
        head += ")"
        if j["status"] == "done":
            return f"{head}. Placed: {j['outputs'].get('place', {}).get('asset', name)}"
        if j["status"] in ("awaiting", "stuck"):
            return f"{head}: waiting for the user's thumbs up or notes (job board, or python -m asset_agent job {name})"
        guide = GUIDE[stage]
        if isinstance(guide, dict):
            guide = guide[j["brief"]["route"]]
        lines = [head, guide]
        if j["brief"]:
            b = j["brief"]
            d = b["description"]
            lines.append(f"brief: {d['what']}; {d['style']}; {d['colours']}; {d['size_studs']} studs; "
                         f"{d['genre']}; {d['use']} | details: {'; '.join(b['details'])} | route {b['route']}, "
                         f"budget {b.get('budget', 'roblox_prop')} | refs: {', '.join(b['images'])}")
        prev = [s for s in STAGES[:STAGES.index(stage)] if s in j["outputs"] and s != "brief"]
        if prev:
            o = j["outputs"][prev[-1]]
            lines.append(f"from {prev[-1]}: " + json.dumps({k: v for k, v in o.items() if k != "parts"})[:300])
        if stage == "shape" and j["brief"]:
            from . import quality
            try:
                lines.append(quality.brief(j["brief"]["category"]))
            except Exception:  # noqa: BLE001
                pass
        if j["note"]:
            lines.append(f"user's note: {j['note']}")
        rep = j["report"]
        if rep and not rep["pass"]:
            lines.append(f"last checks ({rep['stage']}):\n{gates.describe(rep)}")
        return "\n".join(lines)


def final_asset(j: dict) -> str | None:
    """The asset the latest model stage handed in (rig, else texture, else cleanup)."""
    return next((j["outputs"][s]["asset"] for s in ("rig", "texture", "cleanup") if j["outputs"].get(s, {}).get("asset")),
                None)


def board(jobs: Jobs) -> str:
    return "\n".join(f"{j['name']}: {j['stage']} ({j['status']})" for j in jobs.all()) or "no jobs"
