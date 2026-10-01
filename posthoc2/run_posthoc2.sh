#!/bin/sh
# run_posthoc2.sh — N1: the real-data stages of items C, D and E (declared in the post-freeze record "items C, D and E
# declared before they are computed"), in the declared order. Run from the analysis root; every stage appends its UTC
# start, end, elapsed seconds and exit code to posthoc2/times.log. A stage that fails stops the chain.
#   sh posthoc2/run_posthoc2.sh DE    verify, reproduce, D, E, E-summary
#   sh posthoc2/run_posthoc2.sh C     C (main phase), C-checks (check (a) phase), C-summary
set -u
REG=../registration/prereg.md
TMP=${N1_TMP:-/tmp/n1posthoc2}
PY=${N1_PY:-n1python}
OUT=posthoc2
stage() {
  name=$1; shift
  s=$(date -u +%s); st=$(date -u +%H:%M:%S)
  "$PY" posthoc2/n1_posthoc2.py "$@" --root . --code-dir . --tmp "$TMP/$name" --registration "$REG" > "$OUT/run.$name.log" 2>&1
  rc=$?
  e=$(date -u +%s)
  echo "$name rc=$rc start=$(date -u -d @$s +%Y-%m-%dT%H:%M:%SZ) end=$(date -u -d @$e +%Y-%m-%dT%H:%M:%SZ) elapsed=$((e - s))" >> "$OUT/times.log"
  [ $rc -eq 0 ] || { echo "STOPPED at $name" >> "$OUT/times.log"; exit $rc; }
}
case "${1:-}" in
  DE)
    stage verify verify --out "$OUT/VERIFY.json"
    stage reproduce reproduce --out "$OUT/REPRODUCE.json"
    stage D D --out "$OUT"
    stage E E --out "$OUT"
    stage E-summary E-summary --out "$OUT"
    echo "DE DONE" >> "$OUT/times.log" ;;
  C)
    stage C C --out "$OUT"
    stage C-checks C-checks --out "$OUT"
    stage C-summary C-summary --out "$OUT"
    echo "C DONE" >> "$OUT/times.log" ;;
  *) echo "usage: sh posthoc2/run_posthoc2.sh DE|C"; exit 2 ;;
esac
