"""Markdown results tables from results.json and stats.json (pasted into docs/BENCHMARK.md)."""
import json
from pathlib import Path

HERE = Path(__file__).parent
R = json.loads((HERE / "results.json").read_text())
S = json.loads((HERE / "stats.json").read_text())
NAMES = {"palm_tree": "Palm tree", "ssj_aura": "Super Saiyan aura", "run_anim": "R15 run cycle"}


def k(t):
    return f"{t / 1e6:.2f}M" if t >= 1e6 else f"{t / 1000:.0f}k"


print("| Task | Side | Make: time | Make: tokens processed | Make: new tokens | Make: calls | Revise: time | Revise: tokens processed | Revise: new tokens | Revise: calls |")
print("|---|---|--:|--:|--:|--:|--:|--:|--:|--:|")
tot = {}
for t, sides in R.items():
    for s, r in sides.items():
        c, v = r["create"], r["revise"]
        print(f"| {NAMES[t]} | {s} | {c['seconds']:.0f}s | {k(c['context_tokens'])} | {k(c['tokens'])} | {c['tool_calls']} "
              f"| {v['seconds']:.0f}s | {k(v['context_tokens'])} | {k(v['tokens'])} | {v['tool_calls']} |")
        for ph in ("create", "revise"):
            for m in ("seconds", "context_tokens", "tokens", "tool_calls"):
                tot.setdefault(s, {}).setdefault(ph, {}).setdefault(m, 0)
                tot[s][ph][m] += r[ph][m]
for s, r in tot.items():
    c, v = r["create"], r["revise"]
    print(f"| **All three** | **{s}** | **{c['seconds']:.0f}s** | **{k(c['context_tokens'])}** | **{k(c['tokens'])}** | **{c['tool_calls']}** "
          f"| **{v['seconds']:.0f}s** | **{k(v['context_tokens'])}** | **{k(v['tokens'])}** | **{v['tool_calls']}** |")
print()
print("| Output | Native v1 → v2 | Harness v1 → v2 |")
print("|---|---|---|")
p = S["palm_tree"]
for side_fmt in [("tris", "{}"), ("height", "{:.1f}"), ("materials", "{}")]:
    key, f = side_fmt
    print(f"| Palm {key} | {f.format(p['native']['v1'][key])} → {f.format(p['native']['v2'][key])} | "
          f"{f.format(p['harness']['v1'][key])} → {f.format(p['harness']['v2'][key])} |")
a = S["ssj_aura"]
for key in ("ParticleEmitter", "Beam", "total_rate"):
    print(f"| Aura {key} | {a['native']['v1'].get(key, 0)} → {a['native']['v2'].get(key, 0)} | {a['harness']['v1'].get(key, 0)} → {a['harness']['v2'].get(key, 0)} |")
an = S["run_anim"]
for key in ("length", "keyframes"):
    f = (lambda x: f"{x:.1f}s") if key == "length" else str
    print(f"| Run {key} | {f(an['native']['v1'][key])} → {f(an['native']['v2'][key])} | {f(an['harness']['v1'][key])} → {f(an['harness']['v2'][key])} |")
