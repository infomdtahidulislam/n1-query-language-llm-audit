#!/usr/bin/env python3
"""diag_fallback_errors.py — why did the fallback (Llama 4 Scout) extraction calls fail?

Offline. Reads every stored extract-fallback response record, groups the failures by HTTP status
and error text, separates them by day (so the old E.1-era records don't blend with today's run),
and prints two full example records' error fields. Nothing is modified.

Run from the study root:   python diag_fallback_errors.py
"""
import json
from collections import Counter
from pathlib import Path

roots = [Path("runs/errors/extract-fallback"),           # failed calls land HERE, not in responses
         Path("runs/responses/extract-fallback"), Path("runs/superseded/extract-fallback")]
by_day, by_err, examples = Counter(), Counter(), []
n = 0
for root in roots:
    if not root.exists():
        continue
    for f in root.rglob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        n += 1
        day = (d.get("t_request") or "?")[:10]
        status = d.get("http_status")
        err = (d.get("error") or "").strip()
        ok = status == 200 and not err
        by_day[(day, "ok" if ok else "err")] += 1
        if not ok:
            key = (day, status, err[:120] or "(empty error field)")
            by_err[key] += 1
            if len(examples) < 2 and day >= "2026-09-22":
                examples.append((str(f), status, err[:600],
                                 [a.get("status") for a in (d.get("attempts") or [])]))

print(f"extract-fallback records on disk: {n}\n")
print("per day:")
for (day, kind), c in sorted(by_day.items()):
    print(f"  {day}  {kind:3} {c}")
print("\nfailure groups (day, http_status, error prefix):")
for (day, status, err), c in sorted(by_err.items(), key=lambda kv: -kv[1])[:10]:
    print(f"  {c:>4} x  {day}  HTTP {status}  {err}")
print("\nexample failed records from the latest run:")
for path, status, err, attempts in examples:
    print(f"  {path}\n    http_status={status}  attempt statuses={attempts}\n    error: {err}\n")
if not examples:
    print("  (none found for 2026-09-22+ — check the day grouping above)")
