r"""NREM -> REM transitions and recent sleep history (cohort 2026c): REM-anchored cycles, descriptive relations, and a
discrete-time competing-risks transition model (plan: implementation_plan/2026-10-06-sleep-rem-cycle-history.md).

The PI's "scheduling" idea is tested as a hypothesis: does recent sleep history predict when the next REM starts, and
does that dependence change with time of day? Descriptive relations, held-out predictive evidence and mechanism are kept
apart; nothing here is a mechanism.

Input: the 1-s states of `imu_remclean` (ephys/sleep_quant.py export; local copy states_1s/) + the reviewed session
table (sleep_review.py --merge). Inclusion = sleep_quant's rules (user `noise`, tag SF12_contact_failing, sessions
< 0.5 h, not scored; epochs after valid_until / the paddock end dropped) + EXTRA_EXCLUDE. Nothing is stitched across
sessions: a session boundary censors, a gap is never Wake.

Definitions (s = seconds; all within one session; REM bouts = maximal runs of state REM as scored):
  cycle k        REM bout k -> REM bout k+1.  REM_pre = length of bout k (missing if it touches the session start);
                 I = start(k+1) - end(k) (inter-REM interval); N, W = NREM, Wake seconds inside I (N + W = I);
                 REM_next = length of bout k+1 (censored if it touches the session end). After a session's last REM the
                 interval is right-censored (kept, flagged incomplete).
  S1 (Park)      wake runs <= 20 s inside I are counted into N (N_S1 = N + sum of those runs; W_S1 = I - N_S1).
  S2             sequential vs single: 2-component Gaussian mixture on ln N (complete light-phase cycles, N > 0);
                 threshold = the intersection of the weighted Gaussians between the two means.
  step           the person-period unit of the transition model: Delta = 10 s of an NREM bout. For an NREM bout of length L
                 starting at a, steps j = 0 .. ceil(L/10) - 1; the outcome of step j is 0 (still NREM after it), and the last
                 step carries the bout's end: 1 = enters REM, 2 = enters Wake; a bout cut by the session end is censored
                 (all its steps 0, no event). Only bouts after a REM bout of known length are at risk (history defined).
  covariates     known at the step start (no future information):
                   elapsed = 10 j (s in the current NREM bout); hour = local clock hour of the step (EDT);
                   tod = (sin, cos)(2 pi hour / 24); day = days since 09-01 (REM declines over days);
                   REM_pre = length of the last REM bout; N_prior = NREM s between that REM's end and the bout start;
                   W_cum = Wake s in the same span. (time since REM = N_prior + W_cum + elapsed is NOT a covariate.)
  M0             animal intercepts + tod + day + natural cubic spline of ln(elapsed + 5) (4 df)
  M1             M0 + ln REM_pre + ln(1 + N_prior) + ln(1 + W_cum)
  M2             M1 + (ln REM_pre, ln(1 + N_prior)) x (sin, cos)
                 all multinomial logit (softmax over stay / REM / Wake), near-unpenalised (C = 1e4), numeric
                 covariates z-scored on the training fold.
  held-out LL    mean over held-out steps of -ln p_model(observed outcome) (nats per step); Delta LL(M1 - M0) < 0 =
                 M1 predicts better. Also the REM-only binary log-loss and Brier score of p(REM).
  folds          leave one DATE out (all animals of that date together; light-phase steps never cross midnight);
                 95 % CI of Delta LL by bootstrap over dates (2 000 resamples, step-weighted).
  night transfer M0' / M1' = M0 / M1 without tod, trained on all light steps, tested on all dark steps.
  across animals per-animal M1 (no animal intercepts) -> sign of the REM-vs-stay history coefficients; leave-one-animal-
                 out Delta LL with a pooled intercept.

Usage: python ephys/sleep_cycles.py --cohort 2026c [--states <dir>] [--states-s3 <dir>]   |   --selftest
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DT = 10                                   # s per step of the transition model
MA_S = 20                                 # Park et al. 2021 micro-arousal limit (S1)
EXTRA_EXCLUDE = {("SF07", "2_20260905_093310.289"): "SW threshold failure, unresolved (user 2026-10-06)"}
FEMALE_RELEASE = pd.Timestamp("2026-09-11 19:40:00")
DAY0 = pd.Timestamp("2026-09-01")
W, N, R = 1, 3, 5


# ------------------------------------------------------------------ bouts, cycles, person-period rows (pure functions)
def bouts(state: np.ndarray) -> list[tuple[int, int, int]]:
    """Maximal runs: (state, start, end) with end exclusive, in epochs (1 s)."""
    if len(state) == 0:
        return []
    chg = np.flatnonzero(np.diff(state)) + 1
    st, en = np.r_[0, chg], np.r_[chg, len(state)]
    return [(int(state[a]), int(a), int(b)) for a, b in zip(st, en)]


def session_cycles(state: np.ndarray) -> list[dict]:
    """REM-anchored cycles of one session (see the module docstring). Offsets in epochs from the session start."""
    bl = bouts(state)
    rem = [(a, b) for s, a, b in bl if s == R]
    n = len(state)
    out = []
    for k, (a, b) in enumerate(rem):
        rem_pre = (b - a) if a > 0 else np.nan
        if k + 1 < len(rem):
            a2, b2 = rem[k + 1]
            seg = state[b:a2]
            n_s, w_s = int((seg == N).sum()), int((seg == W).sum())
            ma = sum(e - s for st_, s, e in bouts(seg) if st_ == W and e - s <= MA_S)
            out.append({"rem_start": a, "rem_end": b, "rem_pre_s": rem_pre, "interval_s": a2 - b, "nrem_s": n_s, "wake_s": w_s,
                        "nrem_s1_s": n_s + ma, "wake_s1_s": w_s - ma, "rem_next_s": (b2 - a2) if b2 < n else np.nan,
                        "complete": True})
        else:
            seg = state[b:]
            out.append({"rem_start": a, "rem_end": b, "rem_pre_s": rem_pre, "interval_s": n - b, "nrem_s": int((seg == N).sum()),
                        "wake_s": int((seg == W).sum()), "nrem_s1_s": np.nan, "wake_s1_s": np.nan, "rem_next_s": np.nan,
                        "complete": False})
    return out


def session_steps(state: np.ndarray) -> pd.DataFrame:
    """Person-period rows (Delta = DT s) for every NREM bout that follows a REM bout of known length."""
    bl = bouts(state)
    n = len(state)
    rows = []
    last_rem = None                                    # (start, end) of the last REM bout of known length
    for i, (s, a, b) in enumerate(bl):
        if s == R:
            last_rem = (a, b) if a > 0 else None
            continue
        if s != N or last_rem is None:
            continue
        span = state[last_rem[1]:a]
        n_prior, w_cum = int((span == N).sum()), int((span == W).sum())
        L = b - a
        J = int(math.ceil(L / DT))
        j = np.arange(J)
        y = np.zeros(J, np.int8)
        if b < n:                                      # the bout ended inside the session -> event in its last step
            y[-1] = 1 if bl[i + 1][0] == R else 2
        rows.append(pd.DataFrame({"t_off": a + DT * j, "elapsed": DT * j, "y": y, "rem_pre": last_rem[1] - last_rem[0],
                                  "n_prior": n_prior, "w_cum": w_cum, "bout_start": a}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["t_off", "elapsed", "y", "rem_pre", "n_prior", "w_cum", "bout_start"])


# ------------------------------------------------------------------ data assembly
def included_sessions(cohort: str, review_csv: Path, states_dir: Path) -> pd.DataFrame:
    sys.path.insert(0, str(Path(__file__).parent))
    from sleep_quant import MIN_SESSION_H
    rv = pd.read_csv(review_csv)
    rv["start"] = pd.to_datetime(rv.start_local)
    reasons = []
    for r in rv.itertuples():
        tags = r.tags if isinstance(r.tags, str) else ""
        reasons.append("not scored" if not (states_dir / r.animal / f"{r.session}.states.npz").exists()
                       else EXTRA_EXCLUDE.get((r.animal, r.session), "") or ("noise (user)" if r.verdict == "noise" else "")
                       or ("SF12_contact_failing" if "SF12_contact_failing" in tags else "")
                       or (f"< {MIN_SESSION_H} h" if (r.duration_h or 0) < MIN_SESSION_H else ""))
    rv["excluded"] = reasons
    return rv


def probe_settle_windows(cohort: str) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    from _common import ephys_block
    out = []
    for m in ephys_block(cohort).get("probe_moves") or []:
        t = pd.Timestamp(m["time"])
        out.append((m["animal"], t, t + pd.Timedelta(hours=float(m.get("settle_h", 4)))))
    return out


def build_tables(cohort: str, rv: pd.DataFrame, states_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    sys.path.insert(0, str(Path(__file__).parent))
    from sleep_quant import PADDOCK_END, sun_times
    settle = probe_settle_windows(cohort)
    cyc, stp = [], []
    for r in rv[rv.excluded == ""].itertuples():
        with np.load(states_dir / r.animal / f"{r.session}.states.npz") as z:
            state = z["state"].astype(np.int8)
        t0 = r.start
        end = PADDOCK_END
        tags = r.tags if isinstance(r.tags, str) else ""
        for tag in tags.split(";"):
            if tag.startswith("valid_until "):
                end = min(end, pd.Timestamp(tag[len("valid_until "):]))
        n_ok = int(max(0, min(len(state), (end - t0).total_seconds())))
        state = state[:n_ok]                          # censor at valid_until / paddock end
        base = {"animal": r.animal, "session": r.session, "verdict": r.verdict,
                "shank1_degraded": "SF12_shank1_degraded" in tags}

        def stamp(df: pd.DataFrame, off_col: str) -> pd.DataFrame:
            t = t0 + pd.to_timedelta(df[off_col].astype(float), unit="s")
            df["t"] = t
            df["hour"] = t.dt.hour + t.dt.minute / 60 + t.dt.second / 3600
            df["date"] = t.dt.strftime("%Y-%m-%d")
            df["day"] = (t.dt.normalize() - DAY0).dt.days
            sun = {d: sun_times(pd.Timestamp(d).date()) for d in df["date"].unique()}
            sr = pd.to_datetime(df["date"].map(lambda d: sun[d][0]))
            ss = pd.to_datetime(df["date"].map(lambda d: sun[d][1]))
            df["light"] = (t >= sr) & (t < ss)
            ps = np.zeros(len(df), bool)
            for an, lo, hi in settle:
                if an == r.animal:
                    ps |= ((t >= lo) & (t < hi)).to_numpy()
            df["probe_settle"] = ps
            df["after_females"] = t >= FEMALE_RELEASE
            for k, v in base.items():
                df[k] = v
            return df
        c = pd.DataFrame(session_cycles(state))
        if len(c):
            cyc.append(stamp(c, "rem_end"))
        s = session_steps(state)
        if len(s):
            stp.append(stamp(s, "t_off"))
    return pd.concat(cyc, ignore_index=True), pd.concat(stp, ignore_index=True)


# ------------------------------------------------------------------ models
HIST = ["l_rem_pre", "l_n_prior", "l_w_cum"]


def features(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    f["sin"], f["cos"] = np.sin(2 * np.pi * df.hour / 24), np.cos(2 * np.pi * df.hour / 24)
    f["day"] = df.day.astype(float)
    f["l_elapsed"] = np.log(df.elapsed + 5.0)
    f["l_rem_pre"] = np.log(df.rem_pre.astype(float))
    f["l_n_prior"] = np.log1p(df.n_prior.astype(float))
    f["l_w_cum"] = np.log1p(df.w_cum.astype(float))
    return f


def design(f: pd.DataFrame, animals: pd.Series, model: str, fit_state: dict | None, animal_levels: list[str] | None,
           tod: bool = True, hist: list[str] | None = None) -> tuple[np.ndarray, dict]:
    """Design matrix for M0 / M1 / M2 (see docstring). fit_state carries the training fold's spline knots and z-scores."""
    from sklearn.preprocessing import SplineTransformer
    st = fit_state or {}
    if "spline" not in st:
        st["spline"] = SplineTransformer(n_knots=4, degree=3, include_bias=False).fit(f[["l_elapsed"]])
        cols = ["day"] + HIST
        st["mu"], st["sd"] = f[cols].mean(), f[cols].std().replace(0, 1)
    z = (f[["day"] + HIST] - st["mu"]) / st["sd"]
    parts = [st["spline"].transform(f[["l_elapsed"]]), z[["day"]].to_numpy()]
    if tod:
        parts.append(f[["sin", "cos"]].to_numpy())
    if model in ("M1", "M2"):
        parts.append(z[hist or HIST].to_numpy())
    if model == "M2":
        for h in ("l_rem_pre", "l_n_prior"):
            parts.append((z[h] * f["sin"]).to_numpy()[:, None])
            parts.append((z[h] * f["cos"]).to_numpy()[:, None])
    if animal_levels is not None:
        parts.append(pd.get_dummies(pd.Categorical(animals, categories=animal_levels), dtype=float).to_numpy()[:, 1:])
    return np.column_stack(parts), st


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, model: str, animal_fe: bool = True, tod: bool = True,
                hist: list[str] | None = None):
    from sklearn.linear_model import LogisticRegression
    lv = sorted(train.animal.unique()) if animal_fe else None
    Xtr, st = design(features(train), train.animal, model, None, lv, tod, hist)
    Xte, _ = design(features(test), test.animal, model, st, lv, tod, hist)
    m = LogisticRegression(C=1e4, max_iter=2000).fit(Xtr, train.y.to_numpy())
    p = np.full((len(test), 3), np.nan)
    p[:, m.classes_] = m.predict_proba(Xte)
    return p, m


def loglosses(p: np.ndarray, y: np.ndarray) -> dict:
    eps = 1e-12
    ll = -np.log(np.clip(p[np.arange(len(y)), y], eps, 1))
    pr = np.clip(p[:, 1], eps, 1 - eps)
    yr = (y == 1).astype(float)
    return {"ll": ll, "ll_rem": -(yr * np.log(pr) + (1 - yr) * np.log(1 - pr)), "brier_rem": (pr - yr) ** 2}


def boot_ci(per_fold: pd.DataFrame, col: str, n_boot: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Step-weighted mean of a per-fold difference and its 95 % bootstrap CI over folds (dates)."""
    rng = np.random.default_rng(seed)
    v, w = per_fold[col].to_numpy(), per_fold["n"].to_numpy()
    est = float(np.sum(v * w) / np.sum(w))
    b = []
    for _ in range(n_boot):
        i = rng.integers(0, len(v), len(v))
        b.append(np.sum(v[i] * w[i]) / np.sum(w[i]))
    lo, hi = np.percentile(b, [2.5, 97.5])
    return est, float(lo), float(hi)


def cv_dates(steps: pd.DataFrame, models=("M0", "M1", "M2"), specs: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Leave-one-date-out on light-phase steps. Returns per-fold metrics and the held-out predictions of p(REM).
    specs = {label: (base model, history subset)} replaces `models` (ablations)."""
    specs = specs or {m: (m, None) for m in models}
    rows, preds = [], []
    for d in sorted(steps.date.unique()):
        tr, te = steps[steps.date != d], steps[steps.date == d]
        if te.y.eq(1).sum() == 0 or te.animal.nunique() == 0:
            continue
        te = te[te.animal.isin(tr.animal.unique())]
        r = {"date": d, "n": len(te), "n_rem_events": int((te.y == 1).sum())}
        for mdl, (base, hist) in specs.items():
            p, _ = fit_predict(tr, te, base, hist=hist)
            L = loglosses(p, te.y.to_numpy())
            r.update({f"ll_{mdl}": L["ll"].mean(), f"llrem_{mdl}": L["ll_rem"].mean(), f"brier_{mdl}": L["brier_rem"].mean()})
            preds.append(pd.DataFrame({"date": d, "model": mdl, "p_rem": p[:, 1], "y_rem": (te.y.to_numpy() == 1).astype(int)}))
        rows.append(r)
    return pd.DataFrame(rows), pd.concat(preds, ignore_index=True)


# ------------------------------------------------------------------ selftest
def selftest() -> None:
    s = np.array([N] * 30 + [R] * 20 + [N] * 40 + [W] * 15 + [N] * 25 + [R] * 12 + [N] * 7 + [W] * 5 + [R] * 9 + [N] * 18, np.int8)
    c = session_cycles(s)
    assert len(c) == 3 and c[0]["rem_pre_s"] == 20 and c[0]["interval_s"] == 80 and c[0]["nrem_s"] == 65 and c[0]["wake_s"] == 15
    assert c[0]["nrem_s1_s"] == 80 and c[0]["wake_s1_s"] == 0, c[0]          # the 15-s wake run is a micro-arousal (<= 20 s)
    assert c[0]["rem_next_s"] == 12 and c[1]["interval_s"] == 12 and c[1]["nrem_s"] == 7 and c[1]["wake_s"] == 5
    assert not c[2]["complete"] and c[2]["interval_s"] == 18 and np.isnan(c[2]["rem_next_s"])
    s2 = np.array([R] * 10 + [N] * 25 + [R] * 30 + [N] * 12, np.int8)          # session starts in REM -> REM_pre unknown
    c2 = session_cycles(s2)
    assert np.isnan(c2[0]["rem_pre_s"]) and c2[0]["rem_next_s"] == 30
    st = session_steps(s)
    # first NREM bout (before any REM) is not at risk; bout 2 (40 s) -> 4 steps, ends into Wake; bout 3 (25 s) -> 3 steps,
    # ends into REM with n_prior 40, w_cum 15; bout 4 (7 s) -> 1 step into Wake; last bout (18 s) censored -> 2 steps, no event
    b = st.groupby("bout_start")
    assert list(b.size()) == [4, 3, 1, 2], list(b.size())
    assert st[st.bout_start == 50].y.tolist() == [0, 0, 0, 2]
    assert st[st.bout_start == 105].y.tolist() == [0, 0, 1] and st[st.bout_start == 105].n_prior.iloc[0] == 40
    assert st[st.bout_start == 105].w_cum.iloc[0] == 15 and st[st.bout_start == 105].rem_pre.iloc[0] == 20
    assert st[st.bout_start == 142].y.tolist() == [2] and st[st.bout_start == 142].rem_pre.iloc[0] == 12
    assert st[st.bout_start == 163].y.tolist() == [0, 0] and st[st.bout_start == 163].rem_pre.iloc[0] == 9
    # no future information: covariates of a step never change if the rest of the session is altered after that step
    s_alt = s.copy()
    s_alt[120:] = W
    sa = session_steps(s_alt)
    keep = st[st.t_off + DT <= 120][["t_off", "rem_pre", "n_prior", "w_cum", "elapsed"]].reset_index(drop=True)
    keep2 = sa[sa.t_off.isin(keep.t_off)][["t_off", "rem_pre", "n_prior", "w_cum", "elapsed"]].reset_index(drop=True)
    assert keep.equals(keep2)
    # model plumbing on synthetic steps: a history effect is recovered (M1 beats M0 held-out)
    rng = np.random.default_rng(1)
    n = 6000
    df = pd.DataFrame({"hour": rng.uniform(7, 19, n), "day": rng.integers(0, 6, n), "elapsed": rng.integers(0, 30, n) * 10,
                       "rem_pre": rng.lognormal(3.8, 0.7, n), "n_prior": rng.lognormal(4, 1, n), "w_cum": rng.lognormal(2, 1, n),
                       "animal": rng.choice(["A", "B", "C"], n)})
    eta = -3 + 1.0 * (np.log1p(df.n_prior) - 4)
    pr = 1 / (1 + np.exp(-eta))
    u = rng.uniform(size=n)
    df["y"] = np.where(u < pr, 1, np.where(u < pr + 0.05, 2, 0))
    df["date"] = (df.index % 6).astype(str)
    folds, _ = cv_dates(df)
    assert (folds.ll_M1 < folds.ll_M0).mean() > 0.8, folds[["ll_M0", "ll_M1"]]
    print("selftest: 12 checks PASS (cycles, censoring, Park S1, truncated REM_pre, person-period, events, no leakage, model)")


# ------------------------------------------------------------------ main analysis
def coverage(rv: pd.DataFrame, states_dir: Path) -> pd.DataFrame:
    """Included recorded hours per animal x date x phase (same censoring as build_tables)."""
    from sleep_quant import PADDOCK_END, sun_times
    rows = []
    for r in rv[rv.excluded == ""].itertuples():
        with np.load(states_dir / r.animal / f"{r.session}.states.npz") as z:
            n = len(z["state"])
        end = PADDOCK_END
        tags = r.tags if isinstance(r.tags, str) else ""
        for tag in tags.split(";"):
            if tag.startswith("valid_until "):
                end = min(end, pd.Timestamp(tag[len("valid_until "):]))
        n = int(max(0, min(n, (end - r.start).total_seconds())))
        t = r.start + pd.to_timedelta(np.arange(0, n, 60), unit="s")          # 1-min resolution is enough here
        d = pd.DataFrame({"date": t.strftime("%Y-%m-%d"), "t": t})
        sun = {x: sun_times(pd.Timestamp(x).date()) for x in d.date.unique()}
        d["light"] = (d.t >= pd.to_datetime(d.date.map(lambda x: sun[x][0]))) & (d.t < pd.to_datetime(d.date.map(lambda x: sun[x][1])))
        g = d.groupby(["date", "light"]).size() / 60
        for (dt, lt), h in g.items():
            rows.append({"animal": r.animal, "date": dt, "phase": "light" if lt else "dark", "hours": h})
    return pd.DataFrame(rows).groupby(["animal", "date", "phase"], as_index=False).hours.sum()


def gmm_threshold(x: np.ndarray) -> float:
    """S2: intersection of a 2-component Gaussian mixture on x (= ln N) between the two means."""
    from sklearn.mixture import GaussianMixture
    g = GaussianMixture(2, random_state=0).fit(x.reshape(-1, 1))
    mu, sd, w = g.means_.ravel(), np.sqrt(g.covariances_.ravel()), g.weights_
    o = np.argsort(mu)
    mu, sd, w = mu[o], sd[o], w[o]
    grid = np.linspace(mu[0], mu[1], 2000)
    dens = [w[i] / sd[i] * np.exp(-0.5 * ((grid - mu[i]) / sd[i]) ** 2) for i in range(2)]
    return float(grid[np.argmin(np.abs(dens[0] - dens[1]))])


def describe(cyc: pd.DataFrame, x: str, y: str, logx: bool = True) -> dict:
    """Per-animal Spearman rho + pooled OLS of ln y on ln x with animal intercepts, SEs cluster-robust by date."""
    import statsmodels.formula.api as smf
    from scipy import stats
    d = cyc.dropna(subset=[x, y])
    d = d[(d[x] > 0)]
    out = {"n": len(d), "n_animals": d.animal.nunique()}
    rhos = {an: stats.spearmanr(g[x], g[y]).statistic for an, g in d.groupby("animal") if len(g) >= 20}
    out["rho_per_animal"] = {k: round(float(v), 3) for k, v in rhos.items()}
    out["n_pos"] = sum(v > 0 for v in rhos.values())
    dd = d.assign(lx=np.log(d[x]) if logx else d[x], ly=np.log1p(d[y]))
    if len(dd) > 30 and dd.date.nunique() > 2:
        m = smf.ols("ly ~ lx + C(animal)", dd).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(dd.date)[0]})
        out.update({"slope": round(float(m.params["lx"]), 4), "slope_lo": round(float(m.conf_int().loc["lx", 0]), 4),
                    "slope_hi": round(float(m.conf_int().loc["lx", 1]), 4), "p": float(m.pvalues["lx"])})
    return out


def run(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
    from _common import analysis_root, figure_dir, git_commit, report_dir, resolve_cohort, sibling_repo, utc_now_iso
    from output_paths import run_dir
    from sleep_quant import daily_weather, load_weather, save_fig, sun_times, md_table
    c = resolve_cohort(a.cohort)
    states = Path(a.states) if a.states else analysis_root(c) / "sleep_server" / "states_1s"
    rd, fd = report_dir(c), figure_dir(c)
    out = run_dir("sleep_cycles", c)
    rv = included_sessions(c, rd / f"ephys_spikes_sleep_review_{c}.csv", states)
    cyc, stp = build_tables(c, rv, states)
    cov = coverage(rv, states)
    cyc.to_csv(out / "cycles.csv.gz", index=False)
    stp.to_csv(out / "steps.csv.gz", index=False)
    cov.to_csv(rd / f"ephys_spikes_sleep_cycles_coverage_{c}.csv", index=False)
    rv[["animal", "session", "start_local", "duration_h", "verdict", "excluded"]].to_csv(out / "sessions.csv", index=False)
    print(f"cycles {len(cyc)} (complete {int(cyc.complete.sum())}), steps {len(stp)} -> {out}", flush=True)

    # ---------------- descriptive (complete cycles)
    cc = cyc[cyc.complete].copy()
    thr = gmm_threshold(np.log(cc[cc.light & (cc.nrem_s > 0)].nrem_s.to_numpy()))
    cc["single"] = cc.nrem_s >= math.exp(thr)
    desc = []
    for ph, sub in (("light", cc[cc.light]), ("dark", cc[~cc.light])):
        for name, x, y in (("R1 REM_pre -> N", "rem_pre_s", "nrem_s"), ("R2 REM_pre -> I", "rem_pre_s", "interval_s"),
                           ("R3 N -> REM_next", "nrem_s", "rem_next_s")):
            r = describe(sub, x, y)
            desc.append({"phase": ph, "relation": name, "variant": "main", **r})
    lt = cc[cc.light]
    flags_clean = lt[~lt.probe_settle & ~lt.shank1_degraded & ~lt.after_females & (lt.verdict != "bad")]
    for vname, sub, ycol in (("S1 Park micro-arousals -> N", lt, "nrem_s1_s"), ("S2 single cycles only", lt[lt.single], "nrem_s"),
                             ("flags excluded (probe settle, shank1, females, bad)", flags_clean, "nrem_s")):
        desc.append({"phase": "light", "relation": "R1 REM_pre -> N", "variant": vname, **describe(sub, "rem_pre_s", ycol)})
    if a.states_s3:
        rv3 = included_sessions(c, rd / f"ephys_spikes_sleep_review_{c}.csv", Path(a.states_s3))
        cyc3, stp3 = build_tables(c, rv3, Path(a.states_s3))
        c3 = cyc3[cyc3.complete & cyc3.light]
        desc.append({"phase": "light", "relation": "R1 REM_pre -> N", "variant": "S3 imu_nremgate states", **describe(c3, "rem_pre_s", "nrem_s")})
    desc = pd.DataFrame(desc)
    desc.to_csv(rd / f"ephys_spikes_sleep_cycles_descriptive_{c}.csv", index=False)

    # ---------------- transition model, light phase: leave-one-date-out
    sl, sd_ = stp[stp.light].reset_index(drop=True), stp[~stp.light].reset_index(drop=True)
    folds, preds = cv_dates(sl)
    folds["d_M1_M0"], folds["d_M2_M1"] = folds.ll_M1 - folds.ll_M0, folds.ll_M2 - folds.ll_M1
    folds["drem_M1_M0"], folds["drem_M2_M1"] = folds.llrem_M1 - folds.llrem_M0, folds.llrem_M2 - folds.llrem_M1
    folds.to_csv(rd / f"ephys_spikes_sleep_cycles_cv_{c}.csv", index=False)
    preds.to_csv(out / "cv_predictions.csv.gz", index=False)
    cmp_rows = []
    for col, lab in (("d_M1_M0", "M1 - M0, all outcomes"), ("d_M2_M1", "M2 - M1, all outcomes"),
                     ("drem_M1_M0", "M1 - M0, REM outcome"), ("drem_M2_M1", "M2 - M1, REM outcome")):
        est, lo, hi = boot_ci(folds, col)
        cmp_rows.append({"comparison": lab, "delta_ll_nats_per_step": est, "ci_lo": lo, "ci_hi": hi,
                         "folds_better": int((folds[col] < 0).sum()), "folds": len(folds)})
    # single-cycle regime only (time since REM >= the S2 threshold)
    tsr = sl.n_prior + sl.w_cum + sl.elapsed
    f_single, _ = cv_dates(sl[tsr >= math.exp(thr)], models=("M0", "M1"))
    f_single["d"] = f_single.ll_M1 - f_single.ll_M0
    est, lo, hi = boot_ci(f_single, "d")
    cmp_rows.append({"comparison": "M1 - M0, steps >= S2 threshold after REM", "delta_ll_nats_per_step": est, "ci_lo": lo, "ci_hi": hi,
                     "folds_better": int((f_single.d < 0).sum()), "folds": len(f_single)})
    # leave one animal out (pooled intercept)
    loao = []
    for an in sorted(sl.animal.unique()):
        tr, te = sl[sl.animal != an], sl[sl.animal == an]
        L = {m: loglosses(fit_predict(tr, te, m, animal_fe=False)[0], te.y.to_numpy())["ll"].mean() for m in ("M0", "M1")}
        loao.append({"animal": an, "n": len(te), "d_M1_M0": L["M1"] - L["M0"]})
    loao = pd.DataFrame(loao)
    # night transfer (no time-of-day terms)
    pn0, _ = fit_predict(sl, sd_, "M0", tod=False)
    pn1, _ = fit_predict(sl, sd_, "M1", tod=False)
    Ln0, Ln1 = loglosses(pn0, sd_.y.to_numpy()), loglosses(pn1, sd_.y.to_numpy())
    night = pd.DataFrame({"date": sd_.date, "ll0": Ln0["ll"], "ll1": Ln1["ll"], "lr0": Ln0["ll_rem"], "lr1": Ln1["ll_rem"]})
    nf = night.groupby("date").agg(n=("ll0", "size"), ll0=("ll0", "mean"), ll1=("ll1", "mean"), lr0=("lr0", "mean"), lr1=("lr1", "mean"))
    nf["d"], nf["dr"] = nf.ll1 - nf.ll0, nf.lr1 - nf.lr0
    for col, lab in (("d", "night transfer M1' - M0', all outcomes"), ("dr", "night transfer M1' - M0', REM outcome")):
        est, lo, hi = boot_ci(nf.reset_index(), col)
        cmp_rows.append({"comparison": lab, "delta_ll_nats_per_step": est, "ci_lo": lo, "ci_hi": hi,
                         "folds_better": int((nf[col] < 0).sum()), "folds": len(nf)})
    # weather, secondary: day-level weather added to M1 (held-out by date)
    wd = daily_weather(load_weather(sibling_repo("field2026-sync")))
    wz = ((wd[["temp_C", "rh_pct", "rain_mm"]] - wd[["temp_C", "rh_pct", "rain_mm"]].mean()) / wd[["temp_C", "rh_pct", "rain_mm"]].std())
    wz.index = [str(i) for i in wz.index]
    wrows = []
    for d in sorted(sl.date.unique()):
        tr, te = sl[sl.date != d], sl[sl.date == d]
        if (te.y == 1).sum() == 0 or d not in wz.index:
            continue
        p1, _ = fit_predict(tr, te, "M1")
        from sklearn.linear_model import LogisticRegression
        lv = sorted(tr.animal.unique())
        Xtr, st_ = design(features(tr), tr.animal, "M1", None, lv)
        Xte, _ = design(features(te), te.animal, "M1", st_, lv)
        Xtr = np.column_stack([Xtr, wz.loc[tr.date].to_numpy()])
        Xte = np.column_stack([Xte, wz.loc[te.date].to_numpy()])
        mw = LogisticRegression(C=1e4, max_iter=2000).fit(Xtr, tr.y.to_numpy())
        pw = np.full((len(te), 3), np.nan)
        pw[:, mw.classes_] = mw.predict_proba(Xte)
        wrows.append({"date": d, "n": len(te), "d": loglosses(pw, te.y.to_numpy())["ll"].mean() - loglosses(p1, te.y.to_numpy())["ll"].mean()})
    wf = pd.DataFrame(wrows)
    est, lo, hi = boot_ci(wf, "d")
    cmp_rows.append({"comparison": "M1 + day weather - M1 (secondary)", "delta_ll_nats_per_step": est, "ci_lo": lo, "ci_hi": hi,
                     "folds_better": int((wf.d < 0).sum()), "folds": len(wf)})
    # ablations: which history term carries the prediction (each alone on top of M0, light, leave-one-date-out)
    specs = {"M0": ("M0", None), "REM_pre": ("M1", ["l_rem_pre"]), "N_prior": ("M1", ["l_n_prior"]), "W_cum": ("M1", ["l_w_cum"]),
             "REM_pre+N_prior": ("M1", ["l_rem_pre", "l_n_prior"])}
    fa, _ = cv_dates(sl, specs=specs)
    for name in list(specs)[1:]:
        fa[f"d_{name}"] = fa[f"ll_{name}"] - fa.ll_M0
        est, lo, hi = boot_ci(fa, f"d_{name}")
        cmp_rows.append({"comparison": f"ablation, M0 + {name} vs M0", "delta_ll_nats_per_step": est, "ci_lo": lo, "ci_hi": hi,
                         "folds_better": int((fa[f"d_{name}"] < 0).sum()), "folds": len(fa)})
    # night transfer without the wake term (W_cum could stand in for 'night = more wake')
    pnr, _ = fit_predict(sl, sd_, "M1", tod=False, hist=["l_rem_pre", "l_n_prior"])
    night["llr"] = loglosses(pnr, sd_.y.to_numpy())["ll"]
    nf2 = night.groupby("date").agg(n=("ll0", "size"), ll0=("ll0", "mean"), llr=("llr", "mean"))
    nf2["d"] = nf2.llr - nf2.ll0
    est, lo, hi = boot_ci(nf2.reset_index(), "d")
    cmp_rows.append({"comparison": "night transfer, M0' + REM_pre + N_prior vs M0' (no wake term)", "delta_ll_nats_per_step": est,
                     "ci_lo": lo, "ci_hi": hi, "folds_better": int((nf2.d < 0).sum()), "folds": len(nf2)})
    # S3: the same M1 vs M0 test on the scorer's states before the REM post-rules
    if a.states_s3:
        f3, _ = cv_dates(stp3[stp3.light].reset_index(drop=True), models=("M0", "M1"))
        f3["d"] = f3.ll_M1 - f3.ll_M0
        est, lo, hi = boot_ci(f3, "d")
        cmp_rows.append({"comparison": "S3 imu_nremgate states, M1 vs M0", "delta_ll_nats_per_step": est, "ci_lo": lo, "ci_hi": hi,
                         "folds_better": int((f3.d < 0).sum()), "folds": len(f3)})
    cmp_ = pd.DataFrame(cmp_rows)
    base_ll = float((folds.ll_M0 * folds.n).sum() / folds.n.sum())
    cmp_["relative_to_M0_LL_pct"] = (100 * cmp_.delta_ll_nats_per_step / base_ll).round(2)
    cmp_.to_csv(rd / f"ephys_spikes_sleep_cycles_model_comparison_{c}.csv", index=False)

    # ---------------- full-data coefficients (direction / size; inference = held-out above)
    import statsmodels.api as sm
    lv = sorted(sl.animal.unique())
    coef_rows = []
    for mdl in ("M1", "M2"):
        X, st_m = design(features(sl), sl.animal, mdl, None, lv)
        nm = ([f"spline{i + 1}" for i in range(st_m["spline"].n_features_out_)] + ["day", "sin", "cos"] + HIST
              + (["l_rem_pre x sin", "l_rem_pre x cos", "l_n_prior x sin", "l_n_prior x cos"] if mdl == "M2" else [])
              + [f"animal_{x}" for x in lv[1:]])
        assert len(nm) == X.shape[1], (len(nm), X.shape)
        Xs = sm.add_constant(pd.DataFrame(X, columns=nm))
        try:
            fit = sm.MNLogit(sl.y.to_numpy(), Xs).fit(method="lbfgs", maxiter=3000, disp=False, cov_type="cluster",
                                                      cov_kwds={"groups": pd.factorize(sl.date)[0]})
            se_kind = "cluster(date)"
        except Exception as e:  # noqa: BLE001
            fit = sm.MNLogit(sl.y.to_numpy(), Xs).fit(method="lbfgs", maxiter=3000, disp=False)
            se_kind = f"model-based ({type(e).__name__})"
        for j, outcome in enumerate(("REM vs stay", "Wake vs stay")):
            for term in [t for t in Xs.columns if t in HIST or " x " in t]:
                coef_rows.append({"model": mdl, "outcome": outcome, "term": term, "coef_per_SD": fit.params.iloc[:, j][term],
                                  "se": fit.bse.iloc[:, j][term], "p": fit.pvalues.iloc[:, j][term], "se_kind": se_kind})
    coefs = pd.DataFrame(coef_rows)
    coefs.to_csv(rd / f"ephys_spikes_sleep_cycles_coefficients_{c}.csv", index=False)
    # per-animal M1: sign of the REM-vs-stay history coefficients
    from sklearn.linear_model import LogisticRegression
    pa = []
    for an, g in sl.groupby("animal"):
        X, _ = design(features(g), g.animal, "M1", None, None)
        m = LogisticRegression(C=1e4, max_iter=3000).fit(X, g.y.to_numpy())
        cls = list(m.classes_)
        if 1 not in cls:
            continue
        diff = m.coef_[cls.index(1)] - m.coef_[cls.index(0)]
        pa.append({"animal": an, "n_steps": len(g), "n_rem_events": int((g.y == 1).sum()),
                   **{f"{h}_REMvsStay": float(diff[-3 + i]) for i, h in enumerate(HIST)},
                   "d_M1_M0_loao": float(loao.set_index("animal").d_M1_M0.get(an, np.nan))})
    pa = pd.DataFrame(pa)
    pa.to_csv(rd / f"ephys_spikes_sleep_cycles_per_animal_{c}.csv", index=False)

    # ---------------- figures
    gc = git_commit()
    # (1) coverage
    fig, axes = plt.subplots(1, 2, figsize=(13, 3.6), sharey=True)
    for ax, ph in zip(axes, ("light", "dark")):
        pv = cov[cov.phase == ph].pivot(index="animal", columns="date", values="hours").fillna(0)
        im = ax.imshow(pv.to_numpy(), aspect="auto", cmap="viridis", vmin=0, vmax=13.5)
        ax.set_xticks(range(pv.shape[1]), [x[5:] for x in pv.columns], rotation=60, fontsize=7)
        ax.set_yticks(range(pv.shape[0]), pv.index)
        for i in range(pv.shape[0]):
            for j in range(pv.shape[1]):
                ax.text(j, i, f"{pv.iloc[i, j]:.0f}", ha="center", va="center", fontsize=6, color="w" if pv.iloc[i, j] < 7 else "k")
        ax.set_title(f"included hours, {ph} phase", fontsize=9)
    fig.colorbar(im, ax=axes, shrink=0.8, label="h")
    fig.suptitle(f"Sleep-cycle analysis coverage (imu_remclean, after exclusions; git {gc})", fontsize=9)
    f1 = save_fig(fig, fd / f"ephys_spikes_sleep_cycles_coverage_{c}.png")
    plt.close(fig)
    # (2) REM_pre vs N per animal, light vs dark
    ans = sorted(cc.animal.unique())
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.5), sharex=True, sharey=True)
    bins = np.quantile(np.log(cc.rem_pre_s.dropna()), np.linspace(0, 1, 9))
    for ax, an in zip(axes.ravel(), ans):
        g = cc[(cc.animal == an) & cc.rem_pre_s.notna()]
        for ph, col in ((True, "#e0a020"), (False, "#304060")):
            h = g[g.light == ph]
            ax.scatter(h.rem_pre_s, h.nrem_s + 1, s=4, alpha=0.25, color=col, label=f"{'light' if ph else 'dark'} (n={len(h)})")
            if len(h) >= 40:
                b = pd.cut(np.log(h.rem_pre_s), bins, include_lowest=True)
                med = h.groupby(b, observed=True).agg(x=("rem_pre_s", "median"), y=("nrem_s", "median"), n=("nrem_s", "size"))
                med = med[med.n >= 10]
                ax.plot(med.x, med.y + 1, "o-", color=col, lw=2, ms=4)
        rho = desc[(desc.phase == "light") & (desc.relation == "R1 REM_pre -> N") & (desc.variant == "main")].rho_per_animal.iloc[0].get(an)
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_title(f"{an}  (light Spearman rho = {rho})", fontsize=9)
        ax.legend(fontsize=7, loc="lower right")
    for ax in axes[1]:
        ax.set_xlabel("previous REM bout (s)")
    for ax in axes[:, 0]:
        ax.set_ylabel("NREM until the next REM + 1 (s)")
    fig.suptitle(f"R1: previous REM vs NREM in the following inter-REM interval (complete cycles; lines = binned medians; git {gc})", fontsize=9)
    fig.tight_layout()
    f2 = save_fig(fig, fd / f"ephys_spikes_sleep_cycles_rem_pre_vs_nrem_{c}.png")
    plt.close(fig)
    # (3) hazard map: M2 fitted on all light steps
    Xall, st_all = design(features(sl), sl.animal, "M2", None, lv)
    m2 = LogisticRegression(C=1e4, max_iter=3000).fit(Xall, sl.y.to_numpy())
    srs = [sun_times(pd.Timestamp(d).date()) for d in sorted(sl.date.unique())]
    sr_h = float(np.mean([s.hour + s.minute / 60 for s, _ in srs]))
    ss_h = float(np.mean([e.hour + e.minute / 60 for _, e in srs]))
    hours = np.linspace(math.floor(sr_h * 2) / 2, math.ceil(ss_h * 2) / 2, 53)
    nq = np.quantile(sl.n_prior, 0.95)
    ngrid = np.unique(np.r_[0, np.geomspace(10, max(20, nq), 40)])
    fixed = {"rem_pre": float(sl.rem_pre.median()), "w_cum": float(sl.w_cum.median()), "elapsed": float(sl.elapsed.median()),
             "day": float(sl.day.median())}
    H, NN = np.meshgrid(hours, ngrid)
    P = np.zeros_like(H)
    for an in lv:
        g = pd.DataFrame({"hour": H.ravel(), "n_prior": NN.ravel(), "animal": an, **{k: v for k, v in fixed.items()}})
        Xg, _ = design(features(g), g.animal, "M2", st_all, lv)
        P += m2.predict_proba(Xg)[:, list(m2.classes_).index(1)].reshape(H.shape) / len(lv)
    hb = np.digitize(sl.hour, np.arange(0, 25, 1)) - 1
    nb_edges = np.r_[-0.5, (ngrid[1:] + ngrid[:-1]) / 2, np.inf]
    supp = pd.crosstab(hb, np.digitize(sl.n_prior, nb_edges) - 1)
    mask = np.array([[supp.at[int(h), i] < 50 if (int(h) in supp.index and i in supp.columns) else True for h in hours]
                     for i in range(P.shape[0])])
    Pm = np.ma.array(P * 100, mask=mask)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [1.4, 1]})
    im = axes[0].pcolormesh(H, NN, Pm, shading="auto", cmap="magma")
    axes[0].set_yscale("symlog", linthresh=10)
    axes[0].axvline(sr_h, color="c", ls="--", lw=1); axes[0].axvline(ss_h, color="c", ls="--", lw=1)
    axes[0].set_xlabel("hour of day (EDT); dashed = mean sunrise / sunset")
    axes[0].set_ylabel("NREM since the last REM, before the current bout (s)")
    fig.colorbar(im, ax=axes[0], label="P(enter REM in the next 10 s), %")
    axes[0].set_title(f"M2, light phase; fixed: previous REM {fixed['rem_pre']:.0f} s, wake since REM {fixed['w_cum']:.0f} s, "
                      f"bout elapsed {fixed['elapsed']:.0f} s; grey = < 50 steps", fontsize=8)
    for hh, col in ((sr_h + 1.5, "#2a78b8"), ((sr_h + ss_h) / 2, "#3a9a4a"), (ss_h - 1.5, "#c0392b")):
        j = int(np.argmin(np.abs(hours - hh)))
        ok = ~mask[:, j]
        axes[1].plot(ngrid[ok], P[ok, j] * 100, color=col, lw=2, label=f"{hours[j]:.1f} h")
    axes[1].set_xscale("symlog", linthresh=10)
    axes[1].set_xlabel("NREM since the last REM, before the current bout (s)")
    axes[1].set_ylabel("P(enter REM in the next 10 s), %")
    axes[1].legend(fontsize=8, title="time of day")
    fig.suptitle(f"History x time of day (M2 fit on all light-phase steps; averaged over animals; git {gc})", fontsize=9)
    fig.tight_layout()
    f3 = save_fig(fig, fd / f"ephys_spikes_sleep_cycles_hazard_map_{c}.png")
    plt.close(fig)
    # (4) model comparison + calibration
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    x = np.arange(len(folds))
    axes[0].bar(x - 0.2, folds.d_M1_M0 * 1000, 0.4, label="M1 - M0")
    axes[0].bar(x + 0.2, folds.d_M2_M1 * 1000, 0.4, label="M2 - M1")
    axes[0].axhline(0, color="k", lw=0.8)
    axes[0].set_xticks(x, [d[5:] for d in folds.date], rotation=60, fontsize=7)
    axes[0].set_ylabel("held-out Delta log-loss (millinats / step); < 0 = better")
    axes[0].set_title("leave-one-date-out, light phase", fontsize=9)
    axes[0].legend(fontsize=8)
    cm = cmp_.copy()
    axes[1].errorbar(cm.delta_ll_nats_per_step * 1000, np.arange(len(cm)),
                     xerr=[(cm.delta_ll_nats_per_step - cm.ci_lo) * 1000, (cm.ci_hi - cm.delta_ll_nats_per_step) * 1000], fmt="o")
    axes[1].axvline(0, color="k", lw=0.8)
    axes[1].set_yticks(np.arange(len(cm)), cm.comparison, fontsize=7)
    axes[1].set_xlabel("Delta log-loss (millinats / step), 95 % CI over dates")
    for mdl, col in (("M0", "0.5"), ("M1", "#1f5fa8"), ("M2", "#c0392b")):
        pm = preds[preds.model == mdl]
        q = pd.qcut(pm.p_rem, 10, duplicates="drop")
        cal = pm.groupby(q, observed=True).agg(p=("p_rem", "mean"), o=("y_rem", "mean"))
        axes[2].plot(cal.p * 100, cal.o * 100, "o-", color=col, label=mdl)
    lim = axes[2].get_xlim()[1]
    axes[2].plot([0, lim], [0, lim], "k:", lw=0.8)
    axes[2].set_xlabel("predicted P(REM next 10 s), % (held-out deciles)")
    axes[2].set_ylabel("observed, %")
    axes[2].legend(fontsize=8)
    axes[2].set_title("calibration (held-out)", fontsize=9)
    fig.suptitle(f"M0 / M1 / M2 held-out comparison (git {gc})", fontsize=9)
    fig.tight_layout()
    f4 = save_fig(fig, fd / f"ephys_spikes_sleep_cycles_model_comparison_{c}.png")
    plt.close(fig)

    # ---------------- report
    def fmt_cmp(r):
        return (f"| {r.comparison} | {r.delta_ll_nats_per_step * 1000:+.2f} | [{r.ci_lo * 1000:+.2f}, {r.ci_hi * 1000:+.2f}] | "
                f"{r.relative_to_M0_LL_pct:+.2f} % | {r.folds_better}/{r.folds} |")
    d_tab = desc.assign(rho=desc.rho_per_animal.astype(str)).drop(columns=["rho_per_animal"])
    excl = rv.groupby("excluded").agg(sessions=("session", "size"), hours=("duration_h", "sum")).round(1).reset_index()
    excl["excluded"] = excl.excluded.replace("", "(included)")
    lines = [
        f"# NREM → REM transitions and recent sleep history, cohort {c}", "",
        f"`ephys/sleep_cycles.py` (git {gc}, {utc_now_iso()}). Plan: "
        "[implementation_plan/2026-10-06-sleep-rem-cycle-history.md](../../../../implementation_plan/2026-10-06-sleep-rem-cycle-history.md).",
        f"Bulk outputs: `{out}`. Definitions: the module docstring, summarised here.", "",
        "**Scope.**",
        "- States are `imu_remclean`, 1-s epochs. REM bouts as scored, no merging (user decision).",
        "- Models are fitted on the light phase; the dark-phase naps are the held-out transfer test.",
        "- Descriptive relations, predictive evidence and mechanism are kept apart. Nothing here shows a mechanism.", "",
        "## Data", "", *md_table(excl), "",
        f"- Complete cycles: {int(cyc.complete.sum())} ({int((cyc.complete & cyc.light).sum())} light, "
        f"{int((cyc.complete & ~cyc.light).sum())} dark); censored intervals: {int((~cyc.complete).sum())}.",
        f"- Model steps (Δ = {DT} s of NREM after a REM of known length): {len(sl)} light, {len(sd_)} dark.",
        f"- Events: light {int((sl.y == 1).sum())} → REM and {int((sl.y == 2).sum())} → Wake; "
        f"dark {int((sd_.y == 1).sum())} → REM and {int((sd_.y == 2).sum())} → Wake.",
        f"- Per animal × date × phase: `ephys_spikes_sleep_cycles_coverage_{c}.csv` and the coverage figure.", "",
        "## Descriptive relations (complete cycles)", "",
        "- **Per animal:** Spearman ρ, for animals with ≥ 20 cycles.",
        "- **Pooled:** $\\ln(1+y) = \\beta \\ln x + \\alpha_a$, with SEs cluster-robust by date.",
        "- `n_pos` = animals with ρ > 0.",
        f"- **S2 threshold** (2-Gaussian intersection on ln N, light): N = {math.exp(thr):.0f} s. "
        f"Cycles below it are 'sequential' ({(~cc[cc.light].single).mean():.0%} of the light cycles).", "",
        *md_table(d_tab[["phase", "relation", "variant", "n", "n_animals", "n_pos", "slope", "slope_lo", "slope_hi", "p", "rho"]].round(4)), "",
        "## Does history add predictive information? (held-out)", "",
        "**ΔLL** = held-out mean log-loss difference, in millinats per 10-s step; < 0 means the larger model predicts better. "
        "The CI is a bootstrap over dates. `folds better` = held-out dates on which the larger model is better.", "",
        f"Relative = ΔLL / the light-phase held-out log-loss of M0 ({float((folds.ll_M0 * folds.n).sum() / folds.n.sum()):.4f} nats / step).", "",
        "| Comparison | ΔLL (millinats / step) | 95 % CI | Relative to M0 | Folds better |", "|---|---|---|---|---|",
        *[fmt_cmp(r) for r in cmp_.itertuples()], "",
        "Per fold: `ephys_spikes_sleep_cycles_cv_" + c + ".csv`.", "",
        "**Leave one animal out** (pooled intercept), ΔLL M1 − M0 per animal (millinats / step): "
        + ", ".join(f"{r.animal} {r.d_M1_M0 * 1000:+.2f}" for r in loao.itertuples()) + ".", "",
        "## Direction of the history terms", "",
        "Full light-phase fit; coefficients are per SD of the covariate, on the log-odds of REM (or Wake) against staying in "
        "NREM in the next 10 s. Use them for direction and size only: the predictive claim rests on the held-out table "
        "above.", "",
        *md_table(coefs.round(4)), "",
        "Per-animal M1 (REM-vs-stay coefficient per SD, sign consistency):", "",
        *md_table(pa.round(4)), "",
        "## Figures",
        f"- `{f1.relative_to(rd.parent).as_posix()}`: coverage.",
        f"- `{f2.relative_to(rd.parent).as_posix()}`: R1 per animal, light vs dark.",
        f"- `{f3.relative_to(rd.parent).as_posix()}`: P(→ REM) over time of day × prior NREM (M2).",
        f"- `{f4.relative_to(rd.parent).as_posix()}`: M0 / M1 / M2 held-out comparison + calibration.", "",
        "## Limits that stay open",
        "- **Scoring structure.** The scorer smooths its metrics over 15 s and imposes a 6-s minimum bout. `imu_remclean` "
        "forbids REM after > 10 s of wake, so wake → REM is not testable.",
        "- **Per-session thresholds.** REM detection quality varies by session (see the review).",
        "- **History mixed with time.** REM declines over days (day index in M0). Probe advances and contact degradation "
        "are flags, and a sensitivity row drops them.",
        "- **Few units.** 6 animals and ~11 dates, so the M2 interactions have little support. The dark-phase "
        "time-of-day × history question is not answerable (too few cycles).",
        "- **Semi-natural light.** Sunrise and sunset, not a 12:12 lab cycle: Vivaldi 2005's 'lights-on + 1–4 h' maps only "
        "loosely onto sunrise.",
    ]
    rep = rd / f"ephys_spikes_sleep_cycles_{c}.md"
    rep.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (rd / f"run_manifest_sleep_cycles_{c}.json").write_text(json.dumps(
        {"run_dir": str(out), "driver": "ephys/sleep_cycles.py", "git_commit": gc, "written_utc": utc_now_iso(), "states": str(states),
         "states_s3": a.states_s3, "dt_s": DT, "ma_s": MA_S, "extra_exclude": {f"{k[0]}/{k[1]}": v for k, v in EXTRA_EXCLUDE.items()}},
        indent=2), encoding="utf-8")
    print(f"-> {rep}")
    print(cmp_.to_string())
    print(desc[["phase", "relation", "variant", "n", "n_pos", "slope", "slope_lo", "slope_hi", "p"]].to_string())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--states", default=None, help="1-s states of imu_remclean (default the local sleep_server copy)")
    ap.add_argument("--states-s3", default=None, help="1-s states of imu_nremgate for sensitivity S3 (optional)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    run(a)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    main()
