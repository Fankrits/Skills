# <Name> — Image Guide

How to generate new <Name> images that stay consistent. Read this before any generation.

Type: <character | product | style series | scene series>

## References

| File | Use |
|---|---|
| `<name>-sheet.png` / `<name>-board.png` | **Primary.** Approved visual truth |
| `<attr>-ref.png` | One attribute only (for example, a colour or a logo) |
| `<old-file>` | **Outdated:** <what's wrong>. Use for <X> only |

Always attach: <primary> + <attribute refs>.

## Fixed traits

Keep only the block for your type. Make every line concrete and countable.

**Character:** body shape and material · head · eyes and brows (count, colour) · cheeks · mouth (always visible? teeth?) · back and tail · limbs · signature detail

**Product:** silhouette and proportions · materials and finish (matte, gloss, texture) · colourways with hex values · logo (placement, size, colour) · hardware and details · parts that must never change

**Style series:** line weight (px at 1024) · corner and shape language · palette (named hex values, which ones are accents) · shading (flat, cel, soft) · light direction · texture or grain · level of detail · framing and margin

**Scene series:** light (key direction, time of day) · camera (lens, height, angle) · colour grade · mood · composition rules · recurring props

## Palette

| Part / role | Hex | Sampled from |
|---|---|---|
| | `#` | `<file> @ x,y` |

## Never

- <each drift seen so far, one line>
- Text, logos, or watermarks unless the brief asks
- <for cutout types:> a floor, a cast shadow, or a vignette

## Identity / style block (paste verbatim into every prompt)

> <one paragraph: concrete and countable, with CAPS + NOT for the traits that drift>

## Background rule

<flat white #FFFFFF, not touching the edges | the scene rules>

## Pipeline

1. Generate: `gen.sh <out.png> "<brief>"` (at most 2 in parallel)
2. Measure: fill `scorecard.csv` (one column per checklist line), run `scorecard.sh` (target ≥ 95%), then run `qa.sh`, `palette-score.sh` and `contact-sheet.sh`
3. Fix: an edit pass for a single trait; a regenerate for pose or composition (2 attempts at most)
4. Cut out (white types): `cutout.sh`, then `fringe-check.sh`
5. Export: `export-webp.sh cut.png final.webp <maxw>`
6. Provenance: keep the prompt beside the image, and add a row below

## Checklist (= the scorecard columns)

- [ ] <every fixed trait as a yes/no check>
- [ ] Nothing beyond the brief
- [ ] No text
- [ ] A clean cutout on dark, brand, and white grounds (cutout types)

## Outputs

| File | Brief used |
|---|---|
| | |
