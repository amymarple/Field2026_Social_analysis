r"""Step E of the sleep-behaviour explore (plan implementation_plan/2026-10-08-sleep-behaviour-explore.md §4-§5, written
before results): the generative scheduler model — simulate sleep from the fitted rules, conditional on the observed long
wakes and gaps, and check whether the rules alone reproduce the data. Also produces the simulated records that Step D2
(the morning payback without a REM-deficit variable) is measured on.

Usage:  python ephys/sleep_sim.py stepE [--scorings final pass2med] [--reps 100] [--workers 8]
        python ephys/sleep_sim.py --selftest

Definitions:
  conditioning   every observed record keeps its start, length, unknown runs and wake bouts >= 420 s ("forced" blocks,
                 i.e. the observed activity pattern); everything else ("free" time = the observed sleep with its short
                 wakes) is simulated. A free stretch starts in NREM. A simulated bout that reaches a forced block is cut
                 there.
  rules (all fitted on all included NREM / REM steps of the scoring; sklearn multinomial logit, C = 1e4):
    NREM step (10 s from the bout start): stay / REM / WAKE with Step B's B-full spec at the counter P_tw600_k0
      (P = NREM minutes since the last REM, emptied at REM, x exp(-d / 600 s) over any wake, frozen over unknown;
      base: spline ln(elapsed + 5), 2-harmonic clock, linear day, dark (NOAA), has_anchor, animal; L1: ln(1 + preceding
      wake), previous bout REM / unknown, wake share of the last 10 min).
    REM step (10 s): stay / NREM / WAKE with spline ln(elapsed + 5), 2-harmonic clock, linear day, dark, animal (no
      history: #14).
    short wake (< 420 s): its length AND the state that follows it (NREM or REM) drawn together from the observed short
      wakes of the same animal, light phase and preceding state (NREM or REM). (Correction after the first run: 12-15 % of
      REM bouts start right after a wake of <= 10 s — the scorer's brief arousal before REM; v1 sent every short wake to
      NREM and under-produced REM by ~13 %.)
    exit within a 10-s step j: the bout lasts 10 j + U{1..10} s (the data's last step is partial).
  replicates     R independent simulations of every record (seeded); the observed records are the reference.
  checks (plan Step E; observed and simulated go through the same code):
    (i)   per animal: REM and NREM hours per 24 h of known time; across animal-days (calendar days, >= 50 % known):
          the SD of the daily REM and NREM hours. Pass: simulated mean within +-25 % (REM) / +-10 % (NREM) of the
          observed, and the simulated SD within +-25 % of the observed SD.
    (iii) Watson SLEEP episodes (>= 20 min; split at wake > 120 s or unknown), phase = light / dark at onset (NOAA):
          mean REM share of sleep and mean REM bouts per NREM hour by phase. Pass: within +-20 %.
    (iv)  first-REM latency (s from onset; Kaplan-Meier median, censored at the episode end) by the wake before the
          episode (2-7, 7-30, 30-120, >= 120 min) and phase, cells with >= 10 episodes. Pass: within +-25 %.
    (ii)  the carry-over curve (Phase 2 B1: held-out gain of pre-wake history by wake bin) on a few replicates: sign and
          order as observed.
    (v) / D2 the morning-round REM payback slope (sleep_explore_d.payback_from_records) on the simulated records.
    (vi)  the night -> next-day deviation slope with day fixed effects (sleep_explore_d.budget_from_records) ~ 0.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from sleep_cycles import bouts  # noqa: E402
from sleep_schedule import N, R, RELEASE, ROOT, W  # noqa: E402

KEY = "P_tw600_k0"
TAU_W, KAPPA = 600.0, 0.0
LONG_WAKE = 420
JMAX = 2000                                   # 10-s steps tabulated (5.5 h)
PGRID = np.linspace(0.0, np.log1p(1440.0), 3000)
TGRID = np.linspace(0.0, np.log1p(4 * 86400.0), 3000)
H19 = False                                   # post hoc: + spline of ln(1 + wall s since the last REM) (Step B H19)
LIN_N = ["T_day", "has_anchor", "dark", "l_dprev", "prev_rem", "prev_unk", "fW10"]


# ------------------------------------------------------------------ fitted rules -> tables
def fit_nrem(recs: list[dict]):
    """Step B's B-full at KEY on all steps; returns (model, st, levels, D)."""
    from sklearn.linear_model import LogisticRegression
    from sleep_model import build_data, design, to_arrays, variant_specs
    steps = build_data(recs, {KEY: variant_specs()[KEY]})
    D = to_arrays(steps)
    idx = np.arange(len(D["y"]))
    levels = sorted(set(D["animal"]))
    spec = {"L1": True, "hist": KEY, **({"extra": ("l_tsince_t",)} if H19 else {})}
    X, st = design(D, idx, spec, None, levels)
    m = LogisticRegression(C=1e4, max_iter=5000).fit(X, D["y"])
    return m, st, levels, D, X


def rem_steps(recs: list[dict]) -> pd.DataFrame:
    from sleep_schedule_phase3 import light_flags
    rows = []
    for rc in recs:
        st = rc["state"]
        n = len(st)
        for s, a, b in bouts(st):
            if s != R:
                continue
            J = int(np.ceil((b - a) / 10))
            y = np.zeros(J, np.int8)
            if b < n and st[b] in (N, W):
                y[-1] = 1 if st[b] == N else 2
            el = 10 * np.arange(J)
            t = rc["start"] + pd.to_timedelta(a + el, unit="s")
            rows.append(pd.DataFrame({"animal": rc["animal"], "t": t, "elapsed": el, "y": y}))
    df = pd.concat(rows, ignore_index=True)
    df["hour"] = df.t.dt.hour + df.t.dt.minute / 60 + df.t.dt.second / 3600
    df["T_day"] = (df.t - RELEASE).dt.total_seconds() / 86400
    df["dark"] = (~light_flags(df.t)).astype(float)
    return df


def fit_rem(recs: list[dict]):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import SplineTransformer
    df = rem_steps(recs)
    levels = sorted(df.animal.unique())
    spl = SplineTransformer(n_knots=4, degree=3, include_bias=False).fit(np.log(df[["elapsed"]].to_numpy() + 5.0))
    mu, sd = df.T_day.mean(), df.T_day.std() or 1.0
    X = rem_design(df, spl, mu, sd, levels)
    m = LogisticRegression(C=1e4, max_iter=5000).fit(X, df.y.to_numpy())
    return m, (spl, mu, sd), levels, df, X


def rem_design(df, spl, mu, sd, levels):
    h = df.hour.to_numpy()
    parts = [spl.transform(np.log(df[["elapsed"]].to_numpy() + 5.0)),
             np.column_stack([f(2 * np.pi * k * h / 24) for k in (1, 2) for f in (np.sin, np.cos)]),
             ((df.T_day.to_numpy() - mu) / sd)[:, None], df.dark.to_numpy()[:, None],
             np.column_stack([(df.animal.to_numpy() == lv).astype(float) for lv in levels[1:]]) if len(levels) > 1 else np.zeros((len(df), 0))]
    return np.column_stack(parts)


def full_coef(m, n_cls: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """(3, p) coefficients and (3,) intercepts indexed by class 0 / 1 / 2 (classes absent from the fit get -inf)."""
    C = np.zeros((n_cls, m.coef_.shape[1]))
    b = np.full(n_cls, -1e9)
    for i, c in enumerate(m.classes_):
        C[c], b[c] = m.coef_[i], m.intercept_[i]
    return C, b


def tables_nrem(m, st, levels) -> dict:
    C, b = full_coef(m)
    sel = st["spl_l_elapsed"].transform(np.log(10.0 * np.arange(JMAX)[:, None] + 5.0))
    spl_p = st[f"spl_lP_{KEY}"].transform(PGRID[:, None])
    ne, npp = sel.shape[1], spl_p.shape[1]
    o = 0
    fel = sel @ C[:, o:o + ne].T
    o += ne
    fP = spl_p @ C[:, o:o + npp].T
    o += npp
    fT = np.zeros((len(TGRID), 3))
    if H19:
        spl_t = st["spl_l_tsince_t"].transform(TGRID[:, None])
        fT = spl_t @ C[:, o:o + spl_t.shape[1]].T
        o += spl_t.shape[1]
    harm = C[:, o:o + 4]
    o += 4
    lin = np.zeros((3, len(LIN_N)))
    b = b.copy()
    for k, v in enumerate(LIN_N):
        beta = C[:, o + k]
        lin[:, k] = beta / st["sd"][v]
        b -= beta * st["mu"][v] / st["sd"][v]
    o += len(LIN_N)
    an = np.zeros((3, len(levels)))
    an[:, 1:] = C[:, o:o + len(levels) - 1]
    assert o + len(levels) - 1 == C.shape[1]
    return {"fel": np.ascontiguousarray(fel), "fP": np.ascontiguousarray(fP), "fT": np.ascontiguousarray(fT), "harm": harm, "lin": lin, "an": an, "b": b}


def tables_rem(m, aux, levels) -> dict:
    spl, mu, sd = aux
    C, b = full_coef(m)
    sel = spl.transform(np.log(10.0 * np.arange(JMAX)[:, None] + 5.0))
    ne = sel.shape[1]
    fel = sel @ C[:, :ne].T
    harm = C[:, ne:ne + 4]
    bt = C[:, ne + 4] / sd
    b = b - C[:, ne + 4] * mu / sd
    bd = C[:, ne + 5]
    an = np.zeros((3, len(levels)))
    an[:, 1:] = C[:, ne + 6:ne + 6 + len(levels) - 1]
    return {"fel": np.ascontiguousarray(fel), "harm": harm, "lin": np.ascontiguousarray(np.column_stack([bt, bd])), "an": an, "b": b}


def wake_sampler(recs: list[dict], levels: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Observed short wakes (< 420 s) grouped by (animal, dark at the wake start, preceding state REM?): concatenated
    durations, the state that followed each (NREM / REM), and group offsets (group g = (animal * 2 + dark) * 2 + prev_rem)."""
    from sleep_schedule_phase3 import light_flags
    rows = []
    for rc in recs:
        bl = bouts(rc["state"])
        for i, (s, a, b) in enumerate(bl):
            if s == W and (b - a) < LONG_WAKE and i > 0 and bl[i - 1][0] in (N, R):
                nxt = bl[i + 1][0] if i + 1 < len(bl) else N
                rows.append((rc["animal"], rc["start"] + pd.Timedelta(seconds=a), b - a, int(bl[i - 1][0] == R), R if nxt == R else N))
    df = pd.DataFrame(rows, columns=["animal", "t", "d", "prev_rem", "next"])
    df["dark"] = (~light_flags(df.t)).astype(int)
    df["a"] = df.animal.map({lv: i for i, lv in enumerate(levels)})
    df["g"] = (df.a * 2 + df.dark) * 2 + df.prev_rem
    ng = len(levels) * 4
    dur, nx, off = [], [], [0]
    for g in range(ng):
        sel = df[df.g == g]
        if len(sel) < 20:                                        # thin cell: fall back to the animal x phase pool
            a_, dk = (g // 4), (g // 2) % 2
            sel = df[(df.a == a_) & (df.dark == dk)]
            if len(sel) < 20:
                sel = df
        dur.append(sel.d.to_numpy())
        nx.append(sel["next"].to_numpy())
        off.append(off[-1] + len(sel))
    return np.concatenate(dur).astype(np.int64), np.concatenate(nx).astype(np.int8), np.array(off, np.int64)


# ------------------------------------------------------------------ the simulator (numba)
def _sim_core():
    from numba import njit

    @njit
    def lp_interp(fP, x, step):
        n = fP.shape[0]
        u = x / step
        i = int(u)
        if i >= n - 1:
            return fP[n - 1]
        w = u - i
        return fP[i] * (1.0 - w) + fP[i + 1] * w

    PG_STEP = PGRID[1] - PGRID[0]
    TG_STEP = TGRID[1] - TGRID[0]

    @njit
    def simulate(seed, L, sod0, tday0, a_idx, f_start, f_end, f_type, dark,
                 nfel, nfP, nharm, nlin, nan_, nb, rfel, rharm, rlin, ran, rb, wdur, wnext, woff, tau_w, kappa, nfT, use_t):
        np.random.seed(seed)
        out = np.zeros(L, np.int8)
        nf = f_start.shape[0]
        fi = 0
        t = 0
        P = 0.0
        anchor = 0.0
        prev_type = -1                     # -1 record start, 0 unknown, 1 W, 3 N, 5 R
        prev_len = 0
        cur = 3
        last_rem_end = 0
        eta = np.zeros(3)
        while t < L:
            nxt = f_start[fi] if fi < nf else L
            if t >= nxt:                                   # forced block
                e = f_end[fi]
                ty = f_type[fi]
                for s in range(t, min(e, L)):
                    out[s] = ty
                d = e - t
                if ty == 1:
                    if tau_w == 0.0:
                        P = 0.0
                    elif tau_w < 1e18:
                        P = P * np.exp(-d / tau_w)
                prev_type = ty
                prev_len = d
                t = e
                fi += 1
                cur = 3
                continue
            if cur == 3:                                   # NREM bout
                lo = t - 600
                if lo < 0:
                    lo = 0
                kw = 0
                kk = 0
                for s in range(lo, t):
                    if out[s] != 0:
                        kk += 1
                        if out[s] == 1:
                            kw += 1
                fW10 = kw / kk if kk > 0 else 0.0
                ldp = np.log1p(prev_len) if prev_type == 1 else 0.0
                prem = 1.0 if prev_type == 5 else 0.0
                punk = 1.0 if prev_type <= 0 else 0.0
                P0 = P
                j = 0
                nxt_state = 3
                length = 0
                while True:
                    ts = t + 10 * j
                    if ts >= nxt or ts >= L:
                        length = min(nxt, L) - t
                        nxt_state = -1
                        break
                    sod = (sod0 + ts) % 86400
                    h = sod / 3600.0
                    a1 = 2 * np.pi * h / 24
                    x_lin = (tday0 + ts / 86400.0, anchor, float(dark[ts]), ldp, prem, punk, fW10)
                    jj = j if j < nfel.shape[0] else nfel.shape[0] - 1
                    lpv = np.log1p(P0 + 10.0 * j / 60.0)
                    ltv = np.log1p(ts - last_rem_end) * anchor
                    for c in range(3):
                        v = nb[c] + nan_[c, a_idx] + nfel[jj, c] + lp_interp(nfP[:, c], lpv, PG_STEP)
                        if use_t > 0.0:
                            v += lp_interp(nfT[:, c], ltv, TG_STEP)
                        v += nharm[c, 0] * np.sin(a1) + nharm[c, 1] * np.cos(a1) + nharm[c, 2] * np.sin(2 * a1) + nharm[c, 3] * np.cos(2 * a1)
                        for k in range(7):
                            v += nlin[c, k] * x_lin[k]
                        eta[c] = v
                    mx = max(eta[0], max(eta[1], eta[2]))
                    p0 = np.exp(eta[0] - mx)
                    p1 = np.exp(eta[1] - mx)
                    p2 = np.exp(eta[2] - mx)
                    u = np.random.random() * (p0 + p1 + p2)
                    if u >= p0:
                        nxt_state = 5 if u < p0 + p1 else 1
                        length = 10 * j + 1 + np.random.randint(0, 10)
                        break
                    j += 1
                e = t + length
                if e > nxt:
                    e = nxt
                if e > L:
                    e = L
                for s in range(t, e):
                    out[s] = 3
                P = P0 + (e - t) / 60.0
                prev_type = 3
                prev_len = e - t
                t = e
                cur = nxt_state if nxt_state > 0 else 3
                continue
            if cur == 5:                                   # REM bout
                j = 0
                nxt_state = 3
                length = 0
                while True:
                    ts = t + 10 * j
                    if ts >= nxt or ts >= L:
                        length = min(nxt, L) - t
                        nxt_state = -1
                        break
                    sod = (sod0 + ts) % 86400
                    h = sod / 3600.0
                    a1 = 2 * np.pi * h / 24
                    jj = j if j < rfel.shape[0] else rfel.shape[0] - 1
                    for c in range(3):
                        v = rb[c] + ran[c, a_idx] + rfel[jj, c]
                        v += rharm[c, 0] * np.sin(a1) + rharm[c, 1] * np.cos(a1) + rharm[c, 2] * np.sin(2 * a1) + rharm[c, 3] * np.cos(2 * a1)
                        v += rlin[c, 0] * (tday0 + ts / 86400.0) + rlin[c, 1] * float(dark[ts])
                        eta[c] = v
                    mx = max(eta[0], max(eta[1], eta[2]))
                    p0 = np.exp(eta[0] - mx)
                    p1 = np.exp(eta[1] - mx)
                    p2 = np.exp(eta[2] - mx)
                    u = np.random.random() * (p0 + p1 + p2)
                    if u >= p0:
                        nxt_state = 3 if u < p0 + p1 else 1
                        length = 10 * j + 1 + np.random.randint(0, 10)
                        break
                    j += 1
                e = t + length
                if e > nxt:
                    e = nxt
                if e > L:
                    e = L
                for s in range(t, e):
                    out[s] = 5
                r = e - t
                if kappa == 0.0:
                    P = 0.0
                else:
                    P = P * np.exp(-r / kappa)
                anchor = 1.0
                last_rem_end = e
                prev_type = 5
                prev_len = r
                t = e
                cur = nxt_state if nxt_state > 0 else 3
                continue
            # short wake
            g = (a_idx * 2 + int(dark[t])) * 2 + (1 if prev_type == 5 else 0)
            k0 = woff[g]
            k1 = woff[g + 1]
            kq = k0 + np.random.randint(0, k1 - k0)
            d = wdur[kq]
            e = t + d
            if e > nxt:
                e = nxt
            if e > L:
                e = L
            for s in range(t, e):
                out[s] = 1
            dd = e - t
            if tau_w == 0.0:
                P = 0.0
            elif tau_w < 1e18:
                P = P * np.exp(-dd / tau_w)
            prev_type = 1
            prev_len = dd
            t = e
            cur = 5 if wnext[kq] == 5 else 3
        return out

    return simulate


_SIM = None


def simulator():
    global _SIM
    if _SIM is None:
        _SIM = _sim_core()
    return _SIM


# ------------------------------------------------------------------ inputs per record
def record_inputs(rc: dict, levels: list[str]) -> dict:
    from sleep_quant import sun_times
    st = rc["state"]
    L = len(st)
    fs, fe, ft = [], [], []
    for s, a, b in bouts(st):
        if s == 0 or (s == W and (b - a) >= LONG_WAKE):
            fs.append(a)
            fe.append(b)
            ft.append(s)
    t0 = rc["start"]
    sec = np.arange(L)
    tt = t0 + pd.to_timedelta(sec, unit="s")
    dark = np.ones(L, np.uint8)
    days = pd.date_range(tt[0].normalize(), tt[-1].normalize(), freq="D")
    for d in days:
        sr, ss = (pd.Timestamp(x) for x in sun_times(d.date()))
        m = (tt >= sr) & (tt < ss)
        dark[m] = 0
    sod0 = int((t0 - t0.normalize()).total_seconds())
    return {"L": L, "sod0": sod0, "tday0": (t0 - RELEASE).total_seconds() / 86400, "a": levels.index(rc["animal"]),
            "fs": np.array(fs, np.int64), "fe": np.array(fe, np.int64), "ft": np.array(ft, np.int8), "dark": dark}


def build_model(recs: list[dict]) -> dict:
    mN, stN, levN, _, _ = fit_nrem(recs)
    mR, auxR, levR, _, _ = fit_rem(recs)
    assert levN == levR
    TN, TR = tables_nrem(mN, stN, levN), tables_rem(mR, auxR, levR)
    wd, wn, wo = wake_sampler(recs, levN)
    return {"levels": levN, "TN": TN, "TR": TR, "wdur": wd, "wnext": wn, "woff": wo, "mN": mN, "stN": stN, "mR": mR, "auxR": auxR,
            "inputs": [record_inputs(rc, levN) for rc in recs]}


def simulate_records(recs: list[dict], M: dict, rep: int, tau_w: float = TAU_W, kappa: float = KAPPA) -> list[dict]:
    sim = simulator()
    TN, TR = M["TN"], M["TR"]
    out = []
    for i, (rc, I) in enumerate(zip(recs, M["inputs"])):
        st = sim(1_000_003 * rep + 7919 * i + 17, I["L"], I["sod0"], I["tday0"], I["a"], I["fs"], I["fe"], I["ft"], I["dark"],
                 TN["fel"], TN["fP"], TN["harm"], TN["lin"], TN["an"], TN["b"], TR["fel"], TR["harm"], TR["lin"], TR["an"], TR["b"],
                 M["wdur"], M["wnext"], M["woff"], float(tau_w), float(kappa), TN["fT"], 1.0 if H19 else 0.0)
        out.append({**{k: v for k, v in rc.items() if k != "state"}, "state": st})
    return out


# ------------------------------------------------------------------ metrics (observed and simulated, same code)
def m_daily(recs: list[dict]) -> dict:
    rows = []
    for rc in recs:
        st = rc["state"]
        day = (rc["start"] + pd.to_timedelta(np.arange(len(st)), unit="s")).normalize()
        df = pd.DataFrame({"day": day, "known": st != 0, "rem": st == R, "nrem": st == N})
        g = df.groupby("day")[["known", "rem", "nrem"]].sum()
        g["animal"] = rc["animal"]
        rows.append(g.reset_index())
    D = pd.concat(rows).groupby(["animal", "day"])[["known", "rem", "nrem"]].sum().reset_index()
    A = D.groupby("animal")[["known", "rem", "nrem"]].sum()
    rem24 = (24 * A.rem / A.known).mean()
    nrem24 = (24 * A.nrem / A.known).mean()
    Dd = D[D.known >= 0.5 * 86400].copy()
    Dd["rem24"], Dd["nrem24"] = 24 * Dd.rem / Dd.known, 24 * Dd.nrem / Dd.known
    sd_rem = float(Dd.groupby("animal").rem24.std().mean())
    sd_nrem = float(Dd.groupby("animal").nrem24.std().mean())
    return {"rem_h_per_24h": float(rem24), "nrem_h_per_24h": float(nrem24), "sd_rem_daily": sd_rem, "sd_nrem_daily": sd_nrem,
            "animal_days": len(Dd)}


def episodes(recs: list[dict]) -> pd.DataFrame:
    from sleep_schedule_phase3 import episodes_of, light_flags
    rows = []
    for rc in recs:
        st = rc["state"]
        ends = {b: (s, b - a) for s, a, b in bouts(st)}
        for a, b in episodes_of(st, 1200):
            seg = st[a:b]
            rb = [(x0, x1) for s, x0, x1 in bouts(seg) if s == R]
            pw = ends.get(a)
            rows.append({"animal": rc["animal"], "t0": rc["start"] + pd.Timedelta(seconds=a), "nrem_s": int((seg == N).sum()),
                         "rem_s": int((seg == R).sum()), "rem_n": len(rb), "lat_s": (rb[0][0] if rb else b - a), "ev": int(bool(rb)),
                         "pre_wake_s": pw[1] if (pw and pw[0] == W) else np.nan})
    E = pd.DataFrame(rows)
    E["dark"] = ~light_flags(E.t0)
    E["rem_share"] = E.rem_s / (E.rem_s + E.nrem_s)
    E["rem_per_h_nrem"] = E.rem_n / (E.nrem_s / 3600)
    E["pw_bin"] = pd.cut(E.pre_wake_s / 60, [2, 7, 30, 120, 1e9], right=False, labels=["2-7", "7-30", "30-120", ">=120"])
    return E


def m_episodes(E: pd.DataFrame) -> dict:
    from sleep_schedule_phase3 import km_median
    r = {}
    for ph, g in E.groupby("dark"):
        lab = "dark" if ph else "light"
        r[f"rem_share_{lab}"] = float(g.rem_share.mean())
        r[f"rem_per_h_nrem_{lab}"] = float(g.rem_per_h_nrem.mean())
        r[f"n_episodes_{lab}"] = len(g)
        for b, gb in g.groupby("pw_bin", observed=True):
            r[f"lat_med_{lab}_{b}"] = km_median(gb.lat_s.to_numpy(), gb.ev.to_numpy()) if len(gb) >= 10 else np.nan
            r[f"n_{lab}_{b}"] = len(gb)
    return r


def metrics(recs: list[dict]) -> dict:
    return {**m_daily(recs), **m_episodes(episodes(recs))}


def _rep_job(rep: int, recs: list[dict], M: dict) -> dict:
    sim = simulate_records(recs, M, rep)
    return {"rep": rep, **metrics(sim)}


# ------------------------------------------------------------------ step E
def stepE(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from joblib import Parallel, delayed
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_model import PASS2MED, STATES, records_for
    from sleep_quant import md_table, save_fig
    sfx = "_h19" if H19 else ""
    out = run_dir("sleep_explore_E" + sfx, "2026c")
    rd, fd = report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes")
    gc = git_commit()
    t0 = time.time()
    allrows, checks = [], []
    for lab in a.scorings:
        recs = records_for(STATES if lab == "final" else PASS2MED)
        M = build_model(recs)
        obs = metrics(recs)
        print(f"[{lab}] model built {time.time() - t0:.0f} s; observed {obs}", flush=True)
        simulate_records(recs[:1], M, 0)                            # compile once in this process
        res = Parallel(n_jobs=a.workers, backend="loky")(delayed(_rep_job)(r, recs, M) for r in range(a.reps))
        S = pd.DataFrame(res)
        S.insert(0, "scores", lab)
        S.to_csv(out / f"sim_metrics_{lab}.csv", index=False)
        allrows.append(pd.concat([pd.DataFrame([{"scores": lab, "rep": -1, **obs}]), S], ignore_index=True))
        print(f"[{lab}] {a.reps} replicates {time.time() - t0:.0f} s", flush=True)
        tol = {"rem_h_per_24h": 0.25, "nrem_h_per_24h": 0.10, "sd_rem_daily": 0.25, "sd_nrem_daily": 0.25,
               "rem_share_light": 0.20, "rem_share_dark": 0.20, "rem_per_h_nrem_light": 0.20, "rem_per_h_nrem_dark": 0.20}
        tol.update({k: 0.25 for k in obs if k.startswith("lat_med_")})
        for k, tl in tol.items():
            ov = obs.get(k, np.nan)
            sv = S[k].to_numpy(dtype=float) if k in S else np.array([np.nan])
            if not np.isfinite(ov) or not np.isfinite(sv).any():
                continue
            mean = float(np.nanmean(sv))
            lo, hi = np.nanpercentile(sv, [2.5, 97.5])
            rel = mean / ov - 1
            checks.append({"scores": lab, "check": "(iv)" if k.startswith("lat_") else ("(iii)" if k.startswith(("rem_share", "rem_per_h")) else "(i)"),
                           "metric": k, "observed": ov, "sim_mean": mean, "sim_2.5%": lo, "sim_97.5%": hi, "rel_diff": rel,
                           "tolerance": tl, "pass": bool(abs(rel) <= tl)})
        np.save(out / f"model_tables_{lab}.npy", {"TN": M["TN"], "TR": M["TR"], "levels": M["levels"]}, allow_pickle=True)
    CH = pd.DataFrame(checks)
    CH.to_csv(rd / f"ephys_spikes_sleep_explore_E{sfx}_checks_2026c.csv", index=False)
    pd.concat(allrows).to_csv(rd / f"ephys_spikes_sleep_explore_E{sfx}_metrics_2026c.csv", index=False)
    # figure: observed vs simulated for the episode metrics
    fig, ax = plt.subplots(figsize=(10, 4.5))
    q = CH[CH.scores == a.scorings[0]].reset_index(drop=True)
    x = np.arange(len(q))
    ax.errorbar(x, q.sim_mean / q.observed, yerr=[(q.sim_mean - q["sim_2.5%"]) / q.observed, (q["sim_97.5%"] - q.sim_mean) / q.observed], fmt="o", label="simulated / observed")
    ax.fill_between(x, 1 - q.tolerance, 1 + q.tolerance, alpha=0.15, step="mid", label="tolerance")
    ax.axhline(1, color="k", lw=0.6)
    ax.set_xticks(x, q.metric, rotation=70, fontsize=7)
    ax.set_ylabel("simulated / observed")
    ax.legend(fontsize=8)
    ax.set_title(f"Step E: the counter rules simulated, conditional on the observed long wakes and gaps ({a.reps} reps)  {gc}", fontsize=9)
    save_fig(fig, fd / f"ephys_spikes_sleep_explore_E{sfx}_checks_2026c.png")
    L = ["# Sleep-behaviour explore — Step E: the generative scheduler model (cohort 2026c)" + (" — POST HOC variant + wall-clock time since REM (H19)" if H19 else ""), "",
         "Plan [implementation_plan/2026-10-08-sleep-behaviour-explore.md](../../../../implementation_plan/2026-10-08-sleep-behaviour-explore.md) "
         f"§4-§5 (pass rules written before results). Driver `ephys/sleep_sim.py stepE` (commit {gc}); bulk `{out}`; "
         f"{a.reps} replicates; runtime {(time.time() - t0) / 60:.0f} min. **Technical ledger.**", "",
         "## Definitions", "", "```", (__doc__ or "").strip(), "```", "",
         "## Checks (i), (iii), (iv): simulated vs observed", "", *md_table(CH.round(4)), "",
         f"![](../figures/ephys_spikes_sleep_explore_E{sfx}_checks_2026c.png)", ""]
    (rd / f"ephys_spikes_sleep_explore_E{sfx}_2026c.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    write_json(rd / f"run_manifest_sleep_explore_E{sfx}_2026c.json", {"run_dir": str(out), "git_commit": gc, "reps": a.reps, "scorings": a.scorings})
    print(CH.round(3).to_string(index=False), flush=True)
    print("written", rd / "ephys_spikes_sleep_explore_E_2026c.md", flush=True)


# ------------------------------------------------------------------ selftest
def selftest() -> None:
    from sleep_model import records_for, STATES
    t0 = time.time()
    recs = records_for(STATES)
    sub = [rc for rc in recs if rc["animal"] == "SF07"][:6] + [rc for rc in recs if rc["animal"] == "SF10"][:6]
    # 1. the tables reproduce the fitted models exactly
    mN, stN, levN, D, X = fit_nrem(sub)
    TN = tables_nrem(mN, stN, levN)
    rng = np.random.default_rng(0)
    idx = rng.choice(len(D["y"]), 2000, replace=False)
    pk = mN.predict_proba(X[idx])
    el = np.round(np.exp(D["l_elapsed"][idx]) - 5).astype(int) // 10
    eta = np.zeros((len(idx), 3))
    for c in range(3):
        h = 2 * np.pi * np.arctan2(D["sin1"][idx], D["cos1"][idx]) / (2 * np.pi)
        eta[:, c] = (TN["b"][c] + TN["an"][c, [levN.index(x) for x in D["animal"][idx]]] + TN["fel"][el, c]
                     + np.interp(D[f"lP_{KEY}"][idx], PGRID, TN["fP"][:, c])
                     + TN["harm"][c, 0] * D["sin1"][idx] + TN["harm"][c, 1] * D["cos1"][idx] + TN["harm"][c, 2] * D["sin2"][idx] + TN["harm"][c, 3] * D["cos2"][idx]
                     + sum(TN["lin"][c, k] * D[v][idx] for k, v in enumerate(LIN_N))
                     + (np.interp(D["l_tsince_t"][idx], TGRID, TN["fT"][:, c]) if H19 else 0.0))
    p = np.exp(eta - eta.max(1, keepdims=True))
    p /= p.sum(1, keepdims=True)
    err = float(np.abs(p[:, mN.classes_] - pk).max())
    assert err < 1e-3, err
    mR, auxR, levR, dfR, XR = fit_rem(sub)
    TR = tables_rem(mR, auxR, levR)
    idx = rng.choice(len(dfR), 1000, replace=False)
    pk = mR.predict_proba(XR[idx])
    g = dfR.iloc[idx]
    hh = 2 * np.pi * g.hour.to_numpy() / 24
    eta = np.zeros((len(idx), 3))
    for c in range(3):
        eta[:, c] = (TR["b"][c] + TR["an"][c, [levR.index(x) for x in g.animal]] + TR["fel"][(g.elapsed.to_numpy() // 10).astype(int), c]
                     + TR["harm"][c, 0] * np.sin(hh) + TR["harm"][c, 1] * np.cos(hh) + TR["harm"][c, 2] * np.sin(2 * hh) + TR["harm"][c, 3] * np.cos(2 * hh)
                     + TR["lin"][c, 0] * g.T_day.to_numpy() + TR["lin"][c, 1] * g.dark.to_numpy())
    p = np.exp(eta - eta.max(1, keepdims=True))
    p /= p.sum(1, keepdims=True)
    err2 = float(np.abs(p[:, mR.classes_] - pk).max())
    assert err2 < 1e-3, err2
    # 2. the simulator keeps every forced block exactly and fills the rest with sleep / short wakes
    M = {"levels": levN, "TN": TN, "TR": TR}
    M["wdur"], M["wnext"], M["woff"] = wake_sampler(sub, levN)
    M["inputs"] = [record_inputs(rc, levN) for rc in sub]
    sims = simulate_records(sub, M, 1)
    for rc, sm, I in zip(sub, sims, M["inputs"]):
        st = rc["state"]
        forced = (st == 0) | np.isin(np.arange(len(st)), np.concatenate([np.arange(a, b) for a, b in zip(I["fs"], I["fe"])]) if len(I["fs"]) else [])
        assert np.array_equal(sm["state"][forced], st[forced]), "forced blocks not kept"
        free = ~forced
        assert set(np.unique(sm["state"][free])) <= {1, 3, 5}
        w = [b - a for s, a, b in bouts(np.where(free, sm["state"], 0)) if s == 1]
        assert (np.array(w) < LONG_WAKE).all() if w else True
    om, sm_ = metrics(sub), metrics(sims)
    print("selftest observed vs one simulation (subset):", {k: (round(om[k], 3), round(sm_.get(k, np.nan), 3)) for k in ("rem_h_per_24h", "nrem_h_per_24h")}, flush=True)
    print(f"selftest PASS: tables reproduce the fitted models (max |dp| {err:.1e} NREM, {err2:.1e} REM); forced blocks kept; "
          f"free time = sleep + short wakes ({time.time() - t0:.0f} s)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["stepE"])
    ap.add_argument("--scorings", nargs="+", default=["final", "pass2med"], choices=["final", "pass2med"])
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--h19", action="store_true", help="post hoc: add the wall-clock time since REM spline (Step B H19)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    global H19
    H19 = a.h19
    if a.selftest:
        selftest()
    elif a.cmd == "stepE":
        stepE(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
