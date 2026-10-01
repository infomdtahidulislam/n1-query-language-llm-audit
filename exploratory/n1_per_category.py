#!/usr/bin/env python3
"""n1_per_category.py — N1: per-category exploratory breakdown (declared in the post-freeze record of 28 Sep 2026).

Descriptive only. On the machine-extracted layer (all 250 queries, 25 per category) and its F.6 primary analysis set
(answers neither refused nor degenerate that carry an extraction), for every subject model:
  (i)  RQ2 local-brand share of classified brand mentions per category and arm (en, bn, bl): the per-answer share,
       averaged over the repetitions of the query-by-model-by-arm cell, then averaged over the category's queries that
       hold a classified mention — the registered query-level estimand of F.3, restricted to one category;
  (ii) RQ1 excess brand-set divergence Δ (F.2, Jaccard) per category and contrast (bn–en, bl–en, bn–bl): the per-query Δ
       averaged over the category's queries with at least two answers in both arms.
Each value carries a 95% percentile interval from 10,000 cluster-bootstrap resamples of the category's own queries
(seed 20260930 + the category's index in the alphabetical order of category names). No test, no adjustment, no contrast
is tested; nothing here is a result of record. Exploratory under F.6; the machine layer's measured brand-set accuracy
against the rater consensus is 0.8221 (E.6, record 9).

Mechanism: executes the registered n1_analysis.py (refused unless its sha256 is 174bae3e…) up to its results block, so
every input gate, layer, filter and per-query function is the registered run's, then aggregates the per-query values by
category. Self-test first: the same per-query values averaged over all 250 queries must reproduce the registered
machine-layer secondary results (secondary/machine_RQ2 arm shares and secondary/machine_RQ1 mean Δ, ANALYSIS-RESULTS.json
d12e64e5…) exactly; --selftest-only stops there and computes no category value.

Usage (study root):  python exploratory/n1_per_category.py  ->  exploratory/PER-CATEGORY-EXPLORATORY.json / .md
"""
import argparse, hashlib, json, sys, datetime
from collections import defaultdict
from pathlib import Path
import numpy as np

_ap = argparse.ArgumentParser()
_ap.add_argument("root", nargs="?", default=".")
_ap.add_argument("--selftest-only", action="store_true")
_a = _ap.parse_args()
ROOT = Path(_a.root)
OUT_DIR = ROOT / "exploratory"
REG = ROOT / "n1_analysis.py"
REG_SHA = "174bae3e3c8ebb8e219ff832c8105aa7373f17db41e837be738e7d2bb6f8fb7e"
RES_SHA = "d12e64e5e8ebcb0f492d0608bed691315dd64ffc2e539b8d6fb7d34f3fd9903c"
NB, SEED0 = 10000, 20260930
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

src = REG.read_text(encoding="utf-8")
if hashlib.sha256(src.encode("utf-8")).hexdigest() != REG_SHA:
    raise SystemExit("n1_analysis.py is not the registered file")
if sha(ROOT / "ANALYSIS-RESULTS.json") != RES_SHA:
    raise SystemExit("ANALYSIS-RESULTS.json is not the registered run of record")

cut = src.index('\nR = {"meta": {}, "primary": {}')
sys.argv = ["n1_analysis.py", "--root", str(ROOT), "--out", "PER-CATEGORY-unused"]
G = {"__name__": "n1_analysis_defs", "__file__": str(REG)}
exec(compile(src[:cut], str(REG), "exec"), G)
M, P, CAT, MODELS, ARMS3, C3 = G["M"], G["P"], G["CAT"], G["MODELS"], G["ARMS3"], G["C3"]
cells, excess, jaccard, pct, Boot = G["cells"], G["excess"], G["jaccard"], G["pct"], G["Boot"]
per_answer_mentions, brand_items = G["per_answer_mentions"], G["brand_items"]

def cell_means(rows, val, filt):                # identical to the registered F.9 helper (defined after the cut)
    d = defaultdict(list)
    for r in rows:
        if filt(r):
            v = val(r)
            if v is not None:
                d[(r["model"], r["query"], r["arm"])].append(v)
    return {k: float(np.mean(v)) for k, v in d.items()}

def local_share_answer(r):                      # identical to the registered F.9 helper (defined after the cut)
    loc, n, _, _ = per_answer_mentions(r, {"items": brand_items()})
    return (loc / n) if n else None

# ---- per-query values, exactly as the registered estimators form them -------------------------------------
share_cell = cell_means(M, local_share_answer, P)          # (model, query, arm) -> mean per-answer share over reps
brand_cells = cells(M, "brands", P)                        # (model, query, arm) -> list of brand sets
queries = sorted({r["query"] for r in M})
delta_q = {}                                               # (model, a, b) -> {query: Δ}
for m in MODELS:
    for a, b in C3:
        d = {}
        for q in queries:
            v = excess(brand_cells.get((m, q, a), []), brand_cells.get((m, q, b), []), jaccard)
            if v is not None:
                d[q] = v
        delta_q[(m, a, b)] = d
share_q = {(m, a): {q: v for (mm, q, aa), v in share_cell.items() if mm == m and aa == a} for m in MODELS for a in ARMS3}

# ---- self-test: all-query means reproduce the registered machine-layer secondary results exactly -----------
with open(ROOT / "ANALYSIS-RESULTS.json", encoding="utf-8") as fh:
    REC = json.load(fh)
ok = True
for m in MODELS:
    for a in ARMS3:
        reg = REC["secondary"]["machine_RQ2"]["results"][m]["arms"][a]
        mine = float(np.mean(list(share_q[(m, a)].values())))
        if reg["share"] != mine or reg["n_query"] != len(share_q[(m, a)]):
            ok = False; print("SELF-TEST MISMATCH RQ2", m, a, reg["share"], mine, reg["n_query"], len(share_q[(m, a)]))
    for a, b in C3:
        reg = REC["secondary"]["machine_RQ1"]["results"][f"{m}|{a}-{b}"]
        vals = np.array(list(delta_q[(m, a, b)].values()))
        if reg["mean_delta"] != float(vals.mean()) or reg["n_query"] != len(vals):
            ok = False; print("SELF-TEST MISMATCH RQ1", m, a, b, reg["mean_delta"], float(vals.mean()), reg["n_query"], len(vals))
if not ok:
    raise SystemExit("self-test failed: the per-query values do not reproduce the registered machine-layer results")
print("self-test OK: all-query means reproduce secondary/machine_RQ2 and secondary/machine_RQ1 exactly "
      f"({len(queries)} queries; {len(M)} machine-layer answers)")
if _a.selftest_only:
    sys.exit(0)

# ---- per-category aggregation ------------------------------------------------------------------------------
cats = sorted(set(CAT.values()))
assert len(cats) == 10 and all(sum(1 for q in CAT if CAT[q] == c) == 25 for c in cats)
boots = {c: Boot({q for q in queries if CAT[q] == c}, NB, SEED0 + i) for i, c in enumerate(cats)}
res = {"local_share": {}, "excess_divergence": {}}
for c in cats:
    bt = boots[c]
    for m in MODELS:
        for a in ARMS3:
            d = {q: v for q, v in share_q[(m, a)].items() if CAT[q] == c}
            reps, dropped = bt.mean(d) if d else (np.array([]), 0)
            res["local_share"][f"{c}|{m}|{a}"] = {"category": c, "model": m, "arm": a, "n_query": len(d),
                                                  "mean": float(np.mean(list(d.values()))) if d else None,
                                                  "ci": pct(reps), "boot_dropped": dropped}
        for a, b in C3:
            d = {q: v for q, v in delta_q[(m, a, b)].items() if CAT[q] == c}
            reps, dropped = bt.mean(d) if d else (np.array([]), 0)
            res["excess_divergence"][f"{c}|{m}|{a}-{b}"] = {"category": c, "model": m, "contrast": f"{a}-{b}",
                                                            "n_query": len(d),
                                                            "mean_delta": float(np.mean(list(d.values()))) if d else None,
                                                            "ci": pct(reps), "boot_dropped": dropped}

meta = {
    "task": "N1 per-category exploratory breakdown (F.6 exploratory; descriptive only, no test, no adjustment)",
    "layer": "machine-extracted layer, F.6 primary analysis set; brand-set F1 against the rater consensus 0.8221 (E.6)",
    "estimands": {"local_share": "per-answer local share of classified brand mentions (ambiguous and unclassifiable excluded), "
                                 "averaged over the reps of each query x model x arm cell, then over the category's queries with a "
                                 "classified mention (registered F.3 query-level estimand, restricted to the category)",
                  "excess_divergence": "per-query excess brand-set divergence Δ (F.2, Jaccard; ≥ 2 answers per arm), averaged over "
                                       "the category's queries"},
    "bootstrap": {"resamples": NB, "seeds": {c: SEED0 + i for i, c in enumerate(cats)},
                  "note": "cluster resampling of the category's own 25 queries; 95% percentile intervals"},
    "n1_analysis_sha256": REG_SHA, "analysis_results_sha256": RES_SHA, "script_sha256": sha(Path(__file__)),
    "inputs": G["inputs"], "categories": cats, "models": MODELS, "arms": ARMS3, "contrasts": [f"{a}-{b}" for a, b in C3],
    "run_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "status": "exploratory; not a result of record; not part of S3 unless a reviewer asks (post-freeze records of 28 Sep 2026)",
}
OUT_DIR.mkdir(exist_ok=True)
with open(OUT_DIR / "PER-CATEGORY-EXPLORATORY.json", "w", encoding="utf-8") as fh:
    json.dump({"meta": meta, "results": res}, fh, indent=1, ensure_ascii=False)

def f3(x):
    return "–" if x is None else f"{x:.3f}"
def ci(c):
    return "–" if c[0] is None else f"[{c[0]:.3f}, {c[1]:.3f}]"
L = ["# N1 — per-category exploratory breakdown (machine-extracted layer; descriptive only; not a result of record)", "",
     f"Registered code n1_analysis.py `{REG_SHA[:12]}…` executed up to its results block; this script `{meta['script_sha256'][:12]}…`; "
     f"run of record ANALYSIS-RESULTS.json `{RES_SHA[:12]}…` reproduced by the self-test. Machine layer, F.6 primary set, "
     f"25 queries per category; 10,000 cluster-bootstrap resamples of the category's queries (seed {SEED0} + category index). "
     "Query-level means with 95% percentile intervals; no test, no adjustment. Exploratory under F.6; the layer's brand-set "
     "accuracy against the rater consensus is 0.8221.", ""]
for m in MODELS:
    L += [f"## {m}", "", "### Local-brand share by category and arm", "",
          "| category | en (n) | bn (n) | bl (n) |", "|---|---|---|---|"]
    for c in cats:
        row = [c]
        for a in ARMS3:
            e = res["local_share"][f"{c}|{m}|{a}"]
            row.append(f"{f3(e['mean'])} {ci(e['ci'])} ({e['n_query']})")
        L.append("| " + " | ".join(row) + " |")
    L += ["", "### Excess brand-set divergence Δ by category and contrast", "",
          "| category | bn–en (n) | bl–en (n) | bn–bl (n) |", "|---|---|---|---|"]
    for c in cats:
        row = [c]
        for a, b in C3:
            e = res["excess_divergence"][f"{c}|{m}|{a}-{b}"]
            row.append(f"{f3(e['mean_delta'])} {ci(e['ci'])} ({e['n_query']})")
        L.append("| " + " | ".join(row) + " |")
    L.append("")
(OUT_DIR / "PER-CATEGORY-EXPLORATORY.md").write_text("\n".join(L), encoding="utf-8")
print("written:", OUT_DIR / "PER-CATEGORY-EXPLORATORY.json", OUT_DIR / "PER-CATEGORY-EXPLORATORY.md")
