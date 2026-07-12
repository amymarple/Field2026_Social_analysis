r"""
selftest_search_excursions.py — offline planted-scenario check for Phase-4 modules 9 & 10
(search_excursions.py). Exit-coded PASS/FAIL, no DB/field data.

Planted scenarios:
  S1 RETURN-biased    — each animal cycles among its OWN recent sites -> gate_signal True (beats BOTH
                        the layout base-rate and the history-shuffle nulls).
  S2 LAYOUT-driven    — destinations drawn from the GLOBAL popularity, ignoring own recency -> the
                        observed return rate does NOT beat the layout base-rate null.
  S3 EXPLORE-biased   — each destination is a brand-new site -> low return rate, high novelty, no signal.
  S4 GEOMETRY         — a tortuous open-field excursion has low straightness + a directed move high;
                        the jitter gate flags a sub-3-floor radius as unresolvable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import search_excursions as se  # noqa: E402

T0 = pd.Timestamp("2026-06-28 22:00:00")


def _mk(rows):
    """rows: (shortid, night, minutes_from_T0, origin_roi, dest_roi, ttype)."""
    recs = []
    for i, (sid, night, mins, o, d, tt) in enumerate(rows):
        recs.append({"shortid": sid, "night": night, "origin_episode": i, "origin_roi": o,
                     "dest_roi": d, "transition_type": tt,
                     "t_depart": (T0 + pd.Timedelta(minutes=mins)).isoformat(),
                     "origin_dwell_s": 300.0, "clock_hour": 2})
    return pd.DataFrame(recs)


def s1_return_biased():
    # Each animal covers 8 DISTINCT sites over the night (so history-shuffle changes which are 'recent')
    # but every destination is drawn from its RECENT set (a return); the 8 animals have DISJOINT home
    # ranges (so a recent site is globally rare -> beats the layout base rate). A new site is introduced
    # ~1/3 of steps, otherwise the animal returns to its 2nd-most-recent distinct site.
    rows = []
    for ai, a in enumerate(["A", "B", "C", "D", "E", "F", "G", "H"]):
        for ni, night in enumerate([f"n{j}" for j in range(6)]):
            order = [0]; next_new = 1
            for step in range(14):
                if step % 3 == 0 and next_new <= 7:
                    d = next_new; next_new += 1
                else:
                    distinct = list(dict.fromkeys(reversed(order)))
                    d = distinct[min(1, len(distinct) - 1)]   # return to the 2nd-most-recent
                o = order[-1]
                rows.append((a, night, ni * 1000 + step * 10, f"a{ai}s{o}", f"a{ai}s{d}", "relocation"))
                order.append(d)
    tr = _mk(rows)
    ex = se.build_excursions(tr)
    gate = se.return_explore_gate(ex, tr, min_excursions=30, min_nights=3, n_perm=80, seed=1)
    # primary signal = return beyond the layout base rate (recency-specificity is a separate diagnostic)
    ok = gate["gate_signal"] and gate["beats_layout_base_rate"]
    print(f"  S1 return-biased: return_rate={gate['pooled_return_rate']} signal={gate['gate_signal']} "
          f"beats_layout={gate['beats_layout_base_rate']} recency_specific={gate['recency_specific']} -> {'PASS' if ok else 'FAIL'}")
    return ok


def s2_layout_driven():
    # many sites; one site 'hub' is globally very popular; every animal goes to hub regardless of recency.
    rng = np.random.default_rng(0)
    rows = []
    for a in ["A", "B", "C"]:
        for ni, night in enumerate([f"n{j}" for j in range(6)]):
            for step in range(6):
                o = f"o{rng.integers(0,8)}"
                d = "hub" if rng.random() < 0.7 else f"x{rng.integers(0,8)}"
                rows.append((a, night, ni * 600 + step * 10, o, d, "relocation"))
    tr = _mk(rows)
    ex = se.build_excursions(tr)
    gate = se.return_explore_gate(ex, tr, min_excursions=10, min_nights=3, n_perm=80, seed=2)
    # obs return should NOT significantly beat the layout base rate (hub-return IS the layout base rate)
    ok = not gate["beats_layout_base_rate"]
    print(f"  S2 layout-driven: return_rate={gate['pooled_return_rate']} beats_layout={gate['beats_layout_base_rate']} "
          f"(want False) -> {'PASS' if ok else 'FAIL'}")
    return ok


def s3_explore_biased():
    # every destination is a brand-new site never visited before
    rows = []
    k = 0
    for ni, night in enumerate([f"n{j}" for j in range(6)]):
        for step in range(6):
            rows.append(("A", night, ni * 600 + step * 10, f"site{k}", f"site{k+1}", "relocation")); k += 1
    tr = _mk(rows)
    ex = se.build_excursions(tr)
    gate = se.return_explore_gate(ex, tr, min_excursions=10, min_nights=3, n_perm=60, seed=3)
    ok = (gate["pooled_novel_rate"] > 0.8) and (not gate["gate_signal"])
    print(f"  S3 explore-biased: novel_rate={gate['pooled_novel_rate']} return_rate={gate['pooled_return_rate']} "
          f"signal={gate['gate_signal']} -> {'PASS' if ok else 'FAIL'}")
    return ok


def s4_geometry():
    # one tortuous open-field excursion (loops) + one directed relocation (straight); a tiny-radius jitter blob
    fx = []
    # tortuous: circle of radius 40 in
    t = pd.date_range(T0, periods=40, freq="5s")
    theta = np.linspace(0, 2 * np.pi, 40)
    for tt, th in zip(t, theta):
        fx.append(("A", "n0", tt.isoformat(), 200 + 40 * np.cos(th), 200 + 40 * np.sin(th)))
    # directed: straight line 0->300 in
    t2 = pd.date_range(T0 + pd.Timedelta(minutes=10), periods=30, freq="5s")
    for i, tt in enumerate(t2):
        fx.append(("A", "n0", tt.isoformat(), 10 * i, 0.0))
    # jitter blob: radius ~5 in (< 3 floors)
    t3 = pd.date_range(T0 + pd.Timedelta(minutes=20), periods=20, freq="5s")
    rng = np.random.default_rng(0)
    for tt in t3:
        fx.append(("A", "n0", tt.isoformat(), 500 + rng.normal(0, 3), 500 + rng.normal(0, 3)))
    fixes = pd.DataFrame(fx, columns=["shortid", "night", "datetime", "x", "y"])
    # bouts spanning each path segment (t_start..t_end); in_place = the tortuous loop, relocating = directed
    bouts = pd.DataFrame([
        {"shortid": "A", "night": "n0", "t_start": T0.isoformat(),
         "t_end": (T0 + pd.Timedelta(seconds=200)).isoformat(), "in_place": True, "relocating": False},
        {"shortid": "A", "night": "n0", "t_start": (T0 + pd.Timedelta(minutes=10)).isoformat(),
         "t_end": (T0 + pd.Timedelta(minutes=10, seconds=150)).isoformat(), "in_place": False, "relocating": True},
        {"shortid": "A", "night": "n0", "t_start": (T0 + pd.Timedelta(minutes=20)).isoformat(),
         "t_end": (T0 + pd.Timedelta(minutes=20, seconds=100)).isoformat(), "in_place": True, "relocating": False},
    ])
    geom = se.excursion_geometry(bouts, fixes)
    g0 = geom.iloc[0]; g1 = geom.iloc[1]; g2 = geom.iloc[2]
    ok = (g0["straightness"] < 0.3) and (g1["straightness"] > 0.8) and (not bool(g2["resolvable"]))
    print(f"  S4 geometry: tortuous_straight={g0['straightness']} directed_straight={g1['straightness']} "
          f"blob_resolvable={bool(g2['resolvable'])} -> {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    print("[selftest] search_excursions (Phase 4 modules 9 & 10)")
    results = {"S1_return": s1_return_biased(), "S2_layout": s2_layout_driven(),
               "S3_explore": s3_explore_biased(), "S4_geometry": s4_geometry()}
    ok = all(results.values())
    print(f"[selftest] {'PASS' if ok else 'FAIL'} — {sum(results.values())}/{len(results)} scenarios")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
