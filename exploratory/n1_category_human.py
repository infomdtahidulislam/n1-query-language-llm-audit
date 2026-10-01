#!/usr/bin/env python3
"""n1_category_human.py — N1: local-brand share by category and arm on the human-labelled layer (declared in the
post-freeze record of 28 Sep 2026). Descriptive only: no test, no adjustment; outside the results of record. The
machine-layer table of the earlier per-category records is unchanged and is used here only for the comparison sentence.

For each of the ten categories (8 sampled queries each), per subject model and as the equally weighted six-model mean:
the local-brand share of each arm (en, bn, bl) with the number of eligible queries; the bn–en, bl–en and bn–bl paired
differences in percentage points with eligible-query counts; and the differences between the arm means in percentage
points (bn mean − en mean, bl mean − en mean, bn mean − bl mean), the quantities comparable with the machine-layer
per-category values. Run-of-record F.6 primary set (human labels) and tables. Intervals: 95% percentiles from 10,000
resamples of each category's eight query IDs (seeds 20261011 … 20261020 in the alphabetical order of the categories),
reused across models, arms and contrasts; the six-model mean computed within each replicate and NA unless all six model
estimates are defined; undefined replicates NA.
Self-test (registered values only): pooling the ten categories reproduces the registered human-layer RQ2 arm shares,
query counts and paired differences exactly; --selftest-only stops there.

Usage (study root):  python exploratory/n1_category_human.py  ->  exploratory/PER-CATEGORY-HUMAN-EXPLORATORY.json / .md
"""
import argparse, datetime, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from n1_review_common import load, cell_means, make_local_share_answer, share_by_query, paired, Frame, six_model_mean, sha, fmt, fmt_ci, NB

ap = argparse.ArgumentParser(); ap.add_argument("root", nargs="?", default="."); ap.add_argument("--selftest-only", action="store_true")
A = ap.parse_args(); ROOT = Path(A.root); OUT = ROOT / "exploratory"
G = load(ROOT)
H, P, CAT, MODELS, ARMS3, C3, REC = G["H"], G["P"], G["CAT"], G["MODELS"], G["ARMS3"], G["C3"], G["REC"]
SEED0 = 20261011
rows = [r for r in H if r["arm"] in ARMS3]
cm = cell_means(rows, make_local_share_answer(G), P)
hq = sorted({r["query"] for r in rows})
cats = sorted(set(CAT[q] for q in hq))
assert len(cats) == 10 and all(sum(1 for q in hq if CAT[q] == c) == 8 for c in cats)
SEEDS = {c: SEED0 + i for i, c in enumerate(cats)}

# ---- self-test: pooled over categories = the registered human-layer RQ2 -----------------------------------------
reg = REC["primary"]["RQ2_local_share"]["results"]
for m in MODELS:
    sq = {a: share_by_query(cm, m, a) for a in ARMS3}
    for a in ARMS3:
        assert reg[m]["arms"][a]["n_query"] == len(sq[a]) and reg[m]["arms"][a]["share"] == float(np.mean(list(sq[a].values())))
    for a, b in C3:
        d = paired(sq[a], sq[b])
        assert reg[m]["contrasts"][f"{a}-{b}"]["n_query"] == len(d) and reg[m]["contrasts"][f"{a}-{b}"]["diff"] == float(np.mean(list(d.values())))
print("self-test OK: pooled over the ten categories, the human layer reproduces the registered RQ2 arm shares, query counts and paired differences exactly")
if A.selftest_only:
    sys.exit(0)

# ---- estimates ----------------------------------------------------------------------------------------------------
res = {}
for c in cats:
    fr = Frame([q for q in hq if CAT[q] == c], SEEDS[c], NB)
    res[c] = {"frame": {"n_query": len(fr.q), "seed": fr.seed, "query_ids": fr.q}, "models": {}, "six_model_mean": {"arms": {}, "contrasts": {}, "arm_mean_differences": {}}}
    keep = {"arms": {a: ([], [], []) for a in ARMS3}, "contrasts": {f"{a}-{b}": ([], [], []) for a, b in C3}, "arm_mean_differences": {f"{a}-{b}": ([], [], []) for a, b in C3}}
    for m in MODELS:
        sq = {a: {q: v for q, v in share_by_query(cm, m, a).items() if CAT[q] == c} for a in ARMS3}
        e = {"arms": {}, "contrasts": {}, "arm_mean_differences": {}}
        arm_reps = {}
        for a in ARMS3:
            st, reps = fr.stat(sq[a]); e["arms"][a] = st; arm_reps[a] = reps
            keep["arms"][a][0].append(st["estimate"]); keep["arms"][a][1].append(reps); keep["arms"][a][2].append(st["n_query"])
        for a, b in C3:
            st, reps = fr.stat(paired(sq[a], sq[b]), scale=100.0); e["contrasts"][f"{a}-{b}"] = st
            keep["contrasts"][f"{a}-{b}"][0].append(st["estimate"]); keep["contrasts"][f"{a}-{b}"][1].append(reps); keep["contrasts"][f"{a}-{b}"][2].append(st["n_query"])
            # difference between the arm means (pp): point from the arm means, replicate-wise from the arm replicates
            pa, pb = e["arms"][a]["estimate"], e["arms"][b]["estimate"]
            point = None if pa is None or pb is None else (pa - pb) * 100.0
            reps_d = (arm_reps[a] - arm_reps[b]) * 100.0
            nq = min(e["arms"][a]["n_query"], e["arms"][b]["n_query"])
            ci, nrep = Frame.ci(reps_d, nq if point is not None else 0)
            e["arm_mean_differences"][f"{a}-{b}"] = {"estimate": point, "ci": ci, "n_defined_replicates": nrep, "n_query_arms": [e["arms"][a]["n_query"], e["arms"][b]["n_query"]]}
            keep["arm_mean_differences"][f"{a}-{b}"][0].append(point); keep["arm_mean_differences"][f"{a}-{b}"][1].append(reps_d); keep["arm_mean_differences"][f"{a}-{b}"][2].append(nq)
        res[c]["models"][m] = e
    for kind in keep:
        for k, (pts, rl, ns) in keep[kind].items():
            st, _ = six_model_mean(pts, rl, ns)
            res[c]["six_model_mean"][kind][k] = st

# ---- comparison with the machine-layer table of the earlier records --------------------------------------------
mach = json.loads((OUT / "PER-CATEGORY-EXPLORATORY.json").read_text(encoding="utf-8"))
assert sha(OUT / "PER-CATEGORY-EXPLORATORY.json").startswith("04dbaefc9a1d70fc")
mm = mach["results"]["local_share"]
mach_diff = {c: float(np.mean([mm[f"{c}|{m}|bn"]["mean"] - mm[f"{c}|{m}|en"]["mean"] for m in MODELS])) * 100.0 for c in cats}
hum_diff = {c: res[c]["six_model_mean"]["arm_mean_differences"]["bn-en"]["estimate"] for c in cats}
rank_m = sorted(cats, key=lambda c: -mach_diff[c]); rank_h = sorted([c for c in cats if hum_diff[c] is not None], key=lambda c: -hum_diff[c])
common = [c for c in cats if hum_diff[c] is not None]
top3 = sorted(set(rank_m[:3]) & set(rank_h[:3])); bottom4 = sorted(set(rank_m[-4:]) & set(rank_h[-4:]))
comparison = {"machine_six_model_bn_minus_en_pp": mach_diff, "human_six_model_bn_minus_en_pp": hum_diff, "machine_ranking": rank_m, "human_ranking": rank_h,
              "n_categories_compared": len(common), "shared_top3": top3, "shared_bottom4": bottom4}

meta = {"task": "local-brand share by category and arm on the human-labelled layer (F.6 exploratory; descriptive, no test; outside the results of record)",
        "layer": "human-labelled layer, F.6 primary set by the human labels, arms en/bn/bl; run-of-record tables",
        "bootstrap": {"resamples": NB, "seeds": SEEDS, "rule": "each category's eight query IDs resampled with replacement; resamples reused across models, arms and contrasts; six-model mean within each replicate, NA unless all six defined; undefined replicates NA; no interval below two contributing queries"},
        "inputs": G["inputs"], "script_sha256": sha(Path(__file__)), "common_sha256": sha(Path(__file__).with_name("n1_review_common.py")),
        "machine_table_sha256": sha(OUT / "PER-CATEGORY-EXPLORATORY.json"),
        "run_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
json.dump({"meta": meta, "results": res, "comparison_with_machine_layer": comparison}, open(OUT / "PER-CATEGORY-HUMAN-EXPLORATORY.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)

L_ = ["# N1 — local-brand share by category and arm, human-labelled layer (descriptive only; not a result of record)", "",
      f"Eight sampled queries per category; F.6 primary set (human labels); 95% percentile intervals from {NB:,} resamples of the category's query IDs (seeds {SEED0}–{SEED0 + 9}); six-model mean = equally weighted, NA unless all six defined; no test.", ""]
for c in cats:
    L_ += [f"## {c} (seed {SEEDS[c]})", "", "| model | en (n) | bn (n) | bl (n) | bn–en paired pp (n) | bl–en paired pp (n) | bn–bl paired pp (n) | bn−en arm means pp | bl−en arm means pp | bn−bl arm means pp |", "|---|---|---|---|---|---|---|---|---|---|"]
    for m in MODELS + ["six-model mean"]:
        e = res[c]["models"][m] if m in MODELS else res[c]["six_model_mean"]
        cells = [f"{fmt(e['arms'][a]['estimate'])} {fmt_ci(e['arms'][a]['ci'])}" + (f" ({e['arms'][a]['n_query']})" if m in MODELS else "") for a in ARMS3]
        cells += [f"{fmt(e['contrasts'][k]['estimate'], 1)} {fmt_ci(e['contrasts'][k]['ci'], 1)}" + (f" ({e['contrasts'][k]['n_query']})" if m in MODELS else "") for k in ("bn-en", "bl-en", "bn-bl")]
        cells += [f"{fmt(e['arm_mean_differences'][k]['estimate'], 1)} {fmt_ci(e['arm_mean_differences'][k]['ci'], 1)}" for k in ("bn-en", "bl-en", "bn-bl")]
        L_.append(f"| {m} | " + " | ".join(cells) + " |")
    L_.append("")
L_ += ["## Comparison with the machine-layer table (six-model bn − en arm-mean difference, pp)", "", "| category | machine layer | human layer |", "|---|---|---|"]
for c in cats:
    L_.append(f"| {c} | {mach_diff[c]:+.1f} | {fmt(hum_diff[c], 1)} |")
L_ += ["", f"Machine ranking: {' > '.join(rank_m)}", f"Human ranking: {' > '.join(rank_h)}", f"Shared top three: {top3}; shared bottom four: {bottom4} ({len(common)} categories compared)"]
(OUT / "PER-CATEGORY-HUMAN-EXPLORATORY.md").write_text("\n".join(L_) + "\n", encoding="utf-8")
print("written:", OUT / "PER-CATEGORY-HUMAN-EXPLORATORY.json", OUT / "PER-CATEGORY-HUMAN-EXPLORATORY.md")
print(json.dumps(comparison, indent=1))
