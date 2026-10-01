#!/usr/bin/env python3
"""verify_no_system_prompt.py — corpus-wide check of B.3/M4 on the stored record set.

Every stored call record carries its own `request.body`, so what was actually sent is auditable
per call rather than asserted. This walks every record under runs/responses/ and runs/superseded/
and verifies, for each one:

  subject calls    body keys == {model, messages, temperature, max_tokens}
                   messages == exactly one role="user" message, no system role   (B.3 / M4)
  extractor calls  no system role either; body keys limited to the declared set

It prints per-phase counts and lists every violation. Nothing is written or modified.
Run from the study root:   python verify_no_system_prompt.py
"""
import json, sys, time
from collections import Counter
from pathlib import Path

ROOTS = [Path("runs/responses"), Path("runs/superseded")]
SUBJ_KEYS = {"model", "messages", "temperature", "max_tokens"}
EXTR_ALLOWED = SUBJ_KEYS | {"response_format", "provider", "reasoning", "top_p", "seed"}

print("scanning stored call records (this reads every response file — "
      "tens of thousands on the study machine, so allow a few minutes)...", flush=True)
files = [f for root in ROOTS if root.exists() for f in root.rglob("*.json")]
print(f"  {len(files)} files to check\n", flush=True)

seen, bad = Counter(), []
t0 = time.time()
for i, f in enumerate(files, 1):
    if i % 1000 == 0 or i == len(files):
        el = time.time() - t0
        rate = i / el if el else 0
        print(f"  {i:>7}/{len(files)}  ({el:5.1f}s elapsed, ~{rate:,.0f} files/s, "
              f"{len(bad)} violation(s) so far)", flush=True)
    if True:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            bad.append((str(f), f"unreadable: {e}")); continue
        body = (d.get("request") or {}).get("body")
        if body is None:
            continue                                   # not a call record (e.g. a log)
        role = (d.get("spec") or {}).get("role", "subject")
        phase = (d.get("spec") or {}).get("phase", "?")
        seen[(phase, role)] += 1
        msgs = body.get("messages") or []
        roles = [m.get("role") for m in msgs]
        if any(r == "system" for r in roles):
            bad.append((str(f), f"SYSTEM ROLE PRESENT: {roles}")); continue
        if roles != ["user"]:
            bad.append((str(f), f"not a single user message: {roles}")); continue
        keys = set(body)
        if role == "subject" and keys != SUBJ_KEYS:
            bad.append((str(f), f"subject body keys {sorted(keys)} != {sorted(SUBJ_KEYS)}"))
        elif role != "subject" and not keys <= EXTR_ALLOWED:
            bad.append((str(f), f"extractor body keys outside the allowed set: "
                                f"{sorted(keys - EXTR_ALLOWED)}"))

total = sum(seen.values())
print(f"\ncall records checked: {total} in {time.time() - t0:.1f}s\n")
for (phase, role), n in sorted(seen.items()):
    print(f"  {phase:22} {role:10} {n:>7}")
print()
if bad:
    print(f"VIOLATIONS: {len(bad)}")
    for f, why in bad[:40]:
        print("   ", f, "—", why)
    if len(bad) > 40:
        print(f"    … and {len(bad) - 40} more")
    sys.exit(1)
print("PASS — no system role anywhere; every subject body is exactly "
      "{model, messages, temperature, max_tokens} with one user message (B.3 / M4).")
