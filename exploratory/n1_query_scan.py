#!/usr/bin/env python3
"""n1_query_scan.py — N1: a check of the frozen query file against Appendix A.2 (no brand, product-line or retailer
names) and A.7 item 7 (no locations beyond "in Bangladesh"), plus the market-cue counts the paper quotes (post-freeze
record of 28 Sep 2026). Descriptive; changes nothing.

Inputs (hash-gated): queries.csv (frozen, sha256 9639998a…); search terms = every display name and alias of the frozen
brand table (brand_aliases.csv) and of the extended tables (brand_aliases.expansion.csv, retailer_classification.expansion.csv),
plus a fixed list of platform and marketplace names. Every rendering (en, bn, bl) of all 250 queries is scanned:
Latin terms as whole words on the case-folded text (the resolver's fold), Bangla-script terms as substrings.
Every match is listed; the record classifies them.

Usage (study root):  python exploratory/n1_query_scan.py  ->  exploratory/QUERY-SCAN.json / .md
"""
import csv, hashlib, json, re, unicodedata, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
OUT = ROOT / "exploratory"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
Q_SHA = "9639998a98d605f700f7537fe9a3cfb7ed53975b0b1cb43b7a0bf75b595b5e02"
if sha(ROOT / "queries.csv") != Q_SHA:
    raise SystemExit("queries.csv is not the frozen file")
rows = list(csv.DictReader(open(ROOT / "queries.csv", encoding="utf-8")))
assert len(rows) == 250 and Counter(r["subtype"] for r in rows) == {"open": 100, "budget": 80, "use-case": 40, "purchase-channel": 30}

def fold(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s.strip())
    return s.casefold().strip()

# ---- search terms --------------------------------------------------------------------------------------------
terms = {}   # folded term -> (source, canonical)
def add_table(name, kind):
    for r in csv.DictReader(open(ROOT / name, encoding="utf-8", newline="")):
        names = [r["display_name"]] + [a for a in (r.get("aliases") or "").split("|") if a.strip()]
        for n in names:
            f = fold(n)
            if f and f not in terms:
                terms[f] = (f"{kind}:{name}", r["canonical_id"])
add_table("brand_aliases.csv", "brand-frozen")
add_table("brand_aliases.expansion.csv", "brand-extended")
add_table("retailer_classification.expansion.csv", "retailer-extended")
PLATFORMS = ["facebook", "fb", "instagram", "youtube", "tiktok", "whatsapp", "telegram", "messenger", "twitter", "google",
             "amazon", "alibaba", "aliexpress", "ebay", "daraz", "bikroy", "evaly", "pickaboo", "chaldal", "foodpanda",
             "pathao", "uber", "bkash", "nagad", "rocket", "upay", "ফেসবুক", "ইনস্টাগ্রাম", "ইউটিউব", "টিকটক", "হোয়াটসঅ্যাপ",
             "গুগল", "অ্যামাজন", "দারাজ", "বিক্রয়", "ইভ্যালি", "বিকাশ", "নগদ", "রকেট"]
for p in PLATFORMS:
    terms.setdefault(fold(p), ("platform-list", p))
# generic English words that are also alias entries would flood the scan; they are kept in the scan but listed apart
GENERIC = {"vision", "smart", "walton", "best", "one", "pro", "max", "plus", "mini", "note", "air", "lite", "prime", "super"}

def is_bangla(s):
    return any("ঀ" <= ch <= "৿" for ch in s)

latin_terms = {t: v for t, v in terms.items() if not is_bangla(t)}
bangla_terms = {t: v for t, v in terms.items() if is_bangla(t)}
word_re = {t: re.compile(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])") for t in latin_terms}

matches, generic_hits = [], []
for r in rows:
    for arm in ("en", "bn", "bl"):
        text = r[f"{arm}_text"]
        ft = fold(text)
        for t, rx in word_re.items():
            if rx.search(ft):
                hit = {"query_id": r["query_id"], "arm": arm, "term": t, "source": latin_terms[t][0], "canonical": latin_terms[t][1], "text": text}
                (generic_hits if t in GENERIC else matches).append(hit)
        for t, v in bangla_terms.items():
            if t in text:
                matches.append({"query_id": r["query_id"], "arm": arm, "term": t, "source": v[0], "canonical": v[1], "text": text})

# ---- locations and cues -------------------------------------------------------------------------------------
PLACE = {"en": re.compile(r"\b(bangladesh|bangladeshi|dhaka|chittagong|chattogram|sylhet|khulna|rajshahi|barishal|barisal|rangpur|mymensingh|comilla|cumilla|gazipur|narayanganj)\b", re.I),
         "bn": re.compile(r"(বাংলাদেশ|ঢাকা|চট্টগ্রাম|সিলেট|খুলনা|রাজশাহী|বরিশাল|রংপুর|ময়মনসিংহ|কুমিল্লা|গাজীপুর|নারায়ণগঞ্জ)"),
         "bl": re.compile(r"\b(bangladesh\w*|dhaka\w*|chittagong|chattogram|sylhet|khulna|rajshahi|barishal|barisal|rangpur|mymensingh|comilla|cumilla|gazipur|narayanganj)\b", re.I)}
CUR = {"en": re.compile(r"(৳|\btaka\b|\btk\b|\bbdt\b|\btakas\b|\$|\busd\b|\bdollar)", re.I),
       "bn": re.compile(r"(৳|টাকা|টাকার|টাকায়|ডলার)"),
       "bl": re.compile(r"(৳|\btaka\w*|\btk\b|\bbdt\b|\btakar\b|\btakay\b|\$|\bdollar)", re.I)}
place_hits, cur_hits = defaultdict(dict), defaultdict(dict)
for r in rows:
    for arm in ("en", "bn", "bl"):
        t = r[f"{arm}_text"]
        pm = PLACE[arm].findall(t)
        if pm:
            place_hits[r["query_id"]][arm] = sorted({(m if isinstance(m, str) else m[0]).lower() for m in pm})
        cm = CUR[arm].findall(t)
        if cm:
            cur_hits[r["query_id"]][arm] = sorted({(m if isinstance(m, str) else m[0]) for m in cm})
budget = [r["query_id"] for r in rows if r["subtype"] == "budget"]
budget_all3 = [q for q in budget if all(a in cur_hits.get(q, {}) for a in ("en", "bn", "bl"))]
named_all3 = [q for q in place_hits if all(a in place_hits[q] for a in ("en", "bn", "bl"))]
named_any = sorted(place_hits)
nonbudget_named = [q for q in named_all3 if q not in budget]
others = [r["query_id"] for r in rows if r["query_id"] not in budget and r["query_id"] not in place_hits]
others_en_currency = [q for q in others if "en" in cur_hits.get(q, {})]
others_any_currency = {q: cur_hits[q] for q in others if q in cur_hits}
subtype = {r["query_id"]: r["subtype"] for r in rows}
cue = set(budget) | set(nonbudget_named)
xtab = {st: {"cue": sum(1 for q in cue if subtype[q] == st), "no_cue": sum(1 for r in rows if subtype[r["query_id"]] == st and r["query_id"] not in cue)}
        for st in ("open", "budget", "use-case", "purchase-channel")}
dhaka = sorted(q for q in place_hits if any("dhaka" in x or "ঢাকা" in x for a in place_hits[q] for x in place_hits[q][a]))
texts = {r["query_id"]: {a: r[f"{a}_text"] for a in ("en", "bn", "bl")} for r in rows}

out = {"meta": {"queries_sha256": Q_SHA, "script_sha256": sha(Path(__file__)), "n_terms": len(terms),
                "term_sources": dict(Counter(v[0] for v in terms.values())), "generic_terms_listed_apart": sorted(GENERIC)},
       "name_matches": matches, "generic_word_hits": generic_hits,
       "places": {q: place_hits[q] for q in named_any}, "dhaka_queries": dhaka,
       "currency": {q: cur_hits[q] for q in sorted(cur_hits)},
       "cues": {"budget": budget, "budget_with_currency_in_all_three": budget_all3,
                "named_place_in_all_three": named_all3, "named_place_any_rendering": named_any,
                "non_budget_named_place": nonbudget_named, "cue_group": sorted(cue), "no_cue_group": sorted(set(subtype) - cue),
                "others_no_place": others, "others_with_english_currency": others_en_currency,
                "others_with_any_currency_mention": others_any_currency, "cue_by_subtype": xtab},
       "texts_of_interest": {q: texts[q] for q in sorted(set(["Q150", "Q172", "Q180", "Q185", "Q198"] + dhaka + [m["query_id"] for m in matches]))}}
OUT.mkdir(exist_ok=True)
json.dump(out, open(OUT / "QUERY-SCAN.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
L = ["# N1 — frozen query file scan (A.2 names, A.7 locations, market cues)", "",
     f"queries.csv `{Q_SHA[:12]}…`; {len(terms)} search terms ({out['meta']['term_sources']}); generic English words listed apart: {sorted(GENERIC)}.", "",
     "## Name matches (brand, product-line, platform, retailer terms)", ""]
for m in matches:
    L.append(f"- {m['query_id']} {m['arm']}: `{m['term']}` ({m['source']} → {m['canonical']}): {m['text']}")
L += ["", f"## Generic-word hits (listed, not names): {len(generic_hits)}", ""]
for m in generic_hits:
    L.append(f"- {m['query_id']} {m['arm']}: `{m['term']}` → {m['canonical']}: {m['text']}")
L += ["", "## Places", ""] + [f"- {q}: {place_hits[q]}" for q in named_any]
L += ["", "## Cue counts", "", f"- budget queries: {len(budget)}; with a currency mention in all three renderings: {len(budget_all3)}",
      f"- non-budget queries naming a place in all three renderings: {len(nonbudget_named)} {nonbudget_named}",
      f"- queries naming a place in any rendering: {len(named_any)}; Dhaka: {dhaka}",
      f"- other queries (no place): {len(others)}; with an English currency mention: {others_en_currency}; with any currency mention: {others_any_currency}",
      f"- cue by subtype (cue / no cue): {xtab}", ""]
(OUT / "QUERY-SCAN.md").write_text("\n".join(L), encoding="utf-8")
print(json.dumps({"name_matches": [(m['query_id'], m['arm'], m['term']) for m in matches], "generic_hits": len(generic_hits),
                  "places": {q: place_hits[q] for q in named_any}, "budget": len(budget), "budget_all3": len(budget_all3),
                  "nonbudget_named": nonbudget_named, "others": len(others), "others_en_currency": others_en_currency,
                  "others_any_currency": others_any_currency, "xtab": xtab, "dhaka": dhaka}, ensure_ascii=False, indent=1))
