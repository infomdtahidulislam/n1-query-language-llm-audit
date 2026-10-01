#!/usr/bin/env python3
"""build_round2.py — N1 Banglish round 2: one revision sheet per writer, one re-judge sheet per approver.

REVISE  (rows both approvers rejected): the writer sees the Bangla, their own rejected rendering and the
        reasons — with the approvers NOT named, so the revision answers the reason and not the person.
REJUDGE (rows going back to the two approvers):
          · re-judge  — text unchanged; rejected earlier on a ground the protocol excludes, so it is
                        judged again against the re-stated criterion. Each approver sees only their OWN
                        earlier reason, never the other's.
          · new-look  — accepted in round 1; the authors spotted a possible slip of the kind the raters
                        themselves rejected elsewhere. The word is named, the verdict is not.
"""
import json, openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side, Protection
from openpyxl.formatting.rule import FormulaRule
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

KIT = "FINAL.xlsx"
D = json.load(open("decisions.json"))

REVISE  = ["Q044", "Q122", "Q182"]
REJUDGE = {                       # qid -> (kind, note shown to the approver)
 "Q109": ("re-judge",  "Judged again, text unchanged. It was rejected earlier over the spelling of one word. "
                       "'totho' is an ordinary way to write তথ্য. Spelling is not a ground for rejection — "
                       "judge whether a real person could type this and whether it says what the Bangla says."),
 "Q186": ("re-judge",  "Judged again, text unchanged. It was rejected earlier over the spelling of one word. "
                       "'ponye' is an ordinary way to write পণ্যে. Spelling is not a ground for rejection — "
                       "judge whether a real person could type this and whether it says what the Bangla says."),
}
# Rows that both approvers ACCEPTED, where the authors then spotted a possible typing slip. Only the person
# who typed it can say whether it was a slip, so the WRITER is asked first; if the text changes, that row's
# two approvers judge the new text afterwards. qid -> the word in question.
RECHECK = {"Q185": "ecommercee", "Q223": "unoffical"}
EXTRA = {"Q182": "Also check 'kon kon' — the Bangla has a single কোন, so the doubling adds a plural sense the Bangla does not carry. (Raised by the authors, not by an approver.)"}

wb = openpyxl.load_workbook(KIT, data_only=True)["Queries"]
hdr = [c.value for c in wb[1]]; ix = {h: i for i, h in enumerate(hdr)}
import re
K = {}
for r in wb.iter_rows(min_row=2, values_only=True):
    q = str(r[ix["query_id"]] or "").strip()
    if re.fullmatch(r"Q\d{3}", q):
        K[q] = dict(cat=r[ix["category"]], sub=r[ix["subtype"]], bn=str(r[ix["bn_text"]] or ""),
                    bl=str(r[ix["bl_text"]] or ""), au=str(r[ix["bl_author"]] or ""),
                    ap=[str(r[ix["bl_approve_1"]] or ""), str(r[ix["bl_approve_2"]] or "")],
                    digits=" ".join(re.findall(r"\d+(?:\.\d+)?", str(r[ix["bn_text"]] or ""))))

hfill=PatternFill("solid",fgColor="1F3864"); yfill=PatternFill("solid",fgColor="FFF2CC")
bfill=PatternFill("solid",fgColor="EAF1FB"); rfill=PatternFill("solid",fgColor="FCE4E4")
thin=Side(style="thin",color="BFBFBF"); bord=Border(left=thin,right=thin,top=thin,bottom=thin)
BN="Nirmala UI"

def sheet(ws, head, width, title, sub):
    ws["A1"]=title; ws["A1"].font=Font(bold=True,size=13,color="1F3864")
    ws["A2"]=sub;   ws["A2"].font=Font(size=10,italic=True,color="595959")
    ws.merge_cells(start_row=1,end_row=1,start_column=1,end_column=len(head))
    ws.merge_cells(start_row=2,end_row=2,start_column=1,end_column=len(head))
    for j,(h,w) in enumerate(zip(head,width),start=1):
        c=ws.cell(row=4,column=j,value=h); c.font=Font(bold=True,color="FFFFFF",size=10); c.fill=hfill
        c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True); c.border=bord
        ws.column_dimensions[get_column_letter(j)].width=w
    ws.row_dimensions[4].height=30

RULES=[("THE RULES HAVE NOT CHANGED — one clarification",True),("",False),
 ("Spelling and word choice are NOT grounds for rejection. If a word is spelled a way you would not spell it,",False),
 ("or you would have chosen a different word, but a real person could type it and the meaning is unchanged —",False),
 ("that is an Accept. \"It does not look right to me\" is not a reason the protocol allows.",False),
 ("বানান বা শব্দ পছন্দ না হলেই Reject নয়। অর্থ ঠিক থাকলে এবং একজন সত্যিকারের মানুষ এভাবে টাইপ করতে পারলে — Accept।",False),
 ("",False),("REJECT only for these",True),("",False),
 ("1. A number changed, shortened or spelled out — the digits must match the Bangla exactly.",False),
 ("2. A brand or shop name appears.",False),
 ("3. Transliteration-tool output (Pānira philṭāra).",False),
 ("4. Something in the Bangla is missing, or something is added that the Bangla does not say.",False),
 ("5. Bangla letters in the Banglish, or more than two sentences.",False),
 ("6. No real person would type it — including a clear typo that makes a non-word (vao for valo).",False),
 ("",False),
 ("Work alone. Do not discuss any row with the other raters. Reasons come to Tahidul.",False),
 ("Save the file and send it back. Do not rename it.",False)]

def rules_tab(out):
    r=out.create_sheet("Rules"); r.column_dimensions["A"].width=118
    for i,(t,head) in enumerate(RULES,start=1):
        c=r.cell(row=i,column=1,value=t); c.alignment=Alignment(vertical="top",wrap_text=True)
        c.font=Font(bold=True,size=12,color="1F3864") if head else Font(name=BN,size=11)
    r.sheet_view.showGridLines=False

made=[]
# ---------- revision sheets ----------
bywriter={}
for q in REVISE: bywriter.setdefault(K[q]["au"],[]).append(q)
for code,qs in bywriter.items():
    out=openpyxl.Workbook(); w=out.active; w.title="Revise"
    head=["query_id","category","digits","Bangla question","Your Banglish (rejected)",
          "Why it was rejected","REVISED BANGLISH — write here"]
    sheet(w,head,[10,15,12,48,48,54,48],
          f"N1 · Banglish revision — rater {code} — {len(qs)} row(s), revision round 1",
          "Both approvers rejected these. Read the reasons, rewrite the Banglish in the yellow column, send the file back. "
          "The approvers are not named — answer the reason, not the person.")
    for i,q in enumerate(sorted(qs)):
        r=5+i; k=K[q]
        reasons=[v[1] for a,v in D[q].items() if v[0].startswith("rej")]
        txt=" · ".join(f"Reason {n}: {t}" for n,t in enumerate(reasons,1))
        if q in EXTRA: txt += " · " + EXTRA[q]
        for j,v in enumerate([q,k["cat"],k["digits"],k["bn"],k["bl"],txt,None],start=1):
            c=w.cell(row=r,column=j,value=v); c.border=bord
            c.alignment=Alignment(vertical="top",wrap_text=(j in (4,5,6,7)))
            c.protection=Protection(locked=(j!=7))
            if j==1: c.font=Font(bold=True,size=10)
            if j==3: c.font=Font(bold=True,size=11,color="C00000"); c.alignment=Alignment(horizontal="center",vertical="top")
            if j==4: c.font=Font(name=BN,size=12)
            if j==5: c.fill=rfill
            if j==6: c.font=Font(size=10,italic=True,color="843C0C")
            if j==7: c.fill=yfill; c.font=Font(size=11)
    w.freeze_panes="A5"; w.protection.sheet=True; w.protection.enable()
    rules_tab(out)
    p=f"RATER-{code}-REVISE-R1.xlsx"; out.save(p); made.append((p,code,"revise",len(qs)))

# ---------- re-judge sheets ----------
byapprover={}
for q in REJUDGE:
    for a in K[q]["ap"]: byapprover.setdefault(a,[]).append(q)
for code,qs in byapprover.items():
    out=openpyxl.Workbook(); w=out.active; w.title="Judge"
    head=["query_id","category","digits","Bangla question","Banglish to judge",
          "Why this row is back","Your earlier decision","Accept / Reject","Reason — required if you Reject"]
    sheet(w,head,[10,15,12,44,44,50,18,15,44],
          f"N1 · Banglish re-judging — rater {code} — {len(qs)} row(s)",
          "Read the note on each row, then Accept or Reject. Reject needs a reason. The 'Rules' tab has the clarification. Work alone.")
    for i,q in enumerate(sorted(qs)):
        r=5+i; k=K[q]; kind,note=REJUDGE[q]
        prev=D[q].get(code,("",""))
        prevtxt = ("Accept" if prev[0]=="accept" else f"Reject — “{prev[1]}”") if prev[0] else "—"
        for j,v in enumerate([q,k["cat"],k["digits"],k["bn"],k["bl"],note,prevtxt,None,None],start=1):
            c=w.cell(row=r,column=j,value=v); c.border=bord
            c.alignment=Alignment(vertical="top",wrap_text=(j in (4,5,6,7,9)))
            c.protection=Protection(locked=(j not in (8,9)))
            if j==1: c.font=Font(bold=True,size=10)
            if j==3: c.font=Font(bold=True,size=11,color="C00000"); c.alignment=Alignment(horizontal="center",vertical="top")
            if j==4: c.font=Font(name=BN,size=12)
            if j==5: c.fill=bfill; c.font=Font(size=11)
            if j==6: c.font=Font(size=10,italic=True,color="1F4E79")
            if j==7: c.font=Font(size=10,color="595959")
            if j in (8,9): c.fill=yfill
            if j==8: c.alignment=Alignment(horizontal="center",vertical="center")
    last=4+len(qs)
    dv=DataValidation(type="list",formula1='"Accept,Reject"',allow_blank=True,showDropDown=False)
    w.add_data_validation(dv); dv.add(f"H5:H{last}")
    w.conditional_formatting.add(f"I5:I{last}",
        FormulaRule(formula=['AND($H5="Reject",$I5="")'],fill=PatternFill("solid",fgColor="F8CBAD")))
    w.freeze_panes="A5"; w.protection.sheet=True; w.protection.enable()
    rules_tab(out)
    p=f"RATER-{code}-REJUDGE-R1.xlsx"; out.save(p); made.append((p,code,"rejudge",len(qs)))

# ---------- recheck sheets (writer's own accepted row) ----------
byw = {}
for q, word in RECHECK.items(): byw.setdefault(K[q]["au"], []).append((q, word))
for code, items in byw.items():
    out = openpyxl.Workbook(); w = out.active; w.title = "Recheck"
    head = ["query_id", "category", "Bangla question", "Your Banglish (accepted)",
            "The word we are asking about", "Did you mean it?", "If it was a slip, write the corrected line here"]
    sheet(w, head, [10, 15, 46, 46, 22, 16, 50],
          f"N1 · Check your own wording — rater {code} — {len(items)} row(s)",
          "Both approvers accepted these rows. We noticed one word that may be a typing slip. "
          "Only you can say — if you meant it, keep it; if it was a slip, correct it. Neither answer is wrong.")
    for i, (q, word) in enumerate(sorted(items)):
        r = 5 + i; k = K[q]
        for j, v in enumerate([q, k["cat"], k["bn"], k["bl"], word, None, None], start=1):
            c = w.cell(row=r, column=j, value=v); c.border = bord
            c.alignment = Alignment(vertical="top", wrap_text=(j in (3, 4, 7)))
            c.protection = Protection(locked=(j not in (6, 7)))
            if j == 1: c.font = Font(bold=True, size=10)
            if j == 3: c.font = Font(name=BN, size=12)
            if j == 4: c.fill = bfill; c.font = Font(size=11)
            if j == 5: c.font = Font(bold=True, size=12, color="C00000"); c.alignment = Alignment(horizontal="center", vertical="center")
            if j in (6, 7): c.fill = yfill
            if j == 6: c.alignment = Alignment(horizontal="center", vertical="center")
    last = 4 + len(items)
    dv = DataValidation(type="list", formula1='"I meant it,It was a slip"', allow_blank=True, showDropDown=False)
    w.add_data_validation(dv); dv.add(f"F5:F{last}")
    w.conditional_formatting.add(f"G5:G{last}",
        FormulaRule(formula=['AND($F5="It was a slip",$G5="")'], fill=PatternFill("solid", fgColor="F8CBAD")))
    w.freeze_panes = "A5"; w.protection.sheet = True; w.protection.enable()
    rules_tab(out)
    p = f"RATER-{code}-RECHECK-R1.xlsx"; out.save(p); made.append((p, code, "recheck", len(items)))

# ---------------- verification ----------------
print("built:")
ok=True
for p,code,kind,n in made:
    chk=openpyxl.load_workbook(p); ws=chk[chk.sheetnames[0]]
    rows=[r for r in ws.iter_rows(min_row=5,values_only=True) if r and r[0]]
    ids=[r[0] for r in rows]
    blob="\n".join(str(c.value) for s in chk.worksheets for row in s.iter_rows() for c in row if c.value)
    names=[t for t in ("R1","R2","R3") if t in blob]
    if kind=="recheck":
        selfown = all(K[q]["au"]==code for q in ids)
        print(f"  {p}: {len(ids)} rows {ids} | all written by {code}: {selfown} | codes visible: {names}")
        ok &= selfown and names==[code]
        continue
    if kind=="revise":
        selfown = all(K[q]["au"]==code for q in ids)
        others  = [q for q in ids if code in K[q]["ap"]]
        print(f"  {p}: {len(ids)} rows {ids} | all written by {code}: {selfown} | approver codes visible: {names}")
        ok &= selfown and not others and names==[code]
    else:
        assigned = all(code in K[q]["ap"] for q in ids)
        notmine  = all(K[q]["au"]!=code for q in ids)
        print(f"  {p}: {len(ids)} rows {ids} | all assigned to {code}: {assigned} | none self-written: {notmine} | codes visible: {names}")
        ok &= assigned and notmine and names==[code]
# coverage
cov={}
for q in REJUDGE:
    for a in K[q]["ap"]: cov[q]=cov.get(q,0)+1
print("\nre-judge coverage:", cov, "— every row twice:", all(v==2 for v in cov.values()))
print("recheck rows -> writer:", {q: K[q]["au"] for q in RECHECK})
print("revision rows:", REVISE, "— all R2:", all(K[q]["au"]=="R2" for q in REVISE))
print("VERDICT:", "PASS" if ok else "FAIL")
