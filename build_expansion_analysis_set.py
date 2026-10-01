#!/usr/bin/env python3
"""build_expansion_analysis_set.py — N1: the human-labelled analysis set for the expansion sample.

Builds ONE row per drawn expansion answer (3,023) from the banked rater exports, under the rules
recorded in the 12th post-freeze record (22 Sep 2026) and the E.3 consensus rule:
  - the 303 triple-rated answers take the E.3 consensus of R1, R2 and R3 (sets: entries listed by
    >= 2 raters; categorical fields: majority of 3, None if there is none);
  - the 38 answers that already carry a Round-2 three-way consensus keep that label, read from the
    canonical ROUND2-CONSENSUS.json;
  - every other answer takes its single rater's label.
All labels are canonicalised exactly as the registered Round-2 scorer does (round2_agreement.py):
brand / recommended / retailer names mapped through the frozen alias table (canonical ids, unknown
surfaces case-folded); prices as (amount, currency) SETS with the dated named-currency fold. The
F.6 primary analysis set (non-refused, non-degenerate) is marked from the human `refused` label;
the frame is non-degenerate by construction.

SELF-TEST (runs first, aborts on failure): the same consensus code is re-run on the three banked
Round-2 exports and must reproduce every one of the 300 items in ROUND2-CONSENSUS.json exactly.

No rater file, mapping or consensus file is modified. Outputs (written with LF line endings so the
bytes are identical on Windows and Linux):
    EXPANSION-ANALYSIS-SET.jsonl        one JSON object per answer, sorted by key
    EXPANSION-ANALYSIS-SET-REPORT.md    counts, checks and input/output hashes

Usage (study root):  python build_expansion_analysis_set.py
"""
import csv, hashlib, json, re, sys, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

W = Path(".")
GATES = {  # byte-exact sha256 of the banked / frozen inputs
    "EXPANSION-MAPPING-authors-only.csv": "e2bacda5ccc71eee60fb95a9a18350421fb87cc17c7e32f529277b158f3135c0",
    "LABEL-EXPANSION-R1-labels.json": "e81ae46f5723052708dd777893488da50b0bbae27872a58cf33c22e5bd1f74bc",
    "LABEL-EXPANSION-R2-labels.json": "699bec10cf993bb7742e7e852c778689d550a5b2839c4eaa0cb99cebf83af63b",
    "LABEL-EXPANSION-R3-labels.json": "1f2c81dd0941700442fc13e8999f1e4b37a10ba4c37de818c3d8f1e9adc772c0",
    "LABEL-ROUND2-R1-labels.json": "53f46eba77861230edf8ee524ad7a0ec243359a21f43bb3c049470d20e9890ab",
    "LABEL-ROUND2-R2-labels.json": "335dd4dd4f5253abbe253b9fc9686f189d495bd65b453a1e3fe8304c3dac3ce9",
    "LABEL-ROUND2-R3-labels.json": "fea46917cba908904a9fa003b3099389b4f0da6419bae750c99503b5d29f3630",
    "brand_aliases.csv": "0b7bd5e8355c919300129b6ba96008d5cb2d95a691aaf759a1e82823ee2b00ea",
}
# ROUND2-CONSENSUS.json is gated on CONTENT (its bytes differ only in line endings between the
# Windows canonical run and a Linux run): sha256 of json.dumps(obj, sort_keys=True, ensure_ascii=False)
R2_CONSENSUS_CONTENT_SHA = "824bd1838790f7c32fa19090ccdef7a8627cfa9adf9b6a1325779434b1d4b265"
N_DRAWN, N_OVERLAP, N_REUSED = 3023, 303, 38
RATERS = ("R1", "R2", "R3")

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

inputs = {}
for f, want in GATES.items():
    got = sha(W / f)
    if got != want:
        sys.exit(f"INPUT GATE: {f} sha256 {got} != banked {want} — refusing to build")
    inputs[f] = got
r2c = json.load(open(W / "ROUND2-CONSENSUS.json", encoding="utf-8"))
got = hashlib.sha256(json.dumps(r2c, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
if got != R2_CONSENSUS_CONTENT_SHA:
    sys.exit(f"INPUT GATE: ROUND2-CONSENSUS.json content {got} != canonical {R2_CONSENSUS_CONTENT_SHA}")
inputs["ROUND2-CONSENSUS.json (content)"] = got

# ---------- canonicalisation: identical to round2_agreement.py ----------
def fold(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s.strip())
    return s.casefold().strip()

alias_map = {}
with open(W / "brand_aliases.csv", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        cidv = row["canonical_id"]
        alias_map[fold(row["display_name"])] = cidv
        for al in row["aliases"].split("|"):
            if al.strip():
                alias_map[fold(al)] = cidv

def cid(s):
    fs = fold(s)
    if fs in alias_map:
        return alias_map[fs]
    toks = fs.split()
    for n in (3, 2, 1):
        if len(toks) >= n:
            p = " ".join(toks[:n])
            if p in alias_map:
                return alias_map[p]
    return None

def canon_set(items):
    return frozenset((cid(x) or fold(x)) for x in items if str(x).strip())

PRICE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s+(\S{1,14})$")

def fold_currency(tok):
    t = tok.strip()
    if t.upper() in ("BDT", "USD"):
        return t.upper()
    if t.lower() in ("other", "unstated"):
        return t.lower()
    if t.lower() in ("taka", "tk", "৳", "টাকা"):
        return "BDT"
    if t.lower() in ("dollar", "dollars"):
        return "USD"
    if t.isalpha():
        return "other"
    return None

def norm_amount(x):
    fx = float(x)
    return int(fx) if fx == int(fx) else fx

def price_set_rater(lines_):
    out = set()
    for x in lines_:
        m = PRICE_RE.match(str(x).strip())
        cur = fold_currency(m.group(2)) if m else None
        assert cur is not None, f"unparseable price line {x!r}"
        out.add((norm_amount(m.group(1)), cur))
    return frozenset(out)

def rl(row, f):
    v = row.get(f) or []
    return v if isinstance(v, list) else [x for x in str(v).splitlines() if x.strip()]

SETF = ("brands", "recommended", "retailers")

def human(row):
    return {"language": row["answer_language"],
            "refused": str(row["refused"]).lower() == "true",
            "brands": canon_set(rl(row, "brands")),
            "recommended": canon_set(rl(row, "recommended")),
            "retailers": canon_set(rl(row, "retailers")),
            "prices": price_set_rater(rl(row, "prices"))}

def consensus_of(three):
    """E.3 consensus exactly as round2_agreement.py serialises it."""
    lc = Counter(h["language"] for h in three).most_common()
    ent = {"answer_language": lc[0][0] if lc[0][1] >= 2 else None,
           "refused": Counter(h["refused"] for h in three).most_common(1)[0][0]}
    for f in SETF + ("prices",):
        cnt = Counter()
        for h in three:
            for el in h[f]:
                cnt[el] += 1
        ent[f] = sorted([str(e) for e, n in cnt.items() if n >= 2])
    return ent

TUP = re.compile(r"^\((\d+(?:\.\d+)?), '([^']+)'\)$")

def price_list_from_serialised(strs):
    out = []
    for s in strs:
        m = TUP.match(s)
        assert m, f"bad serialised price {s!r}"
        out.append([norm_amount(m.group(1)), m.group(2)])
    return sorted(out, key=lambda p: (p[1], p[0]))

def load_export(path, task, rater):
    d = json.load(open(W / path, encoding="utf-8"))
    assert d["task"] == task and d["rater"] == rater and not d.get("partial"), f"{path}: header"
    rows = {r["pid"]: r for r in d["labels"]}
    assert len(rows) == len(d["labels"]), f"{path}: duplicate pids"
    return rows

# ---------- SELF-TEST: reproduce the registered Round-2 consensus ----------
R2 = {c: load_export(f"LABEL-ROUND2-{c}-labels.json", "N1 labelling round 2", c) for c in RATERS}
r2_pids = [f"M{i:03d}" for i in range(1, 301)]
mismatch = [pid for pid in r2_pids
            if consensus_of([human(R2[c][pid]) for c in RATERS]) != r2c["items"][pid]]
if mismatch:
    sys.exit(f"SELF-TEST FAILED: consensus code does not reproduce ROUND2-CONSENSUS.json on {mismatch[:5]}")
print("self-test: consensus code reproduces all 300 Round-2 consensus items exactly")

# ---------- expansion ----------
mapping = list(csv.DictReader(open(W / "EXPANSION-MAPPING-authors-only.csv", encoding="utf-8")))
assert len(mapping) == N_DRAWN
E = {c: load_export(f"LABEL-EXPANSION-{c}-labels.json", "N1 labelling expansion round", c) for c in RATERS}
r2map = {m["pid"]: m["key"] for m in csv.DictReader(open(W / "ROUND2-MAPPING-authors-only.csv", encoding="utf-8"))}

rows, src_count = [], Counter()
for m in mapping:
    pid = m["pid"]
    base = {"key": m["key"], "pid": pid, "query_id": m["query_id"], "arm": m["arm"],
            "model_id": m["model_id"], "rep": int(m["rep"]), "draw": int(m["draw"]),
            "outcome": m["outcome"], "script_class": m["script_class"]}
    if m["rater"] == "reuse:consensus-round2":
        r2pid = m["reused_round2_pid"]
        assert r2map.get(r2pid) == m["key"], f"{pid}: Round-2 pid {r2pid} key mismatch"
        c = r2c["items"][r2pid]
        lab = {"brands": list(c["brands"]), "recommended": list(c["recommended"]),
               "retailers": list(c["retailers"]), "prices": price_list_from_serialised(c["prices"]),
               "refused": bool(c["refused"]), "answer_language": c["answer_language"]}
        src, who = "round2-consensus", f"round2:{r2pid}"
        for rt in RATERS:
            assert pid not in E[rt], f"{pid}: reused item unexpectedly on {rt}'s page"
    elif m["overlap"] == "True":
        three = [human(E[rt][pid]) for rt in RATERS]
        c = consensus_of(three)
        lab = {"brands": c["brands"], "recommended": c["recommended"], "retailers": c["retailers"],
               "prices": price_list_from_serialised(c["prices"]),
               "refused": bool(c["refused"]), "answer_language": c["answer_language"]}
        src, who = "consensus-3", "R1+R2+R3"
    else:
        rt = m["rater"]
        assert rt in RATERS and pid in E[rt], f"{pid}: single-rated item missing from {rt}"
        for other in RATERS:
            if other != rt:
                assert pid not in E[other], f"{pid}: single-rated item also on {other}'s page"
        h = human(E[rt][pid])
        lab = {"brands": sorted(h["brands"]), "recommended": sorted(h["recommended"]),
               "retailers": sorted(h["retailers"]),
               "prices": sorted([list(p) for p in h["prices"]], key=lambda p: (p[1], p[0])),
               "refused": h["refused"], "answer_language": h["language"]}
        src, who = "single", rt
    src_count[src] += 1
    row = dict(base)
    row.update(lab)
    row["label_source"], row["labelled_by"] = src, who
    row["in_primary_set"] = not lab["refused"]          # F.6: non-refused (frame is non-degenerate)
    row["zero_price_entries"] = sum(1 for p in lab["prices"] if p[0] == 0)
    rows.append(row)

assert src_count == {"single": N_DRAWN - N_OVERLAP - N_REUSED, "consensus-3": N_OVERLAP,
                     "round2-consensus": N_REUSED}, src_count
seen = {rt: {r["pid"] for r in rows if r["labelled_by"] in (rt, "R1+R2+R3")} for rt in RATERS}
for rt in RATERS:
    assert seen[rt] == set(E[rt]), f"{rt}: export pids not all used exactly once"
rows.sort(key=lambda r: r["key"])
assert len({r["key"] for r in rows}) == N_DRAWN

out = W / "EXPANSION-ANALYSIS-SET.jsonl"
with open(out, "w", encoding="utf-8", newline="\n") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
out_sha = sha(out)

# ---------- report ----------
arms = ("bn", "en", "bl", "bl_translit")
models = sorted({r["model_id"] for r in rows})
cell = defaultdict(list)
for r in rows:
    cell[(r["query_id"], r["model_id"], r["arm"])].append(r)
short_all = sorted(k for k, v in cell.items() if len(v) < 2)
short_primary = sorted(k for k, v in cell.items() if sum(x["in_primary_set"] for x in v) < 2)
ref_x = Counter((r["refused"], r["outcome"] == "refusal") for r in rows)
no_major = sorted(r["pid"] for r in rows if r["label_source"] == "consensus-3" and r["answer_language"] is None)
zero_rows = sum(1 for r in rows if r["zero_price_entries"])
zero_entries = sum(r["zero_price_entries"] for r in rows)

L = []
L.append("# N1 — expansion analysis set (human labels)")
L.append("")
L.append(f"Output: `EXPANSION-ANALYSIS-SET.jsonl` — {len(rows)} rows, sha256 `{out_sha}` (LF line endings).")
L.append("")
L.append("## Inputs (all gated; the build refuses to run on anything else)")
for k, v in inputs.items():
    L.append(f"- `{k}` {v}")
L.append("")
L.append("## Self-test")
L.append("- The consensus code, re-run on the three banked Round-2 exports, reproduces all 300 items of "
         "the canonical ROUND2-CONSENSUS.json exactly.")
L.append("")
L.append("## Label sources")
L.append(f"- single-rated: {src_count['single']} (R1 {sum(1 for r in rows if r['labelled_by']=='R1')}, "
         f"R2 {sum(1 for r in rows if r['labelled_by']=='R2')}, R3 {sum(1 for r in rows if r['labelled_by']=='R3')})")
L.append(f"- E.3 consensus of all three raters: {src_count['consensus-3']}")
L.append(f"- Round-2 consensus reused: {src_count['round2-consensus']}")
L.append(f"- language with no majority among the 303 (field set to null, no effect on brand/price analyses): "
         f"{len(no_major)} {', '.join(no_major)}")
L.append("")
L.append("## F.6 primary analysis set (non-refused; frame already excludes degenerate answers)")
L.append(f"- in primary set: {sum(r['in_primary_set'] for r in rows)} of {len(rows)}; "
         f"human-refused: {sum(r['refused'] for r in rows)}")
L.append("")
L.append("| model | " + " | ".join(arms) + " |")
L.append("|---|" + "---|" * len(arms))
for mdl in models:
    cells_ = []
    for a in arms:
        allv = [r for r in rows if r["model_id"] == mdl and r["arm"] == a]
        cells_.append(f"{sum(r['in_primary_set'] for r in allv)}/{len(allv)}")
    L.append(f"| {mdl} | " + " | ".join(cells_) + " |")
L.append("")
L.append(f"- query x model x arm cells with fewer than 2 answers drawn: {len(short_all)} "
         f"({'; '.join('/'.join(k) for k in short_all) or 'none'})")
L.append(f"- cells with fewer than 2 answers IN the primary set (no within-arm pair for F.2's noise "
         f"floor): {len(short_primary)} ({'; '.join('/'.join(k) for k in short_primary) or 'none'})")
L.append("")
L.append("## Human refusal label vs the deterministic outcome code")
L.append("| human refused | outcome code 'refusal' | answers |")
L.append("|---|---|---|")
for (hr, oc), n in sorted(ref_x.items()):
    L.append(f"| {hr} | {oc} | {n} |")
L.append("")
L.append("## Zero-price entries (counted after the 26 Sep 2026 declaration of the zero-price sensitivity)")
L.append(f"- answers with at least one zero-amount price entry: {zero_rows}; zero-amount entries in total: {zero_entries}")
L.append("")
with open(W / "EXPANSION-ANALYSIS-SET-REPORT.md", "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(L) + "\n")

print(f"wrote EXPANSION-ANALYSIS-SET.jsonl ({len(rows)} rows)  sha256 {out_sha}")
print("wrote EXPANSION-ANALYSIS-SET-REPORT.md")
print(f"sources: {dict(src_count)} | primary set {sum(r['in_primary_set'] for r in rows)} | "
      f"cells <2 in primary set {len(short_primary)} | zero-price answers {zero_rows}")
