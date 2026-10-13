# Benchmark: Claude native vs Claude + asset-agent

![Benchmark: native vs harness, first try then one revision](benchmark.gif)

Three Roblox tasks, each done twice by the same model with the same tools: once as plain Claude ("native")
and once with the asset-agent harness added ("harness"). After each first result we asked for one revision
in the same session and measured that too.

| Task | Ask | Revision |
|---|---|---|
| Palm tree | Low-poly palm tree for a Roblox game, 12-18 studs, as FBX | 50% taller, darker green fronds |
| Super Saiyan aura | Golden flame aura with crackling energy on an R15 character, top-tier quality | Super Saiyan Blue |
| R15 run cycle | Looping run cycle as a KeyframeSequence | Faster sprint, bigger arm swing |

Run on 2026-10-12 with Claude Opus 5.5, harness at commit `fde3bbf`.

## Results

| Task | Side | Make: time | Make: tokens processed | Make: new tokens | Make: calls | Revise: time | Revise: tokens processed | Revise: new tokens | Revise: calls |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Palm tree | native | 73s | 337k | 61k | 6 | 29s | 181k | 3k | 3 |
| Palm tree | harness | 822s | 1.44M | 93k | 23 | 199s | 1.46M | 14k | 19 |
| Super Saiyan aura | native | 388s | 1.45M | 48k | 22 | 54s | 740k | 10k | 8 |
| Super Saiyan aura | harness | 751s | 4.32M | 88k | 52 | 65s | 1.07M | 9k | 9 |
| R15 run cycle | native | 125s | 540k | 33k | 12 | 36s | 343k | 5k | 5 |
| R15 run cycle | harness | 98s | 469k | 31k | 9 | 50s | 340k | 7k | 6 |
| **All three** | **native** | **586s** | **2.32M** | **142k** | **40** | **119s** | **1.26M** | **18k** | **16** |
| **All three** | **harness** | **1671s** | **6.22M** | **212k** | **84** | **313s** | **2.87M** | **30k** | **34** |

- **Time** is wall-clock time from the prompt to the final answer, including Blender, generators and Studio.
- **Tokens processed** is every token the model read or wrote: input (including cached context) plus output.
  It tracks cost most closely and doesn't depend on what happened to be cached.
- **New tokens** is input plus cache writes plus output. It is lower when an earlier run had already cached the
  shared system prompt, so compare it with care.
- **Calls** is the number of tool calls.

What the outputs contain (read from the files and the Studio place):

| Output | Native v1 → v2 | Harness v1 → v2 |
|---|---|---|
| Palm tris | 650 → 650 | 1426 → 1422 |
| Palm height | 14.3 → 21.4 | 4.0 → 5.9 |
| Palm materials | 5 → 5 | 1 → 1 |
| Aura ParticleEmitter | 19 → 19 | 12 → 12 |
| Aura Beam | 70 → 70 | 0 → 0 |
| Aura total_rate | 647 → 647 | 635 → 635 |
| Run length | 0.7s → 0.5s | 0.8s → 0.6s |
| Run keyframes | 13 → 13 | 9 → 9 |

Palm heights are in each file's units: native exported studs, while the harness exports metres for Roblox
(3.96 m is about 14 studs). The harness palm also passed its Roblox budget check and has a 100-tri collision mesh.

## What this says

**Native Claude won this round.** Across the three tasks it reached a first result 2.9x faster (586 s vs 1671 s)
and processed 2.7x fewer tokens (2.3M vs 6.2M). It also revised 2.6x faster (119 s vs 313 s) with 2.3x fewer
tokens. The run cycle is a tie in practice: the harness has no animation tool, so both sides wrote the same kind of
Luau, and the difference between them is run-to-run noise.

The harness's strength, cheap revisions, never came into play. A preset recolour is one call of about 50 tokens,
but none of these outputs came from a preset or a layer the harness owns. So every revision meant hand-editing
a script, exactly as on the native side.

**Where the harness lost time:**

1. **Palm tree: the generator.** `make_asset` (on the free Hugging Face backend) took 522 s and returned a potted
   plant at 22k tris. The agent then wrote its own Blender script, as native did, and ran the result through
   `import_mesh` for clean-up, UVs, collision, validation and export. That cost 15 more calls and hit several
   pipeline problems:
   - `surface` mode `auto` dropped the material colours and left the palm flat grey. Only the undocumented
     `bake` mode kept them.
   - `revise topology target_tris` didn't reduce the tri count.
   - A failed `revise` still saved its bad setting, so the next rebuild failed as well.
   - `revise geometry source` kept the old scale unless `keep: []` was passed.
   - Every export wipes the export folder, deleting saved copies, so v1 and v2 can't sit side by side.
   - There is no way to recolour a single material (here, just the fronds).
2. **Aura: no authoring tool.** The harness can play and recolour library presets, but it can't build a new aura
   or put one on a chosen character. `aura_dark` recoloured gold showed nothing in `vfx_lab`, because its
   textures haven't been uploaded to Roblox yet. The agent found Rei's particle pack through `library` and
   `vfx_import`, then hand-wrote the aura from its emitters. That took 52 calls, against native's 22.
3. **Run cycle: no animation layer.** The harness side made no harness calls at all.

**Native's weak spots:**
- Neither side checked its aura or animation in Play mode.
- The native aura needed its own per-frame hook to show in Edit mode.
- Native palm heights assume 1 Blender unit = 1 stud, whereas the harness validated size and budget.

**Quality is your call.** Grade it from the GIF:
- **Palm tree:** native's is cleaner (650 tris, 5 flat materials). The harness palm is textured (1 material,
  1.4k tris), with more fronds and coconuts.
- **Aura:** both are layered. The harness aura added hair spikes and a ground ring; native's added 70 lightning
  beams.
- **Run cycle:** both read as runs.

## What to build next (by impact on these numbers)

1. **A procedural model path.** For stylised low-poly props, a parametric recipe generator (a palm is trunk
   segments plus fronds) beats a diffusion model on both speed and fidelity. `import_mesh` should also keep
   per-material colours by default.
2. **Fix the pipeline bugs listed above.**
   - A failed revise shouldn't persist its settings.
   - The `auto` surface mode should keep material colours, and `bake` should be documented.
   - `target_tris` should work on imported meshes.
   - Earlier exports should be kept, by version.
3. **`vfx_make` and apply-to-rig.** Build an aura into a preset from library layers (flames, spikes, glow,
   lightning, ring), and put any preset on a named character. Then "make it blue" is one `revise preset recolor`
   call. Upload the VFX textures so library presets render in Studio.
4. **An animation layer.** KeyframeSequence presets (run, walk, idle) with parameters such as cycle time, stride,
   arm swing and lean. Then "faster sprint, bigger arm swing" is a parameter revision, not a rewrite.
5. **A sturdier Studio bridge.** A UTF-8 BOM in a Luau file hung the bridge on both sides. The bridge should strip
   the BOM and time out instead of hanging.

## Method

- **Sides:** each side ran as a fresh Claude Code subagent with the same model and effort. Both had Bash, file
  tools, headless Blender 5.0 and a thin bridge to Roblox Studio's own MCP tools (`execute_luau`,
  `screen_capture`): `bench/luau.py`.
- **Harness access:** the harness side also had asset-agent, called through `bench/harness.py`. It runs the same
  tool functions as the MCP server and returns the same one-line results; the session's MCP server was an older
  build. The harness side was told to use the harness wherever it had a tool for the job.
- **Isolation:** the native side was told not to touch the harness, its library, or the place's existing VFX
  packs. Neither side could see the other's work. Runs went one at a time so they didn't compete for Blender or
  Studio.
- **Measurement:** tokens and times come from each subagent's transcript (`bench/usage.py`, `bench/collect.py`),
  split at the revision prompt. Where a transcript undercounts output tokens, they are estimated from the content
  actually written.
- **Noise:** there was one run per cell, so expect roughly ±25% noise on time. The large gaps (palm, aura) are
  well outside that.
- **Recording:**
  - Palms are Blender turntables at one shared scale per side (`bench/turntable.py`).
  - Auras are Studio viewport captures (`bench/record.py aura`).
  - Run cycles are posed frame by frame on an R15 puppet using our own forward kinematics (`bench/puppet.lua`).
    They are sampled at 30 fps and shown at 1/3 speed, so the faster sprint really does play faster. Cubic easing
    is drawn as linear.
- **Files:** everything is in `bench/`:
  - task prompts: `tasks.json`
  - each side's scripts and outputs: `runs/`
  - raw numbers: `results.json`, `stats.json`
  - the GIF builder: `compose.py`
