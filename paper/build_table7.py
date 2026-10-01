#!/usr/bin/env python3
"""Table 7 (sensitivity counts) from ANALYSIS-RESULTS.json and, for the post-hoc Appendix C.1 rows, from
ANALYSIS-C1-SENSITIVITY.json (records 36 and 37); both checked row by row against KEY-NUMBERS.md. The table is
Table A in S3 File. A contrast with P < .05 that rests on a single query is counted apart and shown as "n + k", because
a single query is descriptive only; KEY-NUMBERS.md counts it with the others, so the self-check compares n + k."""
import json, re, sys
from pathlib import Path
RES = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/mnt/user-data/uploads/N1-PACKAGE/06-results")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/home/claude/paper/build/tables")
A = json.load(open(RES / "ANALYSIS-RESULTS.json", encoding="utf-8"))
C1 = json.load(open(RES / "ANALYSIS-C1-SENSITIVITY.json", encoding="utf-8"))
KN = open(RES / "KEY-NUMBERS.md", encoding="utf-8").read()
M = ["claude-sonnet-5", "deepseek-v4-flash", "gemini-3-flash", "gpt-5.6-luna", "grok-4.6", "kimi-k3"]

def count(entry):
    """per contrast: (models with P < .05 on more than one query, those on a single query, fewest and most queries)"""
    res = entry["results"]; out = {}
    for c in ["bn-en", "bl-en"]:
        n = n1 = 0; qs = []
        for m in M:
            if f"{m}|{c}" in res:
                r = res[f"{m}|{c}"]; p = r["test"]["p"] if r.get("test") else None; q = r["n_query"]
            else:
                r = res[m]["contrasts"][c]; p = r["test"]["p"]; q = r["n_query"]
            qs.append(q)
            if p is not None and p < 0.05:
                if q == 1:
                    n1 += 1
                else:
                    n += 1
        out[c] = (n, n1, min(qs), max(qs))
    return out

def total(t):
    """the count as KEY-NUMBERS.md gives it: all models with P < .05, and the query range"""
    n, n1, lo, hi = t
    return (n + n1, lo, hi)

def cell(t):
    n, n1, lo, hi = t
    k = f"{n} + {n1}" if n1 else f"{n}"
    return f"{k} ({lo})" if lo == hi else f"{k} ({lo}–{hi})"

# self-check against KEY-NUMBERS rows (the generated sheet)
kn_rows = {}
SEC = KN[KN.find("## Sensitivities (unadjusted)"):KN.find("## Secondary estimators")]
for line in SEC.split("\n"):
    m = re.match(r"\| (RQ[0-9]_[a-z_]+) \| (\d)/6 \(queries (\d+)–(\d+)\) \| (\d)/6 \(queries (\d+)–(\d+)\) \|", line)
    if m:
        k = m.group(1)
        kn_rows[k] = {"bn-en": (int(m.group(2)), int(m.group(3)), int(m.group(4))),
                      "bl-en": (int(m.group(5)), int(m.group(6)), int(m.group(7)))}
checked = 0
for k, v in kn_rows.items():
    got = count(A["sensitivity"][k])
    assert {c: total(x) for c, x in got.items()} == v, (k, got, v)
    checked += 1
print("self-check against KEY-NUMBERS:", checked, "rows identical")

# self-check of the post-hoc C.1 rows against KEY-NUMBERS ("6/6, 6/6" column of its C.1 table)
C1SEC = KN[KN.find("## Post-hoc C.1 sensitivity"):]
for line in C1SEC.split("\n"):
    m = re.match(r"\| human \| (excluded|counted_local|counted_global) \| [^|]+\| [^|]+\| [^|]+\| (\d)/6, (\d)/6 \|", line)
    if m:
        got = count(C1["human"][m.group(1)])
        assert (total(got["bn-en"])[0], total(got["bl-en"])[0]) == (int(m.group(2)), int(m.group(3))), (m.group(1), got)
        checked += 1
print("self-check including the C.1 rows:", checked, "rows identical")

ROWS = [
    ("RQ1 excess divergence", "Primary", ("primary", "RQ1_excess_divergence")),
    ("", "Valid only", ("sensitivity", "RQ1_valid_only")),
    ("", "Truncated answers removed", ("sensitivity", "RQ1_no_truncated")),
    ("", "Mixed-language answers removed", ("sensitivity", "RQ1_no_mixed")),
    ("", "Self-identifying answers removed", ("sensitivity", "RQ1_no_persona")),
    ("", "Names that are not brands retained", ("sensitivity", "RQ1_exclusions_retained")),
    ("RQ2 local-brand share", "Primary", ("primary", "RQ2_local_share")),
    ("", "Valid only", ("sensitivity", "RQ2_valid_only")),
    ("", "Truncated answers removed", ("sensitivity", "RQ2_no_truncated")),
    ("", "Mixed-language answers removed", ("sensitivity", "RQ2_no_mixed")),
    ("", "Self-identifying answers removed", ("sensitivity", "RQ2_no_persona")),
    ("", "Ambiguous brands counted local", ("sensitivity", "RQ2_ambiguous_local")),
    ("", "Ambiguous brands counted global", ("sensitivity", "RQ2_ambiguous_global")),
    ("", "Recommended brands only", ("sensitivity", "RQ2_recommended_only")),
    ("", "Removed names counted local", ("sensitivity", "RQ2_excluded_as_local")),
    ("", "Removed names counted global", ("sensitivity", "RQ2_excluded_as_global")),
    ("", "Appendix C.1 reading (post hoc), ambiguous excluded", ("c1", "excluded")),
    ("", "Appendix C.1 reading (post hoc), ambiguous counted local", ("c1", "counted_local")),
    ("", "Appendix C.1 reading (post hoc), ambiguous counted global", ("c1", "counted_global")),
    ("RQ4 price-mention rate", "Primary", ("primary", "RQ4_price_mention")),
    ("", "Valid only", ("sensitivity", "RQ4_price_mention_valid_only")),
    ("", "Prices of zero removed", ("sensitivity", "RQ4_price_mention_zero_removed")),
    ("", "Self-identifying answers removed", ("sensitivity", "RQ4_price_mention_no_persona")),
    ("RQ4 BDT share", "Primary", ("primary", "RQ4_bdt_share")),
    ("", "Valid only", ("sensitivity", "RQ4_bdt_share_valid_only")),
    ("", "Prices of zero removed", ("sensitivity", "RQ4_bdt_share_zero_removed")),
    ("", "Unstated currency left out of the denominator", ("sensitivity", "RQ4_bdt_share_unstated_excluded")),
    ("RQ4 local-retailer share (secondary)", "Retailer list only", ("sensitivity", "RQ4_local_retailer_share_strict")),
    ("RQ5 refusal", "Primary (machine code)", ("primary", "RQ5_refusal")),
    ("", "Human refusal labels", ("sensitivity", "RQ5_refusal_human")),
    ("", "Self-identifying answers removed", ("sensitivity", "RQ5_refusal_no_persona")),
]
lines = ["| Outcome | Analysis | bn–en | bl–en |", "|---|---|---|---|"]
for outcome, label, (sec, key) in ROWS:
    c = count(C1["human"][key] if sec == "c1" else A[sec][key])
    lines.append(f"| {outcome} | {label} | {cell(c['bn-en'])} | {cell(c['bl-en'])} |")
(OUT / "table7_sensitivity.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
