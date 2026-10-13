#!/bin/bash
# Fit an image onto an exact output canvas: the one primitive behind most purpose exports.
# usage: fit.sh in out.ext WxH [contain|cover=contain] [bg=none] [margin%=0]
#   contain: whole subject visible, padded with bg (cutouts, products, icons, stickers)
#   cover:   fill the canvas, crop the overflow from the centre (scenes, photos, banners)
#   bg:      none (transparent) | white | "#hex"; formats without alpha (jpg) get white if none
set -euo pipefail
in=$1; out=$2; size=$3; mode=${4:-contain}; bg=${5:-none}; margin=${6:-0}
W=${size%x*}; H=${size#*x}
case "${out##*.}" in jpg|jpeg) [ "$bg" = none ] && bg=white ;; esac
if [ "$mode" = cover ]; then
  magick "$in" -resize "${W}x${H}^" -gravity center -extent "${W}x${H}" -background "$bg" -flatten "$out"
else
  iw=$(awk -v w="$W" -v m="$margin" 'BEGIN{printf "%d", w*(1-2*m/100)}')
  ih=$(awk -v h="$H" -v m="$margin" 'BEGIN{printf "%d", h*(1-2*m/100)}')
  magick "$in" -trim +repage -resize "${iw}x${ih}" -background "$bg" -gravity center -extent "${W}x${H}" "$out"
fi
echo "$out $(magick "$out" -format '%wx%h' info:)"
