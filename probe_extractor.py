#!/usr/bin/env python3
"""Probe a candidate EXTRACTOR model against this study's real inputs, before adopting it.

    python probe_extractor.py --model qwen/qwen3.8-flash --reasoning-off --dry     # show bodies
    python probe_extractor.py --model qwen/qwen3.8-flash --reasoning-off --go      # live

Reads the key from GATEWAY_KEY like the runner does (never from a file, never printed), and
imports n1_pipeline so every request body, prompt and validator is IDENTICAL to production --
a probe built from a toy prompt proves nothing about the real pipeline.

Checks, each PASS/FAIL:
  1  reachable                      HTTP 200 on a minimal call
  2  model string (F13/C.7)         what the endpoint calls itself vs the id requested
  3  fingerprint / provider         is there anything to pin the served version to
  4  Bangla byte integrity (C.1)    Bangla + daṛi survives the round trip unchanged
  5  response_format honoured       json_object actually yields parseable JSON
  6  reasoning switch               `reasoning:{enabled:false}` accepted, reasoning_tokens -> 0
  7  REAL extraction                N real smoke answers through the frozen instruction + alias
                                    table, validated with the runner's own schema check, and
                                    compared field-by-field against the incumbent extractor
  8  cost                           measured tokens -> projected main-run cost
"""
import argparse, collections, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import n1_pipeline as N

BANGLA = "ঢাকায় ২৫০০০ টাকার মধ্যে ভালো ওয়াশিং মেশিন কোনটি? দাম ও দোকান জানতে চাই।"
BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def digit_runs(text: str) -> set:
    """Every maximal run of digits in the text, Bangla numerals folded to Western and separators
    removed, so '৩৮,০০০' and '38,000' both yield '38000'."""
    t = text.translate(BN_DIGITS)
    t = N.re.sub(r"(?<=\d)[,\s](?=\d\d\d)", "", t)
    return set(N.re.findall(r"\d+", t))


def price_is_traceable(amount, source: str) -> str:
    """Can this extracted amount be traced to digits actually present in the answer?
    Returns "" if yes, else a description. Word-scaled forms are allowed: '২০ হাজার' -> 20000
    legitimately has no '20000' in the source, so 20000/1000 = 20 counts as traceable, and the
    same for lakh (1e5). This test catches a MANGLED or INVENTED number, not a converted one."""
    runs = digit_runs(source)
    try:
        a = int(round(float(amount)))
    except Exception:
        return f"amount {amount!r} is not numeric"
    for cand in (a, a // 1000 if a % 1000 == 0 else None,
                 a // 100000 if a % 100000 == 0 else None):
        if cand is not None and str(cand) in runs:
            return ""
    # a near miss on a digit-dropped or digit-added variant is the signature we are hunting
    for r in runs:
        if r != str(a) and (r in str(a) or str(a) in r) and abs(len(r) - len(str(a))) == 1:
            return f"amount {a} not in the answer; nearest digit run is {r} (one digit different)"
    # sort NUMERICALLY, largest first: string-sorting put '1','12','13' first and hid the
    # large numbers, which made a genuine fabrication look like an answer with no prices in it.
    big = sorted((int(r) for r in runs), reverse=True)[:8]
    return (f"amount {a} does not appear in the answer at all"
            f" (largest numbers actually present: {big})")


PASS, FAIL, WARN = [], [], []


def mark(ok, label, detail=""):
    (PASS if ok is True else WARN if ok is None else FAIL).append(label)
    tag = "PASS" if ok is True else ("WARN" if ok is None else "FAIL")
    print(f"  [{tag}] {label}" + (f"\n         {detail}" if detail else ""))


def call(cfg, body, timeout):
    t = time.time()
    st, resp, err = N.http_chat(cfg, body, timeout)
    return st, resp, err, time.time() - t


def usage_of(resp):
    u = (resp or {}).get("usage") or {}
    return (u.get("prompt_tokens") or 0, u.get("completion_tokens") or 0,
            ((u.get("completion_tokens_details") or {}).get("reasoning_tokens")) or 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--models", default="models.json")
    ap.add_argument("--base", default=None,
                    help="override gateway_base for THIS PROBE ONLY (e.g. https://openrouter.ai/api/v1)."
                         " models.json is untouched, so nothing about the study's configuration changes"
                         " until a switch is decided and recorded (C.2/H.3).")
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--phase", default="smoke")
    ap.add_argument("--instruction", default="extractor_instruction.md")
    ap.add_argument("--aliases", default="brand_aliases.starter.csv")
    ap.add_argument("--n", type=int, default=8, help="real answers to extract (stratified by arm)")
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--concurrency", type=int, default=8,
                    help="in-flight extraction calls for check 7. NOTE: with --provider pinned there is"
                         " no fallback provider to absorb rate limits, so refusals become visible 429s"
                         " instead of being silently rerouted — which is the behaviour you want.")
    ap.add_argument("--reasoning-off", action="store_true")
    ap.add_argument("--provider", default=None, help='pin one provider, e.g. "Alibaba"')
    ap.add_argument("--incumbent", default=None,
                    help="extracted jsonl to compare against (default runs/extracted/<phase>.primary.jsonl)")
    ap.add_argument("--go", action="store_true", help="make live calls")
    ap.add_argument("--dry", action="store_true", help="print the bodies and stop")
    a = ap.parse_args()

    cfg = N.Config(Path(a.models))
    if a.base:
        cfg.base = a.base.rstrip("/")
    base_params = {"temperature": 0.0, "max_tokens": a.max_tokens}
    if a.reasoning_off:
        base_params["reasoning"] = {"enabled": False}
    if a.provider:
        base_params["provider"] = {"order": [a.provider], "allow_fallbacks": False}

    def body_for(prompt, want_json=True):
        b = {"model": a.model, "messages": [{"role": "user", "content": prompt}], **base_params}
        if want_json:
            b["response_format"] = {"type": "json_object"}
        return b

    # ── the real answers, exactly as cmd_extract picks them up
    coded = N.read_jsonl(Path(a.runs) / "coded" / f"{a.phase}.jsonl")
    cache = N.Cache(Path(a.runs))
    instruction = Path(a.instruction).read_text(encoding="utf-8")
    aliases = Path(a.aliases).read_text(encoding="utf-8")
    picked, seen = [], collections.Counter()
    per_arm = max(1, a.n // 4)
    for r in [x for x in coded if not x["degenerate"]]:
        if seen[r["arm"]] >= per_arm:
            continue
        p = cache.path({"phase": r["phase"], "model_id": r["model_id"], "query_id": r["query_id"],
                        "arm": r["arm"], "rep": r["rep"], "draw": r["draw"]}, r["key"])
        if not p.exists():
            continue
        ans = (json.loads(p.read_text(encoding="utf-8")).get("meta") or {}).get("content") or ""
        if not ans.strip():
            continue
        seen[r["arm"]] += 1
        picked.append({**r, "answer": ans,
                       "prompt": N.build_extractor_prompt(instruction, aliases, ans)})
        if len(picked) >= a.n:
            break

    print(f"\nPROBE  model={a.model}  max_tokens={a.max_tokens}"
          f"  reasoning={'OFF' if a.reasoning_off else 'default'}"
          f"  provider={a.provider or 'unpinned'}")
    print(f"gateway {cfg.base}"
          + ("   [--base OVERRIDE — models.json unchanged]" if a.base else "   [from models.json]")
          + f"   key from GATEWAY_KEY ({'set' if os.environ.get('GATEWAY_KEY') else 'NOT SET'})")
    print(f"real answers selected: {len(picked)}  by arm {dict(seen)}")

    if a.dry or not a.go:
        print("\n--- request body for the minimal call (key not shown) ---")
        print(json.dumps(body_for('Reply with json: {"ok":true} and nothing else.'), ensure_ascii=False, indent=1))
        if picked:
            b = body_for(picked[0]["prompt"])
            b["messages"][0]["content"] = b["messages"][0]["content"][:300] + " …[truncated for display]"
            print("\n--- request body for a REAL extraction call (prompt truncated for display) ---")
            print(json.dumps(b, ensure_ascii=False, indent=1))
        print("\nDRY — nothing was called. Add --go to probe live.")
        return

    N.LIVE_ALLOWED = True          # this script exists to make live calls; the runner's gate is per-process
    print("\nCHECKS")

    # 1-3, 5 ── minimal call
    st, resp, err, dt = call(cfg, body_for('Reply with json: {"ok":true} and nothing else.'), a.timeout)
    mark(st == 200, f"1 reachable (HTTP {st}, {dt:.1f}s)", err or "")
    if st != 200:
        blob = json.dumps(resp)[:700]
        print(f"\n  the endpoint refused: {blob}")
        if "must contain the word" in blob and "json" in blob:
            print("\n  NOTE: this provider requires the literal word \"json\" in the message text before it"
                  "\n  will accept response_format=json_object. That is a PROVIDER-SPECIFIC request rule,"
                  "\n  not a property of the model: the same body is accepted by other providers of the"
                  "\n  same id. It is also direct evidence that unpinned routing changes request validity,"
                  "\n  not just numerical precision — worth recording (C.7).")
        sys.exit(1)
    got = resp.get("model")
    req_t = {x for x in N.re.split(r"[^0-9a-z.]+", a.model.lower()) if x}
    got_t = {x for x in N.re.split(r"[^0-9a-z.]+", str(got).lower()) if x}
    mark(True if got == a.model else None, f"2 model string: requested {a.model!r}, got {got!r}",
         "" if got == a.model else ("LESS SPECIFIC (drops " + ", ".join(sorted(req_t - got_t)) +
                                    ") — record as the C.7 expected value and note the limitation"
                                    if got_t < req_t else "differs — record the observed string in H.4"))
    fp = next((f"{k}={v}" for k, v in resp.items() if "fingerprint" in k.lower()), None)
    prov = next((f"{k}={v}" for k, v in resp.items() if "provider" in k.lower()), None)
    mark(True if (fp or prov) else None, f"3 version pin: fingerprint={fp or 'none'} provider={prov or 'none'}",
         "" if (fp or prov) else "nothing in the response identifies the serving provider — pin it with --provider")
    obj, perr = N.parse_extractor_json((resp["choices"][0]["message"].get("content") or ""))
    mark(perr is None, f"5 response_format json_object honoured", perr or "")

    # 4 ── Bangla byte integrity
    st4, r4, e4, _ = call(cfg, body_for(
        'Return json in exactly this shape: {"echo": "<TEXT>"} where <TEXT> is this text copied '
        'verbatim -- no translation, no transliteration, no added or removed characters:\n' + BANGLA), a.timeout)
    raw4 = ((r4.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    o4, _ = N.parse_extractor_json(raw4)
    # Do NOT demand the key name: a json_object-mode model may legitimately rename it. Accept the
    # Bangla back under any key, or anywhere in the raw text -- what is under test is whether the
    # BYTES survive, not whether the model obeys a key name.
    cands = []
    if isinstance(o4, dict):
        cands = [v for v in o4.values() if isinstance(v, str)]
    hit = next((v for v in cands if v == BANGLA), None)
    where = "a JSON string value" if hit else None
    if hit is None and BANGLA in raw4:
        hit, where = BANGLA, "the raw response text"
    same = hit == BANGLA
    near = next((v for v in cands if v != BANGLA and len(v) > 10), None)
    mark(same, "4 Bangla + daṛi round trip is byte-identical",
         f"found verbatim in {where}" if same else
         (f"came back CHANGED: {near!r}\n         expected {BANGLA!r}" if near else
          f"no Bangla came back at all; keys were {list(o4) if isinstance(o4, dict) else 'not an object'}"
          f"\n         raw: {raw4[:200]!r}"))

    # 6 ── reasoning switch
    p6, c6, r6 = usage_of(resp)
    mark(None, f"6 reasoning on a trivial call: {r6} tokens"
               + (" (--reasoning-off was sent)" if a.reasoning_off else " (default)"),
         "a trivial call is the wrong place to judge this — a few tokens can be fixed overhead."
         " The verdict is computed from the REAL extraction calls below (check 8).")

    # 7 ── real extraction, and agreement with the incumbent
    inc_p = Path(a.incumbent) if a.incumbent else Path(a.runs) / "extracted" / f"{a.phase}.primary.jsonl"
    inc = {}
    if inc_p.exists():
        for l in inc_p.read_text(encoding="utf-8").splitlines():
            if l.strip():
                r = json.loads(l)
                if r.get("extraction"):
                    inc[(r["query_id"], r["arm"], r["rep"], r["draw"], r["subject_model_id"])] = r["extraction"]
    ok_n = bad_n = 0
    agree = collections.Counter()
    agree_j, agree_f, brand_diffs = [], [], []
    tot = [0, 0, 0]
    http = collections.Counter()
    print(f"\n  7 REAL extraction over the frozen instruction + alias table"
          f"   ({len(picked)} calls, {a.concurrency} in flight)")

    def one(item):
        """Runs in a worker; returns everything needed so the report stays in input order."""
        stx, rx, ex, dtx = call(cfg, body_for(item["prompt"]), a.timeout)
        content = ((rx.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        o, pe = N.parse_extractor_json(content)
        errs = [pe] if pe else N.validate_extraction(o)
        return item, stx, ex, o, errs, usage_of(rx), dtx

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, a.concurrency)) as pool:
        results = list(pool.map(one, picked))       # map preserves input order
    span = time.time() - t0

    print(f"    {'query':<7}{'arm':<13}{'subject':<20}{'valid':<6}{'lang':<10}{'prices':<22}{'brands'}")
    untraceable = []
    for item, stx, ex, o, errs, u, dtx in results:
        http[stx] += 1
        tot = [tot[i] + u[i] for i in range(3)]
        if errs:
            bad_n += 1
        else:
            ok_n += 1
        lang = (o or {}).get("answer_language") if not errs else "-"
        br = (o or {}).get("brands") if not errs else None
        pr = (o or {}).get("prices") if not errs else None
        amts = [x.get("amount") for x in (pr or []) if isinstance(x, dict)]
        for amt in amts:
            why = price_is_traceable(amt, item["answer"])
            if why:
                untraceable.append((item["query_id"], item["arm"], item["model_id"], why))
        print(f"    {item['query_id']:<7}{item['arm']:<13}{item['model_id']:<20}"
              f"{'yes' if not errs else 'NO':<6}{str(lang):<10}"
              f"{(json.dumps(amts) if amts else '-'):<22}"
              f"{json.dumps(br, ensure_ascii=False) if br is not None else (errs or ex)}")
        k = (item["query_id"], item["arm"], item["rep"], item["draw"], item["model_id"])
        if k in inc and not errs:
            agree["n"] += 1
            agree["lang"] += int(inc[k].get("answer_language") == lang)
            A, B = set(inc[k].get("brands") or []), set(br or [])
            Af, Bf = {x.lower() for x in A}, {x.lower() for x in B}
            agree["brands_exact"] += int(A == B)
            agree["brands_exact_ci"] += int(Af == Bf)
            inter = len(Af & Bf)
            agree_j.append(inter / max(len(Af | Bf), 1))
            agree_f.append(2 * inter / max(len(Af) + len(Bf), 1))
            if A != B:
                only_a, only_b = sorted(A - B), sorted(B - A)
                case_only = Af == Bf
                brand_diffs.append((item["query_id"], item["arm"], only_a, only_b, case_only))
            agree["refused"] += int(bool(inc[k].get("refused")) == bool(o.get("refused")))
    print(f"\n    {len(picked)} calls in {span/60:.1f} min"
          f"   ({len(picked)/max(span,1e-9):.2f} calls/s at {a.concurrency} in flight)"
          f"   HTTP {dict(http)}")
    refused = sum(v for k_, v in http.items() if k_ in (429, 503))
    if refused:
        print(f"    ** {refused} call(s) were REFUSED (429/503). With the provider pinned there is no"
              f"\n       fallback to hide this — lower --concurrency rather than unpinning, because"
              f"\n       unpinned fallback is what produced the 88%-empty routes.")
    n_amts = sum(1 for _ in untraceable) 
    mark(not untraceable, f"7b every extracted price traces to digits in the answer"
                          f" ({len(untraceable)} untraceable)",
         "" if not untraceable else
         "\n         ".join(f"{q} {ar} {mo}: {w}" for q, ar, mo, w in untraceable[:8])
         + "\n         A price the answer does not contain is a MANGLED or INVENTED number. This is the"
           "\n         failure the verbatim-echo check hinted at, and it corrupts the price analysis"
           "\n         silently — no schema error catches it. Word-scaled forms (20 hajar -> 20000) are"
           "\n         already allowed, so these are not conversions.")
    mark(bad_n == 0, f"7 schema-valid extractions: {ok_n}/{len(picked)}",
         "" if bad_n == 0 else f"{bad_n} failed — inspect above before adopting this model")
    if agree["n"]:
        n = agree["n"]
        mean = lambda v: sum(v) / max(len(v), 1)
        print(f"\n  AGREEMENT with the incumbent extractor over {n} shared answers:")
        print(f"    answer_language identical    {agree['lang']}/{n}")
        print(f"    refused identical            {agree['refused']}/{n}")
        print(f"    brand set identical          {agree['brands_exact']}/{n}"
              f"      <- exact equality; harsher than the registered metric")
        print(f"    brand set identical (case-folded) {agree['brands_exact_ci']}/{n}")
        print(f"    brand-set F1 (E.5)           {mean(agree_f):.3f}")
        print(f"    brand-set Jaccard (E.5)      {mean(agree_j):.3f}")
        if brand_diffs:
            only_case = [d for d in brand_diffs if d[4]]
            print(f"\n    {len(brand_diffs)} answers differ on brands; {len(only_case)} differ ONLY by"
                  f" letter case or accents:")
            for q, ar, oa, ob, co in brand_diffs[:10]:
                tag = "  [CASE ONLY]" if co else ""
                print(f"      {q} {ar:<12} incumbent-only {oa}  new-only {ob}{tag}")
            if only_case:
                print("      ** case-only differences are an ALIAS TABLE gap (F2), not an extraction"
                      "\n         error: brands absent from the table come back as surface forms, so"
                      "\n         'CeraVe' and 'cerave' would count as two brands in the RQ2 analysis."
                      "\n         Add them to brand_aliases.csv or case-fold before aggregating.")
        print("\n    (agreement is not accuracy — neither has human labels yet. E.5 registers F1 and"
              "\n     Jaccard, so read those two lines, not exact equality.)")
    else:
        print("\n  no overlap with an incumbent extraction file — agreement not computed.")

    # 8 ── cost
    n_calls = len(picked)
    if n_calls:
        print(f"\n  8 COST from {n_calls} real extraction calls")
        pa, ca, ra = tot[0]/n_calls, tot[1]/n_calls, tot[2]/n_calls
        print(f"    per answer: {pa:,.0f} prompt + {ca:,.0f} completion ({ra:,.0f} reasoning) tokens")
        print(f"    add this model to prices.json, then `n1_pipeline.py ledger` prices it exactly.")
        if a.reasoning_off:
            # The question is whether reasoning is a COST FACTOR now, not whether it is exactly 0.
            share = ra / max(ca, 1)
            if ra <= 50:
                mark(True, f"6b reasoning is effectively off ({ra:,.0f} tokens/answer)",
                     "negligible against the JSON output — the reasoning-off cost projection holds"
                     + (f"\n         ON THIS ROUTE ({cfg.base}). If the study's gateway_base differs,"
                        f" the saving\n         only materialises after the route change is made and"
                        f" recorded." if a.base else ""))
            elif share < 0.25:
                mark(None, f"6b reasoning reduced but not off ({ra:,.0f} tokens/answer,"
                           f" {share*100:.0f}% of completion)",
                     "the parameter is partly honoured; price it from the measured tokens, not from zero")
            else:
                mark(False, f"6b reasoning is NOT off ({ra:,.0f} tokens/answer,"
                            f" {share*100:.0f}% of completion)",
                     "the parameter was accepted and ignored — try --provider to reach an endpoint"
                     " that honours it, and do not rely on the reasoning-off cost projection")

    print(f"\nSUMMARY  {len(PASS)} pass, {len(WARN)} warn, {len(FAIL)} fail")
    if FAIL:
        print("  FAILED: " + "; ".join(FAIL))
        sys.exit(1)
    print("  Nothing failed. Adopting this model is still a registered change (H.3) — record it,")
    print("  and remember agreement here is a screen, not the E.3/E.4 validation.")


if __name__ == "__main__":
    main()
