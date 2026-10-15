---
type: "failure"
tag: "pale-colours"
---

# Pale colours

**Symptom.** Textures come out washed out (orange looks tan).

**Cause.** Blender material colours are linear; written as sRGB they lighten.

**Fix.** Convert sRGB to linear when setting material colours (`lin()` in the Kurama model).

## Seen in
- (tag examples with `failures: ["pale-colours"]`)
