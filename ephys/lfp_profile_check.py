"""Channel-map test #3: the hippocampal LFP depth profile must be SMOOTH along a shank (sharp wave, ripple power, theta phase).

Physics (user, 2026-09-08): on a linear shank crossing CA1 the sharp wave (SPW) is positive in stratum oriens / pyramidale and
reverses gradually to negative in stratum radiatum; ripple power peaks in the pyramidal layer and falls off on both sides; theta
phase shifts monotonically with depth. So under the correct within-shank site order all three profiles are smooth; a scrambled
order makes them jagged. The test needs 30 min of LFP and no spike sorting.

Method
  1. Window of the pipeline's .lfp (1250 Hz, 64 exported columns) from the sort folder (daytime sessions are sleep-rich).
  2. Ripples: 130-200 Hz band-pass on every live column, |Hilbert| envelope smoothed 8 ms, z-scored; event = max_z > thr for
     >= 20 ms (merged within 50 ms); peak = argmax of the summed envelope.
  3. Profiles per column: SPW = ripple-triggered mean of the 1-50 Hz LFP over +-15 ms (uV, relative 0.195 uV/count);
     RIPPLE = mean envelope at the peak; THETA = circular-mean phase difference (6-10 Hz Hilbert) to the column with the most
     theta power, over the 2-s windows with the highest theta/delta ratio (REM / running).
  4. Adjacent-site spacing: r_adj = ripple-band (130-200 Hz) correlation of consecutive sites in a candidate order. With an
     exponential fall-off of correlation with distance, the implied distance between two consecutive sites is
     50 um * ln(r_adj) / ln(r_ref), r_ref = median r_adj of the reference shank (--ref-group, a shank whose order is trusted).
     A pair implying >= 1.5 sites is flagged as a GAP (a missing / dead site between them, or a larger pitch).
     CAVEAT (SF10, 2026-09-08): the correlation is NOT a distance when site impedances differ. High-impedance sites carry
     attenuated signal plus shared noise: on SF10 shank 4 the eight even-Intan sites (connector-B row 3) have 4x smaller SPW,
     20 % lower LFP rms and correlate with EACH OTHER at r 0.47 regardless of distance (odd-even 0.26, between shanks 0.11),
     and single degraded sites (SF10 cols 3, 17, 15, 47) correlate with nothing, so they look like gaps. Treat the gap flags as
     a prompt to look at the site's amplitude, never as evidence for placing a dead column; a dead column's position needs the
     physical wiring (user, 2026-09-08). In raw mode the correlation uses the 300-3000 Hz band at 20 kHz (first 2 min).
  5. Scores per candidate order (per shank, averaged): spw_tv, ripple_tv, theta_tv (total variation / range; 1.0 = monotonic),
     flips (SPW sign changes; correct: 0 or 1). Ranking = sum of the three tv ranks (--rank-by spw|theta|ripple|all).
  Candidates: connector_variants (16 full matings) x bank rotations, or --physical: physical_variants (per-connector 180 deg
  rotation, swap, mirror AND pin shifts -2..+2 with their predicted dead columns; a shift is only physically consistent if its
  predicted dead columns lie inside the user's broken-channel list, reported as dead_ok).
  Self-check of the tool: on SF07 its own verified map must rank first. SF07's mating differs from the other animals, so its map is
  NOT a reference for them (user, 2026-09-08) — the 'ref. v1_raw' line is the ProbeMaps standard order, printed for orientation only.

Usage: python ephys/lfp_profile_check.py --cohort 2026c --animal SF10 --session 9_20260902_083247.835 [--minutes 30]
        [--bad 2 32 34 ...] [--ref-group 4] [--physical] [--max-rot 1] [--top 12] [--profile-only]
        [--permute-tail GROUP N   brute-force the order of the last N sites of one group (N <= 7)]
        [--derive-xml OUT --keep-groups 1 4   write a DATA-DERIVED order (positive-SPW sites by ripple power asc, then
         negative-SPW sites by SPW desc); each dead column is placed as a PACE MAKER at the largest SPW-gradient gap of its
         shank, never at the end of the group (its exact site stays unknown, but the position keeps the geometry honest)]
CAVEAT on --derive-xml (2026-10-05, SF08): the rule assumes negative SPW = radiatum. When the shank sits higher (09-09: the
reversal below the tip, top sites negative from an offset) it orders the shank BACKWARDS. Derive only on windows with a clear
reversal or an all-positive profile; check a candidate on other days by the signed profile (monotone along the order,
ripple maximum at the pyramidale end), never by the sign of individual sites.
--imu-csv/--imu-thr/--session-offset-s keep only ripples with the animal IMU-still for +-2 s (NREM / quiet wake; user 2026-10-05).
BOUT mode (user 2026-10-05: the layer profile belongs to NREM SWRs; take short NREM bouts from the sleep score):
  --lfp <ar>/lfp/<SFxx>/<s>.lfp --states <ar>/sleep/<variant>/<SFxx>/<s>/complex_system/<s>.SleepState.states.mat
  [--state NREMstate --edge-s 5 --bout-min-s 15 --bout-max-s 60 --range-min A B --max-bout-min 20] reads only the trimmed bouts
  (the middle <= 60 s of each; bouts spread evenly over the range when they exceed the cap) of the session LFP, z-scores the
  ripple band on NREM alone, filters per bout, drops ripples < 150 ms from a join, and takes theta from REM bouts of the same
  range. --states without --lfp gates a window's ripples instead (whole trimmed bouts). --lfp without --states reads a plain
  window (--offset-min, --minutes) of any session .lfp; channel count and rate come from the .lfp.json sidecar or the --xml.
  The npz adds ripple_peaks_session_s and segments_session_s (session seconds = the .lfp / Neuroscope time base).
Appends results/<cohort>/ephys_spikes/reports/ephys_spikes_lfp_profile_check_<cohort>.csv.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from scipy.signal import butter, filtfilt, hilbert

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import git_commit, report_dir, sort_root, utc_now_iso  # noqa: E402
from probe_map_check import PROBE_XML, PROBEMAPS, connector_variants, load_groups, physical_variants, rotation_permutation  # noqa: E402
from footprint_map_check import candidate_sites  # noqa: E402
from wild_ce_params import parse_ce_params  # noqa: E402
from deglitch_wild import estimate_thresholds, med5  # noqa: E402

UV = 0.195
PITCH_UM = 50.0


def _segwise(fn, x: np.ndarray, bounds) -> np.ndarray:
    """Apply fn to every [s, e) segment of x separately (state bouts concatenated: no filter / Hilbert transient across a join)."""
    if bounds is None:
        return fn(x)
    return np.concatenate([fn(x[s:e]) for s, e in bounds], axis=0)


def bp(x: np.ndarray, fs: float, lo: float, hi: float, order: int = 3, bounds=None) -> np.ndarray:
    b, a = butter(order, [lo / (fs / 2), hi / (fs / 2)], btype="band")
    return _segwise(lambda v: filtfilt(b, a, v, axis=0), x, bounds)


def detect_ripples(lfp: np.ndarray, fs: float, live: np.ndarray, thr: float = 4.0, min_ms: float = 20.0, merge_ms: float = 50.0,
                   bounds=None):
    rip = bp(lfp[:, live], fs, 130.0, 200.0, bounds=bounds)
    env = _segwise(lambda v: np.abs(hilbert(v, axis=0)), rip, bounds)
    k = max(1, int(0.008 * fs)); ker = np.ones(k) / k
    env = _segwise(lambda v: np.apply_along_axis(lambda u: np.convolve(u, ker, mode="same"), 0, v), env, bounds)
    z = (env - env.mean(0)) / (env.std(0) + 1e-9)
    zmax = z.max(1); zsum = z.sum(1)
    above = zmax > thr
    idx = np.where(np.diff(above.astype(int)) != 0)[0] + 1
    if above[0]:
        idx = np.r_[0, idx]
    if above[-1]:
        idx = np.r_[idx, len(above)]
    segs = idx.reshape(-1, 2) if idx.size % 2 == 0 else idx[:-1].reshape(-1, 2)
    merged = []
    for s, e in segs:
        if merged and s - merged[-1][1] < merge_ms / 1000 * fs:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    peaks = [s + int(np.argmax(zsum[s:e])) for s, e in merged if (e - s) >= min_ms / 1000 * fs]
    return np.array(peaks, dtype=int), env, rip


def profiles(lfp: np.ndarray, fs: float, peaks: np.ndarray, env_live: np.ndarray, live: np.ndarray, half_ms: float = 15.0,
             bounds=None):
    slow = bp(lfp, fs, 1.0, 50.0, bounds=bounds)
    h = int(half_ms / 1000 * fs); W = int(0.15 * fs)
    ok = peaks[(peaks > W) & (peaks < lfp.shape[0] - W)]
    spw = np.zeros(lfp.shape[1]); rp = np.zeros(lfp.shape[1]); n = 0
    for t in ok:
        spw += slow[t - h:t + h + 1].mean(0); n += 1
    spw = spw / max(n, 1) * UV
    rp_live = np.zeros(len(live))
    for t in ok:
        rp_live += env_live[max(0, t - h):t + h + 1].mean(0)
    rp[live] = rp_live / max(n, 1) * UV
    return spw, rp, n


def ripple_corr(rip_live: np.ndarray, peaks: np.ndarray, fs: float, live: np.ndarray, nch: int, half_ms: float = 25.0) -> np.ndarray:
    """Event-averaged Pearson correlation of the 130-200 Hz signal between columns over +-half_ms around each ripple peak
    (nch x nch, NaN for dead columns). The ripple keeps its phase above and through stratum pyramidale and REVERSES 150-200 um
    below it, where its envelope grows again (Csicsvari 1999; Schomburg 2012): corr(site, the shank's ripple-maximum site) x
    ripple amplitude = a SIGNED ripple that separates the two sides of the layer. Gain-free and reference-robust."""
    h = int(half_ms / 1000 * fs)
    ok = peaks[(peaks > h) & (peaks < rip_live.shape[0] - h)]
    C = np.zeros((rip_live.shape[1],) * 2)
    for t in ok:
        x = rip_live[t - h:t + h + 1]; x = x - x.mean(0)
        s = np.sqrt((x ** 2).sum(0)) + 1e-12
        C += (x.T @ x) / np.outer(s, s)
    full = np.full((nch, nch), np.nan)
    full[np.ix_(live, live)] = C / max(len(ok), 1)
    return full


def theta_profile(lfp: np.ndarray, fs: float, live: np.ndarray, win_s: float = 2.0, top_frac: float = 0.3, bounds=None):
    """Circular-mean theta (6-10 Hz) phase of every live column relative to the column with the most theta power, over the
    windows with the highest theta/delta ratio (windows never straddle a bout join). Returns (phase_deg[64], theta_power[64],
    ref_col, n_windows)."""
    th = bp(lfp[:, live], fs, 6.0, 10.0, bounds=bounds); de = bp(lfp[:, live], fs, 1.0, 4.0, bounds=bounds)
    w = int(win_s * fs)
    starts = [s + i * w for s, e in (bounds or [(0, lfp.shape[0])]) for i in range((e - s) // w)]
    ratio = np.array([(th[s:s + w] ** 2).mean() / ((de[s:s + w] ** 2).mean() + 1e-9) for s in starts])
    keep = np.argsort(ratio)[-max(3, int(top_frac * len(starts))):]
    sel = np.concatenate([np.arange(starts[i], starts[i] + w) for i in sorted(keep)])
    an = hilbert(th[sel], axis=0)
    power = (np.abs(an) ** 2).mean(0)
    ref_i = int(np.argmax(power))
    d = np.angle(an * np.conj(an[:, [ref_i]]))
    ph = np.angle(np.exp(1j * d).mean(0))
    phase = np.full(lfp.shape[1], np.nan); tp = np.zeros(lfp.shape[1])
    phase[live] = np.degrees(ph); tp[live] = power * UV * UV
    return phase, tp, int(live[ref_i]), len(keep)


def load_raw_lfp(raw_dir: Path, minutes: float, offset_min: float, cfg: dict, target_fs: float = 1250.0,
                 allow_deglitch: bool = True) -> tuple[np.ndarray, float, int]:
    """Read `minutes` of a RAW WILD session (amplifier.dat, int16, 64 ch, 20 kHz) starting at `offset_min`, de-glitch it when the
    firmware is below the clean gate, and decimate to target_fs (anti-aliased, chunked). No staging, no preprocessing needed."""
    cp = parse_ce_params(raw_dir)
    nch, fs0 = cp.n_channels or 64, float(cp.fs or 20000.0)
    ns = (raw_dir / "amplifier.dat").stat().st_size // (2 * nch)
    q = int(round(fs0 / target_fs))
    a0 = int(offset_min * 60 * fs0) if offset_min >= 0 else max(0, ns + int(offset_min * 60 * fs0))   # negative = minutes from the END
    win = int(min(ns - a0, minutes * 60 * fs0))
    mm = np.memmap(raw_dir / "amplifier.dat", dtype=np.int16, mode="r", shape=(ns, nch))
    deglitch = allow_deglitch and int(cp.firmware_version) < int(cfg.get("clean_firmware_min", 65))
    global DEGLITCH_APPLIED; DEGLITCH_APPLIED = bool(deglitch)
    thr = None
    chunks = []
    step = int(60 * fs0)
    S1 = np.zeros(nch); S2 = np.zeros((nch, nch)); N = 0          # spike-band correlation accumulators (300-3000 Hz at 20 kHz)
    for s0 in range(a0, a0 + win, step):
        x = np.asarray(mm[s0:min(a0 + win, s0 + step)]).astype(np.float32)
        if deglitch:
            if thr is None:
                dg = cfg.get("deglitch") or {}
                thr = estimate_thresholds(x, float(dg.get("k_mad", 10)), float(dg.get("floor_adc", 500)), block=min(100_000, len(x)), nblocks=min(8, max(1, len(x) // 100_000)))
            ref = med5(x); bad = np.abs(x - ref) > thr[None, :]; x[bad] = ref[bad]
        if N < 120 * fs0:                      # spike-band correlation from the first 2 min is enough for spacing (cost: filtfilt on 64 x 1.2M per chunk)
            hp = bp(x, fs0, 300.0, 3000.0).astype(np.float64)
            S1 += hp.sum(0); S2 += hp.T @ hp; N += hp.shape[0]
        # anti-alias with a 4th-order Butterworth low-pass at 0.4 x target Nyquist, then stride (the FIR `decimate` took minutes per window)
        b_lp, a_lp = butter(4, 0.4 * (target_fs / 2) / (fs0 / 2), btype="low")
        chunks.append(filtfilt(b_lp, a_lp, x, axis=0)[::q].astype(np.float64))
    mean = S1 / N; cov = S2 / N - np.outer(mean, mean); sd = np.sqrt(np.clip(np.diag(cov), 1e-12, None))
    C_hp = cov / np.outer(sd, sd)
    return np.concatenate(chunks, 0), fs0 / q, int(cp.firmware_version), C_hp


def state_bouts(states_mat: Path, state: str, edge_s: float, min_s: float, range_min=None, max_s: float | None = None) -> np.ndarray:
    """Bouts of one state from a SleepScoreMaster `<session>.SleepState.states.mat` (ints.<state>, seconds from the start of the
    session .lfp), each trimmed by edge_s at both ends (state transitions are fuzzy at the 1-s scoring step), clipped to
    range_min = (start, end) session minutes, kept when >= min_s remain, and cut to its middle max_s (short segments from many
    bouts sample the session better than a few long ones). Returns an (n, 2) array of session seconds."""
    from scipy.io import loadmat
    ints = loadmat(states_mat, simplify_cells=True)["SleepState"]["ints"]
    if state not in ints:
        raise SystemExit(f"{states_mat}: no ints.{state} (has {sorted(ints)})")
    x = np.asarray(ints[state], dtype=float)
    x = x.reshape(-1, 2) if x.size else np.zeros((0, 2))
    x = np.c_[x[:, 0] + edge_s, x[:, 1] - edge_s]
    if range_min is not None:
        x = np.c_[np.maximum(x[:, 0], range_min[0] * 60.0), np.minimum(x[:, 1], range_min[1] * 60.0)]
    x = x[(x[:, 1] - x[:, 0]) >= min_s]
    if max_s:
        mid = x.mean(1); half = np.minimum((x[:, 1] - x[:, 0]) / 2, max_s / 2)
        x = np.c_[mid - half, mid + half]
    return x


def select_bouts(bouts: np.ndarray, max_total_s: float) -> np.ndarray:
    """All bouts if they fit in max_total_s, else the largest set of bouts spread evenly over the range (not just the first ones)."""
    d = bouts[:, 1] - bouts[:, 0]
    if d.sum() <= max_total_s:
        return bouts
    best = None
    for m in range(1, len(bouts) + 1):
        idx = np.unique(np.round(np.linspace(0, len(bouts) - 1, m)).astype(int))
        if d[idx].sum() > max_total_s:
            break
        best = idx
    if best is None:                                   # the first bout alone is longer than the cap
        return np.array([[bouts[0, 0], bouts[0, 0] + max_total_s]])
    return bouts[best]


def load_bouts(lfp_path: Path, bouts_s: np.ndarray, fs: float, nch: int) -> tuple[np.ndarray, list, np.ndarray]:
    """Concatenate the bouts (session seconds) of a 1250-Hz session .lfp. Returns (lfp float64, [(start, end) sample of each bout
    in the concatenation], the bouts actually read in session seconds (n, 2))."""
    ns = lfp_path.stat().st_size // (2 * nch)
    mm = np.memmap(lfp_path, dtype=np.int16, mode="r", shape=(ns, nch))
    parts, bounds, used, n = [], [], [], 0
    for t0, t1 in bouts_s:
        s, e = int(round(t0 * fs)), min(ns, int(round(t1 * fs)))
        if e - s < int(fs):
            continue
        parts.append(np.asarray(mm[s:e]).astype(np.float64)); bounds.append((n, n + e - s)); used.append((s / fs, e / fs)); n += e - s
    if not parts:
        raise SystemExit(f"{lfp_path}: no usable bout")
    return np.concatenate(parts, 0), bounds, np.array(used)


def tv_and_flips(p: np.ndarray) -> tuple[float, int]:
    if p.size < 3:
        return float("nan"), 0
    rng = p.max() - p.min()
    tv = float(np.abs(np.diff(p)).sum() / rng) if rng > 0 else float("nan")
    s = np.sign(p[np.abs(p) > 0.15 * np.abs(p).max()])
    flips = int(np.sum(np.diff(s) != 0)) if s.size > 1 else 0
    return tv, flips


def tv_phase(deg: np.ndarray) -> float:
    if deg.size < 3 or np.any(np.isnan(deg)):
        return float("nan")
    u = np.degrees(np.unwrap(np.radians(deg)))
    rng = u.max() - u.min()
    return float(np.abs(np.diff(u)).sum() / rng) if rng > 1e-6 else float("nan")


C_HP = None   # spike-band (300-3000 Hz, 20 kHz) correlation matrix of the analysed window; set in raw/staged mode


def adjacent_r(rip_live: np.ndarray, live: np.ndarray, order: list[int]) -> np.ndarray:
    """Correlation between consecutive sites of `order`: the 20-kHz spike band when available (falls off over ~100 um, so it
    resolves site spacing), else the 130-200 Hz ripple band (volume-conducted, r 0.9-0.99 everywhere - NOT a spacing measure)."""
    if C_HP is not None:
        return np.array([float(C_HP[a, b]) for a, b in zip(order[:-1], order[1:])])
    idx = {int(c): i for i, c in enumerate(live)}
    out = []
    for a, b in zip(order[:-1], order[1:]):
        out.append(float(np.corrcoef(rip_live[:, idx[a]], rip_live[:, idx[b]])[0, 1]) if (a in idx and b in idx) else np.nan)
    return np.array(out)


def implied_sites(r_adj: np.ndarray, r_ref: float) -> np.ndarray:
    """distance between consecutive sites in units of one pitch, from exponential decay of correlation."""
    r = np.clip(r_adj, 1e-3, 0.999)
    return np.log(r) / np.log(np.clip(r_ref, 1e-3, 0.999))


def score_order(order: list[int], spw, rp, theta, rip_live, live, r_ref) -> dict:
    tv_s, fl = tv_and_flips(spw[order]); tv_r, _ = tv_and_flips(rp[order]); tv_t = tv_phase(theta[order])
    ra = adjacent_r(rip_live, live, order)
    gaps = implied_sites(ra, r_ref) if r_ref else np.full(len(order) - 1, np.nan)
    return {"spw_tv": tv_s, "flips": fl, "ripple_tv": tv_r, "theta_tv": tv_t, "r_adj": ra, "gaps": gaps}


def fmt_profile(order, spw, rp, theta, gaps=None) -> str:
    parts = []
    for i, c in enumerate(order):
        th = "" if np.isnan(theta[c]) else f"/{theta[c]:+.0f}d"
        parts.append(f"{c}:{spw[c]:+.0f}/{rp[c]:.0f}{th}")
        if gaps is not None and i < len(gaps) and not np.isnan(gaps[i]) and gaps[i] >= 1.5:
            parts.append(f"<gap {gaps[i]:.1f}>")
    return " ".join(parts)


DEGLITCH_APPLIED = None   # set by load_raw_lfp (raw mode)


def save_profile_npz(path: Path, *, lfp: np.ndarray, fs: float, peaks: np.ndarray, live: np.ndarray, dead: set, skipped: set,
                     spw, rp, theta, tpow, ref_col: int, nwin: int, n_rip: int, xml_path: Path, all_groups: list,
                     new_groups: list | None, meta: dict, wave_ms: float = 100.0, bounds=None, extra: dict | None = None) -> Path:
    """Keep every intermediate LFP profile of one window for later use (user, 2026-09-29):
    per-column SPW / ripple / theta profiles, the ripple times, ripple-triggered mean waveforms (1-50 Hz LFP and the 130-200 Hz
    envelope, +-wave_ms), per-column LFP rms, the spike-band correlation (raw mode), and the groupings they were read with.
    `extra` adds arrays (ripple_peaks_session_s, ripple_corr = event-averaged 130-200 Hz correlation between columns; in bout
    mode segments_session_s)."""
    slow = bp(lfp, fs, 1.0, 50.0, bounds=bounds)
    env = _segwise(lambda v: np.abs(hilbert(v, axis=0)), bp(lfp, fs, 130.0, 200.0, bounds=bounds), bounds)
    h = int(wave_ms / 1000 * fs)
    ok = peaks[(peaks > h) & (peaks < lfp.shape[0] - h)]
    spw_wave = np.mean([slow[t - h:t + h + 1] for t in ok], axis=0) * UV if len(ok) else np.full((2 * h + 1, lfp.shape[1]), np.nan)
    env_wave = np.mean([env[t - h:t + h + 1] for t in ok], axis=0) * UV if len(ok) else np.full((2 * h + 1, lfp.shape[1]), np.nan)
    flat = lambda gs: (np.array([c for g in gs for c in g], dtype=int), np.array([len(g) for g in gs], dtype=int))
    g_cols, g_len = flat(all_groups)
    d = dict(meta_json=json.dumps(meta), fs=fs, n_ripples=n_rip, ripple_peaks_samples=peaks.astype(np.int64),
             ripple_peaks_s_in_window=peaks / fs, live=np.asarray(live, dtype=int), dead=np.array(sorted(dead), dtype=int),
             skipped=np.array(sorted(skipped), dtype=int), spw_uV=np.asarray(spw), ripple_uV=np.asarray(rp),
             theta_phase_deg=np.asarray(theta), theta_power_uV2=np.asarray(tpow), theta_ref_col=ref_col, theta_n_windows=nwin,
             lfp_rms_uV=lfp.std(0) * UV, wave_t_ms=np.arange(-h, h + 1) / fs * 1000.0, spw_wave_uV=spw_wave,
             ripple_env_wave_uV=env_wave, xml_path=str(xml_path), xml_group_cols=g_cols, xml_group_len=g_len)
    if C_HP is not None:
        d["spikeband_corr"] = C_HP
    if new_groups is not None:
        d["derived_group_cols"], d["derived_group_len"] = flat(new_groups)
    d.update(extra or {})
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **d)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True); ap.add_argument("--animal", required=True); ap.add_argument("--session", required=True)
    ap.add_argument("--probe", default="A4x16-Lin-5mm-50s-300", choices=list(PROBE_XML))
    ap.add_argument("--sort-root", default=None)
    ap.add_argument("--minutes", type=float, default=10.0); ap.add_argument("--offset-min", type=float, default=None, help="window start in minutes; negative = from the end (raw mode); default: middle of the session")
    ap.add_argument("--thr", type=float, default=4.0); ap.add_argument("--max-rot", type=int, default=1); ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--bad", type=int, nargs="*", default=None, help="broken columns from visual inspection (Neuroscope)")
    ap.add_argument("--ref-group", type=int, default=None, help="1-based group of the current XML whose order is trusted: sets the 50-um correlation scale")
    ap.add_argument("--physical", action="store_true", help="candidates = physical_variants (matings incl. pin shifts) instead of the 16 full matings")
    ap.add_argument("--rank-by", default="all", choices=["all", "spw", "theta", "ripple"])
    ap.add_argument("--profile-only", action="store_true"); ap.add_argument("--show-top", type=int, default=2)
    ap.add_argument("--permute-tail", type=int, nargs=2, metavar=("GROUP", "N"), default=None, help="brute-force the last N sites of one current-XML group")
    ap.add_argument("--derive-xml", default=None); ap.add_argument("--keep-groups", type=int, nargs="*", default=[])
    ap.add_argument("--raw", default=None, help="RAW session folder (…/<MAC>/<session>): read amplifier.dat directly and decimate to 1250 Hz; no sort folder needed")
    ap.add_argument("--xml", default=None, help="grouping XML when there is no sort folder (default: the animal's xml: in probes_<cohort>.yaml)")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--no-deglitch", action="store_true", help="raw mode: do not de-glitch (the folder is an already de-glitched staged copy)")
    ap.add_argument("--save-profile", default=None, help="write all intermediate profiles of the window to this .npz")
    ap.add_argument("--imu-csv", default=None, help="per-second IMU table of the session (ephys/make_imu.py *.imu_1s.csv): keep only ripples "
                    "with the animal IMU-still for +-GATE s (NREM / quiet-wake SWRs; drops movement artefacts in the ripple band)")
    ap.add_argument("--session-offset-s", "--imu-offset-s", dest="session_offset_s", type=float, default=0.0,
                    help="session time (s) at the start of the analysed folder (a staged __w<S>s window starts at S); used by the IMU and state gates")
    ap.add_argument("--imu-thr", type=float, default=None, help="animal immobility threshold on vedba_mean (m/s^2; VeDBA valley, change_log 2026-09-28)")
    ap.add_argument("--imu-gate-s", type=float, default=2.0, help="the animal must be still for every second within +- this many seconds of the ripple")
    ap.add_argument("--lfp", default=None, help="BOUT mode: a full-session 1250-Hz .lfp (ephys/make_lfp.py, already de-glitched); analyse only "
                    "the --state bouts of --states, concatenated (filters and Hilbert run per bout; ripples < 150 ms from a join dropped)")
    ap.add_argument("--states", default=None, help="SleepScoreMaster <session>.SleepState.states.mat (the user-reviewed copy is "
                    "complex_system/<session>.SleepState.states.mat). With --lfp: the bouts to analyse; otherwise: keep only ripples inside the bouts")
    ap.add_argument("--state", default="NREMstate", choices=["NREMstate", "REMstate", "WAKEstate"])
    ap.add_argument("--edge-s", type=float, default=5.0, help="trim this much from both ends of every bout (state transitions are fuzzy)")
    ap.add_argument("--bout-min-s", type=float, default=15.0, help="use a bout only if this much remains after trimming")
    ap.add_argument("--bout-max-s", type=float, default=60.0, help="BOUT mode: use at most the middle this-many seconds of a bout (0 = whole bout)")
    ap.add_argument("--range-min", type=float, nargs=2, default=None, metavar=("START", "END"),
                    help="only bouts within these session minutes (stay inside one probe depth)")
    ap.add_argument("--max-bout-min", type=float, default=20.0, help="BOUT mode: at most this many minutes of bouts, spread evenly over the "
                    "range (memory ~1 GB per 20 min)")
    ap.add_argument("--theta-max-min", type=float, default=10.0, help="BOUT mode: theta profile from at most this many minutes of REM bouts in the same range")
    a = ap.parse_args()

    an = a.animal.upper(); an = f"SF{int(an[2:]):02d}" if an.startswith("SF") and an[2:].isdigit() else an
    sdir = sort_root(a.cohort, a.sort_root) / an / a.session
    seg_bounds = seg_s = None; th_lfp = th_bounds = None; theta_src = "the analysed window"
    if a.raw or a.lfp:
        from _common import PROJECT_ROOT, ephys_block
        import yaml
        cfg = ephys_block(a.cohort)
        xml_path = Path(a.xml) if a.xml else PROJECT_ROOT / yaml.safe_load((PROJECT_ROOT / cfg.get("probe_config", f"ephys/configs/probes_{a.cohort}.yaml")).read_text(encoding="utf-8"))["animals"][an]["xml"]
    if a.lfp and not a.states:                                       # plain window of a session .lfp
        lfp_path = Path(a.lfp)
        side = lfp_path.with_name(lfp_path.name + ".json")
        if side.exists():
            sj = json.loads(side.read_text(encoding="utf-8")); nch = int(sj["n_channels"]); fs = float(sj["fs_out"]); fw = sj.get("firmware")
        else:                                                         # any Neuroscope session: channel count / rate from the XML
            xr = ET.parse(xml_path).getroot(); fw = None
            nch = int(xr.findtext("acquisitionSystem/nChannels")); fs = float(xr.findtext("fieldPotentials/lfpSamplingRate") or 1250.0)
        off = a.offset_min if a.offset_min is not None else 0.0
        lfp, _, _ = load_bouts(lfp_path, np.array([[off * 60.0, (off + a.minutes) * 60.0]]), fs, nch)
        win = lfp.shape[0]; a0 = int(round(off * 60.0 * fs)); bad = set()
        print(f"   lfp window mode: {lfp_path} ({nch} ch, {fs:g} Hz), grouping XML {xml_path}")
    elif a.lfp:
        lfp_path = Path(a.lfp)
        side = lfp_path.with_name(lfp_path.name + ".json")
        sj = json.loads(side.read_text(encoding="utf-8")) if side.exists() else {}
        nch = int(sj.get("n_channels", 64)); fs = float(sj.get("fs_out", 1250.0)); fw = sj.get("firmware")
        if not side.exists():
            xr = ET.parse(xml_path).getroot()
            nch = int(xr.findtext("acquisitionSystem/nChannels")); fs = float(xr.findtext("fieldPotentials/lfpSamplingRate") or 1250.0)
        rng = tuple(a.range_min) if a.range_min else None
        avail = state_bouts(Path(a.states), a.state, a.edge_s, a.bout_min_s, rng, a.bout_max_s or None)
        if not len(avail):
            raise SystemExit(f"no {a.state} bout >= {a.bout_min_s:g} s after trimming {a.edge_s:g} s in range {rng}")
        lfp, seg_bounds, seg_s = load_bouts(lfp_path, select_bouts(avail, a.max_bout_min * 60.0), fs, nch)
        if a.state != "REMstate":
            rem = state_bouts(Path(a.states), "REMstate", a.edge_s, a.bout_min_s, rng, a.bout_max_s or None)
            if len(rem):
                th_lfp, th_bounds, rem_s = load_bouts(lfp_path, select_bouts(rem, a.theta_max_min * 60.0), fs, nch)
                theta_src = f"{len(rem_s)} REM bouts ({(rem_s[:, 1] - rem_s[:, 0]).sum() / 60:.1f} min)"
            else:
                theta_src = "the analysed bouts (no REM bout in range)"
        win = lfp.shape[0]; a0 = 0; bad = set()
        win_desc = (f"{len(seg_s)} {a.state} bouts, {win / fs / 60:.1f} of {(avail[:, 1] - avail[:, 0]).sum() / 60:.1f} min available "
                    f"(edges -{a.edge_s:g} s, >= {a.bout_min_s:g} s, middle <= {a.bout_max_s:g} s) within session min "
                    f"{(rng[0] if rng else 0):.0f}-{(rng[1] if rng else seg_s[-1, 1] / 60):.0f}")
        print(f"   bout mode: {lfp_path} (FM{fw}), states {a.states}, grouping XML {xml_path}")
    elif a.raw:
        off = a.offset_min if a.offset_min is not None else 0.0
        lfp, fs, fw, C_hp = load_raw_lfp(Path(a.raw), a.minutes, off, cfg, allow_deglitch=not a.no_deglitch)
        global C_HP; C_HP = C_hp
        nch = lfp.shape[1]; win = lfp.shape[0]; a0 = int(off * 60 * fs); bad = set()
        print(f"   raw mode: {a.raw} (FM{fw}), grouping XML {xml_path}")
    else:
        pm = json.loads((sdir / "preprocessSession_manifest.json").read_text(encoding="utf-8"))
        lfp_path = Path(pm["lfp_path"]); nch = int(pm["n_channels"]); fs = float(pm.get("sr_lfp") or 1250.0)
        bad = set(int(c) for c in (pm.get("bad_channels_0based") or []))
        ns = lfp_path.stat().st_size // (2 * nch)
        win = int(min(ns, a.minutes * 60 * fs))
        a0 = int(a.offset_min * 60 * fs) if a.offset_min is not None else max(0, (ns - win) // 2)
        lfp = np.asarray(np.memmap(lfp_path, dtype=np.int16, mode="r", shape=(ns, nch))[a0:a0 + win]).astype(np.float64)
        xml_path = Path(a.xml) if a.xml else sdir / f"{a.session}.xml"
    if seg_bounds is None:
        win_desc = f"{win / fs / 60:.0f} min from {a0 / fs / 60:.0f} min"
        to_session_s = lambda idx: a.session_offset_s + (a0 + np.asarray(idx, dtype=float)) / fs
    else:
        b_starts = np.array([b[0] for b in seg_bounds])
        def to_session_s(idx):
            idx = np.asarray(idx, dtype=float); k = np.searchsorted(b_starts, idx, side="right") - 1
            return seg_s[k, 0] + (idx - b_starts[k]) / fs
    flat = set(int(c) for c in np.where(lfp.std(0) < 1.0)[0])
    xroot = ET.parse(xml_path).getroot()
    skipped = set(int(c.text) for c in xroot.iter("channel") if c.get("skip") == "1")
    dead = bad | flat | skipped | (set(int(c) for c in a.bad) if a.bad else set())
    live = np.array([c for c in range(nch) if c not in dead])
    peaks, env, rip_live = detect_ripples(lfp, fs, live, thr=a.thr, bounds=seg_bounds)
    n_detected = int(len(peaks)); gate_info = None; state_info = None
    if seg_bounds is not None and len(peaks):                       # ripple-triggered windows must not cross a bout join
        joins = np.array([b for se in seg_bounds for b in se])
        peaks = peaks[np.min(np.abs(peaks[:, None] - joins[None, :]), axis=1) >= int(0.15 * fs)]
        print(f"   {len(peaks)}/{n_detected} ripples >= 150 ms from a bout edge")
    sec_grid = np.unique(np.floor(to_session_s(np.arange(0, lfp.shape[0], int(fs))))).astype(int)   # session seconds analysed
    if a.states and seg_bounds is None:
        bouts = state_bouts(Path(a.states), a.state, a.edge_s, a.bout_min_s)
        inside = lambda t: bool(np.any((bouts[:, 0] <= t) & (t <= bouts[:, 1])))
        keep = np.array([inside(t) for t in to_session_s(peaks)], dtype=bool)
        frac = float(np.mean([inside(s + 0.5) for s in sec_grid]))
        state_info = {"states": a.states, "state": a.state, "edge_s": a.edge_s, "bout_min_s": a.bout_min_s,
                      "n_detected": int(len(peaks)), "n_kept": int(keep.sum()), "window_state_fraction": frac}
        print(f"   state gate: {int(keep.sum())}/{len(peaks)} ripples inside {a.state} bouts (edges -{a.edge_s:g} s; window {frac:.0%} in state)")
        peaks = peaks[keep]
    if a.imu_csv:
        import pandas as pd
        if a.imu_thr is None:
            raise SystemExit("--imu-csv needs --imu-thr (the animal's VeDBA immobility threshold)")
        imu = pd.read_csv(a.imu_csv, usecols=["sec", "vedba_mean", "unreliable", "saturated"]).set_index("sec")
        still = (imu.vedba_mean < a.imu_thr) & (imu.unreliable == 0)
        keep = np.array([all(bool(still.get(s, False)) for s in range(int(np.floor(t - a.imu_gate_s)), int(np.floor(t + a.imu_gate_s)) + 1))
                         for t in to_session_s(peaks)], dtype=bool)
        still_frac = float(np.mean([bool(still.get(s, False)) for s in sec_grid]))
        win_start_s = float(to_session_s(0))
        gate_info = {"imu_csv": a.imu_csv, "session_offset_s": a.session_offset_s, "imu_thr": a.imu_thr, "gate_s": a.imu_gate_s,
                     "window_start_session_s": win_start_s, "n_detected": int(len(peaks)), "n_kept": int(keep.sum()),
                     "window_still_fraction": still_frac}
        print(f"   IMU gate: {int(keep.sum())}/{len(peaks)} ripples kept (animal still +-{a.imu_gate_s:g} s; analysed seconds still {still_frac:.0%}, "
              f"thr {a.imu_thr} m/s^2, session second {win_start_s:.0f} at the start)")
        peaks = peaks[keep]
    spw, rp, n = profiles(lfp, fs, peaks, env, live, bounds=seg_bounds)
    if th_lfp is None:
        th_lfp, th_bounds = lfp, seg_bounds
    theta, tpow, ref_col, nwin = theta_profile(th_lfp, fs, live, bounds=th_bounds)
    all_groups = [[int(c.text) for c in g.findall("channel")] for g in xroot.findall("anatomicalDescription/channelGroups/group")]
    xml_groups = [[c for c in g if c not in dead] for g in all_groups]
    print(f"== {an} {a.session}: {win_desc}, {len(live)} live columns (dead {sorted(dead)}), "
          f"{n} ripples, theta ref col {ref_col} over {nwin} x 2-s windows of {theta_src}")

    # reference correlation scale (one pitch)
    r_ref = None
    if a.ref_group and 1 <= a.ref_group <= len(xml_groups) and len(xml_groups[a.ref_group - 1]) >= 4:
        r_ref = float(np.nanmedian(adjacent_r(rip_live, live, xml_groups[a.ref_group - 1])))
        print(f"   spacing scale from group {a.ref_group}: median adjacent {'spike-band (300-3000 Hz)' if C_HP is not None else 'ripple-band'} r = {r_ref:.2f} == one pitch ({PITCH_UM:.0f} um)")

    print("   current XML per shank (top->bottom): col:SPW_uV/ripple/theta_deg  <gap n> = implied distance in sites where >= 1.5 (spike-band correlation)")
    cur = []
    for k, g in enumerate(xml_groups, 1):
        if len(g) < 4:
            continue
        sc = score_order(g, spw, rp, theta, rip_live, live, r_ref); cur.append(sc)
        print(f"     shank {k}: {fmt_profile(g, spw, rp, theta, sc['gaps'])}")
        print(f"              spw tv {sc['spw_tv']:.2f} flips {sc['flips']} | ripple tv {sc['ripple_tv']:.2f} | theta tv {sc['theta_tv']:.2f}"
              + (f" | adjacent r {np.round(sc['r_adj'], 2).tolist()}" if r_ref else ""))
    if cur:
        print(f"   current XML mean: spw tv {np.nanmean([c['spw_tv'] for c in cur]):.2f}, ripple tv {np.nanmean([c['ripple_tv'] for c in cur]):.2f}, "
              f"theta tv {np.nanmean([c['theta_tv'] for c in cur]):.2f}")

    if a.permute_tail:
        gi, nt = a.permute_tail; g = xml_groups[gi - 1]; head, tail = g[:-nt], g[-nt:]
        res = []
        for perm in itertools.permutations(tail):
            o = head + list(perm); sc = score_order(o, spw, rp, theta, rip_live, live, r_ref)
            res.append((sc["spw_tv"] + sc["ripple_tv"] + (sc["theta_tv"] if not np.isnan(sc["theta_tv"]) else 3.0), sc, o))
        res.sort(key=lambda t: t[0])
        print(f"   permutations of the last {nt} sites of group {gi} ({len(res)}): best 5 by spw+ripple+theta tv (current order marked)")
        for tot, sc, o in res[:5]:
            print(f"     {tot:.2f}  {'<== current' if o == g else '           '} {fmt_profile(o[-nt - 1:], spw, rp, theta)}  spw {sc['spw_tv']:.2f} rip {sc['ripple_tv']:.2f} th {sc['theta_tv']:.2f}")
        cur_tot = next(t for t, sc, o in res if o == g)
        print(f"     current order total {cur_tot:.2f}, rank {sorted(t for t, _, _ in res).index(cur_tot) + 1}/{len(res)}")

    if a.derive_xml:
        from make_session_xml import build_session_xml, write_xml
        new_groups = []
        print("   data-derived order (oriens -> pyramidale -> radiatum), per group; dead columns inserted at detected gaps when possible:")
        for k, g in enumerate(all_groups, 1):
            livec = [c for c in g if c not in dead]; deadc = [c for c in g if c in dead]
            if k in a.keep_groups or len(livec) < 4:
                new_groups.append(g); print(f"     group {k}: kept as is ({len(livec)} live)"); continue
            pos = sorted([c for c in livec if spw[c] >= 0], key=lambda c: rp[c])
            neg = sorted([c for c in livec if spw[c] < 0], key=lambda c: -spw[c])
            o = pos + neg
            sc = score_order(o, spw, rp, theta, rip_live, live, r_ref)
            # dead columns are PACE MAKERS: each goes where the SPW gradient of its shank shows the largest gap, never at the end
            # (user 2026-09-08: "dead channel 不能在最后, 因为这样会影响对 channel 物理位置的判断; 归属可以根据 LFP 梯度 difference 给出").
            seq = [[c, float(spw[c])] for c in o]
            for dc in deadc:
                if len(seq) < 2:
                    seq.append([dc, 0.0]); continue
                gaps = [abs(seq[i + 1][1] - seq[i][1]) for i in range(len(seq) - 1)]
                j = int(np.argmax(gaps))
                seq.insert(j + 1, [dc, (seq[j][1] + seq[j + 1][1]) / 2])
            placed = [c for c, _ in seq]
            print(f"     group {k}: {fmt_profile(o, spw, rp, theta, sc['gaps'])}  | spw tv {sc['spw_tv']:.2f} rip {sc['ripple_tv']:.2f} th {sc['theta_tv']:.2f}"
                  + (f"  | dead placed: {[c for c in placed if c in dead]} at positions {[placed.index(c) + 1 for c in placed if c in dead]}" if deadc else ""))
            new_groups.append(placed)
        desc = (f"{an} data-derived within-shank order from the ripple-triggered LFP profile of {a.session} ({n} ripples, {win_desc}): "
                f"positive-SPW sites by ripple power asc, then negative-SPW sites by SPW desc; groups {sorted(a.keep_groups)} kept from the verified map; "
                f"dead columns {sorted(dead & set(c for g in all_groups for c in g))} skip=1, placed as pace makers at the largest SPW-gradient gap of their shank; "
                f"channels = exported columns")
        out = write_xml(build_session_xml(n_channels=nch, fs=20000.0, groups=new_groups, reject=sorted(dead), layout="linear", description_extra=desc), Path(a.derive_xml))
        print(f"   -> {out}")
    if a.save_profile:
        meta = {"animal": an, "session": a.session, "source": a.lfp or a.raw or str(sdir),
                "mode": "bouts" if seg_bounds is not None else ("lfp_window" if a.lfp else ("raw" if a.raw else "sort")), "window_desc": win_desc,
                "window_start_min": float(to_session_s(0) / 60), "window_min": float(win / fs / 60), "fs": fs, "ripple_thr_z": a.thr,
                "grouping_xml": str(xml_path), "firmware": (fw if (a.raw or a.lfp) else None),
                "deglitch_applied": DEGLITCH_APPLIED if a.raw else None, "units": "uV relative (0.195 uV/count)",
                "imu_gate": gate_info, "state_gate": state_info, "n_ripples_detected": n_detected, "theta_source": theta_src,
                "bouts": ({"states": a.states, "state": a.state, "edge_s": a.edge_s, "bout_min_s": a.bout_min_s,
                           "bout_max_s": a.bout_max_s, "range_min": a.range_min, "max_bout_min": a.max_bout_min, "n_bouts": int(len(seg_s)),
                           "total_min": float(win / fs / 60)} if seg_bounds is not None else None),
                "git_commit": git_commit(), "written_utc": utc_now_iso()}
        extra = {"ripple_peaks_session_s": to_session_s(peaks), "ripple_corr": ripple_corr(rip_live, peaks, fs, live, nch)}
        if seg_bounds is not None:
            extra["segments_session_s"] = seg_s
        out_npz = save_profile_npz(Path(a.save_profile), lfp=lfp, fs=fs, peaks=peaks, live=live, dead=dead, skipped=skipped, spw=spw,
                                   rp=rp, theta=theta, tpow=tpow, ref_col=ref_col, nwin=nwin, n_rip=n, xml_path=xml_path,
                                   all_groups=all_groups, new_groups=locals().get("new_groups") if a.derive_xml else None, meta=meta,
                                   bounds=seg_bounds, extra=extra)
        print(f"   profiles -> {out_npz}")
    if a.profile_only or a.derive_xml or a.permute_tail:
        return

    groups_v1 = load_groups(PROBEMAPS / PROBE_XML[a.probe][0])
    user_bad = set(int(c) for c in a.bad) if a.bad else set()
    fam = physical_variants(groups_v1, 2) if a.physical else {k: {"groups": v, "dead_intan": [], "desc": k} for k, v in connector_variants(groups_v1).items()}
    rows = []
    for vname, var in fam.items():
        for r0 in range(-a.max_rot, a.max_rot + 1):
            for r1 in range(-a.max_rot, a.max_rot + 1):
                P = rotation_permutation(r0, r1)
                shank, depth = candidate_sites(var["groups"], P)
                pred_dead = sorted(int(P[i]) for i in var["dead_intan"])
                dead_ok = (not pred_dead) or set(pred_dead) <= (user_bad | skipped | bad)
                scs = []
                for k in range(len(var["groups"])):
                    cols = [c for c in np.where(shank == k)[0] if c not in dead]
                    if len(cols) < 6:
                        continue
                    cols = sorted(cols, key=lambda c: depth[c])
                    scs.append(score_order(cols, spw, rp, theta, rip_live, live, r_ref))
                if not scs:
                    continue
                rows.append({"variant": vname, "desc": var["desc"], "rot_bank0": r0, "rot_bank1": r1, "n_shanks": len(scs),
                             "spw_tv": float(np.nanmean([s["spw_tv"] for s in scs])), "ripple_tv": float(np.nanmean([s["ripple_tv"] for s in scs])),
                             "theta_tv": float(np.nanmean([s["theta_tv"] for s in scs])), "flips": float(np.mean([s["flips"] for s in scs])),
                             "pred_dead": pred_dead, "dead_ok": dead_ok})
    for key in ("spw_tv", "ripple_tv", "theta_tv"):
        order = sorted(range(len(rows)), key=lambda i: (np.nan_to_num(rows[i][key], nan=9.0)))
        for rank, i in enumerate(order, 1):
            rows[i][key + "_rank"] = rank
    for r in rows:
        r["rank_sum"] = {"all": r["spw_tv_rank"] + r["ripple_tv_rank"] + r["theta_tv_rank"], "spw": r["spw_tv_rank"], "theta": r["theta_tv_rank"], "ripple": r["ripple_tv_rank"]}[a.rank_by]
    rows.sort(key=lambda r: (not r["dead_ok"], r["rank_sum"]))
    ref = next((r for r in rows if r["variant"] == "v1_raw" and r["rot_bank0"] == 1 and r["rot_bank1"] == 0), None)
    print(f"   {len(rows)} candidates ({'physical incl. pin shifts' if a.physical else '16 full matings'} x rotations); ranked by {a.rank_by}; dead_ok = predicted dead columns inside the broken list")
    for i, r in enumerate(rows[:a.top]):
        tag = "  <== SF07's map" if r is ref else ""
        print(f"   {i + 1:3d}. {r['variant']:14s} rot0 {r['rot_bank0']:+d} rot1 {r['rot_bank1']:+d}  spw {r['spw_tv']:.2f} rip {r['ripple_tv']:.2f} th {r['theta_tv']:.2f} "
              f"flips {r['flips']:.1f}  ranks {r['spw_tv_rank']}/{r['ripple_tv_rank']}/{r['theta_tv_rank']}  dead_ok {r['dead_ok']}"
              + (f" pred_dead {r['pred_dead']}" if r["pred_dead"] else "") + f"  [{r['desc']}]{tag}")
    if ref is not None and ref not in rows[:a.top]:
        print(f"   ref. v1_raw +1/+0 (ProbeMaps standard order; = SF07's own mating, not a reference for other animals): rank {rows.index(ref) + 1}, spw {ref['spw_tv']:.2f} rip {ref['ripple_tv']:.2f} th {ref['theta_tv']:.2f}")
    for r in rows[:a.show_top]:
        var = fam[r["variant"]]; P = rotation_permutation(r["rot_bank0"], r["rot_bank1"]); shank, depth = candidate_sites(var["groups"], P)
        print(f"   profiles under {r['variant']} {r['rot_bank0']:+d}/{r['rot_bank1']:+d}:")
        for k in range(len(var["groups"])):
            cols = sorted([c for c in np.where(shank == k)[0] if c not in dead], key=lambda c: depth[c])
            if len(cols) < 6:
                continue
            sc = score_order(cols, spw, rp, theta, rip_live, live, r_ref)
            print(f"     shank {k + 1}: {fmt_profile(cols, spw, rp, theta, sc['gaps'])}  | spw {sc['spw_tv']:.2f} rip {sc['ripple_tv']:.2f} th {sc['theta_tv']:.2f}")
    if not a.no_write and rows:
        out = report_dir(a.cohort) / f"ephys_spikes_lfp_profile_check_{a.cohort}.csv"
        new = not out.exists()
        with open(out, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["written_utc", "animal", "session", "minutes", "n_ripples", "n_live", "family", "rank_by", "rank", "variant", "desc", "rot_bank0", "rot_bank1",
                            "spw_tv", "ripple_tv", "theta_tv", "flips", "dead_ok", "pred_dead", "repo_git"])
            for i, r in enumerate(rows[:a.top]):
                w.writerow([utc_now_iso(), an, a.session, a.minutes, n, len(live), "physical" if a.physical else "matings", a.rank_by, i + 1, r["variant"], r["desc"],
                            r["rot_bank0"], r["rot_bank1"], round(r["spw_tv"], 3), round(r["ripple_tv"], 3), round(r["theta_tv"], 3) if not np.isnan(r["theta_tv"]) else "",
                            round(r["flips"], 2), r["dead_ok"], " ".join(map(str, r["pred_dead"])), git_commit()])
        print(f"   -> {out}")


if __name__ == "__main__":
    main()
