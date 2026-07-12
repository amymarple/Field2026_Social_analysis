r"""
analyze_approach_circadian.py — Part 2: confine the approach/avoid spacing to the ACTIVE-MOVING period
and cross-check it against the nap / circadian rest rhythm.

The approach/avoid metric (module 7) is ALREADY measured only inside locomotor BOUTS (active movement
above the ~7 in jitter floor, within the 21:00–05:00 local night) — a rat that is resting emits no bout
and therefore no (bout, partner) pair. This driver makes that explicit and asks the Part-2 question:

  Is the distance-dependent social spacing (avoid-near / approach-far) a property of the ACTIVE-movement
  period, or is it confounded by the circadian nap rhythm (e.g. "avoid-near" only reflects that when the
  group naps, no one approaches)?

Method (no leakage): the circadian phase of each bout is set from the POPULATION rest rhythm
(``rest_circadian.circadian_rest_profile`` — the animal-independent stationary-fraction by LOCAL hour),
splitting the 8 night-window hours into an ACTIVE phase (below-median population rest) and a NAP phase
(above-median). The night-block measurement gate (per-night effect + binomial sign test across the 11
nights — NOT the pseudoreplicated per-pair z) is then run WITHIN each phase. A spacing that holds in the
ACTIVE phase is a genuine moving-time behaviour; one that appears only in the NAP phase is a rest artifact.

    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\analyze_approach_circadian.py
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

import approach_avoid as aa                          # noqa: E402
import rest_circadian as rc                          # noqa: E402
from build_decision_tables import (load_clean_stream, DEFAULT_INCR, DEFAULT_WEATHER,  # noqa: E402
                                   NIGHTS)

TZ = rc.TZ_OFFSET_HOURS


def _phase_of_hour(rest_by_local_hour: dict) -> dict:
    """{local_hour -> 'active'/'nap'} by a median split of the POPULATION rest fraction across the
    night-window hours (animal-independent -> no leakage into the focal's approach decision)."""
    hrs = sorted(rest_by_local_hour)
    vals = np.array([rest_by_local_hour[h] for h in hrs], float)
    med = float(np.nanmedian(vals))
    return {h: ("nap" if rest_by_local_hour[h] >= med else "active") for h in hrs}, med


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--approach-dir", type=Path,
                    default=ROOT / "outputs/approach_avoid_2026-06-28_to_2026-07-08")
    ap.add_argument("--locomotor-dir", type=Path,
                    default=ROOT / "outputs/locomotor_initiation_2026-06-28_to_2026-07-08")
    ap.add_argument("--incremental-dir", type=Path, default=DEFAULT_INCR)
    ap.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER)
    ap.add_argument("--env-map", type=Path,
                    default=ROOT / "configs/environment_map/2026-06-28_to_2026-07-08.yaml")
    ap.add_argument("--rois", type=Path, default=ROOT / "configs/wiser_rois.json")
    ap.add_argument("--nights", nargs="*", default=NIGHTS)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs/approach_avoid_2026-06-28_to_2026-07-08")
    ap.add_argument("--n-perm-dir", type=int, default=150)
    ap.add_argument("--n-perm-day", type=int, default=50)
    args = ap.parse_args()

    ctx = pd.read_csv(args.approach_dir / "approach_context.csv")
    stream = pd.read_csv(args.locomotor_dir / "locomotor_state_stream.csv")
    R = {"generated_utc": datetime.datetime.utcnow().isoformat(), "n_pairs": int(len(ctx))}

    # ---- circadian rest rhythm (population, animal-independent) ----
    prof = rc.circadian_rest_profile(stream)
    rest_by_lh = dict(zip(prof["local_hour"].astype(int), prof["rest_frac"].astype(float)))
    phase_of, med = _phase_of_hour(rest_by_lh)
    ctx["local_hour"] = ((ctx["clock_hour"].astype(int) + TZ) % 24).astype(int)
    ctx["circ_phase"] = ctx["local_hour"].map(phase_of)
    R["circadian"] = {"rest_frac_by_local_hour": {int(h): round(v, 3) for h, v in rest_by_lh.items()},
                      "median_rest_frac": round(med, 3),
                      "phase_of_local_hour": {int(h): p for h, p in phase_of.items()},
                      "pairs_active": int((ctx["circ_phase"] == "active").sum()),
                      "pairs_nap": int((ctx["circ_phase"] == "nap").sum())}
    print("[circadian] population rest-frac by local hour:",
          {int(h): round(v, 2) for h, v in sorted(rest_by_lh.items())})
    print(f"[circadian] median split rest_frac={med:.2f} -> phases:",
          {int(h): p for h, p in sorted(phase_of.items())})
    print(f"[confine] approach/avoid pairs are all inside active locomotor bouts; "
          f"active-phase pairs={R['circadian']['pairs_active']}, nap-phase pairs={R['circadian']['pairs_nap']}")

    # ---- reload cleaned fixes for the day-shuffle null (partner-cell layout) ----
    print("[load] cleaned fixes for the day-shuffle null (partner cells)")
    S = load_clean_stream(args.incremental_dir, args.weather_dir, args.env_map, args.rois,
                          list(args.nights), plog=lambda m: None)
    fixes = S["win"][["shortid", "night", "datetime", "x", "y"]].copy()

    # ---- night-block gate WITHIN each circadian phase ----
    R["by_phase"] = {}
    for ph in ("active", "nap"):
        sub = ctx[ctx["circ_phase"] == ph]
        if len(sub) < 60:
            R["by_phase"][ph] = {"n_pairs": int(len(sub)), "note": "too few pairs for a night-block gate"}
            print(f"[gate:{ph}] n={len(sub)} too few"); continue
        nb = aa.night_block_gate(sub, fixes, n_perm_dir=args.n_perm_dir, n_perm_day=args.n_perm_day)
        nb.to_csv(args.out / f"night_block_gate_{ph}.csv", index=False)
        soc = nb[(nb["bin"] != "ALL") & nb["real_time_social_night"]]
        signs = {r["bin"]: ("approach" if (r["e_day_mean"] or 0) > 0 else "avoid")
                 for _, r in soc.iterrows() if r["e_day_mean"] == r["e_day_mean"]}
        R["by_phase"][ph] = {
            "n_pairs": int(len(sub)),
            "per_bin": nb.to_dict("records"),
            "social_bin_signs": signs,
            "distance_dependent": len(set(signs.values())) > 1,
        }
        print(f"[gate:{ph}] n={len(sub)} social_bin_signs={signs} distance_dependent={len(set(signs.values()))>1}")
        for r in nb.to_dict("records"):
            print(f"    {r['bin']:>7}: e_dir={r['e_dir_mean']} (p={r['e_dir_signtest_p']}, {r['e_dir_n_pos']}/{r['n_nights']}) "
                  f"| e_day={r['e_day_mean']} (p={r['e_day_signtest_p']}, {r['e_day_n_pos']}/{r['n_nights']})")

    # ---- verdict ----
    act = R["by_phase"].get("active", {})
    active_has_spacing = bool(act.get("distance_dependent"))
    R["verdict"] = (
        "distance-dependent social spacing is PRESENT in the ACTIVE-movement phase -> a genuine "
        "moving-time behaviour, not a circadian-nap artifact" if active_has_spacing else
        "the spacing does not resolve within the active phase alone (see per-phase table)")
    print(f"[verdict] {R['verdict']}")

    (args.out / "approach_circadian_results.json").write_text(json.dumps(R, indent=2, default=str), encoding="utf-8")
    _write_report(args.out, R)
    print(f"done -> {args.out}")


def _write_report(out, R):
    C = R["circadian"]; ph = R["by_phase"]
    rest_tbl = "\n".join(f"| {h:02d}:00 | {C['rest_frac_by_local_hour'][h]:.3f} | "
                         f"{C['phase_of_local_hour'][h]} |" for h in sorted(C['rest_frac_by_local_hour']))

    def bin_tbl(recs):
        rows = [f"| {r['bin']} | {r['e_dir_mean']} | {r['e_dir_n_pos']}/{r['n_nights']} | {r['e_dir_signtest_p']} "
                f"| {r['e_day_mean']} | {r['e_day_n_pos']}/{r['n_nights']} | {r['e_day_signtest_p']} |"
                for r in recs]
        return "\n".join(rows)

    header = ("# Approach/avoid — active-period confinement + nap/circadian cross-check (Part 2, 11 nights)\n\n"
              "**Status:** ⚠️ candidate. Confirms the module-7 distance-dependent social spacing is a "
              "property of the ACTIVE-movement period and cross-checks it against the circadian nap rhythm, "
              f"on the extended 06-28→07-08 window. Generated {R['generated_utc']}. Frame UNVERIFIED (topology "
              "+ coarse distance only); rest is a low-speed proxy, not sleep; night-block bits/sign-tests.\n")
    defn = r"""
## Definitions (formula + plain text)

- **Confinement to active movement** — every approach/avoid unit is a (locomotor bout, partner) pair.
  A bout is a maximal run of ``active`` bins (speed above the ~7 in jitter floor) inside the 21:00–05:00
  local night. A RESTING animal emits no bout, so it contributes no pair: the metric is already confined
  to the active-moving period by construction.
- **Population rest fraction** $\rho(h)$ — at LOCAL clock-hour $h$, the fraction of informative
  (non-``unknown``) locomotor-state bins over ALL animals that are stationary (rest ∪ pause):
  $\rho(h) = \frac{\#\{\text{bins at }h:\ \text{state}\in\{\text{rest},\text{pause}\}\}}{\#\{\text{informative bins at }h\}}$.
  Animal-independent (the group rhythm), so using it to phase a focal's bout leaks no outcome.
- **Circadian phase** — $\text{phase}(h)=\text{nap}$ if $\rho(h)\ge\operatorname{median}_h\rho(h)$, else
  $\text{active}$. A median split of the 8 night-window hours into the group's more-resting vs
  more-active halves.
- **Geometry-adjusted approach** $e_{\dir}$ and **real-time social increment** $e_{\day}$ — as in
  module 7 (`change_log/2026-07-12-approach-avoid.md`): $e_{\dir}=\overline{\text{toward}}-$ (rotation
  null), $e_{\day}=\overline{\text{toward}\mid\text{valid}}-$ (same-partner/same-hour/different-night
  null). Positive $e_{\day}$ = approach, negative = avoid. Significance = a binomial SIGN TEST on the
  per-night effects across the 11 nights (the outer blocks), NOT a per-pair z.

## Circadian rest rhythm (population, animal-independent)

| local hour | pop. rest frac ρ(h) | phase |
|---|---|---|
""" + rest_tbl + f"""

Median ρ = {C['median_rest_frac']:.3f}. Active-phase pairs = {C['pairs_active']}, nap-phase pairs = {C['pairs_nap']}.

## Night-block gate WITHIN the ACTIVE phase

| dist bin | e_dir | dir n_pos | dir p | e_day | day n_pos | day p |
|---|---|---|---|---|---|---|
""" + (bin_tbl(ph['active']['per_bin']) if 'per_bin' in ph.get('active', {}) else "(too few pairs)") + f"""

social bin signs: {ph.get('active', {}).get('social_bin_signs')} — distance-dependent: {ph.get('active', {}).get('distance_dependent')}

## Night-block gate WITHIN the NAP phase

| dist bin | e_dir | dir n_pos | dir p | e_day | day n_pos | day p |
|---|---|---|---|---|---|---|
""" + (bin_tbl(ph['nap']['per_bin']) if 'per_bin' in ph.get('nap', {}) else "(too few pairs)") + f"""

social bin signs: {ph.get('nap', {}).get('social_bin_signs')} — distance-dependent: {ph.get('nap', {}).get('distance_dependent')}

## Verdict

{R['verdict']}

## Scope

Group-level (herd, not dyads), association not motivation. Circadian phase is a population-rhythm split
(a low-speed rest proxy, not sleep/ephys). The night-block sign test has only 11 outer blocks, fewer
within each phase — a phase with few informative nights is under-powered, not evidence of absence.
Frame UNVERIFIED: distance bins are coarse (≥1 m, jitter floor ~7 in), no directional/route claims.
"""
    (out / "approach_circadian_report.md").write_text(header + defn, encoding="utf-8")


if __name__ == "__main__":
    main()
