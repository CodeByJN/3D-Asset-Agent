# Shape routing

Who makes the shape and the texture, decided from the brief before anything is generated.

| Route | Use for | Shape | Texture |
|---|---|---|---|
| **claude** | weapons, tools, buildings, furniture, props, vehicles, modular kits, anything built to measurements | Claude in code (`build`, kit), from the brief and measured facts | Claude procedural materials, baked to one 1024 texture |
| **hunyuan** | creatures, characters, faces, organic sculpted forms (dragons, monsters, plants with organic trunks) | Hunyuan3D from a clean reference image (3/4 view, plain background), then Claude cleanup in Blender | Hunyuan paint, then Claude fixes |
| **hybrid** | organic parts on built things, or creatures with hard parts (a dragon statue on a stone plinth, a monster with armour, a tree house) | split into parts: organic parts from Hunyuan, built parts in code, joined in Blender | per part, as above |
| **import** | VFX and animation | adapt from the library (imported presets, keyframe sequences) | - |

**Deciding**
- Built to exact dimensions or repeated in variants → **claude**.
- Has a face, muscles or flowing organic form → **hunyuan**.
- Both kinds of part → **hybrid**; split before generating, not after.
- No clean reference image for an organic asset → get one first (a model sheet or a 3/4 view); Hunyuan from dark
  painted references gives flat sheets ([[Flat sheets from painted refs]]).
- Unsure → **claude** first for a quick blockout (seconds), then decide.

**Evidence:** master_sword (claude) 9/10; Kurama's face in code 5-6.5 vs the Hunyuan head chosen at once.

See [[Grading guide]], [[Buildings]], [[Creatures and bosses]].
