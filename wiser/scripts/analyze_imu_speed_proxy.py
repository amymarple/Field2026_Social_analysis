r"""Head-IMU speed reference, independent of the WISER smoother (cohort 2026c) - step B of A -> B -> C.

Plan: implementation_plan/2026-10-03-imu-speed-proxy.md (approved by the user 2026-10-03, "干吧"; operational details in
its Amendment 1, written before any number). Report (full Definitions section):
results/<cohort>/wiser_baseline/reports/wiser_baseline_imu_speed_proxy_<cohort>.md

  Reference 1  clean WISER speed: u3(s) = |m(c + 1.5) - m(c - 1.5)| / 3 s, m = coordinate-wise median of the raw fixes
               (aligned times) in [t - 0.5, t + 0.5) (>= 3 fixes), c = s + 0.5; u1 from medians over 0.75 s at c +- 0.5.
               Clean second: every fix in [c - 2, c + 2] has >= 8 anchors, is valid and unmasked, no jump (> 30 in in
               <= 0.35 s), >= 12 fixes, both u3 medians >= 14 in outside the house ROIs, the second IMU-QC-ok.
               Noise floor = the same estimators on the audit's certified still segments (>= 8 anchors).
  Reference 2  IMU speed proxy: per-second features of the make_imu 50-Hz record over the 1-s and 3-s windows of the
               second (cached once under <OUT>/<cohort>/imu_speed_features/), M1 = per-animal OLS on [VeDBA mean,
               stride-band power, stride peak frequency, |w| mean], M2 = pooled HistGradientBoosting (absolute error)
               on all features + animal one-hot, grid chosen on the tuning night; train 09-05/06, tune 09-07, test 09-08,
               rain nights 09-03/09 = robustness. Validity rule (test night, clean seconds) at 3 s and 1 s.
  Re-scoring   R1: each track's speed (same median estimator on the track) vs the clean reference, p50/p95 bias, median
               absolute error, speed bands, paired 10-min block bootstrap. R2 vs the proxy only where it is valid.
  Deliverable  only if valid: the chosen model on every QC-ok second of the audit nights -> <OUT>/<cohort>/imu_speed_proxy/.

Inputs (all read-only): the failure audit's run (imu_seconds/, tracks/, tables/segments.csv) and config (periods,
exclusions, tau*), the default-smoother run (V2b tracks), the V1b run (V1b tracks), the WISER fix caches (float64 raw
fixes), the make_imu 50-Hz npz (features + the reproduction of the audit's per-second IMU states). Existing scripts are
imported, never modified.

Usage:
  python wiser/scripts/analyze_imu_speed_proxy.py --cohort 2026c [--workers 16]            # compute -> fit -> evaluate -> report
  python wiser/scripts/analyze_imu_speed_proxy.py --cohort 2026c --stage compute           # per-second tables + feature cache
  python wiser/scripts/analyze_imu_speed_proxy.py --cohort 2026c --stage fit --run <dir>   # models + tuning-night choice only
  python wiser/scripts/analyze_imu_speed_proxy.py --cohort 2026c --stage evaluate --run <dir>   # validity, R1, R2, deliverable, report
  python wiser/scripts/analyze_imu_speed_proxy.py --report-only <run_dir>                  # re-evaluate / re-render (no refit)
  python wiser/scripts/analyze_imu_speed_proxy.py --selftest                               # synthetic data, no field data
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiser" / "src"))
sys.path.insert(0, str(REPO / "wiser" / "scripts"))
sys.path.append(str(REPO / "ephys"))
import output_paths  # noqa: E402  (wiser shim -> common/output_paths.py)
import wiser_analysis_utils as W  # noqa: E402
import analyze_imu_wiser_calibration as C  # noqa: E402  (helpers; unmodified)
import analyze_wiser_failure_audit as FA  # noqa: E402  (loaders, sample QC, per-second states, medians, bootstrap; unmodified)
import analyze_wiser_default_smoother as DS  # noqa: E402  (block codes, histogram bootstrap, colours; unmodified)

DIRECTION = "wiser_baseline"
NAME = "imu_speed_proxy"
STEM = f"{DIRECTION}_imu_speed_proxy"
PLAN = "implementation_plan/2026-10-03-imu-speed-proxy.md"
DRIVER = "wiser/scripts/analyze_imu_speed_proxy.py"
TRACKS = ["raw", "B1", "B2", "B2p", "V1", "V2", "V2b", "V1b"]
SMOOTHED = ["B1", "B2", "B2p", "V1", "V2", "V2b", "V1b"]
LABEL = {"raw": "raw fixes", "B1": "B1 median-7", "B2": "B2 robust CV", "B2p": "B2′ (+drift, p)", "V1": "V1 ZUPT (audit)",
         "V2": "V2 IMU-q (audit)", "V2b": "V2b IMU-q (B2 base)", "V1b": "V1b B2 + guarded ZUPT", "proxy": "IMU proxy"}
COL = {**{k: v for k, v in DS.COL.items() if k in TRACKS}, "V1b": "#bcbd22", "proxy": "#000000"}
SCALES = (3, 1)
SETS = ("all", "calm", "rain")
BANDS = ("all", "lt5", "5to15", "gt15")
BAND_LABEL = {"all": "all", "lt5": "< 5", "5to15": "5–15", "gt15": "> 15"}
# log-spaced histogram edges for the block-bootstrap quantiles (relative bin width ~0.28 %); 0 gets its own first bin
EDGES = np.r_[0.0, np.geomspace(0.005, 400.0, 4001)]


def log_to(fh, msg: str) -> None:
    print(msg, flush=True)
    if fh is not None:
        fh.write(msg + "\n")
        fh.flush()


# ====================================================================================================== config / context
def load_cfg(cohort: str, path: str | None = None) -> dict:
    cp = Path(path) if path else REPO / "wiser" / "configs" / f"imu_speed_proxy_{cohort}.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    cfg["_path"] = str(cp)
    cfg["_cohort"] = cohort
    return cfg


def load_acfg(cfg: dict) -> dict:
    return FA.load_cfg(cfg["_cohort"], str(REPO / cfg["audit_config"]))


_CTX: dict = {}


def _ctx(acfg: dict) -> dict:
    if acfg["_path"] not in _CTX:
        _CTX[acfg["_path"]] = FA.context(acfg)
    return _CTX[acfg["_path"]]


def nights(cfg: dict) -> list:
    sp = cfg["split"]
    return list(sp["train"]) + list(sp["tune"]) + list(sp["test"]) + list(sp["robustness"])


def role_of(cfg: dict) -> dict:
    sp = cfg["split"]
    return {**{p: "train" for p in sp["train"]}, **{p: "tune" for p in sp["tune"]}, **{p: "test" for p in sp["test"]},
            **{p: "robustness" for p in sp["robustness"]}}


def feat_cols(cfg: dict, w: int | None = None) -> list:
    ws = cfg["features"]["windows_s"] if w is None else [w]
    return [f"{n}_w{x}" for x in ws for n in cfg["features"]["names"]]


# ====================================================================================================== reference 1
def in_house(x: np.ndarray, y: np.ndarray, houses: list, buf: float) -> np.ndarray:
    """True inside any house ROI grown by buf on every side (library buffered membership); NaN -> False."""
    m = np.zeros(len(x), bool)
    for roi in houses:
        with np.errstate(invalid="ignore"):
            _, inb = W._rect_membership(np.asarray(x, float), np.asarray(y, float), roi, buf)
        m |= inb
    return m


def scale_speed(t: np.ndarray, p: np.ndarray, secs: np.ndarray, off: float, half: float, minfix: int):
    """|m(c + off) - m(c - off)| / (2 off) for c = s + 0.5 (Amendment 1.1); m = coordinate-wise median of p over
    [g - half, g + half) with >= minfix points (NaN otherwise). t (s, sorted) and secs on the same absolute clock."""
    c = secs.astype(np.float64) + 0.5
    ma, _ = FA.roll_median(t, p, c - off, half, minfix)
    mb, _ = FA.roll_median(t, p, c + off, half, minfix)
    return np.hypot(*(mb - ma).T) / (2.0 * off), ma, mb


def track_speeds(t: np.ndarray, p: np.ndarray, secs: np.ndarray, rc: dict) -> tuple[np.ndarray, np.ndarray]:
    v3, _, _ = scale_speed(t, p, secs, rc["u3_offset_s"], rc["u3_half_s"], int(rc["min_fix"]))
    v1, _, _ = scale_speed(t, p, secs, rc["u1_offset_s"], rc["u1_half_s"], int(rc["min_fix"]))
    return v3, v1


def reference(t: np.ndarray, z: np.ndarray, A: np.ndarray, valid: np.ndarray, fmask: np.ndarray, secs: np.ndarray,
              ok_imu: np.ndarray, houses: list, rc: dict) -> dict:
    """Reference 1 per second: u3, u1 from the raw fixes and every clean-second condition (Amendment 1.2)."""
    cc = rc["clean"]
    c = secs.astype(np.float64) + 0.5
    span = float(cc["span_s"])
    i0 = np.searchsorted(t, c - span, "left")
    i1 = np.searchsorted(t, c + span, "right")
    n_span = i1 - i0
    jk = FA.find_jumps(t, z, float(cc["jump_in"]), float(cc["jump_dt_s"]))
    jf = np.zeros(len(t), bool)
    jf[jk] = True
    jf[np.minimum(jk + 1, len(t) - 1)] = True

    def cnt(flag):
        cs = np.r_[0, np.cumsum(np.asarray(flag, np.int64))]
        return cs[i1] - cs[i0]
    n_low = cnt(A < float(cc["min_anchors"]))
    n_inv = cnt(~valid) if cc.get("require_valid", True) else np.zeros(len(secs), np.int64)
    n_msk = cnt(fmask)
    n_jmp = cnt(jf)
    u3, ma, mb = scale_speed(t, z, secs, rc["u3_offset_s"], rc["u3_half_s"], int(rc["min_fix"]))
    u1, _, _ = scale_speed(t, z, secs, rc["u1_offset_s"], rc["u1_half_s"], int(rc["min_fix"]))
    buf = float(cc["house_buffer_in"])
    out_a = np.isfinite(ma[:, 0]) & ~in_house(ma[:, 0], ma[:, 1], houses, buf)
    out_b = np.isfinite(mb[:, 0]) & ~in_house(mb[:, 0], mb[:, 1], houses, buf)
    min_n = int(math.ceil(float(cc["min_rate_hz"]) * 2.0 * span - 1e-9))
    rate_ok = n_span >= min_n
    fix_ok = rate_ok & (n_low == 0) & (n_inv == 0) & (n_msk == 0) & (n_jmp == 0)
    med_ok = np.isfinite(u3)
    clean = np.asarray(ok_imu, bool) & fix_ok & med_ok & out_a & out_b
    return {"n_span": n_span, "n_low": n_low, "n_inv": n_inv, "n_msk": n_msk, "n_jmp": n_jmp, "rate_ok": rate_ok,
            "fix_ok": fix_ok, "med_ok": med_ok, "out_a": out_a, "out_b": out_b, "clean": clean, "u3": u3, "u1": u1,
            "mx": 0.5 * (ma[:, 0] + mb[:, 0]), "my": 0.5 * (ma[:, 1] + mb[:, 1])}


def floor_seconds(secs: np.ndarray, segs: np.ndarray, trim: float, span: float) -> tuple[np.ndarray, np.ndarray]:
    """Seconds whose clean span [c - span, c + span] lies inside a trimmed certified still segment [t0 + trim, t1 - trim]
    (segs in absolute seconds, IMU clock). Returns the mask and the segment index (-1 outside)."""
    c = secs.astype(np.float64) + 0.5
    fl = np.zeros(len(secs), bool)
    sid = np.full(len(secs), -1, np.int64)
    for j, (a, b) in enumerate(np.asarray(segs, float).reshape(-1, 2)):
        m = (c - span >= a + trim) & (c + span <= b - trim)
        fl |= m
        sid[m] = j
    return fl, sid


# ====================================================================================================== reference 2: features
IMU_KEYS_PLUS = tuple(FA.IMU_KEYS) + ("pitch_deg",)


def load_imu_plus(sessions: list, lo: float, hi: float, tz: str) -> dict:
    """FA.load_imu with pitch_deg added (same session selection, concatenation and ordering)."""
    parts = []
    for s in sessions:
        base = C.to_ms(s["start_local"][:10] + " 00:00:00", tz)
        with np.load(s["npz"]) as z:
            if "t_pc_ms" not in z.files:
                continue
            u = base + z["t_pc_ms"].astype(np.float64)
            m = (u >= lo) & (u < hi)
            if not m.any():
                continue
            d = {"unix_ms": u[m]}
            for k in IMU_KEYS_PLUS:
                d[k] = z[k][m] if k in z.files else np.zeros(int(m.sum()), bool)
            parts.append(d)
    if not parts:
        return {"unix_ms": np.zeros(0), **{k: np.zeros(0) for k in IMU_KEYS_PLUS}, "n_sessions": 0}
    parts.sort(key=lambda d: d["unix_ms"][0])
    out = {k: np.concatenate([d[k] for d in parts]) for k in parts[0]}
    o = np.argsort(out["unix_ms"], kind="stable")
    out = {k: v[o] for k, v in out.items()}
    for k in ("omega_dps", "vedba_ms2", "turn_dps", "pitch_deg"):
        out[k] = out[k].astype(np.float64)
    for k in ("saturated", "unreliable", "frozen", "invalid"):
        out[k] = out[k].astype(bool)
    out["n_sessions"] = len(parts)
    return out


def bandpass_runs(x: np.ndarray, valid: np.ndarray, u: np.ndarray, fs: float, band, order: int) -> np.ndarray:
    """Zero-phase Butterworth band-pass of each column on every contiguous run (gap < 1.5 samples); invalid samples are
    zeroed before filtering; runs too short for the default pad -> NaN."""
    from scipy import signal
    sos = signal.butter(int(order), [float(band[0]), float(band[1])], btype="bandpass", fs=fs, output="sos")
    xx = np.where(valid[:, None] & np.isfinite(x), x, 0.0)
    y = np.full(x.shape, np.nan)
    if not len(u):
        return y
    brk = np.flatnonzero(np.diff(u) > 1.5 * 1000.0 / fs) + 1
    edges = np.r_[0, brk, len(u)]
    padlen = 3 * (2 * len(sos) + 1)
    for a, b in zip(edges[:-1], edges[1:]):
        if b - a > padlen + 1:
            y[a:b] = signal.sosfiltfilt(sos, xx[a:b], axis=0)
    return y


def second_features(imu: dict, valid: np.ndarray, secs: np.ndarray, fc: dict) -> dict:
    """Per-second IMU features over the 1-s window [s, s+1) and the 3-s window [s-1, s+2) (Amendment 1.4)."""
    u = imu["unix_ms"]
    fs = float(fc["fs"])
    n = len(secs)
    out = {}
    if len(u) < 2:
        for w in fc["windows_s"]:
            for nm in fc["names"]:
                out[f"{nm}_w{w}"] = np.full(n, np.nan) if nm != "qc" else np.zeros(n)
        return out
    lin = imu["lin_acc_earth_ms2"].astype(np.float64)
    hf = bandpass_runs(lin[:, :2], valid, u, fs, fc["hacc_band_hz"], int(fc["hacc_butter_order"]))
    h2 = (hf ** 2).sum(axis=1)
    az = lin[:, 2]
    vb, sb = fc["stride_band_hz"], fc["total_band_hz"]
    for w in fc["windows_s"]:
        N = int(round(fs * w))
        start = (secs.astype(np.float64) + 0.5 - w / 2.0) * 1000.0
        i0 = np.searchsorted(u, start, "left")
        i1 = np.searchsorted(u, start + w * 1000.0, "left")
        nmax = N + 3
        idx = i0[:, None] + np.arange(nmax)[None, :]
        inw = idx < i1[:, None]
        idxc = np.clip(idx, 0, len(u) - 1)
        vm = inw & valid[idxc]
        qc = np.minimum(vm.sum(axis=1) / N, 1.0)
        tok = qc >= float(fc["min_valid_share_time"])

        def M(x):
            return np.where(vm, x[idxc], np.nan)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            ved = M(imu["vedba_ms2"])
            f = {"vedba_mean": np.nanmean(ved, axis=1), "vedba_p90": np.nanpercentile(ved, 90, axis=1),
                 "hacc_rms": np.sqrt(np.nanmean(M(h2), axis=1)),
                 "omega_mean": np.nanmean(M(imu["omega_dps"]), axis=1),
                 "turn_mean": np.nanmean(np.abs(M(imu["turn_dps"])), axis=1),
                 "pitch_sd": np.nanstd(M(imu["pitch_deg"]), axis=1)}
        for k in f:
            f[k] = np.where(tok, f[k], np.nan)
        # spectral (vertical earth-frame linear acceleration)
        idn = i0[:, None] + np.arange(N)[None, :]
        okn = (i1 - i0 >= N) & (idn[:, -1] < len(u))
        idnc = np.clip(idn, 0, len(u) - 1)
        span = u[idnc[:, -1]] - u[idnc[:, 0]]
        okn &= np.abs(span - (N - 1) * 1000.0 / fs) < 30.0
        vn = valid[idnc] & np.isfinite(az[idnc])
        okn &= vn.mean(axis=1) >= float(fc["min_valid_share_spectral"])
        seg = np.where(vn, az[idnc], np.nan)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            mu = np.nanmean(seg, axis=1)
        seg = np.nan_to_num(np.where(vn, seg, mu[:, None]) - mu[:, None])
        win = np.hanning(N)
        X = np.fft.rfft(seg * win[None, :], axis=1)
        P = 2.0 * np.abs(X) ** 2 / (N * np.sum(win ** 2))
        fr = np.fft.rfftfreq(N, 1.0 / fs)
        bs = (fr >= vb[0] - 1e-9) & (fr <= vb[1] + 1e-9)
        bt = (fr >= sb[0] - 1e-9) & (fr <= sb[1] + 1e-9)
        vpow = P[:, bs].sum(axis=1)
        vtot = P[:, bt].sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            vshare = vpow / vtot
        vpeak = fr[bs][np.argmax(P[:, bs], axis=1)]
        f["vpow"] = np.where(okn, vpow, np.nan)
        f["vshare"] = np.where(okn, vshare, np.nan)
        f["vpeak_hz"] = np.where(okn, vpeak, np.nan)
        f["qc"] = qc
        for nm in fc["names"]:
            out[f"{nm}_w{w}"] = f[nm]
    return out


# ====================================================================================================== one animal-period
def segments_of(run: Path, animal: str, pkey: str) -> np.ndarray:
    S = pd.read_csv(run / "tables" / "segments.csv")
    for c in ("primary", "scored", "ge30"):
        S[c] = S[c].astype(bool)
    S = S[S.primary & S.scored & S.ge30 & (S.animal == animal) & (S.period == pkey)]
    return S[["t0_ms", "t1_ms"]].to_numpy(float) / 1000.0


def load_track_npz(path: Path, keys: list, t_ref: np.ndarray) -> dict:
    with np.load(path) as z:
        tm = z["t_ms"].astype(np.int64)
        if len(tm) != len(t_ref) or not np.array_equal(tm, t_ref):
            raise ValueError(f"{path.name}: t_ms differs from the fix cache")
        return {k: z[k].astype(np.float64) for k in keys}


def process(job: dict) -> dict:
    t_job = time.time()
    cfg, acfg, animal, pkey, out = job["cfg"], job["acfg"], job["animal"], job["pkey"], Path(job["out"])
    ctx = _ctx(acfg)
    tz = ctx["tz"]
    p = acfg["periods"][pkey]
    lo, hi = C.to_ms(p["start"], tz), C.to_ms(p["end"], tz)
    night = p["kind"] == "night" and pkey in nights(cfg)
    run = Path(cfg["audit_run"])
    rc, fc = cfg["reference"], cfg["features"]
    ps = pd.read_csv(run / "imu_seconds" / f"{animal}_{pkey}.csv.gz")
    secs = ps["sec"].to_numpy(np.int64)
    assert np.all(np.diff(secs) == 1), "imu_seconds not contiguous"
    ok_imu = ps["ok"].to_numpy(bool)
    still = ps["still"].to_numpy(bool) & ok_imu
    state = np.where(ok_imu, ps["state"].to_numpy(np.int8), 0).astype(np.int8)
    tau = float(ctx["taus"][animal])
    fx = FA.load_fixes(acfg, pkey, animal, lo, hi, tau)
    t = fx["t_al_ms"].to_numpy(np.float64) / 1000.0
    z = fx[["x", "y"]].to_numpy(np.float64)
    A = fx["anchors_used"].to_numpy(np.float64)
    valid = fx["valid"].astype(bool).to_numpy()
    fmask = np.zeros(len(fx), bool)
    for c in rc["clean"]["fix_masks"]:
        fmask |= fx[c].astype(bool).to_numpy()
    t_ms = fx["t_ms"].to_numpy(np.int64)
    ref = reference(t, z, A, valid, fmask, secs, ok_imu, ctx["houses"], rc)
    segs = segments_of(run, animal, pkey)
    fl, fsid = floor_seconds(secs, segs, float(rc["floor"]["trim_s"]), float(rc["clean"]["span_s"]))
    floor_ok = fl & ok_imu & ref["fix_ok"] & ref["med_ok"]
    blk = ((secs * 1000.0 - lo) // (float(cfg["bootstrap"]["block_s"]) * 1000.0)).astype(np.int64)
    tab = pd.DataFrame({"sec": secs, "ok": ok_imu, "still": still, "state": state, "block": blk,
                        **{k: ref[k] for k in ("n_span", "n_low", "n_inv", "n_msk", "n_jmp", "rate_ok", "fix_ok", "med_ok",
                                               "out_a", "out_b", "clean")},
                        "u3": ref["u3"].astype(np.float32), "u1": ref["u1"].astype(np.float32),
                        "mx": ref["mx"].astype(np.float32), "my": ref["my"].astype(np.float32),
                        "floor_seg": fl, "floor_sid": fsid, "floor_ok": floor_ok})
    info = {"animal": animal, "period": pkey, "set": p["set"], "kind": p["kind"], "n_sec": int(len(secs)), "n_fix": int(len(t)),
            "imu_ok": int(ok_imu.sum()), "clean": int(ref["clean"].sum()), "clean_u1": int((ref["clean"] & np.isfinite(ref["u1"])).sum()),
            "floor_seg_s": int(fl.sum()), "floor_ok_s": int(floor_ok.sum()), "n_segments": int(len(segs))}
    rep = {"animal": animal, "period": pkey}
    if night:
        trk = load_track_npz(run / "tracks" / f"{animal}_{pkey}.npz", ["B1", "B2", "B2p", "V1", "V2", "raw"], t_ms)
        trk["raw32"] = trk.pop("raw")          # the audit's float32 copy of the raw fixes (check only)
        trk["raw"] = z                         # float64 from the fix cache = the reference input
        trk.update(load_track_npz(Path(cfg["default_smoother_run"]) / "tracks" / f"{animal}_{pkey}.npz", ["V2b"], t_ms))
        trk.update(load_track_npz(Path(cfg["v1b_run"]) / "tracks" / f"{animal}_{pkey}.npz", ["V1b"], t_ms))
        for m in TRACKS:
            v3, v1 = track_speeds(t, trk[m], secs, rc)
            tab[f"v3_{m}"] = v3.astype(np.float32)
            tab[f"v1_{m}"] = v1.astype(np.float32)
        v3r, v1r = track_speeds(t, trk["raw32"], secs, rc)
        cl = ref["clean"]
        rep["raw32_vs_u3_max"] = float(np.nanmax(np.abs(v3r[cl] - ref["u3"][cl]))) if cl.any() else np.nan
        rep["raw32_vs_u1_max"] = float(np.nanmax(np.abs(v1r[cl] - ref["u1"][cl]))) if cl.any() else np.nan
        # ---- IMU features (+ the audit's per-second states reproduced from the npz)
        ext = float(cfg["imu_margin_s"]) * 1000.0
        sid = C.resolve_tag(ctx["ids"], animal, lo, hi)
        vf, vu = C.tag_window(ctx["ids"], sid, animal, (lo + hi) / 2)
        sess = FA.sessions_for(acfg, ctx, animal, lo - ext, hi + ext)
        imu = load_imu_plus(sess, lo - ext, hi + ext, tz)
        vs = FA.sample_valid(imu, ctx, animal, lo - ext, hi + ext, vf, vu)
        feats = pd.DataFrame({"sec": secs, **second_features(imu, vs, secs, fc)})
        cdir = Path(cfg["feature_cache_root"]) / animal
        cpath = cdir / f"{pkey}.csv.gz"
        if cpath.exists() and not job.get("rebuild_features"):
            old = pd.read_csv(cpath)
            same = len(old) == len(feats) and np.array_equal(old["sec"].to_numpy(np.int64), secs)
            dif = (float(np.nanmax(np.abs(old[feat_cols(cfg)].to_numpy(float) - feats[feat_cols(cfg)].to_numpy(float))))
                   if same else np.inf)
            rep["feature_cache"] = "reused"
            rep["feature_cache_maxdiff"] = dif
        else:
            cdir.mkdir(parents=True, exist_ok=True)
            feats.to_csv(cpath, index=False, float_format="%.6g")
            rep["feature_cache"] = "written"
        ps_rep = FA.per_second_states(imu, ctx, animal, lo - ext, hi + ext, vf, vu)
        ps_rep = ps_rep.set_index("sec").reindex(secs)
        rep.update({"sessions": ";".join(s["session"] for s in sess), "repro_n": int(len(secs)),
                    "repro_ok_agree": float((ps_rep["ok"].fillna(False).astype(bool).to_numpy() == ps["ok"].to_numpy(bool)).mean()),
                    "repro_still_agree": float((ps_rep["still"].fillna(False).astype(bool).to_numpy() == ps["still"].to_numpy(bool)).mean()),
                    "repro_state_agree": float((ps_rep["state"].fillna(0).astype(int).to_numpy() == ps["state"].to_numpy(int)).mean()),
                    "repro_vedba_maxdiff": float(np.nanmax(np.abs(ps_rep["vedba_1s"].to_numpy(float) - ps["vedba_1s"].to_numpy(float)))),
                    "repro_sbf_maxdiff": float(np.nanmax(np.abs(ps_rep["sbf"].to_numpy(float) - ps["sbf"].to_numpy(float))))})
        info["imu_valid_s"] = float(vs.sum() / float(fc["fs"]))
    (out / "seconds").mkdir(exist_ok=True)
    tab.to_csv(out / "seconds" / f"{animal}_{pkey}.csv.gz", index=False, float_format="%.6g")
    info["runtime_s"] = round(time.time() - t_job, 1)
    return {"info": info, "rep": rep}


def _process_safe(job: dict) -> dict:
    try:
        return process(job)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(), "animal": job["animal"], "pkey": job["pkey"]}


def run_compute(cfg: dict, workers: int, rebuild_features: bool = False) -> Path:
    t0 = time.time()
    acfg = load_acfg(cfg)
    out = output_paths.run_dir(NAME, cfg["_cohort"])
    for d in ("tables", "models", "seconds"):
        (out / d).mkdir(exist_ok=True)
    fh = open(out / "log.txt", "w", encoding="utf-8")
    log_to(fh, f"run dir {out}; git {C.git_commit()}; config {cfg['_path']}; audit run {cfg['audit_run']}")
    _ctx(acfg)
    jobs = [{"cfg": cfg, "acfg": acfg, "animal": a, "pkey": pk, "out": str(out), "rebuild_features": rebuild_features}
            for pk in acfg["periods"] for a in cfg["animals"]]
    infos, reps = [], []
    with ProcessPoolExecutor(max_workers=max(1, min(16, workers))) as ex:
        for r in ex.map(_process_safe, jobs):
            if "error" in r:
                log_to(fh, f"ERROR {r['animal']} {r['pkey']}: {r['error']}\n{r['trace']}")
                continue
            i = r["info"]
            log_to(fh, f"{i['animal']} {i['period']}: {i['n_fix']:,} fixes, IMU ok {i['imu_ok'] / 3600:.2f} h, floor seconds {i['floor_ok_s']:,}"
                       f"{'' if 'feature_cache' not in r['rep'] else ', features ' + r['rep']['feature_cache']}, {i['runtime_s']} s")
            infos.append(i)
            reps.append(r["rep"])
    tb = out / "tables"
    pd.DataFrame(infos).to_csv(tb / "periods_info.csv", index=False)
    pd.DataFrame(reps).to_csv(tb / "reproduction.csv", index=False)
    write_feature_readme(cfg)
    prov = {"config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "audit_config": cfg["audit_config"], "audit_run": cfg["audit_run"],
            "default_smoother_run": cfg["default_smoother_run"], "v1b_run": cfg["v1b_run"], "fix_cache_root": cfg["fix_cache_root"],
            "imu_root": cfg["imu_root"], "feature_cache_root": cfg["feature_cache_root"], "git_commit": C.git_commit(),
            "audit_run_manifest": json.loads((Path(cfg["audit_run"]) / "run_manifest.json").read_text(encoding="utf-8")),
            "imu_sessions": [{k: r.get(k) for k in ("animal", "period", "sessions")} for r in reps if "sessions" in r],
            "tau_star_s": _ctx(acfg)["taus"], "runtime_compute_s": round(time.time() - t0, 1)}
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=2, default=str), encoding="utf-8")
    log_to(fh, f"compute done ({time.time() - t0:.0f} s)")
    fh.close()
    return out


def write_feature_readme(cfg: dict) -> None:
    root = Path(cfg["feature_cache_root"])
    root.mkdir(parents=True, exist_ok=True)
    fc = cfg["features"]
    txt = f"""# Per-second head-IMU features for the speed proxy (cohort {cfg['_cohort']})
<!-- written by {DRIVER} -->

`<SFxx>/<period>.csv.gz`, one row per field-PC second `sec` (Unix s; the second [sec, sec + 1)) of the failure audit's
night periods (21:00-04:20 local, `wiser/configs/wiser_failure_audit_{cfg['_cohort']}.json`), computed once from the make_imu
50-Hz npz (`{cfg['imu_root']}/<SFxx>/<session>.imu.npz`, read-only) by `{DRIVER}` (plan `{PLAN}`, Amendment 1.4), so later
models never re-read the npz. Feature version {fc['version']}.

Windows: `_w1` = [sec, sec + 1), `_w3` = [sec - 1, sec + 2). Valid 50-Hz samples = the failure audit's sample QC
(`analyze_wiser_failure_audit.sample_valid`: finite, not saturated / frozen / invalid / unreliable, no frozen-rule run,
outside handling +- 5 min, all-tag silences +- 2 min, the ADC lane and the tag window).

| column | meaning | units |
|---|---|---|
| `vedba_mean`, `vedba_p90` | mean / 90th percentile of make_imu VeDBA over the valid samples | m/s^2 |
| `hacc_rms` | RMS of the horizontal earth-frame linear acceleration after a zero-phase order-{fc['hacc_butter_order']} Butterworth band-pass {fc['hacc_band_hz'][0]}-{fc['hacc_band_hz'][1]} Hz | m/s^2 |
| `vpow` | vertical earth-frame linear acceleration power in {fc['stride_band_hz'][0]}-{fc['stride_band_hz'][1]} Hz (Hann periodogram, one-sided, sum of bins) | (m/s^2)^2 |
| `vpeak_hz` | frequency of the largest periodogram bin in {fc['stride_band_hz'][0]}-{fc['stride_band_hz'][1]} Hz (1-Hz bins at 1 s, 1/3 Hz at 3 s) | Hz |
| `vshare` | `vpow` / power in {fc['total_band_hz'][0]}-{fc['total_band_hz'][1]} Hz (stride-band share) | 1 |
| `omega_mean`, `turn_mean` | mean of make_imu \\|omega\\| and \\|turn rate\\| | deg/s |
| `pitch_sd` | SD of make_imu pitch | deg |
| `qc` | valid samples / (50 x window length) | 1 |

Time-domain features are NaN when `qc` < {fc['min_valid_share_time']}; spectral features (`vpow`, `vpeak_hz`, `vshare`) are NaN unless the window
holds exactly 50 x w ungapped samples with >= {int(100 * fc['min_valid_share_spectral'])} % valid (invalid samples set to the window mean).
A re-run reuses an existing file and only checks it (`--rebuild-features` overwrites).
"""
    (root / "README.md").write_text(txt, encoding="utf-8")


# ====================================================================================================== loading for fit / evaluate
def load_seconds(out: Path, cfg: dict, acfg: dict, only_nights: bool = True) -> pd.DataFrame:
    parts = []
    for f in sorted((out / "seconds").glob("*.csv.gz")):
        a, pk = f.name[:-len(".csv.gz")].split("_", 1)
        if only_nights and pk not in nights(cfg):
            continue
        d = pd.read_csv(f)
        d.insert(0, "period", pk)
        d.insert(0, "animal", a)
        parts.append(d)
    D = pd.concat(parts, ignore_index=True)
    D["set"] = D["period"].map({k: v["set"] for k, v in acfg["periods"].items()})
    D["kind"] = D["period"].map({k: v["kind"] for k, v in acfg["periods"].items()})
    D["role"] = D["period"].map(role_of(cfg)).fillna("")
    for c in ("ok", "still", "clean", "floor_ok", "floor_seg", "fix_ok", "med_ok", "out_a", "out_b", "rate_ok"):
        D[c] = D[c].astype(bool)
    return D


def attach_features(D: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    parts = []
    for (a, pk), _ in D.groupby(["animal", "period"]):
        f = pd.read_csv(Path(cfg["feature_cache_root"]) / a / f"{pk}.csv.gz")
        f.insert(0, "period", pk)
        f.insert(0, "animal", a)
        parts.append(f)
    F = pd.concat(parts, ignore_index=True)
    return D.merge(F, on=["animal", "period", "sec"], how="left", validate="one_to_one")


# ====================================================================================================== models
def m1_fit(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    Xa = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(Xa, y, rcond=None)
    return beta


def m1_predict(beta: np.ndarray, X: np.ndarray, clip: float = 0.0) -> np.ndarray:
    ok = np.isfinite(X).all(axis=1)
    y = np.full(len(X), np.nan)
    y[ok] = np.column_stack([np.ones(int(ok.sum())), X[ok]]) @ beta
    return np.maximum(y, clip)


def m2_matrix(D: pd.DataFrame, cols: list, animals: list) -> np.ndarray:
    X = D[cols].to_numpy(np.float64)
    oh = np.column_stack([(D["animal"].to_numpy() == a).astype(np.float64) for a in animals])
    return np.column_stack([X, oh])


class M1Model:
    """Per-animal OLS (intercept + features); NaN where a feature is missing; clipped at clip_min."""

    def __init__(self, cols: list, coefs: dict, clip: float):
        self.cols, self.coefs, self.clip = cols, coefs, clip

    def predict(self, D: pd.DataFrame) -> np.ndarray:
        y = np.full(len(D), np.nan)
        an = D["animal"].to_numpy()
        X = D[self.cols].to_numpy(np.float64)
        for a, b in self.coefs.items():
            m = an == a
            if m.any():
                y[m] = m1_predict(np.asarray(b["beta"]), X[m], self.clip)
        return y

    def to_dict(self) -> dict:
        return {"type": "M1", "cols": self.cols, "coefs": self.coefs, "clip": self.clip}


class M2Model:
    def __init__(self, est, cols: list, animals: list, clip: float, params: dict):
        self.est, self.cols, self.animals, self.clip, self.params = est, cols, animals, clip, params

    def predict(self, D: pd.DataFrame) -> np.ndarray:
        return np.maximum(self.est.predict(m2_matrix(D, self.cols, self.animals)), self.clip)

    def to_dict(self) -> dict:
        return {"type": "M2", "est": self.est, "cols": self.cols, "animals": self.animals, "clip": self.clip, "params": self.params}


def model_from_dict(d: dict):
    """Pickled models are plain dicts (+ the sklearn estimator), loadable without this module's classes."""
    if d["type"] == "M1":
        return M1Model(d["cols"], d["coefs"], d["clip"])
    return M2Model(d["est"], d["cols"], d["animals"], d["clip"], d["params"])


def fit_scale(D: pd.DataFrame, cfg: dict, scale: int, fh=None) -> dict:
    """Fit M1 / M2 on the training nights, choose M2's grid point and then the model on the tuning night (one scale)."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    mc = cfg["models"]
    y_col = f"u{scale}"
    cl = D["clean"].to_numpy(bool) & np.isfinite(D[y_col].to_numpy(float))
    tr = cl & (D["role"] == "train").to_numpy()
    tu = cl & (D["role"] == "tune").to_numpy()
    y = D[y_col].to_numpy(float)
    animals = list(cfg["animals"])
    # ---- M1 (per animal)
    c1 = [f"{n}_w{scale}" for n in mc["M1"]["features"]]
    X1 = D[c1].to_numpy(np.float64)
    fin1 = np.isfinite(X1).all(axis=1)
    coefs = {}
    for a in animals:
        m = tr & fin1 & (D["animal"] == a).to_numpy()
        beta = m1_fit(X1[m], y[m])
        coefs[a] = {"beta": beta.tolist(), "n_train": int(m.sum()), "names": ["intercept"] + c1}
    M1 = M1Model(c1, coefs, float(mc["M1"]["clip_min"]))
    p1 = M1.predict(D)
    # ---- M2 grid
    c2 = feat_cols(cfg)
    Xtr = m2_matrix(D[tr], c2, animals)
    grid, best = [], None
    g = mc["M2"]["grid"]
    for lr in g["learning_rate"]:
        for md in g["max_depth"]:
            for ml in g["min_samples_leaf"]:
                est = HistGradientBoostingRegressor(loss=mc["M2"]["loss"], learning_rate=lr, max_depth=md, min_samples_leaf=ml,
                                                    random_state=int(mc["M2"]["random_state"]))
                est.fit(Xtr, y[tr])
                ph = np.maximum(est.predict(m2_matrix(D[tu], c2, animals)), float(mc["M2"]["clip_min"]))
                mae = float(np.median(np.abs(ph - y[tu])))
                grid.append({"scale": scale, "learning_rate": lr, "max_depth": md, "min_samples_leaf": ml, "mae_tune": mae,
                             "n_iter": int(est.n_iter_), "n_train": int(tr.sum()), "n_tune": int(tu.sum())})
                if best is None or mae < best[0] - 1e-12:
                    best = (mae, est, {"learning_rate": lr, "max_depth": md, "min_samples_leaf": ml})
    M2 = M2Model(best[1], c2, animals, float(mc["M2"]["clip_min"]), best[2])
    p2 = M2.predict(D)
    common = tu & np.isfinite(p1) & np.isfinite(p2)
    mae1 = float(np.median(np.abs(p1[common] - y[common])))
    mae2 = float(np.median(np.abs(p2[common] - y[common])))
    choice = "M1" if mae1 <= mae2 else "M2"
    res = {"scale": scale, "M1": M1, "M2": M2, "grid": pd.DataFrame(grid), "choice": choice, "mae_tune_M1": mae1, "mae_tune_M2": mae2,
           "n_train": int(tr.sum()), "n_tune": int(tu.sum()), "n_tune_common": int(common.sum()),
           "m1_tune_coverage": float(np.isfinite(p1[tu]).mean()) if tu.any() else np.nan,
           "m2_best": best[2], "m2_best_mae_all_tune": float(best[0]),
           "mae_train_M1": float(np.nanmedian(np.abs(p1[tr] - y[tr]))), "mae_train_M2": float(np.median(np.abs(p2[tr] - y[tr])))}
    log_to(fh, f"scale {scale} s: n train {res['n_train']:,}, tune {res['n_tune']:,}; tuning-night MAE M1 {mae1:.3f} in/s, M2 {mae2:.3f} in/s "
               f"(best grid {best[2]}, MAE on all tuning seconds {best[0]:.3f}); M1 coverage {res['m1_tune_coverage']:.4f} -> {choice}")
    return res


def run_fit(out: Path, cfg: dict, fh=None) -> dict:
    t0 = time.time()
    acfg = load_acfg(cfg)
    D = attach_features(load_seconds(out, cfg, acfg), cfg)
    tb, md = out / "tables", out / "models"
    md.mkdir(exist_ok=True)
    fits, grids, rows = {}, [], []
    for scale in SCALES:
        r = fit_scale(D, cfg, scale, fh)
        fits[scale] = r
        grids.append(r["grid"])
        for a, b in r["M1"].coefs.items():
            rows.append({"scale": scale, "animal": a, "n_train": b["n_train"],
                         **{f"b_{nm.rsplit('_w', 1)[0]}": v for nm, v in zip(b["names"], b["beta"])}})
        for name in ("M1", "M2"):
            with open(md / f"{name}_u{scale}.pkl", "wb") as f:
                pickle.dump(r[name].to_dict(), f)
    pd.concat(grids, ignore_index=True).to_csv(tb / "m2_tuning_grid.csv", index=False)
    pd.DataFrame(rows).to_csv(tb / "m1_coefficients.csv", index=False)
    summ = [{k: v for k, v in r.items() if k not in ("M1", "M2", "grid")} for r in fits.values()]
    pd.DataFrame(summ).to_csv(tb / "model_choice.csv", index=False)
    feat = {"M1": {s: fits[s]["M1"].cols for s in SCALES}, "M2": feat_cols(cfg) + [f"animal_{a}" for a in cfg["animals"]],
            "choice": {s: fits[s]["choice"] for s in SCALES}}
    (md / "features.json").write_text(json.dumps(feat, indent=2), encoding="utf-8")
    fitted = {"fitted_local": pd.Timestamp.now(tz=cfg["tz"]).strftime("%Y-%m-%d %H:%M:%S"), "run_dir": str(out)}
    for s in SCALES:
        r = fits[s]
        fitted[f"u{s}"] = {"choice": r["choice"], "mae_tune_in_per_s": {"M1": round(r["mae_tune_M1"], 4), "M2": round(r["mae_tune_M2"], 4)},
                           "n_train": r["n_train"], "n_tune": r["n_tune"], "M2_best": r["m2_best"],
                           "M1_coef": {a: dict(zip(b["names"], [round(x, 6) for x in b["beta"]])) for a, b in r["M1"].coefs.items()},
                           "models": f"models/M1_u{s}.pkl, models/M2_u{s}.pkl"}
    cp = Path(cfg["_path"])
    cj = json.loads(cp.read_text(encoding="utf-8"))
    cj["fitted"] = fitted
    cp.write_text(json.dumps(cj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log_to(fh, f"fit done ({time.time() - t0:.0f} s); choice {feat['choice']}; fitted block written into {cp.name}")
    return fits


def load_models(out: Path) -> dict:
    md = out / "models"
    feat = json.loads((md / "features.json").read_text(encoding="utf-8"))
    res = {}
    for s in SCALES:
        ch = feat["choice"][str(s)] if str(s) in feat["choice"] else feat["choice"][s]
        with open(md / f"{ch}_u{s}.pkl", "rb") as f:
            res[s] = {"choice": ch, "model": model_from_dict(pickle.load(f))}
    return res


# ====================================================================================================== validity
def validity_metrics(u: np.ndarray, uh: np.ndarray, loco: np.ndarray, vc: dict) -> dict:
    from scipy.stats import spearmanr
    fin = np.isfinite(u) & np.isfinite(uh)
    big = fin & (u >= float(vc["min_u_inps"]))
    lo = fin & loco
    r = {"n": int(fin.sum()), "n_big": int(big.sum()), "n_loco": int(lo.sum())}
    if big.sum() >= 3:
        r["mdare"] = float(np.median(np.abs(uh[big] - u[big]) / u[big]))
        r["spearman"] = float(spearmanr(uh[big], u[big]).statistic)
    else:
        r["mdare"], r["spearman"] = np.nan, np.nan
    if lo.sum() >= 3:
        r["p50_u"], r["p95_u"] = (float(x) for x in np.percentile(u[lo], [50, 95]))
        r["p50_hat"], r["p95_hat"] = (float(x) for x in np.percentile(uh[lo], [50, 95]))
        r["d50"], r["d95"] = r["p50_hat"] / r["p50_u"] - 1.0, r["p95_hat"] / r["p95_u"] - 1.0
    else:
        r.update({"p50_u": np.nan, "p95_u": np.nan, "p50_hat": np.nan, "p95_hat": np.nan, "d50": np.nan, "d95": np.nan})
    r["c_mdare"] = bool(r["mdare"] <= float(vc["max_mdare"]))
    r["c_spearman"] = bool(r["spearman"] >= float(vc["min_spearman"]))
    r["c_loco"] = bool(abs(r["d50"]) <= float(vc["loco_max_rel"]) and abs(r["d95"]) <= float(vc["loco_max_rel"]))
    r["valid"] = bool(r["c_mdare"] and r["c_spearman"] and r["c_loco"])
    return r


def validity_boot(u, uh, loco, blk, vc: dict, n_boot: int, rng) -> dict:
    """Block-bootstrap 2.5-97.5 % intervals of the validity metrics (explicit resampling of whole blocks)."""
    from scipy.stats import spearmanr
    ub = np.unique(blk)
    pos = {b: np.flatnonzero(blk == b) for b in ub}
    acc = {k: [] for k in ("mdare", "spearman", "d50", "d95")}
    thr = float(vc["min_u_inps"])
    for _ in range(n_boot):
        pick = rng.choice(ub, size=len(ub), replace=True)
        ii = np.concatenate([pos[b] for b in pick])
        uu, hh, ll = u[ii], uh[ii], loco[ii]
        fin = np.isfinite(uu) & np.isfinite(hh)
        big = fin & (uu >= thr)
        lo = fin & ll
        if big.sum() >= 3:
            acc["mdare"].append(np.median(np.abs(hh[big] - uu[big]) / uu[big]))
            acc["spearman"].append(spearmanr(hh[big], uu[big]).statistic)
        if lo.sum() >= 3:
            q_u = np.percentile(uu[lo], [50, 95])
            q_h = np.percentile(hh[lo], [50, 95])
            acc["d50"].append(q_h[0] / q_u[0] - 1.0)
            acc["d95"].append(q_h[1] / q_u[1] - 1.0)
    out = {}
    for k, v in acc.items():
        v = np.asarray(v, float)
        v = v[np.isfinite(v)]
        out[f"{k}_lo"] = float(np.percentile(v, 2.5)) if len(v) else np.nan
        out[f"{k}_hi"] = float(np.percentile(v, 97.5)) if len(v) else np.nan
    return out


# ====================================================================================================== R1 / R2
def band_mask(u: np.ndarray, band: str, edges) -> np.ndarray:
    a, b = float(edges[0]), float(edges[1])
    if band == "all":
        return np.isfinite(u)
    if band == "lt5":
        return u < a
    if band == "5to15":
        return (u >= a) & (u <= b)
    return u > b


def ratio_table(d: pd.DataFrame, ref: np.ndarray, vals: dict, n_boot: int, rng, mae: bool, keys: dict) -> list:
    """p50 / p95 ratio - 1 of every series in vals against ref (paired 10-min block bootstrap via block histograms),
    + median absolute error vs ref when mae."""
    blk, K = DS.block_codes(d["animal"], d["period"], d["block"])
    cnt = FA.boot_counts(K, n_boot, rng)
    qr = DS.hist_boot_q(ref, blk, cnt, EDGES, [0.5, 0.95])
    ex_r = np.percentile(ref, [50, 95])
    rows = []
    for m, v in vals.items():
        qm = DS.hist_boot_q(v, blk, cnt, EDGES, [0.5, 0.95])
        ex = np.percentile(v, [50, 95])
        row = {**keys, "track": m, "n_sec": int(len(v)), "n_blocks": int(K), "p50_ref": float(ex_r[0]), "p95_ref": float(ex_r[1]),
               "p50": float(ex[0]), "p95": float(ex[1])}
        for qi, qn in enumerate(("50", "95")):
            row[f"d{qn}"] = float(ex[qi] / ex_r[qi] - 1.0)
            with np.errstate(invalid="ignore", divide="ignore"):
                b = qm[1:, qi] / qr[1:, qi] - 1.0
            row[f"d{qn}_lo"] = float(np.nanpercentile(b, 2.5))
            row[f"d{qn}_hi"] = float(np.nanpercentile(b, 97.5))
        if mae:
            e = np.abs(v - ref)
            row["mae"] = float(np.median(e))
            qe = DS.hist_boot_q(e, blk, cnt, EDGES, [0.5])[1:, 0]
            row["mae_lo"], row["mae_hi"] = float(np.nanpercentile(qe, 2.5)), float(np.nanpercentile(qe, 97.5))
        rows.append(row)
    return rows


def biased_flag(r: dict, bound: float) -> bool:
    return bool(r["d50_lo"] > bound or r["d50_hi"] < -bound or r["d95_lo"] > bound or r["d95_hi"] < -bound)


def r1_tables(D: pd.DataFrame, cfg: dict, rng) -> pd.DataFrame:
    rs = cfg["rescoring"]
    nb = int(cfg["bootstrap"]["n_boot"])
    rows = []
    for scale in SCALES:
        u_all = D[f"u{scale}"].to_numpy(float)
        V = {m: D[f"v{scale}_{m}"].to_numpy(float) for m in TRACKS}
        paired = D["clean"].to_numpy(bool) & np.isfinite(u_all) & np.all([np.isfinite(v) for v in V.values()], axis=0)
        for s in SETS:
            sm = paired & ((D["set"] == s).to_numpy() if s != "all" else True)
            for band in BANDS:
                m = sm & band_mask(u_all, band, rs["bands_inps"])
                if m.sum() < 20:
                    continue
                d = D[m]
                rr = ratio_table(d, u_all[m], {k: v[m] for k, v in V.items()}, nb, rng, True,
                                 {"scale": scale, "set": s, "band": band})
                for r in rr:
                    r["biased"] = biased_flag(r, float(rs["bias_bound"]))
                    r["dist"] = max(abs(r["d50"]), abs(r["d95"]))
                rows.extend(rr)
    return pd.DataFrame(rows)


def r2_tables(D: pd.DataFrame, pred: dict, valid_scales: list, cfg: dict, rng) -> pd.DataFrame:
    nb = int(cfg["bootstrap"]["n_boot"])
    rows = []
    for scale in valid_scales:
        ph = pred[scale]
        V = {m: D[f"v{scale}_{m}"].to_numpy(float) for m in TRACKS}
        base = D["ok"].to_numpy(bool) & ~D["still"].to_numpy(bool) & np.isfinite(ph) & np.all([np.isfinite(v) for v in V.values()], axis=0)
        for s in SETS:
            sm = base & ((D["set"] == s).to_numpy() if s != "all" else True)
            for sub in ("nonstill", "loco"):
                m = sm & ((D["state"] == int(cfg["validity"]["loco_state"])).to_numpy() if sub == "loco" else True)
                if m.sum() < 20:
                    continue
                rr = ratio_table(D[m], ph[m], {k: v[m] for k, v in V.items()}, nb, rng, False, {"scale": scale, "set": s, "subset": sub})
                for r in rr:
                    r["dist"] = max(abs(r["d50"]), abs(r["d95"]))
                    r["biased"] = biased_flag(r, float(cfg["rescoring"]["bias_bound"]))
                rows.extend(rr)
    return pd.DataFrame(rows)


def reading(R1: pd.DataFrame, R2: pd.DataFrame, cfg: dict) -> dict:
    rs = cfg["rescoring"]
    pr = rs["primary"]
    out = {}
    for scale in SCALES:
        c = R1[(R1.scale == scale) & (R1.set == pr["set"]) & (R1.band == pr["band"]) & R1.track.isin(rs["smoothed"])]
        if not len(c):
            continue
        best = c.loc[c.dist.idxmin()]
        out[f"R1_u{scale}"] = {"least_biased": best.track, "dist": float(best.dist),
                               "biased": sorted(c[c.biased].track.tolist(), key=SMOOTHED.index),
                               "order": c.sort_values("dist").track.tolist()}
    if R2 is not None and len(R2):
        for scale in sorted(R2.scale.unique()):
            c = R2[(R2.scale == scale) & (R2.set == "all") & (R2.subset == "nonstill") & R2.track.isin(rs["smoothed"])]
            if len(c):
                best = c.loc[c.dist.idxmin()]
                out[f"R2_u{scale}"] = {"least_biased": best.track, "dist": float(best.dist), "order": c.sort_values("dist").track.tolist()}
    ps = pr["scale"]
    r1 = out.get(f"R1_u{ps}", {})
    r2 = out.get(f"R2_u{ps}")
    if r2 is None:
        out["least_biased"] = r1.get("least_biased")
        out["least_biased_basis"] = f"R1 at the {ps}-s scale (proxy not valid at that scale -> no R2)"
    elif r2["least_biased"] == r1.get("least_biased"):
        out["least_biased"] = r1["least_biased"]
        out["least_biased_basis"] = f"R1 and R2 at the {ps}-s scale agree"
    else:
        out["least_biased"] = None
        out["least_biased_basis"] = f"not unique: R1 -> {r1.get('least_biased')}, R2 -> {r2['least_biased']} ({ps}-s scale)"
    out["biased"] = r1.get("biased", [])
    return out


# ====================================================================================================== evaluate
def run_evaluate(out: Path, cfg: dict, fh=None) -> dict:
    t0 = time.time()
    acfg = load_acfg(cfg)
    tb = out / "tables"
    D = attach_features(load_seconds(out, cfg, acfg), cfg)
    models = load_models(out)
    pred = {s: models[s]["model"].predict(D) for s in SCALES}
    for s in SCALES:
        D[f"hat{s}"] = pred[s]
    vc = cfg["validity"]
    nb = int(cfg["bootstrap"]["n_boot"])
    seed = int(cfg["bootstrap"]["seed"])
    loco = (D["state"] == int(vc["loco_state"])).to_numpy()
    # ---------------- validity (test night) + robustness / in-sample rows (same metrics, reported)
    vrows = []
    groups = [("test", D["role"] == "test"), ("rain_0903", D["period"] == "night_20260903"), ("rain_0909", D["period"] == "night_20260909"),
              ("rain_both", D["role"] == "robustness"), ("tune", D["role"] == "tune"), ("train", D["role"] == "train")]
    for gi, (gname, gm) in enumerate(groups):
        for s in SCALES:
            u = D[f"u{s}"].to_numpy(float)
            m = gm.to_numpy() & D["clean"].to_numpy(bool) & np.isfinite(u)
            r = validity_metrics(u[m], pred[s][m], loco[m], vc)
            r.update(validity_boot(u[m], pred[s][m], loco[m], DS.block_codes(D["animal"][m], D["period"][m], D["block"][m])[0], vc, nb,
                                   np.random.default_rng(seed + 10 * gi + s)))
            r.update({"group": gname, "scale": s, "model": models[s]["choice"], "coverage": float(np.isfinite(pred[s][m]).mean()) if m.any() else np.nan})
            vrows.append(r)
    VT = pd.DataFrame(vrows)
    VT.to_csv(tb / "validity.csv", index=False)
    valid = {s: bool(VT[(VT.group == "test") & (VT.scale == s)].valid.iloc[0]) for s in SCALES}
    for s in SCALES:
        r = VT[(VT.group == "test") & (VT.scale == s)].iloc[0]
        log_to(fh, f"TEST {s}-s ({r.model}): MdARE {r.mdare:.3f} (<= {vc['max_mdare']}), Spearman {r.spearman:.3f} (>= {vc['min_spearman']}), "
                   f"loco p50 {r.d50:+.3f} / p95 {r.d95:+.3f} (+-{vc['loco_max_rel']}) -> {'VALID' if r.valid else 'not valid'}")
    # per-animal test-night breakdown (reported)
    arows = []
    for a in cfg["animals"]:
        for s in SCALES:
            u = D[f"u{s}"].to_numpy(float)
            m = (D["role"] == "test").to_numpy() & D["clean"].to_numpy(bool) & np.isfinite(u) & (D["animal"] == a).to_numpy()
            arows.append({"animal": a, "scale": s, **validity_metrics(u[m], pred[s][m], loco[m], vc)})
    pd.DataFrame(arows).to_csv(tb / "validity_by_animal.csv", index=False)
    # ---------------- R1, R2
    R1 = r1_tables(D, cfg, np.random.default_rng(seed + 101))
    R1.to_csv(tb / "r1_clean_reference.csv", index=False)
    valid_scales = [s for s in SCALES if valid[s]]
    R2 = r2_tables(D, pred, valid_scales, cfg, np.random.default_rng(seed + 202)) if valid_scales else pd.DataFrame()
    if len(R2):
        R2.to_csv(tb / "r2_imu_proxy.csv", index=False)
    rd = reading(R1, R2, cfg)
    log_to(fh, f"R1/R2 reading: {json.dumps(rd, default=str)}")
    # ---------------- clean seconds table, floor, counts
    keep = ["animal", "period", "set", "role", "sec", "block", "state", "u3", "u1", "hat3", "hat1", "mx", "my"] + \
           [f"v{s}_{m}" for s in SCALES for m in TRACKS] + feat_cols(cfg)
    D.loc[D["clean"], keep].to_csv(tb / "clean_seconds.csv.gz", index=False, float_format="%.5g")
    Dall = load_seconds(out, cfg, acfg, only_nights=False)
    FL = Dall[Dall["floor_ok"]]
    frows = []
    for (kind, st), g in list(FL.groupby(["kind", "set"])) + [(("all", "all"), FL)]:
        for s in SCALES:
            v = g[f"u{s}"].to_numpy(float)
            v = v[np.isfinite(v)]
            if not len(v):
                continue
            q = np.percentile(v, [50, 90, 95, 99])
            frows.append({"kind": kind, "set": st, "scale": s, "n_sec": int(len(v)), "n_segments": int(g.groupby(["animal", "period", "floor_sid"]).ngroups),
                          "mean": float(v.mean()), "p50": q[0], "p90": q[1], "p95": q[2], "p99": q[3], "frac_ge5": float((v >= 5).mean())})
    FT = pd.DataFrame(frows)
    FT.to_csv(tb / "noise_floor.csv", index=False)
    crow = []
    for (pk, a), g in D.groupby(["period", "animal"]):
        crow.append({"period": pk, "animal": a, "set": g.set.iloc[0], "role": g.role.iloc[0], "n_sec": len(g), "imu_ok": int(g.ok.sum()),
                     "fix_ok": int(g.fix_ok.sum()), "med_ok": int(g.med_ok.sum()), "outside": int((g.out_a & g.out_b).sum()),
                     "fix_ok_outside_imu": int((g.ok & g.fix_ok & g.med_ok & g.out_a & g.out_b).sum()), "clean": int(g.clean.sum()),
                     "clean_u1": int((g.clean & g.u1.notna()).sum()), "clean_loco": int((g.clean & (g.state == 3)).sum()),
                     "clean_ge5": int((g.clean & (g.u3 >= 5)).sum()), "fail_rate": int((~g.rate_ok).sum()), "fail_anch": int((g.n_low > 0).sum()),
                     "fail_invalid": int((g.n_inv > 0).sum()), "fail_mask": int((g.n_msk > 0).sum()), "fail_jump": int((g.n_jmp > 0).sum())})
    CT = pd.DataFrame(crow)
    CT.to_csv(tb / "clean_counts.csv", index=False)
    # proxy predictions for every night second (compact)
    D[["animal", "period", "sec", "ok", "still", "state", "hat3", "hat1", "qc_w3", "qc_w1"]].to_csv(tb / "proxy_all_seconds.csv.gz", index=False,
                                                                                                float_format="%.4g")
    # ---------------- deliverable for ephys (only if valid)
    deliv = None
    if valid_scales:
        deliv = write_deliverable(D, valid_scales, models, cfg, out)
        log_to(fh, f"ephys deliverable written: {deliv['root']} ({deliv['n_files']} files, scales {valid_scales})")
    else:
        log_to(fh, "proxy not valid at either scale -> no ephys deliverable, no R2")
    # ---------------- summary
    reps = pd.read_csv(tb / "reproduction.csv")
    repro = {}
    if "repro_ok_agree" in reps:
        r_ = reps.dropna(subset=["repro_ok_agree"])
        repro = {"n_animal_nights": int(len(r_)), "ok_agree_min": float(r_.repro_ok_agree.min()), "still_agree_min": float(r_.repro_still_agree.min()),
                 "state_agree_min": float(r_.repro_state_agree.min()), "vedba_maxdiff": float(r_.repro_vedba_maxdiff.max()),
                 "sbf_maxdiff": float(r_.repro_sbf_maxdiff.max()), "raw32_vs_u3_max": float(r_.raw32_vs_u3_max.max()),
                 "raw32_vs_u1_max": float(r_.raw32_vs_u1_max.max()),
                 "feature_cache": r_.feature_cache.value_counts().to_dict() if "feature_cache" in r_ else {}}
    mc = pd.read_csv(tb / "model_choice.csv")
    summ = {"valid": {f"u{s}": valid[s] for s in SCALES}, "models": {f"u{s}": models[s]["choice"] for s in SCALES},
            "model_choice": mc.to_dict("records"),
            "test": VT[VT.group == "test"].to_dict("records"), "reading": rd, "reproduction": repro,
            "clean_counts": {"total": int(CT.clean.sum()), "by_role": CT.groupby("role").clean.sum().to_dict(),
                             "u1_total": int(CT.clean_u1.sum())},
            "noise_floor": FT.to_dict("records"), "deliverable": deliv, "runtime_evaluate_s": round(time.time() - t0, 1)}
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=_jd), encoding="utf-8")
    log_to(fh, f"evaluate done ({time.time() - t0:.0f} s)")
    return {"D": D, "VT": VT, "R1": R1, "R2": R2, "reading": rd, "valid": valid, "models": models, "FT": FT, "CT": CT, "FL": FL,
            "summary": summ, "deliv": deliv, "repro": repro, "mc": mc, "grid": pd.read_csv(tb / "m2_tuning_grid.csv"),
            "coef": pd.read_csv(tb / "m1_coefficients.csv"), "VA": pd.read_csv(tb / "validity_by_animal.csv"), "cfg": cfg, "acfg": acfg}


def write_deliverable(D: pd.DataFrame, valid_scales: list, models: dict, cfg: dict, out: Path) -> dict:
    root = Path(cfg["deliverable_root"])
    n = 0
    for (a, pk), g in D.groupby(["animal", "period"]):
        g = g[g["ok"]]
        parts = [pd.DataFrame({"sec": g["sec"].to_numpy(np.int64), "speed_hat": g[f"hat{s}"].to_numpy(float), "scale": f"{s}s",
                               "qc": g[f"qc_w{s}"].to_numpy(float), "ok": True}) for s in valid_scales]
        dd = pd.concat(parts, ignore_index=True).sort_values(["sec", "scale"])
        (root / a).mkdir(parents=True, exist_ok=True)
        dd.to_csv(root / a / f"{pk}.csv.gz", index=False, float_format="%.4g")
        n += 1
    ch = {s: models[s]["choice"] for s in valid_scales}
    txt = f"""# Head-IMU speed proxy per second (cohort {cfg['_cohort']}) - for ephys
<!-- written by {DRIVER} -->

`<SFxx>/<period>.csv.gz`: one row per IMU-QC-ok field-PC second of the failure audit's night periods (21:00-04:20) and per
**valid** scale. Columns: `sec` (Unix s; the second [sec, sec + 1)), `speed_hat` (predicted head speed, in/s, WISER inch
frame), `scale` (`3s` = speed over the 3 s centred on sec + 0.5, `1s` = over the 1 s centred there), `qc` (valid 50-Hz
share of the feature window), `ok` (the audit's per-second QC; always true here).

Model: {', '.join(f'{s} s -> {ch[s]}' for s in valid_scales)} (plan `{PLAN}`; fitted on clean open-field WISER seconds
of nights 09-05/06, chosen on 09-07, validated on 09-08; run `{out}`). Valid scales: {', '.join(f'{s} s' for s in valid_scales)}.
Validity was shown only on clean open-field seconds; in the houses, in the rain and under poor anchors it is assumed, not
shown (head motion mix differs). Head speed != body speed. Whole-cohort application is a later step on request.
"""
    (root / "README.md").write_text(txt, encoding="utf-8")
    return {"root": str(root), "n_files": n, "scales": valid_scales, "models": ch}


def _jd(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


# ====================================================================================================== figures
def make_figures(E: dict, fdir: Path) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cohort = E["cfg"]["_cohort"]
    figs = {}
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    D = E["D"]
    # ---- 1. noise floor vs clean night speeds
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    bins = np.geomspace(0.02, 100, 70)
    for ax, s in zip(axes, SCALES):
        fl = E["FL"][f"u{s}"].dropna().to_numpy(float)
        cl = D.loc[D["clean"], f"u{s}"].dropna().to_numpy(float)
        ax.hist(np.clip(cl, 0.02, 100), bins=bins, weights=np.full(len(cl), 1.0 / max(len(cl), 1)), histtype="step", lw=1.6,
                color="#1f77b4", label=f"clean open-field night seconds (n {len(cl):,})")
        ax.hist(np.clip(fl, 0.02, 100), bins=bins, weights=np.full(len(fl), 1.0 / max(len(fl), 1)), histtype="step", lw=1.6,
                color="#d62728", label=f"noise floor: certified still, ≥ 8 anchors (n {len(fl):,})")
        if len(fl):
            ax.axvline(np.percentile(fl, 95), color="#d62728", ls=":", lw=1)
        ax.axvline(5.0, color="#7f7f7f", ls="--", lw=0.8)
        ax.set_xscale("log")
        ax.set_xlabel(f"$u_{s}$ (in/s, log)")
        ax.set_ylabel("share of seconds per log bin")
        ax.set_title(f"{s}-s scale (dotted: floor p95; dashed: 5 in/s)")
        ax.set_ylim(0, ax.get_ylim()[1] * 1.3)
        ax.legend(frameon=False, fontsize=7.5, loc="upper left")
    fig.tight_layout()
    f = f"{STEM}_floor_{cohort}.png"
    fig.savefig(fdir / f, dpi=150)
    plt.close(fig)
    figs["floor"] = f
    # ---- 2. proxy vs reference on the test night (+ locomoting quantiles)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    T = D[(D["role"] == "test") & D["clean"]]
    for ax, s in zip(axes[:2], SCALES):
        u, h = T[f"u{s}"].to_numpy(float), T[f"hat{s}"].to_numpy(float)
        m = np.isfinite(u) & np.isfinite(h)
        hb = ax.hexbin(np.clip(u[m], 0, 40), np.clip(h[m], 0, 40), gridsize=50, bins="log", cmap="Greys", mincnt=1, extent=(0, 40, 0, 40))
        ax.plot([0, 40], [0, 40], color="#d62728", lw=1)
        ax.axvline(5, color="#7f7f7f", ls="--", lw=0.8)
        r = E["VT"][(E["VT"].group == "test") & (E["VT"].scale == s)].iloc[0]
        ax.set_title(f"test night 09-08, {s}-s ({r.model}): MdARE {r.mdare:.2f}, ρ {r.spearman:.2f}\n"
                     f"loco p50 {100 * r.d50:+.0f} %, p95 {100 * r.d95:+.0f} % → {'VALID' if r.valid else 'not valid'}", fontsize=8.5)
        ax.set_xlabel(f"clean WISER $u_{s}$ (in/s; clipped at 40)")
        ax.set_ylabel("IMU proxy (in/s)")
        fig.colorbar(hb, ax=ax, label="seconds (log)")
    ax = axes[2]
    VT = E["VT"]
    grp = ["train", "tune", "test", "rain_0903", "rain_0909"]
    x = np.arange(len(grp))
    for k, (s, mk) in enumerate(zip(SCALES, ("o", "s"))):
        for j, (col, nm) in enumerate((("d50", "p50"), ("d95", "p95"))):
            vals = [VT[(VT.group == g) & (VT.scale == s)][col].iloc[0] for g in grp]
            lo = [VT[(VT.group == g) & (VT.scale == s)][f"{col}_lo"].iloc[0] for g in grp]
            hi = [VT[(VT.group == g) & (VT.scale == s)][f"{col}_hi"].iloc[0] for g in grp]
            xx = x + (k * 2 + j - 1.5) * 0.13
            yerr = np.clip(np.vstack([np.subtract(vals, lo), np.subtract(hi, vals)]), 0, None) * 100
            ax.errorbar(xx, np.array(vals) * 100, yerr=yerr, fmt=mk, ms=5, capsize=2, mfc="white" if j else None,
                        color=("#1f77b4" if s == 3 else "#ff7f0e"), label=f"{s}-s {nm}")
    ax.axhspan(-10, 10, color="#2ca02c", alpha=0.12, lw=0)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xticks(x, ["train\n09-05/06", "tune\n09-07", "TEST\n09-08", "rain\n09-03", "rain\n09-09"])
    ax.set_ylabel("proxy quantile / $u$ quantile − 1 (%)")
    ax.set_title("IMU-locomoting clean seconds (band = ± 10 %)", fontsize=8.5)
    ax.legend(frameon=False, fontsize=7, ncol=2)
    fig.tight_layout()
    f = f"{STEM}_test_{cohort}.png"
    fig.savefig(fdir / f, dpi=150)
    plt.close(fig)
    figs["test"] = f
    # ---- 3. R1 bias per track
    R1 = E["R1"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharey="row")
    for ci, s in enumerate(SCALES):
        ax = axes[0, ci]
        c = R1[(R1.scale == s) & (R1.set == "all") & (R1.band == "all") & R1.track.isin(SMOOTHED)].set_index("track").reindex(SMOOTHED)
        x = np.arange(len(SMOOTHED))
        for j, (col, mk) in enumerate((("d50", "o"), ("d95", "D"))):
            v = c[col].to_numpy(float) * 100
            err = np.clip(np.vstack([v - c[f"{col}_lo"].to_numpy(float) * 100, c[f"{col}_hi"].to_numpy(float) * 100 - v]), 0, None)
            ax.errorbar(x + (j - 0.5) * 0.25, v, yerr=err, fmt=mk, ms=5, capsize=2, color="#333333", mfc="white" if j else "#333333",
                        label="p50" if j == 0 else "p95")
        ax.axhspan(-10, 10, color="#2ca02c", alpha=0.12, lw=0)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_xticks(x, [LABEL[m].split(" ")[0] for m in SMOOTHED])
        ax.set_title(f"R1, {s}-s scale, all nights, all clean seconds", fontsize=9)
        ax.set_ylabel("track quantile / clean $u$ quantile − 1 (%)")
        ax.legend(frameon=False, fontsize=7.5)
        ax = axes[1, ci]
        for k, band in enumerate(BANDS[1:]):
            c = R1[(R1.scale == s) & (R1.set == "all") & (R1.band == band) & R1.track.isin(SMOOTHED)].set_index("track").reindex(SMOOTHED)
            v = c["d50"].to_numpy(float) * 100
            err = np.clip(np.vstack([v - c["d50_lo"].to_numpy(float) * 100, c["d50_hi"].to_numpy(float) * 100 - v]), 0, None)
            ax.errorbar(x + (k - 1) * 0.22, v, yerr=err, fmt="o", ms=4, capsize=2, color=("#9ecae1", "#3182bd", "#08519c")[k],
                        label=f"$u_{s}$ {BAND_LABEL[band]} in/s")
        ax.axhspan(-10, 10, color="#2ca02c", alpha=0.12, lw=0)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_xticks(x, [LABEL[m].split(" ")[0] for m in SMOOTHED])
        ax.set_title(f"R1 p50 by reference speed band, {s}-s (bands select on the noisy reference)", fontsize=9)
        ax.set_ylabel("p50 ratio − 1 (%)")
        ax.legend(frameon=False, fontsize=7.5)
    fig.tight_layout()
    f = f"{STEM}_r1_{cohort}.png"
    fig.savefig(fdir / f, dpi=150)
    plt.close(fig)
    figs["r1"] = f
    # ---- 4. R2 (if valid)
    R2 = E["R2"]
    if R2 is not None and len(R2):
        scs = sorted(R2.scale.unique(), reverse=True)
        fig, axes = plt.subplots(1, len(scs), figsize=(6.5 * len(scs), 3.8), squeeze=False)
        for ax, s in zip(axes[0], scs):
            x = np.arange(len(TRACKS))
            for k, sub in enumerate(("nonstill", "loco")):
                c = R2[(R2.scale == s) & (R2.set == "all") & (R2.subset == sub)].set_index("track").reindex(TRACKS)
                for j, (col, mk) in enumerate((("d50", "o"), ("d95", "D"))):
                    v = c[col].to_numpy(float) * 100
                    err = np.clip(np.vstack([v - c[f"{col}_lo"].to_numpy(float) * 100, c[f"{col}_hi"].to_numpy(float) * 100 - v]), 0, None)
                    ax.errorbar(x + (k * 2 + j - 1.5) * 0.16, v, yerr=err, fmt=mk, ms=4, capsize=2, color=("#1f77b4", "#ff7f0e")[k],
                                mfc="white" if j else None, label=f"{'non-still' if sub == 'nonstill' else 'IMU-locomoting'} {col.replace('d', 'p')}")
            ax.axhspan(-10, 10, color="#2ca02c", alpha=0.12, lw=0)
            ax.axhline(0, color="k", lw=0.6)
            ax.set_xticks(x, [LABEL[m].split(" ")[0] for m in TRACKS])
            ax.set_ylabel("track quantile / proxy quantile − 1 (%)")
            ax.set_title(f"R2 vs the IMU proxy, {s}-s scale, all nights (houses, low anchors, rain included)", fontsize=9)
            ax.legend(frameon=False, fontsize=7)
        fig.tight_layout()
        f = f"{STEM}_r2_{cohort}.png"
        fig.savefig(fdir / f, dpi=150)
        plt.close(fig)
        figs["r2"] = f
    return figs


# ====================================================================================================== report
def _f(x, nd: int = 2) -> str:
    try:
        if x is None or not np.isfinite(float(x)):
            return "–"
    except (TypeError, ValueError):
        return str(x)
    return f"{float(x):.{nd}f}"


def _pc(x, nd: int = 1, sign: bool = True) -> str:
    try:
        if x is None or not np.isfinite(float(x)):
            return "–"
    except (TypeError, ValueError):
        return "–"
    return f"{100 * float(x):+.{nd}f} %" if sign else f"{100 * float(x):.{nd}f} %"


def _ci(r, col: str, nd: int = 1) -> str:
    return f"{_pc(r[col], nd)} [{_pc(r[col + '_lo'], nd)}, {_pc(r[col + '_hi'], nd)}]"


DEFINITIONS = r"""
## Definitions

All positions are in the WISER native **inch** frame (unverified offset origin); speeds in **in/s**. Times are field-PC
Unix seconds; WISER fix times are aligned to the IMU clock, $t_i = t_i^{\mathrm{fix}} - \tau^*$ ($\tau^*$ = 0.20 / 0.15 / 0.10
/ 0.20 / 0.15 s for SF07 / 08 / 09 / 10 / 12). $\mathbf z_i$ = raw fix $i$ (float64 from the fix cache), $A_i$ = its
`anchors_used`. A **second** $s$ is the interval $[s, s+1)$ of the audit's `imu_seconds`; its centre is $c = s + 0.5$
(Amendment 1.1).

### Window median ($\mathbf m_h(g)$)
$$\mathbf m_h(g) = \operatorname{median}_{\text{coord}}\{\mathbf z_i : t_i \in [g-h, g+h)\},\quad \text{defined iff } \#\{i\} \ge 3$$
**Text:** coordinate-wise median of the raw fixes in a window of length $2h$ centred on $g$. Units: in. $h = 0.5$ s for the
3-s scale, $h = 0.375$ s for the 1-s scale. The median removes most single-fix outliers without a motion model.

### Clean WISER speed ($u_3$, $u_1$)
$$u_3(s) = \frac{\lVert \mathbf m_{0.5}(c+1.5) - \mathbf m_{0.5}(c-1.5)\rVert}{3\ \mathrm{s}},\qquad
u_1(s) = \frac{\lVert \mathbf m_{0.375}(c+0.5) - \mathbf m_{0.375}(c-0.5)\rVert}{1\ \mathrm{s}}$$
**Text:** displacement of the window medians over 3 s (1 s) divided by the baseline: a nearly model-free head speed.
Units: in/s; range $[0, \infty)$. It is the *target* only on clean seconds. Its noise is set by the per-axis fix scatter
(≈ 1.6–3.7 in at 8–9 anchors) divided by $\sqrt{n}$ and by the baseline, so $u_1$ is noisier than $u_3$.

### Clean second
Second $s$ is clean iff, with span $\mathcal S = [c-2, c+2]$ s: every fix in $\mathcal S$ has $A_i \ge 8$, `valid` true and
none of the masks `m_handling`, `m_silence`, `m_tag_validity`, `m_adc_lane`; no **jump** touches $\mathcal S$ (a consecutive
raw-fix pair $(i, i+1)$ with $\lVert\mathbf z_{i+1}-\mathbf z_i\rVert > 30$ in and $t_{i+1}-t_i \le 0.35$ s, at least one of
the two fixes in $\mathcal S$); $\#\{i : t_i\in\mathcal S\} \ge 12$ (fix rate ≥ 3 Hz); both medians $\mathbf m_{0.5}(c\pm1.5)$
exist and lie outside `house_1` and `house_2` grown by 14 in on every side; and the audit's per-second `ok` of $s$ is true
(IMU QC, handling ± 5 min, all-tag silences ± 2 min, tag validity, ADC lane). $u_1$ uses the same clean seconds and needs
its own two medians. **Thresholds:** 8 anchors = the per-axis static SD ≈ 1.6–3.7 in regime; 30 in / 0.35 s = the audit's
jump definition; 14 in = 2 × the 7-in jitter floor (house buffer used by every WISER zone rule).

### Noise floor ($F_3$, $F_1$)
$$F_k = \{u_k(s) : s \text{ a floor second}\}$$
A floor second has its span $\mathcal S$ inside a certified still segment (the audit's primary, scored segments ≥ 30 s,
trimmed by 1 s) and meets every clean-second condition except the house one. **Text:** the distribution of the reference
when the true head speed is 0 (head IMU certified still), at ≥ 8 anchors. Units: in/s. Reported as p50 / p90 / p95 / p99;
values of $u_k$ below the floor's p95 cannot be told from stillness. Caveat: the still segments are in the houses.

### Valid 50-Hz IMU sample, QC share ($q_w$)
Valid = finite, not saturated / frozen / invalid / unreliable, no frozen-rule run, outside handling ± 5 min, all-tag
silences ± 2 min, the ADC lane and the tag window (the audit's `sample_valid`). $q_w(s) = n_{\mathrm{valid}} / (50\,w)$ for
the window $W_w(s)$: $W_1 = [s, s+1)$, $W_3 = [s-1, s+2)$. Range $[0, 1]$.

### IMU features (per window $W_w$, valid samples only)
- **VeDBA mean / p90** $\overline{\mathrm{VeDBA}}_w$, $\mathrm{VeDBA}_{w,90}$: mean and 90th percentile of make_imu's VeDBA
  (dynamic body acceleration magnitude). m/s². High = vigorous head movement.
- **Horizontal dynamic acceleration RMS** $H_w = \sqrt{\operatorname{mean}_{n\in W_w}(\tilde a_{x,n}^2 + \tilde a_{y,n}^2)}$, $\tilde a$ =
  earth-frame linear acceleration after a zero-phase order-4 Butterworth band-pass 0.5–8 Hz. m/s².
- **Stride-band power** $P_w = \sum_{k: f_k\in[2,8]\,\mathrm{Hz}} P_k$, with $P_k = 2\lvert X_k\rvert^2/(N\sum_n w_n^2)$ the one-sided
  Hann periodogram of the demeaned vertical earth-frame linear acceleration over the $N = 50w$ samples. (m/s²)².
  High = strong rhythmic vertical head motion (stepping).
- **Stride peak frequency** $f^{\ast}_w = \arg\max_{f_k\in[2,8]} P_k$. Hz (bins of $1/w$ Hz). Step frequency rises with speed.
- **Stride-band share** $\rho_w = P_w / \sum_{f_k\in[1,20]} P_k$. Range $[0,1]$; high = the vertical motion is mostly stepping.
- **$|\omega|$ mean, $|$turn rate$|$ mean**: mean head angular speed and mean absolute yaw rate (make_imu). deg/s.
- **Pitch SD**: SD of make_imu pitch. deg. High = head bobbing / rearing.
Time-domain features need $q_w \ge 0.5$, spectral ones an ungapped window with ≥ 90 % valid samples, else missing.

### Models
**M1** (per animal $a$): $\hat u = \beta_{a,0} + \beta_{a,1}\overline{\mathrm{VeDBA}}_w + \beta_{a,2}P_w + \beta_{a,3}f^{\ast}_w + \beta_{a,4}\overline{|\omega|}_w$,
ordinary least squares on the clean training seconds ($w = 3$ for $u_3$, $w = 1$ for $u_1$). **M2**: scikit-learn
`HistGradientBoostingRegressor` (absolute-error loss) on all 20 features + animal one-hot, hyper-parameters from the grid
learning rate {0.05, 0.1} × max depth {3, 5} × min leaf {50, 200} chosen by the tuning-night MAE. Both clipped at 0.
**Choice:** the model with the lower tuning-night $\mathrm{MAE} = \operatorname{median}_s\lvert\hat u(s) - u(s)\rvert$ (clean
tuning seconds where both predict), per scale. Train = nights 09-05, 09-06; tune = 09-07; test = 09-08.

### Validity rule (pre-registered; test night, clean seconds)
$$\mathrm{MdARE} = \operatorname{median}_{s: u\ge 5}\frac{\lvert\hat u(s) - u(s)\rvert}{u(s)} \le 0.25,\qquad
\rho_S = \operatorname{Spearman}(\hat u, u)\big|_{u\ge5} \ge 0.7,$$
$$\left\lvert \frac{Q_{50}(\hat u)}{Q_{50}(u)} - 1\right\rvert \le 0.10 \ \text{and}\ \left\lvert \frac{Q_{95}(\hat u)}{Q_{95}(u)} - 1\right\rvert \le 0.10
\ \text{on clean IMU-locomoting seconds},$$
$Q_q$ = $q$-th percentile, IMU-locomoting = the pilot's state 3 (VeDBA$_{1s}$ ≥ 3.93 m/s², 4–7 Hz stride-band fraction ≥ 0.10,
not still). **Text:** all three → "valid at the 3-s scale" ($u = u_3$); the same rule with $u_1$ → "valid at the 1-s scale".
MdARE is the typical relative error of the proxy for moving seconds (0 = perfect); $\rho_S$ its rank agreement (1 =
perfect order); the quantile conditions demand an unbiased speed distribution while locomoting. Point estimates decide.

### Track speed and R1 bias
For a track $\mathbf p_i$ (positions at the fix times) the speeds $v_3(s)$, $v_1(s)$ use the same medians as $u_3$, $u_1$
(on $\mathbf p_i$ instead of $\mathbf z_i$). On a set $\mathcal C$ of clean seconds:
$$d_{q} = \frac{Q_q\{v(s)\}_{s\in\mathcal C}}{Q_q\{u(s)\}_{s\in\mathcal C}} - 1\ (q = 50, 95),\qquad \mathrm{MAE} = \operatorname{median}_{s\in\mathcal C}\lvert v(s) - u(s)\rvert .$$
**Text:** $d_q < 0$ = the track's speed distribution is slower than the clean reference (under-follows), $> 0$ = faster (adds
noise or overshoot). Units: fraction (reported in %); MAE in in/s. Bands select seconds by the reference speed ($u < 5$,
$5 \le u \le 15$, $u > 15$ in/s); because the band is chosen on the noisy reference, band-wise ratios contain selection
regression (a track that is right on average but does not share the reference's noise still looks slower in the top band and faster in the bottom band).
**Reading:** "closest" = smallest $\max(\lvert d_{50}\rvert, \lvert d_{95}\rvert)$ among the smoothed tracks (raw *is* the
reference on clean seconds, $d_q \equiv 0$); **biased** = the 95 % CI of $d_{50}$ or $d_{95}$ lies entirely beyond ± 10 %.

### R2 (only at a valid scale)
The same ratios with the IMU proxy $\hat u$ as the reference, on all IMU-QC-ok non-still seconds of the six nights (houses,
low anchors, rain included) and on the IMU-locomoting subset, where every track's speed and the proxy are defined.

### Block bootstrap
Blocks $b$ = (animal, night, 10-min block from 21:00). Each replicate draws $K$ blocks with replacement ($K$ = number of
blocks); paired comparisons use the same draw for the track and the reference. Quantiles inside R1/R2 replicates come from
per-block histograms on log-spaced edges (relative bin width ≈ 0.28 %); validity CIs resample the seconds of whole blocks.
CI = 2.5–97.5 % of 1000 replicates (seed in the config).
"""


def render_report(E: dict, out: Path, figs: dict, meta: dict) -> str:
    cfg = E["cfg"]
    VT, R1, R2, rd, FT, CT, mc = E["VT"], E["R1"], E["R2"], E["reading"], E["FT"], E["CT"], E["mc"]
    valid = E["valid"]
    vc = cfg["validity"]
    L = []
    w = L.append
    w(f"# WISER baseline — head-IMU speed reference independent of the smoother (cohort {cfg['_cohort']})\n")
    w(f"**Plan:** [`{PLAN}`](../../../../{PLAN}) (step B of A → B → C, approved by the user 2026-10-03, \"干吧\"; Amendment 1 "
      f"written before any number). **Driver:** `{DRIVER}`. **Config:** `{meta['config']}`. **Run:** `{out}` "
      f"(git {meta['git_commit']}). **Inputs:** failure-audit run `{cfg['audit_run']}`, default-smoother run (V2b), V1b run, "
      f"WISER fix caches, make_imu 50-Hz npz (features cached in `{cfg['feature_cache_root']}`).\n")
    # ---- verdict
    w("## Verdict\n")
    vt = {s: VT[(VT.group == "test") & (VT.scale == s)].iloc[0] for s in SCALES}
    for s in SCALES:
        r = vt[s]
        w(f"- **{s}-s scale: {'VALID' if r.valid else 'NOT VALID'}** ({r.model}) — test night 09-08, clean seconds: MdARE "
          f"{_f(r.mdare)} (≤ {vc['max_mdare']}: {'pass' if r.c_mdare else 'fail'}), Spearman ρ {_f(r.spearman)} (≥ {vc['min_spearman']}: "
          f"{'pass' if r.c_spearman else 'fail'}) on {r.n_big:,} seconds with $u_{s}$ ≥ 5 in/s; IMU-locomoting p50 {_pc(r.d50)} / p95 "
          f"{_pc(r.d95)} (± 10 %: {'pass' if r.c_loco else 'fail'}) on {r.n_loco:,} seconds.")
    r1p = rd.get("R1_u3", {})
    w(f"- **R1 (clean WISER reference, 3-s scale, all six nights): closest = {LABEL.get(r1p.get('least_biased'), r1p.get('least_biased'))}**; "
      f"**biased** (95 % CI of p50 or p95 entirely beyond ± 10 %): {', '.join(LABEL[m] for m in r1p.get('biased', [])) or 'none'}.")
    r11 = rd.get("R1_u1", {})
    w(f"- R1 at the 1-s scale: closest = {LABEL.get(r11.get('least_biased'), r11.get('least_biased'))}; biased: "
      f"{', '.join(LABEL[m] for m in r11.get('biased', [])) or 'none'}.")
    if any(valid.values()):
        for s in SCALES:
            if f"R2_u{s}" in rd:
                w(f"- R2 (vs the IMU proxy, {s}-s, all IMU-ok non-still night seconds): closest = {LABEL.get(rd[f'R2_u{s}']['least_biased'])}.")
    else:
        w("- **R2 not run** — the proxy is not valid at either scale, so it is not used to judge smoothers (pre-registered).")
    w(f"- **Least biased in speed:** {LABEL.get(rd.get('least_biased'), rd.get('least_biased')) or 'not unique'} ({rd.get('least_biased_basis')}). "
      "No default is changed in this step; a least-biased track other than the current default (V1b for the implanted animals, "
      "B2 elsewhere) is a proposal to the user.")
    w(f"- **Ephys deliverable:** {'written to `' + E['deliv']['root'] + '` (' + ', '.join(f'{s} s' for s in E['deliv']['scales']) + ')' if E['deliv'] else 'not written (proxy not valid at either scale)'}.\n")
    # ---- clean seconds + floor
    w("## Clean seconds and the noise floor\n")
    g = CT.groupby(["period", "role", "set"]).sum(numeric_only=True).reset_index()
    order = nights(cfg)
    g["o"] = g["period"].map({p: i for i, p in enumerate(order)})
    g = g.sort_values("o")
    w("| night | role | seconds | IMU ok | fix conditions ok | medians outside houses | clean ($u_3$) | clean ($u_1$) | clean & IMU-locomoting | clean & $u_3$ ≥ 5 |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for r in g.itertuples():
        w(f"| {r.period[6:]} | {r.role} ({r.set}) | {r.n_sec:,} | {r.imu_ok:,} | {r.fix_ok:,} | {r.outside:,} | **{r.clean:,}** | {r.clean_u1:,} | "
          f"{r.clean_loco:,} | {r.clean_ge5:,} |")
    tot = CT.sum(numeric_only=True)
    w(f"| **all** | | {tot.n_sec:,} | {tot.imu_ok:,} | {tot.fix_ok:,} | {tot.outside:,} | **{tot.clean:,}** | {tot.clean_u1:,} | {tot.clean_loco:,} | {tot.clean_ge5:,} |\n")
    w(f"Per animal (all nights): " + ", ".join(f"{a} {int(v):,}" for a, v in CT.groupby('animal').clean.sum().items()) + " clean seconds. "
      f"Why seconds fail the fix conditions (a second can fail several; all nights): rate < 3 Hz {int(tot.fail_rate):,}, an anchor count < 8 "
      f"{int(tot.fail_anch):,}, an invalid fix {int(tot.fail_invalid):,}, a masked fix {int(tot.fail_mask):,}, a jump {int(tot.fail_jump):,}.\n")
    w("**Noise floor** (the same estimators on certified still segments, ≥ 8 anchors, true speed 0):\n")
    w("| periods | scale | seconds | segments | mean | p50 | p90 | p95 | p99 | share ≥ 5 in/s |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for r in FT.itertuples():
        w(f"| {r.kind} {r.set} | {r.scale} s | {r.n_sec:,} | {r.n_segments:,} | {_f(r.mean)} | {_f(r.p50)} | {_f(r.p90)} | {_f(r.p95)} | {_f(r.p99)} | {_pc(r.frac_ge5, 2, False)} |")
    w("")
    w(f"![noise floor](../figures/{figs['floor']})\n")
    # ---- models
    w("## Models and the tuning night\n")
    w("| scale | n train | n tune | MAE tune M1 (in/s) | MAE tune M2 (in/s) | M2 best grid point | M1 coverage (tune) | MAE train M1 / M2 | chosen |")
    w("|---|---|---|---|---|---|---|---|---|")
    for r in mc.itertuples():
        mb = r.m2_best if isinstance(r.m2_best, str) else json.dumps(r.m2_best)
        w(f"| {r.scale} s | {r.n_train:,} | {r.n_tune:,} | {_f(r.mae_tune_M1, 3)} | {_f(r.mae_tune_M2, 3)} | {mb} | {_f(r.m1_tune_coverage, 4)} | "
          f"{_f(r.mae_train_M1, 3)} / {_f(r.mae_train_M2, 3)} | **{r.choice}** |")
    w("")
    coef = E["coef"]
    w("M1 coefficients (per animal; intercept, VeDBA mean [in/s per m/s²], stride-band power [in/s per (m/s²)²], stride peak "
      "frequency [in/s per Hz], |ω| mean [in/s per deg/s]):\n")
    cc = [c for c in coef.columns if c.startswith("b_")]
    w("| scale | animal | n train | " + " | ".join(c[2:] for c in cc) + " |")
    w("|---|---|---|" + "---|" * len(cc))
    for r in coef.itertuples():
        w(f"| {r.scale} s | {r.animal} | {r.n_train:,} | " + " | ".join(_f(getattr(r, c), 4) for c in cc) + " |")
    w("")
    grid = E["grid"]
    w("M2 grid (tuning-night MAE on all clean tuning seconds, in/s): " + "; ".join(
        f"{r.scale} s lr {r.learning_rate} depth {r.max_depth} leaf {r.min_samples_leaf} → {_f(r.mae_tune, 3)}" for r in grid.itertuples()) + ".\n")
    # ---- validity
    w("## Validity (test night 09-08) and robustness\n")
    w("| nights | scale | model | n (u ≥ 5) | MdARE [CI] | Spearman ρ [CI] | n loco | loco p50 Δ [CI] | loco p95 Δ [CI] | valid by the rule |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    gname = {"test": "**TEST 09-08**", "tune": "tune 09-07 (in-sample choice)", "train": "train 09-05/06 (in-sample)", "rain_0903": "rain 09-03",
             "rain_0909": "rain 09-09", "rain_both": "rain both"}
    for gk in ("test", "rain_0903", "rain_0909", "rain_both", "tune", "train"):
        for s in SCALES:
            r = VT[(VT.group == gk) & (VT.scale == s)].iloc[0]
            w(f"| {gname[gk]} | {s} s | {r.model} | {int(r.n_big):,} | {_f(r.mdare)} [{_f(r.mdare_lo)}, {_f(r.mdare_hi)}] | {_f(r.spearman)} "
              f"[{_f(r.spearman_lo)}, {_f(r.spearman_hi)}] | {int(r.n_loco):,} | {_ci(r, 'd50')} | {_ci(r, 'd95')} | "
              f"{'yes' if r.valid else 'no'}{' (decides)' if gk == 'test' else ' (reported)'} |")
    w("")
    VA = E["VA"]
    w("Test night per animal (reported): " + "; ".join(
        f"{r.animal} {r.scale} s MdARE {_f(r.mdare)}, ρ {_f(r.spearman)}, loco p50 {_pc(r.d50, 0)} / p95 {_pc(r.d95, 0)}" for r in VA.itertuples()) + ".\n")
    w(f"![test night](../figures/{figs['test']})\n")
    # ---- R1
    w("## R1 — every track against the clean WISER reference\n")
    w("On clean seconds (open field, ≥ 8 anchors, no jumps, IMU-ok), each track's speed by the same median estimator vs $u$. "
      "`raw` is the reference itself (identity check: Δ = 0 by construction). Point estimate [95 % CI], paired 10-min block bootstrap.\n")
    for s in SCALES:
        for st in SETS:
            c = R1[(R1.scale == s) & (R1.set == st) & (R1.band == "all")]
            if not len(c):
                continue
            r0 = c.iloc[0]
            w(f"**{s}-s scale, {st} nights** — {int(r0.n_sec):,} clean seconds, {int(r0.n_blocks)} blocks; reference p50 {_f(r0.p50_ref)} / p95 "
              f"{_f(r0.p95_ref)} in/s.\n")
            w("| track | p50 (in/s) | p50 Δ [CI] | p95 (in/s) | p95 Δ [CI] | MAE vs u (in/s) [CI] | biased |")
            w("|---|---|---|---|---|---|---|")
            for m in TRACKS:
                rr = c[c.track == m]
                if not len(rr):
                    continue
                r = rr.iloc[0]
                w(f"| {LABEL[m]} | {_f(r.p50)} | {_ci(r, 'd50')} | {_f(r.p95)} | {_ci(r, 'd95')} | {_f(r.mae)} [{_f(r.mae_lo)}, {_f(r.mae_hi)}] | "
                  f"{'—' if m == 'raw' else ('**yes**' if r.biased else 'no')} |")
            w("")
    w("**By reference speed band** (all nights; p50 Δ / p95 Δ / MAE; band selection on the noisy reference biases ratios toward "
      "'slower' in the top band and 'faster' in the bottom band for tracks that do not share the reference's noise; noise removal pushes every smoother 'slower' in the bottom band):\n")
    for s in SCALES:
        w(f"| {s}-s | " + " | ".join(f"{BAND_LABEL[b]} in/s" for b in BANDS[1:]) + " |")
        w("|---|" + "---|" * 3)
        for m in TRACKS:
            cells = []
            for b in BANDS[1:]:
                rr = R1[(R1.scale == s) & (R1.set == "all") & (R1.band == b) & (R1.track == m)]
                cells.append("–" if not len(rr) else f"{_pc(rr.iloc[0].d50, 0)} [{_pc(rr.iloc[0].d50_lo, 0)}, {_pc(rr.iloc[0].d50_hi, 0)}] / "
                             f"{_pc(rr.iloc[0].d95, 0)} / {_f(rr.iloc[0].mae, 2)} (n {int(rr.iloc[0].n_sec):,})")
            w(f"| {LABEL[m]} | " + " | ".join(cells) + " |")
        w("")
    w(f"![R1](../figures/{figs['r1']})\n")
    # ---- R2
    w("## R2 — every track against the IMU proxy\n")
    if R2 is not None and len(R2):
        for s in sorted(R2.scale.unique(), reverse=True):
            for st in SETS:
                for sub in ("nonstill", "loco"):
                    c = R2[(R2.scale == s) & (R2.set == st) & (R2.subset == sub)]
                    if not len(c):
                        continue
                    r0 = c.iloc[0]
                    w(f"**{s}-s, {st} nights, {'IMU-ok non-still' if sub == 'nonstill' else 'IMU-locomoting'} seconds** — {int(r0.n_sec):,} s, proxy p50 "
                      f"{_f(r0.p50_ref)} / p95 {_f(r0.p95_ref)} in/s.\n")
                    w("| track | p50 | p50 Δ [CI] | p95 | p95 Δ [CI] |")
                    w("|---|---|---|---|---|")
                    for m in TRACKS:
                        r = c[c.track == m].iloc[0]
                        w(f"| {LABEL[m]} | {_f(r.p50)} | {_ci(r, 'd50')} | {_f(r.p95)} | {_ci(r, 'd95')} |")
                    w("")
        if "r2" in figs:
            w(f"![R2](../figures/{figs['r2']})\n")
    else:
        w("Not run: the proxy failed the pre-registered validity rule at both scales, so it is reported as not valid and is "
          "**not** used to judge smoothers.\n")
    # ---- reading
    w("## Reading (pre-registered)\n")
    for k in ("R1_u3", "R1_u1", "R2_u3", "R2_u1"):
        if k in rd:
            v = rd[k]
            w(f"- {k.replace('_u', ', ')}-s: order by max(|Δp50|, |Δp95|) = {' < '.join(LABEL[m].split(' ')[0] for m in v['order'])}; closest "
              f"**{LABEL[v['least_biased']]}** ({_pc(v['dist'], 1, False)})" + (f"; biased: {', '.join(LABEL[m] for m in v['biased']) or 'none'}" if 'biased' in v else "") + ".")
    w(f"- **Least biased in speed: {LABEL.get(rd.get('least_biased'), rd.get('least_biased')) or 'not unique'}** — {rd.get('least_biased_basis')}.")
    w("- No default is changed in this step (plan). The current defaults: V1b for the implanted animals where the IMU QC passes, "
      "B2 elsewhere (V1b = B2 in motion, step A).\n")
    # ---- reading aid written after the results (numbers from the same tables; no verdict changed)
    D = E["D"]

    def r1v(s, b, m, col):
        rr = R1[(R1.scale == s) & (R1.set == "all") & (R1.band == b) & (R1.track == m)]
        return float(rr.iloc[0][col]) if len(rr) else np.nan
    fp = {s: float(FT[(FT.kind == "all") & (FT.scale == s)].p95.iloc[0]) for s in SCALES}
    clu = {s: D.loc[D["clean"], f"u{s}"].dropna().to_numpy(float) for s in SCALES}
    w("## Note made after the results (2026-10-03; reading aid only, no verdict changed)\n")
    w(f"- **Why every smoothed track is 'biased' in the primary cell.** The cell is decided by p50, and on clean seconds the reference "
      f"p50 is {_f(r1v(3, 'all', 'raw', 'p50_ref'))} in/s at 3 s — about the noise floor's p95 ({_f(fp[3])} in/s): "
      f"{_pc((clu[3] <= fp[3]).mean(), 0, False)} of the clean seconds are at or below the floor p95 and {_pc((clu[3] < 5).mean(), 0, False)} "
      f"below 5 in/s (most clean open-field seconds are slow). There $u_3$ is largely the fixes' own noise, which every smoother "
      f"removes by design, so a negative p50 Δ mixes noise removal with under-following; the p50 cell cannot separate them. At 1 s the "
      f"reference p50 ({_f(r1v(1, 'all', 'raw', 'p50_ref'))} in/s) is below the floor p95 ({_f(fp[1])} in/s), so the 1-s cells are dominated by noise. "
      "The pre-registered labels stand as computed.")
    w("- **Where the reference is above its floor** — the p95 of all clean seconds and the 5–15 / > 15 in/s bands (band ratios carry "
      "selection regression for tracks that do not share the reference's noise; at 3 s the floor p50 is ≈ 0.6 in/s, so the effect is "
      "small at > 15 in/s and large at 1 s):\n")
    w("| track | 3-s p95 Δ (all clean) | 3-s 5–15 p50 Δ | 3-s > 15 p50 Δ | 3-s > 15 p95 Δ | 1-s p95 Δ (all clean) | 1-s > 15 p50 Δ | 1-s > 15 p95 Δ |")
    w("|---|---|---|---|---|---|---|---|")
    for m in SMOOTHED:
        w(f"| {LABEL[m]} | {_pc(r1v(3, 'all', m, 'd95'))} | {_pc(r1v(3, '5to15', m, 'd50'))} | {_pc(r1v(3, 'gt15', m, 'd50'))} | "
          f"{_pc(r1v(3, 'gt15', m, 'd95'))} | {_pc(r1v(1, 'all', m, 'd95'))} | {_pc(r1v(1, 'gt15', m, 'd50'))} | {_pc(r1v(1, 'gt15', m, 'd95'))} |")
    w("")
    w(f"  Read this way: B2 and V1b (identical in motion) run {_pc(-r1v(3, 'all', 'B2', 'd95'), 0, False)} slow at the 3-s p95 and "
      f"{_pc(-r1v(3, 'gt15', 'B2', 'd95'), 0, False)} slow at the p95 of the > 15 in/s band, and {_pc(-r1v(1, 'gt15', 'B2', 'd50'), 0, False)} slow at the "
      f"1-s p50 above 15 in/s (part of the 1-s figure is selection regression on the noisy 1-s reference) — consistent with the "
      f"constant-velocity q (3 in²/s³) under-following fast bursts, as the NIS of 8–10 in runs suggested. "
      f"V2b (IMU-switched q on B2) follows fast movement best among the Kalman tracks ({_pc(r1v(3, 'gt15', 'V2b', 'd95'))} / "
      f"{_pc(r1v(1, 'gt15', 'V2b', 'd50'))}); B2′ and V1 (drift state) are the slowest ({_pc(r1v(3, 'gt15', 'B2p', 'd95'))} at the 3-s > 15 p95).")
    w(f"- **B1 is closest partly by construction:** it is a running median of the raw fixes, like the reference, so it shares the "
      f"reference's noise and jumps (MAE vs $u_3$ {_f(r1v(3, 'all', 'B1', 'mae'))} in/s, vs ≈ {_f(r1v(3, 'all', 'B2', 'mae'))} for B2). B1 was "
      "eliminated in the default-smoother step (S1–S4: jumps, ≈ 107 in/min of fake path in calm stillness). The pre-registered reading "
      "names it least biased in speed; that is reported, and it is not a recommendation to use B1.")
    vt3 = VT[(VT.group == "test") & (VT.scale == 3)].iloc[0]
    w(f"- **The 3-s proxy misses one condition:** MdARE {_f(vt3.mdare, 3)} against ≤ {vc['max_mdare']} (CI {_f(vt3.mdare_lo, 3)}–"
      f"{_f(vt3.mdare_hi, 3)}); ρ and the locomoting quantiles pass. The point estimate decides (pre-registered), so the proxy is not "
      "valid and is not used for R2 or ephys. On the rain nights it is clearly worse (MdARE ≈ 0.35, locomoting p50 −15 to −26 %).\n")
    # ---- reproduction
    rp = E["repro"]
    w("## Checks\n")
    if rp:
        w(f"- Audit `imu_seconds` reproduced from the npz on all {rp['n_animal_nights']} animal-nights: ok agreement ≥ {_pc(rp['ok_agree_min'], 3, False)}, "
          f"still ≥ {_pc(rp['still_agree_min'], 3, False)}, state ≥ {_pc(rp['state_agree_min'], 3, False)}; max |ΔVeDBA₁ₛ| {rp['vedba_maxdiff']:.2e} m/s², "
          f"max |ΔSBF| {rp['sbf_maxdiff']:.2e}.")
        w(f"- Reference from the float64 fix cache vs the audit's float32 raw track on clean seconds: max |Δu₃| {rp['raw32_vs_u3_max']:.2e}, "
          f"max |Δu₁| {rp['raw32_vs_u1_max']:.2e} in/s. Track files matched the fix cache fix by fix (t_ms) for all tracks.")
        w(f"- Feature cache: {rp.get('feature_cache')}.")
    w("- Selftest (`--selftest`, synthetic): clean filter = an independent loop implementation and excludes every planted defect; "
      "$u_3$ recovers the planted walking speeds within the floor; M1 recovers planted coefficients; features recover a planted "
      "stride frequency / power; the validity rule passes a good and fails two bad proxies; R1 flags a ×0.85 speed-damped track.\n")
    # ---- caveats
    w("## Caveats\n")
    w("- The clean filter selects good conditions (open field, ≥ 8 anchors): R1 says nothing about speed under poor anchors, in "
      "the houses or in heavy rain. The noise floor comes from still segments in the houses.")
    w("- The proxy is calibrated on open-field clean seconds; where it is applied in the houses / rain (R2, deliverable) its "
      "validity is assumed, not shown (more in-place activity there).")
    w("- Head speed ≠ body speed: head scanning adds path; the 3-s scale partly averages it out. The IMU-locomoting class was "
      "itself fitted against WISER speed. Median-window estimators smooth the fastest bursts at both scales, for the reference "
      "and the tracks alike.")
    w("- The WISER frame is an unverified offset frame; speeds are frame-invariant (rotation/offset) but not scale-verified.\n")
    w("## Amendments\n")
    w("Amendment 1 of the plan (operational details) was written before any number of this step; the models were frozen (fit stage, "
      "12:11) before any test-night or rain-night number was computed (evaluate stage, 12:12). Note 2 (after the results): the "
      "reading-aid section above and the figure layout; no definition, threshold, verdict or label changed. Both are listed in the plan.\n")
    w(DEFINITIONS)
    return "\n".join(L) + "\n"


def publish(E: dict, out: Path, fh=None) -> None:
    import shutil
    cfg = E["cfg"]
    cohort = cfg["_cohort"]
    fdir = output_paths.figure_dir(cohort, DIRECTION)
    figs = make_figures(E, fdir)
    (out / "figures").mkdir(exist_ok=True)
    for f in figs.values():
        shutil.copy2(fdir / f, out / "figures" / f)
    rdir = output_paths.report_dir(cohort, DIRECTION)
    rep = rdir / f"{STEM}_{cohort}.md"
    rd = E["reading"]
    meta = {"cohort": cohort, "direction": DIRECTION, "analysis": NAME, "report": rep.name, "driver": DRIVER,
            "config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "plan": PLAN, "git_commit": C.git_commit(), "figures": sorted(figs.values()),
            "audit_run": cfg["audit_run"], "valid_3s": E["valid"][3], "valid_1s": E["valid"][1],
            "models": {f"u{s}": E["models"][s]["choice"] for s in SCALES}, "least_biased": rd.get("least_biased"),
            "biased_R1_3s": rd.get("R1_u3", {}).get("biased", []), "deliverable": E["deliv"]["root"] if E["deliv"] else None}
    rep.write_text(render_report(E, out, figs, meta), encoding="utf-8")
    output_paths.write_run_manifest(out, out, **meta)
    mp = rdir / f"run_manifest_imu_speed_proxy_{cohort}.json"
    mp.write_text(json.dumps({"run_dir": str(out.resolve()), **meta}, indent=2) + "\n", encoding="utf-8")
    cp = Path(cfg["_path"])
    cj = json.loads(cp.read_text(encoding="utf-8"))
    vt = E["VT"]
    cj["result"] = {
        "valid": {f"u{s}": E["valid"][s] for s in SCALES},
        "test_night": {f"u{s}": {k: (None if not np.isfinite(float(r[k])) else round(float(r[k]), 4)) for k in ("mdare", "spearman", "d50", "d95")}
                       for s in SCALES for r in [vt[(vt.group == "test") & (vt.scale == s)].iloc[0]]},
        "R1_least_biased_3s": rd.get("R1_u3", {}).get("least_biased"), "R1_biased_3s": rd.get("R1_u3", {}).get("biased", []),
        "R1_least_biased_1s": rd.get("R1_u1", {}).get("least_biased"), "R1_biased_1s": rd.get("R1_u1", {}).get("biased", []),
        "least_biased": rd.get("least_biased"), "basis": rd.get("least_biased_basis"),
        "deliverable": E["deliv"]["root"] if E["deliv"] else None, "run_dir": str(out),
        "report": f"results/{cohort}/wiser_baseline/reports/{rep.name}",
        "decided_local": pd.Timestamp.now(tz=cfg["tz"]).strftime("%Y-%m-%d %H:%M:%S")}
    cp.write_text(json.dumps(cj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log_to(fh, f"report {rep}\nmanifest {mp}\nresult written into {cp.name}")


# ====================================================================================================== selftest
def _synth(seed: int = 11, dur_s: float = 7200.0) -> dict:
    """Synthetic head track: bouts still (25 %), straight walking at 6/10/15/22 in/s (60 %), in-place activity (15 %);
    WISER-like fix times (0.134 / 0.268 s), sigma 2 in per axis, anchors 9; planted defects: anchors 7 on [1500, 1520) s,
    invalid fixes on [1700, 1702) s, a 40-in single-fix jump at ~1900 s, IMU not ok on [2100, 2130) s, a handling mask on
    [2300, 2310) s; a house ROI placed on the path at t = 1000 s."""
    rng = np.random.default_rng(seed)
    T0 = 1.7e9
    dg = 0.01
    g = np.arange(0.0, dur_s + 5.0, dg)
    v = np.zeros((len(g), 2))
    kind = np.zeros(len(g), np.int8)        # 0 still, 1 walk, 2 in place
    speed = np.zeros(len(g))
    bouts = []
    tt, x = 0.0, 100.0
    while tt < dur_s + 5.0:
        r = rng.random()
        if r < 0.25:
            k, d, sp = 0, rng.uniform(20, 60), 0.0
        elif r < 0.85:
            k, d, sp = 1, rng.uniform(15, 40), float(rng.choice([6.0, 10.0, 15.0, 22.0]))
        else:
            k, d, sp = 2, rng.uniform(10, 30), 0.0
        a, b = int(tt / dg), min(int((tt + d) / dg), len(g))
        if k == 1:
            hd = -1.0 if x > 300 else 1.0
            v[a:b, 0] = hd * sp
            x += hd * sp * (b - a) * dg
        kind[a:b] = k
        speed[a:b] = sp
        bouts.append((tt, tt + d, k, sp))
        tt += d
    pos = np.cumsum(v, axis=0) * dg + np.array([100.0, 200.0])
    m_ = int(dur_s / 0.18) + 20
    t = np.cumsum(rng.choice([0.134, 0.268], size=m_, p=[0.45, 0.55]) + rng.normal(0, 0.003, m_))
    t = t[(t > 3.0) & (t < dur_s)]
    truth = np.column_stack([np.interp(t, g, pos[:, 0]), np.interp(t, g, pos[:, 1])])
    z = truth + rng.normal(0, 2.0, truth.shape)
    A = np.full(len(t), 9.0)
    A[(t >= 1500) & (t < 1520)] = 7.0
    valid = np.ones(len(t), bool)
    valid[(t >= 1700) & (t < 1702)] = False
    j = int(np.searchsorted(t, 1900.0))
    z[j, 0] += 40.0
    fmask = (t >= 2300) & (t < 2310)
    secs_rel = np.arange(4, int(dur_s) - 4)
    ok = ~((secs_rel >= 2100) & (secs_rel < 2130))
    hc = np.array([np.interp(1000.0, g, pos[:, 0]), np.interp(1000.0, g, pos[:, 1])])
    house = {"name": "house_1", "shape": "rect", "x": float(hc[0]), "y": float(hc[1]), "width_in": 36.0, "height_in": 27.0, "orientation_deg": 0.0}
    return {"T0": T0, "t": t + T0, "z": z, "truth": truth, "A": A, "valid": valid, "fmask": fmask, "secs": secs_rel + int(T0), "ok": ok,
            "house": house, "g": g + T0, "pos": pos, "kind": kind, "speed": speed, "bouts": [(a + T0, b + T0, k, s) for a, b, k, s in bouts],
            "jump_t": t[j] + T0}


def _clean_loop(S: dict, rc: dict) -> np.ndarray:
    """Independent (slow) implementation of the clean-second rule for the selftest."""
    cc = rc["clean"]
    t, z, A, valid, fmask = S["t"], S["z"], S["A"], S["valid"], S["fmask"]
    d = np.hypot(*np.diff(z, axis=0).T)
    jpair = (d > cc["jump_in"]) & (np.diff(t) <= cc["jump_dt_s"])
    out = np.zeros(len(S["secs"]), bool)
    for k, s in enumerate(S["secs"]):
        c = s + 0.5
        if not S["ok"][k]:
            continue
        ii = np.flatnonzero((t >= c - 2.0) & (t <= c + 2.0))
        if len(ii) < 12 or (A[ii] < 8).any() or (~valid[ii]).any() or fmask[ii].any():
            continue
        lo_, hi_ = ii[0], ii[-1]
        pairs = np.arange(max(lo_ - 1, 0), min(hi_ + 1, len(t) - 1))
        if jpair[pairs].any():
            continue
        meds = []
        for gc in (c - 1.5, c + 1.5):
            w = (t >= gc - 0.5) & (t < gc + 0.5)
            if w.sum() < 3:
                break
            meds.append(np.median(z[w], axis=0))
        if len(meds) < 2:
            continue
        if any(in_house(np.array([mm[0]]), np.array([mm[1]]), [S["house"]], cc["house_buffer_in"])[0] for mm in meds):
            continue
        out[k] = True
    return out


def selftest() -> int:
    fails = []

    def check(name, cond, info=""):
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}")
        if not cond:
            fails.append(name)
    cfg = json.loads((REPO / "wiser" / "configs" / "imu_speed_proxy_2026c.json").read_text(encoding="utf-8"))
    rc, fc = cfg["reference"], cfg["features"]
    S = _synth()
    secs = S["secs"]
    ref = reference(S["t"], S["z"], S["A"], S["valid"], S["fmask"], secs, S["ok"], [S["house"]], rc)
    # ---- 1. clean filter
    loop = _clean_loop(S, rc)
    check("clean filter = independent loop implementation", np.array_equal(loop, ref["clean"]),
          f"(vectorised {int(ref['clean'].sum())}, loop {int(loop.sum())}, mismatches {int((loop != ref['clean']).sum())})")
    c = secs + 0.5
    defects = [(1500, 1520), (1700, 1702), (2300, 2310)]
    hit = np.zeros(len(secs), bool)
    for a, b in defects:
        hit |= (c + 2.0 >= a + S["T0"]) & (c - 2.0 < b + S["T0"])
    check("no clean second touches a planted anchor / invalid / mask defect", not (ref["clean"] & hit).any())
    jt = S["jump_t"]
    check("no clean second spans the planted jump", not (ref["clean"] & (np.abs(c - jt) <= 2.0)).any())
    imu_bad = (secs - S["T0"] >= 2100) & (secs - S["T0"] < 2130)
    check("no clean second in the planted IMU-QC failure", not (ref["clean"] & imu_bad).any())
    hpos = np.array([S["house"]["x"], S["house"]["y"]])
    hx, hy = S["house"]["width_in"] / 2 + 14.0, S["house"]["height_in"] / 2 + 14.0     # axis-aligned house grown by 14 in
    near_h = np.zeros(len(secs), bool)
    for off in (-1.5, 1.5):
        mm, _ = FA.roll_median(S["t"], S["z"], c + off, 0.5, 3)
        near_h |= (np.abs(mm[:, 0] - hpos[0]) <= hx) & (np.abs(mm[:, 1] - hpos[1]) <= hy)
    check("no clean second with a median inside the house buffer", near_h.sum() > 0 and not (ref["clean"] & near_h).any(),
          f"(seconds with a median in the buffer {int(near_h.sum())})")
    far = ~hit & ~imu_bad & (np.abs(c - jt) > 3) & ~(np.hypot(ref["mx"] - hpos[0], ref["my"] - hpos[1]) < 60)
    frac = float(ref["clean"][far].mean())
    check("most seconds away from every defect are clean (>= 0.9)", frac >= 0.9, f"({frac:.3f})")
    # ---- 2. u3 recovers the planted speed within the floor
    walk_rows, still_rows = [], []
    for a, b, k, sp in S["bouts"]:
        m = ref["clean"] & (c - 2.0 >= a) & (c + 2.0 <= b)
        if k == 1:
            walk_rows.append((sp, ref["u3"][m], ref["u1"][m]))
        elif k == 0:
            still_rows.append((ref["u3"][m], ref["u1"][m]))
    fl3 = np.concatenate([x[0] for x in still_rows])
    fl1 = np.concatenate([x[1] for x in still_rows])
    fl1 = fl1[np.isfinite(fl1)]
    p95_3, p95_1 = np.percentile(fl3, 95), np.percentile(fl1, 95)
    for sp in (6.0, 10.0, 15.0, 22.0):
        u = np.concatenate([x[1] for x in walk_rows if x[0] == sp])
        b3 = float(np.median(u) - sp)
        check(f"u3 recovers {sp:.0f} in/s within the floor p95 ({p95_3:.2f} in/s)", abs(b3) <= p95_3, f"(median bias {b3:+.3f}, n {len(u)})")
    # analytical floor: Rayleigh p95 of |difference of two medians of n fixes| / baseline, sigma_med ~ 1.2533 sigma / sqrt(n)
    rate = len(S["t"]) / (S["t"][-1] - S["t"][0])
    exp95 = {k: 2.448 * math.sqrt(2) * 1.2533 * 2.0 / math.sqrt(rate * 2 * h) / (2 * off) for k, (off, h) in {3: (1.5, 0.5), 1: (0.5, 0.375)}.items()}
    check("floor p95 within 1.25 x the analytical Rayleigh bound, u1 noisier than u3",
          p95_3 <= 1.25 * exp95[3] and p95_1 <= 1.25 * exp95[1] and p95_1 > p95_3,
          f"(u3 {p95_3:.2f} vs {exp95[3]:.2f}, u1 {p95_1:.2f} vs {exp95[1]:.2f} in/s)")
    # floor seconds from planted still segments
    segs = np.array([(a, b) for a, b, k, _ in S["bouts"] if k == 0 and b - a >= 30])
    fl, _ = floor_seconds(secs, segs, 1.0, 2.0)
    fo = fl & S["ok"] & ref["fix_ok"] & ref["med_ok"]
    check("floor seconds lie inside planted still bouts", fo.sum() > 50 and float(np.percentile(ref["u3"][fo], 95)) < 1.5,
          f"(n {int(fo.sum())}, p95 {np.percentile(ref['u3'][fo], 95):.2f})")
    # ---- 3. features on a synthetic 50-Hz IMU
    fs = 50.0
    n = int(120 * fs)
    u_ms = 1.7e12 + np.arange(n) * 20.0
    tt = np.arange(n) / fs
    A_, B_, f0 = 2.0, 1.5, 5.0
    lin = np.column_stack([B_ * np.sin(2 * np.pi * 3.0 * tt), np.zeros(n), A_ * np.sin(2 * np.pi * f0 * tt)])
    imu = {"unix_ms": u_ms, "lin_acc_earth_ms2": lin, "vedba_ms2": np.full(n, 2.5), "omega_dps": np.full(n, 50.0),
           "turn_dps": np.full(n, -20.0), "pitch_deg": np.sin(tt)}
    vs = np.ones(n, bool)
    vs[int(60 * fs):int(60.4 * fs)] = False
    ss = np.arange(int(u_ms[0] / 1000) + 2, int(u_ms[-1] / 1000) - 2)
    ft = second_features(imu, vs, ss, fc)
    k_ok = np.isfinite(ft["vpeak_hz_w3"])
    check("features: stride peak frequency recovered (3 s)", np.allclose(ft["vpeak_hz_w3"][k_ok], f0, atol=0.34), f"({np.nanmedian(ft['vpeak_hz_w3']):.2f} Hz)")
    check("features: stride-band power = A^2/2 within 10 % (3 s)", abs(np.nanmedian(ft["vpow_w3"]) / (A_ ** 2 / 2) - 1) < 0.10,
          f"({np.nanmedian(ft['vpow_w3']):.3f} vs {A_ ** 2 / 2:.3f})")
    check("features: stride-band power = A^2/2 within 15 % (1 s)", abs(np.nanmedian(ft["vpow_w1"]) / (A_ ** 2 / 2) - 1) < 0.15,
          f"({np.nanmedian(ft['vpow_w1']):.3f})")
    check("features: stride share > 0.9", np.nanmedian(ft["vshare_w3"]) > 0.9, f"({np.nanmedian(ft['vshare_w3']):.3f})")
    check("features: horizontal RMS = B/sqrt(2) within 10 %", abs(np.nanmedian(ft["hacc_rms_w3"]) / (B_ / np.sqrt(2)) - 1) < 0.10,
          f"({np.nanmedian(ft['hacc_rms_w3']):.3f})")
    check("features: |turn| mean, VeDBA mean exact", np.allclose(np.nanmedian(ft["turn_mean_w1"]), 20.0) and np.allclose(np.nanmedian(ft["vedba_mean_w3"]), 2.5))
    gap_sec = (ss >= int(u_ms[0] / 1000) + 59) & (ss <= int(u_ms[0] / 1000) + 61)
    check("features: a window with 20-40 % invalid samples has no spectral features but keeps time-domain ones",
          bool(np.isnan(ft["vpow_w1"][ss == int(u_ms[0] / 1000) + 60]).all() and np.isfinite(ft["vedba_mean_w1"][gap_sec]).all()))
    # ---- 4. M1 recovers planted coefficients
    rng = np.random.default_rng(5)
    rows = []
    betas = {"SFa": np.array([1.0, 2.0, 0.3, 1.5, 0.02]), "SFb": np.array([-0.5, 1.2, 0.5, 2.5, 0.01])}
    for a, b in betas.items():
        X = np.column_stack([rng.uniform(0.5, 8, 3000), rng.uniform(0, 20, 3000), rng.uniform(2, 8, 3000), rng.uniform(10, 300, 3000)])
        y = b[0] + X @ b[1:] + rng.normal(0, 0.5, 3000)
        bh = m1_fit(X, y)
        rel = np.max(np.abs(bh[1:] - b[1:]) / np.abs(b[1:]))
        check(f"M1 recovers planted coefficients ({a})", rel < 0.05 and abs(bh[0] - b[0]) < 0.5, f"(max rel err {rel:.4f}, intercept {bh[0]:+.3f})")
        rows.append(y)
    # ---- 5. validity rule passes a good proxy, fails bad ones
    vc = cfg["validity"]
    rng = np.random.default_rng(9)
    u = np.r_[rng.gamma(2.0, 4.0, 6000), rng.uniform(0, 1.5, 2000)]
    loco = u > 4.0
    good = u * np.exp(rng.normal(0, 0.12, len(u)))
    bad1 = 0.75 * u
    bad2 = np.maximum(u + rng.normal(0, 12.0, len(u)), 0)
    rg, r1_, r2_ = validity_metrics(u, good, loco, vc), validity_metrics(u, bad1, loco, vc), validity_metrics(u, bad2, loco, vc)
    check("validity rule passes a good proxy", rg["valid"], f"(MdARE {rg['mdare']:.3f}, rho {rg['spearman']:.3f}, d50 {rg['d50']:+.3f}, d95 {rg['d95']:+.3f})")
    check("validity rule fails a x0.75 proxy (quantiles)", not r1_["valid"] and not r1_["c_loco"], f"(d50 {r1_['d50']:+.3f})")
    check("validity rule fails a noisy proxy (MdARE / rho)", not r2_["valid"] and not (r2_["c_mdare"] and r2_["c_spearman"]),
          f"(MdARE {r2_['mdare']:.3f}, rho {r2_['spearman']:.3f})")
    # ---- 6. R1 flags a x0.85 speed-damped track
    rng = np.random.default_rng(13)
    t, truth = S["t"], S["truth"]
    smooth = truth + rng.normal(0, 0.3, truth.shape)
    damped = truth[0] + 0.85 * (truth - truth[0]) + rng.normal(0, 0.3, truth.shape)
    cl = ref["clean"]
    D = pd.DataFrame({"animal": "SFa", "period": "night_x", "block": ((secs - secs[0]) // 600).astype(int)})
    vals = {}
    for nm, pth in (("raw", S["z"]), ("smooth", smooth), ("damped", damped)):
        v3, _ = track_speeds(t, pth, secs, rc)
        vals[nm] = v3
    ok3 = cl & np.all([np.isfinite(v) for v in vals.values()], axis=0) & np.isfinite(ref["u3"])
    rr = ratio_table(D[ok3], ref["u3"][ok3], {k: v[ok3] for k, v in vals.items()}, 300, np.random.default_rng(1), True, {"scale": 3})
    rr = {r["track"]: r for r in rr}
    check("R1: raw track = the reference (identity)", abs(rr["raw"]["d50"]) < 1e-9 and abs(rr["raw"]["d95"]) < 1e-9 and rr["raw"]["mae"] < 1e-9)
    check("R1 flags the x0.85 damped track as biased", biased_flag(rr["damped"], 0.10),
          f"(d50 {rr['damped']['d50']:+.3f} [{rr['damped']['d50_lo']:+.3f}, {rr['damped']['d50_hi']:+.3f}], d95 {rr['damped']['d95']:+.3f} "
          f"[{rr['damped']['d95_lo']:+.3f}, {rr['damped']['d95_hi']:+.3f}])")
    check("R1 does not flag the undamped smooth track", not biased_flag(rr["smooth"], 0.10),
          f"(d50 {rr['smooth']['d50']:+.3f} [{rr['smooth']['d50_lo']:+.3f}, {rr['smooth']['d50_hi']:+.3f}], d95 {rr['smooth']['d95']:+.3f})")
    # ---- 7. M2 path runs on a toy problem (no field data)
    from sklearn.ensemble import HistGradientBoostingRegressor
    Xt = np.column_stack([rng.uniform(0, 10, 2000), rng.uniform(0, 1, 2000)])
    yt = 2 * Xt[:, 0] + rng.normal(0, 0.5, 2000)
    est = HistGradientBoostingRegressor(loss="absolute_error", learning_rate=0.1, max_depth=3, min_samples_leaf=50, random_state=0).fit(Xt, yt)
    check("M2 (absolute-error HGB) fits a toy law", float(np.median(np.abs(est.predict(Xt) - yt))) < 1.0)
    print(f"\nselftest: {'ALL PASS' if not fails else str(len(fails)) + ' FAIL: ' + ', '.join(fails)}")
    return 0 if not fails else 1


# ====================================================================================================== main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--stage", choices=["all", "compute", "fit", "evaluate"], default="all")
    ap.add_argument("--run", default=None, help="existing run dir for --stage fit / evaluate")
    ap.add_argument("--rebuild-features", action="store_true")
    ap.add_argument("--report-only", default=None, help="re-evaluate and re-render an existing run (no compute, no refit)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if a.report_only:
        out = Path(a.report_only)
        man = json.loads((out / "input_provenance.json").read_text(encoding="utf-8"))
        cohort = a.cohort or Path(out).parent.name
        cfg = load_cfg(cohort, a.config or str(REPO / man["config"]))
        fh = open(out / "log_report.txt", "a", encoding="utf-8")
        E = run_evaluate(out, cfg, fh)
        publish(E, out, fh)
        fh.close()
        return
    cohort = output_paths.resolve_cohort(a.cohort)
    cfg = load_cfg(cohort, a.config)
    workers = a.workers or int(cfg.get("workers", 16))
    if a.stage in ("all", "compute"):
        out = run_compute(cfg, workers, a.rebuild_features)
    else:
        if not a.run:
            raise SystemExit("--run <dir> is required for --stage fit / evaluate")
        out = Path(a.run)
    if a.stage == "compute":
        return
    fh = open(out / "log.txt", "a", encoding="utf-8")
    if a.stage in ("all", "fit"):
        run_fit(out, cfg, fh)
    if a.stage in ("all", "evaluate"):
        E = run_evaluate(out, cfg, fh)
        publish(E, out, fh)
    fh.close()


if __name__ == "__main__":
    main()
