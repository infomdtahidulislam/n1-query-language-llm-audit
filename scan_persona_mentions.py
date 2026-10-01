#!/usr/bin/env python3
"""scan_persona_mentions.py — how often do subject answers name an assistant identity?

Offline, no API calls. Walks runs/responses/**/*.json, takes SUBJECT answers only, and counts
answers containing a self-identification marker ("I'm Claude Code", "I am ChatGPT", "as Gemini",
a CLI-tool self-description, …), cross-tabulated by subject model and by arm.

The column that matters for study integrity is CROSS-VENDOR: an answer from model X that names
vendor Y's assistant. A handful of own-vendor mentions is ordinary model self-identification and
is reported as an observation about model behaviour; cross-vendor mentions would instead raise a
routing question, so every one of them is listed individually with its record path.

    python scan_persona_mentions.py                 # default runs/
    python scan_persona_mentions.py --phase main    # one phase only

Writes PERSONA-SCAN.json next to itself. Nothing is modified.
"""
import argparse, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--runs", default="runs")
ap.add_argument("--phase", default=None, help="limit to one phase (main, pilot, smoke)")
ap.add_argument("--examples", type=int, default=3, help="excerpts to print per vendor")
a = ap.parse_args()

# vendor -> the patterns that identify that vendor's assistant in an answer's own voice
VENDOR_PATTERNS = {
    "anthropic": [r"\bclaude\s*code\b", r"\b(i'?m|i am)\s+claude\b", r"\bas\s+claude\b",
                  r"\bআমি\s*ক্লড\b"],
    "openai":    [r"\b(i'?m|i am)\s+chat\s?gpt\b", r"\bas\s+chat\s?gpt\b",
                  r"\b(i'?m|i am)\s+(a\s+)?gpt[-\s]?\d", r"\bopenai\s+(assistant|model)\b"],
    "google":    [r"\b(i'?m|i am)\s+(google\s+)?gemini\b", r"\bas\s+gemini\b", r"\bbard\b"],
    "xai":       [r"\b(i'?m|i am)\s+grok\b", r"\bas\s+grok\b"],
    "deepseek":  [r"\b(i'?m|i am)\s+deepseek\b", r"\bas\s+deepseek\b"],
    "moonshot":  [r"\b(i'?m|i am)\s+kimi\b", r"\bas\s+kimi\b"],
}
GENERIC = [r"\b(i'?m|i am)\s+(a\s+)?(cli|command[-\s]line)\s+(tool|assistant)\b",
           r"\bcoding\s+assistant\b", r"\bsoftware\s+development\s+(tool|assistant)\b"]

# which vendor each subject model belongs to (from models.json ids used in this study)
MODEL_VENDOR = {"claude-sonnet-5": "anthropic", "gpt-5.6-luna": "openai",
                "gemini-3-flash": "google", "grok-4.6": "xai",
                "deepseek-v4-flash": "deepseek", "kimi-k3": "moonshot"}

VP = {v: [re.compile(p, re.I) for p in pats] for v, pats in VENDOR_PATTERNS.items()}
GP = [re.compile(p, re.I) for p in GENERIC]

root = Path(a.runs) / "responses"
if not root.exists():
    sys.exit(f"no such directory: {root}")

n_subject = 0
by_model = Counter()                       # model -> answers with ANY marker
by_model_total = Counter()
by_arm = Counter()
cell = Counter()            # (model, arm) -> marked
cell_total = Counter()      # (model, arm) -> answers
vendor_hits = defaultdict(list)            # vendor -> [(model, arm, path, excerpt)]
cross = []                                 # cross-vendor: the ones that matter
generic_hits = []

files = sorted(root.rglob("*.json"))
print(f"scanning {len(files)} response records...", flush=True)
for i, f in enumerate(files, 1):
    if i % 5000 == 0:
        print(f"  {i}/{len(files)}", flush=True)
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        continue
    spec = d.get("spec") or {}
    if spec.get("role", "subject") != "subject":
        continue
    if a.phase and spec.get("phase") != a.phase:
        continue
    txt = (((d.get("response") or {}).get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not txt:
        continue
    n_subject += 1
    model, arm = spec.get("model_id", "?"), spec.get("arm", "?")
    by_model_total[model] += 1
    cell_total[(model, arm)] += 1
    marked = False
    for vendor, pats in VP.items():
        for p in pats:
            m = p.search(txt)
            if not m:
                continue
            s = max(0, m.start() - 60)
            exc = " ".join(txt[s:m.end() + 90].split())
            vendor_hits[vendor].append((model, arm, str(f), exc))
            if MODEL_VENDOR.get(model) != vendor:
                cross.append((model, vendor, arm, str(f), exc,
                              (d.get("request") or {}).get("body", {}).get("model"),
                              (d.get("response") or {}).get("model"),
                              (d.get("response") or {}).get("id")))
            marked = True
            break
    for p in GP:
        m = p.search(txt)
        if m:
            s = max(0, m.start() - 60)
            generic_hits.append((model, arm, str(f), " ".join(txt[s:m.end() + 90].split())))
            marked = True
            break
    if marked:
        by_model[model] += 1
        by_arm[arm] += 1
        cell[(model, arm)] += 1

print(f"\nsubject answers scanned: {n_subject}")
print(f"answers containing a self-identification marker: {sum(by_model.values())} "
      f"({sum(by_model.values()) / n_subject * 100:.2f}%)\n" if n_subject else "\n")

print(f"{'model':20}{'answers':>9}{'with marker':>13}{'rate':>9}")
for m in sorted(by_model_total):
    n, k = by_model_total[m], by_model[m]
    print(f"{m:20}{n:>9}{k:>13}{k / n * 100:>8.2f}%")

arms = sorted({ar for _, ar in cell_total})
print(f"\n{'model':20}" + "".join(f"{ar:>16}" for ar in arms))
for m in sorted(by_model_total):
    row = ""
    for ar in arms:
        n, k = cell_total[(m, ar)], cell[(m, ar)]
        row += f"{(str(k) + '/' + str(n) + f' {k / n * 100:.1f}%') if n else '-':>16}"
    print(f"{m:20}" + row)

print(f"\nby arm: " + ", ".join(f"{k} {v}" for k, v in sorted(by_arm.items())) or "none")
print("\nby vendor named: " + (", ".join(f"{v} {len(h)}" for v, h in sorted(vendor_hits.items()))
                               or "none"))
print(f"generic coding-assistant self-descriptions: {len(generic_hits)}")

print("\n=== CROSS-VENDOR mentions (a model naming another vendor's assistant) ===")
if not cross:
    print("  NONE — every self-identification names the answering model's own vendor.")
else:
    print(f"  {len(cross)} found — listed in full; these are the ones to look at:")
    for model, vendor, arm, path, exc, req_m, ret_m, rid in cross:
        print(f"    {model} (arm {arm}) named {vendor}: {exc[:160]}")
        print(f"      requested model : {req_m}")
        print(f"      RETURNED model  : {ret_m}    (if this is the answering "
              f"model's own id, the text is self-misidentification, not routing)")
        print(f"      response id     : {rid}")
        print(f"      {path}")

for vendor, hits in sorted(vendor_hits.items()):
    if not hits:
        continue
    print(f"\n--- examples, {vendor} ({len(hits)} answers) ---")
    for model, arm, path, exc in hits[:a.examples]:
        print(f"  [{model} · {arm}] {exc[:200]}")

json.dump({"subject_answers_scanned": n_subject,
           "answers_with_marker": sum(by_model.values()),
           "by_model": dict(by_model), "by_model_total": dict(by_model_total),
           "by_arm": dict(by_arm),
           "by_vendor": {v: len(h) for v, h in vendor_hits.items()},
           "generic_self_descriptions": len(generic_hits),
           "per_model_per_arm": {f"{m}|{ar}": {"n": cell_total[(m, ar)],
                                 "marked": cell[(m, ar)]} for (m, ar) in sorted(cell_total)},
           "cross_vendor": [{"model": m, "named_vendor": v, "arm": ar, "record": p,
                             "excerpt": e, "requested_model": rq, "returned_model": rt,
                             "response_id": ri} for m, v, ar, p, e, rq, rt, ri in cross]},
          open(Path(__file__).with_name("PERSONA-SCAN.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print("\nwrote PERSONA-SCAN.json")
