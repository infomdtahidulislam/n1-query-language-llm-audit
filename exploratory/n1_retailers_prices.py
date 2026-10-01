#!/usr/bin/env python3
"""n1_retailers_prices.py — N1: two deterministic descriptives on the human-labelled primary set (declared in the
post-freeze record of 28 Sep 2026): (c) the most-named retailers by arm; (d) price entries by currency code by model and
arm. No seed; no test; outside the results of record; no label or code changed.

(c) For each of en, bn and bl: every distinct canonical retailer named in an eligible answer counts once per answer;
counts pooled over the six models, with counts by model and the eligible-answer denominators (per arm, and per model x
arm). Classes come from the run-of-record retailer table with its registered brand-table fallback (rclass(e, strict=False)).
Ranking by count, ties broken by canonical ID; the top ten per arm are listed (the full ranking is in the JSON).
(d) Price entries (not price-bearing answers), including zero amounts and unstated currencies, by model and arm and by
the currency code the analysis set carries: BDT, USD, other, unstated. The analysis set folds every alphabetic code other
than BDT and USD to "other"; for those entries the raw currency tokens of the raters' own labels (the labels the entry
came from) are listed, naming INR when present. No code is changed.
Self-tests (registered values): eligible answers per model and arm equal the registered price-mention denominators
(160 per arm and model; 158 for grok-4.6 bl), and the price-entry totals per model and arm equal the registered
BDT-share denominators (primary/RQ4_bdt_share arms n); --selftest-only stops there.

Usage (study root):  python exploratory/n1_retailers_prices.py  ->  exploratory/TOP-RETAILERS.json / .md, exploratory/PRICE-CURRENCY-COUNTS.json / .md
"""
import argparse, csv, datetime, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from n1_review_common import load, sha

ap = argparse.ArgumentParser(); ap.add_argument("root", nargs="?", default="."); ap.add_argument("--selftest-only", action="store_true")
A = ap.parse_args(); ROOT = Path(A.root); OUT = ROOT / "exploratory"
G = load(ROOT)
H, P, MODELS, ARMS3, REC, rclass = G["H"], G["P"], G["MODELS"], G["ARMS3"], G["REC"], G["rclass"]
rows = [r for r in H if r["arm"] in ARMS3 and P(r)]
denom = Counter((r["model"], r["arm"]) for r in rows)

# ---- self-tests -----------------------------------------------------------------------------------------------------
pm = REC["primary"]["RQ4_price_mention"]["results"]; bs = REC["primary"]["RQ4_bdt_share"]["results"]
for m in MODELS:
    for a in ARMS3:
        assert denom[(m, a)] == pm[m]["arms"][a]["n"], (m, a, denom[(m, a)], pm[m]["arms"][a]["n"])
        assert sum(len(r["prices"]) for r in rows if r["model"] == m and r["arm"] == a) == bs[m]["arms"][a]["n"], (m, a)
assert denom[("grok-4.6", "bl")] == 158 and all(denom[(m, a)] == 160 for m in MODELS for a in ARMS3 if (m, a) != ("grok-4.6", "bl"))
print("self-test OK: eligible answers per model and arm equal the registered price-mention denominators, and price-entry totals equal the registered BDT-share denominators")
if A.selftest_only:
    sys.exit(0)

# ---- (c) retailers ---------------------------------------------------------------------------------------------------
ret = {}
for a in ARMS3:
    cnt, bym = Counter(), defaultdict(Counter)
    for r in rows:
        if r["arm"] != a:
            continue
        for e in set(r["retailers"]):
            cnt[e] += 1; bym[e][r["model"]] += 1
    ranking = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))
    ret[a] = {"eligible_answers": sum(denom[(m, a)] for m in MODELS), "eligible_by_model": {m: denom[(m, a)] for m in MODELS},
              "distinct_retailers": len(cnt), "answers_naming_any_retailer": sum(1 for r in rows if r["arm"] == a and r["retailers"]),
              "ranking": [{"rank": i + 1, "canonical_id": e, "class": rclass(e, False), "answers": n, "share_of_eligible": n / sum(denom[(m, a)] for m in MODELS),
                           "by_model": {m: bym[e][m] for m in MODELS}} for i, (e, n) in enumerate(ranking)]}
top10 = {a: ret[a]["ranking"][:10] for a in ARMS3}

# ---- (d) price entries by currency ----------------------------------------------------------------------------------
codes = ["BDT", "USD", "other", "unstated"]
pc = {m: {a: Counter() for a in ARMS3} for m in MODELS}; zero = Counter(); other_entries = []
for r in rows:
    for amt, cur in r["prices"]:
        pc[r["model"]][r["arm"]][cur] += 1
        if amt == 0:
            zero[(r["model"], r["arm"], cur)] += 1
        if cur == "other":
            other_entries.append((r["key"], r["model"], r["arm"], amt))
allcodes = sorted({c for m in MODELS for a in ARMS3 for c in pc[m][a]})
assert set(allcodes) <= set(codes), allcodes
# raw tokens behind the 'other' entries: the raters' own price lines for those answers (builder's parsing, verbatim)
aset = {r["key"]: r for r in (json.loads(l) for l in open(ROOT / "EXPANSION-ANALYSIS-SET-v2.jsonl", encoding="utf-8"))}
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
        return "other"
    return None
def norm_amount(x):
    fx = float(x)
    return int(fx) if fx == int(fx) else fx
def rl(row, f):
    v = row.get(f) or []
    return v if isinstance(v, list) else [x for x in str(v).splitlines() if x.strip()]
E = {rt: {x["pid"]: x for x in json.load(open(ROOT / f"LABEL-EXPANSION-{rt}-labels.json", encoding="utf-8"))["labels"]} for rt in ("R1", "R2", "R3")}
R2 = {rt: {x["pid"]: x for x in json.load(open(ROOT / f"LABEL-ROUND2-{rt}-labels.json", encoding="utf-8"))["labels"]} for rt in ("R1", "R2", "R3")}
def raw_tokens(key, amt):
    """Distinct raw currency tokens, across the answer's source rater label(s), of price lines with this amount that the
    builder folds to 'other'. An 'other' entry of a consensus answer was listed by at least two raters, so all three
    label sets are read; a single-rated answer has one."""
    r = aset[key]; who = r["labelled_by"]
    if who.startswith("round2:"):
        pid = who.split(":", 1)[1]; srcs = [R2[rt][pid] for rt in ("R1", "R2", "R3")]
    elif who == "R1+R2+R3":
        srcs = [E[rt][r["pid"]] for rt in ("R1", "R2", "R3")]
    else:
        srcs = [E[who][r["pid"]]]
    toks = set()
    for s in srcs:
        for line in rl(s, "prices"):
            m = PRICE_RE.match(str(line).strip()); assert m, line
            if fold_currency(m.group(2)) == "other" and norm_amount(m.group(1)) == amt:
                toks.add(m.group(2))
    assert toks, (key, amt)
    return sorted(toks)
other_detail = [{"key": key, "model": m, "arm": a, "amount": amt, "raw_tokens": raw_tokens(key, amt)} for key, m, a, amt in other_entries]
other_tokens = Counter(t for d in other_detail for t in d["raw_tokens"])  # entries backed by each raw token
totals = {m: {a: sum(pc[m][a].values()) for a in ARMS3} for m in MODELS}
res_d = {"codes": codes, "counts": {m: {a: {c: pc[m][a].get(c, 0) for c in codes} for a in ARMS3} for m in MODELS}, "totals": totals,
         "by_arm_all_models": {a: {c: sum(pc[m][a].get(c, 0) for m in MODELS) for c in codes} for a in ARMS3},
         "zero_amount_entries": {f"{m}|{a}|{c}": n for (m, a, c), n in zero.items()},
         "other_entries": len(other_entries), "entries_by_raw_token_behind_other": dict(other_tokens), "other_entries_detail": other_detail,
         "note": "the analysis set folds every alphabetic code other than BDT and USD to 'other' (builder rule); the raw tokens are read from the raters' own labels and change nothing"}
meta = {"inputs": G["inputs"], "script_sha256": sha(Path(__file__)), "common_sha256": sha(Path(__file__).with_name("n1_review_common.py")),
        "layer": "human-labelled layer, F.6 primary set by the human labels, arms en/bn/bl; run-of-record tables (retailer table with brand-table fallback)",
        "run_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
json.dump({"meta": {**meta, "task": "most-named retailers by arm (descriptive counts; no test; outside the results of record)"}, "results": ret, "top10": top10},
          open(OUT / "TOP-RETAILERS.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
json.dump({"meta": {**meta, "task": "price entries by currency code, model and arm (descriptive counts; no test; outside the results of record)"}, "results": res_d},
          open(OUT / "PRICE-CURRENCY-COUNTS.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)

L_ = ["# N1 — most-named retailers by arm, human-labelled primary set (descriptive only; not a result of record)", ""]
for a in ARMS3:
    L_ += [f"## {a} — {ret[a]['eligible_answers']} eligible answers ({ret[a]['answers_naming_any_retailer']} name a retailer; {ret[a]['distinct_retailers']} distinct retailers)", "",
           "| rank | retailer | class | answers | % of eligible | " + " | ".join(MODELS) + " |", "|---" * (5 + len(MODELS)) + "|"]
    for e in top10[a]:
        L_.append(f"| {e['rank']} | {e['canonical_id']} | {e['class']} | {e['answers']} | {100 * e['share_of_eligible']:.1f}% | " + " | ".join(str(e['by_model'][m]) for m in MODELS) + " |")
    L_.append("")
(OUT / "TOP-RETAILERS.md").write_text("\n".join(L_) + "\n", encoding="utf-8")
L_ = ["# N1 — price entries by currency code, model and arm, human-labelled primary set (descriptive only; not a result of record)", "",
      "Entries, not answers; zero amounts and unstated currencies included; codes as the analysis set carries them (every alphabetic code other than BDT and USD is folded to 'other').", "",
      "| model | arm | BDT | USD | other | unstated | total |", "|---|---|---|---|---|---|---|"]
for m in MODELS:
    for a in ARMS3:
        c = res_d["counts"][m][a]; L_.append(f"| {m} | {a} | {c['BDT']} | {c['USD']} | {c['other']} | {c['unstated']} | {totals[m][a]} |")
for a in ARMS3:
    c = res_d["by_arm_all_models"][a]; L_.append(f"| all models | {a} | {c['BDT']} | {c['USD']} | {c['other']} | {c['unstated']} | {sum(c.values())} |")
L_ += ["", f"Zero-amount entries (model|arm|code: n): {res_d['zero_amount_entries']}", f"'other' entries: {len(other_entries)}; entries by the raw currency token in the raters' labels: {dict(other_tokens)}"]
(OUT / "PRICE-CURRENCY-COUNTS.md").write_text("\n".join(L_) + "\n", encoding="utf-8")
print("written:", OUT / "TOP-RETAILERS.json", OUT / "PRICE-CURRENCY-COUNTS.json")
print(json.dumps({"top3": {a: [(e["canonical_id"], e["class"], e["answers"]) for e in top10[a][:3]] for a in ARMS3}, "by_arm": res_d["by_arm_all_models"], "entries_by_raw_token": dict(other_tokens), "zero": res_d["zero_amount_entries"]}, indent=1))
