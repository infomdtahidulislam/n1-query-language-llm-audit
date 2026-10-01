#!/usr/bin/env python3
"""build_starter_check_pages.py — N1: the starter-table class confirmation as one self-contained HTML page per author
(replaces the two xlsx sheets of build_starter_check.py at the authors' request, before either author answered;
same 49 rows, same rule, same independence).

Each page shows the 49 starter entities in alphabetical order with the drafted class (1 Sep 2026), the frozen aliases
and whether the class was already confirmed on 13 Sep as a retailer class; NO frequencies and NO results. The author
chooses local / global / ambiguous for every row (nothing is pre-selected — a confirmation is an active choice), may
add a note, and exports STARTER-CHECK-<Author>-decisions.json when all 49 are answered. Progress autosaves in the
browser and can be exported/imported as a file. The frozen table is never touched.

Usage: python build_starter_check_pages.py  ->  STARTER-CHECK-Tahidul.html, STARTER-CHECK-Maksuda.html
A JavaScript syntax check (node --check) gates each page, per the D.4 adjudication record's lesson.
"""
import csv, hashlib, html, json, re, subprocess, tempfile
from pathlib import Path

W = Path(".")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
with open(W / "brand_aliases.starter.csv", encoding="utf-8", newline="") as fh:
    rows = list(csv.DictReader(fh))
assert len(rows) == 49 and all(r["source"] == "starter-unverified" for r in rows)
with open(W / "brand_aliases.csv", encoding="utf-8", newline="") as fh:
    frozen = {r["canonical_id"]: r for r in csv.DictReader(fh)}
for r in rows:
    assert frozen[r["canonical_id"]]["class"] == r["class"], r["canonical_id"]
CONFIRMED_13SEP = {"chaldal", "pickaboo", "rokomari", "ryans", "startech", "daraz"}
rows.sort(key=lambda r: r["canonical_id"])
DATA = [{"id": r["canonical_id"], "name": r["display_name"], "drafted": r["class"], "aliases": frozen[r["canonical_id"]]["aliases"],
         "confirmed_13sep": r["canonical_id"] in CONFIRMED_13SEP} for r in rows]
STARTER_SHA = sha(W / "brand_aliases.starter.csv")
FROZEN_SHA = sha(W / "brand_aliases.csv")

RULE = ("Classify by <b>headquarters / ownership only</b> (registered rule C.1) — not by where the product is made, "
        "assembled or sold, and not by anything the models said. <b>local</b> = Bangladeshi-owned brand. "
        "<b>global</b> = foreign-owned; a multinational with a Bangladesh plant, assembler or joint venture is still global. "
        "<b>ambiguous</b> = foreign parent with a strong Bangladesh identity (the subsidiary case; goes into the C.5 "
        "sensitivity). Decide every row yourself; the drafted class is shown for reference only. Work alone — do not "
        "discuss with the other author until both files are returned.")

def build(author):
    data_js = json.dumps(DATA, ensure_ascii=False).replace("</", "<\\/")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>N1 starter-table class confirmation — {author}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f6f4ef;color:#1d1d1d}}
.wrap{{max-width:1180px;margin:0 auto;padding:18px 16px 60px}}
h1{{font-size:20px;margin:0 0 6px}} .sub{{color:#555;font-size:14px;margin:0 0 12px}}
.rule{{background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px 14px;font-size:14px;line-height:1.5;margin:0 0 14px}}
.bar{{position:sticky;top:0;background:#f6f4ef;padding:8px 0;border-bottom:1px solid #ddd;margin:0 0 10px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:14px}}
.bar button{{padding:6px 12px;border-radius:8px;border:1px solid #999;background:#fff;cursor:pointer;font-size:14px}}
.bar button.primary{{background:#1f5f3a;color:#fff;border-color:#1f5f3a}} .bar button:disabled{{opacity:.45;cursor:not-allowed}}
#count{{font-weight:600}} #msg{{color:#555}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:14px}}
th,td{{border:1px solid #e3e0d8;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f0eee8;position:sticky;top:44px}}
td.al{{color:#555;font-size:13px;max-width:360px;word-break:break-word}}
td.ch label{{display:inline-block;margin:0 10px 4px 0;white-space:nowrap;cursor:pointer}}
tr.done td{{background:#f7fbf7}} tr.diff td{{background:#fff7e6}}
input.note{{width:100%;box-sizing:border-box;font-size:13px;padding:4px 6px;border:1px solid #ccc;border-radius:6px}}
.tag{{display:inline-block;font-size:11px;padding:1px 6px;border-radius:6px;background:#e8e4da;color:#333;margin-left:6px}}
.foot{{font-size:12px;color:#666;margin-top:18px}}
</style></head><body><div class="wrap">
<h1>N1 — starter-table class confirmation — {author}</h1>
<p class="sub">28 Sep 2026 · 49 entities · independent review · export when all 49 are answered</p>
<div class="rule">{RULE}<br><br><b>How:</b> pick a class in every row (the counter shows what is left), add a note where you
disagree with the drafted class or are unsure, then press <b>Export decisions</b> and send the downloaded file
<code>STARTER-CHECK-{author}-decisions.json</code> back unchanged. Progress saves itself in this browser; <b>Save progress</b>
downloads a backup you can <b>Import</b> on another computer.</div>
<div class="bar"><span id="count">0 / 49 answered</span>
<button onclick="saveProgress()">Save progress</button>
<label><button onclick="document.getElementById('imp').click()">Import progress</button><input id="imp" type="file" accept="application/json" style="display:none" onchange="importProgress(this)"></label>
<button id="exp" class="primary" onclick="exportDecisions()" disabled>Export decisions</button>
<span id="msg"></span></div>
<table><thead><tr><th>#</th><th>entity</th><th>drafted class<br>(1 Sep 2026)</th><th>aliases in the frozen table</th><th>your class</th><th>note (why, or the ownership source)</th></tr></thead>
<tbody id="tb"></tbody></table>
<div class="foot">Instrument: build_starter_check_pages.py · starter table sha256 {STARTER_SHA[:16]}… · frozen brand_aliases.csv sha256 {FROZEN_SHA[:16]}… · nothing you do here edits any study file.</div>
</div>
<script>
var AUTHOR = {json.dumps(author)};
var DATA = {data_js};
var LSK = "n1-starter-check-" + AUTHOR;
var CLASSES = ["local", "global", "ambiguous"];
function esc(s) {{ return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }}
function render() {{
  var tb = document.getElementById("tb"), h = "";
  for (var i = 0; i < DATA.length; i++) {{
    var d = DATA[i];
    h += "<tr id=\\"r" + i + "\\"><td>" + (i + 1) + "</td><td><b>" + esc(d.name) + "</b><br><span style=\\"color:#666;font-size:12px\\">" + esc(d.id) + "</span>" +
         (d.confirmed_13sep ? "<span class=\\"tag\\">retailer class confirmed 13 Sep</span>" : "") + "</td><td>" + esc(d.drafted) + "</td>" +
         "<td class=\\"al\\">" + esc(d.aliases).split("|").join(" · ") + "</td><td class=\\"ch\\">";
    for (var c = 0; c < CLASSES.length; c++) {{
      h += "<label><input type=\\"radio\\" name=\\"c" + i + "\\" value=\\"" + CLASSES[c] + "\\" onchange=\\"changed()\\"> " + CLASSES[c] + "</label>";
    }}
    h += "</td><td><input class=\\"note\\" id=\\"n" + i + "\\" maxlength=\\"300\\" oninput=\\"changed()\\" placeholder=\\"optional\\"></td></tr>";
  }}
  tb.innerHTML = h;
}}
function state() {{
  var out = [];
  for (var i = 0; i < DATA.length; i++) {{
    var sel = document.querySelector("input[name=c" + i + "]:checked");
    out.push({{ id: DATA[i].id, your_class: sel ? sel.value : null, note: document.getElementById("n" + i).value || "" }});
  }}
  return out;
}}
function apply(rows) {{
  var by = {{}};
  for (var k = 0; k < rows.length; k++) by[rows[k].id] = rows[k];
  for (var i = 0; i < DATA.length; i++) {{
    var r = by[DATA[i].id]; if (!r) continue;
    if (r.your_class) {{ var el = document.querySelector("input[name=c" + i + "][value=" + r.your_class + "]"); if (el) el.checked = true; }}
    document.getElementById("n" + i).value = r.note || "";
  }}
  changed(false);
}}
function changed(save) {{
  var s = state(), n = 0;
  for (var i = 0; i < s.length; i++) {{
    var tr = document.getElementById("r" + i);
    if (s[i].your_class) {{ n++; tr.className = (s[i].your_class === DATA[i].drafted) ? "done" : "diff"; }} else tr.className = "";
  }}
  document.getElementById("count").textContent = n + " / " + DATA.length + " answered";
  document.getElementById("exp").disabled = (n !== DATA.length);
  if (save !== false) {{ try {{ localStorage.setItem(LSK, JSON.stringify(s)); localStorage.setItem(LSK + "-t", new Date().toISOString()); }} catch (e) {{}} }}
}}
function download(obj, name) {{
  var a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 1)], {{ type: "application/json" }}));
  a.download = name; document.body.appendChild(a); a.click(); a.remove();
}}
function saveProgress() {{
  download({{ task: "N1 starter-table class confirmation — progress", author: AUTHOR, saved_at: new Date().toISOString(), rows: state() }},
           "STARTER-CHECK-" + AUTHOR + "-progress.json");
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
  var s = state(), rows = [], changedN = 0;
  for (var i = 0; i < s.length; i++) {{
    rows.push({{ canonical_id: DATA[i].id, display_name: DATA[i].name, drafted_class: DATA[i].drafted, your_class: s[i].your_class, note: s[i].note }});
    if (s[i].your_class !== DATA[i].drafted) changedN++;
  }}
  var out = {{ task: "N1 starter-table class confirmation", author: AUTHOR, exported_at: new Date().toISOString(), n: rows.length,
              differs_from_draft: changedN, starter_sha256: {json.dumps(STARTER_SHA)}, frozen_sha256: {json.dumps(FROZEN_SHA)},
              rule: "C.1 headquarters/ownership", rows: rows }};
  download(out, "STARTER-CHECK-" + AUTHOR + "-decisions.json");
  document.getElementById("msg").textContent = "exported: " + rows.length + " rows, " + changedN + " differ from the draft — send the file back";
}}
render();
(function () {{ var s = null; try {{ s = JSON.parse(localStorage.getItem(LSK) || "null"); }} catch (e) {{}} if (s) apply(s); else changed(false); }})();
</script></body></html>
"""
    return page

for author in ("Tahidul", "Maksuda"):
    page = build(author)
    js = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tf:
        tf.write(js); tmp = tf.name
    r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
    assert r.returncode == 0, f"JavaScript syntax check failed for {author}: {r.stderr[:400]}"
    out = W / f"STARTER-CHECK-{author}.html"
    out.write_text(page, encoding="utf-8", newline="\n")
    print(f"wrote {out.name} sha256 {sha(out)[:16]}… (49 rows; JS syntax check passed)")
print("starter csv sha256", STARTER_SHA[:16], "| frozen brand_aliases.csv sha256", FROZEN_SHA[:16])
