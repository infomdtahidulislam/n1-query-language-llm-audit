#!/usr/bin/env python3
"""validate_queries.py — QC for QUERY-AUTHORING-KIT.xlsx (N1 study, Appendix A rules).

Usage:  python validate_queries.py [path/to/QUERY-AUTHORING-KIT.xlsx]
Needs:  pip install openpyxl

Checks (each reported PASS / WARN / FAIL):
  1. ids Q001..Q250 present once, 25 rows per category, 10 categories
  2. subtype quotas per category: open 10 · budget 8 · usecase 4 · channel 3   (WARN if off)
  3. no brand or retailer name from BrandAliases-Starter appears in any rendering
     (suffix-aware: catches ওয়ালটনের / waltoner; aliases that are also ordinary words —
      general, vision, hero, upay, nagad ... — are WARN-with-context, not FAIL)
  4. bn_text is Bangla script only (Latin letters forbidden); Western digits in every arm (০-৯ forbidden)
  5. numbers identical across en / bn / bl renderings of a row
  5b. budget rows: budget_bdt equals the amount written in every rendering
  5c. no thousands separator in any amount (A.6: 25000, never 25,000) — check 5 is blind to this;
      the EX template row is scanned here too, since it is the format the authors and raters copy
  6. <= 2 sentences per rendering
  7. status=final only if bl_approve_1 and bl_approve_2 are filled and differ from bl_author
     (if optional approve_1_ok / approve_2_ok columns exist, also both = Y; the team may track approvals off-sheet)
  7b. pre-assigned kit: every row's {bl_author, bl_approve_1, bl_approve_2} == {R1,R2,R3}; rotation 9/8/8 per
     category (WARN if off); final_check author differs from the writing author
  8. near-duplicate questions within a category (content-token Jaccard on en_text; function words and
     category-frequent words stripped; the sanctioned open-facet + budget pairing is exempt)
  9. flags: calibration = 6, smoke_test = 10 (1 per category), robust50 = 50 (5 per category)
Rows whose en/bn/bl are all empty are treated as "not yet written" and skipped in 3-8.
"""
import re, sys
from collections import Counter, defaultdict

# This script prints Bangla (the check-4 label carries ০-৯, and any brand-alias hit is quoted with its
# Bangla context). When it is run through a PIPE on Windows, Python encodes stdout with the locale code
# page — cp1252 — and a UnicodeEncodeError kills the run, which is how n1_pipeline.py's preflight saw
# "validate_queries.py exits 0 with 0 FAIL" FAIL on a workbook that is actually clean. Force UTF-8 only
# when stdout is not a console, so interactive output on Windows is left exactly as it was.
if not sys.stdout.isatty():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
try:
    import openpyxl
except ImportError:
    sys.exit("pip install openpyxl")

PATH = sys.argv[1] if len(sys.argv) > 1 else "QUERY-AUTHORING-KIT.xlsx"
QUOTA = {"open": 10, "budget": 8, "usecase": 4, "channel": 3}   # kit labels use-case / purchase-channel are normalized
BANGLA = re.compile(r"[ঀ-৿]")
LATIN  = re.compile(r"[A-Za-z]")
NUM    = re.compile(r"\d[\d,\.]*")
SENT   = re.compile(r"[.!?।]+")

wb = openpyxl.load_workbook(PATH, data_only=True)
ws = wb["Queries"]
hdr = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
col = {name: i for i, name in enumerate(hdr)}
need = ["query_id","category","subtype","en_text","bn_text","bl_text","bl_author","bl_approve_1","bl_approve_2","status"]
missing = [n for n in need if n not in col]
if missing:
    sys.exit(f"FAIL: Queries sheet missing columns {missing}")
opt = {n: col.get(n) for n in ["calibration","smoke_test","robust50","bl_translit","budget_bdt",
                                "approve_1_ok","approve_2_ok","bl_revisions","author","final_check"]}
PREASSIGNED = opt["author"] is not None                                            # kit v4+: codes are assignments
HAS_OK = opt["approve_1_ok"] is not None and opt["approve_2_ok"] is not None        # optional approval-flag columns

rows = []
for r in ws.iter_rows(min_row=2, values_only=True):
    if not r or not r[col["query_id"]]: continue
    qid = str(r[col["query_id"]]).strip()
    if not re.fullmatch(r"Q\d{3}", qid): continue          # skips the EXAMPLE row
    g = lambda n: (str(r[col[n]]).strip() if r[col[n]] is not None else "")
    go = lambda n: (str(r[opt[n]]).strip() if opt[n] is not None and r[opt[n]] is not None else "")
    sub = g("subtype").lower().replace("purchase-channel", "channel").replace("use-case", "usecase").replace("use case", "usecase")
    rows.append(dict(id=qid, cat=g("category"), sub=sub, en=g("en_text"), bn=g("bn_text"),
                     bl=g("bl_text"), au=g("bl_author"), a1=g("bl_approve_1"), a2=g("bl_approve_2"),
                     st=g("status").lower(), cal=go("calibration").upper(), smoke=go("smoke_test").upper(),
                     rob=go("robust50").upper(), ok1=go("approve_1_ok").upper(), ok2=go("approve_2_ok").upper(),
                     rev=go("bl_revisions"), author=go("author"), checker=go("final_check")))

report = []
def out(level, msg): report.append((level, msg))

# 1. ids and category counts
ids = [x["id"] for x in rows]
dup = [k for k, v in Counter(ids).items() if v > 1]
expected = {f"Q{i:03d}" for i in range(1, 251)}
if set(ids) == expected and not dup: out("PASS", "ids Q001–Q250 present exactly once")
else: out("FAIL", f"ids: {len(ids)} rows, missing {len(expected - set(ids))}, duplicates {dup[:5]}")
cats = Counter(x["cat"] for x in rows)
bad = {c: n for c, n in cats.items() if n != 25}
out("PASS" if len(cats) == 10 and not bad else "FAIL", f"categories: {len(cats)} × 25 rows" + (f" — off: {bad}" if bad else ""))

# 2. subtype quotas
for c in sorted(cats):
    sc = Counter(x["sub"] for x in rows if x["cat"] == c)
    off = {s: (sc.get(s, 0), q) for s, q in QUOTA.items() if sc.get(s, 0) != q}
    unknown = [s for s in sc if s not in QUOTA]
    if off or unknown: out("WARN", f"{c}: subtype quota off {off} unknown={unknown}")
if not any(l == "WARN" and "subtype quota" in m for l, m in report): out("PASS", "subtype quotas 10/8/4/3 in every category")

written = [x for x in rows if x["en"] or x["bn"] or x["bl"]]
out("INFO", f"{len(written)}/250 rows have at least one rendering written")

# 3. brand / retailer leakage — two tiers.
#    Tier FAIL: aliases that are only ever brand names (walton, daraz, bkash, স্যামসাং ...).
#    Tier WARN: aliases that are also ordinary words in English, Bangla or Banglish
#    (general, vision, hero, runner, rocket, apple, singer, symphony, minister, marcel;
#     উপায়/upay = "way", নগদ/nagad = "cash", বিকাশ/bikash = "development", রবি/robi = "sun",
#     মিডিয়া = "media", যমুনা = the river ...). These are shown WITH CONTEXT for a human decision,
#    never auto-failed. Extend AMBIGUOUS when the alias table grows.
#    Matching is suffix-aware: Bangla brands take case endings (ওয়ালটনের, দারাজে) and Banglish
#    attaches them in Latin (waltoner, bkashe, darazer), so a bare word-boundary test would miss them.
AMBIGUOUS = {"general", "vision", "hero", "runner", "rocket", "apple", "singer", "symphony", "minister",
             "marcel", "upay", "nagad", "bikash", "robi", "media", "star",
             "উপায়", "নগদ", "বিকাশ", "রবি", "মিডিয়া", "যমুনা", "জেনারেল", "ভিশন", "হিরো", "রানার", "রকেট",
             "সিঙ্গার", "সিম্ফনি", "মিনিস্টার"}
BN_LETTER = "অ-ঔক-হঽৎড়-ঢ়য়-ৡ"      # independent vowels + consonants
BN_SIGN   = "়া-ৄে-ৈো-্ৗৢ-ৣ"       # matras, virama, nukta
BL_SUFFIX = r"(?:er|r|e|te|ke|ta|ti|tar|gulo|guli|ra|o)?"                             # Banglish case endings
# Bangla case endings: matra-initial (ে, ের, ে-র ...) or consonant-initial (র, কে, টা, টি, গুলো, রা, ও ...)
# Matra-initial endings are an explicit list (ে, ের, েও, েতে, েতেই, েই, েরও, েরই) — an open-ended
# "matra then any letters" branch swallowed every word that merely STARTS with an alias (ডেল → ডেলিভারির).
BN_SUFFIX = (r"(?:ে(?:র|ও|তে|তেই|ই|রও|রই)?"
             r"|(?:র|রও|কে|তে|তেই|দের|টা|টি|টার|টির|টাই|গুলো|গুলি|গুলোর|গুলোতে|রা|ও|খানা|য়|য়|য়ে|য়ে|য়ের|য়ের))?")
def alias_regex(a):
    if BANGLA.search(a):   # Bangla alias: nothing word-like before it; an optional case ending after it; then a boundary
        return re.compile(rf"(?<![{BN_LETTER}{BN_SIGN}]){re.escape(a)}{BN_SUFFIX}(?![{BN_LETTER}{BN_SIGN}])")
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(a)}{BL_SUFFIX}(?![A-Za-z0-9])", re.IGNORECASE)
brands = {}
if "BrandAliases-Starter" in wb.sheetnames:
    for r in wb["BrandAliases-Starter"].iter_rows(min_row=2, values_only=True):
        if not r or not r[0] or "STARTER" in str(r[0]).upper(): continue
        for cell in (r[1], r[3]):
            if cell:
                for a in str(cell).split("|"):
                    a = a.strip()
                    if len(a) >= 3: brands[a.lower()] = alias_regex(a.lower())
leaks, maybe = [], []
for x in written:
    for arm, text in (("en", x["en"]), ("bn", x["bn"]), ("bl", x["bl"])):
        if not text: continue
        for b, rx in brands.items():
            m = rx.search(text)
            if not m: continue
            ctx = text[max(0, m.start() - 18): m.end() + 18].replace("\n", " ")
            (maybe if b in AMBIGUOUS else leaks).append((x["id"], arm, b, f"…{ctx}…"))
out("PASS" if not leaks else "FAIL", f"brand/retailer names in queries: {len(leaks)} hits" + (f" e.g. {leaks[:3]}" if leaks else ""))
if maybe:
    out("WARN", f"possible brand words that are also ordinary words — check by eye, rewrite only if it names the brand: {len(maybe)} hits")
    for hit in maybe[:12]: out("WARN", f"    {hit[0]} [{hit[1]}] '{hit[2]}' {hit[3]}")

# 4. bn script purity
impure = [x["id"] for x in written if x["bn"] and LATIN.search(x["bn"])]
out("PASS" if not impure else "FAIL", f"bn_text Latin-letter contamination: {len(impure)}" + (f" {impure[:6]}" if impure else ""))
nobn = [x["id"] for x in written if x["bn"] and not BANGLA.search(x["bn"])]
if nobn: out("FAIL", f"bn_text contains no Bangla characters: {nobn[:6]}")
BN_DIGIT = re.compile(r"[০-৯]")
bndig = [x["id"] for x in written if any(BN_DIGIT.search(t) for t in (x["en"], x["bn"], x["bl"]))]
out("PASS" if not bndig else "FAIL", f"Bangla digits (০-৯) used — rule is Western digits in every arm: {len(bndig)}" + (f" {bndig[:6]}" if bndig else ""))

# 5. numbers identical across arms
def nums(s): return sorted(n.replace(",", "").rstrip(".") for n in NUM.findall(s))
numbad = [x["id"] for x in written if x["en"] and x["bn"] and x["bl"] and not (nums(x["en"]) == nums(x["bn"]) == nums(x["bl"]))]
out("PASS" if not numbad else "FAIL", f"numbers differ across renderings: {len(numbad)}" + (f" {numbad[:6]}" if numbad else ""))

# 5b. budget rows: the budget_bdt column must equal the amount written in every rendering
#     (catches a text edited to 8,000 while the column still says 6000 — the column feeds the analysis).
if opt["budget_bdt"] is not None:
    bcol = opt["budget_bdt"]
    budget_of = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r and r[col["query_id"]] and re.fullmatch(r"Q\d{3}", str(r[col["query_id"]]).strip()):
            v = r[bcol]
            budget_of[str(r[col["query_id"]]).strip()] = re.sub(r"[^\d]", "", str(v)) if v is not None else ""
    bmis = []
    for x in written:
        if x["sub"] != "budget": continue
        b = budget_of.get(x["id"], "")
        texts = [t for t in (x["en"], x["bn"], x["bl"]) if t]
        if not b or any(b not in nums(t) for t in texts):
            bmis.append((x["id"], b or "blank", [nums(t) for t in texts]))
    out("PASS" if not bmis else "FAIL", f"budget_bdt equals the amount in every written rendering: {len(bmis)} off" + (f" e.g. {bmis[:3]}" if bmis else ""))

# 5c. thousands separators. Appendix A.6 (v0.19): amounts are written UNSEPARATED — 25000, never 25,000 —
#     so that the three arms carry byte-identical digits. Check 5 cannot see this: nums() strips commas before
#     comparing, so a separator added in one arm passes silently. A decimal point inside a measurement
#     (1.5 ton) is not a separator and is left alone; only a comma with digits on both sides is flagged.
SEPNUM = re.compile(r"\d,\d")
#     The EXAMPLE row (query_id EX) is skipped by every other check — it is not data — but it is the row the
#     authors and raters copy the format from, so a separator there teaches the wrong convention to three
#     Banglish writers at once. It is scanned here, and only here.
example = []
for _r in ws.iter_rows(min_row=2, values_only=True):
    if _r and str(_r[col["query_id"]] or "").strip().upper() == "EX":
        example = [{"id": "EX(template)",
                    "en": str(_r[col["en_text"]] or ""),
                    "bn": str(_r[col["bn_text"]] or ""),
                    "bl": str(_r[col["bl_text"]] or "")}]
        break
sep = [(x["id"], arm, t[max(0, m.start() - 12): m.end() + 12])
       for x in written + example for arm, t in (("en", x["en"]), ("bn", x["bn"]), ("bl", x["bl"]))
       if t for m in [SEPNUM.search(t)] if m]
out("PASS" if not sep else "FAIL",
    f"thousands separators in amounts (A.6 says unseparated): {len(sep)}" + (f" e.g. {sep[:4]}" if sep else ""))

# 6. sentence count
long = [x["id"] for x in written for t in (x["en"], x["bn"], x["bl"]) if t and len([s for s in SENT.split(t) if s.strip()]) > 2]
out("PASS" if not long else "WARN", f"renderings with >2 sentences: {len(set(long))}" + (f" {sorted(set(long))[:6]}" if long else ""))

# 7. approvals before final. In the pre-assigned kit (approve_1_ok / approve_2_ok columns present) the rater
#    codes are assignments, so the approval ACT is the ok flag: final needs both flags = Y plus 3 distinct codes.
def approved(x):
    codes_ok = x["a1"] and x["a2"] and x["au"] and len({x["au"], x["a1"], x["a2"]}) == 3
    return codes_ok and (not HAS_OK or (x["ok1"] == "Y" and x["ok2"] == "Y"))
badfinal = [x["id"] for x in rows if x["st"] == "final" and not approved(x)]
out("PASS" if not badfinal else "FAIL", f"final rows lacking two distinct non-author approvals" + (" (both ok flags = Y)" if HAS_OK else "") + f": {len(badfinal)}" + (f" {badfinal[:6]}" if badfinal else ""))
if HAS_OK:
    badrev = [x["id"] for x in rows if x["rev"] and not re.fullmatch(r"\d+", x["rev"])]
    if badrev: out("FAIL", f"bl_revisions must be a whole number: {badrev[:6]}")
    early = [x["id"] for x in rows if (x["ok1"] == "Y" or x["ok2"] == "Y") and not x["bl"]]
    if early: out("WARN", f"approval flag set on rows with no bl_text yet: {early[:6]}")

# 7b. assignment integrity (prereg A.5: writer + two other raters, rotation balanced within each category)
if PREASSIGNED:
    RATERS = {"R1", "R2", "R3"}
    badset = [x["id"] for x in rows if {x["au"], x["a1"], x["a2"]} != RATERS]
    out("PASS" if not badset else "FAIL", f"rater assignment: every row has writer + two distinct approvers covering R1/R2/R3: {len(badset)} off" + (f" {badset[:6]}" if badset else ""))
    unbalanced = []
    for c in sorted(cats):
        wc = Counter(x["au"] for x in rows if x["cat"] == c)
        if any(not (8 <= wc.get(r_, 0) <= 9) for r_ in RATERS): unbalanced.append((c, dict(wc)))
    out("PASS" if not unbalanced else "WARN", "bl_author rotation 9/8/8 in every category" + (f" — off: {unbalanced[:3]}" if unbalanced else ""))
    tot = Counter(x["au"] for x in rows)
    out("INFO", "bl_author load: " + ", ".join(f"{k}={v}" for k, v in sorted(tot.items())))
    if opt["author"] is not None and opt["final_check"] is not None:
        same = [x["id"] for x in rows if x["author"] and x["author"] == x["checker"]]
        out("PASS" if not same else "FAIL", f"final_check author differs from the writing author on every row: {len(same)} same" + (f" {same[:6]}" if same else ""))

# 8. near-duplicates within category — Jaccard >= 0.6 on CONTENT tokens of en_text.
#    Function words and category-frequent words are stripped first (which / good / under / taka / brand and the
#    category's head noun): six-word buyer questions otherwise share {which, good, under, taka} and every
#    formulaic budget pair lights up. Two content sets are compared only when both are non-empty.
#    Exempt pairing: an OPEN facet row with a BUDGET row carrying the same facet — the one repetition the
#    authoring rules sanction (FACET-MENU: "a budget row can carry a facet"). Every other subtype
#    combination is compared, so a facet parked in a use-case row, or the same question at two prices, still flags.
STOP = {"which","what","whats","that","this","these","those","there","their","them","they","with","from","where",
        "when","should","would","could","will","does","have","been","being","about","some","than","also","into",
        "over","after","before","more","less","much","many","very","just","like","only","good","best","better",
        "most","under","within","below","taka","price","budget","brand","brands","company","companies","option",
        "options","choose","pick","recommend","recommended","suggest","worth","want","need","looking","someone",
        "anyone","people","person","right","kind","type","sort","thing","things","ones","buying","purchase",
        "purchasing","going","getting","take","give","gives","makes","make","really","actually","overall",
        "the","and","are","can","you","its","has","how","who","not","out","all","one","any","our","was","but",
        "off","per","via","too","own","lot","way","use","get","buy","got","may","did","let","see","for","that",
        "bangladesh"}   # every query is about Bangladesh; "in Bangladesh" never distinguishes two rows
def toks(s): return set(w for w in re.findall(r"[a-z]+(?:-[a-z]+)*", s.lower()) if len(w) > 2 and w not in STOP)   # keeps low-cc, after-sales, second-hand
dups = []
bycat = defaultdict(list)
for x in written:
    if x["en"]: bycat[x["cat"]].append(x)
for c, xs in bycat.items():
    n = len(xs)
    df = Counter(t for x in xs for t in toks(x["en"]))
    catstop = {t for t, k in df.items() if n >= 10 and k >= 0.25 * n}    # the category's own head-noun words (phone, banking, internet ...)
    content = {x["id"]: toks(x["en"]) - catstop for x in xs}
    for i in range(n):
        for j in range(i + 1, n):
            if {xs[i]["sub"], xs[j]["sub"]} == {"open", "budget"}: continue
            a, b = content[xs[i]["id"]], content[xs[j]["id"]]
            if not a and not b:                                   # nothing but the template survives stripping
                if xs[i]["sub"] == xs[j]["sub"]:                  # same subtype → same question, only numbers differ
                    dups.append((xs[i]["id"], xs[j]["id"], "(identical after stripping)"))
            elif a and b and len(a & b) / len(a | b) >= 0.6:
                dups.append((xs[i]["id"], xs[j]["id"], "+".join(sorted(a & b))))
out("PASS" if not dups else "WARN", f"near-duplicate en questions within a category (content tokens, open+budget pairs exempt): {len(dups)}" + (f" e.g. {dups[:4]}" if dups else ""))
if dups:
    for d in dups[4:12]: out("WARN", f"    {d[0]} ~ {d[1]}  shared: {d[2]}")

# 9. flags
cal = sum(1 for x in rows if x["cal"] == "YES")
out("PASS" if cal == 6 else "WARN", f"calibration flags: {cal} (need 6)")
if opt["smoke_test"] is not None:
    sm = Counter(x["cat"] for x in rows if x["smoke"] == "YES")
    out("PASS" if sum(sm.values()) == 10 and all(v == 1 for v in sm.values()) and len(sm) == 10 else "WARN", f"smoke_test flags: {sum(sm.values())} (need 10, one per category)")
else: out("WARN", "no smoke_test column yet — add it (10 rows, 1 per category)")
if opt["robust50"] is not None:
    rb = Counter(x["cat"] for x in rows if x["rob"] == "YES")
    out("PASS" if sum(rb.values()) == 50 and all(v == 5 for v in rb.values()) and len(rb) == 10 else "WARN", f"robust50 flags: {sum(rb.values())} (need 50, five per category)")
else: out("WARN", "no robust50 column yet — add it (50 rows, 5 per category; drives the equivalence check and the transliteration arm)")
if opt["bl_translit"] is None: out("WARN", "no bl_translit column yet — add it (filled by script from bn_text for the robust50 rows only)")

width = max(len(m) for _, m in report)
print(f"\nvalidate_queries — {PATH}\n" + "-" * (width + 8))
for lvl, msg in report: print(f"[{lvl:4}] {msg}")
fails = sum(1 for l, _ in report if l == "FAIL")
print("-" * (width + 8) + f"\n{fails} FAIL · {sum(1 for l,_ in report if l=='WARN')} WARN")
sys.exit(1 if fails else 0)
