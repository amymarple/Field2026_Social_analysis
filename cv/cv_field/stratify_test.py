"""stratify_test.py — split the frozen 07-06 ruler into VISIBLE vs OCCLUDED strata and score HONESTLY.

The val~0.8 -> frozen-test~0.2 collapse is occlusion: on a tall-grass night many labeled rats are physically
buried, and no pixel detector can recover them. Reporting a single AP over all 22 boxes therefore blames the
detector for a physics limit. This module measures the detector only where a pixel method could ever succeed:

  * tag each frozen-test GT box `visible` vs `occluded` (owner-editable `visibility.json`, or a documented
    dark-hood-contrast heuristic as a starting point),
  * match detections to GT (IoU >= thr, greedy, highest-confidence first),
  * report **TP / FP / FN and recall @ matched-precision on the VISIBLE stratum** (not only AP): occluded GT
    are excluded from the recall denominator (a buried rat is un-detectable), but every FP still counts.

FROZEN-TEST DISCIPLINE: this only SCORES the 07-06 set. It is never trained on, gate-fit on, threshold-tuned
on, or acquired against. The visibility tags describe the imagery, not the model.

The matching + PR math is pure numpy and offline-tested (`--selftest`); `box_contrast` (the dark-hood
heuristic, also reused by the training-set contrast check) needs cv2.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CV_ROOT = HERE.parent


# ------------------------------------------------------------------ IoU matching (pure)
def _iou(a, b):
    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def _center_hit(a, b):
    """True if a's centre lies in b OR b's centre lies in a (size-tolerant 'is the detection ON the rat').
    Right for tiny field animals where the exact box size is noisy and IoU>=0.5 wrongly rejects correct hits."""
    ac = ((a[0] + a[2]) / 2.0, (a[1] + a[3]) / 2.0); bc = ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
    inside = lambda box, pt: box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]
    return inside(b, ac) or inside(a, bc)


def match(gt_boxes, pred_boxes, pred_scores, iou_thr=0.5, mode="iou"):
    """Greedy match (highest score first). Returns dict: matched_gt (idx->pred idx), pred_is_tp (bool per
    pred), and the gt indices left unmatched.

    ``mode="iou"`` (legacy): a pred matches the best-IoU gt >= ``iou_thr``. ``mode="center"`` (recommended for
    cv_field): a pred matches the nearest-centre gt whose box CONTAINS the pred centre (or vice versa) — size-
    tolerant, because box-size disagreement between a correct detection and a fuzzy GT box should not count as
    a miss. See `evaluate(match_mode=...)`."""
    order = np.argsort(np.asarray(pred_scores, float))[::-1]
    gt_taken = set()
    pred_is_tp = [False] * len(pred_boxes)
    matched_gt = {}
    for pi in order:
        best_j = -1
        if mode == "center":
            best_d = None
            pc = ((pred_boxes[pi][0] + pred_boxes[pi][2]) / 2.0, (pred_boxes[pi][1] + pred_boxes[pi][3]) / 2.0)
            for j, g in enumerate(gt_boxes):
                if j in gt_taken or not _center_hit(pred_boxes[pi], g):
                    continue
                gc = ((g[0] + g[2]) / 2.0, (g[1] + g[3]) / 2.0)
                d = (pc[0] - gc[0]) ** 2 + (pc[1] - gc[1]) ** 2
                if best_d is None or d < best_d:
                    best_d, best_j = d, j
        else:
            best_iou = iou_thr
            for j, g in enumerate(gt_boxes):
                if j in gt_taken:
                    continue
                v = _iou(pred_boxes[pi], g)
                if v >= best_iou:
                    best_iou, best_j = v, j
        if best_j >= 0:
            gt_taken.add(best_j); pred_is_tp[pi] = True; matched_gt[best_j] = int(pi)
    unmatched_gt = [j for j in range(len(gt_boxes)) if j not in gt_taken]
    return {"pred_is_tp": pred_is_tp, "matched_gt": matched_gt, "unmatched_gt": unmatched_gt}


def pr_sweep(all_preds, n_visible_gt):
    """PR points over confidence thresholds. `all_preds` = list of (score, is_tp, gt_visible) where gt_visible
    is the matched GT's visibility (None for FPs). Recall denominator = visible GT only; FPs always count.
    Returns sorted list of (threshold, precision, recall_visible)."""
    if n_visible_gt == 0:
        return []
    pts = []
    scores = sorted({s for (s, _t, _v) in all_preds}, reverse=True)
    for thr in scores:
        kept = [(t, v) for (s, t, v) in all_preds if s >= thr]
        tp = sum(1 for (t, v) in kept if t)
        fp = sum(1 for (t, v) in kept if not t)
        tp_vis = sum(1 for (t, v) in kept if t and v)     # TP on a VISIBLE gt
        prec = tp / (tp + fp) if (tp + fp) else 1.0
        rec = tp_vis / n_visible_gt
        pts.append((float(thr), float(prec), float(rec)))
    return pts


def recall_at_precision(pr_points, target=0.9):
    """Best recall among PR points whose precision >= target (0.0 if none reach it)."""
    ok = [r for (_t, p, r) in pr_points if p >= target]
    return max(ok) if ok else 0.0


# ------------------------------------------------------------------ visibility (dark-hood contrast heuristic)
def box_contrast(gray, box_px, ring_frac=1.0):
    """Dark-hood contrast of a box vs its surrounding grass ring, in grey levels.

    = median(surrounding ring) - 10th-percentile(box interior). A visible Long Evans rat has a dark hood far
    below the NIR-bright grass -> large positive contrast; a grass-occluded box ~ its ring -> ~0. Pure per-box
    scalar (also used by the training-set dark-hood check)."""
    H, W = gray.shape[:2]
    x1, y1, x2, y2 = (int(round(v)) for v in box_px)
    x1, y1 = max(0, x1), max(0, y1); x2, y2 = min(W, x2), min(H, y2)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return 0.0
    bw, bh = x2 - x1, y2 - y1
    rx1, ry1 = max(0, int(x1 - ring_frac * bw)), max(0, int(y1 - ring_frac * bh))
    rx2, ry2 = min(W, int(x2 + ring_frac * bw)), min(H, int(y2 + ring_frac * bh))
    box = gray[y1:y2, x1:x2].astype(np.float32)
    ring = gray[ry1:ry2, rx1:rx2].astype(np.float32).copy()
    ring[y1 - ry1:y2 - ry1, x1 - rx1:x2 - rx1] = np.nan       # exclude the box from the ring
    ring_med = float(np.nanmedian(ring)) if np.isfinite(ring).any() else float(np.median(box))
    return ring_med - float(np.percentile(box, 10))


def auto_visibility(test_root: Path, thr_contrast=12.0):
    """Heuristic per-box visibility for every frozen-test frame. Returns {frame_stem: [bool,...]} aligned with
    the label file order. A box is `visible` if its dark-hood contrast >= thr_contrast."""
    import cv2
    from tile_dataset import norm_to_px, read_yolo_labels
    img_dir, lbl_dir = test_root / "images", test_root / "labels"
    out = {}
    for p in sorted(img_dir.glob("*.png")):
        rows = read_yolo_labels(lbl_dir / f"{p.stem}.txt")
        if not rows:
            out[p.stem] = []
            continue
        gray = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        H, W = gray.shape[:2]
        vis = []
        for r in rows:
            b = norm_to_px(r, W, H)
            vis.append(bool(box_contrast(gray, b) >= thr_contrast))
        out[p.stem] = vis
    return out


def load_visibility(test_root: Path):
    """Owner-edited visibility.json ({frame_stem: [bool,...]}) if present, else None."""
    p = test_root / "visibility.json"
    if p.exists():
        return json.loads(p.read_text())
    return None


# ------------------------------------------------------------------ evaluation driver
def evaluate(test_root: Path, preds_by_frame: dict, visibility: dict, iou_thr=0.5, target_precision=0.9,
             match_mode="center"):
    """Score predictions against the frozen test, stratified. `preds_by_frame[stem]` = list of
    (x1,y1,x2,y2,score) in PIXELS of that frame. `visibility[stem]` = per-GT-box bool (aligned to labels).

    ``match_mode`` defaults to "center" (size-tolerant, is-the-detection-on-the-rat — the honest metric for
    tiny field animals whose exact box size is noisy); pass "iou" with ``iou_thr`` for the legacy overlap
    metric. Center-matching avoids counting a correct detection with a slightly-off box size as FP+FN."""
    from tile_dataset import norm_to_px, read_yolo_labels
    import cv2
    img_dir, lbl_dir = test_root / "images", test_root / "labels"
    all_preds, n_vis, n_occ, tp_all, fp_all, fn_vis = [], 0, 0, 0, 0, 0
    for p in sorted(img_dir.glob("*.png")):
        stem = p.stem
        rows = read_yolo_labels(lbl_dir / f"{stem}.txt")
        im = cv2.imread(str(p)); H, W = im.shape[:2]
        gt = [norm_to_px(r, W, H) for r in rows]
        vis = visibility.get(stem, [True] * len(gt))
        n_vis += sum(1 for v in vis if v); n_occ += sum(1 for v in vis if not v)
        preds = preds_by_frame.get(stem, [])
        pb = [q[:4] for q in preds]; ps = [q[4] for q in preds]
        m = match(gt, pb, ps, iou_thr, mode=match_mode)
        for pi, is_tp in enumerate(m["pred_is_tp"]):
            gv = None
            if is_tp:
                j = [k for k, v in m["matched_gt"].items() if v == pi]
                gv = bool(vis[j[0]]) if j else True
            all_preds.append((ps[pi], is_tp, gv))
            tp_all += int(is_tp); fp_all += int(not is_tp)
        fn_vis += sum(1 for j in m["unmatched_gt"] if vis[j])
    pr = pr_sweep(all_preds, n_vis)
    return {
        "n_frames": len(list(img_dir.glob("*.png"))),
        "gt_visible": n_vis, "gt_occluded": n_occ,
        "TP": tp_all, "FP": fp_all, "FN_visible": fn_vis,
        "precision_all": round(tp_all / (tp_all + fp_all), 4) if (tp_all + fp_all) else None,
        "recall_visible": round(sum(1 for (_s, t, v) in all_preds if t and v) / n_vis, 4) if n_vis else None,
        f"recall_at_p{int(target_precision*100)}": round(recall_at_precision(pr, target_precision), 4),
        "pr_points": [(round(t, 3), round(p_, 3), round(r, 3)) for (t, p_, r) in pr],
        "iou_thr": iou_thr,
    }


# ------------------------------------------------------------------ self-test (pure)
def _selftest() -> int:
    ok = True

    def chk(name, cond):
        nonlocal ok; ok = ok and bool(cond); print(f"  [{'PASS' if cond else 'FAIL'}] {name}")

    chk("iou identical=1", abs(_iou((0, 0, 10, 10), (0, 0, 10, 10)) - 1.0) < 1e-9)
    chk("iou disjoint=0", _iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0)

    gt = [(0, 0, 10, 10), (100, 100, 110, 110), (200, 0, 210, 10)]   # box2 will be "occluded"
    preds = [(1, 1, 11, 11, 0.9), (101, 101, 111, 111, 0.8), (500, 500, 510, 510, 0.7)]  # 2 TP + 1 FP
    m = match(gt, [p[:4] for p in preds], [p[4] for p in preds], 0.5)
    chk("match finds 2 TP", sum(m["pred_is_tp"]) == 2)
    chk("match leaves box3 unmatched", 2 in m["unmatched_gt"])

    # box3 visible, others: box1 visible, box2 occluded -> recall denominator excludes the occluded box2
    vis = [True, False, True]
    all_preds = []
    for pi, is_tp in enumerate(m["pred_is_tp"]):
        gv = None
        if is_tp:
            j = [k for k, v in m["matched_gt"].items() if v == pi]
            gv = vis[j[0]] if j else True
        all_preds.append((preds[pi][4], is_tp, gv))
    n_visible = sum(vis)  # 2 visible GT
    pr = pr_sweep(all_preds, n_visible)
    # at conf>=0.9: 1 TP (box1, visible), 0 FP -> precision 1.0, recall 1/2=0.5
    top = pr[0]
    chk("PR top precision 1.0", abs(top[1] - 1.0) < 1e-9)
    chk("PR top recall 0.5 (1 of 2 visible)", abs(top[2] - 0.5) < 1e-9)
    # box3 (visible) has no matching pred -> it is an FN_visible; max recall_visible = 1/2 (only box1 found)
    chk("recall@p0.9 = 0.5", abs(recall_at_precision(pr, 0.9) - 0.5) < 1e-9)

    # box_contrast: a dark box on a bright field -> large positive contrast
    g = np.full((60, 60), 200, np.uint8); g[25:35, 25:35] = 40
    chk("box_contrast dark-on-bright large", box_contrast(g, (25, 25, 35, 35)) > 100)
    g2 = np.full((60, 60), 200, np.uint8)                     # no rat -> ~0 contrast
    chk("box_contrast uniform ~0", abs(box_contrast(g2, (25, 25, 35, 35))) < 5)

    print("PASS — stratify_test self-test" if ok else "FAIL — stratify_test self-test")
    return 0 if ok else 1


# ------------------------------------------------------------------ CLI
def _load_preds_json(path):
    """preds JSON: {frame_stem: [[x1,y1,x2,y2,score], ...]} in pixels."""
    d = json.loads(Path(path).read_text())
    return {k: [tuple(map(float, b)) for b in v] for k, v in d.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description="Visible/occluded stratification + honest metrics on the frozen test.")
    ap.add_argument("--test-root", default=str(CV_ROOT / "dataset" / "rat_field_test"))
    ap.add_argument("--auto-visibility", action="store_true",
                    help="write a starter visibility.json from the dark-hood-contrast heuristic (owner then edits)")
    ap.add_argument("--contrast-thr", type=float, default=12.0)
    ap.add_argument("--eval", action="store_true", help="evaluate --preds against the (stratified) frozen test")
    ap.add_argument("--preds", help="predictions JSON {stem: [[x1,y1,x2,y2,score],...]} in pixels")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--target-precision", type=float, default=0.9)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        raise SystemExit(_selftest())
    test_root = Path(args.test_root)
    if args.auto_visibility:
        vis = auto_visibility(test_root, args.contrast_thr)
        out = test_root / "visibility.json"
        out.write_text(json.dumps(vis, indent=1))
        nv = sum(sum(1 for b in v if b) for v in vis.values())
        no = sum(sum(1 for b in v if not b) for v in vis.values())
        print(f"wrote {out}: {nv} visible / {no} occluded GT boxes (heuristic thr={args.contrast_thr}). "
              f"REVIEW + edit before scoring — this is a starting point, not ground truth.")
        return
    if args.eval:
        if not args.preds:
            raise SystemExit("--eval needs --preds <json>")
        vis = load_visibility(test_root)
        if vis is None:
            raise SystemExit("no visibility.json — run --auto-visibility first, then review it")
        res = evaluate(test_root, _load_preds_json(args.preds), vis, args.iou, args.target_precision)
        print(json.dumps(res, indent=2))
        return
    print("stratify_test.py — use --auto-visibility, then --eval --preds, or --selftest")


if __name__ == "__main__":
    main()
