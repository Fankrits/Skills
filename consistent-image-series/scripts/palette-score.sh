#!/bin/bash
# Palette signature of a series vs its anchor. Every subject pixel is snapped to the nearest guide colour.
#   off-palette  share of subject pixels far (>15%) from every guide colour: new colours = added props/accessories/drift
#   similarity   100 − total-variation distance between the image's and the anchor's colour mix (100 = identical mix)
#   biggest Δ    the guide colours whose share moved most (e.g. "cheek -2.1" = cheeks shrank or changed colour)
# Pose and framing legitimately move the mix (a back view shows more spikes), so read similarity against the
# series' own spread: the outlier is the drift. Off-palette that the brief's prop doesn't explain is drift.
# usage: [BG="#FFFFFF"] palette-score.sh palette.txt anchor.png img1.png ...
#   palette.txt: one "#HEX name" per line (the guide's palette; include eyes, highlights, every recurring part)
set -euo pipefail
pal=$1; shift; bg=${BG:-#FFFFFF}; t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
args=(); while read -r hex name; do [[ -z "${hex// }" || $hex == \#* && -z $name ]] && continue; args+=("xc:$hex"); done < <(grep -E '^#[0-9A-Fa-f]{6}' "$pal")
magick "${args[@]}" "xc:$bg" +append "$t/pal.png"
sig() { # -> "<hex> <fraction>" lines over subject pixels, plus "OFF <fraction>"
  local f=$1 k=$2
  magick "$f" -background "$bg" -alpha remove -alpha off -resize 256x256\> "$t/$k-src.png"
  magick "$t/$k-src.png" \( +clone -fill "$bg" -colorize 100 \) -compose Difference -composite \
    -separate -evaluate-sequence Max -threshold 8% "$t/$k-mask.png"
  magick "$t/$k-src.png" +dither -remap "$t/pal.png" "$t/$k-map.png"
  local subj off
  subj=$(magick "$t/$k-mask.png" -format '%[fx:mean]' info:)
  off=$(magick "$t/$k-src.png" "$t/$k-map.png" -compose Difference -composite -separate -evaluate-sequence Max \
        -threshold 15% "$t/$k-mask.png" -compose Multiply -composite -format '%[fx:mean]' info:)
  echo "OFF $(awk -v o="$off" -v s="$subj" 'BEGIN{print (s>0?o/s:0)}')"
  magick "$t/$k-map.png" "$t/$k-mask.png" -alpha off -compose CopyOpacity -composite \
    -format %c histogram:info:- | awk -v s="$subj" '{
      n=$1; sub(":","",n); hex=""; for(i=1;i<=NF;i++) if($i ~ /^#[0-9A-Fa-f]{8}$/) hex=$i;
      if (hex=="" || substr(hex,8,2)=="00") next; tot+=n; c[substr(hex,1,7)]+=n }
      END{ for(h in c) print h, c[h]/tot }'
}
grep -E '^#[0-9A-Fa-f]{6}' "$pal" | awk '{print toupper($1), $2}' > "$t/names"
sig "$1" a > "$t/a.sig"
printf '%-22s %9s %11s  %s\n' image off-palette similarity "biggest Δ (share points vs anchor)"
for f in "$@"; do
  sig "$f" b > "$t/b.sig"
  awk -v img="$(basename "$f")" -v NF1="$t/names" -v AF="$t/a.sig" '
    FILENAME==NF1 { nm[$1]=$2; next }
    FILENAME==AF  { if($1=="OFF") next; A[toupper($1)]=$2; keys[toupper($1)]=1; next }
    { if($1=="OFF"){ off=$2; next } B[toupper($1)]=$2; keys[toupper($1)]=1 }
    END{ tv=0; m=0
      for(k in keys){ d=B[k]-A[k]; tv+=(d<0?-d:d); if(k in nm){ D[++m]=d; K[m]=nm[k] } }
      for(i=1;i<=m;i++) for(j=i+1;j<=m;j++) if((D[j]<0?-D[j]:D[j])>(D[i]<0?-D[i]:D[i])){ x=D[i];D[i]=D[j];D[j]=x; y=K[i];K[i]=K[j];K[j]=y }
      top=""; for(i=1;i<=3&&i<=m;i++) top=top sprintf("%s %+.1f  ", K[i], D[i]*100)
      printf "%-22s %8.1f%% %10.1f%%  %s\n", img, off*100, 100-tv*50, top }' "$t/names" "$t/a.sig" "$t/b.sig"
done
