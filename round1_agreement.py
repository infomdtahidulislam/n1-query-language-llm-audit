#!/usr/bin/env python3
"""round1_agreement.py — N1 E.4/E.5 on the Round-1 108 (pilot validation).

Computes exactly the registered quantities:
  E.3  consensus rule: sets = element listed by >=2 raters; categorical/boolean = majority
       (a 3-way categorical split has no majority -> flagged, excluded from accuracy denominators).
  E.5  human-human: Krippendorff's alpha (categorical/boolean) + pairwise set-F1
       (brands, recommended, prices, retailers), surfaces alias-mapped + case-folded first (v0.35);
       machine-human (primary extractor, Gemini 3 Flash): brand-set / recommended-set F1 and
       Jaccard vs consensus, exact-match rate on (amount, currency) price sets, accuracy on
       refused / answer_language.
  E.6  pilot half of the gate: primary extractor brand-set F1 vs consensus >= 0.90.

Set-F1 convention: both sets empty -> F1 = 1 (stated in the report).
Outputs: ROUND1-CONSENSUS.json, ROUND1-DIVERGENCES-authors-only.csv, ROUND1-AGREEMENT-REPORT.md
"""
import json, re, csv, unicodedata
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

W = Path("/home/claude/w")
RUNS = Path("/mnt/user-data/uploads/New Experiment/runs")

# ---------- folding (identical to the validation battery / v0.35 rule) ----------
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
        for a in row["aliases"].split("|"):
            if a.strip():
                alias_map[fold(a)] = cidv

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

def canon_el(s):
    """canonical id when known, else the case-folded surface (E.5: alias-mapped and case-folded)"""
    return cid(s) or fold(s)

def canon_set(items):
    return frozenset(canon_el(x) for x in items if str(x).strip())

PRICE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s+(BDT|USD|other|unstated)$", re.I)

def norm_amount(a):
    fa = float(a)
    return int(fa) if fa == int(fa) else fa

def price_set_rater(lines_):
    out = set()
    for x in lines_:
        m = PRICE_RE.match(str(x).strip())
        assert m, f"unparseable price line {x!r}"
        cur = m.group(2)
        cur = cur.upper() if cur.upper() in ("BDT", "USD") else cur.lower()
        out.add((norm_amount(m.group(1)), cur))
    return frozenset(out)

def price_set_machine(objs):
    out = set()
    for p in objs or []:
        cur = str(p.get("currency", ""))
        cur = cur.upper() if cur.upper() in ("BDT", "USD") else cur.lower()
        out.add((norm_amount(p.get("amount")), cur))
    return frozenset(out)

# ---------- load ----------
def load_rater(code):
    d = json.load(open(W / f"LABEL-ROUND1-{code}-labels.json", encoding="utf-8"))
    assert d["rater"] == code and d["task"] == "N1 labelling round 1"
    rows = {r["pid"]: r for r in d["labels"]}
    assert len(rows) == 108
    return rows

R = {c: load_rater(c) for c in ("R1", "R2", "R3")}
PIDS = [f"I{i:03d}" for i in range(1, 109)]

mapping = {m["pid"]: m for m in csv.DictReader(open(W / "ROUND1-MAPPING-authors-only.csv", encoding="utf-8"))}
assert set(mapping) == set(PIDS)

prim = {}
for l in open(RUNS / "extracted" / "pilot.primary.jsonl", encoding="utf-8"):
    r = json.loads(l)
    prim[r["subject_key"]] = r
machine = {}
for pid in PIDS:
    rec = prim[mapping[pid]["key"]]
    machine[pid] = rec["extraction"]
assert len(machine) == 108

def rl(row, f):  # rater list field
    v = row.get(f) or []
    return v if isinstance(v, list) else [x for x in str(v).splitlines() if x.strip()]

# per-pid normalized views
SETF = ("brands", "recommended", "retailers")
H = {c: {} for c in R}      # rater -> pid -> dict
for c, rows in R.items():
    for pid in PIDS:
        row = rows[pid]
        H[c][pid] = {
            "language": row["answer_language"],
            "refused": str(row["refused"]).lower() == "true",
            "brands": canon_set(rl(row, "brands")),
            "recommended": canon_set(rl(row, "recommended")),
            "retailers": canon_set(rl(row, "retailers")),
            "prices": price_set_rater(rl(row, "prices")),
        }
M = {}
for pid in PIDS:
    e = machine[pid]
    M[pid] = {
        "language": e.get("answer_language"),
        "refused": bool(e.get("refused")),
        "brands": canon_set(e.get("brands") or []),
        "recommended": canon_set(e.get("recommended") or []),
        "retailers": canon_set(e.get("retailers") or []),
        "prices": price_set_machine(e.get("prices")),
    }

# ---------- Krippendorff's alpha (nominal, complete data) ----------
def kripp_alpha(units):
    """units: list of lists of values (one inner list per unit, one value per rater)"""
    cats = sorted({v for u in units for v in u})
    idx = {c: i for i, c in enumerate(cats)}
    k = len(cats)
    o = [[0.0] * k for _ in range(k)]
    for u in units:
        m = len(u)
        if m < 2:
            continue
        for a in range(m):
            for b in range(m):
                if a != b:
                    o[idx[u[a]]][idx[u[b]]] += 1.0 / (m - 1)
    n_c = [sum(o[i]) for i in range(k)]
    n = sum(n_c)
    if n == 0:
        return None
    Do = sum(o[i][j] for i in range(k) for j in range(k) if i != j) / n
    De = sum(n_c[i] * n_c[j] for i in range(k) for j in range(k) if i != j) / (n * (n - 1))
    if De == 0:
        return None   # degenerate: a single category everywhere
    return 1.0 - Do / De

# sanity checks on the implementation
assert kripp_alpha([["a", "a", "a"]] * 10 + [["b", "b", "b"]] * 10) == 1.0
assert kripp_alpha([["a", "a", "a"]] * 10) is None            # single category -> undefined
_chk = kripp_alpha([["a", "a", "b"]] * 5 + [["b", "b", "a"]] * 5)
assert _chk is not None and _chk < 0.2                        # heavy disagreement -> low

def f1(a, b):
    if not a and not b:
        return 1.0
    i = len(a & b)
    return 2 * i / (len(a) + len(b)) if (a or b) else 1.0

def jac(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)

# ---------- human-human ----------
lang_units = [[H[c][pid]["language"] for c in ("R1", "R2", "R3")] for pid in PIDS]
ref_units = [[H[c][pid]["refused"] for c in ("R1", "R2", "R3")] for pid in PIDS]
alpha_lang = kripp_alpha(lang_units)
alpha_ref = kripp_alpha(ref_units)
lang_all3 = sum(1 for u in lang_units if len(set(u)) == 1)

pair_f1 = {}
for f in SETF + ("prices",):
    for a, b in combinations(("R1", "R2", "R3"), 2):
        vals = [f1(H[a][pid][f], H[b][pid][f]) for pid in PIDS]
        pair_f1[(f, a, b)] = sum(vals) / len(vals)

# ---------- consensus (E.3) ----------
consensus, no_majority = {}, []
for pid in PIDS:
    langs = [H[c][pid]["language"] for c in ("R1", "R2", "R3")]
    lc = Counter(langs).most_common()
    lang_cons = lc[0][0] if lc[0][1] >= 2 else None
    if lang_cons is None:
        no_majority.append(pid)
    refs = [H[c][pid]["refused"] for c in ("R1", "R2", "R3")]
    ref_cons = Counter(refs).most_common(1)[0][0]
    ent = {"answer_language": lang_cons, "refused": ref_cons}
    for f in SETF + ("prices",):
        cnt = Counter()
        for c in ("R1", "R2", "R3"):
            for el in H[c][pid][f]:
                cnt[el] += 1
        ent[f] = sorted([str(e) for e, n in cnt.items() if n >= 2])
    consensus[pid] = ent

# ---------- machine vs consensus (E.5 + E.6 pilot gate) ----------
def cons_set(pid, f):
    ent = consensus[pid][f]
    if f == "prices":
        out = set()
        for s in ent:
            m = re.match(r"^\((\d+(?:\.\d+)?), '(\w+)'\)$", s)
            a, cur = m.group(1), m.group(2)
            out.add((norm_amount(a), cur))
        return frozenset(out)
    return frozenset(ent)

mb_f1, mb_j, mr_f1, mr_j, price_exact = [], [], [], [], []
lang_ok = lang_n = ref_ok = 0
for pid in PIDS:
    mb_f1.append(f1(M[pid]["brands"], cons_set(pid, "brands")))
    mb_j.append(jac(M[pid]["brands"], cons_set(pid, "brands")))
    mr_f1.append(f1(M[pid]["recommended"], cons_set(pid, "recommended")))
    mr_j.append(jac(M[pid]["recommended"], cons_set(pid, "recommended")))
    price_exact.append(M[pid]["prices"] == cons_set(pid, "prices"))
    if consensus[pid]["answer_language"] is not None:
        lang_n += 1
        lang_ok += (M[pid]["language"] == consensus[pid]["answer_language"])
    ref_ok += (M[pid]["refused"] == consensus[pid]["refused"])

brandF1 = sum(mb_f1) / 108
gate = brandF1 >= 0.90

# ---------- divergences (authors only) ----------
div_rows = []
for pid in PIDS:
    langs = {c: H[c][pid]["language"] for c in ("R1", "R2", "R3")}
    ml = M[pid]["language"]
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
            detail = "; ".join(
                f"{el}:{'/'.join(c for c in ('R1','R2','R3') if el in sets[c])}"
                for el in sorted(map(str, u)))
            div_rows.append({"pid": pid, "field": f, "R1": len(sets["R1"]), "R2": len(sets["R2"]),
                             "R3": len(sets["R3"]), "consensus": len(consensus[pid][f]),
                             "extractor": detail[:400]})

# ---------- write outputs ----------
json.dump({"task": "N1 round 1 consensus (E.3 rule)", "n": 108,
           "note": "sets hold canonical ids (unknown surfaces case-folded); prices are (amount, currency) pairs",
           "items": consensus},
          open(W / "ROUND1-CONSENSUS.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

with open(W / "ROUND1-DIVERGENCES-authors-only.csv", "w", newline="", encoding="utf-8") as fo:
    wcsv = csv.DictWriter(fo, fieldnames=["pid", "field", "R1", "R2", "R3", "consensus", "extractor"])
    wcsv.writeheader()
    for r in div_rows:
        wcsv.writerow(r)

fmt = lambda x: "n/a (single category)" if x is None else f"{x:.4f}"
rep = []
rep.append("# N1 Round 1 (E.4 pilot validation) — agreement, consensus, machine scoring")
rep.append("")
rep.append(f"Inputs: LABEL-ROUND1-{{R1,R2,R3}}-labels.json (108 each, validated), "
           f"ROUND1-MAPPING-authors-only.csv, runs/extracted/pilot.primary.jsonl (Gemini 3 Flash, frozen E.1 config).")
rep.append("All set comparisons on canonical ids per E.5/v0.35 (alias-mapped, case-folded; unknown surfaces compare case-folded). "
           "Set-F1 of two empty sets = 1. Consensus per E.3: sets = listed by >=2 raters; categorical = majority.")
rep.append("")
rep.append("## Human–human (E.5)")
rep.append(f"- Krippendorff's alpha, answer_language (nominal, 3 raters, 108 items): **{fmt(alpha_lang)}** "
           f"(all-three-agree on {lang_all3}/108 items)")
rep.append(f"- Krippendorff's alpha, refused: **{fmt(alpha_ref)}** — all 3x108 judgements are 'not refused', "
           f"so alpha is undefined by construction; observed agreement 108/108.")
for f in ("brands", "recommended", "prices", "retailers"):
    cells = "  ".join(f"{a}-{b} {pair_f1[(f,a,b)]:.4f}" for a, b in combinations(("R1","R2","R3"), 2))
    mean3 = sum(pair_f1[(f,a,b)] for a, b in combinations(("R1","R2","R3"), 2)) / 3
    rep.append(f"- pairwise set-F1, {f}: {cells}  (mean {mean3:.4f})")
rep.append("")
rep.append("## Consensus (E.3)")
rep.append(f"- language: consensus on {108 - len(no_majority)}/108; no-majority items: {', '.join(no_majority) or 'none'}")
lc = Counter(consensus[p]["answer_language"] for p in PIDS)
rep.append(f"- consensus language distribution: {dict(lc)}")
rep.append("")
rep.append("## Primary extractor vs consensus (E.5 machine–human; Gemini 3 Flash)")
rep.append(f"- brand-set F1 **{brandF1:.4f}**, Jaccard {sum(mb_j)/108:.4f}")
rep.append(f"- recommended-set F1 {sum(mr_f1)/108:.4f}, Jaccard {sum(mr_j)/108:.4f}")
rep.append(f"- price-set exact-match rate {sum(price_exact)}/108 = {sum(price_exact)/108:.4f}")
rep.append(f"- answer_language accuracy {lang_ok}/{lang_n} = {lang_ok/lang_n:.4f} (items with a language consensus)")
rep.append(f"- refused accuracy {ref_ok}/108 = {ref_ok/108:.4f}")
rep.append("")
rep.append("## E.6 gate — pilot half")
rep.append(f"- registered gate: brand-set F1 vs human consensus >= 0.90 on the pilot set")
rep.append(f"- result: {brandF1:.4f} -> **{'PASS' if gate else 'FAIL'}** "
           f"({'main-300 half still to come' if gate else 'replacement rule per E.6 engages after the G.2 contest'})")
rep.append("")
rep.append(f"Divergence detail: ROUND1-DIVERGENCES-authors-only.csv ({len(div_rows)} rows — authors only, blind ids).")
(W / "ROUND1-AGREEMENT-REPORT.md").write_text("\n".join(rep) + "\n", encoding="utf-8")

print("\n".join(rep))
print(f"\nwrote ROUND1-CONSENSUS.json, ROUND1-DIVERGENCES-authors-only.csv ({len(div_rows)} rows), ROUND1-AGREEMENT-REPORT.md")
