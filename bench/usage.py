"""Token and time totals from a Claude Code transcript (JSONL), split at each user prompt.

  python bench/usage.py transcript.jsonl      -> JSON list, one entry per prompt (create, revision...)
Billed-style totals: fresh input, cache writes, cache reads, output; "tokens" = input + cache writes +
output (new tokens processed), "context_tokens" adds cache reads (what the model actually read).
"""
import json
import sys
from datetime import datetime


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def segments(path):
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    segs, seen = [], set()
    for r in rows:
        m = r.get("message") or {}
        if r.get("type") == "user" and isinstance(m.get("content"), str) or (
                r.get("type") == "user" and isinstance(m.get("content"), list)
                and any(c.get("type") == "text" for c in m["content"]) and not any(c.get("type") == "tool_result" for c in m["content"])):
            segs.append({"start": r["timestamp"], "end": r["timestamp"], "input": 0, "cache_write": 0,
                         "cache_read": 0, "output": 0, "output_est": 0, "api_calls": 0, "tool_calls": 0})
            continue
        if not segs or "timestamp" not in r:
            continue
        s = segs[-1]
        s["end"] = r["timestamp"]
        if r.get("type") == "assistant":
            u = m.get("usage") or {}
            mid = m.get("id")
            # transcripts log usage from the stream's start, so output is undercounted: estimate it from
            # what was actually written (text, thinking, tool inputs) at ~4 characters per token
            s["output_est"] += sum(len(c.get("text") or c.get("thinking") or json.dumps(c.get("input") or ""))
                                   for c in m.get("content") or []) // 4
            s["tool_calls"] += sum(1 for c in m.get("content") or [] if c.get("type") == "tool_use")
            if mid in seen:
                continue
            seen.add(mid)
            s["api_calls"] += 1
            s["input"] += u.get("input_tokens", 0)
            s["cache_write"] += u.get("cache_creation_input_tokens", 0)
            s["cache_read"] += u.get("cache_read_input_tokens", 0)
            s["output"] += u.get("output_tokens", 0)
    for s in segs:
        s["seconds"] = round((ts(s.pop("end")) - ts(s.pop("start"))).total_seconds(), 1)
        s["output"] = max(s["output"], s.pop("output_est"))
        s["tokens"] = s["input"] + s["cache_write"] + s["output"]
        s["context_tokens"] = s["tokens"] + s["cache_read"]
    return [s for s in segs if s["api_calls"]]


if __name__ == "__main__":
    print(json.dumps(segments(sys.argv[1]), indent=1))
