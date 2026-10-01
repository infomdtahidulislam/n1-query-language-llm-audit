#!/usr/bin/env python3
"""contest_score.py — G.2 cross-check contest scoring (registered v0.45/v0.52–v0.54).

Scores Glimmer 30B (cross_check) and Llama 4 Scout (fallback) over the 108 Round-1 answers
against the three-rater consensus (ROUND1-CONSENSUS.json, E.3 rule), with the identical folding
and formulas of round1_agreement.py (E.5/v0.35). Decision per G.2: higher brand-set F1 wins,
tie -> Glimmer; the loser is retired. Machine-machine metrics vs the primary (Flash) per E.5.
"""
import json, re, csv, unicodedata
from pathlib import Path

W = Path("/home/claude/w")
RUNS = Path("/mnt/user-data/uploads/New Experiment/runs")

# ---------- identical folding to round1_agreement.py ----------
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
        alias_map[fold(cidv)] = cidv
        for a in row["aliases"].split("|"):
            if a.strip():
                alias_map[fold(a)] = cidv

def cid(s):
    fs = fold(s)
    if fs in alias_map:
        return alias_map[fs]
    toks = fs.split()
    for n in (3, 2, 1):
        if len(toks) >= n and " ".join(toks[:n]) in alias_map:
            return alias_map[" ".join(toks[:n])]
    return None

def canon_set(items):
    return frozenset((cid(x) or fold(x)) for x in (items or []) if str(x).strip())

def norm_amount(a):
    fa = float(a)
    return int(fa) if fa == int(fa) else fa

def price_set_machine(objs):
    out = set()
    for p in objs or []:
        cur = str(p.get("currency", ""))
        cur = cur.upper() if cur.upper() in ("BDT", "USD") else cur.lower()
        out.add((norm_amount(p.get("amount")), cur))
    return frozenset(out)

def f1(a, b):
    if not a and not b:
        return 1.0
    i = len(a & b)
    return 2 * i / (len(a) + len(b)) if (a or b) else 1.0

def jac(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)

# ---------- inputs ----------
cons = json.load(open(W / "ROUND1-CONSENSUS.json", encoding="utf-8"))["items"]
mapping = {m["pid"]: m for m in csv.DictReader(open(W / "ROUND1-MAPPING-authors-only.csv", encoding="utf-8"))}
PIDS = [f"I{i:03d}" for i in range(1, 109)]
key2pid = {mapping[p]["key"]: p for p in PIDS}

def cons_set(pid, f):
    ent = cons[pid][f]
    if f == "prices":
        out = set()
        for s in ent:
            m = re.match(r"^\((\d+(?:\.\d+)?), '(\w+)'\)$", s)
            out.add((norm_amount(m.group(1)), m.group(2)))
        return frozenset(out)
    return frozenset(ent)

def load_machine(path):
    M = {}
    for l in open(path, encoding="utf-8"):
        r = json.loads(l)
        pid = key2pid.get(r["subject_key"])
        if pid is None:
            continue
        e = r.get("extraction")
        M[pid] = {
            "valid": e is not None,
            "language": (e or {}).get("answer_language"),
            "refused": bool((e or {}).get("refused")),
            "brands": canon_set((e or {}).get("brands")),
            "recommended": canon_set((e or {}).get("recommended")),
            "prices": price_set_machine((e or {}).get("prices")),
        }
    return M

MACHINES = {
    "Qwen3.8-Flash (primary)": load_machine(RUNS / "extracted" / "pilot.primary.jsonl"),
    "Glimmer 30B (cross_check)": load_machine(RUNS / "extracted" / "pilot.cross_check.jsonl"),
    "Llama 4 Scout (fallback)": load_machine(RUNS / "extracted" / "pilot.fallback.jsonl"),
}
for name, M in MACHINES.items():
    assert len(M) == 108, f"{name}: {len(M)} of 108 answers present"

# ---------- machine vs consensus ----------
def score(M):
    bf1 = sum(f1(M[p]["brands"], cons_set(p, "brands")) for p in PIDS) / 108
    bj = sum(jac(M[p]["brands"], cons_set(p, "brands")) for p in PIDS) / 108
    rf1 = sum(f1(M[p]["recommended"], cons_set(p, "recommended")) for p in PIDS) / 108
    rj = sum(jac(M[p]["recommended"], cons_set(p, "recommended")) for p in PIDS) / 108
    pex = sum(M[p]["prices"] == cons_set(p, "prices") for p in PIDS)
    lok = sum(M[p]["language"] == cons[p]["answer_language"] for p in PIDS
              if cons[p]["answer_language"] is not None)
    rok = sum(M[p]["refused"] == cons[p]["refused"] for p in PIDS)
    nval = sum(M[p]["valid"] for p in PIDS)
    return dict(brand_f1=bf1, brand_j=bj, rec_f1=rf1, rec_j=rj,
                price_exact=pex, lang_ok=lok, ref_ok=rok, n_valid=nval)

print("== G.2 contest: machine vs three-rater consensus (108 answers, canonical folding) ==")
res = {}
for name, M in MACHINES.items():
    s = score(M)
    res[name] = s
    print(f"\n{name}  (schema-valid {s['n_valid']}/108)")
    print(f"  brand-set     F1 {s['brand_f1']:.4f}   Jaccard {s['brand_j']:.4f}")
    print(f"  recommended   F1 {s['rec_f1']:.4f}   Jaccard {s['rec_j']:.4f}")
    print(f"  price sets    exact {s['price_exact']}/108 = {s['price_exact']/108:.4f}")
    print(f"  language acc  {s['lang_ok']}/108 = {s['lang_ok']/108:.4f}")
    print(f"  refused acc   {s['ref_ok']}/108 = {s['ref_ok']/108:.4f}")

g = res["Glimmer 30B (cross_check)"]["brand_f1"]
s_ = res["Llama 4 Scout (fallback)"]["brand_f1"]
winner = "Glimmer 30B" if g >= s_ else "Llama 4 Scout"   # tie -> Glimmer per G.2
print(f"\n== G.2 decision ==\n  Glimmer brand-set F1 {g:.4f}  vs  Scout {s_:.4f}"
      f"  ->  **{winner}** takes the cross-check slot"
      + ("" if winner == "Glimmer 30B" else " (Scout replaces Glimmer)")
      + f"; the loser is retired for the study.")

# ---------- machine-machine (E.5): each contestant vs the primary ----------
print("\n== machine-machine vs primary (E.5) ==")
P = MACHINES["Qwen3.8-Flash (primary)"]
for name in ("Glimmer 30B (cross_check)", "Llama 4 Scout (fallback)"):
    M = MACHINES[name]
    bf1 = sum(f1(M[p]["brands"], P[p]["brands"]) for p in PIDS) / 108
    rf1 = sum(f1(M[p]["recommended"], P[p]["recommended"]) for p in PIDS) / 108
    pex = sum(M[p]["prices"] == P[p]["prices"] for p in PIDS)
    lag = sum(M[p]["language"] == P[p]["language"] for p in PIDS)
    rag = sum(M[p]["refused"] == P[p]["refused"] for p in PIDS)
    print(f"  {name}: brand F1 {bf1:.4f} | rec F1 {rf1:.4f} | price exact {pex}/108 "
          f"| language agree {lag}/108 | refused agree {rag}/108")

json.dump({k: v for k, v in res.items()}, open(W / "contest_scores.json", "w"), indent=1)
print("\nwrote contest_scores.json")
