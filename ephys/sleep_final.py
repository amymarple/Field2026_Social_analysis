r"""Assemble the final cohort-2026c sleep scores = the base variant (the user-reviewed per-session scores) with the
per-session substitutions of ephys/configs/sleep_final_<c>.yaml (user decision 2026-10-07).

Writes:
  <root>/states_1s_final/<SFxx>/<session>.states.npz   the 1-s states the analyses read (sleep_quant.py, sleep_cycles_v2.py)
  <root>/final_substitutions.json                      what was substituted, from where, why
  reports/ephys_spikes_sleep_scores_final_<c>.csv       the base scores CSV with the substituted rows replaced (variant = final,
                                                        column source_variant); feed it to sleep_review.py --merge ... --variant final
Inputs (local light copies): <root>/states_1s (base), <root>/states_1s_<suffix> for each from_variant (pass2med_remclean ->
states_1s_pass2med), <root>/<from_variant>/<SFxx>/<session>/score_sleep.json.

Usage: python ephys/sleep_final.py --cohort 2026c [--root D:/3rd_rat_spikes/analysis/sleep_server]
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd
import yaml

from _common import PROJECT_ROOT, analysis_root, report_dir, resolve_cohort, utc_now_iso

STATES_DIR = {"imu_remclean": "states_1s", "pass2med_remclean": "states_1s_pass2med", "pass2_remclean": "states_1s_pass2"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--root", default=None, help="local light copy of the sleep outputs (default <analysis_root>/sleep_server)")
    a = ap.parse_args()
    c = resolve_cohort(a.cohort)
    root = Path(a.root) if a.root else analysis_root(c) / "sleep_server"
    cfg = yaml.safe_load(open(PROJECT_ROOT / "ephys" / "configs" / f"sleep_final_{c}.yaml", encoding="utf-8"))
    base = cfg["base_variant"]
    out = root / "states_1s_final"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(root / STATES_DIR[base], out)
    rd = report_dir(c)
    scores = pd.read_csv(rd / f"ephys_spikes_sleep_scores_{c}.csv")
    scores = scores[scores.variant == base].copy()
    scores["source_variant"] = base
    done = []
    for s in cfg.get("substitutions") or []:
        an, se, fv = s["animal"], s["session"], s["from_variant"]
        src = root / STATES_DIR[fv] / an / f"{se}.states.npz"
        shutil.copy2(src, out / an / f"{se}.states.npz")
        info = json.loads((root / fv / an / se / "score_sleep.json").read_text(encoding="utf-8"))
        scores = scores[~((scores.animal == an) & (scores.session == se))]
        row = {k: v for k, v in info.items() if k in scores.columns}
        row["source_variant"] = fv
        scores = pd.concat([scores, pd.DataFrame([row])], ignore_index=True)
        done.append({"animal": an, "session": se, "from_variant": fv, "states": str(src), "reason": s.get("reason", "")})
    scores["variant"] = "final"
    scores.sort_values(["animal", "session"]).to_csv(rd / f"ephys_spikes_sleep_scores_final_{c}.csv", index=False)
    (root / "final_substitutions.json").write_text(json.dumps({"base_variant": base, "substitutions": done, "written_utc": utc_now_iso()},
                                                              indent=2), encoding="utf-8")
    n = sum(1 for _ in out.glob("*/*.states.npz"))
    print(f"final = {base} + {len(done)} substitution(s): {n} sessions -> {out}; scores -> {rd / f'ephys_spikes_sleep_scores_final_{c}.csv'}")


if __name__ == "__main__":
    main()
