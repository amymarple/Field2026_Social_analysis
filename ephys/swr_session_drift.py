r"""Electrode movement from the LFP, cohort 2026c (plan implementation_plan/2026-10-09-swr-session-drift.md, written before
computing): (a) per-session laminar profiles vs the block reference, (b) within-session hourly ripple trends.

Usage:  python ephys/swr_session_drift.py scan [--workers 5] [--run DIR]      (swr_channel_scan.py --hours 1 per session)
        python ephys/swr_session_drift.py profiles --run DIR
        python ephys/swr_session_drift.py hourly --run DIR
        python ephys/swr_session_drift.py --selftest

Definitions:
  profiles   per live column (final channel order, top -> bottom per shank): ratio = NREM ripple-envelope ratio, spw =
             spw_ref_uV (swr_channel_scan.py, 1-h most-NREM window). Whole probe: r_ratio = Pearson r of log(ratio), r_spw =
             Pearson r of spw, each vs the block reference session. Per shank: peak = depth index of the ratio maximum;
             shift s in [-4, 4] = the integer that maximises corr(ref[i], ses[i + s]) over >= 8 overlapping live sites
             (s > 0 = the profile sits s sites deeper on the shank than in the reference); zero = the interpolated depth of
             the first sign change of spw along the shank.
  candidate  |s| >= 1 with one sign on >= half of the eligible shanks in BOTH profiles (ratio: shanks whose reference
             maximum ratio >= 2; spw: shanks whose reference spw range >= 20 uV), or r_ratio < 0.8 and r_spw < 0.8.
  hourly     kept NREM SWR events per session in 1-h bins since the session start (>= 30 events): y = log(median / the
             session median) of the amplitude and of each env_ratio_*; WLS per animal x block on session fixed effects +
             elapsed hours + 2-harmonic clock, weights = events, SEs clustered by session -> slope in % per hour.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _common import git_commit, report_dir, write_json  # noqa: E402

COHORT = "2026c"
LFP_ROOT = "Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/lfp"
SWR_ROOT = "Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/swr"
STATES = "D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final"
MAX_S, MIN_OVERLAP = 4, 8


# ------------------------------------------------------------------ pure pieces (selftested)
def best_shift(ref: np.ndarray, ses: np.ndarray, max_s: int = MAX_S, min_overlap: int = MIN_OVERLAP) -> tuple[float, float]:
    """(s, r): the integer s in [-max_s, max_s] maximising Pearson r of ref[i] vs ses[i + s] over live sites."""
    best = (np.nan, -np.inf)
    n = len(ref)
    for s in range(-max_s, max_s + 1):
        i = np.arange(max(0, -s), min(n, n - s))
        a, b = ref[i], ses[i + s]
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() < min_overlap or np.std(a[m]) == 0 or np.std(b[m]) == 0:
            continue
        r = float(np.corrcoef(a[m], b[m])[0, 1])
        if r > best[1] + 1e-12 or (abs(r - best[1]) <= 1e-12 and abs(s) < abs(best[0])):
            best = (float(s), r)
    return best if np.isfinite(best[1]) else (np.nan, np.nan)


def zero_cross(v: np.ndarray) -> float:
    """Interpolated depth index of the first sign change along the shank (live sites only), NaN if none."""
    idx = np.flatnonzero(np.isfinite(v))
    for a, b in zip(idx[:-1], idx[1:]):
        if v[a] == 0:
            return float(a)
        if np.sign(v[a]) != np.sign(v[b]) and v[b] != 0:
            return float(a + (b - a) * v[a] / (v[a] - v[b]))
    return np.nan


# ------------------------------------------------------------------ sessions
def session_table(a) -> pd.DataFrame:
    q = pd.read_csv(a.quality)
    q["block_from"] = q.block_from.fillna("start")
    ok = [(Path(a.lfp_root) / r.animal / f"{r.session}.lfp.json").exists() and (Path(a.states_root) / r.animal / f"{r.session}.states.npz").exists()
          for r in q.itertuples()]
    return q[ok].reset_index(drop=True)


def scan(a):
    from concurrent.futures import ThreadPoolExecutor
    from output_paths import run_dir
    out = Path(a.run) if a.run else run_dir("swr_session_drift", COHORT)
    sd = out / "scans"
    sd.mkdir(parents=True, exist_ok=True)
    S = session_table(a)
    todo = [r for r in S.itertuples() if not (sd / f"{r.animal}_{r.session}_scan.csv").exists()]
    print(f"run {out}: {len(S)} sessions, {len(todo)} to scan", flush=True)
    t0 = time.time()

    def one(r):
        log = sd / f"{r.animal}_{r.session}.log"
        cmd = [sys.executable, str(HERE / "swr_channel_scan.py"), "--animal", r.animal, "--session", r.session, "--out", str(sd),
               "--hours", "1", "--lfp-root", a.lfp_root, "--states-root", a.states_root]
        with open(log, "w") as fh:
            rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT).returncode
        print(f"  {r.animal} {r.session}: rc {rc} ({time.time() - t0:.0f} s)", flush=True)
        return r.animal, r.session, rc

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        res = list(ex.map(one, todo))
    write_json(out / "scan_meta.json", dict(git=git_commit(), n_sessions=len(S), failed=[x for x in res if x[2] != 0],
                                            minutes=(time.time() - t0) / 60))
    print(f"scans done in {(time.time() - t0) / 60:.1f} min; failed {sum(x[2] != 0 for x in res)}", flush=True)


# ------------------------------------------------------------------ (a) profiles
def load_scan(sd: Path, animal: str, session: str) -> pd.DataFrame | None:
    f = sd / f"{animal}_{session}_scan.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    d.loc[d.skip.astype(bool), ["ratio", "spw_ref_uV"]] = np.nan
    return d


def compare(ref: pd.DataFrame, ses: pd.DataFrame) -> tuple[dict, list[dict]]:
    m = ref[["col", "ratio", "spw_ref_uV"]].merge(ses[["col", "ratio", "spw_ref_uV"]], on="col", suffixes=("_r", "_s"))
    lr, ls = np.log(m.ratio_r), np.log(m.ratio_s)
    ok = np.isfinite(lr) & np.isfinite(ls)
    r_ratio = float(np.corrcoef(lr[ok], ls[ok])[0, 1]) if ok.sum() > 5 else np.nan
    ok2 = np.isfinite(m.spw_ref_uV_r) & np.isfinite(m.spw_ref_uV_s)
    r_spw = float(np.corrcoef(m.spw_ref_uV_r[ok2], m.spw_ref_uV_s[ok2])[0, 1]) if ok2.sum() > 5 else np.nan
    rows = []
    for sh, g in ref.groupby("shank"):
        g = g.sort_values("depth_index")
        h = ses[ses.shank == sh].set_index("depth_index").reindex(g.depth_index)
        a_r, a_s = np.log(g.ratio.to_numpy(float)), np.log(h.ratio.to_numpy(float))
        w_r, w_s = g.spw_ref_uV.to_numpy(float), h.spw_ref_uV.to_numpy(float)
        rip_ok = np.nanmax(g.ratio.to_numpy(float)) >= 2 if np.isfinite(g.ratio).any() else False
        spw_ok = (np.nanmax(w_r) - np.nanmin(w_r)) >= 20 if np.isfinite(w_r).any() else False
        sr, rr = best_shift(a_r, a_s)
        sw, rw = best_shift(w_r, w_s)
        pr = int(np.nanargmax(np.exp(a_r))) if np.isfinite(a_r).any() else np.nan
        ps = int(np.nanargmax(np.exp(a_s))) if np.isfinite(a_s).any() else np.nan
        rows.append(dict(shank=int(sh), ripple_shank=bool(rip_ok), spw_shank=bool(spw_ok), shift_ratio=sr, r_shift_ratio=rr,
                         shift_spw=sw, r_shift_spw=rw, peak_ref=pr, peak_ses=ps, d_peak=(ps - pr) if np.isfinite(pr) and np.isfinite(ps) else np.nan,
                         zero_ref=zero_cross(w_r), zero_ses=zero_cross(w_s)))
    return {"r_ratio": r_ratio, "r_spw": r_spw}, rows


def verdict(sh: pd.DataFrame, r_ratio: float, r_spw: float) -> tuple[bool, float, float]:
    def consistent(col, elig):
        v = sh.loc[sh[elig], col].dropna()
        if not len(v):
            return False, np.nan
        nz = v[v != 0]
        same = (len(nz) >= max(1, int(np.ceil(len(v) / 2)))) and (np.all(nz > 0) or np.all(nz < 0))
        return bool(same), float(np.median(v))
    cr, mr = consistent("shift_ratio", "ripple_shank")
    cs, ms = consistent("shift_spw", "spw_shank")
    same_dir = cr and cs and np.sign(mr) == np.sign(ms)
    low_r = (r_ratio < 0.8) and (r_spw < 0.8)
    return bool(same_dir or low_r), mr, ms


def profiles(a):
    out = Path(a.run)
    sd = out / "scans"
    S = session_table(a)
    S["start_t"] = pd.to_datetime(S.start)
    rows, shrows = [], []
    for (an, bk), g in S.sort_values("start_t").groupby(["animal", "block"], sort=False):
        ref_name = g.reference.iloc[0]
        ref = load_scan(sd, an, ref_name)
        prev = None
        for r in g.sort_values("start_t").itertuples():
            ses = load_scan(sd, an, r.session)
            if ses is None or ref is None:
                rows.append(dict(animal=an, block=bk, session=r.session, start=r.start, tier=r.tier, scanned=ses is not None))
                continue
            w, sh = compare(ref, ses)
            sh = pd.DataFrame(sh)
            cand, mr, ms = verdict(sh, w["r_ratio"], w["r_spw"])
            row = dict(animal=an, block=bk, block_from=r.block_from, session=r.session, start=r.start, tier=r.tier, scanned=True,
                       is_reference=r.session == ref_name, **w, shift_ratio_median=mr, shift_spw_median=ms, candidate=cand)
            if prev is not None:
                wp, shp = compare(prev[1], ses)
                shp = pd.DataFrame(shp)
                cp, mrp, msp = verdict(shp, wp["r_ratio"], wp["r_spw"])
                row.update(prev_session=prev[0], r_ratio_prev=wp["r_ratio"], r_spw_prev=wp["r_spw"], shift_ratio_prev=mrp,
                           shift_spw_prev=msp, candidate_prev=cp)
            rows.append(row)
            shrows += [dict(animal=an, block=bk, session=r.session, **x) for x in sh.to_dict("records")]
            prev = (r.session, ses)
    P = pd.DataFrame(rows)
    SH = pd.DataFrame(shrows)
    P.to_csv(out / "profiles_by_session.csv", index=False)
    SH.to_csv(out / "profiles_by_shank.csv", index=False)
    print(P[["animal", "block", "session", "tier", "is_reference", "r_ratio", "r_spw", "shift_ratio_median", "shift_spw_median",
             "candidate", "candidate_prev"]].round(2).to_string(index=False))
    write_json(out / "profiles_meta.json", dict(git=git_commit(), n=len(P), n_candidates=int(P.candidate.fillna(False).sum())))


# ------------------------------------------------------------------ (b) hourly
def hourly(a):
    import statsmodels.formula.api as smf
    from scipy import stats
    out = Path(a.run)
    S = session_table(a)
    S = S[S.tier.isin(["validated", "good", "check"])]
    rows = []
    for r in S.itertuples():
        f = Path(a.swr_root) / r.animal / r.session / f"{r.session}.swr_events.npz"
        if not f.exists():
            continue
        z = np.load(f, allow_pickle=True)
        m = (~z["excluded"].astype(bool)) & (z["state"] == "NREM")
        if m.sum() < 200:
            continue
        cols = {"amplitude": z["amplitude"][m]}
        for k in z.files:
            if k.startswith("env_ratio_"):
                cols[k] = z[k][m]
        t = z["peak_s"][m]
        b = np.floor(t / 3600).astype(int)
        t0 = pd.Timestamp(r.start)
        for c, v in cols.items():
            med_s = np.nanmedian(v)
            if not np.isfinite(med_s) or med_s <= 0:
                continue
            for k in np.unique(b):
                vv = v[b == k]
                if len(vv) < 30:
                    continue
                clock = t0 + pd.Timedelta(seconds=float(np.median(t[b == k])))
                h = clock.hour + clock.minute / 60
                rows.append(dict(animal=r.animal, block=r.block, session=r.session, feature=c, bin=int(k), elapsed_h=k + 0.5, n=len(vv),
                                 y=float(np.log(np.nanmedian(vv) / med_s)), hs1=np.sin(2 * np.pi * h / 24), hc1=np.cos(2 * np.pi * h / 24),
                                 hs2=np.sin(4 * np.pi * h / 24), hc2=np.cos(4 * np.pi * h / 24)))
    H = pd.DataFrame(rows)
    H.to_csv(out / "hourly_bins.csv.gz", index=False)
    res = []
    for (an, bk, ft), g in H.groupby(["animal", "block", "feature"]):
        if g.session.nunique() < 2 or len(g) < 10:
            continue
        mdl = smf.wls("y ~ C(session) + elapsed_h + hs1 + hc1 + hs2 + hc2", data=g, weights=g.n).fit(
            cov_type="cluster", cov_kwds={"groups": pd.factorize(g.session)[0], "use_correction": True})
        G = g.session.nunique()
        tq = stats.t.ppf(0.975, G - 1)
        e, se = float(mdl.params["elapsed_h"]), float(mdl.bse["elapsed_h"])
        res.append(dict(animal=an, block=bk, feature=ft, sessions=G, bins=len(g), slope_pct_per_h=100 * (np.exp(e) - 1),
                        lo=100 * (np.exp(e - tq * se) - 1), hi=100 * (np.exp(e + tq * se) - 1)))
    R = pd.DataFrame(res)
    R["trend"] = (R.lo > 0) | (R.hi < 0)
    R["beyond_2pct"] = R.trend & (R.slope_pct_per_h.abs() > 2)
    R.to_csv(out / "hourly_slopes.csv", index=False)
    # per session: last 2 h vs first 2 h (amplitude)
    A = H[H.feature == "amplitude"]
    ses = []
    for (an, bk, s), g in A.groupby(["animal", "block", "session"]):
        if g.bin.max() < 3:
            continue
        f2, l2 = g[g.bin <= g.bin.min() + 1], g[g.bin >= g.bin.max() - 1]
        if not len(f2) or not len(l2) or g.bin.max() - g.bin.min() < 3:
            continue
        ses.append(dict(animal=an, block=bk, session=s, hours=int(g.bin.max() + 1),
                        last2_over_first2=float(np.exp(np.average(l2.y, weights=l2.n) - np.average(f2.y, weights=f2.n)))))
    SS = pd.DataFrame(ses)
    SS.to_csv(out / "hourly_first_last.csv", index=False)
    print(R.round(2).to_string(index=False))
    print(SS.describe().round(3).to_string())
    write_json(out / "hourly_meta.json", dict(git=git_commit(), n_sessions=int(H.session.nunique()), n_bins=len(H)))


# ------------------------------------------------------------------ report
def report(a):
    out = Path(a.run)
    P = pd.read_csv(out / "profiles_by_session.csv")
    R = pd.read_csv(out / "hourly_slopes.csv")
    SS = pd.read_csv(out / "hourly_first_last.csv")
    rd = report_dir(COHORT)
    for nm in ("profiles_by_session", "profiles_by_shank", "hourly_slopes", "hourly_first_last"):
        pd.read_csv(out / f"{nm}.csv").to_csv(rd / f"ephys_spikes_swr_session_drift_{nm}_{COHORT}.csv", index=False)
    Ps = P[P.scanned.fillna(False) & ~P.is_reference.fillna(False)]
    L = [f"# Electrode movement from the LFP (cohort {COHORT}): per-session laminar profiles and within-session ripple trends", "",
         "Plan (before computing): [2026-10-09-swr-session-drift.md](../../../../implementation_plan/2026-10-09-swr-session-drift.md). "
         f"Driver `ephys/swr_session_drift.py`; run `{out}`. Requested by the spike-sorting session.", "",
         "## (a) Laminar profile vs the block reference", "",
         f"{len(Ps)} non-reference sessions scanned (1-h most-NREM window).",
         f"- **Movement candidates vs the block reference:** {int(Ps.candidate.fillna(False).sum())}.",
         f"- **vs the previous session of the block** (the battery-round step): {int(Ps.candidate_prev.fillna(False).sum())}.", "",
         "Per block (sessions in time order; 'stable from' = the first session after the last candidate):", "",
         "| animal | block | sessions | candidates | first candidate | last candidate | stable from | min r SPW | min r ratio |",
         "|---|---|---:|---:|---|---|---|---:|---:|"]
    for (an, bk), g in Ps.assign(start_t=pd.to_datetime(Ps.start)).sort_values("start_t").groupby(["animal", "block"], sort=False):
        c = g[g.candidate.fillna(False).astype(bool)]
        after = g[g.start_t > c.start_t.max()] if len(c) else g
        L.append(f"| {an} | {bk} | {len(g)} | {len(c)} | {c.start.min() if len(c) else '–'} | {c.start.max() if len(c) else '–'} | "
                 f"{after.start.min() if len(after) else '–'} | {g.r_spw.min():.2f} | {g.r_ratio.min():.2f} |")
    L += ["", "All sessions:", "",
         "| animal | block | session | tier | r ratio | r SPW | shift ratio (median, sites) | shift SPW | candidate | vs previous: r ratio / r SPW | candidate (prev) |",
         "|---|---|---|---|---:|---:|---:|---:|:---:|---|:---:|"]
    for r in P.itertuples():
        if not getattr(r, "scanned", False) or r.is_reference:
            continue
        prev = f"{r.r_ratio_prev:.2f} / {r.r_spw_prev:.2f}" if pd.notna(getattr(r, "r_ratio_prev", np.nan)) else "–"
        L.append(f"| {r.animal} | {r.block} | {r.session} | {r.tier} | {r.r_ratio:.2f} | {r.r_spw:.2f} | {r.shift_ratio_median:+.1f} | "
                 f"{r.shift_spw_median:+.1f} | {'**yes**' if r.candidate else 'no'} | {prev} | {'**yes**' if r.candidate_prev is True else 'no'} |")
    L += ["", "## (b) Within-session hourly trend (kept NREM events; session fixed effects + 2-harmonic clock)", "",
          "| animal | block | feature | sessions | slope % / h | 95 % CI | trend | beyond ±2 %/h |", "|---|---|---|---:|---:|---|:---:|:---:|"]
    for r in R.itertuples():
        L.append(f"| {r.animal} | {r.block} | {r.feature} | {r.sessions} | {r.slope_pct_per_h:+.2f} | [{r.lo:+.2f}, {r.hi:+.2f}] | "
                 f"{'yes' if r.trend else 'no'} | {'**yes**' if r.beyond_2pct else 'no'} |")
    L += ["", f"Per session, amplitude last 2 h / first 2 h: median {SS.last2_over_first2.median():.3f}, IQR "
          f"{SS.last2_over_first2.quantile(0.25):.3f}–{SS.last2_over_first2.quantile(0.75):.3f}, "
          f"{int((SS.last2_over_first2 < 0.8).sum())} below 0.8 and {int((SS.last2_over_first2 > 1.25).sum())} above 1.25 of {len(SS)}.", "",
          "## Definitions", "",
          "- **Profiles:** `swr_channel_scan.py`. `ratio` = NREM ripple-envelope ratio per column; `spw_ref_uV` = the sharp wave at "
          "the session's own ripple events (± 15 ms 1–50 Hz minus a ± 150–250 ms baseline).",
          "- **Shift:** the integer $s \\in [-4,4]$ maximising $\\mathrm{corr}(\\mathrm{ref}_i, \\mathrm{ses}_{i+s})$ along a shank "
          "(≥ 8 live sites). $s > 0$ = the profile sits $s$ sites deeper than in the reference.",
          "- **Candidate:** |s| ≥ 1 with one sign on ≥ half of the eligible shanks in both profiles, or whole-probe r < 0.8 in both.",
          "- **Hourly:** y = log(bin median / session median), 1-h bins since the session start (≥ 30 events). Model: WLS on "
          "session fixed effects + elapsed hours + clock harmonics; weights = events; SEs clustered by session.", "",
          "## Limits", "",
          "- A shift is in channel steps of the final order. The site pitch is not converted.",
          "- Ripple amplitude follows state and depth as well as position.",
          "- Low-contrast blocks (SF11 after 09-02 19:08, SF12 block 3) have no SWR-specific profile.", ""]
    p = rd / f"ephys_spikes_swr_session_drift_{COHORT}.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    write_json(rd / f"run_manifest_swr_session_drift_{COHORT}.json", dict(name="swr_session_drift", run_dir=str(out), git=git_commit(), report=str(p)))
    print(f"report {p}")


def selftest():
    ok = True
    x = np.sin(np.linspace(0, 3, 16)) + np.linspace(0, 1, 16)
    y = np.full(16, np.nan)
    y[2:] = x[:-2]                                                    # features 2 sites deeper
    s, r = best_shift(x, y)
    a = s == 2 and r > 0.99
    print(f"{'PASS' if a else 'FAIL'} best_shift {s} r {r:.3f}")
    ok &= a
    s0, r0 = best_shift(x, x.copy())
    b = s0 == 0 and r0 > 0.999
    print(f"{'PASS' if b else 'FAIL'} best_shift identity {s0}")
    ok &= b
    v = np.array([30.0, 20.0, 10.0, np.nan, -10.0, -20.0])
    zc = zero_cross(v)
    c = abs(zc - 3.0) < 1e-9 and np.isnan(zero_cross(np.array([1.0, 2.0, 3.0])))
    print(f"{'PASS' if c else 'FAIL'} zero_cross {zc}")
    ok &= c
    sh = pd.DataFrame(dict(shift_ratio=[1, 1, 0], ripple_shank=[True, True, True], shift_spw=[1, 2, np.nan], spw_shank=[True, True, False]))
    d = verdict(sh, 0.95, 0.95)[0] and not verdict(sh.assign(shift_spw=[-1, -1, np.nan]), 0.95, 0.95)[0]
    print(f"{'PASS' if d else 'FAIL'} verdict (same sign needed)")
    ok &= d
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["scan", "profiles", "hourly", "report"])
    ap.add_argument("--run", default=None)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--lfp-root", default=LFP_ROOT)
    ap.add_argument("--swr-root", default=SWR_ROOT)
    ap.add_argument("--states-root", default=STATES)
    ap.add_argument("--quality", default=str(report_dir(COHORT) / f"ephys_spikes_swr_quality_{COHORT}.csv"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    {"scan": scan, "profiles": profiles, "hourly": hourly, "report": report}[a.cmd](a)


if __name__ == "__main__":
    main()
