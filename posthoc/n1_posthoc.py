#!/usr/bin/env python3
"""n1_posthoc.py — N1: post-hoc mean-effect and randomization tests, stratified intervals and null calibration for
the six registered primary families (review items REV-10 and REV-12). Declared in a dated post-freeze record before
it computes anything from a study outcome; post-hoc, beside and outside the registered results of record. Nothing
here amends the registration, re-runs a registered analysis in place, or changes a frozen file, a stored output or a
table: every output is a new file.

REUSE. The registered definitions of n1_analysis.py (sha256 174bae3e…, record 19) are loaded by a whitelist loader:
its imports, constants, the function definitions and the Boot class used here — including P, has_price,
bdt_entries, nondeg, nonref_nondeg, cell_means and local_share_answer, which the registered file defines below the
start of its run. Its argument parsing and its module-level pipeline are never executed. The registered
state-building statements (queries, CAT, ROBUST, the classification tables and alias map, the coded-corpus indexes,
the final draws, usage and PERSONA) are then executed explicitly into the same namespace, after the input checks;
ROOT, R_SCRIPT (n1_glmm.R, unchanged, sha256 e02ec9dd…), TMP (one directory per worker, inside the analysis root;
Python's and R's temporary files are pointed there) and _job_seq are set explicitly. Real-data state is initialized
only when the registration holds the declaration record and that record quotes this file's sha256.

DEFINITIONS (as the run of record): six subject models; arms en, bn, bl; contrasts bn-en, bl-en, bn-bl; reversion
bn-bl on the bn and bl arms; the six F.7 families, 96 tests. Answer-level outcomes on the run-of-record analysis sets:
human families on human_layer() rows with P(r) in en/bn/bl (RQ1 brand set r["brands"], empty sets kept; RQ2
local_share_answer(), undefined without a classified mention; price mention has_price(r) with its default arguments;
BDT share mean(bdt_entries(r)), undefined without a price entry); corpus families on corpus_layer() (refusal
int(outcome == "refusal") over nondeg(r) in the three arms; reversion int(outcome == "language_reversion") over
nonref_nondeg(r) in bn and bl, frozen as coded). Estimand: the mean over eligible queries of the paired within-query
difference (RQ1: mean Delta from excess(A, B, jaccard), both arms holding at least two answers).

TESTS. (a) mean effect: approximate stratified bootstrap-t, t = estimate / SE (SE = sample SD of the eligible
per-query differences / sqrt(n), a pooled studentizing scale), resamples from the layer's stratified count matrix;
N = sum c, S = sum c*d, Q = sum c*d^2 computed on differences centred at the estimate; estimate* = S/N,
SE*^2 = (Q - S^2/N) / (N (N - 1)); t* = (estimate* - estimate) / SE*; a resample with N >= 2 (multiplicities), at
least two distinct drawn values and a finite SE* > 0 exceeds when |t*| >= |t|; every other resample counts as an
exceedance; P = (1 + exceedances) / (B + 1); no test (P = 1) when the estimate is unavailable, fewer than 10 queries
are eligible, or SE is zero or not finite. (b) randomization: within each query x model the pooled analysis-set
answers of the two arms (undefined markers included) are reassigned uniformly among all assignments that keep each
arm's count (enumerated as setdiv_perm enumerates them, one assignment drawn per query and draw); cell means,
eligible queries and the estimate are recomputed on every draw, a draw with no eligible query scoring 0;
hi = (1 + #{T* >= T - 1e-12}) / (N + 1), lo = (1 + #{T* <= T + 1e-12}) / (N + 1), P = min(1, 2 min(hi, lo)); an
observed contrast with no eligible query has P = 1. Holm within each family at .05 (the registered holm()), and over
all 96 as a descriptive column. Intervals: 95% percentiles (registered Boot.mean and pct) from the stratified count
matrix (within each category, multinomial counts with equal probabilities: 8 draws from the 8 human-layer queries,
25 from the 25 corpus queries).

Subcommands: study (one study: synthetic, or the real data after the declaration), bench, calibrate, summarize.
"""
import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")
import argparse, ast, builtins, csv, hashlib, itertools, json, math, re, shutil, subprocess, sys, tempfile, time
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
DRIVER_SHA = sha(HERE)

# ---------------------------------------------------------------------------------------------------- fixed values
REG_HASH = {"n1_analysis.py": "174bae3e3c8ebb8e219ff832c8105aa7373f17db41e837be738e7d2bb6f8fb7e",
            "n1_glmm.R": "e02ec9ddceab5d5e349af84f94eefdb804db19ea95e8bf5c6d2c6c46ca25e6f0",
            "n1_synth.py": "7b71747f617dff036f131536af88be15f37a6c53566017a3b6affa49eceb05b6",
            "ANALYSIS-RESULTS.json": "d12e64e5e8ebcb0f492d0608bed691315dd64ffc2e539b8d6fb7d34f3fd9903c",
            "ANALYSIS-ROBUSTNESS.md": "2ca41c3500e852f1d94c8cde090a20933815df88ee26381afdc8820fdb528780"}
REC19 = "Post-freeze record (26 Sep 2026, analysis implementation fixed"
REC23 = "Post-freeze record (27 Sep 2026, registered analyses run"
DECL_PREFIX = "Post-freeze record (29 Sep 2026, post-hoc mean-effect and randomization tests, stratified intervals and null calibration declared before they are computed"
FAM_ORDER = ["RQ1_excess_divergence", "RQ2_local_share", "RQ4_bdt_share", "RQ4_price_mention", "RQ5_reversion", "RQ5_refusal"]
HUMAN_FAMS = ["RQ1_excess_divergence", "RQ2_local_share", "RQ4_bdt_share", "RQ4_price_mention"]
CORPUS_FAMS = ["RQ5_reversion", "RQ5_refusal"]
B_BOOT, N_RAND, MIN_Q, TIE, ALPHA = 10000, 10000, 10, 1e-12, 0.05
REL_ZERO = 1e-12      # values equal up to floating-point rounding: spread <= 1e-12 x magnitude counts as no spread
SEEDS = {"strat": {"human": 20261101, "corpus": 20261102},
         "rand": {"RQ1_excess_divergence": 20261111, "RQ2_local_share": 20261112, "RQ4_bdt_share": 20261113,
                  "RQ4_price_mention": 20261114, "RQ5_reversion": 20261115, "RQ5_refusal": 20261116},
         "cal": {"human|i": 20261121, "human|ii": 20261122, "corpus|i": 20261123, "corpus|ii": 20261124},
         "cal_rate_boot": 20261131,
         "bench": {"human|i": 20261141, "human|ii": 20261142, "corpus|i": 20261143, "corpus|ii": 20261144},
         "reproduce_check_c": 20260930}
PURPOSE = {"generator": 1, "randomization": 2}

# ---------------------------------------------------------------------------------------------------- whitelist loader
WL_CONSTS = {"ARMS3", "C3", "C10", "FORM", "NB", "SEED", "P_RBO", "EXCLUDED", "MODELS", "CHINA", "GATES", "EXT_TABLES"}
WL_FUNCS = {"sha", "read_table", "fold", "resolve", "bclass", "rclass", "price_list", "human_layer", "corpus_layer",
            "pct", "jaccard", "excess", "wilcoxon", "glmm", "cells", "setdiv", "setdiv_perm", "per_answer_mentions",
            "share_outcome", "answer_binary", "holm", "P", "brand_items", "has_price", "bdt_entries", "nonref_nondeg",
            "nondeg", "cell_means", "local_share_answer"}
WL_CLASSES = {"Boot"}
STATE_FIRST_LINES = ["queries = ", "CAT = ", "ROBUST = ", "brand_rows = ", "BCLASS = ", "RCLASS = ", "EXCL_KEYS = ",
                     "AMAP = ", "for r in brand_rows:", "for k in EXCL_KEYS:", "coded_all = ", "by_cell = ",
                     "for r in coded_all:", "final, first_degenerate = ", "for c, rs in by_cell.items():",
                     "CODED_BY_KEY = ", "pending = ", "usage = ", "for m in MODELS:", "PERSONA = ", "for m in MODELS:"]
STATE_SET = {"ROOT", "R_SCRIPT", "TMP", "_job_seq", "log", "LOG"}
FORBIDDEN = {"ap", "A", "T0", "inputs", "H", "Cp", "M", "BH", "BC", "BH10", "BC10", "BM", "R", "PRIM_BOOT_H",
             "PRIM_BOOT_C", "SENS", "FAM", "f9", "brk", "R_SCRIPT", "TMP", "_job_seq"}


def _assigned_names(node):
    out = set()
    for t in node.targets:
        for n in ast.walk(t):
            if isinstance(n, ast.Name):
                out.add(n.id)
    return out


def load_registered(code_dir):
    """Exec the whitelisted definitions of the registered file; return (namespace, compiled state statements)."""
    p = Path(code_dir) / "n1_analysis.py"
    raw = p.read_bytes()
    if hashlib.sha256(raw).hexdigest() != REG_HASH["n1_analysis.py"]:
        raise SystemExit("n1_analysis.py is not the file record 19 registers")
    tree = ast.parse(raw.decode("utf-8"))
    defs, state, seen = [], [], set()
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            defs.append(n)
        elif isinstance(n, ast.Assign):
            names = _assigned_names(n)
            if names and names <= WL_CONSTS:
                defs.append(n); seen |= names
            elif 119 <= n.lineno <= 190:
                state.append(n)
        elif isinstance(n, ast.FunctionDef) and n.name in WL_FUNCS:
            defs.append(n); seen.add(n.name)
        elif isinstance(n, ast.ClassDef) and n.name in WL_CLASSES:
            defs.append(n); seen.add(n.name)
        elif isinstance(n, ast.For) and 119 <= n.lineno <= 190:
            state.append(n)
    if seen != WL_CONSTS | WL_FUNCS | WL_CLASSES:
        raise SystemExit(f"whitelist mismatch: missing {sorted((WL_CONSTS | WL_FUNCS | WL_CLASSES) - seen)}")
    first = [ast.unparse(n).split("\n")[0] for n in state]
    if len(first) != len(STATE_FIRST_LINES) or not all(f.startswith(e) for f, e in zip(first, STATE_FIRST_LINES)):
        raise SystemExit(f"state statements differ from the expected list: {first}")
    ns = {"__name__": "n1_registered_definitions", "__file__": str(p), "__builtins__": builtins}
    exec(compile(ast.Module(body=defs, type_ignores=[]), str(p), "exec"), ns)
    bad = FORBIDDEN & set(ns)
    if bad:
        raise SystemExit(f"forbidden names defined: {sorted(bad)}")
    # every global a reused function reads must be defined by the whitelist, the state statements or this driver
    state_names = set()
    for n in state:
        for m in ast.walk(n):
            if isinstance(m, ast.Name) and isinstance(m.ctx, ast.Store):
                state_names.add(m.id)
    for n in defs:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            local = set()
            for m in ast.walk(n):
                if isinstance(m, ast.Name) and isinstance(m.ctx, (ast.Store, ast.Del)):
                    local.add(m.id)
                elif isinstance(m, ast.arg):
                    local.add(m.arg)
                elif isinstance(m, ast.ExceptHandler) and m.name:
                    local.add(m.name)
                elif isinstance(m, (ast.Import, ast.ImportFrom)):
                    for al in m.names:
                        local.add((al.asname or al.name).split(".")[0])
                elif isinstance(m, (ast.FunctionDef, ast.Lambda)) and m is not n:
                    if isinstance(m, ast.FunctionDef):
                        local.add(m.name)
            loads = {m.id for m in ast.walk(n) if isinstance(m, ast.Name) and isinstance(m.ctx, ast.Load)}
            unresolved = loads - local - set(ns) - set(dir(builtins)) - state_names - STATE_SET
            if unresolved:
                raise SystemExit(f"{n.name} reads undefined globals {sorted(unresolved)}")
    return ns, compile(ast.Module(body=state, type_ignores=[]), str(p), "exec")


def init_state(ns, state_code, root, rscript, tmp):
    """Explicit initialization of the state the reused functions read."""
    if hashlib.sha256(Path(rscript).read_bytes()).hexdigest() != REG_HASH["n1_glmm.R"]:
        raise SystemExit("n1_glmm.R is not the file record 19 registers")
    ns["ROOT"] = Path(root)
    ns["LOG"] = []
    ns["log"] = lambda *a: ns["LOG"].append(" ".join(str(x) for x in a))
    exec(state_code, ns)
    ns["R_SCRIPT"] = Path(rscript)
    set_tmp(ns, tmp)


def set_tmp(ns, tmp):
    tmp = Path(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    ns["TMP"] = tmp
    ns["_job_seq"] = [0]
    os.environ["TMPDIR"] = str(tmp)
    tempfile.tempdir = str(tmp)


def clean_tmp(ns):
    for f in Path(ns["TMP"]).iterdir():
        if f.is_file():
            f.unlink()


# ---------------------------------------------------------------------------------------------------- input checks
def record_text(reg_text, title):
    i = reg_text.index(" " + title)
    j = reg_text.find(" Post-freeze record (", i + 10)
    k = reg_text.index(" Document precedence: **PROJECT-BRIEF.md §9b is canonical**")
    return reg_text[i:(j if 0 < j < k else k)]


def verify_real(root, code_dir, registration):
    """Inputs against ANALYSIS-RESULTS.json (meta.inputs), that file against record 23, the scripts against record 19,
    and the declaration guard. Returns the digests used."""
    root, code_dir = Path(root), Path(code_dir)
    reg = Path(registration).read_text(encoding="utf-8")
    if DECL_PREFIX not in reg:
        raise SystemExit("the declaration record is not in the registration: real-data state is not initialized")
    decl = record_text(reg, DECL_PREFIX)
    if DRIVER_SHA not in decl:
        raise SystemExit(f"the declaration record does not quote this driver's sha256 {DRIVER_SHA}")
    r19, r23 = record_text(reg, REC19), record_text(reg, REC23)
    h_an = re.search(r"n1_analysis\.py \(sha256 ([0-9a-f]{64})\)", r19).group(1)
    h_gl = re.search(r"n1_glmm\.R \(([0-9a-f]{64})\)", r19).group(1)
    h_res = re.search(r"ANALYSIS-RESULTS\.json \(sha256 ([0-9a-f]{64})\)", r23).group(1)
    got = {"n1_analysis.py": sha(code_dir / "n1_analysis.py"), "n1_glmm.R": sha(code_dir / "n1_glmm.R"),
           "ANALYSIS-RESULTS.json": sha(root / "ANALYSIS-RESULTS.json"), "ANALYSIS-ROBUSTNESS.md": sha(root / "ANALYSIS-ROBUSTNESS.md")}
    if not (got["n1_analysis.py"] == h_an == REG_HASH["n1_analysis.py"] and got["n1_glmm.R"] == h_gl == REG_HASH["n1_glmm.R"]):
        raise SystemExit("the analysis scripts are not the files record 19 registers")
    if not (got["ANALYSIS-RESULTS.json"] == h_res == REG_HASH["ANALYSIS-RESULTS.json"]):
        raise SystemExit("ANALYSIS-RESULTS.json is not the file record 23 registers")
    if got["ANALYSIS-ROBUSTNESS.md"] != REG_HASH["ANALYSIS-ROBUSTNESS.md"] or REG_HASH["ANALYSIS-ROBUSTNESS.md"] not in r23:
        raise SystemExit("ANALYSIS-ROBUSTNESS.md is not the file record 23 registers")
    R = json.loads((root / "ANALYSIS-RESULTS.json").read_text(encoding="utf-8"))
    if R["meta"]["script_sha256"] != h_an or R["meta"]["glmm_script_sha256"] != h_gl or R["meta"]["synthetic"]:
        raise SystemExit("ANALYSIS-RESULTS.json was not produced by the registered scripts on real data")
    inputs = {}
    for f, h in R["meta"]["inputs"].items():
        if sha(root / f) != h:
            raise SystemExit(f"input {f} differs from ANALYSIS-RESULTS.json meta.inputs")
        inputs[f] = h
    return {"scripts": got, "record19": {"n1_analysis.py": h_an, "n1_glmm.R": h_gl}, "record23": {"ANALYSIS-RESULTS.json": h_res},
            "inputs": inputs, "driver_sha256": DRIVER_SHA, "registration_sha256": sha(registration)}


# ---------------------------------------------------------------------------------------------------- families
def fam_def(ns, fam):
    A3, C3 = ns["ARMS3"], ns["C3"]
    return {"RQ1_excess_divergence": ("human", A3, C3, "set"), "RQ2_local_share": ("human", A3, C3, "scalar"),
            "RQ4_bdt_share": ("human", A3, C3, "scalar"), "RQ4_price_mention": ("human", A3, C3, "scalar"),
            "RQ5_reversion": ("corpus", ["bl", "bn"], [("bn", "bl")], "scalar"),
            "RQ5_refusal": ("corpus", A3, C3, "scalar")}[fam]


def keys_of(ns, fam):
    _, _, cons, _ = fam_def(ns, fam)
    return [f"{m}|{a}-{b}" for m in ns["MODELS"] for a, b in cons]


def analysis_rows(ns, fam, rows):
    A3 = ns["ARMS3"]
    if fam in HUMAN_FAMS:
        return [r for r in rows if r["arm"] in A3 and ns["P"](r)]
    if fam == "RQ5_reversion":
        return [r for r in rows if r["arm"] in ("bn", "bl") and ns["nonref_nondeg"](r)]
    return [r for r in rows if r["arm"] in A3 and ns["nondeg"](r)]


def answer_value(ns, fam, r):
    if fam == "RQ2_local_share":
        v = ns["local_share_answer"](r)
        return float("nan") if v is None else v
    if fam == "RQ4_bdt_share":
        ys = ns["bdt_entries"](r)
        return (sum(ys) / len(ys)) if ys else float("nan")
    if fam == "RQ4_price_mention":
        return float(ns["has_price"](r))
    if fam == "RQ5_reversion":
        return float(r["outcome"] == "language_reversion")
    return float(r["outcome"] == "refusal")


def fam_cells(ns, fam, arows):
    if fam == "RQ1_excess_divergence":
        return ns["cells"](arows, "brands", ns["P"])
    d = defaultdict(list)
    for r in arows:
        d[(r["model"], r["query"], r["arm"])].append(answer_value(ns, fam, r))
    return {k: np.array(v, dtype=float) for k, v in d.items()}


def per_query(ns, fam, cellv, frame, m, a, b):
    """{query: paired difference} over the eligible queries, in sorted query order, computed as the run of record."""
    out = {}
    if fam == "RQ1_excess_divergence":
        for q in frame:
            v = ns["excess"](cellv.get((m, q, a), []), cellv.get((m, q, b), []), ns["jaccard"])
            if v is not None:
                out[q] = v
        return out
    for q in frame:
        va, vb = cellv.get((m, q, a)), cellv.get((m, q, b))
        if va is None or vb is None:
            continue
        da, db = va[~np.isnan(va)], vb[~np.isnan(vb)]
        if len(da) and len(db):
            out[q] = float(np.mean(da)) - float(np.mean(db))
    return out


def estimate_of(per_q):
    return float(np.mean(list(per_q.values()))) if per_q else None


# ---------------------------------------------------------------------------------------------------- count matrices
def strat_boot(ns, frame, cat, seed, nb=B_BOOT):
    """Boot-compatible object with category-stratified counts (not Boot's unstratified constructor)."""
    Boot = ns["Boot"]
    b = Boot.__new__(Boot)
    b.q = sorted(frame)
    b.ix = {q: i for i, q in enumerate(b.q)}
    rng = np.random.default_rng(seed)
    C = np.zeros((nb, len(b.q)), dtype=np.int64)
    cats = sorted({cat[q] for q in b.q})
    per_cat = {}
    for c in cats:
        cols = [b.ix[q] for q in b.q if cat[q] == c]
        per_cat[c] = cols
        C[:, cols] = rng.multinomial(len(cols), np.full(len(cols), 1.0 / len(cols)), size=nb)
    assert (C >= 0).all() and C.dtype.kind == "i"
    for c, cols in per_cat.items():
        assert (C[:, cols].sum(axis=1) == len(cols)).all(), c
    assert (C.sum(axis=1) == len(b.q)).all()
    b.C = C.astype(np.float64)
    b.seed, b.nb = seed, nb
    b.per_cat = {c: len(v) for c, v in per_cat.items()}
    return b


def zero_boot(ns, frame, seed):
    return ns["Boot"](set(frame), 0, seed)


# ---------------------------------------------------------------------------------------------------- test (a)
def mean_effect(per_q, sb, B=None):
    n = len(per_q)
    if n == 0:
        return {"p": 1.0, "test": False, "reason": "no eligible query", "n_query": 0}
    d = np.array(list(per_q.values()), dtype=float)
    est = float(np.mean(d))
    if n < MIN_Q:
        return {"p": 1.0, "test": False, "reason": f"fewer than {MIN_Q} eligible queries", "n_query": n, "estimate": est}
    sd = float(np.std(d, ddof=1))
    scale = float(np.max(np.abs(d)))
    if scale == 0.0 or sd <= REL_ZERO * scale:
        sd = 0.0                               # differences equal up to floating-point rounding: SE is zero
    se = sd / math.sqrt(n)
    if not math.isfinite(se) or se == 0:
        return {"p": 1.0, "test": False, "reason": "SE zero or not finite", "n_query": n, "estimate": est, "se": se}
    t = est / se
    nq = len(sb.q)
    e = np.zeros(nq); d0 = np.zeros(nq); draw_val = np.zeros(nq)
    for q, x in per_q.items():
        j = sb.ix[q]
        e[j] = 1.0; d0[j] = x - est; draw_val[j] = x
    C = sb.C
    N = C @ e
    S = C @ d0
    Q = C @ (d0 * d0)
    drawn = (C > 0) & (e > 0)
    vmin = np.where(drawn, draw_val, np.inf).min(axis=1)
    vmax = np.where(drawn, draw_val, -np.inf).max(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        var = (Q - S * S / N) / (N * (N - 1))
        se_s = np.sqrt(np.where(var > 0, var, np.nan))
        t_s = (S / N) / se_s
    spread = np.where(np.isfinite(vmax) & np.isfinite(vmin), vmax - vmin, 0.0)
    mag = np.where(np.isfinite(vmax) & np.isfinite(vmin), np.maximum(np.abs(vmax), np.abs(vmin)), 0.0)
    distinct = (spread > REL_ZERO * mag) & (mag > 0)
    valid = (N >= 2) & distinct & np.isfinite(var) & (var > 0) & np.isfinite(t_s)
    exceed = (~valid) | (np.abs(t_s) >= abs(t))
    n_invalid = int((~valid).sum())
    Bn = C.shape[0]
    p = (1 + int(exceed.sum())) / (Bn + 1)
    why = Counter()
    if n_invalid:
        why["fewer than two eligible draws"] = int((N < 2).sum())
        why["one distinct drawn value (SE* = 0)"] = int(((N >= 2) & ~distinct).sum())
        why["SE* not finite or not positive otherwise"] = int((((N >= 2) & distinct) & ~valid).sum())
    return {"p": float(p), "test": True, "n_query": n, "estimate": est, "se": se, "t": t, "B": Bn,
            "exceedances": int(exceed.sum()), "invalid_resamples": n_invalid, "invalid_reasons": dict(why)}


# ---------------------------------------------------------------------------------------------------- test (b)
_COMBO = {}


def combos(n, k):
    key = (n, k)
    if key not in _COMBO:
        idx = list(itertools.combinations(range(n), k))
        M = np.zeros((len(idx), n), dtype=np.float64)
        for i, c in enumerate(idx):
            M[i, list(c)] = 1.0
        _COMBO[key] = (idx, M)
    return _COMBO[key]


def alts_scalar(va, vb):
    pool = np.concatenate([va, vb])
    _, M = combos(len(pool), len(va))
    dfn = (~np.isnan(pool)).astype(np.float64)
    vz = np.where(dfn > 0, pool, 0.0)
    sA, cA = M @ vz, M @ dfn
    sB, cB = vz.sum() - sA, dfn.sum() - cA
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where((cA > 0) & (cB > 0), sA / cA - sB / cB, np.nan)


def alts_set(ns, A_, B_):
    """exactly setdiv_perm's enumeration"""
    pool = A_ + B_
    out = []
    for ia in itertools.combinations(range(len(pool)), len(A_)):
        sa = set(ia)
        out.append(ns["excess"]([pool[i] for i in ia], [pool[i] for i in range(len(pool)) if i not in sa], ns["jaccard"]))
    return np.array(out)


def randomization_family(ns, fam, cellv, frame, seed, nperm, est_by_key):
    """One random stream per family, models then contrasts then queries in the registered order (as setdiv_perm)."""
    _, _, cons, kind = fam_def(ns, fam)
    rng = np.random.default_rng(seed)
    out = {}
    for m in ns["MODELS"]:
        for a, b in cons:
            key = f"{m}|{a}-{b}"
            sums = np.zeros(nperm); cnts = np.zeros(nperm); nq = 0
            for q in frame:
                if kind == "set":
                    A_, B_ = cellv.get((m, q, a), []), cellv.get((m, q, b), [])
                    if len(A_) < 2 or len(B_) < 2:
                        continue
                    alts = alts_set(ns, A_, B_)
                else:
                    va, vb = cellv.get((m, q, a)), cellv.get((m, q, b))
                    if va is None or vb is None or not len(va) or not len(vb):
                        continue
                    alts = alts_scalar(va, vb)
                x = alts[rng.integers(0, len(alts), size=nperm)]
                ok = ~np.isnan(x)
                sums += np.where(ok, x, 0.0)
                cnts += ok
                nq += 1
            Ts = np.zeros(nperm)
            np.divide(sums, cnts, out=Ts, where=cnts > 0)
            T = est_by_key.get(key)
            if T is None:
                out[key] = {"p": 1.0, "test": False, "reason": "no eligible query", "n_pool_queries": nq}
                continue
            hi = (np.sum(Ts >= T - TIE) + 1) / (nperm + 1)
            lo = (np.sum(Ts <= T + TIE) + 1) / (nperm + 1)
            out[key] = {"p": float(min(1.0, 2 * min(hi, lo))), "test": True, "n_pool_queries": nq, "draws": nperm,
                        "null_mean": float(Ts.mean()), "draws_without_eligible_query": int((cnts == 0).sum())}
    return out


# ---------------------------------------------------------------------------------------------------- registered tests
def registered_family(ns, fam, rows, b0):
    A3, C3, P = ns["ARMS3"], ns["C3"], ns["P"]
    if fam == "RQ1_excess_divergence":
        return ns["setdiv"](rows, "brands", ns["jaccard"], C3, P, b0, "post-hoc")
    if fam == "RQ2_local_share":
        return ns["share_outcome"](rows, {"items": ns["brand_items"]()}, A3, C3, P, b0, "post-hoc", None, "query")
    if fam == "RQ4_price_mention":
        return ns["answer_binary"](rows, ns["has_price"], A3, C3, P, b0, "post-hoc", None, "query")
    if fam == "RQ4_bdt_share":
        return ns["share_outcome"](rows, {"binary": ns["bdt_entries"]}, A3, C3, P, b0, "post-hoc", None, "query")
    if fam == "RQ5_reversion":
        return ns["answer_binary"](rows, lambda r: int(r["outcome"] == "language_reversion"), ["bl", "bn"], [("bn", "bl")],
                                   ns["nonref_nondeg"], b0, "post-hoc", None, "query")
    return ns["answer_binary"](rows, lambda r: int(r["outcome"] == "refusal"), A3, C3, ns["nondeg"], b0, "post-hoc", None, "query")


def registered_p(ns, fam, res):
    """final P per contrast exactly as the registered Holm block reads it (fallback P kept; no information -> 1)"""
    out = {}
    for m in ns["MODELS"]:
        for a, b in fam_def(ns, fam)[2]:
            k = f"{m}|{a}-{b}"
            if fam == "RQ1_excess_divergence":
                x = res["results"][k]
                p = x.get("test", {}).get("p", 1.0) if x.get("n_query") else 1.0
                meth = "wilcoxon" if x.get("n_query") else "no paired query"
            else:
                c = res["results"][m]["contrasts"][f"{a}-{b}"]
                p, meth = c["test"]["p"], c["test"]["method"]
            out[k] = {"p": 1.0 if p is None else float(p), "method": meth}
    return out


def glmm_diag(ns, fam, res):
    if fam == "RQ1_excess_divergence":
        return {}
    return {m: res["results"][m]["glmm"] for m in ns["MODELS"]}


def run_registered(ns, fam, rows, b0, errors):
    for attempt in (1, 2):
        try:
            res = registered_family(ns, fam, rows, b0)
            clean_tmp(ns)
            return res, attempt
        except BaseException as e:           # SystemExit from glmm() or malformed output: a job error
            if isinstance(e, KeyboardInterrupt):
                raise
            clean_tmp(ns)
            errors.append({"family": fam, "attempt": attempt, "error": f"{type(e).__name__}: {str(e)[-500:]}"})
    raise RuntimeError(f"registered {fam}: job error not resolved by one retry: {errors[-1]}")


def holm_map(ns, pmap):
    keys = [(k, 1.0 if v is None else float(v)) for k, v in pmap.items()]
    return ns["holm"](None, keys)


# ---------------------------------------------------------------------------------------------------- null generators
def _groups(rows, arms):
    g = defaultdict(list)
    for i, r in enumerate(rows):
        if r["arm"] in arms:
            g[(r["model"], r["query"])].append(i)
    return {k: g[k] for k in sorted(g)}


def perm_within(rows, arms, rng):
    """scenario (i): reassign the answers of each query x model among `arms`, keeping each arm's count"""
    out = list(rows)
    for k, idx in _groups(rows, arms).items():
        pool = [i for a in arms for i in idx if rows[i]["arm"] == a]
        labels = [rows[i]["arm"] for i in pool]
        perm = rng.permutation(len(pool))
        for j, i in enumerate(pool):
            out[pool[perm[j]]] = dict(rows[pool[perm[j]]], arm=labels[j])
    return out


def block_perm(rows, arms, rng, swap_only=False):
    """scenario (ii): relabel whole source-arm blocks of each query x model (six orderings, or swap/keep for two arms)"""
    out = list(rows)
    for k, idx in _groups(rows, arms).items():
        if swap_only:
            mp = {arms[0]: arms[1], arms[1]: arms[0]} if rng.random() < 0.5 else {a: a for a in arms}
        else:
            perm = rng.permutation(len(arms))
            mp = {arms[i]: arms[perm[i]] for i in range(len(arms))}
        for i in idx:
            out[i] = dict(rows[i], arm=mp[rows[i]["arm"]])
    return out


def null_dataset(ns, layer, scenario, base, rng):
    """base: {"human": analysis-set rows} or {"refusal": rows, "reversion": rows}"""
    A3 = ns["ARMS3"]
    if layer == "human":
        rows = base["human"]
        return {"human": perm_within(rows, A3, rng) if scenario == "i" else block_perm(rows, A3, rng)}
    if scenario == "i":
        return {"refusal": perm_within(base["refusal"], A3, rng), "reversion": perm_within(base["reversion"], ["bn", "bl"], rng)}
    return {"refusal": block_perm(base["refusal"], A3, rng), "reversion": block_perm(base["reversion"], ["bn", "bl"], rng, swap_only=True)}


def fam_rows(fam, rowsets):
    if fam in HUMAN_FAMS:
        return rowsets["human"]
    return rowsets["reversion"] if fam == "RQ5_reversion" else rowsets["refusal"]


def stream_seed(base, k, purpose, sub=0):
    return int(np.random.SeedSequence([int(base), int(k), int(purpose), int(sub)]).generate_state(1, np.uint64)[0])


# ---------------------------------------------------------------------------------------------------- one data set
def evaluate(ns, fams, rowsets, frames, sbs, b0s, rand_seeds, nperm=N_RAND, registered=True, want_pq=False):
    """New tests (a), (b) and the registered tests on one data set. rand_seeds: {fam: seed} or None."""
    res, errors, timing = {}, [], Counter()
    for fam in fams:
        layer = fam_def(ns, fam)[0]
        rows = fam_rows(fam, rowsets)
        t0 = time.time()
        cellv = fam_cells(ns, fam, rows)
        pqs, est = {}, {}
        for m in ns["MODELS"]:
            for a, b in fam_def(ns, fam)[2]:
                k = f"{m}|{a}-{b}"
                pqs[k] = per_query(ns, fam, cellv, frames[layer], m, a, b)
                est[k] = estimate_of(pqs[k])
        timing["estimates"] += time.time() - t0
        t0 = time.time()
        me = {k: mean_effect(pqs[k], sbs[layer]) for k in pqs}
        timing["mean_effect"] += time.time() - t0
        rz = None
        if rand_seeds is not None:
            t0 = time.time()
            rz = randomization_family(ns, fam, cellv, frames[layer], rand_seeds[fam], nperm, est)
            timing["randomization"] += time.time() - t0
        reg = diag = None
        attempts = 0
        if registered:
            t0 = time.time()
            rr, attempts = run_registered(ns, fam, rows, b0s[layer], errors)
            reg = registered_p(ns, fam, rr)
            diag = glmm_diag(ns, fam, rr)
            timing["registered"] += time.time() - t0
        entry = {}
        for k in pqs:
            e = {"estimate": est[k], "n_query": len(pqs[k]), "me_p": me[k]["p"], "me_test": me[k]["test"]}
            if not me[k]["test"]:
                e["me_reason"] = me[k]["reason"]
            else:
                e["me_invalid"] = me[k]["invalid_resamples"]
            if rz is not None:
                e["rz_p"] = rz[k]["p"]; e["rz_test"] = rz[k]["test"]
            if reg is not None:
                e["reg_p"] = reg[k]["p"]; e["reg_method"] = reg[k]["method"]
            if want_pq:
                e["per_query"] = pqs[k]
            entry[k] = e
        res[fam] = {"contrasts": entry}
        if diag is not None:
            res[fam]["jobs"] = {m: {"status": d.get("status"), "singular": d.get("singular"), "optimizer": d.get("optimizer"),
                                    "tried": d.get("tried")} for m, d in diag.items()}
            res[fam]["attempts"] = attempts
    return {"families": res, "job_errors": errors, "timing": dict(timing)}


# ---------------------------------------------------------------------------------------------------- study setup
class Setup:
    def __init__(self, root, code_dir, tmp, synthetic, registration=None):
        t0 = time.time()
        self.root, self.code_dir, self.synthetic = Path(root), Path(code_dir), synthetic
        if synthetic:
            if not (self.root / "SYNTHETIC").exists():
                raise SystemExit("synthetic mode needs a root made by the validation harness (SYNTHETIC marker): refused")
            self.checks = {"synthetic": True, "n1_synth.py": sha(self.code_dir / "n1_synth.py") if (self.code_dir / "n1_synth.py").exists() else None}
        else:
            self.checks = verify_real(self.root, self.code_dir, registration)
        self.ns, state = load_registered(self.code_dir)
        init_state(self.ns, state, self.root, self.code_dir / "n1_glmm.R", tmp)
        ns = self.ns
        self.H = ns["human_layer"]()
        self.Cp = ns["corpus_layer"]()
        self.frames = {"human": sorted({r["query"] for r in self.H}), "corpus": sorted({r["query"] for r in self.Cp})}
        self.CAT = ns["CAT"]
        # the design frame: 80 human-layer queries (8 per category), 250 corpus queries (25 per category)
        for L, n_total, n_cat in (("human", 80, 8), ("corpus", 250, 25)):
            per = Counter(self.CAT[q] for q in self.frames[L])
            if len(self.frames[L]) != n_total or len(per) != 10 or set(per.values()) != {n_cat}:
                raise SystemExit(f"{L} query frame is not {n_total} queries with {n_cat} in each of 10 categories: {dict(per)}")
        self.base = {"human": analysis_rows(ns, "RQ2_local_share", self.H),
                     "refusal": analysis_rows(ns, "RQ5_refusal", self.Cp),
                     "reversion": analysis_rows(ns, "RQ5_reversion", self.Cp)}
        self.sbs = {L: strat_boot(ns, self.frames[L], self.CAT, SEEDS["strat"][L]) for L in ("human", "corpus")}
        self.b0s = {L: zero_boot(ns, self.frames[L], SEEDS["strat"][L]) for L in ("human", "corpus")}
        self.setup_s = time.time() - t0


def fams_for(layer, scenario):
    fams = HUMAN_FAMS if layer == "human" else CORPUS_FAMS
    return [f for f in FAM_ORDER if f in fams and not (scenario == "ii" and f == "RQ1_excess_divergence")]


# ---------------------------------------------------------------------------------------------------- calibration
G = {}


def _worker_init(counter, tmp_root):
    with counter.get_lock():
        wid = counter.value
        counter.value += 1
    G["wid"] = wid
    set_tmp(G["setup"].ns, Path(tmp_root) / f"w{wid}")


def _cal_task(layer, scenario, k, do_rand, stream_base):
    S = G["setup"]
    ns = S.ns
    t0 = time.time()
    g_seed = stream_seed(stream_base, k, PURPOSE["generator"])
    rng = np.random.default_rng(g_seed)
    rowsets = null_dataset(ns, layer, scenario, S.base, rng)
    tg = time.time() - t0
    fams = fams_for(layer, scenario)
    rseeds = {f: stream_seed(stream_base, k, PURPOSE["randomization"], FAM_ORDER.index(f)) for f in fams} if do_rand else None
    out = evaluate(ns, fams, rowsets, S.frames, S.sbs, S.b0s, rseeds)
    out["timing"]["generate"] = tg
    out["timing"]["total"] = time.time() - t0
    out.update({"layer": layer, "scenario": scenario, "k": k, "worker": G.get("wid"),
                "seeds": {"generator": g_seed, "randomization": rseeds}})
    return out


def calibrate(S, layer, scenario, n, n_rand, workers, out_path, tmp_root, stream_base, progress=None):
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor, as_completed
    out_path = Path(out_path)
    done = set()
    if out_path.exists():
        for l in out_path.read_text(encoding="utf-8").splitlines():
            if l.strip():
                done.add(json.loads(l)["k"])
    todo = [k for k in range(n) if k not in done]
    G["setup"] = S
    ctx = mp.get_context("fork")
    counter = ctx.Value("i", 0)
    t0 = time.time()
    with open(out_path, "a", encoding="utf-8") as fh, ProcessPoolExecutor(max_workers=workers, mp_context=ctx,
                                                                          initializer=_worker_init, initargs=(counter, tmp_root)) as ex:
        futs = {ex.submit(_cal_task, layer, scenario, k, k < n_rand, stream_base): k for k in todo}
        try:
            for i, f in enumerate(as_completed(futs), 1):
                r = f.result()                      # a job error not resolved by one retry stops the run here
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")
                fh.flush(); os.fsync(fh.fileno())
                if progress and (i % progress == 0 or i == len(todo)):
                    print(f"[{time.strftime('%H:%M:%S')}] {layer}|{scenario}: {len(done) + i}/{n} "
                          f"({time.time() - t0:.0f} s this session)", flush=True)
        except BaseException:
            for f in futs:
                f.cancel()
            raise
    return time.time() - t0


# ---------------------------------------------------------------------------------------------------- summaries
def wilson(x, n, z=1.959963984540054):
    if n == 0:
        return [None, None]
    p = x / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [c - h, c + h]


def summarize_cal(ns, lines, layer, scenario, seed=SEEDS["cal_rate_boot"], nb=10000):
    """rejection rates, family-wise rates and intersections for one layer x scenario. statsmodels' multipletests (inside
    the registered holm) calls gc.collect() on every call; the objects already loaded are frozen so that it does not
    rescan them (speed only; no value changes)."""
    import gc
    gc.collect(); gc.freeze()
    try:
        return _summarize_cal(ns, lines, layer, scenario, seed, nb)
    finally:
        gc.unfreeze()


def _summarize_cal(ns, lines, layer, scenario, seed, nb):
    lines = sorted(lines, key=lambda r: r["k"])
    fams = fams_for(layer, scenario)
    procs = ["reg", "me", "rz"]
    out = {"n_datasets": len(lines), "families": {}}
    rng = np.random.default_rng(seed)
    for fam in fams:
        keys = keys_of(ns, fam)
        F = {"per_contrast": {}, "family_average": {}, "fwer": {}, "intersections": {}, "diagnostics": {}}
        rej = {}
        for pr in procs:
            rows = [ln for ln in lines if f"{pr}_p" in next(iter(ln["families"][fam]["contrasts"].values()))]
            if not rows:
                continue
            P = np.array([[ln["families"][fam]["contrasts"][k][f"{pr}_p"] for k in keys] for ln in rows], dtype=float)
            U = P <= ALPHA
            H = np.array([[hm[k]["reject"] for k in keys] for hm in (holm_map(ns, dict(zip(keys, prow))) for prow in P)])
            rej[pr] = (rows, U, H)
            n = len(rows)
            rate = U.mean(axis=0)
            W = rng.multinomial(n, np.full(n, 1.0 / n), size=nb).astype(np.float64)     # resamples of whole data sets
            bs = (W @ U.astype(np.float64)) / n                                         # nb x contrasts
            F["per_contrast"][pr] = {k: {"rate": float(rate[j]), "ci": [float(np.percentile(bs[:, j], 2.5)), float(np.percentile(bs[:, j], 97.5))]}
                                     for j, k in enumerate(keys)}
            fa = bs.mean(axis=1)
            F["family_average"][pr] = {"rate": float(rate.mean()), "ci": [float(np.percentile(fa, 2.5)), float(np.percentile(fa, 97.5))], "n": n}
            fw = int(H.any(axis=1).sum())
            F["fwer"][pr] = {"rate": fw / n, "x": fw, "n": n, "wilson": wilson(fw, n)}
        if "reg" in rej and "me" in rej:
            _, _, Hr = rej["reg"]; _, _, Hm = rej["me"]
            both = (Hr & Hm).any(axis=1)
            F["intersections"]["reg_and_me"] = {"x": int(both.sum()), "n": len(both), "rate": float(both.mean()), "wilson": wilson(int(both.sum()), len(both))}
        if "rz" in rej:
            rows_rz, _, Hz = rej["rz"]
            ks = [ln["k"] for ln in rows_rz]
            pos = {ln["k"]: i for i, ln in enumerate(rej["reg"][0])}
            sel = [pos[k] for k in ks]
            tri = (rej["reg"][2][sel] & rej["me"][2][sel] & Hz).any(axis=1)
            F["intersections"]["reg_and_me_and_rz"] = {"x": int(tri.sum()), "n": len(tri), "rate": float(tri.mean()) if len(tri) else None,
                                                       "wilson": wilson(int(tri.sum()), len(tri))}
        # diagnostics: job-level fit outcomes and contrast-level fallbacks
        st = Counter(); sing = 0; fb = Counter(); meth = Counter(); me_no = Counter(); inval = 0; attempts = Counter()
        for ln in lines:
            fr = ln["families"][fam]
            for m, j in fr.get("jobs", {}).items():
                st[j["status"]] += 1
                sing += bool(j.get("singular"))
            attempts[fr.get("attempts", 0)] += 1
            for k, c in fr["contrasts"].items():
                meth[c.get("reg_method")] += 1
                if not c["me_test"]:
                    me_no[c["me_reason"]] += 1
                else:
                    inval += c.get("me_invalid", 0)
        F["diagnostics"] = {"job_status": dict(st), "singular_fits": sing, "contrast_methods": dict(meth),
                            "mean_effect_no_test": dict(me_no), "mean_effect_invalid_resamples_total": inval,
                            "registered_attempts": dict(attempts)}
        out["families"][fam] = F
    out["job_errors"] = [e for ln in lines for e in ln.get("job_errors", [])]
    out["timing_mean_s"] = {k: float(np.mean([ln["timing"].get(k, 0.0) for ln in lines])) for k in
                            ("generate", "estimates", "mean_effect", "randomization", "registered", "total")} if lines else {}
    return out


# ---------------------------------------------------------------------------------------------------- run of record
ROB_TITLES = {"RQ1_excess_divergence": "## RQ1 — excess brand-set divergence (human)", "RQ2_local_share": "## RQ2 — local-brand share (human)",
              "RQ4_price_mention": "## RQ4 — price-mention rate (human)", "RQ4_bdt_share": "## RQ4 — BDT share of stated prices (human)",
              "RQ5_reversion": "## RQ5 — language reversion (corpus)", "RQ5_refusal": "## RQ5 — refusal (corpus)"}
HET = {"RQ2_local_share": "RQ2_local_share_het", "RQ4_price_mention": "RQ4_price_mention_het", "RQ4_bdt_share": "RQ4_bdt_share_het",
       "RQ5_reversion": "RQ5_reversion_het", "RQ5_refusal": "RQ5_refusal_het"}
N_UNIT = {"RQ2_local_share": "classified brand mentions", "RQ4_bdt_share": "price entries", "RQ4_price_mention": "answers",
          "RQ5_reversion": "answers", "RQ5_refusal": "answers"}
PLANNED_FORMULA = "y ~ arm + (1 | query)"


def _mark(cell):
    if "NOT supp." in cell:
        return "not supported"
    if "supp." in cell:
        return "supported"
    if "n/a" in cell:
        return "not applicable"
    return "no marker"


def parse_robustness(text):
    """support markers of ANALYSIS-ROBUSTNESS.md per family and contrast: RQ1 -> check (c); others -> checks (a), (b)"""
    out = {}
    for fam, title in ROB_TITLES.items():
        i = text.index(title)
        j = text.find("\n## ", i + len(title))
        block = text[i:(j if j > 0 else len(text))]
        rows = {}
        for line in block.splitlines():
            if not line.startswith("| ") or line.startswith("| model") or line.startswith("|---"):
                continue
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            key = f"{c[0]}|{c[1]}"
            if fam == "RQ1_excess_divergence":
                rows[key] = {"holm_cell": c[4], "c": _mark(c[5]), "c_cell": c[5]}
            else:
                rows[key] = {"test_cell": c[2], "holm_cell": c[5], "a": _mark(c[6]), "b": _mark(c[7]), "a_cell": c[6], "b_cell": c[7]}
        out[fam] = rows
    return out


def stored_contrast(R, fam, m, a, b):
    if fam == "RQ1_excess_divergence":
        x = R["primary"][fam]["results"][f"{m}|{a}-{b}"]
        return {"estimate": x.get("mean_delta"), "ci": x.get("ci"), "n_query": x.get("n_query", 0),
                "p": x.get("test", {}).get("p", 1.0) if x.get("n_query") else 1.0, "method": "wilcoxon" if x.get("n_query") else "no paired query",
                "test": x.get("test")}
    c = R["primary"][fam]["results"][m]["contrasts"][f"{a}-{b}"]
    return {"estimate": c.get("diff"), "ci": c.get("ci"), "n_query": c.get("n_query", 0), "p": c["test"]["p"], "method": c["test"]["method"],
            "log_odds": c.get("log_odds"), "fallback": c.get("fallback")}


def _close(x, y, tol=1e-12):
    if x is None or y is None:
        return x is None and y is None
    return abs(float(x) - float(y)) <= tol * max(1.0, abs(float(y)))


def reproduce(S, R, rerun_registered=True):
    """the driver's estimates, run-of-record intervals, registered P values and check (c) against the stored run"""
    ns = S.ns
    nb_rec = R["meta"]["bootstrap"]["resamples"]
    seeds = R["meta"]["bootstrap"]["seeds"]
    boots = {"human": ns["Boot"](set(S.frames["human"]), nb_rec, seeds["human"]),
             "corpus": ns["Boot"](set(S.frames["corpus"]), nb_rec, seeds["corpus"])}
    rep = {"estimates": {"checked": 0, "mismatch": []}, "run_of_record_ci": {"checked": 0, "mismatch": []},
           "registered_p": {"checked": 0, "tolerance": {"glmm_wald": "|dP| <= 0.02 x max(P) or |dP| <= 1e-9 (R/lme4 between sessions; "
                                                                     "the tolerance of the C.1 self-test, record 37)",
                                                        "other": "|dP| <= 1e-12"},
                            "max_abs_diff": {"glmm_wald": 0.0, "other": 0.0}, "max_rel_diff": {"glmm_wald": 0.0, "other": 0.0},
                            "method_mismatch": [], "p_mismatch": [], "holm_decision_mismatch": []},
           "check_c": {"checked": 0, "mismatch": []}, "job_errors": []}
    t0 = time.time()
    for fam in FAM_ORDER:
        layer = fam_def(ns, fam)[0]
        rows = fam_rows(fam, S.base)
        cellv = fam_cells(ns, fam, rows)
        est = {}
        for m in ns["MODELS"]:
            for a, b in fam_def(ns, fam)[2]:
                k = f"{m}|{a}-{b}"
                pq = per_query(ns, fam, cellv, S.frames[layer], m, a, b)
                est[k] = estimate_of(pq)
                st = stored_contrast(R, fam, m, a, b)
                rep["estimates"]["checked"] += 1
                if len(pq) != st["n_query"] or not _close(est[k], st["estimate"]):
                    rep["estimates"]["mismatch"].append({"key": f"{fam}|{k}", "driver": [len(pq), est[k]], "stored": [st["n_query"], st["estimate"]]})
                reps, _ = boots[layer].mean(pq) if pq else (np.array([]), 0)
                ci = ns["pct"](reps)
                rep["run_of_record_ci"]["checked"] += 1
                if not (_close(ci[0], st["ci"][0]) and _close(ci[1], st["ci"][1])):
                    rep["run_of_record_ci"]["mismatch"].append({"key": f"{fam}|{k}", "driver": ci, "stored": st["ci"]})
        if rerun_registered:
            rr, _ = run_registered(ns, fam, rows, S.b0s[layer], rep["job_errors"])
            regp = registered_p(ns, fam, rr)
            for k, v in regp.items():
                m, con = k.split("|")
                st = stored_contrast(R, fam, m, *con.split("-"))
                rep["registered_p"]["checked"] += 1
                if v["method"] != st["method"]:
                    rep["registered_p"]["method_mismatch"].append({"key": f"{fam}|{k}", "driver": v["method"], "stored": st["method"]})
                sp = 1.0 if st["p"] is None else float(st["p"])
                d = abs(v["p"] - sp)
                rel = d / max(abs(v["p"]), abs(sp), 1e-300)
                cls = "glmm_wald" if st["method"] == "glmm_wald" else "other"
                rep["registered_p"]["max_abs_diff"][cls] = max(rep["registered_p"]["max_abs_diff"][cls], d)
                rep["registered_p"]["max_rel_diff"][cls] = max(rep["registered_p"]["max_rel_diff"][cls], rel if d > 0 else 0.0)
                bad = (d > 0.02 * max(abs(v["p"]), abs(sp)) and d > 1e-9) if cls == "glmm_wald" else d > 1e-12
                if bad:
                    rep["registered_p"]["p_mismatch"].append({"key": f"{fam}|{k}", "driver": v["p"], "stored": st["p"], "method": st["method"]})
            hdec = holm_map(ns, {k: v["p"] for k, v in regp.items()})
            for k in regp:
                if hdec[k]["reject"] != R["holm"][fam][k]["reject"]:
                    rep["registered_p"]["holm_decision_mismatch"].append({"key": f"{fam}|{k}", "driver": hdec[k]["reject"],
                                                                          "stored": R["holm"][fam][k]["reject"]})
        if fam == "RQ1_excess_divergence" and "RQ1_permutation" in R["sensitivity"]:
            rz = randomization_family(ns, fam, cellv, S.frames["human"], SEEDS["reproduce_check_c"], nb_rec, est)
            for k, v in rz.items():
                st = R["sensitivity"]["RQ1_permutation"]["results"][k]
                rep["check_c"]["checked"] += 1
                if st.get("n_query"):
                    if not (v["p"] == st["p"] and v["null_mean"] == st["null_mean"]):
                        rep["check_c"]["mismatch"].append({"key": k, "driver": [v["p"], v["null_mean"]], "stored": [st["p"], st["null_mean"]]})
    rep["elapsed_s"] = time.time() - t0
    rep["ok"] = not (rep["estimates"]["mismatch"] or rep["run_of_record_ci"]["mismatch"] or rep["registered_p"]["method_mismatch"]
                     or rep["registered_p"]["p_mismatch"] or rep["registered_p"]["holm_decision_mismatch"] or rep["check_c"]["mismatch"])
    return rep


def glmm_job_table(ns, R):
    out = []
    for fam in FAM_ORDER:
        if fam == "RQ1_excess_divergence":
            continue
        for m in ns["MODELS"]:
            g = R["primary"][fam]["results"][m]["glmm"]
            ok = g.get("status") == "ok"
            failed = g.get("status") == "failed"
            out.append({"family": fam, "model": m, "status": g.get("status"),
                        "formula": g.get("formula") if ok else (f"{g.get('formula')} (tried with every optimizer; none converged)" if failed
                                                                else f"{PLANNED_FORMULA} (planned; stopped at {g.get('status')}, not fitted)"),
                        "random_effects": "(1 | query)" if ok else ("(1 | query), not converged" if failed else "(1 | query) planned"),
                        "optimizer": g.get("optimizer") if ok else ("none converged" if failed else "not applicable"),
                        "tried": g.get("tried") if g.get("tried") is not None else "not applicable (no fit attempted)",
                        "singular": g.get("singular") if ok else "not applicable",
                        "random_intercept_sd": g.get("random_intercept_sd") if ok else "not applicable",
                        "n": g.get("n"), "n_unit": N_UNIT[fam], "n_query": g.get("n_query"), "events": g.get("events"),
                        "fallback_applied": not ok, "fallback_reason": None if ok else g.get("status")})
    return out


def denominators(S):
    ns = S.ns
    A3 = ns["ARMS3"]
    hum = {}
    spec = {"items": ns["brand_items"]()}
    for m in ns["MODELS"]:
        for a in A3:
            rs = [r for r in S.base["human"] if r["model"] == m and r["arm"] == a]
            loc = glob = amb = unc = with_class = with_price = 0
            cur = Counter()
            for r in rs:
                l_, n_, am, un = ns["per_answer_mentions"](r, spec)
                loc += l_; glob += n_ - l_; amb += am; unc += un
                with_class += n_ > 0
                with_price += ns["has_price"](r)
                for _, c in r["prices"]:
                    cur[c if c in ("BDT", "USD", "unstated") else "other"] += 1
            hum[f"{m}|{a}"] = {"answers": len(rs), "answers_with_classified_mention": with_class, "local_mentions": loc,
                               "global_mentions": glob, "ambiguous_mentions": amb, "unclassifiable_mentions": unc,
                               "answers_with_price_entry": with_price,
                               "price_entries": {k: cur.get(k, 0) for k in ("BDT", "USD", "other", "unstated")}}
    cor = {}
    for m in ns["MODELS"]:
        for a in A3:
            nd = [r for r in S.base["refusal"] if r["model"] == m and r["arm"] == a]
            cor[f"{m}|{a}"] = {"non_degenerate_answers": len(nd), "refusals": sum(r["outcome"] == "refusal" for r in nd)}
            if a in ("bn", "bl"):
                rv = [r for r in S.base["reversion"] if r["model"] == m and r["arm"] == a]
                cor[f"{m}|{a}"].update({"non_refused_non_degenerate_answers": len(rv),
                                        "reversions": sum(r["outcome"] == "language_reversion" for r in rv)})
    return {"human": hum, "corpus": cor}


def posthoc_real(S, R, rob):
    """items 1-4 and 6 on the data of S (real after the declaration; synthetic in rehearsal)"""
    ns = S.ns
    fams = {}
    timing = Counter()
    all_keys = []
    for fam in FAM_ORDER:
        layer = fam_def(ns, fam)[0]
        rows = fam_rows(fam, S.base)
        t0 = time.time()
        cellv = fam_cells(ns, fam, rows)
        pqs, est = {}, {}
        for m in ns["MODELS"]:
            for a, b in fam_def(ns, fam)[2]:
                k = f"{m}|{a}-{b}"
                pqs[k] = per_query(ns, fam, cellv, S.frames[layer], m, a, b)
                est[k] = estimate_of(pqs[k])
        timing["item1_estimands"] += time.time() - t0
        t0 = time.time()
        me = {k: mean_effect(pqs[k], S.sbs[layer]) for k in pqs}
        timing["item2a_mean_effect"] += time.time() - t0
        t0 = time.time()
        rz = randomization_family(ns, fam, cellv, S.frames[layer], SEEDS["rand"][fam], N_RAND, est)
        timing["item2b_randomization"] += time.time() - t0
        t0 = time.time()
        iv = {}
        for k, pq in pqs.items():
            if len(pq) < 2:
                iv[k] = {"ci": None, "reason": "fewer than two eligible queries", "dropped_resamples": None}
                continue
            reps, dropped = S.sbs[layer].mean(pq)
            ci = ns["pct"](reps)
            if ci[0] is None:
                iv[k] = {"ci": None, "reason": "no defined resample", "dropped_resamples": int(dropped)}
                continue
            iv[k] = {"ci": ci, "dropped_resamples": int(dropped), "degenerate": bool(ci[0] == ci[1]),
                     "descriptive_only": not me[k]["test"]}
        timing["item3_intervals"] += time.time() - t0
        st = {k: stored_contrast(R, fam, *k.split("|")[:1], *k.split("|")[1].split("-")) for k in pqs}
        hreg = R["holm"][fam]
        hme = holm_map(ns, {k: me[k]["p"] for k in pqs})
        hrz = holm_map(ns, {k: rz[k]["p"] for k in pqs})
        ent = {}
        for k in pqs:
            m, con = k.split("|")
            a, b = con.split("-")
            ids = sorted(pqs[k])
            ent[k] = {"estimate": est[k], "scale": "mean Delta (dimensionless)" if fam == "RQ1_excess_divergence" else "proportion (x100 = percentage points)",
                      "n_query": len(ids), "query_ids": ids, "by_category": dict(Counter(S.CAT[q] for q in ids)),
                      "stored": {"estimate": st[k]["estimate"], "n_query": st[k]["n_query"], "ci": st[k]["ci"], "p": st[k]["p"], "method": st[k]["method"],
                                 "p_holm": hreg[k]["p_holm"], "reject": hreg[k]["reject"], "log_odds": st[k].get("log_odds")},
                      "mean_effect": me[k], "mean_effect_holm": hme[k], "randomization": rz[k], "randomization_holm": hrz[k],
                      "stratified_interval": iv[k]}
            all_keys.append((fam, k))
        fams[fam] = ent
    # Holm over all 96 (descriptive)
    for tag, getp in (("registered", lambda e: e["stored"]["p"]), ("mean_effect", lambda e: e["mean_effect"]["p"]),
                      ("randomization", lambda e: e["randomization"]["p"])):
        h = holm_map(ns, {f"{f}|{k}": getp(fams[f][k]) for f, k in all_keys})
        for f, k in all_keys:
            fams[f][k][f"holm96_{tag}"] = h[f"{f}|{k}"]
    # item 4
    disagreements = []
    for f, k in all_keys:
        e = fams[f][k]
        reg_rej, me_rej, rz_rej = e["stored"]["reject"], e["mean_effect_holm"]["reject"], e["randomization_holm"]["reject"]
        mk = rob[f].get(k, {})
        if f == "RQ1_excess_divergence":
            gates = {"(c)": mk.get("c")}
        elif e["stored"]["method"] == "glmm_wald":
            gates = {"(a)": mk.get("a"), "(b)": mk.get("b")}
        else:
            gates = {}
        gate_ok = all(v == "supported" for v in gates.values())
        concl = bool(reg_rej and me_rej and rz_rej and gate_ok)
        e["item4"] = {"registered_reject": reg_rej, "mean_effect_reject": me_rej, "randomization_reject": rz_rej,
                      "support_gates": gates if gates else "not applicable (F.3 fallback: checks (a) and (b) do not apply)",
                      "conclusion": concl, "direction": None if e["estimate"] is None else ("+" if e["estimate"] > 0 else ("-" if e["estimate"] < 0 else "0"))}
        if len({reg_rej, me_rej, rz_rej}) > 1 or (reg_rej and me_rej and rz_rej and not gate_ok):
            disagreements.append({"key": f"{f}|{k}", "registered": reg_rej, "mean_effect": me_rej, "randomization": rz_rej,
                                  "gates": gates, "conclusion": concl})
    return {"families": fams, "disagreements": disagreements, "timing": dict(timing)}


def outputs_of_record(ns, R, rob):
    rows = []
    allp = {}
    for fam in FAM_ORDER:
        for m in ns["MODELS"]:
            for a, b in fam_def(ns, fam)[2]:
                allp[f"{fam}|{m}|{a}-{b}"] = stored_contrast(R, fam, m, a, b)["p"]
    h96 = holm_map(ns, allp)
    for fam in FAM_ORDER:
        for m in ns["MODELS"]:
            for a, b in fam_def(ns, fam)[2]:
                k = f"{m}|{a}-{b}"
                st = stored_contrast(R, fam, m, a, b)
                lo = st.get("log_odds") if st["method"] == "glmm_wald" else None
                row = {"family": fam, "key": k, "estimate": st["estimate"], "estimate_unit": "mean Delta" if fam == "RQ1_excess_divergence" else "proportion difference",
                       "ci_run_of_record": st["ci"], "n_query": st["n_query"], "method": st["method"], "p": st["p"],
                       "p_holm_family": R["holm"][fam][k]["p_holm"], "decision": R["holm"][fam][k]["reject"], "p_holm_96": h96[f"{fam}|{k}"]["p_holm"],
                       "log_odds": ({"estimate": lo["estimate"], "se": lo["se"], "wald_ci": [lo["ci_low"], lo["ci_high"]],
                                     "boot_ci": lo.get("boot_ci", "not stored"), "boot_dropped": lo.get("boot_dropped", "not stored")} if lo else "not applicable")}
                if fam == "RQ1_excess_divergence":
                    c = R["sensitivity"]["RQ1_permutation"]["results"].get(k, {})
                    row["check_a"] = row["check_b"] = "not applicable"
                    row["check_c"] = {"p": c.get("p"), "support": rob[fam][k]["c"]} if c.get("n_query") else "not stored (no paired query)"
                else:
                    row["check_c"] = "not applicable"
                    if st["method"] == "glmm_wald":
                        row["check_a"] = {"boot_ci": lo.get("boot_ci", "not stored"), "dropped": lo.get("boot_dropped", "not stored"), "support": rob[fam][k]["a"]}
                    else:
                        row["check_a"] = "not applicable (F.3 fallback)"
                    hx = R["sensitivity"][HET[fam]]["results"][m]["contrasts"][f"{a}-{b}"]
                    row["check_b"] = {"method": hx["test"]["method"], "p": hx["test"]["p"],
                                      "log_odds": hx.get("log_odds", {}).get("estimate") if hx.get("log_odds") else "not applicable",
                                      "support": rob[fam][k]["b"]}
                rows.append(row)
    return rows


def fmt(x, nd=4):
    if x is None:
        return "–"
    if isinstance(x, str):
        return x
    if abs(x) < 1e-4 and x != 0:
        return f"{x:.2e}"
    return f"{x:.{nd}f}"


def render_real(res):
    L = ["# N1 — post-hoc mean-effect and randomization tests beside the registered results (REV-10, REV-12)", "",
         "Post-hoc, declared before computation; beside and outside the results of record. Holm within each family at .05; "
         "the 96-test Holm columns are descriptive. Scalar estimates in percentage points (pp), RQ1 in units of mean Δ.", ""]
    L += ["## 6(c) Post-hoc results per contrast", "",
          "| family | model | contrast | estimate | n q | registered P (Holm) | mean-effect P (Holm fam / 96) | randomization P (Holm fam / 96) | stratified 95% interval | run-of-record interval | decisions reg/(a)/(b) | item 4 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for fam in FAM_ORDER:
        sc = 1.0 if fam == "RQ1_excess_divergence" else 100.0
        for k, e in res["posthoc"]["families"][fam].items():
            m, con = k.split("|")
            est = None if e["estimate"] is None else e["estimate"] * sc
            iv = e["stratified_interval"]
            ivs = "–" if iv["ci"] is None else f"[{iv['ci'][0]*sc:+.2f}, {iv['ci'][1]*sc:+.2f}]" + (" descr." if iv.get("descriptive_only") else "") + (" degen." if iv.get("degenerate") else "")
            rr = e["stored"]["ci"]
            rrs = "–" if rr is None or rr[0] is None else f"[{rr[0]*sc:+.2f}, {rr[1]*sc:+.2f}]"
            me, rz = e["mean_effect"], e["randomization"]
            mes = (fmt(me["p"]) if me["test"] else f"1 (no test: {me['reason']})") + f" ({fmt(e['mean_effect_holm']['p_holm'])} / {fmt(e['holm96_mean_effect']['p_holm'])})"
            rzs = (fmt(rz["p"]) if rz["test"] else "1 (no eligible query)") + f" ({fmt(e['randomization_holm']['p_holm'])} / {fmt(e['holm96_randomization']['p_holm'])})"
            i4 = e["item4"]
            dec = "/".join("R" if x else "–" for x in (i4["registered_reject"], i4["mean_effect_reject"], i4["randomization_reject"]))
            L.append(f"| {fam} | {m} | {con} | {'–' if est is None else f'{est:+.3f}'} | {e['n_query']} | {fmt(e['stored']['p'])} ({fmt(e['stored']['p_holm'])}) | {mes} | {rzs} | {ivs} | {rrs} | {dec} | {'conclusion ' + i4['direction'] if i4['conclusion'] else 'no conclusion'} |")
    L += ["", "## Disagreements (registered, mean-effect and randomization decisions differ, or a support gate fails)", ""]
    for d in res["posthoc"]["disagreements"]:
        L.append(f"- {d['key']}: registered {'reject' if d['registered'] else 'no'}, mean-effect {'reject' if d['mean_effect'] else 'no'}, randomization {'reject' if d['randomization'] else 'no'}; gates {d['gates']}; conclusion {d['conclusion']}")
    if not res["posthoc"]["disagreements"]:
        L.append("- none")
    L += ["", "## 6(a) Outputs of record (stored; Holm over 96 is new and descriptive)", "",
          "| family | model | contrast | estimate [run-of-record CI] | method | P | Holm fam | Holm 96 | decision | log-odds (SE) [Wald] {boot} | checks (a)/(b)/(c) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["outputs_of_record"]:
        m, con = r["key"].split("|")
        sc = 1.0 if r["family"] == "RQ1_excess_divergence" else 100.0
        ci = r["ci_run_of_record"]
        ests = "–" if r["estimate"] is None else f"{r['estimate']*sc:+.3f}" + ("" if not ci or ci[0] is None else f" [{ci[0]*sc:+.3f}, {ci[1]*sc:+.3f}]")
        lo = r["log_odds"]
        sg = lambda x, spec="+.2f": "–" if x is None else format(x, spec)
        bci = lo["boot_ci"] if not isinstance(lo, str) else None
        bcs = (f"{sg(bci[0])}, {sg(bci[1])}" if isinstance(bci, list) and bci and bci[0] is not None else
               ("not run" if isinstance(bci, list) else str(bci)))
        los = lo if isinstance(lo, str) else f"{sg(lo['estimate'])} ({sg(lo['se'], '.2f')}) [{sg(lo['wald_ci'][0])}, {sg(lo['wald_ci'][1])}] " + "{" + bcs + "}"
        ck = []
        for c in ("check_a", "check_b", "check_c"):
            v = r[c]
            ck.append(v if isinstance(v, str) else v.get("support", "–"))
        L.append(f"| {r['family']} | {m} | {con} | {ests} | {r['method']} | {fmt(r['p'])} | {fmt(r['p_holm_family'])} | {fmt(r['p_holm_96'])} | {'reject' if r['decision'] else '–'} | {los} | {' / '.join(ck)} |")
    L += ["", "## 6(a) The 30 primary-family model jobs (stored diagnostics, not refitted)", "",
          "| family | model | status | formula | optimizer | tried | singular | RE SD | n (unit) | queries | events per arm | fallback |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for j in res["glmm_jobs"]:
        ev = "; ".join(f"{a} {v['y1']}/{v['n']}" for a, v in (j["events"] or {}).items())
        L.append(f"| {j['family']} | {j['model']} | {j['status']} | {j['formula']} | {j['optimizer']} | {json.dumps(j['tried'], ensure_ascii=False)} | {j['singular']} | {fmt(j['random_intercept_sd']) if not isinstance(j['random_intercept_sd'], str) else j['random_intercept_sd']} | {j['n']} ({j['n_unit']}) | {j['n_query']} | {ev} | {'yes: ' + j['fallback_reason'] if j['fallback_applied'] else 'no'} |")
    L += ["", "## 6(b) Denominators", "", "### Human layer (P-filtered rows, before pairing)", "",
          "| model | arm | answers | with classified mention | local | global | ambiguous | unclassifiable | with price | BDT | USD | other | unstated |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in res["denominators"]["human"].items():
        m, a = k.split("|")
        pe = v["price_entries"]
        L.append(f"| {m} | {a} | {v['answers']} | {v['answers_with_classified_mention']} | {v['local_mentions']} | {v['global_mentions']} | {v['ambiguous_mentions']} | {v['unclassifiable_mentions']} | {v['answers_with_price_entry']} | {pe['BDT']} | {pe['USD']} | {pe['other']} | {pe['unstated']} |")
    L += ["", "### Corpus", "", "| model | arm | non-degenerate | refusals | neither refused nor degenerate | reversions |", "|---|---|---|---|---|---|"]
    for k, v in res["denominators"]["corpus"].items():
        m, a = k.split("|")
        L.append(f"| {m} | {a} | {v['non_degenerate_answers']} | {v['refusals']} | {v.get('non_refused_non_degenerate_answers', '–')} | {v.get('reversions', '–')} |")
    L += ["", "### Queries entering each paired estimate (newly reconstructed; the stored results keep no ID lists)", ""]
    for fam in FAM_ORDER:
        for k, e in res["posthoc"]["families"][fam].items():
            ok = "matches" if e["n_query"] == e["stored"]["n_query"] and _close(e["estimate"], e["stored"]["estimate"]) else "DIFFERS"
            L.append(f"- {fam} {k}: n = {e['n_query']} (stored n_query {e['stored']['n_query']}, estimate {ok}); by category {dict(sorted(e['by_category'].items()))}; IDs {' '.join(e['query_ids'])}")
    return "\n".join(L) + "\n"


NULL_STATUS = [
    "Scenario (i), distributional null: the imposed answer-allocation null holds, and the expected contrasts, the mean Delta included, "
    "are zero under that generator. This does not by itself establish the signed-rank test's symmetry or a correctly specified mixed model.",
    "Scenario (ii), arm-block-symmetric mean-null benchmark: the scalar contrasts included have zero expected means under the generator; "
    "symmetry alone does not establish the registered mixed model's likelihood or its conditional log-odds reading, and the generator does "
    "not in general meet the answer-level exchangeability that the randomization test requires. RQ1 is not included in scenario (ii).",
    "The registered tests' rates are rejection rates against each generator's stated null benchmark, which is distinct from calibration "
    "under a correctly specified model. The randomization test is not run in scenario (ii), so no rate for it is estimated there.",
    "The intersection rows are upper-envelope rates for the post-hoc interpretation rule under the same generator, not the measured rate of "
    "the full rule: the stored support gates are left out, and the two-test intersection also leaves out the randomization test.",
    "Family-wise rates are complete-null rates under the two generators, not the worst case over all zero-mean or partial-null "
    "configurations; neither test is protected against the outcome-informed choice of the design, and neither is study-wide control."]


def render_cal(summ, ns):
    L = ["# N1 — calibration of the registered and post-hoc tests on null data sets made from the real data (REV-10)", "",
         "Calibration conditional on the observed answer pools and the selected design; it does not reproduce the adaptive sizing and "
         "gives no empirical study-wide rate. Rates are rejection rates at P <= .05 against each generator's stated null benchmark; "
         "family-wise rates count data sets with at least one Holm rejection at .05 within the family (Wilson 95% intervals); "
         "unadjusted-rate intervals come from 10,000 resamples of whole data sets. Mean-effect test: 10,000 stratified resamples; "
         "randomization test: 10,000 draws.", "", "## Null status", ""] + [f"- {x}" for x in NULL_STATUS] + [""]
    for key in ("human|i", "human|ii", "corpus|i", "corpus|ii"):
        if key not in summ:
            continue
        s = summ[key]
        L += [f"## {key.replace('|', ', scenario ')} — {s['n_datasets']} data sets", "",
              "| family | procedure | family-average unadjusted rate [95%] | FWER (Holm) [Wilson 95%] | data sets |", "|---|---|---|---|---|"]
        for fam, F in s["families"].items():
            for pr, name in (("reg", "registered"), ("me", "mean-effect (a)"), ("rz", "randomization (b)")):
                if pr not in F["family_average"]:
                    continue
                fa, fw = F["family_average"][pr], F["fwer"][pr]
                L.append(f"| {fam} | {name} | {fa['rate']:.4f} [{fa['ci'][0]:.4f}, {fa['ci'][1]:.4f}] | {fw['rate']:.4f} [{fw['wilson'][0]:.4f}, {fw['wilson'][1]:.4f}] | {fw['n']} |")
            for nm, v in F["intersections"].items():
                L.append(f"| {fam} | ∩ {nm.replace('_', ' ')} | – | {v['rate']:.4f} [{v['wilson'][0]:.4f}, {v['wilson'][1]:.4f}] | {v['n']} |")
        L += ["", "Per-contrast unadjusted rejection rates [95% from resamples of whole data sets]:", ""]
        for fam, F in s["families"].items():
            for pr, name in (("reg", "registered"), ("me", "mean-effect"), ("rz", "randomization")):
                if pr not in F["per_contrast"]:
                    continue
                cells = "; ".join(f"{k} {v['rate']:.3f} [{v['ci'][0]:.3f}, {v['ci'][1]:.3f}]" for k, v in F["per_contrast"][pr].items())
                L.append(f"- {fam}, {name}: {cells}")
        L += ["", "Diagnostics (job-level fit status counts over data sets x models; singular fits; contrast-level methods; mean-effect no-test counts):", ""]
        for fam, F in s["families"].items():
            L.append(f"- {fam}: {json.dumps(F['diagnostics'], ensure_ascii=False)}")
        L.append(f"- job errors: {len(s.get('job_errors', []))}; mean seconds per data set: {json.dumps({k: round(v, 2) for k, v in s.get('timing_mean_s', {}).items()})}")
        L.append("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("study", "real", "bench", "calibrate"):
        s = sub.add_parser(name)
        s.add_argument("--root", required=True)
        s.add_argument("--code-dir", required=True)
        s.add_argument("--tmp", required=True)
        s.add_argument("--synthetic", action="store_true")
        s.add_argument("--registration", default=None)
        s.add_argument("--out", required=True)
        if name == "study":
            s.add_argument("--no-registered", action="store_true")
            s.add_argument("--no-randomization", action="store_true")
            s.add_argument("--no-per-query", action="store_true")
        if name in ("bench", "calibrate"):
            s.add_argument("--layer", choices=["human", "corpus"], required=True)
            s.add_argument("--scenario", choices=["i", "ii"], required=True)
            s.add_argument("--n", type=int, required=True)
            s.add_argument("--n-rand", type=int, required=True)
            s.add_argument("--workers", type=int, default=2)
            s.add_argument("--stream", choices=["cal", "bench"], required=True)
    s = sub.add_parser("summarize")
    s.add_argument("--code-dir", required=True)
    s.add_argument("--inputs", nargs="+", required=True)
    s.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "summarize":
        ns, _ = load_registered(a.code_dir)
        allres = {"driver_sha256": DRIVER_SHA, "rate_boot_seed": SEEDS["cal_rate_boot"]}
        for p in a.inputs:
            lines = [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
            L, sc = lines[0]["layer"], lines[0]["scenario"]
            allres[f"{L}|{sc}"] = summarize_cal(ns, lines, L, sc)
            allres[f"{L}|{sc}"]["source"] = {"file": Path(p).name, "sha256": sha(p)}
        Path(a.out + ".json").write_text(json.dumps(allres, indent=1), encoding="utf-8")
        Path(a.out + ".md").write_text(render_cal(allres, ns), encoding="utf-8")
        return
    if not a.synthetic and a.registration is None:
        raise SystemExit("--registration is required for real data")
    if a.cmd == "bench" and not (a.synthetic and a.stream == "bench"):
        raise SystemExit("bench runs on synthetic data with the bench streams only")
    if a.cmd == "calibrate" and not a.synthetic and a.stream != "cal":
        raise SystemExit("calibration on the real data uses the declared calibration streams (--stream cal)")
    S = Setup(a.root, a.code_dir, a.tmp, a.synthetic, a.registration)
    if a.cmd == "study":
        rseeds = None if a.no_randomization else dict(SEEDS["rand"])
        t0 = time.time()
        r = evaluate(S.ns, FAM_ORDER, dict(S.base), S.frames, S.sbs, S.b0s, rseeds, registered=not a.no_registered, want_pq=not a.no_per_query)
        r.update({"elapsed_s": time.time() - t0, "setup_s": S.setup_s, "checks": S.checks, "driver_sha256": DRIVER_SHA})
        Path(a.out).write_text(json.dumps(r, indent=1), encoding="utf-8")
        return
    if a.cmd == "real":
        R = json.loads((S.root / "ANALYSIS-RESULTS.json").read_text(encoding="utf-8"))
        rob = parse_robustness((S.root / "ANALYSIS-ROBUSTNESS.md").read_text(encoding="utf-8"))
        t0 = time.time()
        rep = reproduce(S, R)
        out = {"driver_sha256": DRIVER_SHA, "checks": S.checks, "setup_s": S.setup_s, "reproduction": rep,
               "seeds": SEEDS, "resamples": B_BOOT, "draws": N_RAND, "min_queries_mean_effect": MIN_Q,
               "stratified_matrix": {L: {"seed": S.sbs[L].seed, "nb": S.sbs[L].nb, "queries": len(S.sbs[L].q), "per_category": S.sbs[L].per_cat}
                                     for L in ("human", "corpus")}}
        if not rep["ok"]:
            Path(a.out + ".json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
            raise SystemExit("REPRODUCTION FAILED: the driver does not reproduce the stored run of record; nothing else computed")
        t1 = time.time()
        out["posthoc"] = posthoc_real(S, R, rob)
        out["outputs_of_record"] = outputs_of_record(S.ns, R, rob)
        out["glmm_jobs"] = glmm_job_table(S.ns, R)
        t2 = time.time()
        out["denominators"] = denominators(S)
        out["timing_s"] = {"reproduction": t1 - t0, "posthoc": t2 - t1, "denominators": time.time() - t2}
        Path(a.out + ".json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        Path(a.out + ".md").write_text(render_real(out), encoding="utf-8")
        return
    base = SEEDS[a.stream][f"{a.layer}|{a.scenario}"]
    el = calibrate(S, a.layer, a.scenario, a.n, a.n_rand, a.workers, a.out, Path(a.tmp), base, progress=1 if a.cmd == "bench" else 25)
    print(json.dumps({"elapsed_s": el, "setup_s": S.setup_s}))


if __name__ == "__main__":
    main()
