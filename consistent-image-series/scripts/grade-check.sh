#!/bin/bash
# Colour-grade drift for scene/photo series: mean Lab of each image vs the approved anchor, and the distance (ΔE76).
# Rough guide: ΔE < 3 same grade; 3–6 noticeable, look at it; > 6 a different grade (regenerate or colour-match).
# Cutout series (subject on a flat BG): pass BG="#FFFFFF" to average the subject only, or framing (how much BG shows) swamps the score.
# usage: [BG="#hex"] grade-check.sh anchor.png img1.png [img2.png ...]
set -euo pipefail
lab() { magick "$1" -alpha off ${BG:+-fuzz 8% -transparent "$BG"} -scale 64x64\! -scale 1x1\! -alpha off -colorspace Lab -format '%[fx:mean.r*100] %[fx:(mean.g-0.5)*255] %[fx:(mean.b-0.5)*255]' info:; }
read -r L0 a0 b0 <<<"$(lab "$1")"
printf '%-28s L=%5.1f a=%5.1f b=%5.1f  (anchor)\n' "$(basename "$1")" "$L0" "$a0" "$b0"
shift
for f in "$@"; do
  read -r L a b <<<"$(lab "$f")"
  awk -v n="$(basename "$f")" -v L="$L" -v a="$a" -v b="$b" -v L0="$L0" -v a0="$a0" -v b0="$b0" 'BEGIN{
    d=sqrt((L-L0)^2+(a-a0)^2+(b-b0)^2); printf "%-28s L=%5.1f a=%5.1f b=%5.1f  ΔE=%4.1f %s\n", n, L, a, b, d, (d<3?"same grade":(d<6?"check":"DRIFT"))}'
done
