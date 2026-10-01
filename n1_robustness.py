#!/usr/bin/env python3
"""n1_robustness.py — N1: set every primary-family decision beside the robustness checks declared in the
post-freeze record of 26 Sep 2026 ("analysis implementation fixed"), so that the paper can say, contrast by
contrast, where a check does not support a family result.

Formatting only. Every estimate, interval and p-value is read from ANALYSIS-RESULTS.json (n1_analysis.py);
the one computation added here is a Holm adjustment of each check's own p-values within its family (the same
statsmodels multipletests call the registered analysis uses), shown beside the unadjusted value.

Checks (as declared): (a) the 95% cluster-bootstrap percentile interval of the log-odds contrast itself
(run with --glmm-boot; replicates that separated or failed are dropped and counted); (b) the sensitivity fit
adding (1|query:arm); (c) for RQ1, the randomization test. Where the registered test is F.3's fallback (the
model is not identifiable), there is no log-odds contrast to bootstrap, and a check fit that also falls back
applies the same test as the primary; both are marked n/a.

Reading rules, applied mechanically:
  * a Holm rejection is SUPPORTED by a check when the check points the same way and excludes no effect:
    (a) the bootstrap interval excludes 0 on the side of the estimate; (b) Wald p < .05 with a log-odds
    estimate of the same sign; (c) randomization p < .05 with the same sign of mean Delta;
  * NOT SUPPORTED otherwise (the paper must say so);
  * for every contrast the table also shows whether the check, Holm-adjusted within the family, reaches the
    same decision as the registered test.
Usage:  python n1_robustness.py [ANALYSIS-RESULTS.json] [ANALYSIS-ROBUSTNESS.md]
"""
import json, sys
from pathlib import Path
from statsmodels.stats.multitest import multipletests

src = Path(sys.argv[1] if len(sys.argv) > 1 else "ANALYSIS-RESULTS.json")
dst = Path(sys.argv[2] if len(sys.argv) > 2 else "ANALYSIS-ROBUSTNESS.md")
with open(src, encoding="utf-8") as fh:
    R = json.load(fh)
MODELS = ["claude-sonnet-5", "deepseek-v4-flash", "gemini-3-flash", "gpt-5.6-luna", "grok-4.6", "kimi-k3"]
FAMS = [("RQ1_excess_divergence", "RQ1 — excess brand-set divergence (human)", None),
        ("RQ2_local_share", "RQ2 — local-brand share (human)", "RQ2_local_share_het"),
        ("RQ4_price_mention", "RQ4 — price-mention rate (human)", "RQ4_price_mention_het"),
        ("RQ4_bdt_share", "RQ4 — BDT share of stated prices (human)", "RQ4_bdt_share_het"),
        ("RQ5_reversion", "RQ5 — language reversion (corpus)", "RQ5_reversion_het"),
        ("RQ5_refusal", "RQ5 — refusal (corpus)", "RQ5_refusal_het")]

def pv(p):
    return "–" if p is None else ("<0.0001" if p < 1e-4 else f"{p:.4f}")

def holm_adj(ps):
    idx = [i for i, p in enumerate(ps) if p is not None]
    out = [None] * len(ps)
    if idx:
        rej, pa, _, _ = multipletests([ps[i] for i in idx], alpha=0.05, method="holm")
        for i, a, r in zip(idx, pa, rej):
            out[i] = (float(a), bool(r))
    return out

L = ["# N1 — primary decisions beside the declared robustness checks", "",
     f"Source: `{src.name}` (script sha256 `{R['meta']['script_sha256'][:12]}…`); GLMM contrasts "
     f"cluster-bootstrapped: {R['meta']['glmm_boot']}. Reading rules: see the header of n1_robustness.py. "
     "✔ = rejected after Holm within the family; 'supp.' = the check supports a Holm rejection; "
     "'NOT supp.' = it does not; 'Holm: same' = the check, Holm-adjusted within the family, reaches the "
     "registered decision.", ""]
summary = []
for fam, title, hetkey in FAMS:
    P = R["primary"][fam]["results"]
    Hd = R["holm"][fam]
    rows = []
    if fam == "RQ1_excess_divergence":
        perm = R["sensitivity"]["RQ1_permutation"]["results"]
        for k, x in P.items():
            m, c = k.split("|")
            h = Hd.get(k, {})
            pr = perm.get(k, {})
            rows.append({"m": m, "c": c, "est": x.get("mean_delta"), "ci": x.get("ci"), "p": x["test"]["p"] if x.get("n_query") else None,
                         "ph": h.get("p_holm"), "rej": h.get("reject", False),
                         "chk": {"c": {"p": pr.get("p"), "sign": pr.get("mean_delta")}}})
    else:
        het = R["sensitivity"][hetkey]["results"]
        for m in MODELS:
            r = P.get(m)
            if not r:
                continue
            for c, x in r["contrasts"].items():
                h = Hd.get(f"{m}|{c}", {})
                lo = x.get("log_odds")
                hx = het.get(m, {}).get("contrasts", {}).get(c, {})
                hlo = hx.get("log_odds")
                a = None
                if lo is not None:
                    a = {"ci": lo.get("boot_ci"), "dropped": lo.get("boot_dropped"), "sign": lo["estimate"]}
                if hlo is not None:
                    b = {"p": hlo["p"], "sign": hlo["estimate"], "method": "GLMM"}
                elif hx.get("fallback") is not None and x.get("fallback") is None:
                    b = {"p": hx["test"]["p"], "sign": x["diff"], "method": "fallback"}
                else:
                    b = None  # check fit also falls back: same test as the primary
                rows.append({"m": m, "c": c, "est": x.get("diff"), "ci": x.get("ci"), "p": x["test"]["p"],
                             "ph": h.get("p_holm"), "rej": h.get("reject", False),
                             "method": "GLMM" if x["test"]["method"] == "glmm_wald" else "fallback",
                             "lo": lo, "chk": {"a": a, "b": b}})
    # Holm-adjust each check's p-values within the family
    keys = ["c"] if fam == "RQ1_excess_divergence" else ["b"]
    for ck in keys:
        adj = holm_adj([(r["chk"][ck] or {}).get("p") if r["chk"].get(ck) else None for r in rows])
        for r, a in zip(rows, adj):
            if r["chk"].get(ck) is not None:
                r["chk"][ck]["holm"] = a
    def verdict_p(r, ck):
        v = r["chk"].get(ck)
        if v is None or v.get("p") is None:
            return "n/a"
        ok = v["p"] < 0.05 and (v["sign"] or 0) * (r["est"] or 0) > 0
        s = pv(v["p"])
        if r["rej"]:
            s += " supp." if ok else " **NOT supp.**"
        hh = v.get("holm")
        if hh is not None:
            s += "; Holm: same" if hh[1] == r["rej"] else ("; Holm: **would reject**" if hh[1] else "; Holm: **no rejection**")
        return s
    def verdict_a(r):
        v = r["chk"].get("a")
        if v is None:
            return "n/a (fallback)"
        if not v.get("ci") or v["ci"][0] is None:
            return "not run"
        lo_, hi_ = v["ci"]
        excl = (lo_ > 0 and v["sign"] > 0) or (hi_ < 0 and v["sign"] < 0)
        s = f"[{lo_:+.2f}, {hi_:+.2f}]"
        if v.get("dropped"):
            s += f" ({v['dropped']} dropped)"
        if r["rej"]:
            s += " supp." if excl else " **NOT supp.**"
        elif (lo_ > 0 or hi_ < 0):
            s += " (excludes 0)"
        return s
    L.append(f"## {title}")
    L.append("")
    if fam == "RQ1_excess_divergence":
        L.append("| model | contrast | mean Δ [95% CI] | Wilcoxon p | Holm p | (c) randomization p |")
        L.append("|---|---|---|---|---|---|")
        for r in rows:
            ci = f"[{r['ci'][0]:.4f}, {r['ci'][1]:.4f}]" if r["ci"] and r["ci"][0] is not None else "–"
            L.append(f"| {r['m']} | {r['c']} | {r['est']:+.4f} {ci} | {pv(r['p'])} | {pv(r['ph'])}{' ✔' if r['rej'] else ''} | {verdict_p(r, 'c')} |")
    else:
        L.append("| model | contrast | test | log-odds [Wald CI] | p | Holm p | (a) bootstrap CI of log-odds | (b) with (1\\|query:arm): p |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in rows:
            lo = r["lo"]
            los = f"{lo['estimate']:+.2f} [{lo['ci_low']:+.2f}, {lo['ci_high']:+.2f}]" if lo else f"pp {100 * r['est']:+.1f}"
            L.append(f"| {r['m']} | {r['c']} | {r['method']} | {los} | {pv(r['p'])} | {pv(r['ph'])}{' ✔' if r['rej'] else ''} | "
                     f"{verdict_a(r)} | {verdict_p(r, 'b')} |")
    L.append("")
    nrej = sum(r["rej"] for r in rows)
    parts = [f"{title}: {nrej} Holm rejection(s)"]
    nfb = sum(1 for r in rows if r["rej"] and r.get("method") == "fallback")
    if nfb:
        parts.append(f"{nfb} of them by F.3's fallback, where (a) and (b) do not apply")
    for ck, nm in (("a", "(a) bootstrap"), ("b", "(b) query:arm"), ("c", "(c) randomization")):
        app = [r for r in rows if r["rej"] and r["chk"].get(ck) is not None and
               (r["chk"][ck].get("p") is not None or r["chk"][ck].get("ci"))]
        if not app:
            continue
        if ck == "a":
            ok = [r for r in app if r["chk"]["a"].get("ci") and r["chk"]["a"]["ci"][0] is not None and
                  ((r["chk"]["a"]["ci"][0] > 0 and r["chk"]["a"]["sign"] > 0) or (r["chk"]["a"]["ci"][1] < 0 and r["chk"]["a"]["sign"] < 0))]
            run = [r for r in app if r["chk"]["a"].get("ci") and r["chk"]["a"]["ci"][0] is not None]
            if not run:
                parts.append(f"{nm} not run")
                continue
            app = run
        else:
            ok = [r for r in app if r["chk"][ck]["p"] < 0.05 and (r["chk"][ck]["sign"] or 0) * (r["est"] or 0) > 0]
        bad = [f"{r['m']} {r['c']}" for r in app if r not in ok]
        parts.append(f"{nm} supports {len(ok)}/{len(app)}" + (f" (not: {', '.join(bad)})" if bad else ""))
        if ck in ("b", "c"):
            diff = [f"{r['m']} {r['c']}" for r in rows if r["chk"].get(ck) and r["chk"][ck].get("holm") and r["chk"][ck]["holm"][1] != r["rej"]]
            parts.append(f"{nm} Holm-adjusted decisions differ: " + (", ".join(diff) if diff else "none"))
    summary.append("; ".join(parts))
L.append("## Summary")
L.append("")
for s in summary:
    L.append(f"- {s}")
L.append("")
dst.write_text("\n".join(L), encoding="utf-8")
print("\n".join(summary))
