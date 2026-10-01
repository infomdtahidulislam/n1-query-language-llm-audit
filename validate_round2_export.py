#!/usr/bin/env python3
"""validate_round2_export.py — check a Round-2 label export before banking it (E.3, main).

Format checks (hard failures) and descriptives (informational). The export is NEVER modified;
inconsistencies inside a rater's labels (e.g. a `recommended` entry missing from `brands`) are
reported and banked as-is — they are the rater's record.

Usage:  python validate_round2_export.py --rater R3 --file "Round 2 got from R3.json"
        [--mapping ROUND2-MAPPING-authors-only.csv --coded runs/coded/main.jsonl]  (authors-side
        cross-tabs; never shown to raters)
"""
import argparse, csv, json, re, sys
from collections import Counter
from pathlib import Path

CLASSES = {"bn", "banglish", "en", "mixed", "other"}
PRICE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s+([A-Za-z\u09F3$\u09A6-\u09CB]{1,14})$")
N = 300

def fold_currency(tok):
    """The codebook's own currency rule, applied to whatever token the rater wrote:
    BDT for taka/Tk/BDT; USD for dollar/USD; the literal tokens other/unstated; ANY other
    named currency (INR, EUR, ...) folds to `other`. Deterministic; identical for all raters;
    decided 21 Sep 2026 before any Round-2 score was computed. Returns None if not a currency."""
    t = tok.strip()
    if t.upper() in ("BDT", "USD"):
        return t.upper()
    if t.lower() in ("other", "unstated"):
        return t.lower()
    if t.lower() in ("taka", "tk", "৳", "টাকা"):
        return "BDT"
    if t.lower() in ("dollar", "dollars"):
        return "USD"
    if t.isalpha():
        return "other"          # a named currency the codebook folds to `other`
    return None

ap = argparse.ArgumentParser()
ap.add_argument("--rater", required=True)
ap.add_argument("--file", required=True)
ap.add_argument("--mapping", default=None)
ap.add_argument("--coded", default=None)
a = ap.parse_args()

d = json.loads(Path(a.file).read_text(encoding="utf-8"))
assert d.get("task") == "N1 labelling round 2", f"wrong task: {d.get('task')!r}"
assert d.get("rater") == a.rater, f"export rater {d.get('rater')!r} != {a.rater}"
assert not d.get("partial"), "this is a PROGRESS save, not the final export — do not bank it"
rows = d.get("labels") or []
pids = [r.get("pid") for r in rows]
assert len(rows) == N and len(set(pids)) == N, f"expected {N} unique labels, got {len(rows)}"
assert sorted(pids) == [f"M{i:03d}" for i in range(1, N + 1)], "pids are not M001..M300"

bad_price, bad_enum, rec_not_in_brands, folded = [], [], [], []
for r in rows:
    if r.get("refused") not in ("true", "false"):
        bad_enum.append((r["pid"], "refused", r.get("refused")))
    if r.get("answer_language") not in CLASSES:
        bad_enum.append((r["pid"], "answer_language", r.get("answer_language")))
    for x in r.get("prices") or []:
        m = PRICE_RE.match(str(x).strip())
        cur = fold_currency(m.group(2)) if m else None
        if cur is None:
            bad_price.append((r["pid"], x))
        elif cur != m.group(2).strip().upper() and cur not in (m.group(2).strip().lower(),
                                                               m.group(2).strip().upper()):
            folded.append((r["pid"], x, cur))
    b = {s.strip().casefold() for s in (r.get("brands") or [])}
    missing = [x for x in (r.get("recommended") or []) if x.strip().casefold() not in b]
    if missing:
        rec_not_in_brands.append((r["pid"], missing))
assert not bad_enum, f"invalid enum values: {bad_enum[:5]}"
assert not bad_price, f"unparseable price lines: {bad_price[:5]}"

lang = Counter(r["answer_language"] for r in rows)
refused = [r["pid"] for r in rows if r["refused"] == "true"]
empty_comm = sum(1 for r in rows if not (r["brands"] or r["prices"] or r["retailers"]))
comments = [(r["pid"], r["comments"].strip()) for r in rows if (r.get("comments") or "").strip()]

print(f"export OK: {a.rater}, {N} labels, exported_at {d.get('exported_at')}")
print(f"  answer_language : " + ", ".join(f"{k} {v}" for k, v in sorted(lang.items())))
print(f"  refused=true    : {len(refused)}  ({', '.join(refused)})")
print(f"  no commercial content: {empty_comm}")
print(f"  comments ({len(comments)}):")
for pid, c in comments:
    print(f"    {pid}: {c}")
if folded:
    print(f"  currency tokens folded per the codebook rule (banked verbatim; folding happens at "
          f"scoring time, identically for all raters):")
    for pid, x, cur in folded:
        print(f"    {pid}: {x!r} -> {cur}")
if rec_not_in_brands:
    print(f"  NOTE — recommended entries not present in brands (banked as-is, the codebook asks "
          f"raters for the subset but the form does not enforce it):")
    for pid, m in rec_not_in_brands:
        print(f"    {pid}: {m}")

if a.mapping and a.coded:
    key_by_pid = {m["pid"]: m["key"] for m in csv.DictReader(open(a.mapping, encoding="utf-8"))}
    coded = {}
    for l in open(a.coded, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            coded[r["key"]] = r
    ct = Counter()
    for r in rows:
        c = coded.get(key_by_pid.get(r["pid"]))
        if c:
            ct[(c["script_class"], r["answer_language"])] += 1
    print(f"\n  authors-only cross-tab  script_class (deterministic) x rater label:")
    scripts = sorted({s for s, _ in ct})
    labels = sorted({l for _, l in ct})
    print(f"    {'':8}" + "".join(f"{l:>10}" for l in labels))
    for s in scripts:
        print(f"    {s:8}" + "".join(f"{ct.get((s, l), 0):>10}" for l in labels))
print("\nvalid — bank as LABEL-ROUND2-" + a.rater + "-labels.json (+ _as-received copy)")
