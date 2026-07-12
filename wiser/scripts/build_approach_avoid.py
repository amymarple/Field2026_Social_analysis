r"""
build_approach_avoid.py — Phase 3 / Module 7 builder + MEASUREMENT GATE (run under anaconda3/cv).

Reads module-3 ``bouts.csv`` (validated active bouts) + re-loads the cleaned WISER fix stream (shared
``build_decision_tables.load_clean_stream``), builds the coarse heading-free in-bout approach/avoid
context, and runs the measurement gate BEFORE any model:
  * direction-randomized (displacement-matched) null  -> is there a toward/away bias above geometry?
  * day-shuffle (same partner, same hour, different night) -> is it real-time SOCIAL vs shared-resource
    LAYOUT?
The approach/avoid MODEL table is written only if the gate certifies a SOCIAL signal; otherwise the
honest verdict (layout-only, or no signal) is recorded and no model is fit.

Respects decision_boundary_validation: no heading/bearing; only >= 1 m, jitter-safe net displacement.

    C:\Users\Cornell\anaconda3\python.exe scripts\build_approach_avoid.py
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

import approach_avoid as aa                                       # noqa: E402
from build_decision_tables import load_clean_stream, DEFAULT_INCR, DEFAULT_WEATHER, NIGHTS  # noqa: E402


def _git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT)).decode().strip()
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bouts", type=Path,
                    default=ROOT / "outputs/locomotor_initiation_2026-06-28_to_2026-07-08/bouts.csv")
    ap.add_argument("--incremental-dir", type=Path, default=DEFAULT_INCR)
    ap.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER)
    ap.add_argument("--env-map", type=Path,
                    default=ROOT / "configs/environment_map/2026-06-28_to_2026-07-08.yaml")
    ap.add_argument("--rois", type=Path, default=ROOT / "configs/wiser_rois.json")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs/approach_avoid_2026-06-28_to_2026-07-08")
    ap.add_argument("--nights", nargs="*", default=NIGHTS)
    ap.add_argument("--min-disp-in", type=float, default=14.0)
    ap.add_argument("--n-perm-dir", type=int, default=150)
    ap.add_argument("--n-perm-day", type=int, default=50)
    ap.add_argument("--min-pairs-per-night", type=int, default=15)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    _t0 = _time.time(); _prog = open(args.out / "_progress.log", "w", buffering=1)

    def plog(m):
        line = f"[{_time.time()-_t0:6.1f}s] {m}"; print(line, flush=True); _prog.write(line+"\n"); _prog.flush()

    plog("[1/4] load bouts + cleaned fixes")
    bouts = pd.read_csv(args.bouts)
    S = load_clean_stream(args.incremental_dir, args.weather_dir, args.env_map, args.rois,
                          list(args.nights), plog=plog)
    win, em = S["win"], S["em"]
    fixes = win[["shortid", "night", "datetime", "x", "y"]].copy()
    plog(f"      {len(bouts)} bouts, {len(fixes):,} fixes")

    plog("[2/4] coarse heading-free in-bout approach/avoid context (>= 1 m partners)")
    ctx = aa.bout_approach_context(bouts, fixes, em, min_disp_in=args.min_disp_in)
    ctx.to_csv(args.out / "approach_context.csv", index=False)
    plog(f"      {len(ctx)} (bout, partner) pairs (disp >= {args.min_disp_in} in, partner >= 1 m)")

    plog("[3/4] NIGHT-BLOCK MEASUREMENT GATE (per-night effect + sign test; NOT pseudoreplicated pair-z)")
    gate = aa.measurement_gate(ctx, fixes, n_perm_dir=args.n_perm_dir, n_perm_day=args.n_perm_day,
                               min_pairs_per_night=args.min_pairs_per_night)
    (args.out / "gate_results.json").write_text(json.dumps(gate, indent=2, default=str), encoding="utf-8")
    nb = pd.DataFrame(gate["night_block"])
    nb.to_csv(args.out / "night_block_gate.csv", index=False)
    pn = gate["pooled_night"]
    plog(f"      pairs={gate['n_pairs']} over {pn.get('n_nights')} night-blocks")
    plog("      per-bin (e_dir mean/signtest-p | e_day mean/signtest-p | net):")
    for r in gate["night_block"]:
        plog(f"        {r.get('bin'):6s}: e_dir={r.get('e_dir_mean')} (p={r.get('e_dir_signtest_p')}, {r.get('e_dir_n_pos')}/{r.get('n_nights')}) "
             f"| e_day={r.get('e_day_mean')} (p={r.get('e_day_signtest_p')}, {r.get('e_day_n_pos')}/{r.get('n_nights')}) | {r.get('net_sign')}")
    plog(f"      gate_resolvable={gate['gate_resolvable']} gate_social={gate['gate_social']} "
         f"distance_dependent={gate['distance_dependent']} bin_signs={gate['social_bin_signs']}")
    plog(f"      VERDICT: {gate['verdict']}")

    plog("[4/4] gated model table + report")
    if gate["gate_social"]:
        mt = aa.build_model_table(ctx)
        mt.to_csv(args.out / "approach_model_table.csv", index=False)
        plog(f"      GATE_SOCIAL -> wrote approach_model_table.csv ({len(mt)} rows) for the held-out model")
    else:
        plog("      GATE_SOCIAL not met -> NO model table (approach/avoid is not a certified social signal)")

    _write_report(args.out, ctx, gate, nb, args)
    manifest = {
        "analysis": "behavioral_policy/module_7_approach_avoid/build+gate",
        "generated_by": "build_approach_avoid.py", "git_commit": _git_commit(),
        "generated_utc": datetime.datetime.utcnow().isoformat(),
        "module": 7, "module_name": "approach_avoid_group_partners",
        "input_bouts": str(args.bouts.resolve()), "nights": list(args.nights),
        "params": {"min_disp_in": args.min_disp_in, "min_partner_dist_in": aa.RADIUS_1M_IN,
                   "n_perm_dir": args.n_perm_dir, "n_perm_day": args.n_perm_day,
                   "min_pairs_per_night": args.min_pairs_per_night},
        "n_pairs": int(len(ctx)),
        "gate": {k: v for k, v in gate.items() if k != "night_block"},
        "night_block": gate["night_block"],
        "caveats": [
            "HEADING-FREE by design: decision_boundary_validation falsified reliable heading/bearing at "
            "WISER resolution, so approach/avoid is a coarse NET distance change over a bout, >= 1 m only.",
            "Approach to the PARTNER's start position isolates the focal's contribution but the partner "
            "also moves; this is coarse net proximity change, not fine steering.",
            "Association, NOT motivation: 'approach/avoid tendency', never 'the rat chooses to approach' "
            "or 'attraction/aversion'. Pair-resolved (dyadic) only if module 13 passes.",
            "Frame UNVERIFIED (topology + coarse distance only); whole nights are the outer blocks.",
        ],
    }
    (args.out / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    plog(f"done -> {args.out}")


def _write_report(out, ctx, gate, nb, args):
    pn = gate["pooled_night"]
    nb_md = "\n".join(
        f"| {r.get('bin')} | {r.get('n_pairs')} | {r.get('n_nights')} | {r.get('e_dir_mean')} | "
        f"{r.get('e_dir_n_pos')}/{r.get('n_nights')} | {r.get('e_dir_signtest_p')} | {r.get('e_day_mean')} | "
        f"{r.get('e_day_n_pos')}/{r.get('n_nights')} | {r.get('e_day_signtest_p')} | {r.get('net_sign')} |"
        for r in nb.to_dict("records")) if not nb.empty else ""
    header = ("# In-bout approach/avoid — coarse, heading-free, NIGHT-BLOCK (Module 7, Phase 3)\n\n"
              "**Status:** ⚠️ candidate (measurement-gate). WITHIN validated active bouts only; a "
              "**coarse, heading-free** net-distance-change approach/avoid (decision_boundary_validation "
              "falsified reliable heading at WISER resolution). Significance is tested at the "
              "**NIGHT-BLOCK level** (the ~8 nights are the outer units) — a per-night effect + a "
              "sign test — NOT a pseudoreplicated per-pair z. Gate runs BEFORE any model. Generated "
              f"{datetime.datetime.utcnow().isoformat()}; min_disp={args.min_disp_in} in.\n")
    defn = r"""
## Definitions (formula + plain text)

- **toward** $= (d_0 - |p_{\text{end}} - p_{\text{partner,0}}|)/\lVert\Delta\rVert \in[-1,1]$, where
  $d_0=|p_{\text{start}}-p_{\text{partner,0}}|$ and $\Delta=p_{\text{end}}-p_{\text{start}}$ is the bout
  displacement. Plain: how much of the bout went toward the partner's start position ($+1$ straight at,
  $-1$ straight away). Heading-free. Included only for bouts with $\lVert\Delta\rVert\ge$ min_disp and a
  partner at $d_0\ge 1$ m (both above the ~7 in floor).
- **Per-night geometry-adjusted effect** $e_{\text{dir}}(n)=\overline{\text{toward}}(n)-\mu_{\text{dir}}(n)$,
  where $\mu_{\text{dir}}(n)$ is the night's direction-randomized (rotate each $\Delta$ about its start)
  mean — the GEOMETRY expectation (generally $<0$; a step from a point usually increases distance).
- **Per-night social increment** $e_{\text{day}}(n)=\overline{\text{toward}}_{\text{valid}}(n)-\mu_{\text{day}}(n)$,
  where $\mu_{\text{day}}(n)$ replaces each partner with the SAME partner at the same clock-hour on a
  DIFFERENT night (layout, not real-time). ``valid`` = pairs whose (partner,hour) cell has another
  night, so obs and null are the SAME subpopulation.
- **Night-level sign test:** two-sided binomial over the $N\approx8$ per-night effects (null $p=0.5$).
  This is the significance — **NOT** the per-pair z, which is invalid here (thousands of pseudoreplicated
  pairs; each bout emits several partner rows and bouts within a night share layout).
- **Gate:** RESOLVABLE = support AND $e_{\text{dir}}$ sign-test $p\le0.1$ (pooled or any $d_0$ bin);
  SOCIAL = RESOLVABLE AND $e_{\text{day}}$ sign-test $p\le0.1$. Model fit only if SOCIAL.

## Result (night-block; the RAW toward sign is distance-dependent by geometry, so read the ADJUSTED effects)"""
    body = f"""

**Support:** {gate['n_pairs']} (bout, partner) pairs over {pn.get('n_nights')} night-blocks.

| d0 bin | n pairs | n nights | e_dir (vs geometry) | dir +/N | dir sign-p | e_day (real-time social) | day +/N | day sign-p | net |
|---|---|---|---|---|---|---|---|---|---|
{nb_md}

- **RESOLVABLE (a toward/away bias above geometry, night-consistent): {gate['gate_resolvable']}**.
- **SOCIAL (real-time, above shared layout, night-consistent): {gate['gate_social']}**;
  **distance-dependent: {gate['distance_dependent']}** (per-bin social signs: {gate['social_bin_signs']}).

**Read:** `e_dir` > 0 means the focal moves toward partners MORE than chance geometry (positive across
bins ⇒ a real toward bias at all distances; the raw negative toward at close range is geometry). `e_day`
is the REAL-TIME social increment beyond shared layout — its **sign is distance-dependent**: the animals
tend to **close distance to FAR conspecifics and open distance to NEAR ones**, i.e. maintain a preferred
inter-individual spacing, only where the night-level sign test is significant ($p\\le0.1$).

### Verdict: {gate['verdict']}

{('The approach/avoid MODEL table is gated on SOCIAL and was ' + ('written (approach_model_table.csv).' if gate['gate_social'] else 'NOT written.'))}

## Scope & language

Coarse net proximity change, ≥ 1 m, heading-free (no fine steering — DBV). **Association, not
motivation:** "in-bout approach/avoid tendency relative to the group", never "the rat chooses to
approach" or "attraction/aversion". Group-level; pair-resolved (dyadic) only if module 13 passes.
Frame UNVERIFIED (topology + coarse distance only).
"""
    (out / "approach_avoid_report.md").write_text(header + defn + body, encoding="utf-8")


if __name__ == "__main__":
    main()
