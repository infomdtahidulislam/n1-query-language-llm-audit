#!/usr/bin/env python3
"""n1_place_scan.py — N1: read-only text check of the frozen query file for place and country names OUTSIDE Bangladesh
(requested by the paper's writer on 29 Sep 2026 after the scan of the record of 28 Sep 2026, whose place terms were
Bangladesh, Dhaka and ten other Bangladeshi cities and divisions). The term list below was fixed in this file before the
scan ran; the record that reports the scan states the list and every match. No answer text is read; nothing changes.

Terms. Latin-script terms are matched on the case-folded text of all three renderings (en, bn, bl) in two ways: as whole
words ("exact") and as a whole word optionally followed by up to four letters ("stem": Banglish case endings such as
-er, -e, -te, -r, -ke, -ra; the stem hits are a superset of the exact hits and are listed so that inflected forms are not
missed; every hit is then read). The bare token "us" is deliberately absent (the English pronoun); "u.s.", "u.s.a" and
"usa" stand for the United States. Bangla-script terms are matched as substrings of all three renderings (as the scan of
the record of 28 Sep 2026 matched them), which can produce false positives inside longer words; every hit is listed.

Usage (study root):  python exploratory/n1_place_scan.py  ->  exploratory/PLACE-SCAN.json / .md
"""
import csv, datetime, hashlib, json, re, unicodedata
from pathlib import Path

ROOT = Path(".")
OUT = ROOT / "exploratory"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
Q_SHA = "9639998a98d605f700f7537fe9a3cfb7ed53975b0b1cb43b7a0bf75b595b5e02"
assert sha(ROOT / "queries.csv") == Q_SHA, "queries.csv is not the frozen file"

LATIN = [
    # South Asia
    "india", "indian", "bharat", "bharot", "hindustan", "kolkata", "calcutta", "west bengal", "bengal", "assam", "tripura",
    "meghalaya", "siliguri", "delhi", "mumbai", "bombay", "chennai", "bangalore", "bengaluru", "hyderabad",
    "pakistan", "pakistani", "karachi", "lahore", "islamabad", "nepal", "nepali", "kathmandu", "bhutan", "thimphu",
    "myanmar", "burma", "burmese", "yangon", "rangoon", "sri lanka", "srilanka", "lanka", "colombo", "maldives",
    # East and South-East Asia
    "china", "chinese", "chin", "beijing", "shanghai", "shenzhen", "hong kong", "hongkong", "taiwan", "japan", "japanese",
    "tokyo", "korea", "korean", "seoul", "singapore", "malaysia", "malaysian", "kuala lumpur", "thailand", "thai", "bangkok",
    "indonesia", "vietnam", "philippines",
    # Americas, Europe, Oceania
    "america", "american", "amerika", "usa", "u.s.a", "u.s", "united states", "new york", "california", "canada", "canadian",
    "uk", "u.k", "britain", "british", "england", "london", "europe", "european", "germany", "german", "france", "french",
    "italy", "italian", "russia", "russian", "turkey", "turkish", "australia", "australian",
    # Middle East and Africa
    "dubai", "uae", "emirates", "abu dhabi", "saudi", "saudi arabia", "riyadh", "jeddah", "arab", "qatar", "doha", "kuwait",
    "oman", "bahrain", "egypt", "africa", "african", "middle east", "gulf", "asia", "asian",
]
BANGLA = [
    "ভারত", "ইন্ডিয়া", "হিন্দুস্তান", "কলকাতা", "ক্যালকাটা", "পশ্চিমবঙ্গ", "পশ্চিম বঙ্গ", "বঙ্গ", "আসাম", "অসম", "ত্রিপুরা", "মেঘালয়",
    "শিলিগুড়ি", "দিল্লি", "মুম্বাই", "চেন্নাই", "ব্যাঙ্গালোর", "বেঙ্গালুরু", "হায়দরাবাদ", "পাকিস্তান", "করাচি", "লাহোর", "নেপাল", "কাঠমান্ডু",
    "ভুটান", "মিয়ানমার", "মায়ানমার", "বার্মা", "শ্রীলঙ্কা", "শ্রীলংকা", "লঙ্কা", "কলম্বো", "মালদ্বীপ",
    "চীন", "চায়না", "চীনা", "বেইজিং", "হংকং", "তাইওয়ান", "জাপান", "টোকিও", "কোরিয়া", "সিউল", "সিঙ্গাপুর", "সিংগাপুর", "মালয়েশিয়া",
    "কুয়ালালামপুর", "থাইল্যান্ড", "ব্যাংকক", "ইন্দোনেশিয়া", "ভিয়েতনাম", "ফিলিপাইন",
    "আমেরিকা", "মার্কিন", "যুক্তরাষ্ট্র", "ইউএসএ", "নিউইয়র্ক", "নিউ ইয়র্ক", "কানাডা", "ইউকে", "যুক্তরাজ্য", "ব্রিটেন", "ইংল্যান্ড", "লন্ডন",
    "ইউরোপ", "জার্মানি", "ফ্রান্স", "ইতালি", "রাশিয়া", "তুরস্ক", "অস্ট্রেলিয়া",
    "দুবাই", "আমিরাত", "আবুধাবি", "সৌদি", "রিয়াদ", "জেদ্দা", "আরব", "কাতার", "দোহা", "কুয়েত", "ওমান", "বাহরাইন", "মিশর", "আফ্রিকা",
    "এশিয়া", "মধ্যপ্রাচ্য", "উপসাগর",
]
assert len(LATIN) == len(set(LATIN)) and len(BANGLA) == len(set(BANGLA))
BANGLA = [unicodedata.normalize("NFC", t) for t in BANGLA]

def fold(s):
    return unicodedata.normalize("NFC", s).casefold()

exact_re = {t: re.compile(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])") for t in LATIN}
stem_re = {t: re.compile(r"(?<![a-z0-9])" + re.escape(t) + r"[a-z]{0,4}(?![a-z0-9])") for t in LATIN}
rows = list(csv.DictReader(open(ROOT / "queries.csv", encoding="utf-8")))
assert len(rows) == 250
hits = []
for r in rows:
    for arm in ("en", "bn", "bl"):
        text = r[f"{arm}_text"]; ft = fold(text); ntext = unicodedata.normalize("NFC", text)
        for t in LATIN:
            ex = exact_re[t].search(ft) is not None
            st = stem_re[t].search(ft)
            if st:
                hits.append({"query_id": r["query_id"], "arm": arm, "script": "latin", "term": t, "kind": "exact" if ex else "stem",
                             "matched": st.group(0), "text": text})
        for t in BANGLA:
            if t in ntext:
                hits.append({"query_id": r["query_id"], "arm": arm, "script": "bangla", "term": t, "kind": "substring", "matched": t, "text": text})
meta = {"task": "read-only text check of the frozen query file for place and country names outside Bangladesh; nothing changes",
        "queries.csv_sha256": Q_SHA, "script_sha256": sha(Path(__file__)), "n_texts": 750, "n_latin_terms": len(LATIN), "n_bangla_terms": len(BANGLA),
        "latin_terms": LATIN, "bangla_terms": BANGLA,
        "matching": {"latin": "case-folded whole word (exact) and whole word plus up to four trailing letters (stem), on en, bn and bl; the bare token 'us' is not a term",
                     "bangla": "NFC substring on en, bn and bl (as in the scan of 28 Sep 2026); false positives inside longer words are possible and are listed"},
        "run_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
json.dump({"meta": meta, "n_hits": len(hits), "hits": hits}, open(OUT / "PLACE-SCAN.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
L = ["# N1 — place and country names outside Bangladesh in the frozen query file (read-only text check; nothing changes)", "",
     f"queries.csv sha256 {Q_SHA}; 750 texts (en, bn, bl of 250 queries); {len(LATIN)} Latin-script terms (exact and stem matching) and {len(BANGLA)} Bangla-script terms (substring); run {meta['run_utc']}.", "",
     f"## Hits: {len(hits)}", ""]
if hits:
    L += ["| query | arm | term | kind | matched | text |", "|---|---|---|---|---|---|"]
    for h in hits:
        L.append(f"| {h['query_id']} | {h['arm']} | {h['term']} | {h['kind']} | {h['matched']} | {h['text'].replace('|', '/')} |")
else:
    L.append("None.")
L += ["", "## Latin-script terms", "", ", ".join(LATIN), "", "## Bangla-script terms", "", ", ".join(BANGLA)]
(OUT / "PLACE-SCAN.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("hits:", len(hits))
for h in hits:
    print(h["query_id"], h["arm"], h["term"], h["kind"], h["matched"], "|", h["text"])
print("written:", OUT / "PLACE-SCAN.json", OUT / "PLACE-SCAN.md")
