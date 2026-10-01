#!/usr/bin/env python3
"""retire_contest_schema_fail.py — E.1 retry mechanics for the G.2 contest extractors.

Reads runs/extracted/pilot.{cross_check,fallback}.jsonl, finds rows whose extraction failed schema
validation, and RETIRES each one's response record to runs/superseded/ (never deleted), so the next
`extract` run re-calls exactly those answers. Per E.1 an answer may be re-called at most twice: a
third schema failure for the same answer is reported and left alone (it is then excluded from
extractor-derived analyses and reported, mirroring D.6).

Run from the study folder:  python retire_contest_schema_fail.py
Then re-run the extract command(s); only the retired answers (and any 429-errored answers, which
were never cached as successes) will call live.
"""
import json, shutil, sys
from pathlib import Path

RUNS = Path("runs")
ROLES = {"cross_check": "meta_muse-glimmer-30b", "fallback": "meta-llama_llama-4-scout"}

total = 0
for role, mdir in ROLES.items():
    ex_p = RUNS / "extracted" / f"pilot.{role}.jsonl"
    if not ex_p.exists():
        continue
    rows = [json.loads(l) for l in open(ex_p, encoding="utf-8") if l.strip()]
    bad = [r for r in rows if r.get("schema_errors")]
    if not bad:
        print(f"[{role}] no schema-invalid rows — nothing to retire")
        continue
    for r in bad:
        stem = f"{r['query_id']}_{r['arm']}_r{r['rep']}d{r['draw']}"
        resp_dir = RUNS / "responses" / f"extract-{role}" / mdir
        sup_dir = RUNS / "superseded" / f"extract-{role}" / mdir

        def same_answer(path):
            """The filename stem is shared by every SUBJECT's answer to this query/arm/rep/draw —
            match on the record's subject_key, never on the stem alone (bug fixed 16 Sep 2026:
            the stem-only glob retired 3 valid records of other subjects alongside the target)."""
            try:
                return json.load(open(path, encoding="utf-8"))["spec"]["subject_key"] == r["subject_key"]
            except Exception:
                return False

        matches = [m for m in sorted(resp_dir.glob(stem + "_*.json")) if same_answer(m)]
        already = (len([m for m in sup_dir.glob(stem + "_*.json") if same_answer(m)])
                   if sup_dir.exists() else 0)
        if already >= 2:
            print(f"[{role}] {stem}: already re-called twice (E.1 cap) — NOT retired; "
                  f"this answer is excluded from {role}-derived analyses and reported")
            continue
        if not matches:
            print(f"[{role}] {stem}: no response record found to retire (was it an HTTP error? "
                  f"errors re-call automatically)")
            continue
        sup_dir.mkdir(parents=True, exist_ok=True)
        for m in matches:
            dest = sup_dir / m.name
            shutil.move(str(m), str(dest))
            print(f"[{role}] retired {m.name} -> runs/superseded/extract-{role}/{mdir}/ "
                  f"(re-call {already + 1} of 2)")
            total += 1
print(f"\nretired {total} record(s). Re-run the extract command(s) to re-call them.")
sys.exit(0)
