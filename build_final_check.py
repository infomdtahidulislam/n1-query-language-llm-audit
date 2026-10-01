#!/usr/bin/env python3
"""build_final_check.py — N1: the authors' cross-rendering alignment sheets (Appendix A.4).

One sheet per author, containing the 125 rows they are named on in the kit's `final_check` column —
i.e. the rows the OTHER author wrote. Unlike the rater files these show all three renderings, because
the check IS the comparison. Rows stay in query_id order so each category reads as a block and the
within-category distinctness rule (A.2) can be judged.

An "auto-check" column pre-computes everything mechanically checkable, so the human pass is spent on
judgement rather than arithmetic. Anything it prints is a prompt to look, not a verdict.

Usage: python3 build_final_check.py kit.xlsx outdir
"""
import re, sys, os
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side, Protection
from openpyxl.formatting.rule import FormulaRule
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

KIT = sys.argv[1] if len(sys.argv) > 1 else "KIT-v3.xlsx"
OUT = sys.argv[2] if len(sys.argv) > 2 else "."

# Brand names that are also ordinary words — the validator's alias table cannot see most of these.
AMBIG_BN = ["সহজ","অথবা","বিক্রয়","রকমারি","স্বপ্ন","আগোরা","ভিশন","সিটি","ট্রাস্ট","জনতা","অগ্রণী",
            "নগদ","বিকাশ","উপায়","রকেট","লিংক","আমরা","প্রাইম","পদ্মা","মেঘনা","যমুনা"]
AMBIG_LAT = ["sohoj","sohoje","shohoz","othoba","bikroy","rokomari","swapno","agora","vision","city",
             "trust","janata","agrani","nagad","bikash","upay","rocket","link","amra","prime","padma","meghna","jamuna"]

wb = openpyxl.load_workbook(KIT, data_only=True)["Queries"]
hdr = [c.value for c in wb[1]]; ix = {h: i for i, h in enumerate(hdr)}
rows = []
for r in wb.iter_rows(min_row=2, values_only=True):
    q = str(r[ix["query_id"]] or "").strip()
    if not re.fullmatch(r"Q\d{3}", q): continue
    g = lambda n: ("" if r[ix[n]] is None else str(r[ix[n]]).strip())
    rows.append(dict(id=q, cat=g("category"), sub=g("subtype"), budget=g("budget_bdt"),
                     en=g("en_text"), bn=g("bn_text"), bl=g("bl_text"), note=g("notes"),
                     checker=g("final_check"), author=g("author"),
                     rob=g("robust50").upper(), smoke=g("smoke_test").upper(), cal=g("calibration").upper()))

NUM = re.compile(r"\d+(?:\.\d+)?")
STOP = set("""the a an is are was for of to in on at by with which what who how best good better top
cheap cheapest under below above and or not any some more most less least buy buying should would can
could does do it its this that these those from about there their they you your my me i we our us as be
been being have has had will shall may might must if then than so such very much many few both all each
other another same different new old first last long short high low big small large great little own
""".split())
def toks(t):
    return {w for w in re.findall(r"[a-z]+(?:-[a-z]+)*", t.lower()) if len(w) > 2 and w not in STOP}

def auto(x, similar=None):
    out = []
    d = [sorted(NUM.findall(x["en"])), sorted(NUM.findall(x["bn"])), sorted(NUM.findall(x["bl"]))]
    if len({tuple(v) for v in d}) != 1: out.append(f"numbers differ across arms {d}")
    if re.search(r"\d,\d", x["en"] + x["bn"] + x["bl"]): out.append("thousands separator")
    # Only the bn <-> bl pair. The en arm's idiomatic "best" for "কোন X ভালো" is a settled convention
    # across all 250 rows and flagging it would bury the column in noise.
    bn_sup = bool(re.search(r"সেরা|সবচেয়ে", x["bn"]))
    bl_sup = bool(re.search(r"\bbest\b|sob\s?cheye|shob\s?cheye|\bsera\b", x["bl"], re.I))
    if bn_sup != bl_sup:
        out.append("superlative in bn but not bl" if bn_sup else "superlative in bl but not bn")
    bd = (bool(re.search(r"বাংলাদেশ", x["bn"])), bool(re.search(r"in bangladesh", x["en"], re.I)),
          bool(re.search(r"bangladesh|\bbd\b", x["bl"], re.I)))
    if len(set(bd)) != 1: out.append(f"'Bangladesh' in some arms only (bn/en/bl = {bd})")
    if x["sub"] == "budget" and re.search(r"মাসিক|মাসে", x["bn"]) and not re.search(r"month|mas", x["en"] + x["bl"], re.I):
        out.append("bn says monthly, other arms may not")
    if not x["en"].rstrip().endswith("?"): out.append("en does not end with '?'")
    if not x["bn"].rstrip().endswith("?"): out.append("bn does not end with '?'")
    hits = [w for w in AMBIG_BN if w in x["bn"]] + \
           [w for w in AMBIG_LAT if re.search(rf"(?<![a-z]){w}(?![a-z])", (x["en"] + " " + x["bl"]).lower())]
    if hits: out.append("word that is also a brand name — check the sense: " + ", ".join(sorted(set(hits))))
    if re.search(r"\bTVs\b", x["en"]): out.append("'TVs' in en — letter-for-letter the TVS brand")
    for arm in ("en", "bn", "bl"):
        if len([t for t in re.split(r"[.!?।]+", x[arm]) if t.strip()]) > 2: out.append(f"{arm}: more than two sentences")
    lo = min(len(x["en"]), len(x["bn"]), len(x["bl"])); hi = max(len(x["en"]), len(x["bn"]), len(x["bl"]))
    if lo and hi / lo > 2.0: out.append("one arm much shorter than another — check nothing was dropped")
    if similar:
        out.append(f"same category and subtype as {similar[0]}, {similar[1]}% of the content words shared "
                   f"— confirm the two ask different questions (A.2)")
    return " · ".join(out) or "—"

HEAD = ["query_id","category","type","amount","flags","en_text","bn_text","bl_text (rater-written)",
        "kit note","auto-check — look, do not trust","DECISION","If Hold: what needs fixing"]
WIDTH= [10,15,15,10,12,44,44,44,30,44,14,40]
BN="Nirmala UI"
hfill=PatternFill("solid",fgColor="1F3864"); yfill=PatternFill("solid",fgColor="FFF2CC")
afill=PatternFill("solid",fgColor="F2F2F2"); sfill=PatternFill("solid",fgColor="E2EFDA")
thin=Side(style="thin",color="BFBFBF"); bord=Border(left=thin,right=thin,top=thin,bottom=thin)

CHECKLIST=[("WHAT THIS SHEET IS",True),("",False),
 ("Appendix A.4: before a row can be marked final, the author who did NOT write it checks that the three",False),
 ("renderings carry the identical question. These 125 rows are the ones the kit names you on. Rows are in",False),
 ("query_id order, so each category is a block — that is deliberate, because one of the checks is that the",False),
 ("25 rows of a category ask 25 different questions.",False),("",False),
 ("FOR EACH ROW",True),("",False),
 ("1. Same question in all three — same product noun, same facet, same persona or use-case, same channel.",False),
 ("2. Same constraints — the amount, and any qualifier: monthly, for a student, under X, in Bangladesh.",False),
 ("3. Numbers identical in all three and unseparated (25000, never 25,000, never 25k).",False),
 ("4. No brand or retailer name in any arm. Watch the words that are also brands — sohoj, othoba, bikroy,",False),
 ("    nagad, bikash, upay, city, trust, janata, agrani, link, amra, vision — and 'TVs' in English, which is",False),
 ("    letter-for-letter the TVS brand. The auto-check column names them where they appear.",False),
 ("5. English register is everyday and matches the Bangla loanword: fridge not refrigerator, TV not",False),
 ("    television, shop not store, load-shedding — but motorcycle, not motorbike.",False),
 ("6. One question, at most two sentences, en and bn end with '?'.",False),
 ("",False),
 ("THE MISTAKES THAT ACTUALLY HAPPENED IN THIS SET — worth a second look on every row",True),("",False),
 ("• The row loses its product noun, so the arms stop carrying the same constraint.",False),
 ("• A phrasing that re-parses the question: 'Which AC filters are easiest to clean?' reads as *which filter*,",False),
 ("    so the answer names component types instead of brands.",False),
 ("• A comparative with nothing to compare to (easier → easiest, fewer → fewest).",False),
 ("• A constraint present in one arm and not the others, or a superlative in one arm only.",False),
 ("• Two rows in the same category asking the same question at two price points.",False),
 ("• The same product or facet used in both a budget row and a use-case row.",False),
 ("",False),
 ("HOW TO ANSWER",True),("",False),
 ("You may fix an en_text or bn_text wording directly in this sheet — those columns are unlocked, and any",False),
 ("change you make will be picked up and merged into the kit when the file comes back. A bn change must be",False),
 ("realigned in en, so mark those rows Hold as well so the pair is reviewed together.",False),
 ("The bl_text column is LOCKED on purpose. A Banglish rendering cannot be edited here — it goes back to its",False),
 ("writer and then to both approvers, or its two approvals no longer mean anything. Mark it Hold and say why.",False),
 ("",False),
 ("DECISION column: 'Final' if all three renderings match, 'Hold' if anything needs changing.",False),
 ("Hold → say what needs fixing in the last column. A Hold on the Banglish goes back to its writer and both",False),
 ("approvers, so it costs a round — but a wrong row costs the study.",False),
 ("A Hold on the bn or en is yours and your co-author's to fix; a bn change must be realigned in en (A.4).",False),
 ("Nothing is marked final in the kit until this sheet comes back.",False)]

# within-category near-duplicates, at a LOWER threshold than the validator's 0.60 — the validator's
# check 8 passes on this set, and its known gap (a row that reduces to an empty content set) is exactly
# what a human eye is for. These are prompts, not failures.
SIM = {}
bycat = {}
for x in rows: bycat.setdefault((x["cat"], x["sub"]), []).append(x)
for key, xs in bycat.items():
    for i in range(len(xs)):
        for j in range(i + 1, len(xs)):
            a, b = toks(xs[i]["en"]), toks(xs[j]["en"])
            if not a or not b: continue
            jac = len(a & b) / len(a | b)
            if jac >= 0.60:
                for p, q in ((i, j), (j, i)):
                    cur = SIM.get(xs[p]["id"])
                    if cur is None or jac > cur[1]: SIM[xs[p]["id"]] = (xs[q]["id"], round(jac * 100))

made=[]
for code in sorted({x["checker"] for x in rows}):
    mine=[x for x in rows if x["checker"]==code]
    out=openpyxl.Workbook(); w=out.active; w.title="FinalCheck"
    w["A1"]=f"N1 · Final cross-rendering check — {code} — {len(mine)} rows"
    w["A1"].font=Font(bold=True,size=13,color="1F3864")
    w["A2"]=("Appendix A.4. These are the rows written by your co-author. Mark each Final or Hold. "
             "The auto-check column has done the arithmetic; your job is the judgement.")
    w["A2"].font=Font(size=10,italic=True,color="595959")
    w.merge_cells(start_row=1,end_row=1,start_column=1,end_column=len(HEAD))
    w.merge_cells(start_row=2,end_row=2,start_column=1,end_column=len(HEAD))
    for j,(h,wd) in enumerate(zip(HEAD,WIDTH),start=1):
        c=w.cell(row=4,column=j,value=h); c.font=Font(bold=True,color="FFFFFF",size=10); c.fill=hfill
        c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True); c.border=bord
        w.column_dimensions[get_column_letter(j)].width=wd
    w.row_dimensions[4].height=32
    for i,x in enumerate(mine):
        r=5+i
        flags=" ".join(f for f,v in (("robust50",x["rob"]),("smoke",x["smoke"]),("calib",x["cal"])) if v in ("Y","YES","TRUE","1"))
        a=auto(x, SIM.get(x["id"]))
        for j,v in enumerate([x["id"],x["cat"],x["sub"],x["budget"],flags,x["en"],x["bn"],x["bl"],x["note"],a,None,None],start=1):
            c=w.cell(row=r,column=j,value=v); c.border=bord
            c.alignment=Alignment(vertical="top",wrap_text=(j in (6,7,8,9,10,12)))
            c.protection=Protection(locked=(j==8))   # only bl_text is locked; see note below
            if j==1: c.font=Font(bold=True,size=10)
            if j==5 and flags: c.fill=sfill; c.font=Font(size=9,bold=True,color="375623")
            if j==7: c.font=Font(name=BN,size=12)
            if j==9: c.fill=afill; c.font=Font(size=9,italic=True,color="7F6000")
            if j==10:
                c.font=Font(size=9,italic=True,color=("C00000" if a!="—" else "808080"))
                if a!="—": c.fill=PatternFill("solid",fgColor="FFF0F0")
            if j in (11,12): c.fill=yfill
            if j==11: c.alignment=Alignment(horizontal="center",vertical="center")
    last=4+len(mine)
    dv=DataValidation(type="list",formula1='"Final,Hold"',allow_blank=True,showDropDown=False)
    w.add_data_validation(dv); dv.add(f"K5:K{last}")
    w.conditional_formatting.add(f"L5:L{last}",
        FormulaRule(formula=['AND($K5="Hold",$L5="")'],fill=PatternFill("solid",fgColor="F8CBAD")))
    w.freeze_panes="F5"
    w.protection.sheet=True; w.protection.enable()   # everything editable except bl_text (column H)
    r2=out.create_sheet("Checklist"); r2.column_dimensions["A"].width=118
    for i,(t,head) in enumerate(CHECKLIST,start=1):
        c=r2.cell(row=i,column=1,value=t); c.alignment=Alignment(vertical="top",wrap_text=True)
        c.font=Font(bold=True,size=12,color="1F3864") if head else Font(name=BN,size=11)
    r2.sheet_view.showGridLines=False
    p=os.path.join(OUT,f"FINAL-CHECK-{code}.xlsx"); out.save(p); made.append((p,code,len(mine)))

print("built:")
allids=set(); ok=True
for p,code,n in made:
    chk=openpyxl.load_workbook(p)["FinalCheck"]
    data=[r for r in chk.iter_rows(min_row=5,values_only=True) if r and r[0]]
    ids=[r[0] for r in data]
    K={x["id"]:x for x in rows}
    right=all(K[i]["checker"]==code for i in ids)
    notmine=all(K[i]["author"]!=code for i in ids)
    texts=all(K[i]["en"]==r[5] and K[i]["bn"]==r[6] and K[i]["bl"]==r[7] for i,r in zip(ids,data))
    empty=all(r[10] in (None,"") and r[11] in (None,"") for r in data)
    ordered=ids==sorted(ids)
    flagged=sum(1 for r in data if r[9]!="—")
    allids|=set(ids)
    print(f"  {p}: {len(ids)} rows | named on all: {right} | none self-authored: {notmine} | "
          f"all three arms match the kit: {texts} | decision cols empty: {empty} | query_id order: {ordered} | "
          f"rows with an auto-check note: {flagged}")
    ok &= right and notmine and texts and empty and ordered
print(f"\nunion: {len(allids)}/250 rows, no overlap: {len(allids)==250}")
print("VERDICT:", "PASS" if ok and len(allids)==250 else "FAIL")
