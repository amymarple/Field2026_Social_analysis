"""Review page for detected delta waves: does the LFP look like a DOWN state? (the user judges; nothing is decided here)

Per example event, +-WIN s around the delta peak of the reference column:
  - the LFP of every site of the reference shank (top -> tip, as recorded, 1250 Hz), start / peak / end marked;
  - raw multi-unit threshold crossings of the same sites (20-kHz amplifier.dat read-only; common median reference,
    600-6000 Hz, -4.5 MAD threshold fixed per channel from 60 s of NREM, 1-ms refractory) and the summed MUA of all
    live sites in 20-ms bins.
Events = the `delta_detect.py scan` detections of the reference column whose window lies inside one NREM bout, drawn
evenly from the four amplitude (z peak - z end) quartiles. An overview tab shows the scan's delta-triggered LFP and,
if present, the MUA PETH of `delta_mua_check.py`. Verdict keys 1 / 2 / 3, autosave in the browser, CSV + JSON export
(keep exports in ephys/configs/delta_review_2026c/).

  python ephys/delta_review_gui.py --set SF11:12_20260902_083534.755:11 [--set ...] --n 30 \
      --lfp-root <.../analysis/lfp> --raw-root <E:/3rd_rat_spikes> --states-root <.../sleep/imu_remclean> \
      --scan-dir <delta_scan dir> --out <dir>      -> <dir>/index.html
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delta_detect as dd  # noqa: E402
import swr_detect as sd  # noqa: E402
import swr_layer_order as slo  # noqa: E402
from make_session_xml import load_probe  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FL, FS = 1250.0, 20000.0
WIN = 1.5


def raw_dir(raw_root: Path, animal: str, session: str) -> Path:
    return next((raw_root / f"SF{int(animal[2:])}").glob(f"*/{session}"))


def build_set(animal, session, ref, n, a, rng):
    lfp_path = Path(a.lfp_root) / animal / f"{session}.lfp"
    meta = json.loads(Path(str(lfp_path) + ".json").read_text())
    nch = int(meta["n_channels"])
    xml = Path(load_probe(REPO / "ephys/configs/probes_2026c.yaml", animal)["xml_resolved"])
    groups, skip = slo.read_groups(xml)
    shank = next(gi for gi, g in enumerate(groups) if ref in g)
    sites = groups[shank]
    live = [c for c in range(nch) if c not in skip]
    nrem = dd.load_nrem(Path(a.states_root) / animal / session / "complex_system" / f"{session}.SleepState.states.mat")
    scan = np.load(Path(a.scan_dir) / f"{animal}_{session}_delta_scan.npz")
    D = scan[f"deltas_{ref}"]
    inside = sd.in_intervals(D[:, 1] - WIN, nrem) & sd.in_intervals(D[:, 1] + WIN, nrem)
    same = np.searchsorted(nrem[:, 0], D[:, 1] - WIN, "right") == np.searchsorted(nrem[:, 0], D[:, 1] + WIN, "right")
    D = D[inside & same]
    amp = D[:, 4] - D[:, 5]
    q = np.digitize(amp, np.percentile(amp, [25, 50, 75]))
    pick = np.concatenate([rng.choice(np.flatnonzero(q == k), size=min(n // 4 + (k < n % 4), int(np.sum(q == k))),
                                      replace=False) for k in range(4)])
    pick = rng.permutation(pick)
    lfp = np.memmap(lfp_path, dtype=np.int16, mode="r")
    lfp = lfp[: lfp.size // nch * nch].reshape(-1, nch)
    raw = np.memmap(raw_dir(Path(a.raw_root), animal, session) / "amplifier.dat", dtype=np.int16, mode="r")
    raw = raw[: raw.size // nch * nch].reshape(-1, nch)
    sos = signal.butter(3, (600, 6000), btype="bandpass", fs=FS, output="sos")
    # fixed thresholds from 60 s in the middle of the longest NREM bout
    b = nrem[np.argmax(nrem[:, 1] - nrem[:, 0])]
    c0 = int(((b[0] + b[1]) / 2 - 30) * FS)
    x = np.asarray(raw[c0:c0 + int(60 * FS)], np.float32)
    x -= np.median(x[:, live], axis=1, keepdims=True)
    thr = -4.5 * np.median(np.abs(signal.sosfiltfilt(sos, x, axis=0)), axis=0) / 0.6745
    del x
    t0 = dt.datetime.fromisoformat(meta["start_local"])
    w, wr, m = int(WIN * FL), int(WIN * FS), int(0.05 * FS)
    events = []
    for i in pick:
        st, pk, en = D[i, 0], D[i, 1], D[i, 2]
        k = int(round(pk * FL)) - 1  # LFP sample of the peak (time = (k + 1) / fs)
        seg = np.asarray(lfp[k - w:k + w + 1][:, sites]).T.astype(np.int16)
        r0 = 16 * k - wr
        x = np.asarray(raw[r0 - m:r0 + 2 * wr + 1 + m], np.float32)
        x -= np.median(x[:, live], axis=1, keepdims=True)
        y = signal.sosfiltfilt(sos, x, axis=0)[m:-m]
        below = y < thr
        on = below[1:] & ~below[:-1]
        spikes = {}
        for c in range(nch):
            t = np.flatnonzero(on[:, c]) + 1
            if t.size:
                t = t[np.concatenate([[True], np.diff(t) > 20])]
            spikes[str(c)] = np.round((t - wr) / FS * 1000).astype(int).tolist()
        events.append(dict(idx=int(i), t=round(float(pk), 4), clock=(t0 + dt.timedelta(seconds=float(pk))).strftime("%m-%d %H:%M:%S"),
                           amp=round(float(amp[i]), 2), z=[round(float(v), 2) for v in D[i, 3:6]],
                           dur_ms=round(float(en - st) * 1000), start=round(float(st - pk), 4), end=round(float(en - pk), 4),
                           lfp=base64.b64encode(seg.tobytes()).decode("ascii"), spikes=spikes))
    lam_i = int(np.flatnonzero(scan["cols"] == ref)[0])
    lam = scan["lam"][lam_i][sites][:, ::2]  # +-1 s at 625 Hz
    mua_file = Path(a.scan_dir) / f"{animal}_{session}_mua_check_ref{ref}.npz"
    mua = None
    if mua_file.exists():
        z = np.load(mua_file)
        base = (z["lag"] >= -1.0) & (z["lag"] <= -0.6)
        mua = dict(lag=z["lag"].round(3).tolist(), rate=[(z["rate"][c] / max(z["rate"][c][base].mean(), 1e-9)).round(3).tolist()
                                                         if z["mean_rate"][c] >= 1 else None for c in sites],
                   mean_rate=[round(float(z["mean_rate"][c]), 2) for c in sites])
    return dict(name=f"{animal} {session} - shank {shank + 1}, ref col {ref}", animal=animal, session=session, ref=int(ref),
                shank=shank + 1, sites=[int(c) for c in sites], skip=[int(c) for c in sites if c in skip], live=live,
                fs=FL, win=WIN, n_sites=len(sites), events=events, lam=np.round(lam, 1).tolist(), lam_fs=FL / 2, mua=mua,
                thr_uV=[round(float(-thr[c]) * dd.UV_PER_BIT, 1) for c in sites], xml=xml.name)


PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Delta Wave Review</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{--bg:#fafafa;--fg:#222;--muted:#666;--line:#ddd;--acc:#d9480f;--ok:#2b8a3e;--bad:#c92a2a;--uns:#e67700;--panel:#fff}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#16181b;--fg:#e6e6e6;--muted:#9aa0a6;--line:#333;--panel:#1f2226}}
body{margin:0;font:14px/1.4 system-ui,sans-serif;background:var(--bg);color:var(--fg)}
header{padding:10px 16px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:10px;align-items:center}
header h1{font-size:16px;margin:0 12px 0 0}
select,button,input{font:inherit;padding:4px 8px}
main{padding:12px 16px;max-width:1300px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:8px;margin-bottom:10px}
canvas{width:100%;display:block}
.verd button{min-width:110px}
.v1{background:var(--ok);color:#fff}.v2{background:var(--bad);color:#fff}.v3{background:var(--uns);color:#fff}
.info{color:var(--muted);font-size:13px}
.tabs button.on{border-bottom:3px solid var(--acc)}
#notes{width:60%}
</style></head><body>
<header><h1>Delta wave review</h1>
<span class="tabs"><button id="tEv" class="on">Events</button><button id="tOv">Overview</button></span>
<select id="setSel"></select>
<button id="prev">&larr;</button><span id="pos"></span><button id="next">&rarr;</button>
<label>LFP gain <input id="gain" type="range" min="0.2" max="5" step="0.1" value="1"></label>
<label><input id="lp" type="checkbox"> 0-30 Hz view</label>
<button id="exp">Export CSV + JSON</button>
</header>
<main>
<div id="evView">
<div class="panel info" id="evInfo"></div>
<div class="panel"><canvas id="cLfp" height="520"></canvas></div>
<div class="panel"><canvas id="cRas" height="300"></canvas></div>
<div class="panel"><canvas id="cHist" height="110"></canvas></div>
<div class="panel verd">Does this look like a delta wave / DOWN state?
<button class="v1" data-v="1">1 looks like it</button><button class="v2" data-v="2">2 does not</button><button class="v3" data-v="3">3 unsure</button>
<span id="cur"></span><br><input id="notes" placeholder="note (optional)"></div>
</div>
<div id="ovView" style="display:none">
<div class="panel info" id="ovInfo"></div>
<div class="panel"><canvas id="cLam" height="460"></canvas></div>
<div class="panel"><canvas id="cPeth" height="380"></canvas></div>
</div>
</main>
<script>
const DATA = __DATA__;
const KEY = "delta_review_" + DATA.tag;
let S = 0, E = 0, V = {};
try { V = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { V = {}; }
function save(){ try { localStorage.setItem(KEY, JSON.stringify(V)); } catch (e) {} }
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function dec(b64){ const s = atob(b64), u = new Uint8Array(s.length); for (let i=0;i<s.length;i++) u[i]=s.charCodeAt(i); return new Int16Array(u.buffer); }
function prep(c){ const r = c.getBoundingClientRect(), d = window.devicePixelRatio||1; c.width = r.width*d; c.height = c.getAttribute("height")*d; const g = c.getContext("2d"); g.scale(d,d); g.font="11px system-ui"; return [g, r.width, +c.getAttribute("height")]; }
function lowpass(x, fs, fc){ // zero-phase one-pole x2 each way (display only)
  const a = Math.exp(-2*Math.PI*fc/fs), y = Float32Array.from(x);
  for (let p=0;p<2;p++){ for (let i=1;i<y.length;i++) y[i]=a*y[i-1]+(1-a)*y[i]; for (let i=y.length-2;i>=0;i--) y[i]=a*y[i+1]+(1-a)*y[i]; }
  return y; }
const L = 70, R = 10;
function xpix(t, w, win){ return L + (t + win) / (2*win) * (w - L - R); }
function marks(g, ev, w, h, win){
  g.strokeStyle = css("--acc"); g.setLineDash([4,3]);
  for (const t of [ev.start, ev.end]) { const x = xpix(t,w,win); g.beginPath(); g.moveTo(x,0); g.lineTo(x,h); g.stroke(); }
  g.setLineDash([]); const x = xpix(0,w,win); g.beginPath(); g.moveTo(x,0); g.lineTo(x,h); g.stroke(); }
function axisT(g, w, h, win){ g.fillStyle = css("--muted"); for (let t=-win; t<=win+1e-9; t+=0.5){ g.fillText(t.toFixed(1)+" s", xpix(t,w,win)-12, h-2); } }
function drawEvent(){
  const st = DATA.sets[S], ev = st.events[E], n = st.n_sites, ns = 2*Math.round(st.win*st.fs)+1;
  const raw = dec(ev.lfp), uv = 0.195, gain = +document.getElementById("gain").value, lp = document.getElementById("lp").checked;
  document.getElementById("pos").textContent = ` ${E+1} / ${st.events.length} `;
  const vv = V[st.name] && V[st.name][ev.idx];
  document.getElementById("cur").textContent = vv ? "  saved: " + ["","looks like it","does not","unsure"][vv.v] : "";
  document.getElementById("notes").value = vv && vv.note ? vv.note : "";
  document.getElementById("evInfo").innerHTML = `<b>${st.name}</b> &middot; event #${ev.idx} at ${ev.t.toFixed(2)} s (${ev.clock}) &middot; amplitude z(peak) - z(end) = ${ev.amp} (start ${ev.z[0]}, peak ${ev.z[1]}, end ${ev.z[2]}) &middot; duration ${ev.dur_ms} ms &middot; orange lines = start / peak / end; red trace = reference column ${st.ref}`;
  // LFP traces
  let [g, w, h] = prep(document.getElementById("cLfp"));
  const rows = [], step = (h-20)/n;
  let rng = 0;
  for (let s=0;s<n;s++){ let x = Float32Array.from(raw.subarray(s*ns,(s+1)*ns), v=>v*uv); if (lp) x = lowpass(x, st.fs, 30);
    let m = 0; for (const v of x) m += v; m /= x.length; for (let i=0;i<x.length;i++) x[i]-=m; rows.push(x);
    if (!st.skip.includes(st.sites[s])) for (const v of x) rng = Math.max(rng, Math.abs(v)); }
  const sc = gain * step * 1.6 / (rng || 1);
  marks(g, ev, w, h-14, st.win);
  for (let s=0;s<n;s++){ const y0 = 8 + step*(s+0.5), c = st.sites[s], dead = st.skip.includes(c);
    g.strokeStyle = c===st.ref ? "#e03131" : (dead ? css("--line") : css("--fg")); g.lineWidth = c===st.ref ? 1.4 : 0.8;
    g.beginPath(); const x = rows[s];
    for (let i=0;i<ns;i++){ const px = L + i/(ns-1)*(w-L-R), py = y0 - x[i]*sc; i ? g.lineTo(px,py) : g.moveTo(px,py); } g.stroke();
    g.fillStyle = css("--muted"); g.fillText(`${s+1}: ${c}${dead?" x":""}`, 4, y0+4); }
  g.fillStyle = css("--muted"); g.fillText(`LFP as recorded${lp?" (display low-pass 30 Hz)":""}; up = positive; scale bar ${(50).toFixed(0)} uV:`, L, 10);
  g.strokeStyle = css("--fg"); g.beginPath(); g.moveTo(w-R-5, 20); g.lineTo(w-R-5, 20+50*sc); g.stroke();
  axisT(g, w, h, st.win);
  // raster
  [g, w, h] = prep(document.getElementById("cRas"));
  const rs = (h-20)/n; marks(g, ev, w, h-14, st.win);
  for (let s=0;s<n;s++){ const c = st.sites[s], y0 = 6 + rs*s, sp = ev.spikes[String(c)] || [];
    g.fillStyle = css("--muted"); g.fillText(`${c} (${st.thr_uV[s]} uV)`, 4, y0+rs*0.7);
    g.strokeStyle = css("--fg"); g.beginPath();
    for (const ms of sp){ const x = xpix(ms/1000, w, st.win); g.moveTo(x, y0+1); g.lineTo(x, y0+rs-1); } g.stroke(); }
  g.fillStyle = css("--muted"); g.fillText("multi-unit threshold crossings (raw 20 kHz), same sites", L, 10); axisT(g, w, h, st.win);
  // summed MUA of all live sites, 20-ms bins
  [g, w, h] = prep(document.getElementById("cHist"));
  const nb = Math.round(2*st.win/0.02), cnt = new Array(nb).fill(0);
  for (const c of st.live){ for (const ms of (ev.spikes[String(c)]||[])){ const b = Math.floor((ms/1000+st.win)/0.02); if (b>=0 && b<nb) cnt[b]++; } }
  const mx = Math.max(1, ...cnt); marks(g, ev, w, h-14, st.win); g.fillStyle = css("--fg");
  for (let b=0;b<nb;b++){ const x0 = xpix(-st.win+b*0.02, w, st.win), x1 = xpix(-st.win+(b+1)*0.02, w, st.win), bh = cnt[b]/mx*(h-30);
    g.fillRect(x0, h-16-bh, Math.max(1,x1-x0-1), bh); }
  g.fillStyle = css("--muted"); g.fillText(`all ${st.live.length} live sites, spikes per 20 ms (max ${mx})`, L, 10); axisT(g, w, h, st.win);
}
function drawOverview(){
  const st = DATA.sets[S];
  document.getElementById("ovInfo").innerHTML = `<b>${st.name}</b> &middot; averages over the scan's detections of col ${st.ref} (XML ${st.xml})`;
  let [g, w, h] = prep(document.getElementById("cLam"));
  const n = st.n_sites, ns = st.lam[0].length, win = 1.0; let rng = 0;
  for (const r of st.lam) for (const v of r) rng = Math.max(rng, Math.abs(v));
  const step = (h-24)/n, sc = step*1.6/(rng||1);
  for (let s=0;s<n;s++){ const y0 = 8+step*(s+0.5), c = st.sites[s];
    g.strokeStyle = c===st.ref ? "#e03131" : (st.skip.includes(c) ? css("--line") : css("--fg")); g.beginPath();
    for (let i=0;i<ns;i++){ const px = L+i/(ns-1)*(w-L-R), py = y0 - st.lam[s][i]*sc; i ? g.lineTo(px,py) : g.moveTo(px,py); } g.stroke();
    g.fillStyle = css("--muted"); g.fillText(`${s+1}: ${c}`, 4, y0+4); }
  g.fillStyle = css("--muted"); g.fillText(`delta-triggered average LFP (up = positive; largest deflection ${rng.toFixed(0)} uV)`, L, 10);
  axisT(g, w, h, win); g.strokeStyle = css("--acc"); const x = xpix(0,w,win); g.beginPath(); g.moveTo(x,0); g.lineTo(x,h-14); g.stroke();
  [g, w, h] = prep(document.getElementById("cPeth"));
  if (!st.mua){ g.fillStyle = css("--muted"); g.fillText("no MUA PETH for this set", L, 20); return; }
  const lag = st.mua.lag, step2 = (h-24)/n;
  for (let s=0;s<n;s++){ const y0 = 8+step2*s, r = st.mua.rate[s];
    g.fillStyle = css("--muted"); g.fillText(`${st.sites[s]} (${st.mua.mean_rate[s]} Hz)`, 4, y0+step2*0.7);
    if (!r) continue;
    for (let i=0;i<lag.length;i++){ const v = Math.log2(Math.max(1/8, Math.min(8, r[i])))/3; // -1..1
      g.fillStyle = v<0 ? `rgba(33,102,172,${-v})` : `rgba(178,24,43,${v})`;
      const x0 = xpix(lag[i]-0.005, w, win), x1 = xpix(lag[i]+0.005, w, win); g.fillRect(x0, y0, x1-x0+0.5, step2-1); } }
  g.fillStyle = css("--muted"); g.fillText("MUA rate / baseline (-1..-0.6 s), 30 min of NREM: blue = fewer spikes, red = more; blank = < 1 Hz", L, 10);
  axisT(g, w, h, win);
}
function draw(){ if (document.getElementById("evView").style.display !== "none") drawEvent(); else drawOverview(); }
function verdict(v){ const st = DATA.sets[S], ev = st.events[E]; V[st.name] = V[st.name] || {};
  V[st.name][ev.idx] = {v, note: document.getElementById("notes").value, t: ev.t, time: new Date().toISOString()}; save();
  if (E < st.events.length-1) E++; draw(); }
const sel = document.getElementById("setSel");
DATA.sets.forEach((s,i)=>{ const o = document.createElement("option"); o.value=i; o.textContent=s.name; sel.appendChild(o); });
sel.onchange = ()=>{ S=+sel.value; E=0; draw(); };
document.getElementById("prev").onclick = ()=>{ if (E>0) E--; draw(); };
document.getElementById("next").onclick = ()=>{ if (E<DATA.sets[S].events.length-1) E++; draw(); };
document.getElementById("gain").oninput = draw; document.getElementById("lp").onchange = draw;
document.querySelectorAll(".verd button").forEach(b=> b.onclick = ()=>verdict(+b.dataset.v));
document.getElementById("notes").onchange = ()=>{ const st = DATA.sets[S], ev = st.events[E]; if (V[st.name] && V[st.name][ev.idx]) { V[st.name][ev.idx].note = document.getElementById("notes").value; save(); } };
document.getElementById("tEv").onclick = ()=>{ document.getElementById("evView").style.display=""; document.getElementById("ovView").style.display="none"; document.getElementById("tEv").className="on"; document.getElementById("tOv").className=""; draw(); };
document.getElementById("tOv").onclick = ()=>{ document.getElementById("evView").style.display="none"; document.getElementById("ovView").style.display=""; document.getElementById("tOv").className="on"; document.getElementById("tEv").className=""; draw(); };
document.addEventListener("keydown", e=>{ if (e.target.tagName==="INPUT" && e.target.type==="text") return;
  if (e.key==="ArrowRight") document.getElementById("next").click(); else if (e.key==="ArrowLeft") document.getElementById("prev").click();
  else if ("123".includes(e.key)) verdict(+e.key); });
function dl(name, text, type){ const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text],{type})); a.download = name; a.click(); }
document.getElementById("exp").onclick = ()=>{
  const rows = [["set","animal","session","ref_col","event_idx","peak_s","amp_z","dur_ms","verdict","label","note","saved_at"]];
  for (const st of DATA.sets){ for (const ev of st.events){ const v = V[st.name] && V[st.name][ev.idx];
    rows.push([st.name, st.animal, st.session, st.ref, ev.idx, ev.t, ev.amp, ev.dur_ms, v?v.v:"", v?["","looks like it","does not","unsure"][v.v]:"", v&&v.note?v.note.replace(/[,\n]/g," "):"", v?v.time:""]); } }
  const stamp = new Date().toISOString().slice(0,16).replace(/[:T]/g,"");
  const q = v => { const s = String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  dl(`delta_review_${DATA.tag}_${stamp}.csv`, rows.map(r=>r.map(q).join(",")).join("\n"), "text/csv");
  dl(`delta_review_${DATA.tag}_${stamp}.json`, JSON.stringify({tag: DATA.tag, built: DATA.built, verdicts: V}, null, 1), "application/json"); };
window.onresize = draw; draw();
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", action="append", required=True, help="ANIMAL:SESSION:REF_COL")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--lfp-root", required=True)
    ap.add_argument("--raw-root", required=True)
    ap.add_argument("--states-root", required=True)
    ap.add_argument("--scan-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    sets = []
    for s in a.set:
        animal, session, ref = s.split(":")
        sets.append(build_set(animal, session, int(ref), a.n, a, rng))
        print(f"{sets[-1]['name']}: {len(sets[-1]['events'])} events", flush=True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = out.name
    data = dict(tag=tag, built=dt.datetime.now().isoformat(timespec="seconds"), sets=sets, git=dd._git())
    (out / "index.html").write_text(PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":"))), encoding="utf-8")
    (out / "README.md").write_text(
        f"Delta-wave review page built {data['built']} by ephys/delta_review_gui.py (git {data['git']}).\n"
        f"Sets: {', '.join(s['name'] for s in sets)}; {a.n} events each, drawn from the amplitude quartiles (seed {a.seed}).\n"
        "Open index.html; keys 1 / 2 / 3 = looks like a delta wave / does not / unsure; Export CSV + JSON -> put the files in "
        "ephys/configs/delta_review_2026c/.\n", encoding="utf-8")
    print("->", out / "index.html")


if __name__ == "__main__":
    main()
