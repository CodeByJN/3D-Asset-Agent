"""Call an asset-agent harness tool by name, exactly as the MCP server would (same functions, same
one-line results). Used by benchmark runs so they always get the current build.

  python bench/harness.py list
  python bench/harness.py make_asset '{"name": "palm", "prompt": "..."}'
"""
import inspect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from asset_agent import server  # noqa: E402

TOOLS = ["build", "make_asset", "import_mesh", "revise", "rollback", "history", "validate", "preview", "library",
         "plan", "rate", "studio", "vfx_lab", "review"]
if len(sys.argv) < 2 or sys.argv[1] == "list":
    for t in TOOLS:
        fn = getattr(server, t)
        print(f"{t}{inspect.signature(fn)}\n    {inspect.getdoc(fn)}\n")
    sys.exit()
fn = getattr(server, sys.argv[1])
out = fn(**(json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}))
for o in out if isinstance(out, list) else [out]:
    print(getattr(o, "path", None) or o)  # images come back as a file path
