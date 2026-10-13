# ImageMagick Recipes

All the recipes below are for IM7 (`magick`).

## Cutout (subject on a flat background)

Use `[BG="#808080"] scripts/cutout.sh in.png out.png [fuzz=8] [hole_area=1500]`. BG defaults to white. Use mid grey (or any colour the subject lacks) for white or pale subjects. Why each step:

| Step | Command core | Reason |
|---|---|---|
| Border flood-fill | `-bordercolor $BG -border 2 -fuzz 8% -fill none -draw "color 0,0 floodfill" -shave 2x2` | Removes only the background that connects to the edge. The 2px border lets the fill go all the way around the subject. |
| Enclosed pockets | mask of pure BG → `-connected-components 8` with `area-threshold` | Gaps between an arm and the body, or a mug handle and the mug, are background but don't touch the edge. Small BG-coloured areas (eye sparkles, a white button) stay because they're under the area threshold. |
| De-fringe | `-morphology Erode Disk:1.5 -blur 0x0.8` on the alpha | Anti-aliased edge pixels are part background, which shows up as a halo on dark grounds. Eroding then softening removes it. |
| Trim | `-trim +repage` | Tight bounds, so layout sizing is predictable. `+repage` drops the virtual canvas offset. |

Pitfalls:
- `-transparent white` without a flood-fill deletes every white detail (eye highlights, teeth, white print).
- If fuzz is too high (over 12%), it eats into pale parts of the subject. If it's too low (under 5%), a ring of background stays.
- A white subject on white: its pale parts (#EEEEEE and up) vanish. In testing, a mug lost its handle (305 px wide instead of 439). Regenerate on grey and pass `BG`.
- Soft, see-through edges (hair against texture, glass, smoke) are beyond fuzz-based cutouts. Use `rembg i in.png out.png` (`pipx install "rembg[cli]"`), then still run `fringe-check.sh`.
- JPEG artefacts around the subject need a higher fuzz, or a flood-fill from all four corners.

## Level an off-white or grey backdrop before the cutout

```bash
magick in.png -level 0%,92% out.png              # pushes light grey (≥92%) to pure white
magick in.png -fuzz 10% -fill white -draw "color 0,0 floodfill" out.png   # flood the backdrop to white
```

## Remove a stray mark on an edge

```bash
magick in.png -gravity north -chop 0x6 out.png   # cut 6px off the top (north/south/east/west)
magick in.png -shave 4x4 out.png                 # every side
```

## Consistent drop shadow (when it can't be done in CSS)

```bash
magick cut.png \( +clone -background black -shadow 35x18+0+14 \) +swap \
  -background none -layers merge +repage shadowed.png
```

`35x18+0+14` means opacity 35%, blur sigma 18, offset (0, 14). Use the same values for every image.

## Contact-shadow ellipse under the feet

```bash
w=$(magick cut.png -format %w info:)
magick -size ${w}x60 xc:none -fill 'rgba(0,0,0,0.25)' -draw "ellipse $((w/2)),30 $((w/3)),14 0,360" -blur 0x8 shadow.png
magick cut.png -background none -gravity south -splice 0x30 shadow.png -compose DstOver -composite out.png
```

## Deterministic recolour of one feature (when an edit pass fails)

Paint the target colour through soft shape masks drawn at the feature's position (ellipse, rectangle, polygon). Tested on a flat cartoon: rosy cheeks became clean peach blush. It suits flat styles and flat colour patches (an icon fill, a product panel). On fur, fabric or photographic texture, prefer the model's edit pass, which keeps the texture.

```bash
# one shape per patch: ellipse cx,cy rx,ry | rectangle x0,y0 x1,y1; blur = edge softness (0 for crisp icons)
magick in.png -fill black -colorize 100 -fill white \
  -draw "ellipse 108,393 18,11 0,360" -draw "ellipse 218,393 18,11 0,360" -blur 0x4 mask.png
magick in.png \( +clone -fill "#F1956C" -colorize 100 \) mask.png -composite out.png
```

Only build the mask from the wrong colour itself (`-fuzz 10% -opaque "#WRONG"`) when that colour appears nowhere else. When it's close to the colour around it (a rosy cheek on red fur), the mask floods the whole face. That was tested and failed.

## Palette

```bash
scripts/extract-palette.sh ref.png 8     # dominant colours by k-means (the background shows as its own cluster)
scripts/sample.sh ref.png X Y 9          # mean of a 9×9 box: exact hex for one feature
magick ref.png -crop 300x200+40+60 +repage crop.png   # make a single-attribute ref from a good render
```

Sample the hex from the **same art style** you're generating. The same colour measures very differently across styles: a flat peach swatch was `#F1956C`, and the same cheek on plush fur `#D17A53`. Shading and texture shift the sampled hex.

## Colour drift check

`scripts/palette-check.sh img --crop WxH+X+Y 5 "#HEX:name"` reports the share of subject pixels near the colour (pass `BG` if the background isn't white). Always crop to the feature's region, and compare with the same crop of the approved reference:

| Worked example (mascot sheet, head row) | Peach share |
|---|---|
| Old sheet, rosy cheeks | 1.20% |
| Corrected sheet, peach cheeks | 3.53% |
| Whole image, no crop (old vs new) | 2.12% vs 2.66%: similar orange elsewhere hides the signal |

## Review boards

```bash
scripts/contact-sheet.sh board.png sheet-front-crop.png a.png b.png c.png   # one row, same height, labelled
scripts/fringe-check.sh cut.png halo.png "#brandhex"                         # dark | brand (default grey) | white
magick montage -label '%t' gen/v3/*.png -geometry 300x300+8+8 -tile 4x grid.png   # every raw at once
```

## Composite a real logo (products)

The generator leaves a blank logo area. Then place the real asset at a fixed position and size:

```bash
magick product.png \( logo.png -resize 180x \) -gravity northwest -geometry +412+530 -composite out.png
# on a curved surface, bend it slightly first:
magick logo.png -resize 180x -virtual-pixel transparent -distort Barrel "0 0 -0.08 1.08" logo-curved.png
```

## Normalise a series to one canvas (icons, stickers, product grids)

Every image gets the same canvas size and margin, so a series lines up in a grid:

```bash
magick cut.png -trim +repage -resize 880x880 -background none -gravity center -extent 1024x1024 norm.png
```

Here 880 inside 1024 gives a ~7% margin. Use the same numbers for every image in the series.

## Export

```bash
scripts/export-webp.sh cut.png out.webp 1200   # cwebp -q 86 -alpha_q 100 -exact
```

`-exact` keeps the RGB under transparent pixels. Without it, cwebp may alter that colour, which can show as dark edges when the image is scaled. Check the result: `magick out.webp -format '%wx%h %[channels]\n' info:` should report `srgba`.
