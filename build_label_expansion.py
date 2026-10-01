#!/usr/bin/env python3
"""build_label_expansion.py — N1 E.6 escalation: expanded human labelling (Option C).

DESIGN AS RECORDED (post-freeze record, 22 Sep 2026 — written BEFORE this build):
  - 80 of the 250 main queries, stratified 8 per category (10 categories, from the frozen
    queries.csv, hash-gated), drawn with SEED 20260922; seeded stream per category.
  - Per sampled query: all 6 subject models x 3 primary arms (bn/en/bl) x 2 of the ~5 reps,
    drawn uniformly without replacement per query x model x arm cell from the NON-DEGENERATE
    frame (refused answers stay in; raters judge refusal themselves — F.6 comes from human
    labels). Sampled queries that are robust50 members also get their bl_translit cells
    (6 models x 2 reps). Two reps per cell keeps F.2's D_win computable verbatim.
  - A drawn answer that already carries a Round-2 three-way consensus label keeps it: it is
    NOT re-labelled; it is listed in the mapping as reuse with its Round-2 pid.
  - Rating plan: single-rating; assignment randomized and balanced within query x arm
    (each rater 4 of the 12 answers; a model's two reps never to the same rater in a cell);
    triple-rated overlap = ceil(10% of drawn items), interleaved invisibly (overlap items
    appear in all three pages under the same pid).
  - Instrument: the Round-1 template verbatim (hash-gated), new pids (X0001..), one page per
    rater holding ONLY that rater's items; raters see answer text only.

Run on the study machine, from the study folder:
    python build_label_expansion.py
Writes:
    LABEL-EXPANSION-R1.html / -R2.html / -R3.html   -> one per rater (DIFFERENT contents)
    EXPANSION-MAPPING-authors-only.csv              -> AUTHORS ONLY, never to a rater
    EXPANSION-SELECTION.json                        -> full draw record; reproduces the draw
Each rater returns LABEL-EXPANSION-<rater>-labels.json.
"""
import collections, csv, glob, hashlib, html, json, math, os, random, sys

SEED = 20260922
N_PER_CAT = 8
ARMS = ("bn", "en", "bl")
REPS_PER_CELL = 2
OVERLAP_RATE = 0.10
RATERS = ("R1", "R2", "R3")
FINAL = os.path.join("runs", "coded", "main.final.jsonl")
RESP = os.path.join("runs", "responses", "main")
QUERIES = "queries.csv"
QUERIES_SHA = "9639998a98d605f700f7537fe9a3cfb7ed53975b0b1cb43b7a0bf75b595b5e02"
R2MAP = "ROUND2-MAPPING-authors-only.csv"
TPL_SHA = "0825b63ff067a09083bf131a42503cc8a8198a6e1bfc4a9e53603f1f7d3e38c7"

# ------------- queries and categories (authoritative: the frozen queries.csv) -------------
got_q = hashlib.sha256(open(QUERIES, "rb").read()).hexdigest()
if got_q != QUERIES_SHA:
    sys.exit(f"queries.csv hash changed ({got_q}) — refusing to draw from a non-frozen query table")
cat_of, r50 = {}, set()
for d in csv.DictReader(open(QUERIES, encoding="utf-8")):
    q = str(d.get("query_id") or "")
    if not (q.startswith("Q") and q[1:].isdigit()):
        continue
    cat_of[q] = str(d["category"])
    if str(d.get("robust50") or "").strip().upper() == "YES":
        r50.add(q)
cats = sorted(set(cat_of.values()))
assert len(cat_of) == 250 and len(cats) == 10, f"queries.csv: {len(cat_of)} queries / {len(cats)} categories"
assert all(sum(1 for q in cat_of if cat_of[q] == c) == 25 for c in cats), "queries.csv: categories not 25 each"
assert len(r50) == 50, f"queries.csv: robust50 = {len(r50)}"

rows = [json.loads(l) for l in open(FINAL, encoding="utf-8") if l.strip()]
frame = [r for r in rows if not r["degenerate"]]
translit_q = {r["query_id"] for r in rows if r["arm"] == "bl_translit"}
assert translit_q == r50, "robust50 flags do not match the translit-arm queries"
models = sorted({r["model_id"] for r in rows})
assert len(models) == 6
print(f"main-run final table: {len(rows)} answers; non-degenerate frame: {len(frame)}")

# ---------------- query draw: 8 per category, seeded stream per category ----------------
sampled_q = []
for c in cats:
    pool = sorted(q for q in cat_of if cat_of[q] == c)
    sampled_q += random.Random(f"{SEED}|cat|{c}").sample(pool, N_PER_CAT)
sampled_q = sorted(sampled_q)
assert len(sampled_q) == 80
r50_sampled = sorted(set(sampled_q) & r50)
print(f"queries drawn: 80 (8 x {len(cats)} categories, seed {SEED}); robust50 among them: {len(r50_sampled)}")

# ---------------- answer draw: 2 reps per cell ----------------
cells = collections.defaultdict(list)
for r in frame:
    cells[(r["query_id"], r["model_id"], r["arm"])].append(r)

drawn, shortfalls = [], []
def draw_cell(q, m, arm):
    pool = sorted(cells.get((q, m, arm), []), key=lambda r: r["key"])
    if len(pool) < REPS_PER_CELL:
        shortfalls.append({"query_id": q, "model_id": m, "arm": arm, "available": len(pool)})
        return list(pool)
    return random.Random(f"{SEED}|{q}|{m}|{arm}").sample(pool, REPS_PER_CELL)

for q in sampled_q:
    for m in models:
        for arm in ARMS:
            drawn += draw_cell(q, m, arm)
        if q in r50:
            drawn += draw_cell(q, m, "bl_translit")
assert len({r["key"] for r in drawn}) == len(drawn), "duplicate keys in draw"
n_drawn = len(drawn)
print(f"answers drawn: {n_drawn} "
      f"(primary {sum(1 for r in drawn if r['arm'] in ARMS)}, "
      f"bl_translit {sum(1 for r in drawn if r['arm'] == 'bl_translit')}); "
      f"cells short of {REPS_PER_CELL}: {len(shortfalls)}")

# ---------------- Round-2 coincidences: reuse the consensus label ----------------
r2pid = {}
if os.path.exists(R2MAP):
    for m in csv.DictReader(open(R2MAP, encoding="utf-8")):
        r2pid[m["key"]] = m["pid"]
else:
    sys.exit(f"{R2MAP} not found — run from the study folder")
for r in drawn:
    r["_reuse"] = r2pid.get(r["key"])
reused = [r for r in drawn if r["_reuse"]]
rated = [r for r in drawn if not r["_reuse"]]
print(f"Round-2 coincidences (labels reused, not re-rated): {len(reused)}")

# ---------------- pids: global seeded shuffle, no stratum signal ----------------
shuffled = sorted(drawn, key=lambda r: r["key"])
random.Random(SEED).shuffle(shuffled)
for n, r in enumerate(shuffled, 1):
    r["pid"] = f"X{n:04d}"

# ---------------- assignment: balanced pairs within query x arm ----------------
PAIRS = [("R1", "R2"), ("R1", "R3"), ("R2", "R3")] * 2       # each rater in 4 of 6 pairs
by_cell = collections.defaultdict(list)
for r in rated:
    by_cell[(r["query_id"], r["arm"])].append(r)
for (q, arm), items in sorted(by_cell.items()):
    rng = random.Random(f"{SEED}|assign|{q}|{arm}")
    pairs = PAIRS[:]
    rng.shuffle(pairs)
    per_model = collections.defaultdict(list)
    for r in items:
        per_model[r["model_id"]].append(r)
    for i, m in enumerate(sorted(per_model)):
        reps = sorted(per_model[m], key=lambda r: r["key"])
        rng.shuffle(reps)
        for r, rater in zip(reps, pairs[i]):
            r["_rater"] = rater
assert all("_rater" in r for r in rated), "unassigned items"

# balance check (informational; reuse removals may perturb single cells)
imbal = 0
for (q, arm), items in by_cell.items():
    c = collections.Counter(r["_rater"] for r in items)
    if len(items) == 12 and set(c.values()) != {4}:
        imbal += 1
print(f"query x arm cells with 12 rated items not split 4/4/4: {imbal}")

# ---------------- overlap: ceil(10% of drawn), all three raters ----------------
n_overlap = math.ceil(OVERLAP_RATE * n_drawn)
overlap_pids = set(random.Random(f"{SEED}|overlap").sample(sorted(r["pid"] for r in rated), n_overlap))
for r in rated:
    r["_overlap"] = r["pid"] in overlap_pids
page_items = {rt: [] for rt in RATERS}
for r in rated:
    for rt in RATERS:
        if r["_overlap"] or r["_rater"] == rt:
            page_items[rt].append(r)
loads = {rt: len(v) for rt, v in page_items.items()}
total_ratings = sum(loads.values())
print(f"overlap (triple-rated): {n_overlap}   per-rater items: {loads}   total ratings: {total_ratings}")

# ---------------- mapping + selection (authors only) ----------------
with open("EXPANSION-MAPPING-authors-only.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["pid", "key", "query_id", "arm", "model_id", "rep", "draw", "outcome",
                "script_class", "prose_ratio", "hedged", "extractor_answer_language",
                "rater", "overlap", "reused_round2_pid"])
    for r in shuffled:
        w.writerow([r["pid"], r["key"], r["query_id"], r["arm"], r["model_id"], r["rep"],
                    r["draw"], r["outcome"], r["script_class"], r.get("prose_ratio"),
                    r.get("hedged"), r.get("extractor_answer_language"),
                    ("reuse:consensus-round2" if r["_reuse"] else r["_rater"]),
                    ("" if r["_reuse"] else str(bool(r.get("_overlap")))),
                    r["_reuse"] or ""])

json.dump({"seed": SEED, "design": "E.6 escalation Option C — recorded 22 Sep 2026 before this build",
           "queries_per_category": N_PER_CAT, "queries": sampled_q,
           "robust50_sampled": r50_sampled,
           "reps_per_cell": REPS_PER_CELL, "arms_primary": list(ARMS),
           "n_drawn": n_drawn, "n_reused_round2": len(reused),
           "reused_keys": sorted(r["key"] for r in reused),
           "overlap_rule": "ceil(0.10 x n_drawn), sampled among rated items",
           "n_overlap": n_overlap, "per_rater_items": loads, "total_ratings": total_ratings,
           "cell_shortfalls": shortfalls},
          open("EXPANSION-SELECTION.json", "w"), indent=1)

# ---------------- answer text ----------------
files = {}
for f in glob.glob(os.path.join(RESP, "*", "*.json")):
    k12 = os.path.basename(f).rsplit("_", 1)[1][:-5]
    if k12 in files:
        sys.exit(f"key-fragment collision: {files[k12]} vs {f}")
    files[k12] = f
need = {r["key"]: r for r in rated}
for k, r in need.items():
    p = files.get(k[:12])
    if not p:
        sys.exit(f"no response record for key {k}")
    d = json.load(open(p, encoding="utf-8"))
    if d["key"] != k:
        sys.exit(f"key mismatch reading {p}")
    r["_answer"] = (d.get("meta") or {}).get("content") or ""

# ---------------- instrument: the Round 1 template, verbatim, hash-gated ----------------
src = open("build_label_round1.py", encoding="utf-8").read()
i = src.find('TEMPLATE = r"""')
j = src.rfind('"""', i)
TPL = src[i + len('TEMPLATE = r"""'):j]
got = hashlib.sha256(TPL.encode()).hexdigest()
if got != TPL_SHA:
    sys.exit(f"Round 1 template hash changed ({got}) — refusing to build a different instrument")
assert TPL.count("108") == 10 and TPL.count("ROUND1") == 5

LANGS = ["bn", "banglish", "en", "mixed", "other"]

def card(r):
    pid = r["pid"]
    lang_opts = "".join(
        f'<label class="opt"><input type="radio" name="lang_{pid}" value="{c}"> {c}</label>'
        for c in LANGS)
    ref_opts = "".join(
        f'<label class="opt"><input type="radio" name="ref_{pid}" value="{v}"> {t}</label>'
        for v, t in [("false", "answered / recommended something"), ("true", "refused everything")])
    return f"""
<div class="card" id="card_{pid}">
  <div class="card-head"><span class="pid">{pid}</span><span class="status" id="st_{pid}">not started</span></div>
  <div class="answer">{html.escape(r["_answer"])}</div>
  <div class="fields">
    <label class="f"><span>Brands <small>(one per line — every brand named, positive or negative)</small></span>
      <textarea id="brands_{pid}" rows="3" placeholder="one brand per line"></textarea></label>
    <label class="f"><span>Recommended <small>(only the ones it advises buying; must also be in Brands)</small></span>
      <textarea id="rec_{pid}" rows="2" placeholder="one per line — leave empty if it recommends nothing specific"></textarea></label>
    <label class="f"><span>Prices <small>(one per line as: amount currency — e.g. <code>38000 BDT</code>, <code>500 USD</code>, <code>20000 unstated</code>)</small></span>
      <textarea id="prices_{pid}" rows="2" placeholder="one price per line — leave empty if none"></textarea></label>
    <label class="f"><span>Retailers <small>(named shops/marketplaces only — one per line)</small></span>
      <textarea id="ret_{pid}" rows="2" placeholder="one per line — leave empty if none"></textarea></label>
    <div class="f"><span>Refused?</span><div class="opts">{ref_opts}</div></div>
    <div class="f"><span>Answer language <small>(judged on the sentences, not brand names or prices)</small></span><div class="opts">{lang_opts}</div></div>
    <label class="f"><span>Comments <small>(anything that was hard to judge — flag, don't guess silently)</small></span>
      <input type="text" id="cmt_{pid}" maxlength="600" placeholder="optional — but please note anything borderline"></label>
  </div>
</div>"""

for rater in RATERS:
    items = page_items[rater][:]
    random.Random(f"{SEED}|page|{rater}").shuffle(items)
    ids = [r["pid"] for r in items]
    base = (TPL.replace("108", str(len(items))).replace("ROUND1", "EXPANSION")
               .replace("round1", "expansion").replace("Round 1", "Expansion Round")
               .replace("round 1", "expansion round"))
    page = (base.replace("__CARDS__", "".join(card(r) for r in items))
                .replace("__IDS__", json.dumps(ids)).replace("__RATER__", rater))
    open(f"LABEL-EXPANSION-{rater}.html", "w", encoding="utf-8").write(page)
    print(f"wrote LABEL-EXPANSION-{rater}.html ({len(page):,} bytes, {len(items)} items)")

print("wrote EXPANSION-MAPPING-authors-only.csv  (AUTHORS ONLY — never send to a rater)")
print("wrote EXPANSION-SELECTION.json  (full draw record; re-running this script reproduces it)")
print("\nsend each rater ONLY their own LABEL-EXPANSION-<rater>.html; they return "
      "LABEL-EXPANSION-<rater>-labels.json")
