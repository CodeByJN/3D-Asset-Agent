# Handoff (2026-10-14, branch `review-window`)

Where the last session stopped, for the next one. Delete or update this when it's acted on.

## Done on this branch (not merged, no PR yet)
- **Review window** (`src/asset_agent/review.py`, `review.html`): every new version from `make_asset`, `build`,
  `import_mesh`, `revise` is queued; `review(name)` waits for the user's 1-10 stars + pros/cons and
  **Back / Place / Next**. Next records the rating with `rate` and returns the note so Claude revises.
- **Review in Studio** (`roblox.review_script`, `studio_plugin.lua`, worker op `studio_mesh`, `Asset.studio_mesh`):
  with Studio open, `review` builds the version on a dark stage above the map (EditableMesh/EditableImage, no
  upload), effects playing, R15 stand-in for scale, camera framed. The **Asset Review** dock panel (local plugin,
  auto-installed on first review or `python -m asset_agent studio-plugin`) grades it. Browser window is the fallback.
- `vfx_import` folded into `vfx_lab(name, import_from=...)` to stay at 15 tools / under 2000 tokens (now ~1976).
- 92 tests pass (`tests/test_review.py`, new cases in `tests/test_server.py`).

## Not verified yet: needs Jordan's PC with Studio
Built in a Linux cloud container (no Studio, no GPU). The plugin and stage script compile and type-check against
Roblox's API, but have never run in real Studio. First test:
1. Pull `review-window`, restart the asset-agent MCP server, make or revise any asset, call `review`.
2. Restart Studio once to load the plugin; allow its HTTP requests to 127.0.0.1.
3. Check: model appears on the stage with the right texture orientation (UV v is flipped in `op_studio_mesh`;
   if textures look upside down, that's the place), faces not inside-out, particles playing, panel buttons work.
4. If it works: open a PR to `main`.

## Next: rest of the approved plan (`docs/PLAN-harness-review.md`)
1. VFX as code: `vfx_kit.py`, `build` compiles presets, sources kept in `library/vfx/src/<name>/v<N>.py`;
   recover the v5 aura sources (Equinox, Luminosity, Breakthrough exist only as compiled JSON).
2. Split `library/vfx/presets.json` (3.1 MB) into one file per preset; one ratings schema.
3. VFX lessons from ratings + a richness lint (auras rated 7/10: "more particles, moving parts, sparkle, HD models").
4. Offline VFX preview (headless Chromium + `tools/vfx_viewer`).
5. Persistent Blender worker; `blender` pytest marker for a fast suite.
6. Trim tool definitions to ~1700 tokens.
Later (needs the GPU): Hunyuan meshes as aura props (`mesh://asset/<name>`).
