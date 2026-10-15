# VFX

Particles, beams, auras, impacts. 86 presets are graded in `examples/vfx/`. What separates the 9-10s from the 1-4s:

1. **Authored textures and flipbooks.** The top scores are imported packs with hand-made flipbooks (`rei_treasure`,
   `rei_explosion_a`, `rei_shock_bubble`: 10). Code-drawn textures plateau around 7.
2. **Layers with a job each**: core, glow, sparks, smoke, light. One plain emitter reads as cheap (`fire` 3: "plain
   flames"; `smoke` 1: "slow grey puffs").
3. **Readable at game distance and on mobile**: bright core, clear shape, not a fog.
4. **Timing**: bursts that pop and settle; loops without visible restarts.

Ceiling noted on Sol's RNG-style auras: more layers stopped helping at 7/10; the next step is authored hero assets
(meshes, flipbooks), not more particles.
