"""thermal/make_label_set.py — build a self-contained HTML labeling tool from detector candidates.

Takes a detection run (detections.csv) + the source video, samples frames, embeds them as JPEGs, and
writes ONE portable `label_tool.html` pre-filled with the detector's candidate boxes. You open it in any
browser (no server, no install), then drag / resize / add / delete boxes (multiple per frame), and click
"Export labels" to download corrected ground truth (labels.json). Feed that to thermal/score_labels.py to
measure the UNSUPERVISED detector's precision/recall and pick an operating point — no training involved.

Sampling (default "mixed"): an even spread across the processed frames (unbiased for recall) PLUS the
frames with the most detections (so multi-object scenes are included, which is where labeling matters most).

Usage:
  python thermal/make_label_set.py --run D:/tmp/thermal_labelrun --video <mp4> --cam 108_thermal \
      --n-frames 40 --out D:/tmp/thermal_labelrun/label_tool.html
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def ffprobe_wh(path: str) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    st = json.loads(out)["streams"][0]
    return int(st["width"]), int(st["height"])


def read_detections(csv_path: Path) -> dict[int, list[dict]]:
    by_frame: dict[int, list[dict]] = defaultdict(list)
    with open(csv_path) as f:
        for r in csv.DictReader(f):
            by_frame[int(r["frame"])].append(dict(
                x=int(r["x"]), y=int(r["y"]), w=int(r["w"]), h=int(r["h"]),
                contrast=float(r.get("tophat_mean", 0) or 0)))
    return by_frame


def pick_frames(by_frame: dict[int, list[dict]], n_total: int, max_frame: int, mode: str) -> list[int]:
    if mode == "detected":
        return sorted(by_frame.keys())[:n_total]
    even = [int(v) for v in np.linspace(0, max_frame, num=max(1, n_total), dtype=int)]
    if mode == "even":
        return sorted(set(even))
    # mixed: even spread + the busiest (multi-object) frames
    busiest = sorted(by_frame.keys(), key=lambda f: -len(by_frame[f]))[:max(4, n_total // 3)]
    return sorted(set(even) | set(int(f) for f in busiest))


def extract_jpeg_b64(video: str, w: int, h: int, frame: int, disp_w: int, quality: int) -> str:
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(frame), "-i", video,
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True)
    buf = p.stdout[:w * h]
    if len(buf) < w * h:
        return ""
    img = np.frombuffer(buf, np.uint8).reshape(h, w)
    if disp_w and disp_w < w:  # downscale for a lighter file; coords stay in ORIGINAL px via scale
        img = cv2.resize(img, (disp_w, int(h * disp_w / w)), interpolation=cv2.INTER_AREA)
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return "data:image/jpeg;base64," + base64.b64encode(enc.tobytes()).decode() if ok else ""


def build(run_dir: Path, video: str, cam: str, n_frames: int, mode: str, out_html: Path,
          disp_w: int, quality: int) -> None:
    assert cv2 is not None, "OpenCV required"
    w, h = ffprobe_wh(video)
    by_frame = read_detections(run_dir / "detections.csv")
    max_frame = max(by_frame) if by_frame else 3599
    frames = pick_frames(by_frame, n_frames, max_frame, mode)
    print(f"sampling {len(frames)} frames (mode={mode}) from {video}")
    scale = w / disp_w if disp_w and disp_w < w else 1.0
    data = []
    for i, fr in enumerate(frames):
        uri = extract_jpeg_b64(video, w, h, fr, disp_w, quality)
        if not uri:
            continue
        boxes = [dict(x=b["x"], y=b["y"], w=b["w"], h=b["h"], src="auto", contrast=round(b["contrast"], 1))
                 for b in by_frame.get(fr, [])]
        data.append(dict(frame=fr, t=fr, img=uri, boxes=boxes))
        print(f"  [{i+1}/{len(frames)}] frame {fr}: {len(boxes)} candidate box(es)")
    meta = dict(video=video, cam=cam, orig_w=w, orig_h=h, disp_w=min(disp_w, w), scale=scale,
                n_frames=len(data), note="Coordinates are ORIGINAL pixel space; drag/resize/add/delete; "
                                          "boxes shown = rats. Export when done.")
    # replace the whole placeholder token INCLUDING its trailing {} / [] fallback literal
    html = (HTML_TEMPLATE
            .replace("/*__META__*/{}", json.dumps(meta))
            .replace("/*__DATA__*/[]", json.dumps(data)))
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")
    mb = out_html.stat().st_size / 1e6
    print(f"\n-> {out_html}  ({mb:.1f} MB, {len(data)} frames)\n   Open it in a browser and start labeling.")


# ---- the self-contained editor (vanilla HTML/CSS/JS; boxes are DOM elements, coords in original px) ----
HTML_TEMPLATE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Thermal label tool</title>
<style>
 body{margin:0;font-family:system-ui,sans-serif;background:#111;color:#ddd}
 #bar{position:sticky;top:0;background:#1c1c1c;padding:8px 12px;display:flex;gap:8px;align-items:center;
      flex-wrap:wrap;border-bottom:1px solid #333;z-index:10}
 button{background:#2b2b2b;color:#ddd;border:1px solid #444;border-radius:5px;padding:6px 10px;cursor:pointer}
 button:hover{background:#3a3a3a}
 button.primary{background:#1f6f3f;border-color:#2c8}
 #stage{position:relative;margin:16px auto;width:max-content}
 #img{display:block;user-select:none;-webkit-user-drag:none}
 #ov{position:absolute;left:0;top:0}
 .box{position:absolute;border:2px solid #2f2;box-sizing:border-box;cursor:move}
 .box.manual{border-color:#2cf}
 .box.sel{border-color:#ff3;box-shadow:0 0 0 1px #ff3}
 .box .tag{position:absolute;top:-16px;left:0;font-size:11px;color:#fff;background:rgba(0,0,0,.6);
           padding:0 3px;white-space:nowrap;pointer-events:none}
 .h{position:absolute;width:10px;height:10px;background:#ff3;border:1px solid #000}
 .h.nw{left:-6px;top:-6px;cursor:nwse-resize}.h.ne{right:-6px;top:-6px;cursor:nesw-resize}
 .h.sw{left:-6px;bottom:-6px;cursor:nesw-resize}.h.se{right:-6px;bottom:-6px;cursor:nwse-resize}
 #info{font-size:13px;color:#aaa}#hint{font-size:12px;color:#888;margin-left:auto}
 kbd{background:#333;border:1px solid #555;border-radius:3px;padding:0 4px}
</style></head><body>
<div id="bar">
 <button onclick="go(-1)">◀ Prev</button>
 <button onclick="go(1)">Next ▶</button>
 <span id="info"></span>
 <button onclick="markEmpty()">No rats here</button>
 <button onclick="delSel()">Delete box</button>
 <button onclick="clearFrame()">Clear frame</button>
 <button class="primary" onclick="exportJSON()">⬇ Export labels</button>
 <span id="hint">drag to move · corners to resize · drag empty area to ADD · <kbd>A</kbd>/<kbd>D</kbd> or <kbd>←</kbd>/<kbd>→</kbd> nav · <kbd>Del</kbd> delete</span>
</div>
<div id="stage"><img id="img" draggable="false"><div id="ov"></div></div>
<script>
const META=/*__META__*/{}, FRAMES=/*__DATA__*/[];
const KEY="thermal_labels_"+(META.video||"set");
const img=document.getElementById('img'), ov=document.getElementById('ov'), info=document.getElementById('info');
let idx=0, sel=null, scale=META.scale||1, dispScale=1;
// restore in-progress work
try{const saved=JSON.parse(localStorage.getItem(KEY)||"null");
    if(saved&&saved.length===FRAMES.length){FRAMES.forEach((f,i)=>{f.boxes=saved[i].boxes;f.reviewed=saved[i].reviewed;});}}catch(e){}
function save(){localStorage.setItem(KEY,JSON.stringify(FRAMES.map(f=>({boxes:f.boxes,reviewed:!!f.reviewed}))));}
function toDisp(v){return v/scale*dispScale;} function toOrig(v){return v*scale/dispScale;}
function show(i){
 idx=(i+FRAMES.length)%FRAMES.length; sel=null; const f=FRAMES[idx];
 img.onload=()=>{dispScale=img.clientWidth/img.naturalWidth; ov.style.width=img.clientWidth+'px';
                 ov.style.height=img.clientHeight+'px'; render();};
 img.src=f.img; updateInfo();
}
function updateInfo(){const n=FRAMES.filter(f=>f.reviewed).length;
 info.textContent=`frame ${FRAMES[idx].frame} (t=${FRAMES[idx].t}s) · ${idx+1}/${FRAMES.length} · `+
 `${FRAMES[idx].boxes.length} box(es) · reviewed ${n}/${FRAMES.length}`;}
function render(){
 ov.innerHTML=''; const f=FRAMES[idx];
 f.boxes.forEach((b,bi)=>{
  const d=document.createElement('div'); d.className='box'+(b.src==='manual'?' manual':'')+(sel===bi?' sel':'');
  d.style.left=toDisp(b.x)+'px'; d.style.top=toDisp(b.y)+'px';
  d.style.width=toDisp(b.w)+'px'; d.style.height=toDisp(b.h)+'px';
  const tag=document.createElement('div'); tag.className='tag';
  tag.textContent=(b.src==='auto'?('auto c'+(b.contrast??'')):'manual'); d.appendChild(tag);
  ['nw','ne','sw','se'].forEach(c=>{const hh=document.createElement('div');hh.className='h '+c;hh.dataset.c=c;d.appendChild(hh);});
  d.addEventListener('mousedown',e=>startBox(e,bi)); ov.appendChild(d);
 });
 updateInfo();
}
function startBox(e,bi){
 e.stopPropagation(); sel=bi; render(); markReviewed();
 const f=FRAMES[idx], b=f.boxes[bi], handle=e.target.dataset.c;
 const sx=e.clientX, sy=e.clientY, o={...b};
 function mm(ev){const dx=toOrig(ev.clientX-sx), dy=toOrig(ev.clientY-sy);
  if(handle){ if(handle.includes('w')){b.x=o.x+dx;b.w=o.w-dx;} if(handle.includes('n')){b.y=o.y+dy;b.h=o.h-dy;}
             if(handle.includes('e')){b.w=o.w+dx;} if(handle.includes('s')){b.h=o.h+dy;}
             if(b.w<4)b.w=4; if(b.h<4)b.h=4; }
  else{b.x=o.x+dx;b.y=o.y+dy;} b.src=b.src==='auto'?'auto':'manual'; render();}
 function mu(){document.removeEventListener('mousemove',mm);document.removeEventListener('mouseup',mu);save();}
 document.addEventListener('mousemove',mm);document.addEventListener('mouseup',mu);
}
ov.addEventListener('mousedown',e=>{ // draw a NEW box on empty area
 if(e.target!==ov)return; const r=ov.getBoundingClientRect();
 const x0=toOrig(e.clientX-r.left), y0=toOrig(e.clientY-r.top);
 const b={x:x0,y:y0,w:1,h:1,src:'manual'}; FRAMES[idx].boxes.push(b); sel=FRAMES[idx].boxes.length-1;
 function mm(ev){b.w=Math.max(1,toOrig(ev.clientX-r.left)-x0); b.h=Math.max(1,toOrig(ev.clientY-r.top)-y0); render();}
 function mu(){document.removeEventListener('mousemove',mm);document.removeEventListener('mouseup',mu);
   if(b.w<6||b.h<6)FRAMES[idx].boxes.pop(); markReviewed(); render(); save();}
 document.addEventListener('mousemove',mm);document.addEventListener('mouseup',mu);
});
function delSel(){if(sel!=null){FRAMES[idx].boxes.splice(sel,1);sel=null;markReviewed();render();save();}}
function clearFrame(){FRAMES[idx].boxes=[];sel=null;markReviewed();render();save();}
function markEmpty(){FRAMES[idx].boxes=[];FRAMES[idx].reviewed=true;sel=null;render();save();}
function markReviewed(){FRAMES[idx].reviewed=true;}
function go(d){markReviewed();save();show(idx+d);}
function exportJSON(){
 save();
 const out={meta:{video:META.video,cam:META.cam,orig_w:META.orig_w,orig_h:META.orig_h,
   exported:FRAMES.filter(f=>f.reviewed).length,total:FRAMES.length},
   frames:FRAMES.map(f=>({frame:f.frame,t:f.t,reviewed:!!f.reviewed,
     boxes:f.boxes.map(b=>({x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.w),h:Math.round(b.h),src:b.src}))}))};
 const blob=new Blob([JSON.stringify(out,null,1)],{type:'application/json'});
 const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='labels.json'; a.click();
}
document.addEventListener('keydown',e=>{
 if(e.key==='ArrowLeft'||e.key==='a')go(-1);
 else if(e.key==='ArrowRight'||e.key==='d')go(1);
 else if(e.key==='Delete'||e.key==='Backspace')delSel();
});
show(0);
</script></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a pre-filled HTML labeling tool from detector output.")
    ap.add_argument("--run", required=True, help="detection run dir (contains detections.csv)")
    ap.add_argument("--video", required=True)
    ap.add_argument("--cam", default="108_thermal")
    ap.add_argument("--n-frames", type=int, default=40, dest="n_frames")
    ap.add_argument("--mode", choices=["mixed", "even", "detected"], default="mixed")
    ap.add_argument("--out", default=None)
    ap.add_argument("--disp-w", type=int, default=1000, dest="disp_w", help="embedded image width (px)")
    ap.add_argument("--quality", type=int, default=80)
    a = ap.parse_args()
    if cv2 is None:
        print("ERROR: OpenCV required")
        return 2
    run_dir = Path(a.run)
    out = Path(a.out) if a.out else run_dir / "label_tool.html"
    build(run_dir, a.video, a.cam, a.n_frames, a.mode, out, a.disp_w, a.quality)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
