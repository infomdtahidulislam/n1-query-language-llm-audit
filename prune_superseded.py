#!/usr/bin/env python3
"""prune_superseded.py — move cached responses that were produced under superseded sampling
parameters out of the live cache, into runs/superseded/, preserving them as evidence.

Why this is needed. Every cached record stores the exact `params` it was called with, and the cache
key includes them, so when a per-model parameter changes the old records do not disappear — they sit
beside the new ones and `code` reads BOTH. That is what turned a 480-answer smoke phase into 560.

What it does. For every record in a phase it compares the record's own `params` against what
models.json specifies for that model TODAY. Anything that does not match is superseded and is moved
(never deleted) to runs/superseded/<phase>/<model>/, so the numbers it produced stay auditable —
prereg v0.30 cites them as the M3 evidence for raising DeepSeek's max_tokens.

Usage:
  python prune_superseded.py --phase smoke              # report only, moves nothing
  python prune_superseded.py --phase smoke --apply      # actually move them
"""
import argparse, json, shutil, sys
from pathlib import Path
import importlib.util

ap = argparse.ArgumentParser()
ap.add_argument("--phase", default="smoke")
ap.add_argument("--runs", default="runs")
ap.add_argument("--models", default="models.json")
ap.add_argument("--apply", action="store_true")
a = ap.parse_args()

spec = importlib.util.spec_from_file_location("n1", "n1_pipeline.py")
n1 = importlib.util.module_from_spec(spec)
sys.argv = ["n1_pipeline.py", "--help"]
try:
    spec.loader.exec_module(n1)
except SystemExit:
    pass

cfg = n1.Config(Path(a.models))
want = {s["id"]: cfg.subject_params(s) for s in cfg.subjects}
for role in ("primary", "cross_check", "fallback"):
    try:
        want[cfg.extractor(role)["id"]] = cfg.extractor_params()
    except SystemExit:
        pass

root = Path(a.runs) / "responses" / a.phase
if not root.exists():
    sys.exit(f"{root} not found — run from the project folder")
keep, move, unknown = [], [], []
for p in sorted(root.rglob("*.json")):
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        unknown.append((p, f"unreadable: {e}")); continue
    mid = (rec.get("spec") or {}).get("model_id")
    got = rec.get("params")
    if mid not in want:
        unknown.append((p, f"model {mid!r} is not in models.json")); continue
    (keep if got == want[mid] else move).append((p, mid, got, want[mid]))

print(f"phase '{a.phase}': {len(keep)+len(move)+len(unknown)} cached records")
print(f"  current parameters : {len(keep)}")
print(f"  SUPERSEDED         : {len(move)}")
if unknown:
    print(f"  unclassified       : {len(unknown)}")
    for p, why in unknown[:5]: print(f"      {p.name}  {why}")
seen = {}
for p, mid, got, wanted in move:
    seen.setdefault((mid, json.dumps(got, sort_keys=True), json.dumps(wanted, sort_keys=True)), 0)
    seen[(mid, json.dumps(got, sort_keys=True), json.dumps(wanted, sort_keys=True))] += 1
for (mid, got, wanted), n in seen.items():
    print(f"      {n:>4} × {mid}: called with {got}, models.json now says {wanted}")

if not move:
    print("\nnothing to move — the cache matches models.json.")
    sys.exit(0)
dest_root = Path(a.runs) / "superseded" / a.phase
if not a.apply:
    print(f"\nDRY RUN — nothing moved. Re-run with --apply to move {len(move)} record(s) to {dest_root}/")
    sys.exit(0)
for p, mid, _, _ in move:
    dest = dest_root / p.parent.name
    dest.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), str(dest / p.name))
print(f"\nmoved {len(move)} record(s) to {dest_root}/  (kept, not deleted — they are the M3 evidence)")
print("now re-run:  python n1_pipeline.py code --phase smoke")
