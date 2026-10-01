#!/usr/bin/env python3
"""build_round2_extension.py — extend the frozen brand_aliases.csv and retailer_classification.csv
from ROUND2-ALIAS-DECISIONS.json (the authors' round-2 verification; C.2 / v0.45 / v0.48).

Order: validate export -> create new canonicals (brand/retailer/both) -> apply alias merges
(targets may be canonicals created in this same batch) -> record exclusions -> integrity check
(no folded surface under two canonicals across the whole extended table) -> write + sha256.

The decisions file is the raw record and is never modified. Backups of the pre-extension tables
are kept as *.pre-round2.csv."""
import json, csv, re, sys, hashlib, unicodedata, shutil
from collections import Counter
from pathlib import Path

W = Path("/home/claude/w")
DEC = W / "ROUND2-ALIAS-DECISIONS.json"
SRC = ("round-2 review 16 Sep 2026 (AI-prefilled from public HQ/ownership info; "
       "author-reviewed and finalised)")

def fold(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s.strip())
    return s.casefold().strip()

D = json.load(open(DEC, encoding="utf-8"))
rows = D["decisions"]
assert D["task"] == "N1 round-2 alias decisions" and len(rows) == 81
assert sorted(r["i"] for r in rows) == list(range(81))
cand = list(csv.DictReader(open(W / "round2_alias_candidates.csv", encoding="utf-8")))
assert {c["example_surface"] for c in cand} == {r["surface"] for r in rows}, "surfaces do not match the candidate list"

brands = list(csv.DictReader(open(W / "brand_aliases.csv", encoding="utf-8")))
retail = list(csv.DictReader(open(W / "retailer_classification.csv", encoding="utf-8")))
existing = {r["canonical_id"] for r in brands}
by_id = {r["canonical_id"]: r for r in brands}
ret_by_id = {r["canonical_id"]: r for r in retail}

KINDS = {"brand", "retailer", "both", "alias", "exclude"}
CLS = {"local", "global", "ambiguous"}
new_rows, alias_ops, excl = [], [], []
new_ids = set()
for r in rows:
    k = r["kind"]
    assert k in KINDS, f"bad kind on {r['surface']}"
    if k in ("brand", "retailer", "both"):
        slug, disp, cls = r["slug"].strip(), r["display"].strip(), r["cls"]
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug), f"bad slug {slug!r}"
        assert cls in CLS and disp, f"bad cls/display on {r['surface']}"
        assert slug not in existing, f"new slug {slug!r} collides with existing canonical"
        assert slug not in new_ids, f"duplicate new slug {slug!r}"
        new_ids.add(slug)
        new_rows.append((slug, disp, cls, k, r["surface"]))
    elif k == "alias":
        alias_ops.append((r["surface"], r["target"].strip()))
    else:
        excl.append(r["surface"])

# 1) create new canonicals
n_ret_added = 0
for slug, disp, cls, kind, surface in new_rows:
    aliases = [surface] if fold(surface) != fold(disp) else []
    brands.append({"canonical_id": slug, "display_name": disp, "class": cls,
                   "aliases": "|".join(aliases), "source": SRC + ("; brand+retailer" if kind == "both" else "")})
    by_id[slug] = brands[-1]
    if kind in ("retailer", "both"):
        retail.append({"canonical_id": slug, "display_name": disp, "class": cls, "source": SRC})
        n_ret_added += 1

# 2) alias merges (targets may be existing or new)
valid = existing | new_ids
for surface, target in alias_ops:
    assert target in valid, f"alias target {target!r} unknown"
    row = by_id[target]
    cur = [a for a in row["aliases"].split("|") if a.strip()]
    if fold(surface) not in {fold(a) for a in cur} | {fold(row["display_name"])}:
        cur.append(surface)
        row["aliases"] = "|".join(cur)
    if not row["source"].endswith("aliases extended round-2 16 Sep 2026"):
        row["source"] = row["source"] + "; aliases extended round-2 16 Sep 2026"

# 3) integrity check: no folded surface under two canonicals
seen = {}
dups = []
for r in brands:
    surfaces = [r["display_name"], r["canonical_id"]] + [a for a in r["aliases"].split("|") if a.strip()]
    for s in surfaces:
        fs = fold(s)
        if not fs:
            continue
        if fs in seen and seen[fs] != r["canonical_id"]:
            dups.append((fs, seen[fs], r["canonical_id"]))
        seen.setdefault(fs, r["canonical_id"])
assert not dups, f"folded-surface collisions across canonicals: {dups}"

# 4) write, backup, hash
shutil.copy(W / "brand_aliases.csv", W / "brand_aliases.pre-round2.csv")
shutil.copy(W / "retailer_classification.csv", W / "retailer_classification.pre-round2.csv")
with open(W / "brand_aliases.csv", "w", newline="", encoding="utf-8") as f:
    wcsv = csv.DictWriter(f, fieldnames=["canonical_id", "display_name", "class", "aliases", "source"])
    wcsv.writeheader()
    for r in brands:
        wcsv.writerow(r)
with open(W / "retailer_classification.csv", "w", newline="", encoding="utf-8") as f:
    wcsv = csv.DictWriter(f, fieldnames=["canonical_id", "display_name", "class", "source"])
    wcsv.writeheader()
    for r in retail:
        wcsv.writerow(r)

h1 = hashlib.sha256((W / "brand_aliases.csv").read_bytes()).hexdigest()
h2 = hashlib.sha256((W / "retailer_classification.csv").read_bytes()).hexdigest()
cc = Counter(cls for _, _, cls, _, _ in new_rows)
print(f"new canonicals: {len(new_rows)} (classes {dict(cc)}); retailer rows added: {n_ret_added}")
print(f"alias merges: {len(alias_ops)}; exclusions recorded: {len(excl)}")
print(f"brand_aliases.csv: {len(brands)} entities, sha256 {h1}")
print(f"retailer_classification.csv: {len(retail)} rows, sha256 {h2}")
json.dump({"new_canonicals": [dict(zip(('canonical_id','display','class','kind','surface'), t)) for t in new_rows],
           "alias_merges": alias_ops, "exclusions": excl,
           "sha256": {"brand_aliases.csv": h1, "retailer_classification.csv": h2}},
          open(W / "round2_extension_record.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote round2_extension_record.json")
