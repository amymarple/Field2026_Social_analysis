r"""
following_incidents.py — Phase B2: human-readable strict-following INCIDENT metrics
+ a video false-negative audit classifier.

Phase B (`analyze_following_structure`) reports the PEAK directional follow score
(max over lags 1-30 s) + circular-shift null — a conservative structure/null layer,
but one max score per pair/night hides how OFTEN strict trailing happens. This module
adds the incident layer: it extracts strict-following EPISODES across ALL lags
(1-30 s), merges overlapping detections per ordered pair (so lag-varying trailing is
not missed), preserves the per-episode lag distribution, and turns those into
per-hour / per-bout frequencies. It also provides the classifier the video-audit
script uses to explain why a human-observed trail was or was not detected.

Built entirely on Phase B's grid + per-bin follow test (`w.build_following_grid`,
`w._pair_follow`, `w.follow_radius_in`); nothing here changes Phase B outputs. Inch
frame UNVERIFIED — "leader/follower" is temporal order, not geometry.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from . import wiser_analysis_utils as w
except ImportError:                                   # src on sys.path
    import wiser_analysis_utils as w                  # type: ignore

DEFAULT_LAGS = range(1, 31)          # seconds
DEFAULT_COS = 0.5                    # heading-cosine cutoff
DEFAULT_MIN_BOUT_S = 3.0
DEFAULT_MAX_GAP_S = 2.0


def _runs_with_gap(mask, *, max_gap, min_len):
    """Contiguous runs of a boolean mask tolerating gaps up to ``max_gap`` bins;
    keep runs whose span >= ``min_len`` bins. Returns [(i_start, i_last), ...]."""
    out, i, T = [], 0, len(mask)
    while i < T:
        if not mask[i]:
            i += 1; continue
        j, last, gap = i, i, 0
        while j < T and gap <= max_gap:
            if mask[j]:
                last = j; gap = 0
            else:
                gap += 1
            j += 1
        if (last - i + 1) >= min_len:
            out.append((i, last))
        i = last + 1
    return out


def _sidx(grid):
    return {str(t): k for k, t in enumerate(grid["tags"])}


# ---------------------------------------------------------------------------
# Episode extraction across ALL lags
# ---------------------------------------------------------------------------

def strict_following_episodes(grid: dict, leader, follower, *,
                              lags=DEFAULT_LAGS, R: float, cos_thresh: float = DEFAULT_COS,
                              min_bout_s: float = DEFAULT_MIN_BOUT_S,
                              max_gap_s: float = DEFAULT_MAX_GAP_S,
                              t0_utc=None, tz_offset_hours: int = w.LOCAL_TZ_OFFSET_HOURS) -> list:
    """
    Strict-following EPISODES for ordered pair leader->follower, extracted across
    **all** ``lags`` and merged (union of time intervals) into episodes.

    For each lag $\\ell$: the per-bin follow test (both moving, follower within $R$ of
    the leader's earlier position, heading cosine > ``cos_thresh``) → gap-tolerant runs
    ≥ ``min_bout_s``. The union over lags is merged into episodes; each episode records
    duration, mean separation, mean heading cosine, and the **lag distribution** (which
    lags fired and the median). Grid indices ``i_start/i_end`` are kept so the caller
    can reconstruct the footprint. If ``t0_utc`` (global first-fix datetime) is given,
    ``t_start_local``/``t_end_local`` (EDT) are added.

    Returns a list of dicts (empty if the pair is absent or nothing fires).
    """
    sidx = _sidx(grid)
    if str(leader) not in sidx or str(follower) not in sidx:
        return []
    ia, ib = sidx[str(leader)], sidx[str(follower)]
    bin_s = grid["bin_s"]; els = grid["elapsed_s"]; T = grid["X"].shape[0]
    max_gap = int(round(max_gap_s / bin_s)); min_len = int(round(min_bout_s / bin_s))
    lags = list(lags)

    covered = np.zeros(T, bool)
    lag_at = np.full(T, np.inf)          # smallest firing lag per bin
    dist_at = np.full(T, np.nan)
    cos_at = np.full(T, np.nan)
    lag_masks = {}
    for L in lags:
        follow, valid, dist, cosal = w._pair_follow(grid, ia, ib, int(L), R, cos_thresh)
        runs = _runs_with_gap(follow, max_gap=max_gap, min_len=min_len)
        m = np.zeros(T, bool)
        for i0, i1 in runs:
            m[i0:i1 + 1] |= follow[i0:i1 + 1]        # only the true follow bins in the run
        lag_masks[L] = m
        covered |= m
        upd = m & (L < lag_at)
        lag_at[upd] = L
        dist_at[upd] = dist[upd]
        cos_at[upd] = cosal[upd]

    episodes = []
    for i0, i1 in _runs_with_gap(covered, max_gap=max_gap, min_len=min_len):
        seg = slice(i0, i1 + 1)
        fired = covered[seg]
        lag_seg = lag_at[seg][fired]
        laghist = {int(L): int(lag_masks[L][seg].sum()) for L in lags if lag_masks[L][seg].any()}
        ep = {"leader": str(leader), "follower": str(follower),
              "i_start": int(i0), "i_end": int(i1),
              "t_start_s": float(els[i0]), "t_end_s": float(els[i1]),
              "duration_s": round((i1 - i0) * bin_s, 1),
              "n_follow_bins": int(fired.sum()),
              "mean_sep_in": round(float(np.nanmean(dist_at[seg][fired])), 1),
              "mean_cos": round(float(np.nanmean(cos_at[seg][fired])), 2),
              "median_lag_s": int(np.median(lag_seg)) if lag_seg.size else -1,
              "min_lag_s": int(lag_seg.min()) if lag_seg.size else -1,
              "max_lag_s": int(lag_seg.max()) if lag_seg.size else -1,
              "n_lags_fired": len(laghist),
              "lag_hist": laghist}
        if t0_utc is not None:
            st = pd.Timestamp(t0_utc) + pd.Timedelta(seconds=ep["t_start_s"] + tz_offset_hours * 3600)
            en = pd.Timestamp(t0_utc) + pd.Timedelta(seconds=ep["t_end_s"] + tz_offset_hours * 3600)
            ep["t_start_local"] = str(st)
            ep["t_end_local"] = str(en)
        episodes.append(ep)
    return episodes


def moving_bouts_grid(grid: dict, idx: int, *, min_bout_s=DEFAULT_MIN_BOUT_S,
                      max_gap_s=DEFAULT_MAX_GAP_S) -> list:
    """Contiguous moving runs of tag column ``idx`` on the grid (the denominator for
    fraction-of-movement-bouts). Returns [(i_start, i_end), ...]."""
    bin_s = grid["bin_s"]
    return _runs_with_gap(grid["MOV"][:, idx], max_gap=int(round(max_gap_s / bin_s)),
                          min_len=int(round(min_bout_s / bin_s)))


def pair_incident_metrics(episodes: list, grid: dict, follower_idx: int, *,
                          window_s: float) -> dict:
    """
    Human-readable incident rates for one ordered pair (leader->follower) on one night.

    Denominators (explicit): ``window_s`` = the analysed night-window length (s);
    follower **active** seconds = follower moving-bin count × bin_s; follower movement
    **bouts** = contiguous moving runs. Returns per-hour episode count + duration,
    fraction of the follower's movement bouts that overlap a following episode, and
    episode-duration stats. All rates are 0 (not NaN) when there are no episodes.
    """
    bin_s = grid["bin_s"]
    hours = window_s / 3600.0
    fol_bouts = moving_bouts_grid(grid, follower_idx)
    fol_active_s = float(grid["MOV"][:, follower_idx].sum()) * bin_s
    fol_active_h = fol_active_s / 3600.0
    durs = np.array([e["duration_s"] for e in episodes], float)
    total_dur = float(durs.sum())
    # fraction of follower movement bouts overlapping any episode
    ep_iv = [(e["i_start"], e["i_end"]) for e in episodes]
    n_overlap = 0
    for (b0, b1) in fol_bouts:
        if any(not (e1 < b0 or e0 > b1) for (e0, e1) in ep_iv):
            n_overlap += 1
    n_ep = len(episodes)
    return {
        "n_episodes": n_ep,
        "strict_follow_episode_count_per_hour": round(n_ep / hours, 3) if hours > 0 else 0.0,
        "strict_follow_total_duration_per_hour_s": round(total_dur / hours, 2) if hours > 0 else 0.0,
        "episodes_per_active_hour": round(n_ep / fol_active_h, 3) if fol_active_h > 0 else 0.0,
        "fraction_of_movement_bouts_that_are_following":
            round(n_overlap / len(fol_bouts), 3) if fol_bouts else 0.0,
        "n_follower_movement_bouts": len(fol_bouts),
        "median_episode_duration_s": round(float(np.median(durs)), 1) if n_ep else 0.0,
        "p95_episode_duration_s": round(float(np.percentile(durs, 95)), 1) if n_ep else 0.0,
        "total_following_duration_s": round(total_dur, 1),
        "follower_active_hours": round(fol_active_h, 3),
        "window_hours": round(hours, 3),
    }


def episode_footprint(grid: dict, leader, follower, i_start: int, i_end: int) -> np.ndarray:
    """Leader+follower grid positions over [i_start, i_end] → (M,2) footprint for
    camera routing (drops NaNs)."""
    sidx = _sidx(grid)
    ia, ib = sidx[str(leader)], sidx[str(follower)]
    seg = slice(i_start, i_end + 1)
    pts = np.vstack([np.column_stack([grid["X"][seg, ia], grid["Y"][seg, ia]]),
                     np.column_stack([grid["X"][seg, ib], grid["Y"][seg, ib]])])
    return pts[np.isfinite(pts).all(1)]


# ---------------------------------------------------------------------------
# Video-audit classifier (why a human-observed trail was / was not detected)
# ---------------------------------------------------------------------------

def classify_audit_event(grid: dict, leader, follower, *, R: float,
                         cos_thresh: float = DEFAULT_COS, lags=DEFAULT_LAGS,
                         min_bout_s: float = DEFAULT_MIN_BOUT_S,
                         max_gap_s: float = DEFAULT_MAX_GAP_S,
                         min_present_frac: float = 0.3,
                         radius_mult: float = 2.0, wide_lag_max: int = 60) -> dict:
    """
    For a local grid around a video-marked event, classify whether the current
    detector caught the leader->follower trail, and if not, WHY — by relaxing ONE
    constraint at a time. Priority (most fundamental first):

      detected → missed_tag_dropout → missed_alignment → missed_moving_mask →
      missed_distance_radius → missed_heading → missed_lag_range →
      missed_not_geometrically_strict

    ``min_present_frac`` = a tag must have fixes in ≥ this fraction of the grid bins
    or it is a dropout; ``radius_mult`` / ``wide_lag_max`` are the relaxations tested.
    Returns a dict with ``classification``, ``detected`` (bool), ``recovered_by`` (the
    relaxation that would recover it, or None), and diagnostic counts.
    """
    sidx = _sidx(grid)
    out = {"detected": False, "classification": None, "recovered_by": None,
           "n_episodes": 0, "leader_present_frac": np.nan, "follower_present_frac": np.nan,
           "both_moving_bins": 0}
    if str(leader) not in sidx or str(follower) not in sidx:
        out["classification"] = "missed_tag_dropout"
        out["recovered_by"] = None
        return out
    ia, ib = sidx[str(leader)], sidx[str(follower)]
    T = grid["X"].shape[0]
    la_present = np.isfinite(grid["X"][:, ia])
    fo_present = np.isfinite(grid["X"][:, ib])
    out["leader_present_frac"] = round(float(la_present.mean()), 3)
    out["follower_present_frac"] = round(float(fo_present.mean()), 3)
    both_present = la_present & fo_present
    both_moving = grid["MOV"][:, ia] & grid["MOV"][:, ib]
    out["both_moving_bins"] = int(both_moving.sum())

    # 0. detected by the current detector?
    eps = strict_following_episodes(grid, leader, follower, lags=lags, R=R,
                                    cos_thresh=cos_thresh, min_bout_s=min_bout_s,
                                    max_gap_s=max_gap_s)
    out["n_episodes"] = len(eps)
    if eps:
        out["detected"] = True
        out["classification"] = "detected"
        return out

    # 1. tag dropout — a tag barely present in the window
    if out["leader_present_frac"] < min_present_frac or out["follower_present_frac"] < min_present_frac:
        out["classification"] = "missed_tag_dropout"
        return out
    # 2. clock/alignment — tags never present at the same bin
    if not both_present.any():
        out["classification"] = "missed_alignment"
        return out
    # 3. moving mask — never both moving together
    if out["both_moving_bins"] == 0:
        out["classification"] = "missed_moving_mask"
        return out
    # 4. distance radius — recovers with a larger R
    if strict_following_episodes(grid, leader, follower, lags=lags, R=R * radius_mult,
                                 cos_thresh=cos_thresh, min_bout_s=min_bout_s,
                                 max_gap_s=max_gap_s):
        out["classification"] = "missed_distance_radius"
        out["recovered_by"] = f"R x{radius_mult}"
        return out
    # 5. heading cutoff — recovers with a relaxed heading requirement
    if strict_following_episodes(grid, leader, follower, lags=lags, R=R,
                                 cos_thresh=-0.1, min_bout_s=min_bout_s, max_gap_s=max_gap_s):
        out["classification"] = "missed_heading"
        out["recovered_by"] = "cos_thresh -0.1"
        return out
    # 6. lag range — recovers with a wider lag window
    if strict_following_episodes(grid, leader, follower, lags=range(1, wide_lag_max + 1), R=R,
                                 cos_thresh=cos_thresh, min_bout_s=min_bout_s, max_gap_s=max_gap_s):
        out["classification"] = "missed_lag_range"
        out["recovered_by"] = f"lags 1-{wide_lag_max}s"
        return out
    # 7. genuinely not WISER-geometrically strict
    out["classification"] = "missed_not_geometrically_strict"
    return out
