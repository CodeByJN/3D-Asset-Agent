# Harness review: quality, speed and token cost

## Context
The Sol's RNG auras have stalled at 7/10 (v5: "good enough; still short of the wiki's next-level quality"). Hunyuan can't be reached from this cloud session, so this plan improves the harness itself: output quality, iteration speed and tokens per finished asset. Everything below can be built and tested in this container, which has no Studio and no GPU. Blender gets installed here for the tests.

## What the review found
| Area | Finding | Cost |
|---|---|---|
| VFX authoring | The v5 auras (Equinox 60 KB/175 nodes, Luminosity 67 KB/212, Breakthrough 178 KB/438) exist only as **compiled JSON** in `library/vfx/presets.json`. The script that made them was never committed (`tools/vfx_auras.py` only has Black Card). | Every revision means Claude rewrites hundreds of nodes from scratch. This costs a lot of tokens and is why the quality is stuck. |
| VFX library | One 3.1 MB / ~58k-line `presets.json`. The v5 commit diff was 23k lines. | Hard to read or grep a single preset. Every save rewrites the whole file. Diffs are noise. |
| VFX feedback | The only way to see a VFX is `vfx_lab`, which needs open Studio. `tools/vfx_viewer` (three.js) exists but isn't wired into the tools. | Impossible without Studio (here, or on Linux). Each look is a slow Studio round trip. |
| Learning | Preset ratings use three different schemas (`history`, `ratings`, `score/note`). Animation has `_lessons` fed by ratings (`anim.lessons()`), but VFX has nothing like it. | The same notes keep coming back ("more particles, more moving parts, sparkle, HD models") without becoming rules. |
| Speed | `blender.run_steps` starts a new Blender process on every call. The full test suite takes minutes. | Seconds of overhead per build or revise, and slow test loops. |
| Tool budget | 15 tools ≈ **1956 of the 2000-token** budget (`tests/test_server.py`). | No room for new tools without consolidating. |

## Plan (in order; one commit per feature, per CLAUDE.md)

### 0. Review window: see every model before it goes to Studio (do first)
The goal: every asset you create opens in a 3D preview where you rate it and choose **Back**, **Place** or **Next**. It also saves tokens, because you look at the model and Claude doesn't need a preview image.

**Page** (`src/asset_agent/review.html`, served locally)
- A 3D viewer built on `<model-viewer>` (Google, pinned CDN version) that loads the version's GLB from `export/versions/v<N>/`. You can orbit, zoom and turn auto-rotate on or off.
- A header with the name, the version and the one-line validate summary (tris, size, ok/FAIL).
- **1–10 stars**, a **Pros** box and a **Cons** box. They're saved as the note `pros: …; cons: …`.
- Buttons under it:
  - **Back:** steps back through what you reviewed earlier, showing each item's model and the rating you gave it. Pressing it again goes further back.
  - **Place:** records the rating if you gave one, then puts the asset in Studio using the same code as the `studio` tool (upload if changed, then place). The page shows the result, or "Studio not reachable". On an older item it says to roll back to that version first.
  - **Next:** records the rating with `rate`, as CLAUDE.md requires, and sends the stars and note back to Claude. Claude revises from the note (`revise` or `build` again). The page shows "rebuilding…", and the new version appears by itself when it's ready.

**Harness** (new `src/asset_agent/review.py`)
- A small `ThreadingHTTPServer` on 127.0.0.1, started on demand inside the MCP server process.
  - The URL carries a random token, so other local pages can't post decisions. This is the same idea as `hy_serve.py`'s key.
  - Endpoints: `GET /` (page), `GET /state`, `GET /glb/<name>/v<N>`, `POST /decide`.
- A review queue and history in `assets/_review/queue.json`, so Back still works after a restart.
- `make_asset`, `import_mesh`, `build` and `revise` add the new version to the queue and add `| review: <url>` to their line.
- A new tool, `review(name)`, opens the page in the browser and **waits** for your button press. It returns one line:
  - `next 6/10 pros: … cons: …`: Claude revises.
  - `placed 9/10 …`
  - `still waiting` after about 10 minutes, so Claude calls it again rather than timing out.
- The server instructions change: after creating something, call `review` instead of asking for a rating in chat.

**Limits**
- The GLB shows the mesh and its colours and glow. Particle effects only appear in Studio (Place).
- VFX presets get their own review once the offline VFX preview (step 4) exists, reusing this same page.

### 1. VFX as code, with source kept per version (quality + tokens)
- Add a VFX kit in `src/asset_agent/vfx_kit.py`. It promotes the helpers that `tools/vfx_originals.py` and `tools/vfx_auras.py` already use (`pe`, `at`, `cs`, `n`, `light`, `plane`, `title_plate`, `aura`) and adds higher-level pieces from the v5 auras:
  - `ring_of(n, make, radius, speed)`
  - `orbiters`
  - `mesh_part("mesh://globe?…")`
  - `sparkle_field`
  - `hand_glow`
- Extend `build`: when `name` is a VFX preset, or `spec.kind == "vfx"`, run the code with the VFX kit instead of Blender (pure Python, under 1 s).
  - Save the source as `library/vfx/src/<name>/v<N>.py` and compile it into the preset.
  - Return one line: version, node counts and the lint from step 3.
  - Calling it again with edited code makes the next version, the same way mesh `build` versions work in `make.build_model`.
  - Extending `build` avoids a new tool, which matters for the tool budget.
- Recover the v5 sources by decompiling the three auras once into kit code. Check that each recompiles to identical nodes, then commit the sources.

### 2. One file per preset (tokens + diffs)
- Split `presets.json` into `library/vfx/presets/<name>.json`. Big repeated node trees go in compact JSON; metadata stays readable.
- `vfx.presets()`, `raw_presets()` and `save_preset()` in `src/asset_agent/vfx.py` read and write the folder. `library_path()` / `ASSET_AGENT_VFX` keep working for tests.
- Migrate the ratings into one schema, `ratings: [{v, stars, note}]`, folding `history` and `score/note` into it. `rate` in `server.py` already appends to `ratings`.

### 3. VFX lessons and a richness lint (quality)
- Add `_lessons` for VFX, mirroring `anim.lessons()`, seeded from the existing notes:
  - Don't cover the avatar.
  - Layer motion: orbit, spin, bob and pulse on different parts.
  - Add a sparkle layer.
  - Use HD meshes for hero props.
- Show the lessons in `build(code="help")` for VFX.
- Richness lint: count emitters, animated nodes, mesh parts, distinct motion types and screen coverage (reuse `roblox.reach`). Compare the counts against the top-rated presets so the build line reads like `motion 4 kinds (top-rated ≥5)`.

### 4. Offline VFX preview (speed, works without Studio)
- `preview(name, layer="vfx")` for a preset uses the existing `tools/vfx_viewer` page.
  - Run it in headless Chromium through Playwright (already installed here).
  - Capture 4 moments of the loop on a stand-in R15 body, as one 512 px contact sheet.
  - Optional `refs` put wiki images alongside, the way `characters.look` does.
- `vfx_lab` stays the final check in Studio.

### 5. Persistent Blender worker + fast tests (speed)
- In `src/asset_agent/blender.py`, keep one `blender -b` process alive. `worker.py` reads jobs line by line on stdin. If the process dies, fall back to spawning a new one.
- Tests: add a `blender` pytest marker. Pure-Python tests (vfx, anim, server schema) run in seconds with `-m "not blender"`.

### 6. Make room in the tool budget (tokens)
- Fold `vfx_import` into `vfx_lab` (`vfx_lab(import_path=…)`). Move long per-tool docs behind `help`, the way `build(code="help")` and `animate("help")` already work.
- Target about 1700 tokens, so later tools fit.

### Later (needs your GPU/Studio)
- `mesh://asset/<name>`: an aura prop can be a `make_asset` or Hunyuan mesh, uploaded through `Asset.upload`, for the HD hero models the ratings keep asking for.

## Critical files
- Step 0: new `src/asset_agent/review.py` and `review.html`. Hooks go in `make.py` (make_asset, build_model) and `server.py` (import_mesh, revise, a new `review` tool, and reuse of the `studio` and `rate` logic). To keep the budget, `vfx_import` folds into `vfx_lab` now instead of waiting for step 6.
- `src/asset_agent/server.py`, `src/asset_agent/vfx.py`, `src/asset_agent/make.py` (build dispatch), `src/asset_agent/blender.py`, `src/asset_agent/worker.py`
- New: `src/asset_agent/vfx_kit.py`, `library/vfx/src/`, `library/vfx/presets/`
- `tools/vfx_originals.py`, `tools/vfx_auras.py` (become thin users of the kit), `tools/vfx_viewer/`
- Tests: `tests/test_server.py`, `tests/test_revision.py`, a new `tests/test_vfx_kit.py`

## Verification
- Install Blender in the container. Run `uv run --python 3.12 pytest -q` (full suite) and `-m "not blender"` (fast suite) after each step.
- Step 0:
  - Unit tests drive the HTTP endpoints against a fixture asset: the queue, Back history, Next recording a rating and returning from `review`, and Place calling a mocked `studio_client`.
  - A Playwright test (Chromium is preinstalled here) loads the page, sees the model render, sets stars and notes, and clicks each button.
  - On your PC: make an asset, review it, press Next, check that the revised version appears, then press Place and check it shows up in Studio.
- Step 1: recompiled v5 aura sources produce node trees identical to the committed presets. A second `build` makes v6 and keeps v5's source.
- Step 2: `vfx.presets()` returns the same dict before and after the split (golden test). `rate` writes the unified schema.
- Step 4: `preview(aura_equinox, layer="vfx")` returns a PNG here without Studio.
- Step 5: time `build` before and after (the target is to save Blender's startup on each call).
- Step 6: `test_tool_definitions_fit_token_budget` passes with the new lower number.
- On your machine: `vfx_lab` an aura in Studio to confirm the presets still play the same.
