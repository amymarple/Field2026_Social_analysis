r"""NREM -> REM transitions and recent sleep history, v2 (plan: implementation_plan/2026-10-06-sleep-rem-cycle-history.md,
revision 2). Full 24 h, continuous records across file splits, history that does not need a REM anchor, day-half blocks.
v1 (ephys/sleep_cycles.py) stays as the record of the first run; this reuses its pure functions where they apply.

Definitions (s = seconds; epochs are 1 s):
  record        consecutive INCLUDED sessions of one animal joined when the gap between them is <= JOIN_S; the gap's
                epochs are state 0 = unknown (never counted as Wake, NREM or REM). A longer gap ends the record.
  cycle         REM bout k -> REM bout k+1 inside one record; complete if no unknown epoch lies inside it.
  step          10 s of an NREM bout (as v1). The bout's end: 1 = REM, 2 = Wake; ending into unknown or the record end =
                censored. Every NREM bout of a record is at risk (no REM anchor needed).
  history at the bout start a (known at every step of the bout; no future information):
    (a) anchor      has_anchor = a REM bout of known length lies earlier in the record; then REM_pre, N_prior, W_cum as v1
                    (else 0 and has_anchor = 0)
    (b) windows     for w in WINDOWS_MIN: rec_w = recorded s in [a - w, a) (outside the record = unrecorded),
                    c_w = rec_w / w (completeness); f_W,w, f_N,w = Wake, NREM s / rec_w (0 if rec_w = 0)
  time            phase = (sin, cos)(2 pi k h / 24), k = 1, 2, h = local clock hour at the step;
                  T = hours since RELEASE (natural cubic spline, 4 knots)
  M0  animal + phase + spline(T) + spline(ln(elapsed + 5))
  M1  M0 + (a) [ln REM_pre, ln(1 + N_prior), ln(1 + W_cum), has_anchor] + (b) [f_W, f_N, c per window]
  M2  M1 + (ln REM_pre, ln(1 + N_prior), ln(1 + W_cum), f_W,60) x (sin, cos)(2 pi h / 24)
  block         the day-half a record starts in: 'D' = 06:00-18:00 of date d, 'N' = 18:00 of d to 06:00 of d + 1. The
                battery rounds (~07:00-09:00, ~18:00-20:00) end records, so no record (cycle, history) crosses blocks.
  validation    leave one block out (all animals of the block together); forward chaining (train on earlier blocks, test
                the next) as a secondary extrapolation test; light-phase-only fit and the night subset as sensitivity.
  held-out LL   as v1 (nats per step); Delta LL < 0 = the larger model predicts better; 95 % CI by bootstrap over blocks.

Usage: python ephys/sleep_cycles_v2.py --cohort 2026c --states <states_1s dir> --review <review csv> [--tag pass2]
       python ephys/sleep_cycles_v2.py --selftest
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from sleep_cycles import boot_ci, bouts, loglosses  # noqa: E402

DT = 10
JOIN_S = 60
WINDOWS_MIN = (10, 60, 180)
RELEASE = pd.Timestamp("2026-08-30 19:00:00")
EXTRA_EXCLUDE: dict = {}
W, N, R = 1, 3, 5


# ------------------------------------------------------------------ records
def build_records(sessions: pd.DataFrame, states_dir: Path) -> list[dict]:
    """sessions: included rows (animal, session, start, end_cut). Returns records with a joined state array (0 = unknown)."""
    recs = []
    for an, g in sessions.sort_values("start").groupby("animal"):
        cur = None
        for r in g.itertuples():
            with np.load(states_dir / an / f"{r.session}.states.npz") as z:
                st = z["state"].astype(np.int8)
            n_ok = int(max(0, min(len(st), (r.end_cut - r.start).total_seconds())))
            st = st[:n_ok]
            if not len(st):
                continue
            if cur is not None:
                gap = (r.start - cur["end"]).total_seconds()
                if 0 <= gap <= JOIN_S:
                    cur["state"] = np.concatenate([cur["state"], np.zeros(int(round(gap)), np.int8), st])
                    cur["end"] = cur["start"] + pd.Timedelta(seconds=len(cur["state"]))
                    cur["sessions"].append(r.session)
                    continue
                recs.append(cur)
            cur = {"animal": an, "start": r.start, "end": r.start + pd.Timedelta(seconds=len(st)), "state": st, "sessions": [r.session]}
        if cur is not None:
            recs.append(cur)
    for i, rc in enumerate(recs):
        h = rc["start"].hour
        d = rc["start"].normalize() - (pd.Timedelta(days=1) if h < 6 else pd.Timedelta(0))
        rc["block"] = f"{d:%Y-%m-%d}{'D' if 6 <= h < 18 else 'N'}"
        rc["record_id"] = i
    return recs


def record_cycles(state: np.ndarray) -> list[dict]:
    """REM-anchored cycles inside one record; complete = both anchors present and no unknown epoch inside."""
    bl = bouts(state)
    rem = [(a, b) for s, a, b in bl if s == R]
    out = []
    for k in range(len(rem) - 1):
        (a, b), (a2, b2) = rem[k], rem[k + 1]
        seg = state[b:a2]
        before_ok = a > 0 and state[a - 1] != 0
        out.append({"rem_start": a, "rem_end": b, "rem_pre_s": (b - a) if before_ok else np.nan, "interval_s": a2 - b,
                    "nrem_s": int((seg == N).sum()), "wake_s": int((seg == W).sum()), "unknown_s": int((seg == 0).sum()),
                    "rem_next_s": (b2 - a2) if (b2 < len(state) and state[b2] != 0) else np.nan,
                    "complete": bool(before_ok and (seg != 0).all())})
    return out


def record_steps(state: np.ndarray) -> pd.DataFrame:
    """Person-period rows for every NREM bout of a record (history definitions in the module docstring)."""
    n = len(state)
    cw = np.r_[0, np.cumsum(state == W)]
    cn = np.r_[0, np.cumsum(state == N)]
    cr = np.r_[0, np.cumsum(state != 0)]
    bl = bouts(state)
    rows = []
    last_rem = None
    for i, (s, a, b) in enumerate(bl):
        if s == R:
            last_rem = (a, b) if (a > 0 and state[a - 1] != 0) else None
            continue
        if s == 0:
            last_rem = last_rem              # unknown epochs do not erase the anchor; they count as unrecorded
            continue
        if s != N:
            continue
        L = b - a
        J = int(math.ceil(L / DT))
        y = np.zeros(J, np.int8)
        if b < n and state[b] in (R, W):
            y[-1] = 1 if state[b] == R else 2
        row = {"t_off": a + DT * np.arange(J), "elapsed": DT * np.arange(J), "y": y, "bout_start": a}
        if last_rem is not None:
            row.update({"has_anchor": 1, "rem_pre": last_rem[1] - last_rem[0], "n_prior": int(cn[a] - cn[last_rem[1]]),
                        "w_cum": int(cw[a] - cw[last_rem[1]])})
        else:
            row.update({"has_anchor": 0, "rem_pre": 1, "n_prior": 0, "w_cum": 0})
        for w in WINDOWS_MIN:
            lo = max(0, a - 60 * w)
            rec_s = int(cr[a] - cr[lo])
            row[f"c{w}"] = rec_s / (60 * w)
            row[f"fW{w}"] = (cw[a] - cw[lo]) / rec_s if rec_s else 0.0
            row[f"fN{w}"] = (cn[a] - cn[lo]) / rec_s if rec_s else 0.0
        rows.append(pd.DataFrame(row))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


# ------------------------------------------------------------------ model
HIST_A = ["l_rem_pre", "l_n_prior", "l_w_cum", "has_anchor"]
HIST_B = [f"{k}{w}" for w in WINDOWS_MIN for k in ("fW", "fN", "c")]
INTER = ["l_rem_pre", "l_n_prior", "l_w_cum", "fW60"]


def features(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    for k in (1, 2):
        f[f"sin{k}"], f[f"cos{k}"] = np.sin(2 * np.pi * k * df.hour / 24), np.cos(2 * np.pi * k * df.hour / 24)
    f["T"] = df.T_h.astype(float)
    f["l_elapsed"] = np.log(df.elapsed + 5.0)
    f["l_rem_pre"] = np.log(df.rem_pre.astype(float)) * df.has_anchor
    f["l_n_prior"] = np.log1p(df.n_prior.astype(float))
    f["l_w_cum"] = np.log1p(df.w_cum.astype(float))
    f["has_anchor"] = df.has_anchor.astype(float)
    for c in HIST_B:
        f[c] = df[c].astype(float)
    return f


def design(f: pd.DataFrame, animals: pd.Series, model: str, st: dict | None, levels: list[str] | None,
           hist: list[str] | None = None, phase: bool = True) -> tuple[np.ndarray, dict]:
    from sklearn.preprocessing import SplineTransformer
    st = st or {}
    if "spl_e" not in st:
        st["spl_e"] = SplineTransformer(n_knots=4, degree=3, include_bias=False).fit(f[["l_elapsed"]])
        st["spl_T"] = SplineTransformer(n_knots=4, degree=3, include_bias=False).fit(f[["T"]])
        cols = HIST_A + HIST_B
        st["mu"], st["sd"] = f[cols].mean(), f[cols].std().replace(0, 1)
    z = (f[HIST_A + HIST_B] - st["mu"]) / st["sd"]
    parts = [st["spl_e"].transform(f[["l_elapsed"]]), st["spl_T"].transform(f[["T"]])]
    if phase:
        parts.append(f[["sin1", "cos1", "sin2", "cos2"]].to_numpy())
    if model in ("M1", "M2"):
        parts.append(z[hist or (HIST_A + HIST_B)].to_numpy())
    if model == "M2":
        for h in INTER:
            parts += [(z[h] * f["sin1"]).to_numpy()[:, None], (z[h] * f["cos1"]).to_numpy()[:, None]]
    if levels is not None:
        parts.append(pd.get_dummies(pd.Categorical(animals, categories=levels), dtype=float).to_numpy()[:, 1:])
    return np.column_stack(parts), st


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, model: str, hist: list[str] | None = None, animal_fe: bool = True,
                phase: bool = True):
    from sklearn.linear_model import LogisticRegression
    lv = sorted(train.animal.unique()) if animal_fe else None
    Xtr, st = design(features(train), train.animal, model, None, lv, hist, phase)
    Xte, _ = design(features(test), test.animal, model, st, lv, hist, phase)
    m = LogisticRegression(C=1e4, max_iter=3000).fit(Xtr, train.y.to_numpy())
    p = np.full((len(test), 3), 1e-12)
    p[:, m.classes_] = m.predict_proba(Xte)
    return p / p.sum(1, keepdims=True), m


def cv_blocks(steps: pd.DataFrame, specs: dict) -> pd.DataFrame:
    """Leave one block out. specs = {label: (model, hist subset or None)}."""
    rows = []
    for blk in sorted(steps.block.unique()):
        tr, te = steps[steps.block != blk], steps[steps.block == blk]
        te = te[te.animal.isin(tr.animal.unique())]
        if (te.y == 1).sum() == 0:
            continue
        r = {"block": blk, "n": len(te), "n_rem": int((te.y == 1).sum())}
        for lab, (mdl, hist) in specs.items():
            p, _ = fit_predict(tr, te, mdl, hist)
            L = loglosses(p, te.y.to_numpy())
            r[f"ll_{lab}"], r[f"llrem_{lab}"] = L["ll"].mean(), L["ll_rem"].mean()
        rows.append(r)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ selftest
def selftest() -> None:
    # record joining: two sessions 30 s apart are joined with 30 unknown epochs; a 2-h gap starts a new record
    s1 = np.array([N] * 50 + [R] * 20 + [N] * 30, np.int8)
    s2 = np.array([N] * 40 + [R] * 15 + [W] * 25, np.int8)
    s3 = np.array([W] * 30 + [N] * 60, np.int8)
    tmp = Path(__file__).with_name("_selftest_states_v2")
    (tmp / "SFX").mkdir(parents=True, exist_ok=True)
    for name, s in (("a", s1), ("b", s2), ("c", s3)):
        np.savez(tmp / "SFX" / f"{name}.states.npz", state=s)
    t0 = pd.Timestamp("2026-09-01 08:00:00")
    ses = pd.DataFrame({"animal": "SFX", "session": ["a", "b", "c"],
                        "start": [t0, t0 + pd.Timedelta(seconds=130), t0 + pd.Timedelta(hours=3)]})
    ses["end_cut"] = ses.start + pd.Timedelta(hours=1)
    recs = build_records(ses, tmp)
    assert len(recs) == 2 and recs[0]["sessions"] == ["a", "b"] and len(recs[0]["state"]) == 100 + 30 + 80
    st = recs[0]["state"]
    assert (st[100:130] == 0).all() and recs[0]["block"] == "2026-09-01D" and recs[1]["block"] == "2026-09-01D"
    cyc = record_cycles(st)
    assert len(cyc) == 1 and cyc[0]["unknown_s"] == 30 and not cyc[0]["complete"] and cyc[0]["nrem_s"] == 70
    sp = record_steps(st)
    # bout 1 (0-50) no anchor -> has_anchor 0, ends into REM; bout 2 (70-100) ends into unknown -> censored;
    # bout 3 (130-170) has the anchor (REM 50-70), n_prior counts bout 2's 30 s, the unknown 30 s count as unrecorded
    b1, b2, b3 = (sp[sp.bout_start == k] for k in (0, 70, 130))
    assert b1.has_anchor.iloc[0] == 0 and b1.y.tolist() == [0, 0, 0, 0, 1]
    assert b2.y.sum() == 0 and len(b2) == 3
    assert b3.has_anchor.iloc[0] == 1 and b3.rem_pre.iloc[0] == 20 and b3.n_prior.iloc[0] == 30 and b3.w_cum.iloc[0] == 0
    assert b3.y.tolist() == [0, 0, 0, 1]
    assert abs(b3.c10.iloc[0] - 100 / 600) < 1e-9 and abs(b3.fN10.iloc[0] - 80 / 100) < 1e-9
    sp3 = record_steps(recs[1]["state"])
    assert sp3.has_anchor.iloc[0] == 0 and abs(sp3.fW10.iloc[0] - 1.0) < 1e-9 and sp3.y.sum() == 0      # censored at record end
    for f in (tmp / "SFX").glob("*.npz"):
        f.unlink()
    (tmp / "SFX").rmdir()
    tmp.rmdir()
    print("selftest v2: 14 checks PASS (joining, unknown gap, blocks, cycles with gaps, anchor-free steps, windows, censoring)")


# ------------------------------------------------------------------ run
def run(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
    from _common import figure_dir, git_commit, report_dir, resolve_cohort, utc_now_iso
    from output_paths import run_dir
    from sleep_quant import MIN_SESSION_H, PADDOCK_END, md_table, save_fig, sun_times
    c = resolve_cohort(a.cohort)
    rd, fd = report_dir(c), figure_dir(c)
    tag = a.tag
    out = run_dir(f"sleep_cycles_v2_{tag}", c)
    states_dir = Path(a.states)
    rv = pd.read_csv(a.review)
    rv["start"] = pd.to_datetime(rv.start_local)
    excl = []
    for r in rv.itertuples():
        tags = r.tags if isinstance(r.tags, str) else ""
        excl.append("not scored" if not (states_dir / r.animal / f"{r.session}.states.npz").exists()
                    else EXTRA_EXCLUDE.get((r.animal, r.session), "") or ("noise (user)" if r.verdict == "noise" else "")
                    or ("SF12_contact_failing" if "SF12_contact_failing" in tags else "")
                    or (f"< {MIN_SESSION_H} h" if (r.duration_h or 0) < MIN_SESSION_H else ""))
    rv["excluded"] = excl
    end_cut = []
    for r in rv.itertuples():
        e = PADDOCK_END
        for t in (r.tags if isinstance(r.tags, str) else "").split(";"):
            if t.startswith("valid_until "):
                e = min(e, pd.Timestamp(t[len("valid_until "):]))
        end_cut.append(e)
    rv["end_cut"] = end_cut
    recs = build_records(rv[rv.excluded == ""], states_dir)

    def stamp(df: pd.DataFrame, rc: dict, off: str) -> pd.DataFrame:
        t = rc["start"] + pd.to_timedelta(df[off].astype(float), unit="s")
        df["t"], df["hour"] = t, t.dt.hour + t.dt.minute / 60 + t.dt.second / 3600
        df["T_h"] = (t - RELEASE).dt.total_seconds() / 3600
        dates = t.dt.strftime("%Y-%m-%d")
        sun = {d: sun_times(pd.Timestamp(d).date()) for d in dates.unique()}
        df["light"] = (t >= pd.to_datetime(dates.map(lambda d: sun[d][0]))) & (t < pd.to_datetime(dates.map(lambda d: sun[d][1])))
        df["animal"], df["block"], df["record_id"] = rc["animal"], rc["block"], rc["record_id"]
        return df
    cyc, stp = [], []
    for rc in recs:
        cc = pd.DataFrame(record_cycles(rc["state"]))
        if len(cc):
            cyc.append(stamp(cc, rc, "rem_end"))
        ss_ = record_steps(rc["state"])
        if len(ss_):
            stp.append(stamp(ss_, rc, "t_off"))
    cyc, stp = pd.concat(cyc, ignore_index=True), pd.concat(stp, ignore_index=True)
    rec_tab = pd.DataFrame([{"record_id": r["record_id"], "animal": r["animal"], "block": r["block"], "start": r["start"], "hours": len(r["state"]) / 3600,
                             "n_sessions": len(r["sessions"]), "unknown_s": int((r["state"] == 0).sum())} for r in recs])
    rec_tab.to_csv(out / "records.csv", index=False)
    cyc.to_csv(out / "cycles.csv.gz", index=False)
    stp.to_csv(out / "steps.csv.gz", index=False)
    print(f"records {len(recs)} ({int((rec_tab.n_sessions > 1).sum())} joined), cycles {len(cyc)} (complete {int(cyc.complete.sum())}), "
          f"steps {len(stp)} ({int((stp.has_anchor == 0).sum())} without a REM anchor) -> {out}", flush=True)

    # ---------------- held-out comparisons (24 h; leave one block out)
    specs = {"M0": ("M0", None), "M1": ("M1", None), "M2": ("M2", None),
             "A_only": ("M1", HIST_A), "B_only": ("M1", HIST_B),
             "W_cum": ("M1", ["l_w_cum", "has_anchor"]), "N_prior": ("M1", ["l_n_prior", "has_anchor"]),
             "REM_pre": ("M1", ["l_rem_pre", "has_anchor"])}
    folds = cv_blocks(stp, specs)
    folds.to_csv(rd / f"ephys_spikes_sleep_cycles_v2_{tag}_cv_{c}.csv", index=False)
    base = float((folds.ll_M0 * folds.n).sum() / folds.n.sum())
    comp = []

    def add(label, a_, b_, fdf=folds, base_ll=base):
        fdf = fdf.copy()
        fdf["d"] = fdf[f"ll_{a_}"] - fdf[f"ll_{b_}"]
        est, lo, hi = boot_ci(fdf, "d")
        comp.append({"comparison": label, "delta_ll": est, "ci_lo": lo, "ci_hi": hi, "rel_pct": 100 * est / base_ll,
                     "folds_better": int((fdf.d < 0).sum()), "folds": len(fdf)})
    add("M1 vs M0 (24 h, leave one block out)", "M1", "M0")
    add("M2 vs M1 (history x phase)", "M2", "M1")
    for lab in ("A_only", "B_only", "W_cum", "N_prior", "REM_pre"):
        add(f"M0 + {lab} vs M0", lab, "M0")
    # night and light subsets of the held-out predictions
    for nm, msk in (("night steps", ~stp.light), ("light steps", stp.light)):
        sub = stp[msk]
        f2 = cv_blocks(sub, {"M0": ("M0", None), "M1": ("M1", None)})
        b2 = float((f2.ll_M0 * f2.n).sum() / f2.n.sum())
        add(f"M1 vs M0, fitted and tested on {nm} only", "M1", "M0", f2, b2)
    # forward chaining (train on all earlier blocks)
    blocks = sorted(stp.block.unique())
    fc = []
    for k in range(6, len(blocks)):
        tr, te = stp[stp.block.isin(blocks[:k])], stp[stp.block == blocks[k]]
        te = te[te.animal.isin(tr.animal.unique())]
        if (te.y == 1).sum() == 0:
            continue
        L = {m: loglosses(fit_predict(tr, te, m)[0], te.y.to_numpy())["ll"].mean() for m in ("M0", "M1")}
        fc.append({"block": blocks[k], "n": len(te), "ll_M1": L["M1"], "ll_M0": L["M0"]})
    fc = pd.DataFrame(fc)
    add("M1 vs M0, forward chaining (extrapolation)", "M1", "M0", fc, float((fc.ll_M0 * fc.n).sum() / fc.n.sum()))
    comp = pd.DataFrame(comp)
    comp.to_csv(rd / f"ephys_spikes_sleep_cycles_v2_{tag}_model_comparison_{c}.csv", index=False)

    # ---------------- coefficients of M1 / M2 (full data; direction only) + per animal
    import statsmodels.api as sm
    lv = sorted(stp.animal.unique())
    coef = []
    for mdl in ("M1", "M2"):
        X, st_ = design(features(stp), stp.animal, mdl, None, lv)
        names = ([f"spl_e{i}" for i in range(st_["spl_e"].n_features_out_)] + [f"spl_T{i}" for i in range(st_["spl_T"].n_features_out_)]
                 + ["sin1", "cos1", "sin2", "cos2"] + HIST_A + HIST_B
                 + ([f"{h} x {p}" for h in INTER for p in ("sin1", "cos1")] if mdl == "M2" else []) + [f"an_{x}" for x in lv[1:]])
        Xs = sm.add_constant(pd.DataFrame(X, columns=names))
        try:
            fit = sm.MNLogit(stp.y.to_numpy(), Xs).fit(method="lbfgs", maxiter=4000, disp=False, cov_type="cluster",
                                                      cov_kwds={"groups": pd.factorize(stp.block)[0]})
            kind = "cluster(block)"
        except Exception as e:  # noqa: BLE001
            fit = sm.MNLogit(stp.y.to_numpy(), Xs).fit(method="lbfgs", maxiter=4000, disp=False)
            kind = f"model-based ({type(e).__name__})"
        for j, outc in enumerate(("REM vs stay", "Wake vs stay")):
            for term in [t for t in Xs.columns if t in HIST_A + HIST_B or " x " in t]:
                coef.append({"model": mdl, "outcome": outc, "term": term, "coef_per_SD": fit.params.iloc[:, j][term],
                             "se": fit.bse.iloc[:, j][term], "p": fit.pvalues.iloc[:, j][term], "se_kind": kind})
    coef = pd.DataFrame(coef)
    coef.to_csv(rd / f"ephys_spikes_sleep_cycles_v2_{tag}_coefficients_{c}.csv", index=False)
    from sklearn.linear_model import LogisticRegression
    pa = []
    for an, g in stp.groupby("animal"):
        X, _ = design(features(g), g.animal, "M1", None, None)
        m = LogisticRegression(C=1e4, max_iter=3000).fit(X, g.y.to_numpy())
        cls = list(m.classes_)
        if 1 not in cls:
            continue
        dlt = m.coef_[cls.index(1)] - m.coef_[cls.index(0)]
        k0 = X.shape[1] - len(HIST_A + HIST_B)
        pa.append({"animal": an, "n_steps": len(g), "n_rem": int((g.y == 1).sum()),
                   **{f"{h}": float(dlt[k0 + i]) for i, h in enumerate(HIST_A + HIST_B)}})
    pa = pd.DataFrame(pa)
    pa.to_csv(rd / f"ephys_spikes_sleep_cycles_v2_{tag}_per_animal_{c}.csv", index=False)

    # ---------------- figures: P(-> REM) over 24 h phase x Wake fraction in the last 60 min (M2), support-masked
    gc = git_commit()
    Xall, st_all = design(features(stp), stp.animal, "M2", None, lv)
    m2 = LogisticRegression(C=1e4, max_iter=3000).fit(Xall, stp.y.to_numpy())
    hours = np.linspace(0, 24, 49)
    fw = np.linspace(0, 1, 21)
    H, FW = np.meshgrid(hours, fw)
    med = stp.median(numeric_only=True)
    P = np.zeros_like(H)
    for an in lv:
        g = pd.DataFrame({"hour": H.ravel() % 24, "fW60": FW.ravel(), "animal": an})
        for col in ("elapsed", "T_h", "rem_pre", "n_prior", "w_cum", "has_anchor", "c10", "fW10", "fN10", "c60", "fN60", "c180", "fW180", "fN180"):
            g[col] = med[col] if col != "has_anchor" else 1
        g["fN60"] = np.minimum(g.fN60, 1 - g.fW60)
        Xg, _ = design(features(g), g.animal, "M2", st_all, lv)
        P += m2.predict_proba(Xg)[:, list(m2.classes_).index(1)].reshape(H.shape) / len(lv)
    hb = np.clip(np.floor(stp.hour).astype(int), 0, 23)
    fb = np.clip(np.floor(stp.fW60 * 20).astype(int), 0, 19)
    supp = pd.crosstab(fb, hb)
    mask = np.array([[supp.at[min(19, int(f * 20)), min(23, int(h))] < 50 if (min(19, int(f * 20)) in supp.index and min(23, int(h)) in supp.columns) else True
                      for h in hours] for f in fw])
    srs = [sun_times(pd.Timestamp(d).date()) for d in sorted(stp.t.dt.strftime("%Y-%m-%d").unique())]
    sr_h = float(np.mean([s.hour + s.minute / 60 for s, _ in srs]))
    ss_h = float(np.mean([e.hour + e.minute / 60 for _, e in srs]))
    fig, ax = plt.subplots(1, 2, figsize=(14, 4.6), gridspec_kw={"width_ratios": [1.5, 1]})
    im = ax[0].pcolormesh(H, FW * 100, np.ma.array(P * 100, mask=mask), shading="auto", cmap="magma")
    for x in (sr_h, ss_h):
        ax[0].axvline(x, color="c", ls="--", lw=1)
    ax[0].set_xlabel("hour of day (EDT); dashed = mean sunrise / sunset")
    ax[0].set_ylabel("Wake in the last 60 min before the bout (% of recorded)")
    fig.colorbar(im, ax=ax[0], label="P(enter REM in the next 10 s), %")
    ax[0].set_title("M2 over 24 h; other covariates at their medians (anchor present); grey = < 50 steps", fontsize=8)
    for hh, col in ((sr_h + 2, "#2a78b8"), ((sr_h + ss_h) / 2, "#3a9a4a"), (ss_h + 3, "#5b3c99"), ((ss_h + 24 + sr_h) / 2 % 24, "#c0392b")):
        j = int(np.argmin(np.abs(hours - hh)))
        ok = ~mask[:, j]
        ax[1].plot(fw[ok] * 100, P[ok, j] * 100, color=col, lw=2, label=f"{hours[j]:.1f} h")
    ax[1].set_xlabel("Wake in the last 60 min (% of recorded)")
    ax[1].set_ylabel("P(enter REM in the next 10 s), %")
    ax[1].legend(fontsize=8, title="time of day")
    fig.suptitle(f"History x time of day over 24 h (v2, {tag}; git {gc})", fontsize=9)
    fig.tight_layout()
    f1 = save_fig(fig, fd / f"ephys_spikes_sleep_cycles_v2_{tag}_hazard_map_{c}.png")
    plt.close(fig)
    fig, axx = plt.subplots(figsize=(8, 4.5))
    axx.errorbar(comp.rel_pct, np.arange(len(comp)), xerr=[comp.rel_pct - 100 * comp.ci_lo / base, 100 * comp.ci_hi / base - comp.rel_pct], fmt="o")
    axx.axvline(0, color="k", lw=0.8)
    axx.set_yticks(np.arange(len(comp)), comp.comparison, fontsize=7)
    axx.set_xlabel("held-out change in log-loss vs the baseline (%), 95 % CI over blocks; < 0 = better")
    fig.suptitle(f"v2 model comparison ({tag}; git {gc})", fontsize=9)
    fig.tight_layout()
    f2 = save_fig(fig, fd / f"ephys_spikes_sleep_cycles_v2_{tag}_model_comparison_{c}.png")
    plt.close(fig)

    # ---------------- report
    lines = [f"# NREM → REM transitions and recent sleep history, v2 ({tag}), cohort {c}", "",
             f"`ephys/sleep_cycles_v2.py` (git {gc}, {utc_now_iso()}). States: `{states_dir}`. Review table: `{a.review}`. Bulk: `{out}`. "
             "Definitions: the module docstring.", "",
             "## Data",
             f"- **Records:** {len(recs)} continuous records; {int((rec_tab.n_sessions > 1).sum())} of them joined across file splits "
             f"of ≤ {JOIN_S} s, with {int(rec_tab.unknown_s.sum())} s marked unknown.",
             f"- **Cycles:** {len(cyc)}, of which {int(cyc.complete.sum())} complete.",
             f"- **Model steps:** {len(stp)} ({int(stp.light.sum())} light, {int((~stp.light).sum())} dark). "
             f"{int((stp.has_anchor == 0).sum())} of them have no REM anchor in the record: these were dropped in v1.",
             f"- **Events:** {int((stp.y == 1).sum())} → REM ({int(((stp.y == 1) & ~stp.light).sum())} in the dark phase); "
             f"{int((stp.y == 2).sum())} → Wake.",
             f"- **Blocks:** {stp.block.nunique()} day-halves.", "",
             "## Held-out comparison", "",
             f"Baseline log-loss of M0 (leave one block out, 24 h): {base:.4f} nats / step. Relative = ΔLL / the baseline of "
             "the same test set.", "",
             "| Comparison | ΔLL (millinats / step) | 95 % CI | Relative | Folds better |", "|---|---|---|---|---|",
             *[f"| {r.comparison} | {r.delta_ll * 1000:+.2f} | [{r.ci_lo * 1000:+.2f}, {r.ci_hi * 1000:+.2f}] | {r.rel_pct:+.2f} % | "
               f"{r.folds_better}/{r.folds} |" for r in comp.itertuples()], "",
             "## Direction of the history terms (full fit; per SD; log-odds against staying in NREM)", "",
             *md_table(coef.round(4)), "",
             "Per animal (M1, REM vs stay, per SD):", "", *md_table(pa.round(3)), "",
             "## Figures",
             f"- `{f1.relative_to(rd.parent).as_posix()}`",
             f"- `{f2.relative_to(rd.parent).as_posix()}`", ""]
    rep = rd / f"ephys_spikes_sleep_cycles_v2_{tag}_{c}.md"
    rep.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (rd / f"run_manifest_sleep_cycles_v2_{tag}_{c}.json").write_text(json.dumps(
        {"run_dir": str(out), "driver": "ephys/sleep_cycles_v2.py", "git_commit": gc, "states": str(states_dir), "review": a.review,
         "join_s": JOIN_S, "windows_min": WINDOWS_MIN, "written_utc": utc_now_iso()}, indent=2), encoding="utf-8")
    print(f"-> {rep}")
    print(comp.round(5).to_string())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--states", default=None)
    ap.add_argument("--review", default=None)
    ap.add_argument("--tag", default="pass2")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    run(a)


if __name__ == "__main__":
    main()
