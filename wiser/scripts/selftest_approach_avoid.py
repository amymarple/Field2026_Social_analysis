r"""
selftest_approach_avoid.py — offline PASS/FAIL for Phase 3 / Module 7 (coarse, heading-free in-bout
approach/avoid). No DB. Plants controlled bout+partner geometries and asserts the toward-ness metric
and the measurement gate behave: real toward/away beats the direction-randomized null; random-
direction bouts do not; sub-floor / sub-1 m pairs are excluded; and the day-shuffle separates
real-time SOCIAL approach from shared-resource LAYOUT geometry.

Run under the anaconda3 interpreter (pandas/numpy):
    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\selftest_approach_avoid.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import approach_avoid as aa                       # noqa: E402
from environment_map import EnvironmentMap        # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


em = EnvironmentMap.from_paths(str(ROOT / "configs/environment_map/2026-06-28_to_2026-07-05.yaml"),
                              str(ROOT / "configs/wiser_rois.json"))
H1 = em.center("house_1")


def gen(kind, n_bouts, rng, *, disp=100.0, d0=150.0, nights=("2026-06-29",), site=None, site_spread=55.0):
    """Emit (fixes, bouts). kind ∈ {approach, avoid, random}.
    SOCIAL (``site`` is None): the partner sits at a night-specific spot; the focal heads per ``kind``
    relative to THIS night's partner. LAYOUT (``site`` given): the partner sits NEAR the shared site
    with realistic cross-night spread ``site_spread``, and the focal heads toward the SITE CENTRE (not
    the specific partner) — so approach is to the site, and a different-night partner (also near the
    site) yields a similar toward-ness (the day-shuffle cannot separate it => not social)."""
    fixes = []; bouts = []; bid = 0
    for night in nights:
        base = pd.Timestamp(f"{night} 22:00:00")
        for k in range(n_bouts):
            t0 = base + pd.Timedelta(seconds=90 * k); t1 = t0 + pd.Timedelta(seconds=20)
            f0 = (rng.uniform(300, 500), rng.uniform(300, 500))
            if site is not None:                                     # LAYOUT
                partner = (site[0] + rng.normal(0, site_spread), site[1] + rng.normal(0, site_spread))
                target = site                                       # focal heads toward the SITE centre
            else:                                                    # SOCIAL
                partner = (f0[0] + d0 * np.cos(rng.uniform(0, 2 * np.pi)),
                           f0[1] + d0 * np.sin(rng.uniform(0, 2 * np.pi)))
                target = partner
            ap = np.arctan2(target[1] - f0[1], target[0] - f0[0])
            if kind == "approach":
                ang = ap
            elif kind == "avoid":
                ang = ap + np.pi
            else:
                ang = rng.uniform(0, 2 * np.pi)
            f1 = (f0[0] + disp * np.cos(ang), f0[1] + disp * np.sin(ang))
            for dt in (-0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75):
                fixes.append(dict(shortid="F", night=night, datetime=t0 + pd.Timedelta(seconds=dt),
                                  x=f0[0] + rng.normal(0, 2), y=f0[1] + rng.normal(0, 2)))
                fixes.append(dict(shortid="F", night=night, datetime=t1 + pd.Timedelta(seconds=dt),
                                  x=f1[0] + rng.normal(0, 2), y=f1[1] + rng.normal(0, 2)))
            for dt in (-1.5, -1.0, -0.5, 0.0):
                fixes.append(dict(shortid="P", night=night, datetime=t0 + pd.Timedelta(seconds=dt),
                                  x=partner[0] + rng.normal(0, 2), y=partner[1] + rng.normal(0, 2)))
            bouts.append(dict(shortid="F", night=night, bout_id=bid, t_start=t0, t_end=t1,
                              spans_dropout=False, has_gap=False)); bid += 1
    return pd.DataFrame(fixes), pd.DataFrame(bouts)


def ctx_of(fixes, bouts, **kw):
    return aa.bout_approach_context(bouts, fixes, em, **kw)


# ---------------------------------------------------------------------------
print("A. toward-ness metric + direction-randomized null")
rng = np.random.default_rng(1)
fA, bA = gen("approach", 40, rng)
cA = ctx_of(fA, bA)
dnA = aa.direction_null_z(cA, n_perm=200, seed=1)
check("A approach: mean toward ~ +1, direction-null z >> 2",
      cA["toward"].mean() > 0.9 and dnA["z"] > 3, f"mean toward={cA['toward'].mean():.2f}, z={dnA['z']:.1f}, n={len(cA)}")

rng = np.random.default_rng(2)
fV, bV = gen("avoid", 40, rng)
cV = ctx_of(fV, bV)
dnV = aa.direction_null_z(cV, n_perm=200, seed=2)
check("B avoid: mean toward ~ -1, direction-null z << -2",
      cV["toward"].mean() < -0.9 and dnV["z"] < -3, f"mean toward={cV['toward'].mean():.2f}, z={dnV['z']:.1f}")

rng = np.random.default_rng(3)
fR, bR = gen("random", 60, rng)
cR = ctx_of(fR, bR)
dnR = aa.direction_null_z(cR, n_perm=200, seed=3)
check("C random direction: mean toward ~ 0, direction-null |z| < 2 (rejected)",
      abs(cR["toward"].mean()) < 0.2 and abs(dnR["z"]) < 2, f"mean toward={cR['toward'].mean():.2f}, z={dnR['z']:.2f}")

# ---------------------------------------------------------------------------
print("D. jitter-safe filters (sub-floor displacement, sub-1 m partner excluded)")
rng = np.random.default_rng(4)
fS, bS = gen("approach", 20, rng, disp=6.0)               # disp < min_disp_in=14
cS = ctx_of(fS, bS)
check("D1 sub-floor displacement bouts excluded", len(cS) == 0, f"rows={len(cS)}")
rng = np.random.default_rng(5)
fP, bP = gen("approach", 20, rng, d0=20.0)                # partner < 1 m (39.37 in)
cP = ctx_of(fP, bP)
check("D2 sub-1 m partners excluded", len(cP) == 0, f"rows={len(cP)}")

# ---------------------------------------------------------------------------
print("E. NIGHT-BLOCK gate: day-shuffle separates SOCIAL approach from shared-resource LAYOUT geometry")
# The gate is night-level (sign test over nights), so use 8 nights for power (8/8 -> p~0.008).
NIGHTS = tuple(f"2026-06-{d:02d}" for d in range(23, 31)) + ("2026-07-01",)  # 9 valid nights
# SOCIAL: partner at a night-specific spot; focal heads toward THIS night's partner
rng = np.random.default_rng(6)
fSoc, bSoc = gen("approach", 30, rng, nights=NIGHTS)
cSoc = ctx_of(fSoc, bSoc)
gSoc = aa.measurement_gate(cSoc, fSoc, n_perm_dir=120, n_perm_day=30, min_pairs=20, min_pairs_per_night=15, seed=6)
check("E1 SOCIAL (night-specific partner) -> night-consistent gate_social True",
      gSoc["gate_resolvable"] and gSoc["gate_social"],
      f"resolvable={gSoc['gate_resolvable']}, social={gSoc['gate_social']}, "
      f"e_dir_p={gSoc['pooled_night']['e_dir_signtest_p']}, e_day_p={gSoc['pooled_night']['e_day_signtest_p']}")

# LAYOUT: partner near the shared site house_1 (realistic spread), focal heads toward the SITE -> above
# geometry every night, but a different-night partner is STILL near house_1 -> e_day ~ 0 -> NOT social.
rng = np.random.default_rng(7)
fLay, bLay = gen("approach", 30, rng, nights=NIGHTS, site=H1)
cLay = ctx_of(fLay, bLay)
gLay = aa.measurement_gate(cLay, fLay, n_perm_dir=120, n_perm_day=30, min_pairs=20, min_pairs_per_night=15, seed=7)
check("E2 LAYOUT (partner at a shared site) -> resolvable but gate_social False",
      gLay["gate_resolvable"] and (not gLay["gate_social"]),
      f"resolvable={gLay['gate_resolvable']}, social={gLay['gate_social']}, "
      f"e_dir_p={gLay['pooled_night']['e_dir_signtest_p']}, e_day_p={gLay['pooled_night']['e_day_signtest_p']}")

# ---------------------------------------------------------------------------
print()
if FAILS:
    print(f"FAIL — {len(FAILS)} check(s) failed: {FAILS}")
    sys.exit(1)
print("PASS — approach/avoid gate healthy (toward-ness resolvable; direction+day-shuffle nulls discriminate)")
sys.exit(0)
