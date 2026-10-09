r"""USV candidates after removing the mics' steady background (the user, 2026-10-09: "most of the time should be silence").

Why: both house mics carry steady narrow tones all the time (MIC01 30.0 kHz and a wandering 18-19.6 kHz line; MIC02 21,
22, 27, 29.9 kHz; 19-30 dB above the background, measured 2026-10-09). DeepSqueak boxes slices of them as calls.

Method (USVSEG-like):
1. Spectrogram 18-100 kHz: nperseg 1024 (MIC01 384 kHz -> 375 Hz bins) / 512 (MIC02 250 kHz -> 488 Hz), hop = nperseg / 2
   (1.3 / 1.0 ms), in 60-s chunks.
2. Whitening: per frequency bin, excess(t, f) = 10 log10 S(t, f) - the median of 10 log10 S(., f) over the chunk (60 s).
   A steady tone has its own median, so it vanishes; a transient above it stays.
3. Candidate = a connected region (8-neighbour) of excess >= TH_DB (10 dB) lasting >= 5 ms, after a 3 x 3 median filter.
4. Features: begin / duration, low / high / bandwidth (kHz), peak frequency (excess-weighted) and its spread, tonality =
   1 - spectral flatness of the raw power inside the box band, max excess (dB).
5. "Tonal" = tonality >= 0.5 and bandwidth <= 20 kHz (a call is a narrow whistle; rustle and knocks are broadband).
Counts per hour, all vs tonal, are the check against the user's expectation (daytime nearly silent).

    python ephys/usv/usv_whiten_detect.py --wav <file.wav> [...] [--start-s S --dur-s D] --out <dir>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage, signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mic_band_levels import parse_name, wav_info  # noqa: E402

FMIN, FMAX, TH_DB, MIN_DUR_S, CHUNK_S = 18000.0, 100000.0, 10.0, 0.005, 60.0


def detect_chunk(x: np.ndarray, rate: int, t0: float) -> list[dict]:
    nper = 1024 if rate > 300000 else 512
    f, t, S = signal.spectrogram(x - x.mean(), fs=rate, nperseg=nper, noverlap=nper // 2, mode="psd")
    k = (f >= FMIN) & (f <= FMAX)
    f, S = f[k], S[k] + 1e-20
    L = 10 * np.log10(S)
    E = L - np.median(L, axis=1, keepdims=True)
    M = ndimage.median_filter(E, size=3) >= TH_DB
    lab, nlab = ndimage.label(M, structure=np.ones((3, 3)))
    out = []
    dt = t[1] - t[0]
    for sl, i in zip(ndimage.find_objects(lab), range(1, nlab + 1)):
        fi, ti = sl
        dur = (ti.stop - ti.start) * dt
        if dur < MIN_DUR_S:
            continue
        reg = lab[sl] == i
        Ex = np.where(reg, E[sl], np.nan)
        w = np.nan_to_num(10 ** (Ex / 10))
        fk = f[fi]
        pk_t = fk[np.nanargmax(np.where(reg, E[sl], -np.inf), axis=0)]
        B = S[fi, ti]
        flat = np.exp(np.mean(np.log(B), axis=0)) / np.mean(B, axis=0)
        out.append({"begin_s": t0 + t[ti.start] - dt / 2, "dur_s": dur, "low_kHz": fk[0] / 1000, "high_kHz": fk[-1] / 1000,
                    "bandwidth_kHz": (fk[-1] - fk[0]) / 1000, "peak_kHz": float((w.sum(1) @ fk) / max(w.sum(), 1e-12)) / 1000,
                    "fm_sd_kHz": float(np.std(pk_t)) / 1000, "tonality": float(np.median(1 - flat)), "max_excess_db": float(np.nanmax(Ex))})
    return out


def detect_file(p: Path, start_s: float = 0.0, dur_s: float | None = None) -> pd.DataFrame:
    rate, n, off = wav_info(p)
    mm = np.memmap(p, dtype="<i2", mode="r", offset=off, shape=(n,))
    end = n / rate if dur_s is None else min(n / rate, start_s + dur_s)
    rows = []
    t = start_s
    while t < end - 1:
        x = np.asarray(mm[int(t * rate):int(min(end, t + CHUNK_S) * rate)], dtype=np.float32)
        rows += detect_chunk(x, rate, t)
        t += CHUNK_S
    cols = ["begin_s", "dur_s", "low_kHz", "high_kHz", "bandwidth_kHz", "peak_kHz", "fm_sd_kHz", "tonality", "max_excess_db"]
    D = pd.DataFrame(rows, columns=cols)              # an empty result keeps its header (a silent stretch is a valid result)
    D["tonal"] = (D.tonality >= 0.5) & (D.bandwidth_kHz <= 20)
    D.attrs.update(rate=rate, seconds=end - start_s)
    return D


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wav", nargs="+", required=True)
    ap.add_argument("--start-s", type=float, default=0.0)
    ap.add_argument("--dur-s", type=float, default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    summ = []
    for w in a.wav:
        p = Path(w)
        D = detect_file(p, a.start_s, a.dur_s)
        D.to_csv(out / f"{p.stem}.csv", index=False)
        h = D.attrs["seconds"] / 3600
        mic, s, _ = parse_name(p)
        summ.append({"file": p.name, "start": s, "minutes": round(h * 60, 1), "candidates_per_h": len(D) / h,
                     "tonal_per_h": float(D.tonal.sum()) / h if len(D) else 0.0,
                     "tonal_median_kHz": float(D[D.tonal].peak_kHz.median()) if len(D) and D.tonal.any() else np.nan,
                     "tonal_median_ms": float(1000 * D[D.tonal].dur_s.median()) if len(D) and D.tonal.any() else np.nan})
        print(summ[-1], flush=True)
    pd.DataFrame(summ).to_csv(out / "summary.csv", index=False)


if __name__ == "__main__":
    main()
