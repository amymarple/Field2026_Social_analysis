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
  axis     POLE_<row><col>  the pole's vertical centre line where it is visible (its ends usually are not) — 2+ points
  polyline WALLTOP_*        the top edge of the wall sheet, one per side (the foot is hidden by grass)
           HOUSE_<n>_BASE   the visible part of a house's bottom edge (validation only)
  outline  TOWER, PCBOX, HOUSE_<n>_ROOF   closed outline, click round it (validation only for houses)
Poles use the paddock grid names (rows A/B/C x columns 0-4, 10 ft grid) so a pole keeps its name in every frame and
camera; add any other structure with "+ add".

Usage: python cv/cv_field/landmark_gui.py CHxx "YYYY-MM-DD HH:MM:SS" --cohort 2026c [--guide <earlier export.json>] [--half]
  09-18 times are read from the calibration session (F:\calibration\session_2026-09-18_13-54-34), other times from the
  cohort copy (F:\3rd_rat). -> $FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/cv_field_landmarks/landmark_gui_CHxx_<ts>.html
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
WALLTOPS = ["WALLTOP_X0", "WALLTOP_X480", "WALLTOP_Y0", "WALLTOP_Y240"]
DEFAULTS = ([(p, "axis") for p in POLES] + [(w, "polyline") for w in WALLTOPS]
            + [("TOWER", "outline"), ("PCBOX", "outline"),
               ("HOUSE_B1_ROOF", "outline"), ("HOUSE_B1_BASE", "polyline"), ("HOUSE_B3_ROOF", "outline"), ("HOUSE_B3_BASE", "polyline")])

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
 <button onclick="undo()">undo last point (u)</button><button onclick="clearLine()">clear this landmark</button>
 <span>zoom <button onclick="zoom(0.25)">25%</button><button onclick="zoom(0.5)">50%</button><button onclick="zoom(1)">100%</button><button onclick="zoom(2)">200%</button></span>
 <label><input type="checkbox" id="showg" checked onchange="draw()"> guides (dashed "NAME?" = where the calibration / an earlier export puts it)</label>
 <button onclick="exportJSON()" style="background:#3c3;font-weight:bold">Export JSON</button><span id="stat"></span></div>
<div id="main">
 <div id="imgwrap"><div id="stage"><img id="img" src="data:image/jpeg;base64,__B64__"><svg id="ov"></svg></div></div>
 <div id="side">
  <b>1. pick a landmark &nbsp; 2. click along it in the image</b><br>
  <small><b>POLE_*</b>: click along the pole's vertical CENTRE LINE where you can see it (2 or more points; the ends need not
  be visible). <b>WALLTOP_*</b>: the TOP edge of the wall sheet, one per side, every ~0.5–1 m. <b>TOWER / PCBOX</b>:
  click round the outline (it closes itself). <b>HOUSE_*</b>: roof outline + the visible part of the bottom edge —
  used only to CHECK the correction, not to fit it. Use the same name for the same structure in every frame.
  Which name is which: the dashed "NAME?" guides (the 09-24 calibration's prediction — only to identify the structure;
  click the REAL one) and the top-view map cv/configs/landmarks/2026c/paddock_schematic.png (A0 = origin corner, x
  along the length, rows A/B/C across; HOUSE_B1 / HOUSE_B3 = the house next to pole B1 / B3).
  <b>Drag</b> a point to move it, <b>right-click</b> to delete. Points are kept in this browser between visits.</small>
  <canvas id="mag" width="240" height="240" style="display:block;margin:6px 0;border:1px solid #888"></canvas>
  <div id="list"></div>
  <div style="margin-top:6px">+ add <input id="newname" size="14" placeholder="NAME"> <select id="newkind"><option>axis</option><option>polyline</option><option>outline</option></select> <button onclick="addLm()">add</button></div>
  <b>Export</b> (also copied here) / paste an earlier export and <button onclick="loadJSON()">Load</button>:<br><textarea id="out"></textarea>
 </div></div>
<script>
const CAM="__CAM__", TS="__TS__", S=__SCALE__, IMGW=__IMGW__, IMGH=__IMGH__, GUIDES=__GUIDES__;
let KIND=__KINDS__;
const GROUP={axis:'Poles (axis)',polyline:'Edges (polyline)',outline:'Outlines (closed)'};
function col(id,i){if(id.startsWith('HOUSE'))return '#9aa0a6';if(id.startsWith('POLE'))return `hsl(${(i*47)%360},95%,55%)`;
  if(id.startsWith('WALLTOP'))return ['#ff3030','#ff8c00','#ff40ff','#ffffff'][i%4];return i%2?'#00e5ff':'#7CFC00';}
let COL={};function recol(){Object.keys(KIND).forEach((l,i)=>COL[l]=col(l,i));} recol();
let lines={}; Object.keys(KIND).forEach(l=>lines[l]=[]); let cur=null, z=0.5;
const ov=document.getElementById('ov'), stage=document.getElementById('stage');
function zoom(f){z=f;stage.style.transform='scale('+z+')';stage.style.width=IMGW+'px';stage.style.height=IMGH+'px';}
function path(pts,closed){return pts.map((p,i)=>(i?'L':'M')+(p[0]*S).toFixed(1)+' '+(p[1]*S).toFixed(1)).join(' ')+(closed&&pts.length>2?' Z':'');}
function draw(){ov.setAttribute('width',IMGW);ov.setAttribute('height',IMGH);let h='';
  if(document.getElementById('showg').checked){for(const [id,g] of Object.entries(GUIDES)){if(g.length<2)continue;
    h+=`<path d="${path(g,KIND[id]==='outline')}" fill="none" stroke="${COL[id]||'#ccc'}" stroke-width="2" stroke-dasharray="14 10" opacity="0.6"/>`;
    const m=g[Math.floor(g.length/2)];h+=`<text x="${m[0]*S+8}" y="${m[1]*S-8}" font-size="22" font-weight="bold" fill="${COL[id]||'#ccc'}" stroke="#000" stroke-width="4" paint-order="stroke" opacity="0.85">${id}?</text>`;}}
  for(const [id,pts] of Object.entries(lines)){if(!pts.length)continue;
    if(pts.length>1)h+=`<path d="${path(pts,KIND[id]==='outline')}" fill="none" stroke="${COL[id]}" stroke-width="${id===cur?4:2.5}"/>`;
    pts.forEach(p=>{h+=`<circle cx="${p[0]*S}" cy="${p[1]*S}" r="${id===cur?9:6}" fill="none" stroke="${COL[id]}" stroke-width="3"/>`;});
    const p=pts[pts.length-1];h+=`<text x="${p[0]*S+10}" y="${p[1]*S+8}" font-size="24" font-weight="bold" fill="${COL[id]}" stroke="#000" stroke-width="5" paint-order="stroke">${id}</text>`;}
  ov.innerHTML=h;list();}
function list(){const L=document.getElementById('list');let h='';for(const k of ['axis','polyline','outline']){h+=`<h4>${GROUP[k]}</h4>`;
  for(const l of Object.keys(KIND).filter(l=>KIND[l]===k))h+=`<button class="ln${l===cur?' cur':''}" style="border-left:12px solid ${COL[l]}" onclick="pick('${l}')">${l}<span class="n">${lines[l].length} pts</span></button>`;}
  L.innerHTML=h;document.getElementById('curinfo').textContent=cur||'none';
  document.getElementById('stat').textContent=Object.values(lines).reduce((a,b)=>a+b.length,0)+' points on '+Object.values(lines).filter(v=>v.length).length+' landmarks';}
function pick(l){cur=l;draw();}
function addLm(){const n=document.getElementById('newname').value.trim().toUpperCase().replace(/[^A-Z0-9_]/g,'_');if(!n)return;
  if(!KIND[n]){KIND[n]=document.getElementById('newkind').value;lines[n]=[];recol();}cur=n;draw();}
function toImg(e){const r=ov.getBoundingClientRect();return [(e.clientX-r.left)/z/S,(e.clientY-r.top)/z/S];}
function hit(x,y){for(const [id,pts] of Object.entries(lines)){for(let i=0;i<pts.length;i++){if(Math.hypot(pts[i][0]-x,pts[i][1]-y)*S*z<12)return [id,i];}}return null;}
let drag=null, hover=null;
ov.addEventListener('contextmenu',e=>{e.preventDefault();const [x,y]=toImg(e);const h=hit(x,y);if(h){lines[h[0]].splice(h[1],1);draw();}});
ov.addEventListener('mousedown',e=>{if(e.button!==0)return;const [x,y]=toImg(e);const h=hit(x,y);
  if(h){drag={id:h[0],i:h[1]};cur=h[0];draw();return;}
  if(!cur){alert('pick a landmark first (right panel)');return;}
  lines[cur].push([Math.round(x*10)/10,Math.round(y*10)/10]);drag={id:cur,i:lines[cur].length-1};draw();});
ov.addEventListener('mousemove',e=>{const [x,y]=toImg(e);hover=[x,y];
  if(drag){lines[drag.id][drag.i]=[Math.round(x*10)/10,Math.round(y*10)/10];draw();}else mag();});
window.addEventListener('mouseup',()=>{if(drag){drag=null;draw();}});
ov.addEventListener('mouseleave',()=>{hover=null;mag();});
function undo(){if(cur&&lines[cur].length){lines[cur].pop();draw();}}
function clearLine(){if(cur&&confirm('clear all points of '+cur+'?')){lines[cur]=[];draw();}}
document.addEventListener('keydown',e=>{if(e.key==='u'&&document.activeElement.tagName!=='INPUT')undo();});
const mg=document.getElementById('mag'), mctx=mg.getContext('2d'), im=document.getElementById('img');
function mag(){if(!hover||!im.complete){mctx.fillStyle='#000';mctx.fillRect(0,0,mg.width,mg.height);return;}
  const Z=4,Sz=mg.width/Z,cx=hover[0]*S,cy=hover[1]*S;mctx.imageSmoothingEnabled=false;
  mctx.fillStyle='#000';mctx.fillRect(0,0,mg.width,mg.height);
  mctx.drawImage(im,cx-Sz/2,cy-Sz/2,Sz,Sz,0,0,mg.width,mg.height);
  for(const [id,pts] of Object.entries(lines))for(const p of pts){const px=(p[0]*S-cx+Sz/2)*Z,py=(p[1]*S-cy+Sz/2)*Z;
    if(px>=0&&px<=mg.width&&py>=0&&py<=mg.height){mctx.strokeStyle=COL[id];mctx.lineWidth=2;mctx.beginPath();mctx.arc(px,py,8,0,7);mctx.stroke();}}
  mctx.strokeStyle='#ff0';mctx.lineWidth=1;mctx.beginPath();mctx.moveTo(mg.width/2-14,mg.height/2);mctx.lineTo(mg.width/2+14,mg.height/2);
  mctx.moveTo(mg.width/2,mg.height/2-14);mctx.lineTo(mg.width/2,mg.height/2+14);mctx.stroke();}
const KEY='landmarks_'+CAM+'_'+TS;
const _draw=draw;draw=function(){_draw();try{localStorage.setItem(KEY,JSON.stringify({lines:lines,kind:KIND}));}catch(e){}};
function loadJSON(){try{const d=JSON.parse(document.getElementById('out').value);const L=d.landmarks||d.lines||d;
  if(d.kind)for(const [k,v] of Object.entries(d.kind))if(!KIND[k])KIND[k]=v;recol();
  for(const [id,pts] of Object.entries(L)){if(lines[id]===undefined){lines[id]=[];if(!KIND[id])KIND[id]='polyline';}lines[id]=pts.map(p=>[+p[0],+p[1]]);}draw();}catch(e){alert('not valid JSON: '+e);}}
function exportJSON(){const out={},kind={};for(const [id,pts] of Object.entries(lines)) if(pts.length){out[id]=pts;kind[id]=KIND[id];}
  const data={camera:CAM,time:TS,frame_size_upright:[IMGW/S,IMGH/S],landmarks:out,kind:kind,source:"__SRC__",
    note:"full-res UPRIGHT px; axis = pole centre line, polyline = open edge, outline = closed; HOUSE_* = validation only"};
  const txt=JSON.stringify(data);document.getElementById('out').value=txt;
  const a=document.createElement('a');a.href='data:application/json;charset=utf-8,'+encodeURIComponent(txt);
  a.download='landmarks_'+CAM+'_'+TS.replace(/[-: ]/g,'').replace(/^(\d{8})(\d{6})$/,'$1_$2')+'.json';a.click();}
try{const s=localStorage.getItem(KEY);if(s){const d=JSON.parse(s);if(d.kind)for(const [k,v] of Object.entries(d.kind))if(!KIND[k])KIND[k]=v;recol();
  for(const [id,pts] of Object.entries(d.lines||{})){lines[id]=pts;}}}catch(e){}
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
