# Harness gaps found by the benchmark

## Palm tree (harness run)
- make_asset (free HF backend) took 522 s and produced a potted plant at 21,977 tris for "low-poly palm tree".
- revise topology target_tris=3500 left the tri count unchanged.
- import_mesh style "auto" came out flat grey; colours only came back with surface mode "bake" (undocumented). "keep"/"texture" errored.
- A failed revise still saves the bad setting, so the next rebuild fails until it is corrected.
- revise geometry source keeps the old scale unless keep=[] is passed.
- Export clears the export folder each time, deleting copies saved there (v1/v2 side by side impossible).
- No tool to recolour one material (fronds only); the agent edited its own Blender script instead.
- No modelling tool: when the generator fails, the agent writes bpy itself, then the harness only post-processes.

## Notes from native runs
- Native aura: Edit-mode emitters did not emit in this place; the agent drove emission itself from a per-frame hook (edit-session only). Play mode untested.
- Native aura: a PowerShell-written BOM in a Luau file hung the Studio bridge once.

## Super Saiyan aura (harness run)
- No tool builds a new character aura; the agent hand-wrote Luau (cloning Rei pack emitters already in the place, found via library/vfx_import).
- vfx_lab of aura_dark recoloured gold showed nothing visible; the lab stand-in was only a smoke + spark emitter.
- A UTF-8 BOM in a Luau file hangs the Studio bridge instead of erroring (hit by both sides).
- Aura revision: revise(layer=preset, recolor) only works on library presets; a hand-built aura can't be recoloured by the harness, so the agent edited its script.

## Run cycle (harness run)
- No animation tool at all: the harness side made zero harness calls and wrote the KeyframeSequence by hand, same as native.
