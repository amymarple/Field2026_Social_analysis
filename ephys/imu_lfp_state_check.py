r"""Is the IMU a usable EMG? IMU movement vs hippocampal LFP state, per second, on sessions with local LFP (validation).

Same logger clock for both, so IMU second s <-> LFP frames [1250 s, 1250 (s+1)) with no cross-device alignment.
Expected if the IMU is a valid EMG: IMU-moving seconds are theta-dominated (active wake); IMU-still seconds split into
low theta/delta (NREM) and high theta/delta (REM). Outputs numbers (printed + CSV) and a 2-D histogram figure for the
user to inspect (not judged by the agent).

Definitions (per second s):
  VeDBA_1s(s)          mean VeDBA in the second (ephys/make_imu.py), m/s^2
  still(s)             VeDBA_1s(s) < theta_a, theta_a = per-animal valley of the log VeDBA histogram (IMU_STILL_THR)
  P_band(s)            mean Welch PSD over the band, 4-s window centred on s (2-s segments, 50 % overlap), on channel c*
  TD(s)                theta/delta = P_6-10 Hz(s) / P_1-4 Hz(s)   (log10 reported)
  c*                   the live channel with the largest median TD over the IMU-moving seconds (theta-richest; chosen on
                       moving seconds only, so the still-second distribution is not used to pick it)
  REM-like / NREM-like still seconds: log10 TD above / below the midpoint between the moving-second median and the
                       5th percentile of still seconds (a descriptive split, not a sleep score)

Usage: python ephys/imu_lfp_state_check.py --cohort 2026c --sessions SF08:6_20260910_082629.685 SF07:15_20260902_082418.755
       [--anchor SF08:6_20260910_082629.685:22230]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal

from _common import analysis_root, figure_dir, git_commit, report_dir, resolve_cohort, utc_now_iso

FS_LFP = 1250
NCH = 64
IMU_STILL_THR = {"SF07": 0.387, "SF08": 0.307, "SF09": 0.325, "SF10": 0.325, "SF11": 0.387, "SF12": 0.365}  # 2026-09-28


def band_power_per_second(x: np.ndarray, n_s: int) -> tuple[np.ndarray, np.ndarray]:
    """Delta (1-4 Hz) and theta (6-10 Hz) power per second from a 4-s centred window (Welch, 2-s segments)."""
    delta = np.full(n_s, np.nan)
    theta = np.full(n_s, np.nan)
    half = 2 * FS_LFP
    for s in range(n_s):
        c = s * FS_LFP + FS_LFP // 2
        a, b = c - half, c + half
        if a < 0 or b > len(x):
            continue
        f, p = signal.welch(x[a:b], fs=FS_LFP, nperseg=2 * FS_LFP, noverlap=FS_LFP)
        delta[s] = p[(f >= 1) & (f <= 4)].mean()
        theta[s] = p[(f >= 6) & (f <= 10)].mean()
    return delta, theta


def pick_channel(lfp: np.ndarray, moving_secs: np.ndarray, rng: np.random.Generator) -> tuple[int, list]:
    secs = rng.choice(moving_secs, size=min(300, len(moving_secs)), replace=False)
    scores = []
    for ch in range(NCH):
        x = lfp[:, ch].astype(np.float32)
        if np.std(x[:: FS_LFP]) < 5:                       # dead / flat column
            scores.append(-np.inf)
            continue
        td = []
        for s in secs:
            seg = x[s * FS_LFP: (s + 2) * FS_LFP]
            if len(seg) < 2 * FS_LFP:
                continue
            f, p = signal.welch(seg, fs=FS_LFP, nperseg=2 * FS_LFP)
            td.append(p[(f >= 6) & (f <= 10)].mean() / p[(f >= 1) & (f <= 4)].mean())
        scores.append(float(np.median(td)) if td else -np.inf)
    return int(np.argmax(scores)), scores


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--sessions", nargs="+", required=True, help="ANIMAL:SESSION (animal as SF07)")
    ap.add_argument("--anchor", nargs="*", default=[], help="ANIMAL:SESSION:REC_SECONDS to report +-60 s around")
    a = ap.parse_args()
    c = resolve_cohort(a.cohort)
    ar = analysis_root(c)
    rng = np.random.default_rng(0)
    rows, figs = [], []
    for spec in a.sessions:
        an, ses = spec.split(":")
        imu = pd.read_csv(ar / "imu" / an / f"{ses}.imu_1s.csv")
        lfp = np.memmap(ar / "lfp" / an / f"{ses}.lfp", dtype=np.int16, mode="r").reshape(-1, NCH)
        n_s = min(len(imu), lfp.shape[0] // FS_LFP)
        imu = imu.iloc[:n_s]
        ok = (imu.saturated == 0) & (imu.unreliable == 0)
        still = (imu.vedba_mean < IMU_STILL_THR[an]) & ok
        moving = (~still) & ok
        ch, _ = pick_channel(lfp, np.flatnonzero(moving.to_numpy()[:-2]), rng)
        delta, theta = band_power_per_second(lfp[:, ch].astype(np.float64), n_s)
        ltd = np.log10(theta / delta)
        m_med = np.nanmedian(ltd[moving])
        s_p5 = np.nanpercentile(ltd[still], 5)
        split = 0.5 * (m_med + s_p5)
        rem_like = still & (ltd > split)
        nrem_like = still & (ltd <= split)
        row = {"animal": an, "session": ses, "seconds": n_s, "channel": ch, "still_share": still.mean(),
               "log10TD_moving_median": m_med, "log10TD_still_median": np.nanmedian(ltd[still]),
               "still_REMlike_share": rem_like.sum() / max(1, still.sum()), "still_NREMlike_share": nrem_like.sum() / max(1, still.sum()),
               "moving_theta_dominated_share": float(np.nanmean(ltd[moving] > split))}
        rows.append(row)
        print(f"{an} {ses}: channel {ch}; still {row['still_share']:.0%}; log10 theta/delta moving median {m_med:.2f} vs still {row['log10TD_still_median']:.2f}; "
              f"moving above split {row['moving_theta_dominated_share']:.0%}; still split: REM-like {row['still_REMlike_share']:.0%}, NREM-like {row['still_NREMlike_share']:.0%}")
        figs.append((an, ses, np.log10(imu.vedba_mean.to_numpy() + 1e-3), ltd, IMU_STILL_THR[an], split))
        for anc in a.anchor:
            aan, ases, arec = anc.split(":")
            if (aan, ases) != (an, ses):
                continue
            r0 = int(float(arec))
            win = slice(max(0, r0 - 60), min(n_s, r0 + 60))
            print(f"  anchor rec {r0} s (+-60 s): VeDBA median {imu.vedba_mean.iloc[win].median():.3f} m/s^2, still {still.iloc[win].mean():.0%}, "
                  f"|w| median {imu.omega_mean.iloc[win].median():.1f} deg/s, log10 theta/delta median {np.nanmedian(ltd[win]):.2f} "
                  f"(split {split:.2f}); pitch {imu.pitch_mean.iloc[win].median():.0f} deg")
    out = pd.DataFrame(rows)
    rd = report_dir(c)
    out.to_csv(rd / f"ephys_spikes_imu_lfp_state_check_{c}.csv", index=False)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, len(figs), figsize=(5 * len(figs), 4.2), squeeze=False)
        for ax, (an, ses, lv, ltd, thr, split) in zip(axes[0], figs):
            okk = np.isfinite(lv) & np.isfinite(ltd)
            ax.hist2d(lv[okk], ltd[okk], bins=(90, 90), range=((-2, 1.3), (-1.5, 1.5)), cmap="magma", norm=matplotlib.colors.LogNorm())
            ax.axvline(np.log10(thr), color="c", lw=1)
            ax.axhline(split, color="w", lw=1, ls="--")
            ax.set_xlabel("log10 IMU VeDBA per second (m/s^2)")
            ax.set_ylabel("log10 theta/delta")
            ax.set_title(f"{an} {ses}", fontsize=9)
        fig.suptitle(f"IMU movement vs LFP state (git {git_commit()}, {utc_now_iso()})", fontsize=9)
        fp = figure_dir(c) / f"ephys_spikes_imu_lfp_state_check_{c}.png"
        fig.savefig(fp, dpi=130, bbox_inches="tight")
        print(f"figure -> {fp}")
    except Exception as e:  # noqa: BLE001
        print(f"figure skipped: {e}")


if __name__ == "__main__":
    main()
