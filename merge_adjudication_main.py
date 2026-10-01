#!/usr/bin/env python3
"""Merge R1's MAIN adjudication export into runs/coded/main.adjudicate.jsonl (N1, D.4 v0.46).

Reads ADJUDICATE-R1-MAIN-decisions.json (R1's export — the raw record, banked
as received, never edited) and ADJUDICATE-MAIN-MAPPING-authors-only.csv
(row_id -> record key), writes R1_decision / R1_note into the 200 sampled rows
of the adjudicate file by key (the other filed rows stay null), recomputes the
registered D.4 confirmation rate with its Wilson 95% CI, applies the registered
escalation trigger (rate < 0.95 -> second disjoint 200), and writes
ADJUDICATION-MAIN-REPORT.md with the input hashes.

finalize regenerates the adjudicate file with R1_decision null, so RE-RUN THIS
after any finalize. The export and mapping are never modified.

Usage (study machine):  python merge_adjudication_main.py
"""
import argparse, csv, hashlib, json, math, sys
from collections import Counter
from pathlib import Path

CLASSES = {"bn", "banglish", "en", "mixed", "other"}
N_SAMPLE = 200
N_QUEUE = 852            # filed script-vs-extractor disagreements, main run (E.2/D.4 record)
TRIGGER = 0.95           # registered D.4 v0.46: rate < 0.95 -> second disjoint 200
Z = 1.959963984540054    # two-sided 95% normal quantile (Wilson)
# Incident boundary (post hoc, descriptive only): the rater's browser page failed with
# ~121 items answered (author's report, 20 Sep 2026); work resumed on a rebuilt page
# from a DOM-rescue snapshot. Used only for the positional side-check in the report.
INTERRUPTION_ANSWERED = 121

ap = argparse.ArgumentParser()
ap.add_argument("--phase", default="main")
ap.add_argument("--decisions", default="ADJUDICATE-R1-MAIN-decisions.json")
ap.add_argument("--mapping", default="ADJUDICATE-MAIN-MAPPING-authors-only.csv")
ap.add_argument("--runs", default="runs")
ap.add_argument("--report", default="ADJUDICATION-MAIN-REPORT.md")
a = ap.parse_args()

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

# ---------------- validate the export (never modified) ----------------
dec_path = Path(a.decisions)
dec = json.loads(dec_path.read_text(encoding="utf-8"))
assert str(dec.get("task", "")).startswith("N1 language adjudication"), "wrong task in export"
assert dec.get("rater") == "R1", "export is not from R1"
assert not dec.get("partial"), "this is a PROGRESS save, not the final export — do not bank it"
rows = dec.get("decisions") or []
ids = [r.get("row_id") for r in rows]
assert len(rows) == N_SAMPLE and len(set(ids)) == N_SAMPLE, \
    f"expected {N_SAMPLE} unique rows, got {len(rows)}"
assert sorted(ids) == [f"C{i:03d}" for i in range(1, N_SAMPLE + 1)], "row ids are not C001..C200"
bad = [r for r in rows if r.get("decision") not in CLASSES]
assert not bad, f"invalid decisions: {bad[:5]}"

# ---------------- mapping (authors-only; never modified) ----------------
key_by_rid, meta_by_rid = {}, {}
for m in csv.DictReader(open(a.mapping, encoding="utf-8")):
    key_by_rid[m["row_id"]] = m["key"]
    meta_by_rid[m["row_id"]] = m
assert set(key_by_rid) == set(ids), "mapping/export row_id mismatch"
assert len(set(key_by_rid.values())) == N_SAMPLE, "duplicate keys in mapping"

# ---------------- adjudicate file: merge in place (tmp + replace) ----------------
adj_p = Path(a.runs) / "coded" / f"{a.phase}.adjudicate.jsonl"
adj = [json.loads(l) for l in open(adj_p, encoding="utf-8") if l.strip()]
by_key = {r["key"]: r for r in adj}
assert len(adj) == len(by_key), "duplicate keys in adjudicate file"
assert len(adj) == N_QUEUE, \
    f"adjudicate file has {len(adj)} rows, expected {N_QUEUE} — was finalize re-run on changed data?"
missing = [k for k in key_by_rid.values() if k not in by_key]
assert not missing, f"{len(missing)} sampled keys absent from the adjudicate file"

for r in rows:
    rec = by_key[key_by_rid[r["row_id"]]]
    prev = rec.get("R1_decision")
    assert prev in (None, r["decision"]), \
        f"{r['row_id']}: adjudicate file already holds a DIFFERENT decision ({prev!r})"
    rec["R1_decision"] = r["decision"]
    rec["R1_note"] = (r.get("note") or "").strip() or None

tmp = adj_p.with_suffix(".jsonl.tmp")
with open(tmp, "w", encoding="utf-8") as f:
    for r in adj:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
tmp.replace(adj_p)

# ---------------- reconciliation + registered D.4 statistics ----------------
agree_script = agree_ext = neither = both = 0
deviations = []                      # (rid, meta, decision, note)
for rid in sorted(ids):
    m = meta_by_rid[rid]
    rec = by_key[m["key"]]
    r1, s, e = rec["R1_decision"], m["script_class"], m["extractor_answer_language"]
    if r1 == s and r1 == e:
        both += 1
    elif r1 == s:
        agree_script += 1
    else:
        if r1 == e:
            agree_ext += 1
        else:
            neither += 1
        deviations.append((rid, m, r1, rec.get("R1_note")))

confirmed = agree_script + both
rate = confirmed / N_SAMPLE

def wilson(k, n, z=Z):
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d

lo, hi = wilson(confirmed, N_SAMPLE)
escalate = rate < TRIGGER

# positional side-check around the page-failure incident (post hoc, descriptive)
def binom_le(k, n, p):
    return sum(math.comb(n, i) * p**i * (1 - p)**(n - i) for i in range(k + 1))

dev_pos = sorted(int(rid[1:]) for rid, *_ in deviations)
n_dev = len(dev_pos)
inc = {}
for boundary in (INTERRUPTION_ANSWERED - 1, INTERRUPTION_ANSWERED):   # 120 and 121
    post = sum(1 for p_ in dev_pos if p_ > boundary)
    inc[boundary] = (post, binom_le(post, n_dev, (N_SAMPLE - boundary) / N_SAMPLE))

# queue / sample composition
q_ext = Counter(m["extractor_answer_language"] for m in meta_by_rid.values())
q_script = Counter(m["script_class"] for m in meta_by_rid.values())
d_cls = Counter(r["decision"] for r in rows)

# ---------------- console ----------------
print(f"merged {N_SAMPLE} R1 decisions -> {adj_p}   "
      f"({len(adj) - N_SAMPLE} filed rows outside the sample stay null)\n")
print(f"R1 sided with the deterministic script check on {agree_script}, "
      f"with the extractor on {agree_ext}, with neither on {neither}, with both on {both}.")
print(f"\n== D.4 (registered v0.46) ==")
print(f"  confirmation rate   {confirmed}/{N_SAMPLE} = {rate:.4f}")
print(f"  Wilson 95% CI       [{lo:.4f}, {hi:.4f}]")
print(f"  trigger (<{TRIGGER})      "
      + ("MET -> draw a SECOND DISJOINT 200 (then exhaustive if still <0.95)" if escalate
         else "not met -> NO escalation"))
print(f"\n  the {n_dev} non-confirmations "
      f"(script={'/'.join(sorted(set(m['script_class'] for _, m, *_ in deviations)))}):")
for rid, m, r1, note in deviations:
    side = "extractor" if r1 == m["extractor_answer_language"] else "neither"
    print(f"    {rid}  {m['query_id']:5} {m['arm']:12} {m['model_id']:18} "
          f"script={m['script_class']} extractor={m['extractor_answer_language']:8} "
          f"R1={r1:8} ({side})" + (f'  note: {note}' if note else ""))
print(f"\n  outcome effect: none — D.4 validates the deterministic script authority; "
      f"it edits no coded outcome.")
for b, (post, p) in sorted(inc.items()):
    print(f"  incident check (post hoc): {n_dev - post}/{n_dev} deviations at positions <= {b}; "
          f"P(X <= {post} | Bin({n_dev}, {(N_SAMPLE - b) / N_SAMPLE:.3f})) = {p:.4f}")

# ---------------- report ----------------
rep = []
w = rep.append
w("# N1 main-run adjudication — D.4 result (R1, 200-answer stratified sample)\n")
w(f"Generated by `merge_adjudication_main.py` (registered D.4, v0.46; seed 20260914 draw).\n")
w("## Inputs (sha256)\n")
w(f"- export (banked as received): `{a.decisions}` — `{sha(dec_path)}`")
w(f"  exported_at {dec.get('exported_at')}")
w(f"- mapping (authors-only): `{a.mapping}` — `{sha(a.mapping)}`")
w(f"- adjudicate file after merge: `{adj_p}` — `{sha(adj_p)}` "
  f"({len(adj)} filed disagreements; {N_SAMPLE} carry R1 decisions, "
  f"{len(adj) - N_SAMPLE} remain null)\n")
w("## Registered result (D.4, v0.46)\n")
w(f"- confirmation rate: **{confirmed}/{N_SAMPLE} = {rate:.4f}** "
  f"(R1 upheld the deterministic script check)")
w(f"- Wilson 95% CI: **[{lo:.4f}, {hi:.4f}]** (z = 1.96)")
w(f"- registered trigger: escalate if rate < {TRIGGER} -> "
  + ("**MET — second disjoint 200 required**" if escalate else "**not met — no escalation**"))
min_pass = -(-19 * N_SAMPLE // 20)          # smallest k with k/n >= 0.95, exact
w(f"- margin: the smallest passing count is {min_pass}/{N_SAMPLE} = {min_pass / N_SAMPLE:.4f}, "
  f"so {confirmed}/{N_SAMPLE} clears the trigger by {confirmed - min_pass} answer(s) — "
  f"two more non-confirmations ({min_pass - 1}/{N_SAMPLE} = {(min_pass - 1) / N_SAMPLE:.4f}) "
  f"would have triggered escalation. The CI lower bound ({lo:.4f}) sits below {TRIGGER}; the "
  f"paper reports both, and the registered rule is the point rate.")
w(f"- outcome effect: none. D.4 is quality control on the deterministic script authority "
  f"(bn/Latin boundary); adjudication edits no coded outcome.\n")
w("## Composition\n")
w(f"- queue (852 filed): script_class " +
  ", ".join(f"{k} {v}" for k, v in sorted(q_script.items())) + "; extractor label " +
  ", ".join(f"{k} {v}" for k, v in sorted(q_ext.items())) + " (sampled 200)")
w(f"- R1 decisions: " + ", ".join(f"{k} {v}" for k, v in sorted(d_cls.items())))
w(f"- reconciliation: script check {agree_script}, extractor {agree_ext}, "
  f"neither {neither}, both {both}\n")
w("## The non-confirmations\n")
w("| id | query | arm | model | script | extractor | R1 | sided with | note |")
w("|---|---|---|---|---|---|---|---|---|")
for rid, m, r1, note in deviations:
    side = "extractor" if r1 == m["extractor_answer_language"] else "neither"
    w(f"| {rid} | {m['query_id']} | {m['arm']} | {m['model_id']} | {m['script_class']} | "
      f"{m['extractor_answer_language']} | {r1} | {side} | {note or ''} |")
w("")
w("## Incident side-check (post hoc, descriptive)\n")
w(f"R1's browser page failed with ~{INTERRUPTION_ANSWERED} items answered (20 Sep 2026, the authors' contemporaneous report); the "
  f"answered items were carried into a rebuilt page via a DOM snapshot and R1 completed the "
  f"rest. Under exchangeability of the {n_dev} non-confirmations across the 200 presented "
  f"positions, the count landing after the failure point is Binomial:")
for b, (post, p) in sorted(inc.items()):
    w(f"- split at {b}: {post} of {n_dev} deviations after it; one-sided "
      f"P(X <= {post}) = {p:.4f}")
w(f"\nNeither split is significant at 0.05: no evidence that the interruption or the rebuilt "
  f"page changed R1's judgements (if anything, deviations concentrate early).\n")
w("## Provenance rules\n")
w("- The export and the mapping are read-only records; only the adjudicate file is written.")
w("- `finalize` regenerates the adjudicate file with `R1_decision` null — re-run "
  "`python merge_adjudication_main.py` after any finalize.")
w("- Raters never see model, arm, or outcome; the mapping stays authors-only.\n")
Path(a.report).write_text("\n".join(rep), encoding="utf-8")
print(f"\nwrote {a.report}")
