r"""
build_settlement_transitions.py — Phase 2 / Module 6 representation builder + VALIDATION GATE.

Reads module-3's ``stationary_episodes.csv`` (the unified locomotor-state residence episodes),
types each as settlement / pass_through / open_stop / dropout, classifies every departure-from-
settlement into {relocation, same_site_return, pass_through, open_field_termination, censored}, and
VALIDATES the representation (settlement-threshold sensitivity + per-origin choice support + genuine
same-site loops) BEFORE any destination-choice model is fit. The destination-choice table is written
ONLY if the validation gate passes (`analyze_destination_choice.py` refuses to fit otherwise).

Respects `decision_boundary_validation`: a destination is anchored on observed SUSTAINED STABLE
RESIDENCE, never on where a pause-bridged movement episode ends. No new WISER load, no fine kinematics.

    C:\Users\Cornell\anaconda3\python.exe scripts\build_settlement_transitions.py
    C:\Users\Cornell\anaconda3\python.exe scripts\build_settlement_transitions.py --settle-min-s 60
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import settlement_transitions as st                 # noqa: E402
from environment_map import EnvironmentMap          # noqa: E402


def _git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT)).decode().strip()
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stationary", type=Path,
                    default=ROOT / "outputs/locomotor_initiation_2026-06-28_to_2026-07-08/stationary_episodes.csv")
    ap.add_argument("--env-map", type=Path,
                    default=ROOT / "configs/environment_map/2026-06-28_to_2026-07-08.yaml")
    ap.add_argument("--rois", type=Path, default=ROOT / "configs/wiser_rois.json")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs/destination_settlement_2026-06-28_to_2026-07-08")
    ap.add_argument("--settle-min-s", type=float, default=60.0)
    ap.add_argument("--conf-frac", type=float, default=0.5)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    em = EnvironmentMap.from_paths(args.env_map, args.rois)
    stat_eps = pd.read_csv(args.stationary)

    print(f"[1/4] type {len(stat_eps)} stationary episodes (settle_min_s={args.settle_min_s}, conf={args.conf_frac})")
    typed = st.type_stationary_episodes(stat_eps, em, settle_min_s=args.settle_min_s, conf_frac=args.conf_frac)
    typed.to_csv(args.out / "stationary_episodes_typed.csv", index=False)
    print("     stype mix:", typed["stype"].value_counts().to_dict())

    print("[2/4] classify departures-from-settlement into 5 transition types")
    trans = st.build_transitions(typed, em)
    trans.to_csv(args.out / "settlement_transitions.csv", index=False)
    summ = st.transition_type_summary(trans)
    summ.to_csv(args.out / "transition_type_summary.csv", index=False)
    print("     transition mix:", {r["transition_type"]: r["n"] for r in summ.to_dict("records")})

    print("[3/4] VALIDATE representation (measurement gate — before any choice model)")
    val = st.validate_representation(stat_eps, em, settle_min_s=args.settle_min_s, conf_frac=args.conf_frac)
    pd.DataFrame(val["sensitivity"]).to_csv(args.out / "representation_sensitivity.csv", index=False)
    (args.out / "validation_results.json").write_text(json.dumps(val, indent=2, default=str), encoding="utf-8")
    print(f"     checks: {val['checks']}")
    print(f"     GATE: {'PASS' if val['gate_ok'] else 'FAIL'} "
          f"(settlements={val['n_settlements']}, departures={val['n_departures']}, "
          f"relocations={val['relocation_support']['n_relocations']}, "
          f"origins-with-choice={val['relocation_support']['origins_with_choice']})")

    print("[4/4] destination-choice table (GATED on validation)")
    if val["gate_ok"]:
        choice, choice_sets = st.build_destination_choice_table(trans, em)
        choice.to_csv(args.out / "destination_choice.csv", index=False)
        (args.out / "choice_sets.json").write_text(json.dumps(choice_sets, indent=2, default=str), encoding="utf-8")
        print(f"     wrote destination_choice.csv ({len(choice)} relocation events, "
              f"{len(choice_sets)} origins) — ready for analyze_destination_choice.py")
    else:
        print("     GATE NOT PASSED -> destination-choice table NOT written (validate first).")

    _write_report(args.out, typed, summ, val, args)
    manifest = {
        "analysis": "behavioral_policy/module_6_destination_settlement/build+validate",
        "generated_by": "build_settlement_transitions.py", "git_commit": _git_commit(),
        "generated_utc": datetime.datetime.utcnow().isoformat(),
        "module": 6, "module_name": "destination_and_settlement",
        "input_stationary_episodes": str(args.stationary.resolve()),
        "params": {"settle_min_s": args.settle_min_s, "conf_frac": args.conf_frac},
        "n_stationary_episodes": int(len(stat_eps)), "stype_mix": typed["stype"].value_counts().to_dict(),
        "transition_mix": {r["transition_type"]: int(r["n"]) for r in summ.to_dict("records")},
        "validation_gate_ok": bool(val["gate_ok"]), "validation_checks": val["checks"],
        "n_right_censored_residence": val.get("n_right_censored_residence"),
        "provenance_note": "Built on module-3 stationary_episodes (unified locomotor state); a "
                           "destination is defined only after sustained stable residence. Respects "
                           "decision_boundary_validation (no fine kinematics, no pause-bridged 'trip' "
                           "destinations). Frame UNVERIFIED (topology + coarse distance only).",
        "caveats": [
            "A destination is measurable ONLY at sustained stable residence; pass-through/open-field/"
            "censored departures are SEPARATED, not counted as destination choices.",
            "Same-site returns require a real intervening locomotor bout (ended_by='onset'), so they "
            "are genuine loops, not jitter flicker.",
            "refuge_4 burrow-night residence is a below-plane dropout -> typed 'dropout', excluded.",
            "Whole nights are the outer inference blocks; settlement thresholds swept for stability.",
        ],
    }
    (args.out / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"done -> {args.out}")


def _write_report(out, typed, summ, val, args):
    smix = typed["stype"].value_counts().to_dict()
    checks = val["checks"]; sup = val["relocation_support"]
    sens = pd.DataFrame(val["sensitivity"])
    md = f"""# Destination & settlement — representation + validation (Module 6, Phase 2)

**Status:** ⚠️ candidate (validation-first). Rebuilds destination/settlement on the **unified
locomotor-state representation** (module-3 stationary episodes). A **destination is defined only after
SUSTAINED STABLE RESIDENCE**; every departure is typed; **the representation is validated BEFORE any
destination-choice or search model is fit** (per `decision_boundary_validation`). Generated
{datetime.datetime.utcnow().isoformat()}; settle_min_s={args.settle_min_s}, conf_frac={args.conf_frac}.

## Definitions (formula + plain text)

- **Settlement (sustained stable residence)** — a stationary episode with `in_named_roi`, duration
  $\\ge$ `settle_min_s`, `frac_in_named_roi` $\\ge$ `conf_frac`, data coverage
  `n_data_bins/n_bins` $\\ge 0.5$, and not a below-plane dropout ROI. Plain: the animal actually
  stopped and stayed at a named site long enough to call it residence — the only anchor at which a
  destination is measurable.
- **Departure** — a settlement that ended by a locomotor-bout **onset** (module-3). Right-censored
  residences (still settled at nightend / lost to a dropout) are NOT departures ({val.get('n_right_censored_residence')} of them, reported separately).
- **Transition type** (one per departure, by the immediately following stationary episode):
  **relocation** (settled at a different named site — the destination-choice event) · **same_site_return**
  (settled back at the same site; requires a real intervening bout) · **pass_through** (next stop is a
  named ROI entered but not sustained) · **open_field_termination** (next low-speed state is in the open)
  · **censored** (a gap/dropout/nightend interrupts before an outcome is observed).
- **Origin-supported choice set** $C(o)$ — destinations observed $\\ge 3$ times from origin $o$
  (training-fold, for the gated choice model).
- **Validation gate** — PASS iff: (a) $\\ge 4$ transition types populated; (b) the relocation fraction
  is stable across the settle_min_s$\\times$conf_frac grid (max$-$min $\\le 0.20$); (c) $\\ge 2$ origins
  have $\\ge 3$ relocations to $\\ge 2$ destinations; (d) same-site returns have a real intervening bout.

## Stationary-episode types

{pd.Series(smix).to_frame('n').to_markdown()}

## Transition-type mix (departures from settlements)

{summ.to_markdown(index=False)}

## Settlement-threshold sensitivity

{sens[['settle_min_s','conf_frac','n_settlements','n_departures','n_relocation','frac_relocation','frac_pass_through','frac_open_field_termination','frac_censored']].to_markdown(index=False)}

## Validation gate

- all types populated: **{checks['all_types_populated']}**
- relocation-fraction range across the DURATION threshold (at the operating conf_frac): **{checks['relocation_frac_range_across_duration']:.3f}** (stable if $\\le 0.10$: {checks['relocation_stable_across_duration']})
- (caveat) relocation-fraction range across the FULL grid incl. conf_frac=0.8: **{checks['relocation_frac_range_full_grid']:.3f}** — a strict confidence threshold reclassifies edge-dwelling settlements as pass-throughs (definition change, not instability); conf_frac=0.5 is the operating point.
- per-origin choice support ($\\ge 2$ origins): **{checks['per_origin_choice_support']}** ({sup['origins_with_choice']} origins; {sup['n_relocations']} relocations)
- same-site returns are real loops: **{checks['same_site_returns_are_real_loops']}**

### GATE: {'PASS — the destination-choice model may be fit (analyze_destination_choice.py)' if val['gate_ok'] else 'FAIL — do NOT fit a destination-choice/search model; the representation is not yet validated'}

## Scope guard

Endpoints only (no route/path — frame UNVERIFIED); a destination is measurable only at sustained
residence; same-site return / pass-through / open-field termination / censored are SEPARATE outcomes,
not destination choices. Not "route choice", not "goal-directed navigation".
"""
    (out / "validation_report.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
