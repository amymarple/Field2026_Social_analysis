r"""
check_social_robustness.py — stress-test the emergent social GO on the clean hysteretic decision
unit (run under anaconda3). The grid showed M5 social beats the WITHIN-NIGHT TIME-SHIFT null (z
11–32), but that null is weak: it removes temporal alignment while keeping each night's marginal
social distribution. Two harder tests before believing a real-time social RESPONSE:

  1. DAY-SHUFFLE null — reassign each decision's social features from the SAME animal + ROI +
     clock-hour on a DIFFERENT night. Preserves the marginal social-by-state structure and the
     circadian/environmental drive; breaks the specific night's real-time co-presence. Surviving
     this = the *particular night's* social configuration predicts leaving (not shared arousal).
     Prior trajectory work found co-movement did NOT beat day-shuffle (herd, not dyadic).
  2. JITTER-FLOOR-SAFE features — drop nn_dist_in (52% < 14 in, 23% < 7 in = sub-floor pseudo-
     proximity) and keep only n_within_1m (1 m = 39.37 in radius, jitter-safe) + mean_others_dist_in.
     If the GO survives on these, it is not a sub-floor artifact.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import choice_models as cm                             # noqa: E402

DWELL = "dwell_elapsed_s"
M2_NUM = ["dist_to_edge_in", "clock_hour", "moving_frac", "wet", "fireworks", "burrow",
          "w_temp_c", "w_tempdew_gap_c", "w_rain_log1p", "w_solar_wm2"]
M1_CAT = ["roi"]
SOCIAL_ALL = ["nn_dist_in", "n_within_1m", "mean_others_dist_in"]
SOCIAL_SAFE = ["n_within_1m", "mean_others_dist_in"]     # jitter-floor-safe only


def day_shuffle_social_null(df, social_features, *, n_perm=30, seed=0):
    """Reassign social features within (shortid, roi, clock_hour) strata (i.e. across nights,
    same animal+state+clock), recompute the social increment, return z of observed vs null."""
    obs = cm.social_increment(df, "left", base_numeric=M2_NUM, base_categorical=M1_CAT,
                              social_features=social_features, dwell_col=DWELL)["delta_bits"].mean()
    rng = np.random.default_rng(seed)
    strata = df.groupby(["shortid", "roi", "clock_hour"]).indices
    null = []
    for _ in range(n_perm):
        dd = df.copy()
        for _, idx in strata.items():
            if len(idx) < 2:
                continue
            perm = rng.permutation(idx)
            for f in social_features:
                dd.iloc[idx, dd.columns.get_loc(f)] = df.iloc[perm][f].to_numpy()
        null.append(cm.social_increment(dd, "left", base_numeric=M2_NUM, base_categorical=M1_CAT,
                                        social_features=social_features, dwell_col=DWELL)["delta_bits"].mean())
    null = np.asarray([x for x in null if x == x], float)
    mu, sd = (null.mean(), null.std()) if len(null) else (np.nan, np.nan)
    z = (obs - mu) / sd if sd and sd > 0 else np.nan
    return {"observed": float(obs), "null_mean": float(mu) if mu == mu else np.nan,
            "z": float(z) if z == z else np.nan, "n_perm": int(len(null))}


def main():
    d = ROOT / "outputs/policy_identifiability_2026-06-28_to_2026-07-06/grid/buf14_exit30_ep15"
    lv = pd.read_csv(d / "leave_decisions.csv")
    print(f"config buf14_exit30_ep15: {len(lv):,} leave epochs")
    print(f"nn_dist_in sub-floor: {100*(lv.nn_dist_in < 14).mean():.0f}% < 14in, "
          f"{100*(lv.nn_dist_in < 7).mean():.0f}% < 7in (of {lv.nn_dist_in.notna().sum():,} present)")
    for name, feats in [("ALL social", SOCIAL_ALL), ("jitter-SAFE (drop nn_dist)", SOCIAL_SAFE),
                        ("nn_dist ONLY", ["nn_dist_in"])]:
        si = cm.social_increment(lv, "left", base_numeric=M2_NUM, base_categorical=M1_CAT,
                                 social_features=feats, dwell_col=DWELL)
        ts = cm.time_shift_social_null(lv, "left", feats, base_numeric=M2_NUM, base_categorical=M1_CAT,
                                       dwell_col=DWELL, n_perm=25)
        ds = day_shuffle_social_null(lv, feats, n_perm=30)
        print(f"\n[{name}]  mean Dbits={si['delta_bits'].mean():.4f}  frac+nights={(si['delta_bits']>0).mean():.2f}")
        print(f"   time-shift null z = {ts['z']:.2f}   |   DAY-SHUFFLE null z = {ds['z']:.2f}  "
              f"(obs {ds['observed']:.4f} vs null {ds['null_mean']:.4f})")


if __name__ == "__main__":
    main()
