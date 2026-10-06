r"""SF12 shank-1 integrity check (one-off, hard-codes SF12's 2026c channel map; read-only on the raw session).

Why: the user marked SF12's 09-07 night (2_20260907_180003) as logger noise; the sleep scorer had picked shank-1 column 58
as its slow-wave channel there. Per 1-min window every 30 min of the raw 20-kHz amplifier.dat (0-based columns):
  MAD(c)    = median |x_c - median(x_c)|, ADC (open circuit ~60-150; healthy 300-1400 here)
  frac60(c) = P_c(59-61 Hz) / P_c(1-100 Hz) on the 1250-Hz LFP (Welch, 2-s segments)
  corr(c)   = Pearson r of the LFP of c with the median LFP of shanks 2+3 (healthy cortex/HPC LFP is coherent: 0.8-0.99)
printed as medians over [the watch columns 48/58/60/63] | [the other shank-1 columns] | [shanks 2+3].

Usage: python ephys/sf12_shank1_check.py 2_20260907_090439.409 2_20260907_180003.285
"""
import sys
import numpy as np
from pathlib import Path
from scipy import signal

RAW = Path("E:/3rd_rat_spikes/SF12/FBED2F2321B1")
SH1 = [57, 52, 54, 50, 56, 61, 53, 48, 58, 63, 60, 59, 49, 55, 62, 51]
WATCH = [48, 58, 60, 63]
OTHER1 = [c for c in SH1 if c not in WATCH]
REF = [42, 39, 40, 33, 41, 43, 34, 44, 35, 47, 32, 11, 6, 9, 8, 13, 4, 7, 15, 2, 12, 1]   # shanks 2 + 3
FS, NCH = 20000, 64


def window(ses: str, t0_s: float, dur_s: float = 60.0):
    f = RAW / ses / "amplifier.dat"
    n = f.stat().st_size // (2 * NCH)
    a = int(t0_s * FS)
    if a + int(dur_s * FS) > n:
        return None
    x = np.fromfile(f, dtype=np.int16, count=int(dur_s * FS) * NCH, offset=a * NCH * 2).reshape(-1, NCH).astype(np.float32)
    mad = np.median(np.abs(x - np.median(x, axis=0)), axis=0)
    lfp = signal.resample_poly(x, 1, 16, axis=0)
    f_, p = signal.welch(lfp, fs=1250, nperseg=2500, axis=0)
    frac60 = p[(f_ >= 59) & (f_ <= 61)].sum(0) / p[(f_ >= 1) & (f_ <= 100)].sum(0)
    ref = np.median(lfp[:, REF], axis=1)
    corr = np.array([np.corrcoef(lfp[:, c], ref)[0, 1] for c in range(NCH)])
    return mad, frac60, corr


for ses in sys.argv[1:]:
    n_s = (RAW / ses / "amplifier.dat").stat().st_size / (2 * NCH * FS)
    print(f"\n{ses}  ({n_s / 3600:.1f} h)   per window: median over [watch 48/58/60/63] | [other shank 1] | [shanks 2+3]")
    for t in np.arange(60, n_s - 60, 1800):
        r = window(ses, t)
        if r is None:
            continue
        mad, f60, cr = r
        def m(v, cols):
            return np.median(v[cols])
        print(f"  +{t / 3600:5.2f} h  MAD {m(mad, WATCH):6.0f} | {m(mad, OTHER1):6.0f} | {m(mad, REF):6.0f}   "
              f"60Hz {m(f60, WATCH):.2f} | {m(f60, OTHER1):.2f} | {m(f60, REF):.2f}   "
              f"corr {m(cr, WATCH):.2f} | {m(cr, OTHER1):.2f} | {m(cr, REF):.2f}   "
              f"per watch col MAD {' '.join(f'{c}:{mad[c]:.0f}' for c in WATCH)}")
