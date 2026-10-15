# Quality vault

The standard of quality for 3D-Asset-Agent, and the record of every graded result. Open this folder as an
[Obsidian](https://obsidian.md) vault (*Open folder as vault*), or read it on GitHub: it's plain Markdown.

| Folder | What's in it |
|---|---|
| `standards/` | What good looks like: the [[Rating scale]], [[Roblox technical]] limits, and a rubric per kind of asset ([[Props]], [[Characters]], [[Creatures and bosses]], [[VFX]], [[Animation]]). |
| `failures/` | Failure patterns seen in real results: the symptom, why it happens and the fix. Tag examples with them. |
| `examples/` | One note per graded result (asset, VFX preset or animation version): stars, verdict, how it was made, numbers, a thumbnail and the reviewer's words. |
| `dataset/` | `ratings.jsonl`, compiled from the notes by `python -m asset_agent quality export`. |
| `_templates/` | Obsidian templates for hand-written notes. |

## How notes get here

- **Automatically**: every `rate` (in chat or the review window's stars) writes or updates
  `examples/<kind>/<name> v<version>.md`.
- **Backfill**: `python -m asset_agent quality sync` writes notes for every rating already in the repo.
- **By hand**: add `failures` tags, fix a `category`, or write a note for something made elsewhere (use the
  template). Hand-edited fields (`category`, `share`, `tags`, `failures`) survive automatic rewrites.

`python -m asset_agent quality summary` counts results by kind and verdict and lists the most common failures.

## Sharing and the open dataset

Notes default to `share: false`. Test projects can use other games' characters and art, so nothing leaves the vault
unless a note is marked `share: true`. `quality export` writes only shared notes (`--all` includes everything, for
local use). Contributors add results the same way: a pull request with their notes (and thumbnails, 256 px).

Each dataset row is the note's frontmatter plus its feedback text: enough to evaluate the harness (does a change
raise average stars per category?) and to train or prompt-tune on what reviewers liked and disliked.
