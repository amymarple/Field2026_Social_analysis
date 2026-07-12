r"""
rest_circadian.py — a rest-state / circadian layer over the module-3 locomotor state stream, used to
SEPARATE rest-need (circadian / nap) drivers from SOCIAL drivers in the movement-decision models
(the leaving hazard, the entering/settlement process, and the approach/avoid spacing).

From ``locomotor_state_stream.csv`` (per-bin: shortid, night, t_start, roi_state, active, state) it
derives:
  * :func:`circadian_rest_profile` — population stationary(rest)-fraction by LOCAL clock-hour = the
    diel rhythm (how much of the group is resting at each hour);
  * :func:`rest_propensity_map` — {local_hour -> population rest-fraction} = a **rest-need** proxy that
    is animal-INDEPENDENT (it is the group rhythm at that hour, NOT the focal's own state), so it can
    be a covariate in the focal's own decision model WITHOUT leaking the outcome;
  * :func:`attach_rest_context` — join to any decision table: the circadian ``rest_propensity`` +
    ``local_hour``, and the focal's OWN state at the decision (``focal_in_rest``) + its recent
    stationary fraction in a strictly-pre-decision window (``focal_rest_frac_pre``).

Local hour = UTC − 4 (EDT). "stationary"/rest = state ∈ {rest, pause} (low-speed); "active" =
{local_active, transit}. Rest is a low-speed PROXY, not sleep. numpy + pandas only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TZ_OFFSET_HOURS = -4
STATIONARY_STATES = ("rest", "pause")
NS = 1_000_000_000


def _local_hour(ts) -> pd.Series:
    return (pd.to_datetime(ts).dt.hour + TZ_OFFSET_HOURS) % 24


def circadian_rest_profile(stream: pd.DataFrame) -> pd.DataFrame:
    """Per LOCAL clock-hour: fraction of informative (non-'unknown') bins that are stationary
    (rest ∪ pause), pooled and per animal. The diel rest rhythm (a low-speed proxy)."""
    s = stream[stream["state"] != "unknown"].copy()
    if s.empty:
        return pd.DataFrame(columns=["local_hour", "rest_frac", "n_bins"])
    s["local_hour"] = _local_hour(s["t_start"])
    s["stationary"] = s["state"].isin(STATIONARY_STATES).astype(float)
    prof = (s.groupby("local_hour")["stationary"].agg(rest_frac="mean", n_bins="size").reset_index())
    return prof


def rest_propensity_map(stream: pd.DataFrame) -> dict:
    """{local_hour -> population stationary(rest)-fraction} — the rest-need covariate (animal-agnostic)."""
    prof = circadian_rest_profile(stream)
    return dict(zip(prof["local_hour"].astype(int), prof["rest_frac"].astype(float)))


def attach_rest_context(table: pd.DataFrame, stream: pd.DataFrame, *, time_col: str,
                        prewindow_s: float = 120.0, bin_s: float = 5.0) -> pd.DataFrame:
    """Attach a rest-need / circadian context to a decision table:

    * ``rest_propensity`` — the POPULATION stationary-fraction at the decision's local clock-hour
      (from :func:`rest_propensity_map`); animal-independent, so it is a clean circadian "rest-need"
      covariate that cannot leak the focal's own outcome. ``local_hour`` also added.
    * ``focal_in_rest`` (0/1) — the focal animal's own unified state at the decision bin is stationary
      (rest ∪ pause). This is a CONDITIONING state (the animal's state *at* the decision), valid as a
      covariate ("given it is resting, ...").
    * ``focal_rest_frac_pre`` — fraction of the focal's bins that are stationary in
      ``[t − prewindow_s, t)`` (STRICTLY pre-decision; missing→NaN, never imputed).

    Vectorised per (shortid, night) via searchsorted over the stream's bin start times."""
    out = table.reset_index(drop=True).copy()
    if out.empty:
        for c in ["rest_propensity", "local_hour", "focal_in_rest", "focal_rest_frac_pre"]:
            out[c] = np.nan
        return out
    prop = rest_propensity_map(stream)
    lh = _local_hour(out[time_col]).astype(int)
    out["local_hour"] = lh
    out["rest_propensity"] = lh.map(prop)
    # per (shortid, night) stream arrays for the focal-state joins
    s = stream.copy()
    s["_ns"] = pd.to_datetime(s["t_start"]).astype("datetime64[ns]").astype("int64")
    s["_stat"] = s["state"].isin(STATIONARY_STATES).astype(float)
    s["_known"] = (s["state"] != "unknown").astype(float)
    grp = {}
    for (sid, night), g in s.sort_values("_ns").groupby(["shortid", "night"], sort=False):
        grp[(str(sid), str(night))] = (g["_ns"].to_numpy("int64"), g["_stat"].to_numpy(float),
                                       g["_known"].to_numpy(float))
    t_ns = pd.to_datetime(out[time_col]).astype("datetime64[ns]").astype("int64").to_numpy()
    sid_a = out["shortid"].astype(str).to_numpy(); night_a = out["night"].astype(str).to_numpy()
    pre = int(round(prewindow_s * NS))
    in_rest = np.full(len(out), np.nan); frac_pre = np.full(len(out), np.nan)
    for i in range(len(out)):
        g = grp.get((sid_a[i], night_a[i]))
        if g is None:
            continue
        ns_, stat_, known_ = g
        # current bin (the bin whose start is the last <= t): the focal's state AT the decision
        j = int(np.searchsorted(ns_, t_ns[i], "right")) - 1
        if 0 <= j < len(ns_) and known_[j] > 0:
            in_rest[i] = stat_[j]
        # strictly pre-decision window [t-pre, t)
        lo = int(np.searchsorted(ns_, t_ns[i] - pre, "left"))
        hi = int(np.searchsorted(ns_, t_ns[i], "left"))
        if hi > lo and known_[lo:hi].sum() > 0:
            frac_pre[i] = float(stat_[lo:hi][known_[lo:hi] > 0].mean())
    out["focal_in_rest"] = in_rest
    out["focal_rest_frac_pre"] = frac_pre
    return out
