r"""Review page for the sleep scores: every session's SSResults figure, in order, for the USER to judge by eye.

The user checks, per session, whether the slow-wave / theta / EMG metrics look plausible (logger noise gives very
artificial responses) and whether REM has high theta and low EMG. The agent does not judge these figures.

Reads a sleep output tree (the layout ephys/score_sleep.py writes, or a light copy of it holding only score_sleep.json and
StateScoreFigures/*_SSResults.jpg): <root>/<variant>/<SFxx>/<session>/, plus <root>/_errors/*.json for sessions the scorer
refused. Writes one self-contained page <root>/review_<variant>.html that references the figures by relative path, so it
works from disk (file://) and the data never leaves this PC.

In the page: <- / -> (or k / j) previous / next session; 1 = ok, 2 = logger noise, 3 = bad / other, 0 = clear; n = note;
u = next unreviewed. Verdicts autosave in the browser (localStorage, per page) and export / import as CSV
(session, verdict, note, reviewed_at). Keep the exported CSV in ephys/configs/sleep_review_<cohort>/.

Usage: python ephys/sleep_review.py --cohort 2026c [--root D:/3rd_rat_spikes/analysis/sleep_server] [--variant imu_remclean]
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import pandas as pd

from _common import analysis_root, report_dir, resolve_cohort, utc_now_iso


def unpad(animal: str) -> str:
    """SF07 -> SF7 (the session index keeps the raw folder names)."""
    return f"SF{int(animal[2:])}"


def collect(root: Path, variant: str, cohort: str) -> list[dict]:
    idx_csv = report_dir(cohort) / f"ephys_spikes_session_index_{cohort}.csv"
    idx = pd.read_csv(idx_csv).set_index(["animal", "session"]) if idx_csv.exists() else None
    items = []
    for js in sorted((root / variant).glob("*/*/score_sleep.json")):
        info = json.loads(js.read_text(encoding="utf-8"))
        animal, session = js.parent.parent.name, js.parent.name
        fig = js.parent / "StateScoreFigures" / f"{session}_SSResults.jpg"
        items.append({"animal": animal, "session": session, "info": info,
                      "img": fig.relative_to(root).as_posix() if fig.exists() else None})
    for ej in sorted((root / "_errors").glob("*.json")):
        e = json.loads(ej.read_text(encoding="utf-8"))
        if not any(it["animal"] == e["animal"] and it["session"] == e["session"] for it in items):
            items.append({"animal": e["animal"], "session": e["session"], "info": {}, "img": None,
                          "error": f"{e['variant']}: {e['error']}"})
    for it in items:
        row = {}
        if idx is not None:
            try:
                row = idx.loc[(unpad(it["animal"]), it["session"])].to_dict()
            except KeyError:
                row = {}
        it["start"] = str(row.get("start_local", ""))[:19]
        it["meta"] = {k: row.get(k) for k in ("duration_hms", "firmware", "regime", "measured_verdict", "field_flag", "adc_lane", "notes")
                      if pd.notna(row.get(k))}
    items.sort(key=lambda it: (it["animal"], it["start"] or it["session"]))
    return items


def card(it: dict) -> dict:
    i, m = it["info"], it["meta"]
    def pct(x):
        return "-" if x is None else f"{100 * float(x):.0f}%"
    lines = [f"{it['animal']}  {it['session']}  |  start {it['start'] or '?'} (logger clock)  |  {m.get('duration_hms', '?')}  |  "
             f"FM{m.get('firmware', '?')}  {m.get('regime', '')}"]
    if i:
        lines.append(f"WAKE {pct(i.get('frac_wake'))}  NREM {pct(i.get('frac_nrem'))}  REM {pct(i.get('frac_rem'))}  "
                     f"(REM {pct(i.get('rem_share_of_sleep'))} of sleep)  |  SW ch {i.get('SWchan')}  TH ch {i.get('THchan')}  |  "
                     f"thresholds SW {float(i.get('swthresh') or 0):.2f} EMG {float(i.get('EMGthresh') or 0):.2f} "
                     f"TH {float(i.get('THthresh') or 0):.2f}  |  sustained movement -> WAKE {pct(i.get('sustained_moving_scored_wake'))}")
    extra = [f"{k} {m[k]}" for k in ("field_flag", "adc_lane", "notes") if k in m]
    if extra:
        lines.append(" | ".join(extra))
    if it.get("error"):
        lines.append("NOT SCORED - " + it["error"])
    return {"key": f"{it['animal']}/{it['session']}", "img": it["img"], "lines": lines}


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Sleep score review</title>
<style>
:root{--bg:#f6f6f4;--fg:#1c1c1c;--muted:#666;--panel:#fff;--line:#d8d8d4;--ok:#2e7d32;--noise:#c77700;--bad:#c62828;--sel:#e8eef8}
@media (prefers-color-scheme: dark){:root{--bg:#161616;--fg:#e8e8e8;--muted:#9a9a9a;--panel:#202020;--line:#333;--sel:#24324a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.4 system-ui,Segoe UI,sans-serif;display:flex;height:100vh}
#side{width:250px;border-right:1px solid var(--line);overflow-y:auto;background:var(--panel);flex:none}
#side div{padding:3px 8px;cursor:pointer;border-left:4px solid transparent;white-space:nowrap;font-family:ui-monospace,Consolas,monospace;font-size:12px}
#side div.cur{background:var(--sel)}#side div.ok{border-left-color:var(--ok)}#side div.noise{border-left-color:var(--noise)}#side div.bad{border-left-color:var(--bad)}
#side div.err{color:var(--muted)}
#main{flex:1;display:flex;flex-direction:column;min-width:0}
#bar{padding:8px 12px;border-bottom:1px solid var(--line);background:var(--panel)}
#bar .l{font-family:ui-monospace,Consolas,monospace;font-size:12px}#bar .l:first-child{font-weight:600;font-size:13px}
#ctl{display:flex;gap:6px;align-items:center;margin-top:6px;flex-wrap:wrap}
button{font:inherit;padding:3px 10px;border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:4px;cursor:pointer}
button.on.ok{background:var(--ok);color:#fff}button.on.noise{background:var(--noise);color:#fff}button.on.bad{background:var(--bad);color:#fff}
#note{flex:1;min-width:200px;font:inherit;padding:3px 6px;border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:4px}
#prog{color:var(--muted);margin-left:auto}
#imgwrap{flex:1;overflow:auto;display:flex;justify-content:center;align-items:flex-start;padding:6px}
#imgwrap img{max-width:100%;max-height:100%;object-fit:contain;cursor:zoom-in}#imgwrap img.zoom{max-width:none;max-height:none;cursor:zoom-out}
.missing{color:var(--muted);padding:40px}
</style></head><body>
<div id="side"></div>
<div id="main"><div id="bar"><div id="lines"></div>
<div id="ctl"><button data-v="ok" class="ok">1 ok</button><button data-v="noise" class="noise">2 logger noise</button>
<button data-v="bad" class="bad">3 bad / other</button><button data-v="">0 clear</button>
<input id="note" placeholder="note (n)"><button id="exp">export CSV</button><button id="imp">import CSV</button>
<input type="file" id="file" accept=".csv" hidden><span id="prog"></span></div>
<div class="l" style="color:var(--muted);margin-top:4px">&larr;/&rarr; or k/j: prev / next &nbsp; u: next unreviewed &nbsp; click image: zoom &nbsp; verdicts autosave in this browser; export CSV to keep them</div></div>
<div id="imgwrap"></div></div>
<script>
const ITEMS = __ITEMS__, STORE = "__STORE__", CSVNAME = "__CSVNAME__";
let cur = 0, db = {};
try { db = JSON.parse(localStorage.getItem(STORE) || "{}"); } catch (e) { db = {}; }
function save(){ try { localStorage.setItem(STORE, JSON.stringify(db)); } catch (e) {} }
const side = document.getElementById("side");
ITEMS.forEach((it, i) => { const d = document.createElement("div"); d.textContent = it.key; d.onclick = () => show(i);
  if (!it.img) d.classList.add("err"); side.appendChild(d); });
function paint(){ [...side.children].forEach((d, i) => { const v = (db[ITEMS[i].key] || {}).verdict || "";
  d.className = (ITEMS[i].img ? "" : "err ") + v + (i === cur ? " cur" : ""); });
  const n = ITEMS.filter(it => (db[it.key] || {}).verdict).length;
  document.getElementById("prog").textContent = `${cur + 1} / ${ITEMS.length}  ·  reviewed ${n}`;
  const v = (db[ITEMS[cur].key] || {}).verdict || "";
  document.querySelectorAll("#ctl button[data-v]").forEach(b => b.classList.toggle("on", b.dataset.v === v && v !== "")); }
function show(i){ cur = Math.max(0, Math.min(ITEMS.length - 1, i)); const it = ITEMS[cur];
  document.getElementById("lines").innerHTML = it.lines.map(l => `<div class="l">${l}</div>`).join("");
  const w = document.getElementById("imgwrap");
  w.innerHTML = it.img ? `<img src="${it.img}" alt="${it.key}">` : `<div class="missing">no figure for this session</div>`;
  const img = w.querySelector("img"); if (img) img.onclick = () => img.classList.toggle("zoom");
  document.getElementById("note").value = (db[it.key] || {}).note || "";
  side.children[cur].scrollIntoView({block: "nearest"}); paint(); }
function setv(v){ const k = ITEMS[cur].key; db[k] = Object.assign(db[k] || {}, {verdict: v, reviewed_at: new Date().toISOString()});
  if (!v && !db[k].note) delete db[k]; save(); paint(); }
document.querySelectorAll("#ctl button[data-v]").forEach(b => b.onclick = () => setv(b.dataset.v));
document.getElementById("note").addEventListener("input", e => { const k = ITEMS[cur].key;
  db[k] = Object.assign(db[k] || {}, {note: e.target.value}); save(); });
document.addEventListener("keydown", e => {
  if (e.target.id === "note") { if (e.key === "Escape" || e.key === "Enter") e.target.blur(); return; }
  if (e.key === "ArrowRight" || e.key === "j") show(cur + 1);
  else if (e.key === "ArrowLeft" || e.key === "k") show(cur - 1);
  else if ("1230".includes(e.key) && e.key.length === 1) setv({"1": "ok", "2": "noise", "3": "bad", "0": ""}[e.key]);
  else if (e.key === "n") { e.preventDefault(); document.getElementById("note").focus(); }
  else if (e.key === "u") { for (let s = 1; s <= ITEMS.length; s++) { const i = (cur + s) % ITEMS.length;
    if (!(db[ITEMS[i].key] || {}).verdict) { show(i); break; } } } });
const q = s => '"' + String(s ?? "").replace(/"/g, '""') + '"';
document.getElementById("exp").onclick = () => {
  const rows = ["animal_session,verdict,note,reviewed_at"].concat(ITEMS.filter(it => db[it.key]).map(it => {
    const r = db[it.key]; return [q(it.key), q(r.verdict), q(r.note), q(r.reviewed_at)].join(","); }));
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([rows.join("\n") + "\n"], {type: "text/csv"}));
  a.download = CSVNAME; a.click(); };
document.getElementById("imp").onclick = () => document.getElementById("file").click();
document.getElementById("file").onchange = async e => { const f = e.target.files[0]; if (!f) return;
  const lines = (await f.text()).trim().split(/\r?\n/).slice(1);
  for (const line of lines) { const c = [...line.matchAll(/"((?:[^"]|"")*)"/g)].map(m => m[1].replace(/""/g, '"'));
    if (c.length >= 2) db[c[0]] = {verdict: c[1], note: c[2] || "", reviewed_at: c[3] || ""}; }
  save(); show(cur); };
show(0);
</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--root", default=None, help="sleep output tree (default <analysis_root>/sleep)")
    ap.add_argument("--variant", default="imu_remclean")
    a = ap.parse_args()
    c = resolve_cohort(a.cohort)
    root = Path(a.root) if a.root else analysis_root(c) / "sleep"
    items = collect(root, a.variant, c)
    cards = [card(it) for it in items]
    for cd in cards:
        cd["lines"] = [html.escape(l) for l in cd["lines"]]
    page = (PAGE.replace("__ITEMS__", json.dumps(cards))
                .replace("__STORE__", f"sleep_review::{c}::{a.variant}::{root.as_posix()}")
                .replace("__CSVNAME__", f"sleep_review_{c}_{a.variant}.csv"))
    out = root / f"review_{a.variant}.html"
    out.write_text(page, encoding="utf-8")
    n_fig = sum(1 for cd in cards if cd["img"])
    print(f"{len(cards)} sessions ({n_fig} with a figure, {len(cards) - n_fig} not scored) -> {out}  [{utc_now_iso()}]")


if __name__ == "__main__":
    main()
