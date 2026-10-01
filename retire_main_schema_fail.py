#!/usr/bin/env python3
"""retire_main_schema_fail.py — E.1 retry mechanics for the MAIN primary extraction.

Reads runs/extracted/main.primary.jsonl, finds rows whose extraction failed schema validation,
and RETIRES each one's cached extraction response record to runs/superseded/ (never deleted),
so that re-running `extract --phase main --primary --go` re-calls exactly those answers live.
Per E.1 an answer may be re-called at most twice: a third schema failure for the same answer is
reported and left alone (it is then excluded from extractor-derived analyses and reported,
mirroring D.6's left-short rule).

Matching is by the cached record's spec.subject_key, never by the filename stem alone — the stem
is shared by all six subjects' answers to the same query/arm/rep/draw (fix of 16 Sep 2026,
disclosed in the version history at v0.55).

Run from the study folder:
    python retire_main_schema_fail.py
then:
    python n1_pipeline.py extract --phase main --primary --concurrency 60 --go
    python n1_pipeline.py finalize --phase main
"""
import json, shutil, sys
from pathlib import Path

RUNS = Path("runs")
EX = RUNS / "extracted" / "main.primary.jsonl"
if not EX.exists():
    sys.exit(f"{EX} not found — run extract first")
resp_root = RUNS / "responses" / "extract-primary"
mdirs = [d for d in resp_root.iterdir() if d.is_dir()] if resp_root.exists() else []
if len(mdirs) != 1:
    sys.exit(f"expected exactly one extractor model dir under {resp_root}, "
             f"found {[d.name for d in mdirs]}")
mdir = mdirs[0]

rows = [json.loads(l) for l in open(EX, encoding="utf-8") if l.strip()]
bad = [r for r in rows if r.get("schema_errors")]
print(f"{len(bad)} schema-invalid extraction row(s) of {len(rows)}")

retired = 0
for r in bad:
    stem = f"{r['query_id']}_{r['arm']}_r{r['rep']}d{r['draw']}"

    def same_answer(p):
        """True when this cached record is the extraction of THIS subject's answer."""
        try:
            return json.load(open(p, encoding="utf-8"))["spec"]["subject_key"] == r["subject_key"]
        except Exception:
            return False

    sup = RUNS / "superseded" / "extract-primary" / mdir.name
    already = (len([m for m in sup.glob(stem + "_*.json") if same_answer(m)])
               if sup.exists() else 0)
    if already >= 2:
        print(f"  {stem} [{r['subject_model_id']}]: already re-called twice (E.1 cap) — NOT "
              f"retired; this answer is excluded from extractor-derived analyses and reported")
        continue
    matches = [m for m in sorted(mdir.glob(stem + "_*.json")) if same_answer(m)]
    if not matches:
        print(f"  {stem} [{r['subject_model_id']}]: no cached record found — nothing to retire "
              f"(an HTTP error re-calls automatically)")
        continue
    sup.mkdir(parents=True, exist_ok=True)
    for m in matches:
        dest = sup / m.name
        n = 1
        while dest.exists():
            # NEVER overwrite an earlier retired record: a re-retired answer keeps the same
            # cache-key filename, so suffix each additional retirement (.a2, .a3, ...).
            # (Fix of 16 Sep 2026: the first version of this helper overwrote on collision,
            # losing 16 first-attempt payloads — disclosed in the version history.)
            n += 1
            dest = sup / m.name.replace(".json", f".a{n}.json")
        shutil.move(str(m), str(dest))
        retired += 1
        print(f"  retired {m.name} -> {dest.name}  (re-call {already + 1} of 2)  "
              f"[{r['subject_model_id']}]")

print(f"\nretired {retired} record(s). Re-run the extract command; only these call live "
      f"(everything else is cached).")
