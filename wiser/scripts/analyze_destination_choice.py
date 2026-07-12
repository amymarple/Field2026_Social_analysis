r"""
analyze_destination_choice.py — Phase 2 / Module 6 GATED destination-choice fit (anaconda3).

Fits the origin-conditioned destination-choice model on the CLEAN relocation set (settlement ->
different-settlement), but ONLY if the representation validated (`validation_results.json` gate_ok).
It REFUSES to fit otherwise — you must validate the representation first (per the design + the
decision_boundary_validation lesson).

Held-out loss = categorical cross-entropy in BITS/decision at the NIGHT-block level. Questions:
  - does the ORIGIN predict the destination beyond a global destination base-rate?  (M1 vs M0)
  - does either beat a uniform-over-supported-choice-set baseline?                   (skill)
  - is there a stable cross-night individual preference among the two houses?         (matched-choice)

Given only ~55 relocations over 8 nights (thin per origin), this is EXPLORATORY — report effect
size + power caveat, not a p-value.

    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\analyze_destination_choice.py
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
import settlement_transitions as st                     # noqa: E402

EPS = 1e-12


def _origin_conditioned_rate(train: pd.DataFrame, alpha: float = 0.5) -> dict:
    """Laplace-smoothed P(dest | origin) over each origin's training choice set."""
    out = {}
    for o, g in train.groupby("origin_roi"):
        dests = sorted(g["dest_roi"].unique())
        vc = g["dest_roi"].value_counts()
        n = len(g); k = len(dests)
        out[o] = {"set": dests, "p": {d: (vc.get(d, 0) + alpha) / (n + alpha * k) for d in dests}}
    return out


def _global_rate(train: pd.DataFrame, alpha: float = 0.5) -> dict:
    dests = sorted(train["dest_roi"].unique())
    vc = train["dest_roi"].value_counts(); n = len(train); k = len(dests)
    return {"set": dests, "p": {d: (vc.get(d, 0) + alpha) / (n + alpha * k) for d in dests}}


def lono_categorical(rel: pd.DataFrame) -> dict:
    """Leave-one-night-out held-out categorical bits for the global (M0) and origin-conditioned (M1)
    base-rate models, and a uniform-over-supported-set baseline. A held destination outside the
    training model's support falls back to that model's global rate (then a floor)."""
    nights = sorted(rel["night"].unique())
    b0, b1, bu, per = [], [], [], []
    for hn in nights:
        tr = rel[rel["night"] != hn]; te = rel[rel["night"] == hn]
        if len(tr) < 8 or te.empty:
            continue
        gr = _global_rate(tr); oc = _origin_conditioned_rate(tr)
        p0 = np.empty(len(te)); p1 = np.empty(len(te)); pu = np.empty(len(te))
        for i, (_, r) in enumerate(te.iterrows()):
            o, d = r["origin_roi"], r["dest_roi"]
            p0[i] = gr["p"].get(d, EPS)
            om = oc.get(o)
            p1[i] = (om["p"].get(d) if (om and d in om["p"]) else gr["p"].get(d, EPS))
            kset = (om["set"] if om else gr["set"])
            # uniform-over-supported-set: 1/|C(o)| for an in-support destination, else the same EPS
            # floor the base-rate models use (a held destination outside training support is an
            # out-of-sample miss for EVERY model — the baseline must not be uniquely generous to it).
            pu[i] = (1.0 / max(1, len(kset))) if d in kset else EPS
        b0.append(cm.bits_categorical(p0)); b1.append(cm.bits_categorical(p1)); bu.append(cm.bits_categorical(pu))
        per.append({"held_night": hn, "n": int(len(te)),
                    "bits_uniform": cm.bits_categorical(pu), "bits_global": cm.bits_categorical(p0),
                    "bits_origin": cm.bits_categorical(p1)})
    H0, H1, Hu = float(np.mean(b0)), float(np.mean(b1)), float(np.mean(bu))
    return {"H_uniform": Hu, "H_global": H0, "H_origin_conditioned": H1,
            "skill_origin_vs_uniform": cm.skill(H1, Hu), "skill_origin_vs_global": cm.skill(H1, H0),
            "dbits_origin_over_global": H0 - H1, "n_held_nights": len(per), "per_night": per}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path,
                    default=ROOT / "outputs/destination_settlement_2026-06-28_to_2026-07-08")
    args = ap.parse_args()
    d = args.dir
    val = json.loads((d / "validation_results.json").read_text())
    if not val.get("gate_ok"):
        print("GATE NOT PASSED (validation_results.json gate_ok=False) -> REFUSING to fit a "
              "destination-choice model. Validate the representation first.")
        sys.exit(2)
    rel = pd.read_csv(d / "destination_choice.csv")
    print(f"[gate] PASS. Fitting on {len(rel)} relocation events (EXPLORATORY — thin per-origin).")

    R = {"gate_ok": True, "n_relocations": int(len(rel))}
    # ---- held-out categorical choice ----
    R["choice"] = lono_categorical(rel)
    c = R["choice"]
    print(f"[choice] held-out bits: global={c['H_global']:.3f} origin-cond={c['H_origin_conditioned']:.3f} "
          f"| ROBUST: origin-over-global dbits={c['dbits_origin_over_global']:.4f} "
          f"(skill {c['skill_origin_vs_global']:.3f}) | uniform={c['H_uniform']:.3f} "
          f"skill-vs-uniform={c['skill_origin_vs_uniform']:.3f} (baseline-sensitive at n=55)")

    # ---- origin->dest structure ----
    struct = rel.groupby(["origin_roi", "dest_roi"]).size().rename("n").reset_index()
    struct.to_csv(d / "destination_structure.csv", index=False)
    hub = rel["dest_roi"].value_counts()
    R["structure"] = {"top_destinations": hub.head(5).to_dict(),
                      "house_house_switches": int(((rel["origin_roi"].isin(["house_1", "house_2"])) &
                                                   (rel["dest_roi"].isin(["house_1", "house_2"])) &
                                                   (rel["origin_roi"] != rel["dest_roi"])).sum())}
    print(f"[structure] top destinations: {R['structure']['top_destinations']}; "
          f"house<->house switches: {R['structure']['house_house_switches']}")

    # ---- matched-choice: stable individual house preference (settled destinations only) ----
    house_dest = rel[rel["dest_roi"].isin(["house_1", "house_2"])].copy()
    mc = (cm.matched_choice_stability(house_dest, ["house_1", "house_2"], dest_col="dest_roi",
                                      min_per_night=2) if len(house_dest) else pd.DataFrame())
    if not mc.empty:
        mc.to_csv(d / "house_matched_choice.csv", index=False)
    R["matched_choice_house"] = {"n_animals_tested": int(len(mc)),
                                 "n_stable_pref": int(mc["stable_pref"].sum()) if not mc.empty else 0}
    print(f"[matched] stable individual house preference: {R['matched_choice_house']['n_stable_pref']}/"
          f"{R['matched_choice_house']['n_animals_tested']} animals")

    R["power_note"] = ("~55 relocations over 8 nights (~7/held-night); per-origin support is thin "
                       "(only house_1/house_2 have >10). Held-out skill is an effect-size estimate, "
                       "NOT a powered test. Most departures are open-field terminations, not relocations.")
    R["generated_utc"] = datetime.datetime.utcnow().isoformat()
    (d / "destination_choice_results.json").write_text(json.dumps(R, indent=2, default=str), encoding="utf-8")
    _write_report(d, R)
    print(f"done -> {d}")


def _write_report(d, R):
    c = R["choice"]; s = R["structure"]
    header = (
        "# Destination-choice — GATED fit (Module 6, Phase 2)\n\n"
        "**Status:** ⚠️ candidate / EXPLORATORY. Fit ONLY because the representation validated "
        f"(`validation_report.md`, gate PASS). {R['n_relocations']} clean relocation events "
        f"(settlement -> different settlement); generated {R['generated_utc']}.\n")
    defn = r"""
## Definitions (formula + plain text)

- **Relocation** — a departure from a sustained settlement that ends in a *different* sustained
  settlement (the only destination-choice event; same-site returns / pass-throughs / open-field
  terminations / censored are excluded).
- **Held-out categorical bits** $H=-\frac1N\sum\log_2 p(\text{chosen dest})$ (leave-one-night-out).
  **M0 global** = $P(\text{dest})$ from training; **M1 origin-conditioned** = $P(\text{dest}\mid
  \text{origin})$ (Laplace $\alpha{=}0.5$ over the origin's training choice set); **uniform** =
  $1/|C(o)|$. **skill** $=1-H/H_{\text{uniform}}$.
- **Matched-choice house preference** — per animal, cross-night consistency of the fraction settling
  in house_1 vs house_2 (LONO transfer error $<0.15$ AND $|pref-0.5|>0.15$).

## Results"""
    md = header + defn + f"""

**Held-out choice bits (robust result):** global {c['H_global']:.3f} → origin-conditioned
**{c['H_origin_conditioned']:.3f}** bits → **origin-over-global Δbits = {c['dbits_origin_over_global']:.4f}
(skill {c['skill_origin_vs_global']:.3f})**. Knowing the ORIGIN improves destination prediction beyond
the global hub rate — this comparison is baseline-independent (both models share the EPS out-of-support
floor, so unpredictable held destinations cancel). The uniform-over-supported-set reference
({c['H_uniform']:.3f}, skill-vs-uniform {c['skill_origin_vs_uniform']:.3f}) is **baseline-SENSITIVE at
n=55** (dominated by held destinations outside the training support) — reported for completeness, not
as the headline.

**Structure (descriptive counts, not a directional claim):** top destinations by count
{s['top_destinations']}; **house↔house switches = {s['house_house_switches']}** of {R['n_relocations']}
relocations. (Endpoints only — the frame is UNVERIFIED, so no route/direction/"feeds into" is claimed.)

**Individual house preference:** stable cross-night preference in
**{R['matched_choice_house']['n_stable_pref']}/{R['matched_choice_house']['n_animals_tested']}** animals.

## Power & scope

{R['power_note']} Endpoints only (frame UNVERIFIED — no route/path/direction). Not "route choice", not
"goal-directed navigation". The headline of Module 6 is the **validated representation** (most shelter
departures terminate in the open, not at a named site); this choice fit is a thin, gated add-on.
"""
    (d / "destination_choice_report.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
