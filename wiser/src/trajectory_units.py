r"""
trajectory_units.py — pluggable TRAJECTORY-UNIT tables for the route-vocabulary test.

The route-vocabulary battery must not privilege one segmentation. A *trajectory unit* is one candidate
locomotor unit (a bout / leg / episode) with an arc-length-resampled path in absolute inch coords. The
SAME core tests (held-out compression, cross-animal generalisation, endpoint-vs-shape, one geometry
null) run on ANY unit table that follows the schema below, so different segmentations can be compared
as REPRESENTATIONS — which one yields the strongest held-out compression, prototype stability,
repertoire closure, and cross-animal generalisation.

=== PROVENANCE CAVEAT (load-bearing) ===
The only implemented segmentation today is ``original_3s_filtered_bouts``: maximal moving runs with a
MIN-DURATION (>= 3 s) + MIN-DISPLACEMENT (>= 15 in) filter. Those thresholds IMPOSE the unit's
duration/displacement scale — these are **NOT** validated decision-to-decision locomotor legs. Every
result computed on this table is *provisional* and MUST be labelled
    "conditional on the original 3-second-filtered bout segmentation".
A positive vocabulary result on it is **not** evidence that rats possess route tokens; that requires
re-running the identical battery on ``validated_locomotor_legs`` / ``pause_merged_episodes``, which
await the decision-boundary analysis. Do not run downstream stability / grammar / policy analyses on
this provisional table.

=== Unit-table schema ===
``units_df`` (one row per unit, aligned row-for-row to ``paths`` of shape (N, L, 2)):
  segmentation_id : str   which segmentation produced this unit
  night           : str   YYYY-MM-DD night label (whole-night = outer CV block)
  shortid         : str   WISER tag id (resolve to animal via rat_identities.csv)
  t_start_ms      : int   unit start, Unix ms UTC
  t_end_ms        : int   unit end, Unix ms UTC
  duration_s      : float
  disp_in         : float net endpoint displacement (in)
  path_in         : float path length (in)
  x0, y0, x1, y1  : float start/end coords (in, UNVERIFIED offset frame)
  start_roi,end_roi: str  (optional) provisional ROI labels
``paths`` : np.ndarray (N, L, 2)  arc-length-resampled absolute inch coords, row i <-> units_df row i.
``meta``  : dict  {segmentation_id, status, provisional, label, definition, params, bout_log}.

Distances/frame are INCHES in the WISER native, UNVERIFIED offset frame -> topological/relative only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import trajectory_stereotypy as ts   # extract_route_bouts (src on sys.path)


# Canonical column order for a trajectory-unit table (external leg/episode tables must match).
UNIT_COLUMNS = ["segmentation_id", "night", "shortid", "t_start_ms", "t_end_ms", "duration_s",
                "disp_in", "path_in", "x0", "y0", "x1", "y1"]

SEGMENTATIONS: dict[str, dict] = {
    "original_3s_filtered_bouts": {
        "status": "implemented_provisional",
        "provisional": True,
        "label": "conditional on the original 3-second-filtered bout segmentation",
        "definition": ("maximal moving runs (smoothed speed > floor, inter-sample gap <= 2 s) kept "
                       "only if duration >= 3 s AND net displacement >= 15 in; arc-length-resampled to "
                       "L points; capped per animal-night by displacement. The min-duration + "
                       "min-displacement thresholds IMPOSE the unit's temporal/spatial scale, so these "
                       "are a provisional baseline, NOT validated decision-to-decision locomotor legs."),
        "params": {"min_bout_s": 3.0, "min_disp_in": 15.0, "max_gap_s": 2.0,
                   "resample_n": 20, "max_per_night": 40},
    },
    "validated_locomotor_legs": {
        "status": "blocked_needs_cv",
        "provisional": True,
        "label": "validated decision-to-decision locomotor legs (BLOCKED — needs CV)",
        "definition": ("decision-to-decision legs. BLOCKED: the decision-boundary validation "
                       "(`decision_boundary_validation/`) found NO reliable boundary class at WISER "
                       "resolution — pause reorientation is not separable from ~7 in jitter (matched "
                       "+17.9 deg vs jitter-only null +20.4 deg; reverses to -3.1 deg when headings are "
                       "well-resolved; changepoint detector 30-77% false-positive). Requires CV "
                       "pose/keypoints, not WISER. Supply an external unit table (UNIT_COLUMNS + paths, "
                       "then validate_units) when CV tracking is available."),
        "params": {},
    },
    "pause_merged_episodes": {
        "status": "implemented_provisional",
        "provisional": True,
        "label": "conditional on pause-merged locomotor episodes (5 s transitive pause-bridging)",
        "definition": ("maximal moving runs transitively chained across pauses shorter than "
                       "`pause_merge_s` (with data continuity across the bridged pause), then the same "
                       "min-displacement filter + per-animal-night cap; arc-length resampled. A purely "
                       "MECHANICAL merge (NOT destination-validated 'trips', NOT decision-to-decision "
                       "legs) that yields longer episode-scale units than the 3s-filtered bouts — a "
                       "second producible representation for the segmentation comparison."),
        "params": {"pause_merge_s": 5.0, "min_bout_s": 3.0, "min_disp_in": 15.0, "max_gap_s": 2.0,
                   "resample_n": 20, "max_per_night": 40},
    },
}


def validate_units(units_df: pd.DataFrame, paths: np.ndarray) -> None:
    """Assert an externally-supplied unit table follows the schema (used when legs/episodes arrive)."""
    missing = [c for c in UNIT_COLUMNS if c not in units_df.columns]
    if missing:
        raise ValueError(f"units_df missing required columns: {missing}")
    if len(units_df) != len(paths):
        raise ValueError(f"units_df ({len(units_df)}) and paths ({len(paths)}) length mismatch")
    if paths.ndim != 3 or paths.shape[2] != 2:
        raise ValueError(f"paths must be (N, L, 2); got {paths.shape}")


def load_units(segmentation_id: str, *, win: pd.DataFrame, nights: list, moving_thr_inps: float,
               roi_cfg: dict | None = None, **overrides):
    """Return ``(units_df, paths, meta)`` for a segmentation.

    Only ``original_3s_filtered_bouts`` is implemented; the leg/episode segmentations raise
    ``NotImplementedError`` (they await the decision-boundary analysis and should be supplied as an
    external unit table matching ``UNIT_COLUMNS`` + a paths array, then validated with ``validate_units``).
    """
    spec = SEGMENTATIONS.get(segmentation_id)
    if spec is None:
        raise KeyError(f"unknown segmentation_id {segmentation_id!r}; known: {list(SEGMENTATIONS)}")
    if spec["status"] != "implemented_provisional":
        raise NotImplementedError(
            f"segmentation {segmentation_id!r} is '{spec['status']}'. {spec['definition']} "
            "Supply an external unit table (schema = trajectory_units.UNIT_COLUMNS + paths) and call "
            "run_core_battery on it to compare representations.")
    p = {**spec["params"], **overrides}
    if segmentation_id == "original_3s_filtered_bouts":
        units, paths, blog = ts.extract_route_bouts(
            win, nights, moving_thr_inps=moving_thr_inps, min_disp_in=p["min_disp_in"],
            resample_n=p["resample_n"], max_per_night=p["max_per_night"],
            min_bout_s=p["min_bout_s"], max_gap_s=p["max_gap_s"], roi_cfg=roi_cfg)
    elif segmentation_id == "pause_merged_episodes":
        units, paths, blog = ts.extract_pause_merged_episodes(
            win, nights, moving_thr_inps=moving_thr_inps, pause_merge_s=p["pause_merge_s"],
            min_bout_s=p["min_bout_s"], min_disp_in=p["min_disp_in"], resample_n=p["resample_n"],
            max_per_night=p["max_per_night"], max_gap_s=p["max_gap_s"], roi_cfg=roi_cfg)
    else:
        raise NotImplementedError(f"no extractor wired for {segmentation_id!r}")
    units = units.reset_index(drop=True)
    units.insert(0, "segmentation_id", segmentation_id)
    meta = {"segmentation_id": segmentation_id, "status": spec["status"],
            "provisional": bool(spec["provisional"]), "label": spec["label"],
            "definition": spec["definition"], "params": p, "bout_log": blog}
    return units, paths, meta
