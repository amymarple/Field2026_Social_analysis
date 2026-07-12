r"""selftest_sleep_site_hierarchy.py — offline planted checks for the sleep-site landmark
HIERARCHY primitives (net_flux_scores, anchor_concentration_kl, permutation_pvalue, kendall_w)
plus an end-to-end exchangeable-vs-ranked recovery on synthetic rat-day state sequences. No DB.
PASS/FAIL exit code, like the other WISER self-tests."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import wiser_analysis_utils as w   # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILS.append(name)


def _kl_from_seqs(seqs):
    anc = pd.Series([s[0] for s in seqs]).value_counts().to_dict()
    dwell = pd.Series([x for s in seqs for x in s]).value_counts(normalize=True).to_dict()
    return w.anchor_concentration_kl(anc, dwell), dwell


def _occupancy_null(seqs, dwell, rng, n=500):
    states = list(dwell); probs = np.array([dwell[s] for s in states], float)
    probs = probs / probs.sum()
    out = []
    for _ in range(n):
        draw = rng.choice(states, size=len(seqs), p=probs)
        out.append(w.anchor_concentration_kl(pd.Series(draw).value_counts().to_dict(), dwell))
    return out


def main() -> None:
    print("=== selftest: sleep-site hierarchy primitives ===")

    # 1) net_flux_scores — planted net sink X (7 in, 1 out)
    tdf = pd.DataFrame([{"from_state": "A", "to_state": "X", "n": 5},
                        {"from_state": "B", "to_state": "X", "n": 2},
                        {"from_state": "X", "to_state": "A", "n": 1}])
    nf = w.net_flux_scores(tdf).set_index("state")
    check("net_flux X arrivals=7, departures=1", nf.loc["X", "arrivals"] == 7 and nf.loc["X", "departures"] == 1)
    check("net_flux X = +0.75 (sink) and top-ranked", abs(nf.loc["X", "net_flux"] - 0.75) < 1e-9 and nf.index[0] == "X")
    check("net_flux A < 0 (source)", nf.loc["A", "net_flux"] < 0)
    check("net_flux empty -> empty", w.net_flux_scores(pd.DataFrame(columns=["from_state", "to_state", "n"])).empty)

    # 2) anchor_concentration_kl — exchangeable ~0 vs concentrated ~log2
    D_flat = w.anchor_concentration_kl({"A": 5, "B": 5}, {"A": 0.5, "B": 0.5})
    D_conc = w.anchor_concentration_kl({"A": 10, "B": 0}, {"A": 0.5, "B": 0.5})
    check("KL(anchor==dwell) ~ 0", abs(D_flat) < 1e-9)
    check("KL(all-anchor-on-half-dwell) ~ log2", abs(D_conc - np.log(2)) < 1e-6)
    check("KL concentrated > flat", D_conc > D_flat)

    # 3) permutation_pvalue — +1 smoothing + tails
    p_small = w.permutation_pvalue(0.75, [0.1, 0.2, 0.3, 0.2, 0.15, 0.25, 0.3, 0.1, 0.2, 0.05])
    check("perm p = 1/11 when obs exceeds all 10 null", abs(p_small - 1 / 11) < 1e-9)
    p_big = w.permutation_pvalue(0.2, [0.1, 0.3, 0.25, 0.4, 0.2])   # null>=0.2 -> {0.3,0.25,0.4,0.2}=4
    check("perm p = 5/6 when obs common", abs(p_big - 5 / 6) < 1e-9)
    check("perm p NaN on empty null", np.isnan(w.permutation_pvalue(0.5, [])))

    # 4) kendall_w — perfect vs opposing
    check("kendall W perfect concordance = 1", abs(w.kendall_w([[1, 2, 3], [1, 2, 3], [1, 2, 3]]) - 1.0) < 1e-9)
    check("kendall W opposing rankings = 0", abs(w.kendall_w([[1, 2, 3], [3, 2, 1]]) - 0.0) < 1e-9)
    check("kendall W NaN with <2 judges", np.isnan(w.kendall_w([[1, 2, 3]])))

    # 5) end-to-end: RANKED (X always anchor but low dwell) -> exchangeability rejected
    rng = np.random.default_rng(7)
    ranked = [["X"] + list(rng.choice(["A", "B", "C"], size=6)) for _ in range(40)]
    D_obs, dwell = _kl_from_seqs(ranked)
    p_ranked = w.permutation_pvalue(D_obs, _occupancy_null(ranked, dwell, rng))
    check(f"RANKED: anchor KL={D_obs:.2f} exceeds occupancy null (p={p_ranked:.3f} <= 0.05)", p_ranked <= 0.05)

    # EXCHANGEABLE control: anchor drawn BY dwell -> consistent with occupancy (p large)
    exch = [list(rng.choice(["A", "B", "C", "X"], size=7, p=[0.4, 0.3, 0.2, 0.1])) for _ in range(40)]
    D2, dwell2 = _kl_from_seqs(exch)
    p_exch = w.permutation_pvalue(D2, _occupancy_null(exch, dwell2, rng))
    check(f"EXCHANGEABLE control: anchor ~ occupancy (p={p_exch:.3f} > 0.05)", p_exch > 0.05)

    print(f"\n{'PASS' if not FAILS else 'FAIL'} - {len(FAILS)} failure(s)"
          + (": " + "; ".join(FAILS) if FAILS else ""))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
