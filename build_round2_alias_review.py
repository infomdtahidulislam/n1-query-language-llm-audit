#!/usr/bin/env python3
"""Build ROUND2-ALIAS-REVIEW.html — the authors' round-2 verification tool for
round2_alias_candidates.csv (81 unknown surface forms from the pilot extraction + the three
Round-1 rater files; C.2 / v0.45 / v0.48).

Same instrument pattern as F2-ALIAS-REVIEW.html. Per-arm frequencies are deliberately NOT
shown (headquarters rule, not usage; Appendix C.3 blindness). Decisions export as
ROUND2-ALIAS-DECISIONS.json, from which the extended frozen brand_aliases.csv (and any
retailer additions) are built, re-hashed and registered."""
import csv, html, json, re

cand = list(csv.DictReader(open("round2_alias_candidates.csv", encoding="utf-8")))
brands = list(csv.DictReader(open("brand_aliases.csv", encoding="utf-8")))
retail = list(csv.DictReader(open("retailer_classification.csv", encoding="utf-8")))
canonicals = sorted({r["canonical_id"] for r in brands} | {r["canonical_id"] for r in retail})

def esc(s): return html.escape(s or "")
def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.casefold()).strip("-")
    return s or "entity"

items = []
for i, r in enumerate(cand):
    counts = []
    for lab, col in (("extractor", "n_extractor"), ("R1", "n_R1"), ("R2", "n_R2"), ("R3", "n_R3")):
        n = int(r[col])
        if n: counts.append(f"{lab} ×{n}")
    nsrc = len(r["sources"].split("+"))
    total = sum(int(r[c]) for c in ("n_extractor", "n_R1", "n_R2", "n_R3"))
    items.append(dict(
        i=i, key=r["surface_folded"], surface=r["example_surface"], field=r["seen_in_field"],
        counts=" · ".join(counts), nsrc=nsrc, total=total,
        extonly=(r["sources"] == "ext"), ratersonly=("ext" not in r["sources"].split("+")),
        isret=(r["seen_in_field"] == "retailers"),
        slug=slugify(r["example_surface"]), display=r["example_surface"]))

def table_rows(rows, alias_col):
    out = []
    for r in sorted(rows, key=lambda x: x["canonical_id"]):
        al = esc(r.get(alias_col, "")) if alias_col else ""
        out.append(f"<tr><td><code>{esc(r['canonical_id'])}</code></td><td>{esc(r['display_name'])}</td>"
                   f"<td>{esc(r['class'])}</td><td class='al'>{al}</td></tr>")
    return "".join(out)

brand_rows = table_rows(brands, "aliases")
ret_rows = table_rows(retail, None)

def card(it):
    i = it["i"]
    folded = f' <span class="meta">(folds to <code>{esc(it["key"])}</code>)</span>' if it["key"] != it["surface"].casefold() else ""
    badge = f'<span class="b {"ok" if it["nsrc"] >= 3 else ("info" if it["nsrc"] == 2 else "new")}">seen by {it["nsrc"]}/4</span>'
    fl = '<span class="b warn">retailer field</span>' if it["isret"] else ""
    return f"""
<div class="row" data-i="{i}" data-nsrc="{it['nsrc']}" data-extonly="{int(it['extonly'])}"
     data-ronly="{int(it['ratersonly'])}" data-ret="{int(it['isret'])}">
 <div class="rh">
   <span class="forms">{esc(it['surface'])}</span>{folded}
   <span class="meta">seen in {esc(it['field'])} · {esc(it['counts'])}</span>
   {badge} {fl}
   <span class="st" id="st{i}">undecided</span>
 </div>
 <div class="rb">
  <div class="kind">
    <label><input type="radio" name="k{i}" value="brand"> Brand</label>
    <label><input type="radio" name="k{i}" value="retailer"> Retailer</label>
    <label><input type="radio" name="k{i}" value="both"> Brand + retailer</label>
    <label><input type="radio" name="k{i}" value="alias"> Alias of existing →</label>
    <label><input type="radio" name="k{i}" value="exclude"> Not a brand (exclude)</label>
  </div>
  <div class="detail">
    <span class="cls" id="cls{i}" hidden>
      <label><input type="radio" name="c{i}" value="local"> local</label>
      <label><input type="radio" name="c{i}" value="global"> global</label>
      <label><input type="radio" name="c{i}" value="ambiguous"> ambiguous</label>
    </span>
    <input class="tgt" id="tgt{i}" list="canon" placeholder="canonical id it maps to" hidden>
    <span class="ids" id="ids{i}" hidden>
      <input class="slug" id="slug{i}" value="{esc(it['slug'])}" title="canonical_id">
      <input class="disp" id="disp{i}" value="{esc(it['display'])}" title="display_name">
    </span>
    <input class="note" id="note{i}" placeholder="note (optional)">
  </div>
 </div>
</div>"""

N = len(items)
cards = "".join(card(it) for it in items)
canon_opts = "".join(f'<option value="{esc(c)}">' for c in canonicals)

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Round 2 — alias table verification</title>
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
 .b{font-size:11px;font-weight:700;border-radius:9px;padding:2px 8px;letter-spacing:.02em}
 .b.new{background:#fde8d7;color:#9a4b00}.b.ok{background:#e2efe2;color:#2e6b2e}
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
 .addbox{background:#fff;border:1px dashed #999;border-radius:8px;padding:10px 14px;margin:14px 0}
 .foot{margin:24px 0;text-align:center}#msg,#msg2{font-weight:600;color:#2e7d32}
</style></head><body><div class="wrap">
<h1>Round 2 — alias table verification</h1>
<p class="sub">Authors only · __N__ unknown surface forms from the pilot (extractor + all three raters) · your decisions extend the frozen <code>brand_aliases.csv</code>, which is then re-hashed and registered</p>

<div class="instr">
<h3>What this is</h3>
<p>The registered round-2 check (C.2, prereg v0.45/v0.48). Every brand/retailer surface form that appeared in
the pilot — in the extractor's output over all 324 answers, or in any of the three raters' Round-1 files —
and does not resolve to the current frozen table. You two decide what each one is; I extend
<code>brand_aliases.csv</code> from your export, re-hash it, register the change, and then re-run the Round-1
set metrics and the E.6 gate on the extended table — those become the reported numbers.</p>

<h3>The five decisions (one per row)</h3>
<p><b>Brand</b> — a real brand not yet in the table: it gets its own row. Check the suggested
<code>canonical_id</code> and display name, fix if wrong. &nbsp;<b>Retailer</b> — a named shop, marketplace or
showroom chain (goes to the retailer table for RQ4). &nbsp;<b>Brand + retailer</b> — sells mainly its own
products in its own stores. &nbsp;<b>Alias of existing</b> — a spelling or variant of something already in the
table: pick the canonical it maps to (browse the two panels below; the box autocompletes every existing id).
&nbsp;<b>Not a brand (exclude)</b> — generic words, product lines you judge out of scope, regulators
(central banks and telecom authorities are not commercial brands unless you decide otherwise). Excluding is a
real decision, not a failure.</p>

<div class="rulebox"><b>Class — Appendix C.1, verbatim rule:</b> a brand is <b>local</b> if its owning company is
headquartered in Bangladesh; otherwise <b>global</b>. Joint ventures, BD-assembled foreign brands, and
multinational subsidiaries with substantial local identity get <b>ambiguous</b> — don't agonize:
RQ2 is computed three ways (ambiguous local / global / excluded), so <b>ambiguous is a safe, registered
answer</b>, documented one-by-one. The same classes apply to retailers for RQ4.</div>

<h3>How to work through __N__ rows quickly</h3>
<p><b>1.</b> <b>Seen by 4/4</b> rows first — the extractor and all three raters recorded them, so they are
almost certainly real entities; most need only a class. <b>2.</b> <b>Extractor only</b> rows deserve a harder
look — no rater wrote them, so check whether it is a real entity or extractor noise. <b>3.</b> Rows tagged
<b>retailer field</b> were recorded as shops — usually a Retailer decision. <b>4.</b> Spelling variants of
things already in the table are <b>Alias of existing</b> merges. <b>5.</b> Frequencies by arm are deliberately
not shown: classify by the headquarters rule, never by how often or where something was mentioned.</p>

<h3>Don't spend time on</h3>
<p>Case, accents, possessive suffixes, and trailing "(EBL)"-style acronyms — folded automatically when I build
the table. Perfect display names — I normalise. Duplicate spellings across rows — merges collapse them.</p>

<h3>Anything missing?</h3>
<p>If you know a brand or shop that will matter in the main run's 250 queries but never appeared here, add it
at the bottom (<b>Add an entity</b>). Market knowledge is a registered source for this table.</p>

<h3>When you're done</h3>
<p>Every row decided (the counter says so) → <b>Export decisions</b> → send me
<code>ROUND2-ALIAS-DECISIONS.json</code>. Work through it together or split halves — one export either way;
progress saves in this browser.</p>
</div>

<details class="starter"><summary><b>Already in the brand table</b> — __NB__ entities (browse before "Alias of existing"; the box in each row autocompletes these ids)</summary>
<table><tr><th>canonical_id</th><th>display name</th><th>class</th><th>aliases</th></tr>__BRANDS__</table>
</details>
<details class="starter"><summary><b>Already in the retailer table</b> — __NR__ retailers (RQ4)</summary>
<table><tr><th>canonical_id</th><th>display name</th><th>class</th><th></th></tr>__RETAIL__</table>
</details>

<div class="topbar">
  <span id="prog">0 / __N__ decided</span>
  <button class="fbtn on" data-f="all">All</button>
  <button class="fbtn" data-f="all4">Seen by 4/4</button>
  <button class="fbtn" data-f="multi">2–3 sources</button>
  <button class="fbtn" data-f="extonly">Extractor only</button>
  <button class="fbtn" data-f="ronly">Raters only</button>
  <button class="fbtn" data-f="ret">Retailer field</button>
  <button class="fbtn" data-f="und">Undecided</button>
  <button class="exp" onclick="doExport()">Export decisions</button><span id="msg"></span>
</div>
<datalist id="canon">__CANON__</datalist>
__CARDS__
<div class="addbox"><b>Add an entity that never appeared in the pilot</b><br>
 <div id="adds"></div>
 <button class="fbtn" onclick="addRow()">+ Add an entity</button></div>
<div class="foot"><button class="exp" onclick="doExport()">Export decisions</button><div id="msg2" style="margin-top:6px"></div></div>
</div>
<script>
var N=__N__, LSK="n1-round2-alias-review";
function kind(i){var e=document.querySelector('input[name="k'+i+'"]:checked');return e?e.value:"";}
function cls(i){var e=document.querySelector('input[name="c'+i+'"]:checked');return e?e.value:"";}
function decided(i){var k=kind(i);if(!k)return false;
  if(k==="alias")return !!document.getElementById("tgt"+i).value.trim();
  if(k==="exclude")return true;return !!cls(i);}
function refresh(){var n=0;for(var i=0;i<N;i++){var k=kind(i);
  document.getElementById("cls"+i).hidden=!(k==="brand"||k==="retailer"||k==="both");
  document.getElementById("tgt"+i).hidden=(k!=="alias");
  document.getElementById("ids"+i).hidden=!(k==="brand"||k==="retailer"||k==="both");
  var d=decided(i);if(d)n++;
  var row=document.querySelector('.row[data-i="'+i+'"]');row.classList.toggle("done",d);
  document.getElementById("st"+i).textContent=d?(kind(i)+(cls(i)?" \\u00b7 "+cls(i):"")):"undecided";}
  document.getElementById("prog").textContent=n+" / "+N+" decided";save();return n;}
function state(){var s={rows:{},adds:[]};for(var i=0;i<N;i++){s.rows[i]={kind:kind(i),cls:cls(i),
  target:document.getElementById("tgt"+i).value.trim(),slug:document.getElementById("slug"+i).value.trim(),
  display:document.getElementById("disp"+i).value.trim(),note:document.getElementById("note"+i).value.trim()};}
  document.querySelectorAll("#adds .arow").forEach(function(a){s.adds.push({
    name:a.querySelector(".an").value.trim(),kind:a.querySelector(".ak").value,
    cls:a.querySelector(".ac").value,slug:a.querySelector(".as").value.trim(),
    aliases:a.querySelector(".aa").value.trim(),note:a.querySelector(".ano").value.trim()});});return s;}
function save(){try{localStorage.setItem(LSK,JSON.stringify(state()));}catch(e){}}
function addRow(d){d=d||{};var div=document.createElement("div");div.className="arow";
  div.style.cssText="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0";
  div.innerHTML='<input class="an" placeholder="name" value="'+(d.name||"")+'" style="width:170px">'+
   '<select class="ak"><option>brand</option><option>retailer</option><option>both</option></select>'+
   '<select class="ac"><option>local</option><option>global</option><option>ambiguous</option></select>'+
   '<input class="as" placeholder="canonical_id" value="'+(d.slug||"")+'" style="width:150px">'+
   '<input class="aa" placeholder="aliases (| separated)" value="'+(d.aliases||"")+'" style="width:210px">'+
   '<input class="ano" placeholder="note" value="'+(d.note||"")+'" style="flex:1;min-width:140px">';
  ["ak","ac"].forEach(function(c){if(d[c==="ak"?"kind":"cls"])div.querySelector("."+c).value=d[c==="ak"?"kind":"cls"];});
  div.querySelectorAll("input,select").forEach(function(e){e.addEventListener("input",save);});
  document.getElementById("adds").appendChild(div);}
function doExport(){var s=state();var miss=[];for(var i=0;i<N;i++)if(!decided(i))miss.push(i);
  var m1=document.getElementById("msg"),m2=document.getElementById("msg2");
  if(miss.length){m1.style.color=m2.style.color="#b23b3b";
    m1.textContent=m2.textContent=miss.length+" row(s) still undecided — the Undecided filter shows them";
    document.querySelectorAll(".fbtn").forEach(function(b){b.classList.toggle("on",b.dataset.f==="und");});
    applyFilter("und");return;}
  var rows=[];document.querySelectorAll(".row[data-i]").forEach(function(r){var i=+r.dataset.i;
    rows.push(Object.assign({surface:r.querySelector(".forms").textContent,i:i},s.rows[i]));});
  var out={task:"N1 round-2 alias decisions",exported_at:new Date().toISOString(),
           decisions:rows,additions:s.adds.filter(function(a){return a.name;})};
  var a=document.createElement("a");
  a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{type:"application/json"}));
  a.download="ROUND2-ALIAS-DECISIONS.json";document.body.appendChild(a);a.click();a.remove();
  m1.style.color=m2.style.color="#2e7d32";m1.textContent=m2.textContent="Exported — send back ROUND2-ALIAS-DECISIONS.json";}
function applyFilter(f){document.querySelectorAll(".row[data-i]").forEach(function(r){var i=+r.dataset.i,show=true;
  if(f==="all4")show=r.dataset.nsrc==="4";else if(f==="multi")show=(r.dataset.nsrc==="2"||r.dataset.nsrc==="3");
  else if(f==="extonly")show=r.dataset.extonly==="1";else if(f==="ronly")show=r.dataset.ronly==="1";
  else if(f==="ret")show=r.dataset.ret==="1";else if(f==="und")show=!decided(i);
  r.style.display=show?"":"none";});}
document.querySelectorAll(".fbtn[data-f]").forEach(function(b){b.onclick=function(){
  document.querySelectorAll(".fbtn[data-f]").forEach(function(x){x.classList.remove("on");});
  b.classList.add("on");applyFilter(b.dataset.f);};});
document.addEventListener("change",refresh);document.addEventListener("input",save);
(function(){var s=null;try{s=JSON.parse(localStorage.getItem(LSK)||"null");}catch(e){}
 if(s){for(var i=0;i<N;i++){var o=s.rows[i];if(!o)continue;
   if(o.kind){var e=document.querySelector('input[name="k'+i+'"][value="'+o.kind+'"]');if(e)e.checked=true;}
   if(o.cls){var c=document.querySelector('input[name="c'+i+'"][value="'+o.cls+'"]');if(c)c.checked=true;}
   document.getElementById("tgt"+i).value=o.target||"";
   if(o.slug)document.getElementById("slug"+i).value=o.slug;
   if(o.display)document.getElementById("disp"+i).value=o.display;
   document.getElementById("note"+i).value=o.note||"";}
  (s.adds||[]).forEach(addRow);}refresh();})();
</script></body></html>"""

page = (PAGE.replace("__CARDS__", cards).replace("__CANON__", canon_opts)
        .replace("__BRANDS__", brand_rows).replace("__RETAIL__", ret_rows)
        .replace("__NB__", str(len(brands))).replace("__NR__", str(len(retail)))
        .replace("__N__", str(N)))
open("ROUND2-ALIAS-REVIEW.html", "w", encoding="utf-8").write(page)
import os
print(f"wrote ROUND2-ALIAS-REVIEW.html {os.path.getsize('ROUND2-ALIAS-REVIEW.html')} bytes | {N} rows | "
      f"canon datalist {len(canonicals)} ids")
