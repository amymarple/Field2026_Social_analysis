"""EMG removal from multichannel LFP by ICA: a Python port of Weiwei Chen's EMG_removing toolbox (Sirota lab).

Source: Chen W. (2023) *Biophysics-based modeling and data analysis of local field potential signal*, dissertation,
LMU Munich, chapter 5 "EMG Artifacts Removing" (`Ref/Chen_Weiwei.pdf`), and its MATLAB toolbox
https://github.com/YY535/EMG_removing (commit 0ee8f0d, 2023-04-05): `EMG_Cluster.m`, `EMG_rm_long.m` (the 'hw' path,
the default), `util/whitensignal.m`, `util/SREaffineV.m`, `util/butfilter.m`, FastICA 2.5 defaults.

Idea: EMG reaches the probe by volume conduction from distant muscles, so along one shank its loading is flat (or
linear); a local event (ripple, gamma) is a dipole. Per shank:
  1. high-EMG samples: 5 sites, > 100 Hz, z-scored, pairwise products smoothed over 20 ms; ICA of (total variation across
     pairs, summed covariance) splits "common" from "structured"; EMG_thrd = common score > the 99th percentile of the
     non-heavy samples (`EMG_Cluster.m`);
  2. ICA (deflation, pow3) on the > 100 Hz data of those samples, then a second ICA of those sources on the AR(1)-whitened
     wide band (every 3rd sample);
  3. flatness of each component = 1 / residual norm of an affine fit of its unit-norm loading against the site position
     (`SREaffineV.m`); the toolbox removes the flattest component only when exactly one is > 10 and one is > 50 (else up
     to four retries with the threshold lowered by 5);
  4. EMG activity = the wide band projected on that component's unmixing vector, high-passed at
     `denoise_frequency_lowerbound` (the thesis recommends 20-30 Hz; here 30 Hz), ends zeroed at the first / last zero
     crossing; cleaned = x - EMG_au * As.

Deviations from the MATLAB toolbox (stated, deliberate):
  - sites are the shank's live sites in their XML depth order (the toolbox takes the group's channel numbers as the
    position, which equals depth only on probes numbered along the shank);
  - the 5 cluster sites are taken on the shank being cleaned (the toolbox takes file channels 3..n-3, i.e. its shank 1);
  - FastICA is scikit-learn's (deflation, cube = pow3, tol 1e-4, max_iter 1000), seeded;
  - line-noise removal is off (battery-powered wireless loggers; the toolbox's band is 50 Hz);
  - `clean_chunk` processes one chunk the caller chooses; the toolbox splits a session into <= 15-min periods at the
    midpoints of low-EMG stretches and takes the cluster percentile over the whole session.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
from scipy import signal

FS = 1250.0


def arburg(x: np.ndarray, order: int) -> np.ndarray:
    """Burg AR coefficients [1, a1, ..., ap] (MATLAB arburg)."""
    x = np.asarray(x, np.float64)
    ef, eb = x.copy(), x.copy()
    a = np.array([1.0])
    for _ in range(order):
        efp, ebp = ef[1:], eb[:-1]
        den = np.dot(efp, efp) + np.dot(ebp, ebp)
        k = -2.0 * np.dot(ebp, efp) / den if den > 0 else 0.0
        ef, eb = efp + k * ebp, ebp + k * efp
        a = np.r_[a, 0.0] + k * np.r_[a, 0.0][::-1]
    return a


def whiten(x: np.ndarray, ar: np.ndarray | None = None, order: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """WhitenSignal with CommonAR: the AR model of the first channel, applied causally (`filter`) to every channel."""
    if ar is None:
        ar = arburg(x[:, 0], order)
    return signal.lfilter(ar, [1.0], x, axis=0), ar


def butfilter(x: np.ndarray, order: int, wn: float, btype: str) -> np.ndarray:
    """MATLAB butter (b, a) + filtfilt (padding 3 * (filter length - 1))."""
    b, a = signal.butter(order, wn, btype=btype)
    return signal.filtfilt(b, a, x, axis=0, padlen=3 * (max(len(a), len(b)) - 1))


_DEV = None


def _device():
    """A CUDA device whose kernels actually run (a torch built for an older CUDA reports is_available() but fails on
    sm_120), else None."""
    global _DEV
    if _DEV is None:
        _DEV = False
        try:
            import torch
            if torch.cuda.is_available():
                (torch.ones(4, device="cuda") * 2).sum().item()
                _DEV = torch.device("cuda")
        except Exception:
            _DEV = False
    return _DEV or None


def fastica(X: np.ndarray, n_components: int | None = None, seed: int = 0, max_iter: int = 1000,
            eps: float = 1e-4) -> tuple[np.ndarray, np.ndarray]:
    """FastICA 2.5 defaults: PCA whitening to n_components, deflation, g = pow3, epsilon 1e-4, 1000 iterations, random
    start. X: samples x channels. Returns (A mixing ch x ic, W unmixing ic x ch), both for centred data.
    On a working CUDA device the iteration runs in torch (float32); otherwise in numpy (float64). A component that does
    not converge within max_iter is kept as it stands (FastICA 2.5 would restart it)."""
    X = np.asarray(X, np.float64)
    Xc = X - X.mean(0)
    C = (Xc.T @ Xc) / (len(Xc) - 1)
    ev, E = np.linalg.eigh(C)
    order = np.argsort(ev)[::-1]
    d = X.shape[1] if not n_components else min(int(n_components), X.shape[1])
    keep = order[:d]
    keep = keep[ev[keep] > ev.max() * 1e-12]
    D, E = ev[keep], E[:, keep]
    Vw = (E / np.sqrt(D)).T                     # whitening   (ic x ch)
    Vd = E * np.sqrt(D)                         # dewhitening (ch x ic)
    rng = np.random.default_rng(seed)
    k = len(D)
    dev = _device()
    if dev is not None:
        import torch
        Z = torch.as_tensor(Xc @ Vw.T, dtype=torch.float32, device=dev)
        B = torch.zeros((k, k), dtype=torch.float32, device=dev)
        n = Z.shape[0]
        for i in range(k):
            w = torch.as_tensor(rng.standard_normal(k), dtype=torch.float32, device=dev)
            w = w - B @ (B.T @ w)
            w = w / torch.linalg.norm(w)
            for _ in range(max_iter):
                w_old = w
                y = Z @ w
                w = (Z.T @ (y ** 3)) / n - 3.0 * w
                w = w - B @ (B.T @ w)
                w = w / torch.linalg.norm(w)
                if min(float(torch.linalg.norm(w - w_old)), float(torch.linalg.norm(w + w_old))) < eps:
                    break
            B[:, i] = w
        B = B.double().cpu().numpy()
    else:
        Z = Xc @ Vw.T
        B = np.zeros((k, k))
        n = len(Z)
        for i in range(k):
            w = rng.standard_normal(k)
            w -= B @ (B.T @ w)
            w /= np.linalg.norm(w)
            for _ in range(max_iter):
                w_old = w
                w = (Z.T @ ((Z @ w) ** 3)) / n - 3.0 * w
                w -= B @ (B.T @ w)
                w /= np.linalg.norm(w)
                if min(np.linalg.norm(w - w_old), np.linalg.norm(w + w_old)) < eps:
                    break
            B[:, i] = w
    A = Vd @ B
    W = B.T @ Vw
    return A, W


def flatness(A: np.ndarray, pos: np.ndarray) -> np.ndarray:
    """1 / SREaffineV: residual norm of the affine fit of each unit-norm loading column against the site position."""
    An = A / np.sqrt(np.sum(A ** 2, axis=0, keepdims=True))
    X = np.column_stack([np.ones(len(pos)), np.asarray(pos, np.float64)])
    beta = np.linalg.solve(X.T @ X + 1e-10 * np.eye(2), X.T @ An)
    r = np.linalg.norm(An - X @ beta, axis=0)
    return 1.0 / np.maximum(r, 1e-12)


def emg_cluster(x5: np.ndarray, hp: float = 100.0, fs: float = FS, lwinms: float = 20.0, seed: int = 0):
    """EMG_Cluster.m: returns (EMG_thrd, EMG_heavy) boolean per sample."""
    t = butfilter(x5, 4, hp / (fs / 2), "high")
    t = (t - t.mean(0)) / t.std(0, ddof=1)
    nch = t.shape[1]
    lwin = int(np.fix(lwinms * fs / 1000))
    win = np.ones(lwin) / lwin
    # MATLAB find(triu(ones)) = column-major linear indices of the upper triangle: column n, rows k <= n
    pairs = [(k, n) for n in range(nch) for k in range(n + 1)]
    cov = {p: np.convolve(t[:, p[0]] * t[:, p[1]], win, mode="same") for p in pairs}
    rng = np.random.default_rng(seed)
    rp = [pairs[i] for i in rng.permutation(len(pairs))]
    cov_v = np.sum([cov[p] for p in pairs], axis=0)
    ttv_v = np.zeros(len(t))
    for k in range(1, len(rp)):
        ttv_v += np.abs(cov[rp[k]] - cov[rp[k - 1]])
    Xtr = np.column_stack([ttv_v, cov_v])
    A, W = fastica(Xtr, seed=seed)
    ratio = np.abs(A[0, :]) / np.maximum(np.abs(A[1, :]), 0)
    if ratio[1] > ratio[0]:
        A, W = A[:, ::-1], W[::-1, :]
    s1, s2 = np.abs(Xtr @ W[0]), np.abs(Xtr @ W[1])
    heavy = s2 > s1
    thrd = s2 > np.percentile(s2[~heavy], 99, method="hazen") if (~heavy).any() else np.zeros(len(t), bool)
    return thrd, heavy


def emg_rm_long(x: np.ndarray, pos: np.ndarray, emg_thrd: np.ndarray, fs: float = FS, lower: float = 30.0,
                hp: float = 100.0, down_sample: int = 3, n_ic: int | None = None, seed: int = 0) -> tuple[np.ndarray, dict]:
    """EMG_rm_long.m, cmp_method 'hw'. x: samples x sites of one shank (wide band). Returns (cleaned x, info)."""
    nt, nch = x.shape
    if not n_ic:
        n_ic = int(max(np.fix(0.7 * nch), min(10, nch)))
    sel = emg_thrd.copy()
    step = int(np.fix(nt / 50 / fs))
    if step > 0:
        sel[::step] = True
    mx = x.mean(0)
    xc = x - mx
    wx, ar = whiten(xc)
    included = np.arange(nt)
    info = dict(n_selected=int(sel.sum()), removed=False, flatness=None, emg_comp=None, ar=ar.tolist())
    if sel.sum() < 10 * fs:
        return x.copy(), info
    thr, thr_low = 50.0, 10.0
    hx = butfilter(xc, 4, hp / (fs / 2), "high")
    Ah, Wh = fastica(hx[sel], n_ic, seed)
    rod = np.argsort(-flatness(Ah, pos))
    Ah, Wh = Ah[:, rod], Wh[rod]
    Ax, Wx = fastica(wx[included[::down_sample]] @ Wh.T, None, seed + 1)
    A, W = Ah @ Ax, Wx @ Wh
    fl = flatness(A, pos)
    remove = True
    if (np.sum(fl > thr_low) > 1) or (np.sum(fl > thr) < 1):
        remove = False
        wx, _ = whiten(wx, ar)
        nn = 1
        while ((np.sum(fl > thr_low) > 1) or (np.sum(fl > thr) < 1)) and nn < 5:
            fa = flatness(Ah, pos)
            if (np.sum(fa > thr_low) > 1) or (np.sum(fa > thr) < 1):
                Ah, Wh = fastica(hx[sel], None, seed + 10 * nn)
            Ax, Wx = fastica(wx[included[nn - 1::down_sample]] @ Wh.T, None, seed + 10 * nn + 1)
            A, W = Ah @ Ax, Wx @ Wh
            nn += 1
            fl = flatness(A, pos)
            thr = max(thr - 5, thr_low)
        if (np.sum(flatness(Ah, pos) > thr_low) < 2) and (np.sum(fl > thr) > 0):
            remove = True
    fl = flatness(A, pos)
    comp = int(np.argmax(fl))
    As, Ws = A[:, comp], W[comp]
    emg = xc @ Ws
    if lower > 0:
        emg = butfilter(emg, 4, lower / (fs / 2), "high")
    info.update(flatness=fl.tolist(), emg_comp=comp, flat_max=float(fl[comp]),
                n_flat_gt10=int(np.sum(fl > thr_low)), As=As.tolist())
    if not remove:
        return x.copy(), info
    med = np.median(np.abs(emg))
    sc = np.flatnonzero(emg[:-1] * emg[1:] < 0)
    if abs(emg[0]) < med * 1e-3:
        first = 1
    else:
        first = int(sc[0]) + 1 if sc.size else 1
    if first > 1250:
        first = int(np.flatnonzero(emg <= med * 1e-2)[0]) + 1
    emg[:first] = 0
    if abs(emg[-1]) < med * 1e-3:
        last = nt
    else:
        last = int(sc[-1]) + 1 if sc.size else nt
    if (nt - last) > 1250:
        last = int(np.flatnonzero(emg <= med * 1e-2)[-1]) + 1
    emg[last:] = 0
    info.update(removed=True, emg_rms=float(np.sqrt(np.mean(emg ** 2))))
    return xc - np.outer(emg, As) + mx, info


def cluster_sites(n: int) -> list[int]:
    """The toolbox's fix(linspace(3, n-3, 5)) (1-based) as 0-based positions."""
    return sorted(set(int(np.fix(v)) - 1 for v in np.linspace(3, n - 3, 5)))


def clean_chunk(X: np.ndarray, shanks: list[list[int]], fs: float = FS, lower: float = 30.0,
                seed: int = 0) -> tuple[np.ndarray, list[dict]]:
    """Clean one chunk (samples x all channels) shank by shank. `shanks`: per shank the live columns in depth order."""
    Xc = X.astype(np.float64, copy=True)
    infos = []
    for si, cols in enumerate(shanks):
        if len(cols) < 6:
            infos.append(dict(shank=si, skipped="fewer than 6 live sites"))
            continue
        pos = np.arange(len(cols), dtype=np.float64)
        cs = [cols[i] for i in cluster_sites(len(cols))]
        thrd, heavy = emg_cluster(Xc[:, cs], fs=fs, seed=seed)
        y, info = emg_rm_long(Xc[:, cols], pos, thrd, fs=fs, lower=lower, seed=seed)
        Xc[:, cols] = y
        info.update(shank=si, heavy_frac=float(heavy.mean()), thrd_frac=float(thrd.mean()))
        infos.append(info)
    return Xc, infos


def selftest() -> None:
    rng = np.random.default_rng(1)
    fs, T, n = FS, 120.0, 16
    nt = int(T * fs)
    t = np.arange(nt) / fs
    b, a = signal.butter(2, 0.5 / (fs / 2), "high")
    neural = np.cumsum(rng.standard_normal((nt, n)), 0) * 0.05
    neural = signal.filtfilt(b, a, neural, axis=0) + 0.3 * rng.standard_normal((nt, n))
    # local ripples: 150 Hz, 50 ms, every 2 s, a dipole centred on site 7
    rip = np.zeros(nt)
    for c in np.arange(1.0, T, 2.0):
        m = np.abs(t - c) < 0.025
        rip[m] = np.sin(2 * np.pi * 150 * (t[m] - c)) * np.hanning(m.sum())
    prof = np.exp(-0.5 * ((np.arange(n) - 7) / 1.5) ** 2) - 0.3 * np.exp(-0.5 * ((np.arange(n) - 11) / 1.5) ** 2)
    ripple = np.outer(rip, prof) * 4.0
    # EMG: broadband 80-450 Hz bursts in "awake" stretches, flat loading with a slight slope
    awake = (t % 30) < 15
    e = signal.filtfilt(*signal.butter(4, [80 / (fs / 2), 450 / (fs / 2)], "band"), rng.standard_normal(nt))
    e *= awake * (1 + 2 * (np.sin(2 * np.pi * 0.3 * t) > 0.5))
    load = 1.0 + 0.02 * np.arange(n)
    emg = np.outer(e, load) * 3.0
    X = neural + ripple + emg
    Xc, infos = clean_chunk(X, [list(range(n))], fs=fs, lower=30.0)
    info = infos[0]
    rb = lambda v: signal.filtfilt(*signal.butter(3, [100 / (fs / 2), 250 / (fs / 2)], "band"), v)
    resid = Xc - neural - ripple
    emg_left = np.sqrt(np.mean(rb(resid[:, 7])[awake] ** 2) / np.mean(rb(emg[:, 7])[awake] ** 2))
    rmask = np.abs(rip) > 0
    kept = np.sqrt(np.mean(rb(Xc[:, 7] - emg[:, 7] * 0)[rmask & ~awake] ** 2) / np.mean(rb(X[:, 7])[rmask & ~awake] ** 2))
    checks = {
        "a component was removed": info["removed"],
        "its flatness > 50": info["flat_max"] > 50,
        "residual EMG < 20 % (ripple band, awake, site 7)": emg_left < 0.2,
        "ripples in quiet stretches kept > 90 %": kept > 0.9,
        "arburg order 1 on an AR(1) process": abs(arburg(signal.lfilter([1], [1, -0.8], rng.standard_normal(20000)), 1)[1] + 0.8) < 0.02,
        "a flat loading is flatter than a dipole": flatness(np.column_stack([load, prof]), np.arange(n))[0]
                                                   > 10 * flatness(np.column_stack([load, prof]), np.arange(n))[1],
    }
    for k, v in checks.items():
        print(f"  {'ok ' if v else 'FAIL'} {k}")
    print(f"  (flatness max {info['flat_max']:.0f}, residual EMG {emg_left:.3f}, ripple kept {kept:.3f}, "
          f"n flat > 10: {info['n_flat_gt10']})")
    if not all(checks.values()):
        sys.exit("SELFTEST FAIL")
    print("SELFTEST PASS")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    else:
        ap.print_help()
