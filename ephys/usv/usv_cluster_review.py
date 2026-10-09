r"""Cluster USV candidates (DeepSqueak via ds_batch.m, or ephys/usv/usv_whiten_detect.py) and build a page where the user
labels whole CLUSTERS, not single calls. For whitened candidates, `score` = the maximum excess over the background (dB).

The user, 2026-10-09: "you won't make me look at them one by one?". So:
1. Features per detected box (ephys/usv/ds_batch.m CSV + the WAV):
   - duration, low / high / bandwidth (kHz), score;
   - peak frequency = the mean of the per-slice peak inside the box, and its spread (FM);
   - tonality = 1 - Wiener entropy (spectral flatness) in the box band, median over time slices: ~0 for broadband
     rustle, high for a whistle-like call;
   - contrast = box power vs the same time span outside the box band within 15-100 kHz (dB).
2. A 48 x 48 log-spectrogram patch (15-100 kHz, the box time +-50 ms) -> 10 principal components, joined to the
   standardised features -> k-means (k clusters, seed 0). Clusters are sorted by median tonality, most call-like first.
3. Page: per cluster, a summary row and up to N random thumbnails (spectrogram, the box outlined). Each thumbnail
   plays the box +-50 ms slowed 8x (22 / 50 kHz -> 2.7 / 6 kHz). One label per cluster (+ "odd one out" ticks on
   single thumbnails). Export -> ephys/configs/usv_review_2026c/.
The agent never judges the sounds; it only groups them.

    python ephys/usv/usv_cluster_review.py --csv <ds_batch out>/*.csv [--raw F:/3rd_rat] [--k 12] [--per-cluster 18]
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import sys
import wave
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mic_band_levels import parse_name, wav_info  # noqa: E402

FMIN, FMAX, PAD, SLOW = 15000.0, 100000.0, 0.05, 8


def wav_for(stem: str, raw: Path) -> Path:
    mic, s, _ = parse_name(Path(stem + ".wav"))
    return raw / f"{s:%Y-%m-%d}" / mic / f"{stem}.wav"


def segment(mm: np.ndarray, rate: int, t0: float, t1: float) -> np.ndarray:
    a, b = max(0, int((t0 - PAD) * rate)), min(len(mm), int((t1 + PAD) * rate))
    return np.asarray(mm[a:b], dtype=np.float32)


def spec(x: np.ndarray, rate: int):
    nper = 1024 if rate > 300000 else 512
    f, t, S = signal.spectrogram(x - x.mean(), fs=rate, nperseg=nper, noverlap=nper * 3 // 4)
    k = (f >= FMIN) & (f <= FMAX)
    return f[k], t, S[k] + 1e-20


def features(x: np.ndarray, rate: int, lo: float, hi: float, dur: float) -> tuple[dict, np.ndarray]:
    f, t, S = spec(x, rate)
    inb = (f >= lo * 1000) & (f <= hi * 1000)
    tin = (t >= PAD) & (t <= PAD + dur)
    if inb.sum() < 2 or tin.sum() < 1:
        tin = np.ones(len(t), bool)
    B = S[np.ix_(inb, tin)] if inb.sum() >= 2 else S[:, tin]
    flat = np.exp(np.mean(np.log(B), axis=0)) / np.mean(B, axis=0)
    pk = f[inb][np.argmax(B, axis=0)] / 1000 if inb.sum() >= 2 else f[np.argmax(B, axis=0)] / 1000
    out = S[np.ix_(~inb, tin)] if (~inb).sum() else B
    feat = {"tonality": float(np.median(1 - flat)), "peak_kHz": float(np.mean(pk)), "fm_sd_kHz": float(np.std(pk)),
            "contrast_db": float(10 * np.log10(B.mean() / out.mean()))}
    L = np.log10(S)
    patch = signal.resample(signal.resample(L, 48, axis=0), 48, axis=1)
    patch = (patch - patch.mean()) / (patch.std() + 1e-9)
    return feat, patch.astype(np.float32)


def thumb(path: Path, x: np.ndarray, rate: int, lo: float, hi: float, dur: float) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    f, t, S = spec(x, rate)
    fig = plt.figure(figsize=(1.9, 1.2), dpi=80)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.pcolormesh(t, f / 1000, 10 * np.log10(S), shading="auto", cmap="magma")
    ax.add_patch(plt.Rectangle((PAD, lo), dur, hi - lo, fill=False, ec="cyan", lw=0.8))
    ax.set_xlim(t[0], t[-1])
    ax.axis("off")
    fig.savefig(path)
    plt.close(fig)


def write_slow(path: Path, x: np.ndarray, rate: int) -> None:
    pcm = np.clip(x / max(1e-9, np.max(np.abs(x))) * 0.9 * 32767, -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(int(rate) // SLOW)
        w.writeframes(pcm.tobytes())


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
    from output_paths import run_dir
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", nargs="+", required=True)
    ap.add_argument("--raw", default="F:/3rd_rat")
    ap.add_argument("--k", type=int, default=12)
    ap.add_argument("--per-cluster", type=int, default=18)
    ap.add_argument("--min-dur-s", type=float, default=0.0, help="keep boxes at least this long")
    ap.add_argument("--tonal-only", action="store_true", help="keep rows with tonal == True (usv_whiten_detect.py CSVs)")
    a = ap.parse_args()
    out = run_dir("usv_cluster_review", "2026c")
    (out / "media").mkdir(exist_ok=True)
    rows, patches = [], []
    files = [p for c in a.csv for p in glob.glob(c)]
    for cf in files:
        stem = Path(cf).stem
        wav = wav_for(stem, Path(a.raw))
        rate, n, off = wav_info(wav)
        mm = np.memmap(wav, dtype="<i2", mode="r", offset=off, shape=(n,))
        try:
            d = pd.read_csv(cf)
        except pd.errors.EmptyDataError:              # no candidates in that stretch
            continue
        if "score" not in d:                         # usv_whiten_detect.py output: the score is the max excess over the background
            d["score"] = d.max_excess_db
        if a.tonal_only and "tonal" in d:
            d = d[d.tonal]
        d = d[d.dur_s >= a.min_dur_s]
        for i, r in d.iterrows():
            x = segment(mm, rate, r.begin_s, r.begin_s + min(r.dur_s, 1.5))
            if len(x) < 512:
                continue
            ft, pt = features(x, rate, r.low_kHz, r.high_kHz, min(r.dur_s, 1.5))
            rows.append({"id": f"{stem}_{i:05d}", "file": stem, "wav": str(wav), "rate": rate, "begin_s": r.begin_s, "dur_s": r.dur_s,
                         "low_kHz": r.low_kHz, "high_kHz": r.high_kHz, "bandwidth_kHz": r.high_kHz - r.low_kHz, "score": r.score, **ft})
            patches.append(pt.ravel())
        print(stem, len(d), "boxes", flush=True)
    D = pd.DataFrame(rows)
    X = np.column_stack([PCA(10, random_state=0).fit_transform(np.vstack(patches)),
                         ((D[["dur_s", "peak_kHz", "bandwidth_kHz", "tonality", "fm_sd_kHz", "contrast_db", "score"]] -
                           D[["dur_s", "peak_kHz", "bandwidth_kHz", "tonality", "fm_sd_kHz", "contrast_db", "score"]].mean()) /
                          D[["dur_s", "peak_kHz", "bandwidth_kHz", "tonality", "fm_sd_kHz", "contrast_db", "score"]].std()).to_numpy()])
    k = min(a.k, max(2, len(D) // 10))
    D["cluster_raw"] = KMeans(k, n_init=10, random_state=0).fit_predict(X)
    order = D.groupby("cluster_raw").tonality.median().sort_values(ascending=False).index
    D["cluster"] = D.cluster_raw.map({c: f"C{j + 1:02d}" for j, c in enumerate(order)})
    rng = np.random.default_rng(0)
    D["shown"] = False
    mmc = {}
    for c, g in D.groupby("cluster"):
        for i in rng.choice(g.index, size=min(a.per_cluster, len(g)), replace=False):
            r = D.loc[i]
            if r.wav not in mmc:
                rate, n, off = wav_info(Path(r.wav))
                mmc[r.wav] = (np.memmap(r.wav, dtype="<i2", mode="r", offset=off, shape=(n,)), rate)
            mm, rate = mmc[r.wav]
            x = segment(mm, rate, r.begin_s, r.begin_s + min(r.dur_s, 1.5))
            thumb(out / "media" / f"{r.id}.png", x, rate, r.low_kHz, r.high_kHz, min(r.dur_s, 1.5))
            write_slow(out / "media" / f"{r.id}.wav", x, rate)
            D.loc[i, "shown"] = True
    D.to_csv(out / "calls.csv", index=False)
    S = D.groupby("cluster").agg(calls=("id", "size"), dur_ms=("dur_s", lambda v: 1000 * v.median()), peak_kHz=("peak_kHz", "median"),
                                 bandwidth_kHz=("bandwidth_kHz", "median"), tonality=("tonality", "median"),
                                 fm_sd_kHz=("fm_sd_kHz", "median"), contrast_db=("contrast_db", "median"), score=("score", "median")).reset_index()
    S.to_csv(out / "clusters.csv", index=False)
    opts = ["22-kHz call", "50-kHz call", "other rat call", "noise (rustle / knock)", "mixed", "can't tell"]
    blocks = []
    for s in S.itertuples():
        g = D[(D.cluster == s.cluster) & D.shown]
        th = "".join(f'<div class="t"><img src="media/{r.id}.png" onclick="pl(\'{r.id}\')" title="{html.escape(r.id)}">'
                     f'<audio id="a_{r.id}" src="media/{r.id}.wav" preload="none"></audio>'
                     f'<label><input type="checkbox" name="odd_{s.cluster}" value="{r.id}">odd</label></div>' for r in g.itertuples())
        rad = " ".join(f'<label><input type="radio" name="c_{s.cluster}" value="{html.escape(o)}"> {html.escape(o)}</label>' for o in opts)
        blocks.append(f'<div class="cl"><h3>{s.cluster} — {s.calls} calls · median {s.dur_ms:.0f} ms · peak {s.peak_kHz:.1f} kHz · '
                      f'bandwidth {s.bandwidth_kHz:.1f} kHz · tonality {s.tonality:.2f} · FM sd {s.fm_sd_kHz:.1f} kHz · contrast '
                      f'{s.contrast_db:.1f} dB · score {s.score:.2f}</h3><div class="g">{th}</div><p>{rad}</p></div>')
    page = f'''<!doctype html><html><head><meta charset="utf-8"><title>USV cluster review</title><style>
body{{font-family:sans-serif;margin:16px;max-width:1300px}} .cl{{border:1px solid #999;margin:12px 0;padding:6px}} h3{{font-size:14px;margin:4px}}
.g{{display:flex;flex-wrap:wrap;gap:4px}} .t{{display:flex;flex-direction:column;align-items:center;font-size:11px}} .t img{{cursor:pointer;border:1px solid #ccc}}
</style></head><body><h2>DeepSqueak detections, grouped — label each CLUSTER (cohort 2026c)</h2>
<p>{len(D)} detected boxes from {len(files)} file(s), grouped into {len(S)} clusters (most whistle-like first). Click a thumbnail to hear it
8x slower (22 / 50 kHz become 2.7 / 6 kHz); cyan = the detected box. Choose one label per cluster; tick "odd" under thumbnails that do not
fit their cluster's label. Answers stay in this browser; <b>Export</b> at the end and save the files to
<code>ephys/configs/usv_review_2026c/</code>.</p>{"".join(blocks)}
<p><button onclick="exp()">Export JSON + CSV</button></p>
<script>
const KEY="usv_cluster_review_{out.name}";
function pl(id){{document.querySelectorAll('audio').forEach(a=>{{a.pause();a.currentTime=0}});document.getElementById('a_'+id).play();}}
function state(){{const s={{}};document.querySelectorAll('.cl').forEach(c=>{{const n=c.querySelector('input[type=radio]').name.slice(2);
 const r=c.querySelector('input[type=radio]:checked');s[n]={{label:r?r.value:"",odd:[...c.querySelectorAll('input[type=checkbox]:checked')].map(x=>x.value)}}}});return s}}
function save(){{try{{localStorage.setItem(KEY,JSON.stringify(state()))}}catch(e){{}}}}
document.addEventListener('change',save);
(function(){{let s={{}};try{{s=JSON.parse(localStorage.getItem(KEY)||"{{}}")}}catch(e){{}}for(const n in s){{const r=document.querySelector('input[name="c_'+n+'"][value="'+s[n].label+'"]');if(r)r.checked=true;
 (s[n].odd||[]).forEach(v=>{{const c=document.querySelector('input[name="odd_'+n+'"][value="'+v+'"]');if(c)c.checked=true}})}}}})();
function exp(){{const s=state();const rows=["cluster,label,odd_ids"];for(const n in s)rows.push([n,JSON.stringify(s[n].label),JSON.stringify(s[n].odd.join(";"))].join(","));
 for(const [f,c,t] of [["usv_cluster_labels.json",JSON.stringify({{run:"{out.name}",clusters:s}},null,1),"application/json"],["usv_cluster_labels.csv",rows.join("\\n"),"text/csv"]]){{
 const b=new Blob([c],{{type:t}});const u=URL.createObjectURL(b);const l=document.createElement("a");l.href=u;l.download=f;l.click();}}}}
</script></body></html>'''
    (out / "index.html").write_text(page, encoding="utf-8")
    print(S.round(2).to_string(index=False))
    print("page", out / "index.html")


if __name__ == "__main__":
    main()
