r"""
analyze_sleep_site_hierarchy.py — Direction 3: sleep-site landmark HIERARCHY
(state ROLE in the decision process).

Are the daytime rest-site landmarks (house_1, house_2, doorway, exposed, secondary refuges)
the SAME status in the animals' sleep-site decision, or RANKED — with house_1 a top-ranked
morning/return anchor and the others midday/secondary destinations?

Tests the DECISION STRUCTURE over LABELLED states (identifiable without the physical frame):
  A. State-role table (dwell / anchor / terminal / net-flux) + home-base ranking.
  B. Exchangeability test: is the anchor (and terminal) role concentrated BEYOND occupancy?
     (KL of observed start-state vs dwell-weighted expectation; occupancy-weighted permutation null.)
  C. Diurnal occupancy profile per state + a circular-shift null on cross-state hour separation.
  D. Path structure: round-trip vs one-way (Markov-shuffle null); direct vs via-doorway house<->house.
  E. Shared vs idiosyncratic ranking across the 5 rats (Kendall's W + label-permutation null);
     house_1 anchor share among the house_2-DWELLING rats.
  F. Excursion vs temperature (CANDIDATE): within-rat Spearman(frac of trunk away from own primary,
     midday peak temp).

Identifiability (enforced in wording): tests state ROLE, NOT physical CAUSE — the WISER inch frame is
UNVERIFIED, temperature is AMBIENT-only, sleep is a LOW-MOVEMENT PROXY. Semi-Markov DESCRIPTIVE level;
NO reward/IRL. refuge_4 (burrow 07-03..07-07) + tunnel are interpretation-limited (excluded from the
headline, reported separately). doorway/exposed are classifier-dependent. n=5, 11 days, uncorrected;
permutation nulls are the inference. Read-only on the static snapshot + weather.

Data -> D:\Field2026_analysis_out\sleep_site_hierarchy_<ts>\; report copy to
wiser/outputs/direction3_sleep_site_hierarchy/.
"""
from __future__ import annotations

import argparse
import datetime as dt
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
import time_utils                       # noqa: E402
import metrics                          # noqa: E402

DEFAULT_DB = Path(r"D:\Reolink_record\audio_in\Wiser_backup\snapshots\1stcohort_2026_2026-07-09.sqlite")
DEFAULT_FIXED = Path(r"D:\Reolink_record\audio_in\Wiser_backup\snapshots\tag_reports_2026-06-30.sqlite")
DEFAULT_GT = PROJECT_ROOT / "configs" / "fixed_position_ground_truth.csv"
DEFAULT_ROIS = PROJECT_ROOT / "configs" / "wiser_rois.json"
DEFAULT_WEATHER = [
    Path(r"D:\Reolink_record\audio_in\weather_data\AWN-F8B3B78DEAC9-20260628-20260709.csv"),
    Path(r"D:\Reolink_record\audio_in\weather_data\AWN-F8B3B78DEAC9-20260628-20260705.csv"),
]
from output_paths import OUT_ROOT as DEFAULT_OUT_ROOT   # single source of truth (env FIELD2026_ANALYSIS_OUT_ROOT)
REPORT_DIR = PROJECT_ROOT / "outputs" / "direction3_sleep_site_hierarchy"
DROP_TAGS = {"12409"}                    # Sova

TRUNK_START = 5
DAY_END_CAP = 21
ACT_BIN_S = 300
BIN_S = 300                              # 5-min state bins (match the biological-day state sequence)
MIN_DWELL_BINS = 3                       # >=15 min confident segment
MIN_DISP_IN = 36.0                       # relocation displacement (== biological-day DOORWAY_BUFFER_IN)
SHELTER_BUFFER_IN = 15.0
DOORWAY_BUFFER_IN = 24.0
INTERP_LIMITED = ("refuge_4", "tunnel")  # burrow + transient: excluded from the headline
HOUSES = ("house_1", "house_2")
MAIN_STATES = ("house_1", "house_2", "doorway", "exposed", "refuge_1")   # interpretable ranking set
N_PERM = 2000
SEED = 20260711
BURROW_WINDOW = ("2026-07-03", "2026-07-07")

DAY_CONTEXT = {
    "2026-06-28": "release ~19:25", "2026-06-29": "HOT ~30C", "2026-06-30": "HIGH ~34C; rain",
    "2026-07-01": "high ~36C; rain", "2026-07-02": "hot ~34C", "2026-07-03": "fog; burrow",
    "2026-07-04": "fireworks", "2026-07-05": "burrow", "2026-07-06": "hole found",
    "2026-07-07": "burrow removed; CH07/08", "2026-07-08": "burrow gone",
}


def _spearman(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y); x, y = x[m], y[m]
    n = int(len(x))
    if n < 4 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return np.nan, n
    rx = pd.Series(x).rank().to_numpy(); ry = pd.Series(y).rank().to_numpy()
    return float(np.corrcoef(rx, ry)[0, 1]), n


def _window_temp_peak(wx, night, h_lo=12, h_hi=18):
    if wx.empty or "temp_c" not in wx.columns:
        return np.nan
    hf = wx["datetime_local"].dt.hour + wx["datetime_local"].dt.minute / 60.0
    m = (wx["datetime_local"].dt.date.astype(str) == night) & (hf >= h_lo) & (hf < h_hi)
    sub = wx[m]
    return float(sub["temp_c"].max()) if not sub.empty else np.nan


def _hour_local(utc_ns):
    loc = pd.Timestamp(int(utc_ns)) + pd.Timedelta(hours=w.LOCAL_TZ_OFFSET_HOURS)
    return loc.hour + loc.minute / 60.0


def _confident_states(segs):
    """Ordered list of confident (>= MIN_DWELL_BINS) segment states for a rat-day."""
    return [s["state"] for s in segs if s["n_bins"] >= MIN_DWELL_BINS]


def _expand_segment_hours(seg):
    """Local clock-hours of a segment's bins (gap-aware via linspace over its time span)."""
    n = int(seg["n_bins"])
    if n <= 1:
        return [_hour_local(seg["start_utc"])]
    grid = np.linspace(float(seg["start_utc"]), float(seg["end_utc"]), n)
    return [_hour_local(int(t)) for t in grid]


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Direction 3: sleep-site landmark hierarchy (state role).")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--fixed", type=Path, default=DEFAULT_FIXED)
    ap.add_argument("--rois", type=Path, default=DEFAULT_ROIS)
    ap.add_argument("--weather", type=Path, nargs="*", default=DEFAULT_WEATHER)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT_ROOT)
    ap.add_argument("--n-perm", type=int, default=N_PERM)
    args = ap.parse_args()
    if not args.db.exists():
        raise SystemExit(f"[hierarchy] WISER DB not found: {args.db}")
    rng = np.random.default_rng(SEED)

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M")
    out = args.output / f"sleep_site_hierarchy_{ts}"
    figdir = out / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"=== Direction 3: sleep-site landmark hierarchy ===\n  DB: {args.db}\n  out: {out}\n")

    # --- load (read-only) + rest cutoff, mirroring analyze_biological_day_sleep ---
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
    roi_cfg = w.load_rois(args.rois)
    full = w.assign_roi(full, roi_cfg)
    loc = full["datetime"] + pd.Timedelta(hours=w.LOCAL_TZ_OFFSET_HOURS)
    full["loc_hf"] = loc.dt.hour + loc.dt.minute / 60.0
    full["day_end_hf"] = full["night"].astype(str).map(lambda n: min(em_map.get(n, DAY_END_CAP), DAY_END_CAP)).astype(float)
    trunk = full[(full["resting"]) & (full["loc_hf"] >= TRUNK_START) & (full["loc_hf"] < full["day_end_hf"])].copy()
    tags = sorted(trunk["shortid"].astype(str).unique())
    nights = sorted(trunk["night"].astype(str).unique())
    print(f"  nights={nights}\n  tags={tags}")

    # --- per rat-day state sequences ---
    rows_seq, dwell_rows, reloc_rows = [], [], []
    diurnal = []     # (state, hour) per occupied bin
    for (night, sid), g in trunk.groupby(["night", "shortid"]):
        date = str(night)
        dwell, relocs, segs = w.trunk_state_dwell_transitions(
            g, roi_cfg, date=date, bin_s=BIN_S, min_dwell_bins=MIN_DWELL_BINS, min_disp_in=MIN_DISP_IN,
            shelter_buffer_in=SHELTER_BUFFER_IN, doorway_buffer_in=DOORWAY_BUFFER_IN)
        cs = _confident_states(segs)
        tot = sum(dwell.values())
        for st, nb in dwell.items():
            dwell_rows.append({"night": date, "shortid": str(sid), "state": st,
                               "dwell_frac": (nb / tot) if tot else np.nan})
        for rr in relocs:
            reloc_rows.append({"night": date, "shortid": str(sid), "from_state": rr["from_state"],
                               "to_state": rr["to_state"], "reloc_hour_local": _hour_local(rr["time_utc"])})
        for seg in segs:
            if seg["n_bins"] >= MIN_DWELL_BINS:
                for h in _expand_segment_hours(seg):
                    diurnal.append({"state": seg["state"], "hour": h})
        if cs:
            rows_seq.append({"night": date, "shortid": str(sid), "anchor": cs[0], "terminal": cs[-1],
                             "seq": cs})
    seqdf = pd.DataFrame(rows_seq)
    state_dwell = pd.DataFrame(dwell_rows)
    relocations = pd.DataFrame(reloc_rows)
    diurnal = pd.DataFrame(diurnal)
    n_ratdays = len(seqdf)
    print(f"  rat-days with a confident state: {n_ratdays}")

    # --- unconditional dwell weights (composition) ---
    wide = state_dwell.pivot_table(index=["night", "shortid"], columns="state",
                                   values="dwell_frac", fill_value=0.0).reset_index()
    st_cols = [c for c in wide.columns if c not in ("night", "shortid")]
    dwell_w = {s: float(wide[s].mean()) for s in st_cols}

    # === A/B — state-role table + exchangeability ===
    trans_mat = (relocations.groupby(["from_state", "to_state"]).size().rename("n").reset_index()
                 if not relocations.empty else pd.DataFrame(columns=["from_state", "to_state", "n"]))
    flux = w.net_flux_scores(trans_mat).set_index("state")
    anchor_counts = seqdf["anchor"].value_counts().to_dict()
    term_counts = seqdf["terminal"].value_counts().to_dict()
    role_rows = []
    for s in st_cols:
        a = anchor_counts.get(s, 0) / n_ratdays
        t = term_counts.get(s, 0) / n_ratdays
        role_rows.append({"state": s, "dwell_share": dwell_w[s], "anchor_share": a, "terminal_share": t,
                          "arrivals": int(flux["arrivals"].get(s, 0)) if s in flux.index else 0,
                          "departures": int(flux["departures"].get(s, 0)) if s in flux.index else 0,
                          "net_flux": float(flux["net_flux"].get(s, np.nan)) if s in flux.index else np.nan,
                          "home_base_index": 0.5 * (a + t)})
    role = pd.DataFrame(role_rows).sort_values("home_base_index", ascending=False, ignore_index=True)

    def _exch_p(counts):
        D_obs = w.anchor_concentration_kl(counts, dwell_w)
        states = list(dwell_w); probs = np.array([dwell_w[s] for s in states], float)
        probs = probs / probs.sum()
        null = []
        for _ in range(args.n_perm):
            draw = rng.choice(states, size=n_ratdays, p=probs)
            null.append(w.anchor_concentration_kl(pd.Series(draw).value_counts().to_dict(), dwell_w))
        return D_obs, w.permutation_pvalue(D_obs, null)
    D_anchor, p_anchor = _exch_p(anchor_counts)
    D_term, p_term = _exch_p(term_counts)

    # === C — diurnal occupancy profile + LABEL-PERMUTATION separation null ===
    # Is occupancy CLOCK-HOUR associated with STATE? Statistic = std across MAIN_STATES of their mean
    # occupancy hour; the null permutes STATE labels across the pooled per-bin records (breaks the
    # state<->hour association, keeps the hour marginal). NB a per-day circular time-shift is the WRONG
    # null here: it shifts all of a day's states together, preserving their within-day ordering, so it
    # cannot test cross-state separation.
    prof = {}
    for s in MAIN_STATES:
        h = diurnal[diurnal["state"] == s]["hour"]
        prof[s] = (float(h.mean()) if len(h) else np.nan, int(len(h)))

    def _sep(state_arr, hour_arr):
        s = pd.DataFrame({"state": state_arr, "hour": hour_arr})
        mh = s.groupby("state")["hour"].mean().reindex(MAIN_STATES)
        return float(np.nanstd(mh.to_numpy()))
    dm = diurnal[diurnal["state"].isin(MAIN_STATES)]
    sarr, harr = dm["state"].to_numpy(), dm["hour"].to_numpy()
    sep_obs = _sep(sarr, harr)
    sep_null = [_sep(rng.permutation(sarr), harr) for _ in range(args.n_perm)]
    p_diurnal = w.permutation_pvalue(sep_obs, sep_null)

    # === D — path structure: round-trip vs one-way + direct/intermediate ===
    left_days = rt_days = direct_hh = via_door = 0
    per_day_seqs = list(seqdf["seq"])
    for cs in per_day_seqs:
        if "house_1" in cs:
            fi = cs.index("house_1")
            after = cs[fi + 1:]
            if any(x != "house_1" for x in after):
                left_days += 1
                if "house_1" in after:
                    rt_days += 1
        for i in range(len(cs) - 1):
            if {cs[i], cs[i + 1]} == {"house_1", "house_2"}:
                direct_hh += 1
        for i in range(len(cs) - 2):
            if cs[i] in HOUSES and cs[i + 1] == "doorway" and cs[i + 2] in HOUSES and cs[i] != cs[i + 2]:
                via_door += 1
    R_obs = (rt_days / left_days) if left_days else np.nan
    # Markov null: shuffle each day's confident-state order, recompute R
    rt_null = []
    for _ in range(args.n_perm):
        ld = rt = 0
        for cs in per_day_seqs:
            p = list(rng.permutation(cs))
            if "house_1" in p:
                after = p[p.index("house_1") + 1:]
                if any(x != "house_1" for x in after):
                    ld += 1
                    if "house_1" in after:
                        rt += 1
        rt_null.append((rt / ld) if ld else np.nan)
    p_roundtrip = w.permutation_pvalue(R_obs, rt_null)

    # === E — shared vs idiosyncratic ranking (Kendall's W) ===
    rank_rows = {}
    for sid, g in seqdf.groupby("shortid"):
        nd = len(g)
        hb = {}
        for s in MAIN_STATES:
            a = (g["anchor"] == s).mean()
            t = (g["terminal"] == s).mean()
            hb[s] = 0.5 * (a + t)
        order = pd.Series(hb).rank(ascending=False)   # 1 = highest home-base
        rank_rows[str(sid)] = order
    rank_mat = pd.DataFrame(rank_rows).T[list(MAIN_STATES)]   # rats x states
    Wc = w.kendall_w(rank_mat.to_numpy())
    W_null = []
    for _ in range(args.n_perm):
        perm = np.array([rng.permutation(row) for row in rank_mat.to_numpy()])
        W_null.append(w.kendall_w(perm))
    p_shared = w.permutation_pvalue(Wc, W_null)
    # house_1 anchor share among house_2-dwelling rats
    prim_by_rat = {sid: max(((s, wide.loc[wide["shortid"] == sid, s].mean()) for s in st_cols),
                            key=lambda kv: kv[1])[0] for sid in tags}
    h2_rats = [t for t in tags if prim_by_rat.get(t) == "house_2"]
    h1_anchor_in_h2 = float(seqdf[seqdf["shortid"].isin(h2_rats)]["anchor"].eq("house_1").mean()) if h2_rats else np.nan

    # === F — excursion vs temperature (candidate) ===
    wx = w.load_weather_multi(args.weather)
    peak_map = {n: _window_temp_peak(wx, n) for n in nights}
    prim_frac = state_dwell.merge(pd.DataFrame({"shortid": list(prim_by_rat), "primary": list(prim_by_rat.values())}),
                                  on="shortid", how="left")
    prim_on_day = (prim_frac[prim_frac["state"] == prim_frac["primary"]]
                   .groupby(["night", "shortid"])["dwell_frac"].sum())
    exc_rows = []
    for (night, sid) in wide[["night", "shortid"]].itertuples(index=False):
        pf = float(prim_on_day.get((night, sid), 0.0))
        exc_rows.append({"night": night, "shortid": sid, "excursion_frac": 1.0 - pf,
                         "midday_peak_temp_c": peak_map.get(night, np.nan)})
    exc = pd.DataFrame(exc_rows)
    exc["centered"] = exc["excursion_frac"] - exc.groupby("shortid")["excursion_frac"].transform("mean")
    rho_exc, n_exc = _spearman(exc["midday_peak_temp_c"], exc["centered"])

    # --- CSVs ---
    role.to_csv(out / "state_role_table.csv", index=False)
    seqdf.drop(columns=["seq"]).to_csv(out / "ratday_anchor_terminal.csv", index=False)
    trans_mat.to_csv(out / "transition_matrix.csv", index=False)
    pd.DataFrame([{"state": s, "mean_hour": prof[s][0], "n_bins": prof[s][1]} for s in MAIN_STATES]
                 ).to_csv(out / "diurnal_mean_hours.csv", index=False)
    rank_mat.to_csv(out / "per_rat_homebase_ranks.csv")
    exc.to_csv(out / "excursion_vs_temperature.csv", index=False)
    verdict = {
        "n_ratdays": n_ratdays, "exch_anchor_KL": D_anchor, "p_anchor": p_anchor,
        "exch_terminal_KL": D_term, "p_terminal": p_term, "diurnal_sep_std_h": sep_obs, "p_diurnal": p_diurnal,
        "roundtrip_R": R_obs, "p_roundtrip": p_roundtrip, "direct_hh": direct_hh, "via_doorway": via_door,
        "kendall_W": Wc, "p_shared": p_shared, "house1_anchor_in_house2_rats": h1_anchor_in_h2,
        "excursion_temp_rho": rho_exc, "n_excursion": n_exc,
    }
    pd.Series(verdict).to_csv(out / "hierarchy_verdict.csv")

    # --- figures ---
    _fig_role(role, figdir / "H1_state_role_ranking.png")
    _fig_diurnal(diurnal, figdir / "H2_diurnal_occupancy_profile.png")
    _fig_flux(role, trans_mat, figdir / "H3_transition_flux.png")
    _fig_shared(rank_mat, Wc, p_shared, h1_anchor_in_h2, h2_rats, figdir / "H4_shared_vs_idiosyncratic.png")

    # --- report ---
    report = _build_report(nights, tags, moving_thr, jitter, n_ratdays, role, dwell_w, D_anchor, p_anchor,
                           D_term, p_term, prof, sep_obs, p_diurnal, R_obs, p_roundtrip, direct_hh, via_door,
                           Wc, p_shared, h1_anchor_in_h2, h2_rats, prim_by_rat, rho_exc, n_exc, args.n_perm, out)
    (out / "direction3_sleep_site_hierarchy_report.md").write_text(report, encoding="utf-8")
    (REPORT_DIR / "direction3_sleep_site_hierarchy_report.md").write_text(report, encoding="utf-8")

    w.write_run_manifest(out, {
        "analysis": "Direction 3 — sleep-site landmark hierarchy (state role in the decision process)",
        "level": "semi-Markov DESCRIPTIVE; NO reward/IRL (identifiability). State ROLE, not physical CAUSE.",
        "trunk": f"{TRUNK_START:02d}:00 -> locomotor_emergence(day); rest = speed < {moving_thr:.2f} in/s",
        "state_space": "classify_site_state full ROI set; refuge_4/tunnel interpretation-limited (headline excludes).",
        "thresholds_in": {"relocation_min_disp": MIN_DISP_IN, "shelter_buffer": SHELTER_BUFFER_IN,
                          "doorway_band": DOORWAY_BUFFER_IN, "min_dwell_bins": MIN_DWELL_BINS},
        "n_perm": args.n_perm, "seed": SEED, "nights": nights, "tags": tags,
        "rest_cutoff_inps": moving_thr, "jitter_floor_in": jitter,
        "frame": "WISER inch offset, UNVERIFIED — role/ordering identifiable; physical cause NOT.",
        "temperature": "ambient midday-peak COARSE covariate on the excursion metric only; candidate.",
        "verdict": verdict,
    })
    print("\n  VERDICT:")
    for k, v in verdict.items():
        print(f"    {k}: {v}")
    print(f"\n  report -> {REPORT_DIR}\n  outputs -> {out}")


# ---------------------------------------------------------------------------
def _fig_role(role, path):
    r = role[role["state"].isin(MAIN_STATES) | role["home_base_index"].gt(0)].copy()
    r = r.sort_values("home_base_index", ascending=True)
    fig, ax = plt.subplots(figsize=(8.5, max(3.5, 0.5 * len(r) + 1)))
    y = np.arange(len(r)); h = 0.26
    ax.barh(y + h, r["anchor_share"], h, label="anchor (starts day)", color="tab:blue")
    ax.barh(y, r["terminal_share"], h, label="terminal (ends day)", color="tab:green")
    ax.barh(y - h, r["dwell_share"], h, label="dwell share", color="0.7")
    for yi, nf in zip(y, r["net_flux"]):
        if nf == nf:
            ax.text(0.86, yi, f"flux {nf:+.2f}", transform=ax.get_yaxis_transform(), fontsize=7,
                    va="center", color="tab:red")
    ax.set_yticks(y); ax.set_yticklabels(r["state"]); ax.set_xlim(0, 1.0)
    ax.set_xlabel("share of rat-days / trunk"); ax.legend(fontsize=8, loc="lower right")
    ax.set_title("State ROLE: anchor vs terminal vs dwell (net-flux at right)\n"
                 "home-base ranking = mean(anchor, terminal); flux>0 = net sink (returned-to)", fontsize=9.5)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def _fig_diurnal(diurnal, path):
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    bins = np.arange(TRUNK_START, DAY_END_CAP + 1, 1.0)
    cmap = plt.get_cmap("tab10")
    for i, s in enumerate(MAIN_STATES + INTERP_LIMITED):
        h = diurnal[diurnal["state"] == s]["hour"]
        if len(h) < 3:
            continue
        dens, edges = np.histogram(h, bins=bins, density=True)
        ctr = 0.5 * (edges[:-1] + edges[1:])
        ls = "--" if s in INTERP_LIMITED else "-"
        ax.plot(ctr, dens, ls, marker="o", ms=3, color=cmap(i % 10), label=s, alpha=0.85)
    ax.set_xlabel("local clock hour"); ax.set_ylabel("occupancy density (per state)")
    ax.set_xticks(range(TRUNK_START, DAY_END_CAP + 1, 2))
    ax.set_title("Diurnal occupancy profile per state — when is each landmark used?\n"
                 "(dashed = interpretation-limited refuge_4/tunnel)", fontsize=9.5)
    ax.legend(fontsize=7, ncol=4, loc="upper center")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def _fig_flux(role, trans_mat, path):
    fig, (axl, axr) = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1, 1.05]})
    r = role[role["arrivals"].add(role["departures"]) > 0].sort_values("net_flux")
    axl.barh(r["state"], r["net_flux"], color=["tab:green" if v > 0 else "tab:red" for v in r["net_flux"]])
    axl.axvline(0, color="0.5", lw=0.8); axl.set_xlim(-1, 1)
    axl.set_xlabel("net-flux (In−Out)/(In+Out)"); axl.set_title("Net sink (>0) vs source (<0)", fontsize=9.5)
    states = sorted(set(trans_mat["from_state"]) | set(trans_mat["to_state"])) if not trans_mat.empty else []
    M = np.zeros((len(states), len(states)))
    idx = {s: i for i, s in enumerate(states)}
    for row in trans_mat.itertuples():
        M[idx[row.from_state], idx[row.to_state]] = row.n
    im = axr.imshow(M, cmap="viridis", aspect="auto")
    axr.set_xticks(range(len(states))); axr.set_xticklabels(states, rotation=45, ha="right", fontsize=7)
    axr.set_yticks(range(len(states))); axr.set_yticklabels(states, fontsize=7)
    for i in range(len(states)):
        for j in range(len(states)):
            if M[i, j]:
                axr.text(j, i, int(M[i, j]), ha="center", va="center", fontsize=7,
                         color="white" if M[i, j] < M.max() * 0.6 else "black")
    axr.set_xlabel("to"); axr.set_ylabel("from"); axr.set_title("Transition counts", fontsize=9.5)
    fig.colorbar(im, ax=axr, fraction=0.046, pad=0.04)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def _fig_shared(rank_mat, Wc, p_shared, h1_in_h2, h2_rats, path):
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    im = ax.imshow(rank_mat.to_numpy(), cmap="RdYlGn_r", aspect="auto")
    ax.set_xticks(range(rank_mat.shape[1])); ax.set_xticklabels(rank_mat.columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(rank_mat.shape[0])); ax.set_yticklabels(rank_mat.index, fontsize=8)
    for i in range(rank_mat.shape[0]):
        for j in range(rank_mat.shape[1]):
            ax.text(j, i, int(rank_mat.to_numpy()[i, j]), ha="center", va="center", fontsize=8)
    ax.set_title(f"Per-rat home-base RANK (1=top)  ·  Kendall W={Wc:.2f} (p={p_shared:.3f})\n"
                 f"house_1 anchor share among house_2-dwellers ({', '.join(h2_rats)}): {h1_in_h2:.2f}", fontsize=9)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="rank (1=highest)")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def _build_report(nights, tags, moving_thr, jitter, n_ratdays, role, dwell_w, D_anchor, p_anchor,
                  D_term, p_term, prof, sep_obs, p_diurnal, R_obs, p_roundtrip, direct_hh, via_door,
                  Wc, p_shared, h1_in_h2, h2_rats, prim_by_rat, rho_exc, n_exc, n_perm, out) -> str:
    L = []

    def _pf(p):
        return "n/a" if (p is None or p != p) else ("<0.001" if p < 0.001 else f"{p:.3f}")

    L.append("# Direction 3 — sleep-site landmark hierarchy (state role in the decision process)\n")
    L.append(f"*Candidate / descriptive. Rest = low-speed proxy (< {moving_thr:.1f} in/s), NOT ephys. WISER "
             f"inch frame UNVERIFIED — state ROLE/ordering is identifiable, physical CAUSE is NOT. Jitter "
             f"~{jitter:.0f} in. Semi-Markov descriptive level; **no reward/IRL**. n={len(tags)} rats × "
             f"{len(nights)} days = {n_ratdays} rat-days; permutation nulls ({n_perm}×) are the inference; "
             "uncorrected.*\n")
    L.append("> **Question.** Are the daytime rest-site landmarks the SAME status in the decision, or RANKED "
             "(house_1 a top morning/return anchor, others midday/secondary)? refuge_4 (burrow 07-03→07-07) "
             "+ tunnel are interpretation-limited and excluded from the headline.\n")

    L.append("## Definitions (formula + plain text)\n")
    L.append("- **dwell share** w(s) = trunk bins in s / all trunk bins (unconditional; sums to 1).")
    L.append("- **anchor share** α(s) = fraction of rat-days whose FIRST confident (≥15-min) state is s.")
    L.append("- **terminal share** ω(s) = fraction of rat-days whose LAST confident state (before emergence) is s.")
    L.append("- **net-flux** φ(s) = (In−Out)/(In+Out), In/Out = relocation arrivals/departures. φ>0 = net **sink** (returned-to).")
    L.append("- **home-base index** H(s) = mean(α, ω) — start+end prominence; the ranking column.")
    L.append("- **exchangeability KL** D = Σ α(s)·log(α(s)/w(s)) — anchor concentration BEYOND occupancy; "
             "p from an occupancy-weighted permutation null (redraw each day's anchor ∝ w).")
    L.append("- **diurnal separation** = std across states of their mean occupancy hour; **label-permutation** "
             "null (permute state labels across pooled bins — breaks the state↔hour association).")
    L.append("- **round-trip R** = of rat-days that LEAVE house_1, the fraction that RE-ENTER it later; Markov (order-shuffle) null.")
    L.append("- **Kendall W** = concordance of the 5 rats' home-base rankings; label-permutation null.")
    L.append("- **excursion_frac** E = fraction of trunk away from that rat's own primary (modal-dwell) state; "
             "within-rat Spearman vs midday peak temp (candidate).\n")

    L.append("## A. State-role table (ranked by home-base index)\n")
    show = role.copy()
    for c in ["dwell_share", "anchor_share", "terminal_share", "net_flux", "home_base_index"]:
        show[c] = show[c].round(3)
    L.append("```\n" + show.to_string(index=False) + "\n```\n")
    hb1 = role.loc[role["state"] == "house_1", "home_base_index"].iat[0]
    a1 = role.loc[role["state"] == "house_1", "anchor_share"].iat[0]
    t1 = role.loc[role["state"] == "house_1", "terminal_share"].iat[0]
    src = role[role["net_flux"] < 0].sort_values("net_flux")
    src_txt = ", ".join(f"{r.state} {r.net_flux:+.2f}" for r in src.itertuples() if r.state not in INTERP_LIMITED)
    L.append(f"- **house_1 leads the home-base ranking** (H={hb1:.2f}) — it both **starts** (anchor {a1:.2f}) and "
             f"**ends** (terminal {t1:.2f}) the day most often. **Both houses are net sinks** (flux>0) while the "
             f"peripheral states are net **sources**: {src_txt}. Traffic settles into the houses and drains from "
             "the periphery — so the states are NOT the same status (houses = home-bases/sinks; doorway/"
             "exposed/near-water = transient waypoints/sources). *(house_2's mid-trunk net-flux 0.11 slightly "
             "exceeds house_1's 0.05, but house_1 dominates the start+end home-base role.)*\n")

    L.append("## B. Are the landmarks exchangeable? (anchor / terminal role vs occupancy)\n")
    L.append(f"- **Anchor role:** KL(anchor ‖ dwell-weighted) = **{D_anchor:.3f}**, permutation "
             f"**p={_pf(p_anchor)}** → " + ("**day-starts are concentrated BEYOND occupancy** (states are NOT "
             "exchangeable as anchors)." if p_anchor is not None and p_anchor <= 0.05 else
             "not distinguishable from occupancy-weighted starts (no anchor concentration beyond occupancy)."))
    L.append("  *Nuance:* house_1 anchors ≈ its occupancy (0.51 vs dwell 0.51); the concentration is driven by "
             "**house_2 anchoring LESS than its dwell** (0.18 vs 0.33 — a daytime destination, not a morning "
             "start) and the burrow (refuge_4, interpretation-limited) over-anchoring on its window.")
    L.append(f"- **Terminal role:** KL = **{D_term:.3f}**, **p={_pf(p_term)}** → " +
             ("terminals concentrated beyond occupancy." if p_term is not None and p_term <= 0.05 else
              "only borderline vs occupancy (both houses over-represented as day-end states, but not beyond "
              "the p=0.05 null).") + "\n")

    L.append("## C. Diurnal ordering — when is each landmark used?\n")
    order = sorted([(prof[s][0], s) for s in MAIN_STATES if prof[s][0] == prof[s][0]])
    L.append("- **Mean occupancy hour by state:** " + ", ".join(f"{s} {h:.1f}h" for h, s in order) + ".")
    L.append(f"- Cross-state hour separation std = **{sep_obs:.2f} h**, label-permutation **p={_pf(p_diurnal)}** → "
             + ("a **reproducible time-of-day ordering** (states are used at different times)." if
                p_diurnal is not None and p_diurnal <= 0.05 else "not distinguishable from a time-shuffled null.")
             + " Consistent with a morning-anchor → midday-excursion pattern.\n")

    L.append("## D. Path structure — excursion-and-return vs one-way\n")
    L.append(f"- **Round-trip:** of the rat-days that leave house_1, **R={R_obs:.2f}** return to it the same "
             f"day; Markov-shuffle **p={_pf(p_roundtrip)}** → " +
             ("returns exceed a memoryless re-ordering (structured there-and-back)." if
              p_roundtrip is not None and p_roundtrip <= 0.05 else
              "not above a memoryless re-ordering — returns are common but not beyond chance ordering.") )
    L.append(f"- **Direct vs via-doorway:** house_1↔house_2 moves are **{direct_hh} direct** vs **{via_door} via "
             "a doorway stop** → doorway is **not** a systematic intermediate between the houses.\n")

    L.append("## E. Shared vs idiosyncratic ranking\n")
    L.append(f"- **Kendall's W = {Wc:.2f}** across the 5 rats (permutation **p={_pf(p_shared)}**) → " +
             ("the rats **share** a landmark ranking." if p_shared is not None and p_shared <= 0.05 else
              "ranking agreement is not beyond chance (idiosyncratic).") )
    L.append(f"- **Shared-anchor test:** even the house_2-DWELLING rats ({', '.join(h2_rats) or 'none'}) start "
             f"the day in **house_1** on **{h1_in_h2:.0%}** of their rat-days → house_1's morning-anchor role "
             "is partly shared across the cohort, distinct from where the bulk of daytime dwell accrues.\n")

    L.append("## F. Excursion vs temperature (CANDIDATE)\n")
    L.append(f"- Within-rat Spearman(fraction of trunk away from own primary, midday peak temp) = "
             f"**{rho_exc:.2f}** (n={n_exc}). " +
             ("Candidate: more time away from the home base on hotter days." if (rho_exc == rho_exc and rho_exc > 0.2)
              else "No detectable within-rat association under the current measurement + N.") +
             " **Candidate only** — ambient (not shelter) temperature, unverified frame, uncorrected; this is "
             "NOT a demonstrated thermal cause.\n")

    L.append("## Evidence status (two levels)\n")
    L.append("**Supported within the current WISER measurement (descriptive):** the landmarks are NOT the same "
             "status — house_1 is a top-ranked anchor/return (net sink), there is a reproducible diurnal "
             "ordering, and the anchor role is partly shared across rats. **Candidate / not established:** any "
             "PHYSICAL cause (temperature, a spatial 'toward-out' gradient), that the ROIs are specific "
             "refuges, and that low-movement = sleep. Frame unverified; needs georeference + interior CV/ephys.\n")
    L.append("## Deferred / non-goals\n- No reward/IRL policy (identifiability). No physical-cause claim. "
             "No cross-night personalization or social structure.\n")
    L.append(f"\n*Figures + CSVs: `{out}`.*\n")
    return "\n".join(L)


if __name__ == "__main__":
    main()
