#!/usr/bin/env python3
"""build_equiv_verdict.py — N1: the authors' equivalence-verdict sheets (A.4b).

Judging equivalence means comparing a back-translation against en_text, so only the authors can do it.
Each author takes the tasks belonging to the rows the OTHER author wrote — the same split as the A.4
final_check column. 100 tasks, 50 each.

The 'register only?' column is computed, not judged: it names the wording differences a script can see,
so the author can tell at a glance whether a difference is the registered good/best convention or
something substantive. The verdict itself stays a human judgement on intent, constraints and numbers.

Usage: python3 build_equiv_verdict.py kit.xlsx outdir
"""
import re, sys, os
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side, Protection
from openpyxl.formatting.rule import FormulaRule
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

KIT = sys.argv[1] if len(sys.argv) > 1 else "KIT-v7.xlsx"
OUT = sys.argv[2] if len(sys.argv) > 2 else "."
NUM = re.compile(r"\d+(?:\.\d+)?")
SUP = {"best","most","fastest","cheapest","safest","longest","easiest","lowest","cheaper","better","top"}
SYN = [("phone","mobile"),("fridge","refrigerator"),("tv","television"),("shop","store"),("used","second hand"),
       ("under","within"),("monthly plan","per month"),("monthly plan","a month"),("costs","fee"),
       ("mid-size","medium size"),("skincare","skin care"),("e-commerce","ecommerce"),("brakes","brake")]
BRANDS=set("walton vision samsung daraz bkash nagad rocket upay lg sony sharp singer minister marcel konka bajaj "
           "tvs hero honda yamaha suzuki runner intel amd asus acer dell lenovo hp apple xiaomi realme oppo vivo "
           "grameenphone robi banglalink airtel teletalk brac dbbl".split())

wv = openpyxl.load_workbook(KIT, data_only=True)
eq, qs = wv["Equivalence"], wv["Queries"]
hdr=[c.value for c in qs[1]]; ix={h:i for i,h in enumerate(hdr)}
K={}
for r in qs.iter_rows(min_row=3, values_only=True):
    q=str(r[ix["query_id"]] or "").strip()
    if re.fullmatch(r"Q\d{3}",q):
        K[q]=dict(en=str(r[ix["en_text"]] or ""),cat=str(r[ix["category"]] or ""),sub=str(r[ix["subtype"]] or ""),
                  author=str(r[ix["author"]] or ""),checker=str(r[ix["final_check"]] or ""))
tasks=[]
for n,r in enumerate(eq.iter_rows(min_row=2,max_row=101,values_only=True),start=2):
    if not r[0]: continue
    tasks.append(dict(sheetrow=n,id=str(r[0]).strip(),arm=str(r[1]).strip(),src=str(r[2] or ""),
                      who=str(r[3] or "").strip(),bt=str(r[4] or "")))
assert len(tasks)==100 and all(t["bt"] for t in tasks)

def auto(t):
    en=K[t["id"]]["en"]; b=t["bt"]; out=[]
    if NUM.findall(en)!=NUM.findall(b): out.append(f"NUMBERS DIFFER — en {NUM.findall(en)} vs back-translation {NUM.findall(b)}")
    hit=[w for w in BRANDS if re.search(rf"(?<![a-z]){w}(?![a-z])",b.lower())]
    if hit: out.append("BRAND NAME in the back-translation: "+", ".join(hit))
    reg=[]
    if any(w in en.lower() for w in SUP) and not any(w in b.lower() for w in SUP):
        reg.append("superlative in en, none in the back-translation (the registered good/best convention, A.4)")
    for a,c in SYN:
        if a in en.lower() and c in b.lower(): reg.append(f"{a} → {c}")
    if reg: out.append("register/synonym only: " + "; ".join(reg))
    return " · ".join(out) or "no difference a script can see"

HEAD=["query_id","category","from","The rendering the rater saw","Their English back-translation",
      "Your en_text","register only? (computed)","EQUIVALENT","If No: what to fix"]
WIDTH=[10,15,10,42,42,42,48,14,38]
BN="Nirmala UI"
hfill=PatternFill("solid",fgColor="1F3864"); yfill=PatternFill("solid",fgColor="FFF2CC")
sfill=PatternFill("solid",fgColor="EAF1FB"); bfill=PatternFill("solid",fgColor="F2F7EC")
efill=PatternFill("solid",fgColor="FFF7E6"); afill=PatternFill("solid",fgColor="F2F2F2")
thin=Side(style="thin",color="BFBFBF"); bord=Border(left=thin,right=thin,top=thin,bottom=thin)

NOTE=[("WHAT YOU ARE DECIDING",True),("",False),
 ("For each row: does the back-translation preserve the intent, the constraints and all the numbers of your en_text?",False),
 ("Yes → EQUIVALENT = Yes. No → No, and say what needs fixing. That row then goes back for correction and is re-checked.",False),
 ("",False),
 ("THE CRITERION, AS REGISTERED IN A.4b — a closed list, so it is not decided case by case",True),("",False),
 ("A MISMATCH is: a number changed, dropped or added · a constraint dropped or added (price cap, persona,",False),
 ("use-case, purchase channel, named facet) · the product or category changed · the question became a different question.",False),
 ("",False),
 ("NOT a mismatch: wording, register and synonym differences that leave intent, constraints and numbers intact —",False),
 ("'good' against 'best', 'mobile' against 'phone', 'within' against 'under', 'second hand' against 'used',",False),
 ("'per month' against 'monthly plan'. The good/best gap in particular is a property of the en arm you registered:",False),
 ("A.4 fixes English at the colloquial register matching the Bangla, so কোন X ভালো is written \"What's the best X?\"",False),
 ("in en, while any faithful back-translation of the same Bangla gives \"which X is good\". Marking that as",False),
 ("non-equivalent would score your own registered style, not the renderings.",False),
 ("",False),
 ("The 'register only?' column has already found every wording difference a script can see. If it says",False),
 ("'register/synonym only' or 'no difference', the mechanical checks are clear and only your judgement of intent",False),
 ("and constraints is left. If it says NUMBERS DIFFER or BRAND NAME, look hard — those are mismatches by the list above.",False),
 ("",False),
 ("HOW THE SPLIT WORKS",True),("",False),
 ("You have the tasks belonging to the rows your co-author wrote — the same split as the final_check column.",False),
 ("Both renderings of a row (Bangla and Banglish) come to the same author, so you can see whether a problem is in",False),
 ("one rendering or in both.",False),
 ("",False),
 ("Save the file and send it back. Do not rename it, do not add, delete or re-order rows.",False)]

made=[]
for code in sorted({K[t["id"]]["checker"] for t in tasks}):
    mine=[t for t in tasks if K[t["id"]]["checker"]==code]
    mine.sort(key=lambda t:(t["id"],t["arm"]))
    out=openpyxl.Workbook(); w=out.active; w.title="Verdict"
    w["A1"]=f"N1 · Equivalence verdicts — {code} — {len(mine)} tasks ({len({t['id'] for t in mine})} rows × 2 renderings)"
    w["A1"].font=Font(bold=True,size=13,color="1F3864")
    w["A2"]=("Does each back-translation preserve the intent, constraints and numbers of your en_text? "
             "Read the 'Criterion' tab — the registered list of what is and is not a mismatch.")
    w["A2"].font=Font(size=10,italic=True,color="595959")
    w.merge_cells(start_row=1,end_row=1,start_column=1,end_column=len(HEAD))
    w.merge_cells(start_row=2,end_row=2,start_column=1,end_column=len(HEAD))
    for j,(hh,wd) in enumerate(zip(HEAD,WIDTH),start=1):
        c=w.cell(row=4,column=j,value=hh); c.font=Font(bold=True,color="FFFFFF",size=10); c.fill=hfill
        c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True); c.border=bord
        w.column_dimensions[get_column_letter(j)].width=wd
    w.row_dimensions[4].height=32
    for i,t in enumerate(mine):
        r=5+i; a=auto(t); k=K[t["id"]]
        for j,v in enumerate([t["id"],k["cat"],("Bangla" if t["arm"]=="bn" else "Banglish"),
                              t["src"],t["bt"],k["en"],a,None,None],start=1):
            c=w.cell(row=r,column=j,value=v); c.border=bord
            c.alignment=Alignment(vertical="top",wrap_text=(j in (4,5,6,7,9)))
            c.protection=Protection(locked=(j not in (8,9)))
            if j==1: c.font=Font(bold=True,size=10)
            if j==3: c.font=Font(size=9,bold=True,color=("1F4E79" if t["arm"]=="bn" else "375623"))
            if j==4:
                c.fill=(sfill if t["arm"]=="bn" else bfill)
                c.font=(Font(name=BN,size=12) if t["arm"]=="bn" else Font(size=11))
            if j==5: c.font=Font(size=11)
            if j==6: c.fill=efill; c.font=Font(size=11,italic=True)
            if j==7:
                bad=a.startswith("NUMBERS") or a.startswith("BRAND") or "NUMBERS DIFFER" in a or "BRAND NAME" in a
                c.fill=(PatternFill("solid",fgColor="FFD9D9") if bad else afill)
                c.font=Font(size=9,italic=True,color=("C00000" if bad else "808080"))
            if j in (8,9): c.fill=yfill
            if j==8: c.alignment=Alignment(horizontal="center",vertical="center")
    last=4+len(mine)
    dv=DataValidation(type="list",formula1='"Yes,No"',allow_blank=True,showDropDown=False)
    w.add_data_validation(dv); dv.add(f"H5:H{last}")
    w.conditional_formatting.add(f"I5:I{last}",
        FormulaRule(formula=['AND($H5="No",$I5="")'],fill=PatternFill("solid",fgColor="F8CBAD")))
    w.freeze_panes="D5"; w.protection.sheet=True; w.protection.enable()
    r2=out.create_sheet("Criterion"); r2.column_dimensions["A"].width=118
    for i,(t_,head) in enumerate(NOTE,start=1):
        c=r2.cell(row=i,column=1,value=t_); c.alignment=Alignment(vertical="top",wrap_text=True)
        c.font=Font(bold=True,size=12,color="1F3864") if head else Font(name=BN,size=11)
    r2.sheet_view.showGridLines=False
    p=os.path.join(OUT,f"EQUIV-VERDICT-{code}.xlsx"); out.save(p); made.append((p,code,len(mine)))

print("built:")
tot=0; ok=True
for p,code,n in made:
    ws=openpyxl.load_workbook(p)["Verdict"]
    d=[r for r in ws.iter_rows(min_row=5,values_only=True) if r and r[0]]
    ids={r[0] for r in d}
    right=all(K[r[0]]["checker"]==code for r in d)
    notown=all(K[r[0]]["author"]!=code for r in d)
    botharms=all(sum(1 for r in d if r[0]==q)==2 for q in ids)
    empty=all(r[7] in (None,"") and r[8] in (None,"") for r in d)
    tot+=len(d)
    print(f"  {p}: {len(d)} tasks over {len(ids)} rows | rows the other author wrote: {notown} | "
          f"matches final_check: {right} | both renderings together: {botharms} | verdict cols empty: {empty}")
    ok &= right and notown and botharms and empty
print(f"\ntotal tasks covered: {tot}/100")
print("VERDICT:", "PASS" if ok and tot==100 else "FAIL")
