#!/bin/bash
# Line up the reference sheet crop and every render at the same height for a side-by-side consistency review.
# usage: contact-sheet.sh out.png img1 img2 ...   (transparent cutouts are flattened onto mid grey)
set -euo pipefail
out=$1; shift
magick montage -label '%t' -pointsize 22 "$@" -background '#9a9a9a' -geometry x600+16+16 -tile x1 "$out"
echo "$out"
