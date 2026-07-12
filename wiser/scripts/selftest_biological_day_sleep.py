r"""
selftest_biological_day_sleep.py — offline checks for the biological-day sleep core
(no DB / no weather). Exit 0 = PASS, 1 = FAIL.

Covers:
  1. locomotor_emergence — recovers an injected afternoon movement rise (~18/20:00), the
     never-rises clamp (=emergence_hi, crossed=False) and early-rise clamp. NONE past midnight.
  2. window_sleep_site + relocation_tier — morning house_1 vs day house_2 differ / major tier.
  3. detect_site_changepoint — recovers a planted transition (state-labelled via classify_site_state,
     full ROI set); a stable day is NOT supported.
  4. classify_site_state — house/refuge/water/doorway/exposed buckets + refuge_4 date-gating.
  5. trunk_state_dwell_transitions — a planted 3-state path -> 2 relocations + dwell by state.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import wiser_analysis_utils as w              # noqa: E402
import analyze_biological_day_sleep as D      # noqa: E402

FAILS: list[str] = []


def check(cond, msg):
    print(("  ok  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


def _profile_day(day, rise_at, base=0.08, hi=0.20):
    rows = []
    for i in range(0, 25):                      # bin_hours 12.0 .. 24.0
        bh = 12.0 + 0.5 * i
        rows.append({"sleep_day": day, "bin_hours": bh, "active_frac": hi if bh >= rise_at else base})
    return pd.DataFrame(rows)


def test_emergence():
    print("[1] locomotor_emergence")
    prof = pd.concat([
        _profile_day("2026-06-29", rise_at=18.0),
        _profile_day("2026-06-30", rise_at=20.0),
        _profile_day("2026-07-01", rise_at=99.0),   # never
        _profile_day("2026-07-02", rise_at=15.0),   # early
    ], ignore_index=True)
    em = w.locomotor_emergence(prof).set_index("sleep_day")
    col = "locomotor_emergence_hour"
    check(abs(em.loc["2026-06-29", col] - 18.0) < 0.6, f"normal emergence ~18 (got {em.loc['2026-06-29', col]:.1f})")
    check(abs(em.loc["2026-06-30", col] - 20.0) < 0.6, f"late emergence ~20 (got {em.loc['2026-06-30', col]:.1f})")
    check(em.loc["2026-07-01", col] == 21.0 and not bool(em.loc["2026-07-01", "crossed"]),
          "never-rises -> clamp emergence_hi=21, crossed=False")
    check(em.loc["2026-07-02", col] == 16.0, "early rise -> clamp emergence_lo=16")
    check(bool((em[col] <= 21.0).all()), "NO emergence past midnight (all <= 21:00)")


def _fixes(night, sid, cx, cy, roi, n=40, jit=2.0):
    rng = np.random.default_rng(abs(hash((night, sid, roi))) % (2**32))
    return pd.DataFrame({"night": night, "shortid": sid,
                         "x": cx + rng.normal(0, jit, n), "y": cy + rng.normal(0, jit, n),
                         "resting": True, "roi": roi})


ROI_CFG = {"rois": [
    {"name": "house_1", "shape": "rect", "x": 100.0, "y": 100.0, "width_in": 36.0, "height_in": 26.0, "orientation_deg": 0.0},
    {"name": "house_2", "shape": "rect", "x": 300.0, "y": 100.0, "width_in": 36.0, "height_in": 26.0, "orientation_deg": 0.0},
    {"name": "refuge_1", "shape": "circle", "x": 100.0, "y": 300.0, "radius_in": 10.0},
    {"name": "water_1", "shape": "circle", "x": 300.0, "y": 300.0, "radius_in": 8.0},
    {"name": "refuge_4", "shape": "circle", "x": 500.0, "y": 300.0, "radius_in": 10.0,
     "valid_until": "2026-07-07T13:00:00-04:00"}]}


def test_sites_diff():
    print("[2] window_sleep_site difference")
    mo = _fixes("2026-06-30", "A", 100, 100, "house_1")
    da = _fixes("2026-06-30", "A", 300, 100, "house_2")
    ms = w.window_sleep_site(mo, ROI_CFG, window_label="morning").iloc[0]
    ds = w.window_sleep_site(da, ROI_CFG, window_label="day").iloc[0]
    check(ms["nearest_shelter"] == "house_1" and ds["nearest_shelter"] == "house_2", "morning house_1, day house_2")
    shift = float(np.hypot(ds["centroid_x"] - ms["centroid_x"], ds["centroid_y"] - ms["centroid_y"]))
    check(w.relocation_tier(shift, True) == "major_shelter_switch", f"differ -> major tier (shift {shift:.0f})")


def test_changepoint():
    print("[3] detect_site_changepoint + classify_site_state (full ROI state space)")
    base = pd.Timestamp("2026-06-30 10:00")
    rng = np.random.default_rng(7)
    rows = []
    for i in range(120):                        # planted house_1 -> refuge_1 halfway
        t = base + pd.Timedelta(minutes=3 * i)
        cx, cy = (100.0, 100.0) if i < 60 else (100.0, 300.0)
        rows.append({"datetime": t + pd.Timedelta(hours=4),
                     "x": cx + rng.normal(0, 3), "y": cy + rng.normal(0, 3)})
    g = pd.DataFrame(rows)
    cp = w.detect_site_changepoint(g, bin_s=300, smooth_bins=3, min_seg_bins=3, min_disp_in=100.0)
    check(cp["supported"] and cp["displacement_in"] > 150, f"planted step supported (disp {cp['displacement_in']:.0f})")
    frm = w.classify_site_state(cp["pre_x"], cp["pre_y"], ROI_CFG, date="2026-06-30")
    to = w.classify_site_state(cp["post_x"], cp["post_y"], ROI_CFG, date="2026-06-30")
    check(frm == "house_1" and to == "refuge_1", f"direction house_1->refuge_1 (NOT house_2; got {frm}->{to})")
    stable = pd.DataFrame([{"datetime": base + pd.Timedelta(hours=4, minutes=3 * i),
                            "x": 100 + rng.normal(0, 3), "y": 100 + rng.normal(0, 3)} for i in range(120)])
    check(not w.detect_site_changepoint(stable, bin_s=300, smooth_bins=3, min_seg_bins=3, min_disp_in=100.0)["supported"],
          "stable day NOT supported")


def test_classify_state():
    print("[4] classify_site_state buckets + refuge_4 date-gating")
    c = lambda x, y, d="2026-06-30": w.classify_site_state(x, y, ROI_CFG, date=d)
    check(c(100, 100) == "house_1", "house_1 core")
    check(c(100, 300) == "refuge_1", "refuge_1 circle")
    check(c(300, 300) == "water_1", "water_1 circle")
    check(c(148, 100) == "doorway", f"near-house band -> doorway (got {c(148, 100)})")
    check(c(100, 700) == "exposed", "far -> exposed")
    check(c(500, 300, "2026-07-05") == "refuge_4", "refuge_4 present before removal")
    check(c(500, 300, "2026-07-08") == "exposed", "refuge_4 GONE after 07-07 -> exposed")


def test_state_sequence():
    print("[5] trunk_state_dwell_transitions (multi-site relocation)")
    base = pd.Timestamp("2026-06-30 06:00")
    rng = np.random.default_rng(11)
    rows = []
    for i in range(180):                        # house_1 -> refuge_1 -> water_1 (2 relocations)
        t = base + pd.Timedelta(minutes=4 * i)
        cx, cy = (100, 100) if i < 60 else (100, 300) if i < 120 else (300, 300)
        rows.append({"datetime": t + pd.Timedelta(hours=4), "x": cx + rng.normal(0, 3), "y": cy + rng.normal(0, 3)})
    dwell, relocs, segs = w.trunk_state_dwell_transitions(pd.DataFrame(rows), ROI_CFG, date="2026-06-30",
                                                          bin_s=300, min_dwell_bins=3, min_disp_in=24.0)
    states = [r["from_state"] for r in relocs] + ([relocs[-1]["to_state"]] if relocs else [])
    check(len(relocs) == 2, f"2 relocations recovered (got {len(relocs)})")
    check(states == ["house_1", "refuge_1", "water_1"], f"path house_1->refuge_1->water_1 (got {states})")
    check(set(dwell) >= {"house_1", "refuge_1", "water_1"}, "dwell covers all three states")


def test_temp_corr():
    print("[6] rat-centered within-rat correlation helper")
    rows = [{"shortid": t, "midday_peak_temp_c": tp, "trunk_frac_house2": base + (tp - 28) * 0.03}
            for t, base in [("A", 0.3), ("B", 0.6)] for tp in (22, 26, 30, 34)]
    rho, n = D._rat_centered_temp_corr(pd.DataFrame(rows))
    check(rho > 0.5 and n == 8, f"within-rat fraction rises with temp -> positive rho (got {rho:.2f})")


def main() -> int:
    for t in (test_emergence, test_sites_diff, test_changepoint, test_classify_state,
              test_state_sequence, test_temp_corr):
        t()
    print()
    if FAILS:
        print(f"FAIL - {len(FAILS)} check(s):")
        for f in FAILS:
            print("   - " + f)
        return 1
    print("PASS - biological-day sleep core healthy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
