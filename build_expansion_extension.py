#!/usr/bin/env python3
"""build_expansion_extension.py — N1: apply the authors' Appendix C.2–C.3 decisions for the expansion
sample (EXPANSION-ALIAS-DECISIONS.json, exported from EXPANSION-ALIAS-REVIEW.html).

THE FROZEN TABLES ARE NEVER MODIFIED. brand_aliases.csv and retailer_classification.csv stay byte-
identical (they are in FREEZE-MANIFEST.sha256); the extension is written beside them as supersets:

    brand_aliases.expansion.csv            frozen rows (aliases appended where the authors merged a new
                                           spelling into an existing entity) + the new entities
    retailer_classification.expansion.csv  frozen rows + new entities decided Retailer / Brand + retailer
    alias_exclusions.expansion.csv         names decided "Not a brand" (removed from every set)
    alias_unidentified.expansion.csv       names the authors could not identify: left out of the tables on
                                           purpose, so they stay in every set as unclassifiable (F.3)
    EXPANSION-EXTENSION-RECORD.json        counts, lists, checks and every input/output sha256

Resolver for the extended table: the registered one (fold, exact match, then 3/2/1-token prefix), with
the exclusion list entered into the same map as a "not a brand" target, so exclusions follow exactly
the precedence aliases do.

Checks (the build aborts on any failure):
  1. the decisions file is a complete, well-formed export of THIS review (1 row per candidate, surfaces
     and drafts identical to EXPANSION-ALIAS-CANDIDATES.csv);
  2. every new lookup key (new spellings, new display names) is itself unresolved under the frozen table
     — which guarantees, by the prefix precedence, that no name the frozen table already resolves can
     change its resolution; this is then verified directly on every name observed in every human label
     file (Round 1, Round 2, expansion) and every machine extraction of the main run;
  3. no folded name maps to two entities anywhere in the extended table;
  4. every candidate resolves, under the extended table, to exactly the authors' decision.

Usage (study root):  python build_expansion_extension.py [--decisions EXPANSION-ALIAS-DECISIONS.json]
"""
import argparse, csv, hashlib, json, re, sys, unicodedata
from collections import Counter
from pathlib import Path

W = Path(".")
GATES = {
    "brand_aliases.csv": "0b7bd5e8355c919300129b6ba96008d5cb2d95a691aaf759a1e82823ee2b00ea",
    "retailer_classification.csv": "94abc294de6fc82c6583d1e9be08bc7443e49008376cf2a718cd6febd19cf22a",
    "EXPANSION-ALIAS-CANDIDATES.csv": "5048e8388266b4a1d0058e8dae24b1fe4f5642b20e451c99c67997bdbc285805",
}
HUMAN = ["LABEL-ROUND1-R1-labels.json", "LABEL-ROUND1-R2-labels.json", "LABEL-ROUND1-R3-labels.json",
         "LABEL-ROUND2-R1-labels.json", "LABEL-ROUND2-R2-labels.json", "LABEL-ROUND2-R3-labels.json",
         "LABEL-EXPANSION-R1-labels.json", "LABEL-EXPANSION-R2-labels.json", "LABEL-EXPANSION-R3-labels.json"]
MACHINE = ["runs/extracted/main.primary.jsonl", "runs/extracted/main.cross_check.jsonl"]
EXCLUDED = "__not_a_brand__"
SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")

ap = argparse.ArgumentParser()
ap.add_argument("--decisions", default="EXPANSION-ALIAS-DECISIONS.json")
ap.add_argument("--date", default=None, help="review date for the source column (default: export date)")
args = ap.parse_args()

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

for f, want in GATES.items():
    if sha(W / f) != want:
        sys.exit(f"INPUT GATE: {f} is not the frozen/banked file — refusing to build")

def fold(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s.strip())
    return s.casefold().strip()

def build_map(rows, excl=()):
    m = {}
    for row in rows:
        m[fold(row["display_name"])] = row["canonical_id"]
        for al in row["aliases"].split("|"):
            if al.strip():
                m[fold(al)] = row["canonical_id"]
    for k in excl:
        m[k] = EXCLUDED
    return m

def resolve(m, s):
    fs = fold(s)
    if fs in m:
        return m[fs]
    toks = fs.split()
    for n in (3, 2, 1):
        if len(toks) >= n and " ".join(toks[:n]) in m:
            return m[" ".join(toks[:n])]
    return None

frozen_b = list(csv.DictReader(open(W / "brand_aliases.csv", encoding="utf-8")))
frozen_r = list(csv.DictReader(open(W / "retailer_classification.csv", encoding="utf-8")))
FM = build_map(frozen_b)
existing = {r["canonical_id"] for r in frozen_b}

# ---------- 1. the decisions file ----------
cand = list(csv.DictReader(open(W / "EXPANSION-ALIAS-CANDIDATES.csv", encoding="utf-8")))
D = json.load(open(W / args.decisions, encoding="utf-8"))
dec = D["decisions"]
assert D["task"] == "N1 expansion alias decisions", "not an expansion alias decisions export"
assert D["n"] == len(cand) == len(dec), f"export has {len(dec)} rows, review has {len(cand)}"
assert [r["i"] for r in dec] == list(range(len(cand))), "rows missing or out of order"
for r, c in zip(dec, cand):
    assert r["surface"] == c["example_surface"] and r["surface_folded"] == c["surface_folded"], \
        f"row {r['i']}: surface does not match this review build"
    pf = r["prefill"]
    assert (pf["kind"], pf["cls"], pf["id"]) == (c["prefill_kind"], c["prefill_class"], c["prefill_id"]), \
        f"row {r['i']}: draft block does not match this review build"
review_date = args.date or D["exported_at"][:10]
KINDS, CLS = {"brand", "retailer", "both", "alias", "exclude", "unidentified"}, {"local", "global", "ambiguous"}

new_rows, alias_ops, excl, unid = [], [], [], []
new_ids = set()
forms = {c["surface_folded"]: [s for s in c["all_surfaces"].split(" | ") if s.strip()] for c in cand}
for r in dec:
    k = r["kind"]
    assert k in KINDS, f"row {r['i']}: bad kind {k!r}"
    how = ("author decision" if r["changed_from_prefill"] else
           "author-completed draft" if r.get("completed_by_authors") else "author-confirmed draft")
    if k in ("brand", "retailer", "both"):
        slug, disp, cls = r["slug"].strip(), r["display"].strip(), r["cls"]
        assert SLUG.fullmatch(slug), f"row {r['i']} ({r['surface']}): canonical_id {slug!r} must be lower-case a-z0-9 with hyphens"
        assert cls in CLS and disp, f"row {r['i']} ({r['surface']}): class/display missing"
        assert slug not in existing, f"row {r['i']}: new id {slug!r} already exists in the frozen table — use 'Alias of existing'"
        assert slug not in new_ids, f"row {r['i']}: new id {slug!r} used twice"
        new_ids.add(slug)
        new_rows.append({"i": r["i"], "slug": slug, "display": disp, "cls": cls, "kind": k,
                         "key": r["surface_folded"], "forms": forms[r["surface_folded"]], "how": how})
    elif k == "alias":
        alias_ops.append({"i": r["i"], "key": r["surface_folded"], "forms": forms[r["surface_folded"]],
                          "target": r["target"].strip(), "how": how})
    elif k == "unidentified":
        unid.append({"i": r["i"], "key": r["surface_folded"], "surface": r["surface"], "note": r.get("note", ""),
                     "how": how})
    else:
        excl.append({"i": r["i"], "key": r["surface_folded"], "surface": r["surface"], "note": r.get("note", ""),
                     "how": how})

valid_targets = existing | new_ids
for a in alias_ops:
    assert a["target"] in valid_targets, f"row {a['i']}: alias target {a['target']!r} is not an existing or new entity"

# ---------- 2a. every new lookup key must be unresolved under the frozen table ----------
bad = []
for n in new_rows:
    for s in [n["display"]] + n["forms"]:
        if resolve(FM, s) is not None:
            bad.append((n["i"], s, resolve(FM, s)))
for a in alias_ops:
    for s in a["forms"]:
        if resolve(FM, s) is not None:
            bad.append((a["i"], s, resolve(FM, s)))
for e in excl:
    if resolve(FM, e["key"]) is not None:
        bad.append((e["i"], e["key"], resolve(FM, e["key"])))
if bad:
    sys.exit("NEW KEYS THE FROZEN TABLE ALREADY RESOLVES (would change a frozen resolution; use the candidate "
             "spelling as the display name, or alias to the frozen entity):\n  "
             + "\n  ".join(f"row {i}: {s!r} -> {c}" for i, s, c in bad))

# ---------- build the extended tables ----------
SRC = f"expansion review {review_date}"
ext_b = [dict(r) for r in frozen_b]
by_id = {r["canonical_id"]: r for r in ext_b}
for n in new_rows:
    al = []
    for s in n["forms"]:
        if fold(s) != fold(n["display"]) and fold(s) not in {fold(x) for x in al}:
            al.append(s)
    row = {"canonical_id": n["slug"], "display_name": n["display"], "class": n["cls"], "aliases": "|".join(al),
           "source": f"{SRC} ({n['how']}; AI draft from public HQ/ownership info)" + ("; brand+retailer" if n["kind"] == "both" else "")}
    ext_b.append(row)
    by_id[n["slug"]] = row
merged_existing, merged_new = 0, 0
for a in alias_ops:
    row = by_id[a["target"]]
    cur = [x for x in row["aliases"].split("|") if x.strip()]
    have = {fold(x) for x in cur} | {fold(row["display_name"])}
    for s in a["forms"]:
        if fold(s) not in have:
            cur.append(s)
            have.add(fold(s))
    row["aliases"] = "|".join(cur)
    tag = f"aliases extended, {SRC}"
    if tag not in row["source"]:
        row["source"] = row["source"] + "; " + tag
    if a["target"] in existing:
        merged_existing += 1
    else:
        merged_new += 1
ext_r = [dict(r) for r in frozen_r]
for n in new_rows:
    if n["kind"] in ("retailer", "both"):
        ext_r.append({"canonical_id": n["slug"], "display_name": n["display"], "class": n["cls"],
                      "source": f"{SRC} ({n['how']}; AI draft from public HQ/ownership info)"})

# ---------- 3. no folded name under two entities ----------
seen, dups = {}, []
for r in ext_b:
    for s in [r["display_name"]] + [x for x in r["aliases"].split("|") if x.strip()]:
        fs = fold(s)
        if fs in seen and seen[fs] != r["canonical_id"]:
            dups.append((fs, seen[fs], r["canonical_id"]))
        seen.setdefault(fs, r["canonical_id"])
ex_keys = {e["key"] for e in excl}
dups += [(k, seen[k], EXCLUDED) for k in ex_keys if k in seen]
if dups:
    sys.exit(f"FOLDED-NAME COLLISIONS: {dups[:20]}")
assert {r["canonical_id"] for r in ext_r} <= {r["canonical_id"] for r in ext_b}

EM = build_map(ext_b, ex_keys)

# ---------- 2b. frozen resolutions unchanged on every observed name ----------
def rl(v):
    return v if isinstance(v, list) else [x for x in str(v or "").splitlines() if x.strip()]
observed, files_used = set(), {}
for f in HUMAN:
    p = W / f
    if not p.exists():
        sys.exit(f"missing human label file {f}")
    d = json.load(open(p, encoding="utf-8"))
    for lab in d["labels"]:
        for fld in ("brands", "recommended", "retailers"):
            observed.update(str(x).strip() for x in rl(lab.get(fld)) if str(x).strip())
    files_used[f] = sha(p)
for f in MACHINE:
    p = W / f
    if not p.exists():
        sys.exit(f"missing machine extraction {f}")
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            ex = (json.loads(line).get("extraction") or {})
            for fld in ("brands", "recommended", "retailers"):
                observed.update(str(x).strip() for x in rl(ex.get(fld)) if str(x).strip())
    files_used[f] = sha(p)
changed = [(s, resolve(FM, s), resolve(EM, s)) for s in observed
           if resolve(FM, s) is not None and resolve(FM, s) != resolve(EM, s)]
if changed:
    sys.exit(f"FROZEN RESOLUTIONS CHANGED on {len(changed)} observed names: {changed[:20]}")
n_frozen_resolved = sum(1 for s in observed if resolve(FM, s) is not None)
n_newly = sum(1 for s in observed if resolve(FM, s) is None and resolve(EM, s) not in (None, EXCLUDED))
n_newly_excl = sum(1 for s in observed if resolve(FM, s) is None and resolve(EM, s) == EXCLUDED)
n_still = sum(1 for s in observed if resolve(EM, s) is None)

# ---------- 4. every candidate resolves to the authors' decision ----------
want = {}
for n in new_rows:
    want[n["key"]] = n["slug"]
for a in alias_ops:
    want[a["key"]] = a["target"]
for e in excl:
    want[e["key"]] = EXCLUDED
for u in unid:
    want[u["key"]] = None          # stays unresolved -> unclassifiable
wrong = []
for c in cand:
    for s in forms[c["surface_folded"]]:
        if resolve(EM, s) != want[c["surface_folded"]]:
            wrong.append((c["i"], s, resolve(EM, s), want[c["surface_folded"]]))
if wrong:
    sys.exit(f"CANDIDATES NOT RESOLVING TO THE DECISION: {wrong[:20]}")

# ---------- write ----------
def wcsv(path, rows, fields):
    with open(W / path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
wcsv("brand_aliases.expansion.csv", ext_b, ["canonical_id", "display_name", "class", "aliases", "source"])
wcsv("retailer_classification.expansion.csv", ext_r, ["canonical_id", "display_name", "class", "source"])
wcsv("alias_exclusions.expansion.csv",
     [{"surface_folded": e["key"], "surface": e["surface"], "note": e["note"], "source": f"{SRC} ({e['how']})"}
      for e in sorted(excl, key=lambda e: e["key"])], ["surface_folded", "surface", "note", "source"])
wcsv("alias_unidentified.expansion.csv",
     [{"surface_folded": u["key"], "surface": u["surface"], "note": u["note"], "source": f"{SRC} ({u['how']})"}
      for u in sorted(unid, key=lambda u: u["key"])], ["surface_folded", "surface", "note", "source"])
for f in GATES:
    assert sha(W / f) == GATES[f], f"{f} changed during the build"   # frozen files untouched

hashes = {f: sha(W / f) for f in ("brand_aliases.expansion.csv", "retailer_classification.expansion.csv",
                                  "alias_exclusions.expansion.csv", "alias_unidentified.expansion.csv")}
cc = Counter(n["cls"] for n in new_rows)
kc = Counter(n["kind"] for n in new_rows)
how = Counter([n["how"] for n in new_rows] + [a["how"] for a in alias_ops] + [e["how"] for e in excl]
              + [u["how"] for u in unid])
rec = {
    "task": "N1 expansion alias extension",
    "decisions_file": {"name": args.decisions, "sha256": sha(W / args.decisions), "exported_at": D["exported_at"],
                       "prefill": D.get("prefill", ""), "rows": len(dec),
                       "changed_from_prefill": D.get("changed_from_prefill"),
                       "completed_by_authors": D.get("completed_by_authors")},
    "inputs": {**{f: GATES[f] for f in GATES}, **files_used},
    "frozen_tables_untouched": True,
    "new_entities": len(new_rows), "new_entity_classes": dict(cc), "new_entity_kinds": dict(kc),
    "retailer_rows_added": sum(1 for n in new_rows if n["kind"] in ("retailer", "both")),
    "alias_merges": {"onto_frozen_entities": merged_existing, "onto_new_entities": merged_new},
    "exclusions": len(excl),
    "unidentified": len(unid),
    "decision_provenance": dict(how),
    "table_sizes": {"brand_aliases.expansion.csv": len(ext_b), "retailer_classification.expansion.csv": len(ext_r),
                    "frozen brand_aliases.csv": len(frozen_b), "frozen retailer_classification.csv": len(frozen_r)},
    "checks": {"new_keys_unresolved_under_frozen": True, "no_folded_collisions": True,
               "observed_names_checked": len(observed), "observed_frozen_resolved_unchanged": n_frozen_resolved,
               "observed_newly_resolved": n_newly, "observed_newly_excluded": n_newly_excl,
               "observed_still_unresolved": n_still, "candidates_resolve_to_decision": len(cand)},
    "outputs": hashes,
    "new": [{k: n[k] for k in ("slug", "display", "cls", "kind", "key")} for n in new_rows],
    "merges": [{k: a[k] for k in ("key", "target")} for a in alias_ops],
    "excluded": sorted(e["key"] for e in excl),
    "unidentified_names": sorted(u["key"] for u in unid),
}
with open(W / "EXPANSION-EXTENSION-RECORD.json", "w", encoding="utf-8", newline="\n") as f:
    json.dump(rec, f, ensure_ascii=False, indent=1)
print(f"new entities {len(new_rows)} {dict(cc)} kinds {dict(kc)}; retailer rows added {rec['retailer_rows_added']}")
print(f"alias merges: onto frozen {merged_existing}, onto new {merged_new}; exclusions {len(excl)}; "
      f"unidentified (left unclassifiable) {len(unid)}")
print(f"provenance: {dict(how)}")
print(f"observed names {len(observed):,}: frozen-resolved unchanged {n_frozen_resolved:,} | newly resolved {n_newly:,} | "
      f"newly excluded {n_newly_excl:,} | still unresolved {n_still:,}")
for f, h in hashes.items():
    print(f"{f}  sha256 {h}")
print("EXPANSION-EXTENSION-RECORD.json written; frozen tables byte-identical")
