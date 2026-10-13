#!/bin/bash
# Generator wrapper: fixed identity/style block + per-image brief, so every call carries the same anchor.
# usage: [SERIES=path/series.env] gen.sh out.png "<brief>"
# series.env (one per series, next to its guide; see templates/series.env):
#   REFS        approved sheet / style board / anchor image(s), space-separated; EMPTY for the very first anchor
#   ATTR_REFS   single-attribute refs for traits that drift (optional)
#   IDENTITY    the guide's identity/style block, verbatim
#   BACKGROUND  the background rule (flat white / flat grey for pale subjects / the scene rule)
set -euo pipefail
cfg=${SERIES:-./series.env}; [ -f "$cfg" ] || { echo "missing $cfg (copy templates/series.env)" >&2; exit 1; }
# shellcheck disable=SC1090
source "$cfg"
REFS=${REFS:-}; ATTR_REFS=${ATTR_REFS:-}
: "${IDENTITY:?set IDENTITY in $cfg}" "${BACKGROUND:?set BACKGROUND in $cfg}"
out=$1; brief=$2; mkdir -p "$(dirname "$out")"
if [ -n "$REFS" ]; then
  refs="Reference images: $REFS (the approved reference; match its subject and style exactly)${ATTR_REFS:+, and $ATTR_REFS (use ONLY for the attribute each one shows)}. "
else
  refs="No reference yet: this image becomes the anchor for the series, so follow the description precisely. "
fi
prompt="Use your image generation tool. ${refs}Must match: $IDENTITY Do not redesign, restyle or add elements beyond the brief. No text, no logos, no watermark unless the brief asks. Background: $BACKGROUND Brief: $brief Save the file to $out. Reply only with the saved path."
printf '%s\n' "$prompt" > "${out%.*}.prompt.txt"   # provenance, written first so it survives a failed run
# agy (Antigravity CLI) shown; swap this line for any generator that accepts reference images.
agy -p "$prompt" --dangerously-skip-permissions --model gemini-3.8-flash-high --print-timeout 900s
[ -f "$out" ] || { echo "generator did not write $out" >&2; exit 2; }
