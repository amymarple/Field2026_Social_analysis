"""Raw multi-unit check of detected delta waves (no sorting): is there a DOWN state at the delta peak?

Threshold crossings on the raw 20-kHz amplifier.dat (read-only; FM65 sessions, no de-glitch): common median reference
over the live channels, 600-6000 Hz Butterworth-3 (zero phase, 60-s chunks + 50-ms margins), negative crossings of
-4.5 x MAD/0.6745 per channel and chunk, 1-ms refractory. Delta peaks come from `delta_detect.py scan`
(<label>_delta_scan.npz, deltas_<col>) of one reference column; LFP sample k <-> amplifier sample 16 k. The longest NREM
bouts (trimmed 5 s) are used up to --minutes. Per site: mean crossing rate and the rate within +-50 ms of the peak / the
-1..-0.6 s baseline (detect_delta_waves' verify_firing window). Sites under ~1 Hz carry no units: their ratio is noise.

  python ephys/delta_mua_check.py --raw <session dir> --states <SleepState.states.mat> --xml <final XML>
         --scan-npz <label>_delta_scan.npz --ref-col C [--minutes 30] --out <npz>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delta_detect as dd  # noqa: E402
import swr_layer_order as slo  # noqa: E402

FS, FL = 20000.0, 1250.0


def longest_bouts(nrem: np.ndarray, minutes: float, trim: float = 5.0, min_s: float = 60.0):
    sel, tot = [], 0.0
    for a, b in nrem[np.argsort(-(nrem[:, 1] - nrem[:, 0]))]:
        a, b = a + trim, b - trim
        if b - a < min_s:
            continue
        b = min(b, a + (minutes * 60 - tot))
        sel.append((a, b))
        tot += b - a
        if tot >= minutes * 60 - 1:
            break
    return sorted(sel)


def crossings(x: np.ndarray, sos, thr_mad: float = 4.5, refractory: int = 20):
    """x: samples x channels (already referenced) -> list of crossing sample indices per channel."""
    y = signal.sosfiltfilt(sos, x, axis=0)
    thr = -thr_mad * np.median(np.abs(y), axis=0) / 0.6745
    below = y < thr
    on = below[1:] & ~below[:-1]
    out = []
    for c in range(x.shape[1]):
        t = np.flatnonzero(on[:, c]) + 1
        out.append(t[np.concatenate([[True], np.diff(t) > refractory])] if t.size else t)
    return out


def mua_check(raw: Path, states: Path, xml: Path, peaks_s: np.ndarray, minutes: float = 30.0, nch: int = 64):
    mm = np.memmap(raw / "amplifier.dat", dtype=np.int16, mode="r")
    mm = mm[: mm.size // nch * nch].reshape(-1, nch)
    groups, skip = slo.read_groups(xml)
    live = [c for c in range(nch) if c not in skip]
    sel = longest_bouts(dd.load_nrem(states), minutes)
    pk = 16 * (np.round(peaks_s * FL).astype(np.int64) - 1)
    sos = signal.butter(3, (600, 6000), btype="bandpass", fs=FS, output="sos")
    w, binw = int(FS), int(0.01 * FS)
    nb = 2 * w // binw
    counts, nspk = np.zeros((nch, nb)), np.zeros(nch)
    n_ev, dur = 0, 0.0
    for a, b in sel:
        s0, s1 = int(a * FS), int(b * FS)
        ev = pk[(pk - w >= s0) & (pk + w < s1)]
        spikes = [[] for _ in range(nch)]
        m = int(0.05 * FS)
        for c0 in range(s0, s1, int(60 * FS)):
            c1 = min(c0 + int(60 * FS), s1)
            lo = max(c0 - m, 0)
            x = np.asarray(mm[lo:c1 + m], np.float32)
            x -= np.median(x[:, live], axis=1, keepdims=True)
            for c, t in enumerate(crossings(x, sos)):
                t = t[(t >= c0 - lo) & (t < c1 - lo)] + lo
                spikes[c].append(t)
        dur += (s1 - s0) / FS
        for c in range(nch):
            st = np.concatenate(spikes[c])
            nspk[c] += st.size
            for e in ev:
                i0, i1 = np.searchsorted(st, [e - w, e + w])
                counts[c] += np.bincount((st[i0:i1] - (e - w)) // binw, minlength=nb)[:nb]
        n_ev += ev.size
    rate = counts / max(n_ev, 1) / 0.01
    lag = (np.arange(nb) + 0.5) * 0.01 - 1.0
    base, peak = (lag >= -1.0) & (lag <= -0.6), np.abs(lag) <= 0.05
    ratio = rate[:, peak].mean(axis=1) / np.maximum(rate[:, base].mean(axis=1), 1e-9)
    return dict(rate=rate, lag=lag, ratio=ratio, mean_rate=nspk / max(dur, 1e-9), n_events=n_ev, minutes=dur / 60,
                bouts=np.array(sel), groups=groups, skip=skip)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--states", required=True)
    ap.add_argument("--xml", required=True)
    ap.add_argument("--scan-npz", required=True)
    ap.add_argument("--ref-col", type=int, required=True)
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    peaks = np.load(a.scan_npz)[f"deltas_{a.ref_col}"][:, 1]
    r = mua_check(Path(a.raw), Path(a.states), Path(a.xml), peaks, a.minutes)
    print(f"ref col {a.ref_col}: {r['n_events']} delta events in {r['minutes']:.1f} min NREM")
    for gi, g in enumerate(r["groups"], 1):
        print(f" shank {gi}: " + "  ".join(f"{j + 1}:{c}{'x' if c in r['skip'] else ''}[{r['mean_rate'][c]:.1f} Hz,"
                                           f"{r['ratio'][c]:.2f}]" for j, c in enumerate(g)))
    np.savez_compressed(a.out, **{k: v for k, v in r.items() if k not in ("groups", "skip")}, ref=a.ref_col)
    print("->", a.out)


if __name__ == "__main__":
    main()
