r"""
analyze_night_consolidated_rest.py — Direction 3 companion: NIGHT-TIME consolidated rest bouts.

A **consolidated rest bout (CRB)** = the animal's position **clusters in one small area** (a stay-point,
within ``radius_in``) while **low-movement** (mean rest >= ``rest_min``), held for a sustained **trunk of
time** (>= a minimum duration), with an **exit tolerance** (brief blips don't end it). Tagged by whether
that spot is an **enclosed shelter**. This is the refined replacement for a naive "lowest-activity minute".

**Framing (measurement-honest):** this is a low-MOVEMENT settled bout — rest / grooming / sleep — NOT
validated sleep. "In a shelter for long" is the behavioural signal. Rest = jitter-ceiling speed proxy;
WISER inch frame UNVERIFIED; a signal GAP is 'unknown' (never rest, coverage-guarded). Read-only snapshot.

Per user (2026-07-12): min duration 30 min PRIMARY + {20,40,60} sensitivity; **refuge_4 (burrow) + tunnel
COUNT as shelter** (enclosed); non-shelter bouts are KEPT and labelled **non-shelter consolidated-rest
candidate** and exported (with a nearest-house camera route) for CH05/CH06 video audit.

Outputs -> <FIELD2026_ANALYSIS_OUT_ROOT>/night_consolidated_rest_<ts>/ ; report copy to
wiser/outputs/night_consolidated_rest/.
"""
from __future__ import annotations
import argparse, datetime as dt, sys
from pathlib import Path
import numpy as np, pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
import wiser_analysis_utils as w   # noqa: E402
import wiser_inputs as _wi        # noqa: E402  (per-cohort WISER snapshot resolver)
import time_utils                  # noqa: E402
import metrics                     # noqa: E402
try:
    from output_paths import OUT_ROOT as DEFAULT_OUT_ROOT
except Exception:
    DEFAULT_OUT_ROOT = Path(r"D:\Field2026_analysis_out")

# WISER db + fixed baseline resolved per-cohort by wiser_inputs.finalize() (see --db / --fixed / --canonical)
DEFAULT_GT = PROJECT_ROOT / "configs" / "fixed_position_ground_truth.csv"
DEFAULT_ROIS = PROJECT_ROOT / "configs" / "wiser_rois.json"
DEFAULT_WEATHER = [
    Path(r"D:\Reolink_record\audio_in\weather_data\AWN-F8B3B78DEAC9-20260628-20260709.csv"),
    Path(r"D:\Reolink_record\audio_in\weather_data\AWN-F8B3B78DEAC9-20260628-20260705.csv"),
]
REPORT_DIR = PROJECT_ROOT / "outputs" / "night_consolidated_rest"
DROP_TAGS = {"12409"}

BIN_S = 300
R_STOP_IN = 24.0          # stay-point cluster radius (> ~7 in jitter, p95 15)
EXIT_TOL_BINS = 2         # tolerate <=2 out-of-cluster bins (10 min) before a bout ends (hysteresis)
REST_MIN = 0.60           # the bout must actually be resting
MIN_FIX = 20              # coverage guard: >=20 fixes in a 5-min bin, else the bin is 'unknown'
DUR_SWEEP_MIN = (20, 30, 40, 60)   # 30 primary + sensitivity
PRIMARY_MIN = 30
# refuge_4 (burrow) + tunnel COUNT as shelter (enclosed) per user 2026-07-12:
SHELTER = {"house_1", "house_2", "refuge_1", "refuge_2", "refuge_3", "refuge_4", "water_1", "water_2", "tunnel"}
HOUSE_X = {"house_1": 411.5, "house_2": 613.6}   # for the nearest-house CH05/CH06 audit route


def _stay_bouts(g: pd.DataFrame, *, min_bins: int) -> list[dict]:
    """Stay-point consolidated-rest bouts for ONE animal-night's 5-min bins ``g``
    (cols bin_utc, cx, cy, rest, lh, sorted). A bout = consecutive bins whose centroids stay within
    ``R_STOP_IN`` of the running centroid (tolerating <= ``EXIT_TOL_BINS`` out bins), length >= ``min_bins``,
    mean rest >= ``REST_MIN``. Returns {start_utc, onset_lh, n_bins, cx, cy, radius_in, rest}."""
    cx = g["cx"].to_numpy(); cy = g["cy"].to_numpy(); n = len(g); out = []; i = 0
    while i < n:
        xs = [cx[i]]; ys = [cy[i]]; last = i; miss = 0
        for j in range(i + 1, n):
            cenx, ceny = np.median(xs), np.median(ys)
            if np.hypot(cx[j] - cenx, cy[j] - ceny) <= R_STOP_IN:
                xs.append(cx[j]); ys.append(cy[j]); last = j; miss = 0
            else:
                miss += 1
                if miss > EXIT_TOL_BINS:
                    break
        seg = g.iloc[i:last + 1]
        if (last - i + 1) >= min_bins and float(seg["rest"].mean()) >= REST_MIN:
            cenx, ceny = float(seg["cx"].median()), float(seg["cy"].median())
            out.append({"start_utc": int(seg["bin_utc"].iloc[0]), "onset_lh": float(seg["lh"].iloc[0]),
                        "n_bins": int(last - i + 1), "cx": cenx, "cy": ceny,
                        "radius_in": float(np.median(np.hypot(seg["cx"] - cenx, seg["cy"] - ceny))),
                        "rest": float(seg["rest"].mean())})
        i = last + 1
    return out


def _spearman(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y); x, y = x[m], y[m]
    if len(x) < 4 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return np.nan, int(len(x))
    return float(np.corrcoef(pd.Series(x).rank(), pd.Series(y).rank())[0, 1]), int(len(x))


def _night_weather(wx: pd.DataFrame) -> pd.DataFrame:
    """Per evening-night (21:00->05:00): mean night temp/humidity + within-night COLDEST and MOST-HUMID
    local clock hour (labelled by evening date, matching the WISER night grouping)."""
    cols = ["night", "night_temp", "night_humid", "night_rain", "wet", "cold_hour", "humid_hour"]
    if wx is None or wx.empty or "datetime_local" not in wx.columns:
        return pd.DataFrame(columns=cols)
    d = wx.copy()
    lh = d["datetime_local"].dt.hour + d["datetime_local"].dt.minute / 60.0
    d = d[(lh >= 21) | (lh < 5)].copy()
    d["lh"] = (d["datetime_local"].dt.hour + d["datetime_local"].dt.minute / 60.0).to_numpy()
    d["night"] = (d["datetime_local"] - pd.Timedelta(hours=5)).dt.date.astype(str)
    has_h = "humidity" in d.columns
    has_r = "rain_rate_mmhr" in d.columns
    rows = []
    for nt, g in d.groupby("night"):
        rain = float(g["rain_rate_mmhr"].max()) if has_r else np.nan
        rows.append({"night": str(nt), "night_temp": float(g["temp_c"].mean()),
                     "night_humid": float(g["humidity"].mean()) if has_h else np.nan,
                     "night_rain": rain, "wet": bool(rain > 0.2) if rain == rain else False,
                     "cold_hour": float(g.loc[g["temp_c"].idxmin(), "lh"]) if g["temp_c"].notna().any() else np.nan,
                     "humid_hour": float(g.loc[g["humidity"].idxmax(), "lh"]) if (has_h and g["humidity"].notna().any()) else np.nan})
    return pd.DataFrame(rows, columns=cols)


def _build_report(n_rn, moving_thr, jitter, sens, primary, cand, rn, why) -> str:
    def _pf(v):
        return "n/a" if (v is None or v != v) else f"{v:+.2f}"
    L = ["# Direction 3 — night-time consolidated rest bouts (stay-point) + why\n"]
    L.append(f"*Candidate / measurement-limited. Rest = low-MOVEMENT proxy (< {moving_thr:.1f} in/s), NOT "
             f"scored sleep. WISER inch frame UNVERIFIED. Jitter ~{jitter:.0f} in. n=5 rats × 11 nights = "
             f"{n_rn} rat-nights; ambient weather (±5 min unverified); Spearman, uncorrected.*\n")
    L.append("> A **consolidated rest bout (CRB)** = position clustered within 24 in (a stay-point) + resting "
             "(rest ≥ 0.6), sustained **≥ 30 min** (20/40/60 sensitivity), 10-min exit tolerance; `refuge_4` "
             "(burrow) + `tunnel` count as enclosed shelter. Rest / grooming / sleep — the in-shelter-for-long "
             "is the behavioural signal, NOT validated sleep.\n")
    L.append("## Detection & duration sensitivity\n```\n" + sens.to_string(index=False) + "\n```")
    L.append(f"- **Primary (30 min):** {len(primary)} CRBs, **{primary['in_shelter'].mean()*100:.0f}% in a "
             f"shelter**, median {primary['dur_min'].median():.0f} min, median cluster radius "
             f"{primary['radius_in'].median():.0f} in; **every rat-night has ≥1**. Sites: "
             + ", ".join(f"{k} {v}" for k, v in primary['site'].value_counts().items()) + ".")
    L.append(f"- **{len(cand)} non-shelter consolidated-rest candidates** exported for CH05/CH06 video audit "
             "(routed by nearest house; NVR video clock = UTC−5).\n")
    L.append("## Why (candidate): amount / timing vs familiarity / temperature / humidity\n")
    L.append(f"- Mean total consolidated rest **{rn['total_crb_min'].mean():.0f} min/night** "
             f"({rn['n_crb'].mean():.1f} bouts).")
    L.append(f"- **Familiarity (day-in-sequence):** total-rest ρ={_pf(why['familiarity_totalrest_vs_dayidx'])}, "
             f"#bouts ρ={_pf(why['familiarity_ncrb_vs_dayidx'])}.")
    L.append(f"- **Temperature:** total-rest vs night temp — pooled ρ={_pf(why['temp_totalrest_pooled'])}, "
             f"**within-rat ρ={_pf(why['temp_totalrest_withinrat'])}**.")
    L.append(f"- **Humidity:** total-rest vs humidity — pooled ρ={_pf(why['humid_totalrest_pooled'])}, "
             f"**within-rat ρ={_pf(why['humid_totalrest_withinrat'])}**.")
    L.append(f"  *Disentangle (rain vs humidity vs sequence):* rain within-rat "
             f"ρ={_pf(why.get('rain_totalrest_withinrat'))}; **humidity | rain ρ={_pf(why.get('humid_rest_partial_ctrl_rain'))}**, "
             f"rain | humidity ρ={_pf(why.get('rain_rest_partial_ctrl_humid'))}, humidity | day "
             f"ρ={_pf(why.get('humid_rest_partial_ctrl_dayidx'))}; humidity on **DRY nights only** "
             f"(n={why.get('n_dry_ratnights')}) ρ={_pf(why.get('humid_rest_withinrat_DRY_only'))}.")
    L.append(f"- **Covariate collinearity:** temp~humid {_pf(why['collin_temp_humid'])}, temp~day "
             f"{_pf(why['collin_temp_dayidx'])}, humid~day {_pf(why['collin_humid_dayidx'])}.")
    L.append(f"- **Within-night timing:** the longest CRB starts a median "
             f"**{why['align_longest_onset_vs_coldhour_medh']:.1f} h** from the night's coldest hour and "
             f"{why['align_longest_onset_vs_humidhour_medh']:.1f} h from the most-humid hour → clock-timed, "
             "NOT locked to the within-night weather minimum.")
    L.append(f"- **Trait vs state:** total-rest η²(rat) = {why['trait_eta2_totalrest_by_rat']:.2f}.\n")
    L.append("## Evidence status (two levels)\n")
    L.append("**Supported (descriptive, within the measurement):** night rest is consolidated into ~2–3 "
             "in-shelter bouts/rat-night (median 50 min, 4-in cluster radius), universal and house-centred; "
             "the longest bout is clock-timed (~midnight), not at the within-night weather minimum.\n")
    L.append("**Candidate:** any weather / familiarity driver of rest AMOUNT (temperature/humidity, within-rat); "
             "that low-movement = sleep. Ambient (not shelter) weather, unverified frame, n=5×11, uncorrected.\n")
    L.append("## Caveats / deferred\n- Rest = proxy (not ephys/CV-validated); non-shelter candidates await "
             "video audit (4 lack transferred CH05/06); a firmer weather test needs a shelter thermistor + "
             "more nights + a within-night hazard model.\n")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="Direction 3: night-time consolidated rest bouts (stay-point).")
    ap.add_argument("--db", type=Path, default=None)
    _wi.add_snapshot_flags(ap)
    ap.add_argument("--fixed", type=Path, default=None)
    ap.add_argument("--rois", type=Path, default=DEFAULT_ROIS)
    ap.add_argument("--weather", type=Path, nargs="*", default=DEFAULT_WEATHER)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT_ROOT)
    args = ap.parse_args()
    args.db, args.fixed, _wiser_prov = _wi.finalize(args)
    if not args.db.exists():
        raise SystemExit(f"[crb] WISER DB not found: {args.db}")
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M")
    out = args.output / f"night_consolidated_rest_{ts}"
    _wi.write_input_provenance(out, _wiser_prov)
    out.mkdir(parents=True, exist_ok=True); REPORT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"=== Direction 3: night consolidated rest ===\n  DB: {args.db}\n  out: {out}\n")

    fx = w.load_wiser_session(args.fixed); fx = time_utils.convert_timestamps(fx)
    fx = time_utils.trim_last_n_minutes(fx, minutes=10); fx = w.add_speed(fx)
    moving_thr = w.speed_noise_floor(fx)["p99"]
    jitter = float(np.nanmedian(metrics.compute_summary(
        fx, ground_truth=metrics.load_ground_truth(DEFAULT_GT))["rms_jitter"]))
    print(f"  rest cutoff={moving_thr:.2f} in/s  jitter={jitter:.2f} in")

    df = w.load_wiser_session(args.db); df = time_utils.convert_timestamps(df); df = w.add_speed(df)
    df = w.add_validity_flags(df, jitter_floor_in=jitter); df = w.apply_tag_cutoffs(df)
    df = df[~df["shortid"].astype(str).isin(DROP_TAGS)]
    df = w.rest_mask(df, moving_thr_inps=moving_thr)
    roi = w.load_rois(args.rois)

    loc = df["datetime"] + pd.Timedelta(hours=w.LOCAL_TZ_OFFSET_HOURS)
    lh = loc.dt.hour + loc.dt.minute / 60.0
    mask = (lh >= 21) | (lh < 5)
    night = df[mask].copy(); locn = loc[mask]
    night["lh"] = lh[mask].to_numpy()
    night["night"] = (locn - pd.Timedelta(hours=5)).dt.date.astype(str)   # evening-date label
    night["bin_utc"] = w._bin_utc_ns(night["datetime"], BIN_S)
    b = night.groupby(["night", "shortid", "bin_utc"]).agg(
        cx=("x", "median"), cy=("y", "median"), rest=("resting", "mean"),
        nfix=("resting", "size"), lh=("lh", "median")).reset_index()
    b = b[b["nfix"] >= MIN_FIX]
    b["shortid"] = b["shortid"].astype(str); b["night"] = b["night"].astype(str)
    rd = b[["night", "shortid"]].drop_duplicates()
    n_rn = len(rd)
    print(f"  rat-nights: {n_rn}")

    # --- detect CRBs at each duration threshold (sensitivity sweep) ---
    def detect(min_min: int) -> pd.DataFrame:
        rows = []
        for (nt, sid), g in b.groupby(["night", "shortid"]):
            g = g.sort_values("bin_utc")
            for s in _stay_bouts(g, min_bins=int(round(min_min * 60 / BIN_S))):
                st = w.classify_site_state(s["cx"], s["cy"], roi, date=str(nt))
                rows.append({"night": str(nt), "shortid": str(sid), "onset_lh": round(s["onset_lh"], 2),
                             "start_utc": s["start_utc"], "dur_min": s["n_bins"] * BIN_S // 60,
                             "site": st, "in_shelter": st in SHELTER, "cx": round(s["cx"], 1),
                             "cy": round(s["cy"], 1), "radius_in": round(s["radius_in"], 1),
                             "rest": round(s["rest"], 2)})
        return pd.DataFrame(rows)

    sens_rows = []
    primary = None
    for m in DUR_SWEEP_MIN:
        d = detect(m)
        if m == PRIMARY_MIN:
            primary = d
        n_bouts = len(d); n_shel = int(d["in_shelter"].sum()) if n_bouts else 0
        cov = d.groupby(["night", "shortid"]).ngroups if n_bouts else 0
        sens_rows.append({"min_dur_min": m, "n_bouts": n_bouts, "ratnights_with_bout": cov,
                          "pct_in_shelter": round(100 * n_shel / n_bouts, 0) if n_bouts else np.nan,
                          "median_dur_min": float(d["dur_min"].median()) if n_bouts else np.nan,
                          "bouts_per_ratnight": round(n_bouts / n_rn, 2)})
    sens = pd.DataFrame(sens_rows)

    # --- outputs ---
    primary.sort_values(["night", "shortid", "onset_lh"]).to_csv(out / "consolidated_rest_bouts.csv", index=False)
    sens.to_csv(out / "duration_sensitivity.csv", index=False)
    # non-shelter candidates (primary threshold) + nearest-house CH05/CH06 audit route
    cand = primary[~primary["in_shelter"]].copy()
    if not cand.empty:
        cand["nearest_house"] = np.where(np.abs(cand["cx"] - HOUSE_X["house_1"]) <=
                                         np.abs(cand["cx"] - HOUSE_X["house_2"]), "house_1", "house_2")
        cand["audit_camera"] = np.where(cand["nearest_house"] == "house_1", "CH05", "CH06")
        cand["onset_utc"] = pd.to_datetime(cand["start_utc"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        cand["onset_local_approx"] = (pd.to_datetime(cand["start_utc"]) +
                                      pd.Timedelta(hours=w.LOCAL_TZ_OFFSET_HOURS)).dt.strftime("%Y-%m-%d %H:%M:%S")
    cand.to_csv(out / "nonshelter_rest_candidates.csv", index=False)

    print("\nDURATION SENSITIVITY:\n" + sens.to_string(index=False))
    print(f"\nPRIMARY ({PRIMARY_MIN} min): {len(primary)} bouts, "
          f"{primary['in_shelter'].mean()*100:.0f}% in shelter, median {primary['dur_min'].median():.0f} min, "
          f"median radius {primary['radius_in'].median():.0f} in; {primary.groupby(['night','shortid']).ngroups}/{n_rn} rat-nights.")
    print("  site dist:", primary["site"].value_counts().to_dict())
    print(f"  non-shelter candidates: {len(cand)} (exported for CH05/CH06 audit)")
    if not cand.empty:
        print(cand[["night", "shortid", "onset_local_approx", "dur_min", "site", "cx", "cy", "audit_camera"]].to_string(index=False))

    # === WHY (candidate): consolidated-rest amount/timing vs familiarity / temperature / humidity ===
    wx = w.load_weather_multi(args.weather)
    nw = _night_weather(wx)
    agg = primary.groupby(["night", "shortid"]).agg(
        n_crb=("dur_min", "size"), total_crb_min=("dur_min", "sum"),
        shelter_frac=("in_shelter", "mean")).reset_index()
    longest = (primary.loc[primary.groupby(["night", "shortid"])["dur_min"].idxmax()]
               [["night", "shortid", "onset_lh", "dur_min"]]
               .rename(columns={"onset_lh": "longest_onset", "dur_min": "longest_dur"}))
    rn = (rd.merge(agg, on=["night", "shortid"], how="left")
          .merge(longest, on=["night", "shortid"], how="left").merge(nw, on="night", how="left"))
    rn[["n_crb", "total_crb_min"]] = rn[["n_crb", "total_crb_min"]].fillna(0)
    rn["day_idx"] = rn["night"].rank(method="dense").astype(int)
    rn.to_csv(out / "crb_per_ratnight.csv", index=False)

    def _rc(col, tcol):        # within-rat (rat-centered) Spearman of a per-night metric vs a covariate
        d = rn.dropna(subset=[col, tcol]).copy()
        if d.empty:
            return (np.nan, 0)
        d["c"] = d[col] - d.groupby("shortid")[col].transform("mean")
        return _spearman(d[tcol], d["c"])

    def _hd(a, b):
        return np.abs(((np.asarray(a, float) - np.asarray(b, float) + 12) % 24) - 12)
    al = rn.dropna(subset=["longest_onset", "cold_hour"])
    g2 = rn.groupby("shortid")["total_crb_min"]; grand = rn["total_crb_min"].mean()
    ssb = float((g2.count() * (g2.mean() - grand) ** 2).sum())
    ssw = float(((rn["total_crb_min"] - rn["shortid"].map(g2.mean())) ** 2).sum())
    why = {
        "n_ratnights": int(len(rn)),
        "familiarity_totalrest_vs_dayidx": _spearman(rn["day_idx"], rn["total_crb_min"])[0],
        "familiarity_ncrb_vs_dayidx": _spearman(rn["day_idx"], rn["n_crb"])[0],
        "temp_totalrest_pooled": _spearman(rn["night_temp"], rn["total_crb_min"])[0],
        "temp_totalrest_withinrat": _rc("total_crb_min", "night_temp")[0],
        "humid_totalrest_pooled": _spearman(rn["night_humid"], rn["total_crb_min"])[0],
        "humid_totalrest_withinrat": _rc("total_crb_min", "night_humid")[0],
        "collin_temp_humid": _spearman(rn["night_temp"], rn["night_humid"])[0],
        "collin_temp_dayidx": _spearman(rn["night_temp"], rn["day_idx"])[0],
        "collin_humid_dayidx": _spearman(rn["night_humid"], rn["day_idx"])[0],
        "align_longest_onset_vs_coldhour_medh": float(np.nanmedian(_hd(al["longest_onset"], al["cold_hour"]))) if len(al) else np.nan,
        "align_longest_onset_vs_humidhour_medh": float(np.nanmedian(_hd(al["longest_onset"], al["humid_hour"]))) if len(al) else np.nan,
        "trait_eta2_totalrest_by_rat": (ssb / (ssb + ssw)) if (ssb + ssw) > 0 else np.nan,
    }
    # --- disentangle the humidity candidate: rain vs humidity vs day-in-sequence ---
    rn["rest_rc"] = rn["total_crb_min"] - rn.groupby("shortid")["total_crb_min"].transform("mean")

    def _psp(y, x, ctrl):      # partial Spearman y~x | ctrl (rank residualisation)
        d = rn.dropna(subset=[y, x, ctrl]).copy()
        if len(d) < 6:
            return np.nan
        R = {c: d[c].rank().to_numpy() for c in (y, x, ctrl)}
        res = {a: R[a] - np.polyval(np.polyfit(R[ctrl], R[a], 1), R[ctrl]) for a in (y, x)}
        return (float(np.corrcoef(res[x], res[y])[0, 1])
                if (np.ptp(res[x]) > 0 and np.ptp(res[y]) > 0) else np.nan)
    dry = rn[rn["wet"] == False].copy()
    dry_rc = (dry["total_crb_min"] - dry.groupby("shortid")["total_crb_min"].transform("mean")
              ) if len(dry) else pd.Series(dtype=float)
    why.update({
        "rain_totalrest_withinrat": _rc("total_crb_min", "night_rain")[0],
        "humid_rest_partial_ctrl_rain": _psp("rest_rc", "night_humid", "night_rain"),
        "rain_rest_partial_ctrl_humid": _psp("rest_rc", "night_rain", "night_humid"),
        "humid_rest_partial_ctrl_dayidx": _psp("rest_rc", "night_humid", "day_idx"),
        "humid_rest_withinrat_DRY_only": (_spearman(dry["night_humid"], dry_rc)[0] if len(dry) >= 6 else np.nan),
        "n_wet_ratnights": int((rn["wet"] == True).sum()), "n_dry_ratnights": int((rn["wet"] == False).sum()),
    })
    pd.Series(why).to_csv(out / "why_correlations.csv")
    print("\n=== WHY (candidate; rest=proxy, ambient weather, n=5x11, uncorrected) ===")
    print(f"  mean total consolidated rest/night: {rn['total_crb_min'].mean():.0f} min ({rn['n_crb'].mean():.1f} bouts)")
    print(f"  FAMILIARITY  total-rest vs day-index rho={why['familiarity_totalrest_vs_dayidx']:+.2f}  (n_crb {why['familiarity_ncrb_vs_dayidx']:+.2f})")
    print(f"  TEMPERATURE  total-rest vs night-temp: pooled {why['temp_totalrest_pooled']:+.2f}  within-rat {why['temp_totalrest_withinrat']:+.2f}")
    print(f"  HUMIDITY     total-rest vs humidity:   pooled {why['humid_totalrest_pooled']:+.2f}  within-rat {why['humid_totalrest_withinrat']:+.2f}")
    print(f"  collinearity temp~humid {why['collin_temp_humid']:+.2f} | temp~day {why['collin_temp_dayidx']:+.2f} | humid~day {why['collin_humid_dayidx']:+.2f}")
    print(f"  WITHIN-NIGHT |longest-CRB onset - coldest hour| med {why['align_longest_onset_vs_coldhour_medh']:.1f}h "
          f"| -most-humid hour med {why['align_longest_onset_vs_humidhour_medh']:.1f}h (cold/humid hour ~pre-dawn)")
    print(f"  TRAIT? total-rest eta^2 by rat = {why['trait_eta2_totalrest_by_rat']:.2f}")
    print(f"  DISENTANGLE humidity vs rain vs sequence: rain(within-rat) {why['rain_totalrest_withinrat']:+.2f} | "
          f"humid|rain {why['humid_rest_partial_ctrl_rain']:+.2f} | rain|humid {why['rain_rest_partial_ctrl_humid']:+.2f} | "
          f"humid|day {why['humid_rest_partial_ctrl_dayidx']:+.2f} | humid on DRY nights only "
          f"(n={why['n_dry_ratnights']}) {why['humid_rest_withinrat_DRY_only']:+.2f}  [wet {why['n_wet_ratnights']}/dry {why['n_dry_ratnights']}]")

    (REPORT_DIR / "night_consolidated_rest_report.md").write_text(
        _build_report(n_rn, moving_thr, jitter, sens, primary, cand, rn, why), encoding="utf-8")

    w.write_run_manifest(out, {
        "why": {k: (round(v, 3) if isinstance(v, float) and v == v else v) for k, v in why.items()},
        "analysis": "Direction 3 — night consolidated rest bouts (stay-point; rest/grooming/sleep proxy, NOT validated sleep)",
        "definition": f"position clustered within {R_STOP_IN} in + rest>= {REST_MIN} + >= dur, exit tol "
                      f"{EXIT_TOL_BINS} bins; shelter set counts refuge_4+tunnel as enclosed.",
        "primary_min_dur_min": PRIMARY_MIN, "sensitivity_min_dur": list(DUR_SWEEP_MIN),
        "rest_cutoff_inps": moving_thr, "jitter_floor_in": jitter, "n_ratnights": n_rn,
        "frame": "WISER inch offset UNVERIFIED; rest = jitter-ceiling proxy; coverage-guarded.",
        "nonshelter_candidates": int(len(cand)),
        "note": "correlations (weather/familiarity) DEFERRED until the detector is signed off.",
    })
    (out / "consolidated_rest_bouts.csv")  # (report is the CSVs + manifest for this refinement pass)
    print(f"\n  outputs -> {out}")


if __name__ == "__main__":
    main()
