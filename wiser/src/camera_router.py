r"""
camera_router.py — recommend which video channel(s) to inspect for a WISER event.

Given WISER coordinates (a point, or an event footprint = leader+follower positions
over an episode) the router returns RANKED camera channels to pull, using a manually
editable visibility map (`configs/camera_visibility_map.yaml`) that maps WISER-inch
polygons to channels. Because the polygons are defined empirically **in the WISER
inch frame**, routing needs NO georeference (the calibration file IS the mapping);
"channel for a location" is an empirical, editable lookup, not a physical claim.

Numpy + matplotlib(.path) + PyYAML only. Read-only. See the config template's header
for how to calibrate.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    from . import wiser_analysis_utils as w
except ImportError:                                   # src on sys.path
    import wiser_analysis_utils as w                  # type: ignore


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------

def load_visibility_map(path: Path | str) -> dict:
    """
    Load `camera_visibility_map.yaml`. Returns
    ``{"meta": {...}, "channels": [{name, polygon:[[x,y],...] | bbox:[xmin,xmax,ymin,ymax],
    priority, notes, examples:[...] }, ...]}``. A ``bbox`` is expanded to a rectangle
    polygon. Raises FileNotFoundError if absent (the caller decides whether to warn).
    """
    import yaml
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"camera visibility map not found: {path}")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    channels = cfg.get("channels", []) or []
    for ch in channels:
        if "polygon" not in ch and "bbox" in ch and ch["bbox"]:
            xmin, xmax, ymin, ymax = ch["bbox"]
            ch["polygon"] = [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]]
        ch["_poly"] = (np.asarray(ch["polygon"], float)
                       if ch.get("polygon") and len(ch["polygon"]) >= 3 else None)
        ch.setdefault("priority", 1.0)
        ch.setdefault("notes", "")
    return {"meta": cfg.get("meta", {}), "channels": channels,
            "confirmed": bool((cfg.get("meta") or {}).get("confirmed", False))}


# ---------------------------------------------------------------------------
# route
# ---------------------------------------------------------------------------

def _coverage(footprint: np.ndarray, poly: np.ndarray) -> float:
    """Fraction of footprint points inside a polygon."""
    if poly is None or len(footprint) == 0:
        return 0.0
    return float(np.mean(w.points_in_polygons(footprint[:, 0], footprint[:, 1], [poly])))


def route_event(footprint_xy, vis_map: dict, *, margin_in: float = 0.0,
                boundary_lo: float = 0.15, boundary_hi: float = 0.85) -> dict:
    """
    Rank camera channels for one event footprint (WISER inches).

    ``footprint_xy`` is an (N,2) array of positions during the event (leader +
    follower, optionally the ±margin envelope). For each channel, ``coverage`` =
    fraction of footprint points inside its polygon; ``score = coverage × priority``.
    Returns a dict with ``channel_rank_1/2`` (names or None), ``confidence`` (best
    coverage, discounted when the event straddles a boundary), ``reason`` (coverage
    breakdown), ``near_boundary`` (footprint split across channels, or best coverage
    inside ``[boundary_lo, boundary_hi]``), ``x_med``/``y_med``, and per-channel
    ``coverages``. ``margin_in`` grows the footprint by a jitter buffer first.
    """
    fp = np.atleast_2d(np.asarray(footprint_xy, float))
    fp = fp[np.isfinite(fp).all(1)]
    if len(fp) == 0:
        return {"channel_rank_1": None, "channel_rank_2": None, "confidence": 0.0,
                "reason": "no valid footprint points", "near_boundary": False,
                "x_med": np.nan, "y_med": np.nan, "coverages": {}}
    if margin_in > 0:                                 # add a ring of margin points
        ring = np.array([[margin_in, 0], [-margin_in, 0], [0, margin_in], [0, -margin_in]])
        fp = np.vstack([fp] + [fp + d for d in ring])

    rows = []
    for ch in vis_map.get("channels", []):
        cov = _coverage(fp, ch.get("_poly"))
        rows.append((ch["name"], cov, float(ch.get("priority", 1.0)),
                     cov * float(ch.get("priority", 1.0)), ch.get("notes", "")))
    rows.sort(key=lambda r: -r[3])
    coverages = {name: round(cov, 3) for name, cov, _, _, _ in rows}
    covered = [r for r in rows if r[1] > 0]

    if not covered:
        return {"channel_rank_1": None, "channel_rank_2": None, "confidence": 0.0,
                "reason": "event footprint outside every calibrated channel polygon "
                          "(fill/extend configs/camera_visibility_map.yaml)",
                "near_boundary": False,
                "x_med": float(np.median(fp[:, 0])), "y_med": float(np.median(fp[:, 1])),
                "coverages": coverages}

    r1 = covered[0]
    r2 = covered[1] if len(covered) > 1 else None
    best_cov = r1[1]
    n_partial = sum(1 for r in covered if r[1] >= 0.1)
    near_boundary = (n_partial >= 2) or (boundary_lo <= best_cov <= boundary_hi)
    confidence = round(best_cov * (0.6 if near_boundary else 1.0), 3)
    reason = f"footprint {best_cov*100:.0f}% inside {r1[0]}"
    if r2 and r2[1] >= 0.1:
        reason += f", {r2[1]*100:.0f}% inside {r2[0]} — near boundary, pull both"
    if r1[4]:
        reason += f" ({r1[4]})"
    return {"channel_rank_1": r1[0], "channel_rank_2": (r2[0] if r2 else None),
            "confidence": confidence, "reason": reason, "near_boundary": bool(near_boundary),
            "x_med": float(np.median(fp[:, 0])), "y_med": float(np.median(fp[:, 1])),
            "coverages": coverages}


def route_events_df(events, vis_map: dict, *, footprint_cols=("x", "y"),
                    group_col: str | None = None, margin_in: float = 0.0):
    """
    Route many events. ``events`` is a DataFrame; if ``group_col`` is given, each
    group's rows form one footprint (e.g. all leader/follower positions of an
    episode); otherwise each row is a single-point footprint. Returns a DataFrame
    of routing columns aligned to the (grouped) events.
    """
    import pandas as pd
    xcol, ycol = footprint_cols
    out = []
    if group_col and group_col in events.columns:
        for gid, g in events.groupby(group_col):
            fp = g[[xcol, ycol]].to_numpy()
            r = route_event(fp, vis_map, margin_in=margin_in)
            r[group_col] = gid
            out.append(r)
    else:
        for _, row in events.iterrows():
            r = route_event(np.array([[row[xcol], row[ycol]]]), vis_map, margin_in=margin_in)
            out.append(r)
    df = pd.DataFrame(out)
    return df.drop(columns=["coverages"], errors="ignore")
