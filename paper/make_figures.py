#!/usr/bin/env python3
"""Figures 1-5 for the N1 manuscript, drawn from the package's result files (read-only).

Usage: python3 make_figures.py <N1-PACKAGE/06-results> <output dir>
Outputs FigN.png (300 dpi preview) and FigN.tif (300 dpi, LZW) for N = 1..5.
Colours: Okabe-Ito palette (colour-blind safe); markers also differ, so no panel relies on colour alone.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from PIL import Image

RES = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/mnt/user-data/uploads/N1-PACKAGE/06-results")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/home/claude/paper/04-FIGURES")
OUT.mkdir(parents=True, exist_ok=True)
A = json.load(open(RES / "ANALYSIS-RESULTS.json", encoding="utf-8"))

plt.rcParams.update({
    "font.family": "Liberation Sans", "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8,
    "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5, "axes.linewidth": 0.6,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6, "savefig.dpi": 300, "figure.dpi": 100,
})
OI = {"black": "#000000", "orange": "#E69F00", "skyblue": "#56B4E9", "green": "#009E73", "yellow": "#F0E442",
      "blue": "#0072B2", "vermillion": "#D55E00", "purple": "#CC79A7", "grey": "#999999"}
MODELS = ["gpt-5.6-luna", "gemini-3-flash", "claude-sonnet-5", "grok-4.6", "kimi-k3", "deepseek-v4-flash"]
CONTRASTS = [("bn-en", "bn–en", OI["blue"], "o"), ("bl-en", "bl–en", OI["vermillion"], "s"), ("bn-bl", "bn–bl", OI["grey"], "^")]
ARMS = [("en", "English (en)", OI["grey"], "o"), ("bn", "Bangla script (bn)", OI["blue"], "s"), ("bl", "Banglish (bl)", OI["orange"], "D")]


def save(fig, name):
    png = OUT / f"{name}.png"
    fig.savefig(png, dpi=300, bbox_inches="tight", facecolor="white")
    tif = OUT / f"{name}.tif"
    Image.open(png).convert("RGB").save(tif, compression="tiff_lzw", dpi=(300, 300))
    plt.close(fig)
    print("wrote", png, tif)


# ------------------------------------------------------------------ Fig 1: design and data flow
def fig1():
    fig, ax = plt.subplots(figsize=(7.5, 6.6))
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
    W, H = 30, 20.5
    X = {1: 1, 2: 35, 3: 69}
    Y = {1: 77.5, 2: 52.5, 3: 27.5, 4: 2.5}
    BLUE, SAND, GREEN, GREY = "#EAF3FA", "#FDF3E1", "#E6F4EF", "#F4F4F4"

    def box(c, r, title, body, fc):
        x, y = X[c], Y[r]
        ax.add_patch(FancyBboxPatch((x, y), W, H, boxstyle="round,pad=0.35,rounding_size=1.2", fc=fc, ec="#333333", lw=0.8))
        ax.text(x + W / 2, y + H - 1.8, title, ha="center", va="top", fontsize=7.8, fontweight="bold")
        ax.text(x + W / 2, y + H - 6.3, body, ha="center", va="top", fontsize=6.9, linespacing=1.28)

    def arrow(x1, y1, x2, y2, text=None, tx=None, ty=None):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", lw=0.8, color="#333333"))
        if text:
            ax.text(tx, ty, text, fontsize=6.5, ha="center", va="center", color="#333333")

    box(1, 1, "Queries", "250 buyer-intent queries\n10 categories x 25\nrenderings: en, bn, bl\n+ bl_translit on 50", BLUE)
    box(1, 2, "Main run", "6 subject models x 5 repetitions\n24,045 calls, 16 Sep, 09:39-15:41\nbare single-turn prompt\ntemperature 1.0", BLUE)
    box(1, 3, "Answer coding", "script class (prose ratio)\noutcome code, completed with\nthe extractor's language label\nboundary check: 191 of 200 upheld", BLUE)
    box(2, 3, "Machine extraction", "primary: Qwen3.8-Flash\n23,993 answers\ncross-check: Glimmer 30B\n2,000 answers (F1 0.9191)", BLUE)
    box(3, 1, "Pilot round (13-16 Sep)", "108 answers, 3 raters\nalpha (answer language) 0.935\nextraction gate: 0.9825\npassed (threshold 0.90)", SAND)
    box(3, 2, "Validation round (17-22 Sep)", "300 stratified answers, 3 raters\nextraction gate: 0.8221, failed\nreplacement contest:\n0.8107 and 0.7807 (below 0.85)", SAND)
    box(3, 3, "Expansion (22-26 Sep)", "registered escalation\n80 queries, 3,023 answers\n3,591 ratings, 303 triple-rated\ndrift floor cleared", SAND)
    box(1, 4, "Coded corpus", "23,994 answers, 250 queries\nprimary tests of RQ5:\nresponse language, refusal", GREEN)
    box(2, 4, "Machine-extracted layer", "23,980 answers, 250 queries\nsecondary and descriptive;\nconcordance with raters", GREEN)
    box(3, 4, "Human-labelled layer", "3,023 answers, 80 queries\nprimary tests of RQ1, RQ2,\nRQ4 prices and currency", GREEN)

    # timeline panel in the empty upper middle cell
    x, y = X[2], Y[2]
    ax.add_patch(FancyBboxPatch((x, y), W, 2 * H + 4.5, boxstyle="round,pad=0.35,rounding_size=1.2", fc=GREY, ec="#999999", lw=0.6))
    ax.text(x + W / 2, y + 2 * H + 2.7, "Timeline (2026, UTC)", ha="center", va="top", fontsize=7.8, fontweight="bold")
    lines = ["10 Sep  query file frozen; smoke test",
             "13 Sep  pilot (324 calls); r = 5",
             "16 Sep  registration frozen 08:53",
             "            OSF registration 09:21",
             "            main run 09:39-15:41",
             "17 Sep  validation sample drawn",
             "22 Sep  gate failed; expansion sized",
             "26 Sep  labels in; analysis code fixed",
             "27 Sep  registered analyses run"]
    ax.text(x + 2.2, y + 2 * H - 2.6, "\n".join(lines), ha="left", va="top", fontsize=6.7, linespacing=1.45, family="Liberation Sans")

    cx = {c: X[c] + W / 2 for c in X}
    arrow(cx[1], Y[1] - 0.6, cx[1], Y[2] + H + 0.6)
    arrow(cx[1], Y[2] - 0.6, cx[1], Y[3] + H + 0.6)
    arrow(X[1] + W + 0.6, Y[3] + H / 2, X[2] - 0.6, Y[3] + H / 2)
    arrow(cx[1], Y[3] - 0.6, cx[1], Y[4] + H + 0.6)
    arrow(cx[2], Y[3] - 0.6, cx[2], Y[4] + H + 0.6)
    arrow(X[2] + W + 0.6, Y[3] + H * 0.75, X[3] - 0.6, Y[2] + H * 0.35)
    arrow(cx[3], Y[1] - 0.6, cx[3], Y[2] + H + 0.6)
    arrow(cx[3], Y[2] - 0.6, cx[3], Y[3] + H + 0.6)
    arrow(cx[3], Y[3] - 0.6, cx[3], Y[4] + H + 0.6)
    save(fig, "Fig1")


# ------------------------------------------------------------------ Fig 2: RQ1 excess divergence
def fig2():
    human = A["primary"]["RQ1_excess_divergence"]["results"]
    machine = A["secondary"]["machine_RQ1"]["results"]
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.5), sharey=True)
    for ax, data, title in [(axes[0], human, "A  Human-labelled layer (80 queries)"),
                            (axes[1], machine, "B  Machine-extracted layer (250 queries)")]:
        for i, m in enumerate(MODELS):
            for j, (c, lab, col, mk) in enumerate(CONTRASTS):
                r = data[f"{m}|{c}"]
                y = len(MODELS) - 1 - i + (0.22 - 0.22 * j)
                ax.errorbar(r["mean_delta"], y, xerr=[[r["mean_delta"] - r["ci"][0]], [r["ci"][1] - r["mean_delta"]]],
                            fmt=mk, color=col, ms=4, lw=0.9, capsize=1.8, label=lab if i == 0 else None)
        ax.axvline(0, color="#555555", lw=0.6, ls="--")
        ax.set_title(title, loc="left", fontweight="bold")
        ax.set_xlabel("Excess divergence Δ (95% CI)")
        ax.set_xlim(-0.08, 0.36)
        ax.grid(axis="x", color="#DDDDDD", lw=0.4)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_yticks(range(len(MODELS)))
    axes[0].set_yticklabels(list(reversed(MODELS)))
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, title="Contrast", loc="lower center", ncol=3, frameon=False, title_fontsize=7.5,
               bbox_to_anchor=(0.55, -0.02))
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    save(fig, "Fig2")


# ------------------------------------------------------------------ Fig 3: RQ2 local-brand share by arm
def fig3():
    rq2 = A["primary"]["RQ2_local_share"]["results"]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    for i, m in enumerate(MODELS):
        for j, (a, lab, col, mk) in enumerate(ARMS):
            x = rq2[m]["arms"][a]
            y = len(MODELS) - 1 - i + (0.22 - 0.22 * j)
            ax.errorbar(x["share"], y, xerr=[[x["share"] - x["ci"][0]], [x["ci"][1] - x["share"]]], fmt=mk, color=col,
                        ms=4, lw=0.9, capsize=1.8, label=lab if i == 0 else None)
    ax.set_yticks(range(len(MODELS)))
    ax.set_yticklabels(list(reversed(MODELS)))
    ax.set_xlabel("Local-brand share of classified mentions (95% CI)")
    ax.set_xlim(0, 0.55)
    ax.grid(axis="x", color="#DDDDDD", lw=0.4)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(title="Query arm", frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0), title_fontsize=7.5)
    fig.tight_layout()
    save(fig, "Fig3")


# ------------------------------------------------------------------ Fig 4: answer language of Banglish-arm answers
def fig4():
    b = A["primary"]["RQ5_reversion_breakdown"]["results"]
    cats = [("bn", "Bangla script", OI["blue"], None), ("en", "English", OI["vermillion"], "////"),
            ("mixed", "Mixed", OI["yellow"], "...."), ("other", "Other", OI["purple"], "xxxx")]
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.2), sharey=True)
    for ax, arm, title in [(axes[0], "bl", "A  Natural Banglish (bl)"), (axes[1], "bl_translit", "B  Mechanical romanization (bl_translit)")]:
        for i, m in enumerate(MODELS):
            x = b[f"{m}|{arm}"]
            left = 0.0
            y = len(MODELS) - 1 - i
            for key, lab, col, hatch in cats:
                v = x["by_answer_language"].get(key)
                w = v["count"] / x["n"] if v else 0.0
                ax.barh(y, 100 * w, left=100 * left, color=col, edgecolor="#333333", lw=0.4, hatch=hatch,
                        label=lab if i == 0 else None, height=0.62)
                left += w
            ax.barh(y, 100 * (1 - left), left=100 * left, color="#FFFFFF", edgecolor="#333333", lw=0.4, height=0.62,
                    label="Banglish (arm's own form)" if i == 0 else None)
            ax.text(101, y, f"n = {x['n']:,}", va="center", fontsize=6.6)
        ax.set_xlim(0, 112)
        ax.set_xticks([0, 20, 40, 60, 80, 100])
        ax.set_xlabel("Share of answers (%)")
        ax.set_title(title, loc="left", fontweight="bold")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_yticks(range(len(MODELS)))
    axes[0].set_yticklabels(list(reversed(MODELS)))
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, frameon=False, bbox_to_anchor=(0.55, -0.04))
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save(fig, "Fig4")


# ------------------------------------------------------------------ Fig 5: human-machine concordance
def fig5():
    h1 = A["primary"]["RQ1_excess_divergence"]["results"]
    c1 = A["secondary"]["concordance_RQ1_machine_on_expansion"]["results"]
    h2 = A["primary"]["RQ2_local_share"]["results"]
    c2 = A["secondary"]["concordance_RQ2_machine_on_expansion"]["results"]
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.6))
    for c, lab, col, mk in CONTRASTS:
        for m in MODELS:
            a, b = h1[f"{m}|{c}"], c1[f"{m}|{c}"]
            axes[0].errorbar(a["mean_delta"], b["mean_delta"],
                             xerr=[[a["mean_delta"] - a["ci"][0]], [a["ci"][1] - a["mean_delta"]]],
                             yerr=[[b["mean_delta"] - b["ci"][0]], [b["ci"][1] - b["mean_delta"]]],
                             fmt=mk, color=col, ms=3.8, lw=0.6, capsize=1.2, alpha=0.9, label=lab if m == MODELS[0] else None)
            a2, b2 = h2[m]["contrasts"][c], c2[m]["contrasts"][c]
            axes[1].errorbar(100 * a2["diff"], 100 * b2["diff"],
                             xerr=[[100 * (a2["diff"] - a2["ci"][0])], [100 * (a2["ci"][1] - a2["diff"])]],
                             yerr=[[100 * (b2["diff"] - b2["ci"][0])], [100 * (b2["ci"][1] - b2["diff"])]],
                             fmt=mk, color=col, ms=3.8, lw=0.6, capsize=1.2, alpha=0.9)
    for ax, lim, title, xl, yl in [
        (axes[0], (-0.08, 0.36), "A  Excess brand-set divergence (RQ1)", "Rater labels: Δ", "Machine labels: Δ"),
        (axes[1], (-8, 32), "B  Local-brand share difference (RQ2)", "Rater labels: difference (pp)", "Machine labels: difference (pp)")]:
        ax.plot(lim, lim, color="#555555", lw=0.6, ls="--")
        ax.axhline(0, color="#BBBBBB", lw=0.4); ax.axvline(0, color="#BBBBBB", lw=0.4)
        ax.set_xlim(lim); ax.set_ylim(lim)
        ax.set_aspect("equal", adjustable="box")
        ax.set_title(title, loc="left", fontweight="bold")
        ax.set_xlabel(xl); ax.set_ylabel(yl)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(title="Contrast", frameon=False, loc="upper left", title_fontsize=7.5)
    fig.tight_layout()
    save(fig, "Fig5")


if __name__ == "__main__":
    fig1(); fig2(); fig3(); fig4(); fig5()
