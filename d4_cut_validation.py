#!/usr/bin/env python3
"""d4_cut_validation.py — N1 §D.4: the second validation of the script-class cuts (prose_ratio >= 0.60 -> bn,
<= 0.20 -> Latin-class, between -> mixed) against the 300 human labels of the Round-2 main set (E.3), stratified
by script class, as D.4 registers ("the cuts are still validated a second time against the 300 human labels
stratified by script_class").

Descriptive; D.4 sets no threshold. For every answer the script class and prose ratio come from the coded corpus
(runs/coded/main.final.jsonl, the record the rater saw, found through the authors-only mapping); each rater's
answer_language and the E.3 consensus (majority of three; a three-way split has none) come from the banked
Round-2 exports. Reported: the full script-class x consensus-language table; the bn/Latin boundary as the cuts
draw it against the consensus and against each rater (a Bangla-class answer judged en or banglish, or a
Latin-class answer judged bn, would be a boundary error); the answers the mixed band holds and what D.4 then did
with them (the extractor decides their language outright; their final coded answer_language is set beside the
consensus); and the prose ratios that bracket the human judgements (lowest of any consensus-bn answer, highest of
any consensus-en or -banglish answer). For scale, the mixed band's reach in the corpus: per model and arm, the
answers in the reversion denominators (valid or language_reversion) whose script class is mixed, with their coded
language and outcome. Wilson 95% intervals throughout. Output holds aggregates only (plus the
rater-facing pids of boundary cases), never the pid-to-record mapping.

Usage (study root):  python d4_cut_validation.py  ->  D4-CUT-VALIDATION.json, D4-CUT-VALIDATION.md
"""
import argparse, csv, hashlib, json, math
from collections import Counter
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=".")
ap.add_argument("--runs", default=None)
a = ap.parse_args()
W = Path(a.root)
RUNS = Path(a.runs) if a.runs else W / "runs"
GATES = {
    W / "LABEL-ROUND2-R1-labels.json": "53f46eba77861230",
    W / "LABEL-ROUND2-R2-labels.json": "335dd4dd4f5253ab",
    W / "LABEL-ROUND2-R3-labels.json": "fea46917cba90890",
    W / "ROUND2-MAPPING-authors-only.csv": "e458a3c539077772",
    RUNS / "coded" / "main.final.jsonl": "b40a1cb9d9ab",
}
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
for p, want in GATES.items():
    if not sha(p).startswith(want):
        raise SystemExit(f"INPUT GATE: {p.name} is not the registered file")
N, RATERS = 300, ("R1", "R2", "R3")
LO, HI = 0.20, 0.60

def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [c - h, c + h]

lab = {}
for c in RATERS:
    with open(W / f"LABEL-ROUND2-{c}-labels.json", encoding="utf-8") as fh:
        d = json.load(fh)
    assert d["rater"] == c and d["task"] == "N1 labelling round 2" and not d.get("partial")
    lab[c] = {r["pid"]: r["answer_language"] for r in d["labels"]}
    assert len(lab[c]) == N
with open(W / "ROUND2-MAPPING-authors-only.csv", encoding="utf-8") as fh:
    mapping = {m["pid"]: m for m in csv.DictReader(fh)}
PIDS = [f"M{i:03d}" for i in range(1, N + 1)]
assert set(mapping) == set(PIDS)
coded = {}
with open(RUNS / "coded" / "main.final.jsonl", encoding="utf-8") as fh:
    for l in fh:
        if l.strip():
            r = json.loads(l)
            coded[r["key"]] = r

rows = []
for pid in PIDS:
    r = coded[mapping[pid]["key"]]
    assert r["script_class"] == mapping[pid]["script_class"]
    pr = float(r["prose_ratio"])
    sc = r["script_class"]
    assert (sc == "bn") == (pr >= HI) and (sc == "latin") == (pr <= LO), (pid, sc, pr)   # the cuts as coded
    langs = [lab[c][pid] for c in RATERS]
    mc = Counter(langs).most_common()
    cons = mc[0][0] if mc[0][1] >= 2 else None
    rows.append({"pid": pid, "class": sc, "prose_ratio": pr, "raters": langs, "consensus": cons,
                 "final_language": r["answer_language"], "outcome": r["outcome"]})

CLASSES = ("bn", "mixed", "latin")
table = {sc: dict(Counter((x["consensus"] or "no-majority") for x in rows if x["class"] == sc)) for sc in CLASSES}
n_class = {sc: sum(1 for x in rows if x["class"] == sc) for sc in CLASSES}
LATIN_LANGS = ("en", "banglish")
# boundary errors against the consensus and against each rater
b_err_bn = [x["pid"] for x in rows if x["class"] == "bn" and x["consensus"] in LATIN_LANGS]
b_err_lat = [x["pid"] for x in rows if x["class"] == "latin" and x["consensus"] == "bn"]
per_rater = {}
for k, c in enumerate(RATERS):
    per_rater[c] = {
        "bn_class_judged_bn": sum(1 for x in rows if x["class"] == "bn" and x["raters"][k] == "bn"),
        "bn_class_judged_en_or_banglish": sum(1 for x in rows if x["class"] == "bn" and x["raters"][k] in LATIN_LANGS),
        "latin_class_judged_bn": sum(1 for x in rows if x["class"] == "latin" and x["raters"][k] == "bn"),
        "mixed_class_judged_bn": sum(1 for x in rows if x["class"] == "mixed" and x["raters"][k] == "bn")}
bn_ok = sum(1 for x in rows if x["class"] == "bn" and x["consensus"] == "bn")
lat_ok = sum(1 for x in rows if x["class"] == "latin" and x["consensus"] in LATIN_LANGS)
mixed_rows = [x for x in rows if x["class"] == "mixed"]
mixed_final = dict(Counter(f"{x['consensus'] or 'no-majority'}->{x['final_language']}" for x in mixed_rows))
mixed_final_agree = sum(1 for x in mixed_rows if x["consensus"] is not None and x["final_language"] == x["consensus"])
reach, denom = Counter(), Counter()
for r in coded.values():
    if r["outcome"] in ("valid", "language_reversion"):
        denom[(r["model_id"], r["arm"])] += 1
        if r["script_class"] == "mixed":
            reach[(r["model_id"], r["arm"], r["answer_language"], r["outcome"])] += 1
corpus_band = {"answers_in_reversion_denominators": sum(denom.values()),
               "mixed_class": sum(reach.values()),
               "by_model_arm": {f"{m}|{arm}": {"mixed_class": sum(v for (m2, a2, _, _), v in reach.items() if (m2, a2) == (m, arm)),
                                               "denominator": denom[(m, arm)],
                                               "coded": {f"{lg}/{oc}": v for (m2, a2, lg, oc), v in reach.items() if (m2, a2) == (m, arm)}}
                                for (m, arm) in sorted(denom)}}
cons_bn = [x["prose_ratio"] for x in rows if x["consensus"] == "bn"]
cons_lat = [x["prose_ratio"] for x in rows if x["consensus"] in LATIN_LANGS]
out = {"task": "N1 D.4 second validation of the script-class cuts on the Round-2 main 300 (E.3)",
       "cuts": {"bn_if_prose_ratio_at_least": HI, "latin_if_prose_ratio_at_most": LO},
       "n_by_class": n_class, "class_by_consensus": table,
       "bn_class_consensus_bn": {"k": bn_ok, "n": n_class["bn"], "wilson95": wilson(bn_ok, n_class["bn"])},
       "latin_class_consensus_en_or_banglish": {"k": lat_ok, "n": n_class["latin"], "wilson95": wilson(lat_ok, n_class["latin"])},
       "boundary_errors_vs_consensus": {"bn_class_judged_en_or_banglish": b_err_bn, "latin_class_judged_bn": b_err_lat},
       "per_rater": per_rater,
       "mixed_band": {"n": len(mixed_rows), "consensus_to_final_coded_language": mixed_final,
                      "final_equals_consensus": mixed_final_agree,
                      "prose_ratio_range": [min(x["prose_ratio"] for x in mixed_rows), max(x["prose_ratio"] for x in mixed_rows)]},
       "prose_ratio_bracket": {"min_over_consensus_bn": min(cons_bn), "max_over_consensus_en_or_banglish": max(cons_lat),
                               "n_consensus_bn": len(cons_bn), "n_consensus_en_or_banglish": len(cons_lat)},
       "non_boundary_cases": {"consensus_mixed_by_class": {sc: sum(1 for x in rows if x["class"] == sc and x["consensus"] == "mixed") for sc in CLASSES},
                              "consensus_other_by_class": {sc: sum(1 for x in rows if x["class"] == sc and x["consensus"] == "other") for sc in CLASSES},
                              "no_majority": [x["pid"] for x in rows if x["consensus"] is None]},
       "corpus_mixed_band": corpus_band,
       "inputs": {("runs/coded/" + p.name if p.parent.name == "coded" else p.name): sha(p) for p in GATES},
       "script_sha256": sha(Path(__file__))}
with open(W / "D4-CUT-VALIDATION.json", "w", encoding="utf-8", newline="\n") as fh:
    json.dump(out, fh, indent=1)
f = lambda k, n: f"{k}/{n} ({100 * k / n:.1f}%, Wilson 95% {100 * wilson(k, n)[0]:.1f}–{100 * wilson(k, n)[1]:.1f}%)"
L = ["# N1 — D.4 second validation of the script-class cuts (Round-2 main 300)", "",
     f"Cuts: prose_ratio ≥ {HI} → bn; ≤ {LO} → Latin-class; between → mixed (the extractor decides). "
     "Consensus = majority of the three raters (E.3).", "",
     "| script class | answers | " + " | ".join(("bn", "en", "banglish", "mixed", "other", "no-majority")) + " |",
     "|---|---|---|---|---|---|---|---|"]
for sc in CLASSES:
    L.append(f"| {sc} | {n_class[sc]} | " + " | ".join(str(table[sc].get(k, 0)) for k in ("bn", "en", "banglish", "mixed", "other", "no-majority")) + " |")
L += ["", f"- Bangla-class answers the consensus calls bn: {f(bn_ok, n_class['bn'])}; called en or banglish: {len(b_err_bn)}.",
      f"- Latin-class answers the consensus calls en or banglish: {f(lat_ok, n_class['latin'])}; called bn: {len(b_err_lat)}.",
      "- Per rater (R1, R2, R3): Bangla-class judged bn " + ", ".join(str(per_rater[c]["bn_class_judged_bn"]) for c in RATERS) +
      f" of {n_class['bn']}; Bangla-class judged en/banglish " + ", ".join(str(per_rater[c]["bn_class_judged_en_or_banglish"]) for c in RATERS) +
      "; Latin-class judged bn " + ", ".join(str(per_rater[c]["latin_class_judged_bn"]) for c in RATERS) + ".",
      f"- Mixed band: {len(mixed_rows)} answers (prose ratio {out['mixed_band']['prose_ratio_range'][0]:.3f}–"
      f"{out['mixed_band']['prose_ratio_range'][1]:.3f}); consensus → final coded language: " +
      ", ".join(f"{k} {v}" for k, v in sorted(mixed_final.items())) + f"; final equals consensus in {mixed_final_agree}.",
      f"- Prose-ratio bracket: lowest of any consensus-bn answer {min(cons_bn):.3f} (n {len(cons_bn)}); highest of any "
      f"consensus-en/banglish answer {max(cons_lat):.3f} (n {len(cons_lat)}).", ""]
with open(W / "D4-CUT-VALIDATION.md", "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(L))
print("\n".join(L))
