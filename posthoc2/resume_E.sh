#!/bin/sh
# resume of run_posthoc2.sh DE after a worker restart: the same stage commands as the declared script, for E and E-summary
set -u
REG=../registration/prereg.md
TMP=${N1_TMP:-/tmp/n1posthoc2}
PY=${N1_PY:-n1python}
OUT=posthoc2
stage() {
  name=$1; shift
  s=$(date -u +%s)
  "$PY" posthoc2/n1_posthoc2.py "$@" --root . --code-dir . --tmp "$TMP/$name" --registration "$REG" > "$OUT/run.$name.log" 2>&1
  rc=$?
  e=$(date -u +%s)
  echo "$name rc=$rc start=$(date -u -d @$s +%Y-%m-%dT%H:%M:%SZ) end=$(date -u -d @$e +%Y-%m-%dT%H:%M:%SZ) elapsed=$((e - s))" >> "$OUT/times.log"
  [ $rc -eq 0 ] || { echo "STOPPED at $name" >> "$OUT/times.log"; exit $rc; }
}
stage E E --out "$OUT"
stage E-summary E-summary --out "$OUT"
echo "DE DONE" >> "$OUT/times.log"
