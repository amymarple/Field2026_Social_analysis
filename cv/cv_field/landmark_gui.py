# -*- coding: utf-8 -*-
r"""Single-file HTML GUI for labelling RIGID LANDMARKS on one camera frame — adapted from the recording repo's
calibration_qc/line_gui.py (same interaction: pick a landmark on the right, click along it, drag to adjust, right-click
to delete, 4x magnifier, autosave in the browser, Export JSON in full-res UPRIGHT pixels).

Why: the 09-24 calibration was anchored on 09-18/19, after cohort 3, and the user found that cohort-3 frames differ
from the calibration epoch — CH01/CH02 by a distortion change (a house's size differs), CH03/CH04 by day-to-day motion.
Structures that do not move over days (pole axes, the wall TOP edge, the water tower, the PC box facing CH02) are
labelled on a calibration-epoch frame and on cohort frames; the correction cohort-pixel -> calibration-pixel is fitted
from them (point-to-curve distances, so clicks need not correspond point by point). Houses are labelled too but are
VALIDATION only (no record says whether they moved): a correction fitted on the rigid set must also explain them.

Landmark kinds (the side panel groups them):
  edge     POLE_<row><col>_L / _R  the pole's LEFT and RIGHT edge as seen in this image (a pole is a vertical cylinder:
                            two parallel lines), each along its visible length (the ends usually are not visible) —
                            2+ points each; the centre line and the apparent width follow from the pair
  outline  BOX_<row><col>   the box mounted on that pole = a WISER UWB anchor (user, 2026-09-29): clear corners, rigid
  polyline PATCH_<wall>_<n> a visible patch on a wall sheet (user, 2026-10-01; CH03/CH04 see several) — an OPEN line
                            along its visible edges, following the corrugation bumps (not straight, not closed; the
                            bottom is often hidden by grass -> pieces); added with "+ add" as polyline; numbered left to
                            right in each camera's view; fit set
  edge     SEAM_<wall>_<n>  a VERTICAL seam between wall panels (user, 2026-10-01): straight, 2+ points along its visible
                            length; numbered left to right per camera; only seams that look clearly different from the
                            regular corrugation ridges (overlap edge, bolts, colour change) — ridges repeat and can be
                            confused by the matcher; fit set (constrains the horizontal position like a pole edge)
  polyline WALLTOP_*        the top edge of the wall sheet, one per side (the foot is hidden by grass)
           HOUSE_<n>_BASE   the visible part of a house's bottom edge (validation only)
  outline  TOWER_1, TOWER_2, PCBOX   closed outline, click round it (closes only when it is one piece)
           HOUSE_1_LABEL, HOUSE_2_LABEL   the fixed NUMBER label on each house roof: its corners (user, 2026-10-01: an
           excellent landmark — clear in daytime frames, often saturated by the IR at night, so label it on daytime
           frames and skip it where it is blown out)
  edge     HOUSE_n_ROOF_X / _ROOF_Y   roof edges parallel to the paddock x / y axis (ridge, eaves, ...)
           HOUSE_n_BASE_X / _BASE_Y   bottom edges parallel to x / y;  HOUSE_n_BASE_Z  the vertical corner edges
           (user, 2026-10-01: a house is 3-D with a gable roof, so it is labelled as straight edges by 3-D direction —
           no closed outline that cannot extend). Each visible edge = one piece (b between edges). A category holds
           up to ~3 edges and they need NOT be parallel (e.g. the two sloped gable edges) — every piece is its own
           straight line, matched to the nearest same-category line in another frame. Validation only. HOUSE_1 =
           house_1 = roof number 4 (by pole B1, under CH05; MOVED on 09-18, so never compare it with 09-18 frames),
           HOUSE_2 = house_2 = roof number 7 (by pole B3, under CH06; never moved). Only edges that are truly parallel
           in 3-D share a vanishing point (a distortion check for those).
           Two water towers outside the paddock (user, 2026-09-29): TOWER_1 beyond the row-C wall (y = 240 side, the
           top of the schematic), TOWER_2 beyond the row-A wall (y = 0 side, the bottom).
Poles use the paddock grid names (rows A/B/C x columns 0-4, 10 ft grid) so a pole keeps its name in every frame and
camera; add any other structure with "+ add".

Usage: python cv/cv_field/landmark_gui.py CHxx "YYYY-MM-DD HH:MM:SS" --cohort 2026c [--guide <earlier export.json>] [--half]
                                          [--session <calibration session folder>]
  09-18 times are read from the calibration session (F:\calibration\session_2026-09-18_13-54-34), other times from the
  cohort copy (F:\3rd_rat); --session reads any date from that session folder instead (e.g. the 2026-09-30 supplement,
  F:\calibration\session_2026-09-30_15-49-39). -> $FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/cv_field_landmarks/landmark_gui_CHxx_<ts>.html
  Export -> landmarks_CHxx_<ts>.json; keep exports in cv/configs/landmarks/<cohort>/ (they are human labels: commit them).
  --guide draws an earlier export (e.g. the 09-18 reference of the same camera) as dashed lines, to identify structures.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import camera_review as cr  # noqa: E402  (frame lookup: segments/locate/grab, PANO)

POLES = [f"POLE_{r}{c}" for r in "ABC" for c in range(5)]
PATCH_CAMS, PATCH_SLOTS = ("CH03", "CH04"), 6       # wall patches: PATCH_<wall>_1..6 per visible wall (more via "+ add")
SEAM_SLOTS = 8                                       # vertical wall seams: SEAM_<wall>_1..8 per visible wall (same cameras)
WALLTOPS = ["WALLTOP_X0", "WALLTOP_X480", "WALLTOP_Y0", "WALLTOP_Y240"]
DEFAULTS = ([(f"{p}_{side}", "edge") for p in POLES for side in "LR"]
            + [(p.replace("POLE_", "BOX_"), "outline") for p in POLES] + [(w, "polyline") for w in WALLTOPS]
            + [("TOWER_1", "outline"), ("TOWER_2", "outline"), ("PCBOX", "outline"),
               ("HOUSE_1_LABEL", "outline"), ("HOUSE_2_LABEL", "outline"),
               ] + [(f"HOUSE_{n}_{part}", "edge") for n in (1, 2) for part in ("ROOF_X", "ROOF_Y", "BASE_X", "BASE_Y", "BASE_Z")])

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>Landmarks __CAM__ __TS__</title>
<style>
 body{margin:0;font-family:Arial,sans-serif;font-size:14px;display:flex;flex-direction:column;height:100vh}
 #top{padding:6px 10px;background:#222;color:#eee;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
 button{font-size:14px;padding:4px 10px}
 #main{display:flex;flex:1;min-height:0}
 #imgwrap{flex:1;overflow:auto;position:relative;background:#111}
 #stage{position:relative;transform-origin:0 0} #stage img{display:block} #ov{position:absolute;left:0;top:0}
 #side{width:320px;padding:8px;overflow:auto;border-left:2px solid #444;background:#f4f4f4}
 .ln{display:block;width:100%;text-align:left;margin:2px 0;padding:3px 8px;border:2px solid #ccc;background:#fff;cursor:pointer}
 .ln.cur{border-color:#000;font-weight:bold} .ln .n{float:right;color:#666} h4{margin:8px 0 2px}
 textarea{width:100%;height:90px;font:11px monospace}
</style></head><body>
<div id="top"><b>__CAM__ @ __TS__</b><span>landmark: <b id="curinfo">none</b></span>
 <button onclick="undo()">undo last point (u)</button><button onclick="penUp()">break: hidden gap here (b)</button><button onclick="clearLine()">clear this landmark</button>
 <span>zoom <button onclick="zoom(0.25)">25%</button><button onclick="zoom(0.5)">50%</button><button onclick="zoom(1)">100%</button><button onclick="zoom(2)">200%</button></span>
 <label><input type="checkbox" id="showg" checked onchange="draw()"> guides (dashed "NAME?" = where the calibration / an earlier export puts it)</label>
 <button onclick="exportJSON()" style="background:#3c3;font-weight:bold">Export JSON</button><span id="stat"></span></div>
<div id="main">
 <div id="imgwrap"><div id="stage"><img id="img" src="data:image/jpeg;base64,__B64__"><svg id="ov"></svg></div></div>
 <div id="side">
  <b>1. pick a landmark &nbsp; 2. click along it in the image</b><br>
  <small><b>POLE_*_L / _R</b>: a pole is a vertical cylinder — label BOTH its edges as two parallel lines: _L = the left
  edge, _R = the right edge as seen in this image, each with 2 or more points along the visible length (the ends need not
  be visible). The dashed "POLE_xx?" guide is the pole's predicted centre line, only to tell which pole it is.
  <b>BOX_xx</b>: the box on that pole (a WISER anchor) — click round its outline, corners first. <b>WALLTOP_*</b>: the TOP edge of the wall sheet, one per side, every ~0.5–1 m. <b>TOWER_1 / TOWER_2 / PCBOX</b>:
  click round the outline (it closes itself); TOWER_1 = the water tower beyond the row-C wall (y = 240, top of the map),
  TOWER_2 = the one beyond the row-A wall (y = 0, bottom). <b>HOUSE_n_*</b>: straight edges sorted by 3-D direction — _ROOF_X / _ROOF_Y = roof edges parallel to the paddock
  x (length) / y (width) axis; _BASE_X / _BASE_Y = bottom edges parallel to x / y; _BASE_Z = the vertical corner edges.
  One piece per visible straight edge, press <b>b</b> between edges; a category can hold up to about 3 edges and they
  need not be parallel (e.g. the two sloped gable edges). Draw the same edges in every frame.
  <b>PATCH_&lt;wall&gt;_&lt;n&gt;</b> (add with "+ add", kind <b>polyline</b>): a visible patch on a wall sheet, e.g. PATCH_X0_1 —
  trace its VISIBLE edges as an open line that follows the corrugation bumps (not a box, not straight); where grass
  hides the bottom, leave it out (b between visible pieces). Number the patches left to right as seen in THIS camera,
  keep the numbers in every frame, and label them on the 09-18 frame too (that is what ties a frame to the calibration).
  <b>SEAM_&lt;wall&gt;_&lt;n&gt;</b>: a vertical seam between wall panels — 2+ points along it (b where hidden), numbered left to
  right, in every frame incl. 09-18. Only seams that look clearly different from the regular corrugation ridges.
  <b>HOUSE_n_LABEL</b>: the fixed number label on the roof — click its corners (it closes itself). Clear by day; at
  night the IR often saturates it — then skip it.
  <b>Only what you can SEE — never an estimated or guessed line</b> (an edge hidden by grass or anything else is left
  out; draw just its visible stretches). A missing line costs nothing, a guessed one biases the result. When grass
  hides the base, the roof edges and the vertical corners usually stay visible. Used only to
  CHECK the correction, not to fit it. Use the same name for the same structure in every frame.
  Which name is which: the dashed "NAME?" guides (the 09-24 calibration's prediction — only to identify the structure;
  click the REAL one) and the top-view map cv/configs/landmarks/2026c/paddock_schematic.png (A0 = origin corner, x
  along the length, rows A/B/C across; HOUSE_1 = house_1 by pole B1, HOUSE_2 = house_2 by pole B3).
  <b>Hidden middle</b> (a wall seen only at both ends, a pole edge cut by something in front): click the first visible
  piece, press <b>b</b> ("break"), then click the next piece — same landmark, no line across the gap.
  <b>Drag</b> a point to move it, <b>right-click</b> to delete. Points are kept in this browser between visits.</small>
  <canvas id="mag" width="240" height="240" style="display:block;margin:6px 0;border:1px solid #888"></canvas>
  <div id="list"></div>
  <div style="margin-top:6px">+ add <input id="newname" size="14" placeholder="NAME"> <select id="newkind"><option>edge</option><option>polyline</option><option>outline</option></select> <button onclick="addLm()">add</button></div>
  <b>Export</b> (also copied here) / paste an earlier export and <button onclick="loadJSON()">Load</button>:<br><textarea id="out"></textarea>
 </div></div>
<script>
const CAM="__CAM__", TS="__TS__", S=__SCALE__, IMGW=__IMGW__, IMGH=__IMGH__, GUIDES=__GUIDES__;
let KIND=__KINDS__;
const GROUP={edge:'Straight edges (pole L/R edges, house edges by direction)',polyline:'Edges (polyline)',outline:'Outlines (closed)',axis:'Pole centre lines (old)'};
const POLE_ORDER=['A0','A1','A2','A3','A4','B0','B1','B2','B3','B4','C0','C1','C2','C3','C4'];
function col(id,i){if(id.startsWith('HOUSE'))return '#9aa0a6';
  if(id.startsWith('POLE')){const k=POLE_ORDER.indexOf(id.slice(5,7));return `hsl(${((k<0?i:k)*47)%360},95%,55%)`;}
  if(id.startsWith('BOX_')){const k=POLE_ORDER.indexOf(id.slice(4,6));return `hsl(${((k<0?i:k)*47)%360},95%,70%)`;}
  if(id.startsWith('WALLTOP'))return ['#ff3030','#ff8c00','#ff40ff','#ffffff'][i%4];return i%2?'#00e5ff':'#7CFC00';}
let COL={};function recol(){Object.keys(KIND).forEach((l,i)=>COL[l]=col(l,i));} recol();
let lines={}; Object.keys(KIND).forEach(l=>lines[l]=[]); let cur=null, z=0.5;
const ov=document.getElementById('ov'), stage=document.getElementById('stage');
function zoom(f){z=f;stage.style.transform='scale('+z+')';stage.style.width=IMGW+'px';stage.style.height=IMGH+'px';}
// A landmark is a list of points in which `null` = pen up: the next point starts a new piece (a wall or an edge whose
// middle is hidden is labelled as separate pieces, never joined across the gap).
function segs(pts){const out=[];let c=[];for(const p of pts){if(p===null){if(c.length)out.push(c);c=[];}else c.push(p);}if(c.length)out.push(c);return out;}
function flat(S_){const out=[];S_.forEach((s,i)=>{if(i)out.push(null);s.forEach(p=>out.push([+p[0],+p[1]]));});return out;}
function tidy(a){const o=[];for(const p of a){if(p===null&&(!o.length||o[o.length-1]===null))continue;o.push(p);}return o;}
function nested(v){return Array.isArray(v)&&v.length&&Array.isArray(v[0])&&Array.isArray(v[0][0]);}
function npts(pts){return pts.filter(p=>p).length;}
function path(pts,closed){return pts.map((p,i)=>(i?'L':'M')+(p[0]*S).toFixed(1)+' '+(p[1]*S).toFixed(1)).join(' ')+(closed&&pts.length>2?' Z':'');}
function draw(){ov.setAttribute('width',IMGW);ov.setAttribute('height',IMGH);let h='';
  if(document.getElementById('showg').checked){for(const [id,g] of Object.entries(GUIDES)){
    const G=nested(g)?g:[g];const gc=COL[id]||COL[id+'_L']||'#ccc';let lab=null;
    for(const s of G){if(s.length<2)continue;if(!lab||s.length>lab.length)lab=s;
      h+=`<path d="${path(s,KIND[id]==='outline'&&G.length===1)}" fill="none" stroke="${gc}" stroke-width="2" stroke-dasharray="14 10" opacity="0.6"/>`;}
    if(lab){const m=lab[Math.floor(lab.length/2)];h+=`<text x="${m[0]*S+8}" y="${m[1]*S-8}" font-size="22" font-weight="bold" fill="${gc}" stroke="#000" stroke-width="4" paint-order="stroke" opacity="0.85">${id}?</text>`;}}}
  for(const [id,pts] of Object.entries(lines)){const S_=segs(pts);if(!S_.length)continue;
    for(const s of S_)if(s.length>1)h+=`<path d="${path(s,KIND[id]==='outline'&&S_.length===1)}" fill="none" stroke="${COL[id]}" stroke-width="${id===cur?4:2.5}"/>`;
    pts.forEach(p=>{if(p)h+=`<circle cx="${p[0]*S}" cy="${p[1]*S}" r="${id===cur?9:6}" fill="none" stroke="${COL[id]}" stroke-width="3"/>`;});
    const p=S_[S_.length-1].slice(-1)[0];h+=`<text x="${p[0]*S+10}" y="${p[1]*S+8}" font-size="24" font-weight="bold" fill="${COL[id]}" stroke="#000" stroke-width="5" paint-order="stroke">${id}</text>`;
    if(id===cur&&pts.length&&pts[pts.length-1]===null)h+=`<text x="${p[0]*S+10}" y="${p[1]*S+36}" font-size="20" fill="#ff0" stroke="#000" stroke-width="4" paint-order="stroke">pen up - next click starts a new piece</text>`;}
  ov.innerHTML=h;list();}
function list(){const L=document.getElementById('list');let h='';for(const k of ['edge','polyline','outline','axis']){
  const ids=Object.keys(KIND).filter(l=>KIND[l]===k);if(!ids.length)continue;h+=`<h4>${GROUP[k]}</h4>`;
  for(const l of ids){const ns=segs(lines[l]).length;h+=`<button class="ln${l===cur?' cur':''}" style="border-left:12px solid ${COL[l]}" onclick="pick('${l}')">${l}<span class="n">${npts(lines[l])} pts${ns>1?' / '+ns+' pieces':''}</span></button>`;}}
  L.innerHTML=h;document.getElementById('curinfo').textContent=cur||'none';
  document.getElementById('stat').textContent=Object.values(lines).reduce((a,b)=>a+npts(b),0)+' points on '+Object.values(lines).filter(v=>npts(v)).length+' landmarks';}
function pick(l){cur=l;draw();}
function addLm(){const n=document.getElementById('newname').value.trim().toUpperCase().replace(/[^A-Z0-9_]/g,'_');if(!n)return;
  if(!KIND[n]){KIND[n]=document.getElementById('newkind').value;lines[n]=[];recol();}cur=n;draw();}
function toImg(e){const r=ov.getBoundingClientRect();return [(e.clientX-r.left)/z/S,(e.clientY-r.top)/z/S];}
function hit(x,y){for(const [id,pts] of Object.entries(lines)){for(let i=0;i<pts.length;i++){if(pts[i]&&Math.hypot(pts[i][0]-x,pts[i][1]-y)*S*z<12)return [id,i];}}return null;}
let drag=null, hover=null;
ov.addEventListener('contextmenu',e=>{e.preventDefault();const [x,y]=toImg(e);const h=hit(x,y);if(h){lines[h[0]].splice(h[1],1);lines[h[0]]=tidy(lines[h[0]]);draw();}});
ov.addEventListener('mousedown',e=>{if(e.button!==0)return;const [x,y]=toImg(e);const h=hit(x,y);
  if(h){drag={id:h[0],i:h[1]};cur=h[0];draw();return;}
  if(!cur){alert('pick a landmark first (right panel)');return;}
  lines[cur].push([Math.round(x*10)/10,Math.round(y*10)/10]);drag={id:cur,i:lines[cur].length-1};draw();});
ov.addEventListener('mousemove',e=>{const [x,y]=toImg(e);hover=[x,y];
  if(drag){lines[drag.id][drag.i]=[Math.round(x*10)/10,Math.round(y*10)/10];draw();}else mag();});
window.addEventListener('mouseup',()=>{if(drag){drag=null;draw();}});
ov.addEventListener('mouseleave',()=>{hover=null;mag();});
function undo(){if(cur&&lines[cur].length){lines[cur].pop();draw();}}
function penUp(){if(cur&&npts(lines[cur])&&lines[cur][lines[cur].length-1]!==null){lines[cur].push(null);draw();}}
function clearLine(){if(cur&&confirm('clear all points of '+cur+'?')){lines[cur]=[];draw();}}
document.addEventListener('keydown',e=>{if(document.activeElement.tagName==='INPUT')return;if(e.key==='u')undo();if(e.key==='b')penUp();});
const mg=document.getElementById('mag'), mctx=mg.getContext('2d'), im=document.getElementById('img');
function mag(){if(!hover||!im.complete){mctx.fillStyle='#000';mctx.fillRect(0,0,mg.width,mg.height);return;}
  const Z=4,Sz=mg.width/Z,cx=hover[0]*S,cy=hover[1]*S;mctx.imageSmoothingEnabled=false;
  mctx.fillStyle='#000';mctx.fillRect(0,0,mg.width,mg.height);
  mctx.drawImage(im,cx-Sz/2,cy-Sz/2,Sz,Sz,0,0,mg.width,mg.height);
  for(const [id,pts] of Object.entries(lines))for(const p of pts){if(!p)continue;const px=(p[0]*S-cx+Sz/2)*Z,py=(p[1]*S-cy+Sz/2)*Z;
    if(px>=0&&px<=mg.width&&py>=0&&py<=mg.height){mctx.strokeStyle=COL[id];mctx.lineWidth=2;mctx.beginPath();mctx.arc(px,py,8,0,7);mctx.stroke();}}
  mctx.strokeStyle='#ff0';mctx.lineWidth=1;mctx.beginPath();mctx.moveTo(mg.width/2-14,mg.height/2);mctx.lineTo(mg.width/2+14,mg.height/2);
  mctx.moveTo(mg.width/2,mg.height/2-14);mctx.lineTo(mg.width/2,mg.height/2+14);mctx.stroke();}
const KEY='landmarks_'+CAM+'_'+TS;
const _draw=draw;draw=function(){_draw();try{localStorage.setItem(KEY,JSON.stringify({lines:lines,kind:KIND}));}catch(e){}};
// earlier names -> current (2026-09-30: houses back to the lab names house_1 / house_2)
function mig(id){return id.replace(/^HOUSE_B1_/,'HOUSE_1_').replace(/^HOUSE_B3_/,'HOUSE_2_');}
function loadJSON(){try{const d=JSON.parse(document.getElementById('out').value);const L=d.landmarks||d.lines||d;
  if(d.kind)for(const [k,v] of Object.entries(d.kind))if(!KIND[mig(k)])KIND[mig(k)]=v;recol();
  for(const [id0,pts] of Object.entries(L)){const id=mig(id0);if(lines[id]===undefined){lines[id]=[];if(!KIND[id])KIND[id]='polyline';}lines[id]=nested(pts)?flat(pts):pts.map(p=>[+p[0],+p[1]]);}draw();}catch(e){alert('not valid JSON: '+e);}}
function exportJSON(){const out={},kind={};for(const [id,pts] of Object.entries(lines)) if(npts(pts)){out[id]=segs(pts);kind[id]=KIND[id];}
  const data={camera:CAM,time:TS,frame_size_upright:[IMGW/S,IMGH/S],format:"pieces",landmarks:out,kind:kind,source:"__SRC__",
    note:"full-res UPRIGHT px; landmarks[name] = list of PIECES, each a list of [u,v] (a hidden middle splits a landmark into pieces; never join across pieces); edge = one straight edge (POLE_xx_L/_R = a pole's left/right edge in this image), polyline = open edge, outline = closed (only when it is one piece); HOUSE_* = validation only"};
  const txt=JSON.stringify(data);document.getElementById('out').value=txt;
  const a=document.createElement('a');a.href='data:application/json;charset=utf-8,'+encodeURIComponent(txt);
  a.download='landmarks_'+CAM+'_'+TS.replace(/[-: ]/g,'').replace(/^(\d{8})(\d{6})$/,'$1_$2')+'.json';a.click();}
try{const s=localStorage.getItem(KEY);if(s){const d=JSON.parse(s);if(d.kind)for(const [k,v] of Object.entries(d.kind))if(!KIND[mig(k)])KIND[mig(k)]=v;recol();
  for(const [id,pts] of Object.entries(d.lines||{})){if(npts(pts)||lines[mig(id)]===undefined)lines[mig(id)]=pts;}}}catch(e){}
zoom(0.5);draw();
</script></body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Rigid-landmark labelling GUI (HTML) for one camera frame.")
    ap.add_argument("camera")
    ap.add_argument("time", help='field-PC time, "YYYY-MM-DD HH:MM:SS"')
    ap.add_argument("--guide", default=None, help="an earlier landmarks_*.json to draw as dashed guides")
    ap.add_argument("--half", action="store_true", help="embed the frame at half resolution (smaller file)")
    ap.add_argument("--cohort", required=True, help="e.g. 2026c (no default: the repo-wide default is 2026a)")
    ap.add_argument("--cohort-root", default=r"F:\3rd_rat")
    ap.add_argument("--ref-session", default=r"F:\calibration\session_2026-09-18_13-54-34")
    ap.add_argument("--session", default=None,
                    help="read the frame from this calibration session folder whatever the date (overrides the two above)")
    args = ap.parse_args(argv)
    import output_paths as op
    cohort = op.resolve_cohort(args.cohort)
    cam, t = args.camera.upper(), datetime.strptime(args.time, "%Y-%m-%d %H:%M:%S")
    size = (7680, 2160) if cam in cr.PANO else (4512, 2512)
    got = cr.grab_at(t, cam, args, cr.find_ffmpeg(), size)
    if got is None:
        raise SystemExit(f"no {cam} frame at {t}")
    img, tk, src = got
    scale = 0.5 if args.half else 1.0
    small = img if scale == 1.0 else cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    b64 = base64.b64encode(cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 85])[1]).decode()
    kinds = dict(DEFAULTS)
    guides = {}
    try:                                                    # calibration-predicted, named guides (identification only)
        import landmark_guides
        guides.update(landmark_guides.calib_guides(cam))
    except Exception as e:  # noqa: BLE001 — the GUI works without them
        print(f"(no calibration guides: {e})")
    if cam in PATCH_CAMS:                                   # several patches per wall: ready-made slots (user, 2026-10-01)
        walls = [k.split("_", 1)[1] for k in guides if k.startswith("WALLTOP_")] or ["X0", "X480", "Y0", "Y240"]
        for w in walls:
            for i in range(1, PATCH_SLOTS + 1):
                kinds.setdefault(f"PATCH_{w}_{i}", "polyline")
            for i in range(1, SEAM_SLOTS + 1):
                kinds.setdefault(f"SEAM_{w}_{i}", "edge")
    if args.guide:
        g = json.loads(Path(args.guide).read_text(encoding="utf-8"))
        guides = g.get("landmarks", {})
        kinds.update({k: v for k, v in g.get("kind", {}).items() if k not in kinds})
    ts = f"{tk:%Y-%m-%d %H:%M:%S}"
    html = (HTML.replace("__CAM__", cam).replace("__TS__", ts).replace("__B64__", b64).replace("__SCALE__", repr(scale))
            .replace("__IMGW__", str(small.shape[1])).replace("__IMGH__", str(small.shape[0]))
            .replace("__GUIDES__", json.dumps(guides)).replace("__KINDS__", json.dumps(kinds))
            .replace("__SRC__", src.name))
    out_dir = op.out_root() / cohort / "cv_field_landmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"landmark_gui_{cam}_{tk:%Y%m%d_%H%M%S}.html"
    out.write_text(html, encoding="utf-8")
    print(f"{cam} @ {ts} ({src.name}) -> {out} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
