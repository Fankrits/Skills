#!/bin/bash
# Cutout PNG -> web-ready WebP that keeps exact alpha. Optional max width.
# usage: export-webp.sh cutout.png out.webp [maxwidth]
set -euo pipefail
in=$1; out=$2; src=$in
if [ -n "${3:-}" ]; then src=$(mktemp -t ex).png; trap 'rm -f "$src"' EXIT; magick "$in" -resize "${3}x>" "$src"; fi
cwebp -quiet -q 86 -alpha_q 100 -exact "$src" -o "$out"
echo "$out $(magick "$out" -format '%wx%h' info:) $(du -h "$out" | cut -f1)"
