# Plan: Low-token 3D asset harness (Blender MCP + AI generators → Roblox/game-ready)

## Context
Jordan wants a "3D modeling harness": an MCP server plus workflow that lets Claude produce 3D assets (mainly for **Roblox**, also other game engines) while spending **as few LLM tokens as possible during generation**. AI text/image-to-3D generators (Tripo, Meshy, Hunyuan3D, Rodin, Roblox Cube) are the **main source** of geometry. The harness cleans that geometry up, validates it and exports it. It **builds on top of** the existing Blender MCP and does not fork it.

Machine state:
- Blender 5.0 is installed.
- Python and Node are installed. uv is not.
- git is configured as CodeByJn. The GitHub CLI is installed, but **the sign-in is not finished yet**.

Project location: `C:\Users\Jordan\Desktop\code\3D-Asset-Agent`. The working name is `3D-Asset-Agent` and can be renamed.

## Where existing tools waste tokens (what we improve)
These problems are in ahujasid/blender-mcp (now `mcp-for-blender`, TCP socket on :9876):
1. **Raw bpy code is the main modeling path.** The model writes verbose code, and failures come back as long tracebacks that cost more tokens.
2. **Screenshots default to 768px PNGs**, and there is no numeric "is this game-ready?" check.
3. **Generation returns a dense mesh with no cleanup.** Rodin and Hunyuan output runs from 40k to 1M+ triangles, while a Roblox MeshPart is capped at 20k.
4. **No checkpoints or rollback, and no scene diffs.** The agent re-reads the whole scene after every change.
5. **Tool definitions keep growing:** about 7k tokens as of issue #347.

Other tools solved some of these separately, and we borrow their ideas:
- FreeCAD MCP: a text-only feedback mode.
- build123d-mcp: a sandboxed DSL, which raised valid outputs from 88% to 100%.
- StraySpark (paid): checkpoints and `verify_export`.
- The official Blender Lab MCP: a headless CLI mode. It needs Blender 5.1+.

## Architecture
```
Claude Code ──stdio──> 3D-Asset-Agent MCP server (Python, FastMCP)
                          ├── generators/   Tripo | Meshy | Hunyuan3D | Rodin | Roblox Cube (pluggable, one interface)
                          ├── pipeline/     cleanup → decimate → UV/bake → validate → export (runs in Blender)
                          ├── blender link  reuses blender-mcp addon socket (:9876) OR headless `blender -b -P` worker
                          ├── recipes/      tiny JSON specs per asset (prompt, budget, style, seed, post-steps)
                          └── library/      cached outputs keyed by recipe hash (never regenerate/re-pay)
```
The design follows four token rules:
- Every tool returns a **one-line summary by default** (`ok tris=4980/5000 mats=1 uv=yes manifold=yes → out/crate.fbx`). Detail is available only when asked for.
- **Images are opt-in.** Previews are one 256px tile showing 4 views.
- **Diffs, not dumps.** After a step, the server reports only what changed.
- **About 8 high-level tools**, each with a short description and a CI check that keeps all definitions under roughly 2k tokens in total.

## Modular assets and targeted revision (core feature)
A model is rarely right the first time, so an asset is never a single blob. Each asset is a folder made of **independent layers and named parts**, wired together as a build graph. A revision rebuilds only the layers that are out of date. Everything else is reused untouched.

```
assets/crate_01/
  manifest.json        # layers, parts, versions, content hashes, dependency edges
  geometry/            # per-part meshes: body.glb, lid.glb, handle.glb   (shape)
  topology/            # decimated / LOD0-2 per part                      (polycount)
  uv/                  # UV layout per part                               (unwrap)
  surface/             # base-color / normal textures                     (texture)
  finish.json          # material params: tint, roughness, metallic, emissive, style (finish)
  collision/           # simplified hulls                                 (physics)
  export/              # final FBX/GLB per target                         (always cheap to redo)
```

**How the layers depend on each other**
- Geometry → Topology → UV → Surface → Export.
- Finish → Export.
- Collision depends on Geometry only.

**Rules**
- **Each layer has a hash.** A layer rebuilds only when one of its inputs' hashes changes, the same way a build system works.
- **`finish.json` holds parameters, not pixels.** Changing roughness, colour tint or the metal/plastic look rewrites a few numbers and re-exports. No geometry, UV or texture work runs.
- **Geometry edits keep the texture.** When the shape changes, the old texture is carried onto the new mesh:
  - Blender's Data Transfer plus a selected-to-active bake projects old surface → new surface.
  - Only the edited part goes through this.
  - So "make the lid taller" does not regenerate or re-texture the crate.
- **Parts are separate.** An asset is split into named parts (`split_parts`, or the generator's part segmentation). Revisions target one part, e.g. `revise(crate_01, part="handle", layer="geometry", ...)`.
- **Every revision is a version.** `manifest.json` keeps a history (v1, v2, …), so `rollback` can restore one layer, e.g. "keep the v3 shape, return to the v1 texture".
- **Revision output is a diff line.** Example: `v4: rebuilt geometry[lid], uv[lid], surface[lid] (texture transferred); reused 9 layers; tris 4120→4380`.

**What each kind of revision rebuilds**
| Revision request | Layers rebuilt |
|---|---|
| "Shinier / more worn / red instead of blue" | finish → export |
| "Repaint the label" (texture only) | surface[part] → export |
| "Too many tris" | topology → uv → surface (transfer) → export |
| "Lid shape is wrong" | geometry[lid] → … only lid, texture transferred |
| "Regenerate the handle entirely" | generator call for that part only → its layers |

## Proposed tools (MVP)
| Tool | Purpose |
|---|---|
| `make_asset(prompt\|image, budget="roblox_prop", style="lowpoly")` | One call runs the whole pipeline: generate, clean, decimate to budget, UV/bake texture, validate, export, cache |
| `revise(asset, layer, part?, change)` | Targeted revision. Updates one layer or part and rebuilds only out-of-date layers. Returns a diff line. Typed changes: `decimate`, `remesh_quad`, `scale_to`, `set_origin`, `split_parts`, `merge_by_distance`, `regenerate_part`, `set_finish{roughness,metallic,tint}`, `repaint(prompt)` |
| `history(asset)` / `rollback(asset, layer, version)` | Version history for each layer. Layers can be mixed across versions |
| `validate(asset, target="roblox")` | Numeric pass/fail checks: tri count, under 20k per MeshPart, manifold, normals, UVs, scale in studs, texture ≤1024, glTF validator |
| `preview(asset, size=256)` | Optional 4-view tile |
| `library_search(query)` | Reuses earlier or cached assets |
| `export(asset, fmt="fbx\|glb\|obj", target="roblox\|godot\|unity")` | Per-engine axis, scale and naming presets |
| `raw_bpy(code)` | Escape hatch. Errors come back as a one-line trimmed message |

Budget presets live in `budgets.yaml`:
- `roblox_prop`: about 2–5k tris, a single 1024 texture.
- `roblox_hero`: up to 20k tris.
- `mobile_prop`
- `godot_lod`: LOD0/1/2.

## Build phases
0. **Setup**
   - Finish the GitHub sign-in.
   - Create `Desktop\code\3D-Asset-Agent`.
   - `gh repo create` (public or private, Jordan to choose).
   - Install uv.
   - Install blender-mcp: `uvx mcp-for-blender install-addon`, then enable the addon in Blender 5.0.
   - Register both MCPs in the project's `.mcp.json`.
1. **Baseline and measurement**
   - Run 3 sample assets (a crate, a lamp, a stylized tree) through plain blender-mcp.
   - Log tokens, cost and tri counts for each. This is the number to beat.
2. **Pipeline core and layer graph** (headless Blender scripts, no LLM involved):
   - `manifest.json` schema, layer hashing, dependency graph and dirty-layer rebuild.
   - Layer steps: cleanup, part split, decimate-to-budget, smart UV, bake to one texture, finish params, collision, FBX/GLB export with a Roblox preset.
   - Texture transfer onto revised geometry: Data Transfer plus a selected-to-active bake.
   - Unit-test the core on fixture meshes, including that a finish-only revision touches no mesh or texture files.
3. **Generators**
   - A `Generator` interface: `submit`, `poll`, `download` (GLB).
   - First backends: Tripo and Meshy, which are cheap and accept polycount targets.
   - Next: Hunyuan3D (self-host or API) and Rodin.
   - Keys come from env vars, and results are cached by recipe hash.
4. **MCP server.** Wrap the pipeline and generators as the tools above, with one-line outputs and opt-in previews.
5. **Roblox delivery**
   - Export an FBX that matches Roblox's import rules.
   - Optional: an Open Cloud Assets API upload, and a Roblox Studio MCP hook to test the import.
6. **Recipes and library**
   - Store recipes in JSON.
   - Keep a `library/index.json` for search.
   - Write a Claude Code skill (`/make-asset`) that teaches the low-token workflow.

## Verification
- Phase 1 baseline compared with the harness on the same 3 prompts. Target: at least 70% fewer tokens per finished asset, and every asset passes `validate(target="roblox")`.
- Revision tests on the crate:
  - A finish change rebuilds only finish and export.
  - Editing the lid's geometry rebuilds only the lid's layers, and the texture survives (visual check from a 256px preview).
  - Rolling back one layer restores it exactly (same hash).
  - A revision costs far fewer tokens and dollars than regenerating: no generator call unless `regenerate_part` is used.
- `pytest` for the pipeline, using headless Blender (`blender -b -P tests/run.py`).
- Import the exported FBX into Roblox Studio by hand. Check scale (studs), texture and triangle-count warnings.
- A CI check that tool definitions stay under about 2k tokens.

## Open items to confirm during setup
- Repo name and whether it's public or private.
- Which generator API keys Jordan has or wants to buy. Tripo and Meshy are recommended first.
- Whether to self-host Hunyuan3D or TRELLIS. That depends on having a GPU.
