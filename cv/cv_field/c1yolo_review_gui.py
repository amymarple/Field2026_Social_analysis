r"""c1yolo_review_gui.py — one clickable review page for the cohort-3 CH01 YOLO work: Step 1 the two YOLO fixed spots (object
/ rat / unsure), Step 2 the WISER suspected-miss episodes (58 episodes, one clip each, shown as 59 rows grouped by the 12
old shared clips; episode 204 sits in two groups). Replaces typing verdicts into CSVs.

Pattern: wiser/scripts/make_wiser_event_review.py (one self-contained index.html, data embedded, works from file://,
verdicts in localStorage, Export CSV + JSON, Import JSON). Media are referenced by absolute file:/// URLs (nothing is
copied or re-rendered):
  Step 1  $OUT/2026c/cv_field_c1yolo_video_20261005_1848/fixed_spots/ (locator.png, heatmap.png, crops/, fixed_spots.csv)
  Step 2  $OUT/2026c/cv_field_wiser_assist_p0_20261005_2211/review_clips_per_episode/ (one mp4 per episode that follows THAT
          episode's animal, clips_per_episode.csv; wiser_assist_p0.py --episode-clips) + review_clips/clips.csv (the old
          shared clips, used only to group the rows) + fn_episodes.csv (episode times) + the step-2 frames.csv.gz (seek
          offsets). The 12 shared clips (review_clips/) followed only each clip's primary animal (the user's bug report
          2026-10-06), so the page no longer plays them.
Storage migration (2026-10-06): Step-2 verdicts saved under the old item ids c<k>_ep<id> are mapped on load to ep<id>
(earliest saved verdict -> verdict_first, latest -> the current verdict; old keys kept as a backup); Import JSON accepts
the old export format the same way. Step 1 (items spot_1, spot_2, fn_notes) and the storage key are unchanged.
Step 2 stays locked until both Step-1 spot verdicts are saved (part-B blinding: the WISER circles in the clips reveal what
part B tests). The page shows no geometry class, occluder or sealed number (it never reads the occlusion run's
episodes.csv / seconds.csv.gz or phase 0's wiser_spots.csv).

Export: one CSV + one JSON with the rows step, item_id, clip, animal, verdict, occluder_kind, notes, saved_at (+ episode_id,
verdict_first, verdict_final, changed, first_saved_at, reviewer, status). verdict_first = the first saved verdict;
verdict_final = the last saved one; changed = they differ. Files go to cv/configs/c1yolo_review_2026c/ in the repo.

Usage (base Python; node for the self-test):
  python cv/cv_field/c1yolo_review_gui.py --selftest
  python cv/cv_field/c1yolo_review_gui.py --build [--out <dir>]   -> $OUT/2026c/cv_field_c1yolo_review_gui_<ts>/index.html
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT_ROOT = Path(os.environ.get("FIELD2026_ANALYSIS_OUT_ROOT", "D:/Field2026_analysis_out"))
STEP2_RUN = OUT_ROOT / "2026c" / "cv_field_c1yolo_video_20261005_1848"
P0_RUN = OUT_ROOT / "2026c" / "cv_field_wiser_assist_p0_20261005_2211"
NAME = "cv_field_c1yolo_review_gui"
COHORT = "2026c"
DEST = "cv/configs/c1yolo_review_2026c"
TOOL = "cv/cv_field/c1yolo_review_gui.py"
SCHEMA = "c1yolo_review/1"
FPS = 20
SPOT_VERDICTS = [["object", "object (not a rat)"], ["rat", "rat"], ["unsure", "unsure"]]
EP_VERDICTS = [["visible_missed", "rat visible, no YOLO box (real miss)"], ["occluded", "rat there but hidden"],
               ["not_there_wiser_wrong", "no rat there (WISER wrong)"], ["box_present", "YOLO has a box on it"], ["unsure", "unsure"]]
OCC_KINDS = [["pole", "by pole"], ["house", "by house"], ["grass", "by grass"], ["other", "other"]]
CROP_ROLES = ("first", "middle", "last", "nobox")
EXPORT_COLS = ["step", "item_id", "clip", "animal", "verdict", "occluder_kind", "notes", "saved_at", "episode_id", "verdict_first",
               "verdict_final", "changed", "first_saved_at", "reviewer", "status"]


def uri(p: Path) -> str:
    return Path(p).resolve().as_uri()


# ----------------------------------------------------------------------------------------------- payload
def spot_payload(step2: Path) -> tuple[list[dict], dict, list[Path]]:
    fs = step2 / "fixed_spots"
    sp = pd.read_csv(fs / "fixed_spots.csv")
    fr = pd.read_csv(step2 / "frames.csv.gz", usecols=["frame", "t_pc"]).set_index("frame")["t_pc"]
    media, spots = [fs / "locator.png", fs / "heatmap.png"], []
    occ_cols = sorted(c for c in sp.columns if c.startswith("occ_min"))
    for r in sp.itertuples():
        crops = []
        for role in CROP_ROLES:
            fsel = sorted((fs / "crops").glob(f"spot{int(r.spot_id):02d}_{role}_f*.png"))
            if fsel:
                k = int(re.search(r"_f(\d+)\.png$", fsel[0].name).group(1))
                crops.append({"role": role, "url": uri(fsel[0]), "frame": k, "t_pc": str(fr.get(k, ""))[11:23]})
                media.append(fsel[0])
            else:
                crops.append({"role": role, "url": "", "frame": None, "t_pc": "", "missing": True})
        spots.append({"item_id": f"spot_{int(r.spot_id)}", "spot_id": int(r.spot_id), "cx": round(float(r.cx_median), 1),
                      "cy": round(float(r.cy_median), 1), "occupancy": float(r.occupancy), "n_frames_with_box": int(r.n_frames_with_box),
                      "conf_median": float(r.conf_median), "w": float(r.w_median), "h": float(r.h_median), "cx_sd": float(r.cx_sd),
                      "cy_sd": float(r.cy_sd), "cells": int(r.n_cells), "minutes": [round(float(getattr(r, c)), 4) for c in occ_cols],
                      "crops": crops})
    imgs = {"locator": uri(fs / "locator.png"), "heatmap": uri(fs / "heatmap.png")}
    return spots, imgs, media


def episode_payload(step2: Path, p0: Path) -> tuple[list[dict], list[dict], list[Path]]:
    """-> (groups = the 12 old shared clips with their rows (episode item ids), unique episodes with their own clip, media).
    Seek offsets inside each episode's own clip are exact: the clip holds every source frame of its window at 20 fps."""
    clips = pd.read_csv(p0 / "review_clips" / "clips.csv")
    pe_dir = p0 / "review_clips_per_episode"
    pe = pd.read_csv(pe_dir / "clips_per_episode.csv").set_index("episode_id")
    ep = pd.read_csv(p0 / "fn_episodes.csv", usecols=["episode_id", "animal", "start_sec", "end_sec", "duration_s", "start_t_pc",
                                                      "end_t_pc", "start_frame", "end_frame"]).set_index("episode_id")
    fr = pd.read_csv(step2 / "frames.csv.gz", usecols=["frame", "pts_s"])
    pts, fid = fr["pts_s"].to_numpy(float), fr["frame"].to_numpy(int)
    groups, episodes, seen, media = [], [], set(), []
    for c in clips.sort_values("k").itertuples():
        ids = sorted(int(x) for x in str(c.episodes_covered).split(";"))
        groups.append({"k": int(c.k), "window": str(c.window), "primary_animal": str(c.animal), "primary_episode": int(c.episode_id),
                       "rows": [f"ep{e}" for e in ids]})
        for e in ids:
            if e in seen:
                continue
            seen.add(e)
            r, q = ep.loc[e], pe.loc[e]
            w0, w1 = float(q.window_start_sec), float(q.window_end_sec)
            cf = fid[(pts >= w0 - 1e-6) & (pts < w1 - 1e-6)]
            dur = len(cf) / FPS
            s0 = float((cf < int(r.start_frame)).sum()) / FPS
            s1 = float((cf <= int(r.end_frame)).sum()) / FPS
            media.append(pe_dir / q.file)
            episodes.append({"item_id": f"ep{e}", "episode_id": e, "animal": str(r.animal), "start": str(r.start_t_pc)[11:19],
                             "end": str(r.end_t_pc)[11:19], "duration_s": int(r.duration_s),
                             "clip": {"file": str(q.file), "url": uri(pe_dir / q.file), "window": str(q.window), "duration_s": round(dur, 2),
                                      "n_frames": int(len(cf)), "seek_s": round(s0, 3), "end_s": round(min(s1, dur), 3),
                                      "capped": bool(q.capped), "ends_after_clip": bool(int(r.end_sec) >= w1)}})
    return groups, episodes, media


def build_payload(step2: Path = STEP2_RUN, p0: Path = P0_RUN, run_id: str = "gui") -> tuple[dict, list[Path]]:
    spots, imgs, m1 = spot_payload(step2)
    groups, episodes, m2 = episode_payload(step2, p0)
    help_ = [
        "Step 1 first. Judge the two fixed spots — places where YOLO keeps a box in the same spot for long stretches of the hour. For each, "
        "look at the locator / heatmap and the four crops (first, middle and last frame with a box, and the nearest frame without one) and "
        "answer object (a thing, not a rat) / rat / unsure; add notes if useful. Save each spot. Optionally write where you see consistent "
        "misses (pano x/y or field-PC time + clip) and save that note.",
        "Step 2 unlocks only after both spot verdicts are saved: the WISER circles in the clips show where the tagged rats were, which is "
        "exactly what the fixed-spot test checks, so judge the spots first.",
        "Step 2: one row per suspected-miss episode (a tagged rat, by WISER, in CH01's view for ≥ 3 s with no YOLO box within 20 in), "
        "grouped by the 12 earlier clips for context; episode 204 sits in two groups but is one item. Selecting a row loads THAT episode's own "
        "clip (episode start − 3 s to end + 3 s, at most 90 s) and shows 'Now viewing: SFxx, episode N' above the video. In the clip: top = whole "
        "panorama; bottom left = native crop following the target rat; bottom right = panel with 'TARGET: SFxx (episode N)'. Red circle = the "
        "target rat, cyan = other tagged rats, radius ≈ 14 in (WISER position ± error); dimmed / dashed = WISER puts it in a house zone; green "
        "boxes = YOLO v5. ⇥ seeks to the episode start.",
        "Verdicts per episode: visible_missed = the rat is visible and YOLO has no box on it (a real detector miss); occluded = a rat is there but "
        "hidden (choose: pole / house / grass / other) — a hidden rat never gets a box; not_there_wiser_wrong = no rat at or near the red "
        "circle; box_present = YOLO does box the rat; unsure. Notes are free text. Save each episode (Save button or Enter on the selected row).",
        "Your first saved verdict is kept as verdict_first; if you change and save again, the new one is verdict_final and changed = true. "
        "Everything autosaves in this browser (localStorage). Export CSV and JSON when done and move both files into " + DEST + "/ of the "
        "analysis repo (the file names start with that path). Import restores a previous JSON export.",
    ]
    payload = {"cohort": COHORT, "run_id": run_id, "tool": TOOL, "schema": SCHEMA, "generated": time.strftime("%Y-%m-%d %H:%M"),
               "dest": DEST, "fps": FPS, "spot_verdicts": SPOT_VERDICTS, "ep_verdicts": EP_VERDICTS, "occ_kinds": OCC_KINDS,
               "sources": {"fixed_spots": (step2 / "fixed_spots").as_posix(), "review_clips": (p0 / "review_clips_per_episode").as_posix(),
                           "groups": (p0 / "review_clips" / "clips.csv").as_posix(), "episodes": (p0 / "fn_episodes.csv").as_posix()},
               "images": imgs, "spots": spots, "groups": groups, "episodes": episodes, "help": help_}
    return payload, m1 + m2


# ----------------------------------------------------------------------------------------------- HTML
HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>CH01 YOLO review — fixed spots, then WISER suspected misses</title>
<style>
:root{--bg:#111418;--panel:#1a1f26;--line:#2c333d;--fg:#e6e9ee;--mut:#98a2b0;--acc:#6db3ff;--ok:#3fbf6f;--warn:#e0a030;--bad:#e05050}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,Segoe UI,Arial,sans-serif}
header{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:6px 10px;background:var(--panel);border-bottom:1px solid var(--line)}
button,.btn,select,input,textarea{background:#232a33;color:var(--fg);border:1px solid var(--line);border-radius:4px;padding:3px 8px;font:inherit}
button:hover,.btn:hover{border-color:var(--acc);cursor:pointer}button.primary{background:#1d4e89}button.on{background:#2f6b3a;border-color:var(--ok)}
.mut{color:var(--mut)}.warn{color:var(--warn)}.okc{color:var(--ok)}
main{padding:8px 12px;max-width:2000px;margin:0 auto}
section{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:8px 12px;margin:10px 0}
h2{margin:4px 0 8px;font-size:18px}h3{margin:6px 0;font-size:15px}
.imgs img{width:100%;max-width:1920px;display:block;margin:4px 0;border-radius:3px;background:#000}
.spot{border:1px solid var(--line);border-radius:6px;padding:8px;margin:10px 0}
.crops{display:flex;flex-wrap:wrap;gap:8px}.crops figure{margin:0}.crops img{width:300px;height:300px;object-fit:contain;background:#000;border-radius:3px}
.crops figcaption{font-size:12px;color:var(--mut)}
table{border-collapse:collapse}td,th{border-bottom:1px solid var(--line);padding:2px 6px;text-align:left;vertical-align:top;font-size:13px}th{color:var(--mut);font-weight:500}
.raster{display:flex;gap:1px;margin:4px 0}.raster span{display:inline-block;width:12px;height:18px;border-radius:1px}
.vbtns{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
textarea{width:100%;min-height:44px}
.state{font-size:12px;margin-left:6px}
#locked{padding:14px;color:var(--warn);font-weight:600}
#s2grid{display:grid;grid-template-columns:minmax(380px,1fr) minmax(0,2fr);gap:12px;align-items:start}
#eplist{max-height:calc(100vh - 70px);overflow:auto;padding-right:4px}
#player{position:sticky;top:52px}
#nowviewing{font-size:24px;font-weight:700;color:#ff6b6b;margin:2px 0 4px}
.grouphead{color:var(--mut);font-size:12px;margin:12px 0 2px;border-top:1px solid var(--line);padding-top:4px}
.ep .view{font-weight:600}
video{width:100%;max-height:72vh;background:#000;border-radius:4px}
#controls{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:4px 0}
#tread{font-variant-numeric:tabular-nums;color:var(--mut)}
.ep{border:1px solid var(--line);border-radius:5px;padding:6px 8px;margin:6px 0}.ep.sel{border-color:var(--acc)}
.ep .head{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#444}.dot.draft{background:var(--warn)}.dot.saved{background:var(--ok)}
#help{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:10}
#help.show{display:flex}#help .card{background:var(--panel);border:1px solid var(--line);border-radius:6px;max-width:980px;max-height:88vh;overflow:auto;padding:14px 18px}
kbd{border:1px solid var(--line);border-radius:3px;background:#0b0e12;color:var(--mut);font-size:11px;padding:0 4px}
</style></head><body>
<header>
 <b>CH01 YOLO review · cohort __COHORT__</b>
 <span id="progress"></span>
 <label>Reviewer <input id="reviewer" size="8" placeholder="initials"></label>
 <button id="btnCsv" title="download all verdicts as CSV">Export CSV</button>
 <button id="btnJson" title="download all verdicts as JSON">Export JSON</button>
 <button id="btnDir" title="write both files straight into a folder you pick (Chrome / Edge); else use Export">Save both into folder…</button>
 <label class="btn" title="restore a previous JSON export">Import JSON<input type="file" id="importFile" accept=".json,application/json" hidden></label>
 <button id="btnHelp">Help (?)</button>
 <span id="saved" class="mut"></span>
</header>
<main>
<div class="mut" id="destnote"></div>
<section id="step1">
 <h2>Step 1 — YOLO fixed spots <span class="mut" id="s1prog"></span></h2>
 <div class="mut">Places where YOLO keeps a box for long stretches of the hour. Judge each: object / rat / unsure. Step 2 unlocks when both are saved.</div>
 <div class="imgs"><h3>Locator (median of 60 frames, one per minute; spot outlines in red)</h3><img id="imgLocator" alt="locator">
 <h3>Box-centre occupancy heatmap (same scale)</h3><img id="imgHeat" alt="heatmap"></div>
 <div id="spots"></div>
 <div class="spot"><h3>Where are the consistent misses? <span class="mut">(free text; pano x/y or field-PC time + clip per line)</span></h3>
  <textarea id="fnNotes" placeholder="e.g. x 6500 y 1200, 21:41:40 clip 01 …"></textarea>
  <button id="fnSave">Save note</button><span class="state" id="fnState"></span></div>
</section>
<section id="step2">
 <h2>Step 2 — WISER suspected misses <span class="mut" id="s2prog"></span></h2>
 <div id="locked">Locked: save both Step-1 spot verdicts first (the WISER circles in these clips would reveal what the fixed-spot test checks).</div>
 <div id="s2body" hidden>
  <div id="s2grid">
   <div id="eplist"></div>
   <div id="player">
    <div id="nowviewing">Select an episode on the left</div>
    <div id="cliphead" class="mut"></div>
    <video id="vid" preload="metadata" playsinline></video>
    <div id="controls">
     <button id="bPlay" title="Space">▶ / ❚❚</button>
     <button id="bBackS" title="Shift+←">−1 s</button><button id="bBackF" title="←">−1 frame</button>
     <button id="bFwdF" title="→">+1 frame</button><button id="bFwdS" title="Shift+→">+1 s</button>
     <span>speed</span><button data-r="0.5" title="[">0.5×</button><button data-r="1" title="\">1×</button><button data-r="2" title="]">2×</button>
     <button id="bSeek" title="j">⇥ episode start</button>
     <span id="tread"></span>
    </div>
   </div>
  </div>
 </div>
</section>
</main>
<div id="help"><div class="card" id="helpcard"></div></div>
<script>
"use strict";
// ------------------------------------------------------------------ data + pure logic (no DOM; the self-test runs this block in node)
const DATA = __DATA_JSON__;
const SPOTS = DATA.spots, GROUPS = DATA.groups, EPS = DATA.episodes;
const ROWS = [];                                  // displayed rows: grouped by the old shared clips (an episode can sit in two)
GROUPS.forEach(g => g.rows.forEach(id => ROWS.push({item_id: id, k: g.k})));
const ITEMS = [].concat(SPOTS.map(s => ({item_id: s.item_id, step: 1, clip: "", animal: "", episode_id: "", kind: "spot"})),
  [{item_id: "fn_notes", step: 1, clip: "", animal: "", episode_id: "", kind: "notes"}],
  EPS.map(e => ({item_id: e.item_id, step: 2, clip: e.clip.file, animal: e.animal, episode_id: e.episode_id, kind: "episode"})));
function epById(id){ return EPS.find(e => e.item_id === id); }
let J = {}, reviewer = "";
function nowIso(){ return new Date().toISOString(); }
function item(id){ return ITEMS.find(x => x.item_id === id); }
function jget(id){
  if (!J[id]) J[id] = {verdict: "", occluder_kind: "", notes: "", s_verdict: "", s_occluder_kind: "", s_notes: "", saved_at: "",
                       verdict_first: "", first_saved_at: "", n_saves: 0, updated: ""};
  return J[id];
}
function options(id){ const it = item(id); return !it ? [] : it.kind === "spot" ? DATA.spot_verdicts : it.kind === "episode" ? DATA.ep_verdicts : []; }
function isSaved(id){ const j = J[id]; return !!(j && j.saved_at); }
function dirty(id){ const j = J[id]; return !!j && (j.verdict !== j.s_verdict || j.occluder_kind !== j.s_occluder_kind || j.notes !== j.s_notes); }
function status(id){ return isSaved(id) ? (dirty(id) ? "draft" : "saved") : (J[id] && (J[id].verdict || J[id].notes) ? "draft" : "todo"); }
function step2Unlocked(){ return SPOTS.every(s => isSaved(s.item_id)); }
function setVerdict(id, v){
  if (!options(id).some(o => o[0] === v)) return false;
  const j = jget(id); j.verdict = (j.verdict === v) ? "" : v;
  if (j.verdict !== "occluded") j.occluder_kind = "";
  j.updated = nowIso(); return true;
}
function setOccluder(id, k){
  const j = jget(id);
  if (j.verdict !== "occluded" || !DATA.occ_kinds.some(o => o[0] === k)) return false;
  j.occluder_kind = (j.occluder_kind === k) ? "" : k; j.updated = nowIso(); return true;
}
function setNotes(id, t){ const j = jget(id); j.notes = String(t); j.updated = nowIso(); }
function saveItem(id){
  const it = item(id); if (!it) return {ok: false, msg: "unknown item"};
  if (it.step === 2 && !step2Unlocked()) return {ok: false, msg: "Step 2 is locked until both spot verdicts are saved."};
  const j = jget(id);
  if (it.kind !== "notes" && !j.verdict) return {ok: false, msg: "Choose a verdict first."};
  if (j.verdict === "occluded" && !j.occluder_kind) return {ok: false, msg: "Occluded by what? Choose pole / house / grass / other."};
  const t = nowIso();
  if (!j.first_saved_at) { j.first_saved_at = t; j.verdict_first = j.verdict; }
  j.s_verdict = j.verdict; j.s_occluder_kind = j.occluder_kind; j.s_notes = j.notes; j.saved_at = t; j.n_saves = (j.n_saves || 0) + 1;
  j.updated = t; return {ok: true, msg: ""};
}
function counts(){
  const s1 = SPOTS.filter(s => isSaved(s.item_id)).length, s2 = EPS.filter(e => isSaved(e.item_id)).length;
  return {spots_saved: s1, n_spots: SPOTS.length, episodes_saved: s2, n_episodes: EPS.length};
}
function exportRows(){
  return ITEMS.map(it => { const j = J[it.item_id] || {};
    const vf = j.verdict_first || "", vl = j.s_verdict || "";
    return {step: it.step, item_id: it.item_id, clip: it.clip, animal: it.animal, verdict: vl, occluder_kind: j.s_occluder_kind || "",
      notes: j.s_notes || "", saved_at: j.saved_at || "", episode_id: it.episode_id, verdict_first: vf,
      verdict_final: j.saved_at ? vl : "", changed: !!(j.saved_at && vf !== vl), first_saved_at: j.first_saved_at || "",
      reviewer: reviewer, status: status(it.item_id)}; });
}
function exportObject(){
  return {schema: DATA.schema, cohort: DATA.cohort, run_id: DATA.run_id, tool: DATA.tool, generated: DATA.generated, dest: DATA.dest,
    sources: DATA.sources, exported_local: new Date().toString(), reviewer: reviewer, counts: counts(),
    note: "verdict = the last saved verdict; verdict_first = the first saved one; changed = they differ. Unsaved drafts are not exported as verdicts.",
    rows: exportRows(), state: J};
}
function csvText(){
  const R = exportRows(), cols = Object.keys(R[0]);
  const q = v => { const s = String(v == null ? "" : v); return /[",\n\r]/.test(s) ? "\"" + s.replace(/"/g, "\"\"") + "\"" : s; };
  return [cols.join(",")].concat(R.map(r => cols.map(c => q(r[c])).join(","))).join("\r\n") + "\r\n";
}
// ---- migration of the old Step-2 item ids c<k>_ep<id> (one per shared clip) to the per-episode ids ep<id>
function oldToNew(id){ const m = /^c(\d+)_ep(\d+)$/.exec(String(id)); return m ? "ep" + Number(m[2]) : null; }
function hasContent(j){ return !!(j && (j.saved_at || j.verdict || j.notes)); }
function mergeOld(entries){
  // current state = the entry saved last (else the one updated last); verdict_first = the earliest first save of any entry
  const key = e => String(e.saved_at || e.updated || "");
  const saved = entries.filter(e => e && e.saved_at);
  const base = Object.assign({}, (saved.length ? saved : entries).slice().sort((a, b) => key(a).localeCompare(key(b))).pop());
  if (saved.length) {
    const fk = e => String(e.first_saved_at || e.saved_at);
    const first = saved.slice().sort((a, b) => fk(a).localeCompare(fk(b)))[0];
    base.verdict_first = first.verdict_first || first.s_verdict || "";
    base.first_saved_at = first.first_saved_at || first.saved_at;
    base.n_saves = saved.reduce((s, e) => s + (e.n_saves || 1), 0);
  }
  return base;
}
function migrateState(S, overwrite){
  const groups = {};
  Object.keys(S || {}).forEach(k => { const nid = oldToNew(k); if (nid && item(nid) && hasContent(S[k])) (groups[nid] = groups[nid] || []).push(Object.assign({}, S[k], {_from: k})); });
  let n = 0;
  Object.keys(groups).forEach(nid => {
    if (!overwrite && hasContent(J[nid])) return;      // already migrated (or answered under the new id): never overwrite
    const m = mergeOld(groups[nid]); m.migrated_from = groups[nid].map(e => e._from).sort(); delete m._from;
    J[nid] = Object.assign(jget(nid), m); n++;
  });
  return n;
}
function importObject(o){
  // accepts the current export (state keyed by item ids) and the old one (Step-2 state keyed c<k>_ep<id>); old keys are
  // also kept in the state as a backup
  const src = (o && o.state) || {}; let n = 0;
  Object.keys(src).forEach(id => {
    if (!src[id]) return;
    if (item(id)) { J[id] = Object.assign(jget(id), src[id]); n++; }
    else if (oldToNew(id)) J[id] = Object.assign({}, src[id]);
  });
  n += migrateState(src, true);
  if (o && o.reviewer && !reviewer) reviewer = o.reviewer;
  return n;
}
function fname(ext, stamp){ return DATA.dest.replace(/\//g, "-") + "__review_" + (reviewer || "anon").replace(/[^A-Za-z0-9_-]/g, "") + "_" + stamp + "." + ext; }
</script>
<script>
"use strict";
// ------------------------------------------------------------------ UI
const KEY = "c1yolo_review_" + DATA.cohort + "_" + DATA.run_id;
const $ = id => document.getElementById(id);
const vid = $("vid");
let curRow = 0, pendingSeek = null, migratedOnLoad = 0;
function esc(s){ return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }
function loadState(){
  try { const s = JSON.parse(localStorage.getItem(KEY) || "null");
    if (s && typeof s === "object") { J = s.judgements || {}; reviewer = s.reviewer || "";
      if (Number.isInteger(s.curRow) && s.curRow >= 0 && s.curRow < ROWS.length) curRow = s.curRow; }
  } catch (e) { console.warn("localStorage unavailable", e); }
  migratedOnLoad = migrateState(J, false);           // old c<k>_ep<id> verdicts -> ep<id>; the old keys stay as a backup
}
function saveState(){
  try { localStorage.setItem(KEY, JSON.stringify({judgements: J, reviewer: reviewer, curRow: curRow, saved: nowIso()}));
    $("saved").textContent = "autosaved " + new Date().toLocaleTimeString();
  } catch (e) { $("saved").innerHTML = "<span class='warn'>autosave unavailable — Export often</span>"; }
}
function stateLabel(id){
  const s = status(id), j = J[id] || {};
  if (s === "saved") return "<span class='okc'>saved " + esc((j.saved_at || "").slice(11, 19)) + " UTC" + (j.verdict_first && j.verdict_first !== j.s_verdict ? " · changed from " + esc(j.verdict_first) : "") + "</span>";
  if (s === "draft") return "<span class='warn'>" + (isSaved(id) ? "changed, not saved" : "not saved") + "</span>";
  return "<span class='mut'>to do</span>";
}
function progress(){
  const c = counts();
  $("progress").textContent = "Step 1: " + c.spots_saved + " / " + c.n_spots + " · Step 2: " + c.episodes_saved + " of " + c.n_episodes + " done";
  $("s1prog").textContent = "(" + c.spots_saved + " / " + c.n_spots + " saved)";
  $("s2prog").textContent = "(" + c.episodes_saved + " of " + c.n_episodes + " episodes done; " + ROWS.length + " rows — episodes shown in two groups share one verdict)";
}
// ---------------------------------------------------------------- step 1
function rasterHtml(m){
  return "<div class='raster'>" + m.map((v, i) => { const g = Math.round(255 - 200 * Math.min(1, v));
    return "<span title='21:" + String(i).padStart(2, "0") + " — " + (100 * v).toFixed(1) + " % of frames with a box' style='background:rgb(" + g + "," + g + ",255)'></span>"; }).join("") +
    "</div><div class='mut' style='font-size:12px'>per minute 21:00 → 22:00, share of frames with a box in the spot (darker = more)</div>";
}
function renderSpots(){
  $("spots").innerHTML = SPOTS.map(s => { const j = jget(s.item_id);
    return "<div class='spot' id='sp_" + s.item_id + "'><h3>Spot " + s.spot_id + "</h3>" +
      "<table><tr><th>pano centre (x, y)</th><td>" + s.cx + ", " + s.cy + " px</td><th>occupancy</th><td>" + (100 * s.occupancy).toFixed(1) + " % of frames (" + s.n_frames_with_box + ")</td></tr>" +
      "<tr><th>median conf</th><td>" + s.conf_median.toFixed(2) + "</td><th>median box w × h</th><td>" + s.w.toFixed(0) + " × " + s.h.toFixed(0) + " px</td></tr>" +
      "<tr><th>centre SD x / y</th><td>" + s.cx_sd.toFixed(1) + " / " + s.cy_sd.toFixed(1) + " px</td><th>40-px cells</th><td>" + s.cells + "</td></tr></table>" +
      rasterHtml(s.minutes) +
      "<div class='crops'>" + s.crops.map(c => c.url ? "<figure><a href='" + esc(c.url) + "' target='_blank'><img src='" + esc(c.url) + "' alt='" + esc(c.role) + "'></a><figcaption>" + esc(c.role) + " · frame " + c.frame + " · " + esc(c.t_pc) + "</figcaption></figure>"
        : "<figure><figcaption class='warn'>" + esc(c.role) + ": no crop</figcaption></figure>").join("") + "</div>" +
      "<div class='vbtns'>" + DATA.spot_verdicts.map(o => "<button data-item='" + s.item_id + "' data-v='" + o[0] + "' class='" + (j.verdict === o[0] ? "on" : "") + "'>" + esc(o[1]) + "</button>").join("") + "</div>" +
      "<textarea data-notes='" + s.item_id + "' placeholder='notes (optional)'>" + esc(j.notes) + "</textarea>" +
      "<button class='primary' data-save='" + s.item_id + "'>Save spot " + s.spot_id + "</button><span class='state'>" + stateLabel(s.item_id) + "</span><span class='state warn' id='msg_" + s.item_id + "'></span></div>"; }).join("");
  bindItemControls($("spots"));
  const fj = jget("fn_notes"); if (document.activeElement !== $("fnNotes")) $("fnNotes").value = fj.notes; $("fnState").innerHTML = stateLabel("fn_notes");
}
function bindItemControls(root){
  root.querySelectorAll("button[data-v]").forEach(b => b.onclick = () => { setVerdict(b.dataset.item, b.dataset.v); saveState(); rerender(); });
  root.querySelectorAll("button[data-occ]").forEach(b => b.onclick = () => { setOccluder(b.dataset.item, b.dataset.occ); saveState(); rerender(); });
  root.querySelectorAll("textarea[data-notes]").forEach(t => t.oninput = () => { setNotes(t.dataset.notes, t.value); saveState(); progress(); });
  root.querySelectorAll("button[data-save]").forEach(b => b.onclick = () => doSave(b.dataset.save));
}
function doSave(id){
  const r = saveItem(id); saveState(); rerender();
  const ms = [$("msg_" + id)].concat(Array.from(document.querySelectorAll("[data-msg='" + id + "']"))).filter(Boolean);
  ms.forEach(m => m.textContent = r.ok ? "" : r.msg);
  if (!r.ok && !ms.length) alert(r.msg);
  return r.ok;
}
// ---------------------------------------------------------------- step 2
function rowHtml(i){
  const r = ROWS[i], e = epById(r.item_id), j = jget(e.item_id), c = e.clip;
  return "<div class='ep" + (i === curRow ? " sel" : "") + "' data-row='" + i + "'><div class='head'><span class='dot " + status(e.item_id) + "'></span>" +
    "<button class='view' data-view='" + i + "' title='load this episode&#39;s own clip'>▶ view</button><b>episode " + e.episode_id + "</b> · <b>" + esc(e.animal) + "</b>" +
    " · " + esc(e.start) + " → " + esc(e.end) + " (" + e.duration_s + " s)" + (c.capped ? " <span class='mut'>(clip shows the first 87 s)</span>" : "") +
    " <button data-seek='" + i + "' title='seek to the episode start in its clip (j)'>⇥ start</button><span class='state'>" + stateLabel(e.item_id) + "</span></div>" +
    "<div class='vbtns'>" + DATA.ep_verdicts.map(o => "<button data-item='" + e.item_id + "' data-v='" + o[0] + "' title='" + esc(o[1]) + "' class='" + (j.verdict === o[0] ? "on" : "") + "'>" + esc(o[0]) + "</button>").join("") + "</div>" +
    (j.verdict === "occluded" ? "<div class='vbtns'><span class='mut'>occluded by:</span>" + DATA.occ_kinds.map(o => "<button data-item='" + e.item_id + "' data-occ='" + o[0] + "' class='" + (j.occluder_kind === o[0] ? "on" : "") + "'>" + esc(o[1]) + "</button>").join("") + "</div>" : "") +
    "<textarea data-notes='" + e.item_id + "' placeholder='notes (optional)'>" + esc(j.notes) + "</textarea>" +
    "<button class='primary' data-save='" + e.item_id + "'>Save episode " + e.episode_id + "</button><span class='state warn' data-msg='" + e.item_id + "'></span></div>";
}
function renderStep2(){
  const open = step2Unlocked();
  $("locked").hidden = open; $("s2body").hidden = !open;
  if (!open) { if (vid.getAttribute("src")) { vid.pause(); vid.removeAttribute("src"); vid.load(); vid.dataset.url = ""; } return; }
  const box = $("eplist"), top = box.scrollTop;
  let i = 0, h = "";
  GROUPS.forEach(g => {
    h += "<div class='grouphead'>earlier clip " + String(g.k).padStart(2, "0") + " · " + esc(g.window) + " · " + g.rows.length + " episode(s)</div>";
    g.rows.forEach(() => { h += rowHtml(i); i++; });
  });
  box.innerHTML = h; box.scrollTop = top;
  bindItemControls(box);
  box.querySelectorAll("button[data-view]").forEach(b => b.onclick = () => selectRow(+b.dataset.view, true));
  box.querySelectorAll("button[data-seek]").forEach(b => b.onclick = () => { selectRow(+b.dataset.seek, true); });
  box.querySelectorAll(".ep .head").forEach(d => d.addEventListener("click", ev => { if (ev.target.tagName !== "BUTTON") selectRow(+d.parentNode.dataset.row, true); }));
  loadCurrent(false);
}
function loadCurrent(seek){
  const e = epById(ROWS[curRow].item_id), c = e.clip;
  $("nowviewing").textContent = "Now viewing: " + e.animal + ", episode " + e.episode_id;
  $("cliphead").innerHTML = "episode " + esc(e.start) + " → " + esc(e.end) + " (" + e.duration_s + " s) · clip " + esc(c.file) + " · field-PC " + esc(c.window) +
    " (" + c.duration_s.toFixed(0) + " s) · the episode starts at " + c.seek_s.toFixed(1) + " s of the clip · red circle = this rat";
  if (vid.dataset.url !== c.url) { vid.dataset.url = c.url; pendingSeek = c.seek_s; vid.src = c.url; vid.load(); }
  else if (seek) { vid.pause(); vid.currentTime = c.seek_s; }
}
function selectRow(i, seek){
  curRow = Math.max(0, Math.min(ROWS.length - 1, i)); saveState();
  $("eplist").querySelectorAll(".ep").forEach(d => d.classList.toggle("sel", +d.dataset.row === curRow));
  const sel = $("eplist").querySelector(".ep.sel"); if (sel) sel.scrollIntoView({block: "nearest"});
  loadCurrent(seek);
}
function seekEp(){ const c = epById(ROWS[curRow].item_id).clip; vid.pause(); vid.currentTime = Math.max(0, c.seek_s); }
function rerender(){ renderSpots(); renderStep2(); progress(); }
function curClip(){ return epById(ROWS[curRow].item_id).clip; }
function drawTread(){ const c = curClip(); $("tread").textContent = "clip " + (vid.currentTime || 0).toFixed(2) + " s · field-PC " + c.window.slice(0, 8) + " + " + (vid.currentTime || 0).toFixed(2) + " s · " + vid.playbackRate + "×"; }
vid.addEventListener("loadedmetadata", () => { if (pendingSeek != null) { vid.currentTime = Math.max(0, pendingSeek); pendingSeek = null; } });
["seeked", "timeupdate", "pause", "loadeddata", "ratechange"].forEach(n => vid.addEventListener(n, drawTread));
vid.addEventListener("error", () => { if (vid.dataset.url) $("tread").innerHTML = "<span class='warn'>cannot load " + esc(vid.dataset.url) + " — the clip must stay at that path</span>"; });
function stepBy(dt){ vid.pause(); vid.currentTime = Math.max(0, Math.min((vid.duration || curClip().duration_s) - 0.001, (vid.currentTime || 0) + dt)); }
function setRate(r){ vid.playbackRate = r; vid.defaultPlaybackRate = r; drawTread(); }
$("bPlay").onclick = () => { vid.paused ? vid.play() : vid.pause(); };
$("bBackS").onclick = () => stepBy(-1); $("bFwdS").onclick = () => stepBy(1);
$("bBackF").onclick = () => stepBy(-1 / DATA.fps); $("bFwdF").onclick = () => stepBy(1 / DATA.fps);
$("bSeek").onclick = seekEp;
document.querySelectorAll("#controls button[data-r]").forEach(b => b.onclick = () => setRate(parseFloat(b.dataset.r)));
document.addEventListener("keydown", e => {
  const t = e.target, tag = t && t.tagName ? t.tagName : "";
  if (tag === "TEXTAREA" || (tag === "INPUT" && t.type !== "radio")) { if (e.key === "Escape") t.blur(); return; }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if ($("help").classList.contains("show")) { if (e.key === "Escape" || e.key === "?") $("help").classList.remove("show"); return; }
  if (e.key === "?") { $("help").classList.add("show"); return; }
  if (!step2Unlocked()) return;
  const k = e.key;
  if (k === " ") { e.preventDefault(); vid.paused ? vid.play() : vid.pause(); }
  else if (k === "ArrowLeft") { e.preventDefault(); stepBy(e.shiftKey ? -1 : -1 / DATA.fps); }
  else if (k === "ArrowRight") { e.preventDefault(); stepBy(e.shiftKey ? 1 : 1 / DATA.fps); }
  else if (k === "[") setRate(0.5); else if (k === "\\") setRate(1); else if (k === "]") setRate(2);
  else if (k === "j") seekEp();
  else if (k === "ArrowDown" || k === "n") { e.preventDefault(); selectRow(curRow + 1, true); }
  else if (k === "ArrowUp" || k === "p") { e.preventDefault(); selectRow(curRow - 1, true); }
  else if (k === "Enter") { e.preventDefault(); doSave(ROWS[curRow].item_id); }
});
// ---------------------------------------------------------------- export / import
function stamp(){ const d = new Date(), p = n => String(n).padStart(2, "0"); return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + "_" + p(d.getHours()) + p(d.getMinutes()); }
function download(name, text, mime){ const b = new Blob([text], {type: mime}), a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500); }
$("btnCsv").onclick = () => download(fname("csv", stamp()), csvText(), "text/csv");
$("btnJson").onclick = () => download(fname("json", stamp()), JSON.stringify(exportObject(), null, 1), "application/json");
$("btnDir").onclick = async () => {
  if (!window.showDirectoryPicker) { alert("This browser cannot write into a folder from a local page. Use Export CSV and Export JSON, then move both files into " + DATA.dest + "/."); return; }
  try { const dir = await window.showDirectoryPicker({mode: "readwrite"}), st = stamp();
    for (const [ext, text] of [["csv", csvText()], ["json", JSON.stringify(exportObject(), null, 1)]]) {
      const fh = await dir.getFileHandle(fname(ext, st), {create: true}), w = await fh.createWritable(); await w.write(text); await w.close(); }
    alert("Both files written into the folder you chose (" + dir.name + "). The intended folder is " + DATA.dest + "/ of the analysis repo.");
  } catch (err) { if (err && err.name !== "AbortError") alert("Could not write (" + err + "). Use Export CSV / JSON instead."); }
};
$("importFile").onchange = e => { const f = e.target.files[0]; if (!f) return; const rd = new FileReader();
  rd.onload = () => { try { const n = importObject(JSON.parse(rd.result)); $("reviewer").value = reviewer; saveState(); rerender(); alert("Imported " + n + " items from " + f.name); }
    catch (err) { alert("Import failed: " + err); } }; rd.readAsText(f); e.target.value = ""; };
$("reviewer").oninput = () => { reviewer = $("reviewer").value.trim(); saveState(); };
$("fnNotes").oninput = () => { setNotes("fn_notes", $("fnNotes").value); saveState(); $("fnState").innerHTML = stateLabel("fn_notes"); };
$("fnSave").onclick = () => doSave("fn_notes");
$("btnHelp").onclick = () => $("help").classList.add("show");
$("help").onclick = e => { if (e.target === $("help")) $("help").classList.remove("show"); };
$("helpcard").innerHTML = "<h3 style='margin-top:0'>How to review</h3><p>" + DATA.help.map(esc).join("</p><p>") + "</p><h4>Keyboard (Step 2)</h4><table>" +
  [["Space", "play / pause"], ["← / →", "one frame (1/" + DATA.fps + " s); Shift = 1 s"], ["[ / \\ / ]", "0.5× / 1× / 2×"], ["j", "seek to the selected episode"],
   ["↑ / ↓", "select the previous / next episode row"], ["n / p", "next / previous clip"], ["Enter", "save the selected episode"], ["? / Esc", "this help"]]
  .map(r => "<tr><td><kbd>" + esc(r[0]) + "</kbd></td><td>" + esc(r[1]) + "</td></tr>").join("") + "</table><p class='mut'>" + esc(DATA.tool) + " · generated " + esc(DATA.generated) +
  " · sources: " + esc(DATA.sources.fixed_spots) + " ; " + esc(DATA.sources.review_clips) + "</p><p><button onclick=\"document.getElementById('help').classList.remove('show')\">close (Esc)</button></p>";
$("destnote").innerHTML = "Verdicts autosave in this browser. When done: <b>Export CSV</b> and <b>Export JSON</b> (or <i>Save both into folder…</i>) and put both files into <code>" + esc(DATA.dest) + "/</code> of the analysis repo.";
$("imgLocator").src = DATA.images.locator; $("imgHeat").src = DATA.images.heatmap;
loadState(); $("reviewer").value = reviewer; rerender();
</script>
</body></html>
"""


def write_html(out_dir: Path, payload: dict) -> Path:
    js = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    p = Path(out_dir) / "index.html"
    p.write_text(HTML.replace("__DATA_JSON__", js).replace("__COHORT__", payload["cohort"]), encoding="utf-8")
    return p


def script_blocks(html_path: Path) -> list[str]:
    return re.findall(r"<script>(.*?)</script>", Path(html_path).read_text(encoding="utf-8"), re.S)


def node_exe() -> str:
    return shutil.which("node") or r"C:\Program Files\nodejs\node.exe"


def check_js(html_path: Path) -> tuple[bool, str]:
    blocks = script_blocks(html_path)
    if len(blocks) != 2:
        return False, f"expected 2 <script> blocks, found {len(blocks)}"
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "page.js"
        f.write_text("\n;\n".join(blocks), encoding="utf-8")
        p = subprocess.run([node_exe(), "--check", str(f)], capture_output=True, text=True)
        return p.returncode == 0, (p.stderr or p.stdout).strip()[-600:]


def embedded_data(html_path: Path) -> dict:
    m = re.search(r"const DATA = (\{.*?\});\n", Path(html_path).read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def media_check(paths: list[Path]) -> pd.DataFrame:
    return pd.DataFrame([{"path": Path(p).as_posix(), "exists": os.path.exists(p), "bytes": os.path.getsize(p) if os.path.exists(p) else 0}
                         for p in paths])


def page_checks(html: Path) -> dict:
    txt = html.read_text(encoding="utf-8")
    ext = sorted(set(re.findall(r"(?:src|href)\s*=\s*['\"](https?://[^'\"]+)", txt)) | set(re.findall(r"https?://[^\s'\"<>)]+", txt)))
    D = embedded_data(html)
    n_rows = sum(len(g["rows"]) for g in D["groups"])
    urls = [D["images"]["locator"], D["images"]["heatmap"]] + [c["url"] for s in D["spots"] for c in s["crops"] if c["url"]] + [e["clip"]["url"] for e in D["episodes"]]
    forbidden = [w for w in ("cv_field_ch01_occlusion", "hidden_share", "h_mean", "geometry class", "category", "occluder_nominal",
                             "wiser_spots", "seconds.csv", "hotspot", "paddock_x", "pano_u") if w in json.dumps(D)]
    okj, msg = check_js(html)
    return {"n_spots": len(D["spots"]), "n_groups": len(D["groups"]), "n_episodes": len(D["episodes"]), "n_episode_rows": n_rows,
            "n_episode_clips": len({e["clip"]["file"] for e in D["episodes"]}), "external_urls": ext,
            "all_media_file_uris": all(u.startswith("file:///") for u in urls), "forbidden_words_in_data": forbidden,
            "node_check": okj, "node_msg": msg, "bytes": html.stat().st_size}


# ----------------------------------------------------------------------------------------------- build
def build(out: Path | None) -> int:
    t0 = time.perf_counter()
    if out is None:
        import output_paths as op
        out = op.run_dir(NAME, COHORT, make_figures=False)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    payload, media = build_payload(STEP2_RUN, P0_RUN, out.name)
    html = write_html(out, payload)
    mc = media_check(media)
    mc.to_csv(out / "media_check.csv", index=False)
    chk = page_checks(html)
    run = {"tool": TOOL, "built": datetime.now().isoformat(timespec="seconds"), "page": html.as_posix(), "dest": DEST,
           "sources": payload["sources"], "media_total": int(len(mc)), "media_missing": mc.loc[~mc["exists"], "path"].tolist(),
           "checks": chk, "runtime_s": round(time.perf_counter() - t0, 2)}
    (out / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    print(f"page -> {html.as_posix()} ({chk['bytes'] / 1e3:.0f} kB); spots {chk['n_spots']}, groups {chk['n_groups']}, episodes "
          f"{chk['n_episodes']} ({chk['n_episode_clips']} own clips), episode rows {chk['n_episode_rows']}; media {len(mc)} referenced, "
          f"{int((~mc['exists']).sum())} missing; external URLs {chk['external_urls']}; node --check {chk['node_check']}; "
          f"forbidden words {chk['forbidden_words_in_data']}")
    return 0 if (chk["node_check"] and mc["exists"].all() and not chk["external_urls"] and chk["n_spots"] == 2
                 and chk["n_episode_rows"] == 59 and chk["n_episodes"] == chk["n_episode_clips"] == 58
                 and not chk["forbidden_words_in_data"]) else 1


# ----------------------------------------------------------------------------------------------- selftest
def selftest() -> int:
    ok = True

    def check(name, cond, info=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}"[:600], flush=True)

    with tempfile.TemporaryDirectory() as td:
        T = Path(td)
        s2, p0 = T / "step2", T / "p0"
        (s2 / "fixed_spots" / "crops").mkdir(parents=True)
        (p0 / "review_clips").mkdir(parents=True)
        for n in ("locator.png", "heatmap.png"):
            (s2 / "fixed_spots" / n).write_bytes(b"png")
        frames = pd.DataFrame({"frame": range(2000), "pts_s": [i * 0.05 for i in range(2000)]})
        frames["t_pc"] = [f"2026-09-06 21:{int(p // 60):02d}:{p % 60:06.3f}" for p in frames["pts_s"]]
        frames.to_csv(s2 / "frames.csv.gz", index=False)
        sp = []
        for sid in (1, 2):
            for role, k in zip(CROP_ROLES, (10, 500, 1900, 501)):
                (s2 / "fixed_spots" / "crops" / f"spot{sid:02d}_{role}_f{k}.png").write_bytes(b"png")
            sp.append({"spot_id": sid, "cx_median": 100.0 * sid, "cy_median": 50.0, "occupancy": 0.3, "n_frames_with_box": 600, "n_cells": 1,
                       "conf_median": 0.5, "w_median": 80.0, "h_median": 90.0, "cx_sd": 2.0, "cy_sd": 1.5,
                       **{f"occ_min{m:02d}": m / 60 for m in range(60)}})
        pd.DataFrame(sp).to_csv(s2 / "fixed_spots" / "fixed_spots.csv", index=False)
        eps = pd.DataFrame({"episode_id": [1, 2, 3, 4], "kind": "suspected_miss", "animal": ["SF07", "SF08", "SF09", "SF10"],
                            "start_sec": [10, 14, 40, 50], "end_sec": [19, 16, 52, 60], "duration_s": [10, 3, 13, 11],
                            "start_t_pc": ["2026-09-06 21:00:10.000", "2026-09-06 21:00:14.000", "2026-09-06 21:00:40.000", "2026-09-06 21:00:50.000"],
                            "end_t_pc": ["2026-09-06 21:00:19.000", "2026-09-06 21:00:16.000", "2026-09-06 21:00:52.000", "2026-09-06 21:01:00.000"],
                            "start_frame": [200, 280, 800, 1000], "end_frame": [380, 320, 1040, 1200], "paddock_x_in": 1.0})
        eps.to_csv(p0 / "fn_episodes.csv", index=False)
        # old shared clips (grouping only; episode 3 sits in both, like episode 204) + one clip per episode
        clips = pd.DataFrame({"file": ["01_ep1_SF07_21-00-10.mp4", "02_ep3_SF09_21-00-40.mp4"], "k": [1, 2], "episode_id": [1, 3],
                              "episodes_covered": ["1;2;3", "3;4"], "animal": ["SF07", "SF09"], "window": ["21:00:05 -> 21:00:24", "21:00:35 -> 21:00:57"],
                              "window_start_sec": [5.0, 35.0], "window_end_sec": [24.0, 57.0], "hotspot": ["yes", "no"]})
        clips.to_csv(p0 / "review_clips" / "clips.csv", index=False)
        (p0 / "review_clips_per_episode").mkdir()
        pe = pd.DataFrame({"file": ["ep1_SF07_21-00-10.mp4", "ep2_SF08_21-00-14.mp4", "ep3_SF09_21-00-40.mp4", "ep4_SF10_21-00-50.mp4"],
                           "episode_id": [1, 2, 3, 4], "window": ["21:00:07 -> 21:00:22", "21:00:11 -> 21:00:19", "21:00:37 -> 21:00:55", "21:00:47 -> 21:01:03"],
                           "window_start_sec": [7.0, 11.0, 37.0, 47.0], "window_end_sec": [22.0, 19.0, 55.0, 63.0], "capped": [False] * 4})
        pe.to_csv(p0 / "review_clips_per_episode" / "clips_per_episode.csv", index=False)
        for f in pe["file"]:
            (p0 / "review_clips_per_episode" / f).write_bytes(b"mp4")
        payload, media = build_payload(s2, p0, "selftest")
        payload["help"].append("a </script> inside the data")
        html = write_html(T, payload)
        D = embedded_data(html)
        check("payload: 2 spots, 2 groups, 4 unique episodes shown as 5 rows (episode 3 in both groups); crops and raster embedded; "
              "'</script>' escaped", len(D["spots"]) == 2 and len(D["groups"]) == 2 and len(D["episodes"]) == 4
              and sum(len(g["rows"]) for g in D["groups"]) == 5 and D["groups"][0]["rows"][2] == D["groups"][1]["rows"][0] == "ep3"
              and len(D["spots"][0]["minutes"]) == 60 and all(c["url"] for c in D["spots"][0]["crops"])
              and html.read_text(encoding="utf-8").count("</script>") == 2)
        e1 = D["episodes"][0]
        check("per-episode clip mapping: each episode has its own clip; seek = episode start in that clip (frame 200 in a clip from frame "
              "140 -> 3.0 s), end 12.05 s", [e["clip"]["file"] for e in D["episodes"]] == list(pe["file"]) and e1["item_id"] == "ep1"
              and abs(e1["clip"]["seek_s"] - 3.0) < 1e-9 and abs(e1["clip"]["end_s"] - 12.05) < 1e-9 and abs(e1["clip"]["duration_s"] - 15.0) < 1e-9,
              str(e1))
        check("media: every referenced path exists (2 images + 8 crops + 4 episode clips; the old shared clips are not used); file:/// "
              "URLs only; no network URL", media_check(media)["exists"].all() and len(media) == 2 + 8 + 4 and page_checks(html)["all_media_file_uris"]
              and not page_checks(html)["external_urls"])
        check("no geometry / occluder / sealed fields in the embedded data (the hotspot and paddock columns of the inputs are dropped)",
              not page_checks(html)["forbidden_words_in_data"], str(page_checks(html)["forbidden_words_in_data"]))
        okj, msg = check_js(html)
        check("both script blocks pass node --check", okj, msg)
        harness = script_blocks(html)[0] + r"""
;(function(){
  const r = {};
  // migration of old per-clip ids: episode 3 answered in both groups (c01 at 10:00 = occluded/pole, c02 earlier at 09:00 =
  // visible_missed), episode 1 once; an unknown old id is ignored
  J = {c01_ep3: {verdict: "occluded", occluder_kind: "pole", notes: "late", s_verdict: "occluded", s_occluder_kind: "pole", s_notes: "late",
                 saved_at: "2026-10-06T10:00:00Z", first_saved_at: "2026-10-06T10:00:00Z", verdict_first: "occluded", n_saves: 1},
       c02_ep3: {verdict: "visible_missed", occluder_kind: "", notes: "early", s_verdict: "visible_missed", s_occluder_kind: "", s_notes: "early",
                 saved_at: "2026-10-06T09:00:00Z", first_saved_at: "2026-10-06T09:00:00Z", verdict_first: "visible_missed", n_saves: 1},
       c01_ep1: {verdict: "box_present", s_verdict: "box_present", s_occluder_kind: "", s_notes: "", notes: "", occluder_kind: "",
                 saved_at: "2026-10-06T08:00:00Z", first_saved_at: "2026-10-06T08:00:00Z", verdict_first: "box_present", n_saves: 1},
       c09_ep999: {verdict: "unsure", saved_at: "2026-10-06T08:00:00Z"}, spot_1: {verdict: "rat"}};
  r.mig1 = migrateState(J, false);
  r.mig2 = migrateState(J, false);
  r.ep3 = Object.assign({}, J.ep3); r.ep1 = Object.assign({}, J.ep1);
  r.oldKept = ["c01_ep3", "c02_ep3", "c01_ep1"].every(k => !!J[k]) && !J.ep999;
  r.spotUntouched = J.spot_1.verdict === "rat" && !J.spot_1.migrated_from;
  r.migRow = exportRows().find(x => x.item_id === "ep3");
  J = {};
  const sp1 = SPOTS[0].item_id, sp2 = SPOTS[1].item_id, e1 = EPS[0].item_id, e2 = EPS[1].item_id;
  r.locked0 = step2Unlocked();
  setVerdict(e1, "visible_missed"); r.saveLocked = saveItem(e1);
  r.badSpot = setVerdict(sp1, "visible_missed");
  r.noVerdict = saveItem(sp1);
  setVerdict(sp1, "object"); r.s1 = saveItem(sp1);
  r.locked1 = step2Unlocked();
  setVerdict(sp2, "rat"); setNotes(sp2, 'a "quoted", note' + "\n" + "line2"); r.s2 = saveItem(sp2);
  r.unlocked = step2Unlocked();
  r.saveE1 = saveItem(e1);
  r.occNoKind = (setVerdict(e2, "occluded"), saveItem(e2));
  r.occKindBad = setOccluder(e2, "tree");
  setOccluder(e2, "pole"); r.saveE2 = saveItem(e2);
  setVerdict(e1, "box_present"); r.draft = status(e1); r.saveE1b = saveItem(e1);
  setVerdict(e2, "unsure"); r.kindCleared = J[e2].occluder_kind === "";
  setNotes("fn_notes", "x 6500 y 1200"); r.fn = saveItem("fn_notes");
  r.counts = counts();
  const o = exportObject();
  const n = importObject({state: {[EPS[2].item_id]: {verdict: "occluded", occluder_kind: "house", s_verdict: "occluded", s_occluder_kind: "house",
                                                       saved_at: "2026-10-06T00:00:00Z", verdict_first: "occluded", first_saved_at: "2026-10-06T00:00:00Z"}}, reviewer: "zz"});
  r.imported = n; r.reviewer = reviewer;
  // the old export format (rows / state keyed c<k>_ep<id>) imports through the same mapping; the old keys are kept
  const nOld = importObject({schema: "c1yolo_review/1", rows: [{item_id: "c02_ep4", verdict: "unsure"}],
                             state: {c02_ep4: {verdict: "unsure", s_verdict: "unsure", s_occluder_kind: "", s_notes: "old", notes: "old",
                                               occluder_kind: "", saved_at: "2026-10-06T07:00:00Z", first_saved_at: "2026-10-06T07:00:00Z", verdict_first: "unsure"}}});
  r.oldImport = {n: nOld, ep4: Object.assign({}, J.ep4), kept: !!J.c02_ep4};
  r.fname = fname("csv", "20261006_1200");
  process.stdout.write(JSON.stringify({r: r, obj: o, csv: csvText()}));
})();
"""
        jsf = T / "harness.js"
        jsf.write_text(harness, encoding="utf-8")
        pr = subprocess.run([node_exe(), str(jsf)], capture_output=True, text=True, encoding="utf-8")
        try:
            got = json.loads(pr.stdout)
        except Exception:  # noqa: BLE001
            got = None
        check("page logic runs in node", got is not None, (pr.stderr or "")[-400:])
        if got is not None:
            R, O = got["r"], got["obj"]
            check("Step 2 locked until both spots are saved; an episode cannot be saved while locked",
                  R["locked0"] is False and R["saveLocked"]["ok"] is False and R["locked1"] is False and R["unlocked"] is True and R["saveE1"]["ok"])
            check("verdicts validated per step; a verdict is required; occluded needs a valid occluder kind; the kind clears off 'occluded'",
                  R["badSpot"] is False and R["noVerdict"]["ok"] is False and R["occNoKind"]["ok"] is False and R["occKindBad"] is False
                  and R["saveE2"]["ok"] and R["kindCleared"])
            rows = {x["item_id"]: x for x in O["rows"]}
            re1, re2 = rows[EPS_ID(O, 0)], rows[EPS_ID(O, 1)]
            check("verdict_first kept, verdict_final + changed after a re-save; an unsaved change is not exported (draft status)",
                  R["draft"] == "draft" and re1["verdict_first"] == "visible_missed" and re1["verdict"] == "box_present"
                  and re1["verdict_final"] == "box_present" and re1["changed"] is True and re2["verdict"] == "occluded"
                  and re2["occluder_kind"] == "pole" and re2["status"] == "draft" and re2["changed"] is False, f"{re1} | {re2}")
            check("export: rows = 2 spots + fn_notes + every episode row, columns in the required order, step 1 / 2",
                  len(O["rows"]) == 2 + 1 + 4 and list(O["rows"][0].keys()) == EXPORT_COLS and O["schema"] == SCHEMA
                  and rows["spot_1"]["step"] == 1 and rows[EPS_ID(O, 0)]["step"] == 2 and rows["fn_notes"]["notes"] == "x 6500 y 1200"
                  and O["counts"] == {"spots_saved": 2, "n_spots": 2, "episodes_saved": 2, "n_episodes": 4}, str(list(O["rows"][0].keys())))
            cr = list(csv.DictReader(io.StringIO(got["csv"])))
            check("CSV: same rows and columns; a quoted multi-line note survives", len(cr) == 7 and list(cr[0].keys()) == EXPORT_COLS
                  and cr[1]["notes"] == 'a "quoted", note\nline2', str(cr[1]))
            check("import restores saved state; file name starts with the destination folder",
                  R["imported"] == 1 and R["reviewer"] == "zz" and R["fname"].startswith("cv-configs-c1yolo_review_2026c__review_"), R["fname"])
            e3, m1 = R["ep3"], R["migRow"]
            check("migration: old c<k>_ep<id> -> ep<id>; the duplicate episode keeps the EARLIER first save as verdict_first and the "
                  "LATER save as the verdict (changed); runs once; old keys kept; unknown ids and Step-1 items untouched",
                  R["mig1"] == 2 and R["mig2"] == 0 and e3["verdict_first"] == "visible_missed" and e3["first_saved_at"] == "2026-10-06T09:00:00Z"
                  and e3["s_verdict"] == "occluded" and e3["s_occluder_kind"] == "pole" and e3["saved_at"] == "2026-10-06T10:00:00Z"
                  and e3["migrated_from"] == ["c01_ep3", "c02_ep3"] and e3["n_saves"] == 2 and R["ep1"]["s_verdict"] == "box_present"
                  and R["oldKept"] and R["spotUntouched"] and m1["verdict"] == "occluded" and m1["verdict_first"] == "visible_missed"
                  and m1["changed"] is True and m1["clip"] == "ep3_SF09_21-00-40.mp4", f"{e3} | {m1}")
            oi = R["oldImport"]
            check("old-format import (state keyed c02_ep4) maps to ep4, keeps the old key; export rows carry the per-episode clip file",
                  oi["n"] == 1 and oi["ep4"]["s_verdict"] == "unsure" and oi["ep4"]["migrated_from"] == ["c02_ep4"] and oi["kept"]
                  and rows["ep1"]["clip"] == "ep1_SF07_21-00-10.mp4", str(oi))
    print(("PASS" if ok else "FAIL") + " — c1yolo_review_gui self-test")
    return 0 if ok else 1


def EPS_ID(obj: dict, i: int) -> str:
    return [r["item_id"] for r in obj["rows"] if r["step"] == 2][i]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.build:
        return build(Path(a.out) if a.out else None)
    ap.error("nothing to do (--selftest or --build)")


if __name__ == "__main__":
    sys.exit(main())
