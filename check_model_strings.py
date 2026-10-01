#!/usr/bin/env python3
"""F13 / C.7 audit: what model string did the endpoint actually return, and what did we ask for?

Reads runs/responses/**/*.json (the raw records, not the coded file) and prints, per subject,
the model id sent in the request body next to the `model` field the response body came back
with, plus any fingerprint field and a sample response id. The runner stores the response's
`model` verbatim (`extract_meta`: "model_string": resp.get("model")) — nothing is derived,
suffixed or normalised anywhere — so this table is the primary evidence for the H.4 expected
values and for whether the gateway substituted or relabelled anything.

    python check_model_strings.py                 # default runs/
    python check_model_strings.py --runs runs     # explicit
    python check_model_strings.py --phase smoke   # one phase only
"""
import argparse, collections, json, re, sys
from pathlib import Path


def toks(s):
    """Split a model id into comparable parts: 'deepseek-v4-flash' -> {deepseek, v4, flash}."""
    return {x for x in re.split(r"[^0-9a-z.]+", (s or "").lower()) if x}


def relation(req, ret):
    """How the endpoint's label relates to the id we asked for. The LESS-SPECIFIC case is the one
    that matters: it means the C.7 drift check cannot see a swap inside that model family."""
    a, b = toks(req), toks(ret)
    if not a or not b:
        return "one side is empty"
    if b < a:
        return ("LESS SPECIFIC than the requested id (drops " + ", ".join(sorted(a - b))
                + ") -- a swap within this family would return the SAME string, so the C.7 drift"
                  " check is blind to it; state this as a limitation")
    if b > a:
        return "MORE SPECIFIC than the requested id (adds " + ", ".join(sorted(b - a)) + ")"
    if a & b:
        return ("overlaps the requested id but differs (requested-only " + ", ".join(sorted(a - b))
                + "; returned-only " + ", ".join(sorted(b - a)) + ")")
    return "shares nothing with the requested id -- check the gateway is not substituting a model"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--phase", default=None, help="limit to one phase (smoke, pilot, main, translit)")
    a = ap.parse_args()

    root = Path(a.runs) / "responses"
    if not root.exists():
        sys.exit(f"{root} does not exist — run from the folder that holds runs/")

    # (model_id, requested, returned, fingerprint) -> [count, sample response_id, sample file]
    seen = collections.defaultdict(lambda: [0, None, None])
    phases = collections.Counter()
    n = bad = 0
    for pth in sorted(root.rglob("*.json")):
        try:
            rec = json.loads(pth.read_text(encoding="utf-8"))
        except Exception as e:
            bad += 1
            print(f"  ! unreadable {pth}: {e}")
            continue
        spec, meta = rec.get("spec") or {}, rec.get("meta") or {}
        ph = spec.get("phase") or rec.get("phase")
        if a.phase and ph != a.phase:
            continue
        n += 1
        phases[ph] += 1
        req = ((rec.get("request") or {}).get("body") or {}).get("model")
        k = (spec.get("model_id"), req, meta.get("model_string"), meta.get("fingerprint"))
        e = seen[k]
        e[0] += 1
        if e[1] is None:
            e[1], e[2] = meta.get("response_id"), str(pth)

    if not n:
        sys.exit("no records matched" + (f" phase={a.phase}" if a.phase else ""))

    print(f"\n{n} response records read from {root}"
          + (f"  (phase {a.phase})" if a.phase else f"  phases: {dict(phases)}"))
    if bad:
        print(f"{bad} unreadable file(s) — investigate before trusting this table")

    print("\n" + "-" * 104)
    print(f"{'models.json id':<20}{'REQUESTED (request body)':<26}{'RETURNED (response.model)':<28}"
          f"{'n':>5}  fingerprint")
    print("-" * 104)
    flags = []
    by_id = collections.defaultdict(set)
    for (mid, req, ret, fp), (c, rid, f) in sorted(seen.items(), key=lambda kv: (str(kv[0][0]), -kv[1][0])):
        print(f"{str(mid):<20}{str(req):<26}{str(ret):<28}{c:>5}  {fp or '—'}")
        by_id[mid].add(ret)
        if ret is None:
            flags.append(f"{mid}: response carried no `model` field at all")
        elif req != ret:
            flags.append(f"{mid}: asked {req!r}, got {ret!r} — {relation(req, ret)}")
        print(f"{'':<20}sample response id {rid}   {f}")
    print("-" * 104)

    for mid, rets in sorted(by_id.items()):
        if len(rets) > 1:
            flags.append(f"{mid}: MORE THAN ONE returned string inside this phase — {sorted(map(str, rets))}"
                         f"  ** this is C.7 drift, log it as a deviation (H.3) **")

    if flags:
        print("\nNOTES (none of these is an error by itself — they are what H.4/C.7 must state):")
        for s in flags:
            print(f"  - {s}")
    else:
        print("\nEvery response returned exactly the id that was requested; nothing to state beyond the ids.")

    print("\nA returned string that differs from the requested id is the ENDPOINT'S label. It is the"
          "\nexpected value for the C.7 drift check either way, because the check compares like with"
          "\nlike. But where the returned string is LESS specific than the id requested, the check"
          "\ncannot see a swap within that family — record that as a stated limitation, not a pass.")


if __name__ == "__main__":
    main()
