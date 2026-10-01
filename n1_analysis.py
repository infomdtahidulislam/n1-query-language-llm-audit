#!/usr/bin/env python3
"""n1_analysis.py — N1: the registered analyses (PREREGISTRATION §F.1–F.10, Appendix C.5, post-freeze
records 12, 15, 17, 18 and the implementation record that registers this script's sha256).

LAYERS
  human    the expansion sample (EXPANSION-ANALYSIS-SET-v2.jsonl): confirmatory for RQ1, RQ2, RQ4 (F.2–F.4)
           and F.10; RQ5 refusal sensitivity (12th record)
  corpus   the full coded main run (runs/coded/main.final.jsonl, final draw per cell): confirmatory for RQ5
           (F.5 reversion, refusal; degeneracy and length exploratory)
  machine  the full main run with the primary extractor's labels (runs/extracted/main.primary.jsonl), names
           resolved through the same extended table: secondary, descriptive (12th record), plus a
           human-machine concordance on the 3,023 expansion answers

ESTIMATES AND TESTS (fixed in the implementation record)
  * estimand (B.2: the query is the unit of analysis): an outcome is averaged over the reps of each
    query x model x arm cell (per-answer share first for mention- and price-level outcomes, D.3), then over
    queries; a contrast is the mean over queries of the paired within-query difference (RQ1: mean Delta);
  * every estimate carries a 95% cluster-bootstrap percentile CI: 10,000 resamples of the layer's queries
    (one fixed set of resample counts per layer, seeds 20260926..20260929, reused for every estimate);
  * RQ1: excess divergence Delta = D_btw - mean(D_win) per query x model x contrast (Jaccard; J(0,0) = 1,
    J(0,S) = 0); registered test = two-sided Wilcoxon signed-rank over queries (scipy, zero_method 'wilcox',
    method 'auto'); sensitivity: randomization test (answers exchangeable across the two arms within a
    query x model); secondary: the same with RBO_ext (p = 0.9) on first-mention order;
  * RQ2 / RQ4 / RQ5 binary outcomes: registered test = logistic mixed model y ~ arm + (1|query) per subject
    model (lme4 glmer, Laplace; n1_glmm.R), Wald contrasts on the log-odds scale; F.3's fallback (per-query
    rate averaged over reps, paired Wilcoxon over queries) when the model is not identifiable or fails to
    converge under the protocol in n1_glmm.R; beside every primary-family contrast, a cluster-bootstrap CI
    of the log-odds contrast itself (--glmm-boot) and a sensitivity fit adding (1|query:arm);
  * length: linear mixed model log(completion_tokens) ~ arm + (1|query), statsmodels MixedLM (REML), Wald;
  * F.7: Holm within each primary family (6 models x its contrasts); everything else is labelled
    secondary / sensitivity / exploratory and not adjusted.

Usage:  python n1_analysis.py --root . [--glmm-boot] [--synthetic] [--out ANALYSIS-RESULTS]
"""
import argparse, csv, hashlib, json, math, os, re, subprocess, sys, tempfile, time, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests

ARMS3 = ["en", "bn", "bl"]
C3 = [("bn", "en"), ("bl", "en"), ("bn", "bl")]
C10 = [("bn", "bl_translit"), ("bl", "bl_translit")]
FORM = {"en": "en", "bn": "bn", "bl": "banglish", "bl_translit": "banglish"}
NB, SEED, P_RBO = 10000, 20260926, 0.9
EXCLUDED = "__not_a_brand__"
MODELS = ["claude-sonnet-5", "deepseek-v4-flash", "gemini-3-flash", "gpt-5.6-luna", "grok-4.6", "kimi-k3"]
CHINA = {"deepseek-v4-flash", "kimi-k3"}

# frozen / banked inputs with fixed hashes (the name tables and the v2 set are gated through their records)
GATES = {
    "queries.csv": "9639998a98d605f700f7537fe9a3cfb7ed53975b0b1cb43b7a0bf75b595b5e02",
    "runs/coded/main.final.jsonl": "b40a1cb9d9abc05bb5a42a8a35d46f6c85fee303af8cbc5027a84f84268f4264",
    "runs/extracted/main.primary.jsonl": "983d233be140bcfe666c2070e1bc306a42dd02443da941a6cbc0358fdac2efab",
    "runs/usage_claude-sonnet-5.csv": "553d36ec30c5619b3a0c02d144ac49704a5afe3349e99f6bbfc7258636e2c631",
    "runs/usage_deepseek-v4-flash.csv": "a5554c9abb40d5ed0ba634af2b5a2d305ab6c5654650fe9ac9e8875ce68fc0b2",
    "runs/usage_gemini-3-flash.csv": "1ba02aa585431d1ac613ea42ad1cb507b9d348f1cb71be077a65d18caedabbeb",
    "runs/usage_gpt-5.6-luna.csv": "beaf0907c48a56d673403006ffa56b8ef0ca7ededcacbb34ce80ffa409e7493b",
    "runs/usage_grok-4.6.csv": "e3b9df81fef395380fbaba93f17da0cea8cec50a111b3841277de275978901ac",
    "runs/usage_kimi-k3.csv": "18c37390c1bed40e13651ac81428fe615c3f1b3f8b78dc69f5883b6d1bf14a60",
    "runs/persona_claude-sonnet-5.csv": "5e344137c4aabbb635fe5069103f70e6fc20f106109238e08ac3ffb51117a1dc",
    "runs/persona_deepseek-v4-flash.csv": "2fe04bbcc063ffbacbf36b92d1641b2786bf05e10e63b5dbcc2103764c8bd0f9",
    "runs/persona_gemini-3-flash.csv": "a1284b124823d09b52ee24b1d19e4a1e19254865a6a1991b325a141321779367",
    "runs/persona_gpt-5.6-luna.csv": "2fe04bbcc063ffbacbf36b92d1641b2786bf05e10e63b5dbcc2103764c8bd0f9",
    "runs/persona_grok-4.6.csv": "2fe04bbcc063ffbacbf36b92d1641b2786bf05e10e63b5dbcc2103764c8bd0f9",
    "runs/persona_kimi-k3.csv": "fa65ee5becec2193ce0ab64da5494bbe20e2e529c523d75f73cd9e69201c2c97",
}
EXT_TABLES = ("brand_aliases.expansion.csv", "retailer_classification.expansion.csv", "alias_exclusions.expansion.csv")

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=".")
ap.add_argument("--out", default="ANALYSIS-RESULTS")
ap.add_argument("--glmm-boot", action="store_true", help="also cluster-bootstrap the GLMM contrasts of the primary families")
ap.add_argument("--synthetic", action="store_true", help="skip hash gates (validation on synthetic data only)")
ap.add_argument("--nb", type=int, default=NB, help=argparse.SUPPRESS)          # validation runs only
ap.add_argument("--only", default=None, choices=[None, "rq12"], help=argparse.SUPPRESS)   # calibration runs only
A = ap.parse_args()
ROOT = Path(A.root)
if A.nb != NB and not A.synthetic:
    sys.exit("the number of bootstrap resamples is fixed at 10,000 for real runs")
T0 = time.time()
LOG = []

def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print(s, flush=True)

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

# ---------------------------------------------------------------------------------------------- inputs
inputs = {}
if not A.synthetic:
    for f, want in GATES.items():
        got = sha(ROOT / f)
        if got != want:
            sys.exit(f"INPUT GATE: {f} is not the banked file")
        inputs[f] = got
    rec = json.load(open(ROOT / "EXPANSION-EXTENSION-RECORD.json", encoding="utf-8"))
    for f in EXT_TABLES:
        if sha(ROOT / f) != rec["outputs"][f]:
            sys.exit(f"INPUT GATE: {f} is not the file the extension record registers")
        inputs[f] = rec["outputs"][f]
    rep = (ROOT / "EXPANSION-ANALYSIS-SET-v2-REPORT.md").read_text(encoding="utf-8")
    m = re.search(r"EXPANSION-ANALYSIS-SET-v2\.jsonl` — 3023 rows, sha256 `([0-9a-f]{64})`", rep)
    if not m or sha(ROOT / "EXPANSION-ANALYSIS-SET-v2.jsonl") != m.group(1):
        sys.exit("INPUT GATE: EXPANSION-ANALYSIS-SET-v2.jsonl is not the file its report registers")
    inputs["EXPANSION-ANALYSIS-SET-v2.jsonl"] = m.group(1)
    inputs["EXPANSION-EXTENSION-RECORD.json"] = sha(ROOT / "EXPANSION-EXTENSION-RECORD.json")
else:
    log("*** SYNTHETIC VALIDATION RUN — hash gates skipped; nothing here is a study result ***")

queries = {r["query_id"]: r for r in csv.DictReader(open(ROOT / "queries.csv", encoding="utf-8"))}
CAT = {q: r["category"] for q, r in queries.items()}
ROBUST = {q for q, r in queries.items() if r.get("robust50") == "YES"}

def read_table(name):
    with open(ROOT / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

brand_rows = read_table("brand_aliases.expansion.csv")
BCLASS = {r["canonical_id"]: r["class"] for r in brand_rows}
RCLASS = {r["canonical_id"]: r["class"] for r in read_table("retailer_classification.expansion.csv")}
EXCL_KEYS = {r["surface_folded"] for r in read_table("alias_exclusions.expansion.csv")}

def fold(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s.strip())
    return s.casefold().strip()

AMAP = {}
for r in brand_rows:
    AMAP[fold(r["display_name"])] = r["canonical_id"]
    for al in r["aliases"].split("|"):
        if al.strip():
            AMAP[fold(al)] = r["canonical_id"]
for k in EXCL_KEYS:
    AMAP[k] = EXCLUDED

def resolve(s):
    fs = fold(s)
    if fs in AMAP:
        return AMAP[fs]
    t = fs.split()
    for n in (3, 2, 1):
        if len(t) >= n and " ".join(t[:n]) in AMAP:
            return AMAP[" ".join(t[:n])]
    return None

def bclass(e):
    return BCLASS.get(e)            # None = unclassifiable (not in the name table)

def rclass(e, strict=False):
    if e in RCLASS:
        return RCLASS[e]
    return None if strict else BCLASS.get(e)

# ---- coded corpus: final draw per cell
coded_all = [json.loads(l) for l in open(ROOT / "runs/coded/main.final.jsonl", encoding="utf-8")]
by_cell = defaultdict(list)
for r in coded_all:
    by_cell[(r["model_id"], r["query_id"], r["arm"], int(r["rep"]))].append(r)
final, first_degenerate = {}, {}
for c, rs in by_cell.items():
    rs.sort(key=lambda r: int(r["draw"]))
    final[c] = rs[-1]
    first_degenerate[c] = bool(rs[0]["degenerate"])
CODED_BY_KEY = {r["key"]: r for r in coded_all}
pending = [r for r in final.values() if r["outcome"] == "pending_extractor"]
log(f"coded corpus: {len(coded_all)} rows, {len(final)} cells; dropping {len(pending)} 'pending_extractor' answers "
    "(terminally excluded by the post-freeze primary-extraction record of 16 Sep 2026)")

usage = {}
for m in MODELS:
    p = ROOT / f"runs/usage_{m}.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8")):
            usage[r["key"]] = r
PERSONA = set()
for m in MODELS:
    p = ROOT / f"runs/persona_{m}.csv"
    if p.exists():
        PERSONA |= {r["key"] for r in csv.DictReader(open(p, encoding="utf-8"))}
log(f"usage records: {len(usage)}; persona-marked main-run answers: {len(PERSONA)}")

# ---------------------------------------------------------------------------------------------- layers
def price_list(prs):
    out = []
    for p in prs:
        if isinstance(p, dict):
            out.append((float(p["amount"]), str(p["currency"])))
        else:
            out.append((float(p[0]), str(p[1])))
    return out

def human_layer():
    rows = []
    for l in open(ROOT / "EXPANSION-ANALYSIS-SET-v2.jsonl", encoding="utf-8"):
        r = json.loads(l)
        cr = CODED_BY_KEY.get(r["key"], {})
        rows.append({
            "key": r["key"], "model": r["model_id"], "query": r["query_id"], "arm": r["arm"], "rep": int(r["rep"]),
            "primary": bool(r["in_primary_set"]), "refused": bool(r["refused"]),
            "valid": r["answer_language"] == FORM[r["arm"]], "mixed": r["answer_language"] == "mixed",
            "truncated": cr.get("finish_reason") == "length", "persona": r["key"] in PERSONA,
            "brands": list(r["brands"]), "brands_order": list(r["brands_order"]),
            "brands_x": list(r["brands_incl_excluded"]), "recommended": list(r["recommended"]),
            "retailers": list(r["retailers"]), "retailers_order": list(r["retailers_order"]),
            "prices": price_list(r["prices"]),
        })
    return rows

def corpus_layer():
    rows = []
    for c, r in final.items():
        if r["outcome"] == "pending_extractor":
            continue
        u = usage.get(r["key"], {})
        ct = u.get("completion_tokens")
        rows.append({
            "key": r["key"], "model": c[0], "query": c[1], "arm": c[2], "rep": c[3],
            "outcome": r["outcome"], "answer_language": r["answer_language"], "script_class": r["script_class"],
            "degenerate_first": first_degenerate[c], "truncated": r["finish_reason"] == "length",
            "persona": r["key"] in PERSONA, "mixed": r["answer_language"] == "mixed",
            "completion_tokens": float(ct) if ct not in (None, "", "None") else float("nan"),
            "content_chars": float(u.get("content_chars") or r.get("content_chars") or "nan"),
        })
    return rows

def machine_layer():
    ext = {}
    for l in open(ROOT / "runs/extracted/main.primary.jsonl", encoding="utf-8"):
        r = json.loads(l)
        if r.get("extraction") is None or r.get("schema_errors"):
            continue
        ext[r["subject_key"]] = r["extraction"]
    rows, n_noext = [], 0
    for c, r in final.items():
        if r["outcome"] not in ("valid", "language_reversion", "refusal"):
            continue
        e = ext.get(r["key"])
        if e is None:
            n_noext += 1
            continue
        def canon(items, keep_excl=False):
            out = []
            for x in items or []:
                if not str(x).strip():
                    continue
                cid = resolve(x)
                if cid == EXCLUDED:
                    if not keep_excl:
                        continue
                    cid = fold(x)
                v = cid or fold(x)
                if v not in out:
                    out.append(v)
            return out
        b = canon(e.get("brands"))
        rows.append({
            "key": r["key"], "model": c[0], "query": c[1], "arm": c[2], "rep": c[3],
            "primary": r["outcome"] in ("valid", "language_reversion"), "refused": r["outcome"] == "refusal",
            "valid": r["outcome"] == "valid", "mixed": r["answer_language"] == "mixed",
            "truncated": r["finish_reason"] == "length", "persona": r["key"] in PERSONA,
            "brands": sorted(b), "brands_order": b, "brands_x": sorted(canon(e.get("brands"), True)),
            "recommended": sorted(canon(e.get("recommended"))),
            "retailers": sorted(canon(e.get("retailers"))), "retailers_order": canon(e.get("retailers")),
            "prices": price_list(e.get("prices") or []),
        })
    log(f"machine layer: {len(rows)} answers with an extraction; {n_noext} without one (terminal schema failures)")
    return rows

# ---------------------------------------------------------------------------------------------- bootstrap
class Boot:
    """Fixed cluster-resample counts for one layer: C[b, j] = times query j is drawn in replicate b."""
    def __init__(self, qids, nb, seed):
        self.q = sorted(qids)
        self.ix = {q: i for i, q in enumerate(self.q)}
        rng = np.random.default_rng(seed)
        n = len(self.q)
        self.C = rng.multinomial(n, np.full(n, 1.0 / n), size=nb).astype(np.float64)
        self.seed, self.nb = seed, nb

    def vec(self, d):
        v = np.zeros(len(self.q))
        for q, x in d.items():
            v[self.ix[q]] += x
        return v

    def mean(self, per_query):
        """mean of per-query values over the resampled defined queries"""
        v, m = self.vec(per_query), self.vec({q: 1.0 for q in per_query})
        num, den = self.C @ v, self.C @ m
        ok = den > 0
        return num[ok] / den[ok], int((~ok).sum())

    def ratio(self, num, den):
        n, d = self.C @ self.vec(num), self.C @ self.vec(den)
        with np.errstate(invalid="ignore", divide="ignore"):
            return n / d

def pct(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return [None, None]
    lo, hi = np.percentile(x, [2.5, 97.5])
    return [float(lo), float(hi)]

# ---------------------------------------------------------------------------------------------- similarity
def jaccard(a, b):
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)

def rbo_ext(S, L, p=P_RBO):
    """Extrapolated RBO for two top-k lists without ties (Webber, Moffat & Zobel 2010, eqs. 30/32).
    Conventions mirroring F.2's Jaccard: both empty -> 1; exactly one empty -> 0."""
    S, L = list(dict.fromkeys(S)), list(dict.fromkeys(L))
    if not S and not L:
        return 1.0
    if not S or not L:
        return 0.0
    if len(S) > len(L):
        S, L = L, S
    s, l = len(S), len(L)
    seen_s, seen_l, X = set(), set(), [0] * (l + 1)
    ov = 0
    for d in range(1, l + 1):
        x_new = L[d - 1]
        if d <= s:
            y_new = S[d - 1]
            if y_new == x_new:
                ov += 1
            else:
                if y_new in seen_l:
                    ov += 1
                if x_new in seen_s:
                    ov += 1
            seen_s.add(y_new)
        else:
            if x_new in seen_s:
                ov += 1
        seen_l.add(x_new)
        X[d] = ov
    Xs, Xl = X[s], X[l]
    sum1 = sum(X[d] / d * p ** d for d in range(1, l + 1))
    sum2 = sum(Xs * (d - s) / (s * d) * p ** d for d in range(s + 1, l + 1))
    return (1 - p) / p * (sum1 + sum2) + ((Xl - Xs) / l + Xs / s) * p ** l

def excess(A, Bs, sim):
    """Delta = D_btw - mean(D_win(A), D_win(B)); needs >= 2 answers per arm."""
    if len(A) < 2 or len(Bs) < 2:
        return None
    dbtw = 1 - np.mean([sim(x, y) for x in A for y in Bs])
    dwa = 1 - np.mean([sim(A[i], A[j]) for i in range(len(A)) for j in range(i + 1, len(A))])
    dwb = 1 - np.mean([sim(Bs[i], Bs[j]) for i in range(len(Bs)) for j in range(i + 1, len(Bs))])
    return float(dbtw - (dwa + dwb) / 2)

def wilcoxon(vals):
    v = np.asarray(vals, dtype=float)
    nz = int((v != 0).sum())
    if nz == 0:
        return {"stat": None, "p": 1.0, "n_nonzero": 0, "note": "all differences zero"}
    try:
        r = stats.wilcoxon(v, zero_method="wilcox", alternative="two-sided", method="auto")
        return {"stat": float(r.statistic), "p": float(r.pvalue), "n_nonzero": nz}
    except ValueError as e:
        return {"stat": None, "p": 1.0, "n_nonzero": nz, "note": str(e)}

# ---------------------------------------------------------------------------------------------- GLMM bridge
R_SCRIPT = Path(__file__).with_name("n1_glmm.R")
TMP = Path(tempfile.mkdtemp(prefix="n1glmm_"))
_job_seq = [0]

def glmm(jobs):
    """jobs: list of dicts {id, rows: [(query, arm, y)], arms, contrasts, boot: Boot|None}"""
    if not jobs:
        return {}
    spec = []
    for j in jobs:
        _job_seq[0] += 1
        dp = TMP / f"d{_job_seq[0]}.csv"
        with open(dp, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["query", "arm", "y"])
            w.writerows(j["rows"])
        s = {"id": j["id"], "data": str(dp), "arms": j["arms"], "contrasts": [list(c) for c in j["contrasts"]],
             "boot": None, "re": j.get("re", "query")}
        if j.get("boot") is not None:
            bp = TMP / f"b{_job_seq[0]}.csv"
            np.savetxt(bp, j["boot"].C.astype(int), fmt="%d", delimiter=",")
            s["boot"], s["boot_queries"] = str(bp), j["boot"].q
        spec.append(s)
    jp, op = TMP / f"jobs{_job_seq[0]}.json", TMP / f"out{_job_seq[0]}.json"
    json.dump(spec, open(jp, "w"))
    r = subprocess.run(["Rscript", str(R_SCRIPT), str(jp), str(op)], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"n1_glmm.R failed:\n{r.stderr[-3000:]}")
    res = json.load(open(op))
    return {x["id"]: x for x in res}

# ---------------------------------------------------------------------------------------------- estimators
def cells(rows, field, filt):
    d = defaultdict(list)
    for r in rows:
        if filt(r):
            d[(r["model"], r["query"], r["arm"])].append(r[field])
    return d

def setdiv(rows, field, sim, contrasts, filt, boot, label):
    """RQ1-type excess divergence per model x contrast."""
    cl = cells(rows, field, filt)
    qs = sorted({r["query"] for r in rows})
    out = {}
    for m in MODELS:
        for a, b in contrasts:
            per_q = {}
            for q in qs:
                v = excess(cl.get((m, q, a), []), cl.get((m, q, b), []), sim)
                if v is not None:
                    per_q[q] = v
            k = f"{m}|{a}-{b}"
            if not per_q:
                out[k] = {"n_query": 0}
                continue
            vals = np.array(list(per_q.values()))
            reps, dropped = boot.mean(per_q)
            out[k] = {"n_query": len(per_q), "mean_delta": float(vals.mean()), "ci": pct(reps),
                      "median_delta": float(np.median(vals)), "boot_dropped": dropped, "test": wilcoxon(vals)}
    return {"label": label, "results": out}

def setdiv_perm(rows, field, sim, contrasts, filt, seed, nperm, label):
    """RQ1 randomization test (declared sensitivity): under 'arm does not matter', the answers of one
    query x model cell pair are exchangeable across the two arms, so every assignment of the pooled answers
    to arms of the observed sizes is equally likely. Statistic: mean Delta over queries; null distribution:
    each query's Delta recomputed under a uniformly drawn assignment, independently across queries;
    two-sided p = min(1, 2 min(P(T* >= t), P(T* <= t))) with the (k + 1)/(n + 1) correction."""
    from itertools import combinations
    cl = cells(rows, field, filt)
    qs = sorted({r["query"] for r in rows})
    rng = np.random.default_rng(seed)
    out = {}
    for m in MODELS:
        for a, b in contrasts:
            vals = []
            for q in qs:
                A_, B_ = cl.get((m, q, a), []), cl.get((m, q, b), [])
                if len(A_) < 2 or len(B_) < 2:
                    continue
                pool = A_ + B_
                alts = []
                for ia in combinations(range(len(pool)), len(A_)):
                    sa = set(ia)
                    alts.append(excess([pool[i] for i in ia], [pool[i] for i in range(len(pool)) if i not in sa], sim))
                vals.append((excess(A_, B_, sim), np.array(alts)))
            k = f"{m}|{a}-{b}"
            if not vals:
                out[k] = {"n_query": 0}
                continue
            t = float(np.mean([v for v, _ in vals]))
            draws = np.zeros(nperm)
            for _, alts in vals:
                draws += alts[rng.integers(0, len(alts), size=nperm)]
            draws /= len(vals)
            hi = (np.sum(draws >= t - 1e-12) + 1) / (nperm + 1)
            lo = (np.sum(draws <= t + 1e-12) + 1) / (nperm + 1)
            out[k] = {"n_query": len(vals), "mean_delta": t, "p": float(min(1.0, 2 * min(hi, lo))),
                      "null_mean": float(draws.mean())}
    return {"label": label, "results": out}

def per_answer_mentions(r, spec):
    """(local, classified, ambiguous, unclassifiable) counts for one answer under a mention spec."""
    items = spec["items"](r)
    loc = glob = amb = unc = 0
    for e, cls in items:
        if cls is None:
            unc += 1
        elif cls == "ambiguous":
            if spec.get("ambiguous") == "local":
                loc += 1
            elif spec.get("ambiguous") == "global":
                glob += 1
            else:
                amb += 1
        elif cls == "local":
            loc += 1
        else:
            glob += 1
    return loc, loc + glob, amb, unc

def share_outcome(rows, spec, arms, contrasts, filt, boot, label, glmm_boot=None, re="query"):
    """Mention- or entry-level binary share (RQ2 local share, local-retailer share, BDT share).
    spec["items"](r) -> list of (entry, class) where class in local/global/ambiguous/None,
    or for BDT: spec["binary"](r) -> list of 0/1 entries."""
    out, jobs = {}, []
    for m in MODELS:
        num, den = defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(float))
        rowsm, amb_n, unc_n, tot_n = [], Counter(), Counter(), Counter()
        per_answer = defaultdict(lambda: defaultdict(list))     # fallback: arm -> query -> [per-answer share]
        for r in rows:
            if r["model"] != m or r["arm"] not in arms or not filt(r):
                continue
            if "binary" in spec:
                ys = spec["binary"](r)
                y1, n = sum(ys), len(ys)
                tot_n[r["arm"]] += n
            else:
                y1, n, amb, unc = per_answer_mentions(r, spec)
                amb_n[r["arm"]] += amb
                unc_n[r["arm"]] += unc
                tot_n[r["arm"]] += n + amb + unc
                ys = [1] * y1 + [0] * (n - y1)
            num[r["arm"]][r["query"]] += y1
            den[r["arm"]][r["query"]] += n
            if n:
                per_answer[r["arm"]][r["query"]].append(y1 / n)
            rowsm += [(r["query"], r["arm"], y) for y in ys]
        res = {"arms": {}, "contrasts": {}}
        # query-level estimand (B.2: the query is the unit of analysis): per-answer share (D.3), averaged over
        # the reps of each query x arm cell, then averaged over queries; contrasts = mean paired difference
        cellm = {a: {q: float(np.mean(v)) for q, v in per_answer.get(a, {}).items()} for a in arms}
        for a in arms:
            N, D = sum(num[a].values()), sum(den[a].values())
            reps, _ = boot.mean(cellm[a]) if cellm[a] else (np.array([]), 0)
            res["arms"][a] = {"share": float(np.mean(list(cellm[a].values()))) if cellm[a] else None,
                              "ci": pct(reps), "n_query": len(cellm[a]), "y1": N, "n": D,
                              "pooled_share": (N / D) if D else None}
            if "binary" not in spec:
                res["arms"][a]["ambiguous_rate"] = (amb_n[a] / tot_n[a]) if tot_n[a] else None
                res["arms"][a]["unclassifiable_rate"] = (unc_n[a] / tot_n[a]) if tot_n[a] else None
        for a, b in contrasts:
            common = sorted(set(cellm[a]) & set(cellm[b]))
            d = {q: cellm[a][q] - cellm[b][q] for q in common}
            reps, _ = boot.mean(d) if d else (np.array([]), 0)
            res["contrasts"][f"{a}-{b}"] = {"diff": float(np.mean(list(d.values()))) if d else None,
                                            "ci": pct(reps), "n_query": len(d), "_paired": d}
        out[m] = res
        jobs.append({"id": m, "rows": rowsm, "arms": arms, "contrasts": contrasts,
                     "boot": glmm_boot, "re": re})
    fits = glmm(jobs)
    for m in MODELS:
        f = fits[m]
        out[m]["glmm"] = {k: f.get(k) for k in ("status", "optimizer", "singular", "random_intercept_sd", "cell_sd",
                                                   "formula", "n", "n_query", "tried", "events")}
        for a, b in contrasts:
            c = out[m]["contrasts"][f"{a}-{b}"]
            if f["status"] == "ok":
                g = f["contrasts"][f"{a}-{b}"]
                c["log_odds"] = {k: g[k] for k in ("estimate", "se", "z", "p", "ci_low", "ci_high")}
                if f.get("boot"):
                    c["log_odds"]["boot_ci"] = f["boot"]["ci"][f"{a}-{b}"]
                    c["log_odds"]["boot_dropped"] = f["boot"]["dropped"]
                c["test"] = {"method": "glmm_wald", "p": g["p"]}
            else:
                # F.3 fallback: per-query rate averaged over reps, paired Wilcoxon over queries
                d = c["_paired"]
                w = wilcoxon(list(d.values())) if d else {"p": 1.0, "n_nonzero": 0, "note": "no paired queries"}
                c["fallback"] = {"n_query": len(d), "wilcoxon": w, "reason": f["status"]}
                c["test"] = {"method": "fallback_paired_wilcoxon", "p": w["p"]}
            c.pop("_paired", None)
    return {"label": label, "results": out}

def answer_binary(rows, yfun, arms, contrasts, filt, boot, label, glmm_boot=None, re="query"):
    spec = {"binary": lambda r: [yfun(r)]}
    return share_outcome(rows, spec, arms, contrasts, filt, boot, label, glmm_boot, re)

def length_lmm(rows, arms, contrasts, filt, boot, label):
    out = {}
    for m in MODELS:
        d = [r for r in rows if r["model"] == m and r["arm"] in arms and filt(r)]
        dropped = sum(1 for r in d if not (r["completion_tokens"] > 0))
        d = [r for r in d if r["completion_tokens"] > 0]
        df = pd.DataFrame({"y": [math.log(r["completion_tokens"]) for r in d], "arm": [r["arm"] for r in d],
                           "query": [r["query"] for r in d]})
        res = {"n": len(df), "dropped_nonpositive_tokens": dropped, "arms": {}, "contrasts": {}}
        cell = {a: defaultdict(list) for a in arms}
        for r in d:
            cell[r["arm"]][r["query"]].append(math.log(r["completion_tokens"]))
        cellm = {a: {q: float(np.mean(v)) for q, v in cell[a].items()} for a in arms}
        for a in arms:
            reps, _ = boot.mean(cellm[a]) if cellm[a] else (np.array([]), 0)
            res["arms"][a] = {"mean_log_tokens": float(np.mean(list(cellm[a].values()))) if cellm[a] else None,
                              "ci": pct(reps), "n_query": len(cellm[a])}
        paired = {}
        for a, b in contrasts:
            common = sorted(set(cellm[a]) & set(cellm[b]))
            paired[(a, b)] = {q: cellm[a][q] - cellm[b][q] for q in common}
        try:
            import warnings
            with warnings.catch_warnings(record=True) as wl:
                warnings.simplefilter("always")
                mod = smf.mixedlm(f"y ~ C(arm, Treatment('{arms[0]}'))", df, groups=df["query"])
                md = mod.fit(reml=True)
                if not md.converged:
                    md = mod.fit(reml=True, method=["powell", "lbfgs"])
            res["lmm_warnings"] = sorted({str(w.message)[:160] for w in wl})
            res["lmm_converged"] = bool(md.converged)
            res["query_sd"] = float(np.sqrt(max(float(md.cov_re.iloc[0, 0]), 0.0)))
            fe, V = md.fe_params, md.cov_params()
            names = list(fe.index)
            def L(a):
                v = pd.Series(0.0, index=names)
                if a != arms[0]:
                    v[f"C(arm, Treatment('{arms[0]}'))[T.{a}]"] = 1.0
                return v
            for a, b in contrasts:
                l = L(a) - L(b)
                est = float((l * fe).sum())
                se = float(np.sqrt(l.values @ V.loc[names, names].values @ l.values))
                z = est / se
                p = float(2 * stats.norm.sf(abs(z)))
                dq = paired[(a, b)]
                ra, _ = boot.mean(dq) if dq else (np.array([]), 0)
                res["contrasts"][f"{a}-{b}"] = {"diff_mean_log": float(np.mean(list(dq.values()))) if dq else None,
                                                "ci": pct(ra), "n_query": len(dq),
                                                "lmm": {"estimate": est, "se": se, "z": z, "p": p,
                                                        "ratio": math.exp(est), "converged": bool(md.converged)}}
        except Exception as e:
            res["error"] = str(e)
        out[m] = res
    return {"label": label, "results": out}

def holm(fam_results, keys):
    """keys: list of (model, contrast) -> p from result dict; returns adjusted p and reject flags."""
    ps = [p for _, p in keys]
    rej, padj, _, _ = multipletests(ps, alpha=0.05, method="holm")
    return {f"{k}": {"p": p, "p_holm": float(pa), "reject": bool(rj)} for (k, p), pa, rj in zip(keys, padj, rej)}

# ---------------------------------------------------------------------------------------------- run
H = human_layer()
Cp = corpus_layer()
M = machine_layer()
log(f"human layer: {len(H)} answers; corpus layer: {len(Cp)} answers")
BH = Boot({r["query"] for r in H}, A.nb, SEED)
BC = Boot({r["query"] for r in Cp}, A.nb, SEED + 1)
BH10 = Boot({r["query"] for r in H if r["arm"] == "bl_translit"}, A.nb, SEED + 2)
BC10 = Boot({r["query"] for r in Cp if r["arm"] == "bl_translit"}, A.nb, SEED + 3)
BM = BC                                   # machine layer = same queries and resample counts as the corpus
log(f"bootstrap: human {len(BH.q)} queries, corpus {len(BC.q)}, F.10 human {len(BH10.q)}, F.10 corpus {len(BC10.q)}; "
    f"{A.nb} resamples each")

def P(r):                                  # F.6 primary set (human / machine layers)
    return r["primary"]

SENS = {  # F.6 (a), (c), (d), persona
    "valid_only": lambda r: r["primary"] and r["valid"],
    "no_truncated": lambda r: r["primary"] and not r["truncated"],
    "no_mixed": lambda r: r["primary"] and not r["mixed"],
    "no_persona": lambda r: r["primary"] and not r["persona"],
}

def brand_items(field="brands"):
    return lambda r: [(e, bclass(e)) for e in r[field]]

def excl_items(as_class):
    def f(r):
        base = [(e, bclass(e)) for e in r["brands"]]
        extra = [e for e in r["brands_x"] if e not in set(r["brands"])]
        return base + [(e, as_class) for e in extra]
    return f

def retail_items(strict=False):
    return lambda r: [(e, rclass(e, strict)) for e in r["retailers"]]

def has_price(r, drop_zero=False):
    return int(any((a != 0) or not drop_zero for a, _ in r["prices"]))

def bdt_entries(r, drop_zero=False, drop_unstated=False):
    ys = []
    for a, c in r["prices"]:
        if drop_zero and a == 0:
            continue
        if drop_unstated and c == "unstated":
            continue
        ys.append(int(c == "BDT"))
    return ys

R = {"meta": {}, "primary": {}, "secondary": {}, "sensitivity": {}, "exploratory": {}, "holm": {}}
PRIM_BOOT_H = BH if A.glmm_boot else None
PRIM_BOOT_C = BC if A.glmm_boot else None

# ---- RQ1 (primary: human, Jaccard) ------------------------------------------------------------
R["primary"]["RQ1_excess_divergence"] = setdiv(H, "brands", jaccard, C3, P, BH, "RQ1 excess divergence (Jaccard), human layer")
if A.only == "rq12":
    if not A.synthetic:
        sys.exit("--only is for synthetic calibration runs")
    R["primary"]["RQ2_local_share"] = share_outcome(H, {"items": brand_items()}, ARMS3, C3, P, BH, "RQ2", PRIM_BOOT_H)
    R["sensitivity"]["RQ1_permutation"] = setdiv_perm(H, "brands", jaccard, C3, P, SEED + 4, max(A.nb, 2000), "RQ1 permutation")
    R["sensitivity"]["RQ2_het"] = share_outcome(H, {"items": brand_items()}, ARMS3, C3, P, BH, "RQ2 het", None, "query+cell")
    R["sensitivity"]["RQ4_price_het"] = answer_binary(H, has_price, ARMS3, C3, P, BH, "price het", None, "query+cell")
    R["primary"]["RQ4_price_mention"] = answer_binary(H, has_price, ARMS3, C3, P, BH, "price", None)
    json.dump(R, open(ROOT / f"{A.out}.json", "w"), default=lambda o: None)
    sys.exit(0)
R["secondary"]["RQ1_rbo"] = setdiv(H, "brands_order", rbo_ext, C3, P, BH, "RQ1 excess divergence (RBO_ext p=0.9, first-mention order)")
R["secondary"]["RQ4_retailer_overlap"] = setdiv(H, "retailers", jaccard, C3, P, BH, "retailer-set excess divergence (Jaccard)")
for s, f in SENS.items():
    R["sensitivity"][f"RQ1_{s}"] = setdiv(H, "brands", jaccard, C3, f, BH, f"RQ1 sensitivity: {s}")
R["sensitivity"]["RQ1_permutation"] = setdiv_perm(H, "brands", jaccard, C3, P, SEED + 4, A.nb,
                                                  "RQ1 randomization test (answers exchangeable across arms within query x model)")
R["sensitivity"]["RQ1_exclusions_retained"] = setdiv(H, "brands_x", jaccard, C3, P, BH, "RQ1 with not-a-brand names retained (17th record)")

# ---- RQ2 (primary: human, mention-level GLMM) -------------------------------------------------------
R["primary"]["RQ2_local_share"] = share_outcome(H, {"items": brand_items()}, ARMS3, C3, P, BH,
                                                "RQ2 local share (ambiguous and unclassifiable excluded)", PRIM_BOOT_H)
R["sensitivity"]["RQ2_ambiguous_local"] = share_outcome(H, {"items": brand_items(), "ambiguous": "local"}, ARMS3, C3, P, BH, "C.5: ambiguous counted local")
R["sensitivity"]["RQ2_ambiguous_global"] = share_outcome(H, {"items": brand_items(), "ambiguous": "global"}, ARMS3, C3, P, BH, "C.5: ambiguous counted global")
R["sensitivity"]["RQ2_recommended_only"] = share_outcome(H, {"items": brand_items("recommended")}, ARMS3, C3, P, BH, "F.3 recommended-only")
R["sensitivity"]["RQ2_excluded_as_local"] = share_outcome(H, {"items": excl_items("local")}, ARMS3, C3, P, BH, "17th record bound: removed mentions counted local")
R["sensitivity"]["RQ2_excluded_as_global"] = share_outcome(H, {"items": excl_items("global")}, ARMS3, C3, P, BH, "17th record bound: removed mentions counted global")
for s, f in SENS.items():
    R["sensitivity"][f"RQ2_{s}"] = share_outcome(H, {"items": brand_items()}, ARMS3, C3, f, BH, f"RQ2 sensitivity: {s}")

# ---- RQ4 (primary: human) ----------------------------------------------------------------------
R["primary"]["RQ4_price_mention"] = answer_binary(H, has_price, ARMS3, C3, P, BH, "RQ4 price-mention rate", PRIM_BOOT_H)
R["primary"]["RQ4_bdt_share"] = share_outcome(H, {"binary": bdt_entries}, ARMS3, C3, P, BH, "RQ4 BDT share of stated prices", PRIM_BOOT_H)
R["sensitivity"]["RQ4_price_mention_zero_removed"] = answer_binary(H, lambda r: has_price(r, True), ARMS3, C3, P, BH, "15th record: zero-amount entries removed")
R["sensitivity"]["RQ4_bdt_share_zero_removed"] = share_outcome(H, {"binary": lambda r: bdt_entries(r, True)}, ARMS3, C3, P, BH, "15th record: zero-amount entries removed")
R["sensitivity"]["RQ4_bdt_share_unstated_excluded"] = share_outcome(H, {"binary": lambda r: bdt_entries(r, False, True)}, ARMS3, C3, P, BH, "unstated currency left out of the denominator")
for s, f in SENS.items():
    R["sensitivity"][f"RQ4_price_mention_{s}"] = answer_binary(H, has_price, ARMS3, C3, f, BH, f"RQ4 price-mention sensitivity: {s}")
    R["sensitivity"][f"RQ4_bdt_share_{s}"] = share_outcome(H, {"binary": bdt_entries}, ARMS3, C3, f, BH, f"RQ4 BDT-share sensitivity: {s}")
R["secondary"]["RQ4_local_retailer_share"] = share_outcome(H, {"items": retail_items()}, ARMS3, C3, P, BH, "local-retailer share (F3 list; brand-table class for entities absent from it)")
R["sensitivity"]["RQ4_local_retailer_share_strict"] = share_outcome(H, {"items": retail_items(True)}, ARMS3, C3, P, BH, "local-retailer share, F3 list only")

# ---- RQ5 (primary: corpus) ------------------------------------------------------------------------
def nonref_nondeg(r):
    return r["outcome"] in ("valid", "language_reversion")
def nondeg(r):
    return r["outcome"] in ("valid", "language_reversion", "refusal")
R["primary"]["RQ5_reversion"] = answer_binary(Cp, lambda r: int(r["outcome"] == "language_reversion"), ["bl", "bn"], [("bn", "bl")],
                                              nonref_nondeg, BC, "RQ5 reversion (bn vs bl)", PRIM_BOOT_C)
R["primary"]["RQ5_refusal"] = answer_binary(Cp, lambda r: int(r["outcome"] == "refusal"), ARMS3, C3, nondeg, BC, "RQ5 refusal", PRIM_BOOT_C)
R["exploratory"]["RQ5_degeneracy_first_draw"] = answer_binary(Cp, lambda r: int(r["degenerate_first"]), ARMS3, C3, lambda r: True, BC, "first-draw degeneracy")
R["exploratory"]["RQ5_length"] = length_lmm(Cp, ARMS3, C3, nonref_nondeg, BC, "F.5 length: log completion tokens")
R["sensitivity"]["RQ5_length_valid_only"] = length_lmm(Cp, ARMS3, C3, lambda r: r["outcome"] == "valid", BC, "F.5 length, valid only")
R["sensitivity"]["RQ5_refusal_human"] = answer_binary(H, lambda r: int(r["refused"]), ARMS3, C3, lambda r: True, BH, "RQ5 refusal on human labels (12th record)")
R["sensitivity"]["RQ5_reversion_no_persona"] = answer_binary(Cp, lambda r: int(r["outcome"] == "language_reversion"), ["bl", "bn"], [("bn", "bl")],
                                                             lambda r: nonref_nondeg(r) and not r["persona"], BC, "RQ5 reversion, persona answers removed")
R["sensitivity"]["RQ5_refusal_no_persona"] = answer_binary(Cp, lambda r: int(r["outcome"] == "refusal"), ARMS3, C3,
                                                           lambda r: nondeg(r) and not r["persona"], BC, "RQ5 refusal, persona answers removed")
# heterogeneity sensitivity for every GLMM-tested primary family: + (1 | query:arm)
R["sensitivity"]["RQ2_local_share_het"] = share_outcome(H, {"items": brand_items()}, ARMS3, C3, P, BH, "RQ2 with (1|query:arm)", None, "query+cell")
R["sensitivity"]["RQ4_price_mention_het"] = answer_binary(H, has_price, ARMS3, C3, P, BH, "RQ4 price-mention with (1|query:arm)", None, "query+cell")
R["sensitivity"]["RQ4_bdt_share_het"] = share_outcome(H, {"binary": bdt_entries}, ARMS3, C3, P, BH, "RQ4 BDT share with (1|query:arm)", None, "query+cell")
R["sensitivity"]["RQ5_reversion_het"] = answer_binary(Cp, lambda r: int(r["outcome"] == "language_reversion"), ["bl", "bn"], [("bn", "bl")],
                                                      nonref_nondeg, BC, "RQ5 reversion with (1|query:arm)", None, "query+cell")
R["sensitivity"]["RQ5_refusal_het"] = answer_binary(Cp, lambda r: int(r["outcome"] == "refusal"), ARMS3, C3, nondeg, BC,
                                                    "RQ5 refusal with (1|query:arm)", None, "query+cell")
# reversion reported by the answer's language/script class, never pooled (D.4)
brk = {}
for m in MODELS:
    for a in ("bn", "bl", "bl_translit"):
        rs = [r for r in Cp if r["model"] == m and r["arm"] == a and nonref_nondeg(r)]
        n = len(rs)
        cl = Counter(r["answer_language"] for r in rs if r["outcome"] == "language_reversion")
        num = {k: defaultdict(float) for k in cl}
        den = defaultdict(float)
        for r in rs:
            den[r["query"]] += 1
            if r["outcome"] == "language_reversion":
                num[r["answer_language"]][r["query"]] += 1
        B_ = BC10 if a == "bl_translit" else BC
        brk[f"{m}|{a}"] = {"n": n, "by_answer_language": {k: {"count": v, "rate": v / n if n else None,
                                                               "ci": pct(B_.ratio(num[k], den))} for k, v in sorted(cl.items())}}
R["primary"]["RQ5_reversion_breakdown"] = {"label": "reversion by answer language (D.4: reported by class, never pooled)", "results": brk}
R["exploratory"]["RQ5_reversion_to_english"] = answer_binary(Cp, lambda r: int(r["outcome"] == "language_reversion" and r["answer_language"] == "en"),
                                                             ["bl", "bn"], [("bn", "bl")], nonref_nondeg, BC, "reversion to English only (like-for-like)")

# ---- F.10 (robust50; human = the expansion's bl_translit queries; corpus machine layer secondary) -----------
H10 = [r for r in H if r["query"] in set(BH10.q)]
R["secondary"]["F10_RQ1"] = setdiv(H10, "brands", jaccard, C10, P, BH10, "F.10 excess divergence, human layer")
R["secondary"]["F10_RQ2"] = share_outcome(H10, {"items": brand_items()}, ["bl_translit", "bn", "bl"], C10, P, BH10, "F.10 local share, human layer")
M10 = [r for r in M if r["query"] in set(BC10.q)]
R["secondary"]["F10_RQ1_machine"] = setdiv(M10, "brands", jaccard, C10, P, BC10, "F.10 excess divergence, machine layer")
R["secondary"]["F10_RQ2_machine"] = share_outcome(M10, {"items": brand_items()}, ["bl_translit", "bn", "bl"], C10, P, BC10, "F.10 local share, machine layer")

# ---- machine layer (secondary, descriptive) ----------------------------------------------------------------
R["secondary"]["machine_RQ1"] = setdiv(M, "brands", jaccard, C3, P, BM, "machine layer: RQ1 excess divergence")
R["secondary"]["machine_RQ2"] = share_outcome(M, {"items": brand_items()}, ARMS3, C3, P, BM, "machine layer: RQ2 local share")
R["secondary"]["machine_RQ4_price_mention"] = answer_binary(M, has_price, ARMS3, C3, P, BM, "machine layer: price-mention rate")
R["secondary"]["machine_RQ4_bdt_share"] = share_outcome(M, {"binary": bdt_entries}, ARMS3, C3, P, BM, "machine layer: BDT share")
R["sensitivity"]["machine_RQ4_price_mention_zero_removed"] = answer_binary(M, lambda r: has_price(r, True), ARMS3, C3, P, BM, "machine layer, zero-amount removed")
R["sensitivity"]["machine_RQ4_bdt_share_zero_removed"] = share_outcome(M, {"binary": lambda r: bdt_entries(r, True)}, ARMS3, C3, P, BM, "machine layer, zero-amount removed")
# human-machine concordance on the expansion answers (same keys, same estimators, machine labels)
hk = {r["key"] for r in H}
Mx = [r for r in M if r["key"] in hk]
R["secondary"]["concordance_RQ1_machine_on_expansion"] = setdiv(Mx, "brands", jaccard, C3, P, BH, "machine labels on the expansion answers: RQ1")
R["secondary"]["concordance_RQ2_machine_on_expansion"] = share_outcome(Mx, {"items": brand_items()}, ARMS3, C3, P, BH, "machine labels on the expansion answers: RQ2")

# ---- F.9 (descriptive: China-trained vs Western) ---------------------------------------------------------
def cell_means(rows, val, filt):
    d = defaultdict(list)
    for r in rows:
        if filt(r):
            v = val(r)
            if v is not None:
                d[(r["model"], r["query"], r["arm"])].append(v)
    return {k: float(np.mean(v)) for k, v in d.items()}

def local_share_answer(r):
    loc, n, _, _ = per_answer_mentions(r, {"items": brand_items()})
    return (loc / n) if n else None

f9 = {}
spec9 = (("brands_per_answer", H, lambda r: float(len(r["brands"])), P, BH, ARMS3),
         ("local_share", H, local_share_answer, P, BH, ARMS3),
         ("reversion_rate", Cp, lambda r: float(r["outcome"] == "language_reversion"), nonref_nondeg, BC, ["bn", "bl"]))
for name, rows, val, filt, bt, arms in spec9:
    cm = cell_means(rows, val, filt)
    for a in arms:
        grp_q = {}
        for grp, mem in (("china_trained", sorted(CHINA)), ("western", sorted(set(MODELS) - CHINA))):
            per_q = defaultdict(list)
            for (m, q, arm), v in cm.items():
                if arm == a and m in mem:
                    per_q[q].append(v)
            gq = {q: float(np.mean(v)) for q, v in per_q.items()}     # models weighted equally within a query
            grp_q[grp] = gq
            reps, _ = bt.mean(gq) if gq else (np.array([]), 0)
            f9[f"{name}|{a}|{grp}"] = {"value": float(np.mean(list(gq.values()))) if gq else None, "ci": pct(reps),
                                       "n_query": len(gq), "models": mem}
        common = sorted(set(grp_q["china_trained"]) & set(grp_q["western"]))
        dq = {q: grp_q["china_trained"][q] - grp_q["western"][q] for q in common}
        reps, _ = bt.mean(dq) if dq else (np.array([]), 0)
        f9[f"{name}|{a}|china_minus_western"] = {"value": float(np.mean(list(dq.values()))) if dq else None,
                                                 "ci": pct(reps), "n_query": len(dq)}
R["exploratory"]["F9_china_vs_western"] = {"label": "F.9 descriptive with CIs only; n = 6 systems precludes model-level inference",
                                           "results": f9}

# ---- F.7 Holm within each primary family ------------------------------------------------------------------
FAM = {"RQ1_excess_divergence": C3, "RQ2_local_share": C3, "RQ4_bdt_share": C3, "RQ4_price_mention": C3,
       "RQ5_reversion": [("bn", "bl")], "RQ5_refusal": C3}
for fam, cons in FAM.items():
    keys = []
    for m in MODELS:
        for a, b in cons:
            if fam == "RQ1_excess_divergence":
                x = R["primary"][fam]["results"][f"{m}|{a}-{b}"]
                p = x.get("test", {}).get("p", 1.0) if x.get("n_query") else 1.0
            else:
                p = R["primary"][fam]["results"][m]["contrasts"][f"{a}-{b}"]["test"]["p"]
            keys.append((f"{m}|{a}-{b}", 1.0 if p is None else float(p)))
    R["holm"][fam] = holm(R, keys)

R["meta"] = {"script_sha256": sha(__file__), "glmm_script_sha256": sha(R_SCRIPT), "inputs": inputs,
             "synthetic": A.synthetic, "bootstrap": {"resamples": A.nb, "seeds": {"human": SEED, "corpus": SEED + 1,
             "f10_human": SEED + 2, "f10_corpus": SEED + 3}, "method": "percentile (numpy linear), queries resampled"},
             "glmm_boot": A.glmm_boot,
             "software": {"python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__,
                          "scipy": __import__("scipy").__version__, "statsmodels": statsmodels.__version__,
                          "R": subprocess.run(["Rscript", "-e", "cat(R.version.string, as.character(packageVersion('lme4')))"],
                                              capture_output=True, text=True).stdout.strip()},
             "runtime_s": round(time.time() - T0, 1), "log": LOG}
out = ROOT / f"{A.out}.json"
with open(out, "w", encoding="utf-8", newline="\n") as f:
    json.dump(R, f, ensure_ascii=False, indent=1, default=lambda o: None)
log(f"wrote {out} ({time.time() - T0:.0f} s)")
