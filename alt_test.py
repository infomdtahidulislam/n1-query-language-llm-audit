#!/usr/bin/env python3
"""alt_test.py — N1 §E.5 / F5: the alternative annotator test (alt-test; Calderon, Reichart & Dror, ACL 2025,
arXiv:2501.10970) of the primary extractor against the three raters on the Round-2 main 300.

Run exactly as the paper specifies (its §3 and the authors' reference implementation, github.com/nitaytech/AltTest,
alt_test_example.ipynb), with the registered F5 parameters and the choices fixed in the post-freeze record
"alt-test specification fixed" (27 Sep 2026) before any alt-test statistic was computed:
  * label: the brand set — the layer the E.6 gate judges — in a single application (F5);
  * alignment score: S(a, x_i, j) = mean over the two raters other than j of set-F1(a, h_k(x_i)), the paper's
    similarity score for structured outputs, with E.5's own set metric: surface forms folded and alias-mapped
    through the frozen name table exactly as round2_agreement.py does (v0.35), both sets empty -> F1 = 1;
  * items: the 300 answers minus those without a primary extraction (the E.6 scored set), because the reference
    implementation keeps only instances that carry an LLM annotation and at least two human annotations;
  * W^f_ij = 1[S(f) >= S(h_j)], W^h_ij = 1[S(h_j) >= S(f)] (ties count for both); d_ij = W^h_ij - W^f_ij;
    H0j: rho^f_j <= rho^h_j - eps vs H1j: rho^f_j > rho^h_j - eps, by scipy.stats.ttest_1samp(d_j, eps,
    alternative='less'); eps = 0.15 (F5, skilled annotators); n >= 30, so the t-test (not the Wilcoxon fallback);
  * the Benjamini-Yekutieli procedure at q = .05 across the three H0j (the paper's §3.3; a single application
    needs no further across-environment correction, which is what F5's "no multiple-environment FDR" waives);
  * winning rate omega = rejected / 3; the extractor passes iff omega >= 0.5; advantage probability rho =
    mean over raters of rho^f_j.
Before the test the script reproduces the registered E.6 main-300 figures from the same labels and folding
(primary brand-set F1 vs consensus 0.8221 on 293 scored answers; 0.8195 conservative on all 300) and stops if
they do not match, so the alt-test judges exactly the labels the gate judged.

Usage (study root):  python alt_test.py  ->  ALT-TEST-RESULTS.json, ALT-TEST-RESULTS.md
"""
import argparse, csv, hashlib, json, re, unicodedata
from collections import Counter
from pathlib import Path
import numpy as np
from scipy.stats import ttest_1samp

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=".")
ap.add_argument("--runs", default=None)
ap.add_argument("--selftest-only", action="store_true", help="reproduce the E.6 figures and stop")
a = ap.parse_args()
W = Path(a.root)
RUNS = Path(a.runs) if a.runs else W / "runs"
N, EPS, Q = 300, 0.15, 0.05
GATES = {
    W / "LABEL-ROUND2-R1-labels.json": "53f46eba77861230",
    W / "LABEL-ROUND2-R2-labels.json": "335dd4dd4f5253ab",
    W / "LABEL-ROUND2-R3-labels.json": "fea46917cba90890",
    W / "ROUND2-MAPPING-authors-only.csv": "e458a3c539077772",
    W / "brand_aliases.csv": "0b7bd5e8355c9193",
    RUNS / "extracted" / "main.primary.jsonl": "983d233be140bcfe",
}
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
for p, want in GATES.items():
    got = sha(p)
    if not got.startswith(want):
        raise SystemExit(f"INPUT GATE: {p.name} sha256 {got[:16]} is not the registered file ({want})")

# ---------- folding and set metric: verbatim from round2_agreement.py (E.5, v0.35) ----------
def fold(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s.strip())
    return s.casefold().strip()

alias_map = {}
with open(W / "brand_aliases.csv", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        cidv = row["canonical_id"]
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
    if not x and not y:
        return 1.0
    i = len(x & y)
    return 2 * i / (len(x) + len(y)) if (x or y) else 1.0

def rl(row, f):
    v = row.get(f) or []
    return v if isinstance(v, list) else [x for x in str(v).splitlines() if x.strip()]

# ---------- load the three raters and the primary extraction, as round2_agreement.py does ----------
def load_rater(code):
    with open(W / f"LABEL-ROUND2-{code}-labels.json", encoding="utf-8") as fh:
        d = json.load(fh)
    assert d["rater"] == code and d["task"] == "N1 labelling round 2" and not d.get("partial")
    rows = {r["pid"]: r for r in d["labels"]}
    assert len(rows) == N, f"{code}: {len(rows)} labels"
    return rows

RATERS = ("R1", "R2", "R3")
Rr = {c: load_rater(c) for c in RATERS}
PIDS = [f"M{i:03d}" for i in range(1, N + 1)]
for c in Rr:
    assert set(Rr[c]) == set(PIDS)
with open(W / "ROUND2-MAPPING-authors-only.csv", encoding="utf-8") as fh:
    mapping = {m["pid"]: m for m in csv.DictReader(fh)}
assert set(mapping) == set(PIDS)
prim = {}
with open(RUNS / "extracted" / "main.primary.jsonl", encoding="utf-8") as fh:
    for l in fh:
        if l.strip():
            r = json.loads(l)
            prim[r["subject_key"]] = r
machine, missing = {}, []
for pid in PIDS:
    rec = prim.get(mapping[pid]["key"])
    e = rec.get("extraction") if rec and not rec.get("schema_errors") else None
    if e is None:
        missing.append(pid)
    else:
        machine[pid] = canon_set(e.get("brands") or [])
human = {c: {pid: canon_set(rl(Rr[c][pid], "brands")) for pid in PIDS} for c in RATERS}

# ---------- self-test: reproduce the registered E.6 main-300 figures ----------
def consensus(pid):
    cnt = Counter()
    for c in RATERS:
        for el in human[c][pid]:
            cnt[el] += 1
    return frozenset(str(e) for e, n in cnt.items() if n >= 2)

scored = [pid for pid in PIDS if pid in machine]
e6 = sum(f1(machine[pid], consensus(pid)) for pid in scored) / len(scored)
e6_all = (sum(f1(machine[pid], consensus(pid)) for pid in scored)
          + sum(1.0 if not consensus(pid) else 0.0 for pid in missing)) / N
assert len(scored) == 293 and round(e6, 4) == 0.8221 and round(e6_all, 4) == 0.8195, (len(scored), e6, e6_all)
print(f"E.6 reproduced: primary brand-set F1 {e6:.4f} on {len(scored)} scored; conservative all-{N} {e6_all:.4f}")
if a.selftest_only:
    raise SystemExit(0)

# ---------- the alt-test: the reference implementation's procedure ----------
def sim_score(pred, anns):
    return float(np.mean([f1(pred, ann) for ann in anns]))

def by_procedure(p_values, q):
    p_values = np.array(p_values, dtype=float)
    m = len(p_values)
    sorted_indices = np.argsort(p_values)
    sorted_pvals = p_values[sorted_indices]
    H_m = np.sum(1.0 / np.arange(1, m + 1))
    by_thresholds = (np.arange(1, m + 1) / m) * (q / H_m)
    max_i = -1
    for i in range(m):
        if sorted_pvals[i] <= by_thresholds[i]:
            max_i = i
    if max_i == -1:
        return []
    return list(sorted_indices[:max_i + 1])

def alt_test(llm, humans, eps, q, min_humans=2, min_instances=30):
    h_set = {}
    for h, anns in humans.items():
        for i in anns:
            h_set.setdefault(i, []).append(h)
    keep = {i for i in h_set if len(h_set[i]) >= min_humans and i in llm}
    per = []
    for h in humans:
        inst = [i for i in humans[h] if i in keep]
        if len(inst) < min_instances:
            continue
        wf, wh, sf, sh = [], [], [], []
        for i in inst:
            rest = [humans[k][i] for k in h_set[i] if k != h]
            s_h, s_f = sim_score(humans[h][i], rest), sim_score(llm[i], rest)
            wf.append(1 if s_f >= s_h else 0)
            wh.append(1 if s_h >= s_f else 0)
            sf.append(s_f)
            sh.append(s_h)
        d = [x - y for x, y in zip(wh, wf)]
        r = ttest_1samp(d, eps, alternative="less")
        per.append({"rater": h, "n": len(inst), "rho_llm": float(np.mean(wf)), "rho_human": float(np.mean(wh)),
                    "mean_d": float(np.mean(d)), "t": float(r.statistic), "df": len(inst) - 1, "p": float(r.pvalue),
                    "mean_S_llm": float(np.mean(sf)), "mean_S_human": float(np.mean(sh)),
                    "ties": int(sum(1 for x, y in zip(wf, wh) if x == y == 1))})
    rej = set(by_procedure([x["p"] for x in per], q))
    for k, x in enumerate(per):
        x["rejected_BY"] = k in rej
    omega = len(rej) / len(per)
    return {"per_rater": per, "winning_rate": omega, "advantage_probability": float(np.mean([x["rho_llm"] for x in per])),
            "passes": omega >= 0.5}

res = alt_test(machine, human, EPS, Q)
out = {"task": "N1 alt-test (F5, §E.5): primary extractor vs R1-R3, brand set, Round-2 main 300",
       "method": "Calderon, Reichart & Dror (ACL 2025), arXiv:2501.10970; reference implementation github.com/nitaytech/AltTest",
       "epsilon": EPS, "q_BY": Q, "score": "mean set-F1 vs the two remaining raters (E.5 folding, frozen name table; both empty = 1)",
       "items": len(scored), "items_without_primary_extraction": missing,
       "e6_reproduced": {"brand_f1_scored": e6, "scored": len(scored), "brand_f1_all300_conservative": e6_all},
       "inputs": {("runs/extracted/" + p.name if p.parent.name == "extracted" else p.name): sha(p) for p in GATES},
       "script_sha256": sha(Path(__file__)), **res}
with open(W / "ALT-TEST-RESULTS.json", "w", encoding="utf-8", newline="\n") as fh:
    json.dump(out, fh, indent=1)
L = ["# N1 — alt-test of the primary extractor (brand set, Round-2 main 300)", "",
     f"ε = {EPS}; Benjamini–Yekutieli q = {Q} across the three raters; {len(scored)} answers with a primary extraction "
     f"({len(missing)} without one: {', '.join(missing)}). E.6 reproduced first: brand-set F1 vs consensus {e6:.4f} "
     f"on {len(scored)} [{e6_all:.4f} conservative on all {N}].", "",
     "| rater left out | n | ρ extractor | ρ rater | mean d | t (df) | p (one-sided) | rejected (BY) | mean S extractor | mean S rater |",
     "|---|---|---|---|---|---|---|---|---|---|"]
for x in res["per_rater"]:
    L.append(f"| {x['rater']} | {x['n']} | {x['rho_llm']:.3f} | {x['rho_human']:.3f} | {x['mean_d']:+.3f} | "
             f"{x['t']:.2f} ({x['df']}) | {x['p']:.4g} | {'yes' if x['rejected_BY'] else 'no'} | "
             f"{x['mean_S_llm']:.3f} | {x['mean_S_human']:.3f} |")
L += ["", f"Winning rate ω = {res['winning_rate']:.3f} → **{'passes' if res['passes'] else 'does not pass'}** "
      f"(registered rule ω ≥ 0.5); advantage probability ρ = {res['advantage_probability']:.3f}.", ""]
with open(W / "ALT-TEST-RESULTS.md", "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(L))
print("\n".join(L))
