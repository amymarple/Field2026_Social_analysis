r"""REM time course within sleep episodes (plan implementation_plan/2026-10-10-sleep-lfp-stage.md §10, revision 4, written
before results): does REM entry rise / fall with the time since an episode began beyond what the count model produces?

Usage:  python ephys/sleep_ramp.py run [--scorings final pass2med] [--workers 6] [--reps 100]
        python ephys/sleep_ramp.py --selftest

Definitions (records, 10-s NREM steps, folds and the B-full spec as ephys/sleep_model.py):
  episode       onset = the first NREM second after (i) a WAKE bout >= 30 min inside a record ("natural") or (ii) a record
                start ("record start"; post-round when the record follows a round gap, else "other start"), or after an
                unknown run > 60 s ("after unknown"); end = the next WAKE bout >= 30 min (observed) or censored at an unknown
                run > 60 s / the record end
  u             seconds since the episode onset on the wall clock (short wakes, REM, short unknown runs included)
  classes       main = the last natural onset in [sunset, next sunrise + 1 h) of a night; nap = earlier natural onsets in
                [sunset, main onset); day = other natural onsets; post-round; other (record start without a round, after
                unknown: dropped)
  bins of u     0-10, 10-20, 20-30, 30-45, 45-60, 60-90, 90-120, 120-180, 180-240, 240-360, >= 360 min
  (A) O / E     O = observed REM entries (y = 1) of the held-out 10-s NREM steps in a bin, E = the sum of B-full's held-out
                p_rem there (sleep_heldout_steps, forward chaining); WAKE likewise (y = 2, p_wake); 95 % CI = 2000 bootstrap
                resamples of episodes within animals; judged bins E >= 20
                ramp residual in a class = >= 2 adjacent judged bins whose CI excludes 1 in the same direction on both
                scorings, and per-animal O / E pooled over those bins on that side in >= n - 1 of the n animals with E >= 5
  (B) REM share REM s / (NREM + REM) s per bin and class on the observed episode bounds, observed vs the 2.5-97.5 % band of
                100 replicates of the Step-E simulator (base model, conditional on the observed long wakes >= 7 min);
                not reproduced = >= 2 adjacent judged bins (>= 20 episodes at risk) outside the band in the same direction
                on both scorings
  (C) episode clock  g(u) = (ln(1 + u_m), max(0, ln(1 + u_m) - ln 31), max(0, ln(1 + u_m) - ln 121)), u_m in minutes, as
                linear extras on B-full; forward chaining; primary subset natural episodes (nap + main + day), secondary
                + post-round; holds = REM log-loss CI < 0 and >= n - 1 animals better, on both scorings
  (D) description  end-aligned O / E (minutes before an observed episode-ending wake >= 30 min; selection-prone) and (A)
                with a 10-min wake threshold
Amendment 1 (post hoc, after the first run; plan §10.7): --episode-rule nsw takes the long wakes from
                night_sleep_wiser.long_wakes (wake runs merged across sleep interruptions < 120 s, >= 30 min) and the
                night window to the next sunrise + 2 h, as night_sleep_wiser's MSO (the pre-registered rule matched its MSO on
                10 / 45 nights); both rules add the pooled class "natural" (nap + main + day), which uses no future
                information (nap vs main depends on whether a later long wake follows: naps end in one by definition)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "common"))

W_STATE, N_STATE, R_STATE = 1, 3, 5
LONG_W = 1800
UNK_MAX = 60
BINS_MIN = [0, 10, 20, 30, 45, 60, 90, 120, 180, 240, 360, np.inf]
END_BINS_MIN = [0, 10, 20, 30, 60, 120, np.inf]
BASE = ["nap", "main", "day", "post-round"]
CLASSES = ["natural", "nap", "main", "day", "post-round"]
NATURAL = ("nap", "main", "day")
RULE = {"name": "plain", "night_end_h": 1}


def members(cls: np.ndarray, c: str) -> np.ndarray:
    return np.isin(cls, NATURAL) if c == "natural" else (cls == c)
HELD = Path("D:/Field2026_analysis_out/2026c/sleep_heldout_steps")
MIN_E, MIN_E_ANIMAL, MIN_RISK = 20.0, 5.0, 20
BOOT = 2000


def bin_labels(edges=BINS_MIN) -> list[str]:
    return [f"{int(a)}-{int(b)}" if np.isfinite(b) else f">={int(a)}" for a, b in zip(edges[:-1], edges[1:])]


# ------------------------------------------------------------------ episodes
def runs(st: np.ndarray) -> list[tuple[int, int, int]]:
    """Run-length encoding: (state, start, end exclusive)."""
    if len(st) == 0:
        return []
    cut = np.flatnonzero(np.diff(st)) + 1
    a = np.r_[0, cut]
    b = np.r_[cut, len(st)]
    return [(int(st[i]), int(i), int(j)) for i, j in zip(a, b)]


def record_episodes(st: np.ndarray, w_long: int = LONG_W) -> list[dict]:
    """Episodes of one record: the record is cut at WAKE runs >= w_long and unknown runs > UNK_MAX; inside each piece the
    episode starts at the first NREM second; the kind of its start and end comes from the boundaries around the piece."""
    known = {W_STATE, N_STATE, R_STATE}
    if RULE["name"] == "nsw":
        from night_sleep_wiser import long_wakes
        bounds = [(W_STATE, a, b) for a, b in long_wakes(st, w_long)]
        bounds += [(s, a, b) for s, a, b in runs(st) if s not in known and b - a > UNK_MAX]
        bounds.sort(key=lambda x: x[1])
    else:
        bounds = [(s, a, b) for s, a, b in runs(st) if (s == W_STATE and b - a >= w_long) or (s not in known and b - a > UNK_MAX)]
    out, prev_end, prev_kind = [], 0, "record_start"
    for s, a, b in bounds + [(None, len(st), len(st))]:
        piece = st[prev_end:a]
        nz = np.flatnonzero(piece == N_STATE)
        if len(nz):
            end_kind = "wake" if s == W_STATE else "censored"
            out.append({"onset": prev_end + int(nz[0]), "end": int(a), "start_kind": prev_kind, "observed_end": end_kind == "wake"})
        prev_end = b
        prev_kind = "natural" if s == W_STATE else "after_unknown"
    return out


def night_windows(dates) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    from sleep_quant import sun_times
    out = []
    for d in sorted(set(dates)):
        ss = pd.Timestamp(sun_times(d)[1])
        sr_next = pd.Timestamp(sun_times(d + pd.Timedelta(days=1))[0])
        out.append((ss, sr_next + pd.Timedelta(hours=RULE["night_end_h"])))
    return out


def classify(E: pd.DataFrame, post_round_ids: set) -> np.ndarray:
    """E: one row per episode with animal, record_id, start_kind, t_onset. Returns the class per row."""
    cls = np.full(len(E), "other", dtype=object)
    rs = E.start_kind == "record_start"
    cls[(rs & E.record_id.isin(post_round_ids)).to_numpy()] = "post-round"
    nat = (E.start_kind == "natural").to_numpy()
    cls[nat] = "day"
    if nat.any():
        wins = night_windows(pd.to_datetime(E.t_onset[nat]).dt.normalize().dt.date.tolist()
                             + (pd.to_datetime(E.t_onset[nat]) - pd.Timedelta(days=1)).dt.normalize().dt.date.tolist())
        for an, g in E[nat].groupby("animal"):
            t = pd.to_datetime(g.t_onset)
            for w0, w1 in wins:
                m = ((t >= w0) & (t < w1)).to_numpy()
                if m.any():
                    idx = g.index[m]
                    order = idx[np.argsort(t[m].to_numpy())]
                    cls[E.index.get_indexer(order[:-1])] = "nap"
                    cls[E.index.get_indexer(order[-1:])] = "main"
    return cls


def episode_table(recs: list[dict], post_round_ids: set, w_long: int = LONG_W) -> pd.DataFrame:
    rows = []
    for rc in recs:
        for e in record_episodes(rc["state"], w_long):
            rows.append({"animal": rc["animal"], "record_id": rc["record_id"], **e,
                         "t_onset": rc["start"] + pd.Timedelta(seconds=e["onset"])})
    E = pd.DataFrame(rows)
    E["cls"] = classify(E, post_round_ids)
    E["ep"] = np.arange(len(E))
    return E


def locate(E: pd.DataFrame, record_id: np.ndarray, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Episode index and u (s since onset) for record seconds s; -1 / nan outside episodes."""
    ep, u = np.full(len(s), -1), np.full(len(s), np.nan)
    for rid, g in E.groupby("record_id"):
        m = np.flatnonzero(record_id == rid)
        if not len(m):
            continue
        g = g.sort_values("onset")
        on, en, ix = g.onset.to_numpy(), g.end.to_numpy(), g.ep.to_numpy()
        j = np.searchsorted(on, s[m], side="right") - 1
        ok = (j >= 0)
        ok[ok] &= s[m][ok] < en[j[ok]]
        ep[m[ok]] = ix[j[ok]]
        u[m[ok]] = s[m][ok] - on[j[ok]]
    return ep, u


# ------------------------------------------------------------------ (A) O / E with episode bootstrap
def oe_table(ep: np.ndarray, b: np.ndarray, obs: np.ndarray, exp: np.ndarray, ep_animal: np.ndarray, nb: int,
             rng: np.random.Generator, boot: int = BOOT) -> dict:
    """ep, b: episode index and bin per step (only valid steps); returns pooled O, E, steps, CI and per-animal O / E."""
    ue, inv = np.unique(ep, return_inverse=True)
    n = len(ue)
    MO, ME, MS = (np.zeros((n, nb)) for _ in range(3))
    np.add.at(MO, (inv, b), obs)
    np.add.at(ME, (inv, b), exp)
    np.add.at(MS, (inv, b), 1.0)
    an = ep_animal[ue]
    groups = [np.flatnonzero(an == a) for a in np.unique(an)]
    bo = np.empty((boot, nb))
    for k in range(boot):
        idx = np.concatenate([rng.choice(g, len(g)) for g in groups])
        o, e = MO[idx].sum(0), ME[idx].sum(0)
        with np.errstate(invalid="ignore", divide="ignore"):
            bo[k] = o / e
    O, E_, S = MO.sum(0), ME.sum(0), MS.sum(0)
    per = {a: (MO[an == a].sum(0), ME[an == a].sum(0)) for a in np.unique(an)}
    with np.errstate(invalid="ignore", divide="ignore"):
        return {"O": O, "E": E_, "steps": S, "oe": O / E_, "lo": np.nanpercentile(bo, 2.5, axis=0),
                "hi": np.nanpercentile(bo, 97.5, axis=0), "per": per, "MO": MO, "ME": ME, "an": an}


def at_risk(E: pd.DataFrame, edges_s: np.ndarray) -> np.ndarray:
    """Episodes still running (uncensored, not ended) at each bin start."""
    dur = (E.end - E.onset).to_numpy()
    return np.array([(dur > lo).sum() for lo in edges_s[:-1]])


def ramp_rule(rows: pd.DataFrame, per_animal: dict) -> list[dict]:
    """rows: per scoring x bin with oe, lo, hi, E; per_animal[(scoring)] = {animal: (O, E)} arrays by bin.
    Returns the qualifying runs (adjacent bins, same direction, both scorings, animal rule)."""
    scs = sorted(rows.scores.unique())
    nb = rows.bin_i.max() + 1
    d = {}
    for sc in scs:
        r = rows[rows.scores == sc].set_index("bin_i").reindex(range(nb))
        judged = r.E.to_numpy() >= MIN_E
        dirn = np.where(judged & (r.lo.to_numpy() > 1), 1, np.where(judged & (r.hi.to_numpy() < 1), -1, 0))
        d[sc] = dirn
    out = []
    for i in range(nb - 1):
        dirs = {sc: (d[sc][i], d[sc][i + 1]) for sc in scs}
        s0 = dirs[scs[0]][0]
        if s0 == 0 or any(v != (s0, s0) for v in dirs.values()):
            continue
        ok_an = {}
        for sc in scs:
            n_ok, n_tot = 0, 0
            for a, (o, e) in per_animal[sc].items():
                eo, ee = o[i] + o[i + 1], e[i] + e[i + 1]
                if ee >= MIN_E_ANIMAL:
                    n_tot += 1
                    n_ok += int((eo / ee - 1) * s0 > 0)
            ok_an[sc] = (n_ok, n_tot)
        passed = all(n_ok >= n_tot - 1 and n_tot > 0 for n_ok, n_tot in ok_an.values())
        out.append({"bins": f"{i},{i + 1}", "direction": "+" if s0 > 0 else "-", "animals": "; ".join(f"{sc} {v[0]}/{v[1]}" for sc, v in ok_an.items()),
                    "passes": passed})
    return out


# ------------------------------------------------------------------ (B) REM share on fixed episode bounds
def share_index(recs: list[dict], E: pd.DataFrame, edges_s: np.ndarray) -> list[np.ndarray]:
    """Per record a per-second code = class_index * nb + bin (or -1 outside the four classes' episodes)."""
    nb = len(edges_s) - 1
    ci = {c: k for k, c in enumerate(BASE)}
    out = []
    for rc in recs:
        code = np.full(len(rc["state"]), -1, np.int32)
        for e in E[E.record_id == rc["record_id"]].itertuples():
            if e.cls not in ci:
                continue
            s = np.arange(e.onset, e.end)
            b = np.searchsorted(edges_s, s - e.onset, side="right") - 1
            code[s] = ci[e.cls] * nb + b
        out.append(code)
    return out


def share_counts(recs: list[dict], codes: list[np.ndarray], nb: int) -> tuple[np.ndarray, np.ndarray]:
    K = len(BASE) * nb
    rem, slp = np.zeros(K), np.zeros(K)
    for rc, c in zip(recs, codes):
        st = rc["state"]
        m = c >= 0
        rem += np.bincount(c[m & (st == R_STATE)], minlength=K)
        slp += np.bincount(c[m & ((st == R_STATE) | (st == N_STATE))], minlength=K)
    rem, slp = rem.reshape(len(BASE), nb), slp.reshape(len(BASE), nb)
    return np.vstack([rem[:3].sum(0), rem]), np.vstack([slp[:3].sum(0), slp])          # row 0 = natural


def _sim_rep(rep: int, recs: list[dict], M: dict, codes: list[np.ndarray], nb: int) -> tuple[np.ndarray, np.ndarray]:
    from sleep_sim import simulate_records
    sim = simulate_records(recs, M, 90_000 + rep)
    return share_counts(sim, codes, nb)


# ------------------------------------------------------------------ run
def run(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from joblib import Parallel, delayed
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_lfp import B, KEY, run_compare
    from sleep_model import PASS2MED, build_data, records_for, to_arrays, variant_specs
    from sleep_perturb import round_info
    from sleep_quant import md_table, save_fig
    from sleep_schedule import STATES
    from sleep_sim import build_model, simulate_records
    from sleep_stability import gaps_table
    RULE.update(name=a.episode_rule, night_end_h=2 if a.episode_rule == "nsw" else 1)
    sfx = "" if a.episode_rule == "plain" else f"_{a.episode_rule}"
    out = run_dir("sleep_ramp" + sfx, "2026c")
    rd, fd = report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes")
    gc = git_commit()
    t0 = time.time()
    rng = np.random.default_rng(0)
    edges_s = np.array(BINS_MIN) * 60.0
    end_s = np.array(END_BINS_MIN) * 60.0
    nb, labels = len(edges_s) - 1, bin_labels()
    gaps = gaps_table()
    A_rows, A_an, RULES, B_rows, C_rows, D_rows, EP_SUM, MSO = [], [], [], [], [], [], [], []
    per_animal = {}
    for lab in a.scorings:
        recs = records_for(STATES if lab == "final" else PASS2MED)
        RI = round_info(recs, gaps)
        prids = set(RI.record_id)
        for w_long, tag in ((LONG_W, "main"), (600, "wake >= 10 min")):
            E = episode_table(recs, prids, w_long)
            if tag == "main":
                E.to_csv(out / f"episodes_{lab}.csv", index=False)
                EP_SUM.append(E.assign(dur_min=(E.end - E.onset) / 60).groupby("cls").agg(
                    episodes=("ep", "size"), animals=("animal", "nunique"), median_min=("dur_min", "median"),
                    observed_end=("observed_end", "mean")).reset_index().assign(scores=lab))
            H = pd.read_csv(HELD / f"heldout_steps_{lab}.csv.gz", usecols=["animal", "record_id", "s_since_rec_start", "y", "p_rem", "p_wake"])
            ep, u = locate(E, H.record_id.to_numpy(), H.s_since_rec_start.to_numpy())
            cls = np.where(ep >= 0, E.cls.to_numpy()[np.maximum(ep, 0)], "none")
            b = np.searchsorted(edges_s, np.nan_to_num(u, nan=-1), side="right") - 1
            ep_an = E.animal.to_numpy()
            for c in CLASSES:
                m = members(cls, c) & (ep >= 0)
                if m.sum() == 0:
                    continue
                risk = at_risk(E[members(E.cls.to_numpy(), c)], edges_s)
                for outcome, yv, pcol in (("REM", 1, "p_rem"), ("WAKE", 2, "p_wake")):
                    T = oe_table(ep[m], b[m], (H.y.to_numpy()[m] == yv).astype(float), H[pcol].to_numpy()[m], ep_an, nb, rng,
                                 BOOT if tag == "main" else 500)
                    for i in range(nb):
                        A_rows.append({"scores": lab, "wake_rule": tag, "cls": c, "outcome": outcome, "bin_i": i, "bin_min": labels[i],
                                       "at_risk": int(risk[i]), "steps": int(T["steps"][i]), "O": int(T["O"][i]), "E": float(T["E"][i]),
                                       "oe": float(T["oe"][i]), "lo": float(T["lo"][i]), "hi": float(T["hi"][i]),
                                       "obs_per_nrem_h": float(T["O"][i] / T["steps"][i] * 360) if T["steps"][i] else np.nan,
                                       "pred_per_nrem_h": float(T["E"][i] / T["steps"][i] * 360) if T["steps"][i] else np.nan})
                    if tag == "main":
                        per_animal[(c, outcome, lab)] = T["per"]
                        for an_, (o, e) in T["per"].items():
                            for i in range(nb):
                                A_an.append({"scores": lab, "cls": c, "outcome": outcome, "animal": an_, "bin_min": labels[i], "O": int(o[i]), "E": float(e[i])})
                if tag == "main":                                          # (D) end-aligned, observed ends only
                    ee = E.set_index("ep")
                    v = np.where(m, ee.end.reindex(np.maximum(ep, 0)).to_numpy() - H.s_since_rec_start.to_numpy(), np.nan)
                    obs_end = np.where(m, ee.observed_end.reindex(np.maximum(ep, 0)).to_numpy(), False).astype(bool)
                    mm = m & obs_end
                    if mm.sum():
                        bd = np.searchsorted(end_s, v[mm], side="right") - 1
                        Td = oe_table(ep[mm], bd, (H.y.to_numpy()[mm] == 1).astype(float), H.p_rem.to_numpy()[mm], ep_an, len(end_s) - 1, rng, 500)
                        for i, bl in enumerate(bin_labels(END_BINS_MIN)):
                            D_rows.append({"scores": lab, "cls": c, "min_before_end": bl, "steps": int(Td["steps"][i]), "O": int(Td["O"][i]),
                                           "E": float(Td["E"][i]), "oe": float(Td["oe"][i]), "lo": float(Td["lo"][i]), "hi": float(Td["hi"][i])})
            if tag == "main" and lab == "final":                           # main onsets vs night_sleep_wiser's mso
                nt = pd.read_csv(REPO / "results/2026c/ephys_spikes/reports/ephys_spikes_night_sleep_wiser_nights_2026c.csv")
                nt = nt[nt.mso_status == "ok"]
                mains = E[E.cls == "main"]
                hit = 0
                for r in nt.itertuples():
                    d = (pd.to_datetime(mains[mains.animal == r.animal].t_onset) - pd.Timestamp(r.mso)).abs()
                    hit += int(len(d) and d.min() <= pd.Timedelta(seconds=60))
                MSO.append({"nights_with_mso": len(nt), "main_onset_within_60s": hit, "share": hit / max(len(nt), 1)})
            print(f"[{lab}] (A) {tag} {time.time() - t0:.0f} s", flush=True)
        E = episode_table(recs, prids, LONG_W)
        # ---- (B) generative overlay on the observed bounds
        codes = share_index(recs, E, edges_s)
        rem_o, slp_o = share_counts(recs, codes, nb)
        M = build_model(recs)
        simulate_records(recs[:1], M, 0)
        sims = Parallel(n_jobs=a.workers, backend="loky")(delayed(_sim_rep)(r, recs, M, codes, nb) for r in range(a.reps))
        sh = np.array([r_ / np.maximum(s_, 1) for r_, s_ in sims])
        for k, c in enumerate(CLASSES):
            risk = at_risk(E[members(E.cls.to_numpy(), c)], edges_s)
            for i in range(nb):
                B_rows.append({"scores": lab, "cls": c, "bin_i": i, "bin_min": labels[i], "at_risk": int(risk[i]), "sleep_min": slp_o[k, i] / 60,
                               "obs_share": rem_o[k, i] / slp_o[k, i] if slp_o[k, i] else np.nan,
                               "sim_mean": float(sh[:, k, i].mean()), "sim_lo": float(np.percentile(sh[:, k, i], 2.5)),
                               "sim_hi": float(np.percentile(sh[:, k, i], 97.5))})
        print(f"[{lab}] (B) {time.time() - t0:.0f} s", flush=True)
        # ---- (C) nested episode clock
        steps = build_data(recs, {KEY: variant_specs()[KEY]})
        s_ = (steps.bout_start.to_numpy() + steps.elapsed.to_numpy()).astype(np.int64)
        ep, u = locate(E, steps.record_id.to_numpy(), s_)
        cls = np.where(ep >= 0, E.cls.to_numpy()[np.maximum(ep, 0)], "none")
        um = np.nan_to_num(u, nan=0.0) / 60.0
        g1 = np.log1p(um)
        F = pd.DataFrame({"ep1": g1, "ep2": np.maximum(0, g1 - np.log(31)), "ep3": np.maximum(0, g1 - np.log(121))}, index=steps.index)
        for label, keep in (("natural (nap + main + day)", ("nap", "main", "day")), ("natural + post-round", ("nap", "main", "day", "post-round"))):
            msk = np.isin(cls, keep)
            s2, f2 = steps[msk].reset_index(drop=True), F[msk].reset_index(drop=True)
            D = to_arrays(s2)
            for col in f2.columns:
                D[col] = f2[col].to_numpy().astype(float)
            specs = {"B": dict(B), "B+episode clock": {**B, "extra": ("ep1", "ep2", "ep3")}}
            C_rows.append(run_compare(D, specs, [("B", "B+episode clock")], a.workers, label, lab))
            print(f"[{lab}] (C) {label} {time.time() - t0:.0f} s", flush=True)
    A, AN, BB, CC, DD = pd.DataFrame(A_rows), pd.DataFrame(A_an), pd.DataFrame(B_rows), pd.concat(C_rows, ignore_index=True), pd.DataFrame(D_rows)
    EPS = pd.concat(EP_SUM, ignore_index=True)
    # ---- rules
    V = []
    for c in CLASSES:
        for outcome in ("REM", "WAKE"):
            rows = A[(A.wake_rule == "main") & (A.cls == c) & (A.outcome == outcome)]
            if rows.scores.nunique() < len(a.scorings):
                continue
            pa = {lab: per_animal[(c, outcome, lab)] for lab in a.scorings}
            runs_ = ramp_rule(rows, pa)
            for r in runs_:
                RULES.append({"cls": c, "outcome": outcome, **r, "bins_min": " + ".join(labels[int(x)] for x in r["bins"].split(","))})
            if outcome == "REM":
                resid = any(r["passes"] for r in runs_)
                bb = BB[BB.cls == c]
                notrep = False
                for i in range(nb - 1):
                    dirs = []
                    for lab in a.scorings:
                        q = bb[bb.scores == lab].set_index("bin_i")
                        dd = []
                        for j in (i, i + 1):
                            if q.at[j, "at_risk"] < MIN_RISK or not np.isfinite(q.at[j, "obs_share"]):
                                dd.append(0)
                            else:
                                dd.append(1 if q.at[j, "obs_share"] > q.at[j, "sim_hi"] else (-1 if q.at[j, "obs_share"] < q.at[j, "sim_lo"] else 0))
                        dirs.append(tuple(dd))
                    if dirs[0][0] != 0 and all(d == (dirs[0][0], dirs[0][0]) for d in dirs):
                        notrep = True
                V.append({"cls": c, "A_ramp_residual_REM": resid, "B_shape_not_reproduced": notrep})
    V = pd.DataFrame(V)
    cr = CC[CC.metric == "rem"]
    Cv = []
    for label in cr.subset.unique():
        rr = cr[cr.subset == label]
        Cv.append({"subset": label, "holds_both": bool(rr.holds.all() and len(rr) == len(a.scorings)),
                   "numbers": "; ".join(f"{r.scores} {r.delta_pct:+.3f} % [{r.ci_lo_pct:+.3f}, {r.ci_hi_pct:+.3f}], {int(r.animals_better)}/{int(r.animals)}"
                                        for r in rr.itertuples())})
    Cv = pd.DataFrame(Cv)
    for name, T in (("A_oe", A), ("A_per_animal", AN), ("A_rule_runs", pd.DataFrame(RULES)), ("B_share", BB), ("C_compare", CC),
                    ("D_end_aligned", DD), ("episodes", EPS), ("verdicts", V), ("C_verdicts", Cv)):
        T.to_csv(rd / f"ephys_spikes_sleep_ramp{sfx}_{name}_2026c.csv", index=False)
    # ---- figure: rows = classes; cols = REM entry per NREM hour (obs vs held-out pred), O / E, REM share (obs vs sim band)
    fig, ax = plt.subplots(len(CLASSES), 3, figsize=(14, 3.0 * len(CLASSES)), squeeze=False)
    x = np.arange(nb)
    sty = {"final": ("C0", "-"), "pass2med": ("C1", "--")}
    for k, c in enumerate(CLASSES):
        for lab in a.scorings:
            col, ls = sty[lab]
            q = A[(A.wake_rule == "main") & (A.cls == c) & (A.outcome == "REM") & (A.scores == lab)].sort_values("bin_i")
            if not len(q):
                continue
            ok = q.E.to_numpy() >= MIN_E
            ax[k, 0].plot(x[ok], q.obs_per_nrem_h[ok], ls, color=col, marker="o", ms=3, label=f"{lab} observed")
            ax[k, 0].plot(x[ok], q.pred_per_nrem_h[ok], ":", color=col, label=f"{lab} held-out B-full")
            ax[k, 1].errorbar(x[ok] + (0.1 if lab == "pass2med" else 0), q.oe[ok], yerr=[q.oe[ok] - q.lo[ok], q.hi[ok] - q.oe[ok]],
                              fmt="o", color=col, ms=3, capsize=2, label=lab)
            bq = BB[(BB.cls == c) & (BB.scores == lab)].sort_values("bin_i")
            okb = bq.at_risk.to_numpy() >= MIN_RISK
            ax[k, 2].fill_between(x[okb], bq.sim_lo[okb], bq.sim_hi[okb], color=col, alpha=0.15)
            ax[k, 2].plot(x[okb], bq.obs_share[okb], ls, color=col, marker="o", ms=3, label=f"{lab} observed (band = simulated)")
            if lab == "final":
                for i in np.flatnonzero(ok):
                    ax[k, 0].annotate(str(int(q.at_risk.iloc[i])), (x[i], 0), xytext=(0, 2), textcoords="offset points", fontsize=6, ha="center", color="0.4")
        ax[k, 1].axhline(1, color="0.5", lw=0.8)
        ax[k, 0].set_ylabel(f"{c}\nREM entries / NREM h")
        ax[k, 1].set_ylabel("O / E (REM entry)")
        ax[k, 2].set_ylabel("REM share of sleep")
        for j in range(3):
            ax[k, j].set_xticks(x, labels, fontsize=6, rotation=45)
        ax[k, 0].legend(fontsize=6)
        ax[k, 2].legend(fontsize=6)
    for j in range(3):
        ax[-1, j].set_xlabel("minutes since episode onset (numbers: episodes at risk, FINAL)")
    fig.suptitle("REM within sleep episodes: observed vs the count model (held out) and its simulator", fontsize=10)
    fig.tight_layout()
    fp = save_fig(fig, fd / f"ephys_spikes_sleep_ramp{sfx}_2026c.png")
    plt.close(fig)
    show = A[(A.wake_rule == "main") & (A.outcome == "REM")][["scores", "cls", "bin_min", "at_risk", "steps", "O", "E", "oe", "lo", "hi", "obs_per_nrem_h", "pred_per_nrem_h"]]
    L_ = [f"# REM within sleep episodes: a time course beyond the count model? (cohort 2026c; episode rule {a.episode_rule})", "",
          "Plan [implementation_plan/2026-10-10-sleep-lfp-stage.md](../../../../implementation_plan/2026-10-10-sleep-lfp-stage.md) §10 "
          f"revision 4 (rules written before results){'' if a.episode_rule == 'plain' else ', amendment 1 (§10.7, post hoc): episode boundaries from night_sleep_wiser'}. "
          f"Driver `ephys/sleep_ramp.py run --episode-rule {a.episode_rule}` (commit {gc}); bulk `{out}`; runtime "
          f"{(time.time() - t0) / 60:.0f} min; figure [{fp.name}](../figures/{fp.name}). **Technical ledger.**", "",
          "## Verdicts", "", "(A) ramp residual and (B) shape not reproduced, per class (REM entry):", "", *md_table(V), "",
          "(C) the episode clock on held-out steps (REM log-loss):", "", *md_table(Cv), "",
          "## Episodes", "", *md_table(EPS.round(3)), "", "Main onsets vs night_sleep_wiser's mso (FINAL):", "", *md_table(pd.DataFrame(MSO)), "",
          "## (A) REM entry, observed vs held-out B-full, by minutes since onset", "", *md_table(show.round(3)), "",
          "Qualifying runs of adjacent bins (both scorings, same direction):", "", *(md_table(pd.DataFrame(RULES)) if RULES else ["none"]), "",
          "## (A) WAKE, observed vs held-out B-full", "", *md_table(A[(A.wake_rule == "main") & (A.outcome == "WAKE")][["scores", "cls", "bin_min", "O", "E", "oe", "lo", "hi"]].round(3)), "",
          "## (B) REM share of sleep, observed vs the simulator (100 replicates)", "", *md_table(BB.round(4)), "",
          "## (C) Held-out comparisons", "", *md_table(CC.round(4)), "",
          "## (D) Description: end-aligned REM O / E (observed ends only; selection-prone)", "", *md_table(DD.round(3)), "",
          "## (D) Sensitivity: (A) REM with a 10-min wake threshold", "",
          *md_table(A[(A.wake_rule != "main") & (A.outcome == "REM")][["scores", "cls", "bin_min", "at_risk", "O", "E", "oe", "lo", "hi"]].round(3)), ""]
    (rd / f"ephys_spikes_sleep_ramp{sfx}_2026c.md").write_text("\n".join(L_) + "\n", encoding="utf-8")
    write_json(rd / f"run_manifest_sleep_ramp{sfx}_2026c.json", {"run_dir": str(out), "git_commit": gc, "scorings": a.scorings, "reps": a.reps,
                                                               "episode_rule": a.episode_rule})
    print(EPS.to_string(index=False), flush=True)
    print(V.to_string(index=False), flush=True)
    print(Cv.to_string(index=False), flush=True)
    print(show[show.E >= MIN_E].round(3).to_string(index=False), flush=True)


# ------------------------------------------------------------------ selftest
def selftest() -> None:
    t0 = time.time()
    st = np.array([3] * 50 + [1] * 2000 + [3] * 1000 + [5] * 100 + [1] * 200 + [3] * 700 + [1] * 1900 + [3] * 500
                  + [0] * 100 + [3] * 400 + [0] * 30 + [3] * 70, np.int8)
    ep = record_episodes(st)
    got = [(e["onset"], e["end"], e["start_kind"], e["observed_end"]) for e in ep]
    want = [(0, 50, "record_start", True), (2050, 4050, "natural", True), (5950, 6450, "natural", False), (6550, 7050, "after_unknown", False)]
    assert got == want, got
    print("PASS episodes: onset after long wakes / record start / unknown runs; observed vs censored ends; short unknown kept", flush=True)
    st2 = np.array([3] * 100 + [1] * 1000 + [3] * 60 + [1] * 900 + [3] * 500, np.int8)
    assert [e["start_kind"] for e in record_episodes(st2)] == ["record_start"]          # plain: no single wake >= 30 min
    RULE.update(name="nsw")
    try:
        got2 = [(e["onset"], e["start_kind"]) for e in record_episodes(st2)]
    finally:
        RULE.update(name="plain")
    assert got2 == [(0, "record_start"), (2060, "natural")], got2
    print("PASS episode rule nsw: wake runs bridged across a < 120-s sleep interruption", flush=True)
    t = pd.Timestamp("2026-09-05 12:00:00")
    E = pd.DataFrame({"animal": ["SF07"] * 5, "record_id": [1, 1, 1, 2, 3], "start_kind": ["natural", "natural", "natural", "record_start", "record_start"],
                      "t_onset": [t + pd.Timedelta(hours=h) for h in (2, 9, 16.5, 20, 21)]})
    cls = classify(E, {2})
    assert list(cls) == ["day", "nap", "main", "post-round", "other"], cls
    print("PASS classes: main = last natural onset of the night, naps earlier, day otherwise; post-round vs other starts", flush=True)
    Et = pd.DataFrame({"record_id": [7, 7], "onset": [100, 5000], "end": [3000, 9000], "ep": [0, 1]})
    e_, u_ = locate(Et, np.array([7, 7, 7, 8]), np.array([150, 3500, 8999, 200]))
    assert list(e_) == [0, -1, 1, -1] and u_[0] == 50 and u_[2] == 3999, (e_, u_)
    print("PASS locate: step -> episode and u", flush=True)
    rng = np.random.default_rng(1)
    n = 300000
    epi = rng.integers(0, 600, n)
    u = rng.uniform(0, 400 * 60, n)
    p = 0.01 + 0.04 * (u / u.max())                                    # a ramp the predictor knows
    y = rng.random(n) < p
    b = np.searchsorted(np.array(BINS_MIN) * 60, u, side="right") - 1
    T = oe_table(epi, b, y.astype(float), p, np.array(["A", "B", "C"] * 200), len(BINS_MIN) - 1, rng, 300)
    ok = T["E"] >= 200
    assert ok.sum() >= 5 and np.all(np.abs(T["oe"][ok] - 1) < 0.12), (T["oe"], T["E"])
    T2 = oe_table(epi, b, y.astype(float), np.full(n, p.mean()), np.array(["A", "B", "C"] * 200), len(BINS_MIN) - 1, rng, 300)
    assert T2["oe"][ok][0] < 0.8 and T2["oe"][ok][-1] > 1.2, T2["oe"]
    print("PASS O / E: calibrated predictor ~ 1 in every bin; a flat predictor shows the ramp", flush=True)
    rows = pd.DataFrame([{"scores": s, "bin_i": i, "E": 50.0, "oe": 1.5 if i in (2, 3) else 1.0, "lo": 1.2 if i in (2, 3) else 0.8,
                          "hi": 1.8 if i in (2, 3) else 1.2} for s in ("final", "pass2med") for i in range(5)])
    pa = {s: {a: (np.array([5, 5, 15, 15, 5.0]), np.full(5, 5.0)) for a in "ABCDEF"} for s in ("final", "pass2med")}
    rr = ramp_rule(rows, pa)
    assert len(rr) == 1 and rr[0]["passes"] and rr[0]["bins"] == "2,3", rr
    print("PASS ramp rule: adjacent bins, both scorings, animal count", flush=True)
    print(f"selftest PASS ({time.time() - t0:.0f} s)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["run"])
    ap.add_argument("--scorings", nargs="+", default=["final", "pass2med"], choices=["final", "pass2med"])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--episode-rule", default="plain", choices=["plain", "nsw"])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == "run":
        run(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
