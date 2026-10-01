#!/usr/bin/env python3
"""convert_alias_decisions_csv.py — N1: turn the authors' spreadsheet of expansion name decisions
(EXPANSION-ALIAS-DECISIONS.csv — the review page stalled in their browser, so the review was completed in a
spreadsheet with one row per candidate) into EXPANSION-ALIAS-DECISIONS.json, the exact format the review
page exports and build_expansion_extension.py reads.

Nothing is decided here. Each row's decision is copied; the only transformations are the page's own:
labels map to the page's kinds (Brand -> brand, Retailer -> retailer, Brand + retailer -> both,
Alias of existing -> alias, Not a brand -> exclude, Unidentified -> unidentified); fields that do not
belong to a row's kind are cleared, exactly as the page's export clears them; and the draft (prefill)
block and the changed/completed flags are computed exactly as the page computes them. The conversion
refuses to write anything if the spreadsheet does not match this review's candidate list row for row, if a
label is unknown, or if any row fails the checks the page runs before export (class present; canonical id
well formed, new and unique; display name not already a name in the frozen table; alias target an existing
or new id) — it lists the rows to fix instead.

Authors' corrections given after delivery (e.g. an answer to a question about a row) are applied from a
separate file (--corrections, a JSON list of {"i", "surface", "set": {...}, "reason", "given"}) so the
spreadsheet itself stays exactly as received; every correction is copied into the output.

Usage (study root):  python convert_alias_decisions_csv.py EXPANSION-ALIAS-DECISIONS.csv --date YYYY-MM-DD [--corrections FILE]
(--date is the day the authors delivered the spreadsheet; the output carries that date and no clock time,
so the conversion is byte-reproducible on any machine.)
"""
import csv, hashlib, io, json, re, sys, unicodedata
from pathlib import Path

W = Path(".")
GATES = {
    "EXPANSION-ALIAS-CANDIDATES.csv": "5048e8388266b4a1d0058e8dae24b1fe4f5642b20e451c99c67997bdbc285805",
    "brand_aliases.csv": "0b7bd5e8355c919300129b6ba96008d5cb2d95a691aaf759a1e82823ee2b00ea",
}
PREFILL_NOTE = ("rows pre-filled 2026-09-26 by Claude (AI assistant) from public headquarters/ownership "
                "information and the registered precedents, with no frequency, arm or model information; "
                "reviewed and finalised by the authors")
KMAP = {"brand": "brand", "retailer": "retailer", "brand + retailer": "both", "alias of existing": "alias",
        "not a brand": "exclude", "not a brand (exclude)": "exclude", "unidentified": "unidentified"}
SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

for f, want in GATES.items():
    if sha(W / f) != want:
        sys.exit(f"INPUT GATE: {f} is not the registered file")
import argparse
ap = argparse.ArgumentParser()
ap.add_argument("csv", nargs="?", default="EXPANSION-ALIAS-DECISIONS.csv")
ap.add_argument("--date", required=True)
ap.add_argument("--corrections", default=None)
args = ap.parse_args()
if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
    sys.exit("--date must be YYYY-MM-DD")
src = Path(args.csv)
src_sha = sha(src)
rows = list(csv.DictReader(io.StringIO(src.read_bytes().decode("utf-8-sig"))))
cand = list(csv.DictReader(open(W / "EXPANSION-ALIAS-CANDIDATES.csv", encoding="utf-8")))

def fold(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s.strip())
    return s.casefold().strip()

frozen = list(csv.DictReader(open(W / "brand_aliases.csv", encoding="utf-8")))
existing = {r["canonical_id"] for r in frozen}
amap = {}
for r in frozen:
    amap[fold(r["display_name"])] = r["canonical_id"]
    for al in r["aliases"].split("|"):
        if al.strip():
            amap[fold(al)] = r["canonical_id"]

def frozen_hit(s):
    fs = fold(s)
    if fs in amap:
        return amap[fs]
    t = fs.split()
    for n in (3, 2, 1):
        if len(t) >= n and " ".join(t[:n]) in amap:
            return amap[" ".join(t[:n])]
    return None

need = ["No", "Name", "Decision", "Class", "ID", "Alias of", "Display name"]
if not rows or any(k not in rows[0] for k in need):
    sys.exit(f"the spreadsheet needs the columns {need}")
if len(rows) != len(cand):
    sys.exit(f"the spreadsheet has {len(rows)} rows; the review has {len(cand)}")

problems, fin = [], []
for r, c in zip(rows, cand):
    i = int(c["i"])
    if r["No"].strip() != str(i) or r["Name"] != c["example_surface"]:
        problems.append(f"row {r['No']}: does not match candidate {i} ({c['example_surface']!r})")
        continue
    lab = r["Decision"].strip().lower()
    if lab not in KMAP:
        problems.append(f"row {i} ({r['Name']}): unknown decision {r['Decision']!r}")
        continue
    k = KMAP[lab]
    d = {"kind": k, "cls": "", "target": "", "slug": "", "display": "", "note": ""}
    if k in ("brand", "retailer", "both"):
        d["cls"] = r["Class"].strip().lower()
        d["slug"] = r["ID"].strip()
        d["display"] = r["Display name"].strip()
    elif k == "alias":
        d["target"] = r["Alias of"].strip()
    fin.append((i, c, d, r))

corrections = json.load(open(args.corrections, encoding="utf-8")) if args.corrections else []
for cor in corrections:
    hit = [x for x in fin if x[0] == cor["i"]]
    if not hit or hit[0][1]["example_surface"] != cor["surface"]:
        sys.exit(f"correction for row {cor['i']} does not match the candidate list")
    d = hit[0][2]
    for k, v in cor["set"].items():
        if k not in ("kind", "cls", "target", "slug", "display"):
            sys.exit(f"correction for row {cor['i']}: field {k!r} cannot be corrected")
        d[k] = v
    if d["kind"] not in ("brand", "retailer", "both"):
        d["cls"], d["slug"], d["display"] = "", "", ""
    if d["kind"] != "alias":
        d["target"] = ""

slugs = {}
for i, c, d, r in fin:
    if d["kind"] in ("brand", "retailer", "both"):
        slugs[d["slug"]] = slugs.get(d["slug"], 0) + 1
for i, c, d, r in fin:
    nm = c["example_surface"]
    if d["kind"] in ("brand", "retailer", "both"):
        if d["cls"] not in ("local", "global", "ambiguous"):
            problems.append(f"row {i} ({nm}): class must be local, global or ambiguous (got {r['Class']!r})")
        if not SLUG.fullmatch(d["slug"]):
            problems.append(f"row {i} ({nm}): ID {d['slug']!r} must be lower-case letters/digits joined by hyphens")
        elif d["slug"] in existing:
            problems.append(f"row {i} ({nm}): ID {d['slug']!r} already exists in the frozen table — use Alias of existing")
        elif slugs[d["slug"]] > 1:
            problems.append(f"row {i} ({nm}): ID {d['slug']!r} is used on more than one row")
        if not d["display"]:
            problems.append(f"row {i} ({nm}): display name is empty")
        elif frozen_hit(d["display"]):
            problems.append(f"row {i} ({nm}): display name {d['display']!r} is already a name of {frozen_hit(d['display'])!r}")
    elif d["kind"] == "alias":
        if not (d["target"] in existing or slugs.get(d["target"])):
            problems.append(f"row {i} ({nm}): alias target {d['target']!r} is not an existing or new ID")

# no folded name may end up naming two entities (the extension build's own check, run here first)
owner = {}
for r0 in frozen:
    for s0 in [r0["display_name"]] + [a for a in r0["aliases"].split("|") if a.strip()]:
        owner.setdefault(fold(s0), r0["canonical_id"])
claims = []
for i, c, d, r in fin:
    forms = [x for x in c["all_surfaces"].split(" | ") if x.strip()]
    if d["kind"] in ("brand", "retailer", "both"):
        claims += [(fold(x), d["slug"], i) for x in forms + [d["display"]]]
    elif d["kind"] == "alias":
        claims += [(fold(x), d["target"], i) for x in forms]
seen_claim = {}
for fs, ent, i in claims:
    prev = owner.get(fs)
    if prev is not None and prev != ent:
        problems.append(f"row {i} ({cand[i]['example_surface']}): the name {fs!r} would belong to both {prev!r} and {ent!r}")
    elif fs in seen_claim and seen_claim[fs][0] != ent:
        j = seen_claim[fs][1]
        problems.append(f"rows {j} ({cand[j]['example_surface']}) and {i} ({cand[i]['example_surface']}): the name {fs!r} "
                        f"is given to two entities, {seen_claim[fs][0]!r} and {ent!r} — same entity (make one an alias) "
                        f"or different (change the display name)?")
    seen_claim.setdefault(fs, (ent, i))

if problems:
    print(f"{len(problems)} row(s) to fix — nothing written:")
    for p in problems:
        print("  " + p)
    sys.exit(1)

out_rows = []
for i, c, d, r in fin:
    pf = {"kind": c["prefill_kind"], "cls": c["prefill_class"], "id": c["prefill_id"],
          "display": c["prefill_display"], "note": c["prefill_note"], "check": c["check"] == "yes"}
    brandish = d["kind"] in ("brand", "retailer", "both")
    changed = (d["kind"] != pf["kind"]) or ((d["target"] != pf["id"]) if d["kind"] == "alias" else
                                            (((bool(pf["cls"]) and d["cls"] != pf["cls"]) or d["slug"] != pf["id"]) if brandish else False))
    completed = (not changed) and brandish and not pf["cls"] and bool(d["cls"])
    out_rows.append({"i": i, "surface": c["example_surface"], "surface_folded": c["surface_folded"], **d,
                     "prefill": pf, "changed_from_prefill": changed, "completed_by_authors": completed})
out = {"task": "N1 expansion alias decisions", "prefill": PREFILL_NOTE,
       "exported_at": args.date,
       "source": f"converted from the authors' spreadsheet {src.name} (sha256 {src_sha}) by convert_alias_decisions_csv.py",
       "corrections": corrections,
       "n": len(out_rows), "changed_from_prefill": sum(r["changed_from_prefill"] for r in out_rows),
       "completed_by_authors": sum(r["completed_by_authors"] for r in out_rows), "decisions": out_rows}
dst = W / "EXPANSION-ALIAS-DECISIONS.json"
with open(dst, "w", encoding="utf-8", newline="\n") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
from collections import Counter
print(f"spreadsheet sha256 {src_sha}")
print(f"wrote {dst}: {out['n']} rows; kinds {dict(Counter(r['kind'] for r in out_rows))}; "
      f"changed from draft {out['changed_from_prefill']}, completed by the authors {out['completed_by_authors']}")
print(f"{dst}  sha256 {sha(dst)}")
