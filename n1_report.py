#!/usr/bin/env python3
"""n1_report.py — N1: render ANALYSIS-RESULTS.json (from n1_analysis.py) as a readable Markdown report.
Formatting only: every number is read from the JSON; nothing is recomputed.
Usage:  python n1_report.py [ANALYSIS-RESULTS.json] [ANALYSIS-RESULTS.md]"""
import json, sys
from pathlib import Path

src = Path(sys.argv[1] if len(sys.argv) > 1 else "ANALYSIS-RESULTS.json")
dst = Path(sys.argv[2] if len(sys.argv) > 2 else src.with_suffix(".md"))
R = json.load(open(src, encoding="utf-8"))
MODELS = ["claude-sonnet-5", "deepseek-v4-flash", "gemini-3-flash", "gpt-5.6-luna", "grok-4.6", "kimi-k3"]
L = []

def f(x, nd=3, pp=False):
    if x is None:
        return "–"
    return f"{100 * x:+.1f}" if pp else f"{x:.{nd}f}"

def ci(c, pp=False, nd=3):
    if not c or c[0] is None:
        return "–"
    return (f"[{100 * c[0]:+.1f}, {100 * c[1]:+.1f}]" if pp else f"[{c[0]:.{nd}f}, {c[1]:.{nd}f}]")

def pv(p):
    if p is None:
        return "–"
    return "<0.0001" if p < 1e-4 else f"{p:.4f}"

def share_table(block, holm=None, pp=True):
    L.append("| model | contrast | difference, pp [95% cluster-bootstrap CI] | log-odds [Wald 95% CI] | test | p | Holm p |")
    L.append("|---|---|---|---|---|---|---|")
    for m in MODELS:
        r = block["results"].get(m)
        if not r:
            continue
        for c, x in r["contrasts"].items():
            lo = x.get("log_odds")
            los = f"{lo['estimate']:+.2f} [{lo['ci_low']:+.2f}, {lo['ci_high']:+.2f}]" if lo else "–"
            if lo and lo.get("boot_ci"):
                los += f"; boot [{lo['boot_ci'][0]:+.2f}, {lo['boot_ci'][1]:+.2f}]"
            t = x.get("test", {})
            meth = "GLMM Wald" if t.get("method") == "glmm_wald" else f"fallback Wilcoxon ({r['glmm']['status']})"
            hp = holm.get(f"{m}|{c}", {}).get("p_holm") if holm else None
            rj = holm.get(f"{m}|{c}", {}).get("reject") if holm else None
            L.append(f"| {m} | {c} | {f(x['diff'], pp=pp)} {ci(x['ci'], pp=pp)} | {los} | {meth} | {pv(t.get('p'))} | "
                     f"{pv(hp)}{' ✔' if rj else ''} |")
    L.append("")
    L.append("| model | " + " | ".join(next(iter(block["results"].values()))["arms"].keys()) + " |")
    L.append("|---|" + "---|" * len(next(iter(block["results"].values()))["arms"]))
    for m in MODELS:
        r = block["results"].get(m)
        if not r:
            continue
        cells = []
        for a, x in r["arms"].items():
            s = f"{f(x['share'])} {ci(x['ci'])} (n {x['n']:.0f})"
            if x.get("ambiguous_rate") is not None:
                s += f"; amb {100 * x['ambiguous_rate']:.1f}%, uncl {100 * x['unclassifiable_rate']:.1f}%"
            cells.append(s)
        L.append(f"| {m} | " + " | ".join(cells) + " |")
    L.append("")

def div_table(block, holm=None):
    L.append("| model | contrast | queries | mean Δ [95% cluster-bootstrap CI] | median Δ | Wilcoxon p | Holm p |")
    L.append("|---|---|---|---|---|---|---|")
    for k, x in block["results"].items():
        m, c = k.split("|")
        if not x.get("n_query"):
            L.append(f"| {m} | {c} | 0 | – | – | – | – |")
            continue
        hp = holm.get(k, {}).get("p_holm") if holm else None
        rj = holm.get(k, {}).get("reject") if holm else None
        L.append(f"| {m} | {c} | {x['n_query']} | {x['mean_delta']:+.4f} {ci(x['ci'], nd=4)} | {x['median_delta']:+.4f} | "
                 f"{pv(x['test']['p'])} | {pv(hp)}{' ✔' if rj else ''} |")
    L.append("")

meta = R["meta"]
L.append("# N1 — registered analyses: results")
L.append("")
if meta.get("synthetic"):
    L.append("> **SYNTHETIC VALIDATION RUN — these numbers are not study results.**")
    L.append("")
L.append(f"Script sha256 `{meta['script_sha256']}`; GLMM worker `{meta['glmm_script_sha256']}`; "
         f"bootstrap {meta['bootstrap']['resamples']} query resamples per layer (seeds {meta['bootstrap']['seeds']}); "
         f"GLMM contrasts also cluster-bootstrapped: {meta['glmm_boot']}. Software: {meta['software']}.")
L.append("")
L.append("Inputs: " + "; ".join(f"`{k}` {v[:12]}…" for k, v in meta.get("inputs", {}).items()) if meta.get("inputs") else "Inputs: synthetic")
L.append("")
L.append("✔ = rejected at α = .05 after Holm correction within the family (F.7).")
L.append("")
P, H = R["primary"], R["holm"]
L.append("## Primary families (F.7)")
L.append("")
L.append("### RQ1 — excess brand-set divergence (human labels)")
div_table(P["RQ1_excess_divergence"], H["RQ1_excess_divergence"])
L.append("### RQ2 — local-brand share (human labels)")
share_table(P["RQ2_local_share"], H["RQ2_local_share"])
L.append("### RQ4 — price-mention rate (human labels)")
share_table(P["RQ4_price_mention"], H["RQ4_price_mention"])
L.append("### RQ4 — BDT share of stated prices (human labels)")
share_table(P["RQ4_bdt_share"], H["RQ4_bdt_share"])
L.append("### RQ5 — language reversion, bn vs bl (full corpus)")
share_table(P["RQ5_reversion"], H["RQ5_reversion"])
L.append("Reversion by the answer's language (D.4: reported by class, never pooled):")
L.append("")
L.append("| model | arm | answers | reverted to … (rate [95% CI]) |")
L.append("|---|---|---|---|")
for k, x in P["RQ5_reversion_breakdown"]["results"].items():
    m, a = k.split("|")
    s = "; ".join(f"{lang} {100 * v['rate']:.1f}% {ci(v['ci'], pp=False)}" for lang, v in x["by_answer_language"].items()) or "none"
    L.append(f"| {m} | {a} | {x['n']} | {s} |")
L.append("")
L.append("### RQ5 — refusal (full corpus)")
share_table(P["RQ5_refusal"], H["RQ5_refusal"])

for sec, title in (("secondary", "Secondary analyses (not adjusted)"), ("sensitivity", "Sensitivity analyses (not adjusted)"),
                   ("exploratory", "Exploratory analyses (not adjusted)")):
    L.append(f"## {title}")
    L.append("")
    for k, blk in R[sec].items():
        L.append(f"### {k} — {blk.get('label', '')}")
        res = blk.get("results", {})
        if not res:
            L.append("(no results)")
            L.append("")
            continue
        first = next(iter(res.values()))
        if k.startswith("F9"):
            L.append("| measure | arm | group | value [95% CI] | queries |")
            L.append("|---|---|---|---|---|")
            for kk, x in res.items():
                meas, arm, grp = kk.split("|")
                v = x.get("value")
                L.append(f"| {meas} | {arm} | {grp} | {'–' if v is None else f'{v:.3f}'} {ci(x.get('ci'))} | {x.get('n_query')} |")
            L.append("")
        elif any(isinstance(x, dict) and "null_mean" in x for x in res.values()):
            L.append("| model | contrast | queries | mean Δ | randomization p |")
            L.append("|---|---|---|---|---|")
            for kk, x in res.items():
                m, c = kk.split("|")
                if not x.get("n_query"):
                    L.append(f"| {m} | {c} | 0 | – | – |")
                else:
                    L.append(f"| {m} | {c} | {x['n_query']} | {x['mean_delta']:+.4f} | {pv(x['p'])} |")
            L.append("")
        elif isinstance(first, dict) and "mean_delta" in first or (isinstance(first, dict) and "n_query" in first and "contrasts" not in first):
            div_table(blk)
        elif isinstance(first, dict) and "contrasts" in first and "arms" in first and "glmm" in first:
            share_table(blk)
        elif k.endswith("length") or "length" in k:
            L.append("| model | contrast | Δ mean log tokens [95% CI] | LMM estimate (ratio) | p | converged |")
            L.append("|---|---|---|---|---|---|")
            for m, x in res.items():
                for c, y in x.get("contrasts", {}).items():
                    lm = y["lmm"]
                    L.append(f"| {m} | {c} | {y['diff_mean_log']:+.3f} {ci(y['ci'])} | {lm['estimate']:+.3f} ({lm['ratio']:.3f}) | "
                             f"{pv(lm['p'])} | {x.get('lmm_converged')} |")
            L.append("")
        else:
            L.append("```")
            L.append(json.dumps(res, indent=1)[:4000])
            L.append("```")
            L.append("")
L.append("## Run log")
L.append("")
L.append("```")
L += meta.get("log", [])
L.append("```")
dst.write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"wrote {dst}")
