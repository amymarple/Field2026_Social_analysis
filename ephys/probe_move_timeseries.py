"""Probe-move check as a TIME SERIES: the per-channel fingerprint (gamma / ripple-band / theta LFP profile, spike-band noise, MUA rate)
in a 5-min window every hour from before the first logged advance to the newest data on disk, each compared with the pre-move
reference windows. A slow displacement after a 1/4 turn (tissue relaxing over hours, shuttle creeping) shows as the fingerprint
correlation to the pre-move reference decaying over the hours after the turn and the best along-shank shift moving off 0; a
slipping drive shows a flat line across days. Usage: python ephys/probe_move_timeseries.py --cohort 2026c
Outputs: results/<cohort>/ephys_spikes/reports/ephys_spikes_probe_move_timeseries_<cohort>.csv + figures/..._timeseries_<cohort>.png"""
import argparse, csv, os, time
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
from scipy import signal

from _common import figure_dir, raw_ephys_root, report_dir

FS = 20000; NCH = 64; WIN_S = 300; DEC = 16; FS_LFP = FS // DEC; HP_S = 60
SHANKS = {0: [57, 54, 56, 55, 59, 52, 58, 53, 61, 50, 60, 51, 63, 48, 62, 49],
          1: [42, 41, 44, 40, 45, 38, 46, 37, 47, 36, 43, 34, 39, 33, 35, 32],
          2: [9, 12, 10, 14, 8, 13, 5, 17, 6, 15, 4, 11, 1, 7, 2, 3],
          3: [22, 27, 25, 24, 20, 29, 23, 26, 18, 31, 21, 28, 16, 0, 19, 30]}
BANDS = {"theta": (5, 10), "gamma": (30, 80), "ripple": (120, 200)}
FOLDER = {"SF07": "SF7", "SF11": "SF11"}
MOVES = {"SF07": ["2026-09-04 14:00:54", "2026-09-05 13:31:19", "2026-09-06 13:29:42"],
         "SF11": ["2026-09-04 13:56:50", "2026-09-05 15:11:34", "2026-09-06 13:33:38"]}
T0, T1, STEP_H = datetime(2026, 9, 4, 8, 30), datetime(2026, 9, 6, 14, 0), 1.0
REF_BEFORE_MOVE = 1     # reference = the last window before move 1 (and, separately, before move 2)


def sessions_on_disk(root, animal):
    out = []
    for sdir in sorted((root / FOLDER[animal]).glob("*/[0-9]*_2026*")):
        amp = sdir / "amplifier.dat"
        if not amp.exists():
            continue
        parts = sdir.name.split("_")
        start = datetime.strptime(parts[1] + parts[2][:6], "%Y%m%d%H%M%S")
        n = os.path.getsize(amp) // (2 * NCH)
        out.append((start, start + timedelta(seconds=n / FS), sdir, n))
    return out


def features(sdir, n, t0_s):
    mm = np.memmap(sdir / "amplifier.dat", dtype=np.int16, mode="r", shape=(n, NCH))
    i0 = int(t0_s * FS); i1 = i0 + WIN_S * FS
    lfp_parts = []
    for c0 in range(i0, i1, 60 * FS):
        x = np.asarray(mm[c0:min(c0 + 60 * FS, i1)], dtype=np.float32)
        x -= np.median(x, axis=0)
        lfp_parts.append(signal.resample_poly(x, 1, DEC, axis=0).astype(np.float32))
        if c0 == i0:
            sos = signal.butter(2, [300, 3000], btype="bandpass", fs=FS, output="sos")
            hp = signal.sosfilt(sos, x[:HP_S * FS], axis=0)[FS:]          # drop the first second (filter transient)
            mad = np.median(np.abs(hp), axis=0) * 1.4826 + 1e-6
            below = hp < (-5.0 * mad)
            mua = (below[1:] & ~below[:-1]).sum(axis=0) / (HP_S - 1)
        del x
    lfp = np.concatenate(lfp_parts, axis=0)
    f, pxx = signal.welch(lfp, fs=FS_LFP, nperseg=2 * FS_LFP, axis=0)
    out = {f"log_{b}": np.log10(pxx[(f >= lo) & (f < hi)].mean(axis=0) + 1e-9) for b, (lo, hi) in BANDS.items()}
    out["spike_band_mad_adc"] = mad
    out["mua_rate_hz"] = mua
    return out


def rel(v):
    return v - np.median(v)


def best_shift(pa, pb):
    pa, pb = pa - pa.mean(), pb - pb.mean()
    best, bestc = 0, -2.0
    for s in range(-3, 4):
        x1, x2 = (pa[:16 - s], pb[s:]) if s >= 0 else (pa[-s:], pb[:16 + s])
        c = float(np.corrcoef(x1, x2)[0, 1]) if x1.std() > 0 and x2.std() > 0 else -2.0
        if c > bestc:
            best, bestc = s, c
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--raw-root", default=None)
    a = ap.parse_args()
    root, rd, fd = raw_ephys_root(a.cohort, a.raw_root), report_dir(a.cohort), figure_dir(a.cohort)
    series = {}
    for animal in FOLDER:
        sess = sessions_on_disk(root, animal)
        t = T0
        pts = []
        while t <= T1:
            hit = [s for s in sess if s[0] <= t and s[1] >= t + timedelta(seconds=WIN_S + 5)]
            if hit:
                start, end, sdir, n = hit[-1]
                t1 = time.time()
                fe = features(sdir, n, (t - start).total_seconds())
                pts.append({"t": t, "session": sdir.name, **fe})
                print(f"{animal} {t:%m-%d %H:%M} {sdir.name:26} ({time.time() - t1:.0f} s)", flush=True)
            t += timedelta(hours=STEP_H)
        # the 09-06 test recording, whatever its time
        for start, end, sdir, n in sess:
            if sdir.name.split("_")[1] == "20260906" and n / FS > WIN_S + 300:
                fe = features(sdir, n, 300.0)
                pts.append({"t": start + timedelta(seconds=300), "session": sdir.name, **fe})
                print(f"{animal} {start + timedelta(seconds=300):%m-%d %H:%M} {sdir.name:26} (test recording)", flush=True)
        series[animal] = sorted(pts, key=lambda p: p["t"])

    rows = []
    for animal, pts in series.items():
        moves = [datetime.strptime(m, "%Y-%m-%d %H:%M:%S") for m in MOVES[animal]]
        refs = {}
        for k, m in enumerate(moves[:2], 1):
            before = [p for p in pts if p["t"] + timedelta(seconds=WIN_S) <= m]
            refs[k] = before[-1] if before else None
        for p in pts:
            r = {"animal": animal, "time": p["t"].strftime("%Y-%m-%d %H:%M"), "session": p["session"],
                 "hours_since_move1": round((p["t"] - moves[0]).total_seconds() / 3600, 2),
                 "hours_since_move2": round((p["t"] - moves[1]).total_seconds() / 3600, 2)}
            for ft in ("log_gamma", "log_ripple", "log_theta", "mua_rate_hz", "spike_band_mad_adc"):
                v = p[ft] if ft != "mua_rate_hz" else np.log10(p[ft] + 0.01)
                r[f"{ft}_median"] = round(float(np.median(v)), 3)
                for sh, ch in SHANKS.items():
                    r[f"{ft}_shank{sh + 1}_median"] = round(float(np.median(v[ch])), 3)
                for k, ref in refs.items():
                    if ref is None:
                        continue
                    vr = ref[ft] if ft != "mua_rate_hz" else np.log10(ref[ft] + 0.01)
                    pr, pv = rel(vr), rel(v)
                    r[f"{ft}_r_vs_ref{k}"] = round(float(np.corrcoef(pr, pv)[0, 1]), 3)
                    r[f"{ft}_shift_vs_ref{k}"] = " ".join(f"{best_shift(pr[ch], pv[ch]):+d}" for ch in SHANKS.values())
                    r[f"{ft}_shank_r_vs_ref{k}"] = " ".join(f"{np.corrcoef(pr[ch] - pr[ch].mean(), pv[ch] - pv[ch].mean())[0, 1]:+.2f}" for ch in SHANKS.values())
            rows.append(r)
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(rd / f"ephys_spikes_probe_move_timeseries_{a.cohort}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    print("\n=== fingerprint correlation vs the window just before move 1 (ref1) and before move 2 (ref2) ===")
    for r in rows:
        print(f"{r['animal']} {r['time']} {r['session']:24} +{r['hours_since_move1']:6.1f}h  gamma r1={r.get('log_gamma_r_vs_ref1', float('nan')):+.2f} r2={r.get('log_gamma_r_vs_ref2', float('nan')):+.2f} shift1=[{r.get('log_gamma_shift_vs_ref1', '')}]  ripple r1={r.get('log_ripple_r_vs_ref1', float('nan')):+.2f}  MUA r1={r.get('mua_rate_hz_r_vs_ref1', float('nan')):+.2f}  shank gamma medians {r['log_gamma_shank1_median']:.2f} {r['log_gamma_shank2_median']:.2f} {r['log_gamma_shank3_median']:.2f} {r['log_gamma_shank4_median']:.2f}")

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 2, figsize=(16, 11), squeeze=False, sharex="col")
    for j, animal in enumerate(FOLDER):
        sub = [r for r in rows if r["animal"] == animal]
        tt = [datetime.strptime(r["time"], "%Y-%m-%d %H:%M") for r in sub]
        ax = axes[0, j]
        for ft, c in (("log_gamma", "tab:green"), ("log_ripple", "tab:red"), ("log_theta", "tab:blue"), ("mua_rate_hz", "k")):
            ax.plot(tt, [r.get(f"{ft}_r_vs_ref1", np.nan) for r in sub], "-o", ms=3, color=c, label=f"{ft} vs ref1 (pre-move-1)")
            ax.plot(tt, [r.get(f"{ft}_r_vs_ref2", np.nan) for r in sub], "--", ms=3, color=c, alpha=0.6, label=f"{ft} vs ref2 (pre-move-2)")
        ax.set_ylim(-0.3, 1.05); ax.set_ylabel("fingerprint r"); ax.set_title(f"{animal}: fingerprint correlation to the pre-move reference"); ax.legend(fontsize=6, ncol=2)
        ax2 = axes[1, j]
        for sh in range(4):
            ax2.plot(tt, [r[f"log_gamma_shank{sh + 1}_median"] for r in sub], "-o", ms=3, label=f"shank {sh + 1}")
        ax2.set_ylabel("median log10 gamma power"); ax2.set_title(f"{animal}: gamma level per shank (state + signal path)"); ax2.legend(fontsize=7)
        ax3 = axes[2, j]
        for sh in range(4):
            ax3.plot(tt, [r[f"spike_band_mad_adc_shank{sh + 1}_median"] for r in sub], "-o", ms=3, label=f"shank {sh + 1}")
        ax3.set_ylabel("spike-band MAD (ADC)"); ax3.set_title(f"{animal}: spike-band noise floor per shank"); ax3.legend(fontsize=7)
        for ax_ in (ax, ax2, ax3):
            for m in MOVES[animal]:
                ax_.axvline(datetime.strptime(m, "%Y-%m-%d %H:%M:%S"), color="gray", ls=":", lw=1)
        ax3.tick_params(axis="x", rotation=30, labelsize=7)
    fig.suptitle("Probe-move time series (5-min window per hour; dotted = logged 1/4-turn advances)")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(fd / f"ephys_spikes_probe_move_timeseries_{a.cohort}.png", dpi=110)
    print("figure written")


if __name__ == "__main__":
    main()
