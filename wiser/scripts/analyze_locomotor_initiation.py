r"""
analyze_locomotor_initiation.py — Phase 1 / Module 3 modeling (run under the anaconda3 interpreter).

Reads ``initiation_decisions.csv`` and runs the locomotor-bout-INITIATION hazard ladder — the
entry-side twin of the module-5 leaving-hazard ladder. Primary loss = held-out cross-entropy in
BITS/decision at the NIGHT-block level (~8 nights). Questions, in order:

  Predictive gate:  is the initiation hazard predictable from the residence STATE at all?
                    (M1 state vs the marginal base rate; skill = 1 - H_M1/H_marginal)
  Context:          does weather add held-out prediction?           (M1 -> M2)
  Social:           does strictly pre-decision GROUP-social state add held-out prediction,
                    surviving circular time-shift AND day-shuffle nulls, jitter-safe?  (M2 -> M3)
  Individual:       does same-animal cross-night personalization add, beyond an env-matched
                    conditional identity permutation?  (secondary; expected negligible, per module 5)
  Effect curve:     empirical initiation hazard vs elapsed rest (the f(tau) basis).

Leakage guard: ``moving_frac`` is DELIBERATELY excluded as a predictor — on the terminal (onset)
epoch it is contaminated by the very movement that defines the event.

    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\analyze_locomotor_initiation.py
    C:\Users\Cornell\anaconda3\python.exe scripts\analyze_locomotor_initiation.py --fast
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

import choice_models as cm                              # noqa: E402
from environment_map import EnvironmentMap              # noqa: E402

DWELL = "rest_elapsed_s"
M1_NUM = ["in_named_roi", "dist_to_edge_in", "clock_hour", "wet", "fireworks", "burrow", "truncated"]
M1_CAT = ["roi"]
WEATHER = ["w_temp_c", "w_tempdew_gap_c", "w_rain_log1p", "w_solar_wm2"]
ID_FEATURES = ["is_house", "is_refuge", "is_water"]
SOCIAL_SAFE = ["n_within_1m", "mean_others_dist_in"]     # jitter-floor-safe group-social (>= 1 m)
# EXCLUDED as predictors: moving_frac (leakage — encodes the onset), nn_dist_in (partly sub-jitter).


def _present(df, cols):
    return [c for c in cols if c in df.columns]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path,
                    default=ROOT / "outputs/locomotor_initiation_2026-06-28_to_2026-07-08")
    ap.add_argument("--env-map", type=Path,
                    default=ROOT / "configs/environment_map/2026-06-28_to_2026-07-08.yaml")
    ap.add_argument("--rois", type=Path, default=ROOT / "configs/wiser_rois.json")
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--config-id", default="locomotor_buf14_exit30_move10_ep5")
    args = ap.parse_args()
    n_perm = 20 if args.fast else 60
    # ~200k at-risk epochs => each held-out-night logistic fit is ~1 s, and a permutation null is
    # (n_perm x 16 fits). The social + individual verdicts here are NO-GO on effect MAGNITUDE (Δbits
    # << the 0.003-bit threshold) independent of the null z, so the nulls are run at a SCREENING
    # count for provenance; re-run with a large n_perm for a publication z (as the module-5 row notes).
    n_null = min(n_perm, 6)
    n_perm_indiv = min(n_perm, 6)
    d = args.dir
    import time as _time
    _t0 = _time.time(); _prog = open(d / "_analyze_progress.log", "w", buffering=1)

    def plog(msg):
        line = f"[{_time.time() - _t0:6.1f}s] {msg}"
        print(line, flush=True); _prog.write(line + "\n"); _prog.flush()

    init = pd.read_csv(d / "initiation_decisions.csv")
    em = EnvironmentMap.from_paths(args.env_map, args.rois)
    m1_num = _present(init, M1_NUM); m2_num = m1_num + _present(init, WEATHER)
    soc = _present(init, SOCIAL_SAFE); idf = _present(init, ID_FEATURES)
    R = {}

    # ------------------------------------------------------------------ support
    plog("[support] onsets / rest episodes / state coverage")
    nights = sorted(init["night"].unique())
    per_an = init.groupby(["night", "shortid"]).agg(
        epochs=("initiated", "size"), onsets=("initiated", "sum")).reset_index()
    occ = pd.read_csv(d / "state_occupancy.csv") if (d / "state_occupancy.csv").exists() else pd.DataFrame()
    diag = json.loads((d / "distinction_diagnostics.json").read_text()) if (d / "distinction_diagnostics.json").exists() else {}
    states_populated = {}
    if not occ.empty:
        for s in ["rest", "local_active", "transit", "pause"]:
            states_populated[s] = bool(s in occ.columns and (occ[s] > 0).any())
    support_ok = int(init["initiated"].sum()) >= 30 and len(nights) >= 4
    R["support"] = {"n_initiation_epochs": int(len(init)), "n_onsets": int(init["initiated"].sum()),
                    "onset_rate": float(init["initiated"].mean()), "nights": nights,
                    "onsets_per_animal_night": per_an["onsets"].describe().to_dict(),
                    "states_populated": states_populated, "gate_ok": support_ok,
                    "power_note": "State coverage, not statistical power; ~8 night-blocks under "
                    "whole-night holdout under-power a <0.003 bit effect (NO-GO = effect upper bound)."}
    per_an.to_csv(d / "support_per_animal_night.csv", index=False)
    print(f"     epochs={len(init)} onsets={int(init['initiated'].sum())} "
          f"({100*init['initiated'].mean():.2f}%) states={states_populated} -> "
          f"{'SUPPORTED' if support_ok else 'THIN'}")

    # ------------------------------------------------------------------ ladder (held-out bits)
    plog("[M0-M3] nested initiation-hazard models (held-out bits/decision)")
    m0 = cm.lono_bits(init, "initiated", numeric=(), categorical=(), dwell_col=None)
    m1 = cm.lono_bits(init, "initiated", numeric=m1_num, categorical=M1_CAT, dwell_col=DWELL)
    m2 = cm.lono_bits(init, "initiated", numeric=m2_num, categorical=M1_CAT, dwell_col=DWELL)
    m3 = cm.lono_bits(init, "initiated", numeric=m2_num + soc, categorical=M1_CAT, dwell_col=DWELL)

    def allbits(t):
        return float(t[t.animal == "ALL"]["bits"].mean())
    H0, H1, H2, H3 = allbits(m0), allbits(m1), allbits(m2), allbits(m3)
    R["ladder"] = {"H_marginal_bits": H0, "H_M1_state_bits": H1, "H_M2_plusweather_bits": H2,
                   "H_M3_plussocial_bits": H3, "skill_state_vs_marginal": cm.skill(H1, H0),
                   "dbits_weather": H1 - H2, "dbits_social": H2 - H3,
                   "predictive_gate_state": bool(H1 < H0)}
    print(f"     H: marginal={H0:.4f} M1_state={H1:.4f} M2_weather={H2:.4f} M3_social={H3:.4f} "
          f"(state skill={cm.skill(H1,H0):.3f}, weather d={H1-H2:.4f}, social d={H2-H3:.4f})")

    # ------------------------------------------------------------------ social nulls
    plog("[social] strictly pre-decision group-social increment + nulls")
    R["social"] = {"tested": bool(soc)}
    if soc:
        si = cm.social_increment(init, "initiated", base_numeric=m2_num, base_categorical=M1_CAT,
                                 social_features=soc, dwell_col=DWELL)
        tshift = cm.time_shift_social_null(init, "initiated", soc, base_numeric=m2_num,
                                           base_categorical=M1_CAT, dwell_col=DWELL,
                                           n_perm=n_null, seed=0)
        dshuf = cm.day_shuffle_social_null(init, "initiated", soc, base_numeric=m2_num,
                                           base_categorical=M1_CAT, dwell_col=DWELL,
                                           n_perm=n_null, seed=0)
        si.to_csv(d / "social_increment.csv", index=False)
        social_go = (si["delta_bits"].mean() > 0.003 and (si["delta_bits"] > 0).mean() >= 0.6
                     and (tshift.get("z") or 0) > 2 and (dshuf.get("z") or 0) > 2)
        R["social"].update({"mean_dbits": float(si["delta_bits"].mean()),
                            "frac_positive_nights": float((si["delta_bits"] > 0).mean()),
                            "time_shift_null": tshift, "day_shuffle_null": dshuf, "GO": bool(social_go)})
        print(f"     social dbits={si['delta_bits'].mean():.4f} time-shift z={tshift.get('z')} "
              f"day-shuffle z={dshuf.get('z')} -> {'GO' if social_go else 'NO-GO'}")

    # ------------------------------------------------------------------ individual arm (secondary)
    plog("[individual] same-animal cross-night personalization (secondary)")
    R["individual"] = {"tested": bool(idf)}
    if idf:
        pg = cm.personalization_gain(init, "initiated", base_numeric=m2_num, base_categorical=M1_CAT,
                                     id_features=idf, dwell_col=DWELL)
        gp = cm.summarize_gain(pg)
        perm = cm.conditional_permutation_null(init, "initiated", strata_cols=("roi",),
                                               base_numeric=m2_num, base_categorical=M1_CAT,
                                               id_features=idf, dwell_col=DWELL, n_perm=n_perm_indiv, seed=0)
        pg.to_csv(d / "personalization_gain.csv", index=False)
        indiv_go = (gp["median"] is not None and gp["median"] > 0.003
                    and gp.get("frac_positive_nights", 0) >= 0.6 and (perm.get("z") or 0) > 2)
        R["individual"].update({"gain": gp, "conditional_permutation": perm, "GO": bool(indiv_go)})
        print(f"     personalization dbits median={gp['median']:.4f} cond-perm z={perm.get('z')} "
              f"-> {'GO' if indiv_go else 'NO-GO (negligible)'}")

    # ------------------------------------------------------------------ effect curve (hazard vs rest)
    plog("[effect] empirical initiation hazard vs elapsed rest")
    ec = init.copy()
    ec["dwell_bin"] = pd.qcut(ec[DWELL].rank(method="first"), 10, labels=False, duplicates="drop")
    curve = (ec.groupby("dwell_bin").agg(rest_elapsed_s=(DWELL, "median"),
             hazard=("initiated", "mean"), n=("initiated", "size")).reset_index())
    curve.to_csv(d / "initiation_hazard_curve.csv", index=False)
    # by resource type + by settled-residence vs open low-speed (the in_named_roi covariate)
    haz_res = (init.groupby("resource_type").agg(hazard=("initiated", "mean"),
               n=("initiated", "size")).reset_index() if "resource_type" in init.columns else pd.DataFrame())
    if not haz_res.empty:
        haz_res.to_csv(d / "initiation_hazard_by_resource.csv", index=False)
    haz_stratum = pd.DataFrame()
    if "in_named_roi" in init.columns:
        haz_stratum = (init.assign(stratum=np.where(init["in_named_roi"] == 1, "settled_named_roi", "open_lowspeed"))
                       .groupby("stratum").agg(hazard=("initiated", "mean"), onsets=("initiated", "sum"),
                                               n_epochs=("initiated", "size")).reset_index())
        haz_stratum.to_csv(d / "initiation_hazard_by_stratum.csv", index=False)
    R["effect_curve"] = {"hazard_vs_dwell": curve.to_dict("records"),
                         "hazard_by_resource": haz_res.to_dict("records") if not haz_res.empty else [],
                         "hazard_by_stratum": haz_stratum.to_dict("records") if not haz_stratum.empty else []}
    print(f"     hazard by stratum: {haz_stratum.to_dict('records') if not haz_stratum.empty else 'n/a'}")

    R["provenance"] = {"config_id": args.config_id, "n_perm": n_perm, "fast_mode": bool(args.fast),
                       "initiation_table": str((d / "initiation_decisions.csv").resolve()),
                       "n_epochs": int(len(init)), "n_onsets": int(init["initiated"].sum()),
                       "excluded_predictors": ["moving_frac (onset leakage)", "nn_dist_in (sub-jitter)"]}
    R["generated_utc"] = datetime.datetime.utcnow().isoformat()
    (d / "locomotor_initiation_results.json").write_text(json.dumps(R, indent=2, default=str),
                                                         encoding="utf-8")
    _write_report(d, R, diag, n_perm)
    print(f"done -> {d}")


def _write_report(d, R, diag, n_perm):
    def gz(x, *k):
        for kk in k:
            x = (x or {}).get(kk, {}) if isinstance(x, dict) else None
        return x
    L = R["ladder"]; S = R.get("social", {}); I = R.get("individual", {}); sup = R["support"]
    prov = R["provenance"]
    d1 = (diag or {}).get("D1_initiation_vs_departure", {})
    d4 = (diag or {}).get("D4_arrival_vs_settled", {})
    header = (
        "# Locomotor-bout-initiation report — WISER agent-policy (Phase 1 / Module 3)\n\n"
        f"**Provenance:** decision unit = `{prov['config_id']}`; {prov['n_epochs']} at-risk rest "
        f"epochs, {prov['n_onsets']} onsets; generated {R['generated_utc']}; n_perm={prov['n_perm']}. "
        "**All metrics from THIS single run.**\n\n"
        "**Status:** ⚠️ candidate. Module 3 is the ENTRY-side twin of the built site-residence-"
        "termination (leaving) hazard: given the animal is SETTLED at rest in a named ROI, the hazard "
        "of INITIATING a locomotor bout. Onset = speed-onset ABOVE the ~7 in jitter floor — a **LOWER "
        "bound** (in-nest sub-jitter stirring, the ~18:00 arousal, are invisible → **not 'wake'**). "
        "Whole nights are the outer blocks (~8); primary loss = held-out **bits/decision**. Frame "
        "UNVERIFIED. NOT 'the policy', NOT 'decided to forage'.\n")
    defn = r"""
## Definitions (formula + plain text)

- **Unified locomotor state** (per 5 s bin): `rest` (settled: named-ROI-state ∧ stationary),
  `local_active` (named-ROI-state ∧ active), `transit` (open ∧ active), `pause` (open ∧ stationary),
  `unknown` (empty/gap). ROI-state = module-5 hysteretic segmentation; movement-state = speed
  hysteresis (enter ACTIVE after 10 s moving, exit after 10 s stationary; a shorter pause HOLDS).
- **Bout-initiation hazard** $h_i(t)=P(\text{initiate a bout in }[t,t{+}\Delta)\mid \text{at rest at }t, z_t)$,
  $\operatorname{logit}h_i(t)=\beta\cdot z_t+f_r(\tau)$; $\tau$ = elapsed rest (mandatory basis),
  $\Delta$ = epoch (s). Plain: per time-slice while settled at rest, the probability of starting a
  locomotor bout given elapsed rest + covariates. Event = the movement-state ACTIVE onset that ends
  a rest episode (NOT an ROI departure).
- **Held-out bits** $H=-\frac1N\sum\log_2 p(\text{initiated}\mid z)$ (bits/decision), leave-one-night
  -out. **skill** $=1-H_{\text{model}}/H_{\text{marginal}}$. **Δbits** $=H_{\text{base}}-H_{\text{model}}$.
- **Social increment**: held-out Δbits of adding jitter-safe group-social ($n_{\le1\text{m}}$,
  mean-others-distance), gated by a within-night **circular time-shift** null and a **day-shuffle**
  null (same animal×ROI×clock-hour on a different night); z of observed vs null.
- **Personalization gain** $\Delta\text{bits}(i,\text{night})=H(\text{pooled})-H(\text{personalized})$,
  the identity part fit only on animal $i$'s TRAINING nights; env-matched conditional identity
  permutation for the null.
- **Excluded predictors:** `moving_frac` (LEAKAGE — the onset epoch's moving fixes encode the event),
  `nn_dist_in` (partly sub-jitter).

## The four distinctions (measurement gate; causal guarantees in `selftest_locomotor_states.py`)

- **D1 initiation ≠ departure:** onsets {n1}, module-relocating departures {n2} (ratio {r}). Initiation
  is a distinct, more frequent event than ROI departure.
- **D4 arrival ≠ settled:** {f} of named-ROI visits contain no rest bin (moving pass-throughs).

## Results
""".replace("{n1}", str(d1.get("n_bout_onsets", "?"))).replace("{n2}", str(d1.get("n_departures_relocating", "?"))
    ).replace("{r}", str(d1.get("onset_to_departure_ratio", "?"))).replace("{f}", str(d4.get("frac_visits_no_rest", "?")))
    body = f"""
**Support:** {sup['n_onsets']} onsets over {sup['n_initiation_epochs']} at-risk rest epochs
({100*sup['onset_rate']:.2f}%); states populated = {sup['states_populated']} → gate
**{'SUPPORTED' if sup['gate_ok'] else 'THIN'}**. {sup['power_note']}

**Predictive gate (state):** marginal {L['H_marginal_bits']:.4f} → M1 state {L['H_M1_state_bits']:.4f}
bits (skill {L['skill_state_vs_marginal']:.3f}) → the initiation hazard **{'IS' if L['predictive_gate_state'] else 'is NOT'}
predictable from residence state**. +weather → M2 {L['H_M2_plusweather_bits']:.4f} (Δbits
{L['dbits_weather']:.4f}); +social → M3 {L['H_M3_plussocial_bits']:.4f} (Δbits {L['dbits_social']:.4f}).

**Social (strictly pre-decision, jitter-safe):** {"mean Δbits " + format(S.get('mean_dbits', float('nan')), '.4f') + f" (frac+ nights {S.get('frac_positive_nights')}); time-shift z = {gz(S,'time_shift_null','z')}; day-shuffle z = {gz(S,'day_shuffle_null','z')} → **" + ('GO — real-time group-social predicts bout initiation' if S.get('GO') else 'NO-GO — no social increment beyond state/weather') + "**." if S.get("tested") else "not tested (no social columns)."}

**Individual (secondary):** {"personalization Δbits median = " + str(I.get('gain', {}).get('median')) + f"; cond-perm z = {gz(I,'conditional_permutation','z')} → **" + ('GO' if I.get('GO') else 'NO-GO (negligible, as in module 5)') + "**." if I.get("tested") else "not tested."}

**Effect curve:** empirical initiation hazard vs elapsed rest in `initiation_hazard_curve.csv`;
by resource type in `initiation_hazard_by_resource.csv`.

## Classification & scope

Each result is behavioral / measurement-artifact / mixed / lower-bound. Onset is a **lower bound**
(sub-jitter stirring invisible). This is the **locomotor-bout-initiation** module (module 3) — one of
14; it does NOT represent the destination, approach/avoid, search, or motivation modules. Permutations:
{n_perm}. Artifacts: `support_per_animal_night.csv`, `social_increment.csv`, `personalization_gain.csv`,
`initiation_hazard_curve.csv`, `locomotor_initiation_results.json`, `distinction_diagnostics.json`.
"""
    (d / "locomotor_initiation_report.md").write_text(header + defn + body, encoding="utf-8")


if __name__ == "__main__":
    main()
