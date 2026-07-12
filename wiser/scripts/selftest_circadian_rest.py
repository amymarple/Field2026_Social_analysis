"""
selftest_circadian_rest.py — offline check of circadian_rest_profile.

No DB. Builds synthetic fixes for 3 tags × 2 days at 1 fix/min: two tags REST during
local 08:00-16:00 and MOVE otherwise; a third rests only half the daytime samples.
Verifies:
  * a daytime hour reads rest_frac ~1 (full resters) and the half-rester ~0.5;
  * a night hour reads rest_frac ~0;
  * group mean/SEM across tags is correct at a daytime hour;
  * cover_frac is in [0,1] and ~1 with full 1-min sampling;
  * NaN smoothed speed counts as NOT resting.

Run:  python scripts/selftest_circadian_rest.py     (-> PASS/FAIL, exit code)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import wiser_analysis_utils as w   # noqa: E402

THR = 12.46          # rest threshold (in/s)
REST_SP, MOVE_SP = 1.0, 30.0
OFF = w.LOCAL_TZ_OFFSET_HOURS      # -4 (local = UTC + OFF); so UTC = local - OFF


def _mk(tag, day, rest_frac_day):
    """1 fix/min for 24 h; local 08:00-16:00 is the 'rest' block (fraction rest_frac_day)."""
    rows = []
    base_utc = pd.Timestamp(day) - pd.Timedelta(hours=OFF)   # local 00:00 -> UTC
    for minute in range(24 * 60):
        t_utc = base_utc + pd.Timedelta(minutes=minute)
        local_h = (t_utc + pd.Timedelta(hours=OFF)).hour
        if 8 <= local_h < 16:
            # full rester -> always rest; half rester -> rest on even minutes (0.5/hour)
            rest = True if rest_frac_day >= 0.999 else (minute % 2 == 0)
            sp = REST_SP if rest else MOVE_SP
        else:
            sp = MOVE_SP
        rows.append({"shortid": tag, "datetime": t_utc, "speed_inps_smooth": sp, "valid": True})
    return rows


def main() -> int:
    ok = True
    rows = []
    for day in ("2026-06-29", "2026-06-30"):
        rows += _mk("A", day, 1.0)
        rows += _mk("B", day, 1.0)
        rows += _mk("C", day, 0.5)
    df = pd.DataFrame(rows)
    # inject a NaN speed on tag A (should count as NOT resting)
    df.loc[0, "speed_inps_smooth"] = np.nan

    per_tag, grp = w.circadian_rest_profile(df, rest_thr_inps=THR)
    g = grp.set_index("clock_hour")
    pt = per_tag.set_index(["shortid", "clock_hour"])

    # daytime hour 10: A,B ~1.0 ; C ~0.5
    a10 = pt.loc[("A", 10), "rest_frac"]; c10 = pt.loc[("C", 10), "rest_frac"]
    if not (a10 > 0.95 and abs(c10 - 0.5) < 0.1):
        print(f"  FAIL daytime rest_frac: A={a10:.2f} (exp ~1), C={c10:.2f} (exp ~0.5)"); ok = False
    else:
        print(f"[daytime] A rest_frac={a10:.2f}, C={c10:.2f}: ok")

    # night hour 2: ~0
    a2 = pt.loc[("A", 2), "rest_frac"]
    if a2 > 0.05:
        print(f"  FAIL night rest_frac A@02:00={a2:.2f} (exp ~0)"); ok = False
    else:
        print(f"[night] A rest_frac@02:00={a2:.2f}: ok")

    # group mean/SEM at hour 10: mean of (1,1,0.5)=0.833, SEM>0
    m10, sem10 = g.loc[10, "rest_frac_mean"], g.loc[10, "rest_frac_sem"]
    if not (abs(m10 - 0.8333) < 0.03 and sem10 > 0):
        print(f"  FAIL group@10: mean={m10:.3f} (exp ~0.833), sem={sem10:.3f} (>0)"); ok = False
    else:
        print(f"[group] hour10 mean={m10:.3f} ± {sem10:.3f}: ok")

    # coverage in [0,1] and ~1
    if not per_tag["cover_frac"].between(0, 1).all():
        print("  FAIL cover_frac out of [0,1]"); ok = False
    elif abs(pt.loc[("A", 10), "cover_frac"] - 1.0) > 0.02:
        print(f"  FAIL cover_frac A@10={pt.loc[('A',10),'cover_frac']:.3f} (exp ~1)"); ok = False
    else:
        print("[coverage] in [0,1], full sampling ~1.0: ok")

    # --- day-resolved: circadian_rest_by_night ---
    per_cell = w.circadian_rest_by_night(df, rest_thr_inps=THR)
    pc = per_cell.set_index(["shortid", "night", "clock_hour"])
    nights_seen = sorted(per_cell["night"].unique())
    a29_10 = pc.loc[("A", "2026-06-29", 10), "rest_frac"]
    a29_2 = pc.loc[("A", "2026-06-29", 2), "rest_frac"]
    cov29_10 = pc.loc[("A", "2026-06-29", 10), "cover_frac"]
    if nights_seen != ["2026-06-29", "2026-06-30"]:
        print(f"  FAIL by_night dates: {nights_seen}"); ok = False
    elif not (a29_10 > 0.95 and a29_2 < 0.05 and abs(cov29_10 - 1.0) < 0.02):
        print(f"  FAIL by_night A/06-29: h10={a29_10:.2f} (exp ~1), h2={a29_2:.2f} "
              f"(exp ~0), cover={cov29_10:.2f} (exp ~1)"); ok = False
    else:
        print("[by_night] per-date rest_frac (day~1, night~0) + coverage: ok")

    # --- anchor_hour (biological-night) shift: a local-02:00 fix belongs to the PREVIOUS
    #     biological night when the night is anchored after 02:00 ---
    one = pd.DataFrame([{"shortid": "Z", "datetime": pd.Timestamp("2026-06-30 06:00"),  # local 02:00
                         "speed_inps_smooth": 1.0, "valid": True}])
    c0 = w.circadian_rest_by_night(one, rest_thr_inps=THR, anchor_hour=0)
    c5 = w.circadian_rest_by_night(one, rest_thr_inps=THR, anchor_hour=5)
    if c0.iloc[0]["night"] != "2026-06-30" or c5.iloc[0]["night"] != "2026-06-29":
        print(f"  FAIL anchor shift: cal={c0.iloc[0]['night']} (exp 06-30), "
              f"bio={c5.iloc[0]['night']} (exp 06-29)"); ok = False
    else:
        print("[anchor_hour] local 02:00 -> calendar 06-30, bio(anchor 5) 06-29: ok")

    print("\nSELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
