#!/bin/bash
# Transparent cutout of a subject rendered on a FLAT background colour (default white).
# usage: [BG="#808080"] cutout.sh in.png out.png [fuzz%=8] [hole_area=1500]
#  White or very pale subjects (white sneakers, a white mug, a cream product): generate on a flat colour the subject
#  doesn't contain (mid grey #808080, or chroma green #00B140 for hair-free subjects) and pass BG.
#  1) flood-fill the background from the border (keeps BG-coloured details INSIDE the subject)
#  2) clear enclosed background pockets larger than hole_area px (gaps between an arm/handle and the body)
#  3) erode 1.5px + blur 0.8 on the alpha to remove the edge halo, then trim
set -euo pipefail
in=$1; out=$2; fuzz=${3:-8}; area=${4:-1500}; bg=${BG:-white}
t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
magick "$in" -bordercolor "$bg" -border 2 -alpha set -fuzz "$fuzz%" -fill none \
  -draw "color 0,0 floodfill" -shave 2x2 "$t/a.png"
magick "$t/a.png" -alpha off -fuzz 3% -fill black +opaque "$bg" -fill white -opaque "$bg" "$t/w.png"
magick "$t/w.png" -define connected-components:area-threshold="$area" \
  -define connected-components:mean-color=true -connected-components 8 -threshold 50% "$t/holes.png"
magick "$t/a.png" -alpha extract "$t/al.png"
magick "$t/al.png" \( "$t/holes.png" -negate \) -compose Multiply -composite \
  -morphology Erode Disk:1.5 -blur 0x0.8 "$t/al2.png"
magick "$in" "$t/al2.png" -alpha off -compose CopyOpacity -composite -trim +repage "$out"
echo "$out $(magick "$out" -format '%wx%h' info:)"
