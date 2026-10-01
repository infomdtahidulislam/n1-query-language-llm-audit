#!/usr/bin/env python3
"""Build the frozen brand_aliases.csv + retailer_classification.csv from F2-DECISIONS.json
(authors' verification, exported 13 Sep 2026) merged over the 49-row starter.

Rules (documented, prereg v0.40):
- starter rows keep id/class/display; their alias sets extend with every observed surface form
  the authors pointed at them.
- decisions kind=brand/retailer/both become rows with the authors' class; kind=alias folds the
  cluster's surface forms into the target's aliases; kind=exclude enters no table (listed in notes).
- display casing: the authors' display if it carries any uppercase; else the first observed
  cased variant; else as written (Bangla script has no case).
- every note is preserved verbatim in brand_aliases.decisions-notes.md.
Schema unchanged: canonical_id,display_name,class,aliases,source.
"""
import csv, json, hashlib
from collections import OrderedDict

dec = json.load(open("F2-DECISIONS.json", encoding="utf-8"))["decisions"]
starter = list(csv.DictReader(open("brand_aliases.starter.csv", encoding="utf-8")))

rows = OrderedDict()   # canonical_id -> row dict
kind_of = {}           # canonical_id -> brand/retailer/both (decisions only)
for s in starter:
    rows[s["canonical_id"]] = dict(canonical_id=s["canonical_id"], display_name=s["display_name"],
                                   cls=s["class"], aliases=list(filter(None, s["aliases"].split("|"))),
                                   source=s["source"] + "; aliases extended F2-review 13 Sep 2026")

def best_display(author_display, surfaces):
    if any(c.isupper() for c in author_display): return author_display
    for f in surfaces:
        if any(c.isupper() for c in f): return f
    return author_display

def add_aliases(cid, forms):
    r = rows[cid]
    have = {a.casefold() for a in r["aliases"]} | {r["display_name"].casefold(), cid.casefold()}
    for f in forms:
        f = f.strip()
        if f and f.casefold() not in have:
            r["aliases"].append(f); have.add(f.casefold())

# pass 1: create new rows
for x in dec:
    if x["kind"] in ("brand", "retailer", "both"):
        surfaces = [s.strip() for s in x["surface"].split(" | ")]
        cid = x["slug"]
        assert cid not in rows, f"slug re-declares existing id: {cid}"
        rows[cid] = dict(canonical_id=cid, display_name=best_display(x["display"], surfaces),
                         cls=x["cls"], aliases=[], source="F2-review 13 Sep 2026")
        kind_of[cid] = x["kind"]
        add_aliases(cid, surfaces)

# pass 2: fold alias clusters into targets
for x in dec:
    if x["kind"] == "alias":
        add_aliases(x["target"], [s.strip() for s in x["surface"].split(" | ")])

# integrity: no casefolded alias under two canonicals
seen = {}
for cid, r in rows.items():
    for a in [r["display_name"]] + r["aliases"] + [cid]:
        k = a.casefold()
        if k in seen and seen[k] != cid:
            raise SystemExit(f"ALIAS COLLISION: {a!r} under both {seen[k]} and {cid}")
        seen[k] = cid
print("integrity: no alias maps to two canonicals |", len(seen), "distinct surface keys")

with open("brand_aliases.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["canonical_id", "display_name", "class", "aliases", "source"])
    for r in rows.values():
        w.writerow([r["canonical_id"], r["display_name"], r["cls"], "|".join(r["aliases"]), r["source"]])

# F3 retailer draft: decided retailer/both + starter entities the corpus used mainly as retailers
STARTER_RETAILERS = {}
cand = {c["surface_casefold"]: c for c in csv.DictReader(open("brand_aliases.candidates.csv", encoding="utf-8"))}
agg = {}
for c in cand.values():
    m = c["matched_canonical"].replace(" (accent-folded)", "")
    if m != "NEW":
        a = agg.setdefault(m, [0, 0])
        a[0] += int(c["n_as_retailer"]); a[1] += int(c["n_as_brand"])
for m, (nr, nb) in agg.items():
    if nr > nb:                       # aggregate over ALL clusters of the canonical
        STARTER_RETAILERS[m] = nr
ret = []
for x in dec:
    if x["kind"] in ("retailer", "both"):
        ret.append((x["slug"], rows[x["slug"]]["display_name"], x["cls"],
                    "author decision (F2 review)" + ("; brand+retailer" if x["kind"] == "both" else "")))
for cid in sorted(STARTER_RETAILERS):
    if cid in rows and cid not in {r[0] for r in ret}:
        ret.append((cid, rows[cid]["display_name"], rows[cid]["cls"],
                    f"starter entity; used as retailer in smoke corpus (n={STARTER_RETAILERS[cid]}) — CONFIRM CLASS"))
ret.sort()
with open("retailer_classification.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["canonical_id", "display_name", "class", "source"])
    w.writerows(ret)

# notes file: every author note verbatim + excludes + sub-brand merges + ambiguous
with open("brand_aliases.decisions-notes.md", "w", encoding="utf-8") as f:
    f.write("# F2 decision notes — authors' verification, exported 13 Sep 2026\n\n"
            "Verbatim record of every note in `F2-DECISIONS.json` (C.1: ambiguous cases documented "
            "one-by-one; mapping judgment calls recorded). The export itself is the raw record.\n\n")
    f.write("## Ambiguous-class entities (C.5 three-way sensitivity)\n\n")
    for x in dec:
        if x["cls"] == "ambiguous":
            f.write(f"- **{x['slug']}** — {x['note'] or '(no note)'}\n")
    f.write("\n## Excluded (not a brand)\n\n")
    for x in dec:
        if x["kind"] == "exclude":
            f.write(f"- {x['surface']} — {x['note'] or '(no note)'}\n")
    f.write("\n## Cross-entity mappings (a cluster folded into a different entity)\n\n")
    for x in dec:
        if x["kind"] == "alias" and x["target"] not in x["surface"].casefold().replace(" ", "").replace("-", ""):
            first = x["surface"].split(" | ")[0]
            if x["target"].replace("-", "") not in first.casefold().replace(" ", "").replace("-", "").replace(".", ""):
                f.write(f"- {first} → `{x['target']}`" + (f" — {x['note']}" if x["note"] else "") + "\n")
    f.write("\n## All other notes\n\n")
    for x in dec:
        if x["note"] and x["cls"] != "ambiguous" and x["kind"] != "exclude":
            f.write(f"- [{x['kind']}] {x['surface'].split(' | ')[0]} — {x['note']}\n")

h1 = hashlib.sha256(open("brand_aliases.csv", "rb").read()).hexdigest()
h2 = hashlib.sha256(open("retailer_classification.csv", "rb").read()).hexdigest()
open("/tmp/claude-0/-home-claude/ebeba51b-6fe6-55f3-a31d-e48865156c93/scratchpad/f2hashes.txt", "w").write(h1 + "\n" + h2)
n_new = sum(1 for x in dec if x["kind"] in ("brand", "retailer", "both"))
print(f"brand_aliases.csv: {len(rows)} entities (49 starter + {n_new} new) sha256 {h1[:16]}…")
print(f"retailer_classification.csv: {len(ret)} retailers sha256 {h2[:16]}…")
from collections import Counter
print("class mix:", dict(Counter(r['cls'] for r in rows.values())))
print("retailer class mix:", dict(Counter(r[2] for r in ret)))
print("starter-derived retailer rows needing class confirm:", [r[0] for r in ret if "CONFIRM" in r[3]])
