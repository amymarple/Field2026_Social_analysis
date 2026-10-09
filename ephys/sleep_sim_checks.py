r"""Steps D2 and E (ii) / (vi) of the sleep-behaviour explore (plan implementation_plan/2026-10-08-sleep-behaviour-explore.md
§5, written before results), measured on records simulated by `ephys/sleep_sim.py` (the counter rules, conditional on
the observed long wakes and gaps; no REM-deficit variable).

Usage:  python ephys/sleep_sim_checks.py [--scorings pass2med final] [--reps 100] [--carry-reps 3] [--workers 8]

Definitions:
  D2      the morning-round REM payback slope (REM payback in the 1 h / 3 h after a battery round on the REM debt of the
          3 h before; phase x day baselines; day-demeaned; NREM debt partialled) measured with
          `sleep_explore_d.payback_from_records` on every simulated replicate. The model has no REM deficit, so a
          simulated slope near the observed one would mean the payback is produced by the counter seen through the clock.
          Pass for "a slow REM deficit exists" (plan Step D): the observed D1 slope > 0.2 (sleep_explore_d, Step D1) AND
          the simulated slope < 0.1 (mean over replicates; 95 % range reported). The D2 number is the row kind = morning,
          outcome = pay_rem, predictors = debt_rem, day_demeaned = True, B_h = 1 and 3 (phase x day baselines refitted on
          each simulated record set). The simulator is sleep_sim v2 (short wakes sampled with their next state), no H19.
  (vi)    the night -> next-day deviation slope with day fixed effects (`sleep_explore_d.budget_from_records`) on the
          simulated records; the model has no budget, so ~ 0 is expected; reported next to the observed value.
  (ii)    the carry-over curve (Phase 2 B1): post-wake NREM steps, held-out log-loss of C1 (pre-wake history: N_pre spline,
          wake before, REM_pre, anchor) vs R0 (current state only), by wake bin (< 40 s, 40-120 s, 2-7 min, 7-30 min,
          >= 30 min), forward chaining (Phase 2 `run_cv`), on the observed records and on `--carry-reps` simulated
          replicates. Pass: the simulated Delta has the observed sign in every bin where the observed CI excludes 0, and
          the same order of magnitude by bin (rank correlation reported).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from sleep_schedule import ROOT  # noqa: E402


def gaps_table() -> pd.DataFrame:
    p0 = json.load(open(ROOT / "results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_phase0_2026c.json"))["run_dir"]
    return pd.read_csv(Path(p0) / "gaps.csv", parse_dates=["gap_start", "gap_end"])


def carry_curve(recs: list[dict]) -> pd.DataFrame:
    from sleep_schedule_phase2 import D_BINS, D_LABELS, build_steps, compare, forward_folds, run_cv
    steps = build_steps(recs)
    steps["d_bin"] = pd.cut(steps.d_prev, D_BINS, right=False, labels=D_LABELS)
    pw = steps[steps.d_prev > 0].copy()
    specs = {"R0": ["cur"], "C1": ["cur", "nspl", "wpre", "rem"]}
    F, FB, FA, _ = run_cv(pw, specs, forward_folds(pw), bin_col="d_bin")
    rows = [compare(F, FA, "R0", "C1", "all post-wake")]
    for b in D_LABELS:
        rows.append(compare(FB[FB.bin == b], None, "R0", "C1", f"wake {b}"))
    return pd.DataFrame(rows)


def _rep(rep: int, recs: list[dict], M: dict, gaps: pd.DataFrame, label: str, what: tuple) -> dict:
    from sleep_explore_d import budget_from_records, payback_from_records
    from sleep_sim import simulate_records
    sim = simulate_records(recs, M, rep)
    out = {"rep": rep}
    if "payback" in what:
        out["payback"] = payback_from_records(sim, gaps, f"{label}_sim{rep}")
    if "budget" in what:
        out["budget"] = budget_from_records(sim, f"{label}_sim{rep}")
    return out


def main() -> None:
    from joblib import Parallel, delayed
    from _common import git_commit, write_json
    from output_paths import report_dir, run_dir
    from sleep_explore_d import budget_from_records, payback_from_records
    from sleep_model import PASS2MED, STATES, records_for
    from sleep_quant import md_table
    from sleep_sim import build_model, simulate_records
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scorings", nargs="+", default=["pass2med", "final"])
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--carry-reps", type=int, default=3)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--from-run", default=None, help="re-summarise a finished run folder (payback_all / budget_all / carry_all.csv)")
    a = ap.parse_args()
    out = Path(a.from_run) if a.from_run else run_dir("sleep_explore_D2E", "2026c")
    rd = report_dir("2026c", "ephys_spikes")
    gc = git_commit()
    t0 = time.time()
    gaps = gaps_table()
    PB, BU, CC = [], [], []
    for lab in ([] if a.from_run else a.scorings):
        recs = records_for(PASS2MED if lab == "pass2med" else STATES)
        M = build_model(recs)
        ob_p = payback_from_records(recs, gaps, f"{lab}_observed").assign(scores=lab, source="observed", rep=-1)
        ob_b = budget_from_records(recs, f"{lab}_observed").assign(scores=lab, source="observed", rep=-1)
        PB.append(ob_p)
        BU.append(ob_b)
        simulate_records(recs[:1], M, 0)
        res = Parallel(n_jobs=a.workers, backend="loky")(delayed(_rep)(r, recs, M, gaps, lab, ("payback", "budget")) for r in range(a.reps))
        for r in res:
            PB.append(r["payback"].assign(scores=lab, source="simulated", rep=r["rep"]))
            BU.append(r["budget"].assign(scores=lab, source="simulated", rep=r["rep"]))
        print(f"[{lab}] payback + budget on {a.reps} replicates: {time.time() - t0:.0f} s", flush=True)
        oc = carry_curve(recs).assign(scores=lab, source="observed", rep=-1)
        CC.append(oc)
        for r in range(a.carry_reps):
            CC.append(carry_curve(simulate_records(recs, M, 10_000 + r)).assign(scores=lab, source="simulated", rep=r))
        print(f"[{lab}] carry-over curves: {time.time() - t0:.0f} s", flush=True)
    if a.from_run:
        PB, BU, CC = (pd.read_csv(out / f) for f in ("payback_all.csv", "budget_all.csv", "carry_all.csv"))
    else:
        PB, BU, CC = (pd.concat(x, ignore_index=True) for x in (PB, BU, CC))
        PB.to_csv(out / "payback_all.csv", index=False)
        BU.to_csv(out / "budget_all.csv", index=False)
        CC.to_csv(out / "carry_all.csv", index=False)
    # summaries: observed value vs the simulated distribution, per numeric column of every row key
    def summarise(T: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        num = [c for c in T.columns if c not in keys + ["scores", "source", "rep"] and pd.api.types.is_numeric_dtype(T[c])]
        rows = []
        for k, g in T.groupby(keys + ["scores"], dropna=False):
            o = g[g.source == "observed"]
            s = g[g.source == "simulated"]
            for c in num:
                sv = s[c].dropna().to_numpy(float)
                rows.append({**dict(zip(keys + ["scores"], k if isinstance(k, tuple) else (k,))), "stat": c,
                             "observed": float(o[c].iloc[0]) if len(o) and pd.notna(o[c].iloc[0]) else np.nan,
                             "sim_mean": float(sv.mean()) if len(sv) else np.nan,
                             "sim_2.5%": float(np.percentile(sv, 2.5)) if len(sv) else np.nan,
                             "sim_97.5%": float(np.percentile(sv, 97.5)) if len(sv) else np.nan, "n_sim": len(sv)})
        return pd.DataFrame(rows)
    pkeys = [c for c in ("kind", "B_h", "outcome", "predictors", "day_demeaned") if c in PB.columns]
    bkeys = [c for c in ("quantity", "model", "x", "y") if c in BU.columns]
    SP, SB = summarise(PB, pkeys), summarise(BU, bkeys)
    SC = CC.groupby(["scores", "source", "subset"], as_index=False)[["delta_pct", "ci_lo_pct", "ci_hi_pct"]].mean()
    for name, T in (("D2_payback", SP), ("E_budget", SB), ("E_carryover", SC)):
        T.to_csv(rd / f"ephys_spikes_sleep_explore_{name}_2026c.csv", index=False)
    L = ["# Sleep-behaviour explore — Step D2 and Step E (ii) / (vi) on simulated records (cohort 2026c)", "",
         f"Plan §5 (rules written before results). Driver `ephys/sleep_sim_checks.py` (commit {gc}); bulk `{out}`; "
         f"{a.reps} replicates (carry-over: {a.carry_reps}); runtime {(time.time() - t0) / 60:.0f} min. **Technical ledger.**", "",
         "## Definitions", "", "```", (__doc__ or "").strip(), "```", "",
         "## D2: the morning-round payback, observed vs simulated without a REM deficit", "", *md_table(SP.round(4)), "",
         "## E (vi): the night -> next-day deviation slope, observed vs simulated", "", *md_table(SB.round(4)), "",
         "## E (ii): the carry-over curve (held-out gain of pre-wake history by wake bin), observed vs simulated", "",
         *md_table(SC.round(4)), ""]
    (rd / "ephys_spikes_sleep_explore_D2E_2026c.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_explore_D2E_2026c.json", {"run_dir": str(out), "git_commit": gc, "reps": a.reps})
    print("written", rd / "ephys_spikes_sleep_explore_D2E_2026c.md", flush=True)


if __name__ == "__main__":
    main()
