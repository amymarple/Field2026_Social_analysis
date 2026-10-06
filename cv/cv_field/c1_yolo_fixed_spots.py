"""c1_yolo_fixed_spots.py — fixed-spot diagnostic of the cached step-2 YOLO v5 detections (cohort-3 CH01 hour).

Plan: implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md, amendment "B" (after results, user-approved 2026-10-05):
the user's review found false positives / negatives that are "very fixed" in place. From the cached detections only (YOLO
is not rerun):
  1. per 40-px cell of the upright 7680 x 2160 pano, occupancy = fraction of the hour's frames with >= 1 box centre
     (conf >= 0.25) in the cell; cells with occupancy >= 5 % joined 8-connected into spots; spot occupancy = fraction of
     frames with a box centre in any of its cells; ranked, all >= 5 %, at most 15. Per spot: median conf, median box
     w x h, box-centre SD, occupancy per minute.
  2. figures for the user (the agent does not interpret them): a 1920 x 540 locator (per-pixel median of 60 frames, one
     per minute) with spot outlines + numbers; an occupancy heatmap on the same scale; per spot native 400 x 400 crops at
     the first / middle / last frame with a spot box and the frame without one nearest the middle (thin boxes, frame time
     and conf printed). Frames decoded with PyAV exactly as in step 2 (pixel-identical to grab_frames.grab).
  3. fixed_spots/index.html, fixed_spots.csv, cells.csv.gz, fixed_spots_review.csv (empty verdicts), fn_notes.txt (stub).
No conclusion about what the spots are is drawn here.

Usage (cv env, PYTHONIOENCODING=utf-8):
  python cv/cv_field/c1_yolo_fixed_spots.py --run <step-2 run dir>
  python cv/cv_field/c1_yolo_fixed_spots.py --selftest      # synthetic detections + synthetic HEVC clip (ffmpeg, PyAV)
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import c1_yolo_video_test as cvt  # noqa: E402

CELL = 40
CONF = 0.25
OCC_MIN = 0.05
MAX_SPOTS = 15
CROP = 400
LOC_SCALE = 4                 # 7680 x 2160 -> 1920 x 540
N_LOC = 60


# ----------------------------------------------------------------------------------------------- spots
def cell_table(det: pd.DataFrame, n_frames: int, w: int = 7680, h: int = 2160, cell: int = CELL, conf: float = CONF):
    """-> (boxes with centre + cell indices, occupancy grid (ny, nx))."""
    d = det[det["conf"] >= conf].copy()
    d["cx"] = (d["x1"] + d["x2"]) / 2
    d["cy"] = (d["y1"] + d["y2"]) / 2
    d["bw"] = d["x2"] - d["x1"]
    d["bh"] = d["y2"] - d["y1"]
    nx, ny = int(np.ceil(w / cell)), int(np.ceil(h / cell))
    d["ix"] = np.clip((d["cx"] // cell).astype(int), 0, nx - 1)
    d["iy"] = np.clip((d["cy"] // cell).astype(int), 0, ny - 1)
    occ = np.zeros((ny, nx))
    u = d[["frame", "iy", "ix"]].drop_duplicates()
    cnt = u.groupby(["iy", "ix"]).size()
    for (iy, ix), c in cnt.items():
        occ[iy, ix] = c / n_frames
    return d, occ


def label8(mask: np.ndarray) -> np.ndarray:
    """8-connected component labels (0 = background, 1..n)."""
    lab = np.zeros(mask.shape, int)
    n = 0
    ny, nx = mask.shape
    for y0, x0 in zip(*np.nonzero(mask)):
        if lab[y0, x0]:
            continue
        n += 1
        stack = [(y0, x0)]
        lab[y0, x0] = n
        while stack:
            y, x = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < ny and 0 <= xx < nx and mask[yy, xx] and not lab[yy, xx]:
                        lab[yy, xx] = n
                        stack.append((yy, xx))
    return lab


def nearest_without(frames_with: np.ndarray, target: int, n_frames: int) -> int | None:
    has = np.zeros(n_frames, bool)
    has[frames_with] = True
    if has.all():
        return None
    for d in range(n_frames):
        for k in (target - d, target + d):
            if 0 <= k < n_frames and not has[k]:
                return int(k)
    return None


def find_spots(d: pd.DataFrame, occ: np.ndarray, frames: pd.DataFrame, cell: int = CELL, occ_min: float = OCC_MIN,
               max_spots: int = MAX_SPOTS) -> tuple[list[dict], np.ndarray]:
    n_frames = len(frames)
    lab = label8(occ >= occ_min)
    minute = np.clip((frames["pts_s"].to_numpy(float) // 60).astype(int), 0, 59)
    per_min = np.bincount(minute, minlength=60).astype(float)
    spots = []
    for k in range(1, lab.max() + 1):
        cells = set(zip(*np.nonzero(lab == k)))
        sel = d[[(a, b) in cells for a, b in zip(d["iy"], d["ix"])]]
        fw = np.unique(sel["frame"].to_numpy(int))
        m_occ = np.bincount(minute[fw], minlength=60) / np.where(per_min > 0, per_min, 1)
        ys, xs = np.nonzero(lab == k)
        mid = int(fw[len(fw) // 2])
        spots.append({"label": k, "n_cells": len(cells), "occupancy": len(fw) / n_frames, "n_frames_with_box": int(len(fw)),
                      "n_boxes": int(len(sel)), "peak_cell_occupancy": float(occ[lab == k].max()),
                      "cx_median": float(sel["cx"].median()), "cy_median": float(sel["cy"].median()),
                      "cx_sd": float(sel["cx"].std(ddof=0)), "cy_sd": float(sel["cy"].std(ddof=0)),
                      "conf_median": float(sel["conf"].median()), "w_median": float(sel["bw"].median()),
                      "h_median": float(sel["bh"].median()),
                      "cell_x0": int(xs.min() * cell), "cell_y0": int(ys.min() * cell), "cell_x1": int((xs.max() + 1) * cell),
                      "cell_y1": int((ys.max() + 1) * cell),
                      "frame_first": int(fw[0]), "frame_middle": mid, "frame_last": int(fw[-1]),
                      "frame_nobox": nearest_without(fw, mid, n_frames), "minute_occupancy": m_occ.round(4).tolist(),
                      "_cells": cells})
    spots = [s for s in spots if s["occupancy"] >= occ_min]
    spots.sort(key=lambda s: (-s["occupancy"], s["cell_y0"], s["cell_x0"]))
    spots = spots[:max_spots]
    for i, s in enumerate(spots, start=1):
        s["spot_id"] = i
    return spots, lab


# ----------------------------------------------------------------------------------------------- frames + figures
def grab_frame(video: Path, pts: float) -> np.ndarray:
    """One upright BGR frame at exactly this PTS (PyAV, as the step-2 pass; frames can be < 1 ms apart)."""
    key = cvt.pts_key(pts)
    src = cvt.AvFrames(video, start_pts=pts, end_pts=pts + 0.0005, workers=2)
    it = iter(src)
    try:
        for p, img in it:
            if cvt.pts_key(p) == key:
                return img
    finally:
        it.close()
    raise RuntimeError(f"frame at PTS {pts} not found")


def spot_mask(spot: dict, ny: int, nx: int) -> np.ndarray:
    m = np.zeros((ny, nx), np.uint8)
    for iy, ix in spot["_cells"]:
        m[iy, ix] = 255
    return m


def draw_outlines(img: np.ndarray, spots: list[dict], ny: int, nx: int, color, scale_px: float) -> np.ndarray:
    import cv2
    h, w = img.shape[:2]
    for s in spots:
        m = cv2.resize(spot_mask(s, ny, nx), (w, h), interpolation=cv2.INTER_NEAREST)
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(img, cs, -1, color, 1)
        x, y = int(s["cell_x1"] * scale_px) + 2, max(12, int(s["cell_y0"] * scale_px) - 2)
        cv2.putText(img, str(s["spot_id"]), (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(img, str(s["spot_id"]), (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    return img


def locator(frames_imgs: list[np.ndarray], spots, ny, nx, out_w: int, out_h: int) -> np.ndarray:
    import cv2
    small = np.stack([cv2.resize(f, (out_w, out_h), interpolation=cv2.INTER_AREA) for f in frames_imgs])
    med = np.median(small, axis=0).astype(np.uint8)
    return draw_outlines(np.ascontiguousarray(med), spots, ny, nx, (0, 0, 255), out_w / (nx * CELL))


def heatmap(occ: np.ndarray, spots, out_w: int, out_h: int) -> np.ndarray:
    import cv2
    mx = occ.max() if occ.max() > 0 else 1.0
    g = (np.clip(occ / mx, 0, 1) * 255).astype(np.uint8)
    hm = cv2.applyColorMap(cv2.resize(g, (out_w, out_h), interpolation=cv2.INTER_NEAREST), cv2.COLORMAP_INFERNO)
    ny, nx = occ.shape
    hm = draw_outlines(hm, spots, ny, nx, (255, 255, 255), out_w / (nx * CELL))
    txt = f"box-centre occupancy per {CELL}-px cell (conf >= {CONF}), linear 0 .. {mx:.1%}"
    cv2.putText(hm, txt, (8, out_h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return hm


def crop_img(img: np.ndarray, spot: dict, boxes: np.ndarray, label: str, crop: int = CROP) -> np.ndarray:
    import cv2
    h, w = img.shape[:2]
    x0 = int(np.clip(round(spot["cx_median"]) - crop // 2, 0, max(0, w - crop)))
    y0 = int(np.clip(round(spot["cy_median"]) - crop // 2, 0, max(0, h - crop)))
    c = np.ascontiguousarray(img[y0:y0 + crop, x0:x0 + crop].copy())
    for x1, y1, x2, y2, cf in boxes:
        if x2 < x0 or x1 > x0 + crop or y2 < y0 or y1 > y0 + crop:
            continue
        a, b, cc, d = int(x1 - x0), int(y1 - y0), int(x2 - x0), int(y2 - y0)
        cv2.rectangle(c, (a, b), (cc, d), (0, 255, 0), 1)
        cv2.putText(c, f"{cf:.2f}", (max(0, a), max(10, b - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1, cv2.LINE_AA)
    for i, line in enumerate(label.split("\n")):
        cv2.rectangle(c, (0, i * 16), (crop, i * 16 + 16), (0, 0, 0), -1)
        cv2.putText(c, line, (3, i * 16 + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
    return c


# ----------------------------------------------------------------------------------------------- outputs
def write_outputs(out: Path, spots: list[dict], occ: np.ndarray, crops: dict, user_check: list[dict], meta: dict) -> None:
    cols = ["spot_id", "cx_median", "cy_median", "occupancy", "n_frames_with_box", "n_boxes", "n_cells", "peak_cell_occupancy",
            "conf_median", "w_median", "h_median", "cx_sd", "cy_sd", "cell_x0", "cell_y0", "cell_x1", "cell_y1", "frame_first",
            "frame_middle", "frame_last", "frame_nobox"]
    rows = []
    for s in spots:
        r = {c: s[c] for c in cols}
        r.update({f"occ_min{m:02d}": v for m, v in enumerate(s["minute_occupancy"])})
        rows.append(r)
    pd.DataFrame(rows).to_csv(out / "fixed_spots.csv", index=False)
    ny, nx = occ.shape
    iy, ix = np.nonzero(occ)
    pd.DataFrame({"x0": ix * CELL, "y0": iy * CELL, "occupancy": occ[iy, ix]}).sort_values(
        "occupancy", ascending=False).to_csv(out / "cells.csv.gz", index=False)
    with open(out / "fixed_spots_review.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["spot_id", "user_verdict", "notes"])
        for s in spots:
            w.writerow([s["spot_id"], "", ""])
    (out / "fn_notes.txt").write_text(
        "# Where are the consistent misses? (free text for the user)\n"
        "# Cohort-3 CH01 2026-09-06 21:00-22:00, YOLO v5 boxes conf >= 0.25. Give pano x/y (upright 7680 x 2160) or a\n"
        "# field-PC time + clip name per entry; one entry per line.\n\n", encoding="utf-8")
    H = ["<!doctype html><html><head><meta charset='utf-8'><title>CH01 YOLO fixed spots</title><style>"
         "body{font-family:sans-serif;margin:16px;max-width:1950px}table{border-collapse:collapse;font-size:12px}"
         "td,th{border:1px solid #999;padding:3px 5px;vertical-align:top}img.cr{width:200px;height:200px}"
         ".raster span{display:inline-block;width:6px;height:14px;margin:0}</style></head><body>",
         "<h1>Fixed spots of the cohort-1 YOLO v5 boxes — cohort-3 CH01 2026-09-06 21:00–22:00</h1>",
         f"<p>From the cached detections only (conf &ge; {CONF}). A spot = 8-connected {CELL}-px cells each holding a box "
         f"centre in &ge; {OCC_MIN:.0%} of the {meta['n_frames']} frames; occupancy = share of frames with a box centre "
         "in the spot. Numbers only; what a spot is, is for you to judge (verdicts in <code>fixed_spots_review.csv</code>: "
         "object / rat / unsure). Crops: native 400 × 400 px, thin boxes = all boxes &ge; 0.25 in that frame.</p>",
         "<h2>Locator (median of 60 frames, one per minute, 1920 × 540) — spot outlines in red</h2>"
         "<img src='locator.png' style='width:100%;max-width:1920px'>",
         "<h2>Occupancy heatmap (same scale)</h2><img src='heatmap.png' style='width:100%;max-width:1920px'>"]
    if user_check:
        H.append("<p>Cells named in the review: " + "; ".join(
            f"x {c['x0']}–{c['x0'] + CELL} / y {c['y0']}–{c['y0'] + CELL}: {c['occupancy']:.1%}" for c in user_check) + "</p>")
    H.append("<h2>Spots</h2><table><tr><th>id</th><th>pano centre (x, y)</th><th>occupancy</th><th>median conf</th>"
             "<th>median box w × h</th><th>centre SD x / y</th><th>cells</th><th>crops: first · middle · last · no box</th>"
             "<th>occupancy per minute (21:00 → 22:00)</th></tr>")
    for s in spots:
        imgs = "".join(f"<a href='{html.escape(crops[s['spot_id']][r])}'><img class='cr' src='{html.escape(crops[s['spot_id']][r])}'"
                       f" title='{r}'></a> " for r in ("first", "middle", "last", "nobox") if crops.get(s["spot_id"], {}).get(r))
        mx = max(s["minute_occupancy"]) or 1
        raster = "".join(f"<span title='minute {m}: {v:.1%}' style='background:rgb({int(255 - 255 * v)},{int(255 - 255 * v)},255)'></span>"
                         for m, v in enumerate(s["minute_occupancy"]))
        H.append(f"<tr><td>{s['spot_id']}</td><td>{s['cx_median']:.0f}, {s['cy_median']:.0f}</td><td>{s['occupancy']:.1%}</td>"
                 f"<td>{s['conf_median']:.2f}</td><td>{s['w_median']:.0f} × {s['h_median']:.0f}</td>"
                 f"<td>{s['cx_sd']:.1f} / {s['cy_sd']:.1f}</td><td>{s['n_cells']}</td><td>{imgs}</td>"
                 f"<td class='raster'>{raster}<br>max {mx:.1%}</td></tr>")
    H.append("</table>")
    H.append("<h2>Where are the consistent misses?</h2><p>Free text for you (this page cannot save it: copy it into "
             "<code>fn_notes.txt</code> in this folder).</p><textarea rows='10' cols='160'></textarea>")
    H.append("</body></html>")
    (out / "index.html").write_text("\n".join(H), encoding="utf-8")


def run(run_dir: Path) -> int:
    import cv2
    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    video = Path(meta["video"])
    out = run_dir / "fixed_spots"
    (out / "crops").mkdir(parents=True, exist_ok=True)
    fr = pd.read_csv(run_dir / "frames.csv.gz")
    det = pd.read_csv(run_dir / "detections.csv.gz")
    n = len(fr)
    d, occ = cell_table(det, n)
    spots, lab = find_spots(d, occ, fr)
    user_check = [{"x0": x0, "y0": y0, "occupancy": float(occ[y0 // CELL, x0 // CELL])}
                  for x0, y0 in ((6480, 1120), (6440, 1120), (3280, 600))]
    print(f"{len(spots)} spots >= {OCC_MIN:.0%} (cells >= {OCC_MIN:.0%}: {(occ >= OCC_MIN).sum()}); user cells: {user_check}")
    ny, nx = occ.shape
    # locator: frame nearest to the middle of each minute
    pts = fr["pts_s"].to_numpy(float)
    idx = [int(np.argmin(np.abs(pts - (60 * m + 30)))) for m in range(N_LOC)]
    imgs = [grab_frame(video, float(pts[k])) for k in idx]
    W, Hh = imgs[0].shape[1] // LOC_SCALE, imgs[0].shape[0] // LOC_SCALE
    cv2.imwrite(str(out / "locator.png"), locator(imgs, spots, ny, nx, W, Hh))
    del imgs
    cv2.imwrite(str(out / "heatmap.png"), heatmap(occ, spots, W, Hh))
    allb = det[det["conf"] >= CONF]
    by_frame = {k: g[["x1", "y1", "x2", "y2", "conf"]].to_numpy() for k, g in allb.groupby("frame")}
    crops = {}
    for s in spots:
        crops[s["spot_id"]] = {}
        sel = d[[(a, b) in s["_cells"] for a, b in zip(d["iy"], d["ix"])]]
        for role in ("first", "middle", "last", "nobox"):
            k = s[f"frame_{role}"]
            if k is None:
                continue
            img = grab_frame(video, float(pts[k]))
            sc = sel[sel["frame"] == k]["conf"]
            spot_conf = f"spot box conf {', '.join(f'{v:.2f}' for v in sorted(sc, reverse=True))}" if len(sc) else "no spot box"
            label = f"spot {s['spot_id']} | {role} | frame {k}\n{fr.loc[k, 't_pc']} field-PC | {spot_conf}"
            c = crop_img(img, s, by_frame.get(k, np.zeros((0, 5))), label)
            name = f"crops/spot{s['spot_id']:02d}_{role}_f{k}.png"
            cv2.imwrite(str(out / name), c)
            crops[s["spot_id"]][role] = name
    info = {"n_frames": n, "cell_px": CELL, "conf": CONF, "occ_min": OCC_MIN, "max_spots": MAX_SPOTS,
            "n_cells_ge_min": int((occ >= OCC_MIN).sum()), "n_components": int(lab.max()), "user_cells": user_check,
            "locator_frames": idx, "made": datetime.now().isoformat(timespec="seconds")}
    write_outputs(out, spots, occ, crops, user_check, info)
    (out / "fixed_spots.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(f"-> {out / 'index.html'}")
    return 0


# ----------------------------------------------------------------------------------------------- selftest
def selftest() -> int:
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

    rng = np.random.default_rng(0)
    n = 1200
    fr = pd.DataFrame({"frame": np.arange(n), "pts_s": np.linspace(0, 3599, n)})
    rows = []
    for k in range(n):
        if k % 10 < 4:                                    # spot A: 40 % of frames, two cells side by side
            cx = 6500 if k % 2 else 6460
            rows.append((k, cx - 30, 1130 - 30, cx + 30, 1130 + 30, 0.6))
        if k % 10 == 0:                                   # spot B: 10 %, two diagonal cells (8-connected)
            c = (410, 410) if k % 20 else (450, 450)
            rows.append((k, c[0] - 20, c[1] - 20, c[0] + 20, c[1] + 20, 0.4))
        if k % 50 == 0:                                   # 2 % cell: below threshold
            rows.append((k, 1000, 1000, 1030, 1030, 0.9))
        x = rng.uniform(0, 7600)
        rows.append((k, x, 100, x + 60, 160, 0.3))         # noise
        rows.append((k, 5000, 500, 5060, 560, 0.1))        # below conf
    det = pd.DataFrame(rows, columns=["frame", "x1", "y1", "x2", "y2", "conf"])
    d, occ = cell_table(det, n)
    rec("occupancy of the user's cell (6480-6520 / 1120-1160) = 20 %", abs(occ[1120 // 40, 6480 // 40] - 0.2) < 1e-9,
        f"{occ[28, 162]}")
    spots, lab = find_spots(d, occ, fr)
    rec("two spots, ranked by occupancy", len(spots) == 2 and spots[0]["occupancy"] > spots[1]["occupancy"],
        str([(s["spot_id"], round(s["occupancy"], 3), s["n_cells"]) for s in spots]))
    a, b = spots
    rec("spot A: 2 cells, occupancy 40 %, conf 0.6, box 60 x 60", a["n_cells"] == 2 and abs(a["occupancy"] - 0.4) < 1e-9
        and a["conf_median"] == 0.6 and a["w_median"] == 60, str({k: a[k] for k in ("occupancy", "conf_median", "w_median")}))
    rec("spot B: diagonal cells merged (8-connectivity), occupancy 10 %", b["n_cells"] == 2 and abs(b["occupancy"] - 0.1) < 1e-9)
    rec("below-threshold cell and sub-conf boxes excluded", all(s["conf_median"] >= 0.25 for s in spots)
        and lab[1000 // 40, 1000 // 40] == 0)
    rec("first / last frame with a box; no-box frame has none", a["frame_first"] == 0 and a["frame_last"] == 1193
        and a["frame_nobox"] is not None and a["frame_nobox"] % 10 >= 4, f"{a['frame_first']} {a['frame_last']} {a['frame_nobox']}")
    rec("per-minute occupancy ~0.4 for spot A", np.allclose(a["minute_occupancy"], 0.4, atol=0.05))
    many = pd.DataFrame([(k, 200 * i + 10, 1500, 200 * i + 30, 1520, 0.5) for i in range(20) for k in range(0, n, 10)],
                        columns=["frame", "x1", "y1", "x2", "y2", "conf"])
    d2, occ2 = cell_table(many, n)
    s2, _ = find_spots(d2, occ2, fr)
    rec("at most 15 spots kept", len(s2) == 15, str(len(s2)))
    # figures on a small canvas
    W, H = 7680, 2160
    loc = locator([np.full((H // 8, W // 8, 3), v, np.uint8) for v in (10, 20, 30)], spots, *occ.shape, 480, 135)
    rec("locator: median image with outlines, 480 x 135", loc.shape == (135, 480, 3) and (loc == 20).mean() > 0.9)
    hm = heatmap(occ, spots, 480, 135)
    rec("heatmap: same scale", hm.shape == (135, 480, 3))
    img = np.zeros((H, W, 3), np.uint8)
    c = crop_img(img, a, np.array([[6440, 1100, 6500, 1160, 0.6]]), "spot 1 | first\n21:00:00")
    rec("crop: 400 x 400 native, box drawn", c.shape == (400, 400, 3) and c[100:, :].max() > 0)
    # exact-frame grab vs sequential decode on a synthetic clip
    ff, _ = cvt.gf.find_ffmpeg()
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        vid = t / "CH01_2026-09-06_22-00-00_to_22-00-08.mp4"
        subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=90x320:rate=20:duration=8", "-c:v", "libx265",
                        "-x265-params", "keyint=40:min-keyint=40:scenecut=0:log-level=error", "-pix_fmt", "yuv420p", str(vid)], check=True)
        seq = list(cvt.AvFrames(vid))
        p, ref = seq[123]
        g = grab_frame(vid, p)
        rec("grab_frame = sequential decode frame (pixel-identical)", g.shape == ref.shape and int(np.abs(g.astype(int) - ref).max()) == 0)
        out = t / "fs"
        (out / "crops").mkdir(parents=True)
        write_outputs(out, spots, occ, {1: {"first": "crops/x.png"}}, [{"x0": 6480, "y0": 1120, "occupancy": 0.2}], {"n_frames": n})
        h = (out / "index.html").read_text(encoding="utf-8")
        rv = list(csv.reader(open(out / "fixed_spots_review.csv", encoding="utf-8")))
        rec("index + csv + empty review sheet + fn_notes stub", "consistent misses" in h and rv[0] == ["spot_id", "user_verdict", "notes"]
            and len(rv) == 3 and all(r[1] == "" for r in rv[1:]) and (out / "fn_notes.txt").is_file()
            and len(pd.read_csv(out / "fixed_spots.csv")) == 2)
    print(("PASS" if ok else "FAIL") + " — c1_yolo_fixed_spots self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--run", help="step-2 run dir (cv_field_c1yolo_video_<ts>)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.run:
        ap.error("--run is required")
    return run(Path(a.run))


if __name__ == "__main__":
    sys.exit(main())
