"""Pick the second USV labelling round's windows (plan implementation_plan/2026-10-08-mic-imu-sync.md, Amendment 3
verdict): per mic, 8 night windows (20:00-05:59) and 4 day windows (09:00-16:59) of 5 min, each on a different date
(08-31 -> 09-10, night dates = the evening's date), random hour and start (whole 30 s), seed 12. Excluded:
- the round-1 hours (the windows of usv_strip_review_20261009_1757);
- battery-round gaps from the Phase-0 gap table (+-15 min);
- the logged acoustic field events (cohorts/2026c.yaml).
A window must lie inside one WAV whose name span covers it.

    python ephys/usv/usv_pick_windows.py --raw F:/3rd_rat --out <targets.csv>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mic_band_levels import NAME_RE, parse_name  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
ROUND1 = Path("D:/Field2026_analysis_out/2026c/usv_strip_review_20261009_1757/strips.json")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default="F:/3rd_rat")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=12)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    used = {(x["file"][:5], x["file"][6:16], x["file"][17:19]) for x in json.load(open(ROUND1))}
    g0 = json.load(open(REPO / "results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_phase0_2026c.json"))["run_dir"]
    gaps = pd.read_csv(Path(g0) / "gaps.csv", parse_dates=["gap_start", "gap_end"])
    gaps = gaps[gaps.cause.isin(["round_logged", "round_inferred"]) & (gaps.gap_min < 300)]
    bad = [(r.gap_start - pd.Timedelta(minutes=15), r.gap_end + pd.Timedelta(minutes=15)) for r in gaps.itertuples()]
    for e in yaml.safe_load(open(REPO / "cohorts/2026c.yaml", encoding="utf-8"))["field_events"]:
        if e.get("kind") == "acoustic":
            es = pd.Timestamp(str(e["start"]))
            ee = pd.Timestamp(str(e["end"])) if e.get("end") not in (None, "None") else es.normalize() + pd.Timedelta(days=1)
            bad.append((es, ee))
    rows = []
    for mic in ("MIC01", "MIC02"):
        files = []
        for d in sorted(Path(a.raw).glob("2026-*")):
            for f in (d / mic).glob(f"{mic}_*.wav"):
                if NAME_RE.search(f.name):
                    _, s, e = parse_name(f)
                    if e is not None and (e - s).total_seconds() >= 600:
                        files.append((f, s, e))
        dates = list(pd.date_range("2026-08-31", "2026-09-10"))
        for part, n_want, hours in (("night", 8, list(range(20, 24)) + list(range(0, 6))), ("day", 4, list(range(9, 17)))):
            order = rng.permutation(len(dates))
            got = 0
            for di in order:
                if got >= n_want:
                    break
                d = dates[di]
                for _ in range(20):                                  # tries for this date
                    h = int(rng.choice(hours))
                    day = d + pd.Timedelta(days=1) if (part == "night" and h < 12) else d
                    if (mic, f"{day:%Y-%m-%d}", f"{h:02d}") in used:
                        continue
                    t0 = day + pd.Timedelta(hours=h, seconds=30 * int(rng.integers(0, 110)))
                    t1 = t0 + pd.Timedelta(minutes=5)
                    if any(b0 < t1 and b1 > t0 for b0, b1 in bad):
                        continue
                    hit = [(f, s) for f, s, e in files if s <= t0 and t1 <= e]
                    if not hit:
                        continue
                    f, s = hit[0]
                    rows.append({"wav": str(f).replace("\\", "/"), "start_s": (t0 - s).total_seconds(), "dur_s": 300.0,
                                 "mic": mic, "part": part, "t_start": t0})
                    got += 1
                    break
            print(mic, part, got, "windows", flush=True)
    T = pd.DataFrame(rows).sort_values(["mic", "t_start"])
    T.to_csv(a.out, index=False)
    print(T.to_string(index=False))


if __name__ == "__main__":
    main()
