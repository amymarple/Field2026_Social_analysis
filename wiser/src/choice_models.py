r"""
choice_models.py — estimators, held-out losses, personalization, matched-choice, and nulls
for the WISER agent-policy identifiability ladder.

Primary loss is held-out CROSS-ENTROPY in BITS/decision (base-2), separately for the leaving
(Bernoulli) and destination (categorical) processes. The organizing quantities:

  skill  = 1 - H_model / H_baseline
  Dbits  = H_baseline - H_model                     (bits/decision)

All model comparison is done at the NIGHT-block level (leave-one-night-out); ~8 nights are the
outer unit, never per-decision p-values. Individual structure is tested by SAME-ANIMAL
CROSS-NIGHT personalization (pooled vs +identity, scored on a held-out night for that animal),
guarded by an env-matched conditional identity permutation. Social structure is a strictly
pre-decision predictive increment gated by within-night time-shift AND day-shuffle nulls.

Interpretable estimators only: penalized logistic (leaving), per-origin multinomial (destination).
sklearn is used for the fits (available under the anaconda3 interpreter); the loss/CV/null logic
is numpy/pandas. Frame-invariant features only; NaN predictors (e.g. missing social) are carried
via a missing-indicator + zero-fill, never dropped.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    _HAVE_SK = True
except Exception:                                    # pragma: no cover
    _HAVE_SK = False

EPS = 1e-12


class _ConstPredictor:
    """Intercept-only predictor (train base rate) for the marginal / no-feature model."""
    def __init__(self, p):
        self.p = float(np.clip(p, EPS, 1 - EPS))

    def predict_proba(self, X):
        n = len(X)
        return np.column_stack([np.full(n, 1 - self.p), np.full(n, self.p)])


# ---------------------------------------------------------------------------
# losses (bits/decision)
# ---------------------------------------------------------------------------

def bits_bernoulli(y, p) -> float:
    """Mean binary cross-entropy in bits: -mean[y log2 p + (1-y) log2(1-p)]."""
    y = np.asarray(y, float)
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return float(-np.mean(y * np.log2(p) + (1 - y) * np.log2(1 - p)))


def bits_categorical(p_chosen) -> float:
    """Mean categorical cross-entropy in bits: -mean log2 P(chosen)."""
    p = np.clip(np.asarray(p_chosen, float), EPS, 1.0)
    return float(-np.mean(np.log2(p)))


def skill(h_model: float, h_base: float) -> float:
    return float(1.0 - h_model / h_base) if h_base > 0 else np.nan


# ---------------------------------------------------------------------------
# design matrix
# ---------------------------------------------------------------------------

def _dwell_basis(dwell_s) -> np.ndarray:
    """Low-dof monotone dwell basis (absorbs residence-time dependence): [log1p, sqrt-ish]."""
    d = np.asarray(dwell_s, float)
    return np.column_stack([np.log1p(np.clip(d, 0, None)),
                            np.sqrt(np.clip(d, 0, None))])


def build_design(df: pd.DataFrame, numeric=(), categorical=(), *, dwell_col=None,
                 categories: dict | None = None, missing: set | None = None):
    """Assemble a numeric design matrix with train/test-ALIGNED columns. Categoricals -> one-hot
    (fixed ``categories``); numeric NaN -> a missing-indicator column + zero-fill. Because the
    design is positional (hstack + coefficients-by-index), the SAME columns in the SAME order
    must be emitted for the train-fit and the test-predict, even when the held-out night's NaN
    pattern differs (a real hazard here: social/weather features drop out on specific nights).
    So the set of numeric columns that carry a missing-indicator is fixed on the training call
    and passed back in via ``missing`` for the test call. Returns (X, names, categories, missing)."""
    cols, names = [], []
    cats_out = dict(categories or {})
    # which numeric columns carry a missing-indicator (decided on train; reused on test)
    if missing is None:
        miss_set = {c for c in numeric if c in df.columns
                    and bool(pd.to_numeric(df[c], errors="coerce").isna().any())}
    else:
        miss_set = set(missing)
    if dwell_col and dwell_col in df.columns:
        b = _dwell_basis(df[dwell_col]); cols.append(b); names += ["dwell_log1p", "dwell_sqrt"]
    for c in numeric:
        if c not in df.columns:
            continue
        v = pd.to_numeric(df[c], errors="coerce").to_numpy(float)
        if c in miss_set:                                     # always emit (all-zero if no NaN here)
            cols.append(np.isnan(v).astype(float)[:, None]); names.append(f"{c}__missing")
        cols.append(np.nan_to_num(v, nan=0.0)[:, None]); names.append(c)
    for c in categorical:
        if c not in df.columns:
            continue
        levels = cats_out.get(c) or sorted(pd.Series(df[c].astype("object")).dropna().unique().tolist())
        cats_out[c] = levels
        vv = df[c].astype("object").to_numpy()
        for lv in levels:
            cols.append((vv == lv).astype(float)[:, None]); names.append(f"{c}={lv}")
    if not cols:
        return np.zeros((len(df), 0)), [], cats_out, miss_set
    return np.hstack(cols), names, cats_out, miss_set


def _fit_logit(X, y, l2=1.0):
    if not _HAVE_SK:
        raise RuntimeError("scikit-learn required (run under the anaconda3 interpreter)")
    y = np.asarray(y, int)
    # no informative features (marginal) or degenerate class -> constant base-rate predictor
    if X.shape[1] == 0 or np.allclose(X.std(axis=0), 0) or len(np.unique(y)) < 2:
        return _ConstPredictor(y.mean())
    C = 1.0 / max(l2, 1e-6)
    m = make_pipeline(StandardScaler(), LogisticRegression(C=C, solver="lbfgs", max_iter=5000))
    m.fit(X, y)
    return m


def _predict(m, X):
    return np.clip(m.predict_proba(X)[:, 1], EPS, 1 - EPS)


# ---------------------------------------------------------------------------
# leave-one-night-out held-out bits for a feature set (Bernoulli leaving model)
# ---------------------------------------------------------------------------

def lono_bits(df: pd.DataFrame, y_col: str, *, numeric=(), categorical=(), dwell_col="dwell_elapsed_s",
              night_col="night", animal_col="shortid", l2=1.0) -> pd.DataFrame:
    """Leave-one-night-out held-out bits for one Bernoulli feature set. Returns per-(held night)
    and per-(held night, animal) held-out bits + n."""
    nights = sorted(df[night_col].unique())
    rows = []
    for hn in nights:
        tr = df[df[night_col] != hn]
        te = df[df[night_col] == hn]
        if len(tr) < 20 or te.empty:
            continue
        Xtr, names, cats, miss = build_design(tr, numeric, categorical, dwell_col=dwell_col)
        m = _fit_logit(Xtr, tr[y_col].to_numpy(int), l2=l2)
        Xte, _, _, _ = build_design(te, numeric, categorical, dwell_col=dwell_col,
                                    categories=cats, missing=miss)
        p = _predict(m, Xte)
        y = te[y_col].to_numpy(int)
        rows.append({"held_night": hn, "animal": "ALL", "n": int(len(te)),
                     "bits": bits_bernoulli(y, p)})
        for a, ga in te.groupby(animal_col):
            idx = (te[animal_col] == a).to_numpy()
            rows.append({"held_night": hn, "animal": str(a), "n": int(idx.sum()),
                         "bits": bits_bernoulli(y[idx], p[idx])})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# same-animal cross-night personalization gain (individual arm)
# ---------------------------------------------------------------------------

def personalization_gain(df: pd.DataFrame, y_col: str, *, base_numeric=(), base_categorical=(),
                         id_features=(), dwell_col="dwell_elapsed_s", night_col="night",
                         animal_col="shortid", l2=1.0) -> pd.DataFrame:
    """Δbits(i, held_night) = H_holdout(pooled) - H_holdout(personalized), per animal per held
    night. Pooled = base features; personalized = base + animal fixed effects + animal×id_features
    interactions (the identity part is estimated only from that animal's TRAINING nights, because
    the whole held-out night is excluded). Positive, sign-consistent, calibrated, transfer =
    stable individual decision structure."""
    nights = sorted(df[night_col].unique())
    rows = []
    for hn in nights:
        tr = df[df[night_col] != hn].copy()
        te = df[df[night_col] == hn].copy()
        if len(tr) < 40 or te.empty:
            continue
        # pooled
        Xtr, names, cats, miss = build_design(tr, base_numeric, base_categorical, dwell_col=dwell_col)
        mp = _fit_logit(Xtr, tr[y_col].to_numpy(int), l2=l2)
        Xte, _, _, _ = build_design(te, base_numeric, base_categorical, dwell_col=dwell_col,
                                    categories=cats, missing=miss)
        p_pool = _predict(mp, Xte)
        # personalized: add animal FE + animal×id interactions
        animals = sorted(df[animal_col].unique())
        tr_p = _augment_identity(tr, animals, id_features, animal_col)
        te_p = _augment_identity(te, animals, id_features, animal_col)
        id_num = tuple(base_numeric) + tuple(c for c in tr_p.columns if c.startswith("_id_"))
        Xtr2, names2, cats2, miss2 = build_design(tr_p, id_num, base_categorical, dwell_col=dwell_col)
        mq = _fit_logit(Xtr2, tr_p[y_col].to_numpy(int), l2=l2)
        Xte2, _, _, _ = build_design(te_p, id_num, base_categorical, dwell_col=dwell_col,
                                     categories=cats2, missing=miss2)
        p_pers = _predict(mq, Xte2)
        y = te[y_col].to_numpy(int)
        for a in te[animal_col].unique():
            idx = (te[animal_col] == a).to_numpy()
            if idx.sum() < 10:
                continue
            rows.append({"held_night": hn, "animal": str(a), "n": int(idx.sum()),
                         "bits_pooled": bits_bernoulli(y[idx], p_pool[idx]),
                         "bits_personalized": bits_bernoulli(y[idx], p_pers[idx]),
                         "delta_bits": bits_bernoulli(y[idx], p_pool[idx]) - bits_bernoulli(y[idx], p_pers[idx])})
    return pd.DataFrame(rows)


def _augment_identity(df, animals, id_features, animal_col):
    """Add animal fixed-effect dummies (_id_<a>) and animal×feature interactions (_id_<a>_x_<f>)."""
    out = df.copy()
    a = out[animal_col].astype("object").to_numpy()
    for an in animals:
        d = (a == an).astype(float)
        out[f"_id_{an}"] = d
        for f in id_features:
            if f in out.columns:
                out[f"_id_{an}_x_{f}"] = d * pd.to_numeric(out[f], errors="coerce").fillna(0.0).to_numpy()
    return out


def summarize_gain(gain: pd.DataFrame, value="delta_bits") -> dict:
    """Block-level summary of a per-(animal,held-night) gain: median, sign fraction across held
    nights, and whether dominated by a single animal or night."""
    if gain.empty:
        return {"median": np.nan, "frac_positive": np.nan, "n_cells": 0}
    g = gain.dropna(subset=[value])
    by_night = g.groupby("held_night")[value].mean()
    by_animal = g.groupby("animal")[value].mean()
    total = g[value].sum()
    top_animal = by_animal.abs().max() / (abs(total) + EPS) if len(by_animal) else np.nan
    top_night = by_night.abs().max() / (abs(total) + EPS) if len(by_night) else np.nan
    return {
        "median": float(g[value].median()),
        "mean": float(g[value].mean()),
        "frac_positive_cells": float((g[value] > 0).mean()),
        "frac_positive_nights": float((by_night > 0).mean()),
        "n_cells": int(len(g)), "n_nights": int(len(by_night)),
        "dominance_top_animal": float(top_animal), "dominance_top_night": float(top_night),
    }


# ---------------------------------------------------------------------------
# nulls
# ---------------------------------------------------------------------------

def conditional_permutation_null(df: pd.DataFrame, y_col: str, *, strata_cols, base_numeric=(),
                                 base_categorical=(), id_features=(), dwell_col="dwell_elapsed_s",
                                 night_col="night", animal_col="shortid", n_perm=100, seed=0,
                                 l2=1.0) -> dict:
    """Env-matched conditional identity permutation: shuffle the animal label WITHIN comparable
    -state strata (holding each animal's marginal state-visitation fixed), recompute the median
    personalization gain, and return z of the observed vs the permutation distribution."""
    obs = summarize_gain(personalization_gain(df, y_col, base_numeric=base_numeric,
                                              base_categorical=base_categorical, id_features=id_features,
                                              dwell_col=dwell_col, night_col=night_col,
                                              animal_col=animal_col, l2=l2))["median"]
    rng = np.random.default_rng(seed)
    strata = df.groupby(list(strata_cols)).ngroup().to_numpy()
    perms = []
    for _ in range(n_perm):
        dd = df.copy()
        lab = dd[animal_col].to_numpy().copy()
        for s in np.unique(strata):
            m = strata == s
            lab[m] = rng.permutation(lab[m])
        dd[animal_col] = lab
        perms.append(summarize_gain(personalization_gain(dd, y_col, base_numeric=base_numeric,
                                    base_categorical=base_categorical, id_features=id_features,
                                    dwell_col=dwell_col, night_col=night_col,
                                    animal_col=animal_col, l2=l2))["median"])
    perms = np.asarray([p for p in perms if p == p], float)
    mu, sd = (perms.mean(), perms.std()) if len(perms) else (np.nan, np.nan)
    z = (obs - mu) / sd if sd and sd > 0 else np.nan
    return {"observed": obs, "null_mean": float(mu) if mu == mu else np.nan,
            "null_sd": float(sd) if sd == sd else np.nan, "z": float(z) if z == z else np.nan,
            "n_perm": int(len(perms))}


def social_increment(df: pd.DataFrame, y_col: str, *, base_numeric=(), base_categorical=(),
                     social_features=(), dwell_col="dwell_elapsed_s", night_col="night",
                     animal_col="shortid", l2=1.0) -> pd.DataFrame:
    """Held-out Δbits of adding strictly pre-decision social features over a base model
    (whole-night holdout). Returns per-(held night) Δbits (H_base - H_social)."""
    base = lono_bits(df, y_col, numeric=base_numeric, categorical=base_categorical,
                     dwell_col=dwell_col, night_col=night_col, animal_col=animal_col, l2=l2)
    full = lono_bits(df, y_col, numeric=tuple(base_numeric) + tuple(social_features),
                     categorical=base_categorical, dwell_col=dwell_col, night_col=night_col,
                     animal_col=animal_col, l2=l2)
    b = base[base.animal == "ALL"].set_index("held_night")["bits"]
    f = full[full.animal == "ALL"].set_index("held_night")["bits"]
    out = pd.DataFrame({"held_night": b.index, "bits_base": b.values,
                        "bits_social": f.reindex(b.index).values})
    out["delta_bits"] = out["bits_base"] - out["bits_social"]
    return out


def time_shift_social_null(df: pd.DataFrame, y_col: str, social_features, *, base_numeric=(),
                           base_categorical=(), dwell_col="dwell_elapsed_s", night_col="night",
                           animal_col="shortid", n_perm=50, seed=0, l2=1.0) -> dict:
    """Within-night circular time-shift of the social features (preserving their activity +
    missingness structure), recompute the mean social Δbits, return z of observed vs null."""
    obs = social_increment(df, y_col, base_numeric=base_numeric, base_categorical=base_categorical,
                           social_features=social_features, dwell_col=dwell_col, night_col=night_col,
                           animal_col=animal_col, l2=l2)["delta_bits"].mean()
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(n_perm):
        dd = df.copy()
        for (n, a), g in dd.groupby([night_col, animal_col]):
            k = rng.integers(1, max(2, len(g)))
            idx = g.index.to_numpy()
            for f in social_features:
                dd.loc[idx, f] = np.roll(g[f].to_numpy(), k)
        null.append(social_increment(dd, y_col, base_numeric=base_numeric,
                    base_categorical=base_categorical, social_features=social_features,
                    dwell_col=dwell_col, night_col=night_col, animal_col=animal_col, l2=l2)["delta_bits"].mean())
    null = np.asarray([x for x in null if x == x], float)
    mu, sd = (null.mean(), null.std()) if len(null) else (np.nan, np.nan)
    z = (obs - mu) / sd if sd and sd > 0 else np.nan
    return {"observed": float(obs), "null_mean": float(mu) if mu == mu else np.nan,
            "z": float(z) if z == z else np.nan, "n_perm": int(len(null))}


def day_shuffle_social_null(df: pd.DataFrame, y_col: str, social_features, *, base_numeric=(),
                            base_categorical=(), dwell_col="dwell_elapsed_s", animal_col="shortid",
                            strata_extra=("roi", "clock_hour"), n_perm=30, seed=0, l2=1.0) -> dict:
    """Day-shuffle null for the social increment: reassign each decision's social features from the
    SAME animal + ROI + clock-hour on a DIFFERENT night (permute within (animal, roi, clock_hour)
    strata, which span nights). Preserves the marginal social-by-state structure and the
    circadian/environmental drive; breaks the specific night's real-time co-presence. Surviving it
    = the particular night's social configuration predicts leaving (not shared arousal). Returns z."""
    obs = social_increment(df, y_col, base_numeric=base_numeric, base_categorical=base_categorical,
                           social_features=social_features, dwell_col=dwell_col, l2=l2)["delta_bits"].mean()
    rng = np.random.default_rng(seed)
    strata = df.groupby([animal_col] + list(strata_extra)).indices
    cols = [df.columns.get_loc(f) for f in social_features]
    null = []
    for _ in range(n_perm):
        dd = df.copy()
        for _, idx in strata.items():
            if len(idx) < 2:
                continue
            perm = rng.permutation(idx)
            for f, c in zip(social_features, cols):
                dd.iloc[idx, c] = df.iloc[perm][f].to_numpy()
        null.append(social_increment(dd, y_col, base_numeric=base_numeric, base_categorical=base_categorical,
                                     social_features=social_features, dwell_col=dwell_col, l2=l2)["delta_bits"].mean())
    null = np.asarray([x for x in null if x == x], float)
    mu, sd = (null.mean(), null.std()) if len(null) else (np.nan, np.nan)
    z = (obs - mu) / sd if sd and sd > 0 else np.nan
    return {"observed": float(obs), "null_mean": float(mu) if mu == mu else np.nan,
            "z": float(z) if z == z else np.nan, "n_perm": int(len(null))}


# ---------------------------------------------------------------------------
# matched-choice for nominally symmetric resources (destination process)
# ---------------------------------------------------------------------------

def matched_choice_stability(dest_df: pd.DataFrame, group_members, *, animal_col="shortid",
                             night_col="night", origin_col="origin", dest_col="dest",
                             min_per_night=3) -> pd.DataFrame:
    """For departures whose destination lies in a nominally symmetric group, test whether each
    animal shows a STABLE cross-night preference among the group members. Per animal: the
    per-night fraction choosing member[0] (vs the group), and cross-night consistency measured
    as held-out predictability = 1 - mean|f_heldnight - f_otherNights| (in [~0,1]); a value near
    the pooled base rate's consistency means no stable individual preference."""
    gm = list(group_members)
    ref = 1.0 / len(gm)                         # indifference: symmetric alternatives
    sub = dest_df[dest_df[dest_col].isin(gm)].copy()
    if sub.empty:
        return pd.DataFrame()
    sub["choose0"] = (sub[dest_col] == gm[0]).astype(int)
    rows = []
    for a, ga in sub.groupby(animal_col):
        byn = ga.groupby(night_col)["choose0"].agg(["mean", "size"])
        byn = byn[byn["size"] >= min_per_night]
        if len(byn) < 2:
            continue
        # leave-one-night-out: predict held night's fraction from the animal's OTHER nights
        errs = [abs(byn.loc[hn, "mean"] - byn.drop(index=hn)["mean"].mean()) for hn in byn.index]
        pref = float(byn["mean"].mean())
        rows.append({"animal": str(a), "n_nights": int(len(byn)),
                     "pref_member0": pref, "indifference_ref": ref,
                     "transfer_error": float(np.mean(errs)),
                     "base_error": float(np.mean([abs(byn.loc[hn, "mean"] - ref) for hn in byn.index])),
                     # a stable individual preference: consistent across nights (low transfer error)
                     # AND actually a preference (far from indifference) — measured against 1/|group|,
                     # NOT a cross-animal pooled rate (which would leak other animals' preferences).
                     "stable_pref": bool(abs(pref - ref) > 0.15 and np.mean(errs) < 0.15)})
    return pd.DataFrame(rows)
