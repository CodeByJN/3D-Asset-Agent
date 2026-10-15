# Roblox technical standard

Hard requirements before anything goes in a game. The `blender` server's `inspect` checks all of them.

## Limits
- **20,000 triangles per MeshPart.** Split bigger models into parts (a boss: body, head, tails) or decimate.
  Budgets in the harness: prop 5k, hero 20k, boss 60k across parts.
- **One texture per MeshPart, at most 1024 px.** Bake materials and vertex colours into one image (`bake_texture`).
- **Size in studs.** 1 stud = 0.28 m. An R15 avatar is about 5.5 studs tall; a door about 7; a room 12-16.
  Models sit on the ground (lowest point at 0), facing -Y in the kit (forward in Roblox).
- **Under 2048 studs** on any side.

## Clean geometry (from `inspect`)
- No duplicate vertices on the shape (unwelded seams), no loose vertices or edges, no zero-area faces.
- Normals consistent and pointing out (no inside-out patches: they render as holes in Roblox).
- Watertight where it matters (open edges show as holes from some angles); remesh seals them.
- One connected piece unless it's meant to be several (floating bits from generators: `keep_largest`).
- UVs inside 0-1 with little overlap (overlap makes a baked texture smear), covering a reasonable share of the image.

## Colour
- Blender material colours are linear; textures are sRGB. Pick colours as they should look in Roblox and convert,
  or they come out pale (see [[Pale colours]]).
- Glow is a separate part with the Neon material, not a texture.

## Moving parts
- Anything that animates separately (jaw, tails, wings, limbs) is its own part or its own bones, with geometry
  overlapping at the joint so bending never opens a gap. See [[Fused parts]].
