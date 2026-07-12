r"""
aggregate_ladder_grid.py — run the identifiability ladder on every hysteretic-grid config and
collate the verdicts (run under the anaconda3 interpreter). Reports whether the individual (M4)
and social (M5) NO-GO / GO is STABLE across buffer × exit × epoch — the point being robustness,
not a cherry-picked threshold.

    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\aggregate_ladder_grid.py
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def _num(x):
    try:
        return round(float(x), 4)
    except Exception:
        return None


def extract(R: dict, cfg: str) -> dict:
    n = R.get("nested", {}); m4 = R.get("M4_individual", {}); m5 = R.get("M5_social", {})
    gw = m4.get("gain_with_weather", {}); cp = m4.get("conditional_permutation", {})
    ts = m5.get("time_shift_null", {})
    return {
        "config": cfg, "n_leave": R.get("A0", {}).get("n_leave_epochs"),
        "n_dep": R.get("A0", {}).get("n_departures"),
        "H_marginal": _num(n.get("H_marginal_bits")), "H_M1": _num(n.get("H_M1_layout_bits")),
        "skill_M1": _num(n.get("skill_M1_vs_marginal")),
        "dbits_weather": _num(n.get("dbits_weather_M1_to_M2")),
        "dbits_shareduse": _num(n.get("dbits_shareduse_M2_to_M3")),
        "memory_dbits": _num(R.get("memory", {}).get("dbits_history_over_M2")),
        "M4_dbits_med": _num(gw.get("median")), "M4_frac+nights": _num(gw.get("frac_positive_nights")),
        "M4_condperm_z": _num(cp.get("z")), "M4_GO": m4.get("GO"),
        "M5_dbits_mean": _num(m5.get("mean_dbits")), "M5_timeshift_z": _num(ts.get("z")),
        "M5_GO": m5.get("GO"),
        "matched_stable": R.get("matched_choice", {}).get("n_stable"),
        "matched_n": R.get("matched_choice", {}).get("n_tested"),
        "reward": R.get("reward_feasibility", {}).get("verdict"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", type=Path, default=ROOT / "outputs/policy_identifiability_2026-06-28_to_2026-07-06/grid")
    ap.add_argument("--fast", action="store_true", default=True)
    ap.add_argument("--full", dest="fast", action="store_false")
    args = ap.parse_args()
    configs = sorted([p for p in args.grid.iterdir() if p.is_dir() and (p / "leave_decisions.csv").exists()])
    env = dict(os.environ); env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    rows = []
    for cfg in configs:
        print(f"[ladder] {cfg.name}", flush=True)
        cmd = [sys.executable, str(ROOT / "scripts/analyze_policy_identifiability.py"), "--dir", str(cfg)]
        if args.fast:
            cmd.append("--fast")
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        rj = cfg / "policy_identifiability_results.json"
        if not rj.exists():
            print(f"  FAILED: {r.stderr[-400:]}")
            continue
        rows.append(extract(json.loads(rj.read_text()), cfg.name))
    if not rows:
        print("no configs produced results"); return
    df = pd.DataFrame(rows)
    df.to_csv(args.grid / "grid_ladder_summary.csv", index=False)
    pd.set_option("display.width", 240); pd.set_option("display.max_columns", 30)
    show = ["config", "n_leave", "H_marginal", "H_M1", "skill_M1", "dbits_weather", "dbits_shareduse",
            "memory_dbits", "M4_dbits_med", "M4_frac+nights", "M4_condperm_z", "M4_GO",
            "M5_dbits_mean", "M5_timeshift_z", "M5_GO", "matched_stable", "reward"]
    print("\n=== LADDER ROBUSTNESS ACROSS THE HYSTERETIC GRID ===")
    print(df[show].to_string(index=False))
    print("\nM4 GO count:", int(df["M4_GO"].sum()), "/", len(df),
          "| M5 GO count:", int(df["M5_GO"].sum()), "/", len(df))
    print(f"wrote {args.grid / 'grid_ladder_summary.csv'}")


if __name__ == "__main__":
    main()
