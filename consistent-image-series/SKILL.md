---
name: consistent-image-series
description: Generate AI images that stay consistent and ship them in any format — the same character or mascot, the same product, the same visual style across icons, illustrations and stickers, or the same look across scenes and banners — using a written guide (.md) plus a reference sheet or style board, a fixed identity/style prompt block, objective ImageMagick QA, and an edit-not-regenerate fix loop; then cut subjects out and export every deliverable (web, social, OG, favicon/app icons, print CMYK with bleed, stickers, print-on-demand, email, animation, sprite sheets) from one approved master. Use whenever the user wants several images that must match, says generated images "look different each time", wants a character sheet, product sheet or style board created or fixed, wants a background removed or an image made transparent with magick, or asks how to keep AI image generation consistent, or needs one image resized and exported for several purposes. Also trigger when setting up a reusable image guide for later generations.
---

# Consistent Image Series

A generator has no memory between calls, so consistency has to come from what you send it. Every call gets three things that never change:

1. **A reference image:** a turnaround sheet (character), a product sheet (object), or a style board (style series). This is the visual truth.
2. **A guide (`.md`):** the words that pin down what the picture leaves ambiguous, plus a "never" list built from every drift you catch.
3. **A fixed identity or style block**, pasted verbatim into every prompt. Only the per-image brief changes.

You then check the image by eye and with numbers, and fix drift by editing it.

Scripts are in `scripts/` (run them with `bash <skill-dir>/scripts/<name>.sh`). They need ImageMagick 7 (`magick`), plus `cwebp` for WebP. Read `references/prompting.md` before the first generation.

## 0. Pick the series type

| Type | Reference image | The guide pins down | Background | Cutout? |
|---|---|---|---|---|
| **Character / mascot** | Turnaround sheet: head close-ups, front, 3/4, side, back, palette | Anatomy, countable features, expressions, palette, never-list | Flat white | Yes |
| **Product / object** | Product sheet: front, 3/4, side, back, top, detail crops (logo, texture, hardware) | Proportions, materials and finish, exact colours, logo placement, what must never change | Flat white; flat grey for white or pale products | Yes |
| **Style series** (icons, illustrations, stickers) | Style board: 4–8 approved examples plus palette | Line weight, shape language, palette with hex values, lighting, texture, framing, level of detail | The guide's rule (often flat white) | When white |
| **Scene series** (backgrounds, banners, editorial, photo-style) | Style board plus one approved scene | Lighting, camera and lens, colour grade, time of day, mood, composition rules | Full scene, at the target aspect ratio | No, skip step 7 |

Mixed (a character inside full scenes): use the character sheet *and* a scene style board, but skip the cutout.

**No reference yet?** Bootstrap one. Generate the first image from the identity or style block alone (`REFS` empty: gen.sh marks it as the anchor), approve it, then set it as `REFS` for every image after it. Tested this way, an icon series (cart, then heart) kept its stroke, split fill and palette, a product kept its shape across two angles, and two café scenes kept the same room and grade (ΔE 1.9).

## 1. Gather and audit the references

- Read every reference image yourself.
- **Audit before trusting it.** Generated sheets often have nonsense labels, duplicated or mislabelled views, and traits that contradict the brief. Any error in the reference shows up in every output.
- When the user's chosen trait differs from the reference, the user wins. Make a **single-attribute reference** (a crop that shows only that trait) and record the decision in the guide.

## 2. Write the guide

Copy `templates/guide.md` and fill in the section for your type. It needs:
- the reference files, with outdated ones marked "use for X only"
- concrete, countable traits
- a palette with sampled hex values (`scripts/extract-palette.sh`, `scripts/sample.sh`), not guesses
- a Never list
- the identity or style block
- the pipeline and a checklist
- a table of outputs with the brief each one used

Every drift you catch becomes a new line in the guide.

## 3. Create or fix the reference (when it's missing or wrong)

Ask for the sheet or board with the old one attached. Spell out the layout: panel names, view order, every view at the same height and scale, labels spelled correctly, a palette table with hex values, "no other text". Make one sheet per art style.

Expect the generator to copy the old reference almost exactly, flaws included. Follow up with an **edit pass**: "Change ONLY X on every figure/panel… keep everything else identical." Save the approved version under a clear name and keep the old one, labelled as outdated.

## 4. Generate

Copy `templates/series.env` next to the guide and fill it in, then run `SERIES=path/series.env templates/gen.sh out.png "<brief>"`. To use a generator other than agy, change its last command. The prompt order never changes:
1. the references, saying what each one is for
2. "Must match:" plus the identity or style block, verbatim
3. hard negatives: no redesign, no extra elements, no text
4. the background rule
5. the brief

Brief order for a character or product: pose or angle → expression or state, **restating the fragile traits** → one prop or context → framing → aspect ratio. For a style series: subject → composition → which palette colours → framing. For a scene: subject and place → light → camera → **aspect ratio of the final use** (16:9 banner, 9:16 story), so the crop doesn't cut it later.

- For a whole series, put one `name|brief` per line in a briefs file and run `SERIES=series.env templates/run-series.sh briefs.txt raw/`. It runs 2 at a time (4 hit timeouts), skips outputs that already exist, and stops with exit code 3 when the generator reports a quota or rate limit. Rerun the same command after the reset to continue.
- Never overwrite a raw output.

## 5. Measure consistency: scorecard first, then numbers

Consistency is a number, not a feeling. For every series, copy `templates/scorecard.csv`. Make one column per trait in the guide's checklist, plus `no-extras` and `in-frame`, and one row per image. Judge each image next to the reference: 1 = on-model, 0 = drift, `-` = not visible in this view. Never guess: a trait you can't see is `-`, not 1. Then:

```bash
scripts/scorecard.sh scorecard.csv     # pass rate per trait, per image, and the series score
```

| Series score | Meaning | Action |
|---|---|---|
| ≥ 95% | consistent | ship; 100% for every image that actually ships |
| 85–95% | drift in a few traits | fix loop below |
| < 85% | the guide or prompt is wrong | rework the identity block and references before generating more |

**The fix loop.** Measured on a real 5-image character series: the first pass scored 93.9%, with the belly at 0/2. After one edit pass per drifted image plus the strengthened belly line, it scored **100% (55/55)**, and the new images came out right on the first try (belly 1/1 where visible):
1. The **weakest trait** (under 90%) is a prompt problem, not bad luck. Rewrite its identity line to be concrete. Name the material and the colour, and say what it is NOT ("BELLY is the SAME shaggy plush fur, only slightly lighter salmon-red #C85E51, NOT a smooth peach oval"). Add a single-attribute crop of it from the reference to `ATTR_REFS`.
2. Fix the drifted rows with `templates/edit.sh in.png out.png "<trait>" "<exact change>"` (one trait per pass).
3. Re-judge only the edited cells, rerun `scorecard.sh`, and add the new rule to the guide's Never list, so the next image is born right.

Then the objective checks:

Look at every output next to the reference, and go through the guide's checklist. Then:

```bash
scripts/qa.sh raw.png                    # cutout types: corners = BG? subject touches an edge? (BG="#808080" if not white)
scripts/palette-check.sh raw.png --crop WxH+X+Y 5 "#HEX:feature"   # colour presence in a region
scripts/contact-sheet.sh board.png ref-crop.png out1.png out2.png   # side by side, one height
scripts/grade-check.sh anchor.png scene2.png scene3.png              # scenes: mean-colour distance ΔE
BG="#FFFFFF" scripts/grade-check.sh out1.png out2.png ...           # cutout series: the subject's colour only
scripts/palette-score.sh palette.txt anchor.png img1.png img2.png ... # series: colour-mix similarity + off-palette share
```

- **`palette-score`** snaps every subject pixel to the guide's palette (`templates/palette.txt`). **Off-palette** is new colour: a prop the brief named, or drift (an accessory, a wrong material). **Similarity** compares the colour mix with the anchor. Pose moves it (79–100% across a real on-model series), so look for the outlier: a different object scored 9.8% similarity and 82% off-palette. It can't see a small feature (cheeks on a sheet moved it only 100 → 94%). That's the scorecard's job.

- **`palette-check` is relative.** Compare the same crop of the approved reference with the candidate. Crop to the feature whenever its colour appears elsewhere too. In testing, the face crop separated wrong from right cheeks (1.2% vs 3.5%); the whole image couldn't (2.1% vs 2.7%).
- **`contact-sheet` is the drift detector.** Differences you can't see one image at a time are obvious side by side. On the first real use, it caught a belly texture that had drifted across four "approved" images.
- For a style series, also put the new output next to the board examples. Stroke weight and palette drift show up immediately. Normalise every image to one canvas and margin first (magick recipe), otherwise the size differences hide the style differences.
- For a style series, `palette-check.sh` with every allowed colour shows how much of the image is off-palette: 100% minus the sum. In testing, the cart and heart icons were about 95% on-palette (the rest is anti-aliasing).
- For scene series, `qa.sh` doesn't apply. Use `grade-check.sh` against the anchor: ΔE under 3 is the same grade; over 6 means it drifted (in testing, a 20% saturation shift scored 22). Then use `contact-sheet.sh` for composition and props.
- For cutout series, always pass `BG`. Without it, framing dominates: a sideways sleeping pose and a tight reference crop both scored "DRIFT" (ΔE 8–18) on whole-image means, while on the subject alone the on-model series sat at ΔE 1.7–3.2 and a hue-shifted copy at 33.8. Use an output as the anchor, not a cropped sheet.

## 6. Fix drift

| Drift | Fix |
|---|---|
| One trait wrong (colour, a missing feature, the wrong logo) | Edit pass with the single-attribute reference attached |
| Pose, angle or composition wrong | Regenerate with a more specific brief |
| Touches an edge | Regenerate with "generous margin", or crop flat on purpose |
| Grey or gradient backdrop | Level it first (`references/magick-recipes.md`) |
| A flat-style colour patch | Deterministic recolour with shape masks (magick recipe) |
| A wrong or garbled logo or text | Generate a blank area, then composite the real asset (magick recipe) |

Two attempts per image at most. After that, report what's still off.

## 7. Cut out (types on a flat background only)

```bash
[BG="#808080"] scripts/cutout.sh raw.png cut.png [fuzz=8] [hole_area=1500]
scripts/fringe-check.sh cut.png halo.png "#brand"     # look at it: dark | brand | white
scripts/export-webp.sh cut.png final.webp 1200
```

`cutout.sh` flood-fills from the border, so background-coloured details inside the subject survive. White or pale subjects must be generated on grey and cut with `BG`: on white, a test mug lost its handle. It clears enclosed gaps above the area threshold, erodes and softens the alpha edge to remove the halo, then trims. Never use a global `-transparent white`.

**When magick isn't enough:** fine hair against texture, glass, smoke, motion blur, or anything not on flat white. Use an AI matting tool instead (`rembg i in.png out.png`, installed with `pipx install "rembg[cli]"`), then still run `fringe-check.sh`. Better still, regenerate on flat white.

Don't bake shadows into the images. Add them in the layout (CSS `drop-shadow`) or with the shadow recipe, using identical values for every image.

## 8. Export for the purpose

Keep one approved master per image, and derive every deliverable from it with `scripts/fit.sh` or a recipe in `references/purposes.md`. Covered there: web `srcset`, WebP and AVIF, e-commerce tiles, OG images, social posts and stories, banners, favicons, iOS and Android icons, stickers, print (300 DPI, bleed, CMYK), print-on-demand, email, animated WebP and GIF, sprite sheets, slides, seamless tiles. Don't regenerate per size: each extra generation is another chance to drift. Use the same margin for every image in a series.

## 9. Provenance

Keep, next to each final image: the exact prompt (gen.sh writes `*.prompt.txt`), the references used, the post-processing steps, and the raw source path. Then add a row to the guide's output table.

## Limits (say so upfront)

- Text inside images is unreliable. Add the text in layout instead.
- Real people: only with consent. Faces drift more than characters, so expect more edit passes.
- Exact logos and trademarks drift too. For products, composite the real logo with magick rather than trusting the generator.
- Photoreal scenes with many recurring people or objects: consistency drops with every extra subject. Keep one recurring subject per image where possible.

## Files

- `templates/guide.md`: the guide skeleton, with sections for each type
- `templates/series.env` + `templates/gen.sh`: per-series config, and the generator wrapper (fixed block + brief, anchor bootstrap, provenance)
- `templates/run-series.sh`: a whole series from a briefs file (2 in parallel, resumable, stops on quota)
- `templates/edit.sh`: an edit pass for one trait, with the attribute refs attached
- `templates/scorecard.csv` + `templates/palette.txt`: the consistency scorecard, and the palette for palette-score
- `references/prompting.md`: why drift happens, identity-block patterns, the edit-pass template, how to request a sheet
- `references/purposes.md`: export specs and tested commands for each purpose
- `references/magick-recipes.md`: cutout internals (any flat BG), levelling, edge marks, shadows, recolour, logo compositing, canvas normalising, palettes, review boards, export
- `scripts/`: `scorecard`, `palette-score`, `cutout`, `qa`, `palette-check`, `grade-check`, `extract-palette`, `sample`, `contact-sheet`, `fringe-check`, `fit`, `export-webp`. Every script honours `BG` where a background matters.
