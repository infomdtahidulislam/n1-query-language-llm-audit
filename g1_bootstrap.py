#!/usr/bin/env python3
"""G.1 repetition calibration (N1, 13 Sep 2026) — registered rule, mechanical.

Within each model×arm cell (6 calibration queries × 3 reps), bootstrap the projected SE of
the cell's local-brand share at r=5: per bootstrap draw, resample 5 reps per query with
replacement from that query's observed reps, take the cell mean of per-answer local shares,
SD over B=2000 draws = projected SE. Median over the 18 cells > 0.05 -> r=7, else r=5.

Per D.3 / Appendix C / F.3: share per answer = local/(local+global) over BRAND mentions,
ambiguous excluded (primary), unknown (not in the frozen table) excluded and counted;
answers with an empty denominator carry no share and drop out of that cell mean.
Analysis set: all non-refused, non-degenerate answers (F.6) — in this pilot, all 324.
Seed 20260913. Frozen inputs: brand_aliases.csv (v0.40), pilot.primary.jsonl.
"""
import csv, json, random, re, statistics, unicodedata
from collections import defaultdict

U = "/mnt/user-data/uploads/New Experiment/runs"
SEED, B, R_TARGET, THRESH = 20260913, 2000, 5, 0.05

def fold(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s.strip())      # trailing parenthetical acronym
    return re.sub(r"\s+", " ", s).casefold()

cls = {}
for r in csv.DictReader(open("brand_aliases.csv", encoding="utf-8")):
    for form in {r["canonical_id"], r["display_name"], *filter(None, r["aliases"].split("|"))}:
        cls[fold(form)] = r["class"]

final = [json.loads(l) for l in open(f"{U}/coded/pilot.final.jsonl", encoding="utf-8") if l.strip()]
ext = {json.loads(l)["subject_key"]: (json.loads(l).get("extraction") or {})
       for l in open(f"{U}/extracted/pilot.primary.jsonl", encoding="utf-8") if l.strip()}
assert len(final) == 324 and len(ext) == 324

unknown = defaultdict(int)
shares = {}          # key -> share or None
meta = {}
for row in final:
    k = row["key"]
    if row["outcome"] in ("refused", "degenerate"):     # F.6 exclusion (none in this pilot)
        continue
    n_loc = n_glob = 0
    for b in (ext.get(k, {}).get("brands") or []):
        c = cls.get(fold(str(b)))
        if c == "local": n_loc += 1
        elif c == "global": n_glob += 1
        elif c == "ambiguous": pass                     # excluded (primary, C.5/F.3)
        else: unknown[str(b)] += 1                      # not in frozen table: excluded, counted
    shares[k] = (n_loc / (n_loc + n_glob)) if (n_loc + n_glob) else None
    meta[k] = (row["model_id"], row["arm"], row["query_id"], row["rep"])

# cells: model×arm -> query -> [shares by rep]
cells = defaultdict(lambda: defaultdict(list))
for k, s in shares.items():
    m, a, q, _ = meta[k]
    cells[(m, a)][q].append(s)

rng = random.Random(SEED)
results = []
for (m, a), qmap in sorted(cells.items()):
    boots = []
    for _ in range(B):
        vals = []
        for q, reps in qmap.items():
            draw = [reps[rng.randrange(len(reps))] for _ in range(R_TARGET)]
            vals.extend(v for v in draw if v is not None)
        boots.append(sum(vals) / len(vals) if vals else 0.0)
    mu = sum(boots) / B
    se = statistics.pstdev(boots)
    results.append(((m, a), se, mu))

ses = sorted(se for _, se, _ in results)
med = statistics.median(ses)
r_decided = 7 if med > THRESH else 5

print(f"G.1 bootstrap — B={B}, seed {SEED}, projected r={R_TARGET}, threshold {THRESH}")
print(f"{'cell':34}{'proj SE':>9}{'mean share':>12}")
for (m, a), se, mu in results:
    print(f"  {m:24}{a:8}{se:9.4f}{mu:12.4f}")
print(f"\ncells: {len(results)} | median projected SE = {med:.4f}"
      f" | rule: median > {THRESH} -> r=7 else r=5")
print(f"DECISION: r = {r_decided}")
print(f"\nanswers with no classifiable brand (share undefined, dropped from cell means): "
      f"{sum(1 for s in shares.values() if s is None)}/324")
if unknown:
    top = sorted(unknown.items(), key=lambda x: -x[1])[:10]
    print("unknown surface forms excluded (C.2 post-hoc addable, documented):", top)
else:
    print("unknown surface forms: NONE — every extracted brand resolved against the frozen table")
