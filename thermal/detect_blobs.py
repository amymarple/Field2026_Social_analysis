"""thermal/detect_blobs.py — unsupervised warm-blob (rat) detector for AGC white-hot thermal video.

The 108/109 thermal cameras record 1 fps, 1280x960, HEVC, monochrome, with AUTO-GAIN-CONTROL: the
gray->temperature mapping is re-scaled EVERY frame (see the burned-in colorbar min/max), so absolute
pixel brightness is NOT comparable across frames. This detector is therefore AGC-robust by construction:

  primary cue   = morphological white TOP-HAT (responds to LOCAL compact-bright structure regardless of
                  the global gain) -> ROBUST-ADAPTIVE threshold (fixed floor guarded by median+MAD; NOT
                  Otsu, which invents a foreground in the majority-empty frames) -> morphology ->
                  connected components -> geometry filter (area/aspect/extent/solidity/mean-response)
  static guard  = pixels persistently foreground AND part of a LARGE or ELONGATED structure (survey pole,
                  berms, wires) are erased from the mask, so a rat sitting on the pole SEPARATES into its
                  own compact component. Compact persistent blobs (a possible long-resting rat) are NOT
                  erased.
  overlay guard = static OSD rectangles (timestamp, colorbar+labels, 'Thermal' text) + a 6 px border, plus
                  a DYNAMIC red-chroma mask of the moving spot-meter crosshair and its white readout text
                  (it tracks the hottest pixel and roams onto warm structures, so a static mask can't
                  catch it); the diamond sits ON the true rat, so only a tight rightward text box is masked
  motion score  = frame-difference support, recorded per blob (never a gate — a huddled rat must survive
                  on brightness alone)
  linking       = greedy nearest-centroid tracker (110 px gate at 1 fps) with short gap tolerance

OUTPUTS ARE RELATIVE WARM-BLOB DETECTIONS + SHORT TRACKS. NOT temperature (AGC render, not radiometric),
NOT animal identity, NOT a certified count (a lower bound — occlusion / refuge / haze suppress true rats).
The camera's burned-in clock runs ~1 h BEHIND the filename time; times here are frame index + filename
wallclock only. UNSUPERVISED and UNVALIDATED: precision/recall unknown; every parameter is a starting
point that needs a per-hour sweep + a small human spot-check before any count is trusted.

Usage:
  python thermal/detect_blobs.py --video <mp4> --out <dir> [--max-frames N] [--start-sec S] [--preview]
  python thermal/detect_blobs.py --cam 108_thermal --date 2026-07-01 --hour 21 --out <dir> --preview
  python thermal/detect_blobs.py --selftest        # offline synthetic PASS/FAIL (no video, no GPU)

Frames are read via an ffmpeg pipe as BGR (robust for network HEVC, and the red spot-meter chroma is
needed for the dynamic crosshair mask); the top-hat runs on the luma channel.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


# --------------------------------------------------------------------------------------
# Parameters — defaults grounded in the 10-probe (108/109 x night hours) characterization sweep.
# --------------------------------------------------------------------------------------
@dataclass
class Params:
    # --- morphology geometry, pixels @ 1280x960 ---
    tophat_se: int = 61          # white top-hat SE (odd, elliptical); > largest rat minor-axis (~55 px huddle)
    open_se: int = 3             # opening kernel to drop speckle / hot pixels
    close_se: int = 7            # closing kernel to knit a soft-edged thermal blob together
    # --- threshold ---
    thresh_method: str = "robust"  # "robust" (floor guarded by median+MAD) | "otsu" | "percentile"
    tophat_floor: int = 50       # absolute top-hat floor (0-255). 50 = F1 knee on the 108/21:00 labeled
                                 # set (precision 0.80, recall 0.42); use 45 for +recall, 55 for precision 0.92
    thresh_pct: float = 99.0     # used when thresh_method == "percentile"
    # --- candidate geometry (all must hold) ---
    min_area: int = 120          # px^2 (rejects ~8-15 px dust/hot-pixel specks)
    max_area: int = 4500         # px^2 (above = structure/glare; a real huddle flagged, see notes)
    min_extent: float = 0.35     # area / bbox_area
    max_aspect: float = 4.5      # max(w,h)/min(w,h); rejects the pole / wires / berm edges
    min_solidity: float = 0.5    # area / convex-hull area; rejects thin/fragmented wire+berm pieces
    mean_resp_frac: float = 0.5  # component mean top-hat must exceed this * tophat_floor (kills diffuse texture)
    overlay_overlap_drop: float = 0.30
    border_px: int = 6
    # --- localization: split a blob on its top-hat peaks + report an intensity-weighted centroid.
    # OFF by default: on the 108/21:00 labeled set it gave ZERO recall gain (identical TP at every floor)
    # and ADDED false positives (over-split rats), i.e. the recall ceiling is genuinely-hard cases (merges/
    # occlusion/faint-on-structure), not a centroid artifact. Kept as an opt-in for denser/other data. ---
    localize: bool = False
    split_max_area_mult: float = 2.5  # split components up to this * max_area (a 2-rat merge); above = structure
    split_prom_frac: float = 0.55     # a split peak must be >= this fraction of the blob's own max top-hat
    # --- learned static-structure suppression ---
    static_persist_frac: float = 0.6   # a pixel foreground in > this fraction of frames is "persistent"
    static_warmup: int = 45            # frames to accumulate before trusting the static mask
    static_struct_min_area: int = 4500   # a persistent blob becomes STATIC only if large OR...
    static_struct_min_aspect: float = 4.0  # ...elongated (so a compact resting rat is NOT erased)
    # --- dynamic spot-meter crosshair (needs the color decode) ---
    red_chroma_thresh: int = 45  # R - max(G,B) > this => the red diamond
    readout_w: int = 170         # width of the rightward white 'NN.N C' readout box to mask
    readout_h: int = 40
    # --- motion score (informational only) ---
    motion_diff: int = 12        # abs frame-diff (0-255) counted as motion
    # --- temporal MOTION detection channel (recovers faint-but-moving rats the top-hat floor misses) ---
    use_motion: bool = False     # OR-fuse a motion channel with the top-hat channel
    motion_bg_frames: int = 20   # EMA background window (s @1fps); a warm object slower than this is absorbed
    motion_resid_thresh: int = 25  # normalized (AGC-undone) resid above background counted as motion foreground
    motion_support_frac: float = 0.15  # a blob qualifies via motion if >= this fraction of it is motion px
    # --- tracker ---
    track_max_dist: float = 110.0  # ~ rat @0.5 m/s, ~0.4-0.5 cm/px, 1 fps
    track_max_gap: int = 3
    track_min_len: int = 2


# Static burned-in OSD rectangles [x, y, w, h] @ 1280x960 (108 & 109 agree to ~10-20 px; re-verify per
# camera/night). We mask ONLY the truly-static OSD: timestamp, the colorbar BAR, its top & bottom numeric
# labels, and 'Thermal'. We deliberately do NOT mask the tall mid-height right strip — real rats appear on
# the right-side berm there, and the only thing that roams into it is the spot-meter readout, which the
# DYNAMIC red-chroma mask already removes. (An earlier wide [1085,175,195,570] block cost ~11 rats of recall.)
OVERLAY_MASKS: dict[str, list[list[int]]] = {
    "108_thermal": [[855, 28, 410, 60], [1190, 226, 55, 490], [1100, 176, 120, 46],
                    [1100, 686, 120, 48], [18, 886, 155, 74]],
    "109_thermal": [[855, 28, 410, 60], [1190, 226, 55, 490], [1100, 176, 120, 46],
                    [1100, 686, 120, 48], [18, 886, 155, 74]],
}
DEFAULT_OVERLAYS = OVERLAY_MASKS["108_thermal"]


# --------------------------------------------------------------------------------------
# Core detection (pure functions over arrays — exercised by --selftest without any video)
# --------------------------------------------------------------------------------------
def build_overlay_mask(h: int, w: int, rects: list[list[int]], border_px: int = 0) -> np.ndarray:
    """Return a uint8 HxW mask, 255 where the burned-in OSD / border lives, else 0."""
    m = np.zeros((h, w), np.uint8)
    for (x, y, ww, hh) in rects:
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(w, x + ww), min(h, y + hh)
        if x1 > x0 and y1 > y0:
            m[y0:y1, x0:x1] = 255
    if border_px > 0:
        m[:border_px, :] = 255
        m[-border_px:, :] = 255
        m[:, :border_px] = 255
        m[:, -border_px:] = 255
    return m


def _odd(n: int) -> int:
    n = int(round(n))
    return n if n % 2 == 1 else n + 1


def white_tophat(gray: np.ndarray, se_size: int) -> np.ndarray:
    """White top-hat: gray - opening(gray). Highlights compact bright structure <= se_size, AGC-robust."""
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_odd(se_size), _odd(se_size)))
    return cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, se)


def robust_norm(gray: np.ndarray, overlay_mask: np.ndarray | None) -> np.ndarray:
    """Undo the per-frame AGC affine drift: map to a robust z-scale (median->128, MAD->40) over non-OSD
    pixels. Cross-frame comparable, so temporal differencing sees real warmth change, not gain rescaling."""
    m = gray[overlay_mask == 0] if (overlay_mask is not None and np.any(overlay_mask)) else gray.reshape(-1)
    med = float(np.median(m))
    mad = float(np.median(np.abs(m - med))) + 1e-3
    return np.clip(128.0 + 40.0 * (gray.astype(np.float32) - med) / (1.4826 * mad), 0, 255)


def _threshold(th: np.ndarray, params: Params) -> np.ndarray:
    """Binary foreground from the top-hat response."""
    if params.thresh_method == "robust":
        med = float(np.median(th))
        mad = float(np.median(np.abs(th.astype(np.float32) - med)))
        T = max(float(params.tophat_floor), med + 5.0 * 1.4826 * mad)
        return (th >= T).astype(np.uint8) * 255
    if params.thresh_method == "otsu":
        _, bw = cv2.threshold(th, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        cut = np.percentile(th, params.thresh_pct)
        bw = (th >= max(cut, 1)).astype(np.uint8) * 255
    bw[th < params.tophat_floor] = 0
    return bw


def _tophat_foreground(img: np.ndarray, params: Params, overlay_mask: np.ndarray | None):
    """White top-hat -> robust threshold -> morphology. Returns (th float map, bw uint8 0/255, osd_dilated)."""
    g = img.copy()
    dil = None
    if overlay_mask is not None and np.any(overlay_mask):
        # Neutralize OSD with the frame MEDIAN (not 0): a sharp dark rectangle would make the top-hat
        # paint a bright rim just outside the mask. Dilate the OSD by the top-hat scale for suppression.
        g[overlay_mask > 0] = int(np.median(g))
        dil = cv2.dilate(overlay_mask, cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (_odd(params.tophat_se), _odd(params.tophat_se))))

    th = white_tophat(g, params.tophat_se)  # local & AGC-robust: no global normalization needed
    bw = _threshold(th, params)
    if params.open_se > 1:
        bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (params.open_se, params.open_se)))
    if params.close_se > 1:
        bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (params.close_se, params.close_se)))
    return th, bw, dil


def _solidity(comp_u8: np.ndarray, area: int) -> float:
    cnts, _ = cv2.findContours(comp_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return 1.0
    hull = cv2.convexHull(np.vstack(cnts))
    ha = cv2.contourArea(hull)
    return area / ha if ha > 0 else 1.0


def _peak_seeds(thf: np.ndarray, params: Params) -> list[tuple[float, float]]:
    """Prominent local maxima of the (masked) top-hat: smoothed, separated by ~tophat_se/2, and PROMINENT
    (≥ split_prom_frac of the component's own max) so noise ripples near the floor don't shatter a rat.
    One rat → one seed; two comparably-bright rats in one blob → two. Returns (x,y) seeds."""
    if float(thf.max()) < params.tophat_floor:
        return []
    sm = cv2.GaussianBlur(thf, (0, 0), max(1.0, params.tophat_se / 6.0))
    k = _odd(max(9, params.tophat_se // 2))
    d = cv2.dilate(sm, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    hi = max(float(params.tophat_floor), params.split_prom_frac * float(sm.max()))
    peak = ((sm >= d - 1e-3) & (sm >= hi)).astype(np.uint8)
    if not peak.any():
        return []
    n, _lab, _st, cent = cv2.connectedComponentsWithStats(peak, 8)
    return [(float(cent[i][0]), float(cent[i][1])) for i in range(1, n)]


def _split_and_localize(th: np.ndarray, comp: np.ndarray, params: Params):
    """Split one foreground component on its top-hat peaks and report an INTENSITY-WEIGHTED centroid per
    sub-blob. A rat merged with dim structure keeps a bright peak, so the weighted centroid lands on the
    rat (not the blob's geometric middle); two rats in one blob split into two. Yields dicts per sub-blob.
    """
    ys, xs = np.where(comp)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    sub = comp[y0:y1, x0:x1]
    thsub = (th[y0:y1, x0:x1].astype(np.float32)) * sub
    seeds = _peak_seeds(thsub, params)

    def emit(mask_local, ly, lx):
        wy, wx = np.where(mask_local)
        wt = thsub[wy, wx]
        s = float(wt.sum())
        cx = x0 + (float((wx * wt).sum()) / s if s > 0 else float(wx.mean()))
        cy = y0 + (float((wy * wt).sum()) / s if s > 0 else float(wy.mean()))
        bx, by = int(wx.min()), int(wy.min())
        full = np.zeros_like(comp)
        full[wy + y0, wx + x0] = True
        return dict(mask=full, cx=cx, cy=cy, x=x0 + bx, y=y0 + by,
                    w=int(wx.max()) - bx + 1, h=int(wy.max()) - by + 1, area=int(mask_local.sum()))

    if len(seeds) <= 1:
        return [emit(sub, y0, x0)]
    # assign each foreground pixel to its nearest peak (Voronoi within the component bbox)
    fy, fx = np.where(sub)
    sa = np.array(seeds)  # (k, [x,y]) in local coords
    assign = ((fx[:, None] - sa[None, :, 0]) ** 2 + (fy[:, None] - sa[None, :, 1]) ** 2).argmin(1)
    out = []
    for si in range(len(seeds)):
        m = assign == si
        if int(m.sum()) < params.min_area:
            continue
        ml = np.zeros_like(sub)
        ml[fy[m], fx[m]] = True
        out.append(emit(ml, y0, x0))
    return out or [emit(sub, y0, x0)]


def detect_blobs(img: np.ndarray, params: Params, overlay_mask: np.ndarray | None,
                 static_mask: np.ndarray | None = None, motion_map: np.ndarray | None = None,
                 motion_bw: np.ndarray | None = None):
    """Detect warm blobs in one white-hot frame. Returns (detections, raw_foreground_bw).

    img         : HxW uint8 luma (white-hot). No global normalization — the white top-hat is LOCAL and
                  inherently robust to the per-frame AGC gain.
    overlay_mask: HxW uint8, 255 where OSD/border/dynamic-crosshair lives (blobs overlapping it dropped).
    static_mask : HxW uint8, 255 where persistently-static LARGE/ELONGATED structure lives (pole, wires,
                  berms). Those pixels are ERASED from the foreground BEFORE components, so a rat on the
                  pole SEPARATES into its own compact blob rather than merging into a rejected pole shape.
    motion_map  : optional HxW uint8 (0/255) frame-difference mask, used only to SCORE motion support.
    motion_bw   : optional HxW uint8 (0/255) temporal MOTION foreground. When given it is OR-fused into the
                  detection foreground so a faint-but-MOVING rat (low top-hat contrast) is still found, and
                  a blob that is motion-supported is exempt from the top-hat mean-response gate. Each blob
                  is tagged source in {tophat, motion, both}.

    The returned raw foreground (before the static erase) is what the caller accumulates to LEARN the
    static mask over time. The motion channel is merged at the DETECTION level (a separate component pass +
    centroid dedupe), NOT by OR-ing pixels — a diffuse motion residual would otherwise bloat/merge the clean
    top-hat blobs and destroy them.
    """
    h, w = img.shape[:2]
    th, bw_raw, dil = _tophat_foreground(img, params, overlay_mask)

    bw_th = bw_raw.copy()
    if static_mask is not None and np.any(static_mask):
        bw_th[static_mask > 0] = 0
    dets = _emit_dets(bw_th, th, params, dil, overlay_mask, motion_bw, motion_map, require="tophat")

    if motion_bw is not None:
        mo = motion_bw.copy()
        if overlay_mask is not None and np.any(overlay_mask):
            mo[overlay_mask > 0] = 0
        if static_mask is not None and np.any(static_mask):
            mo[static_mask > 0] = 0
        mo = cv2.morphologyEx(mo, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))  # drop diffuse thin resid
        mdets = _emit_dets(mo, th, params, dil, overlay_mask, motion_bw, motion_map, require="motion")
        r2 = 30.0 ** 2
        for md in mdets:  # add only motion blobs that aren't already a top-hat detection
            if all((md["cx"] - d["cx"]) ** 2 + (md["cy"] - d["cy"]) ** 2 > r2 for d in dets):
                dets.append(md)
    return dets, bw_raw


def _emit_dets(bw: np.ndarray, th: np.ndarray, params: Params, dil: np.ndarray | None,
               overlay_mask: np.ndarray | None, motion_bw: np.ndarray | None,
               motion_map: np.ndarray | None, require: str) -> list[dict]:
    """Components of one foreground -> filtered, localized detections. `require` ('tophat'|'motion') is the
    channel that produced `bw`; a blob is kept if it is bright-enough (top-hat) OR motion-supported."""
    h, w = bw.shape[:2]
    mean_floor = params.mean_resp_frac * params.tophat_floor
    n, labels, stats, _cents = cv2.connectedComponentsWithStats(bw, 8)
    out: list[dict] = []
    for i in range(1, n):
        raw_area = int(stats[i, cv2.CC_STAT_AREA])
        if raw_area < params.min_area or raw_area > params.max_area * params.split_max_area_mult:
            continue
        raw_w, raw_h = int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])
        if max(raw_w, raw_h) / float(max(1, min(raw_w, raw_h))) > params.max_aspect:
            continue
        comp = labels == i
        sub_blobs = _split_and_localize(th, comp, params) if params.localize else [
            dict(mask=comp, cx=float(_cents[i][0]), cy=float(_cents[i][1]),
                 x=int(stats[i, cv2.CC_STAT_LEFT]), y=int(stats[i, cv2.CC_STAT_TOP]),
                 w=raw_w, h=raw_h, area=raw_area)]
        for sb in sub_blobs:
            area, bw_, bh_ = sb["area"], sb["w"], sb["h"]
            if area < params.min_area or area > params.max_area:
                continue
            extent = area / float(max(1, bw_ * bh_))
            aspect = max(bw_, bh_) / float(max(1, min(bw_, bh_)))
            if extent < params.min_extent or aspect > params.max_aspect:
                continue
            mask = sb["mask"]
            tophat_mean = float(th[mask].mean())
            motion_frac = float((motion_bw[mask] > 0).mean()) if motion_bw is not None else 0.0
            th_ok = tophat_mean >= mean_floor
            mo_ok = motion_frac >= params.motion_support_frac
            if not (th_ok or mo_ok):
                continue
            if _solidity(mask.astype(np.uint8), area) < params.min_solidity:
                continue
            cx, cy = sb["cx"], sb["cy"]
            if dil is not None:
                cxi, cyi = int(round(cx)), int(round(cy))
                if 0 <= cyi < h and 0 <= cxi < w and dil[cyi, cxi] > 0:
                    continue
                if float(np.count_nonzero(mask & (dil > 0))) / float(area) > params.overlay_overlap_drop:
                    continue
            src = "both" if (th_ok and mo_ok) else ("motion" if mo_ok else "tophat")
            motion = float(motion_map[mask].mean() / 255.0) if motion_map is not None else round(motion_frac, 3)
            out.append(dict(cx=cx, cy=cy, x=sb["x"], y=sb["y"], w=bw_, h=bh_, area=area,
                            extent=round(extent, 3), aspect=round(aspect, 2),
                            solidity=round(_solidity(mask.astype(np.uint8), area), 3),
                            tophat_mean=round(tophat_mean, 2), motion=round(motion, 3), source=src))
    return out


def red_crosshair_mask(bgr: np.ndarray, params: Params) -> np.ndarray:
    """Dynamic mask for the moving red spot-meter crosshair + its white 'NN.N C' readout text.

    The crosshair is chroma-distinct (saturated red) on the desaturated white-hot body, and tracks the
    hottest pixel — it roams onto warm structures, so a static mask can't catch it. It sits ON the true
    rat, so we mask the diamond glyph tightly and only a TIGHT rightward box for the readout text.
    """
    h, w = bgr.shape[:2]
    B, G, R = bgr[:, :, 0].astype(np.int16), bgr[:, :, 1].astype(np.int16), bgr[:, :, 2].astype(np.int16)
    red = ((R - np.maximum(G, B)) > params.red_chroma_thresh).astype(np.uint8) * 255
    mask = np.zeros((h, w), np.uint8)
    if not red.any():
        return mask
    # dilate & mask the diamond glyph itself
    mask = cv2.dilate(red, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    # readout text box, biased to the right of the largest red component's centroid
    n, labels, stats, cents = cv2.connectedComponentsWithStats(red, 8)
    if n > 1:
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        dx, dy = int(cents[i][0]), int(cents[i][1])
        x0, y0 = max(0, dx - 12), max(0, dy - params.readout_h // 2)
        x1, y1 = min(w, dx + params.readout_w), min(h, dy + params.readout_h // 2)
        mask[y0:y1, x0:x1] = 255
    return mask


class WarmBlobDetector:
    """Stateful wrapper: learns a static-structure mask online (persistence of the top-hat foreground,
    restricted to LARGE/ELONGATED components so a resting rat is not erased) and a frame-difference motion
    map, then runs detect_blobs per frame. AGC-robust, MOG2/CLAHE-free."""

    def __init__(self, params: Params, overlay_mask: np.ndarray | None):
        self.p = params
        self.overlay = overlay_mask
        self.persist: np.ndarray | None = None   # float accumulator of foreground occurrences
        self.n = 0
        self.static: np.ndarray | None = None     # current learned static mask (uint8 0/255)
        self.prev: np.ndarray | None = None
        self.bg: np.ndarray | None = None          # EMA background in robust-normalized space (motion channel)

    def _refresh_static(self) -> None:
        frac = self.persist / float(self.n)
        persistent = (frac > self.p.static_persist_frac).astype(np.uint8) * 255
        if not persistent.any():
            self.static = None
            return
        # keep only LARGE or ELONGATED persistent components (pole, wires, berms) — never a compact
        # rat-sized persistent blob (which could be a long-resting rat; flagged elsewhere, not erased).
        nn, lab, st, _ = cv2.connectedComponentsWithStats(persistent, 8)
        keep = np.zeros_like(persistent)
        for i in range(1, nn):
            a = int(st[i, cv2.CC_STAT_AREA])
            ww, hh = int(st[i, cv2.CC_STAT_WIDTH]), int(st[i, cv2.CC_STAT_HEIGHT])
            aspect = max(ww, hh) / float(max(1, min(ww, hh)))
            if a >= self.p.static_struct_min_area or aspect >= self.p.static_struct_min_aspect:
                keep[lab == i] = 255
        k = _odd(max(3, self.p.tophat_se // 4))  # cover the pole edge, not a whole adjacent rat
        self.static = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) if keep.any() else None

    def process(self, gray: np.ndarray, dyn_mask: np.ndarray | None = None) -> list[dict]:
        eff = self.overlay
        if dyn_mask is not None and eff is not None:
            eff = cv2.bitwise_or(eff, dyn_mask)
        elif dyn_mask is not None:
            eff = dyn_mask
        motion = None
        if self.prev is not None:
            motion = (cv2.absdiff(gray, self.prev) >= self.p.motion_diff).astype(np.uint8) * 255
        motion_bw = None
        if self.p.use_motion:
            nrm = robust_norm(gray, self.overlay)          # undo AGC so differencing is meaningful
            if self.bg is None:
                self.bg = nrm.copy()                        # warmup: no motion on the first frame
            else:
                resid = np.clip(nrm - self.bg, 0, 255)      # warmer-than-background = a warm object appeared/moved
                motion_bw = (resid >= self.p.motion_resid_thresh).astype(np.uint8) * 255
                a = 1.0 / max(1, self.p.motion_bg_frames)
                self.bg += a * (nrm - self.bg)              # EMA update (a slow/stationary object is absorbed)
        dets, bw_raw = detect_blobs(gray, self.p, eff, self.static, motion, motion_bw)
        if self.persist is None:
            self.persist = np.zeros(gray.shape[:2], np.float32)
        self.persist += (bw_raw > 0)
        self.n += 1
        if self.n >= self.p.static_warmup:
            self._refresh_static()
        self.prev = gray
        return dets


# --------------------------------------------------------------------------------------
# Greedy nearest-centroid tracker (short-gap tolerant)
# --------------------------------------------------------------------------------------
class Tracker:
    def __init__(self, max_dist: float, max_gap: int):
        self.max_dist = max_dist
        self.max_gap = max_gap
        self.next_id = 0
        self.tracks: dict[int, dict] = {}  # id -> {cx, cy, last_frame}

    def update(self, dets: list[dict], frame_idx: int) -> list[int]:
        for tid in [t for t, v in self.tracks.items() if frame_idx - v["last_frame"] > self.max_gap]:
            del self.tracks[tid]
        assigned: list[int] = [-1] * len(dets)
        used: set[int] = set()
        pairs = []
        for di, d in enumerate(dets):
            for tid, tv in self.tracks.items():
                dist = ((d["cx"] - tv["cx"]) ** 2 + (d["cy"] - tv["cy"]) ** 2) ** 0.5
                if dist <= self.max_dist:
                    pairs.append((dist, di, tid))
        for dist, di, tid in sorted(pairs, key=lambda p: p[0]):
            if assigned[di] != -1 or tid in used:
                continue
            assigned[di] = tid
            used.add(tid)
            self.tracks[tid].update(cx=dets[di]["cx"], cy=dets[di]["cy"], last_frame=frame_idx)
        for di, d in enumerate(dets):
            if assigned[di] == -1:
                tid = self.next_id
                self.next_id += 1
                self.tracks[tid] = dict(cx=d["cx"], cy=d["cy"], last_frame=frame_idx)
                assigned[di] = tid
        return assigned


# --------------------------------------------------------------------------------------
# Video I/O via ffmpeg pipe (BGR: luma for detection, red chroma for the dynamic crosshair mask)
# --------------------------------------------------------------------------------------
def ffprobe_wh_dur(path: str) -> tuple[int, int, float]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    st = j["streams"][0]
    dur = float(j.get("format", {}).get("duration", 0.0) or 0.0)
    return int(st["width"]), int(st["height"]), dur


def iter_frames(path: str, w: int, h: int, start_sec: float = 0.0, max_frames: int | None = None):
    """Yield (frame_idx, bgr_uint8 HxWx3) decoded at native fps via an ffmpeg BGR pipe."""
    cmd = ["ffmpeg", "-v", "error"]
    if start_sec > 0:
        cmd += ["-ss", str(start_sec)]
    cmd += ["-i", path, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    frame_bytes = w * h * 3
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    idx = 0
    try:
        while True:
            if max_frames is not None and idx >= max_frames:
                break
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            yield idx, np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            idx += 1
    finally:
        proc.stdout.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def find_video(base: str, cam: str, date: str, hour: str) -> str:
    d = Path(base) / date / cam
    hits = sorted(d.glob(f"*{date}_{hour}-00*.mp4"))
    if not hits:
        raise FileNotFoundError(f"no thermal file for {cam} {date} hour {hour} in {d}")
    return str(hits[0])


# --------------------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------------------
def run(video: str, out_dir: str, params: Params, cam: str, start_sec: float = 0.0,
        max_frames: int | None = None, preview: bool = False, preview_stride: int = 5) -> dict:
    assert cv2 is not None, "OpenCV (cv2) is required"
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if preview:
        (out / "preview").mkdir(exist_ok=True)

    w, h, dur = ffprobe_wh_dur(video)
    rects = OVERLAY_MASKS.get(cam, DEFAULT_OVERLAYS)
    overlay_mask = build_overlay_mask(h, w, rects, params.border_px)
    detector = WarmBlobDetector(params, overlay_mask)
    tracker = Tracker(params.track_max_dist, params.track_max_gap)

    det_rows: list[dict] = []
    per_frame_counts: list[int] = []
    for idx, bgr in iter_frames(video, w, h, start_sec, max_frames):
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        dyn = red_crosshair_mask(bgr, params)
        dets = detector.process(gray, dyn)
        tids = tracker.update(dets, idx)
        for d, tid in zip(dets, tids):
            det_rows.append(dict(frame=idx, t_sec=round(start_sec + idx, 3), track_id=tid, **d))
        per_frame_counts.append(len(dets))
        if preview and idx % preview_stride == 0:
            _write_preview(out / "preview" / f"f{idx:06d}.png", bgr, dets, tids, rects)

    _write_csv(out / "detections.csv", det_rows,
               ["frame", "t_sec", "track_id", "cx", "cy", "x", "y", "w", "h",
                "area", "extent", "aspect", "solidity", "tophat_mean", "motion", "source"])
    tracks = _summarize_tracks(det_rows, params.track_min_len)
    _write_csv(out / "tracks.csv", tracks,
               ["track_id", "n_frames", "first_frame", "last_frame", "mean_area",
                "mean_tophat", "mean_motion", "path_len_px", "max_step_px", "net_disp_px", "motion_class"])
    counts = np.array(per_frame_counts) if per_frame_counts else np.array([0])
    summary = dict(
        video=video, cam=cam, width=w, height=h, duration_sec=dur,
        frames_processed=int(len(per_frame_counts)),
        detections_total=int(len(det_rows)),
        tracks_total=int(len(tracks)),
        per_frame_count_mean=float(counts.mean()),
        per_frame_count_max=int(counts.max()),
        params=asdict(params),
        caveats=[
            "AGC white-hot render, NOT radiometric: gray != temperature; per-frame gain differs.",
            "Detections are RELATIVE warm blobs, NOT confirmed animals and NOT identities.",
            "Counts are a LOWER BOUND: occlusion / refuge / haze suppress true rats; 0 detections != 0 rats.",
            "Camera OSD clock runs ~1 h behind the filename time; times here are frame idx + filename.",
            "Unsupervised + unvalidated: no labels, precision/recall unknown; per-hour threshold sweep needed.",
            "Right-edge colorbar mask is a declared blind spot; huddled/cool rats & rats on warm ground missed.",
        ],
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    if detector.static is not None:
        cv2.imwrite(str(out / "static_mask.png"), detector.static)
    if preview and (out / "preview").exists() and any((out / "preview").iterdir()):
        _assemble_preview_mp4(out / "preview", out / "preview.mp4", preview_stride)
    return summary


def _summarize_tracks(rows: list[dict], min_len: int) -> list[dict]:
    by: dict[int, list[dict]] = {}
    for r in rows:
        by.setdefault(r["track_id"], []).append(r)
    tracks = []
    for tid, rs in sorted(by.items()):
        if len(rs) < min_len:
            continue
        rs = sorted(rs, key=lambda r: r["frame"])
        xs = np.array([r["cx"] for r in rs])
        ys = np.array([r["cy"] for r in rs])
        steps = np.hypot(np.diff(xs), np.diff(ys)) if len(rs) > 1 else np.array([0.0])
        plen = float(np.sum(steps))
        max_step = float(steps.max())
        # Label-free confidence: a MOVING blob (net displacement) is a strong rat candidate; a long-lived
        # near-stationary compact blob is AMBIGUOUS (resting rat OR warm structure/rock) and NOT separable
        # by single-frame appearance. This is a confidence flag, not a filter.
        net_disp = float(np.hypot(xs[-1] - xs[0], ys[-1] - ys[0]))
        # Net displacement is the honest "went somewhere" signal; per-frame max_step is noisier (catches
        # association jitter on a stationary FP), so it only qualifies a track when large AND sustained.
        motion_class = "moving" if net_disp >= 40.0 else "stationary_ambiguous"
        tracks.append(dict(
            track_id=tid, n_frames=len(rs),
            first_frame=rs[0]["frame"], last_frame=rs[-1]["frame"],
            mean_area=round(float(np.mean([r["area"] for r in rs])), 1),
            mean_tophat=round(float(np.mean([r["tophat_mean"] for r in rs])), 2),
            mean_motion=round(float(np.nanmean([r["motion"] for r in rs])), 3),
            path_len_px=round(plen, 1), max_step_px=round(max_step, 1),
            net_disp_px=round(net_disp, 1), motion_class=motion_class))
    return tracks


def _write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    import csv
    with open(path, "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        wtr.writeheader()
        for r in rows:
            wtr.writerow(r)


def _write_preview(path: Path, bgr: np.ndarray, dets: list[dict], tids: list[int],
                   rects: list[list[int]]) -> None:
    vis = bgr.copy()
    for (x, y, ww, hh) in rects:                                   # OSD masks in dim blue
        cv2.rectangle(vis, (x, y), (x + ww, y + hh), (120, 60, 0), 1)
    for d, tid in zip(dets, tids):                                 # detections in green
        cv2.rectangle(vis, (d["x"], d["y"]), (d["x"] + d["w"], d["y"] + d["h"]), (0, 255, 0), 2)
        cv2.putText(vis, f"#{tid} a{d['area']}", (d["x"], max(0, d["y"] - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1, cv2.LINE_AA)
    cv2.imwrite(str(path), vis)


def _assemble_preview_mp4(png_dir: Path, out_mp4: Path, stride: int) -> None:
    # This ffmpeg build lacks glob input and the sampled PNGs are not consecutively numbered, so use the
    # concat demuxer with an explicit (absolute-path) frame list.
    pngs = sorted(png_dir.glob("f*.png"))
    if not pngs:
        return
    listfile = png_dir / "_frames.txt"
    with open(listfile, "w") as f:
        for p in pngs:
            f.write(f"file '{p.resolve().as_posix()}'\n")
            f.write("duration 0.1667\n")   # ~6 fps playback of the sampled frames
        f.write(f"file '{pngs[-1].resolve().as_posix()}'\n")
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
             "-pix_fmt", "yuv420p", str(out_mp4)], check=True)
    except Exception as e:  # pragma: no cover
        print(f"  (preview mp4 assembly skipped: {e})")


# --------------------------------------------------------------------------------------
# Offline self-test — synthetic AGC thermal sequence, no video / GPU
# --------------------------------------------------------------------------------------
def _synth_frame(t: int, h: int, w: int, rats: list[tuple[float, float]], rng) -> np.ndarray:
    """One synthetic white-hot frame with: AGC-drifting background, a static bright 'pole' bar, OSD text
    blocks in the corners, a thin moving 'crosshair', and the given rat centers as bright gaussians."""
    base = 40 + 25 * np.sin(t / 5.0)                       # global level drifts (mimics AGC)
    img = np.full((h, w), base, np.float32)
    img += rng.normal(0, 4, size=(h, w))                   # sensor noise
    yy, xx = np.mgrid[0:h, 0:w]
    img[:, w // 2 - 4:w // 2 + 4] += 90                    # pole: bright vertical bar mid-frame
    for (cx, cy) in rats:                                  # rats: compact bright gaussians (sigma ~5 px)
        img += 130 * np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 5.0 ** 2)))
    img = np.clip(img, 0, 255).astype(np.uint8)
    img[6:26, w - 120:w - 6] = 255       # timestamp top-right
    img[h // 2 - 40:h // 2 + 40, w - 18:w - 6] = 255  # colorbar right edge
    img[h - 22:h - 6, 6:60] = 255        # 'Thermal' bottom-left
    ccx = int(30 + (t * 3) % (w - 60))                     # thin moving crosshair (reject by geometry)
    ccy = int(h * 0.4)
    img[ccy - 8:ccy + 8, ccx] = 255
    img[ccy, ccx - 8:ccx + 8] = 255
    return img


def selftest() -> int:
    fails: list[str] = []
    if cv2 is None:
        print("FAIL — thermal detector self-test: OpenCV (cv2) unavailable")
        return 1
    h, w = 240, 320
    rng = np.random.default_rng(0)
    T = 40

    def rat_paths(t):
        return [(60 + 4.0 * t, 60 + 1.0 * t), (250 - 3.0 * t, 180 - 1.5 * t)]

    # params scaled to the 320x240 synthetic frame
    p = Params(tophat_se=25, min_area=12, max_area=1500, open_se=3, close_se=5,
               tophat_floor=12, track_max_dist=30, track_min_len=3,
               static_warmup=12, static_struct_min_area=4000, static_struct_min_aspect=4.0)
    rects = [[w - 120, 6, 114, 20], [w - 18, h // 2 - 40, 12, 80], [6, h - 22, 54, 16]]
    overlay = build_overlay_mask(h, w, rects, border_px=2)
    detector = WarmBlobDetector(p, overlay)
    tracker = Tracker(p.track_max_dist, p.track_max_gap)

    counts, hits_near_rat, all_dets_rows = [], 0, []
    for t in range(T):
        rats = rat_paths(t)
        img = _synth_frame(t, h, w, rats, rng)
        dets = detector.process(img)
        tids = tracker.update(dets, t)
        counts.append(len(dets))
        for d in dets:
            near = min(((d["cx"] - cx) ** 2 + (d["cy"] - cy) ** 2) ** 0.5 for (cx, cy) in rats)
            if near <= 12:
                hits_near_rat += 1
        for d, tid in zip(dets, tids):
            all_dets_rows.append(dict(frame=t, track_id=tid, **d))

    warm = np.array(counts[5:])
    if warm.mean() < 1.6:                                          # S1 recall
        fails.append(f"S1 mean detections/frame {warm.mean():.2f} < 1.6 (missing rats)")
    total_dets = sum(counts)                                       # S2 precision
    if total_dets == 0 or hits_near_rat / total_dets < 0.9:
        fails.append(f"S2 precision {hits_near_rat}/{total_dets} near-rat < 0.90 (false positives leaking)")
    pole_fp = sum(1 for r in all_dets_rows if abs(r["cx"] - w / 2) < 6 and r["h"] > 30)  # S3 pole
    if pole_fp > 0:
        fails.append(f"S3 pole detected {pole_fp}x (should be 0)")
    tracks = _summarize_tracks(all_dets_rows, p.track_min_len)     # S4 tracks
    persistent = [tk for tk in tracks if tk["n_frames"] >= T // 2]
    if len(persistent) < 2:
        fails.append(f"S4 expected >=2 persistent tracks, got {len(persistent)}")
    cross_only = np.full((h, w), 45, np.uint8)                     # S5 crosshair rejection
    cross_only[100 - 8:100 + 8, 160] = 255
    cross_only[100, 160 - 8:160 + 8] = 255
    cross_dets, _ = detect_blobs(cross_only, p, np.zeros((h, w), np.uint8), None)
    if len(cross_dets) != 0:
        fails.append("S5 thin crosshair not rejected by geometry filter")
    # S6 red-chroma crosshair mask covers the diamond + a rightward readout box
    bgr = np.full((h, w, 3), 60, np.uint8)
    bgr[100 - 7:100 + 7, 160 - 7:160 + 7] = (30, 30, 220)  # red diamond (BGR)
    cm = red_crosshair_mask(bgr, p)
    if cm[100, 160] == 0 or cm[100, 160 + 30] == 0:
        fails.append("S6 red-chroma mask missed the diamond or its rightward readout box")

    if fails:
        print("FAIL — thermal warm-blob detector self-test")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"PASS — thermal warm-blob detector self-test "
          f"(mean {warm.mean():.2f} blobs/frame, {hits_near_rat}/{total_dets} near-rat, "
          f"{len(persistent)} tracks; pole+crosshair rejected; chroma mask OK)")
    return 0


# --------------------------------------------------------------------------------------
def build_params(a: argparse.Namespace) -> Params:
    p = Params()
    for k in vars(p):
        v = getattr(a, k, None)
        if v is not None:
            setattr(p, k, v)
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Unsupervised warm-blob (rat) detector for AGC thermal video.")
    ap.add_argument("--selftest", action="store_true", help="run offline synthetic PASS/FAIL and exit")
    ap.add_argument("--video", help="path to a thermal .mp4")
    ap.add_argument("--base", default="Q:/hc997/SocialFieldRat2026", help="raw data root (for --cam/--date/--hour)")
    ap.add_argument("--cam", default="108_thermal", help="camera id, e.g. 108_thermal / 109_thermal")
    ap.add_argument("--date", help="YYYY-MM-DD (with --hour)")
    ap.add_argument("--hour", help="two-digit start hour, e.g. 21 (with --date)")
    ap.add_argument("--out", help="output directory")
    ap.add_argument("--start-sec", type=float, default=0.0, dest="start_sec")
    ap.add_argument("--max-frames", type=int, default=None, dest="max_frames")
    ap.add_argument("--preview", action="store_true", help="write annotated preview frames + mp4")
    ap.add_argument("--preview-stride", type=int, default=5, dest="preview_stride")
    ap.add_argument("--use-motion", action="store_true", default=None, dest="use_motion",
                    help="OR-fuse a temporal motion channel (recovers faint-but-moving rats)")
    for name, typ in (("tophat_se", int), ("tophat_floor", int), ("min_area", int), ("max_area", int),
                      ("min_extent", float), ("max_aspect", float), ("thresh_method", str),
                      ("track_max_dist", float), ("track_min_len", int), ("static_persist_frac", float),
                      ("static_warmup", int)):
        ap.add_argument(f"--{name.replace('_', '-')}", type=typ, default=None, dest=name)
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()
    if cv2 is None:
        print("ERROR: OpenCV (cv2) is required for video processing", file=sys.stderr)
        return 2
    video = a.video or (find_video(a.base, a.cam, a.date, a.hour) if (a.date and a.hour) else None)
    if not video:
        ap.error("provide --video, or --date and --hour (with --cam/--base)")
    if not a.out:
        ap.error("provide --out")
    params = build_params(a)
    summary = run(video, a.out, params, a.cam, a.start_sec, a.max_frames, a.preview, a.preview_stride)
    print(json.dumps({k: summary[k] for k in
                      ("frames_processed", "detections_total", "tracks_total",
                       "per_frame_count_mean", "per_frame_count_max")}, indent=2))
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
