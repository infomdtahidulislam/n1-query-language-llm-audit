#!/usr/bin/env python3
"""n1_overlap_raters.py — N1: the 303 triple-rated expansion answers on the outcome scale — each rater against the
three-rater E.3 consensus (declared in the post-freeze record of 28 Sep 2026). Descriptive only; no test; outside the
results of record; describes the overlap only. The compared rater is part of the consensus.

Answers: the 303 expansion answers with label_source "consensus-3" (not the 38 that keep their validation-round
consensus); arms en, bn, bl (282 answers; the 21 bl_translit answers are outside the arms of this analysis). Eligibility
is held at the consensus-defined primary set (not refused by the consensus) for every label version.
Label versions: consensus (the analysis-set row) and R1, R2, R3 (each rater's own export, canonicalised through the
registered resolver on the extended tables exactly as the analysis-set builder canonicalises every rater label, with
not-a-brand names removed). Outcomes per answer: local share = local / (local + global) over the distinct classified
brand mentions (NA without a classified mention); price mention = 1 when the answer holds at least one price entry.
Per model and arm: each outcome averaged over the repetitions of a query cell, then over the queries, with contributing
query counts; pooled = equally weighted mean of the six per-model estimates (NA unless all six defined). Contrasts bn–en
and bl–en per model and label version on the queries defined in both arms under both the consensus and that rater (common
support), with the rater-minus-consensus difference in pp. Intervals: 95% percentiles from 10,000 resamples of one frame —
the 77 query IDs represented in the overlap (seed 20261021) — identical for every label version; undefined replicates NA.
Self-tests (identities, no new value): the consensus recomputed from the three raters' raw labels with the builder's
functions equals the analysis-set rows' brands, prices, refused and language for all 303 answers, and the consensus
per-answer local share and price mention equal the registered per-answer values; --selftest-only stops there.

Usage (study root):  python exploratory/n1_overlap_raters.py  ->  exploratory/OVERLAP-RATER-VS-CONSENSUS.json / .md
"""
import argparse, csv, datetime, json, re, sys, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from n1_review_common import load, Frame, six_model_mean, sha, fmt, fmt_ci, NB

ap = argparse.ArgumentParser(); ap.add_argument("root", nargs="?", default="."); ap.add_argument("--selftest-only", action="store_true")
A = ap.parse_args(); ROOT = Path(A.root); OUT = ROOT / "exploratory"
G = load(ROOT)
MODELS, ARMS3, bclass, EXCLUDED = G["MODELS"], G["ARMS3"], G["bclass"], G["EXCLUDED"]
RATERS = ("R1", "R2", "R3"); SEED = 20261021

# ---- the builder's canonicalisation and consensus, verbatim in logic (build_expansion_analysis_set_v2.py) ----------
def fold(s):
    s = unicodedata.normalize("NFKD", str(s)); s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s.strip()); return s.casefold().strip()
def load_map(table, excl_file=None):
    m = {}
    for row in csv.DictReader(open(ROOT / table, newline="", encoding="utf-8")):
        m[fold(row["display_name"])] = row["canonical_id"]
        for al in row["aliases"].split("|"):
            if al.strip():
                m[fold(al)] = row["canonical_id"]
    if excl_file:
        for row in csv.DictReader(open(ROOT / excl_file, newline="", encoding="utf-8")):
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
    if t.upper() in ("BDT", "USD"): return t.upper()
    if t.lower() in ("other", "unstated"): return t.lower()
    if t.lower() in ("taka", "tk", "৳", "টাকা"): return "BDT"
    if t.lower() in ("dollar", "dollars"): return "USD"
    if t.isalpha(): return "other"
    return None
def norm_amount(x):
    fx = float(x); return int(fx) if fx == int(fx) else fx
def price_set_rater(lines_):
    out = set()
    for x in lines_:
        m = PRICE_RE.match(str(x).strip()); cur = fold_currency(m.group(2)) if m else None
        assert cur is not None, f"unparseable price line {x!r}"
        out.add((norm_amount(m.group(1)), cur))
    return frozenset(out)
def rl(row, f):
    v = row.get(f) or []
    return v if isinstance(v, list) else [x for x in str(v).splitlines() if x.strip()]
SETF = ("brands", "recommended", "retailers")
def canon_list(items, cid, keep_excluded):
    out = []
    for x in items:
        if not str(x).strip(): continue
        c = cid(x)
        if c == EXCLUDED:
            if not keep_excluded: continue
            c = fold(x)
        e = c or fold(x)
        if e not in out: out.append(e)
    return out
def human(row, cid, keep_excluded=False):
    h = {"language": row["answer_language"], "refused": str(row["refused"]).lower() == "true", "prices": price_set_rater(rl(row, "prices"))}
    for f in SETF:
        h[f + "_list"] = canon_list(rl(row, f), cid, keep_excluded); h[f] = frozenset(h[f + "_list"])
    return h
def consensus_of(three):
    lc = Counter(h["language"] for h in three).most_common()
    ent = {"answer_language": lc[0][0] if lc[0][1] >= 2 else None, "refused": Counter(h["refused"] for h in three).most_common(1)[0][0]}
    for f in SETF + ("prices",):
        cnt = Counter()
        for h in three:
            for el in h[f]: cnt[el] += 1
        ent[f] = sorted([str(e) for e, n in cnt.items() if n >= 2])
    return ent
TUP = re.compile(r"^\((\d+(?:\.\d+)?), '([^']+)'\)$")
def price_list_from_serialised(strs):
    out = []
    for s in strs:
        m = TUP.match(s); assert m; out.append([norm_amount(m.group(1)), m.group(2)])
    return sorted(out, key=lambda p: (p[1], p[0]))

EXTENDED = make_resolver(load_map("brand_aliases.expansion.csv", "alias_exclusions.expansion.csv"))
E = {}
for rt in RATERS:
    d = json.load(open(ROOT / f"LABEL-EXPANSION-{rt}-labels.json", encoding="utf-8"))
    assert d["task"] == "N1 labelling expansion round" and d["rater"] == rt and not d.get("partial")
    E[rt] = {r["pid"]: r for r in d["labels"]}
label_sha = {rt: sha(ROOT / f"LABEL-EXPANSION-{rt}-labels.json") for rt in RATERS}
aset = [json.loads(l) for l in open(ROOT / "EXPANSION-ANALYSIS-SET-v2.jsonl", encoding="utf-8")]
ov = [r for r in aset if r["label_source"] == "consensus-3"]
assert len(ov) == 303 and all(r["labelled_by"] == "R1+R2+R3" for r in ov)

# ---- self-test: consensus reconstruction equals the analysis-set rows ------------------------------------------------
for r in ov:
    hs = [human(E[rt][r["pid"]], EXTENDED) for rt in RATERS]
    c = consensus_of(hs)
    assert c["brands"] == r["brands"] and price_list_from_serialised(c["prices"]) == [list(p) for p in r["prices"]] and bool(c["refused"]) == r["refused"] and c["answer_language"] == r["answer_language"], r["pid"]
print("self-test OK: the three raters' raw labels reproduce the analysis set's consensus brands, prices, refusal and language for all 303 overlap answers")

def share_of(brands):
    loc = glob = 0
    for e in brands:
        cls = bclass(e)
        if cls == "local": loc += 1
        elif cls == "global": glob += 1
    return (loc / (loc + glob)) if (loc + glob) else None
# identity 2: the consensus per-answer share here equals the registered per-answer local share (F.2/RQ2 machinery) for all 303
from n1_review_common import make_local_share_answer
_lsa = make_local_share_answer(G); _H = {r["key"]: r for r in G["H"]}
for r in ov:
    assert share_of(r["brands"]) == _lsa(_H[r["key"]]) and (len(r["prices"]) > 0) == (len(_H[r["key"]]["prices"]) > 0), r["pid"]
print("self-test OK: the consensus per-answer local share and price mention equal the registered per-answer values for all 303 overlap answers")
if A.selftest_only:
    sys.exit(0)

# ---- per-answer outcomes under each label version --------------------------------------------------------------------
VERSIONS = ("consensus",) + RATERS
per = []   # one entry per eligible answer in the arms en/bn/bl
for r in ov:
    if r["arm"] not in ARMS3 or not r["in_primary_set"]:
        continue
    ent = {"pid": r["pid"], "model": r["model_id"], "query": r["query_id"], "arm": r["arm"], "share": {}, "price": {}}
    ent["share"]["consensus"] = share_of(r["brands"]); ent["price"]["consensus"] = int(len(r["prices"]) > 0)
    for rt in RATERS:
        h = human(E[rt][r["pid"]], EXTENDED)
        ent["share"][rt] = share_of(h["brands_list"]); ent["price"][rt] = int(len(h["prices"]) > 0)
    per.append(ent)
frame_q = sorted({r["query_id"] for r in ov})
assert len(frame_q) == 77
fr = Frame(frame_q, SEED, NB)

def cellq(outcome, version, model, arm):
    d = defaultdict(list)
    for e in per:
        if e["model"] == model and e["arm"] == arm and e[outcome][version] is not None:
            d[e["query"]].append(e[outcome][version])
    return {q: float(np.mean(v)) for q, v in d.items()}

res = {"answers": {"overlap_total": 303, "in_arms_en_bn_bl": len(per), "eligible_consensus_primary": len(per),
                   "by_arm": dict(Counter(e["arm"] for e in per)), "by_model": dict(Counter(e["model"] for e in per))},
       "frame": {"n_query": len(fr.q), "seed": SEED, "query_ids": fr.q}, "levels": {}, "contrasts": {}}
for outcome in ("share", "price"):
    res["levels"][outcome] = {}
    for v in VERSIONS:
        res["levels"][outcome][v] = {"models": {}, "pooled": {}}
        pooled = {a: ([], [], []) for a in ARMS3}
        for m in MODELS:
            res["levels"][outcome][v]["models"][m] = {}
            for a in ARMS3:
                st, reps = fr.stat(cellq(outcome, v, m, a)); res["levels"][outcome][v]["models"][m][a] = st
                pooled[a][0].append(st["estimate"]); pooled[a][1].append(reps); pooled[a][2].append(st["n_query"])
        for a in ARMS3:
            st, _ = six_model_mean(*pooled[a]); res["levels"][outcome][v]["pooled"][a] = st
    res["contrasts"][outcome] = {}
    for rt in RATERS:
        res["contrasts"][outcome][rt] = {"models": {}, "pooled": {}}
        pooledc = {c: {"consensus": ([], [], []), rt: ([], [], []), "diff": ([], [], [])} for c in ("bn-en", "bl-en")}
        for m in MODELS:
            res["contrasts"][outcome][rt]["models"][m] = {}
            for a, b in (("bn", "en"), ("bl", "en")):
                cq = {vv: {x: cellq(outcome, vv, m, x) for x in (a, b)} for vv in ("consensus", rt)}
                common = sorted(set(cq["consensus"][a]) & set(cq["consensus"][b]) & set(cq[rt][a]) & set(cq[rt][b]))
                out = {"common_support_n_query": len(common)}
                reps_v = {}
                for vv in ("consensus", rt):
                    d = {q: cq[vv][a][q] - cq[vv][b][q] for q in common}
                    st, reps = fr.stat(d, scale=100.0); out[vv] = st; reps_v[vv] = reps
                    pooledc[f"{a}-{b}"][vv][0].append(st["estimate"]); pooledc[f"{a}-{b}"][vv][1].append(reps); pooledc[f"{a}-{b}"][vv][2].append(st["n_query"])
                dd = {q: (cq[rt][a][q] - cq[rt][b][q]) - (cq["consensus"][a][q] - cq["consensus"][b][q]) for q in common}
                st, reps = fr.stat(dd, scale=100.0); out["rater_minus_consensus"] = st
                pooledc[f"{a}-{b}"]["diff"][0].append(st["estimate"]); pooledc[f"{a}-{b}"]["diff"][1].append(reps); pooledc[f"{a}-{b}"]["diff"][2].append(st["n_query"])
                res["contrasts"][outcome][rt]["models"][m][f"{a}-{b}"] = out
        for c in ("bn-en", "bl-en"):
            res["contrasts"][outcome][rt]["pooled"][c] = {k: six_model_mean(*pooledc[c][k])[0] for k in ("consensus", rt, "diff")}

meta = {"task": "overlap check on the outcome scale: each rater vs the E.3 consensus on the 303 triple-rated expansion answers (descriptive; no test; outside the results of record; the compared rater is part of the consensus)",
        "eligibility": "consensus-defined primary set (not refused by the consensus); arms en, bn, bl; 21 bl_translit overlap answers outside these arms",
        "label_versions": "consensus = analysis-set row; R1/R2/R3 = the rater's own export canonicalised with the registered resolver on the extended tables, not-a-brand names removed (the analysis-set builder's rules)",
        "outcomes": {"share": "local / (local + global) over distinct classified brand mentions (NA without one)", "price": "1 if at least one price entry, else 0"},
        "estimand": "per-answer values averaged over the repetitions of a query cell, then over queries; pooled = equally weighted mean of six model estimates (NA unless all six defined); contrasts on the common support (defined in both arms under both versions)",
        "bootstrap": {"resamples": NB, "frame": "the 77 query IDs represented in the overlap", "seed": SEED, "rule": "identical resamples for every label version, model, arm and contrast; undefined replicates NA"},
        "inputs": {**G["inputs"], **{f"LABEL-EXPANSION-{rt}-labels.json": label_sha[rt] for rt in RATERS}},
        "script_sha256": sha(Path(__file__)), "common_sha256": sha(Path(__file__).with_name("n1_review_common.py")),
        "run_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
json.dump({"meta": meta, "results": res}, open(OUT / "OVERLAP-RATER-VS-CONSENSUS.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)

L_ = ["# N1 — the triple-rated overlap on the outcome scale: raters vs consensus (descriptive only; not a result of record)", "",
      f"{len(per)} of the 303 overlap answers lie in the arms en/bn/bl and in the consensus-defined primary set (by arm {res['answers']['by_arm']}); frame = {len(fr.q)} query IDs, seed {SEED}, {NB:,} resamples; the compared rater is part of the consensus.", ""]
for outcome, name in (("share", "Local-brand share"), ("price", "Price mention")):
    L_ += [f"## {name} by label version, model and arm (n = contributing queries)", "", "| version | model | en | bn | bl |", "|---|---|---|---|---|"]
    for v in VERSIONS:
        for m in MODELS + ["pooled"]:
            e = res["levels"][outcome][v]["models"][m] if m in MODELS else res["levels"][outcome][v]["pooled"]
            cells = [f"{fmt(e[a]['estimate'])} {fmt_ci(e[a]['ci'])}" + (f" ({e[a]['n_query']})" if m in MODELS else "") for a in ARMS3]
            L_.append(f"| {v} | {m} | " + " | ".join(cells) + " |")
    L_ += ["", f"## {name}: bn–en and bl–en contrasts (pp) on the common support, consensus vs rater", "",
           "| rater | model | contrast | n common | consensus | rater | rater − consensus |", "|---|---|---|---|---|---|---|"]
    for rt in RATERS:
        for m in MODELS + ["pooled"]:
            for c in ("bn-en", "bl-en"):
                if m in MODELS:
                    e = res["contrasts"][outcome][rt]["models"][m][c]
                    L_.append(f"| {rt} | {m} | {c} | {e['common_support_n_query']} | {fmt(e['consensus']['estimate'], 1)} {fmt_ci(e['consensus']['ci'], 1)} | {fmt(e[rt]['estimate'], 1)} {fmt_ci(e[rt]['ci'], 1)} | {fmt(e['rater_minus_consensus']['estimate'], 1)} {fmt_ci(e['rater_minus_consensus']['ci'], 1)} |")
                else:
                    e = res["contrasts"][outcome][rt]["pooled"][c]
                    L_.append(f"| {rt} | pooled | {c} | – | {fmt(e['consensus']['estimate'], 1)} {fmt_ci(e['consensus']['ci'], 1)} | {fmt(e[rt]['estimate'], 1)} {fmt_ci(e[rt]['ci'], 1)} | {fmt(e['diff']['estimate'], 1)} {fmt_ci(e['diff']['ci'], 1)} |")
    L_.append("")
(OUT / "OVERLAP-RATER-VS-CONSENSUS.md").write_text("\n".join(L_) + "\n", encoding="utf-8")
print("written:", OUT / "OVERLAP-RATER-VS-CONSENSUS.json", OUT / "OVERLAP-RATER-VS-CONSENSUS.md")
for outcome in ("share", "price"):
    for rt in RATERS:
        print(outcome, rt, {c: {k: res["contrasts"][outcome][rt]["pooled"][c][k]["estimate"] for k in ("consensus", rt, "diff")} for c in ("bn-en", "bl-en")})
