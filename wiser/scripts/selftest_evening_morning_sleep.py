r"""
selftest_evening_morning_sleep.py — offline checks for the evening/morning sleep
split (no DB, no weather CSV). Exit code 0 = PASS, 1 = FAIL.

Covers:
  1. temperature_calibrated_sleep_end — a hotter night crosses theta* LATER (later
     sleep_end), a night that only cools after midnight gives sleep_end > 24 (NOT
     clamped to the calendar day), plus the auto-theta* path + clamp.
  2. window_sleep_site — centroid / nearest_shelter / in_shelter_frac on a known
     layout; a morning house flip is detected; relocation_tier flags it.
  3. nightly_activity_profile + sleep_emergence_from_profile — night-centered activity
     fraction (incl. past-midnight bins) and recovered emergence time.
  4. driver weather helpers — _overnight_rain_mm integral, _spearman monotonic.
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
import analyze_evening_morning_sleep as D     # noqa: E402

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


def _day_weather(date: str, peak: float, cool_per_h: float) -> pd.DataFrame:
    """Rise 12->15 to `peak`, then cool at `cool_per_h` C/h to 23:30 (30-min samples)."""
    rows = []
    for i in range(0, 24):                      # 12:00 .. 23:30
        t = pd.Timestamp(f"{date} 12:00") + pd.Timedelta(minutes=30 * i)
        h = t.hour + t.minute / 60.0
        temp = (peak - (15 - h)) if h < 15 else (peak - cool_per_h * (h - 15))
        rows.append({"datetime_local": t, "temp_c": temp, "rain_rate_mmhr": 0.0})
    return pd.DataFrame(rows)


def test_sleep_end():
    print("[1] temperature_calibrated_sleep_end")
    # cool day crosses 22.5 at 20:30; hot day crosses 22.5 at 22:30
    cool = _day_weather("2026-06-30", peak=25.0, cool_per_h=2.5 / 5.5)     # 25 -> 22.5 at 20.5h
    hot = _day_weather("2026-06-29", peak=30.0, cool_per_h=1.0)            # 30 -> 22.5 at 22.5h
    wx = pd.concat([hot, cool], ignore_index=True)
    days = ["2026-06-29", "2026-06-30"]
    ee, theta = w.temperature_calibrated_sleep_end(wx, days, threshold_c=22.5, ceil_h=30.0)
    em = dict(zip(ee["sleep_day"], ee["sleep_end_hour"]))
    check(abs(em["2026-06-30"] - 20.5) < 0.2, f"cool night end ~20.5 (got {em['2026-06-30']:.2f})")
    check(abs(em["2026-06-29"] - 22.5) < 0.2, f"hot night end ~22.5 (got {em['2026-06-29']:.2f})")
    check(em["2026-06-29"] > em["2026-06-30"], "hotter night emerges LATER (later sleep_end)")
    check(bool(ee["crossed"].all()), "both nights crossed theta* within the window")
    # PAST MIDNIGHT: a night that only cools to theta* after midnight -> sleep_end > 24 (not clamped to 24)
    rows = []
    for i in range(0, 30):                                   # 12:00 07-10 -> 03:00 07-11 @30min
        t = pd.Timestamp("2026-07-10 12:00") + pd.Timedelta(minutes=30 * i)
        h = (t - pd.Timestamp("2026-07-10")) / pd.Timedelta(hours=1)
        temp = (30 - (15 - h)) if h < 15 else (30 - 0.75 * (h - 15))   # crosses 22.5 at h=25 (01:00)
        rows.append({"datetime_local": t, "temp_c": temp, "rain_rate_mmhr": 0.0})
    een, _ = w.temperature_calibrated_sleep_end(pd.DataFrame(rows), ["2026-07-10"],
                                                threshold_c=22.5, ceil_h=30.0)
    seh = float(een.iloc[0]["sleep_end_hour"])
    check(seh > 24.0 and abs(seh - 25.0) < 0.4, f"hot night emerges PAST MIDNIGHT (sleep_end {seh:.1f} > 24)")
    # auto theta* path returns a finite level and clamps within [18,30]
    ee2, theta2 = w.temperature_calibrated_sleep_end(wx, days)
    check(np.isfinite(theta2), f"auto theta* finite (got {theta2:.2f})")
    check(bool(((ee2["sleep_end_hour"] >= 18.0) & (ee2["sleep_end_hour"] <= 30.0)).all()),
          "auto sleep_end clamped to [18,30]")
    # empty weather -> fixed ceiling fallback, no crash
    ee3, _ = w.temperature_calibrated_sleep_end(pd.DataFrame(), days, ceil_h=30.0)
    check(bool((ee3["sleep_end_hour"] == 30.0).all()), "no-weather fallback = ceil for every night")


def _fixes(night, sid, cx, cy, roi, n=40, jit=2.0):
    rng = np.random.default_rng(abs(hash((night, sid, roi))) % (2**32))
    return pd.DataFrame({
        "night": night, "shortid": sid,
        "x": cx + rng.normal(0, jit, n), "y": cy + rng.normal(0, jit, n),
        "resting": True, "roi": roi})


def test_window_sleep_site():
    print("[2] window_sleep_site + relocation flag")
    roi_cfg = {"rois": [{"name": "house_1", "x": 100.0, "y": 100.0},
                        {"name": "house_2", "x": 300.0, "y": 100.0}]}
    # evening baseline at house_1; morning flips to house_2 on the wet day
    ev = _fixes("2026-06-30", "A", 100, 100, "house_1")
    mo = _fixes("2026-06-30", "A", 300, 100, "house_2")
    es = w.window_sleep_site(ev, roi_cfg, window_label="evening")
    ms = w.window_sleep_site(mo, roi_cfg, window_label="morning")
    r_e = es.iloc[0]; r_m = ms.iloc[0]
    check(abs(r_e["centroid_x"] - 100) < 5 and abs(r_e["centroid_y"] - 100) < 5, "evening centroid ~house_1")
    check(r_e["nearest_shelter"] == "house_1", "evening nearest_shelter = house_1")
    check(abs(r_e["in_shelter_frac"] - 1.0) < 1e-9, "evening in_shelter_frac = 1.0")
    check(r_m["nearest_shelter"] == "house_2", "morning nearest_shelter = house_2 (flipped)")
    # displacement + tier
    d = float(np.hypot(r_m["centroid_x"] - r_e["centroid_x"], r_m["centroid_y"] - r_e["centroid_y"]))
    check(d > 150, f"morning move from baseline large (~200 in; got {d:.0f})")
    check(w.relocation_tier(d, True) == "major_shelter_switch", "big switch -> major_shelter_switch")
    check(w.relocation_tier(5.0, False) == "stable", "5-in wiggle -> stable")
    # empty slice -> empty framed result, no crash
    check(w.window_sleep_site(ev.iloc[0:0], roi_cfg, window_label="evening").empty, "empty slice -> empty")


def test_activity_profile():
    print("[3] nightly_activity_profile + sleep_emergence_from_profile")
    rows = []
    for i in range(0, 240):                                 # 12:00 06-29 -> ~08:00 06-30 @5min
        loc = pd.Timestamp("2026-06-29 12:00") + pd.Timedelta(minutes=5 * i)
        utc = loc + pd.Timedelta(hours=4)                   # LOCAL = UTC-4
        active = (loc.hour >= 21) or (loc.hour < 3)         # active night 21:00 -> 03:00
        rows.append({"datetime": utc, "speed_inps_smooth": 5.0 if active else 0.1})
    df = pd.DataFrame(rows)
    prof = w.nightly_activity_profile(df, moving_thr_inps=1.0, bin_s=300, anchor_hour=12)
    check(set(prof["sleep_day"].unique()) == {"2026-06-29"}, "all fixes assigned to sleep_day 06-29")
    hi = prof[(prof["bin_hours"] >= 21) & (prof["bin_hours"] < 25)]   # 21:00 -> 01:00 (past midnight)
    check(bool((hi["active_frac"] > 0.9).all()) and not hi.empty,
          "active fraction high across the emergence window (incl. past midnight, bin_hours>24)")
    lo = prof[(prof["bin_hours"] >= 13) & (prof["bin_hours"] < 20)]   # afternoon rest
    check(bool((lo["active_frac"] < 0.1).all()), "afternoon rest fraction low")
    em = w.sleep_emergence_from_profile(prof, frac_thr=0.5, sustain_bins=2, search_from_h=15)
    emh = float(em.iloc[0]["emergence_hour"])
    check(20.9 < emh < 21.2, f"behavioral emergence recovered ~21:00 (got {emh:.2f})")


def test_weather_helpers():
    print("[4] driver weather helpers")
    rows = []
    for i in range(0, 30):                                  # prev 21:00 -> next 11:30 @30min
        t = pd.Timestamp("2026-06-29 21:00") + pd.Timedelta(minutes=30 * i)
        rows.append({"datetime_local": t, "rain_rate_mmhr": 2.0, "temp_c": 20.0})
    wx = pd.DataFrame(rows)
    mm = D._overnight_rain_mm(wx, "2026-06-30")             # ~2 mm/h over ~14 h
    check(25 < mm < 30, f"overnight rain integral ~28 mm (got {mm:.1f})")
    rho, n = D._spearman([1, 2, 3, 4, 5], [2, 4, 5, 9, 11])
    check(abs(rho - 1.0) < 1e-9 and n == 5, f"spearman monotonic = 1.0 (got {rho:.3f}, n={n})")
    rho2, n2 = D._spearman([1, 2], [1, 2])
    check(np.isnan(rho2), "spearman n<4 -> NaN")


def main() -> int:
    for t in (test_sleep_end, test_window_sleep_site, test_activity_profile, test_weather_helpers):
        t()
    print()
    if FAILS:
        print(f"FAIL — {len(FAILS)} check(s) failed:")
        for f in FAILS:
            print("   - " + f)
        return 1
    print("PASS — evening/morning sleep split healthy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
