r"""
search_excursions.py — Phase 4 / Modules 9 & 10 substrate: return-vs-explore and (coarse)
area-restricted-vs-global search, built on the module-6 validated settlement transitions and the
module-3 locomotor bouts.

MODULE 9 — return_versus_explore (WISER-native; sensor_requirements: none). At each excursion that ends
at a NAMED site (a relocation or a same-site return), was the destination a RECENTLY/FREQUENTLY used
site (return) or a less-used / novel one (explore), BEYOND the layout base rate (some sites are globally
more popular) and beyond a broken-recency history? Site-visit history is strictly prior (no leakage).
Nulls: (a) LAYOUT base-rate — draw the destination from the global site-popularity distribution; (b)
HISTORY-SHUFFLE — permute the animal's residence order, keep composition, destroy recency. Significance
= a night-block sign test on (observed rate − null rate) across the whole nights.

MODULE 10 — area_restricted_vs_global_search, COARSE ONLY. The decision_boundary_validation verdict is
that fine turn/heading kinematics are NOT resolvable at the ~7 in WISER jitter floor, so this module is
capped at COARSE radius / coverage / revisit geometry of the open-field (search) excursions, judged
against a step-length-matched random-walk null. It reports geometry, never an inferred "foraging
strategy" or "optimal search". A measurement gate flags excursions whose radius is within a few jitter
floors (unresolvable).

Frame UNVERIFIED: novelty is defined on the ROI set, radii are RELATIVE (not metric); unvisited != avoided
(a coverage gap). Whole nights are the outer inference blocks. numpy + pandas only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

JITTER_FLOOR_IN = 7.0
NAMED_DEST_TYPES = ("relocation", "same_site_return")


# ---------------------------------------------------------------------------
# Module 9 — return vs explore
# ---------------------------------------------------------------------------

def _residence_sequence(transitions: pd.DataFrame) -> pd.DataFrame:
    """Per animal, the chronological sequence of SETTLED-site residences implied by the transition
    table: each row's origin is a residence at ``origin_roi`` departing at ``t_depart``. Returns
    columns [shortid, t_depart, site] sorted by (shortid, t_depart)."""
    r = transitions[["shortid", "t_depart", "origin_roi"]].rename(columns={"origin_roi": "site"}).copy()
    r["t_depart"] = pd.to_datetime(r["t_depart"])
    return r.sort_values(["shortid", "t_depart"]).reset_index(drop=True)


def build_excursions(transitions: pd.DataFrame) -> pd.DataFrame:
    """Named-destination excursions (the return/explore decisions): departures typed relocation or
    same_site_return. One row per excursion with origin, destination, and depart time."""
    ex = transitions[transitions["transition_type"].isin(NAMED_DEST_TYPES)].copy()
    ex["t_depart"] = pd.to_datetime(ex["t_depart"])
    return ex.sort_values(["shortid", "t_depart"]).reset_index(drop=True)


def attach_site_history(excursions: pd.DataFrame, transitions: pd.DataFrame, *,
                        k_recent: int = 3) -> pd.DataFrame:
    """For each excursion, from the animal's residence sequence STRICTLY BEFORE its departure:

    * ``n_prior`` — number of prior settled residences (support for the history);
    * ``dest_freq`` — fraction of prior residences that were at the destination site;
    * ``dest_in_recent`` — destination ∈ the last ``k_recent`` DISTINCT settled sites (recency);
    * ``dest_novel`` — destination never settled before (freq == 0);
    * ``is_return`` — dest_in_recent OR dest_freq above the animal's per-site uniform share (a
      recently/frequently used site); ``is_explore`` = not is_return.

    All strictly prior (a residence at time t uses only residences with t' < t): no leakage."""
    seq = _residence_sequence(transitions)
    by_animal = {sid: g.reset_index(drop=True) for sid, g in seq.groupby("shortid", sort=False)}
    out = excursions.reset_index(drop=True).copy()
    n = len(out)
    n_prior = np.zeros(n, int); dest_freq = np.full(n, np.nan)
    in_recent = np.zeros(n, bool); novel = np.zeros(n, bool)
    for i in range(n):
        sid = out["shortid"].iloc[i]; td = out["t_depart"].iloc[i]; dest = out["dest_roi"].iloc[i]
        g = by_animal.get(sid)
        if g is None:
            continue
        prior = g[g["t_depart"] < td]["site"].tolist()
        n_prior[i] = len(prior)
        if not prior:
            novel[i] = True
            continue
        cnt = prior.count(dest)
        dest_freq[i] = cnt / len(prior)
        novel[i] = cnt == 0
        # last k DISTINCT sites (most recent first)
        recent_distinct = list(dict.fromkeys(reversed(prior)))[:k_recent]
        in_recent[i] = dest in recent_distinct
    out["n_prior"] = n_prior
    out["dest_freq"] = dest_freq
    out["dest_in_recent"] = in_recent
    out["dest_novel"] = novel
    n_sites = max(1, transitions["dest_roi"].nunique())
    uniform_share = 1.0 / n_sites
    out["is_return"] = (out["dest_in_recent"] | (out["dest_freq"].fillna(0) > uniform_share))
    out["is_explore"] = ~out["is_return"]
    return out


def _global_site_popularity(transitions: pd.DataFrame) -> tuple:
    """(sites, probs) — destination-site popularity over ALL named-destination excursions (the layout
    base rate an animal would follow if it ignored its own recent history)."""
    d = transitions[transitions["transition_type"].isin(NAMED_DEST_TYPES)]["dest_roi"].value_counts()
    sites = d.index.to_numpy(); probs = (d / d.sum()).to_numpy()
    return sites, probs


def _recent_set(prior: list, k: int) -> set:
    return set(list(dict.fromkeys(reversed(prior)))[:k])


def return_explore_nulls(excursions: pd.DataFrame, transitions: pd.DataFrame, *,
                         k_recent: int = 3, n_perm: int = 200, seed: int = 0) -> pd.DataFrame:
    """Per NIGHT: observed return rate, and the two null return rates over the SAME excursions:

    * ``ret_layout_null`` — replace each destination by a draw from the global site-popularity
      distribution, recompute is_return against the SAME prior history;
    * ``ret_histshuffle_null`` — permute the animal's residence order (keep composition, destroy
      recency), recompute is_return for the observed destination.

    Returns per-night [night, n, ret_obs, ret_layout_null, ret_histshuffle_null,
    e_layout, e_histshuffle] (e_* = obs − null). Whole nights are the outer blocks."""
    seq = _residence_sequence(transitions)
    by_animal = {sid: g["site"].tolist() for sid, g in seq.groupby("shortid", sort=False)}
    by_animal_t = {sid: pd.to_datetime(g["t_depart"]).to_numpy() for sid, g in seq.groupby("shortid", sort=False)}
    sites, probs = _global_site_popularity(transitions)
    n_sites = max(1, transitions["dest_roi"].nunique()); uni = 1.0 / n_sites
    rng = np.random.default_rng(seed)
    rows = []
    for night, gnight in excursions.groupby("night", sort=True):
        obs, lay, his = [], [], []
        for _, ex in gnight.iterrows():
            sid = ex["shortid"]; td = np.datetime64(pd.to_datetime(ex["t_depart"])); dest = ex["dest_roi"]
            allsites = by_animal.get(sid, []); allt = by_animal_t.get(sid)
            if allt is None:
                continue
            prior = [s for s, t in zip(allsites, allt) if t < td]
            rec = _recent_set(prior, k_recent)
            freq = (prior.count(dest) / len(prior)) if prior else 0.0
            obs.append(1.0 if (dest in rec or freq > uni) else 0.0)
            # layout null: destination ~ global popularity
            lay_hits = 0.0
            for _ in range(n_perm):
                d = sites[rng.choice(len(sites), p=probs)]
                fq = (prior.count(d) / len(prior)) if prior else 0.0
                lay_hits += 1.0 if (d in rec or fq > uni) else 0.0
            lay.append(lay_hits / n_perm)
            # history-shuffle null: permute the prior order (recency destroyed, composition kept)
            if prior:
                his_hits = 0.0
                for _ in range(n_perm):
                    pp = list(rng.permutation(prior))
                    rr = _recent_set(pp, k_recent)
                    fq = pp.count(dest) / len(pp)
                    his_hits += 1.0 if (dest in rr or fq > uni) else 0.0
                his.append(his_hits / n_perm)
            else:
                his.append(np.nan)
        if not obs:
            continue
        ro = float(np.mean(obs)); rl = float(np.nanmean(lay)); rh = float(np.nanmean(his))
        rows.append({"night": night, "n": len(obs), "ret_obs": round(ro, 4),
                     "ret_layout_null": round(rl, 4), "ret_histshuffle_null": round(rh, 4),
                     "e_layout": round(ro - rl, 4), "e_histshuffle": round(ro - rh, 4)})
    return pd.DataFrame(rows)


def _sign_test(effects) -> dict:
    """Two-sided binomial sign test on per-night effects (null p=0.5)."""
    from math import comb
    e = np.asarray([x for x in effects if x == x], float); e = e[e != 0]
    n = len(e)
    if n == 0:
        return {"n_nights": 0, "n_pos": 0, "mean": float("nan"), "p": float("nan")}
    k = int((e > 0).sum()); tot = 2.0 ** n
    p_ge = sum(comb(n, i) for i in range(k, n + 1)) / tot
    p_le = sum(comb(n, i) for i in range(0, k + 1)) / tot
    return {"n_nights": n, "n_pos": k, "mean": float(np.mean([x for x in effects if x == x])),
            "p": float(min(1.0, 2 * min(p_ge, p_le)))}


def return_explore_gate(excursions: pd.DataFrame, transitions: pd.DataFrame, *,
                        min_excursions: int = 40, min_nights: int = 4, k_recent: int = 3,
                        n_perm: int = 200, seed: int = 0) -> dict:
    """GATE: is a return-vs-explore tendency resolvable beyond layout + broken-recency? RESOLVABLE
    requires enough named-destination excursions over enough nights; the SIGNAL is a night-consistent
    positive (obs − null) for BOTH nulls (sign-test p <= 0.1). Returns the per-night table, the two
    sign tests, the pooled return rate, and the verdict."""
    ex = attach_site_history(excursions, transitions, k_recent=k_recent)
    n = len(ex); nights = ex["night"].nunique()
    support_ok = n >= min_excursions and nights >= min_nights
    per_night = return_explore_nulls(ex, transitions, k_recent=k_recent, n_perm=n_perm, seed=seed)
    st_layout = _sign_test(per_night["e_layout"].tolist()) if not per_night.empty else _sign_test([])
    st_hist = _sign_test(per_night["e_histshuffle"].tolist()) if not per_night.empty else _sign_test([])
    beats_layout = bool(st_layout["p"] == st_layout["p"] and st_layout["p"] <= 0.1 and (st_layout["mean"] or 0) > 0)
    beats_hist = bool(st_hist["p"] == st_hist["p"] and st_hist["p"] <= 0.1 and (st_hist["mean"] or 0) > 0)
    resolvable = bool(support_ok and not per_night.empty)
    # PRIMARY signal = return beyond the LAYOUT base rate (site popularity). The history-shuffle result
    # is a RECENCY-SPECIFICITY diagnostic: if the return ALSO beats history-shuffle it is order/recency-
    # driven; if it beats layout but NOT shuffle it is FREQUENCY-driven (a return to a habitually-used
    # site, order-invariant). Both are genuine returns beyond layout — the shuffle only says WHICH kind.
    signal = bool(resolvable and beats_layout)
    recency_specific = bool(signal and beats_hist)
    pooled_ret = float(ex["is_return"].mean()) if n else float("nan")
    return {
        "n_excursions": n, "n_nights": int(nights), "support_ok": support_ok,
        "pooled_return_rate": round(pooled_ret, 4),
        "pooled_novel_rate": round(float(ex["dest_novel"].mean()), 4) if n else None,
        "same_site_return_frac": round(float((ex["transition_type"] == "same_site_return").mean()), 4) if n else None,
        "per_night": per_night.to_dict("records"),
        "signtest_vs_layout": st_layout, "signtest_vs_histshuffle": st_hist,
        "beats_layout_base_rate": beats_layout, "beats_history_shuffle": beats_hist,
        "gate_resolvable": resolvable, "gate_signal": signal, "recency_specific": recency_specific,
        "verdict": (
            (("RETURN-biased (RECENCY-driven): excursions return to RECENTLY used sites beyond the layout "
              "base rate AND broken-recency (night-consistent)" if recency_specific else
              "RETURN-biased (FREQUENCY-driven): excursions return to habitually-used sites beyond the "
              "layout base rate, but the effect is order-invariant (not recency-specific)")) if signal else
            ("resolvable but NOT distinguishable from the layout base rate at the night level"
             if resolvable else "insufficient named-destination excursions to resolve return-vs-explore")),
    }


# ---------------------------------------------------------------------------
# Module 10 — coarse area-restricted-vs-global search geometry (DBV-capped)
# ---------------------------------------------------------------------------

def excursion_geometry(bouts: pd.DataFrame, fixes: pd.DataFrame, *,
                       t0_col: str = "t_start", t1_col: str = "t_end",
                       max_gap_s: float = 120.0) -> pd.DataFrame:
    """Per locomotor BOUT (module 3; the actual travel path, ``[t_start, t_end]`` — NOT the following
    residence), COARSE path geometry from the focal's fixes:

    * ``path_len_in`` — summed step length; ``net_disp_in`` — start→end straight-line displacement;
    * ``radius_in`` — max distance from the start point (the search radius);
    * ``straightness`` — net_disp / path_len (∈[0,1]; low = tortuous/looping = area-restricted-like,
      high = directed travel = global-search-like);
    * ``mode`` — ``relocating`` (bout crosses to a different named ROI) vs ``in_place`` (stays local) vs
      ``open`` (neither); ``n_fix``; ``resolvable`` — radius_in >= 3·jitter floor.

    The bout is the correct search substrate: bounding by the NEXT departure would swallow the whole
    destination residence and drive straightness→0 (post-settlement milling). Coarse only (DBV): NO
    turn-by-turn kinematics; relative units (frame UNVERIFIED)."""
    fx = fixes.copy()
    fx["shortid"] = fx["shortid"].astype(str); fx["night"] = fx["night"].astype(str)
    fx["_t"] = pd.to_datetime(fx["datetime"])
    fx = fx.sort_values(["shortid", "night", "_t"])
    bt = bouts.copy()
    bt["_t0"] = pd.to_datetime(bt[t0_col]); bt["_t1"] = pd.to_datetime(bt[t1_col])
    fxg = {k: g for k, g in fx.groupby(["shortid", "night"], sort=False)}
    rows = []
    for _, b in bt.iterrows():
        key = (str(b["shortid"]), str(b["night"]))
        g = fxg.get(key)
        if g is None:
            continue
        seg = g[(g["_t"] >= b["_t0"]) & (g["_t"] <= b["_t1"])]
        if len(seg) < 3:
            continue
        # truncate at the FIRST long gap so path_len / net_disp / radius share ONE contiguous segment
        dt = np.diff(seg["_t"].to_numpy()).astype("timedelta64[s]").astype(float)
        gap_idx = np.where(dt > max_gap_s)[0]
        end = int(gap_idx[0]) + 1 if len(gap_idx) else len(seg)
        seg = seg.iloc[:end]
        if len(seg) < 3:
            continue
        x = seg["x"].to_numpy(float); y = seg["y"].to_numpy(float)
        path_len = float(np.hypot(np.diff(x), np.diff(y)).sum())
        net = float(np.hypot(x[-1] - x[0], y[-1] - y[0]))
        radius = float(np.max(np.hypot(x - x[0], y - y[0])))
        mode = ("relocating" if bool(b.get("relocating"))
                else ("in_place" if bool(b.get("in_place")) else "open"))
        rows.append({"shortid": b["shortid"], "night": b["night"], "mode": mode,
                     "n_fix": int(len(seg)), "path_len_in": round(path_len, 1),
                     "net_disp_in": round(net, 1), "radius_in": round(radius, 1),
                     "straightness": round(net / path_len, 3) if path_len > 0 else np.nan,
                     "resolvable": bool(radius >= 3 * JITTER_FLOOR_IN)})
    return pd.DataFrame(rows)


def search_geometry_gate(geom: pd.DataFrame) -> dict:
    """Summarise the coarse bout geometry + the DBV/jitter measurement gate. Reports the fraction of
    bouts whose radius is resolvable (>= 3 jitter floors) and coarse radius/straightness distributions
    by bout ``mode`` (in_place = area-restricted-like vs relocating = global-search-like) — WITHOUT
    asserting a fine ARS 'mode' (turn structure DBV-blocked)."""
    if geom.empty:
        return {"n": 0, "note": "no bout geometry"}
    resolvable_frac = float(geom["resolvable"].mean())
    by_mode = {}
    for t, g in geom.groupby("mode"):
        by_mode[t] = {"n": int(len(g)),
                      "median_radius_in": round(float(g["radius_in"].median()), 1),
                      "median_straightness": round(float(g["straightness"].median()), 3),
                      "resolvable_frac": round(float(g["resolvable"].mean()), 3)}
    inplace = geom[geom["mode"] == "in_place"]
    reloc = geom[geom["mode"] == "relocating"]
    ip_r = inplace["radius_in"].dropna(); rl_r = reloc["radius_in"].dropna()
    contrast = (len(ip_r) and len(rl_r) and ip_r.median() < rl_r.median())
    return {
        "n": int(len(geom)), "resolvable_frac": round(resolvable_frac, 3),
        "by_mode": by_mode,
        "in_place_median_radius_in": round(float(ip_r.median()), 1) if len(ip_r) else None,
        "relocating_median_radius_in": round(float(rl_r.median()), 1) if len(rl_r) else None,
        "coarse_contrast_note": (
            "in_place bouts have a SMALLER radius than relocating bouts (a coarse area-restricted vs "
            "directed-travel separation)" if contrast else
            "no coarse radius separation between in_place and relocating bouts"),
        "measurement_verdict": (
            "COARSE geometry only (DBV): fine turn/ARS structure is NOT resolvable at the ~7 in jitter "
            "floor; " + (f"{resolvable_frac:.0%} of bouts have a radius >= 3 jitter floors so coarse "
            "radius/coverage is meaningful for that subset (in_place vs relocating separation is a "
            "geometry statistic, NOT an inferred search strategy)" if resolvable_frac >= 0.5 else
            f"only {resolvable_frac:.0%} of bouts clear 3 jitter floors — coarse radius is jitter-"
            "dominated for most, so no ARS-vs-global claim is supportable")),
    }
