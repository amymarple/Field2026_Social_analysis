r"""selftest_night_consolidated_rest.py — offline planted checks for the stay-point consolidated-rest
detector (`_stay_bouts`) + the night-weather summariser. No DB. PASS/FAIL exit code."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_night_consolidated_rest as A   # noqa: E402

FAILS: list[str] = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILS.append(name)


def mk(coords, rest):
    n = len(coords)
    rests = rest if isinstance(rest, list) else [rest] * n
    return pd.DataFrame({"bin_utc": [i * 300_000_000_000 for i in range(n)],
                         "cx": [c[0] for c in coords], "cy": [c[1] for c in coords],
                         "rest": rests, "lh": [22 + i * (5 / 60) for i in range(n)]})


def main():
    print("=== selftest: night consolidated rest (stay-point) ===")
    print(f"  params: R_STOP={A.R_STOP_IN} in, EXIT_TOL={A.EXIT_TOL_BINS} bins, REST_MIN={A.REST_MIN}")

    # A: clustered + resting for 8 bins (40 min) -> ONE bout, tight radius
    a = A._stay_bouts(mk([(100, 100)] * 8, 0.9), min_bins=6)
    check("A clustered-rest 40 min -> 1 bout", len(a) == 1 and a[0]["n_bins"] == 8 and a[0]["radius_in"] < 5)

    # B: wanderer (each bin > R away) -> NO bout
    b = A._stay_bouts(mk([(100 + 60 * i, 100) for i in range(8)], 0.9), min_bins=6)
    check("B wanderer -> 0 bouts", len(b) == 0)

    # C: clustered but ACTIVE (rest < REST_MIN) -> NO bout (rest gate)
    c = A._stay_bouts(mk([(100, 100)] * 8, 0.3), min_bins=6)
    check("C clustered-but-active -> 0 bouts", len(c) == 0)

    # D: hysteresis — a single out-of-cluster blip (<= EXIT_TOL) is spanned, one merged bout
    d = A._stay_bouts(mk([(100, 100)] * 3 + [(600, 600)] + [(100, 100)] * 4, 0.9), min_bins=6)
    check("D 1-bin blip merged -> 1 bout of 8 bins", len(d) == 1 and d[0]["n_bins"] == 8)

    # D2: a LONG excursion (> EXIT_TOL) breaks the bout -> two short segs, neither >= 6 -> 0
    d2 = A._stay_bouts(mk([(100, 100)] * 3 + [(600, 600)] * 4 + [(100, 100)] * 3, 0.9), min_bins=6)
    check("D2 long excursion breaks bout -> 0 bouts", len(d2) == 0)

    # E: too short (< min_bins) -> NO bout
    e = A._stay_bouts(mk([(100, 100)] * 4, 0.9), min_bins=6)
    check("E short sit (4<6 bins) -> 0 bouts", len(e) == 0)

    # night-weather summariser: temp/humidity means + wet flag + within-night coldest hour
    idx = pd.date_range("2026-06-30T21:00:00", "2026-07-01T04:55:00", freq="5min")
    wx = pd.DataFrame({"datetime_local": idx, "temp_c": np.linspace(28, 20, len(idx)),
                       "humidity": np.linspace(60, 95, len(idx)),
                       "rain_rate_mmhr": [0.0] * (len(idx) - 3) + [1.5, 0.0, 0.0]})
    nw = A._night_weather(wx)
    check("night-weather one night, wet flag set (rain>0.2)", len(nw) == 1 and bool(nw.iloc[0]["wet"]))
    check("night-weather coldest hour is pre-dawn (temp falls overnight)", 3.0 <= nw.iloc[0]["cold_hour"] <= 5.0)

    print(f"\n{'PASS' if not FAILS else 'FAIL'} - {len(FAILS)} failure(s)"
          + (": " + "; ".join(FAILS) if FAILS else ""))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
