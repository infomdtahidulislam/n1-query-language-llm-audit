#!/usr/bin/env python3
"""Build LABEL-ROUND1-R1/R2/R3.html (N1 Round 1 / E.4, 13 Sep 2026).

108 pilot answers (6 per model-arm cell, one per calibration query, seed 20260913,
shuffled), blind: no model, no arm, no selection reason. Each rater labels
every D.2 field + comments; Export writes LABEL-PRACTICE-<rater>-labels.json.
Self-contained, no external resources. Identical content across raters; only the
rater code, storage key and export name differ."""
# NOTE (added 17 Sep 2026, documentation only — the instrument itself is untouched): this
# script was executed in the authors' cloud workspace, so `U` below points at that copy of
# runs/responses/pilot. It is kept in the study folder as the record of how the Round 1
# labelling pages were produced, and because build_label_round2.py reads the page TEMPLATE
# out of it (and refuses to build unless the template's sha256 still matches).

import csv, glob, html, json, os

U = "/mnt/user-data/uploads/New Experiment/runs/responses/pilot"
import random
sel = json.load(open("round1_selection.json"))
rng = random.Random(20260913)
rng.shuffle(sel)                       # cell-ordered -> shuffled so nothing groups by model/arm
rows = []
for n, r in enumerate(sel, 1):
    rows.append(dict(pid=f"I{n:03d}", **r))
assert len(rows) == 108
import csv as _csv
with open("ROUND1-MAPPING-authors-only.csv", "w", newline="", encoding="utf-8") as f:
    w = _csv.DictWriter(f, fieldnames=list(rows[0].keys()) + ["shuffle_seed"])
    w.writeheader()
    for r in rows: w.writerow(dict(r, shuffle_seed=20260913))
files = {os.path.basename(f).rsplit("_", 1)[1][:-5]: f for f in glob.glob(os.path.join(U, "*", "*.json"))}
for r in rows:
    d = json.load(open(files[r["key"][:12]], encoding="utf-8"))
    assert d["key"] == r["key"]
    r["_answer"] = d["meta"]["content"]

LANGS = ["bn", "banglish", "en", "mixed", "other"]

def card(r):
    pid = r["pid"]
    lang_opts = "".join(
        f'<label class="opt"><input type="radio" name="lang_{pid}" value="{c}"> {c}</label>' for c in LANGS)
    ref_opts = "".join(
        f'<label class="opt"><input type="radio" name="ref_{pid}" value="{v}"> {t}</label>'
        for v, t in [("false", "answered / recommended something"), ("true", "refused everything")])
    return f"""
<div class="card" id="card_{pid}">
  <div class="card-head"><span class="pid">{pid}</span><span class="status" id="st_{pid}">not started</span></div>
  <div class="answer">{html.escape(r["_answer"])}</div>
  <div class="fields">
    <label class="f"><span>Brands <small>(one per line — every brand named, positive or negative)</small></span>
      <textarea id="brands_{pid}" rows="3" placeholder="one brand per line"></textarea></label>
    <label class="f"><span>Recommended <small>(only the ones it advises buying; must also be in Brands)</small></span>
      <textarea id="rec_{pid}" rows="2" placeholder="one per line — leave empty if it recommends nothing specific"></textarea></label>
    <label class="f"><span>Prices <small>(one per line as: amount currency — e.g. <code>38000 BDT</code>, <code>500 USD</code>, <code>20000 unstated</code>)</small></span>
      <textarea id="prices_{pid}" rows="2" placeholder="one price per line — leave empty if none"></textarea></label>
    <label class="f"><span>Retailers <small>(named shops/marketplaces only — one per line)</small></span>
      <textarea id="ret_{pid}" rows="2" placeholder="one per line — leave empty if none"></textarea></label>
    <div class="f"><span>Refused?</span><div class="opts">{ref_opts}</div></div>
    <div class="f"><span>Answer language <small>(judged on the sentences, not brand names or prices)</small></span><div class="opts">{lang_opts}</div></div>
    <label class="f"><span>Comments <small>(anything that was hard to judge — flag, don't guess silently)</small></span>
      <input type="text" id="cmt_{pid}" maxlength="600" placeholder="optional — but please note anything borderline"></label>
  </div>
</div>"""

ids = [r["pid"] for r in rows]
cards = "".join(card(r) for r in rows)

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>N1 labelling — Round 1 — __RATER__</title>
<style>
 :root{color-scheme:light}
 body{margin:0;padding:0 16px 90px;background:#f6f5f1;color:#1a1a1a;font:15px/1.55 "Segoe UI",system-ui,sans-serif}
 .wrap{max-width:900px;margin:0 auto}
 h1{font-size:20px;margin:20px 0 4px} .sub{color:#555;margin:0 0 14px}
 .intro{background:#fff;border:1px solid #ddd;border-radius:8px;padding:14px 16px;margin:12px 0 18px}
 .intro b{color:#1a4d8f}
 .topbar{position:sticky;top:0;z-index:5;background:#f6f5f1ee;backdrop-filter:blur(2px);padding:8px 0;border-bottom:1px solid #ddd;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
 #prog{font-weight:700}
 .card{background:#fff;border:1px solid #ddd;border-radius:8px;margin:16px 0;overflow:hidden}
 .card.done{border-color:#7cb87c}
 .card-head{display:flex;justify-content:space-between;padding:8px 14px;background:#efece4;font-weight:700}
 .card.done .card-head{background:#e2efe2}
 .status{font-weight:400;color:#8a6d3b}.card.done .status{color:#2e7d32}
 .answer{padding:12px 16px;white-space:pre-wrap;word-wrap:break-word;font-size:16px;line-height:1.7;border-bottom:1px solid #eee;background:#fcfcfb}
 .fields{padding:12px 14px;display:flex;flex-direction:column;gap:11px}
 .f{display:flex;flex-direction:column;gap:4px}
 .f>span{font-weight:600}.f small{font-weight:400;color:#666}
 .f code{background:#eee;padding:0 3px;border-radius:3px}
 textarea,input[type=text]{width:100%;box-sizing:border-box;padding:7px 9px;border:1px solid #ccc;border-radius:6px;font:14px inherit;resize:vertical}
 .opts{display:flex;flex-wrap:wrap;gap:6px 12px}
 .opt{padding:4px 10px;border:1px solid #ccc;border-radius:16px;cursor:pointer;user-select:none;background:#fafafa}
 .opt:has(input:checked){background:#1a4d8f;color:#fff;border-color:#1a4d8f}
 .opt input{accent-color:#1a4d8f;margin-right:4px}
 button.export{background:#1a4d8f;color:#fff;border:0;border-radius:6px;padding:9px 18px;font:700 15px inherit;cursor:pointer}
 button.export:hover{background:#153e73}
 #msg,#msg2{font-weight:600}
 .foot{margin:26px 0;text-align:center}
</style></head><body><div class="wrap">
<h1>Labelling — Round 1</h1>
<p class="sub">Rater __RATER__ · 108 answers · this round COUNTS — work carefully, take breaks, your progress saves in this browser</p>
<div class="intro">
 <p>For each answer, record the commercial content it contains — <b>describe what is on the page, don't judge it</b>.
 Read the codebook first; it defines every field. The short version:</p>
 <p><b>Brands</b> — every brand named (even ones advised against). <b>Recommended</b> — only the ones it advises
 <i>buying</i> (a subtle line; a brand merely compared is not recommended). <b>Prices</b> — amounts attached to a
 product, one per line as <code>amount currency</code>, Bangla digits and "50k"/"লাখ" converted; not the user's own
 budget. <b>Retailers</b> — named shops only. <b>Refused</b> — true only if it declines entirely and names nothing.
 <b>Language</b> — judged on the sentences, not brand names; embedded English words don't make it <i>mixed</i>.</p>
 <p>Work alone, no AI tools. If anything is borderline, make your call and <b>note it in Comments — flag, don't guess
 silently</b>. Your progress saves in this browser automatically; on top of that, press <b>Save progress</b> any time to
 download <code>LABEL-ROUND1-__RATER__-progress.json</code> — keep it as your backup — and <b>Import progress</b> loads it
 back so you can continue on any computer or after a break (Import accepts only <i>your own</i> file). If you made test
 entries while trying the page out, <b>Clear all fields</b> wipes everything (it asks first) so you can Import cleanly. When all 108 are
 done, press <b>Export labels</b> and send back the final <code>LABEL-ROUND1-__RATER__-labels.json</code>.</p>
</div>
<div class="topbar"><span id="prog">0 / 108 done</span>
 <button class="export" onclick="doExport()">Export labels</button>
 <button class="export" style="background:#fff;color:#1a4d8f;border:1px solid #1a4d8f" onclick="doSaveProgress()">Save progress</button>
 <button class="export" style="background:#fff;color:#1a4d8f;border:1px solid #1a4d8f" onclick="document.getElementById('impfile').click()">Import progress</button>
 <button class="export" style="background:#fff;color:#b23b3b;border:1px solid #b23b3b" onclick="doClearAll()">Clear all fields</button>
 <input type="file" id="impfile" accept=".json,application/json" hidden>
 <span id="msg"></span></div>
__CARDS__
<div class="foot"><button class="export" onclick="doExport()">Export labels</button> <button class="export" style="background:#fff;color:#1a4d8f;border:1px solid #1a4d8f" onclick="doSaveProgress()">Save progress</button><div id="msg2" style="margin-top:8px"></div></div>
</div>
<script>
var IDS=__IDS__, RATER="__RATER__", LSK="n1-label-round1-"+RATER;
function lines(id){return document.getElementById(id).value.split("\n").map(function(s){return s.trim()}).filter(Boolean);}
function radio(n){var el=document.querySelector('input[name="'+n+'"]:checked');return el?el.value:"";}
function state(){var s={};IDS.forEach(function(p){s[p]={
  brands:lines("brands_"+p),recommended:lines("rec_"+p),prices:lines("prices_"+p),
  retailers:lines("ret_"+p),refused:radio("ref_"+p),answer_language:radio("lang_"+p),
  comments:document.getElementById("cmt_"+p).value.trim()};});return s;}
function done1(o){return !!(o&&o.answer_language&&o.refused);}
function ndone(s){var n=0;IDS.forEach(function(p){if(done1(s[p]))n++;});return n;}
function applyState(s){IDS.forEach(function(p){var o=s[p]||{};
  document.getElementById("brands_"+p).value=(o.brands||[]).join("\n");
  document.getElementById("rec_"+p).value=(o.recommended||[]).join("\n");
  document.getElementById("prices_"+p).value=(o.prices||[]).join("\n");
  document.getElementById("ret_"+p).value=(o.retailers||[]).join("\n");
  document.querySelectorAll('input[name="ref_'+p+'"]').forEach(function(e){e.checked=(e.value===o.refused);});
  document.querySelectorAll('input[name="lang_'+p+'"]').forEach(function(e){e.checked=(e.value===o.answer_language);});
  document.getElementById("cmt_"+p).value=o.comments||"";});}
function refresh(){var s=state(),n=0;IDS.forEach(function(p){var d=done1(s[p]);if(d)n++;
  document.getElementById("card_"+p).classList.toggle("done",d);
  document.getElementById("st_"+p).textContent=d?"done":"not started";});
  document.getElementById("prog").textContent=n+" / 108 done";
  try{localStorage.setItem(LSK,JSON.stringify(s));}catch(e){}return n;}
function download(obj,name){var a=document.createElement("a");
  a.href=URL.createObjectURL(new Blob([JSON.stringify(obj,null,2)],{type:"application/json"}));
  a.download=name;document.body.appendChild(a);a.click();a.remove();}
function labelsArray(s){return IDS.map(function(p){return Object.assign({pid:p},s[p]);});}
function msg(text,ok){var m1=document.getElementById("msg"),m2=document.getElementById("msg2");
  m1.style.color=m2.style.color=ok?"#2e7d32":"#b23b3b";m1.textContent=m2.textContent=text;}
function doExport(){var s=state();var miss=IDS.filter(function(p){return !done1(s[p]);});
  if(miss.length){msg("Not finished — "+miss.length+" answer(s) still need language + refused (first: "+miss[0]+"). Use Save progress to keep partial work.",false);
    var el=document.getElementById("card_"+miss[0]);if(el)el.scrollIntoView({behavior:"smooth",block:"center"});return;}
  download({task:"N1 labelling round 1",rater:RATER,exported_at:new Date().toISOString(),
    labels:labelsArray(s)},"LABEL-ROUND1-"+RATER+"-labels.json");
  msg("Exported — send back LABEL-ROUND1-"+RATER+"-labels.json",true);}
function doSaveProgress(){var s=state();
  download({task:"N1 labelling round 1",rater:RATER,partial:true,done:ndone(s),
    saved_at:new Date().toISOString(),labels:labelsArray(s)},
    "LABEL-ROUND1-"+RATER+"-progress.json");
  msg("Progress saved ("+ndone(s)+" / 108 done) — keep that file; Import loads it back on any computer.",true);}
function doClearAll(){var cur=ndone(state());
  if(!confirm("This will ERASE everything on this page ("+cur+" / 108 done) and the browser's saved copy.\n\nIf any of this is real work, press Cancel and use Save progress first. Continue?"))return;
  applyState({});try{localStorage.removeItem(LSK);}catch(e){}refresh();
  msg("All fields cleared — 0 / 108. Import your progress file to continue, or start fresh.",true);}
function doImport(ev){var f=ev.target.files[0];ev.target.value="";if(!f)return;
  var rd=new FileReader();
  rd.onload=function(){try{var j=JSON.parse(rd.result);
    if(!j||typeof j!=="object"||!Array.isArray(j.labels)){msg("Import failed: not a labels/progress file.",false);return;}
    if((j.task||"").indexOf("N1 labelling round 1")!==0){msg("Import refused: that file is from a different task.",false);return;}
    if(j.rater!==RATER){msg("Import refused: that file belongs to rater "+j.rater+" — this page is "+RATER+"'s. Work only from your own file.",false);return;}
    var s={},inc=0;j.labels.forEach(function(o){if(o&&o.pid&&IDS.indexOf(o.pid)>=0){s[o.pid]=o;if(done1(o))inc++;}});
    if(!Object.keys(s).length){msg("Import failed: no matching answers in that file.",false);return;}
    var cur=ndone(state());
    if(cur>0&&!confirm("This will REPLACE what is currently on this page ("+cur+" / 108 done) with the file's contents ("+inc+" / 108 done). Continue?"))return;
    applyState(s);refresh();
    msg("Imported — "+ndone(state())+" / 108 done. Continue where you left off.",true);
  }catch(e){msg("Import failed: could not read that file ("+e.message+").",false);}};
  rd.readAsText(f);}
document.addEventListener("input",refresh);
document.addEventListener("change",function(e){if(e.target&&e.target.id==="impfile")return;refresh();});
document.getElementById("impfile").addEventListener("change",doImport);
(function(){try{var s=JSON.parse(localStorage.getItem(LSK)||"null");if(s)applyState(s);}catch(e){}refresh();})();
</script></body></html>"""

for rater in ["R1", "R2", "R3"]:
    page = (TEMPLATE.replace("__CARDS__", cards).replace("__IDS__", json.dumps(ids))
            .replace("__RATER__", rater))
    open(f"LABEL-ROUND1-{rater}.html", "w", encoding="utf-8").write(page)
    print(f"wrote LABEL-ROUND1-{rater}.html ({len(page)} bytes)")
