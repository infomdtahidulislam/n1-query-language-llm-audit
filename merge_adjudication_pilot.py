#!/usr/bin/env python3
"""Merge R1's adjudication export into runs/coded/<phase>.adjudicate.jsonl (N1, D.4).

Reads ADJUDICATE-R1-decisions.json (R1's export — the raw record, never edited)
and ADJUDICATE-MAPPING-authors-only.csv (row_id -> record key), writes
R1_decision / R1_note into the adjudicate file by key, and prints the
reconciliation. finalize regenerates the adjudicate file with R1_decision null,
so RE-RUN THIS after any finalize. The export and mapping are never modified.
"""
import argparse, csv, json, sys
from pathlib import Path

CLASSES = {"bn", "banglish", "en", "mixed", "other"}

ap = argparse.ArgumentParser()
ap.add_argument("--phase", default="pilot")
ap.add_argument("--decisions", default="ADJUDICATE-R1-PILOT-decisions.json")
ap.add_argument("--mapping", default="ADJUDICATE-PILOT-MAPPING-authors-only.csv")
ap.add_argument("--runs", default="runs")
a = ap.parse_args()

dec = json.loads(Path(a.decisions).read_text(encoding="utf-8"))
rows = dec.get("decisions") or []
ids = [r.get("row_id") for r in rows]
assert dec.get("rater") == "R1", "export is not from R1"
assert len(rows) == 13 and len(set(ids)) == 13, f"expected 13 unique rows, got {len(rows)}"
assert sorted(ids) == [f"B{i:02d}" for i in range(1, 14)], "row ids are not B01..B13"
bad = [r for r in rows if r.get("decision") not in CLASSES]
assert not bad, f"invalid decisions: {bad}"

key_by_rid = {}
meta_by_rid = {}
for m in csv.DictReader(open(a.mapping, encoding="utf-8")):
    key_by_rid[m["row_id"]] = m["key"]
    meta_by_rid[m["row_id"]] = m
assert set(key_by_rid) == set(ids), "mapping/export row_id mismatch"

adj_p = Path(a.runs) / "coded" / f"{a.phase}.adjudicate.jsonl"
adj = [json.loads(l) for l in open(adj_p, encoding="utf-8") if l.strip()]
by_key = {r["key"]: r for r in adj}
assert set(by_key) == set(key_by_rid.values()), \
    "adjudicate file keys do not match the mapping — was finalize re-run on changed data?"

for r in rows:
    rec = by_key[key_by_rid[r["row_id"]]]
    rec["R1_decision"] = r["decision"]
    rec["R1_note"] = r.get("note") or None

tmp = adj_p.with_suffix(".jsonl.tmp")
with open(tmp, "w", encoding="utf-8") as f:
    for r in adj:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
tmp.replace(adj_p)

# reconciliation
print(f"merged 13 R1 decisions -> {adj_p}\n")
print(f"{'id':4} {'qid':5} {'arm':12} {'model':18} {'script':7} {'extractor':10} "
      f"{'R1':9} {'R1 sided with':14} {'outcome effect'}")
agree_script = agree_ext = neither = 0
for rid in sorted(ids):
    m = meta_by_rid[rid]
    rec = by_key[m["key"]]
    r1 = rec["R1_decision"]
    s, e = m["script_class"], m["extractor_answer_language"]
    if r1 == s and r1 == e: side = "both"
    elif r1 == s: side = "script check"; agree_script += 1
    elif r1 == e: side = "extractor"; agree_ext += 1
    else: side = "neither"; neither += 1
    # outcome: for bl/bl_translit arms bn and mixed are both non-conforming (reversion);
    # for the bn arm the deterministic script class decides (D.4) — adjudication is QC.
    eff = "none (outcome unchanged)"
    note = f"  note: {rec['R1_note']}" if rec.get("R1_note") else ""
    print(f"{rid:4} {m['query_id']:5} {m['arm']:12} {m['model_id']:18} {s:7} {e:10} "
          f"{r1:9} {side:14} {eff}{note}")
print(f"\nR1 sided with the deterministic script check on {agree_script}, "
      f"with the extractor on {agree_ext}, with neither on {neither} (of 13).")
