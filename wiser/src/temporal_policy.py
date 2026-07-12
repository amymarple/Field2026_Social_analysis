r"""
temporal_policy.py — does the state->site-departure MAPPING vary across hour-of-night / across nights?

The question is about the CONDITIONAL rule, not marginal behavior. Different hours contain different
ROI occupancy, dwell, activity, and social configurations; that is NOT a different policy. Evidence
for a time-varying rule requires that the conditional mapping (leaving hazard given the SAME state)
changes — i.e. a held-out-night gain from letting slopes vary with time, within comparable states.

Nested leaving-hazard models on the CLEAN hysteretic leave table (never the raw run):
  M0 — pooled reference: dwell basis + ROI + hour-block MAIN effect + regime/weather + group-social.
       (Hour may shift the BASELINE hazard; all dwell/social/ROI slopes are shared across time.)
  M1 — hour-varying slopes: add hour-block × {social, dwell, major-ROI} interactions (ridge = partial
       pooling toward the shared slope). Held-out-night testable (hour known for a held-out night).
  M2 — night-slope variance (IN-SAMPLE): a held-out NIGHT's slope deviation is unobservable, so this
       cannot show held-out-night gain by construction. Instead estimate the shrunk night×social slope
       spread and test it vs a night-label permutation → is there night-to-night conditional variation?
  M3 — structured context (held-out testable): replace arbitrary night identity with habituation trend
       / phase / wet / fireworks / burrow × social interactions. A held-out night HAS a known context,
       so these improve held-out prediction iff night drift is structured.
  M4 — hour × structured-context (gated on M1 AND M3), heavily regularized, held-out evaluated.

Reuses choice_models (build_design / lono_bits / social_increment / _fit_logit / bits_bernoulli).
Runs under anaconda3 (sklearn).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import choice_models as cm

DWELL = "dwell_elapsed_s"
BASE_NUM = ["dist_to_edge_in", "moving_frac", "wet", "fireworks", "burrow",
            "w_temp_c", "w_tempdew_gap_c", "w_rain_log1p", "w_solar_wm2"]
SOCIAL = ["n_within_1m", "mean_others_dist_in"]        # jitter-floor-safe group-social
VARY = SOCIAL + ["is_house", "is_refuge"]              # slopes allowed to vary with time
BASE_CAT = ["roi", "hour_block"]

# release date -> night index (habituation), and experiment phase
_NIGHTS = ["2026-06-28", "2026-06-29", "2026-06-30", "2026-07-01",
           "2026-07-02", "2026-07-03", "2026-07-04", "2026-07-05"]
_PHASE = {n: ("early" if i < 2 else "mid" if i < 5 else "late") for i, n in enumerate(_NIGHTS)}


TZ_OFFSET_HOURS = -4        # EDT: the decision tables store clock_hour in naive UTC


def add_hour_block(df: pd.DataFrame, col: str = "clock_hour") -> pd.DataFrame:
    """3-block hour-of-night factor (robust default; go finer only if support justifies):
    early 21:00–24:00, mid 00:00–03:00, late 03:00–05:00 LOCAL. The decision tables store
    ``clock_hour`` in naive UTC, so convert to local (EDT −4 h) first. Also a continuous
    hours-since-21:00 (0..7)."""
    d = df.copy()
    h_utc = pd.to_numeric(d[col], errors="coerce")
    h = (h_utc + TZ_OFFSET_HOURS) % 24                 # local hour
    hon = np.where(h >= 21, h - 21, h + 3)             # hours since 21:00 (0..7)
    d["local_hour"] = h
    d["hours_since_2100"] = hon
    d["hour_block"] = np.where(hon < 3, "early", np.where(hon < 6, "mid", "late"))
    return d


def add_structured_context(df: pd.DataFrame) -> pd.DataFrame:
    """Structured night covariates (held-out testable): habituation night index (days since release),
    experiment phase, and the per-night regime flags already on the table."""
    d = df.copy()
    idx = {n: i for i, n in enumerate(_NIGHTS)}
    d["night_index"] = d["night"].map(idx).fillna(0).astype(float)     # habituation trend
    d["phase"] = d["night"].map(_PHASE).fillna("mid")
    return d


def _interactions(df: pd.DataFrame, factor_col: str, feature_cols, *, base_num=BASE_NUM,
                  dwell=True) -> tuple[pd.DataFrame, list]:
    """Add (factor level × feature) numeric interaction columns for the varying features + dwell.
    Returns (df_with_cols, new_numeric_names). Levels taken from the whole df so train/test align."""
    d = df.copy()
    levels = sorted(d[factor_col].astype("object").dropna().unique().tolist())
    feats = list(feature_cols) + (["_dwell_lin"] if dwell else [])
    if dwell:
        d["_dwell_lin"] = np.log1p(pd.to_numeric(d[DWELL], errors="coerce").clip(lower=0))
    new = []
    for lv in levels[1:]:                              # drop first level = reference (avoid collinearity w/ main)
        ind = (d[factor_col].astype("object") == lv).astype(float)
        for f in feats:
            if f in d.columns:
                nm = f"_ix_{factor_col}_{lv}__{f}"
                d[nm] = ind * pd.to_numeric(d[f], errors="coerce").fillna(0.0)
                new.append(nm)
    return d, new


def _lono_H(df, numeric, categorical, l2=1.0):
    t = cm.lono_bits(df, "left", numeric=numeric, categorical=categorical, dwell_col=DWELL, l2=l2)
    return float(t[t.animal == "ALL"]["bits"].mean()), t


def hour_varying_gain(df: pd.DataFrame, *, l2=1.0) -> dict:
    """M0 (hour main-effect) vs M1 (hour × {social,dwell,ROI} slopes). Held-out-night Δbits."""
    d = add_hour_block(df)
    H0, t0 = _lono_H(d, BASE_NUM + SOCIAL, BASE_CAT, l2=l2)
    d1, ix = _interactions(d, "hour_block", VARY)
    H1, t1 = _lono_H(d1, BASE_NUM + SOCIAL + ix, BASE_CAT, l2=l2)
    # per-held-night gain (block-level effect size)
    b0 = t0[t0.animal == "ALL"].set_index("held_night")["bits"]
    b1 = t1[t1.animal == "ALL"].set_index("held_night")["bits"]
    per = (b0 - b1).reindex(b0.index)
    return {"H_M0": H0, "H_M1": H1, "dbits": H0 - H1, "skill_gain": (H0 - H1) / H0 if H0 else np.nan,
            "frac_positive_nights": float((per > 0).mean()), "per_night": per.to_dict(),
            "n_interaction_terms": len(ix)}


def structured_context_gain(df: pd.DataFrame, *, l2=1.0) -> pd.DataFrame:
    """M0 vs M3 for each structured context covariate separately (context × social interactions).
    Held-out-night Δbits — a held-out night has a known context value, so this is testable."""
    d = add_structured_context(add_hour_block(df))
    H0, _ = _lono_H(d, BASE_NUM + SOCIAL, BASE_CAT, l2=l2)
    rows = []
    for ctx, kind in [("night_index", "num"), ("phase", "cat"), ("wet", "num"),
                      ("fireworks", "num"), ("burrow", "num")]:
        if ctx not in d.columns:
            continue
        if kind == "num":
            dd = d.copy()
            for f in SOCIAL:
                dd[f"_ctx_{ctx}__{f}"] = pd.to_numeric(dd[ctx], errors="coerce").fillna(0.0) * \
                    pd.to_numeric(dd[f], errors="coerce").fillna(0.0)
            ixcols = [f"_ctx_{ctx}__{f}" for f in SOCIAL]
            H, _ = _lono_H(dd, BASE_NUM + SOCIAL + ixcols, BASE_CAT, l2=l2)
        else:
            dd, ixcols = _interactions(d, ctx, SOCIAL, dwell=False)
            H, _ = _lono_H(dd, BASE_NUM + SOCIAL + ixcols, BASE_CAT + [ctx] if ctx not in BASE_CAT else BASE_CAT, l2=l2)
        rows.append({"context": ctx, "H_M0": round(H0, 4), "H_M3": round(H, 4),
                     "dbits": round(H0 - H, 4), "improves": bool(H0 - H > 0)})
    return pd.DataFrame(rows)


def hour_social_slopes(df: pd.DataFrame, *, l2=1.0) -> pd.DataFrame:
    """Effect DIRECTION: per hour-block, the in-sample social increment (does crowding increase or
    suppress departure, and does the sign change across the night?). Reports Δbits + the sign of the
    n_within_1m coefficient per block."""
    d = add_hour_block(df)
    rows = []
    for blk in ["early", "mid", "late"]:
        g = d[d.hour_block == blk]
        if len(g) < 200:
            rows.append({"hour_block": blk, "n": len(g), "social_dbits": np.nan, "nn1m_coef_sign": None})
            continue
        # in-sample: fit base vs base+social on this block, and the sign of n_within_1m
        X0, _, cats, miss = cm.build_design(g, BASE_NUM, ["roi"], dwell_col=DWELL)
        m0 = cm._fit_logit(X0, g["left"].to_numpy(int), l2=l2)
        X1, names, _, _ = cm.build_design(g, BASE_NUM + SOCIAL, ["roi"], dwell_col=DWELL)
        m1 = cm._fit_logit(X1, g["left"].to_numpy(int), l2=l2)
        p0 = cm._predict(m0, X0); p1 = cm._predict(m1, X1)
        db = cm.bits_bernoulli(g["left"].to_numpy(int), p0) - cm.bits_bernoulli(g["left"].to_numpy(int), p1)
        coef = None
        if hasattr(m1, "named_steps") and "n_within_1m" in names:
            coef = float(m1.named_steps["logisticregression"].coef_[0][names.index("n_within_1m")])
        rows.append({"hour_block": blk, "n": int(len(g)), "leave_rate": round(float(g.left.mean()), 3),
                     "median_crowd": round(float(pd.to_numeric(g.n_within_1m, errors="coerce").median()), 2),
                     "social_dbits_insample": round(float(db), 4),
                     "nn1m_coef": round(coef, 4) if coef is not None else None,
                     "crowd_effect": (None if coef is None else "increases_leaving" if coef > 0 else "suppresses_leaving")})
    return pd.DataFrame(rows)


def night_slope_variance(df: pd.DataFrame, *, n_perm=30, seed=0, l2=1.0) -> dict:
    """M2 (in-sample): spread of per-night social increment vs a night-label permutation null.
    Positive = night-to-night CONDITIONAL variation exists (magnitude), NOT a held-out claim."""
    d = df.copy()
    def per_night_social(dd):
        out = []
        for n, g in dd.groupby("night"):
            if len(g) < 200:
                continue
            X0, _, _, _ = cm.build_design(g, BASE_NUM, ["roi"], dwell_col=DWELL)
            X1, _, _, _ = cm.build_design(g, BASE_NUM + SOCIAL, ["roi"], dwell_col=DWELL)
            y = g["left"].to_numpy(int)
            p0 = cm._predict(cm._fit_logit(X0, y, l2=l2), X0)
            p1 = cm._predict(cm._fit_logit(X1, y, l2=l2), X1)
            out.append(cm.bits_bernoulli(y, p0) - cm.bits_bernoulli(y, p1))
        return np.asarray(out, float)
    obs = per_night_social(d)
    obs_sd = float(np.std(obs)) if len(obs) > 1 else np.nan
    rng = np.random.default_rng(seed)
    null_sd = []
    for _ in range(n_perm):
        dd = d.copy(); dd["night"] = rng.permutation(dd["night"].to_numpy())
        s = per_night_social(dd)
        if len(s) > 1:
            null_sd.append(np.std(s))
    null_sd = np.asarray(null_sd, float)
    z = (obs_sd - null_sd.mean()) / null_sd.std() if len(null_sd) and null_sd.std() > 0 else np.nan
    return {"per_night_social_dbits": [round(float(x), 4) for x in obs], "sd_observed": round(obs_sd, 4),
            "sd_null_mean": round(float(null_sd.mean()), 4) if len(null_sd) else np.nan,
            "z": round(float(z), 2) if z == z else np.nan}


def hour_label_permutation_null(df: pd.DataFrame, *, n_perm=20, seed=0, l2=1.0) -> dict:
    """Permute hour_block WITHIN comparable-state strata (roi × dwell-tercile × animal), recompute the
    hour-varying gain. Breaks hour↔decision alignment while holding state fixed → tests whether the
    hour-varying gain is real conditional structure, not state confound."""
    d = add_hour_block(df)
    d["_dt"] = pd.qcut(pd.to_numeric(d[DWELL]).rank(method="first"), 3, labels=False, duplicates="drop")
    obs = hour_varying_gain(df, l2=l2)["dbits"]
    rng = np.random.default_rng(seed)
    strata = d.groupby(["roi", "_dt", "shortid"]).indices
    null = []
    for _ in range(n_perm):
        dd = d.copy()
        hb = dd["hour_block"].to_numpy().copy()
        for _, idx in strata.items():
            if len(idx) > 1:
                hb[idx] = rng.permutation(hb[idx])
        dd["hour_block"] = hb
        d1, ix = _interactions(dd, "hour_block", VARY)
        H0, _ = _lono_H(dd, BASE_NUM + SOCIAL, BASE_CAT, l2=l2)
        H1, _ = _lono_H(d1, BASE_NUM + SOCIAL + ix, BASE_CAT, l2=l2)
        null.append(H0 - H1)
    null = np.asarray(null, float)
    z = (obs - null.mean()) / null.std() if len(null) and null.std() > 0 else np.nan
    return {"observed_dbits": round(float(obs), 4), "null_mean": round(float(null.mean()), 4),
            "z": round(float(z), 2) if z == z else np.nan, "n_perm": len(null)}


def night_dominance_audit(df: pd.DataFrame, *, l2=1.0) -> pd.DataFrame:
    """Leave-one-night-out and leave-one-animal-out recomputation of the hour-varying gain — is it
    dominated by fireworks (07-04) / wet / truncated (07-05) / burrow / one animal?"""
    rows = [{"drop": "none", "dbits": round(hour_varying_gain(df, l2=l2)["dbits"], 4)}]
    for n in sorted(df["night"].unique()):
        rows.append({"drop": f"night_{n}", "dbits": round(hour_varying_gain(df[df.night != n], l2=l2)["dbits"], 4)})
    for a in sorted(df["shortid"].astype(str).unique()):
        rows.append({"drop": f"animal_{a}", "dbits": round(hour_varying_gain(df[df.shortid.astype(str) != a], l2=l2)["dbits"], 4)})
    return pd.DataFrame(rows)


def state_vs_conditional(df: pd.DataFrame) -> pd.DataFrame:
    """Decompose per hour-block: MARGINAL state occupancy/dwell/crowding/leave-rate vs the CONDITIONAL
    departure probability at a FIXED reference state (so a hazard change isn't just occupancy change)."""
    d = add_hour_block(df)
    rows = []
    for blk in ["early", "mid", "late"]:
        g = d[d.hour_block == blk]
        if g.empty:
            continue
        rows.append({"hour_block": blk, "n_epochs": int(len(g)),
                     "marginal_leave_rate": round(float(g.left.mean()), 3),
                     "frac_in_house": round(float(g.roi.isin(["house_1", "house_2"]).mean()), 3),
                     "median_dwell_s": round(float(pd.to_numeric(g[DWELL]).median()), 1),
                     "median_crowd_within1m": round(float(pd.to_numeric(g.n_within_1m, errors="coerce").median()), 2),
                     "frac_moving": round(float(pd.to_numeric(g.moving_frac, errors="coerce").mean()), 3)})
    return pd.DataFrame(rows)
