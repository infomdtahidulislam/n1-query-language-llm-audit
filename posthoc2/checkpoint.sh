#!/bin/sh
# checkpoint.sh — N1: commit and push the partial outputs of a long post-hoc computation every INTERVAL seconds (default
# 1500), so that a reclaimed machine can resume from the branch. Adds only files under analysis/posthoc2/. Stops when
# the file posthoc2/STOP-CHECKPOINTS exists. Run from the repository root:  sh analysis/posthoc2/checkpoint.sh BRANCH
# Release copy: the copy that ran (sha256 0ad91c7a34d24f950edf459693907b4caaa74b75b293aefe7167f0b11bd806c0, quoted in
# the registration) also added two trailer lines to each commit message; they are left out here. No result uses this file.
set -u
BR=$1
INTERVAL=${INTERVAL:-1500}
while [ ! -e analysis/posthoc2/STOP-CHECKPOINTS ]; do
  sleep "$INTERVAL"
  git add analysis/posthoc2 >/dev/null 2>&1
  if ! git diff --cached --quiet; then
    git commit -q -m "posthoc2: checkpoint of partial outputs $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    for d in 2 4 8 16; do git push -q -u origin "$BR" && break; sleep $d; done
    echo "checkpoint $(date -u +%Y-%m-%dT%H:%M:%SZ) $(git rev-parse --short HEAD)" >> analysis/posthoc2/checkpoints.log
  fi
done
