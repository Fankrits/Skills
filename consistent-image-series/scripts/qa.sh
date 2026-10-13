#!/bin/bash
# Objective checks on a raw generation (before cutout).
# usage: [BG="#808080"] qa.sh raw.png   (BG = the flat background colour the image was generated on; default white)
# Reports: size, background purity (corners), whether the subject touches an edge, subject coverage.
set -euo pipefail
f=$1; bg=${BG:-white}
w=$(magick "$f" -format '%w' info:); h=$(magick "$f" -format '%h' info:)
echo "size: ${w}x${h}"
for p in "0,0" "$((w-1)),0" "0,$((h-1))" "$((w-1)),$((h-1))"; do
  printf 'corner %-12s %s\n' "$p" "$(magick "$f" -format "%[hex:p{$p}]" info:)"
done
# mask: subject=white, background(near BG)=black
m=$(mktemp -t qa).png; trap 'rm -f "$m"' EXIT
magick "$f" -alpha off \( +clone -fill "$bg" -colorize 100 \) -compose Difference -composite \
  -separate -evaluate-sequence Max -threshold 8% "$m"   # max channel distance from BG > 8% = subject
for side in top bottom left right; do
  case $side in
    top)    g="${w}x2+0+0" ;;          bottom) g="${w}x2+0+$((h-2))" ;;
    left)   g="2x${h}+0+0" ;;          right)  g="2x${h}+$((w-2))+0" ;;
  esac
  v=$(magick "$m" -crop "$g" +repage -format '%[fx:mean*100]' info:)
  awk -v s="$side" -v v="$v" 'BEGIN{printf "edge %-6s %5.2f%% subject %s\n", s, v, (v>0.5?"<- TOUCHES":"ok")}'
done
magick "$m" -format 'subject coverage: %[fx:mean*100]%%\n' info:
magick "$m" -trim -format 'subject bbox: %wx%h%O\n' info:
