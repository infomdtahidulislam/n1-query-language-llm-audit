#!/usr/bin/env python3
"""Why is a phase slow, and would --concurrency help? Reads the records already on disk.

Safe to run WHILE a run is in progress, from a second terminal: it only reads files.

    python diagnose_throughput.py --phase extract-primary
    python diagnose_throughput.py --phase smoke

It answers one question: is the wall clock going into (a) server-side latency, in which case
more concurrency helps roughly linearly, or (b) retries and backoff after 429/5xx, in which
case the gateway is already pushing back and MORE concurrency makes it slower and lossier.
"""
import argparse, collections, json, statistics, sys
from datetime import datetime
from pathlib import Path


def parse_ts(s):
    for f in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, f)
        except (ValueError, TypeError):
            pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--phase", default="extract-primary")
    ap.add_argument("--concurrency", type=int, default=4, help="what the run was launched with")
    ap.add_argument("--timeout", type=int, default=180, help="what the run was launched with")
    a = ap.parse_args()

    recs, kinds = [], collections.Counter()
    for kind in ("responses", "errors"):
        d = Path(a.runs) / kind / a.phase
        if not d.exists():
            continue
        for p in sorted(d.rglob("*.json")):
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue          # a record still being written — skip, do not crash a live run
            r["_kind"] = kind
            recs.append(r)
            kinds[kind] += 1
    if not recs:
        sys.exit(f"no records yet under {a.runs}/*/{a.phase}")

    dur = sorted(float(r.get("duration_s") or 0) for r in recs)
    n = len(dur)
    q = lambda f: dur[min(n - 1, int(f * n))]
    print(f"\n{n} records for phase {a.phase!r}   ok={kinds['responses']}  error={kinds['errors']}")
    print(f"\nPER-CALL WALL TIME (seconds, includes that call's own retries and backoff)")
    print(f"  min {dur[0]:.1f}   p25 {q(.25):.1f}   median {q(.50):.1f}   p75 {q(.75):.1f}"
          f"   p90 {q(.90):.1f}   max {dur[-1]:.1f}   mean {statistics.fmean(dur):.1f}")

    # attempts / retry pressure
    att = collections.Counter()
    codes = collections.Counter()
    waited = 0.0
    retried = 0
    for r in recs:
        A = r.get("attempts") or []
        att[len(A)] += 1
        if len(A) > 1:
            retried += 1
        for x in A:
            codes[x.get("http_status")] += 1
            waited += float(x.get("waited_s") or 0)
    print(f"\nRETRY PRESSURE")
    for k in sorted(att):
        print(f"  {att[k]:>5} calls needed {k} attempt(s)")
    print(f"  HTTP statuses seen across all attempts: {dict(sorted(codes.items(), key=lambda kv: -kv[1]))}")
    print(f"  total time slept in backoff: {waited/60:.1f} min"
          f"   ({waited/max(1e-9, sum(dur))*100:.1f}% of all call time)")

    # observed throughput from the timestamps
    t0 = min((parse_ts(r.get("t_request")) for r in recs if parse_ts(r.get("t_request"))), default=None)
    t1 = max((parse_ts(r.get("t_response")) for r in recs if parse_ts(r.get("t_response"))), default=None)
    print(f"\nTHROUGHPUT")
    if t0 and t1 and (t1 - t0).total_seconds() > 0:
        span = (t1 - t0).total_seconds()
        rate = n / span
        busy = sum(dur) / span
        print(f"  wall span {span/60:.1f} min for {n} calls  ->  {rate:.3f} calls/s"
              f"  ({rate*60:.1f}/min)")
        print(f"  summed call time / wall span = {busy:.2f}  "
              f"(this is how many calls were genuinely in flight on average;"
              f" the run was launched with --concurrency {a.concurrency})")
        if busy < a.concurrency * 0.7:
            print(f"  ** the workers were NOT kept busy — something is serialising them"
                  f" (backoff, or one slow tail call blocking a batch)")
    else:
        print("  not enough timestamps yet")

    # ── the verdict.
    # A retry is NOT evidence of throttling by itself: status 429/503 means the gateway is refusing
    # load, while status 0/408/504 means the request timed out or the connection dropped. Those call
    # for OPPOSITE actions -- back off vs. raise the timeout -- so they are counted separately, and
    # a throttling conclusion additionally requires the backoff sleep to be a material share of the
    # wall clock. (Earlier versions of this script fired on the retry count alone and could report
    # throttling on a run whose backoff share was under 1% and which had never seen a single 429.)
    THROTTLE = {429, 503}
    TRANSPORT = {0, 408, 504, 425, 409}
    n_throttle = sum(c for s, c in codes.items() if s in THROTTLE)
    n_transport = sum(c for s, c in codes.items() if s in TRANSPORT)
    share_backoff = waited / max(1e-9, sum(dur))
    med = q(.50)
    print(f"\nVERDICT")
    print(f"  refused by the gateway (429/503): {n_throttle}      "
          f"timed out / dropped (0/408/504): {n_transport}")
    throttled = n_throttle > 0 and share_backoff > 0.10
    if throttled:
        print("  The gateway is REFUSING load: it returned 429/503 and the resulting backoff is a"
              f"\n  material share of the wall clock ({share_backoff*100:.1f}%). Raising --concurrency"
              "\n  makes this worse -- more parallel calls -> more refusals -> longer backoff -> more"
              "\n  failures. Fix the cause (quota / rate limit) or lower concurrency.")
    else:
        if n_throttle:
            print(f"  {n_throttle} refusal(s) seen, but backoff is only {share_backoff*100:.1f}% of call"
                  " time -- not the bottleneck.")
        if n_transport:
            print(f"  The {n_transport} failed attempt(s) are TIMEOUTS or dropped connections, not"
                  "\n  refusals. That is a --timeout problem, not a concurrency problem: each one burns"
                  "\n  the full timeout and then re-runs the call from scratch.")
            if q(.90) > a.timeout * 0.9:
                print(f"  ** p90 per-call time {q(.90):.0f}s is at or past --timeout {a.timeout}s, so the"
                      f"\n     slow tail is being thrown away and retried. Raise --timeout to about"
                      f"\n     {int(max(dur)*1.15//60+1)*60}s (max observed {max(dur):.0f}s) to stop paying twice"
                      " for it.")
        print("  Almost all the wall clock is server-side latency per call, not backoff. Throughput"
              "\n  is then roughly (concurrency / median latency), so raising --concurrency scales it"
              "\n  close to linearly until the gateway's rate limit is reached. Your own machine is"
              "\n  irrelevant either way: these calls are network I/O, the CPU is idle.")
        for c in (a.concurrency, a.concurrency*2, a.concurrency*4, a.concurrency*8):
            print(f"    --concurrency {c:<3} ->  ~{c/max(med,1e-9):.3f} calls/s"
                  f"   ({n} calls in ~{n*med/c/60:.0f} min)")
        print("    (a projection from the measured median, valid only while the gateway has headroom;"
              "\n     the error counter during the run is what tells you when it stops.)")
    if kinds["errors"]:
        print(f"\n  {kinds['errors']} call(s) landed in runs/errors/{a.phase}/ — these are NOT cached as"
              f"\n  successes, so re-running the same command retries only those.")


if __name__ == "__main__":
    main()
