#!/usr/bin/env python3
"""n1_posthoc2_tests.py — N1: validation and benchmark of n1_posthoc2.py (items C, D and E) on synthetic data only, run
before the declaration record exists. Nothing here reads a study outcome: the synthetic studies come from the registered
harness n1_synth.py (sha256 7b71747f...), which reuses only design information, and the label-source overlay and the
three synthetic label exports are written here from the synthetic answers.

  deterministic   the fixed checks that must pass (loaders; the batched bridge against separate registered calls; the
                  job filter; the retry path; every generator: rows, units, filters, undefined markers, seeds, truth,
                  exact zero means and non-exchangeability; the rater-label process on the observed-design overlay; the
                  sign-flip test; Holm; the envelope and verdict logic, the lazy check (a) phase with a stub; the support
                  checks (a), (b), (c) against the registered script's run with --glmm-boot --nb 200 and n1_robustness.py
                  on the same synthetic study; D end to end with an independent recomputation; E's generators, effects,
                  power summary and bounds; the reproduction on the synthetic registered run; 1 vs 4 workers and a
                  resumed run give identical outputs; the real-data guard)
  bench           timing on synthetic data at the intended concurrency: C per family and configuration (one worker, then
                  four), check (a) at 10,000 refits (one human-layer and one corpus-layer model job), E per part, D, the
                  reproduction; the forecast inputs of the declaration

Usage:  python n1_posthoc2_tests.py deterministic|bench --code-dir DIR --work DIR --out FILE
"""
import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import argparse, copy, hashlib, importlib.util, itertools, json, math, shutil, subprocess, sys, time
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
spec = importlib.util.spec_from_file_location("n1_posthoc2", HERE.with_name("n1_posthoc2.py"))
P2 = importlib.util.module_from_spec(spec)
sys.modules["n1_posthoc2"] = P2
spec.loader.exec_module(P2)
D = P2.D
SYNTH_SHA = "7b71747f"


class Checks:
    def __init__(self):
        self.items = []

    def ok(self, name, cond, detail=None):
        self.items.append({"check": name, "pass": bool(cond), **({"detail": detail} if detail is not None and not cond else {})})
        print(("PASS " if cond else "FAIL ") + name + ("" if cond or detail is None else f"  {str(detail)[:400]}"), flush=True)


def make_synth(code_dir, work, seed):
    out = Path(work) / f"syn{seed}"
    if (out / "SYNTHETIC").exists():
        return out
    assert sha(Path(code_dir) / "n1_synth.py").startswith(SYNTH_SHA)
    subprocess.run([sys.executable, str(Path(code_dir) / "n1_synth.py"), str(out), "--seed", str(seed)], check=True, capture_output=True)
    (out / "SYNTHETIC").write_text("synthetic study made by n1_synth.py for the validation of n1_posthoc2.py\n")
    return out


def overlay(src, dst, seed=11):
    """a copy of a synthetic study with the expansion's label design: every query x arm group of 12 answers assigned by the
    expansion's rule (a model's two repetitions to two different raters, 4/4/4), 303 answers made triple-rated
    (consensus-3) and 38 given a validation-round consensus (bl 13, en 11, bn 10, bl_translit 4); the three label exports
    of the 303, whose majority reproduces each answer's brands and prices (one rater exact, one drops an entry, one adds
    one, the roles drawn per answer)"""
    src, dst = Path(src), Path(dst)
    if (dst / "SYNTHETIC").exists():
        return dst
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("ANALYSIS-*", "tmp*"))
    rng = np.random.default_rng(seed)
    rows = [json.loads(l) for l in open(dst / "EXPANSION-ANALYSIS-SET-v2.jsonl", encoding="utf-8")]
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        groups[(r["query_id"], r["arm"])].append(i)
    pairs = [("R1", "R2"), ("R1", "R3"), ("R2", "R3")]
    for g, idx in sorted(groups.items()):
        bym = defaultdict(list)
        for i in idx:
            bym[rows[i]["model_id"]].append(i)
        assert len(bym) == 6 and all(len(v) == 2 for v in bym.values())
        types = [pairs[j // 2] for j in range(6)]
        for mi, t in zip(sorted(bym), rng.permutation(6)):
            pr = list(types[t])
            if rng.random() < 0.5:
                pr = pr[::-1]
            for i, rt in zip(sorted(bym[mi], key=lambda i: rows[i]["rep"]), pr):
                rows[i]["label_source"], rows[i]["labelled_by"] = "single", rt
    order = [int(i) for i in rng.permutation(len(rows))]
    ov = order[:303]
    rest = order[303:]
    r2 = []
    for arm, n in (("bl", 13), ("en", 11), ("bn", 10), ("bl_translit", 4)):
        r2 += [i for i in rest if rows[i]["arm"] == arm][:n]
    tbl = {r["canonical_id"]: r["display_name"] for r in __import__("csv").DictReader(open(dst / "brand_aliases.expansion.csv", encoding="utf-8"))}
    allb = sorted(tbl)
    exports = {rt: [] for rt in P2.RATERS}
    norm = lambda x: int(float(x)) if float(x) == int(float(x)) else float(x)
    for j, i in enumerate(ov):
        r = rows[i]
        r["label_source"], r["labelled_by"], r["pid"] = "consensus-3", "R1+R2+R3", f"P{j:04d}"
        assert all(c in ("BDT", "USD", "other", "unstated") for _, c in r["prices"])
        r["prices"] = sorted([[float(a_), c_] for a_, c_ in {(float(a), c) for a, c in r["prices"]}], key=lambda p: (p[1], norm(p[0])))
        br = list(r["brands"])
        pl = [f"{norm(a)} {c}" for a, c in r["prices"]]
        roles = [P2.RATERS[x] for x in rng.permutation(3)]          # exact, drop, add
        extra_b = next((b for b in allb if b not in br and b.split("-")[0] == (br[0].split("-")[0] if br else "c0")), allb[0])
        for rt in P2.RATERS:
            if rt == roles[0]:
                b, p = br, pl
            elif rt == roles[1]:
                b, p = br[:-1], pl[:-1]
            else:
                b, p = br + [extra_b], pl + ["999 BDT"]
            exports[rt].append({"pid": r["pid"], "answer_language": r["answer_language"], "refused": r["refused"],
                                "brands": [tbl[x] for x in b], "prices": p, "recommended": [], "retailers": []})
    for j, i in enumerate(r2):
        rows[i]["label_source"], rows[i]["labelled_by"] = "round2-consensus", f"round2:M{j:03d}"
    with open(dst / "EXPANSION-ANALYSIS-SET-v2.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for rt in P2.RATERS:
        json.dump({"task": "N1 labelling expansion round", "rater": rt, "labels": exports[rt]},
                  open(dst / f"LABEL-EXPANSION-{rt}-labels.json", "w", encoding="utf-8"))
    (dst / "SYNTHETIC").write_text("synthetic study made by n1_synth.py with a label-design overlay, for the validation of n1_posthoc2.py\n")
    return dst


def strip_labels(res):
    if isinstance(res, dict):
        return {k: strip_labels(v) for k, v in res.items() if k != "label"}
    if isinstance(res, list):
        return [strip_labels(v) for v in res]
    return res


# ============================================================================================ deterministic checks
def deterministic(code_dir, work, out):
    C = Checks()
    t0 = time.time()
    code_dir, work = Path(code_dir), Path(work)
    s1 = make_synth(code_dir, work, 1)
    if not (s1 / "ANALYSIS-ROBUSTNESS.md").exists():
        raise SystemExit("run n1_analysis.py --synthetic --glmm-boot --nb 200 and n1_robustness.py on the synthetic study first")
    so = overlay(s1, work / "syn1o")
    # ---- 1 loaders
    old = set(D.WL_FUNCS)
    ns, state = P2.load_ns(code_dir)
    C.ok("loader: machine_layer added to record 53's whitelist in memory only (the module's set restored)", D.WL_FUNCS == old and "machine_layer" in ns)
    C.ok("loader: the registered pipeline and argument parsing not executed", not (D.FORBIDDEN & set(ns)))
    S = P2.Setup2(so, code_dir, work / "tmp_det", synthetic=True, machine=True)
    ns = S.ns
    OV = P2.load_overlap_defs(code_dir, so, ns)
    C.ok("overlap loader: exactly the whitelisted definitions (no module-level names such as E, aset, ov, G, A)",
         set(P2.OV_NAMES) <= set(OV) and not ({"E", "aset", "ov", "G", "A", "EXTENDED", "res"} & set(OV)))
    # ---- 2 batched bridge against separate registered calls, the job filter and the retry path
    for fam in P2.FAM_ORDER:
        layer = D.fam_def(ns, fam)[0]
        g = P2.Generator(S, fam, "C0")
        ds = [g.draw(np.random.default_rng(100 + j)) for j in range(3)]
        fn = P2.registered_fn(ns, fam, S.b0s[layer])
        bat = P2.batched(ns, fn, ds)
        sep = [D.registered_family(ns, fam, r, S.b0s[layer]) for r in ds]
        D.clean_tmp(ns)
        C.ok(f"bridge: {fam}: three data sets batched give exactly the separate registered calls' results", strip_labels(bat) == strip_labels(sep))
        if fam != "RQ1_excess_divergence":
            m = ns["MODELS"][2]
            one = P2.batched(ns, fn, ds[:1], keep=lambda k, jid: jid == m)[0]
            C.ok(f"bridge: {fam}: a fit filtered to one model equals that model's result in the full fit",
                 strip_labels(one["results"][m]) == strip_labels(sep[0]["results"][m]))
    real = ns["glmm"]
    calls = [0]

    def flaky(jobs):
        calls[0] += 1
        if calls[0] == 1:
            raise SystemExit("n1_glmm.R failed: simulated")
        return real(jobs)
    ns["glmm"] = flaky
    errs = []
    try:
        g = P2.Generator(S, "RQ4_price_mention", "C0")
        ds = [g.draw(np.random.default_rng(7))]
        r1 = P2.batched(ns, P2.registered_fn(ns, "RQ4_price_mention", S.b0s["human"]), ds, errors=errs)
    finally:
        ns["glmm"] = real
    r0 = D.registered_family(ns, "RQ4_price_mention", ds[0], S.b0s["human"])
    C.ok("bridge: a failed R call is logged and retried once, with the same result", len(errs) == 1 and strip_labels(r1[0]) == strip_labels(r0), errs)
    # ---- 3 generators
    for fam in P2.FAM_ORDER:
        base = D.fam_rows(fam, S.base)
        for cfg in P2.CONFIGS[fam]:
            g = P2.Generator(S, fam, cfg)
            d1 = g.draw(np.random.default_rng(stream_t(fam, cfg, 1)))
            d1b = g.draw(np.random.default_rng(stream_t(fam, cfg, 1)))
            C.ok(f"generator {fam} {cfg}: same seed, same data set", d1 == d1b)
            same_design = [(r["key"], r["model"], r["query"], r["rep"]) for r in d1] == [(r["key"], r["model"], r["query"], r["rep"]) for r in base]
            if cfg == "ii":
                ref = D.fam_rows(fam, D.null_dataset(ns, D.fam_def(ns, fam)[0], "ii", S.base, np.random.default_rng(stream_t(fam, cfg, 1))))
                C.ok(f"generator {fam} ii: record 53's arm-block generator, unchanged", d1 == ref)
                continue
            C.ok(f"generator {fam} {cfg}: rows, keys, models, queries, repetitions and arms as observed",
                 same_design and [r["arm"] for r in d1] == [r["arm"] for r in base])
            if fam != "RQ1_excess_divergence":
                u0 = [P2.fam_units(ns, fam, r)[1] for r in base]
                u1 = [P2.fam_units(ns, fam, r)[1] for r in d1]
                C.ok(f"generator {fam} {cfg}: units per answer (and so every undefined marker) as observed", u0 == u1)
            filt = {"RQ5_reversion": ns["nonref_nondeg"], "RQ5_refusal": ns["nondeg"]}.get(fam, ns["P"])
            C.ok(f"generator {fam} {cfg}: every simulated row passes the family's registered filter", all(filt(r) for r in d1))
            if fam == "RQ1_excess_divergence":
                cnt0 = Counter((r["model"], r["query"], r["arm"]) for r in base)
                cnt1 = Counter((r["model"], r["query"], r["arm"]) for r in d1)
                C.ok(f"generator {fam} {cfg}: answers per cell (eligibility) as observed", cnt0 == cnt1)
            tr = g.truth
            if cfg in P2.COMPLETE:
                C.ok(f"generator {fam} {cfg}: every hypothesis true", all(tr.values()))
            elif cfg == "P1":
                C.ok(f"generator {fam} P1: bn-bl true for every model", all(tr[f"{m}|bn-bl"] for m in ns["MODELS"]))
            elif cfg == "P2":
                C.ok(f"generator {fam} P2: every contrast of the three models without effects true",
                     all(tr[k] for k in tr if k.split("|")[0] not in P2.MODELS_A))
        if fam != "RQ1_excess_divergence":
            g = P2.Generator(S, fam, "C2")
            pm = {(r["model"], r["query"], r["arm"]): p for r, p in zip(g.rows, g.p)}
            shifted = sum(1 for m, q in {(r["model"], r["query"]) for r in g.rows}
                          if len({pm.get((m, q, a)) for a in g.st.arms if (m, q, a) in pm}) > 1)
            C.ok(f"generator {fam} C2: queries with non-exchangeable arms exist and every expected contrast mean is exactly 0",
                 shifted > 0 and all(abs(v) <= 1e-12 for v in g.mu.values()), {"shifted": shifted, "max": max(abs(v) for v in g.mu.values())})
            # Monte Carlo: the realised mean of the estimates over 300 data sets is within 4 MC SE of 0 (C2) and of mu (P1)
            for cfg in ("C2", "P1") if fam != "RQ5_reversion" else ("C2", "P2"):
                g = P2.Generator(S, fam, cfg)
                layer = D.fam_def(ns, fam)[0]
                k = D.keys_of(ns, fam)[0]
                m, con = k.split("|")
                vals = []
                for j in range(300):
                    rows = g.draw(np.random.default_rng(stream_t(fam, cfg, 1000 + j)))
                    cv = D.fam_cells(ns, fam, rows)
                    vals.append(D.estimate_of(D.per_query(ns, fam, cv, S.frames[layer], m, *con.split("-"))))
                se = np.std(vals, ddof=1) / math.sqrt(len(vals))
                C.ok(f"generator {fam} {cfg}: the mean estimate of {k} over 300 data sets agrees with its expectation {g.mu[k]:+.4f}",
                     abs(np.mean(vals) - g.mu[k]) <= 4 * se + 1e-12, {"mean": float(np.mean(vals)), "se": float(se)})
    # ---- 4 the rater-label process on the overlay design
    dc = P2.design_check(S)
    C.ok("design overlay: sources 303 / 38 / the rest single; no cell with both repetitions by one rater",
         dc["sources"].get("consensus-3") == 303 and dc["sources"].get("round2-consensus") == 38 and dc["cells_with_two_single_labels_by_one_rater"] == 0, dc)
    g = P2.Generator(S, "RQ4_price_mention", "R_real")
    src_real = g.sources(np.random.default_rng(1))
    exp = [("single", S.design[r["key"]]["by"]) if S.design[r["key"]]["source"] == "single" else
           (("overlap", None) if S.design[r["key"]]["source"] == "consensus-3" else ("round2", None)) for r in g.rows]
    C.ok("rater process R_real: every answer keeps its realized label source and rater", src_real == exp)
    g = P2.Generator(S, "RQ4_price_mention", "R_stress")
    asg, ov = g.assign(np.random.default_rng(11))
    asg2, ov2 = g.assign(np.random.default_rng(11))
    asg3, ov3 = g.assign(np.random.default_rng(12))
    cells = defaultdict(list)
    grp = defaultdict(Counter)
    for k_, rt in asg.items():
        d_ = S.design[k_]
        if k_ not in ov:
            cells[(d_["model"], d_["query"], d_["arm"])].append(rt)
        grp[(d_["query"], d_["arm"])][rt] += 1
    full = [gg for gg, ms in g.groups.items() if len(ms) == 6 and all(len(v) == 2 for v in ms.values())]
    C.ok("rater process R_obs/R_stress: the re-drawn assignment follows its rule (a model's two answers of a query and arm never to one "
         "rater; every full group 4/4/4; every other group as balanced as its answers allow); the overlap has the realized size; the "
         "38 validation-round answers keep their source; same seed same draw, another seed another",
         all(len(v) == len(set(v)) for v in cells.values()) and all(sorted(grp[gg].values()) == [4, 4, 4] for gg in full)
         and all(max(c_.values()) - min(c_.get(x, 0) for x in P2.RATERS) <= 1 for c_ in grp.values() if sum(c_.values()) % 3 == 0 or True)
         and len(ov) == 303 and not (ov & g.round2) and len(g.round2) == 38 and (asg, ov) == (asg2, ov2) and (asg, ov) != (asg3, ov3),
         {"full": len(full), "groups": len(g.groups)})
    kinds = Counter(k_ for k_, _ in g.sources(np.random.default_rng(3)))
    C.ok("rater process R_stress: the analysis rows get single, overlap and round-2 sources in every data set", set(kinds) == {"single", "overlap", "round2"}, kinds)
    rng = np.random.default_rng(5)
    r0 = g.rows[0]
    lab1 = [g._label(rng, "R1", 1, r0) for _ in range(200)] + [g._label(rng, "R1", 0, r0) for _ in range(200)]
    C.ok("rater process: R1 (no distortion) returns the latent label", lab1 == [1] * 200 + [0] * 200)
    fp = np.mean([g._label(rng, "R2", 0, r0) for _ in range(20000)])
    C.ok("rater process: R2's false-positive rate for price mention as declared (0.06 in R_stress)", abs(fp - 0.06) < 0.006, fp)
    C.ok("rater process: consensus = majority of three", g._consensus([1, 1, 0]) == 1 and g._consensus([1, 0, 0]) == 0)
    g1 = P2.Generator(S, "RQ1_excess_divergence", "R_obs")
    C.ok("rater process (sets): consensus keeps entities listed by at least two", g1._consensus([("a", "b"), ("a",), ("b", "c")]) == ("a", "b"))
    g2 = P2.Generator(S, "RQ2_local_share", "R_obs")
    C.ok("rater process (shares): per-mention majority", g2._consensus([[1, 0, 1], [1, 1, 0], [0, 0, 1]]) == [1, 0, 1])
    # ---- 5 sign-flip test
    d = {f"q{i}": v for i, v in enumerate([0.3, -0.1, 0.25, 0.4, 0.05])}
    ex = np.mean([abs(sum(s * v for s, v in zip(sg, d.values()))) >= abs(sum(d.values())) - 1e-12 for sg in itertools.product((1, -1), repeat=5)])
    sfp = P2.signflip(d, 1, B=200000)["p"]
    C.ok("sign-flip: Monte Carlo P agrees with the exhaustive P of a five-query case", abs(sfp - ex) < 0.005, (sfp, ex))
    rng = np.random.default_rng(3)
    rej = np.mean([P2.signflip({f"q{i}": x for i, x in enumerate(rng.normal(size=20))}, j, B=2000)["p"] <= 0.05 for j in range(1000)])
    C.ok("sign-flip: rejection rate at .05 under a symmetric null within Monte Carlo error", abs(rej - 0.05) < 0.02, rej)
    C.ok("sign-flip: all-zero differences give no test and P = 1", P2.signflip({"a": 0.0, "b": 0.0}, 1)["p"] == 1.0)
    # ---- 6 Holm
    from statsmodels.stats.multitest import multipletests
    ps = {f"k{i}": p for i, p in enumerate([0.001, 0.01, 0.02, 0.2, 0.004])}
    rj = multipletests(list(ps.values()), alpha=0.05, method="holm")[0]
    C.ok("Holm: the registered holm() decisions", P2.holm_rej(ns, ps) == {k for k, r_ in zip(ps, rj) if r_})
    # ---- 7 envelopes, verdicts and the lazy check (a) phase
    keys = [f"m{i}|a-b" for i in range(3)]
    truth = {k: True for k in keys}
    mk = lambda k, e0, meth="g", chk=None, sf=None: {"k": k, "e0": e0, "rej": {"sf": sf if sf is not None else e0}, "chk": chk or {},
                                                     "c": [[0.1, 0.01, meth, 0.01, 0.01, 0.01] for _ in keys]}
    lines = [mk(0, []), mk(1, [0], chk={"0": {"b": [0.01, True, "g"]}}), mk(2, [1], chk={"1": {"b": [0.2, False, "g"]}}),
             mk(3, [2], meth="f"), mk(4, [0], chk={"0": {"b": [0.01, True, "g"]}}, sf=[])]
    st = P2.classify("RQ2_local_share", keys, truth, lines, {}, False)
    C.ok("envelopes: E0 counts data sets with a three-test rejection on a true null; E1 applies (b); the rule needs (a) for GLMM contrasts",
         st["E0"] == 4 and st["E1"] == 3 and st["rule_known"] == 1 and st["pending"] == [(1, ["m0"]), (4, ["m0"])], st)
    st2 = P2.classify("RQ2_local_share", keys, truth, lines, {(1, "m0|a-b"): {"supported": True}, (4, "m0|a-b"): {"supported": False}}, False)
    sts = P2.classify("RQ2_local_share", keys, truth, lines, {}, True)
    C.ok("envelopes: check (a) results enter the rule; A* adds the sign-flip gate", st2["rule_known"] == 2 and not st2["pending"] and sts["E0"] == 3, (st2, sts))
    T = P2.pass_max(1000)
    C.ok("acceptance: pass_max(1000) is the largest count whose Wilson lower limit is at most .05",
         P2.wilson(T, 1000)[0] <= 0.05 < P2.wilson(T + 1, 1000)[0], T)
    C.ok("verdict: E0 at the threshold passes; above it with E1 at it passes by E1; bounds decide the rule",
         P2.verdict({"n": 1000, "E0": T, "E1": T, "rule_known": 0, "pending": []}) == ("pass", "E0")
         and P2.verdict({"n": 1000, "E0": T + 5, "E1": T, "rule_known": 0, "pending": []}) == ("pass", "E1")
         and P2.verdict({"n": 1000, "E0": T + 5, "E1": T + 5, "rule_known": T + 1, "pending": []}) == ("fail", "rule")
         and P2.verdict({"n": 1000, "E0": T + 5, "E1": T + 5, "rule_known": T - 1, "pending": [(0, [])] * 3}) == ("undetermined", "rule"))
    lazy_ok = lazy_phase_test(S, work)
    C.ok("check (a) phase: pending data sets computed in the seeded order until the verdict is determined; the budget stops it", lazy_ok[0], lazy_ok[1])
    # ---- 8 the support checks against the registered script and n1_robustness.py on synthetic study 1
    R = json.loads((s1 / "ANALYSIS-RESULTS.json").read_text(encoding="utf-8"))
    rob = D.parse_robustness((s1 / "ANALYSIS-ROBUSTNESS.md").read_text(encoding="utf-8"))
    S1 = P2.Setup2(s1, code_dir, work / "tmp_det1", synthetic=True, machine=True)
    nb = R["meta"]["bootstrap"]["resamples"]
    agree = {"a": [0, 0], "b": [0, 0], "c": [0, 0]}
    bad = []
    for fam in P2.FAM_ORDER:
        rows = D.fam_rows(fam, S1.base)
        keys = D.keys_of(S1.ns, fam)
        est = {k: (R["primary"][fam]["results"][k].get("mean_delta") if fam == "RQ1_excess_divergence"
                   else R["primary"][fam]["results"][k.split("|")[0]]["contrasts"][k.split("|")[1]]["diff"]) for k in keys}
        rej = [k for k in keys if R["holm"][fam][k]["reject"]]
        if fam == "RQ1_excess_divergence":
            pr = S1.ns["setdiv_perm"](rows, "brands", S1.ns["jaccard"], S1.ns["C3"], S1.ns["P"], 20260930, nb, "check (c)")
            for k in rej:
                x = pr["results"][k]
                mine = x["p"] < 0.05 and (x["mean_delta"] or 0) * (est[k] or 0) > 0
                agree["c"][0] += 1; agree["c"][1] += mine == (rob[fam][k]["c"] == "supported")
                if mine != (rob[fam][k]["c"] == "supported"):
                    bad.append((fam, k, "c", mine, rob[fam][k]))
            continue
        glmm = [k for k in rej if R["primary"][fam]["results"][k.split("|")[0]]["contrasts"][k.split("|")[1]]["test"]["method"] == "glmm_wald"]
        if not glmm:
            continue
        line = {"chk": {}}
        P2.check_b(S1, fam, [(line, rows, glmm, est)])
        models = sorted({k.split("|")[0] for k in glmm})
        A_ = P2.check_a_rows(S1, fam, rows, models, nb=nb)
        for k in glmm:
            mine_b = line["chk"][str(keys.index(k))]["b"][1]
            agree["b"][0] += 1; agree["b"][1] += mine_b == (rob[fam][k]["b"] == "supported")
            mine_a = A_[k]["supported"]
            agree["a"][0] += 1; agree["a"][1] += mine_a == (rob[fam][k]["a"] == "supported")
            stored = R["primary"][fam]["results"][k.split("|")[0]]["contrasts"][k.split("|")[1]]["log_odds"]["boot_ci"]
            if mine_b != (rob[fam][k]["b"] == "supported") or mine_a != (rob[fam][k]["a"] == "supported") or A_[k]["boot_ci"] != stored:
                bad.append((fam, k, mine_a, mine_b, rob[fam][k], A_[k]["boot_ci"], stored))
    C.ok(f"support checks: (a), (b), (c) recomputed on the synthetic study give n1_robustness.py's classification for every Holm-rejected contrast, "
         f"and (a)'s bootstrap intervals equal the registered run's ({agree})", not bad and all(v[0] > 0 and v[0] == v[1] for v in agree.values()), bad[:4])
    # ---- 9 reproduction on the synthetic registered run (record 53's reproduction and the F.10 results)
    rep = P2.reproduce2(S1, R)
    C.ok("reproduction: record 53's reproduction and the 48 F.10 results through the batched bridge", rep["ok"] and rep["f10"]["checked"] == 48,
         {"r53": rep["record53"]["ok"], "f10": rep["f10"]["mismatch"][:3]})
    # ---- 10 D end to end on the overlay, with an independent recomputation of one cell and one agreement rate
    Dres = P2.d_compute(S)
    ind = independent_d(so, S)
    got = Dres["outcome"]["R2"]["price_mention|strict"]["cells"][ind["cell"]]["discrepancy"]["estimate"]
    got2 = Dres["agreement"]["R1-R3"]["price_sets_identical"]["estimate"]
    C.ok("D: runs end to end (identity of the raw exports and the consensus) and matches an independent recomputation",
         abs(got - ind["disc"]) < 1e-12 and abs(got2 - ind["ident"]) < 1e-12, (got, ind["disc"], got2, ind["ident"]))
    sys.path.insert(0, str(code_dir / "exploratory"))
    import n1_review_common as RC
    fr0, fr1 = RC.Frame(["a", "b", "c", "d"], 20261021, 500), P2.Frame(["a", "b", "c", "d"], 20261021, 500)
    pq = {"a": 0.1, "c": 0.5, "d": -0.2}
    C.ok("D: the resampling frame reproduces records 47 and 50's Frame (replicates and interval)",
         np.array_equal(fr0.reps(pq), fr1.reps(pq), equal_nan=True) and RC.Frame.ci(fr0.reps(pq), 3)[0] == P2.Frame.ci(fr1.reps(pq), 3))
    # ---- 11 E
    specs = P2.e_specs(S)
    C.ok("E: 12 refusal generators (18 contrasts), 24 + 24 F.10 share and 12 + 12 divergence contrasts",
         sum(s["part"] == "refusal" for s in specs) == 12 and sum(len(s["cons"]) for s in specs if s["part"] == "refusal") == 18
         and sum(len(s["cons"]) for s in specs if s["part"].startswith("f10_share")) == 24 and sum(len(s["cons"]) for s in specs if s["part"].startswith("f10_delta")) == 24)
    ok_e, det = True, []
    for s in specs[::5]:
        gE = P2.EGen(S, s)
        d0 = gE.draw(np.random.default_rng(1), 0.0)
        same = [(r["key"], r["arm"]) for r in d0] == [(r["key"], r["arm"]) for r in gE.rows]
        e0 = all(gE.effect(0.0, c) in (0.0, None) for c in s["cons"])
        ok_e &= same and e0
        if not (same and e0):
            det.append(s)
    C.ok("E: generators keep the rows and give zero effect at the null grid value", ok_e, det[:2])
    sd = next(s for s in specs if s["part"] == "f10_delta_machine")
    gE = P2.EGen(S, sd)
    con = sd["cons"][0]
    th = 0.7
    vals = []
    for j in range(200):
        rr = S.ns["setdiv"](gE.draw(np.random.default_rng(500 + j), th), "brands", S.ns["jaccard"], P2.C10, S.ns["P"], S.b0_f10["machine"], "t")
        vals.append(rr["results"][f"{sd['model']}|{con[0]}-{con[1]}"]["mean_delta"])
    se = np.std(vals, ddof=1) / math.sqrt(len(vals))
    C.ok("E: the divergence alternative's expected mean Delta is theta^2 x mean(D^2/2) (Monte Carlo, 200 data sets)",
         abs(np.mean(vals) - gE.effect(th, con)) <= 4 * se, (float(np.mean(vals)), gE.effect(th, con), float(se)))
    C.ok("E: isotonic fit", P2.isotonic([0.1, 0.3, 0.2, 0.9], [1, 1, 1, 1]) == [0.1, 0.25, 0.25, 0.9])
    from scipy.stats import beta
    C.ok("E: Clopper-Pearson one-sided upper limits (0 of 250: 1 - 0.05^(1/250); 3 of 250)",
         abs(P2.cp_upper(0, 250, 0.95) - (1 - 0.05 ** (1 / 250))) < 1e-12 and abs(P2.cp_upper(3, 250, 0.95) - beta.ppf(0.95, 4, 247)) < 1e-12)
    b = P2.e_bounds(S)
    C.ok("E: bounds for 18 cells and 18 contrasts; the cluster-aware limit is at least the answer-level benchmark",
         len(b["cells"]) == 18 and len(b["contrasts"]) == 18 and all(c["upper95_query_level"] >= c["upper95_answer_level_benchmark"] - 1e-12 for c in b["cells"]))
    # ---- 12 1 vs 4 workers, and a resumed run
    w1, w4, wr = work / "c_w1", work / "c_w4", work / "c_wr"
    for p in (w1, w4, wr):
        if p.exists():
            shutil.rmtree(p)
    fams = ["RQ1_excess_divergence", "RQ4_price_mention"]
    P2.c_run(S, fams, w1, 1, work / "tmp_w1", n_override=6)
    P2.c_run(S, fams, w4, 4, work / "tmp_w4", n_override=6)
    P2.c_run(S, fams, wr, 4, work / "tmp_wr", n_override=3)
    P2.c_run(S, fams, wr, 4, work / "tmp_wr", n_override=6)
    same, resumed = True, True
    for fam in fams:
        for cfg in P2.CONFIGS[fam]:
            a1, a4, ar = (P2.load_c(p, fam, cfg)[1] for p in (w1, w4, wr))
            same &= a1 == a4 and len(a1) == 6
            resumed &= a1 == ar
    C.ok("C: one worker and four workers give identical outputs", same)
    C.ok("C: a run resumed after 3 of 6 data sets gives the uninterrupted run's outputs", resumed)
    Es = work / "e_w"
    if Es.exists():
        shutil.rmtree(Es)
    P2.e_run(S, Es, 4, work / "tmp_e", n_rep=4, parts=["refusal", "f10_delta_human"], grid_points=[0, 5])
    summ = P2.e_summary(S, P2.read_jsonl(Es / "E-POWER.jsonl"))
    C.ok("E: a short run and its summary complete (66 contrasts)", len(summ) == 66 and all(x["grid"][0]["n"] in (0, 4) for x in summ))
    # ---- 13 the real-data guard
    try:
        P2.verify_real2(code_dir, code_dir, code_dir.parent / "registration" / "prereg.md")
        guard = False
    except SystemExit as e:
        guard = "declaration record" in str(e) or "not the file" in str(e)
        gmsg = str(e)
    C.ok("guard: real data refused while the registration holds no declaration record quoting this driver", guard, locals().get("gmsg"))
    try:
        P2.Setup2(s1.parent, code_dir, work / "tmp_g", synthetic=True)
        g2 = False
    except SystemExit:
        g2 = True
    C.ok("guard: synthetic mode refuses a root without the SYNTHETIC marker", g2)
    res = {"driver_sha256": P2.DRIVER_SHA, "tests_sha256": sha(HERE), "checks": C.items, "n_pass": sum(c["pass"] for c in C.items),
           "n": len(C.items), "elapsed_s": time.time() - t0, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    Path(out).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"{res['n_pass']}/{res['n']} checks passed in {res['elapsed_s']:.0f} s")
    if res["n_pass"] != res["n"]:
        raise SystemExit(1)


def stream_t(fam, cfg, j):
    return P2.stream(99, P2.FAM_ORDER.index(fam), P2.CFG_INDEX[cfg], j)


def lazy_phase_test(S, work):
    """the check (a) phase on hand-made main-phase files with a stub for check (a): 40 data sets of which 30 need check
    (a) on one GLMM contrast; the stub supports odd k; with pass_max(40) = 5 the verdict needs the computations until
    more than 5 conclusions are known, in the seeded order; a zero budget stops the phase with the verdict undetermined"""
    d = Path(work) / "lazy"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    fam, cfg = "RQ2_local_share", "C0"
    keys = D.keys_of(S.ns, fam)
    truth = {k: True for k in keys}
    (d / f"C-{fam}-{cfg}.meta.json").write_text(json.dumps({"truth": truth, "meta": {}, "keys": keys}), encoding="utf-8")
    for c in P2.CONFIGS[fam]:
        if c != cfg:
            (d / f"C-{fam}-{c}.meta.json").write_text(json.dumps({"truth": truth, "meta": {}, "keys": keys}), encoding="utf-8")
            (d / f"C-{fam}-{c}.jsonl").write_text("", encoding="utf-8")
    with open(d / f"C-{fam}-{cfg}.jsonl", "w", encoding="utf-8") as f:
        for k in range(40):
            e0 = [0] if k < 30 else []
            f.write(json.dumps({"k": k, "e0": e0, "rej": {"reg": e0, "me": e0, "rz": e0, "sf": e0}, "chk": {"0": {"b": [0.01, True, "g"]}} if e0 else {},
                                "c": [[0.1, 0.01, "g", 0.01, 0.01, 0.01] for _ in keys]}) + "\n")
    calls = []
    orig = P2.check_a

    def stub(S_, fam_, cfg_, k, models, gen=None, nb=0):
        calls.append(k)
        return {"fam": fam_, "cfg": cfg_, "k": k, "models": models, "seconds": 0.0, "nb": nb,
                "contrasts": {f"{m}|{a}-{b}": {"supported": k % 2 == 1} for m in models for a, b in D.fam_def(S_.ns, fam_)[2]}}
    P2.check_a = stub
    try:
        r0 = P2.c_checks(S, d, [fam], budget_s=0.0)
        stopped = bool(r0["stopped_by_budget"]) and not calls
        P2.c_checks(S, d, [fam], budget_s=1e9)
    finally:
        P2.check_a = orig
    meta, lines = P2.load_c(d, fam, cfg)
    st = P2.classify(fam, keys, truth, lines, {(k, kk): v for (f_, c_, k, kk), v in P2.a_done(d).items() if c_ == cfg}, False)
    v = P2.verdict(st)
    ok = stopped and v == ("fail", "rule") and st["rule_known"] == P2.pass_max(40) + 1 and len(calls) == len(set(calls))
    return ok, {"calls": len(calls), "verdict": v, "known": st["rule_known"], "stopped": stopped}


def independent_d(root, S):
    """a second, plain computation of one D value (R2 against the other two, strict, price mention, one model x arm cell)
    and one agreement rate (R1-R3 identical price sets), from the exports"""
    import csv, re, unicodedata
    ex = {rt: {r["pid"]: r for r in json.load(open(Path(root) / f"LABEL-EXPANSION-{rt}-labels.json", encoding="utf-8"))["labels"]} for rt in P2.RATERS}
    aset = [json.loads(l) for l in open(Path(root) / "EXPANSION-ANALYSIS-SET-v2.jsonl", encoding="utf-8")]
    ov = [r for r in aset if r["label_source"] == "consensus-3"]
    pset = lambda lines: {(float(x.split()[0]), x.split()[1]) for x in lines}
    m, a = S.ns["MODELS"][0], "bn"
    per = defaultdict(list)
    for r in ov:
        if r["model_id"] == m and r["arm"] == a and r["in_primary_set"]:
            h, o1, o2 = (pset(ex[rt][r["pid"]]["prices"]) for rt in ("R2", "R1", "R3"))
            per[r["query_id"]].append(int(bool(h)) - int(bool(o1 & o2)))
    disc = float(np.mean([np.mean(v) for v in per.values()]))
    ident = float(np.mean([pset(ex["R1"][r["pid"]]["prices"]) == pset(ex["R3"][r["pid"]]["prices"]) for r in ov]))
    return {"cell": f"{m}|{a}", "disc": disc, "ident": ident}


# ============================================================================================ benchmark
def bench(code_dir, work, out):
    code_dir, work = Path(code_dir), Path(work)
    s1 = make_synth(code_dir, work, 1)
    so = overlay(s1, work / "syn1o")
    S = P2.Setup2(so, code_dir, work / "tmp_bench", synthetic=True, machine=True)
    res = {"driver_sha256": P2.DRIVER_SHA, "tests_sha256": sha(HERE), "utc_start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "cpus": os.cpu_count(), "setup_s": S.setup_s, "C_one_worker": {}, "C_four_workers": {}, "check_a": {}, "E": {}}
    # C, one worker: one batch per family and configuration
    P2.G["S"] = S
    for fam in P2.FAM_ORDER:
        for cfg in P2.CONFIGS[fam]:
            g = P2.Generator(S, fam, cfg)
            P2.G["gens"] = {(fam, cfg): g}
            ks = list(range(P2.C_BATCH[fam]))
            t0 = time.time()
            lines, tm = P2.c_task(fam, cfg, ks)
            res["C_one_worker"][f"{fam}|{cfg}"] = {"per_data_set_s": (time.time() - t0) / len(ks), **{k: v for k, v in tm.items() if isinstance(v, (int, float))}}
            print(fam, cfg, round((time.time() - t0) / len(ks), 2), "s per data set", flush=True)
    # C, four workers: 2 batches per family and configuration through the pool
    d4 = work / "bench_c4"
    if d4.exists():
        shutil.rmtree(d4)
    n_per = {f: 2 * P2.C_BATCH[f] for f in P2.FAM_ORDER}
    total_sets = sum(n_per[f] * len(P2.CONFIGS[f]) for f in P2.FAM_ORDER)
    el = run_c_n(S, d4, work, n_per)
    t = P2.read_jsonl(d4 / "C-timing.jsonl")
    res["C_four_workers"] = {"elapsed_s": el, "data_sets": total_sets, "worker_s": sum(x["total"] for x in t),
                             "per_family_worker_s_per_data_set": {f: sum(x["total"] for x in t if x["fam"] == f) / (n_per[f] * len(P2.CONFIGS[f])) for f in P2.FAM_ORDER}}
    print("C four workers", res["C_four_workers"], flush=True)
    # check (a) at 10,000 refits: one human-layer and one corpus-layer model job (all four cores)
    for fam in ("RQ2_local_share", "RQ5_refusal"):
        g = P2.Generator(S, fam, "C0")
        m = S.ns["MODELS"][0]
        t0 = time.time()
        r = P2.check_a(S, fam, "C0", 0, [m], gen=g, nb=P2.N_BOOT_A)
        res["check_a"][fam] = {"seconds": time.time() - t0, "contrasts": r["contrasts"]}
        print("check (a)", fam, round(time.time() - t0), "s", flush=True)
    # E: one batch of E_BATCH data sets per part at a middle grid value, one worker
    specs = P2.e_specs(S)
    P2.G["especs"], P2.G["egens"] = specs, [P2.EGen(S, s) for s in specs]
    for part in ("refusal", "f10_share_human", "f10_share_machine", "f10_delta_human", "f10_delta_machine"):
        s = next(x for x in specs if x["part"] == part)
        t0 = time.time()
        lines, tm = P2.e_task(s["index"], 6, list(range(P2.E_BATCH)))
        res["E"][part] = {"per_data_set_s": (time.time() - t0) / P2.E_BATCH, **{k: v for k, v in tm.items() if isinstance(v, (int, float))}}
        print("E", part, round((time.time() - t0) / P2.E_BATCH, 3), "s per data set", flush=True)
    t0 = time.time()
    P2.d_compute(S)
    res["D_s"] = time.time() - t0
    S1 = P2.Setup2(s1, code_dir, work / "tmp_bench1", synthetic=True, machine=True)
    t0 = time.time()
    P2.reproduce2(S1, json.loads((s1 / "ANALYSIS-RESULTS.json").read_text(encoding="utf-8")))
    res["reproduce_s"] = time.time() - t0
    res["utc_end"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    Path(out).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")


def run_c_n(S, d4, work, n_per):
    """the pool with a per-family number of data sets (benchmark only)"""
    old = dict(P2.N_REP_C)
    try:
        P2.N_REP_C.update(n_per)
        el, _ = P2.c_run(S, P2.FAM_ORDER, d4, 4, work / "tmp_b4")
    finally:
        P2.N_REP_C.clear(); P2.N_REP_C.update(old)
    return el


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["deterministic", "bench"])
    ap.add_argument("--code-dir", required=True); ap.add_argument("--work", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    (deterministic if a.cmd == "deterministic" else bench)(a.code_dir, a.work, a.out)


if __name__ == "__main__":
    main()
