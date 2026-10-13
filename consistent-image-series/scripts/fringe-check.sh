#!/bin/bash
# Composite a cutout onto dark, brand and white grounds side by side. White halos show on dark; dark halos on white.
# usage: fringe-check.sh cutout.png out.png ["#brandhex"=#808080]
set -euo pipefail
in=$1; out=$2; brand=${3:-#808080}
magick \( "$in" -background '#121212' -flatten \) \( "$in" -background "$brand" -flatten \) \
  \( "$in" -background white -flatten \) +append -resize 1800x\> "$out"
echo "$out"
