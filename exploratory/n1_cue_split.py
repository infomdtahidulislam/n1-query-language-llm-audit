#!/usr/bin/env python3
"""n1_cue_split.py — N1: exploratory split of the local-brand share by market cue (declared in the post-freeze record of
28 Sep 2026). Descriptive only: no test, no adjustment; outside the results of record.

Groups (from the frozen queries.csv and the scan record): "cue" = the 80 budget questions plus the 9 questions that name
Bangladesh or Dhaka in all three renderings (Q001, Q026, Q126, Q151, Q172, Q176, Q185, Q201, Q226) — 89 queries;
"no cue" = the other 161, with Q150 and Q180 kept there and flagged (everyday টাকা / taka).
Per subject model, on the human-labelled layer (80 queries) and on the machine-extracted layer (250 queries), on the
run-of-record F.6 primary set: the local-brand share by arm (en, bn, bl) and the bn–en, bl–en and bn–bl paired
differences in percentage points, with eligible-query counts. Intervals: 95% percentiles from 10,000 resamples of the
frame's query IDs — four frames fixed before any eligibility filter: human × cue (seed 20261001), human × no cue
(20261002), machine × cue (20261003), machine × no cue (20261004) — reused across models, arms and contrasts; undefined
replicates NA. Cue-by-subtype cross-tabulations of query counts for the full frame and the human layer.
Self-test (registered values only): pooling the two groups reproduces the registered RQ2 arm shares, query counts and
paired differences of each layer exactly (primary/RQ2_local_share on the human layer, secondary/machine_RQ2 on the
machine layer); --selftest-only stops there.

Usage (study root):  python exploratory/n1_cue_split.py  ->  exploratory/CUE-SPLIT-EXPLORATORY.json / .md
"""
import argparse, csv, datetime, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from n1_review_common import load, cell_means, make_local_share_answer, share_by_query, paired, Frame, sha, fmt, fmt_ci, NB

ap = argparse.ArgumentParser(); ap.add_argument("root", nargs="?", default="."); ap.add_argument("--selftest-only", action="store_true")
A = ap.parse_args(); ROOT = Path(A.root); OUT = ROOT / "exploratory"
G = load(ROOT)
H, M, P, MODELS, ARMS3, C3, REC = G["H"], G["M"], G["P"], G["MODELS"], G["ARMS3"], G["C3"], G["REC"]
NAMED = ["Q001", "Q026", "Q126", "Q151", "Q172", "Q176", "Q185", "Q201", "Q226"]
FLAGGED = ["Q150", "Q180"]
SEEDS = {("human", "cue"): 20261001, ("human", "no_cue"): 20261002, ("machine", "cue"): 20261003, ("machine", "no_cue"): 20261004}
Q_SHA = "9639998a98d605f700f7537fe9a3cfb7ed53975b0b1cb43b7a0bf75b595b5e02"
assert sha(ROOT / "queries.csv") == Q_SHA
qrows = list(csv.DictReader(open(ROOT / "queries.csv", encoding="utf-8")))
SUB = {r["query_id"]: r["subtype"] for r in qrows}
CUE = {q for q, s in SUB.items() if s == "budget"} | set(NAMED)
assert len(CUE) == 89 and all(q not in CUE for q in FLAGGED)
group_of = lambda q: "cue" if q in CUE else "no_cue"
SUBTYPES = ("open", "budget", "use-case", "purchase-channel")

lsa = make_local_share_answer(G)
layers = {"human": [r for r in H if r["arm"] in ARMS3], "machine": [r for r in M if r["arm"] in ARMS3]}
cm = {L: cell_means(rows, lsa, P) for L, rows in layers.items()}
frame_q = {L: sorted({r["query"] for r in rows}) for L, rows in layers.items()}

# ---- self-test: pooled over both groups = the registered RQ2 shares and paired differences ---------------------
def registered(L):
    return REC["primary"]["RQ2_local_share"]["results"] if L == "human" else REC["secondary"]["machine_RQ2"]["results"]
for L in layers:
    reg = registered(L)
    for m in MODELS:
        sq = {a: share_by_query(cm[L], m, a) for a in ARMS3}
        for a in ARMS3:
            assert reg[m]["arms"][a]["n_query"] == len(sq[a]) and reg[m]["arms"][a]["share"] == float(np.mean(list(sq[a].values()))), (L, m, a)
        for a, b in C3:
            d = paired(sq[a], sq[b])
            assert reg[m]["contrasts"][f"{a}-{b}"]["n_query"] == len(d) and reg[m]["contrasts"][f"{a}-{b}"]["diff"] == float(np.mean(list(d.values()))), (L, m, a, b)
print("self-test OK: pooled over the cue groups, both layers reproduce the registered RQ2 arm shares, query counts and paired differences exactly")
if A.selftest_only:
    sys.exit(0)

# ---- cross-tabulations --------------------------------------------------------------------------------------------
def xtab(qids):
    return {st: {"cue": sum(1 for q in qids if group_of(q) == "cue" and SUB[q] == st),
                 "no_cue": sum(1 for q in qids if group_of(q) == "no_cue" and SUB[q] == st)} for st in SUBTYPES}
XT = {"full_frame_250": xtab(list(SUB)), "human_layer": xtab(frame_q["human"]), "machine_layer": xtab(frame_q["machine"])}
sizes = {L: {g: sorted(q for q in frame_q[L] if group_of(q) == g) for g in ("cue", "no_cue")} for L in layers}

# ---- estimates ----------------------------------------------------------------------------------------------------
res = {}
for L in layers:
    res[L] = {}
    for g in ("cue", "no_cue"):
        fr = Frame(sizes[L][g], SEEDS[(L, g)], NB)
        res[L][g] = {"frame": {"n_query": len(fr.q), "seed": fr.seed, "query_ids": fr.q, "resamples": NB}, "models": {}}
        for m in MODELS:
            sq = {a: {q: v for q, v in share_by_query(cm[L], m, a).items() if group_of(q) == g} for a in ARMS3}
            entry = {"arms": {}, "contrasts": {}}
            for a in ARMS3:
                st, _ = fr.stat(sq[a])
                entry["arms"][a] = st
            for a, b in C3:
                st, _ = fr.stat(paired(sq[a], sq[b]), scale=100.0)
                entry["contrasts"][f"{a}-{b}"] = st
            res[L][g]["models"][m] = entry

def diffs(L, g, c):
    return [res[L][g]["models"][m]["contrasts"][c]["estimate"] for m in MODELS]
summary = {}
for L in layers:
    for c in ("bn-en", "bl-en"):
        summary[f"{L}|{c}"] = {g: {"range_pp": ([min(x for x in diffs(L, g, c) if x is not None), max(x for x in diffs(L, g, c) if x is not None)]
                                                if any(x is not None for x in diffs(L, g, c)) else None),
                                   "n_models_defined": sum(x is not None for x in diffs(L, g, c))} for g in ("cue", "no_cue")}

meta = {"task": "exploratory split by market cue (F.6 exploratory; descriptive, no test, no adjustment; outside the results of record)",
        "groups": {"cue": "80 budget questions + 9 questions naming Bangladesh or Dhaka in all three renderings", "no_cue": "the other 161; Q150 and Q180 kept there and flagged",
                   "named_queries": NAMED, "flagged_in_no_cue": FLAGGED, "cue_n": 89, "no_cue_n": 161},
        "layers": {"human": "human-labelled layer, F.6 primary set by the human labels (arms en, bn, bl)", "machine": "machine-extracted layer, F.6 primary set by the coded outcomes; brand-set F1 0.8221 against the rater consensus"},
        "estimand": "per-answer local share of classified brand mentions (ambiguous, unclassifiable and not-a-brand names excluded), averaged over the repetitions of the query x model x arm cell, then over the group's queries; paired contrasts over the queries defined in both arms; run-of-record tables",
        "bootstrap": {"resamples": NB, "frames": {f"{L}|{g}": {"seed": SEEDS[(L, g)], "n_query": len(sizes[L][g])} for L in layers for g in ("cue", "no_cue")},
                      "rule": "frame fixed before eligibility; resamples reused across models, arms and contrasts; undefined replicates NA; percentiles over defined replicates; no interval below two contributing queries"},
        "n1_analysis_sha256": G["REC"]["meta"].get("n1_analysis_sha256") if isinstance(G["REC"].get("meta"), dict) else None,
        "inputs": G["inputs"], "queries_sha256": Q_SHA, "script_sha256": sha(Path(__file__)), "common_sha256": sha(Path(__file__).with_name("n1_review_common.py")),
        "run_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
OUT.mkdir(exist_ok=True)
json.dump({"meta": meta, "crosstab": XT, "group_sizes": {L: {g: len(sizes[L][g]) for g in sizes[L]} for L in layers}, "results": res, "summary": summary},
          open(OUT / "CUE-SPLIT-EXPLORATORY.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)

L_ = ["# N1 — exploratory split by market cue (descriptive only; not a result of record)", "",
      f"Groups: cue = 80 budget questions + 9 naming Bangladesh or Dhaka ({', '.join(NAMED)}) = 89; no cue = 161 (Q150 and Q180 kept there, flagged). "
      f"Human layer {len(sizes['human']['cue'])} / {len(sizes['human']['no_cue'])} queries; machine layer {len(sizes['machine']['cue'])} / {len(sizes['machine']['no_cue'])}. "
      f"95% percentile intervals from {NB:,} resamples of each frame's query IDs (seeds {', '.join(str(SEEDS[k]) for k in SEEDS)}); no test.", "",
      "## Cue by subtype (query counts, cue / no cue)", "", "| subtype | full frame (250) | human layer (80) |", "|---|---|---|"]
for st in SUBTYPES:
    L_.append(f"| {st} | {XT['full_frame_250'][st]['cue']} / {XT['full_frame_250'][st]['no_cue']} | {XT['human_layer'][st]['cue']} / {XT['human_layer'][st]['no_cue']} |")
for L in layers:
    for g in ("cue", "no_cue"):
        L_ += ["", f"## {L} layer — {g.replace('_', ' ')} ({len(sizes[L][g])} queries; seed {SEEDS[(L, g)]})", "",
               "| model | en (n) | bn (n) | bl (n) | bn–en pp (n) | bl–en pp (n) | bn–bl pp (n) |", "|---|---|---|---|---|---|---|"]
        for m in MODELS:
            e = res[L][g]["models"][m]
            cells = [f"{fmt(e['arms'][a]['estimate'])} {fmt_ci(e['arms'][a]['ci'])} ({e['arms'][a]['n_query']})" for a in ARMS3]
            cells += [f"{fmt(e['contrasts'][c]['estimate'], 1)} {fmt_ci(e['contrasts'][c]['ci'], 1)} ({e['contrasts'][c]['n_query']})" for c in ("bn-en", "bl-en", "bn-bl")]
            L_.append(f"| {m} | " + " | ".join(cells) + " |")
rng = lambda r: "NA" if r is None else f"{r[0]:+.1f} to {r[1]:+.1f}"
L_ += ["", "## Ranges of the six per-model differences (pp)", ""] + [f"- {k}: cue {rng(v['cue']['range_pp'])}; no cue {rng(v['no_cue']['range_pp'])}" for k, v in summary.items()]
(OUT / "CUE-SPLIT-EXPLORATORY.md").write_text("\n".join(L_) + "\n", encoding="utf-8")
print("written:", OUT / "CUE-SPLIT-EXPLORATORY.json", OUT / "CUE-SPLIT-EXPLORATORY.md")
print(json.dumps(summary, indent=1))
