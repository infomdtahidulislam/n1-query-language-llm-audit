#!/usr/bin/env python3
"""Audit runs/ before an extraction, and archive superseded extractor records.

    python prerun_check.py --phase smoke --role primary              # report only (default)
    python prerun_check.py --phase smoke --role primary --archive    # move superseded records aside

Reads models.json to learn which extractor is CURRENT, then classifies everything under
runs/responses/extract-<role>/ and runs/errors/extract-<role>/ as current or superseded.

Superseded records are harmless to the run itself — the cache key includes the model id, so a new
extractor can never read an old one's answers — but they are NOT harmless to the checks you run
afterwards: check_extraction.py and `ledger` walk the whole phase directory and would blend two
extractors, two routes and two parameter sets into one table.

Nothing is ever deleted. Records are MOVED to runs/archive/<timestamp>/... because they were paid
for, they are the evidence behind a registered instrument change (H.3), and the cost ledger should
still be able to find them. Subject answers are never touched, and the script refuses to run if a
path it is about to move lies under responses/<phase>/ rather than responses/extract-*/.
"""
import argparse, json, shutil, sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--models", default="models.json")
    ap.add_argument("--phase", default="smoke")
    ap.add_argument("--role", default="primary", choices=["primary", "cross_check"])
    ap.add_argument("--archive", action="store_true", help="move superseded records (default: report)")
    a = ap.parse_args()

    runs = Path(a.runs)
    m = json.loads(Path(a.models).read_text(encoding="utf-8"))
    cur_id = (m.get("extractors", {}).get(a.role) or {}).get("id")
    if not cur_id:
        sys.exit(f"models.json has no extractors.{a.role}.id")
    slug = "".join(c if (c.isalnum() or c in "-._") else "_" for c in cur_id)

    print(f"\ncurrent {a.role} extractor: {cur_id}   (records live in .../{slug}/)")
    print(f"subjects route : {m.get('gateway_base')}")
    print(f"extractor route: {m.get('extractor_gateway_base') or m.get('gateway_base')}")

    # ── what is there
    moves, keep = [], []
    for kind in ("responses", "errors"):
        d = runs / kind / f"extract-{a.role}"
        if not d.exists():
            continue
        for sub in sorted(x for x in d.iterdir() if x.is_dir()):
            n = len(list(sub.rglob("*.json")))
            (keep if sub.name == slug else moves).append((kind, sub, n))

    print(f"\n{'':2}{'dir':<52}{'files':>7}  status")
    for kind, sub, n in keep:
        print(f"  {str(sub):<52}{n:>7}  CURRENT — will be reused (cache hit), not re-billed")
    for kind, sub, n in moves:
        print(f"  {str(sub):<52}{n:>7}  SUPERSEDED — different extractor")
    if not keep and not moves:
        print("  (no extraction records yet)")

    # ── the subject answers, for reassurance; never touched
    sd = runs / "responses" / a.phase
    if sd.exists():
        tot = sum(len(list(x.rglob('*.json'))) for x in sd.iterdir() if x.is_dir())
        print(f"\n  {str(sd):<52}{tot:>7}  SUBJECT ANSWERS — never touched by this script")

    # ── the extracted jsonl is overwritten by the next run
    jl = runs / "extracted" / f"{a.phase}.{a.role}.jsonl"
    if jl.exists():
        rows = sum(1 for _ in jl.open(encoding="utf-8"))
        print(f"\n  {str(jl):<52}{rows:>7}  WILL BE OVERWRITTEN by the next extract run")
        print("    ^ this is the baseline the extractor comparison was made against — it is copied"
              "\n      into the archive below so the decision stays reproducible.")

    if not moves and not jl.exists():
        print("\nNothing to archive. Safe to run.")
        return
    if not a.archive:
        print("\nREPORT ONLY — nothing moved. Re-run with --archive to move the superseded records")
        print("and snapshot the jsonl. The extraction itself is safe either way; this only keeps")
        print("check_extraction.py and `ledger` from blending two extractors.")
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    arch = runs / "archive" / stamp
    arch.mkdir(parents=True, exist_ok=True)
    moved = 0
    for kind, sub, n in moves:
        # hard guard: only ever move things under an extract-* directory
        rel = sub.relative_to(runs)
        assert rel.parts[1].startswith("extract-"), f"refusing to move {sub} — not an extractor dir"
        dst = arch / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(sub), str(dst))
        moved += n
        print(f"  moved {n:>4} files  {sub}  ->  {dst}")
    if jl.exists():
        snap = arch / "extracted" / jl.name
        snap.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(jl, snap)          # COPY: the runner overwrites it, the snapshot preserves it
        print(f"  copied         {jl}  ->  {snap}")
    (arch / "WHY.txt").write_text(
        f"Archived {stamp}\n"
        f"Current {a.role} extractor at archive time: {cur_id}\n"
        f"These records were produced by a DIFFERENT extractor and/or route. They were paid for and\n"
        f"are the evidence behind a registered instrument change (prereg H.3), so they are kept, not\n"
        f"deleted. They were moved out of runs/responses|errors/extract-{a.role}/ so that\n"
        f"check_extraction.py and `n1_pipeline.py ledger` report one extractor at a time.\n"
        f"Nothing under runs/responses/{a.phase}/ (the subject answers) was touched.\n", encoding="utf-8")
    print(f"\n{moved} record(s) archived under {arch}")
    print("Subject answers untouched. Safe to run the extraction.")


if __name__ == "__main__":
    main()
