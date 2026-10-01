#!/usr/bin/env python3
"""n1_supplement.py — N1: the registered re-runs the H.6 plan audit found missing from n1_analysis.py's run
(post-freeze record "plan audit — omissions found and their re-runs fixed", 27 Sep 2026).

Nothing new is estimated here in kind. The script loads the registered analysis code itself — n1_analysis.py,
refused unless its sha256 is the registered 174bae3e… — and executes its definitions, input gates, layers and
fixed bootstrap counts exactly as the registered run does (its source up to the line that starts the results
dictionary), then calls the registered functions with the registered filters for the thirteen analyses the
first run left out:
  F.6 (a) valid-only, (c) truncated removed, (d) mixed removed, for the three estimators of F.2 and F.4 that
      run on the primary set but were re-run only for the primary outcomes:
        RBO_ext on first-mention order (F.2 secondary)        setdiv(H, "brands_order", rbo_ext, ...)
        retailer-set excess divergence (F.4)                  setdiv(H, "retailers", jaccard, ...)
        local-retailer share (F.4, "as in F.3")               share_outcome(H, {"items": retail_items()}, ...)
  C.5 three-way sensitivity for the local-retailer share ("as in F.3"): ambiguous counted local / global
  F.10 RBO_ext ("same estimators as F.2–F.3"), human robust50 layer and machine layer.
All are unadjusted secondary or sensitivity analyses; no primary family, test, seed or input changes.

Before any of them, the script recomputes three analyses of the run of record through the same path —
RBO_ext, retailer-set divergence and local-retailer share on the primary set — and stops unless each reproduces
ANALYSIS-RESULTS.json exactly (--selftest-only stops there).

Usage (study root):  python n1_supplement.py  ->  ANALYSIS-SUPPLEMENT.json, ANALYSIS-SUPPLEMENT.md
"""
import hashlib, json, sys
from pathlib import Path

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("root", nargs="?", default=".")
_ap.add_argument("--synthetic", action="store_true", help="validation on synthetic data only (hash gates off)")
_ap.add_argument("--nb", type=int, default=None, help=argparse.SUPPRESS)
_ap.add_argument("--selftest-only", action="store_true", help="reproduce three registered analyses and stop")
_a = _ap.parse_args()
ROOT_ARG = _a.root
REG = Path(ROOT_ARG) / "n1_analysis.py"
REG_SHA = "174bae3e3c8ebb8e219ff832c8105aa7373f17db41e837be738e7d2bb6f8fb7e"
src = REG.read_text(encoding="utf-8")
if hashlib.sha256(src.encode("utf-8")).hexdigest() != REG_SHA:
    raise SystemExit("n1_analysis.py is not the registered file")
cut = src.index('\nR = {"meta": {}, "primary": {}')
sys.argv = ["n1_analysis.py", "--root", ROOT_ARG, "--out", "ANALYSIS-SUPPLEMENT-unused"] + \
    (["--synthetic"] if _a.synthetic else []) + (["--nb", str(_a.nb)] if _a.nb else [])
G = {"__name__": "n1_analysis_defs", "__file__": str(REG)}
exec(compile(src[:cut], str(REG), "exec"), G)

H, M, BH, BC10, BH10 = G["H"], G["M"], G["BH"], G["BC10"], G["BH10"]
setdiv, share_outcome, jaccard, rbo_ext = G["setdiv"], G["share_outcome"], G["jaccard"], G["rbo_ext"]
retail_items, SENS, P, ARMS3, C3, C10 = G["retail_items"], G["SENS"], G["P"], G["ARMS3"], G["C3"], G["C10"]
F6 = {k: SENS[k] for k in ("valid_only", "no_truncated", "no_mixed")}

def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [strip(v) for v in o]
    return o

# self-test: through this path the registered functions reproduce the registered run exactly
if not _a.synthetic:
    RES = Path(ROOT_ARG) / "ANALYSIS-RESULTS.json"
    if hashlib.sha256(RES.read_bytes()).hexdigest() != "d12e64e5e8ebcb0f492d0608bed691315dd64ffc2e539b8d6fb7d34f3fd9903c":
        raise SystemExit("ANALYSIS-RESULTS.json is not the registered run of record")
    with open(RES, encoding="utf-8") as fh:
        REC = json.load(fh)
    rt = lambda o: json.loads(json.dumps(strip(o), default=lambda v: None))
    checks = {"RQ1_rbo": setdiv(H, "brands_order", rbo_ext, C3, P, BH, "RQ1 excess divergence (RBO_ext p=0.9, first-mention order)"),
              "RQ4_retailer_overlap": setdiv(H, "retailers", jaccard, C3, P, BH, "retailer-set excess divergence (Jaccard)"),
              "RQ4_local_retailer_share": share_outcome(H, {"items": retail_items()}, ARMS3, C3, P, BH,
                                                        "local-retailer share (F3 list; brand-table class for entities absent from it)")}
    for k, v in checks.items():
        if rt(v) != REC["secondary"][k]:
            raise SystemExit(f"SELF-TEST FAILED: {k} does not reproduce the registered run")
    print("self-test passed: RQ1_rbo, RQ4_retailer_overlap and RQ4_local_retailer_share reproduce the run of record exactly")
if _a.selftest_only:
    raise SystemExit(0)

S = {"secondary": {}, "sensitivity": {}}
for s, f in F6.items():
    S["sensitivity"][f"RQ1_rbo_{s}"] = setdiv(H, "brands_order", rbo_ext, C3, f, BH, f"RQ1 RBO_ext sensitivity: {s}")
    S["sensitivity"][f"RQ4_retailer_overlap_{s}"] = setdiv(H, "retailers", jaccard, C3, f, BH, f"retailer-set divergence sensitivity: {s}")
    S["sensitivity"][f"RQ4_local_retailer_share_{s}"] = share_outcome(H, {"items": retail_items()}, ARMS3, C3, f, BH,
                                                                      f"local-retailer share sensitivity: {s}")
S["sensitivity"]["RQ4_local_retailer_share_ambiguous_local"] = share_outcome(
    H, {"items": retail_items(), "ambiguous": "local"}, ARMS3, C3, P, BH, "C.5 for the local-retailer share: ambiguous counted local")
S["sensitivity"]["RQ4_local_retailer_share_ambiguous_global"] = share_outcome(
    H, {"items": retail_items(), "ambiguous": "global"}, ARMS3, C3, P, BH, "C.5 for the local-retailer share: ambiguous counted global")
H10 = [r for r in H if r["query"] in set(BH10.q)]
M10 = [r for r in M if r["query"] in set(BC10.q)]
S["secondary"]["F10_RQ1_rbo"] = setdiv(H10, "brands_order", rbo_ext, C10, P, BH10, "F.10 RBO_ext, human layer")
S["secondary"]["F10_RQ1_rbo_machine"] = setdiv(M10, "brands_order", rbo_ext, C10, P, BC10, "F.10 RBO_ext, machine layer")

import numpy, scipy, statsmodels, pandas, platform
out = {"meta": {"task": "N1 supplementary registered re-runs found by the H.6 plan audit",
                "n1_analysis_sha256": REG_SHA,
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "inputs": G["inputs"], "synthetic": _a.synthetic,
                "bootstrap": {"resamples": G["A"].nb, "seeds": "the registered layer seeds (as n1_analysis.py)"},
                "software": {"python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
                             "pandas": pandas.__version__, "statsmodels": statsmodels.__version__}},
       **strip(S)}
root = Path(ROOT_ARG)
with open(root / "ANALYSIS-SUPPLEMENT.json", "w", encoding="utf-8", newline="\n") as fh:
    json.dump(out, fh, indent=1, default=lambda o: None)

# ---- rendering (formatting only; same table layout as n1_report.py)
MODELS = G["MODELS"]
L = ["# N1 — supplementary registered re-runs (H.6 plan audit)", "",
     f"Registered code n1_analysis.py `{REG_SHA[:12]}…` executed up to its results block; this script "
     f"`{out['meta']['script_sha256'][:12]}…`. Bootstrap {G['A'].nb} query resamples with the registered layer seeds. "
     "All results unadjusted (secondary or sensitivity).", ""]
pv = lambda p: "–" if p is None else ("<0.0001" if p < 1e-4 else f"{p:.4f}")
def ci(c, pp=False, nd=4):
    if not c or c[0] is None:
        return "–"
    return f"[{100 * c[0]:+.1f}, {100 * c[1]:+.1f}]" if pp else f"[{c[0]:.{nd}f}, {c[1]:.{nd}f}]"
for blk in ("sensitivity", "secondary"):
    for key, b in out[blk].items():
        L += [f"### {key} — {b['label']}", ""]
        res = b["results"]
        if all("|" in k for k in res):
            L += ["| model | contrast | queries | mean Δ [95% CI] | median Δ | Wilcoxon p |", "|---|---|---|---|---|---|"]
            for k, x in res.items():
                m, c = k.split("|")
                if not x.get("n_query"):
                    L.append(f"| {m} | {c} | 0 | – | – | – |")
                    continue
                L.append(f"| {m} | {c} | {x['n_query']} | {x['mean_delta']:+.4f} {ci(x['ci'])} | {x['median_delta']:+.4f} | {pv(x['test']['p'])} |")
        else:
            L += ["| model | contrast | difference, pp [95% CI] | log-odds [Wald 95% CI] | test | p |", "|---|---|---|---|---|---|"]
            for m in MODELS:
                r = res.get(m)
                if not r:
                    continue
                for c, x in r["contrasts"].items():
                    lo = x.get("log_odds")
                    los = f"{lo['estimate']:+.2f} [{lo['ci_low']:+.2f}, {lo['ci_high']:+.2f}]" if lo else "–"
                    t = x.get("test", {})
                    meth = "GLMM Wald" if t.get("method") == "glmm_wald" else f"fallback Wilcoxon ({r['glmm']['status']})"
                    d = x.get("diff")
                    L.append(f"| {m} | {c} | {'–' if d is None else f'{100 * d:+.1f}'} {ci(x['ci'], True)} | {los} | {meth} | {pv(t.get('p'))} |")
            L += ["", "| model | " + " | ".join(ARMS3) + " |", "|---|---|---|---|"]
            for m in MODELS:
                r = res.get(m)
                if r:
                    L.append(f"| {m} | " + " | ".join(
                        (f"{x['share']:.3f} {ci(x['ci'], nd=3)} (n {x['n']:.0f})" if x.get("share") is not None else "–")
                        + (f"; amb {100 * x['ambiguous_rate']:.1f}%" if x.get("ambiguous_rate") is not None else "")
                        for x in (r["arms"][a] for a in ARMS3)) + " |")
        L.append("")
with open(root / "ANALYSIS-SUPPLEMENT.md", "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(L))
print(f"wrote ANALYSIS-SUPPLEMENT.json / .md ({sum(len(v) for k, v in out.items() if k != 'meta')} analyses)")
