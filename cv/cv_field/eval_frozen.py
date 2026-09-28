"""eval_frozen.py — honest frozen-07-06 comparison: old 1280 full-frame vs new native-tile (mask-gated).

The money metric for the visible-regime slice. Runs two detector configurations on the SAME frozen ruler and
scores both with the SAME stratified metric (TP/FP/FN + recall@matched-precision on the VISIBLE stratum), so
the before/after is apples-to-apples:

  * BASELINE  — the previous detector, full-frame inference on the stored 1280x712 test frames (rat ~25 px);
  * NATIVE-TILE — the new detector, proposal-free tiled inference on the NATIVE 4512x2512 07-06 frames
    (from E:), mask-gated to the valid field, detections merged to global then scaled back to 1280-frame px.

Both predict at low conf to populate the PR curve; `stratify_test` sweeps the threshold. Visibility tags come
from the dark-hood-contrast heuristic (owner may override via visibility.json). FROZEN-TEST DISCIPLINE: this
only SCORES 07-06 — no training, no gate-fit, no threshold tuning against it.

    python cv_field/eval_frozen.py \
        --baseline-weights runs/detect/rat_field_r2_aug/weights/best.pt \
        --tiled-weights   runs/detect/rat_field_tiles/weights/best.pt \
        --rec-root E: --contrast-thr 20
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CV_ROOT = HERE.parent


def _stored_size(img_path):
    import cv2
    im = cv2.imread(str(img_path))
    return (im.shape[1], im.shape[0])


def baseline_preds(test_root: Path, weights: str, imgsz=1280, conf=0.05, device="0"):
    """Old config: full-frame predict on the stored (1280) test frames. Preds in stored-frame px."""
    from ultralytics import YOLO
    import cv2
    model = YOLO(str(weights))
    out = {}
    for p in sorted((test_root / "images").glob("*.png")):
        r = model.predict(str(p), imgsz=imgsz, conf=conf, device=device, verbose=False, classes=[0])[0]
        dets = []
        if r.boxes is not None and len(r.boxes):
            xy = r.boxes.xyxy.cpu().numpy(); cf = r.boxes.conf.cpu().numpy()
            dets = [(float(a), float(b), float(c), float(d), float(s)) for (a, b, c, d), s in zip(xy, cf)]
        out[p.stem] = dets
    return out


def tiled_preds(test_root: Path, weights: str, rec_root: str, tile=1280, overlap=0.2, conf=0.05,
                device="0", ffmpeg="ffmpeg", use_mask=True):
    """New config: tiled inference on the NATIVE 07-06 frames, mask-gated, scaled back to stored-frame px."""
    from tile_infer import tiled_predict, yolo_predictor
    from tile_dataset import parse_source, extract_native
    from field_mask import FieldMask
    predict_fn = yolo_predictor(weights, imgsz=tile, conf=conf, device=device)
    masks = {ch: FieldMask.load_or_none(ch) for ch in ("CH03", "CH04")} if use_mask else {}
    out = {}
    for p in sorted((test_root / "images").glob("*.png")):
        sw, sh = _stored_size(p)                                 # stored (1280x712) size for GT-space scaling
        parsed = parse_source(p.name, rec_root)
        if parsed is None:
            out[p.stem] = []; continue
        src, off, ch, _stem = parsed
        frame = extract_native(src, off, ffmpeg) if Path(src).exists() else None
        if frame is None:
            print(f"  [miss] native source for {p.stem}: {src}"); out[p.stem] = []; continue
        H, W = frame.shape[:2]
        gb, gs = tiled_predict(predict_fn, frame, tile=tile, overlap=overlap,
                               proposals_px=None, mask=masks.get(ch))
        sx, sy = sw / W, sh / H                                  # native px -> stored-frame px
        out[p.stem] = [(float(b[0] * sx), float(b[1] * sy), float(b[2] * sx), float(b[3] * sy), float(s))
                       for b, s in zip(gb, gs)]
    return out


def gate_filter(preds_by_frame: dict, images_dir: Path, gate, device="0", backend="dino"):
    """Drop detections whose crop the DINOv3 gate scores as background. Crops come from the stored frame (the
    gate was fit on stored-frame crops, so this matches its training distribution). Returns filtered preds."""
    from field_embed import embed_frames
    out = {}
    for stem, dets in preds_by_frame.items():
        if not dets:
            out[stem] = []; continue
        img = images_dir / f"{stem}.png"
        crops = [tuple(d[:4]) for d in dets]
        X, _ = embed_frames([img] * len(crops), backend=backend, device=device, pca_dim=0, crops=crops)
        keep = gate.score(X) >= gate.threshold
        out[stem] = [d for d, k in zip(dets, keep) if k]
    return out


def _recall_all_gt(res):
    """Convenience: recall over ALL gt (visible+occluded) = TP / (TP + FN_visible + occluded-missed)."""
    total_gt = res["gt_visible"] + res["gt_occluded"]
    return round(res["TP"] / total_gt, 4) if total_gt else None


def main() -> None:
    from stratify_test import evaluate, auto_visibility, load_visibility
    ap = argparse.ArgumentParser(description="Frozen-test baseline vs native-tile comparison (visible stratum).")
    ap.add_argument("--test-root", default=str(CV_ROOT / "dataset" / "rat_field_test"))
    ap.add_argument("--baseline-weights", default=str(CV_ROOT / "runs/detect/rat_field_r2_aug/weights/best.pt"))
    ap.add_argument("--tiled-weights", default=str(CV_ROOT / "runs/detect/rat_field_tiles/weights/best.pt"))
    ap.add_argument("--rec-root", default="E:", help="recording root holding 2026-07-06/<CH>/*.mp4 (native)")
    ap.add_argument("--tile", type=int, default=1280)
    ap.add_argument("--conf", type=float, default=0.05)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--target-precision", type=float, default=0.9)
    ap.add_argument("--contrast-thr", type=float, default=20.0)
    ap.add_argument("--gate", help="DINOv3 gate .npz to also apply as a precision post-filter to both detectors")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--device", default="0")
    ap.add_argument("--out", default=str(HERE / "eval_frozen_result.json"))
    args = ap.parse_args()
    test_root = Path(args.test_root)

    vis = load_visibility(test_root)
    if vis is None:
        vis = auto_visibility(test_root, args.contrast_thr)
        (test_root / "visibility.json").write_text(json.dumps(vis, indent=1))
        print(f"[visibility] wrote heuristic visibility.json (contrast thr {args.contrast_thr}) — owner should review")

    print("[baseline] full-frame @1280 on stored frames ...")
    bp = baseline_preds(test_root, args.baseline_weights, imgsz=args.tile, conf=args.conf, device=args.device)
    print("[native-tile] tiled inference on native 07-06 (mask-gated) ...")
    tp = tiled_preds(test_root, args.tiled_weights, args.rec_root, tile=args.tile, conf=args.conf,
                     device=args.device, ffmpeg=args.ffmpeg)

    configs = [("baseline-1280", bp), ("native-tile", tp)]
    if args.gate:
        from dino_gate import DinoGate
        gate = DinoGate.load(args.gate)
        imgs = test_root / "images"
        print(f"[gate] applying DINOv3 gate (thr={gate.threshold:.4f}) as precision post-filter ...")
        configs += [("baseline+gate", gate_filter(bp, imgs, gate, args.device)),
                    ("native+gate", gate_filter(tp, imgs, gate, args.device))]

    rk = f"recall_at_p{int(args.target_precision*100)}"
    results = {name: evaluate(test_root, preds, vis, args.iou, args.target_precision) for name, preds in configs}
    r0 = next(iter(results.values()))
    print("\n================ FROZEN 07-06 — visible-stratum comparison ================")
    print(f"frames={r0['n_frames']}  GT visible={r0['gt_visible']}  occluded={r0['gt_occluded']}  "
          f"(heuristic thr={args.contrast_thr}; IoU={args.iou})")
    hdr = f"{'config':<16}{'TP':>4}{'FP':>5}{'FN_vis':>8}{'precision':>11}{'recall_vis':>12}{rk:>16}{'recall_allGT':>14}"
    print(hdr); print("-" * len(hdr))
    for name, r in results.items():
        print(f"{name:<16}{r['TP']:>4}{r['FP']:>5}{r['FN_visible']:>8}{str(r['precision_all']):>11}"
              f"{str(r['recall_visible']):>12}{str(r[rk]):>16}{str(_recall_all_gt(r)):>14}")
    Path(args.out).write_text(json.dumps({**{k: v for k, v in results.items()},
                                          "contrast_thr": args.contrast_thr, "iou": args.iou}, indent=2))
    print(f"\nfull metrics -> {args.out}")


if __name__ == "__main__":
    main()
