r"""USV detector v2 (plan implementation_plan/2026-10-08-mic-imu-sync.md, Amendment 2).

Per 60-s chunk of a house-mic WAV (MIC01 384 kHz, MIC02 250 kHz), 18-100 kHz:
1. Spectrogram: nperseg 1024 (384 kHz) / 512 (250 kHz), hop = nperseg / 2; L = 10 log10 PSD.
2. Background B(f) = the 20th percentile of L(., f) over the chunk (v1 used the median, which calls raise when a
   frequency is busy); excess E = L - B.
3. Components: E >= TH_DB (10 dB) after a 3 x 3 median filter, 8-connected. Per component: start / end, low / high,
   ridge (the frequency of the maximum excess per time column), tonality = median over columns of 1 - spectral flatness
   of the raw power inside its band, max excess.
4. Linking: components are joined into one contour when the next starts <= LINK_GAP_S (50 ms) after the previous ends
   and its first ridge frequency is within LINK_DF_KHZ (2 kHz) of the previous one's last; union over the chain.
5. Contour classes: line = duration > LINE_S (5 s; the drifting electronic tone, tagged "long line" by the user);
   call = not a line, tonality (duration-weighted over its parts) >= 0.5, bandwidth <= 20 kHz, duration >= 10 ms.

Output per WAV: <stem>.contours.csv (one row per contour: begin_s, dur_s, low_kHz, high_kHz, bandwidth_kHz, mean_kHz,
fm_sd_kHz, tonality, max_excess_db, n_parts, is_line, is_call).

    python ephys/usv/usv_detect_v2.py --wav <a.wav> [...] [--start-s 0 --dur-s 600] --out <dir> [--workers N]
    python ephys/usv/usv_detect_v2.py --selftest
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage, signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mic_band_levels import wav_info  # noqa: E402

FMIN, FMAX, TH_DB, PCT, CHUNK_S = 18000.0, 100000.0, 10.0, 20.0, 60.0
LINK_GAP_S, LINK_DF_KHZ, LINE_S, MIN_CALL_S = 0.05, 2.0, 5.0, 0.010
COLS = ["begin_s", "dur_s", "low_kHz", "high_kHz", "bandwidth_kHz", "mean_kHz", "fm_sd_kHz", "tonality",
        "max_excess_db", "n_parts", "is_line", "is_call"]


def components(x: np.ndarray, rate: int, t0: float) -> list[dict]:
    nper = 1024 if rate > 300000 else 512
    f, t, S = signal.spectrogram(x - x.mean(), fs=rate, nperseg=nper, noverlap=nper // 2, mode="psd")
    k = (f >= FMIN) & (f <= FMAX)
    f, S = f[k], S[k] + 1e-20
    L = 10 * np.log10(S)
    E = L - np.percentile(L, PCT, axis=1, keepdims=True)
    lab, n = ndimage.label(ndimage.median_filter(E, size=3) >= TH_DB, structure=np.ones((3, 3)))
    dt = t[1] - t[0]
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        if sl is None:
            continue
        fi, ti = sl
        reg = lab[sl] == i
        Ex = np.where(reg, E[sl], -np.inf)
        ridge = f[fi][np.argmax(Ex, axis=0)] / 1000
        B = S[fi, ti]
        flat = np.exp(np.mean(np.log(B), axis=0)) / np.mean(B, axis=0)
        out.append({"t0": t0 + t[ti.start] - dt / 2, "t1": t0 + t[ti.stop - 1] + dt / 2, "low": f[fi][0] / 1000,
                    "high": f[fi][-1] / 1000, "r0": float(ridge[0]), "r1": float(ridge[-1]), "ridge": ridge,
                    "ton": float(np.median(1 - flat)), "exc": float(np.max(Ex))})
    return out


def link(comps: list[dict]) -> pd.DataFrame:
    if not comps:
        return pd.DataFrame(columns=COLS)
    comps = sorted(comps, key=lambda c: c["t0"])
    parent = list(range(len(comps)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    starts = np.array([c["t0"] for c in comps])
    for i, c in enumerate(comps):
        j0 = np.searchsorted(starts, c["t1"] - 1e-9)                     # candidates starting after c ends
        j1 = np.searchsorted(starts, c["t1"] + LINK_GAP_S, side="right")
        for j in range(max(j0, i + 1), j1):
            if abs(comps[j]["r0"] - c["r1"]) <= LINK_DF_KHZ:
                parent[find(j)] = find(i)
    groups: dict[int, list[int]] = {}
    for i in range(len(comps)):
        groups.setdefault(find(i), []).append(i)
    rows = []
    for idx in groups.values():
        cs = [comps[i] for i in idx]
        b, e = min(c["t0"] for c in cs), max(c["t1"] for c in cs)
        w = np.array([c["t1"] - c["t0"] for c in cs])
        ridge = np.concatenate([c["ridge"] for c in cs])
        lo, hi = min(c["low"] for c in cs), max(c["high"] for c in cs)
        ton = float(np.average([c["ton"] for c in cs], weights=w))
        dur = e - b
        is_line = dur > LINE_S
        rows.append({"begin_s": b, "dur_s": dur, "low_kHz": lo, "high_kHz": hi, "bandwidth_kHz": hi - lo,
                     "mean_kHz": float(np.mean(ridge)), "fm_sd_kHz": float(np.std(ridge)), "tonality": ton,
                     "max_excess_db": max(c["exc"] for c in cs), "n_parts": len(cs), "is_line": is_line,
                     "is_call": (not is_line) and ton >= 0.5 and (hi - lo) <= 20 and dur >= MIN_CALL_S})
    return pd.DataFrame(rows, columns=COLS).sort_values("begin_s").reset_index(drop=True)


def detect_file(p: Path, start_s: float = 0.0, dur_s: float | None = None) -> pd.DataFrame:
    rate, n, off = wav_info(p)
    mm = np.memmap(p, dtype="<i2", mode="r", offset=off, shape=(n,))
    end = n / rate if dur_s is None else min(n / rate, start_s + dur_s)
    comps = []
    t = start_s
    while t < end - 1:
        x = np.asarray(mm[int(t * rate):int(min(end, t + CHUNK_S) * rate)], dtype=np.float32)
        comps += components(x, rate, t)
        t += CHUNK_S
    return link(comps)


def one(job: tuple) -> str:
    w, out, s, d = job
    p = Path(w)
    D = detect_file(p, s, d)
    D.to_csv(Path(out) / f"{p.stem}.contours.csv", index=False)
    return f"{p.name}: {len(D)} contours, {int(D.is_call.sum())} calls, {int(D.is_line.sum())} lines"


def selftest() -> None:
    """Synthetic 384-kHz noise + a steady 30-kHz tone + a 2-s 23-kHz call broken by three 30-ms gaps + a 40-ms 55-kHz
    call + a 8-s slowly drifting 19-20 kHz line: the broken call must come out as ONE call contour of ~2 s, the short
    call as a call, the drifting line as a line, and the steady tone not at all."""
    rate = 384000
    tt = np.arange(int(20 * rate)) / rate
    rng = np.random.default_rng(0)
    x = rng.normal(0, 30, len(tt))
    x += 300 * np.sin(2 * np.pi * 30000 * tt)
    m = (tt >= 3) & (tt < 5)
    for g in (3.5, 4.0, 4.5):
        m &= ~((tt >= g) & (tt < g + 0.03))
    x += m * 200 * np.sin(2 * np.pi * 23000 * tt)
    m2 = (tt >= 8) & (tt < 8.04)
    x += m2 * 200 * np.sin(2 * np.pi * 55000 * tt)
    m3 = (tt >= 10) & (tt < 18)
    fdr = 19000 + 1000 * (tt - 10) / 8
    x += m3 * 120 * np.sin(2 * np.pi * np.cumsum(fdr) / rate)
    D = link(components(x.astype(np.float32), rate, 0.0))
    calls, lines = D[D.is_call], D[D.is_line]
    c23 = calls[(calls.mean_kHz > 21) & (calls.mean_kHz < 25)]
    assert len(c23) == 1 and 1.8 < c23.dur_s.iloc[0] < 2.2, D.to_string()
    assert ((calls.mean_kHz > 53) & (calls.mean_kHz < 57)).sum() == 1, D.to_string()
    assert len(lines) >= 1 and (lines.mean_kHz.between(18.5, 20.5)).any(), D.to_string()
    assert not ((D.mean_kHz > 29.5) & (D.mean_kHz < 30.5) & (D.dur_s > 1)).any(), D.to_string()
    print(f"selftest PASS: broken 2-s call -> one contour of {c23.dur_s.iloc[0]:.2f} s ({int(c23.n_parts.iloc[0])} parts); "
          f"short call found; drifting line flagged ({lines.dur_s.max():.1f} s); steady tone removed")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wav", nargs="*")
    ap.add_argument("--start-s", type=float, default=0.0)
    ap.add_argument("--dur-s", type=float, default=None)
    ap.add_argument("--out")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    Path(a.out).mkdir(parents=True, exist_ok=True)
    jobs = [(w, a.out, a.start_s, a.dur_s) for w in a.wav]
    with ProcessPoolExecutor(a.workers) as ex:
        for msg in ex.map(one, jobs):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
