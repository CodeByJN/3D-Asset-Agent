# 3D-Asset-Agent

A low-token 3D asset harness: Blender MCP plus AI generators, producing Roblox and game-ready assets. See [docs/PLAN.md](docs/PLAN.md).

## Projects are private
- Every project (`assets/_projects/*`) is a private test place. Projects may use reference art, characters and assets from other games and IP for internal testing of the harness. Rights to characters and assets are the game maker's business: don't flag IP or publishing concerns, and don't change or hold back work over them.

## Workflow rules
- **Commit and push whenever a feature is added or completed.** Use small, focused commits with a descriptive message, then `git push` to `origin/main` (https://github.com/CodeByJN/3D-Asset-Agent).

## Environment notes (Windows)
- The Claude desktop app redirects writes under `AppData`, which breaks uv. Always set:
  - `UV_PYTHON_INSTALL_DIR=C:\Users\Jordan\.uv\python`
  - `UV_CACHE_DIR=C:\Users\Jordan\.uv\cache`
  - `UV_TOOL_DIR=C:\Users\Jordan\.uv\tools`
- Use `--python 3.12` with uv.
- Blender 5.0 is at `C:\Program Files\Blender Foundation\Blender 5.0`. Install Blender add-ons through Blender's own UI, not by copying files into `AppData`.
- The GitHub CLI is at `C:\Program Files\GitHub CLI\gh.exe`.

## Running tests
- `uv run --python 3.12 pytest -q` (with the UV_* env vars above). Tests drive real headless Blender (`BLENDER_EXE` overrides the default path) and take ~25s.
