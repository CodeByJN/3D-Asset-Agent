# 3D-Asset-Agent

A low-token 3D asset harness for Claude and other LLM agents. It builds on [Blender MCP](https://github.com/ahujasid/blender-mcp) and AI text/image-to-3D generators to produce game-ready assets, mainly for Roblox.

- **Low token cost.** Tools return one-line summaries, images are opt-in, and the server reports diffs instead of full scene dumps.
- **Modular assets.** Geometry, topology, UVs, surface, finish and collision are separate layers, so a revision rebuilds only what changed.
- **Validated output.** Each asset is checked against a polycount budget and for manifold geometry, UVs and scale, then exported as FBX/GLB for Roblox or other engines.

See [docs/PLAN.md](docs/PLAN.md) for the full plan.

## Benchmark

![Claude native vs Claude + asset-agent](docs/benchmark.gif)

The benchmark covers three tasks (a palm tree, a Super Saiyan aura and an R15 run cycle), with one revision each.
For now, native Claude is faster and cheaper. The generator, the missing aura and animation tools, and pipeline
bugs cost the harness more than its cheap revisions save. Full numbers, method and the fix list are in
[docs/BENCHMARK.md](docs/BENCHMARK.md).

## Quick start (free, no API keys)

```python
from asset_agent import make_asset, Asset

# text -> image (FLUX.1-schnell) -> shape (Hunyuan3D-2) on free Hugging Face Spaces,
# then decimate to the Roblox budget, UV, texture, validate and export
print(make_asset("assets/chest", prompt="a wooden treasure chest, low poly"))
print(make_asset("assets/chest_flat", prompt="a wooden treasure chest, low poly", style="flat", color=[0.7, 0.45, 0.25]))

a = Asset("assets/chest")
a.revise("finish", tint=[1, 0.8, 0.8])      # re-exports only
a.revise("topology", part="main", target_tris=2000)
```

- `style="project"` paints the generated reference image onto the front; `style="flat"` is one colour × ambient occlusion, and recolouring is a finish-only change.
- Works anonymously. Set `HF_TOKEN` (a free Hugging Face account) for more daily GPU time.
- Generations are cached in `library/cache/`, so the same request is never run twice.

## MCP server
`.mcp.json` registers `asset-agent` (run with `uv run asset-agent-mcp`). It has 14 tools, about 1.6k tokens of definitions:
- `build`: you model the asset in Python with a small kit (`code="help"` lists it), and the harness turns it into a
  validated, textured Roblox model in about 10 s. It's the cleanest and fastest path for stylised props, creatures and
  weapons. R15 characters too: tag each piece with `body(part, ...)` around the rig's joints (`R15` in the kit) and
  `studio(name)` builds it in Studio on a real R15 rig (no upload), so any R15 animation plays on it. Write a spec first (shape, details, palette, pose, size, what to take from references), check the 4 views
  it returns, and rebuild before showing. `mat(..., glow=True)` parts become Neon in Roblox.
- `character`: known characters from real Roblox assets, the fastest route to a character that looks right.
  `character(name, query="Gon Freecss", refs=[...])` searches free Creator Store models, strips their scripts and
  returns them numbered side by side next to your references; `character(name, pick={"shirt": 2, "hair": 3,
  "face": 3})` composes an R15 avatar from the chosen parts (faces on a classic head, decal ids resolved, hair
  welded at its offset). `animate` and `studio(anim, on=name)` play on it.
- `preview(name, layer="studio", refs=[...], hide=[...])`: the model in the open Studio place from front, 3/4, side
  and face, next to the references, saying so when Studio isn't rendering instead of returning blank images.
- `make_asset` (text/image to 3D generators, for organic shapes), `import_mesh`
- `revise`, `rollback` (no version: the history), `validate`, `preview`, `library`
- `animate`: R15 animations (KeyframeSequences) from presets (idle, walk, run, sprint, jump, fall, wave, punch,
  slash, dance) or tracks you write per joint (waves for loops, spline keys that flow through poses for
  one-shots, and IK targets for hands and feet). Overlap makes the body move hips-first, head and hands last. A revision is a call
  with only what changes, e.g. `params={"speed": 1.3, "arms": 1.3}`. Feet are planted with leg IK so they never
  sink or slide into the floor. Returns a filmstrip (side + three-quarter view) and writes `export/<name>.rbxmx`
  (Studio: Insert from File); `studio(name)` builds it in the place and plays it on a test dummy, live in Edit mode,
  or on one of your characters with `studio(name, on=character)`.
- `plan` (a game's style guide; also writes `HANDOFF.md` so a new chat can carry on), `rate` (stars plus what you
  liked and didn't)
- `studio`, `vfx_lab`, `vfx_import` (Roblox Studio). VFX textures we haven't uploaded are sent as pixels and built in
  Studio as EditableImages, so every library texture renders without an upload; `vfx_lab` plays effects on a dark
  stage with bloom, the way game captures look.
- References from the web: `plan(project, references=["https://game.fandom.com/wiki/Auras|TRANSCENDENT"])` imports a
  wiki page's images (full size, with captions and the page section they sit in; animated GIFs also get a frame
  sheet) into the project's refs, and `library("transcendent")` finds them again. Test case: Sol's RNG's
  Transcendent auras, recreated as `aura_equinox`, `aura_luminosity` and `aura_breakthrough`.

## Your own GPU (optional)
With an NVIDIA GPU (6 GB+ of VRAM), shape generation runs on your own machine: unlimited and private. The GPU can also be in another machine, such as a home desktop serving your laptop.
```
uv run asset-agent setup            # on the GPU machine: installs Hunyuan3D-2 for your card
uv run asset-agent serve            # this machine only
uv run asset-agent serve --remote   # or let other machines connect; prints a key
uv run asset-agent connect http://<gpu-machine>:8080 --key <key>   # on the other machine
uv run asset-agent status           # what is installed and which backend is in use
```
`backend="auto"`, the default, uses your server when it's up and the free Spaces when it isn't. See [docs/GPU_SERVER.md](docs/GPU_SERVER.md).
