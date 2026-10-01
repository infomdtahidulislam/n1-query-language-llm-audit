#!/usr/bin/env python3
"""build_label_round2.py — N1 Round 2 / E.3 human ground truth (300 main-run answers).

REGISTERED SCOPE (prereg E.3): 300 main-run answers, stratified across model x arm x outcome
code and script class (so `mixed`-script answers are represented), labelled INDEPENDENTLY by
all three raters using the codebook; no discussion, no AI assistance, model identity hidden.

ALLOCATION (operationalised and approved by the authors 17 Sep 2026, before the draw; the
registration fixes the strata but not the allocation): every non-empty
model x arm x outcome x script_class stratum receives **1** answer, and the remaining draws are
allocated proportionally to stratum size by the largest-remainder method, capped at stratum
size. This is what the registered parenthetical asks for: rare cells (mixed script, refusals,
degenerate) are deliberately over-represented so the D.4 script-class cuts and the D.5 refusal
conjunct can actually be validated. Consequence, stated in the paper: agreement figures from
this set describe the stratified validation sample, not the corpus.
**Seed 20260917**, fixed before the draw; the draw is reproducible by re-running this script.

The labelling instrument is the ROUND 1 TEMPLATE ITSELF, read from build_label_round1.py at
build time and checked against its recorded hash, so the two rounds are the same instrument
(only the round name, the answer count and the storage/export names differ).

Run on the study machine, from the study folder:
    python build_label_round2.py
Writes:
    LABEL-ROUND2-R1.html / -R2.html / -R3.html   -> one per rater (identical content)
    ROUND2-MAPPING-authors-only.csv              -> AUTHORS ONLY, never to a rater
    ROUND2-SELECTION.json                        -> allocation per stratum + drawn keys
Each rater returns LABEL-ROUND2-<rater>-labels.json.
"""
import collections, csv, glob, hashlib, html, json, os, random, sys

SEED = 20260917
TARGET = 300
FINAL = os.path.join("runs", "coded", "main.final.jsonl")
RESP = os.path.join("runs", "responses", "main")
TPL_SHA = "0825b63ff067a09083bf131a42503cc8a8198a6e1bfc4a9e53603f1f7d3e38c7"

rows = [json.loads(l) for l in open(FINAL, encoding="utf-8") if l.strip()]
print(f"main-run final table: {len(rows)} answers")

# ---------------- draw ----------------
cells = collections.defaultdict(list)
for r in rows:
    cells[(r["model_id"], r["arm"], r["outcome"], r["script_class"])].append(r)
keys = sorted(cells)
N = len(rows)
if len(keys) > TARGET:
    sys.exit(f"{len(keys)} strata exceed the {TARGET} draws — allocation rule does not apply")

rem = TARGET - len(keys)                       # after the guaranteed 1 per stratum
exact = {c: len(cells[c]) * rem / N for c in keys}
add = {c: int(exact[c]) for c in keys}
left = rem - sum(add.values())
rng_tie = random.Random(SEED)
for c in sorted(keys, key=lambda c: (-(exact[c] - add[c]), rng_tie.random()))[:left]:
    add[c] += 1
alloc = {c: min(1 + add[c], len(cells[c])) for c in keys}
short = TARGET - sum(alloc.values())
while short > 0:                               # redistribute what the caps freed
    room = [c for c in keys if alloc[c] < len(cells[c])]
    if not room:
        break
    room.sort(key=lambda c: (-(len(cells[c]) - alloc[c]), c))
    alloc[room[0]] += 1
    short -= 1

sample = []
for c in keys:                                 # one seeded stream per stratum
    pool = sorted(cells[c], key=lambda r: r["key"])
    sample += random.Random(f"{SEED}|{'|'.join(c)}").sample(pool, alloc[c])
assert len({r["key"] for r in sample}) == len(sample) == TARGET, "bad draw"
print(f"drawn: {TARGET} across {len(keys)} strata (seed {SEED}, guarantee-1 + proportional)")
for ix, name in ((1, "arm"), (2, "outcome"), (3, "script_class")):
    d = collections.Counter()
    for c, v in alloc.items():
        d[c[ix]] += v
    print(f"  by {name:<13}" + "  ".join(f"{k}={v}" for k, v in sorted(d.items())))

# ---------------- answer text ----------------
files = {}
for f in glob.glob(os.path.join(RESP, "*", "*.json")):
    k12 = os.path.basename(f).rsplit("_", 1)[1][:-5]
    if k12 in files:
        sys.exit(f"key-fragment collision: {files[k12]} vs {f}")
    files[k12] = f
for r in sample:
    p = files.get(r["key"][:12])
    if not p:
        sys.exit(f"no response record for key {r['key']}")
    d = json.load(open(p, encoding="utf-8"))
    if d["key"] != r["key"]:
        sys.exit(f"key mismatch reading {p}")
    r["_answer"] = (d.get("meta") or {}).get("content") or ""

shuffled = sorted(sample, key=lambda r: r["key"])
random.Random(SEED).shuffle(shuffled)          # ids carry no stratum signal
for n, r in enumerate(shuffled, 1):
    r["pid"] = f"M{n:03d}"

with open("ROUND2-MAPPING-authors-only.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["pid", "key", "query_id", "arm", "model_id", "rep", "draw", "outcome",
                "script_class", "prose_ratio", "hedged", "extractor_answer_language"])
    for r in shuffled:
        w.writerow([r["pid"], r["key"], r["query_id"], r["arm"], r["model_id"], r["rep"],
                    r["draw"], r["outcome"], r["script_class"], r.get("prose_ratio"),
                    r.get("hedged"), r.get("extractor_answer_language")])

json.dump({"seed": SEED, "target": TARGET, "population": N, "strata": len(keys),
           "rule": "prereg E.3 strata (model x arm x outcome x script_class); allocation "
                   "operationalised 17 Sep 2026 with author approval: guarantee 1 per non-empty "
                   "stratum, remainder proportional by largest remainder, capped at stratum size",
           "allocation_per_stratum": {"|".join(c): alloc[c] for c in keys},
           "stratum_totals": {"|".join(c): len(cells[c]) for c in keys},
           "drawn_keys": sorted(r["key"] for r in sample)},
          open("ROUND2-SELECTION.json", "w"), indent=1)

# ---------------- instrument: the Round 1 template, verbatim ----------------
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

cards = "".join(card(r) for r in shuffled)
ids = [r["pid"] for r in shuffled]
base = (TPL.replace("108", str(TARGET)).replace("ROUND1", "ROUND2")
           .replace("round1", "round2").replace("Round 1", "Round 2")
           .replace("round 1", "round 2"))
for rater in ["R1", "R2", "R3"]:
    page = (base.replace("__CARDS__", cards).replace("__IDS__", json.dumps(ids))
                .replace("__RATER__", rater))
    open(f"LABEL-ROUND2-{rater}.html", "w", encoding="utf-8").write(page)
    print(f"wrote LABEL-ROUND2-{rater}.html ({len(page):,} bytes)")
print("wrote ROUND2-MAPPING-authors-only.csv  (AUTHORS ONLY — never send to a rater)")
print("wrote ROUND2-SELECTION.json  (allocation per stratum + drawn keys; reproduces the draw)")
print("\nsend each rater ONLY their own LABEL-ROUND2-<rater>.html; they return "
      "LABEL-ROUND2-<rater>-labels.json")
