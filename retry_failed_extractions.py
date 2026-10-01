#!/usr/bin/env python3
"""Retire the cache records behind schema-FAILED extractions so the next `extract --go`
re-calls exactly those answers and nothing else.

    python retry_failed_extractions.py --phase smoke --role primary            # report
    python retry_failed_extractions.py --phase smoke --role primary --apply    # retire

Why this exists (prereg v0.35): a successful HTTP response is cached and never re-called (H.1),
so when the extractor returns schema-INVALID content the ordinary re-run replays the same bad
record from cache forever. The registered rule mirrors D.6's cap-and-log: a schema-invalid
extraction is re-called at most twice; an answer still failing after that is excluded from
extractor-dependent analyses and the exclusion is reported. This script implements the mechanical
half — it moves the failed extraction's cache record to runs/superseded/<phase-role>/retryN/...
(never deletes; the record stays in the cost ledger, which walks superseded/), and counts prior
retries so the cap is enforced. Subject answers are never touched.
"""
import argparse, json, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import n1_pipeline as N

MAX_RETRIES = 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--models", default="models.json")
    ap.add_argument("--phase", default="smoke")
    ap.add_argument("--role", default="primary", choices=["primary", "cross_check"])
    ap.add_argument("--instruction", default="extractor_instruction.md")
    ap.add_argument("--aliases", default="brand_aliases.starter.csv")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    runs = Path(a.runs)
    cfg = N.Config(Path(a.models))
    cache = N.Cache(runs)
    ex = cfg.extractor(a.role)
    params = cfg.extractor_params()
    instruction = Path(a.instruction).read_text(encoding="utf-8")
    aliases = Path(a.aliases).read_text(encoding="utf-8")

    jl = runs / "extracted" / f"{a.phase}.{a.role}.jsonl"
    rows = [json.loads(l) for l in jl.read_text(encoding="utf-8").splitlines() if l.strip()]
    bad = [r for r in rows if r.get("schema_errors")]
    print(f"{len(rows)} extraction rows; {len(bad)} schema-failed")
    if not bad:
        print("nothing to retry.")
        return

    sup = runs / "superseded" / f"extract-{a.role}"
    plans = []
    for r in bad:
        # rebuild the SAME spec cmd_extract builds, so the key is identical
        subj_rec = cache.path({"phase": a.phase, "model_id": r["subject_model_id"],
                               "query_id": r["query_id"], "arm": r["arm"],
                               "rep": r["rep"], "draw": r["draw"]}, r["subject_key"])
        answer = (json.loads(subj_rec.read_text(encoding="utf-8")).get("meta") or {}).get("content") or ""
        prompt = N.build_extractor_prompt(instruction, aliases, answer)
        spec = {"phase": f"extract-{a.role}", "role": "extractor", "model_id": ex["id"],
                "query_id": r["query_id"], "arm": r["arm"], "rep": r["rep"], "draw": r["draw"],
                "prompt_sha256": N.sha256_text(prompt)}
        k = N.Cache.key(spec, params)
        rec = cache.path(spec, k)
        prior = sorted(sup.glob(f"retry*/**/{rec.name}")) if sup.exists() else []
        plans.append((r, rec, len(prior)))
        state = ("NO CACHE RECORD (already retired? next extract re-calls it)" if not rec.exists()
                 else f"retire -> retry{len(prior)+1}" if len(prior) < MAX_RETRIES
                 else f"RETRY CAP REACHED ({MAX_RETRIES}) — exclude and report, do not re-call")
        print(f"  {r['query_id']} {r['arm']:<12} {r['subject_model_id']:<20} "
              f"prior retries: {len(prior)}   {state}")
        print(f"    errors: {r['schema_errors']}")

    if not a.apply:
        print("\nREPORT ONLY — re-run with --apply to retire the records, then run the usual"
              "\n  extract --go   (re-calls ONLY the retired answers; everything else is a cache hit)"
              "\n  finalize")
        return
    moved = 0
    for r, rec, prior in plans:
        if not rec.exists() or prior >= MAX_RETRIES:
            continue
        assert "extract-" in str(rec), f"refusing to touch {rec}"
        dst = sup / f"retry{prior+1}" / rec.parent.name / rec.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(rec), str(dst))
        moved += 1
        print(f"  retired {rec.name} -> {dst}")
    print(f"\n{moved} record(s) retired. Now run extract --go (only these are re-called), then finalize.")


if __name__ == "__main__":
    main()
