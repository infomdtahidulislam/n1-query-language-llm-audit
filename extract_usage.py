#!/usr/bin/env python3
"""extract_usage.py — N1: per-call usage for the F.5 length analysis, from the stored subject response
records (runs/responses/main/<model>/*.json). Writes ONLY: key, model_id, query_id, arm, rep, draw,
finish_reason, prompt_tokens, completion_tokens, reasoning_tokens, content_chars, http_status, file.
No request field (and so no endpoint address) is ever read into the output.
Usage (study root):  python extract_usage.py <model_id>    -> runs/usage_<model_id>.csv"""
import csv, json, sys
from pathlib import Path
m = sys.argv[1]
root = Path("runs/responses/main") / m
out = Path("runs") / f"usage_{m}.csv"
F = ["key", "model_id", "query_id", "arm", "rep", "draw", "finish_reason", "prompt_tokens", "completion_tokens",
     "reasoning_tokens", "content_chars", "http_status", "file"]
n = 0
with open(out, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=F, lineterminator="\n")
    w.writeheader()
    for p in sorted(root.glob("*.json")):
        d = json.load(open(p, encoding="utf-8"))
        sp, meta = d.get("spec") or {}, d.get("meta") or {}
        u = meta.get("usage") or ((d.get("response") or {}).get("usage")) or {}
        det = u.get("completion_tokens_details") or {}
        w.writerow({"key": d.get("key"), "model_id": sp.get("model_id"), "query_id": sp.get("query_id"),
                    "arm": sp.get("arm"), "rep": sp.get("rep"), "draw": sp.get("draw"),
                    "finish_reason": meta.get("finish_reason"), "prompt_tokens": u.get("prompt_tokens"),
                    "completion_tokens": u.get("completion_tokens"), "reasoning_tokens": det.get("reasoning_tokens"),
                    "content_chars": meta.get("content_chars"), "http_status": d.get("http_status"), "file": p.name})
        n += 1
print(m, n, "records ->", out)
