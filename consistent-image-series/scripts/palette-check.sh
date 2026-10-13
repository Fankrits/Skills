#!/bin/bash
# Share of the SUBJECT (non-background pixels) within fuzz of each colour. A cheap pre-filter for colour drift.
# Crop to the feature's region (e.g. the face) when its colour also appears elsewhere (a red logo vs a red strap, cheeks vs spikes),
# and compare against the same crop of the approved reference: absolute numbers depend on framing.
# usage: [BG="#808080"] palette-check.sh img.png [--crop WxH+X+Y] [fuzz%=4] "#E4572E:accent" ...
set -euo pipefail
f=$1; shift; bg=${BG:-white}
crop=(); fuzz=4
[[ ${1:-} == --crop ]] && { crop=(-crop "$2" +repage); shift 2; }
[[ ${1:-} =~ ^[0-9.]+$ ]] && { fuzz=$1; shift; }
base=(magick "$f" -background "$bg" -alpha remove -alpha off ${crop[@]+"${crop[@]}"})
subj=$("${base[@]}" \( +clone -fill "$bg" -colorize 100 \) -compose Difference -composite \
  -separate -evaluate-sequence Max -threshold 8% -format '%[fx:mean]' info:)
for spec in "$@"; do
  hex=${spec%%:*}; name=${spec#*:}
  v=$("${base[@]}" -fuzz "$fuzz%" -fill black +opaque "$hex" -fill white -opaque "$hex" -format '%[fx:mean]' info:)
  awk -v n="$name" -v h="$hex" -v v="$v" -v s="$subj" 'BEGIN{printf "%-16s %s %6.2f%% of subject\n", n, h, (s>0?100*v/s:0)}'
done
