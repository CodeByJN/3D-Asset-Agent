---
type: "failure"
tag: "over-budget"
---

# Over budget

**Symptom.** Far more triangles than the asset needs (or than Roblox allows per mesh: 20k).

**Cause.** Raw sculpts, scans or generator output shipped without decimation; detail the style doesn't show.

**Fix.** Decimate to the budget for its size and style (`cleanup` decimate, `quality/standards/Roblox technical`); blocky styles need hundreds of tris, not tens of thousands.

## Seen in
- (tag examples with `failures: ["over-budget"]`)
