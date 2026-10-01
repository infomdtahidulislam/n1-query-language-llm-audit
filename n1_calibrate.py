#!/usr/bin/env python3
"""n1_calibrate.py — N1: null calibration of the registered tests on synthetic data (n1_synth.py --null).

For each seed a synthetic study with NO arm effect is generated and n1_analysis.py is run in its
calibration mode (--only rq12: RQ1 Wilcoxon and randomization tests, RQ2 and price-mention GLMMs with and
without the query-by-arm term, query-level cluster-bootstrap intervals). Reports each test's rejection
rate at alpha = .05 (nominal 5%) and how often the bootstrap interval excludes zero.
    python n1_calibrate.py --het 0 --seeds 1001-1040 --out CAL-het0.json
    python n1_calibrate.py --het 0.5 --seeds 2001-2040 --out CAL-het05.json
"""
import argparse, json, shutil, subprocess, sys, tempfile
from pathlib import Path
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--het", type=float, default=0.0)
ap.add_argument("--seeds", default="1001-1040")
ap.add_argument("--nb", type=int, default=1000)
ap.add_argument("--out", required=True)
a = ap.parse_args()
lo, hi = (int(x) for x in a.seeds.split("-"))
here = Path(__file__).parent
acc = {k: [] for k in ("rq1_wilcoxon", "rq1_permutation", "rq2_glmm", "rq2_glmm_cell", "price_glmm", "price_glmm_cell")}
excl = {"rq2_boot_ci": [], "price_boot_ci": []}
for s in range(lo, hi + 1):
    d = Path(tempfile.mkdtemp(prefix=f"n1cal{s}_"))
    subprocess.run([sys.executable, str(here / "n1_synth.py"), str(d), "--seed", str(s), "--null", "--het", str(a.het)],
                   check=True, capture_output=True)
    subprocess.run([sys.executable, str(here / "n1_analysis.py"), "--root", str(d), "--synthetic", "--nb", str(a.nb),
                    "--only", "rq12", "--out", "CAL"], check=True, capture_output=True)
    R = json.load(open(d / "CAL.json"))
    for k, v in R["primary"]["RQ1_excess_divergence"]["results"].items():
        if v.get("n_query"):
            acc["rq1_wilcoxon"].append(v["test"]["p"])
    for k, v in R["sensitivity"]["RQ1_permutation"]["results"].items():
        if v.get("n_query"):
            acc["rq1_permutation"].append(v["p"])
    for blk, key, ek in (("primary", "RQ2_local_share", "rq2_glmm"), ("sensitivity", "RQ2_het", "rq2_glmm_cell"),
                         ("primary", "RQ4_price_mention", "price_glmm"), ("sensitivity", "RQ4_price_het", "price_glmm_cell")):
        for m, r in R[blk][key]["results"].items():
            for c, x in r["contrasts"].items():
                if x["test"]["method"] == "glmm_wald":
                    acc[ek].append(x["test"]["p"])
                if blk == "primary" and x["ci"][0] is not None:
                    excl["rq2_boot_ci" if key == "RQ2_local_share" else "price_boot_ci"].append(
                        bool(x["ci"][0] > 0 or x["ci"][1] < 0))
    shutil.rmtree(d)
    print(f"seed {s} done", flush=True)
summary = {"het": a.het, "seeds": a.seeds, "datasets": hi - lo + 1, "bootstrap_resamples": a.nb,
           "rejection_at_05": {k: {"rate": float(np.mean(np.array(v) < 0.05)), "n": len(v)} for k, v in acc.items()},
           "bootstrap_ci_excludes_zero": {k: {"rate": float(np.mean(v)), "n": len(v)} for k, v in excl.items()}}
json.dump(summary, open(a.out, "w"), indent=1)
print(json.dumps(summary, indent=1))
