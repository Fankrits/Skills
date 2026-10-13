# Output by Purpose

Generate once at high resolution (1024–2048 px on a flat background, or a full scene), approve it, then derive every deliverable with magick. Don't regenerate per size: each extra generation is another chance to drift.

`scripts/fit.sh in out WxH [contain|cover] [bg] [margin%]` covers most rows:
- `contain` fits the whole subject inside the canvas and pads the rest (cutouts, products, icons).
- `cover` fills the canvas and crops from the centre (scenes, banners).

Every command below was run once on test images.

| Purpose | Spec | Command |
|---|---|---|
| Web/UI image | WebP or AVIF, keep alpha, 2–3 widths for `srcset` | `for w in 480 960 1440; do magick cut.png -resize ${w}x img-$w.webp; done` · `magick cut.png -resize 960x -quality 60 img.avif` |
| Web, exact alpha | lossless alpha | `scripts/export-webp.sh cut.png img.webp 1200` |
| E-commerce product tile | square, white or transparent, the same margin across the catalogue | `fit.sh cut.png tile.png 2000x2000 contain none 6` (white: `… contain white 6` → `.jpg`) |
| Open Graph / link preview | 1200×630 JPG; keep text and subject in the centre | `fit.sh cut.png og.jpg 1200x630 contain "#brand" 8` |
| Social post / portrait / story | 1080×1080, 1080×1350, 1080×1920 | scene: `fit.sh scene.png story.jpg 1080x1920 cover` · subject: `… contain "#brand" 10` |
| Banner / header | for example, 1500×500 or 1920×600 | `fit.sh scene.png banner.jpg 1920x600 cover`. **Generate scenes at the target aspect ratio** (state it in the brief), or the cover crop cuts the subject |
| Favicon | `.ico` at 16/32/48, plus a 180px apple-touch icon | `fit.sh cut.png icon.png 1024x1024 contain none 10` → `magick icon.png -define icon:auto-resize=16,32,48 favicon.ico` · `magick icon.png -resize 180x180 apple-touch-icon.png` |
| iOS app icon | 1024×1024, **no alpha** (the App Store rejects transparency), square corners (iOS rounds them) | `magick icon.png -background white -alpha remove -alpha off ios-1024.png` |
| Android adaptive icon | 432×432 foreground; keep the subject inside the central 66% safe zone | `fit.sh cut.png fg.png 432x432 contain none 17` |
| Sticker / die-cut | white outline around the alpha | `magick cut.png -bordercolor none -border 40 \( +clone -alpha extract -morphology Dilate Disk:24 -background white -alpha shape \) +swap -compose Over -composite -trim +repage sticker.png` |
| Print (poster, card, packaging) | 300 DPI; size + 3 mm bleed on each side; CMYK TIFF | px = (mm + 6) / 25.4 × 300 → `fit.sh … WxH contain white 12` → `magick in.png -units PixelsPerInch -density 300 -colorspace CMYK -compress lzw print.tif`. For colour-critical print, convert with the printer's ICC profile (`-profile sRGB.icc -profile printer.icc`) instead of a plain `-colorspace` |
| Print-on-demand (T-shirt, tote) | transparent PNG, often 4500×5400 at 300 DPI | `fit.sh cut.png pod.png 4500x5400 contain none 5` → `magick pod.png -units PixelsPerInch -density 300 pod.png`. PNG stores this per centimetre, so identify shows it as 118.11 PixelsPerCentimeter, which equals 300 DPI. Upscaling past the source resolution softens the image, so generate at the highest resolution available |
| Email | JPG/PNG, 600 or 1200 px wide (2×), under ~1 MB | `magick cut.png -background white -alpha remove -resize 1200x -quality 82 email.jpg` |
| Animation / reaction | animated WebP or GIF from frames | `magick -delay 12 -loop 0 -dispose Background f1.png f2.png f3.png -background none anim.webp` (the same frames → `anim.gif`) |
| Game / UI sprite sheet | frames side by side, one cell size | normalise every frame (`fit.sh … 340x400 contain none 0`), then `magick f*.png +append sprite.png` (`-append` stacks them vertically) |
| Slide / presentation | 1920×1080, PNG with alpha for subjects | `fit.sh cut.png slide-art.png 1920x1080 contain none 10` |
| Pattern / texture tile | seamless | Ask for a "seamless tileable texture". Check it with `magick tile.png -roll +50%+50% check.png`: any seam shows as a cross in the middle |

## Rules that hold for every purpose

- **One master per image.** Keep the approved raw image and the cutout. Every deliverable is derived from them, and you never edit a derived file.
- **One margin per series.** The same `fit.sh` margin for every image in a catalogue, icon set or sticker pack. Otherwise the series looks inconsistent even when the images are on-model.
- **Text goes in the layout, not in the generation.** Add headlines in HTML, Figma or slides, or as a magick overlay with a real font: `magick in.png -font /path/to/Brand-Bold.ttf -pointsize 72 -fill white -gravity south -annotate +0+60 'Headline' out.png`. Pass the brand font as a file path; `magick -list font` shows the installed names.
- **Check every deliverable at its real size.** A 16 px favicon has to read at 16 px. Simplify the subject (a face mark instead of the full body) if it doesn't.
