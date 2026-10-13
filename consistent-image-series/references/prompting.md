# Prompting for Consistency

## Why images drift (every series type)

- **The model averages toward its prior.** Whatever is unusual about your subject gets pulled back to the generic version. A cute red monster gets pink blush and a closed mouth. A custom sneaker gets a generic sole. A flat icon set gets gradients. Every trait that differs from the generic version needs stating, every time.
- **A vague noun becomes a new material.** "Lighter salmon belly patch" came out as a smooth peach oval in every front and side view, even with the reference attached. A patch, panel or marking needs its material named ("the SAME shaggy plush fur, only lighter") and what it is NOT.
- **The reference beats the text.** When the attached image shows X and the text says Y, X usually wins. Fix the reference, or add a single-attribute reference that wins for that one trait.
- **The angle or pose hides features.** Back views, close crops, sleeping or peeking poses, and top-down product shots are where details vanish. Restate the feature *in the brief*, phrased for that view.
- **Long prompts dilute.** Put the identity or style block first, then the brief. Don't scatter traits through the brief.
- **"Fix the reference" turns into "copy the reference".** Given an old sheet, models reproduce it almost exactly, flaws included. Follow up with a targeted edit pass.

## The identity / style block

Write it once in the guide and paste it verbatim. Make it concrete, countable and positive, and use CAPS plus NOT for each trait that has already drifted.

Character (worked example, a plush mascot):
> red plush fur; rainbow-gradient two-leaf sprout on top of the head; curly fur tuft on the forehead; two small dark-red eyebrow marks; big sparkling dark eyes; CHEEKS are round soft peach-orange blush patches (NOT dark red, NOT pink); the MOUTH is ALWAYS visible: a small open smile with one tiny white fang; soft orange spikes down the back; short tail.

Product:
> 500 ml cylindrical bottle, height:width 3:1; brushed stainless-steel body; matte black flat screw cap with 12 vertical grip ridges; ONE thin engraved ring 2 cm below the cap; plain body with NO logo and NO text (the logo is added later).

Style series (icons):
> flat vector icon; 2px uniform rounded stroke in #1F2937 at 1024px; flat fills ONLY from #F97316, #FDE68A, #FFFFFF; NO gradients, NO shadows, NO 3D; rounded corners; one subject centred with a 12% margin.

Scene series:
> 35mm lens at eye level; soft key light from the upper left, late-afternoon warm grade; muted terracotta and sage palette; shallow depth of field; calm and uncluttered; NO people unless the brief says so.

Patterns:
- **Count things:** "two-leaf", "one fang", "12 grip ridges", "2px stroke".
- **Give every part a material and a colour:** "red plush fur", "brushed stainless steel", "flat fill #F97316".
- **Use CAPS plus NOT** for each trait that has drifted before. Each drift you catch earns one.
- **Say what each reference is for:** "the third reference is used ONLY for cheek colour", "use ONLY for the cap shape".

## Single-attribute references

When one trait keeps drifting, give it its own image: a close-up crop of an output that got it right, a photo of the real material, or the real logo. Name it in the prompt and limit it ("use ONLY for …"). A picture of the trait works better than any adjective.

## The background contract

For anything you'll cut out, generate on one flat colour: "completely empty, NO floor, NO cast shadow, NO contact shadow, NO vignette; must not touch the image edges". This makes the magick cutout deterministic, and every output then shares one shadow added in the layout.

- The default is pure white `#FFFFFF`.
- **For white or very pale subjects** (white shoes, a porcelain mug, a cream sweater), use flat mid grey `#808080`, or a colour the subject doesn't contain. Then pass `BG="#808080"` to `cutout.sh`, `qa.sh` and `palette-check.sh`. On white, pale details disappear: in testing, a white mug lost its #EEEEEE handle.
- Avoid chroma green for hair, fur, glass or shiny metal. The green spills into the edges and reflections.
- If the subject must be cropped (peeking over a ledge, a product cut off at the frame), say exactly where: "bottom edge cuts straight across below the hands".

Scene series don't get a cutout. Their contract is the guide's light, camera and grade rules.

## Briefs

- **Character:** pose → expression, with the fragile trait restated → one prop → framing → aspect ratio. "3/4 view, full body, back spikes and tail visible, holding a yellow tailor's tape, small focused smile with the fang".
- **Product:** angle (front, 3/4, top-down, detail) → state (cap on or off, open or closed) → framing → aspect ratio. Name the angle precisely: "3/4 from the front-left, camera slightly above the cap".
- **Style series:** subject → composition → which palette colours are allowed → margin. Keep one subject per icon.
- **Scene:** subject and location → time of day and light, restated → camera → the grade, restated.
- Use one prop or context element at most, and name its colour and material.

## Edit pass (the fix that works)

> Use your image generation tool to EDIT the image `<path>`. Reference for `<trait>`: `<single-attribute ref>`. Change ONLY `<trait>`: on every `<figure / panel / view list>`, `<exact change>`. Keep everything else identical: layout, text, poses or angles, `<other fragile traits>`, colours. Save the result to `<new path>`.

List where the change applies (every figure, every panel). Otherwise it fixes one place and leaves the rest. Always save to a new path.

## Reference sheet requests

Spell out the layout, ask for "correct spelling" and "no other text", and attach the old reference plus any single-attribute refs. Ask for one sheet per art style.

| Type | Layout to request |
|---|---|
| Character | Top row: head close-ups with 3 expressions, plus detail panels. Middle: front, 3/4 front, side, 3/4 back and back, all on one ground line at the same height. Bottom: palette swatches with hex values, materials, notes |
| Product | Front, 3/4, side, back and top at the same scale on white. Detail crops (closures, texture, logo area). Palette and finish swatches |
| Style series | A 3×3 or 4×2 grid of the approved subjects in the style, each in its own cell, plus a palette strip with hex values |
| Scene series | 2–4 approved scenes as tiles, plus a strip of palette and grade swatches |

## Operational

- Run 1–2 generations in parallel. With 4, some timed out (`--print-timeout 900s` helped).
- Quotas run out mid-batch. Keep a handoff note of what's left (the briefs plus the checklist) so the batch can resume later.
- Never overwrite a raw output. Version the folders (`gen/v1`, `v2`, …) when the guide changes.
- Logos and text in images are unreliable. Generate a blank area and composite the real asset with magick.
