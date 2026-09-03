"""Cheap per-session signal probe on a short window of ``amplifier.dat`` (shared by the index and the stager).

Reads ``seconds`` of raw data from the middle of the file (all of it when shorter) and reports, per channel:

    glitch samples   |x - med5(x)| > max(K*1.4826*MAD, FLOOR)    (the de-glitch rule, see deglitch_wild.py)
    ticks            |x(t) - (x(t-1)+x(t+1))/2| > 1200 ADC        (defects-note metric; interior samples)
    raw_std_adc      standard deviation of the raw window (ADC counts)
    noise_uV         robust high-pass noise = 1.4826 * median|hp| * gain_uV, hp = 500-5000 Hz band-pass of the
                     DE-GLITCHED window (scipy if available, else a first-difference proxy / sqrt(2))
    bad-channel candidates (advisory): noise_uV < 3 uV (open/dead)  OR  noise_uV > 4 x median(noise_uV) (broken)
                     OR raw_std_adc < 0.25 x median(raw_std_adc)

Noise regime (the de-glitch rule targets 1-2-sample impulses; anything wider or a broadband blow-up is a
different problem that the median filter must NOT be trusted to fix):
    tick_removal_frac  1 - ticks(after de-glitching the window) / ticks(before): the fraction of impulses the
                       5-point median rule actually removes (FM64 defect: ~0.997; wider impulses survive)
    raw_std_median     median over channels of the raw window std (ADC); night FM64 sessions sit at ~550-1000
    regime             'broadband' if raw_std_median > 2500 ADC (~490 uV rms); 'wide-impulse' if ticks_per_s > 100
                       and tick_removal_frac < 0.9; else 'normal'
    (the tick-mask run-length histogram is reported for information only: one large single-sample impulse
    also trips the tick test on its two neighbours, so run length is NOT impulse width)

Measured verdict (session level, from ticks/s summed over channels): 'glitchy' > 10/s, 'clean' < 1/s, else
'ambiguous'; a non-normal regime prefixes the verdict (e.g. 'glitchy+wide-impulse') so the index cannot be read
as "de-glitch will make this session clean".
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from deglitch_wild import DEFAULT_FLOOR, DEFAULT_K, TICK_ADC, estimate_thresholds, med5

NOISE_DEAD_UV = 3.0
NOISE_BROKEN_FACTOR = 4.0
STD_DEAD_FACTOR = 0.25
GLITCHY_TICKS_PER_S = 10.0
CLEAN_TICKS_PER_S = 1.0
WIDE_MIN_TICKS_PER_S = 100.0
WIDE_MAX_REMOVAL_FRAC = 0.9
BROADBAND_STD_ADC = 2500.0


def tick_run_lengths(mask: np.ndarray) -> np.ndarray:
    """Lengths of contiguous True runs down axis 0 of a (samples, channels) boolean mask, pooled over channels."""
    lengths = []
    for c in range(mask.shape[1]):
        m = mask[:, c].astype(np.int8)
        e = np.diff(np.concatenate(([0], m, [0])))
        lengths.append(np.where(e == -1)[0] - np.where(e == 1)[0])
    return np.concatenate(lengths) if lengths else np.zeros(0, dtype=int)


def _highpass(x: np.ndarray, fs: float) -> np.ndarray:
    try:
        from scipy import signal
        b, a = signal.butter(2, [500.0 / (fs / 2), min(5000.0, fs / 2 * 0.9) / (fs / 2)], "band")
        return signal.filtfilt(b, a, x, axis=0).astype(np.float32)
    except Exception:
        return (np.diff(x, axis=0) / np.sqrt(2.0)).astype(np.float32)


REGIME_RANK = {"normal": 0, "wide-impulse": 1, "broadband": 2}


def probe_window_stats(amplifier: Path, *, nch: int = 64, fs: float = 20000.0, seconds: float = 30.0,
                       k: float = DEFAULT_K, floor: float = DEFAULT_FLOOR, gain_uV: float = 0.195, n_windows: int = 5) -> dict:
    """Probe ``n_windows`` windows of ``seconds`` spread evenly over the file (1 = the middle window only).

    Sessions are non-stationary (handling, daytime troubleshooting), so the session-level numbers are the
    WORST case over windows: regime = worst regime, tick_removal_frac = min, raw_std_median_adc = max,
    ticks_per_s = max; per-window values are kept in ``windows``. Per-channel arrays (noise, thresholds,
    bad-channel candidates) come from the window with the median ticks/s (the 'typical' window)."""
    amplifier = Path(amplifier)
    nbytes = os.path.getsize(amplifier)
    ns = nbytes // (2 * nch)
    if ns < 16:
        return {"probe_seconds": 0.0, "verdict": "too-short"}
    win = int(min(ns, round(seconds * fs)))
    n_windows = max(1, int(n_windows))
    if ns <= win or n_windows == 1:
        starts = [max(0, (ns - win) // 2)]
    else:
        starts = sorted({int(round((ns - win) * (i + 0.5) / n_windows)) for i in range(n_windows)})
    d = np.memmap(amplifier, dtype=np.int16, mode="r", shape=(ns, nch))
    per = [_one_window(np.asarray(d[a:a + win]).astype(np.float32), a, fs=fs, k=k, floor=floor, gain_uV=gain_uV, nch=nch) for a in starts]
    if len(per) == 1:
        out = dict(per[0])
        out["n_windows"] = 1
        out["windows"] = [{kk: v for kk, v in per[0].items() if not isinstance(v, list)}]
        return out
    typical = sorted(per, key=lambda p: p["ticks_per_s"])[len(per) // 2]
    out = dict(typical)
    worst_regime = max((p["regime"] for p in per), key=lambda r: REGIME_RANK[r])
    out.update({
        "n_windows": len(per),
        "regime": worst_regime,
        "regime_by_window": ",".join(p["regime"] for p in per),
        "ticks_per_s": max(p["ticks_per_s"] for p in per),
        "ticks_per_s_typical": typical["ticks_per_s"],
        "tick_removal_frac": min(p["tick_removal_frac"] for p in per),
        "raw_std_median_adc": max(p["raw_std_median_adc"] for p in per),
        "glitch_samples_per_s": max(p["glitch_samples_per_s"] for p in per),
        "glitch_pct_samples": max(p["glitch_pct_samples"] for p in per),
        "windows": [{kk: v for kk, v in p.items() if not isinstance(v, list)} for p in per],
    })
    base = "glitchy" if out["ticks_per_s"] > GLITCHY_TICKS_PER_S else ("clean" if out["ticks_per_s"] < CLEAN_TICKS_PER_S else "ambiguous")
    out["verdict"] = base if worst_regime == "normal" else f"{base}+{worst_regime}"
    return out


def _one_window(x: np.ndarray, a: int, *, fs: float, k: float, floor: float, gain_uV: float, nch: int) -> dict:
    win = x.shape[0]
    dur = win / fs

    thr = estimate_thresholds(x, k, floor, block=min(100_000, win), nblocks=min(8, max(1, win // 100_000)))
    ref = med5(x)
    bad = np.abs(x - ref) > thr[None, :]
    n_glitch = bad.sum(axis=0)
    interior = np.abs(x[1:-1] - 0.5 * (x[:-2] + x[2:]))
    tick_mask = interior > TICK_ADC
    n_ticks = tick_mask.sum(axis=0)
    runs = tick_run_lengths(tick_mask)
    run_hist = np.bincount(np.minimum(runs, 7), minlength=8)[1:].tolist() if runs.size else [0] * 7
    raw_std = x.std(axis=0)
    raw_mean = x.mean(axis=0)
    xc = x.copy()
    xc[bad] = ref[bad]
    ticks_before = int(n_ticks.sum())
    ticks_after = int((np.abs(xc[1:-1] - 0.5 * (xc[:-2] + xc[2:])) > TICK_ADC).sum())
    tick_removal_frac = (1.0 - ticks_after / ticks_before) if ticks_before else 1.0
    hp = _highpass(xc, fs)
    noise_uV = 1.4826 * np.median(np.abs(hp - np.median(hp, axis=0)), axis=0) * gain_uV

    med_noise = float(np.median(noise_uV))
    med_std = float(np.median(raw_std))
    cand = np.where((noise_uV < NOISE_DEAD_UV) | (noise_uV > NOISE_BROKEN_FACTOR * med_noise) | (raw_std < STD_DEAD_FACTOR * med_std))[0]
    ticks_per_s = float(n_ticks.sum() / dur)
    verdict = "glitchy" if ticks_per_s > GLITCHY_TICKS_PER_S else ("clean" if ticks_per_s < CLEAN_TICKS_PER_S else "ambiguous")
    if med_std > BROADBAND_STD_ADC:
        regime = "broadband"
    elif ticks_per_s > WIDE_MIN_TICKS_PER_S and tick_removal_frac < WIDE_MAX_REMOVAL_FRAC:
        regime = "wide-impulse"
    else:
        regime = "normal"
    if regime != "normal":
        verdict = f"{verdict}+{regime}"
    return {
        "probe_seconds": dur,
        "probe_start_sample": int(a),
        "regime": regime,
        "raw_std_median_adc": med_std,
        "ticks_before": ticks_before,
        "ticks_after_deglitch": ticks_after,
        "tick_removal_frac": float(tick_removal_frac),
        "tick_mask_run_length_hist_1_to_7plus": run_hist,
        "glitch_samples_per_s": float(n_glitch.sum() / dur),
        "glitch_pct_samples": float(100.0 * n_glitch.sum() / (win * nch)),
        "ticks_per_s": ticks_per_s,
        "verdict": verdict,
        "threshold_adc_per_channel": [float(t) for t in thr],
        "glitch_per_channel_per_s": [float(v / dur) for v in n_glitch],
        "ticks_per_channel_per_s": [float(v / dur) for v in n_ticks],
        "raw_std_adc": [float(v) for v in raw_std],
        "raw_mean_adc": [float(v) for v in raw_mean],
        "noise_uV": [float(v) for v in noise_uV],
        "noise_uV_median": med_noise,
        "bad_channel_candidates": [int(c) for c in cand],
        "rules": {"noise_dead_uV": NOISE_DEAD_UV, "noise_broken_factor": NOISE_BROKEN_FACTOR, "std_dead_factor": STD_DEAD_FACTOR,
                  "glitchy_ticks_per_s": GLITCHY_TICKS_PER_S, "clean_ticks_per_s": CLEAN_TICKS_PER_S, "k_mad": k, "floor_adc": floor,
                  "tick_adc": TICK_ADC, "gain_uV": gain_uV, "wide_min_ticks_per_s": WIDE_MIN_TICKS_PER_S,
                  "wide_max_removal_frac": WIDE_MAX_REMOVAL_FRAC, "broadband_std_adc": BROADBAND_STD_ADC},
    }
