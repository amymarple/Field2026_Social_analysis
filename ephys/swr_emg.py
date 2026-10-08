"""LFP-derived EMG for SWR detection (cohort 3; plan implementation_plan/2026-10-07-swr-detection-automation.md).

Why (user, 2026-10-08): where the probe has no sharp-wave reversal (SF07, above the pyramidal layer) detection rests on
ripple-band power alone, which chewing / muscle activity contaminates; such events must be excludable by EMG.

Definition = PreprocessPipeline state_scoring._compute_emg_from_lfp (= buzcode getEMGFromLFP), the one the sleep
pipeline's `lfpemg` variant uses:
  channels  the first non-skipped channel of every spike group of the final channel map (here: each shank's top site)
  signal    300 - 600 Hz band-pass (Butterworth order 3, zero-phase); our LFP is already low-passed at 450 Hz, so the
            effective band is ~300-450 Hz, above the ripple band
  EMG(t)    mean pairwise Pearson correlation of those signals over t +- 0.5 s
Muscle activity is volume-conducted (the same waveform on every shank: high correlation); a ripple and its spikes are
local (low correlation). Session trace at 2 Hz like the scorer; per event / candidate in the +-0.5 s window centred on it.
Exclusion rule (starting point, to be calibrated by the user's review): EMG above `NREM_PCT` (95th) percentile of the
session's own 2-Hz EMG during NREM seconds.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from scipy import signal

SR = 1250.0
HALF_S = 0.5
STEP_S = 0.5
NREM_PCT = 95.0


def emg_channels(xml_path: Path, skip: set[int] | None = None) -> list[int]:
    """0-based: the first non-skipped channel of every spike group (PreprocessPipeline _select_emg_channels)."""
    root = ET.parse(xml_path).getroot()
    groups = root.findall("spikeDetection/channelGroups/group")
    if groups:
        groups = [[int(c.text) for c in g.findall("channels/channel")] for g in groups]
    else:
        groups = [[int(c.text) for c in g.findall("channel")] for g in root.findall("anatomicalDescription/channelGroups/group")]
    anat_skip = {int(c.text) for g in root.findall("anatomicalDescription/channelGroups/group")
                 for c in g.findall("channel") if c.get("skip", "0") == "1"}
    skip = set(skip or set()) | anat_skip
    picks = [next(c for c in g if c not in skip) for g in groups if any(c not in skip for c in g)]
    return sorted(set(picks))


def bandpass(x: np.ndarray, fs: float = SR) -> np.ndarray:
    nyq = fs / 2.0
    hi = max(301.0, max(625.0, nyq) - 25.0)
    b, a = signal.butter(3, [300.0 / nyq, min(0.999, hi / nyq)], btype="bandpass")
    return signal.filtfilt(b, a, np.asarray(x, float), axis=0)


class LfpEmg:
    """Mean pairwise correlation of the band-passed channels in +-half windows, at arbitrary sample indices
    (window sums from cumulative sums; one pair in memory at a time)."""

    def __init__(self, raw_cols: np.ndarray, fs: float = SR, half_s: float = HALF_S):
        self.sig = bandpass(raw_cols, fs)
        self.n, self.k = self.sig.shape
        self.half = int(round(half_s * fs))
        self.fs = fs
        self.c1 = [np.concatenate([[0.0], np.cumsum(self.sig[:, i])]) for i in range(self.k)]
        self.c2 = [np.concatenate([[0.0], np.cumsum(self.sig[:, i] ** 2)]) for i in range(self.k)]

    def at(self, idx: np.ndarray) -> np.ndarray:
        idx = np.asarray(idx, np.int64)
        lo = np.clip(idx - self.half, 0, self.n)
        hi = np.clip(idx + self.half + 1, 0, self.n)
        m = (hi - lo).astype(float)
        out = np.zeros(idx.size)
        npair = 0
        for i in range(self.k):
            sx, sxx = self.c1[i][hi] - self.c1[i][lo], self.c2[i][hi] - self.c2[i][lo]
            for j in range(i + 1, self.k):
                cxy = np.concatenate([[0.0], np.cumsum(self.sig[:, i] * self.sig[:, j])])
                sy, syy = self.c1[j][hi] - self.c1[j][lo], self.c2[j][hi] - self.c2[j][lo]
                cov = (cxy[hi] - cxy[lo]) - sx * sy / m
                den = np.sqrt(np.maximum((sxx - sx ** 2 / m) * (syy - sy ** 2 / m), 1e-30))
                out += cov / den
                npair += 1
        return out / max(npair, 1)

    def trace(self, step_s: float = STEP_S):
        """The scorer's 2-Hz EMG: centres every step from `half` to n - half."""
        step = max(1, int(round(step_s * self.fs)))
        centres = np.arange(self.half, self.n - self.half, step)
        return centres / self.fs, self.at(centres)


def nrem_threshold(t_s: np.ndarray, emg: np.ndarray, states_npz: Path | None, pct: float = NREM_PCT):
    """The `pct` percentile of the 2-Hz EMG during NREM seconds (None when the session has < 10 min of NREM)."""
    if states_npz is None or not Path(states_npz).exists():
        return None
    st = np.load(states_npz)
    nrem = set(st["ts"][st["state"] == 3].tolist())
    m = np.array([int(t) in nrem for t in t_s])
    if m.sum() < 10 * 60 * 2:
        return None
    return float(np.percentile(emg[m], pct))


def theta_delta_log(x: np.ndarray, fs: float = SR, half_s: float = HALF_S) -> np.ndarray:
    """log(theta 6-10 Hz / delta 1-4 Hz power), each the mean squared band-passed signal over t +- half (every sample)."""
    from scipy.ndimage import uniform_filter1d
    w = 2 * int(round(half_s * fs)) + 1
    out = []
    for lo, hi in ((6.0, 10.0), (1.0, 4.0)):
        sos = signal.butter(3, [lo, hi], btype="bandpass", fs=fs, output="sos")
        y = signal.sosfiltfilt(sos, np.asarray(x, float))
        out.append(uniform_filter1d(y * y, w, mode="nearest"))
    return np.log(np.maximum(out[0], 1e-12) / np.maximum(out[1], 1e-12))


def nrem_pct_threshold(values_per_sample: np.ndarray, states_npz: Path | None, fs: float = SR, pct: float = NREM_PCT):
    """The `pct` percentile of a per-sample series sampled at 2 Hz during NREM seconds (None if < 10 min NREM)."""
    if states_npz is None or not Path(states_npz).exists():
        return None
    st = np.load(states_npz)
    sec = st["ts"][st["state"] == 3]
    if sec.size < 600:
        return None
    idx = np.concatenate([(sec + 0.25) * fs, (sec + 0.75) * fs]).astype(np.int64)
    idx = idx[idx < values_per_sample.size]
    return float(np.percentile(values_per_sample[idx], pct))
