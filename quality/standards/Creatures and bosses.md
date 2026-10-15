# Creatures and bosses

Big non-human models with their own rigs: beasts, monsters, bosses (the Kurama test, `tools/kurama`).

1. **The face carries it.** A clean, smooth replica of the reference face beats any amount of body detail
   ([[kurama v8]], 6.5: "face reads as geometric shapes thrown together").
2. **Silhouette and proportions** from a model sheet: front and side views of the same pose. Painted close-ups
   alone mislead (see [[Flat sheets from painted refs]]).
3. **One connected, smooth body**: no visible primitives, seams or clutter ([[kurama v4]]: "too many spiky hair,
   joints are flush but awkward"). See [[Primitive soup]], [[Spike clutter]].
4. **Parts that move are separate and overlap at joints**: jaw, tails, legs. See [[Fused parts]].
5. **Signature features are exact**: Kurama's black eye bands into the ears, tail count and shape, chakra-mode
   markings ([[kurama v8]]: "chakra form is missing the black line markings").
6. **It moves like it's alive**: idle motion everywhere (tails sway), weight in attacks, screen shake on impacts.

## Method
- Shape: Hunyuan from a clean concept image (plain background, 3/4 view, the whole subject). Model sheets work.
- Clean it in the `blender` server; split moving parts; rig with bones (skinned) rather than rigid pieces.
- Markings and exact graphics: paint them on (`paint`/`decal` in the kit, or a projected sheet view).
- Review in stages: head shape, eyes, mouth, markings, then body, then motion. See [[Staged review]].
