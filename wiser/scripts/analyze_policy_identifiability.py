r"""
analyze_policy_identifiability.py — Phase-1 modeling (run under the anaconda3 interpreter).

Reads the decision tables from build_decision_tables.py and runs the identifiability ladder:
audits A0-A2, nested models M1-M5 (leaving hazard), a memory check, matched-choice, the
transfer audit, and the reward-feasibility verdict. Writes CSVs + a report with formula+text
Definitions. All significance at the NIGHT-block level (~8 nights); primary loss bits/decision.

    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\analyze_policy_identifiability.py
    C:\Users\Cornell\anaconda3\python.exe scripts\analyze_policy_identifiability.py --fast   # fewer perms
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import choice_models as cm                            # noqa: E402
from environment_map import EnvironmentMap            # noqa: E402

# --- leaving-hazard feature sets (frame-invariant) ---
DWELL = "dwell_elapsed_s"
M1_NUM = ["dist_to_edge_in", "clock_hour", "moving_frac", "wet", "fireworks", "burrow"]
M1_CAT = ["roi"]
WEATHER = ["w_temp_c", "w_tempdew_gap_c", "w_rain_log1p", "w_solar_wm2"]
M2_NUM = M1_NUM + WEATHER
ID_FEATURES = ["is_house", "is_refuge", "is_water"]
SOCIAL = ["nn_dist_in", "n_within_1m", "mean_others_dist_in"]
SOCIAL_SAFE = ["n_within_1m", "mean_others_dist_in"]   # jitter-floor-safe (drop sub-floor nn_dist_in)


def add_shared_use(df: pd.DataFrame) -> pd.DataFrame:
    """Leave-focal-OUT shared-use hazard: pooled P(left | roi, dwell-tercile) estimated from the
    OTHER animals. An ANIMAL-DERIVED behavioral feature (trails/habit), NOT environment; a gain
    over M2 (explicit layout+weather) signals emergent shared use. (Global leave-focal-out, a
    disclosed mild optimism vs strict per-fold; the individual/social arms remain per-fold.)"""
    d = df.copy()
    d["_dwell_t"] = pd.qcut(d[DWELL].rank(method="first"), 3, labels=False, duplicates="drop")
    key = ["roi", "_dwell_t"]
    tot = d.groupby(key)["left"].agg(["sum", "count"])
    vals = []
    for _, r in d.iterrows():
        k = (r["roi"], r["_dwell_t"])
        s, c = tot.loc[k] if k in tot.index else (np.nan, np.nan)
        # remove the focal row's own contribution (leave-one-out within the stratum)
        vals.append((s - r["left"]) / (c - 1) if c and c > 1 else np.nan)
    d["shareduse_hazard"] = vals
    return d.drop(columns=["_dwell_t"])


def marginal_bits(df, y="left"):
    """Held-out marginal (intercept-only) bits, leave-one-night-out."""
    return cm.lono_bits(df, y, numeric=(), categorical=(), dwell_col=None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path,
                    default=ROOT / "outputs/policy_identifiability_2026-06-28_to_2026-07-08")
    ap.add_argument("--env-map", type=Path,
                    default=ROOT / "configs/environment_map/2026-06-28_to_2026-07-08.yaml")
    ap.add_argument("--rois", type=Path, default=ROOT / "configs/wiser_rois.json")
    ap.add_argument("--fast", action="store_true", help="fewer permutations (smoke)")
    ap.add_argument("--config-id", default="", help="provenance identifier for the decision unit "
                    "(e.g. 'hysteretic_buf14_exit30_ep15') — stamped into the report + json")
    args = ap.parse_args()
    n_perm = 20 if args.fast else 60
    d = args.dir
    leave = pd.read_csv(d / "leave_decisions.csv")
    dest = pd.read_csv(d / "destination_decisions.csv")
    audit = pd.read_csv(d / "measurement_process_audit.csv") if (d / "measurement_process_audit.csv").exists() else pd.DataFrame()
    em = EnvironmentMap.from_paths(args.env_map, args.rois)
    R = {}

    # ------------------------------------------------------------------ A0
    print("[A0] decision-table validity & support")
    nights = sorted(leave["night"].unique())
    per_an = leave.groupby(["night", "shortid"]).size().rename("leave_epochs").reset_index()
    dep_an = dest.groupby(["night", "shortid"]).size().rename("departures").reset_index()
    # comparable-state strata: (roi, dwell tercile); count animal-nights with >= 15 epochs
    lv = leave.copy()
    lv["dwell_t"] = pd.qcut(lv[DWELL].rank(method="first"), 3, labels=False, duplicates="drop")
    strata = lv.groupby(["roi", "dwell_t", "shortid", "night"]).size().rename("n").reset_index()
    comparable = strata[strata["n"] >= 15]
    n_comparable_cells = int(len(comparable))
    n_strata_multi_animal = int(comparable.groupby(["roi", "dwell_t", "night"])["shortid"].nunique().ge(2).sum())
    A0_ok = n_strata_multi_animal >= 5
    R["A0"] = {"nights": nights, "n_leave_epochs": int(len(leave)), "n_departures": int(len(dest)),
               "leave_epochs_per_animal_night": per_an["leave_epochs"].describe().to_dict(),
               "n_comparable_cells": n_comparable_cells,
               "n_strata_with_>=2_animals": n_strata_multi_animal,
               "individual_arm_state_coverage": A0_ok,
               "power_note": "A0 confirms STATE COVERAGE (comparable cross-night same-state decisions), "
               "NOT statistical power; ~8 night-blocks under whole-night holdout under-power a small "
               "(<0.003 bit) effect, so a NO-GO is a lower bound on effect size, not exact zero."}
    per_an.to_csv(d / "A0_support_per_animal_night.csv", index=False)
    print(f"     leave_epochs={len(leave)} departures={len(dest)} "
          f"multi-animal comparable strata={n_strata_multi_animal} -> individual arm "
          f"{'SUPPORTED' if A0_ok else 'UNDERPOWERED'}")

    # ------------------------------------------------------------------ A1
    R["A1"] = em.registration_note()
    R["A1"]["allowed"] = "topology + coarse distances (>= min_resolvable_distance_in); NO fine metric distance, NO absolute direction"
    print(f"[A1] registration: {R['A1']['status']} (transform {R['A1']['physical_transform']}); "
          f"min resolvable {R['A1']['min_resolvable_distance_in']} in")

    # ------------------------------------------------------------------ A2
    if not audit.empty:
        hi = audit.sort_values("gap_frac", ascending=False).head(5)
        R["A2"] = {"valid_frac_range": [float(audit["valid_frac"].min()), float(audit["valid_frac"].max())],
                   "gap_frac_range": [float(audit["gap_frac"].min()), float(audit["gap_frac"].max())],
                   "jitter_proxy_range_inps": [float(audit["jitter_proxy_inps"].min()),
                                               float(audit["jitter_proxy_inps"].max())],
                   "highest_dropout_strata": hi.to_dict("records")}
        print(f"[A2] valid_frac {R['A2']['valid_frac_range']}, gap_frac {R['A2']['gap_frac_range']}")
    else:
        R["A2"] = {}

    # ------------------------------------------------------------------ M0-M3 (nested bits)
    print("[M1-M3] nested leaving-hazard models (held-out bits/decision)")
    leave3 = add_shared_use(leave)
    m0 = marginal_bits(leave)
    m1 = cm.lono_bits(leave, "left", numeric=M1_NUM, categorical=M1_CAT, dwell_col=DWELL)
    m2 = cm.lono_bits(leave, "left", numeric=M2_NUM, categorical=M1_CAT, dwell_col=DWELL)
    m3 = cm.lono_bits(leave3, "left", numeric=M2_NUM + ["shareduse_hazard"], categorical=M1_CAT, dwell_col=DWELL)

    def allbits(t):
        return float(t[t.animal == "ALL"]["bits"].mean())
    H0, H1, H2, H3 = allbits(m0), allbits(m1), allbits(m2), allbits(m3)
    R["nested"] = {
        "H_marginal_bits": H0, "H_M1_layout_bits": H1, "H_M2_plusweather_bits": H2,
        "H_M3_plussharedus_bits": H3,
        "skill_M1_vs_marginal": cm.skill(H1, H0), "dbits_weather_M1_to_M2": H1 - H2,
        "dbits_shareduse_M2_to_M3": H2 - H3}
    print(f"     H: marginal={H0:.3f} M1={H1:.3f} M2={H2:.3f} M3={H3:.3f} bits "
          f"(skill M1={cm.skill(H1,H0):.3f}, weather Dbits={H1-H2:.4f}, shared-use Dbits={H2-H3:.4f})")

    # ------------------------------------------------------------------ memory check
    print("[memory] history (previous-visit resource type) beyond dwell")
    vis = pd.read_csv(d / "visits.csv") if (d / "visits.csv").exists() else pd.DataFrame()
    mem_dbits = np.nan
    if not vis.empty:
        vis = vis.sort_values(["shortid", "night", "visit_id"])
        vis["prev_roi"] = vis.groupby(["shortid", "night"])["roi"].shift(1).fillna("none")
        lv_m = leave.merge(vis[["shortid", "night", "visit_id", "prev_roi"]],
                           on=["shortid", "night", "visit_id"], how="left")
        lv_m["prev_roi"] = lv_m["prev_roi"].fillna("none")
        mm = cm.lono_bits(lv_m, "left", numeric=M2_NUM, categorical=M1_CAT + ["prev_roi"], dwell_col=DWELL)
        mem_dbits = H2 - allbits(mm)
    R["memory"] = {"dbits_history_over_M2": float(mem_dbits) if mem_dbits == mem_dbits else None,
                   "observed_state_markov_ok": bool(mem_dbits < 0.01) if mem_dbits == mem_dbits else None}
    print(f"     history Dbits over M2 = {mem_dbits:.4f} -> "
          f"{'Markov-sufficient' if (mem_dbits==mem_dbits and mem_dbits<0.01) else 'memory matters (reward-misspec flag)'}")

    # ------------------------------------------------------------------ M4 individual
    print("[M4] individual: same-animal cross-night personalization (+/- weather)")
    pg_w = cm.personalization_gain(leave, "left", base_numeric=M2_NUM, base_categorical=M1_CAT,
                                   id_features=ID_FEATURES, dwell_col=DWELL)
    pg_now = cm.personalization_gain(leave, "left", base_numeric=M1_NUM, base_categorical=M1_CAT,
                                     id_features=ID_FEATURES, dwell_col=DWELL)
    g_w, g_now = cm.summarize_gain(pg_w), cm.summarize_gain(pg_now)
    perm = cm.conditional_permutation_null(leave, "left", strata_cols=("roi",), base_numeric=M2_NUM,
                                           base_categorical=M1_CAT, id_features=ID_FEATURES,
                                           dwell_col=DWELL, n_perm=n_perm, seed=0)
    pg_w.to_csv(d / "M4_personalization_gain.csv", index=False)
    m4_go = (g_w["median"] is not None and g_w["median"] > 0.003
             and g_w.get("frac_positive_nights", 0) >= 0.6
             and perm.get("z") is not None and perm["z"] > 2)
    R["M4_individual"] = {"gain_with_weather": g_w, "gain_without_weather": g_now,
                          "conditional_permutation": perm, "GO": bool(m4_go)}
    print(f"     Dbits median (weather-adj)={g_w['median']:.4f} frac+nights={g_w.get('frac_positive_nights')}"
          f" cond-perm z={perm.get('z')} -> individual policy {'GO' if m4_go else 'NO-GO'}")

    # ------------------------------------------------------------------ M5 social
    print("[M5] social: strictly pre-decision increment (+ time-shift, day-shuffle, jitter-safe)")
    si = cm.social_increment(leave, "left", base_numeric=M2_NUM, base_categorical=M1_CAT,
                             social_features=SOCIAL, dwell_col=DWELL)
    ts = cm.time_shift_social_null(leave, "left", SOCIAL, base_numeric=M2_NUM, base_categorical=M1_CAT,
                                   dwell_col=DWELL, n_perm=max(15, n_perm // 3), seed=0)
    ds = cm.day_shuffle_social_null(leave, "left", SOCIAL, base_numeric=M2_NUM, base_categorical=M1_CAT,
                                    dwell_col=DWELL, n_perm=max(20, n_perm // 2), seed=0)
    # jitter-floor-safe (drop sub-floor nn_dist_in) — the auditor's caveat check
    si_safe = cm.social_increment(leave, "left", base_numeric=M2_NUM, base_categorical=M1_CAT,
                                  social_features=SOCIAL_SAFE, dwell_col=DWELL)
    ds_safe = cm.day_shuffle_social_null(leave, "left", SOCIAL_SAFE, base_numeric=M2_NUM,
                                         base_categorical=M1_CAT, dwell_col=DWELL, n_perm=max(20, n_perm // 2), seed=1)
    si.to_csv(d / "M5_social_increment.csv", index=False)
    m5_go = (si["delta_bits"].mean() > 0.003 and (si["delta_bits"] > 0).mean() >= 0.6
             and ts.get("z", 0) is not None and ts["z"] > 2 and ds.get("z", 0) is not None and ds["z"] > 2
             and si_safe["delta_bits"].mean() > 0.003)   # survives day-shuffle AND jitter-safe
    R["M5_social"] = {"mean_dbits": float(si["delta_bits"].mean()),
                      "frac_positive_nights": float((si["delta_bits"] > 0).mean()),
                      "time_shift_null": ts, "day_shuffle_null": ds,
                      "jitter_safe_mean_dbits": float(si_safe["delta_bits"].mean()),
                      "jitter_safe_day_shuffle_z": ds_safe.get("z"), "GO": bool(m5_go)}
    print(f"     social Dbits mean={si['delta_bits'].mean():.4f} time-shift z={ts.get('z')} "
          f"day-shuffle z={ds.get('z')} | jitter-safe Dbits={si_safe['delta_bits'].mean():.4f} "
          f"ds-z={ds_safe.get('z')} -> social increment {'GO' if m5_go else 'NO-GO'}")

    # ------------------------------------------------------------------ matched-choice
    print("[matched-choice] symmetric resources")
    mc_all = []
    for grp, members in em.symmetric_groups().items():
        if grp in ("refuges_left", "refuges_right", "foods"):
            continue
        mc = cm.matched_choice_stability(dest, members)
        if not mc.empty:
            mc["group"] = grp
            mc_all.append(mc)
    mc_df = pd.concat(mc_all, ignore_index=True) if mc_all else pd.DataFrame()
    if not mc_df.empty:
        mc_df.to_csv(d / "matched_choice.csv", index=False)
    R["matched_choice"] = {"n_stable": int(mc_df["stable_pref"].sum()) if not mc_df.empty else 0,
                           "n_tested": int(len(mc_df))}
    print(f"     stable cross-night preferences: {R['matched_choice']['n_stable']}/{R['matched_choice']['n_tested']}")

    # ------------------------------------------------------------------ transfer audit
    reg_rows = [{"night": n, **em.night_regime(n)} for n in nights]
    reg = pd.DataFrame(reg_rows)
    tr = (pg_w.groupby("held_night")["delta_bits"].mean().rename("indiv_dbits").reset_index()
          .merge(si.rename(columns={"held_night": "held_night", "delta_bits": "social_dbits"})[["held_night", "social_dbits"]],
                 on="held_night", how="outer").merge(reg, left_on="held_night", right_on="night", how="left"))
    tr.to_csv(d / "transfer_audit.csv", index=False)
    R["transfer"] = {"per_night": tr.to_dict("records")}

    # ------------------------------------------------------------------ reward-feasibility verdict
    gates = {
        "policy_stationary_transfer": bool(R["M4_individual"]["GO"] or R["M5_social"]["GO"]),
        "state_coverage_ok": bool(A0_ok),
        "observed_state_markov": bool(R["memory"].get("observed_state_markov_ok") or False),
        "action_space_adequate": bool(len(dest["dest"].unique()) >= 3),
    }
    reward_go = all(gates.values())
    R["reward_feasibility"] = {"gates": gates, "verdict": "GO" if reward_go else "NO-GO",
                               "note": "Forward predictability != reward identifiability; unobserved "
                               "odor/temperature/food/habituation/social -> observationally equivalent "
                               "rewards. Preferred endpoint = interpretable semi-Markov choice model."}
    print(f"[reward] gates={gates} -> {R['reward_feasibility']['verdict']}")

    R["generated_utc"] = datetime.datetime.utcnow().isoformat()
    R["n_perm"] = n_perm
    R["fast_mode"] = bool(args.fast)
    R["provenance"] = {
        "config_id": args.config_id or "unspecified",
        "decision_unit": "hysteretic_roi_state" if args.config_id.startswith("hyst") else "unspecified",
        "leave_table": str((d / "leave_decisions.csv").resolve()),
        "n_leave_epochs": int(len(leave)), "n_departures": int(len(dest)),
        "note": "All A0/M1-M5/nulls/verdicts below are from THIS single run/decision unit.",
    }
    (d / "policy_identifiability_results.json").write_text(json.dumps(R, indent=2, default=str), encoding="utf-8")
    _write_report(d, R, n_perm)
    print(f"done -> {d}")


def _write_report(d, R, n_perm):
    def g(x, *k, default=None):
        for kk in k:
            x = (x or {}).get(kk, {}) if isinstance(x, dict) else default
        return x
    m4, m5 = R["M4_individual"], R["M5_social"]
    prov = R.get("provenance", {})
    header = ("# Policy-identifiability report — WISER agent-policy (Phase 1)\n\n"
              f"**Provenance:** decision unit = `{prov.get('config_id','?')}` "
              f"({prov.get('decision_unit','?')}); {prov.get('n_leave_epochs','?')} leave epochs, "
              f"{prov.get('n_departures','?')} departures; generated {R.get('generated_utc','?')}; "
              f"n_perm={R.get('n_perm','?')}. **All metrics below are from THIS single run.**\n\n"
              "**Status:** ⚠️ candidate. Hierarchical semi-Markov identifiability ladder; whole "
              "nights are the outer blocks (~8); primary loss = held-out cross-entropy in "
              "**bits/decision**. Inch frame UNVERIFIED (topology + coarse distances only); gaps "
              "are 'unknown', never departures. FORWARD-prediction / identifiability study — NOT "
              "reward inference (see verdict).\n")
    defn = r"""
## Definitions

- **Leaving hazard** $h_i(t)=P(\text{leave ROI }r\text{ in }[t,t{+}\Delta)\mid\text{resident at }t,z_t)$,
  $\operatorname{logit}h_i(t)=\beta\cdot z_t+f_r(\tau)$; $\tau$=elapsed dwell (mandatory), $\Delta$=epoch (s).
  Plain: per fixed time-slice while in an ROI, the probability of leaving given dwell + covariates.
- **Destination choice** $P(\text{next ROI}=j\mid o, C(o), z_t)$ over the origin-specific supported
  choice set $C(o)$. Plain: given a departure from $o$, which supported ROI is entered next.
- **Held-out bits** $H=-\frac1N\sum \log_2 p(\text{observed}\mid z)$ (bits/decision). **Dbits**
  $=H_{\text{base}}-H_{\text{model}}$ (>0 = model better). **skill** $=1-H_{\text{model}}/H_{\text{base}}$.
- **Personalization gain** $\Delta\text{bits}(i,\text{night})=H_{\text{holdout}}(\text{pooled})-H_{\text{holdout}}(\text{personalized})$;
  personalized = pooled + animal FE + animal x resource interactions, the identity part fit only on
  animal $i$'s TRAINING nights (whole held-out night excluded). Plain: does knowing WHICH animal
  improve prediction on a night it was not trained on.
- **Env-matched conditional permutation**: shuffle identity WITHIN (roi) strata, recompute the
  median gain; $z=(\text{obs}-\mu_\text{null})/\sigma_\text{null}$ (holds marginal state-visitation
  fixed). **Time-shift null**: circularly shift the pre-decision social features within night.
- **Shared-use hazard** (leave-focal-out pooled $P(\text{left}\mid \text{roi,dwell-tercile})$): an
  animal-derived behavioral feature; its Dbits over M2 (explicit layout+weather) = emergent shared use.
- **Matched-choice stability**: for a symmetric resource group, an animal's cross-night preference
  transfers (LONO error < 0.15) AND departs indifference $1/|\text{group}|$ by > 0.15.

## Stage results"""
    md = header + defn + f"""

**A0 support:** {R['A0']['n_leave_epochs']} leave epochs, {R['A0']['n_departures']} departures;
multi-animal comparable strata = {R['A0']['n_strata_with_>=2_animals']} → individual arm
**{'SUPPORTED (state coverage; see power note)' if R['A0'].get('individual_arm_state_coverage') else 'UNDERPOWERED'}**.

**A1 registration:** {R['A1']['status']} (physical transform {R['A1']['physical_transform']});
allowed predictors: {R['A1']['allowed']}.

**A2 measurement process:** valid_frac {g(R,'A2','valid_frac_range')}, gap_frac
{g(R,'A2','gap_frac_range')} (a gap stays 'unknown', never a departure).

**M1→M3 (held-out bits):** marginal {R['nested']['H_marginal_bits']:.3f} → M1 layout
{R['nested']['H_M1_layout_bits']:.3f} (skill {R['nested']['skill_M1_vs_marginal']:.3f}) → M2 +weather
{R['nested']['H_M2_plusweather_bits']:.3f} (weather Δbits {R['nested']['dbits_weather_M1_to_M2']:.4f})
→ M3 +shared-use {R['nested']['H_M3_plussharedus_bits']:.3f} (shared-use Δbits
{R['nested']['dbits_shareduse_M2_to_M3']:.4f}).

**Memory:** history Δbits over M2 = {R['memory']['dbits_history_over_M2']} →
{'observed-state Markov-sufficient' if R['memory'].get('observed_state_markov_ok') else 'memory matters (reward-on-observed-state would be misspecified)'}.

**M4 individual:** weather-adjusted personalization Δbits median = {m4['gain_with_weather']['median']}
(frac+ nights {m4['gain_with_weather'].get('frac_positive_nights')}); without-weather median
{m4['gain_without_weather']['median']}; conditional-permutation z = {g(R,'M4_individual','conditional_permutation','z')}.
**Verdict: {'GO — stable individual decision structure' if m4['GO'] else 'NO-GO — no identifiable individual policy beyond the shared baseline'}.**

**M5 social:** pre-decision social Δbits mean = {m5['mean_dbits']:.4f} (frac+ nights
{m5['frac_positive_nights']:.2f}); time-shift null z = {g(R,'M5_social','time_shift_null','z')};
**day-shuffle null z = {g(R,'M5_social','day_shuffle_null','z')}**; jitter-safe (drop sub-floor
nn_dist) Δbits = {m5.get('jitter_safe_mean_dbits')}, day-shuffle z = {m5.get('jitter_safe_day_shuffle_z')}.
**Verdict: {'GO — real-time group-social predictive increment (survives time-shift + day-shuffle + jitter-safe)' if m5['GO'] else 'NO-GO — no social increment beyond shared-use/environment'}.**

**Matched-choice:** stable cross-night symmetric-resource preferences =
{R['matched_choice']['n_stable']}/{R['matched_choice']['n_tested']}.

## Reward-feasibility verdict

Gates: {json.dumps(R['reward_feasibility']['gates'])} → **{R['reward_feasibility']['verdict']}**.
{R['reward_feasibility']['note']}

## Classification

Each result is behavioral / measurement-artifact / mixed / lower-bound; individual and social
verdicts rest on **cross-night transfer**, not coefficients. Permutations: {n_perm}. Artifacts:
`A0_support_per_animal_night.csv`, `M4_personalization_gain.csv`, `M5_social_increment.csv`,
`matched_choice.csv`, `transfer_audit.csv`, `policy_identifiability_results.json`.
"""
    (d / "policy_identifiability_report.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
