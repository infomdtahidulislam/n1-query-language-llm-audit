#!/usr/bin/env python3
"""round2_provenance_fix.py — provenance correction (prereg v0.50).

The authors state the 'prefill' metadata line carried by the first two ROUND2-ALIAS-DECISIONS
exports was erroneous (exported from the wrong working copy); the decisions are the authors' own.
The superseding export (07:46 UTC, decisions verified byte-identical to the 07:37 export) is the
file of record. This script corrects the source strings written into the two frozen tables by
build_round2_extension.py; table CONTENT (entities, classes, aliases) is untouched, so every
Round-1 metric and the E.6 gate stand. Both tables are re-hashed after the edit."""
import hashlib, re, unicodedata, csv
from pathlib import Path

W = Path("/home/claude/w")
OLD = ("round-2 review 16 Sep 2026 (AI-prefilled from public HQ/ownership info; "
       "author-reviewed and finalised)")
NEW = "round-2 author review 16 Sep 2026"

for name in ("brand_aliases.csv", "retailer_classification.csv"):
    p = W / name
    src = p.read_text(encoding="utf-8")
    n = src.count(OLD)
    assert n > 0, f"{name}: provenance string not found"
    src = src.replace(OLD, NEW)
    assert OLD not in src and "AI-prefilled" not in src
    p.write_text(src, encoding="utf-8")
    print(f"{name}: {n} source strings corrected")

# integrity re-check: no folded surface under two canonicals
def fold(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s.strip())
    return s.casefold().strip()
seen, dups = {}, []
for r in csv.DictReader(open(W / "brand_aliases.csv", encoding="utf-8")):
    for s in [r["display_name"], r["canonical_id"]] + [a for a in r["aliases"].split("|") if a.strip()]:
        fs = fold(s)
        if fs and fs in seen and seen[fs] != r["canonical_id"]:
            dups.append((fs, seen[fs], r["canonical_id"]))
        seen.setdefault(fs, r["canonical_id"])
assert not dups, dups
print("fold-integrity check: OK")

for name in ("brand_aliases.csv", "retailer_classification.csv"):
    h = hashlib.sha256((W / name).read_bytes()).hexdigest()
    rows = sum(1 for _ in open(W / name, encoding="utf-8")) - 1
    print(f"{name}: {rows} rows, sha256 {h}")
