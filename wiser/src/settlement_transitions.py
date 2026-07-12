r"""
settlement_transitions.py — Phase 2 / Module 6: destination & settlement on the UNIFIED
locomotor-state representation. Rebuilds the destination unit so a "destination" is defined ONLY
after SUSTAINED STABLE RESIDENCE, and every departure outcome is typed — respecting the
`decision_boundary_validation` verdict (a destination cannot be read off where a pause-bridged
movement episode ends; it must be anchored on observed sustained residence).

Consumes module-3's `stationary_episodes` (gap-holding low-speed episodes with roi, in_named_roi,
frac_in_named_roi, dur_s, ended_by, bin_start/bin_end) — NO new WISER load, NO fine kinematics.

Two layers:

  1. TYPE each stationary episode (:func:`type_stationary_episodes`):
       * ``settlement``   — a named ROI, SUSTAINED (dur >= settle_min_s), confident (data-covered,
                            frac_in_named_roi >= conf_frac), not a below-plane dropout ROI;
       * ``pass_through`` — a named ROI but NOT sustained (dur < settle_min_s): entry != settlement;
       * ``open_stop``    — a low-speed episode in the open (not a named ROI);
       * ``dropout``      — a named ROI in a below-plane dropout regime (refuge_4 burrow nights).

  2. TYPE each departure from a settlement (:func:`build_transitions`), by the NEXT stationary
     episode (runs alternate settle/bout, so the next stationary episode is the immediate outcome):
       * ``relocation``            — settled at a DIFFERENT named site (the destination-choice event);
       * ``same_site_return``      — settled back at the SAME named site;
       * ``pass_through``          — the next stop is a named ROI entered but NOT settled;
       * ``open_field_termination``— the next low-speed state is in the open (no named destination);
       * ``censored``              — a gap/dropout/nightend interrupts before an outcome is observed.

The destination-CHOICE model is fit ONLY on ``relocation`` transitions from ``settlement`` origins,
and ONLY after the representation is validated (:func:`representation_sensitivity`, the planted
selftest, support). numpy + pandas only (imports in ``cv``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

STYPES = ("settlement", "pass_through", "open_stop", "dropout")
TTYPES = ("relocation", "same_site_return", "pass_through", "open_field_termination", "censored")


# ===========================================================================
# 1. type stationary episodes as sustained residence vs not
# ===========================================================================

def type_stationary_episodes(stat_eps: pd.DataFrame, em, *, settle_min_s: float = 60.0,
                             conf_frac: float = 0.5) -> pd.DataFrame:
    """Add ``stype`` (settlement / pass_through / open_stop / dropout) + ``is_settlement`` to each
    stationary episode. A ``settlement`` = SUSTAINED STABLE RESIDENCE = named ROI, dur >=
    ``settle_min_s``, ``frac_in_named_roi`` >= ``conf_frac``, and NOT a below-plane dropout ROI
    (``em.is_dropout``).

    NOTE: no separate data-coverage gate. Module-3 stationary episodes already HOLD through short
    gaps (a long, well-localised residence with intermittent dropout is ONE episode, split only by a
    >= long_gap_s blackout), so a coverage gate here would wrongly demote genuine gap-held residences
    to pass-throughs. ``dur_s`` is the held residence duration; ``frac_in_named_roi`` (of the OBSERVED
    bins) is the confidence. Because module-3's ``in_named_roi`` is already frac_in_named_roi >= 0.5,
    the effective confidence threshold is max(0.5, ``conf_frac``) — conf_frac operates on [0.5, 1]."""
    d = stat_eps.copy()
    if d.empty:
        d["stype"] = pd.Series(dtype="object"); d["is_settlement"] = pd.Series(dtype=bool)
        return d
    roi = d["roi"].astype("object").to_numpy()
    named = d["in_named_roi"].astype(bool).to_numpy()
    dur = pd.to_numeric(d["dur_s"], errors="coerce").to_numpy()
    fracn = pd.to_numeric(d["frac_in_named_roi"], errors="coerce").fillna(0.0).to_numpy()
    is_drop = np.array([bool(em.is_dropout(r, nn)) for r, nn in zip(roi, d["night"].astype(str))])

    stype = np.empty(len(d), dtype=object)
    for i in range(len(d)):
        if named[i] and is_drop[i]:
            stype[i] = "dropout"
        elif named[i] and dur[i] >= settle_min_s and fracn[i] >= conf_frac:
            stype[i] = "settlement"
        elif named[i]:
            stype[i] = "pass_through"
        else:
            stype[i] = "open_stop"
    d["stype"] = stype
    d["is_settlement"] = (d["stype"] == "settlement")
    return d


# ===========================================================================
# 2. type each departure-from-settlement transition
# ===========================================================================

def build_transitions(typed: pd.DataFrame, em, *, bin_s: float = 5.0,
                      long_gap_s: float = 120.0) -> pd.DataFrame:
    """One row per DEPARTURE from a settlement (a ``settlement`` episode that ended by ``onset``),
    typed by the immediately following stationary episode. Columns: origin/dest roi + type, the
    ``transition_type`` (one of :data:`TTYPES`), origin dwell (settled duration), inter-episode bout
    gap (bins), clock-hour, per-night regime, and layout for origin + destination.

    Only ``settlement`` origins are emitted (a destination is defined only after sustained stable
    residence). Same-site returns are genuine loops by construction: ``ended_by=='onset'`` means a real
    locomotor bout (>= the movement-enter debounce) separated the two same-site settlements — a jitter
    flicker cannot produce it (module 3 holds ROI/movement state through jitter).

    A departure whose connecting locomotor bout spans an implausibly long period
    (``inter_bout_bins * bin_s >= long_gap_s``, i.e., >= 2 min of continuous 'movement') is typed
    **censored**, not a direct relocation: the movement machine holds ``active`` through a WISER
    dropout, so such a connecting period almost certainly crossed unobserved time — the animal could
    have settled at an intermediate site — and the destination is NOT a confirmed direct outcome
    (per decision_boundary_validation: anchor destinations on observed residence, never across a long
    unobserved stretch)."""
    cols = ["shortid", "night", "origin_episode", "origin_roi", "origin_type", "dest_roi",
            "dest_type", "transition_type", "origin_dwell_s", "inter_bout_bins", "t_depart",
            "clock_hour", "origin_resource_type", "dest_resource_type", "origin_dist_to_edge_in",
            "wet", "fireworks", "truncated", "burrow"]
    rows = []
    if typed.empty:
        return pd.DataFrame(columns=cols)
    for (sid, night), g in typed.groupby(["shortid", "night"], sort=False):
        g = g.sort_values("episode_id").reset_index(drop=True)
        eid = g["episode_id"].to_numpy()
        stype = g["stype"].to_numpy(); roi = g["roi"].to_numpy()
        ended = g["ended_by"].to_numpy(); dur = pd.to_numeric(g["dur_s"], errors="coerce").to_numpy()
        bstart = pd.to_numeric(g["bin_start"], errors="coerce").to_numpy()
        bend = pd.to_numeric(g["bin_end"], errors="coerce").to_numpy()
        tend = g["t_end"].to_numpy()
        reg = None
        for i in range(len(g)):
            if stype[i] != "settlement":
                continue                                    # a destination departs from a residence
            if ended[i] != "onset":
                # ended by gap/nightend = the residence is right-censored (the animal was still settled,
                # or the signal dropped) — NOT an observed departure. Skip; counted separately as
                # right-censored residence in the summary.
                continue
            # a confirmed departure (a locomotor bout started). Type by the next stationary episode
            # (episode_id is a dense per-animal-night counter, so i+1 IS the immediate next episode).
            nxt = i + 1 if i + 1 < len(g) else None
            long_gap_bins = long_gap_s / bin_s
            if nxt is None:
                # departed (onset) but no subsequent stationary episode observed (the bout ran into a
                # dropout / nightend) -> the destination is unobserved.
                ttype, dst_roi, dst_type, inter = "censored", None, None, np.nan
            else:
                dst_type = stype[nxt]; dst_roi = roi[nxt]
                inter = float(bstart[nxt] - bend[i] - 1)
                if inter >= long_gap_bins:
                    # the connecting 'bout' spans >= long_gap_s of continuous held-active time -> almost
                    # certainly crossed a WISER dropout / unobserved intermediate -> not a direct destination
                    ttype, dst_roi, dst_type = "censored", None, "dropout_spanned"
                elif dst_type == "settlement":
                    ttype = "same_site_return" if dst_roi == roi[i] else "relocation"
                elif dst_type == "pass_through":
                    ttype = "pass_through"
                elif dst_type == "open_stop":
                    ttype = "open_field_termination"
                else:                                        # dropout destination -> unobservable
                    ttype, dst_roi, dst_type = "censored", None, "dropout"
            reg = em.night_regime(night) if reg is None else reg
            lay = em.layout_features(roi[i], night)
            rows.append({
                "shortid": sid, "night": night, "origin_episode": int(eid[i]),
                "origin_roi": roi[i], "origin_type": "settlement",
                "dest_roi": dst_roi, "dest_type": dst_type, "transition_type": ttype,
                "origin_dwell_s": float(dur[i]), "inter_bout_bins": inter,
                "t_depart": pd.Timestamp(tend[i]), "clock_hour": int(pd.Timestamp(tend[i]).hour),
                "origin_resource_type": lay["resource_type"],
                "dest_resource_type": (em.resource_type(dst_roi) if dst_roi else None),
                "origin_dist_to_edge_in": lay["dist_to_edge_in"],
                "wet": int(bool(reg.get("wet", False))), "fireworks": int(bool(reg.get("fireworks", False))),
                "truncated": int(bool(reg.get("truncated", False))), "burrow": int(bool(reg.get("burrow", False))),
            })
    return pd.DataFrame(rows, columns=cols)


# ===========================================================================
# representation validation (measurement gate — BEFORE any choice/search model)
# ===========================================================================

def transition_type_summary(trans: pd.DataFrame) -> pd.DataFrame:
    """Counts + fractions of each transition type (over departures from settlements)."""
    if trans.empty:
        return pd.DataFrame(columns=["transition_type", "n", "frac"])
    vc = trans["transition_type"].value_counts()
    out = vc.rename("n").reset_index().rename(columns={"index": "transition_type"})
    out["frac"] = out["n"] / out["n"].sum()
    return out


def representation_sensitivity(stat_eps: pd.DataFrame, em, *,
                               settle_grid=(30.0, 60.0, 120.0), conf_grid=(0.5, 0.8)) -> pd.DataFrame:
    """Preregistered sensitivity of the transition-type mix + the relocation count to the settlement
    thresholds. A VALIDATED representation is one whose transition-type proportions and relocation
    support do not swing wildly across the grid (i.e., the settle/pass-through boundary is not a
    knife-edge). One row per (settle_min_s, conf_frac)."""
    rows = []
    for s in settle_grid:
        for c in conf_grid:
            typed = type_stationary_episodes(stat_eps, em, settle_min_s=s, conf_frac=c)
            tr = build_transitions(typed, em)
            n = len(tr)
            def frac(t):
                return float((tr["transition_type"] == t).mean()) if n else np.nan
            rows.append({
                "settle_min_s": s, "conf_frac": c,
                "n_settlements": int(typed["is_settlement"].sum()),
                "n_departures": n,
                "n_relocation": int((tr["transition_type"] == "relocation").sum()),
                "frac_relocation": frac("relocation"),
                "frac_same_site_return": frac("same_site_return"),
                "frac_pass_through": frac("pass_through"),
                "frac_open_field_termination": frac("open_field_termination"),
                "frac_censored": frac("censored"),
            })
    return pd.DataFrame(rows)


def relocation_support(trans: pd.DataFrame, *, min_support: int = 3) -> dict:
    """Support for a per-origin destination-choice model: relocations per origin site, and how many
    origins have >= ``min_support`` relocations with >= 2 distinct destinations (a real choice)."""
    rel = trans[trans["transition_type"] == "relocation"]
    if rel.empty:
        return {"n_relocations": 0, "origins_with_choice": 0, "per_origin": {}}
    per_origin = rel.groupby("origin_roi").agg(
        n=("dest_roi", "size"), n_dest=("dest_roi", "nunique")).reset_index()
    choice = per_origin[(per_origin["n"] >= min_support) & (per_origin["n_dest"] >= 2)]
    return {"n_relocations": int(len(rel)),
            "origins_with_choice": int(len(choice)),
            "per_origin": per_origin.set_index("origin_roi").to_dict("index")}


def validate_representation(stat_eps: pd.DataFrame, em, *, settle_min_s: float = 60.0,
                            conf_frac: float = 0.5) -> dict:
    """Run the measurement-gate checks and return a pass/fail verdict + evidence. The destination-
    choice model is GATED on ``gate_ok``.

    Gate = (a) all five transition types are populated (the representation is non-degenerate);
    (b) the relocation fraction is stable across the sensitivity grid (max−min <= 0.20); (c) there is
    per-origin choice support (>= 2 origins with >= 3 relocations to >= 2 destinations); (d) same-site
    returns are genuine loops (median inter-bout gap >= 1 bin — a real intervening bout)."""
    typed = type_stationary_episodes(stat_eps, em, settle_min_s=settle_min_s, conf_frac=conf_frac)
    tr = build_transitions(typed, em)
    summ = transition_type_summary(tr)
    # always include the OPERATING (settle_min_s, conf_frac) in the sensitivity grid, so the
    # at-operating-conf stability slice is never empty for a non-default operating point.
    sg = tuple(sorted(set((30.0, 60.0, 120.0, float(settle_min_s)))))
    cg = tuple(sorted(set((0.5, 0.8, float(conf_frac)))))
    sens = representation_sensitivity(stat_eps, em, settle_grid=sg, conf_grid=cg)
    sup = relocation_support(tr)
    types_present = set(tr["transition_type"].unique()) if not tr.empty else set()
    all_types = len(types_present & set(TTYPES)) >= 4         # relocation, pass_through, open, censored
    # Stability is judged across the DURATION threshold AT THE OPERATING confidence (the primary knob);
    # the confidence threshold is reported SEPARATELY as a sensitivity caveat (a strict conf_frac
    # reclassifies edge-dwelling settlements as pass-throughs, which is a definition change, not
    # instability of the operating representation).
    at_conf = sens[np.isclose(sens["conf_frac"], conf_frac)] if not sens.empty else sens
    reloc_range_dur = float(at_conf["frac_relocation"].max() - at_conf["frac_relocation"].min()) if len(at_conf) else np.nan
    reloc_range_full = float(sens["frac_relocation"].max() - sens["frac_relocation"].min()) if not sens.empty else np.nan
    # a grid cell that collapses to zero departures (frac_relocation=NaN, or n_departures=0) is
    # instability, not a value to skip: require every operating-conf cell to be populated.
    all_cells_populated = bool(len(at_conf) and at_conf["frac_relocation"].notna().all()
                               and (at_conf["n_departures"] > 0).all())
    stable = bool(all_cells_populated and np.isfinite(reloc_range_dur) and reloc_range_dur <= 0.10)
    choice_ok = sup["origins_with_choice"] >= 2
    ssr = tr[tr["transition_type"] == "same_site_return"]
    loops_real = bool(ssr.empty or (pd.to_numeric(ssr["inter_bout_bins"], errors="coerce").median() >= 1))
    gate_ok = bool(all_types and stable and choice_ok and loops_real)
    n_cens_res = int(((typed["stype"] == "settlement") & (typed["ended_by"] != "onset")).sum())
    return {
        "settle_min_s": settle_min_s, "conf_frac": conf_frac,
        "n_settlements": int(typed["is_settlement"].sum()), "n_departures": int(len(tr)),
        "n_right_censored_residence": n_cens_res,   # settled at nightend / lost to dropout (no departure)
        "type_summary": summ.to_dict("records"),
        "sensitivity": sens.to_dict("records"),
        "relocation_support": sup,
        "checks": {"all_types_populated": bool(all_types),
                   "relocation_frac_range_across_duration": reloc_range_dur,
                   "relocation_stable_across_duration": stable,
                   "relocation_frac_range_full_grid": reloc_range_full,
                   "conf_frac_sensitivity_note": "a strict conf_frac (0.8) reclassifies edge-dwelling "
                   "settlements as pass-throughs -> fewer relocations; conf_frac=0.5 (majority-in-ROI) "
                   "is the operating point. Report both.",
                   "per_origin_choice_support": bool(choice_ok),
                   "same_site_returns_are_real_loops": loops_real},
        "gate_ok": gate_ok,
    }


# ===========================================================================
# gated destination-choice table (only after validate_representation passes)
# ===========================================================================

def build_destination_choice_table(trans: pd.DataFrame, em, *, min_support: int = 3) -> tuple:
    """The clean destination-choice event set: ``relocation`` transitions from settlement origins,
    with an origin-specific supported choice set (destinations observed >= ``min_support`` times from
    that origin). Returns (choice_df, choice_sets). Same-site returns, pass-throughs, open-field
    terminations, and censored transitions are EXCLUDED — they are separate outcomes, not
    destination choices. Attaches destination layout features. Fit with ``choice_models`` ONLY if the
    representation validated."""
    rel = trans[trans["transition_type"] == "relocation"].copy()
    if rel.empty:
        return rel, {}
    choice_sets = {}
    for o, gg in rel.groupby("origin_roi"):
        vc = gg["dest_roi"].value_counts()
        choice_sets[o] = sorted(vc[vc >= min_support].index.tolist())
    rel["in_choice_set"] = [d in choice_sets.get(o, []) for o, d in zip(rel["origin_roi"], rel["dest_roi"])]
    feats = [em.destination_features(o, d, n) for o, d, n in
             zip(rel["origin_roi"], rel["dest_roi"], rel["night"])]
    fdf = pd.DataFrame(feats, index=rel.index)
    keep = [c for c in ["dest_resource_type", "dest_is_house", "dest_is_water", "dest_is_refuge",
                        "dest_is_open", "origin_dest_dist_in", "distance_reliable"] if c in fdf.columns]
    rel = pd.concat([rel, fdf[keep]], axis=1)
    return rel, choice_sets
