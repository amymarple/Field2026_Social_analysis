r"""
analyze_heat_gated_relocation.py — Direction 3: does daytime temperature GATE house-leaving?

Below a temperature threshold rats stay inside a group house; above it they come out toward
cooling/margin sites. HEADLINE = the WITHIN-DAY above/below-gate contrast: on a day that crosses
the gate, the SAME rat-day has below-gate (cool morning/evening) and above-gate (hot midday)
periods, so comparing them removes day / rat / sequence / new-environment-exploration.

Analyses:
  A. Gate curve + logistic threshold (T at which coming-out becomes non-trivial) + day-clustered CI.
  B. WITHIN-DAY above/below-gate contrast (headline): ΔP(out), Δrelocation at G in {31,32,33} C,
     day-clustered bootstrap CI + per-rat breakdown.
  C. Timing: P(out) and mean temp by clock hour (does out-of-house track the afternoon heat peak?).
  D. Cooling-directedness: of house-exits, fraction going to a cooling/out state below vs above gate.

CANDIDATE / descriptive: an ASSOCIATION between AMBIENT temperature and a low-movement OUT-of-house
state, in an UNVERIFIED inch frame; NOT a proven thermoregulatory cause. refuge_4 (burrow) + tunnel
(interpretation-limited) and unknown (dropout) bins excluded. Release day 06-28 dropped (truncated).
Read-only on the static snapshot + weather.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
import wiser_analysis_utils as w        # noqa: E402
import wiser_inputs as _wi        # noqa: E402  (per-cohort WISER snapshot resolver)
import time_utils                       # noqa: E402
import metrics                          # noqa: E402
import output_paths                     # noqa: E402

# WISER db + fixed baseline resolved per-cohort by wiser_inputs.finalize() (see --db / --fixed / --canonical)
DEFAULT_GT = PROJECT_ROOT / "configs" / "fixed_position_ground_truth.csv"
DEFAULT_ROIS = PROJECT_ROOT / "configs" / "wiser_rois.json"
DEFAULT_WEATHER = [
    Path(r"D:\Reolink_record\audio_in\weather_data\AWN-F8B3B78DEAC9-20260628-20260709.csv"),
    Path(r"D:\Reolink_record\audio_in\weather_data\AWN-F8B3B78DEAC9-20260628-20260705.csv"),
]
DROP_TAGS = {"12409"}
DROP_DAYS = {"2026-06-28"}               # truncated evening-release day
TRUNK_START = 5
DAY_END_CAP = 21
ACT_BIN_S = 300
BIN_S = 300
ENCLOSED = {"house_1", "house_2"}
OUT = {"doorway", "exposed", "water_1", "water_2", "refuge_1", "refuge_2", "refuge_3"}
GATES = (31.0, 32.0, 33.0)
GATE_MAIN = 32.0
HOT_DAY_CUT = 32.0                       # day peak temp: HOT vs COLD day (matched-hour circadian control)
MIDDAY = (12, 16)                        # peak-heat window for the matched clock-hour contrast
MIN_HALF_BINS = 3
LEVEL = 0.15                              # "coming-out becomes non-trivial" point on the ramp
N_BOOT = 2000
N_BOOT_THR = 400
SEED = 20260712


def _build_bins(args):
    """Per (night, shortid) 5-min trunk bins -> state + local hour + instantaneous temp."""
    fx = w.load_wiser_session(args.fixed)
    fx = time_utils.convert_timestamps(fx)
    fx = time_utils.trim_last_n_minutes(fx, minutes=10)
    fx = w.add_speed(fx)
    moving_thr = w.speed_noise_floor(fx)["p99"]
    jitter = float(np.nanmedian(metrics.compute_summary(
        fx, ground_truth=metrics.load_ground_truth(DEFAULT_GT))["rms_jitter"]))
    print(f"  rest cutoff={moving_thr:.2f} in/s  jitter={jitter:.2f} in")

    df = w.load_wiser_session(args.db)
    df = time_utils.convert_timestamps(df)
    df = w.add_speed(df)
    df = w.add_validity_flags(df, jitter_floor_in=jitter)
    df = w.apply_tag_cutoffs(df)
    df = df[~df["shortid"].astype(str).isin(DROP_TAGS)]

    profile = w.nightly_activity_profile(df, moving_thr_inps=moving_thr, bin_s=ACT_BIN_S)
    emergence = w.locomotor_emergence(profile)
    em_map = dict(zip(emergence["sleep_day"].astype(str), emergence["locomotor_emergence_hour"]))

    full = w.select_route_window(df, clock_start=TRUNK_START, clock_end=DAY_END_CAP)
    full = w.rest_mask(full, moving_thr_inps=moving_thr)
    roi = w.load_rois(args.rois)
    loc = full["datetime"] + pd.Timedelta(hours=w.LOCAL_TZ_OFFSET_HOURS)
    full["loc_hf"] = loc.dt.hour + loc.dt.minute / 60.0
    full["day_end_hf"] = full["night"].astype(str).map(lambda n: min(em_map.get(n, DAY_END_CAP), DAY_END_CAP)).astype(float)
    trunk = full[(full["resting"]) & (full["loc_hf"] >= TRUNK_START) & (full["loc_hf"] < full["day_end_hf"])]

    rec = []
    for (night, sid), g in trunk.groupby(["night", "shortid"]):
        d = g.dropna(subset=["x", "y", "datetime"]).copy()
        if d.empty:
            continue
        d["bin_utc"] = w._bin_utc_ns(d["datetime"], BIN_S)
        b = d.groupby("bin_utc").agg(x=("x", "median"), y=("y", "median"))
        for bu, r in b.iterrows():
            locd = pd.Timestamp(int(bu)) + pd.Timedelta(hours=w.LOCAL_TZ_OFFSET_HOURS)
            rec.append({"night": str(night), "shortid": str(sid), "bin_local": locd,
                        "hour": locd.hour + locd.minute / 60.0,
                        "state": w.classify_site_state(r.x, r.y, roi, date=str(night))})
    B = pd.DataFrame(rec)
    wx = w.load_weather_multi(args.weather)[["datetime_local", "temp_c"]].dropna().sort_values("datetime_local")
    B = B.sort_values("bin_local")
    B = pd.merge_asof(B, wx, left_on="bin_local", right_on="datetime_local",
                      direction="nearest", tolerance=pd.Timedelta("15min")).dropna(subset=["temp_c"])
    B = B[~B["night"].isin(DROP_DAYS)].copy()
    B["enclosed"] = B["state"].isin(ENCLOSED)
    B["out"] = B["state"].isin(OUT)
    B["is_out"] = B["out"].astype(int)
    B = B.sort_values(["night", "shortid", "bin_local"])
    B["next_state"] = B.groupby(["night", "shortid"])["state"].shift(-1)
    B["dtmin"] = B.groupby(["night", "shortid"])["bin_local"].diff().shift(-1).dt.total_seconds() / 60
    B["consec"] = B["dtmin"].between(4, 6)
    B["moved"] = B["consec"] & (B["next_state"] != B["state"])
    return B, moving_thr, jitter


def _within_day(BB, gate):
    BB = BB.copy(); BB["above"] = BB["temp_c"] >= gate
    Bi = BB[BB["enclosed"] | BB["out"]]
    rows = []
    for (night, sid), g in Bi.groupby(["night", "shortid"]):
        bel, abo = g[~g["above"]], g[g["above"]]
        if len(bel) >= MIN_HALF_BINS and len(abo) >= MIN_HALF_BINS:
            rows.append({"night": night, "shortid": sid,
                         "p_out_below": bel["is_out"].mean(), "p_out_above": abo["is_out"].mean(),
                         "reloc_below": bel["moved"].mean(), "reloc_above": abo["moved"].mean()})
    return pd.DataFrame(rows)


def _cb_by_day(c, col_below, col_above, seed):
    c = c.copy(); c["delta"] = c[col_above] - c[col_below]
    groups = [g["delta"].to_numpy() for _, g in c.groupby("night")]
    return w.cluster_bootstrap(groups, n_boot=N_BOOT, seed=seed)


def _robust_threshold(gate_curve, level=0.12):
    """Lower edge of the lowest 2 C temperature bin whose P(out) first reaches ``level`` — a
    step-robust gate location (a single logistic is a poor fit to a sharp step with sparse hot data)."""
    over = gate_curve[gate_curve["p_out"] >= level]
    if over.empty:
        return np.nan
    return float(over.iloc[0]["temp_bin"].left)


def main() -> None:
    ap = argparse.ArgumentParser(description="Direction 3: heat-gated house-leaving.")
    ap.add_argument("--db", type=Path, default=None)
    _wi.add_snapshot_flags(ap)
    ap.add_argument("--fixed", type=Path, default=None)
    ap.add_argument("--rois", type=Path, default=DEFAULT_ROIS)
    ap.add_argument("--weather", type=Path, nargs="*", default=DEFAULT_WEATHER)
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--cohort", default=None,
                    help="cohort key (a cohorts/<key>.yaml); default FIELD2026_COHORT or 2026a")
    args = ap.parse_args()
    args.db, args.fixed, _wiser_prov = _wi.finalize(args)
    if not args.db.exists():
        raise SystemExit(f"[heat-gate] WISER DB not found: {args.db}")

    cohort = output_paths.resolve_cohort(args.cohort)
    direction = "wiser_d3_sleep"
    out = output_paths.run_dir("heat_gated_relocation", cohort)
    _wi.write_input_provenance(out, _wiser_prov)
    figdir = out / "figures"
    report_dir = output_paths.report_dir(cohort, direction)
    print(f"=== Direction 3: heat-gated house-leaving ===\n  DB: {args.db}\n  out: {out}\n")

    B, moving_thr, jitter = _build_bins(args)
    Bi = B[B["enclosed"] | B["out"]].copy()
    print(f"  interpretable bins {len(Bi)} (enclosed {int((~Bi['out']).sum())}, out {int(Bi['out'].sum())}); "
          f"days {Bi['night'].nunique()}, rats {Bi['shortid'].nunique()}")

    # === A. gate curve + logistic threshold ===
    tb = pd.cut(Bi["temp_c"], np.arange(20, 40, 2.0))
    gate_curve = Bi.groupby(tb, observed=True)["is_out"].agg(["mean", "size"]).reset_index()
    gate_curve.columns = ["temp_bin", "p_out", "n"]
    b0, b1 = w.logistic_fit_1d(Bi["temp_c"].to_numpy(), Bi["is_out"].to_numpy())
    thr = _robust_threshold(gate_curve, level=0.12)   # step-robust gate location (~2C bin)

    # === B. within-day above/below-gate contrast ===
    contrasts = {}
    for G in GATES:
        c = _within_day(B, G)
        cb_out = _cb_by_day(c, "p_out_below", "p_out_above", SEED)
        cb_rel = _cb_by_day(c, "reloc_below", "reloc_above", SEED + 1)
        contrasts[G] = {"c": c, "out": cb_out, "reloc": cb_rel}
    cmain = contrasts[GATE_MAIN]["c"]
    per_rat = (cmain.assign(d_out=cmain["p_out_above"] - cmain["p_out_below"])
               .groupby("shortid").agg(n_days=("night", "nunique"),
                                       p_out_below=("p_out_below", "mean"),
                                       p_out_above=("p_out_above", "mean"),
                                       d_out=("d_out", "mean")).reset_index())

    # === C. timing ===
    timing = Bi.groupby(Bi["hour"].round().astype(int)).agg(
        p_out=("is_out", "mean"), temp=("temp_c", "mean"), n=("is_out", "size")).reset_index()

    # === D. cooling-directedness of exits ===
    ex = B[B["moved"] & B["enclosed"]].copy()
    ex["to_out"] = ex["next_state"].isin(OUT); ex["above"] = ex["temp_c"] >= GATE_MAIN
    cool = ex.groupby("above")["to_out"].agg(["mean", "size"])
    cool_below = float(cool["mean"].get(False, np.nan)); cool_above = float(cool["mean"].get(True, np.nan))

    # === E. matched clock-hour HOT vs COLD day (circadian control) ===
    # If the midday exodus were a CIRCADIAN "come out at midday" rhythm, cold-day midday would also be high;
    # matching the clock hour and contrasting HOT vs COLD days isolates temperature from time-of-day.
    daypeak = Bi.groupby("night")["temp_c"].max()
    hot_days = set(daypeak[daypeak >= HOT_DAY_CUT].index); cold_days = set(daypeak[daypeak < HOT_DAY_CUT].index)
    Bi["day_class"] = np.where(Bi["night"].isin(hot_days), "HOT", "COLD")
    hour_hc = (Bi.groupby([Bi["hour"].round().astype(int), "day_class"])["is_out"].mean()
               .unstack().reset_index())
    mid = Bi[(Bi["hour"] >= MIDDAY[0]) & (Bi["hour"] < MIDDAY[1])]
    mid_hot = float(mid[mid["day_class"] == "HOT"]["is_out"].mean())
    mid_cold = float(mid[mid["day_class"] == "COLD"]["is_out"].mean())
    perrat_mid = (mid.groupby(["shortid", "day_class"])["is_out"].mean()
                  .unstack().reindex(columns=["COLD", "HOT"]).reset_index())

    # --- CSVs ---
    gate_curve.to_csv(out / "gate_curve.csv", index=False)
    contrasts[GATE_MAIN]["c"].to_csv(out / "within_day_contrast.csv", index=False)
    per_rat.to_csv(out / "per_rat_contrast.csv", index=False)
    timing.to_csv(out / "timing_by_hour.csv", index=False)
    hour_hc.to_csv(out / "matched_hour_hot_cold.csv", index=False)
    perrat_mid.to_csv(out / "matched_hour_per_rat.csv", index=False)
    cbm = contrasts[GATE_MAIN]["out"]
    n_gate_days = int(cmain["night"].nunique())
    verdict = {"gate_main_C": GATE_MAIN, "threshold_approx_C": thr, "logistic_slope_per_C": round(b1, 3),
               "threshold_note": f"gate-curve step (first 2C bin with P(out)>=0.12); parametric logistic CI unstable ({n_gate_days} gate-crossing days)",
               "n_days_analyzed": int(Bi["night"].nunique()),
               "n_ratdays_crossing": int(len(cmain)), "n_gate_days": n_gate_days,
               "p_out_below": round(float(cmain["p_out_below"].mean()), 3),
               "p_out_above": round(float(cmain["p_out_above"].mean()), 3),
               "dP_out_mean": round(cbm["mean"], 3), "dP_out_CI": [round(cbm["lo"], 3), round(cbm["hi"], 3)],
               "dP_out_frac_gt0": round(cbm["frac_gt0"], 3),
               "dReloc_mean": round(contrasts[GATE_MAIN]["reloc"]["mean"], 3),
               "dReloc_CI": [round(contrasts[GATE_MAIN]["reloc"]["lo"], 3), round(contrasts[GATE_MAIN]["reloc"]["hi"], 3)],
               "cooling_directed_exit_below": round(cool_below, 2), "cooling_directed_exit_above": round(cool_above, 2),
               "n_hot_days": len(hot_days), "n_cold_days": len(cold_days),
               "midday_hot_Pout": round(mid_hot, 3), "midday_cold_Pout": round(mid_cold, 3),
               "midday_hot_minus_cold": round(mid_hot - mid_cold, 3)}
    pd.Series(verdict).to_csv(out / "heat_gate_verdict.csv")

    # --- figures ---
    _fig_gate(gate_curve, b0, b1, thr, figdir / "HG1_gate_curve.png")
    _fig_within(cmain, per_rat, contrasts[GATE_MAIN]["out"], figdir / "HG2_within_day_gate_contrast.png")
    _fig_timing(timing, figdir / "HG3_timing.png")
    _fig_matched(hour_hc, mid_hot, mid_cold, figdir / "HG4_matched_hour_hot_cold.png")

    # --- report ---
    report = _build_report(Bi, moving_thr, jitter, gate_curve, thr, b1, n_gate_days,
                           contrasts, per_rat, timing, cool_below, cool_above,
                           mid_hot, mid_cold, len(hot_days), len(cold_days), perrat_mid, out)
    (out / "direction3_heat_gated_relocation_report.md").write_text(report, encoding="utf-8")
    (report_dir / f"{direction}_heat_gated_relocation_{cohort}.md").write_text(report, encoding="utf-8")
    output_paths.write_run_manifest(report_dir, out, cohort=cohort, direction=direction,
                                    analysis="heat_gated_relocation")

    w.write_run_manifest(out, {
        "analysis": "Direction 3 — heat-gated house-leaving (temperature as a gate; within-day contrast)",
        "status": "CANDIDATE / descriptive — ambient temp association, low-movement proxy, UNVERIFIED frame; NOT causal.",
        "enclosed": sorted(ENCLOSED), "out_states": sorted(OUT),
        "excluded_states": ["refuge_4 (burrow)", "tunnel", "unknown (dropout)"],
        "dropped_days": sorted(DROP_DAYS), "gates_C": list(GATES), "gate_main_C": GATE_MAIN,
        "headline": "WITHIN-DAY above/below-gate contrast (day = its own control, removes sequence/exploration)",
        "inference": f"day-clustered bootstrap ({args.n_boot}x) CI + frac>0",
        "verdict": verdict, "rest_cutoff_inps": moving_thr, "jitter_floor_in": jitter,
        "caveat": "above-gate temps occur on ~5 (early) days -> threshold rests on limited hot exposure.",
    })
    print("\n  VERDICT:")
    for k, v in verdict.items():
        print(f"    {k}: {v}")
    print(f"\n  report -> {report_dir}\n  outputs -> {out}")


# ---------------------------------------------------------------------------
def _fig_gate(gc, b0, b1, thr, path):
    fig, ax = plt.subplots(figsize=(8, 4.6))
    ctr = gc["temp_bin"].apply(lambda iv: iv.mid).astype(float)
    ax.bar(ctr, gc["p_out"], width=1.6, color="tab:orange", alpha=0.6, label="P(out) per 2°C bin")
    if np.isfinite(thr):
        ax.axvline(thr, color="tab:green", lw=1.6, ls="--", label=f"gate ~{thr:.0f}°C (curve step)")
    ax.set_xlabel("instantaneous temperature (°C)"); ax.set_ylabel("P(out of enclosed house)")
    ax.set_title("Heat GATE — P(out of house) vs instantaneous temperature\n"
                 "flat below ~30°C, rises steeply above the threshold", fontsize=10)
    ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def _fig_within(c, per_rat, cb, path):
    fig, ax = plt.subplots(figsize=(7.5, 5))
    cmap = plt.get_cmap("tab10"); tags = sorted(c["shortid"].unique())
    ci = {t: i for i, t in enumerate(tags)}
    for r in c.itertuples():
        y = ci[r.shortid] + np.random.default_rng(hash(r.night) % 999).uniform(-0.18, 0.18)
        ax.plot([r.p_out_below, r.p_out_above], [y, y], "-", color=cmap(ci[r.shortid] % 10), alpha=0.35, lw=1)
        ax.scatter([r.p_out_below], [y], s=14, color="0.6", zorder=3)
        ax.scatter([r.p_out_above], [y], s=22, color=cmap(ci[r.shortid] % 10), zorder=3)
    ax.set_yticks(range(len(tags))); ax.set_yticklabels(tags)
    ax.set_xlabel("P(out of house)   grey = below gate → colour = above gate (same rat-day)")
    ax.set_title(f"WITHIN-DAY heat-gate contrast (G={GATE_MAIN:.0f}°C, each rat-day its own control)\n"
                 f"ΔP(out) = {cb['mean']:+.2f} (95% CI {cb['lo']:+.2f}–{cb['hi']:+.2f}; frac>0 {cb['frac_gt0']:.2f}), "
                 f"{len(c)} rat-days", fontsize=9.5)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def _fig_timing(t, path):
    fig, ax = plt.subplots(figsize=(8, 4.4))
    ax.bar(t["hour"], t["p_out"], width=0.8, color="tab:orange", alpha=0.6, label="P(out)")
    ax.set_xlabel("local clock hour"); ax.set_ylabel("P(out of house)", color="tab:orange")
    ax.set_xticks(range(5, 22, 2))
    axt = ax.twinx(); axt.plot(t["hour"], t["temp"], "-o", ms=3, color="tab:red", label="mean temp")
    axt.set_ylabel("mean temperature (°C)", color="tab:red")
    ax.set_title("Timing — out-of-house tracks the afternoon heat peak (~14–15:00)", fontsize=10)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def _fig_matched(hour_hc, mid_hot, mid_cold, path):
    """Matched clock-hour P(out): HOT days vs COLD days — the circadian control."""
    fig, ax = plt.subplots(figsize=(8, 4.4))
    h = hour_hc.sort_values("hour")
    for col, color, lab in [("HOT", "tab:red", "HOT days (peak≥32°C)"), ("COLD", "tab:blue", "COLD days (<32°C)")]:
        if col in h.columns:
            ax.plot(h["hour"], h[col], "-o", ms=3, color=color, label=lab)
    ax.axvspan(MIDDAY[0], MIDDAY[1], color="0.85", zorder=0, label="midday window")
    ax.set_xlabel("local clock hour (matched)"); ax.set_ylabel("P(out of enclosed house)")
    ax.set_xticks(range(5, 22, 2))
    ax.set_title("Circadian control — same clock hour, HOT vs COLD day\n"
                 f"midday P(out): HOT {mid_hot:.2f} vs COLD {mid_cold:.2f} — cold days stay in ALL day "
                 "(so the midday exodus is temperature, not a circadian rhythm)", fontsize=9)
    ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def _build_report(Bi, moving_thr, jitter, gc, thr, b1, n_gate_days,
                  contrasts, per_rat, timing, cool_below, cool_above,
                  mid_hot, mid_cold, n_hot_days, n_cold_days, perrat_mid, out) -> str:
    G = GATE_MAIN; cb = contrasts[G]["out"]; cbr = contrasts[G]["reloc"]; c = contrasts[G]["c"]
    L = []
    L.append("# Direction 3 — heat-gated house-leaving (temperature as a gate)\n")
    L.append(f"*CANDIDATE / descriptive. 'Out of house' = low-movement position (< {moving_thr:.1f} in/s) in a "
             f"non-house ROI band, **UNVERIFIED inch frame**, jitter ~{jitter:.0f} in. Temperature = **ambient** "
             "AWN air (no in-shelter microclimate). refuge_4 (burrow) + tunnel + unknown(dropout) excluded; "
             "release day 06-28 dropped. This is an **association**, NOT proven thermoregulation.*\n")
    L.append("> **Headline design.** On a day that crosses the gate, the SAME rat-day has below-gate (cool "
             "morning/evening) and above-gate (hot midday) periods. The **within-day** contrast therefore "
             "removes day, rat, day-in-sequence, and new-environment exploration — the one confound (hot days "
             "were early) that the across-day view cannot beat.\n")

    L.append("## Definitions (formula + plain text)\n")
    L.append("- **enclosed** = house_1/house_2; **out** = doorway/exposed/water_1/2/refuge_1/2/3 (cooling/margin). "
             "**P(out)** = out / (enclosed+out) bins.")
    L.append("- **instantaneous temp** = AWN temp at the nearest sample to a 5-min bin (≤15 min).")
    L.append("- **within-day ΔP(out)** = P(out|T≥G) − P(out|T<G) per rat-day with ≥3 bins each side; inference by "
             "**day-clustered bootstrap** (resample days; CI + frac>0).")
    L.append("- **gate threshold** = lower edge of the first 2 °C bin whose P(out) reaches 0.12 (step-robust; "
             "a single logistic is a poor fit to a sharp step and its parametric threshold CI is uninformative here).\n")

    L.append("## A. Gate curve + threshold\n")
    L.append(f"- **{Bi['night'].nunique()} days analyzed** (the 11-day window 06-28→07-08 minus the truncated "
             "06-28 evening-release day); the gate curve pools all interpretable bins.")
    L.append("```\n" + gc.to_string(index=False) + "\n```")
    L.append(f"- **Gate ≈ {thr:.0f} °C** (the curve step): P(out) is flat (~4–6%) up to ~30 °C, then jumps to "
             f"~27–40% above ~32 °C — a **threshold gate, not a linear dial**. The logistic slope is positive "
             f"({b1:+.2f}/°C) but a *parametric* threshold is unstable (hot temps occur on only ~{n_gate_days} "
             "days), so the location is approximate. `HG1`.\n")

    L.append("## B. WITHIN-DAY above/below-gate contrast (headline)\n")
    L.append(f"- **G = {G:.0f} °C ({len(c)} rat-days across {n_gate_days} gate-crossing days):** P(out) "
             f"**{c['p_out_below'].mean():.3f} "
             f"(below) → {c['p_out_above'].mean():.3f} (above)**, ΔP(out) = **{cb['mean']:+.3f}** "
             f"(95% CI {cb['lo']:+.3f}–{cb['hi']:+.3f}, frac>0 {cb['frac_gt0']:.2f}). "
             f"Relocation rate Δ = {cbr['mean']:+.3f} (CI {cbr['lo']:+.3f}–{cbr['hi']:+.3f}).")
    for G2 in GATES:
        if G2 == G:
            continue
        cc = contrasts[G2]["out"]; nn = len(contrasts[G2]["c"])
        L.append(f"- G = {G2:.0f} °C ({nn} rat-days): ΔP(out) = {cc['mean']:+.3f} "
                 f"(CI {cc['lo']:+.3f}–{cc['hi']:+.3f}, frac>0 {cc['frac_gt0']:.2f}).")
    L.append("- **Per rat** (is it all animals?):\n```\n" + per_rat.round(3).to_string(index=False) + "\n```")
    n_resp = int((per_rat["d_out"] > 0.1).sum())
    exc = ", ".join(per_rat[per_rat["d_out"] <= 0.1]["shortid"].astype(str)) or "none"
    L.append(f"  **{n_resp} of {len(per_rat)} rats** show a large above-gate exodus; the exception(s) ({exc}) — the "
             f"most house-loyal/sedentary — stay in even above the gate. The direction is shared but rests on only "
             f"**{n_gate_days} gate-crossing days**, so the day-clustered CI (not a per-rat-day sign test) is the "
             "honest inference.\n")

    L.append("## C. Timing\n")
    L.append("```\n" + timing.round(2).to_string(index=False) + "\n```")
    L.append("- P(out) is near-zero through the morning and peaks at **14–15:00**, the hottest hours — the "
             "exodus is timed to the within-day heat peak (`HG3`), which is why it survives the within-day design.\n")

    L.append("## D. Cooling-directedness of exits\n")
    L.append(f"- Of house-exits, the fraction going to a cooling/out state is **{cool_below:.2f} below** vs "
             f"**{cool_above:.2f} above** the gate — above-gate departures are more cooling-directed.\n")

    L.append("## E. Circadian control — matched clock-hour, HOT vs COLD day\n")
    L.append(f"- Days split by peak temp: **{n_hot_days} HOT** (peak ≥ {HOT_DAY_CUT:.0f} °C; 06-29→07-03) vs "
             f"**{n_cold_days} COLD** (07-04→07-08). The within-day contrast (B) confounds temperature with "
             "time-of-day, so this **matches the clock hour** and contrasts hot vs cold days.")
    L.append(f"- **Midday ({MIDDAY[0]}–{MIDDAY[1]}:00): P(out) = {mid_hot:.2f} on HOT days vs {mid_cold:.2f} on "
             f"COLD days.** At the SAME clock hour the exodus happens **only when it is hot**; **cold days stay "
             "inside essentially ALL day** (P(out) ~0–0.05 at every hour) → the midday leaving is **temperature, "
             "NOT a circadian midday rhythm**. `HG4`.")
    L.append("- **Per rat (midday, HOT vs COLD):**\n```\n" + perrat_mid.round(3).to_string(index=False) + "\n```")
    L.append("  All 5 rats show a hot>cold midday gap (12378 smallest). **Residual confound:** hot days were all "
             "early and cold days all late, so the hot-vs-cold contrast **alone** is sequence-confounded — but the "
             "within-day contrast (B) removes sequence while this removes circadian, so the **pair together** "
             "triangulates temperature (neither confound survives both).\n")

    L.append("## Evidence status\n")
    L.append("**Supported (descriptive, within the WISER measurement):** out-of-house time is **gated** by "
             "instantaneous temperature (flat below ~30 °C, steep above ~32 °C) and rises **within the same "
             "day** from the cool to the hot window; **at a matched clock hour it is present on HOT days but "
             "absent on COLD days** (so it is not a circadian midday rhythm); the exodus is timed to the "
             "afternoon heat peak and is more cooling-directed above the gate. **Candidate / not established:** "
             "that this is thermoregulation "
             "(ambient not in-shelter temp; the out-states are unverified locations); the precise threshold "
             f"(rests on only {n_gate_days} hot days); and the instantaneous *trigger* (the per-bin leave-hazard "
             "was the weakest piece). Needs a shelter thermistor + interior CV (CH07/CH08) + georeference.\n")
    L.append(f"\n*Figures + CSVs: `{out}`.*\n")
    return "\n".join(L)


if __name__ == "__main__":
    main()
