"""thermal/train_filter.py — learn a small rat/not-rat filter from your labels (the supervised step).

The detector is unsupervised, so labeling alone never changes it. This script USES your labels to train a
lightweight classifier on the per-blob features the detector already computes (contrast, area, shape,
motion, image position) and reject the candidates that aren't rats — killing the repeated berm/structure
false positives, and (with a lower detection floor feeding more candidates) recovering some misses.

It is evaluated with FRAME-GROUPED cross-validation (GroupKFold on frame id) so no frame appears in both
train and test — the reported precision/recall is an honest held-out estimate, not memorized. It is
compared head-to-head with the rule-only contrast threshold so you can see whether the classifier is
actually worth it on THIS much data.

Note: position features make the model CAMERA-SPECIFIC (it learns where this camera's berms are). Retrain
per camera/setup. Small label sets are noisy — treat a small win cautiously.

Usage:
  python thermal/train_filter.py --labels D:/tmp/thermal_labelrun/labels.json --run D:/tmp/thermal_labelrun_lo
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

FEATURES = ["tophat_mean", "area", "extent", "aspect", "solidity", "motion", "w", "h", "cxn", "cyn"]


def load_labels(path: Path):
    j = json.loads(Path(path).read_text())
    gt = {int(f["frame"]): [dict(x=b["x"], y=b["y"], w=b["w"], h=b["h"]) for b in f["boxes"]]
          for f in j["frames"] if f.get("reviewed")}
    meta = j.get("meta", {})
    return gt, meta


def load_dets(run_dir: Path, W: int, H: int):
    rows = []
    with open(run_dir / "detections.csv") as f:
        for r in csv.DictReader(f):
            d = {k: float(r[k]) for k in ("cx", "cy", "w", "h", "area", "extent", "aspect",
                                          "solidity", "tophat_mean", "motion") if r.get(k) not in (None, "")}
            d["motion"] = 0.0 if ("motion" not in d or np.isnan(d.get("motion", np.nan))) else d["motion"]
            d["frame"] = int(r["frame"])
            d["cxn"], d["cyn"] = d["cx"] / W, d["cy"] / H
            rows.append(d)
    return rows


def match_gt(cx, cy, boxes, used, tol=40.0):
    best, bd = -1, 1e9
    for gi, b in enumerate(boxes):
        if used[gi]:
            continue
        gcx, gcy = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
        d = ((cx - gcx) ** 2 + (cy - gcy) ** 2) ** 0.5
        half = 0.5 * (b["w"] ** 2 + b["h"] ** 2) ** 0.5
        inside = b["x"] <= cx <= b["x"] + b["w"] and b["y"] <= cy <= b["y"] + b["h"]
        if (inside or d <= max(tol, half)) and d < bd:
            bd, best = d, gi
    return best


def label_detections(gt, dets):
    """y=1 if a detection matches a GT box (greedy nearest per frame), else 0."""
    y = np.zeros(len(dets), int)
    by_frame = defaultdict(list)
    for i, d in enumerate(dets):
        by_frame[d["frame"]].append(i)
    for fr, idxs in by_frame.items():
        boxes = gt.get(fr, [])
        used = [False] * len(boxes)
        # match brightest detections first (stable, mimics a real keep-order)
        for i in sorted(idxs, key=lambda i: -dets[i]["tophat_mean"]):
            gi = match_gt(dets[i]["cx"], dets[i]["cy"], boxes, used)
            if gi >= 0:
                used[gi] = True
                y[i] = 1
    return y


def score_at(gt, dets, keep_mask):
    """GT-level precision/recall/F1 given a boolean keep-mask over detections."""
    tp = fp = fn = 0
    by_frame = defaultdict(list)
    for i, d in enumerate(dets):
        if keep_mask[i]:
            by_frame[d["frame"]].append(i)
    for fr, boxes in gt.items():
        used = [False] * len(boxes)
        for i in sorted(by_frame.get(fr, []), key=lambda i: -dets[i]["tophat_mean"]):
            gi = match_gt(dets[i]["cx"], dets[i]["cy"], boxes, used)
            if gi >= 0:
                used[gi] = True
                tp += 1
            else:
                fp += 1
        fn += used.count(False)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return dict(tp=tp, fp=fp, fn=fn, precision=round(p, 3), recall=round(r, 3), f1=round(f1, 3))


def main() -> int:
    ap = argparse.ArgumentParser(description="Train a small rat/not-rat filter from labels (supervised).")
    ap.add_argument("--labels", required=True)
    ap.add_argument("--run", required=True, help="detection run (ideally a LOW --tophat-floor pool)")
    ap.add_argument("--out-model", default=None)
    ap.add_argument("--folds", type=int, default=5)
    a = ap.parse_args()

    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GroupKFold
    from sklearn.preprocessing import StandardScaler

    gt, meta = load_labels(Path(a.labels))
    W, H = int(meta.get("orig_w", 1280)), int(meta.get("orig_h", 960))
    dets = load_dets(Path(a.run), W, H)
    dets = [d for d in dets if d["frame"] in gt]  # only reviewed frames
    y = label_detections(gt, dets)
    X = np.array([[d[f] for f in FEATURES] for d in dets], float)
    groups = np.array([d["frame"] for d in dets])
    n_gt = sum(len(v) for v in gt.values())
    print(f"reviewed frames: {len(gt)}   candidate detections: {len(dets)} "
          f"({int(y.sum())} rat / {int((1 - y).sum())} not-rat)   GT rats: {n_gt}\n")
    if y.sum() < 5 or (1 - y).sum() < 5:
        print("Too few examples of one class to train a meaningful filter — label more frames.")
        return 1

    models = {
        "logistic": LogisticRegression(class_weight="balanced", C=0.5, max_iter=1000),
        "rf_depth3": RandomForestClassifier(n_estimators=200, max_depth=3, class_weight="balanced",
                                            random_state=0),
    }
    gkf = GroupKFold(n_splits=min(a.folds, len(set(groups))))
    for name, base in models.items():
        oof = np.full(len(dets), np.nan)
        for tr, te in gkf.split(X, y, groups):
            sc = StandardScaler().fit(X[tr])
            m = base.__class__(**base.get_params()).fit(sc.transform(X[tr]), y[tr])
            oof[te] = m.predict_proba(sc.transform(X[te]))[:, 1]
        # sweep the probability threshold; report GT-level P/R/F1 out-of-fold
        best = None
        for p in np.linspace(0.1, 0.9, 17):
            s = score_at(gt, dets, oof >= p)
            if best is None or s["f1"] > best["f1"]:
                best = {**s, "prob": round(float(p), 2)}
        print(f"[{name:9s}] out-of-fold best  F1={best['f1']:.2f}  precision={best['precision']:.2f}  "
              f"recall={best['recall']:.2f}  (TP {best['tp']} FP {best['fp']} FN {best['fn']}, "
              f"prob>= {best['prob']})")

    # rule baseline (contrast threshold) on the SAME candidate pool, for comparison
    print("\n rule baseline (contrast threshold, same pool):")
    for t in (45, 50, 55, 60):
        s = score_at(gt, dets, np.array([d["tophat_mean"] >= t for d in dets]))
        print(f"   contrast>= {t}: precision {s['precision']:.2f}  recall {s['recall']:.2f}  F1 {s['f1']:.2f}")

    # fit final logistic on all data + report standardized coefficients (which features matter)
    sc = StandardScaler().fit(X)
    final = LogisticRegression(class_weight="balanced", C=0.5, max_iter=1000).fit(sc.transform(X), y)
    coefs = sorted(zip(FEATURES, final.coef_[0]), key=lambda kv: -abs(kv[1]))
    print("\n logistic coefficients (standardized; + => more rat-like):")
    for f, c in coefs:
        print(f"   {f:11s} {c:+.2f}")
    out = Path(a.out_model) if a.out_model else Path(a.run) / "rat_filter.json"
    out.write_text(json.dumps(dict(features=FEATURES, mean=sc.mean_.tolist(), scale=sc.scale_.tolist(),
                                   coef=final.coef_[0].tolist(), intercept=float(final.intercept_[0]),
                                   camera=meta.get("cam"), note="apply: sigmoid(coef.((x-mean)/scale)+b)"),
                              indent=1))
    print(f"\n-> saved model: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
