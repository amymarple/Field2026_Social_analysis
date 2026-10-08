r"""Phase 2b of the internal-schedule analysis: the user's follow-up questions on Phase 2 (plan Amendment 3).
Called by `python ephys/sleep_schedule.py phase2b`. Reads the Phase-1 / Phase-2 run folders (manifests) for the saved
per-bout predictions and compensation windows; recomputes what it needs from the FINAL 1-s states and metrics.

Definitions (FINAL 1-s states + the scorer's per-second metrics sw, th, emg in the same npz; field-PC time):
  z-metrics      per session, each metric (sw = -IRASA slope 4-90 Hz, the scorer's slow-wave / depth measure; th =
                 theta ratio; emg = head-IMU VeDBA) is z-scored with the mean and SD of that session's NREM seconds, so
                 sessions with different probe positions / thresholds become comparable. NOTE: the scorer defines NREM
                 by sw above a threshold (15-s smoothing), so sw right before a transition is partly the transition's
                 own definition; depth used as a predictor is therefore lagged (below).
  E1 effect size per held-out NREM bout with an observed end, the model's probability that the bout ends in REM (pi, from
                 the Phase-1 / Phase-2 opportunity split); bouts pooled over folds and cut into deciles of pi; reported:
                 the share of bouts that actually ended in REM per decile (top vs bottom), for the model without and with
                 history (Phase 1 M0 vs M2; Phase 2 B1 R0 vs C1).
  E2 depth       (a) long wakes (>= 7 min, as B1b): depth = mean z-sw over the first 120 s of NREM after the wake;
                 OLS depth ~ ln d + phase + animal, then ln|N|_1 ~ ln d + depth + ln(1+N_pre) + anchor + phase + animal
                 (SEs clustered by block): is post-wake NREM deeper after longer wakes, and does the wake-length effect
                 remain with depth controlled?
                 (b) the REM hazard: lagged depth z_sw_lag = mean z-sw over the NREM seconds in [t-150, t-30) s before
                 each 10-s step; held-out comparison M2t vs M2t + [z_sw_lag] (forward chaining), and the empirical REM
                 hazard against total NREM since the last REM per tertile of z_sw_lag (description).
  E3 tails       z-metric traces over the 180 s before: natural NREM -> WAKE and NREM -> REM transitions (>= 60 s NREM
                 before, >= 180 s after the session start), and the END of the last session before a usable gap
                 (Phase-0 gaps; the logger's Record Stop or auto-stop), split by gap cause and by how the cell ended.
                 Reported: mean +- SEM traces, the state in the last second, NREM share of the last 60 s.
  E4 circadian   the across-gap compensation slopes (Phase-2 C1 windows, both scorings) split by morning vs evening rounds.
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
from sleep_schedule_phase2 import (MA_LIMITS, build_steps, compare, comp_slopes, forward_folds, run_cv,  # noqa: E402
                                   wake_to_kth_rem)
import sleep_schedule_phase2 as P2  # noqa: E402

JOIN_S = 60


def records_with_metrics(rv: pd.DataFrame, states_dir: Path) -> list[dict]:
    """build_records (sleep_cycles_v2) + per-second z-metrics (NaN in joins); state arrays identical to build_records."""
    recs = []
    for an, g in rv.sort_values("start").groupby("animal"):
        cur = None
        for r in g.itertuples():
            with np.load(states_dir / an / f"{r.session}.states.npz") as z:
                st = z["state"].astype(np.int8)
                mets = {k: z[k].astype(np.float64) for k in ("sw", "th", "emg")}
            n_ok = int(max(0, min(len(st), (r.end_cut - r.start).total_seconds())))
            st = st[:n_ok]
            if not len(st):
                continue
            nrem = st == N
            zm = {}
            for k, v in mets.items():
                v = v[:n_ok]
                mu, sd = (np.nanmean(v[nrem]), np.nanstd(v[nrem])) if nrem.sum() > 30 else (np.nanmean(v), np.nanstd(v))
                zm[k] = (v - mu) / (sd if sd > 0 else 1.0)
            if cur is not None:
                gap = (r.start - cur["end"]).total_seconds()
                if 0 <= gap <= JOIN_S:
                    k = int(round(gap))
                    cur["state"] = np.concatenate([cur["state"], np.zeros(k, np.int8), st])
                    for m in zm:
                        cur[m] = np.concatenate([cur[m], np.full(k, np.nan), zm[m]])
                    cur["end"] = cur["start"] + pd.Timedelta(seconds=len(cur["state"]))
                    cur["sessions"].append(r.session)
                    continue
                recs.append(cur)
            cur = {"animal": an, "start": r.start, "end": r.start + pd.Timedelta(seconds=len(st)), "state": st,
                   "sessions": [r.session], **zm}
        if cur is not None:
            recs.append(cur)
    for i, rc in enumerate(recs):
        h = rc["start"].hour
        d = rc["start"].normalize() - (pd.Timedelta(days=1) if h < 6 else pd.Timedelta(0))
        rc["block"] = f"{d:%Y-%m-%d}{'D' if 6 <= h < 18 else 'N'}"
        rc["record_id"] = i
    return recs


def lagged_depth(rc: dict, t_idx: np.ndarray, lo: int = 150, hi: int = 30) -> np.ndarray:
    st, sw = rc["state"], rc["sw"]
    m = (st == N) & np.isfinite(sw)
    cs = np.r_[0, np.cumsum(np.where(m, sw, 0.0))]
    cnt = np.r_[0, np.cumsum(m)]
    a = np.clip(t_idx - lo, 0, len(st))
    b = np.clip(t_idx - hi, 0, len(st))
    k = cnt[b] - cnt[a]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(k >= 20, (cs[b] - cs[a]) / np.maximum(k, 1), np.nan)


def phase2b(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import statsmodels.api as sm
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_quant import md_table, save_fig
    out = run_dir("sleep_schedule_phase2b" + ("_smoke" if a.smoke else ""), "2026c")
    rd, fd = (out, out) if a.smoke else (report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes"))
    gc = git_commit()
    man = lambda n: json.load(open(ROOT / f"results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_{n}_2026c.json"))["run_dir"]  # noqa: E731
    p0, p1, p2 = Path(man("phase0")), Path(man("phase1")), Path(man("phase2"))
    rv = included_sessions(Path(a.review), Path(a.states))
    recs = records_with_metrics(rv, Path(a.states))
    from sleep_cycles_v2 import build_records
    ref = build_records(rv, Path(a.states))
    assert len(ref) == len(recs) and all(np.array_equal(x["state"], y["state"]) for x, y in zip(ref, recs)), "records differ"
    L = ["# Internal sleep schedule — Phase 2b: effect sizes, NREM depth, NREM tails, morning vs evening (cohort 2026c)", "",
         f"Plan: [2026-10-07-sleep-internal-schedule.md](../../../../implementation_plan/2026-10-07-sleep-internal-schedule.md) "
         f"(Amendment 3). Driver `ephys/sleep_schedule.py phase2b` → `ephys/sleep_schedule_phase2b.py` (commit {gc}); bulk "
         f"`{out}`. **Technical ledger; no claim audit yet.**", "", "## Definitions", "", "```",
         (sys.modules[__name__].__doc__ or "").strip(), "```", ""]

    # ---------------- E1 effect sizes
    rows = []
    for src, lo_m, hi_m, path in (("Phase 1, all NREM bouts", "M0", "M2", p1 / "split_by_bout.csv.gz"),
                                  ("Phase 2 B1, post-wake bouts", "R0", "C1", p2 / "b1_split_by_bout.csv.gz")):
        S = pd.read_csv(path)
        for m in (lo_m, hi_m):
            s = S[S.model == m].copy()
            s["dec"] = pd.qcut(s.pi_rem.rank(method="first"), 10, labels=False)
            g = s.groupby("dec").agg(pi=("pi_rem", "mean"), obs=("type", lambda v: (v == 1).mean()), n=("type", "size"))
            rows.append({"source": src, "model": m, "bouts": len(s), "obs_REM_share_bottom_decile": g.obs.iloc[0],
                         "obs_REM_share_top_decile": g.obs.iloc[-1], "pred_pi_bottom": g.pi.iloc[0], "pred_pi_top": g.pi.iloc[-1],
                         "pi_p10": s.pi_rem.quantile(0.1), "pi_p90": s.pi_rem.quantile(0.9), "overall_REM_share": (s.type == 1).mean()})
    E1 = pd.DataFrame(rows)
    E1.to_csv(rd / "ephys_spikes_sleep_schedule_phase2b_e1_2026c.csv", index=False)
    L += ["## E1 Effect size on an interpretable scale", "",
          "Share of held-out NREM bouts that actually ended in REM, among the 10 % the model rated least vs most likely "
          "to end in REM.", "", md_table(E1.round(3)), ""]
    print(E1.round(3).to_string(index=False), flush=True)

    # ---------------- E2 depth (a) long wakes
    D = wake_to_kth_rem(recs)
    rows = []
    for rc in recs:
        st, sw = rc["state"], rc["sw"]
        bl = bouts(st)
        for i, (s, a0, b0) in enumerate(bl):
            if s == W and (b0 - a0) >= 420 and i + 1 < len(bl) and bl[i + 1][0] == N:
                seg_s, seg_w = st[b0:b0 + 600], sw[b0:b0 + 600]
                m = (seg_s == N) & np.isfinite(seg_w)
                idx = np.flatnonzero(m)[:120]
                rows.append({"animal": rc["animal"], "block": rc["block"], "d_s": b0 - a0, "t_end": rc["start"] + pd.Timedelta(seconds=b0),
                             "depth": float(np.mean(seg_w[idx])) if len(idx) >= 60 else np.nan})
    Dd = pd.DataFrame(rows)
    D1 = D[D.k == 1].reset_index(drop=True)
    D1 = D1.merge(Dd.drop_duplicates(["animal", "d_s", "block"]), on=["animal", "block", "d_s"], how="left").dropna(subset=["depth"])

    def ph(df):
        h = df.t_end.dt.hour + df.t_end.dt.minute / 60
        return pd.DataFrame({f"{f}{k}": fn(2 * np.pi * k * h / 24) for k in (1, 2) for f, fn in (("sin", np.sin), ("cos", np.cos))}, index=df.index)
    Xa = sm.add_constant(pd.concat([pd.DataFrame({"l_d": np.log(D1.d_s)}), ph(D1), pd.get_dummies(D1.animal, drop_first=True, dtype=float)], axis=1))
    fa = sm.OLS(D1.depth, Xa).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(D1.block)[0]})
    base_cols = pd.DataFrame({"l_d": np.log(D1.d_s), "l_npre": np.log1p(D1.n_pre), "anchor": D1.anchor})
    Xb0 = sm.add_constant(pd.concat([base_cols, ph(D1), pd.get_dummies(D1.animal, drop_first=True, dtype=float)], axis=1))
    Xb1 = Xb0.assign(depth=D1.depth)
    y = np.log(D1.n_k.clip(lower=1))
    fb0 = sm.OLS(y, Xb0).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(D1.block)[0]})
    fb1 = sm.OLS(y, Xb1).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(D1.block)[0]})
    E2a = pd.DataFrame([
        {"model": "depth ~ ln d", "term": "l_d", "coef": fa.params["l_d"], "se": fa.bse["l_d"], "p": fa.pvalues["l_d"], "n": len(D1)},
        {"model": "ln|N|_1 ~ ln d (+ N_pre, phase, animal)", "term": "l_d", "coef": fb0.params["l_d"], "se": fb0.bse["l_d"], "p": fb0.pvalues["l_d"], "n": len(D1)},
        {"model": "ln|N|_1 ~ ln d + depth (+ same)", "term": "l_d", "coef": fb1.params["l_d"], "se": fb1.bse["l_d"], "p": fb1.pvalues["l_d"], "n": len(D1)},
        {"model": "ln|N|_1 ~ ln d + depth (+ same)", "term": "depth", "coef": fb1.params["depth"], "se": fb1.bse["depth"], "p": fb1.pvalues["depth"], "n": len(D1)}])
    E2a.to_csv(rd / "ephys_spikes_sleep_schedule_phase2b_e2a_2026c.csv", index=False)
    print(E2a.round(4).to_string(index=False), flush=True)

    # ---------------- E2 depth (b) hazard
    steps = build_steps(recs)
    zl = np.full(len(steps), np.nan)
    for rid, g in steps.groupby("record_id"):
        rc = recs[rid]
        zl[g.index] = lagged_depth(rc, (g.bout_start + g.elapsed).to_numpy().astype(int))
    steps["z_sw_lag"] = zl
    st2 = steps.dropna(subset=["z_sw_lag"]).copy()
    orig_feats2 = P2.feats2

    def feats2_depth(df):
        f = orig_feats2(df)
        f["z_sw_lag"] = df.z_sw_lag.astype(float) if "z_sw_lag" in df else 0.0
        return f
    P2.feats2 = feats2_depth
    orig_design2 = P2.design2

    def design2_depth(f, animals, terms, st, levels):
        X, st = orig_design2(f, animals, [t for t in terms if t != "depth"], st, levels)
        if "depth" in terms:
            z = (f["z_sw_lag"] - st["mu"]["z_sw_lag"]) / st["sd"]["z_sw_lag"]
            X = np.column_stack([X, z.to_numpy()])
        return X, st
    P2.design2 = design2_depth
    F, _, FA, _ = run_cv(st2, {"M2t": ["L1", "ntspl", "wsince", "rem"], "M2t_depth": ["L1", "ntspl", "wsince", "rem", "depth"]},
                         forward_folds(st2))
    P2.feats2, P2.design2 = orig_feats2, orig_design2
    E2b = pd.DataFrame([compare(F, FA, "M2t", "M2t_depth", "NREM steps with >= 20 s of NREM in the lag window")])
    E2b.to_csv(rd / "ephys_spikes_sleep_schedule_phase2b_e2b_2026c.csv", index=False)
    print(E2b.round(3).to_string(index=False), flush=True)
    s_ = st2[st2.has_anchor == 1].copy()
    s_["n_tot"] = s_.n_since + s_.elapsed
    s_["tert"] = pd.qcut(s_.z_sw_lag, 3, labels=["shallow", "middle", "deep"])
    edges = np.r_[0, 30, 60, 120, 240, 480, 720, 1200, 1800, 3600]
    s_["nb"] = pd.cut(s_.n_tot, edges, right=False)
    H = s_.groupby(["tert", "nb"], observed=True).agg(n=("y", "size"), hR=("y", lambda v: (v == 1).mean()),
                                                     hW=("y", lambda v: (v == 2).mean())).reset_index()
    H["n_tot_mid_min"] = [(iv.left + iv.right) / 120 for iv in H.nb]
    H.drop(columns="nb").to_csv(rd / "ephys_spikes_sleep_schedule_phase2b_e2b_hazard_by_depth_2026c.csv", index=False)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for t, g in H.groupby("tert", observed=True):
        g = g[g.n >= 200]
        ax.plot(g.n_tot_mid_min, g.hR, "o-", label=f"lagged depth: {t}")
    ax.set_xscale("log")
    ax.set_xlabel("total NREM since the last REM (min)")
    ax.set_ylabel("empirical P(REM in the next 10 s)")
    ax.set_title(f"E2 REM hazard by lagged NREM depth (z-sw, [t-150, t-30) s; description)  {gc}", fontsize=8)
    ax.legend(fontsize=8)
    save_fig(fig, fd / "ephys_spikes_sleep_schedule_phase2b_depth_hazard_2026c.png")
    L += ["## E2 NREM depth", "", "(a) Long wakes (≥ 7 min): is post-wake NREM deeper after longer wakes, and does the "
          "wake-length effect on the NREM before the first REM survive with depth controlled?", "", md_table(E2a.round(4)), "",
          "(b) REM hazard: does lagged depth add held-out prediction beyond the running since-REM clock?", "",
          md_table(E2b.round(3)), "", "![](../figures/ephys_spikes_sleep_schedule_phase2b_depth_hazard_2026c.png)", ""]

    # ---------------- E3 tails
    gaps = pd.read_csv(p0 / "gaps.csv", parse_dates=["gap_start", "gap_end"])
    gk = {(r.animal, pd.Timestamp(r.gap_start).floor("s")): r for r in gaps.itertuples()}
    traces, summ = {}, []
    lags = np.arange(-180, 0)
    for rc in recs:
        st = rc["state"]
        bl = bouts(st)
        for i, (s, a0, b0) in enumerate(bl[1:], start=1):
            ps, pa, pb = bl[i - 1]
            if ps == N and s in (W, R) and (pb - pa) >= 60 and a0 >= 180:
                cls = "natural NREM -> WAKE" if s == W else "natural NREM -> REM"
                traces.setdefault(cls, []).append(np.stack([rc[m][a0 + lags] for m in ("sw", "th", "emg")]))
                summ.append({"class": cls, "animal": rc["animal"], "last_state": int(st[a0 - 1]), "nrem_share_60": float(np.mean(st[a0 - 60:a0] == N))})
        key = (rc["animal"], pd.Timestamp(rc["end"]).floor("s"))
        if key in gk and len(st) >= 180:
            g = gk[key]
            if not g.usable:
                continue
            how = str(g.prev_cell_end).lower()
            stop = "auto-stop" if ("yes" in how or "auto" in how) else ("manual Stop / swap" if g.cause.startswith("round") else g.cause)
            cls = f"end before gap: {g.cause} ({stop})"
            tr = np.stack([rc[m][len(st) + lags] for m in ("sw", "th", "emg")])
            traces.setdefault(cls, []).append(tr)
            summ.append({"class": cls, "animal": rc["animal"], "last_state": int(st[-1]), "nrem_share_60": float(np.mean(st[-60:] == N))})
    SU = pd.DataFrame(summ)
    E3 = SU.groupby("class").agg(n=("animal", "size"), animals=("animal", "nunique"),
                                 last_second_NREM=("last_state", lambda v: (v == N).mean()),
                                 last_second_WAKE=("last_state", lambda v: (v == W).mean()),
                                 last_second_REM=("last_state", lambda v: (v == R).mean()),
                                 nrem_share_last_60s=("nrem_share_60", "mean")).reset_index()
    for cls, arr in traces.items():
        A = np.array(arr)
        for j, m in enumerate(("sw", "th", "emg")):
            E3.loc[E3["class"] == cls, f"{m}_mean_last_30s"] = float(np.nanmean(A[:, j, -30:]))
            E3.loc[E3["class"] == cls, f"{m}_mean_-180_-120s"] = float(np.nanmean(A[:, j, :60]))
    E3.to_csv(rd / "ephys_spikes_sleep_schedule_phase2b_e3_2026c.csv", index=False)
    print(E3.round(3).to_string(index=False), flush=True)
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.5), sharex=True)
    for cls, arr in traces.items():
        A = np.array(arr)
        if len(A) < 5:
            continue
        for j, (m, ax) in enumerate(zip(("sw (depth)", "theta", "EMG (head IMU)"), axs)):
            mu, se = np.nanmean(A[:, j], 0), np.nanstd(A[:, j], 0) / np.sqrt(np.sum(np.isfinite(A[:, j]), 0))
            ax.plot(lags, mu, label=f"{cls} (n={len(A)})")
            ax.fill_between(lags, mu - se, mu + se, alpha=0.2)
            ax.set_title(m, fontsize=9)
            ax.set_xlabel("s before the transition / the recording stop")
    axs[0].set_ylabel("z (session NREM mean / SD)")
    axs[0].legend(fontsize=6)
    fig.suptitle(f"E3 NREM tails: natural transitions vs recording stops before gaps (description)  {gc}", fontsize=9)
    save_fig(fig, fd / "ephys_spikes_sleep_schedule_phase2b_tails_2026c.png")
    L += ["## E3 NREM tails: natural transitions vs the recording stop before a gap", "",
          "States and z-metrics in the 180 s before the event. A battery-round stop is a BLE Record Stop (or an auto-stop) "
          "before the animal is caught, so its tail shows the state the round interrupted.", "", md_table(E3.round(3)), "",
          "![](../figures/ephys_spikes_sleep_schedule_phase2b_tails_2026c.png)", ""]

    # ---------------- E4 morning vs evening compensation
    rows = []
    for lab in ("FINAL", "pass2med_remclean"):
        f = p2 / f"c1_windows_{lab}.csv.gz"
        if not f.exists():
            continue
        Wn = pd.read_csv(f)
        Wn = Wn[Wn.setting.str.startswith("across gap (round")].copy()
        Wn["setting"] = Wn.setting.str.replace(r"\(round_\w+\)", "", regex=True).str.strip() + " " + Wn.kind.fillna("?")
        S = comp_slopes(Wn)
        S.insert(0, "scores", lab)
        rows.append(S[S.outcome.isin(["pay_rem", "pay_rem_n", "pay_nrem"]) & ((S.outcome != "pay_nrem") | (S.predictor == "debt_nrem"))])
    E4 = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    E4.to_csv(rd / "ephys_spikes_sleep_schedule_phase2b_e4_2026c.csv", index=False)
    print(E4.round(3).to_string(index=False), flush=True)
    L += ["## E4 Compensation across battery rounds: morning vs evening", "",
          "Across-gap windows of all battery rounds (logged + inferred), split by the round's kind; both scorings.", "",
          md_table(E4.round(3)), ""]
    flat = [ln for x in L for ln in (x if isinstance(x, list) else [x])]
    (rd / "ephys_spikes_sleep_schedule_phase2b_2026c.md").write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_schedule_phase2b_2026c.json", {"run_dir": str(out), "git_commit": gc, "states": str(a.states)})
    print("written", rd / "ephys_spikes_sleep_schedule_phase2b_2026c.md")
