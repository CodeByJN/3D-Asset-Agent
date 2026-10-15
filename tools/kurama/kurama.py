"""Kurama (Nine-Tails) boss: model it, place it in Studio and install its moves.

  python tools/kurama/kurama.py build      model (rig.py + model.py) -> asset 'kurama' -> review preview
  python tools/kurama/kurama.py head       just the head and jaw (asset 'kurama_head') for face work
  python tools/kurama/kurama.py studio    upload/insert it in the open place and install the boss runtime
  python tools/kurama/kurama.py pose MOVE T [MOVE T ...]   pose it in Edit mode at time T of MOVE and screenshot
  python tools/kurama/kurama.py play MOVE T1,T2,.. [view] [chakra]   play MOVE live in Edit mode, screenshots at T1..
  python tools/kurama/kurama.py stop       end an Edit-mode preview and put him back at rest
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import rig  # noqa: E402

NAME = "kurama"


def model_code(only: str | None = None) -> str:
    data = rig.data() | ({"only": only} if only else {})
    return f"import json\nR = json.loads({json.dumps(json.dumps(data))})\n" + (HERE / "model.py").read_text(encoding="utf-8")


def head() -> str:
    """Just the head and jaw as asset 'kurama_head': a quick look at the face."""
    from asset_agent.make import build_model
    from asset_agent.server import home
    line, img = build_model(home() / "kurama_head", model_code("head"), budget="roblox_boss")
    return f"{line[:300]}\npreview: {img}"


def build() -> str:
    from asset_agent.make import build_model
    from asset_agent.asset import Asset
    from asset_agent.server import home
    root = home() / NAME
    if (root / "manifest.json").exists():  # no baked AO on the tails: it darkens every joint where segments overlap
        a = Asset(root)
        for part, p in a.m["params"]["surface"].items():
            if part.startswith("Tail"):
                p["ao"] = 0
        a._save()
    line, img = build_model(root, model_code(), budget="roblox_boss")
    return f"{line}\npreview: {img}"


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        print(build())
    elif cmd == "head":
        print(head())
    elif cmd == "studio":
        import studio
        print(studio.install())
    elif cmd == "pose":
        import studio
        args = sys.argv[2:]
        view = args.pop() if len(args) % 2 else "3q"
        print(studio.pose([(args[k], float(args[k + 1])) for k in range(0, len(args), 2)], view))
    elif cmd == "play":
        import studio
        a = sys.argv[2:]
        print(studio.play(a[0], [float(x) for x in a[1].split(",")], a[2] if len(a) > 2 else "3q", "chakra" in a))
    elif cmd == "stop":
        import studio
        print(studio.stop())
    else:
        sys.exit(__doc__)
