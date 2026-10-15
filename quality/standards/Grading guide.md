# Grading guide

A grade is an **overall** number (0-10, half points allowed; see [[Rating scale]]) plus whatever of the following
you can say. Only the overall is required; every other field is optional, and a blank is better than a guess.

## Sub-scores (0-10 each)

| Dimension | Judges | 10 looks like | 2 looks like |
|---|---|---|---|
| shape | the mesh itself: form, silhouette, proportions | Gothic dragon statue: reads instantly, clean | a stack of grey blocks |
| surface | texture, colour, materials | Village house pack: every surface textured, strong colours | flat single colours, "lacks depth and texture" |
| vfx | effects: fit and frame the model (blank if none) | Swords Pack (#14): uses VFX perfectly | water sword: only the aura is visible |
| function | works in a game: scripts, animations, usability (blank if n/a) | Sword System (#11): comes with its animations | a model that can't be used as it is |
| fit | belongs in Roblox and in its genres | clean, would sit in many Roblox games | out of place (too realistic, wrong style) |

The overall is your call, not an average: a great mesh with VFX that ruin it can be shape 8, vfx 3, overall 6.

## Also

- **within its style** (`style_score`): how good it is among assets of its own style, separate from your taste.
  A stud tree you dislike can be overall 3 and within its style 7.
- **genres**: the games it fits (traditional, hangout, roleplay, realistic, horror, stud, simulator, ...).
- **judged from**: `thumbnail` (a store picture), `studio` (looked at in Studio) or `review` (our review window).
  Thumbnails show one angle the creator chose; note it when the angle hides the model.
- **failures**: tags from `failures/` when one applies.

## Quick format in chat

`#3 6, shape 8 vfx 3 fit 7, hangout: the mesh is good but the VFX ruin it`

Number first, then any sub-scores, genres, and your words. The words matter most: they become the notes.

## Why

These grades are post-training data. Sub-scores separate what was wrong (a bad mesh vs bad effects), the style
score separates craft from taste, and `quality pairs` turns grades in the same search or across an asset's
versions into chosen/rejected pairs for preference training.
