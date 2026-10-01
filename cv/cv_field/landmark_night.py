"""landmark_night.py — automatic NIGHT reference for the rigid-landmark tracking: dusk hand-off + dawn closure check.

Why: the structures do not move, but at night the camera's own IR illuminator lights the scene, so the daytime
appearance around each landmark in the 09-18 reference does not match night frames and the tracking of
landmark_track.py fails there. Instead of labelling a night frame per camera, the night reference is made
automatically (plan agreed with the user, 2026-10-01; implementation_plan/2026-09-28-cohort3-camera-stability.md):

  1. Switch: mean brightness of every keyframe (~every 2 s; 64x64 grey thumbnails, keyframes only) over DUSK_WIN; the
     switch = the largest keyframe-to-keyframe jump, extended over neighbouring same-sign jumps > RAMP_Z robust SDs (an
     exposure ramp). The cohort footage is IR by day too (no colour / IR-cut change; saturation of the hand-off frames is
     logged to check), so the switch is the illuminator turning on — nothing optical changes, the pose is the same.
  2. Hand-off: the last keyframe BEFORE the switch (daytime appearance) is tracked from the 09-18 labelled reference with
     landmark_track.track_frame -> A_pre (if not ok: frames PRE_FALLBACK_S earlier). The frame HANDOFF_POST_S after the
     switch is the NIGHT REFERENCE; its labels = the 09-18 labels moved by A_pre (pieces kept, names kept).
  3. Night frames (default 21:00, 00:00, 03:01) are tracked from the night reference -> A_n; the map from the 09-18
     reference is A_total = A_n o A_pre, reported like the daytime track (tx, ty, rot, scale from landmark_track.params).
  4. Dawn closure: the dawn switch (DAWN_WIN) is found the same way. The last keyframe before it (still night appearance)
     is tracked from the night reference -> A_n o A_pre; the frame HANDOFF_POST_S after it (daytime appearance; later
     fallbacks POST_FALLBACK_S if not ok) from the 09-18 reference -> A_d. Both describe (nearly) the same moment, so
          closure = median / max over the 09-18 fit-set label points p of |A_n A_pre p - A_d p|   [px, full-res upright]
     PASS if median <= CLOSURE_MAX px. It checks the dusk hand-off and the night tracking together, without labels.
     (A pure optical shift at the switch would cancel between dusk and dawn and not show — none is expected, see 1.)
Definitions: z = |jump| / (1.4826 * MAD of all keyframe-to-keyframe jumps in the window); z2 = the same for the next
largest jump outside the ramp (z2 close to z = ambiguous switch); gap = time between the two frames compared at dawn [s].
The agent makes no visual judgement: the user reviews the overlays (night frames, hand-off pairs) and brightness plots.

Usage: python cv/cv_field/landmark_night.py --cohort 2026c --night 2026-09-03 [--cameras CH01 CH02 CH03 CH04]
                                            [--night-times 21:00 00:00 03:01]
       python cv/cv_field/landmark_night.py --selftest          # offline: synthetic clip (ffmpeg), no field data
Output: $FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/cv_field_landmark_night_<ts>/ (frames, overlays, brightness_<CH>.png,
        brightness_<CH>.csv, handoff.csv, night_frames.csv) and
        results/<cohort>/cv_field/reports/cv_field_landmark_night_<cohort>.md + run_manifest_landmark_night_<cohort>.json
        (own pointer, so landmark_track's run_manifest.json survives).
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import grab_frames as gf  # noqa: E402
import landmark_track as lt  # noqa: E402

DUSK_WIN = (time(19, 0), time(21, 0))          # early September, Ithaca: sunset ~19:30 EDT (field-PC time)
DAWN_WIN = (time(5, 30), time(7, 30))          # sunrise ~06:40
THUMB = 64
MAX_KEY_GAP_S = 10.0                           # a larger gap between keyframes = a segment boundary: no jump there
RAMP_Z, SWITCH_Z_MIN = 5.0, 10.0
HANDOFF_POST_S = 10.0
PRE_FALLBACK_S = (0, 60, 300, 900)             # pre-switch daytime frame: the keyframe itself, then earlier
POST_FALLBACK_S = (0, 60, 300, 900)            # dawn daytime frame: HANDOFF_POST_S after the switch, then later
CLOSURE_MAX = 2.0


def keyframe_brightness(ffmpeg: str, video: Path, off0: float, dur: float) -> list[tuple[float, float]]:
    """(pts [s, file time], mean grey) of every keyframe in [off0, off0 + dur) — keyframes only, 64x64 thumbnails."""
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-skip_frame", "nokey", "-copyts", "-ss", f"{max(0.0, off0):.3f}",
           "-t", f"{dur:.3f}", "-i", str(video), "-an", "-vf", f"scale={THUMB}:{THUMB},format=gray,showinfo",
           "-vsync", "0", "-f", "rawvideo", "-"]
    p = subprocess.run(cmd, capture_output=True)
    n = len(p.stdout) // (THUMB * THUMB)
    pts = [float(v) for v in gf.PTS.findall(p.stderr.decode(errors="replace"))]
    frames = np.frombuffer(p.stdout[:n * THUMB * THUMB], np.uint8).reshape(n, THUMB * THUMB)
    return [(t, float(f.mean())) for t, f in zip(pts, frames)]


def brightness_series(ffmpeg: str, ffprobe: str, root: Path, cam: str, t_a: datetime, t_b: datetime) -> list[tuple]:
    """[(time, mean grey, video, pts)] of the camera's keyframes between t_a and t_b (field-PC time)."""
    out = []
    for s, e, f in gf.segments(root, cam, t_b.date(), ffprobe):
        a, b = max(s, t_a), min(e, t_b)
        if a >= b:
            continue
        for pts, m in keyframe_brightness(ffmpeg, f, (a - s).total_seconds(), (b - a).total_seconds()):
            out.append((s + timedelta(seconds=pts), m, f, pts))
    return sorted(out, key=lambda r: r[0])


def find_switch(series: list[tuple]) -> dict | None:
    """Largest keyframe-to-keyframe brightness jump, extended over its same-sign ramp. None if too few keyframes."""
    if len(series) < 10:
        return None
    t = [r[0] for r in series]
    m = np.array([r[1] for r in series], float)
    dt = np.array([(b - a).total_seconds() for a, b in zip(t[:-1], t[1:])])
    d = np.where(dt <= MAX_KEY_GAP_S, np.diff(m), 0.0)
    mad = 1.4826 * float(np.median(np.abs(d - np.median(d)))) + 1e-3
    i = int(np.argmax(np.abs(d)))
    sg = np.sign(d[i])
    s = i
    while s - 1 >= 0 and np.sign(d[s - 1]) == sg and abs(d[s - 1]) > RAMP_Z * mad:
        s -= 1
    e = i
    while e + 1 < len(d) and np.sign(d[e + 1]) == sg and abs(d[e + 1]) > RAMP_Z * mad:
        e += 1
    rest = np.abs(np.concatenate([d[:s], d[e + 1:]]))
    z = abs(d[i]) / mad
    return {"t_pre": t[s], "t_post": t[e + 1], "jump": float(m[e + 1] - m[s]), "z": float(z),
            "z2": float(rest.max() / mad) if len(rest) else 0.0, "ramp_keyframes": e - s + 1,
            "clear": bool(z >= SWITCH_Z_MIN and (not len(rest) or rest.max() < 0.5 * abs(d[i])))}


def to3(A: np.ndarray) -> np.ndarray:
    return np.vstack([A, [0.0, 0.0, 1.0]])


def compose(A2: np.ndarray, A1: np.ndarray) -> np.ndarray:
    """p -> A2(A1(p))."""
    return (to3(A2) @ to3(A1))[:2]


def apply(A: np.ndarray, P: np.ndarray) -> np.ndarray:
    return P @ A[:, :2].T + A[:, 2]


def move_labels(landmarks: dict, A: np.ndarray, day: date) -> dict:
    """The labels moved by A (pieces and names kept), only those usable on `day`."""
    return {n: [apply(A, p).tolist() for p in lt.pieces_of(v)] for n, v in landmarks.items() if lt.usable(n, day)}


def fit_points(landmarks: dict, day: date) -> np.ndarray:
    return np.vstack([p for n, v in landmarks.items() if lt.in_fit(n) and lt.usable(n, day) for p in lt.pieces_of(v)])


def closure(A1: np.ndarray, A2: np.ndarray, P: np.ndarray) -> tuple[float, float]:
    e = np.hypot(*(apply(A1, P) - apply(A2, P)).T)
    return float(np.median(e)), float(e.max())


def grab(t: datetime, cam: str, root: Path, ff: tuple[str, str], out: Path, tag: str) -> tuple[np.ndarray, datetime] | None:
    row = gf.grab_one({"camera": cam, "time": t, "tag": tag}, root, ff[0], ff[1], "exact", "cpu", out)
    if row["error"] or not row["frame_time"]:
        print(f"  {cam} {t:%m-%d %H:%M:%S} {tag}: {row['error'] or 'no frame time'}")
        return None
    return row["_img"], datetime.strptime(row["frame_time"][:19], "%Y-%m-%d %H:%M:%S")


def track_first_ok(times: list[datetime], cam: str, ref_g, labels, kinds, root, ff, out, tag) -> dict | None:
    """Track candidate frames in order; the first with status ok, else the one with the lowest held-out median."""
    best = None
    for t in times:
        g = grab(t, cam, root, ff, out, tag)
        if g is None:
            continue
        img, ft = g
        res = lt.track_frame(ref_g, lt.prep(img), labels, kinds, ft.date())
        cand = {"res": res, "img": img, "time": ft, "target": t}
        if res.get("status") == "ok":
            return cand
        if res["A"] is not None and (best is None or res.get("held_med", np.inf) < best["res"].get("held_med", np.inf)):
            best = cand
    return best


def plot_brightness(series_d, sw_d, series_m, sw_m, cam: str, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 2, figsize=(12, 3.2))
    for ax, ser, sw, title in ((axs[0], series_d, sw_d, "dusk"), (axs[1], series_m, sw_m, "dawn")):
        if ser:
            ax.plot([r[0] for r in ser], [r[1] for r in ser], lw=0.8)
        if sw:
            for k, c in (("t_pre", "tab:green"), ("t_post", "tab:red")):
                ax.axvline(sw[k], color=c, lw=0.8)
            ax.set_title(f"{cam} {title}: switch {sw['t_pre']:%H:%M:%S}->{sw['t_post']:%H:%M:%S}, z {sw['z']:.0f}, "
                         f"z2 {sw['z2']:.0f}", fontsize=9)
        ax.set_ylabel("mean grey (keyframes)")
        ax.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def save_overlay(run: Path, img, labels, A, day, caption, dropped, name) -> str:
    ov = lt.draw_overlay(img, labels, A, day, caption, dropped)
    s = 2400 / ov.shape[1]
    p = run / "overlays" / name
    cv2.imwrite(str(p), cv2.resize(ov, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 88])
    return p.name


def run_camera(cam: str, night: date, args, run: Path, ff, ffmpeg_cr: str) -> tuple[dict, list[dict]]:
    import camera_review as cr
    root = Path(args.cohort_root)
    frames = run / "frames"
    lab = json.loads(sorted(Path(args.labels_dir).glob(f"landmarks_{cam}_20260918_*.json"))[0].read_text(encoding="utf-8"))
    labels, kinds = lab["landmarks"], lab.get("kind", {})
    size = tuple(int(v) for v in lab["frame_size_upright"])
    got = cr.grab_at(datetime.strptime(lab["time"], "%Y-%m-%d %H:%M:%S"), cam, args, ffmpeg_cr, size)
    if got is None:
        return {"camera": cam, "verdict": "no 09-18 reference frame"}, []
    ref_g = lt.prep(got[0])
    morning = night + timedelta(days=1)
    H = {"camera": cam, "night": f"{night}"}
    ser_d = brightness_series(ff[0], ff[1], root, cam, datetime.combine(night, DUSK_WIN[0]), datetime.combine(night, DUSK_WIN[1]))
    ser_m = brightness_series(ff[0], ff[1], root, cam, datetime.combine(morning, DAWN_WIN[0]), datetime.combine(morning, DAWN_WIN[1]))
    for nm, ser in (("dusk", ser_d), ("dawn", ser_m)):
        with open(run / f"brightness_{cam}_{nm}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["time", "mean_grey", "video", "pts_s"])
            w.writerows([(f"{t:%Y-%m-%d %H:%M:%S.%f}"[:-3], f"{m:.3f}", v.name, f"{p:.3f}") for t, m, v, p in ser])
    sw_d, sw_m = find_switch(ser_d), find_switch(ser_m)
    plot_brightness(ser_d, sw_d, ser_m, sw_m, cam, run / f"brightness_{cam}.png")
    H.update({"dusk_keyframes": len(ser_d), "dawn_keyframes": len(ser_m)})
    for nm, sw in (("dusk", sw_d), ("dawn", sw_m)):
        if sw:
            H.update({f"{nm}_pre": f"{sw['t_pre']:%Y-%m-%d %H:%M:%S}", f"{nm}_post": f"{sw['t_post']:%Y-%m-%d %H:%M:%S}",
                      f"{nm}_jump": round(sw["jump"], 2), f"{nm}_z": round(sw["z"], 1), f"{nm}_z2": round(sw["z2"], 1),
                      f"{nm}_ramp_keyframes": sw["ramp_keyframes"], f"{nm}_clear": sw["clear"]})
    if sw_d is None:
        H["verdict"] = "no dusk switch found"
        return H, []
    # 2. hand-off at dusk
    pre = track_first_ok([sw_d["t_pre"] - timedelta(seconds=s) for s in PRE_FALLBACK_S], cam, ref_g, labels, kinds,
                         root, ff, frames, "dusk_pre")
    post = grab(sw_d["t_post"] + timedelta(seconds=HANDOFF_POST_S), cam, root, ff, frames, "dusk_post")
    if pre is None or post is None or pre["res"]["A"] is None:
        H["verdict"] = "dusk hand-off failed (no daytime fit before the switch)"
        return H, []
    A_pre = pre["res"]["A"]
    night_img, night_t = post
    H.update({"pre_frame": f"{pre['time']:%Y-%m-%d %H:%M:%S}", "pre_status": pre["res"]["status"],
              "pre_held_med_px": round(pre["res"].get("held_med", np.nan), 2),
              "pre_to_nightref_s": round((night_t - pre["time"]).total_seconds(), 1), "night_ref": f"{night_t:%Y-%m-%d %H:%M:%S}",
              "sat_pre": round(cr.saturation(pre["img"]), 1), "sat_nightref": round(cr.saturation(night_img), 1)})
    nlabels = move_labels(labels, A_pre, night_t.date())
    n_g = lt.prep(night_img)
    save_overlay(run, pre["img"], labels, A_pre, pre["time"].date(), f"{cam} DUSK pre {pre['time']:%m-%d %H:%M:%S} (09-18 ref) "
                 f"{pre['res']['status']} held {pre['res'].get('held_med', np.nan):.1f}px", pre["res"].get("dropped", {}),
                 f"{cam}_{pre['time']:%Y%m%d_%H%M%S}_dusk_pre.jpg")
    save_overlay(run, night_img, labels, A_pre, night_t.date(), f"{cam} NIGHT REF {night_t:%m-%d %H:%M:%S} = 09-18 labels moved by the pre-switch fit",
                 {}, f"{cam}_{night_t:%Y%m%d_%H%M%S}_night_ref.jpg")
    # 3. night frames
    rows = []
    for tt in args.night_times:
        t = datetime.combine(night if tt >= time(12, 0) else morning, tt)
        g = grab(t, cam, root, ff, frames, "night")
        if g is None:
            continue
        img, ft = g
        res = lt.track_frame(n_g, lt.prep(img), nlabels, kinds, ft.date())
        A_tot = compose(res["A"], A_pre) if res["A"] is not None else None
        pr = lt.params(A_tot, size) if A_tot is not None else {k: np.nan for k in ("tx", "ty", "rot_deg", "sx", "sy")}
        cap = (f"{cam} {ft:%m-%d %H:%M} NIGHT (via night ref) {res.get('status')} held {res.get('held_med', np.nan):.1f}/"
               f"{res.get('held_p90', np.nan):.1f}px  vs 09-18 t=({pr['tx']:+.1f},{pr['ty']:+.1f}) rot {pr['rot_deg']:+.2f}")
        ov = save_overlay(run, img, labels, A_tot, ft.date(), cap, res.get("dropped", {}), f"{cam}_{ft:%Y%m%d_%H%M%S}_night.jpg")
        rows.append({"camera": cam, "frame_time": f"{ft:%Y-%m-%d %H:%M:%S}", "status": res.get("status", "no fit"),
                     "n_fit_units": len(res["fit_names"]), "held_med_px": res.get("held_med", np.nan),
                     "held_p90_px": res.get("held_p90", np.nan), **pr, "basis": res.get("basis", ""),
                     "n_dropped": len(res.get("dropped", {})),
                     "dropped": "; ".join(f"{u}: {w}" for u, w in sorted(res.get("dropped", {}).items())), "overlay": ov})
        print(f"  {cap}")
    # 4. dawn closure
    if sw_m is None:
        H["verdict"] = "no dawn switch found (closure not checked)"
        return H, rows
    nside = track_first_ok([sw_m["t_pre"] - timedelta(seconds=s) for s in PRE_FALLBACK_S[:3]], cam, n_g, nlabels, kinds,
                           root, ff, frames, "dawn_night")
    dside = track_first_ok([sw_m["t_post"] + timedelta(seconds=HANDOFF_POST_S + s) for s in POST_FALLBACK_S], cam, ref_g,
                           labels, kinds, root, ff, frames, "dawn_day")
    if nside is None or dside is None or nside["res"]["A"] is None or dside["res"]["A"] is None:
        H["verdict"] = "dawn closure not computable (a side did not fit)"
        return H, rows
    A_n = compose(nside["res"]["A"], A_pre)
    med, mx = closure(A_n, dside["res"]["A"], fit_points(labels, morning))
    H.update({"dawn_night_frame": f"{nside['time']:%Y-%m-%d %H:%M:%S}", "dawn_night_status": nside["res"]["status"],
              "dawn_day_frame": f"{dside['time']:%Y-%m-%d %H:%M:%S}", "dawn_day_status": dside["res"]["status"],
              "dawn_gap_s": round((dside["time"] - nside["time"]).total_seconds(), 1),
              "closure_med_px": round(med, 2), "closure_max_px": round(mx, 2)})
    for side, A, tag in ((nside, A_n, "dawn_night"), (dside, dside["res"]["A"], "dawn_day")):
        save_overlay(run, side["img"], labels, A, side["time"].date(), f"{cam} {tag} {side['time']:%m-%d %H:%M:%S} "
                     f"{side['res']['status']} closure {med:.1f}/{mx:.1f}px", side["res"].get("dropped", {}),
                     f"{cam}_{side['time']:%Y%m%d_%H%M%S}_{tag}.jpg")
    ok = (med <= CLOSURE_MAX and pre["res"]["status"] == "ok" and nside["res"]["status"] == "ok"
          and dside["res"]["status"] == "ok")
    H["verdict"] = "PASS" if ok else "FAIL"
    return H, rows


def write_report(run: Path, cohort: str, night: date, H: list[dict], R: list[dict]) -> Path:
    import output_paths as op
    rep = op.report_dir(cohort, "cv_field")
    f2 = lambda v: "-" if v is None or (isinstance(v, float) and not np.isfinite(v)) else (f"{v:.2f}" if isinstance(v, float) else str(v))  # noqa: E731
    L = [f"# Night reference by dusk hand-off + dawn closure (cohort `{cohort}`, night {night} -> {night + timedelta(days=1)})\n",
         f"Generated {datetime.now():%Y-%m-%d %H:%M} by `cv/cv_field/landmark_night.py` (method and definitions in its docstring). "
         f"Bulk: `{run}` (brightness plots/CSVs, frames, overlays, `handoff.csv`, `night_frames.csv`). Test plan agreed with the "
         "user 2026-10-01: pass = dawn closure median <= 2 px with all three fits ok; the user reviews the 03:01 overlays. "
         "**This report makes no visual claim.**\n",
         "## Hand-off and dawn closure\n",
         "| camera | dusk switch (pre -> post) | z / z2 | pre frame (status, held px) | night ref | sat pre / ref | dawn switch | dawn frames (night / day, gap s) | closure median / max px | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for h in H:
        L.append(f"| {h['camera']} | {h.get('dusk_pre', '-')[11:]} -> {h.get('dusk_post', '-')[11:]} | {f2(h.get('dusk_z'))} / "
                 f"{f2(h.get('dusk_z2'))} | {h.get('pre_frame', '-')[11:]} ({h.get('pre_status', '-')}, {f2(h.get('pre_held_med_px'))}) | "
                 f"{h.get('night_ref', '-')[11:]} | {f2(h.get('sat_pre'))} / {f2(h.get('sat_nightref'))} | "
                 f"{h.get('dawn_pre', '-')[11:]} -> {h.get('dawn_post', '-')[11:]} | {h.get('dawn_night_frame', '-')[11:]} "
                 f"({h.get('dawn_night_status', '-')}) / {h.get('dawn_day_frame', '-')[11:]} ({h.get('dawn_day_status', '-')}), "
                 f"{f2(h.get('dawn_gap_s'))} | {f2(h.get('closure_med_px'))} / {f2(h.get('closure_max_px'))} | **{h.get('verdict')}** |")
    L += ["\n## Night frames (tracked from the night reference; shift vs the 09-18 reference)\n",
          "| camera | frame | status | fit units | held-out median / p90 px | tx px | ty px | rot deg | scale | dropped | overlay |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in R:
        L.append(f"| {r['camera']} | {r['frame_time']} | {r['status']} | {r['n_fit_units']} | {f2(r['held_med_px'])} / "
                 f"{f2(r['held_p90_px'])} | {r['tx']:+.1f} | {r['ty']:+.1f} | {r['rot_deg']:+.3f} | {(r['sx'] + r['sy']) / 2:.4f} | "
                 f"{r['n_dropped']} | `overlays/{r['overlay']}` |")
    L.append("\nOverlays: red = the 09-18 labels as drawn, green = fit units moved by the total map, cyan = houses "
             "(validation), orange = occludable pieces dropped in that frame; nails are circles. sat = mean HSV saturation "
             "(IR / monochrome ~0-6, colour > 12).")
    out = rep / f"cv_field_landmark_night_{cohort}.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    (rep / f"run_manifest_landmark_night_{cohort}.json").write_text(json.dumps(
        {"run_dir": str(run.resolve()), "cohort": cohort, "direction": "cv_field", "analysis": "landmark_night",
         "night": str(night), "report": out.name}, indent=2) + "\n", encoding="utf-8")
    return out


def selftest() -> int:
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

    t0 = datetime(2026, 9, 3, 19, 0)
    rng = np.random.default_rng(0)
    m = np.r_[np.linspace(60, 30, 300), [45, 80], np.full(200, 95.0)] + rng.normal(0, 0.2, 502)
    ser = [(t0 + timedelta(seconds=2 * k), float(v), None, 2.0 * k) for k, v in enumerate(m)]
    sw = find_switch(ser)
    rec("switch: ramp of two keyframes found", sw and sw["t_pre"] == ser[299][0] and sw["t_post"] == ser[302][0] and sw["clear"],
        f"(pre {sw['t_pre']:%H:%M:%S}, post {sw['t_post']:%H:%M:%S}, z {sw['z']:.0f})" if sw else "")
    A1 = np.array([[1.001, 0.004, 5.0], [-0.004, 0.999, -3.0]])
    A2 = np.array([[0.998, -0.002, -1.5], [0.002, 1.002, 2.0]])
    P = rng.uniform(0, 4000, (20, 2))
    rec("compose = sequential application", np.allclose(apply(compose(A2, A1), P), apply(A2, apply(A1, P))))
    rec("closure of a map with itself = 0", closure(A1, A1, P)[1] < 1e-9)
    mv = move_labels({"POLE_A0_L": [[[0, 0], [0, 100]]], "HOUSE_1_ROOF_X": [[[5, 5], [50, 5]]]}, A1, date(2026, 9, 4))
    rec("move_labels keeps pieces, drops house_1 before 09-18", list(mv) == ["POLE_A0_L"] and len(mv["POLE_A0_L"][0]) == 2)
    ffmpeg, _ = gf.find_ffmpeg()
    with tempfile.TemporaryDirectory() as tmp:
        clip = Path(tmp) / "step.mp4"
        subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x202020:s=64x64:r=10:d=12", "-f", "lavfi",
                        "-i", "color=c=0xa0a0a0:s=64x64:r=10:d=8", "-filter_complex", "[0][1]concat=n=2:v=1",
                        "-c:v", "libx264", "-g", "10", "-keyint_min", "10", "-sc_threshold", "0", "-pix_fmt", "yuv420p",
                        str(clip)], check=True)
        kb = keyframe_brightness(ffmpeg, clip, 0.0, 30.0)
        sw2 = find_switch([(t0 + timedelta(seconds=p), v, clip, p) for p, v in kb])
        rec("keyframe brightness from a real clip: 20 keyframes, step between 11 and 12 s",
            len(kb) == 20 and sw2 is not None and abs((sw2["t_post"] - t0).total_seconds() - 12.0) < 0.05
            and abs((sw2["t_pre"] - t0).total_seconds() - 11.0) < 0.05, f"({len(kb)} keyframes)")
    print(("PASS" if ok else "FAIL") + " — landmark_night self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--night", type=date.fromisoformat, help="date of the DUSK (the night runs to the next morning)")
    ap.add_argument("--cameras", nargs="+", default=["CH01", "CH02", "CH03", "CH04"])
    ap.add_argument("--night-times", nargs="+", type=lambda s: datetime.strptime(s, "%H:%M").time(),
                    default=[time(21, 0), time(0, 0), time(3, 1)])
    ap.add_argument("--labels-dir", default=str(REPO / "cv" / "configs" / "landmarks" / "2026c"))
    ap.add_argument("--cohort-root", default=r"F:\3rd_rat")
    ap.add_argument("--ref-session", default=r"F:\calibration\session_2026-09-18_13-54-34")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.night is None:
        ap.error("--night is required")
    import camera_review as cr
    import output_paths as op
    args.session = None
    cohort = op.resolve_cohort(args.cohort)
    run = op.run_dir("cv_field_landmark_night", cohort, make_figures=False)
    (run / "frames").mkdir(parents=True, exist_ok=True)
    (run / "overlays").mkdir(exist_ok=True)
    ff, ffmpeg_cr = gf.find_ffmpeg(), cr.find_ffmpeg()
    H, R = [], []
    for cam in args.cameras:
        print(f"{cam}:")
        h, rows = run_camera(cam, args.night, args, run, ff, ffmpeg_cr)
        print(f"  -> {h.get('verdict')}  closure {h.get('closure_med_px', '-')} / {h.get('closure_max_px', '-')} px")
        H.append(h)
        R += rows
    for name, rows in (("handoff.csv", H), ("night_frames.csv", R)):
        if rows:
            keys = list(dict.fromkeys(k for r in rows for k in r))
            with open(run / name, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                w.writerows(rows)
    out = write_report(run, cohort, args.night, H, R)
    print(f"report -> {out}\nbulk -> {run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
