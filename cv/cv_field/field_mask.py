"""field_mask.py — static valid-field region (polygon + crop) for the CH03/CH04 whole-field night cams.

Part of the CH03/CH04 field of view is the enclosure WALL and out-of-field margin where a rat can never
be; wind on those structures is pure false-positive fuel for any motion/detector. Unlike the grass regime,
this geometry is STATIC (the wall does not move night to night), so a mask drawn once pays off on every
frame in every regime — the cheapest precision win available.

This module owns the *consumption* side (loading + geometry); `mask_field.py` is the interactive GUI that
authors the file. The mask is stored in **normalized (0-1) coordinates**, never pixels: the calibration
reference still is 2560x1426 while inference runs at 1280 or native 4512x2512, so pixel coords would not
port across resolutions. `scale_to(w, h)` turns the normalized polygon into pixel coordinates for whatever
resolution the caller runs at.

Mask JSON schema (`cv/configs/CH0X_field_mask.json`, schema `cv_field_mask/1`):
    {
      "channel": "CH03",
      "schema": "cv_field_mask/1",
      "polygon": [[x,y], ...],          # valid-field boundary, normalized 0-1 (fraction of W,H)
      "exclusions": [[[x,y], ...], ...],# optional wall/blind-band holes, normalized 0-1
      "crop": [x1, y1, x2, y2],         # tight bounding box of the valid area, normalized 0-1
      "ref_image_size": [W, H],         # resolution the polygon was drawn on (provenance only)
      "created": "<iso>", "note": "..."
    }

Pure numpy for the geometry (ray-casting point-in-polygon, vectorized over N points); cv2 is imported
lazily only for `apply()` (rasterized crop+zero-out) and `render_mask()`.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

SCHEMA = "cv_field_mask/1"
CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"


def mask_path(channel: str, config_dir: Path | str = CONFIG_DIR) -> Path:
    return Path(config_dir) / f"{channel}_field_mask.json"


# ------------------------------------------------------------------ geometry (pure numpy)
def _points_in_polygon(pts, poly) -> np.ndarray:
    """Vectorized even-odd ray-casting. `pts` (N,2), `poly` (M,2), both in the SAME units. Returns (N,) bool.

    A point exactly on an edge is treated as inside consistently enough for a coarse ROI (no sub-pixel
    guarantee is needed here). Empty/degenerate polygons -> all False."""
    pts = np.asarray(pts, np.float64).reshape(-1, 2)
    poly = np.asarray(poly, np.float64).reshape(-1, 2)
    if len(poly) < 3 or len(pts) == 0:
        return np.zeros(len(pts), bool)
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), bool)
    x1, y1 = poly[:, 0], poly[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    for j in range(len(poly)):
        xi, yi, xj, yj = x1[j], y1[j], x2[j], y2[j]
        # edge straddles the horizontal ray at y, and the crossing x is to the right of the point
        cond = ((yi > y) != (yj > y))
        denom = np.where(yj - yi == 0.0, np.finfo(float).eps, yj - yi)
        x_cross = (xj - xi) * (y - yi) / denom + xi
        inside ^= cond & (x < x_cross)
    return inside


class FieldMask:
    """Loaded valid-field mask. Coordinates are normalized (0-1); resolve to pixels with `scale_to`."""

    def __init__(self, channel, polygon, exclusions=None, crop=None, ref_image_size=None, note=""):
        self.channel = channel
        self.polygon = np.asarray(polygon, np.float64).reshape(-1, 2)
        self.exclusions = [np.asarray(e, np.float64).reshape(-1, 2) for e in (exclusions or [])]
        self.note = note
        self.ref_image_size = tuple(ref_image_size) if ref_image_size else None
        if crop is not None:
            self.crop = tuple(float(v) for v in crop)
        elif len(self.polygon) >= 3:
            self.crop = (float(self.polygon[:, 0].min()), float(self.polygon[:, 1].min()),
                         float(self.polygon[:, 0].max()), float(self.polygon[:, 1].max()))
        else:
            self.crop = (0.0, 0.0, 1.0, 1.0)

    # ---- construction ----
    @classmethod
    def load(cls, channel: str, config_dir: Path | str = CONFIG_DIR) -> "FieldMask":
        d = json.loads(mask_path(channel, config_dir).read_text(encoding="utf-8-sig"))
        return cls(channel=d.get("channel", channel), polygon=d["polygon"],
                   exclusions=d.get("exclusions"), crop=d.get("crop"),
                   ref_image_size=d.get("ref_image_size"), note=d.get("note", ""))

    @classmethod
    def load_or_none(cls, channel: str, config_dir: Path | str = CONFIG_DIR):
        """FieldMask if the file exists, else None — so callers can treat a mask as optional."""
        return cls.load(channel, config_dir) if mask_path(channel, config_dir).exists() else None

    def to_dict(self) -> dict:
        return {"channel": self.channel, "schema": SCHEMA,
                "polygon": [[round(x, 6), round(y, 6)] for x, y in self.polygon.tolist()],
                "exclusions": [[[round(x, 6), round(y, 6)] for x, y in e.tolist()] for e in self.exclusions],
                "crop": [round(v, 6) for v in self.crop],
                "ref_image_size": list(self.ref_image_size) if self.ref_image_size else None,
                "note": self.note}

    def save(self, config_dir: Path | str = CONFIG_DIR, created: str = "") -> Path:
        p = mask_path(self.channel, config_dir)
        d = self.to_dict()
        if created:
            d["created"] = created
        p.write_text(json.dumps(d, indent=2), encoding="utf-8")
        return p

    # ---- geometry in pixel space ----
    def scale_to(self, w: int, h: int):
        """(polygon_px, exclusions_px, crop_px) at pixel resolution (w, h). crop_px = int (x1,y1,x2,y2)."""
        s = np.array([w, h], np.float64)
        poly = self.polygon * s
        excl = [e * s for e in self.exclusions]
        cx1, cy1, cx2, cy2 = self.crop
        crop = (int(round(cx1 * w)), int(round(cy1 * h)), int(round(cx2 * w)), int(round(cy2 * h)))
        return poly, excl, crop

    def contains(self, pts_px, w: int, h: int) -> np.ndarray:
        """(N,) bool: is each pixel point inside the valid field (inside polygon AND outside every
        exclusion) at resolution (w, h)?"""
        poly, excl, _ = self.scale_to(w, h)
        inside = _points_in_polygon(pts_px, poly)
        for e in excl:
            inside &= ~_points_in_polygon(pts_px, e)
        return inside

    def contains_norm(self, pts_norm) -> np.ndarray:
        """(N,) bool for points already in normalized 0-1 coordinates (resolution-independent)."""
        return self.contains(np.asarray(pts_norm, np.float64) * np.array([1.0, 1.0]), 1, 1)

    def box_center_inside(self, box_px, w: int, h: int) -> bool:
        """True if the CENTROID of a pixel box (x1,y1,x2,y2) is inside the valid field."""
        x1, y1, x2, y2 = box_px
        c = np.array([[(x1 + x2) / 2.0, (y1 + y2) / 2.0]], np.float64)
        return bool(self.contains(c, w, h)[0])

    def filter_boxes(self, boxes_px, w: int, h: int):
        """Keep only boxes whose centroid is inside the valid field. Returns (kept_boxes, kept_index)."""
        kept, idx = [], []
        for i, b in enumerate(boxes_px):
            if self.box_center_inside(b, w, h):
                kept.append(b); idx.append(i)
        return kept, idx

    # ---- rasterization (cv2, lazy) ----
    def render_mask(self, w: int, h: int) -> np.ndarray:
        """Boolean (h, w) mask: True inside the valid field. cv2 fillPoly."""
        import cv2
        poly, excl, _ = self.scale_to(w, h)
        m = np.zeros((h, w), np.uint8)
        cv2.fillPoly(m, [poly.round().astype(np.int32)], 1)
        for e in excl:
            cv2.fillPoly(m, [e.round().astype(np.int32)], 0)
        return m.astype(bool)

    def apply(self, frame, zero_value: int = 0, do_crop: bool = True):
        """Zero out everything outside the valid field, then (optionally) crop to the valid bounding box.

        Returns (out_frame, crop_px) where crop_px = (x1,y1,x2,y2) in the INPUT frame's pixel coords, so a
        caller can map detections in the cropped frame back to full-frame coordinates."""
        frame = np.asarray(frame)
        h, w = frame.shape[:2]
        m = self.render_mask(w, h)
        out = frame.copy()
        out[~m] = zero_value
        crop = (0, 0, w, h)
        if do_crop:
            _, _, crop = self.scale_to(w, h)
            x1, y1, x2, y2 = crop
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 - x1 >= 2 and y2 - y1 >= 2:
                out = out[y1:y2, x1:x2]
                crop = (x1, y1, x2, y2)
        return out, crop


# ------------------------------------------------------------------ calib-projected field rectangle (GUI guide)
def projected_field_polygon_norm(channel: str, config_dir: Path | str = CONFIG_DIR, n_per_edge: int = 12):
    """Normalized (0-1) polygon of the surveyed field rectangle projected into this camera's image, for the
    GUI to draw as a *tracing guide*. Returns None if no calibration exists.

    Densely samples the 4 field edges (world cm) and maps them to pixels via the inverse calibration, then
    normalizes by the calib reference image size. NOTE: this is only trustworthy where the calibration is
    well-constrained (near its landmarks); the far field is extrapolated, so it is a hint to trace against,
    not ground truth."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # cv/ on path -> field_coords
    try:
        import field_coords as fc
    except Exception:  # noqa: BLE001
        return None
    try:
        calib = fc.load_calib(channel, config_dir)
    except FileNotFoundError:
        return None
    isz = calib.get("image_size")
    if not isz:
        return None
    W, H = isz
    fx, fy = fc.FIELD_X_CM, fc.FIELD_Y_CM
    corners = [(0.0, 0.0), (fx, 0.0), (fx, fy), (0.0, fy)]
    edge_cm = []
    for i in range(4):
        a = np.array(corners[i]); b = np.array(corners[(i + 1) % 4])
        for t in np.linspace(0, 1, n_per_edge, endpoint=False):
            edge_cm.append(a + (b - a) * t)
    px = fc.to_pixel(channel, np.asarray(edge_cm, float), config_dir=config_dir, calib=calib)
    norm = px / np.array([W, H], float)
    return norm
