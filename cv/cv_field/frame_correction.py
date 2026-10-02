"""frame_correction.py — per-camera, per-time image correction (cohort px -> 09-18 calibration-epoch px) for the
whole-field cameras CH01-CH04, and the full pixel -> paddock chain. NIGHT first (user, 2026-10-02: the whole-field
cameras are used only at night, 21:00 -> 04:20).

Sources (the runs named by the canonical pointers in results/<cohort>/cv_field/reports/):
  CH01, CH02  landmark_night.py — dusk chain from the 09-18 labels, night frames tracked from the chained night reference;
              night_frames.csv (+ handoff.csv: the night's dawn closure and verdict). Pointer run_manifest_landmark_night_<c>.json.
  CH03, CH04  landmark_track.py --ref-labels <the user's 09-04 03:01 labels> --tie — tracked from the labelled night
              reference, tied to 09-18 by the two label sets (pole centre lines); track_frames.csv (+ tie.json).
              Pointer run_manifest_landmark_track_<tag>_<c>.json (default tag ch0304_ref0904night_hourly).
Table (one row per camera and sampled time): A = a11..a23, the affine 09-18 px -> frame px; B = b11..b23, its inverse
frame px -> 09-18 px (what a detection needs); source; status / held-out error of that sample; the night's quality
(CH01/CH02: dawn closure = median of the first three dawn frames and the verdict, pass <= 3 px; CH03/CH04: the tie's
held-out error); the night's rain (AWN console, 21:00 -> 04:20) and a flag:
  ok            sample fitted (status ok) and the night passes (CH01/CH02) / tie computed (CH03/CH04)
  sample        this sample's fit is unreliable (held-out above 3 / 6 px) — the lookup skips it if the night has others
  night         CH01/CH02 night failing the dawn-closure rule (closure > 3 px or a night frame unreliable)
Lookup: Corrections.correction(cam, t) -> (B, info) for any time inside a sampled night (a night = 12:00 -> 12:00, named
by its dusk date): the six parameters of A interpolated linearly between the two nearest usable samples of that night
(within-night changes are a few px), the nearest sample beyond them; (None, info) outside sampled nights.
Corrections.to_paddock(cam, t, uv, z_mm=60) -> paddock (x, y) through the 09-24 calibration (paddock_map.load()[cam]
.to_paddock), z = the assumed height of the point (60 mm ~ a rat's back, per the calibration README).
Pixels are full-resolution UPRIGHT pixels (CH01/CH02: the 7680 x 2160 frame rotated upright, as grab_frames.py returns).
Precision (user decisions 2026-10-02): CH01/CH02 <= 3 px on passing nights (< 1 cm); CH03/CH04 ~5-10 px (~1-2 cm).
The calibration's own error (76 mm median cross-camera, exploratory) is not reduced by this.

Usage: python cv/cv_field/frame_correction.py build --cohort 2026c [--night-run <dir>] [--track-run <dir>] [--weather-dir F:/weather_data]
       python cv/cv_field/frame_correction.py --selftest
       from frame_correction import Corrections; C = Corrections("2026c"); B, info = C.correction("CH01", t)
Output: results/<cohort>/cv_field/reports/cv_field_frame_corrections_<cohort>.csv + .md (coverage, flags, sources).
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

NIGHT_START, NIGHT_END = time(20, 30), time(5, 0)          # samples kept: the 21:00 -> 04:20 window with a margin
CLOSURE_MAX = 3.0
A_KEYS = ("a11", "a12", "a13", "a21", "a22", "a23")
B_KEYS = ("b11", "b12", "b13", "b21", "b22", "b23")
FMT = "%Y-%m-%d %H" + ":" + "%M" + ":" + "%S"


def night_of(t: datetime) -> date:
    """A night runs 12:00 -> 12:00 and is named by its dusk date."""
    return t.date() if t.hour >= 12 else t.date() - timedelta(days=1)


def in_night_window(t: datetime) -> bool:
    return t.time() >= NIGHT_START or t.time() <= NIGHT_END


def invert(A: np.ndarray) -> np.ndarray:
    return np.linalg.inv(np.vstack([A, [0, 0, 1.0]]))[:2]


def mat(row: dict, keys=A_KEYS) -> np.ndarray:
    return np.array([float(row[k]) for k in keys], float).reshape(2, 3)


def rain_by_night(weather_dir: str | None, nights: list[date]) -> dict:
    """mm of rain 21:00 -> 04:20 per night from the AWN console exports (5-min rows, field-PC local time); {} if absent."""
    if not weather_dir or not Path(weather_dir).exists():
        return {}
    bins = {}
    files = sorted(glob.glob(str(Path(weather_dir) / "AWN-*.csv"))) + sorted(glob.glob(str(Path(weather_dir) / "local" / "AWN-*.csv")))
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            rd = csv.reader(fh)
            hdr = next(rd, None)
            if not hdr:
                continue
            ix = {k: i for i, k in enumerate(hdr)}
            try:
                ct = next(i for k, i in ix.items() if k.startswith("Simple Date"))
                cr = next(i for k, i in ix.items() if k.startswith("Rain Rate"))
            except StopIteration:
                continue
            for r in rd:
                try:
                    t = datetime.strptime(r[ct][:19], FMT)
                    v = float(r[cr]) if r[cr] not in ("", "N/A") else np.nan
                except (ValueError, IndexError):
                    continue
                bins.setdefault(t.replace(second=0, minute=t.minute - t.minute % 5), []).append(v)
    out = {}
    for n in nights:
        a, b = datetime.combine(n, time(21, 0)), datetime.combine(n + timedelta(days=1), time(4, 20))
        v = [np.nanmean(x) for t, x in bins.items() if a <= t <= b]
        out[n] = float(np.nansum(v) * 5 / 60) if v else np.nan
    return out


def pointer(rep: Path, name: str) -> Path | None:
    p = rep / name
    return Path(json.loads(p.read_text(encoding="utf-8"))["run_dir"]) if p.exists() else None


def build(cohort: str, night_run: Path | None, track_run: Path | None, weather_dir: str | None) -> tuple[list[dict], dict]:
    rows, src = [], {}
    if night_run is not None:
        src["CH01/CH02 night chain"] = str(night_run)
        H = {(h["camera"], h["night"]): h for h in csv.DictReader(open(night_run / "handoff.csv", encoding="utf-8"))}
        for r in csv.DictReader(open(night_run / "night_frames.csv", encoding="utf-8")):
            if "a11" not in r or r["a11"] in ("", "nan"):
                continue
            h = H.get((r["camera"], r["night"]), {})
            cl = float(h["closure_med_next_px"]) if h.get("closure_med_next_px") not in (None, "") else np.nan
            rows.append({"camera": r["camera"], "night": r["night"], "time": r["frame_time"], "source": r.get("source", "night"),
                         "status": r["status"], "held_med_px": r["held_med_px"], "held_p90_px": r["held_p90_px"],
                         "night_quality": "dawn closure", "night_quality_px": cl, "night_verdict": h.get("verdict", ""),
                         **{k: r[k] for k in A_KEYS}})
    if track_run is not None:
        src["CH03/CH04 from the 09-04 03:01 labels"] = str(track_run)
        tie = json.loads((track_run / "tie.json").read_text(encoding="utf-8")) if (track_run / "tie.json").exists() else {}
        for r in csv.DictReader(open(track_run / "track_frames.csv", encoding="utf-8")):
            if r["frame"] == "REF" or "a11" not in r or r["a11"] in ("", "nan"):
                continue
            t = datetime.strptime(r["frame_time"], FMT)
            if not in_night_window(t):
                continue
            ti = tie.get(r["camera"], {})
            rows.append({"camera": r["camera"], "night": f"{night_of(t)}", "time": r["frame_time"], "source": "night_ref_labels",
                         "status": r["status"], "held_med_px": r["held_med_px"], "held_p90_px": r["held_p90_px"],
                         "night_quality": "tie to 09-18 (labels)", "night_quality_px": ti.get("held_med", np.nan),
                         "night_verdict": ti.get("status", ""), **{k: r[k] for k in A_KEYS}})
    rain = rain_by_night(weather_dir, sorted({date.fromisoformat(r["night"]) for r in rows}))
    for r in rows:
        A = mat(r)
        r.update({k: float(v) for k, v in zip(B_KEYS, invert(A).ravel())})
        r["rain_mm_night"] = rain.get(date.fromisoformat(r["night"]), np.nan)
        night_bad = r["night_quality"] == "dawn closure" and r["night_verdict"] != "PASS"
        r["flag"] = "sample" if r["status"] != "ok" else "night" if night_bad else "ok"
    rows.sort(key=lambda r: (r["camera"], r["time"]))
    return rows, src


class Corrections:
    """Lookup of the per-time correction table (default: the canonical CSV of the cohort)."""

    def __init__(self, cohort: str | None = None, table: str | Path | None = None):
        if table is None:
            import output_paths as op
            table = op.report_dir(op.resolve_cohort(cohort), "cv_field") / f"cv_field_frame_corrections_{op.resolve_cohort(cohort)}.csv"
        self.rows = list(csv.DictReader(open(table, encoding="utf-8")))
        for r in self.rows:
            r["_t"] = datetime.strptime(r["time"], FMT)
        self._cams = None

    def samples(self, cam: str, night: date) -> list[dict]:
        return sorted((r for r in self.rows if r["camera"] == cam and r["night"] == f"{night}"), key=lambda r: r["_t"])

    def correction(self, cam: str, t: datetime) -> tuple[np.ndarray | None, dict]:
        n = night_of(t)
        allr = self.samples(cam, n)
        use = [r for r in allr if r["flag"] != "sample"] or allr
        info = {"camera": cam, "night": f"{n}", "n_samples": len(use)}
        if not use:
            return None, {**info, "flag": "no samples for this night"}
        ts = [r["_t"] for r in use]
        if t <= ts[0] or len(use) == 1:
            A, used = mat(use[0]), [use[0]]
        elif t >= ts[-1]:
            A, used = mat(use[-1]), [use[-1]]
        else:
            i = max(k for k in range(len(ts)) if ts[k] <= t)
            w = (t - ts[i]).total_seconds() / max((ts[i + 1] - ts[i]).total_seconds(), 1e-9)
            A, used = (1 - w) * mat(use[i]) + w * mat(use[i + 1]), [use[i], use[i + 1]]
        flags = sorted({r["flag"] for r in used})
        return invert(A), {**info, "used": [r["time"] for r in used], "flag": "ok" if flags == ["ok"] else "+".join(flags),
                           "night_quality": used[0]["night_quality"], "night_quality_px": used[0]["night_quality_px"],
                           "rain_mm_night": used[0]["rain_mm_night"]}

    def to_09_18(self, cam: str, t: datetime, uv) -> tuple[np.ndarray | None, dict]:
        B, info = self.correction(cam, t)
        if B is None:
            return None, info
        P = np.asarray(uv, float).reshape(-1, 2)
        return P @ B[:, :2].T + B[:, 2], info

    def to_paddock(self, cam: str, t: datetime, uv, z_mm: float = 60.0, units: str = "in") -> tuple[np.ndarray | None, dict]:
        """Detection pixel(s) at field-PC time t -> paddock (x, y) via the 09-18-epoch pixel and the 09-24 calibration."""
        p18, info = self.to_09_18(cam, t, uv)
        if p18 is None:
            return None, info
        if self._cams is None:
            import landmark_guides
            sys.path.insert(0, str(landmark_guides.calib_dir()))
            import paddock_map as pm
            self._cams = pm.load()
        return self._cams[cam].to_paddock(p18, z_mm=z_mm, units=units), info


def write_outputs(rows: list[dict], src: dict, cohort: str) -> Path:
    import output_paths as op
    rep = op.report_dir(cohort, "cv_field")
    out = rep / f"cv_field_frame_corrections_{cohort}.csv"
    keys = ["camera", "night", "time", "source", "flag", "status", "held_med_px", "held_p90_px", "night_quality",
            "night_quality_px", "night_verdict", "rain_mm_night", *A_KEYS, *B_KEYS]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    f2 = lambda v: "-" if v in ("", None) or (isinstance(v, float) and not np.isfinite(v)) else f"{float(v):.2f}"  # noqa: E731
    L = [f"# Frame corrections, whole-field cameras, nights (cohort `{cohort}`)\n",
         f"Generated {datetime.now():%Y-%m-%d %H:%M} by `cv/cv_field/frame_correction.py build` (method, columns, flags and "
         "lookup in its docstring). Table: `cv_field_frame_corrections_" + cohort + ".csv` (A = 09-18 px -> frame px, B = "
         "frame px -> 09-18 px; full-resolution upright pixels). Use `Corrections(cohort).to_paddock(cam, t, uv, z_mm=60)`.\n",
         "Sources: " + "; ".join(f"{k}: `{v}`" for k, v in src.items()) + ".\n",
         "Precision (user, 2026-10-02): CH01/CH02 dawn closure <= 3 px on passing nights (< 1 cm); CH03/CH04 ~5-10 px "
         "(~1-2 cm). The 09-24 calibration's own error (76 mm median cross-camera) is separate and not reduced here.\n",
         "| camera | night | samples | ok / sample / night flags | held-out median px (median) | night quality px | verdict | rain mm (21:00-04:20) | shift range tx, ty px |",
         "|---|---|---|---|---|---|---|---|---|"]
    for cam in sorted({r["camera"] for r in rows}):
        for n in sorted({r["night"] for r in rows if r["camera"] == cam}):
            rs = [r for r in rows if r["camera"] == cam and r["night"] == n]
            tx = [float(r["a13"]) for r in rs]
            fl = {k: sum(r["flag"] == k for r in rs) for k in ("ok", "sample", "night")}
            L.append(f"| {cam} | {n} | {len(rs)} | {fl['ok']} / {fl['sample']} / {fl['night']} | "
                     f"{np.nanmedian([float(r['held_med_px']) for r in rs]):.2f} | {f2(rs[0]['night_quality_px'])} | "
                     f"{rs[0]['night_verdict'] or '-'} | {f2(rs[0]['rain_mm_night'])} | see CSV |")
    L.append("\nThe shift itself is in the CSV (a13 / a23 are the translation terms at the image origin; landmark_track.params "
             "gives tx, ty at the frame centre). Nights 09-12 -> 09-15 have no video.")
    md = rep / f"cv_field_frame_corrections_{cohort}.md"
    md.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out


def selftest() -> int:
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

    rec("night_of: 03:00 belongs to the previous dusk, 21:00 to its own",
        night_of(datetime(2026, 9, 4, 3)) == date(2026, 9, 3) and night_of(datetime(2026, 9, 3, 21)) == date(2026, 9, 3))
    A1 = np.array([[1.001, 0.002, 10.0], [-0.002, 0.999, -4.0]])
    A2 = np.array([[1.000, 0.004, 14.0], [-0.004, 1.000, -2.0]])
    with tempfile.TemporaryDirectory() as tmp:
        tab = Path(tmp) / "t.csv"
        keys = ["camera", "night", "time", "flag", "night_quality", "night_quality_px", "rain_mm_night", *A_KEYS]
        with open(tab, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for t, A, flag in (("2026-09-03 21:00:00", A1, "ok"), ("2026-09-04 01:00:00", A2, "ok"),
                               ("2026-09-04 03:00:00", A2 + 5.0, "sample")):
                w.writerow({"camera": "CH01", "night": "2026-09-03", "time": t, "flag": flag, "night_quality": "dawn closure",
                            "night_quality_px": 1.5, "rain_mm_night": 0.0, **dict(zip(A_KEYS, A.ravel()))})
        C = Corrections(table=tab)
        B, info = C.correction("CH01", datetime(2026, 9, 3, 23))
        Am = 0.5 * (A1 + A2)
        rec("interpolation half-way between two samples, inverse maps back",
            np.allclose(invert(Am), B) and np.allclose(np.vstack([B, [0, 0, 1]]) @ np.vstack([Am, [0, 0, 1]]), np.eye(3)))
        B2, info2 = C.correction("CH01", datetime(2026, 9, 4, 4))
        rec("unreliable sample skipped, nearest usable sample beyond the last", np.allclose(B2, invert(A2)) and info2["used"] == ["2026-09-04 01:00:00"])
        B3, info3 = C.correction("CH01", datetime(2026, 9, 5, 2))
        rec("no samples for another night -> None", B3 is None)
        p18, _ = C.to_09_18("CH01", datetime(2026, 9, 3, 21), [[100.0, 200.0]])
        rec("to_09_18 undoes A at a sample", np.allclose(p18[0] @ A1[:, :2].T + A1[:, 2], [100.0, 200.0]))
    print(("PASS" if ok else "FAIL") + " — frame_correction self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("cmd", nargs="?", choices=["build"])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--night-run", default=None, help="landmark_night run folder (default: the canonical pointer)")
    ap.add_argument("--track-run", default=None, help="landmark_track run folder for CH03/CH04 nights (default: the pointer)")
    ap.add_argument("--track-tag", default="ch0304_ref0904night_hourly")
    ap.add_argument("--weather-dir", default=r"F:\weather_data")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd != "build":
        ap.error("nothing to do (build or --selftest)")
    import output_paths as op
    cohort = op.resolve_cohort(args.cohort)
    rep = op.report_dir(cohort, "cv_field")
    night_run = Path(args.night_run) if args.night_run else pointer(rep, f"run_manifest_landmark_night_{cohort}.json")
    track_run = Path(args.track_run) if args.track_run else pointer(rep, f"run_manifest_landmark_track_{args.track_tag}_{cohort}.json")
    rows, src = build(cohort, night_run, track_run, args.weather_dir)
    out = write_outputs(rows, src, cohort)
    print(f"{len(rows)} samples -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
