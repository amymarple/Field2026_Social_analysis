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
  python cv/cv_field/inbox_prelabel_edit.py update-v21 [--run <SAM 3 run>]                        # v2 -> v2.1 IN PLACE (amendment B2:
         J joins pieces); same storage key, backups *.v2_0.bak, payload verified identical, old-state load test
  python cv/cv_field/inbox_prelabel_edit.py update-v22 [--run <SAM 3 run>]                        # v2.1 -> v2.2 IN PLACE (UX: a click
         switches to the rat box, mode banner, toasts saying why a key cannot act, legend); backups *.v2_1.bak, old-state test
  python cv/cv_field/inbox_prelabel_edit.py update-v23 [--run <SAM 3 run>]                        # v2.2 -> v2.3 IN PLACE (two sticky
         modes IMPLANT / RAT — buttons, 1 / 2, Tab — no auto-switch; rat chips, white-dot select, Enter / ← next / previous
         rat); backups *.v2_2.bak, old-state test
  python cv/cv_field/inbox_prelabel_edit.py update-v24 [--run <SAM 3 run>]                        # v2.3 -> v2.4 IN PLACE (right-side
         mask panel: × remove / + join / hover; drag handles; a drag on the candidate bbox accepts it; status split into
         Box / Last click); backups *.v2_3.bak, old-state test
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
    t["joined"] = t.source == "joined"
    t["usable_any_join"] = t.source.isin(["cand", "joined"]) & ~t.acc_merged & ~t.acc_partial
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
            "joined": d.joined.mean() if (n and "joined" in d) else np.nan,
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
    v2s = (PAGE_VERSION_V2, PAGE_VERSION_V21, PAGE_VERSION_V22, PAGE_VERSION_V23, PAGE_VERSION_V24)
    if ver not in (PAGE_VERSION,) + v2s or any((x.get("page_version") in v2s) != (ver in v2s) for x in exs):
        raise SystemExit(f"not exports of one page version: {[x.get('page_version') for x in exs]}")
    meta = {"export": Path(export).as_posix(), "more_exports": [Path(m).as_posix() for m in (more or [])], "made": datetime.now().isoformat(timespec="seconds")}
    if ver in v2s:
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
                cf = dict(o.get("cand_flags") or {})
                of = o.get("obj_flags") or {}
                acc = cf.get(str(o.get("rank")), {}) if o.get("rank") else (of if o.get("source") == "joined" else {})
                if of:
                    cf["obj"] = of
                pcs = o.get("pieces")
                npc = len(pcs) if isinstance(pcs, list) else (1 if o.get("source") == "cand" else 0)
                rows.append({"frame_id": f0["frame_id"], "domain": f0["domain"], "arm": f0["arm"], "pile_bin": f0["pile_bin"],
                             "n_pieces": npc, "union_box": o.get("union_box"),
                             "completed": bool(mp["completed"]), "rat_id": r["id"], "origin": r["origin"], "deleted": bool(r["deleted"]),
                             "object": k, "hidden": bool(o.get("hidden")) if k == "implant" else False, "n_cand": len(o.get("cand") or []),
                             "source": o.get("source") or "", "rank": o.get("rank"), "boxed": o.get("box") is not None,
                             "acc_merged": bool(acc.get("merged")), "acc_partial": bool(acc.get("partial")),
                             "any_merged": any(bool((v or {}).get("merged")) for v in cf.values()),
                             "any_partial": any(bool((v or {}).get("partial")) for v in cf.values()),
                             "edge_moves": int(o.get("edge_moves") or 0), "next_presses": int(o.get("next_presses") or 0),
                             "prop": o.get("prop"), "box": o.get("box"), "time_s": float(o.get("time_ms") or 0) / 1000.0,
                             "has_click": o.get("click") is not None, "u": r["u"], "v": r["v"], "pass": mp.get("pass", 1),
                             "cand_src": o.get("cand_src") or ("click" if k == "rat" else "head")})
    t = pd.DataFrame(rows)
    return derive(t) if len(t) else t


def obj_block_v2(d: pd.DataFrame) -> dict:
    """Per object type on its evaluated objects (not deleted, boxed), PRELABEL arm."""
    pre = d[d.arm == "PRELABEL"]
    n = len(pre)
    c3 = c3_table(d) if len(d) else pd.DataFrame()
    cb = c3_block(c3)
    jt = pre[(pre.source == "joined") & pre.union_box.notna() & pre.box.notna()] if n else pre
    cu = c3_block(pd.DataFrame([{**r, **edge_shifts(r["union_box"], r["box"])} for r in jt.to_dict("records")])) if len(jt) else c3_block(pd.DataFrame())
    npc = pre.n_pieces.clip(upper=4) if n else pd.Series(dtype=int)
    return {"n_prelabel": n, "usable1": pre.usable1.mean() if n else np.nan, "usable_any": pre.usable_any.mean() if n else np.nan,
            "usable_any_join": pre.usable_any_join.mean() if n else np.nan, "joined": pre.joined.mean() if n else np.nan,
            "n_pieces_dist": {("4+" if k == 4 else str(int(k))): int(v) for k, v in npc.value_counts().sort_index().items()},
            "union_shift": {"n": int(len(jt)), "edges": cu},
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
        pd_ = d[(d.arm == "PRELABEL") & d.frame_id.isin(done)] if len(d) else d
        by_src = {src: {"n": int((pd_.source == src).sum()), "s_per_object": float(pd_[pd_.source == src].time_s.mean()) if (pd_.source == src).any() else np.nan}
                  for src in ("cand", "joined", "manual")} if len(d) else {}
        out["objects"][k] = {**(obj_block_v2(d) if len(d) else {"n_prelabel": 0}), "time": ({a: secs(d, a) for a in ("PRELABEL", "SCRATCH")} if len(d) else {}),
                             "time_by_source": by_src,
                             "from_click": int((d[d.arm == "PRELABEL"].cand_src == "click").sum()) if len(d) and "cand_src" in d else 0,
                             "sizes": {"scratch": size_block(d[d.arm == "SCRATCH"].box) if len(d) else size_block([]),
                                       "accepted_mask_bbox": size_block([m for m in d[(d.arm == "PRELABEL") & (d.source == "cand")].prop]) if len(d) else size_block([])}}
        for dom in ("ir", "colour"):
            for b in PILE_BINS:
                x = d[(d.domain == dom) & (d.pile_bin == b)] if len(d) else d
                lx = live[(live.domain == dom) & (live.pile_bin == b)] if len(live) else live
                row = {"object": k, "domain": dom, "pile_bin": b}
                if len(x):
                    bl = obj_block_v2(x)
                    row.update({kk: bl[kk] for kk in ("n_prelabel", "usable1", "usable_any", "usable_any_join", "joined", "manual", "merged", "partial")})
                    row["n_pieces_dist"] = bl["n_pieces_dist"]
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
              f"- **usable@any as a single mask {S.pct(o['usable_any'])}; with joins {S.pct(o.get('usable_any_join', np.nan))}** (joined boxes "
              f"{S.pct(o.get('joined', np.nan))}); pieces per box: " + ", ".join(f"{kk}: {vv}" for kk, vv in (o.get("n_pieces_dist") or {}).items()) + ";",
              f"- IoU proposed (first candidate of the first click) → final: median {fx(q['iou_median'], 3)} [quartiles {fx(q['iou_q25'], 3)}, {fx(q['iou_q75'], 3)}];",
              f"- no edit {S.pct(q['no_edit'])}; edge moves only {S.pct(q['edge_only'])} (median edge shift "
              f"{fx(q['edge_shift_median_px'])} px); another candidate {S.pct(q['other_candidate'])}.",
              f"- Seconds per box (per-object time slices, completed frames): PRELABEL {fx(tp.get('s_per_object', np.nan))} s "
              f"(n {tp.get('n', 0)}), SCRATCH {fx(ts.get('s_per_object', np.nan))} s (n {ts.get('n', 0)}); PRELABEL by source: "
              + ", ".join(f"{src} {fx(v['s_per_object'])} s (n {v['n']})" for src, v in (o.get("time_by_source") or {}).items()) + ".", ""]
        if k == "implant" and o.get("from_click"):
            L += [f"Implant boxes whose candidates came from a click in IMPLANT mode (page v2.3), not from the head dot: {o['from_click']} — "
                  "their rank refers to the click's candidate list, so usable@1 mixes two candidate sources.", ""]
        us = o.get("union_shift") or {}
        if us.get("n"):
            L += [f"Joined boxes ({us['n']}): per-edge shift from the union box (before edge drags) to the final box, px median [q25, q75]: "
                  + ", ".join(f"{e} {us['edges'][e]['px']['median']:+.0f} [{us['edges'][e]['px']['q25']:+.0f}, {us['edges'][e]['px']['q75']:+.0f}]" for e in EDGES) + ".", ""]

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
                 "usable@any single": S.pct(r.get("usable_any", np.nan)), "usable@any with joins": S.pct(r.get("usable_any_join", np.nan)),
                 "joined": S.pct(r.get("joined", np.nan)), "manual": S.pct(r.get("manual", np.nan)),
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
          "- **usable@1 / usable@any:** per object type, as in v1. Merged / partial flags apply to the rat box only; on a joined box they "
          "apply to the whole box.",
          "- **Joined box (v2.1, amendment B2):** the union bounding box of ≥ 2 SAM 3 masks the user joined with J. **usable@any with "
          "joins** = the share whose final box came from one candidate or a join, with no flag; **usable@any as a single mask** counts "
          "single candidates only. **Pieces per box** = the number of masks used (0 = drawn by hand).",
          "- **Proposed box** = the first candidate of the first body click (implant: of the head point). For rat boxes labelled in "
          "v2.0 with more than one body click, the stored proposal is the latest click's (v2.0 rule; `prop_rule` = latest_click_v2.0).",
          "- **IoU proposed → final**, **edge shifts**, **padding rule**, **uniformity flag:** as in v1 (C2 / C3), per object type.",
          "- **Seconds per box** = the object's active time slice (the clock runs for the active box only; it pauses when the tab "
          "is hidden or after 45 s without input), mean over the boxed objects on completed frames.",
          "- **Repeat check** per object type: rats paired by head point within 15 px, IoU of the two final boxes (hidden implants "
          "excluded).", ""]
    return "\n".join(L)


PAGE_JS_V21 = r"""
(function(){
const D = window.PL_DATA;
const KEY = D.storage_key || (D.page_version + '::' + D.run);          // v2.1 keeps the v2 storage key: the user's progress is kept
const $ = id => document.getElementById(id);
const iso = () => new Date().toISOString();
const OBJ_NAME = {implant: 'IMPLANT box', rat: 'RAT box'};
function newObj(f, cand, hidden){ return {cand: cand, k: 0, prop: cand.length ? f.masks[cand[0]].b.slice() : null, box: null, source: null, rank: null,
  mask: null, cand_flags: {}, edge_moves: 0, next_presses: 0, time_ms: 0, hidden: !!hidden, click: null, clicks: [],
  pieces: [], union_box: null, obj_flags: {}, prop_rule: 'first_click'}; }
function initFrame(f){ return {arm: f.arm, active_ms: 0, showall_ms: 0, completed: false, visited: false, next_add: 1, marks: {}, passes: [],
  rats: f.heads.map((h, i) => ({id: 'h' + (i + 1), num: i + 1, origin: 'click', click_id: h.c, u: h.u, v: h.v, deleted: false,
    implant: newObj(f, f.cand[i], false), rat: newObj(f, [], false)}))}; }
function fresh(){ const fr = {}; D.frames.forEach(f => fr[f.id] = initFrame(f));
  return {v: 2, schema: '2.1', started_at: iso(), defnote: '', cur: {fi: 0, ri: 0, obj: 'implant'}, frames: fr, events: []}; }
// ---------------------------------------------------------------- lazy migration v2.0 -> v2.1 (adds fields, never rewrites a v2.0 value)
function migObj(f, o, kind){ if (!o) return; let ch = false;
  if (!Array.isArray(o.pieces)) { o.pieces = (o.source === 'cand' && o.mask !== null && o.mask !== undefined) ? [{mask: o.mask, rank: o.rank, click: kind === 'rat' ? (o.click || null) : null}] : []; ch = true; }
  if (o.union_box === undefined) { o.union_box = (o.source === 'cand' && o.mask !== null && o.mask !== undefined && f.masks[o.mask]) ? f.masks[o.mask].b.slice() : null; ch = true; }
  if (!o.obj_flags) { o.obj_flags = {}; ch = true; }
  if (!o.prop_rule) { o.prop_rule = (kind === 'rat' && (o.clicks || []).length > 1) ? 'latest_click_v2.0' : 'first_click'; ch = true; }
  if (!Array.isArray(o.clicks)) { o.clicks = []; ch = true; }
  return ch; }
function migrate(st0){ let n = 0; D.frames.forEach(f => { const s = st0.frames[f.id]; if (!s) return;
  const all = [s.rats].concat((s.passes || []).map(p => p.rats)); all.forEach(rs => (rs || []).forEach(r => { if (migObj(f, r.implant, 'implant')) n++; if (migObj(f, r.rat, 'rat')) n++; })); });
  if (st0.schema !== '2.1') { st0.schema = '2.1'; st0.migrated_v21_at = iso(); st0.migrated_v21_objects = n; } return st0; }
function load(){ try { const t = localStorage.getItem(KEY); if (t) { const o = JSON.parse(t); if (o && o.frames && o.v === 2) return migrate(o); } } catch (e) {} return null; }
let saveT = null;
function save(now){ const f = () => { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { $('banner').textContent = 'could not save to this browser: export now'; } };
  if (now) { f(); return; } clearTimeout(saveT); saveT = setTimeout(f, 250); }
let S = load() || fresh();
const fr = () => D.frames[S.cur.fi], st = () => S.frames[fr().id], rats = () => st().rats;
const liveIdx = () => rats().map((r, i) => i).filter(i => !rats()[i].deleted);
const rat = () => rats()[S.cur.ri];
const obj = () => { const r = rat(); return r ? r[S.cur.obj] : null; };
function log(ev, extra){ const r = rat(); S.events.push(Object.assign({t: iso(), frame: fr().id, arm: st().arm, rat: r ? r.id : null, obj: S.cur.obj, ev: ev}, extra || {})); save(); }
let toastT = null;
function toast(msg){ const el = $('toast'); el.textContent = msg; el.style.display = 'block'; clearTimeout(toastT); toastT = setTimeout(() => { el.style.display = 'none'; }, 3500); }
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
function unionBox(pieces){ const f = fr(); let b = null; pieces.forEach(p => { const m = f.masks[p.mask].b;
  b = b ? [Math.min(b[0], m[0]), Math.min(b[1], m[1]), Math.max(b[2], m[2]), Math.max(b[3], m[3])] : m.slice(); }); return b; }
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
    const r = rat();
    if (r && !r.deleted) ['implant', 'rat'].forEach(k => (r[k].pieces || []).forEach(pc => { const m = f.masks[pc.mask]; if (!m) return;
      m.p.forEach(p => { const P = polyPath(p); ctx.globalAlpha = 0.12; ctx.fillStyle = STYLE[k].box; ctx.fill(P); ctx.globalAlpha = 1;
        ctx.lineWidth = 1.8 * lw; ctx.strokeStyle = STYLE[k].box; ctx.stroke(P); }); }));
    const c = curCand();
    if (c !== null) { const m = f.masks[c], col = STYLE[S.cur.obj].cand; ctx.setLineDash([7 * lw, 5 * lw]);
      m.p.forEach(p => { const P = polyPath(p); ctx.globalAlpha = 0.12; ctx.fillStyle = col; ctx.fill(P); ctx.globalAlpha = 1; ctx.lineWidth = 2.5 * lw; ctx.strokeStyle = col; ctx.stroke(P); });
      drawnMasks = 1; ctx.lineWidth = 2 * lw; ctx.strokeStyle = '#ffd400'; ctx.strokeRect(m.b[0], m.b[1], m.b[2] - m.b[0], m.b[3] - m.b[1]); ctx.setLineDash([]); }
  }
  s.rats.forEach((r, i) => { if (r.deleted) return; const cur = i === S.cur.ri;
    ['rat', 'implant'].forEach(k => { const b = r[k].box; if (!b) return; const act = cur && S.cur.obj === k;
      ctx.globalAlpha = cur ? 1 : 0.4; ctx.lineWidth = (act ? 3 : cur ? 1.8 : 1.3) * lw; ctx.strokeStyle = STYLE[k].box;
      if (k === 'implant') ctx.setLineDash([4 * lw, 3 * lw]); ctx.strokeRect(b[0], b[1], b[2] - b[0], b[3] - b[1]); ctx.setLineDash([]); ctx.globalAlpha = 1; });
    if (cur) (r.rat.clicks || []).forEach((cl, n) => { const R = 8 * lw; ctx.lineWidth = 2.5 * lw; ctx.strokeStyle = STYLE.rat.cand; ctx.globalAlpha = n === r.rat.clicks.length - 1 ? 1 : 0.5;
      ctx.beginPath(); ctx.moveTo(cl[0] - R, cl[1]); ctx.lineTo(cl[0] + R, cl[1]); ctx.moveTo(cl[0], cl[1] - R); ctx.lineTo(cl[0], cl[1] + R); ctx.stroke(); ctx.globalAlpha = 1; }); });
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
  if (pre) { if (k === 'rat' && !o.click) t = 'click the rat\'s body'; else if (o.cand.length === 0) t = 'no candidate here — click another part, or draw (B)';
    else t = o.k < o.cand.length ? 'candidate ' + (o.k + 1) + ' / ' + o.cand.length + ((o.pieces || []).some(p => p.mask === o.cand[o.k]) ? ' (joined)' : '') : 'none usable — draw (B)'; }
  else t = 'draw by hand (drag)';
  if (o.box) t += ' · box: ' + (o.source === 'manual' ? 'manual' : o.source === 'joined' ? 'joined ' + o.pieces.length + ' pieces' : 'candidate ' + o.rank)
    + (o.edge_moves ? ', ' + o.edge_moves + ' edge move(s)' : '');
  const fl = o.source === 'joined' ? (o.obj_flags || {}) : (pre && o.k < o.cand.length ? (o.cand_flags[o.k + 1] || {}) : {});
  if (k === 'rat' && (fl.merged || fl.partial)) t += ' · flagged ' + [fl.merged ? 'merged' : '', fl.partial ? 'partial' : ''].filter(Boolean).join(' + ');
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
  const had = (o.pieces || []).length; if (had > 1 || (had === 1 && o.pieces[0].mask !== c)) toast('replaced ' + had + ' joined piece(s) with this one mask (U undoes)');
  o.pieces = [{mask: c, rank: o.k + 1, click: S.cur.obj === 'rat' ? o.click : null}]; o.union_box = m.b.slice(); o.obj_flags = {};
  o.box = m.b.slice(); o.source = 'cand'; o.rank = o.k + 1; o.mask = c;
  log('accept', {rank: o.rank, mask: c, mask_score: m.s, box: o.box, flags: o.cand_flags[o.rank] || {}, click: S.cur.obj === 'rat' ? o.click : undefined, replaced_pieces: had}); draw(); }
function join(){ const o = obj(), c = curCand(); if (!o || c === null) return;
  if ((o.pieces || []).some(p => p.mask === c)) { toast('this piece is already joined'); return; }
  snap(); const m = fr().masks[c];
  if (o.source === 'manual' || !o.pieces) { if (o.source === 'manual') toast('the hand-drawn box is replaced by the joined pieces (U undoes)'); o.pieces = []; }
  o.pieces.push({mask: c, rank: o.k + 1, click: S.cur.obj === 'rat' ? o.click : null});
  o.box = unionBox(o.pieces); o.union_box = o.box.slice();
  if (o.pieces.length >= 2) { o.source = 'joined'; o.rank = null; o.mask = null; } else { o.source = 'cand'; o.rank = o.k + 1; o.mask = c; }
  log('join', {mask: c, rank: o.k + 1, mask_score: m.s, click: S.cur.obj === 'rat' ? o.click : undefined, n_pieces: o.pieces.length, box: o.box}); draw(); }
function next(){ const o = obj(), r = rat(); if (!o || !r || r.deleted || st().arm !== 'PRELABEL' || showAll) return; if (S.cur.obj === 'implant' && o.hidden) return;
  if (S.cur.obj === 'rat' && !o.click) return; snap(); o.k = o.k < o.cand.length ? o.k + 1 : 0; o.next_presses++;
  log('next', {to: o.k < o.cand.length ? o.k + 1 : 'none'}); draw(); }
function flag(kind){ if (S.cur.obj !== 'rat') return; const o = obj(); if (!o) return;
  if (o.source === 'joined') { snap(); o.obj_flags = o.obj_flags || {}; o.obj_flags[kind] = !o.obj_flags[kind]; log('flag', {object_level: true, flag: kind, value: o.obj_flags[kind], n_pieces: o.pieces.length}); draw(); return; }
  if (curCand() === null) return; snap(); const fl = o.cand_flags[o.k + 1] = o.cand_flags[o.k + 1] || {}; fl[kind] = !fl[kind];
  log('flag', {rank: o.k + 1, flag: kind, value: fl[kind]}); draw(); }
function setManual(b){ const r = rat(), o = obj(); if (!r || r.deleted || !o) return; snap(); o.box = b.map(x => Math.round(x * 10) / 10); o.source = 'manual'; o.rank = null; o.mask = null;
  o.pieces = []; o.union_box = null; o.obj_flags = {}; if (S.cur.obj === 'implant') o.hidden = false; log('manual_box', {box: o.box}); mode = null; draw(); }
function fitToMask(){ const r = rat(), o = obj(); if (!r || r.deleted || !o || !(o.pieces || []).length || o.source === 'manual') return; const b = unionBox(o.pieces);
  if (o.box && o.box.every((x, i) => x === b[i])) return; snap(); const from = o.box; o.box = b.slice(); log('fit_to_mask', {from: from, to: o.box, rank: o.rank, n_pieces: o.pieces.length}); draw(); }
function hideImplant(){ const r = rat(); if (!r || r.deleted) return; snap(); const o = r.implant; o.hidden = !o.hidden;
  if (o.hidden) { o.box = null; o.source = null; o.rank = null; o.mask = null; o.pieces = []; o.union_box = null; o.obj_flags = {}; if (S.cur.obj === 'implant') S.cur.obj = 'rat'; }
  log('implant_hidden', {value: o.hidden}); draw(); }
function bodyClick(u, v){ const r = rat(); if (!r || r.deleted) return; snap(); const o = r.rat, f = fr(); o.click = [Math.round(u * 10) / 10, Math.round(v * 10) / 10];
  o.clicks.push(o.click.slice()); o.cand = candidatesAt(u, v); o.k = 0;
  if (!o.prop && o.cand.length) { o.prop = f.masks[o.cand[0]].b.slice(); o.prop_rule = 'first_click'; }       // C2 / C3: the first candidate of the first click
  log('body_click', {u: o.click[0], v: o.click[1], n_cand: o.cand.length, n_click: o.clicks.length}); draw(); }
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
  if (k === 'a' && pre) accept(); else if (k === 'j' && pre) join(); else if (k === 'n' && pre) next(); else if (k === 'm' && pre) flag('merged'); else if (k === 'p' && pre) flag('partial');
  else if (k === 'h') hideImplant();
  else if (k === 'b') { if (S.cur.obj === 'implant' && rat() && rat().implant.hidden) rat().implant.hidden = false; mode = mode === 'draw' ? null : 'draw'; log('draw_mode', {on: mode === 'draw'}); draw(); }
  else if (k === 'r') { mode = mode === 'add' ? null : 'add'; log('add_mode', {on: mode === 'add'}); draw(); }
  else if (k === 'x') delDot();
  else if (k === 'f') fitToMask(); });
// ---------------------------------------------------------------- export / import
function objOut(f, o){ return Object.assign({}, o, {mask_cache_index: o.mask === null || o.mask === undefined ? null : f.masks[o.mask].i,
  mask_score: o.mask === null || o.mask === undefined ? null : f.masks[o.mask].s, n_pieces: (o.pieces || []).length,
  pieces: (o.pieces || []).map(p => Object.assign({}, p, {mask_cache_index: f.masks[p.mask].i, mask_score: f.masks[p.mask].s})),
  cand_cache_index: o.cand.map(j => f.masks[j].i), cand_scores: o.cand.map(j => f.masks[j].s)}); }
function ratOut(f, r){ return Object.assign({}, r, {implant: objOut(f, r.implant), rat: objOut(f, r.rat)}); }
function marksOut(f, mk){ return Object.entries(mk || {}).map(([j, m]) => ({mask: +j, mask_cache_index: f.masks[+j].i, mask_score: f.masks[+j].s, mark: m})); }
function exportJSON(){ return {page_version: D.page_version, schema: '2.1', storage_key: KEY, run: D.run, plan: D.plan, seed: D.seed, exported_at: iso(),
  started_at: S.started_at, migrated_v21_at: S.migrated_v21_at || null, migrated_v21_objects: S.migrated_v21_objects || 0,
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
  passes.forEach(ps => ps.rats.forEach(r => ['implant', 'rat'].forEach(k => { const o = r[k], fl = o.rank ? (o.cand_flags[o.rank] || {}) : (o.source === 'joined' ? (o.obj_flags || {}) : {});
    const any = q => Object.values(o.cand_flags).some(x => x && x[q]) || !!(o.obj_flags || {})[q];
    const ub = o.union_box;
    out.push({frame_id: f.id, pass: ps.n, domain: f.domain, arm: s.arm, pile_bin: f.pile_bin, frame_order: f.order, rat_id: r.id, origin: r.origin,
      click_id: r.click_id || '', head_u: r.u, head_v: r.v, deleted: r.deleted, object: k, hidden: k === 'implant' ? o.hidden : '',
      body_click_u: o.click ? o.click[0] : '', body_click_v: o.click ? o.click[1] : '', n_body_clicks: (o.clicks || []).length, n_candidates: o.cand.length,
      source: o.source || '', rank: o.rank || '', n_pieces: (o.pieces || []).length, pieces_cache_index: (o.pieces || []).map(p => f.masks[p.mask].i).join(';'),
      mask_index: o.mask === null || o.mask === undefined ? '' : o.mask, mask_cache_index: o.mask === null || o.mask === undefined ? '' : f.masks[o.mask].i,
      mask_score: o.mask === null || o.mask === undefined ? '' : f.masks[o.mask].s,
      box_x0: o.box ? o.box[0] : '', box_y0: o.box ? o.box[1] : '', box_x1: o.box ? o.box[2] : '', box_y1: o.box ? o.box[3] : '',
      union_x0: ub ? ub[0] : '', union_y0: ub ? ub[1] : '', union_x1: ub ? ub[2] : '', union_y1: ub ? ub[3] : '',
      prop_x0: o.prop ? o.prop[0] : '', prop_y0: o.prop ? o.prop[1] : '', prop_x1: o.prop ? o.prop[2] : '', prop_y1: o.prop ? o.prop[3] : '', prop_rule: o.prop_rule || '',
      flag_merged: !!fl.merged, flag_partial: !!fl.partial, any_merged: any('merged'), any_partial: any('partial'), edge_moves: o.edge_moves,
      next_presses: o.next_presses, object_s: +(o.time_ms / 1000).toFixed(2), frame_active_s: +(ps.active_ms / 1000).toFixed(2),
      frame_showall_s: +(ps.showall_ms / 1000).toFixed(2), frame_completed: ps.completed}); }))); }); return out; }
function csvCell(v){ v = String(v == null ? '' : v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
function exportCSV(){ const rs = rows(); const cols = Object.keys(rs[0] || {frame_id: ''}); return [cols.join(',')].concat(rs.map(r => cols.map(c => csvCell(r[c])).join(','))).join('\n') + '\n'; }
function stamp(){ const d = new Date(), p = n => String(n).padStart(2, '0'); return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + '_' + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds()); }
function download(name, text, type){ const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], {type})); a.download = name;
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); }
function strip(r){ const q = JSON.parse(JSON.stringify(r)); ['implant', 'rat'].forEach(k => { ['mask_cache_index', 'mask_score', 'cand_cache_index', 'cand_scores', 'n_pieces'].forEach(x => delete q[k][x]);
  (q[k].pieces || []).forEach(p => { delete p.mask_cache_index; delete p.mask_score; }); }); return q; }
$('ej').addEventListener('click', () => { log('export'); download(D.export_prefix + stamp() + '.json', JSON.stringify(exportJSON()), 'application/json'); });
$('ec').addEventListener('click', () => download(D.export_prefix + stamp() + '.csv', exportCSV(), 'text/csv'));
$('ij').addEventListener('change', e => { const f = e.target.files[0]; if (!f) return; f.text().then(t => { const o = JSON.parse(t);
  if (!o.frames || o.run !== D.run || !(D.accept_versions || [D.page_version]).includes(o.page_version)) { alert('not a v2 / v2.1 export of this page'); return; }
  o.frames.forEach(x => { if (!S.frames[x.frame_id]) return; const s = S.frames[x.frame_id]; s.active_ms = x.active_s * 1000; s.showall_ms = x.showall_s * 1000;
    s.visited = x.visited; s.completed = x.completed; s.rats = x.rats.map(strip); s.marks = {}; (x.showall_marks || []).forEach(m => s.marks[m.mask] = m.mark);
    s.next_add = 1 + s.rats.filter(r => r.origin === 'added').length;
    s.passes = (x.passes || []).map(ps => { const mk = {}; (ps.showall_marks || []).forEach(m => mk[m.mask] = m.mark);
      return {rats: ps.rats.map(strip), active_ms: ps.active_s * 1000, showall_ms: ps.showall_s * 1000, completed: ps.completed, marks: mk, archived_at: ps.archived_at}; }); });
  S.events = o.events || []; S.defnote = o.definition_note || ''; $('defnote').value = S.defnote; migrate(S); save(true); draw(); }); });
$('defnote').value = S.defnote || '';
$('defnote').addEventListener('input', e => { S.defnote = e.target.value; save(); });
$('defnote').addEventListener('change', () => log('definition_note', {text: S.defnote}));
$('showall').addEventListener('change', e => toggleShowAll(e.target.checked));
$('redo').addEventListener('click', () => redoFrame(false));
$('goto').innerHTML = D.frames.map((f, i) => '<option value="' + i + '">' + (i + 1) + ' · ' + (f.domain === 'ir' ? 'IR' : 'col') + ' · ' + f.arm + '</option>').join('');
$('goto').addEventListener('change', e => goFrame(+e.target.value));
const keepObj = S.cur.obj, keepRi = S.cur.ri; goFrame(S.cur.fi); S.cur.ri = Math.max(0, Math.min(keepRi, rats().length - 1)); S.cur.obj = keepObj || 'implant'; draw();
window.__pl = {S: () => S, D, goFrame, cur: () => ({fi: S.cur.fi, ri: S.cur.ri, obj: S.cur.obj}), rat: () => rat(), frame: () => fr(), drawn: () => drawnMasks,
  candidatesAt, exportJSON, exportCSV, key: KEY, redoFrame, setLastInput: dt => { lastInput = performance.now() - dt; },
  imgToClient: (u, v) => { const r0 = cv.getBoundingClientRect(), [x, y] = toCv(u, v); return [x + r0.left, y + r0.top]; },
  ready: () => { const im = img(); return im.complete && im.naturalWidth > 0; }, save: () => save(true), visible: () => document.visibilityState,
  setCur: (ri, o) => { S.cur.ri = ri; S.cur.obj = o; draw(); }, toast: () => $('toast').style.display === 'block' ? $('toast').textContent : ''};
})();
"""


# ============================================================================================ v2.1: join pieces (amendment B2)
PAGE_VERSION_V21 = "inbox_sam3_prelabel_edit_2026c_v2.1"


def page_html_v21(run_name: str) -> str:
    """v2 layout + J (join) in the help, a toast line; same definitions."""
    h = page_html_v2(run_name).replace(PAGE_JS_V2, PAGE_JS_V21)
    h = h.replace("<title>In-box pre-label edit v2</title>", "<title>In-box pre-label edit v2.1</title>")
    h = h.replace("· v2: implant box + rat box · 预标注编辑 v2</h1>", "· v2.1: implant box + rat box, join pieces · 预标注编辑 v2.1</h1>")
    h = h.replace("""M / P flag merged / partial (rat box) 合并 / 不完整 · B draw by hand 手画框 · F fit back to the mask 恢复 mask 框<br>""",
                  """M / P flag merged / partial (rat box; on a joined box: the whole box) 合并 / 不完整 · B draw by hand 手画框 ·
F fit back to the mask(s) 恢复 mask 框<br>
<b>J join this piece 拼接</b> (click another part → N → J): the box becomes the union of all joined pieces; every piece is outlined,
the candidate not yet joined is dashed · U undoes the last step (e.g. the last join) · A on a candidate = that ONE mask only<br>""")
    h = h.replace('<div id="banner"></div>', '<div id="banner"></div><div id="toast" style="display:none;font-weight:600;color:var(--acc)"></div>')
    return h


def _v2_data(run: Path, page_version: str, storage_key: str | None, accept_versions: list | None = None) -> dict:
    frames = pd.read_csv(run / "frames.csv")
    heads = pd.read_csv(run / "heads.csv")
    arms = assign_arms(frames, heads)
    data = {"page_version": page_version, "run": run.name, "plan": PLAN, "seed": SEED, "idle_ms": IDLE_MS, "cover_px": S.COVER_PX,
            "definitions": [{"term": k, "text": v} for k, v in DEFINITIONS_V2], "export_prefix": "v2_inbox_sam3_prelabel_edit_2026c_",
            "frames": []}
    if storage_key:
        data["storage_key"] = storage_key
    if accept_versions:
        data["accept_versions"] = accept_versions
    for r in arms.itertuples():
        H = heads[heads.frame_id == r.frame_id].sort_values(["u", "click_id"]).reset_index(drop=True)
        pl = frame_payload(run, r.frame_id, H)
        data["frames"].append({"id": r.frame_id, "domain": r.domain, "arm": r.arm, "pile_bin": r.pile_bin, "order": int(r.order),
                               "img": f"frames/{Path(r.path).name}", "w": S.IMG_W, "h": S.IMG_H,
                               "heads": [{"c": h.click_id, "u": round(float(h.u), 1), "v": round(float(h.v), 1)} for h in H.itertuples()],
                               "masks": pl["masks"], "cand": pl["cand"]})
    return data


def _read_data_js(p: Path) -> dict:
    t = p.read_text(encoding="utf-8").strip()
    assert t.startswith("window.PL_DATA = ") and t.endswith(";")
    return json.loads(t[len("window.PL_DATA = "):-1])


def update_v21(run: Path, check: bool = True) -> dict:
    """In-place update of <run>/prelabel_edit_v2 to v2.1 (amendment B2). The user's progress lives in their browser under the
    v2 storage key, which v2.1 keeps (data.storage_key). Before anything is written: index.html, pl_data.js, page_check.json
    and build_meta.json are copied to *.v2_0.bak (an existing backup is never overwritten), and the new frame payload is
    verified identical to v2.0 (frames, order, arms, heads, masks, candidate lists), so every stored mask id keeps its
    meaning. The frames/ folder is not touched."""
    out = run / "prelabel_edit_v2"
    assert (out / "pl_data.js").exists() and (out / "index.html").exists(), "no v2 page to update"
    for name in ("index.html", "pl_data.js", "page_check.json", "build_meta.json"):
        src, bak = out / name, out / f"{name}.v2_0.bak"
        if src.exists() and not bak.exists():
            shutil.copy2(src, bak)
    old = _read_data_js(out / "pl_data.js.v2_0.bak")
    key = old["page_version"] + "::" + old["run"]
    assert old["page_version"] == PAGE_VERSION_V2, f"the backup is not v2.0: {old['page_version']}"
    new = _v2_data(run, PAGE_VERSION_V21, key, [PAGE_VERSION_V2, PAGE_VERSION_V21])
    same = all(a[k] == b[k] for a, b in zip(old["frames"], new["frames"]) for k in ("id", "domain", "arm", "pile_bin", "order", "img", "heads", "masks", "cand")) \
        and len(old["frames"]) == len(new["frames"])
    if not same:
        raise SystemExit("v2.1 payload differs from v2.0 (frames / masks / candidates): not written, v2.0 left in place")
    js_final = "window.PL_DATA = " + json.dumps(new, separators=(",", ":")) + ";\n"
    html_final = page_html_v21(run.name)
    pc = None
    if check:                       # test a staged copy first; the live files are replaced only on PASS
        stg = out / "_v21_staging"
        if stg.exists():
            shutil.rmtree(stg)
        stg.mkdir()
        staged = json.loads(json.dumps(new))
        for f in staged["frames"]:
            f["img"] = "../" + f["img"]
        (stg / "pl_data.js").write_text("window.PL_DATA = " + json.dumps(staged, separators=(",", ":")) + ";\n", encoding="utf-8")
        (stg / "index.html").write_text(html_final, encoding="utf-8")
        try:
            pc = page_check_v21(stg, new, out / "index.html.v2_0.bak", out / "pl_data.js.v2_0.bak")
        finally:
            shutil.rmtree(stg, ignore_errors=True)
        print(f"v2.1 page check (staged): {pc['verdict']}", flush=True)
        if pc["verdict"] != "PASS":
            S.write_json(out / "page_check_v2_1_FAILED.json", pc)
            raise SystemExit("v2.1 check failed: the live v2.0 page was NOT replaced (see page_check_v2_1_FAILED.json)")
    (out / "pl_data.js").write_text(js_final, encoding="utf-8")
    (out / "index.html").write_text(html_final, encoding="utf-8")
    meta = json.loads((out / "build_meta.json.v2_0.bak").read_text(encoding="utf-8")) if (out / "build_meta.json.v2_0.bak").exists() else {}
    meta["v2_1"] = {"made": datetime.now().isoformat(timespec="seconds"), "amendment": "B2", "page_version": PAGE_VERSION_V21, "storage_key": key,
                    "payload_identical_to_v2_0": same, "backups": sorted(q.name for q in out.glob("*.v2_0.bak")),
                    "size": {"pl_data_js_bytes": (out / "pl_data.js").stat().st_size, "index_html_bytes": (out / "index.html").stat().st_size},
                    "page_check": pc["verdict"] if pc else "not run", "git_commit": git_commit()}
    if pc:
        S.write_json(out / "page_check.json", pc)
    S.write_json(out / "build_meta.json", meta)
    return meta


def _strip_new(o):
    """Recursively drop the fields v2.1 adds, so a v2.1 export can be compared with a v2.0 export of the same state."""
    new_obj = {"pieces", "union_box", "obj_flags", "prop_rule", "n_pieces"}
    new_top = {"schema", "storage_key", "migrated_v21_at", "migrated_v21_objects"}
    if isinstance(o, dict):
        return {k: _strip_new(v) for k, v in o.items() if k not in new_obj and k not in new_top}
    if isinstance(o, list):
        return [_strip_new(v) for v in o]
    return o


def page_check_v21(out: Path, data: dict, old_html: Path, old_data: Path) -> dict:
    """Headless Chrome (throwaway profile; the user's own browser storage is never touched).
    A. Old-state test: the backed-up v2.0 page (served from a temporary sibling folder, images from ../frames) saves a state
       with finished rats (candidate, manual, hidden implant, flags, time slices, events); the v2.1 page then loads it under
       the same storage key; every rat, box, flag, time slice and log entry must be intact, and its export must equal the
       v2.0 export apart from the new fields (and the clock / frame_open entries the reload itself adds).
    B. Joins on the v2.1 page: 2 and 3 pieces, J on a joined mask is a no-op, U undoes a join, F refits after an edge drag,
       A replaces the pieces (toast), M on a joined box is object-level, J on the implant box; export; no network URL."""
    import inbox_identity_page as ipage
    html_t, js_t = (out / "index.html").read_text(encoding="utf-8"), (out / "pl_data.js").read_text(encoding="utf-8")
    res = {"network_urls": re.findall(r"https?://[^\s\"'<>]+", html_t) + re.findall(r"https?://[^\s\"'<>]+", js_t)}
    tdir = out.parent / "_v20_oldstate_test" if out.name == "_v21_staging" else out / "_v20_oldstate_test"
    if tdir.exists():
        shutil.rmtree(tdir)
    tdir.mkdir()
    shutil.copy2(old_html, tdir / "index.html")
    od = _read_data_js(old_data)
    for f in od["frames"]:
        f["img"] = "../" + f["img"]
    (tdir / "pl_data.js").write_text("window.PL_DATA = " + json.dumps(od, separators=(",", ":")) + ";\n", encoding="utf-8")
    prof = Path(tempfile.mkdtemp(prefix="pl21check_"))
    p, wsu, bws = ipage._chrome((tdir / "index.html").resolve().as_uri(), prof, ipage._free_port())
    c = None
    fr = data["frames"]
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

        def interior_points(f, min_cand):
            pts_out = []
            for m in sorted(f["masks"], key=lambda m: -m["a"])[:25]:
                for pts in m["p"]:
                    x0, y0 = float(np.mean(pts[0::2])), float(np.mean(pts[1::2]))
                    if _pip(x0, y0, pts):
                        cand = c.ev(f"window.__pl.candidatesAt({x0}, {y0})")
                        if len(cand) >= min_cand:
                            pts_out.append(((x0, y0), cand))
                        break
            return pts_out
        # ---------------- A. old-state test with the v2.0 page
        res["loaded_v20"] = ready()
        res["v20_page_version"] = c.ev("window.__pl.D.page_version")
        pre = [i for i, f in enumerate(fr) if f["arm"] == "PRELABEL" and len(f["cand"]) >= 2 and f["cand"][0]]
        fi = pre[0]
        c.ev(f"window.__pl.goFrame({fi})")
        ready()
        f = fr[fi]
        bp = interior_points(f, 1)[0][0]
        key("a")                                   # rat 1: implant candidate 1
        key("Enter")
        click(*bp)                                 # body click -> candidates
        key("m")                                   # flag candidate 1 merged
        key("a")
        for _ in range(3):
            c.ev("window.__pl.setLastInput(0)")
            time.sleep(0.5)
        key("Enter")                               # rat 2
        key("h")                                   # implant hidden
        hu, hv = f["heads"][1]["u"], f["heads"][1]["v"]
        key("b")
        drag(hu - 120, hv - 90, hu + 160, hv + 140)  # manual rat box
        fs = next(i for i, x in enumerate(fr) if x["arm"] == "SCRATCH")
        c.ev(f"window.__pl.goFrame({fs})")
        ready()
        g = fr[fs]
        gu, gv = g["heads"][0]["u"], g["heads"][0]["v"]
        drag(gu - 50, gv - 40, gu + 50, gv + 40)
        key("Enter")
        drag(gu - 180, gv - 140, gu + 220, gv + 180)
        c.ev(f"window.__pl.goFrame({fi})")
        c.ev("window.__pl.setLastInput(60000)")      # idle before the switch, so the reload adds as little clock as possible
        ex_old = c.ev("window.__pl.exportJSON()")
        c.ev("window.__pl.save()")
        old_key = c.ev("window.__pl.key")
        c.call("Page.navigate", url=(out / "index.html").resolve().as_uri())
        time.sleep(1.5)
        res["loaded_v21"] = ready()
        c.ev("window.__pl.setLastInput(60000)")
        ex_new = c.ev("window.__pl.exportJSON()")
        new_key = c.ev("window.__pl.key")
        a, b = _strip_new(ex_old), _strip_new(ex_new)
        diffs = []
        for k in set(a) | set(b):
            if k in ("page_version", "exported_at", "events", "frames"):
                continue
            if a.get(k) != b.get(k):
                diffs.append(k)
        fr_diff = []
        for fa, fb in zip(a["frames"], b["frames"]):
            for k in fa:
                if k in ("active_s",):
                    if not (fb[k] >= fa[k] - 1e-9 and fb[k] - fa[k] < 3.0):
                        fr_diff.append((fa["frame_id"], k, fa[k], fb[k]))
                    continue
                if k == "rats":
                    for ra, rb in zip(fa["rats"], fb["rats"]):
                        for kk in ra:
                            if kk in ("implant", "rat"):
                                for k3 in ra[kk]:
                                    if k3 == "time_ms":
                                        if not (rb[kk][k3] >= ra[kk][k3] - 1e-9 and rb[kk][k3] - ra[kk][k3] < 3000):
                                            fr_diff.append((fa["frame_id"], ra["id"], kk, k3))
                                    elif ra[kk][k3] != rb[kk].get(k3):
                                        fr_diff.append((fa["frame_id"], ra["id"], kk, k3, ra[kk][k3], rb[kk].get(k3)))
                            elif ra[kk] != rb.get(kk):
                                fr_diff.append((fa["frame_id"], ra["id"], kk))
                    continue
                if fa[k] != fb[k]:
                    fr_diff.append((fa["frame_id"], k))
        ev_old, ev_new = ex_old["events"], ex_new["events"]
        extra_ev = [e["ev"] for e in ev_new[len(ev_old):]]
        f_new = next(x for x in ex_new["frames"] if x["frame_id"] == f["id"])
        r1, r2 = f_new["rats"][0], f_new["rats"][1]
        res["old_state"] = {"same_storage_key": old_key == new_key, "top_level_diffs": diffs, "frame_diffs": fr_diff[:10],
                            "events_prefix_intact": ev_new[:len(ev_old)] == ev_old, "events_added_by_reload": extra_ev,
                            "migrated_objects": ex_new.get("migrated_v21_objects"),
                            "rat1_implant": [r1["implant"]["source"], r1["implant"]["n_pieces"], r1["implant"]["union_box"] == r1["implant"]["box"]],
                            "rat1_rat": [r1["rat"]["source"], r1["rat"]["cand_flags"], r1["rat"]["n_pieces"], r1["rat"]["pieces"][0]["click"] == r1["rat"]["click"]],
                            "rat2": [r2["implant"]["hidden"], r2["implant"]["n_pieces"], r2["rat"]["source"], r2["rat"]["n_pieces"], r2["rat"]["union_box"]],
                            "ok": old_key == new_key and not diffs and not fr_diff and ev_new[:len(ev_old)] == ev_old
                            and set(extra_ev) <= {"frame_open", "visibility"} and len(extra_ev) <= 3
                            and r1["implant"]["source"] == "cand" and r1["implant"]["n_pieces"] == 1 and r1["rat"]["n_pieces"] == 1
                            and r1["rat"]["cand_flags"].get("1", {}).get("merged") is True and r2["implant"]["hidden"] is True
                            and r2["rat"]["source"] == "manual" and r2["rat"]["n_pieces"] == 0 and r2["rat"]["union_box"] is None}
        res["v1_storage_untouched_note"] = "the throwaway profile held no v1 data; v2.1 reads only the v2 key"
        # ---------------- B. joins on the v2.1 page (another PRELABEL frame)
        fj, pts = None, None
        for i in pre[1:]:
            c.ev(f"window.__pl.goFrame({i})")
            cand_pts = interior_points(fr[i], 2)
            if len(cand_pts) >= 2:
                (p1, c1), (p2, c2) = cand_pts[0], cand_pts[1]
                if any(x not in c1[:2] for x in c2):
                    fj, pts = i, cand_pts
                    break
        c.ev(f"window.__pl.goFrame({fj})")
        ready()
        g = fr[fj]
        (p1, c1), (p2, c2) = pts[0], pts[1]
        key("Enter")                              # implant -> rat
        click(*p1)
        key("j")                                  # piece 1 = candidate 1 at p1
        key("n")
        key("j")                                  # piece 2 = candidate 2 at p1
        r2p = R()["rat"]
        ub2 = [min(g["masks"][c1[0]]["b"][0], g["masks"][c1[1]]["b"][0]), min(g["masks"][c1[0]]["b"][1], g["masks"][c1[1]]["b"][1]),
               max(g["masks"][c1[0]]["b"][2], g["masks"][c1[1]]["b"][2]), max(g["masks"][c1[0]]["b"][3], g["masks"][c1[1]]["b"][3])]
        key("j")                                  # J on an already joined mask: no-op
        r2b = R()["rat"]
        click(*p2)
        k3 = next(j for j, x in enumerate(c2) if x not in c1[:2])
        for _ in range(k3):
            key("n")
        key("j")                                  # piece 3
        r3p = R()["rat"]
        res["join"] = {"two": [r2p["source"], len(r2p["pieces"]), r2p["box"] == ub2, r2p["union_box"] == ub2],
                       "rejoin_noop": len(r2b["pieces"]) == 2, "toast_rejoin": c.ev("window.__pl.toast()"),
                       "three": [r3p["source"], len(r3p["pieces"]), [pc["click"] for pc in r3p["pieces"]]],
                       "ok": r2p["source"] == "joined" and len(r2p["pieces"]) == 2 and r2p["box"] == ub2 and len(r2b["pieces"]) == 2
                       and r3p["source"] == "joined" and len(r3p["pieces"]) == 3 and r3p["pieces"][2]["click"] is not None
                       and r3p["pieces"][0]["click"] != r3p["pieces"][2]["click"]}
        key("u")                                  # undo the last join
        ru = R()["rat"]
        res["undo_join"] = {"n_pieces": len(ru["pieces"]), "box_back_to_two": ru["box"] == ub2, "ok": len(ru["pieces"]) == 2 and ru["box"] == ub2}
        b = ru["box"]
        drag(b[2], (b[1] + b[3]) / 2, b[2] + 50, (b[1] + b[3]) / 2)
        rd = R()["rat"]
        key("f")
        rf = R()["rat"]
        res["fit_after_join"] = {"dragged": rd["box"] != ub2, "union_kept": rd["union_box"] == ub2, "fitted": rf["box"] == ub2,
                                 "ok": rd["box"] != ub2 and rd["union_box"] == ub2 and rf["box"] == ub2 and rd["edge_moves"] == 1}
        key("m")                                  # flag on a joined box = object level
        rm = R()["rat"]
        res["flag_joined"] = {"obj_flags": rm["obj_flags"], "ok": rm["obj_flags"].get("merged") is True}
        c.ev(f"(() => {{ const S = window.__pl.S(); S.cur.obj = 'rat'; }})()")
        key("a")                                  # A on the shown candidate replaces the pieces
        ra = R()["rat"]
        res["accept_replaces"] = {"source": ra["source"], "n_pieces": len(ra["pieces"]), "toast": c.ev("window.__pl.toast()"), "obj_flags": ra["obj_flags"],
                                  "ok": ra["source"] == "cand" and len(ra["pieces"]) == 1 and "replaced" in c.ev("window.__pl.toast()")
                                  and ra["box"] == g["masks"][ra["mask"]]["b"]}
        # J on the implant box
        ji = next((j for j, x in enumerate(g["cand"]) if len(x) >= 2), None)
        if ji is not None:
            c.ev(f"window.__pl.setCur({ji}, 'implant')")
            key("j")
            key("n")
            key("j")
            ri = R()["implant"]
            res["implant_join"] = {"source": ri["source"], "n_pieces": len(ri["pieces"]), "ok": ri["source"] == "joined" and len(ri["pieces"]) == 2}
        else:
            res["implant_join"] = {"ok": True, "note": "no head with >= 2 candidates on this frame"}
        # export
        ej = c.ev("window.__pl.exportJSON()")
        n_rats = sum(len(x["rats"]) for x in ej["frames"])
        csv_lines = c.ev("window.__pl.exportCSV().trim().split('\\n').length")
        evk = sorted({e["ev"] for e in ej["events"]})
        fj_out = next(x for x in ej["frames"] if x["frame_id"] == g["id"])
        res["export"] = {"version": ej["page_version"], "schema": ej.get("schema"), "csv_lines": csv_lines, "event_kinds": evk,
                         "pieces_have_cache_index": all("mask_cache_index" in pc for r in fj_out["rats"] for k in OBJS for pc in r[k]["pieces"]),
                         "ok": ej["page_version"] == PAGE_VERSION_V21 and csv_lines == 2 * n_rats + 1 and "join" in evk
                         and all("mask_cache_index" in pc for r in fj_out["rats"] for k in OBJS for pc in r[k]["pieces"])}
        c.ev("localStorage.clear()")
    finally:
        if c:
            c.close()
        ipage._close_chrome(p, bws)
        shutil.rmtree(prof, ignore_errors=True)
        shutil.rmtree(tdir, ignore_errors=True)
    keys = ["old_state", "join", "undo_join", "fit_after_join", "flag_joined", "accept_replaces", "implant_join", "export"]
    res["verdict"] = "PASS" if (res.get("loaded_v20") and res.get("loaded_v21") and all(res[k]["ok"] for k in keys) and not res["network_urls"]) else "FAIL"
    return res


# ============================================================================================ v2.2: UX fixes (the user: "click body -> J does nothing")
PAGE_VERSION_V22 = "inbox_sam3_prelabel_edit_2026c_v2.2"


def _sub(src: str, old: str, new: str) -> str:
    assert src.count(old) == 1, (src.count(old), old[:90])
    return src.replace(old, new)


def _make_js_v22() -> str:
    j = PAGE_JS_V21
    # 1. a plain click on a PRELABEL frame always goes to the RAT box and runs the body click (logged as obj_auto_switch)
    j = _sub(j, """  if (d.kind === 'press') { if (!d.moved && st().arm === 'PRELABEL' && S.cur.obj === 'rat') bodyClick(d.u, d.v); return; }""",
             """  if (d.kind === 'press') { if (!d.moved && st().arm === 'PRELABEL' && mode !== 'draw' && !showAll) { const r = rat();
      if (r && !r.deleted) { if (S.cur.obj !== 'rat') { S.cur.obj = 'rat'; log('obj_auto_switch', {from: 'implant', reason: 'body_click'}); } bodyClick(d.u, d.v); } } return; }""")
    # 3. why a key cannot act
    j = _sub(j, """function accept(){ const o = obj(), c = curCand(); if (!o || c === null) return; snap(); const m = fr().masks[c];""",
             """const MSG = {scratch: 'SCRATCH frame: draw by hand (drag) · 从零画框: 请手动拖框', norat: 'no rat selected · 没有选中的鼠',
  hidden: 'implant hidden — press H to show it again · 植入体已标为看不见 (按 H 取消)', noclick: 'no candidate here — click the body first · 先点鼠的身体',
  nocand: 'no candidate here — click another part of the rat, or draw by hand (B) · 这里没有候选: 点鼠的别处或手画 (B)',
  none: '"none usable" is shown — press N for the candidates again, or draw by hand (B) · 当前为"无可用": 按 N 或手画 (B)',
  joined: 'already joined · 已经拼接过这个 mask', mp_implant: 'M / P apply to the rat box only · 合并 / 不完整只用于鼠框'};
function whyNot(){ const r = rat(), o = obj(); if (st().arm !== 'PRELABEL') return MSG.scratch; if (!r || r.deleted || !o) return MSG.norat;
  if (S.cur.obj === 'implant' && o.hidden) return MSG.hidden; if (S.cur.obj === 'rat' && !o.click) return MSG.noclick;
  if (!o.cand.length) return MSG.nocand; if (o.k >= o.cand.length) return MSG.none; return null; }
function accept(){ const o = obj(), c = curCand(); if (!o || c === null) { const w = whyNot(); if (w) toast(w); return; } snap(); const m = fr().masks[c];""")
    j = _sub(j, """function join(){ const o = obj(), c = curCand(); if (!o || c === null) return;
  if ((o.pieces || []).some(p => p.mask === c)) { toast('this piece is already joined'); return; }""",
             """function join(){ const o = obj(), c = curCand(); if (!o || c === null) { const w = whyNot(); if (w) toast(w); return; }
  if ((o.pieces || []).some(p => p.mask === c)) { toast(MSG.joined); return; }""")
    j = _sub(j, """function next(){ const o = obj(), r = rat(); if (!o || !r || r.deleted || st().arm !== 'PRELABEL' || showAll) return; if (S.cur.obj === 'implant' && o.hidden) return;
  if (S.cur.obj === 'rat' && !o.click) return; snap();""",
             """function next(){ const o = obj(), r = rat(); if (showAll) return; if (!o || !r || r.deleted || st().arm !== 'PRELABEL' || (S.cur.obj === 'implant' && o.hidden)
  || (S.cur.obj === 'rat' && !o.click)) { toast(whyNot() || MSG.norat); return; } if (!o.cand.length) { toast(MSG.nocand); return; } snap();""")
    j = _sub(j, """function flag(kind){ if (S.cur.obj !== 'rat') return; const o = obj(); if (!o) return;""",
             """function flag(kind){ if (st().arm !== 'PRELABEL') { toast(MSG.scratch); return; } if (S.cur.obj !== 'rat') { toast(MSG.mp_implant); return; } const o = obj(); if (!o) return;""")
    j = _sub(j, """  if (curCand() === null) return; snap(); const fl = o.cand_flags[o.k + 1] = o.cand_flags[o.k + 1] || {}; fl[kind] = !fl[kind];""",
             """  if (curCand() === null) { toast(whyNot() || MSG.none); return; } snap(); const fl = o.cand_flags[o.k + 1] = o.cand_flags[o.k + 1] || {}; fl[kind] = !fl[kind];""")
    j = _sub(j, """  if (k === 'a' && pre) accept(); else if (k === 'j' && pre) join(); else if (k === 'n' && pre) next(); else if (k === 'm' && pre) flag('merged'); else if (k === 'p' && pre) flag('partial');""",
             """  if (!pre && ['a', 'j', 'n', 'm', 'p'].includes(k)) { toast(MSG.scratch); return; }
  if (k === 'a') accept(); else if (k === 'j') join(); else if (k === 'n') next(); else if (k === 'm') flag('merged'); else if (k === 'p') flag('partial');""")
    # 2. mode banner, coloured like the box
    j = _sub(j, """  $('objtag').textContent = OBJ_NAME[S.cur.obj]; $('objtag').className = 'obj-' + S.cur.obj;""",
             """  $('objtag').textContent = OBJ_NAME[S.cur.obj]; $('objtag').className = 'obj-' + S.cur.obj;
  const pre = s.arm === 'PRELABEL', mb = $('modebanner');
  mb.textContent = (S.cur.obj === 'implant' ? 'NOW: IMPLANT box 植入体框 (orange)' : 'NOW: RAT box 整鼠框 (green) — ' + (pre ? 'click the body' : 'drag to draw'))
    + '   ·   ' + (pre ? 'PRELABEL 预标注' : 'SCRATCH 从零画框 — drag to draw, no candidates, A/N/J off');
  mb.className = 'mode-' + S.cur.obj;""")
    j = _sub(j, """  setCur: (ri, o) => { S.cur.ri = ri; S.cur.obj = o; draw(); }, toast: () => $('toast').style.display === 'block' ? $('toast').textContent : ''};""",
             """  setCur: (ri, o) => { S.cur.ri = ri; S.cur.obj = o; draw(); }, toast: () => $('toast').style.display === 'block' ? $('toast').textContent : '',
  banner: () => $('modebanner').textContent, clearToast: () => { $('toast').style.display = 'none'; }};""")
    return j


PAGE_JS_V22 = _make_js_v22()

LEGEND_V22 = """<details id="legend" open><summary>colours 图例</summary>
<div><span class="sw" style="border:2px dashed #00e5ff"></span> implant candidate 植入体候选</div>
<div><span class="sw" style="border:2px dashed #ff9f1a"></span> implant box 植入体框 (orange)</div>
<div><span class="sw" style="border:2px dashed #ff4fd8"></span> rat candidate 鼠候选 (pink)</div>
<div><span class="sw" style="border:2px solid #39ff14"></span> rat box 整鼠框 (green)</div>
<div><span class="sw" style="border:2px dashed #ffd400"></span> candidate bbox 候选框</div>
<div><span style="color:#ff4fd8;font-weight:700">+</span> body click 点击位置 &nbsp; <span style="color:#fff">●</span> head 头 (<span style="color:#ff2fd0">●</span> current rat)</div>
<div style="opacity:.55">faint = other rats 其他鼠</div></details>"""


def page_html_v22(run_name: str) -> str:
    h = page_html_v21(run_name).replace(PAGE_JS_V21, PAGE_JS_V22)
    h = _sub(h, "<title>In-box pre-label edit v2.1</title>", "<title>In-box pre-label edit v2.2</title>")
    h = _sub(h, "· v2.1: implant box + rat box, join pieces · 预标注编辑 v2.1</h1>", "· v2.2: implant box + rat box, join pieces · 预标注编辑 v2.2</h1>")
    h = _sub(h, """<b>Per rat: IMPLANT box, then RAT box, then Enter</b> 每只鼠: 先植入体框, 再鼠框, 然后 Enter.<br>""",
             """<b>Each rat: implant (A/N/J, H hidden) → click the body → rat box (A/N/J…) → Enter</b> 每只鼠: 植入体 (A/N/J, H 看不见) → 点身体 → 鼠框 (A/N/J…) → Enter.
A click on the image always switches to the RAT box 点击图像总是切换到鼠框.<br>""")
    h = _sub(h, '<canvas id="cv"></canvas>', '<div id="modebanner"></div><div style="position:relative"><canvas id="cv"></canvas>' + LEGEND_V22 + "</div>")
    h = _sub(h, '<div id="toast" style="display:none;font-weight:600;color:var(--acc)"></div>', '<div id="toast" style="display:none"></div>')
    h = _sub(h, "</style></head>", """
#modebanner{font-size:19px;font-weight:800;padding:6px 12px;border-radius:6px;margin:4px 0;color:#111;letter-spacing:.2px}
#modebanner.mode-implant{background:#ff9f1a}#modebanner.mode-rat{background:#39ff14}
#toast{position:fixed;top:70px;left:50%;transform:translateX(-50%);z-index:50;font-size:18px;font-weight:700;padding:10px 18px;border-radius:8px;
 background:#222;color:#fff;border:2px solid #ffd400;box-shadow:0 4px 18px rgba(0,0,0,.4);max-width:80vw;text-align:center}
#legend{position:absolute;left:8px;bottom:8px;background:rgba(0,0,0,.62);color:#eee;font-size:12px;padding:4px 8px;border-radius:6px;line-height:1.5}
#legend summary{cursor:pointer;font-weight:700}#legend .sw{display:inline-block;width:18px;height:9px;margin-right:4px;vertical-align:middle}
</style></head>""")
    return h


def _compare_exports(ex_old: dict, ex_new: dict, strip=lambda x: x) -> dict:
    """Same state, two page versions: everything equal (after strip) except page_version / exported_at, time that may only have
    grown by the reload's seconds, and events (the old log must be a prefix of the new one)."""
    a, b = strip(ex_old), strip(ex_new)
    top = [k for k in set(a) | set(b) if k not in ("page_version", "exported_at", "events", "frames") and a.get(k) != b.get(k)]
    fd = []
    for fa, fb in zip(a["frames"], b["frames"]):
        for k in fa:
            if k == "active_s":
                if not (fb[k] >= fa[k] - 1e-9 and fb[k] - fa[k] < 3.0):
                    fd.append((fa["frame_id"], k))
            elif k == "rats":
                for ra, rb in zip(fa["rats"], fb["rats"]):
                    for kk in ra:
                        if kk in ("implant", "rat"):
                            for k3 in ra[kk]:
                                if k3 == "time_ms":
                                    if not (rb[kk][k3] >= ra[kk][k3] - 1e-9 and rb[kk][k3] - ra[kk][k3] < 3000):
                                        fd.append((fa["frame_id"], ra["id"], kk, k3))
                                elif ra[kk][k3] != rb[kk].get(k3):
                                    fd.append((fa["frame_id"], ra["id"], kk, k3))
                        elif ra[kk] != rb.get(kk):
                            fd.append((fa["frame_id"], ra["id"], kk))
                if len(fa["rats"]) != len(fb["rats"]):
                    fd.append((fa["frame_id"], "n_rats"))
            elif fa[k] != fb.get(k):
                fd.append((fa["frame_id"], k))
    eo, en = ex_old["events"], ex_new["events"]
    extra = [e["ev"] for e in en[len(eo):]]
    return {"top_level_diffs": top, "frame_diffs": fd[:10], "events_prefix_intact": en[:len(eo)] == eo, "events_added_by_reload": extra,
            "ok": not top and not fd and en[:len(eo)] == eo and set(extra) <= {"frame_open", "visibility"} and len(extra) <= 3}


def page_check_v22(new_dir: Path, data: dict, old_html: Path, old_data: Path) -> dict:
    """Headless Chrome (throwaway profile). A: old-state test — the backed-up v2.1 page saves a state with joins (2 pieces + an
    object-level flag), an accepted implant, a hidden implant + manual rat box and SCRATCH boxes; v2.2 loads it under the same
    key; exports equal apart from page_version / time / reload events. B: v2.2 UX — a click in IMPLANT mode switches to the RAT
    box and gives candidates (obj_auto_switch logged), J joins; the toasts (already joined, no click yet, SCRATCH, implant hidden);
    the banner text per mode and arm; export; no network URL."""
    import inbox_identity_page as ipage
    html_t, js_t = (new_dir / "index.html").read_text(encoding="utf-8"), (new_dir / "pl_data.js").read_text(encoding="utf-8")
    res = {"network_urls": re.findall(r"https?://[^\s\"'<>]+", html_t) + re.findall(r"https?://[^\s\"'<>]+", js_t)}
    vdir = new_dir.parent if new_dir.name.startswith("_") else new_dir
    tdir = vdir / "_v21_oldstate_test"
    if tdir.exists():
        shutil.rmtree(tdir)
    tdir.mkdir()
    shutil.copy2(old_html, tdir / "index.html")
    od = _read_data_js(old_data)
    for f in od["frames"]:
        f["img"] = "../" + f["img"]
    (tdir / "pl_data.js").write_text("window.PL_DATA = " + json.dumps(od, separators=(",", ":")) + ";\n", encoding="utf-8")
    prof = Path(tempfile.mkdtemp(prefix="pl22check_"))
    p, wsu, bws = ipage._chrome((tdir / "index.html").resolve().as_uri(), prof, ipage._free_port())
    c = None
    fr = data["frames"]
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

        def body_points(f, min_cand):
            out = []
            for m in sorted(f["masks"], key=lambda m: -m["a"])[:25]:
                for pts in m["p"]:
                    x0, y0 = float(np.mean(pts[0::2])), float(np.mean(pts[1::2]))
                    if _pip(x0, y0, pts):
                        cand = c.ev(f"window.__pl.candidatesAt({x0}, {y0})")
                        if len(cand) >= min_cand:
                            out.append(((x0, y0), cand))
                        break
            return out
        # ---------------- A. old-state test (v2.1 state with joins)
        res["loaded_v21"] = ready()
        res["v21_page_version"] = c.ev("window.__pl.D.page_version")
        pre = [i for i, f in enumerate(fr) if f["arm"] == "PRELABEL" and len(f["cand"]) >= 2 and f["cand"][0]]
        fi = None
        for i in pre:
            c.ev(f"window.__pl.goFrame({i})")
            bp = body_points(fr[i], 2)
            if bp:
                fi, (pt, cands) = i, bp[0]
                break
        c.ev(f"window.__pl.goFrame({fi})")
        ready()
        f = fr[fi]
        key("a")                                    # implant candidate 1
        key("Enter")                                # -> rat (v2.1 needs the explicit switch)
        click(*pt)
        key("j")
        key("n")
        key("j")                                    # joined, 2 pieces
        key("m")                                    # object-level flag
        for _ in range(3):
            c.ev("window.__pl.setLastInput(0)")
            time.sleep(0.5)
        key("Enter")
        key("h")
        hu, hv = f["heads"][1]["u"], f["heads"][1]["v"]
        key("b")
        drag(hu - 120, hv - 90, hu + 160, hv + 140)
        fs = next(i for i, x in enumerate(fr) if x["arm"] == "SCRATCH")
        c.ev(f"window.__pl.goFrame({fs})")
        ready()
        g = fr[fs]
        gu, gv = g["heads"][0]["u"], g["heads"][0]["v"]
        drag(gu - 50, gv - 40, gu + 50, gv + 40)
        key("Enter")
        drag(gu - 180, gv - 140, gu + 220, gv + 180)
        c.ev(f"window.__pl.goFrame({fi})")
        c.ev("window.__pl.setLastInput(60000)")
        ex_old = c.ev("window.__pl.exportJSON()")
        c.ev("window.__pl.save()")
        old_key = c.ev("window.__pl.key")
        c.call("Page.navigate", url=(new_dir / "index.html").resolve().as_uri())
        time.sleep(1.5)
        res["loaded_v22"] = ready()
        c.ev("window.__pl.setLastInput(60000)")
        ex_new = c.ev("window.__pl.exportJSON()")
        cmp = _compare_exports(ex_old, ex_new)
        f_new = next(x for x in ex_new["frames"] if x["frame_id"] == f["id"])
        r1 = f_new["rats"][0]
        res["old_state"] = {**cmp, "same_storage_key": old_key == c.ev("window.__pl.key"),
                            "rat1_rat": [r1["rat"]["source"], r1["rat"]["n_pieces"], r1["rat"]["obj_flags"]],
                            "ok": cmp["ok"] and old_key == c.ev("window.__pl.key") and r1["rat"]["source"] == "joined" and r1["rat"]["n_pieces"] == 2
                            and r1["rat"]["obj_flags"].get("merged") is True}
        # ---------------- B. v2.2 UX on another PRELABEL frame
        fj, pts = None, None
        for i in pre:
            if i == fi:
                continue
            c.ev(f"window.__pl.goFrame({i})")
            bp = body_points(fr[i], 2)
            if bp:
                fj, pts = i, bp[0]
                break
        c.ev(f"window.__pl.goFrame({fj})")
        ready()
        g = fr[fj]
        b_impl = c.ev("window.__pl.banner()")
        o0 = c.ev("window.__pl.cur()")["obj"]
        click(*pts[0])                              # still in IMPLANT mode: the click switches to the RAT box
        o1 = c.ev("window.__pl.cur()")["obj"]
        rr = R()["rat"]
        b_rat = c.ev("window.__pl.banner()")
        evs = c.ev("window.__pl.S().events.slice(-3).map(e => e.ev)")
        key("j")
        r_j = R()["rat"]
        key("j")                                    # same mask again -> toast
        t_joined = c.ev("window.__pl.toast()")
        res["click_switch_and_join"] = {"obj_before": o0, "obj_after": o1, "n_cand": len(rr["cand"]), "last_events": evs, "pieces_after_j": len(r_j["pieces"]),
                                        "ok": o0 == "implant" and o1 == "rat" and len(rr["cand"]) >= 2 and "obj_auto_switch" in evs and "body_click" in evs
                                        and len(r_j["pieces"]) == 1 and r_j["source"] == "cand"}
        key("n")
        key("j")
        res["join_after_switch"] = {"source": R()["rat"]["source"], "n_pieces": len(R()["rat"]["pieces"]),
                                    "ok": R()["rat"]["source"] == "joined" and len(R()["rat"]["pieces"]) == 2}
        # toasts
        c.ev("window.__pl.clearToast()")
        key("Enter")                                # next rat, IMPLANT
        c.ev("(() => { const S = window.__pl.S(); S.cur.obj = 'rat'; })()")
        key("j")                                    # rat box, no body click yet
        t_noclick = c.ev("window.__pl.toast()")
        key("h")                                    # implant hidden
        c.ev("window.__pl.setCur(window.__pl.cur().ri, 'implant')")
        key("j")
        t_hidden = c.ev("window.__pl.toast()")
        fs2 = next(i for i, x in enumerate(fr) if x["arm"] == "SCRATCH" and i != fs)
        c.ev(f"window.__pl.goFrame({fs2})")
        ready()
        b_scr_impl = c.ev("window.__pl.banner()")
        key("a")
        t_scratch = c.ev("window.__pl.toast()")
        key("Enter")
        b_scr_rat = c.ev("window.__pl.banner()")
        res["toasts"] = {"already_joined": t_joined, "no_click": t_noclick, "implant_hidden": t_hidden, "scratch": t_scratch,
                         "ok": "already joined" in t_joined and "click the body first" in t_noclick and "implant hidden" in t_hidden
                         and "SCRATCH frame" in t_scratch}
        res["banner"] = {"prelabel_implant": b_impl, "prelabel_rat": b_rat, "scratch_implant": b_scr_impl, "scratch_rat": b_scr_rat,
                         "ok": "IMPLANT" in b_impl and "PRELABEL" in b_impl and "RAT box" in b_rat and "click the body" in b_rat
                         and "IMPLANT" in b_scr_impl and "SCRATCH" in b_scr_impl and "A/N/J off" in b_scr_impl and "RAT box" in b_scr_rat
                         and "drag to draw" in b_scr_rat}
        res["legend"] = {"ok": c.ev("!!document.getElementById('legend') && document.getElementById('legend').textContent.includes('rat candidate')")}
        ej = c.ev("window.__pl.exportJSON()")
        n_rats = sum(len(x["rats"]) for x in ej["frames"])
        csv_lines = c.ev("window.__pl.exportCSV().trim().split('\\n').length")
        evk = sorted({e["ev"] for e in ej["events"]})
        res["export"] = {"version": ej["page_version"], "csv_lines": csv_lines, "event_kinds": evk,
                         "ok": ej["page_version"] == PAGE_VERSION_V22 and csv_lines == 2 * n_rats + 1 and "obj_auto_switch" in evk and "join" in evk}
        c.ev("localStorage.clear()")
    finally:
        if c:
            c.close()
        ipage._close_chrome(p, bws)
        shutil.rmtree(prof, ignore_errors=True)
        shutil.rmtree(tdir, ignore_errors=True)
    keys = ["old_state", "click_switch_and_join", "join_after_switch", "toasts", "banner", "legend", "export"]
    res["verdict"] = "PASS" if (res.get("loaded_v21") and res.get("loaded_v22") and all(res[k]["ok"] for k in keys) and not res["network_urls"]) else "FAIL"
    return res


def update_v22(run: Path, check: bool = True) -> dict:
    """In-place v2.1 -> v2.2 (UX fixes). Same storage key; *.v2_1.bak backups first; payload verified identical to v2.1; a
    staged copy is checked (incl. the old-state load test) before the live files are replaced."""
    out = run / "prelabel_edit_v2"
    cur = _read_data_js(out / "pl_data.js")
    if cur["page_version"] == PAGE_VERSION_V21:
        for name in ("index.html", "pl_data.js", "page_check.json", "build_meta.json"):
            src, bak = out / name, out / f"{name}.v2_1.bak"
            if src.exists() and not bak.exists():
                shutil.copy2(src, bak)
    old = _read_data_js(out / "pl_data.js.v2_1.bak")
    assert old["page_version"] == PAGE_VERSION_V21, f"the backup is not v2.1: {old['page_version']}"
    key = old["storage_key"]
    new = _v2_data(run, PAGE_VERSION_V22, key, [PAGE_VERSION_V2, PAGE_VERSION_V21, PAGE_VERSION_V22])
    same = len(old["frames"]) == len(new["frames"]) and all(a[k] == b[k] for a, b in zip(old["frames"], new["frames"])
                                                            for k in ("id", "domain", "arm", "pile_bin", "order", "img", "heads", "masks", "cand"))
    if not same:
        raise SystemExit("v2.2 payload differs from v2.1: not written, v2.1 left in place")
    js_final = "window.PL_DATA = " + json.dumps(new, separators=(",", ":")) + ";\n"
    html_final = page_html_v22(run.name)
    pc = None
    if check:
        stg = out / "_v22_staging"
        if stg.exists():
            shutil.rmtree(stg)
        stg.mkdir()
        staged = json.loads(json.dumps(new))
        for f in staged["frames"]:
            f["img"] = "../" + f["img"]
        (stg / "pl_data.js").write_text("window.PL_DATA = " + json.dumps(staged, separators=(",", ":")) + ";\n", encoding="utf-8")
        (stg / "index.html").write_text(html_final, encoding="utf-8")
        try:
            pc = page_check_v22(stg, new, out / "index.html.v2_1.bak", out / "pl_data.js.v2_1.bak")
        finally:
            shutil.rmtree(stg, ignore_errors=True)
        print(f"v2.2 page check (staged): {pc['verdict']}", flush=True)
        if pc["verdict"] != "PASS":
            S.write_json(out / "page_check_v2_2_FAILED.json", pc)
            raise SystemExit("v2.2 check failed: the live v2.1 page was NOT replaced (see page_check_v2_2_FAILED.json)")
    (out / "pl_data.js").write_text(js_final, encoding="utf-8")
    (out / "index.html").write_text(html_final, encoding="utf-8")
    meta = json.loads((out / "build_meta.json.v2_1.bak").read_text(encoding="utf-8"))
    meta["v2_2"] = {"made": datetime.now().isoformat(timespec="seconds"), "why": "UX: click switches to the rat box; mode banner; toasts; legend",
                    "page_version": PAGE_VERSION_V22, "storage_key": key, "payload_identical_to_v2_1": same,
                    "backups": sorted(q.name for q in out.glob("*.bak")), "page_check": pc["verdict"] if pc else "not run", "git_commit": git_commit()}
    if pc:
        S.write_json(out / "page_check.json", pc)
    S.write_json(out / "build_meta.json", meta)
    return meta


# ============================================================================================ v2.3: two explicit sticky modes + rat switching
PAGE_VERSION_V23 = "inbox_sam3_prelabel_edit_2026c_v2.3"


def _make_js_v23() -> str:
    """v2.2 -> v2.3 (the user: "太复杂了 … 显示我现在到底是啥模式" and "怎么切换鼠"): two explicit, sticky modes (IMPLANT / RAT; buttons,
    1 / 2, Tab) — a click, key or drawn box acts only on the active object; no auto-switch; the mode never changes on Enter, ←,
    a new rat or a new frame. Rat switching: number chips with per-object status in the banner, a plain click on another rat's
    white head dot, Enter / ← next / previous rat."""
    j = PAGE_JS_V22
    # ---- clicks act on the ACTIVE object only (no auto-switch); a plain click on another rat's white dot selects that rat
    j = _sub(j, """  const ed = edgeAt(x, y); if (ed) { drag = {kind: 'edge', edges: ed, b0: obj().box.slice()}; return; }
  if (canDraw()) { drag = {kind: 'draw', start: [u, v], cur: null}; return; }
  drag = {kind: 'press', x0: e.clientX, y0: e.clientY, ox: view.ox, oy: view.oy, u: u, v: v, moved: false}; });""",
             """  const dot = dotAt(x, y);
  const ed = edgeAt(x, y); if (ed) { drag = {kind: 'edge', edges: ed, b0: obj().box.slice(), dot: dot, x0: e.clientX, y0: e.clientY}; return; }
  if (canDraw()) { drag = {kind: 'draw', start: [u, v], cur: null, dot: dot, x0: e.clientX, y0: e.clientY}; return; }
  drag = {kind: 'press', x0: e.clientX, y0: e.clientY, ox: view.ox, oy: view.oy, u: u, v: v, moved: false, dot: dot}; });""")
    j = _sub(j, """  if (d.kind === 'press') { if (!d.moved && st().arm === 'PRELABEL' && mode !== 'draw' && !showAll) { const r = rat();
      if (r && !r.deleted) { if (S.cur.obj !== 'rat') { S.cur.obj = 'rat'; log('obj_auto_switch', {from: 'implant', reason: 'body_click'}); } bodyClick(d.u, d.v); } } return; }
  if (d.kind === 'draw') { if (d.cur) {""",
             """  const plain = Math.hypot(e.clientX - d.x0, e.clientY - d.y0) <= 4, dotHit = d.dot !== null && d.dot !== undefined && d.dot !== S.cur.ri;
  if (d.kind === 'press') { if (!d.moved && dotHit) { selectRat(d.dot, 'dot'); return; }
    if (!d.moved && st().arm === 'PRELABEL' && mode !== 'draw' && !showAll) objClick(d.u, d.v); return; }
  if (d.kind === 'draw' && plain && dotHit) { selectRat(d.dot, 'dot'); return; }
  if (d.kind === 'edge' && plain && dotHit) { obj().box = d.b0; selectRat(d.dot, 'dot'); return; }
  if (d.kind === 'draw') { if (d.cur) {""")
    j = _sub(j, """function canDraw(){""", """function dotAt(x, y){ let best = null, bd = 12; rats().forEach((r, i) => { if (r.deleted) return; const [cx, cy] = toCv(r.u, r.v);
  const dd = Math.hypot(cx - x, cy - y); if (dd <= bd) { bd = dd; best = i; } }); return best; }
function canDraw(){""")
    j = _sub(j, """function addRat(u, v){""", """function implantClick(u, v){ const r = rat(); if (!r || r.deleted) { toast(MSG.norat); return; } const o = r.implant;
  if (o.hidden) { toast(MSG.hidden); return; }
  snap(); o.click = [Math.round(u * 10) / 10, Math.round(v * 10) / 10]; o.clicks = (o.clicks || []).concat([o.click.slice()]); o.cand = candidatesAt(u, v); o.k = 0; o.cand_src = 'click';
  log('implant_click', {u: o.click[0], v: o.click[1], n_cand: o.cand.length, n_click: o.clicks.length}); if (!o.cand.length) toast(MSG.nocand); draw(); }
function objClick(u, v){ if (S.cur.obj === 'implant') implantClick(u, v); else { bodyClick(u, v); const o = obj(); if (o && !o.cand.length) toast(MSG.nocand); } }
function selectRat(i, via){ const q = rats()[i]; if (!q) return; if (i === S.cur.ri) { draw(); return; } const from = rat() ? rat().id : null;
  S.cur.ri = i; mode = null; log('rat_select', {via: via, from: from, to: q.id});
  if (via === 'dot') toast('rat ' + q.num + ' selected (its white dot) · 已选鼠 ' + q.num + ' — zoom in to click near a dot 放大后再点白点附近'); draw(); }
function setMode(m, via){ if (S.cur.obj === m) { draw(); return; } S.cur.obj = m; mode = null; log('mode_set', {mode: m, via: via}); draw(); }
function addRat(u, v){""")
    # the pieces / log keep the click of either object (an implant click is recorded like a body click) and where the candidates came from
    for a, b, n in (("click: S.cur.obj === 'rat' ? o.click : null}", "click: o.click || null, src: o.cand_src || (S.cur.obj === 'rat' ? 'click' : 'head')}", 2),
                    ("click: S.cur.obj === 'rat' ? o.click : undefined", "click: o.click || undefined, cand_src: o.cand_src || (S.cur.obj === 'rat' ? 'click' : 'head')", 2)):
        assert j.count(a) == n, (j.count(a), a)
        j = j.replace(a, b)
    # ---- the mode is sticky: it changes only through the buttons, 1 / 2 or Tab
    j = _sub(j, """function startObj(r){ return r && r.implant.hidden ? 'rat' : 'implant'; }""", """function startObj(r){ return S.cur.obj || 'implant'; }""")
    j = _sub(j, """function advance(){ if (S.cur.obj === 'implant') { S.cur.obj = 'rat'; mode = null; log('obj_next'); draw(); } else nextRat(); }""",
             """function advance(){ nextRat(); }""")
    j = _sub(j, """function back(){ if (S.cur.obj === 'rat' && rat() && !rat().implant.hidden) { S.cur.obj = 'implant'; mode = null; draw(); return; }
  const live = liveIdx(), p = live.indexOf(S.cur.ri); if (p > 0) { S.cur.ri = live[p - 1]; S.cur.obj = 'rat'; mode = null; draw(); } else if (S.cur.fi > 0) goFrame(S.cur.fi - 1); }""",
             """function back(){ const live = liveIdx(), p = live.indexOf(S.cur.ri); if (p > 0) { S.cur.ri = live[p - 1]; mode = null; log('rat_prev'); draw(); }
  else if (S.cur.fi > 0) goFrame(S.cur.fi - 1); }""")
    j = _sub(j, """function hideImplant(){ const r = rat(); if (!r || r.deleted) return; snap(); const o = r.implant; o.hidden = !o.hidden;
  if (o.hidden) { o.box = null; o.source = null; o.rank = null; o.mask = null; o.pieces = []; o.union_box = null; o.obj_flags = {}; if (S.cur.obj === 'implant') S.cur.obj = 'rat'; }""",
             """function hideImplant(){ if (S.cur.obj !== 'implant') { toast(MSG.h_mode); return; } const r = rat(); if (!r || r.deleted) return; snap(); const o = r.implant; o.hidden = !o.hidden;
  if (o.hidden) { o.box = null; o.source = null; o.rank = null; o.mask = null; o.pieces = []; o.union_box = null; o.obj_flags = {}; }""")
    j = _sub(j, """s.next_add++; s.rats.push(r); S.cur.ri = s.rats.length - 1; S.cur.obj = 'rat'; mode = null;""",
             """s.next_add++; s.rats.push(r); S.cur.ri = s.rats.length - 1; mode = null; if (S.cur.obj === 'implant') toast(MSG.added_implant);""")
    j = _sub(j, """S.cur.ri = Math.min(o.ri, st().rats.length - 1); S.cur.obj = o.obj; log('undo'); draw(); }""",
             """S.cur.ri = Math.min(o.ri, st().rats.length - 1); log('undo'); draw(); }""")
    j = _sub(j, """  if (k === 'Tab') { const r = rat(); S.cur.obj = (S.cur.obj === 'implant' || (r && r.implant.hidden)) ? 'rat' : 'implant'; mode = null; draw(); e.preventDefault(); return; }""",
             """  if (k === 'Tab') { setMode(S.cur.obj === 'implant' ? 'rat' : 'implant', 'tab'); e.preventDefault(); return; }
  if (k === '1') { setMode('implant', 'key'); return; } if (k === '2') { setMode('rat', 'key'); return; }""")
    # ---- messages
    j = _sub(j, """  nocand: 'no candidate here — click another part of the rat, or draw by hand (B) · 这里没有候选: 点鼠的别处或手画 (B)',""",
             """  nocand: 'no candidate here — click another spot, or draw by hand (B) · 这里没有候选: 点别处或手画 (B)',""")
    j = _sub(j, """  joined: 'already joined · 已经拼接过这个 mask', mp_implant: 'M / P apply to the rat box only · 合并 / 不完整只用于鼠框'};""",
             """  joined: 'already joined · 已经拼接过这个 mask', mp_implant: 'M / P apply to the rat box only — press 2 · 合并 / 不完整只用于鼠框 (按 2)',
  h_mode: 'H (implant hidden) works in IMPLANT mode only — press 1 · H 只在植入体模式有效 (按 1)',
  added_implant: 'rat added: its implant is marked hidden — press 2 for its rat box · 已加鼠: 植入体标为看不见, 按 2 画鼠框'};""")
    # ---- banner: mode, rat i / n, arm; number chips with per-object status; mode buttons
    j = _sub(j, """  mb.textContent = (S.cur.obj === 'implant' ? 'NOW: IMPLANT box 植入体框 (orange)' : 'NOW: RAT box 整鼠框 (green) — ' + (pre ? 'click the body' : 'drag to draw'))
    + '   ·   ' + (pre ? 'PRELABEL 预标注' : 'SCRATCH 从零画框 — drag to draw, no candidates, A/N/J off');
  mb.className = 'mode-' + S.cur.obj;""",
             """  $('modetext').textContent = 'MODE ' + (S.cur.obj === 'implant' ? '植入体 IMPLANT' : '整鼠 RAT') + ' · ' + (r ? 'rat ' + r.num + ' / ' + s.rats.length : 'no rat')
    + ' · ' + (pre ? 'PRELABEL 预标注' : 'SCRATCH 从零画框 (drag to draw)');
  mb.className = 'mode-' + S.cur.obj;
  $('mb-implant').className = 'modebtn' + (S.cur.obj === 'implant' ? ' on-implant' : ''); $('mb-rat').className = 'modebtn' + (S.cur.obj === 'rat' ? ' on-rat' : '');
  const chips = s.rats.map((q, i) => '<button type="button" class="chip' + (i === S.cur.ri ? ' cur' : '') + (q.deleted ? ' del' : '') + '" data-ri="' + i
    + '" title="' + (q.origin === 'added' ? 'added rat ' : 'rat ') + q.num + ': implant ' + (q.implant.hidden ? 'hidden' : q.implant.box ? 'done' : 'not yet')
    + ', rat box ' + (q.rat.box ? 'done' : 'not yet') + '">' + (q.origin === 'added' ? '◆' : '') + q.num
    + '<span class="m mi">' + (q.implant.hidden ? 'H' : q.implant.box ? '✓' : '·') + '</span><span class="m mr">' + (q.rat.box ? '✓' : '·') + '</span></button>').join('');
  if (chips !== lastChips) { $('ratchips').innerHTML = chips; lastChips = chips; }""")
    j = _sub(j, """function panel(){""", """let lastChips = null;
function panel(){""")
    j = _sub(j, """$('redo').addEventListener('click', () => redoFrame(false));""",
             """$('redo').addEventListener('click', () => redoFrame(false));
['modebtns', 'ratchips'].forEach(id => $(id).addEventListener('mousedown', e => e.preventDefault()));      // never take the keyboard focus (Enter / Space)
$('mb-implant').addEventListener('click', () => { touch(); setMode('implant', 'button'); });
$('mb-rat').addEventListener('click', () => { touch(); setMode('rat', 'button'); });
$('ratchips').addEventListener('click', e => { const b = e.target.closest('[data-ri]'); if (!b) return; touch(); selectRat(+b.dataset.ri, 'chip'); });""")
    # ---- drawing: only the active object is bright
    j = _sub(j, """    if (r && !r.deleted) ['implant', 'rat'].forEach(k => (r[k].pieces || []).forEach(pc => { const m = f.masks[pc.mask]; if (!m) return;""",
             """    if (r && !r.deleted) [S.cur.obj].forEach(k => (r[k].pieces || []).forEach(pc => { const m = f.masks[pc.mask]; if (!m) return;""")
    j = _sub(j, """      ctx.globalAlpha = cur ? 1 : 0.4; ctx.lineWidth = (act ? 3 : cur ? 1.8 : 1.3) * lw; ctx.strokeStyle = STYLE[k].box;""",
             """      ctx.globalAlpha = act ? 1 : 0.35; ctx.lineWidth = (act ? 3 : 1.3) * lw; ctx.strokeStyle = STYLE[k].box;""")
    j = _sub(j, """    if (cur) (r.rat.clicks || []).forEach((cl, n) => { const R = 8 * lw; ctx.lineWidth = 2.5 * lw; ctx.strokeStyle = STYLE.rat.cand; ctx.globalAlpha = n === r.rat.clicks.length - 1 ? 1 : 0.5;""",
             """    if (cur) (r[S.cur.obj].clicks || []).forEach((cl, n, all) => { const R = 8 * lw; ctx.lineWidth = 2.5 * lw; ctx.strokeStyle = STYLE[S.cur.obj].cand; ctx.globalAlpha = n === all.length - 1 ? 1 : 0.5;""")
    # ---- CSV: where the candidates came from
    j = _sub(j, """n_body_clicks: (o.clicks || []).length, n_candidates: o.cand.length,""",
             """n_body_clicks: (o.clicks || []).length, n_candidates: o.cand.length, cand_src: o.cand_src || (k === 'rat' ? 'click' : 'head'),""")
    # ---- test hooks
    j = _sub(j, """  banner: () => $('modebanner').textContent, clearToast: () => { $('toast').style.display = 'none'; }};""",
             """  banner: () => $('modetext').textContent, clearToast: () => { $('toast').style.display = 'none'; },
  buttons: () => [$('mb-implant').className, $('mb-rat').className],
  chips: () => Array.from(document.querySelectorAll('#ratchips .chip')).map(b => ({ri: +b.dataset.ri, cls: b.className, text: b.textContent})),
  dotAtImg: (u, v) => { const [x, y] = toCv(u, v); return dotAt(x, y); }};""")
    assert "obj_auto_switch" not in j and "S.cur.obj = 'rat'" not in j, "an automatic mode change is left"
    return j


PAGE_JS_V23 = _make_js_v23()


def page_html_v23(run_name: str) -> str:
    h = page_html_v22(run_name).replace(PAGE_JS_V22, PAGE_JS_V23)
    h = _sub(h, "<title>In-box pre-label edit v2.2</title>", "<title>In-box pre-label edit v2.3</title>")
    h = _sub(h, "· v2.2: implant box + rat box, join pieces · 预标注编辑 v2.2</h1>", "· v2.3: two modes (implant / rat), join pieces · 预标注编辑 v2.3</h1>")
    h = _sub(h, """<b>Each rat: implant (A/N/J, H hidden) → click the body → rat box (A/N/J…) → Enter</b> 每只鼠: 植入体 (A/N/J, H 看不见) → 点身体 → 鼠框 (A/N/J…) → Enter.
A click on the image always switches to the RAT box 点击图像总是切换到鼠框.<br>""",
             """<b>Two modes 两个模式: ① IMPLANT (key 1) · ② RAT (key 2) · Tab toggles. The mode stays until you change it 模式不会自动切换.</b>
In a mode every click, key and drawn box acts on THAT box only 每个模式只改对应的框.<br>
<b>switch rat: click its white dot or its number chip · Enter/← next/prev 切换鼠：点白点或上方数字</b>
(chip marks: implant / rat box — ✓ done, H hidden, · not yet). PageDown / PageUp = next / previous frame.<br>""")
    h = _sub(h, """<span class="obj-implant">IMPLANT</span> candidates come from the head dot (cyan). <span class="obj-rat">RAT</span> (head + body, no tail):
click on the rat's body first 先点鼠身体; candidates containing that point are offered (pink).<br>""",
             """<span class="obj-implant">IMPLANT</span> candidates (cyan) come from the head dot; in IMPLANT mode a click offers the masks under the click.
<span class="obj-rat">RAT</span> (head + body, no tail): in RAT mode click the rat's body 点鼠身体; the masks under the click are offered (pink).<br>""")
    h = _sub(h, "<b>SCRATCH</b>: drag the implant box, Enter, drag the rat box 先拖植入体框, Enter, 再拖鼠框<br>",
             "<b>SCRATCH</b>: drag the box of the current mode (1 implant, 2 rat) 按当前模式手动拖框<br>")
    h = _sub(h, "H implant hidden 植入体看不见 ·", "H implant hidden (IMPLANT mode) 植入体看不见 ·")
    h = _sub(h, "Tab switch implant / rat 切换 · Enter / → next box, then next rat 下一个 ·", "1 / 2 / Tab mode 模式 · Enter / → next rat 下一只 ·")
    h = _sub(h, "← back 上一个 ·", "← previous rat 上一只 ·")
    h = _sub(h, '<div id="modebanner"></div>', '<div id="modebtns"><button type="button" id="mb-implant" class="modebtn">① 植入体 IMPLANT</button>'
                                              '<button type="button" id="mb-rat" class="modebtn">② 整鼠 RAT</button></div>'
                                              '<div id="modebanner"><span id="modetext"></span><span id="ratchips"></span></div>')
    h = _sub(h, "</style></head>", """
#modebanner{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px}
#modebtns{display:flex;gap:10px;margin:4px 0}.modebtn{font-size:18px;font-weight:800;padding:8px 18px;border-radius:8px;border:2px solid #888;
 background:#5a5a5a;color:#ddd;cursor:pointer}.modebtn.on-implant{background:#ff9f1a;border-color:#111;color:#111}
.modebtn.on-rat{background:#39ff14;border-color:#111;color:#111}
#ratchips{display:flex;flex-wrap:wrap;gap:6px}.chip{font-size:16px;font-weight:800;padding:2px 7px;border-radius:6px;border:2px solid #111;
 background:rgba(255,255,255,.85);color:#111;cursor:pointer}.chip.cur{background:#ff2fd0;color:#fff;border-color:#fff;box-shadow:0 0 0 2px #111}
.chip.del{text-decoration:line-through;opacity:.5}.chip .m{display:inline-block;min-width:13px;margin-left:3px;padding:0 2px;font-size:13px;border-radius:3px;background:#fff}
.chip .mi{color:#b35400}.chip .mr{color:#0a7d00}
</style></head>""")
    return h


def page_check_v23(new_dir: Path, data: dict, old_html: Path, old_data: Path) -> dict:
    """Headless Chrome (throwaway profile). A: old-state test — the backed-up v2.2 page saves a state (an accepted implant, a
    2-piece joined rat box with an object-level flag, a hidden implant + a manual rat box, SCRATCH boxes); v2.3 loads it under
    the same key and exports it unchanged apart from version / time / reload events. B: v2.3 — a click in each mode affects only
    that object; J in both modes; the mode persists across Enter, ← and frames; 1 / 2 / Tab and the buttons; H only in IMPLANT
    mode; a click on another rat's white dot selects it without a candidate lookup (both modes); the chips select a rat and show
    the status marks; banner text; help line; export; no network URL."""
    import inbox_identity_page as ipage
    html_t, js_t = (new_dir / "index.html").read_text(encoding="utf-8"), (new_dir / "pl_data.js").read_text(encoding="utf-8")
    res = {"network_urls": re.findall(r"https?://[^\s\"'<>]+", html_t) + re.findall(r"https?://[^\s\"'<>]+", js_t)}
    vdir = new_dir.parent if new_dir.name.startswith("_") else new_dir
    tdir = vdir / "_v22_oldstate_test"
    if tdir.exists():
        shutil.rmtree(tdir)
    tdir.mkdir()
    shutil.copy2(old_html, tdir / "index.html")
    od = _read_data_js(old_data)
    for f in od["frames"]:
        f["img"] = "../" + f["img"]
    (tdir / "pl_data.js").write_text("window.PL_DATA = " + json.dumps(od, separators=(",", ":")) + ";\n", encoding="utf-8")
    prof = Path(tempfile.mkdtemp(prefix="pl23check_"))
    p, wsu, bws = ipage._chrome((tdir / "index.html").resolve().as_uri(), prof, ipage._free_port())
    c = None
    fr = data["frames"]

    def nt(o):
        return {k: v for k, v in o.items() if k != "time_ms"}
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

        def R(i=None):
            return c.ev("JSON.parse(JSON.stringify(window.__pl.rat()))" if i is None else
                        f"JSON.parse(JSON.stringify(window.__pl.S().frames[window.__pl.frame().id].rats[{i}]))")

        def cur():
            return c.ev("window.__pl.cur()")

        def last_ev():
            return c.ev("window.__pl.S().events.slice(-1)")[0]

        def body_points(f, min_cand, away_from_dots=False):
            out = []
            for m in sorted(f["masks"], key=lambda m: -m["a"])[:40]:
                for pts in m["p"]:
                    x0, y0 = float(np.mean(pts[0::2])), float(np.mean(pts[1::2]))
                    if _pip(x0, y0, pts):
                        if away_from_dots and c.ev(f"window.__pl.dotAtImg({x0}, {y0})") is not None:
                            break
                        cand = c.ev(f"window.__pl.candidatesAt({x0}, {y0})")
                        if len(cand) >= min_cand:
                            out.append(((x0, y0), cand))
                        break
            return out
        # ---------------- A. old-state test with the backed-up v2.2 page (its auto-switch flow)
        res["loaded_v22"] = ready()
        res["v22_page_version"] = c.ev("window.__pl.D.page_version")
        pre = [i for i, f in enumerate(fr) if f["arm"] == "PRELABEL" and len(f["cand"]) >= 2 and f["cand"][0]]
        fi, pt = None, None
        for i in pre:
            c.ev(f"window.__pl.goFrame({i})")
            bp = body_points(fr[i], 2)
            if bp:
                fi, pt = i, bp[0][0]
                break
        c.ev(f"window.__pl.goFrame({fi})")
        ready()
        f = fr[fi]
        key("a")                                     # implant candidate 1
        click(*pt)                                   # v2.2: switches to the rat box
        key("j")
        key("n")
        key("j")
        key("m")
        for _ in range(3):
            c.ev("window.__pl.setLastInput(0)")
            time.sleep(0.5)
        key("Enter")
        c.ev("window.__pl.setCur(window.__pl.cur().ri, 'implant')")
        key("h")
        hu, hv = f["heads"][1]["u"], f["heads"][1]["v"]
        key("b")
        drag(hu - 120, hv - 90, hu + 160, hv + 140)
        fs = next(i for i, x in enumerate(fr) if x["arm"] == "SCRATCH")
        c.ev(f"window.__pl.goFrame({fs})")
        ready()
        g = fr[fs]
        gu, gv = g["heads"][0]["u"], g["heads"][0]["v"]
        drag(gu - 50, gv - 40, gu + 50, gv + 40)
        key("Enter")
        drag(gu - 180, gv - 140, gu + 220, gv + 180)
        c.ev(f"window.__pl.goFrame({fi})")
        c.ev("window.__pl.setLastInput(60000)")
        ex_old = c.ev("window.__pl.exportJSON()")
        c.ev("window.__pl.save()")
        old_key = c.ev("window.__pl.key")
        c.call("Page.navigate", url=(new_dir / "index.html").resolve().as_uri())
        time.sleep(1.5)
        res["loaded_v23"] = ready()
        c.ev("window.__pl.setLastInput(60000)")
        ex_new = c.ev("window.__pl.exportJSON()")
        cmp = _compare_exports(ex_old, ex_new)
        fo = next(x for x in ex_new["frames"] if x["frame_id"] == f["id"])
        r1, r2 = fo["rats"][0], fo["rats"][1]
        res["old_state"] = {**cmp, "same_storage_key": old_key == c.ev("window.__pl.key"),
                            "rat1": [r1["implant"]["source"], r1["rat"]["source"], r1["rat"]["n_pieces"], r1["rat"]["obj_flags"]],
                            "rat2": [r2["implant"]["hidden"], r2["rat"]["source"]],
                            "ok": cmp["ok"] and old_key == c.ev("window.__pl.key") and r1["implant"]["source"] == "cand" and r1["rat"]["source"] == "joined"
                            and r1["rat"]["n_pieces"] == 2 and r1["rat"]["obj_flags"].get("merged") is True and r2["implant"]["hidden"] is True
                            and r2["rat"]["source"] == "manual"}
        # ---------------- B. v2.3 on another PRELABEL frame with >= 2 rats
        fj, pts = None, None
        for i in pre:
            if i == fi or i == len(fr) - 1:
                continue
            c.ev(f"window.__pl.goFrame({i})")
            bp = body_points(fr[i], 2, away_from_dots=True)
            if bp:
                fj, pts = i, bp[0]
                break
        c.ev(f"window.__pl.goFrame({fj})")
        ready()
        (pu, pv), pc = pts
        ri0 = cur()["ri"]
        key("1")
        m0 = cur()["obj"]
        before = R()
        click(pu, pv)                                # IMPLANT mode: implant candidates at the click; the rat box untouched
        a1 = R()
        e1 = last_ev()["ev"]
        res["click_implant_mode"] = {"mode": m0, "n_cand": len(a1["implant"]["cand"]), "implant_click": a1["implant"]["click"], "last_event": e1,
                                     "ok": m0 == "implant" and a1["implant"]["cand"] == pc and a1["implant"]["click"] is not None
                                     and a1["implant"].get("cand_src") == "click" and nt(a1["rat"]) == nt(before["rat"]) and cur()["obj"] == "implant"
                                     and e1 == "implant_click"}
        key("j")                                     # J in IMPLANT mode
        ji = R()
        key("2")
        b1 = R()
        click(pu, pv)                                # RAT mode: rat candidates; the implant box untouched
        a2 = R()
        e2 = last_ev()["ev"]
        res["click_rat_mode"] = {"mode": cur()["obj"], "n_cand": len(a2["rat"]["cand"]), "last_event": e2,
                                 "ok": cur()["obj"] == "rat" and a2["rat"]["cand"] == pc and nt(a2["implant"]) == nt(b1["implant"]) and e2 == "body_click"}
        key("j")
        key("n")
        key("j")
        jr = R()
        res["join_both_modes"] = {"implant": [ji["implant"]["source"], len(ji["implant"]["pieces"]),
                                              ji["implant"]["pieces"][0].get("src") if ji["implant"]["pieces"] else None],
                                  "rat": [jr["rat"]["source"], len(jr["rat"]["pieces"])],
                                  "ok": ji["implant"]["source"] == "cand" and len(ji["implant"]["pieces"]) == 1 and ji["implant"]["pieces"][0].get("src") == "click"
                                  and nt(ji["rat"]) == nt(before["rat"]) and jr["rat"]["source"] == "joined" and len(jr["rat"]["pieces"]) == 2
                                  and nt(jr["implant"]) == nt(ji["implant"])}
        ch0 = c.ev("window.__pl.chips()")           # rat 1 now has both boxes: ✓ ✓
        # sticky mode: Enter, ←, next frame, previous frame
        key("Enter")
        c1 = cur()
        key("ArrowLeft")
        c2 = cur()
        key("PageDown")
        c3 = cur()
        key("PageUp")
        c4 = cur()
        res["sticky"] = {"after_enter": c1, "after_left": c2, "after_pagedown": c3, "after_pageup": c4,
                         "ok": all(x["obj"] == "rat" for x in (c1, c2, c3, c4)) and c1["ri"] != ri0 and c2["ri"] == ri0
                         and c3["fi"] == fj + 1 and c4["fi"] == fj}
        # keys and buttons
        key("Tab")
        t1 = cur()["obj"]
        key("Tab")
        t2 = cur()["obj"]
        key("1")
        k1 = cur()["obj"]
        b_impl = c.ev("window.__pl.banner()")
        btn_impl = c.ev("window.__pl.buttons()")
        key("2")
        k2 = cur()["obj"]
        b_rat = c.ev("window.__pl.banner()")
        btn_rat = c.ev("window.__pl.buttons()")
        c.ev("document.getElementById('mb-implant').click()")
        bt1 = cur()["obj"]
        c.ev("document.getElementById('mb-rat').click()")
        bt2 = cur()["obj"]
        ms = [e for e in c.ev("window.__pl.S().events") if e["ev"] == "mode_set"]
        res["keys_buttons"] = {"tab": [t1, t2], "one_two": [k1, k2], "buttons": [bt1, bt2], "mode_set_via": sorted({e["via"] for e in ms}),
                               "ok": {t1, t2} == {"implant", "rat"} and t1 != t2 and k1 == "implant" and k2 == "rat" and bt1 == "implant" and bt2 == "rat"
                               and {"tab", "key", "button"} <= {e["via"] for e in ms}}
        # H: refused in RAT mode, works in IMPLANT mode (and the mode stays)
        c.ev("window.__pl.clearToast()")
        hb = R()
        key("h")
        t_h = c.ev("window.__pl.toast()")
        h_rat_ok = R()["implant"]["hidden"] == hb["implant"]["hidden"]
        key("1")
        key("h")
        h_impl = R()["implant"]["hidden"]
        res["h_key"] = {"toast_in_rat_mode": t_h, "hidden_in_implant_mode": h_impl, "mode_after": cur()["obj"],
                        "ok": "IMPLANT mode only" in t_h and h_rat_ok and h_impl is True and cur()["obj"] == "implant"}
        # chips: number, highlight, marks; select a rat by its chip
        chs = c.ev("window.__pl.chips()")
        cri = cur()["ri"]
        other = next(q["ri"] for q in chs if q["ri"] != cri)
        c.ev(f"document.querySelector('#ratchips [data-ri=\"{other}\"]').click()")
        c_chip = cur()
        ev_chip = last_ev()
        chs2 = c.ev("window.__pl.chips()")
        n_rats_f = len(c.ev("window.__pl.S().frames[window.__pl.frame().id].rats"))
        chip_worked = next(q for q in ch0 if q["ri"] == ri0)["text"]
        chip_hidden = next(q for q in chs if q["ri"] == cri)["text"]
        res["chips"] = {"n": len(chs), "n_rats": n_rats_f, "chip_after_work": chip_worked, "chip_after_hidden": chip_hidden,
                        "after_chip_click": c_chip, "event": ev_chip,
                        "ok": len(chs) == n_rats_f and sum("cur" in q["cls"].split() for q in chs) == 1 and "cur" in next(q for q in chs if q["ri"] == cri)["cls"].split()
                        and chip_worked.endswith("✓✓") and chip_hidden.endswith("H✓") and c_chip["ri"] == other and c_chip["obj"] == "implant"
                        and ev_chip["ev"] == "rat_select" and ev_chip["via"] == "chip" and "cur" in next(q for q in chs2 if q["ri"] == other)["cls"].split()}
        # a click on ANOTHER rat's white dot selects it without a candidate lookup — in IMPLANT mode, then in RAT mode
        dots = []
        for mode_key in ("1", "2"):
            key(mode_key)
            ri_now = cur()["ri"]
            tgt = next(i for i in range(n_rats_f) if i != ri_now and not R(i)["deleted"])
            hd = R(tgt)
            before_t = {k: nt(hd[k]) for k in ("implant", "rat")}
            n_ev = len(c.ev("window.__pl.S().events"))
            click(hd["u"], hd["v"])
            after = R(tgt)
            new_ev = c.ev(f"window.__pl.S().events.slice({n_ev})")
            dots.append({"mode": cur()["obj"], "to": tgt, "ri_after": cur()["ri"], "events": [e["ev"] for e in new_ev],
                         "ok": cur()["ri"] == tgt and cur()["obj"] == ("implant" if mode_key == "1" else "rat")
                         and {k: nt(after[k]) for k in ("implant", "rat")} == before_t and [e["ev"] for e in new_ev] == ["rat_select"]
                         and new_ev[0]["via"] == "dot"})
        # the current rat's own dot is a normal click for the active object (the rat is already selected)
        key("1")
        if R()["implant"]["hidden"]:
            key("h")
        own, ri_own = R(), cur()["ri"]
        click(own["u"], own["v"])
        own_ev = last_ev()["ev"]
        dots.append({"own_dot_event": own_ev, "ok": own_ev == "implant_click" and cur()["ri"] == ri_own})
        res["dot_select"] = {"cases": dots, "ok": all(d["ok"] for d in dots)}
        # SCRATCH banner
        fs2 = next(i for i, x in enumerate(fr) if x["arm"] == "SCRATCH" and i != fs)
        c.ev(f"window.__pl.goFrame({fs2})")
        b_scr = c.ev("window.__pl.banner()")
        res["banner"] = {"implant": b_impl, "rat": b_rat, "scratch": b_scr, "buttons_implant": btn_impl, "buttons_rat": btn_rat,
                         "ok": b_impl.startswith("MODE 植入体 IMPLANT · rat ") and b_impl.endswith("PRELABEL 预标注")
                         and b_rat.startswith("MODE 整鼠 RAT · rat ") and b_scr.endswith("SCRATCH 从零画框 (drag to draw)")
                         and "on-implant" in btn_impl[0] and "on-rat" not in btn_impl[1] and "on-rat" in btn_rat[1] and "on-implant" not in btn_rat[0]}
        res["help_legend"] = {"ok": bool(c.ev("document.body.textContent.includes('switch rat: click its white dot or its number chip · Enter/← next/prev 切换鼠：点白点或上方数字')")
                                         and c.ev("!!document.getElementById('legend') && document.getElementById('legend').textContent.includes('rat candidate')"))}
        ej = c.ev("window.__pl.exportJSON()")
        n_rats = sum(len(x["rats"]) for x in ej["frames"])
        csv_head = c.ev("window.__pl.exportCSV().split('\\n')[0]")
        csv_lines = c.ev("window.__pl.exportCSV().trim().split('\\n').length")
        new_evs = [e["ev"] for e in ej["events"][len(ex_old["events"]):]]
        res["export"] = {"version": ej["page_version"], "csv_lines": csv_lines, "event_kinds_new": sorted(set(new_evs)),
                         "ok": ej["page_version"] == PAGE_VERSION_V23 and csv_lines == 2 * n_rats + 1 and "cand_src" in csv_head
                         and {"mode_set", "implant_click", "body_click", "join", "rat_select", "rat_prev"} <= set(new_evs) and "obj_auto_switch" not in new_evs}
        c.ev("localStorage.clear()")
    finally:
        if c:
            c.close()
        ipage._close_chrome(p, bws)
        shutil.rmtree(prof, ignore_errors=True)
        shutil.rmtree(tdir, ignore_errors=True)
    keys = ["old_state", "click_implant_mode", "click_rat_mode", "join_both_modes", "sticky", "keys_buttons", "h_key", "chips", "dot_select",
            "banner", "help_legend", "export"]
    res["verdict"] = "PASS" if (res.get("loaded_v22") and res.get("loaded_v23") and all(res[k]["ok"] for k in keys) and not res["network_urls"]) else "FAIL"
    return res


def update_v23(run: Path, check: bool = True) -> dict:
    """In-place v2.2 -> v2.3 (two sticky modes, rat switching). Same storage key; *.v2_2.bak backups first; payload verified
    identical to v2.2; a staged copy is checked (incl. the old-state test) before the live files are replaced."""
    out = run / "prelabel_edit_v2"
    cur = _read_data_js(out / "pl_data.js")
    if cur["page_version"] == PAGE_VERSION_V22:
        for name in ("index.html", "pl_data.js", "page_check.json", "build_meta.json"):
            src, bak = out / name, out / f"{name}.v2_2.bak"
            if src.exists() and not bak.exists():
                shutil.copy2(src, bak)
    old = _read_data_js(out / "pl_data.js.v2_2.bak")
    assert old["page_version"] == PAGE_VERSION_V22, f"the backup is not v2.2: {old['page_version']}"
    key = old["storage_key"]
    new = _v2_data(run, PAGE_VERSION_V23, key, [PAGE_VERSION_V2, PAGE_VERSION_V21, PAGE_VERSION_V22, PAGE_VERSION_V23])
    same = len(old["frames"]) == len(new["frames"]) and all(a[k] == b[k] for a, b in zip(old["frames"], new["frames"])
                                                            for k in ("id", "domain", "arm", "pile_bin", "order", "img", "heads", "masks", "cand"))
    if not same:
        raise SystemExit("v2.3 payload differs from v2.2: not written, v2.2 left in place")
    js_final = "window.PL_DATA = " + json.dumps(new, separators=(",", ":")) + ";\n"
    html_final = page_html_v23(run.name)
    pc = None
    if check:
        stg = out / "_v23_staging"
        if stg.exists():
            shutil.rmtree(stg)
        stg.mkdir()
        staged = json.loads(json.dumps(new))
        for f in staged["frames"]:
            f["img"] = "../" + f["img"]
        (stg / "pl_data.js").write_text("window.PL_DATA = " + json.dumps(staged, separators=(",", ":")) + ";\n", encoding="utf-8")
        (stg / "index.html").write_text(html_final, encoding="utf-8")
        try:
            pc = page_check_v23(stg, new, out / "index.html.v2_2.bak", out / "pl_data.js.v2_2.bak")
        finally:
            shutil.rmtree(stg, ignore_errors=True)
        print(f"v2.3 page check (staged): {pc['verdict']}", flush=True)
        if pc["verdict"] != "PASS":
            S.write_json(out / "page_check_v2_3_FAILED.json", pc)
            raise SystemExit("v2.3 check failed: the live v2.2 page was NOT replaced (see page_check_v2_3_FAILED.json)")
    (out / "pl_data.js").write_text(js_final, encoding="utf-8")
    (out / "index.html").write_text(html_final, encoding="utf-8")
    meta = json.loads((out / "build_meta.json.v2_2.bak").read_text(encoding="utf-8"))
    meta["v2_3"] = {"made": datetime.now().isoformat(timespec="seconds"),
                    "why": "two explicit sticky modes (implant / rat), no auto-switch; rat chips, white-dot select, Enter / ← next / previous rat",
                    "page_version": PAGE_VERSION_V23, "storage_key": key, "payload_identical_to_v2_2": same,
                    "backups": sorted(q.name for q in out.glob("*.bak")), "page_check": pc["verdict"] if pc else "not run", "git_commit": git_commit()}
    if pc:
        S.write_json(out / "page_check.json", pc)
    S.write_json(out / "build_meta.json", meta)
    return meta


# ============================================================================================ v2.4: mask panel, drag handles, split status
PAGE_VERSION_V24 = "inbox_sam3_prelabel_edit_2026c_v2.4"


def _make_js_v24() -> str:
    """v2.3 -> v2.4. The user: "右侧显示一列 哪些mask被包括进了当前选择 … 直接点击删除不是的mask。另外我发现没法更改implant的框" and
    "这明明已经画上了为啥没有候选". (1) a right-side panel for the active object: the masks in the box (× removes, hover
    highlights) and the candidates at the last click / head dot (click = current, + = join); (2) visible drag handles on the
    active box (corners move two edges, nearest handle only, hit radius 10 screen px, priority over the head dot and
    click-for-candidates), a drag on the yellow bbox of an un-accepted candidate accepts it and then resizes, a minimum box
    size, a toast for a drag on the inactive box; (3) the status per object split into "Box 框" and "Last click 上次点击"."""
    j = PAGE_JS_V23
    # ---- state for the panel / hover
    j = _sub(j, "let view = null, mode = null, drag = null, spaceDown = false, showAll = false;",
             "let view = null, mode = null, drag = null, spaceDown = false, showAll = false;\nlet hoverMask = null, lastHL = null, lastPanel = null;")
    # ---- grabbing: handles (nearest, 10 screen px) then one edge (8 px); never several edges of a small box at once
    old_edge = j[j.index("function edgeAt(x, y){"):j.index("  return e.length ? e : null; }") + len("  return e.length ? e : null; }")]
    assert j.count(old_edge) == 1
    j = j.replace(old_edge, """function handlesOf(b){ const [x0, y0] = toCv(b[0], b[1]), [x1, y1] = toCv(b[2], b[3]), mx = (x0 + x1) / 2, my = (y0 + y1) / 2;
  const hs = [{x: x0, y: y0, e: [0, 1]}, {x: x1, y: y0, e: [2, 1]}, {x: x0, y: y1, e: [0, 3]}, {x: x1, y: y1, e: [2, 3]}];
  if (Math.abs(y1 - y0) >= 30) { hs.push({x: x0, y: my, e: [0], mid: true}); hs.push({x: x1, y: my, e: [2], mid: true}); }
  if (Math.abs(x1 - x0) >= 30) { hs.push({x: mx, y: y0, e: [1], mid: true}); hs.push({x: mx, y: y1, e: [3], mid: true}); }
  return hs; }
function grabAt(b, x, y){ let best = null, bd = 10; handlesOf(b).forEach(h => { const d = Math.hypot(h.x - x, h.y - y); if (d <= bd) { bd = d; best = {edges: h.e.slice(), handle: true}; } });
  if (best) return best; const [x0, y0] = toCv(b[0], b[1]), [x1, y1] = toCv(b[2], b[3]), t = 8, c = [];
  if (y > y0 - t && y < y1 + t) { c.push([Math.abs(x - x0), 0]); c.push([Math.abs(x - x1), 2]); }
  if (x > x0 - t && x < x1 + t) { c.push([Math.abs(y - y0), 1]); c.push([Math.abs(y - y1), 3]); }
  const hit = c.filter(q => q[0] < t).sort((a, b2) => a[0] - b2[0]); return hit.length ? {edges: [hit[0][1]], handle: false} : null; }
function candInBox(o, c){ return !!o.box && o.source !== 'manual' && (o.pieces || []).some(p => p.mask === c); }
function grabBox(x, y){ const o = obj(), r = rat(); if (!r || !o || !o.box || r.deleted || showAll) return null; return grabAt(o.box, x, y); }
function grabCand(x, y){ if (showAll || mode === 'draw' || st().arm !== 'PRELABEL') return null; const o = obj(), c = curCand(); if (!o || c === null || candInBox(o, c)) return null;
  const g = grabAt(fr().masks[c].b, x, y); return g ? Object.assign(g, {cand: c}) : null; }
function grabOther(x, y){ const r = rat(); if (!r || r.deleted || showAll) return null; const k = S.cur.obj === 'implant' ? 'rat' : 'implant';
  return r[k].box && grabAt(r[k].box, x, y) ? k : null; }""")
    # ---- mousedown: active box (handles first) > un-accepted candidate bbox > draw > press (with the inactive-box flag)
    j = _sub(j, """  const dot = dotAt(x, y);
  const ed = edgeAt(x, y); if (ed) { drag = {kind: 'edge', edges: ed, b0: obj().box.slice(), dot: dot, x0: e.clientX, y0: e.clientY}; return; }
  if (canDraw()) { drag = {kind: 'draw', start: [u, v], cur: null, dot: dot, x0: e.clientX, y0: e.clientY}; return; }
  drag = {kind: 'press', x0: e.clientX, y0: e.clientY, ox: view.ox, oy: view.oy, u: u, v: v, moved: false, dot: dot}; });""",
             """  const dot = dotAt(x, y);
  const g = grabBox(x, y); if (g) { drag = {kind: 'edge', edges: g.edges, handle: g.handle, b0: obj().box.slice(), dot: g.handle ? null : dot, x0: e.clientX, y0: e.clientY}; return; }
  const gc = grabCand(x, y); if (gc) { drag = {kind: 'cedge', edges: gc.edges, handle: gc.handle, cand: gc.cand, accepted: false, dot: dot, x0: e.clientX, y0: e.clientY, u: u, v: v}; return; }
  const wrong = grabOther(x, y);
  if (canDraw() && !wrong) { drag = {kind: 'draw', start: [u, v], cur: null, dot: dot, x0: e.clientX, y0: e.clientY}; return; }
  drag = {kind: 'press', x0: e.clientX, y0: e.clientY, ox: view.ox, oy: view.oy, u: u, v: v, moved: false, dot: dot, wrong: wrong}; });""")
    j = _sub(j, """  if (!drag) { cv.style.cursor = showAll ? 'pointer' : edgeAt(x, y) ? 'move' : (canDraw() || mode === 'add' || (S.cur.obj === 'rat' && st().arm === 'PRELABEL')) ? 'crosshair' : 'grab'; return; }
  if (drag.kind === 'press') { if (Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) > 4) drag.moved = true; if (drag.moved) {""",
             """  if (!drag) { cv.style.cursor = showAll ? 'pointer' : (grabBox(x, y) || grabCand(x, y)) ? 'move' : (canDraw() || mode === 'add' || st().arm === 'PRELABEL') ? 'crosshair' : 'grab'; return; }
  if (drag.kind === 'press') { if (Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) > 4) drag.moved = true;
    if (drag.moved && drag.wrong) { if (!drag.told) { drag.told = true; toast(drag.wrong === 'implant' ? MSG.wrong_implant : MSG.wrong_rat); log('wrong_mode_edit', {box: drag.wrong}); } return; }
    if (drag.moved) {""")
    j = _sub(j, """  if (drag.kind === 'edge') { const b = obj().box; drag.edges.forEach(k => { b[k] = (k % 2 === 0) ? u : v; }); draw(); } });""",
             """  if (drag.kind === 'cedge' && !drag.accepted) { if (Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) <= 3) return;
    accept(); const o = obj(); if (!o || !o.box || o.mask !== drag.cand) { drag = null; draw(); return; }
    log('cand_drag_accept', {rank: o.rank, mask: drag.cand, edges: drag.edges}); drag.accepted = true; drag.b0 = o.box.slice(); drag.dot = null; }
  if (drag.kind === 'edge' || drag.kind === 'cedge') { const b = obj().box; drag.edges.forEach(k => { b[k] = (k % 2 === 0) ? u : v; }); draw(); } });""")
    # ---- mouseup
    j = _sub(j, """  if (d.kind === 'press') { if (!d.moved && dotHit) { selectRat(d.dot, 'dot'); return; }""",
             """  if (d.kind === 'cedge') { if (!d.accepted) { if (dotHit) { selectRat(d.dot, 'dot'); return; } if (st().arm === 'PRELABEL' && mode !== 'draw' && !showAll) objClick(d.u, d.v); return; }
    d.kind = 'edge'; d.via = 'candidate_bbox'; }
  if (d.kind === 'press' && d.wrong && !d.moved && st().arm !== 'PRELABEL') { toast(d.wrong === 'implant' ? MSG.wrong_implant : MSG.wrong_rat); log('wrong_mode_edit', {box: d.wrong}); return; }
  if (d.kind === 'press') { if (!d.moved && dotHit) { selectRat(d.dot, 'dot'); return; }""")
    j = _sub(j, """  if (d.kind === 'edge') { const o = obj(), b = normBox([o.box[0], o.box[1]], [o.box[2], o.box[3]]); const moved = b.some((x, i) => Math.abs(x - d.b0[i]) > 0.5);
    if (moved) { const nb = b.map(x => Math.round(x * 10) / 10); o.box = d.b0; snap(); o.box = nb; o.edge_moves++; log('edge_move', {from: d.b0, to: nb, edges: d.edges}); } else o.box = d.b0; draw(); } });""",
             """  if (d.kind === 'edge') { const o = obj(), b = normBox([o.box[0], o.box[1]], [o.box[2], o.box[3]]);
    if (b[2] - b[0] < 2) b[2] = b[0] + 2; if (b[3] - b[1] < 2) b[3] = b[1] + 2;
    const moved = b.some((x, i) => Math.abs(x - d.b0[i]) > 0.5);
    if (moved) { const nb = b.map(x => Math.round(x * 10) / 10); o.box = d.b0; snap(); o.box = nb; o.edge_moves++;
      log('edge_move', {from: d.b0, to: nb, edges: d.edges, handle: !!d.handle, via: d.via || 'box'}); } else o.box = d.b0; draw(); } });""")
    # ---- drawing: hover highlight; handles of the active box (filled) and of an un-accepted candidate's bbox (hollow, yellow)
    j = _sub(j, """      drawnMasks = 1; ctx.lineWidth = 2 * lw; ctx.strokeStyle = '#ffd400'; ctx.strokeRect(m.b[0], m.b[1], m.b[2] - m.b[0], m.b[3] - m.b[1]); ctx.setLineDash([]); }""",
             """      drawnMasks = 1; ctx.lineWidth = 2 * lw; ctx.strokeStyle = '#ffd400'; ctx.strokeRect(m.b[0], m.b[1], m.b[2] - m.b[0], m.b[3] - m.b[1]); ctx.setLineDash([]); }
    if (hoverMask !== null && f.masks[hoverMask]) { const m = f.masks[hoverMask];
      m.p.forEach(p => { const P = polyPath(p); ctx.globalAlpha = 0.35; ctx.fillStyle = '#ffffff'; ctx.fill(P); ctx.globalAlpha = 1; ctx.lineWidth = 4 * lw; ctx.strokeStyle = '#ffffff'; ctx.stroke(P);
        ctx.lineWidth = 1.5 * lw; ctx.strokeStyle = '#000'; ctx.stroke(P); }); lastHL = hoverMask; }""")
    j = _sub(j, """  const lw = 1 / view.s; drawnMasks = 0;""", """  const lw = 1 / view.s; drawnMasks = 0; lastHL = null;""")
    j = _sub(j, "  ctx.setTransform(1, 0, 0, 1, 0, 0);\n  panel();\n}",
             """  ctx.setTransform(1, 0, 0, 1, 0, 0);
  if (!showAll) { const r = rat(), o = obj(); if (r && !r.deleted && o) { const c = curCand();
    if (c !== null && !candInBox(o, c) && st().arm === 'PRELABEL') drawHandles(f.masks[c].b, '#ffd400', true); if (o.box) drawHandles(o.box, STYLE[S.cur.obj].box, false); } }
  panel();
}
function drawHandles(b, col, hollow){ handlesOf(b).forEach(h => { const z = h.mid ? 8 : 10; ctx.fillStyle = hollow ? 'rgba(0,0,0,0.45)' : col;
  ctx.fillRect(h.x - z / 2, h.y - z / 2, z, z); ctx.lineWidth = 1.5; ctx.strokeStyle = hollow ? col : '#000'; ctx.strokeRect(h.x - z / 2, h.y - z / 2, z, z); }); }""")
    # ---- status per object: "Box 框" and "Last click 上次点击" kept apart
    i0 = j.index("function objText(r, k){")
    i1 = j.index("  return t; }", i0) + len("  return t; }")
    j = j[:i0] + """function objText(r, k){ const o = r[k], pre = st().arm === 'PRELABEL';
  if (k === 'implant' && o.hidden) return '<span class="st-box">implant hidden 植入体看不见 (H)</span>';
  let b = 'Box 框: ';
  if (o.box) { b += '✓ done — ' + (o.source === 'manual' ? 'hand-drawn' : o.source === 'joined' ? (o.pieces || []).length + ' joined masks' : '1 mask (candidate ' + o.rank + ')')
      + (o.edge_moves ? ', ' + o.edge_moves + ' edge move(s)' : '');
    const fl = o.source === 'joined' ? (o.obj_flags || {}) : (o.rank ? (o.cand_flags[o.rank] || {}) : {});
    if (k === 'rat' && (fl.merged || fl.partial)) b += ', flagged ' + [fl.merged ? 'merged' : '', fl.partial ? 'partial' : ''].filter(Boolean).join(' + '); }
  else b += '— not yet 未标';
  let c = 'Last click 上次点击: ';
  if (!pre) c += '— (SCRATCH: draw by hand 手画)';
  else if (!o.click) c += 'no click yet 还没点' + (k === 'implant' ? (o.cand.length ? ' — head dot: ' + (o.k < o.cand.length ? (o.k + 1) + ' of ' + o.cand.length + ' candidates' : 'none usable of ' + o.cand.length) : ' — no mask at the head dot') : '');
  else if (!o.cand.length) c += 'no mask under this point (box unchanged) 这里没有 mask，框没变';
  else c += o.k < o.cand.length ? (o.k + 1) + ' of ' + o.cand.length + ' candidates' + (candInBox(o, o.cand[o.k]) ? ' (in the box 已含)' : '') : 'none usable shown — N cycles 无可用 (N 切换)';
  return '<span class="st-box">' + b + '</span><br>&emsp;<span class="st-click">' + c + '</span>'; }""" + j[i1:]
    # ---- messages
    j = _sub(j, """  nocand: 'no candidate here — click another spot, or draw by hand (B) · 这里没有候选: 点别处或手画 (B)',""",
             """  nocand: 'no mask under this point (box unchanged 框没变) — click another spot, or draw by hand (B) · 这里没有 mask',
  nocand_head: 'no mask at the head dot — click on the object, or draw by hand (B) · 头点没有 mask: 点该物体或手画 (B)',
  wrong_implant: 'switch to ① IMPLANT (press 1) to edit this box 按 1 切到植入体模式再改',
  wrong_rat: 'switch to ② RAT (press 2) to edit this box 按 2 切到整鼠模式再改',""")
    j = _sub(j, "  if (!o.cand.length) return MSG.nocand; if (o.k >= o.cand.length) return MSG.none; return null; }",
             "  if (!o.cand.length) return o.click ? MSG.nocand : MSG.nocand_head; if (o.k >= o.cand.length) return MSG.none; return null; }")
    # ---- join from the panel; piece removal; clearing a hand-drawn box; picking a candidate
    j = _sub(j, "function join(){", "function join(via){")
    j = _sub(j, "n_pieces: o.pieces.length, box: o.box}); draw(); }", "n_pieces: o.pieces.length, box: o.box, via: via || 'key'}); draw(); }")
    j = _sub(j, "function addRat(u, v){", """function pickCand(i, via){ const o = obj(); if (!o || i < 0 || i >= o.cand.length || o.k === i) return; snap(); o.k = i;
  log('cand_pick', {rank: i + 1, mask: o.cand[i], via: via}); draw(); }
function removePiece(i){ const o = obj(); if (!o || !(o.pieces || []).length || i < 0 || i >= o.pieces.length || o.source === 'manual') return; snap();
  const pc = o.pieces.splice(i, 1)[0], had = Object.assign({}, o.obj_flags || {});
  if (!o.pieces.length) { o.box = null; o.source = null; o.rank = null; o.mask = null; o.union_box = null; o.obj_flags = {}; }
  else { o.box = unionBox(o.pieces); o.union_box = o.box.slice();
    if (o.pieces.length === 1) { o.source = 'cand'; o.rank = o.pieces[0].rank; o.mask = o.pieces[0].mask; o.obj_flags = {}; } else { o.source = 'joined'; o.rank = null; o.mask = null; } }
  hoverMask = null; log('piece_remove', {mask: pc.mask, rank: pc.rank, n_pieces_left: o.pieces.length, box: o.box, flags_cleared: o.pieces.length < 2 && Object.keys(had).length ? had : undefined}); draw(); }
function clearBox(){ const o = obj(); if (!o || !o.box) return; snap(); const from = o.source; o.box = null; o.source = null; o.rank = null; o.mask = null; o.pieces = [];
  o.union_box = null; o.obj_flags = {}; hoverMask = null; log('box_clear', {from: from}); draw(); }
function mInfo(f, j){ const m = f.masks[j]; return 'area ' + m.a.toLocaleString('en-US') + ' px · score ' + m.s.toFixed(2); }
function objPanel(){ const f = fr(), s = st(), r = rat(), k = S.cur.obj, o = r ? r[k] : null;
  let h = '<div class="op-h obj-' + k + '">' + (k === 'implant' ? 'IMPLANT box 植入体框' : 'RAT box 整鼠框') + (r ? ' · rat ' + r.num : '') + '</div>';
  if (!r || r.deleted || !o) h += '<div class="op-note">no rat selected 没有选中的鼠</div>';
  else if (k === 'implant' && o.hidden) h += '<div class="op-note">implant hidden (H) 植入体看不见</div>';
  else { h += '<div class="op-t">In this box 当前框包含的 mask</div>';
    if (o.box && o.source === 'manual') h += '<div class="op-row op-in" data-kind="manual"><span>hand-drawn 手画 [' + o.box.map(x => Math.round(x)).join(', ') + ']</span>'
      + '<button type="button" class="op-x" data-act="clear" title="clear this box 清除">×</button></div>';
    else if (o.box && (o.pieces || []).length) o.pieces.forEach((p, i) => { h += '<div class="op-row op-in" data-mask="' + p.mask + '"><span>#' + (p.rank || '?') + ' · ' + mInfo(f, p.mask) + '</span>'
      + '<button type="button" class="op-x" data-act="rm" data-i="' + i + '" title="remove this mask from the box 移除">×</button></div>'; });
    else h += '<div class="op-note">empty 空 — A accept / J join / + a candidate, or B draw</div>';
    if (o.box && o.source !== 'manual' && o.union_box && o.box.some((x, i) => Math.abs(x - o.union_box[i]) > 0.5)) h += '<div class="op-note">edges adjusted by hand 已手动调边 (× refits to the masks 移除后按 mask 重算)</div>';
    if (s.arm === 'PRELABEL') { h += '<div class="op-t">Candidates at ' + (o.click ? 'your click 点击处候选' : 'the head dot 头点候选') + '</div>';
      if (k === 'rat' && !o.click) h += '<div class="op-note">click the rat\\'s body first 先点鼠身体</div>';
      else if (!o.cand.length) h += '<div class="op-note">' + (o.click ? 'no mask under this point 这里没有 mask' : 'no mask at the head dot 头点没有 mask') + '</div>';
      else o.cand.forEach((jm, i) => { const inb = candInBox(o, jm); h += '<div class="op-row op-c' + (i === o.k ? ' cur' : '') + (inb ? ' inb' : '') + '" data-mask="' + jm + '" data-i="' + i + '"><span>#' + (i + 1) + ' · '
        + mInfo(f, jm) + (inb ? ' · in box 已含' : '') + (i === o.k ? ' · current 当前' : '') + '</span>'
        + (inb ? '' : '<button type="button" class="op-x op-plus" data-act="join" data-i="' + i + '" title="join into the box 拼接 (= J)">+</button>') + '</div>'; }); }
    else h += '<div class="op-note">SCRATCH: no candidates, draw by hand 手画</div>'; }
  if (h !== lastPanel) { $('objpanel').innerHTML = h; lastPanel = h; } }
function addRat(u, v){""")
    j = _sub(j, "  if (chips !== lastChips) { $('ratchips').innerHTML = chips; lastChips = chips; }",
             "  if (chips !== lastChips) { $('ratchips').innerHTML = chips; lastChips = chips; }\n  objPanel();")
    j = _sub(j, "$('ratchips').addEventListener('click', e => {", """$('objpanel').addEventListener('mousedown', e => e.preventDefault());
$('objpanel').addEventListener('mouseover', e => { const row = e.target.closest('[data-mask]'); const m = row ? +row.dataset.mask : null; if (m !== hoverMask) { hoverMask = m; draw(); } });
$('objpanel').addEventListener('mouseleave', () => { if (hoverMask !== null) { hoverMask = null; draw(); } });
$('objpanel').addEventListener('click', e => { touch(); const b = e.target.closest('[data-act]');
  if (b) { const i = +b.dataset.i; if (b.dataset.act === 'rm') removePiece(i); else if (b.dataset.act === 'clear') clearBox();
    else if (b.dataset.act === 'join') { pickCand(i, 'panel_plus'); join('panel'); hoverMask = null; draw(); } return; }
  const row = e.target.closest('.op-c'); if (row) pickCand(+row.dataset.i, 'panel'); });
$('ratchips').addEventListener('click', e => {""")
    # ---- test hooks
    j = _sub(j, "  dotAtImg: (u, v) => { const [x, y] = toCv(u, v); return dotAt(x, y); }};",
             """  dotAtImg: (u, v) => { const [x, y] = toCv(u, v); return dotAt(x, y); },
  hover: () => hoverMask, hl: () => lastHL, statusText: () => $('status').textContent, origin: () => [view.ox, view.oy], scale: () => view.s,
  handlesClient: (which, k) => { const r = rat(), r0 = cv.getBoundingClientRect(); let b = null;
    if (which === 'box') { const o = r ? r[k || S.cur.obj] : null; b = o && o.box; } else { const c = curCand(); b = c !== null ? fr().masks[c].b : null; }
    return b ? handlesOf(b).map(h => ({x: h.x + r0.left, y: h.y + r0.top, e: h.e, mid: !!h.mid})) : []; },
  grabInfo: (cx, cy) => { const r0 = cv.getBoundingClientRect(), x = cx - r0.left, y = cy - r0.top; return {box: grabBox(x, y), cand: grabCand(x, y), other: grabOther(x, y)}; }};""")
    assert "edgeAt(" not in j
    return j


PAGE_JS_V24 = _make_js_v24()


def page_html_v24(run_name: str) -> str:
    h = page_html_v23(run_name).replace(PAGE_JS_V23, PAGE_JS_V24)
    h = _sub(h, "<title>In-box pre-label edit v2.3</title>", "<title>In-box pre-label edit v2.4</title>")
    h = _sub(h, "· v2.3: two modes (implant / rat), join pieces · 预标注编辑 v2.3</h1>", "· v2.4: two modes, mask panel, drag handles · 预标注编辑 v2.4</h1>")
    h = _sub(h, "In a mode every click, key and drawn box acts on THAT box only 每个模式只改对应的框.<br>",
             """In a mode every click, key and drawn box acts on THAT box only 每个模式只改对应的框.<br>
<b>Right panel 右侧:</b> the masks in this box (× removes one; hover = highlight) and the candidates (click = show, + = join) 当前框的 mask (× 删除) 与候选 (+ 拼接).
<b>Resize: drag the square handles</b> (corners move two edges) 拖方块调整框; dragging the yellow candidate box accepts it first 拖黄色候选框 = 先接受再调.<br>""")
    h = _sub(h, '<div class="side"><div id="status"></div>', '<div class="side"><div id="status"></div><div id="objpanel"></div>')
    h = _sub(h, '<div style="opacity:.55">faint = other rats 其他鼠</div></details>',
             '<div><span class="sw" style="background:#fff;border:2px solid #fff"></span> hovered mask 悬停高亮</div>'
             '<div><span class="sw" style="background:#ff9f1a;width:9px;border:1px solid #000"></span> drag handles 拖动方块 '
             '(<span style="border:1px solid #ffd400;display:inline-block;width:8px;height:8px"></span> = candidate 候选)</div>'
             '<div style="opacity:.55">faint = other rats / the other box 其他鼠 / 另一个框</div></details>')
    h = _sub(h, "</style></head>", """
#objpanel{border:1px solid #555;border-radius:6px;padding:4px 6px;font-size:13px;max-height:46vh;overflow:auto}
#objpanel .op-h{font-weight:800;padding:2px 6px;border-radius:4px;color:#111;margin-bottom:4px}
#objpanel .op-t{font-weight:700;margin:6px 0 2px}
#objpanel .op-row{display:flex;justify-content:space-between;align-items:center;gap:6px;padding:2px 4px;border-radius:4px}
#objpanel .op-row:hover{background:rgba(255,212,0,.25);outline:1px solid #ffd400}
#objpanel .op-c{cursor:pointer}#objpanel .op-c.cur{font-weight:700;outline:1px dashed #ffd400}#objpanel .op-c.inb{opacity:.7}
#objpanel .op-x{font-size:16px;font-weight:800;line-height:1;padding:1px 9px;border-radius:4px;border:1px solid #333;cursor:pointer;background:#c62828;color:#fff}
#objpanel .op-plus{background:#2e7d32}#objpanel .op-note{opacity:.75;font-style:italic}
#status .st-click{opacity:.85}
</style></head>""")
    return h


def page_check_v24(new_dir: Path, data: dict, old_html: Path, old_data: Path) -> dict:
    """Headless Chrome (throwaway profile). A: old-state test — the backed-up v2.3 page saves a state (implant click +
    accept, a 2-piece joined rat box with a merged flag, a hidden implant + manual rat box, SCRATCH boxes); v2.4 loads it
    under the same key and exports it unchanged apart from version / time / reload events. B: v2.4 — panel rows, click =
    current, hover highlight, + joins (3 pieces), × removes one (box = union of 2), U restores; × on a single mask clears; edge
    and corner drags of the implant box by its handles after A; a drag on an un-accepted candidate's bbox accepts and resizes;
    the inactive box gives a toast and no pan; a small hand-drawn box at fit zoom resizes by a corner without collapsing, ×
    clears it; the split status ("Box 框" / "Last click 上次点击") and the "box unchanged" toast; export; no network URL."""
    import inbox_identity_page as ipage
    html_t, js_t = (new_dir / "index.html").read_text(encoding="utf-8"), (new_dir / "pl_data.js").read_text(encoding="utf-8")
    res = {"network_urls": re.findall(r"https?://[^\s\"'<>]+", html_t) + re.findall(r"https?://[^\s\"'<>]+", js_t)}
    vdir = new_dir.parent if new_dir.name.startswith("_") else new_dir
    tdir = vdir / "_v23_oldstate_test"
    if tdir.exists():
        shutil.rmtree(tdir)
    tdir.mkdir()
    shutil.copy2(old_html, tdir / "index.html")
    od = _read_data_js(old_data)
    for f in od["frames"]:
        f["img"] = "../" + f["img"]
    (tdir / "pl_data.js").write_text("window.PL_DATA = " + json.dumps(od, separators=(",", ":")) + ";\n", encoding="utf-8")
    prof = Path(tempfile.mkdtemp(prefix="pl24check_"))
    p, wsu, bws = ipage._chrome((tdir / "index.html").resolve().as_uri(), prof, ipage._free_port())
    c = None
    fr = data["frames"]

    def union(bs):
        return [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)]

    def area(b):
        return (b[2] - b[0]) * (b[3] - b[1])

    def close(a, b, tol=0.25):
        return a is not None and b is not None and all(abs(x - y) <= tol for x, y in zip(a, b))

    def cm(a, e, moved, s):
        # moved edges follow the mouse (synthetic events land within ~1.5 screen px); the other edges must not move
        return a is not None and all(abs(a[i] - e[i]) <= (1.5 / s if i in moved else 0.25) for i in range(4))
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

        def mxy(kind, x, y):
            c.ev(f"document.getElementById('cv').dispatchEvent(new MouseEvent({json.dumps(kind)}, {{clientX: {x}, clientY: {y}, button: 0, bubbles: true}}))")

        def click(u, v):
            mouse("mousedown", u, v)
            mouse("mouseup", u, v)

        def drag(u0, v0, u1, v1):
            mouse("mousedown", u0, v0)
            mouse("mousemove", (u0 + u1) / 2, (v0 + v1) / 2)
            mouse("mousemove", u1, v1)
            mouse("mouseup", u1, v1)

        def drag_xy(x0, y0, dx, dy):
            mxy("mousedown", x0, y0)
            for t in (0.25, 0.5, 0.75, 1.0):
                mxy("mousemove", x0 + dx * t, y0 + dy * t)
            mxy("mouseup", x0 + dx, y0 + dy)

        def R(i=None):
            return c.ev("JSON.parse(JSON.stringify(window.__pl.rat()))" if i is None else
                        f"JSON.parse(JSON.stringify(window.__pl.S().frames[window.__pl.frame().id].rats[{i}]))")

        def cur():
            return c.ev("window.__pl.cur()")

        def n_events():
            return c.ev("window.__pl.S().events.length")

        def events_since(n):
            return c.ev(f"window.__pl.S().events.slice({n})")

        def qclick(sel):
            return c.ev(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); if (!el) return false; el.click(); return true; }})()")

        def body_points(f, min_cand, away_from_dots=False):
            out = []
            for m in sorted(f["masks"], key=lambda m: -m["a"])[:40]:
                for pts in m["p"]:
                    x0, y0 = float(np.mean(pts[0::2])), float(np.mean(pts[1::2]))
                    if _pip(x0, y0, pts):
                        if away_from_dots and c.ev(f"window.__pl.dotAtImg({x0}, {y0})") is not None:
                            break
                        cand = c.ev(f"window.__pl.candidatesAt({x0}, {y0})")
                        if len(cand) >= min_cand:
                            out.append(((x0, y0), cand))
                        break
            return out
        # ---------------- A. old-state test with the backed-up v2.3 page (sticky modes, implant click)
        res["loaded_v23"] = ready()
        res["v23_page_version"] = c.ev("window.__pl.D.page_version")
        pre = [i for i, f in enumerate(fr) if f["arm"] == "PRELABEL" and len(f["cand"]) >= 2 and f["cand"][0] and f["cand"][1]]
        fi, pt = None, None
        for i in pre:
            c.ev(f"window.__pl.goFrame({i})")
            bp = body_points(fr[i], 2, away_from_dots=True)
            if bp:
                fi, pt = i, bp[0][0]
                break
        c.ev(f"window.__pl.goFrame({fi})")
        ready()
        f = fr[fi]
        key("1")
        click(*pt)                                   # v2.3: implant candidates at the click
        key("a")
        key("2")
        click(*pt)
        key("j")
        key("n")
        key("j")
        key("m")
        for _ in range(3):
            c.ev("window.__pl.setLastInput(0)")
            time.sleep(0.5)
        key("Enter")
        key("1")
        key("h")
        key("2")
        hu, hv = f["heads"][1]["u"], f["heads"][1]["v"]
        key("b")
        drag(hu - 120, hv - 90, hu + 160, hv + 140)
        fs = next(i for i, x in enumerate(fr) if x["arm"] == "SCRATCH")
        c.ev(f"window.__pl.goFrame({fs})")
        ready()
        g = fr[fs]
        gu, gv = g["heads"][0]["u"], g["heads"][0]["v"]
        key("1")
        drag(gu - 50, gv - 40, gu + 50, gv + 40)
        key("2")
        drag(gu - 180, gv - 140, gu + 220, gv + 180)
        c.ev(f"window.__pl.goFrame({fi})")
        c.ev("window.__pl.setLastInput(60000)")
        ex_old = c.ev("window.__pl.exportJSON()")
        c.ev("window.__pl.save()")
        old_key = c.ev("window.__pl.key")
        c.call("Page.navigate", url=(new_dir / "index.html").resolve().as_uri())
        time.sleep(1.5)
        res["loaded_v24"] = ready()
        c.ev("window.__pl.setLastInput(60000)")
        ex_new = c.ev("window.__pl.exportJSON()")
        cmp = _compare_exports(ex_old, ex_new)
        fo = next(x for x in ex_new["frames"] if x["frame_id"] == f["id"])
        r1, r2 = fo["rats"][0], fo["rats"][1]
        res["old_state"] = {**cmp, "same_storage_key": old_key == c.ev("window.__pl.key"),
                            "rat1": [r1["implant"]["source"], r1["implant"].get("cand_src"), r1["rat"]["source"], r1["rat"]["n_pieces"], r1["rat"]["obj_flags"]],
                            "rat2": [r2["implant"]["hidden"], r2["rat"]["source"]],
                            "ok": cmp["ok"] and old_key == c.ev("window.__pl.key") and r1["implant"]["source"] == "cand" and r1["implant"].get("cand_src") == "click"
                            and r1["rat"]["source"] == "joined" and r1["rat"]["n_pieces"] == 2 and r1["rat"]["obj_flags"].get("merged") is True
                            and r2["implant"]["hidden"] is True and r2["rat"]["source"] == "manual"}
        # ---------------- B. v2.4 on another PRELABEL frame: a body point with >= 3 candidates, rat 2 with head candidates
        fj, pts = None, None
        for i in pre:
            if i == fi:
                continue
            c.ev(f"window.__pl.goFrame({i})")
            b0 = fr[i]["masks"][fr[i]["cand"][0][0]]["b"]
            s_ = c.ev("window.__pl.scale()")
            if min(b0[2] - b0[0], b0[3] - b0[1]) * s_ < 40:
                continue
            bp = body_points(fr[i], 3, away_from_dots=True)
            if bp:
                fj, pts = i, bp[0]
                break
        c.ev(f"window.__pl.goFrame({fj})")
        ready()
        g = fr[fj]
        s = c.ev("window.__pl.scale()")
        (pu, pv), pc = pts
        res["frame_B"] = {"fi": fj, "scale": s, "n_cand_at_point": len(pc)}
        # 1. RAT mode: click -> candidate rows; row click = current; hover highlight; + joins three pieces
        key("2")
        click(pu, pv)
        n_rows = c.ev("document.querySelectorAll('#objpanel .op-c').length")
        qclick('#objpanel .op-c[data-i="1"] span')
        k_after_row = R()["rat"]["k"]
        ev_pick = c.ev("window.__pl.S().events.slice(-1)[0]")
        c.ev("document.querySelector('#objpanel .op-c[data-i=\"2\"]').dispatchEvent(new MouseEvent('mouseover', {bubbles: true}))")
        hv_, hl_ = c.ev("window.__pl.hover()"), c.ev("window.__pl.hl()")
        c.ev("document.getElementById('objpanel').dispatchEvent(new MouseEvent('mouseleave'))")
        hv_off = c.ev("window.__pl.hover()")
        n0 = n_events()
        for i in range(3):
            qclick(f'#objpanel [data-act="join"][data-i="{i}"]')
        r3 = R()["rat"]
        joins = [e for e in events_since(n0) if e["ev"] == "join"]
        bbs = [g["masks"][m]["b"] for m in pc[:3]]
        box3 = union(bbs)
        n_in_rows = c.ev("document.querySelectorAll('#objpanel [data-act=\"rm\"]').length")
        res["panel_rows_hover_plus"] = {"n_cand_rows": n_rows, "k_after_row_click": k_after_row, "pick_event": ev_pick.get("ev"), "hover": hv_, "highlighted": hl_,
                                        "hover_after_leave": hv_off, "n_pieces": len(r3["pieces"]), "join_via": [e.get("via") for e in joins], "in_box_rows": n_in_rows,
                                        "ok": n_rows == len(pc) and k_after_row == 1 and ev_pick.get("ev") == "cand_pick" and hv_ == pc[2] and hl_ == pc[2]
                                        and hv_off is None and len(r3["pieces"]) == 3 and r3["source"] == "joined" and close(r3["box"], box3)
                                        and [e.get("via") for e in joins] == ["panel"] * 3 and n_in_rows == 3}
        # 2. × removes the piece whose removal shrinks the union most; U restores
        opts = [(area(union([b for k2, b in enumerate(bbs) if k2 != i])), i) for i in range(3)]
        a_min, i_rm = min(opts)
        qclick(f'#objpanel [data-act="rm"][data-i="{i_rm}"]')
        r2p = R()["rat"]
        ev_rm = c.ev("window.__pl.S().events.slice(-1)[0]")
        exp2 = union([b for k2, b in enumerate(bbs) if k2 != i_rm])
        key("u")
        ru = R()["rat"]
        res["piece_remove_undo"] = {"removed": i_rm, "box3": box3, "box2": r2p["box"], "expected2": exp2, "shrank": area(exp2) < area(box3), "event": ev_rm.get("ev"),
                                    "after_undo_pieces": len(ru["pieces"]),
                                    "ok": len(r2p["pieces"]) == 2 and r2p["source"] == "joined" and close(r2p["box"], exp2) and area(exp2) < area(box3)
                                    and ev_rm.get("ev") == "piece_remove" and ev_rm.get("n_pieces_left") == 2 and len(ru["pieces"]) == 3 and close(ru["box"], box3)}
        # 3. status split + "box unchanged" toast (RAT mode, a click on a point with no mask)
        free = None
        for gu_ in np.linspace(40, g["w"] - 40, 25):
            for gv_ in np.linspace(40, g["h"] - 40, 19):
                if c.ev(f"window.__pl.candidatesAt({gu_}, {gv_}).length") == 0 and c.ev(f"window.__pl.dotAtImg({gu_}, {gv_})") is None:
                    xy = c.ev(f"window.__pl.imgToClient({gu_}, {gv_})")
                    gi = c.ev(f"window.__pl.grabInfo({xy[0]}, {xy[1]})")
                    if not gi["box"] and not gi["cand"] and not gi["other"]:
                        free = (float(gu_), float(gv_))
                        break
            if free:
                break
        c.ev("window.__pl.clearToast()")
        rb = R()["rat"]["box"]
        click(*free)
        st_txt = c.ev("window.__pl.statusText()")
        t_free = c.ev("window.__pl.toast()")
        res["status_split"] = {"status": st_txt, "toast": t_free,
                               "ok": "Box 框: ✓ done — 3 joined masks" in st_txt and "Last click 上次点击: no mask under this point (box unchanged) 这里没有 mask，框没变" in st_txt
                               and "(box unchanged 框没变)" in t_free and close(R()["rat"]["box"], rb)}
        # 4. IMPLANT mode: A, × on the single mask clears, U restores; edge drag and corner drag by the handles
        key("1")
        key("a")
        bA = R()["implant"]["box"]
        qclick('#objpanel [data-act="rm"][data-i="0"]')
        cleared = R()["implant"]
        st_cleared = c.ev("window.__pl.statusText()")
        ev_cl = c.ev("window.__pl.S().events.slice(-1)[0]")
        key("u")
        bU = R()["implant"]["box"]
        hs = c.ev("window.__pl.handlesClient('box')")
        hr = next(h for h in hs if h["e"] == [2])
        drag_xy(hr["x"], hr["y"], -15, 0)
        bE = R()["implant"]["box"]
        hs = c.ev("window.__pl.handlesClient('box')")
        htl = next(h for h in hs if h["e"] == [0, 1])
        drag_xy(htl["x"], htl["y"], 10, 10)
        bC = R()["implant"]["box"]
        res["implant_single_clear_and_handles"] = {"box_after_A": bA, "cleared_box": cleared["box"], "cleared_event": ev_cl.get("ev"), "after_undo": bU,
                                                   "after_edge_drag": bE, "after_corner_drag": bC, "n_handles": len(hs),
                                                   "ok": bA is not None and cleared["box"] is None and cleared["source"] is None and ev_cl.get("n_pieces_left") == 0
                                                   and "Box 框: — not yet 未标" in st_cleared and close(bU, bA) and len(hs) == 8
                                                   and cm(bE, [bA[0], bA[1], bA[2] - 15 / s, bA[3]], (2,), s)
                                                   and cm(bC, [bE[0] + 10 / s, bE[1] + 10 / s, bE[2], bE[3]], (0, 1), s)}
        # 5. rat 2 (chip): drag the hollow handle of the un-accepted head candidate's bbox -> accepted, then resized
        qclick('#ratchips [data-ri="1"]')
        r2_ = R()
        cb = g["masks"][r2_["implant"]["cand"][r2_["implant"]["k"]]]["b"]
        hc = next(h for h in c.ev("window.__pl.handlesClient('cand')") if h["e"] == [2, 3])
        n0 = n_events()
        drag_xy(hc["x"], hc["y"], -12, -12)
        bD = R()["implant"]["box"]
        evd = [e["ev"] for e in events_since(n0)]
        res["candidate_bbox_drag"] = {"cand_bbox": cb, "box": bD, "events": evd,
                                      "ok": r2_["implant"]["box"] is None and evd == ["accept", "cand_drag_accept", "edge_move"]
                                      and cm(bD, [cb[0], cb[1], cb[2] - 12 / s, cb[3] - 12 / s], (2, 3), s)}
        # 6. wrong mode: RAT mode, drag the implant box's handle -> toast, no change, no pan
        key("2")
        c.ev("window.__pl.clearToast()")
        hi = next(h for h in c.ev("window.__pl.handlesClient('box', 'implant')") if h["e"] == [2, 3])
        gi = c.ev(f"window.__pl.grabInfo({hi['x']}, {hi['y']})")
        o0 = c.ev("window.__pl.origin()")
        drag_xy(hi["x"], hi["y"], -15, -15)
        o1 = c.ev("window.__pl.origin()")
        t_w = c.ev("window.__pl.toast()")
        res["wrong_mode_toast"] = {"grab": gi, "toast": t_w, "view_moved": [o1[0] - o0[0], o1[1] - o0[1]],
                                   "ok": gi["other"] == "implant" and not gi["box"] and "switch to ① IMPLANT (press 1) to edit this box 按 1 切到植入体模式再改" in t_w
                                   and close(R()["implant"]["box"], bD) and o0 == o1}
        # 7. a small hand-drawn box at fit zoom: corners only, resizes without collapsing; × clears it
        key("1")
        key("z")
        qclick('#objpanel [data-act="rm"][data-i="0"]')
        s = c.ev("window.__pl.scale()")
        hd = R()
        key("b")
        drag(hd["u"] - 4.5 / s, hd["v"] - 4.5 / s, hd["u"] + 4.5 / s, hd["v"] + 4.5 / s)
        sb = R()["implant"]["box"]
        hs = c.ev("window.__pl.handlesClient('box')")
        hbr = next(h for h in hs if h["e"] == [2, 3])
        drag_xy(hbr["x"], hbr["y"], 20, 20)
        sb2 = R()["implant"]["box"]
        hs2 = c.ev("window.__pl.handlesClient('box')")
        hr2 = min((h for h in hs2 if h["e"] == [2, 3]), key=lambda h: h["x"])
        drag_xy(hr2["x"] + 0.0, hr2["y"] - (hr2["y"] - hs2[0]["y"]) / 2, 0, 0)   # a plain press between handles: nothing changes
        sb3 = R()["implant"]["box"]
        qclick('#objpanel [data-act="clear"]')
        ev_bc = c.ev("window.__pl.S().events.slice(-1)[0]")
        res["small_box"] = {"box_screen_px": [(sb[2] - sb[0]) * s, (sb[3] - sb[1]) * s] if sb else None, "n_handles": len(hs), "before": sb, "after_corner": sb2,
                            "after_plain_press": sb3, "clear_event": ev_bc.get("ev"), "after_clear": R()["implant"]["box"],
                            "ok": sb is not None and (sb[2] - sb[0]) * s < 12 and len(hs) == 4 and cm(sb2, [sb[0], sb[1], sb[2] + 20 / s, sb[3] + 20 / s], (2, 3), s)
                            and sb2[2] - sb2[0] > 2 and sb2[3] - sb2[1] > 2 and close(sb3, sb2) and ev_bc.get("ev") == "box_clear" and R()["implant"]["box"] is None}
        # 8. status wording for an object without a box / without a click
        key("2")
        st2 = c.ev("window.__pl.statusText()")
        res["status_empty"] = {"status": st2, "ok": "Box 框: — not yet 未标" in st2 and "Last click 上次点击: no click yet 还没点" in st2}
        res["help_legend"] = {"ok": bool(c.ev("document.body.textContent.includes('drag the square handles') && document.body.textContent.includes('In this box 当前框包含的 mask')")
                                         and c.ev("document.getElementById('legend').textContent.includes('hovered mask')"))}
        ej = c.ev("window.__pl.exportJSON()")
        n_rats = sum(len(x["rats"]) for x in ej["frames"])
        csv_lines = c.ev("window.__pl.exportCSV().trim().split('\\n').length")
        new_evs = [e["ev"] for e in ej["events"][len(ex_old["events"]):]]
        res["export"] = {"version": ej["page_version"], "csv_lines": csv_lines, "event_kinds_new": sorted(set(new_evs)),
                         "ok": ej["page_version"] == PAGE_VERSION_V24 and csv_lines == 2 * n_rats + 1
                         and {"piece_remove", "cand_pick", "cand_drag_accept", "box_clear", "wrong_mode_edit", "edge_move", "join", "undo"} <= set(new_evs)}
        c.ev("localStorage.clear()")
    finally:
        if c:
            c.close()
        ipage._close_chrome(p, bws)
        shutil.rmtree(prof, ignore_errors=True)
        shutil.rmtree(tdir, ignore_errors=True)
    keys = ["old_state", "panel_rows_hover_plus", "piece_remove_undo", "status_split", "implant_single_clear_and_handles", "candidate_bbox_drag",
            "wrong_mode_toast", "small_box", "status_empty", "help_legend", "export"]
    res["verdict"] = "PASS" if (res.get("loaded_v23") and res.get("loaded_v24") and all(res[k]["ok"] for k in keys) and not res["network_urls"]) else "FAIL"
    return res


def update_v24(run: Path, check: bool = True) -> dict:
    """In-place v2.3 -> v2.4 (mask panel, drag handles, split status). Same storage key; *.v2_3.bak backups first; payload
    verified identical to v2.3; a staged copy is checked (incl. the old-state test) before the live files are replaced."""
    out = run / "prelabel_edit_v2"
    cur = _read_data_js(out / "pl_data.js")
    if cur["page_version"] == PAGE_VERSION_V23:
        for name in ("index.html", "pl_data.js", "page_check.json", "build_meta.json"):
            src, bak = out / name, out / f"{name}.v2_3.bak"
            if src.exists() and not bak.exists():
                shutil.copy2(src, bak)
    old = _read_data_js(out / "pl_data.js.v2_3.bak")
    assert old["page_version"] == PAGE_VERSION_V23, f"the backup is not v2.3: {old['page_version']}"
    key = old["storage_key"]
    new = _v2_data(run, PAGE_VERSION_V24, key, [PAGE_VERSION_V2, PAGE_VERSION_V21, PAGE_VERSION_V22, PAGE_VERSION_V23, PAGE_VERSION_V24])
    same = len(old["frames"]) == len(new["frames"]) and all(a[k] == b[k] for a, b in zip(old["frames"], new["frames"])
                                                            for k in ("id", "domain", "arm", "pile_bin", "order", "img", "heads", "masks", "cand"))
    if not same:
        raise SystemExit("v2.4 payload differs from v2.3: not written, v2.3 left in place")
    js_final = "window.PL_DATA = " + json.dumps(new, separators=(",", ":")) + ";\n"
    html_final = page_html_v24(run.name)
    pc = None
    if check:
        stg = out / "_v24_staging"
        if stg.exists():
            shutil.rmtree(stg)
        stg.mkdir()
        staged = json.loads(json.dumps(new))
        for f in staged["frames"]:
            f["img"] = "../" + f["img"]
        (stg / "pl_data.js").write_text("window.PL_DATA = " + json.dumps(staged, separators=(",", ":")) + ";\n", encoding="utf-8")
        (stg / "index.html").write_text(html_final, encoding="utf-8")
        try:
            pc = page_check_v24(stg, new, out / "index.html.v2_3.bak", out / "pl_data.js.v2_3.bak")
        finally:
            shutil.rmtree(stg, ignore_errors=True)
        print(f"v2.4 page check (staged): {pc['verdict']}", flush=True)
        if pc["verdict"] != "PASS":
            S.write_json(out / "page_check_v2_4_FAILED.json", pc)
            raise SystemExit("v2.4 check failed: the live v2.3 page was NOT replaced (see page_check_v2_4_FAILED.json)")
    (out / "pl_data.js").write_text(js_final, encoding="utf-8")
    (out / "index.html").write_text(html_final, encoding="utf-8")
    meta = json.loads((out / "build_meta.json.v2_3.bak").read_text(encoding="utf-8"))
    meta["v2_4"] = {"made": datetime.now().isoformat(timespec="seconds"),
                    "why": "right-side mask panel (× remove, + join, hover); drag handles + candidate-bbox drag; status split into Box / Last click",
                    "page_version": PAGE_VERSION_V24, "storage_key": key, "payload_identical_to_v2_3": same,
                    "backups": sorted(q.name for q in out.glob("*.bak")), "page_check": pc["verdict"] if pc else "not run", "git_commit": git_commit()}
    if pc:
        S.write_json(out / "page_check.json", pc)
    S.write_json(out / "build_meta.json", meta)
    return meta


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
    # ---------------- v2.1 (joins)
    if node:
        with tempfile.TemporaryDirectory() as td:
            js = Path(td) / "pl21.js"
            js.write_text(PAGE_JS_V21, encoding="utf-8")
            r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
            rec("v2.1 page script parses (node --check)", r.returncode == 0, r.stderr[-300:])
    h21 = page_html_v21("x")
    rec("v2.1 page: J help line, toast, keeps the v2 layout, no network", "J join this piece 拼接" in h21 and 'id="toast"' in h21
        and PAGE_JS_V21 in h21 and not re.search(r"https?://", h21))
    rec("v2.1 storage key is the v2 key (data.storage_key wins in the script)", "D.storage_key ||" in PAGE_JS_V21)

    def O21(src, rank=None, npc=0, flags=None, obj_flags=None, t=10.0, ub=None, box=(0, 0, 10, 10), prop=(0, 0, 10, 10)):
        pcs = [{"mask": i, "rank": i + 1, "click": [1, 1]} for i in range(npc)]
        return {"cand": [0, 1, 2], "k": 0, "prop": list(prop), "box": list(box) if src else None, "source": src, "rank": rank,
                "mask": 0 if src == "cand" else None, "cand_flags": {str(a): b for a, b in (flags or {}).items()}, "obj_flags": obj_flags or {},
                "edge_moves": 0, "next_presses": 0, "time_ms": t * 1000, "hidden": False, "click": [1, 1], "clicks": [[1, 1]], "pieces": pcs,
                "union_box": list(ub) if ub else (list(box) if src in ("cand", "joined") else None)}
    ex21 = {"page_version": PAGE_VERSION_V21, "definition_note": "", "frames": [
        {"frame_id": "J", "domain": "ir", "arm": "PRELABEL", "pile_bin": "4+", "completed": True, "visited": True, "active_s": 100.0, "showall_s": 0.0,
         "showall_marks": [], "passes": [], "rats": [
             RR(1, O21("cand", 1, 1), O21("cand", 1, 1, t=5)),
             RR(2, O21("cand", 1, 1), O21("joined", None, 2, t=20, ub=(0, 0, 20, 20), box=(-2, 0, 20, 20))),
             RR(3, O21("cand", 1, 1), O21("joined", None, 3, obj_flags={"merged": True}, t=30, ub=(0, 0, 30, 30), box=(0, 0, 30, 30))),
             RR(4, O21("cand", 1, 1), O21("manual", None, 0, t=12, box=(0, 0, 40, 20)))]}]}
    sj = summarize_v2(ex21)
    rr_ = sj["objects"]["rat"]
    rec("v2.1 rat: usable@any single 1/4, with joins 2/4 (merged joined box excluded), joined 2/4",
        abs(rr_["usable_any"] - 0.25) < 1e-12 and abs(rr_["usable_any_join"] - 0.5) < 1e-12 and abs(rr_["joined"] - 0.5) < 1e-12,
        str({k: rr_[k] for k in ("usable_any", "usable_any_join", "joined")}))
    rec("v2.1 rat: n_pieces distribution 0:1, 1:1, 2:1, 3:1", rr_["n_pieces_dist"] == {"0": 1, "1": 1, "2": 1, "3": 1}, str(rr_["n_pieces_dist"]))
    rec("v2.1 rat: seconds single 5, joined 25, manual 12", abs(rr_["time_by_source"]["cand"]["s_per_object"] - 5) < 1e-9
        and abs(rr_["time_by_source"]["joined"]["s_per_object"] - 25) < 1e-9 and abs(rr_["time_by_source"]["manual"]["s_per_object"] - 12) < 1e-9,
        str(rr_["time_by_source"]))
    rec("v2.1 rat: union-box shifts of joined boxes (left +2 / 0 -> median +1 px)", rr_["union_shift"]["n"] == 2
        and rr_["union_shift"]["edges"]["left"]["px"]["median"] == 1.0, str(rr_["union_shift"]["edges"]["left"]))
    ex20 = json.loads(json.dumps(ex2))
    ex20["page_version"] = PAGE_VERSION_V2
    sv20 = summarize_v2(ex20)
    rec("v2.1 summary still reads v2.0 exports (no pieces field: single = 1 piece)", sv20["objects"]["rat"]["n_pieces_dist"].get("1", 0) >= 1
        and abs(sv20["objects"]["rat"]["usable_any_join"] - sv20["objects"]["rat"]["usable_any"]) < 1e-12)
    md21 = summary_md_v2(sj, "synthetic_v21.json")
    rec("v2.1 markdown: single vs joins, pieces per box, union shifts", "with joins" in md21 and "pieces per box" in md21 and "union box" in md21)
    rec("strip of v2.1-only fields", _strip_new({"a": 1, "pieces": [], "x": {"union_box": 1, "b": 2}, "schema": "2.1"}) == {"a": 1, "x": {"b": 2}})
    # ---------------- v2.2 (UX)
    if node:
        with tempfile.TemporaryDirectory() as td:
            js = Path(td) / "pl22.js"
            js.write_text(PAGE_JS_V22, encoding="utf-8")
            r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
            rec("v2.2 page script parses (node --check)", r.returncode == 0, r.stderr[-300:])
    h22 = page_html_v22("x")
    rec("v2.2 page: banner, legend, new help line, centred toast, no network", 'id="modebanner"' in h22 and 'id="legend"' in h22
        and "Each rat: implant (A/N/J, H hidden) → click the body → rat box (A/N/J…) → Enter" in h22 and "#toast{position:fixed" in h22
        and not re.search(r"https?://", h22))
    rec("v2.2 script: click -> rat box + obj_auto_switch; toasts for scratch / hidden / no click / joined", "obj_auto_switch" in PAGE_JS_V22
        and all(m in PAGE_JS_V22 for m in ("SCRATCH frame: draw by hand", "implant hidden", "click the body first", "already joined")))
    rec("v2.2 keeps the storage-key rule", "D.storage_key ||" in PAGE_JS_V22)
    rec("export comparison helper: equal states pass, a changed box fails",
        _compare_exports({"a": 1, "events": [{"ev": "x"}], "frames": [{"frame_id": "F", "active_s": 1.0, "rats": [{"id": "h1", "implant": {"box": [0, 0, 1, 1], "time_ms": 5}, "rat": {"box": None, "time_ms": 1}}]}]},
                         {"a": 1, "events": [{"ev": "x"}, {"ev": "frame_open"}], "frames": [{"frame_id": "F", "active_s": 1.5, "rats": [{"id": "h1", "implant": {"box": [0, 0, 1, 1], "time_ms": 900}, "rat": {"box": None, "time_ms": 1}}]}]})["ok"]
        and not _compare_exports({"events": [], "frames": [{"frame_id": "F", "rats": [{"id": "h1", "implant": {"box": [0, 0, 1, 1]}, "rat": {}}]}]},
                                 {"events": [], "frames": [{"frame_id": "F", "rats": [{"id": "h1", "implant": {"box": [0, 0, 2, 1]}, "rat": {}}]}]})["ok"])
    # ---------------- v2.3 (two sticky modes, rat switching)
    if node:
        with tempfile.TemporaryDirectory() as td:
            js = Path(td) / "pl23.js"
            js.write_text(PAGE_JS_V23, encoding="utf-8")
            r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
            rec("v2.3 page script parses (node --check)", r.returncode == 0, r.stderr[-300:])
    h23 = page_html_v23("x")
    rec("v2.3 page: mode buttons, chips, rat-switch help line, legend, no network", 'id="mb-implant"' in h23 and 'id="mb-rat"' in h23
        and 'id="ratchips"' in h23 and "switch rat: click its white dot or its number chip · Enter/← next/prev 切换鼠：点白点或上方数字" in h23
        and 'id="legend"' in h23 and not re.search(r"https?://", h23))
    rec("v2.3 script: no automatic mode change; mode_set / implant_click / rat_select / rat_prev logged; H only in IMPLANT mode",
        "obj_auto_switch" not in PAGE_JS_V23 and "S.cur.obj = 'rat'" not in PAGE_JS_V23
        and all(m in PAGE_JS_V23 for m in ("log('mode_set'", "log('implant_click'", "log('rat_select'", "log('rat_prev')", "IMPLANT mode only")))
    rec("v2.3 keeps the storage-key rule", "D.storage_key ||" in PAGE_JS_V23)
    ex23 = json.loads(json.dumps(ex21))
    ex23["page_version"] = PAGE_VERSION_V23
    ex23["frames"][0]["rats"][0]["implant"]["cand_src"] = "click"
    s23 = summarize_v2(ex23)
    rec("v2.3 summary: implant boxes from a click counted (1), rat boxes all from clicks (4)",
        s23["objects"]["implant"]["from_click"] == 1 and s23["objects"]["rat"]["from_click"] == 4,
        str((s23["objects"]["implant"]["from_click"], s23["objects"]["rat"]["from_click"])))
    rec("v2.3 markdown notes the mixed implant candidate sources", "came from a click in IMPLANT mode" in summary_md_v2(s23, "x.json"))
    # ---------------- v2.4 (mask panel, drag handles, split status)
    if node:
        with tempfile.TemporaryDirectory() as td:
            js = Path(td) / "pl24.js"
            js.write_text(PAGE_JS_V24, encoding="utf-8")
            r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
            rec("v2.4 page script parses (node --check)", r.returncode == 0, r.stderr[-300:])
    h24 = page_html_v24("x")
    rec("v2.4 page: mask panel, handle help, legend, no network", 'id="objpanel"' in h24 and "drag the square handles" in h24
        and "hovered mask" in h24 and not re.search(r"https?://", h24))
    rec("v2.4 script: handles (nearest, 10 px) replace the multi-edge grab; piece_remove / box_clear / cand_drag_accept / wrong-mode toast",
        "edgeAt(" not in PAGE_JS_V24 and "bd = 10" in PAGE_JS_V24
        and all(m in PAGE_JS_V24 for m in ("log('piece_remove'", "log('box_clear'", "log('cand_drag_accept'", "log('wrong_mode_edit'", "switch to ① IMPLANT (press 1)")))
    rec("v2.4 status split: 'Box 框' and 'Last click 上次点击', 'box unchanged' wording", all(m in PAGE_JS_V24 for m in (
        "Box 框: ", "— not yet 未标", "Last click 上次点击: ", "no mask under this point (box unchanged) 这里没有 mask，框没变", "(box unchanged 框没变)", "no click yet 还没点")))
    rec("v2.4 keeps the storage-key rule", "D.storage_key ||" in PAGE_JS_V24)
    print("SELFTEST", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", nargs="?", choices=["build", "summarize", "update-v21", "update-v22", "update-v23", "update-v24"])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--run", type=Path, default=RUN_DEFAULT)
    ap.add_argument("--export", type=Path)
    ap.add_argument("--more-exports", type=Path, nargs="*", default=[], help="exports from other labelling sessions (repeat check only)")
    ap.add_argument("--no-page-check", action="store_true")
    ap.add_argument("--v2", action="store_true", help="build the v2 page (implant box + rat box, amendments B1 / B1a) into <run>/prelabel_edit_v2")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "update-v24":
        m = update_v24(a.run, check=not a.no_page_check)
        print(json.dumps(m.get("v2_4"), indent=1, default=str))
        return 0
    if a.cmd == "update-v23":
        m = update_v23(a.run, check=not a.no_page_check)
        print(json.dumps(m.get("v2_3"), indent=1, default=str))
        return 0
    if a.cmd == "update-v22":
        m = update_v22(a.run, check=not a.no_page_check)
        print(json.dumps(m.get("v2_2"), indent=1, default=str))
        return 0
    if a.cmd == "update-v21":
        m = update_v21(a.run, check=not a.no_page_check)
        print(json.dumps(m.get("v2_1"), indent=1, default=str))
        return 0
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
