#!/bin/bash
# Dominant colours of a reference via k-means. The background shows up as its own cluster; ignore it.
# usage: extract-palette.sh ref.png [k=8]
set -euo pipefail
magick "$1" -background white -alpha remove -alpha off -resize 400x400\> -kmeans "${2:-8}" \
  -format %c histogram:info:- | sort -rn | awk '{print $1, $3}'
