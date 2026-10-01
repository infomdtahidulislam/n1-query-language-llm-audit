#!/usr/bin/env python3
"""n1_language_confusion.py — N1: answer-language confusion on the 300 validation answers (declared in the post-freeze
record of 28 Sep 2026). Deterministic counts; no seed; no test; outside the results of record; no label changes.

Join, for every one of the 300 validation-sample answers: the three-rater E.3 consensus language (ROUND2-CONSENSUS.json),
the deterministic script class and the raw extractor language label (ROUND2-MAPPING-authors-only.csv, the authors' key
map), and the final pipeline language (runs/coded/main.final.jsonl, the row of the same answer). Confusion matrix of the
final language: rows = consensus (every recorded category; a consensus with no two-rater majority counted as "no
consensus"), columns = final code (every recorded category; an answer with no final code counted as "no final code"),
in counts and row percentages, overall and for the Bangla, Latin and mixed script strata. The three decisions of D.4 are
separated: (1) the deterministic override on the Bangla/Latin boundary (Bangla-class answers whose extractor label was not
Bangla, and Latin-class answers whose extractor label was Bangla, which the deterministic class overrides); (2) the
extractor's English-versus-Banglish decision for Latin-class answers; (3) the extractor's decision for mixed-band answers.
Self-test (registered value): the raw extractor label agrees with the consensus on 269 of the 292 answers where both
are defined (the E.6 main-contest answer_language accuracy 269/292 = 0.9212 of the record of 22 Sep 2026); --selftest-only
stops there. The final pipeline code is compared with the consensus only descriptively (below).

Usage (study root):  python exploratory/n1_language_confusion.py  ->  exploratory/LANGUAGE-CONFUSION.json / .md
"""
import argparse, csv, datetime, hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path

ap = argparse.ArgumentParser(); ap.add_argument("root", nargs="?", default="."); ap.add_argument("--selftest-only", action="store_true")
A = ap.parse_args(); ROOT = Path(A.root); OUT = ROOT / "exploratory"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
CONS = json.load(open(ROOT / "ROUND2-CONSENSUS.json", encoding="utf-8"))
assert CONS["n"] == 300 and len(CONS["items"]) == 300
MAP = {r["pid"]: r for r in csv.DictReader(open(ROOT / "ROUND2-MAPPING-authors-only.csv", encoding="utf-8"))}
assert len(MAP) == 300 and set(MAP) == set(CONS["items"])
final = {}
for l in open(ROOT / "runs/coded/main.final.jsonl", encoding="utf-8"):
    r = json.loads(l); final[r["key"]] = r
NOCONS, NOFINAL = "no consensus", "no final code"
rows = []
for pid, c in CONS["items"].items():
    m = MAP[pid]; f = final[m["key"]]
    norm = lambda x: "" if x in (None, "", "None") else str(x)
    assert f["script_class"] == m["script_class"] and norm(f.get("extractor_answer_language")) == norm(m["extractor_answer_language"]), pid
    rows.append({"pid": pid, "arm": m["arm"], "model": m["model_id"], "script_class": f["script_class"],
                 "extractor": f.get("extractor_answer_language") or "no extractor label", "final": f.get("answer_language") or NOFINAL,
                 "consensus": c["answer_language"] or NOCONS, "outcome": f["outcome"], "adjudicate_reason": f.get("adjudicate_reason")})
both_x = [r for r in rows if r["consensus"] != NOCONS and r["extractor"] != "no extractor label"]
agree_x = sum(1 for r in both_x if r["consensus"] == r["extractor"])
assert (agree_x, len(both_x)) == (269, 292), (agree_x, len(both_x))
print(f"self-test OK: raw extractor label = consensus on {agree_x} of {len(both_x)} answers with both defined (E.6: 0.9212)")
both = [r for r in rows if r["consensus"] != NOCONS and r["final"] != NOFINAL]
agree = sum(1 for r in both if r["consensus"] == r["final"])
if A.selftest_only:
    sys.exit(0)

CATS_ROW = ["en", "bn", "banglish", "mixed", "other", NOCONS]
CATS_COL = ["en", "bn", "banglish", "mixed", "other", "latin_unresolved", NOFINAL]
def matrix(rs, rowkey="consensus", colkey="final", cols=CATS_COL):
    cnt = Counter((r[rowkey], r[colkey]) for r in rs)
    rowcats = [c for c in CATS_ROW if any(k[0] == c for k in cnt)] + sorted({k[0] for k in cnt} - set(CATS_ROW))
    colcats = [c for c in cols if any(k[1] == c for k in cnt)] + sorted({k[1] for k in cnt} - set(cols))
    counts = {rc: {cc: cnt.get((rc, cc), 0) for cc in colcats} for rc in rowcats}
    pct = {rc: {cc: (100.0 * counts[rc][cc] / sum(counts[rc].values())) if sum(counts[rc].values()) else None for cc in colcats} for rc in rowcats}
    return {"rows": rowcats, "cols": colcats, "counts": counts, "row_pct": pct, "n": len(rs),
            "agreement": {"n_both_defined": sum(1 for r in rs if r[rowkey] not in (NOCONS,) and r[colkey] not in (NOFINAL, "no extractor label")),
                          "n_agree": sum(1 for r in rs if r[rowkey] == r[colkey] and r[rowkey] not in (NOCONS,))}}
res = {"overall": matrix(rows), "by_script_class": {sc: matrix([r for r in rows if r["script_class"] == sc]) for sc in ("bn", "latin", "mixed")}}
# the three D.4 decisions
d1 = [r for r in rows if (r["script_class"] == "bn" and r["extractor"] != "bn") or (r["script_class"] == "latin" and r["extractor"] == "bn")]
d2 = [r for r in rows if r["script_class"] == "latin" and r["extractor"] != "bn"]
d3 = [r for r in rows if r["script_class"] == "mixed"]
res["decisions"] = {
    "1_deterministic_override_on_the_boundary": {"n": len(d1), "extractor_labels": dict(Counter(r["extractor"] for r in d1)),
                                                  "final_vs_consensus": matrix(d1), "extractor_vs_consensus": matrix(d1, colkey="extractor", cols=["en", "bn", "banglish", "mixed", "other", "no extractor label"]),
                                                  "note": "Bangla-class answers with a non-Bangla extractor label (final = bn by D.4) and Latin-class answers the extractor called Bangla (none in the sample if the count is 0)"},
    "2_extractor_en_vs_banglish_for_latin_class": {"n": len(d2), "extractor_labels": dict(Counter(r["extractor"] for r in d2)),
                                                    "extractor_vs_consensus": matrix(d2, colkey="extractor", cols=["en", "bn", "banglish", "mixed", "other", "no extractor label"]), "final_vs_consensus": matrix(d2)},
    "3_extractor_decides_mixed_band": {"n": len(d3), "extractor_labels": dict(Counter(r["extractor"] for r in d3)),
                                       "extractor_vs_consensus": matrix(d3, colkey="extractor", cols=["en", "bn", "banglish", "mixed", "other", "no extractor label"]), "final_vs_consensus": matrix(d3)}}
res["strata_sizes"] = dict(Counter(r["script_class"] for r in rows))
res["agreement"] = {"final_vs_consensus": {"n_agree": agree, "n_both_defined": len(both)}, "extractor_vs_consensus": {"n_agree": agree_x, "n_both_defined": len(both_x)}}
res["no_final_code_by_outcome"] = dict(Counter(r["outcome"] for r in rows if r["final"] == NOFINAL))
res["no_consensus"] = sum(1 for r in rows if r["consensus"] == NOCONS)
res["extractor_vs_consensus_overall"] = matrix(rows, colkey="extractor", cols=["en", "bn", "banglish", "mixed", "other", "no extractor label"])
res["no_extraction"] = {"pids": CONS["no_extraction_pids"], "n": len(CONS["no_extraction_pids"])}
meta = {"task": "answer-language confusion on the 300 validation answers (descriptive counts; no test; outside the results of record; no label changed)",
        "inputs": {"ROUND2-CONSENSUS.json": sha(ROOT / "ROUND2-CONSENSUS.json"), "ROUND2-MAPPING-authors-only.csv": sha(ROOT / "ROUND2-MAPPING-authors-only.csv"),
                   "runs/coded/main.final.jsonl": sha(ROOT / "runs/coded/main.final.jsonl")},
        "script_sha256": sha(Path(__file__)), "run_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
OUT.mkdir(exist_ok=True)
json.dump({"meta": meta, "results": res, "rows": rows}, open(OUT / "LANGUAGE-CONFUSION.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)

def md_matrix(M, title):
    L = [f"### {title} (n = {M['n']})", "", "| consensus \\ final | " + " | ".join(M["cols"]) + " | row total |", "|---" * (len(M["cols"]) + 2) + "|"]
    for rc in M["rows"]:
        tot = sum(M["counts"][rc].values())
        L.append(f"| {rc} | " + " | ".join(f"{M['counts'][rc][cc]} ({M['row_pct'][rc][cc]:.0f}%)" for cc in M["cols"]) + f" | {tot} |")
    return L + [""]
L_ = ["# N1 — answer language on the 300 validation answers: consensus vs final pipeline code (descriptive only)", "",
      f"Strata by deterministic script class: {res['strata_sizes']}; {res['no_extraction']['n']} answers without an extraction; answers without a final code by outcome: {res['no_final_code_by_outcome']}; {res['no_consensus']} answer without a two-rater language majority. "
      f"Agreement where both defined: final code {agree} of {len(both)}; raw extractor label {agree_x} of {len(both_x)} (the registered E.6 value).", ""]
L_ += md_matrix(res["overall"], "Overall — final pipeline code")
M = res["extractor_vs_consensus_overall"]
L_ += [f"### Overall — raw extractor label (n = {M['n']})", "", "| consensus \\ extractor | " + " | ".join(M["cols"]) + " | row total |", "|---" * (len(M["cols"]) + 2) + "|"]
for rc in M["rows"]:
    L_.append(f"| {rc} | " + " | ".join(f"{M['counts'][rc][cc]} ({M['row_pct'][rc][cc]:.0f}%)" for cc in M["cols"]) + f" | {sum(M['counts'][rc].values())} |")
L_.append("")
for sc in ("bn", "latin", "mixed"):
    L_ += md_matrix(res["by_script_class"][sc], f"Script class {sc}")
for k, v in res["decisions"].items():
    L_ += [f"## Decision {k} (n = {v['n']}; extractor labels {v['extractor_labels']})", ""] + md_matrix(v["final_vs_consensus"], "final code vs consensus")
    M = v["extractor_vs_consensus"]
    L_ += [f"### raw extractor label vs consensus (n = {M['n']})", "", "| consensus \\ extractor | " + " | ".join(M["cols"]) + " |", "|---" * (len(M["cols"]) + 1) + "|"]
    for rc in M["rows"]:
        L_.append(f"| {rc} | " + " | ".join(str(M["counts"][rc][cc]) for cc in M["cols"]) + " |")
    L_.append("")
(OUT / "LANGUAGE-CONFUSION.md").write_text("\n".join(L_) + "\n", encoding="utf-8")
print("written:", OUT / "LANGUAGE-CONFUSION.json", OUT / "LANGUAGE-CONFUSION.md")
print(json.dumps({"agreement": res["agreement"], "no_final_code_by_outcome": res["no_final_code_by_outcome"], "overall_counts": res["overall"]["counts"],
                  "decisions": {k: {"n": v["n"], "extractor_labels": v["extractor_labels"], "final_vs_consensus_counts": v["final_vs_consensus"]["counts"]} for k, v in res["decisions"].items()}}, indent=1))
