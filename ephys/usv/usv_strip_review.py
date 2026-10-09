r"""USV review by SHAPE: long spectrogram strips, labelled per strip (the user, 2026-10-09: "no need to listen, USVs are
judged by their shape and whether they come in bouts; small thumbnails are too hard to see; work out a sensible
frequency range and timescale, maybe 10 s to 1 min", with an Audacity example of MIC01 09-05 03:00, 13-100 kHz, 55 s).

Per WAV window: consecutive strips of STRIP_S (30 s), 15-100 kHz.
- Spectrogram: nperseg 1024 (384 kHz: 375-Hz bins, hop 256 = 0.67 ms) / 512 (250 kHz: 488 Hz, hop 128 = 0.5 ms).
- Whitened per frequency: dB minus the median of that frequency over the whole window, so the mics' steady tones vanish.
- Shown 0-25 dB above the background.
- Compressed in time by the MAXIMUM over each pixel's span (a 20-ms call stays visible): 3600 px per strip; the page
  shows it at 1800 px, a click opens the full image.
- Under each strip, a tick row with the whitened detector's tonal >= 30-ms candidates
  (ephys/usv/usv_whiten_detect.py; drawn outside the image so they do not cover shapes).
- Per strip the user answers only presence: USV contours none / a few / many (+ optional 22-kHz / 50-kHz band). The
  detector ticks are hidden by default (a button shows them), so the labels stay independent of the detector (the user,
  2026-10-09: "what matters is yes or no; fine detection is the next step"). No audio. Export -> ephys/configs/usv_review_2026c/.

    python ephys/usv/usv_strip_review.py --wav <a.wav> [...] [--start-s 0 --dur-s 600] --cand-dir <usv_whiten_detect out>
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mic_band_levels import parse_name, wav_info  # noqa: E402

FMIN, FMAX, STRIP_S, PX, VMAX = 15000.0, 100000.0, 30.0, 3600, 25.0


def whitened(x: np.ndarray, rate: int):
    nper = 1024 if rate > 300000 else 512
    f, t, S = signal.spectrogram(x - x.mean(), fs=rate, nperseg=nper, noverlap=nper * 3 // 4, mode="psd")
    k = (f >= FMIN) & (f <= FMAX)
    L = 10 * np.log10(S[k] + 1e-20)
    return f[k], t, L - np.median(L, axis=1, keepdims=True)


def maxpool(E: np.ndarray, n: int) -> np.ndarray:
    edges = np.linspace(0, E.shape[1], n + 1).astype(int)
    return np.maximum.reduceat(E, edges[:-1], axis=1)


def strip_png(path: Path, E: np.ndarray, f: np.ndarray) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(PX / 100, 3.2), dpi=100)
    ax = fig.add_axes((0.012, 0.08, 0.986, 0.9))
    ax.imshow(np.clip(E, 0, VMAX), origin="lower", aspect="auto", cmap="inferno", vmin=0, vmax=VMAX,
              extent=(0, STRIP_S, f[0] / 1000, f[-1] / 1000))
    ax.set_yticks([20, 30, 40, 50, 60, 80, 100])
    ax.set_xticks(np.arange(0, STRIP_S + 0.1, 5))
    ax.tick_params(labelsize=7, length=2, pad=1)
    for y in (20, 30, 40, 50, 60, 80):
        ax.axhline(y, color="w", lw=0.3, alpha=0.3)
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
    from output_paths import run_dir
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wav", nargs="+", required=True)
    ap.add_argument("--start-s", type=float, default=0.0)
    ap.add_argument("--dur-s", type=float, default=600.0)
    ap.add_argument("--cand-dir", default=None)
    a = ap.parse_args()
    out = run_dir("usv_strip_review", "2026c")
    (out / "media").mkdir(exist_ok=True)
    meta, cards = [], []
    for w in a.wav:
        p = Path(w)
        mic, s0, _ = parse_name(p)
        rate, n, off = wav_info(p)
        mm = np.memmap(p, dtype="<i2", mode="r", offset=off, shape=(n,))
        t1 = min(n / rate, a.start_s + a.dur_s)
        x = np.asarray(mm[int(a.start_s * rate):int(t1 * rate)], dtype=np.float32)
        f, t, E = whitened(x, rate)
        C = pd.DataFrame()
        if a.cand_dir and (Path(a.cand_dir) / f"{p.stem}.csv").exists():
            try:
                C = pd.read_csv(Path(a.cand_dir) / f"{p.stem}.csv")
                C = C[C.tonal & (C.dur_s >= 0.03)]
            except pd.errors.EmptyDataError:
                C = pd.DataFrame()
        dt = t[1] - t[0]
        for j, ss in enumerate(np.arange(0, t1 - a.start_s - 1, STRIP_S)):
            k = (t >= ss) & (t < ss + STRIP_S)
            if k.sum() < 100:
                continue
            Es = maxpool(E[:, k], PX)
            sid = f"{p.stem}_{int(a.start_s + ss):04d}"
            strip_png(out / "media" / f"{sid}.png", Es, f)
            ticks = []
            if len(C):
                cc = C[(C.begin_s >= a.start_s + ss) & (C.begin_s < a.start_s + ss + STRIP_S)]
                ticks = [((r.begin_s - a.start_s - ss) / STRIP_S, max(r.dur_s / STRIP_S, 0.002), r.peak_kHz) for r in cc.itertuples()]
            tstart = s0 + pd.Timedelta(seconds=float(a.start_s + ss))
            meta.append({"id": sid, "mic": mic, "file": p.name, "offset_s": float(a.start_s + ss), "t_start": str(tstart),
                         "candidates": len(ticks)})
            tk = "".join(f'<div class="tk" style="left:{1.2 + 98.6 * x0:.2f}%;width:{max(0.15, 98.6 * w_):.2f}%;'
                         f'background:{"#e33" if pk < 32 else "#36f"}" title="{pk:.0f} kHz"></div>' for x0, w_, pk in ticks)
            q1 = " ".join(f'<label><input type="radio" name="u_{sid}" value="{v}"> {v}</label>'
                          for v in ("none", "a few", "many"))
            q2 = " ".join(f'<label><input type="checkbox" name="b_{sid}" value="{v}"> {v}</label>' for v in ("22-kHz band", "50-kHz band"))
            cards.append(f'<div class="s" id="{sid}"><div class="h">{html.escape(mic)} {tstart:%m-%d %H:%M:%S} '
                         f'(+{a.start_s + ss:.0f} s in {html.escape(p.name)}) · {len(ticks)} detector ticks</div>'
                         f'<a href="media/{sid}.png" target="_blank"><img loading="lazy" src="media/{sid}.png"></a>'
                         f'<div class="tr">{tk}</div><div class="q"><b>USV present?</b> {q1} &nbsp; {q2}</div></div>')
        print(p.name, "strips so far", len(meta), flush=True)
    (out / "strips.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    page = f'''<!doctype html><html><head><meta charset="utf-8"><title>USV strip review</title><style>
body{{font-family:sans-serif;margin:12px;max-width:1860px}} .s{{margin:10px 0 18px 0;border-bottom:1px solid #bbb;padding-bottom:6px}}
.h{{font-size:13px;font-weight:bold;margin:2px 0}} img{{width:1800px;display:block}} .q{{font-size:13px;margin-top:3px}}
body:not(.ticks) .tr{{display:none}} .tr{{position:relative;width:1800px;height:8px;background:#eee}} .tk{{position:absolute;top:0;height:8px}}
</style></head><body><h2>USV review by shape — 30-s spectrogram strips, 15-100 kHz (cohort 2026c)</h2>
<p>{len(meta)} strips from {len(a.wav)} recording windows, in time order. Each frequency has its own background removed (the mics' steady
electronic tones vanish); colour = 0-25 dB above that background; time compressed by the maximum, so short calls stay visible.
Click a strip to open it full size. The thin row under each strip shows the automatic detector's candidates (red < 32 kHz, blue >= 32 kHz).
Answer per strip; answers stay in this browser; <b>Export</b> at the end and put the files in <code>ephys/configs/usv_review_2026c/</code>.</p>
<p><b>Only question: are there USV contours in this strip (none / a few / many)?</b> The detector ticks are hidden so that your
answers stay independent of the detector; <button onclick="document.body.classList.toggle('ticks')">show / hide detector ticks</button>
(only after labelling, if curious).</p>{"".join(cards)}<p><button onclick="exp()">Export JSON + CSV</button></p>
<script>
const KEY="usv_strip_review_{out.name}";
function st(){{const s={{}};document.querySelectorAll('.s').forEach(c=>{{const id=c.id;const u=c.querySelector('input[name="u_'+id+'"]:checked');
 const d=c.querySelector('input[name="d_'+id+'"]:checked');s[id]={{usv:u?u.value:"",bands:[...c.querySelectorAll('input[name="b_'+id+'"]:checked')].map(x=>x.value),detector:d?d.value:""}}}});return s}}
document.addEventListener('change',()=>{{try{{localStorage.setItem(KEY,JSON.stringify(st()))}}catch(e){{}}}});
(function(){{let s={{}};try{{s=JSON.parse(localStorage.getItem(KEY)||"{{}}")}}catch(e){{}}for(const id in s){{const v=s[id];
 const u=document.querySelector('input[name="u_'+id+'"][value="'+v.usv+'"]');if(u)u.checked=true;
 const d=document.querySelector('input[name="d_'+id+'"][value="'+v.detector+'"]');if(d)d.checked=true;
 (v.bands||[]).forEach(b=>{{const c=document.querySelector('input[name="b_'+id+'"][value="'+b+'"]');if(c)c.checked=true}})}}}})();
function exp(){{const s=st();const rows=["strip,usv,bands,detector"];for(const id in s)rows.push([id,s[id].usv,JSON.stringify(s[id].bands.join(";")),JSON.stringify(s[id].detector)].join(","));
 for(const [f,c,t] of [["usv_strip_labels.json",JSON.stringify({{run:"{out.name}",strips:s}},null,1),"application/json"],["usv_strip_labels.csv",rows.join("\\n"),"text/csv"]]){{
 const b=new Blob([c],{{type:t}});const u=URL.createObjectURL(b);const l=document.createElement("a");l.href=u;l.download=f;l.click();}}}}
</script></body></html>'''
    (out / "index.html").write_text(page, encoding="utf-8")
    print("page", out / "index.html")


if __name__ == "__main__":
    main()
