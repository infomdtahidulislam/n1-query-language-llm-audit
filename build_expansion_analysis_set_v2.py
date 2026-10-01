#!/usr/bin/env python3
"""build_expansion_analysis_set_v2.py — N1: the human-labelled analysis set for the expansion sample,
canonicalised under the EXTENDED alias table (Appendix C.2–C.3 expansion review).

Identical to build_expansion_analysis_set.py (v1, 16th post-freeze record) in every rule — the draw,
the label sources, the E.3 consensus, the price folding, the F.6 primary-set flag — except the name
table: brand / recommended / retailer names are resolved through brand_aliases.expansion.csv (the frozen
table plus the authors' expansion decisions) and names the authors classified "Not a brand"
(alias_exclusions.expansion.csv) are removed before the consensus is formed. Canonicalisation happens
before the consensus, exactly as in v1 and the registered Round-2 scorer. The 38 reused items take the
E.3 consensus of their three Round-2 labels recomputed under the same table (under the frozen table
this reproduces ROUND2-CONSENSUS.json exactly — self-test 1).

Added fields (all derived from the same labels):
  brands_order, retailers_order    first-mention order (RBO, F.2 secondary): a single rater's own order;
                                   for a consensus, entries ordered by their mean first-mention rank over
                                   the raters who listed them (ties: lower best rank, then id)
  *_incl_excluded                  the same sets with the "Not a brand" names kept (as case-folded
                                   strings) — the exclusions-retained sensitivity

SELF-TESTS (run first; the build aborts on any failure):
  1. the consensus code reproduces all 300 items of the canonical ROUND2-CONSENSUS.json (frozen table);
  2. this script, run with the FROZEN table and no exclusions and projected to v1's fields, reproduces
     v1's EXPANSION-ANALYSIS-SET.jsonl byte for byte — so the table is the only thing that changed.

Outputs (LF): EXPANSION-ANALYSIS-SET-v2.jsonl, EXPANSION-ANALYSIS-SET-v2-REPORT.md.  v1 is kept.
Usage (study root):  python build_expansion_analysis_set_v2.py
"""
import csv, hashlib, json, re, sys, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

W = Path(".")
GATES = {
    "EXPANSION-MAPPING-authors-only.csv": "e2bacda5ccc71eee60fb95a9a18350421fb87cc17c7e32f529277b158f3135c0",
    "LABEL-EXPANSION-R1-labels.json": "e81ae46f5723052708dd777893488da50b0bbae27872a58cf33c22e5bd1f74bc",
    "LABEL-EXPANSION-R2-labels.json": "699bec10cf993bb7742e7e852c778689d550a5b2839c4eaa0cb99cebf83af63b",
    "LABEL-EXPANSION-R3-labels.json": "1f2c81dd0941700442fc13e8999f1e4b37a10ba4c37de818c3d8f1e9adc772c0",
    "LABEL-ROUND2-R1-labels.json": "53f46eba77861230edf8ee524ad7a0ec243359a21f43bb3c049470d20e9890ab",
    "LABEL-ROUND2-R2-labels.json": "335dd4dd4f5253abbe253b9fc9686f189d495bd65b453a1e3fe8304c3dac3ce9",
    "LABEL-ROUND2-R3-labels.json": "fea46917cba908904a9fa003b3099389b4f0da6419bae750c99503b5d29f3630",
    "brand_aliases.csv": "0b7bd5e8355c919300129b6ba96008d5cb2d95a691aaf759a1e82823ee2b00ea",
    "EXPANSION-ANALYSIS-SET.jsonl": "f472436a859cf9b9a34cf4ea099394d53b1b03d2b2892f6ee99fe90ebd0230c0",   # v1
    "ROUND2-MAPPING-authors-only.csv": "e458a3c539077772a1813966b36e1ae9feffb7681aef11a7e2e0191b7509d276",
}
R2_CONSENSUS_CONTENT_SHA = "824bd1838790f7c32fa19090ccdef7a8627cfa9adf9b6a1325779434b1d4b265"
EXT = ("brand_aliases.expansion.csv", "retailer_classification.expansion.csv", "alias_exclusions.expansion.csv")
N_DRAWN, N_OVERLAP, N_REUSED = 3023, 303, 38
RATERS = ("R1", "R2", "R3")
EXCLUDED = "__not_a_brand__"
V1_FIELDS = ("answer_language", "arm", "brands", "draw", "in_primary_set", "key", "label_source", "labelled_by",
             "model_id", "outcome", "pid", "prices", "query_id", "recommended", "refused", "rep", "retailers",
             "script_class", "zero_price_entries")

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
    sys.exit("INPUT GATE: ROUND2-CONSENSUS.json content is not the canonical consensus")
inputs["ROUND2-CONSENSUS.json (content)"] = got
# the extended tables must be exactly the ones the extension record registers
rec = json.load(open(W / "EXPANSION-EXTENSION-RECORD.json", encoding="utf-8"))
for f in EXT:
    if sha(W / f) != rec["outputs"][f]:
        sys.exit(f"INPUT GATE: {f} is not the file EXPANSION-EXTENSION-RECORD.json registers")
    inputs[f] = rec["outputs"][f]
assert rec["inputs"]["brand_aliases.csv"] == GATES["brand_aliases.csv"], "extension was not built on the frozen table"
inputs["EXPANSION-EXTENSION-RECORD.json"] = sha(W / "EXPANSION-EXTENSION-RECORD.json")

# ---------- canonicalisation: the registered resolver ----------
def fold(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s.strip())
    return s.casefold().strip()

def load_map(table, excl_file=None):
    m = {}
    with open(W / table, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m[fold(row["display_name"])] = row["canonical_id"]
            for al in row["aliases"].split("|"):
                if al.strip():
                    m[fold(al)] = row["canonical_id"]
    if excl_file:
        with open(W / excl_file, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                m[row["surface_folded"]] = EXCLUDED
    return m

def make_resolver(m):
    def cid(s):
        fs = fold(s)
        if fs in m:
            return m[fs]
        toks = fs.split()
        for n in (3, 2, 1):
            if len(toks) >= n and " ".join(toks[:n]) in m:
                return m[" ".join(toks[:n])]
        return None
    return cid

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

def canon_list(items, cid, keep_excluded):
    """Ordered, de-duplicated canonical entries (first occurrence wins)."""
    out = []
    for x in items:
        if not str(x).strip():
            continue
        c = cid(x)
        if c == EXCLUDED:
            if not keep_excluded:
                continue
            c = fold(x)
        e = c or fold(x)
        if e not in out:
            out.append(e)
    return out

def human(row, cid, keep_excluded=False):
    h = {"language": row["answer_language"], "refused": str(row["refused"]).lower() == "true",
         "prices": price_set_rater(rl(row, "prices"))}
    for f in SETF:
        h[f + "_list"] = canon_list(rl(row, f), cid, keep_excluded)
        h[f] = frozenset(h[f + "_list"])
    return h

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

def consensus_order(three, f, members):
    """Consensus entries by mean first-mention rank over the raters who listed them."""
    def key(e):
        ranks = [h[f + "_list"].index(e) + 1 for h in three if e in h[f + "_list"]]
        return (sum(ranks) / len(ranks), min(ranks), e)
    return sorted(members, key=key)

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

R2 = {c: load_export(f"LABEL-ROUND2-{c}-labels.json", "N1 labelling round 2", c) for c in RATERS}
E = {c: load_export(f"LABEL-EXPANSION-{c}-labels.json", "N1 labelling expansion round", c) for c in RATERS}
mapping = list(csv.DictReader(open(W / "EXPANSION-MAPPING-authors-only.csv", encoding="utf-8")))
assert len(mapping) == N_DRAWN
r2map = {m["pid"]: m["key"] for m in csv.DictReader(open(W / "ROUND2-MAPPING-authors-only.csv", encoding="utf-8"))}

FROZEN = make_resolver(load_map("brand_aliases.csv"))
EXTENDED = make_resolver(load_map("brand_aliases.expansion.csv", "alias_exclusions.expansion.csv"))

# ---------- SELF-TEST 1: reproduce the registered Round-2 consensus ----------
r2_pids = [f"M{i:03d}" for i in range(1, 301)]
bad = [p for p in r2_pids if consensus_of([human(R2[c][p], FROZEN) for c in RATERS]) != r2c["items"][p]]
if bad:
    sys.exit(f"SELF-TEST 1 FAILED on {bad[:5]}")
print("self-test 1: consensus code reproduces all 300 Round-2 consensus items exactly")

def build(cid, extended):
    rows, src_count, removed = [], Counter(), Counter()
    for m in mapping:
        pid = m["pid"]
        base = {"key": m["key"], "pid": pid, "query_id": m["query_id"], "arm": m["arm"],
                "model_id": m["model_id"], "rep": int(m["rep"]), "draw": int(m["draw"]),
                "outcome": m["outcome"], "script_class": m["script_class"]}
        if m["rater"] == "reuse:consensus-round2":
            r2pid = m["reused_round2_pid"]
            assert r2map.get(r2pid) == m["key"], f"{pid}: Round-2 pid {r2pid} key mismatch"
            raw = [R2[c][r2pid] for c in RATERS]
            src, who = "round2-consensus", f"round2:{r2pid}"
            for rt in RATERS:
                assert pid not in E[rt], f"{pid}: reused item unexpectedly on {rt}'s page"
        elif m["overlap"] == "True":
            raw = [E[rt][pid] for rt in RATERS]
            src, who = "consensus-3", "R1+R2+R3"
        else:
            rt = m["rater"]
            assert rt in RATERS and pid in E[rt], f"{pid}: single-rated item missing from {rt}"
            for other in RATERS:
                if other != rt:
                    assert pid not in E[other], f"{pid}: single-rated item also on {other}'s page"
            raw = [E[rt][pid]]
            src, who = "single", rt
        hs = [human(r, cid) for r in raw]
        hk = [human(r, cid, keep_excluded=True) for r in raw]
        if len(hs) == 3:
            c, ck = consensus_of(hs), consensus_of(hk)
            lab = {"brands": c["brands"], "recommended": c["recommended"], "retailers": c["retailers"],
                   "prices": price_list_from_serialised(c["prices"]),
                   "refused": bool(c["refused"]), "answer_language": c["answer_language"]}
            extra = {"brands_order": consensus_order(hs, "brands", c["brands"]),
                     "retailers_order": consensus_order(hs, "retailers", c["retailers"])}
            for f in SETF:
                extra[f + "_incl_excluded"] = ck[f]
        else:
            h, k = hs[0], hk[0]
            lab = {"brands": sorted(h["brands"]), "recommended": sorted(h["recommended"]),
                   "retailers": sorted(h["retailers"]),
                   "prices": sorted([list(p) for p in h["prices"]], key=lambda p: (p[1], p[0])),
                   "refused": h["refused"], "answer_language": h["language"]}
            extra = {"brands_order": list(h["brands_list"]), "retailers_order": list(h["retailers_list"])}
            for f in SETF:
                extra[f + "_incl_excluded"] = sorted(k[f])
        for f in SETF:
            removed[f] += len(set(extra[f + "_incl_excluded"])) - len(set(lab[f]))
        src_count[src] += 1
        row = dict(base)
        row.update(lab)
        row["label_source"], row["labelled_by"] = src, who
        row["in_primary_set"] = not lab["refused"]
        row["zero_price_entries"] = sum(1 for p in lab["prices"] if p[0] == 0)
        if extended:
            row.update(extra)
        rows.append(row)
    assert src_count == {"single": N_DRAWN - N_OVERLAP - N_REUSED, "consensus-3": N_OVERLAP,
                         "round2-consensus": N_REUSED}, src_count
    for rt in RATERS:
        used = {r["pid"] for r in rows if r["labelled_by"] in (rt, "R1+R2+R3")}
        assert used == set(E[rt]), f"{rt}: export pids not all used exactly once"
    rows.sort(key=lambda r: r["key"])
    assert len({r["key"] for r in rows}) == N_DRAWN
    return rows, src_count, removed

def serialise(rows):
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)

# ---------- SELF-TEST 2: frozen table + no exclusions reproduces v1 byte for byte ----------
v1_rows, _, _ = build(FROZEN, extended=False)
v1_text = serialise([{k: r[k] for k in V1_FIELDS} for r in v1_rows])
if hashlib.sha256(v1_text.encode("utf-8")).hexdigest() != GATES["EXPANSION-ANALYSIS-SET.jsonl"]:
    sys.exit("SELF-TEST 2 FAILED: frozen-table mode does not reproduce v1")
print("self-test 2: with the frozen table this script reproduces v1 byte for byte")

rows, src_count, removed = build(EXTENDED, extended=True)
out = W / "EXPANSION-ANALYSIS-SET-v2.jsonl"
with open(out, "w", encoding="utf-8", newline="\n") as f:
    f.write(serialise(rows))
out_sha = sha(out)

# ---------- report (aggregate counts only) ----------
def table_ids(table):
    with open(W / table, newline="", encoding="utf-8") as f:
        return {r["canonical_id"] for r in csv.DictReader(f)}
IDS = {"v1": table_ids("brand_aliases.csv"), "v2": table_ids("brand_aliases.expansion.csv")}
def unresolved(rs, f, ver):
    tot = sum(len(r[f]) for r in rs if r["in_primary_set"])
    un = sum(1 for r in rs if r["in_primary_set"] for e in r[f] if e not in IDS[ver])
    return tot, un
L = ["# N1 — expansion analysis set v2 (human labels, extended name table)", ""]
L.append(f"Output: `EXPANSION-ANALYSIS-SET-v2.jsonl` — {len(rows)} rows, sha256 `{out_sha}` (LF line endings). "
         "v1 (`EXPANSION-ANALYSIS-SET.jsonl`, 16th post-freeze record) is kept unchanged.")
L.append("")
L.append("## Inputs (all gated)")
for k, v in inputs.items():
    L.append(f"- `{k}` {v}")
L.append("")
L.append("## Self-tests")
L.append("- 1: the consensus code reproduces all 300 items of ROUND2-CONSENSUS.json exactly (frozen table).")
L.append("- 2: run with the frozen table and no exclusions, this script reproduces v1 byte for byte "
         "(sha256 f472436a…), so the name table is the only change.")
L.append("")
L.append("## Label sources (unchanged from v1)")
L.append(f"- single {src_count['single']}, consensus of three {src_count['consensus-3']}, "
         f"Round-2 consensus (recomputed under the extended table) {src_count['round2-consensus']}")
L.append("")
L.append("## Names (F.6 primary set)")
for f in SETF:
    tv1, uv1 = unresolved(v1_rows, f, "v1")
    tv2, uv2 = unresolved(rows, f, "v2")
    L.append(f"- {f}: entries {tv2:,} (v1 {tv1:,}); not in the name table {uv2:,} = {100*uv2/max(tv2,1):.1f}% "
             f"(v1, frozen table: {uv1:,} = {100*uv1/max(tv1,1):.1f}%); 'Not a brand' entries removed "
             f"(all 3,023 rows) {removed[f]:,}")
L.append("")
with open(W / "EXPANSION-ANALYSIS-SET-v2-REPORT.md", "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(L) + "\n")
print(f"wrote EXPANSION-ANALYSIS-SET-v2.jsonl ({len(rows)} rows)  sha256 {out_sha}")
print("\n".join(L[-5:]))
