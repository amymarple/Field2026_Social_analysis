"""Strict sharp-wave-ripple test, fleet-wide: shank-local reference (channel minus shank median), 130-200 Hz envelope z-scored on the
REST window, events = peak z > 5, >= 20 ms above z 2.5, band-limited (130-200 vs 250-400 Hz power ratio > 3), spatially coherent
(>= 3 channels of the same shank within 10 ms). Reports per logger: best-shank rest-day rate, active-night rate on the same
channels (true SWRs vanish in theta states), and the ripple-triggered sharp-wave (1-50 Hz local LFP at the ripple peak, ADC)."""
import sys, os, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import numpy as np
from scipy import signal
from datetime import datetime
import hpc_signature_check as H
from _common import raw_ephys_root

FS_LFP = H.FS_LFP
SH = {1: [57, 54, 56, 55, 59, 52, 58, 53, 61, 50, 60, 51, 63, 48, 62, 49], 2: [42, 41, 44, 40, 45, 38, 46, 37, 47, 36, 43, 34, 39, 33, 35, 32],
      3: [9, 12, 10, 14, 8, 13, 5, 17, 6, 15, 4, 11, 1, 7, 2, 3], 4: [22, 27, 25, 24, 20, 29, 23, 26, 18, 31, 21, 28, 16, 0, 19, 30]}
WIN = [("rest day", datetime(2026, 9, 5, 10, 30)), ("active night", datetime(2026, 9, 4, 21, 30)), ("rest night", datetime(2026, 9, 5, 0, 30))]


def detect(lfp_local, stats=None):
    sos_r = signal.butter(3, [130, 200], btype="bandpass", fs=FS_LFP, output="sos")
    sos_h = signal.butter(3, [250, 400], btype="bandpass", fs=FS_LFP, output="sos")
    sos_l = signal.butter(2, [1, 50], btype="bandpass", fs=FS_LFP, output="sos")
    rb = signal.sosfiltfilt(sos_r, lfp_local, axis=0); hb = signal.sosfiltfilt(sos_h, lfp_local, axis=0); lb = signal.sosfiltfilt(sos_l, lfp_local, axis=0)
    env = np.abs(signal.hilbert(rb, axis=0))
    k = max(1, int(0.005 * FS_LFP)); kern = np.ones(k) / k
    env = np.stack([np.convolve(env[:, c], kern, mode="same") for c in range(env.shape[1])], axis=1)
    if stats is None:
        med = np.median(env, axis=0); mad = np.median(np.abs(env - med), axis=0) * 1.4826 + 1e-9
        stats = (med, mad)
    med, mad = stats
    z = (env - med) / mad
    win = int(0.04 * FS_LFP)
    events = {c: [] for c in range(lfp_local.shape[1])}
    for c in range(lfp_local.shape[1]):
        a = (z[:, c] > 2.5).astype(np.int8)
        d = np.diff(np.concatenate([[0], a, [0]]))
        for s, t in zip(np.where(d == 1)[0], np.where(d == -1)[0]):
            if (t - s) < int(0.02 * FS_LFP) or (t - s) > int(0.15 * FS_LFP) or z[s:t, c].max() < 5:
                continue
            pk = s + int(np.argmax(z[s:t, c]))
            a0, a1 = max(0, pk - win), min(lfp_local.shape[0], pk + win)
            if float((rb[a0:a1, c] ** 2).mean()) < 3.0 * float((hb[a0:a1, c] ** 2).mean()):
                continue
            events[c].append(pk)
    return events, stats, lb, rb


def coherent(events, chans):
    """events on >= 3 channels of the shank within 10 ms -> list of (peak sample, n channels)"""
    tol = int(0.01 * FS_LFP)
    allp = sorted((p, c) for c in chans for p in events[c])
    out, i = [], 0
    while i < len(allp):
        j = i; chs = {allp[i][1]}
        while j + 1 < len(allp) and allp[j + 1][0] - allp[i][0] <= tol:
            j += 1; chs.add(allp[j][1])
        if len(chs) >= 3:
            out.append((allp[i][0], len(chs)))
        i = j + 1
    return out


def main():
    root = raw_ephys_root("2026c")
    print("logger | shank | rest-day coherent SWR/min | active-night SWR/min (same z stats) | rest/active | sharp wave at ripple peak (local 1-50 Hz LFP, median ADC, best ch) | ripple amp z median")
    for animal, folder in H.LOGGERS.items():
        res = {}
        for wname, t in WIN:
            hit = H.session_for(root, folder, t)
            if hit is None:
                continue
            sdir, n, t0 = hit
            lfp, mad = H.load_lfp(sdir, n, t0)
            res[wname] = lfp
        rest = res["rest day"]
        for sh, chans in SH.items():
            loc_rest = rest[:, chans] - np.median(rest[:, chans], axis=1, keepdims=True)
            ev_r, stats, lb_r, rb_r = detect(loc_rest)
            ev_r = {chans[i]: v for i, v in ev_r.items()}
            coh_r = coherent(ev_r, chans)
            rate_r = len(coh_r) / (H.WIN_S / 60)
            # active window with the SAME z statistics (rest-based) so the comparison is like for like
            act = res["active night"]
            loc_act = act[:, chans] - np.median(act[:, chans], axis=1, keepdims=True)
            ev_a, _, _, _ = detect(loc_act, stats)
            ev_a = {chans[i]: v for i, v in ev_a.items()}
            rate_a = len(coherent(ev_a, chans)) / (H.WIN_S / 60)
            # sharp wave + ripple amplitude at coherent rest events, on the channel with most events
            best_i = int(np.argmax([len(ev_r[c]) for c in chans]))
            sw, ramp = [], []
            for pk, nc in coh_r:
                sw.append(float(lb_r[pk, best_i] - np.median(lb_r[max(0, pk - 250):pk - 60, best_i])))
                ramp.append(float(np.abs(rb_r[max(0, pk - 12):pk + 12, best_i]).max()))
            print(f"{animal} | sh{sh} | {rate_r:5.1f} | {rate_a:5.1f} | {rate_r / max(rate_a, 0.1):4.1f} | {np.median(sw) if sw else float('nan'):+7.0f} | ripple amp {np.median(ramp) if ramp else float('nan'):5.0f} ADC | best ch {chans[best_i]} n_rest={len(coh_r)} n_act={len(coherent(ev_a, chans))}", flush=True)


if __name__ == "__main__":
    main()
