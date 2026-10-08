r"""Phase 5 of the internal-schedule analysis: do the animals enter REM in sync? (plan Amendment 7, written before results)
Called by `python ephys/sleep_schedule.py phase5`.

Definitions (FINAL 1-s states on one absolute field-PC timeline per animal, cut at 09-11 19:40; WISER zone per second from
the default tracks: house_1 / house_2 (wiser_rois.json + 14 in) / field):
  co-located     two animals in the same house at that second (both zone house_1 or both house_2).
  far            the other animal is somewhere else (other house or field) while both zones are known.
  REM onset      a REM bout that starts after >= 60 s of NREM.
  per NREM step of animal B (time t = bout start + elapsed):
    n_mates      co-located other animals with a known state; mates_asleep = their share in NREM or REM (social context,
                 in the BASE model so that huddling alone cannot produce the effect);
    mate_on60    a co-located animal had a REM onset in (t - 60, t];   mate_rem: a co-located animal is in REM at t;
    far_on60, far_rem  the same for animals that are elsewhere (the natural control).
  held out       forward chaining (as Phase 2): S0 = M2t + n_mates + mates_asleep; S_mate = S0 + mate_on60 + mate_rem;
                 S_far = S0 + far_on60 + far_rem. Full-fit REM-vs-stay coefficients per SD; per-animal signs.
  descriptive    among B's NREM steps in a house with >= 1 asleep mate: P(REM in the next 10 s) with vs without a mate
                 onset in the last 60 s, within strata of B's own total NREM since its last REM (weighted ratio); and the
                 share of B's REM seconds during which a co-located asleep mate is also in REM vs during B's NREM seconds.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from sleep_cycles import bouts  # noqa: E402
from sleep_cycles_v2 import build_records  # noqa: E402
from sleep_schedule import N, R, ROOT, included_sessions  # noqa: E402
from sleep_schedule_phase2 import build_steps, compare, fit2, forward_folds, run_cv  # noqa: E402

ANIMALS = ["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"]


def phase5(a) -> None:
    from _common import git_commit, write_json
    from mic_wake_pilot import load_zone
    from output_paths import report_dir, run_dir
    from sleep_quant import md_table
    out = run_dir("sleep_schedule_phase5" + ("_smoke" if a.smoke else ""), "2026c")
    rd = out if a.smoke else report_dir("2026c", "ephys_spikes")
    gc = git_commit()
    rv = included_sessions(Path(a.review), Path(a.states))
    recs = build_records(rv, Path(a.states))
    t_min = min(rc["start"] for rc in recs).floor("s")
    t_max = max(rc["end"] for rc in recs).ceil("s")
    span = int((t_max - t_min).total_seconds()) + 1
    arr, zone, onset = {}, {}, {}
    rois = {r["name"]: r for r in json.load(open(ROOT / "wiser/configs/wiser_rois.json"))["rois"] if r["name"] in ("house_1", "house_2")}
    dates = sorted({d.strftime("%Y%m%d") for d in pd.date_range(t_min.normalize(), t_max.normalize())})
    for an in sorted({rc["animal"] for rc in recs}):
        s = np.zeros(span, np.int8)
        for rc in recs:
            if rc["animal"] == an:
                o = int((rc["start"] - t_min).total_seconds())
                s[o:o + len(rc["state"])] = rc["state"][:max(0, span - o)]
        arr[an] = s
        on = np.zeros(span, bool)
        for st_, a0, b0 in bouts(s):
            pass
        bl = bouts(s)
        for i in range(1, len(bl)):
            (ps, pa, pb), (cs_, ca, _) = bl[i - 1], bl[i]
            if cs_ == R and ps == N and (pb - pa) >= 60:
                on[ca] = True
        onset[an] = np.r_[0, np.cumsum(on)]
        z = load_zone(an, dates, rois)
        zc = np.zeros(span, np.int8)
        if len(z):
            zz = z.reindex(pd.date_range(t_min, t_max, freq="1s")[:span])
            zc = np.select([zz.eq("house_1").to_numpy(), zz.eq("house_2").to_numpy(), zz.eq("field").to_numpy()], [1, 2, 3], 0).astype(np.int8)
        zone[an] = zc
        print(an, "zones", np.bincount(zc, minlength=4), flush=True)
    feats = {}
    for B in arr:
        n_m, n_s = np.zeros(span, np.int16), np.zeros(span, np.int16)
        m_on, m_rem, f_on, f_rem = (np.zeros(span, bool) for _ in range(4))
        idx = np.arange(span)
        for A in arr:
            if A == B:
                continue
            known = arr[A] != 0
            co = (zone[A] == zone[B]) & np.isin(zone[B], (1, 2)) & known
            far = (zone[A] != zone[B]) & (zone[A] > 0) & (zone[B] > 0) & known
            on60 = (onset[A][idx + 1] - onset[A][np.maximum(idx - 59, 0)]) > 0
            n_m += co
            n_s += co & np.isin(arr[A], (N, R))
            m_on |= co & on60
            m_rem |= co & (arr[A] == R)
            f_on |= far & on60
            f_rem |= far & (arr[A] == R)
        feats[B] = (n_m, n_s, m_on, m_rem, f_on, f_rem)
    steps = build_steps(recs)
    ti = ((steps.t - t_min).dt.total_seconds()).astype(int).clip(0, span - 1).to_numpy()
    cols = {k: np.zeros(len(steps)) for k in ("n_mates", "mates_asleep", "mate_on60", "mate_rem", "far_on60", "far_rem")}
    for B, (n_m, n_s, m_on, m_rem, f_on, f_rem) in feats.items():
        sel = (steps.animal == B).to_numpy()
        j = ti[sel]
        cols["n_mates"][sel] = n_m[j]
        cols["mates_asleep"][sel] = np.where(n_m[j] > 0, n_s[j] / np.maximum(n_m[j], 1), 0)
        cols["mate_on60"][sel], cols["mate_rem"][sel] = m_on[j], m_rem[j]
        cols["far_on60"][sel], cols["far_rem"][sel] = f_on[j], f_rem[j]
    for k, v in cols.items():
        steps[k] = v
    print({k: float(np.mean(v)) for k, v in cols.items()}, flush=True)
    base = ["L1", "ntspl", "wsince", "rem", "col:n_mates", "col:mates_asleep"]
    specs = {"S0": base, "S_mate": base + ["col:mate_on60", "col:mate_rem"], "S_far": base + ["col:far_on60", "col:far_rem"]}
    F, _, FA, _ = run_cv(steps, specs, forward_folds(steps))
    T1 = pd.DataFrame([compare(F, FA, "S0", "S_mate", "co-located mates"), compare(F, FA, "S0", "S_far", "animals elsewhere (control)")])
    # full-fit coefficients (REM vs stay, Wake vs stay) for the four social terms
    levels = sorted(steps.animal.unique())
    from sleep_schedule_phase2 import design2, feats2
    rows = []
    for spec, terms in (("S_mate", ["mate_on60", "mate_rem"]), ("S_far", ["far_on60", "far_rem"])):
        m, st = fit2(steps, specs[spec], levels)
        X0, _ = design2(feats2(steps.iloc[:50]), steps.animal.iloc[:50], base, st, levels)
        k0 = X0.shape[1] - (len(levels) - 1)
        cls = list(m.classes_)
        for j, term in enumerate(terms):
            r = {"term": term}
            for lab, c in (("REM_vs_stay", 1), ("Wake_vs_stay", 2)):
                r[lab] = float(m.coef_[cls.index(c)][k0 + j] - m.coef_[cls.index(0)][k0 + j])
            sg = []
            for an, g in steps.groupby("animal"):
                ma, _ = fit2(g, specs[spec], [an])
                ca = list(ma.classes_)
                if 1 in ca:
                    sg.append(np.sign(ma.coef_[ca.index(1)][k0 + j] - ma.coef_[ca.index(0)][k0 + j]))
            r["animals_REM_coef_positive"], r["animals"] = int(np.sum(np.array(sg) > 0)), len(sg)
            rows.append(r)
    T2 = pd.DataFrame(rows)
    # descriptive rate ratio within strata of B's own NREM since REM
    d = steps[(steps.n_mates > 0) & (steps.mates_asleep > 0) & (steps.has_anchor == 1)].copy()
    d["n_tot"] = d.n_since + d.elapsed
    d["nb"] = pd.cut(d.n_tot, [0, 60, 240, 480, 720, 1200, 1800, 1e9], right=False)
    rr = []
    for cue in ("mate_on60", "mate_rem", "far_on60", "far_rem"):
        g = d.groupby(["nb", cue], observed=True).agg(n=("y", "size"), hR=("y", lambda v: (v == 1).mean())).reset_index()
        pv = g.pivot_table(index="nb", columns=cue, values=["hR", "n"], observed=True)
        if (1.0 not in pv["hR"].columns) or (0.0 not in pv["hR"].columns):
            continue
        ok = pv["n"][1.0].fillna(0) >= 50
        ratio = (pv["hR"][1.0] / pv["hR"][0.0])[ok]
        wts = pv["n"][1.0][ok]
        rr.append({"cue": cue, "steps_with_cue": int(pv["n"][1.0].sum()), "steps_without": int(pv["n"][0.0].sum()),
                   "hazard_with": float(np.average(pv["hR"][1.0][ok], weights=wts)), "hazard_without_same_strata": float(np.average(pv["hR"][0.0][ok], weights=wts)),
                   "weighted_ratio": float(np.average(ratio, weights=wts))})
    T3 = pd.DataFrame(rr)
    # simultaneous REM: P(co-located asleep mate in REM | B in REM) vs | B in NREM
    sim = []
    for B in arr:
        for A in arr:
            if A == B:
                continue
            co = (zone[A] == zone[B]) & np.isin(zone[B], (1, 2)) & np.isin(arr[A], (N, R))
            bR, bN = co & (arr[B] == R), co & (arr[B] == N)
            if bR.sum() > 300 and bN.sum() > 3000:
                sim.append({"B": B, "A": A, "B_REM_s": int(bR.sum()), "p_A_REM_given_B_REM": float(np.mean(arr[A][bR] == R)),
                            "p_A_REM_given_B_NREM": float(np.mean(arr[A][bN] == R))})
    T4 = pd.DataFrame(sim)
    if len(T4):
        T4["ratio"] = T4.p_A_REM_given_B_REM / T4.p_A_REM_given_B_NREM
    for name, T in (("t1", T1), ("t2", T2), ("t3", T3), ("t4", T4)):
        T.to_csv(rd / f"ephys_spikes_sleep_schedule_phase5_{name}_2026c.csv", index=False)
        print(T.round(4).to_string(index=False), flush=True)
    L = ["# Internal sleep schedule — Phase 5: do the animals enter REM in sync? (cohort 2026c)", "",
         f"Plan Amendment 7 (written before results). Driver `ephys/sleep_schedule.py phase5` → `ephys/sleep_sync.py` (commit {gc}); "
         f"bulk `{out}`. **Technical ledger; no claim audit yet.**", "", "## Definitions", "", "```", (sys.modules[__name__].__doc__ or "").strip(),
         "```", "", "## Held out: do a mate's REM onset / REM add to predicting this animal's REM entry?", "", md_table(T1.round(3)), "",
         "Full-fit coefficients (per SD; REM vs stay, Wake vs stay) and per-animal signs:", "", md_table(T2.round(3)), "",
         "## Descriptive: REM-entry hazard with vs without the cue, within strata of the animal's own NREM since REM", "", md_table(T3.round(4)), "",
         "## Simultaneous REM: P(co-located asleep mate in REM | this animal in REM) vs | in NREM", "", md_table(T4.round(4)), ""]
    flat = [ln for x in L for ln in (x if isinstance(x, list) else [x])]
    (rd / "ephys_spikes_sleep_schedule_phase5_2026c.md").write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_schedule_phase5_2026c.json", {"run_dir": str(out), "git_commit": gc})
    print("written", rd / "ephys_spikes_sleep_schedule_phase5_2026c.md")


def phase5b(a) -> None:
    """Local, fast coupling of head-movement onsets during sleep between animals (plan Amendment 8, before results).
    Event = IMU state >= 2 after >= 5 s of IMU state 1 (head-IMU seconds cache, field-PC clock), while the FINAL score is
    NREM or REM; pairs both asleep, same house vs elsewhere; cross-correlogram -10..+10 s against the baseline at
    |lag| 30-60 s; direction +1..+3 vs -1..-3 s; cascade = housemates with an event within +5 s vs +30..+60 s."""
    from _common import git_commit, write_json
    from mic_wake_pilot import load_zone
    from output_paths import report_dir, run_dir
    from sleep_quant import md_table
    out = run_dir("sleep_schedule_phase5b" + ("_smoke" if a.smoke else ""), "2026c")
    rd = out if a.smoke else report_dir("2026c", "ephys_spikes")
    gc = git_commit()
    rv = included_sessions(Path(a.review), Path(a.states))
    recs = build_records(rv, Path(a.states))
    t_min = min(rc["start"] for rc in recs).floor("s")
    t_max = max(rc["end"] for rc in recs).ceil("s")
    span = int((t_max - t_min).total_seconds()) + 1
    rois = {r["name"]: r for r in json.load(open(ROOT / "wiser/configs/wiser_rois.json"))["rois"] if r["name"] in ("house_1", "house_2")}
    dates = sorted({d.strftime("%Y%m%d") for d in pd.date_range(t_min.normalize(), t_max.normalize())})
    OUT = Path("D:/Field2026_analysis_out/2026c")
    S, Z, EV = {}, {}, {}
    for an in sorted({rc["animal"] for rc in recs}):
        s = np.zeros(span, np.int8)
        for rc in recs:
            if rc["animal"] == an:
                o = int((rc["start"] - t_min).total_seconds())
                s[o:o + len(rc["state"])] = rc["state"][:max(0, span - o)]
        S[an] = s
        z = load_zone(an, dates, rois)
        zz = z.reindex(pd.date_range(t_min, t_max, freq="1s")[:span]) if len(z) else pd.Series(index=range(span), dtype=object)
        Z[an] = np.select([zz.eq("house_1").to_numpy(), zz.eq("house_2").to_numpy(), zz.eq("field").to_numpy()], [1, 2, 3], 0).astype(np.int8)
        fs = [OUT / f"imu_seconds_cache/{an}/{d}.csv.gz" for d in dates]
        im = pd.concat([pd.read_csv(f, usecols=["sec", "ok", "state"]) for f in fs if f.exists()])
        im["i"] = ((pd.to_datetime(im.sec, unit="s") - pd.Timedelta(hours=4)) - t_min).dt.total_seconds().astype(int)
        im = im[(im.i >= 0) & (im.i < span)]
        st = np.zeros(span, np.int8)
        st[im.i.to_numpy()] = np.where(im.ok.astype(bool), im.state, 0)
        still = st == 1
        cs = np.r_[0, np.cumsum(still)]
        idx = np.arange(span)
        prev5 = (cs[idx] - cs[np.maximum(idx - 5, 0)]) == 5
        ev = (st >= 2) & prev5 & np.isin(s, (N, R))
        EV[an] = (ev, s)
        print(an, "events", int(ev.sum()), "REM", int((ev & (s == R)).sum()), flush=True)
    lags = np.arange(-60, 61)
    rows, cc = [], {}
    for A in EV:
        evA, sA = EV[A]
        iA = np.flatnonzero(evA)
        iA = iA[(iA >= 60) & (iA < span - 60)]
        for B in EV:
            if A == B:
                continue
            evB, sB = EV[B]
            asleepB = np.isin(sB[iA], (N, R))
            same = (Z[A][iA] == Z[B][iA]) & np.isin(Z[A][iA], (1, 2))
            far = (Z[A][iA] != Z[B][iA]) & (Z[A][iA] > 0) & (Z[B][iA] > 0)
            for where, msk in (("same house", same & asleepB), ("elsewhere", far & asleepB)):
                for typ, tm in (("all", np.ones(len(iA), bool)), ("REM (twitch)", sA[iA] == R), ("NREM", sA[iA] == N)):
                    ii = iA[msk & tm]
                    if len(ii) < 20:
                        continue
                    M = evB[ii[:, None] + lags[None, :]].sum(0).astype(float)
                    cc[(A, B, where, typ)] = (M, len(ii))
    for where in ("same house", "elsewhere"):
        for typ in ("all", "REM (twitch)", "NREM"):
            keys = [k for k in cc if k[2] == where and k[3] == typ]
            if not keys:
                continue
            M = sum(cc[k][0] for k in keys)
            n = sum(cc[k][1] for k in keys)
            base = M[(np.abs(lags) >= 30) & (np.abs(lags) <= 60)].mean()
            r = {"pairs": where, "A_event_type": typ, "A_events": n, "ordered_pairs": len(keys), "baseline_per_bin": base / n}
            for L_ in (0, 1, 2, 3):
                r[f"excess_lag+{L_}"] = M[lags == L_][0] / base
                if L_:
                    r[f"excess_lag-{L_}"] = M[lags == -L_][0] / base
            r["direction_plus_over_minus_1to3"] = M[(lags >= 1) & (lags <= 3)].sum() / max(M[(lags >= -3) & (lags <= -1)].sum(), 1)
            pp = []
            for k in keys:
                Mk, nk = cc[k]
                bk = Mk[(np.abs(lags) >= 30) & (np.abs(lags) <= 60)].mean()
                if bk > 0:
                    pp.append(Mk[(lags >= 0) & (lags <= 3)].mean() / bk)
            r["pairs_with_excess_0to3"] = int(np.sum(np.array(pp) > 1))
            r["pairs_tested"] = len(pp)
            rows.append(r)
    T1 = pd.DataFrame(rows)
    # cascade
    crow = []
    for A in EV:
        evA, sA = EV[A]
        iA = np.flatnonzero(evA)
        iA = iA[(iA >= 60) & (iA < span - 61)]
        mates = [B for B in EV if B != A]
        for i in iA:
            co = [B for B in mates if Z[B][i] == Z[A][i] and Z[A][i] in (1, 2) and S[B][i] in (N, R)]
            if len(co) < 2:
                continue
            k5 = sum(EV[B][0][i:i + 6].any() for B in co)
            kb = sum(EV[B][0][i + 30:i + 36].any() for B in co)
            crow.append({"A": A, "type": "REM" if sA[i] == R else "NREM", "mates": len(co), "mates_moving_0to5s": k5, "mates_moving_30to35s": kb})
    C = pd.DataFrame(crow)
    T2 = C.groupby("type").agg(events=("A", "size"), mean_mates=("mates", "mean"), share_any_mate_0to5=("mates_moving_0to5s", lambda v: (v > 0).mean()),
                               share_any_mate_30to35=("mates_moving_30to35s", lambda v: (v > 0).mean()),
                               mean_mates_0to5=("mates_moving_0to5s", "mean"), mean_mates_30to35=("mates_moving_30to35s", "mean")).reset_index()
    T2["ratio_any"] = T2.share_any_mate_0to5 / T2.share_any_mate_30to35
    for name, T in (("t1", T1), ("t2", T2)):
        T.to_csv(rd / f"ephys_spikes_sleep_schedule_phase5b_{name}_2026c.csv", index=False)
        print(T.round(3).to_string(index=False), flush=True)
    # figure: summed correlograms
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from output_paths import figure_dir
    from sleep_quant import save_fig
    fd = out if a.smoke else figure_dir("2026c", "ephys_spikes")
    fig, axs = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    for ax, typ in zip(axs, ("all", "REM (twitch)", "NREM")):
        for where in ("same house", "elsewhere"):
            keys = [k for k in cc if k[2] == where and k[3] == typ]
            if not keys:
                continue
            M = sum(cc[k][0] for k in keys)
            base = M[(np.abs(lags) >= 30) & (np.abs(lags) <= 60)].mean()
            sel = np.abs(lags) <= 15
            ax.plot(lags[sel], M[sel] / base, "o-", ms=3, label=where)
        ax.axhline(1, color="k", lw=0.6)
        ax.axvline(0, color="k", lw=0.4)
        ax.set_title(f"A's event: {typ}", fontsize=9)
        ax.set_xlabel("lag of B's movement onset (s; + = B after A)")
    axs[0].set_ylabel("B onsets / baseline (|lag| 30-60 s)")
    axs[0].legend(fontsize=8)
    fig.suptitle(f"Phase 5b: movement-onset coupling between sleeping animals (head IMU, 1 s)  {gc}", fontsize=9)
    save_fig(fig, fd / "ephys_spikes_sleep_schedule_phase5b_correlogram_2026c.png")
    L = ["# Internal sleep schedule — Phase 5b: local, fast coupling of movements during sleep (cohort 2026c)", "",
         f"Plan Amendment 8 (written before results). Driver `ephys/sleep_schedule.py phase5b` → `ephys/sleep_sync.py` (commit {gc}); "
         f"bulk `{out}`. **Technical ledger.**", "", "## Definitions", "", "```", (phase5b.__doc__ or "").strip(), "```", "",
         "## Cross-correlogram summary (excess = B onsets at that lag / baseline)", "", md_table(T1.round(3)), "",
         "![](../figures/ephys_spikes_sleep_schedule_phase5b_correlogram_2026c.png)", "",
         "## Cascade: housemates moving within 5 s of an event vs 30-35 s later", "", md_table(T2.round(3)), ""]
    flat = [ln for x in L for ln in (x if isinstance(x, list) else [x])]
    (rd / "ephys_spikes_sleep_schedule_phase5b_2026c.md").write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_schedule_phase5b_2026c.json", {"run_dir": str(out), "git_commit": gc})
    print("written", rd / "ephys_spikes_sleep_schedule_phase5b_2026c.md")


def phase5c(a) -> None:
    """The coupling at 20 ms with the IMU-as-EMG signal (plan Amendment 9, before results). VeDBA at 50 Hz from make_imu
    (field-PC clock); per animal theta = median + 8 MAD of VeDBA in scored-NREM seconds; event = first sample >= theta after
    >= 1 s below, while scored NREM / REM. Same-house pairs (WISER), B asleep: cross-correlogram +-3 s (20-ms bins) vs the rate
    at |lag| 30-60 s; peak lag per unordered pair; leader share per animal. Outcome: the score 10 s / 30 s after the event
    (asleep = twitch / brief movement; WAKE = awakening), for A's events, B's coupled responses (0-1 s after A) and B's
    other events; P(B scored WAKE within 30 s | A event) vs 60 s before."""
    from _common import git_commit, write_json
    from mic_wake_pilot import load_zone
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_quant import md_table, save_fig
    out = run_dir("sleep_schedule_phase5c" + ("_smoke" if a.smoke else ""), "2026c")
    rd = out if a.smoke else report_dir("2026c", "ephys_spikes")
    fd = out if a.smoke else figure_dir("2026c", "ephys_spikes")
    gc = git_commit()
    rv = included_sessions(Path(a.review), Path(a.states))
    recs = build_records(rv, Path(a.states))
    t_min = min(rc["start"] for rc in recs).floor("s")
    t_max = max(rc["end"] for rc in recs).ceil("s")
    span = int((t_max - t_min).total_seconds()) + 1
    FS = 50
    rois = {r["name"]: r for r in json.load(open(ROOT / "wiser/configs/wiser_rois.json"))["rois"] if r["name"] in ("house_1", "house_2")}
    dates = sorted({d.strftime("%Y%m%d") for d in pd.date_range(t_min.normalize(), t_max.normalize())})
    IMU = Path("D:/3rd_rat_spikes/analysis/imu")
    S, Z, EVT = {}, {}, {}
    for an in sorted({rc["animal"] for rc in recs}):
        s = np.zeros(span, np.int8)
        for rc in recs:
            if rc["animal"] == an:
                o = int((rc["start"] - t_min).total_seconds())
                s[o:o + len(rc["state"])] = rc["state"][:max(0, span - o)]
        S[an] = s
        z = load_zone(an, dates, rois)
        zz = z.reindex(pd.date_range(t_min, t_max, freq="1s")[:span]) if len(z) else pd.Series(index=range(span), dtype=object)
        Z[an] = np.select([zz.eq("house_1").to_numpy(), zz.eq("house_2").to_numpy()], [1, 2], 0).astype(np.int8)
        v = np.full(span * FS, np.nan, np.float32)
        for sess in rv[rv.animal == an].session:
            f = IMU / an / f"{sess}.imu.npz"
            jf = IMU / an / f"{sess}.imu.json"
            if not f.exists() or not jf.exists():
                continue
            with np.load(f) as zf:
                if "t_pc_ms" not in zf.files:
                    continue
                tp, vd, bad = zf["t_pc_ms"], zf["vedba_ms2"], zf["unreliable"] | zf["frozen"] | zf["invalid"]
            day = pd.Timestamp(json.loads(jf.read_text())["start_local"]).normalize()
            k = np.round(((day - t_min).total_seconds() * 1000 + tp) / (1000 / FS)).astype(np.int64)
            ok = (k >= 0) & (k < len(v)) & ~bad & np.isfinite(vd)
            v[k[ok]] = vd[ok]
        sec = np.arange(len(v)) // FS
        nrem = (s[sec] == N) & np.isfinite(v)
        med = np.nanmedian(v[nrem])
        mad = np.nanmedian(np.abs(v[nrem] - med))
        th = med + 8 * 1.4826 * mad
        above = np.nan_to_num(v, nan=0) >= th
        csum = np.r_[0, np.cumsum(above)]
        kk = np.flatnonzero(above)
        kk = kk[kk >= FS]
        onset = kk[(csum[kk] - csum[kk - FS]) == 0]
        onset = onset[np.isin(s[onset // FS], (N, R))]
        EVT[an] = onset
        print(an, "theta", round(float(th), 3), "events", len(onset), "REM", int((s[onset // FS] == R).sum()), flush=True)
        del v
    # ---- coupling at 20 ms
    bins = np.arange(-3.0, 3.0 + 1e-9, 0.02)
    rows, peaks, lead = [], [], {an: [0, 0] for an in EVT}
    CC = {}
    for A in EVT:
        for B in EVT:
            if A == B:
                continue
            eA, eB = EVT[A], np.sort(EVT[B])
            secA = eA // FS
            ok = (Z[A][secA] == Z[B][secA]) & (Z[A][secA] > 0) & np.isin(S[B][secA], (N, R))
            eA = eA[ok]
            if len(eA) < 30:
                continue
            lo = np.searchsorted(eB, eA - 60 * FS)
            hi = np.searchsorted(eB, eA + 60 * FS)
            d = np.concatenate([eB[l_:h_] - x for x, l_, h_ in zip(eA, lo, hi)]) / FS
            near = np.histogram(d, bins=bins)[0].astype(float)
            base = np.sum((np.abs(d) >= 30) & (np.abs(d) <= 60)) / (60 / 0.02)       # per 20-ms bin
            CC[(A, B)] = (near, base, len(eA))
            dd = d[np.abs(d) <= 1]
            lead[A][0] += int(np.sum(dd >= 0.06))
            lead[A][1] += int(np.sum(dd <= -0.06))
    for (A, B), (near, base, n) in CC.items():
        if A < B and (B, A) in CC:
            tot = near + CC[(B, A)][0][::-1]
            b_ = base + CC[(B, A)][1]
            ctr = (bins[:-1] + bins[1:]) / 2
            sel = np.abs(ctr) <= 1
            pk = ctr[sel][np.argmax(tot[sel])]
            peaks.append({"pair": f"{A}-{B}", "A_events": n, "peak_lag_s (+ = second animal later)": round(float(pk), 3),
                          "peak_over_baseline": float(tot[sel].max() / b_) if b_ > 0 else np.nan,
                          "excess_within_100ms": float(tot[np.abs(ctr) <= 0.1].sum() / (b_ * np.sum(np.abs(ctr) <= 0.1))) if b_ > 0 else np.nan,
                          "excess_0.1_to_1s": float(tot[(np.abs(ctr) > 0.1) & (np.abs(ctr) <= 1)].sum() / (b_ * np.sum((np.abs(ctr) > 0.1) & (np.abs(ctr) <= 1)))) if b_ > 0 else np.nan})
    P = pd.DataFrame(peaks)
    LD = pd.DataFrame([{"animal": an, "moved_first_by_60ms_or_more": l[0], "moved_second": l[1],
                        "leader_share": l[0] / max(l[0] + l[1], 1)} for an, l in lead.items()])
    # pooled correlogram figure
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ctr = (bins[:-1] + bins[1:]) / 2
    tot = sum(v[0] for v in CC.values())
    base = sum(v[1] for v in CC.values())
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(ctr, tot / base, lw=1)
    ax.axhline(1, color="k", lw=0.5)
    ax.set_xlabel("lag of B's movement onset after A's (s; 20-ms bins)")
    ax.set_ylabel("B onsets / baseline")
    ax.set_title(f"Phase 5c: same-house sleeping pairs, IMU-as-EMG (VeDBA 50 Hz)  {gc}", fontsize=9)
    save_fig(fig, fd / "ephys_spikes_sleep_schedule_phase5c_correlogram_2026c.png")
    # ---- outcome: twitch or awakening?
    orow = []
    for A in EVT:
        eA = EVT[A]
        secA = eA // FS
        ok = secA + 31 < span
        eA, secA = eA[ok], secA[ok]
        typ = np.where(S[A][secA] == R, "REM", "NREM")
        coupled = np.zeros(len(eA), bool)
        for B in EVT:
            if B == A:
                continue
            eB = np.sort(EVT[B])
            lo = np.searchsorted(eB, eA - FS)
            hi = np.searchsorted(eB, eA)
            same = (Z[A][secA] == Z[B][secA]) & (Z[A][secA] > 0)
            coupled |= same & (hi > lo)                      # a housemate moved 0-1 s BEFORE this event: a response
        for t_, cpl in ((t_, c_) for t_ in ("REM", "NREM") for c_ in (True, False)):
            m_ = (typ == t_) & (coupled == cpl)
            if m_.sum() < 10:
                continue
            s10, s30 = S[A][secA[m_] + 10], S[A][secA[m_] + 30]
            orow.append({"animal": A, "event_state": t_, "after_a_housemate_moved_0to1s": cpl, "events": int(m_.sum()),
                         "wake_at_10s": float(np.mean(s10 == 1)), "asleep_at_10s": float(np.mean(np.isin(s10, (N, R)))),
                         "rem_at_10s": float(np.mean(s10 == R)), "wake_at_30s": float(np.mean(s30 == 1))})
    O = pd.DataFrame(orow)
    O2 = O.groupby(["event_state", "after_a_housemate_moved_0to1s"]).apply(
        lambda g: pd.Series({"events": g.events.sum(), "wake_at_10s": np.average(g.wake_at_10s, weights=g.events),
                             "rem_at_10s": np.average(g.rem_at_10s, weights=g.events), "wake_at_30s": np.average(g.wake_at_30s, weights=g.events),
                             "animals": g.animal.nunique()}), include_groups=False).reset_index()
    # partner woken? P(B scored WAKE within 30 s | A's event, B asleep) vs 60 s before
    wrow = []
    for A in EVT:
        for B in EVT:
            if A == B:
                continue
            secA = EVT[A] // FS
            secA = secA[(secA >= 61) & (secA + 31 < span)]
            ok = (Z[A][secA] == Z[B][secA]) & (Z[A][secA] > 0) & np.isin(S[B][secA], (N, R)) & np.isin(S[B][secA - 60], (N, R))
            x = secA[ok]
            if len(x) < 30:
                continue
            woke = np.array([np.any(S[B][i + 1:i + 31] == 1) for i in x])
            woke0 = np.array([np.any(S[B][i - 59:i - 29] == 1) for i in x])
            wrow.append({"A": A, "B": B, "events": len(x), "P_B_wakes_within_30s_after": woke.mean(), "P_B_wakes_in_30s_window_60s_before": woke0.mean()})
    WK = pd.DataFrame(wrow)
    if len(WK):
        WK["ratio"] = WK.P_B_wakes_within_30s_after / WK.P_B_wakes_in_30s_window_60s_before
    for name, T in (("pairs", P), ("leader", LD), ("outcome", O2), ("partner_wake", WK)):
        T.to_csv(rd / f"ephys_spikes_sleep_schedule_phase5c_{name}_2026c.csv", index=False)
        print(T.round(3).to_string(index=False), flush=True)
    L = ["# Internal sleep schedule — Phase 5c: movement coupling at 20 ms (IMU-as-EMG); twitch or awakening? (cohort 2026c)", "",
         f"Plan Amendment 9 (before results). Driver `ephys/sleep_schedule.py phase5c` → `ephys/sleep_sync.py` (commit {gc}); bulk `{out}`.", "",
         "## Definitions", "", "```", (phase5c.__doc__ or "").strip(), "```", "",
         "![](../figures/ephys_spikes_sleep_schedule_phase5c_correlogram_2026c.png)", "",
         "## Per pair: peak lag and excess (both directions pooled; + = the second-named animal later)", "", md_table(P.round(3)), "",
         "## Who moves first (coupled pairs within +-1 s, >= 60 ms apart)", "", md_table(LD.round(3)), "",
         "## Twitch or awakening: the mover's score 10 s / 30 s later", "", md_table(O2.round(3)), "",
         "## Is the partner woken? P(B scored WAKE within 30 s after A's event) vs a 30-s window 60 s before", "", md_table(WK.round(3)), ""]
    flat = [ln for x in L for ln in (x if isinstance(x, list) else [x])]
    (rd / "ephys_spikes_sleep_schedule_phase5c_2026c.md").write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_schedule_phase5c_2026c.json", {"run_dir": str(out), "git_commit": gc})
    print("written", rd / "ephys_spikes_sleep_schedule_phase5c_2026c.md")
