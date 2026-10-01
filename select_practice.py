#!/usr/bin/env python3
"""Select 15 Session-B practice answers from the smoke corpus (N1, 11 Sep 2026).

Purposive stratified sample for rater calibration only — excluded from every
statistic (Appendix D). Deterministic: greedy feature-coverage with model>=2
floor, fixed seed 20260911, so the pick is reproducible and documented.
Excludes the 23 answers R1 already saw in the adjudication.
Writes an authors-only mapping (opaque ids P01..P15 -> key/model/arm/features).
"""
import csv, json, random
from collections import Counter

SEED = 20260911
U = "/mnt/user-data/uploads/New Experiment/runs"
coded = {json.loads(l)['key']: json.loads(l)
         for l in open(f"{U}/coded/smoke.jsonl", encoding="utf-8") if l.strip()}
ext = {json.loads(l)['subject_key']: (json.loads(l).get('extraction') or {})
       for l in open(f"{U}/extracted/smoke.primary.jsonl", encoding="utf-8") if l.strip()}
adj = {json.loads(l)['key'] for l in open(f"{U}/coded/smoke.adjudicate.jsonl", encoding="utf-8") if l.strip()}

def features(k):
    c, ex = coded[k], ext.get(k, {})
    nb, nr, npr, nret = (len(ex.get(f) or []) for f in ("brands", "recommended", "prices", "retailers"))
    content = bool((ex.get("brands") or []) or (ex.get("retailers") or []) or (ex.get("prices") or []))
    curs = {p.get("currency") for p in (ex.get("prices") or []) if isinstance(p, dict)}
    tags = set()
    tags.add("lang:" + str(ex.get("answer_language")))
    tags.add("arm:" + c["arm"])
    tags.add("model:" + c["model_id"])
    if c["f4_fires"] and content: tags.add("hedged")
    if 0 < nr < nb: tags.add("rec_subset")
    if nr == nb and nb > 0: tags.add("rec_all")
    if nr == 0 and nb > 0: tags.add("rec_none")
    if "BDT" in curs: tags.add("price_bdt")
    if "USD" in curs: tags.add("price_usd")
    if nret > 0: tags.add("retailers")
    if nb >= 4: tags.add("many_brands")
    if nb == 0 and not content: tags.add("no_commercial")
    return tags, dict(nb=nb, nr=nr, npr=npr, nret=nret)

pool = [k for k in coded if k not in adj]
tagmap = {k: features(k)[0] for k in pool}

# target buckets we want represented, weighted (scarce/subtle features heavier)
TARGETS = {
    "lang:mixed": 5, "lang:banglish": 3, "lang:bn": 1, "lang:en": 1,
    "arm:bl": 2, "arm:bl_translit": 2, "arm:bn": 1, "arm:en": 1,
    "hedged": 4, "rec_subset": 4, "rec_all": 2, "rec_none": 1,
    "price_bdt": 3, "price_usd": 4, "retailers": 2, "many_brands": 1, "no_commercial": 2,
}
MODELS = ["claude-sonnet-5", "deepseek-v4-flash", "gemini-3-flash", "gpt-5.6-luna", "grok-4.6", "kimi-k3"]
rng = random.Random(SEED)

chosen = []
covered = Counter()
model_ct = Counter()

def gain(k):
    g = 0.0
    for t in tagmap[k]:
        if t in TARGETS and covered[t] < 3:      # diminishing after 3 of a kind
            g += TARGETS[t] / (1 + covered[t])
    m = next(t[6:] for t in tagmap[k] if t.startswith("model:"))
    if model_ct[m] < 2: g += 6                    # push the >=2/model floor
    return g

remaining = set(pool)
while len(chosen) < 15:
    best = max(remaining, key=lambda k: (gain(k), rng.random()))
    chosen.append(best); remaining.discard(best)
    for t in tagmap[best]: covered[t] += 1
    model_ct[next(t[6:] for t in tagmap[best] if t.startswith("model:"))] += 1

# repair: guarantee >=2 per model
for m in MODELS:
    while model_ct[m] < 2:
        cands = [k for k in remaining if ("model:" + m) in tagmap[k]]
        if not cands: break
        # drop the lowest-value chosen answer from an over-represented model
        over = [k for k in chosen if model_ct[next(t[6:] for t in tagmap[k] if t.startswith("model:"))] > 2]
        drop = min(over, key=gain) if over else None
        add = max(cands, key=lambda k: (gain(k), rng.random()))
        if drop:
            dm = next(t[6:] for t in tagmap[drop] if t.startswith("model:"))
            chosen.remove(drop); remaining.add(drop); model_ct[dm] -= 1
        chosen.append(add); remaining.discard(add); model_ct[m] += 1

# stable shuffle for opaque ids so model/arm ordering leaks nothing
rng.shuffle(chosen)
rows = []
for n, k in enumerate(chosen, 1):
    c, ex = coded[k], ext.get(k, {})
    _, cnt = features(k)
    rows.append(dict(pid=f"P{n:02d}", key=k, query_id=c["query_id"], arm=c["arm"],
                     model_id=c["model_id"], rep=c["rep"], draw=c["draw"],
                     answer_language=ex.get("answer_language"),
                     n_brands=cnt["nb"], n_recommended=cnt["nr"], n_prices=cnt["npr"],
                     n_retailers=cnt["nret"], tags="|".join(sorted(tagmap[k]))))

with open("PRACTICE-MAPPING-authors-only.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
json.dump([r["key"] for r in rows], open("practice_keys.json", "w"))

print("selected 15 | per model:", dict(model_ct))
print("arms:", dict(Counter(r["arm"] for r in rows)))
print("langs:", dict(Counter(r["answer_language"] for r in rows)))
feat = Counter()
for k in chosen:
    for t in tagmap[k]:
        if t in TARGETS: feat[t] += 1
print("feature coverage:", {t: feat[t] for t in TARGETS})
print("wrote PRACTICE-MAPPING-authors-only.csv + practice_keys.json")
