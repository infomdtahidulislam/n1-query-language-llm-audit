#!/usr/bin/env python3
"""numbers_for_paper.py — N1: one compact sheet of the numbers the paper quotes, each read from its result file
and labelled with the file and key it comes from (nothing is typed by hand). Formatting only; no statistic is
computed here beyond rounding. Run from a folder holding the result files (the study root or N1-PACKAGE/06-results):
  python numbers_for_paper.py [dir]  ->  KEY-NUMBERS.md
"""
import hashlib, json, sys
from pathlib import Path

D = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name):
    with open(D / name, encoding="utf-8") as fh:
        return json.load(fh)
R, S, ALT, D4, AUD, DESC = (load(n) for n in ("ANALYSIS-RESULTS.json", "ANALYSIS-SUPPLEMENT.json", "ALT-TEST-RESULTS.json",
                                              "D4-CUT-VALIDATION.json", "N1-PLAN-AUDIT.json", "REGISTERED-DESCRIPTIVES.json"))
MODELS = ["claude-sonnet-5", "deepseek-v4-flash", "gemini-3-flash", "gpt-5.6-luna", "grok-4.6", "kimi-k3"]
PR, H, SE, SC, EX = R["primary"], R["holm"], R["sensitivity"], R["secondary"], R["exploratory"]
pz = lambda p: "–" if p is None else ("<.001" if p < 0.001 else f"{p:.3f}".lstrip("0"))
sg = lambda x, nd=3: "–" if x is None else (f"+{x:.{nd}f}" if x >= 0 else f"−{abs(x):.{nd}f}")
pp = lambda x: "–" if x is None else sg(100 * x, 1)
ci = lambda c, f=lambda v: f"{v:.3f}": "–" if not c or c[0] is None else f"[{f(c[0])}, {f(c[1])}]"
L = [f"# N1 — key numbers for the paper (generated {sys.argv[0].split('/')[-1]}; sources in brackets)", "",
     f"ANALYSIS-RESULTS.json `{sha(D / 'ANALYSIS-RESULTS.json')[:12]}…`, ANALYSIS-SUPPLEMENT.json `{sha(D / 'ANALYSIS-SUPPLEMENT.json')[:12]}…`, "
     f"ALT-TEST-RESULTS.json `{sha(D / 'ALT-TEST-RESULTS.json')[:12]}…`, D4-CUT-VALIDATION.json `{sha(D / 'D4-CUT-VALIDATION.json')[:12]}…`, "
     f"N1-PLAN-AUDIT.json `{sha(D / 'N1-PLAN-AUDIT.json')[:12]}…`, REGISTERED-DESCRIPTIVES.json `{sha(D / 'REGISTERED-DESCRIPTIVES.json')[:12]}…`.",
     "", f"Bootstrap: {R['meta']['bootstrap']['resamples']:,} query resamples, seeds {R['meta']['bootstrap']['seeds']}; GLMM bootstrap run: {R['meta']['glmm_boot']}. "
     f"Software: {R['meta']['software']}.", ""]

# ---- confirmatory families
L += ["## Confirmatory families (Holm within family, α = .05) — [primary.*, holm.*]", ""]
L += ["### RQ1 excess brand-set divergence (query-level Δ, cluster-bootstrap 95% CI, Wilcoxon p, Holm) — [primary.RQ1_excess_divergence, holm.RQ1_excess_divergence]", "",
      "| model | contrast | queries | mean Δ [95% CI] | p | p_Holm | reject |", "|---|---|---|---|---|---|---|"]
for m in MODELS:
    for c in ("bn-en", "bl-en", "bn-bl"):
        x = PR["RQ1_excess_divergence"]["results"][f"{m}|{c}"]; h = H["RQ1_excess_divergence"][f"{m}|{c}"]
        L.append(f"| {m} | {c} | {x['n_query']} | {sg(x['mean_delta'])} {ci(x['ci'])} | {pz(x['test']['p'])} | {pz(h['p_holm'])} | {'yes' if h['reject'] else 'no'} |")
def share_family(fam, title):
    arms = [a for a in ("en", "bn", "bl") if a in PR[fam]["results"][MODELS[0]]["arms"]]
    L.extend(["", f"### {title} — [primary.{fam}, holm.{fam}]", "", "| model | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)])
    for m in MODELS:
        r = PR[fam]["results"][m]
        L.append(f"| {m} | " + " | ".join((f"{r['arms'][a]['share']:.3f} {ci(r['arms'][a]['ci'])} (n {r['arms'][a]['n']:.0f})" if r["arms"][a].get("share") is not None else "–") for a in arms) + " |")
    L.extend(["", "| model | contrast | Δ pp [95% CI] | log-odds [Wald] | bootstrap CI of log-odds | test | p | p_Holm | reject |", "|---|---|---|---|---|---|---|---|---|"])
    for m in MODELS:
        r = PR[fam]["results"][m]
        for c, x in r["contrasts"].items():
            lo = x.get("log_odds") or {}
            los = f"{sg(lo['estimate'], 2)} [{sg(lo['ci_low'], 2)}, {sg(lo['ci_high'], 2)}]" if lo else "–"
            bci = ci(lo.get("boot_ci"), lambda v: sg(v, 2)) if lo else "–"
            t = x.get("test") or {}; h = H[fam][f"{m}|{c}"]
            meth = "GLMM Wald" if t.get("method") == "glmm_wald" else "F.3 fallback (paired Wilcoxon)"
            L.append(f"| {m} | {c} | {pp(x.get('diff'))} {ci(x.get('ci'), lambda v: pp(v))} | {los} | {bci} | {meth} | {pz(t.get('p'))} | {pz(h['p_holm'])} | {'yes' if h['reject'] else 'no'} |")
share_family("RQ2_local_share", "RQ2 local-brand share (answer-level, GLMM y ~ arm + (1|query))")
share_family("RQ4_price_mention", "RQ4 price-mention rate")
share_family("RQ4_bdt_share", "RQ4 BDT share among stated prices (all contrasts on the F.3 fallback — low power, report descriptively)")
share_family("RQ5_reversion", "RQ5 language reversion (bn vs bl only)")
share_family("RQ5_refusal", "RQ5 refusal (conjunctive machine code; see REGISTERED-DESCRIPTIVES E.5 for its precision)")
L += ["", "### RQ5 reversion by answer language (D.4 breakdown, never pooled) — [primary.RQ5_reversion_breakdown]", "", "| model | arm | n | bn | en | mixed | banglish | other |", "|---|---|---|---|---|---|---|---|"]
for k, b in PR["RQ5_reversion_breakdown"]["results"].items():
    m, a = k.split("|"); bl = b["by_answer_language"]
    L.append(f"| {m} | {a} | {b['n']} | " + " | ".join((f"{100 * bl[l]['rate']:.1f}%" if l in bl else "–") for l in ("bn", "en", "mixed", "banglish", "other")) + " |")

# ---- robustness summary
L += ["", "## Robustness of the Holm rejections — [sensitivity.RQ1_permutation, sensitivity.*_het, primary.*.log_odds.boot_ci]", ""]
perm = SE["RQ1_permutation"]["results"]
L.append("(c) randomization test on RQ1: " + ", ".join(f"{m} {c} p={pz(perm[f'{m}|{c}']['p'])}" for m in MODELS for c in ("bn-en", "bl-en", "bn-bl") if perm[f"{m}|{c}"]["p"] < 0.05 or c != "bn-bl") + ".")
for fam, het in (("RQ2_local_share", "RQ2_local_share_het"), ("RQ4_price_mention", "RQ4_price_mention_het"), ("RQ5_reversion", "RQ5_reversion_het"), ("RQ5_refusal", "RQ5_refusal_het")):
    rows = []
    for m in MODELS:
        for c, x in PR[fam]["results"][m]["contrasts"].items():
            if H[fam][f"{m}|{c}"]["reject"]:
                hp = ((SE[het]["results"].get(m) or {}).get("contrasts", {}).get(c, {}).get("log_odds") or {}).get("p")
                bci = (x.get("log_odds") or {}).get("boot_ci")
                a_ok = bci and bci[0] is not None and ((bci[0] > 0 and x["log_odds"]["estimate"] > 0) or (bci[1] < 0 and x["log_odds"]["estimate"] < 0))
                rows.append(f"{m} {c}: (b) (1|query:arm) p={pz(hp)}; (a) bootstrap CI {'supports' if a_ok else ('n/a' if not bci or bci[0] is None else 'does NOT support')}")
    L.append(f"{fam} rejections — " + ("; ".join(rows) if rows else "none") + ".")

# ---- sensitivities (bn-en / bl-en p < .05 counts)
L += ["", "## Sensitivities (unadjusted): models with bn–en / bl–en below p = .05 — [sensitivity.*, ANALYSIS-SUPPLEMENT sensitivity.*]", "", "| analysis | bn–en | bl–en | note |", "|---|---|---|---|"]
def cnt(block, key):
    r = block[key]["results"]; out = []
    for c in ("bn-en", "bl-en"):
        if all("|" in k for k in r):
            n = sum(1 for m in MODELS if (r.get(f"{m}|{c}") or {}).get("n_query") and r[f"{m}|{c}"]["test"]["p"] < 0.05)
            q = [r.get(f"{m}|{c}", {}).get("n_query") or 0 for m in MODELS]
        else:
            n = sum(1 for m in MODELS if m in r and (r[m]["contrasts"].get(c, {}).get("test") or {}).get("p") is not None and r[m]["contrasts"][c]["test"]["p"] < 0.05)
            q = [(r[m]["contrasts"].get(c) or {}).get("n_query") or 0 for m in MODELS if m in r]
        out.append(f"{n}/6 (queries {min(q)}–{max(q)})")
    return out
for key in ["RQ1_valid_only", "RQ1_no_truncated", "RQ1_no_mixed", "RQ1_no_persona", "RQ1_exclusions_retained", "RQ2_valid_only", "RQ2_no_truncated", "RQ2_no_mixed",
            "RQ2_no_persona", "RQ2_ambiguous_local", "RQ2_ambiguous_global", "RQ2_recommended_only", "RQ2_excluded_as_local", "RQ2_excluded_as_global",
            "RQ4_price_mention_valid_only", "RQ4_bdt_share_valid_only", "RQ4_price_mention_zero_removed", "RQ4_bdt_share_zero_removed", "RQ4_bdt_share_unstated_excluded",
            "RQ4_local_retailer_share_strict", "RQ5_refusal_human"]:
    if key in SE:
        a, b = cnt(SE, key); L.append(f"| {key} | {a} | {b} | {SE[key].get('label', '')[:70]} |")
for key in S["sensitivity"]:
    a, b = cnt(S["sensitivity"], key); L.append(f"| supplement: {key} | {a} | {b} | {S['sensitivity'][key].get('label', '')[:70]} |")

# ---- secondary
L += ["", "## Secondary estimators and layers: models with bn–en / bl–en below p = .05 — [secondary.*, ANALYSIS-SUPPLEMENT secondary.*]", "", "| analysis | bn–en | bl–en | label |", "|---|---|---|---|"]
for key in SC:
    if key.startswith("F10"):
        continue
    a, b = cnt(SC, key); L.append(f"| {key} | {a} | {b} | {SC[key].get('label', '')[:70]} |")
L += ["", "### F.10 (bl_translit, robust50): contrasts below p = .05 of 12 — [secondary.F10_*, supplement secondary.F10_RQ1_rbo*]", ""]
def f10(res):
    if all("|" in k for k in res):
        return sum(1 for x in res.values() if x.get("n_query") and x["test"]["p"] < 0.05), len(res)
    return sum(1 for m in res for c, x in res[m]["contrasts"].items() if (x.get("test") or {}).get("p") is not None and x["test"]["p"] < 0.05), sum(len(res[m]["contrasts"]) for m in res)
for key in ("F10_RQ1", "F10_RQ2", "F10_RQ1_machine", "F10_RQ2_machine"):
    n, t = f10(SC[key]["results"]); L.append(f"- {key}: {n} of {t} ({SC[key].get('label', '')[:60]})")
for key in ("F10_RQ1_rbo", "F10_RQ1_rbo_machine"):
    n, t = f10(S["secondary"][key]["results"]); L.append(f"- supplement {key}: {n} of {t}")

# ---- exploratory, alt-test, D.4, audit, descriptives
L += ["", "## Exploratory — [exploratory.*]", ""]
for k, v in EX.items():
    L.append(f"- {k}: {v.get('label', '')[:120]}")
pr_ = {x["rater"]: x for x in ALT["per_rater"]}
rf = ", ".join(f"{pr_[r]['rho_llm']:.3f}" for r in pr_)
rh = ", ".join(f"{pr_[r]['rho_human']:.3f}" for r in pr_)
e6 = ALT["e6_reproduced"]
L += ["", "## Alt-test (Calderon et al. 2025) — [ALT-TEST-RESULTS.json]", "",
      f"items {ALT['items']} (without primary extraction: {len(ALT['items_without_primary_extraction'])}); ε = {ALT['epsilon']}, BY q = {ALT['q_BY']}; "
      f"ρ^f = {rf} (R1, R2, R3), ρ^h = {rh}; winning rate ω = {ALT['winning_rate']}; passes: {ALT['passes']}; "
      f"advantage probability {ALT['advantage_probability']:.3f}; E.6 reproduced: brand F1 {e6['brand_f1_scored']:.4f} (scored), "
      f"{e6['brand_f1_all300_conservative']:.4f} (all 300, conservative)."]
bn, la = D4["bn_class_consensus_bn"], D4["latin_class_consensus_en_or_banglish"]
L += ["", "## D.4 cut validation — [D4-CUT-VALIDATION.json]", "",
      f"n by class {D4['n_by_class']}; bn-class judged bn by consensus {bn['k']}/{bn['n']} (Wilson {ci(bn['wilson95'])}); latin-class judged en/banglish {la['k']}/{la['n']} ({ci(la['wilson95'])}); "
      f"boundary errors {D4['boundary_errors_vs_consensus']}; mixed band n={D4['mixed_band']['n']}, corpus mixed-class {D4['corpus_mixed_band']['mixed_class']} of {D4['corpus_mixed_band']['answers_in_reversion_denominators']:,}."]
L += ["", "## H.6 audit — [N1-PLAN-AUDIT.json]", "", f"{AUD['total']} items: {AUD['computed']} computed, {AUD['held']} held, {AUD['outstanding']} outstanding, {AUD['dropped']} dropped; outstanding: " +
      "; ".join(f"{x['plan_section']} {x['item'][:50]} ({x.get('note', '')})" for x in AUD["items"] if x["status"] == "OUTSTANDING") + "."]
e5 = DESC["E5_outcome_code"]
L += ["", "## Registered descriptives — [REGISTERED-DESCRIPTIVES.json]", "",
      f"hedged-but-answered total {DESC['D5_hedged_total_final_draws']:,}; en-arm non-English answers {len(DESC['D4_en_arm_language_reversion_rows'])}; cells left short {len(DESC['D6_cells_left_short'])}; "
      f"E.5 outcome-code accuracy {e5['agree']}/{e5['scored']} = {e5['accuracy']:.4f}; machine refusal code confirmed {e5['confusion_machine_x_human'].get('refusal|refusal', 0)} of "
      f"{sum(v for k, v in e5['confusion_machine_x_human'].items() if k.startswith('refusal|'))} marked; C.6 gate on bl_translit (final draws): " +
      ", ".join(f"{m} {100 * DESC['C6_gate_bl_translit'][m]['final_draws']['rate']:.1f}%" for m in MODELS) + "."]
C1 = D / "ANALYSIS-C1-SENSITIVITY.json"
if C1.exists():
    with open(C1, encoding="utf-8") as fh:
        C = json.load(fh)
    L += ["", "## Post-hoc C.1 sensitivity: RQ2 local share with the authors' 32 decided brands classed ambiguous (unadjusted) — [ANALYSIS-C1-SENSITIVITY.json]", "",
          f"Decided brands ({len(C['meta']['decided_ambiguous'])}): {', '.join(C['meta']['decided_ambiguous'])}. Decision counts: {C['meta']['decisions_counts']}.", "",
          "| layer | variant | en | bn | bl | bn–en / bl–en below .05 | Δ pp range (bn–en, bl–en) | bn–bl below .05 |", "|---|---|---|---|---|---|---|---|"]
    for layer in ("human", "machine"):
        for var in ("excluded", "counted_local", "counted_global"):
            b = C[layer][var]["results"]
            r_ = lambda a: f"{min(b[m]['arms'][a]['share'] for m in MODELS):.3f}–{max(b[m]['arms'][a]['share'] for m in MODELS):.3f}"
            d_ = [100 * b[m]["contrasts"][c]["diff"] for m in MODELS for c in ("bn-en", "bl-en")]
            s_ = lambda c: sum(1 for m in MODELS if b[m]["contrasts"][c]["test"]["p"] < 0.05)
            L.append(f"| {layer} | {var} | {r_('en')} | {r_('bn')} | {r_('bl')} | {s_('bn-en')}/6, {s_('bl-en')}/6 | {min(d_):+.1f} to {max(d_):+.1f} | {s_('bn-bl')}/6 |")
out = D / "KEY-NUMBERS.md"
with open(out, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(L) + "\n")
print(f"wrote {out} ({len(L)} lines)")
