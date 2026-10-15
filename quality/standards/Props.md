# Props

Weapons, furniture, items, scenery. Rubric, in order of how much it moves the rating:

1. **Silhouette and proportions** match the reference or the brief. Readable at game distance.
2. **The detail that makes it this object**: the hilt and blade shape of a named sword, the bricks on a stone base.
   Missing detail against a reference costs the most ([[master_sword v2]], 5: "lacking detail vs the reference").
3. **Presentation**: lighting and VFX can carry a prop ([[master_sword v5]], 9: "the lighting and vfx are the key").
4. **Clean and in budget**: see [[Roblox technical]].

## Method
- Hard-surface, modular or exact-size props: `build` (modelled in code) beats generation: exact dimensions,
  crisp edges, matching sets.
- Organic props (trees, rocks, creatures' parts): generate with Hunyuan, then clean in the `blender` server.
- Ask for a reference image when the user has one in mind; without one, say what you assumed.
