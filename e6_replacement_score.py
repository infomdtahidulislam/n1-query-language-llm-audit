#!/usr/bin/env python3
"""e6_replacement_score.py — E.6 registered fallback: score all three extractor roles against the
Round-2 human consensus (same metric as the gate: brand-set F1, alias-mapped + case-folded,
empty-empty = 1) and print the registered decision.

Usage (study root, after the two --keys extraction runs):
  python e6_replacement_score.py --primary runs/extracted/main.primary.jsonl \
      --cross runs/extracted/main.cross_check.e6-300.jsonl \
      --fallback runs/extracted/main.fallback.e6-300.jsonl
Each role is scored on the sampled answers it validly extracted (schema-failed / missing rows are
excluded and reported, mirroring E.1); a conservative all-answers number (missing scored 0 unless
the consensus set is also empty) is printed beside it.
"""
import argparse, json, re, csv, unicodedata
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--consensus", default="ROUND2-CONSENSUS.json")
ap.add_argument("--mapping", default="ROUND2-MAPPING-authors-only.csv")
ap.add_argument("--aliases", default="brand_aliases.csv")
ap.add_argument("--primary", default="runs/extracted/main.primary.jsonl")
ap.add_argument("--cross", default="runs/extracted/main.cross_check.e6-300.jsonl")
ap.add_argument("--fallback", default="runs/extracted/main.fallback.e6-300.jsonl")
a = ap.parse_args()

def fold(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s*\([^)]*\)\s*$", "", s.strip()).casefold().strip()

alias_map = {}
for row in csv.DictReader(open(a.aliases, newline="", encoding="utf-8")):
    alias_map[fold(row["display_name"])] = row["canonical_id"]
    for al in row["aliases"].split("|"):
        if al.strip():
            alias_map[fold(al)] = row["canonical_id"]

def cid(s):
    fs = fold(s)
    if fs in alias_map:
        return alias_map[fs]
    t = fs.split()
    for n in (3, 2, 1):
        if len(t) >= n and " ".join(t[:n]) in alias_map:
            return alias_map[" ".join(t[:n])]
    return None

def canon_set(items):
    return frozenset((cid(x) or fold(x)) for x in items if str(x).strip())

def f1(x, y):
    if not x and not y:
        return 1.0
    return 2 * len(x & y) / (len(x) + len(y)) if (x or y) else 1.0

cons = json.load(open(a.consensus, encoding="utf-8"))
PIDS = sorted(cons["items"])
CB = {pid: frozenset(cons["items"][pid]["brands"]) for pid in PIDS}
key_by_pid = {m["pid"]: m["key"] for m in csv.DictReader(open(a.mapping, encoding="utf-8"))}
pid_by_key = {v: k for k, v in key_by_pid.items()}

def load_role(path):
    out = {}
    p = Path(path)
    if not p.exists():
        return None
    for l in open(p, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        pid = pid_by_key.get(r["subject_key"])
        if pid is None:
            continue
        e = r.get("extraction") if not r.get("schema_errors") else None
        out[pid] = canon_set(e.get("brands") or []) if e is not None else None
    return out

GATE, FLOOR = 0.90, 0.85
MIN_COVERAGE = 279          # 93% of 300 — an extractor must actually read the sample to compete;
                            # exclusion of a handful of terminal failures is the E.1 convention,
                            # wholesale absence is not "performance" and cannot win by exclusion.
results, seen = {}, 0
print(f"E.6 replacement contest — brand-set F1 vs the Round-2 human consensus ({len(PIDS)} items)\n")
for role, path in (("primary", a.primary), ("cross_check", a.cross), ("fallback", a.fallback)):
    R = load_role(path)
    if R is None:
        print(f"  {role:12} {path}: FILE NOT FOUND — run its --keys extraction first")
        continue
    seen += 1
    scored = [p for p in PIDS if R.get(p) is not None]
    missing = [p for p in PIDS if R.get(p) is None]
    v = sum(f1(R[p], CB[p]) for p in scored) / len(scored) if scored else 0.0
    v_all = (sum(f1(R[p], CB[p]) for p in scored)
             + sum(1.0 if not CB[p] else 0.0 for p in missing)) / len(PIDS)
    ok = len(scored) >= MIN_COVERAGE
    results[role] = {"v": v, "v_all": v_all, "n": len(scored), "eligible": ok}
    print(f"  {role:12} brand F1 {v:.4f} on {len(scored)}/{len(PIDS)} scored "
          f"(conservative all-items {v_all:.4f}; {len(missing)} missing/schema-failed)"
          + ("" if ok else f"   ** NOT ELIGIBLE: coverage below {MIN_COVERAGE}/{len(PIDS)} — it "
                           f"cannot be re-validated on labels it did not read; treat as an "
                           f"infrastructure incident to diagnose and record **"))

elig = {r: d for r, d in results.items() if d["eligible"]}
if seen == 3 and elig:
    best = max(elig, key=lambda r: elig[r]["v"])
    bv = elig[best]["v"]
    print(f"\n  best eligible: {best} at {bv:.4f} (scored on {elig[best]['n']}/{len(PIDS)}; "
          f"conservative {elig[best]['v_all']:.4f})")
    if bv >= GATE:
        print(f"  decision: {best} clears the {GATE} gate -> replaces the primary for the full "
              f"corpus and is re-validated on these labels (E.6).")
    elif bv >= FLOOR:
        print(f"  decision: no eligible extractor clears {GATE}; best is >= {FLOOR} -> {best} "
              f"replaces the primary for the full corpus, is re-validated on these labels, and "
              f"the limitation is reported prominently (E.6).")
    else:
        print(f"  decision: no eligible extractor reaches {FLOOR} -> extraction is escalated: "
              f"expanded human labelling, size set at this point; limitation reported prominently "
              f"(E.6).")
    if any(not d["eligible"] for d in results.values()):
        bad = [r for r, d in results.items() if not d["eligible"]]
        print(f"  note: {', '.join(bad)} could not be scored for lack of coverage; the outage is "
              f"recorded separately and does not enter the ranking.")
elif seen == 3:
    print("\n  no role has usable coverage — diagnose the extraction failures before any decision.")
else:
    print("\n  decision pending — score all three roles first.")
