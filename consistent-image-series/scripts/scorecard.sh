#!/bin/bash
# Consistency scorecard: turns per-image trait judgements into pass rates, so drift is a number, not a feeling.
# scorecard.csv: header "image,<trait>,<trait>,...[,notes]"; one row per image; cells 1 = on-model, 0 = drift, - = not visible.
# Fill it by looking at each image next to the reference (the guide's checklist = the trait columns).
# usage: scorecard.sh scorecard.csv
#   trait pass rate   how reliable each trait is across the series (the weakest trait is what to fix in the prompt)
#   image pass rate   which images need an edit pass
#   series score      passes / judged cells. Targets: >= 85% first pass, >= 95% after fixes, 100% for anything shipped
set -euo pipefail
awk -F, '
NR==1 { for(i=2;i<=NF;i++){ if(tolower($i)=="notes"){ nc=i; continue } T[i]=$i; ord[++n]=i } next }
{ img=$1; ip=0; ij=0
  for(k=1;k<=n;k++){ i=ord[k]; v=$i; gsub(/ /,"",v)
    if(v=="1"){ P[i]++; J[i]++; ip++; ij++ } else if(v=="0"){ J[i]++; ij++; F[img]=F[img] " " T[i] } }
  imgs[++m]=img; IP[img]=ip; IJ[img]=ij; tp+=ip; tj+=ij }
END{
  print "TRAITS (pass rate across the series)"
  for(k=1;k<=n;k++){ i=ord[k]; r=(J[i]?100*P[i]/J[i]:0); printf "  %-18s %5.1f%%  (%d/%d)%s\n", T[i], r, P[i], J[i], (r<90?"  <- weakest: strengthen prompt / add attribute ref":"") }
  print "IMAGES"
  for(j=1;j<=m;j++){ g=imgs[j]; r=(IJ[g]?100*IP[g]/IJ[g]:0); printf "  %-18s %5.1f%%%s\n", g, r, (F[g]!=""?"  drift:" F[g]:"") }
  s=(tj?100*tp/tj:0); printf "SERIES SCORE %.1f%% (%d/%d judged)  %s\n", s, tp, tj, (s>=95?"consistent":(s>=85?"fix the drift rows":"rework the guide/prompt before generating more")) }' "$1"
