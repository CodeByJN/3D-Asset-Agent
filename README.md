# 3D-Asset-Agent

A harness that makes Claude Code good at making Roblox assets: models, R15 characters, animations and VFX, built
in Blender and placed straight into your open Roblox Studio place. Works on **Windows and macOS**.

Claude on its own can write Blender and Luau code, but starts from scratch every time. This repo gives it:

- **Tools** (an MCP server, 15 tools, ~1.9k tokens): high-level actions like `build`, `animate`, `character`,
  `vfx_lab` and `studio` that return one-line results, so long scripts and screenshots never fill the chat.
- **Hands**: it drives headless Blender, and talks to Roblox Studio's own MCP server directly, so meshes, textures
  and effects appear in Studio with **no uploads and no API keys**.
- **A library that grows**: VFX presets, procedural textures and 3D meshes, R15 animation presets, shader lighting.
  Every improvement lands here, so every project starts with it.
- **Taste that learns**: `rate` stores your 1-10 grades and notes per version; `plan()` and `animate('help')` hand
  them back to Claude as what to do and what to avoid.

## Setup (about 10 minutes)

You need:

| | Windows | macOS |
|---|---|---|
| [Claude Code](https://claude.com/claude-code) (CLI, desktop app or IDE) | ✓ | ✓ |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | `winget install astral-sh.uv` | `brew install uv` |
| [Blender](https://www.blender.org/download/) 4.2+ (tested on 5.0) | default install folder | in `/Applications` |
| [Roblox Studio](https://create.roblox.com/) | ✓ | ✓ |

Then:

```bash
git clone https://github.com/CodeByJN/3D-Asset-Agent
```

```bash
cd 3D-Asset-Agent
```

```bash
uv sync --python 3.12
```

1. In Roblox Studio, open a place (a Baseplate is fine), then **Assistant > ... > Manage MCP Servers > Enable Studio
   as MCP server**.
2. Check everything:

   ```bash
   uv run --python 3.12 python -m asset_agent doctor
   ```

   Each line says `ok`, or `FIX` with what to do. Blender elsewhere? Set `BLENDER_EXE` to its executable.
3. Open the folder in Claude Code and approve the two project MCP servers it offers (`asset-agent` and
   `Roblox_Studio`, both in `.mcp.json`).

**Windows + the Claude desktop app:** if uv fails with errors writing under `AppData`, point uv at a folder outside
it in `.claude/settings.local.json` (not committed):

```json
{ "env": { "UV_PYTHON_INSTALL_DIR": "C:\\Users\\you\\.uv\\python", "UV_CACHE_DIR": "C:\\Users\\you\\.uv\\cache",
           "UV_TOOL_DIR": "C:\\Users\\you\\.uv\\tools" } }
```

**Windows Smart App Control** can block uv's generated `asset-agent.exe`; everything here runs as
`python -m asset_agent ...` instead, so it isn't needed.

## Try it

Ask Claude in this folder:

- "Make a low-poly wooden treasure chest and put it in Studio."
- "Make a Gon Freecss NPC from Creator Store assets, with an idle animation."
- "Show me `aura_luminosity` in the VFX lab." Then grade it: "7, the blades need more glow."
- "Set the place to shader night lighting." (`studio("lighting:shader_night")`; also `shader_dusk`, `shader_day`)

For a whole game, start with `plan(project)`: it keeps a style guide, a roster, what past ratings liked and
avoided, and writes `HANDOFF.md` so a new chat carries on where the last one stopped. Projects live in
`assets/_projects/` and are not committed.

## Tools

- `build`: you model the asset in Python with a small kit (`code="help"` lists it), and the harness turns it into a
  validated, textured Roblox model in about 10 s. The cleanest and fastest path for stylised props, creatures and
  weapons. R15 characters too: tag each piece with `body(part, ...)` around the rig's joints and `studio(name)`
  builds it on a real R15 rig, so any R15 animation plays on it. `mat(..., glow=True)` parts become Neon.
- `character`: known characters from real Roblox assets. `character(name, query="Gon Freecss", refs=[...])` searches
  free Creator Store models, strips their scripts and shows them numbered next to your references;
  `character(name, pick={"shirt": 2, "hair": 3, "face": 3})` composes an R15 avatar from the chosen parts.
- `animate`: R15 animations from presets (idle, walk, run, sprint, jump, fall, wave, punch, slash, dance) or tracks
  you write per joint, with overlap and leg IK so feet never sink or slide. Revisions pass only what changes, e.g.
  `params={"speed": 1.3}`. `studio(name)` plays it live on a test dummy, or on a character with `on=`.
- `vfx_lab`: play a VFX preset on a stand-in in Studio and get a screenshot; `vfx_lab(name, import_from="workspace.Pack.Blast")`
  saves effects already in the place (e.g. Creator Store packs) as presets. Presets are trees of real Roblox instances plus:
  - procedural HD meshes, built in Studio as EditableMeshes: `mesh://sphere`, `globe` (UV-mapped, wears a texture),
    `torus`, `crystal`, `blade`, `cube`, `shard`, and glowing outlines `frame` and `blade_edge`;
  - textures sent as pixels and built as EditableImages, so nothing needs uploading;
  - motion: orbits (tilted, around any centre), bob, spin, tumble, pulse, shimmer and looping shockwave `wave`s;
  - a `Highlight` node that outlines the whole character.
- `review`: every new version from `make_asset`, `build`, `import_mesh` or `revise` is reviewed before it goes into
  your game. `review(name)` opens a browser window with a 3D viewer (orbit, zoom, a light-shaft stage, wireframe, an R15
  figure for scale, and its effects playing: particles and lights, approximated in the browser) and the grade: 1-10 stars,
  pros and cons, and
  - **Back** / **Next ›**: step through what you reviewed before;
  - **Place**: records the rating and builds the model, with its effects, in the open Studio place;
  - **Next**: records the rating and sends it back, so Claude makes the next version from your note.
  `review` waits for that choice, so you never type the grade in chat. `ASSET_AGENT_REVIEW_PORT` changes the
  port (8765).
- `studio`: puts an asset, character, animation or lighting preset (`lighting:shader_night`) into the open place.

### Getting assets into your game

Everything goes in through Roblox Studio's own MCP server: Studio must be open with **Enable Studio as MCP server**
on, and that's all. `studio(name)` (or **Place** in the review window) sends the model to Studio and **builds it
there live**, as EditableMeshes with EditableImage textures, plus its effects, next to the camera or in place of the
old copy. **No Roblox account setup, API key or upload.** Characters and VFX meshes arrive the same way.

Live-built meshes aren't saved in the place file: they're there for building and testing in the open session, and
`studio(name)` rebuilds one in a second. To keep them in a published game, turn uploads on once
(`python -m asset_agent roblox --upload on`, with an [Open Cloud API key](https://create.roblox.com/dashboard/credentials)
that has **Assets** read+write and your IP allowed, pasted at the prompt of `roblox --key -`): `studio(name)` then
uploads the mesh to your account and inserts it. If an upload fails it falls back to the live build and says why.
- `preview`: geometry, topology, colour and texture breakdowns, or the model in Studio from four angles next to
  your references.
- `plan`, `rate`, `library`: projects, grades and search. `plan(project, references=["https://game.fandom.com/wiki/Auras"])`
  imports a wiki page's images (GIFs also get a frame sheet) into the project's references.
- `make_asset`: Hunyuan3D-2 sculpts a 3D model from your reference image (about 2 minutes on your own GPU), or
  from a text prompt (a picture is generated first). To get it right first shot, it first asks for what's missing:
  a reference image (one object, plain background, no glow), style, colours, what it's for and how big, and the
  key shape details. Generated models can go straight into VFX presets as `mesh://asset/<name>`.
- `import_mesh`, `revise`, `rollback`, `validate`: bring in any mesh, and per-layer revisions (geometry,
  topology, UVs, surface, finish) that rebuild only what changed.

## Python API (no Claude needed)

```python
from asset_agent import make_asset, Asset

# text -> image (FLUX.1-schnell) -> shape (Hunyuan3D-2) on free Hugging Face Spaces,
# then decimate to the Roblox budget, UV, texture, validate and export
print(make_asset("assets/chest", prompt="a wooden treasure chest, low poly"))

a = Asset("assets/chest")
a.revise("finish", tint=[1, 0.8, 0.8])      # re-exports only
a.revise("topology", part="main", target_tris=2000)
```

Generation works anonymously; set `HF_TOKEN` (a free Hugging Face account) for more daily GPU time. Results are
cached in `library/cache/`.

## Your own GPU (optional)

With an NVIDIA GPU (6 GB+ of VRAM), shape generation runs on your own machine, unlimited and private, or on a home
desktop serving your laptop:

```bash
uv run --python 3.12 python -m asset_agent setup
```

```bash
uv run --python 3.12 python -m asset_agent serve --remote
```

```bash
uv run --python 3.12 python -m asset_agent connect http://<gpu-machine>:8080 --key <key>
```

`serve` without `--remote` serves this machine only; `status` shows what is installed and which backend is in use.
See [docs/GPU_SERVER.md](docs/GPU_SERVER.md).

## Development

```bash
uv run --python 3.12 pytest -q
```

Tests drive real headless Blender and take a few minutes.
[docs/BENCHMARK.md](docs/BENCHMARK.md) compares the harness with native Claude on three tasks (in the last run,
native Claude was still faster and cheaper; the fix list is there), and [docs/PLAN.md](docs/PLAN.md) has the full plan.
