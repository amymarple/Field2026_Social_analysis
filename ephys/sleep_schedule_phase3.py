r"""Phase 3 of the internal-schedule analysis: the 24/7 record (plan Amendment 4).
Called by `python ephys/sleep_schedule.py phase3 [--parts q1 q2 q3]`.

Definitions (FINAL 1-s states + per-second z-metrics as Phase 2b; field-PC time; light = sunrise..sunset, NOAA times):
  episode        a maximal stretch of a record with no wake bout > 120 s and no unknown epoch, trimmed to its first and
                 last sleep epoch (Watson-2016 SLEEP rule); SLEEP = >= 20 min, short nap = 5-20 min. Phase of an episode
                 = dark / light at its onset. "Naps" = dark-phase episodes (the rats' main sleep is the light phase).
  per episode    duration; NREM, REM s; REM bouts (n, durations); latency from onset to the first REM onset (censored
                 at the episode end); REM-onset-to-onset intervals; sequential share = intervals whose NREM + MA (< 40 s)
                 content <= 135 s (the v1 two-Gaussian split); pre-episode wake (the wake bout ending at the onset); mean
                 z-theta, z-SW, z-EMG over the episode's REM seconds.
  Q1a            per animal: means by phase; dark - light per animal (6/6 sign); episode-level mixed model
                 outcome ~ dark + ln(duration) (+ animal random intercept). Latency: Kaplan-Meier median per phase.
  Q1b            held out (forward chaining, as Phase 2): M2t vs M2t + dark x [spline ln(1+NREM since REM, running),
                 ln(1+W_since), ln REM_pre]; and the empirical REM hazard against the running NREM since REM by phase.
  Q1c            REM-onset tails (180 s before natural NREM -> REM) by phase: z-theta, z-SW, z-EMG.
  Q1d            24-h budget: per animal and night (sunset d -> sunrise d+1) and the following day (-> sunset d+1),
                 REM observed - expected (min per recorded hour; C1 baselines, >= 50 % recorded); slope of the day
                 deviation on the night deviation (and day d -> night d), per-animal signs.
  Q2             events = natural wakes >= 120 s followed by NREM inside a record, and battery-round gaps (Phase-0
                 usable gaps with cause round_*; t0 = the first NREM onset after the gap). From t0 the record is
                 followed up to 6 h (censored at its end): cumulative NREM s, REM s, REM onsets, observed - expected
                 (C1 baselines per second of recorded time) at horizons 5 .. 360 min; first-REM survival (Kaplan-Meier,
                 censored). Classes: wake 2-7, 7-30, 30-120 min, >= 2 h, battery round; pre-wake REM debt = expected -
                 observed REM over the 3 h before the wake (>= 80 % recorded). At h = 60, 180, 360 min (complete cases):
                 OLS excess ~ ln d + dark + debt + animal, SEs clustered by block, plus per-animal fits (sign counts:
                 with ~22 blocks the clustered SEs are fragile, and long horizons keep only events early in a record;
                 the synthetic smoke test gave a spurious ln d effect at 360 min). Repeated on pass2med_remclean.
  Q3             fragmentation at an NREM bout start: frag60 = wake bouts >= 40 s ending in the previous 60 min; totals
                 held by w60 = wake share of recorded time in the same 60 min. Held out: M2t + w60 vs + frag60.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from sleep_cycles import bouts  # noqa: E402
from sleep_schedule import N, R, ROOT, W, included_sessions  # noqa: E402
from sleep_schedule_phase2 import baselines, bins10, build_steps, compare, forward_folds, run_cv  # noqa: E402
from sleep_schedule_phase2b import records_with_metrics  # noqa: E402

HORIZONS = np.arange(5, 361, 5)
CLASSES = [(120, 420, "wake 2-7 min"), (420, 1800, "wake 7-30 min"), (1800, 7200, "wake 30-120 min"), (7200, 10 ** 9, "wake >= 2 h")]


def light_flags(t: pd.Series) -> np.ndarray:
    from sleep_quant import sun_times
    t = pd.to_datetime(t)
    days = t.dt.normalize()
    out = np.zeros(len(t), bool)
    for d in days.unique():
        sr, ss = (pd.Timestamp(x) for x in sun_times(pd.Timestamp(d).date()))
        m = (days == d).to_numpy()
        out[m] = ((t[m] >= sr) & (t[m] < ss)).to_numpy()
    return out


def episodes_of(st: np.ndarray, min_s: int) -> list[tuple[int, int]]:
    bl = bouts(st)
    cut = np.zeros(len(st), bool)
    for s, a, b in bl:
        if (s == W and (b - a) > 120) or s == 0:
            cut[a:b] = True
    out, a0 = [], None
    for i in range(len(st) + 1):
        if i < len(st) and not cut[i]:
            a0 = i if a0 is None else a0
        elif a0 is not None:
            seg = st[a0:i]
            idx = np.flatnonzero((seg == N) | (seg == R))
            if idx.size and (idx[-1] - idx[0] + 1) >= min_s:
                out.append((a0 + int(idx[0]), a0 + int(idx[-1]) + 1))
            a0 = None
    return out


def km(t: np.ndarray, e: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    o = np.argsort(t)
    t, e = t[o], e[o]
    ut = np.unique(t[e == 1])
    S, s = [], 1.0
    for u in ut:
        at_risk = np.sum(t >= u)
        d = np.sum((t == u) & (e == 1))
        s *= 1 - d / at_risk
        S.append(s)
    return ut, np.array(S)


def km_median(t, e) -> float:
    ut, S = km(np.asarray(t, float), np.asarray(e, int))
    below = np.flatnonzero(S <= 0.5)
    return float(ut[below[0]]) if below.size else np.nan


def episode_table(recs: list[dict]) -> pd.DataFrame:
    rows = []
    for rc in recs:
        st = rc["state"]
        bl = bouts(st)
        starts = {a: (s, b - a) for s, a, b in bl}
        ends = {b: (s, b - a) for s, a, b in bl}
        for a, b in episodes_of(st, 300):
            seg = st[a:b]
            rb = [(x0, x1) for s, x0, x1 in bouts(seg) if s == R]
            on = [a + x0 for x0, _ in rb]
            inter = []
            for (r0a, r0b), (r1a, _) in zip(rb[:-1], rb[1:]):
                sub = seg[r0b:r1a]
                nn = int((sub == N).sum())
                for s2, x0, x1 in bouts(sub):
                    if s2 == W and (x1 - x0) < 40 and x0 > 0 and x1 < len(sub):
                        nn += x1 - x0
                inter.append((r1a - r0a, nn))
            pw = ends.get(a)
            remm = seg == R
            t0 = rc["start"] + pd.Timedelta(seconds=a)
            rows.append({"animal": rc["animal"], "block": rc["block"], "record_id": rc["record_id"], "t0": t0, "dur_s": b - a,
                         "kind": "SLEEP >= 20 min" if (b - a) >= 1200 else "short 5-20 min",
                         "nrem_s": int((seg == N).sum()), "rem_s": int(remm.sum()), "rem_n": len(rb),
                         "rem_dur_mean": float(np.mean([x1 - x0 for x0, x1 in rb])) if rb else np.nan,
                         "lat_s": (on[0] - a) if on else (b - a), "lat_event": int(bool(on)),
                         "ioi_median": float(np.median([x for x, _ in inter])) if inter else np.nan,
                         "seq_share": float(np.mean([n <= 135 for _, n in inter])) if inter else np.nan,
                         "pre_wake_s": pw[1] if (pw and pw[0] == W) else np.nan,
                         **{f"rem_z_{m}": float(np.nanmean(rc[m][a:b][remm])) if remm.any() else np.nan for m in ("th", "sw", "emg")}})
    E = pd.DataFrame(rows)
    E["dark"] = ~light_flags(E.t0)
    E["rem_share"] = E.rem_s / (E.rem_s + E.nrem_s)
    E["rem_per_h_nrem"] = E.rem_n / (E.nrem_s / 3600)
    return E


def expected_rates(recs: list[dict], Bn: pd.DataFrame) -> None:
    """Per-second expected REM / NREM probability and REM-onset rate from the 10-min baseline bins (filled forward)."""
    for rc in recs:
        g = Bn[Bn.record_id == rc["record_id"]].sort_values("t")
        n = len(rc["state"])
        for col, key in (("e_rem_s", "p_rem"), ("e_nrem_s", "p_nrem"), ("e_rem_on", "r_on")):
            v = np.full(n, np.nan)
            for i, r in enumerate(g.itertuples()):
                s0 = 600 * i
                v[s0:s0 + 600] = getattr(r, col) / r.rec_s if r.rec_s > 0 else np.nan
            v = pd.Series(v).ffill().bfill().to_numpy()
            v[rc["state"] == 0] = 0.0
            rc[key] = np.r_[0, np.cumsum(v)]


def trajectories(recs: list[dict], gaps: pd.DataFrame) -> pd.DataFrame:
    rows = []
    by_end = {(rc["animal"], pd.Timestamp(rc["end"]).floor("s")): rc for rc in recs}
    by_start = {}
    for rc in recs:
        by_start.setdefault(rc["animal"], []).append(rc)

    def follow(rc, i0, cls, d_s, wake_start_i, pre_rc=None, pre_end_i=None):
        st = rc["state"]
        cr, cn = np.r_[0, np.cumsum(st == R)], np.r_[0, np.cumsum(st == N)]
        on = np.r_[0, np.cumsum(np.r_[0, (st[1:] == R) & (st[:-1] != R) & (st[:-1] != 0)])]
        n = len(st)
        first = np.flatnonzero(st[i0:] == R)
        lat = first[0] if first.size else n - i0
        src, j1 = (pre_rc, pre_end_i) if pre_rc is not None else (rc, wake_start_i)
        j0 = j1 - 3 * 3600
        debt = np.nan
        if j0 >= 0:
            s_ = src["state"]
            rec = np.sum(s_[j0:j1] != 0)
            if rec >= 0.8 * 3 * 3600:
                debt = (src["p_rem"][j1] - src["p_rem"][j0] - np.sum(s_[j0:j1] == R)) / 60
        t0 = rc["start"] + pd.Timedelta(seconds=i0)
        r = {"animal": rc["animal"], "block": rc["block"], "cls": cls, "d_s": d_s, "t0": t0, "debt_rem_min": debt,
             "lat_first_rem_s": min(lat, 6 * 3600), "lat_event": int(first.size > 0 and lat <= 6 * 3600),
             "followed_s": min(n - i0, 6 * 3600)}
        for h in HORIZONS:
            j = i0 + 60 * h
            if j > n:
                break
            r[f"rem_{h}"] = (cr[j] - cr[i0]) / 60
            r[f"erem_{h}"] = (rc["p_rem"][j] - rc["p_rem"][i0]) / 60
            r[f"nrem_{h}"] = (cn[j] - cn[i0]) / 60
            r[f"enrem_{h}"] = (rc["p_nrem"][j] - rc["p_nrem"][i0]) / 60
            r[f"on_{h}"] = on[j] - on[i0]
            r[f"eon_{h}"] = rc["r_on"][j] - rc["r_on"][i0]
        rows.append(r)

    for rc in recs:
        st = rc["state"]
        for s, a, b in bouts(st):
            if s == W and (b - a) >= 120 and b < len(st) and st[b] == N and a > 0 and st[a - 1] != 0:
                cls = next(lab for lo, hi, lab in CLASSES if lo <= (b - a) < hi)
                follow(rc, b, cls, b - a, a)
    for g in gaps[gaps.usable & gaps.cause.str.startswith("round")].itertuples():
        pre = by_end.get((g.animal, pd.Timestamp(g.gap_start).floor("s")))
        post = [rc for rc in by_start.get(g.animal, []) if abs((rc["start"] - pd.Timestamp(g.gap_end)).total_seconds()) < 2]
        if pre is None or not post:
            continue
        rc = post[0]
        nn = np.flatnonzero(rc["state"] == N)
        if not nn.size:
            continue
        follow(rc, int(nn[0]), "battery round", (pd.Timestamp(g.gap_end) - pd.Timestamp(g.gap_start)).total_seconds() + nn[0],
               None, pre_rc=pre, pre_end_i=len(pre["state"]))
    T = pd.DataFrame(rows)
    T["dark"] = ~light_flags(T.t0)
    return T


def traj_summary(T: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    import statsmodels.api as sm
    rows = []
    for cls, g in T.groupby("cls"):
        for h in HORIZONS:
            if f"rem_{h}" not in g:
                continue
            gg = g.dropna(subset=[f"rem_{h}"])
            if len(gg) < 10:
                continue
            for q, (o, e) in {"REM min": ("rem", "erem"), "NREM min": ("nrem", "enrem"), "REM bouts": ("on", "eon")}.items():
                x = gg[f"{o}_{h}"] - gg[f"{e}_{h}"]
                rows.append({"cls": cls, "h_min": h, "quantity": q, "n": len(gg), "excess_mean": x.mean(),
                             "excess_se": x.std() / np.sqrt(len(gg)), "observed_mean": gg[f"{o}_{h}"].mean(), "expected_mean": gg[f"{e}_{h}"].mean()})
    S = pd.DataFrame(rows)
    reg = []
    nat = T[T.cls != "battery round"].copy()
    for h in (60, 180, 360):
        for q, (o, e) in {"REM min": ("rem", "erem"), "NREM min": ("nrem", "enrem"), "REM bouts": ("on", "eon")}.items():
            g = nat.dropna(subset=[f"{o}_{h}", "debt_rem_min"])
            if len(g) < 30:
                continue
            X = pd.DataFrame({"l_d": np.log(g.d_s), "dark": g.dark.astype(float), "debt": g.debt_rem_min}, index=g.index)
            X = sm.add_constant(pd.concat([X, pd.get_dummies(g.animal, drop_first=True, dtype=float)], axis=1))
            yv = g[f"{o}_{h}"] - g[f"{e}_{h}"]
            fit = sm.OLS(yv, X).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(g.block)[0]})
            own = ["const", "l_d", "dark", "debt"]
            sg = {k: [] for k in ("l_d", "dark", "debt")}
            for an, ga in g.groupby("animal"):              # per-animal fits: the replication count (few clusters -> SEs fragile)
                Xa = X.loc[ga.index, own]
                if len(ga) >= 15 and Xa.dark.nunique() > 1:
                    pa_ = sm.OLS(yv.loc[ga.index], Xa).fit().params
                    for k in sg:
                        sg[k].append(np.sign(pa_[k]))
            for term in ("l_d", "dark", "debt"):
                reg.append({"h_min": h, "quantity": q, "term": term, "n": len(g), "coef": fit.params[term],
                            "ci_lo": fit.conf_int().loc[term, 0], "ci_hi": fit.conf_int().loc[term, 1], "p": fit.pvalues[term],
                            "animals_positive": int(np.sum(np.array(sg[term]) > 0)), "animals": len(sg[term])})
    return S, pd.DataFrame(reg)


def phase3(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import statsmodels.formula.api as smf
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_quant import md_table, save_fig
    parts = set(a.parts) & {"q1", "q2", "q3"} or {"q1", "q2", "q3"}
    out = run_dir("sleep_schedule_phase3" + ("_smoke" if a.smoke else ""), "2026c")
    rd, fd = (out, out) if a.smoke else (report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes"))
    gc = git_commit()
    man = lambda n: json.load(open(ROOT / f"results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_{n}_2026c.json"))["run_dir"]  # noqa: E731
    gaps = pd.read_csv(Path(man("phase0")) / "gaps.csv", parse_dates=["gap_start", "gap_end"])
    rv = included_sessions(Path(a.review), Path(a.states))
    recs = records_with_metrics(rv, Path(a.states))
    L = ["# Internal sleep schedule — Phase 3: the 24/7 record — naps vs day sleep, recovery after interruptions, "
         "fragmentation (cohort 2026c)", "",
         f"Plan: [2026-10-07-sleep-internal-schedule.md](../../../../implementation_plan/2026-10-07-sleep-internal-schedule.md) "
         f"(Amendment 4). Driver `ephys/sleep_schedule.py phase3` → `ephys/sleep_schedule_phase3.py` (commit {gc}); bulk "
         f"`{out}`. **Technical ledger; no claim audit yet.**", "", "## Definitions", "", "```",
         (sys.modules[__name__].__doc__ or "").strip(), "```", ""]

    if "q1" in parts:
        E = episode_table(recs)
        E.to_csv(out / "q1_episodes.csv", index=False)
        outc = ["rem_share", "rem_per_h_nrem", "rem_dur_mean", "ioi_median", "seq_share", "pre_wake_s", "rem_z_th", "rem_z_sw", "rem_z_emg"]
        rows = []
        for kind in ("SLEEP >= 20 min", "all >= 5 min"):
            Ek = E if kind == "all >= 5 min" else E[E.kind == kind]
            pa = Ek.groupby(["animal", "dark"])[outc + ["dur_s"]].mean()
            cnt = Ek.groupby(["animal", "dark"]).size()
            for o in outc + ["dur_s"]:
                dd = (pa[o].xs(True, level="dark") - pa[o].xs(False, level="dark")).dropna()
                r = {"episodes": kind, "outcome": o, "light_mean": Ek[~Ek.dark][o].mean(), "dark_mean": Ek[Ek.dark][o].mean(),
                     "animals_dark_higher": int((dd > 0).sum()), "animals": len(dd), "n_light": int((~Ek.dark).sum()), "n_dark": int(Ek.dark.sum())}
                if o != "dur_s":
                    g = Ek.dropna(subset=[o]).assign(l_dur=lambda x: np.log(x.dur_s), dk=lambda x: x.dark.astype(float))
                    try:
                        mm = smf.mixedlm(f"{o} ~ dk + l_dur", g, groups=g.animal).fit()
                        r.update(dark_coef=mm.params["dk"], dark_ci_lo=mm.conf_int().loc["dk", 0], dark_ci_hi=mm.conf_int().loc["dk", 1], dark_p=mm.pvalues["dk"])
                    except Exception:  # noqa: BLE001
                        pass
                rows.append(r)
            for dk, g in Ek.groupby("dark"):
                rows.append({"episodes": kind, "outcome": f"KM median latency to first REM (s), {'dark' if dk else 'light'}",
                             "light_mean" if not dk else "dark_mean": km_median(g.lat_s, g.lat_event),
                             "n_light" if not dk else "n_dark": len(g)})
        Q1a = pd.DataFrame(rows)
        Q1a.to_csv(rd / "ephys_spikes_sleep_schedule_phase3_q1a_2026c.csv", index=False)
        print(Q1a.round(3).to_string(index=False), flush=True)
        # Q1b held out + hazard by phase
        steps = build_steps(recs)
        steps["dark"] = (~light_flags(steps.t)).astype(float)
        F, _, FA, _ = run_cv(steps, {"M2t": ["L1", "ntspl", "wsince", "rem"], "M2t_dark": ["L1", "ntspl", "wsince", "rem", "darkint"]},
                             forward_folds(steps))
        Q1b = pd.DataFrame([compare(F, FA, "M2t", "M2t_dark", "all NREM steps")])
        Q1b.to_csv(rd / "ephys_spikes_sleep_schedule_phase3_q1b_2026c.csv", index=False)
        print(Q1b.round(3).to_string(index=False), flush=True)
        s_ = steps[steps.has_anchor == 1].copy()
        s_["n_tot"] = s_.n_since + s_.elapsed
        edges = np.r_[0, 30, 60, 120, 240, 480, 720, 1200, 1800, 3600]
        s_["nb"] = pd.cut(s_.n_tot, edges, right=False)
        H = s_.groupby(["dark", "animal", "nb"], observed=True).agg(n=("y", "size"), hR=("y", lambda v: (v == 1).mean()),
                                                                   hW=("y", lambda v: (v == 2).mean())).reset_index()
        H = H[H.n >= 50].groupby(["dark", "nb"], observed=True).agg(hR=("hR", "mean"), hW=("hW", "mean"), animals=("animal", "nunique")).reset_index()
        H["n_tot_mid_min"] = [(iv.left + iv.right) / 120 for iv in H.nb]
        H.drop(columns="nb").to_csv(rd / "ephys_spikes_sleep_schedule_phase3_q1b_hazard_2026c.csv", index=False)
        # Q1c REM-onset tails by phase
        lags = np.arange(-180, 0)
        tails = {}
        for rc in recs:
            st = rc["state"]
            bl = bouts(st)
            for i in range(1, len(bl)):
                (ps, pa_, pb), (s, a0, _) = bl[i - 1], bl[i]
                if ps == N and s == R and (pb - pa_) >= 60 and a0 >= 180:
                    t = rc["start"] + pd.Timedelta(seconds=a0)
                    dk = bool(~light_flags(pd.Series([t]))[0])
                    tails.setdefault(dk, []).append(np.stack([rc[m][a0 + lags] for m in ("sw", "th", "emg")]))
        Q1c = pd.DataFrame([{"phase": "dark" if dk else "light", "n": len(v), **{f"{m}_last30": float(np.nanmean(np.array(v)[:, j, -30:]))
                            for j, m in enumerate(("sw", "th", "emg"))}} for dk, v in tails.items()])
        Q1c.to_csv(rd / "ephys_spikes_sleep_schedule_phase3_q1c_2026c.csv", index=False)
        # Q1d 24-h budget
        Bn, RB = bins10(recs)
        Bn = baselines(Bn, RB)
        Bn["dark"] = ~light_flags(Bn.t)
        from sleep_quant import sun_times
        rows = []
        for an, g in Bn.groupby("animal"):
            for d in pd.date_range("2026-08-30", "2026-09-11"):
                sr0, ss0 = (pd.Timestamp(x) for x in sun_times(d.date()))
                sr1, ss1 = (pd.Timestamp(x) for x in sun_times((d + pd.Timedelta(days=1)).date()))
                per = {"day_before": (sr0, ss0), "night": (ss0, sr1), "day_after": (sr1, ss1)}
                rr = {"animal": an, "night_of": d.date()}
                for k, (t0, t1) in per.items():
                    gg = g[(g.t >= t0) & (g.t < t1)]
                    span = (t1 - t0).total_seconds()
                    rr[f"{k}_cov"] = gg.rec_s.sum() / span
                    rr[f"{k}_dev"] = (gg.rem_s.sum() - gg.e_rem_s.sum()) / max(gg.rec_s.sum(), 1) * 60 if gg.rec_s.sum() > 0 else np.nan
                rows.append(rr)
        D = pd.DataFrame(rows)
        D.to_csv(out / "q1d_days.csv", index=False)
        import statsmodels.api as sm
        q1d = []
        for x, y in (("night_dev", "day_after_dev"), ("day_before_dev", "night_dev")):
            g = D[(D[x.replace("_dev", "_cov")] >= 0.5) & (D[y.replace("_dev", "_cov")] >= 0.5)].dropna(subset=[x, y])
            if len(g) < 10:
                continue
            fit = sm.OLS(g[y], sm.add_constant(g[[x]])).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(g.animal)[0]})
            sg = [np.sign(sm.OLS(ga[y], sm.add_constant(ga[[x]])).fit().params[x]) for _, ga in g.groupby("animal") if len(ga) >= 4]
            q1d.append({"predictor": x, "outcome": y, "n_animal_days": len(g), "slope": fit.params[x], "ci_lo": fit.conf_int().loc[x, 0],
                        "ci_hi": fit.conf_int().loc[x, 1], "p": fit.pvalues[x], "animals_positive": int(np.sum(np.array(sg) > 0)), "animals": len(sg)})
        Q1d = pd.DataFrame(q1d)
        Q1d.to_csv(rd / "ephys_spikes_sleep_schedule_phase3_q1d_2026c.csv", index=False)
        print(Q1d.round(3).to_string(index=False), flush=True)
        fig, axs = plt.subplots(1, 2, figsize=(12, 4.5))
        for dk, g in H.groupby("dark"):
            axs[0].plot(g.n_tot_mid_min, g.hR, "o-", label=("dark (naps)" if dk else "light (main sleep)"))
            axs[1].plot(g.n_tot_mid_min, g.hW, "o-", label=("dark (naps)" if dk else "light (main sleep)"))
        for ax, lab in zip(axs, ("REM", "WAKE")):
            ax.set_xscale("log")
            ax.set_xlabel("total NREM since the last REM (min)")
            ax.set_ylabel(f"empirical P({lab} in the next 10 s)")
            ax.legend(fontsize=8)
        fig.suptitle(f"Q1b hazards by phase (description)  {gc}", fontsize=9)
        save_fig(fig, fd / "ephys_spikes_sleep_schedule_phase3_q1_hazard_2026c.png")
        L += ["## Q1 Night naps vs day sleep", "", "(a) Episode structure and REM physiology (dark − light; mixed model with "
              "ln(duration), animal random intercept; per-animal signs):", "", md_table(Q1a.round(3)), "",
              "(b) Do the REM-entry rules differ at night? Held out:", "", md_table(Q1b.round(3)), "",
              "![](../figures/ephys_spikes_sleep_schedule_phase3_q1_hazard_2026c.png)", "",
              "(c) REM-onset tails by phase (z, last 30 s before REM):", "", md_table(Q1c.round(3)), "",
              "(d) 24-h budget (REM deviation, min per recorded hour):", "", md_table(Q1d.round(3)), ""]

    if "q2" in parts:
        allS, allR = [], []
        for lab, sdir in (("FINAL", Path(a.states)), ("pass2med_remclean", Path(a.b3_states))):
            if not sdir.exists():
                continue
            recs_c = recs if lab == "FINAL" else records_with_metrics(included_sessions(Path(a.review), sdir), sdir)
            Bn, RB = bins10(recs_c)
            Bn = baselines(Bn, RB)
            expected_rates(recs_c, Bn)
            T = trajectories(recs_c, gaps)
            T.to_csv(out / f"q2_trajectories_{lab}.csv.gz", index=False)
            S, Rg = traj_summary(T)
            S.insert(0, "scores", lab)
            Rg.insert(0, "scores", lab)
            allS.append(S)
            allR.append(Rg)
            surv = []
            for cls, g in T.groupby("cls"):
                surv.append({"scores": lab, "cls": cls, "n": len(g), "km_median_first_rem_min": km_median(g.lat_first_rem_s, g.lat_event) / 60,
                             "share_no_rem_within_6h_or_followup": float(1 - g.lat_event.mean()), "dark_share": float(g.dark.mean())})
            allS.append(pd.DataFrame(surv).assign(quantity="first-REM survival"))
            if lab == "FINAL":
                fig, axs = plt.subplots(1, 3, figsize=(16, 4.5))
                for ax, q in zip(axs, ("REM min", "REM bouts", "NREM min")):
                    for cls, g in S[S.quantity == q].groupby("cls"):
                        ax.plot(g.h_min, g.excess_mean, label=f"{cls} (n0={g.n.iloc[0]})")
                        ax.fill_between(g.h_min, g.excess_mean - g.excess_se, g.excess_mean + g.excess_se, alpha=0.15)
                    ax.axhline(0, color="k", lw=0.6)
                    ax.set_xlabel("minutes after sleep onset following the interruption")
                    ax.set_ylabel(f"cumulative {q}: observed - expected")
                    ax.set_title(q, fontsize=9)
                axs[0].legend(fontsize=7)
                fig.suptitle(f"Q2 recovery trajectories after interruptions (complete cases per horizon; FINAL)  {gc}", fontsize=9)
                save_fig(fig, fd / "ephys_spikes_sleep_schedule_phase3_q2_trajectories_2026c.png")
        Q2S = pd.concat(allS, ignore_index=True)
        Q2R = pd.concat(allR, ignore_index=True)
        Q2S.to_csv(rd / "ephys_spikes_sleep_schedule_phase3_q2_curves_2026c.csv", index=False)
        Q2R.to_csv(rd / "ephys_spikes_sleep_schedule_phase3_q2_regression_2026c.csv", index=False)
        sel = Q2S[Q2S.h_min.isin([60, 180, 360]) | Q2S.quantity.eq("first-REM survival")]
        print(sel.round(3).to_string(index=False), flush=True)
        print(Q2R.round(3).to_string(index=False), flush=True)
        L += ["## Q2 Recovery trajectories after interruptions", "",
              "Excess = observed − expected cumulative quantity since the sleep onset after the interruption (complete cases at "
              "each horizon; records end at the battery rounds, so long horizons hold fewer events).", "",
              "![](../figures/ephys_spikes_sleep_schedule_phase3_q2_trajectories_2026c.png)", "",
              "Selected horizons (60 / 180 / 360 min) and first-REM survival:", "", md_table(sel.round(3)), "",
              "Natural wakes, OLS of the excess at each horizon (ln wake length, dark, pre-wake REM debt; animal FE; SEs by block):",
              "", md_table(Q2R.round(3)), ""]

    if "q3" in parts:
        steps = build_steps(recs)
        w60 = np.zeros(len(steps))
        f60 = np.zeros(len(steps))
        f120 = np.zeros(len(steps))
        for rid, g in steps.groupby("record_id"):
            st = recs[rid]["state"]
            cw, ck = np.r_[0, np.cumsum(st == W)], np.r_[0, np.cumsum(st != 0)]
            wb_end = np.array([b for s, a0, b in bouts(st) if s == W and (b - a0) >= 40])
            a_ = g.bout_start.to_numpy().astype(int)
            lo = np.maximum(a_ - 3600, 0)
            k = ck[a_] - ck[lo]
            w60[g.index] = np.where(k > 0, (cw[a_] - cw[lo]) / np.maximum(k, 1), 0)
            f60[g.index] = np.searchsorted(wb_end, a_, side="right") - np.searchsorted(wb_end, lo, side="right")
            f120[g.index] = np.searchsorted(wb_end, a_, side="right") - np.searchsorted(wb_end, np.maximum(a_ - 7200, 0), side="right")
        steps["w60"], steps["frag60"], steps["frag120"] = w60, f60, f120
        base = ["L1", "ntspl", "wsince", "rem", "col:w60"]
        F, _, FA, _ = run_cv(steps, {"A": base, "B": base + ["col:frag60"], "C": base + ["col:frag60", "col:frag120"]}, forward_folds(steps))
        Q3 = pd.DataFrame([compare(F, FA, "A", "B", "frag60 beyond the totals"), compare(F, FA, "A", "C", "frag60 + frag120")])
        Q3.to_csv(rd / "ephys_spikes_sleep_schedule_phase3_q3_2026c.csv", index=False)
        print(Q3.round(3).to_string(index=False), flush=True)
        L += ["## Q3 Fragmentation beyond the totals", "", md_table(Q3.round(3)), ""]

    flat = [ln for x in L for ln in (x if isinstance(x, list) else [x])]
    (rd / "ephys_spikes_sleep_schedule_phase3_2026c.md").write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_schedule_phase3_2026c.json", {"run_dir": str(out), "git_commit": gc, "states": str(a.states),
                                                                     "b3_states": str(a.b3_states), "parts": sorted(parts)})
    print("written", rd / "ephys_spikes_sleep_schedule_phase3_2026c.md")


# ================================================================== Phase 3b (Amendment 5: two checks before the claim audit)
def phase3b(a) -> None:
    """(1) Same-events catch-up: natural wakes followed >= 3 h (>= 6 h): REM excess at 1 / 3 (/ 6) h on the SAME events,
    and the paired change; battery rounds likewise. (2) 24-h budget robustness: both scorings, minutes (obs - exp over the
    recorded part) and rates, >= 50 % / >= 80 % recorded in both periods, animal fixed effects + per-animal slopes, REM and
    NREM."""
    import statsmodels.api as sm
    from _common import git_commit, write_json
    from output_paths import report_dir, run_dir
    from sleep_quant import md_table, sun_times
    out = run_dir("sleep_schedule_phase3b" + ("_smoke" if a.smoke else ""), "2026c")
    rd = out if a.smoke else report_dir("2026c", "ephys_spikes")
    gc = git_commit()
    p3 = Path(json.load(open(ROOT / "results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_phase3_2026c.json"))["run_dir"])
    rows, brow = [], []
    for lab in ("FINAL", "pass2med_remclean"):
        T = pd.read_csv(p3 / f"q2_trajectories_{lab}.csv.gz", parse_dates=["t0"])
        nat = T[T.cls != "battery round"].copy()
        for hs in ((60, 180), (60, 180, 360)):
            g = nat.dropna(subset=[f"rem_{h}" for h in hs]).copy()
            for h in hs:
                g[f"x{h}"] = g[f"rem_{h}"] - g[f"erem_{h}"]
            X = pd.DataFrame({"l_d": np.log(g.d_s), "dark": g.dark.astype(float)}, index=g.index)
            X = sm.add_constant(pd.concat([X, pd.get_dummies(g.animal, drop_first=True, dtype=float)], axis=1))
            ys = {f"REM excess at {h} min": g[f"x{h}"] for h in hs}
            ys[f"change {hs[0]} -> {hs[-1]} min"] = g[f"x{hs[-1]}"] - g[f"x{hs[0]}"]
            for yl, y in ys.items():
                fit = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(g.block)[0]})
                sg = []
                for _, ga in g.groupby("animal"):
                    if len(ga) >= 15 and ga.dark.nunique() > 1:
                        Xa = sm.add_constant(pd.DataFrame({"l_d": np.log(ga.d_s), "dark": ga.dark.astype(float)}))
                        sg.append(np.sign(sm.OLS(y.loc[ga.index], Xa).fit().params["l_d"]))
                rows.append({"scores": lab, "events": f"followed >= {hs[-1]} min", "n": len(g), "outcome": yl,
                             "l_d_coef": fit.params["l_d"], "ci_lo": fit.conf_int().loc["l_d", 0], "ci_hi": fit.conf_int().loc["l_d", 1],
                             "p": fit.pvalues["l_d"], "animals_negative": int(np.sum(np.array(sg) < 0)), "animals": len(sg)})
        b = T[T.cls == "battery round"].dropna(subset=["rem_60", "rem_180", "rem_360"])
        for h in (60, 180, 360):
            x = b[f"rem_{h}"] - b[f"erem_{h}"]
            brow.append({"scores": lab, "n": len(b), "h_min": h, "REM_excess_mean": x.mean(), "se": x.std() / np.sqrt(len(b)),
                         "animals_below_0": int((b.assign(x=x).groupby("animal").x.mean() < 0).sum()), "animals": b.animal.nunique()})
    S1, S1b = pd.DataFrame(rows), pd.DataFrame(brow)
    S1.to_csv(rd / "ephys_spikes_sleep_schedule_phase3b_same_events_2026c.csv", index=False)
    S1b.to_csv(rd / "ephys_spikes_sleep_schedule_phase3b_battery_same_events_2026c.csv", index=False)
    print(S1.round(3).to_string(index=False), flush=True)
    print(S1b.round(3).to_string(index=False), flush=True)
    brows = []
    for lab, sdir in (("FINAL", Path(a.states)), ("pass2med_remclean", Path(a.b3_states))):
        recs = records_with_metrics(included_sessions(Path(a.review), sdir), sdir)
        Bn, RB = bins10(recs)
        Bn = baselines(Bn, RB)
        drows = []
        for an, g in Bn.groupby("animal"):
            for d in pd.date_range("2026-08-30", "2026-09-11"):
                ss0 = pd.Timestamp(sun_times(d.date())[1])
                sr1, ss1 = (pd.Timestamp(x) for x in sun_times((d + pd.Timedelta(days=1)).date()))
                rr = {"animal": an, "night_of": d}
                for k, (t0, t1) in {"night": (ss0, sr1), "day": (sr1, ss1)}.items():
                    gg = g[(g.t >= t0) & (g.t < t1)]
                    rr[f"{k}_cov"] = gg.rec_s.sum() / (t1 - t0).total_seconds()
                    for q, (o, e) in {"REM": ("rem_s", "e_rem_s"), "NREM": ("nrem_s", "e_nrem_s")}.items():
                        rr[f"{k}_{q}_dev_min"] = (gg[o].sum() - gg[e].sum()) / 60
                        rr[f"{k}_{q}_rate_dev"] = (gg[o].sum() - gg[e].sum()) / max(gg.rec_s.sum(), 1) * 60
                drows.append(rr)
        D = pd.DataFrame(drows)
        D.to_csv(out / f"budget_days_{lab}.csv", index=False)
        for cov in (0.5, 0.8):
            for q in ("REM", "NREM"):
                for unit, suf in (("min per recorded h (rate)", "rate_dev"), ("minutes over the recorded part", "dev_min")):
                    x, y = f"night_{q}_{suf}", f"day_{q}_{suf}"
                    g = D[(D.night_cov >= cov) & (D.day_cov >= cov)].dropna(subset=[x, y])
                    if len(g) < 12:
                        continue
                    pooled = sm.OLS(g[y], sm.add_constant(g[[x]])).fit(cov_type="HC3")
                    Xf = sm.add_constant(pd.concat([g[[x]], pd.get_dummies(g.animal, drop_first=True, dtype=float)], axis=1))
                    fe = sm.OLS(g[y], Xf).fit(cov_type="HC3")
                    sg = [np.sign(sm.OLS(ga[y], sm.add_constant(ga[[x]])).fit().params[x]) for _, ga in g.groupby("animal") if len(ga) >= 4]
                    brows.append({"scores": lab, "coverage_min": cov, "quantity": q, "unit": unit, "n_animal_days": len(g),
                                  "pooled_slope": pooled.params[x], "pooled_ci_lo": pooled.conf_int().loc[x, 0], "pooled_ci_hi": pooled.conf_int().loc[x, 1],
                                  "within_animal_slope": fe.params[x], "within_ci_lo": fe.conf_int().loc[x, 0], "within_ci_hi": fe.conf_int().loc[x, 1],
                                  "within_p": fe.pvalues[x], "animals_negative": int(np.sum(np.array(sg) < 0)), "animals": len(sg)})
    S2 = pd.DataFrame(brows)
    S2.to_csv(rd / "ephys_spikes_sleep_schedule_phase3b_budget_2026c.csv", index=False)
    print(S2.round(3).to_string(index=False), flush=True)
    L = ["# Internal sleep schedule — Phase 3b: same-events catch-up and the 24-h budget checks (cohort 2026c)", "",
         f"Plan Amendment 5. Driver `ephys/sleep_schedule.py phase3b` (commit {gc}); bulk `{out}`. Technical ledger.", "",
         "## Definitions", "", "```", (phase3b.__doc__ or "").strip(), "```", "",
         "## 1. Same events: REM excess after natural wakes (coefficient of ln wake length; animal FE, dark; SEs by block)", "",
         md_table(S1.round(3)), "", "Battery rounds, the same events at 1 / 3 / 6 h (REM observed − expected, min):", "",
         md_table(S1b.round(3)), "", "## 2. 24-h budget: next-day deviation on the preceding night's deviation", "",
         md_table(S2.round(3)), ""]
    flat = [ln for x in L for ln in (x if isinstance(x, list) else [x])]
    (rd / "ephys_spikes_sleep_schedule_phase3b_2026c.md").write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_schedule_phase3b_2026c.json", {"run_dir": str(out), "git_commit": gc})
    print("written", rd / "ephys_spikes_sleep_schedule_phase3b_2026c.md")
