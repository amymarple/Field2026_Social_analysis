"""thermal/detect_traces.py — detect rat THERMAL TRACES (resting heat-ghosts) on the 108 thermal camera.

Phase 1 of the thermal-traces analysis, built after Phase 0 (`thermal/trace_feasibility.py`) verified on real
2026-07-01 video that a warm residual DOES linger and decay after a rat leaves a spot on the 108 view
(GO: ~2 min decays, tau ~30-84 s) — but NOT on 109 (rats there leave no lingering warmth; substrate-dependent).
So this detector is scoped to 108-type views that image warmable ground.

Approach (RAT-ANCHORED — the Phase-0-validated path, high precision): find where a rat dwelled then left
(the moment a heat-ghost is planted), then confirm at that fixed spot a warm anomaly that (i) stepped up on
arrival, (ii) STAYS elevated AFTER departure, and (iii) DECAYS (finite exponential tau — a constant-warm
structure the rat merely sat by is FLAT and rejected). Reuses the primitives in `trace_feasibility.py`.

Outputs: `traces.csv` (per-event list), a nightly `trace_heatmap.png` (where ghosts accumulate, weighted by
persistence), `summary.json`, and per-trace contrast plots + crops.

EVERYTHING is RELATIVE brightness, NOT temperature (AGC white-hot, not radiometric); tau is a relative
relaxation time. Times are frame index + filename wallclock (OSD clock runs ~1 h behind). Thermal is NOT
georeferenced — trace coords are thermal PIXELS; any cross-ref to WISER rest-sites (house_1 etc.) is by-eye.
Detection is biased toward larger, longer-lived RESTING heat-ghosts and will miss small fast urine deposits.
UNSUPERVISED / weakly validated — every trace is a CANDIDATE.

Usage:
  python thermal/detect_traces.py --cam 108_thermal --date 2026-07-01 --hour 21 --out D:/tmp/traces
  python thermal/detect_traces.py --video <mp4> --detections <detect_blobs detections.csv> --out <dir>
  python thermal/detect_traces.py --selftest
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
import detect_blobs as db          # noqa: E402
import trace_feasibility as tf     # noqa: E402  (reuse: derive_events, _ring_indices, contrast_at, classify, plots)

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=str(Path(__file__).resolve().parent)).stdout.strip() or None
    except Exception:
        return None


def measure_events(video, w, h, cam, params, events, *, disk_r, ann_r0, ann_r1, pre, post,
                   motion_thresh=10.0, max_frames=None):
    """Two-pass: for each event site, measure annulus contrast(t) over its window (AGC-undone, OSD+crosshair
    excluded). Also measures POST-DEPARTURE frame-to-frame MOTION at the disk — a cooling ground ghost is
    thermally static (small smooth change) while a still-present rat twitches (large change). Returns
    (series, post_motion_frac) aligned to `events`."""
    nframes = max((e["depart"] + post + 1) for e in events)
    rings = [tf._ring_indices(e["cx"], e["cy"], disk_r, ann_r0, ann_r1, h, w) for e in events]
    lo = min(max(0, e["rest_start"] - pre) for e in events)
    hi = max(min(nframes, e["depart"] + 1 + post) for e in events)
    overlay = db.build_overlay_mask(h, w, db.OVERLAY_MASKS.get(cam, db.DEFAULT_OVERLAYS), params.border_px)
    series = [np.full(nframes, np.nan, np.float32) for _ in events]
    mo_hit = [0] * len(events)
    mo_tot = [0] * len(events)
    prev = None
    for idx, bgr in db.iter_frames(video, w, h, float(lo), max_frames):
        fr = lo + idx
        if fr >= hi:
            break
        norm = db.robust_norm(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), overlay)
        invalid = (overlay > 0) | (db.red_crosshair_mask(bgr, params) > 0)
        for si, e in enumerate(events):
            if max(0, e["rest_start"] - pre) <= fr < min(nframes, e["depart"] + 1 + post):
                series[si][fr] = tf.contrast_at(norm, invalid, *rings[si])
            if prev is not None and e["depart"] < fr < min(nframes, e["depart"] + 1 + post):
                dy, dx = rings[si][0]  # disk pixels
                v = ~invalid[dy, dx]
                if int(v.sum()) >= 10:
                    mo_tot[si] += 1
                    if float(np.median(np.abs(norm[dy, dx][v] - prev[dy, dx][v]))) > motion_thresh:
                        mo_hit[si] += 1
        prev = norm
    post_motion = [(mo_hit[i] / mo_tot[i] if mo_tot[i] else 0.0) for i in range(len(events))]
    return series, post_motion


def render_heatmap(rows, w, h, rep_bgr, out_png, splat_sigma=22.0):
    """Accumulate accepted-trace footprints (weighted by persistence) into a heatmap overlaid on a frame."""
    heat = np.zeros((h, w), np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    for r in rows:
        if r["verdict"] != "ghost":
            continue
        wgt = float(r["persist_frames"]) or 1.0
        heat += wgt * np.exp(-(((xx - r["cx"]) ** 2 + (yy - r["cy"]) ** 2) / (2 * splat_sigma ** 2)))
    if heat.max() > 0:
        heat /= heat.max()
    cmap = cv2.applyColorMap((heat * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    base = rep_bgr if rep_bgr is not None else np.zeros((h, w, 3), np.uint8)
    vis = cv2.addWeighted(base, 0.55, cmap, 0.45, 0)
    for r in rows:
        if r["verdict"] == "ghost":
            cv2.circle(vis, (int(r["cx"]), int(r["cy"])), 6, (255, 255, 255), 1)
    cv2.imwrite(str(out_png), vis)


def run(video, out_dir, cam, *, date=None, params=None, detections=None, max_frames=None,
        disk_r=12, ann_r0=20, ann_r1=36, pre=25, post=150, dwell_min=8, gap=15,
        onset_min=8.0, min_persist=5, decay_r2_min=0.3, motion_thresh=10.0, post_motion_max=0.15,
        plot_top=12) -> dict:
    assert cv2 is not None, "OpenCV required"
    params = params or db.Params()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "crops").mkdir(exist_ok=True)
    w, h, dur = db.ffprobe_wh_dur(video)
    overlay = db.build_overlay_mask(h, w, db.OVERLAY_MASKS.get(cam, db.DEFAULT_OVERLAYS), params.border_px)

    # pass 1: rat detections (reuse detector or a prior CSV) -> rest-then-depart events
    dets, nframes = [], 0
    if detections:
        with open(detections) as f:
            for r in csv.DictReader(f):
                dets.append((int(r["frame"]), float(r["cx"]), float(r["cy"])))
                nframes = max(nframes, int(r["frame"]) + 1)
    else:
        detector = db.WarmBlobDetector(params, overlay)
        for idx, bgr in db.iter_frames(video, w, h, 0.0, max_frames):
            for d in detector.process(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), db.red_crosshair_mask(bgr, params)):
                dets.append((idx, d["cx"], d["cy"]))
            nframes = idx + 1
    if max_frames:
        nframes = min(nframes, max_frames)
    events = tf.derive_events(dets, nframes, dwell_min=dwell_min, gap=gap)
    print(f"{len(events)} rest-then-depart events from {len(dets)} detections over {nframes} frames")

    # index detections by frame for the re-detection (rat came back / never left) gate
    det_by_frame = {}
    for fr, cx, cy in dets:
        det_by_frame.setdefault(fr, []).append((cx, cy))

    def first_return(e):
        """First frame-offset after departure where a rat is re-detected within the site radius (or None)."""
        for f in range(e["depart"] + 1, e["depart"] + 1 + post):
            for (cx, cy) in det_by_frame.get(f, []):
                if (cx - e["cx"]) ** 2 + (cy - e["cy"]) ** 2 <= 40.0 ** 2:
                    return f - e["depart"]
        return None

    rows = []
    if events:
        series, post_motion = measure_events(video, w, h, cam, params, events,
                                             disk_r=disk_r, ann_r0=ann_r0, ann_r1=ann_r1, pre=pre, post=post,
                                             motion_thresh=motion_thresh, max_frames=max_frames)
        for tid, (e, s, pm) in enumerate(zip(events, series, post_motion)):
            cls = tf.classify(s, e, pre=pre, post=post, onset_min=onset_min,
                              min_persist=min_persist, decay_r2_min=decay_r2_min)
            persist = cls.get("persist_frames", 0) or 0
            # GATE 1: the rat is re-detected during the persistence -> it never left / came back. Only the
            # frames BEFORE the return are a clean ghost.
            rr = first_return(e)
            clean_persist = min(persist, rr - 1) if rr is not None else persist
            verdict = cls["verdict"]
            if verdict == "ghost":
                if clean_persist < min_persist:
                    verdict = "rat_present"          # warmth is the still-present / returning rat, not a ghost
                elif pm > post_motion_max:
                    verdict = "rat_present"          # GATE 2: post-departure micro-motion -> undetected rat
            rows.append(dict(
                trace_id=tid, cam=cam, date=date or "",
                arrival_frame=e["rest_start"], depart_frame=e["depart"], dwell_len=e["dwell_len"],
                persist_frames=persist, clean_persist=clean_persist, persist_s=clean_persist,
                rat_return_f=rr, post_motion_frac=round(pm, 3),
                cx=round(e["cx"], 1), cy=round(e["cy"], 1),
                peak_contrast=cls.get("peak"), onset_step=cls.get("onset_step"),
                onset_amp=cls.get("onset_amp"), tau_s=cls.get("tau_s"), decay_r2=cls.get("decay_r2"),
                verdict=verdict, depart_t_sec=e["depart"],
                osd_clock_note="filename clock; OSD ~1h behind"))
        # plots + crops for the strongest accepted/ambiguous traces
        order = sorted(range(len(rows)), key=lambda i: (rows[i]["verdict"] != "ghost",
                                                        -(rows[i]["persist_frames"] or 0)))
        for i in order[:plot_top]:
            e, s = events[i], series[i]
            cls = {k: rows[i].get(k) for k in ("verdict", "persist_frames", "tau_s", "decay_r2", "band")}
            cls.setdefault("band", None)
            tf._plot_event(out / f"trace_{rows[i]['trace_id']}_c{int(e['cx'])}_{int(e['cy'])}.png", s, e, cls, pre, post)
            tf._save_crops(out / "crops", video, w, h, e, params)

    _write_csv(out / "traces.csv", rows)
    rep = tf.grab_bgr(video, w, h, min(nframes // 2, nframes - 1)) if nframes else None
    render_heatmap(rows, w, h, rep, out / "trace_heatmap.png")

    ghosts = [r for r in rows if r["verdict"] == "ghost"]
    summary = dict(
        video=video, cam=cam, date=date, width=w, height=h, duration_sec=dur, git=_git_commit(),
        frames=nframes, events_tested=len(events), traces_confirmed=len(ghosts),
        verdict_counts={v: sum(1 for r in rows if r["verdict"] == v) for v in {r["verdict"] for r in rows}},
        median_tau_s=float(np.median([g["tau_s"] for g in ghosts if g.get("tau_s")])) if ghosts else None,
        median_persist_frames=float(np.median([g["persist_frames"] for g in ghosts])) if ghosts else None,
        params=dict(disk_r=disk_r, ann_r0=ann_r0, ann_r1=ann_r1, pre=pre, post=post, dwell_min=dwell_min,
                    gap=gap, onset_min=onset_min, min_persist=min_persist, decay_r2_min=decay_r2_min),
        caveats=[
            "RELATIVE brightness, NOT temperature (AGC white-hot, not radiometric); tau is a relative "
            "relaxation time, not degC cooling.",
            "Traces are CANDIDATE resting heat-ghosts; NOT confirmed marks/deposits, NOT identity.",
            "108-scoped: Phase 0 found ghosts visible on 108's warmable-ground view but NOT on 109 (vegetation).",
            "Biased to larger/longer resting ghosts; small fast urine deposits are systematically missed.",
            "Times = frame idx + filename wallclock (OSD ~1h behind); thermal NOT georeferenced (pixel coords).",
            "Rat-anchored on the rat detector (recall ~0.5) so some ghosts are missed; unsupervised/unvalidated.",
            "STILL-PRESENT-RAT confound: 'departure' = detector stops firing, which its ~0.5 recall makes "
            "unreliable. Guarded by (1) rejecting re-detection in the persistence window and (2) a post-"
            "departure MOTION gate (a cooling ghost is thermally static; a lingering rat twitches). A rat "
            "that sits perfectly still is still indistinguishable from a ghost by thermal alone -> "
            "verdict='rat_present' filters the detectable cases only.",
        ],
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"confirmed {len(ghosts)} trace(s); -> {out}  (traces.csv, trace_heatmap.png, summary.json)")
    return summary


def _write_csv(path, rows):
    cols = ["trace_id", "cam", "date", "arrival_frame", "depart_frame", "dwell_len", "persist_frames",
            "clean_persist", "persist_s", "rat_return_f", "post_motion_frac", "cx", "cy", "peak_contrast",
            "onset_step", "onset_amp", "tau_s", "decay_r2", "verdict", "depart_t_sec", "osd_clock_note"]
    with open(path, "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        wtr.writeheader()
        wtr.writerows(rows)


# --------------------------------------------------------------------------------------
# Offline self-test — a synthetic decaying ghost must be ACCEPTED, a static warm bar REJECTED.
# --------------------------------------------------------------------------------------
def selftest() -> int:
    if cv2 is None:
        print("FAIL — trace self-test: OpenCV unavailable")
        return 1
    fails = []
    h, w = 240, 320
    rng = np.random.default_rng(0)
    T = 260
    arrive, depart, ghost_tau = 30, 60, 40.0
    rat1 = (150.0, 120.0)   # rat rests then LEAVES -> a decaying, motionless ghost (must ACCEPT)
    rat2 = (250.0, 120.0)   # rat the detector LOSES: stays put, jitters, slowly decays (must REJECT via motion)
    yy, xx = np.mgrid[0:h, 0:w]
    # static low-frequency background texture -> realistic MAD so robust_norm doesn't blow up sensor noise
    tex = cv2.GaussianBlur(np.random.default_rng(7).normal(0, 600, (h, w)).astype(np.float32), (0, 0), 8)

    def gauss(cx, cy, sig):
        return np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sig ** 2)))

    def frame(t, j2):
        img = np.full((h, w), 40 + 20 * np.sin(t / 6.0), np.float32) + tex + rng.normal(0, 2, (h, w))
        img[:, 20:26] += 70                                    # STATIC warm bar (no onset/decay) -> reject
        if arrive <= t < depart:                               # both rats present, bright, compact
            img += 150 * gauss(*rat1, 6.0) + 150 * gauss(*rat2, 6.0)
        elif t >= depart:
            img += 60 * np.exp(-(t - depart) / ghost_tau) * gauss(*rat1, 8.0)          # rat1: motionless ghost
            img += 100 * np.exp(-(t - depart) / 100.0) * gauss(rat2[0] + j2[0], rat2[1] + j2[1], 6.0)  # rat2: jitters
        return np.clip(img, 0, 255).astype(np.uint8)

    overlay = np.zeros((h, w), np.uint8)
    dets = []                                                  # detections stop at departure for BOTH rats + bar
    for t in range(arrive, depart):
        dets.append((t, rat1[0] + rng.normal(0, 1), rat1[1] + rng.normal(0, 1)))
        dets.append((t, rat2[0] + rng.normal(0, 1), rat2[1] + rng.normal(0, 1)))
        dets.append((t, 23.0, 120.0 + rng.normal(0, 1)))
    events = tf.derive_events(dets, T, dwell_min=8, gap=15)
    if not any(abs(e["cx"] - rat1[0]) < 15 for e in events):
        fails.append("S1 no rest-depart event derived at the ghost spot")

    rings = [tf._ring_indices(e["cx"], e["cy"], 12, 20, 36, h, w) for e in events]
    series = [np.full(T, np.nan, np.float32) for _ in events]
    mo_hit, mo_tot, prev = [0] * len(events), [0] * len(events), None
    for t in range(T):
        j2 = rng.normal(0, 2.5, 2) if t >= depart else (0.0, 0.0)   # rat2 twitches after departure
        norm = db.robust_norm(frame(t, j2), overlay)
        inv = overlay > 0
        for si, e in enumerate(events):
            series[si][t] = tf.contrast_at(norm, inv, *rings[si])
            if prev is not None and e["depart"] < t < e["depart"] + 1 + 150:
                dy, dx = rings[si][0]
                mo_tot[si] += 1
                if float(np.median(np.abs(norm[dy, dx] - prev[dy, dx]))) > 10.0:
                    mo_hit[si] += 1
        prev = norm
    post_motion = [mo_hit[i] / mo_tot[i] if mo_tot[i] else 0.0 for i in range(len(events))]

    verdicts, motions = {}, {}
    for i, (e, s) in enumerate(zip(events, series)):
        cls = tf.classify(s, e, pre=25, post=150, onset_min=8.0, min_persist=5, decay_r2_min=0.3)
        v, pm = cls["verdict"], post_motion[i]
        if v == "ghost" and pm > 0.15:                          # motion gate -> undetected still-present rat
            v = "rat_present"
        key = ("ghost" if abs(e["cx"] - rat1[0]) < 15 else "linger" if abs(e["cx"] - rat2[0]) < 15
               else "bar" if abs(e["cx"] - 23) < 15 else "other")
        verdicts[key], motions[key] = v, round(pm, 2)
    if verdicts.get("ghost") != "ghost":
        fails.append(f"S2 decaying ghost not accepted (got {verdicts.get('ghost')}, motion {motions.get('ghost')})")
    if verdicts.get("bar") == "ghost":
        fails.append("S3 static warm bar wrongly accepted as a ghost")
    if verdicts.get("linger") == "ghost":
        fails.append(f"S4 lingering (jittering) rat accepted as ghost — motion gate failed (motion {motions.get('linger')})")
    if motions.get("ghost", 1.0) >= 0.15:
        fails.append(f"S5 motionless ghost has high post-motion {motions.get('ghost')} (gate would false-reject it)")

    if fails:
        print("FAIL — thermal trace detector self-test")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"PASS — thermal trace detector self-test (ghost accepted, static bar + jittering lingering-rat "
          f"rejected; verdicts={verdicts}, motion={motions})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Detect rat thermal traces (resting heat-ghosts) on 108.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--video")
    ap.add_argument("--base", default="Q:/hc997/SocialFieldRat2026")
    ap.add_argument("--cam", default="108_thermal")
    ap.add_argument("--date")
    ap.add_argument("--hour")
    ap.add_argument("--out")
    ap.add_argument("--detections")
    ap.add_argument("--max-frames", type=int, default=None, dest="max_frames")
    for name, typ in (("disk_r", int), ("ann_r0", int), ("ann_r1", int), ("pre", int), ("post", int),
                      ("dwell_min", int), ("gap", int), ("onset_min", float), ("min_persist", int),
                      ("decay_r2_min", float)):
        ap.add_argument(f"--{name.replace('_', '-')}", type=typ, default=None, dest=name)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if cv2 is None:
        print("ERROR: OpenCV required", file=sys.stderr)
        return 2
    video = a.video or (db.find_video(a.base, a.cam, a.date, a.hour) if (a.date and a.hour) else None)
    if not video:
        ap.error("provide --video, or --date and --hour")
    if not a.out:
        ap.error("provide --out")
    kw = {k: getattr(a, k) for k in ("disk_r", "ann_r0", "ann_r1", "pre", "post", "dwell_min", "gap",
                                     "onset_min", "min_persist", "decay_r2_min") if getattr(a, k) is not None}
    run(video, a.out, a.cam, date=a.date, detections=a.detections, max_frames=a.max_frames, **kw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
