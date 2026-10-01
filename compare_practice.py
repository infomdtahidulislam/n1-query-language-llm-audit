#!/usr/bin/env python3
"""Compare the three raters' Session-B practice labels and build the joint-session
agenda (N1, 11 Sep 2026). Per-field three-way agreement, casefolded set comparison,
majority consensus, and — authors-only — the extractor's own label as a reference
line. Prints a DISAGREEMENT AGENDA (every pid where the three differ on any field),
ordered by how much they differ, for the joint session to work through.

Usage:  python compare_practice.py [--dir .]         # needs the 3 exports present
        python compare_practice.py --selftest        # runs the agreement math on fixtures
The three exports are LABEL-PRACTICE-R1/R2/R3-labels.json. Never edits them.
"""
import argparse, csv, json, re, sys
from pathlib import Path

RATERS = ["R1", "R2", "R3"]
SET_FIELDS = ["brands", "recommended", "retailers"]
CAT_FIELDS = ["answer_language", "refused"]

def cf(s):  # casefold a surface form, strip separators/space
    return re.sub(r"[\s,]+", "", str(s).strip().casefold())

def price_set(lines):
    out = set()
    for ln in lines or []:
        parts = str(ln).split()
        if not parts: continue
        amt = re.sub(r"[,\s]", "", parts[0])
        cur = (parts[1].upper() if len(parts) > 1 else "UNSTATED")
        cur = {"TK": "BDT", "TAKA": "BDT", "৳": "BDT", "$": "USD", "DOLLAR": "USD"}.get(cur, cur)
        out.add((amt, cur))
    return out

def f1(a, b):
    if not a and not b: return 1.0
    if not a or not b: return 0.0
    inter = len(a & b)
    if inter == 0: return 0.0
    p, r = inter / len(b), inter / len(a)
    return 2 * p * r / (p + r)

def three_way_set_agreement(sets):  # mean pairwise F1 over the 3 rater pairs
    a, b, c = sets
    return round((f1(a, b) + f1(a, c) + f1(b, c)) / 3, 3)

def majority_set(sets):  # element in >=2 raters' sets
    from collections import Counter
    ct = Counter()
    for s in sets:
        ct.update(s)
    return {e for e, n in ct.items() if n >= 2}

def load(d):
    labs = {}
    for r in RATERS:
        p = Path(d) / f"LABEL-PRACTICE-{r}-labels.json"
        if not p.exists():
            return None, f"missing {p.name}"
        j = json.loads(p.read_text(encoding="utf-8"))
        assert j.get("rater") == r, f"{p.name} is not rater {r}"
        labs[r] = {row["pid"]: row for row in j["labels"]}
    return labs, None

def report(d):
    labs, err = load(d)
    if err:
        print("Cannot compare yet:", err)
        print("Place LABEL-PRACTICE-R1/R2/R3-labels.json here and re-run.")
        return
    mp = {r["pid"]: r for r in csv.DictReader(open(Path(d) / "PRACTICE-MAPPING-authors-only.csv", encoding="utf-8"))}
    pids = sorted(mp)
    # load extractor reference (authors-only) from the mapping's key if available
    print(f"Session B practice — three-way agreement over {len(pids)} answers\n")

    # categorical fields
    for fld in CAT_FIELDS:
        unan = maj = split = 0
        for p in pids:
            vals = [labs[r][p].get(fld, "") for r in RATERS]
            if vals[0] == vals[1] == vals[2] and vals[0] != "": unan += 1
            elif len(set(vals)) <= 2 and max(vals.count(v) for v in set(vals)) >= 2: maj += 1
            else: split += 1
        print(f"  {fld:16} unanimous {unan:2}/{len(pids)}   majority {maj:2}   three-way split {split:2}")

    # set fields
    for fld in SET_FIELDS:
        agrs = []
        for p in pids:
            sets = [set(cf(x) for x in labs[r][p].get(fld, [])) for r in RATERS]
            agrs.append(three_way_set_agreement(sets))
        print(f"  {fld:16} mean pairwise F1 {sum(agrs)/len(agrs):.3f}   "
              f"(perfect on {sum(1 for a in agrs if a==1.0)}/{len(pids)})")
    # prices
    pagr = []
    for p in pids:
        sets = [price_set(labs[r][p].get("prices", [])) for r in RATERS]
        pagr.append(three_way_set_agreement(sets))
    print(f"  {'prices':16} mean pairwise F1 {sum(pagr)/len(pagr):.3f}   "
          f"(perfect on {sum(1 for a in pagr if a==1.0)}/{len(pids)})")

    # authors-only: consensus (>=2 raters) vs the extractor's own label
    if any("extractor_answer_language" in r for r in mp.values()):
        def cf_set(xs): return set(cf(x) for x in xs)
        lang_hit = ref_lang_total = 0
        brand_f1s = []
        for p in pids:
            langs = [labs[r][p].get("answer_language", "") for r in RATERS]
            from collections import Counter
            cons_lang = Counter(langs).most_common(1)[0][0]
            ex_lang = mp[p].get("extractor_answer_language", "")
            if ex_lang:
                ref_lang_total += 1
                lang_hit += (cons_lang == ex_lang)
            cons_brands = majority_set([cf_set(labs[r][p].get("brands", [])) for r in RATERS])
            ex_brands = cf_set([b for b in (mp[p].get("extractor_brands", "") or "").split("|") if b])
            brand_f1s.append(f1(cons_brands, ex_brands))
        print("\n[authors-only] consensus vs extractor: "
              f"answer_language match {lang_hit}/{ref_lang_total}   "
              f"brand-set mean F1 {sum(brand_f1s)/len(brand_f1s):.3f}  "
              f"(reference only — practice is not a gate; E.6 is the real gate on the 100/300 sets)")

    # disagreement agenda
    print("\nDISAGREEMENT AGENDA (joint session works through these, worst first):")
    agenda = []
    for p in pids:
        issues = []
        for fld in CAT_FIELDS:
            vals = [labs[r][p].get(fld, "") for r in RATERS]
            if len(set(vals)) > 1:
                issues.append(f"{fld}: " + "/".join(f"{r}={labs[r][p].get(fld) or '-'}" for r in RATERS))
        for fld in SET_FIELDS + ["prices"]:
            getter = price_set if fld == "prices" else (lambda xs: set(cf(x) for x in xs))
            sets = [getter(labs[r][p].get(fld, [])) for r in RATERS]
            if three_way_set_agreement(sets) < 1.0:
                shown = "/".join(r + "={" + ",".join(sorted(str(x) for x in s)) + "}" for r, s in zip(RATERS, sets))
                issues.append(f"{fld}: {shown}")
        cmts = [f"{r}: {labs[r][p]['comments']}" for r in RATERS if labs[r][p].get("comments")]
        if issues:
            agenda.append((len(issues), p, issues, cmts))
    agenda.sort(reverse=True)
    if not agenda:
        print("  none — all three raters agreed on every field of every answer.")
    for nfld, p, issues, cmts in agenda:
        print(f"\n  {p}  ({nfld} field(s) in disagreement)")
        for it in issues:
            print(f"     - {it}")
        for c in cmts:
            print(f"     · comment {c}")
    print(f"\n{len(agenda)} of {len(pids)} answers need discussion; {len(pids)-len(agenda)} were unanimous on every field.")

def selftest():
    import tempfile, os
    d = tempfile.mkdtemp()
    with open(Path(d) / "PRACTICE-MAPPING-authors-only.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["pid", "key"]); w.writerow(["P01", "k1"]); w.writerow(["P02", "k2"])
    base = {"P01": dict(brands=["Walton", "Samsung"], recommended=["Walton"], prices=["38000 BDT"],
                        retailers=["Daraz"], refused="false", answer_language="bn", comments=""),
            "P02": dict(brands=["Apple"], recommended=[], prices=[], retailers=[], refused="false",
                        answer_language="en", comments="")}
    labs = {"R1": json.loads(json.dumps(base)), "R2": json.loads(json.dumps(base)), "R3": json.loads(json.dumps(base))}
    # introduce disagreements: R2 casefold-only (should still agree), R3 real difference
    labs["R2"]["P01"]["brands"] = ["walton", "SAMSUNG"]          # casefold — agrees
    labs["R3"]["P01"]["answer_language"] = "mixed"               # cat disagreement
    labs["R3"]["P01"]["recommended"] = ["Walton", "Samsung"]     # set disagreement
    labs["R3"]["P01"]["comments"] = "torn bn vs mixed"
    for r in RATERS:
        out = {"task": "t", "rater": r, "labels": [dict(pid=p, **labs[r][p]) for p in ["P01", "P02"]]}
        (Path(d) / f"LABEL-PRACTICE-{r}-labels.json").write_text(json.dumps(out), encoding="utf-8")
    # checks
    assert three_way_set_agreement([{"walton"}, {"walton"}, {"walton"}]) == 1.0
    assert three_way_set_agreement([{"a"}, {"a"}, {"a", "b"}]) < 1.0
    assert price_set(["38,000 Tk", "500 USD"]) == {("38000", "BDT"), ("500", "USD")}
    assert majority_set([{"a", "b"}, {"a"}, {"a"}]) == {"a"}
    assert f1({"a", "b"}, {"a"}) == 2 * (1/1) * (1/2) / (1/1 + 1/2)
    print("selftest: agreement math OK\n")
    report(d)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: selftest()
    else: report(a.dir)
