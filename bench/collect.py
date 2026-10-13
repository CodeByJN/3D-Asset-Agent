"""results.json from the run transcripts listed in runs.json (task -> side -> agent id).
Each run's first prompt is the build, its second the revision."""
import json
import os
from pathlib import Path

from usage import segments

HERE = Path(__file__).parent
TRANSCRIPTS = Path(os.environ.get("BENCH_TRANSCRIPTS", Path.home() / ".claude/projects/C--Users-Jordan-Desktop-code-3D-Asset-Agent/53c5b14f-6810-4cc9-82eb-bebb42364f93/subagents"))
KEEP = ("seconds", "tokens", "context_tokens", "output", "tool_calls", "api_calls")

out = {}
for task, sides in json.loads((HERE / "runs.json").read_text()).items():
    for side, agent in sides.items():
        segs = segments(TRANSCRIPTS / f"agent-{agent}.jsonl")
        r = {name: {k: s[k] for k in KEEP} for name, s in zip(("create", "revise"), segs)}
        out.setdefault(task, {})[side] = r
(HERE / "results.json").write_text(json.dumps(out, indent=1) + "\n")
for task, sides in out.items():
    for side, r in sides.items():
        print(task, side, {k: (v["seconds"], v["tokens"], v["tool_calls"]) for k, v in r.items()})
