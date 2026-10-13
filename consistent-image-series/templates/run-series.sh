#!/bin/bash
# Run a whole series from a briefs file, 2 at a time. Resumable: existing outputs are skipped, so rerun after a failure.
# Stops cleanly (exit 3) when the generator reports a quota/rate limit, so nothing is wasted on doomed calls.
# usage: SERIES=series.env run-series.sh briefs.txt outdir
#   briefs.txt: one "name|brief" per line (# comments allowed)
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd); briefs=$1; out=$2; mkdir -p "$out"
quota() { grep -qiE '429|RESOURCE_EXHAUSTED|quota|usage limit|rate limit' "$1"; }
pids=()
while IFS='|' read -r name brief; do
  [[ -z "$name" || $name == \#* ]] && continue
  [ -f "$out/$name.png" ] && continue
  "$here/gen.sh" "$out/$name.png" "$brief" > "$out/$name.log" 2>&1 & pids+=($!)
  if [ ${#pids[@]} -ge 2 ]; then wait "${pids[@]}"; pids=()
    for l in "$out"/*.log; do quota "$l" && [ ! -f "${l%.log}.png" ] && { echo "quota hit ($l); rerun later to resume"; exit 3; }; done
  fi
done < "$briefs"
wait
for l in "$out"/*.log; do quota "$l" && [ ! -f "${l%.log}.png" ] && { echo "quota hit ($l); rerun later to resume"; exit 3; }; done
missing=$(grep -vE '^\s*(#|$)' "$briefs" | cut -d'|' -f1 | while read -r n; do [ -f "$out/$n.png" ] || echo "$n"; done)
[ -z "$missing" ] && echo "series complete" || { echo "missing: $missing (see logs; rerun to retry)"; exit 2; }
