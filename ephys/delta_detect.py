"""Faithful Python port of the lab's delta-wave detector: neurocode/lfp/FindDeltaWaves.m (current = 2022-10 / 2023-09
version) + detect_delta_waves.m (wrappers 2024-06 and 2025-09), the user's older script
(R_Project/PPP/codebook/pre_Ephys_pipline.m, used for PPP / HYC3), and the 2017 FindDeltaWaves for the record.

FindDeltaWaves (one channel, [t x]):
  filtered = FilterLFP(x, 0.5-9 Hz)           cheby2 (order 5, 20 dB) filtfilt on a 1250-Hz grid interpolated over gaps;
                                              band = lowpass 9 Hz of (x - lowpass 0.5 Hz)
  dz = zscore(FilterLFP(diff(filtered), 0-9 Hz, order 8))
  triplets = (up, down, next up) zero crossings of dz = local min -> max -> min of the filtered LFP
  keep 150-650 ms (min to min) and, in z of the filtered LFP, (peak > 3 & end <= 0) | (peak >= 1 & end < -1.5),
  peak > start                                -> rows [t_start t_peak t_end z_start z_peak z_end]
  (the rule is "a peak, then a deep trough": an inverted wave with a positive side lobe before its trough also passes,
  so polarity must be checked on the channel, not assumed)
  ("2017": no internal filter — the caller was meant to pass a delta-band signal —, 150-450 ms, highPeak 2, no
  peak > start rule)
detect_delta_waves: NREM restrict (Restrict of k/fs, k 1-based) -> CleanLFP [6 10] (+-0.5 / 0.1 s, bad samples
  linearly interpolated) -> EMGFromLFP < 0.6 for >= 1 s -> FindDeltaWaves -> z_peak - z_end > 3 (verify_firing, which
  needs sorted cortical units, can only raise this threshold).

Every interval and time follows the MATLAB code: sample k (1-based) <-> k / fs s, intervals inclusive. The LFP is read
through a numpy memmap; nothing is written next to it.

  python ephys/delta_detect.py --selftest
  python ephys/delta_detect.py replay --session-dir <lab session> [--script lab|user] [--version current|2017]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.fft import next_fast_len

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swr_detect as sd  # noqa: E402

GRID_FS = 1250.0  # FilterLFP interpolates every signal to this rate (its filters assume nyquist 625)

FINDDELTA = {
    #            lowPeak highPeak lowTrough highTrough  min_ms max_ms  peak>start  internal filter
    "current": dict(lp=1.0, hp=3.0, lt=0.0, ht=1.5, dmin=150.0, dmax=650.0, above_start=True, filt=True),
    "2017": dict(lp=1.0, hp=2.0, lt=0.0, ht=1.5, dmin=150.0, dmax=450.0, above_start=False, filt=False),
}


# --------------------------------------------------------------------------------------------- MATLAB primitives
def zscore(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, float)
    return (x - x.mean()) / x.std(ddof=1)


def filtfilt_mat(b, a, x):
    """MATLAB filtfilt: odd reflection of 3*(nfilt-1) samples, steady-state initial conditions (== scipy 'pad')."""
    return signal.filtfilt(b, a, x, padtype="odd", padlen=3 * (max(len(a), len(b)) - 1))


def mat_filter(x: np.ndarray, passband, order: int = 5) -> np.ndarray:
    """FMA Filter.m, cheby2 branch (ripple 20 dB, nyquist 625)."""
    if passband[0] == 0:
        b, a = signal.cheby2(order, 20, passband[1] / 625.0, btype="low", output="ba")
    else:
        b, a = signal.cheby2(order, 20, np.asarray(passband) / 625.0, btype="bandpass", output="ba")
    return filtfilt_mat(b, a, x)


def _grid(t0: np.ndarray) -> np.ndarray:
    n = int(np.floor((t0[-1] - t0[0]) * GRID_FS + 1e-6)) + 1  # MATLAB t0(1):1/1250:t0(end)
    return t0[0] + np.arange(n) / GRID_FS


def filter_lfp(t0: np.ndarray, x: np.ndarray, passband, order: int = 5) -> np.ndarray:
    """neurocode FilterLFP (2024 version): interpolate to a 1250-Hz grid (linear across gaps), filter, sample back.
    passband (a, b) with a > 0 = lowpass b of (x - lowpass a)."""
    t0 = np.asarray(t0, float)
    x = np.asarray(x, float)
    ok = np.diff(np.concatenate([[-np.inf], t0])) > 0
    tg = _grid(t0)
    xg = np.interp(tg, t0[ok], x[ok])
    if passband[0] > 0:
        hp = xg - mat_filter(xg, (0.0, passband[0]), order)
        fg = hp if np.isinf(passband[1]) else mat_filter(hp, (0.0, passband[1]), order)
    else:
        fg = mat_filter(xg, passband, order)
    out = np.interp(t0, tg, fg)
    out[t0 > tg[-1]] = np.nan  # interp1 outside the grid
    if np.isnan(out[-1]):
        out[-1] = out[-2]
    return out


def zero_crossings(x: np.ndarray):
    """FMA ZeroCrossings: 0-based index of the sample BEFORE each strict sign change (exact zeros never count)."""
    prev, cur = x[:-1], x[1:]
    return np.flatnonzero((prev < 0) & (cur > 0)), np.flatnonzero((prev > 0) & (cur < 0))


def runs(mask: np.ndarray) -> np.ndarray:
    """FindInterval: [first, last] (0-based, inclusive) of every run of True."""
    e = np.diff(np.concatenate([[0], np.asarray(mask, np.int8), [0]]))
    return np.column_stack([np.flatnonzero(e == 1), np.flatnonzero(e == -1) - 1])


def consolidate(iv: np.ndarray) -> np.ndarray:
    """ConsolidateIntervals (strict off, epsilon 0): merge overlapping or touching intervals."""
    if iv.size == 0:
        return np.zeros((0, 2))
    iv = iv[np.argsort(iv[:, 0], kind="stable")]
    out = [list(iv[0])]
    for a, b in iv[1:]:
        if a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return np.array(out, float)


def clean_lfp(t: np.ndarray, x: np.ndarray, thresholds=(6.0, 10.0), around=(0.5, 0.1)):
    """neurocode CleanLFP (non-manual): |z| > thr1 (+-around1) or |diff(z)| > thr2 (+-around2) -> bad; bad samples are
    replaced by linear interpolation from the good ones, NaNs at the ends dropped. The codebook copy used by the
    user's script is the same with around = (2, 0.1)."""
    x = np.asarray(x, float).copy()
    z = zscore(x)
    d = np.append(np.diff(z), 0.0)
    bad = np.zeros(x.shape, bool)
    ivs = []
    for mask, pad in ((np.abs(z) > thresholds[0], around[0]), (np.abs(d) > thresholds[1], around[1])):
        r = runs(mask)
        if r.size:
            iv = consolidate(np.column_stack([t[r[:, 0]] - pad, t[r[:, 1]] + pad]))
            bad |= sd.in_intervals(t, iv)
            ivs.append(iv)
    if bad.any():
        tg, xg = t[~bad], x[~bad]
        v = np.interp(t[bad], tg, xg)
        v[(t[bad] < tg[0]) | (t[bad] > tg[-1])] = np.nan
        x[bad] = v
    ok = ~np.isnan(x)
    return t[ok], x[ok], bad, (consolidate(np.concatenate(ivs)) if ivs else np.zeros((0, 2)))


def immobility(emg_t: np.ndarray, emg_x: np.ndarray, thr: float = 0.6) -> np.ndarray:
    """detect_delta_waves: EMG.timestamps(FindInterval(EMG.data < thr)), intervals shorter than 1 s removed."""
    r = runs(np.asarray(emg_x) < thr)
    iv = np.column_stack([emg_t[r[:, 0]], emg_t[r[:, 1]]]) if r.size else np.zeros((0, 2))
    return iv[(iv[:, 1] - iv[:, 0]) >= 1] if iv.size else iv


# ---------------------------------------------------------------------------------------------- the detector
def find_delta_waves(t: np.ndarray, x: np.ndarray, version: str = "current") -> np.ndarray:
    """FindDeltaWaves.m -> N x 6 [t_start t_peak t_end z_start z_peak z_end] (z of the filtered LFP)."""
    p = FINDDELTA[version]
    t = np.asarray(t, float)
    if p["filt"]:
        filtered = filter_lfp(t, x, (0.5, 9.0))
        dz = zscore(filter_lfp(t, np.append(np.diff(filtered), 0.0), (0.0, 9.0), order=8))
    else:
        filtered = np.asarray(x, float)
        dz = zscore(np.append(np.diff(filtered), 0.0))
    up, down = zero_crossings(dz)
    if down.size and up.size and down[0] < up[0]:
        down = down[1:]
    n = up.size
    if down.size < n - 1:
        raise ValueError("FindDeltaWaves: fewer down than up crossings (MATLAB would fail on down(1:n-1))")
    w = np.column_stack([up[:n - 1], down[:n - 1], up[1:n]])
    zf = zscore(filtered)
    D = np.column_stack([t[w[:, 0]], t[w[:, 1]], t[w[:, 2]], zf[w[:, 0]], zf[w[:, 1]], zf[w[:, 2]]])
    dur = D[:, 2] - D[:, 0]
    D = D[~((dur < p["dmin"] / 1000) | (dur > p["dmax"] / 1000))]
    peak, trough = D[:, 4], D[:, 5]
    keep = ((peak > p["hp"]) & (trough <= -p["lt"])) | ((peak >= p["lp"]) & (trough < -p["ht"]))
    if p["above_start"]:
        keep &= peak > D[:, 3]
    return D[keep]


def keep_outside(ignore: np.ndarray) -> np.ndarray:
    """~IntervalArray(ignore): the gaps between consecutive intervals, from -inf to inf (used with Restrict)."""
    iv = np.asarray(ignore, float).reshape(-1, 2)
    iv = iv[np.argsort(iv[:, 0], kind="stable")]
    comp = np.column_stack([np.concatenate([[-np.inf], iv[:, 1]]), np.concatenate([iv[:, 0], [np.inf]])])
    return comp[comp[:, 1] >= comp[:, 0]]


def intersects(ev: np.ndarray, iv: np.ndarray) -> np.ndarray:
    """IntervalsIntersect(ev, iv): an iv start or end inside [s, e] of the event, or the event end inside an iv."""
    if ev.size == 0 or iv.size == 0:
        return np.zeros(ev.shape[0], bool)
    iv = iv[np.argsort(iv[:, 0], kind="stable")]
    hit = np.zeros(ev.shape[0], bool)
    for col in (iv[:, 0], np.sort(iv[:, 1])):
        hit |= np.searchsorted(col, ev[:, 1], side="right") > np.searchsorted(col, ev[:, 0], side="left")
    i = np.searchsorted(iv[:, 0], ev[:, 1], side="right") - 1
    j = np.clip(i, 0, None)
    return hit | ((i >= 0) & (ev[:, 1] <= np.maximum.accumulate(iv[:, 1])[j]))


WRAPPERS = ("2025-09", "2024-06")  # detect_delta_waves 61e7b5b (ignore cut from the LFP) / a60fc16..f560cfe (events
#                                     intersecting an ignore interval dropped after the threshold)


def detect(x: np.ndarray, fs: float, nrem=None, emg=None, emg_thr: float = 0.6, clean=(6.0, 10.0),
           around=(0.5, 0.1), threshold: float = 3.0, version: str = "current", ignore=None,
           wrapper: str = "2025-09"):
    """detect_delta_waves.m without the channel choice and verify_firing. x = the whole channel (int16 ok);
    nrem = N x 2 s (None = whole record); emg = (t, data) of EMGFromLFP (None or emg_thr = inf = no gate);
    ignore = N x 2 s (e.g. stimulation), handled as in `wrapper`. Returns (deltas, all candidates, info)."""
    t = (np.arange(x.size) + 1) / fs
    x = np.asarray(x, float)
    if nrem is not None:
        m = sd.in_intervals(t, np.asarray(nrem, float).reshape(-1, 2))
        t, x = t[m], x[m]
    n_restricted = t.size
    t, x, bad, bad_iv = clean_lfp(t, x, clean, around)
    if emg is not None and np.isfinite(emg_thr):
        m = sd.in_intervals(t, immobility(emg[0], emg[1], emg_thr))
        t, x = t[m], x[m]
    has_ignore = ignore is not None and np.size(ignore) > 0
    if has_ignore and wrapper == "2025-09":
        m = sd.in_intervals(t, keep_outside(ignore))
        t, x = t[m], x[m]
    D0 = find_delta_waves(t, x, version)
    D = D0[(D0[:, 4] - D0[:, 5]) > threshold]
    if has_ignore and wrapper == "2024-06":
        D = D[~intersects(D[:, [0, 2]], np.asarray(ignore, float).reshape(-1, 2))]
    info = dict(n_samples_nrem=int(n_restricted), n_bad=int(bad.sum()), n_samples_used=int(t.size),
                n_candidates=int(D0.shape[0]), n_events=int(D.shape[0]))
    return D, D0, info


# ------------------------------------------------------------------------------------------------------ lab files
def _mat(path):
    import scipy.io as sio
    return sio.loadmat(str(path), squeeze_me=True, struct_as_record=False)


def load_session_meta(sdir: Path):
    s = _mat(sdir / f"{sdir.name}.session.mat")["session"]
    return int(s.extracellular.nChannels), float(s.extracellular.srLfp)


def load_nrem(path) -> np.ndarray:
    ss = _mat(path)["SleepState"]
    return np.atleast_2d(np.asarray(ss.ints.NREMstate, float)).reshape(-1, 2)


def nrem_from_states(path) -> np.ndarray:
    """NREM intervals [s] from the final 1-s states (<session>.states.npz: ts, state; 3 = NREM) as [first, last] second
    of every run - identical to SleepState.ints.NREMstate (checked on SF07 / SF11 2026-10-09); a SleepState .mat is read
    directly."""
    if str(path).endswith(".mat"):
        return load_nrem(path)
    st = np.load(path)
    ts = st["ts"][st["state"] == 3].astype(np.int64)
    if not ts.size:
        return np.zeros((0, 2))
    br = np.flatnonzero(np.diff(ts) > 1)
    return np.column_stack([ts[np.r_[0, br + 1]], ts[np.r_[br, ts.size - 1]]]).astype(float)


def load_emg(path):
    m = _mat(path)
    e = m[[k for k in m if not k.startswith("__")][0]]
    return np.asarray(e.timestamps, float).ravel(), np.asarray(e.data, float).ravel()


def load_deltas(path) -> dict:
    d = _mat(path)["deltaWaves"]
    ts = np.atleast_2d(np.asarray(d.timestamps, float))
    out = dict(start=ts[:, 0], stop=ts[:, 1], peak=np.atleast_1d(np.asarray(d.peaks, float)), fields=d._fieldnames)
    if "detectorinfo" in d._fieldnames:
        di = d.detectorinfo
        dp = di.detectionparms
        thr = np.asarray(getattr(di, "threshold", []), float).ravel()  # final (after verify_firing; [] if it failed)
        base = np.asarray(getattr(dp, "threshold", 3.0), float).ravel()  # the amplitude threshold passed in
        ign = np.asarray(getattr(dp, "ignore_intervals", []), float)
        out.update(kind="lab", channel0=int(di.detectionchannel),
                   threshold=float(thr[0]) if thr.size else float(base[0]) if base.size else 3.0,
                   verify=bool(getattr(dp, "verify_firing", False)), emg_thr=float(dp.EMG_threshold),
                   nrem=bool(dp.NREM_restrict), ignore=ign.reshape(-1, 2) if ign.size else None,
                   values=np.atleast_2d(np.asarray(d.values, float)))
    else:
        name = str(d.detectorName)
        m = re.search(r"channel (\d+)", name)
        t = re.search(r"peak-trough>\s*([\d.]+)", name)
        out.update(kind="user", channel0=int(m.group(1)), threshold=float(t.group(1)) if t else None, name=name,
                   values=np.column_stack([np.full(ts.shape[0], np.nan), np.asarray(d.peakNormedPower, float),
                                           np.asarray(d.troughValue, float)]))
    return out


def compare(D: np.ndarray, ref: dict) -> dict:
    out = dict(n_port=int(D.shape[0]), n_ref=int(ref["peak"].size))
    for tol, name in ((0.5 / GRID_FS, "exact"), (0.010, "10ms")):
        ia, ib = sd.match_peaks(D[:, 1], ref["peak"], tol)
        out[f"match_{name}"] = int(ia.size)
        out[f"recall_{name}"] = round(ia.size / max(out["n_ref"], 1), 4)
        out[f"precision_{name}"] = round(ia.size / max(out["n_port"], 1), 4)
        if name == "exact" and ia.size:
            out["max_dt_start_ms"] = round(float(np.max(np.abs(D[ia, 0] - ref["start"][ib]))) * 1000, 3)
            out["max_dt_stop_ms"] = round(float(np.max(np.abs(D[ia, 2] - ref["stop"][ib]))) * 1000, 3)
            dv = np.abs(D[ia, 3:6] - ref["values"][ib])
            out["max_dz_peak"] = round(float(np.nanmax(dv[:, 1])), 6)
            out["max_dz_end"] = round(float(np.nanmax(dv[:, 2])), 6)
    return out


def replay(sdir: Path, script: str, version: str, threshold=None, emg_override=None, wrapper: str = "2024-06"):
    """Re-run the lab detection of one session from its own files.
    script 'lab' = detect_delta_waves (NREM, CleanLFP [6 10] +-0.5 s, EMG gate, stored threshold);
    script 'user' = pre_Ephys_pipline.m (whole session, CleanLFP [6 Inf], no gate). Its CleanLFP padding is the
    neurocode one (+-0.5 s, from 2022-10-13), not the codebook copy's +-2 s: +-0.5 s reproduces the stored
    badIntervals and events exactly (PPP4 d11, PPP7 d7), +-2 s does not."""
    base = sdir.name
    ref = load_deltas(sdir / f"{base}.deltaWaves.events.mat")
    nch, fs = load_session_meta(sdir)
    x = sd.load_channels(str(sdir / f"{base}.lfp"), nch, [ref["channel0"] + 1])[:, 0]
    if script == "lab":
        thr = threshold if threshold is not None else (ref["threshold"] if ref["threshold"] is not None else 3.0)
        emg_thr = ref["emg_thr"] if emg_override is None else emg_override
        D, D0, info = detect(x, fs, nrem=load_nrem(sdir / f"{base}.SleepState.states.mat"),
                             emg=load_emg(sdir / f"{base}.EMGFromLFP.LFP.mat"), emg_thr=emg_thr, threshold=thr,
                             version=version, ignore=ref.get("ignore"), wrapper=wrapper)
    else:
        thr = threshold if threshold is not None else (ref["threshold"] or 4.5)
        D, D0, info = detect(x, fs, nrem=None, emg=None, clean=(6.0, np.inf), around=(0.5, 0.1), threshold=thr,
                             version=version)
    res = dict(session=base, script=script, version=version, wrapper=wrapper if script == "lab" else None,
               channel0=ref["channel0"], threshold=thr,
               ref_kind=ref["kind"], ref_verify=ref.get("verify"), **info, **compare(D, ref))
    return res, D, ref


# ------------------------------------------------------------------------------------------ cohort-3 channel scan
UV_PER_BIT = 0.195  # Intan RHD
HF_BAND = (250.0, 450.0)  # multi-unit proxy inside the 1250-Hz LFP (make_lfp low-passes at 450 Hz)
WIN_S = 1.0  # +- window of the event-triggered averages
DIP_S = 0.05  # +- window of the HF response at the delta peak (detect_delta_waves' verify_firing uses +-50 ms)
BASE_S = (-1.0, -0.6)  # baseline of both PETHs


def nrem_extract(lfp_path: str, nch: int, fs: float, nrem: np.ndarray, out_dir: Path):
    """One sequential pass over the .lfp: NREM samples of every channel -> channel-major int16 .npy + their 0-based
    sample index (time of sample k = (k + 1) / fs, as in the MATLAB code)."""
    mm = np.memmap(lfp_path, dtype=np.int16, mode="r")
    n = mm.size // nch
    mm = mm[: n * nch].reshape(n, nch)
    idx = np.flatnonzero(sd.in_intervals((np.arange(n) + 1) / fs, nrem))
    np.save(out_dir / "nrem_idx.npy", idx)
    X = np.lib.format.open_memmap(out_dir / "nrem_lfp.npy", mode="w+", dtype=np.int16, shape=(nch, idx.size))
    step, pos = 1 << 21, 0
    for i in range(0, n, step):
        sel = idx[(idx >= i) & (idx < i + step)]
        if sel.size:
            X[:, pos:pos + sel.size] = np.asarray(mm[sel]).T
            pos += sel.size
    X.flush()
    return idx.size


def _contiguous(pos: np.ndarray, idx: np.ndarray, w: int) -> np.ndarray:
    """Event positions whose +-w window lies inside one NREM bout (no join inside)."""
    ok = (pos - w >= 0) & (pos + w < idx.size)
    p = np.clip(pos, w, idx.size - w - 1)
    return ok & (idx[p + w] - idx[p - w] == 2 * w)


def hf_response(x: np.ndarray, pos: np.ndarray, fs: float, w: int):
    """z-scored log 250-450 Hz envelope (20-ms smoothing) of x, averaged at the event positions -> (PETH, dip), dip = mean
    within +-DIP_S of the peak minus the BASE_S baseline (negative = less high-frequency power = fewer spikes)."""
    from scipy.ndimage import uniform_filter1d
    sos = signal.butter(4, HF_BAND, btype="bandpass", fs=fs, output="sos")
    n = x.size
    env = np.abs(signal.hilbert(signal.sosfiltfilt(sos, x), N=next_fast_len(n))[:n])
    lg = np.log(uniform_filter1d(env, int(0.02 * fs)) + 1e-9)
    lg = (lg - lg.mean()) / lg.std()
    lag = np.arange(-w, w + 1) / fs
    if not pos.size:
        return np.full(lag.size, np.nan), np.nan
    peth = np.zeros(lag.size)
    for p in pos:
        peth += lg[p - w:p + w + 1]
    peth /= pos.size
    base = (lag >= BASE_S[0]) & (lag <= BASE_S[1])
    return peth, float(np.mean(peth[np.abs(lag) <= DIP_S]) - np.mean(peth[base]))


def scan_channel(job):
    """Detection + checks on one channel's NREM samples (worker; reads the .npy files written by scan()). The HF check
    runs on the common-average-referenced channel (car.npy = mean of the live channels; SF07's 250-450 Hz band is
    largely common mode) and, for comparison, on the channel as recorded."""
    tmp, ch, fs, nmax_lam = job
    X = np.load(tmp / "nrem_lfp.npy", mmap_mode="r")
    idx = np.load(tmp / "nrem_idx.npy", mmap_mode="r")
    t = (idx + 1) / fs
    tc, xc, bad, _ = clean_lfp(t, np.asarray(X[ch], float))
    D0 = find_delta_waves(tc, xc)
    D = D0[(D0[:, 4] - D0[:, 5]) > 3.0]
    f, P = signal.welch(xc, fs, nperseg=int(4 * fs))
    ratio = float(P[(f >= 1) & (f <= 6)].sum() / P[(f >= 1) & (f <= fs / 2 - 1)].sum())
    w = int(WIN_S * fs)
    lag = np.arange(-w, w + 1) / fs
    base = (lag >= BASE_S[0]) & (lag <= BASE_S[1])
    # event positions in the NREM array; keep windows inside one bout
    px = np.searchsorted(idx, np.round(D[:, 1] * fs).astype(np.int64) - 1)
    okx = _contiguous(px, np.asarray(idx), w)
    hf_peth, hf_dip = hf_response(np.asarray(X[ch], float) - np.load(tmp / "car.npy"), px[okx], fs, w)
    _, hf_dip_raw = hf_response(np.asarray(X[ch], float), px[okx], fs, w)
    sel = px[okx]
    if sel.size > nmax_lam:
        sel = sel[np.linspace(0, sel.size - 1, nmax_lam).astype(int)]
    lam = np.zeros((X.shape[0], lag.size))
    for p in sel:
        lam += X[:, p - w:p + w + 1]
    lam = lam / max(sel.size, 1) * UV_PER_BIT
    lam -= lam[:, base].mean(axis=1, keepdims=True)
    dur_min = tc.size / fs / 60
    return dict(col=int(ch), n_events=int(D.shape[0]), rate_per_min=D.shape[0] / dur_min, nrem_used_min=dur_min,
                bad_frac=float(bad.mean()), amp_med=float(np.median(D[:, 4] - D[:, 5])) if D.size else np.nan,
                dur_med_ms=float(np.median(D[:, 2] - D[:, 0]) * 1000) if D.size else np.nan, delta_ratio=ratio,
                hf_dip_z=hf_dip, hf_dip_raw_z=hf_dip_raw, n_peth=int(okx.sum()), n_lam=int(sel.size),
                hf_peth=hf_peth.astype(np.float32), lam=lam.astype(np.float32), peaks_s=D[:, 1].astype(np.float64),
                deltas=D.astype(np.float64))


def propose(rows: list[dict], groups, skip, dip_max: float = -0.5, min_events: int = 100):
    """Per shank: among live sites whose HF power drops at the delta peak (<= dip_max z, the DOWN-state check) with
    >= min_events events, the largest NREM 1-6 Hz power share (detect_delta_waves' channel rule)."""
    by = {r["col"]: r for r in rows}
    out = {}
    for gi, g in enumerate(groups, 1):
        ok = [c for c in g if c not in skip and by[c]["hf_dip_z"] <= dip_max and by[c]["n_events"] >= min_events]
        out[gi] = max(ok, key=lambda c: by[c]["delta_ratio"]) if ok else None
    return out


def plot_scan(rows, groups, skip, prop, title, png1, png2):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    by = {r["col"]: r for r in rows}
    ng = len(groups)
    fig, ax = plt.subplots(3, ng, figsize=(3.4 * ng, 8.5), sharey="row", squeeze=False)
    for gi, g in enumerate(groups):
        depth = np.arange(1, len(g) + 1)
        for k, (key, lab) in enumerate((("delta_ratio", "NREM 1-6 Hz power share"), ("rate_per_min", "delta waves / NREM min"),
                                         ("hf_dip_z", "HF (250-450 Hz, CAR) at peak, z"))):
            v = np.array([by[c][key] for c in g], float)
            live = np.array([c not in skip for c in g])
            a = ax[k, gi]
            a.plot(v, depth, "-", color="0.6", lw=1)
            a.plot(v[live], depth[live], "o", color="k", ms=4)
            a.plot(v[~live], depth[~live], "x", color="r", ms=6)
            if prop.get(gi + 1) is not None:
                j = g.index(prop[gi + 1])
                a.plot(v[j], depth[j], "o", mfc="none", mec="tab:orange", ms=11, mew=2)
            if key == "hf_dip_z":
                a.axvline(-0.5, color="tab:orange", ls=":", lw=1)
                a.axvline(0, color="0.8", lw=0.8)
            a.set_ylim(len(g) + 0.5, 0.5)
            a.set_xlabel(lab, fontsize=8)
            if gi == 0:
                a.set_ylabel("site (1 = top)")
            if k == 0:
                a.set_title(f"shank {gi + 1}" + (f" - proposed col {prop[gi + 1]}" if prop.get(gi + 1) is not None else " - none"), fontsize=9)
            for j, c in enumerate(g):
                a.annotate(str(c), (v[j], depth[j]), fontsize=6, color="0.4", xytext=(3, 0), textcoords="offset points")
    fig.suptitle(title + "\nx = skipped column; orange circle = proposal (HF dip <= -0.5 z, >= 100 events, max 1-6 Hz share)", fontsize=9)
    fig.tight_layout()
    fig.savefig(png1, dpi=110)
    plt.close(fig)
    lag = np.linspace(-WIN_S, WIN_S, rows[0]["hf_peth"].size)
    fig, ax = plt.subplots(2, ng, figsize=(3.4 * ng, 8), squeeze=False, gridspec_kw=dict(height_ratios=[3, 1]))
    for gi, g in enumerate(groups):
        c = prop.get(gi + 1)
        if c is None:
            c = max([x for x in g if x not in skip], key=lambda x: by[x]["n_events"])
        r = by[c]
        live = [x for x in g if x not in skip]
        L = r["lam"][live]
        vmax = np.nanpercentile(np.abs(L), 99)
        a = ax[0, gi]
        a.imshow(L, aspect="auto", cmap="RdBu_r", vmin=-vmax, vmax=vmax, extent=[-WIN_S, WIN_S, len(live) + 0.5, 0.5])
        a.set_yticks(np.arange(1, len(live) + 1))
        a.set_yticklabels([str(x) + ("*" if x == c else "") for x in live], fontsize=6)
        a.set_xlim(-0.6, 0.6)
        a.set_title(f"shank {gi + 1}: LFP at col {c}'s delta peaks\n(n={r['n_lam']}, red +, blue -, +-{vmax:.0f} uV)", fontsize=8)
        a.set_xlabel("s")
        b = ax[1, gi]
        b.plot(lag, r["hf_peth"], "k", lw=1)
        b.axvspan(-DIP_S, DIP_S, color="tab:orange", alpha=0.2)
        b.set_xlim(-0.6, 0.6)
        b.set_title(f"col {c} HF power (CAR, z), dip {r['hf_dip_z']:.2f}", fontsize=8)
    fig.suptitle(title, fontsize=9)
    fig.tight_layout()
    fig.savefig(png2, dpi=110)
    plt.close(fig)


def scan(lfp: str, states: str, xml: str, out: Path, label: str, workers: int = 8, nmax_lam: int = 2000):
    import shutil
    from concurrent.futures import ProcessPoolExecutor
    import swr_layer_order as slo
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads(Path(lfp + ".json").read_text())
    nch, fs = int(meta["n_channels"]), float(meta["fs_out"])
    groups, skip = slo.read_groups(Path(xml))
    nrem = load_nrem(states)
    tmp = out / f"_tmp_{label}"
    tmp.mkdir(exist_ok=True)
    n_nrem = nrem_extract(lfp, nch, fs, nrem, tmp)
    if n_nrem < 10 * 60 * fs:
        shutil.rmtree(tmp)
        info = dict(label=label, lfp=lfp, states=states, nrem_min=n_nrem / fs / 60, skipped="< 10 min NREM")
        (out / f"{label}_delta_scan.json").write_text(json.dumps(info, indent=1))
        return info
    X = np.load(tmp / "nrem_lfp.npy", mmap_mode="r")
    live = [c for c in range(nch) if c not in skip]
    car = np.empty(X.shape[1], np.float32)
    for i in range(0, X.shape[1], 1 << 22):
        car[i:i + (1 << 22)] = X[live, i:i + (1 << 22)].astype(np.float32).mean(axis=0)
    np.save(tmp / "car.npy", car)
    del X
    with ProcessPoolExecutor(workers) as ex:
        rows = list(ex.map(scan_channel, [(tmp, c, fs, nmax_lam) for c in range(nch)]))
    shutil.rmtree(tmp)
    prop = propose(rows, groups, skip)
    depth = {c: (gi + 1, g.index(c) + 1) for gi, g in enumerate(groups) for c in g}
    keys = ["col", "n_events", "rate_per_min", "nrem_used_min", "bad_frac", "amp_med", "dur_med_ms", "delta_ratio",
            "hf_dip_z", "hf_dip_raw_z", "n_peth", "n_lam"]
    lines = ["shank,site_from_top,skip,proposed," + ",".join(keys)]
    for r in sorted(rows, key=lambda r: depth.get(r["col"], (99, 99))):
        s, d = depth.get(r["col"], (0, 0))
        lines.append(f"{s},{d},{int(r['col'] in skip)},{int(prop.get(s) == r['col'])}," +
                     ",".join(f"{r[k]:.4g}" if isinstance(r[k], float) else str(r[k]) for k in keys))
    (out / f"{label}_delta_scan.csv").write_text("\n".join(lines) + "\n")
    np.savez_compressed(out / f"{label}_delta_scan.npz", cols=np.array([r["col"] for r in rows]),
                        hf_peth=np.stack([r["hf_peth"] for r in rows]), lam=np.stack([r["lam"] for r in rows]),
                        **{f"deltas_{r['col']}": r["deltas"] for r in rows})
    info = dict(label=label, lfp=lfp, states=states, xml=xml, nrem_min=n_nrem / fs / 60, proposal=prop, fs=fs,
                emg_gate="none (scorer EMG = IMU; NREM from imu_remclean)", hf_band=HF_BAND,
                hf_reference="common average of the live channels (hf_dip_raw_z = as recorded)", git=_git())
    (out / f"{label}_delta_scan.json").write_text(json.dumps(info, indent=1))
    plot_scan(rows, groups, skip, prop, f"{label}  (NREM {n_nrem / fs / 60:.0f} min)", out / f"{label}_delta_scan.png",
              out / f"{label}_delta_profile.png")
    return info


VERIFY = dict(peak_s=0.05, pre_s=(-1.0, -0.4), min_rate_hz=1.0, min_pre_spikes=10, ratio_max=0.5)


def verify_events(D: np.ndarray, spikes: list, rate_hz: np.ndarray, live, bouts_s: np.ndarray, p=VERIFY):
    """Per-event DOWN-state check with multi-unit threshold crossings (`mua_nrem.py`), replacing verify_firing's sorted
    units: spikes within +-peak_s of the delta peak vs the pre_s window, summed over the MUA sites = live sites with
    >= min_rate_hz NREM firing whose firing does not RISE at the delta peaks (session sum; excludes e.g. hippocampal
    sites that fire more there). ratio = peak rate / pre rate; p = Poisson P(K <= k_peak | pre rate). Events with fewer
    than min_pre_spikes pre-window spikes, or windows outside one NREM bout, are untestable (NaN)."""
    from scipy.stats import poisson
    pk = 16 * (np.round(D[:, 1] * 1250.0).astype(np.int64) - 1)  # amplifier sample of each peak
    fs = 20000.0
    win = [(-p["peak_s"], p["peak_s"]), p["pre_s"]]
    lo, hi = D[:, 1] + p["pre_s"][0], D[:, 1] + p["peak_s"]
    b0 = np.searchsorted(bouts_s[:, 0], lo, "right") - 1
    ok = (b0 >= 0) & (b0 == np.searchsorted(bouts_s[:, 0], hi, "right") - 1)
    ok &= (lo >= bouts_s[np.clip(b0, 0, None), 0]) & (hi <= bouts_s[np.clip(b0, 0, None), 1])

    def counts(c):
        st = spikes[c]
        return [np.searchsorted(st, pk + int(b * fs), "left") - np.searchsorted(st, pk + int(a * fs), "left") for a, b in win]

    K = {c: counts(c) for c in live if rate_hz[c] >= p["min_rate_hz"]}
    dur_pk, dur_pre = 2 * p["peak_s"], p["pre_s"][1] - p["pre_s"][0]
    site_ratio = {c: (k[0][ok].sum() / dur_pk) / max(k[1][ok].sum() / dur_pre, 1e-9) for c, k in K.items()}
    sites = sorted(c for c, r in site_ratio.items() if r < 1.0)
    kp = np.sum([K[c][0] for c in sites], axis=0) if sites else np.zeros(D.shape[0])
    kb = np.sum([K[c][1] for c in sites], axis=0) if sites else np.zeros(D.shape[0])
    testable = ok & (kb >= p["min_pre_spikes"])
    ratio = np.where(testable, (kp / dur_pk) / np.maximum(kb / dur_pre, 1e-9), np.nan)
    pval = np.where(testable, poisson.cdf(kp, kb * dur_pk / dur_pre), np.nan)
    info = dict(sites=sites, site_ratio={int(c): round(float(r), 3) for c, r in site_ratio.items()},
                site_rate_hz={int(c): round(float(rate_hz[c]), 2) for c in K}, n_events=int(D.shape[0]),
                n_testable=int(testable.sum()), params=p,
                frac_verified={str(t): round(float(np.mean(ratio[testable] <= t)), 3) for t in (0.3, 0.5, 0.7)})
    return dict(k_peak=kp, k_pre=kb, ratio=ratio, p=pval, testable=testable,
                verified=testable & (ratio <= p["ratio_max"])), info


def _git():
    import subprocess
    try:
        return subprocess.run(["git", "-C", str(Path(__file__).resolve().parent), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------------------------------------------- selftest
def selftest() -> bool:
    rng = np.random.default_rng(3)
    ok = True

    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS " if cond else "FAIL ") + name)

    fs = 1250.0
    # 1 MATLAB primitives
    check("runs = FindInterval", np.array_equal(runs(np.array([1, 1, 0, 1, 0, 0, 1], bool)), [[0, 1], [3, 3], [6, 6]]))
    check("consolidate merges touching", np.array_equal(consolidate(np.array([[0, 1], [1, 2], [3, 4.0]])), [[0, 2], [3, 4]]))
    up, down = zero_crossings(np.array([-1, 1, 0, -1, -2, 3.0]))
    check("zero crossings strict, index before", np.array_equal(up, [0, 4]) and down.size == 0)
    # 2 FilterLFP: 3 Hz passes, 0.1 Hz and 30 Hz are removed; gaps are bridged on the grid
    t = (np.arange(int(60 * fs)) + 1) / fs
    s3, s01, s30 = np.sin(2 * np.pi * 3 * t), np.sin(2 * np.pi * 0.1 * t), np.sin(2 * np.pi * 30 * t)
    f = filter_lfp(t, s3 + s01 + s30, (0.5, 9.0))
    mid = slice(int(10 * fs), int(50 * fs))
    check("FilterLFP 0.5-9 keeps 3 Hz (rms err < 0.1)", np.sqrt(np.mean((f[mid] - s3[mid]) ** 2)) < 0.1)
    keep = np.ones(t.size, bool)
    keep[int(20 * fs):int(25 * fs)] = False
    fg = filter_lfp(t[keep], (s3 + s30)[keep], (0.0, 9.0))
    check("FilterLFP on gapped samples returns one value per sample", fg.size == keep.sum() and np.isfinite(fg).all())
    # 3 synthetic delta waves: positive 1-cycle bumps (sigma 60 ms) in pink-ish noise
    n = int(600 * fs)
    noise = np.cumsum(rng.standard_normal(n))
    noise = signal.filtfilt(*signal.butter(2, 1.0 / (fs / 2), "high"), noise)
    noise = noise / noise.std()
    pk = np.sort(rng.choice(np.arange(int(5 * fs), n - int(5 * fs), int(2.5 * fs)), 150, replace=False))
    tt = np.arange(-int(0.6 * fs), int(0.6 * fs) + 1) / fs
    bump = np.exp(-tt ** 2 / (2 * 0.06 ** 2)) - 0.35 * np.exp(-(np.abs(tt) - 0.22) ** 2 / (2 * 0.07 ** 2))
    x = noise.copy()
    for p in pk:
        x[p - tt.size // 2:p + tt.size // 2 + 1] += 6 * bump
    D, D0, info = detect(x, fs, threshold=3.0)
    ia, ib = sd.match_peaks(D[:, 1], (pk + 1) / fs, 0.05)
    check(f"synthetic recall >= 0.9 ({ia.size}/{pk.size})", ia.size >= 0.9 * pk.size)
    check(f"synthetic precision >= 0.8 ({ia.size}/{D.shape[0]})", ia.size >= 0.8 * D.shape[0])
    check("durations within 150-650 ms", np.all((D[:, 2] - D[:, 0] >= 0.15) & (D[:, 2] - D[:, 0] <= 0.65)))
    check("peaks at the bump centre (median |dt| < 10 ms)",
          np.median(np.abs(D[ia, 1] - (pk[ib] + 1) / fs)) < 0.010)
    # 4 CleanLFP interpolates an artefact and reports its padded interval
    y = noise.copy()
    y[int(100 * fs)] = 80.0
    tc, yc, bad, iv = clean_lfp(t=(np.arange(n) + 1) / fs, x=y)
    check("CleanLFP: one interval, +-0.5 s around the artefact", iv.shape == (1, 2) and abs((iv[0, 1] - iv[0, 0]) - 1.0) < 0.01)
    check("CleanLFP: artefact replaced, sample count kept", tc.size == n and np.abs(yc).max() < 20)
    # 4b per-event MUA verification: silence at half of the events, an "excited" site that must be left out
    fsa, T = 20000.0, 600.0
    tpk = np.arange(5.0, T - 5.0, 2.0)
    Dv = np.column_stack([tpk - 0.15, tpk, tpk + 0.15, np.zeros((tpk.size, 3))])
    down = np.zeros(tpk.size, bool)
    down[::2] = True
    sp = []
    for c in range(4):
        s = np.sort(rng.uniform(0, T, int(60 * T)))  # 60 Hz per site
        if c < 3:
            for t in tpk[down]:
                s = s[(s < t - 0.08) | (s > t + 0.08)]
        else:  # excited at every peak
            s = np.sort(np.concatenate([s, np.concatenate([rng.uniform(t - 0.05, t + 0.05, 20) for t in tpk])]))
        sp.append(np.round(s * fsa).astype(np.int64))
    rv, iv = verify_events(Dv, sp, np.array([60.0] * 4), [0, 1, 2, 3], np.array([[0.0, T]]))
    check("verify: excited site excluded", iv["sites"] == [0, 1, 2])
    check(f"verify: DOWN events kept ({rv['verified'][down].mean():.2f}), others not ({rv['verified'][~down].mean():.2f})",
          rv["verified"][down].mean() > 0.95 and rv["verified"][~down].mean() < 0.05)
    # 5 restrict is inclusive
    tt5 = (np.arange(10) + 1) / 10
    check("in_intervals inclusive", np.array_equal(np.flatnonzero(sd.in_intervals(tt5, np.array([[0.2, 0.4]]))), [1, 2, 3]))
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("replay", help="re-run a lab session's delta detection and compare with its events file")
    r.add_argument("--session-dir", required=True, nargs="+")
    r.add_argument("--script", choices=["lab", "user", "auto"], default="auto",
                   help="lab = detect_delta_waves.m, user = pre_Ephys_pipline.m; auto = from the events file")
    r.add_argument("--version", choices=["current", "2017", "both"], default="current")
    r.add_argument("--threshold", type=float, default=None)
    r.add_argument("--wrapper", choices=WRAPPERS, default="2024-06",
                   help="detect_delta_waves version (only matters with ignore_intervals); the lab files on hand "
                        "predate 2025-09")
    r.add_argument("--out", default=None, help="append one JSON line per run")
    c = sub.add_parser("scan", help="cohort-3 session: detection + DOWN-state check on every channel, proposal per shank")
    c.add_argument("--lfp", required=True, help="<session>.lfp with its .lfp.json sidecar")
    c.add_argument("--states", required=True, help="<session>.SleepState.states.mat (final scoring)")
    c.add_argument("--xml", required=True, help="final channel-map XML (group order = top -> tip)")
    c.add_argument("--out", required=True)
    c.add_argument("--label", required=True, help="e.g. SF11_5_20260906_080735.254")
    c.add_argument("--workers", type=int, default=8)
    v = sub.add_parser("verify", help="per-event DOWN-state check of a scan's events with mua_nrem.py spikes")
    v.add_argument("--scan-npz", required=True)
    v.add_argument("--ref-col", type=int, required=True)
    v.add_argument("--mua-npz", required=True)
    v.add_argument("--out", required=True, help="output stem: <stem>.csv (one row per event) + <stem>.json")
    a = ap.parse_args()
    if a.cmd == "verify":
        import mua_nrem
        D = np.load(a.scan_npz)[f"deltas_{a.ref_col}"]
        spikes, m = mua_nrem.load(a.mua_npz)
        bouts = np.load(a.mua_npz)["bouts_s"]
        r, info = verify_events(D, spikes, m["rate_hz"], [int(c) for c in m["live"]], bouts)
        hdr = "t_start,t_peak,t_end,z_start,z_peak,z_end,amp_z,k_peak,k_pre,mua_ratio,mua_p,testable,verified"
        rows = [",".join([f"{x:.4f}" for x in d[:6]] + [f"{d[4] - d[5]:.3f}", str(int(kp)), str(int(kb)), f"{ra:.4f}",
                          f"{pv:.3g}", str(int(t)), str(int(vv))])
                for d, kp, kb, ra, pv, t, vv in zip(D, r["k_peak"], r["k_pre"], r["ratio"], r["p"], r["testable"], r["verified"])]
        Path(a.out + ".csv").write_text(hdr + "\n" + "\n".join(rows) + "\n")
        info.update(scan_npz=a.scan_npz, ref_col=a.ref_col, mua_npz=a.mua_npz, git=_git())
        Path(a.out + ".json").write_text(json.dumps(info, indent=1))
        print(json.dumps({k: info[k] for k in ("sites", "n_events", "n_testable", "frac_verified")}))
        return
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    if a.cmd == "replay":
        for sdir in map(Path, a.session_dir):
            script = a.script
            if script == "auto":
                script = "lab" if load_deltas(sdir / f"{sdir.name}.deltaWaves.events.mat")["kind"] == "lab" else "user"
            for v in (["current", "2017"] if a.version == "both" else [a.version]):
                try:
                    res = replay(sdir, script, v, a.threshold, wrapper=a.wrapper)[0]
                except Exception as e:  # noqa: BLE001
                    res = dict(session=sdir.name, script=script, version=v, error=repr(e))
                print(json.dumps(res))
                if a.out:
                    with open(a.out, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(res) + "\n")
        return
    if a.cmd == "scan":
        print(json.dumps(scan(a.lfp, a.states, a.xml, Path(a.out), a.label, a.workers), indent=1))
        return
    ap.print_help()


if __name__ == "__main__":
    main()
