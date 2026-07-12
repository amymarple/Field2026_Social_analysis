r"""
semimarkov_decisions.py — build the two decision tables for the WISER agent-policy study.

The navigational "decision" is modeled as a hierarchical semi-Markov process over PLACES:

  A. Leaving hazard      — while resident in a named ROI, at each fixed epoch Δ decide
                           leave / stay, conditional on elapsed dwell (mandatory), etc.
  B. Destination choice  — given a leave, which named ROI is entered next.

Bout initiation/termination are only used to segment visits; they are not action categories.

This module turns a cleaned per-fix WISER frame into:
  * ``leave_decisions``       — one row per (animal, night, visit, at-risk epoch);
  * ``destination_decisions`` — one row per realized departure from a named origin ROI.

Hard invariants (WISER regime): frame-invariant only (inch frame unverified); a GAP is
'unknown' and is NEVER coded as staying or leaving (epochs spanning a gap are dropped; a
visit that ends in a gap or inside a below-plane dropout region is CENSORED, not a leave);
social features are STRICTLY pre-decision (a window ending before decision onset).

Input ``fixes`` schema (one cleaned fix per row), naive-UTC ``datetime``:
    shortid, night (str 'YYYY-MM-DD'), datetime, x, y,
    roi (named ROI or 'open'/'edge'), valid (bool), gap_flag (bool), moving (bool)
Optional: speed_inps_smooth. Cleaning/ROI assignment is done by the driver (``cv`` env);
the offline selftest feeds synthetic fixes of this schema directly.

numpy + pandas only (imports in ``cv``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RADIUS_1M_IN = 39.37          # 1 m in inches — jitter-floor-safe social radius

try:
    from . import wiser_analysis_utils as _w
except ImportError:                                   # src on sys.path
    import wiser_analysis_utils as _w                 # type: ignore


# ===========================================================================
# HYSTERETIC ROI-STATE visit segmentation (jitter-tolerant; replaces the raw
# point-in-ROI `segment_visits` that shredded rest into boundary-flicker micro-visits).
# Reuses the shelter-state machinery: _hysteresis_state (enter after sustained NEAR,
# exit only after sustained FAR, uncertain HOLDS) + buffered membership.
# ===========================================================================

def _roi_membership(x, y, roi, buffer_in):
    """(in_core, in_buffer) for a rect OR circle ROI, buffer grown by ``buffer_in``."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    if roi.get("shape") == "rect":
        return _w._rect_membership(x, y, roi, buffer_in)
    r = float(roi.get("radius_in", 12.0))
    d = np.hypot(x - float(roi["x"]), y - float(roi["y"]))
    return d <= r, d <= r + buffer_in


def hysteretic_visits(fixes_an: pd.DataFrame, roi_cfg: dict, em, *, buffer_in: float = 14.0,
                      bin_s: float = 5.0, enter_s: float = 10.0, exit_s: float = 30.0,
                      near_frac: float = 0.5, far_frac: float = 0.2,
                      flicker_merge_s: float = 30.0, flicker_max_dist_in: float | None = None,
                      long_gap_s: float = 120.0) -> pd.DataFrame:
    """Segment ONE animal-night into jitter-tolerant ROI visits.

    Per state-ROI (named ROIs on this night, **food folded into its containing house** and
    excluded, since food_i sits inside house_i): bin fixes at ``bin_s``; per bin evidence =
    NEAR (frac of bin's fixes within ROI+``buffer_in`` >= ``near_frac``), FAR (<= ``far_frac``),
    else UNCERTAIN (NaN). Hysteresis (:func:`wiser_analysis_utils._hysteresis_state`) enters after
    ``enter_s`` of sustained NEAR and exits only after ``exit_s`` of sustained FAR — UNCERTAIN
    and empty (dropout) bins HOLD, so boundary wobble at the ~7 in jitter floor cannot flicker a
    rest visit off. Each bin is assigned to the in-state ROI with the highest frac_near (else
    'open'); contiguous runs are visits.

    Flicker-vs-genuine-loop merge: a same-ROI return (roi -> open -> same roi) is merged into one
    visit ONLY when the open excursion is (a) short (< ``flicker_merge_s``), (b) stayed near the
    boundary (max fix distance to the ROI centre < ``flicker_max_dist_in``, default 3x buffer), AND
    (c) established NO other ROI's state. A long / far / other-ROI excursion is kept as a genuine
    leave-and-return. Returns visits (schema of :func:`segment_visits` + excursion metadata)."""
    g = fixes_an.sort_values("datetime").reset_index(drop=True)
    empty = pd.DataFrame(columns=["shortid", "night", "visit_id", "roi", "t_start", "t_end",
                                  "dwell_s", "n_fix", "ended_by", "next_roi", "has_gap",
                                  "excursion_s", "excursion_max_dist_in"])
    if g.empty:
        return empty
    night = str(g["night"].iloc[0]); sid = g["shortid"].iloc[0]
    if flicker_max_dist_in is None:
        flicker_max_dist_in = 3.0 * buffer_in
    rois = {r["name"]: r for r in (roi_cfg.get("rois", []) or [])}
    active = [r for r in em.active_rois(night) if em.resource_type(r) != "food"]  # food ⊂ house
    active = [r for r in active if r in rois]
    if not active:
        return empty

    NS = 1_000_000_000
    t = pd.to_datetime(g["datetime"]).astype("datetime64[ns]").astype("int64").to_numpy()
    binns = int(round(bin_s * NS))
    b0 = t.min() - (t.min() % binns)
    bin_idx = ((t - b0) // binns).astype("int64")
    n_bins = int(bin_idx.max()) + 1
    x = g["x"].to_numpy(float); y = g["y"].to_numpy(float)
    gapf = g["gap_flag"].to_numpy(bool) if "gap_flag" in g.columns else np.zeros(len(g), bool)
    n_enter = max(1, int(np.ceil(enter_s / bin_s)))
    n_exit = max(1, int(np.ceil(exit_s / bin_s)))

    # per-ROI frac_near per bin + per-ROI hysteretic state
    frac_near = {}; state = {}
    counts = np.bincount(bin_idx, minlength=n_bins).astype(float)
    for rn in active:
        _, in_buf = _roi_membership(x, y, rois[rn], buffer_in)
        near_cnt = np.bincount(bin_idx, weights=in_buf.astype(float), minlength=n_bins)
        fn = np.where(counts > 0, near_cnt / np.maximum(counts, 1), np.nan)
        frac_near[rn] = fn
        ev = np.where(np.isnan(fn), np.nan, np.where(fn >= near_frac, 1.0,
                                                     np.where(fn <= far_frac, 0.0, np.nan)))
        state[rn] = _w._hysteresis_state(ev, n_enter, n_exit)

    # assign each bin to the in-state ROI with the highest frac_near, else 'open' (vectorised)
    roi_list = list(active)
    S = np.stack([state[rn] for rn in roi_list], axis=1)                 # (n_bins, n_roi) bool
    F = np.stack([np.where(np.isnan(frac_near[rn]), -1.0, frac_near[rn])
                  for rn in roi_list], axis=1)
    Fm = np.where(S, F, -np.inf)
    any_state = S.any(axis=1)
    idx = np.argmax(Fm, axis=1)
    assigned = np.array(["open"] * n_bins, dtype=object)
    ra = np.array(roi_list, dtype=object)
    assigned[any_state] = ra[idx[any_state]]

    # bin centroids (for excursion distance) + empty-bin / gap tracking (vectorised)
    bx = np.full(n_bins, np.nan); by = np.full(n_bins, np.nan); bgap = np.zeros(n_bins, bool)
    _bc = pd.DataFrame({"b": bin_idx, "x": x, "y": y, "g": gapf}).groupby("b").agg(
        x=("x", "median"), y=("y", "median"), g=("g", "any"))
    bi = _bc.index.to_numpy()
    bx[bi] = _bc["x"].to_numpy(); by[bi] = _bc["y"].to_numpy(); bgap[bi] = _bc["g"].to_numpy()

    # run-length encode assigned -> raw visits (named + open)
    runs = []
    s = 0
    for i in range(1, n_bins + 1):
        if i == n_bins or assigned[i] != assigned[s]:
            runs.append([s, i - 1, assigned[s]]); s = i

    # flicker-merge pass: named-A / short-near-open / named-A -> single A
    merged = []
    k = 0
    while k < len(runs):
        r = runs[k]
        if (r[2] == "open" and merged and k + 1 < len(runs)
                and merged[-1][2] == runs[k + 1][2] and merged[-1][2] != "open"):
            a = merged[-1][2]
            open_s = (r[1] - r[0] + 1) * bin_s
            seg = slice(r[0], r[1] + 1)
            dd = np.hypot(bx[seg] - float(rois[a]["x"]), by[seg] - float(rois[a]["y"]))
            max_dist = np.nanmax(dd) if np.any(~np.isnan(dd)) else np.inf
            other = any(state[o][r[0]:r[1] + 1].any() for o in active if o != a)
            if open_s < flicker_merge_s and max_dist < flicker_max_dist_in and not other:
                prev = merged.pop(); nxt = runs[k + 1]
                merged.append([prev[0], nxt[1], a]); k += 2; continue
        merged.append(list(r)); k += 1

    named = [r for r in merged if r[2] != "open"]
    rows = []
    for idx, r in enumerate(named):
        a, b = r[0], r[1]
        start = pd.Timestamp(b0 + a * binns)
        end = pd.Timestamp(b0 + (b + 1) * binns)
        # actual fixes in this visit
        fmask = (bin_idx >= a) & (bin_idx <= b)
        nfix = int(fmask.sum())
        has_gap = bool(bgap[a:b + 1].any())
        nxt = named[idx + 1][2] if idx + 1 < len(named) else None
        # excursion to next named visit (gap between merged runs' bin ranges)
        exc_s = np.nan; exc_dist = np.nan
        if nxt is not None:
            gap0, gap1 = b + 1, named[idx + 1][0] - 1
            exc_s = max(0, (gap1 - gap0 + 1)) * bin_s
            if gap1 >= gap0:
                dd = np.hypot(bx[gap0:gap1 + 1] - float(rois[r[2]]["x"]),
                              by[gap0:gap1 + 1] - float(rois[r[2]]["y"]))
                exc_dist = np.nanmax(dd) if np.any(~np.isnan(dd)) else np.nan
        # ended_by: last named visit -> nightend; a long dropout at the tail -> gap; else leave
        if nxt is None:
            ended = "censored_nightend"
        else:
            tail_gap = bgap[b:named[idx + 1][0]].sum() * bin_s if named[idx + 1][0] > b else 0
            ended = "gap" if tail_gap >= long_gap_s else "leave"
        rows.append({"shortid": sid, "night": night, "visit_id": idx, "roi": r[2],
                     "t_start": start, "t_end": end,
                     "dwell_s": (b - a + 1) * bin_s, "n_fix": nfix,
                     "ended_by": ended, "next_roi": nxt, "has_gap": has_gap,
                     "excursion_s": float(exc_s) if exc_s == exc_s else np.nan,
                     "excursion_max_dist_in": float(exc_dist) if exc_dist == exc_dist else np.nan})
    return pd.DataFrame(rows) if rows else empty


# ---------------------------------------------------------------------------
# visit segmentation
# ---------------------------------------------------------------------------

def _named(roi_series: pd.Series) -> pd.Series:
    """Map 'edge'/'open'/NaN -> 'open'; keep named ROIs."""
    s = roi_series.astype("object").where(roi_series.notna(), "open")
    return s.where(~s.isin(["edge", "open", ""]), "open")


def _runs(labels, times):
    """Run-length encode a label stream. Returns list of dicts with i0,i1,label,t0,t1."""
    runs = []
    n = len(labels)
    if n == 0:
        return runs
    i0 = 0
    for i in range(1, n + 1):
        if i == n or labels[i] != labels[i0]:
            runs.append({"i0": i0, "i1": i - 1, "label": labels[i0],
                         "t0": times[i0], "t1": times[i - 1]})
            i0 = i
    return runs


def segment_visits(fixes_an: pd.DataFrame, *, min_dwell_s: float = 3.0,
                   max_open_flicker_s: float = 2.0, gap_col: str = "gap_flag") -> pd.DataFrame:
    """Segment one animal-night's fixes into visits (dwell episodes) in named ROIs / 'open'.

    Cleaning: a named run shorter than ``min_dwell_s`` becomes 'open'; a short 'open' flicker
    (< ``max_open_flicker_s``) between two runs of the SAME named ROI is absorbed (jitter
    out-and-back). Returns visits with ``ended_by`` in {'leave','censored_nightend','gap'}
    and ``next_roi`` (the following named visit's ROI, else None)."""
    g = fixes_an.sort_values("datetime").reset_index(drop=True)
    if g.empty:
        return pd.DataFrame(columns=["shortid", "night", "visit_id", "roi", "t_start", "t_end",
                                     "dwell_s", "n_fix", "ended_by", "next_roi", "has_gap"])
    labels = _named(g["roi"]).to_numpy()
    times = g["datetime"].to_numpy()
    dur = lambda t0, t1: (pd.Timestamp(t1) - pd.Timestamp(t0)).total_seconds()

    runs = _runs(labels, times)
    # pass 1: demote too-brief named runs to 'open'
    for r in runs:
        if r["label"] != "open" and dur(r["t0"], r["t1"]) < min_dwell_s:
            r["label"] = "open"
    runs = _runs([r["label"] for r in _expand(runs)], times) if False else _merge_adjacent(runs)
    # pass 2: absorb short 'open' flickers between identical named neighbours
    merged = []
    k = 0
    while k < len(runs):
        r = runs[k]
        if (r["label"] == "open" and 0 < k < len(runs) - 1
                and runs[k - 1]["label"] == runs[k + 1]["label"] != "open"
                and dur(r["t0"], r["t1"]) < max_open_flicker_s):
            # fuse prev + this + next into one named visit
            prev = merged.pop()
            nxt = runs[k + 1]
            merged.append({"i0": prev["i0"], "i1": nxt["i1"], "label": prev["label"],
                           "t0": prev["t0"], "t1": nxt["t1"]})
            k += 2
        else:
            merged.append(dict(r))
            k += 1
    runs = _merge_adjacent(merged)

    # gap presence per run (any gap_flag among its fixes)
    gapf = g[gap_col].to_numpy() if gap_col in g.columns else np.zeros(len(g), bool)
    rows = []
    named_runs = [r for r in runs if r["label"] != "open"]
    for idx, r in enumerate(named_runs):
        has_gap = bool(gapf[r["i0"]:r["i1"] + 1].any())
        # find the next named run's label (destination)
        nxt = named_runs[idx + 1]["label"] if idx + 1 < len(named_runs) else None
        # ended_by: last named visit of the night -> censored_nightend; gap in the trailing
        # transit -> 'gap'; else 'leave'
        if nxt is None:
            ended = "gap" if has_gap else "censored_nightend"
        else:
            # was there a gap between this run's end and the next named run's start?
            between = gapf[r["i1"]:named_runs[idx + 1]["i0"] + 1]
            ended = "gap" if between.any() else "leave"
        rows.append({"shortid": g["shortid"].iloc[0], "night": g["night"].iloc[0],
                     "visit_id": idx, "roi": r["label"],
                     "t_start": pd.Timestamp(r["t0"]), "t_end": pd.Timestamp(r["t1"]),
                     "dwell_s": dur(r["t0"], r["t1"]), "n_fix": r["i1"] - r["i0"] + 1,
                     "ended_by": ended, "next_roi": nxt, "has_gap": has_gap})
    return pd.DataFrame(rows)


def _merge_adjacent(runs):
    """Merge consecutive runs with the same label."""
    out = []
    for r in runs:
        if out and out[-1]["label"] == r["label"]:
            out[-1]["i1"] = r["i1"]
            out[-1]["t1"] = r["t1"]
        else:
            out.append(dict(r))
    return out


def _expand(runs):   # placeholder kept for readability of the (disabled) branch above
    return runs


# ---------------------------------------------------------------------------
# leaving-hazard table (at-risk epochs)
# ---------------------------------------------------------------------------

def build_leave_table(visits: pd.DataFrame, fixes: pd.DataFrame, em, *, epoch_s: float = 5.0,
                      min_moving_speed_inps: float | None = None) -> pd.DataFrame:
    """Discretise each NAMED visit into at-risk epochs of ``epoch_s`` seconds. One row per epoch:
    ``left`` = 1 only on the terminal epoch of a 'leave'-ended visit; 0 otherwise (right-censored
    for 'censored_nightend'). **Epochs of a 'gap'-ended visit's tail, and any epoch inside a
    below-plane dropout region, are dropped (unknown — never a leave).** Adds elapsed dwell,
    moving fraction, layout features, and per-night regime flags."""
    rows = []
    # Pre-group fixes by (shortid, night) into sorted numpy arrays ONCE, then searchsorted per
    # visit/epoch — avoids re-scanning the whole (multi-million-row) frame inside the visit loop.
    NS = 1_000_000_000
    fx = fixes.copy()
    fx["_ns"] = pd.to_datetime(fx["datetime"]).astype("datetime64[ns]").astype("int64")
    fx = fx.sort_values(["shortid", "night", "_ns"])
    groups = {}
    for (sid, night), g in fx.groupby(["shortid", "night"], sort=False):
        groups[(str(sid), str(night))] = (
            g["_ns"].to_numpy("int64"),
            g["gap_flag"].to_numpy(bool) if "gap_flag" in g.columns else np.zeros(len(g), bool),
            g["moving"].to_numpy(float) if "moving" in g.columns else np.full(len(g), np.nan),
        )
    estep = int(round(epoch_s * NS))
    for _, v in visits.iterrows():
        if v["roi"] == "open":
            continue
        # Below-plane dropout region (e.g. refuge_4 on burrow nights): occupancy is under-counted,
        # so EVERY visit there is excluded entirely — a signal dropout must never be scored as a
        # leave, and the surviving short/tracked visits would be a biased subsample. This matches
        # build_destination_table. (Gap-ended NON-dropout visits are kept but right-censored: their
        # terminal epoch is left=0 and the epoch spanning the gap is dropped inside the loop below.)
        if em.is_dropout(v["roi"], v["night"]):
            continue
        key = (str(v["shortid"]), str(v["night"]))
        g = groups.get(key)
        if g is None:
            continue
        t_arr, gap_arr, mov_arr = g
        t0 = pd.Timestamp(v["t_start"]).value
        t_end = pd.Timestamp(v["t_end"]).value
        n_epochs = int(np.floor(max(0, t_end - t0) / estep)) + 1
        lay = em.layout_features(v["roi"], v["night"])
        reg = em.night_regime(v["night"])
        for e in range(n_epochs):
            te = t0 + e * estep
            lo = int(np.searchsorted(t_arr, te, "left"))
            hi = int(np.searchsorted(t_arr, te + estep, "left"))
            if hi <= lo:
                continue                                    # no data in epoch -> unknown, drop
            if gap_arr[lo:hi].any():
                continue                                    # gap inside epoch -> unknown, drop
            is_terminal = (e == n_epochs - 1)
            left = int(is_terminal and v["ended_by"] == "leave")
            mvslice = mov_arr[lo:hi]
            mv = float(np.nanmean(mvslice)) if np.any(~np.isnan(mvslice)) else np.nan
            te_ts = pd.Timestamp(te)
            rows.append({
                "shortid": v["shortid"], "night": v["night"], "visit_id": v["visit_id"],
                "roi": v["roi"], "epoch": e, "t_epoch": te_ts,
                "dwell_elapsed_s": (te - t0) / NS,
                "moving_frac": mv,
                "left": left, "censored": int(v["ended_by"] != "leave"),
                "clock_hour": int(te_ts.hour),
                **{k: lay[k] for k in ("roi", "resource_type", "is_house", "is_food", "is_water",
                                       "is_refuge", "is_tunnel", "dist_to_edge_in",
                                       "is_dropout_region")},
                "wet": int(bool(reg.get("wet", False))),
                "fireworks": int(bool(reg.get("fireworks", False))),
                "truncated": int(bool(reg.get("truncated", False))),
                "burrow": int(bool(reg.get("burrow", False))),
            })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.loc[:, ~out.columns.duplicated()]
    return out


# ---------------------------------------------------------------------------
# destination-choice table (one row per realized departure)
# ---------------------------------------------------------------------------

def build_destination_table(visits: pd.DataFrame, em) -> pd.DataFrame:
    """One row per realized departure from a NAMED origin ROI with an observed next named ROI.
    Attaches origin layout + dwell + clock + regime. The origin-specific CHOICE SET (empirically
    supported destinations) is finalised in the modeling step per training fold; the layout
    reachable set (all active named ROIs) is available via ``em.choice_set_layout``."""
    rows = []
    for _, v in visits.iterrows():
        if v["roi"] == "open" or v["ended_by"] != "leave" or not v["next_roi"]:
            continue
        if em.is_dropout(v["roi"], v["night"]):
            continue                                        # origin in dropout region -> unreliable
        lay = em.layout_features(v["roi"], v["night"])
        reg = em.night_regime(v["night"])
        rows.append({
            "shortid": v["shortid"], "night": v["night"], "visit_id": v["visit_id"],
            "origin": v["roi"], "dest": v["next_roi"], "t_dep": v["t_end"],
            "dwell_s": float(v["dwell_s"]), "clock_hour": int(pd.Timestamp(v["t_end"]).hour),
            "origin_resource_type": lay["resource_type"], "origin_dist_to_edge_in": lay["dist_to_edge_in"],
            "wet": int(bool(reg.get("wet", False))), "fireworks": int(bool(reg.get("fireworks", False))),
            "truncated": int(bool(reg.get("truncated", False))), "burrow": int(bool(reg.get("burrow", False))),
        })
    return pd.DataFrame(rows)


def supported_choice_sets(dest_table: pd.DataFrame, *, min_support: int = 3) -> dict:
    """Origin-specific choice set C(o) = destinations observed from o with >= ``min_support``
    departures (computed on TRAINING data only by the caller). Returns {origin: [dests]}."""
    cs = {}
    for o, g in dest_table.groupby("origin"):
        vc = g["dest"].value_counts()
        cs[o] = sorted(vc[vc >= min_support].index.tolist())
    return cs


# ---------------------------------------------------------------------------
# strictly pre-decision social features
# ---------------------------------------------------------------------------

def build_social_grid(fixes: pd.DataFrame, *, bin_s: float = 1.0) -> pd.DataFrame:
    """Per-(night) synchronized position grid for all animals at ``bin_s`` bins: median x,y
    per (night, shortid, tbin). Used to read others' positions STRICTLY before a decision."""
    f = fixes.copy()
    if "valid" in f.columns:
        f = f[f["valid"].astype(bool)]
    f = f.dropna(subset=["x", "y", "datetime"])
    t0 = f.groupby("night")["datetime"].transform("min")
    f["tbin"] = ((f["datetime"] - t0).dt.total_seconds() // bin_s).astype("int64")
    grid = (f.groupby(["night", "shortid", "tbin"])
              .agg(x=("x", "median"), y=("y", "median"),
                   # stamp the bin by its END (latest fix): a backward strictly-before merge then
                   # selects only bins whose LAST fix precedes the decision, so a bin straddling
                   # the decision instant (median would mix pre- and post-decision positions) is
                   # excluded -> the social feature stays STRICTLY pre-decision.
                   t=("datetime", "max"),
                   moving=("moving", "mean") if "moving" in f.columns else ("x", "size"))
              .reset_index())
    return grid


def add_pre_decision_social(table: pd.DataFrame, social_grid: pd.DataFrame, *,
                            time_col: str, window_s: float = 10.0, radius_in: float = RADIUS_1M_IN,
                            bin_s: float = 1.0) -> pd.DataFrame:
    """Attach STRICTLY pre-decision social features to each decision using each conspecific's
    last position in ``[t - window_s, t)`` (never at/after the decision instant). Adds
    ``nn_dist_in``, ``n_within_1m``, ``mean_others_dist_in``, ``n_others_present``, ``nn_id``.
    Missing (focal or others absent in the pre-window) -> NaN; never imputed.

    Vectorised: one backward ``merge_asof`` per animal (strictly-before, within tolerance),
    then a reduction over the per-animal distance columns — O(n_animals * n_decisions)."""
    out = table.reset_index(drop=True).copy()
    if out.empty or social_grid.empty:
        for c in ["nn_dist_in", "n_within_1m", "mean_others_dist_in", "n_others_present", "nn_id"]:
            out[c] = np.nan if c != "n_others_present" else 0
        return out
    out["_t"] = pd.to_datetime(out[time_col]).astype("datetime64[ns]")
    out["_row"] = np.arange(len(out))
    sg = social_grid.copy()
    sg["t"] = pd.to_datetime(sg["t"]).astype("datetime64[ns]")
    animals = sorted(sg["shortid"].astype(str).unique())
    tol = pd.Timedelta(seconds=window_s)

    # per-animal position at each decision's pre-window (aligned to _row)
    ax = np.full((len(out), len(animals)), np.nan)
    ay = np.full((len(out), len(animals)), np.nan)
    for j, a in enumerate(animals):
        ga = sg[sg["shortid"].astype(str) == a][["night", "t", "x", "y"]].sort_values("t")
        parts = []
        for night, gdec in out.groupby("night"):
            gan = ga[ga["night"] == night]
            if gan.empty:
                continue
            m = pd.merge_asof(gdec[["_row", "_t"]].sort_values("_t"),
                              gan[["t", "x", "y"]].sort_values("t"),
                              left_on="_t", right_on="t", direction="backward",
                              allow_exact_matches=False, tolerance=tol)
            parts.append(m[["_row", "x", "y"]])
        if parts:
            p = pd.concat(parts).set_index("_row").reindex(out["_row"])
            ax[:, j] = p["x"].to_numpy(float)
            ay[:, j] = p["y"].to_numpy(float)

    focal = out["shortid"].astype(str).to_numpy()
    aidx = {a: j for j, a in enumerate(animals)}
    fx = np.array([ax[i, aidx[focal[i]]] if focal[i] in aidx else np.nan for i in range(len(out))])
    fy = np.array([ay[i, aidx[focal[i]]] if focal[i] in aidx else np.nan for i in range(len(out))])
    d = np.hypot(ax - fx[:, None], ay - fy[:, None])
    for i in range(len(out)):                        # blank the focal's own column
        if focal[i] in aidx:
            d[i, aidx[focal[i]]] = np.nan
    d[np.isnan(fx)] = np.nan                          # focal unknown -> all unknown

    present = np.sum(~np.isnan(d), axis=1)
    with np.errstate(all="ignore"):
        nn = np.where(present > 0, np.nanmin(d, axis=1), np.nan)
        mean_d = np.where(present > 0, np.nanmean(d, axis=1), np.nan)
        n_within = np.nansum(d < radius_in, axis=1).astype(float)
    n_within[present == 0] = np.nan
    nn_id = np.array([animals[int(np.nanargmin(d[i]))] if present[i] > 0 else None
                      for i in range(len(out))], dtype=object)
    out["nn_dist_in"] = nn
    out["n_within_1m"] = n_within
    out["mean_others_dist_in"] = mean_d
    out["n_others_present"] = present
    out["nn_id"] = nn_id
    return out.drop(columns=["_t", "_row"])


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------

def build_decision_tables(fixes: pd.DataFrame, em, *, epoch_s: float = 5.0,
                          min_dwell_s: float = 3.0, social_window_s: float = 10.0,
                          social_bin_s: float = 1.0, add_social: bool = True):
    """Build (leave_decisions, destination_decisions, visits) from a cleaned multi-animal,
    multi-night ``fixes`` frame. Social features are strictly pre-decision."""
    visits_all = []
    for (night, sid), g in fixes.groupby(["night", "shortid"]):
        visits_all.append(segment_visits(g, min_dwell_s=min_dwell_s))
    visits = pd.concat(visits_all, ignore_index=True) if visits_all else pd.DataFrame()
    if visits.empty:
        return (pd.DataFrame(), pd.DataFrame(), visits)
    leave = build_leave_table(visits, fixes, em, epoch_s=epoch_s)
    dest = build_destination_table(visits, em)
    if add_social and not (leave.empty and dest.empty):
        sg = build_social_grid(fixes, bin_s=social_bin_s)
        if not leave.empty:
            leave = add_pre_decision_social(leave, sg, time_col="t_epoch",
                                            window_s=social_window_s, bin_s=social_bin_s)
        if not dest.empty:
            dest = add_pre_decision_social(dest, sg, time_col="t_dep",
                                           window_s=social_window_s, bin_s=social_bin_s)
    return leave, dest, visits
