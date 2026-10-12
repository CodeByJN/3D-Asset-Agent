# 3D-Asset-Agent

A low-token 3D asset harness for Claude and other LLM agents. It builds on [Blender MCP](https://github.com/ahujasid/blender-mcp) and AI text/image-to-3D generators to produce game-ready assets, mainly for Roblox.

- **Low token cost.** Tools return one-line summaries, images are opt-in, and the server reports diffs instead of full scene dumps.
- **Modular assets.** Geometry, topology, UVs, surface, finish and collision are separate layers, so a revision rebuilds only what changed.
- **Validated output.** Each asset is checked against a polycount budget and for manifold geometry, UVs and scale, then exported as FBX/GLB for Roblox or other engines.

See [docs/PLAN.md](docs/PLAN.md) for the full plan.

## Quick start (free, no API keys)

```python
from asset_agent import make_asset, Asset

# text -> image (FLUX.1-schnell) -> shape (Hunyuan3D-2) on free Hugging Face Spaces,
# then decimate to the Roblox budget, UV, texture, validate and export
print(make_asset("assets/chest", prompt="a wooden treasure chest, low poly"))
print(make_asset("assets/chest_flat", prompt="a wooden treasure chest, low poly", style="flat", color=[0.7, 0.45, 0.25]))

a = Asset("assets/chest")
a.revise("finish", tint=[1, 0.8, 0.8])      # re-exports only
a.revise("topology", part="main", target_tris=2000)
```

- `style="project"` paints the generated reference image onto the front; `style="flat"` is one colour × ambient occlusion, and recolouring is a finish-only change.
- Works anonymously. Set `HF_TOKEN` (a free Hugging Face account) for more daily GPU time.
- Generations are cached in `library/cache/`, so the same request is never run twice.
