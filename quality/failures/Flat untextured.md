---
type: "failure"
tag: "flat-texture"
---

# Flat untextured

**Symptom.** Good shapes in flat single colours: walls, roofs and wood with no grain, tiles, stone or wear.
The model lacks depth.

**Cause.** Colour per part only; no texture bake, no material variation.

**Fix.** Texture every surface for what it is (roof tiles, planks, stone courses, trim), with value variation and
edge wear; bake to one 1024 texture. A good mesh left flat loses about 2 points.

## Seen in
- (tag examples with `failures: ["flat-texture"]`)
