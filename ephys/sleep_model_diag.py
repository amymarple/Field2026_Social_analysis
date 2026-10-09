r"""POST-HOC diagnosis of Step B (added 2026-10-08 after Step B's results; NOT a pre-registered test): where in the
sleep do the counter variants differ?

Step B's pre-registered comparison over ALL NREM steps could not separate the gradual wake discount (tau_w) from a hard
reset after wakes >= 7 min or from a pause (all within ~0.1 %), while "erase at every wake" was clearly worse. The
variants make different predictions only after wakes, so the same held-out comparison is split by what happened since
the last REM, per NREM step:
  after_long     a wake >= 420 s occurred since the last REM (or since the record start if no REM yet);
  after_medium   no such wake, but a wake of 120-419 s did;
  after_short    only wakes < 120 s (or none) since the last REM.
For each test fold (1..), the variant chosen by Step B's nested forward chaining in each family (B = discount grid,
reset, pause) is refitted on the fold's training blocks (the same fit as Step B) and its per-step held-out log-loss is
averaged within each subset; Delta and the bootstrap CI over folds as in Step B (Phase-2 `compare`), per-animal signs.
Usage: python ephys/sleep_model_diag.py [--scorings final pass2med] [--workers 6]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from sleep_cycles import bouts  # noqa: E402
from sleep_model import PASS2MED, STATES, W, R, build_data, fit_eval, folds_of, records_for, to_arrays, variant_specs  # noqa: E402

SUBSETS = ("after_long", "after_medium", "after_short")


def since_rem_class(state: np.ndarray) -> dict[int, int]:
    """NREM bout start -> 2 (a wake >= 420 s since the last REM), 1 (a wake 120-419 s, no longer one), 0 (otherwise)."""
    out, cls = {}, 0
    for s, a, b in bouts(state):
        if s == R:
            cls = 0
        elif s == W:
            d = b - a
            cls = max(cls, 2 if d >= 420 else (1 if d >= 120 else 0))
        elif s == 3:
            out[a] = cls
    return out


def job(i: int, tr: np.ndarray, te: np.ndarray, D: dict, keys: dict[str, str]) -> list[dict]:
    te = te[np.isin(D["animal"][te], np.unique(D["animal"][tr]))]
    rows = []
    ll = {fam: fit_eval(D, tr, te, {"L1": True, "hist": k}) for fam, k in keys.items()}
    for c, lab in enumerate(SUBSETS[::-1]):                 # 0 short, 1 medium, 2 long
        m = D["cls"][te] == c
        if not m.any():
            continue
        an = D["animal"][te][m]
        rows.append({"fold": i, "subset": lab, "animal": "_all", "n": int(m.sum()), "n_rem": int((D["y"][te][m] == 1).sum()),
                     **{f"ll_{f}": float(v[m].mean()) for f, v in ll.items()}})
        for a in np.unique(an):
            ma = an == a
            rows.append({"fold": i, "subset": lab, "animal": a, "n": int(ma.sum()), "n_rem": int((D["y"][te][m][ma] == 1).sum()),
                         **{f"ll_{f}": float(v[m][ma].mean()) for f, v in ll.items()}})
    return rows


def run(label: str, states: Path, chosen: pd.DataFrame, workers: int) -> pd.DataFrame:
    from joblib import Parallel, delayed
    from sleep_schedule_phase2 import compare
    t0 = time.time()
    fams = {"B": "chosen_B", "reset": "chosen_reset", "pause": "chosen_pause"}
    need = sorted({c[2:] for col in fams.values() for c in chosen[col].dropna()})
    allv = variant_specs()
    recs = records_for(states)
    steps = build_data(recs, {k: allv[k] for k in need})
    cls = np.zeros(len(steps), np.int8)
    byrid = {rc["record_id"]: rc for rc in recs}
    for rid, g in steps.groupby("record_id"):
        c = since_rem_class(byrid[rid]["state"])
        cls[steps.index.get_indexer(g.index)] = [c[b] for b in g.bout_start]
    D = to_arrays(steps)
    D["cls"] = cls
    folds = folds_of(D)
    jobs = []
    for i, (tr, te) in enumerate(folds):
        if i == 0:
            continue
        row = chosen[chosen.fold == i]
        keys = {f: row[col].iloc[0][2:] for f, col in fams.items()}
        jobs.append((i, tr, te, keys))
    res = Parallel(n_jobs=workers, backend="loky")(delayed(job)(i, tr, te, D, k) for i, tr, te, k in jobs)
    T = pd.DataFrame([r for rr in res for r in rr])
    out = []
    for sub in SUBSETS:
        F = T[(T.subset == sub) & (T.animal == "_all")]
        FA = T[(T.subset == sub) & (T.animal != "_all")]
        for lo in ("reset", "pause"):
            r = compare(F, FA, lo, "B", sub)
            r["scores"] = label
            out.append(r)
        out.append({**compare(F, FA, "pause", "reset", sub), "scores": label})
    print(f"[{label}] diag done {time.time() - t0:.0f} s", flush=True)
    return pd.DataFrame(out), T.assign(scores=label)


def main() -> None:
    from _common import git_commit, write_json
    from output_paths import report_dir, run_dir
    from sleep_quant import md_table
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scorings", nargs="+", default=["final", "pass2med"])
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    rd = report_dir("2026c", "ephys_spikes")
    out = run_dir("sleep_explore_B_diag", "2026c")
    gc = git_commit()
    chosen = pd.read_csv(rd / "ephys_spikes_sleep_explore_B_chosen_2026c.csv")
    res, folds = [], []
    for lab in a.scorings:
        if lab == "final":
            ch = chosen
        else:                                           # Step B saved only FINAL's nested choices: the same blocks, FINAL's keys
            ch = chosen
        C, T = run(lab, STATES if lab == "final" else PASS2MED, ch, a.workers)
        res.append(C)
        folds.append(T)
    C = pd.concat(res, ignore_index=True)
    pd.concat(folds).to_csv(out / "diag_folds.csv", index=False)
    C.to_csv(rd / "ephys_spikes_sleep_explore_B_diag_2026c.csv", index=False)
    cols = ["scores", "subset", "comparison", "n_steps", "n_rem", "delta_pct", "ci_lo_pct", "ci_hi_pct", "folds_better", "folds", "animals_better", "holds"]
    L = ["# Step B post-hoc diagnosis: where do the counter variants differ? (cohort 2026c)", "",
         f"**POST HOC** (added after Step B's results; not a pre-registered test). Driver `ephys/sleep_model_diag.py` (commit {gc}); "
         f"bulk `{out}`.", "", "## Definitions", "", "```", (__doc__ or "").strip(), "```", "",
         "## Held-out comparisons by what happened since the last REM", "", *md_table(C[[c for c in cols if c in C.columns]].round(4)), ""]
    (rd / "ephys_spikes_sleep_explore_B_diag_2026c.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_explore_B_diag_2026c.json", {"run_dir": str(out), "git_commit": gc})
    print(C[[c for c in cols if c in C.columns]].round(3).to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
