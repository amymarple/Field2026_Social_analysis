r"""Phase 2 of the internal-schedule analysis (plan: implementation_plan/2026-10-07-sleep-internal-schedule.md, rev. 2 +
Amendment 1): carry-over of sleep history across wakes (curve 2), compensation (curve 3), and the corrected
refractoriness description. Called by `python ephys/sleep_schedule.py phase2 [--parts c2 b1 b1b c1 b2]`.

Definitions (FINAL 1-s states; field-PC time; 10-s NREM steps as Phase 1; forward chaining over day-half blocks):
  post-wake bout  an NREM bout whose previous bout is WAKE of length d (s); its history at the bout start:
                  N_pre = NREM s since the last REM (NREM time stops during the wake), W_pre = wake s since the last REM
                  BEFORE this wake (w_since - d), T = wall s since the last REM (includes d), REM_pre, has_anchor.
  B1 models       reset  R0 = L0 + [ln(1+d), fW10]
                  carry  C1 = R0 + spline ln(1+N_pre) + ln(1+W_pre) + [ln REM_pre, has_anchor]
                  update U  = C1 + (spline ln(1+N_pre), ln(1+W_pre), ln REM_pre) x z(ln(1+d))
                  clocks K_nrem = R0 + spline ln(1+N_pre) + [ln REM_pre, anchor];  K_wall = R0 + spline ln(1+T) + same
                  Carry-over curve = held-out log-loss change per wake-length bin (< 40 s, 40-120 s, 2-7 min, 7-30 min,
                  >= 30 min; Watson-2016 marks), from the same fits.
  B1b             every wake >= 7 min followed by NREM in its record: NREM content |N|_k (NREM + MAs < 40 s) before the
                  k-th REM after the wake, k = 1..3 (stop at a wake >= 7 min, an unknown epoch or the record end; only
                  cycles that reach REM are used); OLS ln|N|_k ~ ln d + ln(1+N_pre) + anchor + phase + animal, SEs
                  clustered by block.
  B2              records of an animal joined across the usable gaps (<= 180 min, >= 1 h recorded each side; Phase 0)
                  with the gap as unknown epochs. Post-gap bouts = NREM bouts after a gap >= 600 s and before the first
                  REM after it. Lean models (few events): R0g = L0 + [ln gap, morning]; C1g = R0g + [ln(1+N_pre),
                  ln REM_pre, anchor] (N_pre = NREM since the last REM before the gap). Leave-one-block-out with a
                  purge (the next block's post-gap rows are dropped from training: their history is the left-out block).
                  Battery rounds only (cause round_logged / round_inferred); probe moves and the one unhandled gap are
                  listed. B3 = the same on pass2med_remclean states (fixed per-animal thresholds).
  C1 compensation 10-min bins per animal (recorded s, REM s, NREM s, REM onsets). Baselines fitted leave-one-block-out on
                  animal + (sin, cos)(2 pi k h / 24), k = 1, 2 + linear day: REM and NREM share (binomial GLM,
                  var weights = recorded s), REM onset rate (Poisson GLM, offset ln recorded min), REM bout duration
                  (OLS on ln duration, smearing). Window A (3 h) then B (1 h / 3 h), >= 80 % recorded each:
                    debt_A = E[REM_A] - REM_A ;  payback_B = REM_B - E[REM_B]   (minutes; + slope = compensation)
                  and the same for NREM minutes, REM count and mean REM bout duration (s) in B. Within records (sliding
                  by 1 h) and across battery-round gaps (A = the 3 h before the gap, B = the first 1 h / 3 h after).
                  OLS with SEs clustered by block (of A); per-animal slope signs.
                  Run on both scorings (FINAL and pass2med_remclean, fixed per-animal thresholds; Amendment 1 follow-up):
                  within-record persistence under FINAL vanished under fixed thresholds (scoring artefact).
  C2              empirical hazard per 10-s NREM step of REM and of WAKE against the TOTAL NREM since the last REM at
                  that step (bout-start value + elapsed), per animal then averaged (model-free description); and one
                  held-out comparison: M2 (bout-start N_since) vs M2t (step-level N_since + elapsed).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from sleep_cycles import boot_ci, bouts, loglosses  # noqa: E402
from sleep_cycles_v2 import build_records  # noqa: E402
from sleep_schedule import (DT, JMAX, MA_LIMITS, N, R, RELEASE, ROOT, W, add_time, episode_units, feats,  # noqa: E402
                            included_sessions, record_steps_s, split_scores)

D_BINS = [0, 40, 120, 420, 1800, np.inf]
D_LABELS = ["< 40 s", "40-120 s", "2-7 min", "7-30 min", ">= 30 min"]
FIRST = 6


# ------------------------------------------------------------------ features / design
def feats2(df: pd.DataFrame) -> pd.DataFrame:
    f = feats(df)
    f["l_d"] = np.log1p(df.d_prev.astype(float))
    f["l_wpre"] = np.log1p(np.maximum(df.w_since.astype(float) - df.d_prev.astype(float), 0))
    f["l_nsince_t"] = np.log1p(df.n_since.astype(float) + df.elapsed.astype(float))
    f["l_gap"] = np.log1p(df.pg_gap_s.astype(float)) if "pg_gap_s" in df else 0.0
    f["morning"] = ((df.t_start.dt.hour >= 5) & (df.t_start.dt.hour < 11)).astype(float) if "t_start" in df else 0.0
    for c in EXTRA_COLS:                                   # optional per-step columns (Phase 2b / 3); 0 when absent
        f[c] = df[c].astype(float) if c in df else 0.0
    return f


EXTRA_COLS = ("dark", "w60", "frag60", "frag120", "z_sw_lag")


SPLINES = ("l_elapsed", "l_nsince", "l_tsince", "l_nsince_t")


def design2(f: pd.DataFrame, animals: pd.Series, terms: list[str], st: dict | None, levels: list[str]):
    from sklearn.preprocessing import SplineTransformer
    if st is None:
        st = {}
        for c in SPLINES:
            st[f"spl_{c}"] = SplineTransformer(n_knots=4, degree=3, include_bias=False).fit(f[[c]])
        zc = [c for c in f.columns if not c.startswith(("sin", "cos"))]
        st["mu"], st["sd"] = f[zc].mean(), f[zc].std().replace(0, 1)
    z = (f[st["mu"].index] - st["mu"]) / st["sd"]
    sp = lambda c: st[f"spl_{c}"].transform(f[[c]])  # noqa: E731
    parts = [sp("l_elapsed"), f[["sin1", "cos1", "sin2", "cos2"]].to_numpy(), z[["T_day"]].to_numpy()]
    for t in terms:
        if t == "L1":
            parts.append(z[["l_dprev", "prev_rem", "prev_unk", "fW10"]].to_numpy())
        elif t == "cur":
            parts.append(z[["l_d", "fW10"]].to_numpy())
        elif t == "nspl":
            parts.append(sp("l_nsince"))
        elif t == "tspl":
            parts.append(sp("l_tsince"))
        elif t == "ntspl":
            parts.append(sp("l_nsince_t"))
        elif t == "wpre":
            parts.append(z[["l_wpre"]].to_numpy())
        elif t == "wsince":
            parts.append(z[["l_wsince"]].to_numpy())
        elif t == "rem":
            parts.append(z[["l_rem_pre", "has_anchor"]].to_numpy())
        elif t == "upd":
            zd = z[["l_d"]].to_numpy()
            parts += [sp("l_nsince") * zd, z[["l_wpre"]].to_numpy() * zd, z[["l_rem_pre"]].to_numpy() * zd]
        elif t == "gap":
            parts.append(z[["l_gap", "morning"]].to_numpy())
        elif t == "nlin":
            parts.append(z[["l_nsince"]].to_numpy())
        elif t == "darkint":                             # history x dark phase (Phase 3 Q1b)
            dk = f[["dark"]].to_numpy()
            parts += [sp("l_nsince_t") * dk, z[["l_wsince"]].to_numpy() * dk, z[["l_rem_pre"]].to_numpy() * dk]
        elif t.startswith("col:"):                       # any extra column, z-scored
            parts.append(z[[t[4:]]].to_numpy())
        else:
            raise ValueError(t)
    parts.append(pd.get_dummies(pd.Categorical(animals, categories=levels), dtype=float).to_numpy()[:, 1:])
    return np.column_stack(parts), st


def fit2(train: pd.DataFrame, terms: list[str], levels: list[str]):
    from sklearn.linear_model import LogisticRegression
    X, st = design2(feats2(train), train.animal, terms, None, levels)
    return LogisticRegression(C=1e4, max_iter=3000).fit(X, train.y.to_numpy()), st


def pred2(m, st, df: pd.DataFrame, terms: list[str], levels: list[str]) -> np.ndarray:
    X, _ = design2(feats2(df), df.animal, terms, st, levels)
    p = np.full((len(df), 3), 1e-12)
    p[:, m.classes_] = m.predict_proba(X)
    return p / p.sum(1, keepdims=True)


def run_cv(steps: pd.DataFrame, specs: dict, folds: list[tuple[pd.Index, pd.Index]], bin_col: str | None = None,
           split_pairs: list[tuple[str, str]] = ()) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fit every spec per fold; per-step log-loss aggregated per fold, per (fold, bin), per (fold, animal); and the
    opportunity / timing split for the listed pairs on test bouts with an observed end."""
    F, FB, FA, SP = [], [], [], []
    for k, (tr_i, te_i) in enumerate(folds):
        tr, te = steps.loc[tr_i], steps.loc[te_i]
        te = te[te.animal.isin(tr.animal.unique())]
        if (te.y == 1).sum() == 0 or len(tr) == 0:
            continue
        lv = sorted(tr.animal.unique())
        LL, models = {}, {}
        for name, terms in specs.items():
            m, st = fit2(tr, terms, lv)
            models[name] = (m, st)
            LL[name] = loglosses(pred2(m, st, te, terms, lv), te.y.to_numpy())["ll"]
        blk = te.block.iloc[0] if te.block.nunique() == 1 else f"fold{k}"
        F.append({"fold": blk, "n": len(te), "n_rem": int((te.y == 1).sum()), **{f"ll_{n}": LL[n].mean() for n in specs}})
        if bin_col:
            for b, g in te.groupby(bin_col, observed=True):
                pos = te.index.get_indexer(g.index)
                FB.append({"fold": blk, "bin": b, "n": len(g), "n_rem": int((g.y == 1).sum()),
                           **{f"ll_{n}": LL[n][pos].mean() for n in specs}})
        for an, g in te.groupby("animal"):
            pos = te.index.get_indexer(g.index)
            FA.append({"fold": blk, "animal": an, "n": len(g), **{f"ll_{n}": LL[n][pos].mean() for n in specs}})
        if split_pairs:
            ends = te[te.y > 0]
            first = te.drop_duplicates(["record_id", "bout_start"]).set_index(["record_id", "bout_start"])
            keys = list(ends[["record_id", "bout_start"]].itertuples(index=False, name=None))
            ext = []
            for rid, bs in keys:
                row = first.loc[(rid, bs)]
                g = pd.DataFrame([row] * JMAX)
                g["elapsed"] = DT * np.arange(JMAX)
                g["t"] = row.t_start + pd.to_timedelta(g.elapsed, unit="s")
                g["hour"] = g.t.dt.hour + g.t.dt.minute / 60 + g.t.dt.second / 3600
                g["T_day"] = (g.t - RELEASE).dt.total_seconds() / 86400
                g["t_start"] = row.t_start
                ext.append(g)
            if ext:
                E = pd.concat(ext, ignore_index=True)
                E["t_start"] = pd.to_datetime(E.t_start)
                ends_k = ends.set_index(["record_id", "bout_start"])
                need = sorted({n for pr in split_pairs for n in pr})
                P = {n: pred2(*models[n], E, specs[n], lv).reshape(len(keys), JMAX, 3) for n in need}
                for b_i, (rid, bs) in enumerate(keys):
                    e = ends_k.loc[(rid, bs)]
                    j_end = int(e.elapsed // DT)
                    if j_end >= JMAX:
                        continue
                    for n in need:
                        SP.append({"fold": blk, "model": n, "rid": rid, "bs": bs, "type": int(e.y),
                                   "bin": e[bin_col] if bin_col else "", **split_scores(P[n][b_i], j_end, int(e.y))})
        print(f"  fold {blk}: n {len(te)}, " + ", ".join(f"{n} {LL[n].mean():.4f}" for n in specs), flush=True)
    return pd.DataFrame(F), pd.DataFrame(FB), pd.DataFrame(FA), pd.DataFrame(SP)


def compare(F: pd.DataFrame, FA: pd.DataFrame | None, lo: str, hi: str, label: str = "") -> dict:
    if F is None or len(F) < 2 or f"ll_{hi}" not in F:
        return {"comparison": f"{hi} vs {lo}", "subset": label, "n_steps": int(F.n.sum()) if F is not None and len(F) else 0}
    F = F.copy()
    F["d"] = F[f"ll_{hi}"] - F[f"ll_{lo}"]
    if len(F) < 2:
        return {"comparison": f"{hi} vs {lo}", "subset": label, "n_steps": int(F.n.sum()) if len(F) else 0}
    est, lo_, hi_ = boot_ci(F, "d")
    base = float(np.sum(F[f"ll_{lo}"] * F.n) / F.n.sum())
    r = {"comparison": f"{hi} vs {lo}", "subset": label, "n_steps": int(F.n.sum()), "n_rem": int(F.n_rem.sum()),
         "delta_pct": 100 * est / base, "ci_lo_pct": 100 * lo_ / base, "ci_hi_pct": 100 * hi_ / base,
         "folds_better": int((F.d < 0).sum()), "folds": len(F)}
    if FA is not None and len(FA):
        pa = FA.assign(d=FA[f"ll_{hi}"] - FA[f"ll_{lo}"]).groupby("animal").apply(
            lambda g: np.sum(g.d * g.n) / g.n.sum(), include_groups=False)
        r.update(animals_better=int((pa < 0).sum()), animals=len(pa), holds=bool(r["ci_hi_pct"] < 0 and (pa < 0).sum() >= 5))
    return r


def split_summary(SP: pd.DataFrame, pairs, by_bin: bool = False) -> pd.DataFrame:
    rows = []
    for lo, hi in pairs:
        A = SP[SP.model == lo].set_index(["fold", "rid", "bs"])
        B = SP[SP.model == hi].set_index(["fold", "rid", "bs"])
        j = A.join(B, lsuffix="_a", rsuffix="_b", how="inner")
        groups = [("all", j)] + ([(b, g) for b, g in j.groupby("bin_a")] if by_bin else [])
        for gl, jj0 in groups:
            for typ, lab in ((None, "all ends"), (1, "ends in REM"), (2, "ends in Wake")):
                jj = jj0 if typ is None else jj0[jj0.type_a == typ]
                if not len(jj):
                    continue
                rows.append({"comparison": f"{hi} vs {lo}", "wake_bin": gl, "bouts": lab, "n": len(jj),
                             "gain_total": float((jj.log_total_b - jj.log_total_a).mean()),
                             "gain_whether": float((jj.log_type_b - jj.log_type_a).mean()),
                             "gain_when": float((jj.log_timing_b - jj.log_timing_a).mean())})
    return pd.DataFrame(rows)


def forward_folds(steps: pd.DataFrame) -> list[tuple[pd.Index, pd.Index]]:
    blocks = sorted(steps.block.unique())
    return [(steps.index[steps.block.isin(blocks[:k])], steps.index[steps.block == blocks[k]]) for k in range(FIRST, len(blocks))]


# ------------------------------------------------------------------ data
def build_steps(recs: list[dict]) -> pd.DataFrame:
    parts = []
    for rc in recs:
        df = record_steps_s(rc["state"])
        if df.empty:
            continue
        df = add_time(df, rc["start"])
        df["animal"], df["record_id"] = rc["animal"], rc["record_id"]
        df["t_start"] = rc["start"] + pd.to_timedelta(df.bout_start.astype(float), unit="s")
        if "segments" in rc:                                      # joined timeline: block of the segment the bout is in
            seg = rc["segments"]
            ix = np.searchsorted(np.array([s[0] for s in seg]), df.bout_start.to_numpy(), side="right") - 1
            df["block"] = np.array([s[2] for s in seg])[ix]
        else:
            df["block"] = rc["block"]
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def join_timelines(recs: list[dict], gaps: pd.DataFrame) -> list[dict]:
    """Join consecutive records of an animal across usable battery-round gaps (unknown epochs in between)."""
    ok = gaps[gaps.usable & gaps.cause.isin(["round_logged", "round_inferred"])]
    okset = {(r.animal, pd.Timestamp(r.gap_start).floor("s")) for r in ok.itertuples()}
    out, rid = [], 10000
    for an in sorted({rc["animal"] for rc in recs}):
        rr = sorted([rc for rc in recs if rc["animal"] == an], key=lambda x: x["start"])
        cur = None
        for rc in rr:
            if cur is not None and (an, pd.Timestamp(cur["end"]).floor("s")) in okset:
                gap = int(round((rc["start"] - cur["end"]).total_seconds()))
                off = len(cur["state"]) + gap
                cur["state"] = np.concatenate([cur["state"], np.zeros(gap, np.int8), rc["state"]])
                cur["segments"].append((off, rc["record_id"], rc["block"]))
                cur["end"] = rc["end"]
                continue
            if cur is not None:
                out.append(cur)
            cur = {"animal": an, "start": rc["start"], "end": rc["end"], "state": rc["state"].copy(), "record_id": rid,
                   "segments": [(0, rc["record_id"], rc["block"])]}
            rid += 1
        out.append(cur)
    return out


# ------------------------------------------------------------------ compensation helpers
def bins10(recs: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, rb = [], []
    for rc in recs:
        st = rc["state"]
        for s, a, b in bouts(st):
            if s == R and a > 0 and st[a - 1] != 0 and b < len(st) and st[b] != 0:
                t = rc["start"] + pd.Timedelta(seconds=a)
                rb.append({"animal": rc["animal"], "block": rc["block"], "t": t, "dur_s": b - a})
        n = len(st) // 600
        for i in range(n):
            seg = st[600 * i:600 * (i + 1)]
            t = rc["start"] + pd.Timedelta(seconds=600 * i)
            on = int(np.sum((seg[1:] == R) & (seg[:-1] != R) & (seg[:-1] != 0)))
            rows.append({"animal": rc["animal"], "block": rc["block"], "record_id": rc["record_id"], "t": t,
                         "rec_s": int((seg != 0).sum()), "rem_s": int((seg == R).sum()), "nrem_s": int((seg == N).sum()),
                         "rem_on": on})
    B = pd.DataFrame(rows)
    B["hour"] = B.t.dt.hour + B.t.dt.minute / 60
    B["day"] = (B.t - RELEASE).dt.total_seconds() / 86400
    RB = pd.DataFrame(rb)
    RB["hour"] = RB.t.dt.hour + RB.t.dt.minute / 60
    RB["day"] = (RB.t - RELEASE).dt.total_seconds() / 86400
    return B, RB


def _X(df: pd.DataFrame, levels: list[str]) -> np.ndarray:
    import statsmodels.api as sm
    X = pd.DataFrame({f"{f}{k}": fn(2 * np.pi * k * df.hour / 24) for k in (1, 2) for f, fn in (("sin", np.sin), ("cos", np.cos))})
    X["day"] = df.day.to_numpy()
    X = pd.concat([X.reset_index(drop=True), pd.get_dummies(pd.Categorical(df.animal, categories=levels), dtype=float).iloc[:, 1:].reset_index(drop=True)], axis=1)
    return sm.add_constant(X, has_constant="add").to_numpy()


def baselines(B: pd.DataFrame, RB: pd.DataFrame) -> pd.DataFrame:
    """Leave-one-block-out expectations per 10-min bin: E REM s, E NREM s, E REM onsets, E mean REM duration (s)."""
    import statsmodels.api as sm
    levels = sorted(B.animal.unique())
    B = B.copy()
    for c in ("e_rem_s", "e_nrem_s", "e_rem_on", "e_rem_dur"):
        B[c] = np.nan
    Bk = B[B.rec_s > 0]
    for blk in sorted(B.block.unique()):
        tr, te = Bk[Bk.block != blk], B[B.block == blk]
        if not len(te):
            continue
        Xtr, Xte = _X(tr, levels), _X(te, levels)
        for col, ecol in (("rem_s", "e_rem_s"), ("nrem_s", "e_nrem_s")):
            g = sm.GLM(tr[col] / tr.rec_s, Xtr, family=sm.families.Binomial(), var_weights=tr.rec_s).fit()
            B.loc[te.index, ecol] = g.predict(Xte) * te.rec_s.to_numpy()
        g = sm.GLM(tr.rem_on, Xtr, family=sm.families.Poisson(), offset=np.log(tr.rec_s / 600)).fit()
        B.loc[te.index, "e_rem_on"] = g.predict(Xte, offset=np.log(np.maximum(te.rec_s, 1) / 600)) * (te.rec_s > 0)
        rtr = RB[RB.block != blk]
        o = sm.OLS(np.log(rtr.dur_s), _X(rtr, levels)).fit()
        smear = float(np.mean(np.exp(o.resid)))
        B.loc[te.index, "e_rem_dur"] = np.exp(o.predict(Xte)) * smear
    return B


def comp_windows(B: pd.DataFrame, RB: pd.DataFrame, gaps: pd.DataFrame) -> pd.DataFrame:
    """Window pairs A (3 h) -> B (1 h / 3 h): within records (start every hour) and across battery-round gaps."""
    rows = []
    Bi = B.set_index("t").sort_index()

    def agg(an: str, t0: pd.Timestamp, t1: pd.Timestamp) -> dict | None:
        g = Bi[(Bi.animal == an)].loc[t0:t1 - pd.Timedelta(seconds=1)]
        if not len(g):
            return None
        rec = g.rec_s.sum()
        if rec < 0.8 * (t1 - t0).total_seconds():
            return None
        rb = RB[(RB.animal == an) & (RB.t >= t0) & (RB.t < t1)]
        e_dur = float(np.average(g.e_rem_dur, weights=np.maximum(g.e_rem_on, 1e-9))) if g.e_rem_on.sum() > 0 else np.nan
        return {"rem_min": g.rem_s.sum() / 60, "e_rem_min": g.e_rem_s.sum() / 60, "nrem_min": g.nrem_s.sum() / 60,
                "e_nrem_min": g.e_nrem_s.sum() / 60, "rem_n": float(g.rem_on.sum()), "e_rem_n": float(g.e_rem_on.sum()),
                "rem_dur_s": float(rb.dur_s.mean()) if len(rb) else np.nan, "e_rem_dur_s": e_dur, "block": g.block.iloc[0]}

    for (an, rid), g in B.groupby(["animal", "record_id"]):
        t_first, t_last = g.t.min(), g.t.max() + pd.Timedelta(minutes=10)
        for bh in (1, 3):
            s = t_first
            while s + pd.Timedelta(hours=3 + bh) <= t_last:
                a_ = agg(an, s, s + pd.Timedelta(hours=3))
                b_ = agg(an, s + pd.Timedelta(hours=3), s + pd.Timedelta(hours=3 + bh))
                if a_ and b_:
                    rows.append({"setting": "within record", "B_h": bh, "animal": an, "t_A": s, **{f"A_{k}": v for k, v in a_.items()},
                                 **{f"B_{k}": v for k, v in b_.items()}})
                s += pd.Timedelta(hours=1)
    for r in gaps[gaps.usable].itertuples():
        for bh in (1, 3):
            gs, ge = pd.Timestamp(r.gap_start), pd.Timestamp(r.gap_end)
            a_ = agg(r.animal, gs - pd.Timedelta(hours=3), gs)
            b_ = agg(r.animal, ge, ge + pd.Timedelta(hours=bh))
            if a_ and b_:
                rows.append({"setting": f"across gap ({r.cause})", "B_h": bh, "animal": r.animal, "t_A": gs - pd.Timedelta(hours=3),
                             "kind": r.kind, **{f"A_{k}": v for k, v in a_.items()}, **{f"B_{k}": v for k, v in b_.items()}})
    return pd.DataFrame(rows)


def comp_slopes(Wn: pd.DataFrame) -> pd.DataFrame:
    import statsmodels.api as sm
    out = []
    Wn = Wn.copy()
    Wn["debt_rem"] = Wn.A_e_rem_min - Wn.A_rem_min
    Wn["pay_rem"] = Wn.B_rem_min - Wn.B_e_rem_min
    Wn["pay_nrem"] = Wn.B_nrem_min - Wn.B_e_nrem_min
    Wn["pay_rem_n"] = Wn.B_rem_n - Wn.B_e_rem_n
    Wn["pay_rem_dur"] = Wn.B_rem_dur_s - Wn.B_e_rem_dur_s
    Wn["debt_nrem"] = Wn.A_e_nrem_min - Wn.A_nrem_min
    sets = [(s, b) for s in sorted(Wn.setting.unique()) for b in (1, 3)]
    for s, bh in sets:
        g = Wn[(Wn.setting == s) & (Wn.B_h == bh)]
        for y, x in (("pay_rem", "debt_rem"), ("pay_rem_n", "debt_rem"), ("pay_rem_dur", "debt_rem"), ("pay_nrem", "debt_nrem"),
                     ("pay_nrem", "debt_rem")):
            gg = g[[y, x, "A_block", "animal"]].dropna()
            if len(gg) < 15:
                continue
            X = sm.add_constant(gg[[x]])
            try:
                fit = sm.OLS(gg[y], X).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(gg.A_block)[0]})
            except Exception:  # noqa: BLE001
                fit = sm.OLS(gg[y], X).fit()
            sg = []
            for an, ga in gg.groupby("animal"):
                if len(ga) >= 8 and ga[x].std() > 0:
                    sg.append(np.sign(sm.OLS(ga[y], sm.add_constant(ga[[x]])).fit().params[x]))
            out.append({"setting": s, "B_h": bh, "outcome": y, "predictor": x, "n_windows": len(gg), "slope": fit.params[x],
                        "ci_lo": fit.conf_int().loc[x, 0], "ci_hi": fit.conf_int().loc[x, 1], "p": fit.pvalues[x],
                        "animals_positive": int(np.sum(np.array(sg) > 0)), "animals": len(sg),
                        "mean_debt": float(gg[x].mean()), "mean_payback": float(gg[y].mean())})
    return pd.DataFrame(out)


# ------------------------------------------------------------------ B1b
def wake_to_kth_rem(recs: list[dict]) -> pd.DataFrame:
    rows = []
    for rc in recs:
        st = rc["state"]
        bl = bouts(st)
        ma = {(a, b) for a, b in episode_units(st, MA_LIMITS[0])["ma"]}
        cn = np.r_[0, np.cumsum(st == N)]
        last_rem_end = None
        for i, (s, a, b) in enumerate(bl):
            if s == R:
                last_rem_end = b if (a > 0 and st[a - 1] != 0) else None
            if not (s == W and (b - a) >= 420 and i + 1 < len(bl) and bl[i + 1][0] == N):
                continue
            n_pre = int(cn[a] - cn[last_rem_end]) if last_rem_end is not None else 0
            t_end = rc["start"] + pd.Timedelta(seconds=b)
            k, cur_n = 0, 0
            for s2, a2, b2 in bl[i + 1:]:
                if s2 == 0 or (s2 == W and (b2 - a2) >= 420):
                    break
                if s2 == N or (s2 == W and (a2, b2) in ma):
                    cur_n += b2 - a2
                elif s2 == R:
                    k += 1
                    rows.append({"animal": rc["animal"], "block": rc["block"], "k": k, "d_s": b - a, "n_pre": n_pre,
                                 "anchor": int(last_rem_end is not None), "n_k": cur_n,
                                 "hour": t_end.hour + t_end.minute / 60})
                    cur_n = 0
                    if k == 3:
                        break
    return pd.DataFrame(rows)


def b1b_fit(D: pd.DataFrame) -> pd.DataFrame:
    import statsmodels.api as sm
    out = []
    for k, g in D.groupby("k"):
        g = g[g.n_k > 0].copy()
        X = pd.DataFrame({"l_d": np.log(g.d_s), "l_npre": np.log1p(g.n_pre), "anchor": g.anchor}, index=g.index)
        for h in (1, 2):
            X[f"sin{h}"], X[f"cos{h}"] = np.sin(2 * np.pi * h * g.hour / 24), np.cos(2 * np.pi * h * g.hour / 24)
        X = sm.add_constant(pd.concat([X, pd.get_dummies(g.animal, drop_first=True, dtype=float)], axis=1))
        fit = sm.OLS(np.log(g.n_k), X).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(g.block)[0]})
        sg = []
        for an, ga in g.groupby("animal"):
            if len(ga) >= 15:
                Xa = X.loc[ga.index, ["const", "l_d", "l_npre", "anchor", "sin1", "cos1", "sin2", "cos2"]]
                sg.append(np.sign(sm.OLS(np.log(ga.n_k), Xa).fit().params["l_d"]))
        for term in ("l_d", "l_npre"):
            out.append({"k_th_REM_after_wake": k, "n": len(g), "term": term, "coef": fit.params[term], "se": fit.bse[term],
                        "p": fit.pvalues[term], "animals_positive_l_d": int(np.sum(np.array(sg) > 0)) if term == "l_d" else None,
                        "animals": len(sg) if term == "l_d" else None})
    return pd.DataFrame(out)


# ------------------------------------------------------------------ main
def phase2(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_quant import md_table, save_fig
    parts = set(a.parts)
    out = run_dir("sleep_schedule_phase2" + ("_smoke" if a.smoke else ""), "2026c")
    rd, fd = (out, out) if a.smoke else (report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes"))
    gc = git_commit()
    rv = included_sessions(Path(a.review), Path(a.states))
    recs = build_records(rv, Path(a.states))
    p0 = json.load(open(ROOT / "results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_phase0_2026c.json"))["run_dir"]
    gaps = pd.read_csv(Path(p0) / "gaps.csv", parse_dates=["gap_start", "gap_end", "swap"])
    steps = build_steps(recs)
    steps["d_bin"] = pd.cut(steps.d_prev, D_BINS, right=False, labels=D_LABELS)
    print(f"steps {len(steps)}", flush=True)
    sec = {}

    if "c2" in parts:                                              # ---- C2: empirical hazard + one held-out comparison
        s_ = steps[steps.has_anchor == 1].copy()
        s_["n_tot"] = s_.n_since + s_.elapsed
        edges = np.r_[0, 10, 20, 30, 45, 60, 90, 120, 180, 240, 360, 480, 720, 960, 1200, 1800, 2700, 3600]
        s_["nb"] = pd.cut(s_.n_tot, edges, right=False)
        H = s_.groupby(["animal", "nb"], observed=True).agg(n=("y", "size"), hR=("y", lambda v: (v == 1).mean()),
                                                           hW=("y", lambda v: (v == 2).mean())).reset_index()
        H = H[H.n >= 50]
        Hm = H.groupby("nb", observed=True).agg(hR=("hR", "mean"), hW=("hW", "mean"), animals=("animal", "nunique"),
                                              steps=("n", "sum")).reset_index()
        Hm["n_tot_mid_min"] = [(iv.left + iv.right) / 120 for iv in Hm.nb]
        Hm.drop(columns="nb").to_csv(rd / "ephys_spikes_sleep_schedule_phase2_c2_hazard_2026c.csv", index=False)
        fig, ax = plt.subplots(figsize=(7, 4.5))
        ax.plot(Hm.n_tot_mid_min, Hm.hR, "o-", label="REM next 10 s")
        ax.plot(Hm.n_tot_mid_min, Hm.hW, "s-", label="WAKE next 10 s")
        ax.set_xscale("log")
        ax.set_xlabel("total NREM since the last REM at this step (min; bout start + elapsed)")
        ax.set_ylabel("empirical hazard per 10-s NREM step (mean of animals)")
        ax.set_title(f"C2 empirical hazards (description; steps with a REM anchor)  {gc}", fontsize=9)
        ax.legend(fontsize=8)
        save_fig(fig, fd / "ephys_spikes_sleep_schedule_phase2_c2_hazard_2026c.png")
        F, _, FA, _ = run_cv(steps, {"M2": ["L1", "nspl", "wsince", "rem"], "M2t": ["L1", "ntspl", "wsince", "rem"]}, forward_folds(steps))
        sec["c2"] = (Hm, pd.DataFrame([compare(F, FA, "M2", "M2t", "all NREM steps")]))
        print(sec["c2"][1].round(3).to_string(index=False), flush=True)

    if "b1" in parts:                                              # ---- B1: carry-over across natural wakes
        pw = steps[steps.d_prev > 0].copy()
        specs = {"R0": ["cur"], "C1": ["cur", "nspl", "wpre", "rem"], "U": ["cur", "nspl", "wpre", "rem", "upd"],
                 "K_nrem": ["cur", "nspl", "rem"], "K_wall": ["cur", "tspl", "rem"]}
        F, FB, FA, SP = run_cv(pw, specs, forward_folds(pw), bin_col="d_bin", split_pairs=[("R0", "C1")])
        F.to_csv(out / "b1_folds.csv", index=False)
        FB.to_csv(out / "b1_folds_by_bin.csv", index=False)
        SP.to_csv(out / "b1_split_by_bout.csv.gz", index=False)
        rows = [compare(F, FA, "R0", "C1", "all post-wake"), compare(F, FA, "C1", "U", "all post-wake"),
                compare(F, FA, "K_nrem", "K_wall", "all post-wake")]
        for b in D_LABELS:
            fb = FB[FB.bin == b]
            for lo, hi in (("R0", "C1"), ("R0", "U"), ("K_nrem", "K_wall")):
                rows.append(compare(fb, None, lo, hi, f"wake {b}"))
        CB = pd.DataFrame(rows)
        CB.to_csv(rd / "ephys_spikes_sleep_schedule_phase2_b1_2026c.csv", index=False)
        SS = split_summary(SP, [("R0", "C1")], by_bin=True)
        SS.to_csv(rd / "ephys_spikes_sleep_schedule_phase2_b1_split_2026c.csv", index=False)
        sec["b1"] = (CB, SS)
        print(CB.round(3).to_string(index=False), flush=True)
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for (lo, hi), mk in ((("R0", "C1"), "o-"), (("R0", "U"), "s--"), (("K_nrem", "K_wall"), "^:")):
            cc = CB[(CB.comparison == f"{hi} vs {lo}") & CB.subset.str.startswith("wake ")]
            ax.errorbar(range(len(cc)), cc.delta_pct, yerr=[cc.delta_pct - cc.ci_lo_pct, cc.ci_hi_pct - cc.delta_pct],
                        fmt=mk, capsize=3, label=f"{hi} vs {lo}")
        ax.set_xticks(range(len(D_LABELS)), D_LABELS)
        ax.axhline(0, color="k", lw=0.8)
        ax.set_xlabel("length of the wake before the NREM bout")
        ax.set_ylabel("held-out log-loss change (%), negative = better")
        ax.set_title(f"B1 carry-over curve across natural wakes (forward chaining)  {gc}", fontsize=9)
        ax.legend(fontsize=8)
        save_fig(fig, fd / "ephys_spikes_sleep_schedule_phase2_b1_carryover_2026c.png")

    if "b1b" in parts:                                             # ---- B1b: long wake -> k-th REM after
        D = wake_to_kth_rem(recs)
        D.to_csv(out / "b1b_cycles.csv", index=False)
        T = b1b_fit(D)
        T.to_csv(rd / "ephys_spikes_sleep_schedule_phase2_b1b_2026c.csv", index=False)
        sec["b1b"] = T
        print(T.round(4).to_string(index=False), flush=True)

    if "c1" in parts:                                              # ---- C1: compensation, FINAL + fixed-threshold scores
        S_all = []
        for lab, sdir in (("FINAL", Path(a.states)), ("pass2med_remclean", Path(a.b3_states))):
            if not sdir.exists():
                continue
            recs_c = recs if lab == "FINAL" else build_records(included_sessions(Path(a.review), sdir), sdir)
            Bn, RB = bins10(recs_c)
            Bn = baselines(Bn, RB)
            Wn_c = comp_windows(Bn, RB, gaps)
            Wn_c.to_csv(out / f"c1_windows_{lab}.csv.gz", index=False)
            S_c = comp_slopes(Wn_c)
            S_c.insert(0, "scores", lab)
            S_all.append(S_c)
            if lab == "FINAL":
                Wn = Wn_c
                Bn.to_csv(out / "c1_bins10.csv.gz", index=False)
        S = pd.concat(S_all, ignore_index=True)
        S.to_csv(rd / "ephys_spikes_sleep_schedule_phase2_c1_2026c.csv", index=False)
        sec["c1"] = S
        print(S.round(3).to_string(index=False), flush=True)
        fig, axs = plt.subplots(1, 2, figsize=(11, 4.5))
        for ax, sel in zip(axs, ("within record", "across gap (round_logged)")):
            g = Wn[(Wn.setting == sel) & (Wn.B_h == 3)]
            ax.scatter(g.A_e_rem_min - g.A_rem_min, g.B_rem_min - g.B_e_rem_min, s=6, alpha=0.4)
            ax.axhline(0, color="k", lw=0.6)
            ax.axvline(0, color="k", lw=0.6)
            ax.set_xlabel("REM debt in the 3 h before (expected - observed, min)")
            ax.set_ylabel("REM payback in the 3 h after (observed - expected, min)")
            ax.set_title(sel, fontsize=9)
        fig.suptitle(f"C1 compensation (description; slopes in the report)  {gc}", fontsize=9)
        save_fig(fig, fd / "ephys_spikes_sleep_schedule_phase2_c1_compensation_2026c.png")

    if "b2" in parts:                                              # ---- B2 (+ B3): across battery-round gaps
        res = []
        for lab, sdir in (("FINAL", Path(a.states)), ("B3 pass2med_remclean", Path(a.b3_states))):
            if not sdir.exists():
                print(f"skip {lab}: {sdir} missing", flush=True)
                continue
            rv2 = included_sessions(Path(a.review), sdir)
            recs2 = build_records(rv2, sdir)
            tl = join_timelines(recs2, gaps)
            st2 = build_steps(tl)
            pg = st2[(st2.pg_pending == 1) & (st2.pg_gap_s >= 600)].copy()
            if pg.empty:
                print(f"{lab}: no post-gap bouts", flush=True)
                continue
            pg["kind"] = np.where(pg.t_start.dt.hour < 12, "morning", "evening")
            blocks = sorted(pg.block.unique())
            folds = []
            allb = sorted(st2.block.unique())
            for blk in blocks:
                nxt = allb[allb.index(blk) + 1] if allb.index(blk) + 1 < len(allb) else None
                tr = pg.index[(pg.block != blk) & (pg.block != nxt)]          # purge: the next block's post-gap rows
                folds.append((tr, pg.index[pg.block == blk]))
            specs = {"R0g": ["gap"], "C1g": ["gap", "nlin", "rem"]}
            F, _, FA, _ = run_cv(pg, specs, folds)
            r = compare(F, FA, "R0g", "C1g", f"{lab}: post-gap bouts before the first REM")
            r.update(gaps_with_bouts=int(pg.groupby(["animal", "pg_gap_s"]).ngroups), bouts=int(pg.drop_duplicates(["record_id", "bout_start"]).shape[0]))
            res.append(r)
            if lab == "FINAL":
                pg.to_csv(out / "b2_postgap_steps.csv.gz", index=False)
        B2 = pd.DataFrame(res)
        B2.to_csv(rd / "ephys_spikes_sleep_schedule_phase2_b2_2026c.csv", index=False)
        sec["b2"] = B2
        print(B2.round(3).to_string(index=False), flush=True)

    write_json(rd / "run_manifest_sleep_schedule_phase2_2026c.json",
               {"run_dir": str(out), "git_commit": gc, "states": str(a.states), "b3_states": str(a.b3_states), "parts": sorted(parts)})
    L = ["# Internal sleep schedule — Phase 2: carry-over across wakes, compensation, refractoriness (cohort 2026c)", "",
         f"Plan: [2026-10-07-sleep-internal-schedule.md](../../../../implementation_plan/2026-10-07-sleep-internal-schedule.md) "
         f"(rev. 2 + Amendment 1). Driver `ephys/sleep_schedule.py phase2` → `ephys/sleep_schedule_phase2.py` (commit {gc}); "
         f"bulk `{out}`. Definitions: the module docstring (copied below).", "",
         "**Status: technical ledger; no claim audit yet.** Δ = held-out log-loss change in % of the smaller model (negative "
         "= better), forward chaining over day-half blocks unless stated; holds = CI below 0 and ≥ 5/6 animals better.", "",
         "## Definitions", "", "```", (sys.modules[__name__].__doc__ or "").strip(), "```", ""]
    if "c2" in sec:
        L += ["## C2 Empirical hazards against the total NREM since the last REM", "", md_table(sec["c2"][0].round(4)), "",
              "![](../figures/ephys_spikes_sleep_schedule_phase2_c2_hazard_2026c.png)", "", md_table(sec["c2"][1].round(3)), ""]
    if "b1" in sec:
        L += ["## B1 Carry-over across natural wakes (post-wake NREM bouts)", "", md_table(sec["b1"][0].round(3)), "",
              "![](../figures/ephys_spikes_sleep_schedule_phase2_b1_carryover_2026c.png)", "",
              "Whether / when split of the carry-over gain (C1 vs R0; nats per held-out bout; positive = better):", "",
              md_table(sec["b1"][1].round(4)), ""]
    if "b1b" in sec:
        L += ["## B1b A long wake (≥ 7 min) and the next three REMs", "", md_table(sec["b1b"].round(4)), ""]
    if "c1" in sec:
        L += ["## C1 Compensation (debt = expected − observed before; payback = observed − expected after)", "",
              "Both scorings: FINAL (per-session thresholds) and pass2med_remclean (fixed per-animal thresholds). A slope "
              "that appears only under per-session thresholds can be a scoring artefact (a session's threshold error persists "
              "for its whole length).", "",
              md_table(sec["c1"].round(3)), "", "![](../figures/ephys_spikes_sleep_schedule_phase2_c1_compensation_2026c.png)", ""]
    if "b2" in sec:
        L += ["## B2 / B3 Across battery-round gaps (leave-one-block-out with purge)", "", md_table(sec["b2"].round(3)), ""]
    flat = [ln for x in L for ln in (x if isinstance(x, list) else [x])]
    (rd / "ephys_spikes_sleep_schedule_phase2_2026c.md").write_text("\n".join(flat) + "\n", encoding="utf-8")
    print("written", rd / "ephys_spikes_sleep_schedule_phase2_2026c.md")
