r"""selftest_heat_gated_relocation.py — offline planted checks for the heat-gate stats primitives
(logistic_fit_1d, logistic_threshold, cluster_bootstrap) + an end-to-end within-day Δ recovery on
synthetic gate behaviour. No DB. PASS/FAIL exit code, like the other WISER self-tests."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import wiser_analysis_utils as w   # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILS.append(name)


def main() -> None:
    print("=== selftest: heat-gated relocation primitives ===")

    # 1) logistic_fit_1d recovers a planted temperature gate (P(out) steps up near 32 C)
    rng = np.random.default_rng(0)
    x = rng.uniform(20, 40, 4000)
    p = 1.0 / (1.0 + np.exp(-2.0 * (x - 32.0)))
    y = (rng.uniform(size=x.size) < p).astype(float)
    b0, b1 = w.logistic_fit_1d(x, y)
    thr = w.logistic_threshold(b0, b1, 0.5)
    check("logistic slope positive (dose-response up)", b1 > 0.5)
    check(f"logistic threshold ~32C (got {thr:.2f})", abs(thr - 32.0) < 1.0)
    check("logistic_fit_1d NaN on one-class y", not np.isfinite(w.logistic_fit_1d(x, np.ones_like(y))[1]))

    # 2) logistic_threshold algebra
    check("threshold(-64, 2, 0.5) == 32", abs(w.logistic_threshold(-64.0, 2.0, 0.5) - 32.0) < 1e-9)
    check("threshold at level 0.15 ~ 31.13", abs(w.logistic_threshold(-64.0, 2.0, 0.15) - 31.13) < 0.1)
    check("threshold NaN when slope ~ 0", not np.isfinite(w.logistic_threshold(1.0, 0.0, 0.5)))

    # 3) cluster_bootstrap — positive effect excludes 0; null straddles 0
    rng = np.random.default_rng(1)
    pos = [rng.normal(0.20, 0.10, 5) for _ in range(6)]     # 6 days x 5 rats, mean +0.20
    cbp = w.cluster_bootstrap(pos, seed=2)
    check("cluster_bootstrap observed ~ +0.20", abs(cbp["observed"] - 0.20) < 0.08)
    check("cluster_bootstrap positive: CI excludes 0 & frac>0 high", cbp["lo"] > 0 and cbp["frac_gt0"] > 0.95)
    null = [rng.normal(0.0, 0.10, 5) for _ in range(6)]
    cbn = w.cluster_bootstrap(null, seed=2)
    check("cluster_bootstrap null: CI straddles 0", cbn["lo"] < 0 < cbn["hi"] and 0.2 < cbn["frac_gt0"] < 0.8)
    check("cluster_bootstrap n_clusters=6", cbp["n_clusters"] == 6)

    # 4) end-to-end: planted within-day gate -> per-rat-day ΔP(out) recovered, day-clustered
    rng = np.random.default_rng(3)
    groups = []
    for _day in range(5):                                    # 5 hot days
        deltas = []
        for _rat in range(5):                                # 5 rats
            below = (rng.uniform(size=20) < 0.05).mean()     # below gate: rarely out
            above = (rng.uniform(size=20) < 0.40).mean()     # above gate: often out
            deltas.append(above - below)
        groups.append(deltas)
    cb = w.cluster_bootstrap(groups, seed=4)
    check(f"within-day ΔP(out) recovered ~+0.35 (got {cb['observed']:.2f})", cb["observed"] > 0.25)
    check("within-day Δ: CI excludes 0 & frac>0 high", cb["lo"] > 0 and cb["frac_gt0"] > 0.95)

    print(f"\n{'PASS' if not FAILS else 'FAIL'} - {len(FAILS)} failure(s)"
          + (": " + "; ".join(FAILS) if FAILS else ""))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
