"""Faithful Python port of the lab's DetectSWR.m (neurocode/SharpWaveRipples, 2025-10 version = the 2023-01 version used
for the PPP sessions; `version="2022-10"` reproduces the older ripple-boundary arithmetic used for HYC3 day2).

DetectSWR(Channels=[ripple, sharp-wave, noise], ...) in four steps, each a function here:
  features()    swDiff  = DoG(2-50 Hz)(ripple ch) - DoG(2-50 Hz)(sharp-wave ch)
                ripPower = smoothed |DoG(80-250 Hz)| of the ripple ch minus the same of the noise ch
                (Eran Stark's Gaussian FIRs, `makegausslpfir` + `firfilt`, reproduced exactly)
  candidates()  the swDiff maximum of every non-overlapping WinSize window (edge maxima must be 3-point maxima)
                + the ripPower maximum within +-WinSize/2 of it
  split()       k-means (k = 2) on the raw (swDiff, ripPower) pairs, the smaller cluster = SWR; then
                swDiff > 10th percentile of that cluster and ripPower > median of the other (MATLAB prctile)
                -> or, in the user's `check` mode, the cluster the user scored by hand (DetectSWR_manual_scoring.mat
                `idx1`), with no percentile thresholds and useSPW = false
  localize()    per candidate, +-Ns_chk s around it: peak > median + 2.5 SD (sharp wave only if useSPW; ripple always),
                inter-candidate interval >= minIsi, not (ripple < minDurRP AND sharp wave < minDurSW), sharp wave
                <= maxDurSW (if useSPW); bounds where the features fall below median + 0.5 SD
  troughs()     peak = LFP trough within 10 ms of the max of the fir1(80-250 Hz) envelope; events whose trough falls
                outside their bounds are dropped; unique by start, then by peak

Times follow DetectSWR: sample index k (1-based) <-> k / SR seconds. Known MATLAB behaviours kept on purpose and
listed in `DETECTSWR_NOTES`. The LFP is read through a numpy memmap of the given .lfp (int16, interleaved); nothing is
written next to it.

  python ephys/swr_detect.py --selftest
  python ephys/swr_detect.py check-features --lfp X.lfp --nchan N --channels R S Z --scoring DetectSWR_manual_scoring.mat
  python ephys/swr_detect.py replay --lfp X.lfp --nchan N --channels R S Z --scoring ... [--ripples X.ripples.events.mat]
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field

import numpy as np
from scipy import signal
from scipy.ndimage import maximum_filter1d

DETECTSWR_NOTES = [
    "k-means runs on unscaled features; the smaller cluster is called SWR (artifacts can win it)",
    "check mode forces useSPW = false: no local sharp-wave threshold, no maximum sharp-wave duration, event bounds = "
    "union of the sharp-wave and ripple intervals, no percentile thresholds",
    "the duration rule rejects only when BOTH the ripple and the sharp wave are short",
    "the minimum interval is measured to the previous CANDIDATE (accepted or not); the last candidate is never "
    "tested",
    "with several Epochs MATLAB re-runs k-means and the localisation once per epoch on the accumulated candidates; the "
    "final result equals one pass over all candidates, which is what this port does",
    "local statistics use +-Ns_chk s that include the event and its neighbours (dense ripples inflate the SD)",
]


@dataclass
class Params:
    swBP: tuple = (2.0, 50.0)
    ripBP: tuple = (80.0, 250.0)
    per_thresswD: float = 10.0
    per_thresRip: float = 50.0
    WinSize: float = 40.0  # ms
    Ns_chk: float = 5.0  # s
    thresSDswD: tuple = (0.5, 2.5)
    thresSDrip: tuple = (0.5, 2.5)
    minIsi: float = 0.05
    minDurSW: float = 0.02
    maxDurSW: float = 0.5
    minDurRP: float = 0.025
    useSPW: bool = True
    version: str = "2025-10"  # or "2022-10" (HYC3 day2)


# --------------------------------------------------------------------------------------------- Eran Stark's filters
def makegausslpfir(Fc: float, Fs: float, s: float = 4) -> np.ndarray:
    s = max(s, 3)
    sd = Fs / (2 * np.pi * Fc)
    x = np.arange(-math.ceil(s * sd), math.ceil(s * sd) + 1, dtype=float)
    g = 1 / (2 * np.pi * sd) * np.exp(-(x ** 2) / 2 / sd ** 2)
    return g / g.sum()


def firfilt(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    """MATLAB firfilt: reflect C samples at both ends, causal FIR, take the centred part (zero phase)."""
    x = np.asarray(x, dtype=float)
    one = x.ndim == 1
    if one:
        x = x[:, None]
    C = len(w)
    n = x.shape[0]
    if C > n:
        return np.full(x.shape if not one else (n,), np.nan)
    D = math.ceil(C / 2) - 1
    pad = np.concatenate([x[:C][::-1], x, x[-C:][::-1]], axis=0)
    y = np.empty_like(x)
    for j in range(x.shape[1]):
        full = signal.oaconvolve(pad[:, j], w, mode="full")
        y[:, j] = full[C + D: C + D + n]
    return y[:, 0] if one else y


# ------------------------------------------------------------------------------------------------------- features
def load_channels(lfp_path: str, nchan: int, channels_1b) -> np.ndarray:
    mm = np.memmap(lfp_path, dtype=np.int16, mode="r")
    n = mm.size // nchan
    mm = mm[: n * nchan].reshape(n, nchan)
    cols = [int(c) - 1 for c in channels_1b]
    out = np.empty((n, len(cols)), dtype=np.int16)
    step = 1 << 20
    for i in range(0, n, step):
        out[i:i + step] = mm[i:i + step, cols]
    return out


def features(lfp: np.ndarray, SR: float, p: Params):
    """lfp: (N, 2 or 3) int16 [ripple, sharp wave(, noise)] -> swDiff, ripPower0 (float64, length N)."""
    hSw1 = makegausslpfir(p.swBP[0], SR, 6)
    hSw2 = makegausslpfir(p.swBP[1], SR, 6)
    low = firfilt(lfp[:, :2], hSw2)
    low = low - firfilt(low, hSw1)
    swDiff = low[:, 0] - low[:, 1]
    hRip1 = makegausslpfir(p.ripBP[0], SR, 6)
    hRip2 = makegausslpfir(p.ripBP[1], SR, 6)
    powerWin = makegausslpfir(1 / (np.pi / np.mean(p.ripBP)), SR, 6)

    def env(x):
        r = firfilt(x, hRip2)
        r = r - firfilt(r, hRip1)
        return firfilt(np.abs(r), powerWin)

    if lfp.shape[1] == 2:
        mu = lfp.astype(float).mean(axis=1, keepdims=True)
        mu16 = np.sign(mu) * np.floor(np.abs(mu) + 0.5)  # int16(): round half away from zero
        lfpM = np.clip(lfp.astype(np.int32) - mu16.astype(np.int32), -32768, 32767).astype(float)  # int16 saturates
        ripPower0 = np.max(np.column_stack([env(lfpM[:, 0]), env(lfpM[:, 1])]), axis=1)
    else:
        ripPower0 = env(lfp[:, 0]) - env(lfp[:, 2])
    return swDiff, ripPower0


def propagate_clicks(swDiffAll, ripPowerAll, scores, bad):
    """DetectSWR_check_helper: every candidate takes the score of the nearest clicked candidate in z-space (mean/SD over
    non-bad candidates); selected = estimate > 0.1; idx1 = selected & ~bad."""
    X = np.column_stack([swDiffAll, ripPowerAll]).astype(float)
    ok = ~bad
    z = (X - X[ok].mean(0)) / X[ok].std(0, ddof=1)
    sc = np.flatnonzero(~np.isnan(scores))
    from scipy.spatial import cKDTree
    _, nn = cKDTree(z[sc]).query(z, k=1)
    est = scores[sc][nn]
    selected = est > 0.1
    return selected & ok, selected


def candidates(swDiff: np.ndarray, ripPower0: np.ndarray, SR: float, p: Params, epochs=None):
    """-> featureTs (1-based samples), swDiffAll, ripPowerAll; one pass over all epochs (see DETECTSWR_NOTES)."""
    N = swDiff.size
    W = int(math.floor(p.WinSize * SR / 1000))
    half = W // 2
    if epochs is None:
        epochs = np.array([[1 / SR, N / SR]])
    rp_max = maximum_filter1d(ripPower0, size=2 * half + 1, mode="nearest")
    ts_all = []
    for e0, e1 in np.atleast_2d(epochs):
        b0, b1 = int(math.floor(e0 * SR)), int(math.floor(e1 * SR))
        blocks = np.arange(b0, b1 + 1, W)
        nW = blocks.size - 1
        if nW < 1:
            continue
        seg = swDiff[b0 - 1: b0 - 1 + nW * W].reshape(nW, W)
        ind0 = np.argmax(seg, axis=1)  # 0-based, first maximum like MATLAB
        m = blocks[:-1] + ind0  # 1-based sample of the maximum
        keep = np.ones(nW, bool)
        edge = (ind0 == 0) | (ind0 == W - 1)
        bnd = edge & ((m == 1) | (m == N))
        keep &= ~bnd
        chk = edge & ~bnd
        mi = m[chk] - 1
        trip = np.column_stack([swDiff[mi - 1], swDiff[mi], swDiff[np.minimum(mi + 1, N - 1)]])
        keep[np.flatnonzero(chk)[np.argmax(trip, axis=1) != 1]] = False
        ts_all.append(m[keep])
    featureTs = np.concatenate(ts_all) if ts_all else np.zeros(0, int)
    return featureTs, swDiff[featureTs - 1], rp_max[featureTs - 1]


def prctile(x, q):
    return float(np.percentile(np.asarray(x, float), q, method="hazen"))  # MATLAB prctile


def split_kmeans(swDiffAll, ripPowerAll, seed=0):
    from sklearn.cluster import KMeans
    X = np.column_stack([swDiffAll, ripPowerAll])
    lab = KMeans(n_clusters=2, n_init=10, random_state=seed).fit_predict(X)
    idx1 = lab == 0 if np.sum(lab == 0) <= np.sum(lab == 1) else lab == 1
    return idx1, ~idx1


# ----------------------------------------------------------------------------------------------------- localise
@dataclass
class Localized:
    Ts: np.ndarray  # (n, 3) 1-based samples [peak, start, stop]
    SwMax: np.ndarray  # (n, 2) [z, fraction below]
    RipMax: np.ndarray
    cand_index: np.ndarray  # index into featureTs
    reasons: dict = field(default_factory=dict)


def localize(swDiff, ripPower0, featureTs, swDiffAll, ripPowerAll, SWRind, SR, p: Params) -> Localized:
    N = swDiff.size
    W = int(math.floor(p.WinSize * SR / 1000))
    half = W // 2
    bound = int(round(p.Ns_chk * SR))
    minDurSWs, minDurRPs, maxDurSWs = (int(math.floor(v * SR)) for v in (p.minDurSW, p.minDurRP, p.maxDurSW))
    SWRid = np.flatnonzero(SWRind)
    SWRs = featureTs[SWRid]
    excl = (SWRs - bound < 1) | (SWRs + bound > N)
    SWRid, SWRs = SWRid[~excl], SWRs[~excl]
    Nswr = SWRs.size
    SWR_diff = np.diff(np.concatenate([[0.0], SWRs / SR]))
    reasons = dict(boundary=int(excl.sum()), sw_local=0, rip_local=0, isi=0, short=0, sw_long=0, empty_bound=0)
    Ts, SwM, RpM, cidx = [], [], [], []
    for ii in range(Nswr):
        m = int(SWRs[ii])
        lo, hi = m - bound, m + bound  # 1-based inclusive
        sw_chk = swDiff[lo - 1: hi]
        Msw, SDsw = np.median(sw_chk), np.std(sw_chk, ddof=1)
        if p.useSPW and sw_chk[bound] < Msw + p.thresSDswD[1] * SDsw:
            reasons["sw_local"] += 1
            continue
        rp_chk = ripPower0[lo - 1: hi]
        Mrp, SDrp = np.median(rp_chk), np.std(rp_chk, ddof=1)
        ripMax = ripPowerAll[SWRid[ii]]
        if ripMax < Mrp + p.thresSDrip[1] * SDrp:
            reasons["rip_local"] += 1
            continue
        if ii < Nswr - 1 and SWR_diff[ii] < p.minIsi:
            reasons["isi"] += 1
            continue
        thr_sw = Msw + p.thresSDswD[0] * SDsw
        below = np.flatnonzero(sw_chk[: bound + 1] < thr_sw)
        after = np.flatnonzero(sw_chk[bound:] < thr_sw)
        thr_rp = Mrp + p.thresSDrip[0] * SDrp
        pk = rp_chk[bound - half: bound + half + 1]
        maxRpInd = int(np.argmax(pk)) + 1  # 1-based within potentialPeak
        st_part = rp_chk[: bound - half + maxRpInd]
        sp_from = bound - half + maxRpInd  # 1-based row where potentialStop starts
        sp_part = rp_chk[sp_from - 1:]
        b_rp = np.flatnonzero(st_part < thr_rp)
        a_rp = np.flatnonzero(sp_part < thr_rp)
        if below.size == 0 or after.size == 0 or b_rp.size == 0 or a_rp.size == 0:
            reasons["empty_bound"] += 1  # MATLAB would error here
            continue
        startSWR = int(below[-1]) + 1
        stopSWR = int(after[0]) + 1
        durSWR = (bound + 1 - startSWR) + stopSWR
        if p.version == "2022-10":
            startRP_l = int(b_rp[-1]) + 1
            stopRP_l = int(a_rp[0]) + 1
            durRP = (bound - half + maxRpInd - startRP_l) + stopRP_l
        else:
            startRP = lo + int(b_rp[-1])  # absolute 1-based sample
            stopRP = lo + (sp_from - 1) + int(a_rp[0])
            durRP = stopRP - startRP
        if durRP < minDurRPs and durSWR < minDurSWs:
            reasons["short"] += 1
            continue
        if durSWR > maxDurSWs and p.useSPW:
            reasons["sw_long"] += 1
            continue
        if p.useSPW:
            row = [m, m - (bound + 1 - startSWR), m + stopSWR - 1]
        elif p.version == "2022-10":
            row = [m, m - (bound + 1 - min(startSWR, startRP_l)), m + max(stopSWR, stopRP_l) - 1]
        else:
            row = [m, min(m - (bound + 1 - startSWR), startRP), max(m + stopSWR - 1, stopRP)]
        swMax = swDiffAll[SWRid[ii]]
        Ts.append(row)
        SwM.append([(swMax - Msw) / SDsw, np.sum(sw_chk < swMax) / (2 * bound + 1)])
        RpM.append([(ripMax - Mrp) / SDrp, np.sum(rp_chk < ripMax) / (2 * bound + 1)])
        cidx.append(SWRid[ii])
    z = np.zeros((0, 3), int)
    return Localized(np.array(Ts, int) if Ts else z, np.array(SwM) if SwM else np.zeros((0, 2)),
                     np.array(RpM) if RpM else np.zeros((0, 2)), np.array(cidx, int), reasons)


# -------------------------------------------------------------------------------------------------------- troughs
def fir1_bandpass(order: int, band, nyq: float) -> np.ndarray:
    return signal.firwin(order + 1, [band[0] / nyq, band[1] / nyq], pass_zero=False, window="hamming", scale=True)


def trough_context(lfp_rip: np.ndarray, SR: float, p: Params) -> dict:
    """The whole-channel products troughs() needs (computed once per session, reusable across candidate masks)."""
    nyq = SR / 2
    order = int(np.floor(4 * 2 * nyq / p.ripBP[0] + 0.5))  # MATLAB round(62.5) = 63
    b = fir1_bandpass(order, p.ripBP, nyq)
    lf = signal.filtfilt(b, [1.0], lfp_rip.astype(float), padtype="odd", padlen=3 * (len(b) - 1))
    envl = np.sqrt(np.abs(signal.savgol_filter(2 * lf * lf, 101, 4, mode="interp")))
    h = signal.hilbert(lf)
    return dict(envl=envl, amp=np.abs(h), unw=np.unwrap(np.angle(h)))


def troughs(lfp_rip: np.ndarray, loc: Localized, SR: float, p: Params, ctx: dict | None = None):
    """bz_Filter(fir1, order 4) + sgolay envelope -> trough peak, amplitude, frequency; drops troughs outside bounds."""
    ctx = ctx or trough_context(lfp_rip, SR, p)
    envl, amp, unw = ctx["envl"], ctx["amp"], ctx["unw"]
    N = lfp_rip.size
    # MATLAB round(imax-0.01*SR : imax+0.01*SR): colon steps of 1 from imax-12.5, rounded half away from zero
    steps = np.arange(int(math.floor(0.02 * SR + 1e-9)) + 1) - 0.01 * SR
    out_peak, out_amp, out_freq, keep = [], [], [], []
    for k, (pk, st, sp) in enumerate(loc.Ts):
        seg = envl[st - 1: sp]
        imax = st + int(np.argmax(seg))  # 1-based
        idx = np.floor(imax + steps + 0.5).astype(int)
        idx = idx[(idx >= 1) & (idx <= N)]
        imin = int(idx[int(np.argmin(lfp_rip[idx - 1]))])
        if not (st < imin < sp):
            continue
        keep.append(k)
        out_peak.append(imin)
        out_amp.append(amp[imin - 1])
        j = imin - 1

        def mf(c):  # MATLAB medfilt1(.,12) at 0-based c: median of x[c-6 .. c+5]
            a, z = max(c - 6, 0), min(c + 6, N)
            return np.median(unw[a:z])
        out_freq.append((mf(j + 1) - mf(j - 1)) * SR / 2 / (2 * np.pi))
    return np.array(keep, int), np.array(out_peak, int), np.array(out_amp), np.array(out_freq)


def assemble(loc: Localized, keep, peak, amp, freq, SR):
    Ts = loc.Ts[keep]
    ev = dict(start=Ts[:, 1] / SR, stop=Ts[:, 2] / SR, peak=peak / SR, amplitude=amp, frequency=freq,
              SwMax=loc.SwMax[keep, 0], RipMax=loc.RipMax[keep, 0], cand=loc.cand_index[keep])
    _, u = np.unique(ev["start"], return_index=True)
    ev = {k: v[u] for k, v in ev.items()}
    _, u = np.unique(ev["peak"], return_index=True)
    return {k: v[u] for k, v in ev.items()}


def events_from_mask(fe: dict, lfp_rip, SWRind, SR, p: Params, ctx=None):
    """Localise + troughs for a candidate mask on precomputed features `fe` (keys as returned by detect())."""
    loc = localize(fe["swDiff"], fe["ripPower0"], fe["featureTs"], fe["swDiffAll"], fe["ripPowerAll"], SWRind, SR, p)
    keep, peak, amp, freq = troughs(lfp_rip, loc, SR, p, ctx)
    return assemble(loc, keep, peak, amp, freq, SR), loc


def detect(lfp3: np.ndarray, SR: float, p: Params, SWRind=None, epochs=None, seed=0):
    """Full DetectSWR. SWRind=None -> automatic k-means path; else the given candidate mask (check-mode replay)."""
    swDiff, ripPower0 = features(lfp3, SR, p)
    featureTs, swA, rpA = candidates(swDiff, ripPower0, SR, p, epochs)
    info = dict(n_candidates=int(featureTs.size))
    if SWRind is None:
        idx1, idx2 = split_kmeans(swA, rpA, seed)
        thS, thR = prctile(swA[idx1], p.per_thresswD), prctile(rpA[idx2], p.per_thresRip)
        SWRind = idx1 & (swA > thS) & (rpA > thR)
        info.update(n_cluster=int(idx1.sum()), thresL_swD=thS, thresL_Rip=thR)
    loc = localize(swDiff, ripPower0, featureTs, swA, rpA, SWRind, SR, p)
    keep, peak, amp, freq = troughs(lfp3[:, 0], loc, SR, p)
    ev = assemble(loc, keep, peak, amp, freq, SR)
    info.update(n_selected=int(np.sum(SWRind)), n_localized=int(loc.Ts.shape[0]), n_events=int(ev["peak"].size),
                reasons=loc.reasons)
    return ev, info, dict(swDiff=swDiff, ripPower0=ripPower0, featureTs=featureTs, swDiffAll=swA, ripPowerAll=rpA)


def clean_lfp_intervals(x: np.ndarray, SR: float, thresholds=(8.0, 5.0), around=(0.5, 0.1)) -> np.ndarray:
    """neurocode CleanLFP (as called by DetectSWR_check_helper: thresholds [8 5], non-manual): intervals [s] where the
    z-scored LFP exceeds thresholds[0] (+-around[0]) or its sample-to-sample derivative exceeds thresholds[1]
    (+-around[1]); time of sample k (1-based) = k/SR."""
    x = np.asarray(x, float)
    z = (x - x.mean()) / x.std(ddof=1)
    d = np.append(np.diff(z), 0.0)
    out = []
    for mask, pad in ((np.abs(z) > thresholds[0], around[0]), (np.abs(d) > thresholds[1], around[1])):
        e = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
        s, f = np.flatnonzero(e == 1), np.flatnonzero(e == -1) - 1
        out.append(np.column_stack([(s + 1) / SR - pad, (f + 1) / SR + pad]))
    iv = np.concatenate(out) if out else np.zeros((0, 2))
    if iv.size == 0:
        return iv
    iv = iv[np.argsort(iv[:, 0])]
    merged = [iv[0].tolist()]
    for a, b in iv[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return np.array(merged)


def in_intervals(t: np.ndarray, iv: np.ndarray) -> np.ndarray:
    if iv.size == 0:
        return np.zeros(t.shape, bool)
    i = np.searchsorted(iv[:, 0], t, side="right") - 1
    return (i >= 0) & (t <= iv[np.clip(i, 0, None), 1])


# ---------------------------------------------------------------------------------------------------- comparisons
def load_scoring(path):
    import scipy.io as sio
    m = sio.loadmat(path, squeeze_me=True)
    return {k: np.asarray(v) for k, v in m.items() if not k.startswith("__")}


def load_ripples(path):
    import scipy.io as sio
    r = sio.loadmat(path, squeeze_me=True, struct_as_record=False)["ripples"]
    ts = np.atleast_2d(np.asarray(r.timestamps, float))
    out = dict(start=ts[:, 0], stop=ts[:, 1], peak=np.atleast_1d(np.asarray(r.peaks, float)))
    for k in ("flagged", "added"):
        out[k] = np.atleast_1d(np.asarray(getattr(r, k), float)) if k in r._fieldnames else np.zeros(0)
    return out


def match_peaks(a, b, tol):
    """Greedy one-to-one match of sorted peak times a, b within tol s -> (ia, ib)."""
    ia, ib = [], []
    j = 0
    for i, t in enumerate(a):
        while j < len(b) and b[j] < t - tol:
            j += 1
        if j < len(b) and abs(b[j] - t) <= tol:
            ia.append(i)
            ib.append(j)
            j += 1
    return np.array(ia, int), np.array(ib, int)


# ------------------------------------------------------------------------------------------------------- selftest
def selftest():
    rng = np.random.default_rng(1)
    ok = True

    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS " if cond else "FAIL ") + name)

    # 1 firfilt == explicit reflected convolution, and zero phase on a symmetric pulse
    x = rng.normal(size=5000)
    w = makegausslpfir(50, 1250, 6)
    C, D = len(w), math.ceil(len(w) / 2) - 1
    pad = np.concatenate([x[:C][::-1], x, x[-C:][::-1]])
    ref = signal.lfilter(w, 1, pad)[C + D: C + D + x.size]
    check("firfilt equals MATLAB filter() on the reflected signal", np.max(np.abs(firfilt(x, w) - ref)) < 1e-10)
    pulse = np.zeros(2001)
    pulse[1000] = 1
    y = firfilt(pulse, w)
    check("firfilt is zero-phase", int(np.argmax(y)) == 1000 and np.allclose(y[990:1000], y[1001:1011][::-1]))
    # 2 makegausslpfir lengths match the MATLAB support rule
    check("Gaussian FIR lengths 1195/49/11/31/47", [len(makegausslpfir(f, 1250, 6)) for f in (2, 50, 250, 80, 165 / np.pi)]
          == [1195, 49, 11, 31, 47])
    # 3 MATLAB prctile (midpoint rule)
    check("prctile hazen == MATLAB", abs(prctile([1, 2, 3, 4], 50) - 2.5) < 1e-12 and abs(prctile([1, 2, 3, 4], 10) - 1.0) < 1e-12)
    # 4 synthetic session: sharp-wave ripples are found, a broadband artifact on all channels is not
    SR, T = 1250.0, 120.0
    n = int(SR * T)
    t = np.arange(n) / SR
    base = rng.normal(0, 30, size=(n, 3))
    events = np.arange(5.0, 115.0, 2.3)
    for e in events:
        k = np.abs(t - e) < 0.04
        g = np.exp(-((t[k] - e) / 0.015) ** 2)
        base[k, 0] += 300 * g * np.sin(2 * np.pi * 170 * (t[k] - e))
        sw = -400 * np.exp(-((t[np.abs(t - e) < 0.1] - e) / 0.03) ** 2)
        base[np.abs(t - e) < 0.1, 1] += sw
    art = 61.0
    k = np.abs(t - art) < 0.05
    base[k, :] += rng.normal(0, 600, size=(k.sum(), 1))  # same on every channel
    lfp = np.clip(np.round(base), -32768, 32767).astype(np.int16)
    ev, info, _ = detect(lfp, SR, Params())
    ia, ib = match_peaks(np.sort(events), ev["peak"], 0.03)
    check(f"synthetic recall {ia.size}/{events.size}", ia.size >= 0.9 * events.size)
    check("artifact rejected by the noise channel", not np.any(np.abs(ev["peak"] - art) < 0.1))
    check("version 2022-10 runs", detect(lfp, SR, Params(version="2022-10"), SWRind=None)[1]["n_events"] > 0)
    print("SELFTEST", "PASS" if ok else "FAIL")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("check-features", "replay", "auto"):
        s = sub.add_parser(name)
        s.add_argument("--lfp", required=True)
        s.add_argument("--nchan", type=int, required=True)
        s.add_argument("--channels", type=int, nargs="+", required=True, help="1-based [ripple sharp-wave noise]")
        s.add_argument("--sr", type=float, default=1250.0)
        s.add_argument("--scoring")
        s.add_argument("--ripples")
        s.add_argument("--version", default="2025-10")
        s.add_argument("--winsize", type=float, default=40.0, help="ms")
        s.add_argument("--thresSDswD", type=float, nargs=2, default=(0.5, 2.5))
        s.add_argument("--thresSDrip", type=float, nargs=2, default=(0.5, 2.5))
        s.add_argument("--maxDurSW", type=float, default=0.5)
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    if not a.cmd:
        ap.print_help()
        return
    p = Params(version=a.version, WinSize=a.winsize, thresSDswD=tuple(a.thresSDswD), thresSDrip=tuple(a.thresSDrip),
               maxDurSW=a.maxDurSW)
    lfp3 = load_channels(a.lfp, a.nchan, a.channels)
    if a.cmd == "check-features":
        swDiff, rp0 = features(lfp3, a.sr, p)
        ts, sw, rp = candidates(swDiff, rp0, a.sr, p)
        sc = load_scoring(a.scoring)
        tm = np.round(sc["t"] * a.sr).astype(int)
        print(f"candidates python {ts.size}  matlab {tm.size}  identical samples {np.array_equal(ts, tm)}")
        if ts.size == tm.size:
            print(f"max |d swDiff| {np.max(np.abs(sw - sc['swDiffAll'])):.3e}  (scale {np.max(np.abs(sw)):.1f});"
                  f"  max |d ripPower| {np.max(np.abs(rp - sc['ripPowerAll'])):.3e}  (scale {np.max(np.abs(rp)):.1f})")
    elif a.cmd in ("replay", "auto"):
        SWRind = None
        if a.cmd == "replay":
            sc = load_scoring(a.scoring)
            SWRind = sc["idx1"].astype(bool)
            p.useSPW = False
        ev, info, _ = detect(lfp3, a.sr, p, SWRind=SWRind)
        print(info)
        if a.ripples:
            ref = load_ripples(a.ripples)
            ia, ib = match_peaks(np.sort(ref["peak"]), np.sort(ev["peak"]), 0.0005)
            print(f"reference {ref['peak'].size} events, python {ev['peak'].size}; peaks identical (<=0.5 ms): {ia.size}")


if __name__ == "__main__":
    main()
