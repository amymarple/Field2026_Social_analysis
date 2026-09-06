"""Is a logger's signal hippocampal or cortical? Fleet comparison of LFP signatures in matched windows: theta prominence in an
active window, spindle (11-15 Hz) prominence and sharp-wave-ripple-like events (130-200 Hz, band-limited, >= 20 ms) in rest
windows, per channel and per logger. Usage: python ephys/hpc_signature_check.py --cohort 2026c
Outputs: results/<cohort>/ephys_spikes/reports/ephys_spikes_hpc_signature_<cohort>.csv (per logger x window x channel) and
figures/ephys_spikes_hpc_signature_<cohort>.png. Windows are the 2026c ones (edit WINDOWS for others)."""
import argparse, csv, os, time
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
from scipy import signal

from _common import figure_dir, raw_ephys_root, report_dir

FS = 20000; NCH = 64; WIN_S = 600; DEC = 16; FS_LFP = FS // DEC
LOGGERS = {"SF07": "SF7", "SF08": "SF8", "SF09": "SF9", "SF10": "SF10", "SF11": "SF11", "SF12": "SF12"}
WINDOWS = [("active night", datetime(2026, 9, 4, 21, 30)), ("rest night", datetime(2026, 9, 5, 0, 30)), ("rest day", datetime(2026, 9, 5, 10, 30))]


def session_for(root, folder, t):
    for sdir in sorted((root / folder).glob("*/[0-9]*_2026*")):
        amp = sdir / "amplifier.dat"
        if not amp.exists():
            continue
        p = sdir.name.split("_")
        start = datetime.strptime(p[1] + p[2][:6], "%Y%m%d%H%M%S")
        n = os.path.getsize(amp) // (2 * NCH)
        if start <= t and start + timedelta(seconds=n / FS) >= t + timedelta(seconds=WIN_S + 5):
            return sdir, n, (t - start).total_seconds()
    return None


def load_lfp(sdir, n, t0_s):
    mm = np.memmap(sdir / "amplifier.dat", dtype=np.int16, mode="r", shape=(n, NCH))
    i0 = int(t0_s * FS); i1 = i0 + WIN_S * FS
    parts, mads = [], []
    sos = signal.butter(2, [300, 3000], btype="bandpass", fs=FS, output="sos")
    for c0 in range(i0, i1, 60 * FS):
        x = np.asarray(mm[c0:min(c0 + 60 * FS, i1)], dtype=np.float32)
        x -= np.median(x, axis=0)
        parts.append(signal.resample_poly(x, 1, DEC, axis=0).astype(np.float32))
        if len(mads) < 2:
            hp = signal.sosfilt(sos, x[:20 * FS], axis=0)[FS:]
            mads.append(np.median(np.abs(hp), axis=0) * 1.4826)
        del x
    return np.concatenate(parts, axis=0), np.median(np.array(mads), axis=0)


def band(f, p, lo, hi):
    return p[(f >= lo) & (f < hi)].mean(axis=0)


def ripple_events(lfp):
    """Per channel: SWR-like events = 130-200 Hz envelope z > 4 at peak, z > 2 for >= 20 ms, band-limited (130-200 Hz power in the
    event > 2x the 250-400 Hz power in the same snippet - rejects broadband EMG/artifact bursts). Returns rate/min, median peak
    frequency (Hz), median duration (ms), median peak z per channel."""
    sos_r = signal.butter(3, [130, 200], btype="bandpass", fs=FS_LFP, output="sos")
    sos_h = signal.butter(3, [250, 400], btype="bandpass", fs=FS_LFP, output="sos")
    rb = signal.sosfiltfilt(sos_r, lfp, axis=0)
    hb = signal.sosfiltfilt(sos_h, lfp, axis=0)
    env = np.abs(signal.hilbert(rb, axis=0))
    k = max(1, int(0.005 * FS_LFP)); kern = np.ones(k) / k
    out = np.zeros((NCH, 4))
    win = int(0.04 * FS_LFP)
    for ch in range(NCH):
        e = np.convolve(env[:, ch], kern, mode="same")
        med = np.median(e); mad = np.median(np.abs(e - med)) * 1.4826 + 1e-9
        z = (e - med) / mad
        a = (z > 2).astype(np.int8)
        d = np.diff(np.concatenate([[0], a, [0]]))
        starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
        freqs, durs, peaks = [], [], []
        for s, t in zip(starts, ends):
            if (t - s) < int(0.02 * FS_LFP) or z[s:t].max() < 4:
                continue
            c = s + int(np.argmax(z[s:t]))
            a0, a1 = max(0, c - win), min(lfp.shape[0], c + win)
            pr = float((rb[a0:a1, ch] ** 2).mean()); ph = float((hb[a0:a1, ch] ** 2).mean())
            if pr < 2.0 * ph:
                continue
            seg = rb[a0:a1, ch] * np.hanning(a1 - a0)
            sp = np.abs(np.fft.rfft(seg, n=1024)); fr = np.fft.rfftfreq(1024, 1 / FS_LFP)
            sel = (fr >= 100) & (fr <= 250)
            freqs.append(float(fr[sel][np.argmax(sp[sel])])); durs.append((t - s) / FS_LFP * 1000); peaks.append(float(z[c]))
        out[ch] = [len(freqs) / (WIN_S / 60), np.median(freqs) if freqs else np.nan, np.median(durs) if durs else np.nan, np.median(peaks) if peaks else np.nan]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--raw-root", default=None)
    a = ap.parse_args()
    root, rd, fd = raw_ephys_root(a.cohort, a.raw_root), report_dir(a.cohort), figure_dir(a.cohort)
    rows, spectra, summary = [], {}, []
    for animal, folder in LOGGERS.items():
        for wname, t in WINDOWS:
            hit = session_for(root, folder, t)
            if hit is None:
                print(f"{animal} {wname}: no session"); continue
            sdir, n, t0 = hit
            t1 = time.time()
            lfp, mad = load_lfp(sdir, n, t0)
            f, p = signal.welch(lfp, fs=FS_LFP, nperseg=4 * FS_LFP, axis=0)
            theta = band(f, p, 6, 9) / (0.5 * (band(f, p, 3, 5) + band(f, p, 10, 13)))
            spindle = band(f, p, 11, 15) / (0.5 * (band(f, p, 7, 10) + band(f, p, 17, 20)))
            delta_frac = band(f, p, 1, 4) / band(f, p, 1, 100)
            gamma = band(f, p, 30, 80)
            rip = ripple_events(lfp)
            # 1/f-flattened mean spectrum (log-log linear fit 2-200 Hz removed) for the figure
            sel = (f >= 1) & (f <= 300)
            lp = np.log10(p[sel].mean(axis=1) + 1e-12); lf = np.log10(f[sel])
            fit = np.polyfit(lf[(f[sel] >= 2) & (f[sel] <= 200)], lp[(f[sel] >= 2) & (f[sel] <= 200)], 1)
            spectra[(animal, wname)] = (f[sel], lp - np.polyval(fit, lf))
            for ch in range(NCH):
                rows.append({"animal": animal, "window": wname, "session": sdir.name, "channel": ch, "spike_band_mad_adc": round(float(mad[ch]), 1),
                             "theta_ratio": round(float(theta[ch]), 3), "spindle_ratio": round(float(spindle[ch]), 3), "delta_frac": round(float(delta_frac[ch]), 3),
                             "log_gamma": round(float(np.log10(gamma[ch] + 1e-9)), 3), "swr_rate_per_min": round(float(rip[ch, 0]), 2),
                             "swr_peak_freq_hz": round(float(rip[ch, 1]), 1) if np.isfinite(rip[ch, 1]) else "", "swr_dur_ms": round(float(rip[ch, 2]), 1) if np.isfinite(rip[ch, 2]) else "",
                             "swr_peak_z": round(float(rip[ch, 3]), 1) if np.isfinite(rip[ch, 3]) else ""})
            best = int(np.argmax(rip[:, 0]))
            summary.append({"animal": animal, "window": wname, "session": sdir.name, "state_mad": round(float(np.median(mad)), 1),
                            "theta_max": round(float(theta.max()), 2), "theta_median": round(float(np.median(theta)), 2),
                            "spindle_max": round(float(spindle.max()), 2), "delta_frac_median": round(float(np.median(delta_frac)), 2),
                            "swr_rate_best_ch": round(float(rip[best, 0]), 1), "swr_best_ch": best, "swr_freq_best_ch": round(float(rip[best, 1]), 0) if np.isfinite(rip[best, 1]) else "",
                            "swr_dur_best_ch": round(float(rip[best, 2]), 0) if np.isfinite(rip[best, 2]) else "", "swr_peakz_best_ch": round(float(rip[best, 3]), 1) if np.isfinite(rip[best, 3]) else "",
                            "n_ch_swr_rate_ge_5": int((rip[:, 0] >= 5).sum()), "swr_rate_median_ch": round(float(np.median(rip[:, 0])), 1)})
            print(f"{animal} {wname:12} {sdir.name:26} mad {np.median(mad):5.1f}  theta max {theta.max():.2f}  spindle max {spindle.max():.2f}  SWR best ch {best} {rip[best, 0]:.1f}/min @ {rip[best, 1]:.0f} Hz, {rip[best, 2]:.0f} ms; ch>=5/min: {(rip[:, 0] >= 5).sum()}  ({time.time() - t1:.0f} s)", flush=True)
    with open(rd / f"ephys_spikes_hpc_signature_{a.cohort}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(rd / f"ephys_spikes_hpc_signature_{a.cohort}_summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0].keys())); w.writeheader(); w.writerows(summary)
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(16, 8), squeeze=False)
    for j, (wname, _) in enumerate(WINDOWS):
        ax = axes[0, j]
        for animal in LOGGERS:
            if (animal, wname) in spectra:
                f_, s_ = spectra[(animal, wname)]
                ax.plot(f_, s_, label=animal, lw=2 if animal == "SF11" else 1)
        ax.set_xscale("log"); ax.set_xlim(1, 300); ax.set_title(f"{wname}: 1/f-flattened mean PSD (log10)"); ax.set_xlabel("Hz"); ax.legend(fontsize=7)
        for x in (7.5, 13, 165):
            ax.axvline(x, color="gray", ls=":", lw=0.8)
        ax = axes[1, j]
        for animal in LOGGERS:
            r = [x for x in rows if x["animal"] == animal and x["window"] == wname]
            if r:
                ax.plot(sorted([x["swr_rate_per_min"] for x in r], reverse=True), label=animal, lw=2 if animal == "SF11" else 1)
        ax.set_title(f"{wname}: SWR-like events per min, channels sorted"); ax.set_xlabel("channel rank"); ax.legend(fontsize=7)
    fig.suptitle("Hippocampal vs cortical signature, all six loggers (theta ~7.5 Hz, spindle ~13 Hz, ripple ~165 Hz marked)")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(fd / f"ephys_spikes_hpc_signature_{a.cohort}.png", dpi=110)
    print("figure written")


if __name__ == "__main__":
    main()
