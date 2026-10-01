#!/usr/bin/env python3
"""starter_check_compare.py — N1: compares the two authors' independent starter-class confirmations
(STARTER-CHECK-Tahidul-decisions.json, STARTER-CHECK-Maksuda-decisions.json, banked as received) against the
drafted classes of brand_aliases.starter.csv and the frozen brand_aliases.csv, and writes STARTER-CHECK-RESULT.json/.md.
Standard library only. A class is confirmed when both authors give the drafted class; any other row is listed for
resolution under the C.1 rule (post-freeze record of 28 Sep 2026).
"""
import csv, hashlib, json
from pathlib import Path

W = Path(".")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
with open(W / "brand_aliases.starter.csv", encoding="utf-8", newline="") as fh:
    starter = {r["canonical_id"]: r for r in csv.DictReader(fh)}
with open(W / "brand_aliases.csv", encoding="utf-8", newline="") as fh:
    frozen = {r["canonical_id"]: r for r in csv.DictReader(fh)}
assert len(starter) == 49 and all(frozen[c]["class"] == r["class"] for c, r in starter.items())
files = {a: W / f"STARTER-CHECK-{a}-decisions.json" for a in ("Tahidul", "Maksuda")}
dec = {}
for a, p in files.items():
    with open(p, encoding="utf-8") as fh:
        o = json.load(fh)
    assert o["task"] == "N1 starter-table class confirmation" and o["author"] == a and o["n"] == 49 and len(o["rows"]) == 49
    assert o["starter_sha256"] == sha(W / "brand_aliases.starter.csv") and o["frozen_sha256"] == sha(W / "brand_aliases.csv")
    assert sha(p) == sha(W / f"STARTER-CHECK-{a}-decisions_as-received.json"), f"{a}: banked copy differs from the as-received copy"
    rows = {r["canonical_id"]: r for r in o["rows"]}
    assert sorted(rows) == sorted(starter) and [r["canonical_id"] for r in o["rows"]] == sorted(starter)
    assert all(r["your_class"] in ("local", "global", "ambiguous") for r in rows.values())
    assert all(r["drafted_class"] == starter[c]["class"] for c, r in rows.items())
    dec[a] = {"exported_at": o["exported_at"], "sha256": sha(p), "rows": rows}

out_rows, confirmed, unresolved = [], 0, []
for c in sorted(starter):
    d = starter[c]["class"]
    t, m = dec["Tahidul"]["rows"][c], dec["Maksuda"]["rows"][c]
    ok = (t["your_class"] == d and m["your_class"] == d)
    confirmed += ok
    row = {"canonical_id": c, "display_name": starter[c]["display_name"], "drafted_class": d, "tahidul": t["your_class"], "maksuda": m["your_class"],
           "confirmed": ok, "notes": {k: v for k, v in (("Tahidul", t["note"].strip()), ("Maksuda", m["note"].strip())) if v}}
    out_rows.append(row)
    if not ok:
        unresolved.append(row)
by_class = {k: sum(1 for r in out_rows if r["drafted_class"] == k) for k in ("global", "local", "ambiguous")}
res = {"task": "N1 starter-table class confirmation — comparison", "entities": 49, "drafted_by_class": by_class,
       "confirmed_by_both": confirmed, "unresolved": unresolved,
       "agreement_between_authors": sum(1 for r in out_rows if r["tahidul"] == r["maksuda"]),
       "differs_from_draft": {a: sum(1 for r in out_rows if r[a.lower()] != r["drafted_class"]) for a in ("Tahidul", "Maksuda")},
       "notes_given": sum(1 for r in out_rows if r["notes"]),
       "files": {a: {"exported_at": dec[a]["exported_at"], "sha256": dec[a]["sha256"]} for a in dec},
       "inputs": {"brand_aliases.starter.csv": sha(W / "brand_aliases.starter.csv"), "brand_aliases.csv": sha(W / "brand_aliases.csv")},
       "consequence": ("no class changes: the frozen table's classes stand as confirmed; no sensitivity re-run is needed" if not unresolved
                       else "rows listed under 'unresolved' are resolved by the C.1 rule with a written reason; if any class changes, RQ2 "
                            "local share and the local-retailer share are re-run with the corrected classes as a declared sensitivity"),
       "rows": out_rows, "script_sha256": sha(Path(__file__))}
with open(W / "STARTER-CHECK-RESULT.json", "w", encoding="utf-8", newline="\n") as fh:
    json.dump(res, fh, indent=1, ensure_ascii=False)
L = ["# N1 — starter-table class confirmation: result (28 Sep 2026)", "",
     f"49 starter entities (drafted 1 Sep 2026: global {by_class['global']}, local {by_class['local']}, ambiguous {by_class['ambiguous']}). "
     f"Both authors answered all 49 independently — exports {dec['Tahidul']['exported_at']} (Tahidul) and {dec['Maksuda']['exported_at']} (Maksuda), banked as received.", "",
     f"**Confirmed by both authors: {confirmed} / 49.** Author agreement {res['agreement_between_authors']} / 49; differences from the draft: "
     f"Tahidul {res['differs_from_draft']['Tahidul']}, Maksuda {res['differs_from_draft']['Maksuda']}; notes given: {res['notes_given']}.", "",
     f"Consequence: {res['consequence']}.", "", "| entity | drafted | Tahidul | Maksuda | confirmed |", "|---|---|---|---|---|"]
for r in out_rows:
    L.append(f"| {r['display_name']} (`{r['canonical_id']}`) | {r['drafted_class']} | {r['tahidul']} | {r['maksuda']} | {'yes' if r['confirmed'] else 'NO'} |")
L += ["", f"Inputs: brand_aliases.starter.csv `{res['inputs']['brand_aliases.starter.csv'][:12]}…`, brand_aliases.csv `{res['inputs']['brand_aliases.csv'][:12]}…`; "
      f"decision files `{dec['Tahidul']['sha256'][:12]}…` / `{dec['Maksuda']['sha256'][:12]}…`; script `{res['script_sha256'][:12]}…`."]
with open(W / "STARTER-CHECK-RESULT.md", "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(L) + "\n")
print(f"confirmed {confirmed}/49; agreement {res['agreement_between_authors']}/49; unresolved {len(unresolved)}; notes {res['notes_given']}")
