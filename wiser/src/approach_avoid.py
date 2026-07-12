r"""
approach_avoid.py — Phase 3 / Module 7: in-bout approach/avoid, COARSE and HEADING-FREE.

`decision_boundary_validation` falsified any reliable HEADING/bearing at WISER resolution, so a
per-step "relative bearing toward/away" is NOT measurable. The module-7 spec itself allows only
"coarse approach/avoid at >= 1 m". This module therefore measures approach/avoid as a **net
distance change over a validated active bout**, NOT an instantaneous heading:

For each validated active bout of a focal animal (module-3 ``bouts.csv``) and each conspecific
present at >= 1 m at bout start:
  * ``disp``    = |focal_end - focal_start|                      (bout displacement magnitude)
  * ``d0``      = |focal_start - partner_start|                  (initial focal-partner distance)
  * ``approach``= d0 - |focal_end - partner_start|              (distance the focal CLOSED on the
                                                                 partner's start position; >0 toward)
  * ``toward``  = approach / disp  in [-1, 1]                    (~cos of the angle between the bout
                                                                 and the direction to the partner)

Only bouts with ``disp`` above a jitter-safe floor and partners at ``d0`` >= 1 m enter (both sides
above the ~7 in floor -> frame-invariant and resolvable). The partner position is taken STRICTLY at/
before bout start (pre-decision). This is the FOCAL's contribution to proximity (partner held at its
start position); it does not require the partner's heading or fine steering.

MEASUREMENT GATE (run BEFORE any model): (a) support; (b) a **direction-randomized, displacement-
matched null** — rotate each bout's displacement vector by a random angle about its start and
recompute ``toward``; a real toward/away bias makes the observed mean exceed this geometry null;
(c) a **day-shuffle** control — replace each partner's start position with the SAME partner's
position at the same clock-hour on a DIFFERENT night; if the observed toward-ness does not exceed
this, the "approach" is shared-resource LAYOUT geometry, not real-time social steering (a NO-GO for
SOCIAL approach, exactly the module-5/6 day-shuffle logic and the DBV falsification structure).

numpy + pandas only (imports in ``cv``). Frame-invariant outputs (distances/toward); absolute inch
coords are used only internally for the direction null.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RADIUS_1M_IN = 39.37          # 1 m in inches — jitter-floor-safe social radius
JITTER_FLOOR_IN = 7.0
NS = 1_000_000_000


# ---------------------------------------------------------------------------
# per-(bout, partner) approach context
# ---------------------------------------------------------------------------

def _pos_at(t_ns, arr_ns, arr_x, arr_y, *, win_ns, side):
    """Jitter-robust position near time ``t_ns``: median x,y of fixes within +/- ``win_ns``.
    ``side='before'`` restricts to fixes <= t_ns (strictly pre-decision for the partner)."""
    lo = int(np.searchsorted(arr_ns, t_ns - win_ns, "left"))
    if side == "before":
        hi = int(np.searchsorted(arr_ns, t_ns, "right"))
    else:
        hi = int(np.searchsorted(arr_ns, t_ns + win_ns, "right"))
    if hi <= lo:
        return np.nan, np.nan
    return float(np.median(arr_x[lo:hi])), float(np.median(arr_y[lo:hi]))


def bout_approach_context(bouts: pd.DataFrame, fixes: pd.DataFrame, em, *,
                          min_disp_in: float = 14.0, min_partner_dist_in: float = RADIUS_1M_IN,
                          endpoint_win_s: float = 1.0, partner_win_s: float = 2.0,
                          exclude_spans_dropout: bool = True) -> pd.DataFrame:
    """One row per (validated bout, conspecific present at >= 1 m at start). Heading-free.

    Bouts with ``disp < min_disp_in`` (jitter-scale, not a real displacement) or a partner closer than
    ``min_partner_dist_in`` (sub-1 m pseudo-proximity) are dropped. Bouts flagged ``spans_dropout`` /
    ``has_gap`` are dropped (their endpoints straddle unobserved time). Returns columns incl.
    ``disp``, ``d0``, ``approach``, ``toward``, ``n_partners``, plus internal ``_fx0,_fy0,_fx1,_fy1,
    _px,_py`` (inch coords) for the direction null."""
    cols = ["shortid", "night", "bout_id", "partner", "t_start", "disp", "d0", "approach", "toward",
            "n_partners", "clock_hour", "wet", "fireworks", "burrow", "truncated",
            "_fx0", "_fy0", "_fx1", "_fy1", "_px", "_py"]
    if bouts.empty or fixes.empty:
        return pd.DataFrame(columns=cols)
    win = int(round(endpoint_win_s * NS)); pwin = int(round(partner_win_s * NS))
    # pre-group fixes by (shortid, night) -> sorted numpy arrays
    fx = fixes.copy()
    fx["_ns"] = pd.to_datetime(fx["datetime"]).astype("datetime64[ns]").astype("int64")
    fx = fx.sort_values(["shortid", "night", "_ns"])
    grp = {}
    for (sid, night), g in fx.groupby(["shortid", "night"], sort=False):
        grp[(str(sid), str(night))] = (g["_ns"].to_numpy("int64"),
                                       g["x"].to_numpy(float), g["y"].to_numpy(float))
    animals_by_night = {}
    for (sid, night) in grp:
        animals_by_night.setdefault(night, []).append(sid)

    b = bouts.copy()
    if exclude_spans_dropout and "spans_dropout" in b.columns:
        b = b[~b["spans_dropout"].astype(bool)]
    if "has_gap" in b.columns:
        b = b[~b["has_gap"].astype(bool)]
    rows = []
    for _, bt in b.iterrows():
        sid = str(bt["shortid"]); night = str(bt["night"])
        gf = grp.get((sid, night))
        if gf is None:
            continue
        t0 = pd.Timestamp(bt["t_start"]).value; t1 = pd.Timestamp(bt["t_end"]).value
        fx0, fy0 = _pos_at(t0, *gf, win_ns=win, side="around")
        fx1, fy1 = _pos_at(t1, *gf, win_ns=win, side="around")
        if not (np.isfinite(fx0) and np.isfinite(fx1)):
            continue
        disp = float(np.hypot(fx1 - fx0, fy1 - fy0))
        if disp < min_disp_in:
            continue                                         # jitter-scale bout (e.g., in-place) -> skip
        reg = em.night_regime(night)
        # partners present at bout start
        partners = []
        for pid in animals_by_night.get(night, []):
            if pid == sid:
                continue
            pg = grp[(pid, night)]
            px, py = _pos_at(t0, *pg, win_ns=pwin, side="before")
            if not np.isfinite(px):
                continue
            d0 = float(np.hypot(fx0 - px, fy0 - py))
            if d0 < min_partner_dist_in:
                continue                                     # sub-1 m pseudo-proximity -> skip
            partners.append((pid, px, py, d0))
        for pid, px, py, d0 in partners:
            d1 = float(np.hypot(fx1 - px, fy1 - py))
            approach = d0 - d1
            toward = float(np.clip(approach / disp, -1.0, 1.0)) if disp > 0 else np.nan
            rows.append({"shortid": sid, "night": night, "bout_id": int(bt["bout_id"]),
                         "partner": pid, "t_start": pd.Timestamp(t0), "disp": disp, "d0": d0,
                         "approach": approach, "toward": toward, "n_partners": len(partners),
                         "clock_hour": int(pd.Timestamp(t0).hour),
                         "wet": int(bool(reg.get("wet", False))), "fireworks": int(bool(reg.get("fireworks", False))),
                         "burrow": int(bool(reg.get("burrow", False))), "truncated": int(bool(reg.get("truncated", False))),
                         "_fx0": fx0, "_fy0": fy0, "_fx1": fx1, "_fy1": fy1, "_px": px, "_py": py})
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# measurement gate — NIGHT-BLOCK (the ~8 nights are the outer units, NOT the
# ~4k pseudoreplicated (bout,partner) pairs). Per-pair z scales with sqrt(n_pairs)
# and is NOT a valid significance test here; we test the per-night effect's
# SIGN CONSISTENCY across nights (a night-level sign test) instead.
# ---------------------------------------------------------------------------

def _toward_from(fx0, fy0, dx, dy, px, py):
    """toward = (|start-partner| - |end-partner|)/|disp| for displacement (dx,dy) from (fx0,fy0)."""
    d0 = np.hypot(fx0 - px, fy0 - py)
    d1 = np.hypot(fx0 + dx - px, fy0 + dy - py)
    disp = np.hypot(dx, dy)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(disp > 0, np.clip((d0 - d1) / disp, -1, 1), np.nan)


def _dir_null_mean(g, *, n_perm, rng):
    """Geometry expectation of mean toward-ness for this pair-set: rotate each displacement by a
    random angle about its start. The mean is NOT ~0 — it is generally negative (a step from a point
    tends to increase distance) — so the geometry-adjusted effect is obs MINUS this."""
    fx0 = g["_fx0"].to_numpy(); fy0 = g["_fy0"].to_numpy()
    r = np.hypot(g["_fx1"].to_numpy() - fx0, g["_fy1"].to_numpy() - fy0)
    px = g["_px"].to_numpy(); py = g["_py"].to_numpy()
    vals = np.empty(n_perm)
    for k in range(n_perm):
        phi = rng.uniform(0, 2 * np.pi, size=len(r))
        vals[k] = np.nanmean(_toward_from(fx0, fy0, r * np.cos(phi), r * np.sin(phi), px, py))
    return float(np.nanmean(vals))


def _build_partner_cells(fixes, *, max_per_cell=150, seed=0):
    """{(partner, clock_hour): {night: (xs, ys)}} downsampled — the layout distribution used by the
    day-shuffle (same partner, same hour, DIFFERENT night)."""
    fx = fixes.copy()
    fx["night"] = fx["night"].astype(str); fx["shortid"] = fx["shortid"].astype(str)
    fx["_hr"] = pd.to_datetime(fx["datetime"]).dt.hour
    rng = np.random.default_rng(seed)
    cell = {}
    for (pid, hr), g in fx.groupby(["shortid", "_hr"], sort=False):
        by_night = {}
        for nn, gn in g.groupby("night", sort=False):
            xs = gn["x"].to_numpy(float); ys = gn["y"].to_numpy(float)
            if len(xs) > max_per_cell:
                sel = rng.choice(len(xs), max_per_cell, replace=False); xs, ys = xs[sel], ys[sel]
            by_night[nn] = (xs, ys)
        cell[(pid, int(hr))] = by_night
    return cell


def _day_null_mean(g, cells, *, n_perm, rng):
    """(obs over VALID pairs, day-shuffle null mean over the SAME valid pairs). VALID = pairs whose
    (partner, hour) cell has >= 1 OTHER night — so obs and null are over the SAME subpopulation (a
    pair the null cannot evaluate is excluded from BOTH). Returns (obs_valid, null_mean, n_valid)."""
    fx0 = g["_fx0"].to_numpy(); fy0 = g["_fy0"].to_numpy()
    dx = g["_fx1"].to_numpy() - fx0; dy = g["_fy1"].to_numpy() - fy0
    tw = g["toward"].to_numpy()
    partner = g["partner"].astype(str).to_numpy(); hour = g["clock_hour"].to_numpy()
    night = g["night"].astype(str).to_numpy()
    valid = np.zeros(len(g), bool); others_list = [None] * len(g)
    for i in range(len(g)):
        bn = cells.get((partner[i], int(hour[i])))
        if not bn:
            continue
        oth = [nn for nn in bn if nn != night[i]]
        if oth:
            valid[i] = True; others_list[i] = oth
    if valid.sum() < 5:
        return np.nan, np.nan, int(valid.sum())
    obs_valid = float(np.nanmean(tw[valid]))
    vidx = np.where(valid)[0]
    nullv = np.empty(n_perm)
    for k in range(n_perm):
        pxs = np.full(len(g), np.nan); pys = np.full(len(g), np.nan)
        for i in vidx:
            oth = others_list[i]
            xs, ys = cells[(partner[i], int(hour[i]))][oth[rng.integers(0, len(oth))]]
            j = rng.integers(0, len(xs)); pxs[i] = xs[j]; pys[i] = ys[j]
        nullv[k] = np.nanmean(_toward_from(fx0[valid], fy0[valid], dx[valid], dy[valid], pxs[valid], pys[valid]))
    return obs_valid, float(np.nanmean(nullv)), int(valid.sum())


def _sign_test(effects) -> dict:
    """Two-sided binomial sign test on the per-night effects (null: p=0.5). Returns n, n_pos, mean, p."""
    from math import comb
    e = np.asarray([x for x in effects if x == x], float); e = e[e != 0]
    n = len(e)
    if n == 0:
        return {"n_nights": 0, "n_pos": 0, "mean": np.nan, "p": np.nan}
    k = int((e > 0).sum()); tot = 2.0 ** n
    p_ge = sum(comb(n, i) for i in range(k, n + 1)) / tot
    p_le = sum(comb(n, i) for i in range(0, k + 1)) / tot
    return {"n_nights": n, "n_pos": k, "mean": float(np.mean([x for x in effects if x == x])),
            "p": float(min(1.0, 2 * min(p_ge, p_le)))}


def direction_null_z(ctx: pd.DataFrame, *, n_perm: int = 200, seed: int = 0) -> dict:
    """POOLED descriptive direction-randomized null (obs mean toward vs the geometry expectation).
    On INDEPENDENT data (e.g. the selftest, where each bout is a distinct draw) the z validates that
    the metric responds to direction. On REAL pseudoreplicated (bout, partner) pairs the pooled z is
    NOT valid inference (it scales with sqrt(n_pairs)) — use :func:`night_block_gate`. Returns obs,
    null_mean (the geometry expectation, generally < 0), z."""
    if ctx.empty:
        return {"observed_mean_toward": np.nan, "null_mean": np.nan, "z": np.nan, "n": 0}
    fx0 = ctx["_fx0"].to_numpy(); fy0 = ctx["_fy0"].to_numpy()
    r = np.hypot(ctx["_fx1"].to_numpy() - fx0, ctx["_fy1"].to_numpy() - fy0)
    px = ctx["_px"].to_numpy(); py = ctx["_py"].to_numpy()
    obs = float(np.nanmean(ctx["toward"].to_numpy())); rng = np.random.default_rng(seed)
    null = np.empty(n_perm)
    for k in range(n_perm):
        phi = rng.uniform(0, 2 * np.pi, size=len(r))
        null[k] = np.nanmean(_toward_from(fx0, fy0, r * np.cos(phi), r * np.sin(phi), px, py))
    mu, sd = float(null.mean()), float(null.std()); z = (obs - mu) / sd if sd > 0 else np.nan
    return {"observed_mean_toward": obs, "null_mean": mu, "z": float(z) if z == z else np.nan,
            "n": int(len(ctx))}


def night_block_gate(ctx: pd.DataFrame, fixes: pd.DataFrame, *,
                     edges=(RADIUS_1M_IN, 80.0, 150.0, 1e9), labels=("1-2m", "2-3.8m", ">3.8m"),
                     min_pairs_per_night: int = 15, n_perm_dir: int = 150, n_perm_day: int = 50,
                     seed: int = 0) -> pd.DataFrame:
    """The valid gate: per NIGHT, per distance bin (+ pooled), compute the geometry-adjusted effect
    e_dir = mean(toward) - dir_null_mean and the social increment e_day = mean(toward|valid) -
    day_null_mean; then a night-level SIGN TEST across the ~8 nights (the outer blocks). Columns per
    (bin): n_nights, e_dir mean/n_pos/p, e_day mean/n_pos/p, and the resolved sign. This does NOT use
    the pseudoreplicated per-pair z."""
    if ctx.empty:
        return pd.DataFrame()
    c = ctx.copy()
    c["_bin"] = pd.cut(c["d0"], list(edges), labels=list(labels), include_lowest=True).astype("object")
    cells = _build_partner_cells(fixes, seed=seed)
    rng = np.random.default_rng(seed)
    nights = sorted(c["night"].astype(str).unique())
    rows = []
    for b in ["ALL"] + list(labels):
        cb = c if b == "ALL" else c[c["_bin"] == b]
        e_dir, e_day = [], []
        for nn in nights:
            g = cb[cb["night"].astype(str) == nn]
            if len(g) < min_pairs_per_night:
                continue
            dnm = _dir_null_mean(g, n_perm=n_perm_dir, rng=rng)
            e_dir.append(float(np.nanmean(g["toward"].to_numpy())) - dnm)
            ov, dvm, nv = _day_null_mean(g, cells, n_perm=n_perm_day, rng=rng)
            e_day.append((ov - dvm) if (ov == ov and dvm == dvm) else np.nan)
        sd = _sign_test(e_dir); sy = _sign_test([x for x in e_day if x == x])
        net = "approach" if (sd["mean"] or 0) > 0 else ("avoid" if (sd["mean"] or 0) < 0 else "none")
        rows.append({"bin": b, "n_pairs": int(len(cb)), "n_nights": sd["n_nights"],
                     "e_dir_mean": round(sd["mean"], 4) if sd["mean"] == sd["mean"] else None,
                     "e_dir_n_pos": sd["n_pos"], "e_dir_signtest_p": round(sd["p"], 3) if sd["p"] == sd["p"] else None,
                     "e_day_mean": round(sy["mean"], 4) if sy["mean"] == sy["mean"] else None,
                     "e_day_n_pos": sy["n_pos"], "e_day_signtest_p": round(sy["p"], 3) if sy["p"] == sy["p"] else None,
                     "above_geometry_night": bool(sd["p"] == sd["p"] and sd["p"] <= 0.1),
                     "real_time_social_night": bool(sy["p"] == sy["p"] and sy["p"] <= 0.1),
                     "net_sign": net})
    return pd.DataFrame(rows)


def measurement_gate(ctx: pd.DataFrame, fixes: pd.DataFrame, *, n_perm_dir: int = 150,
                     n_perm_day: int = 50, min_pairs: int = 40, min_pairs_per_night: int = 15,
                     seed: int = 0) -> dict:
    """NIGHT-BLOCK gate. RESOLVABLE = enough pairs AND the geometry-adjusted effect (e_dir) is
    sign-consistent across nights (night-level sign-test p <= 0.1) in the pooled set OR any distance
    bin. SOCIAL = the real-time social increment (e_day) is night-consistent (p <= 0.1) in the pooled
    set OR any bin. The model is fit only if SOCIAL. Also carries the per-bin night-block table (the
    headline, because the sign is distance-dependent)."""
    nb = night_block_gate(ctx, fixes, n_perm_dir=n_perm_dir, n_perm_day=n_perm_day,
                          min_pairs_per_night=min_pairs_per_night, seed=seed)
    n = int(len(ctx))
    support_ok = n >= min_pairs
    pooled = nb[nb["bin"] == "ALL"].iloc[0].to_dict() if not nb.empty else {}
    resolvable = bool(support_ok and not nb.empty and bool(nb["above_geometry_night"].any()))
    social = bool(resolvable and bool(nb["real_time_social_night"].any()))
    # SOCIAL sign structure = the direction of the real-time increment e_day (approach if >0, avoid if
    # <0) among bins whose e_day is night-consistent — NOT e_dir (which is 'above geometry' everywhere).
    soc_bins = nb[(nb["bin"] != "ALL") & nb["real_time_social_night"]]
    signs = {r["bin"]: ("approach" if (r["e_day_mean"] or 0) > 0 else "avoid")
             for _, r in soc_bins.iterrows() if r["e_day_mean"] == r["e_day_mean"]}
    distance_dependent = len(set(signs.values())) > 1
    return {"n_pairs": n, "support_ok": support_ok, "night_block": nb.to_dict("records"),
            "pooled_night": {k: pooled.get(k) for k in ("n_nights", "e_dir_mean", "e_dir_signtest_p",
                                                        "e_day_mean", "e_day_signtest_p", "net_sign")},
            "gate_resolvable": resolvable, "gate_social": social,
            "net_sign": pooled.get("net_sign", "none"), "social_bin_signs": signs,
            "distance_dependent": distance_dependent,
            "verdict": (("SOCIAL approach/avoid resolvable at the night level" +
                         (" — DISTANCE-DEPENDENT (approach far / avoid near): social spacing" if distance_dependent else ""))
                        if social else
                        ("above-geometry directional bias is night-consistent but LAYOUT (not social)"
                         if resolvable else "no night-consistent approach/avoid signal above geometry/jitter"))}


# ---------------------------------------------------------------------------
# gated model table
# ---------------------------------------------------------------------------

def build_model_table(ctx: pd.DataFrame) -> pd.DataFrame:
    """The modeling table (built only after ``gate_social``): drop internal coords, add a binary
    ``approached`` (toward > 0) and a crowding covariate. For a held-out approach/avoid model over
    covariates (own displacement, layout, group-social)."""
    keep = [c for c in ctx.columns if not c.startswith("_")]
    out = ctx[keep].copy()
    out["approached"] = (out["toward"] > 0).astype(int)
    return out
