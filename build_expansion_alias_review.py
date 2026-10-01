#!/usr/bin/env python3
"""build_expansion_alias_review.py — N1: the authors' Appendix C.2–C.3 review for the expansion sample.

Derives, from the banked and frozen inputs only, every brand / retailer surface form that enters the
expansion analysis set and does not resolve under the FROZEN brand_aliases.csv — i.e. every name in
the three expansion exports (brands + recommended, retailers; all items, all raters) and in the three
Round-2 labels of the 38 reused items — using exactly the resolver of the registered scorer
(round2_agreement.py / build_expansion_analysis_set.py: case/accent fold, trailing-parenthetical
strip, exact alias match, then 3/2/1-token prefix). It lists them ALPHABETICALLY with NO frequency,
NO arm and NO model information (Appendix C.3); the only context shown is the field the raters used
and the query categories the name appeared under (query-level, identical across arms and models).

Each row carries a draft decision from EXPANSION-ALIAS-PREFILL.csv (drafted by an AI assistant from
public headquarters/ownership information and the registered precedents, blind to frequency, arm and
model). The authors confirm or change every row; decisions export as EXPANSION-ALIAS-DECISIONS.json,
which keeps the draft and the final decision side by side for every row.

Outputs (LF line endings): EXPANSION-ALIAS-CANDIDATES.csv (derived columns + draft), and
EXPANSION-ALIAS-REVIEW.html (the review page).   Usage (study root): python build_expansion_alias_review.py
"""
import csv, hashlib, html, json, re, sys, unicodedata
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

W = Path(".")
GATES = {
    "brand_aliases.csv": "0b7bd5e8355c919300129b6ba96008d5cb2d95a691aaf759a1e82823ee2b00ea",
    "retailer_classification.csv": "94abc294de6fc82c6583d1e9be08bc7443e49008376cf2a718cd6febd19cf22a",
    "queries.csv": "9639998a98d605f700f7537fe9a3cfb7ed53975b0b1cb43b7a0bf75b595b5e02",
    "EXPANSION-MAPPING-authors-only.csv": "e2bacda5ccc71eee60fb95a9a18350421fb87cc17c7e32f529277b158f3135c0",
    "LABEL-EXPANSION-R1-labels.json": "e81ae46f5723052708dd777893488da50b0bbae27872a58cf33c22e5bd1f74bc",
    "LABEL-EXPANSION-R2-labels.json": "699bec10cf993bb7742e7e852c778689d550a5b2839c4eaa0cb99cebf83af63b",
    "LABEL-EXPANSION-R3-labels.json": "1f2c81dd0941700442fc13e8999f1e4b37a10ba4c37de818c3d8f1e9adc772c0",
    "LABEL-ROUND2-R1-labels.json": "53f46eba77861230edf8ee524ad7a0ec243359a21f43bb3c049470d20e9890ab",
    "LABEL-ROUND2-R2-labels.json": "335dd4dd4f5253abbe253b9fc9686f189d495bd65b453a1e3fe8304c3dac3ce9",
    "LABEL-ROUND2-R3-labels.json": "fea46917cba908904a9fa003b3099389b4f0da6419bae750c99503b5d29f3630",
}
RATERS = ("R1", "R2", "R3")

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

for f, want in GATES.items():
    if sha(W / f) != want:
        sys.exit(f"INPUT GATE: {f} is not the banked/frozen file — refusing to build")

# ---------- the registered resolver, verbatim ----------
def fold(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s.strip())
    return s.casefold().strip()

brands = list(csv.DictReader(open(W / "brand_aliases.csv", encoding="utf-8")))
retail = list(csv.DictReader(open(W / "retailer_classification.csv", encoding="utf-8")))
alias_map = {}
for row in brands:
    alias_map[fold(row["display_name"])] = row["canonical_id"]
    for al in row["aliases"].split("|"):
        if al.strip():
            alias_map[fold(al)] = row["canonical_id"]

def cid(s):
    fs = fold(s)
    if fs in alias_map:
        return alias_map[fs]
    toks = fs.split()
    for n in (3, 2, 1):
        if len(toks) >= n and " ".join(toks[:n]) in alias_map:
            return alias_map[" ".join(toks[:n])]
    return None

def rl(row, f):
    v = row.get(f) or []
    return v if isinstance(v, list) else [x for x in str(v).splitlines() if x.strip()]

# ---------- candidates ----------
SHORT = {"Smartphones": "Pho", "Air conditioners": "AC", "Refrigerators": "Fri", "Motorbikes": "Moto",
         "Skincare": "Skin", "Banks & MFS": "Bank", "ISPs": "ISP", "E-commerce": "Ecom", "Laptops": "Lap",
         "Televisions": "TV"}
CAT = {v: k for k, v in SHORT.items()}
qcat = {r["query_id"]: r["category"] for r in csv.DictReader(open(W / "queries.csv", encoding="utf-8"))}
mapping = list(csv.DictReader(open(W / "EXPANSION-MAPPING-authors-only.csv", encoding="utf-8")))
pid_q = {m["pid"]: m["query_id"] for m in mapping}
reused = {m["reused_round2_pid"]: m["query_id"] for m in mapping if m["rater"] == "reuse:consensus-round2"}
assert len(reused) == 38

cand = OrderedDict()
def take(label, query_id):
    for field, vals in (("brands", rl(label, "brands") + rl(label, "recommended")),
                        ("retailers", rl(label, "retailers"))):
        for b in vals:
            if str(b).strip() and cid(b) is None:
                e = cand.setdefault(fold(b), {"forms": Counter(), "fields": set(), "cats": set()})
                e["forms"][str(b).strip()] += 1
                e["fields"].add(field)
                e["cats"].add(SHORT[qcat[query_id]])

for rt in RATERS:
    d = json.load(open(W / f"LABEL-EXPANSION-{rt}-labels.json", encoding="utf-8"))
    assert d["task"] == "N1 labelling expansion round" and d["rater"] == rt
    for lab in d["labels"]:
        take(lab, pid_q[lab["pid"]])
for rt in RATERS:
    d = json.load(open(W / f"LABEL-ROUND2-{rt}-labels.json", encoding="utf-8"))
    assert d["task"] == "N1 labelling round 2" and d["rater"] == rt
    for lab in d["labels"]:
        if lab["pid"] in reused:
            take(lab, reused[lab["pid"]])

PF = {r["surface_folded"]: r for r in csv.DictReader(open(W / "EXPANSION-ALIAS-PREFILL.csv", encoding="utf-8"))}
missing = sorted(set(cand) - set(PF))
stale = sorted(set(PF) - set(cand))
if missing or stale:
    sys.exit(f"PREFILL does not match the derived candidate list: missing {missing[:10]} stale {stale[:10]}")

cand_rows = []
for i, k in enumerate(sorted(cand)):
    e, p = cand[k], PF[k]
    cand_rows.append({"i": str(i), "surface_folded": k, "example_surface": e["forms"].most_common(1)[0][0],
                      "all_surfaces": " | ".join(sorted(e["forms"])), "seen_in_field": "+".join(sorted(e["fields"])),
                      "categories": ",".join(sorted(e["cats"])),
                      **{f: p[f] for f in ("prefill_kind", "prefill_class", "prefill_id", "prefill_display",
                                           "prefill_note", "check")}})

# ---------- draft sanity (the authors can change anything; this only stops a malformed draft) ----------
existing = {r["canonical_id"] for r in brands}
new_ids = Counter(c["prefill_id"] for c in cand_rows if c["prefill_kind"] in ("brand", "retailer", "both"))
SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
for c in cand_rows:
    k = c["prefill_kind"]
    assert k in ("brand", "retailer", "both", "alias", "exclude", "unidentified"), c
    assert c["prefill_class"] in ("", "local", "global", "ambiguous") and c["check"] in ("", "yes"), c
    if k in ("brand", "retailer", "both"):
        assert SLUG.fullmatch(c["prefill_id"]) and new_ids[c["prefill_id"]] == 1 and c["prefill_id"] not in existing, c
        assert c["prefill_display"].strip() and fold(c["prefill_display"]) not in alias_map, c
    elif k == "alias":
        assert c["prefill_id"] in existing | set(new_ids) and not c["prefill_class"], c
    else:
        assert not c["prefill_id"] and not c["prefill_class"], c

CAND_FIELDS = ["i", "surface_folded", "example_surface", "all_surfaces", "seen_in_field", "categories",
               "prefill_kind", "prefill_class", "prefill_id", "prefill_display", "prefill_note", "check"]
with open(W / "EXPANSION-ALIAS-CANDIDATES.csv", "w", newline="", encoding="utf-8") as f:
    wcsv = csv.DictWriter(f, fieldnames=CAND_FIELDS, lineterminator="\n")
    wcsv.writeheader()
    wcsv.writerows(cand_rows)
cand = cand_rows
canonicals = sorted(existing | {r["canonical_id"] for r in retail} | set(new_ids))
PREFILL_NOTE = ("rows pre-filled 2026-09-26 by Claude (AI assistant) from public headquarters/ownership "
                "information and the registered precedents, with no frequency, arm or model information; "
                "reviewed and finalised by the authors")

def esc(s): return html.escape(s or "")

def default_slug(c):
    """Pre-filled canonical_id for rows the authors may switch to Brand/Retailer (never used unless they do)."""
    s = re.sub(r"[^a-z0-9]+", "-", c["surface_folded"].encode("ascii", "ignore").decode()).strip("-")
    return s or f"entity-{c['i']}"

def card(c):
    i = int(c["i"])
    cats = ", ".join(CAT[x] for x in c["categories"].split(",") if x)
    field = {"brands": "brands field", "retailers": "retailers field",
             "brands+retailers": "brands and retailers fields"}[c["seen_in_field"]]
    others = [s for s in c["all_surfaces"].split(" | ") if s != c["example_surface"]]
    also = f' <span class="meta">also written: {esc(", ".join(others))}</span>' if others else ""
    chk = '<span class="b warn">CHECK</span>' if c["check"] else ""
    ret = '<span class="b info">retailer field</span>' if "retailers" in c["seen_in_field"] else ""
    k = c["prefill_kind"]
    def kr(v, lab):
        return (f'<label><input type="radio" name="k{i}" value="{v}"{" checked" if k == v else ""}> {lab}</label>')
    def cr(v):
        return (f'<label><input type="radio" name="c{i}" value="{v}"'
                f'{" checked" if c["prefill_class"] == v else ""}> {v}</label>')
    tgt = c["prefill_id"] if k == "alias" else ""
    slug = c["prefill_id"] if k in ("brand", "retailer", "both") else default_slug(c)
    disp = c["prefill_display"] if k in ("brand", "retailer", "both") else c["example_surface"]
    return f"""
<div class="row" data-i="{i}" data-chk="{1 if c['check'] else 0}" data-ret="{1 if 'retailers' in c['seen_in_field'] else 0}"
     data-pk="{esc(k)}">
 <div class="rh">
   <span class="forms">{esc(c['example_surface'])}</span>{also}
   <span class="meta">{field} · {esc(cats)}</span> {chk} {ret}
   <span class="st" id="st{i}">undecided</span>
 </div>
 <div class="pf">prefill: <b>{esc(k)}</b>{(' · ' + esc(c['prefill_class'])) if c['prefill_class'] else ''}{(' → ' + esc(c['prefill_id'])) if k == 'alias' else ''}{(' — ' + esc(c['prefill_note'])) if c['prefill_note'] else ''}</div>
 <div class="rb">
  <div class="kind">{kr("brand", "Brand")}{kr("retailer", "Retailer")}{kr("both", "Brand + retailer")}{kr("alias", "Alias of existing →")}{kr("exclude", "Not a brand (exclude)")}{kr("unidentified", "Unidentified")}</div>
  <div class="detail">
    <span class="cls" id="cls{i}" hidden>{cr("local")}{cr("global")}{cr("ambiguous")}</span>
    <input class="tgt" id="tgt{i}" list="canon" placeholder="canonical id it maps to" value="{esc(tgt)}" hidden>
    <span class="ids" id="ids{i}" hidden>
      <input class="slug" id="slug{i}" value="{esc(slug)}" title="canonical_id">
      <input class="disp" id="disp{i}" value="{esc(disp)}" title="display_name">
    </span>
    <input class="note" id="note{i}" placeholder="note (optional)" value="">
  </div>
 </div>
</div>"""

def table_rows(rows, alias_col):
    out = []
    for r in sorted(rows, key=lambda x: x["canonical_id"]):
        al = esc(r.get(alias_col, "")) if alias_col else ""
        out.append(f"<tr><td><code>{esc(r['canonical_id'])}</code></td><td>{esc(r['display_name'])}</td>"
                   f"<td>{esc(r['class'])}</td><td class='al'>{al}</td></tr>")
    return "".join(out)

N = len(cand)
assert [int(c["i"]) for c in cand] == list(range(N))
cards = "".join(card(c) for c in sorted(cand, key=lambda c: int(c["i"])))
canon_opts = "".join(f'<option value="{esc(c)}">' for c in canonicals)
meta = json.dumps([{"i": int(c["i"]), "surface_folded": c["surface_folded"], "example_surface": c["example_surface"],
                    "prefill_kind": c["prefill_kind"], "prefill_class": c["prefill_class"],
                    "prefill_id": c["prefill_id"], "prefill_display": c["prefill_display"],
                    "prefill_note": c["prefill_note"], "check": bool(c["check"])} for c in cand],
                  ensure_ascii=False)

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Expansion round — brand and retailer review</title>
<style>
 :root{color-scheme:light}
 body{margin:0;padding:0 16px 90px;background:#f6f5f1;color:#16181d;font:15px/1.5 "Segoe UI",system-ui,sans-serif}
 .wrap{max-width:1080px;margin:0 auto}
 h1{font-size:23px;margin:18px 0 4px} .sub{color:#555;margin:0 0 12px}
 .instr{background:#fff;border:1px solid #ddd;border-radius:10px;padding:4px 18px 14px;margin:0 0 14px}
 .instr h3{margin:14px 0 4px;font-size:16px;color:#1a4d8f}
 .instr p{margin:5px 0} .instr code{background:#eee;padding:0 4px;border-radius:3px}
 .rulebox{background:#eef3fa;border-radius:8px;padding:9px 14px;margin:8px 0}
 .topbar{position:sticky;top:0;z-index:10;background:#f6f5f1ee;backdrop-filter:blur(3px);padding:8px 0;
         border-bottom:1px solid #ddd;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
 #prog{font-weight:700}
 .fbtn{border:1px solid #bbb;background:#fff;border-radius:14px;padding:4px 12px;font:13px inherit;cursor:pointer}
 .fbtn.on{background:#1a4d8f;color:#fff;border-color:#1a4d8f}
 button.exp{background:#1a4d8f;color:#fff;border:0;border-radius:6px;padding:8px 16px;font:700 14px inherit;cursor:pointer}
 .row{background:#fff;border:1px solid #ddd;border-radius:8px;margin:8px 0;padding:9px 13px}
 .row.done{border-color:#7cb87c;background:#fbfdfb}
 .rh{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
 .forms{font-weight:700;font-size:15px}
 .meta{color:#666;font-size:13px}
 .pf{color:#6b5b2e;font-size:12.5px;margin-top:3px}
 .b{font-size:11px;font-weight:700;border-radius:9px;padding:2px 8px;letter-spacing:.02em}
 .b.warn{background:#fdecec;color:#a33}.b.info{background:#e8eef7;color:#3a5f94}
 .st{margin-left:auto;font-size:12px;color:#8a6d3b}.row.done .st{color:#2e7d32;font-weight:700}
 .rb{margin-top:7px}
 .kind{display:flex;gap:5px 16px;flex-wrap:wrap;font-size:14px}
 .kind label,.cls label{cursor:pointer;user-select:none}
 .kind input,.cls input{accent-color:#1a4d8f}
 .detail{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-top:6px}
 .cls{display:flex;gap:12px;background:#f4f7fb;border-radius:6px;padding:4px 12px;font-size:14px}
 input.tgt,input.slug,input.disp,input.note{padding:5px 8px;border:1px solid #ccc;border-radius:6px;font:13px inherit}
 input.tgt{width:230px}input.slug{width:170px}input.disp{width:190px}input.note{flex:1;min-width:170px}
 details.starter{background:#fff;border:1px solid #ddd;border-radius:10px;padding:8px 14px;margin:0 0 12px}
 details.starter summary{cursor:pointer;user-select:none}
 details.starter table{border-collapse:collapse;margin:10px 0 4px;font-size:13px;width:100%}
 details.starter th,details.starter td{border:1px solid #e3e0d8;padding:4px 8px;text-align:left;vertical-align:top}
 details.starter th{background:#f0eee8}
 details.starter td.al{color:#555;max-width:480px;word-break:break-word}
 .foot{margin:24px 0;text-align:center}#msg,#msg2{font-weight:600;color:#2e7d32}
 [hidden]{display:none !important}
 .pgrp{display:flex;gap:8px;align-items:center;flex-wrap:wrap;width:100%;padding-top:4px}
 .pbtn{border:1px solid #1a4d8f;background:#fff;color:#1a4d8f;border-radius:6px;padding:5px 12px;font:600 13px inherit;cursor:pointer}
 .pbtn:hover{background:#eef3fa}
 #saved{color:#555;font-size:12.5px}#pmsg{font-size:13px;font-weight:600}
 .row.conflict{border-color:#d98c1f;box-shadow:0 0 0 2px #f6dcb5}
 .b.conf{background:#fdf0dc;color:#9a5a00}
</style></head><body><div class="wrap">
<h1>Expansion round — brand and retailer review</h1>
<p class="sub">Authors only · __N__ names in the expansion sample's labels that the frozen table does not
recognise · Appendix C.2–C.3 · your decisions extend <code>brand_aliases.csv</code> and
<code>retailer_classification.csv</code>, which are then re-hashed and registered before any brand result is computed</p>

<div class="instr">
<h3>What this is</h3>
<p>The registered step before RQ1/RQ2 (Appendix C.2–C.3): every brand or retailer name the raters wrote that the
frozen table cannot place. New spellings of known entities become <b>aliases</b>; new entities get a
<b>class</b> by the headquarters rule. Until this is done these names would count as "unclassifiable" and drop out of
the local-vs-global ratio.</p>

<div class="rulebox"><b>Class — Appendix C.1, verbatim rule:</b> a brand is <b>local</b> if its owning company is
headquartered in Bangladesh; otherwise <b>global</b>. Joint ventures, BD-assembled foreign brands and multinational
subsidiaries with substantial local identity get <b>ambiguous</b> — a safe, registered answer, because RQ2 is
computed three ways (ambiguous local / global / excluded).</div>
<p><b>Unidentified</b> — for a name you cannot place after a quick search. It stays in the brand lists and is
counted as <i>unclassifiable</i> (F.3 excludes unclassifiable mentions from the local share and reports their rate),
instead of being guessed into a class or removed. <b>Not a brand</b> removes the name from every list, so keep it for
things that are clearly not brands.</p>

<h3>The rows are prefilled — you decide</h3>
<p>Every row arrives with a suggested decision (shown in brown under the name), drafted from public
headquarters/ownership information, the same draft-then-author-verify pattern as the round-2 review. Nothing
is final until you confirm it. <b>Rows marked CHECK</b> are ones the draft is unsure about, and
<b>rows without a class</b> are left open on purpose — both need your decision. The <b>CHECK</b> and
<b>Needs a decision</b> filters take you straight to them.</p>

<h3>How the rows were prefilled</h3>
<p>Each rule follows a decision already on the registered record, so the expansion is classified the way the
pilot and round-2 tables were. <b>Not a brand (exclude):</b> generic words; components named only as a spec —
chip makers, GPU series, camera co-brands (codebook); reference sources — publications, blogs, YouTube channels,
review, testing, benchmark and valuation sites, forums, rating, survey and certification bodies (round 2:
Consumer Reports, Wirecutter, J.D. Power, Energy Star, Ookla, Reddit, TechShohor); uses, features and tools outside
the ten categories — software, games, apps, streaming services and utilities named as a workload, feature or tool
of the product being chosen, whoever makes them (the logic of the codebook's spec rule); and the answering system's
own name in the persona line. <b>Counted:</b> regulators and central banks named as answer entities, and their own
products (your round-2 standing policy: Bangladesh Bank, BTRC); state-owned providers (as BTCL, Teletalk);
payment networks (as American Express); price-comparison and other shopping-aid portals (you kept price.com.bd at
F2). Names I could not identify are left for you without a class; the two that round 2 could not identify
either (Esco, Icon) are prefilled <b>Unidentified</b>. A decision applies to the name wherever it appears. Every row where another reading is plausible is flagged
<b>CHECK</b> and its note gives the alternative — override anything.</p>

<h3>What you see, and why</h3>
<p>Names are alphabetical. You see which field the raters used and the <b>query categories</b> the name appeared
under — nothing else. Frequencies, arms and models are deliberately hidden (Appendix C.3): classify by the
headquarters rule, never by where or how often something was mentioned.</p>

<h3>Saving and moving your work</h3>
<p>Progress <b>saves automatically in this browser</b> after every click (<b>Save progress</b> saves on demand and shows
the time). <b>Export progress</b> downloads a progress file you can keep as a backup, or open on another computer
with <b>Import progress</b> — so you and Maksuda can work on separate computers. Importing <b>adds</b> the file's
decisions to yours: rows only the file changed are taken from it, rows only you changed stay yours, and a row you
both changed differently keeps <b>your</b> version and is flagged orange (the <b>Import conflicts</b> filter lists
them). <b>Undo import</b> puts back exactly what you had before the import.</p>

<h3>When you're done</h3>
<p>Every row decided (the counter says so) → <b>Export decisions</b> → put
<code>EXPANSION-ALIAS-DECISIONS.json</code> in the study folder. One final export is needed: if you worked on two
computers, import the other person's progress file first, then export from that one browser.</p>
</div>

<details class="starter"><summary><b>Already in the brand table</b> — __NB__ entities (the alias box autocompletes these ids)</summary>
<table><tr><th>canonical_id</th><th>display name</th><th>class</th><th>aliases</th></tr>__BRANDS__</table>
</details>
<details class="starter"><summary><b>Already in the retailer table</b> — __NR__ retailers</summary>
<table><tr><th>canonical_id</th><th>display name</th><th>class</th><th></th></tr>__RETAIL__</table>
</details>

<div class="topbar">
  <span id="prog">0 / __N__ decided</span>
  <button class="fbtn on" data-f="all">All</button>
  <button class="fbtn" data-f="und">Needs a decision</button>
  <button class="fbtn" data-f="chk">CHECK</button>
  <button class="fbtn" data-f="ret">Retailer field</button>
  <button class="fbtn" data-f="exc">Prefilled "not a brand"</button>
  <button class="fbtn" data-f="ali">Prefilled alias</button>
  <button class="fbtn" data-f="conf" id="fconf" hidden>Import conflicts</button>
  <button class="exp" onclick="doExport()">Export decisions</button><span id="msg"></span>
  <div class="pgrp">
    <b>Progress:</b>
    <button class="pbtn" onclick="saveNow()">Save progress</button>
    <button class="pbtn" onclick="exportProgress()">Export progress</button>
    <button class="pbtn" onclick="document.getElementById('impf').click()">Import progress</button>
    <input type="file" id="impf" accept=".json,application/json" hidden>
    <button class="pbtn" id="undoimp" onclick="undoImport()" hidden>Undo import</button>
    <span id="saved"></span><span id="pmsg"></span>
  </div>
</div>
<datalist id="canon">__CANON__</datalist>
__CARDS__
<div class="foot"><button class="exp" onclick="doExport()">Export decisions</button><div id="msg2" style="margin-top:6px"></div></div>
</div>
<script>
var N=__N__, LSK="n1-expansion-alias-review", META=__META__, FROZEN_KEYS=__FKEYS__, EXISTING=__EXIST__;
var REVIEW_ID="__REVIEW_ID__", DRAFT=null, BUSY=false;
function jfold(x){x=String(x).normalize("NFKD").replace(/[\\u0300-\\u036f\\u1ab0-\\u1aff\\u1dc0-\\u1dff\\u20d0-\\u20ff\\ufe20-\\ufe2f]/g,"");
  x=x.trim().replace(/\\s*\\([^)]*\\)\\s*$/,"");return x.toLowerCase().trim();}
function frozenHit(x){var f=jfold(x);if(FROZEN_KEYS[f])return FROZEN_KEYS[f];var t=f.split(/\\s+/);
  for(var n=3;n>=1;n--){if(t.length>=n){var p=t.slice(0,n).join(" ");if(FROZEN_KEYS[p])return FROZEN_KEYS[p];}}return "";}
function problems(s){var out=[],seen={},slugs={};
  for(var i=0;i<N;i++){var r=s.rows[i];if(r.kind==="brand"||r.kind==="retailer"||r.kind==="both"){slugs[r.slug]=(slugs[r.slug]||0)+1;}}
  for(var i=0;i<N;i++){var r=s.rows[i],nm=META[i].example_surface;
    if(r.kind==="brand"||r.kind==="retailer"||r.kind==="both"){
      if(!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(r.slug))out.push([i,nm+": canonical_id must be lower-case letters/digits with hyphens"]);
      else if(EXISTING[r.slug])out.push([i,nm+": id '"+r.slug+"' already exists — choose 'Alias of existing' instead"]);
      else if(slugs[r.slug]>1)out.push([i,nm+": id '"+r.slug+"' is used on more than one row — merge with 'Alias of existing'"]);
      var h=frozenHit(r.display);if(h)out.push([i,nm+": display name '"+r.display+"' is already a name of '"+h+"' — alias it, or keep the row's own spelling"]);}
    else if(r.kind==="alias"){if(!(EXISTING[r.target]||slugs[r.target]))out.push([i,nm+": alias target '"+r.target+"' is not an existing or new id"]);}}
  return out;}
function kind(i){var e=document.querySelector('input[name="k'+i+'"]:checked');return e?e.value:"";}
function cls(i){var e=document.querySelector('input[name="c'+i+'"]:checked');return e?e.value:"";}
function decided(i){var k=kind(i);if(!k)return false;
  if(k==="alias")return !!document.getElementById("tgt"+i).value.trim();
  if(k==="exclude"||k==="unidentified")return true;
  return !!cls(i)&&!!document.getElementById("slug"+i).value.trim()&&!!document.getElementById("disp"+i).value.trim();}
function refresh(){var n=0;for(var i=0;i<N;i++){var k=kind(i);
  document.getElementById("cls"+i).hidden=!(k==="brand"||k==="retailer"||k==="both");
  document.getElementById("tgt"+i).hidden=(k!=="alias");
  document.getElementById("ids"+i).hidden=!(k==="brand"||k==="retailer"||k==="both");
  var d=decided(i);if(d)n++;
  var row=document.querySelector('.row[data-i="'+i+'"]');row.classList.toggle("done",d);
  document.getElementById("st"+i).textContent=d?(kind(i)+(cls(i)?" \\u00b7 "+cls(i):"")):"needs a decision";}
  document.getElementById("prog").textContent=n+" / "+N+" decided";save();return n;}
function state(){var s={rows:{}};for(var i=0;i<N;i++){s.rows[i]={kind:kind(i),cls:cls(i),
  target:document.getElementById("tgt"+i).value.trim(),slug:document.getElementById("slug"+i).value.trim(),
  display:document.getElementById("disp"+i).value.trim(),note:document.getElementById("note"+i).value.trim()};}return s;}
function hhmm(d){return ("0"+d.getHours()).slice(-2)+":"+("0"+d.getMinutes()).slice(-2);}
function save(){if(BUSY)return;var ok=true;
  try{localStorage.setItem(LSK,JSON.stringify(state()));localStorage.setItem(LSK+"-t",new Date().toISOString());}catch(e){ok=false;}
  var el=document.getElementById("saved");
  if(el)el.textContent=ok?("saved in this browser \u00b7 "+hhmm(new Date())):"this browser is not saving progress — use Export progress";}
function saveNow(){save();pmsg("Progress saved in this browser.",true);}
function pmsg(t,good){var e=document.getElementById("pmsg");e.style.color=good?"#2e7d32":"#b23b3b";e.textContent=t;}
function norm(r){var k=r.kind||"",o={kind:k,cls:"",target:"",slug:"",display:""};
  if(k==="alias")o.target=(r.target||"").trim();
  else if(k==="brand"||k==="retailer"||k==="both"){o.cls=r.cls||"";o.slug=(r.slug||"").trim();o.display=(r.display||"").trim();}
  return o;}
function same(a,b){var x=norm(a),y=norm(b);return x.kind===y.kind&&x.cls===y.cls&&x.target===y.target&&x.slug===y.slug&&x.display===y.display;}
function setRow(i,o){
  document.querySelectorAll('input[name="k'+i+'"]').forEach(function(e){e.checked=(e.value===o.kind);});
  document.querySelectorAll('input[name="c'+i+'"]').forEach(function(e){e.checked=(e.value===o.cls);});
  document.getElementById("tgt"+i).value=o.target||"";
  if(o.slug)document.getElementById("slug"+i).value=o.slug;
  if(o.display)document.getElementById("disp"+i).value=o.display;
  document.getElementById("note"+i).value=o.note||"";}
function stamp(){var d=new Date();return d.getFullYear()+("0"+(d.getMonth()+1)).slice(-2)+("0"+d.getDate()).slice(-2)+"-"+
  ("0"+d.getHours()).slice(-2)+("0"+d.getMinutes()).slice(-2);}
function download(obj,name){var a=document.createElement("a");
  a.href=URL.createObjectURL(new Blob([JSON.stringify(obj,null,1)],{type:"application/json"}));
  a.download=name;document.body.appendChild(a);a.click();a.remove();}
function exportProgress(){var s=state(),n=0,rows=[];
  for(var i=0;i<N;i++){if(decided(i))n++;var r=s.rows[i];
    rows.push({i:i,surface_folded:META[i].surface_folded,kind:r.kind,cls:r.cls,target:r.target,slug:r.slug,display:r.display,note:r.note});}
  var name="EXPANSION-ALIAS-PROGRESS-"+stamp()+".json";
  download({task:"N1 expansion alias progress",review_id:REVIEW_ID,saved_at:new Date().toISOString(),n:N,decided:n,rows:rows},name);
  save();pmsg("Progress exported as "+name+" ("+n+" / "+N+" decided).",true);}
function readRows(obj){
  var list=null;
  if(obj&&obj.task==="N1 expansion alias progress"){if(obj.review_id!==REVIEW_ID)return "this progress file belongs to a different review page";list=obj.rows;}
  else if(obj&&obj.task==="N1 expansion alias decisions"){list=obj.decisions;}
  else return "not a progress or decisions file from this review";
  if(!list||list.length!==N)return "the file has "+(list?list.length:0)+" rows; this review has "+N;
  var out={};
  for(var j=0;j<list.length;j++){var r=list[j];
    if(typeof r.i!=="number"||r.i<0||r.i>=N||r.surface_folded!==META[r.i].surface_folded)return "row "+j+" does not match this review's names";
    out[r.i]=r;}
  return out;}
function importProgress(file){var fr=new FileReader();
  fr.onload=function(){var obj=null;try{obj=JSON.parse(fr.result);}catch(e){pmsg("Import failed: the file is not valid JSON.",false);return;}
    var rows=readRows(obj);if(typeof rows==="string"){pmsg("Import failed: "+rows+". Nothing was changed.",false);return;}
    var cur=state(),backup=JSON.stringify(cur);
    try{localStorage.setItem(LSK+"-backup",backup);}catch(e){}
    window._backup=backup;
    var took=0,conf=0,notes=0;BUSY=true;
    document.querySelectorAll(".row.conflict").forEach(function(r){r.classList.remove("conflict");r.dataset.conf="0";});
    for(var i=0;i<N;i++){var c=cur.rows[i],f=rows[i],d=DRAFT.rows[i];
      var fo={kind:f.kind||"",cls:f.cls||"",target:f.target||"",slug:f.slug||"",display:f.display||"",note:f.note||""};
      var nt=(!c.note&&fo.note)?fo.note:c.note;
      if(same(fo,d)||same(fo,c)){if(nt!==c.note){document.getElementById("note"+i).value=nt;notes++;}continue;}
      if(same(c,d)){fo.note=nt;setRow(i,fo);took++;continue;}
      conf++;var row=document.querySelector('.row[data-i="'+i+'"]');row.classList.add("conflict");row.dataset.conf="1";
      if(nt!==c.note)document.getElementById("note"+i).value=nt;}
    BUSY=false;refresh();
    document.getElementById("undoimp").hidden=false;
    var fc=document.getElementById("fconf");fc.hidden=!conf;fc.textContent="Import conflicts ("+conf+")";
    pmsg("Imported: "+took+" row(s) taken from the file"+(notes?", "+notes+" note(s) added":"")+
         (conf?"; "+conf+" row(s) decided differently in both — yours kept, flagged orange":"; no conflicts")+".",true);};
  fr.readAsText(file);}
function undoImport(){var b=window._backup;if(!b){try{b=localStorage.getItem(LSK+"-backup");}catch(e){}}
  if(!b){pmsg("Nothing to undo.",false);return;}
  var s=JSON.parse(b);BUSY=true;for(var i=0;i<N;i++)if(s.rows[i])setRow(i,s.rows[i]);BUSY=false;
  document.querySelectorAll(".row.conflict").forEach(function(r){r.classList.remove("conflict");r.dataset.conf="0";});
  document.getElementById("fconf").hidden=true;document.getElementById("undoimp").hidden=true;
  refresh();pmsg("Import undone — your progress is back as it was.",true);}
function doExport(){var s=state();var miss=[];for(var i=0;i<N;i++)if(!decided(i))miss.push(i);
  var m1=document.getElementById("msg"),m2=document.getElementById("msg2");
  if(miss.length){m1.style.color=m2.style.color="#b23b3b";
    m1.textContent=m2.textContent=miss.length+" row(s) still need a decision — the 'Needs a decision' filter shows them";
    document.querySelectorAll(".fbtn").forEach(function(b){b.classList.toggle("on",b.dataset.f==="und");});
    applyFilter("und");return;}
  var pr=problems(s);
  if(pr.length){m1.style.color=m2.style.color="#b23b3b";
    m1.textContent=m2.textContent=pr.length+" row(s) to fix before export — "+pr.slice(0,3).map(function(p){return p[1];}).join(" · ");
    var bad={};pr.forEach(function(p){bad[p[0]]=1;});
    document.querySelectorAll(".row[data-i]").forEach(function(r){r.style.display=bad[+r.dataset.i]?"":"none";});return;}
  var rows=META.map(function(m){var r=s.rows[m.i];var fin=Object.assign({},r);
    if(fin.kind!=="alias")fin.target="";if(fin.kind==="alias"||fin.kind==="exclude"||fin.kind==="unidentified"){fin.slug="";fin.display="";fin.cls="";}
    var pf={kind:m.prefill_kind,cls:m.prefill_class,id:m.prefill_id,display:m.prefill_display,note:m.prefill_note,check:m.check};
    var brandish=(fin.kind==="brand"||fin.kind==="retailer"||fin.kind==="both");
    var changed=(fin.kind!==pf.kind)||((fin.kind==="alias")?(fin.target!==pf.id):
      (brandish?((!!pf.cls&&fin.cls!==pf.cls)||(fin.slug!==pf.id)):false));
    var completed=(!changed&&brandish&&!pf.cls&&!!fin.cls);
    return Object.assign({i:m.i,surface:m.example_surface,surface_folded:m.surface_folded},fin,
                         {prefill:pf,changed_from_prefill:changed,completed_by_authors:completed});});
  var out={task:"N1 expansion alias decisions",prefill:"__PREFILL_NOTE__",exported_at:new Date().toISOString(),
           n:rows.length,changed_from_prefill:rows.filter(function(r){return r.changed_from_prefill;}).length,
           completed_by_authors:rows.filter(function(r){return r.completed_by_authors;}).length,decisions:rows};
  var a=document.createElement("a");
  a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{type:"application/json"}));
  a.download="EXPANSION-ALIAS-DECISIONS.json";document.body.appendChild(a);a.click();a.remove();
  m1.style.color=m2.style.color="#2e7d32";m1.textContent=m2.textContent="Exported — send back EXPANSION-ALIAS-DECISIONS.json";}
function applyFilter(f){document.querySelectorAll(".row[data-i]").forEach(function(r){var i=+r.dataset.i,show=true;
  if(f==="und")show=!decided(i);else if(f==="chk")show=r.dataset.chk==="1";else if(f==="ret")show=r.dataset.ret==="1";
  else if(f==="exc")show=r.dataset.pk==="exclude";else if(f==="ali")show=r.dataset.pk==="alias";
  else if(f==="conf")show=r.dataset.conf==="1";
  r.style.display=show?"":"none";});}
document.querySelectorAll(".fbtn[data-f]").forEach(function(b){b.onclick=function(){
  document.querySelectorAll(".fbtn[data-f]").forEach(function(x){x.classList.remove("on");});
  b.classList.add("on");applyFilter(b.dataset.f);};});
document.addEventListener("change",refresh);document.addEventListener("input",save);
document.getElementById("impf").addEventListener("change",function(e){var f=e.target.files[0];if(f)importProgress(f);e.target.value="";});
(function(){DRAFT=state();var s=null,t=null;
 try{s=JSON.parse(localStorage.getItem(LSK)||"null");t=localStorage.getItem(LSK+"-t");}catch(e){}
 if(s&&s.rows){BUSY=true;for(var i=0;i<N;i++){var o=s.rows[i];if(!o)continue;setRow(i,o);}BUSY=false;}
 refresh();
 if(s&&s.rows)document.getElementById("saved").textContent="progress restored from this browser"+
   (t?" (last saved "+hhmm(new Date(t))+")":"");})();
</script></body></html>"""

fkeys = json.dumps(alias_map, ensure_ascii=False, sort_keys=True)
review_id = hashlib.sha256("\n".join(c["surface_folded"] for c in cand).encode("utf-8")).hexdigest()[:16]
exist = json.dumps({c: 1 for c in sorted(existing)}, sort_keys=True)
page = (PAGE.replace("__FKEYS__", fkeys).replace("__EXIST__", exist).replace("__CARDS__", cards).replace("__CANON__", canon_opts)
        .replace("__BRANDS__", table_rows(brands, "aliases")).replace("__RETAIL__", table_rows(retail, None))
        .replace("__NB__", str(len(brands))).replace("__NR__", str(len(retail)))
        .replace("__META__", meta).replace("__PREFILL_NOTE__", PREFILL_NOTE).replace("__REVIEW_ID__", review_id)
        .replace("__N__", str(N)))
with open(W / "EXPANSION-ALIAS-REVIEW.html", "w", encoding="utf-8", newline="\n") as f:
    f.write(page)
print(f"candidates: {N} (derived from the gated exports; draft joined from EXPANSION-ALIAS-PREFILL.csv)")
print(f"draft: {dict(Counter(c['prefill_kind'] for c in cand))} | CHECK {sum(1 for c in cand if c['check'])} | "
      f"open class {sum(1 for c in cand if c['prefill_kind'] in ('brand','retailer','both') and not c['prefill_class'])}")
for f in ("EXPANSION-ALIAS-PREFILL.csv", "EXPANSION-ALIAS-CANDIDATES.csv", "EXPANSION-ALIAS-REVIEW.html"):
    print(f"{f}  sha256 {sha(W / f)}")
