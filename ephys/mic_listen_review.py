r"""Blind listening page for the in-house microphone pilot (plan implementation_plan/2026-10-07-sleep-internal-schedule.md
section 4 D; the user validates, the agent never judges sounds or images).

For every event of the pilot's listening sample (8 per candidate class) and 8 control moments (the same animals 120 s
before a wake, i.e. asleep): a 30-s window [t - 20, t + 10] s around t = the animal's head-IMU movement onset (controls:
t - 120 s), on the field-PC clock, with
  - the own-house mic: an audible clip (resampled to 48 kHz), a time-expanded clip of [t - 3, t] played 8x slower
    (ultrasonic rat calls at 22 / 50 kHz become 2.7 / 6 kHz), a spectrogram 0-100 kHz;
  - the other house's mic: a spectrogram;
  - the outdoor CH01 camera audio (stream timestamps): an audible clip and a spectrogram 0-8 kHz.
The candidate class and the cue values are hidden until the user has answered; the answers are kept in the browser and
exported as CSV / JSON (keep them in ephys/configs/mic_listen_review_2026c/).

Mic timing: file start from the name, samples spread over the name span as in ephys/mic_band_levels.py (the extract log
gives rate_eff / t_first per file); the per-file timing error bound is shown on each card.

Usage: python ephys/mic_listen_review.py --pilot-run <mic_wake_pilot run> [--raw F:/3rd_rat] [--audio-log <extract_log_*.csv>]
"""
from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from mic_band_levels import FFMPEG, NAME_RE, parse_name, wav_info  # noqa: E402

PRE, POST, SLOW_S, SLOW_X = 20, 10, 3, 8


def find_file(raw: Path, stream: str, t: pd.Timestamp, ext: str) -> Path | None:
    for day in {t.normalize(), (t - pd.Timedelta(hours=1)).normalize()}:
        for f in sorted((raw / f"{day:%Y-%m-%d}" / stream).glob(f"{stream}_*.{ext}")):
            if not NAME_RE.search(f.name):
                continue
            _, s, e = parse_name(f)
            if e is not None and s <= t - pd.Timedelta(seconds=PRE) and t + pd.Timedelta(seconds=POST) <= e:
                return f
    return None


def mic_segment(f: Path, t: pd.Timestamp, log: pd.DataFrame):
    mic, s, e = parse_name(f)
    rate, n, off = wav_info(f)
    row = log[log.file == f.name]
    rate_eff = float(row.rate_eff.iloc[0]) if len(row) else n / (e - s).total_seconds()
    t_first = float(row.t_first_s.iloc[0]) if len(row) and np.isfinite(row.t_first_s.iloc[0]) else 0.0
    err = row.timing_err_s.iloc[0] if len(row) and "timing_err_s" in row else np.nan
    x = np.memmap(f, dtype="<i2", mode="r", offset=off, shape=(n,))
    i0 = int(round(((t - s).total_seconds() - PRE - t_first) * rate_eff))
    i1 = i0 + int(round((PRE + POST) * rate_eff))
    if i0 < 0 or i1 > n:
        return None
    return np.asarray(x[i0:i1], dtype=np.float32), rate, rate_eff, err


def write_wav(path: Path, x: np.ndarray, rate: int) -> None:
    pcm = np.clip(x / max(1e-9, np.max(np.abs(x))) * 0.9 * 32767, -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(int(rate))
        w.writeframes(pcm.tobytes())


def spectro(path: Path, x: np.ndarray, rate: float, fmax: float, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.signal import spectrogram
    nper = 4096 if rate > 100000 else 512
    f, tt, S = spectrogram(x - x.mean(), fs=rate, nperseg=nper, noverlap=nper // 2)
    keep = f <= fmax
    fig = plt.figure(figsize=(9, 2.6))
    ax = fig.add_axes(AX)                           # fixed geometry: the page's moving bar maps time to x with AX
    ax.pcolormesh(tt - PRE, f[keep] / 1000, 10 * np.log10(S[keep] + 1e-12), shading="auto", cmap="magma")
    ax.set_xlim(-PRE, POST)
    ax.axvline(0, color="cyan", lw=1.2)
    ax.set_ylabel("kHz")
    ax.set_xlabel("s from the movement onset (cyan)")
    ax.set_title(title, fontsize=8)
    fig.savefig(path, dpi=90)
    plt.close(fig)


AX = (0.07, 0.2, 0.91, 0.68)                        # left, bottom, width, height of every spectrogram's axes
JS_SYNC = """
const AXL = %AXL%, AXW = %AXW%, PRE = %PRE%, POST = %POST%;
function setBars(card, x) {
  const f = Math.min(Math.max((x + PRE) / (PRE + POST), 0), 1);
  card.querySelectorAll('.bar').forEach(b => { b.style.left = ((AXL + f * AXW) * 100) + '%'; });
}
document.querySelectorAll('.sync').forEach(el => {
  const card = el.closest('.card'), t0 = parseFloat(el.dataset.t0), rate = parseFloat(el.dataset.rate);
  let raf = null;
  const tick = () => { setBars(card, t0 + el.currentTime * rate); if (!el.paused && !el.ended) raf = requestAnimationFrame(tick); };
  el.addEventListener('play', () => { cancelAnimationFrame(raf); tick(); });
  el.addEventListener('seeked', tick);
  el.addEventListener('timeupdate', () => { if (el.paused) tick(); });
});
"""


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
    from output_paths import run_dir
    from scipy.signal import resample_poly
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pilot-run", required=True)
    ap.add_argument("--raw", default="F:/3rd_rat")
    ap.add_argument("--audio-log", default=None)
    ap.add_argument("--n-controls", type=int, default=8)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
    pr, raw = Path(a.pilot_run), Path(a.raw)
    logs = sorted(Path("D:/Field2026_analysis_out/2026c/audio_levels").glob("extract_log_*.csv")) if a.audio_log is None else [Path(a.audio_log)]
    log = pd.read_csv(logs[-1])
    S = pd.read_csv(pr / "d3_listening_sample.csv", parse_dates=["move_onset"])
    E = pd.read_csv(pr / "d3_wake_events.csv", parse_dates=["move_onset"])
    rng = np.random.default_rng(11)
    C = E.drop(S.index.intersection(E.index), errors="ignore").sample(a.n_controls, random_state=11).copy()
    C["candidate_class"] = "control (asleep, 120 s before a wake)"
    C["move_onset"] = C.move_onset - pd.Timedelta(seconds=120)
    ev = pd.concat([S.assign(kind="event"), C.assign(kind="control")], ignore_index=True)
    ev = ev.iloc[rng.permutation(len(ev))].reset_index(drop=True)
    ev["id"] = [f"L{i + 1:02d}" for i in range(len(ev))]
    out = run_dir("mic_listen_review", "2026c")
    (out / "media").mkdir(exist_ok=True)
    cards, meta = [], []
    for r in ev.itertuples():
        t = pd.Timestamp(r.move_onset)
        other = "MIC02" if r.own_mic == "MIC01" else "MIC01"
        info = {"id": r.id, "t_onset": str(t), "animal": r.animal, "house": r.house, "own_mic": r.own_mic,
                "kind": r.kind, "candidate_class": r.candidate_class, "housemates_first": "" if pd.isna(r.housemates_first) else r.housemates_first,
                **{k: (None if pd.isna(getattr(r, k)) else round(float(getattr(r, k)), 1)) for k in
                   ("own_b0_jump_db", "own_b1_jump_db", "own_b2_jump_db", "other_b0_jump_db", "other_b1_jump_db", "other_b2_jump_db", "outdoor_jump_db")}}
        media, notes = {}, []
        for role, mic in (("own", r.own_mic), ("other", other)):
            f = find_file(raw / "", mic, t, "wav")
            seg = mic_segment(f, t, log) if f else None
            if seg is None:
                notes.append(f"{role} mic {mic}: no covering file")
                continue
            x, rate, rate_eff, err = seg
            spectro(out / "media" / f"{r.id}_{role}.png", x, rate_eff, 100000, f"{r.id} {role}-house mic {mic} ({'house_2' if mic == 'MIC01' else 'house_1'}) 0-100 kHz")
            media[f"{role}_png"] = f"media/{r.id}_{role}.png"
            if role == "own":
                write_wav(out / "media" / f"{r.id}_own.wav", resample_poly(x, 48000, int(rate)), 48000)
                k0 = int((PRE - SLOW_S) * rate_eff)
                write_wav(out / "media" / f"{r.id}_own_slow.wav", x[k0:int(PRE * rate_eff)], int(rate) // SLOW_X)
                media["own_wav"], media["own_slow_wav"] = f"media/{r.id}_own.wav", f"media/{r.id}_own_slow.wav"
                info["own_timing_err_s"] = None if pd.isna(err) else float(err)
        fc = find_file(raw, "CH01", t, "mp4")
        if fc is not None:
            _, s, _ = parse_name(fc)
            off = (t - s).total_seconds() - PRE
            wav = out / "media" / f"{r.id}_outdoor.wav"
            subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{off:.3f}", "-t", str(PRE + POST), "-i", str(fc), "-vn", "-map", "0:a:0",
                            "-af", "aresample=async=1", "-ac", "1", "-ar", "16000", str(wav)], check=False)
            if wav.exists() and wav.stat().st_size > 1000:
                with wave.open(str(wav)) as w:
                    y = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32)
                spectro(out / "media" / f"{r.id}_outdoor.png", y, 16000, 8000, f"{r.id} outdoor CH01 camera audio 0-8 kHz")
                media["outdoor_wav"], media["outdoor_png"] = f"media/{r.id}_outdoor.wav", f"media/{r.id}_outdoor.png"
        else:
            notes.append("outdoor CH01: no covering file")
        meta.append({**info, **media, "notes": "; ".join(notes)})
        print(r.id, r.kind, "media:", sorted(media), notes, flush=True)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(3) as ex:                    # 2x2 house video per card (both houses, inside + outside)
        for m, stt in zip(meta, ex.map(lambda m: mosaic(out, m, raw), meta)):
            if (out / "media" / f"{m['id']}_mosaic.mp4").exists():
                m["mosaic_mp4"] = f"media/{m['id']}_mosaic.mp4"
            print(m["id"], "video", stt[:120], flush=True)
    (out / "events.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    opts = ["outside sound (weather / machine / people / animal outside)", "housemate noise or movement",
            "this rat's own noise", "nothing audible", "can't tell"]
    for m in meta:
        vid = (f'<video class="sync" data-t0="{-PRE}" data-rate="1" controls preload="none" width="960" src="{m["mosaic_mp4"]}"></video>'
               '<div><small>Both houses, inside and outside (the focal rat\'s house in yellow); sound = the focal rat\'s house mic; '
               'countdown to the movement onset, cyan flash at 0. The green bar on the spectrograms follows whatever is playing.</small></div>'
               if "mosaic_mp4" in m else "<div><small>no house video</small></div>")
        aud = "".join(f'<div class="a"><b>{lab}</b><br><audio class="sync" data-t0="{t0}" data-rate="{rate}" controls preload="none" src="{m[k]}"></audio></div>'
                      for k, lab, t0, rate in (("own_wav", "own-house mic (audible)", -PRE, 1),
                                               ("own_slow_wav", f"own mic, last {SLOW_S} s x{SLOW_X} slower (ultrasound)", -SLOW_S, 1 / SLOW_X),
                                               ("outdoor_wav", "outdoor CH01", -PRE, 1)) if k in m)
        img = "".join(f'<div class="sw"><img src="{m[k]}"><div class="bar"></div></div>' for k in ("own_png", "other_png", "outdoor_png") if k in m)
        aud = vid + aud
        radios = "".join(f'<label><input type="radio" name="v_{m["id"]}" value="{html.escape(o)}"> {html.escape(o)}</label><br>' for o in opts)
        cards.append(f'''<div class="card" id="{m["id"]}"><h3>{m["id"]} &nbsp; <small>{m["t_onset"]} · {m["animal"]} · {m["house"]} · own mic {m["own_mic"]}
 · timing error bound {m.get("own_timing_err_s", "?")} s</small></h3>{aud}<div>{img}</div>
<p><b>What happened just before the movement onset (cyan line)?</b><br>{radios}
<label><input type="checkbox" name="usv_{m["id"]}"> rat ultrasonic call before the onset</label><br>
<textarea name="n_{m["id"]}" rows="2" cols="80" placeholder="note"></textarea><br>
<button onclick="reveal('{m["id"]}')">save + reveal</button><span class="rev" id="rev_{m["id"]}"></span></p></div>''')
    page = f'''<!doctype html><html><head><meta charset="utf-8"><title>Mic listening review</title><style>
body{{font-family:sans-serif;margin:16px;max-width:1100px}} .card{{border:1px solid #999;padding:8px;margin:12px 0}} img{{max-width:100%;display:block}}
.a{{display:inline-block;margin-right:16px}} .rev{{color:#a33;margin-left:12px}}
.sw{{position:relative;display:block}} .bar{{position:absolute;top:0;bottom:0;width:3px;background:#3f3;left:{AX[0] * 100}%;pointer-events:none}}</style></head><body>
<h2>In-house microphone listening review (blind) — cohort 2026c</h2>
<p>{len(meta)} cards: wakes from NREM ({(ev.kind == "event").sum()}) and controls ({(ev.kind == "control").sum()}, the rat asleep), shuffled.
Listen to the own-house mic (and the slowed clip for ultrasonic calls), look at the spectrograms (own house, other house, outdoor),
then answer. The pilot's class appears only after you save. Answers stay in this browser; use <b>Export</b> at the end and save the
files to <code>ephys/configs/mic_listen_review_2026c/</code>.</p>
{"".join(cards)}
<p><button onclick="exp()">Export CSV + JSON</button></p>
<script>
const META = {json.dumps({m["id"]: {k: m[k] for k in m if k not in ("own_png", "other_png", "outdoor_png", "own_wav", "own_slow_wav", "outdoor_wav")} for m in meta}, default=str)};
const KEY = "mic_listen_review_2026c";
function load(){{try{{return JSON.parse(localStorage.getItem(KEY)||"{{}}")}}catch(e){{return {{}}}}}}
function save(s){{try{{localStorage.setItem(KEY, JSON.stringify(s))}}catch(e){{}}}}
function val(id){{const r=document.querySelector('input[name="v_'+id+'"]:checked');return {{verdict:r?r.value:"",usv:document.querySelector('input[name="usv_'+id+'"]').checked,
 note:document.querySelector('textarea[name="n_'+id+'"]').value}}}}
function reveal(id){{const s=load();const v=val(id);if(!v.verdict){{alert("choose an answer first");return}}
 s[id]=Object.assign(s[id]||{{}},v,{{saved_at:new Date().toISOString()}});if(!s[id].verdict_blind){{s[id].verdict_blind=v.verdict}}save(s);
 const m=META[id];document.getElementById("rev_"+id).textContent="pilot class: "+m.candidate_class+" | housemates first: "+(m.housemates_first||"-")+
 " | own jumps b0/b1/b2: "+m.own_b0_jump_db+"/"+m.own_b1_jump_db+"/"+m.own_b2_jump_db+" dB | other b1: "+m.other_b1_jump_db+" | outdoor: "+m.outdoor_jump_db+" dB";}}
function exp(){{const s=load();const rows=[["id","verdict_blind","verdict_final","usv","note","saved_at"].join(",")];
 for(const id in META){{const v=s[id]||{{}};rows.push([id,JSON.stringify(v.verdict_blind||""),JSON.stringify(v.verdict||""),v.usv?1:0,JSON.stringify(v.note||""),v.saved_at||""].join(","))}}
 for(const [n,c,t] of [["mic_listen_review_answers.csv",rows.join("\\n"),"text/csv"],["mic_listen_review_answers.json",JSON.stringify(s,null,1),"application/json"]]){{
 const b=new Blob([c],{{type:t}});const u=URL.createObjectURL(b);const l=document.createElement("a");l.href=u;l.download=n;l.click();}}}}
(function(){{const s=load();for(const id in s){{const v=s[id];const r=document.querySelector('input[name="v_'+id+'"][value="'+(v.verdict||"").replace(/"/g,'\\\\"')+'"]');if(r)r.checked=true;
 const c=document.querySelector('input[name="usv_'+id+'"]');if(c)c.checked=!!v.usv;const t=document.querySelector('textarea[name="n_'+id+'"]');if(t)t.value=v.note||"";}}}})();
</script><script>{JS_SYNC.replace("%AXL%", str(AX[0])).replace("%AXW%", str(AX[2])).replace("%PRE%", str(PRE)).replace("%POST%", str(POST))}</script></body></html>'''
    (out / "index.html").write_text(page, encoding="utf-8")
    print("written", out / "index.html")


HOUSE_CAMS = [("CH08", "house_1 inside (CH08)"), ("CH07", "house_2 inside (CH07)"),
              ("CH05", "house_1 outside (CH05)"), ("CH06", "house_2 outside (CH06)")]   # CLAUDE.md camera map
FONT = "C\\:/Windows/Fonts/arial.ttf"


def mosaic(run: Path, m: dict, raw: Path) -> str:
    """2x2 video of both houses (inside CH08 / CH07, outside CH05 / CH06) over [t - 20, t + 10] s, 10 fps, the own-house
    mic as the sound, an onset countdown and a cyan frame flash at the movement onset. Returns a status string."""
    t = pd.Timestamp(m["t_onset"])
    dst = run / "media" / f"{m['id']}_mosaic.mp4"
    if dst.exists():
        return "exists"
    cmd, filt = [FFMPEG, "-v", "error", "-y"], []
    for k, (cam, label) in enumerate(HOUSE_CAMS):
        f = find_file(raw, cam, t, "mp4")
        focal = " - FOCAL RAT HOUSE" if label.startswith(m["house"]) else ""
        if f is None:
            cmd += ["-f", "lavfi", "-t", str(PRE + POST), "-i", "color=c=black:s=640x480:r=10"]
            label += " - no file"
        else:
            _, s, _ = parse_name(f)
            cmd += ["-ss", f"{(t - s).total_seconds() - PRE:.3f}", "-t", str(PRE + POST), "-i", str(f)]
        filt.append(f"[{k}:v]fps=10,scale=640:480,setsar=1,drawtext=fontfile={FONT}:text='{label}{focal}':x=8:y=8:fontsize=20:"
                    f"fontcolor={'yellow' if focal else 'white'}:box=1:boxcolor=black@0.6[v{k}]")
    wav = run / "media" / f"{m['id']}_own.wav"
    has_audio = wav.exists()
    if has_audio:
        cmd += ["-i", str(wav)]
    filt.append("[v0][v1][v2][v3]xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0[mm]")
    filt.append(f"[mm]drawtext=fontfile={FONT}:text='%{{eif\\:t-{PRE}\\:d}} s from the movement onset':x=(w-tw)/2:y=h-44:fontsize=28:"
                f"fontcolor=white:box=1:boxcolor=black@0.6,drawbox=x=0:y=0:w=iw:h=ih:color=cyan@0.9:t=14:enable='between(t,{PRE},{PRE + 1})'[v]")
    cmd += ["-filter_complex", ";".join(filt), "-map", "[v]"]
    if has_audio:
        cmd += ["-map", "4:a", "-c:a", "aac", "-b:a", "96k"]
    cmd += ["-t", str(PRE + POST), "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return "ok" if r.returncode == 0 and dst.exists() else f"error: {r.stderr[-300:]}"


def add_video(run: Path, raw: Path, only: list[str] | None, workers: int) -> None:
    from concurrent.futures import ThreadPoolExecutor
    meta = json.loads((run / "events.json").read_text(encoding="utf-8"))
    todo = [m for m in meta if not only or m["id"] in only]
    with ThreadPoolExecutor(workers) as ex:
        for m, st in zip(todo, ex.map(lambda m: mosaic(run, m, raw), todo)):
            print(m["id"], st, flush=True)
    page = (run / "index.html").read_text(encoding="utf-8")
    for m in meta:
        v = run / "media" / f"{m['id']}_mosaic.mp4"
        tag = (f'<video controls preload="none" width="960" src="media/{m["id"]}_mosaic.mp4"></video>'
               f'<div><small>Both houses, inside and outside; sound = the focal rat\'s house mic; countdown to the movement onset '
               f'(cyan flash).</small></div>')
        anchor = f'<div class="card" id="{m["id"]}"><h3>'
        if v.exists() and anchor in page and f'{m["id"]}_mosaic.mp4' not in page:
            i = page.index(anchor)
            j = page.index("</h3>", i) + len("</h3>")
            page = page[:j] + tag + page[j:]
    (run / "index.html").write_text(page, encoding="utf-8")
    print("page updated", run / "index.html")


IMU_ROOT = Path("D:/3rd_rat_spikes/analysis/imu")


def imu_window(an: str, t: pd.Timestamp) -> np.ndarray | None:
    """VeDBA (m/s^2) of `an` at 50 Hz over [t - PRE, t + POST] on the field-PC clock (NaN where invalid), from the make_imu
    session that covers t; None if no session covers it."""
    for jf in sorted((IMU_ROOT / an).glob("*.imu.json")):
        j = json.loads(jf.read_text())
        s0 = pd.Timestamp(j["start_local"])
        if not (s0 <= t - pd.Timedelta(seconds=PRE) and t + pd.Timedelta(seconds=POST) <= s0 + pd.Timedelta(seconds=j["duration_s"])):
            continue
        with np.load(jf.with_name(jf.name.replace(".imu.json", ".imu.npz"))) as z:
            if "t_pc_ms" not in z.files:
                return None
            tp, v = z["t_pc_ms"], z["vedba_ms2"].astype(np.float64)
            bad = z["unreliable"] | z["frozen"] | z["invalid"]
        rel = (s0.normalize() + pd.to_timedelta(tp, unit="ms") - t).total_seconds().to_numpy()
        grid = np.arange(-PRE, POST + 1e-9, 0.02)
        k = np.clip(np.searchsorted(rel, grid), 1, len(rel) - 1)
        k = np.where(np.abs(rel[k - 1] - grid) < np.abs(rel[k] - grid), k - 1, k)
        out = np.where(bad[k] | (np.abs(rel[k] - grid) > 0.03), np.nan, v[k])
        return out
    return None


def imu_png(path: Path, m: dict, traces: list[tuple[str, str, np.ndarray | None]]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(traces)
    hgt = 0.6 + 0.42 * n
    fig = plt.figure(figsize=(9, hgt))
    ax = fig.add_axes((AX[0], 0.45 / hgt, AX[2], 1 - 0.75 / hgt))    # same horizontal geometry as the spectrograms
    grid = np.arange(-PRE, POST + 1e-9, 0.02)
    for i, (an, where, v) in enumerate(traces):
        y0 = n - 1 - i
        if v is not None:
            y = np.clip((np.log10(v + 0.01) + 2) / 4, 0, 1) * 0.9          # log10 VeDBA -2..+2 -> 0..0.9 of the row
            ax.plot(grid, y0 + y, lw=0.7, color="crimson" if an == m["animal"] else "k")
        ax.text(-PRE - 0.3, y0 + 0.35, f"{an} {where}", ha="right", va="center", fontsize=7,
                color="crimson" if an == m["animal"] else "k")
    ax.axvline(0, color="cyan", lw=1.2)
    ax.set_xlim(-PRE, POST)
    ax.set_ylim(0, n)
    ax.set_yticks([])
    ax.set_xlabel("s from the movement onset (cyan); head VeDBA per rat, log scale (0.01-100 m/s^2 per row)", fontsize=7)
    ax.set_title(f"{m['id']}: head IMU of every rat (focal rat in red); field-PC clock via the logger time chain", fontsize=8)
    fig.savefig(path, dpi=90)
    plt.close(fig)


def add_imu(run: Path) -> None:
    """Who moved? One IMU panel per card, inside a <details> block placed after the spectrograms (opened = shown;
    the page stores whether it was opened before the first answer)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
    from mic_wake_pilot import ANIMALS, ROOT, load_zone
    meta = json.loads((run / "events.json").read_text(encoding="utf-8"))
    rois = {r["name"]: r for r in json.load(open(ROOT / "wiser/configs/wiser_rois.json"))["rois"] if r["name"] in ("house_1", "house_2")}
    days = sorted({pd.Timestamp(m["t_onset"]).strftime("%Y%m%d") for m in meta})
    zone = {an: load_zone(an, days, rois) for an in ANIMALS}
    page = (run / "index.html").read_text(encoding="utf-8")
    for m in meta:
        t = pd.Timestamp(m["t_onset"])
        rows = []
        for an in ANIMALS:
            z = zone[an]
            w = z.get(t.floor("s"), "unknown") if len(z) else "unknown"
            v = imu_window(an, t)
            if v is None and w == "unknown":
                continue
            rows.append((an, f"({w})" + ("" if v is not None else " no IMU"), v))
        rows.sort(key=lambda r: (r[1] != f"({m['house']})", r[0] != m["animal"], r[0]))   # focal house first, focal rat on top
        png = run / "media" / f"{m['id']}_imu.png"
        imu_png(png, m, rows)
        m["imu_png"] = f"media/{m['id']}_imu.png"
        block = (f'<details class="imu" data-id="{m["id"]}"><summary><b>Head IMU of every rat — who moved?</b> '
                 f'(opens the movement traces; the green bar follows playback)</summary>'
                 f'<div class="sw"><img src="{m["imu_png"]}"><div class="bar"></div></div></details>')
        anchor = f'<div class="card" id="{m["id"]}">'
        if anchor in page and f'{m["id"]}_imu.png' not in page:
            i = page.index(anchor)
            j = page.index("<p><b>What happened", i)
            page = page[:j] + block + page[j:]
        print(m["id"], [(r[0], r[1]) for r in rows], flush=True)
    js = """<script>
document.querySelectorAll('details.imu').forEach(d => d.addEventListener('toggle', () => {
  if (!d.open) return; const id = d.dataset.id; const s = load(); s[id] = s[id] || {};
  if (s[id].imu_opened_before_answer === undefined) s[id].imu_opened_before_answer = !s[id].verdict_blind;
  save(s); }));
</script>"""
    if "details.imu" not in page:
        page = page.replace("</body></html>", js + "</body></html>")
        page = page.replace('rows=[["id","verdict_blind","verdict_final","usv","note","saved_at"].join(",")]',
                            'rows=[["id","verdict_blind","verdict_final","usv","note","saved_at","imu_opened_before_answer"].join(",")]')
        page = page.replace('JSON.stringify(v.note||""),v.saved_at||""].join(",")',
                            'JSON.stringify(v.note||""),v.saved_at||"",v.imu_opened_before_answer===undefined?"":(v.imu_opened_before_answer?1:0)].join(",")')
    (run / "events.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    (run / "index.html").write_text(page, encoding="utf-8")
    print("page updated", run / "index.html")


if __name__ == "__main__":
    if "--add-imu" in sys.argv:
        api = argparse.ArgumentParser()
        api.add_argument("--add-imu", required=True, help="an existing mic_listen_review run folder")
        add_imu(Path(api.parse_args().add_imu))
    elif "--add-video" in sys.argv:
        apv = argparse.ArgumentParser()
        apv.add_argument("--add-video", required=True, help="an existing mic_listen_review run folder")
        apv.add_argument("--raw", default="F:/3rd_rat")
        apv.add_argument("--only", nargs="*")
        apv.add_argument("--workers", type=int, default=3)
        av = apv.parse_args()
        add_video(Path(av.add_video), Path(av.raw), av.only, av.workers)
    else:
        main()
