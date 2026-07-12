r"""
build_search_excursions.py — Phase 4 driver: return-vs-explore (module 9) + coarse area-restricted-vs-
global search geometry (module 10), GATE-FIRST, on the extended 11-night data.

Reads the module-6 validated settlement transitions (``settlement_transitions.csv``) for the excursion
substrate and reloads the cleaned WISER fixes (shared ``build_decision_tables.load_clean_stream``) only
for the coarse module-10 path geometry. Module 9 is WISER-native (visit history); module 10 is capped at
COARSE radius/coverage by the decision_boundary_validation verdict (fine turn/ARS structure is
jitter-unresolvable). Neither module asserts motivation, curiosity, or a foraging strategy.

    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\build_search_excursions.py
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
import time as _time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import search_excursions as se                        # noqa: E402
from build_decision_tables import (load_clean_stream, DEFAULT_INCR, DEFAULT_WEATHER,  # noqa: E402
                                   NIGHTS)


def _git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT)).decode().strip()
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transitions", type=Path,
                    default=ROOT / "outputs/destination_settlement_2026-06-28_to_2026-07-08/settlement_transitions.csv")
    ap.add_argument("--bouts", type=Path,
                    default=ROOT / "outputs/locomotor_initiation_2026-06-28_to_2026-07-08/bouts.csv")
    ap.add_argument("--incremental-dir", type=Path, default=DEFAULT_INCR)
    ap.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER)
    ap.add_argument("--env-map", type=Path,
                    default=ROOT / "configs/environment_map/2026-06-28_to_2026-07-08.yaml")
    ap.add_argument("--rois", type=Path, default=ROOT / "configs/wiser_rois.json")
    ap.add_argument("--nights", nargs="*", default=NIGHTS)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs/search_excursions_2026-06-28_to_2026-07-08")
    ap.add_argument("--k-recent", type=int, default=3)
    ap.add_argument("--n-perm", type=int, default=200)
    ap.add_argument("--no-geometry", action="store_true", help="skip module 10 (no fix reload)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    _t0 = _time.time(); _prog = open(args.out / "_progress.log", "w", buffering=1)

    def plog(m):
        line = f"[{_time.time()-_t0:6.1f}s] {m}"; print(line, flush=True); _prog.write(line + "\n"); _prog.flush()

    trans = pd.read_csv(args.transitions)
    plog(f"[1/4] MODULE 9 return-vs-explore: {len(trans)} transitions "
         f"({trans['transition_type'].value_counts().to_dict()})")
    ex = se.build_excursions(trans)
    ex_hist = se.attach_site_history(ex, trans, k_recent=args.k_recent)
    ex_hist.to_csv(args.out / "excursions_return_explore.csv", index=False)
    gate9 = se.return_explore_gate(ex, trans, k_recent=args.k_recent, n_perm=args.n_perm)
    (args.out / "return_explore_gate.json").write_text(json.dumps(gate9, indent=2, default=str), encoding="utf-8")
    pd.DataFrame(gate9["per_night"]).to_csv(args.out / "return_explore_per_night.csv", index=False)
    plog(f"      named-dest excursions={gate9['n_excursions']} over {gate9['n_nights']} nights | "
         f"return_rate={gate9['pooled_return_rate']} novel_rate={gate9['pooled_novel_rate']} "
         f"same_site_return_frac={gate9['same_site_return_frac']}")
    plog(f"      vs layout: p={gate9['signtest_vs_layout']['p']} (mean e={gate9['signtest_vs_layout']['mean']:.3f}, "
         f"{gate9['signtest_vs_layout']['n_pos']}/{gate9['signtest_vs_layout']['n_nights']}) beats_layout={gate9['beats_layout_base_rate']}")
    plog(f"      vs hist-shuffle: p={gate9['signtest_vs_histshuffle']['p']} beats_hist={gate9['beats_history_shuffle']}")
    plog(f"      MODULE 9 VERDICT: {gate9['verdict']}")

    gate10 = {"skipped": True}
    if not args.no_geometry:
        plog("[2/4] MODULE 10 coarse search geometry: reload cleaned fixes")
        S = load_clean_stream(args.incremental_dir, args.weather_dir, args.env_map, args.rois,
                              list(args.nights), plog=plog)
        fixes = S["win"][["shortid", "night", "datetime", "x", "y"]].copy()
        plog("[3/4] coarse per-BOUT path geometry (DBV-capped: radius/coverage only)")
        bouts = pd.read_csv(args.bouts)
        geom = se.excursion_geometry(bouts, fixes)
        geom.to_csv(args.out / "excursion_geometry.csv", index=False)
        gate10 = se.search_geometry_gate(geom)
        (args.out / "search_geometry_gate.json").write_text(json.dumps(gate10, indent=2, default=str), encoding="utf-8")
        plog(f"      bout geometry n={gate10['n']} resolvable_frac={gate10['resolvable_frac']} "
             f"in_place_radius={gate10.get('in_place_median_radius_in')} "
             f"relocating_radius={gate10.get('relocating_median_radius_in')}")
        plog(f"      MODULE 10 MEASUREMENT VERDICT: {gate10['measurement_verdict']}")
    else:
        plog("[2-3/4] MODULE 10 skipped (--no-geometry)")

    plog("[4/4] report + manifest")
    _write_report(args.out, gate9, gate10, args)
    manifest = {
        "analysis": "behavioral_policy/phase4_search_excursions/build+gate",
        "generated_by": "build_search_excursions.py", "git_commit": _git_commit(),
        "generated_utc": datetime.datetime.utcnow().isoformat(),
        "modules": [9, 10], "module_names": ["return_versus_explore", "area_restricted_vs_global_search"],
        "input_transitions": str(args.transitions.resolve()), "nights": list(args.nights),
        "params": {"k_recent": args.k_recent, "n_perm": args.n_perm},
        "module9": {k: gate9[k] for k in ("n_excursions", "n_nights", "pooled_return_rate",
                                          "pooled_novel_rate", "same_site_return_frac",
                                          "beats_layout_base_rate", "beats_history_shuffle",
                                          "gate_signal", "recency_specific", "verdict")},
        "module10": ({"n": gate10.get("n"), "resolvable_frac": gate10.get("resolvable_frac"),
                      "measurement_verdict": gate10.get("measurement_verdict")}
                     if not gate10.get("skipped") else {"skipped": True}),
        "caveats": [
            "Module 9: novelty/return defined on the ROI set in the UNVERIFIED inch frame; unvisited != "
            "avoided (a coverage gap, not a choice). 'return-vs-explore tendency', not curiosity/novelty-"
            "seeking as a drive (association, not motivation).",
            "Module 10: COARSE geometry only — fine turn/ARS structure is NOT resolvable at the ~7 in "
            "jitter floor (decision_boundary_validation); radii are RELATIVE, jitter inflates small ones. "
            "Geometry, not an inferred foraging strategy or optimal search.",
            "Whole nights are the outer inference blocks; single 11-night pilot.",
        ],
    }
    (args.out / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    plog(f"done -> {args.out}")


def _write_report(out, g9, g10, args):
    sl = g9["signtest_vs_layout"]; sh = g9["signtest_vs_histshuffle"]
    header = ("# Return-vs-explore & coarse search geometry (Phase 4, Modules 9 & 10, 11 nights)\n\n"
              "**Status:** ⚠️ candidate (gate-first). Module 9 (return-vs-explore) is WISER-native; Module "
              "10 (area-restricted-vs-global search) is capped at COARSE geometry by the "
              "decision_boundary_validation verdict. Extended 06-28→07-08 window. "
              f"Generated {datetime.datetime.utcnow().isoformat()}. Frame UNVERIFIED (topology + coarse "
              "distance only); whole-night sign tests; association not motivation.\n")
    defn = r"""
## Definitions (formula + plain text)

- **Named-destination excursion** — a validated departure (module 6) that settles at a NAMED site: a
  ``relocation`` (different site) or a ``same_site_return`` (back to the same site). The denominator for
  return-vs-explore. Open-field terminations and pass-throughs are NOT return/explore decisions.
- **Prior site-visit history** — for an excursion departing at $t$, the animal's sequence of settled
  sites at times $t' < t$ (strictly prior; no leakage).
- **is_return** — the destination is in the animal's last $k$=%d DISTINCT settled sites (RECENCY) OR its
  prior-visit frequency there exceeds the uniform per-site share $1/S$ (FREQUENCY), $S$ = number of named
  sites. **is_explore** = otherwise; **dest_novel** = never settled there before.
- **Layout base-rate null** — replace the destination with a draw from the GLOBAL site-popularity
  distribution and recompute is_return against the SAME prior history. Answers: does the animal return
  MORE than site popularity alone would produce?
- **History-shuffle null** — permute the animal's residence ORDER (keeps site composition/frequency,
  destroys recency) and recompute is_return. Beating it means the return is RECENCY-specific, not merely
  frequency-driven.
- **Night-block effect** $e = \text{rate}_{obs} - \text{rate}_{null}$ per night; significance = a binomial
  SIGN TEST on $e$ across the whole nights (the outer blocks), NOT a per-excursion test.
- **Coarse search geometry** (module 10, per excursion, from the contiguous fix segment): ``radius_in`` =
  max distance from the start; ``path_len_in`` = summed step length; ``net_disp_in`` = start→end straight
  line; ``straightness`` = net/path $\in[0,1]$ (low = tortuous/looping). ``resolvable`` = radius
  $\ge 3\times$ the ~7 in jitter floor. NO turn-by-turn kinematics (DBV-blocked).
""" % args.k_recent
    body = f"""

## Module 9 — return vs explore

- Named-destination excursions: **{g9['n_excursions']}** over **{g9['n_nights']}** nights
  (pooled return rate **{g9['pooled_return_rate']:.2f}**, novelty rate **{g9['pooled_novel_rate']:.2f}**,
  same-site-return fraction **{g9['same_site_return_frac']:.2f}**).
- **vs the layout base rate:** night-block sign test p = **{sl['p']}** (mean e = {sl['mean']:.3f},
  {sl['n_pos']}/{sl['n_nights']} nights positive) → beats layout: **{g9['beats_layout_base_rate']}**.
- **vs history-shuffle (recency specificity):** p = **{sh['p']}** → beats shuffle:
  **{g9['beats_history_shuffle']}** (recency-specific: {g9['recency_specific']}).
- **Verdict:** {g9['verdict']}

## Module 10 — coarse area-restricted-vs-global search geometry

{_g10_md(g10)}

## Scope

Module 9: return/novelty are defined on the ROI set in the UNVERIFIED inch frame; an unvisited site is a
coverage gap, not a demonstrated avoidance. "return-vs-explore tendency / site-history dependence" only —
NOT curiosity or novelty-seeking as a drive. Module 10: coarse radius/coverage only; fine ARS turn
structure is jitter-unresolvable (DBV); geometry, not a foraging strategy. Group-level, single 11-night
pilot; whole nights are the outer blocks.
"""
    (out / "search_excursions_report.md").write_text(header + defn + body, encoding="utf-8")


def _g10_md(g10):
    if g10.get("skipped"):
        return "_skipped (--no-geometry)._"
    bt = g10.get("by_mode", {})
    rows = "\n".join(f"| {t} | {v['n']} | {v['median_radius_in']} | {v['median_straightness']} "
                     f"| {v['resolvable_frac']} |" for t, v in bt.items())
    return (f"Coarse path geometry of {g10['n']} locomotor bouts ({g10['resolvable_frac']:.0%} clear 3 "
            f"jitter floors).\n\n| bout mode | n | median radius (in) | median straightness | resolvable "
            f"frac |\n|---|---|---|---|---|\n{rows}\n\n"
            f"- in_place median radius = {g10.get('in_place_median_radius_in')} in; "
            f"relocating = {g10.get('relocating_median_radius_in')} in "
            f"({g10.get('coarse_contrast_note')}).\n"
            f"- **Measurement verdict:** {g10['measurement_verdict']}")


if __name__ == "__main__":
    main()
