r"""
analyze_temporal_policy.py — does the site-leaving RULE vary across hour-of-night / across nights?
Runs under anaconda3. Reads the CLEAN hysteretic decision tables ONLY (grid config subdirs) — never
the superseded raw run. Whole nights are the outer held-out blocks.

Writes: temporal_policy_support.csv, hour_varying_effects.csv, night_varying_effects.csv,
temporal_model_comparison.csv, temporal_nulls.csv, plots (social effect by hour-block; per-night
gain), and feeds TEMPORAL_POLICY_SUMMARY.md.

    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\analyze_temporal_policy.py
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import temporal_policy as tp                          # noqa: E402

GRID = ROOT / "outputs/policy_identifiability_2026-06-28_to_2026-07-08/grid"
PRIMARY = "buf14_exit30_ep15"
EXTREMES = ["buf7_exit30_ep15", "buf21_exit60_ep15"]
OUT = ROOT / "outputs/policy_identifiability_2026-06-28_to_2026-07-08"


def load(cfg):
    return pd.read_csv(GRID / cfg / "leave_decisions.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", default=True)
    ap.add_argument("--full", dest="fast", action="store_false")
    args = ap.parse_args()
    nperm = 15 if args.fast else 40
    lv = load(PRIMARY)
    print(f"[temporal] primary={PRIMARY} n_leave={len(lv):,}")

    # --- effect direction + support/decomposition (primary) ---
    slopes = tp.hour_social_slopes(lv)
    slopes.to_csv(OUT / "hour_varying_effects.csv", index=False)
    support = tp.state_vs_conditional(lv)
    support.to_csv(OUT / "temporal_policy_support.csv", index=False)
    print("\n[effect direction by hour-block]"); print(slopes[["hour_block","n","leave_rate","median_crowd","nn1m_coef","crowd_effect"]].to_string(index=False))
    print("\n[state occupancy vs conditional — MARGINAL differs by hour]"); print(support.to_string(index=False))

    # --- M1 hour-varying gain + hour-label permutation null + night-dominance (primary) ---
    m1 = tp.hour_varying_gain(lv)
    hnull = tp.hour_label_permutation_null(lv, n_perm=nperm)
    dom = tp.night_dominance_audit(lv)
    dom.to_csv(OUT / "temporal_night_dominance.csv", index=False)
    print(f"\n[M1 hour-varying] held-out dbits={m1['dbits']:.4f} frac+nights={m1['frac_positive_nights']:.2f} "
          f"| hour-label-perm null z={hnull['z']}")

    # --- M2 night-slope variance (in-sample) + M3 structured context (held-out) ---
    m2 = tp.night_slope_variance(lv, n_perm=nperm)
    m3 = tp.structured_context_gain(lv)
    m3.to_csv(OUT / "night_varying_effects.csv", index=False)
    print(f"\n[M2 night-slope variance] per-night social dbits sd={m2['sd_observed']} vs null {m2['sd_null_mean']} (z={m2['z']})")
    print("[M3 structured context held-out dbits]"); print(m3.to_string(index=False))

    # --- M4 hour x structured context, GATED on M1 AND best-M3 both improving ---
    m1_ok = m1["dbits"] > 0.001
    best_ctx = m3.loc[m3["dbits"].idxmax()] if not m3.empty else None
    m3_ok = best_ctx is not None and best_ctx["dbits"] > 0.001
    m4 = {"gated_run": bool(m1_ok and m3_ok), "reason": f"M1 dbits {m1['dbits']:.4f} (>0.001? {m1_ok}); "
          f"best M3 ctx {None if best_ctx is None else best_ctx['context']} dbits "
          f"{None if best_ctx is None else round(best_ctx['dbits'],4)} (>0.001? {m3_ok})"}
    print(f"\n[M4 hour x context] {'RUN' if m4['gated_run'] else 'NOT RUN (gate not met)'} — {m4['reason']}")

    # --- sensitivity across the extreme configs (hour-varying + best structured context) ---
    sens = [{"config": PRIMARY, "m1_hour_dbits": round(m1["dbits"], 4),
             "m1_frac+nights": round(m1["frac_positive_nights"], 2),
             "best_m3_ctx": None if best_ctx is None else best_ctx["context"],
             "best_m3_dbits": None if best_ctx is None else round(float(best_ctx["dbits"]), 4)}]
    for cfg in EXTREMES:
        try:
            l2 = load(cfg)
            g = tp.hour_varying_gain(l2); mm = tp.structured_context_gain(l2)
            bc = mm.loc[mm["dbits"].idxmax()] if not mm.empty else None
            sens.append({"config": cfg, "m1_hour_dbits": round(g["dbits"], 4),
                         "m1_frac+nights": round(g["frac_positive_nights"], 2),
                         "best_m3_ctx": None if bc is None else bc["context"],
                         "best_m3_dbits": None if bc is None else round(float(bc["dbits"]), 4)})
        except Exception as e:
            sens.append({"config": cfg, "error": str(e)[:80]})
    sens_df = pd.DataFrame(sens)
    print("\n[sensitivity across configs]"); print(sens_df.to_string(index=False))

    # --- model comparison + nulls tables ---
    comp = pd.DataFrame([
        {"model": "M0_pooled", "held_out_H_bits": round(m1["H_M0"], 4), "dbits_over_M0": 0.0, "held_out_testable": True},
        {"model": "M1_hour_varying", "held_out_H_bits": round(m1["H_M1"], 4), "dbits_over_M0": round(m1["dbits"], 4), "held_out_testable": True},
        {"model": "M2_night_variance", "held_out_H_bits": None, "dbits_over_M0": None, "held_out_testable": False,
         "insample_night_slope_sd": m2["sd_observed"], "vs_null_z": m2["z"]},
        {"model": "M3_structured_ctx_best", "held_out_H_bits": None,
         "dbits_over_M0": None if best_ctx is None else round(float(best_ctx["dbits"]), 4), "held_out_testable": True,
         "best_context": None if best_ctx is None else best_ctx["context"]},
        {"model": "M4_hour_x_context", "held_out_H_bits": None, "dbits_over_M0": None, "held_out_testable": True,
         "gated_run": m4["gated_run"]},
    ])
    comp.to_csv(OUT / "temporal_model_comparison.csv", index=False)
    nulls = pd.DataFrame([
        {"null": "hour_label_permutation_within_state", "target": "M1_hour_varying", "observed_dbits": hnull["observed_dbits"], "null_mean": hnull["null_mean"], "z": hnull["z"]},
        {"null": "night_label_permutation", "target": "M2_night_variance", "observed_sd": m2["sd_observed"], "null_mean": m2["sd_null_mean"], "z": m2["z"]},
    ])
    nulls.to_csv(OUT / "temporal_nulls.csv", index=False)

    # --- plots ---
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    sl = slopes.dropna(subset=["nn1m_coef"])
    ax[0].bar(sl["hour_block"], sl["nn1m_coef"], color="#4C78A8")
    ax[0].axhline(0, color="k", lw=0.8); ax[0].set_ylabel("crowd (n_within_1m) coef")
    ax[0].set_title("Social effect on leaving by hour-block\n(negative = crowding suppresses leaving)")
    pn = pd.Series(m1["per_night"]); ax[1].bar(range(len(pn)), pn.values, color="#F58518")
    ax[1].axhline(0, color="k", lw=0.8); ax[1].set_xticks(range(len(pn))); ax[1].set_xticklabels([n[5:] for n in pn.index], rotation=45)
    ax[1].set_ylabel("held-out Δbits (M0→M1)"); ax[1].set_title("Per-night hour-varying gain\n(≈0 = one shared rule)")
    fig.tight_layout(); fig.savefig(OUT / "temporal_effects.png", dpi=140); plt.close(fig)

    summary = {"primary": PRIMARY, "n_leave": int(len(lv)), "m1_hour_varying": m1, "hour_label_null": hnull,
               "m2_night_variance": m2, "m3_structured": m3.to_dict("records"), "m4": m4,
               "effect_direction": slopes.to_dict("records"), "support": support.to_dict("records"),
               "sensitivity": sens, "night_dominance": dom.to_dict("records")}
    (OUT / "temporal_policy_results.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\ndone -> {OUT}")


if __name__ == "__main__":
    main()
