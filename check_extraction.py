#!/usr/bin/env python3
"""Did the extraction pass actually work? Verifies an extraction phase before anything is
concluded from it, and diagnoses schema failures by cause rather than by count.

    python check_extraction.py --phase smoke --role primary

Reads runs/responses/extract-<role>/**  (the raw calls) and
      runs/extracted/<phase>.<role>.jsonl (the parsed rows the runner wrote)
and reports:
  * finish_reason histogram, and every EMPTY reply with its finish_reason and token usage --
    an empty reply from a reasoning model at a low max_tokens is the DeepSeek failure mode
    (prereg D.5 iv / C.2): hidden reasoning eats the budget and no JSON is ever emitted;
  * the schema-error breakdown split into TRANSPORT (never answered), EMPTY/TRUNCATED
    (answered with nothing usable) and SEMANTIC (a real extractor mistake), because only the
    third is evidence about the extractor's quality;
  * the answer_language and refused distributions over the rows that did parse, so a silent
    collapse (e.g. everything labelled `en`) is visible.
"""
import argparse, collections, json, re, sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--phase", default="smoke")
    ap.add_argument("--role", default="primary", choices=["primary", "cross_check"])
    a = ap.parse_args()

    # ── 1. the raw calls
    rd = Path(a.runs) / "responses" / f"extract-{a.role}"
    ed = Path(a.runs) / "errors" / f"extract-{a.role}"
    fin, empty, trunc, models, caps = collections.Counter(), [], 0, collections.Counter(), collections.Counter()
    provs, prov_empty = collections.Counter(), collections.Counter()
    n_ok = 0
    for p in sorted(rd.rglob("*.json")) if rd.exists() else []:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        n_ok += 1
        m = r.get("meta") or {}
        u = m.get("usage") or {}
        fr = m.get("finish_reason")
        fin[fr] += 1
        models[m.get("model_string")] += 1
        caps[(r.get("params") or {}).get("max_tokens")] += 1
        if fr == "length":
            trunc += 1
        resp = r.get("response") or {}
        prov = next((str(v) for k, v in resp.items() if "provider" in k.lower()), None)
        provs[prov or "(not reported)"] += 1
        if not (m.get("content") or "").strip():
            prov_empty[prov or "(not reported)"] += 1
            empty.append({
                "file": p.name, "finish_reason": fr, "provider": prov,
                "prompt": u.get("prompt_tokens"), "completion": u.get("completion_tokens"),
                "reasoning": ((u.get("completion_tokens_details") or {}).get("reasoning_tokens")),
            })
    n_err = len(list(ed.rglob("*.json"))) if ed.exists() else 0
    if not n_ok:
        sys.exit(f"no records under {rd}")

    print(f"\n{n_ok} successful extractor calls, {n_err} in errors/  (phase {a.phase}, role {a.role})")
    print(f"  model string(s): {dict(models)}")
    print(f"  max_tokens sent: {dict(caps)}")
    print(f"  finish_reason:   {dict(fin)}")
    print(f"  finish_reason=length (TRUNCATED): {trunc}")
    print(f"  serving provider: {dict(provs)}")
    if len(provs) > 1:
        print(f"    ** MORE THAN ONE PROVIDER served this phase. Providers differ in quantization and"
              f"\n       in which request parameters they honour, so this is a version-identity problem"
              f"\n       for C.7, not a detail — pin the provider and record it.")
    if prov_empty and len(provs) > 1:
        print(f"    empty replies by provider: {dict(prov_empty)}")
        worst = prov_empty.most_common(1)[0]
        rate = worst[1] / max(provs[worst[0]], 1)
        if rate > 0.5 and worst[1] >= 3:
            print(f"    ** {worst[1]} of the {provs[worst[0]]} calls served by {worst[0]!r} came back EMPTY"
                  f" ({rate*100:.0f}%).\n       The empties are concentrated on one provider — that is the"
                  f" cause, not the model or the token cap.")
    print(f"  EMPTY content:                    {len(empty)}")
    if empty:
        print("\n  empty replies -- finish_reason / prompt / completion / reasoning tokens:")
        for e in empty[:15]:
            print(f"    {e['file'][:30]:<32}{str(e['finish_reason']):<9}"
                  f"{str(e['prompt']):>7}{str(e['completion']):>8}{str(e['reasoning']):>8}"
                  f"   {e.get('provider') or '-'}")
        if len(empty) > 15:
            print(f"    ... and {len(empty)-15} more")
        by = collections.Counter(e["finish_reason"] for e in empty)
        print(f"  empties by finish_reason: {dict(by)}")
        cap = max((c for c in caps if c), default=0)
        hit = [e for e in empty if e["completion"] and cap and e["completion"] >= cap * 0.95]
        if by.get("length") or hit:
            print(f"\n  ** DIAGNOSIS: {by.get('length', 0)} empty replies finished on `length` and"
                  f" {len(hit)} spent >=95% of the {cap}-token cap.\n"
                  f"     This is the reasoning-budget failure: the extractor thinks until the budget is\n"
                  f"     gone and never emits the JSON. Raise the extractor's max_tokens and/or turn\n"
                  f"     reasoning off, then re-run -- these rows carry NO extraction at all.")
        else:
            print("\n  ** the empties did NOT finish on `length` and did not approach the cap, so the"
                  "\n     budget is not the cause -- inspect one raw response body before concluding.")

    # ── 2. the parsed rows
    jp = Path(a.runs) / "extracted" / f"{a.phase}.{a.role}.jsonl"
    if not jp.exists():
        print(f"\n{jp} not found — run `extract` first for the parsed rows.")
        return
    rows = [json.loads(l) for l in jp.read_text(encoding="utf-8").splitlines() if l.strip()]
    bad = [r for r in rows if r.get("schema_errors")]
    print(f"\n{len(rows)} extraction rows, {len(bad)} failed schema validation"
          f"  ({len(bad)/len(rows)*100:.1f}%)")

    TRANSPORT, EMPTYISH, SEMANTIC = [], [], []
    for r in bad:
        raw = r.get("extractor_raw") or ""
        (EMPTYISH if not raw.strip() else SEMANTIC).append(r)
    print(f"  no output at all (empty raw)      {len(EMPTYISH):>4}   <- a config/transport failure, NOT")
    print(f"                                            an extractor quality signal")
    print(f"  parsed but semantically invalid   {len(SEMANTIC):>4}   <- the real extractor error rate:"
          f" {len(SEMANTIC)/len(rows)*100:.2f}%")
    if SEMANTIC:
        print("\n  semantic failures (these are the ones that judge the model):")
        for r in SEMANTIC[:12]:
            print(f"    {r['query_id']} {r['arm']:<12} {r['subject_model_id']:<20} {r['schema_errors']}")
    c = collections.Counter()
    for r in bad:
        for e in r["schema_errors"]:
            c[re.sub(r"\[\d+\]", "[i]", e)[:100]] += 1
    print(f"\n  all failure messages: ")
    for k, v in c.most_common():
        print(f"    {v:>4}  {k}")
    print(f"  by arm:     {dict(collections.Counter(r['arm'] for r in bad))}")
    print(f"  by subject: {dict(collections.Counter(r['subject_model_id'] for r in bad))}")

    good = [r for r in rows if r.get("extraction")]
    if good:
        print(f"\nOVER THE {len(good)} ROWS THAT PARSED (sanity — a collapse shows up here)")
        al = collections.Counter(r["extraction"].get("answer_language") for r in good)
        print(f"  answer_language: {dict(al)}")
        print(f"  refused=true:    {sum(1 for r in good if r['extraction'].get('refused'))}")
        print(f"  rows with >=1 brand: {sum(1 for r in good if r['extraction'].get('brands'))}"
              f"   with >=1 price: {sum(1 for r in good if r['extraction'].get('prices'))}"
              f"   with >=1 retailer: {sum(1 for r in good if r['extraction'].get('retailers'))}")
        # answer_language should track the arm; a flat distribution means the field is not working
        print("\n  answer_language x arm (the extractor's own language call, per D.4):")
        t = collections.defaultdict(collections.Counter)
        for r in good:
            t[r["arm"]][r["extraction"].get("answer_language")] += 1
        for arm in sorted(t):
            print(f"    {arm:<13}{dict(t[arm])}")


if __name__ == "__main__":
    main()
