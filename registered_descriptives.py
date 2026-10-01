#!/usr/bin/env python3
"""registered_descriptives.py — N1: four registered descriptive reports the H.6 audit's item list did not carry
(pre-write-up check, 27 Sep 2026). Standard library only; runs on the study machine from the study root.

  D.5  hedged-but-answered counts (refusal detector fired, content present; code kept) by arm and model
  D.4  the full query-language x answer-language matrix per model, including the en-arm row (matrix-only)
  D.6  the cells left short at the 3-draw cap (persistently degenerate), enumerated
  E.5  machine-human accuracy on the OUTCOME CODE for the Round-2 300 (beside the refused and
       answer_language accuracies already reported): the code the registered rule (n1_pipeline.py D.5)
       assigns from the three-rater consensus label versus the code the machine assigned

Inputs: runs/coded/main.final.jsonl (all main-run draws; the final draw of a cell is its last draw),
ROUND2-CONSENSUS.json, ROUND2-MAPPING-authors-only.csv. Also recomputes the H.2/C.6 gate on bl_translit
two ways (all draws vs final draws) because the 16 Sep extraction record quoted the all-draws figure.
Outputs: REGISTERED-DESCRIPTIVES.json, REGISTERED-DESCRIPTIVES.md
"""
import csv, collections, hashlib, json
from pathlib import Path

ROOT = Path(".")
MODELS = ["claude-sonnet-5", "deepseek-v4-flash", "gemini-3-flash", "gpt-5.6-luna", "grok-4.6", "kimi-k3"]
ARMS = ["en", "bn", "bl", "bl_translit"]
TARGET = {"bn": "bn", "en": "en", "bl": "banglish", "bl_translit": "banglish"}     # n1_pipeline.ARM_TARGET
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

with open(ROOT / "runs/coded/main.final.jsonl", encoding="utf-8") as fh:
    rows = [json.loads(l) for l in fh]
assert all(r["phase"] == "main" for r in rows)
cells = {}
for r in rows:                                   # final draw = highest draw number of the cell
    k = (r["model_id"], r["query_id"], r["arm"], r["rep"])
    if k not in cells or r["draw"] > cells[k]["draw"]:
        cells[k] = r
final = list(cells.values())
assert len(final) == 24000 and len(rows) == 24045

out = {"task": "N1 registered descriptives (D.5 hedged, D.4 matrix, D.6 short cells, E.5 outcome-code accuracy)",
       "inputs": {"runs/coded/main.final.jsonl": sha(ROOT / "runs/coded/main.final.jsonl"),
                  "ROUND2-CONSENSUS.json": sha(ROOT / "ROUND2-CONSENSUS.json"),
                  "ROUND2-MAPPING-authors-only.csv": sha(ROOT / "ROUND2-MAPPING-authors-only.csv")},
       "rows_all_draws": len(rows), "cells_final": len(final)}

# D.5 hedged: F4 fired, content present, code kept (final draws)
hed = {m: {a: sum(1 for r in final if r["model_id"] == m and r["arm"] == a and r.get("hedged")) for a in ARMS} for m in MODELS}
den = {m: {a: sum(1 for r in final if r["model_id"] == m and r["arm"] == a) for a in ARMS} for m in MODELS}
out["D5_hedged_by_model_arm"] = {m: {a: {"hedged": hed[m][a], "answers": den[m][a]} for a in ARMS} for m in MODELS}
out["D5_hedged_total_final_draws"] = sum(hed[m][a] for m in MODELS for a in ARMS)
out["D5_hedged_total_all_draws"] = sum(1 for r in rows if r.get("hedged"))

# D.4 matrix: query language (arm) x coded answer language, per model, final draws; outcome shown for non-language rows
def lang_of(r):
    if r["outcome"] in ("refusal", "degenerate", "pending_extractor"):
        return r["outcome"]
    return r["answer_language"] or "unresolved"
mat = {m: {a: dict(collections.Counter(lang_of(r) for r in final if r["model_id"] == m and r["arm"] == a)) for a in ARMS} for m in MODELS}
out["D4_matrix_by_model"] = mat
out["D4_en_arm_non_english"] = {m: {k: v for k, v in mat[m]["en"].items() if k not in ("en", "refusal", "degenerate", "pending_extractor")} for m in MODELS}
out["D4_en_arm_language_reversion_rows"] = [{"model_id": r["model_id"], "query_id": r["query_id"], "rep": r["rep"], "answer_language": r["answer_language"]}
                                            for r in final if r["arm"] == "en" and r["outcome"] == "language_reversion"]

# D.6 short cells: final draw still degenerate
short = [r for r in final if r["outcome"] == "degenerate"]
out["D6_cells_left_short"] = [{"model_id": r["model_id"], "query_id": r["query_id"], "arm": r["arm"], "rep": r["rep"], "draws": r["draw"],
                              "reason": r.get("degenerate_reason")} for r in sorted(short, key=lambda r: (r["query_id"], r["arm"], r["rep"]))]
out["D6_degenerate_rows_all_draws"] = sum(1 for r in rows if r["outcome"] == "degenerate")

# H.2/C.6 gate on bl_translit, both bases
gate = {}
for m in MODELS:
    fa = [r for r in final if r["model_id"] == m and r["arm"] == "bl_translit"]
    al = [r for r in rows if r["model_id"] == m and r["arm"] == "bl_translit"]
    bad = lambda rr: sum(1 for r in rr if r["outcome"] in ("refusal", "degenerate"))
    gate[m] = {"final_draws": {"refusal_or_degenerate": bad(fa), "answers": len(fa), "rate": bad(fa) / len(fa)},
               "all_draws": {"refusal_or_degenerate": bad(al), "answers": len(al), "rate": bad(al) / len(al)}}
out["C6_gate_bl_translit"] = gate

# E.5 outcome-code accuracy on the Round-2 300
with open(ROOT / "ROUND2-CONSENSUS.json", encoding="utf-8") as fh:
    cons = json.load(fh)
with open(ROOT / "ROUND2-MAPPING-authors-only.csv", encoding="utf-8", newline="") as fh:
    mp = {r["pid"]: r for r in csv.DictReader(fh)}
assert len(mp) == 300 and len(cons["items"]) == 300
def human_code(item, arm):
    if item["refused"]:
        return "refusal"
    lang = item["answer_language"]
    if lang is None:
        return "no-majority"
    return "valid" if lang == TARGET[arm] else "language_reversion"
conf = collections.Counter()
n_scored = 0
agree = 0
per_class = collections.defaultdict(lambda: [0, 0])
for pid, item in cons["items"].items():
    row = mp[pid]
    if pid in cons["no_extraction_pids"]:
        conf[("(no machine extraction)", human_code(item, row["arm"]))] += 1
        continue
    h = human_code(item, row["arm"])
    if h == "no-majority":
        conf[(row["outcome"], "no-majority")] += 1
        continue
    n_scored += 1
    agree += (row["outcome"] == h)
    per_class[h][1] += 1
    per_class[h][0] += (row["outcome"] == h)
    conf[(row["outcome"], h)] += 1
out["E5_outcome_code"] = {"items": 300, "scored": n_scored, "agree": agree, "accuracy": agree / n_scored,
                          "recall_by_human_code": {k: {"agree": v[0], "n": v[1], "rate": v[0] / v[1]} for k, v in per_class.items()},
                          "confusion_machine_x_human": {f"{a}|{b}": n for (a, b), n in sorted(conf.items())},
                          "rule": "human code = refusal if consensus refused; else valid if consensus answer_language equals the arm's "
                                  "target (en->en, bn->bn, bl->banglish) else language_reversion (n1_pipeline.py D.5/D.4 rule applied "
                                  "to the consensus label); items without a majority language or without a machine extraction are "
                                  "listed, not scored"}
out["script_sha256"] = sha(Path(__file__))
with open(ROOT / "REGISTERED-DESCRIPTIVES.json", "w", encoding="utf-8", newline="\n") as fh:
    json.dump(out, fh, indent=1)

L = ["# N1 — registered descriptives (pre-write-up check, 27 Sep 2026)", "",
     f"Inputs: main.final.jsonl `{out['inputs']['runs/coded/main.final.jsonl'][:12]}…` ({len(rows):,} draws, {len(final):,} cells), "
     f"ROUND2-CONSENSUS.json, ROUND2-MAPPING-authors-only.csv. Script `{out['script_sha256'][:12]}…`.", "",
     "## D.5 hedged-but-answered (detector fired, content present; code kept) — final draws", "",
     "| model | " + " | ".join(ARMS) + " |", "|---|" + "---|" * len(ARMS)]
for m in MODELS:
    L.append(f"| {m} | " + " | ".join(f"{hed[m][a]} / {den[m][a]}" for a in ARMS) + " |")
L += ["", f"Total {out['D5_hedged_total_final_draws']:,} on final draws ({out['D5_hedged_total_all_draws']:,} over all draws, the figure of the 16 Sep extraction record).", "",
      "## D.4 query-language × answer-language matrix (final draws; refusal / degenerate / pending shown as their outcome)", ""]
for m in MODELS:
    L += [f"**{m}**", "", "| arm | " + " | ".join(sorted({k for a in ARMS for k in mat[m][a]})) + " |"]
    keys = sorted({k for a in ARMS for k in mat[m][a]})
    L.append("|---|" + "---|" * len(keys))
    for a in ARMS:
        L.append(f"| {a} | " + " | ".join(str(mat[m][a].get(k, 0)) for k in keys) + " |")
    L.append("")
L += ["en-arm answers coded language_reversion (matrix-only, D.4): " +
      (", ".join(f"{r['model_id']} {r['query_id']} rep {r['rep']} ({r['answer_language']})" for r in out["D4_en_arm_language_reversion_rows"]) or "none"), "",
      "## D.6 cells left short at the 3-draw cap", "", "| model | query | arm | rep | draws | reason |", "|---|---|---|---|---|---|"]
for c in out["D6_cells_left_short"]:
    L.append(f"| {c['model_id']} | {c['query_id']} | {c['arm']} | {c['rep']} | {c['draws']} | {c['reason']} |")
L += ["", f"{len(short)} cells; {out['D6_degenerate_rows_all_draws']} degenerate draws in all.", "",
      "## C.6 gate on bl_translit (refusal + degenerate), final draws vs all draws", "", "| model | final draws | all draws |", "|---|---|---|"]
for m in MODELS:
    g = gate[m]
    L.append(f"| {m} | {g['final_draws']['refusal_or_degenerate']} / {g['final_draws']['answers']} = {100 * g['final_draws']['rate']:.1f}% | "
             f"{g['all_draws']['refusal_or_degenerate']} / {g['all_draws']['answers']} = {100 * g['all_draws']['rate']:.1f}% |")
e = out["E5_outcome_code"]
L += ["", "## E.5 machine–human accuracy on the outcome code (Round-2 300)", "",
      f"Scored {e['scored']} of 300 (7 without a machine extraction and {300 - 7 - e['scored']} without a majority language listed, not scored): "
      f"accuracy {e['agree']}/{e['scored']} = {e['accuracy']:.4f}.", "", "| human code | machine agrees | n | rate |", "|---|---|---|---|"]
for k, v in e["recall_by_human_code"].items():
    L.append(f"| {k} | {v['agree']} | {v['n']} | {v['rate']:.4f} |")
L += ["", "Confusion (machine | human): " + ", ".join(f"{k}: {v}" for k, v in e["confusion_machine_x_human"].items()), "", e["rule"], ""]
with open(ROOT / "REGISTERED-DESCRIPTIVES.md", "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(L))
print(f"hedged {out['D5_hedged_total_final_draws']} | short cells {len(short)} | en-arm reversions {len(out['D4_en_arm_language_reversion_rows'])} | "
      f"E.5 outcome-code accuracy {e['agree']}/{e['scored']} = {e['accuracy']:.4f}")
for m in MODELS:
    print(f"  gate {m}: final {100 * gate[m]['final_draws']['rate']:.1f}% all {100 * gate[m]['all_draws']['rate']:.1f}%")
