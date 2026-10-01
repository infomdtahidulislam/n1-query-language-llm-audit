#!/usr/bin/env python3
"""n1_plan_audit.py — N1 §H.6: the registration-vs-execution audit, in the form of the researcher's thesis
plan audit (stage7_plan_audit.json: every pre-registered item with its plan section, an evidence key and a
status, totals on top), applied to N1's frozen registration and its post-freeze records.

Status is decided mechanically: an item is COMPUTED when every one of its evidence keys resolves in the study
files (a JSON path, a text anchor, a line count, a registration record title, or the freeze manifest); HELD when
it is conditionally registered and its evidence shows the condition was not met; OUTSTANDING when it is
registered but not yet done — either due later (write-up, release) or, where the evidence does not resolve,
missing. DROPPED would be a registered item abandoned; there is none by construction, and the script says so.
Standard library only; reads, never writes, anything but its two outputs.

Usage (study root):  python n1_plan_audit.py [--out N1-PLAN-AUDIT]  ->  <out>.json, <out>.md
"""
import argparse, hashlib, json, re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=".")
ap.add_argument("--out", default="N1-PLAN-AUDIT")
a = ap.parse_args()
W = Path(a.root)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
_cache = {}

def load_json(f):
    if f not in _cache:
        with open(W / f, encoding="utf-8") as fh:
            _cache[f] = json.load(fh)
    return _cache[f]

def text(f):
    k = ("t", f)
    if k not in _cache:
        _cache[k] = (W / f).read_text(encoding="utf-8")
    return _cache[k]

def check(spec):
    kind = spec[0]
    try:
        if kind == "json":
            _, f, path = spec
            x = load_json(f)
            for k in path:
                x = x[k]
            ok = x not in (None, {}, [], "")
            return ok, f"{f} → {'.'.join(path)}"
        if kind == "text":
            _, f, anchor = spec
            return anchor in text(f), f"{f} ⟨{anchor}⟩"
        if kind == "lines":
            _, f, n = spec
            with open(W / f, encoding="utf-8") as fh:
                k = sum(1 for l in fh if l.strip())
            return k == n, f"{f} ({n:,} records)"
        if kind == "field":
            _, f, field, n = spec
            k = 0
            with open(W / f, encoding="utf-8") as fh:
                for l in fh:
                    if l.strip() and json.loads(l).get(field) not in (None, ""):
                        k += 1
            return k == n, f"{f} → {field} on all {n:,} rows"
        if kind == "record":
            _, title = spec
            return text("prereg.md").count(title) == 1, f"prereg.md record ⟨{title[:90]}⟩"
        if kind == "count":
            _, f, anchor, at_least = spec
            return text(f).count(anchor) >= at_least, f"{f} ⟨{anchor}⟩ ×≥{at_least}"
        if kind == "h3":
            t = text("prereg.md")
            n_rec, n_h3 = t.count("Post-freeze record ("), t.count("the H.3 deviation log remains empty")
            return n_rec == n_h3 and n_rec > 0, f"prereg.md: all {n_rec} post-freeze records state the H.3 log is empty"
        if kind == "manifest":
            ok, n = True, 0
            for line in text("FREEZE-MANIFEST.sha256").splitlines():
                if line.strip() and not line.lstrip().startswith("#"):
                    h, name = line.split(None, 1)
                    name = name.strip().lstrip("*")
                    ok &= (W / name).exists() and sha(W / name) == h
                    n += 1
            return ok, f"FREEZE-MANIFEST.sha256 ({n} files verify)"
    except (KeyError, IndexError, TypeError, FileNotFoundError, ValueError):
        return False, f"{spec[1] if len(spec) > 1 else kind} (does not resolve)"
    raise ValueError(kind)

AR, SU = "ANALYSIS-RESULTS.json", "ANALYSIS-SUPPLEMENT.json"
J = lambda *p: ("json", AR, list(p))
JS = lambda *p: ("json", SU, list(p))
REC = lambda t: ("record", "Post-freeze record (" + t)
D_ = "due"
ITEMS = [
    # ---- pre-freeze
    ("pre-freeze", "every pre-freeze item (A.4–A.5 authoring and approval, F1–F13, calibration, smoke H.2, pilot G.1, contest G.2) closed at the freeze",
     [("text", "prereg.md", "Every pre-freeze item is closed"), ("text", "prereg.md", "**Status: FROZEN v1.0 — 16 September 2026.**")]),
    # ---- C
    ("§C.4", "main run: 24,000 cells answered (250 queries x 3 arms x 6 models x r = 5, plus bl_translit on robust50)",
     [REC("16 Sep 2026, main run — record only"), ("lines", "runs/coded/main.final.jsonl", 24045)]),
    ("§C.5/§D.6", "redraw rule: degenerate answers redrawn at most twice, persistent failures reported",
     [("text", "prereg.md", "D.6 redraw trail: all 52 degenerate answers"), ("json", "runs/coded/main.redraw_plan.json", ["persistently_degenerate"])]),
    ("§C.7", "main run inside at most 7 consecutive days; start and end reported",
     [("text", "WINDOW-CLOSEOUT.txt", "2026-09-16T09:39:10.488Z → 2026-09-16T15:41:09.888Z   span 0.25 days"), REC("27 Sep 2026, ledger and window close-out")]),
    ("§C.7", "model-string and fingerprint drift check against expected_models.json",
     [("text", "WINDOW-CLOSEOUT.txt", "OBSERVED MODEL STRINGS (H.4 expected values / C.7 drift check)"), REC("27 Sep 2026, ledger and window close-out")]),
    ("§C.7", "analyses re-run by period if a subject's string or fingerprint changed inside the window",
     [("text", "prereg.md", "and the run satisfies C.7.**")], "HELD", "no subject changed inside the window"),
    # ---- D
    ("§D.4", "deterministic script class on prose, cuts 0.60 / 0.20, on every answer",
     [("field", "runs/coded/main.final.jsonl", "script_class", 24045)]),
    ("§D.4", "every bn/Latin deterministic-vs-extractor disagreement filed and released",
     [("lines", "runs/coded/main.adjudicate.jsonl", 852)]),
    ("§D.4", "R1 adjudicates the seeded stratified 200 (seed 20260914); confirmation rate with Wilson 95% CI",
     [("text", "ADJUDICATION-MAIN-REPORT.md", "191/200 = 0.9550"), REC("21 Sep 2026, D.4 main adjudication closed")]),
    ("§D.4", "escalation to a second disjoint 200, then exhaustive, if the rate falls below 95%",
     [("text", "prereg.md", "is NOT met — no escalation")], "HELD", "191/200 = 0.9550 ≥ 0.95"),
    ("§D.4", "cuts validated a second time against the 300 human labels, stratified by script class",
     [("json", "D4-CUT-VALIDATION.json", ["class_by_consensus"]), REC("27 Sep 2026, D.4 cut validation")]),
    ("§D.4/§D.5", "reversion reported by the answer's script class, never pooled",
     [J("primary", "RQ5_reversion_breakdown", "results")]),
    ("§D.5", "outcome code for every answer (valid, reversion, conjunctive refusal, degenerate)",
     [("field", "runs/coded/main.final.jsonl", "outcome", 24045)]),
    # ---- E
    ("§E.1", "primary extraction of every answer; schema-invalid re-called at most twice; terminal failures excluded and reported",
     [REC("16 Sep 2026, primary extraction — record only"), ("text", "ANALYSIS-RESULTS.md", "7 without one (terminal schema failures)")]),
    ("§E.2", "cross-check pass on the stratified ~2,000",
     [("lines", "runs/extracted/main.cross_check.jsonl", 2000), ("json", "E2-AGREEMENT.json", ["brand_f1"]), REC("17 Sep 2026, E.2 cross-check — record only")]),
    ("§E.3", "300 main-run answers labelled independently by all three raters; consensus by majority",
     [("json", "ROUND2-CONSENSUS.json", ["items"]), ("json", "LABEL-ROUND2-R1-labels.json", ["labels"]), ("json", "LABEL-ROUND2-R2-labels.json", ["labels"]),
      ("json", "LABEL-ROUND2-R3-labels.json", ["labels"]), REC("22 Sep 2026, E.3/E.5/E.6 main — Round 2 closed")]),
    ("§E.4", "pilot ~100 labelled by all three raters (calibration follow-through; decides the contest)",
     [("text", "ROUND1-AGREEMENT-REPORT.md", "0.9825")]),
    ("§E.5", "human–human agreement: Krippendorff's alpha and pairwise set-F1",
     [("text", "ROUND2-AGREEMENT-REPORT.md", "Krippendorff's alpha")]),
    ("§E.5", "machine–human metrics against consensus, per machine",
     [("text", "ROUND2-AGREEMENT-REPORT.md", "0.8221"), REC("22 Sep 2026, E.6 contest closed — all three extractors scored")]),
    ("§E.5", "machine–machine metrics, primary vs cross-checker",
     [("json", "E2-AGREEMENT.json", ["outcome_agree"])]),
    ("§E.5/F5", "alt-test on the 300 with the three raters (ε 0.15, ω ≥ 0.5)",
     [("json", "ALT-TEST-RESULTS.json", ["per_rater"]), REC("27 Sep 2026, alt-test specification fixed"), REC("27 Sep 2026, alt-test run")]),
    ("§E.6", "gate on the pilot 100: primary brand-set F1 ≥ 0.90",
     [("text", "ROUND1-AGREEMENT-REPORT.md", "0.9825")]),
    ("§E.6", "gate on the main 300: primary brand-set F1 ≥ 0.90",
     [("text", "ROUND2-AGREEMENT-REPORT.md", "0.8221 -> **FAIL**")]),
    ("§E.6", "replacement contest: the three extractors scored on the same labels",
     [("lines", "runs/extracted/main.cross_check.e6-300.jsonl", 296), ("lines", "runs/extracted/main.fallback.e6-300.jsonl", 296),
      REC("22 Sep 2026, E.6 contest closed — all three extractors scored")]),
    ("§E.6", "escalation: human labelling expanded to a size set at that point",
     [("text", "EXPANSION-PROPOSAL.md", "#"), REC("22 Sep 2026, E.6 escalation sized and designed"), REC("26 Sep 2026, expansion labelling closed"),
      ("lines", "EXPANSION-ANALYSIS-SET-v2.jsonl", 3023)]),
    ("§E.6", "the extraction limitation reported prominently", [], "OUTSTANDING", "due at write-up (Methods and Limitations)"),
    # ---- Appendix C
    ("App. C.1–C.3", "brands new in the main run classified blind from an alphabetical list, before RQ2",
     [("json", "EXPANSION-ALIAS-DECISIONS.json", ["decisions"]), REC("27 Sep 2026, expansion name review closed"),
      REC("27 Sep 2026, correction to the name-review-closed record")]),
    ("App. C.5", "three-way ambiguity sensitivity for the local-brand share",
     [J("sensitivity", "RQ2_ambiguous_local"), J("sensitivity", "RQ2_ambiguous_global")]),
    # ---- F
    ("§F.1", "95% cluster-bootstrap CI on every estimate, 10,000 query resamples, per model, three contrasts",
     [J("meta", "bootstrap", "resamples")]),
    ("§F.2", "RQ1 excess divergence Δ, two-sided Wilcoxon over queries, per model per contrast", [J("primary", "RQ1_excess_divergence")]),
    ("§F.2", "RQ1 secondary: RBO p = 0.9 on first-mention order", [J("secondary", "RQ1_rbo")]),
    ("§F.2", "Jaccard convention J(∅,∅) = 1, J(∅,S) = 0",
     [("text", "n1_analysis.py", "(Jaccard; J(0,0) = 1,"), ("text", "n1_analysis.py", "def jaccard(a, b):\n    a, b = set(a), set(b)\n    if not a and not b:\n        return 1.0")]),
    ("§F.3", "RQ2 mention-level mixed logistic, random intercept query, per model", [J("primary", "RQ2_local_share")]),
    ("§F.3", "registered fallback where the model is not identifiable or does not converge",
     [J("primary", "RQ4_bdt_share", "results", "claude-sonnet-5", "contrasts", "bn-en", "fallback")]),
    ("§F.3", "ambiguous and unclassifiable mentions excluded, their rates reported",
     [J("primary", "RQ2_local_share", "results", "claude-sonnet-5", "arms", "en", "ambiguous_rate")]),
    ("§F.3", "recommended-only sensitivity", [J("sensitivity", "RQ2_recommended_only")]),
    ("§F.4", "RQ4 price-mention rate (answer-level mixed logistic)", [J("primary", "RQ4_price_mention")]),
    ("§F.4", "RQ4 BDT share of stated prices", [J("primary", "RQ4_bdt_share")]),
    ("§F.4", "retailer-set overlap across arms (as F.2)", [J("secondary", "RQ4_retailer_overlap")]),
    ("§F.4", "local-retailer share (F3 list adopted), as F.3", [J("secondary", "RQ4_local_retailer_share")]),
    ("§F.4/App. C.5", "three-way ambiguity sensitivity for the local-retailer share (\"as in F.3\")",
     [JS("sensitivity", "RQ4_local_retailer_share_ambiguous_local"), JS("sensitivity", "RQ4_local_retailer_share_ambiguous_global")]),
    ("§F.5", "RQ5 reversion per arm with CIs; bn–bl mixed logistic per model", [J("primary", "RQ5_reversion")]),
    ("§F.5", "RQ5 refusal, three contrasts", [J("primary", "RQ5_refusal")]),
    ("§F.5", "degeneracy, three contrasts (first draw)", [J("exploratory", "RQ5_degeneracy_first_draw")]),
    ("§F.5", "length: linear mixed model on log completion tokens; valid-only as sensitivity (a)",
     [J("exploratory", "RQ5_length"), J("sensitivity", "RQ5_length_valid_only")]),
    ("§F.6", "primary analysis set: all non-refused, non-degenerate answers (valid + reversion)",
     [("text", "prereg.md", "In its F.6 primary set"), ("text", "prereg.md", "Reversion: bn and bl arms over non-refused, non-degenerate answers")]),
    ("§F.6 (a)", "valid-only, primary estimators (RQ1 Δ, RQ2, price-mention, BDT share)",
     [J("sensitivity", "RQ1_valid_only"), J("sensitivity", "RQ2_valid_only"), J("sensitivity", "RQ4_price_mention_valid_only"),
      J("sensitivity", "RQ4_bdt_share_valid_only")]),
    ("§F.6 (a)", "valid-only, the other F.2/F.4 estimators (RBO_ext, retailer-set divergence, local-retailer share)",
     [JS("sensitivity", "RQ1_rbo_valid_only"), JS("sensitivity", "RQ4_retailer_overlap_valid_only"), JS("sensitivity", "RQ4_local_retailer_share_valid_only")]),
    ("§F.6 (b)", "refusal and degeneracy rates by arm and model, as outcomes in their own right",
     [J("primary", "RQ5_refusal", "results", "claude-sonnet-5", "arms"), J("exploratory", "RQ5_degeneracy_first_draw", "results")]),
    ("§F.6 (c)", "truncated answers removed, primary estimators",
     [J("sensitivity", "RQ1_no_truncated"), J("sensitivity", "RQ2_no_truncated"), J("sensitivity", "RQ4_price_mention_no_truncated"),
      J("sensitivity", "RQ4_bdt_share_no_truncated")]),
    ("§F.6 (c)", "truncated answers removed, the other F.2/F.4 estimators",
     [JS("sensitivity", "RQ1_rbo_no_truncated"), JS("sensitivity", "RQ4_retailer_overlap_no_truncated"), JS("sensitivity", "RQ4_local_retailer_share_no_truncated")]),
    ("§F.6 (d)", "mixed-language answers removed, primary estimators",
     [J("sensitivity", "RQ1_no_mixed"), J("sensitivity", "RQ2_no_mixed"), J("sensitivity", "RQ4_price_mention_no_mixed"), J("sensitivity", "RQ4_bdt_share_no_mixed")]),
    ("§F.6 (d)", "mixed-language answers removed, the other F.2/F.4 estimators",
     [JS("sensitivity", "RQ1_rbo_no_mixed"), JS("sensitivity", "RQ4_retailer_overlap_no_mixed"), JS("sensitivity", "RQ4_local_retailer_share_no_mixed")]),
    ("§F.7", "Holm within each of the six primary families, α = .05",
     [J("holm", f) for f in ("RQ1_excess_divergence", "RQ2_local_share", "RQ4_bdt_share", "RQ4_price_mention", "RQ5_reversion", "RQ5_refusal")]),
    ("§F.8", "software: Python 3.11+, statsmodels, R/lme4 as the registered fallback for the GLMM, fixed seeds",
     [J("meta", "software", "R"), J("meta", "bootstrap", "seeds")]),
    ("§F.8", "full analysis code released with the corpus", [], "OUTSTANDING", "due with the H.5 release"),
    ("§F.9", "China-trained vs Western, descriptive with CIs", [J("exploratory", "F9_china_vs_western")]),
    ("§F.10", "bn vs bl_translit and bl vs bl_translit on robust50: Δ and local share with bootstrap CIs",
     [J("secondary", "F10_RQ1"), J("secondary", "F10_RQ2"), J("secondary", "F10_RQ1_machine"), J("secondary", "F10_RQ2_machine")]),
    ("§F.10", "the F.2 secondary estimator too (\"same estimators as F.2–F.3\"): RBO_ext",
     [JS("secondary", "F10_RQ1_rbo"), JS("secondary", "F10_RQ1_rbo_machine")]),
    # ---- post-freeze registered additions
    ("rec. 22 Sep (escalation)", "layers: human labels confirmatory for RQ1, RQ2, RQ4; corpus for RQ5; machine layer secondary",
     [REC("22 Sep 2026, E.6 escalation sized and designed"), ("text", "prereg.md", "**Layers.** The expansion sample's human labels")]),
    ("rec. 22 Sep (escalation)", "RQ5 refusal sensitivity on the human labels", [J("sensitivity", "RQ5_refusal_human")]),
    ("rec. 26 Sep (zero price)", "zero-amount price entries removed (human and machine layers)",
     [J("sensitivity", "RQ4_price_mention_zero_removed"), J("sensitivity", "RQ4_bdt_share_zero_removed"),
      J("sensitivity", "machine_RQ4_price_mention_zero_removed"), J("sensitivity", "machine_RQ4_bdt_share_zero_removed")]),
    ("rec. 26 Sep (analysis set)", "not-a-brand names: RQ1 with them retained; RQ2 bounds with removed mentions counted local / global",
     [J("sensitivity", "RQ1_exclusions_retained"), J("sensitivity", "RQ2_excluded_as_local"), J("sensitivity", "RQ2_excluded_as_global")]),
    ("rec. 26 Sep (analysis set)", "machine layer (secondary) and human–machine concordance",
     [J("secondary", "machine_RQ1"), J("secondary", "machine_RQ2"), J("secondary", "machine_RQ4_price_mention"), J("secondary", "machine_RQ4_bdt_share"),
      J("secondary", "concordance_RQ1_machine_on_expansion"), J("secondary", "concordance_RQ2_machine_on_expansion")]),
    ("rec. 26 Sep (implementation)", "robustness (a): cluster bootstrap of every log-odds contrast of the primary families",
     [J("primary", "RQ2_local_share", "results", "claude-sonnet-5", "contrasts", "bn-en", "log_odds", "boot_ci"), J("meta", "glmm_boot")]),
    ("rec. 26 Sep (implementation)", "robustness (b): every GLMM-tested family refitted with (1|query:arm)",
     [J("sensitivity", f) for f in ("RQ2_local_share_het", "RQ4_price_mention_het", "RQ4_bdt_share_het", "RQ5_reversion_het", "RQ5_refusal_het")]),
    ("rec. 26 Sep (implementation)", "robustness (c): RQ1 randomization test", [J("sensitivity", "RQ1_permutation")]),
    ("rec. 26 Sep (implementation)", "every family decision set beside the checks; non-support stated",
     [("text", "ANALYSIS-ROBUSTNESS.md", "## Summary"), REC("27 Sep 2026, registered analyses run")]),
    ("rec. 26 Sep (implementation)", "persona-marked answers removed",
     [J("sensitivity", f) for f in ("RQ1_no_persona", "RQ2_no_persona", "RQ4_price_mention_no_persona", "RQ4_bdt_share_no_persona",
                                    "RQ5_reversion_no_persona", "RQ5_refusal_no_persona")]),
    ("rec. 26 Sep (implementation)", "BDT share with 'unstated' left out of the denominator", [J("sensitivity", "RQ4_bdt_share_unstated_excluded")]),
    ("rec. 26 Sep (implementation)", "local-retailer share on the F3 list only", [J("sensitivity", "RQ4_local_retailer_share_strict")]),
    ("rec. 26 Sep (implementation)", "like-for-like reversion to English (exploratory)", [J("exploratory", "RQ5_reversion_to_english")]),
    ("rec. 26 Sep (implementation)", "null calibration of the registered tests (40 + 40 synthetic studies)",
     [("json", "CALIBRATION-het0.json", ["rejection_at_05"]), ("json", "CALIBRATION-het05.json", ["rejection_at_05"])]),
    # ---- G, H, I
    ("§G.3", "cost ledger replaces every estimate: exact tokens, billed actuals",
     [("text", "LEDGER-CLOSEOUT.txt", "TOTAL BILLED BY THE GATEWAY"), REC("27 Sep 2026, ledger and window close-out")]),
    ("§H.3", "deviation log kept; every post-freeze record states its state",
     [("h3",)]),
    ("§H.4", "freeze packet: every frozen artifact still matches its hash", [("manifest",)]),
    ("§H.5", "release: corpus, extraction outputs, labels (rater codes only), code; gateway URL redacted by `release`", [], "OUTSTANDING", "due at submission"),
    ("§I.7", "the registered limitations stated in the paper", [], "OUTSTANDING", "due at write-up"),
]

out_items = []
for it in ITEMS:
    sec, item, ev = it[0], it[1], it[2]
    fixed = it[3] if len(it) > 3 else None
    note = it[4] if len(it) > 4 else None
    res = [check(s) for s in ev]
    ok = all(r[0] for r in res)
    if fixed == "HELD":
        status = "HELD" if ok else "OUTSTANDING"
    elif fixed == "OUTSTANDING":
        status = "OUTSTANDING"
    else:
        status = "COMPUTED" if ok and ev else "OUTSTANDING"
        if status == "OUTSTANDING":
            note = "evidence does not resolve: " + "; ".join(r[1] for r in res if not r[0])
    out_items.append({"plan_section": sec, "item": item, "evidence": [r[1] for r in res], "status": status,
                      **({"note": note} if note else {})})
counts = {s: sum(1 for x in out_items if x["status"] == s) for s in ("COMPUTED", "HELD", "OUTSTANDING", "DROPPED")}
NOTES = [
    "F.6's sentence on per-category (10 categories) breakdowns classifies any such breakdown as exploratory and registers none; none was run.",
    "The 16 and 17 Sep records' next-step lists name 'R1's seeded 200-answer coder audit'; the registration defines one seeded "
    "200-answer task for R1, the D.4 main-run adjudication (v0.46), audited above.",
    "Instrument: the plan audit of the researcher's thesis (the same 34-item audit in both of its experiments), applied here to "
    "N1's own registered items; the item list is N1's, not the thesis's.",
]
out = {"total": len(out_items), "computed": counts["COMPUTED"], "held": counts["HELD"], "outstanding": counts["OUTSTANDING"],
       "dropped": counts["DROPPED"], "notes": NOTES,
       "evidence_files": {f: sha(W / f) for f in sorted({s[1] for it in ITEMS for s in it[2] if s[0] in ("json", "text", "lines", "field", "count")})
                          if (W / f).exists()},
       "script_sha256": sha(Path(__file__)), "items": out_items}
with open(W / f"{a.out}.json", "w", encoding="utf-8", newline="\n") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
L = [f"# N1 — plan audit (H.6): registration vs execution", "",
     f"**{out['total']} registered items: {out['computed']} computed, {out['held']} held (conditional, not triggered), "
     f"{out['outstanding']} outstanding, {out['dropped']} dropped.**", "",
     "| # | section | item | status | evidence / note |", "|---|---|---|---|---|"]
for k, x in enumerate(out_items, 1):
    ev = "; ".join(x["evidence"]) if x["evidence"] else ""
    if x.get("note"):
        ev = (ev + " — " if ev else "") + x["note"]
    L.append(f"| {k} | {x['plan_section']} | {x['item']} | {x['status']} | {ev} |")
L += ["", "Notes:"] + [f"- {n}" for n in NOTES] + [""]
with open(W / f"{a.out}.md", "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(L))
print(f"{out['total']} items: {out['computed']} computed, {out['held']} held, {out['outstanding']} outstanding, {out['dropped']} dropped")
for x in out_items:
    if x["status"] == "OUTSTANDING":
        print(f"  OUTSTANDING  {x['plan_section']}: {x['item']}  [{x.get('note', '')}]")
