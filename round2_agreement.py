#!/usr/bin/env python3
"""round2_agreement.py — N1 E.3/E.5/E.6 on the Round-2 main 300.

The registered quantities, with the identical folding and formulas as Round 1
(round1_agreement.py) and the machine blocks (contest_score.py / e2_agreement.py):
  E.3  consensus: sets = element listed by >=2 raters; categorical/boolean = majority
       (a 3-way categorical split has no majority -> flagged, excluded from accuracy denominators).
  E.5  human-human: Krippendorff's alpha (answer_language, refused) + pairwise set-F1
       (brands, recommended, prices, retailers), alias-mapped + case-folded (v0.35);
       machine-human vs the MAIN primary extractor (Qwen3.8-Flash, frozen E.1 config).
  E.6  MAIN half of the gate: primary brand-set F1 vs consensus >= 0.90 on the 300
       (< 0.90 -> the registered replacement rule engages; < 0.85 -> expanded human labelling).

Differences from Round 1, both recorded in RATER-QUERIES-ROUND2.md before any score existed:
  - price parsing folds a named currency token to the codebook's `other` (INR etc.; taka/Tk -> BDT,
    dollar -> USD), identically for all three raters;
  - answers whose primary extraction is terminally schema-failed or absent (E.1 cap; degenerate
    answers) are excluded from the machine-vs-consensus block and reported; the report also shows
    the conservative all-300 brand F1 with those answers scored 0 for the extractor.

Set-F1 convention: both sets empty -> F1 = 1 (stated in the report).
Outputs: ROUND2-CONSENSUS.json, ROUND2-DIVERGENCES-authors-only.csv, ROUND2-AGREEMENT-REPORT.md

Usage (study machine, from the study root):  python round2_agreement.py
"""
import argparse, json, re, csv, unicodedata
from collections import Counter
from itertools import combinations
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=".", help="study root (labels, aliases, mapping)")
ap.add_argument("--runs", default=None, help="runs dir (default <root>/runs)")
a = ap.parse_args()
W = Path(a.root)
RUNS = Path(a.runs) if a.runs else W / "runs"
N = 300
E6_GATE, E6_FLOOR = 0.90, 0.85

# ---------- folding (identical to round1_agreement.py / v0.35) ----------
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

# ---------- prices: Round-1 regex + the recorded Round-2 currency fold ----------
PRICE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s+(\S{1,14})$")

def fold_currency(tok):
    t = tok.strip()
    if t.upper() in ("BDT", "USD"):
        return t.upper()
    if t.lower() in ("other", "unstated"):
        return t.lower()
    if t.lower() in ("taka", "tk", "৳", "টাকা"):
        return "BDT"
    if t.lower() in ("dollar", "dollars"):
        return "USD"
    if t.isalpha():
        return "other"            # any named currency (INR, EUR, ...) per the codebook rule
    return None

def norm_amount(x):
    fx = float(x)
    return int(fx) if fx == int(fx) else fx

def price_set_rater(lines_):
    out = set()
    for x in lines_:
        m = PRICE_RE.match(str(x).strip())
        cur = fold_currency(m.group(2)) if m else None
        assert cur is not None, f"unparseable price line {x!r}"
        out.add((norm_amount(m.group(1)), cur))
    return frozenset(out)

def price_set_machine(objs):
    out = set()
    for p in objs or []:
        cur = str(p.get("currency", ""))
        cur = cur.upper() if cur.upper() in ("BDT", "USD") else cur.lower()
        out.add((norm_amount(p.get("amount")), cur))
    return frozenset(out)

# ---------- load raters ----------
def load_rater(code):
    d = json.load(open(W / f"LABEL-ROUND2-{code}-labels.json", encoding="utf-8"))
    assert d["rater"] == code and d["task"] == "N1 labelling round 2" and not d.get("partial")
    rows = {r["pid"]: r for r in d["labels"]}
    assert len(rows) == N, f"{code}: {len(rows)} labels"
    return rows

R = {c: load_rater(c) for c in ("R1", "R2", "R3")}
PIDS = [f"M{i:03d}" for i in range(1, N + 1)]
for c in R:
    assert set(R[c]) == set(PIDS), f"{c}: pid set mismatch"

mapping = {m["pid"]: m for m in csv.DictReader(open(W / "ROUND2-MAPPING-authors-only.csv",
                                                    encoding="utf-8"))}
assert set(mapping) == set(PIDS)

# ---------- load MAIN primary extraction (may be terminally failed for a few) ----------
prim = {}
for l in open(RUNS / "extracted" / "main.primary.jsonl", encoding="utf-8"):
    if not l.strip():
        continue
    r = json.loads(l)
    prim[r["subject_key"]] = r

machine, machine_missing = {}, []
for pid in PIDS:
    rec = prim.get(mapping[pid]["key"])
    e = rec.get("extraction") if rec and not rec.get("schema_errors") else None
    if e is None:
        machine_missing.append(pid)
    else:
        machine[pid] = e

def rl(row, f):
    v = row.get(f) or []
    return v if isinstance(v, list) else [x for x in str(v).splitlines() if x.strip()]

SETF = ("brands", "recommended", "retailers")
H = {c: {} for c in R}
for c, rows in R.items():
    for pid in PIDS:
        row = rows[pid]
        H[c][pid] = {"language": row["answer_language"],
                     "refused": str(row["refused"]).lower() == "true",
                     "brands": canon_set(rl(row, "brands")),
                     "recommended": canon_set(rl(row, "recommended")),
                     "retailers": canon_set(rl(row, "retailers")),
                     "prices": price_set_rater(rl(row, "prices"))}
M = {}
for pid, e in machine.items():
    M[pid] = {"language": e.get("answer_language"),
              "refused": bool(e.get("refused")),
              "brands": canon_set(e.get("brands") or []),
              "recommended": canon_set(e.get("recommended") or []),
              "retailers": canon_set(e.get("retailers") or []),
              "prices": price_set_machine(e.get("prices"))}

# ---------- Krippendorff's alpha (nominal, complete data; identical implementation) ----------
def kripp_alpha(units):
    cats = sorted({v for u in units for v in u})
    idx = {c: i for i, c in enumerate(cats)}
    k = len(cats)
    o = [[0.0] * k for _ in range(k)]
    for u in units:
        m = len(u)
        if m < 2:
            continue
        for x in range(m):
            for y in range(m):
                if x != y:
                    o[idx[u[x]]][idx[u[y]]] += 1.0 / (m - 1)
    n_c = [sum(o[i]) for i in range(k)]
    n = sum(n_c)
    if n == 0:
        return None
    Do = sum(o[i][j] for i in range(k) for j in range(k) if i != j) / n
    De = sum(n_c[i] * n_c[j] for i in range(k) for j in range(k) if i != j) / (n * (n - 1))
    return None if De == 0 else 1.0 - Do / De

assert kripp_alpha([["a", "a", "a"]] * 10 + [["b", "b", "b"]] * 10) == 1.0
assert kripp_alpha([["a", "a", "a"]] * 10) is None
_chk = kripp_alpha([["a", "a", "b"]] * 5 + [["b", "b", "a"]] * 5)
assert _chk is not None and _chk < 0.2

def f1(x, y):
    if not x and not y:
        return 1.0
    i = len(x & y)
    return 2 * i / (len(x) + len(y)) if (x or y) else 1.0

def jac(x, y):
    if not x and not y:
        return 1.0
    return len(x & y) / len(x | y)

# ---------- human-human (E.5) ----------
lang_units = [[H[c][pid]["language"] for c in ("R1", "R2", "R3")] for pid in PIDS]
ref_units = [[H[c][pid]["refused"] for c in ("R1", "R2", "R3")] for pid in PIDS]
alpha_lang, alpha_ref = kripp_alpha(lang_units), kripp_alpha(ref_units)
lang_all3 = sum(1 for u in lang_units if len(set(u)) == 1)
ref_all3 = sum(1 for u in ref_units if len(set(u)) == 1)

pair_f1 = {}
for f in SETF + ("prices",):
    for x, y in combinations(("R1", "R2", "R3"), 2):
        vals = [f1(H[x][pid][f], H[y][pid][f]) for pid in PIDS]
        pair_f1[(f, x, y)] = sum(vals) / len(vals)

# ---------- consensus (E.3) ----------
consensus, no_majority = {}, []
for pid in PIDS:
    langs = [H[c][pid]["language"] for c in ("R1", "R2", "R3")]
    lc = Counter(langs).most_common()
    lang_cons = lc[0][0] if lc[0][1] >= 2 else None
    if lang_cons is None:
        no_majority.append(pid)
    refs = [H[c][pid]["refused"] for c in ("R1", "R2", "R3")]
    ent = {"answer_language": lang_cons, "refused": Counter(refs).most_common(1)[0][0]}
    for f in SETF + ("prices",):
        cnt = Counter()
        for c in ("R1", "R2", "R3"):
            for el in H[c][pid][f]:
                cnt[el] += 1
        ent[f] = sorted([str(e) for e, n in cnt.items() if n >= 2])
    consensus[pid] = ent

# ---------- machine vs consensus (E.5 machine-human + E.6 MAIN gate) ----------
def cons_set(pid, f):
    ent = consensus[pid][f]
    if f == "prices":
        out = set()
        for s in ent:
            m = re.match(r"^\((\d+(?:\.\d+)?), '([^']+)'\)$", s)
            out.add((norm_amount(m.group(1)), m.group(2)))
        return frozenset(out)
    return frozenset(ent)

scored = [pid for pid in PIDS if pid in M]
mb_f1, mb_j, mr_f1, mr_j, price_exact = [], [], [], [], []
lang_ok = lang_n = ref_ok = 0
for pid in scored:
    mb_f1.append(f1(M[pid]["brands"], cons_set(pid, "brands")))
    mb_j.append(jac(M[pid]["brands"], cons_set(pid, "brands")))
    mr_f1.append(f1(M[pid]["recommended"], cons_set(pid, "recommended")))
    mr_j.append(jac(M[pid]["recommended"], cons_set(pid, "recommended")))
    price_exact.append(M[pid]["prices"] == cons_set(pid, "prices"))
    if consensus[pid]["answer_language"] is not None:
        lang_n += 1
        lang_ok += (M[pid]["language"] == consensus[pid]["answer_language"])
    ref_ok += (M[pid]["refused"] == consensus[pid]["refused"])

ns = len(scored)
brandF1 = sum(mb_f1) / ns
# conservative: missing extractions scored 0 unless the consensus brand set is also empty
cons_zero = [1.0 if not cons_set(pid, "brands") else 0.0 for pid in machine_missing]
brandF1_all = (sum(mb_f1) + sum(cons_zero)) / N
gate = brandF1 >= E6_GATE

# ---------- divergences (authors only) ----------
div_rows = []
for pid in PIDS:
    langs = {c: H[c][pid]["language"] for c in ("R1", "R2", "R3")}
    ml = M[pid]["language"] if pid in M else "NO-EXTRACTION"
    if len(set(langs.values())) > 1 or ml != consensus[pid]["answer_language"]:
        div_rows.append({"pid": pid, "field": "language",
                         "R1": langs["R1"], "R2": langs["R2"], "R3": langs["R3"],
                         "consensus": consensus[pid]["answer_language"] or "NO-MAJORITY",
                         "extractor": ml})
for f in SETF + ("prices",):
    for pid in PIDS:
        sets = {c: H[c][pid][f] for c in ("R1", "R2", "R3")}
        if len({sets[c] for c in sets}) > 1:
            u = set().union(*sets.values())
            detail = "; ".join(f"{el}:{'/'.join(c for c in ('R1','R2','R3') if el in sets[c])}"
                               for el in sorted(map(str, u)))
            div_rows.append({"pid": pid, "field": f, "R1": len(sets["R1"]), "R2": len(sets["R2"]),
                             "R3": len(sets["R3"]), "consensus": len(consensus[pid][f]),
                             "extractor": detail[:400]})

# ---------- outputs ----------
json.dump({"task": "N1 round 2 consensus (E.3 rule, main 300)", "n": N,
           "note": "sets hold canonical ids (unknown surfaces case-folded); prices are "
                   "(amount, currency) pairs with named currencies folded to 'other'",
           "no_extraction_pids": machine_missing, "items": consensus},
          open(W / "ROUND2-CONSENSUS.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

with open(W / "ROUND2-DIVERGENCES-authors-only.csv", "w", newline="", encoding="utf-8") as fo:
    wcsv = csv.DictWriter(fo, fieldnames=["pid", "field", "R1", "R2", "R3", "consensus", "extractor"])
    wcsv.writeheader()
    for r in div_rows:
        wcsv.writerow(r)

fmt = lambda x: "n/a (single category)" if x is None else f"{x:.4f}"
rep = []
rep.append("# N1 Round 2 (main 300) — agreement, consensus, machine scoring, E.6 main gate")
rep.append("")
rep.append(f"Inputs: LABEL-ROUND2-{{R1,R2,R3}}-labels.json (300 each, validated and banked "
           f"as-received), ROUND2-MAPPING-authors-only.csv, runs/extracted/main.primary.jsonl "
           f"(Qwen3.8-Flash, frozen E.1 config).")
rep.append("All set comparisons on canonical ids per E.5/v0.35 (alias-mapped, case-folded). "
           "Set-F1 of two empty sets = 1. Consensus per E.3: sets = listed by >=2 raters; "
           "categorical = majority. Named currency tokens fold to 'other' per the rule recorded "
           "in RATER-QUERIES-ROUND2.md before any score was computed.")
rep.append("")
rep.append("## Human–human (E.5)")
rep.append(f"- Krippendorff's alpha, answer_language (nominal, 3 raters, {N} items): "
           f"**{fmt(alpha_lang)}** (all-three-agree on {lang_all3}/{N})")
rep.append(f"- Krippendorff's alpha, refused: **{fmt(alpha_ref)}** "
           f"(all-three-agree on {ref_all3}/{N})")
for f in ("brands", "recommended", "prices", "retailers"):
    cells = "  ".join(f"{x}-{y} {pair_f1[(f,x,y)]:.4f}" for x, y in combinations(("R1","R2","R3"), 2))
    mean3 = sum(pair_f1[(f,x,y)] for x, y in combinations(("R1","R2","R3"), 2)) / 3
    rep.append(f"- pairwise set-F1, {f}: {cells}  (mean {mean3:.4f})")
rep.append("")
rep.append("## Consensus (E.3)")
rep.append(f"- language: consensus on {N - len(no_majority)}/{N}; no-majority items: "
           f"{', '.join(no_majority) or 'none'}")
lc = Counter(consensus[p]["answer_language"] for p in PIDS)
rep.append(f"- consensus language distribution: {dict(sorted(lc.items(), key=lambda kv: str(kv[0])))}")
rep.append("")
rep.append("## Primary extractor vs consensus (E.5 machine–human; Qwen3.8-Flash)")
rep.append(f"- scored answers: {ns}/{N}" +
           (f" ({len(machine_missing)} without a valid primary extraction — E.1 terminal / "
            f"degenerate: {', '.join(machine_missing)})" if machine_missing else ""))
rep.append(f"- brand-set F1 **{brandF1:.4f}**, Jaccard {sum(mb_j)/ns:.4f}")
rep.append(f"- conservative all-{N} brand-set F1 (missing extractions scored 0 unless consensus "
           f"is also empty): {brandF1_all:.4f}")
rep.append(f"- recommended-set F1 {sum(mr_f1)/ns:.4f}, Jaccard {sum(mr_j)/ns:.4f}")
rep.append(f"- price-set exact-match rate {sum(price_exact)}/{ns} = {sum(price_exact)/ns:.4f}")
rep.append(f"- answer_language accuracy {lang_ok}/{lang_n} = {lang_ok/lang_n:.4f} "
           f"(items with a language consensus)")
rep.append(f"- refused accuracy {ref_ok}/{ns} = {ref_ok/ns:.4f}")
rep.append("")
rep.append("## E.6 gate — MAIN half (registered)")
rep.append(f"- registered gate: primary brand-set F1 vs human consensus >= {E6_GATE} on the 300")
rep.append(f"- result: {brandF1:.4f} -> **{'PASS' if gate else 'FAIL'}**")
if not gate:
    rep.append(f"- registered consequence: the best-performing of the three extractors (same metric) "
               f"replaces the primary for the full corpus and is re-validated on these labels. The "
               f"cross-check and fallback extractors must now be scored on the same 300; expanded "
               f"human labelling engages ONLY if none of the three reaches {E6_FLOOR}. "
               f"(Primary scored {brandF1:.4f}" +
               (f", itself below {E6_FLOOR}." if brandF1 < E6_FLOOR else ".") + ")")
rep.append(f"- pilot half passed at 0.9825 (v0.49); the gate needs both halves.")
rep.append("")
rep.append(f"Divergence detail: ROUND2-DIVERGENCES-authors-only.csv ({len(div_rows)} rows — "
           f"authors only, blind ids).")
(W / "ROUND2-AGREEMENT-REPORT.md").write_text("\n".join(rep) + "\n", encoding="utf-8")
print("\n".join(rep))
print(f"\nwrote ROUND2-CONSENSUS.json, ROUND2-DIVERGENCES-authors-only.csv ({len(div_rows)} rows), "
      f"ROUND2-AGREEMENT-REPORT.md")
