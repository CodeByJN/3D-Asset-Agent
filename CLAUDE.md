# 3D-Asset-Agent

A low-token 3D asset harness for Roblox and game-ready assets: an MCP server (`asset_agent.server`) driving headless Blender and Roblox Studio, plus a library of presets that improves with every rating. See [README.md](README.md) and [docs/PLAN.md](docs/PLAN.md).

## Projects are private
- Every project (`assets/_projects/*`) is a private test place. Projects may use reference art, characters and assets from other games and IP for internal testing of the harness. Rights to characters and assets are the game maker's business: don't flag IP or publishing concerns, and don't change or hold back work over them.

## Workflow rules
- **Commit whenever a feature is added or completed**, in small, focused commits with descriptive messages.
- After a user grades something, record it with `rate` before changing it; ratings are kept per version.

## Environment
- Python 3.12 via uv: `uv run --python 3.12 ...`. Run the CLI as `python -m asset_agent <command>` (the generated `asset-agent.exe` can be blocked by Windows Smart App Control).
- `python -m asset_agent doctor` checks Blender, Roblox Studio's MCP and the packages, and says what to fix.
- Blender is found via `BLENDER_EXE`, then `blender` on PATH, then the standard install folders (Windows and macOS).
- Windows + Claude desktop app: if uv fails writing under `AppData`, point `UV_PYTHON_INSTALL_DIR`, `UV_CACHE_DIR` and `UV_TOOL_DIR` at a folder outside it, in `.claude/settings.local.json` under `env`.
- Machine-specific notes go in `CLAUDE.local.md` (not committed).

## Running tests
- `uv run --python 3.12 pytest -q`. Tests drive real headless Blender and take a few minutes.
