r"""
selftest_route_vocabulary.py — offline, synthetic, exit-coded PASS/FAIL check of the route-vocabulary
validation machinery. No WISER data. Plants four scenarios with KNOWN ground truth and runs the REAL
driver analyses (analyze_route_vocabulary.a1..a7 + derive_criteria + decide_verdict) on each, then
unit-checks the A/B/C/D decision boundaries directly.

  1. discrete shared vocabulary (4 prototypes, 2 shapes per endpoint pair) -> verdict A
  2. spatial graph / endpoint-only (straight edges between 4 nodes)        -> verdict B
  3. structureless continuum (random Brownian bridges)                     -> verdict C or D
  4. global-dictionary leakage                                            -> in-sample cov >> held-out

    KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1 \
      C:/Users/Cornell/anaconda3/python.exe scripts/selftest_route_vocabulary.py
"""
from __future__ import annotations

import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import route_vocabulary as rv                 # noqa: E402
import analyze_route_vocabulary as drv        # noqa: E402

L = 20
T = np.linspace(0.0, 1.0, L)
NIGHTS = [f"2026-06-{d:02d}" for d in range(28, 28 + 6)]     # 6 nights
ANIMALS = ["12378", "12380", "12386", "12395", "12407"]
PER = 8
THETA = 21.0
NODES = [(60.0, 60.0), (360.0, 60.0), (60.0, 360.0), (360.0, 360.0)]


def _chord(s, e):
    return np.column_stack([s[0] + (e[0] - s[0]) * T, s[1] + (e[1] - s[1]) * T])


def _shape(s, e, sign, amp=80.0):
    c = _chord(s, e)
    c[:, 1] = c[:, 1] + sign * amp * np.sin(np.pi * T)     # transverse bulge; 0 at both endpoints
    return c


PROTOS = [_shape((60, 60), (360, 60), +1), _shape((60, 60), (360, 60), -1),
          _shape((60, 360), (360, 360), +1), _shape((60, 360), (360, 360), -1)]


def assemble(sampler, *, seed):
    rng = np.random.default_rng(seed)
    paths, recs = [], []
    for ni, night in enumerate(NIGHTS):
        for a in ANIMALS:
            for k in range(PER):
                paths.append(sampler(rng))
                recs.append({"night": night, "shortid": a,
                             "t_start_ms": 1000 * (ni * 86400 + k * 1800)})   # 30-min spacing
    return np.asarray(paths, float), pd.DataFrame(recs)


def s_discrete(rng):
    return PROTOS[int(rng.integers(4))] + rng.normal(0, 4.0, (L, 2))


def s_endpoint_graph(rng):
    i, j = rng.choice(4, 2, replace=False)
    return _chord(NODES[i], NODES[j]) + rng.normal(0, 3.0, (L, 2))


def s_continuum(rng):
    s = rng.uniform(60, 360, 2); e = rng.uniform(60, 360, 2)
    b = np.column_stack([rv._bbridge(L, rng), rv._bbridge(L, rng)])
    b_rms = np.sqrt((b ** 2).sum(1).mean()) or 1.0
    return _chord(s, e) + b * (60.0 / b_rms)


def run_pipeline(paths, bouts):
    a0 = drv.a0_support(bouts, theta=THETA, endpoint_bin=42.0)
    a1 = drv.a1_temporal_holdout(paths, bouts, NIGHTS, theta=THETA)
    a2 = drv.a2_loao(paths, bouts, theta=THETA, seed=0)
    a3 = drv.a3_compression(paths, bouts, NIGHTS, sigma_in=7.0, bits_per_param=16, L=L)
    a4 = drv.a4_endpoint(paths, bouts, NIGHTS, theta=THETA, endpoint_bin=42.0)
    a5 = drv.a5_geometry_null(paths, bouts, NIGHTS, theta=THETA, seed=0)
    crit = drv.derive_criteria(a0, a1, a2, a3, a4, a5)
    insufficient = bool(a0["median_bouts_per_animal_night"] < 2 or a0["n_nights"] < 3
                        or a1.empty or a3.empty)
    v = rv.decide_verdict(crit, insufficient_support=insufficient)
    return crit, v, (a3, a4, a5)


def main():
    fails = []

    def check(name, cond, detail=""):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
        if not cond:
            fails.append(name)

    print("Scenario 1: discrete shared vocabulary -> expect A")
    p, b = assemble(s_discrete, seed=1)
    crit, v, (a3, a4, a5) = run_pipeline(p, b)
    print("   criteria:", {k: crit[k] for k in rv.VERDICT_CRITERIA})
    check("discrete mdl_has_finite_min", crit["mdl_has_finite_min"])
    check("discrete dict_beats_pca (MDL)", crit["dict_beats_pca"])
    check("discrete loao_generalizes", crit["loao_generalizes"])
    check("discrete beats_geometry_null", crit["beats_geometry_null"])
    check("discrete shape_beyond_endpoints", crit["shape_beyond_endpoints"])
    check("discrete verdict == A", v["verdict"] == "A", v["verdict"])

    print("Scenario 2: spatial graph / endpoint-only -> expect B")
    p, b = assemble(s_endpoint_graph, seed=2)
    crit, v, _ = run_pipeline(p, b)
    print("   criteria:", {k: crit[k] for k in rv.VERDICT_CRITERIA})
    check("graph endpoint_explains_most", crit["endpoint_explains_most"])
    check("graph shape_beyond_endpoints is False", not crit["shape_beyond_endpoints"])
    check("graph verdict == B", v["verdict"] == "B", v["verdict"])

    print("Scenario 3: structureless continuum -> expect C or D")
    p, b = assemble(s_continuum, seed=3)
    crit, v, _ = run_pipeline(p, b)
    print("   criteria:", {k: crit[k] for k in rv.VERDICT_CRITERIA})
    check("continuum verdict in {C,D}", v["verdict"] in ("C", "D"), v["verdict"])
    check("continuum not verdict A", v["verdict"] != "A", v["verdict"])

    print("Scenario 4: global-dictionary leakage -> in-sample cov >> held-out cov")
    p, b = assemble(s_continuum, seed=4)
    protos_all, _ = rv.learn_leader_dictionary(p, theta=THETA)
    _, res_in = rv.assign(p, protos_all)
    cov_in = float(np.mean(res_in <= THETA))
    tr = np.isin(b["night"].to_numpy(), NIGHTS[:3]); te = ~tr
    p_tr, _ = rv.learn_leader_dictionary(p[tr], theta=THETA)
    _, res_out = rv.assign(p[te], p_tr)
    cov_out = float(np.mean(res_out <= THETA))
    print(f"   in-sample cov={cov_in:.2f}  held-out cov={cov_out:.2f}")
    check("leakage gap > 0.1", cov_in - cov_out > 0.1, f"{cov_in:.2f} vs {cov_out:.2f}")

    print("Unit: decide_verdict boundaries")
    allc = dict.fromkeys(rv.VERDICT_CRITERIA, True)
    a_case = {**allc, "endpoint_explains_most": False}          # every A-criterion holds
    check("verdict A", rv.decide_verdict(a_case)["verdict"] == "A")
    b_case = dict.fromkeys(rv.VERDICT_CRITERIA, False)          # endpoints explain + repertoire CLOSES
    b_case.update(endpoint_explains_most=True, novelty_saturates=True)
    check("verdict B", rv.decide_verdict(b_case)["verdict"] == "B")
    c_case = dict.fromkeys(rv.VERDICT_CRITERIA, False)          # endpoints explain but repertoire OPEN
    c_case.update(endpoint_explains_most=True, novelty_saturates=False)
    check("verdict C (endpoint manifold)", rv.decide_verdict(c_case)["verdict"] == "C")
    c_case2 = dict.fromkeys(rv.VERDICT_CRITERIA, False)         # shape beyond endpoints, no discrete scale
    c_case2.update(beats_geometry_null=True, shape_beyond_endpoints=True)
    check("verdict C (shape manifold)", rv.decide_verdict(c_case2)["verdict"] == "C")
    d_case = dict.fromkeys(rv.VERDICT_CRITERIA, False)          # nothing reused
    check("verdict D (structureless)", rv.decide_verdict(d_case)["verdict"] == "D")
    check("verdict D (thin support)",
          rv.decide_verdict(allc, insufficient_support=True)["verdict"] == "D")

    print()
    if fails:
        print(f"FAIL — {len(fails)} check(s) failed: {fails}")
        sys.exit(1)
    print("PASS — route-vocabulary validation machinery healthy")


if __name__ == "__main__":
    main()
