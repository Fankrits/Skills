#!/bin/bash
# Edit pass: fix ONE drifted trait, keep everything else. Uses the same series.env (for ATTR_REFS).
# usage: [SERIES=series.env] edit.sh in.png out.png "<trait>" "<exact change, and where it applies>"
set -euo pipefail
cfg=${SERIES:-./series.env}; source "$cfg"; ATTR_REFS=${ATTR_REFS:-}
in=$1; out=$2; trait=$3; change=$4
prompt="Use your image generation tool to EDIT the image $in.${ATTR_REFS:+ Reference images for single attributes: $ATTR_REFS (use each ONLY for the attribute it shows).} Change ONLY the $trait: $change Keep everything else identical: pose, framing, expression, eyes, mouth and fang, all colours, background, props. Save the result to $out. Reply only with the saved path."
printf '%s\n' "$prompt" > "${out%.*}.prompt.txt"
agy -p "$prompt" --dangerously-skip-permissions --model gemini-3.8-flash-high --print-timeout 900s
[ -f "$out" ] || { echo "generator did not write $out" >&2; exit 2; }
