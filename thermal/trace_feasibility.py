"""thermal/trace_feasibility.py — Phase 0 feasibility probe for RAT THERMAL TRACES (heat-ghosts / deposits).

Question this answers BEFORE any detector is built: when a rat rests at a spot and then leaves, does a WARM
residual (a "heat ghost" — warmed ground, or a urine/scent deposit) remain VISIBLE in the AGC thermal video,
and for how long does it persist and decay? If yes -> GO (and it hands the detector calibrated time-constants);
if the warmth vanishes the instant the rat leaves -> NO-GO (a valid, reportable negative result).

Method (auto-anchored — no georeference or hand-picked pixels needed):
  1. Run the existing moving-rat detector (thermal/detect_blobs.py) over an hour -> per-frame blob positions.
  2. Derive "rest-then-depart" EVENTS: a location where a rat blob dwelled >= dwell_min frames, then the spot
     went rat-free for >= gap frames (the moment a ghost would be "planted"). Also accepts manual ROIs.
  3. At each event's fixed pixel ROI, measure ANNULUS-REFERENCED contrast over time: median(warm disk) -
     median(surrounding annulus), on the AGC-undone (robust_norm) frame, excluding OSD + the roaming red
     spot-meter crosshair per frame. The annulus cancels AGC whole-frame flicker (disk+annulus move together).
  4. Fit post-departure c(t) = c0*exp(-(t-t0)/tau) + b. A genuine trace: step UP on arrival, stays elevated
     AFTER departure, then DECAYS (finite tau). A constant warm structure the rat sat by: flat, no decay.
  5. Classify each event (ghost / no_ghost / persistent_no_decay / ambiguous) and emit an overall GO/NO-GO
     plus the calibrated constants (baseline window, min-persist, onset threshold) for the Phase 1 detector.

EVERYTHING here is RELATIVE brightness, NOT temperature (AGC, not radiometric); times are frame index +
filename wallclock (the OSD clock runs ~1 h behind); thermal is NOT georeferenced. Read-only: writes only --out.

Usage:
  python thermal/trace_feasibility.py --cam 108_thermal --date 2026-07-01 --hour 21 --out D:/tmp/trace_feas
  python thermal/trace_feasibility.py --video <mp4> --detections <detect_blobs detections.csv> --out <dir>
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import detect_blobs as db  # noqa: E402

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


# --------------------------------------------------------------------------------------
# Event derivation from rat detections
# --------------------------------------------------------------------------------------
def _presence_runs(present: np.ndarray, merge_gap: int) -> list[tuple[int, int]]:
    """Maximal runs of True in `present`, bridging gaps <= merge_gap. Returns [(start, end_inclusive)]."""
    runs, i, n = [], 0, len(present)
    while i < n:
        if not present[i]:
            i += 1
            continue
        j = i
        gap = 0
        last = i
        while j < n and (present[j] or gap < merge_gap):
            if present[j]:
                last = j
                gap = 0
            else:
                gap += 1
            j += 1
        runs.append((i, last))
        i = last + 1
    return runs


def derive_events(dets: list[tuple[int, float, float]], nframes: int, *, bin_px=30, site_radius=25.0,
                  dwell_min=8, merge_gap=3, gap=15) -> list[dict]:
    """From (frame, cx, cy) detections, find rest-then-depart events: a rat dwelled at a site then left it."""
    if not dets:
        return []
    # cluster detection positions into sites on a coarse grid, then refine the site to the mean position
    bins: dict[tuple[int, int], list[tuple[int, float, float]]] = {}
    for fr, cx, cy in dets:
        bins.setdefault((int(cx // bin_px), int(cy // bin_px)), []).append((fr, cx, cy))
    events = []
    for _, members in bins.items():
        if len(members) < dwell_min:
            continue
        sx = float(np.mean([m[1] for m in members]))
        sy = float(np.mean([m[2] for m in members]))
        # presence at this site across the whole hour (any detection within site_radius)
        present = np.zeros(nframes, bool)
        for fr, cx, cy in dets:
            if (cx - sx) ** 2 + (cy - sy) ** 2 <= site_radius ** 2 and 0 <= fr < nframes:
                present[fr] = True
        runs = [r for r in _presence_runs(present, merge_gap) if r[1] - r[0] + 1 >= dwell_min]
        if not runs:
            continue
        rest_start, depart = max(runs, key=lambda r: r[1] - r[0])  # longest dwell
        # require the site to go rat-free right after departure (else the rat lingered — not a clean depart)
        free_end = min(nframes, depart + 1 + gap)
        if present[depart + 1:free_end].any():
            continue
        events.append(dict(cx=sx, cy=sy, rest_start=int(rest_start), depart=int(depart),
                           dwell_len=int(depart - rest_start + 1)))
    events.sort(key=lambda e: -e["dwell_len"])
    return events


# --------------------------------------------------------------------------------------
# Annulus-referenced contrast (AGC-flicker-cancelling), with OSD + crosshair exclusion
# --------------------------------------------------------------------------------------
def _ring_indices(cx: float, cy: float, r_disk: int, r_in: int, r_out: int, h: int, w: int):
    x0, x1 = max(0, int(cx - r_out)), min(w, int(cx + r_out) + 1)
    y0, y1 = max(0, int(cy - r_out)), min(h, int(cy + r_out) + 1)
    ys, xs = np.mgrid[y0:y1, x0:x1]
    d2 = (xs - cx) ** 2 + (ys - cy) ** 2
    disk = d2 <= r_disk ** 2
    ann = (d2 >= r_in ** 2) & (d2 <= r_out ** 2)
    return (ys[disk], xs[disk]), (ys[ann], xs[ann])


def contrast_at(norm: np.ndarray, invalid: np.ndarray, disk_idx, ann_idx, min_px=20) -> float:
    dy, dx = disk_idx
    ay, ax = ann_idx
    dv = norm[dy, dx][~invalid[dy, dx]]
    av = norm[ay, ax][~invalid[ay, ax]]
    if dv.size < min_px or av.size < min_px:
        return float("nan")
    return float(np.median(dv) - np.median(av))


# --------------------------------------------------------------------------------------
# Decay fit + per-event classification
# --------------------------------------------------------------------------------------
def _fit_decay(t: np.ndarray, c: np.ndarray, b: float):
    """Fit c(t) = c0*exp(-t/tau) + b (t = frames since departure). Returns (tau, r2, c0) or (nan,nan,nan)."""
    ok = np.isfinite(c)
    t, c = t[ok], c[ok]
    if t.size < 4:
        return float("nan"), float("nan"), float("nan")
    try:
        from scipy.optimize import curve_fit
        f = lambda tt, c0, tau: c0 * np.exp(-tt / np.maximum(tau, 1e-3)) + b
        p0 = [max(c[0] - b, 1.0), 30.0]
        popt, _ = curve_fit(f, t, c, p0=p0, bounds=([0, 1.0], [np.inf, 7200.0]), maxfev=5000)
        resid = c - f(t, *popt)
        ss = float(np.sum((c - np.mean(c)) ** 2))
        r2 = 1.0 - float(np.sum(resid ** 2)) / ss if ss > 0 else 0.0
        return float(popt[1]), float(r2), float(popt[0])
    except Exception:
        # log-linear fallback on (c - b)
        y = c - b
        m = y > 1e-6
        if m.sum() < 4:
            return float("nan"), float("nan"), float("nan")
        A = np.polyfit(t[m], np.log(y[m]), 1)
        tau = -1.0 / A[0] if A[0] < 0 else float("inf")
        pred = np.exp(np.polyval(A, t[m]))
        ss = float(np.sum((y[m] - y[m].mean()) ** 2))
        r2 = 1.0 - float(np.sum((y[m] - pred) ** 2)) / ss if ss > 0 else 0.0
        return float(tau), float(r2), float(np.exp(A[1]))


def classify(series: np.ndarray, ev: dict, *, pre: int, post: int,
             onset_min: float, min_persist: int, decay_r2_min: float) -> dict:
    rs, dp = ev["rest_start"], ev["depart"]
    pre_seg = series[max(0, rs - pre):rs]
    pre_seg = pre_seg[np.isfinite(pre_seg)]
    if pre_seg.size < 3:
        return dict(verdict="unusable", reason="no pre-baseline")
    med_pre = float(np.median(pre_seg))
    mad_pre = float(np.median(np.abs(pre_seg - med_pre))) + 1e-6
    band = med_pre + 3 * 1.4826 * mad_pre
    during = series[rs:dp + 1]
    peak = float(np.nanmax(during)) if np.isfinite(during).any() else float("nan")
    onset_step = peak - med_pre
    post_t = np.arange(1, post + 1)
    post_c = series[dp + 1:dp + 1 + post]
    post_t = post_t[:len(post_c)]
    # persistence: consecutive post frames above the pre-baseline band, starting right after departure
    persist = 0
    for v in post_c:
        if np.isfinite(v) and v > band:
            persist += 1
        else:
            break
    tau, r2, c0 = _fit_decay(post_t.astype(float), post_c, med_pre)
    # verdict
    if onset_step <= onset_min or persist < 2:
        verdict = "no_ghost"
    elif persist >= len(post_c) - 1 and (not np.isfinite(tau) or tau > post * 3):
        verdict = "persistent_no_decay"      # stays hot, never decays -> likely structure the rat sat by
    elif persist >= min_persist and np.isfinite(tau) and r2 >= decay_r2_min and c0 > 0:
        verdict = "ghost"
    else:
        verdict = "ambiguous"
    return dict(verdict=verdict, med_pre=round(med_pre, 2), band=round(band, 2), peak=round(peak, 2),
                onset_step=round(onset_step, 2), persist_frames=int(persist),
                tau_s=round(tau, 1) if np.isfinite(tau) else None, decay_r2=round(r2, 3) if np.isfinite(r2) else None,
                onset_amp=round(c0, 2) if np.isfinite(c0) else None)


# --------------------------------------------------------------------------------------
# Frame grabbing for crops
# --------------------------------------------------------------------------------------
def grab_bgr(path: str, w: int, h: int, frame: int) -> np.ndarray | None:
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(frame), "-i", path,
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                       capture_output=True)
    if len(p.stdout) < w * h * 3:
        return None
    return np.frombuffer(p.stdout[:w * h * 3], np.uint8).reshape(h, w, 3)


def _plot_event(out_png: Path, series: np.ndarray, ev: dict, cls: dict, pre: int, post: int) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    rs, dp = ev["rest_start"], ev["depart"]
    lo, hi = max(0, rs - pre), min(len(series), dp + 1 + post)
    t = np.arange(lo, hi)
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.plot(t, series[lo:hi], ".-", ms=3, lw=1, color="#c23")
    ax.axvspan(rs, dp, color="#8bd", alpha=0.3, label="rat present (dwell)")
    ax.axvline(dp, color="k", ls="--", lw=1, label="departure")
    if cls.get("band") is not None:
        ax.axhline(cls["band"], color="gray", ls=":", lw=1, label="baseline+3σ")
    ax.set_title(f"site ({int(ev['cx'])},{int(ev['cy'])})  verdict={cls['verdict']}  "
                 f"persist={cls.get('persist_frames')}f  tau={cls.get('tau_s')}s  R2={cls.get('decay_r2')}")
    ax.set_xlabel("frame (1 fps)  —  time relative to departure = frame−depart")
    ax.set_ylabel("annulus contrast (rel. brightness)")
    ax.legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    fig.savefig(out_png, dpi=90)
    plt.close(fig)


def _save_crops(out_dir: Path, video: str, w: int, h: int, ev: dict, params) -> None:
    rs, dp = ev["rest_start"], ev["depart"]
    stamps = {"before": max(0, rs - 15), "during": (rs + dp) // 2, "after": dp + 20}
    cx, cy = int(ev["cx"]), int(ev["cy"])
    x0, x1, y0, y1 = max(0, cx - 60), min(w, cx + 60), max(0, cy - 60), min(h, cy + 60)
    for name, fr in stamps.items():
        bgr = grab_bgr(video, w, h, fr)
        if bgr is None:
            continue
        crop = bgr[y0:y1, x0:x1].copy()
        cv2.rectangle(crop, (cx - x0 - 12, cy - y0 - 12), (cx - x0 + 12, cy - y0 + 12), (0, 255, 0), 1)
        cv2.imwrite(str(out_dir / f"site_{cx}_{cy}_{name}_f{fr}.png"), crop)


# --------------------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Phase 0 feasibility probe for thermal rat traces.")
    ap.add_argument("--video")
    ap.add_argument("--base", default="Q:/hc997/SocialFieldRat2026")
    ap.add_argument("--cam", default="108_thermal")
    ap.add_argument("--date")
    ap.add_argument("--hour")
    ap.add_argument("--out", required=True)
    ap.add_argument("--detections", help="reuse a detect_blobs detections.csv (else runs the detector inline)")
    ap.add_argument("--max-frames", type=int, default=None, dest="max_frames")
    ap.add_argument("--max-events", type=int, default=40, dest="max_events")
    ap.add_argument("--plot-top", type=int, default=8, dest="plot_top")
    # geometry / thresholds (calibrated by this probe's own output)
    ap.add_argument("--disk-r", type=int, default=12, dest="disk_r")
    ap.add_argument("--ann-r0", type=int, default=20, dest="ann_r0")
    ap.add_argument("--ann-r1", type=int, default=36, dest="ann_r1")
    ap.add_argument("--pre", type=int, default=25)
    ap.add_argument("--post", type=int, default=150)
    ap.add_argument("--dwell-min", type=int, default=8, dest="dwell_min")
    ap.add_argument("--gap", type=int, default=15)
    ap.add_argument("--onset-min", type=float, default=8.0, dest="onset_min")
    ap.add_argument("--min-persist", type=int, default=5, dest="min_persist")
    ap.add_argument("--decay-r2-min", type=float, default=0.3, dest="decay_r2_min")
    a = ap.parse_args(argv)
    if cv2 is None:
        print("ERROR: OpenCV required", file=sys.stderr)
        return 2

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "crops").mkdir(exist_ok=True)
    video = a.video or db.find_video(a.base, a.cam, a.date, a.hour)
    w, h, dur = db.ffprobe_wh_dur(video)
    params = db.Params()
    overlay = db.build_overlay_mask(h, w, db.OVERLAY_MASKS.get(a.cam, db.DEFAULT_OVERLAYS), params.border_px)

    # ---- pass 1: rat detections (reuse detector or a prior CSV) ----
    dets: list[tuple[int, float, float]] = []
    nframes = 0
    if a.detections:
        with open(a.detections) as f:
            for r in csv.DictReader(f):
                dets.append((int(r["frame"]), float(r["cx"]), float(r["cy"])))
                nframes = max(nframes, int(r["frame"]) + 1)
        print(f"loaded {len(dets)} detections from {a.detections}")
    else:
        print("pass 1/2: running rat detector to find dwell sites ...")
        detector = db.WarmBlobDetector(params, overlay)
        for idx, bgr in db.iter_frames(video, w, h, 0.0, a.max_frames):
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            for d in detector.process(gray, db.red_crosshair_mask(bgr, params)):
                dets.append((idx, d["cx"], d["cy"]))
            nframes = idx + 1
    if a.max_frames:
        nframes = min(nframes, a.max_frames)

    events = derive_events(dets, nframes, dwell_min=a.dwell_min, gap=a.gap)[:a.max_events]
    print(f"derived {len(events)} rest-then-depart events from {len(dets)} detections over {nframes} frames")
    if not events:
        (out / "feasibility_summary.json").write_text(json.dumps(
            dict(video=video, cam=a.cam, nframes=nframes, events=0,
                 decision="NO_EVENTS", note="No rat dwelled-then-departed cleanly; nothing to test. "
                 "Try a busier hour or lower --dwell-min."), indent=2))
        print("NO EVENTS to test — see feasibility_summary.json")
        return 0

    # precompute ring indices per event site
    rings = [_ring_indices(e["cx"], e["cy"], a.disk_r, a.ann_r0, a.ann_r1, h, w) for e in events]
    lo = min(max(0, e["rest_start"] - a.pre) for e in events)
    hi = max(min(nframes, e["depart"] + 1 + a.post) for e in events)
    series = [np.full(nframes, np.nan, np.float32) for _ in events]

    # ---- pass 2: annulus contrast over the union window ----
    print(f"pass 2/2: measuring annulus contrast at {len(events)} sites over frames [{lo},{hi}) ...")
    for idx, bgr in db.iter_frames(video, w, h, float(lo), a.max_frames):
        fr = lo + idx
        if fr >= hi:
            break
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        norm = db.robust_norm(gray, overlay)
        invalid = (overlay > 0) | (db.red_crosshair_mask(bgr, params) > 0)
        for si, e in enumerate(events):
            if max(0, e["rest_start"] - a.pre) <= fr < min(nframes, e["depart"] + 1 + a.post):
                series[si][fr] = contrast_at(norm, invalid, *rings[si])

    # ---- classify + write ----
    rows, counts = [], {}
    for si, e in enumerate(events):
        cls = classify(series[si], e, pre=a.pre, post=a.post, onset_min=a.onset_min,
                       min_persist=a.min_persist, decay_r2_min=a.decay_r2_min)
        counts[cls["verdict"]] = counts.get(cls["verdict"], 0) + 1
        rows.append({**dict(cx=round(e["cx"], 1), cy=round(e["cy"], 1), rest_start=e["rest_start"],
                            depart=e["depart"], dwell_len=e["dwell_len"]), **cls})
    rows.sort(key=lambda r: (r["verdict"] != "ghost", -(r.get("persist_frames") or 0)))

    with open(out / "feasibility.csv", "w", newline="") as f:
        cols = ["cx", "cy", "rest_start", "depart", "dwell_len", "verdict", "med_pre", "band", "peak",
                "onset_step", "persist_frames", "tau_s", "decay_r2", "onset_amp", "reason"]
        wtr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        wtr.writeheader()
        wtr.writerows(rows)

    # plots + crops for the most persistent events
    ranked = sorted(range(len(events)), key=lambda si: -(classify(
        series[si], events[si], pre=a.pre, post=a.post, onset_min=a.onset_min,
        min_persist=a.min_persist, decay_r2_min=a.decay_r2_min).get("persist_frames") or 0))
    for si in ranked[:a.plot_top]:
        e = events[si]
        cls = classify(series[si], e, pre=a.pre, post=a.post, onset_min=a.onset_min,
                       min_persist=a.min_persist, decay_r2_min=a.decay_r2_min)
        _plot_event(out / f"contrast_site_{int(e['cx'])}_{int(e['cy'])}.png", series[si], e, cls, a.pre, a.post)
        _save_crops(out / "crops", video, w, h, e, params)

    n_ghost = counts.get("ghost", 0)
    ghosts = [r for r in rows if r["verdict"] == "ghost"]
    med_tau = float(np.median([g["tau_s"] for g in ghosts if g.get("tau_s")])) if ghosts else None
    med_persist = float(np.median([g["persist_frames"] for g in ghosts])) if ghosts else None
    med_onset = float(np.median([g["onset_step"] for g in ghosts])) if ghosts else None
    decision = "GO" if n_ghost >= 3 else ("NO_GO" if n_ghost == 0 else "AMBIGUOUS")
    calib = None
    if ghosts:
        calib = dict(baseline_window_s=int(round(3 * (med_tau or 60))), min_persist_s=int(med_persist or 5),
                     onset_threshold=round(med_onset or a.onset_min, 1),
                     note="relative-brightness units; 1 fps so seconds==frames")
    summary = dict(
        video=video, cam=a.cam, date=a.date, nframes=nframes, duration_sec=dur,
        events_tested=len(events), verdict_counts=counts, n_ghost=n_ghost,
        median_tau_s=med_tau, median_persist_frames=med_persist, median_onset_step=med_onset,
        decision=decision, calibrated_params=calib,
        params=dict(disk_r=a.disk_r, ann_r0=a.ann_r0, ann_r1=a.ann_r1, pre=a.pre, post=a.post,
                    dwell_min=a.dwell_min, gap=a.gap, onset_min=a.onset_min, min_persist=a.min_persist,
                    decay_r2_min=a.decay_r2_min),
        caveats=[
            "RELATIVE brightness, NOT temperature (AGC white-hot, not radiometric); tau is a relative "
            "relaxation time, not degC cooling.",
            "Times are frame index + filename wallclock; the burned-in OSD clock runs ~1 h behind.",
            "Thermal NOT georeferenced; sites are thermal pixels only.",
            "Auto-anchored on the rat detector (recall ~0.5) so some rest events are missed; small urine "
            "deposits may cool within a frame and be invisible -> biased toward larger resting heat-ghosts.",
            "Unvalidated: inspect the contrast_*.png plots + crops by eye before trusting the decision.",
        ],
    )
    (out / "feasibility_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nDECISION: {decision}   (ghost={n_ghost}, verdicts={counts})")
    if calib:
        print(f"calibrated -> baseline_window_s~{calib['baseline_window_s']}, "
              f"min_persist_s~{calib['min_persist_s']}, onset~{calib['onset_threshold']}")
    print(f"-> {out}  (feasibility.csv, feasibility_summary.json, contrast_*.png, crops/)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
