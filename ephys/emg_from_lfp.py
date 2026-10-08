r"""EMG from LFP for every cohort-3 session: the standard buzcode product plus a fast 50-Hz version.

The user, 2026-10-08: "LFP-EMG is useful, save it (like W:\data\PPP\PPP7\day8)"; "its time resolution may not be enough".

Input  <lfp_root>/<SFxx>/<session>.lfp (+ .lfp.json), from ephys/make_lfp.py:
- 64 channels, int16, 1250 Hz;
- Butterworth-5 450-Hz low-pass of the raw amplifier.dat;
- lfp[k] <-> amplifier sample 16 k.

Output <out>/<SFxx>/

<session>.EMGFromLFP.LFP.mat — STANDARD, the lab's format (e.g. W:\data\PPP\PPP7\day8\day8.EMGFromLFP.LFP.mat).
- Computed by PreprocessPipeline's own state_scoring._compute_emg_from_lfp (= neurocode lfp/getEMGFromLFP.m), so it
  equals what the sleep scorer's lfpemg variant computes for this session and XML.
- Band: Butterworth-3 band-pass 300-600 Hz. Effectively 300-450 Hz here, because the .lfp is low-passed at 450 Hz.
- Value: the mean pairwise Pearson correlation between channels.
- Windows: +-0.5 s, every 0.5 s (2 Hz).
- Channels: one per shank, the first usable channel of each XML spike group. Rejects = the XML's skip='1' + the probes
  YAML reject_channels.
- Fields: timestamps (s from the session start), data, channels (1-based), detectorName, samplingFrequency.

<session>.EMGFromLFP50Hz.npz — FAST: same band and filter, 50 Hz.
- Bin centres every 25 LFP samples (20 ms). Bin j sits at amplifier sample 400 j, the same grid as make_imu's 50-Hz
  samples (amp_sample = 400 i).
- Window: +-31 LFP samples (50.4 ms).
- Channels: the first and last usable channel of every shank in XML order (top and bottom site, 2 per shank).
- Arrays:
      j            int64    bin index (amp_sample = 400 j; LFP sample = 25 j)
      t_pc_ms      float64  field-PC ms since the session-start day's midnight, not wrapped (pc_time_fit.json formula,
                            as make_imu's t_pc_ms); NaN without a fit
      corr         float32  mean pairwise correlation, -1..1. Muscle activity is volume-conducted and so correlated on
                            all channels; spikes / MUA are local and uncorrelated.
      log_rms      float32  mean over channels of log10 RMS of the band (ADC units, 0.195 uV/bit). Amplitude, which
                            local spikes also raise.
      channels     int16    1-based exported columns used

<session>.EMGFromLFP.json — parameters, channels of both products, commit, elapsed time.

Usage:
    python ephys/emg_from_lfp.py --lfp-root <root> --out <dir> [--animal SF08] [--session <s>] \
        [--pc-time-root <.../analysis/pc_time>] [--workers N] [--redo] [--pipeline-root <PreprocessPipeline>]
    python ephys/emg_from_lfp.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import yaml
from scipy import signal

sys.path.insert(0, str(Path(__file__).parent))
from _common import ephys_block, git_commit  # noqa: E402
from make_imu import pc_time_ms  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FS = 1250.0
NCH = 64
STEP = 25                      # LFP samples per fast bin (20 ms)
HALF = 31                      # fast window half-width in LFP samples (window 63 samples = 50.4 ms)
CHUNK = 75000                  # LFP samples per processing chunk (60 s)
MARGIN = 1250                  # filter margin on each side of a chunk (1 s)
BAND = (300.0, 600.0)          # as the pipeline: lo 300, hi = max(625, fs/2) - 25


def band_sos() -> np.ndarray:
    return signal.butter(3, [BAND[0] / (FS / 2), min(0.999, BAND[1] / (FS / 2))], btype="bandpass", output="sos")


def shank_channels(cohort: str, animal: str) -> tuple[dict, list[list[int]], set[int]]:
    """Session struct (score_sleep), spike groups (1-based, XML order) and the reject set (1-based)."""
    from score_sleep import session_struct
    st = session_struct(cohort, animal)
    groups = [[int(round(c)) for c in np.asarray(g).ravel()] for g in st["extracellular"]["spikeGroups"]["channels"]]
    probes = yaml.safe_load(open(PROJECT_ROOT / ephys_block(cohort)["probe_config"], encoding="utf-8"))
    entry = (probes.get("animals") or probes).get(animal) or {}
    reject = {int(c) + 1 for c in (entry.get("reject_channels") or [])}
    reject |= {int(round(c)) for c in np.asarray(st["channelTags"]["Bad"]["channels"]).ravel()}
    return st, groups, reject


def fast_channels(groups: list[list[int]], reject: set[int]) -> list[int]:
    out = []
    for g in groups:
        keep = [c for c in g if c not in reject and 1 <= c <= NCH]
        if keep:
            out += [keep[0], keep[-1]] if len(keep) > 1 else [keep[0]]
    return sorted(set(out))


def window_stats(x: np.ndarray, centres: np.ndarray, half: int) -> tuple[np.ndarray, np.ndarray]:
    """Mean pairwise correlation and mean log10 RMS of the columns of x in windows [c-half, c+half] (inclusive),
    by cumulative sums (exact up to float rounding; = the pipeline's per-window Pearson r)."""
    n_w = 2 * half + 1
    C = x.shape[1]
    z = np.zeros((1, C))
    S1 = np.vstack([z, np.cumsum(x, axis=0)])
    S2 = np.vstack([z, np.cumsum(x * x, axis=0)])
    lo, hi = centres - half, centres + half + 1
    sx = S1[hi] - S1[lo]
    var = (S2[hi] - S2[lo]) - sx * sx / n_w                    # n_w * window variance, per channel
    var = np.maximum(var, 0.0)
    pi, pj = np.triu_indices(C, k=1)
    r_sum = np.zeros(len(centres))
    for i, j in zip(pi, pj):
        sxy = np.r_[0.0, np.cumsum(x[:, i] * x[:, j])]
        cov = (sxy[hi] - sxy[lo]) - sx[:, i] * sx[:, j] / n_w
        den = np.sqrt(var[:, i] * var[:, j])
        r_sum += np.divide(cov, den, out=np.zeros_like(cov), where=den > 0)
    corr = r_sum / max(len(pi), 1)
    log_rms = np.log10(np.sqrt(var / n_w) + 1e-3).mean(axis=1)
    return corr, log_rms


def read_columns(lfp_path: Path, chans_1based: list[int], frames_per_read: int = 200000) -> np.ndarray:
    """The requested columns of the whole .lfp, read sequentially in large blocks (int16, frames x columns). A column
    index of a memmap reads the file page by page, which on the BioHPC NFS storage took > 14 min for one session."""
    n = os.path.getsize(lfp_path) // (NCH * 2)
    c0 = np.asarray(chans_1based, dtype=np.int64) - 1
    out = np.empty((n, len(c0)), dtype=np.int16)
    with open(lfp_path, "rb") as f:
        a = 0
        while a < n:
            m = min(frames_per_read, n - a)
            blk = np.fromfile(f, dtype=np.int16, count=m * NCH).reshape(m, NCH)
            out[a:a + m] = blk[:, c0]
            a += m
    return out


def fast_product(cols: np.ndarray, chans: list[int], all_chans: list[int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """cols = read_columns(...) for `all_chans`; the fast product uses the subset `chans`."""
    mm = cols
    n = mm.shape[0]
    c0 = np.asarray([all_chans.index(c) for c in chans])
    sos = band_sos()
    j_first = -(-HALF // STEP)                                  # first centre with a full window
    j_last = (n - 1 - HALF) // STEP
    J, R, L = [], [], []
    for a in range(j_first * STEP, (j_last + 1) * STEP, CHUNK):
        js = np.arange(-(-a // STEP), min(j_last, (a + CHUNK - 1) // STEP) + 1)
        if not len(js):
            continue
        cen = js * STEP
        s0 = max(0, cen[0] - HALF - MARGIN)
        s1 = min(n, cen[-1] + HALF + 1 + MARGIN)
        x = signal.sosfiltfilt(sos, np.asarray(mm[s0:s1][:, c0], dtype=np.float64), axis=0)
        r, lr = window_stats(x, cen - s0, HALF)
        J.append(js)
        R.append(r)
        L.append(lr)
    return np.concatenate(J), np.concatenate(R).astype(np.float32), np.concatenate(L).astype(np.float32)


def load_fit(root: str | None, animal: str, session: str) -> dict | None:
    if not root:
        return None
    f = Path(root) / animal / session / "pc_time_fit.json"
    return json.loads(f.read_text()) if f.exists() else None


def one_session(job: dict) -> dict:
    t0 = time.time()
    animal, session = job["animal"], job["session"]
    lfp = Path(job["lfp_root"]) / animal / f"{session}.lfp"
    od = Path(job["out"]) / animal
    od.mkdir(parents=True, exist_ok=True)
    jf = od / f"{session}.EMGFromLFP.json"
    if jf.exists() and not job["redo"]:
        return {"animal": animal, "session": session, "status": "exists"}
    sys.path.insert(0, job["pipeline_root"])
    import src.preprocess.state_scoring as ss          # noqa: E402
    st, groups, reject = shank_channels(job["cohort"], animal)
    # The pipeline parses spikeGroups with np.asarray(..., dtype=object).reshape(-1): a Python list of equal-length
    # groups (every A4x16 animal) becomes a 2-D array and then 64 one-channel "groups", so all 64 channels were used
    # (found 2026-10-08; the scorer's lfpemg pilot files have that). A 1-D object array keeps one entry per shank.
    sg = np.empty(len(groups), dtype=object)
    sg[:] = [np.asarray(g, dtype=np.float64) for g in groups]
    st["extracellular"]["spikeGroups"]["channels"] = sg
    std_ch = [int(c) for c in ss._select_emg_channels(ss._extract_spike_groups_1based(st), reject, n_channels=NCH)]
    ch = fast_channels(groups, reject)
    all_ch = sorted(set(std_ch) | set(ch))
    cols = read_columns(lfp, all_ch)                    # one sequential read serves both products
    t_read = time.time()

    def from_memory(path, n_channels, channels_1based):  # = the pipeline's _load_binary_lfp_channels, from `cols`
        c = np.unique(np.asarray(channels_1based, dtype=np.int64).reshape(-1))
        return cols[:, [all_ch.index(int(x)) for x in c]], c, {int(x): i for i, x in enumerate(c.tolist())}
    orig = ss._load_binary_lfp_channels
    ss._load_binary_lfp_channels = from_memory
    try:
        emg, mat = ss._compute_emg_from_lfp(basepath=od, basename=session, lfp_path=lfp, session_struct=st,
                                            reject_channels_1based=np.asarray(sorted(reject)), overwrite=True)
    finally:
        ss._load_binary_lfp_channels = orig
    t1 = time.time()
    j, corr, lrms = fast_product(cols, ch, all_ch)
    del cols
    fit = load_fit(job.get("pc_time_root"), animal, session)
    tpc = pc_time_ms(j * 400, fit)
    tpc = np.full(len(j), np.nan) if tpc is None else tpc
    tmp = od / f"{session}.EMGFromLFP50Hz.tmp.npz"
    np.savez(tmp, j=j.astype(np.int64), t_pc_ms=tpc.astype(np.float64), corr=corr, log_rms=lrms,
             channels=np.asarray(ch, np.int16))
    os.replace(tmp, od / f"{session}.EMGFromLFP50Hz.npz")
    side = json.loads((lfp.parent / f"{session}.lfp.json").read_text()) if (lfp.parent / f"{session}.lfp.json").exists() else {}
    info = {"animal": animal, "session": session, "cohort": job["cohort"], "lfp": str(lfp), "start_local": side.get("start_local"),
            "n_lfp_samples": int(os.path.getsize(lfp) // (NCH * 2)),
            "standard": {"file": mat.name, "channels_1based": [int(c) for c in np.asarray(emg["channels"]).ravel()],
                         "sampling_frequency_hz": 2, "window_s": "+-0.5", "band_hz": "300-600 Butterworth-3 filtfilt (effective 300-450)",
                         "implementation": "PreprocessPipeline state_scoring._compute_emg_from_lfp (LFP columns read once, sequentially)",
                         "read_s": round(t_read - t0, 1), "elapsed_s": round(t1 - t_read, 1)},
            "fast": {"file": f"{session}.EMGFromLFP50Hz.npz", "channels_1based": ch, "bin_step_lfp_samples": STEP,
                     "bin_step_amp_samples": STEP * 16, "window_lfp_samples": 2 * HALF + 1, "window_ms": round((2 * HALF + 1) / FS * 1000, 1),
                     "band_hz": "300-600 Butterworth-3 sosfiltfilt per 60-s chunk with 1-s margins (effective 300-450)",
                     "n_bins": int(len(j)), "elapsed_s": round(time.time() - t1, 1)},
            "reject_channels_1based": sorted(reject), "spike_groups_1based": groups,
            "pc_time": "pc_time_fit.json formula (make_imu.pc_time_ms)" if fit else "none",
            "pc_time_fit": {k: fit.get(k) for k in ("verdict", "drift_ppm", "offset_ms", "n_anchors")} if fit else None,
            "pipeline_root": job["pipeline_root"], "git_commit": job["git_commit"],
            "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    jf.write_text(json.dumps(info, indent=1))
    return {"animal": animal, "session": session, "status": "ok", "elapsed_s": round(time.time() - t0, 1),
            "n_fast_channels": len(ch), "n_std_channels": len(info["standard"]["channels_1based"])}


def selftest() -> None:
    """Synthetic: 8 channels = independent noise + a common 'muscle' burst on all channels in one second; the fast
    corr must rise from ~0 to ~0.8 inside the burst, follow it within one bin, and window_stats must equal a direct
    per-window Pearson computation."""
    rng = np.random.default_rng(0)
    n = int(FS * 10)
    x = rng.normal(0, 1, (n, 8))
    burst = slice(int(5 * FS), int(6 * FS))
    common = rng.normal(0, 2, burst.stop - burst.start)
    x[burst] += common[:, None]
    xf = signal.sosfiltfilt(band_sos(), x, axis=0)
    cen = np.arange(HALF, n - HALF, STEP)
    r, lr = window_stats(xf, cen, HALF)
    # direct check on 20 random windows
    for c in rng.choice(cen, 20, replace=False):
        w = xf[c - HALF:c + HALF + 1]
        cc = np.corrcoef(w.T)[np.triu_indices(8, 1)].mean()
        k = np.flatnonzero(cen == c)[0]
        assert abs(cc - r[k]) < 1e-9, (cc, r[k])
    t = cen / FS
    inside = (t > 5.1) & (t < 5.9)
    outside = (t < 4.5) | (t > 6.5)
    assert r[inside].mean() > 0.7 and abs(r[outside].mean()) < 0.05, (r[inside].mean(), r[outside].mean())
    onset = t[np.argmax(r > 0.4)]
    assert abs(onset - 5.0) < 0.05, onset
    assert lr[inside].mean() > lr[outside].mean() + 0.3
    assert fast_channels([[1, 2, 3], [4], [5, 6]], {2}) == [1, 3, 4, 5, 6]
    print(f"selftest PASS: corr inside {r[inside].mean():.2f} / outside {r[outside].mean():.3f}; onset {onset:.3f} s; "
          f"window_stats = direct Pearson on 20 windows")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--lfp-root")
    ap.add_argument("--out")
    ap.add_argument("--animal", nargs="*")
    ap.add_argument("--session", nargs="*")
    ap.add_argument("--pc-time-root")
    ap.add_argument("--pipeline-root", default=os.environ.get("PREPROCESS_PIPELINE_ROOT", "D:/Documents/ayalab/PreprocessPipeline"))
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    root = Path(a.lfp_root)
    specs = [(p.parent.name, p.name[:-4]) for p in sorted(root.glob("*/*.lfp"))]
    if a.animal:
        specs = [s for s in specs if s[0] in a.animal]
    if a.session:
        specs = [s for s in specs if s[1] in a.session]
    gc = git_commit()
    jobs = [{"cohort": a.cohort, "animal": an, "session": s, "lfp_root": str(root), "out": a.out, "redo": a.redo,
             "pc_time_root": a.pc_time_root, "pipeline_root": a.pipeline_root, "git_commit": gc} for an, s in specs]
    print(f"{len(jobs)} sessions -> {a.out}  workers {a.workers}  commit {gc}", flush=True)
    err = Path(a.out) / "_errors"
    n_bad = 0
    with ProcessPoolExecutor(a.workers) as ex:
        futs = {ex.submit(one_session, j): j for j in jobs}
        for f in as_completed(futs):
            j = futs[f]
            try:
                print(json.dumps(f.result()), flush=True)
            except Exception:
                n_bad += 1
                err.mkdir(parents=True, exist_ok=True)
                (err / f"{j['animal']}_{j['session']}.txt").write_text(traceback.format_exc())
                print(f"ERROR {j['animal']} {j['session']} -> {err}", flush=True)
    print(f"done: {len(jobs) - n_bad} ok, {n_bad} errors", flush=True)
    write_readme(Path(a.out), root, a.pc_time_root, a.pipeline_root, gc)
    sys.exit(1 if n_bad else 0)


def write_readme(out: Path, lfp_root: Path, pc_root: str | None, pp_root: str, gc: str) -> None:
    import subprocess
    ppc = subprocess.run(["git", "-C", pp_root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip() or "unknown"
    n = len(list(out.glob("SF*/*.EMGFromLFP.json")))
    (out / "README.md").write_text(f"""# LFP-EMG, cohort 2026c (one folder per animal)

Made by ephys/emg_from_lfp.py (repo commit {gc}; PreprocessPipeline commit {ppc}), {time.strftime('%Y-%m-%d %H:%M')}, from
{lfp_root}/<SFxx>/<session>.lfp (1250 Hz, 450-Hz low-pass; storage analysis/lfp); field-PC time from {pc_root}.
{n} sessions. The tool's docstring has the full definitions.

- <session>.EMGFromLFP.LFP.mat: the lab's standard product (the format of day8.EMGFromLFP.LFP.mat of PPP7 on ayadata;
  neurocode getEMGFromLFP = PreprocessPipeline state_scoring._compute_emg_from_lfp). Mean pairwise correlation of the
  300-600 Hz band (effectively 300-450 Hz here), +-0.5-s windows at 2 Hz, one channel per shank (the first usable
  channel of each spike group of the current XML, ephys/configs/probes_2026c.yaml). Timestamps are seconds from the
  session start.
- <session>.EMGFromLFP50Hz.npz: the fast version for event work. Same band, 50.4-ms windows every 20 ms, two channels
  per shank. j = bin index (amplifier sample 400 j = make_imu's 50-Hz sample j), t_pc_ms = field-PC ms since the
  session-start day's midnight (pc_time_fit.json formula), corr, log_rms (log10 RMS of the band, ADC units), channels.
- <session>.EMGFromLFP.json: channels of both products, parameters, timing.

Caveats:
- SF07 carries a large common-mode signal on all channels (probes_2026c.yaml), so its correlation baseline is high.
  Use changes, not absolute levels.
- SF12's contacts fail from 2026-09-10 14:53:45 (cohorts/2026c.yaml quality_flags).
- The scorer's earlier lfpemg pilot files used all 64 channels: the pipeline flattens a Python list of equal-length spike
  groups. These files use one channel per shank.
""", encoding="utf-8")


if __name__ == "__main__":
    main()
