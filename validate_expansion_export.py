#!/usr/bin/env python3
"""validate_expansion_export.py — check an expansion label export before banking it (E.6 escalation).

Format checks (hard failures) and descriptives (informational). The export is NEVER modified;
inconsistencies inside a rater's labels are reported and banked as-is — they are the rater's
record. Unlike Round 2, each rater has their OWN item set, so the expected pids come from
EXPANSION-MAPPING-authors-only.csv (rows assigned to the rater, plus every overlap row).

Usage:  python validate_expansion_export.py --rater R1 --file LABEL-EXPANSION-R1-labels.json
        [--mapping EXPANSION-MAPPING-authors-only.csv --coded runs/coded/main.final.jsonl]
        [--allow-partial]   (validate a progress save for the tranche drift check — never banked)
"""
import argparse, csv, json, re, sys
from collections import Counter
from pathlib import Path

CLASSES = {"bn", "banglish", "en", "mixed", "other"}
PRICE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s+([A-Za-z৳$দ-ো]{1,14})$")
TASK = "N1 labelling expansion round"

def fold_currency(tok):
    """The codebook's currency rule (decided 21 Sep 2026, before any Round-2 score): BDT for
    taka/Tk/BDT; USD for dollar/USD; literal other/unstated; any other named currency folds to
    `other` at scoring time. Deterministic; identical for all raters. None if not a currency."""
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
        return "other"
    return None

ap = argparse.ArgumentParser()
ap.add_argument("--rater", required=True)
ap.add_argument("--file", required=True)
ap.add_argument("--mapping", default="EXPANSION-MAPPING-authors-only.csv")
ap.add_argument("--coded", default=None)
ap.add_argument("--allow-partial", action="store_true",
                help="accept a progress save (partial=true) for drift checks; never bank it")
a = ap.parse_args()

expected = set()
for m in csv.DictReader(open(a.mapping, encoding="utf-8")):
    if m["rater"] == a.rater or m["overlap"] == "True":
        expected.add(m["pid"])
assert expected, f"no items for {a.rater} in {a.mapping}"

d = json.loads(Path(a.file).read_text(encoding="utf-8"))
assert d.get("task") == TASK, f"wrong task: {d.get('task')!r}"
assert d.get("rater") == a.rater, f"export rater {d.get('rater')!r} != {a.rater}"
if d.get("partial"):
    if not a.allow_partial:
        sys.exit("this is a PROGRESS save, not the final export — do not bank it "
                 "(use --allow-partial only for the tranche drift check)")
    print(f"PROGRESS save accepted for drift check only — done {d.get('done')} — NEVER banked")
rows = d.get("labels") or []
pids = [r.get("pid") for r in rows]
assert len(set(pids)) == len(rows), "duplicate pids in export"
unknown = sorted(set(pids) - expected)
assert not unknown, f"pids not in this rater's set: {unknown[:5]}"
if not d.get("partial"):
    missing = sorted(expected - set(pids))
    assert not missing, f"expected {len(expected)} labels, got {len(rows)}; missing e.g. {missing[:5]}"
    assert len(rows) == len(expected)

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
        elif cur not in (m.group(2).strip().lower(), m.group(2).strip().upper()):
            folded.append((r["pid"], x, cur))
    b = {s.strip().casefold() for s in (r.get("brands") or [])}
    missing_b = [x for x in (r.get("recommended") or []) if x.strip().casefold() not in b]
    if missing_b:
        rec_not_in_brands.append((r["pid"], missing_b))
assert not bad_enum, f"invalid enum values: {bad_enum[:5]}"
assert not bad_price, f"unparseable price lines: {bad_price[:5]}"

lang = Counter(r["answer_language"] for r in rows)
refused = [r["pid"] for r in rows if r["refused"] == "true"]
empty_comm = sum(1 for r in rows if not (r["brands"] or r["prices"] or r["retailers"]))
comments = [(r["pid"], r["comments"].strip()) for r in rows if (r.get("comments") or "").strip()]

print(f"export OK: {a.rater}, {len(rows)}/{len(expected)} labels, exported_at {d.get('exported_at')}")
print(f"  answer_language : " + ", ".join(f"{k} {v}" for k, v in sorted(lang.items())))
print(f"  refused=true    : {len(refused)}" + (f"  ({', '.join(refused[:30])}{'...' if len(refused)>30 else ''})" if refused else ""))
print(f"  no commercial content: {empty_comm}")
print(f"  comments ({len(comments)}):")
for pid, c in comments:
    print(f"    {pid}: {c}")
if folded:
    print(f"  currency tokens that will fold at scoring (banked verbatim):")
    for pid, x, cur in folded:
        print(f"    {pid}: {x!r} -> {cur}")
if rec_not_in_brands:
    print(f"  NOTE — recommended entries not present in brands (banked as-is):")
    for pid, m in rec_not_in_brands:
        print(f"    {pid}: {m}")

if a.coded:
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
if not d.get("partial"):
    print(f"\nvalid — bank as LABEL-EXPANSION-{a.rater}-labels.json (+ _as-received copy)")
