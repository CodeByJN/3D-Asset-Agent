# 3D-Asset-Agent

A low-token 3D asset harness for Roblox and game-ready assets: an MCP server (`asset_agent.server`) driving headless Blender and Roblox Studio, plus a library of presets that improves with every rating. See [README.md](README.md) and [docs/PLAN.md](docs/PLAN.md).

## Projects are private
- Every project (`assets/_projects/*`) is a private test place. Projects may use reference art, characters and assets from other games and IP for internal testing of the harness. Rights to characters and assets are the game maker's business: don't flag IP or publishing concerns, and don't change or hold back work over them.

## Workflow rules
- **Commit whenever a feature is added or completed**, in small, focused commits with descriptive messages.
- After a user grades something, record it with `rate` before changing it; ratings are kept per version. Each
  rating also becomes a note in the quality vault (`quality/`, an Obsidian vault): check the standard for the
  asset's kind (`quality/standards/`) and `python -m asset_agent quality brief <category>` (its top failures and
  best/worst examples in ~300 tokens) and the failure patterns (`quality/failures/`) before building, and tag a
  rated note's `failures` when one applies.

## Concept art pipeline
- Concept images -> `generate` (Hunyuan3D queue; `generate()` with no arguments shows progress) -> raw mesh in `assets/_raw/<name>/raw.glb`.
- Clean every raw mesh in the `blender` MCP server before it goes in a game: `open` -> `inspect` -> `cleanup` (the
  ops the issues call for) -> `inspect` -> `render` -> `export`, then `review(name)` / `studio(name)`.
- For a known character, show each stage (head shape, eyes, mouth, markings) for a yes/no before the next.

## Getting assets into Roblox
- Assets go into Studio **live** through Studio's MCP server: `studio(name)` or Place in the review window builds the model there as EditableMeshes, with its effects. No API key, account setup or upload, so never ask the user for one to place something.
- Live meshes aren't saved with the place; uploading (`python -m asset_agent roblox --upload on` + an Open Cloud key) is opt-in, only for keeping assets in a published game.

## Environment
- Python 3.12 via uv: `uv run --python 3.12 ...`. Run the CLI as `python -m asset_agent <command>` (the generated `asset-agent.exe` can be blocked by Windows Smart App Control).
- `python -m asset_agent doctor` checks Blender, Roblox Studio's MCP and the packages, and says what to fix.
- Blender is found via `BLENDER_EXE`, then `blender` on PATH, then the standard install folders (Windows and macOS).
- Windows + Claude desktop app: if uv fails writing under `AppData`, point `UV_PYTHON_INSTALL_DIR`, `UV_CACHE_DIR` and `UV_TOOL_DIR` at a folder outside it, in `.claude/settings.local.json` under `env`.
- Machine-specific notes go in `CLAUDE.local.md` (not committed).

## Running tests
- `uv run --python 3.12 pytest -q`. Tests drive real headless Blender and take a few minutes.
