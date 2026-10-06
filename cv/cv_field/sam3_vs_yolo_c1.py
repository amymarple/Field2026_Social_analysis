"""sam3_vs_yolo_c1.py — SAM3 zero-shot vs the cohort-1 YOLO v5 panorama rat detector on labelled cohort-1 frames.

Plan: implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md, step 1 (pre-registered; amendments dated there).
Ground truth = the human YOLO labels of `social-field-rat` (read from the verified step-0 backup, never the source):
  S-val  = the 177 `labeled_yolo/images/val` frames (v5 never trained on them, but they sit seconds from training frames
           and v5's best epoch was chosen on them -> v5-favourable);
  S-held = the labelled frames of the two never-trained clips CH02 07-04 (`frames_0704_CH02_selective`) and CH01 07-05
           (`frames_0705_CH01_selective`); an empty .txt = a negative frame, a missing .txt = never labelled -> excluded.
Frames are upright 7680 x 2160 PNG (raw portrait rotated 90 deg ccw); labels `0 cx cy w h` normalised.

Detectors (raw outputs cached once at a low floor, every score re-derived from the caches):
  yolo_v5_1280      v5 `rat_m_v5/best.pt`, imgsz 1280 (as trained), conf >= 0.01                         [primary]
  yolo_v5_2560      the same weights at imgsz 2560 (inference only)                                          [sensitivity]
  sam3_rat_t1008    SAM3SemanticPredictor, text "rat", tiles of 1008 x 1008 native px (>= 20 % overlap; 10 x 3 tiles),
                    box = bounding box of SAM3's thresholded mask mapped back to the frame, cross-tile duplicates
                    merged by NMS IoU 0.5, score = SAM3's presence x detection score, kept >= 0.01               [primary]
  sam3_rat_t2016    tiles of 2016 native px resized (INTER_AREA) to 1008 (5 x 2 tiles; a rat ~32 px)          [sensitivity]
  sam3_animal_t1008 text "animal", 1008 tiles                                                                  [sensitivity]
  sam3_rat_t1008_edge  (amendment, before results) sam3_rat_t1008 with boxes touching an inner tile border dropped
                    before the NMS (every rat lies whole in some tile: overlaps 267 / 432 px >> a rat)         [sensitivity]
SAM3 API facts (ultralytics 8.4.93, read from models/sam/predict.py): `SAM3SemanticPredictor.inference_features`
scores = sigmoid(pred_logits) x sigmoid(presence_logit_dec) (detection x presence), drops scores <= args.conf, runs a
within-image NMS at args.iou (0.7) on the decoder boxes, returns masks bilinearly upsampled to the tile and
thresholded > 0.5 plus the decoder boxes; the image is letterboxed with scale_fill to args.imgsz, so imgsz=1008 is set
explicitly (the default 640 would shrink the tile). The image features of a tile are computed once and reused for
both text prompts (forward_grounding only overwrites the text-embedding entries of the feature dict).

Lighting per frame, numerically: chroma = mean over a 4-px grid of |R-G| + |G-B| (8-bit units); IR if chroma < thr,
thr fixed BEFORE any scoring from the labelled CH02 07-06 (IR night) and CH02 06-30 (dusk) frames (plan amendment
2026-10-05, before results): the geometric mid-point of the LARGEST gap in log10(max(chroma, 1e-4)) over the pooled
reference frames (monochrome IR frames have neutral chroma planes, chroma ~0.01, colour frames are orders of magnitude
higher; the first rule - midpoint, else the cut minimising misclassified frames - assumed every 06-30 frame was colour,
which the chroma values contradict, and is kept as `ir_threshold_v0` for the record). Written to lighting.json +
ref_chroma.csv.

Matching (pre-registered): primary = centre match (a prediction matches an unmatched GT box if its centre lies in the
GT box grown by 25 % of its width / height on every side; greedy by score; among candidates the nearest GT centre);
secondary = IoU >= 0.5 (greedy by score, highest IoU). Metrics per group (overall, camera x date, lighting,
camera x lighting) and set: AP (all-point interpolated), recall at precision >= 0.8, max F1 with its P / R / score
cut, count error per frame and empty-frame false-positive rate at the set-level max-F1 cut of that detector and at the
fixed 0.25 cut, 95 % CIs from 1 000 frame-bootstrap resamples (paired across detectors for the differences).

Usage (cv env: C:/Users/Cornell/.conda/envs/cv/python.exe, PYTHONIOENCODING=utf-8):
  python cv/cv_field/sam3_vs_yolo_c1.py [--run <existing run dir>] [--phases lighting yolo sam3 score]
  python cv/cv_field/sam3_vs_yolo_c1.py --score-only <run dir>      # re-score + rewrite the report from the caches
  python cv/cv_field/sam3_vs_yolo_c1.py --selftest                  # synthetic data only, no GPU, no field data
Output: $FIELD2026_ANALYSIS_OUT_ROOT/2026a/cv_field_sam3_vs_yolo_c1_<ts>/ (frames.csv, gt.csv, lighting.json,
        yolo_preds.csv.gz, sam3_tiles_<tiling>.csv, sam3_preds.csv.gz, timing.csv, metrics_*.csv, pr_*.csv, run.json)
        + results/2026a/cv_field/reports/cv_field_sam3_vs_yolo_c1_2026a.md, figures/sam3_vs_yolo_c1/,
        pointer run_manifest_sam3_vs_yolo_c1_2026a.json. The agent never looks at frames or figures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

OUT_ROOT = Path(os.environ.get("FIELD2026_ANALYSIS_OUT_ROOT", "D:/Field2026_analysis_out"))
BACKUP = OUT_ROOT / "2026a" / "social_field_rat_backup_20261005"
SAM3_WEIGHTS = Path("C:/Users/Cornell/.cache/huggingface/hub/models--facebook--sam3/snapshots/"
                    "3c879f39826c281e95690f02c7821c4de09afae7/sam3.pt")
FW, FH = 7680, 2160
SCORE_FLOOR = 0.01
GROW = 0.25
IOU_MATCH = 0.5
NMS_IOU = 0.5
P_TARGET = 0.8
FIXED_CUT = 0.25
N_BOOT = 1000
SEED = 0
COHORT, DIRECTION, NAME = "2026a", "cv_field", "cv_field_sam3_vs_yolo_c1"
REPORT_NAME = "cv_field_sam3_vs_yolo_c1_2026a.md"
POINTER_NAME = "run_manifest_sam3_vs_yolo_c1_2026a.json"
TILINGS = {"t1008": {"tile": 1008, "prompts": ["rat", "animal"]}, "t2016": {"tile": 2016, "prompts": ["rat"]}}
DETECTORS = ["yolo_v5_1280", "yolo_v5_2560", "sam3_rat_t1008", "sam3_rat_t2016", "sam3_animal_t1008",
             "sam3_rat_t1008_edge"]
PRIMARY = ("yolo_v5_1280", "sam3_rat_t1008")
# Post-hoc (plan amendment 2026-10-05, after results, the user's suggestion): the prompt "Long Evans rat" on both tilings.
POSTHOC_PROMPT = "Long Evans rat"
POSTHOC_TILINGS = {"t1008_ler": {"tile": 1008, "prompts": [POSTHOC_PROMPT]},
                   "t2016_ler": {"tile": 2016, "prompts": [POSTHOC_PROMPT]}}
POSTHOC = ["sam3_ler_t1008", "sam3_ler_t2016"]
PREREG = list(DETECTORS)
DETECTORS = DETECTORS + POSTHOC
NAME_RE = re.compile(r"(CH0\d)_(\d{4})-(\d{2})-(\d{2})")


# ----------------------------------------------------------------------------------------------- inventory / GT
def data_root(backup: Path) -> Path:
    return Path(backup) / "computer_vision" / "data"


def parse_cam_date(stem: str) -> tuple[str, str]:
    m = NAME_RE.search(stem)
    if not m:
        raise ValueError(f"cannot parse camera/date from {stem}")
    return m.group(1), f"{m.group(3)}-{m.group(4)}"


def inventory(data: Path) -> pd.DataFrame:
    rows = []
    for img in sorted((data / "labeled_yolo" / "images" / "val").glob("*.png")):
        lab = data / "labeled_yolo" / "labels" / "val" / (img.stem + ".txt")
        if lab.is_file():
            rows.append(("S-val", img, lab))
    for clip in ("frames_0704_CH02_selective", "frames_0705_CH01_selective"):
        for img in sorted((data / clip / "images").glob("*.png")):
            lab = img.with_suffix(".txt")
            if lab.is_file():
                rows.append(("S-held", img, lab))
    out = []
    for s, img, lab in rows:
        cam, d = parse_cam_date(img.stem)
        out.append({"frame_id": f"{s}/{img.stem}", "set": s, "path": img.as_posix(), "label": lab.as_posix(),
                    "camera": cam, "date": d, "cam_date": f"{cam} {d}"})
    return pd.DataFrame(out)


def read_yolo_labels(path: str | Path, w: int = FW, h: int = FH) -> np.ndarray:
    boxes = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        cx, cy, bw, bh = (float(v) for v in p[1:5])
        boxes.append([(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h])
    return np.asarray(boxes, float).reshape(-1, 4)


# ----------------------------------------------------------------------------------------------- lighting
def chroma(img_bgr: np.ndarray, step: int = 4) -> float:
    s = img_bgr[::step, ::step].astype(np.int16)
    b, g, r = s[..., 0], s[..., 1], s[..., 2]
    return float(np.mean(np.abs(r - g) + np.abs(g - b)))


def ir_threshold_v0(ir_vals, col_vals) -> dict:
    """First (pre-registered) rule, superseded before results: assumes the colour reference is all colour."""
    ir, col = np.sort(np.asarray(ir_vals, float)), np.sort(np.asarray(col_vals, float))
    if ir.max() < col.min():
        return {"thr": float((ir.max() + col.min()) / 2), "rule": "midpoint of the gap (sets separate)",
                "n_misclassified": 0}
    pooled = np.unique(np.concatenate([ir, col]))
    cuts = (pooled[:-1] + pooled[1:]) / 2
    err = np.array([(ir >= c).sum() + (col < c).sum() for c in cuts])
    best = cuts[err == err.min()]
    return {"thr": float(best.min()), "rule": "cut minimising misclassified reference frames (sets overlap)",
            "n_misclassified": int(err.min())}


def ir_threshold(ir_vals, col_vals, floor: float = 1e-4) -> dict:
    """Geometric mid-point of the largest gap in log10(max(chroma, floor)) over the pooled reference frames."""
    ir, col = np.asarray(ir_vals, float), np.asarray(col_vals, float)
    v = np.sort(np.log10(np.maximum(np.concatenate([ir, col]), floor)))
    g = np.diff(v)
    k = int(np.argmax(g))
    thr = float(10 ** ((v[k] + v[k + 1]) / 2))
    return {"thr": thr, "rule": "geometric mid-point of the largest log10-chroma gap of the pooled reference frames",
            "gap_lo": float(10 ** v[k]), "gap_hi": float(10 ** v[k + 1]), "gap_log10": float(g[k]),
            "n_ir_ref_below": int((ir < thr).sum()), "n_ir_ref": int(ir.size),
            "n_dusk_ref_below": int((col < thr).sum()), "n_dusk_ref": int(col.size),
            "n_misclassified": int((ir >= thr).sum()), "v0_rule": ir_threshold_v0(ir, col)}


# ----------------------------------------------------------------------------------------------- geometry
def tile_origins(length: int, tile: int, min_overlap: float = 0.2) -> list[int]:
    if length <= tile:
        return [0]
    n = math.ceil((length - tile) / (tile * (1 - min_overlap))) + 1
    return [int(round(v)) for v in np.linspace(0, length - tile, n)]


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = np.asarray(a, float).reshape(-1, 4), np.asarray(b, float).reshape(-1, 4)
    ix1 = np.maximum(a[:, None, 0], b[None, :, 0])
    iy1 = np.maximum(a[:, None, 1], b[None, :, 1])
    ix2 = np.minimum(a[:, None, 2], b[None, :, 2])
    iy2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(ix2 - ix1, 0, None) * np.clip(iy2 - iy1, 0, None)
    aa = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    ab = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    union = aa[:, None] + ab[None, :] - inter
    return np.where(union > 0, inter / np.where(union > 0, union, 1), 0.0)


def nms(boxes: np.ndarray, scores: np.ndarray, thr: float = NMS_IOU) -> np.ndarray:
    """Greedy NMS -> indices kept (descending score)."""
    order = np.argsort(-np.asarray(scores, float), kind="stable")
    keep = []
    boxes = np.asarray(boxes, float).reshape(-1, 4)
    while order.size:
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break
        ov = iou_matrix(boxes[i:i + 1], boxes[order[1:]])[0]
        order = order[1:][ov <= thr]
    return np.asarray(keep, int)


def mask_boxes(xs_any: np.ndarray, ys_any: np.ndarray) -> np.ndarray:
    """Mask bounding boxes from per-mask column / row occupancy (N, W) / (N, H) -> (N, 4) xyxy (x2, y2 exclusive);
    an empty mask -> NaN row."""
    xs_any, ys_any = np.asarray(xs_any, bool), np.asarray(ys_any, bool)
    n, w = xs_any.shape
    h = ys_any.shape[1]
    out = np.full((n, 4), np.nan)
    has = xs_any.any(1) & ys_any.any(1)
    if has.any():
        xa, ya = xs_any[has].astype(np.uint8), ys_any[has].astype(np.uint8)
        out[has, 0] = xa.argmax(1)
        out[has, 2] = w - xa[:, ::-1].argmax(1)
        out[has, 1] = ya.argmax(1)
        out[has, 3] = h - ya[:, ::-1].argmax(1)
    return out


def touches_inner_edge(box_tile: np.ndarray, ox: int, oy: int, tw: int, th: int, fw: int = FW, fh: int = FH,
                       tol: float = 2.0) -> np.ndarray:
    """box_tile in tile px (N, 4). True where a box touches a tile border that is not also a frame border."""
    b = np.asarray(box_tile, float).reshape(-1, 4)
    left = (b[:, 0] <= tol) & (ox > 0)
    top = (b[:, 1] <= tol) & (oy > 0)
    right = (b[:, 2] >= tw - tol) & (ox + tw < fw)
    bottom = (b[:, 3] >= th - tol) & (oy + th < fh)
    return left | top | right | bottom


# ----------------------------------------------------------------------------------------------- matching / metrics
def match_frame(gt: np.ndarray, pred: np.ndarray, scores: np.ndarray, mode: str = "center") -> np.ndarray:
    """Greedy by score. Returns a bool TP flag per prediction."""
    gt = np.asarray(gt, float).reshape(-1, 4)
    pred = np.asarray(pred, float).reshape(-1, 4)
    tp = np.zeros(len(pred), bool)
    if len(gt) == 0 or len(pred) == 0:
        return tp
    taken = np.zeros(len(gt), bool)
    order = np.argsort(-np.asarray(scores, float), kind="stable")
    if mode == "center":
        gw, gh = gt[:, 2] - gt[:, 0], gt[:, 3] - gt[:, 1]
        g1x, g1y = gt[:, 0] - GROW * gw, gt[:, 1] - GROW * gh
        g2x, g2y = gt[:, 2] + GROW * gw, gt[:, 3] + GROW * gh
        gcx, gcy = (gt[:, 0] + gt[:, 2]) / 2, (gt[:, 1] + gt[:, 3]) / 2
        pcx, pcy = (pred[:, 0] + pred[:, 2]) / 2, (pred[:, 1] + pred[:, 3]) / 2
        for i in order:
            ok = (~taken) & (g1x <= pcx[i]) & (pcx[i] <= g2x) & (g1y <= pcy[i]) & (pcy[i] <= g2y)
            if ok.any():
                d = np.where(ok, (gcx - pcx[i]) ** 2 + (gcy - pcy[i]) ** 2, np.inf)
                j = int(np.argmin(d))
                taken[j] = True
                tp[i] = True
    else:
        ious = iou_matrix(pred, gt)
        for i in order:
            v = np.where(taken, -1.0, ious[i])
            j = int(np.argmax(v))
            if v[j] >= IOU_MATCH:
                taken[j] = True
                tp[i] = True
    return tp


class GroupData:
    """Pooled predictions of one detector over one frame group, pre-sorted for weighted (bootstrap) metrics."""

    def __init__(self, frame_idx: np.ndarray, scores: np.ndarray, tp: np.ndarray, n_gt_per_frame: np.ndarray):
        o = np.argsort(-scores, kind="stable")
        self.f, self.s, self.tp = frame_idx[o], scores[o], tp[o].astype(float)
        self.ngt = np.asarray(n_gt_per_frame, float)
        self.nf = len(self.ngt)
        last = np.ones(len(self.s), bool)
        if len(self.s) > 1:
            last[:-1] = self.s[:-1] != self.s[1:]
        self.cut_idx = np.nonzero(last)[0]

    def curve(self, w: np.ndarray | None = None):
        w = np.ones(self.nf) if w is None else w
        n_gt = float((w * self.ngt).sum())
        pw = w[self.f] if len(self.f) else np.zeros(0)
        ctp = np.cumsum(pw * self.tp)[self.cut_idx] if len(self.f) else np.zeros(0)
        cfp = np.cumsum(pw * (1 - self.tp))[self.cut_idx] if len(self.f) else np.zeros(0)
        return n_gt, ctp, cfp, self.s[self.cut_idx] if len(self.s) else np.zeros(0)

    def metrics(self, w: np.ndarray | None = None) -> dict:
        n_gt, ctp, cfp, cuts = self.curve(w)
        nan = {"AP": np.nan, "R_at_P80": np.nan, "maxF1": np.nan, "P_maxF1": np.nan, "R_maxF1": np.nan,
               "cut_maxF1": np.nan}
        if n_gt <= 0:
            return nan
        if len(ctp) == 0:
            return {"AP": 0.0, "R_at_P80": 0.0, "maxF1": 0.0, "P_maxF1": np.nan, "R_maxF1": 0.0, "cut_maxF1": np.nan}
        denom = ctp + cfp
        prec = np.where(denom > 0, ctp / np.where(denom > 0, denom, 1), 1.0)
        rec = ctp / n_gt
        env = np.maximum.accumulate(prec[::-1])[::-1]
        ap = float(np.sum(np.diff(np.concatenate([[0.0], rec])) * env))
        ok = prec >= P_TARGET
        r80 = float(rec[ok].max()) if ok.any() else 0.0
        f1 = np.where(prec + rec > 0, 2 * prec * rec / np.where(prec + rec > 0, prec + rec, 1), 0.0)
        k = int(np.argmax(f1))
        return {"AP": ap, "R_at_P80": r80, "maxF1": float(f1[k]), "P_maxF1": float(prec[k]), "R_maxF1": float(rec[k]),
                "cut_maxF1": float(cuts[k])}


def count_stats(n_pred: np.ndarray, n_gt: np.ndarray, w: np.ndarray | None = None) -> dict:
    """Per-frame count error e = n_pred - n_gt; weighted summaries + empty-frame FP rate."""
    w = np.ones(len(n_gt)) if w is None else w
    e = n_pred - n_gt
    W = w.sum()
    empty = n_gt == 0
    we = (w * empty).sum()
    return {"count_err_mean": float((w * e).sum() / W) if W else np.nan,
            "count_mae": float((w * np.abs(e)).sum() / W) if W else np.nan,
            "count_exact": float((w * (e == 0)).sum() / W) if W else np.nan,
            "count_under": float((w * (e < 0)).sum() / W) if W else np.nan,
            "count_over": float((w * (e > 0)).sum() / W) if W else np.nan,
            "empty_fp_rate": float((w * empty * (n_pred > 0)).sum() / we) if we else np.nan,
            "empty_fp_per_frame": float((w * empty * n_pred).sum() / we) if we else np.nan}


def boot_weights(n: int, b: int, rng: np.random.Generator) -> np.ndarray:
    return rng.multinomial(n, np.full(n, 1.0 / n), size=b).astype(float)


def ci(vals) -> tuple[float, float]:
    v = np.asarray(vals, float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return (np.nan, np.nan)
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


# ----------------------------------------------------------------------------------------------- scoring
def group_defs(frames: pd.DataFrame) -> list[tuple[str, str, np.ndarray]]:
    g = [("overall", "all", np.ones(len(frames), bool))]
    for col, kind in (("cam_date", "camera x date"), ("light", "lighting"), ("cam_light", "camera x lighting")):
        for v in sorted(frames[col].unique()):
            g.append((kind, v, (frames[col] == v).to_numpy()))
    return g


def score_all(frames: pd.DataFrame, gt: pd.DataFrame, preds: pd.DataFrame, detectors: list[str], n_boot: int = N_BOOT,
              seed: int = SEED) -> dict:
    """frames: frame_id, set, cam_date, light, cam_light; gt: frame_id, x1..y2; preds: detector, frame_id, x1..y2, score.
    Returns dict of DataFrames: metrics_<mode>, diffs_<mode>, pr_<mode>, counts_<mode>."""
    out = {}
    gt_by = {k: v[["x1", "y1", "x2", "y2"]].to_numpy() for k, v in gt.groupby("frame_id")}
    pr_by = {k: v for k, v in preds.groupby(["detector", "frame_id"])}
    for mode in ("center", "iou"):
        mrows, drows, prow, crows = [], [], [], []
        for sname in sorted(frames["set"].unique()):
            fs = frames[frames["set"] == sname].reset_index(drop=True)
            ngt = np.array([len(gt_by.get(f, ())) for f in fs["frame_id"]], float)
            per_det = {}
            for det in detectors:
                fi, sc, tp = [], [], []
                for k, f in enumerate(fs["frame_id"]):
                    p = pr_by.get((det, f))
                    if p is None or len(p) == 0:
                        continue
                    b = p[["x1", "y1", "x2", "y2"]].to_numpy()
                    s = p["score"].to_numpy(float)
                    t = match_frame(gt_by.get(f, np.zeros((0, 4))), b, s, mode)
                    fi.append(np.full(len(s), k)); sc.append(s); tp.append(t)
                fi = np.concatenate(fi) if fi else np.zeros(0, int)
                sc = np.concatenate(sc) if sc else np.zeros(0)
                tp = np.concatenate(tp) if tp else np.zeros(0, bool)
                per_det[det] = (fi, sc, tp)
                # set-level max-F1 cut (a summary of the whole set; then held fixed for counts in every group)
                set_m = GroupData(fi, sc, tp, ngt).metrics()
                cut_set = set_m["cut_maxF1"]
                cuts = {"setF1": cut_set, "fixed025": FIXED_CUT}
                npred = {cn: np.bincount(fi[sc >= c], minlength=len(fs)).astype(float) if np.isfinite(c) else
                         np.zeros(len(fs)) for cn, c in cuts.items()}
                per_det[det] = (fi, sc, tp, cuts, npred)
                for k, f in enumerate(fs["frame_id"]):
                    crows.append({"set": sname, "detector": det, "frame_id": f, "n_gt": int(ngt[k]),
                                  "n_pred_setF1": int(npred["setF1"][k]), "n_pred_025": int(npred["fixed025"][k])})
                gd = GroupData(fi, sc, tp, ngt)
                n_gt_tot, ctp, cfp, cs = gd.curve()
                if n_gt_tot > 0 and len(ctp):
                    den = ctp + cfp
                    for a, b_, c in zip(ctp / n_gt_tot, np.where(den > 0, ctp / np.where(den > 0, den, 1), 1.0), cs):
                        prow.append({"set": sname, "detector": det, "score_cut": c, "recall": a, "precision": b_})
            rng = np.random.default_rng(seed)
            for kind, gname, sel in group_defs(fs):
                idx = np.nonzero(sel)[0]
                if idx.size == 0:
                    continue
                remap = -np.ones(len(fs), int)
                remap[idx] = np.arange(idx.size)
                W = boot_weights(idx.size, n_boot, rng)
                gds = {}
                for det in detectors:
                    fi, sc, tp, cuts, npred = per_det[det]
                    keep = remap[fi] >= 0 if len(fi) else np.zeros(0, bool)
                    gds[det] = GroupData(remap[fi[keep]], sc[keep], tp[keep], ngt[idx])
                    pt = gds[det].metrics()
                    row = {"set": sname, "group_type": kind, "group": gname, "detector": det, "n_frames": int(idx.size),
                           "n_gt": int(ngt[idx].sum()), "n_empty": int((ngt[idx] == 0).sum()), **pt,
                           "cut_setF1": cuts["setF1"]}
                    for cn, tag in (("setF1", ""), ("fixed025", "_025")):
                        cs_ = count_stats(npred[cn][idx], ngt[idx])
                        row.update({k + tag: v for k, v in cs_.items()})
                    boots = {k: [] for k in ("AP", "R_at_P80", "maxF1", "count_mae", "empty_fp_rate", "count_mae_025",
                                             "empty_fp_rate_025")}
                    for w in W:
                        m = gds[det].metrics(w)
                        boots["AP"].append(m["AP"]); boots["R_at_P80"].append(m["R_at_P80"]); boots["maxF1"].append(m["maxF1"])
                        c1 = count_stats(npred["setF1"][idx], ngt[idx], w)
                        c2 = count_stats(npred["fixed025"][idx], ngt[idx], w)
                        boots["count_mae"].append(c1["count_mae"]); boots["empty_fp_rate"].append(c1["empty_fp_rate"])
                        boots["count_mae_025"].append(c2["count_mae"]); boots["empty_fp_rate_025"].append(c2["empty_fp_rate"])
                    for k, v in boots.items():
                        lo, hi = ci(v)
                        row[k + "_lo"], row[k + "_hi"] = lo, hi
                    mrows.append(row)
                # paired difference primary YOLO - each SAM3 variant (same resamples)
                for other in [d for d in detectors if d != PRIMARY[0]]:
                    a, b_ = gds[PRIMARY[0]], gds[other]
                    pa, pb = a.metrics(), b_.metrics()
                    dd = {"AP": [], "R_at_P80": []}
                    for w in W:
                        ma, mb = a.metrics(w), b_.metrics(w)
                        dd["AP"].append(ma["AP"] - mb["AP"]); dd["R_at_P80"].append(ma["R_at_P80"] - mb["R_at_P80"])
                    r = {"set": sname, "group_type": kind, "group": gname, "minuend": PRIMARY[0], "subtrahend": other,
                         "n_frames": int(idx.size), "dAP": pa["AP"] - pb["AP"], "dR_at_P80": pa["R_at_P80"] - pb["R_at_P80"]}
                    r["dAP_lo"], r["dAP_hi"] = ci(dd["AP"])
                    r["dR_at_P80_lo"], r["dR_at_P80_hi"] = ci(dd["R_at_P80"])
                    drows.append(r)
        out[f"metrics_{mode}"] = pd.DataFrame(mrows)
        out[f"diffs_{mode}"] = pd.DataFrame(drows)
        out[f"pr_{mode}"] = pd.DataFrame(prow)
        out[f"counts_{mode}"] = pd.DataFrame(crows)
    return out


# ----------------------------------------------------------------------------------------------- GPU phases
def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def phase_lighting(run: Path, frames: pd.DataFrame, data: Path) -> pd.DataFrame:
    import cv2
    ref = []
    for split in ("train", "val"):
        for img in sorted((data / "labeled_yolo" / "images" / split).glob("CH02_2026-0*.png")):
            cam, d = parse_cam_date(img.stem)
            if d in ("07-06", "06-30"):
                ref.append((d, img))
    ir, col, refrows = [], [], []
    for d, img in ref:
        c = chroma(cv2.imread(str(img), cv2.IMREAD_COLOR))
        (ir if d == "07-06" else col).append(c)
        refrows.append({"image": img.name, "clip": f"CH02 {d}", "chroma": c})
    pd.DataFrame(refrows).to_csv(run / "ref_chroma.csv", index=False)
    th = ir_threshold(ir, col)
    th.update({"definition": "chroma = mean over a 4-px grid of |R-G| + |G-B| (8-bit); IR if chroma < thr",
               "reference_ir": "labelled CH02 07-06 frames (labeled_yolo train+val)",
               "reference_colour": "labelled CH02 06-30 frames (labeled_yolo train+val; 'colour dusk' per the author)",
               "n_ir": len(ir), "n_colour": len(col),
               "ir_min_med_max": [float(np.min(ir)), float(np.median(ir)), float(np.max(ir))],
               "colour_min_med_max": [float(np.min(col)), float(np.median(col)), float(np.max(col))],
               "fixed_at": datetime.now().isoformat(timespec="seconds"), "before_scoring": True})
    (run / "lighting.json").write_text(json.dumps(th, indent=2), encoding="utf-8")
    print(f"lighting threshold {th['thr']:.3f} ({th['rule']}); IR {th['ir_min_med_max']} colour {th['colour_min_med_max']}")
    ch = []
    for p in frames["path"]:
        ch.append(chroma(cv2.imread(p, cv2.IMREAD_COLOR)))
    frames = frames.copy()
    frames["chroma"] = ch
    frames["light"] = np.where(frames["chroma"] < th["thr"], "IR", "colour")
    frames["cam_light"] = frames["camera"] + " " + frames["light"]
    return frames


def phase_yolo(run: Path, frames: pd.DataFrame, weights: Path) -> None:
    import cv2
    from ultralytics import YOLO
    model = YOLO(str(weights))
    rows, timing = [], []
    for sz, det in ((1280, "yolo_v5_1280"), (2560, "yolo_v5_2560")):
        for _, fr in frames.iterrows():
            img = cv2.imread(fr["path"], cv2.IMREAD_COLOR)
            t0 = time.perf_counter()
            r = model.predict(img, imgsz=sz, conf=SCORE_FLOOR, verbose=False)[0]
            dt = time.perf_counter() - t0
            b = r.boxes.xyxy.cpu().numpy()
            s = r.boxes.conf.cpu().numpy()
            for bb, ss in zip(b, s):
                rows.append({"detector": det, "frame_id": fr["frame_id"], "x1": bb[0], "y1": bb[1], "x2": bb[2],
                             "y2": bb[3], "score": float(ss)})
            timing.append({"detector": det, "frame_id": fr["frame_id"], "seconds": dt, "n_tiles": 1})
        print(f"{det}: {len(frames)} frames done")
    pd.DataFrame(rows).to_csv(run / "yolo_preds.csv.gz", index=False)
    pd.DataFrame(timing).to_csv(run / "timing_yolo.csv", index=False)


def build_sam3(half: bool):
    from ultralytics.models.sam import SAM3SemanticPredictor
    ov = dict(model=str(SAM3_WEIGHTS), conf=SCORE_FLOOR, imgsz=1008, save=False, verbose=False)
    if half:
        ov["quantize"] = 16
    return SAM3SemanticPredictor(overrides=ov)


def sam3_tile(pred, tile_bgr: np.ndarray, prompts: list[str]) -> list[dict]:
    """One 1008 x 1008 tile -> per prompt the kept detections (tile px): mask bbox, decoder box, score, mask area."""
    import torch
    pred.set_image(tile_bgr)
    assert list(pred.imgsz) == [1008, 1008], pred.imgsz
    out = []
    for pr in prompts:
        masks, boxes = pred.inference_features(pred.features, src_shape=tile_bgr.shape[:2], text=[pr])
        if masks is None or boxes.shape[0] == 0:
            continue
        with torch.no_grad():
            xs = masks.any(1).cpu().numpy()
            ys = masks.any(2).cpu().numpy()
            area = masks.flatten(1).sum(1).cpu().numpy()
        mb = mask_boxes(xs, ys)
        bx = boxes.float().cpu().numpy()
        for k in range(len(bx)):
            out.append({"prompt": pr, "mx1": mb[k, 0], "my1": mb[k, 1], "mx2": mb[k, 2], "my2": mb[k, 3],
                        "dx1": bx[k, 0], "dy1": bx[k, 1], "dx2": bx[k, 2], "dy2": bx[k, 3], "score": float(bx[k, 4]),
                        "mask_px": int(area[k])})
    pred.reset_image()
    return out


def phase_sam3(run: Path, frames: pd.DataFrame, half: bool = True, tilings: dict | None = None) -> dict:
    import cv2
    import torch
    info = {"requested_fp16": half}
    pred = build_sam3(half)
    # fp16 smoke test on a blank tile; fall back to fp32 on any error
    try:
        sam3_tile(pred, np.zeros((1008, 1008, 3), np.uint8), ["rat"])
        info["precision"] = "fp16" if half else "fp32"
    except Exception as e:  # noqa: BLE001
        info["fp16_error"] = repr(e)[:300]
        pred = build_sam3(False)
        sam3_tile(pred, np.zeros((1008, 1008, 3), np.uint8), ["rat"])
        info["precision"] = "fp32"
    info["device"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    print(f"SAM3 precision {info['precision']} on {info['device']}")
    for tname, cfg in (tilings or TILINGS).items():
        T = cfg["tile"]
        xo, yo = tile_origins(FW, T), tile_origins(FH, T)
        info[f"{tname}_tiles"] = {"x": xo, "y": yo, "n": len(xo) * len(yo)}
        cache = run / f"sam3_tiles_{tname}.csv"
        done = set(pd.read_csv(cache, usecols=["frame_id"])["frame_id"]) if cache.is_file() else set()
        tpath = run / f"timing_sam3_{tname}.csv"
        for n, fr in enumerate(frames.itertuples()):
            if fr.frame_id in done:
                continue
            img = cv2.imread(fr.path, cv2.IMREAD_COLOR)
            torch.cuda.synchronize() if torch.cuda.is_available() else None
            t0 = time.perf_counter()
            rows = []
            for oy in yo:
                for ox in xo:
                    tile = img[oy:oy + T, ox:ox + T]
                    sc = 1.0
                    if T != 1008:
                        tile = cv2.resize(tile, (1008, 1008), interpolation=cv2.INTER_AREA)
                        sc = T / 1008
                    for d in sam3_tile(pred, np.ascontiguousarray(tile), cfg["prompts"]):
                        mt = np.array([[d["mx1"], d["my1"], d["mx2"], d["my2"]]]) * sc
                        edge = bool(touches_inner_edge(mt, ox, oy, T, T)[0]) if np.isfinite(mt).all() else False
                        rows.append({"frame_id": fr.frame_id, "tiling": tname, "prompt": d["prompt"], "tile_x0": ox,
                                     "tile_y0": oy, "x1": d["mx1"] * sc + ox, "y1": d["my1"] * sc + oy,
                                     "x2": d["mx2"] * sc + ox, "y2": d["my2"] * sc + oy,
                                     "dx1": d["dx1"] * sc + ox, "dy1": d["dy1"] * sc + oy, "dx2": d["dx2"] * sc + ox,
                                     "dy2": d["dy2"] * sc + oy, "score": d["score"], "mask_px": d["mask_px"],
                                     "inner_edge": edge})
            torch.cuda.synchronize() if torch.cuda.is_available() else None
            dt = time.perf_counter() - t0
            df = pd.DataFrame(rows, columns=["frame_id", "tiling", "prompt", "tile_x0", "tile_y0", "x1", "y1", "x2", "y2",
                                             "dx1", "dy1", "dx2", "dy2", "score", "mask_px", "inner_edge"])
            if df.empty:   # keep a marker row so a resumed run knows the frame is done
                df = pd.DataFrame([{"frame_id": fr.frame_id, "tiling": tname, "prompt": "", "score": np.nan}],
                                  columns=df.columns)
            df.to_csv(cache, mode="a", header=not cache.is_file(), index=False)
            pd.DataFrame([{"frame_id": fr.frame_id, "tiling": tname, "seconds": dt, "n_tiles": len(xo) * len(yo)}]).to_csv(
                tpath, mode="a", header=not tpath.is_file(), index=False)
            if n % 20 == 0:
                print(f"  {tname} {n + 1}/{len(frames)} frames, {dt:.1f} s/frame", flush=True)
    return info


def merge_sam3(run: Path) -> pd.DataFrame:
    """Per frame x variant: drop empty-mask rows (box NaN), NMS IoU 0.5 across tiles -> frame-level predictions."""
    out = []
    variants = {"sam3_rat_t1008": ("t1008", "rat", False), "sam3_animal_t1008": ("t1008", "animal", False),
                "sam3_ler_t1008": ("t1008_ler", POSTHOC_PROMPT, False), "sam3_ler_t2016": ("t2016_ler", POSTHOC_PROMPT, False),
                "sam3_rat_t2016": ("t2016", "rat", False), "sam3_rat_t1008_edge": ("t1008", "rat", True)}
    tabs = {t: pd.read_csv(run / f"sam3_tiles_{t}.csv") for t in list(TILINGS) + list(POSTHOC_TILINGS)
            if (run / f"sam3_tiles_{t}.csv").is_file()}
    stats = {}
    for det, (tiling, prompt, edge_filter) in variants.items():
        if tiling not in tabs:
            continue
        t = tabs[tiling]
        t = t[(t["prompt"] == prompt) & t["score"].notna()]
        n_empty_mask = int(t[["x1", "y1", "x2", "y2"]].isna().any(axis=1).sum())
        t = t.dropna(subset=["x1", "y1", "x2", "y2"])
        if edge_filter:
            t = t[~t["inner_edge"].astype(bool)]
        n_in, n_kept = len(t), 0
        for f, g in t.groupby("frame_id"):
            b = g[["x1", "y1", "x2", "y2"]].to_numpy()
            k = nms(b, g["score"].to_numpy())
            n_kept += len(k)
            for i in k:
                out.append({"detector": det, "frame_id": f, "x1": b[i, 0], "y1": b[i, 1], "x2": b[i, 2], "y2": b[i, 3],
                            "score": float(g["score"].iloc[i])})
        stats[det] = {"tile_dets": n_in, "after_nms": n_kept, "empty_mask_dropped": n_empty_mask}
    (run / "sam3_merge_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    df = pd.DataFrame(out, columns=["detector", "frame_id", "x1", "y1", "x2", "y2", "score"])
    df.to_csv(run / "sam3_preds.csv.gz", index=False)
    return df


# ----------------------------------------------------------------------------------------------- report
def fmt(v, lo=None, hi=None, d=3):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "–"
    s = f"{v:.{d}f}"
    if lo is not None and np.isfinite(lo):
        s += f" [{lo:.{d}f}, {hi:.{d}f}]"
    return s


LABEL = {"yolo_v5_1280": "YOLO v5 @1280", "yolo_v5_2560": "YOLO v5 @2560", "sam3_rat_t1008": "SAM3 'rat' 1008 tiles",
         "sam3_rat_t2016": "SAM3 'rat' 2016→1008", "sam3_animal_t1008": "SAM3 'animal' 1008",
         "sam3_rat_t1008_edge": "SAM3 'rat' 1008, inner-edge boxes dropped",
         "sam3_ler_t1008": "SAM3 'Long Evans rat' 1008 (post hoc)", "sam3_ler_t2016": "SAM3 'Long Evans rat' 2016→1008 (post hoc)"}


def make_figures(res: dict, figdir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figdir.mkdir(parents=True, exist_ok=True)
    names = []
    pr = res["pr_center"]
    for s in sorted(pr["set"].unique()):
        fig, ax = plt.subplots(figsize=(6, 5))
        for det in PREREG:
            d = pr[(pr["set"] == s) & (pr["detector"] == det)]
            if len(d):
                ax.plot(d["recall"], d["precision"], label=LABEL[det], lw=1.5 if det in PRIMARY else 0.8)
        ax.axhline(P_TARGET, color="grey", ls=":", lw=0.8)
        ax.set_xlabel("recall (centre match)"); ax.set_ylabel("precision"); ax.set_xlim(0, 1); ax.set_ylim(0, 1.02)
        ax.set_title(f"{s}: precision-recall, all frames"); ax.legend(fontsize=7, loc="lower left")
        n = f"sam3_vs_yolo_c1_pr_{s.replace('-', '').lower()}_2026a.png"
        fig.tight_layout(); fig.savefig(figdir / n, dpi=130); plt.close(fig)
        names.append(n)
    m = res["metrics_center"]
    for s in sorted(m["set"].unique()):
        d = m[(m["set"] == s) & (m["group_type"].isin(["overall", "camera x date", "lighting"]))]
        groups = list(dict.fromkeys(d["group"]))
        fig, ax = plt.subplots(figsize=(max(6, 1.3 * len(groups)), 4.5))
        dets = [x for x in PREREG if x != "sam3_rat_t1008_edge"]
        wdt = 0.8 / len(dets)
        for k, det in enumerate(dets):
            dd = d[d["detector"] == det].set_index("group").reindex(groups)
            x = np.arange(len(groups)) + (k - len(dets) / 2 + 0.5) * wdt
            ax.bar(x, dd["AP"], wdt, label=LABEL[det])
            ax.errorbar(x, dd["AP"], yerr=[dd["AP"] - dd["AP_lo"], dd["AP_hi"] - dd["AP"]], fmt="none", ecolor="k", lw=0.7)
        ax.set_xticks(np.arange(len(groups))); ax.set_xticklabels(groups, rotation=30, ha="right", fontsize=8)
        ax.set_ylabel("AP (centre match), 95 % bootstrap CI"); ax.set_ylim(0, 1); ax.set_title(f"{s}: AP per group")
        ax.legend(fontsize=7)
        n = f"sam3_vs_yolo_c1_ap_groups_{s.replace('-', '').lower()}_2026a.png"
        fig.tight_layout(); fig.savefig(figdir / n, dpi=130); plt.close(fig)
        names.append(n)
    return names


def table(m: pd.DataFrame, s: str, kinds: list[str], dets: list[str]) -> list[str]:
    d = m[(m["set"] == s) & (m["group_type"].isin(kinds)) & (m["detector"].isin(dets))]
    lines = ["| group | n fr (gt / empty) | detector | AP | R@P≥0.8 | max F1 (P / R) | count MAE @setF1 | empty FP rate @setF1 | count MAE @0.25 | empty FP @0.25 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for (kind, g), dd in d.groupby(["group_type", "group"], sort=False):
        for det in dets:
            r = dd[dd["detector"] == det]
            if r.empty:
                continue
            r = r.iloc[0]
            lines.append(f"| {g} | {r.n_frames} ({r.n_gt} / {r.n_empty}) | {LABEL[det]} | {fmt(r.AP, r.AP_lo, r.AP_hi, 2)} | "
                         f"{fmt(r.R_at_P80, r.R_at_P80_lo, r.R_at_P80_hi, 2)} | {fmt(r.maxF1, None, None, 2)} "
                         f"({fmt(r.P_maxF1, None, None, 2)} / {fmt(r.R_maxF1, None, None, 2)}) | "
                         f"{fmt(r.count_mae, r.count_mae_lo, r.count_mae_hi, 2)} | "
                         f"{fmt(r.empty_fp_rate, r.empty_fp_rate_lo, r.empty_fp_rate_hi, 2)} | "
                         f"{fmt(r.count_mae_025, r.count_mae_025_lo, r.count_mae_025_hi, 2)} | "
                         f"{fmt(r.empty_fp_rate_025, r.empty_fp_rate_025_lo, r.empty_fp_rate_025_hi, 2)} |")
    return lines


def write_report(run: Path, frames: pd.DataFrame, res: dict, meta: dict, figs: list[str], report_path: Path) -> None:
    lt = json.loads((run / "lighting.json").read_text(encoding="utf-8"))
    m, mi = res["metrics_center"], res["metrics_iou"]
    dfc = res["diffs_center"]
    sets = ["S-val", "S-held"]
    L = [f"# SAM3 zero-shot vs YOLO v5 on labelled cohort-1 panorama frames (2026a)", "",
         f"Driver `cv/cv_field/sam3_vs_yolo_c1.py` (plan `implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md`, step 1); "
         f"run `{run.as_posix()}`; generated {datetime.now():%Y-%m-%d %H:%M}. Inputs = the verified step-0 backup "
         f"`{Path(meta['backup']).as_posix()}`. All numbers are against the author's human labels; no threshold was tuned "
         "on these frames; machine boxes are not labels. The agent did not look at any frame or figure.", "",
         "## Headline", ""]
    L += meta.get("headline", [])
    L += ["", "## Frame sets and lighting", ""]
    for s in sets:
        f = frames[frames["set"] == s]
        L.append(f"- **{s}**: {len(f)} frames, " + ", ".join(f"{k} {v}" for k, v in f["cam_date"].value_counts().sort_index().items())
                 + f"; lighting: " + ", ".join(f"{k} {v}" for k, v in f["light"].value_counts().sort_index().items()) + ".")
    v0 = lt.get("v0_rule", {})
    L += [f"- **IR threshold** (fixed before any scoring, `lighting.json`, `ref_chroma.csv`): thr = **{lt['thr']:.4g}** "
          f"({lt['rule']}: gap {lt.get('gap_lo', float('nan')):.4g} → {lt.get('gap_hi', float('nan')):.4g}, "
          f"{lt.get('gap_log10', float('nan')):.2f} decades). Below thr: {lt.get('n_ir_ref_below')} / {lt.get('n_ir_ref')} "
          f"CH02 07-06 IR reference frames and {lt.get('n_dusk_ref_below')} / {lt.get('n_dusk_ref')} CH02 06-30 'colour dusk' "
          f"reference frames. Reference chroma min / median / max: 07-06 "
          f"{' / '.join(f'{v:.4g}' for v in lt['ir_min_med_max'])}, 06-30 "
          f"{' / '.join(f'{v:.4g}' for v in lt['colour_min_med_max'])}. The first rule (plan; midpoint, else the cut "
          f"misclassifying fewest reference frames) gave thr {v0.get('thr', float('nan')):.4g} inside the grey cluster "
          "because most 06-30 frames are numerically monochrome; replaced before any scoring (plan amendment).",
          f"- Per camera × date lighting split: " + "; ".join(
              f"{k}: " + ", ".join(f"{a} {b}" for a, b in g["light"].value_counts().sort_index().items())
              for k, g in frames.groupby("cam_date")) + ".",
          "", "## Detectors and runtime", ""]
    for k, v in meta.get("runtime", {}).items():
        L.append(f"- {k}: {v}")
    L += [f"- SAM3: precision **{meta['sam3'].get('precision')}** on {meta['sam3'].get('device')}"
          + (f" (fp16 failed: `{meta['sam3']['fp16_error']}`)" if meta["sam3"].get("fp16_error") else "")
          + f"; tiles t1008 x {meta['sam3']['t1008_tiles']['x']} y {meta['sam3']['t1008_tiles']['y']} "
          f"({meta['sam3']['t1008_tiles']['n']} per frame), t2016 x {meta['sam3']['t2016_tiles']['x']} "
          f"y {meta['sam3']['t2016_tiles']['y']} ({meta['sam3']['t2016_tiles']['n']} per frame).",
          f"- SAM3 tile detections → after cross-tile NMS (`sam3_merge_stats.json`): "
          + "; ".join(f"{LABEL[k]} {v['tile_dets']} → {v['after_nms']} (empty masks dropped {v['empty_mask_dropped']})"
                      for k, v in meta.get("merge", {}).items()) + ".",
          f"- YOLO weights `rat_m_v5/best.pt` sha256 `{meta['weights_sha256']}`; SAM3 `sam3.pt` sha256 "
          f"`{meta.get('sam3_sha256', '–')}`; ultralytics {meta['versions'].get('ultralytics')}, torch "
          f"{meta['versions'].get('torch')}.", ""]
    for s in sets:
        L += [f"## {s} — centre match (primary)", ""]
        L += table(m, s, ["overall", "camera x date", "lighting", "camera x lighting"], PREREG)
        L += ["", f"Paired difference YOLO v5 @1280 − SAM3 (same bootstrap resamples), centre match:", "",
              "| group | − SAM3 variant | ΔAP [95 % CI] | ΔR@P≥0.8 [95 % CI] |", "|---|---|---|---|"]
        dd = dfc[(dfc["set"] == s) & (dfc["subtrahend"].str.startswith("sam3")) & (dfc["subtrahend"].isin(PREREG))]
        for r in dd.itertuples():
            L.append(f"| {r.group} | {LABEL[r.subtrahend]} | {fmt(r.dAP, r.dAP_lo, r.dAP_hi, 2)} | "
                     f"{fmt(r.dR_at_P80, r.dR_at_P80_lo, r.dR_at_P80_hi, 2)} |")
        L += ["", f"### {s} — IoU ≥ 0.5 (secondary), primary detectors", ""]
        L += table(mi, s, ["overall", "camera x date", "lighting"], list(PRIMARY) + ["yolo_v5_2560"])
        L.append("")
    L += posthoc_section(res, meta)
    L += ["## Author's numbers (orientation only; different matcher, val split and grouping — not comparable)", "",
          "From `computer_vision/models.md`, v5 per-group validation (ultralytics mAP50 at IoU 0.5): CH01 06-30 + 07-04 "
          ".824 (R .774), CH01 07-07 .608, CH02 colour 06-30 .455, CH02 IR 07-06 .585 (R .545).", "",
          "## Label provenance (diagnostic added after results; plan amendment)", "",
          f"Share of GT boxes near-identical (IoU ≥ {PROV_IOU}) to a v5 @1280 box with conf ≥ {PROV_CONF} — the author's "
          "pre-labelling setting (`prelabel_frames.py` uses the newest `best.pt` = v5; `WORKFLOW.md`: pre-label, then correct). "
          "A share near 1 means the labeller kept v5's boxes, so v5 is scored against itself there.", "",
          "| set | camera × date | GT boxes | median best IoU with a v5 box | share IoU ≥ 0.95 |", "|---|---|---:|---:|---:|"]
    if "label_provenance" in res:
        L += [f"| {r.set} | {r.cam_date} | {r.n_gt} | {r.median_best_iou:.3f} | {r.share_iou_ge_095:.0%} |"
              for r in res["label_provenance"].itertuples()]
    L += ["", "## Caveats", "",
          "- S-val sits seconds from training frames of the same clip and v5's best epoch was selected on it → v5 numbers "
          "on S-val are optimistic. S-held frames were chosen by an earlier model as uncertain → hard for YOLO by "
          "construction; SAM3 never saw any of these frames.",
          "- Ground truth boxes the rat body without the tail; SAM3 masks may include the tail → the IoU match penalises "
          "SAM3 for box convention, the centre match does not. GT can be incomplete (a labeller can miss a rat); every "
          "unmatched prediction counts as a false positive here.",
          "- Groups are small (30–60 frames); read the CIs. The max-F1 summaries are argmax over the scored frames "
          "(descriptive, not a tuned operating point); counts and empty-frame FP use the set-level max-F1 cut of each "
          "detector and the fixed 0.25 cut (the cut used in step 2).",
          "- Lighting is a numeric chroma split, not a camera log; frames near the dusk switch can fall either side. By "
          "it most frames of every clip are monochrome IR — including the CH01 clips and the CH02 06-30 clip that "
          "`models.md` calls daytime / colour (all clips are 21:00–22:00); the author's per-clip day/night labels do not "
          "match the frames' chroma.",
          "- Label provenance (table above): where the GT boxes are v5's own pre-label boxes, v5 is scored against "
          "itself; SAM3 is scored against v5's choices there too. The pre-label conf of that batch is taken as 0.10 "
          "(`WORKFLOW.md` reports re-running the CH02 07-04 batch at 0.10; the script default is 0.2).", ""]
    L += ["## Definitions", "",
          "Units: pixels of the upright 7680 × 2160 panorama. $f$ = frame, $g$ = GT box, $p$ = prediction with score $s_p$; "
          "a group $G$ is a set of frames; $N_{GT}(G)$ = number of GT boxes in $G$.", "",
          "### Centre match (primary)",
          "$$ p \\to g \\iff c_p \\in [x_1^g - 0.25w_g,\\ x_2^g + 0.25w_g] \\times [y_1^g - 0.25h_g,\\ y_2^g + 0.25h_g] $$",
          "where $c_p$ is the prediction's box centre and $w_g, h_g$ the GT box width / height. Predictions are taken in "
          "descending score; each matches the nearest-centre still-unmatched candidate GT, else it is a false positive. "
          "**Text:** is the detection on the rat, tolerant of box-size conventions.", "",
          "### IoU match (secondary)",
          "$$ \\mathrm{IoU}(p,g)=\\frac{|p\\cap g|}{|p\\cup g|} \\ge 0.5 $$ greedy by score, highest-IoU unmatched GT. "
          "**Text:** the usual detection criterion; penalises box-convention differences.", "",
          "### Precision, recall at a score cut $t$",
          "$$ P(t)=\\frac{TP(t)}{TP(t)+FP(t)},\\quad R(t)=\\frac{TP(t)}{N_{GT}(G)} $$ with $TP(t), FP(t)$ the matched / "
          "unmatched predictions with $s_p \\ge t$ pooled over $G$. **Text:** fraction of kept boxes that are rats / "
          "fraction of labelled rats found. Range [0, 1].", "",
          "### Average precision (AP, all-point interpolated)",
          "$$ AP=\\sum_k (R_k-R_{k-1})\\,\\max_{j\\ge k} P_j $$ over the distinct score cuts in descending order "
          "($R_0=0$). **Text:** area under the precision envelope; 1 = every rat found before any false box. Range [0, 1].", "",
          "### Recall at precision ≥ 0.8 ($R_{P\\ge0.8}$)",
          "$$ R_{P\\ge0.8}=\\max\\{R(t): P(t)\\ge 0.8\\} $$ (0 if no cut reaches 0.8). **Text:** how many rats a detector "
          "finds while at most 1 in 5 kept boxes is wrong. The 0.8 target is pre-registered.", "",
          "### Max F1",
          "$$ F1^{*}=\\max_t \\frac{2P(t)R(t)}{P(t)+R(t)},\\quad t^{*}=\\arg\\max_t $$ **Text:** best balance of P and R; "
          "$t^{*}$ is a descriptive argmax, not a tuned threshold. $t^{*}_{set}$ = the argmax over all frames of the set.", "",
          "### Count error and empty-frame false-positive rate at a cut $t$",
          "$$ e_f(t)=n_f^{pred}(t)-n_f^{GT},\\quad MAE=\\frac{1}{|G|}\\sum_f |e_f|,\\quad "
          "FP_{empty}=\\frac{\\#\\{f\\in G: n_f^{GT}=0,\\ n_f^{pred}(t)>0\\}}{\\#\\{f\\in G: n_f^{GT}=0\\}} $$ "
          "**Text:** per-frame miscount (rats) and the share of empty labelled frames with ≥ 1 kept box; at "
          "$t=t^{*}_{set}$ of that detector and at the fixed $t=0.25$.", "",
          "### SAM3 score and boxes",
          "$$ s=\\sigma(\\ell_{det})\\cdot\\sigma(\\ell_{presence}) $$ (ultralytics `inference_features`); box = bounding box "
          "of the thresholded mask, mapped to frame px; cross-tile NMS at IoU 0.5. **Text:** SAM3's confidence that the "
          "prompt is present in the tile times that this query is an instance of it.", "",
          "### Lighting (chroma)",
          "$$ C_f=\\frac{1}{|\\Omega|}\\sum_{(x,y)\\in\\Omega} |R-G|+|G-B| $$ over a 4-px grid $\\Omega$, 8-bit units; IR "
          "if $C_f<$ thr. **Text:** colour content of the frame; ~0 for IR monochrome.", "",
          "### Bootstrap CI",
          "95 % percentile interval of a metric over 1 000 resamples of the group's frames with replacement (seed 0), "
          "predictions re-weighted by their frame's multiplicity; differences use the same resamples for both "
          "detectors (paired).", "", "## Figures", ""]
    for n in figs:
        L.append(f"- `results/2026a/cv_field/figures/sam3_vs_yolo_c1/{n}`")
    L += ["", "## Rerun", "", "```", "C:/Users/Cornell/.conda/envs/cv/python.exe cv/cv_field/sam3_vs_yolo_c1.py "
          f"--score-only {run.as_posix()}   # re-score from the caches", "```", ""]
    report_path.write_text("\n".join(L), encoding="utf-8")


PROV_CONF, PROV_IOU = 0.10, 0.95


def label_provenance(frames: pd.DataFrame, gt: pd.DataFrame, preds: pd.DataFrame) -> pd.DataFrame:
    """Diagnostic (plan amendment, after results): per set x camera-date, the share of GT boxes that are near-identical
    (IoU >= 0.95) to a v5 @1280 box with conf >= 0.10 — the author's pre-label conf (prelabel_frames.py defaults to the
    newest best.pt = v5; WORKFLOW.md: pre-label, then correct)."""
    yp = preds[(preds["detector"] == PRIMARY[0]) & (preds["score"] >= PROV_CONF)]
    yb = {k: v[["x1", "y1", "x2", "y2"]].to_numpy() for k, v in yp.groupby("frame_id")}
    rows = []
    for f, g in gt.groupby("frame_id"):
        b = g[["x1", "y1", "x2", "y2"]].to_numpy()
        best = iou_matrix(b, yb[f]).max(1) if f in yb else np.zeros(len(b))
        rows += [{"frame_id": f, "best_iou": v} for v in best]
    d = pd.DataFrame(rows).merge(frames[["frame_id", "set", "cam_date"]], on="frame_id")
    out = d.groupby(["set", "cam_date"])["best_iou"].agg(
        n_gt="size", median_best_iou="median", share_iou_ge_095=lambda x: float((x >= PROV_IOU).mean())).reset_index()
    return out


def posthoc_verdict(m: pd.DataFrame) -> str:
    """One sentence, by a fixed numeric rule: the prompt changes the conclusion only if a 'Long Evans rat' variant's AP CI
    overlaps v5 @1280's AP CI on S-val overall or on the non-circular held-out clip CH01 07-05."""
    checks = []
    for s, kind, g in (("S-val", "overall", "all"), ("S-held", "camera x date", "CH01 07-05")):
        d = m[(m["set"] == s) & (m["group_type"] == kind) & (m["group"] == g)].set_index("detector")
        if PRIMARY[0] not in d.index:
            continue
        y = d.loc[PRIMARY[0]]
        for det in POSTHOC:
            if det in d.index:
                checks.append((s, g, det, d.loc[det].AP, d.loc[det].AP_hi, y.AP, y.AP_lo))
    if not checks:
        return "Not computed."
    overlap = [c for c in checks if c[4] >= c[6]]
    best = max(checks, key=lambda c: c[3])
    if overlap:
        return ("The prompt changes the conclusion: on " + "; ".join(f"{c[0]} {c[1]} ({LABEL[c[2]]})" for c in overlap)
                + " its AP CI overlaps v5 @1280's.")
    return (f"The prompt does not change the conclusion: every 'Long Evans rat' AP CI lies below v5 @1280's on S-val and on "
            f"held-out CH01 07-05 (best: {LABEL[best[2]]} AP {best[3]:.2f} on {best[0]} {best[1]} vs v5 {best[5]:.2f}).")


def posthoc_section(res: dict, meta: dict) -> list[str]:
    m, mi = res["metrics_center"], res["metrics_iou"]
    if not set(POSTHOC) & set(m["detector"]):
        return []
    dets = [PRIMARY[0], "sam3_rat_t1008", "sam3_rat_t2016", "sam3_animal_t1008"] + POSTHOC
    L = ["## POST HOC — SAM3 prompt 'Long Evans rat' (added after results at the user's suggestion; plan amendment)", "",
         "Not pre-registered. Same 270 frames, matchers, metrics, bootstrap resamples, groups and IR rule as above; "
         "both tilings; image features computed once per tile, then the text prompt; raw outputs cached in "
         "`sam3_tiles_t1008_ler.csv` / `sam3_tiles_t2016_ler.csv`. The 'rat' and 'animal' rows are the cached "
         "pre-registered outputs (not rerun).", ""]
    rt = meta.get("runtime", {})
    L += [f"Runtime: t1008_ler {rt.get('t1008_ler', '–')}; t2016_ler {rt.get('t2016_ler', '–')}.", "",
          f"**{posthoc_verdict(m)}**", ""]
    for s in ("S-val", "S-held"):
        L += [f"### {s} — centre match", ""]
        L += table(m, s, ["overall", "camera x date", "lighting"], dets)
        L += ["", f"### {s} — IoU ≥ 0.5", ""]
        L += table(mi, s, ["overall"], dets)
        L.append("")
    return L


def headline(res: dict, prov: pd.DataFrame | None = None) -> list[str]:
    m = res["metrics_center"]
    out = []
    for s in ("S-val", "S-held"):
        o = m[(m["set"] == s) & (m["group_type"] == "overall")].set_index("detector")
        if o.empty:
            continue
        a, b = o.loc[PRIMARY[0]], o.loc[PRIMARY[1]]
        out.append(f"- **{s}** ({int(a.n_frames)} frames, {int(a.n_gt)} rats; centre match): YOLO v5 @1280 AP "
                   f"{fmt(a.AP, a.AP_lo, a.AP_hi, 2)}, R@P≥0.8 {fmt(a.R_at_P80, a.R_at_P80_lo, a.R_at_P80_hi, 2)}; SAM3 'rat' "
                   f"AP {fmt(b.AP, b.AP_lo, b.AP_hi, 2)}, R@P≥0.8 {fmt(b.R_at_P80, b.R_at_P80_lo, b.R_at_P80_hi, 2)}.")
        ir = m[(m["set"] == s) & (m["group_type"] == "lighting") & (m["group"] == "IR")].set_index("detector")
        if not ir.empty:
            a, b = ir.loc[PRIMARY[0]], ir.loc[PRIMARY[1]]
            out.append(f"  - IR frames ({int(a.n_frames)}, {int(a.n_gt)} rats): YOLO AP {fmt(a.AP, a.AP_lo, a.AP_hi, 2)} vs "
                       f"SAM3 {fmt(b.AP, b.AP_lo, b.AP_hi, 2)}.")
        if prov is not None:
            for r in prov[(prov["set"] == s) & (prov["share_iou_ge_095"] >= 0.9)].itertuples():
                g = m[(m["set"] == s) & (m["group"] == r.cam_date)].set_index("detector")
                out.append(f"  - **Circular group: {r.cam_date}** — {r.share_iou_ge_095:.0%} of its {r.n_gt} GT boxes are "
                           f"v5's own boxes (IoU ≥ {PROV_IOU} with a v5 box at conf ≥ {PROV_CONF}; labels were v5 pre-labels), so "
                           f"its YOLO AP {fmt(g.loc[PRIMARY[0]].AP, None, None, 2)} measures label provenance, not skill.")
            for r in prov[(prov["set"] == s) & (prov["share_iou_ge_095"] < 0.9) & (s == "S-held")].itertuples():
                g = m[(m["set"] == s) & (m["group"] == r.cam_date)].set_index("detector")
                a, b = g.loc[PRIMARY[0]], g.loc[PRIMARY[1]]
                out.append(f"  - Non-circular held-out clip {r.cam_date} ({int(a.n_frames)} frames, {int(a.n_gt)} rats; "
                           f"{r.share_iou_ge_095:.0%} of GT boxes = v5 boxes): YOLO AP {fmt(a.AP, a.AP_lo, a.AP_hi, 2)}, "
                           f"R@P≥0.8 {fmt(a.R_at_P80, a.R_at_P80_lo, a.R_at_P80_hi, 2)}; SAM3 'rat' AP {fmt(b.AP, b.AP_lo, b.AP_hi, 2)}.")
    if set(POSTHOC) & set(m["detector"]):
        for s in ("S-val", "S-held"):
            o = m[(m["set"] == s) & (m["group_type"] == "overall")].set_index("detector")
            out.append(f"- Post hoc ({s}): SAM3 'Long Evans rat' AP " + ", ".join(
                f"{t} {fmt(o.loc[d].AP, o.loc[d].AP_lo, o.loc[d].AP_hi, 2)}" for d, t in
                (("sam3_ler_t1008", "1008"), ("sam3_ler_t2016", "2016→1008")) if d in o.index) + ".")
        out.append(f"- Post hoc: {posthoc_verdict(m)}")
    return out


def phase_score(run: Path, report: bool = True) -> dict:
    frames = pd.read_csv(run / "frames.csv")
    gt = pd.read_csv(run / "gt.csv")
    parts = [pd.read_csv(run / "yolo_preds.csv.gz")]
    parts.append(merge_sam3(run))
    preds = pd.concat(parts, ignore_index=True)
    dets = [d for d in DETECTORS if d in set(preds["detector"])]
    res = score_all(frames, gt, preds, dets)
    for k, v in res.items():
        v.to_csv(run / f"{k}.csv", index=False)
    res = dict(res)
    meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
    meta["merge"] = json.loads((run / "sam3_merge_stats.json").read_text(encoding="utf-8"))
    tm = []
    for p in sorted(run.glob("timing_*.csv")):
        t = pd.read_csv(p)
        key = "detector" if "detector" in t.columns else "tiling"
        for k, g in t.groupby(key):
            tm.append((k, g["seconds"].median(), g["seconds"].mean(), g["n_tiles"].iloc[0]))
    meta["runtime"] = {str(k): f"median {a:.2f} s/frame (mean {b:.2f}; {int(n)} tile(s) per frame)" for k, a, b, n in tm}
    prov = label_provenance(frames, gt, preds)
    prov.to_csv(run / "label_provenance.csv", index=False)
    res["label_provenance"] = prov
    meta["headline"] = headline(res, prov)
    (run / "run.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    if report:
        figdir = REPO / "results" / COHORT / DIRECTION / "figures" / "sam3_vs_yolo_c1"
        figs = make_figures(res, figdir)
        rdir = REPO / "results" / COHORT / DIRECTION / "reports"
        rdir.mkdir(parents=True, exist_ok=True)
        write_report(run, frames, res, meta, figs, rdir / REPORT_NAME)
        ptr = {"run_dir": str(run.resolve()), "cohort": COHORT, "direction": DIRECTION, "analysis": "sam3_vs_yolo_c1",
               "driver": "cv/cv_field/sam3_vs_yolo_c1.py", "report": REPORT_NAME,
               "plan": "implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md", "backup": meta["backup"],
               "weights_sha256": meta["weights_sha256"], "git_commit": meta.get("git_commit"),
               "figures": [f"results/2026a/cv_field/figures/sam3_vs_yolo_c1/{n}" for n in figs]}
        (rdir / POINTER_NAME).write_text(json.dumps(ptr, indent=2) + "\n", encoding="utf-8")
        print(f"report -> {rdir / REPORT_NAME}")
    for line in meta["headline"]:
        print(line)
    return res


def git_commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def run_all(args) -> int:
    backup = Path(args.backup)
    ver = json.loads((backup / "VERIFY.json").read_text(encoding="utf-8"))
    if not ver.get("pass"):
        raise SystemExit("step-0 backup not verified (VERIFY.json pass != true) — step 1 must not start")
    data = data_root(backup)
    weights = backup / "computer_vision" / "outputs" / "runs" / "rat_m_v5" / "weights" / "best.pt"
    if args.run:
        run = Path(args.run)
    else:
        sys.path.insert(0, str(REPO / "common"))
        import output_paths as op
        run = op.run_dir(NAME, COHORT, make_figures=False)
    run.mkdir(parents=True, exist_ok=True)
    phases = args.phases
    if not (run / "run.json").is_file():
        import torch
        import ultralytics
        meta = {"plan": "implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md", "backup": backup.as_posix(),
                "backup_verified_at": ver.get("verified_at"), "weights": weights.as_posix(),
                "weights_sha256": sha256(weights), "sam3_weights": SAM3_WEIGHTS.as_posix(),
                "versions": {"ultralytics": ultralytics.__version__, "torch": torch.__version__,
                             "cuda": torch.version.cuda, "python": sys.version.split()[0]},
                "git_commit": git_commit(), "started": datetime.now().isoformat(timespec="seconds"),
                "params": {"score_floor": SCORE_FLOOR, "grow": GROW, "iou_match": IOU_MATCH, "nms_iou": NMS_IOU,
                           "p_target": P_TARGET, "fixed_cut": FIXED_CUT, "n_boot": N_BOOT, "seed": SEED,
                           "tilings": TILINGS}}
        (run / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
    print(f"run -> {run}")
    if "lighting" in phases or not (run / "frames.csv").is_file():
        frames = inventory(data)
        gt = []
        for r in frames.itertuples():
            for b in read_yolo_labels(r.label):
                gt.append({"frame_id": r.frame_id, "x1": b[0], "y1": b[1], "x2": b[2], "y2": b[3]})
        pd.DataFrame(gt, columns=["frame_id", "x1", "y1", "x2", "y2"]).to_csv(run / "gt.csv", index=False)
        frames = phase_lighting(run, frames, data)
        frames["n_gt"] = frames["frame_id"].map(pd.DataFrame(gt).groupby("frame_id").size()).fillna(0).astype(int)
        frames.to_csv(run / "frames.csv", index=False)
        print(frames.groupby(["set", "cam_date", "light"]).size().to_string())
    frames = pd.read_csv(run / "frames.csv")
    if "yolo" in phases:
        phase_yolo(run, frames, weights)
    if "sam3" in phases:
        if not args.sam3_weights_sha_skip:
            meta["sam3_sha256"] = sha256(SAM3_WEIGHTS)
        meta["sam3"] = phase_sam3(run, frames, half=not args.fp32)
        (run / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if "sam3_posthoc" in phases:
        print(f"nvidia check before SAM3 post hoc: {subprocess.run(['nvidia-smi', '--query-gpu=memory.used,utilization.gpu', '--format=csv,noheader'], capture_output=True, text=True).stdout.strip()}")
        meta["sam3_posthoc"] = phase_sam3(run, frames, half=not args.fp32, tilings=POSTHOC_TILINGS)
        meta["sam3_posthoc"]["prompt"] = POSTHOC_PROMPT
        (run / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if "score" in phases:
        phase_score(run)
    return 0


# ----------------------------------------------------------------------------------------------- selftest
def selftest() -> int:
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

    xo, yo = tile_origins(FW, 1008), tile_origins(FH, 1008)
    ov_x = 1008 - (xo[1] - xo[0])
    ov_y = 1008 - (yo[1] - yo[0])
    rec("1008 tiling: 10 x 3 tiles, covers the frame, overlap >= 20 %",
        len(xo) == 10 and len(yo) == 3 and xo[-1] + 1008 == FW and yo[-1] + 1008 == FH and ov_x >= 0.2 * 1008
        and ov_y >= 0.2 * 1008, f"x {xo} y {yo} overlap {ov_x}/{ov_y}")
    x2, y2 = tile_origins(FW, 2016), tile_origins(FH, 2016)
    rec("2016 tiling: 5 x 2 tiles, covers the frame", len(x2) == 5 and len(y2) == 2 and x2[-1] + 2016 == FW and y2[-1] + 2016 == FH,
        f"x {x2} y {y2}")
    # centre match: grown box, nearest centre, greedy by score
    gt = np.array([[100, 100, 160, 160], [300, 100, 360, 160]], float)
    pred = np.array([[150, 150, 190, 190],     # centre (170,170): inside g0 grown by 15 px -> TP
                     [102, 102, 158, 158],     # second on g0 -> FP (g0 taken by the higher score)
                     [500, 500, 520, 520]], float)
    tp = match_frame(gt, pred, np.array([0.9, 0.8, 0.7]), "center")
    rec("centre match: grown-box hit, one GT per prediction, far box FP", tp.tolist() == [True, False, False], str(tp))
    tp2 = match_frame(gt, pred, np.array([0.8, 0.9, 0.7]), "center")
    rec("centre match is greedy by score", tp2.tolist() == [False, True, False], str(tp2))
    tpi = match_frame(gt, pred, np.array([0.9, 0.8, 0.7]), "iou")
    rec("IoU match: only the tight box matches at 0.5", tpi.tolist() == [False, True, False], str(tpi))
    # AP / R@P80 / max F1 on a known case: 2 GT, scores .9 TP, .8 FP, .7 TP
    gd = GroupData(np.array([0, 0, 1]), np.array([0.9, 0.8, 0.7]), np.array([1, 0, 1], bool), np.array([1, 1]))
    m = gd.metrics()
    rec("AP all-point = 0.5*1 + 0.5*(2/3) = 0.8333", abs(m["AP"] - (0.5 + 0.5 * 2 / 3)) < 1e-9, f"{m['AP']:.4f}")
    rec("R@P>=0.8 = 0.5; max F1 = 0.8 at cut 0.7", abs(m["R_at_P80"] - 0.5) < 1e-9 and abs(m["maxF1"] - 0.8) < 1e-9
        and m["cut_maxF1"] == 0.7, str(m))
    rec("weights of ones reproduce the point estimate", abs(gd.metrics(np.ones(2))["AP"] - m["AP"]) < 1e-12)
    rec("frame weight 2 on frame 1 changes recall denominators",
        abs(gd.metrics(np.array([0.0, 2.0]))["AP"] - 1.0) < 1e-12)
    cs = count_stats(np.array([1, 0, 2, 1]), np.array([1, 0, 0, 3]))
    rec("count stats: MAE, exact, empty FP rate", abs(cs["count_mae"] - 1.0) < 1e-12 and cs["count_exact"] == 0.5
        and cs["empty_fp_rate"] == 0.5, str(cs))
    # threshold rule
    t1 = ir_threshold([0.004, 0.006, 0.010], [0.007, 0.008, 45.0, 30.0])
    rec("IR threshold: geometric mid-point of the largest log gap (0.010 -> 30)", abs(t1["thr"] - np.sqrt(0.010 * 30.0)) < 1e-9
        and t1["n_dusk_ref_below"] == 2 and t1["n_misclassified"] == 0, str({k: v for k, v in t1.items() if k != "v0_rule"}))
    t2 = ir_threshold([0.0, 0.002], [5.0])
    rec("IR threshold: chroma 0 floored at 1e-4", abs(t2["thr"] - np.sqrt(0.002 * 5.0)) < 1e-9, str(t2["thr"]))
    t0 = ir_threshold_v0([0.5, 1.0, 9.0], [8.0, 12.0, 3.0])
    rec("superseded v0 rule kept: min-misclassification cut", t0["n_misclassified"] == 1 and abs(t0["thr"] - 2.0) < 1e-9, str(t0))
    rec("chroma: grey 0, coloured > 0", chroma(np.full((40, 40, 3), 90, np.uint8)) == 0.0
        and chroma(np.dstack([np.full((40, 40), 10, np.uint8), np.full((40, 40), 80, np.uint8),
                              np.full((40, 40), 200, np.uint8)])) == 190.0)
    # mask boxes + edges + NMS merge
    mk = np.zeros((2, 50, 60), bool)
    mk[0, 10:20, 5:15] = True
    xs, ys = mk.any(1), mk.any(2)
    mb = mask_boxes(xs, ys)
    rec("mask bbox (x2/y2 exclusive); empty mask -> NaN", mb[0].tolist() == [5, 10, 15, 20] and np.isnan(mb[1]).all(), str(mb))
    e = touches_inner_edge(np.array([[0, 10, 30, 40], [500, 500, 1008, 600], [100, 0, 150, 40]]), 0, 0, 1008, 1008)
    rec("inner-edge flag: frame border no, inner right border yes", e.tolist() == [False, True, False], str(e))
    b = np.array([[100, 100, 165, 165], [110, 102, 166, 166], [400, 100, 460, 160]], float)
    k = nms(b, np.array([0.5, 0.9, 0.4]))
    rec("NMS keeps the best of two overlapping boxes + the separate one", sorted(k.tolist()) == [1, 2], str(k))
    # end-to-end scoring on synthetic frames
    rng = np.random.default_rng(1)
    fr, gtr, pr = [], [], []
    for i in range(24):
        s = "S-val" if i < 16 else "S-held"
        cam = "CH01" if i % 2 else "CH02"
        light = "IR" if i % 3 == 0 else "colour"
        fid = f"{s}/f{i}"
        fr.append({"frame_id": fid, "set": s, "cam_date": f"{cam} 07-0{i % 2 + 1}", "light": light, "cam_light": f"{cam} {light}"})
        n = i % 3
        for j in range(n):
            x = 200 + 400 * j
            gtr.append({"frame_id": fid, "x1": x, "y1": 300, "x2": x + 65, "y2": 365})
            pr.append({"detector": "yolo_v5_1280", "frame_id": fid, "x1": x + 3, "y1": 302, "x2": x + 66, "y2": 366,
                       "score": 0.6 + 0.3 * rng.random()})
            if rng.random() < 0.6:
                pr.append({"detector": "sam3_rat_t1008", "frame_id": fid, "x1": x - 2, "y1": 298, "x2": x + 140, "y2": 370,
                           "score": 0.3 + 0.5 * rng.random()})
        pr.append({"detector": "sam3_rat_t1008", "frame_id": fid, "x1": 3000, "y1": 50, "x2": 3060, "y2": 110,
                   "score": 0.2 * rng.random()})
    res = score_all(pd.DataFrame(fr), pd.DataFrame(gtr), pd.DataFrame(pr), ["yolo_v5_1280", "sam3_rat_t1008"], n_boot=50)
    mc = res["metrics_center"]
    yo_ = mc[(mc["set"] == "S-val") & (mc["group_type"] == "overall") & (mc["detector"] == "yolo_v5_1280")].iloc[0]
    sa_ = mc[(mc["set"] == "S-val") & (mc["group_type"] == "overall") & (mc["detector"] == "sam3_rat_t1008")].iloc[0]
    rec("synthetic: perfect YOLO -> AP 1, R@P80 1, count MAE 0", abs(yo_.AP - 1) < 1e-9 and yo_.R_at_P80 == 1 and yo_.count_mae == 0,
        f"AP {yo_.AP} R80 {yo_.R_at_P80} mae {yo_.count_mae}")
    rec("synthetic: SAM3 with misses + FPs scores lower; CI brackets the point", sa_.AP < 1 and sa_.AP_lo <= sa_.AP <= sa_.AP_hi,
        f"AP {sa_.AP:.3f} [{sa_.AP_lo:.3f}, {sa_.AP_hi:.3f}]")
    mi = res["metrics_iou"]
    sa_i = mi[(mi["set"] == "S-val") & (mi["group_type"] == "overall") & (mi["detector"] == "sam3_rat_t1008")].iloc[0]
    rec("synthetic: tail-wide SAM3 boxes fail IoU 0.5 but pass the centre match", sa_i.AP < sa_.AP, f"{sa_i.AP:.3f} < {sa_.AP:.3f}")
    d = res["diffs_center"]
    rec("paired differences table present for every group", len(d) == len(mc) // 2, f"{len(d)} rows")
    vm = pd.DataFrame([
        {"set": "S-val", "group_type": "overall", "group": "all", "detector": "yolo_v5_1280", "AP": 0.8, "AP_lo": 0.75, "AP_hi": 0.85},
        {"set": "S-val", "group_type": "overall", "group": "all", "detector": "sam3_ler_t1008", "AP": 0.3, "AP_lo": 0.2, "AP_hi": 0.4},
        {"set": "S-held", "group_type": "camera x date", "group": "CH01 07-05", "detector": "yolo_v5_1280", "AP": 0.5,
         "AP_lo": 0.3, "AP_hi": 0.7},
        {"set": "S-held", "group_type": "camera x date", "group": "CH01 07-05", "detector": "sam3_ler_t2016", "AP": 0.2,
         "AP_lo": 0.1, "AP_hi": 0.35}])
    v = posthoc_verdict(vm)
    rec("post-hoc verdict: an overlapping CI (0.35 >= 0.30) counts as a change", v.startswith("The prompt changes"), v)
    v2 = posthoc_verdict(vm.assign(AP_hi=[0.85, 0.4, 0.7, 0.25]))
    rec("post-hoc verdict: all CIs below -> no change", v2.startswith("The prompt does not change"), v2)
    print(("PASS" if ok else "FAIL") + " — sam3_vs_yolo_c1 self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--backup", default=str(BACKUP))
    ap.add_argument("--run", default=None, help="existing run dir to resume")
    ap.add_argument("--phases", nargs="+", default=["lighting", "yolo", "sam3", "score"],
                    choices=["lighting", "yolo", "sam3", "sam3_posthoc", "score"])
    ap.add_argument("--score-only", default=None, help="run dir: re-score from the caches and rewrite the report")
    ap.add_argument("--fp32", action="store_true", help="run SAM3 in fp32 (default: fp16 if it works)")
    ap.add_argument("--sam3-weights-sha-skip", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.score_only:
        phase_score(Path(a.score_only))
        return 0
    return run_all(a)


if __name__ == "__main__":
    sys.exit(main())
