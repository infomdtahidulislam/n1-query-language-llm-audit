#!/usr/bin/env python3
"""build_bd_assembly_check.py — N1: the authors' review page for the post-hoc C.1 sensitivity (record of 28 Sep 2026).

Frozen Appendix C.1 names joint ventures, BD-assembled foreign brands and multinational subsidiaries with substantial
local identity as `ambiguous` cases; the frozen classification file and the run of record class such foreign brands
`global` (C.5's definition: ambiguous = contested or mixed ownership). The declared sensitivity re-runs RQ2 with the
C.1 reading applied. This page lists every entity classed global in brand_aliases.expansion.csv that has at least
five mentions in the human layer's primary analysis set (EXPANSION-ANALYSIS-SET-v2.jsonl, arms en/bn/bl), in
alphabetical order, WITHOUT counts, per Appendix C.3. The authors decide each row together, with a public source for
every row that is not "stays global", and export BD-ASSEMBLY-CHECK-decisions.json; the frozen table is never touched.
The draft column repeats, verbatim, the evidence the authors' writing assistant gathered on 28 Sep 2026; it decides nothing.

Usage: python build_bd_assembly_check.py  ->  BD-ASSEMBLY-CHECK.html (node --check gates the script)
"""
import csv, collections, hashlib, json, re, subprocess, tempfile
from pathlib import Path

W = Path(".")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
MIN_MENTIONS = 5
with open(W / "brand_aliases.expansion.csv", encoding="utf-8", newline="") as fh:
    tab = {r["canonical_id"]: r for r in csv.DictReader(fh)}
with open(W / "EXPANSION-ANALYSIS-SET-v2.jsonl", encoding="utf-8") as fh:
    rows = [json.loads(l) for l in fh]
prim = [r for r in rows if r["in_primary_set"] and r["arm"] in ("en", "bn", "bl")]
cnt = collections.Counter(e for r in prim for e in r["brands"])
glob = {e: n for e, n in cnt.items() if tab.get(e, {}).get("class") == "global"}
sel = sorted(e for e, n in glob.items() if n >= MIN_MENTIONS)
covered = sum(glob[e] for e in sel) / sum(glob.values())

DRAFT = {  # verbatim from the writing assistant's message of 28 Sep 2026 (E:\Experiment 3 journal paper\08-INTEGRITY\BD-ASSEMBLY-EVIDENCE.csv)
    "honda": "joint venture — Bangladesh Honda: Honda 70%, BSEC 30%", "hero": "joint venture — HMCL Niloy Bangladesh: Hero 55%",
    "tvs": "joint venture — TVS Auto Bangladesh, with Rangs' REL Motors",
    "samsung": "assembled locally — Fair Electronics; Excel Telecom", "xiaomi": "assembled locally — DBG Technology BD",
    "oppo": "assembled locally — Benli Electronic", "realme": "assembled locally — Benli Electronic", "oneplus": "assembled locally — Benli Electronic",
    "vivo": "assembled locally — Best Tycoon BD", "tecno": "assembled locally — ISMARTU Technology BD", "infinix": "assembled locally — ISMARTU Technology BD",
    "itel": "assembled locally — ISMARTU Technology BD", "motorola": "assembled locally — Edison Industries, announced 2023",
    "bajaj": "assembled locally — Uttara Motors", "yamaha": "assembled locally — ACI Motors", "suzuki": "assembled locally — Rancon Motorbikes",
    "apple": "imported, stays global", "google": "imported, stays global", "kawasaki": "imported, stays global", "harley-davidson": "imported, stays global",
    "lenovo": "imported, stays global", "hp": "imported, stays global", "dell": "imported, stays global", "asus": "imported, stays global", "acer": "imported, stays global",
    "lg": "not yet checked", "sony": "not yet checked", "haier": "not yet checked", "gree": "not yet checked", "tcl": "not yet checked", "midea": "not yet checked",
    "daikin": "not yet checked", "hisense": "not yet checked", "panasonic": "not yet checked", "general": "not yet checked", "sharp": "not yet checked",
    "ponds": "not yet checked (Unilever Bangladesh)", "vaseline": "not yet checked (Unilever Bangladesh)"}
DATA = [{"id": e, "name": tab[e]["display_name"], "aliases": tab[e]["aliases"], "draft": DRAFT.get(e, "")} for e in sel]
TAB_SHA, SET_SHA = sha(W / "brand_aliases.expansion.csv"), sha(W / "EXPANSION-ANALYSIS-SET-v2.jsonl")
OPTIONS = [("global", "foreign brand, imported or sold through a distributor — stays global"),
           ("jv", "joint venture with a Bangladeshi company"),
           ("assembled", "made or assembled in Bangladesh (own plant or contract assembler)"),
           ("subsidiary", "sold by a multinational's Bangladesh subsidiary with substantial local identity"),
           ("unsure", "not sure — stays global in the sensitivity, say why")]
RULE = ("Frozen Appendix C.1: a brand is <b>local</b> if its owning company is headquartered in Bangladesh, otherwise <b>global</b>; "
        "<b>ambiguous</b> cases — joint ventures, BD-assembled foreign brands, multinational subsidiaries with substantial local identity "
        "(Robi/Axiata, Grameenphone/Telenor, Singer BD/Arçelik) — receive the label ambiguous. The frozen classification file and the run of "
        "record classed the brands below global; this page decides, for the declared sensitivity only, which of them fall under C.1's "
        "ambiguous cases. Decide from public facts about the brand in Bangladesh as of 2026, not from anything the models said. "
        "<b>A source (URL or publication) is required for every answer other than 'stays global'.</b> Brands you mark are treated as "
        "ambiguous in the sensitivity; nothing changes in the registered results or in any table.")

data_js = json.dumps(DATA, ensure_ascii=False).replace("</", "<\\/")
opts_js = json.dumps(OPTIONS, ensure_ascii=False).replace("</", "<\\/")
page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>N1 — C.1 sensitivity: brands to review</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f6f4ef;color:#1d1d1d}}
.wrap{{max-width:1280px;margin:0 auto;padding:18px 16px 60px}}
h1{{font-size:20px;margin:0 0 6px}} .sub{{color:#555;font-size:14px;margin:0 0 12px}}
.rule{{background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px 14px;font-size:14px;line-height:1.5;margin:0 0 14px}}
.bar{{position:sticky;top:0;background:#f6f4ef;padding:8px 0;border-bottom:1px solid #ddd;margin:0 0 10px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:14px;z-index:2}}
.bar button{{padding:6px 12px;border-radius:8px;border:1px solid #999;background:#fff;cursor:pointer;font-size:14px}}
.bar button.primary{{background:#1f5f3a;color:#fff;border-color:#1f5f3a}} .bar button:disabled{{opacity:.45;cursor:not-allowed}}
#count{{font-weight:600}} #msg{{color:#555}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}}
th,td{{border:1px solid #e3e0d8;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f0eee8}}
td.al{{color:#555;font-size:12px;max-width:260px;word-break:break-word}}
td.dr{{color:#7a5a00;font-size:12px;max-width:220px}}
td.ch label{{display:block;margin:0 0 3px;cursor:pointer;white-space:nowrap}}
tr.done td{{background:#f7fbf7}} tr.amb td{{background:#fff7e6}} tr.need td{{background:#fdeaea}}
input.src,input.note{{width:100%;box-sizing:border-box;font-size:12px;padding:4px 6px;border:1px solid #ccc;border-radius:6px}}
.foot{{font-size:12px;color:#666;margin-top:18px}}
</style></head><body><div class="wrap">
<h1>N1 — post-hoc C.1 sensitivity: which foreign brands are Bangladeshi joint ventures, assembled in Bangladesh, or sold by a local subsidiary?</h1>
<p class="sub">28 Sep 2026 · {len(DATA)} brands (every global entity with ≥ {MIN_MENTIONS} mentions in the human layer's primary set, alphabetical, no counts shown) · both authors decide together · export when every row is answered</p>
<div class="rule">{RULE}<br><br><b>How:</b> for each brand pick one option; type the source for every non-global answer (the export is blocked while a source is missing — red rows); the draft column is the writing assistant's evidence and decides nothing. Progress saves itself in this browser; <b>Save progress</b> downloads a backup you can <b>Import</b> on another computer. When done press <b>Export decisions</b> and send back <code>BD-ASSEMBLY-CHECK-decisions.json</code> unchanged.</div>
<div class="bar"><span id="count">0 / {len(DATA)} answered</span><span id="need"></span>
<button onclick="saveProgress()">Save progress</button>
<label><button onclick="document.getElementById('imp').click()">Import progress</button><input id="imp" type="file" accept="application/json" style="display:none" onchange="importProgress(this)"></label>
<button id="exp" class="primary" onclick="exportDecisions()" disabled>Export decisions</button>
<span id="msg"></span></div>
<table><thead><tr><th>#</th><th>brand</th><th>aliases in the table</th><th>draft evidence (writing assistant, 28 Sep)</th><th>your decision</th><th>source (required unless "stays global")</th><th>note</th></tr></thead>
<tbody id="tb"></tbody></table>
<div class="foot">Instrument: build_bd_assembly_check.py · brand_aliases.expansion.csv sha256 {TAB_SHA[:16]}… · EXPANSION-ANALYSIS-SET-v2.jsonl sha256 {SET_SHA[:16]}… · listed brands carry {100 * covered:.1f}% of the global mentions in the human primary set; the rest stay global in the sensitivity.</div>
</div>
<script>
var DATA = {data_js};
var OPTIONS = {opts_js};
var LSK = "n1-bd-assembly-check";
function esc(s) {{ return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }}
function render() {{
  var h = "";
  for (var i = 0; i < DATA.length; i++) {{
    var d = DATA[i];
    h += "<tr id=\\"r" + i + "\\"><td>" + (i + 1) + "</td><td><b>" + esc(d.name) + "</b><br><span style=\\"color:#666;font-size:12px\\">" + esc(d.id) + "</span></td>" +
         "<td class=\\"al\\">" + esc(d.aliases).split("|").join(" · ") + "</td><td class=\\"dr\\">" + esc(d.draft) + "</td><td class=\\"ch\\">";
    for (var c = 0; c < OPTIONS.length; c++) {{
      h += "<label><input type=\\"radio\\" name=\\"c" + i + "\\" value=\\"" + OPTIONS[c][0] + "\\" onchange=\\"changed()\\"> " + esc(OPTIONS[c][1]) + "</label>";
    }}
    h += "</td><td><input class=\\"src\\" id=\\"s" + i + "\\" maxlength=\\"400\\" oninput=\\"changed()\\" placeholder=\\"URL or publication\\"></td>" +
         "<td><input class=\\"note\\" id=\\"n" + i + "\\" maxlength=\\"300\\" oninput=\\"changed()\\" placeholder=\\"optional\\"></td></tr>";
  }}
  document.getElementById("tb").innerHTML = h;
}}
function state() {{
  var out = [];
  for (var i = 0; i < DATA.length; i++) {{
    var sel = document.querySelector("input[name=c" + i + "]:checked");
    out.push({{ id: DATA[i].id, decision: sel ? sel.value : null, source: document.getElementById("s" + i).value || "", note: document.getElementById("n" + i).value || "" }});
  }}
  return out;
}}
function apply(rows) {{
  var by = {{}};
  for (var k = 0; k < rows.length; k++) by[rows[k].id] = rows[k];
  for (var i = 0; i < DATA.length; i++) {{
    var r = by[DATA[i].id]; if (!r) continue;
    if (r.decision) {{ var el = document.querySelector("input[name=c" + i + "][value=" + r.decision + "]"); if (el) el.checked = true; }}
    document.getElementById("s" + i).value = r.source || "";
    document.getElementById("n" + i).value = r.note || "";
  }}
  changed(false);
}}
function changed(save) {{
  var s = state(), n = 0, need = 0;
  for (var i = 0; i < s.length; i++) {{
    var tr = document.getElementById("r" + i), cls = "";
    if (s[i].decision) {{
      n++;
      if (s[i].decision === "global") cls = "done";
      else if (s[i].decision === "unsure") cls = (s[i].note.trim() ? "amb" : "need");
      else cls = (s[i].source.trim() ? "amb" : "need");
      if (cls === "need") need++;
    }}
    tr.className = cls;
  }}
  document.getElementById("count").textContent = n + " / " + DATA.length + " answered";
  document.getElementById("need").textContent = need ? " · " + need + " missing a source or reason" : "";
  document.getElementById("exp").disabled = (n !== DATA.length || need > 0);
  if (save !== false) {{ try {{ localStorage.setItem(LSK, JSON.stringify(s)); }} catch (e) {{}} }}
}}
function download(obj, name) {{
  var a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 1)], {{ type: "application/json" }}));
  a.download = name; document.body.appendChild(a); a.click(); a.remove();
}}
function saveProgress() {{
  download({{ task: "N1 C.1 sensitivity review — progress", saved_at: new Date().toISOString(), rows: state() }}, "BD-ASSEMBLY-CHECK-progress.json");
  document.getElementById("msg").textContent = "progress file downloaded";
}}
function importProgress(inp) {{
  var f = inp.files && inp.files[0]; if (!f) return;
  var rd = new FileReader();
  rd.onload = function () {{
    try {{ var o = JSON.parse(rd.result); apply(o.rows || []); changed(); document.getElementById("msg").textContent = "progress imported"; }}
    catch (e) {{ document.getElementById("msg").textContent = "could not read that file"; }}
  }};
  rd.readAsText(f); inp.value = "";
}}
function exportDecisions() {{
  var s = state(), rows = [], counts = {{}};
  for (var i = 0; i < s.length; i++) {{
    rows.push({{ canonical_id: DATA[i].id, display_name: DATA[i].name, decision: s[i].decision, source: s[i].source, note: s[i].note }});
    counts[s[i].decision] = (counts[s[i].decision] || 0) + 1;
  }}
  var out = {{ task: "N1 post-hoc C.1 sensitivity — brands decided", exported_at: new Date().toISOString(), n: rows.length, counts: counts,
              min_mentions: {MIN_MENTIONS}, table_sha256: {json.dumps(TAB_SHA)}, analysis_set_sha256: {json.dumps(SET_SHA)}, rows: rows }};
  download(out, "BD-ASSEMBLY-CHECK-decisions.json");
  document.getElementById("msg").textContent = "exported " + rows.length + " rows — send the file back";
}}
render();
(function () {{ var s = null; try {{ s = JSON.parse(localStorage.getItem(LSK) || "null"); }} catch (e) {{}} if (s) apply(s); else changed(false); }})();
</script></body></html>
"""
js = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tf:
    tf.write(js); tmp = tf.name
r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
assert r.returncode == 0, r.stderr[:400]
out = W / "BD-ASSEMBLY-CHECK.html"
out.write_text(page, encoding="utf-8", newline="\n")
print(f"wrote {out.name}: {len(DATA)} brands (>= {MIN_MENTIONS} mentions; {100 * covered:.1f}% of global mentions), sha256 {sha(out)[:16]}…; JS syntax check passed")
