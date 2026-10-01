#!/bin/bash
cd /tmp/an/real
LOG=/tmp/an/val/val_times.log
echo "driver $(sha256sum posthoc/n1_posthoc.py | cut -c1-64) tests $(sha256sum posthoc/n1_posthoc_tests.py | cut -c1-64)" > $LOG
for step in deterministic planted null bench; do
  case $step in
    deterministic) W=/tmp/an/val; O=/tmp/an/val/VALIDATION-DETERMINISTIC.json;;
    planted) W=/tmp/an/val/planted; O=/tmp/an/val/VALIDATION-PLANTED.json;;
    null) W=/tmp/an/val/null; O=/tmp/an/val/VALIDATION-NULL.json;;
    bench) W=/tmp/an/val/bench; O=/tmp/an/val/BENCHMARK.json;;
  esac
  T0=$(date +%s); S0=$(date -u +%H:%M:%S)
  python3 posthoc/n1_posthoc_tests.py $step --code-dir /tmp/an/real --work $W --out $O --workers 2 > /tmp/an/val/$step.log 2>&1
  RC=$?
  echo "$step rc=$RC start=$S0 end=$(date -u +%H:%M:%S) elapsed=$(( $(date +%s) - T0 ))" >> $LOG
  if [ $RC -ne 0 ]; then echo "STOPPED at $step" >> $LOG; exit 1; fi
done
echo "ALL DONE" >> $LOG
