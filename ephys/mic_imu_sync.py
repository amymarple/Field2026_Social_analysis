r"""In-house microphones <-> head IMU: who made the sound, and the mic clock (plan
implementation_plan/2026-10-08-mic-imu-sync.md; definitions there, repeated in the report).

    python ephys/mic_imu_sync.py pilot [--raw F:/3rd_rat] [--hours-per-mic 6]
    python ephys/mic_imu_sync.py peaks [--raw F:/3rd_rat]      # Amendment 1: mic peaks -> IMU, before the morning round
    python ephys/mic_imu_sync.py --selftest

Mic envelope: 20-ms frames of the WAV, exactly as ephys/mic_band_levels.py (Hann, mean removed, full-scale sine = 0 dB,
all-zero frames missing), frame centres on the PC clock by the file's timing model (stretched / end-anchored), put on a
50-Hz PC grid by nearest centre. IMU: log10(VeDBA + 0.01) at 50 Hz from make_imu (t_pc_ms), invalid samples missing.
Both detrended by their 2-s running median. Cross-correlation r(l) = Pearson(m(t), v(t + l)), l in [-2, +2] s; peak lag
> 0 = the IMU sees the event later than the mic's own time stamp, i.e. the mic timeline runs ahead by that much.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from mic_band_levels import ANOMALY, BANDS, CLOCK_RATIO, FRAME_S, NAME_RE, load_samples, parse_name  # noqa: E402

FS = 50
LAG_S = 2.0
NULL_SHIFTS_S = np.linspace(30, 90, 20)
MED_S = 2.0
IMU = Path("D:/3rd_rat_spikes/analysis/imu")
OUT = Path("D:/Field2026_analysis_out/2026c")
HOUSE_MIC = {"house_1": "MIC02", "house_2": "MIC01"}
ANIMALS = ["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"]
CUTOFF = pd.Timestamp("2026-09-11 19:40")


# ------------------------------------------------------------------ signals
def frame_envelope(p: Path, t_from: float | None = None, t_to: float | None = None) -> tuple[pd.Timestamp, np.ndarray, np.ndarray, dict]:
    """Per 20-ms frame: centre time (s after the file-name start, PC clock, by the file's timing model) and band power
    in dB (frames x bands, NaN for all-zero frames). Same frames and timing model as mic_band_levels.band_levels.
    t_from / t_to (s after the file-name start) restrict the frames computed (only that part of the file is read)."""
    mic, start, end = parse_name(p)
    x, rate = load_samples(p)
    n = len(x)
    span = (end - start).total_seconds() if end is not None else n / rate
    rate_eff, t_first, timing = n / span, 0.0, "stretched"
    if end is not None and abs(rate_eff / rate - 1) > ANOMALY:
        timing = "end_anchored"
        rate_eff = rate * CLOCK_RATIO.get(mic, 1.0)
        t_first = span - n / rate_eff
    L = int(round(FRAME_S * rate))
    win = np.hanning(L).astype(np.float32)
    freqs = np.fft.rfftfreq(L, 1.0 / rate)
    sel = [(f >= lo) & (f < hi) for f in [freqs] for _, lo, hi in BANDS]
    norm = 32768.0 ** 2 * L * float((win.astype(np.float64) ** 2).sum()) / 4
    nf = n // L
    fa = 0 if t_from is None else int(np.clip(np.floor((t_from - t_first) * rate_eff / L), 0, nf))
    fb = nf if t_to is None else int(np.clip(np.ceil((t_to - t_first) * rate_eff / L) + 1, 0, nf))
    out = np.full((fb - fa, len(BANDS)), np.nan, np.float32)
    step = 3000
    for f0 in range(fa, fb, step):
        f1 = min(fb, f0 + step)
        seg = np.asarray(x[f0 * L:f1 * L], dtype=np.float32).reshape(f1 - f0, L)
        nz = np.any(seg != 0, axis=1)
        seg -= seg.mean(axis=1, keepdims=True)
        P = np.abs(np.fft.rfft(seg * win, axis=1)) ** 2 / norm
        pb = np.stack([P[:, s].sum(axis=1) for s in sel], axis=1)
        with np.errstate(divide="ignore"):
            out[f0 - fa:f1 - fa] = np.where(nz[:, None], 10 * np.log10(pb + 1e-20), np.nan)
    centre = t_first + (np.arange(fa, fb) + 0.5) * L / rate_eff
    return start, centre, out, {"file": p.name, "timing": timing, "rate_eff": rate_eff, "t_first_s": t_first, "span_s": span}


def to_grid(t0: pd.Timestamp, n: int, src_t: np.ndarray, src_v: np.ndarray, tol: float = 0.011) -> np.ndarray:
    """Values at grid times t0 + k/FS (s, relative to t0 = src_t's origin) by nearest source sample within tol."""
    g = np.arange(n) / FS
    k = np.clip(np.searchsorted(src_t, g), 1, len(src_t) - 1)
    k = np.where(np.abs(src_t[k - 1] - g) < np.abs(src_t[k] - g), k - 1, k)
    ok = np.abs(src_t[k] - g) <= tol
    out = np.full((n,) + src_v.shape[1:], np.nan, np.float32)
    out[ok] = src_v[k[ok]]
    return out


def imu_grid(an: str, t0: pd.Timestamp, n: int) -> np.ndarray:
    """log10(VeDBA + 0.01) of `an` on the grid t0 + k/FS (NaN = no valid sample)."""
    out = np.full(n, np.nan, np.float32)
    t1 = t0 + pd.Timedelta(seconds=n / FS)
    for jf in sorted((IMU / an).glob("*.imu.json")):
        j = json.loads(jf.read_text())
        s0 = pd.Timestamp(j["start_local"])
        if s0 >= t1 or s0 + pd.Timedelta(seconds=j["duration_s"]) <= t0:
            continue
        with np.load(jf.with_name(jf.name.replace(".imu.json", ".imu.npz"))) as z:
            if "t_pc_ms" not in z.files:
                continue
            tp, v = z["t_pc_ms"], z["vedba_ms2"]
            bad = z["unreliable"] | z["frozen"] | z["invalid"]
        rel = (s0.normalize() - t0).total_seconds() + tp / 1000.0
        keep = (rel > -1) & (rel < n / FS + 1)
        if not keep.any():
            continue
        vv = np.where(bad[keep], np.nan, np.log10(v[keep].astype(np.float64) + 0.01))
        g = to_grid(t0, n, rel[keep], vv)
        out = np.where(np.isfinite(g), g, out)
    return out


def detrend(x: np.ndarray) -> np.ndarray:
    s = pd.Series(x)
    return (s - s.rolling(int(MED_S * FS) + 1, center=True, min_periods=int(MED_S * FS / 2)).median()).to_numpy(np.float64)


def xcorr(m: np.ndarray, v: np.ndarray, mask: np.ndarray, max_lag: int) -> np.ndarray:
    """Pearson r(l) of m(t) with v(t + l) over t in mask with both finite, l = -max_lag..max_lag samples."""
    n = len(m)
    r = np.full(2 * max_lag + 1, np.nan)
    for i, L in enumerate(range(-max_lag, max_lag + 1)):
        a0, a1 = max(0, -L), min(n, n - L)
        a, b, mk = m[a0:a1], v[a0 + L:a1 + L], mask[a0:a1]
        ok = mk & np.isfinite(a) & np.isfinite(b)
        if ok.sum() < 500:
            continue
        x, y = a[ok] - a[ok].mean(), b[ok] - b[ok].mean()
        d = np.sqrt((x * x).sum() * (y * y).sum())
        r[i] = (x * y).sum() / d if d > 0 else np.nan
    return r


def onsets(v_lin: np.ndarray, th: float) -> np.ndarray:
    """Phase-6 rule on the grid: first sample >= th after >= 1 s below (v_lin = VeDBA, NaN treated as below)."""
    above = np.nan_to_num(v_lin, nan=0.0) >= th
    cs = np.r_[0, np.cumsum(above)]
    k = np.flatnonzero(above)
    k = k[k >= FS]
    return k[(cs[k] - cs[k - FS]) == 0]


# ------------------------------------------------------------------ pilot
def choose_hours(raw: Path, zone: dict, per_mic: int) -> pd.DataFrame:
    """Per mic: the 3 dates (08-31..09-10) with the most rat-seconds in its house (IMU sessions present), and on each the
    best day hour (08-18 h) and the best night hour (20-05 h) by the same count. Occupancy only - no correlation."""
    spans = {}
    for an in ANIMALS:
        s = []
        for jf in sorted((IMU / an).glob("*.imu.json")):
            j = json.loads(jf.read_text())
            s0 = pd.Timestamp(j["start_local"])
            s.append((s0, s0 + pd.Timedelta(seconds=j["duration_s"])))
        spans[an] = s
    rows = []
    for house, mic in HOUSE_MIC.items():
        for d in pd.date_range("2026-08-31", "2026-09-10"):
            for f in sorted((raw / f"{d:%Y-%m-%d}" / mic).glob(f"{mic}_*.wav")):
                if not NAME_RE.search(f.name):
                    continue
                _, s, e = parse_name(f)
                if e is None or (e - s).total_seconds() < 3000 or e > CUTOFF:
                    continue
                secs = pd.date_range(s, e, freq="1s", inclusive="left")
                tot = 0
                for an in ANIMALS:
                    z = zone[an]
                    if not len(z):
                        continue
                    inh = z.reindex(secs).eq(house).to_numpy()
                    cov = np.zeros(len(secs), bool)
                    for a0, a1 in spans[an]:
                        cov |= (secs >= a0) & (secs < a1)
                    tot += int((inh & cov).sum())
                h = s.hour
                part = "day" if 8 <= h <= 18 else ("night" if (h >= 20 or h <= 5) else "")
                if part:
                    nd = (s - pd.Timedelta(hours=6)).normalize()          # a night belongs to the evening's date
                    rows.append({"mic": mic, "house": house, "file": str(f), "start": s, "end": e, "part": part,
                                 "date": nd if part == "night" else s.normalize(), "rat_seconds": tot})
    H = pd.DataFrame(rows)
    pick = []
    for mic, g in H.groupby("mic"):
        best = g.sort_values("rat_seconds", ascending=False).groupby(["date", "part"]).head(1)
        dd = best.pivot_table(index="date", columns="part", values="rat_seconds", aggfunc="max").dropna()
        dates = dd.sum(axis=1).sort_values(ascending=False).index[: per_mic // 2]
        pick.append(best[best.date.isin(dates)])
    return pd.concat(pick).sort_values(["mic", "start"]).reset_index(drop=True)


def pilot(a) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
    from _common import git_commit, write_json
    from mic_wake_pilot import ROOT, load_zone
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_quant import md_table, save_fig
    out = run_dir("mic_imu_sync_pilot", "2026c")
    rd, fd = report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes")
    gc = git_commit()
    raw = Path(a.raw)
    rois = {r["name"]: r for r in json.load(open(ROOT / "wiser/configs/wiser_rois.json"))["rois"] if r["name"] in ("house_1", "house_2")}
    dates = [d.strftime("%Y%m%d") for d in pd.date_range("2026-08-30", "2026-09-11")]
    zone = {an: load_zone(an, dates, rois) for an in ANIMALS}
    th = json.load(open(sorted(OUT.glob("sleep_events_2026*/thresholds.json"))[-1]))["theta_vedba_ms2"]
    hours = choose_hours(raw, zone, a.hours_per_mic)
    hours.to_csv(out / "hours.csv", index=False)
    print(hours[["mic", "start", "part", "rat_seconds"]].to_string(), flush=True)
    ml = int(LAG_S * FS)
    lags = np.arange(-ml, ml + 1) / FS
    pr, offs, drift, attr = [], [], [], []
    curves = {}
    rng = np.random.default_rng(8)
    for hrow in hours.itertuples():
        f = Path(hrow.file)
        start, centre, env, info = frame_envelope(f)
        n = int(info["span_s"] * FS)
        M = {b[0]: detrend(to_grid(start, n, centre, env[:, j])) for j, b in enumerate(BANDS)}
        secs = start + pd.to_timedelta(np.arange(n) // FS, unit="s")
        print(f.name, info["timing"], round(info["rate_eff"], 2), flush=True)
        for an in ANIMALS:
            z = zone[an].reindex(secs).to_numpy() if len(zone[an]) else np.full(n, None)
            vlog = imu_grid(an, start, n)
            if np.isfinite(vlog).sum() < 600 * FS:
                continue
            v = detrend(vlog)
            ons = onsets(10 ** vlog.astype(np.float64) - 0.01, th[an]) if an in th else np.array([], int)
            for where, mask in (("in_house", z == hrow.house), ("elsewhere", np.isin(z, ["house_1", "house_2", "field"]) & (z != hrow.house))):
                mask = np.asarray(mask, bool)
                secs_ok = int((mask & np.isfinite(v)).sum() / FS)
                if secs_ok < 600:
                    continue
                n_on = int(mask[ons].sum()) if len(ons) else 0
                for band in [b[0] for b in BANDS]:
                    r = xcorr(M[band], v, mask, ml)
                    if not np.isfinite(r).any():
                        continue
                    i = int(np.nanargmax(r))
                    row = {"mic": hrow.mic, "file": f.name, "part": hrow.part, "animal": an, "where": where, "band": band,
                           "seconds": secs_ok, "onsets": n_on, "peak_lag_s": lags[i], "peak_r": r[i], "r_lag0": r[ml]}
                    if band == "b2":
                        nul = []
                        for sh in NULL_SHIFTS_S:
                            k = int(sh * FS) * (1 if rng.random() < 0.5 else -1)
                            rn = xcorr(M[band], np.roll(v, k), mask, ml)
                            nul.append(np.nanmax(rn))
                        row["null_p99"] = float(np.nanpercentile(nul, 99))
                        row["coupled"] = bool(r[i] > row["null_p99"])
                        curves[(f.name, an, where)] = r
                        # 10-min sub-windows: lag per window (drift)
                        for w0 in range(0, n, 600 * FS):
                            wm = mask.copy()
                            wm[:w0] = False
                            wm[w0 + 600 * FS:] = False
                            if (wm & np.isfinite(v)).sum() < 120 * FS:
                                continue
                            rw = xcorr(M[band], v, wm, ml)
                            if np.isfinite(rw).any():
                                drift.append({"mic": hrow.mic, "file": f.name, "animal": an, "where": where, "window_min": w0 // (60 * FS),
                                              "peak_lag_s": lags[int(np.nanargmax(rw))], "peak_r": float(np.nanmax(rw))})
                    pr.append(row)
        # mic offset for this file (b2, coupled in-house rats)
        P = pd.DataFrame([r for r in pr if r["file"] == f.name and r["band"] == "b2" and r["where"] == "in_house" and r.get("coupled")])
        if len(P):
            o = float(np.average(P.peak_lag_s, weights=P.peak_r)) if len(P) < 3 else float(np.median(np.repeat(P.peak_lag_s, np.maximum(1, (P.peak_r * 100).astype(int)))))
            offs.append({"mic": hrow.mic, "file": f.name, "part": hrow.part, "timing": info["timing"], "coupled_rats": len(P),
                         "offset_s": o, "max_dev_s": float(np.max(np.abs(P.peak_lag_s - o))), "lags": ";".join(f"{a_}:{l_:+.2f}" for a_, l_ in zip(P.animal, P.peak_lag_s))})
            # attribution of b2 transients with the offset applied
            m_raw = to_grid(start, n, centre, env[:, [b[0] for b in BANDS].index("b2")]).astype(np.float64)
            base = pd.Series(m_raw).rolling(2 * FS + 1, center=True, min_periods=FS).median().to_numpy()
            hi = np.nan_to_num(m_raw - base, nan=0) >= 10
            cs = np.r_[0, np.cumsum(hi)]
            kk = np.flatnonzero(hi)
            kk = kk[kk >= FS]
            tr = kk[(cs[kk] - cs[kk - FS]) == 0]
            inh = [an for an in ANIMALS if len(zone[an])]
            O = {}
            for an in inh:
                vlog = imu_grid(an, start, n)
                O[an] = (onsets(10 ** vlog.astype(np.float64) - 0.01, th[an]) if an in th else np.array([], int),
                         zone[an].reindex(secs).to_numpy())
            for label, shift in (("observed", 0), ("shifted_null", 45 * FS)):
                cnt = {"none": 0, "one": 0, "several": 0}
                for k0 in tr:
                    kc = k0 + int(round(o * FS)) + shift
                    if kc < 0 or kc >= n:
                        continue
                    movers = [an for an, (on, zz) in O.items() if zz[min(k0, n - 1)] == hrow.house and len(on) and np.any(np.abs(on - kc) <= int(0.2 * FS))]
                    cnt["none" if not movers else ("one" if len(movers) == 1 else "several")] += 1
                tot = max(1, sum(cnt.values()))
                attr.append({"mic": hrow.mic, "file": f.name, "part": hrow.part, "which": label, "transients": sum(cnt.values()),
                             **{k: v_ / tot for k, v_ in cnt.items()}})
    PR, OF, DR, AT = pd.DataFrame(pr), pd.DataFrame(offs), pd.DataFrame(drift), pd.DataFrame(attr)
    for nm, T in (("pairs", PR), ("offsets", OF), ("drift", DR), ("attribution", AT)):
        T.to_csv(out / f"{nm}.csv", index=False)
    # criteria
    b2 = PR[PR.band == "b2"]
    eligible = b2[(b2["where"] == "in_house") & (b2.seconds >= 600) & (b2.onsets >= 20)]
    crit_a = float(eligible.coupled.mean()) if len(eligible) else np.nan
    els = b2[b2["where"] == "elsewhere"]
    crit_b = float(els.coupled.mean()) if len(els) else np.nan
    crit_c = float((OF.max_dev_s <= 0.04).mean()) if len(OF) else np.nan
    C = pd.DataFrame([{"criterion": "(a) in-house coupled (>= 75 %)", "value": crit_a, "n": len(eligible), "pass": crit_a >= 0.75},
                      {"criterion": "(b) elsewhere coupled (<= 10 %)", "value": crit_b, "n": len(els), "pass": crit_b <= 0.10},
                      {"criterion": "(c) mic-hours whose coupled rats agree within 40 ms", "value": crit_c, "n": len(OF), "pass": crit_c == 1.0}])
    band_tab = (PR.groupby(["where", "band"]).agg(pairs=("peak_r", "size"), peak_r_median=("peak_r", "median"),
                                                   r_lag0_median=("r_lag0", "median"), lag_median_s=("peak_lag_s", "median")).reset_index())
    dr_tab = pd.DataFrame()
    if len(DR):
        d_in = DR[DR["where"] == "in_house"]
        rows = []
        for (mic, fl), g in d_in.groupby(["mic", "file"]):
            gg = g.groupby("window_min").peak_lag_s.median()
            if len(gg) >= 3:
                sl = np.polyfit(gg.index.to_numpy() / 60.0, gg.to_numpy(), 1)[0]
                rows.append({"mic": mic, "file": fl, "windows": len(gg), "lag_first_s": gg.iloc[0], "lag_last_s": gg.iloc[-1], "slope_s_per_h": sl})
        dr_tab = pd.DataFrame(rows)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    files = list(dict.fromkeys(k[0] for k in curves))
    fig, axs = plt.subplots(len(files), 1, figsize=(9, 2.0 * len(files)), sharex=True, squeeze=False)
    for ax, fl in zip(axs[:, 0], files):
        for (f_, an, where), r in curves.items():
            if f_ == fl:
                ax.plot(lags, r, lw=1.2 if where == "in_house" else 0.7, ls="-" if where == "in_house" else ":", label=f"{an} {where}")
        ax.axvline(0, color="k", lw=0.4)
        ax.set_title(fl, fontsize=7)
        ax.legend(fontsize=6, ncol=3)
    axs[-1, 0].set_xlabel("lag l (s): r of mic b2 (4-20 kHz) envelope at t vs head VeDBA at t + l")
    fig.suptitle(f"mic <-> head IMU cross-correlation (pilot)  {gc}", fontsize=8)
    save_fig(fig, fd / "ephys_spikes_mic_imu_sync_pilot_xcorr_2026c.png")
    L = ["# In-house microphones ↔ head IMU: pilot (cohort 2026c)", "",
         f"Plan `implementation_plan/2026-10-08-mic-imu-sync.md` (criteria fixed before results). Driver `ephys/mic_imu_sync.py pilot` "
         f"(commit {gc}); bulk `{out}`. **Technical ledger.**", "", "## Definitions", "", "```", (__doc__ or "").strip(), "```", "",
         "## Hours (chosen by occupancy only)", "", md_table(hours[["mic", "house", "start", "end", "part", "rat_seconds"]]), "",
         "## Pass criteria", "", md_table(C.round(3)), "",
         "## Mic offset per file (b2, coupled in-house rats; + = the IMU sees the event later = the mic timeline runs ahead)", "",
         md_table(OF.round(3)) if len(OF) else "none", "",
         "## Drift within the hour (in-house rats, 10-min windows, median lag per window)", "", md_table(dr_tab.round(3)) if len(dr_tab) else "none", "",
         "## Bands", "", md_table(band_tab.round(3)), "",
         "## Pairs (b2)", "", md_table(b2.drop(columns=["band"]).round(3)), "",
         "## Who moved: b2 transients (>= 10 dB over the 2-s median) with an in-house IMU onset within 0.2 s (offset applied)", "",
         md_table(AT.round(3)) if len(AT) else "none", "",
         "![](../figures/ephys_spikes_mic_imu_sync_pilot_xcorr_2026c.png)", ""]
    flat = [ln for x in L for ln in (x if isinstance(x, list) else [x])]
    (rd / "ephys_spikes_mic_imu_sync_pilot_2026c.md").write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_mic_imu_sync_pilot_2026c.json", {"run_dir": str(out), "git_commit": gc})
    print(C.to_string(index=False), "\n", OF.round(3).to_string(index=False), flush=True)
    print("written", rd / "ephys_spikes_mic_imu_sync_pilot_2026c.md")


OFFSET_S = -0.02                 # pilot median: PC time of a mic event = mic time - 0.02 s
PEAK_DB = 10.0


def morning_windows() -> list[tuple[pd.Timestamp, pd.Timestamp, str]]:
    """Plan Amendment 1: per date, [round_start - 60 min, round_start - 5 min] with round_start = the earliest logged /
    inferred round stop between 05:00 and 10:00; else 07:00-08:00; minus logged acoustic field events."""
    import yaml
    from mic_wake_pilot import ROOT
    g0 = json.load(open(ROOT / "results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_phase0_2026c.json"))["run_dir"]
    g = pd.read_csv(Path(g0) / "gaps.csv", parse_dates=["gap_start", "gap_end"])
    g = g[g.cause.isin(["round_logged", "round_inferred"])]
    fe = [e for e in yaml.safe_load(open(ROOT / "cohorts/2026c.yaml", encoding="utf-8"))["field_events"] if e.get("kind") == "acoustic"]
    out = []
    for d in pd.date_range("2026-08-31", "2026-09-11"):
        rs = g[(g.gap_start >= d + pd.Timedelta(hours=5)) & (g.gap_start < d + pd.Timedelta(hours=10))].gap_start.min()
        if pd.isna(rs):
            w0, w1, why = d + pd.Timedelta(hours=7), d + pd.Timedelta(hours=8), "07-08 (no morning round)"
        else:
            w0, w1, why = rs - pd.Timedelta(minutes=60), rs - pd.Timedelta(minutes=5), f"before the round at {rs:%H:%M}"
        for e in fe:
            es = pd.Timestamp(str(e["start"]))
            ee = pd.Timestamp(str(e["end"])) if e.get("end") not in (None, "None") else es.normalize() + pd.Timedelta(days=1)   # unknown end: rest of that day
            if es < w1 and ee > w0:
                w1 = min(w1, es) if es > w0 else w1
                if es <= w0:
                    w0 = max(w0, ee)
        if w1 - w0 >= pd.Timedelta(minutes=10) and w1 <= CUTOFF:
            out.append((w0.floor("s"), w1.floor("s"), why))
    return out


def window_envelope(raw: Path, mic: str, w0: pd.Timestamp, n: int) -> tuple[np.ndarray, list[str]]:
    """50-Hz band envelopes (n x bands, dB) of `mic` on the grid w0 + k/FS (mic timeline), from the hourly WAVs."""
    w1 = w0 + pd.Timedelta(seconds=n / FS)
    grid = np.full((n, len(BANDS)), np.nan, np.float32)
    used = []
    for day in sorted({w0.normalize(), w1.normalize(), (w0 - pd.Timedelta(hours=1)).normalize()}):
        for f in sorted((raw / f"{day:%Y-%m-%d}" / mic).glob(f"{mic}_*.wav")):
            if not NAME_RE.search(f.name):
                continue
            _, s, e = parse_name(f)
            e = e if e is not None else s + pd.Timedelta(hours=1)
            if s >= w1 or e <= w0:
                continue
            a, b = max(0.0, (w0 - s).total_seconds() - 1), (w1 - s).total_seconds() + 1
            start, centre, env, info = frame_envelope(f, a, b)
            rel = (start - w0).total_seconds() + centre
            g = to_grid(w0, n, rel, env)
            grid = np.where(np.isfinite(g), g, grid)
            used.append(f"{day:%Y-%m-%d}/{mic}/{f.name}")
    return grid, used


def peak_onsets(m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Frames >= PEAK_DB above the 2-s running median after >= 1 s below; returns indices and the peak size (dB, max
    excess within 0.2 s)."""
    base = pd.Series(m).rolling(2 * FS + 1, center=True, min_periods=FS).median().to_numpy()
    exc = m - base
    hi = np.nan_to_num(exc, nan=0) >= PEAK_DB
    cs = np.r_[0, np.cumsum(hi)]
    k = np.flatnonzero(hi)
    k = k[k >= FS]
    k = k[(cs[k] - cs[k - FS]) == 0]
    size = np.array([np.nanmax(exc[i:i + 11]) for i in k]) if len(k) else np.array([])
    return k, size


def peaks(a) -> None:
    """Plan Amendment 1: mic peaks -> in-house rats' IMU, in the quiet hour before the morning battery round."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
    from _common import git_commit, write_json
    from mic_wake_pilot import ROOT, load_zone
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_cycles_v2 import build_records
    from sleep_quant import md_table, save_fig
    from sleep_schedule import N, R, REVIEW, STATES, W, included_sessions
    out = run_dir("mic_imu_peaks", "2026c")
    rd, fd = report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes")
    gc = git_commit()
    raw = Path(a.raw)
    rng = np.random.default_rng(9)
    rois = {r["name"]: r for r in json.load(open(ROOT / "wiser/configs/wiser_rois.json"))["rois"] if r["name"] in ("house_1", "house_2")}
    zone = {an: load_zone(an, [d.strftime("%Y%m%d") for d in pd.date_range("2026-08-30", "2026-09-11")], rois) for an in ANIMALS}
    th = json.load(open(sorted(OUT.glob("sleep_events_2026*/thresholds.json"))[-1]))["theta_vedba_ms2"]
    recs = build_records(included_sessions(Path(REVIEW), Path(STATES)), Path(STATES))
    t_min = min(rc["start"] for rc in recs).floor("s")
    span = int((max(rc["end"] for rc in recs) - t_min).total_seconds()) + 2
    S = {}
    for an in ANIMALS:
        s = np.zeros(span, np.int8)
        for rc in recs:
            if rc["animal"] == an:
                o = int((rc["start"] - t_min).total_seconds())
                s[o:o + len(rc["state"])] = rc["state"][:max(0, span - o)]
        S[an] = s
    W_ = morning_windows()
    pd.DataFrame(W_, columns=["start", "end", "why"]).to_csv(out / "windows.csv", index=False)
    sh = int(round(OFFSET_S * FS))
    names = {W: "WAKE", N: "NREM", R: "REM", 0: "unknown"}
    prow, rrow = [], []
    tr_obs = {}
    for w0, w1, why in W_:
        n = int((w1 - w0).total_seconds() * FS)
        secs = w0 + pd.to_timedelta(np.arange(n) // FS, unit="s")
        imu = {an: imu_grid(an, w0, n) for an in ANIMALS}
        ons = {an: onsets(10 ** imu[an].astype(np.float64) - 0.01, th[an]) if an in th else np.array([], int) for an in ANIMALS}
        zz = {an: (zone[an].reindex(secs).to_numpy() if len(zone[an]) else np.full(n, None)) for an in ANIMALS}
        for house, mic in HOUSE_MIC.items():
            env, used = window_envelope(raw, mic, w0, n)
            if np.isfinite(env[:, 2]).mean() < 0.5:
                continue
            for bi, band in enumerate([b[0] for b in BANDS]):
                if band not in ("b1", "b2", "b3", "b4"):
                    continue
                pk, size = peak_onsets(env[:, bi].astype(np.float64))
                keep = (pk + sh - 150 >= 0) & (pk + sh + 150 < n)
                pk, size = pk[keep], size[keep]
                far = np.ones(n, bool)
                for k in pk:
                    far[max(0, k - 2 * FS):k + 2 * FS] = False
                cand = np.flatnonzero(far)
                cand = cand[(cand + sh - 150 >= 0) & (cand + sh + 150 < n)]
                nul = rng.choice(cand, size=min(len(cand), 5 * len(pk)), replace=False) if len(pk) and len(cand) else np.array([], int)
                for which, ks, sz in (("observed", pk, size), ("random_time", nul, np.full(len(nul), np.nan))):
                    for k, s_db in zip(ks, sz):
                        ki = k + sh
                        sec_abs = int((w0 - t_min).total_seconds()) + ki // FS
                        movers, resp, valid = [], {}, 0
                        for an in ANIMALS:
                            if zz[an][min(ki, n - 1)] != house:
                                continue
                            v = imu[an]
                            if np.isfinite(v[ki - 150:ki + 50]).mean() < 0.8:
                                continue
                            valid += 1
                            st = int(S[an][sec_abs]) if 0 <= sec_abs < span else 0
                            o = ons[an]
                            hit = o[(o >= ki - 15) & (o <= ki + 25)]
                            rsp = float(np.nanmax(v[ki - 15:ki + 26]) - np.nanmedian(v[ki - 150:ki - 49]))
                            woke10 = bool(st in (N, R) and np.any(S[an][sec_abs + 1:sec_abs + 11] == W)) if 0 <= sec_abs < span - 11 else False
                            rrow.append({"house": house, "band": band, "which": which, "t": w0 + pd.Timedelta(seconds=k / FS), "animal": an,
                                         "state": names.get(st, "unknown"), "moved": bool(len(hit)), "lag_s": (hit[0] - ki) / FS if len(hit) else np.nan,
                                         "resp": rsp, "woke10": woke10, "peak_db": s_db})
                            resp[an] = rsp
                            if len(hit):
                                movers.append(an)
                            if band == "b2":
                                tr_obs.setdefault((which, names.get(st, "unknown")), []).append(v[ki - 150:ki + 151] - np.nanmedian(v[ki - 150:ki - 49]))
                        if valid == 0:
                            continue
                        f_, off_ = "", np.nan
                        for u in used:
                            _, s0, e0 = parse_name(Path(u))
                            tt = w0 + pd.Timedelta(seconds=k / FS)
                            if s0 <= tt < (e0 if e0 is not None else s0 + pd.Timedelta(hours=1)):
                                f_, off_ = u, (tt - s0).total_seconds()
                        prow.append({"house": house, "mic": mic, "band": band, "which": which, "t": w0 + pd.Timedelta(seconds=k / FS),
                                     "window": why, "peak_db": s_db, "rats_in_house": valid, "rats_moved": len(movers),
                                     "class": "none" if not movers else ("one" if len(movers) == 1 else "several"),
                                     "movers": ";".join(movers), "top_rat": max(resp, key=resp.get) if resp else "",
                                     "top_resp": max(resp.values()) if resp else np.nan, "mic_file": f_, "mic_offset_s": off_})
        print(w0, w1, why, "peaks so far", sum(1 for p in prow if p["which"] == "observed"), flush=True)
    P, Rr = pd.DataFrame(prow), pd.DataFrame(rrow)
    P.to_csv(out / "peaks.csv.gz", index=False)
    Rr.to_csv(out / "peak_rats.csv.gz", index=False)
    T1 = (P.groupby(["house", "band", "which"]).agg(peaks=("class", "size"), per_hour=("class", "size"),
                                                     none=("class", lambda x: np.mean(x == "none")), one=("class", lambda x: np.mean(x == "one")),
                                                     several=("class", lambda x: np.mean(x == "several")),
                                                     rats_in_house=("rats_in_house", "mean")).reset_index())
    hours = sum((w1 - w0).total_seconds() for w0, w1, _ in W_) / 3600
    T1["per_hour"] = np.where(T1.which == "observed", T1.peaks / hours, np.nan)
    Pb = P[(P.band == "b2")]
    Pb = Pb.assign(tier=pd.cut(Pb.peak_db, [10, 15, 20, 30, 200], labels=["10-15 dB", "15-20 dB", "20-30 dB", ">30 dB"], right=False))
    obs = Pb[Pb.which == "observed"].groupby(["house", "tier"], observed=True).agg(peaks=("class", "size"), any_moved=("class", lambda x: np.mean(x != "none"))).reset_index()
    nul = Pb[Pb.which == "random_time"].groupby("house").agg(null_any_moved=("class", lambda x: np.mean(x != "none"))).reset_index()
    T2 = obs.merge(nul, on="house")
    Rb = Rr[Rr.band == "b2"]
    T3 = (Rb.groupby(["which", "state"]).agg(rat_peaks=("moved", "size"), moved=("moved", "mean"), resp_median=("resp", "median"),
                                              woke10=("woke10", "mean")).reset_index())
    lag = Rb[(Rb.which == "observed") & Rb.moved].lag_s
    T4 = pd.cut(lag, np.arange(-0.3, 0.51, 0.1)).value_counts().sort_index().rename("onsets").reset_index()
    T4.columns = ["lag_bin_s", "onsets"]
    top = P[(P.which == "observed") & (P.band == "b2")].sort_values("peak_db", ascending=False).head(30)
    for nm, T in (("by_band", T1), ("by_size", T2), ("by_state", T3), ("lag", T4)):
        T.to_csv(rd / f"ephys_spikes_mic_imu_peaks_{nm}_2026c.csv", index=False)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tax = np.arange(-150, 151) / FS
    fig, ax = plt.subplots(figsize=(9, 3.5))
    for (which, st), L_ in sorted(tr_obs.items()):
        if len(L_) >= 20 and st in ("NREM", "REM", "WAKE"):
            ax.plot(tax, np.nanmean(np.vstack(L_), 0), ls="-" if which == "observed" else ":", label=f"{st} {which} (n={len(L_)})")
    ax.axvline(0, color="k", lw=0.4)
    ax.set_xlabel("s from the mic peak (b2 4-20 kHz; PC time)")
    ax.set_ylabel("log10 VeDBA - baseline")
    ax.legend(fontsize=7)
    ax.set_title(f"In-house rats' head movement around house-mic peaks, quiet hour before the morning round  {gc}", fontsize=8)
    save_fig(fig, fd / "ephys_spikes_mic_imu_peaks_2026c.png")
    L = ["# House-mic peaks → the in-house rats' head IMU, before the morning round (cohort 2026c)", "",
         f"Plan `implementation_plan/2026-10-08-mic-imu-sync.md`, Amendment 1 (before results). Driver `ephys/mic_imu_sync.py peaks` "
         f"(commit {gc}); bulk `{out}`. Descriptive; the sounds are not listened to. **Technical ledger.**", "",
         "## Definitions", "", "```", (peaks.__doc__ or "").strip(), "Windows: " + (morning_windows.__doc__ or "").strip(),
         "Peak: " + (peak_onsets.__doc__ or "").strip(),
         "Per peak and in-house rat (WISER zone; IMU valid >= 80 % over -3..+1 s): moved = an IMU onset (Phase-6 rule) within "
         "[-0.3, +0.5] s; resp = max log10 VeDBA over [-0.3, +0.5] s minus its median over [-3, -1] s; lag < 0 = the rat moved "
         "before the sound; woke10 = an asleep rat scored WAKE within 10 s. PC time of a mic frame = mic time - 0.02 s. "
         "Null = 5 random times per peak in the same windows, >= 2 s from any peak.", "```", "",
         f"Windows: {len(W_)} ({hours:.1f} h); see `windows.csv` in the run folder.", "",
         "## Peaks: share with none / one / several in-house rats moving (observed vs null)", "", md_table(T1.round(3)), "",
         "## b2 peaks by size: share with any in-house rat moving vs the null", "", md_table(T2.round(3)), "",
         "## Per rat and state (b2): moved, response, woke within 10 s", "", md_table(T3.round(3)), "",
         "## Lag of the first IMU onset relative to the peak (b2, observed; < 0 = the rat moved first)", "", md_table(T4), "",
         "![](../figures/ephys_spikes_mic_imu_peaks_2026c.png)", "",
         "## The 30 largest b2 peaks (for listening; file under F:/3rd_rat or the storage copy, offset in s)", "",
         md_table(top[["house", "t", "peak_db", "rats_in_house", "movers", "top_rat", "mic_file", "mic_offset_s"]].round(2)), ""]
    flat = [ln for x in L for ln in (x if isinstance(x, list) else [x])]
    (rd / "ephys_spikes_mic_imu_peaks_2026c.md").write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_mic_imu_peaks_2026c.json", {"run_dir": str(out), "git_commit": gc})
    print(T1.round(3).to_string(index=False), "\n", T2.round(3).to_string(index=False), "\n", T3.round(3).to_string(index=False), "\n", T4.to_string(index=False), flush=True)
    print("written", rd / "ephys_spikes_mic_imu_peaks_2026c.md")


def selftest() -> None:
    """Synthetic: an IMU burst train and a mic envelope with the same bursts 0.30 s earlier (mic ahead) + noise; the
    peak lag must be +0.30 s, a rolled IMU must not couple, and the onset rule must find the bursts."""
    rng = np.random.default_rng(1)
    n = 30000
    v = rng.normal(-1.5, 0.05, n)
    ks = np.sort(rng.choice(np.arange(200, n - 200), 150, replace=False))
    for k in ks:
        v[k:k + 10] += 1.2
    m = rng.normal(-60, 1.0, n)
    for k in ks - 15:                                  # 15 samples = 0.30 s earlier on the mic's own time stamps
        m[k:k + 10] += 8
    mask = np.ones(n, bool)
    r = xcorr(detrend(m), detrend(v), mask, 100)
    lag = (np.nanargmax(r) - 100) / FS
    assert abs(lag - 0.30) < 0.021, lag
    rn = xcorr(detrend(m), detrend(np.roll(v, 2000)), mask, 100)
    assert np.nanmax(rn) < 0.5 * np.nanmax(r), (np.nanmax(rn), np.nanmax(r))
    on = onsets(10 ** v - 0.01, 0.5)
    assert len(on) >= 100, len(on)                     # bursts < 1 s after the previous one are not onsets (rule)
    t = np.arange(0, 10, 0.02003)
    g = to_grid(pd.Timestamp("2026-09-01"), 400, t, np.arange(len(t), dtype=np.float32))
    assert np.isfinite(g).sum() > 390
    print(f"selftest PASS: lag {lag:+.2f} s (true +0.30), peak r {np.nanmax(r):.2f} vs rolled {np.nanmax(rn):.2f}, onsets {len(on)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["pilot", "peaks"])
    ap.add_argument("--raw", default="F:/3rd_rat")
    ap.add_argument("--hours-per-mic", type=int, default=6)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == "pilot":
        pilot(a)
    elif a.cmd == "peaks":
        peaks(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
