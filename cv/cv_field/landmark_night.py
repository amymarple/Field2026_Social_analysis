"""landmark_night.py — automatic NIGHT reference for the rigid-landmark tracking: dusk chain + dawn closure check.

Why: the structures do not move, but at night the camera's own IR illuminator lights the scene, so the daytime
appearance around each landmark in the 09-18 reference does not match night frames and landmark_track.py fails there.
Instead of labelling a night frame per camera, the night reference is made automatically (plan agreed with the user,
2026-10-01; implementation_plan/2026-09-28-cohort3-camera-stability.md, revision 3):

  1. Dusk chain: frames every CHAIN_STEP_MIN from DUSK_START to NIGHT_START. Each is tracked DIRECTLY from the 09-18
     labelled reference (landmark_track.track_frame) while that gives status ok; from the first failure on, frames are
     tracked from an ANCHOR (a LINK: the best direct frame of the last ANCHOR_WINDOW_MIN as reference, its labels = the
     09-18 labels moved by its map)
     -> A_k = T_k o A_anchor; the anchor moves to the last good frame only when a link from it fails (errors add up per
     anchor change, not per frame). The NIGHT_START frame is the night reference (its map A_night from 09-18).
  2. Night frames (default 00:00, 03:01) are tracked from the night reference -> A_total = A_n o A_night, reported like
     the daytime track (tx, ty, rot, scale from landmark_track.params).
  3. Dawn closure: frames every CHAIN_STEP_MIN from DAWN_START to DAWN_END are chained FORWARD from the night reference
     (night side) and also tracked DIRECTLY from 09-18 (day side). At the first CLOSURE_N dawn frames where the direct
     track is ok:  closure = median / max over the 09-18 fit-set label points p of |A_chain p - A_direct p|  [px].
     PASS if the MEDIAN over those first CLOSURE_N frames of their median closure is <= CLOSURE_MAX px and the night
     frames are ok (user, 2026-10-02: 3 px; the first rule — first frame <= 2 px — failed nights on single dim-dawn
     direct fits, and 3 px is < 1 cm in the panoramas, far below the calibration's own 76-mm median error). The loop
     09-18 -> dusk chain -> night -> dawn chain vs 09-18 directly checks the night maps without labels.
Rejected first version (same day): a hand-off at the "illuminator switch" found as the largest keyframe brightness jump —
the largest jumps are one-keyframe spikes near stream restarts, and dusk has no abrupt step (only dawn: one at ~07:25 on
all four cameras); see change_log/2026-09-28-cohort3-camera-stability.md.
Definitions: link = one frame tracked from the previous good frame; drift grows with the number of links, which the
dawn closure measures. The agent makes no visual judgement: the user reviews the overlays.

Usage: python cv/cv_field/landmark_night.py --cohort 2026c --nights 2026-09-03 [2026-09-04 ...] [--cameras CH01 CH02]
                                            [--night-times 00:00 03:01]
       python cv/cv_field/landmark_night.py --cohort 2026c --report-only <run folder>   # re-judge an earlier run
       python cv/cv_field/landmark_night.py --selftest          # offline, synthetic frames
Output: $FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/cv_field_landmark_night_<ts>/ (frames, overlays, chain.csv,
        night_frames.csv, closure.csv) and results/<cohort>/cv_field/reports/cv_field_landmark_night_<cohort>.md +
        run_manifest_landmark_night_<cohort>.json (own pointer, so landmark_track's run_manifest.json survives).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import grab_frames as gf  # noqa: E402
import landmark_track as lt  # noqa: E402

DUSK_START, NIGHT_START = time(18, 30), time(21, 0)      # early September, Ithaca: sunset ~19:30 EDT (field-PC time)
DAWN_START, DAWN_END = time(5, 30), time(8, 0)           # sunrise ~06:40; the dawn brightness step is at ~07:25
CHAIN_STEP_MIN = 5
CLOSURE_MAX, CLOSURE_N = 3.0, 3                           # pass: median of the first 3 closure frames <= 3 px (user, 2026-10-02)
# Anchor = the BEST direct frame of the last ANCHOR_WINDOW_MIN (lowest held-out p90 among those with >= ANCHOR_UNITS of
# the most units seen), not the last one: on 09-09 rain from 19:10 degraded the direct fits and the last "ok" frame
# (held-out 2.94 px, 15 of 20 units) carried its error into the whole night (dawn closure 19.5 px).
ANCHOR_WINDOW_MIN, ANCHOR_UNITS = 30, 0.9
MAX_LINK_FAILS = 3


def frame_times(day: date, t0: time, t1: time, step_min: int = CHAIN_STEP_MIN) -> list[datetime]:
    a, b = datetime.combine(day, t0), datetime.combine(day, t1)
    out = []
    while a <= b:
        out.append(a)
        a += timedelta(minutes=step_min)
    return out


def apply(A: np.ndarray, P: np.ndarray) -> np.ndarray:
    return P @ A[:, :2].T + A[:, 2]


def move_labels(landmarks: dict, A: np.ndarray, day: date) -> dict:
    """The 09-18 labels moved by A (pieces and names kept), only those usable on `day`."""
    return {n: [apply(A, p).tolist() for p in lt.pieces_of(v)] for n, v in landmarks.items() if lt.usable(n, day)}


def fit_points(landmarks: dict, day: date) -> np.ndarray:
    return np.vstack([p for n, v in landmarks.items() if lt.in_fit(n) and lt.usable(n, day) for p in lt.pieces_of(v)])


def closure(A1: np.ndarray, A2: np.ndarray, P: np.ndarray) -> tuple[float, float]:
    e = np.hypot(*(apply(A1, P) - apply(A2, P)).T)
    return float(np.median(e)), float(e.max())


class Chain:
    """Maps 09-18 px -> frame px along a sequence of frames: DIRECT from 09-18 while allowed and ok; otherwise from the
    current ANCHOR frame (the last direct frame, or the night reference). Only when the anchor fails is it moved to the
    last good frame, so errors accumulate per anchor change, not per frame (each link under-measures a sub-pixel shift a
    little; chaining every 5-min frame would add that up)."""

    def __init__(self, ref_g, labels, kinds, start=None):
        self.ref_g, self.labels, self.kinds = ref_g, labels, kinds
        self.anchor = self.last_good = start   # (frame_g, A 09-18 -> frame, day)
        self.rows, self.fails, self.anchor_changes = [], 0, 0
        self.direct_hist = []                  # (time, frame_g, A, day, held_p90, n_units) of direct-ok frames

    def best_anchor(self, t: datetime):
        recent = [h for h in self.direct_hist if (t - h[0]).total_seconds() <= 60 * ANCHOR_WINDOW_MIN]
        if not recent:
            return None
        nmax = max(h[5] for h in recent)
        good = [h for h in recent if h[5] >= ANCHOR_UNITS * nmax] or recent
        return min(good, key=lambda h: h[4])

    def _from(self, anc, img_g, t):
        ag, aA, aday = anc
        r = lt.track_frame(ag, img_g, move_labels(self.labels, aA, aday), self.kinds, t.date(), ref_day=t.date())
        return r, (lt.compose(r["A"], aA) if r.get("status") == "ok" else None)

    def step(self, img_g, t: datetime, direct: bool) -> dict:
        row = {"time": f"{t:%Y-%m-%d %H:%M:%S}", "mode": "", "status": "", "held_med_px": np.nan, "held_p90_px": np.nan,
               "n_fit_units": 0, "anchor_changes": self.anchor_changes, "anchor": "", "A": None}
        if direct:
            r = lt.track_frame(self.ref_g, img_g, self.labels, self.kinds, t.date())
            if r.get("status") == "ok":
                row.update(mode="direct", status="ok", held_med_px=r["held_med"], held_p90_px=r["held_p90"],
                           n_fit_units=len(r["fit_names"]), A=r["A"])
                self.direct_hist.append((t, img_g, r["A"], t.date(), r["held_p90"], len(r["fit_names"])))
                b = self.best_anchor(t)
                self.anchor = (b[1], b[2], b[3])
                self.anchor_time = b[0]
                self.last_good = (img_g, r["A"], t.date())
                self.fails = 0
                self.rows.append(row)
                return row
        if self.anchor is None:
            row.update(mode="direct", status="unreliable")
            self.rows.append(row)
            return row
        r, A = self._from(self.anchor, img_g, t)
        mode = "link"
        if A is None and self.last_good is not None and self.last_good is not self.anchor:
            self.anchor = self.last_good                       # move the anchor to the last good frame and retry
            self.anchor_time = None
            self.anchor_changes += 1
            r, A = self._from(self.anchor, img_g, t)
            mode = "relink"
        row.update(mode=mode, status=r.get("status", "no fit"), held_med_px=r.get("held_med", np.nan),
                   held_p90_px=r.get("held_p90", np.nan), n_fit_units=len(r["fit_names"]),
                   anchor_changes=self.anchor_changes, A=A,
                   anchor=f"{getattr(self, 'anchor_time', None):%H:%M}" if getattr(self, "anchor_time", None) else "")
        if A is not None:
            self.last_good, self.fails = (img_g, A, t.date()), 0
        else:
            self.fails += 1
        self.rows.append(row)
        return row


def grab_all(times: list[datetime], cam: str, root: Path, ff, out: Path, tag: str) -> dict:
    """Grab frames in parallel to disk; -> {target time: (jpg path, frame time)}."""
    def one(t):
        r = gf.grab_one({"camera": cam, "time": t, "tag": tag}, root, ff[0], ff[1], "exact", "cpu", out)
        r.pop("_img", None)
        return t, r
    got = {}
    with ThreadPoolExecutor(3) as ex:
        for t, r in ex.map(one, times):
            if not r["error"] and r["frame_time"]:
                got[t] = (out / r["out"], datetime.strptime(r["frame_time"][:19], "%Y-%m-%d %H:%M:%S"))
    return got


def save_overlay(run: Path, img, labels, A, day, caption, dropped, name) -> str:
    ov = lt.draw_overlay(img, labels, A, day, caption, dropped)
    s = 2400 / ov.shape[1]
    cv2.imwrite(str(run / "overlays" / name), cv2.resize(ov, None, fx=s, fy=s, interpolation=cv2.INTER_AREA),
                [cv2.IMWRITE_JPEG_QUALITY, 88])
    return name


def run_night(cam: str, night: date, args, run: Path, ff, ref_g, labels, kinds, size) -> tuple[dict, list, list]:
    root = Path(args.cohort_root)
    frames = run / "frames"
    morning = night + timedelta(days=1)
    H = {"camera": cam, "night": f"{night}"}
    # 1. dusk chain
    dusk_t = frame_times(night, DUSK_START, NIGHT_START)
    got = grab_all(dusk_t, cam, root, ff, frames, "dusk")
    ch = Chain(ref_g, labels, kinds)
    chained = False
    last = None
    for t in dusk_t:
        if t not in got:
            continue
        img = cv2.imread(str(got[t][0]))
        row = ch.step(lt.prep(img), got[t][1], direct=not chained)
        chained |= row["mode"] in ("link", "relink")
        if row["A"] is not None:
            last = (img, row["A"], got[t][1])
        if ch.fails >= MAX_LINK_FAILS:
            break
    links = [r for r in ch.rows if r["mode"] in ("link", "relink")]
    direct_ok = [r for r in ch.rows if r["mode"] == "direct" and r["status"] == "ok"]
    H.update({"dusk_frames": len(ch.rows), "dusk_direct_until": direct_ok[-1]["time"][11:16] if direct_ok else "-",
              "dusk_links": len(links), "dusk_links_failed": sum(r["status"] != "ok" for r in links),
              "dusk_anchor_changes": ch.anchor_changes})
    chain_rows = [{"camera": cam, "night": f"{night}", "phase": "dusk", **{k: v for k, v in r.items() if k != "A"}} for r in ch.rows]
    if last is None or abs((last[2] - datetime.combine(night, NIGHT_START)).total_seconds()) > 60 * CHAIN_STEP_MIN or \
            ch.fails >= MAX_LINK_FAILS:
        H["verdict"] = "dusk chain broken"
        return H, chain_rows, []
    night_img, A_night, night_t = last
    H["night_ref"] = f"{night_t:%Y-%m-%d %H:%M:%S}"
    n_g = lt.prep(night_img)
    nlabels = move_labels(labels, A_night, night_t.date())
    save_overlay(run, night_img, labels, A_night, night_t.date(), f"{cam} NIGHT REF {night_t:%m-%d %H:%M} (end of dusk chain)",
                 {}, f"{cam}_{night_t:%Y%m%d_%H%M%S}_night_ref.jpg")
    # 2. night frames
    rows = []
    nt = [datetime.combine(night if tt >= time(12, 0) else morning, tt) for tt in args.night_times]
    got_n = grab_all(nt, cam, root, ff, frames, "night")
    for t in nt:
        if t not in got_n:
            continue
        img = cv2.imread(str(got_n[t][0]))
        ft = got_n[t][1]
        res = lt.track_frame(n_g, lt.prep(img), nlabels, kinds, ft.date(), ref_day=ft.date())
        A_tot = lt.compose(res["A"], A_night) if res["A"] is not None else None
        pr = lt.params(A_tot, size) if A_tot is not None else {k: np.nan for k in ("tx", "ty", "rot_deg", "sx", "sy")}
        cap = (f"{cam} {ft:%m-%d %H:%M} NIGHT (via night ref) {res.get('status')} held {res.get('held_med', np.nan):.1f}/"
               f"{res.get('held_p90', np.nan):.1f}px  vs 09-18 t=({pr['tx']:+.1f},{pr['ty']:+.1f}) rot {pr['rot_deg']:+.2f}")
        ov = save_overlay(run, img, labels, A_tot, ft.date(), cap, res.get("dropped", {}), f"{cam}_{ft:%Y%m%d_%H%M%S}_night.jpg")
        rows.append({"camera": cam, "night": f"{night}", "frame_time": f"{ft:%Y-%m-%d %H:%M:%S}", "status": res.get("status", "no fit"),
                     "n_fit_units": len(res["fit_names"]), "held_med_px": res.get("held_med", np.nan),
                     "held_p90_px": res.get("held_p90", np.nan), **pr, "n_dropped": len(res.get("dropped", {})), "overlay": ov})
        print(f"  {cap}")
    # 3. dawn: chain forward from the night reference + direct from 09-18 -> closure
    dawn_t = frame_times(morning, DAWN_START, DAWN_END)
    got_d = grab_all(dawn_t, cam, root, ff, frames, "dawn")
    chn = Chain(ref_g, labels, kinds, start=(n_g, A_night, night_t.date()))
    pts = fit_points(labels, morning)
    clos = []
    for t in dawn_t:
        if t not in got_d:
            continue
        img = cv2.imread(str(got_d[t][0]))
        g = lt.prep(img)
        ft = got_d[t][1]
        rc = chn.step(g, ft, direct=False)                           # night side: always a link
        rd = lt.track_frame(ref_g, g, labels, kinds, ft.date())      # day side: direct from 09-18
        chain_rows.append({"camera": cam, "night": f"{night}", "phase": "dawn", **{k: v for k, v in rc.items() if k != "A"},
                           "direct_status": rd.get("status"), "direct_held_med_px": rd.get("held_med", np.nan)})
        if rc["A"] is not None and rd.get("status") == "ok":
            med, mx = closure(rc["A"], rd["A"], pts)
            clos.append({"camera": cam, "night": f"{night}", "time": f"{ft:%Y-%m-%d %H:%M:%S}", "closure_med_px": med,
                         "closure_max_px": mx, "chain_links": sum(r["mode"] in ("link", "relink") for r in chn.rows),
                         "anchor_changes": chn.anchor_changes})
            if len(clos) == 1:
                for A, tag in ((rc["A"], "dawn_chain"), (rd["A"], "dawn_direct")):
                    save_overlay(run, img, labels, A, ft.date(), f"{cam} {tag} {ft:%m-%d %H:%M} closure {med:.1f}/{mx:.1f}px",
                                 {}, f"{cam}_{ft:%Y%m%d_%H%M%S}_{tag}.jpg")
            if len(clos) >= CLOSURE_N:
                break
        if chn.fails >= MAX_LINK_FAILS:
            break
    if not clos:
        H["verdict"] = "no closure (dawn chain broken or no direct fit)"
        return H, chain_rows, rows
    H.update({"closure_time": clos[0]["time"][11:16], "closure_med_px": round(clos[0]["closure_med_px"], 2),
              "closure_max_px": round(clos[0]["closure_max_px"], 2),
              "closure_med_next_px": round(float(np.median([c["closure_med_px"] for c in clos])), 2),
              "dawn_links": clos[0]["chain_links"], "dawn_anchor_changes": clos[0]["anchor_changes"]})
    H["verdict"] = verdict(H["closure_med_next_px"], rows)
    return H, chain_rows, rows


def verdict(closure_med3: float, night_rows: list[dict]) -> str:
    """PASS = median closure of the first CLOSURE_N dawn frames <= CLOSURE_MAX px and every night frame ok."""
    ok = closure_med3 <= CLOSURE_MAX and bool(night_rows) and all(r["status"] == "ok" for r in night_rows)
    return "PASS" if ok else "FAIL"


def rerender(run: Path, cohort: str) -> Path:
    """Rebuild the report of an earlier run from its CSVs with the current pass rule (no frames re-read)."""
    def num(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return v
        return int(f) if str(v).lstrip("-").isdigit() else f
    H = [{k: num(v) if k not in ("camera", "night", "night_ref", "closure_time", "verdict", "dusk_direct_until") else v
          for k, v in r.items()} for r in csv.DictReader(open(run / "handoff.csv", encoding="utf-8"))]
    R = [{k: num(v) for k, v in r.items()} for r in csv.DictReader(open(run / "night_frames.csv", encoding="utf-8"))]
    for h in H:
        if isinstance(h.get("closure_med_next_px"), float):
            h["verdict"] = verdict(h["closure_med_next_px"], [r for r in R if r["camera"] == h["camera"] and r["night"] == h["night"]])
    nights = sorted({date.fromisoformat(h["night"]) for h in H if h.get("night", "-") != "-"})
    return write_report(run, cohort, nights, H, R)


def write_report(run: Path, cohort: str, nights: list[date], H: list[dict], R: list[dict]) -> Path:
    import output_paths as op
    rep = op.report_dir(cohort, "cv_field")
    f2 = lambda v: "-" if v is None or (isinstance(v, float) and not np.isfinite(v)) else (f"{v:.2f}" if isinstance(v, float) else str(v))  # noqa: E731
    L = [f"# Night reference by dusk chain + dawn closure (cohort `{cohort}`, nights {', '.join(str(n) for n in nights)})\n",
         f"Generated {datetime.now():%Y-%m-%d %H:%M} by `cv/cv_field/landmark_night.py` (method and definitions in its "
         f"docstring). Bulk: `{run}` (frames, overlays, `chain.csv`, `night_frames.csv`, `closure.csv`). Pass = the median of "
         f"the first {CLOSURE_N} dawn closure frames <= {CLOSURE_MAX} px with every night frame ok (user, 2026-10-02; the first "
         "rule, first frame <= 2 px, is superseded). **This report makes no visual claim.**\n",
         f"Summary: " + "; ".join(f"{c} {sum(h.get('verdict') == 'PASS' for h in H if h['camera'] == c)}/"
                                    f"{sum(h['camera'] == c for h in H)} nights pass" for c in sorted({h['camera'] for h in H})) + ".\n",
         "## Per camera and night\n",
         "| camera | night | dusk: direct until / links (failed, anchor changes) | night ref | dawn links (anchor changes) | closure at (median / max px; median of first 3) | verdict |",
         "|---|---|---|---|---|---|---|"]
    for h in H:
        L.append(f"| {h['camera']} | {h['night']} | {h.get('dusk_direct_until', '-')} / {h.get('dusk_links', '-')} "
                 f"({h.get('dusk_links_failed', '-')}, {h.get('dusk_anchor_changes', '-')}) | {h.get('night_ref', '-')[11:16]} | "
                 f"{h.get('dawn_links', '-')} ({h.get('dawn_anchor_changes', '-')}) | "
                 f"{h.get('closure_time', '-')} ({f2(h.get('closure_med_px'))} / {f2(h.get('closure_max_px'))}; "
                 f"{f2(h.get('closure_med_next_px'))}) | **{h.get('verdict')}** |")
    L += ["\n## Night frames (tracked from the night reference; shift vs the 09-18 reference)\n",
          "| camera | frame | status | fit units | held-out median / p90 px | tx px | ty px | rot deg | scale | overlay |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in R:
        L.append(f"| {r['camera']} | {r['frame_time']} | {r['status']} | {r['n_fit_units']} | {f2(r['held_med_px'])} / "
                 f"{f2(r['held_p90_px'])} | {r['tx']:+.1f} | {r['ty']:+.1f} | {r['rot_deg']:+.3f} | {(r['sx'] + r['sy']) / 2:.4f} | "
                 f"`overlays/{r['overlay']}` |")
    L.append("\nOverlays: red = the 09-18 labels as drawn, green = fit units moved by the total map, cyan = houses "
             "(validation), orange = occludable pieces dropped in that frame; nails are circles.")
    out = rep / f"cv_field_landmark_night_{cohort}.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    (rep / f"run_manifest_landmark_night_{cohort}.json").write_text(json.dumps(
        {"run_dir": str(run.resolve()), "cohort": cohort, "direction": "cv_field", "analysis": "landmark_night",
         "nights": [str(n) for n in nights], "report": out.name}, indent=2) + "\n", encoding="utf-8")
    return out


def selftest() -> int:
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

    rng = np.random.default_rng(3)
    h, w = 700, 1300
    day = cv2.GaussianBlur((rng.random((h, w)) * 90).astype(np.uint8), (0, 0), 2)
    night = cv2.GaussianBlur((rng.random((h, w)) * 90).astype(np.uint8), (0, 0), 2)      # other texture = other light
    for im in (day, night):
        for x in (250, 600, 1000):
            cv2.line(im, (x, 100), (x + 8, 600), 250, 9)
        cv2.line(im, (80, 330), (1220, 315), 230, 5)
        cv2.rectangle(im, (650, 160), (720, 210), 255, -1)
    labels = {"POLE_A0_L": [[[246, 140], [254, 560]]], "POLE_A1_L": [[[596, 140], [604, 560]]],
              "POLE_A2_L": [[[996, 140], [1004, 560]]], "WALLTOP_Y0": [[[120, 329], [1180, 316]]],
              "BOX_A1": [[[650, 160], [720, 160], [720, 210], [650, 210]]]}
    kinds = {"POLE_A0_L": "edge", "POLE_A1_L": "edge", "POLE_A2_L": "edge", "WALLTOP_Y0": "polyline", "BOX_A1": "outline"}

    def frame(k, alpha):                       # camera drifts 0.4 px / step right, 0.2 px up; appearance day -> night
        M = np.array([[1, 0, 0.4 * k], [0, 1, -0.2 * k]], float)
        im = cv2.addWeighted(day, 1 - alpha, night, alpha, 0)
        return cv2.warpAffine(cv2.cvtColor(im, cv2.COLOR_GRAY2BGR), M, (w, h), borderMode=cv2.BORDER_REFLECT), M
    ref_g = lt.prep(cv2.cvtColor(day, cv2.COLOR_GRAY2BGR))
    ch = Chain(ref_g, labels, kinds)
    t0 = datetime(2026, 9, 3, 18, 30)
    chained = False
    alphas = list(np.linspace(0, 1, 8)) + [1.0] * 3 + list(np.linspace(1, 0, 8))
    out = []
    for k, a in enumerate(alphas):
        im, M = frame(k, a)
        r = ch.step(lt.prep(im), t0 + timedelta(minutes=5 * k), direct=not chained if k < 11 else False)
        chained |= r["mode"] in ("link", "relink")
        out.append((r, M))
    errs = [float(np.abs(apply(r["A"], np.array([[650.0, 350.0]])) - apply(M, np.array([[650.0, 350.0]]))).max())
            for r, M in out if r["A"] is not None]
    rec("chain: every step mapped, end-to-end error small", len(errs) == len(alphas) and max(errs) < 0.6,
        f"({len(errs)}/{len(alphas)} mapped, max error {max(errs) if errs else np.inf:.2f} px, "
        f"{sum(r['mode'] != 'direct' for r, _ in out)} linked, {ch.anchor_changes} anchor changes)")
    rd = lt.track_frame(ref_g, lt.prep(frame(len(alphas) - 1, 0.0)[0]), labels, kinds, date(2026, 9, 4))
    med, mx = closure(out[-1][0]["A"], rd["A"], fit_points(labels, date(2026, 9, 4)))
    rec("closure of the chain vs a direct fit at the end", med < 0.6, f"({med:.2f} / {mx:.2f} px)")
    A1 = np.array([[1.001, 0.004, 5.0], [-0.004, 0.999, -3.0]])
    mv = move_labels({"POLE_A0_L": [[[0, 0], [0, 100]]], "HOUSE_1_ROOF_X": [[[5, 5], [50, 5]]]}, A1, date(2026, 9, 4))
    rec("move_labels keeps pieces, drops house_1 before 09-18", list(mv) == ["POLE_A0_L"] and len(mv["POLE_A0_L"][0]) == 2)
    rec("frame times every 5 min, both ends", len(frame_times(date(2026, 9, 3), DUSK_START, NIGHT_START)) == 31)
    c = Chain(None, {}, {})
    t1 = datetime(2026, 9, 9, 19, 0)
    c.direct_hist = [(t1 - timedelta(minutes=45), "old", None, None, 0.5, 20), (t1 - timedelta(minutes=20), "best", None, None, 2.4, 20),
                     (t1 - timedelta(minutes=10), "fewunits", None, None, 1.0, 15), (t1, "last", None, None, 5.6, 20)]
    rec("anchor = lowest p90 of the last 30 min among frames with >= 90 % of the units", c.best_anchor(t1)[1] == "best")
    print(("PASS" if ok else "FAIL") + " — landmark_night self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--nights", nargs="+", type=date.fromisoformat, help="dates of the DUSK (each night runs to the next morning)")
    ap.add_argument("--cameras", nargs="+", default=["CH01", "CH02"])
    ap.add_argument("--night-times", nargs="+", type=lambda s: datetime.strptime(s, "%H:%M").time(),
                    default=[time(0, 0), time(3, 1)])
    ap.add_argument("--labels-dir", default=str(REPO / "cv" / "configs" / "landmarks" / "2026c"))
    ap.add_argument("--cohort-root", default=r"F:\3rd_rat")
    ap.add_argument("--ref-session", default=r"F:\calibration\session_2026-09-18_13-54-34")
    ap.add_argument("--report-only", default=None, help="rebuild the report of this run folder from its CSVs (current rule)")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.report_only:
        import output_paths as op
        out = rerender(Path(args.report_only), op.resolve_cohort(args.cohort))
        print(f"report -> {out}")
        return 0
    if not args.nights:
        ap.error("--nights is required")
    import camera_review as cr
    import output_paths as op
    args.session = None
    cohort = op.resolve_cohort(args.cohort)
    run = op.run_dir("cv_field_landmark_night", cohort, make_figures=False)
    (run / "frames").mkdir(parents=True, exist_ok=True)
    (run / "overlays").mkdir(exist_ok=True)
    ff = gf.find_ffmpeg()
    H, C, R = [], [], []
    for cam in args.cameras:
        lab = json.loads(sorted(Path(args.labels_dir).glob(f"landmarks_{cam}_20260918_*.json"))[0].read_text(encoding="utf-8"))
        labels, kinds = lab["landmarks"], lab.get("kind", {})
        size = tuple(int(v) for v in lab["frame_size_upright"])
        got = cr.grab_at(datetime.strptime(lab["time"], "%Y-%m-%d %H:%M:%S"), cam, args, cr.find_ffmpeg(), size)
        if got is None:
            H.append({"camera": cam, "night": "-", "verdict": "no 09-18 reference frame"})
            continue
        ref_g = lt.prep(got[0])
        for night in args.nights:
            print(f"{cam} night {night}:")
            h, c, rows = run_night(cam, night, args, run, ff, ref_g, labels, kinds, size)
            print(f"  -> {h.get('verdict')}  closure {h.get('closure_med_px', '-')} / {h.get('closure_max_px', '-')} px")
            H.append(h)
            C += c
            R += rows
    for name, rows in (("handoff.csv", H), ("chain.csv", C), ("night_frames.csv", R)):
        if rows:
            keys = list(dict.fromkeys(k for r in rows for k in r))
            with open(run / name, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                w.writerows(rows)
    out = write_report(run, cohort, args.nights, H, R)
    print(f"report -> {out}\nbulk -> {run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
