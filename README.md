# 3D-Asset-Agent

A low-token 3D asset harness for Claude and other LLM agents. It builds on [Blender MCP](https://github.com/ahujasid/blender-mcp) and AI text/image-to-3D generators to produce game-ready assets, mainly for Roblox.

- **Low token cost.** Tools return one-line summaries, images are opt-in, and the server reports diffs instead of full scene dumps.
- **Modular assets.** Geometry, topology, UVs, surface, finish and collision are separate layers, so a revision rebuilds only what changed.
- **Validated output.** Each asset is checked against a polycount budget and for manifold geometry, UVs and scale, then exported as FBX/GLB for Roblox or other engines.

See [docs/PLAN.md](docs/PLAN.md) for the full plan.
