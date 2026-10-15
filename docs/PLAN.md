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

## Next: the asset studio (a strict pipeline with its own interface)

Decided 2026-10-15. In chat, Claude can skip steps (no cleanup, no brief, straight to placing). The pipeline moves
into an app that **owns each job's stage**; Claude does the work inside a stage but never chooses the order.

**Rule: linear, one stage at a time, your thumbs up after every stage.** A stage first runs its automatic checks;
only then is its result shown to you, and the job moves on when you give it a thumbs up. Thumbs down (with a note)
redoes that stage. Nothing runs ahead, so a wrong turn costs one stage, not the whole asset.

**Required inputs before anything is generated** (the Brief stage won't start without them):
- reference images (at least one; a clean view of the subject, ideally front and side or a model sheet);
- a description: what it is, style, colours, size in studs, genre, and how it's used in the game;
- the details that make it *this* asset (3-5), which every later stage is checked against.

**Stages** (automatic gate, then your thumbs up; a failed gate sends it back with the reason):

| # | Stage | Workers | Gate |
|---|---|---|---|
| 1 | Brief | Claude, `quality brief` | Images and description complete; Claude restates the brief and the standard it'll be held to |
| 2 | Shape | Hunyuan3D (organic) or kit code (hard surface) | A mesh exists |
| 3 | Cleanup | Blender session | `inspect` clean, within the tri budget |
| 4 | Texture | Hunyuan paint and/or Blender bake | Every surface textured (no "Flat untextured") |
| 5 | Rig + scripts | Blender rig, game-script library | Skinned if it moves; scripts pass a Studio play test |
| 6 | Auto critic | Claude vs the category standard, failures and references | Critic score at or above the target, else back to the weakest stage |
| 7 | Your review | Review window with sub-score sliders | Approve, regenerate (back to a chosen stage) or place |
| 8 | Place + record | Studio client, vault | Placed; the grade and every stage's record saved |

**Shape of the build**
- **Orchestrator:** a job state machine (`pipeline.py` grows into it), jobs in SQLite with every stage's inputs,
  outputs, metrics and scores; the full trace per job is also post-training data.
- **Claude through MCP, on the user's plan:** asset-agent exposes stage tools only (`job_next`: what the current
  stage needs; `job_submit`: the stage's output, which the gate checks). No tool reaches past the current stage.
  The same stage tools can later be driven through the Claude API for unattended runs or open-source users.
- **Interface:** a local web app grown from the review window: a job board (one card per job and its stage),
  a stage view (inputs, outputs, gate result, 3D viewer), grading with sub-scores, and the vault's brief beside it.
- **Reused as is:** the Blender session, the Hunyuan queue, the vault (`quality.py`, `store.py`), the Studio client.

**Build order:** state machine and stage tools → job board UI → texture stage → auto critic → rig + scripts →
sub-score review → scenes (whole environments: terrain, lighting, layout, play test) as a later job type.

**Merged from the Gemini plan review (2026-10-15)**
- **Core vault + project vaults:** the harness ships a core vault (standards, failure patterns, rules, our own
  references and graded store asset ids; never other creators' files or thumbnails). Each new game gets a project
  vault for its art style that inherits the core one as the fallback; `plan(project)` style guides move into it.
- **JSON report per stage:** named checks with pass/fail and values (tris, scale, manifold, UV overlap, texture
  size, bone count, weights normalised, play-test errors), stored on the job; the gate reads it.
- **Targeted loop-back with a retry cap:** a failed check returns the job to the stage that owns it with that
  check attached; after 3 failed attempts the stage stops and asks the user.
- **Three grading layers:** Blender for hard numbers; Claude critic for the look (colour, likeness, standards);
  the user's thumbs up. VFX and Roblox animation are checked in Studio (play test), not Blender.
- **Not adopted:** an LLM supervisor and separate agents. The orchestrator is a deterministic state machine; one
  Claude session works each stage with that stage's instructions and tools (same specialisation, no drift, no
  context re-derived per agent).
- **What the vault holds for the AI:** text first (standards, failures, grades in the grader's words), measured
  facts as JSON extracted from rbxm/GLB (proportions, tris, parts, hex palettes, emitter parameters), a few
  reference renders per standard (front/side/3/4) for the critic, and frame strips (6-8 frames in one image) for
  VFX and animation instead of GIF/MP4. Original rbxm/GLB/FBX stay in the asset library or the place, linked by
  path or asset id.
- **Shape router (stage 2):** the brief picks a route from `quality/standards/Shape routing.md`: **claude** (built
  things, from measured facts; procedural texture + bake), **hunyuan** (organic forms; Hunyuan paint), **hybrid**
  (split into organic and built parts, joined in Blender) or **import** (VFX/animation from the library). The route
  is shown in the Brief stage for the thumbs up; the recreation benchmark tests each route against the originals.
