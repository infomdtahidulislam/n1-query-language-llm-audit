#!/usr/bin/env python3
"""merge_rater_files.py — write the raters' bl_text back into the kit, safely.

For each returned RATER-<code>-WRITE.xlsx:
  * the row must exist in the kit and be assigned to that rater (bl_author)
  * the Bangla shown to the rater must still equal the kit's bn_text  (tamper / stale-file guard)
  * the target bl_text cell must be empty, or already hold exactly this text (idempotent re-run)
Nothing is written unless EVERY row of EVERY file passes. Then: recalc, cell-level diff, validator.

Usage: python3 merge_rater_files.py kit.xlsx out.xlsx back/R1.xlsx back/R2.xlsx back/R3.xlsx
"""
import re, sys, unicodedata
import openpyxl

kit_path, out_path, *returned = sys.argv[1:]

vals = openpyxl.load_workbook(kit_path, data_only=True)["Queries"]
hdr = [c.value for c in vals[1]]
ix = {h: i for i, h in enumerate(hdr)}
kit, rownum = {}, {}
for n, r in enumerate(vals.iter_rows(min_row=2, values_only=True), start=2):
    q = str(r[ix["query_id"]] or "").strip()
    if re.fullmatch(r"Q\d{3}", q):
        kit[q] = dict(bn=str(r[ix["bn_text"]] or "").strip(),
                      bl=str(r[ix["bl_text"]] or "").strip(),
                      au=str(r[ix["bl_author"]] or "").strip())
        rownum[q] = n

pending, errors = [], []
for path in returned:
    code = re.search(r"R[123]", path.upper()).group(0)
    ws = openpyxl.load_workbook(path, data_only=True)["Write"]
    for r in ws.iter_rows(min_row=5, values_only=True):
        if not r or not r[0]:
            continue
        q = str(r[0]).strip()
        bn_shown = str(r[4] or "").strip()
        bl = unicodedata.normalize("NFC", str(r[5] or "").strip())
        if q not in kit:                        errors.append(f"{code} {q}: not a kit row"); continue
        if kit[q]["au"] != code:                errors.append(f"{code} {q}: assigned to {kit[q]['au']}"); continue
        if kit[q]["bn"] != bn_shown:            errors.append(f"{code} {q}: Bangla in the returned file differs from the kit"); continue
        if not bl:                              errors.append(f"{code} {q}: Banglish is empty"); continue
        if kit[q]["bl"] and kit[q]["bl"] != bl: errors.append(f"{code} {q}: kit already holds a different bl_text"); continue
        pending.append((q, rownum[q], bl))

if errors:
    print(f"REFUSING TO WRITE — {len(errors)} problem(s):")
    for e in errors[:20]: print("  ", e)
    sys.exit(1)

seen = {}
for q, _, bl in pending:
    seen.setdefault(q, 0); seen[q] += 1
dup = [q for q, n in seen.items() if n > 1]
if dup: sys.exit(f"REFUSING TO WRITE — the same row arrived twice: {dup[:5]}")

wb = openpyxl.load_workbook(kit_path)          # keep formulas
ws = wb["Queries"]
bl_col = ix["bl_text"] + 1
for q, n, bl in pending:
    ws.cell(row=n, column=bl_col, value=bl)
wb.save(out_path)
print(f"wrote {len(pending)} bl_text cells -> {out_path}  (rows {min(n for _,n,_ in pending)}–{max(n for _,n,_ in pending)}, column {bl_col})")
