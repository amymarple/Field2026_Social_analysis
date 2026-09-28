"""thermal/score_labels.py — score the unsupervised detector against hand-corrected labels.

Reads labels.json (exported from label_tool.html) + detections.csv (the same run), matches detector boxes
to your ground-truth boxes on the REVIEWED frames, and reports precision / recall / F1. Then it SWEEPS a
contrast (tophat_mean) threshold over the detections so you can pick the operating point — i.e. answer
"is the unsupervised detector good enough, and where do I set the floor?" WITHOUT any training.

Matching: a detection is a true positive if its centroid falls inside an as-yet-unmatched ground-truth box
(greedy, one-to-one, nearest first). This is centroid-in-box, which suits small soft thermal blobs better
than strict IoU. Unmatched detections = false positives; unmatched GT boxes = false negatives (misses).

Usage:
  python thermal/score_labels.py --labels D:/tmp/thermal_labelrun/labels.json \
      --run D:/tmp/thermal_labelrun
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def load_labels(path: Path):
    j = json.loads(Path(path).read_text())
    gt = {}
    for f in j["frames"]:
        if f.get("reviewed"):
            gt[int(f["frame"])] = [dict(x=b["x"], y=b["y"], w=b["w"], h=b["h"]) for b in f["boxes"]]
    return gt, j.get("meta", {})


def load_dets(run_dir: Path):
    by_frame = defaultdict(list)
    with open(run_dir / "detections.csv") as f:
        for r in csv.DictReader(f):
            by_frame[int(r["frame"])].append(dict(
                cx=float(r["cx"]), cy=float(r["cy"]), contrast=float(r.get("tophat_mean", 0) or 0)))
    return by_frame


def match_dist(cx, cy, b, tol):
    """A detection matches a GT box if its centroid is inside the box, or within `tol` px of the box
    centre, or within the box's own half-diagonal — whichever is most generous. Hand-drawn boxes are
    often tight/offset, so a pure centroid-in-box test under-counts real hits; this is distance-tolerant."""
    gcx, gcy = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
    d = ((cx - gcx) ** 2 + (cy - gcy) ** 2) ** 0.5
    half_diag = 0.5 * (b["w"] ** 2 + b["h"] ** 2) ** 0.5
    inside = b["x"] <= cx <= b["x"] + b["w"] and b["y"] <= cy <= b["y"] + b["h"]
    return (d, inside or d <= max(tol, half_diag))


def score(gt: dict, dets_by_frame: dict, min_contrast: float, tol: float = 40.0):
    tp = fp = fn = 0
    for fr, gboxes in gt.items():
        dets = [d for d in dets_by_frame.get(fr, []) if d["contrast"] >= min_contrast]
        used = [False] * len(gboxes)
        # greedy: each detection claims the nearest matching GT box
        for d in dets:
            best, bd = -1, 1e9
            for gi, g in enumerate(gboxes):
                if used[gi]:
                    continue
                dd, ok = match_dist(d["cx"], d["cy"], g, tol)
                if ok and dd < bd:
                    bd, best = dd, gi
            if best >= 0:
                used[best] = True
                tp += 1
            else:
                fp += 1
        fn += used.count(False)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return dict(min_contrast=min_contrast, tp=tp, fp=fp, fn=fn,
                precision=round(prec, 3), recall=round(rec, 3), f1=round(f1, 3))


def main() -> int:
    ap = argparse.ArgumentParser(description="Score the unsupervised detector vs hand-corrected labels.")
    ap.add_argument("--labels", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--sweep", default="0,40,45,50,55,60,65,70",
                    help="comma-separated contrast (tophat_mean) thresholds to sweep")
    ap.add_argument("--tol", type=float, default=40.0, help="match tolerance px (centroid-to-GT-centre)")
    a = ap.parse_args()
    gt, meta = load_labels(Path(a.labels))
    dets = load_dets(Path(a.run))
    n_gt = sum(len(v) for v in gt.values())
    print(f"reviewed frames: {len(gt)}   ground-truth boxes: {n_gt}   "
          f"(video: {meta.get('video','?')})\n")
    if not gt:
        print("No reviewed frames in labels.json — open label_tool.html, correct some frames, Export first.")
        return 1
    print(f"(match tolerance: centroid within max({a.tol:.0f}px, box half-diagonal) of a GT box)\n")
    thresholds = [float(t) for t in a.sweep.split(",")]
    rows = [score(gt, dets, t, a.tol) for t in thresholds]
    print(f"{'contrast>=':>11} {'TP':>4} {'FP':>4} {'FN':>4} {'prec':>6} {'recall':>7} {'F1':>6}")
    for r in rows:
        print(f"{r['min_contrast']:>11.0f} {r['tp']:>4} {r['fp']:>4} {r['fn']:>4} "
              f"{r['precision']:>6.2f} {r['recall']:>7.2f} {r['f1']:>6.2f}")
    best = max(rows, key=lambda r: r["f1"])
    print(f"\nBest F1={best['f1']:.2f} at contrast>= {best['min_contrast']:.0f} "
          f"(precision {best['precision']:.2f}, recall {best['recall']:.2f}).")
    print("Set the operating point with --tophat-floor near this contrast in detect_blobs.py, or filter "
          "detections.csv by tophat_mean. Recall < 1 that is dominated by huddle/occlusion/haze is a data "
          "limit, not a threshold you can tune away.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
