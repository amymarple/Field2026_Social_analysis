r"""
analyze_nightly_progression.py — nightly 9pm-12am movement (habituation vs rain), all nights.

Rate-normalized, paired (5 rats, Sova removed) comparison of nocturnal movement
to separate **novelty habituation** from **rain**. Nights are auto-discovered:
  * primary metric = active_distance_m_per_valid_hour (unequal windows compare);
  * habituation = the full rate curve over all nights (clean dry contrast 6/28 vs 6/29);
  * rain is classified PER NIGHT from AWN weather (not "the last night"): `wet_ground`
    = meaningful rain in 15:00-24:00, `rain_in_window` = rain in the 21-24 window ->
    (a) a WET-vs-DRY between-night rate contrast (the general test), read against
    per-night valid_frac (rain raises UWB dropout -> NOT missing-at-random), and
    (b) the within-night 22:30 DiD retained for nights that actually have in-window rain.

Everything is exploratory/candidate (n=5 paired). Read-only; outputs to
D:\Field2026_analysis_out\nightly_progression_YYYYMMDD_HHMM\.

    conda activate cv
    cd wiser
    python scripts/analyze_nightly_progression.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
import wiser_analysis_utils as w        # noqa: E402
import time_utils                       # noqa: E402
import metrics                          # noqa: E402

DEFAULT_DB = Path(r"D:\Wiser\data\1stcohort_2026.sqlite")
DEFAULT_FIXED = Path(r"D:\Wiser\data\tag_reports.sqlite")
DEFAULT_GT = PROJECT_ROOT / "configs" / "fixed_position_ground_truth.csv"
from output_paths import OUT_ROOT as DEFAULT_OUT_ROOT   # single source of truth (env FIELD2026_ANALYSIS_OUT_ROOT)
WEATHER_FILES = [  # newest full export first; load_weather_multi dedups + tolerates missing files
    Path(r"D:\Reolink_record\audio_in\weather_data\AWN-F8B3B78DEAC9-20260628-20260709.csv"),
    Path(r"D:\weather_data\AWN-F8B3B78DEAC9-20260628-20260629.csv"),
    Path(r"D:\weather_data\AWN-F8B3B78DEAC9-20260630-20260701.csv")]
DROP_TAGS = {"12409"}                   # Sova, deceased -> removed entirely
RAIN_MMHR_THR = 0.2                     # per-night wet classification: rain rate above this = wet
RAIN_SPLIT = "22:30"                    # 6/30 observed in-window rain onset (within-night DiD)
RAIN_BAND_HHMM = ("22:30", "22:50")     # 6/30 observed burst
BUFFERS = (0, 20)                       # DiD without / with transition buffer


def main() -> None:
    ap = argparse.ArgumentParser(description="Nightly 9pm-12am movement (habituation vs rain; all nights).")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--fixed", type=Path, default=DEFAULT_FIXED)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT_ROOT)
    ap.add_argument("--clock-start", type=int, default=21)
    ap.add_argument("--clock-end", type=int, default=24)
    args = ap.parse_args()
    if not args.db.exists():
        raise SystemExit(f"[nightly] DB not found: {args.db}")

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M")
    out = args.output / f"nightly_progression_{ts}"
    fig = out / "figures"
    fig.mkdir(parents=True, exist_ok=True)
    print(f"=== Nightly progression ===\n  DB: {args.db}\n  out: {out}\n")

    # thresholds from the stationary baseline
    fx = w.load_wiser_session(args.fixed)
    fx = time_utils.convert_timestamps(fx)
    fx = time_utils.trim_last_n_minutes(fx, minutes=10)
    fx = w.add_speed(fx)
    moving_thr = w.speed_noise_floor(fx)["p99"]
    jitter = float(np.nanmedian(metrics.compute_summary(
        fx, ground_truth=metrics.load_ground_truth(DEFAULT_GT))["rms_jitter"]))
    print(f"  moving_thr(p99)={moving_thr:.2f} in/s  jitter_floor={jitter:.2f} in")

    # free session -> cleaned, Sova removed, 9pm-12am paired window
    df = w.load_wiser_session(args.db)
    df = time_utils.convert_timestamps(df)
    df = w.add_speed(df)
    df = w.add_validity_flags(df, jitter_floor_in=jitter)
    df = w.apply_tag_cutoffs(df)
    df = df[~df["shortid"].astype(str).isin(DROP_TAGS)]
    win = w.select_route_window(df, clock_start=args.clock_start, clock_end=args.clock_end)
    nights = sorted(win["night"].unique())
    print(f"  nights={nights}  rats/night="
          f"{win.groupby('night')['shortid'].nunique().to_dict()}")
    if len(nights) < 2:
        raise SystemExit("[nightly] need >=2 nights of data.")
    # --- weather -> per-night rain classification (data-driven; replaces "last night = wet") ---
    weather = w.load_weather_multi(WEATHER_FILES)

    def _seg(night, h0, h1):
        s = w._roi_time_utc(f"{night}T{h0:02d}:00:00{w.LOCAL_OFFSET_STR}")
        if h1 < 24:
            e = w._roi_time_utc(f"{night}T{h1:02d}:00:00{w.LOCAL_OFFSET_STR}")
        else:
            nd = (pd.Timestamp(night) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            e = w._roi_time_utc(f"{nd}T{h1 - 24:02d}:00:00{w.LOCAL_OFFSET_STR}")
        if weather.empty:
            return weather
        dtu = weather["datetime_utc"].to_numpy()
        return weather[(dtu >= s) & (dtu < e)]

    def _max_rain(seg):
        if seg.empty or "rain_rate_mmhr" not in seg or not seg["rain_rate_mmhr"].notna().any():
            return np.nan
        return float(seg["rain_rate_mmhr"].max())

    wsum = []
    for night in nights:
        inw = _seg(night, args.clock_start, args.clock_end)   # in-window 21-24 rain (acute)
        ante = _seg(night, 15, args.clock_start)              # afternoon 15-21 (wets the ground)
        mx_in, mx_ante = _max_rain(inw), _max_rain(ante)
        has_wx = not inw.empty
        rain_in_window = bool(np.isfinite(mx_in) and mx_in > RAIN_MMHR_THR)
        wet_ground = bool(rain_in_window or (np.isfinite(mx_ante) and mx_ante > RAIN_MMHR_THR))
        wsum.append({"night": night, "weather_rows_in_window": int(len(inw)),
                     "max_rain_inwindow_mmhr": mx_in, "max_rain_afternoon_mmhr": mx_ante,
                     "rain_in_window": rain_in_window, "wet_ground": wet_ground,
                     "weather_known": has_wx})
    wx_night = pd.DataFrame(wsum)
    wx_night.to_csv(out / "weather_night_summary.csv", index=False)
    wet_nights = wx_night[wx_night["wet_ground"]]["night"].tolist()
    inwindow_rain_nights = wx_night[wx_night["rain_in_window"]]["night"].tolist()
    dry_nights = [n for n in nights if n not in wet_nights
                  and bool(wx_night.set_index("night").loc[n, "weather_known"])]
    print(f"  wet_ground nights={wet_nights}  in-window-rain nights={inwindow_rain_nights}")

    # --- rates + habituation (primary; generalizes to all nights) ---
    nr = w.nightly_rates(win, moving_thr_inps=moving_thr,
                         clock_start=args.clock_start, clock_end=args.clock_end)
    nr.to_csv(out / "nightly_rates.csv", index=False)
    w.plot_nightly_trajectories(win, save_path=fig / "N1_trajectories.png")
    w.plot_nightly_rate_lines(nr, save_path=fig / "N2_rate_habituation.png")

    # --- QC per night (valid_frac / dropout — read every rain effect against this) ---
    qc = (win.assign(anch=win.get("anchors_used"))
          .groupby("night")
          .apply(lambda g: pd.Series({
              "n_fixes": len(g), "valid_frac": float(g["valid"].mean()),
              "mean_anchors": float(pd.to_numeric(g.get("anchors_used"), errors="coerce").mean()),
              "n_rats": g["shortid"].nunique()}), include_groups=False)
          .reset_index())
    qc.to_csv(out / "nightly_qc.csv", index=False)

    # --- WET-vs-DRY between-night contrast (the general rain test) ---
    rate_by_night = nr.groupby("night")["active_distance_m_per_valid_hour"].mean()
    vf = qc.set_index("night")["valid_frac"]
    wet_rate = float(np.nanmean([rate_by_night.get(n, np.nan) for n in wet_nights])) if wet_nights else float("nan")
    dry_rate = float(np.nanmean([rate_by_night.get(n, np.nan) for n in dry_nights])) if dry_nights else float("nan")
    pd.DataFrame([{"night": n, "active_distance_m_per_valid_hour": float(rate_by_night.get(n, np.nan)),
                   "valid_frac": float(vf.get(n, np.nan)), "night_index": nights.index(n),
                   "class": ("wet_ground" if n in wet_nights else "dry" if n in dry_nights else "unknown"),
                   "rain_in_window": n in inwindow_rain_nights} for n in nights]
                 ).to_csv(out / "wet_vs_dry_by_night.csv", index=False)

    # --- through-the-night cumulative curves (mark the in-window rain band) ---
    cum = w.cumulative_night_distance(win, moving_thr_inps=moving_thr, bin_s=60)
    def _min_since_start(hhmm):
        h, m = map(int, hhmm.split(":"))
        return (h - args.clock_start) * 60 + m
    band = (_min_since_start(RAIN_BAND_HHMM[0]), _min_since_start(RAIN_BAND_HHMM[1]))
    w.plot_cumulative_night(cum, rain_band_min=band, save_path=fig / "N3_cumulative.png")

    # --- within-night rain DiD: ONLY for nights that actually have in-window rain ---
    did_variants, split_frames = {}, []
    rain_night = inwindow_rain_nights[0] if inwindow_rain_nights else None
    control_nights = ([n for n in dry_nights if n != rain_night]
                      or [n for n in nights if n != rain_night]) if rain_night else []
    if rain_night is not None:
        for buf in BUFFERS:
            sr = w.night_split_rates(win, moving_thr_inps=moving_thr, split_hm=RAIN_SPLIT,
                                     buffer_min=buf, clock_start=args.clock_start,
                                     clock_end=args.clock_end)
            split_frames.append(sr)
            did_variants[f"buf{buf}"] = w.rain_did(sr, rain_night, control_nights)
    if split_frames:
        pd.concat(split_frames, ignore_index=True).to_csv(out / "night_split_rates.csv", index=False)
    did_list = [d for d in did_variants.values() if d is not None and not d.empty]
    rain_did_all = pd.concat(did_list, ignore_index=True) if did_list else pd.DataFrame()
    did_conf = pd.DataFrame()
    if not rain_did_all.empty:
        rain_did_all.to_csv(out / "rain_did.csv", index=False)
        w.plot_rain_did(did_variants, save_path=fig / "N5_rain_did.png")
        did_conf = w.did_confidence(rain_did_all)
        did_conf.to_csv(out / "rain_did_confidence.csv", index=False)
    if not weather.empty and rain_night is not None:
        w.plot_rain_timeline(weather, day=rain_night, night_hours=(args.clock_start, args.clock_end),
                             obs_band_hhmm=RAIN_BAND_HHMM, save_path=fig / "N4_rain_timeline.png")

    # --- confound covariates (data-driven wet classification) ---
    covariates = pd.DataFrame([{
        "night": night,
        "wet_ground": (night in wet_nights),
        "rain_in_window": (night in inwindow_rain_nights),
        "tunnel_present": (night == nights[0]),
        "sova_removed": True,
    } for night in nights])
    covariates.to_csv(out / "night_covariates.csv", index=False)

    # --- verdict ---
    m = rate_by_night
    n1, n2 = nights[0], nights[1]
    drop = 100 * (1 - m[n2] / m[n1]) if m[n1] else float("nan")
    ci_by_buf = {int(r.buffer_min): (r.mean_did, r.ci_lo, r.ci_hi)
                 for r in did_conf.itertuples()} if not did_conf.empty else {}
    def _did_cell(k, v):
        if v is None or v.empty:
            return f"{k}=NA"
        buf = int(v["buffer_min"].iloc[0])
        if buf in ci_by_buf:
            mm, lo, hi = ci_by_buf[buf]
            return f"{k}={mm:+.1f} [95% CI {lo:+.1f},{hi:+.1f}]"
        return f"{k}={float(v['did'].mean()):+.1f}"
    did_str = (", ".join(_did_cell(k, v) for k, v in did_variants.items())
               if did_variants else "n/a (no in-window rain)")
    if rain_night is not None:
        others = [n for n in inwindow_rain_nights if n != rain_night]
        did_desc = (f"Within-night DiD on {rain_night}'s 22:30 in-window rain"
                    + (f" (other in-window nights {others} not split-tested — 22:30 is {rain_night}-specific)"
                       if others else "")
                    + f": [{did_str}] m/valid-hr (n=5; ~0 = no acute suppression beyond time-of-night).")
    else:
        did_desc = "No in-window (21-24) rain on any night -> within-night DiD n/a."
    verdict = (
        f"CANDIDATE habituation over {len(nights)} nights ({n1}->{nights[-1]}): full-night active-distance "
        f"rate {m[n1]:.0f}->{m[nights[-1]]:.0f} m/valid-hr; first dry-night drop {n1}->{n2} {drop:.0f}%. "
        f"WET-vs-DRY (general rain test): wet-ground nights {wet_nights or 'none'} mean {wet_rate:.0f} vs "
        f"dry nights mean {dry_rate:.0f} m/valid-hr -> READ AGAINST per-night valid_frac (nightly_qc.csv): "
        f"rain raises UWB dropout (wet nights NOT missing-at-random) AND wet nights sit later in the "
        f"habituation sequence, so the wet/dry gap is confounded, not causal. " + did_desc +
        " WISER frame unverified; candidate.")
    (out / "nightly_conclusion.txt").write_text(verdict, encoding="utf-8")
    w.write_run_manifest(out, {
        "window": f"{args.clock_start}:00-{args.clock_end}:00 EDT, nights {nights}",
        "paired_core": "5 rats (Sova/12409 removed; Hypnos/12380 auto-cut 2026-07-09 03:35, valid through 07-08)",
        "moving_thr_inps": moving_thr, "jitter_floor_in": jitter,
        "rain_classification": f"per-night from AWN weather: wet_ground = max rain > {RAIN_MMHR_THR} mm/hr "
                               f"in 15:00-24:00; rain_in_window = > {RAIN_MMHR_THR} in {args.clock_start}-{args.clock_end}",
        "wet_ground_nights": wet_nights, "in_window_rain_nights": inwindow_rain_nights,
        "dry_nights": dry_nights, "rain_split": RAIN_SPLIT, "rain_band_observed": RAIN_BAND_HHMM,
        "buffers_min": list(BUFFERS),
        "did_ci": "bootstrap 95% CI of mean DiD across n=5 rats -> rain_did_confidence.csv (if in-window rain)",
        "confounds": "night_covariates.csv; wet nights confounded with habituation position + raise UWB "
                     "dropout (read vs nightly_qc valid_frac); tunnel_present(6/28 only); WISER frame unverified",
    })
    print("\n  " + verdict)
    print(f"\nAll outputs written to: {out}")


if __name__ == "__main__":
    main()
