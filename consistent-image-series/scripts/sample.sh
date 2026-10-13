#!/bin/bash
# Mean colour of a small box: exact hex for one feature (a cheek, a logo, a fabric) at a known spot.
# usage: sample.sh img.png X Y [size=9]
set -euo pipefail
s=${4:-9}; x=$(( $2 - s/2 )); y=$(( $3 - s/2 ))
magick "$1" -alpha off -crop "${s}x${s}+${x}+${y}" +repage -scale 1x1\! -format '#%[hex:p{0,0}]\n' info:
