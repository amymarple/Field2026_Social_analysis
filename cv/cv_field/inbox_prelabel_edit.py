r"""inbox_prelabel_edit.py — in-box CH07: SAM 3 "rat" masks as head-anchored pre-labels, part B (dev edit pilot).

Specification: implementation_plan/2026-10-12-inbox-sam3-rat-prelabel.md, sections "A", "Definitions" and "B" (approved by
the user 2026-10-12, "行干吧 ABC都来 我给你标注"). Part C (frozen test on new frames) is NOT built here; nothing goes on C frames.

build      From the SAM 3 test run (default cv_field_inbox_sam3_dino_20261010_2320), all 58 frames of frames.csv:
           - candidates = the cached "rat" (P1) masks of sam3_t1/whole (every mask, score >= 0.01, whole frame, no filter);
           - per blind head click (heads.csv, 284) the masks within 15 px of the point by the T1 coverage rule
             (inbox_sam3_dino_test.head_dist), ordered by score (highest first; ties: smaller area, then cache index);
           - masks shipped as outer contours, cv2.approxPolyDP eps 2 px at full resolution, + exact mask bbox;
           - arms (seed 20261012): stratified by domain x the frame's largest pile size (1 / 2-3 / 4+), PRELABEL =
             round(2 n / 3) per stratum, SCRATCH the rest; order = IR first, then colour, shuffled within each domain;
           -> <run>/prelabel_edit/index.html (self-contained, file://, data in pl_data.js, no network) + frames/ (the
              identity page's original JPEGs, copied unchanged) + arms.csv + head_candidates.csv + build_meta.json +
              page_check.json (headless Chrome).
summarize  --export <the user's JSON export>: the plan's B descriptive summary (usable@1, usable@any, merged / partial /
           manual-box rates, seconds per rat PRELABEL vs SCRATCH, all by pile size and domain; show-all garbage /
           fragment marks) -> <run>/prelabel_edit/summary_B.md, included by the SAM 3 report as section
           "B — pre-label edit pilot (dev)" (the report is regenerated).

The agent never judges an image: every verdict is the user's. Base Python (numpy, pandas, opencv, websocket-client for the
headless check; node for the selftest's syntax check).
Usage:
  python cv/cv_field/inbox_prelabel_edit.py --selftest
  python cv/cv_field/inbox_prelabel_edit.py build [--run <SAM 3 run>] [--no-page-check]            # v1 page (prelabel_edit/)
  python cv/cv_field/inbox_prelabel_edit.py build --v2 [--run <SAM 3 run>]                         # v2 page (prelabel_edit_v2/):
         implant box (head-point candidates) + rat box (head + body, no tail; candidates from a body click), amendments B1 / B1a
  python cv/cv_field/inbox_prelabel_edit.py summarize --export cv/configs/inbox_sam3_prelabel_edit_2026c/<file>.json [--run <run>]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import inbox_sam3_dino_test as S  # noqa: E402

PLAN = "implementation_plan/2026-10-12-inbox-sam3-rat-prelabel.md"
RUN_DEFAULT = S.OUT_ROOT / "2026c" / "cv_field_inbox_sam3_dino_20261010_2320"
EXPORT_DIR = REPO / "cv" / "configs" / "inbox_sam3_prelabel_edit_2026c"
SEED = 20261012
P1 = 0                               # index of the prompt "rat" in the T1 cache (P1)
EPS_PX = 2.0
IDLE_MS = 45000
PAGE_VERSION = "inbox_sam3_prelabel_edit_2026c_v1"
PILE_BINS = ("1", "2-3", "4+")
DEFINITIONS = [
    ("Final label per rat", "the head point plus the body box; the chosen mask is kept when one was used."),
    ("Body box", "the visible body without the tail; occluded parts are not inferred."),
    ("Usable mask", "covers the visible body of exactly ONE rat (head when visible, plus trunk) and no part of another rat; "
                    "its box may still need small edge moves."),
    ("Merged", "covers parts of ≥ 2 rats."),
    ("Partial", "clearly misses a large part of that rat's visible body (e.g. only the head, only the hindquarters)."),
    ("Garbage", "on no rat (only in the optional 'show all' view)."),
    ("Fragment", "on part of a rat but not offered for it (only in the optional 'show all' view)."),
]


def pile_bin(p) -> str:
    p = int(p)
    return "1" if p <= 1 else "2-3" if p <= 3 else "4+"


# ============================================================================================ arms + candidates
def assign_arms(frames: pd.DataFrame, heads: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    """PRELABEL = round(2 n / 3) of each stratum (domain x the frame's largest pile size), SCRATCH the rest; then the work
    order: IR first, then colour, shuffled within each domain. One seeded generator, strata in a fixed order."""
    rng = np.random.default_rng(seed)
    mp = heads.groupby("frame_id").pile_size.max()
    f = frames[["frame_id", "domain", "segment_id", "frame_kind", "path", "frame_time", "n_heads", "split"]].copy()
    f["pile_max"] = f.frame_id.map(mp).fillna(0).astype(int)
    f["pile_bin"] = f.pile_max.map(pile_bin)
    f["arm"] = ""
    for dom in ("ir", "colour"):
        for b in PILE_BINS:
            ids = sorted(f.loc[(f.domain == dom) & (f.pile_bin == b), "frame_id"])
            if not ids:
                continue
            perm = [ids[i] for i in rng.permutation(len(ids))]
            n_pre = int(np.floor(2 * len(ids) / 3 + 0.5))
            for j, fid in enumerate(perm):
                f.loc[f.frame_id == fid, "arm"] = "PRELABEL" if j < n_pre else "SCRATCH"
    order = []
    for dom in ("ir", "colour"):
        ids = sorted(f.loc[f.domain == dom, "frame_id"])
        order += [ids[i] for i in rng.permutation(len(ids))]
    f["order"] = f.frame_id.map({fid: k + 1 for k, fid in enumerate(order)})
    return f.sort_values("order").reset_index(drop=True)


def mask_polygons(crop: np.ndarray, bbox, eps: float = EPS_PX) -> list[list[int]]:
    import cv2
    if crop.size == 0:
        return []
    cs, _ = cv2.findContours(crop.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in cs:
        a = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
        if len(a) < 3:
            continue
        out.append([int(v) for xy in a for v in (xy[0] + int(bbox[0]), xy[1] + int(bbox[1]))])
    return out


def order_candidates(ks, score, area) -> list[int]:
    """Score descending, then smaller area, then index."""
    return sorted(ks, key=lambda k: (-float(score[k]), int(area[k]), int(k)))


def frame_payload(run: Path, fid: str, H: pd.DataFrame) -> dict:
    """All P1 masks of one frame (page ids = score order) + per head the candidate page ids (T1 coverage rule)."""
    M = S.load_masks(run / "sam3_t1" / "whole" / f"{fid}.npz")
    idx = np.flatnonzero(M["prompt"] == P1)
    ordered = order_candidates(list(idx), M["score"], M["area"])
    pid = {int(k): j for j, k in enumerate(ordered)}
    masks = [{"s": round(float(M["score"][k]), 4), "a": int(M["area"][k]), "b": [int(x) for x in M["bbox"][k]],
              "i": int(k), "p": mask_polygons(M["crops"][k], M["bbox"][k])} for k in ordered]
    uv = H[["u", "v"]].to_numpy(float)
    D = S.dist_matrix(uv, [M["crops"][k] for k in ordered], [tuple(int(b) for b in M["bbox"][k]) for k in ordered]) \
        if len(ordered) else np.zeros((len(uv), 0))
    cand = [[j for j in range(len(ordered)) if D[i, j] <= S.COVER_PX] for i in range(len(uv))]   # already score-ordered
    return {"masks": masks, "cand": cand, "pid": pid}


# ============================================================================================ page
PAGE_CSS = S.PAGE_CSS + """
.wrap{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:12px;padding:8px 16px}
@media (max-width:1000px){.wrap{grid-template-columns:minmax(0,1fr)}}
#cv{width:100%;height:calc(100vh - 230px);min-height:420px;background:#111;border-radius:6px;display:block}
.side{display:flex;flex-direction:column;gap:8px;font-size:14px}.side textarea{min-height:60px}
.defs{max-width:1500px;font-size:13px;margin:4px 0}.defs dt{font-weight:600;display:inline}.defs dd{display:inline;margin:0 0 0 4px}
.defs div{margin:1px 0}#status{font-weight:600}#armtag{font-weight:700;padding:1px 6px;border-radius:4px}
.PRELABEL{background:#d8ecff;color:#123}.SCRATCH{background:#ffe8c8;color:#321}.keys{font-size:12.5px;color:var(--muted);line-height:1.5}
.prog{height:10px;background:var(--line);border-radius:5px;overflow:hidden}.prog>div{height:100%;background:var(--acc)}
#banner{font-weight:600;color:var(--warn)}
"""

PAGE_JS = r"""
(function(){
const D = window.PL_DATA, KEY = D.page_version + '::' + D.run;
const $ = id => document.getElementById(id);
const iso = () => new Date().toISOString();
let S = null;
function initFrame(f){ return {arm: f.arm, active_ms: 0, showall_ms: 0, completed: false, visited: false, next_add: 1, marks: {},
  passes: [], rats: f.heads.map((h, i) => ({id: 'h' + (i + 1), num: i + 1, origin: 'click', click_id: h.c, u: h.u, v: h.v, cand: f.cand[i], k: 0,
    prop: f.cand[i].length ? f.masks[f.cand[i][0]].b.slice() : null,
    deleted: false, box: null, source: null, rank: null, mask: null, cand_flags: {}, edge_moves: 0, next_presses: 0}))}; }
function fresh(){ const fr = {}; D.frames.forEach(f => fr[f.id] = initFrame(f));
  return {v: 1, started_at: iso(), defnote: '', cur: {fi: 0, ri: 0}, frames: fr, events: []}; }
function load(){ try { const t = localStorage.getItem(KEY); if (t) { const o = JSON.parse(t); if (o && o.frames) return o; } } catch (e) {} return null; }
let saveT = null;
function save(now){ const f = () => { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { $('banner').textContent = 'could not save to this browser: export now'; } };
  if (now) { f(); return; } clearTimeout(saveT); saveT = setTimeout(f, 250); }
S = load() || fresh();
const FD = Object.fromEntries(D.frames.map(f => [f.id, f]));
const fr = () => D.frames[S.cur.fi], st = () => S.frames[fr().id];
const rats = () => st().rats;
function liveIdx(){ return rats().map((r, i) => i).filter(i => !rats()[i].deleted); }
function rat(){ const r = rats()[S.cur.ri]; return r; }
function log(ev, extra){ const r = rat(); S.events.push(Object.assign({t: iso(), frame: fr().id, arm: st().arm, rat: r ? r.id : null, ev: ev}, extra || {})); save(); }
// ---------------------------------------------------------------- undo (per frame, in memory)
const undo = {};
function snap(){ const id = fr().id; (undo[id] = undo[id] || []).push(JSON.stringify({rats: st().rats, marks: st().marks, next_add: st().next_add, ri: S.cur.ri})); if (undo[id].length > 200) undo[id].shift(); }
function doUndo(){ const a = undo[fr().id]; if (!a || !a.length) return; const o = JSON.parse(a.pop());
  st().rats = o.rats; st().marks = o.marks; st().next_add = o.next_add; S.cur.ri = Math.min(o.ri, st().rats.length - 1); log('undo'); draw(); }
// ---------------------------------------------------------------- geometry
function pointInPoly(x, y, p){ let ins = false; for (let i = 0, j = p.length - 2; i < p.length; j = i, i += 2) {
  const xi = p[i], yi = p[i + 1], xj = p[j], yj = p[j + 1];
  if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) ins = !ins; } return ins; }
function segDist(x, y, x1, y1, x2, y2){ const dx = x2 - x1, dy = y2 - y1, L = dx * dx + dy * dy; let t = L ? ((x - x1) * dx + (y - y1) * dy) / L : 0;
  t = Math.max(0, Math.min(1, t)); return Math.hypot(x - x1 - t * dx, y - y1 - t * dy); }
function polyDist(x, y, p){ let d = Infinity; for (let i = 0, j = p.length - 2; i < p.length; j = i, i += 2) d = Math.min(d, segDist(x, y, p[j], p[j + 1], p[i], p[i + 1])); return d; }
function maskHit(m, x, y, tol){ for (const p of m.p) { if (pointInPoly(x, y, p)) return true; } if (tol > 0) { for (const p of m.p) if (polyDist(x, y, p) <= tol) return true; } return false; }
function candidatesAt(x, y){ const f = fr(); const out = []; f.masks.forEach((m, j) => { if (maskHit(m, x, y, D.cover_px)) out.push(j); }); return out; }
// ---------------------------------------------------------------- view
const cv = $('cv'), ctx = cv.getContext('2d');
let view = null, mode = null, drag = null, hover = null, spaceDown = false, showAll = false;
const imgs = {};
function img(){ const f = fr(); if (!imgs[f.img]) { const im = new Image(); im.onload = () => draw(); im.src = f.img; imgs[f.img] = im; } return imgs[f.img]; }
function fit(){ const w = cv.clientWidth, h = cv.clientHeight, f = fr(); const s = Math.min(w / f.w, h / f.h); view = {s, ox: (w - f.w * s) / 2, oy: (h - f.h * s) / 2}; }
const toImg = (x, y) => [(x - view.ox) / view.s, (y - view.oy) / view.s];
const toCv = (u, v) => [u * view.s + view.ox, v * view.s + view.oy];
function polyPath(p){ const P = new Path2D(); for (let i = 0; i < p.length; i += 2) { if (i === 0) P.moveTo(p[i], p[i + 1]); else P.lineTo(p[i], p[i + 1]); } P.closePath(); return P; }
function colour(r){ return 'hsl(' + ((r * 137.508) % 360).toFixed(1) + ',90%,58%)'; }
let drawnMasks = 0;
function curCand(){ const r = rat(); if (!r || r.deleted || st().arm !== 'PRELABEL' || showAll) return null; return r.k < r.cand.length ? r.cand[r.k] : null; }
function draw(){
  const f = fr(), s = st(); if (!f) return;
  if (cv.width !== cv.clientWidth) cv.width = cv.clientWidth; if (cv.height !== cv.clientHeight) cv.height = cv.clientHeight;
  if (!view) fit();
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = '#111'; ctx.fillRect(0, 0, cv.width, cv.height);
  ctx.setTransform(view.s, 0, 0, view.s, view.ox, view.oy);
  const im = img(); if (im.complete && im.naturalWidth) ctx.drawImage(im, 0, 0, f.w, f.h);
  const lw = 1 / view.s; drawnMasks = 0;
  if (showAll) {
    f.masks.forEach((m, j) => { const mk = s.marks[j]; const col = mk === 'garbage' ? '#ff3b3b' : mk === 'fragment' ? '#ffa500' : colour(j);
      m.p.forEach(p => { const P = polyPath(p); if (mk) { ctx.globalAlpha = 0.35; ctx.fillStyle = col; ctx.fill(P); ctx.globalAlpha = 1; }
        ctx.lineWidth = 1.5 * lw; ctx.strokeStyle = col; ctx.stroke(P); }); drawnMasks++; });
  } else {
    const c = curCand();
    if (c !== null) { const m = f.masks[c]; m.p.forEach(p => { const P = polyPath(p); ctx.globalAlpha = 0.18; ctx.fillStyle = '#00e5ff'; ctx.fill(P);
      ctx.globalAlpha = 1; ctx.lineWidth = 2.5 * lw; ctx.strokeStyle = '#00e5ff'; ctx.stroke(P); }); drawnMasks = 1;
      ctx.setLineDash([8 * lw, 6 * lw]); ctx.lineWidth = 2 * lw; ctx.strokeStyle = '#ffd400'; ctx.strokeRect(m.b[0], m.b[1], m.b[2] - m.b[0], m.b[3] - m.b[1]); ctx.setLineDash([]); }
  }
  s.rats.forEach((r, i) => { if (r.deleted || !r.box) return; const cur = i === S.cur.ri; const b = r.box;
    ctx.globalAlpha = cur ? 1 : 0.45; ctx.lineWidth = (cur ? 2.5 : 1.5) * lw; ctx.strokeStyle = cur ? '#39ff14' : '#ffffff'; ctx.strokeRect(b[0], b[1], b[2] - b[0], b[3] - b[1]); ctx.globalAlpha = 1; });
  if (drag && drag.kind === 'draw' && drag.cur) { const b = normBox(drag.start, drag.cur); ctx.setLineDash([6 * lw, 4 * lw]); ctx.lineWidth = 2 * lw; ctx.strokeStyle = '#39ff14';
    ctx.strokeRect(b[0], b[1], b[2] - b[0], b[3] - b[1]); ctx.setLineDash([]); }
  ctx.font = (16 * lw) + 'px system-ui, sans-serif';
  s.rats.forEach((r, i) => { const cur = i === S.cur.ri, R = (cur ? 9 : 7) * lw;
    ctx.beginPath(); if (r.origin === 'added') { ctx.moveTo(r.u, r.v - R); ctx.lineTo(r.u + R, r.v); ctx.lineTo(r.u, r.v + R); ctx.lineTo(r.u - R, r.v); ctx.closePath(); }
    else ctx.arc(r.u, r.v, R, 0, 2 * Math.PI);
    ctx.fillStyle = r.deleted ? '#777' : '#fff'; ctx.fill(); ctx.lineWidth = (cur ? 3 : 2) * lw; ctx.strokeStyle = cur ? '#ff2fd0' : '#000'; ctx.stroke();
    if (r.deleted) { ctx.strokeStyle = '#ff3b3b'; ctx.beginPath(); ctx.moveTo(r.u - R, r.v - R); ctx.lineTo(r.u + R, r.v + R); ctx.moveTo(r.u + R, r.v - R); ctx.lineTo(r.u - R, r.v + R); ctx.stroke(); }
    ctx.lineWidth = 3 * lw; ctx.strokeStyle = '#000'; ctx.strokeText(String(r.num), r.u + R + 3 * lw, r.v - R); ctx.fillStyle = cur ? '#ff2fd0' : '#fff'; ctx.fillText(String(r.num), r.u + R + 3 * lw, r.v - R); });
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  panel();
}
function panel(){
  const f = fr(), s = st(), r = rat();
  $('armtag').textContent = s.arm; $('armtag').className = s.arm; if ($('goto').value !== String(S.cur.fi)) $('goto').value = String(S.cur.fi);
  $('ftitle').textContent = 'frame ' + (S.cur.fi + 1) + ' / ' + D.frames.length + ' · ' + (f.domain === 'ir' ? 'IR' : 'colour') + ' · ' + f.id;
  const live = liveIdx();
  let txt = r ? ('rat ' + r.num + (r.origin === 'added' ? ' (added)' : '') + ' · ' + (live.indexOf(S.cur.ri) + 1) + ' of ' + live.length + ' on this frame') : 'no rat on this frame';
  if (r && r.deleted) txt += ' · deleted';
  if (r && s.arm === 'PRELABEL' && !r.deleted) txt += ' · ' + (r.cand.length === 0 ? 'no candidate — draw a box (B)' : r.k < r.cand.length ? ('candidate ' + (r.k + 1) + ' / ' + r.cand.length) : 'none usable — draw a box (B)');
  if (r && r.box) txt += ' · box: ' + (r.source === 'manual' ? 'manual' : 'candidate ' + r.rank) + (r.edge_moves ? ', ' + r.edge_moves + ' edge move(s)' : '');
  if ((s.passes || []).length) txt += ' · pass ' + (s.passes.length + 1);
  const c = curCand(); if (c !== null) { const fl = r.cand_flags[r.k + 1] || {}; if (fl.merged || fl.partial) txt += ' · flagged ' + [fl.merged ? 'merged' : '', fl.partial ? 'partial' : ''].filter(Boolean).join(' + '); }
  $('status').textContent = txt;
  $('banner').textContent = showAll ? 'SHOW ALL: every "rat" mask; click a mask: garbage → fragment → clear. Press S to go back. (显示全部)' : mode === 'draw' ? 'draw a box: drag on the image (画框)' : mode === 'add' ? 'add a rat: click its visible body (加鼠)' : '';
  const done = D.frames.filter(x => S.frames[x.id].completed).length; let nr = 0, nb = 0;
  D.frames.forEach(x => S.frames[x.id].rats.forEach(q => { if (!q.deleted) { nr++; if (q.box) nb++; } }));
  $('progbar').style.width = (100 * done / D.frames.length).toFixed(1) + '%';
  $('progtxt').textContent = done + ' / ' + D.frames.length + ' frames done · ' + nb + ' / ' + nr + ' rats boxed';
  $('timetxt').textContent = 'active ' + (s.active_ms / 1000).toFixed(0) + ' s' + (s.showall_ms ? ' · show-all ' + (s.showall_ms / 1000).toFixed(0) + ' s' : '') + (idle() ? ' · paused' : '');
}
function normBox(a, b){ return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])]; }
// ---------------------------------------------------------------- actions
function goFrame(i){ S.cur.fi = Math.max(0, Math.min(D.frames.length - 1, i)); const live = liveIdx(); S.cur.ri = live.length ? live[0] : 0;
  st().visited = true; view = null; mode = null; showAll = false; $('showall').checked = false; log('frame_open'); draw(); }
function nextRat(){ const live = liveIdx(), p = live.indexOf(S.cur.ri);
  if (p >= 0 && p < live.length - 1) { S.cur.ri = live[p + 1]; mode = null; log('rat_next'); draw(); return; }
  if (p < 0 && live.length) { const nx = live.find(i => i > S.cur.ri); if (nx !== undefined) { S.cur.ri = nx; draw(); return; } }
  st().completed = true; log('frame_done'); if (S.cur.fi < D.frames.length - 1) goFrame(S.cur.fi + 1); else { draw(); $('banner').textContent = 'last frame done — please export'; } }
function prevRat(){ const live = liveIdx(), p = live.indexOf(S.cur.ri); if (p > 0) { S.cur.ri = live[p - 1]; mode = null; draw(); } else if (S.cur.fi > 0) { goFrame(S.cur.fi - 1); } }
function accept(){ const r = rat(), c = curCand(); if (!r || c === null) return; snap(); const m = fr().masks[c];
  r.box = m.b.slice(); r.source = 'cand'; r.rank = r.k + 1; r.mask = c; log('accept', {rank: r.rank, mask: c, mask_score: m.s, box: r.box, flags: r.cand_flags[r.rank] || {}}); draw(); }
function fitToMask(){ const r = rat(); if (!r || r.deleted || r.mask === null || r.source !== 'cand') return; const b = fr().masks[r.mask].b;
  if (r.box && r.box.every((x, i) => x === b[i])) return; snap(); const from = r.box; r.box = b.slice(); log('fit_to_mask', {from: from, to: r.box, rank: r.rank}); draw(); }
function next(){ const r = rat(); if (!r || r.deleted || st().arm !== 'PRELABEL' || showAll) return; snap(); r.k = r.k < r.cand.length ? r.k + 1 : 0; r.next_presses++;
  log('next', {to: r.k < r.cand.length ? r.k + 1 : 'none'}); draw(); }
function flag(kind){ const r = rat(); if (curCand() === null) return; snap(); const fl = r.cand_flags[r.k + 1] = r.cand_flags[r.k + 1] || {}; fl[kind] = !fl[kind];
  log('flag', {rank: r.k + 1, flag: kind, value: fl[kind]}); draw(); }
function setManual(b){ const r = rat(); if (!r || r.deleted) return; snap(); r.box = b.map(x => Math.round(x * 10) / 10); r.source = 'manual'; r.rank = null; r.mask = null;
  log('manual_box', {box: r.box}); mode = null; draw(); }
function addRat(u, v){ snap(); const s = st(), f = fr(); const cand = s.arm === 'PRELABEL' ? candidatesAt(u, v) : [];
  const r = {id: 'a' + s.next_add, num: s.rats.length + 1, origin: 'added', click_id: null, u: Math.round(u * 10) / 10, v: Math.round(v * 10) / 10, cand: cand, k: 0,
    prop: cand.length ? f.masks[cand[0]].b.slice() : null, deleted: false, box: null, source: null, rank: null, mask: null, cand_flags: {}, edge_moves: 0, next_presses: 0};
  s.next_add++; s.rats.push(r); S.cur.ri = s.rats.length - 1; mode = null; log('add_rat', {u: r.u, v: r.v, n_cand: cand.length}); draw(); }
function delDot(){ const r = rat(); if (!r) return; snap(); r.deleted = !r.deleted; log(r.deleted ? 'delete_dot' : 'undelete_dot'); draw(); }
function redoFrame(skipConfirm){ const f = fr(), s = st();
  if (!skipConfirm && !confirm('Label this frame again from the start? The current labels are kept as pass ' + ((s.passes || []).length + 1) + '.')) return;
  s.passes = (s.passes || []).concat([{rats: s.rats, active_ms: s.active_ms, showall_ms: s.showall_ms, completed: s.completed, marks: s.marks, archived_at: iso()}]);
  const nf = initFrame(f); s.rats = nf.rats; s.active_ms = 0; s.showall_ms = 0; s.completed = false; s.marks = {}; s.next_add = 1; undo[f.id] = [];
  S.cur.ri = 0; log('redo_frame', {pass: s.passes.length + 1}); draw(); }
function toggleShowAll(on){ showAll = on === undefined ? !showAll : on; $('showall').checked = showAll; mode = null; log('show_all', {on: showAll}); draw(); }
function markMask(u, v){ const f = fr(), s = st(); let best = -1, ba = Infinity;
  f.masks.forEach((m, j) => { if (maskHit(m, u, v, 0) && m.a < ba) { best = j; ba = m.a; } }); if (best < 0) return; snap();
  const cur = s.marks[best], nx = !cur ? 'garbage' : cur === 'garbage' ? 'fragment' : null; if (nx) s.marks[best] = nx; else delete s.marks[best];
  log('showall_mark', {mask: best, mark: nx || 'clear'}); draw(); }
// ---------------------------------------------------------------- timing
let lastInput = performance.now(), lastTick = performance.now();
const idle = () => document.visibilityState !== 'visible' || performance.now() - lastInput > D.idle_ms;
function touch(){ lastInput = performance.now(); }
setInterval(() => { const now = performance.now(), dt = now - lastTick; lastTick = now; if (!idle() && dt < 5000) { const s = st(); if (showAll) s.showall_ms += dt; else s.active_ms += dt; }
  panel(); if (Math.random() < 0.1) save(); }, 500);
document.addEventListener('visibilitychange', () => { log('visibility', {state: document.visibilityState}); save(true); });
window.addEventListener('beforeunload', () => save(true));
// ---------------------------------------------------------------- mouse
function edgeAt(x, y){ const r = rat(); if (!r || !r.box || r.deleted || showAll) return null; const b = r.box, [u, v] = toImg(x, y), t = 8 / view.s;
  const inY = v > b[1] - t && v < b[3] + t, inX = u > b[0] - t && u < b[2] + t, e = [];
  if (inY && Math.abs(u - b[0]) < t) e.push(0); if (inY && Math.abs(u - b[2]) < t) e.push(2); if (inX && Math.abs(v - b[1]) < t) e.push(1); if (inX && Math.abs(v - b[3]) < t) e.push(3);
  return e.length ? e : null; }
cv.addEventListener('contextmenu', e => e.preventDefault());
cv.addEventListener('mousedown', e => { touch(); const r0 = cv.getBoundingClientRect(), x = e.clientX - r0.left, y = e.clientY - r0.top, [u, v] = toImg(x, y);
  if (e.button === 2 || e.button === 1 || spaceDown) { drag = {kind: 'pan', x0: e.clientX, y0: e.clientY, ox: view.ox, oy: view.oy}; return; }
  if (showAll) { markMask(u, v); return; }
  if (mode === 'add') { addRat(u, v); return; }
  const ed = edgeAt(x, y); if (ed) { drag = {kind: 'edge', edges: ed, b0: rat().box.slice()}; return; }
  if (mode === 'draw' || (st().arm === 'SCRATCH' && rat() && !rat().deleted)) { drag = {kind: 'draw', start: [u, v], cur: null}; return; }
  drag = {kind: 'pan', x0: e.clientX, y0: e.clientY, ox: view.ox, oy: view.oy}; });
window.addEventListener('mousemove', e => { if (e.target === cv) touch(); const r0 = cv.getBoundingClientRect(), x = e.clientX - r0.left, y = e.clientY - r0.top;
  if (!drag) { cv.style.cursor = showAll ? 'pointer' : edgeAt(x, y) ? 'move' : (mode === 'draw' || mode === 'add' || st().arm === 'SCRATCH') ? 'crosshair' : 'grab'; return; }
  if (drag.kind === 'pan') { view.ox = drag.ox + e.clientX - drag.x0; view.oy = drag.oy + e.clientY - drag.y0; draw(); return; }
  const [u, v] = toImg(x, y);
  if (drag.kind === 'draw') { drag.cur = [u, v]; draw(); return; }
  if (drag.kind === 'edge') { const b = rat().box; drag.edges.forEach(k => { b[k] = (k % 2 === 0) ? u : v; }); draw(); } });
window.addEventListener('mouseup', e => { if (!drag) return; const d = drag; drag = null;
  if (d.kind === 'draw' && d.cur) { const b = normBox(d.start, d.cur); if (b[2] - b[0] >= 5 && b[3] - b[1] >= 5) setManual(b); else draw(); return; }
  if (d.kind === 'edge') { const r = rat(), b = normBox([r.box[0], r.box[1]], [r.box[2], r.box[3]]); const moved = b.some((x, i) => Math.abs(x - d.b0[i]) > 0.5);
    if (moved) { const nb = b.map(x => Math.round(x * 10) / 10); r.box = d.b0; snap(); r.box = nb; r.edge_moves++; log('edge_move', {from: d.b0, to: nb, edges: d.edges}); } else r.box = d.b0; draw(); } });
cv.addEventListener('wheel', e => { e.preventDefault(); touch(); const r0 = cv.getBoundingClientRect(), mx = e.clientX - r0.left, my = e.clientY - r0.top;
  const z = Math.exp(-e.deltaY * 0.0015), s2 = Math.min(Math.max(view.s * z, 0.05), 20);
  view.ox = mx - (mx - view.ox) * s2 / view.s; view.oy = my - (my - view.oy) * s2 / view.s; view.s = s2; draw(); }, {passive: false});
window.addEventListener('resize', () => { view = null; draw(); });
// ---------------------------------------------------------------- keys
document.addEventListener('keyup', e => { if (e.key === ' ') spaceDown = false; });
document.addEventListener('keydown', e => { touch(); const tg = e.target.tagName; if (tg === 'TEXTAREA' || tg === 'SELECT' || (tg === 'INPUT' && e.target.type === 'text')) return;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (k === ' ') { spaceDown = true; e.preventDefault(); return; }
  if (k === 's') { toggleShowAll(); return; } if (k === 'z') { view = null; draw(); return; } if (k === 'u') { doUndo(); return; }
  if (k === 'PageDown') { goFrame(S.cur.fi + 1); e.preventDefault(); return; } if (k === 'PageUp') { goFrame(S.cur.fi - 1); e.preventDefault(); return; }
  if (showAll) return;
  if (k === 'Enter' || k === 'ArrowRight') { nextRat(); e.preventDefault(); return; } if (k === 'ArrowLeft') { prevRat(); e.preventDefault(); return; }
  if (k === 'Escape') { mode = null; draw(); return; }
  const pre = st().arm === 'PRELABEL';
  if (k === 'a' && pre) accept(); else if (k === 'n' && pre) next(); else if (k === 'm' && pre) flag('merged'); else if (k === 'p' && pre) flag('partial');
  else if (k === 'b') { mode = mode === 'draw' ? null : 'draw'; log('draw_mode', {on: mode === 'draw'}); draw(); }
  else if (k === 'r') { mode = mode === 'add' ? null : 'add'; log('add_mode', {on: mode === 'add'}); draw(); }
  else if (k === 'x') delDot();
  else if (k === 'f') fitToMask(); });
// ---------------------------------------------------------------- export / import
function ratRows(){ const out = []; D.frames.forEach(f => { const s = S.frames[f.id];
  const passes = (s.passes || []).map((ps, i) => ({n: i + 1, rats: ps.rats, active_ms: ps.active_ms, showall_ms: ps.showall_ms, completed: ps.completed}))
    .concat([{n: (s.passes || []).length + 1, rats: s.rats, active_ms: s.active_ms, showall_ms: s.showall_ms, completed: s.completed}]);
  passes.forEach(ps => ps.rats.forEach(r => { const fl = r.rank ? (r.cand_flags[r.rank] || {}) : {};
  const any = k => Object.values(r.cand_flags).some(x => x && x[k]);
  out.push({frame_id: f.id, pass: ps.n, domain: f.domain, arm: s.arm, pile_bin: f.pile_bin, frame_order: f.order, rat_id: r.id, origin: r.origin, click_id: r.click_id || '',
    head_u: r.u, head_v: r.v, deleted: r.deleted, n_candidates: r.cand.length, source: r.source || '', rank: r.rank || '', mask_index: r.mask === null ? '' : r.mask,
    mask_cache_index: r.mask === null ? '' : f.masks[r.mask].i, mask_score: r.mask === null ? '' : f.masks[r.mask].s,
    box_x0: r.box ? r.box[0] : '', box_y0: r.box ? r.box[1] : '', box_x1: r.box ? r.box[2] : '', box_y1: r.box ? r.box[3] : '',
    prop_x0: r.prop ? r.prop[0] : '', prop_y0: r.prop ? r.prop[1] : '', prop_x1: r.prop ? r.prop[2] : '', prop_y1: r.prop ? r.prop[3] : '',
    flag_merged: !!fl.merged, flag_partial: !!fl.partial, any_merged: any('merged'), any_partial: any('partial'), edge_moves: r.edge_moves, next_presses: r.next_presses,
    frame_active_s: +(ps.active_ms / 1000).toFixed(2), frame_showall_s: +(ps.showall_ms / 1000).toFixed(2), frame_completed: ps.completed}); })); }); return out; }
function exportJSON(){ return {page_version: D.page_version, run: D.run, plan: D.plan, seed: D.seed, exported_at: iso(), started_at: S.started_at,
  definitions: D.definitions, definition_note: S.defnote, idle_ms: D.idle_ms, coords: 'full-resolution pixels, origin top-left; box = [x0, y0, x1, y1]',
  frames: D.frames.map(f => { const s = S.frames[f.id]; return {frame_id: f.id, domain: f.domain, arm: s.arm, pile_bin: f.pile_bin, order: f.order,
    active_s: +(s.active_ms / 1000).toFixed(3), showall_s: +(s.showall_ms / 1000).toFixed(3), visited: s.visited, completed: s.completed,
    rats: s.rats.map(r => Object.assign({}, r, {mask_cache_index: r.mask === null ? null : f.masks[r.mask].i, mask_score: r.mask === null ? null : f.masks[r.mask].s,
      cand_cache_index: r.cand.map(j => f.masks[j].i), cand_scores: r.cand.map(j => f.masks[j].s)})),
    showall_marks: Object.entries(s.marks).map(([j, m]) => ({mask: +j, mask_cache_index: f.masks[+j].i, mask_score: f.masks[+j].s, mark: m})),
    passes: (s.passes || []).map((ps, i) => ({pass: i + 1, active_s: +(ps.active_ms / 1000).toFixed(3), showall_s: +(ps.showall_ms / 1000).toFixed(3),
      completed: ps.completed, archived_at: ps.archived_at, rats: ps.rats,
      showall_marks: Object.entries(ps.marks || {}).map(([j, m]) => ({mask: +j, mask_cache_index: f.masks[+j].i, mask_score: f.masks[+j].s, mark: m}))}))}; }),
  events: S.events}; }
function csvCell(v){ v = String(v == null ? '' : v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
function exportCSV(){ const rows = ratRows(); const cols = Object.keys(rows[0] || {frame_id: ''});
  return [cols.join(',')].concat(rows.map(r => cols.map(c => csvCell(r[c])).join(','))).join('\n') + '\n'; }
function stamp(){ const d = new Date(), p = n => String(n).padStart(2, '0'); return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + '_' + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds()); }
function download(name, text, type){ const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], {type})); a.download = name;
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); }
$('ej').addEventListener('click', () => { log('export'); download(D.export_prefix + stamp() + '.json', JSON.stringify(exportJSON()), 'application/json'); });
$('ec').addEventListener('click', () => download(D.export_prefix + stamp() + '.csv', exportCSV(), 'text/csv'));
$('ij').addEventListener('change', e => { const f = e.target.files[0]; if (!f) return; f.text().then(t => { const o = JSON.parse(t);
  if (!o.frames || o.run !== D.run) { alert('not an export of this page'); return; }
  o.frames.forEach(x => { if (!S.frames[x.frame_id]) return; const s = S.frames[x.frame_id]; s.active_ms = x.active_s * 1000; s.showall_ms = x.showall_s * 1000;
    s.visited = x.visited; s.completed = x.completed; s.rats = x.rats.map(r => { const q = Object.assign({}, r); delete q.mask_cache_index; delete q.mask_score; delete q.cand_cache_index; delete q.cand_scores; return q; });
    s.marks = {}; (x.showall_marks || []).forEach(m => s.marks[m.mask] = m.mark); s.next_add = 1 + s.rats.filter(r => r.origin === 'added').length;
    s.passes = (x.passes || []).map(ps => { const mk = {}; (ps.showall_marks || []).forEach(m => mk[m.mask] = m.mark);
      return {rats: ps.rats, active_ms: ps.active_s * 1000, showall_ms: ps.showall_s * 1000, completed: ps.completed, marks: mk, archived_at: ps.archived_at}; }); });
  S.events = o.events || []; S.defnote = o.definition_note || ''; $('defnote').value = S.defnote; save(true); draw(); }); });
$('defnote').value = S.defnote || '';
$('defnote').addEventListener('input', e => { S.defnote = e.target.value; save(); });
$('defnote').addEventListener('change', () => log('definition_note', {text: S.defnote}));
$('showall').addEventListener('change', e => toggleShowAll(e.target.checked));
$('redo').addEventListener('click', () => redoFrame(false));
$('goto').innerHTML = D.frames.map((f, i) => '<option value="' + i + '">' + (i + 1) + ' · ' + (f.domain === 'ir' ? 'IR' : 'col') + ' · ' + f.arm + '</option>').join('');
$('goto').addEventListener('change', e => goFrame(+e.target.value));
goFrame(S.cur.fi); S.cur.ri = Math.min(S.cur.ri, rats().length - 1);
window.__pl = {S: () => S, D, goFrame, cur: () => ({fi: S.cur.fi, ri: S.cur.ri}), rat: () => rat(), frame: () => fr(), drawn: () => drawnMasks,
  candidatesAt, exportJSON, exportCSV, key: KEY, redoFrame, fitToMask, setLastInput: dt => { lastInput = performance.now() - dt; },
  imgToClient: (u, v) => { const r0 = cv.getBoundingClientRect(), [x, y] = toCv(u, v); return [x + r0.left, y + r0.top]; },
  ready: () => { const im = img(); return im.complete && im.naturalWidth > 0; }, showAll: () => showAll, mode: () => mode, save: () => save(true),
  visible: () => document.visibilityState};
})();
"""


def page_html(run_name: str) -> str:
    import html as _html
    defs = "".join(f"<div><dt>{_html.escape(k)}:</dt><dd>{_html.escape(v)}</dd></div>" for k, v in DEFINITIONS)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>In-box pre-label edit</title><style>{PAGE_CSS}</style></head><body>
<header><h1>In-box CH07 — SAM 3 "rat" pre-label edit pilot (B, dev) · 预标注编辑</h1>
<dl class="defs">{defs}</dl>
<div class="bar"><label style="flex:1;display:flex;gap:6px;align-items:center">my definition changes / 我的定义修改:
<input type="text" id="defnote" style="flex:1;font:inherit;padding:3px 6px" placeholder="optional — exported with your labels"></label></div>
<div class="bar"><div style="flex:1"><div class="prog"><div id="progbar" style="width:0"></div></div></div><span id="progtxt"></span>
<button id="ej" type="button">Export JSON</button><button id="ec" type="button">Export CSV</button>
<label class="btn">Import JSON<input id="ij" type="file" accept=".json,application/json" class="hidden"></label></div></header>
<div class="wrap"><div><div class="bar"><span id="armtag"></span><span id="ftitle" style="font-weight:600"></span><span id="timetxt" style="color:var(--muted)"></span></div>
<canvas id="cv"></canvas><div id="banner"></div></div>
<div class="side"><div id="status"></div>
<label><input type="checkbox" id="showall"> show all "rat" candidates (S) · 显示全部候选</label>
<label>jump to frame <select id="goto"></select></label>
<button id="redo" type="button" title="the current labels are kept as an earlier pass">redo this frame (keeps the earlier pass) · 重做此帧</button>
<div class="keys"><b>PRELABEL</b> (cyan = candidate mask, dashed yellow = its box):<br>
A accept 接受 (the box = the mask's bounding box, no padding; drag its edges to your own convention 按你的习惯拖边) ·
N next candidate 下一个候选 (then "none usable") · M flag merged 合并 · P flag partial 不完整 · B draw a box by hand 手画框 ·
F fit the box back to the mask 恢复为 mask 框<br>
<b>SCRATCH</b>: drag one box per rat 每只鼠拖一个框<br>
<b>both</b>: drag a green box edge to adjust 拖边调整 · R add a rat whose head is hidden, then click its body 加鼠(头被挡) ·
X delete a dot that is not a rat 删除点 · Enter / → next rat, then next frame 下一只 · ← previous 上一只 · U undo 撤销 ·
PageDown / PageUp frame 换帧 · wheel zoom 缩放 · right-drag or Space + drag pan 平移 · Z fit 适配 · Esc cancel<br>
Clock: active time per frame; it pauses when the tab is hidden or after 45 s without input (计时: 45 秒无操作暂停). Stop any time; progress is saved in this browser.</div>
<div class="keys">Exports → <code>cv/configs/inbox_sam3_prelabel_edit_2026c/</code> · run {_html.escape(run_name)}</div></div></div>
<script src="pl_data.js"></script>
<script>{PAGE_JS}</script></body></html>
"""


# ============================================================================================ build
def build(run: Path, check: bool = True) -> dict:
    frames = pd.read_csv(run / "frames.csv")
    heads = pd.read_csv(run / "heads.csv")
    arms = assign_arms(frames, heads)
    out = run / "prelabel_edit"
    if out.exists():
        shutil.rmtree(out)
    (out / "frames").mkdir(parents=True)
    data = {"page_version": PAGE_VERSION, "run": run.name, "plan": PLAN, "seed": SEED, "idle_ms": IDLE_MS, "cover_px": S.COVER_PX,
            "definitions": [{"term": k, "text": v} for k, v in DEFINITIONS], "export_prefix": "inbox_sam3_prelabel_edit_2026c_", "frames": []}
    cand_rows = []
    for r in arms.itertuples():
        H = heads[heads.frame_id == r.frame_id].sort_values(["u", "click_id"]).reset_index(drop=True)   # numbered left to right
        pl = frame_payload(run, r.frame_id, H)
        dst = out / "frames" / Path(r.path).name
        shutil.copy2(r.path, dst)
        data["frames"].append({"id": r.frame_id, "domain": r.domain, "arm": r.arm, "pile_bin": r.pile_bin, "order": int(r.order),
                               "img": f"frames/{dst.name}", "w": S.IMG_W, "h": S.IMG_H,
                               "heads": [{"c": h.click_id, "u": round(float(h.u), 1), "v": round(float(h.v), 1)} for h in H.itertuples()],
                               "masks": pl["masks"], "cand": pl["cand"]})
        for i, h in enumerate(H.itertuples()):
            c = pl["cand"][i]
            cand_rows.append({"frame_id": r.frame_id, "domain": r.domain, "arm": r.arm, "pile_bin": r.pile_bin, "click_id": h.click_id,
                              "num": i + 1, "pile_size": int(h.pile_size), "n_candidates": len(c),
                              "top_score": pl["masks"][c[0]]["s"] if c else np.nan,
                              "candidate_cache_index": ";".join(str(pl["masks"][j]["i"]) for j in c)})
        print(f"  build {int(r.order)}/{len(arms)} {r.frame_id} ({r.arm}): {len(pl['masks'])} rat masks, {len(H)} heads", flush=True)
    (out / "pl_data.js").write_text("window.PL_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n", encoding="utf-8")
    (out / "index.html").write_text(page_html(run.name), encoding="utf-8")
    arms.drop(columns=["path"]).to_csv(out / "arms.csv", index=False)
    cr = pd.DataFrame(cand_rows)
    cr.to_csv(out / "head_candidates.csv", index=False)
    meta = {"made": datetime.now().isoformat(timespec="seconds"), "plan": PLAN, "run": run.as_posix(), "seed": SEED,
            "n_frames": len(arms), "arms": arms.groupby(["domain", "pile_bin", "arm"]).size().rename("n").reset_index().to_dict("records"),
            "n_prelabel": int((arms.arm == "PRELABEL").sum()), "n_scratch": int((arms.arm == "SCRATCH").sum()),
            "n_heads": len(cr), "heads_with_0_candidates": int((cr.n_candidates == 0).sum()),
            "candidates_per_head_median": float(cr.n_candidates.median()),
            "size": {"pl_data_js_bytes": (out / "pl_data.js").stat().st_size,
                     "frames_bytes": int(sum(p.stat().st_size for p in (out / "frames").glob("*.jpg"))),
                     "index_html_bytes": (out / "index.html").stat().st_size,
                     "n_masks": int(sum(len(f["masks"]) for f in data["frames"])),
                     "n_polygon_points": int(sum(len(p) // 2 for f in data["frames"] for m in f["masks"] for p in m["p"]))},
            "git_commit": git_commit()}
    if check:
        meta["page_check"] = page_check(out, data)
        S.write_json(out / "page_check.json", meta["page_check"])
        print(f"page check: {meta['page_check']['verdict']}", flush=True)
    S.write_json(out / "build_meta.json", meta)
    return meta


# ============================================================================================ headless check
def page_check(out: Path, data: dict) -> dict:
    """Headless Chrome (throwaway profile): accept, N cycling, manual box, edge move, SCRATCH box, add + delete + undo,
    show all (marks, separate clock), the idle pause, persistence across a reload, export; JS candidates at every clicked
    head vs the Python mask-based lists; no network URL."""
    import inbox_identity_page as ipage
    html_t, js_t = (out / "index.html").read_text(encoding="utf-8"), (out / "pl_data.js").read_text(encoding="utf-8")
    res = {"network_urls": re.findall(r"https?://[^\s\"'<>]+", html_t) + re.findall(r"https?://[^\s\"'<>]+", js_t)}
    prof = Path(tempfile.mkdtemp(prefix="plcheck_"))
    p, wsu, bws = ipage._chrome((out / "index.html").resolve().as_uri(), prof, ipage._free_port())
    c = None
    try:
        c = ipage._CDP(wsu)
        c.call("Runtime.enable")

        def ready():
            for _ in range(240):
                try:
                    if c.ev("!!window.__pl && window.__pl.ready()"):
                        return True
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(0.25)
            return False

        def key(k):
            c.ev(f"document.dispatchEvent(new KeyboardEvent('keydown', {{key: {json.dumps(k)}, bubbles: true}}))")

        def mouse(kind, u, v, button=0, target="cv"):
            c.ev(f"(() => {{ const [x, y] = window.__pl.imgToClient({u}, {v}); const el = {('document.getElementById(' + json.dumps(target) + ')') if target else 'window'};"
                 f" el.dispatchEvent(new MouseEvent({json.dumps(kind)}, {{clientX: x, clientY: y, button: {button}, bubbles: true}})); }})()")

        def drag(u0, v0, u1, v1):
            mouse("mousedown", u0, v0)
            mouse("mousemove", (u0 + u1) / 2, (v0 + v1) / 2)
            mouse("mousemove", u1, v1)
            mouse("mouseup", u1, v1)

        def rat():
            return c.ev("JSON.parse(JSON.stringify(window.__pl.rat()))")
        res["loaded"] = ready()
        fr = data["frames"]
        pre = [i for i, f in enumerate(fr) if f["arm"] == "PRELABEL" and len(f["cand"]) >= 2 and len(f["cand"][0]) >= 1
               and any(len(x) >= 2 for x in f["cand"][1:])]
        scr = [i for i, f in enumerate(fr) if f["arm"] == "SCRATCH"]
        # 1 accept + N cycling on a PRELABEL frame
        fi = pre[0]
        c.ev(f"window.__pl.goFrame({fi})")
        ready()
        f = fr[fi]
        first = c.ev("window.__pl.cur().ri")
        key("a")
        r = rat()
        cb = f["masks"][f["cand"][first][0]]["b"] if f["cand"][first] else None
        res["accept"] = {"source": r["source"], "rank": r["rank"], "box_equals_candidate_box": r["box"] == cb, "drawn": c.ev("window.__pl.drawn()"),
                         "ok": bool(cb) and r["source"] == "cand" and r["rank"] == 1 and r["box"] == cb}
        # N cycles on a rat with >= 2 candidates
        j = next(i for i, x in enumerate(f["cand"]) if len(x) >= 2 and i != first)
        c.ev(f"(() => {{ const S = window.__pl.S(); S.cur.ri = {j}; }})()")
        n = len(f["cand"][j])
        seen = []
        for _ in range(n + 1):
            key("n")
            seen.append(c.ev("window.__pl.rat().k"))
        res["next_cycle"] = {"n_candidates": n, "k_sequence": seen, "next_presses": rat()["next_presses"],
                             "ok": seen[:n] == list(range(1, n)) + [n] and seen[n] == 0}
        # flag merged on the displayed candidate
        key("m")
        res["flag"] = {"cand_flags": rat()["cand_flags"], "ok": rat()["cand_flags"].get("1", {}).get("merged") is True}
        # manual box via B + drag, then an edge move
        u, v = f["heads"][j]["u"], f["heads"][j]["v"]
        key("b")
        drag(u - 150, v - 100, u + 200, v + 180)
        r = rat()
        res["manual_box"] = {"source": r["source"], "box": r["box"],
                             "ok": r["source"] == "manual" and abs(r["box"][0] - (u - 150)) < 3 and abs(r["box"][3] - (v + 180)) < 3}
        b = r["box"]
        drag(b[2], (b[1] + b[3]) / 2, b[2] + 60, (b[1] + b[3]) / 2)
        r2 = rat()
        res["edge_move"] = {"edge_moves": r2["edge_moves"], "box": r2["box"], "ok": r2["edge_moves"] == 1 and abs(r2["box"][2] - (b[2] + 60)) < 3}
        # F: fit the accepted (rank-1) box back to the mask bbox after an edge move
        c.ev(f"(() => {{ window.__pl.S().cur.ri = {first}; }})()")
        bf = rat()["box"]
        drag(bf[0], (bf[1] + bf[3]) / 2, bf[0] - 40, (bf[1] + bf[3]) / 2)
        moved = rat()["box"]
        key("f")
        fitted = rat()["box"]
        res["fit_to_mask"] = {"moved": moved, "fitted": fitted, "ok": moved != cb and fitted == cb}
        c.ev(f"(() => {{ window.__pl.S().cur.ri = {j}; }})()")
        # add a rat at a clicked head of the frame (JS candidates), delete it, undo
        h0 = f["heads"][0]
        fid_js = json.dumps(f["id"])
        nr = c.ev(f"window.__pl.S().frames[{fid_js}].rats.length")
        key("r")
        mouse("mousedown", h0["u"], h0["v"])
        mouse("mouseup", h0["u"], h0["v"])
        ra = rat()
        key("x")
        dl = c.ev(f"window.__pl.S().frames[{fid_js}].rats[{nr}].deleted")
        key("u")
        ud = c.ev(f"window.__pl.S().frames[{fid_js}].rats[{nr}].deleted")
        res["add_delete_undo"] = {"added_origin": ra["origin"], "added_n_cand": len(ra["cand"]), "deleted": dl, "after_undo_deleted": ud,
                                  "ok": ra["origin"] == "added" and dl is True and ud is False}
        # show all: every mask drawn, a mark, the separate clock
        key("s")
        drawn_all = c.ev("window.__pl.drawn()")
        cx = cy = None
        for m0 in sorted(f["masks"], key=lambda m: -m["a"]):
            for pts in m0["p"]:
                x0, y0 = float(np.mean(pts[0::2])), float(np.mean(pts[1::2]))
                if _pip(x0, y0, pts):
                    cx, cy = x0, y0
                    break
            if cx is not None:
                break
        mouse("mousedown", cx, cy)
        mouse("mouseup", cx, cy)
        marks = c.ev("JSON.parse(JSON.stringify(window.__pl.S().frames[window.__pl.frame().id].marks))")
        a0 = c.ev("window.__pl.S().frames[window.__pl.frame().id].active_ms")
        s0 = c.ev("window.__pl.S().frames[window.__pl.frame().id].showall_ms")
        for _ in range(4):
            c.ev("window.__pl.setLastInput(0)")
            time.sleep(0.5)
        a1 = c.ev("window.__pl.S().frames[window.__pl.frame().id].active_ms")
        s1 = c.ev("window.__pl.S().frames[window.__pl.frame().id].showall_ms")
        key("s")
        res["show_all"] = {"drawn": drawn_all, "n_masks": len(f["masks"]), "marks": marks, "showall_ms_gain": s1 - s0, "active_ms_gain": a1 - a0,
                           "ok": drawn_all == len(f["masks"]) and len(marks) >= 1 and s1 - s0 > 1000 and a1 - a0 < 1e-6}
        # idle pause
        c.ev("window.__pl.setLastInput(50000)")
        i0 = c.ev("window.__pl.S().frames[window.__pl.frame().id].active_ms")
        time.sleep(1.6)
        i1 = c.ev("window.__pl.S().frames[window.__pl.frame().id].active_ms")
        c.ev("window.__pl.setLastInput(0)")
        time.sleep(1.2)
        i2 = c.ev("window.__pl.S().frames[window.__pl.frame().id].active_ms")
        res["idle_pause"] = {"gain_while_idle_ms": i1 - i0, "gain_after_input_ms": i2 - i1, "ok": i1 - i0 < 1e-6 and i2 - i1 > 500}
        # SCRATCH frame: dots only, drag = box
        fs = scr[0]
        c.ev(f"window.__pl.goFrame({fs})")
        ready()
        g = fr[fs]
        hu, hv = g["heads"][0]["u"], g["heads"][0]["v"]
        drag(hu - 120, hv - 90, hu + 160, hv + 140)
        r = rat()
        res["scratch"] = {"arm": c.ev("window.__pl.S().frames[window.__pl.frame().id].arm"), "drawn_masks": c.ev("window.__pl.drawn()"),
                          "source": r["source"], "ok": r["source"] == "manual" and c.ev("window.__pl.drawn()") == 0}
        # Enter -> next rat; past the last -> frame done, next frame
        nlive = sum(1 for x in c.ev("window.__pl.S().frames[window.__pl.frame().id].rats.map(r => r.deleted)") if not x)
        for _ in range(nlive):
            key("Enter")
        res["enter_flow"] = {"frame_completed": c.ev(f"window.__pl.S().frames[{json.dumps(g['id'])}].completed"),
                             "now_frame": c.ev("window.__pl.cur().fi"), "ok": c.ev(f"window.__pl.S().frames[{json.dumps(g['id'])}].completed") is True
                             and c.ev("window.__pl.cur().fi") == min(fs + 1, len(fr) - 1)}
        # JS candidates (point-in-polygon + 15 px on the simplified polygons) vs the Python mask lists, at every clicked head
        agree = tot = 0
        diffs = []
        for i, fz in enumerate(fr):
            c.ev(f"window.__pl.goFrame({i})")
            js = c.ev("window.__pl.frame().heads.map(h => window.__pl.candidatesAt(h.u, h.v))")
            for hi, (a, b) in enumerate(zip(js, fz["cand"])):
                tot += 1
                if list(a) == list(b):
                    agree += 1
                elif len(diffs) < 5:
                    diffs.append({"frame": fz["id"], "head": hi + 1, "js": a[:6], "py": b[:6]})
        res["candidates_js_vs_python"] = {"heads": tot, "identical_lists": agree, "examples": diffs}
        # persistence + export
        snap_before = c.ev(f"JSON.stringify(window.__pl.S().frames[{json.dumps(fr[fi]['id'])}].rats.map(r => [r.source, r.rank, r.box]))")
        n_ev = c.ev("window.__pl.S().events.length")
        res["visibility_state"] = c.ev("window.__pl.visible()")
        c.ev("window.__pl.save()")
        c.call("Page.reload")
        time.sleep(1.5)
        ready()
        snap_after = c.ev(f"JSON.stringify(window.__pl.S().frames[{json.dumps(fr[fi]['id'])}].rats.map(r => [r.source, r.rank, r.box]))")
        res["persistence"] = {"ok": snap_before == snap_after, "events_before": n_ev, "events_after": c.ev("window.__pl.S().events.length")}
        ej = c.ev("window.__pl.exportJSON()")
        csv_lines = c.ev("window.__pl.exportCSV().trim().split('\\n').length")
        n_rats = sum(len(x["rats"]) for x in ej["frames"])
        evk = sorted({e["ev"] for e in ej["events"]})
        f0 = next(x for x in ej["frames"] if x["frame_id"] == fr[fi]["id"])
        props_ok = all((r["prop"] == fr[fi]["masks"][r["cand"][0]]["b"]) if r["cand"] else r["prop"] is None for r in f0["rats"])
        res["proposed_box"] = {"ok": props_ok}
        # redo: archive the pass, fresh labels
        c.ev(f"window.__pl.goFrame({fi})")
        c.ev("window.__pl.redoFrame(true)")
        ej2 = c.ev("window.__pl.exportJSON()")
        f1 = next(x for x in ej2["frames"] if x["frame_id"] == fr[fi]["id"])
        res["redo"] = {"passes": len(f1["passes"]), "fresh_boxes": sum(1 for r in f1["rats"] if r["box"]),
                       "archived_boxes": sum(1 for r in f1["passes"][0]["rats"] if r["box"]) if f1["passes"] else 0,
                       "csv_lines_after": c.ev("window.__pl.exportCSV().trim().split('\\n').length"),
                       "ok": len(f1["passes"]) == 1 and sum(1 for r in f1["rats"] if r["box"]) == 0 and f1["passes"][0]["rats"][first]["source"] == "cand"}
        res["export"] = {"frames": len(ej["frames"]), "rats": n_rats, "csv_lines": csv_lines, "event_kinds": evk,
                         "ok": len(ej["frames"]) == len(fr) and csv_lines == n_rats + 1
                         and {"accept", "next", "flag", "manual_box", "edge_move", "add_rat", "delete_dot", "undo", "show_all", "showall_mark", "frame_done",
                              "fit_to_mask"} <= set(evk)}
        c.ev("localStorage.clear()")
    finally:
        if c:
            c.close()
        ipage._close_chrome(p, bws)
        shutil.rmtree(prof, ignore_errors=True)
    keys = ["accept", "next_cycle", "flag", "manual_box", "edge_move", "add_delete_undo", "show_all", "idle_pause", "scratch", "enter_flow",
            "persistence", "export", "proposed_box", "redo", "fit_to_mask"]
    res["verdict"] = "PASS" if (res.get("loaded") and all(res[k]["ok"] for k in keys) and not res["network_urls"]) else "FAIL"
    return res


def _pip(x: float, y: float, p: list) -> bool:
    """Even-odd point-in-polygon on a flat [x0, y0, x1, y1, ...] list (same rule as the page)."""
    ins = False
    n = len(p) // 2
    j = n - 1
    for i in range(n):
        xi, yi, xj, yj = p[2 * i], p[2 * i + 1], p[2 * j], p[2 * j + 1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            ins = not ins
        j = i
    return ins


def git_commit() -> str:
    try:
        h = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", "cv/cv_field/inbox_prelabel_edit.py"],
                               capture_output=True, text=True).stdout.strip()
        return h + ("+dirty" if dirty else "")
    except Exception:  # noqa: BLE001
        return "unknown"


# ============================================================================================ summarize
def box_iou(a, b) -> float:
    if a is None or b is None:
        return np.nan
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return float(inter / u) if u > 0 else np.nan


def frame_passes(f: dict) -> list[dict]:
    """All passes of one exported frame in order: the archived ones, then the current state."""
    cur = {"pass": len(f.get("passes") or []) + 1, "rats": f["rats"], "active_s": f["active_s"], "showall_s": f["showall_s"],
           "completed": f["completed"], "showall_marks": f.get("showall_marks") or []}
    return list(f.get("passes") or []) + [cur]


def main_pass(f: dict) -> dict:
    """B metrics use each frame's FIRST completed pass (else the current state); later passes enter only the repeat check."""
    ps = frame_passes(f)
    done = [p for p in ps if p["completed"]]
    return done[0] if done else ps[-1]


def rat_table(ex: dict) -> pd.DataFrame:
    rows = []
    for f0 in ex["frames"]:
        mp = main_pass(f0)
        f = {**f0, "rats": mp["rats"], "completed": mp["completed"]}
        for r in f["rats"]:
            cf = r.get("cand_flags") or {}
            acc = cf.get(str(r.get("rank")), {}) if r.get("rank") else {}
            rows.append({"frame_id": f["frame_id"], "domain": f["domain"], "arm": f["arm"], "pile_bin": f["pile_bin"], "completed": bool(f["completed"]),
                         "rat_id": r["id"], "origin": r["origin"], "deleted": bool(r["deleted"]), "n_cand": len(r.get("cand") or []),
                         "source": r.get("source") or "", "rank": r.get("rank"), "boxed": r.get("box") is not None,
                         "acc_merged": bool(acc.get("merged")), "acc_partial": bool(acc.get("partial")),
                         "any_merged": any(bool((v or {}).get("merged")) for v in cf.values()),
                         "any_partial": any(bool((v or {}).get("partial")) for v in cf.values()),
                         "edge_moves": int(r.get("edge_moves") or 0), "next_presses": int(r.get("next_presses") or 0),
                         "prop": r.get("prop"), "box": r.get("box"), "pass": mp.get("pass", 1)})
    t = pd.DataFrame(rows)
    if t.empty:
        return t
    return derive(t)


def derive(t: pd.DataFrame) -> pd.DataFrame:
    """Derived per-object columns shared by v1 (rats) and v2 (implant / rat boxes)."""
    t = t.copy()
    t["usable1"] = (t.source == "cand") & (t["rank"] == 1) & ~t.acc_merged & ~t.acc_partial
    t["usable_any"] = (t.source == "cand") & ~t.acc_merged & ~t.acc_partial
    t["manual"] = t.source == "manual"
    t["iou_prop_final"] = [box_iou(p, b) for p, b in zip(t.prop, t.box)]
    t["no_edit"] = (t.source == "cand") & (t["rank"] == 1) & (t.edge_moves == 0)
    t["edge_only"] = (t.source == "cand") & (t["rank"] == 1) & (t.edge_moves > 0)
    t["other_cand"] = (t.source == "cand") & (t["rank"] != 1)
    t["edge_shift_px"] = [float(np.mean(np.abs(np.asarray(b, float) - np.asarray(p, float)))) if (eo and p is not None and b is not None) else np.nan
                          for eo, p, b in zip(t.edge_only, t.prop, t.box)]
    return t


def quality_block(d: pd.DataFrame) -> dict:
    """Amendment C2 item 1 on PRELABEL rats with a proposal (descriptive)."""
    d = d[(d.arm == "PRELABEL") & d.prop.notna()]
    n = len(d)
    q = d.iou_prop_final.dropna()
    es = d.edge_shift_px.dropna()
    return {"n_with_proposal": n, "iou_median": float(q.median()) if len(q) else np.nan,
            "iou_q25": float(q.quantile(0.25)) if len(q) else np.nan, "iou_q75": float(q.quantile(0.75)) if len(q) else np.nan,
            "no_edit": d.no_edit.mean() if n else np.nan, "edge_only": d.edge_only.mean() if n else np.nan,
            "edge_shift_median_px": float(es.median()) if len(es) else np.nan, "other_candidate": d.other_cand.mean() if n else np.nan,
            "manual": d.manual.mean() if n else np.nan}


EDGES = ("left", "right", "top", "bottom")
ONE_EDGE_RATIO, ONE_EDGE_MIN = 2.0, 0.05     # 'one edge much worse': |median| >= 2 x the median |median| of the other three and >= 0.05


def edge_shifts(prop, box) -> dict:
    """Signed shift of each edge from the mask bbox (prop) to the final box; + = the final box is larger on that side.
    px and as a fraction of the mask-bbox width (left / right) or height (top / bottom)."""
    p, b = np.asarray(prop, float), np.asarray(box, float)
    w, h = p[2] - p[0], p[3] - p[1]
    px = {"left": p[0] - b[0], "right": b[2] - p[2], "top": p[1] - b[1], "bottom": b[3] - p[3]}
    den = {"left": w, "right": w, "top": h, "bottom": h}
    return {**{f"{e}_px": float(px[e]) for e in EDGES}, **{f"{e}_frac": float(px[e] / den[e]) if den[e] > 0 else np.nan for e in EDGES}}


def c3_table(t: pd.DataFrame) -> pd.DataFrame:
    """PRELABEL rats whose first candidate was kept (rank 1, any edits), with their per-edge shifts."""
    d = t[(t.arm == "PRELABEL") & (t.source == "cand") & (t["rank"] == 1) & ~t.deleted & t.prop.notna() & t.box.notna()]
    rows = [{**r, **edge_shifts(r["prop"], r["box"])} for r in d.to_dict("records")]
    return pd.DataFrame(rows)


def q3(x) -> dict:
    x = pd.Series(x, dtype=float).dropna()
    return {"n": int(len(x)), "median": float(x.median()) if len(x) else np.nan,
            "q25": float(x.quantile(0.25)) if len(x) else np.nan, "q75": float(x.quantile(0.75)) if len(x) else np.nan}


def c3_block(d: pd.DataFrame) -> dict:
    return {e: {"px": q3(d[f"{e}_px"]) if len(d) else q3([]), "frac": q3(d[f"{e}_frac"]) if len(d) else q3([])} for e in EDGES}


def uniformity(blk: dict) -> dict:
    """Spread flag: an edge whose IQR of the fraction exceeds |its median|. One-edge flag: the edge with the largest |median|
    is >= ONE_EDGE_RATIO x the median |median| of the other three and >= ONE_EDGE_MIN. Uniform = neither flag."""
    med = {e: blk[e]["frac"]["median"] for e in EDGES}
    iqr = {e: blk[e]["frac"]["q75"] - blk[e]["frac"]["q25"] for e in EDGES}
    if any(not np.isfinite(v) for v in med.values()):
        return {"spread_edges": [], "spread_flag": None, "one_edge_flag": None, "worst_edge": None, "uniform": None}
    spread = [e for e in EDGES if iqr[e] > abs(med[e])]
    worst = max(EDGES, key=lambda e: abs(med[e]))
    others = float(np.median([abs(med[e]) for e in EDGES if e != worst]))
    one = bool(abs(med[worst]) >= ONE_EDGE_MIN and abs(med[worst]) >= ONE_EDGE_RATIO * others)
    return {"spread_edges": spread, "spread_flag": bool(spread), "one_edge_flag": one, "worst_edge": worst,
            "worst_over_others": float(abs(med[worst]) / others) if others > 0 else np.inf, "uniform": not spread and not one}


def size_block(boxes) -> dict:
    b = np.asarray([x for x in boxes if x is not None], float).reshape(-1, 4)
    w, h = b[:, 2] - b[:, 0], b[:, 3] - b[:, 1]
    return {"width_px": q3(w), "height_px": q3(h), "aspect_w_over_h": q3(w / np.where(h > 0, h, np.nan))}


def match_by_head(ra: list, rb: list, tol: float = S.COVER_PX) -> list[tuple]:
    """One-to-one pairs of boxed, not deleted rats of two passes by head point: greedy nearest within tol px."""
    A = [r for r in ra if not r.get("deleted") and r.get("box")]
    B = [r for r in rb if not r.get("deleted") and r.get("box")]
    cand = sorted((float(np.hypot(a["u"] - b["u"], a["v"] - b["v"])), i, j) for i, a in enumerate(A) for j, b in enumerate(B))
    ua, ub, out = set(), set(), []
    for d, i, j in cand:
        if d <= tol and i not in ua and j not in ub:
            ua.add(i)
            ub.add(j)
            out.append((A[i], B[j], d))
    return out


def repeat_pairs(exports: list[dict]) -> pd.DataFrame:
    """Frames labelled twice: completed passes of one frame within an export (the page's 'redo this frame'), and the same
    frame completed in another export from a different labelling session (other started_at). Consecutive passes are
    compared; rats matched by head point (nearest within 15 px); IoU of the two final boxes."""
    rows = []
    by_frame: dict = {}
    for k, ex in enumerate(exports):
        for f in ex["frames"]:
            for p in frame_passes(f):
                if p["completed"]:
                    by_frame.setdefault(f["frame_id"], []).append({"src": f"{k}:{ex.get('started_at')}", "pass": p["pass"], "arm": f["arm"],
                                                                   "domain": f["domain"], "pile_bin": f["pile_bin"], "rats": p["rats"]})
    for fid, ps in by_frame.items():
        seen, uniq = set(), []
        for p in ps:                      # one export's copy of an earlier session is not a repeat: dedupe identical labels
            key = json.dumps([(r.get("id"), r.get("box")) for r in p["rats"]])
            if key not in seen:
                seen.add(key)
                uniq.append(p)
        for a, b in zip(uniq[:-1], uniq[1:]):
            for ra, rb, d in match_by_head(a["rats"], b["rats"]):
                rows.append({"frame_id": fid, "domain": a["domain"], "pile_bin": a["pile_bin"], "arm": a["arm"], "pass_a": a["pass"],
                             "pass_b": b["pass"], "rat_a": ra["id"], "rat_b": rb["id"], "head_dist_px": d, "iou": box_iou(ra["box"], rb["box"])})
    return pd.DataFrame(rows)


def summarize(ex: dict, more: list | None = None) -> dict:
    """The plan's B summary on one export (descriptive), + amendment C2 quality from the user's own corrections, + the
    optional repeat check (frames labelled twice; `more` = further exports from other labelling sessions). Evaluated rats =
    not deleted and with a final box, in each frame's main (first completed) pass."""
    t = rat_table(ex)
    fr = pd.DataFrame([{"frame_id": f["frame_id"], "domain": f["domain"], "arm": f["arm"], "pile_bin": f["pile_bin"],
                        "completed": bool(mp["completed"]), "active_s": float(mp["active_s"]), "showall_s": float(mp["showall_s"]),
                        "n_marks": len(mp.get("showall_marks") or []),
                        "n_garbage": sum(1 for m in (mp.get("showall_marks") or []) if m["mark"] == "garbage"),
                        "n_fragment": sum(1 for m in (mp.get("showall_marks") or []) if m["mark"] == "fragment")}
                       for f in ex["frames"] for mp in [main_pass(f)]])
    ev = t[~t.deleted & t.boxed] if len(t) else t

    def pre_block(d: pd.DataFrame) -> dict:
        d = d[d.arm == "PRELABEL"]
        n = len(d)
        return {"n_rats": n, "usable1": d.usable1.mean() if n else np.nan, "usable_any": d.usable_any.mean() if n else np.nan,
                "merged": d.any_merged.mean() if n else np.nan, "partial": d.any_partial.mean() if n else np.nan,
                "manual": d.manual.mean() if n else np.nan, "no_candidate": (d.n_cand == 0).mean() if n else np.nan,
                "edge_moves_per_rat": d.edge_moves.mean() if n else np.nan, "next_per_rat": d.next_presses.mean() if n else np.nan}

    def time_block(arm: str, keyf=None) -> dict:
        f = fr[(fr.arm == arm) & fr.completed]
        if keyf is not None:
            f = f[keyf(f)]
        nb = ev[ev.frame_id.isin(f.frame_id)].groupby("frame_id").size().reindex(f.frame_id).fillna(0) if len(ev) else pd.Series(0, index=f.frame_id)
        per = (f.set_index("frame_id").active_s / nb.replace(0, np.nan)).dropna()
        return {"frames": len(f), "rats": int(nb.sum()), "s_per_rat": float(f.active_s.sum() / nb.sum()) if nb.sum() else np.nan,
                "median_frame_s_per_rat": float(per.median()) if len(per) else np.nan}
    out = {"n_frames_visited": int(sum(1 for f in ex["frames"] if f.get("visited"))), "n_frames_completed": int(fr.completed.sum()),
           "n_rats_evaluated": int(len(ev)), "n_deleted": int(t.deleted.sum()) if len(t) else 0,
           "n_added": int(((t.origin == "added") & ~t.deleted).sum()) if len(t) else 0,
           "n_unboxed": int((~t.deleted & ~t.boxed).sum()) if len(t) else 0,
           "prelabel_all": pre_block(ev), "quality_all": quality_block(ev) if len(ev) else quality_block(t),
           "time": {a: time_block(a) for a in ("PRELABEL", "SCRATCH")}, "split": [],
           "showall": {"frames_used": int((fr.showall_s > 0).sum()), "showall_s": float(fr.showall_s.sum()), "marks": int(fr.n_marks.sum()),
                       "garbage": int(fr.n_garbage.sum()), "fragment": int(fr.n_fragment.sum()),
                       "by_domain": fr.groupby("domain")[["n_garbage", "n_fragment"]].sum().reset_index().to_dict("records")},
           "definition_note": ex.get("definition_note", "")}
    c3 = c3_table(ev) if len(ev) else pd.DataFrame()
    allb = c3_block(c3)
    out["c3"] = {"n_rats": int(len(c3)), "all": allb, "uniformity": uniformity(allb),
                 "padding_rule_frac": {e: allb[e]["frac"]["median"] for e in EDGES},
                 "by_domain": {dom: c3_block(c3[c3.domain == dom]) if len(c3) else c3_block(c3) for dom in ("ir", "colour")},
                 "by_pile": {b: c3_block(c3[c3.pile_bin == b]) if len(c3) else c3_block(c3) for b in PILE_BINS},
                 "sizes": {"scratch": size_block(ev[(ev.arm == "SCRATCH")].box) if len(ev) else size_block([]),
                           "accepted_mask_bbox": size_block([m for m in ev[(ev.arm == "PRELABEL") & (ev.source == "cand")].prop])
                           if len(ev) else size_block([]),
                           "prelabel_final": size_block(ev[(ev.arm == "PRELABEL")].box) if len(ev) else size_block([])}}
    rp = repeat_pairs([ex] + list(more or []))
    out["repeat"] = {"n_pairs": len(rp), "n_frames": int(rp.frame_id.nunique()) if len(rp) else 0,
                     "iou_median": float(rp.iou.median()) if len(rp) else np.nan,
                     "iou_q25": float(rp.iou.quantile(0.25)) if len(rp) else np.nan, "iou_q75": float(rp.iou.quantile(0.75)) if len(rp) else np.nan,
                     "share_below_0_5": float((rp.iou < 0.5).mean()) if len(rp) else np.nan,
                     "by_arm": rp.groupby("arm").iou.agg(["size", "median"]).reset_index().to_dict("records") if len(rp) else []}
    out["_repeat_pairs"] = rp
    for dom in ("ir", "colour"):
        for b in PILE_BINS:
            d = ev[(ev.domain == dom) & (ev.pile_bin == b)] if len(ev) else ev
            row = {"domain": dom, "pile_bin": b, **pre_block(d), **{f"q_{k}": v for k, v in (quality_block(d) if len(d) else {}).items()}}
            for a in ("PRELABEL", "SCRATCH"):
                tb = time_block(a, lambda f, dom=dom, b=b: (f.domain == dom) & (f.pile_bin == b))
                row[f"{a}_s_per_rat"], row[f"{a}_rats"] = tb["s_per_rat"], tb["rats"]
            out["split"].append(row)
    return out


def summary_md(sm: dict, export_name: str) -> str:
    pa, tp, ts = sm["prelabel_all"], sm["time"]["PRELABEL"], sm["time"]["SCRATCH"]
    ratio = tp["s_per_rat"] / ts["s_per_rat"] if ts["s_per_rat"] and np.isfinite(ts["s_per_rat"]) else np.nan
    L = ["## B — pre-label edit pilot (dev)", "",
         f"Plan `{PLAN}`, part B; driver `cv/cv_field/inbox_prelabel_edit.py`; the user's export `{export_name}`.",
         "",
         "**Status: dev, descriptive only.** The 58 frames had all been seen before, so nothing here is a claim and the timing "
         "contrast is indicative only. The frozen test is part C.", "",
         "**Coverage of the export:**",
         f"- {sm['n_frames_completed']} frames completed of {sm['n_frames_visited']} opened;",
         f"- {sm['n_rats_evaluated']} rats with a final box;",
         f"- {sm['n_added']} rats added by the user (head hidden), {sm['n_deleted']} dots deleted (not a rat);",
         f"- {sm['n_unboxed']} rats without a box.", "",
         f"**PRELABEL** ({pa['n_rats']} rats):",
         f"- usable@1 {S.pct(pa['usable1'])}; usable@any {S.pct(pa['usable_any'])};",
         f"- merged {S.pct(pa['merged'])}, partial {S.pct(pa['partial'])}, manual box {S.pct(pa['manual'])};",
         f"- no candidate at the head {S.pct(pa['no_candidate'])};",
         f"- {S.f3(pa['edge_moves_per_rat'], 2)} edge moves and {S.f3(pa['next_per_rat'], 2)} 'next' presses per rat.", "",
         "**Seconds per rat** (completed frames):",
         f"- PRELABEL {S.f3(tp['s_per_rat'], 1)} s ({tp['rats']} rats on {tp['frames']} frames);",
         f"- SCRATCH {S.f3(ts['s_per_rat'], 1)} s ({ts['rats']} rats on {ts['frames']} frames);",
         f"- ratio PRELABEL / SCRATCH {S.f3(ratio, 2)}.", "",
         "By domain and the frame's largest pile size:", ""]
    qa = sm["quality_all"]
    qlines = ["**Quality from the user's own corrections** (plan amendment C2 item 1; PRELABEL rats with a proposed box, descriptive):",
              f"- {qa['n_with_proposal']} rats; IoU proposed → final: median {S.f3(qa['iou_median'], 3)} [quartiles {S.f3(qa['iou_q25'], 3)}, "
              f"{S.f3(qa['iou_q75'], 3)}];",
              f"- accepted with no edit {S.pct(qa['no_edit'])};",
              f"- fixed by edge moves only {S.pct(qa['edge_only'])} (median edge shift {S.f3(qa['edge_shift_median_px'], 1)} px);",
              f"- another candidate taken {S.pct(qa['other_candidate'])}; manual box {S.pct(qa['manual'])}.", ""]
    rows = []
    for r in sm["split"]:
        rows.append({"domain": r["domain"], "pile": r["pile_bin"], "PRELABEL rats": r["n_rats"], "usable@1": S.pct(r["usable1"]),
                     "usable@any": S.pct(r["usable_any"]), "merged": S.pct(r["merged"]), "partial": S.pct(r["partial"]),
                     "manual": S.pct(r["manual"]), "s / rat PRELABEL": S.f3(r["PRELABEL_s_per_rat"], 1),
                     "s / rat SCRATCH": S.f3(r["SCRATCH_s_per_rat"], 1)})
    L += [S.md_table(pd.DataFrame(rows)), ""] + qlines
    qrows = [{"domain": r["domain"], "pile": r["pile_bin"], "rats with a proposal": r.get("q_n_with_proposal", 0),
              "IoU median [q25, q75]": f"{S.f3(r.get('q_iou_median', np.nan), 3)} [{S.f3(r.get('q_iou_q25', np.nan), 3)}, {S.f3(r.get('q_iou_q75', np.nan), 3)}]",
              "no edit": S.pct(r.get("q_no_edit", np.nan)), "edge moves only": S.pct(r.get("q_edge_only", np.nan)),
              "median edge shift px": S.f3(r.get("q_edge_shift_median_px", np.nan), 1), "other candidate": S.pct(r.get("q_other_candidate", np.nan)),
              "manual": S.pct(r.get("q_manual", np.nan))} for r in sm["split"]]
    L += [S.md_table(pd.DataFrame(qrows)), ""]
    c3 = sm.get("c3")
    if c3:
        def cell(qq, pct_=False):
            if not qq["n"]:
                return "–"
            f = (lambda v: f"{100 * v:+.1f} %") if pct_ else (lambda v: f"{v:+.0f}")
            return f"{f(qq['median'])} [{f(qq['q25'])}, {f(qq['q75'])}]"
        L += [f"**Box convention (plan amendment C3).** PRELABEL rats whose first candidate was kept ({c3['n_rats']}). Each cell "
              "gives the signed shift of each edge from the SAM 3 mask bounding box to the user's final box, as median "
              "[q25, q75]; + = the final box is larger on that side.", ""]
        crow = []
        for name, blk in [("all", c3["all"])] + [(f"domain {k}", v) for k, v in c3["by_domain"].items()] + [(f"pile {k}", v) for k, v in c3["by_pile"].items()]:
            crow.append({"set": name, "n": blk["left"]["px"]["n"], **{f"{e} px": cell(blk[e]["px"]) for e in EDGES},
                         **{f"{e} fraction": cell(blk[e]["frac"], True) for e in EDGES}})
        L += [S.md_table(pd.DataFrame(crow)), ""]
        sz = c3["sizes"]

        def scell(qq, d=0):
            return "–" if not qq["n"] else f"{qq['median']:.{d}f} [{qq['q25']:.{d}f}, {qq['q75']:.{d}f}] (n {qq['n']})"
        L += ["Box sizes, median [q25, q75]:", "",
              S.md_table(pd.DataFrame([{"boxes": k, "width px": scell(v["width_px"]), "height px": scell(v["height_px"]),
                                        "aspect w / h": scell(v["aspect_w_over_h"], 2)}
                                       for k, v in (("SCRATCH (drawn by hand)", sz["scratch"]),
                                                    ("accepted mask bboxes (PRELABEL)", sz["accepted_mask_bbox"]),
                                                    ("PRELABEL final boxes", sz["prelabel_final"]))])), ""]
        pr, un = c3["padding_rule_frac"], c3["uniformity"]
        L += ["**Proposed padding rule** (a proposal only; it is frozen later, with the user, before any C frame): pad each "
              "SAM 3 box by the per-edge median fraction:",
              "- " + ", ".join(f"{e} {100 * pr[e]:+.1f} %" if np.isfinite(pr[e]) else f"{e} –" for e in EDGES) + ".",
              "- Uniformity: "
              + ("not computable (no kept first candidates)." if un["uniform"] is None else
                 ("**uniform** (no edge with IQR > |median|; no single edge much worse)." if un["uniform"] else
                  "**NOT uniform**: "
                  + "; ".join(([f"IQR > |median| on {', '.join(un['spread_edges'])}"] if un["spread_flag"] else [])
                              + ([f"the {un['worst_edge']} edge is {un['worst_over_others']:.1f}× the other edges' median shift"]
                                 if un["one_edge_flag"] else []))
                 + ". Per amendment C3 item 3, a uniform padding would then not be used and the fix stays manual (the decision "
                   "is the user's at the freeze).")), ""]
    rp = sm["repeat"]
    if rp["n_pairs"]:
        L += [f"**Repeat check** (frames labelled twice; rats matched by head point within 15 px): {rp['n_pairs']} rat pairs on "
              f"{rp['n_frames']} frames. IoU of the two final boxes: median {S.f3(rp['iou_median'], 3)} [quartiles "
              f"{S.f3(rp['iou_q25'], 3)}, {S.f3(rp['iou_q75'], 3)}], {S.pct(rp['share_below_0_5'])} below 0.5.", ""]
    else:
        L += ["**Repeat check:** no frame was labelled twice.", ""]
    sa = sm["showall"]
    L += [f"**'Show all' view** (descriptive; time kept apart from the edit time): used on {sa['frames_used']} frames for "
          f"{S.f3(sa['showall_s'], 0)} s. The user marked {sa['garbage']} masks as garbage and {sa['fragment']} as fragment.", ""]
    if sm.get("definition_note"):
        L += [f"**The user's definition changes:** {sm['definition_note']}", ""]
    L += ["**Definitions (B):**", "",
          "- **Evaluated rat:** a dot not deleted, with a final box.",
          "- **usable@1** $=\\frac{1}{N}\\sum_r \\mathbb 1[\\text{rank}_r=1 \\wedge \\neg\\text{merged}_{r,1} \\wedge \\neg\\text{partial}_{r,1}]$:",
          "  - over the PRELABEL rats;",
          "  - the share whose first candidate was accepted with no flag.",
          "- **usable@any** $=\\frac{1}{N}\\sum_r \\mathbb 1[\\text{source}_r=\\text{cand} \\wedge \\neg\\text{flags on the accepted candidate}]$:",
          "  - the share for which some offered candidate was accepted without a flag;",
          "  - a rat with no candidate counts as not usable.",
          "- **merged / partial rate:** the share of PRELABEL rats with ≥ 1 offered candidate flagged merged / partial.",
          "- **manual-box rate:** the share of PRELABEL rats whose final box was drawn by hand.",
          "- **Proposed box** = the bounding box of the first offered candidate (full-resolution px); **final box** = the "
          "user's box.",
          "- **IoU proposed → final** $=|P\\cap F|/|P\\cup F|$ of the two boxes (0–1; 1 = unchanged).",
          "- **No edit** = the first candidate accepted with no edge move. **Edge moves only** = the first candidate accepted, "
          "then ≥ 1 edge move; **edge shift** = the mean over the four edges of |final − proposed| px, median over rats.",
          "- **Edge shift (C3)** for a kept first candidate with mask bbox $(x_0,y_0,x_1,y_1)$ and final box $(X_0,Y_0,X_1,Y_1)$: "
          "left $=x_0-X_0$, right $=X_1-x_1$, top $=y_0-Y_0$, bottom $=Y_1-y_1$ (px; + = the final box is larger on that side); "
          "fraction = shift / mask-bbox width (left, right) or height (top, bottom).",
          "- **Uniformity flag (C3, the agent's proposal):**",
          "  - spread = an edge whose IQR of the fraction exceeds |its median|;",
          f"  - one edge much worse = the largest |median| is ≥ {ONE_EDGE_RATIO:g}× the median |median| of the other three "
          f"edges and ≥ {ONE_EDGE_MIN:g};",
          "  - uniform = neither holds.",
          "- **Main pass** = a frame's first completed pass. Later passes ('redo this frame', or another labelling session) "
          "enter only the **repeat check**: rats paired by head point (nearest within 15 px), IoU of the two final boxes.",
          "- **Seconds per rat** $=\\sum_f t_f / \\sum_f n_f$ over the completed frames of an arm:",
          "  - $t_f$ = active seconds (the clock pauses when the tab is hidden or after 45 s without input; 'show all' time is "
          "excluded);",
          "  - $n_f$ = evaluated rats on frame $f$.", ""]
    return "\n".join(L)


def write_summary(run: Path, export: Path, regenerate_report: bool = True, more: list | None = None) -> Path:
    """v1 export -> <run>/prelabel_edit/summary_B.*; v2 export (amendments B1 / B1a) -> <run>/prelabel_edit_v2/summary_B.*.
    The SAM 3 report includes the v2 section when it exists, else the v1 one."""
    exs = []
    for e in [export] + list(more or []):
        exs.append(json.loads(Path(e).read_text(encoding="utf-8")))
    ver = exs[0].get("page_version")
    if ver not in (PAGE_VERSION, PAGE_VERSION_V2) or any(x.get("page_version") != ver for x in exs):
        raise SystemExit(f"not exports of one page version: {[x.get('page_version') for x in exs]}")
    meta = {"export": Path(export).as_posix(), "more_exports": [Path(m).as_posix() for m in (more or [])], "made": datetime.now().isoformat(timespec="seconds")}
    if ver == PAGE_VERSION_V2:
        d = run / "prelabel_edit_v2"
        d.mkdir(parents=True, exist_ok=True)
        sm = summarize_v2(exs[0], exs[1:])
        out = d / "summary_B.md"
        out.write_text(summary_md_v2(sm, Path(export).as_posix()), encoding="utf-8")
        S.write_json(d / "summary_B.json", {**sm, **meta})
    else:
        sm = summarize(exs[0], exs[1:])
        rp = sm.pop("_repeat_pairs")
        if len(rp):
            rp.to_csv(run / "prelabel_edit" / "summary_B_repeat_pairs.csv", index=False)
        out = run / "prelabel_edit" / "summary_B.md"
        out.write_text(summary_md(sm, Path(export).as_posix()), encoding="utf-8")
        S.write_json(run / "prelabel_edit" / "summary_B.json", {**sm, **meta})
    if regenerate_report:
        S.write_report(run)
    return out


# ============================================================================================ v2: implant box + rat box (amendments B1 / B1a)
PAGE_VERSION_V2 = "inbox_sam3_prelabel_edit_2026c_v2"
OBJS = ("implant", "rat")
DEFINITIONS_V2 = [
    ("Head point", "your click on the head; kept as the keypoint."),
    ("Implant box", "the implant only (the IR identity marks are on it). If the implant is not visible: H = implant hidden, no box."),
    ("Rat box", "head + body, without the tail; visible parts only, occluded parts are not inferred."),
    ("Usable mask", "for the rat box: covers the visible head + body of exactly ONE rat and no part of another rat; for the implant "
                    "box: covers this rat's implant only. The box may still need small edge moves."),
    ("Merged / partial (rat box only)", "merged = covers parts of ≥ 2 rats; partial = clearly misses a large part of the rat's visible "
                                         "head + body."),
    ("Garbage / fragment", "only in the optional 'show all' view: on no rat / on part of a rat but not offered for it."),
]

PAGE_JS_V2 = r"""
(function(){
const D = window.PL_DATA, KEY = D.page_version + '::' + D.run;
const $ = id => document.getElementById(id);
const iso = () => new Date().toISOString();
const OBJ_NAME = {implant: 'IMPLANT box', rat: 'RAT box'};
function newObj(f, cand, hidden){ return {cand: cand, k: 0, prop: cand.length ? f.masks[cand[0]].b.slice() : null, box: null, source: null, rank: null,
  mask: null, cand_flags: {}, edge_moves: 0, next_presses: 0, time_ms: 0, hidden: !!hidden, click: null, clicks: []}; }
function initFrame(f){ return {arm: f.arm, active_ms: 0, showall_ms: 0, completed: false, visited: false, next_add: 1, marks: {}, passes: [],
  rats: f.heads.map((h, i) => ({id: 'h' + (i + 1), num: i + 1, origin: 'click', click_id: h.c, u: h.u, v: h.v, deleted: false,
    implant: newObj(f, f.cand[i], false), rat: newObj(f, [], false)}))}; }
function fresh(){ const fr = {}; D.frames.forEach(f => fr[f.id] = initFrame(f));
  return {v: 2, started_at: iso(), defnote: '', cur: {fi: 0, ri: 0, obj: 'implant'}, frames: fr, events: []}; }
function load(){ try { const t = localStorage.getItem(KEY); if (t) { const o = JSON.parse(t); if (o && o.frames && o.v === 2) return o; } } catch (e) {} return null; }
let saveT = null;
function save(now){ const f = () => { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { $('banner').textContent = 'could not save to this browser: export now'; } };
  if (now) { f(); return; } clearTimeout(saveT); saveT = setTimeout(f, 250); }
let S = load() || fresh();
const fr = () => D.frames[S.cur.fi], st = () => S.frames[fr().id], rats = () => st().rats;
const liveIdx = () => rats().map((r, i) => i).filter(i => !rats()[i].deleted);
const rat = () => rats()[S.cur.ri];
const obj = () => { const r = rat(); return r ? r[S.cur.obj] : null; };
function log(ev, extra){ const r = rat(); S.events.push(Object.assign({t: iso(), frame: fr().id, arm: st().arm, rat: r ? r.id : null, obj: S.cur.obj, ev: ev}, extra || {})); save(); }
// ---------------------------------------------------------------- undo (per frame, in memory)
const undo = {};
function snap(){ const id = fr().id; (undo[id] = undo[id] || []).push(JSON.stringify({rats: st().rats, marks: st().marks, next_add: st().next_add, ri: S.cur.ri, obj: S.cur.obj}));
  if (undo[id].length > 200) undo[id].shift(); }
function doUndo(){ const a = undo[fr().id]; if (!a || !a.length) return; const o = JSON.parse(a.pop());
  st().rats = o.rats; st().marks = o.marks; st().next_add = o.next_add; S.cur.ri = Math.min(o.ri, st().rats.length - 1); S.cur.obj = o.obj; log('undo'); draw(); }
// ---------------------------------------------------------------- geometry
function pointInPoly(x, y, p){ let ins = false; for (let i = 0, j = p.length - 2; i < p.length; j = i, i += 2) {
  const xi = p[i], yi = p[i + 1], xj = p[j], yj = p[j + 1];
  if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) ins = !ins; } return ins; }
function segDist(x, y, x1, y1, x2, y2){ const dx = x2 - x1, dy = y2 - y1, L = dx * dx + dy * dy; let t = L ? ((x - x1) * dx + (y - y1) * dy) / L : 0;
  t = Math.max(0, Math.min(1, t)); return Math.hypot(x - x1 - t * dx, y - y1 - t * dy); }
function polyDist(x, y, p){ let d = Infinity; for (let i = 0, j = p.length - 2; i < p.length; j = i, i += 2) d = Math.min(d, segDist(x, y, p[j], p[j + 1], p[i], p[i + 1])); return d; }
function maskHit(m, x, y, tol){ for (const p of m.p) { if (pointInPoly(x, y, p)) return true; } if (tol > 0) { for (const p of m.p) if (polyDist(x, y, p) <= tol) return true; } return false; }
function candidatesAt(x, y){ const out = []; fr().masks.forEach((m, j) => { if (maskHit(m, x, y, D.cover_px)) out.push(j); }); return out; }
// ---------------------------------------------------------------- view
const cv = $('cv'), ctx = cv.getContext('2d');
let view = null, mode = null, drag = null, spaceDown = false, showAll = false;
const imgs = {};
function img(){ const f = fr(); if (!imgs[f.img]) { const im = new Image(); im.onload = () => draw(); im.src = f.img; imgs[f.img] = im; } return imgs[f.img]; }
function fit(){ const w = cv.clientWidth, h = cv.clientHeight, f = fr(); const s = Math.min(w / f.w, h / f.h); view = {s, ox: (w - f.w * s) / 2, oy: (h - f.h * s) / 2}; }
const toImg = (x, y) => [(x - view.ox) / view.s, (y - view.oy) / view.s];
const toCv = (u, v) => [u * view.s + view.ox, v * view.s + view.oy];
function polyPath(p){ const P = new Path2D(); for (let i = 0; i < p.length; i += 2) { if (i === 0) P.moveTo(p[i], p[i + 1]); else P.lineTo(p[i], p[i + 1]); } P.closePath(); return P; }
function colour(r){ return 'hsl(' + ((r * 137.508) % 360).toFixed(1) + ',90%,58%)'; }
const STYLE = {implant: {box: '#ff9f1a', cand: '#00e5ff'}, rat: {box: '#39ff14', cand: '#ff4fd8'}};
let drawnMasks = 0;
function curCand(){ const r = rat(), o = obj(); if (!r || r.deleted || st().arm !== 'PRELABEL' || showAll || !o) return null;
  if (S.cur.obj === 'implant' && o.hidden) return null; return o.k < o.cand.length ? o.cand[o.k] : null; }
function draw(){
  const f = fr(), s = st(); if (!f) return;
  if (cv.width !== cv.clientWidth) cv.width = cv.clientWidth; if (cv.height !== cv.clientHeight) cv.height = cv.clientHeight;
  if (!view) fit();
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = '#111'; ctx.fillRect(0, 0, cv.width, cv.height);
  ctx.setTransform(view.s, 0, 0, view.s, view.ox, view.oy);
  const im = img(); if (im.complete && im.naturalWidth) ctx.drawImage(im, 0, 0, f.w, f.h);
  const lw = 1 / view.s; drawnMasks = 0;
  if (showAll) {
    f.masks.forEach((m, j) => { const mk = s.marks[j]; const col = mk === 'garbage' ? '#ff3b3b' : mk === 'fragment' ? '#ffa500' : colour(j);
      m.p.forEach(p => { const P = polyPath(p); if (mk) { ctx.globalAlpha = 0.35; ctx.fillStyle = col; ctx.fill(P); ctx.globalAlpha = 1; }
        ctx.lineWidth = 1.5 * lw; ctx.strokeStyle = col; ctx.stroke(P); }); drawnMasks++; });
  } else {
    const c = curCand();
    if (c !== null) { const m = f.masks[c], col = STYLE[S.cur.obj].cand; m.p.forEach(p => { const P = polyPath(p); ctx.globalAlpha = 0.18; ctx.fillStyle = col; ctx.fill(P);
      ctx.globalAlpha = 1; ctx.lineWidth = 2.5 * lw; ctx.strokeStyle = col; ctx.stroke(P); }); drawnMasks = 1;
      ctx.setLineDash([8 * lw, 6 * lw]); ctx.lineWidth = 2 * lw; ctx.strokeStyle = '#ffd400'; ctx.strokeRect(m.b[0], m.b[1], m.b[2] - m.b[0], m.b[3] - m.b[1]); ctx.setLineDash([]); }
  }
  s.rats.forEach((r, i) => { if (r.deleted) return; const cur = i === S.cur.ri;
    ['rat', 'implant'].forEach(k => { const b = r[k].box; if (!b) return; const act = cur && S.cur.obj === k;
      ctx.globalAlpha = cur ? 1 : 0.4; ctx.lineWidth = (act ? 3 : cur ? 1.8 : 1.3) * lw; ctx.strokeStyle = STYLE[k].box;
      if (k === 'implant') ctx.setLineDash([4 * lw, 3 * lw]); ctx.strokeRect(b[0], b[1], b[2] - b[0], b[3] - b[1]); ctx.setLineDash([]); ctx.globalAlpha = 1; });
    const cl = r.rat.click; if (cur && cl) { const R = 8 * lw; ctx.lineWidth = 2.5 * lw; ctx.strokeStyle = STYLE.rat.cand; ctx.beginPath();
      ctx.moveTo(cl[0] - R, cl[1]); ctx.lineTo(cl[0] + R, cl[1]); ctx.moveTo(cl[0], cl[1] - R); ctx.lineTo(cl[0], cl[1] + R); ctx.stroke(); } });
  if (drag && drag.kind === 'draw' && drag.cur) { const b = normBox(drag.start, drag.cur); ctx.setLineDash([6 * lw, 4 * lw]); ctx.lineWidth = 2 * lw; ctx.strokeStyle = STYLE[S.cur.obj].box;
    ctx.strokeRect(b[0], b[1], b[2] - b[0], b[3] - b[1]); ctx.setLineDash([]); }
  ctx.font = (16 * lw) + 'px system-ui, sans-serif';
  s.rats.forEach((r, i) => { const cur = i === S.cur.ri, R = (cur ? 9 : 7) * lw;
    ctx.beginPath(); if (r.origin === 'added') { ctx.moveTo(r.u, r.v - R); ctx.lineTo(r.u + R, r.v); ctx.lineTo(r.u, r.v + R); ctx.lineTo(r.u - R, r.v); ctx.closePath(); }
    else ctx.arc(r.u, r.v, R, 0, 2 * Math.PI);
    ctx.fillStyle = r.deleted ? '#777' : '#fff'; ctx.fill(); ctx.lineWidth = (cur ? 3 : 2) * lw; ctx.strokeStyle = cur ? '#ff2fd0' : '#000'; ctx.stroke();
    if (r.deleted) { ctx.strokeStyle = '#ff3b3b'; ctx.beginPath(); ctx.moveTo(r.u - R, r.v - R); ctx.lineTo(r.u + R, r.v + R); ctx.moveTo(r.u + R, r.v - R); ctx.lineTo(r.u - R, r.v + R); ctx.stroke(); }
    ctx.lineWidth = 3 * lw; ctx.strokeStyle = '#000'; ctx.strokeText(String(r.num), r.u + R + 3 * lw, r.v - R); ctx.fillStyle = cur ? '#ff2fd0' : '#fff'; ctx.fillText(String(r.num), r.u + R + 3 * lw, r.v - R); });
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  panel();
}
function objText(r, k){ const o = r[k], pre = st().arm === 'PRELABEL';
  if (k === 'implant' && o.hidden) return 'implant hidden';
  let t = '';
  if (pre) { if (k === 'rat' && !o.click) t = 'click the rat\'s body'; else if (o.cand.length === 0) t = 'no candidate — draw (B)';
    else t = o.k < o.cand.length ? 'candidate ' + (o.k + 1) + ' / ' + o.cand.length : 'none usable — draw (B)'; }
  else t = 'draw by hand (drag)';
  if (o.box) t += ' · box: ' + (o.source === 'manual' ? 'manual' : 'candidate ' + o.rank) + (o.edge_moves ? ', ' + o.edge_moves + ' edge move(s)' : '');
  if (k === 'rat' && pre && o.k < o.cand.length) { const fl = o.cand_flags[o.k + 1] || {}; if (fl.merged || fl.partial) t += ' · flagged ' + [fl.merged ? 'merged' : '', fl.partial ? 'partial' : ''].filter(Boolean).join(' + '); }
  return t; }
function panel(){
  const f = fr(), s = st(), r = rat();
  $('armtag').textContent = s.arm; $('armtag').className = s.arm; if ($('goto').value !== String(S.cur.fi)) $('goto').value = String(S.cur.fi);
  $('objtag').textContent = OBJ_NAME[S.cur.obj]; $('objtag').className = 'obj-' + S.cur.obj;
  $('ftitle').textContent = 'frame ' + (S.cur.fi + 1) + ' / ' + D.frames.length + ' · ' + (f.domain === 'ir' ? 'IR' : 'colour') + ' · ' + f.id + ((s.passes || []).length ? ' · pass ' + (s.passes.length + 1) : '');
  const live = liveIdx();
  $('status').innerHTML = r ? ('rat ' + r.num + (r.origin === 'added' ? ' (added)' : '') + ' · ' + (live.indexOf(S.cur.ri) + 1) + ' of ' + live.length + (r.deleted ? ' · deleted' : '')
    + '<br><span class="obj-implant">IMPLANT</span> ' + objText(r, 'implant') + '<br><span class="obj-rat">RAT</span> ' + objText(r, 'rat')) : 'no rat on this frame';
  $('banner').textContent = showAll ? 'SHOW ALL: every "rat" mask; click a mask: garbage → fragment → clear. Press S to go back. (显示全部)' : mode === 'draw' ? 'draw the ' + OBJ_NAME[S.cur.obj] + ': drag on the image (画框)' : mode === 'add' ? 'add a rat: click its visible body (加鼠)' : '';
  const done = D.frames.filter(x => S.frames[x.id].completed).length; let nr = 0, nb = 0;
  D.frames.forEach(x => S.frames[x.id].rats.forEach(q => { if (!q.deleted) { nr++; if (q.rat.box && (q.implant.box || q.implant.hidden)) nb++; } }));
  $('progbar').style.width = (100 * done / D.frames.length).toFixed(1) + '%';
  $('progtxt').textContent = done + ' / ' + D.frames.length + ' frames done · ' + nb + ' / ' + nr + ' rats with both boxes';
  $('timetxt').textContent = 'active ' + (s.active_ms / 1000).toFixed(0) + ' s' + (s.showall_ms ? ' · show-all ' + (s.showall_ms / 1000).toFixed(0) + ' s' : '') + (idle() ? ' · paused' : '');
}
function normBox(a, b){ return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])]; }
// ---------------------------------------------------------------- actions
function startObj(r){ return r && r.implant.hidden ? 'rat' : 'implant'; }
function goFrame(i){ S.cur.fi = Math.max(0, Math.min(D.frames.length - 1, i)); const live = liveIdx(); S.cur.ri = live.length ? live[0] : 0; S.cur.obj = startObj(rat());
  st().visited = true; view = null; mode = null; showAll = false; $('showall').checked = false; log('frame_open'); draw(); }
function nextRat(){ const live = liveIdx(), p = live.indexOf(S.cur.ri);
  let nx = p >= 0 ? (p < live.length - 1 ? live[p + 1] : undefined) : live.find(i => i > S.cur.ri);
  if (nx !== undefined) { S.cur.ri = nx; S.cur.obj = startObj(rat()); mode = null; log('rat_next'); draw(); return; }
  st().completed = true; log('frame_done'); if (S.cur.fi < D.frames.length - 1) goFrame(S.cur.fi + 1); else { draw(); $('banner').textContent = 'last frame done — please export'; } }
function advance(){ if (S.cur.obj === 'implant') { S.cur.obj = 'rat'; mode = null; log('obj_next'); draw(); } else nextRat(); }
function back(){ if (S.cur.obj === 'rat' && rat() && !rat().implant.hidden) { S.cur.obj = 'implant'; mode = null; draw(); return; }
  const live = liveIdx(), p = live.indexOf(S.cur.ri); if (p > 0) { S.cur.ri = live[p - 1]; S.cur.obj = 'rat'; mode = null; draw(); } else if (S.cur.fi > 0) goFrame(S.cur.fi - 1); }
function accept(){ const o = obj(), c = curCand(); if (!o || c === null) return; snap(); const m = fr().masks[c];
  o.box = m.b.slice(); o.source = 'cand'; o.rank = o.k + 1; o.mask = c;
  log('accept', {rank: o.rank, mask: c, mask_score: m.s, box: o.box, flags: o.cand_flags[o.rank] || {}, click: S.cur.obj === 'rat' ? o.click : undefined}); draw(); }
function next(){ const o = obj(), r = rat(); if (!o || !r || r.deleted || st().arm !== 'PRELABEL' || showAll) return; if (S.cur.obj === 'implant' && o.hidden) return;
  if (S.cur.obj === 'rat' && !o.click) return; snap(); o.k = o.k < o.cand.length ? o.k + 1 : 0; o.next_presses++;
  log('next', {to: o.k < o.cand.length ? o.k + 1 : 'none'}); draw(); }
function flag(kind){ if (S.cur.obj !== 'rat') return; const o = obj(); if (curCand() === null) return; snap(); const fl = o.cand_flags[o.k + 1] = o.cand_flags[o.k + 1] || {}; fl[kind] = !fl[kind];
  log('flag', {rank: o.k + 1, flag: kind, value: fl[kind]}); draw(); }
function setManual(b){ const r = rat(), o = obj(); if (!r || r.deleted || !o) return; snap(); o.box = b.map(x => Math.round(x * 10) / 10); o.source = 'manual'; o.rank = null; o.mask = null;
  if (S.cur.obj === 'implant') o.hidden = false; log('manual_box', {box: o.box}); mode = null; draw(); }
function fitToMask(){ const r = rat(), o = obj(); if (!r || r.deleted || !o || o.mask === null || o.source !== 'cand') return; const b = fr().masks[o.mask].b;
  if (o.box && o.box.every((x, i) => x === b[i])) return; snap(); const from = o.box; o.box = b.slice(); log('fit_to_mask', {from: from, to: o.box, rank: o.rank}); draw(); }
function hideImplant(){ const r = rat(); if (!r || r.deleted) return; snap(); const o = r.implant; o.hidden = !o.hidden;
  if (o.hidden) { o.box = null; o.source = null; o.rank = null; o.mask = null; if (S.cur.obj === 'implant') S.cur.obj = 'rat'; }
  log('implant_hidden', {value: o.hidden}); draw(); }
function bodyClick(u, v){ const r = rat(); if (!r || r.deleted) return; snap(); const o = r.rat, f = fr(); o.click = [Math.round(u * 10) / 10, Math.round(v * 10) / 10];
  o.clicks.push(o.click.slice()); o.cand = candidatesAt(u, v); o.k = 0; o.prop = o.cand.length ? f.masks[o.cand[0]].b.slice() : null;
  log('body_click', {u: o.click[0], v: o.click[1], n_cand: o.cand.length}); draw(); }
function addRat(u, v){ snap(); const s = st(), f = fr(); const r = {id: 'a' + s.next_add, num: s.rats.length + 1, origin: 'added', click_id: null,
  u: Math.round(u * 10) / 10, v: Math.round(v * 10) / 10, deleted: false, implant: newObj(f, [], true), rat: newObj(f, [], false)};
  if (s.arm === 'PRELABEL') { r.rat.click = [r.u, r.v]; r.rat.clicks = [[r.u, r.v]]; r.rat.cand = candidatesAt(u, v); r.rat.prop = r.rat.cand.length ? f.masks[r.rat.cand[0]].b.slice() : null; }
  s.next_add++; s.rats.push(r); S.cur.ri = s.rats.length - 1; S.cur.obj = 'rat'; mode = null; log('add_rat', {u: r.u, v: r.v, n_cand: r.rat.cand.length}); draw(); }
function delDot(){ const r = rat(); if (!r) return; snap(); r.deleted = !r.deleted; log(r.deleted ? 'delete_dot' : 'undelete_dot'); draw(); }
function redoFrame(skipConfirm){ const f = fr(), s = st();
  if (!skipConfirm && !confirm('Label this frame again from the start? The current labels are kept as pass ' + ((s.passes || []).length + 1) + '.')) return;
  s.passes = (s.passes || []).concat([{rats: s.rats, active_ms: s.active_ms, showall_ms: s.showall_ms, completed: s.completed, marks: s.marks, archived_at: iso()}]);
  const nf = initFrame(f); s.rats = nf.rats; s.active_ms = 0; s.showall_ms = 0; s.completed = false; s.marks = {}; s.next_add = 1; undo[f.id] = [];
  S.cur.ri = 0; S.cur.obj = startObj(rat()); log('redo_frame', {pass: s.passes.length + 1}); draw(); }
function toggleShowAll(on){ showAll = on === undefined ? !showAll : on; $('showall').checked = showAll; mode = null; log('show_all', {on: showAll}); draw(); }
function markMask(u, v){ const f = fr(), s = st(); let best = -1, ba = Infinity;
  f.masks.forEach((m, j) => { if (maskHit(m, u, v, 0) && m.a < ba) { best = j; ba = m.a; } }); if (best < 0) return; snap();
  const cur = s.marks[best], nx = !cur ? 'garbage' : cur === 'garbage' ? 'fragment' : null; if (nx) s.marks[best] = nx; else delete s.marks[best];
  log('showall_mark', {mask: best, mark: nx || 'clear'}); draw(); }
// ---------------------------------------------------------------- timing (frame clock + per-object time slices)
let lastInput = performance.now(), lastTick = performance.now();
const idle = () => document.visibilityState !== 'visible' || performance.now() - lastInput > D.idle_ms;
function touch(){ lastInput = performance.now(); }
setInterval(() => { const now = performance.now(), dt = now - lastTick; lastTick = now;
  if (!idle() && dt < 5000) { const s = st(); if (showAll) s.showall_ms += dt; else { s.active_ms += dt; const r = rat(); if (r && !r.deleted) r[S.cur.obj].time_ms += dt; } }
  panel(); if (Math.random() < 0.1) save(); }, 500);
document.addEventListener('visibilitychange', () => { log('visibility', {state: document.visibilityState}); save(true); });
window.addEventListener('beforeunload', () => save(true));
// ---------------------------------------------------------------- mouse
function edgeAt(x, y){ const o = obj(), r = rat(); if (!r || !o || !o.box || r.deleted || showAll) return null; const b = o.box, [u, v] = toImg(x, y), t = 8 / view.s;
  const inY = v > b[1] - t && v < b[3] + t, inX = u > b[0] - t && u < b[2] + t, e = [];
  if (inY && Math.abs(u - b[0]) < t) e.push(0); if (inY && Math.abs(u - b[2]) < t) e.push(2); if (inX && Math.abs(v - b[1]) < t) e.push(1); if (inX && Math.abs(v - b[3]) < t) e.push(3);
  return e.length ? e : null; }
function canDraw(){ const r = rat(); if (!r || r.deleted) return false; if (mode === 'draw') return true;
  return st().arm === 'SCRATCH' && !(S.cur.obj === 'implant' && r.implant.hidden); }
cv.addEventListener('contextmenu', e => e.preventDefault());
cv.addEventListener('mousedown', e => { touch(); const r0 = cv.getBoundingClientRect(), x = e.clientX - r0.left, y = e.clientY - r0.top, [u, v] = toImg(x, y);
  if (e.button === 2 || e.button === 1 || spaceDown) { drag = {kind: 'pan', x0: e.clientX, y0: e.clientY, ox: view.ox, oy: view.oy}; return; }
  if (showAll) { markMask(u, v); return; }
  if (mode === 'add') { addRat(u, v); return; }
  const ed = edgeAt(x, y); if (ed) { drag = {kind: 'edge', edges: ed, b0: obj().box.slice()}; return; }
  if (canDraw()) { drag = {kind: 'draw', start: [u, v], cur: null}; return; }
  drag = {kind: 'press', x0: e.clientX, y0: e.clientY, ox: view.ox, oy: view.oy, u: u, v: v, moved: false}; });
window.addEventListener('mousemove', e => { if (e.target === cv) touch(); const r0 = cv.getBoundingClientRect(), x = e.clientX - r0.left, y = e.clientY - r0.top;
  if (!drag) { cv.style.cursor = showAll ? 'pointer' : edgeAt(x, y) ? 'move' : (canDraw() || mode === 'add' || (S.cur.obj === 'rat' && st().arm === 'PRELABEL')) ? 'crosshair' : 'grab'; return; }
  if (drag.kind === 'press') { if (Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) > 4) drag.moved = true; if (drag.moved) { view.ox = drag.ox + e.clientX - drag.x0; view.oy = drag.oy + e.clientY - drag.y0; draw(); } return; }
  if (drag.kind === 'pan') { view.ox = drag.ox + e.clientX - drag.x0; view.oy = drag.oy + e.clientY - drag.y0; draw(); return; }
  const [u, v] = toImg(x, y);
  if (drag.kind === 'draw') { drag.cur = [u, v]; draw(); return; }
  if (drag.kind === 'edge') { const b = obj().box; drag.edges.forEach(k => { b[k] = (k % 2 === 0) ? u : v; }); draw(); } });
window.addEventListener('mouseup', e => { if (!drag) return; const d = drag; drag = null;
  if (d.kind === 'press') { if (!d.moved && st().arm === 'PRELABEL' && S.cur.obj === 'rat') bodyClick(d.u, d.v); return; }
  if (d.kind === 'draw') { if (d.cur) { const b = normBox(d.start, d.cur); if (b[2] - b[0] >= 5 && b[3] - b[1] >= 5) { setManual(b); return; } } draw(); return; }
  if (d.kind === 'edge') { const o = obj(), b = normBox([o.box[0], o.box[1]], [o.box[2], o.box[3]]); const moved = b.some((x, i) => Math.abs(x - d.b0[i]) > 0.5);
    if (moved) { const nb = b.map(x => Math.round(x * 10) / 10); o.box = d.b0; snap(); o.box = nb; o.edge_moves++; log('edge_move', {from: d.b0, to: nb, edges: d.edges}); } else o.box = d.b0; draw(); } });
cv.addEventListener('wheel', e => { e.preventDefault(); touch(); const r0 = cv.getBoundingClientRect(), mx = e.clientX - r0.left, my = e.clientY - r0.top;
  const z = Math.exp(-e.deltaY * 0.0015), s2 = Math.min(Math.max(view.s * z, 0.05), 20);
  view.ox = mx - (mx - view.ox) * s2 / view.s; view.oy = my - (my - view.oy) * s2 / view.s; view.s = s2; draw(); }, {passive: false});
window.addEventListener('resize', () => { view = null; draw(); });
// ---------------------------------------------------------------- keys
document.addEventListener('keyup', e => { if (e.key === ' ') spaceDown = false; });
document.addEventListener('keydown', e => { touch(); const tg = e.target.tagName; if (tg === 'TEXTAREA' || tg === 'SELECT' || (tg === 'INPUT' && e.target.type === 'text')) return;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (k === ' ') { spaceDown = true; e.preventDefault(); return; }
  if (k === 's') { toggleShowAll(); return; } if (k === 'z') { view = null; draw(); return; } if (k === 'u') { doUndo(); return; }
  if (k === 'PageDown') { goFrame(S.cur.fi + 1); e.preventDefault(); return; } if (k === 'PageUp') { goFrame(S.cur.fi - 1); e.preventDefault(); return; }
  if (showAll) return;
  if (k === 'Enter' || k === 'ArrowRight') { advance(); e.preventDefault(); return; } if (k === 'ArrowLeft') { back(); e.preventDefault(); return; }
  if (k === 'Tab') { const r = rat(); S.cur.obj = (S.cur.obj === 'implant' || (r && r.implant.hidden)) ? 'rat' : 'implant'; mode = null; draw(); e.preventDefault(); return; }
  if (k === 'Escape') { mode = null; draw(); return; }
  const pre = st().arm === 'PRELABEL';
  if (k === 'a' && pre) accept(); else if (k === 'n' && pre) next(); else if (k === 'm' && pre) flag('merged'); else if (k === 'p' && pre) flag('partial');
  else if (k === 'h') hideImplant();
  else if (k === 'b') { if (S.cur.obj === 'implant' && rat() && rat().implant.hidden) rat().implant.hidden = false; mode = mode === 'draw' ? null : 'draw'; log('draw_mode', {on: mode === 'draw'}); draw(); }
  else if (k === 'r') { mode = mode === 'add' ? null : 'add'; log('add_mode', {on: mode === 'add'}); draw(); }
  else if (k === 'x') delDot();
  else if (k === 'f') fitToMask(); });
// ---------------------------------------------------------------- export / import
function objOut(f, o){ return Object.assign({}, o, {mask_cache_index: o.mask === null ? null : f.masks[o.mask].i, mask_score: o.mask === null ? null : f.masks[o.mask].s,
  cand_cache_index: o.cand.map(j => f.masks[j].i), cand_scores: o.cand.map(j => f.masks[j].s)}); }
function ratOut(f, r){ return Object.assign({}, r, {implant: objOut(f, r.implant), rat: objOut(f, r.rat)}); }
function marksOut(f, mk){ return Object.entries(mk || {}).map(([j, m]) => ({mask: +j, mask_cache_index: f.masks[+j].i, mask_score: f.masks[+j].s, mark: m})); }
function exportJSON(){ return {page_version: D.page_version, run: D.run, plan: D.plan, seed: D.seed, exported_at: iso(), started_at: S.started_at,
  definitions: D.definitions, definition_note: S.defnote, idle_ms: D.idle_ms, objects: ['implant', 'rat'],
  coords: 'full-resolution pixels, origin top-left; box = [x0, y0, x1, y1]',
  frames: D.frames.map(f => { const s = S.frames[f.id]; return {frame_id: f.id, domain: f.domain, arm: s.arm, pile_bin: f.pile_bin, order: f.order,
    active_s: +(s.active_ms / 1000).toFixed(3), showall_s: +(s.showall_ms / 1000).toFixed(3), visited: s.visited, completed: s.completed,
    rats: s.rats.map(r => ratOut(f, r)), showall_marks: marksOut(f, s.marks),
    passes: (s.passes || []).map((ps, i) => ({pass: i + 1, active_s: +(ps.active_ms / 1000).toFixed(3), showall_s: +(ps.showall_ms / 1000).toFixed(3),
      completed: ps.completed, archived_at: ps.archived_at, rats: ps.rats.map(r => ratOut(f, r)), showall_marks: marksOut(f, ps.marks)}))}; }),
  events: S.events}; }
function rows(){ const out = []; D.frames.forEach(f => { const s = S.frames[f.id];
  const passes = (s.passes || []).map((ps, i) => ({n: i + 1, rats: ps.rats, active_ms: ps.active_ms, showall_ms: ps.showall_ms, completed: ps.completed}))
    .concat([{n: (s.passes || []).length + 1, rats: s.rats, active_ms: s.active_ms, showall_ms: s.showall_ms, completed: s.completed}]);
  passes.forEach(ps => ps.rats.forEach(r => ['implant', 'rat'].forEach(k => { const o = r[k], fl = o.rank ? (o.cand_flags[o.rank] || {}) : {};
    const any = q => Object.values(o.cand_flags).some(x => x && x[q]);
    out.push({frame_id: f.id, pass: ps.n, domain: f.domain, arm: s.arm, pile_bin: f.pile_bin, frame_order: f.order, rat_id: r.id, origin: r.origin,
      click_id: r.click_id || '', head_u: r.u, head_v: r.v, deleted: r.deleted, object: k, hidden: k === 'implant' ? o.hidden : '',
      body_click_u: o.click ? o.click[0] : '', body_click_v: o.click ? o.click[1] : '', n_body_clicks: o.clicks.length, n_candidates: o.cand.length,
      source: o.source || '', rank: o.rank || '', mask_index: o.mask === null ? '' : o.mask, mask_cache_index: o.mask === null ? '' : f.masks[o.mask].i,
      mask_score: o.mask === null ? '' : f.masks[o.mask].s,
      box_x0: o.box ? o.box[0] : '', box_y0: o.box ? o.box[1] : '', box_x1: o.box ? o.box[2] : '', box_y1: o.box ? o.box[3] : '',
      prop_x0: o.prop ? o.prop[0] : '', prop_y0: o.prop ? o.prop[1] : '', prop_x1: o.prop ? o.prop[2] : '', prop_y1: o.prop ? o.prop[3] : '',
      flag_merged: !!fl.merged, flag_partial: !!fl.partial, any_merged: any('merged'), any_partial: any('partial'), edge_moves: o.edge_moves,
      next_presses: o.next_presses, object_s: +(o.time_ms / 1000).toFixed(2), frame_active_s: +(ps.active_ms / 1000).toFixed(2),
      frame_showall_s: +(ps.showall_ms / 1000).toFixed(2), frame_completed: ps.completed}); }))); }); return out; }
function csvCell(v){ v = String(v == null ? '' : v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
function exportCSV(){ const rs = rows(); const cols = Object.keys(rs[0] || {frame_id: ''}); return [cols.join(',')].concat(rs.map(r => cols.map(c => csvCell(r[c])).join(','))).join('\n') + '\n'; }
function stamp(){ const d = new Date(), p = n => String(n).padStart(2, '0'); return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + '_' + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds()); }
function download(name, text, type){ const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], {type})); a.download = name;
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); }
function strip(r){ const q = JSON.parse(JSON.stringify(r)); ['implant', 'rat'].forEach(k => { ['mask_cache_index', 'mask_score', 'cand_cache_index', 'cand_scores'].forEach(x => delete q[k][x]); }); return q; }
$('ej').addEventListener('click', () => { log('export'); download(D.export_prefix + stamp() + '.json', JSON.stringify(exportJSON()), 'application/json'); });
$('ec').addEventListener('click', () => download(D.export_prefix + stamp() + '.csv', exportCSV(), 'text/csv'));
$('ij').addEventListener('change', e => { const f = e.target.files[0]; if (!f) return; f.text().then(t => { const o = JSON.parse(t);
  if (!o.frames || o.run !== D.run || o.page_version !== D.page_version) { alert('not a v2 export of this page'); return; }
  o.frames.forEach(x => { if (!S.frames[x.frame_id]) return; const s = S.frames[x.frame_id]; s.active_ms = x.active_s * 1000; s.showall_ms = x.showall_s * 1000;
    s.visited = x.visited; s.completed = x.completed; s.rats = x.rats.map(strip); s.marks = {}; (x.showall_marks || []).forEach(m => s.marks[m.mask] = m.mark);
    s.next_add = 1 + s.rats.filter(r => r.origin === 'added').length;
    s.passes = (x.passes || []).map(ps => { const mk = {}; (ps.showall_marks || []).forEach(m => mk[m.mask] = m.mark);
      return {rats: ps.rats.map(strip), active_ms: ps.active_s * 1000, showall_ms: ps.showall_s * 1000, completed: ps.completed, marks: mk, archived_at: ps.archived_at}; }); });
  S.events = o.events || []; S.defnote = o.definition_note || ''; $('defnote').value = S.defnote; save(true); draw(); }); });
$('defnote').value = S.defnote || '';
$('defnote').addEventListener('input', e => { S.defnote = e.target.value; save(); });
$('defnote').addEventListener('change', () => log('definition_note', {text: S.defnote}));
$('showall').addEventListener('change', e => toggleShowAll(e.target.checked));
$('redo').addEventListener('click', () => redoFrame(false));
$('goto').innerHTML = D.frames.map((f, i) => '<option value="' + i + '">' + (i + 1) + ' · ' + (f.domain === 'ir' ? 'IR' : 'col') + ' · ' + f.arm + '</option>').join('');
$('goto').addEventListener('change', e => goFrame(+e.target.value));
const keepObj = S.cur.obj; goFrame(S.cur.fi); S.cur.ri = Math.max(0, Math.min(S.cur.ri, rats().length - 1)); S.cur.obj = keepObj || 'implant'; draw();
window.__pl = {S: () => S, D, goFrame, cur: () => ({fi: S.cur.fi, ri: S.cur.ri, obj: S.cur.obj}), rat: () => rat(), frame: () => fr(), drawn: () => drawnMasks,
  candidatesAt, exportJSON, exportCSV, key: KEY, redoFrame, setLastInput: dt => { lastInput = performance.now() - dt; },
  imgToClient: (u, v) => { const r0 = cv.getBoundingClientRect(), [x, y] = toCv(u, v); return [x + r0.left, y + r0.top]; },
  ready: () => { const im = img(); return im.complete && im.naturalWidth > 0; }, save: () => save(true), visible: () => document.visibilityState,
  setCur: (ri, o) => { S.cur.ri = ri; S.cur.obj = o; draw(); }};
})();
"""


def page_html_v2(run_name: str) -> str:
    import html as _html
    defs = "".join(f"<div><dt>{_html.escape(k)}:</dt><dd>{_html.escape(v)}</dd></div>" for k, v in DEFINITIONS_V2)
    css = PAGE_CSS + """
#objtag{font-weight:700;padding:1px 8px;border-radius:4px}.obj-implant{color:#111;background:#ff9f1a;padding:0 5px;border-radius:3px;font-weight:700}
.obj-rat{color:#111;background:#39ff14;padding:0 5px;border-radius:3px;font-weight:700}
"""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>In-box pre-label edit v2</title><style>{css}</style></head><body>
<header><h1>In-box CH07 — SAM 3 pre-label edit pilot (B, dev) · v2: implant box + rat box · 预标注编辑 v2</h1>
<dl class="defs">{defs}</dl>
<div class="bar"><label style="flex:1;display:flex;gap:6px;align-items:center">my definition changes / 我的定义修改:
<input type="text" id="defnote" style="flex:1;font:inherit;padding:3px 6px" placeholder="optional — exported with your labels"></label></div>
<div class="bar"><div style="flex:1"><div class="prog"><div id="progbar" style="width:0"></div></div></div><span id="progtxt"></span>
<button id="ej" type="button">Export JSON</button><button id="ec" type="button">Export CSV</button>
<label class="btn">Import JSON<input id="ij" type="file" accept=".json,application/json" class="hidden"></label></div></header>
<div class="wrap"><div><div class="bar"><span id="armtag"></span><span id="objtag"></span><span id="ftitle" style="font-weight:600"></span><span id="timetxt" style="color:var(--muted)"></span></div>
<canvas id="cv"></canvas><div id="banner"></div></div>
<div class="side"><div id="status"></div>
<label><input type="checkbox" id="showall"> show all "rat" candidates (S) · 显示全部候选</label>
<label>jump to frame <select id="goto"></select></label>
<button id="redo" type="button" title="the current labels are kept as an earlier pass">redo this frame (keeps the earlier pass) · 重做此帧</button>
<div class="keys"><b>Per rat: IMPLANT box, then RAT box, then Enter</b> 每只鼠: 先植入体框, 再鼠框, 然后 Enter.<br>
<span class="obj-implant">IMPLANT</span> candidates come from the head dot (cyan). <span class="obj-rat">RAT</span> (head + body, no tail):
click on the rat's body first 先点鼠身体; candidates containing that point are offered (pink).<br>
<b>PRELABEL</b>: A accept 接受 (box = the mask's bounding box, no padding) · N next candidate 下一个候选 (then "none usable") ·
M / P flag merged / partial (rat box) 合并 / 不完整 · B draw by hand 手画框 · F fit back to the mask 恢复 mask 框<br>
<b>SCRATCH</b>: drag the implant box, Enter, drag the rat box 先拖植入体框, Enter, 再拖鼠框<br>
<b>both</b>: H implant hidden 植入体看不见 · drag a box edge to adjust 拖边调整 · Tab switch implant / rat 切换 · Enter / → next box, then next rat 下一个 ·
← back 上一个 · R add a rat whose head is hidden, click its body 加鼠 · X delete a dot that is not a rat 删除点 · U undo 撤销 ·
PageDown / PageUp frame 换帧 · wheel zoom 缩放 · right-drag or Space + drag pan 平移 · Z fit 适配 · Esc cancel<br>
Clock: active time per frame and per box; it pauses when the tab is hidden or after 45 s without input (计时: 45 秒无操作暂停). Stop any time; progress is saved in this browser.</div>
<div class="keys">Exports (prefix v2_) → <code>cv/configs/inbox_sam3_prelabel_edit_2026c/</code> · run {_html.escape(run_name)}</div></div></div>
<script src="pl_data.js"></script>
<script>{PAGE_JS_V2}</script></body></html>
"""


def build_v2(run: Path, check: bool = True) -> dict:
    """The v2 page in <run>/prelabel_edit_v2/: same frames, arms, seed, masks and head candidate lists as v1 (amendment B1:
    arms unchanged); implant box from the head candidates, rat box from a body click. v1's files are not touched."""
    import os
    frames = pd.read_csv(run / "frames.csv")
    heads = pd.read_csv(run / "heads.csv")
    arms = assign_arms(frames, heads)
    out = run / "prelabel_edit_v2"
    if out.exists():
        shutil.rmtree(out)
    (out / "frames").mkdir(parents=True)
    data = {"page_version": PAGE_VERSION_V2, "run": run.name, "plan": PLAN, "seed": SEED, "idle_ms": IDLE_MS, "cover_px": S.COVER_PX,
            "definitions": [{"term": k, "text": v} for k, v in DEFINITIONS_V2], "export_prefix": "v2_inbox_sam3_prelabel_edit_2026c_",
            "frames": []}
    linked = 0
    for r in arms.itertuples():
        H = heads[heads.frame_id == r.frame_id].sort_values(["u", "click_id"]).reset_index(drop=True)
        pl = frame_payload(run, r.frame_id, H)
        dst = out / "frames" / Path(r.path).name
        src_v1 = run / "prelabel_edit" / "frames" / dst.name
        try:
            os.link(src_v1 if src_v1.exists() else r.path, dst)            # hard link (no second copy on disk)
            linked += 1
        except OSError:
            shutil.copy2(r.path, dst)
        data["frames"].append({"id": r.frame_id, "domain": r.domain, "arm": r.arm, "pile_bin": r.pile_bin, "order": int(r.order),
                               "img": f"frames/{dst.name}", "w": S.IMG_W, "h": S.IMG_H,
                               "heads": [{"c": h.click_id, "u": round(float(h.u), 1), "v": round(float(h.v), 1)} for h in H.itertuples()],
                               "masks": pl["masks"], "cand": pl["cand"]})
        print(f"  build v2 {int(r.order)}/{len(arms)} {r.frame_id} ({r.arm})", flush=True)
    (out / "pl_data.js").write_text("window.PL_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n", encoding="utf-8")
    (out / "index.html").write_text(page_html_v2(run.name), encoding="utf-8")
    arms.drop(columns=["path"]).to_csv(out / "arms.csv", index=False)
    v1_arms = run / "prelabel_edit" / "arms.csv"
    same_arms = bool(v1_arms.exists() and pd.read_csv(v1_arms)[["frame_id", "arm", "order"]].equals(arms[["frame_id", "arm", "order"]]))
    meta = {"made": datetime.now().isoformat(timespec="seconds"), "plan": PLAN, "amendments": "B1, B1a", "run": run.as_posix(), "seed": SEED,
            "page_version": PAGE_VERSION_V2, "n_frames": len(arms), "n_prelabel": int((arms.arm == "PRELABEL").sum()),
            "n_scratch": int((arms.arm == "SCRATCH").sum()), "arms_identical_to_v1": same_arms, "frames_hard_linked": linked,
            "size": {"pl_data_js_bytes": (out / "pl_data.js").stat().st_size, "index_html_bytes": (out / "index.html").stat().st_size,
                     "frames_bytes_apparent": int(sum(p.stat().st_size for p in (out / "frames").glob("*.jpg")))},
            "git_commit": git_commit()}
    if check:
        meta["page_check"] = page_check_v2(out, data)
        S.write_json(out / "page_check.json", meta["page_check"])
        print(f"v2 page check: {meta['page_check']['verdict']}", flush=True)
    S.write_json(out / "build_meta.json", meta)
    return meta


def page_check_v2(out: Path, data: dict) -> dict:
    """Headless Chrome (throwaway profile), the full two-box flow: implant accept + edge move + F; H; body click -> candidates
    -> N -> accept; manual rat box; SCRATCH two boxes; add / delete / undo; per-object time + idle pause; a v1 storage key is
    ignored; persistence across a reload; export; no network URL."""
    import inbox_identity_page as ipage
    html_t, js_t = (out / "index.html").read_text(encoding="utf-8"), (out / "pl_data.js").read_text(encoding="utf-8")
    res = {"network_urls": re.findall(r"https?://[^\s\"'<>]+", html_t) + re.findall(r"https?://[^\s\"'<>]+", js_t)}
    prof = Path(tempfile.mkdtemp(prefix="pl2check_"))
    p, wsu, bws = ipage._chrome((out / "index.html").resolve().as_uri(), prof, ipage._free_port())
    c = None
    try:
        c = ipage._CDP(wsu)
        c.call("Runtime.enable")

        def ready():
            for _ in range(240):
                try:
                    if c.ev("!!window.__pl && window.__pl.ready()"):
                        return True
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(0.25)
            return False

        def key(k):
            c.ev(f"document.dispatchEvent(new KeyboardEvent('keydown', {{key: {json.dumps(k)}, bubbles: true}}))")

        def mouse(kind, u, v):
            c.ev(f"(() => {{ const [x, y] = window.__pl.imgToClient({u}, {v}); document.getElementById('cv').dispatchEvent("
                 f"new MouseEvent({json.dumps(kind)}, {{clientX: x, clientY: y, button: 0, bubbles: true}})); }})()")

        def click(u, v):
            mouse("mousedown", u, v)
            mouse("mouseup", u, v)

        def drag(u0, v0, u1, v1):
            mouse("mousedown", u0, v0)
            mouse("mousemove", (u0 + u1) / 2, (v0 + v1) / 2)
            mouse("mousemove", u1, v1)
            mouse("mouseup", u1, v1)

        def R():
            return c.ev("JSON.parse(JSON.stringify(window.__pl.rat()))")

        def cur():
            return c.ev("window.__pl.cur()")
        # a v1 state under the v1 key must be ignored
        c.ev("localStorage.setItem('inbox_sam3_prelabel_edit_2026c_v1::' + window.PL_DATA.run, JSON.stringify({frames: {x: 1}, cur: {fi: 5, ri: 0}}))")
        c.call("Page.reload")
        time.sleep(1.0)
        res["loaded"] = ready()
        res["v1_storage_ignored"] = {"cur_fi": cur()["fi"], "ok": cur()["fi"] == 0 and c.ev("!!localStorage.getItem('inbox_sam3_prelabel_edit_2026c_v1::' + window.PL_DATA.run)")}
        fr = data["frames"]
        # PRELABEL frame: head 0 with an implant candidate, and a body point with >= 2 rat candidates
        fi, body = None, None
        for i, f in enumerate(fr):
            if f["arm"] != "PRELABEL" or len(f["cand"]) < 2 or not f["cand"][0]:
                continue
            for m in sorted(f["masks"], key=lambda m: -m["a"])[:15]:
                for pts in m["p"]:
                    x0, y0 = float(np.mean(pts[0::2])), float(np.mean(pts[1::2]))
                    if _pip(x0, y0, pts):
                        c.ev(f"window.__pl.goFrame({i})")
                        if len(c.ev(f"window.__pl.candidatesAt({x0}, {y0})")) >= 2:
                            fi, body = i, (x0, y0)
                        break
                if body:
                    break
            if body:
                break
        c.ev(f"window.__pl.goFrame({fi})")
        ready()
        f = fr[fi]
        cb = f["masks"][f["cand"][0][0]]["b"]
        # 1 implant: accept, edge move, F
        st0 = cur()
        key("a")
        r = R()
        acc_ok = st0["obj"] == "implant" and r["implant"]["source"] == "cand" and r["implant"]["rank"] == 1 and r["implant"]["box"] == cb
        b = r["implant"]["box"]
        drag(b[2], (b[1] + b[3]) / 2, b[2] + 30, (b[1] + b[3]) / 2)
        moved = R()["implant"]
        key("f")
        fitted = R()["implant"]["box"]
        res["implant"] = {"accept_ok": acc_ok, "edge_moves": moved["edge_moves"], "fitted_equals_mask": fitted == cb,
                          "ok": acc_ok and moved["edge_moves"] == 1 and moved["box"] != cb and fitted == cb}
        # 2 Enter -> RAT box; no candidate before the body click; body click -> candidates; N; accept rank 2
        key("Enter")
        o1 = cur()["obj"]
        drawn_before = c.ev("window.__pl.drawn()")
        click(*body)
        rr = R()["rat"]
        key("n")
        k1 = R()["rat"]["k"]
        key("m")
        key("a")
        rr2 = R()["rat"]
        res["rat_box"] = {"obj_after_enter": o1, "drawn_before_click": drawn_before, "n_cand": len(rr["cand"]), "prop": rr["prop"],
                          "click": rr["click"], "k_after_n": k1, "source": rr2["source"], "rank": rr2["rank"], "flags": rr2["cand_flags"],
                          "ok": o1 == "rat" and drawn_before == 0 and len(rr["cand"]) >= 2 and rr["click"] is not None
                          and rr["prop"] == f["masks"][rr["cand"][0]]["b"] and k1 == 1 and rr2["source"] == "cand" and rr2["rank"] == 2
                          and rr2["cand_flags"].get("2", {}).get("merged") is True and rr2["box"] == f["masks"][rr["cand"][1]]["b"]}
        # 3 Enter -> next rat (implant); H -> hidden, active = rat; manual rat box (B + drag)
        ri0 = cur()["ri"]
        key("Enter")
        c2 = cur()
        key("h")
        c3 = cur()
        hu, hv = f["heads"][c2["ri"]]["u"], f["heads"][c2["ri"]]["v"]
        key("b")
        drag(hu - 150, hv - 100, hu + 220, hv + 160)
        r3 = R()
        res["hidden_and_manual"] = {"moved_to_rat": c2["ri"] != ri0 and c2["obj"] in ("implant", "rat"), "hidden": r3["implant"]["hidden"],
                                    "obj_after_h": c3["obj"], "rat_source": r3["rat"]["source"], "rat_box": r3["rat"]["box"],
                                    "ok": c2["ri"] != ri0 and r3["implant"]["hidden"] is True and r3["implant"]["box"] is None and c3["obj"] == "rat"
                                    and r3["rat"]["source"] == "manual" and abs(r3["rat"]["box"][0] - (hu - 150)) < 3}
        # 4 add / delete / undo (added rat: implant hidden, rat candidates from the add point)
        fid_js = json.dumps(f["id"])
        nr = c.ev(f"window.__pl.S().frames[{fid_js}].rats.length")
        key("r")
        click(*body)
        ra = R()
        key("x")
        dl = c.ev(f"window.__pl.S().frames[{fid_js}].rats[{nr}].deleted")
        key("u")
        ud = c.ev(f"window.__pl.S().frames[{fid_js}].rats[{nr}].deleted")
        res["add_delete_undo"] = {"origin": ra["origin"], "implant_hidden": ra["implant"]["hidden"], "rat_n_cand": len(ra["rat"]["cand"]),
                                  "deleted": dl, "after_undo": ud,
                                  "ok": ra["origin"] == "added" and ra["implant"]["hidden"] is True and len(ra["rat"]["cand"]) >= 1 and dl is True and ud is False}
        # 5 per-object time slice + idle pause
        c.ev("window.__pl.setCur(0, 'rat')")
        t0 = c.ev(f"window.__pl.S().frames[{fid_js}].rats[0].rat.time_ms")
        i0 = c.ev(f"window.__pl.S().frames[{fid_js}].rats[0].implant.time_ms")
        for _ in range(3):
            c.ev("window.__pl.setLastInput(0)")
            time.sleep(0.5)
        t1 = c.ev(f"window.__pl.S().frames[{fid_js}].rats[0].rat.time_ms")
        i1 = c.ev(f"window.__pl.S().frames[{fid_js}].rats[0].implant.time_ms")
        c.ev("window.__pl.setLastInput(50000)")
        a0 = c.ev(f"window.__pl.S().frames[{fid_js}].active_ms")
        time.sleep(1.6)
        a1 = c.ev(f"window.__pl.S().frames[{fid_js}].active_ms")
        c.ev("window.__pl.setLastInput(0)")
        res["timing"] = {"rat_slice_gain_ms": t1 - t0, "implant_slice_gain_ms": i1 - i0, "idle_gain_ms": a1 - a0,
                         "ok": t1 - t0 > 800 and i1 - i0 < 1e-6 and a1 - a0 < 1e-6}
        # 6 SCRATCH frame: two boxes by hand, no mask drawn
        fs = next(i for i, x in enumerate(fr) if x["arm"] == "SCRATCH")
        c.ev(f"window.__pl.goFrame({fs})")
        ready()
        g = fr[fs]
        gu, gv = g["heads"][0]["u"], g["heads"][0]["v"]
        drag(gu - 60, gv - 50, gu + 60, gv + 40)
        key("Enter")
        drag(gu - 200, gv - 150, gu + 250, gv + 200)
        r6 = R()
        res["scratch"] = {"implant_source": r6["implant"]["source"], "rat_source": r6["rat"]["source"], "drawn_masks": c.ev("window.__pl.drawn()"),
                          "ok": r6["implant"]["source"] == "manual" and r6["rat"]["source"] == "manual" and c.ev("window.__pl.drawn()") == 0}
        # 7 persistence
        snap_before = c.ev(f"JSON.stringify(window.__pl.S().frames[{fid_js}].rats.map(r => [r.implant.box, r.implant.hidden, r.rat.box, r.rat.click]))")
        c.ev("window.__pl.save()")
        c.call("Page.reload")
        time.sleep(1.5)
        ready()
        snap_after = c.ev(f"JSON.stringify(window.__pl.S().frames[{fid_js}].rats.map(r => [r.implant.box, r.implant.hidden, r.rat.box, r.rat.click]))")
        res["persistence"] = {"ok": snap_before == snap_after}
        # 8 export
        ej = c.ev("window.__pl.exportJSON()")
        n_rats = sum(len(x["rats"]) for x in ej["frames"])
        csv_lines = c.ev("window.__pl.exportCSV().trim().split('\\n').length")
        evk = sorted({e["ev"] for e in ej["events"]})
        f0 = next(x for x in ej["frames"] if x["frame_id"] == f["id"])
        props_ok = all((r["implant"]["prop"] == f["masks"][r["implant"]["cand"][0]]["b"]) if r["implant"]["cand"] else r["implant"]["prop"] is None
                       for r in f0["rats"] if r["origin"] == "click")
        res["export"] = {"version": ej["page_version"], "frames": len(ej["frames"]), "rats": n_rats, "csv_lines": csv_lines, "event_kinds": evk,
                         "implant_props_ok": props_ok,
                         "ok": ej["page_version"] == PAGE_VERSION_V2 and len(ej["frames"]) == len(fr) and csv_lines == 2 * n_rats + 1 and props_ok
                         and {"accept", "edge_move", "fit_to_mask", "obj_next", "body_click", "next", "flag", "implant_hidden", "manual_box",
                              "add_rat", "delete_dot", "undo", "rat_next"} <= set(evk)}
        c.ev("localStorage.clear()")
    finally:
        if c:
            c.close()
        ipage._close_chrome(p, bws)
        shutil.rmtree(prof, ignore_errors=True)
    keys = ["v1_storage_ignored", "implant", "rat_box", "hidden_and_manual", "add_delete_undo", "timing", "scratch", "persistence", "export"]
    res["verdict"] = "PASS" if (res.get("loaded") and all(res[k]["ok"] for k in keys) and not res["network_urls"]) else "FAIL"
    return res


# ---------------------------------------------------------------- v2 summary (per object type)
def obj_table_v2(ex: dict) -> pd.DataFrame:
    """One row per rat x object (implant, rat) of each frame's main pass, with the v1 derived columns."""
    rows = []
    for f0 in ex["frames"]:
        mp = main_pass(f0)
        for r in mp["rats"]:
            for k in OBJS:
                o = r[k]
                cf = o.get("cand_flags") or {}
                acc = cf.get(str(o.get("rank")), {}) if o.get("rank") else {}
                rows.append({"frame_id": f0["frame_id"], "domain": f0["domain"], "arm": f0["arm"], "pile_bin": f0["pile_bin"],
                             "completed": bool(mp["completed"]), "rat_id": r["id"], "origin": r["origin"], "deleted": bool(r["deleted"]),
                             "object": k, "hidden": bool(o.get("hidden")) if k == "implant" else False, "n_cand": len(o.get("cand") or []),
                             "source": o.get("source") or "", "rank": o.get("rank"), "boxed": o.get("box") is not None,
                             "acc_merged": bool(acc.get("merged")), "acc_partial": bool(acc.get("partial")),
                             "any_merged": any(bool((v or {}).get("merged")) for v in cf.values()),
                             "any_partial": any(bool((v or {}).get("partial")) for v in cf.values()),
                             "edge_moves": int(o.get("edge_moves") or 0), "next_presses": int(o.get("next_presses") or 0),
                             "prop": o.get("prop"), "box": o.get("box"), "time_s": float(o.get("time_ms") or 0) / 1000.0,
                             "has_click": o.get("click") is not None, "u": r["u"], "v": r["v"], "pass": mp.get("pass", 1)})
    t = pd.DataFrame(rows)
    return derive(t) if len(t) else t


def obj_block_v2(d: pd.DataFrame) -> dict:
    """Per object type on its evaluated objects (not deleted, boxed), PRELABEL arm."""
    pre = d[d.arm == "PRELABEL"]
    n = len(pre)
    c3 = c3_table(d) if len(d) else pd.DataFrame()
    cb = c3_block(c3)
    return {"n_prelabel": n, "usable1": pre.usable1.mean() if n else np.nan, "usable_any": pre.usable_any.mean() if n else np.nan,
            "manual": pre.manual.mean() if n else np.nan, "merged": pre.any_merged.mean() if n else np.nan,
            "partial": pre.any_partial.mean() if n else np.nan, "no_candidate": (pre.n_cand == 0).mean() if n else np.nan,
            "quality": quality_block(d), "c3": {"n": int(len(c3)), "edges": cb, "padding_rule_frac": {e: cb[e]["frac"]["median"] for e in EDGES},
                                                "uniformity": uniformity(cb)}}


def summarize_v2(ex: dict, more: list | None = None) -> dict:
    t = obj_table_v2(ex)
    live = t[~t.deleted] if len(t) else t
    ev = live[live.boxed] if len(live) else live
    fr = pd.DataFrame([{"frame_id": f["frame_id"], "domain": f["domain"], "arm": f["arm"], "pile_bin": f["pile_bin"],
                        "completed": bool(mp["completed"]), "showall_s": float(mp["showall_s"]),
                        "n_garbage": sum(1 for m in (mp.get("showall_marks") or []) if m["mark"] == "garbage"),
                        "n_fragment": sum(1 for m in (mp.get("showall_marks") or []) if m["mark"] == "fragment")}
                       for f in ex["frames"] for mp in [main_pass(f)]])
    done = set(fr.loc[fr.completed, "frame_id"])

    def secs(d: pd.DataFrame, arm: str) -> dict:
        x = d[(d.arm == arm) & d.frame_id.isin(done)]
        return {"n": int(len(x)), "s_per_object": float(x.time_s.sum() / len(x)) if len(x) else np.nan,
                "median_s": float(x.time_s.median()) if len(x) else np.nan}

    def hidden_rate(d: pd.DataFrame) -> dict:
        x = d[d.object == "implant"]
        return {a: (float(x[x.arm == a].hidden.mean()) if (x.arm == a).any() else np.nan) for a in ("PRELABEL", "SCRATCH")} | {
            "all": float(x.hidden.mean()) if len(x) else np.nan, "n_rats": int(len(x))}
    out = {"page_version": PAGE_VERSION_V2, "n_frames_visited": int(sum(1 for f in ex["frames"] if f.get("visited"))),
           "n_frames_completed": int(fr.completed.sum()), "n_rats": int((t.object == "rat").sum()) if len(t) else 0,
           "n_deleted": int(((t.object == "rat") & t.deleted).sum()) if len(t) else 0,
           "n_added": int(((t.object == "rat") & (t.origin == "added") & ~t.deleted).sum()) if len(t) else 0,
           "hidden": hidden_rate(live) if len(live) else {}, "objects": {}, "split": [],
           "showall": {"frames_used": int((fr.showall_s > 0).sum()), "showall_s": float(fr.showall_s.sum()),
                       "garbage": int(fr.n_garbage.sum()), "fragment": int(fr.n_fragment.sum())},
           "definition_note": ex.get("definition_note", "")}
    for k in OBJS:
        d = ev[ev.object == k] if len(ev) else ev
        out["objects"][k] = {**(obj_block_v2(d) if len(d) else {"n_prelabel": 0}), "time": ({a: secs(d, a) for a in ("PRELABEL", "SCRATCH")} if len(d) else {}),
                             "sizes": {"scratch": size_block(d[d.arm == "SCRATCH"].box) if len(d) else size_block([]),
                                       "accepted_mask_bbox": size_block([m for m in d[(d.arm == "PRELABEL") & (d.source == "cand")].prop]) if len(d) else size_block([])}}
        for dom in ("ir", "colour"):
            for b in PILE_BINS:
                x = d[(d.domain == dom) & (d.pile_bin == b)] if len(d) else d
                lx = live[(live.domain == dom) & (live.pile_bin == b)] if len(live) else live
                row = {"object": k, "domain": dom, "pile_bin": b}
                if len(x):
                    bl = obj_block_v2(x)
                    row.update({kk: bl[kk] for kk in ("n_prelabel", "usable1", "usable_any", "manual", "merged", "partial")})
                    row.update({f"iou_{q}": bl["quality"][f"iou_{q}"] for q in ("median", "q25", "q75")})
                    row.update({f"pad_{e}": bl["c3"]["padding_rule_frac"][e] for e in EDGES})
                    row["uniform"] = bl["c3"]["uniformity"]["uniform"]
                    for a in ("PRELABEL", "SCRATCH"):
                        row[f"{a}_s"] = secs(x, a)["s_per_object"]
                if k == "implant" and len(lx):
                    row["hidden"] = float(lx[lx.object == "implant"].hidden.mean()) if (lx.object == "implant").any() else np.nan
                out["split"].append(row)
    # repeat check per object: reuse the v1 pairing on per-object views of the passes
    out["repeat"] = {}
    for k in OBJS:
        exs = [ex] + list(more or [])
        proj = [{**e, "frames": [{**f, "rats": [{"id": r["id"], "u": r["u"], "v": r["v"], "deleted": r["deleted"] or (k == "implant" and r["implant"].get("hidden")),
                                                 "box": r[k].get("box")} for r in f["rats"]],
                                  "passes": [{**ps, "rats": [{"id": r["id"], "u": r["u"], "v": r["v"],
                                                              "deleted": r["deleted"] or (k == "implant" and r["implant"].get("hidden")),
                                                              "box": r[k].get("box")} for r in ps["rats"]]} for ps in (f.get("passes") or [])]}
                                 for f in e["frames"]]} for e in exs]
        rp = repeat_pairs(proj)
        out["repeat"][k] = {"n_pairs": len(rp), "n_frames": int(rp.frame_id.nunique()) if len(rp) else 0,
                            "iou_median": float(rp.iou.median()) if len(rp) else np.nan,
                            "iou_q25": float(rp.iou.quantile(0.25)) if len(rp) else np.nan,
                            "iou_q75": float(rp.iou.quantile(0.75)) if len(rp) else np.nan,
                            "share_below_0_5": float((rp.iou < 0.5).mean()) if len(rp) else np.nan}
    return out


def summary_md_v2(sm: dict, export_name: str) -> str:
    def fx(v, d=1):
        return S.f3(v, d)
    L = ["## B — pre-label edit pilot (dev)", "",
         f"Plan `{PLAN}`, part B as amended by B1 / B1a: an implant box and a rat box per rat. Page v2; driver "
         f"`cv/cv_field/inbox_prelabel_edit.py`; the user's export `{export_name}`.", "",
         "**Status: dev, descriptive only.** The 58 frames had all been seen before, so nothing here is a claim and the timing "
         "contrast is indicative only. The frozen test is part C. Every metric is per object type (implant box, rat box).", "",
         "**Coverage of the export:**",
         f"- {sm['n_frames_completed']} frames completed of {sm['n_frames_visited']} opened;",
         f"- {sm['n_rats']} rats, {sm['n_added']} added by the user (head hidden), {sm['n_deleted']} dots deleted.", ""]
    hd = sm.get("hidden") or {}
    if hd:
        L += [f"**Implant hidden:** {S.pct(hd.get('all', np.nan))} of {hd.get('n_rats', 0)} rats (PRELABEL "
              f"{S.pct(hd.get('PRELABEL', np.nan))}, SCRATCH {S.pct(hd.get('SCRATCH', np.nan))}).", ""]
    for k, name in (("implant", "Implant box"), ("rat", "Rat box (head + body, no tail)")):
        o = sm["objects"].get(k, {})
        if not o or not o.get("n_prelabel"):
            L += [f"### {name}", "", "No PRELABEL object of this type in the export.", ""]
            continue
        q, c3 = o["quality"], o["c3"]
        tp, ts = o["time"].get("PRELABEL", {}), o["time"].get("SCRATCH", {})
        L += [f"### {name}", "",
              f"**PRELABEL** ({o['n_prelabel']} boxes):",
              f"- usable@1 {S.pct(o['usable1'])}; usable@any {S.pct(o['usable_any'])}; manual {S.pct(o['manual'])}; no candidate "
              f"{S.pct(o['no_candidate'])}" + (f"; merged {S.pct(o['merged'])}, partial {S.pct(o['partial'])}." if k == "rat" else "."),
              f"- IoU proposed → final: median {fx(q['iou_median'], 3)} [quartiles {fx(q['iou_q25'], 3)}, {fx(q['iou_q75'], 3)}];",
              f"- no edit {S.pct(q['no_edit'])}; edge moves only {S.pct(q['edge_only'])} (median edge shift "
              f"{fx(q['edge_shift_median_px'])} px); another candidate {S.pct(q['other_candidate'])}.",
              f"- Seconds per box (per-object time slices, completed frames): PRELABEL {fx(tp.get('s_per_object', np.nan))} s "
              f"(n {tp.get('n', 0)}), SCRATCH {fx(ts.get('s_per_object', np.nan))} s (n {ts.get('n', 0)}).", ""]

        def cell(qq, pct_=False):
            if not qq["n"]:
                return "–"
            f = (lambda v: f"{100 * v:+.1f} %") if pct_ else (lambda v: f"{v:+.0f}")
            return f"{f(qq['median'])} [{f(qq['q25'])}, {f(qq['q75'])}]"
        L += [f"Per-edge signed shift from the mask bbox to the final box ({c3['n']} kept first candidates; + = the final box larger):", "",
              S.md_table(pd.DataFrame([{**{f"{e} px": cell(c3["edges"][e]["px"]) for e in EDGES},
                                        **{f"{e} fraction": cell(c3["edges"][e]["frac"], True) for e in EDGES}}])), ""]
        pr, un = c3["padding_rule_frac"], c3["uniformity"]
        L += ["- **Proposed padding rule** (a proposal; frozen later with the user): "
              + ", ".join(f"{e} {100 * pr[e]:+.1f} %" if np.isfinite(pr[e]) else f"{e} –" for e in EDGES) + ".",
              "- Uniformity: " + ("not computable." if un["uniform"] is None else ("**uniform**." if un["uniform"] else
                                  "**NOT uniform** (" + "; ".join(([f"IQR > |median| on {', '.join(un['spread_edges'])}"] if un["spread_flag"] else [])
                                                                 + ([f"{un['worst_edge']} edge {un['worst_over_others']:.1f}× the others"] if un["one_edge_flag"] else []))
                                  + "); a uniform padding would then not be used (amendment C3 item 3).")), ""]
        sz = o["sizes"]

        def scell(qq, d=0):
            return "–" if not qq["n"] else f"{qq['median']:.{d}f} [{qq['q25']:.{d}f}, {qq['q75']:.{d}f}] (n {qq['n']})"
        L += [S.md_table(pd.DataFrame([{"boxes": nm, "width px": scell(v["width_px"]), "height px": scell(v["height_px"]),
                                        "aspect w / h": scell(v["aspect_w_over_h"], 2)}
                                       for nm, v in (("SCRATCH (by hand)", sz["scratch"]), ("accepted mask bboxes", sz["accepted_mask_bbox"]))])), ""]
        rows = [{"domain": r["domain"], "pile": r["pile_bin"], "PRELABEL n": r.get("n_prelabel", 0), "usable@1": S.pct(r.get("usable1", np.nan)),
                 "usable@any": S.pct(r.get("usable_any", np.nan)), "manual": S.pct(r.get("manual", np.nan)),
                 **({"merged": S.pct(r.get("merged", np.nan)), "partial": S.pct(r.get("partial", np.nan))} if k == "rat" else
                    {"hidden": S.pct(r.get("hidden", np.nan))}),
                 "IoU median": fx(r.get("iou_median", np.nan), 3),
                 "padding L / R / T / B": " / ".join(f"{100 * r[f'pad_{e}']:+.0f} %" if np.isfinite(r.get(f"pad_{e}", np.nan)) else "–" for e in EDGES),
                 "s PRELABEL": fx(r.get("PRELABEL_s", np.nan)), "s SCRATCH": fx(r.get("SCRATCH_s", np.nan))}
                for r in sm["split"] if r["object"] == k]
        L += ["By domain and pile size:", "", S.md_table(pd.DataFrame(rows)), ""]
        rp = sm["repeat"].get(k, {})
        L += [f"Repeat check ({name.lower()}): " + (f"{rp['n_pairs']} pairs on {rp['n_frames']} frames, IoU median {fx(rp['iou_median'], 3)} "
                                                    f"[{fx(rp['iou_q25'], 3)}, {fx(rp['iou_q75'], 3)}], {S.pct(rp['share_below_0_5'])} below 0.5."
                                                    if rp.get("n_pairs") else "no frame was labelled twice."), ""]
    sa = sm["showall"]
    L += [f"**'Show all' view** (descriptive): {sa['frames_used']} frames, {fx(sa['showall_s'], 0)} s, {sa['garbage']} garbage / "
          f"{sa['fragment']} fragment marks.", ""]
    if sm.get("definition_note"):
        L += [f"**The user's definition changes:** {sm['definition_note']}", ""]
    L += ["**Definitions (B, v2):**", "",
          "- **Implant box** = the implant only; candidates = the 'rat' masks within 15 px of the head point, in score order; "
          "**implant hidden** = the user's H.",
          "- **Rat box** = head + body, no tail, visible parts only; candidates = the masks containing the user's body click "
          "(polygon or within 15 px), in score order. The proposed box is the first candidate of the latest body click.",
          "- **usable@1 / usable@any:** per object type, as in v1. Merged / partial flags apply to the rat box only.",
          "- **IoU proposed → final**, **edge shifts**, **padding rule**, **uniformity flag:** as in v1 (C2 / C3), per object type.",
          "- **Seconds per box** = the object's active time slice (the clock runs for the active box only; it pauses when the tab "
          "is hidden or after 45 s without input), mean over the boxed objects on completed frames.",
          "- **Repeat check** per object type: rats paired by head point within 15 px, IoU of the two final boxes (hidden implants "
          "excluded).", ""]
    return "\n".join(L)


# ============================================================================================ selftest
def selftest() -> int:
    ok_all = True

    def rec(name, cond, detail=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    # arms
    fr_, hd_ = [], []
    k = 0
    for dom, b, n in (("ir", 2, 30), ("ir", 5, 8), ("colour", 1, 1), ("colour", 3, 15), ("colour", 4, 4)):
        for _ in range(n):
            fid = f"F{k:03d}"
            fr_.append({"frame_id": fid, "domain": dom, "segment_id": fid, "frame_kind": "x", "path": "x", "frame_time": "t", "n_heads": b, "split": "dev"})
            for j in range(b):
                hd_.append({"frame_id": fid, "pile_size": b if j == 0 else 1})
            k += 1
    a = assign_arms(pd.DataFrame(fr_), pd.DataFrame(hd_))
    cnt = a.groupby(["domain", "pile_bin", "arm"]).size().to_dict()
    rec("arms: round(2n/3) PRELABEL per stratum", cnt == {("colour", "1", "PRELABEL"): 1, ("colour", "2-3", "PRELABEL"): 10, ("colour", "2-3", "SCRATCH"): 5,
                                                      ("colour", "4+", "PRELABEL"): 3, ("colour", "4+", "SCRATCH"): 1, ("ir", "2-3", "PRELABEL"): 20,
                                                      ("ir", "2-3", "SCRATCH"): 10, ("ir", "4+", "PRELABEL"): 5, ("ir", "4+", "SCRATCH"): 3}, str(cnt))
    rec("arms: IR first, then colour; order 1..n", list(a.domain[:38]) == ["ir"] * 38 and list(a.domain[38:]) == ["colour"] * 20
        and sorted(a.order) == list(range(1, 59)))
    a2 = assign_arms(pd.DataFrame(fr_), pd.DataFrame(hd_))
    rec("arms: deterministic with the seed", a.equals(a2))
    rec("pile bins", [pile_bin(x) for x in (1, 2, 3, 4, 5)] == ["1", "2-3", "2-3", "4+", "4+"])
    # candidate order and polygons
    rec("candidate order: score desc, then smaller area, then index",
        order_candidates([0, 1, 2, 3], np.array([0.2, 0.5, 0.5, 0.1]), np.array([10, 300, 200, 5])) == [2, 1, 0, 3])
    try:
        import cv2  # noqa: F401
        m = np.zeros((60, 80), bool)
        m[10:40, 20:70] = True
        polys = mask_polygons(m[10:40, 20:70], (20, 10, 70, 40))
        xs, ys = polys[0][0::2], polys[0][1::2]
        rec("polygon at full resolution (offset by the bbox)", min(xs) == 20 and max(xs) == 69 and min(ys) == 10 and max(ys) == 39, str(polys))
    except ImportError:
        print("[SKIP] opencv not available")
    # page script syntax
    node = shutil.which("node")
    if node:
        with tempfile.TemporaryDirectory() as td:
            js = Path(td) / "pl.js"
            js.write_text(PAGE_JS, encoding="utf-8")
            r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
            rec("page script parses (node --check)", r.returncode == 0, r.stderr[-300:])
    else:
        print("[SKIP] node not on PATH")
    sq = [0, 0, 10, 0, 10, 10, 0, 10]
    rec("point-in-polygon (page rule)", _pip(5, 5, sq) and not _pip(15, 5, sq) and not _pip(5, -1, sq))
    html_t = page_html("x")
    rec("page: no network URL, data in a sibling .js", not re.search(r"https?://", html_t) and '<script src="pl_data.js">' in html_t)
    # summarize on a synthetic export
    def R(i, src, rank=None, flags=None, cand=3, deleted=False, origin="click", edges=0, nxt=0):
        cf = {str(k): v for k, v in (flags or {}).items()}
        box = None if src is None else ([0, 0, 10, 10] if edges == 0 else [0, 0, 12, 10])
        return {"id": f"h{i}", "origin": origin, "deleted": deleted, "cand": list(range(cand)), "source": src, "rank": rank,
                "box": box, "prop": [0, 0, 10, 10] if cand else None, "u": 100.0 * i, "v": 50.0,
                "cand_flags": cf, "edge_moves": edges, "next_presses": nxt}
    ex = {"page_version": PAGE_VERSION, "definition_note": "boxes include the head even if tucked", "frames": [
        {"frame_id": "A", "domain": "ir", "arm": "PRELABEL", "pile_bin": "2-3", "completed": True, "visited": True, "active_s": 60.0, "showall_s": 20.0,
         "showall_marks": [{"mask": 3, "mark": "garbage"}, {"mask": 4, "mark": "fragment"}],
         "rats": [R(1, "cand", 1), R(2, "cand", 2, {1: {"merged": True}}, nxt=1), R(3, "manual", None, {1: {"partial": True}}, nxt=3),
                  R(4, "cand", 1, {1: {"merged": True}}, edges=2), R(5, None, deleted=True)]},
        {"frame_id": "B", "domain": "ir", "arm": "SCRATCH", "pile_bin": "2-3", "completed": True, "visited": True, "active_s": 90.0, "showall_s": 0.0,
         "showall_marks": [], "rats": [R(1, "manual"), R(2, "manual"), R(3, "manual")]},
        {"frame_id": "C", "domain": "colour", "arm": "PRELABEL", "pile_bin": "4+", "completed": False, "visited": True, "active_s": 30.0, "showall_s": 0.0,
         "showall_marks": [], "rats": [R(1, "cand", 1), R(2, None), R(3, "cand", 3, origin="added")]},
        {"frame_id": "E", "domain": "colour", "arm": "SCRATCH", "pile_bin": "1", "completed": False, "visited": False, "active_s": 0.0, "showall_s": 0.0,
         "showall_marks": [], "rats": [R(1, None)]}]}
    sm = summarize(ex)
    pa = sm["prelabel_all"]
    # PRELABEL evaluated: A1 (u1), A2 (merged on rank 1, accepted rank 2 no flag -> usable_any), A3 manual, A4 (rank 1 merged) , C1 (u1), C3 (rank 3)
    rec("summary: usable@1 = 2/6, usable@any = 4/6", abs(pa["usable1"] - 2 / 6) < 1e-12 and abs(pa["usable_any"] - 4 / 6) < 1e-12, str(pa))
    rec("summary: merged 2/6, partial 1/6, manual 1/6", abs(pa["merged"] - 2 / 6) < 1e-12 and abs(pa["partial"] - 1 / 6) < 1e-12
        and abs(pa["manual"] - 1 / 6) < 1e-12)
    rec("summary: s/rat on completed frames (PRELABEL 60/4, SCRATCH 90/3)", abs(sm["time"]["PRELABEL"]["s_per_rat"] - 15.0) < 1e-12
        and abs(sm["time"]["SCRATCH"]["s_per_rat"] - 30.0) < 1e-12, str(sm["time"]))
    rec("summary: counts (deleted 1, added 1, unboxed 2), show-all marks", sm["n_deleted"] == 1 and sm["n_added"] == 1 and sm["n_unboxed"] == 2
        and sm["showall"]["garbage"] == 1 and sm["showall"]["fragment"] == 1 and sm["showall"]["showall_s"] == 20.0)
    sp = {(r["domain"], r["pile_bin"]): r for r in sm["split"]}
    rec("summary: split by domain x pile", sp[("ir", "2-3")]["n_rats"] == 4 and sp[("colour", "4+")]["n_rats"] == 2
        and abs(sp[("ir", "2-3")]["PRELABEL_s_per_rat"] - 15.0) < 1e-12 and np.isnan(sp[("colour", "4+")]["PRELABEL_s_per_rat"]))
    qa = sm["quality_all"]
    # PRELABEL rats with a proposal: A1 (no edit, IoU 1), A2 (rank 2 -> other cand), A3 manual, A4 (rank 1, 2 edge moves -> edge only, IoU 100/120),
    # C1 (no edit), C3 (rank 3)
    rec("C2 quality: no edit 2/6, edge only 1/6 (shift 0.5 px), other candidate 2/6, manual 1/6",
        abs(qa["no_edit"] - 2 / 6) < 1e-12 and abs(qa["edge_only"] - 1 / 6) < 1e-12 and abs(qa["edge_shift_median_px"] - 0.5) < 1e-12
        and abs(qa["other_candidate"] - 2 / 6) < 1e-12 and abs(qa["manual"] - 1 / 6) < 1e-12, str(qa))
    tt = rat_table(ex)
    rec("C2 quality: IoU proposed -> final = 100/120 for the edge-only rat, median 1",
        abs(float(tt[tt.edge_only].iou_prop_final.iloc[0]) - 100 / 120) < 1e-12 and qa["iou_median"] == 1.0, str(qa))
    rec("box IoU", abs(box_iou([0, 0, 10, 10], [5, 0, 15, 10]) - 1 / 3) < 1e-12 and np.isnan(box_iou(None, [0, 0, 1, 1])))
    exr = json.loads(json.dumps(ex))
    fa = exr["frames"][1]                      # SCRATCH frame B: archive the current labels as pass 1, redo with shifted boxes
    fa["passes"] = [{"pass": 1, "rats": json.loads(json.dumps(fa["rats"])), "active_s": 90.0, "showall_s": 0.0, "completed": True, "showall_marks": []}]
    for r in fa["rats"]:
        r["box"] = [0, 0, 10, 20]
        r["u"] += 4.0
    fa["active_s"] = 50.0
    smr = summarize(exr)
    rec("repeat check: 3 pairs on 1 frame, IoU 0.5 each; main pass = the first (timing 90/3)", smr["repeat"]["n_pairs"] == 3
        and abs(smr["repeat"]["iou_median"] - 0.5) < 1e-12 and abs(smr["time"]["SCRATCH"]["s_per_rat"] - 30.0) < 1e-12, str(smr["repeat"]))
    mb = match_by_head([{"u": 0, "v": 0, "box": [0, 0, 1, 1], "id": "a"}, {"u": 50, "v": 0, "box": [0, 0, 1, 1], "id": "b"}],
                       [{"u": 3, "v": 0, "box": [0, 0, 1, 1], "id": "x"}, {"u": 80, "v": 0, "box": [0, 0, 1, 1], "id": "y"}])
    rec("head matching: nearest within 15 px, one-to-one", [(p[0]["id"], p[1]["id"]) for p in mb] == [("a", "x")])
    smm = summarize(ex, [json.loads(json.dumps(ex))])
    rec("repeat check: a second export of the same session is not a repeat (identical labels deduplicated)", smm["repeat"]["n_pairs"] == 0)
    # C3: five kept first candidates with known shifts (mask bbox 100 x 50 at (100, 100))
    def K(i, sh):
        p0 = [100.0, 100.0, 200.0, 150.0]
        return {"id": f"k{i}", "origin": "click", "deleted": False, "cand": [0], "source": "cand", "rank": 1, "prop": p0,
                "box": [p0[0] - sh[0], p0[1] - sh[2], p0[2] + sh[1], p0[3] + sh[3]], "u": 10.0 * i, "v": 0.0, "cand_flags": {}, "edge_moves": 1,
                "next_presses": 0}
    exc = {"page_version": PAGE_VERSION, "frames": [
        {"frame_id": "K", "domain": "ir", "arm": "PRELABEL", "pile_bin": "2-3", "completed": True, "visited": True, "active_s": 10.0, "showall_s": 0.0,
         "showall_marks": [], "rats": [K(i, (10, 10, 5, 5)) for i in range(4)] + [K(4, (10, 30, 5, 5))]},
        {"frame_id": "L", "domain": "ir", "arm": "SCRATCH", "pile_bin": "2-3", "completed": True, "visited": True, "active_s": 10.0, "showall_s": 0.0,
         "showall_marks": [], "rats": [{**K(9, (0, 0, 0, 0)), "source": "manual", "rank": None, "box": [0, 0, 120, 60]}]}]}
    sc = summarize(exc)["c3"]
    rec("C3: per-edge median shifts px (left 10, right 10, top 5, bottom 5) and fractions (0.1, 0.1, 0.1, 0.1)",
        [sc["all"][e]["px"]["median"] for e in EDGES] == [10, 10, 5, 5]
        and all(abs(sc["padding_rule_frac"][e] - 0.1) < 1e-12 for e in EDGES), str(sc["padding_rule_frac"]))
    rec("C3: uniform when IQRs are small", sc["uniformity"]["uniform"] is True, str(sc["uniformity"]))
    rec("C3: SCRATCH sizes vs accepted mask bboxes", sc["sizes"]["scratch"]["width_px"]["median"] == 120
        and sc["sizes"]["accepted_mask_bbox"]["width_px"]["median"] == 100)
    exc["frames"][0]["rats"] = [K(0, (0, 0, 0, 40)), K(1, (0, 0, 0, 40)), K(2, (2, 0, 1, 45)), K(3, (1, 2, 0, 35)), K(4, (0, 1, 2, 40))]
    sc2 = summarize(exc)["c3"]["uniformity"]
    rec("C3: one edge much worse (bottom) -> not uniform", sc2["one_edge_flag"] is True and sc2["worst_edge"] == "bottom" and sc2["uniform"] is False,
        str(sc2))
    md = summary_md({k: v for k, v in sm.items() if k != "_repeat_pairs"}, "synthetic.json")
    rec("summary markdown: section title, definitions, C2 quality, C3 padding proposal, the user's note", md.startswith("## B — pre-label edit pilot (dev)")
        and "usable@any" in md and "IoU proposed → final" in md and "Proposed padding rule" in md and "boxes include the head" in md)
    with tempfile.TemporaryDirectory() as td:
        run = Path(td)
        (run / "prelabel_edit").mkdir()
        p = run / "ex.json"
        p.write_text(json.dumps(ex), encoding="utf-8")
        out = write_summary(run, p, regenerate_report=False)
        rec("write_summary: fragment + json written (report not touched in the selftest)", out.exists() and (run / "prelabel_edit" / "summary_B.json").exists())
    # ---------------- v2 (implant box + rat box)
    if node:
        with tempfile.TemporaryDirectory() as td:
            js = Path(td) / "pl2.js"
            js.write_text(PAGE_JS_V2, encoding="utf-8")
            r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
            rec("v2 page script parses (node --check)", r.returncode == 0, r.stderr[-300:])
    h2 = page_html_v2("x")
    rec("v2 page: no network URL, data in a sibling .js, both object names", not re.search(r"https?://", h2) and '<script src="pl_data.js">' in h2
        and "IMPLANT" in h2 and "RAT" in h2)

    def O(src, rank=None, prop=(0, 0, 10, 10), box=None, hidden=False, flags=None, t=10.0, click=None, edges=0, ncand=2):
        return {"cand": list(range(ncand)), "k": 0, "prop": list(prop) if prop else None, "box": box if box is not None else ((list(prop) if prop else [0, 0, 10, 10]) if src else None),
                "source": src, "rank": rank, "mask": 0 if src == "cand" else None, "cand_flags": {str(a): b for a, b in (flags or {}).items()},
                "edge_moves": edges, "next_presses": 0, "time_ms": t * 1000, "hidden": hidden, "click": click, "clicks": [click] if click else []}

    def RR(i, imp, rt, origin="click", deleted=False):
        return {"id": f"h{i}", "num": i, "origin": origin, "click_id": f"c{i}", "u": 100.0 * i, "v": 50.0, "deleted": deleted, "implant": imp, "rat": rt}
    ex2 = {"page_version": PAGE_VERSION_V2, "definition_note": "", "frames": [
        {"frame_id": "P", "domain": "ir", "arm": "PRELABEL", "pile_bin": "2-3", "completed": True, "visited": True, "active_s": 100.0, "showall_s": 0.0,
         "showall_marks": [], "passes": [], "rats": [
             RR(1, O("cand", 1, t=4), O("cand", 1, prop=(0, 0, 100, 50), box=[-10, -5, 110, 55], click=[5, 5], t=6, edges=2)),
             RR(2, O("cand", 2, t=5), O("cand", 1, prop=(0, 0, 100, 50), flags={1: {"merged": True}}, click=[5, 5], t=8)),
             RR(3, O(None, hidden=True, t=1), O("manual", None, prop=(0, 0, 100, 50), box=[0, 0, 90, 40], click=[5, 5], t=12)),
             RR(4, O("manual", None, prop=None, ncand=0, t=7), O("cand", 2, prop=(0, 0, 100, 50), click=[5, 5], t=9))]},
        {"frame_id": "Q", "domain": "ir", "arm": "SCRATCH", "pile_bin": "2-3", "completed": True, "visited": True, "active_s": 60.0, "showall_s": 0.0,
         "showall_marks": [], "passes": [], "rats": [
             RR(1, O("manual", None, prop=None, box=[0, 0, 12, 12], t=6), O("manual", None, prop=None, box=[0, 0, 120, 60], t=14)),
             RR(2, O(None, hidden=True, prop=None, t=2), O("manual", None, prop=None, box=[0, 0, 110, 60], t=16))]}]}
    sv = summarize_v2(ex2)
    oi, orr = sv["objects"]["implant"], sv["objects"]["rat"]
    # implant PRELABEL boxed: h1 (rank 1), h2 (rank 2), h4 (manual) -> usable@1 1/3, usable@any 2/3, manual 1/3
    rec("v2 implant: usable@1 1/3, usable@any 2/3, manual 1/3", abs(oi["usable1"] - 1 / 3) < 1e-12 and abs(oi["usable_any"] - 2 / 3) < 1e-12
        and abs(oi["manual"] - 1 / 3) < 1e-12, str({k: oi[k] for k in ("usable1", "usable_any", "manual")}))
    # rat PRELABEL boxed: h1 rank 1 (edges), h2 rank 1 merged, h3 manual, h4 rank 2 -> usable@1 1/4, usable@any 2/4, merged 1/4, manual 1/4
    rec("v2 rat: usable@1 1/4, usable@any 2/4, merged 1/4, manual 1/4", abs(orr["usable1"] - 0.25) < 1e-12 and abs(orr["usable_any"] - 0.5) < 1e-12
        and abs(orr["merged"] - 0.25) < 1e-12 and abs(orr["manual"] - 0.25) < 1e-12, str({k: orr[k] for k in ("usable1", "usable_any", "merged", "manual")}))
    rec("v2 implant hidden: PRELABEL 1/4, SCRATCH 1/2, all 2/6", abs(sv["hidden"]["PRELABEL"] - 0.25) < 1e-12 and abs(sv["hidden"]["SCRATCH"] - 0.5) < 1e-12
        and abs(sv["hidden"]["all"] - 2 / 6) < 1e-12, str(sv["hidden"]))
    rec("v2 seconds per box: implant PRELABEL 16/3, SCRATCH 6/1; rat PRELABEL 35/4, SCRATCH 30/2",
        abs(oi["time"]["PRELABEL"]["s_per_object"] - 16 / 3) < 1e-9 and abs(oi["time"]["SCRATCH"]["s_per_object"] - 6.0) < 1e-9
        and abs(orr["time"]["PRELABEL"]["s_per_object"] - 35 / 4) < 1e-9 and abs(orr["time"]["SCRATCH"]["s_per_object"] - 15.0) < 1e-9,
        str((oi["time"], orr["time"])))
    rec("v2 rat C3: kept first candidates h1 (+10 / +10 / +5 / +5 px) and h2 (0) -> medians +5 / +5 / +2.5 / +2.5 px, fraction +5 %",
        [orr["c3"]["edges"][e]["px"]["median"] for e in EDGES] == [5.0, 5.0, 2.5, 2.5] and abs(orr["c3"]["padding_rule_frac"]["left"] - 0.05) < 1e-12,
        str(orr["c3"]["padding_rule_frac"]))
    rec("v2 rat sizes: SCRATCH width median 115 vs accepted mask bboxes 100", orr["sizes"]["scratch"]["width_px"]["median"] == 115
        and orr["sizes"]["accepted_mask_bbox"]["width_px"]["median"] == 100)
    ex3 = json.loads(json.dumps(ex2))
    fq = ex3["frames"][1]
    fq["passes"] = [{"pass": 1, "rats": json.loads(json.dumps(fq["rats"])), "active_s": 60.0, "showall_s": 0.0, "completed": True, "showall_marks": []}]
    fq["rats"][0]["rat"]["box"] = [0, 0, 120, 120]
    fq["rats"][0]["implant"]["box"] = [0, 0, 12, 24]
    sv3 = summarize_v2(ex3)
    rec("v2 repeat per object: rat 2 pairs (IoU 0.5, 1), implant 1 pair (IoU 0.5; hidden excluded)", sv3["repeat"]["rat"]["n_pairs"] == 2
        and abs(sv3["repeat"]["rat"]["iou_median"] - 0.75) < 1e-12 and sv3["repeat"]["implant"]["n_pairs"] == 1
        and abs(sv3["repeat"]["implant"]["iou_median"] - 0.5) < 1e-12, str(sv3["repeat"]))
    md2 = summary_md_v2(sv, "synthetic_v2.json")
    rec("v2 summary markdown: per-object sections, padding proposal, implant hidden", "### Implant box" in md2 and "### Rat box" in md2
        and "Proposed padding rule" in md2 and "Implant hidden" in md2)
    with tempfile.TemporaryDirectory() as td:
        run = Path(td)
        pp = run / "ex2.json"
        pp.write_text(json.dumps(ex2), encoding="utf-8")
        out2 = write_summary(run, pp, regenerate_report=False)
        rec("v2 write_summary -> prelabel_edit_v2/summary_B.md", out2 == run / "prelabel_edit_v2" / "summary_B.md" and out2.exists())
    print("SELFTEST", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", nargs="?", choices=["build", "summarize"])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--run", type=Path, default=RUN_DEFAULT)
    ap.add_argument("--export", type=Path)
    ap.add_argument("--more-exports", type=Path, nargs="*", default=[], help="exports from other labelling sessions (repeat check only)")
    ap.add_argument("--no-page-check", action="store_true")
    ap.add_argument("--v2", action="store_true", help="build the v2 page (implant box + rat box, amendments B1 / B1a) into <run>/prelabel_edit_v2")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "build" and a.v2:
        m = build_v2(a.run, check=not a.no_page_check)
        print(json.dumps({k: m[k] for k in ("n_prelabel", "n_scratch", "arms_identical_to_v1", "frames_hard_linked", "size")}, indent=1))
        return 0
    if a.cmd == "build":
        m = build(a.run, check=not a.no_page_check)
        print(json.dumps({k: m[k] for k in ("n_prelabel", "n_scratch", "n_heads", "heads_with_0_candidates", "size")}, indent=1))
        return 0
    if a.cmd == "summarize":
        if not a.export:
            ap.error("summarize needs --export")
        print(f"summary: {write_summary(a.run, a.export, more=a.more_exports)}")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
