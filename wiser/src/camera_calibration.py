r"""
camera_calibration.py — image-based calibration for the Phase B2 camera router.

The natural way to calibrate: look at a CAMERA frame (where you can see landmarks),
mark a few landmarks whose WISER (x,y) are known (houses, refuges, water — from
`wiser_rois.json`), fit a **pixel -> WISER homography** (the correct fixed planar
transform), then map the camera's visible ground region back into a WISER polygon =
that channel's visibility polygon. No georeference needed: the homography is fit
directly from your pixel<->WISER landmark correspondences.

Numpy only for the math; cv2 (OpenCV, in the `cv` env) only for grabbing a frame.
Homography assumes a roughly planar ground + pinhole camera; for the wide fisheyes
(CH03/CH04) it is approximate but fine for a visibility polygon.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    from . import wiser_analysis_utils as w
except ImportError:                                   # src on sys.path
    import wiser_analysis_utils as w                  # type: ignore


# ---------------------------------------------------------------------------
# homography (numpy DLT)
# ---------------------------------------------------------------------------

def fit_homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """
    3x3 homography H mapping ``src`` pixels -> ``dst`` (WISER inches), from >= 4
    point correspondences, via the DLT (SVD). ``src``/``dst`` are (N,2).
    """
    src = np.asarray(src, float); dst = np.asarray(dst, float)
    if len(src) < 4 or len(src) != len(dst):
        raise ValueError("need >= 4 matched (src, dst) point pairs")
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        A.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, _, Vt = np.linalg.svd(np.asarray(A, float))
    H = Vt[-1].reshape(3, 3)
    return H / H[2, 2] if H[2, 2] != 0 else H


def apply_homography(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Map (N,2) points through a 3x3 homography -> (N,2)."""
    pts = np.atleast_2d(np.asarray(pts, float))
    ph = np.column_stack([pts, np.ones(len(pts))])
    q = (np.asarray(H, float) @ ph.T).T
    return q[:, :2] / q[:, 2:3]


def homography_rms(H: np.ndarray, src: np.ndarray, dst: np.ndarray) -> float:
    """RMS reprojection error (inches) of the fitted homography on its landmarks."""
    pred = apply_homography(H, src)
    return float(np.sqrt(np.mean(np.sum((pred - np.asarray(dst, float)) ** 2, axis=1))))


# ---------------------------------------------------------------------------
# hull + buffer (numpy; also used when no explicit visible region is drawn)
# ---------------------------------------------------------------------------

def convex_hull(points: np.ndarray) -> np.ndarray:
    pts = sorted(set(map(tuple, np.asarray(points, float).tolist())))
    if len(pts) <= 2:
        return np.asarray(pts, float)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.asarray(lower[:-1] + upper[:-1], float)


def buffer_polygon(poly: np.ndarray, margin_in: float) -> np.ndarray:
    if len(poly) < 3 or margin_in <= 0:
        return poly
    c = poly.mean(0); d = poly - c
    n = np.linalg.norm(d, axis=1, keepdims=True)
    return poly + margin_in * d / np.clip(n, 1e-9, None)


# ---------------------------------------------------------------------------
# build a channel's visibility polygon from image landmarks
# ---------------------------------------------------------------------------

def build_visibility_polygon(px_pts, wiser_pts, *, region_px=None,
                             margin_in: float = 18.0) -> dict:
    """
    Fit pixel->WISER homography from the landmark correspondences, then return the
    channel's WISER visibility polygon:
      - if ``region_px`` (a polygon of the visible GROUND area drawn in the image)
        is given, map its vertices through the homography;
      - else use the convex hull of the mapped landmark points (+ ``margin_in``).
    Returns ``{polygon: [[x,y]...], homography: 3x3 list, rms_in, n_landmarks,
    source}``.
    """
    px = np.asarray(px_pts, float); wz = np.asarray(wiser_pts, float)
    H = fit_homography(px, wz)
    rms = homography_rms(H, px, wz)
    if region_px is not None and len(region_px) >= 3:
        poly = apply_homography(H, np.asarray(region_px, float))
        source = f"visible-region polygon mapped via homography ({len(px)} landmarks)"
    else:
        poly = buffer_polygon(convex_hull(apply_homography(H, px)), margin_in)
        source = f"convex hull of {len(px)} mapped landmarks + {margin_in:.0f} in margin"
    return {"polygon": np.round(poly, 1).tolist(), "homography": H.tolist(),
            "rms_in": round(rms, 2), "n_landmarks": int(len(px)), "source": source}


# ---------------------------------------------------------------------------
# WISER landmark table (the known (name, x, y) the user clicks against)
# ---------------------------------------------------------------------------

def roi_landmarks(roi_cfg: dict) -> list:
    """(name, x, y) for every ROI + the 4 boundary corners — the menu of landmarks
    with known WISER coordinates the user maps image points onto."""
    out = []
    for roi in (roi_cfg or {}).get("rois", []):
        out.append((roi["name"], float(roi["x"]), float(roi["y"])))
    b = (roi_cfg or {}).get("boundary", {})
    if b.get("rect"):
        xmin, xmax, ymin, ymax = b["rect"]
        out += [("corner_SW", xmin, ymin), ("corner_SE", xmax, ymin),
                ("corner_NE", xmax, ymax), ("corner_NW", xmin, ymax)]
    return out


# ---------------------------------------------------------------------------
# frame grab (cv2)
# ---------------------------------------------------------------------------

def crop_blank_margins(img: np.ndarray, *, uniform_std: float = 3.0):
    """
    Trim the uniform (near-zero-variance) padding border of a frame — the CH01/CH02
    2160×7680 panorama pads the coded frame, and the fill colour is decoder-dependent
    (white on software libav, black on d3d11va, grey on cuda), so detect it by
    **row/column variance**, not colour. Trims only *contiguous* uniform rows/cols
    from each edge. Returns ``(cropped, (row0, col0))``; the offset maps cropped-pixel
    clicks back to the original if ever needed. No-op if no uniform margin.
    """
    g = img[..., :3].mean(axis=2)
    row_blank = g.std(axis=1) < uniform_std
    col_blank = g.std(axis=0) < uniform_std
    r0 = 0
    while r0 < len(row_blank) and row_blank[r0]:
        r0 += 1
    r1 = len(row_blank) - 1
    while r1 > r0 and row_blank[r1]:
        r1 -= 1
    c0 = 0
    while c0 < len(col_blank) and col_blank[c0]:
        c0 += 1
    c1 = len(col_blank) - 1
    while c1 > c0 and col_blank[c1]:
        c1 -= 1
    return img[r0:r1 + 1, c0:c1 + 1], (r0, c0)


def _grab_frame_av(video_path, at_frac, warmup=6):
    """Decode a CLEAN full frame with PyAV: seek to the keyframe near ``at_frac``,
    then decode ``warmup`` frames forward so the decoder is fully primed (avoids the
    partial-decode corruption cv2's raw seek produces on long-GOP H.264). Returns a
    BGR ndarray or None."""
    import av
    with av.open(str(video_path)) as container:
        stream = container.streams.video[0]
        if stream.duration and stream.time_base:
            target = float(stream.duration * stream.time_base) * float(np.clip(at_frac, 0, 0.999))
            try:
                container.seek(int(target / stream.time_base), stream=stream, any_frame=False)
            except Exception:
                pass
        frame = None
        for i, f in enumerate(container.decode(stream)):
            frame = f
            if i >= warmup:
                break
    return None if frame is None else frame.to_ndarray(format="bgr24")


def _find_ffmpeg():
    """Locate a standalone ffmpeg binary (the conda env bundles a full build under
    Library\\bin — a newer/fuller build than PyAV/OpenCV's linked libav)."""
    import shutil
    import sys
    cands = [Path(sys.prefix) / "Library" / "bin" / "ffmpeg.exe",
             Path(sys.prefix) / "bin" / "ffmpeg", Path(sys.prefix) / "bin" / "ffmpeg.exe"]
    w = shutil.which("ffmpeg")
    if w:
        cands.append(Path(w))
    for c in cands:
        if Path(c).exists():
            return str(c)
    return None


def _video_duration_s(video_path):
    try:
        import av
        with av.open(str(video_path)) as c:
            s = c.streams.video[0]
            if s.duration and s.time_base:
                return float(s.duration * s.time_base)
            if c.duration:
                return float(c.duration) / 1e6
    except Exception:
        pass
    return None


def _is_truncated(img, *, frac: float = 0.15, std_thresh: float = 8.0,
                  dark_thresh: float = 25.0, dark_ratio: float = 0.35) -> bool:
    """BEST-EFFORT check that the bottom ``frac`` is decoder garbage, not real content.

    Caveat: on these 2160×7680 panoramas the corrupt fill is **decoder-state-dependent**
    and takes many forms — flat white/black/grey (old HW paths), a bright band, or a DARK
    dither-noise gradient with a green/red left–right tint (software seq/seek). No single
    statistic catches them all (the dark-noise variant even has *higher* Laplacian
    variance than real night content). This flags the two reliably-catchable signatures:
      (1) near-uniform fill  -> bottom std < ``std_thresh``;
      (2) dark collapse      -> bottom is near-black AND much darker than the top band.
    It can miss a bright-fill variant, so it is only a warning aid. The robust fix is to
    extract a **night IR frame**, which decodes fully (see ``grab_frame``)."""
    g = img[..., :3].mean(2).astype("float32")
    h = g.shape[0]
    n = max(1, int(frac * h))
    bottom = g[h - n:]
    top = g[:n]
    if float(bottom.std()) < std_thresh:                         # (1) flat fill
        return True
    bm, tm = float(bottom.mean()), float(top.mean())             # (2) dark collapse
    return bm < dark_thresh and bm < dark_ratio * max(tm, 1e-6)


# Minimum seek (seconds) to clear a file's FIRST GOP. The 2160×7680 CH01/CH02 panoramas
# decode their file's first keyframe BROKEN on a cold open at frame 0, and that poisons the
# whole continuous decode (P-frames reference it). Any decode STARTED with a seek past the
# first GOP reconstructs the full frame and stays full thereafter. See module notes.
_FIRST_GOP_SKIP_S = 3.0


def _grab_frame_ffmpeg(video_path, out_png, at_frac, ffmpeg, hwaccel=None):
    """Extract a frame via standalone ffmpeg, ALWAYS starting with a seek (``-ss``) so the
    decoder inits on a good keyframe (never the poisoned first GOP). ``hwaccel`` None =
    software decode (the reliable path for the tall panoramas). Returns True iff the saved
    frame is not truncated."""
    import subprocess
    import cv2
    dur = _video_duration_s(video_path)
    seek_s = max(_FIRST_GOP_SKIP_S, (dur or 0) * float(np.clip(at_frac, 0, 0.999)))
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error"]
    if hwaccel:
        cmd += ["-hwaccel", hwaccel]
    cmd += ["-ss", f"{seek_s:.3f}", "-i", str(video_path), "-frames:v", "1", "-update", "1",
            "-y", str(out_png)]
    try:
        subprocess.run(cmd, check=True, timeout=180)
    except Exception:
        return False
    img = cv2.imread(str(out_png))
    return img is not None and not _is_truncated(img)


def grab_frame(video_path: Path | str, out_png: Path | str, *, at_frac: float = 0.5,
               crop_blank: bool = False, hwaccel: bool = True) -> bool:
    """Save one frame (~``at_frac`` through the clip) from a CHxx MP4 to a PNG.

    **Partial-frame note (CH01/CH02 2160×7680 Duo 3).** The camera encoder HARD-CAPS every
    keyframe at 2,000,000 bytes. Bright daytime keyframes need 2.0–2.5 MB, so the overflow —
    the bottom band — is **never recorded**; NO decoder can recover it (software shows white/
    gray, NVDEC shows green, VLC-HW shows stale pixels that only *look* real). Capped GOPs
    cluster through bright hours (up to ~41 % of a low-sun afternoon). Night IR keyframes are
    ~1.1 MB and never hit the cap → always full. See docs/methods/duo3_keyframe_2mb_cap.md.

    Therefore: for a CALIBRATION still on CH01/CH02, use a **night frame** (the driver defaults
    ``--extract`` to a night hour). Extraction is seek-based and, for robustness against the
    cv2 frame-number seek bug on these VFR streams, uses ffmpeg time seeks. For daytime CV
    tracking you must additionally mask bottom-band detections inside capped-GOP time ranges
    (cvpipe ``find_capped_gops``) and use time-based intact-keyframe seeking. Forcing B/W night
    mode 24/7 is NOT a fix (it dodges the cap by discarding needed daytime detail).

    Normal-res channels (CH03 4512×2512, CH05 2560×1920) were never affected. ``crop_blank``
    (opt-in) trims uniform padding.
    """
    import cv2
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    ff = _find_ffmpeg()
    if ff:
        # HW seek first (fast); then SW seek (the reliable path for the tall panoramas).
        attempts = ([("d3d11va", "hardware d3d11va"), ("cuda", "hardware cuda")] if hwaccel else [])
        attempts += [(None, "software")]
        for hw, label in attempts:
            if _grab_frame_ffmpeg(video_path, out_png, at_frac, ff, hw):
                if crop_blank:
                    img, _ = crop_blank_margins(cv2.imread(str(out_png)))
                    cv2.imwrite(str(out_png), img)
                print(f"    [grab] {label} decode (seek) -> full frame")
                return True
        print("    [grab] ffmpeg seek decodes truncated; trying PyAV seek fallback")

    # PyAV seek+warmup fallback (also seek-based)
    frame = None
    try:
        frame = _grab_frame_av(video_path, at_frac)
    except Exception:
        pass
    if frame is None:
        return False
    if _is_truncated(frame):
        print(f"    [grab] WARNING: {frame.shape[1]}x{frame.shape[0]} frame still looks truncated "
              "even after a seek. Try a larger --at-frac, or a VLC snapshot (Shift+S) via --image.")
    if crop_blank:
        frame, _ = crop_blank_margins(frame)
    cv2.imwrite(str(out_png), frame)
    return True
