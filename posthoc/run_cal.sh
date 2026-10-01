#!/bin/bash
# item 5 of the post-hoc declaration (record 53): calibration on null data sets made from the real data
cd /tmp/an/real
LOG=/tmp/an/real/posthoc/cal_times.log
REG=/tmp/an/real/prereg.md
echo "driver $(sha256sum posthoc/n1_posthoc.py | cut -c1-64) registration $(md5sum $REG | cut -c1-32)" >> $LOG
for spec in "human i 1000 200" "human ii 1000 0" "corpus i 1000 200" "corpus ii 1000 0"; do
  set -- $spec
  T0=$(date +%s); S0=$(date -u +%H:%M:%S)
  python3 posthoc/n1_posthoc.py calibrate --root /tmp/an/real --code-dir /tmp/an/real --tmp /tmp/an/real/posthoc/tmp/cal_$1_$2 \
      --registration $REG --out /tmp/an/real/posthoc/CALIBRATION-$1-$2.jsonl --layer $1 --scenario $2 --n $3 --n-rand $4 \
      --workers 2 --stream cal >> /tmp/an/real/posthoc/cal_$1_$2.log 2>&1
  RC=$?
  echo "$1|$2 rc=$RC start=$S0 end=$(date -u +%H:%M:%S) elapsed=$(( $(date +%s) - T0 ))" >> $LOG
  if [ $RC -ne 0 ]; then echo "STOPPED at $1|$2" >> $LOG; exit 1; fi
done
T0=$(date +%s); S0=$(date -u +%H:%M:%S)
python3 posthoc/n1_posthoc.py summarize --code-dir /tmp/an/real --inputs posthoc/CALIBRATION-human-i.jsonl posthoc/CALIBRATION-human-ii.jsonl \
    posthoc/CALIBRATION-corpus-i.jsonl posthoc/CALIBRATION-corpus-ii.jsonl --out posthoc/CALIBRATION-SUMMARY >> /tmp/an/real/posthoc/cal_summary.log 2>&1
RC=$?
echo "summary rc=$RC start=$S0 end=$(date -u +%H:%M:%S) elapsed=$(( $(date +%s) - T0 ))" >> $LOG
[ $RC -eq 0 ] && echo "ALL DONE" >> $LOG
