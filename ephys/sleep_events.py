r"""Phase 6 of the internal-schedule analysis: a library of sleep-perturbation events, with the LFP-EMG of every
participant (plan Amendment 10, written before results).
Called by `python ephys/sleep_schedule.py phase6 [--emg-root <dir>/<SFxx>/<s>.EMGFromLFP50Hz.npz]`.

The user, 2026-10-08: "movement but not awakening is very good, this will be a special window … group movement in REM and
in NREM; how often does this happen; separate such windows for future use: (1) disruption after which the animal wakes,
(2) disruption after which it does not".

Timeline. Everything lives on the field-PC clock:
- FINAL 1-s scores, cut at 09-11 19:40;
- WISER zone per second (house_1 / house_2 = wiser_rois.json + 14 in; field; unknown);
- head VeDBA at 50 Hz from make_imu, invalid samples blanked.

Movement onset (as Phase 5c):
- per animal, theta = median + 8 * 1.4826 * MAD of VeDBA in scored-NREM seconds;
- onset = the first 50-Hz sample >= theta after >= 1 s below it;
- an "asleep onset" is one whose second is scored NREM or REM.

Movement events, per house (source = movement):
- Seed: an asleep onset of an animal in the house, with no onset of any animal in that house, in any state, during the
  2 s before. The next seed must come more than 1 s after the previous one.
- Members: the animals in the house at the seed second.
- Movers: members with an asleep onset in [t0, t0 + 1 s]. role = first (the seed) or follower (with its lag).
  Other members are non_mover if asleep, awake if not.
- type:
  - group = >= 2 movers;
  - solo = 1 mover and >= 1 other member asleep;
  - alone = no other member asleep.
- Followers are split by lag (role_detail):
  - follower_tight = <= 0.1 s, the Phase-5c peak, 6-10x chance;
  - follower_loose = 0.1-1 s, ~2x chance.
- Chance level per event (null_tight / null_any): the same follower test (an asleep housemate's onset after 2 s
  without one) in windows shifted by -47 / -31 / +31 / +47 s, averaged. Coupled events above chance per co-sleep hour
  = (observed share - chance share) x seeds / co-sleep hours.

Sound candidates (source = sound; UNVALIDATED until the user's listening check):
- Level jump J(t) = max over b0-b2 (50 Hz-20 kHz) of [b_max_db(t) - median of b_max_db over t-60..t-20 s].
- The microphone is the house's own in-house mic: MIC02 = house_1, MIC01 = house_2.
- Event = J >= 20 dB after a second below 20 dB, while every member is asleep over t-10..t and no member had an onset
  in the 5 s before.
- Members who move in [t0, t0 + 2 s] get role moved_after_sound; the others get non_mover / awake.
- J is per second, so a member's movement inside the same second may have made the sound (column move_same_second).

Handling (battery rounds, Phase-0 gap table; usable gaps caused by a logged or inferred round). The gap itself is
unobserved, so this source has only pre / post:
- before the stop: the last scored state and the composition of the last 10 min;
- after the restart: latency to the first NREM run >= 60 s, latency to the first REM, wake share of the first 10 min.

Per participant (outcome only for members asleep at t0):
- state at +10 / +30 / +60 s;
- class30 = the first state change within 30 s: stay / to_REM / to_NREM / wake / unknown;
- woke30 / woke60 = any scored WAKE within 30 / 60 s;
- the first wake: latency, duration (run of WAKE, capped at 1 h, censored at unknown), and
  wake_kind = MA (< 40 s, Watson 2016) or long (>= 40 s);
- scenario = woke (wake within 60 s) or not_woken;
- follow-up: the state composition +1..+10 min.

Complete flags:
- imu_ok = the IMU is valid (>= 90 % of the 50-Hz samples) over t0-2..t0+2 s;
- state_ok = the score is known over t0-60..t0+60 s.

Pointers:
- the logger session and its 50-Hz IMU index i (amp_sample = 400 i);
- the LFP sample (= amp_sample / 16) and the storage LFP path;
- the fast EMG bin j (= i);
- the house cameras (inside CH08 / CH07, outside CH05 / CH06), the house mic and CH01, as file + offset (s). The file
  names are field-PC time.

Controls:
- random co-sleep seconds (>= 2 members asleep, every member's IMU valid, scores known);
- the same outcome fields, and the same all / some / none event classes.

Rates: complete events per co-sleep hour (the same co-sleep seconds), by type and seed state.

LFP-EMG (fast product of ephys/emg_from_lfp.py, 50 Hz, 300-450 Hz):
- per participant, dcorr = mean corr over [-0.1, +0.5] s minus mean over [-2, -1] s; dlog_rms the same for the band
  amplitude;
- burst = dcorr above the 95th percentile of the same statistic at 200 random asleep times of that session (null).
- Passive-jolt control (a jolt could put motion artefact into the LFP):
  - (b) compare roles within terciles of the peak head VeDBA over 0..+0.5 s, i.e. at a matched movement size;
  - (c) per role, the half-maximum and peak times of the mean VeDBA and mean EMG-corr traces. Muscle activity
    leading the head acceleration is the active signature.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from sleep_cycles_v2 import build_records  # noqa: E402
from sleep_schedule import N, R, ROOT, W, included_sessions  # noqa: E402

FS = 50
OUT = Path("D:/Field2026_analysis_out/2026c")
IMU = Path("D:/3rd_rat_spikes/analysis/imu")
VIDEO_ROOT = Path("F:/3rd_rat")
STORAGE = "Q:/hc997/SocialFieldRat2026/3rd_rat"
HOUSE_STREAMS = {1: {"cam_in": "CH08", "cam_out": "CH05", "mic": "MIC02"}, 2: {"cam_in": "CH07", "cam_out": "CH06", "mic": "MIC01"}}
PRE_QUIET_S, JOIN_S, SOUND_DB = 2, 1, 20.0
TIGHT_S = 0.1                              # a follower within 0.1 s: the Phase-5c peak (6-10x chance); 0.1-1 s: ~2x chance
NULL_SHIFTS_S = (-47, -31, 31, 47)         # chance level of a follower: the same test at these offsets
TR = 150                                   # trace half-width in 50-Hz samples (3 s)


# ------------------------------------------------------------------ helpers
def stream_index(stream: str) -> pd.DataFrame:
    from mic_band_levels import NAME_RE, parse_name
    rows = []
    for d in sorted(VIDEO_ROOT.glob("2026-*")):
        for f in (d / stream).glob(f"{stream}_*"):
            if NAME_RE.search(f.name):
                _, s, e = parse_name(f)
                rows.append({"start": s, "end": e, "rel": f"{d.name}/{stream}/{f.name}"})
    df = pd.DataFrame(rows).sort_values("start").reset_index(drop=True)
    if len(df):
        nxt = df.start.shift(-1)
        df["end"] = df.end.fillna(nxt).fillna(df.start + pd.Timedelta(hours=1))
    return df


def locate(idx: pd.DataFrame, t: pd.Timestamp) -> tuple[str, float]:
    if idx is None or not len(idx):
        return "", np.nan
    i = int(np.searchsorted(idx.start.to_numpy(), np.datetime64(t), side="right")) - 1
    if i < 0 or t >= idx.end.iloc[i]:
        return "", np.nan
    return idx.rel.iloc[i], (t - idx.start.iloc[i]).total_seconds()


def outcome(s: np.ndarray, sec: int) -> dict:
    """Outcome of a member asleep at second `sec` (s = its 1-s state array, 0 = unknown)."""
    pre = int(s[sec])
    n = len(s)
    r = {"pre_state": {W: "WAKE", N: "NREM", R: "REM"}.get(pre, "unknown")}
    for d in (10, 30, 60):
        r[f"s{d}"] = {W: "WAKE", N: "NREM", R: "REM", 0: "unknown"}.get(int(s[sec + d]), "unknown") if sec + d < n else "unknown"
    w = s[sec + 1:min(n, sec + 61)]
    ch = np.flatnonzero(w[:30] != pre)
    r["class30"] = "stay" if not len(ch) else {W: "wake", R: "to_REM", N: "to_NREM"}.get(int(w[ch[0]]), "unknown")
    wk = np.flatnonzero(w == W)
    r["woke30"] = bool(len(wk) and wk[0] < 30)
    r["woke60"] = bool(len(wk))
    r["scenario"] = "woke" if len(wk) else "not_woken"
    if len(wk):
        a = sec + 1 + wk[0]
        seg = s[a:min(n, a + 3600)]
        nz = np.flatnonzero(seg != W)
        dur = int(nz[0]) if len(nz) else len(seg)
        r.update(wake_latency_s=int(wk[0] + 1), wake_dur_s=dur,
                 wake_censored=bool(len(nz) == 0 or seg[nz[0]] == 0), wake_kind="MA" if dur < 40 else "long")
    else:
        r.update(wake_latency_s=np.nan, wake_dur_s=np.nan, wake_censored=False, wake_kind="none")
    fu = s[sec + 61:min(n, sec + 601)]
    for nm, v in (("W", W), ("N", N), ("R", R)):
        r[f"fu_{nm}"] = float(np.mean(fu == v)) if len(fu) else np.nan
    r["fu_known"] = float(np.mean(fu > 0)) if len(fu) else 0.0
    return r


# ------------------------------------------------------------------ main
def phase6(a) -> None:
    from _common import git_commit, write_json
    from mic_wake_pilot import load_zone
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_quant import md_table, save_fig
    out = run_dir("sleep_events" + ("_smoke" if a.smoke else ""), "2026c")
    rd = out if a.smoke else report_dir("2026c", "ephys_spikes")
    fd = out if a.smoke else figure_dir("2026c", "ephys_spikes")
    gc = git_commit()
    rng = np.random.default_rng(6)
    rv = included_sessions(Path(a.review), Path(a.states))
    recs = build_records(rv, Path(a.states))
    t_min = min(rc["start"] for rc in recs).floor("s")
    t_max = max(rc["end"] for rc in recs).ceil("s")
    span = int((t_max - t_min).total_seconds()) + 1
    rois = {r_["name"]: r_ for r_ in json.load(open(ROOT / "wiser/configs/wiser_rois.json"))["rois"] if r_["name"] in ("house_1", "house_2")}
    dates = sorted({d.strftime("%Y%m%d") for d in pd.date_range(t_min.normalize(), t_max.normalize())})
    animals = sorted({rc["animal"] for rc in recs})
    S, Z, V, OK, SOS, SNAMES, ONS, ASL, TH = {}, {}, {}, {}, {}, {}, {}, {}, {}
    for an in animals:
        s = np.zeros(span, np.int8)
        for rc in recs:
            if rc["animal"] == an:
                o = int((rc["start"] - t_min).total_seconds())
                s[o:o + len(rc["state"])] = rc["state"][:max(0, span - o)]
        S[an] = s
        z = load_zone(an, dates, rois)
        zz = z.reindex(pd.date_range(t_min, t_max, freq="1s")[:span]) if len(z) else pd.Series(index=range(span), dtype=object)
        Z[an] = np.select([zz.eq("house_1").to_numpy(), zz.eq("house_2").to_numpy(), zz.eq("field").to_numpy()], [1, 2, 3], 0).astype(np.int8)
        v = np.full(span * FS, np.nan, np.float32)
        sos = np.full(span, -1, np.int16)
        names = []
        for sess in rv[rv.animal == an].session:
            f, jf = IMU / an / f"{sess}.imu.npz", IMU / an / f"{sess}.imu.json"
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
            kin = k[(k >= 0) & (k < len(v))]
            if len(kin):
                sos[kin.min() // FS:kin.max() // FS + 1] = len(names)
                names.append(sess)
        SOS[an], SNAMES[an] = sos, names
        OK[an] = np.isfinite(v).reshape(span, FS).mean(1) >= 0.9
        sec = np.arange(len(v)) // FS
        nrem = (s[sec] == N) & np.isfinite(v)
        med = np.nanmedian(v[nrem])
        mad = np.nanmedian(np.abs(v[nrem] - med))
        TH[an] = med + 8 * 1.4826 * mad
        above = np.nan_to_num(v, nan=0) >= TH[an]
        csum = np.r_[0, np.cumsum(above)]
        kk = np.flatnonzero(above)
        kk = kk[kk >= FS]
        onset = kk[(csum[kk] - csum[kk - FS]) == 0]
        ONS[an] = onset
        ASL[an] = np.isin(s[onset // FS], (N, R))
        V[an] = v
        print(an, "theta", round(float(TH[an]), 3), "onsets", len(onset), "asleep", int(ASL[an].sum()), flush=True)
        del sec, nrem, above, csum

    def t_of(k: int) -> pd.Timestamp:
        return t_min + pd.Timedelta(milliseconds=20 * int(k))

    # ---------------- movement events
    events, parts = [], []

    def add_member_rows(eid: str, src: str, h: int, k0: int, members: list[str], roles: dict, lags: dict) -> None:
        sec = k0 // FS
        for bn in members:
            st = int(S[bn][sec])
            r = {"event_id": eid, "source": src, "house": h, "animal": bn, "role": roles[bn], "lag_s": lags.get(bn, np.nan),
                 "k50": int(k0), "imu_ok": bool(OK[bn][max(0, sec - 2):sec + 3].all()),
                 "state_ok": bool((S[bn][max(0, sec - 60):sec + 61] > 0).all() and sec >= 60 and sec + 60 < span)}
            pre = S[bn][max(0, sec - 60):sec]
            for nm, v_ in (("W", W), ("N", N), ("R", R)):
                r[f"pre60_{nm}"] = float(np.mean(pre == v_)) if len(pre) else np.nan
            if st in (N, R):
                r.update(outcome(S[bn], sec))
            else:
                r["pre_state"] = {W: "WAKE"}.get(st, "unknown")
            parts.append(r)

    for h in (1, 2):
        all_k, cand_k, cand_a = [], [], []
        for an in animals:
            o = ONS[an]
            inh = Z[an][o // FS] == h
            all_k.append(o[inh])
            m = inh & ASL[an]
            cand_k.append(o[m])
            cand_a += [an] * int(m.sum())
        all_k = np.sort(np.concatenate(all_k))
        ck = np.concatenate(cand_k)
        ca = np.asarray(cand_a)
        order = np.argsort(ck, kind="stable")
        ck, ca = ck[order], ca[order]
        prev = np.searchsorted(all_k, ck, side="left") - 1
        quiet = (prev < 0) | (all_k[np.maximum(prev, 0)] < ck - PRE_QUIET_S * FS)
        last = -10 ** 12
        n_h = 0
        for k0, an in zip(ck[quiet], ca[quiet]):
            if k0 <= last:
                continue
            last = k0 + JOIN_S * FS
            sec = int(k0 // FS)
            members = [bn for bn in animals if Z[bn][sec] == h]
            roles, lags = {}, {}
            for bn in members:
                o = ONS[bn]
                i0, i1 = np.searchsorted(o, k0), np.searchsorted(o, k0 + JOIN_S * FS, side="right")
                asl = [ii for ii in range(i0, i1) if ASL[bn][ii]]
                if bn == an:
                    roles[bn], lags[bn] = "first", 0.0
                elif asl:
                    roles[bn], lags[bn] = "follower", (o[asl[0]] - k0) / FS
                else:
                    roles[bn] = "non_mover" if S[bn][sec] in (N, R) else "awake"
                    if i1 > i0:
                        lags[bn] = (o[i0] - k0) / FS          # an awake member's own movement in the window
            n_mov = sum(r_ in ("first", "follower") for r_ in roles.values())
            n_asl_other = sum(roles[bn] == "non_mover" for bn in members) + n_mov - 1
            typ = "group" if n_mov >= 2 else ("solo" if n_asl_other >= 1 else "alone")
            fl = [lags[bn] for bn in members if roles[bn] == "follower"]
            # chance level: the same follower test in windows shifted by +-31 / +-47 s (each asleep housemate's own onsets,
            # with the same 2-s quiet rule before the shifted window)
            mates = [bn for bn in members if bn != an and roles[bn] in ("follower", "non_mover")]
            nt = na = 0
            for D in NULL_SHIFTS_S:
                kd = k0 + D * FS
                ht = hy = False
                for bn in mates:
                    o = ONS[bn]
                    if np.any((o >= kd - PRE_QUIET_S * FS) & (o < kd)):
                        continue
                    i0, i1 = np.searchsorted(o, kd), np.searchsorted(o, kd + JOIN_S * FS, side="right")
                    hit = [o[ii] for ii in range(i0, i1) if ASL[bn][ii]]
                    if hit:
                        hy = True
                        ht |= (hit[0] - kd) / FS <= TIGHT_S
                nt += ht
                na += hy
            n_h += 1
            eid = f"M{h}_{n_h:06d}"
            events.append({"event_id": eid, "source": "movement", "type": typ, "house": h, "k50": int(k0), "t0": t_of(k0),
                           "seed": an, "seed_state": "REM" if S[an][sec] == R else "NREM", "n_members": len(members),
                           "n_movers": n_mov, "members": ";".join(members), "n_asleep_mates": len(mates),
                           "min_follower_lag_s": min(fl) if fl else np.nan, "tight": bool(fl and min(fl) <= TIGHT_S),
                           "null_tight": nt / len(NULL_SHIFTS_S) if mates else np.nan,
                           "null_any": na / len(NULL_SHIFTS_S) if mates else np.nan})
            add_member_rows(eid, "movement", h, int(k0), members, roles, lags)
        print(f"house_{h}: {n_h} movement events", flush=True)

    # ---------------- sound candidates
    sec_index = pd.date_range(t_min, periods=span, freq="1s")
    sound_n = 0
    for h, st_ in HOUSE_STREAMS.items():
        fs_ = sorted((OUT / "audio_levels" / st_["mic"]).glob("*.csv.gz"))
        if not fs_:
            print("no levels for", st_["mic"], flush=True)
            continue
        lv = pd.concat([pd.read_csv(f, parse_dates=["t_pc"]) for f in fs_]).drop_duplicates("t_pc").set_index("t_pc").sort_index()
        lv = lv.reindex(sec_index)
        J = None
        for b in ("b0", "b1", "b2"):
            x = lv[f"{b}_max_db"]
            base = x.rolling(41, min_periods=20).median().shift(20)
            j_ = x - base
            J = j_ if J is None else np.fmax(J, j_)
        Jv = J.to_numpy()
        cand = np.flatnonzero((Jv >= SOUND_DB) & (np.r_[np.nan, Jv[:-1]] < SOUND_DB))
        for sec in cand:
            if sec < 60 or sec + 61 >= span:
                continue
            members = [bn for bn in animals if Z[bn][sec] == h]
            if not members or not all(np.isin(S[bn][sec - 10:sec + 1], (N, R)).all() for bn in members):
                continue
            k0 = sec * FS
            pre_move = any(((ONS[bn] >= k0 - 5 * FS) & (ONS[bn] < k0)).any() for bn in members)
            if pre_move:
                continue
            roles, lags = {}, {}
            same = False
            for bn in members:
                o = ONS[bn]
                hit = o[(o >= k0) & (o <= k0 + 2 * FS)]
                if len(hit):
                    roles[bn], lags[bn] = "moved_after_sound", (hit[0] - k0) / FS
                    same |= bool(hit[0] < k0 + FS)
                else:
                    roles[bn] = "non_mover"
            sound_n += 1
            eid = f"S{h}_{sound_n:06d}"
            events.append({"event_id": eid, "source": "sound", "type": "sound", "house": h, "k50": int(k0), "t0": t_of(k0),
                           "seed": "", "seed_state": "", "n_members": len(members), "n_movers": len(lags), "members": ";".join(members),
                           "jump_db": float(Jv[sec]), "move_same_second": same})
            add_member_rows(eid, "sound", h, int(k0), members, roles, lags)
        print(f"house_{h}: sound candidates so far {sound_n}", flush=True)

    E = pd.DataFrame(events)
    P = pd.DataFrame(parts)

    # ---------------- controls: random co-sleep seconds
    ctrl_e, ctrl_p = [], []
    cos_sec = {}
    for h in (1, 2):
        memb = np.stack([Z[bn] == h for bn in animals])                    # animals x span
        asl = np.stack([np.isin(S[bn], (N, R)) for bn in animals]) & memb
        okm = np.stack([OK[bn] for bn in animals]) | ~memb
        cos = (asl.sum(0) >= 2) & okm.all(0)
        cos_sec[h] = int(cos.sum())
        pool = np.flatnonzero(cos & (np.arange(span) >= 60) & (np.arange(span) + 601 < span))
        pick = np.sort(rng.choice(pool, size=min(20000, len(pool)), replace=False)) if len(pool) else []
        for i, sec in enumerate(pick):
            members = [bn for j, bn in enumerate(animals) if memb[j, sec]]
            eid = f"C{h}_{i:06d}"
            ctrl_e.append({"event_id": eid, "source": "control", "type": "control", "house": h, "k50": int(sec * FS),
                           "t0": t_min + pd.Timedelta(seconds=int(sec)), "n_members": len(members), "members": ";".join(members)})
            for bn in members:
                st = int(S[bn][sec])
                r = {"event_id": eid, "source": "control", "house": h, "animal": bn,
                     "role": "control" if st in (N, R) else "awake", "imu_ok": True,
                     "state_ok": bool((S[bn][sec - 60:sec + 61] > 0).all())}
                if st in (N, R):
                    r.update(outcome(S[bn], sec))
                ctrl_p.append(r)
    CE, CP = pd.DataFrame(ctrl_e), pd.DataFrame(ctrl_p)
    P["role_detail"] = np.where(P.role.eq("follower"), np.where(P.lag_s <= TIGHT_S, "follower_tight", "follower_loose"), P.role)
    CP["role_detail"] = CP.role

    # ---------------- handling (battery rounds)
    hrows = []
    g0 = json.load(open(ROOT / "results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_phase0_2026c.json"))["run_dir"]
    gaps = pd.read_csv(Path(g0) / "gaps.csv", parse_dates=["gap_start", "gap_end"])
    gaps = gaps[gaps.usable & gaps.cause.isin(["round_logged", "round_inferred"])]
    for g in gaps.itertuples():
        if g.animal not in S:
            continue
        s = S[g.animal]
        a0 = int((g.gap_start - t_min).total_seconds())
        a1 = int(np.ceil((g.gap_end - t_min).total_seconds()))
        if a0 < 600 or a1 + 600 >= span:
            continue
        pre, post = s[a0 - 600:a0], s[a1:a1 + 3600]
        known = np.flatnonzero(s[:a0] > 0)
        nrun = np.flatnonzero(np.convolve(post == N, np.ones(60), "valid") == 60)
        rem = np.flatnonzero(post == R)
        zone = int(Z[g.animal][max(0, a0 - 60)])
        hrows.append({"event_id": f"H_{len(hrows) + 1:04d}", "source": "handling", "animal": g.animal, "kind": g.kind, "cause": g.cause,
                      "t_stop": g.gap_start, "t_restart": g.gap_end, "gap_min": round(g.gap_min, 1), "house_before": zone,
                      "last_state": {W: "WAKE", N: "NREM", R: "REM"}.get(int(s[known[-1]]), "unknown") if len(known) else "unknown",
                      "pre10_W": float(np.mean(pre == W)), "pre10_N": float(np.mean(pre == N)), "pre10_R": float(np.mean(pre == R)),
                      "post_first_NREM60_min": nrun[0] / 60 if len(nrun) else np.nan, "post_first_REM_min": rem[0] / 60 if len(rem) else np.nan,
                      "post10_W": float(np.mean(post[:600] == W)), "post10_known": float(np.mean(post[:600] > 0))})
    HD = pd.DataFrame(hrows)

    # ---------------- pointers
    print("pointers ...", flush=True)
    idx = {st: stream_index(st) for st in ("CH05", "CH06", "CH07", "CH08", "MIC01", "MIC02", "CH01")}
    for col, key in (("cam_in", "cam_in"), ("cam_out", "cam_out"), ("mic", "mic")):
        fl, off = [], []
        for e in E.itertuples():
            f_, o_ = locate(idx[HOUSE_STREAMS[e.house][key]], e.t0)
            fl.append(f_)
            off.append(o_)
        E[f"{col}_file"], E[f"{col}_offset_s"] = fl, off
    f1 = [locate(idx["CH01"], t) for t in E.t0]
    E["ch01_file"], E["ch01_offset_s"] = [x[0] for x in f1], [x[1] for x in f1]
    E["window_start"], E["window_end"] = E.t0 - pd.Timedelta(seconds=60), E.t0 + pd.Timedelta(seconds=60)
    for c in ("cam_in", "cam_out"):
        for side in ("stop", "restart"):
            HD[f"{c}_{side}_file"] = [locate(idx[HOUSE_STREAMS[hb][c]], t)[0] if hb in (1, 2) else ""
                                      for hb, t in zip(HD.house_before, HD[f"t_{side}"])] if len(HD) else []
    # IMU / LFP / EMG pointers per participant
    P["session"], P["imu_i"], P["amp_sample"] = "", -1, -1
    P["sec"] = P.k50 // FS
    for an in animals:
        rows = P.index[P.animal == an]
        si = SOS[an][P.loc[rows, "sec"].to_numpy()]
        for s_i in np.unique(si[si >= 0]):
            sess = SNAMES[an][s_i]
            rr = rows[si == s_i]
            with np.load(IMU / an / f"{sess}.imu.npz") as zf:
                tp, amp = zf["t_pc_ms"], zf["amp_sample"]
            day = pd.Timestamp(json.loads((IMU / an / f"{sess}.imu.json").read_text())["start_local"]).normalize()
            kk = np.round(((day - t_min).total_seconds() * 1000 + tp) / (1000 / FS)).astype(np.int64)
            ii = np.clip(np.searchsorted(kk, P.loc[rr, "k50"].to_numpy()), 0, len(kk) - 1)
            good = np.abs(kk[ii] - P.loc[rr, "k50"].to_numpy()) <= 1
            P.loc[rr, "session"] = np.where(good, sess, "")
            P.loc[rr, "imu_i"] = np.where(good, ii, -1)
            P.loc[rr, "amp_sample"] = np.where(good, amp[ii], -1)
    P["lfp_sample"] = np.where(P.amp_sample >= 0, P.amp_sample // 16, -1)
    P["emg_j"] = np.where(P.amp_sample >= 0, P.amp_sample // 400, -1)
    P["lfp_file"] = [f"{STORAGE}/analysis/lfp/{an}/{s}.lfp" if s else "" for an, s in zip(P.animal, P.session)]

    # ---------------- traces (VeDBA; EMG if available)
    n_p = len(P)
    tr_v = np.full((n_p, 2 * TR + 1), np.nan, np.float16)
    for an in animals:
        rows = np.flatnonzero(P.animal.to_numpy() == an)
        ks = P.k50.to_numpy()[rows]
        ok_ = (ks - TR >= 0) & (ks + TR < len(V[an]))
        win = ks[ok_, None] + np.arange(-TR, TR + 1)[None, :]
        tr_v[rows[ok_]] = V[an][win].astype(np.float16)     # m/s^2
    tr_c = np.full((n_p, 2 * TR + 1), np.nan, np.float16)
    tr_r = np.full((n_p, 2 * TR + 1), np.nan, np.float16)
    P["dcorr"], P["dlog_rms"], P["dcorr_null_p95"], P["emg_burst"] = np.nan, np.nan, np.nan, np.nan
    emg_root = Path(a.emg_root) if getattr(a, "emg_root", None) else None
    n_sess_emg = 0
    if emg_root is not None:
        for (an, sess), g in P[P.session != ""].groupby(["animal", "session"]):
            f = emg_root / an / f"{sess}.EMGFromLFP50Hz.npz"
            if not f.exists():
                continue
            n_sess_emg += 1
            with np.load(f) as zf:
                j0, corr, lr = int(zf["j"][0]), zf["corr"], zf["log_rms"]
            jj = g.emg_j.to_numpy() - j0
            ok_ = (jj - TR >= 0) & (jj + TR < len(corr))
            rows = g.index.to_numpy()[ok_]
            win = jj[ok_, None] + np.arange(-TR, TR + 1)[None, :]
            tr_c[rows], tr_r[rows] = corr[win].astype(np.float16), lr[win].astype(np.float16)

            def delta(x: np.ndarray, centres: np.ndarray) -> np.ndarray:
                post = x[centres[:, None] + np.arange(-5, 26)[None, :]].mean(1)
                base = x[centres[:, None] + np.arange(-100, -49)[None, :]].mean(1)
                return post - base
            P.loc[rows, "dcorr"] = delta(corr, jj[ok_])
            P.loc[rows, "dlog_rms"] = delta(lr, jj[ok_])
            # null: random asleep seconds of this session
            ss_ = np.flatnonzero((SOS[an] == SNAMES[an].index(sess)) & np.isin(S[an], (N, R)))
            if len(ss_) > 200:
                ks = rng.choice(ss_, 200, replace=False) * FS
                # map the absolute 50-Hz index to j through the session's offset at the event rows
                off = int(np.median(g.emg_j.to_numpy() - g.k50.to_numpy()))
                jn = ks + off - j0
                jn = jn[(jn - 100 >= 0) & (jn + 26 < len(corr))]
                if len(jn) > 50:
                    p95 = float(np.nanpercentile(delta(corr, jn), 95))
                    P.loc[g.index, "dcorr_null_p95"] = p95
            print(f"EMG {an} {sess}: {len(rows)} rows", flush=True)
        P["emg_burst"] = np.where(P.dcorr.notna() & P.dcorr_null_p95.notna(), (P.dcorr > P.dcorr_null_p95).astype(float), np.nan)

    # ---------------- tables
    comp = P.imu_ok & P.state_ok
    ev_comp = P.groupby("event_id").apply(lambda g: bool((g.imu_ok & g.state_ok).all()), include_groups=False)
    E["complete"] = E.event_id.map(ev_comp).fillna(False)
    Em = E[(E.source == "movement") & E.complete]
    T1 = (Em.groupby(["house", "type", "seed_state"]).size().rename("events").reset_index())
    T1["cosleep_h"] = T1.house.map(cos_sec) / 3600
    T1["per_cosleep_h"] = T1.events / T1.cosleep_h
    rows_c = []
    for (h, ss_), g in Em[Em.n_asleep_mates >= 1].groupby(["house", "seed_state"]):
        hrs = cos_sec[h] / 3600
        r_ = {"house": h, "seed_state": ss_, "seeds_with_asleep_mates": len(g),
              "follower_0.1s": g.tight.mean(), "chance_0.1s": g.null_tight.mean(),
              "follower_1s": (g.type == "group").mean(), "chance_1s": g.null_any.mean()}
        for w in ("0.1s", "1s"):
            r_[f"ratio_{w}"] = r_[f"follower_{w}"] / r_[f"chance_{w}"] if r_[f"chance_{w}"] > 0 else np.nan
            r_[f"above_chance_per_cosleep_h_{w}"] = (r_[f"follower_{w}"] - r_[f"chance_{w}"]) * len(g) / hrs
        rows_c.append(r_)
    T1b = pd.DataFrame(rows_c)
    # event level: asleep participants other than nothing - how many woke within 60 s
    asleep = P[comp & P.pre_state.isin(["NREM", "REM"])]

    def ev_class(df: pd.DataFrame) -> pd.Series:
        g = df.groupby("event_id").agg(n=("woke60", "size"), k=("woke60", "sum"))
        g = g[g.n >= 2]
        return pd.Series({"events": len(g), "all_stay_asleep": float(np.mean(g.k == 0)) if len(g) else np.nan,
                          "some_wake": float(np.mean((g.k > 0) & (g.k < g.n))) if len(g) else np.nan,
                          "all_wake": float(np.mean(g.k == g.n)) if len(g) else np.nan})
    rows = []
    for (typ, ss_), ge in Em.groupby(["type", "seed_state"]):
        rows.append({"what": f"movement {typ}, seed in {ss_}", **ev_class(asleep[asleep.event_id.isin(ge.event_id)]).to_dict()})
    Es = E[(E.source == "sound") & E.complete]
    if len(Es):
        rows.append({"what": "sound candidate", **ev_class(asleep[asleep.event_id.isin(Es.event_id)]).to_dict()})
    CPa = CP[CP.state_ok & CP.pre_state.isin(["NREM", "REM"])] if len(CP) else CP
    if len(CPa):
        rows.append({"what": "control (random co-sleep second)", **ev_class(CPa).to_dict()})
    T2 = pd.DataFrame(rows)

    def role_tab(df: pd.DataFrame, label: str) -> pd.DataFrame:
        g = df.groupby(["role_detail", "pre_state"])
        t = g.agg(n=("animal", "size"), animals=("animal", "nunique"), woke30=("woke30", "mean"), woke60=("woke60", "mean"),
                  MA=("wake_kind", lambda x: np.mean(x == "MA")), long_wake=("wake_kind", lambda x: np.mean(x == "long")),
                  stay30=("class30", lambda x: np.mean(x == "stay")), to_REM30=("class30", lambda x: np.mean(x == "to_REM")),
                  to_NREM30=("class30", lambda x: np.mean(x == "to_NREM")), wake30=("class30", lambda x: np.mean(x == "wake"))).reset_index()
        t.insert(0, "source", label)
        return t
    T3 = pd.concat([role_tab(asleep[asleep.source == "movement"], "movement"),
                    role_tab(asleep[asleep.source == "sound"], "sound") if (asleep.source == "sound").any() else pd.DataFrame(),
                    role_tab(CPa, "control") if len(CPa) else pd.DataFrame()], ignore_index=True)
    # per-animal check of the key contrast: woke60 of first movers vs controls, by pre-state
    pa = []
    for (an, ps), g in asleep[asleep.source == "movement"].groupby(["animal", "pre_state"]):
        c = CPa[(CPa.animal == an) & (CPa.pre_state == ps)] if len(CPa) else pd.DataFrame()
        r_ = {"animal": an, "pre_state": ps, "control_woke60": float(c.woke60.mean()) if len(c) else np.nan, "control_n": len(c)}
        for role in ("first", "follower_tight", "follower_loose", "non_mover"):
            x = g[g.role_detail == role]
            r_[f"{role}_n"], r_[f"{role}_woke60"] = len(x), float(x.woke60.mean()) if len(x) else np.nan
        pa.append(r_)
    T4 = pd.DataFrame(pa)
    T5, T5b, T5c = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if P.dcorr.notna().any():
        e_ = asleep[asleep.dcorr.notna() & (asleep.source == "movement")]
        T5 = e_.groupby(["role_detail", "pre_state"]).agg(n=("animal", "size"), animals=("animal", "nunique"),
                                                   dcorr_mean=("dcorr", "mean"), dcorr_median=("dcorr", "median"),
                                                   dlog_rms_mean=("dlog_rms", "mean"), burst_share=("emg_burst", "mean")).reset_index()
        ap_ = e_.groupby(["animal", "role_detail", "pre_state"]).agg(n=("dcorr", "size"), dcorr_median=("dcorr", "median"),
                                                              burst_share=("emg_burst", "mean")).reset_index()
        ap_.to_csv(out / "emg_by_animal_role.csv", index=False)
        # (b) matched movement size: peak head VeDBA over [0, +0.5] s, terciles over all movers (first + followers)
        pk = np.nanmax(tr_v[:, TR:TR + 26].astype(np.float32), axis=1)
        e2 = e_.assign(peak_vedba=pk[e_.index.to_numpy()])
        mv = e2[e2.role_detail.isin(["first", "follower_tight", "follower_loose"])]
        if len(mv) > 100:
            edges = np.nanquantile(mv.peak_vedba, [0, 1 / 3, 2 / 3, 1])
            e2["vedba_tercile"] = pd.cut(e2.peak_vedba, edges, labels=["low", "mid", "high"], include_lowest=True)
            T5b = (e2[e2.vedba_tercile.notna()].groupby(["pre_state", "vedba_tercile", "role_detail"], observed=True)
                   .agg(n=("dcorr", "size"), peak_vedba_median=("peak_vedba", "median"), dcorr_median=("dcorr", "median"),
                        burst_share=("emg_burst", "mean")).reset_index())
        # (c) timing: half-maximum crossing of the mean VeDBA and mean EMG-corr traces (baseline -2..-1 s), per role
        rows_t = []
        for (rl, ps), g in e_.groupby(["role_detail", "pre_state"]):
            ii = g.index.to_numpy()
            row = {"role_detail": rl, "pre_state": ps, "n": len(ii)}
            for nm, arr in (("vedba", tr_v), ("emg_corr", tr_c)):
                y = np.nanmean(arr[ii].astype(np.float32), axis=0)
                b = np.nanmean(y[TR - 100:TR - 49])
                seg = y[TR - 50:TR + 51] - b                        # -1..+1 s
                if np.nanmax(seg) > 0:
                    k = int(np.argmax(seg >= 0.5 * np.nanmax(seg)))
                    row[f"{nm}_halfmax_s"] = (k - 50) / FS
                    row[f"{nm}_peak_s"] = (int(np.nanargmax(seg)) - 50) / FS
            rows_t.append(row)
        T5c = pd.DataFrame(rows_t)

    # ---------------- write the library
    E.to_csv(out / "events.csv.gz", index=False)
    P.to_csv(out / "participants.csv.gz", index=False)
    CE.to_csv(out / "control_events.csv.gz", index=False)
    CP.to_csv(out / "control_participants.csv.gz", index=False)
    HD.to_csv(out / "handling.csv.gz", index=False)
    np.savez_compressed(out / "traces.npz", t_s=np.arange(-TR, TR + 1) / FS, vedba=tr_v, emg_corr=tr_c, emg_log_rms=tr_r,
                        row=np.arange(n_p))
    for name, T in (("rates", T1), ("chance", T1b), ("event_outcome", T2), ("role_outcome", T3), ("per_animal", T4), ("emg", T5), ("emg_matched", T5b), ("emg_timing", T5c), ("handling", HD)):
        if len(T):
            T.to_csv(rd / f"ephys_spikes_sleep_events_{name}_2026c.csv", index=False)
            print(name, "\n", T.round(3).to_string(index=False), flush=True)
    readme = f"""Sleep-perturbation event library, cohort 2026c (ephys/sleep_events.py, `sleep_schedule.py phase6`, commit {gc}).
Plan: implementation_plan/2026-10-07-sleep-internal-schedule.md, Amendment 10. Definitions: the module docstring (copied in
the report results/2026c/ephys_spikes/reports/ephys_spikes_sleep_events_2026c.md).

Files
  events.csv.gz            one row per event (source movement / sound): event_id, type (group / solo / alone / sound), house
                           (1 = house_1, 2 = house_2), t0 (field-PC), k50 (50-Hz index from t_min = {t_min}), seed, seed_state,
                           members, n_movers, complete (every member imu_ok and state_ok), window_start / window_end (t0 -+ 60 s),
                           cam_in / cam_out / mic / ch01 file (relative to F:/3rd_rat or {STORAGE}) + offset_s into that file.
  participants.csv.gz      one row per event x member: role (first / follower / non_mover / awake / moved_after_sound), lag_s,
                           pre_state, pre60_W/N/R, s10/s30/s60, class30, woke30, woke60, scenario (woke / not_woken), wake latency /
                           duration / kind (MA < 40 s, long), fu_* = composition +1..+10 min; imu_ok, state_ok; pointers: session,
                           imu_i (index into <session>.imu.npz), amp_sample, lfp_sample (= amp_sample/16 into lfp_file), emg_j
                           (bin of <session>.EMGFromLFP50Hz.npz, j = amp_sample/400), lfp_file; dcorr / dlog_rms / emg_burst.
  traces.npz               per participant row (same order): VeDBA (m/s^2) and the fast LFP-EMG corr / log_rms, -3..+3 s at 50 Hz.
  control_events/participants.csv.gz   random co-sleep seconds, the same outcome fields (role control).
  handling.csv.gz          battery rounds: pre/post sleep around each usable logged / inferred round gap + camera files.
Scenario 1 (disruption, the animal wakes) = participants with scenario == woke; scenario 2 (does not wake) = not_woken.
Sound candidates are unvalidated (mic levels, not listening). Video and mic offsets are from file-name times (mic clocks
drift up to ~210 ppm; see ephys/mic_band_levels.py).
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    write_json(out / "thresholds.json", {"t_min": str(t_min), "fs": FS, "theta_vedba_ms2": {k: float(v) for k, v in TH.items()},
                                         "tight_s": TIGHT_S, "null_shifts_s": list(NULL_SHIFTS_S)})

    # ---------------- figure: mean traces by role
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t_ax = np.arange(-TR, TR + 1) / FS
    roles = ("first", "follower_tight", "follower_loose", "non_mover")
    have_emg = bool(np.isfinite(tr_c.astype(np.float32)).any())
    nrow = 2 if have_emg else 1
    fig, axs = plt.subplots(nrow, 2, figsize=(12, 3.6 * nrow), squeeze=False)
    msk_base = (P.source == "movement").to_numpy() & comp.to_numpy()
    for ci, ps in enumerate(("NREM", "REM")):
        for role in roles:
            m_ = msk_base & (P.role_detail == role).to_numpy() & (P.pre_state == ps).to_numpy()
            if m_.sum() < 20:
                continue
            axs[0, ci].plot(t_ax, np.nanmean(tr_v[m_].astype(np.float32), 0), label=f"{role} (n={int(m_.sum())})")
            if have_emg:
                y = tr_c[m_].astype(np.float32)
                if np.isfinite(y).any():
                    axs[1, ci].plot(t_ax, np.nanmean(y, 0), label=f"{role} (n={int(np.isfinite(y[:, TR]).sum())})")
        axs[0, ci].set_title(f"pre-state {ps}: head VeDBA", fontsize=9)
        axs[0, ci].axvline(0, color="k", lw=0.4)
        axs[0, ci].legend(fontsize=7)
        if have_emg:
            axs[1, ci].set_title(f"pre-state {ps}: LFP-EMG corr (300-450 Hz, 50 Hz)", fontsize=9)
            axs[1, ci].axvline(0, color="k", lw=0.4)
            axs[1, ci].legend(fontsize=7)
            axs[1, ci].set_xlabel("time from the event (s; t0 = first mover's onset)")
    fig.suptitle(f"Phase 6: movement events among sleeping housemates, mean by role  {gc}", fontsize=9)
    save_fig(fig, fd / "ephys_spikes_sleep_events_traces_2026c.png")

    L = ["# Internal sleep schedule — Phase 6: sleep-perturbation event library + LFP-EMG (cohort 2026c)", "",
         f"Plan Amendment 10 (before results). Driver `ephys/sleep_schedule.py phase6` → `ephys/sleep_events.py` (commit {gc}); "
         f"library `{out}` (README.md there). LFP-EMG: {'`' + str(emg_root) + '` (' + str(n_sess_emg) + ' sessions)' if emg_root else 'not used'}. "
         "**Technical ledger.**", "", "## Definitions", "", "```", (__doc__ or "").strip(), "```", "",
         f"Co-sleep seconds (>= 2 members asleep, every member's IMU valid): house_1 {cos_sec.get(1, 0) / 3600:.1f} h, "
         f"house_2 {cos_sec.get(2, 0) / 3600:.1f} h. Events: {len(E)} ({int((E.source == 'movement').sum())} movement, "
         f"{int((E.source == 'sound').sum())} sound candidates); participants {len(P)}; handling rounds {len(HD)}.", "",
         "## Rates: complete movement events per co-sleep hour", "", md_table(T1.round(3)), "",
         "## Group events vs chance (seeds with >= 1 asleep housemate; chance = the same follower test at +-31 / +-47 s)", "",
         md_table(T1b.round(3)), "",
         "## Event level: of the asleep participants (>= 2 per event), none / some / all woke within 60 s", "", md_table(T2.round(3)), "",
         "## Participant level, by role and pre-state", "", md_table(T3.round(3)), "",
         "## Per animal: woke within 60 s, by role, vs random co-sleep seconds", "", md_table(T4.round(3)), ""]
    if len(T5):
        L += ["## LFP-EMG by role (movement events)", "", md_table(T5.round(3)), ""]
        if len(T5b):
            L += ["### Matched movement size (terciles of the peak head VeDBA over 0..0.5 s)", "", md_table(T5b.round(3)), ""]
        if len(T5c):
            L += ["### Timing of the mean traces (half-maximum and peak, s from t0; 20-ms grid)", "", md_table(T5c.round(3)), ""]
    L += ["![](../figures/ephys_spikes_sleep_events_traces_2026c.png)", "",
          "## Handling (battery rounds)", "", md_table(HD.drop(columns=[c for c in HD.columns if c.endswith("_file")]).round(2)) if len(HD) else "none", ""]
    flat = [ln for x in L for ln in (x if isinstance(x, list) else [x])]
    (rd / "ephys_spikes_sleep_events_2026c.md").write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_events_2026c.json", {"run_dir": str(out), "git_commit": gc, "emg_root": str(emg_root) if emg_root else None})
    print("written", rd / "ephys_spikes_sleep_events_2026c.md", flush=True)
