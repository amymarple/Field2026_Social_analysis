"""Recording coverage from the session index: per-hour table, per-second coverage per day, and a raster figure.

Inputs: results/<cohort>/ephys_spikes/reports/ephys_spikes_session_index_<cohort>.csv (start_local, duration_s, firmware).
Coverage is defined on the logger wallclock (RTC start + sample count / fs); a session covers [start, start + duration).
Sessions carrying a `field_flag` in the index (zombie restarts, test recordings from another PC - cohorts/<key>.yaml
ephys.field_flags) are NOT counted; they are listed in the hourly md header instead.

Outputs (results/<cohort>/ephys_spikes/reports and figures; mirrored under <analysis_root>/index/ when declared):
  ephys_spikes_hourly_coverage_<cohort>.csv / .md   minutes recorded per local hour per logger, every day in range
  ephys_spikes_coverage_1s_<cohort>_<date>.csv       one row per local second of that day: time_local, one column per
                                                    logger (firmware version while recording, 0 = not recording), n_loggers
  ephys_spikes_coverage_raster_<cohort>.png          loggers x time raster, one panel per day (FM64 vs FM65 coloured)

Usage: python ephys/coverage_tables.py --cohort 2026c [--days 2026-09-01 2026-09-02 ...] [--no-1s]
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from _common import analysis_root, figure_dir, git_commit, report_dir, utc_now_iso


def load_sessions(cohort: str) -> tuple[list[dict], list[dict], list[dict]]:
    """(counted sessions, field-flagged sessions left out of the coverage, sessions truncated at their `valid_until`).
    A `valid_until` (index column from cohorts/<key>.yaml ephys.valid_until) clips the counted span: the recording continued
    after the neural signal ended (implant detached mid-session); `duration_s` becomes the valid span, `tail_s` the rest."""
    p = report_dir(cohort) / f"ephys_spikes_session_index_{cohort}.csv"
    rows, flagged, truncated = [], [], []
    for r in csv.DictReader(open(p, encoding="utf-8")):
        if not r.get("start_local") or not r.get("duration_s"):
            continue
        a = r["animal"].upper()
        a = f"SF{int(a[2:]):02d}" if a.startswith("SF") and a[2:].isdigit() else a
        s = datetime.strptime(r["start_local"][:19], "%Y-%m-%d %H:%M:%S")
        row = {"animal": a, "session": r["session"], "start": s, "end": s + timedelta(seconds=float(r["duration_s"])),
               "firmware": int(r["firmware"]) if r.get("firmware") else 0, "duration_s": float(r["duration_s"]),
               "field_flag": (r.get("field_flag") or "").strip(), "tail_s": 0.0}
        vu = (r.get("valid_until") or "").strip()
        if vu and not row["field_flag"]:
            v = datetime.strptime(vu[:19], "%Y-%m-%d %H:%M:%S")
            if s < v < row["end"]:
                row["tail_s"] = (row["end"] - v).total_seconds()
                row["end"] = v
                row["duration_s"] = (v - s).total_seconds()
                truncated.append(row)
        (flagged if row["field_flag"] else rows).append(row)
    return rows, flagged, truncated


def per_second(rows: list[dict], animals: list[str], day: datetime) -> np.ndarray:
    """(86400, n_animals) int16 array of firmware version while recording (0 = none) for local day `day`."""
    out = np.zeros((86400, len(animals)), dtype=np.int16)
    d0 = day
    d1 = day + timedelta(days=1)
    for r in rows:
        if r["end"] <= d0 or r["start"] >= d1:
            continue
        i0 = int(max(0.0, (r["start"] - d0).total_seconds()))
        i1 = int(min(86400.0, np.ceil((r["end"] - d0).total_seconds())))
        out[i0:i1, animals.index(r["animal"])] = r["firmware"] or 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--days", nargs="*", default=None, help="YYYY-MM-DD ... (default: every day touched by a session)")
    ap.add_argument("--no-1s", action="store_true")
    a = ap.parse_args()
    rows, flagged, truncated = load_sessions(a.cohort)
    animals = sorted({r["animal"] for r in rows})
    if a.days:
        days = [datetime.strptime(d, "%Y-%m-%d") for d in a.days]
    else:
        d0 = min(r["start"] for r in rows).replace(hour=0, minute=0, second=0, microsecond=0)
        d1 = max(r["end"] for r in rows).replace(hour=0, minute=0, second=0, microsecond=0)
        days = [d0 + timedelta(days=k) for k in range((d1 - d0).days + 1)]
    rd = report_dir(a.cohort)
    fd = figure_dir(a.cohort)
    ar = analysis_root(a.cohort)
    mirror = (ar / "index") if ar else None
    if mirror:
        mirror.mkdir(parents=True, exist_ok=True)

    # ---- hourly table ----
    hourly_csv = rd / f"ephys_spikes_hourly_coverage_{a.cohort}.csv"
    hourly_md = rd / f"ephys_spikes_hourly_coverage_{a.cohort}.md"
    L = [f"# Hourly recording coverage, cohort `{a.cohort}`\n",
         f"Generated {utc_now_iso()} by `ephys/coverage_tables.py` (git {git_commit()}) from the session index. Minutes recorded per local hour per logger "
         "(60 = full hour, `-` = none, `*` = FM65). Coverage = logger wallclock (RTC start + samples/fs). A logger absent for a whole day may simply not be offloaded yet.\n"]
    if flagged:
        L.append(f"**{len(flagged)} field-flagged session(s), {sum(r['duration_s'] for r in flagged) / 3600:.2f} h, are NOT counted** "
                 "(`field_flag` in the session index; cohorts/<key>.yaml `ephys.field_flags`):")
        L += [f"- {r['animal']} `{r['session']}` {r['start']:%Y-%m-%d %H:%M} ({r['duration_s'] / 60:.1f} min): {r['field_flag']}" for r in flagged]
        L.append("")
    if truncated:
        L.append(f"**{len(truncated)} session(s) counted only up to their `valid_until`** (cohorts/<key>.yaml `ephys.valid_until`: the neural "
                 "signal ended before the Stop; the open-circuit tail is not coverage):")
        L += [f"- {r['animal']} `{r['session']}` {r['start']:%Y-%m-%d %H:%M} -> valid until {r['end']:%Y-%m-%d %H:%M:%S} "
              f"({r['duration_s'] / 3600:.2f} h counted, {r['tail_s'] / 3600:.2f} h tail not counted)" for r in truncated]
        L.append("")
    per_day_arrays = {}
    with open(hourly_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "hour_local"] + [f"{x}_min" for x in animals] + ["loggers_with_data", "logger_hours"])
        for day in days:
            arr = per_second(rows, animals, day)
            per_day_arrays[day] = arr
            L.append(f"## {day:%Y-%m-%d}\n")
            L.append("| hour | " + " | ".join(animals) + " | loggers |")
            L.append("|---|" + "---|" * len(animals) + "---|")
            day_total = 0.0
            for h in range(24):
                seg = arr[h * 3600:(h + 1) * 3600]
                mins = (seg > 0).sum(axis=0) / 60.0
                n = int((mins > 0).sum())
                day_total += mins.sum() / 60.0
                w.writerow([day.strftime("%Y-%m-%d"), h] + [round(float(m), 1) for m in mins] + [n, round(float(mins.sum() / 60.0), 2)])
                cells = []
                for j, m in enumerate(mins):
                    if m <= 0:
                        cells.append("-")
                    else:
                        fw = int(np.max(seg[:, j]))
                        cells.append(f"{m:.0f}{'*' if fw >= 65 else ''}")
                L.append(f"| {h:02d} | " + " | ".join(cells) + f" | {n} |")
            per_logger = ", ".join(f"{x} {(arr[:, j] > 0).sum() / 3600:.1f} h" for j, x in enumerate(animals))
            L.append(f"\nDay total {day_total:.1f} logger-hours; {per_logger}.\n")
    hourly_md.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"hourly -> {hourly_csv}\n          {hourly_md}")

    # ---- per-second coverage per day ----
    if not a.no_1s:
        for day, arr in per_day_arrays.items():
            if not (arr > 0).any():
                continue
            p = rd / f"ephys_spikes_coverage_1s_{a.cohort}_{day:%Y-%m-%d}.csv"
            with open(p, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["time_local"] + [f"{x}_fw" for x in animals] + ["n_loggers"])
                n_log = (arr > 0).sum(axis=1)
                for i in range(86400):
                    w.writerow([f"{day:%Y-%m-%d} {i // 3600:02d}:{(i // 60) % 60:02d}:{i % 60:02d}"] + [int(v) for v in arr[i]] + [int(n_log[i])])
            print(f"1-s coverage -> {p}")
            if mirror:
                (mirror / p.name).write_bytes(p.read_bytes())

    # ---- raster figure ----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import ListedColormap
        n_days = len([d for d in per_day_arrays if (per_day_arrays[d] > 0).any()])
        fig, axes = plt.subplots(max(1, n_days), 1, figsize=(14, 1.2 + 1.6 * max(1, n_days)), squeeze=False)
        cmap = ListedColormap(["white", "#d62728", "#ff7f0e", "#1f77b4"])   # none, FM62, FM64, FM65
        k = 0
        for day, arr in per_day_arrays.items():
            if not (arr > 0).any():
                continue
            ax = axes[k, 0]
            cls = np.zeros_like(arr)
            cls[arr == 62] = 1
            cls[arr == 64] = 2
            cls[arr >= 65] = 3
            ax.imshow(cls.T[:, ::60], aspect="auto", cmap=cmap, vmin=0, vmax=3, interpolation="nearest", extent=[0, 24, len(animals) - 0.5, -0.5])
            ax.set_yticks(range(len(animals)))
            ax.set_yticklabels(animals)
            ax.set_xticks(range(0, 25, 2))
            ax.set_xlim(0, 24)
            ax.set_title(f"{day:%Y-%m-%d}  (red FM62, orange FM64, blue FM65; white = no data on E:)", fontsize=10, loc="left")
            ax.set_xlabel("local hour")
            k += 1
        fig.suptitle(f"Recording coverage per logger, cohort {a.cohort}", fontsize=12)
        fig.tight_layout()
        fp = fd / f"ephys_spikes_coverage_raster_{a.cohort}.png"
        fig.savefig(fp, dpi=130)
        plt.close(fig)
        print(f"raster -> {fp}")
        if mirror:
            (mirror / fp.name).write_bytes(fp.read_bytes())
    except Exception as e:
        print(f"raster skipped: {e}")
    if mirror:
        for p in (hourly_csv, hourly_md):
            (mirror / p.name).write_bytes(p.read_bytes())
        print(f"mirrored to {mirror}")


if __name__ == "__main__":
    main()
