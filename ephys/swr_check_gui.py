"""Browser version of DetectSWR's manual `check` step for cohort-3 sessions (user request 2026-10-07: "like the 2D GUI").

The page shows the candidate scatter (swDiff x ripPower, exactly DetectSWR's candidates from `swr_detect.py`). Click a
point -> its +-0.5 s trace (ripple, sharp-wave and noise channel, swDiff, ripPower; `w` toggles +-2 s to see theta
context) with that second's sleep state and head-IMU movement; score it 1 / 0 (Enter = skip, u = undo). Every click is
propagated live with the helper's own rule (nearest click in z-space over non-bad candidates; `swr_detect.
propagate_clicks`). The automatic labels are hidden until "I'm done" (blind first, then compare). "Compute events" runs
DetectSWR's check-mode localisation on the current labels and writes the events.

Data: the session LFP from the local copy (`--lfp-root`, default D:/3rd_rat_spikes/analysis/lfp; copy it from storage
first), the final 1-s states + IMU emg (`states_1s_final`). Bad candidates: the CleanLFP port with the helper's fixed
thresholds. Outputs (scores autosaved on every click, events) under $FIELD2026_ANALYSIS_OUT_ROOT/2026c/swr_check/<SFxx>/
<session>/ch<r>-<s>-<n>/. Nothing is written next to the LFP.

  python ephys/swr_check_gui.py --animal SF10 --session 6_20260906_080449.175 --channels 8 16 10 [--params rat] [--port 8765]
  (channels are DetectSWR's 1-based numbers = exported column + 1)
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swr_detect as sd  # noqa: E402
from _common import git_commit, utc_now_iso, write_json  # noqa: E402
from output_paths import out_root  # noqa: E402

SR = 1250.0
UV = 0.195
PRESETS = {"rat": dict(thresSDswD=(0.25, 0.5), thresSDrip=(0.25, 0.5), maxDurSW=0.8),  # the lab's HP/RM rat runs
           "mouse": {}}  # DetectSWR defaults
STATE_NAME = {0: "?", 1: "WAKE", 2: "?", 3: "NREM", 4: "?", 5: "REM"}


class Session:
    def __init__(self, a):
        self.animal, self.session, self.channels = a.animal, a.session, list(a.channels)
        self.params = sd.Params(**PRESETS[a.params])
        self.lfp_path = Path(a.lfp_root) / a.animal / f"{a.session}.lfp"
        meta = json.loads(Path(str(self.lfp_path) + ".json").read_text())
        self.nchan = int(meta["n_channels"])
        tag = "ch" + "-".join(str(c) for c in self.channels)
        self.out = Path(a.out_root or out_root()) / "2026c" / "swr_check" / a.animal / a.session / tag
        self.out.mkdir(parents=True, exist_ok=True)
        self.states_path = Path(a.states_root) / a.animal / f"{a.session}.states.npz"
        self.lock = threading.Lock()
        self.prepare()

    def prepare(self):
        cache = self.out / "prep.npz"
        mm = np.memmap(self.lfp_path, dtype=np.int16, mode="r")
        self.N = mm.size // self.nchan
        self.raw = mm[: self.N * self.nchan].reshape(self.N, self.nchan)
        self.lfp3 = None
        if cache.exists() and (self.out / "swDiff.f32").exists():
            d = np.load(cache)
            self.ts, self.sw, self.rp, self.bad = d["featureTs"], d["swDiffAll"], d["ripPowerAll"], d["bad"]
            self.auto, self.state, self.emg = d["auto"], d["state"], d["emg"]
        else:
            t0 = time.time()
            print("preparing features (one-off, ~1-2 min) ...", flush=True)
            self.lfp3 = sd.load_channels(str(self.lfp_path), self.nchan, self.channels)
            swDiff, rp0 = sd.features(self.lfp3, SR, self.params)
            self.ts, self.sw, self.rp = sd.candidates(swDiff, rp0, SR, self.params)
            self.bad = sd.in_intervals(self.ts / SR, sd.clean_lfp_intervals(self.lfp3[:, 0], SR))
            swDiff.astype(np.float32).tofile(self.out / "swDiff.f32")
            rp0.astype(np.float32).tofile(self.out / "ripPower0.f32")
            ok = ~self.bad
            Z = self.zcoords()
            sec = (self.ts / SR).astype(int)
            self.state = np.zeros(self.ts.size, np.uint8)
            self.emg = np.full(self.ts.size, np.nan, np.float32)
            if self.states_path.exists():
                st = np.load(self.states_path)
                idx = np.searchsorted(st["ts"], sec)
                good = (idx < st["ts"].size) & (st["ts"][np.minimum(idx, st["ts"].size - 1)] == sec)
                self.state[good] = st["state"][idx[good]]
                self.emg[good] = st["emg"][idx[good]]
            # the automatic labels = the production rule (swr_auto.py): k-means fitted on NREM candidates when the session
            # has >= 10 min NREM, applied to all non-bad candidates as the nearest centre; else fitted on all candidates
            import swr_auto
            fit = ok & (self.state == 3)
            if fit.sum() < swr_auto.MIN_NREM_MIN * 60 * 20:
                fit = ok
            X = np.column_stack([self.sw, self.rp]).astype(float)
            Zf = (X - X[fit].mean(0)) / X[fit].std(0, ddof=1)
            _, c_sel, c_rest = swr_auto.kmeans_minority(Zf[fit])
            self.auto = ok & (np.sum((Zf - c_sel) ** 2, 1) < np.sum((Zf - c_rest) ** 2, 1))
            np.savez_compressed(cache, featureTs=self.ts, swDiffAll=self.sw, ripPowerAll=self.rp, bad=self.bad,
                                auto=self.auto, state=self.state, emg=self.emg)
            write_json(self.out / "prep.json", dict(animal=self.animal, session=self.session, channels_1based=self.channels,
                       params=self.params.__dict__, lfp=str(self.lfp_path), states=str(self.states_path),
                       n_candidates=int(self.ts.size), n_bad=int(self.bad.sum()), git_commit=git_commit(),
                       created_utc=utc_now_iso(), seconds=round(time.time() - t0)))
            print(f"prepared in {time.time()-t0:.0f} s: {self.ts.size} candidates", flush=True)
        self.swDiff = np.memmap(self.out / "swDiff.f32", dtype=np.float32, mode="r")
        self.rp0 = np.memmap(self.out / "ripPower0.f32", dtype=np.float32, mode="r")

    def zcoords(self):
        X = np.column_stack([self.sw, self.rp]).astype(float)
        ok = ~self.bad
        return (X - X[ok].mean(0)) / X[ok].std(0, ddof=1)

    def points_blob(self) -> bytes:
        Z = self.zcoords()
        n = self.ts.size
        parts = [np.array([n], np.uint32).tobytes()]
        for a in (self.sw, self.rp, Z[:, 0], Z[:, 1], self.ts / SR):
            parts.append(np.asarray(a, np.float32).tobytes())
        for a in (self.bad, self.auto, self.state):
            parts.append(np.asarray(a, np.uint8).tobytes())
        return b"".join(parts)

    def trace(self, i: int, half_s: float) -> dict:
        c = int(self.ts[i]) - 1
        h = int(half_s * SR)
        a, b = max(c - h, 0), min(c + h + 1, self.N)
        step = 1 if half_s <= 0.6 else 2
        sl = slice(a, b, step)
        cols = [ch - 1 for ch in self.channels]
        lfp = np.asarray(self.raw[a:b:step][:, cols], float) * UV
        lo, hi = np.searchsorted(self.ts, a + 1), np.searchsorted(self.ts, b)
        others = [(int(t) - 1 - c) / SR for t in self.ts[lo:hi] if t - 1 != c]
        return dict(i=i, t_s=float(self.ts[i] / SR), x=((np.arange(a, b, step) - c) / SR).round(4).tolist(),
                    lfp=[lfp[:, k].round(1).tolist() for k in range(lfp.shape[1])],
                    swDiff=np.asarray(self.swDiff[sl], float).round(1).tolist(),
                    ripPower=np.asarray(self.rp0[sl], float).round(2).tolist(), others=others,
                    state=STATE_NAME.get(int(self.state[i]), "?"),
                    emg=None if np.isnan(self.emg[i]) else round(float(self.emg[i]), 3),
                    sw=float(self.sw[i]), rp=float(self.rp[i]), bad=bool(self.bad[i]))

    def save_scores(self, scores: dict) -> Path:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        payload = dict(animal=self.animal, session=self.session, channels_1based=self.channels, saved_local=stamp,
                       scores={str(k): v for k, v in scores.items()}, n_clicks=len(scores))
        (self.out / "scores_latest.json").write_text(json.dumps(payload, indent=1))
        return self.out / "scores_latest.json"

    def load_scores(self) -> dict:
        f = self.out / "scores_latest.json"
        return json.loads(f.read_text())["scores"] if f.exists() else {}

    def events(self, scores: dict) -> dict:
        s = np.full(self.ts.size, np.nan)
        for k, v in scores.items():
            s[int(k)] = float(v)
        if np.isnan(s).all():
            return dict(error="no clicks yet")
        idx1, _ = sd.propagate_clicks(self.sw, self.rp, s, self.bad)
        if self.lfp3 is None:
            self.lfp3 = sd.load_channels(str(self.lfp_path), self.nchan, self.channels)
        fe = dict(swDiff=np.asarray(self.swDiff, float), ripPower0=np.asarray(self.rp0, float), featureTs=self.ts,
                  swDiffAll=self.sw, ripPowerAll=self.rp)
        pc = sd.Params(**{**self.params.__dict__, "useSPW": False})  # check mode
        ev, loc = sd.events_from_mask(fe, self.lfp3[:, 0], idx1, SR, pc)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        np.savez_compressed(self.out / f"events_{stamp}.npz", **ev, idx1=idx1, scores=s)
        import pandas as pd
        pd.DataFrame({k: ev[k] for k in ("start", "stop", "peak", "amplitude", "frequency", "SwMax", "RipMax")}).to_csv(
            self.out / f"events_{stamp}.csv", index=False)
        agree = float(np.mean(idx1[~self.bad] == self.auto[~self.bad]))
        return dict(n_events=int(ev["peak"].size), n_selected=int(idx1.sum()), file=str(self.out / f"events_{stamp}.csv"),
                    reasons=loc.reasons, agree_with_auto=round(agree, 4))


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>SWR check</title>
<style>
:root{--bg:#fff;--fg:#222;--mut:#888;--pan:#f6f6f6}
@media (prefers-color-scheme:dark){:root{--bg:#1b1b1b;--fg:#ddd;--mut:#888;--pan:#262626}}
body{margin:0;font:13px system-ui,sans-serif;background:var(--bg);color:var(--fg)}
#top{padding:6px 10px;display:flex;gap:14px;align-items:center;flex-wrap:wrap;background:var(--pan)}
#wrap{display:flex;flex-wrap:wrap;gap:8px;padding:8px}
#sc{border:1px solid #8884;cursor:crosshair;flex-shrink:0;width:640px;height:560px}
#tr{flex-shrink:0}
#tr{border:1px solid #8884}
button{font:inherit;padding:3px 8px}
.k{font-family:monospace;background:#8882;padding:0 4px;border-radius:3px}
#msg{color:var(--mut)}
</style></head><body>
<div id="top"><b id="title"></b>
<span>clicks <b id="nc">0</b> (1: <b id="n1">0</b>)</span><span>selected <b id="nsel">0</b></span>
<label><input type="checkbox" id="zoom" checked> zoom 0.05-99.95 %</label>
<button id="done">I'm done: reveal automatic labels</button><button id="ev">Compute events</button>
<span id="msg"></span></div>
<div id="wrap"><canvas id="sc" width="640" height="560"></canvas><div><canvas id="tr" width="760" height="560"></canvas>
<div id="info" style="padding:4px 0"></div>
<div style="color:var(--mut)">keys: <span class="k">1</span> ripple <span class="k">0</span> not <span class="k">Enter</span> skip
<span class="k">u</span> undo <span class="k">w</span> +-0.5 / +-2 s</div></div></div>
<script>
let N,SW,RP,ZX,ZY,T,BAD,AUTO,ST, scores=new Map(), order=[], cur=-1, hov=-1, half=0.5, reveal=false, est=null, view=null, grid=null;
const base=document.createElement('canvas'); base.width=640; base.height=560; const bg=base.getContext('2d'); const CELL=6;
const sc=document.getElementById('sc'), g=sc.getContext('2d'), tr=document.getElementById('tr'), h=tr.getContext('2d');
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n);
async function init(){
  const meta=await (await fetch('/api/meta')).json(); document.getElementById('title').textContent=meta.title;
  const b=await (await fetch('/api/points.bin')).arrayBuffer(); N=new Uint32Array(b,0,1)[0]; let o=4;
  const f=()=>{const a=new Float32Array(b,o,N); o+=4*N; return a}; SW=f();RP=f();ZX=f();ZY=f();T=f();
  const u=()=>{const a=new Uint8Array(b,o,N); o+=N; return a}; BAD=u();AUTO=u();ST=u();
  const prev=await (await fetch('/api/scores')).json(); for(const [k,v] of Object.entries(prev)){scores.set(+k,v);order.push(+k)}
  setView(); propagate(); drawBase(); draw();
}
function pct(a,q){const s=Array.from(a).filter((x,i)=>!BAD[i]).sort((x,y)=>x-y); return s[Math.floor(q*(s.length-1))]}
function mm(a){let lo=Infinity,hi=-Infinity; for(let i=0;i<a.length;i++){ if(BAD[i]) continue; if(a[i]<lo) lo=a[i]; if(a[i]>hi) hi=a[i]} return [lo,hi]}
function setView(){const z=document.getElementById('zoom').checked;
  if(z){view={x0:pct(SW,.0005),x1:pct(SW,.9995),y0:pct(RP,.0005),y1:pct(RP,.9995)}}
  else{const [x0,x1]=mm(SW),[y0,y1]=mm(RP); view={x0,x1,y0,y1}}
  grid=new Map(); for(let i=0;i<N;i++){ if(BAD[i]) continue; const k=Math.floor(PX(SW[i])/CELL)*10000+Math.floor(PY(RP[i])/CELL);
    let a=grid.get(k); if(!a){a=[]; grid.set(k,a)} a.push(i)}}
function nearest(mx,my){ const cx=Math.floor(mx/CELL), cy=Math.floor(my/CELL); let bd=1e30,bi=-1;
  for(let r=0;r<40;r++){ for(let x=cx-r;x<=cx+r;x++) for(let y=cy-r;y<=cy+r;y++){ if(Math.max(Math.abs(x-cx),Math.abs(y-cy))!==r) continue;
      const a=grid.get(x*10000+y); if(!a) continue; for(const i of a){const dx=PX(SW[i])-mx, dy=PY(RP[i])-my, d=dx*dx+dy*dy; if(d<bd){bd=d;bi=i}}}
    if(bi>=0 && Math.sqrt(bd)<=(r)*CELL) break }
  return bi }
function mouse(e){ const r=sc.getBoundingClientRect();
  return [(e.clientX-r.left-sc.clientLeft)*sc.width/sc.clientWidth, (e.clientY-r.top-sc.clientTop)*sc.height/sc.clientHeight] }
const PX=x=>50+(x-view.x0)/(view.x1-view.x0)*(sc.width-60), PY=y=>sc.height-30-(y-view.y0)/(view.y1-view.y0)*(sc.height-40);
function propagate(){ // the helper: nearest click in z-space, estimate > 0.1 -> ripple
  est=new Float32Array(N).fill(NaN); const ks=[...scores.keys()]; if(!ks.length) return;
  for(let i=0;i<N;i++){ if(BAD[i]) continue; let bd=1e30,bv=0;
    for(const k of ks){const dx=ZX[i]-ZX[k],dy=ZY[i]-ZY[k],d=dx*dx+dy*dy; if(d<bd){bd=d;bv=scores.get(k)}} est[i]=bv}
}
let NSEL=0;
function drawBase(){
  bg.fillStyle=css('--bg'); bg.fillRect(0,0,base.width,base.height); let nsel=0;
  for(let i=0;i<N;i++){ if(BAD[i]) continue; let c;
    if(reveal){ const u=est[i]>0.1, a=AUTO[i]; c=u&&a?'#2a2':u?'#d33':a?'#36f':'#9995'; }
    else c=isNaN(est[i])?'#9995':(est[i]>0.1?'#2a2':'#9996');
    if(est[i]>0.1) nsel++;
    bg.fillStyle=c; bg.fillRect(PX(SW[i]),PY(RP[i]),1.4,1.4)}
  NSEL=nsel;
}
function draw(){
  g.drawImage(base,0,0);
  for(const [k,v] of scores){ g.strokeStyle=v>0.1?'#000':'#d33'; g.lineWidth=1.5; g.beginPath(); g.arc(PX(SW[k]),PY(RP[k]),5,0,7); g.stroke()}
  if(cur>=0){g.strokeStyle='#f80'; g.lineWidth=2; g.beginPath(); g.arc(PX(SW[cur]),PY(RP[cur]),8,0,7); g.stroke()}
  if(hov>=0&&hov!==cur){g.strokeStyle='#f80'; g.lineWidth=1; g.beginPath(); g.arc(PX(SW[hov]),PY(RP[hov]),6,0,7); g.stroke()}
  g.fillStyle=css('--fg'); g.fillText('swDiff (sharp-wave depth) ->',sc.width/2-60,sc.height-8);
  g.save(); g.translate(12,sc.height/2+60); g.rotate(-Math.PI/2); g.fillText('ripPower (ripple - noise) ->',0,0); g.restore();
  if(reveal) g.fillText('green both | red you only | blue auto only',60,14);
  document.getElementById('nc').textContent=scores.size;
  document.getElementById('n1').textContent=[...scores.values()].filter(v=>v>0.1).length;
  document.getElementById('nsel').textContent=NSEL;
}
let pend=false;
sc.onmousemove=e=>{ if(pend) return; pend=true; requestAnimationFrame(()=>{pend=false; const [mx,my]=mouse(e); hov=nearest(mx,my); draw()})};
sc.onmouseleave=()=>{hov=-1; draw()};
sc.onclick=async e=>{ const [mx,my]=mouse(e); const bi=nearest(mx,my); if(bi<0) return; cur=bi; draw(); await showTrace()};
async function showTrace(){ if(cur<0) return; const d=await (await fetch(`/api/trace?i=${cur}&half=${half}`)).json();
  const rows=[['ripple ch',d.lfp[0]],['sharp-wave ch',d.lfp[1]],['noise ch',d.lfp[2]||null],['swDiff',d.swDiff],['ripPower',d.ripPower]]
    .filter(r=>r[1]); const H=tr.height/rows.length, W=tr.width-70;
  h.fillStyle=css('--bg'); h.fillRect(0,0,tr.width,tr.height); const X=x=>60+(x+half)/(2*half)*W;
  rows.forEach(([name,y],k)=>{ const y0=k*H, lo=Math.min(...y), hi=Math.max(...y), Y=v=>y0+H-6-(v-lo)/((hi-lo)||1)*(H-12);
    h.strokeStyle='#8884'; h.strokeRect(60,y0+2,W,H-4); h.fillStyle=css('--fg'); h.fillText(name,2,y0+H/2);
    h.fillStyle=css('--mut'); h.fillText(hi.toFixed(0),2,y0+12);
    h.strokeStyle=['#c33','#36c','#888','#2a2','#a3a'][k]; h.lineWidth=1; h.beginPath();
    y.forEach((v,j)=>{const px=X(d.x[j]),py=Y(v); j?h.lineTo(px,py):h.moveTo(px,py)}); h.stroke();
    h.strokeStyle='#f80'; h.beginPath(); h.moveTo(X(0),y0+2); h.lineTo(X(0),y0+H-2); h.stroke();
    h.setLineDash([3,3]); h.strokeStyle='#8888'; d.others.forEach(t=>{h.beginPath(); h.moveTo(X(t),y0+2); h.lineTo(X(t),y0+H-2); h.stroke()}); h.setLineDash([])});
  const s=scores.has(cur)?` | scored ${scores.get(cur)}`:'';
  document.getElementById('info').textContent=`candidate ${cur} at ${d.t_s.toFixed(3)} s (${(d.t_s/3600).toFixed(2)} h) | state ${d.state} | IMU movement ${d.emg} | swDiff ${d.sw.toFixed(0)} ripPower ${d.rp.toFixed(1)}${s} | window +-${half} s`;
}
async function save(){ await fetch('/api/save',{method:'POST',body:JSON.stringify(Object.fromEntries(scores))}); }
document.onkeydown=async e=>{
  if(e.key==='w'){half=half<1?2:0.5; showTrace(); return}
  if(e.key==='u'&&order.length){const k=order.pop(); scores.delete(k); propagate(); drawBase(); draw(); save(); return}
  if(cur<0) return;
  if(e.key==='1'||e.key==='0'){ if(!scores.has(cur)) order.push(cur); scores.set(cur,+e.key); propagate(); drawBase(); draw(); showTrace(); save();
    document.getElementById('msg').textContent='saved'; }
  if(e.key==='Enter'){cur=-1; draw()}
};
document.getElementById('zoom').onchange=()=>{setView(); drawBase(); draw()};
document.getElementById('done').onclick=()=>{reveal=!reveal; drawBase(); draw()};
document.getElementById('ev').onclick=async()=>{ document.getElementById('msg').textContent='computing events ...';
  const r=await (await fetch('/api/events',{method:'POST',body:JSON.stringify(Object.fromEntries(scores))})).json();
  document.getElementById('msg').textContent=r.error||`${r.n_events} events (from ${r.n_selected} selected candidates; agreement with auto ${r.agree_with_auto}) -> ${r.file}`};
init();
</script></body></html>"""


def make_handler(S: Session):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/":
                return self.send(200, PAGE.encode(), "text/html; charset=utf-8")
            if u.path == "/api/meta":
                t = f"{S.animal} {S.session}  channels {S.channels} (ripple, sharp wave, noise; 1-based)  {S.ts.size} candidates"
                return self.send(200, json.dumps(dict(title=t)).encode(), "application/json")
            if u.path == "/api/points.bin":
                return self.send(200, S.points_blob(), "application/octet-stream")
            if u.path == "/api/scores":
                return self.send(200, json.dumps(S.load_scores()).encode(), "application/json")
            if u.path == "/api/trace":
                q = parse_qs(u.query)
                d = S.trace(int(q["i"][0]), float(q.get("half", ["0.5"])[0]))
                return self.send(200, json.dumps(d).encode(), "application/json")
            self.send(404, b"not found", "text/plain")

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/api/save":
                with S.lock:
                    S.save_scores(body)
                return self.send(200, b'{"ok":true}', "application/json")
            if self.path == "/api/events":
                with S.lock:
                    S.save_scores(body)
                    r = S.events(body)
                return self.send(200, json.dumps(r).encode(), "application/json")
            self.send(404, b"not found", "text/plain")
    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--animal", required=True)
    ap.add_argument("--session", required=True)
    ap.add_argument("--channels", type=int, nargs=3, required=True, help="1-based ripple, sharp-wave, noise channel")
    ap.add_argument("--params", choices=sorted(PRESETS), default="rat")
    ap.add_argument("--lfp-root", default="D:/3rd_rat_spikes/analysis/lfp")
    ap.add_argument("--states-root", default="D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final")
    ap.add_argument("--out-root", default=None)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    S = Session(a)
    if a.prepare_only:
        print("prepared:", S.out)
        return
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(S))
    url = f"http://127.0.0.1:{a.port}/"
    print(f"SWR check GUI for {S.animal} {S.session}: {url}  (outputs: {S.out}; Ctrl+C to stop)", flush=True)
    if not a.no_browser:
        webbrowser.open(url)
    srv.serve_forever()


if __name__ == "__main__":
    main()
