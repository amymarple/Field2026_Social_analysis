r"""
locomotor_states.py — Phase 1 / Module 3: the unified locomotor state machine and the
locomotor-bout-INITIATION hazard (the entry-side twin of the built site-residence-termination
/ leaving hazard in ``semimarkov_decisions``).

The built model answers "given residence, WHEN does it end (leave) and WHERE to". This module
answers the complementary question the built model never touched: "given the animal is SETTLED at
rest in a named ROI, what is the hazard of INITIATING a locomotor bout" — and, to do that
honestly, it forces the unified locomotor state machine (modules 1–2 substrate + a movement
hysteresis) that keeps four things distinct:

  1. movement INITIATION  ≠  ROI DEPARTURE          (a bout onset need not relocate the animal)
  2. activity IN PLACE    ≠  leaving                (a bout can occur without an ROI transition)
  3. brief PAUSE          ≠  settlement             (a stop inside a bout is not a new rest episode)
  4. ENTRY into an ROI    ≠  settled residence      (arrival while still moving is not rest)

State substrate reuse: the ROI side is module 5's EXACT hysteretic segmentation
(:func:`semimarkov_decisions.hysteretic_visits`) — we stamp each bin with its covering named
visit's ROI, so the two modules share one jitter-tolerant ROI substrate with no divergence. The
movement side is a NEW speed hysteresis over the same :func:`wiser_analysis_utils._hysteresis_state`.

Hard measurement invariants (WISER regime, inherited): frame-invariant only (inch frame UNVERIFIED);
a GAP is 'unknown' and is NEVER an onset; a rest episode that ends in a gap / below-plane dropout
region is CENSORED, not an initiation; onset is speed-onset ABOVE the ~7 in jitter floor — a LOWER
BOUND (in-nest sub-jitter stirring, the ~18:00 arousal, are invisible → never 'wake'). Social
features are STRICTLY pre-decision.

numpy + pandas only (imports in the ``cv`` env). Modeling (bits/decision ladder, nulls) reuses
``choice_models`` under the anaconda3 interpreter.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from . import wiser_analysis_utils as _w
    from . import semimarkov_decisions as _smd
except ImportError:                                   # src on sys.path
    import wiser_analysis_utils as _w                  # type: ignore
    import semimarkov_decisions as _smd                # type: ignore

MOVING_THR_INPS = 12.0        # smoothed speed above the stationary jitter ceiling => 'moving'
NS = 1_000_000_000

_STATES = ("rest", "local_active", "transit", "pause", "unknown")


# ===========================================================================
# per-animal-night unified locomotor state stream
# ===========================================================================

def locomotor_state_stream(fixes_an: pd.DataFrame, roi_cfg: dict, em, *,
                           buffer_in: float = 14.0, bin_s: float = 5.0,
                           roi_enter_s: float = 10.0, roi_exit_s: float = 30.0,
                           near_frac: float = 0.5, far_frac: float = 0.2,
                           move_thr_inps: float = MOVING_THR_INPS,
                           move_enter_s: float = 10.0, move_exit_s: float = 10.0,
                           move_near_frac: float = 0.5, move_far_frac: float = 0.2,
                           flicker_merge_s: float = 30.0, long_gap_s: float = 120.0,
                           visits: pd.DataFrame | None = None) -> pd.DataFrame:
    """One animal-night -> per-bin unified locomotor state stream.

    The ROI-state per bin is taken from module 5's flicker-merged :func:`hysteretic_visits` output
    (identical substrate, same ``bin_s``/origin). The MOVEMENT state per bin is a fresh speed
    hysteresis: per bin ``frac_moving`` = fraction of the bin's fixes with ``speed_inps_smooth`` (or
    the boolean ``moving`` column) above ``move_thr_inps``; evidence MOVING (>= ``move_near_frac``) /
    STATIONARY (<= ``move_far_frac``) / UNCERTAIN (else) / empty->NaN; debounced by
    :func:`wiser_analysis_utils._hysteresis_state` (enter ACTIVE after ``move_enter_s``, exit after
    ``move_exit_s`` — the brief-pause guard: a stationary blip shorter than ``move_exit_s`` HOLDS
    ACTIVE, so it neither splits a bout nor creates a rest episode).

    Unified per-bin ``state`` in {rest, local_active, transit, pause, unknown}:
      * ``unknown``      — empty bin or a bin containing a gap (never a decision);
      * ``local_active`` — ACTIVE and inside a named ROI-state (activity in place / pre-departure);
      * ``transit``      — ACTIVE and in 'open' (travelling);
      * ``rest``         — STATIONARY and inside a named ROI-state (SETTLED residence, module 2);
      * ``pause``        — STATIONARY and in 'open' (a stop in the open, NOT settlement).

    Columns: shortid, night, bin, t_start, t_end, roi_state, active, frac_moving, n_fix, has_gap,
    state. Empty frame (fixed columns) if the animal-night has no fixes."""
    cols = ["shortid", "night", "bin", "t_start", "t_end", "roi_state", "active",
            "frac_moving", "n_fix", "has_gap", "state"]
    g = fixes_an.sort_values("datetime").reset_index(drop=True)
    if g.empty:
        return pd.DataFrame(columns=cols)
    night = str(g["night"].iloc[0]); sid = str(g["shortid"].iloc[0])

    # -- shared bin grid (identical formula to hysteretic_visits so bins align) --------------
    t = pd.to_datetime(g["datetime"]).astype("datetime64[ns]").astype("int64").to_numpy()
    binns = int(round(bin_s * NS))
    b0 = t.min() - (t.min() % binns)
    bin_idx = ((t - b0) // binns).astype("int64")
    n_bins = int(bin_idx.max()) + 1
    counts = np.bincount(bin_idx, minlength=n_bins).astype(float)

    # -- movement machine ---------------------------------------------------------------------
    if "moving" in g.columns and g["moving"].notna().any():
        mov = pd.to_numeric(g["moving"], errors="coerce").fillna(0).to_numpy(float)
    else:
        sp = pd.to_numeric(g.get("speed_inps_smooth"), errors="coerce").to_numpy(float)
        mov = (sp > move_thr_inps).astype(float)
    gapf = g["gap_flag"].to_numpy(bool) if "gap_flag" in g.columns else np.zeros(len(g), bool)
    mov_cnt = np.bincount(bin_idx, weights=mov, minlength=n_bins)
    frac_moving = np.where(counts > 0, mov_cnt / np.maximum(counts, 1), np.nan)
    ev = np.where(np.isnan(frac_moving), np.nan,
                  np.where(frac_moving >= move_near_frac, 1.0,
                           np.where(frac_moving <= move_far_frac, 0.0, np.nan)))
    n_enter = max(1, int(np.ceil(move_enter_s / bin_s)))
    n_exit = max(1, int(np.ceil(move_exit_s / bin_s)))
    active = _w._hysteresis_state(ev, n_enter, n_exit)

    # per-bin gap presence (a bin holding any gap fix is 'unknown')
    bgap = np.zeros(n_bins, bool)
    if gapf.any():
        gi = np.unique(bin_idx[gapf])
        bgap[gi] = True

    # -- ROI substrate from module 5's flicker-merged visits (compute once if not supplied) ---
    if visits is None:
        visits = _smd.hysteretic_visits(g, roi_cfg, em, buffer_in=buffer_in, bin_s=bin_s,
                                        enter_s=roi_enter_s, exit_s=roi_exit_s, near_frac=near_frac,
                                        far_frac=far_frac, flicker_merge_s=flicker_merge_s,
                                        long_gap_s=long_gap_s)
    roi_state = np.array(["open"] * n_bins, dtype=object)
    for _, v in visits.iterrows():
        a = int(round((pd.Timestamp(v["t_start"]).value - b0) / binns))
        b = int(round((pd.Timestamp(v["t_end"]).value - b0) / binns)) - 1
        a = max(0, a); b = min(n_bins - 1, b)
        if b >= a:
            roi_state[a:b + 1] = v["roi"]

    # -- unified state ------------------------------------------------------------------------
    has_data = (counts > 0) & (~bgap)
    in_roi = roi_state != "open"
    state = np.where(~has_data, "unknown",
                     np.where(active, np.where(in_roi, "local_active", "transit"),
                              np.where(in_roi, "rest", "pause"))).astype(object)

    bins = np.arange(n_bins)
    t_start = pd.to_datetime(b0 + bins * binns)
    t_end = pd.to_datetime(b0 + (bins + 1) * binns)
    return pd.DataFrame({"shortid": sid, "night": night, "bin": bins,
                         "t_start": t_start, "t_end": t_end, "roi_state": roi_state,
                         "active": active, "frac_moving": frac_moving,
                         "n_fix": counts.astype(int), "has_gap": bgap, "state": state})


# ===========================================================================
# episodes (rest) and bouts (active) from a per-bin state stream
# ===========================================================================

def _runs(labels):
    """Run-length encode -> list of (i0, i1, label)."""
    out = []
    n = len(labels)
    if n == 0:
        return out
    s = 0
    for i in range(1, n + 1):
        if i == n or labels[i] != labels[s]:
            out.append((s, i - 1, labels[s])); s = i
    return out


def _data_segments(i0, i1, nodata, n_longgap):
    """Split the bin range [i0,i1] into DATA segments separated by 'unknown' (no-data) stretches of
    length >= ``n_longgap``. Short gaps are ABSORBED (held); leading/trailing/internal long gaps
    split. Each segment is trimmed to start and end on a data bin. Returns
    [(s0, s1, long_gap_after)] with ``long_gap_after`` = a long dropout follows this segment inside
    the run (so it must be censored, not scored as an onset)."""
    segs = []
    j = i0
    while j <= i1:
        if nodata[j]:                                    # skip a no-data stretch (leading/separator)
            k = j
            while k <= i1 and nodata[k]:
                k += 1
            j = k
            continue
        s0 = j                                           # start of a data segment (a data bin)
        long_after = False
        while j <= i1:
            if nodata[j]:
                k = j
                while k <= i1 and nodata[k]:
                    k += 1
                if (k - j) >= n_longgap:                  # long gap ends this segment
                    long_after = True
                    break
                j = k                                     # short gap absorbed
            else:
                j += 1
        s1 = j - 1
        while s1 >= s0 and nodata[s1]:                    # trim to end on a data bin
            s1 -= 1
        if s1 >= s0:
            segs.append((s0, s1, long_after))
        if long_after:                                    # advance past the long gap
            while j <= i1 and nodata[j]:
                j += 1
    return segs


def stationary_episodes(stream: pd.DataFrame, *, bin_s: float = 5.0,
                        long_gap_s: float = 120.0) -> pd.DataFrame:
    """Contiguous LOW-SPEED (``active``==False) episodes per animal-night = the bout-INITIATION
    at-risk unit. The movement hysteresis HOLDS through short signal dropout, so a brief gap or an
    ROI-edge label flicker does NOT fragment a continuous stationary period (the module-5 lesson:
    jitter/dropout must never shred the decision unit — segmenting the earlier per-bin 'rest' label
    over-fragmented it ~30x). An episode is split only by a LONG (>= ``long_gap_s``) internal signal
    dropout, and ends by:
      * ``onset``             — followed by an ACTIVE run (a locomotor bout begins): the event;
      * ``censored_gap``      — a long dropout follows (the animal may have moved unobserved);
      * ``censored_nightend`` — the record ends.
    ``roi`` = dominant named ROI over the episode's data bins (else 'open'); ``frac_in_named_roi`` =
    fraction of data bins inside a named ROI; ``in_named_roi`` = that fraction >= 0.5 (SETTLED
    RESIDENCE vs open low-speed). ``bin_start``/``bin_end`` index the per-animal-night stream."""
    cols = ["shortid", "night", "episode_id", "bin_start", "bin_end", "roi", "frac_in_named_roi",
            "in_named_roi", "t_start", "t_end", "dur_s", "n_bins", "n_data_bins", "ended_by", "has_gap"]
    rows = []
    if stream.empty:
        return pd.DataFrame(columns=cols)
    n_longgap = max(1, int(np.ceil(long_gap_s / bin_s)))
    for (sid, night), g in stream.groupby(["shortid", "night"], sort=False):
        g = g.sort_values("bin").reset_index(drop=True)
        act = g["active"].to_numpy(bool)
        nodata = (g["state"].to_numpy() == "unknown")
        roi = g["roi_state"].to_numpy()
        binv = g["bin"].to_numpy(); tst = g["t_start"].to_numpy(); ten = g["t_end"].to_numpy()
        runs = _runs(act)
        eid = 0
        for k, (i0, i1, lab) in enumerate(runs):
            if lab:                                       # active run (a bout) -> not at-risk
                continue
            followed_by_active = (k + 1 < len(runs))      # runs alternate -> next run is active
            segs = _data_segments(i0, i1, nodata, n_longgap)
            for s_idx, (s0, s1, long_after) in enumerate(segs):
                is_last = (s_idx == len(segs) - 1)
                if long_after:
                    ended = "censored_gap"
                elif is_last:
                    ended = "onset" if followed_by_active else "censored_nightend"
                else:
                    ended = "censored_gap"
                sl = slice(s0, s1 + 1)
                data_mask = ~nodata[s0:s1 + 1]
                n_data = int(data_mask.sum())
                named = (roi[s0:s1 + 1] != "open") & data_mask
                frac_named = float(named.sum() / n_data) if n_data else 0.0
                dom = "open"
                nm = roi[s0:s1 + 1][named]
                if len(nm):
                    vals, cnts = np.unique(nm, return_counts=True); dom = vals[cnts.argmax()]
                rows.append({"shortid": sid, "night": night, "episode_id": eid,
                             "bin_start": int(binv[s0]), "bin_end": int(binv[s1]),
                             "roi": dom, "frac_in_named_roi": frac_named,
                             "in_named_roi": bool(frac_named >= 0.5),
                             "t_start": pd.Timestamp(tst[s0]), "t_end": pd.Timestamp(ten[s1]),
                             "dur_s": (s1 - s0 + 1) * bin_s, "n_bins": s1 - s0 + 1,
                             "n_data_bins": n_data, "ended_by": ended,
                             "has_gap": bool((~data_mask).any())})
                eid += 1
    return pd.DataFrame(rows, columns=cols)


def bouts_table(stream: pd.DataFrame, *, bin_s: float = 5.0, long_gap_s: float = 120.0) -> pd.DataFrame:
    """Contiguous ACTIVE (local_active ∪ transit) runs = locomotor bouts (module-4 substrate).

    The movement hysteresis HOLDS ``active`` through empty/'unknown' bins (no data), so a raw active
    run can silently span a signal dropout. Like :func:`stationary_episodes`, a bout is therefore
    SPLIT at any internal no-data stretch >= ``long_gap_s`` (:func:`_data_segments`) — a dropout is
    'unknown', never observed locomotion, so ``dur_s`` counts only observed (data-bin) time and two
    bouts separated by an invisible stationary period are NOT merged. Short gaps (< ``long_gap_s``)
    are absorbed (one bout, flagged ``has_gap``). ``spans_dropout`` = the run was split by a long gap.

    ``origin_roi`` / ``dest_roi`` = the ROI-state at the stationary bin immediately BEFORE the run /
    AFTER the run (only assigned to the first / last segment; interior split segments get 'open').
    ``in_place`` = both named & equal (activity in place); ``relocating`` = both named & different (a
    named-ROI departure = the module-5 'leave'). ``from_rest`` = the preceding stationary bin is a
    named-ROI 'rest'."""
    cols = ["shortid", "night", "bout_id", "t_start", "t_end", "dur_s", "n_bins",
            "origin_roi", "dest_roi", "in_place", "relocating", "from_rest", "has_gap", "spans_dropout"]
    rows = []
    if stream.empty:
        return pd.DataFrame(columns=cols)
    n_longgap = max(1, int(np.ceil(long_gap_s / bin_s)))
    for (sid, night), g in stream.groupby(["shortid", "night"], sort=False):
        g = g.sort_values("bin").reset_index(drop=True)
        st = g["state"].to_numpy(); roi = g["roi_state"].to_numpy()
        act = g["active"].to_numpy(bool); nodata = (st == "unknown")
        tst = g["t_start"].to_numpy(); ten = g["t_end"].to_numpy()
        n = len(st)
        # A bout = a contiguous run of active==True (local_active ∪ transit merged: house->open->water
        # is ONE bout), split at long dropouts. origin/dest = the bracketing stationary ROIs.
        runs = _runs(act)
        bid = 0
        for i0, i1, lab in runs:
            if not lab:
                continue
            segs = _data_segments(i0, i1, nodata, n_longgap)
            if not segs:
                continue                                      # an all-dropout 'active' run -> unobserved
            run_origin = roi[i0 - 1] if i0 > 0 else "open"
            run_dest = roi[i1 + 1] if i1 + 1 < n else "open"
            run_from_rest = bool(i0 > 0 and st[i0 - 1] == "rest")
            multi = len(segs) > 1
            for s_idx, (s0, s1, long_after) in enumerate(segs):
                is_first = (s_idx == 0); is_last = (s_idx == len(segs) - 1)
                origin = run_origin if is_first else "open"
                dest = run_dest if is_last else "open"
                named = (origin != "open") and (dest != "open")
                rows.append({"shortid": sid, "night": night, "bout_id": bid,
                             "t_start": pd.Timestamp(tst[s0]), "t_end": pd.Timestamp(ten[s1]),
                             "dur_s": (s1 - s0 + 1) * bin_s, "n_bins": s1 - s0 + 1,
                             "origin_roi": origin, "dest_roi": dest,
                             "in_place": bool(named and origin == dest),
                             "relocating": bool(named and origin != dest),
                             "from_rest": bool(run_from_rest and is_first),
                             "has_gap": bool(nodata[s0:s1 + 1].any() or long_after or multi),
                             "spans_dropout": bool(multi)})
                bid += 1
    return pd.DataFrame(rows, columns=cols)


# ===========================================================================
# bout-initiation at-risk table (built from the held per-bin substrate)
# ===========================================================================

_LAY_KEYS = ("resource_type", "is_house", "is_food", "is_water", "is_refuge", "is_tunnel",
             "is_open", "dist_to_edge_in", "is_dropout_region")


def build_initiation_table(stat_eps: pd.DataFrame, stream: pd.DataFrame, em, *,
                           epoch_s: float = 5.0, bin_s: float = 5.0) -> pd.DataFrame:
    """Discretise each STATIONARY episode into ``epoch_s`` at-risk epochs, directly from the held
    per-bin ``stream`` (so short gaps do NOT fragment; the jitter-tolerant substrate is preserved).
    One row per epoch:
      * ``initiated`` = 1 only on the terminal epoch of an ``onset``-ended episode; 0 otherwise
        (right-censored for gap/nightend endings);
      * an epoch is DROPPED if any of its bins is empty or gap-flagged ('unknown', never an onset);
      * an epoch whose held ROI-state is a below-plane dropout region (refuge_4 burrow nights) is
        EXCLUDED (``em.is_dropout``).
    Covariates: ``rest_elapsed_s`` (elapsed low-speed time = the mandatory hazard basis f(τ)),
    ``in_named_roi`` (settled residence vs open low-speed), ROI + resource-type layout, clock-hour,
    per-night regime. (``moving_frac`` is intentionally NOT emitted — it would leak the onset.)"""
    if stat_eps.empty or stream.empty:
        return pd.DataFrame()
    k = max(1, int(round(epoch_s / bin_s)))
    sidx = {key: g.sort_values("bin").set_index("bin")
            for key, g in stream.groupby(["shortid", "night"], sort=False)}
    rows = []
    for _, ep in stat_eps.iterrows():
        g = sidx.get((ep["shortid"], ep["night"]))
        if g is None:
            continue
        sub = g.loc[ep["bin_start"]:ep["bin_end"]]
        if sub.empty:
            continue
        roi_s = sub["roi_state"].to_numpy(); nfix = sub["n_fix"].to_numpy()
        hasg = sub["has_gap"].to_numpy(bool); tst = sub["t_start"].to_numpy()
        reg = em.night_regime(ep["night"])
        night = ep["night"]
        n = len(sub); n_epochs = int(np.ceil(n / k))
        for e in range(n_epochs):
            lo = e * k; hi = min(n, lo + k)
            if np.any(nfix[lo:hi] == 0) or np.any(hasg[lo:hi]):
                continue                                     # unknown epoch -> dropped
            roi_e = roi_s[lo]
            if em.is_dropout(roi_e, night):
                continue                                     # below-plane dropout ROI -> excluded
            lay = em.layout_features(roi_e, night)
            is_terminal = (e == n_epochs - 1)
            initiated = int(is_terminal and ep["ended_by"] == "onset")
            t_ep = pd.Timestamp(tst[lo])
            rows.append({
                "shortid": ep["shortid"], "night": night, "visit_id": ep["episode_id"],
                "roi": roi_e, "epoch": e, "t_epoch": t_ep, "rest_elapsed_s": e * epoch_s,
                "in_named_roi": int(roi_e != "open"),
                "initiated": initiated, "censored": int(ep["ended_by"] != "onset"),
                "clock_hour": int(t_ep.hour),
                **{kk: lay[kk] for kk in _LAY_KEYS},
                "wet": int(bool(reg.get("wet", False))), "fireworks": int(bool(reg.get("fireworks", False))),
                "truncated": int(bool(reg.get("truncated", False))), "burrow": int(bool(reg.get("burrow", False))),
            })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.loc[:, ~out.columns.duplicated()]
    return out


# ===========================================================================
# four-distinction diagnostics (measurement gate, data-level)
# ===========================================================================

def distinction_diagnostics(stream: pd.DataFrame, bouts: pd.DataFrame, stat_eps: pd.DataFrame,
                            visits: pd.DataFrame) -> dict:
    """Quantify, at the data level, that the four distinctions are non-degenerate (the causal
    guarantees are in the selftest; this shows they actually bite on real data).

    D1 initiation ≠ departure: onset count vs relocating (departure) count, and their ratio.
    D2 in-place ≠ leaving: fraction of bouts that are in-place (no ROI transition).
    D3 pause ≠ settlement: bout count + median bout duration (pauses did not fragment them).
    D4 arrival ≠ settled: fraction of named ROI visits that contain NO rest bin (pass-through)."""
    n_onset = int((stat_eps["ended_by"] == "onset").sum()) if not stat_eps.empty else 0
    n_reloc = int(bouts["relocating"].sum()) if not bouts.empty else 0
    n_inplace = int(bouts["in_place"].sum()) if not bouts.empty else 0
    n_bouts = int(len(bouts))
    # D4: visits (named ROI episodes from module 5) with any 'rest' bin under them
    frac_visit_no_rest = np.nan
    if not visits.empty and not stream.empty:
        rest_bins = stream[stream["state"] == "rest"]
        has_rest = 0
        for _, vv in visits.iterrows():
            rb = rest_bins[(rest_bins["shortid"] == vv["shortid"]) & (rest_bins["night"] == vv["night"])
                           & (rest_bins["t_start"] >= vv["t_start"]) & (rest_bins["t_end"] <= vv["t_end"])]
            has_rest += int(len(rb) > 0)
        frac_visit_no_rest = float(1.0 - has_rest / max(1, len(visits)))
    return {
        "D1_initiation_vs_departure": {
            "n_bout_onsets": n_onset, "n_departures_relocating": n_reloc,
            "onset_to_departure_ratio": float(n_onset / n_reloc) if n_reloc else np.nan,
            "interpretation": "onsets >> departures => initiation is a distinct, more frequent event"},
        "D2_inplace_vs_leaving": {
            "n_bouts": n_bouts, "n_in_place": n_inplace, "n_relocating": n_reloc,
            "frac_in_place": float(n_inplace / n_bouts) if n_bouts else np.nan},
        "D3_pause_vs_settlement": {
            "n_bouts": n_bouts,
            "median_bout_s": float(bouts["dur_s"].median()) if n_bouts else np.nan,
            "note": "brief pauses did not fragment bouts (causal guarantee: selftest)"},
        "D4_arrival_vs_settled": {
            "n_named_visits": int(len(visits)),
            "frac_visits_no_rest": frac_visit_no_rest,
            "interpretation": "some ROI arrivals never settle (pass-through) => entry != rest"},
    }


def state_occupancy(stream: pd.DataFrame) -> pd.DataFrame:
    """Per (night, shortid): number of bins in each unified state (+ fraction). Support-gate input."""
    if stream.empty:
        return pd.DataFrame(columns=["night", "shortid"] + list(_STATES))
    tab = (stream.groupby(["night", "shortid", "state"]).size()
           .unstack("state").reindex(columns=_STATES).fillna(0).astype(int).reset_index())
    tot = tab[list(_STATES)].sum(axis=1).replace(0, np.nan)
    for s in _STATES:
        tab[f"frac_{s}"] = tab[s] / tot
    return tab


# ===========================================================================
# orchestrator
# ===========================================================================

def build_locomotor_tables(fixes: pd.DataFrame, roi_cfg: dict, em, *, bin_s: float = 5.0,
                           epoch_s: float = 5.0, add_social: bool = True,
                           social_window_s: float = 10.0, social_bin_s: float = 1.0,
                           state_kwargs: dict | None = None):
    """Build (stream, stat_eps, bouts, initiation, diagnostics, occupancy) from a cleaned
    multi-animal, multi-night ``fixes`` frame. ``stat_eps`` = stationary (low-speed) episodes = the
    bout-initiation at-risk unit. Social features on the initiation table are strictly pre-decision
    (reuses :func:`semimarkov_decisions.add_pre_decision_social`)."""
    sk = dict(state_kwargs or {}); sk.setdefault("bin_s", bin_s)
    lg = sk.get("long_gap_s", 120.0)
    streams, visits_all = [], []
    for (night, sid), g in fixes.groupby(["night", "shortid"]):
        v = _smd.hysteretic_visits(
            g, roi_cfg, em, buffer_in=sk.get("buffer_in", 14.0), bin_s=bin_s,
            enter_s=sk.get("roi_enter_s", 10.0), exit_s=sk.get("roi_exit_s", 30.0),
            near_frac=sk.get("near_frac", 0.5), far_frac=sk.get("far_frac", 0.2),
            flicker_merge_s=sk.get("flicker_merge_s", 30.0), long_gap_s=lg)
        streams.append(locomotor_state_stream(g, roi_cfg, em, visits=v, **sk))
        visits_all.append(v)
    stream = pd.concat(streams, ignore_index=True) if streams else pd.DataFrame()
    visits = pd.concat(visits_all, ignore_index=True) if visits_all else pd.DataFrame()
    stat_eps = stationary_episodes(stream, bin_s=bin_s, long_gap_s=lg)
    bouts = bouts_table(stream, bin_s=bin_s, long_gap_s=lg)
    initiation = build_initiation_table(stat_eps, stream, em, epoch_s=epoch_s, bin_s=bin_s)
    if add_social and not initiation.empty:
        sg = _smd.build_social_grid(fixes, bin_s=social_bin_s)
        initiation = _smd.add_pre_decision_social(initiation, sg, time_col="t_epoch",
                                                  window_s=social_window_s, bin_s=social_bin_s)
    diagnostics = distinction_diagnostics(stream, bouts, stat_eps, visits)
    occupancy = state_occupancy(stream)
    return stream, stat_eps, bouts, initiation, diagnostics, occupancy
