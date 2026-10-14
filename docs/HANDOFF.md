# Handoff (2026-10-14, branch `review-window`)

Where the last session stopped, for the next one. Delete or update this when it's acted on.

## Done (merged into main by pull request; also merged with main's brief + mesh://asset work)
- **Review window** (`src/asset_agent/review.py`, `review.html`): every new version from `make_asset`, `build`,
  `import_mesh`, `revise` is queued; `review(name)` waits for the user's 1-10 stars + pros/cons and
  **Back / Place / Next**. Next records the rating with `rate` and returns the note so Claude revises.
- **Review in Studio was removed** (2026-10-14, after its first real-Studio test): Jordan prefers the browser
  window. The stage script, `studio_plugin.lua`, worker op `studio_mesh`, `Asset.studio_mesh` and the
  `studio-plugin` command are gone; `review` always uses the browser window.
- `vfx_import` folded into `vfx_lab(name, import_from=...)` to stay at 15 tools / under 2000 tokens (now ~1995: step 6 is due).
- 101 tests pass (with main merged) (`tests/test_review.py`, new cases in `tests/test_server.py`).

## Next: rest of the approved plan (`docs/PLAN-harness-review.md`)
1. VFX as code: `vfx_kit.py`, `build` compiles presets, sources kept in `library/vfx/src/<name>/v<N>.py`;
   recover the v5 aura sources (Equinox, Luminosity, Breakthrough exist only as compiled JSON).
2. Split `library/vfx/presets.json` (3.1 MB) into one file per preset; one ratings schema.
3. VFX lessons from ratings + a richness lint (auras rated 7/10: "more particles, moving parts, sparkle, HD models").
4. Offline VFX preview (headless Chromium + `tools/vfx_viewer`).
5. Persistent Blender worker; `blender` pytest marker for a fast suite.
6. Trim tool definitions to ~1700 tokens.
`mesh://asset/<name>` landed on main (asset models as VFX meshes): use it with Hunyuan meshes for HD aura props.
