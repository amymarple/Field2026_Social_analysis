r"""In-house microphones <-> head IMU: who made the sound, and the mic clock (plan
implementation_plan/2026-10-08-mic-imu-sync.md; definitions there, repeated in the report).

    python ephys/mic_imu_sync.py pilot [--raw F:/3rd_rat] [--hours-per-mic 6]
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
def frame_envelope(p: Path) -> tuple[pd.Timestamp, np.ndarray, np.ndarray, dict]:
    """Per 20-ms frame: centre time (s after the file-name start, PC clock, by the file's timing model) and band power
    in dB (frames x bands, NaN for all-zero frames). Same frames and timing model as mic_band_levels.band_levels."""
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
    out = np.full((nf, len(BANDS)), np.nan, np.float32)
    step = 3000
    for f0 in range(0, nf, step):
        f1 = min(nf, f0 + step)
        seg = np.asarray(x[f0 * L:f1 * L], dtype=np.float32).reshape(f1 - f0, L)
        nz = np.any(seg != 0, axis=1)
        seg -= seg.mean(axis=1, keepdims=True)
        P = np.abs(np.fft.rfft(seg * win, axis=1)) ** 2 / norm
        pb = np.stack([P[:, s].sum(axis=1) for s in sel], axis=1)
        with np.errstate(divide="ignore"):
            out[f0:f1] = np.where(nz[:, None], 10 * np.log10(pb + 1e-20), np.nan)
    centre = t_first + (np.arange(nf) + 0.5) * L / rate_eff
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
    ap.add_argument("cmd", nargs="?", choices=["pilot"])
    ap.add_argument("--raw", default="F:/3rd_rat")
    ap.add_argument("--hours-per-mic", type=int, default=6)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == "pilot":
        pilot(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
