#!/usr/bin/env python3
"""persona_keys.py — N1: the main-run answer keys that carry an assistant self-identification marker,
for the persona sensitivity. Patterns are copied VERBATIM from scan_persona_mentions.py (same vendor
patterns, same generic coding-assistant patterns, same first-hit logic), so the per-model counts match
PERSONA-SCAN.json restricted to the main phase. Offline; reads runs/responses/main/<model>/*.json.
Usage (study root):  python persona_keys.py <model_id>   -> runs/persona_<model_id>.csv"""
import csv, json, re, sys
from pathlib import Path
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
VP = {v: [re.compile(p, re.I) for p in pats] for v, pats in VENDOR_PATTERNS.items()}
GP = [re.compile(p, re.I) for p in GENERIC]
m = sys.argv[1]
out = Path("runs") / f"persona_{m}.csv"
n = k = 0
with open(out, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh, lineterminator="\n")
    w.writerow(["key", "model_id", "arm", "marker"])
    for f in sorted((Path("runs/responses/main") / m).glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        spec = d.get("spec") or {}
        if spec.get("role", "subject") != "subject":
            continue
        txt = (((d.get("response") or {}).get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        if not txt:
            continue
        n += 1
        hit = None
        for vendor, pats in VP.items():
            if any(p.search(txt) for p in pats):
                hit = vendor
                break
        if hit is None and any(p.search(txt) for p in GP):
            hit = "generic"
        if hit:
            k += 1
            w.writerow([d.get("key"), spec.get("model_id"), spec.get("arm"), hit])
print(m, "answers", n, "marked", k, "->", out)
