#!/usr/bin/env python3
"""Planning computations for the E.6 escalation sizing proposal (N1).

Part A — single-rater reliability baseline from the banked Round-2 exports:
  each rater's brand-set F1 against the INTERSECTION of the other two raters'
  sets (leave-one-out consensus), plus refused / language agreement vs the
  other-two-unanimous subset. Justifies (or refutes) single-rating with a
  triple-rated overlap.

Part B — design-based precision for the expanded-labelling options, computed
  from the frozen machine extraction corpus (main.primary.jsonl) joined to the
  coded corpus (main.final.jsonl). Machine labels are PLANNING INPUTS ONLY
  (measured brand F1 0.8221): they estimate variance components and observed
  effect magnitudes; the expansion's human labels replace them for inference.

Design simulated: sample Q of the 250 main queries; within each sampled query
label 2 of the 5 reps for every primary arm (bn/en/bl) x 6 models = 36 answers
per query. 2 reps is the minimum that keeps every registered estimator
computable verbatim (F.2 needs a within-arm rep pair for D_win).

Outputs SEs / MDEs per model per contrast for:
  - F.3 (RQ2) local-brand share: per-query arm difference of answer-level share
  - F.2 (RQ1) excess divergence: delta(q,m) = D_btw - mean(D_win), 2-rep draw
and the G.1-anchored per-model per-arm SE of local share (registered bar 0.05).

Usage: python expansion_sizing.py --root . --extract runs/extracted/main.primary.jsonl
       (defaults match the author's F: layout; here run with explicit paths)
"""
import argparse, csv, json, random, statistics, sys, unicodedata, re
from pathlib import Path
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument("--aliases", default="brand_aliases.csv")
ap.add_argument("--labels-dir", default=".")
ap.add_argument("--mapping", default="ROUND2-MAPPING-authors-only.csv")
ap.add_argument("--coded", default="runs/coded/main.final.jsonl")
ap.add_argument("--extract", default="runs/extracted/main.primary.jsonl")
ap.add_argument("--draws", type=int, default=400, help="MC subsample draws")
ap.add_argument("--seed", type=int, default=20260922)
a = ap.parse_args()
rng = random.Random(a.seed)

# ---------- folding (identical to round2_agreement.py / v0.35) ----------
def fold(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s.strip())
    return s.casefold().strip()

alias_map, class_map = {}, {}
with open(a.aliases, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        cidv = row["canonical_id"]
        class_map[cidv] = row["class"]
        alias_map[fold(row["display_name"])] = cidv
        for al in row["aliases"].split("|"):
            if al.strip():
                alias_map[fold(al)] = cidv

def cid(s):
    fs = fold(s)
    if fs in alias_map:
        return alias_map[fs]
    toks = fs.split()
    for n in (3, 2, 1):
        if len(toks) >= n:
            p = " ".join(toks[:n])
            if p in alias_map:
                return alias_map[p]
    return None

def canon_set(items):
    return frozenset((cid(x) or fold(x)) for x in items if str(x).strip())

def f1(x, y):
    """Canonical Round-1/Round-2 convention: mean per-item set-F1, empty-empty = 1."""
    if not x and not y:
        return 1.0
    if not x or not y:
        return 0.0
    tp = len(x & y)
    if tp == 0:
        return 0.0
    p, r = tp / len(x), tp / len(y)
    return 2 * p * r / (p + r)

# =====================================================================
# Part A — single-rater vs leave-one-out consensus (Round-2 300)
# =====================================================================
print("=" * 78)
print("PART A - single-rater reliability vs leave-one-out consensus (Round-2 300)")
print("=" * 78)
raters = ["R1", "R2", "R3"]
lab = {}
for r in raters:
    d = json.load(open(Path(a.labels_dir) / f"LABEL-ROUND2-{r}-labels.json", encoding="utf-8"))
    assert d["rater"] == r and len(d["labels"]) == 300
    lab[r] = {row["pid"]: row for row in d["labels"]}
pids = sorted(lab["R1"])
assert all(sorted(lab[r]) == pids for r in raters)

bset = {r: {p: canon_set(lab[r][p]["brands"]) for p in pids} for r in raters}

# self-check: pairwise mean per-item F1 must reproduce the recorded Round-2 numbers
# (ROUND2-AGREEMENT-REPORT: R1-R2 0.9197, R1-R3 0.9024, R2-R3 0.9231)
pairs = [("R1", "R2"), ("R1", "R3"), ("R2", "R3")]
print("\npairwise brand set-F1, canonical convention (self-check vs ROUND2-AGREEMENT-REPORT):")
for x, y in pairs:
    v = statistics.mean(f1(bset[x][p], bset[y][p]) for p in pids)
    print(f"  {x}-{y}: {v:.4f}")

print("\nrater vs INTERSECTION of the other two (leave-one-out two-rater consensus),")
print("same mean per-item set-F1 convention as the E.6 machine gate (machine: 0.8221):")
for r in raters:
    o1, o2 = [x for x in raters if x != r]
    per = [f1(bset[r][p], bset[o1][p] & bset[o2][p]) for p in pids]
    print(f"  {r}: mean per-item F1 {statistics.mean(per):.4f}"
          f"   items with F1=1: {sum(1 for v in per if v == 1.0)}/{len(per)}"
          f"   items with F1=0: {sum(1 for v in per if v == 0.0)}/{len(per)}")

def norm_bool(v):
    return str(v).strip().lower() in ("true", "1", "yes")

print("\ncategorical layers - rater vs other-two-unanimous subset:")
for field, getter in [("refused", lambda row: norm_bool(row["refused"])),
                      ("answer_language", lambda row: str(row["answer_language"]).strip().lower())]:
    for r in raters:
        o1, o2 = [x for x in raters if x != r]
        sub = [p for p in pids if getter(lab[o1][p]) == getter(lab[o2][p])]
        agree = sum(1 for p in sub if getter(lab[r][p]) == getter(lab[o1][p]))
        print(f"  {field:16} {r}: {agree}/{len(sub)} = {agree/len(sub):.4f}")

# =====================================================================
# Part B — design-based precision from the machine corpus
# =====================================================================
print("\n" + "=" * 78)
print("PART B - design precision (machine corpus as planning input, F1 0.8221)")
print("=" * 78)

coded = {}
with open(a.coded, encoding="utf-8") as f:
    for line in f:
        if line.strip():
            r = json.loads(line)
            coded[r["key"]] = r

items = defaultdict(list)   # (query, model, arm) -> list of (brands_set, local_share, n_class)
n_join = n_prim = 0
ARMS = ("bn", "en", "bl")
with open(a.extract, encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        e = json.loads(line)
        c = coded.get(e["subject_key"])
        if c is None:
            continue
        n_join += 1
        if c["degenerate"]:
            continue
        ex = e.get("extraction") or {}
        if not isinstance(ex, dict) or ex.get("refused") is True:
            continue
        if c["arm"] not in ARMS:
            continue
        n_prim += 1
        s = canon_set(ex.get("brands") or [])
        loc = sum(1 for b in s if class_map.get(b) == "local")
        glo = sum(1 for b in s if class_map.get(b) == "global")
        share = loc / (loc + glo) if (loc + glo) else None
        items[(c["query_id"], c["model_id"], c["arm"])].append((s, share))

queries = sorted({q for q, m, arm in items})
models = sorted({m for q, m, arm in items})
print(f"\njoined {n_join} extraction rows; primary-arm F.6 items used: {n_prim}")
print(f"queries {len(queries)}, models {len(models)}")

def jac(s1, s2):
    if not s1 and not s2:
        return 1.0
    u = len(s1 | s2)
    return len(s1 & s2) / u if u else 1.0

CONTRASTS = [("bn", "en"), ("bl", "en"), ("bn", "bl")]

# --- full-corpus (5-rep) reference statistics per query x model ---
ref_delta = defaultdict(dict)   # (model, contrast) -> {q: excess divergence}
ref_dshare = defaultdict(dict)  # (model, contrast) -> {q: local-share diff}
arm_share = defaultdict(dict)   # (model, arm) -> {q: mean local share}
for m in models:
    for q in queries:
        cell = {arm: items.get((q, m, arm), []) for arm in ARMS}
        for arm in ARMS:
            sh = [s for _, s in cell[arm] if s is not None]
            if sh:
                arm_share[(m, arm)][q] = statistics.mean(sh)
        for a1, a2 in CONTRASTS:
            r1, r2 = cell[a1], cell[a2]
            if len(r1) >= 2 and len(r2) >= 2:
                btw = statistics.mean(jac(x[0], y[0]) for x in r1 for y in r2)
                w1 = statistics.mean(jac(r1[i][0], r1[j][0]) for i in range(len(r1)) for j in range(i + 1, len(r1)))
                w2 = statistics.mean(jac(r2[i][0], r2[j][0]) for i in range(len(r2)) for j in range(i + 1, len(r2)))
                ref_delta[(m, (a1, a2))][q] = (1 - btw) - statistics.mean([1 - w1, 1 - w2])
            s1 = [s for _, s in r1 if s is not None]
            s2 = [s for _, s in r2 if s is not None]
            if s1 and s2:
                ref_dshare[(m, (a1, a2))][q] = statistics.mean(s1) - statistics.mean(s2)

print("\nobserved full-corpus effect magnitudes (machine labels, planning input):")
print(f"{'model':20} {'contrast':8} {'mean excess div.':>17} {'mean d(local share)':>20}")
for m in models:
    for con in CONTRASTS:
        dd = list(ref_delta[(m, con)].values())
        ds = list(ref_dshare[(m, con)].values())
        print(f"{m:20} {con[0]+'-'+con[1]:8} {statistics.mean(dd):>17.4f} {statistics.mean(ds):>20.4f}")

# --- MC: variance of the per-query statistic under the 2-rep design ---
# total variance of the subsampled per-query stat = between-query variance of
# its draw-mean + mean within-query draw variance; SE(Q) = sqrt(totvar / Q).
def mc_variance(stat_fn, keys):
    per_q = defaultdict(list)
    for _ in range(a.draws):
        for q in keys:
            v = stat_fn(q)
            if v is not None:
                per_q[q].append(v)
    qmeans, wvars = [], []
    for q, vals in per_q.items():
        if len(vals) >= 2:
            qmeans.append(statistics.mean(vals))
            wvars.append(statistics.variance(vals))
    if len(qmeans) < 2:
        return None, None, 0
    return (statistics.variance(qmeans) + statistics.mean(wvars),
            statistics.mean(qmeans), len(qmeans))

res = {}
for m in models:
    for con in CONTRASTS:
        a1, a2 = con

        def stat_delta(q, m=m, a1=a1, a2=a2):
            r1, r2 = items.get((q, m, a1), []), items.get((q, m, a2), [])
            if len(r1) < 2 or len(r2) < 2:
                return None
            x = rng.sample(r1, 2); y = rng.sample(r2, 2)
            btw = statistics.mean(jac(p[0], s[0]) for p in x for s in y)
            win = statistics.mean([1 - jac(x[0][0], x[1][0]), 1 - jac(y[0][0], y[1][0])])
            return (1 - btw) - win

        def stat_dshare(q, m=m, a1=a1, a2=a2):
            r1, r2 = items.get((q, m, a1), []), items.get((q, m, a2), [])
            if len(r1) < 2 or len(r2) < 2:
                return None
            s1 = [s for _, s in rng.sample(r1, 2) if s is not None]
            s2 = [s for _, s in rng.sample(r2, 2) if s is not None]
            if not s1 or not s2:
                return None
            return statistics.mean(s1) - statistics.mean(s2)

        vd, mu_d, nd = mc_variance(stat_delta, queries)
        vs, mu_s, ns = mc_variance(stat_dshare, queries)
        res[(m, con)] = dict(var_delta=vd, mu_delta=mu_d, var_share=vs, mu_share=mu_s)

# per-model per-arm local-share SE under the design (G.1 anchor, bar = 0.05)
def stat_arm(q, m, arm):
    r1 = items.get((q, m, arm), [])
    if len(r1) < 2:
        return None
    s1 = [s for _, s in rng.sample(r1, 2) if s is not None]
    return statistics.mean(s1) if s1 else None

arm_var = {}
for m in models:
    for arm in ARMS:
        v, mu, n = mc_variance(lambda q, m=m, arm=arm: stat_arm(q, m, arm), queries)
        arm_var[(m, arm)] = (v, mu)

Z95, Z80 = 1.959963984540054, 0.8416212335729143
QS = [30, 40, 50, 60, 80]
print(f"\nMC draws per cell: {a.draws}   design: Q queries x 3 arms x 6 models x 2 reps = 36Q answers")

print("\n--- F.3 (RQ2) local-share arm contrast: SE and MDE (80% power, two-sided) ---")
print(f"{'model':20} {'con':7} {'mu(mach)':>9} " + " ".join(f"Q={Q:<3} SE/MDE(a=.05)/MDE(Holm)".rjust(28) for Q in QS[:3]))
alpha_holm = 0.05 / 18
ZH = 2.9155  # Phi^-1(1 - alpha_holm/2), alpha_holm = 0.05/18
for m in models:
    row = ""
    for con in CONTRASTS:
        r = res[(m, con)]
        if r["var_share"] is None:
            continue
        sd = r["var_share"] ** 0.5
        cells = []
        for Q in QS[:3]:
            se = sd / Q ** 0.5
            cells.append(f"{se:.3f}/{(Z95+Z80)*se:.3f}/{(ZH+Z80)*se:.3f}")
        print(f"{m:20} {con[0]+'-'+con[1]:7} {r['mu_share']:>9.4f} " + " ".join(c.rjust(28) for c in cells))

print("\n--- F.2 (RQ1) excess divergence: SE and MDE ---")
for m in models:
    for con in CONTRASTS:
        r = res[(m, con)]
        if r["var_delta"] is None:
            continue
        sd = r["var_delta"] ** 0.5
        cells = []
        for Q in QS[:3]:
            se = sd / Q ** 0.5
            cells.append(f"{se:.3f}/{(Z95+Z80)*se:.3f}/{(ZH+Z80)*se:.3f}")
        print(f"{m:20} {con[0]+'-'+con[1]:7} {r['mu_delta']:>9.4f} " + " ".join(c.rjust(28) for c in cells))

print("\n--- G.1 anchor: per-model per-arm local-share SE (registered pilot bar: 0.05) ---")
print(f"{'model':20} {'arm':4} {'share':>7} " + " ".join(f"SE@Q={Q}".rjust(9) for Q in QS))
worst = defaultdict(list)
for m in models:
    for arm in ARMS:
        v, mu = arm_var[(m, arm)]
        if v is None:
            continue
        ses = [(v / Q) ** 0.5 for Q in QS]
        for Q, se in zip(QS, ses):
            worst[Q].append(se)
        print(f"{m:20} {arm:4} {mu:>7.4f} " + " ".join(f"{se:9.4f}" for se in ses))
print("\nmedian / max per-cell SE across the 18 model x arm cells:")
for Q in QS:
    w = sorted(worst[Q])
    print(f"  Q={Q:<3}: median {w[len(w)//2]:.4f}   max {w[-1]:.4f}   cells<=0.05: {sum(1 for x in w if x <= 0.05)}/18")

# power at the OBSERVED machine-based effect sizes
print("\n--- power at observed (machine) effect magnitudes, Holm-floor alpha=.05/18 ---")
from math import erf, sqrt
def phi(x): return 0.5 * (1 + erf(x / sqrt(2)))
print(f"{'model':20} {'con':7} {'outcome':10} " + " ".join(f"Q={Q}".rjust(7) for Q in QS))
for m in models:
    for con in CONTRASTS:
        r = res[(m, con)]
        for nm, mu_k, var_k in [("excess", "mu_delta", "var_delta"), ("d(share)", "mu_share", "var_share")]:
            if r[var_k] is None:
                continue
            sd = r[var_k] ** 0.5
            pw = [phi(abs(r[mu_k]) / (sd / Q ** 0.5) - ZH) for Q in QS]
            print(f"{m:20} {con[0]+'-'+con[1]:7} {nm:10} " + " ".join(f"{p:7.2f}" for p in pw))

print("\ndone.")
