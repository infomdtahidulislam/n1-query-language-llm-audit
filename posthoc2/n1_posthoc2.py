#!/usr/bin/env python3
"""n1_posthoc2.py — N1: items C, D and E of the writer's V16 request (post-hoc; declared in a dated post-freeze record
before it computes anything on study data; reported beside and outside the results of record). Nothing here amends the
registration, re-runs a registered analysis in place, or changes a frozen file, a stored output or a table: every output
is a new file in posthoc2/.

REUSE. Record 53's driver posthoc/n1_posthoc.py (sha256 c7bb9cad...) is imported read-only: its whitelist loader of the
registered definitions of n1_analysis.py (with one name added to the whitelist in memory, machine_layer, the registered
builder of the machine-extracted layer, which item E needs), its tests (mean_effect = test (a), randomization_family =
test (b)), its stratified count matrices, family definitions, arm-block generator (scenario (ii)) and reproduction.
n1_analysis.py's argument parsing and module-level pipeline are never executed. Every registered test runs through the
registered functions (setdiv, setdiv_perm, share_outcome, answer_binary, holm, glmm with n1_glmm.R unchanged); only
their calls of the R bridge are gathered, for a batch of simulated data sets, into one call of the registered glmm()
(the jobs are fitted independently, so each fit is the one a separate call gives: the validation checks it).
The canonicalisation of each rater's own labels is that of records 47 and 50 (exploratory/n1_overlap_raters.py, sha256
a4518fbc...), whose definitions are loaded read-only by the same kind of whitelist (its module-level code, which
runs the registered pipeline through n1_review_common.py, is never executed).

ITEMS (every seed, count, threshold and configuration is a constant below; the declaration record quotes them)
  C  calibration of record 53's interpretation rule for the zero-mean hypotheses: outcome-model generators (complete
     nulls, non-exchangeable mean nulls with cancelling query effects, partial nulls with effects of the observed size,
     the arm-block scenario (ii), and rater-label generators on the observed rater assignment and label sources), the
     rule's support checks recomputed on each simulated data set where the rule needs them, upper envelopes, the
     acceptance criterion and the declared alternative A*.
  D  each rater against the consensus of the other two on the 303 triple-rated expansion answers.
  E  detection limits (80% power) of the registered tests for the refusal contrasts (coded corpus) and the
     bl_translit contrasts (F.10, human and machine layers), by simulation; cluster-aware one-sided upper bounds for the
     zero-event and near-zero refusal cells.

Subcommands: verify, reproduce, D, E, E-summary, C, C-checks, C-summary, check-a-one.
"""
import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")
import argparse, ast, builtins, gc, hashlib, importlib.util, json, math, re, sys, time
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
DRIVER_SHA = sha(HERE)
POSTHOC_SHA = "c7bb9cad438726d71dbe421bd7589fd9d3e71f83f446b1421dfc310562e79ce2"
POSTHOC_TESTS_SHA = "2edd30d7faa4e0abe5be9fa14f99dd45b7b7b18c07dbee346d5956da58e488b2"
OVERLAP_SHA = "a4518fbc843534720093fb901bfdb437d768a17b75b44d20ad5a70b9fe2179f3"
OVERLAP_OUT_SHA = "59cc956bcb6376c3abe8cbdd44dc8802f7bd9a758d3de5b216eb581f2fc2ea9b"


def import_posthoc(code_dir):
    p = Path(code_dir) / "posthoc" / "n1_posthoc.py"
    if sha(p) != POSTHOC_SHA:
        raise SystemExit("posthoc/n1_posthoc.py is not the file record 53 registers")
    spec = importlib.util.spec_from_file_location("n1_posthoc", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["n1_posthoc"] = mod
    spec.loader.exec_module(mod)
    return mod


D = import_posthoc(HERE.parent.parent)          # the analysis root holds posthoc/ and posthoc2/ side by side
FAM_ORDER = D.FAM_ORDER

# ---------------------------------------------------------------------------------------------------- fixed values
ALPHA = 0.05
N_RAND, N_SF, N_CHECK_C, N_BOOT_A = 10000, 10000, 10000, 10000
TIE = 1e-12
WILSON_Z = 1.959963984540054
MODELS_A = ["claude-sonnet-5", "deepseek-v4-flash", "gemini-3-flash"]       # P2: the models that carry effects
RATERS = ("R1", "R2", "R3")
SEEDS2 = {
    "C": {"RQ1_excess_divergence": 20261301, "RQ2_local_share": 20261302, "RQ4_bdt_share": 20261303,
          "RQ4_price_mention": 20261304, "RQ5_reversion": 20261305, "RQ5_refusal": 20261306},
    "C_check_a_order": 20261310,
    "A_real": 20261401,
    "E": {"refusal": 20261211, "f10_share_human": 20261212, "f10_share_machine": 20261213,
          "f10_delta_human": 20261214, "f10_delta_machine": 20261215},
    "D_frame": 20261021,                  # reused: the resampling frame of records 47 and 50 (77 overlap query IDs)
    "reused": {"stratified_matrix_human": 20261101, "stratified_matrix_corpus": 20261102,
               "check_a_boot_human": 20260926, "check_a_boot_corpus": 20260927,
               "f10_zero_boot_human": 20260928, "f10_zero_boot_machine": 20260929},
}
PURPOSE2 = {"generator": 1, "randomization": 2, "signflip": 3, "check_c": 4, "grouping": 6}
# ---- C: configurations, replication counts, acceptance
CONFIGS = {
    "RQ1_excess_divergence": ["C0", "P1", "P2", "R_obs", "R_stress", "R_real"],
    "RQ2_local_share": ["C0", "ii", "C2", "P1", "P2", "R_obs", "R_stress", "R_real"],
    "RQ4_bdt_share": ["C0", "ii", "C2", "P1", "P2", "R_obs", "R_stress", "R_real"],
    "RQ4_price_mention": ["C0", "ii", "C2", "P1", "P2", "R_obs", "R_stress", "R_real"],
    "RQ5_reversion": ["C0", "ii", "C2", "P2"],
    "RQ5_refusal": ["C0", "ii", "C2", "P1", "P2"],
}
CFG_INDEX = {"C0": 0, "ii": 1, "C2": 2, "P1": 3, "P2": 4, "R_obs": 5, "R_stress": 6, "R_real": 7}
COMPLETE = {"C0", "ii", "C2", "R_obs", "R_stress", "R_real"}                  # every hypothesis of the family true
RATER_CFGS = ("R_obs", "R_stress", "R_real")      # R_obs, R_stress: assignment re-drawn; R_real: the realized one
N_REP_C = {"RQ1_excess_divergence": 2000, "RQ2_local_share": 2000, "RQ4_price_mention": 2000, "RQ5_reversion": 2000,
           "RQ4_bdt_share": 1000, "RQ5_refusal": 1000}
C_BATCH = {"RQ1_excess_divergence": 25, "RQ2_local_share": 10, "RQ4_bdt_share": 10, "RQ4_price_mention": 10,
           "RQ5_reversion": 10, "RQ5_refusal": 10}
ACCEPT_WILSON_LOWER_MAX = 0.05          # a configuration passes iff the Wilson 95% lower limit of the FWER <= .05
CHECK_A_BUDGET_S = 4 * 3600             # wall-clock budget of the check (a) phase of C (after the main phase)
# ---- rater-label generators (C.4): R_obs and R_stress re-draw the assignment under its own rule in every data set
#      (single raters, the overlap); R_real keeps the realized assignment and label sources, with R_stress's distortions
#      tilt: (local->global, global->local) per classified mention; price: (sensitivity, false positive);
#      bdt: flip probability per price entry; sets: (drop per entity, add a rater-specific token per answer);
#      round2: a systematic effect of the validation round on its 38 consensus labels, applied after the consensus
RATER_PARAMS = {
    "R_obs": {"sets": {"R1": (0.0, 0.0), "R2": (0.01, 0.03), "R3": (0.01, 0.03)},
              "tilt": {"R1": (0.0, 0.0), "R2": (0.0, 0.02), "R3": (0.02, 0.0)},
              "price": {"R1": (1.0, 0.0), "R2": (0.99, 0.02), "R3": (0.97, 0.0)},
              "bdt": {"R1": 0.0, "R2": 0.01, "R3": 0.01},
              "round2": {"sets": 0.05, "tilt_gl": 0.05, "price_fp": 0.03, "bdt_to_bdt": 0.03}},
    "R_stress": {"sets": {"R1": (0.0, 0.0), "R2": (0.03, 0.09), "R3": (0.03, 0.09)},
                 "tilt": {"R1": (0.0, 0.0), "R2": (0.0, 0.06), "R3": (0.06, 0.0)},
                 "price": {"R1": (1.0, 0.0), "R2": (0.97, 0.06), "R3": (0.91, 0.0)},
                 "bdt": {"R1": 0.0, "R2": 0.03, "R3": 0.03},
                 "round2": {"sets": 0.15, "tilt_gl": 0.15, "price_fp": 0.09, "bdt_to_bdt": 0.09}},
}
# ---- E: grids, replications, thresholds
E_ALPHA = {"refusal": 0.05 / 18, "f10": 0.05}
E_GRID = {"refusal": [0.0, 0.0025, 0.0035, 0.005, 0.007, 0.01, 0.014, 0.02, 0.028, 0.04, 0.056, 0.08, 0.113, 0.16],
          "share": [0.0, 0.025, 0.035, 0.05, 0.07, 0.10, 0.14, 0.20, 0.28, 0.40, 0.56, 0.80],
          "delta": [0.0, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.85, 1.0]}
N_REP_E = {"refusal": 200, "f10_share_human": 200, "f10_share_machine": 200, "f10_delta_human": 100, "f10_delta_machine": 200}
#   f10_delta_human: 100 (a declared approximation: the registered signed-rank test on at most 12 queries with ties runs
#   SciPy's exact enumeration, about 0.4 s per call, so 200 would take D and E past the request's three hours)
E_BATCH = 50
E_POWER = 0.80
BOUND_CONF = 0.95
NEAR_ZERO_MAX = 10                       # refusal cells with 1 to 10 refusals are 'near-zero'
F10_ARMS = ["bl_translit", "bn", "bl"]   # the registered arm order of the F.10 share fits
C10 = [("bn", "bl_translit"), ("bl", "bl_translit")]
DECL_KEY = "items C, D and E declared before they are computed"
R54_HASHES = {"POSTHOC-RESULTS.json": "9c0435ee00fd55249000f7f4063ccd6e2a9b1a7c30d414e0500e39e3c91517fb",
              "POSTHOC-RESULTS.md": "d1cf7954d54aad15e0fd8578c566c3412a84ea7cba4713bead4d1fb61db1a0d0",
              "CALIBRATION-SUMMARY.json": "4e899959a36730f47713349890de4fff0f00437b519d73e88d65aa1ee882ae75",
              "CALIBRATION-SUMMARY.md": "4e8dc6f9b64b3702c789da355483ef415e2fa8b77dbe6cf844d488941a4fa107"}
LABEL_HASHES = {"R1": "e81ae46f5723052708dd777893488da50b0bbae27872a58cf33c22e5bd1f74bc",
                "R2": "699bec10cf993bb7742e7e852c778689d550a5b2839c4eaa0cb99cebf83af63b",
                "R3": "1f2c81dd0941700442fc13e8999f1e4b37a10ba4c37de818c3d8f1e9adc772c0"}


def stream(*ints):
    return int(np.random.SeedSequence([int(x) for x in ints]).generate_state(1, np.uint64)[0])


def wilson(x, n):
    return D.wilson(x, n, WILSON_Z)


def pass_max(n):
    """largest x with Wilson lower limit of x/n at most ACCEPT_WILSON_LOWER_MAX (-1 when there is no data set)"""
    if n <= 0:
        return -1
    x = 0
    while x <= n and wilson(x, n)[0] <= ACCEPT_WILSON_LOWER_MAX:
        x += 1
    return x - 1


def g8(x):
    return None if x is None else float(f"{float(x):.10g}")


# ---------------------------------------------------------------------------------------------------- loaders
def load_ns(code_dir):
    """record 53's whitelist loader with machine_layer added to its whitelist in memory (the file is unchanged)"""
    old = set(D.WL_FUNCS)
    D.WL_FUNCS = old | {"machine_layer"}
    try:
        ns, state = D.load_registered(code_dir)
    finally:
        D.WL_FUNCS = old
    return ns, state


OV_NAMES = ["fold", "load_map", "make_resolver", "PRICE_RE", "fold_currency", "norm_amount", "price_set_rater", "rl", "SETF",
            "canon_list", "human", "consensus_of", "TUP", "price_list_from_serialised", "share_of"]


def load_overlap_defs(code_dir, root, ns):
    """records 47 and 50's canonicalisation: the whitelisted definitions of exploratory/n1_overlap_raters.py, executed in a
    namespace holding the registered EXCLUDED and bclass; the script's module-level code is not executed"""
    p = Path(code_dir) / "exploratory" / "n1_overlap_raters.py"
    raw = p.read_bytes()
    if hashlib.sha256(raw).hexdigest() != OVERLAP_SHA:
        raise SystemExit("exploratory/n1_overlap_raters.py is not the file record 47 registers")
    tree = ast.parse(raw.decode("utf-8"))
    body, seen = [], set()
    for n in tree.body:
        if isinstance(n, ast.Import):
            body.append(n)
        elif isinstance(n, ast.ImportFrom) and n.module != "n1_review_common":
            body.append(n)
        elif isinstance(n, ast.FunctionDef) and n.name in OV_NAMES:
            body.append(n); seen.add(n.name)
        elif isinstance(n, ast.Assign) and all(isinstance(t, ast.Name) and t.id in OV_NAMES for t in n.targets):
            body.append(n); seen |= {t.id for t in n.targets}
    if seen != set(OV_NAMES):
        raise SystemExit(f"overlap whitelist mismatch: {sorted(set(OV_NAMES) - seen)}")
    g = {"__name__": "n1_overlap_definitions", "__builtins__": builtins, "ROOT": Path(root), "EXCLUDED": ns["EXCLUDED"],
         "bclass": ns["bclass"]}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(p), "exec"), g)
    return g


def find_record(reg_text, key):
    k = reg_text.index(" Document precedence: **PROJECT-BRIEF.md §9b is canonical**")
    starts = [m.start() for m in re.finditer(r" Post-freeze record \(", reg_text)]
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else k
        if key in reg_text[s:reg_text.find("):", s)]:
            return reg_text[s:e]
    return None


def verify_real2(root, code_dir, registration):
    """record 53's input checks (registered scripts, ANALYSIS-RESULTS.json, ANALYSIS-ROBUSTNESS.md, every meta.inputs
    file), then the post-hoc outputs against record 54, record 53's driver and harness, record 47's script, the label
    exports and record 50's stored overlap output, and the guard: the registration holds this driver's declaration record
    and that record quotes this file's sha256"""
    root, code_dir = Path(root), Path(code_dir)
    base = D.verify_real(root, code_dir, registration)
    reg = Path(registration).read_text(encoding="utf-8")
    decl = find_record(reg, DECL_KEY)
    if decl is None:
        raise SystemExit("the declaration record of items C, D and E is not in the registration: real data refused")
    if DRIVER_SHA not in decl:
        raise SystemExit(f"the declaration record does not quote this driver's sha256 {DRIVER_SHA}")
    r54 = find_record(reg, "post-hoc mean-effect and randomization tests, stratified intervals and null calibration computed")
    r53 = find_record(reg, "post-hoc mean-effect and randomization tests, stratified intervals and null calibration declared")
    r47 = find_record(reg, "four review descriptives declared before they are computed")
    if not (r54 and r53 and r47):
        raise SystemExit("records 47, 53 and 54 are not all found in the registration")
    got = {}
    for f, h in R54_HASHES.items():
        g = sha(root / "posthoc" / f)
        if g != h or h not in r54:
            raise SystemExit(f"posthoc/{f} is not the file record 54 registers")
        got[f"posthoc/{f}"] = g
    for f, h in (("n1_posthoc.py", POSTHOC_SHA), ("n1_posthoc_tests.py", POSTHOC_TESTS_SHA)):
        if sha(code_dir / "posthoc" / f) != h or h not in r53:
            raise SystemExit(f"posthoc/{f} is not the file record 53 registers")
        got[f"posthoc/{f}"] = h
    if sha(code_dir / "exploratory" / "n1_overlap_raters.py") != OVERLAP_SHA or OVERLAP_SHA[:8] not in r47:
        raise SystemExit("exploratory/n1_overlap_raters.py is not the file record 47 registers")
    got["exploratory/n1_overlap_raters.py"] = OVERLAP_SHA
    for rt, h in LABEL_HASHES.items():
        if sha(root / f"LABEL-EXPANSION-{rt}-labels.json") != h:
            raise SystemExit(f"LABEL-EXPANSION-{rt}-labels.json is not the export of the expansion round")
        got[f"LABEL-EXPANSION-{rt}-labels.json"] = h
    if sha(root / "exploratory" / "OVERLAP-RATER-VS-CONSENSUS.json") != OVERLAP_OUT_SHA:
        raise SystemExit("exploratory/OVERLAP-RATER-VS-CONSENSUS.json is not the stored output of record 50")
    got["exploratory/OVERLAP-RATER-VS-CONSENSUS.json"] = OVERLAP_OUT_SHA
    base.update({"posthoc2_inputs": got, "driver_sha256": DRIVER_SHA})
    return base


# ---------------------------------------------------------------------------------------------------- set-up
class Setup2:
    def __init__(self, root, code_dir, tmp, synthetic, registration=None, machine=False):
        t0 = time.time()
        self.root, self.code_dir, self.synthetic = Path(root), Path(code_dir), synthetic
        if synthetic:
            if not (self.root / "SYNTHETIC").exists():
                raise SystemExit("synthetic mode needs a root made by the validation harness (SYNTHETIC marker): refused")
            self.checks = {"synthetic": True, "driver_sha256": DRIVER_SHA}
        else:
            self.checks = verify_real2(self.root, self.code_dir, registration)
        self.ns, state = load_ns(self.code_dir)
        D.init_state(self.ns, state, self.root, self.code_dir / "n1_glmm.R", tmp)
        ns = self.ns
        self.H = ns["human_layer"]()
        self.Cp = ns["corpus_layer"]()
        self.M = ns["machine_layer"]() if machine else None
        self.frames = {"human": sorted({r["query"] for r in self.H}), "corpus": sorted({r["query"] for r in self.Cp})}
        self.CAT = ns["CAT"]
        for L, n_total, n_cat in (("human", 80, 8), ("corpus", 250, 25)):
            per = Counter(self.CAT[q] for q in self.frames[L])
            if len(self.frames[L]) != n_total or len(per) != 10 or set(per.values()) != {n_cat}:
                raise SystemExit(f"{L} query frame is not {n_total} queries with {n_cat} in each of 10 categories: {dict(per)}")
        self.base = {"human": D.analysis_rows(ns, "RQ2_local_share", self.H),
                     "refusal": D.analysis_rows(ns, "RQ5_refusal", self.Cp),
                     "reversion": D.analysis_rows(ns, "RQ5_reversion", self.Cp)}
        self.sbs = {L: D.strat_boot(ns, self.frames[L], self.CAT, D.SEEDS["strat"][L]) for L in ("human", "corpus")}
        self.b0s = {L: D.zero_boot(ns, self.frames[L], D.SEEDS["strat"][L]) for L in ("human", "corpus")}
        # the human layer's label sources: design information of the analysis set (which answer has which label source)
        self.design = {}
        for l in open(self.root / "EXPANSION-ANALYSIS-SET-v2.jsonl", encoding="utf-8"):
            r = json.loads(l)
            self.design[r["key"]] = {"source": r["label_source"], "by": r["labelled_by"], "model": r["model_id"],
                                     "query": r["query_id"], "arm": r["arm"], "rep": int(r["rep"])}
        # F.10 frames and rows exactly as the registered analysis forms them
        self.f10q = {"human": sorted({r["query"] for r in self.H if r["arm"] == "bl_translit"}),
                     "machine": sorted({r["query"] for r in self.Cp if r["arm"] == "bl_translit"})}
        self.f10rows = {"human": [r for r in self.H if r["query"] in set(self.f10q["human"])]}
        if machine:
            self.f10rows["machine"] = [r for r in self.M if r["query"] in set(self.f10q["machine"])]
        self.b0_f10 = {"human": ns["Boot"](set(self.f10q["human"]), 0, SEEDS2["reused"]["f10_zero_boot_human"]),
                       "machine": ns["Boot"](set(self.f10q["machine"]), 0, SEEDS2["reused"]["f10_zero_boot_machine"])}
        # pseudo-brands with fixed classes for the local-share generators (never names of the tables)
        for i in range(400):
            ns["BCLASS"][f"__simL{i}"] = "local"
            ns["BCLASS"][f"__simG{i}"] = "global"
        self._boot_a = {}
        self.setup_s = time.time() - t0

    def boot_a(self, layer, nb=N_BOOT_A):
        """check (a)'s count matrix: the registered layer matrix (Boot, 10,000 resamples, seeds 20260926 / 20260927)"""
        if (layer, nb) not in self._boot_a:
            seed = SEEDS2["reused"]["check_a_boot_human"] if layer == "human" else SEEDS2["reused"]["check_a_boot_corpus"]
            self._boot_a[(layer, nb)] = self.ns["Boot"](set(self.frames[layer]), nb, seed)
        return self._boot_a[(layer, nb)]


def design_check(S):
    """the observed rater assignment against the expansion's rules (design information only): two repetitions of a query,
    arm and model never single-labelled by one rater; rater counts in each query x arm group"""
    by_cell = defaultdict(list)
    groups = defaultdict(Counter)
    src = Counter()
    for k, d in S.design.items():
        src[d["source"]] += 1
        if d["source"] == "single":
            by_cell[(d["model"], d["query"], d["arm"])].append(d["by"])
            groups[(d["query"], d["arm"])][d["by"]] += 1
    same = sum(1 for v in by_cell.values() if len(v) != len(set(v)))
    full = [g for g in groups.values() if sum(g.values()) == 12]
    bal = sum(1 for g in full if sorted(g.values()) == [4, 4, 4])
    by_arm = defaultdict(Counter)
    for d in S.design.values():
        by_arm[d["source"]][d["arm"]] += 1
    single_by = Counter(d["by"] for d in S.design.values() if d["source"] == "single")
    return {"sources": dict(src), "single_by_rater": dict(single_by), "sources_by_arm": {k: dict(v) for k, v in by_arm.items()},
            "cells_with_two_single_labels_by_one_rater": same, "single_cells": len(by_cell),
            "full_query_arm_groups_of_12_single": len(full), "full_groups_balanced_4_4_4": bal}


# ---------------------------------------------------------------------------------------------------- batched bridge
def batched(ns, fn, datasets, keep=None, errors=None):
    """fn(rows) on each data set with its glmm() calls gathered into one call of the registered glmm(). Pass 1 collects
    every job (placeholder fits), pass 2 fits the kept jobs in one call (n1_glmm.R unchanged, jobs fitted independently;
    a job left out returns the status 'separation' and its result is never read), pass 3 re-runs fn with the stored
    fits. keep(k, job_id) selects jobs (default all). A failed call is retried once, then each data set alone once more."""
    real = ns["glmm"]
    per = []

    def collect(jobs):
        per.append([dict(j) for j in jobs])
        return {j["id"]: {"status": "separation"} for j in jobs}
    ns["glmm"] = collect
    counts = []
    try:
        for rows in datasets:
            n0 = len(per)
            fn(rows)
            counts.append(len(per) - n0)
    finally:
        ns["glmm"] = real
    big, idx = [], 0
    for k, c in enumerate(counts):
        for t in range(c):
            for j in per[idx]:
                if keep is None or keep(k, j["id"]):
                    big.append(dict(j, id=f"{k}|{t}|{j['id']}"))
            idx += 1

    def fit(jobs):
        for attempt in (1, 2):
            try:
                return real(jobs)
            except BaseException as e:
                if isinstance(e, KeyboardInterrupt):
                    raise
                if errors is not None:
                    errors.append({"attempt": attempt, "n_jobs": len(jobs), "error": f"{type(e).__name__}: {str(e)[-300:]}"})
            finally:
                D.clean_tmp(ns)
        return None
    fits = fit(big) if big else {}
    if fits is None:
        fits = {}
        for k in range(len(datasets)):
            sub = [j for j in big if j["id"].split("|", 1)[0] == str(k)]
            f = fit(sub) if sub else {}
            if f is None:
                raise RuntimeError("registered fit failed on one data set after its retries")
            fits.update(f)
    out = []
    for k, rows in enumerate(datasets):
        calls = [0]

        def stub(jobs, k=k, calls=calls):
            t = calls[0]; calls[0] += 1
            return {j["id"]: fits.get(f"{k}|{t}|{j['id']}", {"status": "separation"}) for j in jobs}
        ns["glmm"] = stub
        try:
            out.append(fn(rows))
        finally:
            ns["glmm"] = real
    return out


def registered_fn(ns, fam, b0, re_="query", boot=None):
    """the registered primary call of the family (record 53's registered_family), with the random-effects term and the
    GLMM bootstrap as arguments: re_='query+cell' is check (b)'s fit, boot=Boot is check (a)'s fit"""
    A3, C3, P = ns["ARMS3"], ns["C3"], ns["P"]
    if fam == "RQ1_excess_divergence":
        return lambda rows: ns["setdiv"](rows, "brands", ns["jaccard"], C3, P, b0, "post-hoc")
    if fam == "RQ2_local_share":
        return lambda rows: ns["share_outcome"](rows, {"items": ns["brand_items"]()}, A3, C3, P, b0, "post-hoc", boot, re_)
    if fam == "RQ4_price_mention":
        return lambda rows: ns["answer_binary"](rows, ns["has_price"], A3, C3, P, b0, "post-hoc", boot, re_)
    if fam == "RQ4_bdt_share":
        return lambda rows: ns["share_outcome"](rows, {"binary": ns["bdt_entries"]}, A3, C3, P, b0, "post-hoc", boot, re_)
    if fam == "RQ5_reversion":
        return lambda rows: ns["answer_binary"](rows, lambda r: int(r["outcome"] == "language_reversion"), ["bl", "bn"], [("bn", "bl")],
                                                ns["nonref_nondeg"], b0, "post-hoc", boot, re_)
    return lambda rows: ns["answer_binary"](rows, lambda r: int(r["outcome"] == "refusal"), A3, C3, ns["nondeg"], b0, "post-hoc", boot, re_)


def reg_summary(ns, fam, res):
    """per contrast: the final P as the registered Holm block reads it (record 53's registered_p), the method and the
    query-level estimate"""
    out = {}
    for m in ns["MODELS"]:
        for a, b in D.fam_def(ns, fam)[2]:
            k = f"{m}|{a}-{b}"
            if fam == "RQ1_excess_divergence":
                x = res["results"][k]
                p = x.get("test", {}).get("p", 1.0) if x.get("n_query") else 1.0
                out[k] = {"p": 1.0 if p is None else float(p), "m": "w" if x.get("n_query") else "n", "est": x.get("mean_delta")}
            else:
                c = res["results"][m]["contrasts"][f"{a}-{b}"]
                p = c["test"]["p"]
                out[k] = {"p": 1.0 if p is None else float(p), "m": "g" if c["test"]["method"] == "glmm_wald" else "f", "est": c.get("diff")}
    return out


# ---------------------------------------------------------------------------------------------------- A*'s test
def signflip(per_q, seed, B=N_SF):
    """A*'s mean-targeted test of a zero mean of the per-query paired differences: sign-flip (Rademacher) randomization,
    statistic |sum d| (equivalent to the studentized one-sample t, since sum d^2 is invariant under sign changes),
    P = (1 + #{|S*| >= |S| - tol}) / (B + 1), tol = 1e-12 x max(1, sum|d|); exact for independent differences symmetric
    about zero, asymptotically valid for independent heterogeneous differences with zero means"""
    d = np.array(list(per_q.values()), dtype=float)
    if len(d) == 0:
        return {"p": 1.0, "test": False, "reason": "no eligible query"}
    if float(np.max(np.abs(d))) == 0.0:
        return {"p": 1.0, "test": False, "reason": "all differences zero"}
    s0 = abs(float(d.sum()))
    tol = TIE * max(1.0, float(np.abs(d).sum()))
    rng = np.random.default_rng(seed)
    sg = rng.integers(0, 2, size=(B, len(d)), dtype=np.int8).astype(np.float64) * 2.0 - 1.0
    p = (1 + int(np.sum(np.abs(sg @ d) >= s0 - tol))) / (B + 1)
    return {"p": float(p), "test": True}


def holm_rej(ns, pmap):
    return {k for k, v in D.holm_map(ns, pmap).items() if v["reject"]}


# ---------------------------------------------------------------------------------------------------- C: outcome structure
SHARE_FAMS = ("RQ2_local_share", "RQ4_bdt_share")


def fam_units(ns, fam, r):
    """(successes, units) of one analysed answer: classified mentions (local share), price entries (BDT share), or the
    answer itself (binary families)"""
    if fam == "RQ2_local_share":
        loc, n, _, _ = ns["per_answer_mentions"](r, {"items": ns["brand_items"]()})
        return loc, n
    if fam == "RQ4_bdt_share":
        ys = ns["bdt_entries"](r)
        return sum(ys), len(ys)
    if fam == "RQ4_price_mention":
        return int(ns["has_price"](r)), 1
    if fam == "RQ5_reversion":
        return int(r["outcome"] == "language_reversion"), 1
    return int(r["outcome"] == "refusal"), 1


def with_outcome(ns, fam, r, x, n, extra=None):
    """the answer with its analysed outcome replaced (units, filters and every other field as observed)"""
    if fam == "RQ2_local_share":
        keep = [e for e in r["brands"] if ns["bclass"](e) not in ("local", "global")]
        return dict(r, brands=keep + [f"__simL{i}" for i in range(x)] + [f"__simG{i}" for i in range(n - x)])
    if fam == "RQ4_bdt_share":
        z = extra if extra is not None else [1] * x + [0] * (n - x)
        return dict(r, prices=[(a, "BDT" if zz else "USD") for (a, _), zz in zip(r["prices"], z)])
    if fam == "RQ4_price_mention":
        return dict(r, prices=[(1.0, "BDT")] if x else [])
    if fam == "RQ5_reversion":
        return dict(r, outcome="language_reversion" if x else "valid")
    return dict(r, outcome="refusal" if x else ("valid" if r["outcome"] == "refusal" else r["outcome"]))


def rho_of(cells_units):
    """moment estimator of the beta-binomial intra-answer correlation from (x, n, cell proportion) triples, in [0, .95]"""
    num = den = 0.0
    for x, n, pc in cells_units:
        if n >= 2 and 0 < pc < 1:
            num += (x - n * pc) ** 2 - n * pc * (1 - pc)
            den += n * (n - 1) * pc * (1 - pc)
    return float(min(0.95, max(0.0, num / den))) if den > 0 else 0.0


def draw_units(rng, n, p, rho):
    if n == 0:
        return 0
    if rho > 0 and 0 < p < 1:
        p = float(rng.beta(p * (1 - rho) / rho, (1 - p) * (1 - rho) / rho))
    return int(rng.binomial(n, p))


class Structure:
    """observed per-query structure of one family's analysis rows: pooled proportion per model x query (b), observed
    proportion per model x query x arm (o), pooled over bn and bl (bnbl), units per answer, the beta-binomial
    intra-answer correlation per model (share families), each contrast's eligible queries and their intersection"""
    def __init__(self, ns, fam, rows, frame):
        self.fam, self.rows = fam, rows
        _, self.arms, self.cons, _ = D.fam_def(ns, fam)
        self.units = [fam_units(ns, fam, r) for r in rows]
        pooled, cell, bnbl = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
        for r, (x, n) in zip(rows, self.units):
            for d_, k in ((pooled, (r["model"], r["query"])), (cell, (r["model"], r["query"], r["arm"]))):
                d_[k][0] += x; d_[k][1] += n
            if r["arm"] in ("bn", "bl"):
                bnbl[(r["model"], r["query"])][0] += x; bnbl[(r["model"], r["query"])][1] += n
        pr = lambda v: (v[0] / v[1]) if v[1] else 0.0
        self.b = {k: pr(v) for k, v in pooled.items()}
        self.o = {k: pr(v) for k, v in cell.items()}
        self.bnbl = {k: pr(v) for k, v in bnbl.items()}
        self.rho = {}
        for m in ns["MODELS"]:
            tr = [(x, n, self.o[(m, r["query"], r["arm"])]) for r, (x, n) in zip(rows, self.units) if r["model"] == m]
            self.rho[m] = rho_of(tr) if fam in SHARE_FAMS else 0.0
        cellv = D.fam_cells(ns, fam, rows)
        self.elig = {}
        for m in ns["MODELS"]:
            for a, b in self.cons:
                self.elig[f"{m}|{a}-{b}"] = sorted(D.per_query(ns, fam, cellv, frame, m, a, b))
        self.estar = {m: sorted(set.intersection(*[set(self.elig[f"{m}|{a}-{b}"]) for a, b in self.cons])) for m in ns["MODELS"]}
        self.cellv = cellv


class Generator:
    """one configuration of one family; draw(rng) returns simulated analysis rows (the observed rows, models, queries,
    arms, repetitions, filters, units, undefined markers and label sources; new outcomes)"""
    def __init__(self, S, fam, cfg):
        self.S, self.ns, self.fam, self.cfg = S, S.ns, fam, cfg
        ns = self.ns
        self.layer = D.fam_def(ns, fam)[0]
        self.rows = D.fam_rows(fam, S.base)
        self.frame = S.frames[self.layer]
        self.meta = {"family": fam, "config": cfg}
        if fam == "RQ1_excess_divergence":
            self._init_sets()
        else:
            self.st = Structure(ns, fam, self.rows, self.frame)
            if cfg != "ii":
                self._init_probs()
        if cfg in RATER_CFGS:
            self._init_raters()
        self.truth, self.mu = self._truth()
        self.meta["true_nulls"] = sorted(k for k, v in self.truth.items() if v)
        self.meta["expected_estimand"] = self.mu

    # ---- outcome probabilities per answer
    def _init_probs(self):
        st, cfg = self.st, self.cfg
        offs = self._rotation() if cfg == "C2" else {}
        p = []
        for r in self.rows:
            mq = (r["model"], r["query"])
            if cfg in ("C0",) + RATER_CFGS or (cfg == "P2" and r["model"] not in MODELS_A):
                pq = st.b[mq]
            elif cfg in ("P1", "P2"):
                if len(st.arms) == 3:
                    pq = st.o[(r["model"], r["query"], "en")] if r["arm"] == "en" else st.bnbl[mq]
                else:                                   # reversion: the models of P2 keep their observed arm proportions
                    pq = st.o[(r["model"], r["query"], r["arm"])]
            elif cfg == "C2":
                pq = st.b[mq] + offs.get((r["model"], r["query"], r["arm"]), 0.0)
            else:
                raise ValueError(cfg)
            p.append(min(1.0, max(0.0, pq)))
        self.p = p
        self.meta["rho"] = dict(st.rho)

    def _rotation(self):
        """C2: per model and category, the queries eligible for every contrast of the family, in a seeded order, form
        groups of k = the number of arms; within a group each member's probability moves by s*v on a different arm (a
        seeded rotation); s = +1 when 1 - max(b) >= min(b) over the group, else -1; v = min(target, room), room =
        1 - max(b) or min(b); every group cancels exactly in every contrast, so every contrast's mean over its eligible
        queries is exactly zero while no shifted query is exchangeable across arms. target (per model) = the median over
        the family's contrasts of the SD of the observed per-query paired differences"""
        ns, st, S = self.ns, self.st, self.S
        target = {}
        for m in ns["MODELS"]:
            sds = [float(np.std(list(D.per_query(ns, self.fam, st.cellv, self.frame, m, a, b).values()), ddof=1))
                   for a, b in st.cons if len(st.elig[f"{m}|{a}-{b}"]) >= 2]
            target[m] = float(np.median(sds)) if sds else 0.0
        rng = np.random.default_rng(stream(SEEDS2["C"][self.fam], CFG_INDEX["C2"], 0, PURPOSE2["grouping"]))
        arms = list(st.arms)
        k = len(arms)
        offs, groups = {}, []
        for m in ns["MODELS"]:
            by_cat = defaultdict(list)
            for q in st.estar[m]:
                by_cat[S.CAT[q]].append(q)
            for c in sorted(by_cat):
                qs = [by_cat[c][i] for i in rng.permutation(len(by_cat[c]))]
                for g in range(len(qs) // k):
                    mem = qs[g * k:(g + 1) * k]
                    rot = [arms[i] for i in rng.permutation(k)]
                    bs = [st.b[(m, q)] for q in mem]
                    up = (1 - max(bs)) >= min(bs)
                    v = min(target[m], (1 - max(bs)) if up else min(bs))
                    s = 1.0 if up else -1.0
                    for q, a in zip(mem, rot):
                        offs[(m, q, a)] = s * v
                    groups.append({"model": m, "category": c, "queries": mem, "arms": rot, "shift": s * v})
        self.meta["spread_target"] = target
        self.meta["groups"] = len(groups)
        self.meta["queries_shifted"] = sum(len(g["queries"]) for g in groups if g["shift"] != 0)
        self.meta["mean_abs_shift"] = float(np.mean([abs(g["shift"]) for g in groups])) if groups else 0.0
        return offs

    # ---- sets (RQ1)
    def _init_sets(self):
        pool, pool_arm, pool_bnbl = defaultdict(list), defaultdict(list), defaultdict(list)
        for r in self.rows:
            mq = (r["model"], r["query"])
            pool[mq].append(tuple(r["brands"]))
            pool_arm[(r["model"], r["query"], r["arm"])].append(tuple(r["brands"]))
            if r["arm"] in ("bn", "bl"):
                pool_bnbl[mq].append(tuple(r["brands"]))
        self.pool, self.pool_arm, self.pool_bnbl = pool, pool_arm, pool_bnbl

    def _set_pool(self, r):
        mq = (r["model"], r["query"])
        cfg = self.cfg
        if cfg in ("C0",) + RATER_CFGS or (cfg == "P2" and r["model"] not in MODELS_A):
            return self.pool[mq]
        if cfg in ("P1", "P2"):
            return self.pool_arm[(r["model"], r["query"], "en")] if r["arm"] == "en" else self.pool_bnbl[mq]
        raise ValueError(cfg)

    # ---- which hypotheses are true
    def _truth(self):
        ns, fam, cfg = self.ns, self.fam, self.cfg
        keys = D.keys_of(ns, fam)
        if fam == "RQ1_excess_divergence":
            out = {}
            for k in keys:
                m, con = k.split("|")
                out[k] = cfg in COMPLETE or (cfg == "P1" and con == "bn-bl") or (cfg == "P2" and (m not in MODELS_A or con == "bn-bl"))
            return out, None
        if cfg == "ii":
            return {k: True for k in keys}, None
        pm = {(r["model"], r["query"], r["arm"]): pr for r, pr in zip(self.rows, self.p)}
        out, mu = {}, {}
        for k in keys:
            m, con = k.split("|")
            a, b = con.split("-")
            el = self.st.elig[k]
            mu[k] = float(np.mean([pm[(m, q, a)] - pm[(m, q, b)] for q in el])) if el else 0.0
            out[k] = True if cfg in COMPLETE else abs(mu[k]) <= 1e-12
            if cfg in COMPLETE and abs(mu[k]) > 1e-12:
                raise AssertionError(f"{fam} {cfg} {k}: expected estimand {mu[k]} is not zero")
        return out, mu

    # ---- rater-label process (R_obs, R_stress, R_real)
    def _init_raters(self):
        """the design of the human layer's labels (analysis-set fields only). The 38 validation-round answers keep their
        label source in every configuration (which drawn answers carry a Round-2 consensus is fixed by the draw). R_real:
        every answer keeps its realized label source and rater. R_obs and R_stress: in every data set the assignment is
        re-drawn under its own rule (record 12: randomized and balanced within query x arm, each rater 4 of the 12 answers
        of a full group, a model's two repetitions never to one rater) over the answers without a Round-2 label, and the
        overlap is re-drawn as a simple random sample of as many of those answers as the realized overlap holds"""
        des = self.S.design
        self.redraw = self.cfg in ("R_obs", "R_stress")
        self.par = RATER_PARAMS["R_stress" if self.cfg == "R_real" else self.cfg]
        self.round2 = {k for k, d in des.items() if d["source"] == "round2-consensus"}
        self.n_overlap = sum(1 for d in des.values() if d["source"] == "consensus-3")
        groups = defaultdict(lambda: defaultdict(list))
        for k in sorted(des, key=lambda k: (des[k]["query"], des[k]["arm"], des[k]["model"], des[k]["rep"], k)):
            if k not in self.round2:
                groups[(des[k]["query"], des[k]["arm"])][des[k]["model"]].append(k)
        self.groups = {g: {m: list(v) for m, v in sorted(ms.items())} for g, ms in sorted(groups.items())}
        self.pool_keys = sorted(k for k in des if k not in self.round2)
        for r in self.rows:
            d = des[r["key"]]
            if d["source"] == "single" and d["by"] not in RATERS:
                raise SystemExit(f"single label of {r['key']} is not by R1, R2 or R3")
            if d["source"] not in ("single", "consensus-3", "round2-consensus"):
                raise SystemExit(f"unknown label source {d['source']}")
        self.meta["label_design"] = ({"assignment": "re-drawn in every data set", "overlap_per_data_set": self.n_overlap,
                                      "round2_fixed": len(self.round2)} if self.redraw else
                                     {"assignment": "realized", **dict(Counter(des[r["key"]]["source"] for r in self.rows))})

    def assign(self, rng):
        """one draw of the assignment under its rule: {key: rater} for the answers without a Round-2 label, and the
        overlap set. A full group (six models with two answers each) gets each rater pair (R1,R2), (R1,R3), (R2,R3) for
        two models, in random order and orientation; other groups take a model's two answers to the pair of distinct
        raters that keeps the counts most balanced (ties at random) and single answers to the least-loaded rater."""
        pairs = [("R1", "R2"), ("R1", "R3"), ("R2", "R3")]
        out = {}
        for g, ms in self.groups.items():
            models = list(ms)
            if len(models) == 6 and all(len(v) == 2 for v in ms.values()):
                for mi, t in zip(models, rng.permutation(6)):
                    pr = list(pairs[int(t) // 2])
                    if rng.random() < 0.5:
                        pr.reverse()
                    for key, rt in zip(ms[mi], pr):
                        out[key] = rt
                continue
            cnt = {x: 0 for x in RATERS}
            for i in rng.permutation(len(models)):
                ks = ms[models[int(i)]]
                rest = ks
                if len(ks) >= 2:
                    score = lambda pp: (max(cnt[x] + (x in pp) for x in RATERS), sum(cnt[x] for x in pp))
                    best = min(score(pp) for pp in pairs)
                    cand = [pp for pp in pairs if score(pp) == best]
                    pp = list(cand[int(rng.integers(0, len(cand)))])
                    if rng.random() < 0.5:
                        pp.reverse()
                    for key, rt in zip(ks[:2], pp):
                        out[key] = rt; cnt[rt] += 1
                    rest = ks[2:]
                for key in rest:
                    lo = min(cnt.values())
                    cand = [x for x in RATERS if cnt[x] == lo]
                    rt = cand[int(rng.integers(0, len(cand)))]
                    out[key] = rt; cnt[rt] += 1
        ov = {self.pool_keys[int(i)] for i in rng.choice(len(self.pool_keys), size=self.n_overlap, replace=False)}
        return out, ov

    def sources(self, rng):
        """(kind, rater) for every analysis row: kind single, overlap or round2"""
        des = self.S.design
        if not self.redraw:
            return [("single", des[r["key"]]["by"]) if des[r["key"]]["source"] == "single" else
                    (("overlap", None) if des[r["key"]]["source"] == "consensus-3" else ("round2", None)) for r in self.rows]
        asg, ov = self.assign(rng)
        return [("round2", None) if r["key"] in self.round2 else (("overlap", None) if r["key"] in ov else ("single", asg[r["key"]]))
                for r in self.rows]

    def _label(self, rng, rt, latent, r):
        fam, par = self.fam, self.par
        if fam == "RQ1_excess_divergence":
            drop, add = par["sets"][rt]
            s = [e for e in latent if not (drop and rng.random() < drop)]
            if add and rng.random() < add:
                s.append(f"__rater_{rt}_{r['query']}")
            return tuple(sorted(set(s)))
        if fam == "RQ2_local_share":
            lg, gl = par["tilt"][rt]
            return [(0 if (lg and rng.random() < lg) else 1) if c else (1 if (gl and rng.random() < gl) else 0) for c in latent]
        if fam == "RQ4_price_mention":
            se, fp = par["price"][rt]
            return int(rng.random() < (se if latent else fp))
        f = par["bdt"][rt]
        return [(1 - c) if (f and rng.random() < f) else c for c in latent]

    def _round2(self, rng, lab, r):
        fam, p2 = self.fam, self.par["round2"]
        if fam == "RQ1_excess_divergence":
            return tuple(sorted(set(lab) | ({f"__round2_{r['query']}"} if rng.random() < p2["sets"] else set())))
        if fam == "RQ2_local_share":
            return [1 if (c == 1 or rng.random() < p2["tilt_gl"]) else 0 for c in lab]
        if fam == "RQ4_price_mention":
            return int(lab == 1 or rng.random() < p2["price_fp"])
        return [1 if (c == 1 or rng.random() < p2["bdt_to_bdt"]) else 0 for c in lab]

    def _consensus(self, labs):
        if self.fam == "RQ1_excess_divergence":
            cnt = Counter(e for l in labs for e in l)
            return tuple(sorted(e for e, c in cnt.items() if c >= 2))
        if self.fam == "RQ4_price_mention":
            return int(sum(labs) >= 2)
        return [int(sum(col) >= 2) for col in zip(*labs)]

    # ---- one simulated data set
    def draw(self, rng):
        ns, fam, cfg = self.ns, self.fam, self.cfg
        if cfg == "ii":
            return D.fam_rows(fam, D.null_dataset(ns, self.layer, "ii", self.S.base, rng))
        if cfg in RATER_CFGS:
            return self._draw_raters(rng)
        if fam == "RQ1_excess_divergence":
            out = []
            for r in self.rows:
                pool = self._set_pool(r)
                out.append(dict(r, brands=list(pool[int(rng.integers(0, len(pool)))])))
            return out
        return [with_outcome(ns, fam, r, draw_units(rng, n, p, self.st.rho[r["model"]]), n)
                for r, (_, n), p in zip(self.rows, self.st.units, self.p)]

    def _draw_raters(self, rng):
        ns, fam = self.ns, self.fam
        src = self.sources(rng)
        out = []
        for i, r in enumerate(self.rows):
            if fam == "RQ1_excess_divergence":
                pool = self.pool[(r["model"], r["query"])]
                latent = list(pool[int(rng.integers(0, len(pool)))])
            else:
                n = self.st.units[i][1]
                x = draw_units(rng, n, self.p[i], self.st.rho[r["model"]])
                if fam == "RQ4_price_mention":
                    latent = x
                else:
                    z = np.zeros(n, dtype=int)
                    if x:
                        z[rng.choice(n, size=x, replace=False)] = 1
                    latent = [int(v) for v in z]
            kind, rt = src[i]
            if kind == "single":
                lab = self._label(rng, rt, latent, r)
            else:
                lab = self._consensus([self._label(rng, x_, latent, r) for x_ in RATERS])
                if kind == "round2":
                    lab = self._round2(rng, lab, r)
            if fam == "RQ1_excess_divergence":
                out.append(dict(r, brands=list(lab)))
            elif fam == "RQ4_price_mention":
                out.append(with_outcome(ns, fam, r, lab, 1))
            elif fam == "RQ2_local_share":
                out.append(with_outcome(ns, fam, r, int(sum(lab)), len(lab)))
            else:
                out.append(with_outcome(ns, fam, r, int(sum(lab)), len(lab), extra=lab))
        return out


# ---------------------------------------------------------------------------------------------------- C: one data set
G = {}


def _worker_init(counter, tmp_root):
    with counter.get_lock():
        wid = counter.value
        counter.value += 1
    G["wid"] = wid
    D.set_tmp(G["S"].ns, Path(tmp_root) / f"w{wid}")
    gc.collect()
    gc.freeze()


def c_eval(S, fam, cfg, rows, rr, k, truth):
    """the registered test, test (a), test (b) and A*'s sign-flip test with Holm within the family; the upper envelope
    E0 = the contrasts all three of record 53's tests reject; check (c) for the true-null contrasts of RQ1 in E0"""
    ns = S.ns
    layer, arms, cons, kind = D.fam_def(ns, fam)
    base, ci = SEEDS2["C"][fam], CFG_INDEX[cfg]
    cellv = D.fam_cells(ns, fam, rows)
    keys = D.keys_of(ns, fam)
    pqs = {kk: D.per_query(ns, fam, cellv, S.frames[layer], kk.split("|")[0], *kk.split("|")[1].split("-")) for kk in keys}
    est = {kk: D.estimate_of(pqs[kk]) for kk in keys}
    me = {kk: D.mean_effect(pqs[kk], S.sbs[layer]) for kk in keys}
    rz = D.randomization_family(ns, fam, cellv, S.frames[layer], stream(base, ci, k, PURPOSE2["randomization"]), N_RAND, est)
    sf = {kk: signflip(pqs[kk], stream(base, ci, k, PURPOSE2["signflip"], j)) for j, kk in enumerate(keys)}
    reg = reg_summary(ns, fam, rr)
    rej = {"reg": holm_rej(ns, {kk: reg[kk]["p"] for kk in keys}), "me": holm_rej(ns, {kk: me[kk]["p"] for kk in keys}),
           "rz": holm_rej(ns, {kk: rz[kk]["p"] for kk in keys}), "sf": holm_rej(ns, {kk: sf[kk]["p"] for kk in keys})}
    ix = {kk: j for j, kk in enumerate(keys)}
    e0 = rej["reg"] & rej["me"] & rej["rz"]
    line = {"k": k, "c": [[g8(est[kk]), g8(reg[kk]["p"]), reg[kk]["m"], g8(me[kk]["p"]), g8(rz[kk]["p"]), g8(sf[kk]["p"])] for kk in keys],
            "rej": {t: sorted(ix[kk] for kk in v) for t, v in rej.items()}, "e0": sorted(ix[kk] for kk in e0), "chk": {}}
    flag = [kk for kk in keys if kk in e0 and truth[kk]]
    if fam == "RQ1_excess_divergence" and flag:
        pr = ns["setdiv_perm"](rows, "brands", ns["jaccard"], ns["C3"], ns["P"], stream(base, ci, k, PURPOSE2["check_c"]), N_CHECK_C, "check (c)")
        for kk in flag:
            x = pr["results"][kk]
            ok = x.get("p") is not None and x["p"] < 0.05 and (x.get("mean_delta") or 0) * (est[kk] or 0) > 0
            line["chk"][str(ix[kk])] = {"c": [g8(x.get("p")), bool(ok)]}
    return line, [kk for kk in flag if reg[kk]["m"] == "g"], est


def check_b(S, fam, items, errors=None):
    """check (b) for the flagged GLMM contrasts: the registered fit with (1|query) + (1|query:arm) of the contrast's
    model, read as n1_robustness.py reads it (P < .05 and the sign of the check's log-odds estimate, or of the
    fallback's paired difference, equal to the sign of the query-level estimate). items: (line, rows, keys, est);
    all fits of a batch in one call"""
    ns = S.ns
    layer = D.fam_def(ns, fam)[0]
    if not items:
        return
    fn = registered_fn(ns, fam, S.b0s[layer], re_="query+cell")
    models = [sorted({kk.split("|")[0] for kk in ks}) for _, _, ks, _ in items]
    res = batched(ns, fn, [rows for _, rows, _, _ in items], keep=lambda k, jid: jid in models[k], errors=errors)
    keys = D.keys_of(ns, fam)
    for (line, rows, ks, est), rr in zip(items, res):
        for kk in ks:
            m, con = kk.split("|")
            c = rr["results"][m]["contrasts"][con]
            if c["test"]["method"] == "glmm_wald":
                p, sign, meth = c["log_odds"]["p"], c["log_odds"]["estimate"], "g"
            else:
                p, sign, meth = c["test"]["p"], c.get("diff"), "f"
            ok = p is not None and p < 0.05 and (sign or 0) * (est[kk] or 0) > 0
            line["chk"].setdefault(str(keys.index(kk)), {})["b"] = [g8(p), bool(ok), meth]


def c_task(fam, cfg, ks):
    S = G["S"]
    ns = S.ns
    gen = G["gens"][(fam, cfg)]
    layer = D.fam_def(ns, fam)[0]
    t0 = time.time()
    base, ci = SEEDS2["C"][fam], CFG_INDEX[cfg]
    datasets = [gen.draw(np.random.default_rng(stream(base, ci, k, PURPOSE2["generator"]))) for k in ks]
    t1 = time.time()
    errors = []
    regs = batched(ns, registered_fn(ns, fam, S.b0s[layer]), datasets, errors=errors)
    t2 = time.time()
    lines, bitems = [], []
    for k, rows, rr in zip(ks, datasets, regs):
        line, bflag, est = c_eval(S, fam, cfg, rows, rr, k, gen.truth)
        lines.append(line)
        if bflag:
            bitems.append((line, rows, bflag, est))
    t3 = time.time()
    check_b(S, fam, bitems, errors)
    t4 = time.time()
    return lines, {"fam": fam, "cfg": cfg, "k0": ks[0], "n": len(ks), "worker": G.get("wid"), "generate": t1 - t0,
                   "registered": t2 - t1, "tests_and_check_c": t3 - t2, "check_b": t4 - t3, "check_b_items": len(bitems),
                   "total": t4 - t0, "job_errors": errors, "utc_end": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def run_pool(tasks, fn, workers, tmp_root, sink, log=print, progress_every=120):
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor, as_completed
    ctx = mp.get_context("fork")
    counter = ctx.Value("i", 0)
    t0 = last = time.time()
    done = 0
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx, initializer=_worker_init, initargs=(counter, tmp_root)) as ex:
        futs = [ex.submit(fn, *t) for t in tasks]
        for f in as_completed(futs):
            sink(f.result())
            done += 1
            if time.time() - last >= progress_every or done == len(futs):
                last = time.time()
                log(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC] {done}/{len(futs)} tasks, {time.time() - t0:.0f} s", flush=True)
    return time.time() - t0


def read_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def c_run(S, fams, out_dir, workers, tmp_root, n_override=None, configs=None):
    """C's main phase: every configuration of every family; resumable (a data set already in its JSONL file is skipped;
    lines are written only when their whole batch is done)"""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    gens = {}
    for fam in fams:
        for cfg in CONFIGS[fam]:
            if configs and cfg not in configs:
                continue
            g = gens[(fam, cfg)] = Generator(S, fam, cfg)
            p = out_dir / f"C-{fam}-{cfg}.meta.json"
            txt = json.dumps({"truth": g.truth, "meta": g.meta, "keys": D.keys_of(S.ns, fam), "driver_sha256": DRIVER_SHA},
                             indent=1, sort_keys=True)
            if p.exists() and p.read_text(encoding="utf-8") != txt:
                raise SystemExit(f"{p.name} differs from this run's configuration: refusing to mix runs")
            p.write_text(txt, encoding="utf-8")
    G["S"], G["gens"] = S, gens
    tasks = []
    for (fam, cfg) in gens:
        n = n_override or N_REP_C[fam]
        have = {l["k"] for l in read_jsonl(out_dir / f"C-{fam}-{cfg}.jsonl")}
        todo = [k for k in range(n) if k not in have]
        for i in range(0, len(todo), C_BATCH[fam]):
            tasks.append((fam, cfg, todo[i:i + C_BATCH[fam]]))
    # every configuration advances together: tasks ordered by their progress fraction
    tasks.sort(key=lambda t: (t[2][0] / (n_override or N_REP_C[t[0]]), FAM_ORDER.index(t[0]), CFG_INDEX[t[1]]))
    fh = {}
    tlog = open(out_dir / "C-timing.jsonl", "a", encoding="utf-8")

    def sink(res):
        lines, tm = res
        key = (tm["fam"], tm["cfg"])
        if key not in fh:
            fh[key] = open(out_dir / f"C-{key[0]}-{key[1]}.jsonl", "a", encoding="utf-8")
        fh[key].write("".join(json.dumps(l, separators=(",", ":")) + "\n" for l in lines))
        fh[key].flush(); os.fsync(fh[key].fileno())
        tlog.write(json.dumps(tm) + "\n"); tlog.flush()
    try:
        el = run_pool(tasks, c_task, workers, tmp_root, sink) if tasks else 0.0
    finally:
        for f in fh.values():
            f.close()
        tlog.close()
    return el, len(tasks)


# ---------------------------------------------------------------------------------------------------- C: check (a)
def check_a(S, fam, cfg, k, models, gen=None, nb=N_BOOT_A):
    """check (a) on one simulated data set: the data set re-drawn from its seed; for each listed model, the registered
    primary fit with the layer's registered count matrix, refitted on every resample by n1_glmm.R (bobyqa), read as
    n1_robustness.py reads it: supported iff the 95% bootstrap interval of the log-odds excludes 0 on the side of the
    log-odds estimate ('not run' when there is no interval: not supported). One R job per model gives all its contrasts."""
    gen = gen or Generator(S, fam, cfg)
    rows = gen.draw(np.random.default_rng(stream(SEEDS2["C"][fam], CFG_INDEX[cfg], k, PURPOSE2["generator"])))
    t0 = time.time()
    out = check_a_rows(S, fam, rows, models, nb)
    return {"fam": fam, "cfg": cfg, "k": k, "models": models, "contrasts": out, "seconds": time.time() - t0, "nb": nb,
            "utc_end": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def check_a_rows(S, fam, rows, models, nb=N_BOOT_A):
    ns = S.ns
    layer = D.fam_def(ns, fam)[0]
    fn = registered_fn(ns, fam, S.b0s[layer], re_="query", boot=S.boot_a(layer, nb))
    rr = batched(ns, fn, [rows], keep=lambda _k, jid: jid in models)[0]
    out = {}
    for m in models:
        for a, b in D.fam_def(ns, fam)[2]:
            c = rr["results"][m]["contrasts"][f"{a}-{b}"]
            lo = c.get("log_odds") or {}
            ci = lo.get("boot_ci")
            if c["test"]["method"] != "glmm_wald" or not ci or ci[0] is None:
                ok, st = False, "not run"
            else:
                ok = (ci[0] > 0 and lo["estimate"] > 0) or (ci[1] < 0 and lo["estimate"] < 0)
                st = "supported" if ok else "not supported"
            out[f"{m}|{a}-{b}"] = {"boot_ci": ci, "dropped": lo.get("boot_dropped"), "log_odds": lo.get("estimate"), "status": st,
                                   "supported": bool(ok)}
    return out


def load_c(out_dir, fam, cfg):
    out_dir = Path(out_dir)
    meta = json.loads((out_dir / f"C-{fam}-{cfg}.meta.json").read_text(encoding="utf-8"))
    lines = {}
    for l in read_jsonl(out_dir / f"C-{fam}-{cfg}.jsonl"):
        lines.setdefault(l["k"], l)
    return meta, [lines[k] for k in sorted(lines)]


def classify(fam, keys, truth, lines, a_res, star):
    """per data set, the conclusions on true-null contrasts: E0 (record 53's three tests; A*: and the sign-flip test),
    E1 (E0 and checks (b)/(c) where they apply), and the rule (E1 and check (a) for GLMM contrasts). Returns the counts
    of data sets with at least one such conclusion, and the data sets whose status needs check (a) (no conclusion
    known without it)."""
    X0 = X1 = Xr = pos = neg = 0
    pend = []
    for l in lines:
        e0 = set(l["e0"]) & set(l["rej"]["sf"]) if star else set(l["e0"])
        tn = [j for j in sorted(e0) if truth[keys[j]]]
        X0 += bool(tn)
        e1 = []
        for j in tn:
            ch = l["chk"].get(str(j), {})
            if fam == "RQ1_excess_divergence":
                if ch.get("c", [None, True])[1]:      # a check missing from the line counts as support (upper bound)
                    e1.append(j)
            elif l["c"][j][2] == "g":
                if ch.get("b", [None, True])[1]:
                    e1.append(j)
            else:
                e1.append(j)                    # fallback contrasts: (a) and (b) do not apply and are not failures
        X1 += bool(e1)
        concl, need = [], []
        for j in e1:
            if fam != "RQ1_excess_divergence" and l["c"][j][2] == "g":
                ar = a_res.get((l["k"], keys[j]))
                if ar is None:
                    need.append(j)
                elif ar["supported"]:
                    concl.append(j)
            else:
                concl.append(j)
        if concl:
            Xr += 1
            if fam == "RQ1_excess_divergence":
                pos += any((l["c"][j][0] or 0) > 0 for j in concl)
                neg += any((l["c"][j][0] or 0) < 0 for j in concl)
        elif need:
            pend.append((l["k"], sorted({keys[j].split("|")[0] for j in need})))
    return {"n": len(lines), "E0": X0, "E1": X1, "rule_known": Xr, "pending": pend, "rq1_positive": pos, "rq1_negative": neg}


def verdict(st):
    """the acceptance decision of one configuration from its envelopes and the rule (an envelope that meets the
    criterion is sufficient; one that does not is inconclusive, and the omitted checks decide)"""
    if st["n"] == 0:
        return "undetermined", "no data set"
    T = pass_max(st["n"])
    if st["E0"] <= T:
        return "pass", "E0"
    if st["E1"] <= T:
        return "pass", "E1"
    lo, hi = st["rule_known"], st["rule_known"] + len(st["pending"])
    if hi <= T:
        return "pass", "rule"
    if lo > T:
        return "fail", "rule"
    return "undetermined", "rule"


def a_done(out_dir):
    done = {}
    for r in read_jsonl(Path(out_dir) / "C-CHECK-A.jsonl"):
        for kk, v in r["contrasts"].items():
            done[(r["fam"], r["cfg"], r["k"], kk)] = v
    return done


def c_checks(S, out_dir, fams, budget_s=CHECK_A_BUDGET_S, nb=N_BOOT_A, log=print):
    """C's check (a) phase, after the main phase: for each family and configuration whose verdict is undetermined, the
    pending data sets in a seeded order (seed 20261310), one at a time with all four cores (n1_glmm.R's own parallel
    refits), until the verdict is determined or the budget is spent; first the rule, then A* for the families where
    the rule does not pass. Results are appended to C-CHECK-A.jsonl (resumable; the budget counts earlier computing)."""
    out_dir = Path(out_dir)
    path = out_dir / "C-CHECK-A.jsonl"
    done = a_done(out_dir)
    spent0 = sum(r["seconds"] for r in read_jsonl(path))
    t_start = time.time()
    fh = open(path, "a", encoding="utf-8")
    stopped = []
    try:
        for star in (False, True):
            for fam in fams:
                if fam == "RQ1_excess_divergence":
                    continue
                cache = {cfg: load_c(out_dir, fam, cfg) for cfg in CONFIGS[fam]}

                def status(cfg, st_):
                    meta, lines = cache[cfg]
                    a_res = {(k, kk): v for (f_, c_, k, kk), v in done.items() if f_ == fam and c_ == cfg}
                    return classify(fam, meta["keys"], meta["truth"], lines, a_res, st_)
                if star and all(verdict(status(cfg, False))[0] == "pass" for cfg in CONFIGS[fam]):
                    continue
                for cfg in CONFIGS[fam]:
                    rng = np.random.default_rng(stream(SEEDS2["C_check_a_order"], FAM_ORDER.index(fam), CFG_INDEX[cfg], int(star)))
                    while True:
                        st = status(cfg, star)
                        if verdict(st)[0] != "undetermined" or not st["pending"]:
                            break
                        if spent0 + (time.time() - t_start) >= budget_s:
                            stopped.append({"fam": fam, "cfg": cfg, "A*": star, "pending": len(st["pending"])})
                            break
                        pend = sorted(st["pending"])
                        k, models = pend[int(rng.integers(0, len(pend)))]
                        r = check_a(S, fam, cfg, k, models, nb=nb)
                        fh.write(json.dumps(r) + "\n"); fh.flush(); os.fsync(fh.fileno())
                        for kk, vv in r["contrasts"].items():
                            done[(fam, cfg, k, kk)] = vv
                        log(f"[{time.strftime('%H:%M:%S', time.gmtime())} UTC] check (a) {fam} {cfg} k={k} {models}: {r['seconds']:.0f} s", flush=True)
    finally:
        fh.close()
    return {"spent_s": spent0 + (time.time() - t_start), "stopped_by_budget": stopped}


# ---------------------------------------------------------------------------------------------------- C: summary
def rates(keys, truth, lines, fam):
    """marginal rejection fractions per contrast (Holm within the family) of the registered test, test (a), test (b),
    the sign-flip test, E0, E0* (E0 and the sign-flip test) and, for true-null contrasts, E1"""
    n = len(lines)
    out = {}
    for j, kk in enumerate(keys):
        cnt = Counter()
        for l in lines:
            for t in ("reg", "me", "rz", "sf"):
                cnt[t] += j in l["rej"][t]
            if j in l["e0"]:
                cnt["E0"] += 1
                cnt["E0*"] += j in l["rej"]["sf"]
                if truth[kk]:
                    ch = l["chk"].get(str(j), {})
                    if fam == "RQ1_excess_divergence":
                        ok1 = ch.get("c", [None, True])[1]
                    elif l["c"][j][2] == "g":
                        ok1 = ch.get("b", [None, True])[1]
                    else:
                        ok1 = True
                    cnt["E1"] += bool(ok1)
        ts = ("reg", "me", "rz", "sf", "E0", "E0*") + (("E1",) if truth[kk] else ())
        out[kk] = {"true_null": bool(truth[kk]), **{t: {"x": int(cnt[t]), "rate": cnt[t] / n if n else None, "wilson": wilson(int(cnt[t]), n)} for t in ts}}
    return out


def fwer(lines, keys, truth, sets):
    x = sum(1 for l in lines if any(truth[keys[j]] for j in sets(l)))
    return {"x": x, "n": len(lines), "rate": x / len(lines) if lines else None, "wilson": wilson(x, len(lines))}


def c_summary(out_dir, fams):
    out_dir = Path(out_dir)
    done = a_done(out_dir)
    a_lines = read_jsonl(out_dir / "C-CHECK-A.jsonl")
    res = {"families": {}, "acceptance": {"criterion": "Wilson 95% lower limit of the family-wise false-conclusion rate <= .05",
                                          "pass_max": {}},
           "check_a": {"computations": len(a_lines), "seconds": sum(r["seconds"] for r in a_lines)}}
    for fam in fams:
        F = {"configs": {}}
        vr, vs_ = [], []
        for cfg in CONFIGS[fam]:
            meta, lines = load_c(out_dir, fam, cfg)
            keys, truth = meta["keys"], meta["truth"]
            a_res = {(k, kk): v for (f_, c_, k, kk), v in done.items() if f_ == fam and c_ == cfg}
            st, sts = classify(fam, keys, truth, lines, a_res, False), classify(fam, keys, truth, lines, a_res, True)
            v, how = verdict(st)
            vs, hows = verdict(sts)
            vr.append(v); vs_.append(vs)
            n = len(lines)
            res["acceptance"]["pass_max"][str(n)] = pass_max(n)
            fw = {t: fwer(lines, keys, truth, (lambda l, t=t: l["rej"][t])) for t in ("reg", "me", "rz", "sf")}
            fw["E0"] = fwer(lines, keys, truth, lambda l: l["e0"])
            fw["E0*"] = fwer(lines, keys, truth, lambda l: set(l["e0"]) & set(l["rej"]["sf"]))
            env = {"E0": {"x": st["E0"], "wilson": wilson(st["E0"], n)}, "E1": {"x": st["E1"], "wilson": wilson(st["E1"], n)},
                   "rule": {"known": st["rule_known"], "pending": len(st["pending"]),
                            "wilson": wilson(st["rule_known"], n) if not st["pending"] else None},
                   "E0*": {"x": sts["E0"], "wilson": wilson(sts["E0"], n)}, "E1*": {"x": sts["E1"], "wilson": wilson(sts["E1"], n)},
                   "rule*": {"known": sts["rule_known"], "pending": len(sts["pending"]),
                             "wilson": wilson(sts["rule_known"], n) if not sts["pending"] else None}}
            if fam == "RQ1_excess_divergence":
                env["rq1_positive_conclusion"] = {"x": st["rq1_positive"], "wilson": wilson(st["rq1_positive"], n)}
                env["rq1_negative_conclusion"] = {"x": st["rq1_negative"], "wilson": wilson(st["rq1_negative"], n)}
            mu = meta["meta"].get("expected_estimand")
            sign_err = None
            if mu and cfg not in COMPLETE:
                sign_err = sum(1 for l in lines if any((not truth[keys[j]]) and (l["c"][j][0] or 0) * mu[keys[j]] < 0 for j in l["e0"]))
            F["configs"][cfg] = {"n": n, "complete_null": cfg in COMPLETE, "true_nulls": sum(truth.values()), "contrasts": len(keys),
                                 "verdict": v, "decided_by": how, "verdict_A*": vs, "decided_by_A*": hows,
                                 "fwer_procedures": fw, "envelopes": env, "E0_wrong_sign_on_non_null": sign_err,
                                 "marginal": rates(keys, truth, lines, fam),
                                 "meta": {k_: v_ for k_, v_ in meta["meta"].items() if k_ not in ("expected_estimand",)}}
        F["rule_passes"] = all(v == "pass" for v in vr)
        F["A*_activated"] = not F["rule_passes"]
        F["A*_passes"] = all(v == "pass" for v in vs_) if F["A*_activated"] else None
        F["post_hoc_conclusions_withdrawn"] = F["A*_activated"] and not F["A*_passes"]
        res["families"][fam] = F
    t = read_jsonl(out_dir / "C-timing.jsonl")
    res["timing"] = {"tasks": len(t), "worker_s_by_family": {f: round(sum(x["total"] for x in t if x["fam"] == f), 1) for f in fams},
                     "check_b_items": sum(x["check_b_items"] for x in t), "job_errors": sum(len(x["job_errors"]) for x in t)}
    return res


def a_star_real(S, fams):
    """A* on the real data for the activated families: the sign-flip P of every contrast (seeds from 20261401), Holm
    within the family, and A*'s conclusion = record 54's stored conclusion of the rule and the sign-flip Holm rejection"""
    ns = S.ns
    PR = json.loads((S.root / "posthoc" / "POSTHOC-RESULTS.json").read_text(encoding="utf-8"))["posthoc"]["families"]
    out = {}
    for fam in fams:
        layer = D.fam_def(ns, fam)[0]
        rows = D.fam_rows(fam, S.base)
        cellv = D.fam_cells(ns, fam, rows)
        keys = D.keys_of(ns, fam)
        sf = {}
        for j, kk in enumerate(keys):
            m, con = kk.split("|")
            pq = D.per_query(ns, fam, cellv, S.frames[layer], m, *con.split("-"))
            if not _close(D.estimate_of(pq), PR[fam][kk]["estimate"]):
                raise SystemExit(f"A*: the estimate of {fam} {kk} differs from record 54")
            sf[kk] = signflip(pq, stream(SEEDS2["A_real"], FAM_ORDER.index(fam), j))
        h = D.holm_map(ns, {kk: sf[kk]["p"] for kk in keys})
        out[fam] = {kk: {"estimate": PR[fam][kk]["estimate"], "signflip_p": sf[kk]["p"], "signflip_test": sf[kk]["test"],
                         "signflip_p_holm": h[kk]["p_holm"], "signflip_reject": h[kk]["reject"],
                         "rule_conclusion_record54": bool(PR[fam][kk]["item4"]["conclusion"]),
                         "A*_conclusion": bool(PR[fam][kk]["item4"]["conclusion"]) and h[kk]["reject"]} for kk in keys}
    return out


# ---------------------------------------------------------------------------------------------------- D
class Frame:
    """records 47 and 50's resampling frame: fixed query IDs, multinomial counts (seed as declared), per-replicate mean
    over the resampled defined queries (NaN where none), 95% percentile interval over the defined replicates, no
    interval when fewer than two queries contribute"""
    def __init__(self, qids, seed, nb=10000):
        self.q = sorted(set(qids)); self.ix = {q: i for i, q in enumerate(self.q)}
        self.seed, self.nb = int(seed), nb
        n = len(self.q)
        self.C = np.random.default_rng(self.seed).multinomial(n, np.full(n, 1.0 / n), size=nb).astype(np.float64)

    def reps(self, per_q):
        v = np.zeros(len(self.q)); m = np.zeros(len(self.q))
        for q, x in per_q.items():
            v[self.ix[q]] = x; m[self.ix[q]] = 1.0
        num, den = self.C @ v, self.C @ m
        out = np.full(self.nb, np.nan)
        ok = den > 0
        out[ok] = num[ok] / den[ok]
        return out

    @staticmethod
    def ci(reps, n_query):
        d = reps[np.isfinite(reps)]
        if n_query < 2 or len(d) == 0:
            return None
        lo, hi = np.percentile(d, [2.5, 97.5])
        return [float(lo), float(hi)]

    def stat(self, per_q):
        reps = self.reps(per_q)
        return {"estimate": float(np.mean(list(per_q.values()))) if per_q else None, "n_query": len(per_q),
                "ci": self.ci(reps, len(per_q))}, reps

    def ratio(self, num_q, den_q):
        """answer-level rate sum(num) / sum(den), the answers of a query resampled together"""
        s, c = np.zeros(len(self.q)), np.zeros(len(self.q))
        for q in den_q:
            s[self.ix[q]] = num_q.get(q, 0.0); c[self.ix[q]] = den_q[q]
        num, den = self.C @ s, self.C @ c
        reps = np.full(self.nb, np.nan)
        ok = den > 0
        reps[ok] = num[ok] / den[ok]
        d = reps[np.isfinite(reps)]
        return {"estimate": float(s.sum() / c.sum()) if c.sum() else None, "n_answers": int(c.sum()), "n_query": int((c > 0).sum()),
                "ci": [float(x) for x in np.percentile(d, [2.5, 97.5])] if (len(d) and (c > 0).sum() >= 2) else None}

    def kappa(self, cells_q):
        """Cohen's kappa for two binary labels; cells_q: {query: [n11, n10, n01, n00]}"""
        M = np.zeros((len(self.q), 4))
        for q, v in cells_q.items():
            M[self.ix[q]] = v

        def kap(t):
            n = t.sum(axis=-1)
            with np.errstate(invalid="ignore", divide="ignore"):
                po = (t[..., 0] + t[..., 3]) / n
                pa, pb = (t[..., 0] + t[..., 1]) / n, (t[..., 0] + t[..., 2]) / n
                pe = pa * pb + (1 - pa) * (1 - pb)
                return np.where(pe < 1, (po - pe) / (1 - pe), np.nan)
        est = float(kap(M.sum(axis=0)))
        reps = kap(self.C @ M)
        d = reps[np.isfinite(reps)]
        return {"estimate": est, "ci": [float(x) for x in np.percentile(d, [2.5, 97.5])] if len(d) else None, "n_defined_replicates": int(len(d))}


def dice(a, b):
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    return 2 * len(a & b) / (len(a) + len(b))


def d_compute(S):
    """item D on the 303 triple-rated answers (label source consensus-3). Outcome scale (arms en, bn, bl; the consensus-
    defined primary set, as records 47 and 50): per answer, the rater's own label against the consensus of the other two,
    strict (primary: an entity counts when both other raters list it — the three-rater majority rule applied to two) and
    lenient (sensitivity: when either lists it); local share = local / (local + global) over the distinct classified
    brands (an answer undefined under either label set is left out of that comparison, and counted); price mention = a
    non-empty price set. Per rater, model and arm: per-query means over the query's answers, then the mean over queries
    of the rater's value, of the other two's and of their paired difference, with 95% percentile intervals from the
    10,000 resamples of records 47 and 50's frame (the 77 overlap query IDs, seed 20261021), the same resamples for both
    label sets; the six-model mean where all six are defined. Agreement on price labels (all 303 answers): pairwise and
    each rater against the other two (strict and lenient): price-mention agreement, Cohen's kappa (pairwise), identical
    price sets and the mean Dice coefficient of the price sets (1 when both are empty), each an answer-level rate with the
    answers of a query resampled together from the same frame."""
    ns = S.ns
    OV = load_overlap_defs(S.code_dir, S.root, ns)
    ext = OV["make_resolver"](OV["load_map"]("brand_aliases.expansion.csv", "alias_exclusions.expansion.csv"))
    E = {}
    for rt in RATERS:
        d = json.load(open(S.root / f"LABEL-EXPANSION-{rt}-labels.json", encoding="utf-8"))
        assert d["task"] == "N1 labelling expansion round" and d["rater"] == rt and not d.get("partial")
        E[rt] = {r["pid"]: r for r in d["labels"]}
    aset = [json.loads(l) for l in open(S.root / "EXPANSION-ANALYSIS-SET-v2.jsonl", encoding="utf-8")]
    ov = [r for r in aset if r["label_source"] == "consensus-3"]
    assert len(ov) == 303 and all(r["labelled_by"] == "R1+R2+R3" for r in ov)
    Hs = {rt: {r["pid"]: OV["human"](E[rt][r["pid"]], ext) for r in ov} for rt in RATERS}
    for r in ov:           # the identity of records 47 and 50: the raw exports reproduce the analysis set's consensus
        c = OV["consensus_of"]([Hs[rt][r["pid"]] for rt in RATERS])
        assert c["brands"] == r["brands"] and OV["price_list_from_serialised"](c["prices"]) == [list(p) for p in r["prices"]], r["pid"]
    share = OV["share_of"]
    frame_q = sorted({r["query_id"] for r in ov})
    assert S.synthetic or len(frame_q) == 77          # records 47 and 50's frame: the 77 overlap query IDs
    fr = Frame(frame_q, SEEDS2["D_frame"])
    elig = [r for r in ov if r["arm"] in ns["ARMS3"] and r["in_primary_set"]]
    res = {"answers": {"overlap": len(ov), "outcome_scale": len(elig), "by_arm": dict(Counter(r["arm"] for r in elig))},
           "frame": {"n_query": len(frame_q), "seed": SEEDS2["D_frame"], "resamples": fr.nb}, "outcome": {}, "agreement": {}}

    def ref_set(o1, o2, f, rule):
        a, b = set(o1[f]), set(o2[f])
        return (a & b) if rule == "strict" else (a | b)
    for rt in RATERS:
        o = [x for x in RATERS if x != rt]
        R = res["outcome"][rt] = {}
        for rule in ("strict", "lenient"):
            for oc in ("local_share", "price_mention"):
                vals, left_out, disagree = [], 0, 0
                for r in elig:
                    h, o1, o2 = Hs[rt][r["pid"]], Hs[o[0]][r["pid"]], Hs[o[1]][r["pid"]]
                    if oc == "local_share":
                        disagree += set(o1["brands"]) != set(o2["brands"])
                        x, y = share(h["brands_list"]), share(sorted(ref_set(o1, o2, "brands", rule)))
                        if x is None or y is None:
                            left_out += 1
                            continue
                    else:
                        disagree += (len(o1["prices"]) > 0) != (len(o2["prices"]) > 0)
                        x, y = int(len(h["prices"]) > 0), int(len(ref_set(o1, o2, "prices", rule)) > 0)
                    vals.append((r["model_id"], r["query_id"], r["arm"], x, y))
                cells = {}
                pooled = {a: {"rater": [], "others": [], "diff": [], "reps": {"rater": [], "others": [], "diff": []}, "nq": []} for a in ns["ARMS3"]}
                for m in ns["MODELS"]:
                    for a in ns["ARMS3"]:
                        cq = defaultdict(list)
                        for (mm, q, aa, x, y) in vals:
                            if mm == m and aa == a:
                                cq[q].append((x, y))
                        rq = {q: float(np.mean([v[0] for v in vs])) for q, vs in cq.items()}
                        oq = {q: float(np.mean([v[1] for v in vs])) for q, vs in cq.items()}
                        dq = {q: rq[q] - oq[q] for q in cq}
                        (sr, rr_), (so, ro), (sd, rd) = fr.stat(rq), fr.stat(oq), fr.stat(dq)
                        cells[f"{m}|{a}"] = {"n_query": len(cq), "n_answers": sum(len(v) for v in cq.values()), "rater": sr, "others": so,
                                             "discrepancy": sd}
                        P_ = pooled[a]
                        P_["rater"].append(sr["estimate"]); P_["others"].append(so["estimate"]); P_["diff"].append(sd["estimate"])
                        P_["reps"]["rater"].append(rr_); P_["reps"]["others"].append(ro); P_["reps"]["diff"].append(rd); P_["nq"].append(len(cq))
                six = {}
                for a, P_ in pooled.items():
                    six[a] = {}
                    for t in ("rater", "others", "diff"):
                        if any(p is None for p in P_[t]):
                            six[a][t] = {"estimate": None, "ci": None}
                            continue
                        reps = np.mean(np.vstack(P_["reps"][t]), axis=0)
                        d_ = reps[np.isfinite(reps)]
                        six[a][t] = {"estimate": float(np.mean(P_[t])),
                                     "ci": ([float(x) for x in np.percentile(d_, [2.5, 97.5])] if (len(d_) and min(P_["nq"]) >= 2) else None)}
                R[f"{oc}|{rule}"] = {"cells": cells, "six_model_mean": six, "answers_used": len(vals), "answers_left_out_undefined": left_out,
                                     "answers_where_the_other_two_disagree": disagree}

    def rate_items(pairs_):
        num, den = defaultdict(float), defaultdict(float)
        for q, v in pairs_:
            num[q] += v; den[q] += 1
        return fr.ratio(num, den)
    A = res["agreement"]
    for x, y in (("R1", "R2"), ("R1", "R3"), ("R2", "R3")):
        pm, ps, pdc, cells = [], [], [], defaultdict(lambda: [0, 0, 0, 0])
        for r in ov:
            hx, hy, q = Hs[x][r["pid"]], Hs[y][r["pid"]], r["query_id"]
            mx, my = len(hx["prices"]) > 0, len(hy["prices"]) > 0
            pm.append((q, float(mx == my))); ps.append((q, float(set(hx["prices"]) == set(hy["prices"]))))
            pdc.append((q, dice(hx["prices"], hy["prices"])))
            cells[q][0 if (mx and my) else 1 if mx else 2 if my else 3] += 1
        A[f"{x}-{y}"] = {"price_mention_agreement": rate_items(pm), "price_mention_kappa": fr.kappa(cells),
                         "price_sets_identical": rate_items(ps), "price_set_dice": rate_items(pdc)}
    for rt in RATERS:
        o = [x for x in RATERS if x != rt]
        for rule in ("strict", "lenient"):
            pm, ps, pdc = [], [], []
            for r in ov:
                h, o1, o2, q = Hs[rt][r["pid"]], Hs[o[0]][r["pid"]], Hs[o[1]][r["pid"]], r["query_id"]
                ref = ref_set(o1, o2, "prices", rule)
                pm.append((q, float((len(h["prices"]) > 0) == (len(ref) > 0))))
                ps.append((q, float(set(h["prices"]) == ref))); pdc.append((q, dice(h["prices"], ref)))
            A[f"{rt}-vs-other-two|{rule}"] = {"price_mention_agreement": rate_items(pm), "price_sets_identical": rate_items(ps),
                                               "price_set_dice": rate_items(pdc)}
    return res


# ---------------------------------------------------------------------------------------------------- E
def e_specs(S):
    """the E generators: refusal — per model, the raised arm (bn serves bn-en and bn-bl, bl serves bl-en); F.10 local
    share — per model and contrast; F.10 excess divergence — per model, serving both bl_translit contrasts"""
    ns = S.ns
    specs = []
    for m in ns["MODELS"]:
        specs.append({"part": "refusal", "layer": "corpus", "model": m, "shift": "bn", "cons": [("bn", "en"), ("bn", "bl")], "grid": "refusal"})
        specs.append({"part": "refusal", "layer": "corpus", "model": m, "shift": "bl", "cons": [("bl", "en")], "grid": "refusal"})
    for lay in ("human", "machine"):
        if lay not in S.f10rows:
            continue
        for m in ns["MODELS"]:
            for a, b in C10:
                specs.append({"part": f"f10_share_{lay}", "layer": lay, "model": m, "shift": a, "cons": [(a, b)], "grid": "share"})
            specs.append({"part": f"f10_delta_{lay}", "layer": lay, "model": m, "shift": "bl_translit", "cons": list(C10), "grid": "delta"})
    for i, s in enumerate(specs):
        s["index"] = i
    return specs


def mmd2(P, Q, J):
    """D^2 = E J(A,A') + E J(B,B') - 2 E J(A,B) for independent draws with replacement from two lists of sets"""
    return float(np.mean([J(x, y) for x in P for y in P]) + np.mean([J(x, y) for x in Q for y in Q]) - 2 * np.mean([J(x, y) for x in P for y in Q]))


class EGen:
    """refusal: each answer (the model's refusal-family analysis rows) is a refusal with its query's pooled refusal
    proportion over the three arms; the raised arm's is min(1, b_q + delta). F.10 local share: the query's pooled local
    share over the three F.10 arms; mentions beta-binomial with the model's intra-answer correlation; the contrast's first
    arm min(1, b_q + delta/2), bl_translit max(0, b_q - delta/2). F.10 excess divergence: the query's pooled brand sets
    over the three F.10 arms drawn with replacement; each bl_translit answer drawn with probability theta from the pooled
    sets of the model's other F.10 queries of the same category (all its other F.10 queries when the category has none).
    Estimand under an alternative: the mean over the contrast's eligible queries of the expected paired difference
    (refusal, share), and theta^2 x the mean of D^2/2 (divergence), D^2 the Jaccard-kernel distance of the two pools."""
    def __init__(self, S, spec):
        self.S, self.spec = S, spec
        ns = S.ns
        m, part = spec["model"], spec["part"]
        self.x_arm = spec["shift"]
        if part == "refusal":
            self.rows = [r for r in S.base["refusal"] if r["model"] == m]
            self.an = [True] * len(self.rows)
            self.fam, self.frame = "RQ5_refusal", S.frames["corpus"]
            pool = defaultdict(lambda: [0, 0])
            for r in self.rows:
                pool[r["query"]][0] += int(r["outcome"] == "refusal"); pool[r["query"]][1] += 1
            self.b = {q: v[0] / v[1] for q, v in pool.items()}
        else:
            lay = spec["layer"]
            self.rows = [r for r in S.f10rows[lay] if r["model"] == m]
            self.frame = sorted(S.f10q[lay])
            self.an = [r["arm"] in F10_ARMS and ns["P"](r) for r in self.rows]
            if part.startswith("f10_share"):
                self.fam = "RQ2_local_share"
                self.units = [fam_units(ns, self.fam, r) if a_ else (0, 0) for r, a_ in zip(self.rows, self.an)]
                pool, cell = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
                for r, a_, (x, n) in zip(self.rows, self.an, self.units):
                    if a_:
                        pool[r["query"]][0] += x; pool[r["query"]][1] += n
                        cell[(r["query"], r["arm"])][0] += x; cell[(r["query"], r["arm"])][1] += n
                self.b = {q: (v[0] / v[1] if v[1] else 0.0) for q, v in pool.items()}
                pc = {k: (v[0] / v[1] if v[1] else 0.0) for k, v in cell.items()}
                self.rho = rho_of([(x, n, pc[(r["query"], r["arm"])]) for r, a_, (x, n) in zip(self.rows, self.an, self.units) if a_])
            else:
                self.fam = "RQ1_excess_divergence"
                pool = defaultdict(list)
                for r, a_ in zip(self.rows, self.an):
                    if a_:
                        pool[r["query"]].append(tuple(r["brands"]))
                self.pool = pool
                self.other = {}
                for q in pool:
                    oth = [s for q2, ss in pool.items() if q2 != q and S.CAT[q2] == S.CAT[q] for s in ss]
                    self.other[q] = oth or [s for q2, ss in pool.items() if q2 != q for s in ss]
        self._elig = {}

    def elig(self, con):
        if con not in self._elig:
            a, b = con
            ns = self.S.ns
            if self.spec["part"] == "refusal":
                cellv = D.fam_cells(ns, "RQ5_refusal", self.rows)
                self._elig[con] = sorted(D.per_query(ns, "RQ5_refusal", cellv, self.frame, self.spec["model"], a, b))
            elif self.spec["part"].startswith("f10_share"):
                defined = defaultdict(int)
                for r, a_, (x, n) in zip(self.rows, self.an, self.units):
                    if a_ and n:
                        defined[(r["query"], r["arm"])] += 1
                self._elig[con] = sorted(q for q in self.frame if defined.get((q, a)) and defined.get((q, b)))
            else:
                cnt = Counter((r["query"], r["arm"]) for r, a_ in zip(self.rows, self.an) if a_)
                self._elig[con] = sorted(q for q in self.frame if cnt.get((q, a), 0) >= 2 and cnt.get((q, b), 0) >= 2)
        return self._elig[con]

    def effect(self, e, con):
        el = self.elig(con)
        if not el:
            return None
        part = self.spec["part"]
        if part == "refusal":
            return float(np.mean([min(1.0, self.b[q] + e) - self.b[q] for q in el]))
        if part.startswith("f10_share"):
            return float(np.mean([min(1.0, self.b[q] + e / 2) - max(0.0, self.b[q] - e / 2) for q in el]))
        J = self.S.ns["jaccard"]
        if not hasattr(self, "_d2"):
            self._d2 = {q: 0.5 * mmd2(self.other[q], self.pool[q], J) for q in self.pool}
        return float(e * e * np.mean([self._d2[q] for q in el]))

    def draw(self, rng, e):
        ns = self.S.ns
        part = self.spec["part"]
        if part == "refusal":
            return [with_outcome(ns, "RQ5_refusal", r, int(rng.random() < min(1.0, self.b[r["query"]] + (e if r["arm"] == self.x_arm else 0.0))), 1)
                    for r in self.rows]
        out = []
        if part.startswith("f10_share"):
            for r, a_, (_, n) in zip(self.rows, self.an, self.units):
                if not a_:
                    out.append(r); continue
                p = self.b[r["query"]]
                p = min(1.0, p + e / 2) if r["arm"] == self.x_arm else (max(0.0, p - e / 2) if r["arm"] == "bl_translit" else p)
                out.append(with_outcome(ns, "RQ2_local_share", r, draw_units(rng, n, p, self.rho), n))
            return out
        for r, a_ in zip(self.rows, self.an):
            if not a_:
                out.append(r); continue
            src = self.other[r["query"]] if (r["arm"] == "bl_translit" and e > 0 and rng.random() < e) else self.pool[r["query"]]
            out.append(dict(r, brands=list(src[int(rng.integers(0, len(src)))])))
        return out


def e_fn(S, spec):
    ns = S.ns
    part = spec["part"]
    if part == "refusal":
        return registered_fn(ns, "RQ5_refusal", S.b0s["corpus"])
    b0 = S.b0_f10[spec["layer"]]
    if part.startswith("f10_share"):
        return lambda rows: ns["share_outcome"](rows, {"items": ns["brand_items"]()}, F10_ARMS, C10, ns["P"], b0, "post-hoc E", None, "query")
    return lambda rows: ns["setdiv"](rows, "brands", ns["jaccard"], C10, ns["P"], b0, "post-hoc E")


def e_read(spec, rr):
    m = spec["model"]
    out = []
    for a, b in spec["cons"]:
        if spec["part"].startswith("f10_delta"):
            x = rr["results"][f"{m}|{a}-{b}"]
            p = x.get("test", {}).get("p", 1.0) if x.get("n_query") else 1.0
            out.append([g8(1.0 if p is None else p), g8(x.get("mean_delta")), "w" if x.get("n_query") else "n"])
        else:
            c = rr["results"][m]["contrasts"][f"{a}-{b}"]
            p = c["test"]["p"]
            out.append([g8(1.0 if p is None else p), g8(c.get("diff")), "g" if c["test"]["method"] == "glmm_wald" else "f"])
    return out


def e_task(si, gi, reps):
    S = G["S"]
    spec, gen = G["especs"][si], G["egens"][si]
    e = E_GRID[spec["grid"]][gi]
    t0 = time.time()
    ds = [gen.draw(np.random.default_rng(stream(SEEDS2["E"][spec["part"]], spec["index"], gi, rep)), e) for rep in reps]
    t1 = time.time()
    errors = []
    m = spec["model"]
    res = batched(S.ns, e_fn(S, spec), ds, keep=lambda _k, jid: jid == m, errors=errors)
    t2 = time.time()
    lines = [{"s": si, "g": gi, "r": rep, "c": e_read(spec, rr)} for rep, rr in zip(reps, res)]
    return lines, {"s": si, "g": gi, "part": spec["part"], "n": len(reps), "generate": t1 - t0, "registered": t2 - t1,
                   "worker": G.get("wid"), "job_errors": errors}


def e_run(S, out_dir, workers, tmp_root, n_rep=None, parts=None, grid_points=None):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    specs = e_specs(S)
    gens = [EGen(S, s) for s in specs]
    G["S"], G["especs"], G["egens"] = S, specs, gens
    path = out_dir / "E-POWER.jsonl"
    have = {(l["s"], l["g"], l["r"]) for l in read_jsonl(path)}
    tasks = []
    for s in specs:
        if parts and s["part"] not in parts:
            continue
        for gi in range(len(E_GRID[s["grid"]])):
            if grid_points is not None and gi not in grid_points:
                continue
            todo = [r for r in range(n_rep or N_REP_E[s["part"]]) if (s["index"], gi, r) not in have]
            for i in range(0, len(todo), E_BATCH):
                tasks.append((s["index"], gi, todo[i:i + E_BATCH]))
    fh = open(path, "a", encoding="utf-8")
    tlog = open(out_dir / "E-timing.jsonl", "a", encoding="utf-8")

    def sink(res):
        lines, tm = res
        fh.write("".join(json.dumps(l, separators=(",", ":")) + "\n" for l in lines)); fh.flush(); os.fsync(fh.fileno())
        tlog.write(json.dumps(tm) + "\n"); tlog.flush()
    try:
        el = run_pool(tasks, e_task, workers, tmp_root, sink) if tasks else 0.0
    finally:
        fh.close(); tlog.close()
    return el, len(tasks)


def isotonic(y, w):
    """pool-adjacent-violators fit, non-decreasing"""
    out = []
    for yy, ww in zip(y, w):
        out.append([yy, ww, 1])
        while len(out) > 1 and out[-2][0] > out[-1][0]:
            y2, w2, n2 = out.pop(); y1, w1, n1 = out.pop()
            out.append([(y1 * w1 + y2 * w2) / (w1 + w2), w1 + w2, n1 + n2])
    res = []
    for yy, _, nn in out:
        res += [yy] * nn
    return res


def e_summary(S, lines):
    """per contrast: detections (registered P at most the contrast's threshold and the estimate on the side of the
    alternative) at each grid value with a Wilson interval; the isotonic (non-decreasing) fit of power over the grid;
    the smallest effect with 80% power = linear interpolation of the isotonic fit on the estimand scale between the two
    grid values that bracket 80%"""
    specs = e_specs(S)
    gens = [EGen(S, s) for s in specs]
    by = defaultdict(list)
    for l in lines:
        by[(l["s"], l["g"])].append(l)
    out = []
    for s, g in zip(specs, gens):
        grid = E_GRID[s["grid"]]
        alpha = E_ALPHA["refusal" if s["part"] == "refusal" else "f10"]
        for ci_, con in enumerate(s["cons"]):
            rows = []
            for gi, e in enumerate(grid):
                ls = {l["r"]: l for l in by[(s["index"], gi)]}
                ls = [ls[r] for r in sorted(ls)]
                n = len(ls)
                det = sum(1 for l in ls if l["c"][ci_][0] <= alpha and (l["c"][ci_][1] or 0) > 0)
                rows.append({"nominal": e, "effect": g.effect(e, con), "n": n, "detected": det, "power": det / n if n else None,
                             "wilson": wilson(det, n) if n else None, "rejected_any_sign": sum(1 for l in ls if l["c"][ci_][0] <= alpha),
                             "methods": dict(Counter(l["c"][ci_][2] for l in ls))})
            iso = isotonic([r["power"] or 0.0 for r in rows], [max(1, r["n"]) for r in rows])
            mde = None
            for i in range(1, len(rows)):
                if iso[i] >= E_POWER > iso[i - 1]:
                    e0, e1 = rows[i - 1]["effect"], rows[i]["effect"]
                    t = (E_POWER - iso[i - 1]) / (iso[i] - iso[i - 1])
                    mde = {"effect": e0 + t * (e1 - e0), "bracket": [e0, e1], "nominal_bracket": [grid[i - 1], grid[i]]}
                    break
            if mde is None:
                mde = {"effect": None, "note": ("80% power at the null grid value" if iso and iso[0] >= E_POWER
                                                else f"power below 80% at the largest grid value (effect {rows[-1]['effect']})")}
            out.append({"part": s["part"], "layer": s["layer"], "model": s["model"], "contrast": f"{con[0]}-{con[1]}", "shifted_arm": s["shift"],
                        "alpha": alpha, "n_eligible_queries": len(g.elig(con)),
                        "n_answers": sum(1 for r, a_ in zip(g.rows, g.an) if a_ and r["arm"] in con),
                        "grid": rows, "isotonic_power": iso, "mde": mde, **({"rho": g.rho} if hasattr(g, "rho") else {})})
    return out


def cp_upper(k, n, conf):
    from scipy.stats import beta
    if n == 0:
        return None
    return 1.0 if k >= n else float(beta.ppf(conf, k + 1, n - k))


def e_bounds(S):
    """one-sided upper bounds for the refusal cells (model x arm; the refusal family's analysis rows). Estimand: the
    query-level refusal rate (the mean over queries of the per-query refusal proportion); sampling unit: the query.
    Cluster-aware bound: each query's proportion is at most 1 if the query has a refusal and 0 otherwise, so the rate is
    at most the share of queries with any refusal; the exact one-sided 95% Clopper-Pearson upper limit of that share, from
    the number of such queries among the queries with an answer, bounds the rate (for queries drawn independently; by
    Hoeffding's inequality also for fixed queries with independent answers). Benchmark only: the answer-level Clopper-
    Pearson limit (assumes independent answers). A contrast's absolute difference is at most the larger of its two rates:
    bounded by the larger of the two cells' one-sided 97.5% query-level limits (Bonferroni over the two cells)."""
    ns = S.ns
    cells = {}
    for m in ns["MODELS"]:
        for a in ns["ARMS3"]:
            byq = defaultdict(list)
            for r in S.base["refusal"]:
                if r["model"] == m and r["arm"] == a:
                    byq[r["query"]].append(int(r["outcome"] == "refusal"))
            kq = sum(1 for v in byq.values() if sum(v))
            x = sum(sum(v) for v in byq.values()); n = sum(len(v) for v in byq.values())
            cells[(m, a)] = {"model": m, "arm": a, "answers": n, "refusals": x, "queries": len(byq), "queries_with_refusal": kq,
                             "query_level_rate": float(np.mean([np.mean(v) for v in byq.values()])) if byq else None,
                             "upper95_query_level": cp_upper(kq, len(byq), BOUND_CONF),
                             "upper975_query_level": cp_upper(kq, len(byq), 1 - (1 - BOUND_CONF) / 2),
                             "upper95_answer_level_benchmark": cp_upper(x, n, BOUND_CONF),
                             "class": "zero-event" if x == 0 else ("near-zero" if x <= NEAR_ZERO_MAX else "other")}
    cons = [{"model": m, "contrast": f"{a}-{b}", "cells": [cells[(m, a)]["class"], cells[(m, b)]["class"]],
             "upper95_abs_difference": max(cells[(m, a)]["upper975_query_level"], cells[(m, b)]["upper975_query_level"])}
            for m in ns["MODELS"] for a, b in ns["C3"]]
    return {"cells": list(cells.values()), "contrasts": cons}


# ---------------------------------------------------------------------------------------------------- reproduction
def _close(x, y, tol=1e-12):
    if x is None or y is None:
        return x is None and y is None
    return abs(float(x) - float(y)) <= tol * max(1.0, abs(float(y)))


def reproduce2(S, R):
    """before any new value: record 53's reproduction (96 estimates, run-of-record intervals, registered P values and
    Holm decisions, check (c)); record 54's stored P values of tests (a) and (b); the stored F.10 results (estimates and
    P values, human and machine layers, through the batched bridge); records 47 and 50's stored overlap levels"""
    ns = S.ns
    out = {"record53": D.reproduce(S, R)}
    has54 = (S.root / "posthoc" / "POSTHOC-RESULTS.json").exists()
    has50 = (S.root / "exploratory" / "OVERLAP-RATER-VS-CONSENSUS.json").exists()
    if not S.synthetic and not (has54 and has50):
        raise SystemExit("record 54's and record 50's stored outputs are required on real data")
    PR = json.loads((S.root / "posthoc" / "POSTHOC-RESULTS.json").read_text(encoding="utf-8"))["posthoc"]["families"] if has54 else None
    mism, n = [], 0
    for fam in (FAM_ORDER if has54 else []):
        layer = D.fam_def(ns, fam)[0]
        rows = D.fam_rows(fam, S.base)
        cellv = D.fam_cells(ns, fam, rows)
        pqs = {kk: D.per_query(ns, fam, cellv, S.frames[layer], kk.split("|")[0], *kk.split("|")[1].split("-")) for kk in D.keys_of(ns, fam)}
        est = {kk: D.estimate_of(v) for kk, v in pqs.items()}
        rz = D.randomization_family(ns, fam, cellv, S.frames[layer], D.SEEDS["rand"][fam], D.N_RAND, est)
        for kk, pq in pqs.items():
            me = D.mean_effect(pq, S.sbs[layer])
            n += 1
            if me["p"] != PR[fam][kk]["mean_effect"]["p"] or rz[kk]["p"] != PR[fam][kk]["randomization"]["p"]:
                mism.append({"key": f"{fam}|{kk}", "me": [me["p"], PR[fam][kk]["mean_effect"]["p"]], "rz": [rz[kk]["p"], PR[fam][kk]["randomization"]["p"]]})
    out["record54_tests"] = {"checked": n, "mismatch": mism}
    f10 = {"checked": 0, "mismatch": [], "max_rel_diff_glmm": 0.0}
    for lay, sk, dk in (("human", "F10_RQ2", "F10_RQ1"), ("machine", "F10_RQ2_machine", "F10_RQ1_machine")):
        rows = S.f10rows[lay]
        b0 = S.b0_f10[lay]
        rs = batched(ns, lambda rw: ns["share_outcome"](rw, {"items": ns["brand_items"]()}, F10_ARMS, C10, ns["P"], b0, "F.10"), [rows])[0]
        rd = ns["setdiv"](rows, "brands", ns["jaccard"], C10, ns["P"], b0, "F.10")
        for m in ns["MODELS"]:
            for a, b in C10:
                c, st = rs["results"][m]["contrasts"][f"{a}-{b}"], R["secondary"][sk]["results"][m]["contrasts"][f"{a}-{b}"]
                f10["checked"] += 1
                pd_, ps_ = float(c["test"]["p"] if c["test"]["p"] is not None else 1), float(st["test"]["p"] if st["test"]["p"] is not None else 1)
                d_ = abs(pd_ - ps_)
                if c["test"]["method"] == "glmm_wald" and d_ > 0:
                    f10["max_rel_diff_glmm"] = max(f10["max_rel_diff_glmm"], d_ / max(abs(pd_), abs(ps_), 1e-300))
                bad = c["test"]["method"] != st["test"]["method"] or not _close(c.get("diff"), st.get("diff")) or \
                    ((d_ > 0.02 * max(abs(pd_), abs(ps_)) and d_ > 1e-9) if c["test"]["method"] == "glmm_wald" else d_ > 1e-12)
                if bad:
                    f10["mismatch"].append({"key": f"{sk}|{m}|{a}-{b}", "driver": [c["test"]["method"], c.get("diff"), c["test"]["p"]],
                                            "stored": [st["test"]["method"], st.get("diff"), st["test"]["p"]]})
                x, sx = rd["results"][f"{m}|{a}-{b}"], R["secondary"][dk]["results"][f"{m}|{a}-{b}"]
                f10["checked"] += 1
                if x.get("n_query", 0) != sx.get("n_query", 0) or (x.get("n_query") and not (_close(x["mean_delta"], sx["mean_delta"])
                                                                                           and _close(x["test"]["p"], sx["test"]["p"]))):
                    f10["mismatch"].append({"key": f"{dk}|{m}|{a}-{b}", "driver": [x.get("n_query"), x.get("mean_delta")],
                                            "stored": [sx.get("n_query"), sx.get("mean_delta")]})
    out["f10"] = f10
    ovm = {"checked": 0, "mismatch": []}
    out["overlap_record50"] = ovm
    if not has50:
        out["ok"] = bool(out["record53"]["ok"] and not mism and not f10["mismatch"])
        out["skipped_in_synthetic_mode"] = ["record54_tests" if not has54 else None, "overlap_record50"]
        return out
    # records 47 and 50: the stored per-rater and consensus levels (estimates, query counts, intervals) recomputed
    OV = load_overlap_defs(S.code_dir, S.root, ns)
    ext = OV["make_resolver"](OV["load_map"]("brand_aliases.expansion.csv", "alias_exclusions.expansion.csv"))
    E = {rt: {r["pid"]: r for r in json.load(open(S.root / f"LABEL-EXPANSION-{rt}-labels.json", encoding="utf-8"))["labels"]} for rt in RATERS}
    aset = [json.loads(l) for l in open(S.root / "EXPANSION-ANALYSIS-SET-v2.jsonl", encoding="utf-8")]
    ov = [r for r in aset if r["label_source"] == "consensus-3"]
    fr = Frame(sorted({r["query_id"] for r in ov}), SEEDS2["D_frame"])
    stored = json.loads((S.root / "exploratory" / "OVERLAP-RATER-VS-CONSENSUS.json").read_text(encoding="utf-8"))["results"]["levels"]
    per = []
    for r in ov:
        if r["arm"] not in ns["ARMS3"] or not r["in_primary_set"]:
            continue
        e = {"model": r["model_id"], "query": r["query_id"], "arm": r["arm"], "share": {"consensus": OV["share_of"](r["brands"])},
             "price": {"consensus": int(len(r["prices"]) > 0)}}
        for rt in RATERS:
            h = OV["human"](E[rt][r["pid"]], ext)
            e["share"][rt] = OV["share_of"](h["brands_list"]); e["price"][rt] = int(len(h["prices"]) > 0)
        per.append(e)
    for oc in ("share", "price"):
        for ver in ("consensus",) + RATERS:
            for m in ns["MODELS"]:
                for a in ns["ARMS3"]:
                    d_ = defaultdict(list)
                    for e in per:
                        if e["model"] == m and e["arm"] == a and e[oc][ver] is not None:
                            d_[e["query"]].append(e[oc][ver])
                    st_, _ = fr.stat({q: float(np.mean(v)) for q, v in d_.items()})
                    sv = stored[oc][ver]["models"][m][a]
                    ovm["checked"] += 1
                    same_ci = (st_["ci"] is None and sv.get("ci") is None) or (st_["ci"] is not None and sv.get("ci") is not None
                                                                              and _close(st_["ci"][0], sv["ci"][0]) and _close(st_["ci"][1], sv["ci"][1]))
                    if not (_close(st_["estimate"], sv.get("estimate")) and st_["n_query"] == sv.get("n_query") and same_ci):
                        ovm["mismatch"].append({"key": f"{oc}|{ver}|{m}|{a}", "driver": st_, "stored": sv})
    out["ok"] = bool(out["record53"]["ok"] and not mism and not f10["mismatch"] and not ovm["mismatch"])
    return out


# ---------------------------------------------------------------------------------------------------- rendering
def fp(x, nd=4):
    return "–" if x is None else f"{x:.{nd}f}"


def esc(x):
    """a Markdown table cell: | escaped"""
    return str(x).replace("|", "\\|")


def fw_s(w):
    return f"{w['x']}/{w['n']} = {fp(w['rate'])} [{fp(w['wilson'][0])}, {fp(w['wilson'][1])}]"


def ci_s(s):
    return f"{fp(s['estimate'])} [{fp(s['ci'][0]) if s.get('ci') else '–'}, {fp(s['ci'][1]) if s.get('ci') else '–'}]"


def render_c(res):
    L = ["# N1 — item C: calibration of record 53's interpretation rule for the zero-mean hypotheses (post-hoc; outside the results of record)", "",
         f"Driver sha256 {DRIVER_SHA}. Acceptance: {res['acceptance']['criterion']}; pass iff at most pass_max of n data sets have a "
         "false conclusion (" + ", ".join(f"n = {n}: {x}" for n, x in sorted(res["acceptance"]["pass_max"].items(), key=lambda t: int(t[0]))) + ").",
         "FWER rows: data sets with at least one Holm rejection (or conclusion) on a true-null contrast; x/n = rate [Wilson 95%].", ""]
    for fam, F in res["families"].items():
        L += [f"## {fam}", "",
              f"Rule passes in every configuration: **{F['rule_passes']}**; A* activated: {F['A*_activated']}; A* passes: {F['A*_passes']}; "
              f"post-hoc conclusions withdrawn: {F['post_hoc_conclusions_withdrawn']}.", "",
              "| configuration | null | n | true nulls | registered | mean-effect (a) | randomization (b) | sign-flip | E0 | E1 | rule | verdict (by) | A*: E0* | A* verdict (by) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for cfg, C in F["configs"].items():
            f_, e_ = C["fwer_procedures"], C["envelopes"]
            rule = f"{e_['rule']['known']} known + {e_['rule']['pending']} pending"
            L.append(f"| {cfg} | {'complete' if C['complete_null'] else 'partial'} | {C['n']} | {C['true_nulls']}/{C['contrasts']} | {fw_s(f_['reg'])} | "
                     f"{fw_s(f_['me'])} | {fw_s(f_['rz'])} | {fw_s(f_['sf'])} | {fw_s(f_['E0'])} | {e_['E1']['x']} [{fp(e_['E1']['wilson'][0])}, "
                     f"{fp(e_['E1']['wilson'][1])}] | {rule} | {C['verdict']} ({C['decided_by']}) | {fw_s(f_['E0*'])} | {C['verdict_A*']} ({C['decided_by_A*']}) |")
        if fam == "RQ1_excess_divergence":
            L.append("")
            for cfg, C in F["configs"].items():
                e_ = C["envelopes"]
                p_, n_ = e_["rq1_positive_conclusion"], e_["rq1_negative_conclusion"]
                L.append(f"- {cfg}: data sets with a positive-Δ conclusion on a true null {p_['x']}/{C['n']} [{fp(p_['wilson'][0])}, {fp(p_['wilson'][1])}]; "
                         f"negative-Δ {n_['x']}/{C['n']} [{fp(n_['wilson'][0])}, {fp(n_['wilson'][1])}]")
        L += ["", "Marginal rejection fractions per contrast (Holm within the family; * = true null):"]
        for cfg, C in F["configs"].items():
            parts = [f"{kk}{'*' if v['true_null'] else ''} reg {fp(v['reg']['rate'], 3)}, me {fp(v['me']['rate'], 3)}, rz {fp(v['rz']['rate'], 3)}, "
                     f"sf {fp(v['sf']['rate'], 3)}, E0 {fp(v['E0']['rate'], 3)}" + (f", E1 {fp(v['E1']['rate'], 3)}" if "E1" in v else "")
                     for kk, v in C["marginal"].items()]
            L.append(f"- {cfg}: " + "; ".join(parts))
        L.append("")
    if res.get("A*_real"):
        L += ["## A* on the real data (activated families)", "",
              "| family | contrast | estimate | sign-flip P | Holm P | sign-flip rejects | rule's conclusion (record 54) | A* conclusion |",
              "|---|---|---|---|---|---|---|---|"]
        for fam, X in res["A*_real"].items():
            for kk, v in X.items():
                L.append(f"| {fam} | {esc(kk)} | {fp(v['estimate'])} | {fp(v['signflip_p'], 5)} | {fp(v['signflip_p_holm'], 5)} | {v['signflip_reject']} | "
                         f"{v['rule_conclusion_record54']} | {v['A*_conclusion']} |")
        L.append("")
    L.append(f"Check (a) computations: {res['check_a']['computations']} ({res['check_a']['seconds']:.0f} s). Timing: {json.dumps(res['timing'])}")
    return "\n".join(L) + "\n"


def render_d(res):
    L = ["# N1 — item D: each rater against the consensus of the other two on the 303 triple-rated answers (descriptive; outside the results of record)", "",
         f"Driver sha256 {DRIVER_SHA}. Outcome scale: {res['answers']['outcome_scale']} answers in arms en, bn, bl (consensus-defined primary set); "
         f"frame: the {res['frame']['n_query']} overlap query IDs, {res['frame']['resamples']} resamples, seed {res['frame']['seed']} (records 47 and 50). "
         "Values are proportions; discrepancy = the rater's value minus the other two's; [95% percentile interval]; n = contributing queries / answers.", ""]
    for rt, R in res["outcome"].items():
        for key, X in R.items():
            oc, rule = key.split("|")
            L += [f"## {rt} — {oc.replace('_', ' ')} — the other two, {rule} ({X['answers_used']} answers used; {X['answers_left_out_undefined']} left out "
                  f"as undefined; the other two disagree on {X['answers_where_the_other_two_disagree']})", "",
                  "| model | arm | n (queries / answers) | rater | other two | discrepancy |", "|---|---|---|---|---|---|"]
            for c, v in X["cells"].items():
                m, a = c.split("|")
                L.append(f"| {m} | {a} | {v['n_query']} / {v['n_answers']} | {ci_s(v['rater'])} | {ci_s(v['others'])} | {ci_s(v['discrepancy'])} |")
            for a, v in X["six_model_mean"].items():
                L.append(f"| six-model mean | {a} | – | {ci_s(v['rater'])} | {ci_s(v['others'])} | {ci_s(v['diff'])} |")
            L.append("")
    L += ["## Agreement on price labels (all 303 overlap answers; answer-level rates, the answers of a query resampled together)", "",
          "| comparison | price-mention agreement | kappa | identical price sets | mean Dice of price sets |", "|---|---|---|---|---|"]
    for k, v in res["agreement"].items():
        L.append(f"| {esc(k)} | {ci_s(v['price_mention_agreement'])} | {ci_s(v['price_mention_kappa']) if 'price_mention_kappa' in v else '–'} | "
                 f"{ci_s(v['price_sets_identical'])} | {ci_s(v['price_set_dice'])} |")
    return "\n".join(L) + "\n"


def render_e(power, bounds, meta):
    L = ["# N1 — item E: detection limits and upper bounds (planning; outside the results of record)", "", f"Driver sha256 {DRIVER_SHA}. {meta}", "",
         "## Smallest effect detected with 80% power (the registered test; declared alternatives; a simulation approximation)", "",
         "| part | model | contrast | alpha | eligible queries | answers | MDE (estimand scale) | bracket (nominal) | power at the largest grid value |",
         "|---|---|---|---|---|---|---|---|---|"]
    for x in power:
        md = x["mde"]
        L.append(f"| {x['part']} | {x['model']} | {x['contrast']} | {x['alpha']:.5f} | {x['n_eligible_queries']} | {x['n_answers']} | "
                 f"{fp(md.get('effect'))} | {md.get('nominal_bracket', md.get('note', ''))} | {fp(x['grid'][-1]['power'], 3)} |")
    L += ["", "## Refusal cells: one-sided upper bounds (estimand: the query-level refusal rate; unit: the query; 95%)", "",
          "| model | arm | answers | refusals | queries | queries with a refusal | query-level rate | upper 95% (cluster-aware) | upper 95% answer-level (benchmark only) | class |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for c in bounds["cells"]:
        L.append(f"| {c['model']} | {c['arm']} | {c['answers']} | {c['refusals']} | {c['queries']} | {c['queries_with_refusal']} | {fp(c['query_level_rate'], 5)} | "
                 f"{fp(c['upper95_query_level'], 5)} | {fp(c['upper95_answer_level_benchmark'], 5)} | {c['class']} |")
    L += ["", "| model | contrast | cells | upper 95% of the absolute difference (query level) |", "|---|---|---|---|"]
    for c in bounds["contrasts"]:
        L.append(f"| {c['model']} | {c['contrast']} | {', '.join(c['cells'])} | {fp(c['upper95_abs_difference'], 5)} |")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["verify", "reproduce", "D", "E", "E-summary", "C", "C-checks", "C-summary", "check-a-one"])
    ap.add_argument("--root", required=True); ap.add_argument("--code-dir", required=True); ap.add_argument("--tmp", required=True)
    ap.add_argument("--synthetic", action="store_true"); ap.add_argument("--registration", default=None)
    ap.add_argument("--out", required=True); ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--families", nargs="*", default=None); ap.add_argument("--configs", nargs="*", default=None)
    ap.add_argument("--n", type=int, default=None); ap.add_argument("--parts", nargs="*", default=None)
    ap.add_argument("--grid-points", nargs="*", type=int, default=None)
    ap.add_argument("--nb-a", type=int, default=N_BOOT_A); ap.add_argument("--budget-s", type=float, default=CHECK_A_BUDGET_S)
    ap.add_argument("--k", type=int, default=0); ap.add_argument("--config", default=None); ap.add_argument("--models", nargs="*", default=None)
    a = ap.parse_args()
    if not a.synthetic:
        if a.registration is None:
            raise SystemExit("--registration is required for real data")
        if a.n is not None or a.nb_a != N_BOOT_A or a.configs or a.parts or a.grid_points is not None or a.budget_s != CHECK_A_BUDGET_S \
                or a.cmd == "check-a-one" or (a.families and a.cmd in ("C", "C-checks", "C-summary")) or a.workers != 4:
            raise SystemExit("counts, configurations, parts, budget and workers are fixed for real data (declared): overrides are refused")
    machine = a.cmd in ("E", "E-summary", "reproduce")
    S = Setup2(a.root, a.code_dir, a.tmp, a.synthetic, a.registration, machine=machine)
    out = Path(a.out)
    fams = a.families or FAM_ORDER
    stamp = {"driver_sha256": DRIVER_SHA, "synthetic": a.synthetic, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "setup_s": S.setup_s}
    if a.cmd == "verify":
        out.write_text(json.dumps({**stamp, "checks": S.checks, "design": design_check(S)}, indent=1), encoding="utf-8")
    elif a.cmd == "reproduce":
        R = json.loads((S.root / "ANALYSIS-RESULTS.json").read_text(encoding="utf-8"))
        t0 = time.time()
        rep = reproduce2(S, R)
        out.write_text(json.dumps({**stamp, "elapsed_s": time.time() - t0, **rep}, indent=1, default=str), encoding="utf-8")
        print(json.dumps({"ok": rep["ok"], "elapsed_s": time.time() - t0}))
        if not rep["ok"]:
            raise SystemExit(1)
    elif a.cmd == "D":
        t0 = time.time()
        res = d_compute(S)
        res = {**stamp, "elapsed_s": time.time() - t0, **res}
        out.mkdir(parents=True, exist_ok=True)
        (out / "D-RESULTS.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        (out / "D-RESULTS.md").write_text(render_d(res), encoding="utf-8")
    elif a.cmd == "E":
        el, nt = e_run(S, out, a.workers, Path(a.tmp), n_rep=a.n, parts=a.parts, grid_points=a.grid_points)
        print(json.dumps({"elapsed_s": el, "tasks": nt}))
    elif a.cmd == "E-summary":
        lines = read_jsonl(out / "E-POWER.jsonl")
        power = e_summary(S, lines)
        bounds = e_bounds(S)
        t = read_jsonl(out / "E-timing.jsonl")
        meta = (f"Replications per grid value: {a.n or N_REP_E}; {len(lines)} simulated data sets in {len(t)} tasks; "
                f"{sum(x['generate'] + x['registered'] for x in t):.0f} s of worker time; job errors {sum(len(x['job_errors']) for x in t)}.")
        res = {**stamp, "power": power, "bounds": bounds, "meta": meta}
        (out / "E-RESULTS.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        (out / "E-RESULTS.md").write_text(render_e(power, bounds, meta), encoding="utf-8")
    elif a.cmd == "C":
        el, nt = c_run(S, fams, out, a.workers, Path(a.tmp), n_override=a.n, configs=a.configs)
        print(json.dumps({"elapsed_s": el, "tasks": nt}))
    elif a.cmd == "C-checks":
        print(json.dumps(c_checks(S, out, fams, budget_s=a.budget_s, nb=a.nb_a)))
    elif a.cmd == "C-summary":
        res = c_summary(out, fams)
        act = [f for f, F in res["families"].items() if F["A*_activated"]]
        res["A*_real"] = a_star_real(S, act) if (act and not a.synthetic) else {}
        res = {**stamp, **res}
        (out / "C-RESULTS.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        (out / "C-RESULTS.md").write_text(render_c(res), encoding="utf-8")
    elif a.cmd == "check-a-one":
        r = check_a(S, fams[0], a.config, a.k, a.models, nb=a.nb_a)
        out.write_text(json.dumps(r, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
