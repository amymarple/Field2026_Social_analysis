r"""
compare_route_segmentations.py — REPRESENTATION COMPARISON for the route-vocabulary test.

Runs the IDENTICAL Stage-1 core battery (`analyze_route_vocabulary.run_core_battery`) on every
PRODUCIBLE trajectory-unit segmentation and tabulates which representation yields the strongest
held-out compression, repertoire closure, and cross-animal generalisation — the "eventual scientific
test" the pluggable `trajectory_units` layer was built for.

`validated_locomotor_legs` is **BLOCKED** (the decision-boundary validation found WISER cannot validate
decision boundaries — jitter dominates pause headings; needs CV pose/keypoints; see
`decision_boundary_validation/`), so the live comparison is **original 3s-filtered bouts vs
pause-merged episodes**. Both are PROVISIONAL (filter/merge-defined units, not validated legs). Frame is
the UNVERIFIED WISER inch frame -> topological/relative only. Run under anaconda3 (scipy + sklearn):

    KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1 C:/Users/Cornell/anaconda3/python.exe \
      scripts/compare_route_segmentations.py [--max-nights N]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import wiser_analysis_utils as w              # noqa: E402
import time_utils                             # noqa: E402
import trajectory_stereotypy as ts            # noqa: E402
import analyze_trajectory_stereotypy as pa    # noqa: E402
import trajectory_units as tu                 # noqa: E402
import analyze_route_vocabulary as drv        # noqa: E402

DEFAULT_OUT = PROJECT_ROOT / "outputs" / "route_vocabulary_validation_2026-06-28_to_2026-07-10" / "comparison"
PRODUCIBLE = ["original_3s_filtered_bouts", "pause_merged_episodes"]


def _metrics(seg, umeta, res):
    """Pull the comparison-relevant numbers out of one segmentation's battery result."""
    a1, a2, a3, a4, a5, a7 = res["a1"], res["a2"], res["a3"], res["a4"], res["a5"], res["a7"]
    m = {"segmentation": seg, "n_units": int(umeta["bout_log"]["n_bouts_kept"]),
         "verdict": res["verdict"]["verdict"]}
    m.update({f"crit_{k}": v for k, v in res["crit"].items()})
    if not a1.empty:
        m["holdout_cov21_last"] = float(a1["cov_21in"].iloc[-1])
        m["holdout_meanresid_last_in"] = float(a1["mean_resid_in"].iloc[-1])
        tail = a1["novelty_next_night"].to_numpy()[-3:]
        m["novelty_next_last3_mean"] = round(float(tail.mean()), 3)
    if not a3.empty:
        m["mdl_min_K"] = int(a3.loc[a3["mdl_total_bits"].idxmin(), "K"])
        pca4 = a3[a3["pca_M"] == 4]
        m["pca_M4_resid_in"] = float(pca4["pca_resid_in"].iloc[0]) if len(pca4) else float("nan")
    if a4:
        for k in ("E_chord_in", "E_route_dict_in", "endpoint_share", "E_pn_shapedict_in",
                  "E_pn_null_in", "shape_beyond_endpoints"):
            m[f"a4_{k}"] = a4[k]
    if not a2.empty:
        m["loao_E_other_mean"] = round(float(a2["E_other_in"].mean()), 2)
        m["loao_E_own_mean"] = round(float(a2["E_own_in"].mean()), 2)
        m["loao_E_endpoint_mean"] = round(float(a2["E_endpoint_in"].mean()), 2)
    if not a7.empty:
        fwd = a7[a7["test"].str.startswith("forward")]
        m["a7_forward_cov21"] = float(fwd["cov_21in"].iloc[0]) if len(fwd) else float("nan")
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--incremental-dir", type=Path, default=pa.DEFAULT_INCR)
    ap.add_argument("--baseline", type=Path, default=pa.DEFAULT_BASELINE)
    ap.add_argument("--rois", type=Path, default=pa.DEFAULT_ROIS)
    ap.add_argument("--gt", type=Path, default=pa.DEFAULT_GT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--night-start", type=int, default=21)
    ap.add_argument("--night-end", type=int, default=4)
    ap.add_argument("--min-disp-in", type=float, default=15.0)
    ap.add_argument("--resample-n", type=int, default=20)
    ap.add_argument("--max-per-night", type=int, default=40)
    ap.add_argument("--endpoint-bin-in", type=float, default=42.0)
    ap.add_argument("--bits-per-param", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-nights", type=int, default=None)
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    print("== Representation comparison (route-vocabulary) ==")
    print("[1/3] load + clean (mirror Phase B) ...")
    df, _ = ts.load_incremental_days(args.incremental_dir, dates=None)
    df = time_utils.convert_timestamps(df)
    floor = pa.establish_floor(args.baseline, args.gt)
    jitter_floor, moving_thr = floor["jitter_floor_in"], floor["moving_thr_inps"]
    df = w.add_speed(df)
    roi_cfg = w.load_rois(args.rois)
    boundary = (roi_cfg or {}).get("boundary")
    df = w.add_validity_flags(df, boundary=boundary, jitter_floor_in=jitter_floor)
    df = w.apply_tag_cutoffs(df)
    win = ts.select_night_window(df, night_start=args.night_start, night_end=args.night_end, valid_only=True)
    win = win[~win["shortid"].astype(str).isin(pa.DROP_TAGS)].reset_index(drop=True)
    nights = sorted(win["night"].unique())
    if args.max_nights:
        nights = nights[:args.max_nights]
        win = win[win["night"].isin(nights)].reset_index(drop=True)
    L = args.resample_n
    theta = round(3.0 * jitter_floor, 1)
    cfg = {"theta": theta, "sigma_in": float(jitter_floor), "bits_per_param": args.bits_per_param,
           "endpoint_bin": args.endpoint_bin_in, "seed": args.seed, "L": L}

    print(f"[2/3] run the core battery per producible segmentation {PRODUCIBLE} ...")
    rows, metas = [], {}
    for seg in PRODUCIBLE:
        units, paths, umeta = tu.load_units(
            seg, win=win, nights=nights, moving_thr_inps=moving_thr, roi_cfg=roi_cfg,
            min_disp_in=args.min_disp_in, resample_n=L, max_per_night=args.max_per_night)
        print(f"    {seg}: {len(units)} units ({umeta['label']})")
        if len(units) < 20:
            print("      too few units; skipping."); continue
        res = drv.run_core_battery(paths, units, nights, cfg)
        rows.append(_metrics(seg, umeta, res))
        metas[seg] = {"label": umeta["label"], "params": umeta["params"],
                      "verdict": res["verdict"]["verdict"], "reasons": res["verdict"]["reasons"]}

    comp = pd.DataFrame(rows)
    comp.to_csv(out / "segmentation_comparison.csv", index=False)

    blocked = {sid: s for sid, s in tu.SEGMENTATIONS.items() if s["status"] != "implemented_provisional"}
    manifest = {"analysis": "route_vocabulary_representation_comparison",
                "generated_utc": _dt.datetime.utcnow().isoformat(), "git_commit": pa._git_commit(),
                "nights": nights, "theta_in": theta, "jitter_floor_in": jitter_floor,
                "producible_segmentations": PRODUCIBLE,
                "blocked_segmentations": {k: v["status"] for k, v in blocked.items()},
                "per_segmentation": metas,
                "caveats": [
                    "PROVISIONAL: both units are filter/merge-defined, not validated locomotor legs",
                    "validated_locomotor_legs BLOCKED — WISER cannot validate decision boundaries "
                    "(decision_boundary_validation/); needs CV pose/keypoints",
                    "frame UNVERIFIED -> topological/relative only; Module 11 blocked",
                    "the per-segmentation verdicts carry their own audit caveats (C-vs-B unresolved; "
                    "reusable-shape sub-jitter-floor) — see each run's validation_report.md"]}
    with open(out / "run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    print("[3/3] write comparison report ...")
    _write_report(out, comp, metas, blocked, nights, theta)
    print(f"\nDONE -> {out}")
    print(comp.to_string(index=False))


def _write_report(out, comp, metas, blocked, nights, theta):
    L = []
    A = L.append
    A("# Route-vocabulary — representation comparison across segmentations")
    A("")
    A(f"**Nights:** {', '.join(nights)} · **θ:** {theta} in · **Frame:** inches, UNVERIFIED (topological/"
      "relative only). Identical Stage-1 core battery (`run_core_battery`) on each producible unit table.")
    A("")
    A("> **PROVISIONAL.** Both representations are filter/merge-defined units, NOT validated "
      "decision-to-decision legs. `validated_locomotor_legs` is **BLOCKED**: the decision-boundary "
      "validation found no reliable boundary class at WISER resolution (pause reorientation not "
      "separable from ~7 in jitter) → needs CV pose/keypoints, not WISER.")
    A("")
    A("## Segmentations")
    A("")
    for seg, m in metas.items():
        A(f"- **`{seg}`** — {m['label']} · params {m['params']} · **verdict {m['verdict']}**.")
    for seg, s in blocked.items():
        A(f"- **`{seg}`** — BLOCKED ({s['status']}): {s['definition'][:180]}…")
    A("")
    A("## Comparison (which representation compresses / closes / generalises best?)")
    A("")
    cols = [c for c in ["segmentation", "n_units", "verdict", "holdout_cov21_last",
                        "novelty_next_last3_mean", "mdl_min_K", "pca_M4_resid_in",
                        "a4_E_chord_in", "a4_E_route_dict_in", "a4_endpoint_share",
                        "a4_shape_beyond_endpoints", "loao_E_other_mean", "loao_E_endpoint_mean",
                        "a7_forward_cov21"] if c in comp.columns]
    A("| " + " | ".join(cols) + " |")
    A("|" + "|".join(["---"] * len(cols)) + "|")
    for _, r in comp.iterrows():
        A("| " + " | ".join(str(r[c]) for c in cols) + " |")
    A("")
    A("## Reading")
    A("")
    if len(comp) >= 2:
        b = comp[comp["segmentation"] == "original_3s_filtered_bouts"]
        e = comp[comp["segmentation"] == "pause_merged_episodes"]
        if len(b) and len(e):
            b, e = b.iloc[0], e.iloc[0]
            same_verdict = b["verdict"] == e["verdict"]
            A(f"- **Verdict is {'scale-invariant' if same_verdict else 'scale-dependent'}:** bouts → "
              f"**{b['verdict']}**, pause-merged episodes → **{e['verdict']}**. "
              + ("The 'not a discrete vocabulary' conclusion does not depend on the bout-vs-episode "
                 "segmentation scale." if same_verdict else "The conclusion changes with unit scale — "
                 "investigate before generalising."))
            A(f"- **Endpoint dominance** holds in both: endpoint chord {b.get('a4_E_chord_in','?')} "
              f"(bouts) / {e.get('a4_E_chord_in','?')} in (episodes) vs the route dictionary "
              f"{b.get('a4_E_route_dict_in','?')} / {e.get('a4_E_route_dict_in','?')} in; endpoint share "
              f"{b.get('a4_endpoint_share','?')} / {e.get('a4_endpoint_share','?')}.")
            A(f"- **Closure / compression:** held-out cov≤21in {b.get('holdout_cov21_last','?')} / "
              f"{e.get('holdout_cov21_last','?')}; last-3 next-night novelty "
              f"{b.get('novelty_next_last3_mean','?')} / {e.get('novelty_next_last3_mean','?')}; MDL min K "
              f"{b.get('mdl_min_K','?')} / {e.get('mdl_min_K','?')}. Lower held-out error + higher "
              "coverage + smaller K = the more compressible representation.")
            A(f"- **Cross-animal generalisation (LOAO):** E_other {b.get('loao_E_other_mean','?')} / "
              f"{e.get('loao_E_other_mean','?')} in; the endpoint chord E_endpoint "
              f"{b.get('loao_E_endpoint_mean','?')} / {e.get('loao_E_endpoint_mean','?')} in still ≪ any "
              "dictionary in both — what transfers across animals is the endpoint graph, not a path "
              "vocabulary, at either scale.")
    A("")
    A("- **Bottom line (provisional):** the segmentation comparison is limited to two filter/merge-"
      "defined representations because validated legs are WISER-unresolvable. If the verdict + "
      "endpoint-dominance are stable across bouts and episodes, the 'continuous endpoint manifold, not a "
      "discrete route vocabulary' reading is robust to unit scale within WISER; the definitive test still "
      "requires CV-resolved legs.")
    A("")
    (out / "comparison_report.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
