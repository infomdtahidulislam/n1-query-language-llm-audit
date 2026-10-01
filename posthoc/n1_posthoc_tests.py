#!/usr/bin/env python3
"""n1_posthoc_tests.py — N1: validation of n1_posthoc.py on synthetic data only (item 7 of the post-hoc declaration),
run before the declaration record exists. Nothing here reads a study outcome: the synthetic studies come from the
registered harness n1_synth.py (sha256 7b71747f…), which reuses only design information (query ids, categories,
robust50 flags), and every fixture below is written by hand.

  deterministic   the fixed checks that must pass (loader and state; identity with the registered script on a synthetic
                  study; family filters; known per-answer and paired estimates; exhaustive small permutation cases;
                  undefined outcomes, no eligible query, all-zero and constant differences, separation and the fallback;
                  the bootstrap-t arithmetic; reproducible seeds, also across worker counts; the stratified count matrix;
                  the null generators; Holm; the zero-replicate Boot; temporary files; the real-data guard)
  planted         recovery in five planted-effect synthetic studies (n1_synth.py seeds 1 to 5), registered and post-hoc
  null            rejection rates of the two post-hoc tests in 200 synthetic null studies (--null --het 0, seeds
                  3001 to 3200), as diagnostics with Monte Carlo intervals

Usage:  python n1_posthoc_tests.py deterministic|planted|null --code-dir DIR --work DIR --out FILE [--workers 2]
"""
import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import argparse, hashlib, importlib.util, itertools, json, math, shutil, subprocess, sys, time
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location("n1_posthoc", HERE.with_name("n1_posthoc.py"))
D = importlib.util.module_from_spec(spec)
sys.modules["n1_posthoc"] = D              # so that worker tasks pickle by reference
spec.loader.exec_module(D)
sha = D.sha
PLANTED_SEEDS = [1, 2, 3, 4, 5]
NULL_SEEDS = list(range(3001, 3201))
VAL_BOOT_SEED = 20261151


def make_synth(code_dir, work, seed, null=False, het=0.0):
    out = Path(work) / f"syn_{'null_' if null else ''}{seed}"
    if (out / "SYNTHETIC").exists():
        return out
    if out.exists():
        shutil.rmtree(out)
    cmd = [sys.executable, str(Path(code_dir) / "n1_synth.py"), str(out), "--seed", str(seed)]
    if null:
        cmd += ["--null", "--het", str(het)]
    assert sha(Path(code_dir) / "n1_synth.py") == D.REG_HASH["n1_synth.py"]
    subprocess.run(cmd, check=True, capture_output=True)
    (out / "SYNTHETIC").write_text("synthetic study made by n1_synth.py for the validation of n1_posthoc.py\n")
    return out


# ============================================================================================ deterministic checks
class Checks:
    def __init__(self):
        self.res = []

    def ok(self, name, cond, detail=None):
        self.res.append({"check": name, "pass": bool(cond), "detail": detail})
        print(("PASS " if cond else "FAIL ") + name + ("" if cond or detail is None else f"  {detail}"), flush=True)
        return cond


_ROWN = itertools.count()


def row(model="m1", query="q1", arm="en", primary=True, brands=(), prices=(), outcome="valid", key=None):
    return {"key": key or f"{model}-{query}-{arm}-{next(_ROWN)}", "model": model, "query": query, "arm": arm,
            "rep": 1, "primary": primary, "refused": not primary, "valid": True, "mixed": False, "truncated": False,
            "persona": False, "brands": list(brands), "brands_order": list(brands), "brands_x": list(brands),
            "recommended": [], "retailers": [], "retailers_order": [], "prices": list(prices), "outcome": outcome}


def deterministic(code_dir, work, out):
    C = Checks()
    t0 = time.time()
    code_dir, work = Path(code_dir), Path(work)
    s1 = make_synth(code_dir, work, 1)
    reg_json = s1 / "ANALYSIS-RESULTS.json"
    if not reg_json.exists():
        raise SystemExit("run the registered script on the synthetic study first (ANALYSIS-RESULTS.json with --glmm-boot) and n1_robustness.py")
    # ---- 1 loader and state
    ns, state = D.load_registered(code_dir)
    C.ok("loader: every whitelisted name defined", all(n in ns for n in D.WL_CONSTS | D.WL_FUNCS | D.WL_CLASSES))
    C.ok("loader: argument parsing and pipeline not executed (no ap, A, H, Cp, R, BH, BC in the namespace)", not (D.FORBIDDEN & set(ns)))
    C.ok("loader: reused functions read the loader namespace", all(ns[f].__globals__ is ns for f in D.WL_FUNCS))
    D.init_state(ns, state, s1, code_dir / "n1_glmm.R", work / "tmp_det")
    C.ok("state: counts as the registered script reports them on this study",
         (len(ns["coded_all"]), len(ns["final"]), len(ns["pending"]), len(ns["usage"]), len(ns["PERSONA"])) == (24043, 24000, 0, 24000, 230),
         (len(ns["coded_all"]), len(ns["final"]), len(ns["pending"]), len(ns["usage"]), len(ns["PERSONA"])))
    C.ok("state: R_SCRIPT is the registered n1_glmm.R", sha(ns["R_SCRIPT"]) == D.REG_HASH["n1_glmm.R"])
    C.ok("state: TMP inside the work folder and TMPDIR pointed there", str(ns["TMP"]).startswith(str(work)) and os.environ["TMPDIR"] == str(ns["TMP"]))
    # ---- 2 identity with the registered script on synthetic study 1 (estimates, stored intervals, registered P, check (c))
    S = D.Setup(s1, code_dir, work / "tmp_det2", synthetic=True)
    R = json.loads(reg_json.read_text(encoding="utf-8"))
    rep = D.reproduce(S, R)
    C.ok("identity: 96 estimates and eligible-query counts equal the registered script's", rep["estimates"]["checked"] == 96 and not rep["estimates"]["mismatch"], rep["estimates"]["mismatch"][:3])
    C.ok("identity: 96 run-of-record intervals reproduced with the registered Boot", rep["run_of_record_ci"]["checked"] == 96 and not rep["run_of_record_ci"]["mismatch"], rep["run_of_record_ci"]["mismatch"][:3])
    C.ok("identity: 96 registered P values, methods and within-family Holm decisions reproduced through the reused functions",
         rep["registered_p"]["checked"] == 96 and not rep["registered_p"]["p_mismatch"] and not rep["registered_p"]["method_mismatch"]
         and not rep["registered_p"]["holm_decision_mismatch"],
         {"max_abs": rep["registered_p"]["max_abs_diff"], "p": rep["registered_p"]["p_mismatch"][:3], "m": rep["registered_p"]["method_mismatch"][:3]})
    # the reproduction tolerances: GLMM Wald P within 2% (or 1e-9), every other P within 1e-12
    import copy
    glmm_keys = [(f, m, c) for f in ("RQ2_local_share", "RQ4_price_mention", "RQ4_bdt_share", "RQ5_reversion", "RQ5_refusal")
                 for m in S.ns["MODELS"] for c, x in R["primary"][f]["results"][m]["contrasts"].items()
                 if x["test"]["method"] == "glmm_wald" and x["test"]["p"] > 1e-6]
    wil_key = next(k for k, x in R["primary"]["RQ1_excess_divergence"]["results"].items() if x.get("n_query"))
    R1 = copy.deepcopy(R)
    f, m, c = glmm_keys[0]
    R1["primary"][f]["results"][m]["contrasts"][c]["test"]["p"] *= 1.01
    rp1 = D.reproduce(S, R1)
    R2 = copy.deepcopy(R)
    f2, m2, c2 = glmm_keys[1]
    R2["primary"][f2]["results"][m2]["contrasts"][c2]["test"]["p"] *= 1.05
    R2["primary"]["RQ1_excess_divergence"]["results"][wil_key]["test"]["p"] += 1e-10
    rp2 = D.reproduce(S, R2)
    flagged = sorted(x["key"] for x in rp2["registered_p"]["p_mismatch"])
    C.ok("reproduction tolerance: a GLMM P off by 1% passes; one off by 5% and a Wilcoxon P off by 1e-10 stop the run",
         rp1["ok"] and not rp2["ok"] and flagged == sorted([f"{f2}|{m2}|{c2}", f"RQ1_excess_divergence|{wil_key}"]), flagged)
    C.ok("identity: the randomization code reproduces the registered setdiv_perm exactly (seed 20260930, check (c))",
         rep["check_c"]["checked"] == 18 and not rep["check_c"]["mismatch"], rep["check_c"]["mismatch"][:3])
    rob = D.parse_robustness((s1 / "ANALYSIS-ROBUSTNESS.md").read_text(encoding="utf-8"))
    C.ok("robustness markers parsed for all six families and 96 contrasts", sum(len(v) for v in rob.values()) == 96)
    # ---- 3 family filters
    rows = [row(arm="en", primary=True), row(arm="en", primary=False), row(arm="bl_translit", primary=True), row(arm="bn", primary=True)]
    fr = D.analysis_rows(ns, "RQ2_local_share", rows)
    C.ok("filters: human families keep P-filtered rows in en, bn, bl only", [r["arm"] for r in fr] == ["en", "bn"] and all(r["primary"] for r in fr))
    crow = lambda arm, oc: {"model": "m", "query": "q", "arm": arm, "outcome": oc, "key": f"{arm}{oc}"}
    cr = [crow(a, o) for a in ("en", "bn", "bl", "bl_translit") for o in ("valid", "language_reversion", "refusal", "degenerate")]
    ref = D.analysis_rows(ns, "RQ5_refusal", cr)
    rev = D.analysis_rows(ns, "RQ5_reversion", cr)
    C.ok("filters: refusal over nondeg answers in en, bn, bl", sorted((r["arm"], r["outcome"]) for r in ref) ==
         sorted((a, o) for a in ("en", "bn", "bl") for o in ("valid", "language_reversion", "refusal")))
    C.ok("filters: reversion over non-refused non-degenerate answers in bn and bl", sorted((r["arm"], r["outcome"]) for r in rev) ==
         sorted((a, o) for a in ("bn", "bl") for o in ("valid", "language_reversion")))
    # ---- 4 known per-answer and paired estimates
    ns["BCLASS"].update({"LOCAL1": "local", "GLOB1": "global", "AMB1": "ambiguous"})
    r1 = row(brands=["LOCAL1", "GLOB1", "AMB1", "UNKNOWN"])
    C.ok("per answer: local share = local / (local + global), ambiguous and unclassifiable excluded", ns["local_share_answer"](r1) == 0.5)
    C.ok("per answer: no classified mention -> undefined", math.isnan(D.answer_value(ns, "RQ2_local_share", row(brands=["AMB1"]))))
    C.ok("per answer: BDT share = mean of BDT indicators, unstated counts 0", D.answer_value(ns, "RQ4_bdt_share", row(prices=[(10.0, "BDT"), (0.0, "unstated"), (5.0, "USD"), (7.0, "BDT")])) == 0.5)
    C.ok("per answer: BDT share undefined without a price entry", math.isnan(D.answer_value(ns, "RQ4_bdt_share", row(prices=[]))))
    C.ok("per answer: price mention counts a zero-amount entry", D.answer_value(ns, "RQ4_price_mention", row(prices=[(0.0, "BDT")])) == 1.0)
    cellv = {("m", "q1", "a"): np.array([0.2, np.nan, 0.4]), ("m", "q1", "b"): np.array([0.1]),
             ("m", "q2", "a"): np.array([np.nan, np.nan]), ("m", "q2", "b"): np.array([0.5]),
             ("m", "q3", "a"): np.array([1.0]), ("m", "q3", "b"): np.array([0.0, 1.0])}
    pq = D.per_query(ns, "RQ2_local_share", cellv, ["q1", "q2", "q3", "q4"], "m", "a", "b")
    C.ok("paired: defined cell means, queries with an undefined arm dropped", set(pq) == {"q1", "q3"} and abs(pq["q1"] - 0.2) < 1e-15 and pq["q3"] == 0.5, pq)
    C.ok("paired: estimate = mean over eligible queries", abs(D.estimate_of(pq) - 0.35) < 1e-15)
    J = ns["jaccard"]
    C.ok("RQ1: excess for disjoint constant arms = 1", ns["excess"]([["x"], ["x"]], [["y"], ["y"]], J) == 1.0)
    C.ok("RQ1: excess for identical mixed arms = -0.5", ns["excess"]([["x"], ["y"]], [["x"], ["y"]], J) == -0.5)
    C.ok("RQ1: empty sets kept (J(0,0) = 1, J(0,S) = 0)", ns["excess"]([[], []], [["x"], []], J) == 0.0)
    C.ok("RQ1: fewer than two answers in an arm -> undefined", ns["excess"]([["x"]], [["x"], ["y"]], J) is None)
    # ---- 5 exhaustive small permutation cases
    pools = {"q1": (np.array([1.0, 0.0]), np.array([0.0, 0.0])), "q2": (np.array([0.5, np.nan]), np.array([1.0, 0.0])),
             "q3": (np.array([1.0]), np.array([0.0, np.nan, 1.0])), "q4": (np.array([np.nan]), np.array([np.nan, 0.3]))}
    brute_ok = True
    per_q_alts = {}
    for q, (va, vb) in pools.items():
        alts = D.alts_scalar(va, vb)
        pool = np.concatenate([va, vb])
        bf = []
        for ia in itertools.combinations(range(len(pool)), len(va)):
            A_ = pool[list(ia)]; B_ = np.delete(pool, list(ia))
            A_, B_ = A_[~np.isnan(A_)], B_[~np.isnan(B_)]
            bf.append(A_.mean() - B_.mean() if len(A_) and len(B_) else np.nan)
        bf = np.array(bf)
        brute_ok &= bool(np.allclose(alts, bf, equal_nan=True, atol=1e-15))
        per_q_alts[q] = alts
    C.ok("randomization: per-query alternatives equal brute-force enumeration (undefined markers move)", brute_ok)
    cellx = {("m", q, "a"): va for q, (va, vb) in pools.items()}
    cellx.update({("m", q, "b"): vb for q, (va, vb) in pools.items()})
    pqx = D.per_query(ns, "RQ2_local_share", cellx, sorted(pools), "m", "a", "b")
    T = D.estimate_of(pqx)
    # exact distribution over the product of per-query assignments
    vals, probs = [], []
    for combo in itertools.product(*[range(len(per_q_alts[q])) for q in sorted(pools)]):
        xs = [per_q_alts[q][i] for q, i in zip(sorted(pools), combo)]
        xs = [x for x in xs if not np.isnan(x)]
        vals.append(np.mean(xs) if xs else 0.0)
        probs.append(np.prod([1.0 / len(per_q_alts[q]) for q in sorted(pools)]))
    vals, probs = np.array(vals), np.array(probs)
    hi = probs[vals >= T - 1e-12].sum(); lo = probs[vals <= T + 1e-12].sum()
    p_exact = min(1.0, 2 * min(hi, lo))
    ns_mini = dict(ns); ns_mini["MODELS"] = ["m"]
    old_def = D.fam_def
    D.fam_def = lambda ns_, fam: ("human", ["a", "b"], [("a", "b")], "scalar")
    try:
        rz = D.randomization_family(ns_mini, "RQ2_local_share", cellx, sorted(pools), 12345, 400000, {"m|a-b": T})
    finally:
        D.fam_def = old_def
    se = math.sqrt(max(p_exact * (1 - p_exact), 1e-12) / 400000) * 2
    C.ok("randomization: Monte Carlo P matches the exact enumeration within 4 MC SE (+1 correction)",
         abs(rz["m|a-b"]["p"] - p_exact) < 4 * se + 2 * 2 / 400001, {"mc": rz["m|a-b"]["p"], "exact": p_exact})
    # RQ1 small exact case: alternatives equal brute force
    A_, B_ = [["x"], ["y"]], [["x"], ["z"]]
    alts = D.alts_set(ns, A_, B_)
    pool = A_ + B_
    bf = [ns["excess"]([pool[i] for i in ia], [pool[i] for i in range(4) if i not in ia], J) for ia in itertools.combinations(range(4), 2)]
    C.ok("randomization (RQ1): alternatives equal setdiv_perm's enumeration", np.allclose(alts, bf))
    # ---- 6 undefined outcomes, no eligible query, all-zero and constant differences
    sb = D.strat_boot(ns, [f"q{i:02d}" for i in range(40)], {f"q{i:02d}": f"c{i % 4}" for i in range(40)}, 7, 2000)
    C.ok("mean effect: no eligible query -> no test, P = 1", D.mean_effect({}, sb)["p"] == 1.0 and not D.mean_effect({}, sb)["test"])
    few = {f"q{i:02d}": 0.1 * i for i in range(9)}
    C.ok("mean effect: fewer than 10 eligible queries -> no test, P = 1", D.mean_effect(few, sb)["p"] == 1.0 and "fewer than 10" in D.mean_effect(few, sb)["reason"])
    zeros = {f"q{i:02d}": 0.0 for i in range(20)}
    C.ok("mean effect: all-zero differences -> SE = 0, no test, P = 1", D.mean_effect(zeros, sb)["p"] == 1.0 and "SE zero" in D.mean_effect(zeros, sb)["reason"])
    const = {f"q{i:02d}": 0.3 for i in range(20)}
    mc = D.mean_effect(const, sb)
    C.ok("mean effect: constant non-zero differences (0.3 x 20; floating SD 5e-17) -> SE = 0, no test, P = 1", mc["p"] == 1.0 and "SE zero" in mc.get("reason", ""), mc)
    const2 = {f"q{i:02d}": (1 / 3 - 0.0) if i % 2 else (2 / 3 - 1 / 3) for i in range(20)}
    mc2 = D.mean_effect(const2, sb)
    C.ok("mean effect: differences equal up to rounding (1/3 vs 2/3 - 1/3) -> SE = 0, no test", mc2["p"] == 1.0 and "SE zero" in mc2.get("reason", ""), mc2)
    cell0 = {("m", "q1", "a"): np.array([np.nan, np.nan]), ("m", "q1", "b"): np.array([1.0, 0.0])}
    D.fam_def = lambda ns_, fam: ("human", ["a", "b"], [("a", "b")], "scalar")
    try:
        pq0 = D.per_query(ns_mini, "RQ2_local_share", cell0, ["q1"], "m", "a", "b")
        rz0 = D.randomization_family(ns_mini, "RQ2_local_share", cell0, ["q1"], 1, 1000, {"m|a-b": D.estimate_of(pq0)})
        cz = {("m", q, x): np.zeros(2) for q in ("q1", "q2", "q3") for x in ("a", "b")}
        rzz = D.randomization_family(ns_mini, "RQ4_price_mention", cz, ["q1", "q2", "q3"], 1, 1000, {"m|a-b": 0.0})
    finally:
        D.fam_def = old_def
    C.ok("randomization: observed contrast without an eligible query -> P = 1 (draws without an eligible query score 0)",
         pq0 == {} and rz0["m|a-b"]["p"] == 1.0 and not rz0["m|a-b"]["test"])
    C.ok("randomization: all-zero outcomes -> T* = 0 = T, P = 1", rzz["m|a-b"]["p"] == 1.0 and rzz["m|a-b"]["null_mean"] == 0.0)
    # ---- 7 separation and the fallback (registered functions; synthetic gemini en mentions all global)
    rr, _ = D.run_registered(S.ns, "RQ2_local_share", S.base["human"], S.b0s["human"], [])
    g = rr["results"]["gemini-3-flash"]
    C.ok("separation: the registered model reports separation and F.3's fallback supplies the P value",
         g["glmm"]["status"] == "separation" and g["contrasts"]["bn-en"]["test"]["method"] == "fallback_paired_wilcoxon")
    rr2, _ = D.run_registered(S.ns, "RQ5_refusal", S.base["refusal"], S.b0s["corpus"], [])
    gz = rr2["results"]["gpt-5.6-luna"]
    C.ok("no events: an arm with no refusals is not identifiable; the contrast keeps P = 1 via the fallback",
         gz["glmm"]["status"] == "separation" and gz["contrasts"]["bn-en"]["test"]["p"] == 1.0, gz["contrasts"]["bn-en"]["test"])
    C.ok("temporary files: the worker directory is empty after each registered call", not any(Path(S.ns["TMP"]).iterdir()))
    # ---- 8 the bootstrap-t arithmetic against an explicit multiset computation
    rng = np.random.default_rng(3)
    frame = [f"q{i:02d}" for i in range(40)]
    per_q = {q: float(x) for q, x in zip(frame[:30], rng.normal(0.05, 0.2, 30))}
    me = D.mean_effect(per_q, sb)
    exc = 0
    est = np.mean(list(per_q.values())); se = np.std(list(per_q.values()), ddof=1) / math.sqrt(30); t = est / se
    for bi in range(sb.C.shape[0]):
        vals = []
        for q, x in per_q.items():
            vals += [x] * int(sb.C[bi, sb.ix[q]])
        vals = np.array(vals)
        if len(vals) >= 2 and np.ptp(vals) > 0:
            ts = (vals.mean() - est) / (np.std(vals, ddof=1) / math.sqrt(len(vals)))
            exc += abs(ts) >= abs(t)
        else:
            exc += 1
    C.ok("bootstrap-t: vectorized N, S, Q arithmetic equals the explicit multiset computation (2,000 resamples)",
         me["exceedances"] == exc and me["p"] == (1 + exc) / (sb.C.shape[0] + 1), {"vector": me["exceedances"], "explicit": exc})
    sparse = {q: (1.0 if q in ("q00", "q01") else 0.0) for q in frame[:20]}
    ms = D.mean_effect(sparse, sb)
    C.ok("bootstrap-t: resamples drawing one distinct value count as exceedances (reported with reason)",
         ms["invalid_resamples"] > 0 and ms["invalid_reasons"].get("one distinct drawn value (SE* = 0)", 0) == ms["invalid_resamples"], ms["invalid_reasons"])
    # ---- 9 stratified count matrix
    sh = S.sbs["human"]; sc = S.sbs["corpus"]
    cats_h = Counter(S.CAT[q] for q in sh.q); cats_c = Counter(S.CAT[q] for q in sc.q)
    okh = all((sh.C[:, [sh.ix[q] for q in sh.q if S.CAT[q] == c]].sum(axis=1) == n).all() for c, n in cats_h.items())
    okc = all((sc.C[:, [sc.ix[q] for q in sc.q if S.CAT[q] == c]].sum(axis=1) == n).all() for c, n in cats_c.items())
    C.ok("stratified matrix: every row draws 8 per category (80) on the human layer and 25 per category (250) on the corpus",
         okh and okc and set(cats_h.values()) == {8} and set(cats_c.values()) == {25} and (sh.C.sum(1) == 80).all() and (sc.C.sum(1) == 250).all())
    C.ok("stratified matrix: non-negative integer counts, 10,000 rows, seeds 20261101 / 20261102",
         (sh.C >= 0).all() and np.array_equal(sh.C, np.round(sh.C)) and sh.C.shape == (10000, 80) and sc.C.shape == (10000, 250)
         and sh.seed == 20261101 and sc.seed == 20261102)
    C.ok("stratified matrix: Boot.mean works on it and drops no row when every query is eligible",
         S.sbs["human"].mean({q: 1.0 for q in sh.q})[1] == 0)
    sh2 = D.strat_boot(S.ns, S.frames["human"], S.CAT, 20261101)
    C.ok("stratified matrix: reproducible from its seed", np.array_equal(sh.C, sh2.C))
    # ---- 10 null generators
    base = S.base["human"]
    g1 = D.null_dataset(S.ns, "human", "i", S.base, np.random.default_rng(11))["human"]
    cnt0 = Counter((r["model"], r["query"], r["arm"]) for r in base); cnt1 = Counter((r["model"], r["query"], r["arm"]) for r in g1)
    def by_mq(rows):
        d = defaultdict(list)
        for r in rows:
            d[(r["model"], r["query"])].append(r)
        return d
    b0g, b1g = by_mq(base), by_mq(g1)
    same_pool = set(b0g) == set(b1g) and all(sorted(r["key"] for r in b0g[mq]) == sorted(r["key"] for r in b1g[mq]) for mq in b0g)
    moved = sum(r0["arm"] != r1["arm"] for r0, r1 in zip(base, g1))
    C.ok("scenario (i): each arm's count kept per query x model, pooled answers kept intact, labels actually reassigned", cnt0 == cnt1 and same_pool and moved > 0, moved)
    C.ok("scenario (i): answers stay intact (brands and prices move together)", all(r1["brands"] is r0["brands"] and r1["prices"] is r0["prices"] for r0, r1 in zip(base, g1)))
    g2 = D.null_dataset(S.ns, "human", "ii", S.base, np.random.default_rng(12))["human"]
    blocks_ok = True
    b2g = by_mq(g2)
    for mq in b0g:
        src = {a: tuple(sorted(r["key"] for r in b0g[mq] if r["arm"] == a)) for a in S.ns["ARMS3"]}
        dst = {a: tuple(sorted(r["key"] for r in b2g[mq] if r["arm"] == a)) for a in S.ns["ARMS3"]}
        blocks_ok &= sorted(src.values()) == sorted(dst.values())
    C.ok("scenario (ii): whole source-arm blocks relabelled by one ordering per query x model", blocks_ok)
    gc = D.null_dataset(S.ns, "corpus", "ii", S.base, np.random.default_rng(13))
    sw = Counter()
    bg, ag = by_mq(S.base["reversion"]), by_mq(gc["reversion"])
    for mq in bg:
        before = {r["key"]: r["arm"] for r in bg[mq]}
        after = {r["key"]: r["arm"] for r in ag[mq]}
        sw["swap" if all(before[k] != after[k] for k in before) else ("keep" if before == after else "other")] += 1
    C.ok("scenario (ii): reversion blocks swapped or kept (never mixed), about half each", sw["other"] == 0 and 0.4 < sw["swap"] / (sw["swap"] + sw["keep"]) < 0.6, dict(sw))
    C.ok("scenario (ii): indicators frozen as coded (outcome fields unchanged)", all(a["outcome"] == b["outcome"] and a["key"] == b["key"] for a, b in zip(S.base["reversion"], gc["reversion"])))
    C.ok("scenario (ii): RQ1 left out", "RQ1_excess_divergence" not in D.fams_for("human", "ii") and D.fams_for("human", "i")[0] == "RQ1_excess_divergence")
    # ---- 11 Holm and the zero-replicate Boot
    from statsmodels.stats.multitest import multipletests
    ps = [0.001, 0.02, 0.04, 0.3, 1.0]
    hm = D.holm_map(S.ns, dict(zip("abcde", ps)))
    rej, pa, _, _ = multipletests(ps, alpha=0.05, method="holm")
    C.ok("Holm: the registered holm() equals statsmodels' Holm", all(hm[k]["p_holm"] == float(x) and hm[k]["reject"] == bool(r) for k, x, r in zip("abcde", pa, rej)))
    b0 = S.b0s["human"]
    C.ok("zero-replicate Boot: C has 0 rows; percentile interval empty; the layer's query frame kept",
         b0.C.shape == (0, 80) and S.ns["pct"](b0.mean({"x": 1.0} if False else {b0.q[0]: 1.0})[0]) == [None, None])
    # ---- 12 reproducible seeds, also across worker counts
    wd = work / "repro"
    if wd.exists():
        shutil.rmtree(wd)
    wd.mkdir()
    D.G["setup"] = S
    D.set_tmp(S.ns, wd / "t0")
    D.G["wid"] = 0
    a1 = D._cal_task("human", "i", 3, True, D.SEEDS["bench"]["human|i"])
    a2 = D._cal_task("human", "i", 3, True, D.SEEDS["bench"]["human|i"])
    strip = lambda r: {k: v for k, v in r.items() if k not in ("timing", "worker")}
    C.ok("seeds: the same data-set index gives identical results", json.dumps(strip(a1), sort_keys=True) == json.dumps(strip(a2), sort_keys=True))
    D.calibrate(S, "corpus", "i", 4, 4, 1, wd / "w1.jsonl", wd / "tmp1", D.SEEDS["bench"]["corpus|i"])
    D.calibrate(S, "corpus", "i", 4, 4, 2, wd / "w2.jsonl", wd / "tmp2", D.SEEDS["bench"]["corpus|i"])
    l1 = {json.loads(l)["k"]: strip(json.loads(l)) for l in (wd / "w1.jsonl").read_text().splitlines()}
    l2 = {json.loads(l)["k"]: strip(json.loads(l)) for l in (wd / "w2.jsonl").read_text().splitlines()}
    C.ok("seeds: results do not depend on scheduling (1 vs 2 workers, 4 corpus data sets)", json.dumps(l1, sort_keys=True) == json.dumps(l2, sort_keys=True))
    # the calibration summary against an independent recomputation (4 corpus data sets, scenario i)
    lines = [json.loads(l) for l in (wd / "w1.jsonl").read_text().splitlines()]
    sm = D.summarize_cal(S.ns, lines, "corpus", "i", nb=500)
    ok_sum = True
    for fam in ("RQ5_reversion", "RQ5_refusal"):
        keys = D.keys_of(S.ns, fam)
        rows_ = sorted(lines, key=lambda r: r["k"])
        hs = {pr: [D.holm_map(S.ns, {k: ln["families"][fam]["contrasts"][k][f"{pr}_p"] for k in keys}) for ln in rows_] for pr in ("reg", "me", "rz")}
        for pr in ("reg", "me", "rz"):
            fw = sum(any(v["reject"] for v in h.values()) for h in hs[pr])
            ok_sum &= sm["families"][fam]["fwer"][pr]["x"] == fw and sm["families"][fam]["fwer"][pr]["n"] == len(rows_)
            for k in keys:
                rate = np.mean([ln["families"][fam]["contrasts"][k][f"{pr}_p"] <= 0.05 for ln in rows_])
                ok_sum &= abs(sm["families"][fam]["per_contrast"][pr][k]["rate"] - rate) < 1e-15
        both = sum(any(hs["reg"][i][k]["reject"] and hs["me"][i][k]["reject"] for k in keys) for i in range(len(rows_)))
        tri = sum(any(hs["reg"][i][k]["reject"] and hs["me"][i][k]["reject"] and hs["rz"][i][k]["reject"] for k in keys) for i in range(len(rows_)))
        ok_sum &= sm["families"][fam]["intersections"]["reg_and_me"]["x"] == both and sm["families"][fam]["intersections"]["reg_and_me_and_rz"]["x"] == tri
    C.ok("summary: per-contrast rates, family-wise rates and both intersections equal an independent recomputation", ok_sum)
    mdc = D.render_cal({"corpus|i": sm}, S.ns)
    C.ok("summary: the calibration report renders with the null-status statements", "## corpus, scenario i" in mdc and all(x[:40] in mdc for x in D.NULL_STATUS))
    C.ok("summary: Wilson interval matches the closed form (3 of 20)", all(abs(a - b) < 1e-4 for a, b in zip(D.wilson(3, 20), (0.0524, 0.3604))))
    s_a = D.stream_seed(D.SEEDS["cal"]["human|i"], 0, 1); s_b = D.stream_seed(D.SEEDS["cal"]["human|ii"], 0, 1); s_c = D.stream_seed(D.SEEDS["cal"]["human|i"], 1, 1)
    C.ok("seeds: independent declared streams per layer, scenario, index and purpose", len({s_a, s_b, s_c, D.stream_seed(D.SEEDS["cal"]["human|i"], 0, 2)}) == 4)
    # ---- 13 guards
    try:
        D.Setup(work, code_dir, work / "tmp_g", synthetic=True)
        g_ok = False
    except SystemExit:
        g_ok = True
    C.ok("guard: synthetic mode refuses a root without the SYNTHETIC marker", g_ok)
    reg_text = Path(code_dir).joinpath("prereg.md")
    if reg_text.exists():
        try:
            D.verify_real(code_dir, code_dir, reg_text)
            g2_ok = D.DECL_PREFIX in reg_text.read_text(encoding="utf-8")
        except SystemExit as e:
            g2_ok = "declaration record" in str(e) or "does not quote" in str(e)
        C.ok("guard: real-data state refused while the registration lacks the declaration quoting this driver", g2_ok)
    # ---- 14 end-to-end rehearsal of the real-data path on the synthetic study (tables, item 4)
    rp = D.posthoc_real(S, R, rob)
    orr = D.outputs_of_record(S.ns, R, rob)
    jobs = D.glmm_job_table(S.ns, R)
    den = D.denominators(S)
    C.ok("rehearsal: 96 post-hoc rows, 96 outputs of record, 30 model jobs, 36 human and 18 corpus denominator cells",
         sum(len(v) for v in rp["families"].values()) == 96 and len(orr) == 96 and len(jobs) == 30 and len(den["human"]) == 18 and len(den["corpus"]) == 18)
    C.ok("rehearsal: reconstructed query lists match the stored counts and estimates",
         all(e["n_query"] == e["stored"]["n_query"] and D._close(e["estimate"], e["stored"]["estimate"]) for f in rp["families"].values() for e in f.values()))
    md = D.render_real({"posthoc": rp, "outputs_of_record": orr, "glmm_jobs": jobs, "denominators": den})
    C.ok("rehearsal: the report renders", md.count("\n") > 300)
    R3 = copy.deepcopy(R)
    f3, m3, c3 = glmm_keys[0]
    R3["primary"][f3]["results"][m3]["contrasts"][c3]["log_odds"]["boot_ci"] = [None, None]
    md3 = D.render_real({"posthoc": rp, "outputs_of_record": D.outputs_of_record(S.ns, R3, rob), "glmm_jobs": jobs, "denominators": den})
    C.ok("rehearsal: a log-odds bootstrap interval that was not run renders as 'not run'", "{not run}" in md3)
    res = {"checks": C.res, "n_pass": sum(c["pass"] for c in C.res), "n": len(C.res), "elapsed_s": time.time() - t0,
           "driver_sha256": D.DRIVER_SHA, "tests_sha256": sha(HERE), "synthetic_study": {"seed": 1, "root": str(s1)},
           "rehearsal_disagreements": rp["disagreements"][:50]}
    Path(out).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"{res['n_pass']}/{res['n']} checks passed in {res['elapsed_s']:.0f} s")
    return res


# ============================================================================================ planted and null studies
def planted_truth(fam, m, a, b):
    s = 1.0 if m == "claude-sonnet-5" else (0.5 if m in ("grok-4.6", "kimi-k3") else 0.0)
    sign = lambda x: "+" if x > 1e-12 else ("-" if x < -1e-12 else "0")
    if fam == "RQ1_excess_divergence":
        if s > 0:
            return "+"
        return "+" if (m == "gemini-3-flash" and "en" in (a, b)) else "0"
    if fam == "RQ2_local_share":
        if m == "gemini-3-flash" and "en" in (a, b):
            return "+" if a != "en" else "-"
        t = {"en": 0.0, "bn": 0.9 * s, "bl": 0.45 * s}
        return sign(t[a] - t[b])
    if fam == "RQ4_price_mention":
        t = {"en": 0.0, "bn": 0.25 * s, "bl": 0.10 * s}
        return sign(t[a] - t[b])
    if fam == "RQ4_bdt_share":
        t = {"en": 0.0, "bn": 0.35 * s, "bl": 0.15 * s}
        return sign(t[a] - t[b])
    if fam == "RQ5_reversion":
        return "-" if s > 0 else "0"
    if m == "gpt-5.6-luna":
        return "0"
    t = {"en": 0.02 + 0.02 * s, "bn": 0.02 - 0.01 * s, "bl": 0.02}
    return sign(t[a] - t[b])


def _study_job(args):
    code_dir, work, seed, null, registered = args
    root = make_synth(code_dir, work, seed, null=null)
    out = Path(work) / f"study_{'null_' if null else ''}{seed}.json"
    if not out.exists():
        cmd = [sys.executable, str(HERE.with_name("n1_posthoc.py")), "study", "--root", str(root), "--code-dir", str(code_dir),
               "--tmp", str(Path(work) / f"tmp_{seed}"), "--synthetic", "--out", str(out)]
        if not registered:
            cmd.append("--no-registered")
        if null:
            cmd.append("--no-per-query")
        subprocess.run(cmd, check=True, capture_output=True)
    r = json.loads(out.read_text(encoding="utf-8"))
    if null:
        shutil.rmtree(root)
    return seed, r


def run_studies(code_dir, work, seeds, null, registered, workers):
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return dict(ex.map(_study_job, [(code_dir, work, s, null, registered) for s in seeds]))


def decisions(ns, fam, contrasts, proc):
    pm = {k: c[f"{proc}_p"] for k, c in contrasts.items()}
    return {k: v["reject"] for k, v in D.holm_map(ns, pm).items()}


def planted(code_dir, work, out, workers):
    t0 = time.time()
    ns, _ = D.load_registered(code_dir)
    res = run_studies(code_dir, work, PLANTED_SEEDS, False, True, workers)
    table, summ = [], defaultdict(Counter)
    for seed, r in sorted(res.items()):
        for fam in D.FAM_ORDER:
            cs = r["families"][fam]["contrasts"]
            dec = {p: decisions(ns, fam, cs, p) for p in ("reg", "me", "rz")}
            for k, c in cs.items():
                m, con = k.split("|"); a, b = con.split("-")
                tr = planted_truth(fam, m, a, b)
                sgn = None if c["estimate"] is None else ("+" if c["estimate"] > 0 else ("-" if c["estimate"] < 0 else "0"))
                row = {"seed": seed, "family": fam, "key": k, "truth": tr, "estimate": c["estimate"], "sign": sgn, "n_query": c["n_query"],
                       **{f"{p}_p": c[f"{p}_p"] for p in ("reg", "me", "rz")}, **{f"{p}_reject": dec[p][k] for p in ("reg", "me", "rz")},
                       "reg_method": c["reg_method"]}
                table.append(row)
                grp = "planted" if tr != "0" else "null"
                for p in ("reg", "me", "rz"):
                    summ[(fam, grp, p)]["n"] += 1
                    summ[(fam, grp, p)]["reject"] += dec[p][k]
                    if grp == "planted":
                        summ[(fam, grp, p)]["reject_right_sign"] += dec[p][k] and sgn == tr
                        summ[(fam, grp, p)]["sign_right"] += sgn == tr
    S = {f"{f}|{g}|{p}": dict(v) for (f, g, p), v in summ.items()}
    res_out = {"seeds": PLANTED_SEEDS, "summary": S, "table": table, "elapsed_s": time.time() - t0, "driver_sha256": D.DRIVER_SHA,
               "tests_sha256": sha(HERE), "truth_rule": "read from n1_synth.py: claude-sonnet-5 full effects, grok-4.6 and kimi-k3 half, "
               "gemini-3-flash's en mentions all global (RQ1 and RQ2 bn-en, bl-en), gpt-5.6-luna and deepseek-v4-flash null; "
               "refusal en 0.02+0.02s, bn 0.02-0.01s, bl 0.02 (gpt 0); reversion bl +0.35s"}
    Path(out).write_text(json.dumps(res_out, indent=1), encoding="utf-8")
    print(json.dumps(S, indent=0)[:3000])
    return res_out


def null_rates(code_dir, work, out, workers):
    t0 = time.time()
    ns, _ = D.load_registered(code_dir)
    res = run_studies(code_dir, work, NULL_SEEDS, True, False, workers)
    import gc
    gc.collect(); gc.freeze()             # multipletests calls gc.collect() on every call (speed only)
    seeds = sorted(res)
    out_d = {"seeds": [seeds[0], seeds[-1]], "n_studies": len(seeds), "families": {}}
    rng = np.random.default_rng(VAL_BOOT_SEED)
    for fam in D.FAM_ORDER:
        keys = D.keys_of(ns, fam)
        F = {}
        for p in ("me", "rz"):
            P = np.array([[res[s]["families"][fam]["contrasts"][k][f"{p}_p"] for k in keys] for s in seeds])
            notest = np.array([[not res[s]["families"][fam]["contrasts"][k][f"{p}_test"] for k in keys] for s in seeds])
            U = P <= D.ALPHA
            Hm = np.array([[hm[k]["reject"] for k in keys] for hm in (D.holm_map(ns, dict(zip(keys, row))) for row in P)])
            n = len(seeds)
            W = rng.multinomial(n, np.full(n, 1.0 / n), size=10000).astype(float)
            fa = (W @ U.mean(axis=1)) / n
            fw = int(Hm.any(axis=1).sum())
            F[p] = {"unadjusted_rate": float(U.mean()), "unadjusted_ci": [float(np.percentile(fa, 2.5)), float(np.percentile(fa, 97.5))],
                    "tests": int(U.size), "no_test": int(notest.sum()),
                    "fwer": fw / n, "fwer_wilson": D.wilson(fw, n), "per_model": {m: float(U[:, [i for i, k in enumerate(keys) if k.startswith(m + "|")]].mean()) for m in ns["MODELS"]}}
        out_d["families"][fam] = F
    out_d.update({"elapsed_s": time.time() - t0, "driver_sha256": D.DRIVER_SHA, "tests_sha256": sha(HERE), "interval_seed": VAL_BOOT_SEED})
    Path(out).write_text(json.dumps(out_d, indent=1), encoding="utf-8")
    print(json.dumps(out_d["families"], indent=0)[:3000])
    return out_d


BENCH_SEED = 4001
BENCH_PLAN = {"human|i": (1000, 200), "human|ii": (1000, 0), "corpus|i": (1000, 200), "corpus|ii": (1000, 0)}
CORPUS_CAP_S = 43200


def bench(code_dir, work, out, workers):
    """ten end-to-end null data sets per layer and scenario on n1_synth.py data (seed 4001), at the intended concurrency;
    forecast of item 5 (1,000 per layer and scenario, randomization on 200 in scenario i) and the 43,200 s corpus rule"""
    t0 = time.time()
    root = make_synth(code_dir, work, BENCH_SEED)
    runs = {}
    for key in ("human|i", "human|ii", "corpus|i", "corpus|ii"):
        L, sc = key.split("|")
        o = Path(work) / f"bench_{L}_{sc}.jsonl"
        if o.exists():
            o.unlink()
        cmd = [sys.executable, str(HERE.with_name("n1_posthoc.py")), "bench", "--root", str(root), "--code-dir", str(code_dir),
               "--tmp", str(Path(work) / f"tmp_bench_{L}_{sc}"), "--synthetic", "--out", str(o), "--layer", L, "--scenario", sc,
               "--n", "10", "--n-rand", "10" if sc == "i" else "0", "--workers", str(workers), "--stream", "bench"]
        t1 = time.time()
        pr = subprocess.run(cmd, check=True, capture_output=True, text=True)
        wall = time.time() - t1
        info = json.loads(pr.stdout.strip().splitlines()[-1])
        lines = [json.loads(l) for l in o.read_text(encoding="utf-8").splitlines() if l.strip()]
        comp = {c: [ln["timing"].get(c, 0.0) for ln in lines] for c in ("generate", "estimates", "mean_effect", "randomization", "registered", "total")}
        tot = sum(comp["total"])
        eff = tot / (info["elapsed_s"] * workers)
        a = float(np.mean([t - r for t, r in zip(comp["total"], comp["randomization"])]))
        b = float(np.mean(comp["randomization"]))
        N, Rn = BENCH_PLAN[key]
        work_s = N * a + Rn * b
        fc = work_s / (workers * eff) + info["setup_s"]
        runs[key] = {"n": len(lines), "wall_s_process": wall, "pool_elapsed_s": info["elapsed_s"], "setup_s": info["setup_s"],
                     "per_dataset_mean_s": {c: float(np.mean(v)) for c, v in comp.items()},
                     "per_dataset_max_s": {c: float(np.max(v)) for c, v in comp.items()},
                     "parallel_efficiency": eff, "forecast": {"datasets": N, "randomization_datasets": Rn, "single_worker_s": work_s,
                                                              "wall_s": fc}, "job_errors": sum(len(ln["job_errors"]) for ln in lines),
                     "seeds_logged": [ln["seeds"] for ln in lines], "file_sha256": sha(o)}
    # the summary path of item 5 (CLI), exercised on the benchmark's data sets
    t1 = time.time()
    subprocess.run([sys.executable, str(HERE.with_name("n1_posthoc.py")), "summarize", "--code-dir", str(code_dir), "--inputs"]
                   + [str(Path(work) / f"bench_{k.replace('|', '_')}.jsonl") for k in ("human|i", "human|ii", "corpus|i", "corpus|ii")]
                   + ["--out", str(Path(work) / "BENCH-SUMMARY")], check=True, capture_output=True)
    summary_s = time.time() - t1
    bsum = json.loads((Path(work) / "BENCH-SUMMARY.json").read_text(encoding="utf-8"))
    assert all(bsum[k]["n_datasets"] == 10 for k in ("human|i", "human|ii", "corpus|i", "corpus|ii"))
    corpus_wall = runs["corpus|i"]["forecast"]["wall_s"] + runs["corpus|ii"]["forecast"]["wall_s"]
    cut = corpus_wall > CORPUS_CAP_S
    if cut:
        for key in ("corpus|i", "corpus|ii"):
            r = runs[key]
            N, Rn = 500, BENCH_PLAN[key][1]
            a = r["per_dataset_mean_s"]["total"] - r["per_dataset_mean_s"]["randomization"]
            b = r["per_dataset_mean_s"]["randomization"]
            r["forecast_reduced"] = {"datasets": N, "randomization_datasets": Rn,
                                     "wall_s": (N * a + Rn * b) / (workers * r["parallel_efficiency"]) + r["setup_s"]}
    res = {"synthetic_seed": BENCH_SEED, "workers": workers, "runs": runs, "corpus_both_scenarios_wall_s": corpus_wall,
           "corpus_both_scenarios_single_worker_s": runs["corpus|i"]["forecast"]["single_worker_s"] + runs["corpus|ii"]["forecast"]["single_worker_s"],
           "human_both_scenarios_single_worker_s": runs["human|i"]["forecast"]["single_worker_s"] + runs["human|ii"]["forecast"]["single_worker_s"],
           "corpus_cap_s": CORPUS_CAP_S, "corpus_reduced_to_500": cut,
           "summary_s_for_40_datasets": summary_s, "bench_summary_sha256": {"json": sha(Path(work) / "BENCH-SUMMARY.json"), "md": sha(Path(work) / "BENCH-SUMMARY.md")},
           "human_both_scenarios_wall_s": runs["human|i"]["forecast"]["wall_s"] + runs["human|ii"]["forecast"]["wall_s"],
           "elapsed_s": time.time() - t0, "driver_sha256": D.DRIVER_SHA, "tests_sha256": sha(HERE),
           "hardware": {"cpus": os.cpu_count(), "cpu": _cpu(), "mem_kb": _mem()}}
    Path(out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: {"mean": v["per_dataset_mean_s"], "eff": v["parallel_efficiency"], "forecast": v["forecast"]} for k, v in runs.items()}, indent=1))
    print("corpus both scenarios (s):", corpus_wall, "cut:", cut)
    return res


def _cpu():
    try:
        return [l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")][0]
    except Exception:
        return None


def _mem():
    try:
        return int([l.split()[1] for l in open("/proc/meminfo") if l.startswith("MemTotal")][0])
    except Exception:
        return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["deterministic", "planted", "null", "bench"])
    ap.add_argument("--code-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    Path(a.work).mkdir(parents=True, exist_ok=True)
    if a.what == "deterministic":
        r = deterministic(a.code_dir, a.work, a.out)
        sys.exit(0 if r["n_pass"] == r["n"] else 1)
    elif a.what == "planted":
        planted(a.code_dir, a.work, a.out, a.workers)
    elif a.what == "bench":
        bench(a.code_dir, a.work, a.out, a.workers)
    else:
        null_rates(a.code_dir, a.work, a.out, a.workers)
