#!/usr/bin/env python3
"""n1_c1_sensitivity.py — N1: the declared post-hoc C.1 sensitivity (post-freeze records of 28 Sep 2026).

Frozen Appendix C.1 names joint ventures, BD-assembled foreign brands and multinational subsidiaries with substantial
local identity as `ambiguous` cases; the frozen classification file classes such foreign brands `global`. This script
re-runs RQ2 local share with the brands the authors decided on BD-ASSEMBLY-CHECK.html (BD-ASSEMBLY-CHECK-decisions.json,
banked as received; every non-global decision carries a source) classed `ambiguous`, three ways — ambiguous excluded,
counted local, counted global — on the human layer's primary analysis set (the registered confirmatory layer) and on
the machine layer (secondary). It executes the registered n1_analysis.py (refused unless its sha256 is the registered
174bae3e…) up to its results block, exactly as n1_supplement.py does, so every gate, layer, filter, bootstrap count and
seed is the registered run's, then overrides the class lookup for the decided brands and calls the registered
share_outcome. Before any variant it recomputes the registered RQ2 local share on the human layer with no override and
stops unless it reproduces ANALYSIS-RESULTS.json exactly outside the GLMM-bootstrap fields outside the GLMM-fit fields, which R/lme4 reproduces only to floating-point precision between sessions (checked
to a relative 1e-3 on estimates and 2% on p-values; --selftest-only stops there).
All results are unadjusted, post hoc, and reported beside the registered results, which remain the run of record.

Usage (study root):  python n1_c1_sensitivity.py  ->  ANALYSIS-C1-SENSITIVITY.json, ANALYSIS-C1-SENSITIVITY.md
"""
import argparse, hashlib, json, sys
from pathlib import Path

_ap = argparse.ArgumentParser()
_ap.add_argument("root", nargs="?", default=".")
_ap.add_argument("--selftest-only", action="store_true")
_ap.add_argument("--nb", type=int, default=None, help=argparse.SUPPRESS)
_a = _ap.parse_args()
ROOT = Path(_a.root)
REG = ROOT / "n1_analysis.py"
REG_SHA = "174bae3e3c8ebb8e219ff832c8105aa7373f17db41e837be738e7d2bb6f8fb7e"
DEC_SHA = "f52e0824d2a2afe1"          # BD-ASSEMBLY-CHECK-decisions.json as banked (prefix)
src = REG.read_text(encoding="utf-8")
if hashlib.sha256(src.encode("utf-8")).hexdigest() != REG_SHA:
    raise SystemExit("n1_analysis.py is not the registered file")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
dec_path = ROOT / "BD-ASSEMBLY-CHECK-decisions.json"
if not sha(dec_path).startswith(DEC_SHA):
    raise SystemExit("BD-ASSEMBLY-CHECK-decisions.json is not the banked file")
with open(dec_path, encoding="utf-8") as fh:
    DEC = json.load(fh)
AMB = sorted(r["canonical_id"] for r in DEC["rows"] if r["decision"] in ("jv", "assembled", "subsidiary"))
assert len(AMB) == 32 and all(r["source"].strip() for r in DEC["rows"] if r["decision"] != "global")

cut = src.index('\nR = {"meta": {}, "primary": {}')
sys.argv = ["n1_analysis.py", "--root", str(ROOT), "--out", "ANALYSIS-C1-SENSITIVITY-unused"] + (["--nb", str(_a.nb)] if _a.nb else [])
G = {"__name__": "n1_analysis_defs", "__file__": str(REG)}
exec(compile(src[:cut], str(REG), "exec"), G)
H, M, BH, BM = G["H"], G["M"], G["BH"], G["BM"]
share_outcome, brand_items, P, ARMS3, C3, BCLASS = G["share_outcome"], G["brand_items"], G["P"], G["ARMS3"], G["C3"], G["BCLASS"]
assert all(BCLASS.get(e) == "global" for e in AMB), "a decided brand is not global in the frozen table"

def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if not k.startswith("_") and k not in ("boot_ci", "boot_dropped")}
    if isinstance(o, list):
        return [strip(v) for v in o]
    return o
rt = lambda o: json.loads(json.dumps(strip(o), default=lambda v: None))

# self-test: the registered RQ2 local share, no override, reproduced outside the GLMM-bootstrap fields
RES = ROOT / "ANALYSIS-RESULTS.json"
if sha(RES) != "d12e64e5e8ebcb0f492d0608bed691315dd64ffc2e539b8d6fb7d34f3fd9903c":
    raise SystemExit("ANALYSIS-RESULTS.json is not the registered run of record")
with open(RES, encoding="utf-8") as fh:
    REC = json.load(fh)
base = share_outcome(H, {"items": brand_items()}, ARMS3, C3, P, BH, "RQ2 local share (ambiguous and unclassifiable excluded)")
GLMM_KEYS = ("estimate", "se", "z", "p", "ci_low", "ci_high", "random_intercept_sd", "cell_sd")
def compare(a, b, path, exact, near):
    """exact: every non-GLMM field identical; near: GLMM-fit fields (R/lme4 floating point) within tolerance."""
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            exact.append((path, "keys", sorted(set(a) ^ set(b))))
        for k in a:
            if k in b:
                compare(a[k], b[k], path + "/" + k, exact, near)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (u, v) in enumerate(zip(a, b)):
            compare(u, v, f"{path}[{i}]", exact, near)
    elif a != b:
        leaf = path.rsplit("/", 1)[-1]
        if leaf in GLMM_KEYS and isinstance(a, (int, float)) and isinstance(b, (int, float)):
            tol = 0.02 if leaf == "p" else 1e-3
            near.append((path, a, b, abs(a - b) / max(abs(b), 1e-300)))
            if abs(a - b) > tol * max(abs(a), abs(b)) and abs(a - b) > 1e-9:
                exact.append((path, a, b))
        else:
            exact.append((path, a, b))
_exact, _near = [], []
compare(rt(base), rt(REC["primary"]["RQ2_local_share"]), "", _exact, _near)
if _exact:
    raise SystemExit(f"SELF-TEST FAILED: RQ2 local share does not reproduce the run of record: {_exact[:5]}")
_maxrel = max((x[3] for x in _near), default=0.0)
print(f"self-test passed: RQ2 local share reproduces the run of record exactly outside the GLMM-fit fields; "
      f"{len(_near)} GLMM-fit values differ by floating point only (largest relative difference {_maxrel:.2e})")
SELFTEST = {"glmm_fields_differing": len(_near), "largest_relative_difference": _maxrel,
            "largest_absolute_difference_estimate": max((abs(x[1] - x[2]) for x in _near if x[0].endswith("/estimate")), default=0.0)}
if _a.selftest_only:
    raise SystemExit(0)

# override: the decided brands become ambiguous (BCLASS is the dict bclass() reads)
for e in AMB:
    BCLASS[e] = "ambiguous"
S = {"human": {}, "machine": {}}
S["human"]["excluded"] = share_outcome(H, {"items": brand_items()}, ARMS3, C3, P, BH, "C.1 reading, ambiguous excluded (human layer)")
S["human"]["counted_local"] = share_outcome(H, {"items": brand_items(), "ambiguous": "local"}, ARMS3, C3, P, BH, "C.1 reading, ambiguous counted local (human layer)")
S["human"]["counted_global"] = share_outcome(H, {"items": brand_items(), "ambiguous": "global"}, ARMS3, C3, P, BH, "C.1 reading, ambiguous counted global (human layer)")
S["machine"]["excluded"] = share_outcome(M, {"items": brand_items()}, ARMS3, C3, P, BM, "C.1 reading, ambiguous excluded (machine layer)")
S["machine"]["counted_local"] = share_outcome(M, {"items": brand_items(), "ambiguous": "local"}, ARMS3, C3, P, BM, "C.1 reading, ambiguous counted local (machine layer)")
S["machine"]["counted_global"] = share_outcome(M, {"items": brand_items(), "ambiguous": "global"}, ARMS3, C3, P, BM, "C.1 reading, ambiguous counted global (machine layer)")

import numpy, scipy, statsmodels, pandas, platform
out = {"meta": {"task": "N1 post-hoc C.1 sensitivity: RQ2 local share with the authors' decided brands classed ambiguous",
                "n1_analysis_sha256": REG_SHA, "script_sha256": sha(Path(__file__)), "decisions_sha256": sha(dec_path),
                "decided_ambiguous": AMB, "decisions_counts": DEC["counts"], "inputs": G["inputs"], "selftest": SELFTEST,
                "bootstrap": {"resamples": G["A"].nb, "seeds": "the registered layer seeds (as n1_analysis.py)"},
                "note": ("registered results remain the run of record; these are unadjusted post-hoc sensitivities. Entities already "
                         "ambiguous in the frozen table are treated as in the registered C.5 sensitivities (excluded / counted local / "
                         "counted global together with the decided brands)."),
                "software": {"python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
                             "pandas": pandas.__version__, "statsmodels": statsmodels.__version__}},
       "human": strip(S["human"]), "machine": strip(S["machine"])}
with open(ROOT / "ANALYSIS-C1-SENSITIVITY.json", "w", encoding="utf-8", newline="\n") as fh:
    json.dump(out, fh, indent=1, default=lambda o: None)

MODELS = G["MODELS"]
pv = lambda p: "–" if p is None else ("<0.0001" if p < 1e-4 else f"{p:.4f}")
def ci(c, pp=False, nd=3):
    if not c or c[0] is None:
        return "–"
    return f"[{100 * c[0]:+.1f}, {100 * c[1]:+.1f}]" if pp else f"[{c[0]:.{nd}f}, {c[1]:.{nd}f}]"
L = ["# N1 — post-hoc C.1 sensitivity: RQ2 local share (unadjusted; the registered results remain the run of record)", "",
     f"Registered code n1_analysis.py `{REG_SHA[:12]}…` executed up to its results block; this script `{out['meta']['script_sha256'][:12]}…`; "
     f"decisions BD-ASSEMBLY-CHECK-decisions.json `{out['meta']['decisions_sha256'][:12]}…` ({len(AMB)} brands classed ambiguous: {', '.join(AMB)}). "
     f"Bootstrap {G['A'].nb} query resamples with the registered layer seeds; GLMM y ~ arm + (1|query) as registered (no GLMM bootstrap).", ""]
reg = REC["primary"]["RQ2_local_share"]["results"]
L += ["## Registered RQ2 local share (human layer, run of record) for reference", "", "| model | en | bn | bl | bn–en pp | bl–en pp | bn–bl pp |", "|---|---|---|---|---|---|---|"]
for m in MODELS:
    r = reg[m]
    L.append(f"| {m} | " + " | ".join(f"{r['arms'][a]['share']:.3f}" for a in ARMS3) + " | " +
             " | ".join(f"{100 * r['contrasts'][c]['diff']:+.1f} (p {pv(r['contrasts'][c]['test']['p'])})" for c in ("bn-en", "bl-en", "bn-bl")) + " |")
for layer in ("human", "machine"):
    for var in ("excluded", "counted_local", "counted_global"):
        b = out[layer][var]
        L += ["", f"## {layer} layer — {b['label']}", "", "| model | en | bn | bl | contrast | Δ pp [95% CI] | log-odds [Wald 95% CI] | test | p |", "|---|---|---|---|---|---|---|---|---|"]
        for m in MODELS:
            r = b["results"][m]
            shares = " | ".join((f"{r['arms'][a]['share']:.3f} {ci(r['arms'][a]['ci'])}" if r["arms"][a].get("share") is not None else "–") for a in ARMS3)
            for c, x in r["contrasts"].items():
                lo = x.get("log_odds")
                los = f"{lo['estimate']:+.2f} [{lo['ci_low']:+.2f}, {lo['ci_high']:+.2f}]" if lo else "–"
                t = x.get("test", {})
                meth = "GLMM Wald" if t.get("method") == "glmm_wald" else f"fallback Wilcoxon ({r['glmm']['status']})"
                d = x.get("diff")
                L.append(f"| {m} | {shares} | {c} | {'–' if d is None else f'{100 * d:+.1f}'} {ci(x['ci'], True)} | {los} | {meth} | {pv(t.get('p'))} |")
        L.append("")
        L.append("Ambiguous rate by arm: " + "; ".join(f"{m} " + "/".join(f"{100 * (b['results'][m]['arms'][a].get('ambiguous_rate') or 0):.1f}%" for a in ARMS3) for m in MODELS) + ".")
with open(ROOT / "ANALYSIS-C1-SENSITIVITY.md", "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(L) + "\n")
print("wrote ANALYSIS-C1-SENSITIVITY.json / .md")
