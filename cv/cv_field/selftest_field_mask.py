"""selftest_field_mask.py — offline PASS/FAIL for the valid-field mask geometry (numpy/cv2 only, no GPU/data).

Verifies the pieces the whole precision layer rests on:
  * point-in-polygon correctness (inside / outside / excluded-hole),
  * NORMALIZED coords classify a point consistently across 1280 / 2560 / 4512 resolutions (the reason the
    mask is stored normalized, not in the calib's 2560x1426 pixels),
  * box-centroid filtering (what field_motion uses to drop wall proposals),
  * render_mask + apply(crop) round-trip,
  * the calib-projected guide polygon runs (best-effort; only asserts shape when a calibration exists).

Run:  python cv_field/selftest_field_mask.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from field_mask import FieldMask, projected_field_polygon_norm   # noqa: E402


def main() -> int:
    ok = True

    def chk(name, cond):
        nonlocal ok; ok = ok and bool(cond); print(f"  [{'PASS' if cond else 'FAIL'}] {name}")

    # a valid rectangle 0.1..0.9 in x, 0.2..0.8 in y, with a wall wedge cut from the lower-left corner
    poly = [[0.1, 0.2], [0.9, 0.2], [0.9, 0.8], [0.1, 0.8]]
    excl = [[[0.1, 0.2], [0.35, 0.2], [0.1, 0.5]]]            # triangular "wall" hole
    m = FieldMask("CH03", polygon=poly, exclusions=excl, ref_image_size=(2560, 1426))

    # (1) point-in-polygon at a concrete resolution
    W, H = 1280, 712
    chk("centre inside", m.contains([[0.5 * W, 0.5 * H]], W, H)[0])
    chk("far outside polygon", not m.contains([[0.02 * W, 0.02 * H]], W, H)[0])
    chk("inside the excluded wall wedge -> outside", not m.contains([[0.15 * W, 0.25 * H]], W, H)[0])
    chk("just inside valid, clear of wedge", m.contains([[0.6 * W, 0.3 * H]], W, H)[0])

    # (2) SAME normalized point classifies consistently across resolutions
    probe = (0.7, 0.5)                                        # clearly inside
    votes = [m.contains([[probe[0] * w, probe[1] * h]], w, h)[0]
             for (w, h) in [(1280, 712), (2560, 1426), (4512, 2512)]]
    chk("normalized point resolution-invariant (all inside)", all(votes))
    probe_out = (0.05, 0.05)
    votes_out = [m.contains([[probe_out[0] * w, probe_out[1] * h]], w, h)[0]
                 for (w, h) in [(1280, 712), (2560, 1426), (4512, 2512)]]
    chk("normalized outside point resolution-invariant (none inside)", not any(votes_out))

    # (3) box-centroid filtering (field_motion's gate): a wall box is dropped, a field box kept
    boxes = [(int(0.55 * W), int(0.35 * H), int(0.6 * W), int(0.4 * H)),      # in field
             (int(0.12 * W), int(0.24 * H), int(0.16 * W), int(0.28 * H))]    # in the wall wedge
    kept, idx = m.filter_boxes(boxes, W, H)
    chk("filter_boxes keeps the field box only", idx == [0])

    # (4) render_mask + apply
    rm = m.render_mask(W, H)
    chk("render_mask shape", rm.shape == (H, W))
    chk("render_mask interior true", rm[int(0.5 * H), int(0.5 * W)])
    chk("render_mask wedge false", not rm[int(0.25 * H), int(0.15 * W)])
    frame = np.full((H, W, 3), 200, np.uint8)
    out, crop = m.apply(frame)
    cx1, cy1, cx2, cy2 = crop
    chk("apply crop within frame", 0 <= cx1 < cx2 <= W and 0 <= cy1 < cy2 <= H)
    chk("apply crop matches valid bbox x", abs(cx1 - int(round(0.1 * W))) <= 1)

    # (5) save/load round-trip
    with tempfile.TemporaryDirectory() as d:
        m.save(d, created="2026-07-13T00:00:00")
        m2 = FieldMask.load("CH03", d)
        chk("round-trip polygon", np.allclose(m2.polygon, np.asarray(poly)))
        chk("round-trip exclusions", len(m2.exclusions) == 1)
        chk("round-trip classification", m2.contains([[0.7 * W, 0.5 * H]], W, H)[0])

    # (6) calib-projected guide (best-effort — only asserts shape if a CH03 calibration exists)
    guide = projected_field_polygon_norm("CH03")
    if guide is not None:
        chk("projected guide is (N,2)", guide.ndim == 2 and guide.shape[1] == 2 and len(guide) >= 8)
    else:
        print("  [skip] no CH03 calibration reachable for the projected-guide check")

    print("PASS — field_mask self-test" if ok else "FAIL — field_mask self-test")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
