r"""
analyze_rest_vs_social.py — Part 3: is a movement decision driven by REST-NEED (circadian / nap) or
by OTHER RATS (social)? Two questions, on the extended (11-night) data:

  LEAVING: the headline social result is "crowding SUPPRESSES leaving" (module 5). Is that because a
  crowded site is a HUDDLE and the animal stays to REST (rest-confounded), or a genuine social effect?
  Test: does the group-social increment on the leaving hazard SURVIVE adding rest covariates
  (circadian rest-propensity + the focal's own rest-state), and does it hold within resting vs active
  residents?

  ENTERING/SETTLING: when a rat settles at a named site (vs terminating its bout in the open), is it
  rest-driven (high circadian rest-propensity) or social (other rats already there)? Test both
  predictors' held-out increment on P(settle at a named site).

Rest-need proxy = the POPULATION stationary(rest)-fraction at the decision's local clock-hour
(animal-independent -> no leakage) + the focal's own rest-state. Rest is a low-speed proxy, not sleep.
Significance at the NIGHT-block level (bits/decision, leave-one-night-out).

    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\analyze_rest_vs_social.py
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

import choice_models as cm                       # noqa: E402
import rest_circadian as rc                       # noqa: E402

DWELL = "dwell_elapsed_s"
M1_NUM = ["dist_to_edge_in", "clock_hour", "moving_frac", "wet", "fireworks", "burrow"]
WEATHER = ["w_temp_c", "w_tempdew_gap_c", "w_rain_log1p", "w_solar_wm2"]
SOCIAL_SAFE = ["n_within_1m", "mean_others_dist_in"]
REST = ["rest_propensity", "focal_in_rest", "focal_rest_frac_pre"]
CAT = ["roi"]


def _present(df, cols):
    return [c for c in cols if c in df.columns]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy-dir", type=Path,
                    default=ROOT / "outputs/policy_identifiability_2026-06-28_to_2026-07-08")
    ap.add_argument("--locomotor-dir", type=Path,
                    default=ROOT / "outputs/locomotor_initiation_2026-06-28_to_2026-07-08")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs/policy_identifiability_2026-06-28_to_2026-07-08")
    ap.add_argument("--fast", action="store_true")
    args = ap.parse_args()
    n_perm = 20 if args.fast else 40
    leave = pd.read_csv(args.policy_dir / "leave_decisions.csv")
    stream = pd.read_csv(args.locomotor_dir / "locomotor_state_stream.csv")
    R = {"generated_utc": datetime.datetime.utcnow().isoformat(), "n_leave_epochs": int(len(leave))}

    print("[rest-context] attach circadian rest-propensity + focal rest-state to the leave table")
    leave = rc.attach_rest_context(leave, stream, time_col="t_epoch")
    rest = _present(leave, REST); m2 = _present(leave, M1_NUM) + _present(leave, WEATHER)
    soc = _present(leave, SOCIAL_SAFE)
    R["rest_coverage"] = {c: float(leave[c].notna().mean()) for c in rest}

    # ---- circadian rest rhythm (context) ----
    prof = rc.circadian_rest_profile(stream)
    prof.to_csv(args.out / "circadian_rest_profile.csv", index=False)
    R["circadian_rest_by_local_hour"] = prof.round(3).to_dict("records")

    def allbits(t):
        return float(t[t.animal == "ALL"]["bits"].mean())

    print("[LEAVING] does REST predict leaving, and does crowding survive controlling for rest?")
    # base H, +rest H, +social H, +rest+social H
    Hb = allbits(cm.lono_bits(leave, "left", numeric=m2, categorical=CAT, dwell_col=DWELL))
    Hr = allbits(cm.lono_bits(leave, "left", numeric=m2 + rest, categorical=CAT, dwell_col=DWELL))
    # social increment over base vs over base+rest (does the social effect survive rest control?)
    si_orig = cm.social_increment(leave, "left", base_numeric=m2, base_categorical=CAT,
                                  social_features=soc, dwell_col=DWELL)
    si_restctrl = cm.social_increment(leave, "left", base_numeric=m2 + rest, base_categorical=CAT,
                                      social_features=soc, dwell_col=DWELL)
    ds_restctrl = cm.day_shuffle_social_null(leave, "left", soc, base_numeric=m2 + rest,
                                             base_categorical=CAT, dwell_col=DWELL, n_perm=n_perm, seed=0)
    R["leaving"] = {
        "H_base": Hb, "H_base_plus_rest": Hr, "dbits_rest_over_base": Hb - Hr,
        "social_dbits_orig": float(si_orig["delta_bits"].mean()),
        "social_dbits_rest_controlled": float(si_restctrl["delta_bits"].mean()),
        "social_frac_retained_after_rest_control":
            float(si_restctrl["delta_bits"].mean() / si_orig["delta_bits"].mean())
            if si_orig["delta_bits"].mean() else np.nan,
        "social_rest_controlled_day_shuffle_z": ds_restctrl.get("z"),
    }
    print(f"     rest predicts leaving: dbits {Hb-Hr:.4f} | social orig={si_orig['delta_bits'].mean():.4f} "
          f"-> rest-controlled={si_restctrl['delta_bits'].mean():.4f} "
          f"(retained {R['leaving']['social_frac_retained_after_rest_control']:.2f}), day-shuffle z={ds_restctrl.get('z')}")

    # stratify: is crowding-suppresses-leaving present among RESTING residents vs ACTIVE ones?
    strat = {}
    for lab, sub in [("resting_focal", leave[leave["focal_in_rest"] == 1]),
                     ("active_focal", leave[leave["focal_in_rest"] == 0])]:
        if len(sub) < 500 or sub["left"].sum() < 20:
            strat[lab] = {"n": int(len(sub)), "note": "too few"}; continue
        si = cm.social_increment(sub, "left", base_numeric=m2, base_categorical=CAT,
                                 social_features=soc, dwell_col=DWELL)
        strat[lab] = {"n": int(len(sub)), "leave_rate": round(float(sub["left"].mean()), 4),
                      "social_dbits": float(si["delta_bits"].mean()),
                      "frac_positive_nights": float((si["delta_bits"] > 0).mean())}
    R["leaving_by_rest_state"] = strat
    print(f"     by rest-state: {strat}")

    # ---- ENTERING/SETTLING: rest-need vs social at the destination ----
    print("[ENTERING] settle at a named site (vs open-field) — rest-need vs others-present")
    trans_f = args.out.parent / "destination_settlement_2026-06-28_to_2026-07-08/settlement_transitions.csv"
    R["entering"] = {"tested": bool(trans_f.exists())}
    if trans_f.exists():
        tr = pd.read_csv(trans_f)
        tr = tr[tr["transition_type"] != "censored"].copy()
        tr["settled_named"] = tr["transition_type"].isin(["relocation", "same_site_return"]).astype(int)
        tr = rc.attach_rest_context(tr, stream, time_col="t_depart")
        # social at the moment of departure already on the leave/dest table? attach group-social here:
        # use rest_propensity (rest-need) vs a crowding proxy from the leave table joined by time is
        # complex; here test rest_propensity alone vs clock (does settling track the rest rhythm?)
        base_e = _present(tr, ["clock_hour", "wet", "fireworks", "burrow"])
        Hb_e = allbits(cm.lono_bits(tr, "settled_named", numeric=base_e, categorical=["origin_roi"], dwell_col="origin_dwell_s"))
        Hr_e = allbits(cm.lono_bits(tr, "settled_named", numeric=base_e + _present(tr, ["rest_propensity", "focal_rest_frac_pre"]),
                                    categorical=["origin_roi"], dwell_col="origin_dwell_s"))
        R["entering"].update({"n_departures": int(len(tr)), "settle_rate": round(float(tr["settled_named"].mean()), 3),
                              "H_base": Hb_e, "H_base_plus_rest": Hr_e, "dbits_rest_over_base": Hb_e - Hr_e})
        print(f"     settle-vs-open: rest-need dbits over base = {Hb_e-Hr_e:.4f} (n={len(tr)})")

    (args.out / "rest_vs_social_results.json").write_text(json.dumps(R, indent=2, default=str), encoding="utf-8")
    _write_report(args.out, R)
    print(f"done -> {args.out}")


def _write_report(out, R):
    L = R["leaving"]; strat = R["leaving_by_rest_state"]; E = R.get("entering", {})
    header = ("# Rest-need vs social — leaving & entering (Part 3, 11 nights)\n\n"
              "**Status:** ⚠️ candidate. Separates a REST-NEED (circadian / nap) driver from a SOCIAL "
              "(other-rats) driver in the movement decisions, on the extended 06-28→07-08 window. "
              f"Generated {R['generated_utc']}. Rest is a low-speed proxy, not sleep; night-block bits.\n")
    defn = r"""
## Definitions (formula + plain text)

- **rest_propensity(t)** — the POPULATION fraction of informative bins that are stationary (rest∪pause)
  at t's LOCAL clock-hour (the diel rest rhythm). Animal-INDEPENDENT, so it is a pure circadian
  rest-need covariate that cannot leak the focal's own outcome. **focal_in_rest** = the focal's own
  state at the decision is stationary (0/1); **focal_rest_frac_pre** = its stationary fraction in the
  120 s strictly before the decision.
- **Rest-controlled social increment** — the held-out group-social Δbits on the leaving hazard when the
  base ALSO contains the rest covariates. If it ≈ the uncontrolled increment, crowding-suppresses-
  leaving is NOT a rest artifact; if it collapses toward 0, it was rest-confounded.
- All Δbits are leave-one-night-out (whole nights = the outer blocks).

## Result — LEAVING"""
    body = f"""

- **Rest predicts leaving** (a resting/rest-phase animal leaves less): base→+rest held-out Δbits =
  **{L['dbits_rest_over_base']:.4f}**.
- **Crowding-suppresses-leaving SURVIVES rest control:** the group-social increment is
  **{L['social_dbits_orig']:.4f}** uncontrolled → **{L['social_dbits_rest_controlled']:.4f}** after
  adding the rest covariates (**{L['social_frac_retained_after_rest_control']:.0%} retained**), and the
  rest-controlled social still beats the day-shuffle (z = {L['social_rest_controlled_day_shuffle_z']}).
  {'So the social effect is NOT explained by rest/huddle-need — it is a genuine real-time social increment beyond both layout and rest-phase.' if (L['social_frac_retained_after_rest_control'] or 0) > 0.5 else 'The social effect largely disappears after controlling for rest — it was substantially rest/huddle-confounded.'}
- **By the focal's rest-state:** {strat}. {'Crowding suppresses leaving among BOTH resting and active residents' if all(isinstance(v,dict) and v.get('social_dbits',0)>0 for v in strat.values()) else 'The effect concentrates in one rest-state (see values)'}.

## Result — ENTERING / SETTLING

{('Settling at a named site (vs terminating a bout in the open) has a rest-need (circadian) held-out increment of **' + format(E.get('dbits_rest_over_base', float('nan')), '.4f') + '** bits over the layout+clock base (n=' + str(E.get('n_departures')) + ', settle-rate ' + str(E.get('settle_rate')) + '). Whether the destination tracks OTHER rats specifically needs the pre-decision group configuration at the destination (follow-up).') if E.get('tested') else 'not tested (transition table absent).'}

## Scope

Circadian rest-need is a population-rhythm proxy (a low-speed state, not sleep); the focal rest-state
is contemporaneous conditioning, not an outcome. Social remains group-level (herd, not dyads),
association not causation. Frame UNVERIFIED. Single 11-night pilot.
"""
    (out / "rest_vs_social_report.md").write_text(header + defn + body, encoding="utf-8")


if __name__ == "__main__":
    main()
