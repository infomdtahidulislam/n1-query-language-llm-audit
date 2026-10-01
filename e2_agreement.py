#!/usr/bin/env python3
"""e2_agreement.py — E.2 cross-extractor agreement on the main run (registered E.5 formulas).

Compares the cross-check extractor (Glimmer 30B) against the primary (Qwen3.8-Flash) over the
stratified ~2,000-answer subsample, with the IDENTICAL canonical folding and metrics used for
the G.2 contest's machine-machine block (contest_score.py, v0.52–v0.55) and Round 1 (E.5/v0.35):
brand-set F1, recommended-set F1, exact price-set agreement, answer-language agreement, refused
agreement. Pairs whose PRIMARY extraction is terminally schema-failed (E.1 cap; 13 answers
study-wide) are excluded and reported, mirroring D.6.

Usage (study machine):   python e2_agreement.py
Here (staged copies):    python e2_agreement.py --cross <path> --primary <path> --aliases brand_aliases.csv
Writes E2-AGREEMENT.json next to itself.
"""
import argparse, csv, json, re, unicodedata
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--cross", default="runs/extracted/main.cross_check.jsonl")
ap.add_argument("--primary", default="runs/extracted/main.primary.jsonl")
ap.add_argument("--aliases", default="brand_aliases.csv")
ap.add_argument("--coded", default="runs/coded/main.jsonl")
ap.add_argument("--pipeline", default="n1_pipeline.py")
a = ap.parse_args()

# ---------- identical folding to round1_agreement.py / contest_score.py ----------
def fold(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s.strip())
    return s.casefold().strip()

alias_map = {}
with open(a.aliases, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        cidv = row["canonical_id"]
        alias_map[fold(row["display_name"])] = cidv
        alias_map[fold(cidv)] = cidv
        for al in row["aliases"].split("|"):
            if al.strip():
                alias_map[fold(al)] = cidv

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

def norm_amount(x):
    fx = float(x)
    return int(fx) if fx == int(fx) else fx

def price_set(objs):
    out = set()
    for p in objs or []:
        cur = str(p.get("currency", ""))
        cur = cur.upper() if cur.upper() in ("BDT", "USD") else cur.lower()
        out.add((norm_amount(p.get("amount")), cur))
    return frozenset(out)

def f1(x, y):
    if not x and not y:
        return 1.0
    i = len(x & y)
    return 2 * i / (len(x) + len(y)) if (x or y) else 1.0

def jac(x, y):                      # F.3 convention: J(∅,∅)=1, J(∅,S≠∅)=0
    if not x and not y:
        return 1.0
    return len(x & y) / len(x | y)

def load(path):
    M = {}
    for l in open(path, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        e = r.get("extraction") if not r.get("schema_errors") else None
        M[r["subject_key"]] = {
            "valid": e is not None,
            "language": (e or {}).get("answer_language"),
            "refused": bool((e or {}).get("refused")),
            "brands": canon_set((e or {}).get("brands")),
            "recommended": canon_set((e or {}).get("recommended")),
            "prices": price_set((e or {}).get("prices")),
            # D.5 code-3 conjunct input: any content at all
            "has_content": bool((e or {}).get("brands") or (e or {}).get("retailers")
                                or (e or {}).get("prices")) if e else None,
            "arm": r["arm"], "subject": r["subject_model_id"], "query_id": r["query_id"],
        }
    return M

C = load(a.cross)
P = load(a.primary)
keys = sorted(C)
assert len(keys) == 2000, f"expected 2000 cross-check rows, got {len(keys)}"
missing_primary = [k for k in keys if k not in P]
assert not missing_primary, f"{len(missing_primary)} subsample keys absent from the primary file"

excl = [k for k in keys if not P[k]["valid"] or not C[k]["valid"]]
pairs = [k for k in keys if k not in set(excl)]
n = len(pairs)

bf1 = sum(f1(C[k]["brands"], P[k]["brands"]) for k in pairs) / n
bja = sum(jac(C[k]["brands"], P[k]["brands"]) for k in pairs) / n
rf1 = sum(f1(C[k]["recommended"], P[k]["recommended"]) for k in pairs) / n
rja = sum(jac(C[k]["recommended"], P[k]["recommended"]) for k in pairs) / n
pex = sum(C[k]["prices"] == P[k]["prices"] for k in pairs)
lag = sum(C[k]["language"] == P[k]["language"] for k in pairs)
rag = sum(C[k]["refused"] == P[k]["refused"] for k in pairs)

# ---------- outcome-code agreement (E.5 machine-machine): fold each extractor through the
# REGISTERED finalize logic, importing resolve_language from the frozen runner itself ----------
import importlib.util
spec = importlib.util.spec_from_file_location("n1p", Path(a.pipeline))
n1p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n1p)          # module-level only; main() is __main__-guarded

coded = {}
for l in open(a.coded, encoding="utf-8"):
    if not l.strip():
        continue
    r = json.loads(l)
    coded[r["key"]] = r

def outcome_for(row, M, k):
    """cmd_finalize's branch logic, verbatim, for one extractor."""
    if row["degenerate"]:
        return "degenerate"
    f4 = row.get("f4_fires")
    if f4 is None:
        return "pending_refusal_rules"
    valid = M[k]["valid"]
    if not valid and (f4 or row["pending_extractor"]):
        return "pending_extractor"
    if f4 and not M[k]["has_content"]:
        return "refusal"
    lang, conforming, _ = n1p.resolve_language(row["arm"], row["script_class"], M[k]["language"])
    return "pending_adjudication" if conforming is None else ("valid" if conforming else
                                                              "language_reversion")

oc_pairs = [k for k in pairs if k in coded]
oag = sum(outcome_for(coded[k], C, k) == outcome_for(coded[k], P, k) for k in oc_pairs)

print(f"== E.2 cross-extractor agreement (Glimmer 30B vs Flash primary, main run) ==")
print(f"  subsample pairs scored : {n} of 2000"
      + (f"   ({len(excl)} excluded: primary terminally schema-failed per E.1)" if excl else ""))
print(f"  brand-set     F1 mean  {bf1:.4f}   Jaccard {bja:.4f}")
print(f"  recommended   F1 mean  {rf1:.4f}   Jaccard {rja:.4f}")
print(f"  price sets    exact    {pex}/{n} = {pex/n:.4f}")
print(f"  language      agree    {lag}/{n} = {lag/n:.4f}")
print(f"  refused       agree    {rag}/{n} = {rag/n:.4f}")
print(f"  outcome code  agree    {oag}/{len(oc_pairs)} = {oag/len(oc_pairs):.4f}"
      f"   (finalize fold re-run per extractor)")
if excl:
    for k in excl:
        r = C[k]
        print(f"    excluded: {r['subject']} {r['query_id']} {r['arm']}")

# per-arm brand F1 (reporting aid; same formula, same folding)
arms = sorted({C[k]["arm"] for k in pairs})
per_arm = {}
for arm in arms:
    ks = [k for k in pairs if C[k]["arm"] == arm]
    per_arm[arm] = {"n": len(ks), "brand_f1": sum(f1(C[k]["brands"], P[k]["brands"]) for k in ks) / len(ks),
                    "lang_agree": sum(C[k]["language"] == P[k]["language"] for k in ks) / len(ks)}
    print(f"    {arm:<12} n={len(ks):<5} brand F1 {per_arm[arm]['brand_f1']:.4f}   "
          f"language agree {per_arm[arm]['lang_agree']:.4f}")

json.dump({"pairs_scored": n, "excluded_keys": excl,
           "brand_f1": bf1, "brand_jaccard": bja, "rec_f1": rf1, "rec_jaccard": rja,
           "price_exact": pex, "language_agree": lag, "refused_agree": rag,
           "outcome_agree": oag, "outcome_pairs": len(oc_pairs),
           "per_arm": per_arm},
          open(Path(__file__).with_name("E2-AGREEMENT.json"), "w"), indent=1)
print("\nwrote E2-AGREEMENT.json")
