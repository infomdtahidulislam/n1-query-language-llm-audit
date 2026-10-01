#!/usr/bin/env python3
"""build_adjudication_main.py — R1's D.4 adjudication page for the MAIN run.

REGISTERED SCOPE (prereg D.4, "Main-run scope", amended pre-freeze 13 Sep 2026, v0.46):
filing stays exhaustive (all 852 disagreements are filed and released), but R1 adjudicates
a stratified random sample of **200** of them — proportional by model x arm, without
replacement, **seed 20260914** — and the confirmation rate is reported with a Wilson 95% CI.
Below 95% -> a second disjoint 200; below 95% again -> exhaustive.

Run this ON THE STUDY MACHINE, from the study folder:
    python build_adjudication_main.py

Reads  runs/coded/main.adjudicate.jsonl  (the filed disagreements finalize emitted) and the
answer text from runs/responses/main/.
Writes:
    ADJUDICATE-R1-MAIN.html                  -> send this file to R1 (200 answers)
    ADJUDICATE-MAIN-MAPPING-authors-only.csv -> stays with the authors, never to raters
    ADJUDICATE-MAIN-SAMPLE.json              -> per-cell allocation + drawn keys (audit trail)

Instrument identity with the pilot (D.4): same five classes with the same one-line
definitions, same blind presentation (no model, no arm, no selection reason), same export
shape {rater: "R1", decisions: [{row_id, decision, note}]}. Row ids C001..C200; presentation
order shuffled with the same registered seed. R1's progress autosaves in the browser AND
can be saved to / restored from a progress file (Save progress / Import progress), matching
the labelling instrument; added 21 Sep 2026 — judgement surface unchanged.
"""
import csv, glob, html, json, os, random, sys
from collections import Counter

SEED = 20260914          # registered in prereg D.4 main-run scope
TARGET = 200
ADJ = os.path.join("runs", "coded", "main.adjudicate.jsonl")
RESP = os.path.join("runs", "responses", "main")

rows = [json.loads(l) for l in open(ADJ, encoding="utf-8") if l.strip()]
N_FILED = len(rows)
print(f"filed disagreements: {N_FILED}")

# ---------- registered sampling: stratified by model x arm, proportional, without replacement ----------
by_cell = {}
for r in rows:
    by_cell.setdefault((r["model_id"], r["arm"]), []).append(r)
cells = sorted(by_cell)                      # deterministic cell order

if N_FILED <= TARGET:
    sample = list(rows)
    alloc = {f"{m}|{a}": len(by_cell[(m, a)]) for (m, a) in cells}
    print(f"fewer than {TARGET} filed -> all {N_FILED} adjudicated (registered rule)")
else:
    # largest-remainder (Hamilton) proportional allocation, so the parts sum to exactly TARGET
    exact = {c: len(by_cell[c]) * TARGET / N_FILED for c in cells}
    base = {c: int(exact[c]) for c in cells}
    left = TARGET - sum(base.values())
    # rank by remainder, ties broken by the registered seed (never by dict order)
    rng_tie = random.Random(SEED)
    order = sorted(cells, key=lambda c: (-(exact[c] - base[c]), rng_tie.random()))
    for c in order[:left]:
        base[c] += 1
    for c in cells:                          # cannot draw more than a cell holds
        base[c] = min(base[c], len(by_cell[c]))
    # any shortfall from that clamp is redistributed, largest cells first, deterministically
    short = TARGET - sum(base.values())
    while short > 0:
        room = [c for c in cells if base[c] < len(by_cell[c])]
        if not room:
            break
        room.sort(key=lambda c: (-(len(by_cell[c]) - base[c]), c))
        base[room[0]] += 1
        short -= 1
    sample = []
    for c in cells:                          # independent draw per cell, one seeded stream
        pool = sorted(by_cell[c], key=lambda r: r["key"])
        sample += random.Random(f"{SEED}|{c[0]}|{c[1]}").sample(pool, base[c])
    alloc = {f"{m}|{a}": base[(m, a)] for (m, a) in cells}

assert len({r["key"] for r in sample}) == len(sample), "duplicate keys drawn"
N = len(sample)
print(f"drawn for adjudication: {N} (seed {SEED}, proportional by model x arm, without replacement)")
for (m, a) in cells:
    print(f"  {m:<20}{a:<14}{alloc[f'{m}|{a}']:>4} of {len(by_cell[(m, a)]):>4}")

# ---------- attach the answer text ----------
files = {}
for f in glob.glob(os.path.join(RESP, "*", "*.json")):
    k12 = os.path.basename(f).rsplit("_", 1)[1][:-5]
    if k12 in files:
        sys.exit(f"key-fragment collision: {files[k12]} vs {f} — refuse to guess")
    files[k12] = f
for r in sample:
    p = files.get(r["key"][:12])
    if not p:
        sys.exit(f"no response record found for key {r['key']}")
    d = json.load(open(p, encoding="utf-8"))
    if d["key"] != r["key"]:
        sys.exit(f"key mismatch reading {p}")
    content = (d.get("meta") or {}).get("content") or ""
    if r.get("content_start") and not content.startswith(r["content_start"][:100]):
        sys.exit(f"content mismatch for {r['key']} — cache and queue disagree")
    r["_answer"] = content

# presentation order: shuffled with the same registered seed, so ids carry no cell signal
shuffled = sorted(sample, key=lambda r: r["key"])
random.Random(SEED).shuffle(shuffled)
for n, r in enumerate(shuffled, 1):
    r["_rid"] = f"C{n:03d}"

with open("ADJUDICATE-MAIN-MAPPING-authors-only.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["row_id", "key", "query_id", "arm", "model_id", "rep", "draw", "script_class",
                "bangla_ratio", "extractor_answer_language", "reason", "provisional_outcome"])
    for r in shuffled:
        w.writerow([r["_rid"], r["key"], r["query_id"], r["arm"], r["model_id"], r["rep"],
                    r["draw"], r["script_class"], r["bangla_ratio"],
                    r["extractor_answer_language"], r["reason"], r["provisional_outcome"]])

json.dump({"seed": SEED, "filed_total": N_FILED, "target": TARGET, "drawn": N,
           "rule": "prereg D.4 main-run scope (v0.46): stratified random sample, proportional "
                   "by model x arm, without replacement, seed 20260914",
           "allocation_per_cell": alloc,
           "cell_totals": {f"{m}|{a}": len(by_cell[(m, a)]) for (m, a) in cells},
           "drawn_keys": sorted(r["key"] for r in sample)},
          open("ADJUDICATE-MAIN-SAMPLE.json", "w"), indent=1)

CLASSES = ["bn", "banglish", "en", "mixed", "other"]
DEFS = {
    "bn": "Bangla written in Bangla script.",
    "banglish": 'Bangla written in Latin letters ("ei budget e Walton bhalo hobe").',
    "en": "English.",
    "mixed": "substantial passages in two or more of the above (a Bangla answer that contains "
             "English product names is still bn; an answer whose paragraphs alternate between "
             "English and Bangla is mixed).",
    "other": "none of the above, or no readable prose.",
}
cards = []
for r in shuffled:
    rid = r["_rid"]
    opts = "".join(
        f'<label class="opt"><input type="radio" name="dec_{rid}" value="{c}"> {c}</label>'
        for c in CLASSES)
    cards.append(f"""
<div class="card" id="card_{rid}">
  <div class="card-head"><span class="rid">{rid}</span><span class="status" id="st_{rid}">not answered</span></div>
  <div class="answer">{html.escape(r["_answer"])}</div>
  <div class="decide">
    <div class="opts">{opts}</div>
    <input type="text" class="note" id="note_{rid}" placeholder="note (optional — required if you were torn between two classes)" maxlength="500">
  </div>
</div>""")

defs_html = "".join(f"<tr><td class='cls'>{c}</td><td>{html.escape(DEFS[c])}</td></tr>"
                    for c in CLASSES)
ids_js = json.dumps([r["_rid"] for r in shuffled])

page = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Language adjudication — main run — __N__ answers</title>
<style>
  :root { color-scheme: light; }
  body { margin:0; padding:0 16px 80px; background:#f6f5f1; color:#1a1a1a;
         font:15px/1.55 "Segoe UI", system-ui, sans-serif; }
  .wrap { max-width: 860px; margin: 0 auto; }
  h1 { font-size:20px; margin:20px 0 6px; }
  .instr { background:#fff; border:1px solid #ddd; border-radius:8px; padding:14px 16px; margin:12px 0 20px; }
  .instr table { border-collapse:collapse; margin:8px 0; }
  .instr td { padding:3px 10px 3px 0; vertical-align:top; }
  .instr td.cls { font-weight:700; white-space:nowrap; }
  .topbar { position:sticky; top:0; z-index:5; background:#f6f5f1ee; backdrop-filter:blur(2px);
            padding:8px 0; border-bottom:1px solid #ddd; display:flex; gap:14px; align-items:center; flex-wrap:wrap; }
  #prog { font-weight:700; }
  .card { background:#fff; border:1px solid #ddd; border-radius:8px; margin:14px 0; overflow:hidden; }
  .card.done { border-color:#7cb87c; }
  .card-head { display:flex; justify-content:space-between; padding:8px 14px; background:#efece4; font-weight:700; }
  .card.done .card-head { background:#e2efe2; }
  .status { font-weight:400; color:#8a6d3b; }
  .card.done .status { color:#2e7d32; }
  .answer { padding:12px 16px; white-space:pre-wrap; word-wrap:break-word;
            font-size:16px; line-height:1.7; border-bottom:1px solid #eee; }
  .decide { padding:10px 14px 14px; }
  .opts { display:flex; flex-wrap:wrap; gap:6px 14px; margin-bottom:8px; }
  .opt { padding:4px 10px; border:1px solid #ccc; border-radius:16px; cursor:pointer; user-select:none; background:#fafafa; }
  .opt:has(input:checked) { background:#1a4d8f; color:#fff; border-color:#1a4d8f; }
  .opt input { accent-color:#1a4d8f; margin-right:4px; }
  .note { width:100%; box-sizing:border-box; padding:7px 9px; border:1px solid #ccc; border-radius:6px; font:14px inherit; }
  button.export { background:#1a4d8f; color:#fff; border:0; border-radius:6px; padding:9px 18px;
                  font:700 15px inherit; cursor:pointer; }
  button.export:hover { background:#153e73; }
  button.next { background:#efece4; color:#1a1a1a; border:1px solid #ccc; border-radius:6px;
                padding:9px 14px; font:700 14px inherit; cursor:pointer; }
  #msg { color:#b23b3b; font-weight:600; }
  .foot { margin:26px 0; text-align:center; }
</style>
</head>
<body>
<div class="wrap">
<h1>Language adjudication — main run — __N__ answers</h1>
<div class="instr">
  <p><b>Task.</b> Below are __N__ chatbot answers. For each one, judge the language of its
  <b>running prose</b> — the sentences — <b>not</b> brand names, model numbers, units or prices.
  Pick one class per answer:</p>
  <table>__DEFS__</table>
  <p>If you are torn between two classes, pick the closer one and say why in the note box
  (notes are optional otherwise). Judge only what is on this page, work alone, and please
  don't discuss the answers with anyone while working.</p>
  <p>Work in as many sittings as you like. Your progress is saved in this browser whenever you
  answer, so you can close and reopen the page. The <b>next unanswered</b> button jumps to
  wherever you left off.</p>
  <p><b>Keep a backup.</b> <b>Save progress</b> downloads
  <code>ADJUDICATE-R1-MAIN-progress.json</code> — keep that file; <b>Import progress</b> loads it
  back, on this computer or any other, so nothing is lost if the browser forgets. Do that at the
  end of each sitting. <b>Clear all fields</b> wipes everything (it asks first) if you ever need a
  clean start.</p>
  <p><b>When all __N__ are answered</b>, press <b>Export decisions</b> (top or bottom of the
  page) — it downloads a small file named <code>ADJUDICATE-R1-MAIN-decisions.json</code>.
  Send that file back.</p>
</div>
<div class="topbar"><span id="prog">0 / __N__ answered</span>
  <button class="next" onclick="nextUnanswered()">next unanswered</button>
  <button class="export" onclick="doExport()">Export decisions</button>
  <button class="export" style="background:#fff;color:#1a4d8f;border:1px solid #1a4d8f" onclick="doSaveProgress()">Save progress</button>
  <button class="export" style="background:#fff;color:#1a4d8f;border:1px solid #1a4d8f" onclick="document.getElementById('impfile').click()">Import progress</button>
  <button class="export" style="background:#fff;color:#b23b3b;border:1px solid #b23b3b" onclick="doClearAll()">Clear all fields</button>
  <input type="file" id="impfile" accept=".json,application/json" hidden>
  <span id="msg"></span></div>
__CARDS__
<div class="foot"><button class="export" onclick="doExport()">Export decisions</button>
  <button class="export" style="background:#fff;color:#1a4d8f;border:1px solid #1a4d8f" onclick="doSaveProgress()">Save progress</button>
  <div id="msg2" style="color:#b23b3b;font-weight:600;margin-top:8px;"></div></div>
</div>
<script>
var IDS = __IDS__;
var N = __N__;
var LSK = "n1-adjudicate-r1-main-draft";
function state() {
  var s = {};
  IDS.forEach(function (id) {
    var sel = document.querySelector('input[name="dec_' + id + '"]:checked');
    s[id] = { decision: sel ? sel.value : "", note: document.getElementById("note_" + id).value.trim() };
  });
  return s;
}
function refresh() {
  var s = state(), n = 0;
  IDS.forEach(function (id) {
    var done = !!s[id].decision; if (done) n++;
    document.getElementById("card_" + id).classList.toggle("done", done);
    document.getElementById("st_" + id).textContent = done ? "answered: " + s[id].decision : "not answered";
  });
  document.getElementById("prog").textContent = n + " / " + N + " answered";
  try { localStorage.setItem(LSK, JSON.stringify(s)); } catch (e) {}
  return n;
}
function nextUnanswered() {
  var s = state();
  for (var i = 0; i < IDS.length; i++) {
    if (!s[IDS[i]].decision) {
      document.getElementById("card_" + IDS[i]).scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
  }
  document.getElementById("msg").textContent = "All answered — export when ready.";
}
function decisionsArray(s) {
  return IDS.map(function (id) { return { row_id: id, decision: s[id].decision, note: s[id].note }; });
}
function ndone(s) { var n = 0; IDS.forEach(function (id) { if (s[id].decision) n++; }); return n; }
function applyState(s) {
  IDS.forEach(function (id) {
    var o = s[id] || {};
    document.querySelectorAll('input[name="dec_' + id + '"]').forEach(function (e) {
      e.checked = (e.value === (o.decision || ""));
    });
    document.getElementById("note_" + id).value = o.note || "";
  });
}
function download(obj, name) {
  var a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" }));
  a.download = name; document.body.appendChild(a); a.click(); a.remove();
}
function msg(text, ok) {
  var m1 = document.getElementById("msg"), m2 = document.getElementById("msg2");
  m1.style.color = m2.style.color = ok ? "#2e7d32" : "#b23b3b";
  m1.textContent = m2.textContent = text;
}
function doSaveProgress() {
  var s = state();
  download({ task: "N1 language adjudication (main)", rater: "R1", partial: true,
             done: ndone(s), saved_at: new Date().toISOString(), decisions: decisionsArray(s) },
           "ADJUDICATE-R1-MAIN-progress.json");
  msg("Progress saved (" + ndone(s) + " / " + N + " answered) — keep that file; Import loads it back on any computer.", true);
}
function doClearAll() {
  var cur = ndone(state());
  if (!confirm("This will ERASE everything on this page (" + cur + " / " + N + " answered) and the browser's saved copy.\\n\\nIf any of this is real work, press Cancel and use Save progress first. Continue?")) return;
  applyState({}); try { localStorage.removeItem(LSK); } catch (e) {}
  refresh(); msg("All fields cleared — 0 / " + N + ". Import your progress file to continue, or start fresh.", true);
}
function doImport(ev) {
  var f = ev.target.files[0]; ev.target.value = ""; if (!f) return;
  var rd = new FileReader();
  rd.onload = function () {
    try {
      var j = JSON.parse(rd.result);
      if (!j || typeof j !== "object" || !Array.isArray(j.decisions)) { msg("Import failed: not a decisions/progress file.", false); return; }
      if ((j.task || "").indexOf("N1 language adjudication") !== 0) { msg("Import refused: that file is from a different task.", false); return; }
      if (j.rater && j.rater !== "R1") { msg("Import refused: that file belongs to rater " + j.rater + ".", false); return; }
      var s = {}, inc = 0;
      j.decisions.forEach(function (o) { if (o && o.row_id && IDS.indexOf(o.row_id) >= 0) { s[o.row_id] = o; if (o.decision) inc++; } });
      if (!Object.keys(s).length) { msg("Import failed: no matching answers in that file.", false); return; }
      var cur = ndone(state());
      if (cur > 0 && !confirm("This will REPLACE what is currently on this page (" + cur + " / " + N + " answered) with the file's contents (" + inc + " / " + N + " answered). Continue?")) return;
      applyState(s); refresh();
      msg("Imported — " + ndone(state()) + " / " + N + " answered. Continue where you left off.", true);
    } catch (e) { msg("Import failed: could not read that file (" + e.message + ").", false); }
  };
  rd.readAsText(f);
}
function doExport() {
  var s = state();
  var missing = IDS.filter(function (id) { return !s[id].decision; });
  var m1 = document.getElementById("msg"), m2 = document.getElementById("msg2");
  if (missing.length) {
    m1.style.color = m2.style.color = "#b23b3b";
    m1.textContent = m2.textContent = "Not finished — " + missing.length + " unanswered (first: " + missing[0] + "). Use Save progress to keep partial work.";
    var el = document.getElementById("card_" + missing[0]);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  var out = { task: "N1 language adjudication (main)", rater: "R1",
              exported_at: new Date().toISOString(),
              decisions: IDS.map(function (id) { return { row_id: id, decision: s[id].decision, note: s[id].note }; }) };
  var blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "ADJUDICATE-R1-MAIN-decisions.json";
  document.body.appendChild(a); a.click(); a.remove();
  m1.style.color = m2.style.color = "#2e7d32";
  m1.textContent = m2.textContent = "Exported — send back ADJUDICATE-R1-MAIN-decisions.json";
}
document.addEventListener("change", function (e) { if (e.target && e.target.id === "impfile") return; refresh(); });
document.addEventListener("input", refresh);
document.getElementById("impfile").addEventListener("change", doImport);
(function () {
  try {
    var s = JSON.parse(localStorage.getItem(LSK) || "{}");
    IDS.forEach(function (id) {
      if (s[id] && s[id].decision) {
        var el = document.querySelector('input[name="dec_' + id + '"][value="' + s[id].decision + '"]');
        if (el) el.checked = true;
      }
      if (s[id] && s[id].note) document.getElementById("note_" + id).value = s[id].note;
    });
  } catch (e) {}
  refresh();
})();
</script>
</body>
</html>"""
page = (page.replace("__DEFS__", defs_html).replace("__CARDS__", "".join(cards))
            .replace("__IDS__", ids_js).replace("__N__", str(N)))
with open("ADJUDICATE-R1-MAIN.html", "w", encoding="utf-8") as f:
    f.write(page)
print(f"\nwrote ADJUDICATE-R1-MAIN.html ({len(page):,} bytes, {N} answers, ids C001..C{N:03d})")
print("wrote ADJUDICATE-MAIN-MAPPING-authors-only.csv  (AUTHORS ONLY — never send to a rater)")
print("wrote ADJUDICATE-MAIN-SAMPLE.json  (per-cell allocation + drawn keys; reproduces the draw)")
print("send ADJUDICATE-R1-MAIN.html to R1; the export to send back is ADJUDICATE-R1-MAIN-decisions.json")
