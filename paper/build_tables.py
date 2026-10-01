#!/usr/bin/env python3
"""Build the manuscript's result tables (Markdown) from the N1 package result files.

Read-only on the package. Every number in the tables is formatted from the JSON result files, never typed.
Usage: python3 build_tables.py <path to N1-PACKAGE/06-results> <output dir>
"""
import json
import sys
from pathlib import Path

RES = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/mnt/user-data/uploads/N1-PACKAGE/06-results")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/home/claude/paper/build/tables")
OUT.mkdir(parents=True, exist_ok=True)

# Registered roster order (registration C.3): four Western subjects, then the two China-trained subjects.
MODELS = ["gpt-5.6-luna", "gemini-3-flash", "claude-sonnet-5", "grok-4.6", "kimi-k3", "deepseek-v4-flash"]
CONTRASTS = ["bn-en", "bl-en", "bn-bl"]
CLABEL = {"bn-en": "bn–en", "bl-en": "bl–en", "bn-bl": "bn–bl"}
MINUS = "−"

A = json.load(open(RES / "ANALYSIS-RESULTS.json", encoding="utf-8"))


def sgn(x, nd):
    """Signed number with a typographic minus."""
    s = f"{x:+.{nd}f}"
    return s.replace("-", MINUS)


def num(x, nd):
    s = f"{x:.{nd}f}"
    return s.replace("-", MINUS)


def pfmt(p):
    if p is None:
        return "–"
    if p < 0.001:
        return "<.001"
    s = f"{p:.3f}"
    return s[1:] if s.startswith("0") else s  # .308, 1.000


def ci(lo, hi, nd, signed=False):
    f = sgn if signed else num
    return f"[{f(lo, nd)}, {f(hi, nd)}]"


def holm(fam, key):
    return A["holm"][fam][key]


def reject_mark(fam, key):
    h = holm(fam, key)
    return "yes" if h.get("reject") else "no"


def write(name, text):
    (OUT / name).write_text(text, encoding="utf-8")
    print("wrote", OUT / name)


# ---------------------------------------------------------------- Table 4: RQ1 and RQ2 (human layer)
def table4():
    rq1 = A["primary"]["RQ1_excess_divergence"]["results"]
    rq2 = A["primary"]["RQ2_local_share"]["results"]
    rows = ["| Model | Contrast | RQ1 queries | RQ1 mean Δ [95% CI] | RQ1 P (Holm) | RQ2 queries | RQ2 difference, pp [95% CI] | RQ2 log-odds [Wald 95% CI] | RQ2 log-odds, bootstrap 95% CI | RQ2 P (Holm) |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for m in MODELS:
        for c in CONTRASTS:
            k = f"{m}|{c}"
            r1 = rq1[k]
            h1 = holm("RQ1_excess_divergence", k)
            r2 = rq2[m]["contrasts"][c]
            h2 = holm("RQ2_local_share", k)
            lo = r2["log_odds"]
            star1 = "*" if h1["reject"] else ""
            star2 = "*" if h2["reject"] else ""
            rows.append(
                f"| {m} | {CLABEL[c]} | {r1['n_query']} | {sgn(r1['mean_delta'], 3)} {ci(*r1['ci'], 3, True)} | "
                f"{pfmt(h1['p_holm'])}{star1} | {r2['n_query']} | {sgn(100*r2['diff'], 1)} {ci(100*r2['ci'][0], 100*r2['ci'][1], 1, True)} | "
                f"{sgn(lo['estimate'], 2)} {ci(lo['ci_low'], lo['ci_high'], 2, True)} | {ci(*lo['boot_ci'], 2, True)} | {pfmt(h2['p_holm'])}{star2} |")
    write("table4_rq1_rq2.md", "\n".join(rows) + "\n")


# ---------------------------------------------------------------- RQ2 arm shares (for Fig 3 legend / S3 check)
def rq2_arms():
    rq2 = A["primary"]["RQ2_local_share"]["results"]
    rows = ["| Model | en share [95% CI] (mentions) | bn share [95% CI] (mentions) | bl share [95% CI] (mentions) |", "|---|---|---|---|"]
    for m in MODELS:
        cells = []
        for a in ["en", "bn", "bl"]:
            x = rq2[m]["arms"][a]
            cells.append(f"{num(x['share'], 3)} {ci(*x['ci'], 3)} ({int(x['n']):,})")
        rows.append(f"| {m} | " + " | ".join(cells) + " |")
    write("rq2_arm_shares.md", "\n".join(rows) + "\n")


# ---------------------------------------------------------------- Table 5: arm-level RQ4 and RQ5 estimates
def table5():
    P = A["primary"]
    rows = ["| Model | Price mention en | bn | bl | BDT share en | bn | bl | Reversion bn | bl | Refusal en | bn | bl |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in MODELS:
        pm = P["RQ4_price_mention"]["results"][m]["arms"]
        bd = P["RQ4_bdt_share"]["results"][m]["arms"]
        rv = P["RQ5_reversion"]["results"][m]["arms"]
        rf = P["RQ5_refusal"]["results"][m]["arms"]
        cells = [num(pm[a]["share"], 3) for a in ("en", "bn", "bl")]
        cells += [f"{num(bd[a]['share'], 3)} ({int(bd[a]['n'])})" for a in ("en", "bn", "bl")]
        cells += [num(rv[a]["share"], 3) for a in ("bn", "bl")]
        cells += [num(rf[a]["share"], 3) for a in ("en", "bn", "bl")]
        rows.append(f"| {m} | " + " | ".join(cells) + " |")
    # denominators for the note
    dn = {m: {a: int(P["RQ4_price_mention"]["results"][m]["arms"][a]["n"]) for a in ("en", "bn", "bl")} for m in MODELS}
    rv_n = {m: {a: int(P["RQ5_reversion"]["results"][m]["arms"][a]["n"]) for a in ("bn", "bl")} for m in MODELS}
    rf_n = {m: {a: int(P["RQ5_refusal"]["results"][m]["arms"][a]["n"]) for a in ("en", "bn", "bl")} for m in MODELS}
    note = {"price_mention_n": dn, "reversion_n": rv_n, "refusal_n": rf_n}
    write("table5_rq4_rq5_arms.md", "\n".join(rows) + "\n")
    write("table5_denominators.json", json.dumps(note, indent=1))


# ---------------------------------------------------------------- rejected contrasts of RQ4/RQ5 (text)
def rejections():
    out = []
    for fam in ["RQ4_price_mention", "RQ4_bdt_share", "RQ5_reversion", "RQ5_refusal"]:
        res = A["primary"][fam]["results"]
        for m in MODELS:
            for c, r in res[m]["contrasts"].items():
                k = f"{m}|{c}"
                h = A["holm"][fam].get(k)
                if h and h["reject"]:
                    lo = r.get("log_odds")
                    los = f"; log-odds {sgn(lo['estimate'], 2)} {ci(lo['ci_low'], lo['ci_high'], 2, True)}, bootstrap {ci(*lo['boot_ci'], 2, True)}" if lo else ""
                    out.append(f"{fam} {m} {CLABEL[c]}: {sgn(100*r['diff'], 1)} pp {ci(100*r['ci'][0], 100*r['ci'][1], 1, True)}, test {r['test']['method']}, p_Holm {pfmt(h['p_holm'])}{los}")
    write("rejections_rq4_rq5.txt", "\n".join(out) + "\n")


# ---------------------------------------------------------------- answer-language breakdown (Fig 4 data)
def breakdown():
    b = A["primary"]["RQ5_reversion_breakdown"]["results"]
    rows = ["| Model | Arm | Answers | Bangla script | English | Mixed | Other | Total reverted |", "|---|---|---|---|---|---|---|---|"]
    for m in MODELS:
        for a in ["bl", "bl_translit"]:
            x = b[f"{m}|{a}"]
            by = x["by_answer_language"]
            n = x["n"]
            def g(lang):
                v = by.get(lang)
                if v is None:
                    return "–"
                return f"{100*v['rate']:.1f}% ({v['count']})"
            tot = sum(v["count"] for v in by.values())
            rows.append(f"| {m} | {a} | {n:,} | {g('bn')} | {g('en')} | {g('mixed')} | {g('other')} | {100*tot/n:.1f}% ({tot}) |")
    write("breakdown_bl.md", "\n".join(rows) + "\n")


if __name__ == "__main__":
    # peek structure of the breakdown entries once, to format robustly
    b = A["primary"]["RQ5_reversion_breakdown"]["results"]
    print(json.dumps(b["claude-sonnet-5|bl"], indent=1)[:800])
    table4(); rq2_arms(); table5(); rejections(); breakdown()
