"""
stripe_flow.py -- optical-flow "stripe-flow" MOTION index Phi for the shelter interior (CH05/CH06).

DIAGNOSTIC / ANNOTATION ONLY. This computes a *motion lower bound* from the rat's dark dorsal
back-stripe moving through a (possibly fogged) inside-glass view. It NEVER feeds a pipeline
decision and NEVER relaxes the shelter safety rule (degraded/unusable view must not become
`occupied_high_motion`). It exists so a human-labeled validation clip can *also* carry a Phi
score, letting us test whether coherent dark-pixel flow separates a *moving rat under fog* from
fog-only drift. It is not (yet) wired into shelter_sleep.py and must not gate any state.

## Definition

Input: a short burst of consecutive inside-view grayscale frames f_1..f_K and the inside-shelter
ROI mask M (a boolean image). For each adjacent pair (a, b) = (f_k, f_{k+1}) compute dense
Farneback optical flow v(p) = (vx(p), vy(p)) with magnitude |v(p)| = sqrt(vx^2 + vy^2).

Dark-moving pixel set (the candidate rat-stripe-in-motion pixels):

    D = { p in M : b(p) < Q_q(b | M)  AND  |v(p)| >= v_min }

where Q_q(b | M) is the q-th intensity percentile of b taken over ROI pixels only (dark = the
rat's black back-stripe stands out against the lighter bedding/fog), and v_min is the minimum
flow magnitude (px/frame) counted as motion.

Per-pair quantities:

    cov = |D| / |M|                                             in [0, 1]
        dark-moving coverage: fraction of the inside ROI that is simultaneously dark AND moving.

    coh = || sum_{p in D} v(p) || / ( sum_{p in D} |v(p)| )     in [0, 1]
        flow coherence: 1 = all dark-moving vectors point the same way (a rigid body / rat
        translating coherently), ~0 = incoherent directions (diffuse fog drift / rain speckle).
        Set to 0 when |D| < min_pixels (too few dark-moving pixels to have a meaningful direction).

Phi(clip) = ( mean_k cov_k , mean_k coh_k )  over the K-1 adjacent pairs.

**Text.** cov says "how much of the inside view is a dark thing that moved" (unitless fraction,
0..1; high = a large dark region shifted); coh says "did that dark motion move together like one
body" (unitless, 0..1; high = coherent translation consistent with a rat, low = incoherent drift
consistent with fog). A moving rat under fog should read HIGH on both relative to a fog-only /
empty view; a still rat or an empty foggy view should read LOW. MOTION LOWER BOUND ONLY: a low
Phi does not prove the rat is absent or still (it may be occluded, at the wall-edge blind zone,
or the sampled instant may miss the motion) -- it only fails to *witness* motion.
"""

from __future__ import annotations

import numpy as np
import cv2

# Farneback parameters (match the feasibility prototype: pyr_scale, levels, winsize, iters, poly_n,
# poly_sigma, flags). Winsize 15 tolerates the low-contrast fogged view; kept fixed so Phi is
# comparable across clips/days.
_FB = dict(pyr_scale=0.5, levels=3, winsize=15, iterations=3, poly_n=5, poly_sigma=1.2, flags=0)


def _pair_cov_coh(a, b, mask, v_min, dark_pctl, min_pixels):
    """cov, coh for one adjacent grayscale pair (a -> b) inside `mask` (bool image)."""
    flow = cv2.calcOpticalFlowFarneback(a, b, None, **_FB)
    mag = np.hypot(flow[..., 0], flow[..., 1])
    thr = np.percentile(b[mask], dark_pctl)                    # dark = below this ROI-intensity pctile
    dm = mask & (b < thr) & (mag >= v_min)                     # dark AND moving, inside ROI
    ndm = int(dm.sum())
    cov = ndm / max(1, int(mask.sum()))
    if ndm >= min_pixels:
        vx, vy = flow[..., 0][dm].sum(), flow[..., 1][dm].sum()
        coh = float(np.hypot(vx, vy) / (mag[dm].sum() + 1e-6))
    else:
        coh = 0.0
    return cov, coh


def stripe_flow(frames, mask, v_min: float = 1.0, dark_pctl: float = 25.0,
                min_pixels: int = 5):
    """Stripe-flow motion index Phi over a burst of consecutive grayscale `frames`.

    Returns (cov, coh), each the mean over adjacent pairs (0.0 if fewer than 2 usable frames).
    `mask` is a boolean inside-ROI image the same HxW as the frames. DIAGNOSTIC ONLY -- a MOTION
    lower bound; never use it to relax the shelter safety rule.
    """
    mask = mask.astype(bool)
    frames = [f for f in frames if f is not None]
    if len(frames) < 2 or not mask.any():
        return 0.0, 0.0
    covs, cohs = [], []
    for a, b in zip(frames[:-1], frames[1:]):
        if a.shape != mask.shape or b.shape != mask.shape:
            continue
        cov, coh = _pair_cov_coh(a, b, mask, v_min, dark_pctl, min_pixels)
        covs.append(cov)
        cohs.append(coh)
    if not covs:
        return 0.0, 0.0
    return float(np.mean(covs)), float(np.mean(cohs))
