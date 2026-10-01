#!/usr/bin/env python3
"""n1_synth.py — N1: synthetic study data with KNOWN effects, in the exact schemas n1_analysis.py reads,
for validating the analysis code before it touches any real outcome. Nothing here is derived from the
study's outcome data: only the query ids, categories and robust50 flags (design information) are reused.

Planted truths (per subject model):
  claude-sonnet-5   strong arm effects everywhere: brand pools shift by arm (RQ1 Delta > 0), local share
                    logit +0.9 bn / +0.45 bl vs en, price mention and BDT share up in bn, reversion
                    bn 0.10 vs bl 0.45, refusal en 0.04 / bn 0.01 / bl 0.02, length +10% in bn, 6% persona
  gpt-5.6-luna      exact null on every outcome (and zero refusals -> 'no events' path)
  gemini-3-flash    RQ2: every en-arm mention is global (complete separation -> registered fallback)
  grok-4.6, kimi-k3, deepseek-v4-flash   small effects (half of claude's) / null mixtures
Usage:  python n1_synth.py OUTDIR [--seed N] [--null]   (--null: every model null, for calibration runs)"""
import csv, hashlib, json, math, random, shutil, sys
from pathlib import Path
import numpy as np

out = Path(sys.argv[1])
seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 1
NULL = "--null" in sys.argv
HET = float(sys.argv[sys.argv.index("--het") + 1]) if "--het" in sys.argv else 0.0   # query x arm heterogeneity (logit sd)
rng = np.random.default_rng(seed)
random.seed(seed)
(out / "runs/coded").mkdir(parents=True, exist_ok=True)
(out / "runs/extracted").mkdir(parents=True, exist_ok=True)
src_q = Path(__file__).with_name("queries.csv")
shutil.copy(src_q, out / "queries.csv")
Q = list(csv.DictReader(open(src_q, encoding="utf-8")))
CATS = sorted({q["category"] for q in Q})
MODELS = ["claude-sonnet-5", "deepseek-v4-flash", "gemini-3-flash", "gpt-5.6-luna", "grok-4.6", "kimi-k3"]
ARMS = ["en", "bn", "bl"]
FORM = {"en": "en", "bn": "bn", "bl": "banglish", "bl_translit": "banglish"}

def eff(m, big, half=None):
    if NULL or m == "gpt-5.6-luna":
        return 0.0
    if m == "claude-sonnet-5":
        return big
    if m in ("grok-4.6", "kimi-k3"):
        return big / 2 if half is None else half
    return 0.0

# ---------------- name tables: per category 25 local, 25 global, 3 ambiguous brands; 10 retailers
brands, cat_pool = [], {}
for ci, c in enumerate(CATS):
    pool = {"local": [], "global": [], "ambiguous": []}
    for cls, n in (("local", 25), ("global", 25), ("ambiguous", 3)):
        for i in range(n):
            cid = f"c{ci}-{cls[0]}{i:02d}"
            brands.append({"canonical_id": cid, "display_name": cid.upper(), "class": cls,
                           "aliases": "", "source": "synthetic"})
            pool[cls].append(cid)
    cat_pool[c] = pool
rets = []
for i in range(30):
    cls = "local" if i < 18 else ("global" if i < 28 else "ambiguous")
    rid = f"shop{i:02d}"
    rets.append({"canonical_id": rid, "display_name": rid.upper(), "class": cls, "source": "synthetic"})
    brands.append({"canonical_id": rid, "display_name": rid.upper(), "class": cls, "aliases": "", "source": "synthetic"})
def wcsv(p, rows, fields):
    with open(out / p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n"); w.writeheader(); w.writerows(rows)
wcsv("brand_aliases.expansion.csv", brands, ["canonical_id", "display_name", "class", "aliases", "source"])
wcsv("retailer_classification.expansion.csv", rets, ["canonical_id", "display_name", "class", "source"])
wcsv("alias_exclusions.expansion.csv", [{"surface_folded": "notabrand", "surface": "NotABrand", "note": "", "source": "synthetic"}],
     ["surface_folded", "surface", "note", "source"])

# ---------------- answers ("truth") for the full corpus: 250 queries x 6 models x arms x 5 reps
def key():
    return hashlib.md5(str(rng.random()).encode()).hexdigest()
def sh(*a):
    return int(hashlib.md5(repr(a).encode()).hexdigest()[:8], 16)
qeff = {q["query_id"]: rng.normal(0, 0.8) for q in Q}          # query random intercept (local share)
qarm = {(q["query_id"], m, a): (rng.normal(0, HET) if HET else 0.0)
        for q in Q for m in MODELS for a in ARMS + ["bl_translit"]}  # query x arm deviation, mean zero
qtok = {q["query_id"]: rng.normal(0, 0.25) for q in Q}             # query effect on length
qpref = {}                                                      # query-specific brand preference weights
for q in Q:
    pool = cat_pool[q["category"]]
    allb = pool["local"] + pool["global"] + pool["ambiguous"]
    qpref[q["query_id"]] = (allb, rng.gamma(0.6, 1.0, size=len(allb)))
def arm_weights(qid, m, arm):
    allb, w = qpref[qid]
    w = w.copy()
    if arm != "en":
        s = eff(m, 1.0)
        if s:
            r = np.random.default_rng(sh(seed, qid, m, arm))
            w = w * np.exp(s * r.normal(0, 1.0, size=len(w)))    # arm-specific re-weighting -> Delta > 0
    return allb, w
def draw_brands(qid, m, arm, rr):
    allb, w = arm_weights(qid, m, arm)
    k = min(len(allb), 1 + rr.poisson(4))
    # local/global tilt
    tilt = {"en": 0.0, "bn": eff(m, 0.9), "bl": eff(m, 0.45)}.get(arm, eff(m, 0.7))
    cls = np.array([0 if b.split("-")[1][0] == "l" else (1 if b.split("-")[1][0] == "g" else 2) for b in allb])
    logit_local = -0.2 + qeff[qid] + tilt + qarm[(qid, m, arm)]
    ww = w * np.where(cls == 0, math.exp(logit_local / 2), np.where(cls == 1, math.exp(-logit_local / 2), 0.3))
    if m == "gemini-3-flash" and arm == "en" and not NULL:
        ww = np.where(cls == 1, ww, 0.0)                         # separation: en mentions all global
    p = ww / ww.sum()
    return list(rr.choice(allb, size=k, replace=False, p=p))
coded, truth, usage, persona = [], {}, {m: [] for m in MODELS}, {m: [] for m in MODELS}
rev_p = lambda m, a: {"bn": 0.10 + eff(m, 0.0), "bl": 0.10 + eff(m, 0.35)}.get(a, 0.0 if a == "en" else 0.3)
def ref_p(m, a):
    if m == "gpt-5.6-luna":
        return 0.0
    return {"en": 0.02 + eff(m, 0.02), "bn": 0.02 - eff(m, 0.01), "bl": 0.02}.get(a, 0.02)
for q in Q:
    qid = q["query_id"]
    arms = ARMS + (["bl_translit"] if q["robust50"] == "YES" else [])
    for m in MODELS:
        for a in arms:
            for rep in range(1, 6):
                rr = np.random.default_rng(sh(seed, qid, m, a, rep))
                draws = [1]
                if rr.random() < 0.002:
                    draws = [1, 2]
                for dr in draws:
                    k = key()
                    degenerate = (dr == 1 and len(draws) == 2)
                    u = rr.random()
                    if degenerate:
                        outcome, lang = "degenerate", None
                    elif u < ref_p(m, a):
                        outcome, lang = "refusal", FORM[a]
                    elif a != "en" and rr.random() < rev_p(m, a):
                        outcome = "language_reversion"
                        lang = ("bn" if a in ("bl", "bl_translit") and rr.random() < 0.8 else "en") if a != "bn" else \
                               ("en" if rr.random() < 0.7 else "banglish")
                    else:
                        outcome, lang = "valid", FORM[a]
                    trunc = rr.random() < 0.003
                    coded.append({"key": k, "phase": "main", "model_id": m, "query_id": qid, "arm": a, "rep": rep,
                                  "draw": dr, "finish_reason": "length" if trunc else "stop", "truncated": trunc,
                                  "content_chars": int(rr.integers(400, 3000)), "script_class": "bn" if lang == "bn" else "latin",
                                  "degenerate": degenerate, "answer_language": lang, "outcome": outcome})
                    if degenerate:
                        continue
                    tok = math.exp(rr.normal(6.2 + qtok[qid] + (eff(m, 0.10) if a == "bn" else 0.0), 0.4))
                    usage[m].append({"key": k, "model_id": m, "query_id": qid, "arm": a, "rep": rep, "draw": dr,
                                     "finish_reason": "stop", "prompt_tokens": 20, "completion_tokens": int(tok),
                                     "reasoning_tokens": "", "content_chars": 1000, "http_status": 200, "file": "x"})
                    if m == "claude-sonnet-5" and rr.random() < 0.06 and not NULL:
                        persona[m].append({"key": k, "model_id": m, "arm": a, "marker": "anthropic"})
                    bset = [] if outcome == "refusal" else draw_brands(qid, m, a, rr)
                    pr_mention = 0.5 + ({"bn": eff(m, 0.25), "bl": eff(m, 0.1)}.get(a, 0.0))
                    bdt_p = 0.5 + ({"bn": eff(m, 0.35), "bl": eff(m, 0.15)}.get(a, 0.0))
                    prices = []
                    if outcome != "refusal" and rr.random() < pr_mention:
                        for _ in range(1 + rr.poisson(2)):
                            cur = "BDT" if rr.random() < bdt_p else ("USD" if rr.random() < 0.7 else "unstated")
                            prices.append([float(rr.choice([0, 1500, 20000, 45000])) if rr.random() < 0.05 else float(rr.integers(1000, 90000)), cur])
                    shops = [] if outcome == "refusal" else list(rr.choice([r["canonical_id"] for r in rets],
                                                                             size=int(rr.integers(0, 3)), replace=False))
                    rec = [b for b in bset if rr.random() < 0.3]
                    truth[k] = {"brands": bset, "recommended": rec, "retailers": shops, "prices": prices,
                                "refused": outcome == "refusal", "lang": lang}
with open(out / "runs/coded/main.final.jsonl", "w", encoding="utf-8") as f:
    for r in coded:
        f.write(json.dumps(r) + "\n")
for m in MODELS:
    wcsv(f"runs/usage_{m}.csv", usage[m], ["key", "model_id", "query_id", "arm", "rep", "draw", "finish_reason",
                                             "prompt_tokens", "completion_tokens", "reasoning_tokens", "content_chars", "http_status", "file"])
    wcsv(f"runs/persona_{m}.csv", persona[m], ["key", "model_id", "arm", "marker"])

# ---------------- machine extraction: truth with noise (drop 10%, add 5% spurious, 3% 'NotABrand')
with open(out / "runs/extracted/main.primary.jsonl", "w", encoding="utf-8") as f:
    for r in coded:
        if r["degenerate"]:
            continue
        t = truth[r["key"]]
        rr = np.random.default_rng(int(r["key"][:8], 16))
        b = [x.upper() for x in t["brands"] if rr.random() > 0.10]
        if rr.random() < 0.05:
            b.append("SPURIOUS-" + str(int(rr.integers(0, 50))))
        if rr.random() < 0.03:
            b.append("NotABrand")
        ex = {"brands": b, "recommended": [x.upper() for x in t["recommended"] if x.upper() in b],
              "prices": [{"amount": a, "currency": c} for a, c in t["prices"]], "retailers": [x.upper() for x in t["retailers"]],
              "refused": t["refused"], "answer_language": r["answer_language"]}
        f.write(json.dumps({"subject_key": r["key"], "query_id": r["query_id"], "arm": r["arm"], "rep": r["rep"],
                            "draw": r["draw"], "subject_model_id": r["model_id"], "extraction": ex, "schema_errors": None}) + "\n")

# ---------------- human expansion sample: 80 queries (8 per category), 2 reps per cell, + bl_translit for robust
final = {}
for r in coded:
    c = (r["model_id"], r["query_id"], r["arm"], r["rep"])
    if c not in final or r["draw"] > final[c]["draw"]:
        final[c] = r
byq = {}
for q in Q:
    byq.setdefault(q["category"], []).append(q["query_id"])
sample = []
for c in CATS:
    sample += list(rng.choice(sorted(byq[c]), size=8, replace=False))
rows = []
robust = {q["query_id"] for q in Q if q["robust50"] == "YES"}
for qid in sorted(sample):
    arms = ARMS + (["bl_translit"] if qid in robust else [])
    for m in MODELS:
        for a in arms:
            reps = [rp for rp in range(1, 6) if final[(m, qid, a, rp)]["outcome"] != "degenerate"]
            for rp in sorted(rng.choice(reps, size=min(2, len(reps)), replace=False)):
                r = final[(m, qid, a, int(rp))]
                t = truth[r["key"]]
                b = list(t["brands"])
                if rng.random() < 0.03:
                    b.append("notabrand")                          # rater recorded a not-a-brand name
                excl = [x for x in b if x == "notabrand"]
                prim = [x for x in b if x != "notabrand"]
                lang = t["lang"]
                rows.append({"answer_language": lang, "arm": a, "brands": sorted(prim), "brands_order": prim,
                             "brands_incl_excluded": sorted(prim + excl), "draw": r["draw"],
                             "in_primary_set": not t["refused"], "key": r["key"], "label_source": "single",
                             "labelled_by": "R1", "model_id": m, "outcome": r["outcome"], "pid": "X",
                             "prices": sorted([[p[0], p[1]] for p in t["prices"]], key=lambda p: (p[1], p[0])),
                             "query_id": qid, "recommended": sorted(t["recommended"]),
                             "recommended_incl_excluded": sorted(t["recommended"]), "refused": t["refused"],
                             "rep": int(rp), "retailers": sorted(t["retailers"]), "retailers_order": list(t["retailers"]),
                             "retailers_incl_excluded": sorted(t["retailers"]), "script_class": r["script_class"],
                             "zero_price_entries": sum(1 for p in t["prices"] if p[0] == 0)})
with open(out / "EXPANSION-ANALYSIS-SET-v2.jsonl", "w", encoding="utf-8") as f:
    for r in sorted(rows, key=lambda r: r["key"]):
        f.write(json.dumps(r, sort_keys=True) + "\n")
print(f"synthetic study written to {out}: corpus {len(coded)} rows, human sample {len(rows)} answers, "
      f"{len(sample)} queries; null={NULL}")
