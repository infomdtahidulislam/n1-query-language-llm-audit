#!/usr/bin/env python3
"""n1_review_common.py — shared machinery for the exploratory descriptives declared in the post-freeze records of
28 Sep 2026 (cue split, human-layer categories, overlap raters, language confusion, retailers and prices).

Everything here is the registered run's: the module executes n1_analysis.py (refused unless its sha256 is the registered
174bae3e…) up to its results block, so the input gates, the three layers, the F.6 primary filter P, the resolver and
class lookups, per_answer_mentions, brand_items and the Boot resampler are the registered objects. It adds only:
  * cell_means / local_share_answer — copies of the registered F.9 helpers, which are defined after the cut;
  * Frame — the resampling rule of the 28 Sep declarations: a frame of query IDs fixed before any eligibility filter,
    10,000 with-replacement resamples of those IDs from a stated seed, reused across models, arms, label versions and
    contrasts; undefined replicates kept as NA (never zero, never redrawn); percentiles over the defined replicates,
    their number reported; no interval when fewer than two distinct queries contribute; an equally weighted six-model
    mean is NA unless all six model estimates are defined, in the point estimate and in each replicate.
"""
import hashlib, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

REG_SHA = "174bae3e3c8ebb8e219ff832c8105aa7373f17db41e837be738e7d2bb6f8fb7e"
RES_SHA = "d12e64e5e8ebcb0f492d0608bed691315dd64ffc2e539b8d6fb7d34f3fd9903c"
NB = 10000
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(root):
    root = Path(root)
    reg = root / "n1_analysis.py"
    src = reg.read_text(encoding="utf-8")
    if hashlib.sha256(src.encode("utf-8")).hexdigest() != REG_SHA:
        raise SystemExit("n1_analysis.py is not the registered file")
    if sha(root / "ANALYSIS-RESULTS.json") != RES_SHA:
        raise SystemExit("ANALYSIS-RESULTS.json is not the registered run of record")
    cut = src.index('\nR = {"meta": {}, "primary": {}')
    argv0 = list(sys.argv)
    sys.argv = ["n1_analysis.py", "--root", str(root), "--out", "REVIEW-unused"]
    G = {"__name__": "n1_analysis_defs", "__file__": str(reg)}
    exec(compile(src[:cut], str(reg), "exec"), G)
    sys.argv = argv0
    G["REC"] = json.loads((root / "ANALYSIS-RESULTS.json").read_text(encoding="utf-8"))
    G["ROOTP"] = root
    return G


def cell_means(rows, val, filt):                # identical to the registered F.9 helper
    d = defaultdict(list)
    for r in rows:
        if filt(r):
            v = val(r)
            if v is not None:
                d[(r["model"], r["query"], r["arm"])].append(v)
    return {k: float(np.mean(v)) for k, v in d.items()}


def make_local_share_answer(G, items=None):
    per_answer_mentions, brand_items = G["per_answer_mentions"], G["brand_items"]
    spec = {"items": items or brand_items()}

    def f(r):
        loc, n, _, _ = per_answer_mentions(r, spec)
        return (loc / n) if n else None
    return f


def share_by_query(cm, model, arm):
    """(model, query, arm) cell means -> {query: value} for one model and arm."""
    return {q: v for (m, q, a), v in cm.items() if m == model and a == arm}


def paired(dA, dB):
    """{query: A - B} over the queries defined in both, in sorted query order (as the registered contrast code)."""
    return {q: dA[q] - dB[q] for q in sorted(set(dA) & set(dB))}


class Frame:
    """Fixed resampling frame of query IDs (fixed before any eligibility filter)."""
    def __init__(self, qids, seed, nb=NB):
        self.q = sorted(set(qids))
        self.ix = {q: i for i, q in enumerate(self.q)}
        self.seed, self.nb = int(seed), nb
        n = len(self.q)
        rng = np.random.default_rng(self.seed)
        self.C = rng.multinomial(n, np.full(n, 1.0 / n), size=nb).astype(np.float64)

    def reps(self, per_q):
        """per-replicate estimate (mean over the resampled defined queries); NaN where no defined query is drawn."""
        v = np.zeros(len(self.q)); m = np.zeros(len(self.q))
        for q, x in per_q.items():
            if q in self.ix:
                v[self.ix[q]] = x; m[self.ix[q]] = 1.0
        num, den = self.C @ v, self.C @ m
        out = np.full(self.nb, np.nan)
        ok = den > 0
        out[ok] = num[ok] / den[ok]
        return out

    @staticmethod
    def ci(reps, n_query):
        """95% percentile interval over the defined replicates; None when fewer than two distinct queries contribute."""
        d = reps[np.isfinite(reps)]
        if n_query < 2 or len(d) == 0:
            return None, int(len(d))
        lo, hi = np.percentile(d, [2.5, 97.5])
        return [float(lo), float(hi)], int(len(d))

    def stat(self, per_q, scale=1.0):
        per_q = {q: v for q, v in per_q.items() if q in self.ix}
        n = len(per_q)
        point = float(np.mean(list(per_q.values())) * scale) if n else None
        reps = self.reps(per_q) * scale
        ci, nrep = self.ci(reps, n)
        return {"estimate": point, "n_query": n, "ci": ci, "n_defined_replicates": nrep if n else 0}, reps


def six_model_mean(points, reps_list, n_queries=None):
    """Equally weighted mean over the six models: NA unless all six defined (point and per replicate); no interval when
    any model's estimate rests on fewer than two contributing queries."""
    if any(p is None for p in points):
        return {"estimate": None, "ci": None, "n_defined_replicates": 0, "note": "NA: not all six model estimates defined"}, None
    R = np.vstack(reps_list)
    ok = np.all(np.isfinite(R), axis=0)
    reps = np.full(R.shape[1], np.nan)
    reps[ok] = R[:, ok].mean(axis=0)
    d = reps[np.isfinite(reps)]
    ci = [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))] if len(d) else None
    if n_queries is not None and min(n_queries) < 2:
        ci = None
    return {"estimate": float(np.mean(points)), "ci": ci, "n_defined_replicates": int(len(d)), "min_n_query": (int(min(n_queries)) if n_queries is not None else None)}, reps


def fmt(x, nd=3):
    return "NA" if x is None else f"{x:.{nd}f}"


def fmt_ci(ci, nd=3):
    return "NA" if ci is None else f"[{ci[0]:.{nd}f}, {ci[1]:.{nd}f}]"
