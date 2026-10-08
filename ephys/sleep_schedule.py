r"""Does sleep follow an internal schedule that survives interruptions? (plan: implementation_plan/2026-10-07-sleep-internal-schedule.md)

Phase 0 = definitions, tables and counts only; no outcome is computed (no REM hazard, no history effect, no payback).

Definitions (1-s FINAL states: 0 unknown, 1 WAKE, 3 NREM, 5 REM; times are field-PC local time):
  inclusion     the FINAL-score exclusions (sleep_cycles_v2) and everything from CUTOFF = 2026-09-11 19:40 (the five
                females; plan section 8).
  record        sessions joined across splits <= 60 s (sleep_cycles_v2.build_records); a longer gap ends a record.
  wake bout     a maximal WAKE run inside a record, with its duration d (s), the state before and after it.
  episode units (Watson et al. 2016, Neuron 90:839; plan section 3), for a microarousal limit m (primary 40 s):
    MA              a wake bout with d < m whose neighbours are both NREM;
    NREM packet     a maximal NREM run;
    NREM episode    a maximal run of NREM packets and MAs (no REM, no other wake);
    SLEEP           a maximal stretch of a record containing no wake bout > 120 s and no unknown epoch, trimmed to its
                    first and last sleep epoch, kept if >= 20 min;
    WAKE-SLEEP      a wake bout >= 7 min followed directly by a SLEEP;
    REM cycle       REM onset -> next REM onset inside one SLEEP.
  gap           the time between two consecutive records of an animal (> 60 s). Kind: 'morning' if it starts 05:00-11:00,
                'evening' 15:30-21:30, else 'other'. Usable for the gap tests if <= 180 min with >= 1 h recorded on
                both sides. Per gap (description only): the logger's battery swap inside it (BATTERY_LOG cell table,
                5-min resolution), whether the previous cell auto-stopped, minutes before / after the swap, and
                WISER movement: the share of gap minutes whose 1-min median position moved >= 14 in from the previous
                minute, and the share of gap seconds the default tracks flag m_handling. Movement never upgrades a gap
                to "wake": a gap is a handled interruption of unknown state.
                Cause (first match): 'probe_move' (a cohorts/2026c.yaml ephys.probe_moves time within the gap +- 15 min;
                handling + an electrode change, reported apart from the rounds) > 'round_logged' (a battery swap in
                the gap) > 'round_inferred' (morning / evening kind, >= 30 min; the cell table is partial before
                09-01 23:41) > 'no_handling_recorded'.
  windows       compensation windows (plan C1): A = 3 h, B = the next 1 h / 3 h, inside a record (completeness >= 80 %
                of recorded seconds in each), and across usable gaps (A = 3 h before, B = 1 h / 3 h after).

Phase 1 = curve 1 (memory curve over layers L0 clock -> L1 current state -> L2 accumulated since the last REM -> L3
distant bands), the clock comparison, cycles ahead, own vs shared history, refractoriness and the opportunity / timing
split; forward chaining over day-half blocks (definitions in the Phase-1 report).

Usage: python ephys/sleep_schedule.py phase0 [--states <states_1s_final>] [--review <review csv>]
       python ephys/sleep_schedule.py phase1
       python ephys/sleep_schedule.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "common"))
from sleep_cycles import bouts  # noqa: E402
from sleep_cycles_v2 import build_records  # noqa: E402

W, N, R = 1, 3, 5
CUTOFF = pd.Timestamp("2026-09-11 19:40")
MA_LIMITS = (40, 100, 20)          # primary first
SLEEP_END_WAKE_S = 120
SLEEP_MIN_S = 20 * 60
WAKE_SLEEP_MIN_WAKE_S = 7 * 60
OUT = Path("D:/Field2026_analysis_out/2026c")
STATES = Path("D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final")
REVIEW = ROOT / "results/2026c/ephys_spikes/reports/ephys_spikes_sleep_review_2026c.csv"


# ------------------------------------------------------------------ inclusion
def included_sessions(review: Path, states: Path) -> pd.DataFrame:
    from sleep_quant import MIN_SESSION_H, PADDOCK_END
    rv = pd.read_csv(review)
    rv["start"] = pd.to_datetime(rv.start_local)
    keep, ends = [], []
    for r in rv.itertuples():
        tags = r.tags if isinstance(r.tags, str) else ""
        keep.append((states / r.animal / f"{r.session}.states.npz").exists() and r.verdict != "noise"
                    and "SF12_contact_failing" not in tags and (r.duration_h or 0) >= MIN_SESSION_H and r.start < CUTOFF)
        e = PADDOCK_END
        for t in tags.split(";"):
            if t.startswith("valid_until "):
                e = min(e, pd.Timestamp(t[len("valid_until "):]))
        ends.append(min(e, CUTOFF))
    rv["end_cut"] = ends
    return rv[keep].copy()


# ------------------------------------------------------------------ episode units (pure; selftested)
def wake_bouts(state: np.ndarray) -> list[dict]:
    bl = bouts(state)
    out = []
    for i, (s, a, b) in enumerate(bl):
        if s == W:
            out.append({"a": a, "b": b, "d": b - a, "prev": bl[i - 1][0] if i else -1,
                        "next": bl[i + 1][0] if i + 1 < len(bl) else -1})
    return out


def episode_units(state: np.ndarray, m: float) -> dict:
    """Watson-2016 units for one record (see the module docstring). Returns lists of (a, b) intervals."""
    bl = bouts(state)
    ma = [(a, b) for i, (s, a, b) in enumerate(bl)
          if s == W and (b - a) < m and 0 < i < len(bl) - 1 and bl[i - 1][0] == N and bl[i + 1][0] == N]
    ma_set = {a for a, _ in ma}
    packets = [(a, b) for s, a, b in bl if s == N]
    nrem_ep, cur = [], None
    for s, a, b in bl:
        if s == N or (s == W and a in ma_set):
            cur = (cur[0], b) if cur else (a, b)
        else:
            if cur:
                nrem_ep.append(cur)
            cur = None
    if cur:
        nrem_ep.append(cur)
    # SLEEP: split at wake bouts > 120 s and at unknown epochs, trim to sleep, keep >= 20 min
    cut = np.zeros(len(state) + 1, bool)
    for s, a, b in bl:
        if (s == W and (b - a) > SLEEP_END_WAKE_S) or s == 0:
            cut[a:b] = True
    sleep_eps, a0 = [], None
    for i in range(len(state) + 1):
        if i < len(state) and not cut[i]:
            a0 = i if a0 is None else a0
        elif a0 is not None:
            seg = state[a0:i]
            idx = np.flatnonzero((seg == N) | (seg == R))
            if idx.size and (idx[-1] - idx[0] + 1) >= SLEEP_MIN_S:
                sleep_eps.append((a0 + int(idx[0]), a0 + int(idx[-1]) + 1))
            a0 = None
    starts = {a for a, _ in sleep_eps}
    wake_sleep = [(a, b) for s, a, b in bl if s == W and (b - a) >= WAKE_SLEEP_MIN_WAKE_S and b in starts]
    rem_cycles = []
    for sa, sb in sleep_eps:
        on = [a for s, a, b in bl if s == R and sa <= a < sb]
        rem_cycles += list(zip(on[:-1], on[1:]))
    return {"ma": ma, "packets": packets, "nrem_episodes": nrem_ep, "sleep": sleep_eps, "wake_sleep": wake_sleep,
            "rem_cycles": rem_cycles}


# ------------------------------------------------------------------ battery log
CELL_RE = re.compile(r"^\| (\d\d-\d\d \d\d:\d\d)( †)? \| (SF\d\d) \|.*\| (\d\d-\d\d \d\d:\d\d) \|[^|]*\|[^|]*\|[^|]*\| ([^|]*)\|\s*$")


def battery_cells(path: Path) -> pd.DataFrame:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = CELL_RE.match(line)
        if m:
            t0, dag, rat, t1, how = m.groups()
            rows.append({"rat": rat, "swap": pd.Timestamp(f"2026-{t0}"), "aggregated_row": bool(dag),
                         "last_seen": pd.Timestamp(f"2026-{t1}"), "how_ended": how.strip()})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ WISER during gaps
def wiser_gap_motion(an: str, t0: pd.Timestamp, t1: pd.Timestamp) -> dict:
    days = sorted({d.strftime("%Y%m%d") for d in pd.date_range(t0.normalize(), t1.normalize(), freq="D")})
    fs = [OUT / f"wiser_default_tracks/{an}/{d}.csv.gz" for d in days]
    fs = [f for f in fs if f.exists()]
    if not fs:
        return {"wiser_minutes": 0, "wiser_moving_share": np.nan, "wiser_handling_share": np.nan}
    tr = pd.concat([pd.read_csv(f, usecols=["t_ms", "x", "y", "m_handling"]) for f in fs])
    tr["t"] = pd.to_datetime(tr.t_ms, unit="ms") - pd.Timedelta(hours=4)
    tr = tr[(tr.t >= t0) & (tr.t < t1)]
    if tr.empty:
        return {"wiser_minutes": 0, "wiser_moving_share": np.nan, "wiser_handling_share": np.nan}
    mins = tr.set_index("t")[["x", "y"]].resample("1min").median().dropna()
    step = np.hypot(mins.x.diff(), mins.y.diff()).dropna()
    return {"wiser_minutes": len(mins), "wiser_moving_share": float((step >= 14).mean()) if len(step) else np.nan,
            "wiser_handling_share": float(tr.m_handling.astype(bool).mean())}


# ------------------------------------------------------------------ phase 0
def phase0(a) -> None:
    sys.path.insert(0, str(ROOT / "ephys"))
    from _common import git_commit, write_json
    from output_paths import report_dir, run_dir
    from sleep_quant import md_table, sun_times
    out = run_dir("sleep_schedule_phase0", "2026c")
    rd = report_dir("2026c", "ephys_spikes")
    rv = included_sessions(Path(a.review), Path(a.states))
    recs = build_records(rv, Path(a.states))

    def is_light(t: pd.Timestamp) -> bool:
        sr, ss = sun_times(t.date())
        return pd.Timestamp(sr) <= t < pd.Timestamp(ss)

    # records + wake table + episode units
    rec_rows, wk_rows, unit_rows = [], [], []
    for rc in recs:
        st, t0 = rc["state"], rc["start"]
        rec_rows.append({"record_id": rc["record_id"], "animal": rc["animal"], "block": rc["block"], "start": t0,
                         "end": rc["end"], "hours": len(st) / 3600, "n_sessions": len(rc["sessions"]),
                         "unknown_s": int((st == 0).sum())})
        for w in wake_bouts(st):
            t = t0 + pd.Timedelta(seconds=w["a"])
            wk_rows.append({"animal": rc["animal"], "record_id": rc["record_id"], "t": t, "d_s": w["d"],
                            "prev": w["prev"], "next": w["next"], "light": is_light(t)})
        for m in MA_LIMITS:
            u = episode_units(st, m)
            for kind, ivs in u.items():
                for x0, x1 in ivs:
                    t = t0 + pd.Timedelta(seconds=x0)
                    unit_rows.append({"m": m, "unit": kind, "animal": rc["animal"], "record_id": rc["record_id"],
                                      "t": t, "dur_s": x1 - x0, "light": is_light(t)})
    REC, WK, UN = pd.DataFrame(rec_rows), pd.DataFrame(wk_rows), pd.DataFrame(unit_rows)
    REC.to_csv(out / "records.csv", index=False)
    WK.to_csv(out / "wake_bouts.csv.gz", index=False)
    UN.to_csv(out / "episode_units.csv.gz", index=False)

    # gaps
    cells = battery_cells(ROOT.parent / "Field_2026_Social_Recording" / "BATTERY_LOG_cohort3.md") if a.battery_log is None \
        else battery_cells(Path(a.battery_log))
    import yaml
    probe_moves = yaml.safe_load((ROOT / "cohorts" / "2026c.yaml").read_text(encoding="utf-8"))["ephys"].get("probe_moves", [])
    gap_rows = []
    for an, g in REC.sort_values("start").groupby("animal"):
        g = g.reset_index(drop=True)
        for i in range(len(g) - 1):
            p, n = g.iloc[i], g.iloc[i + 1]
            gs, ge = pd.Timestamp(p.end), pd.Timestamp(n.start)
            h = gs.hour + gs.minute / 60
            kind = "morning" if 5 <= h < 11 else ("evening" if 15.5 <= h < 21.5 else "other")
            c = cells[(cells.rat == an) & (cells.swap >= gs - pd.Timedelta(minutes=10)) & (cells.swap <= ge + pd.Timedelta(minutes=10))]
            prev_cell = cells[(cells.rat == an) & (cells.swap < gs)].sort_values("swap").tail(1)
            row = {"animal": an, "gap_start": gs, "gap_end": ge, "gap_min": (ge - gs).total_seconds() / 60, "kind": kind,
                   "pre_h": p.hours, "post_h": n.hours, "usable": ((ge - gs).total_seconds() <= 180 * 60) and p.hours >= 1 and n.hours >= 1,
                   "swap": c.swap.min() if len(c) else pd.NaT, "n_swaps_in_gap": len(c),
                   "prev_cell_end": prev_cell.how_ended.iloc[0] if len(prev_cell) else ""}
            if len(c):
                row["min_before_swap"] = (c.swap.min() - gs).total_seconds() / 60
                row["min_after_swap"] = (ge - c.swap.min()).total_seconds() / 60
            pm = [x for x in probe_moves if x["animal"] == an
                  and gs - pd.Timedelta(minutes=15) <= pd.Timestamp(x["time"]) <= ge + pd.Timedelta(minutes=15)]
            row["cause"] = ("probe_move" if pm else "round_logged" if len(c) else
                            "round_inferred" if kind in ("morning", "evening") and row["gap_min"] >= 30 else "no_handling_recorded")
            row.update(wiser_gap_motion(an, gs, ge))
            gap_rows.append(row)
    GP = pd.DataFrame(gap_rows)
    GP.to_csv(out / "gaps.csv", index=False)

    # compensation windows (counts only)
    win = []
    for rc in recs:
        st = rc["state"]
        known = np.r_[0, np.cumsum(st != 0)]
        for A, B in ((3, 1), (3, 3)):
            nA, nB = A * 3600, B * 3600
            for s in range(0, len(st) - nA - nB + 1, 3600):
                okA = (known[s + nA] - known[s]) >= 0.8 * nA
                okB = (known[s + nA + nB] - known[s + nA]) >= 0.8 * nB
                win.append({"setting": "within record", "A_h": A, "B_h": B, "ok": bool(okA and okB), "animal": rc["animal"]})
    ug = GP[GP.usable]
    for A, B in ((3, 1), (3, 3)):
        for r in ug.itertuples():
            win.append({"setting": "across gap", "A_h": A, "B_h": B, "ok": bool(r.pre_h >= A and r.post_h >= B), "animal": r.animal})
    WN = pd.DataFrame(win)

    # ---------------- summaries
    WK["d_class"] = pd.cut(WK.d_s, [0, 40, 120, 420, np.inf], right=False, labels=["< 40 s (MA range)", "40-120 s", "2-7 min", ">= 7 min"])
    wk_sum = WK.groupby(["d_class", "light"], observed=True).size().unstack(fill_value=0).rename(columns={True: "light", False: "dark"})
    wk_next = WK[WK.next == N].groupby("d_class", observed=True).size().rename("followed by NREM in the record")
    wk_tab = wk_sum.join(wk_next).reset_index()
    un_sum = UN.groupby(["m", "unit"]).agg(n=("dur_s", "size"), median_min=("dur_s", lambda x: np.median(x) / 60)).reset_index()
    un_tab = un_sum.pivot_table(index="unit", columns="m", values="n").reset_index()
    un_med = un_sum[un_sum.m == MA_LIMITS[0]][["unit", "median_min"]]
    gp_tab = GP.groupby(["cause", "kind", "usable"]).agg(n=("gap_min", "size"), median_gap_min=("gap_min", "median"),
                                              with_swap=("n_swaps_in_gap", lambda x: int((x > 0).sum())),
                                              prev_autostop=("prev_cell_end", lambda x: int(x.str.contains("yes|auto", case=False).sum())),
                                              median_wiser_moving=("wiser_moving_share", "median"),
                                              median_wiser_handling=("wiser_handling_share", "median")).reset_index()
    wn_tab = WN.groupby(["setting", "A_h", "B_h"]).ok.sum().reset_index().rename(columns={"ok": "windows"})
    per_an = REC.groupby("animal").agg(records=("record_id", "size"), hours=("hours", "sum")).reset_index()
    per_an = per_an.merge(WK[(WK.d_s >= 600) & WK.prev.isin([N, R]) & (WK.next == N)].groupby("animal").size().rename("wakes_ge_10min").reset_index(), how="left")
    per_an = per_an.merge(GP[GP.usable].groupby("animal").size().rename("usable_gaps").reset_index(), how="left")
    per_an["hours"] = per_an.hours.round(1)
    per_an = per_an.fillna(0).astype({"wakes_ge_10min": int, "usable_gaps": int})
    un_tab = un_tab.set_index("unit").astype(int).reset_index()

    rpt = rd / "ephys_spikes_sleep_schedule_phase0_2026c.md"
    L = ["# Internal sleep schedule — Phase 0: definitions and counts (cohort 2026c)", "",
         f"Plan: [implementation_plan/2026-10-07-sleep-internal-schedule.md](../../../../implementation_plan/2026-10-07-sleep-internal-schedule.md). "
         f"Driver: `ephys/sleep_schedule.py phase0` (commit {git_commit()}). Bulk: `{out}`.", "",
         "**Phase 0 computes no outcome**: no REM hazard, no history effect, no payback. Only the units and how many there are.", "",
         "## Inclusion", "",
         f"- The FINAL sleep scores and their exclusions, cut at {CUTOFF:%Y-%m-%d %H:%M} (the females).",
         f"- {len(rv)} sessions → {len(REC)} records, {REC.hours.sum():.0f} h; unknown seconds inside records (file splits ≤ 60 s): "
         f"{int(REC.unknown_s.sum())}.", "", md_table(per_an), "",
         "## Wake bouts inside records (durations as observed; curve 2 uses d continuously)", "",
         "Reference marks from Watson et al. 2016: < 40 s = microarousal range; > 120 s ends a SLEEP; ≥ 7 min = the WAKE of a "
         "WAKE–SLEEP cycle.", "", md_table(wk_tab), "",
         "## Episode units (Watson et al. 2016) for the microarousal limit m = 40 s (primary), 100 s (our pipeline's code), "
         "20 s (Park)", "", "Counts:", "", md_table(un_tab), "", f"Median durations at m = {MA_LIMITS[0]} s (min):", "",
         md_table(un_med.round(2)), "",
         "## Gaps between records (battery rounds and others)", "",
         "A gap is a handled interruption of unknown state. WISER columns are descriptive only (share of gap minutes with ≥ "
         "14 in movement of the 1-min median; share of gap seconds flagged `m_handling`). `prev_autostop` = the cell before "
         "the gap auto-stopped (unobserved, undisturbed time before the round).", "", md_table(gp_tab.round(2)), "",
         "## Compensation windows available (A = 3 h before, B = the next 1 h / 3 h; ≥ 80 % recorded)", "",
         md_table(wn_tab), "",
         "## Next", "", "Phase 1 (curve 1: memory curve, clock, cycles ahead, own vs shared; refractoriness; opportunity / "
         "timing split) after the user has seen these counts."]
    flat = [ln for x in L for ln in (x if isinstance(x, list) else [x])]       # md_table returns a list of lines
    rpt.write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_schedule_phase0_2026c.json",
               {"run_dir": str(out), "git_commit": git_commit(), "states": str(a.states), "review": str(a.review),
                "cutoff": str(CUTOFF), "ma_limits": MA_LIMITS})
    print("written", rpt)


# ================================================================== Phase 1 (curve 1 + C2 + C4)
DT = 10
BANDS_MIN = ((10, 30), (30, 90), (90, 270), (270, 720))
JMAX = 720                                     # 2 h of NREM: horizon of the opportunity / timing integration
GAP_MIN_S = 600                                # an unknown run this long is a gap (file splits <= 60 s are not)
RELEASE = pd.Timestamp("2026-08-30 19:00:00")


def record_steps_s(state: np.ndarray) -> pd.DataFrame:
    """Person-period rows (one per 10 s) for every NREM bout of a record. History is taken at the bout start a and is
    fixed during the bout (only `elapsed` and the clock change). Definitions: plan section 3 / Phase-1 report."""
    n = len(state)
    cw, cn, cr = (np.r_[0, np.cumsum(state == s)] for s in (W, N, R))
    ck = np.r_[0, np.cumsum(state != 0)]
    bl = bouts(state)
    rows = []
    last_rem = None
    last_gap_s, rem_since_gap = 0, True              # post-gap bookkeeping (Phase 2 B2): gap = unknown run >= GAP_MIN_S
    for i, (s, a, b) in enumerate(bl):
        if s == R:
            last_rem = (a, b) if (a > 0 and state[a - 1] != 0) else None
            rem_since_gap = True
            continue
        if s == 0:
            if b - a >= GAP_MIN_S:
                last_gap_s, rem_since_gap = b - a, False
            continue
        if s != N:
            continue
        J = int(np.ceil((b - a) / DT))
        y = np.zeros(J, np.int8)
        if b < n and state[b] in (R, W):
            y[-1] = 1 if state[b] == R else 2
        ps, pa, pb = bl[i - 1] if i else (0, a, a)
        f = {"bout_start": a, "bout_len": b - a,
             "d_prev": (pb - pa) if ps == W else 0, "prev_rem": int(ps == R), "prev_unk": int(ps == 0 or i == 0),
             "u_prev": (pb - pa) if (ps == 0 and i) else 0,
             "pg_pending": int(not rem_since_gap), "pg_gap_s": last_gap_s if not rem_since_gap else 0}
        if last_rem is not None:
            ra, rb = last_rem
            f.update(has_anchor=1, rem_pre=rb - ra, n_since=int(cn[a] - cn[rb]), w_since=int(cw[a] - cw[rb]), t_since=a - rb)
        else:
            f.update(has_anchor=0, rem_pre=1, n_since=0, w_since=0, t_since=0)
        lo10 = max(0, a - 600)
        k10 = ck[a] - ck[lo10]
        f["fW10"] = (cw[a] - cw[lo10]) / k10 if k10 else 0.0
        for lo, hi in BANDS_MIN:                                   # wall-clock bands
            x0, x1 = max(0, a - 60 * hi), max(0, a - 60 * lo)
            k = ck[x1] - ck[x0]
            f[f"fR_{hi}"] = (cr[x1] - cr[x0]) / k if k else 0.0
            f[f"fW_{hi}"] = (cw[x1] - cw[x0]) / k if k else 0.0
            f[f"c_{hi}"] = k / (60 * (hi - lo))
            # NREM-time bands: the span holding the NREM seconds (cn[a] - 60 hi, cn[a] - 60 lo]
            v0, v1 = cn[a] - 60 * hi, cn[a] - 60 * lo
            j1 = int(np.searchsorted(cn, max(v1, 0), side="left")) if v1 > 0 else 0
            j0 = int(np.searchsorted(cn, max(v0, 0), side="left")) if v0 > 0 else 0
            nn = cn[j1] - cn[j0]
            f[f"nR_{hi}"] = (cr[j1] - cr[j0]) / nn if nn else 0.0
            f[f"nW_{hi}"] = (cw[j1] - cw[j0]) / nn if nn else 0.0
            f[f"nc_{hi}"] = nn / (60 * (hi - lo))
        rows.append(pd.DataFrame({"t_off": a + DT * np.arange(J), "elapsed": DT * np.arange(J), "y": y, **f}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def add_time(df: pd.DataFrame, start: pd.Timestamp) -> pd.DataFrame:
    t = start + pd.to_timedelta(df.t_off.astype(float), unit="s")
    df["t"] = t
    df["hour"] = t.dt.hour + t.dt.minute / 60 + t.dt.second / 3600
    df["T_day"] = (t - RELEASE).dt.total_seconds() / 86400
    return df


CONT = ["l_dprev", "prev_rem", "prev_unk", "fW10", "l_wsince", "l_rem_pre", "has_anchor"]


def feats(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    for k in (1, 2):
        f[f"sin{k}"], f[f"cos{k}"] = np.sin(2 * np.pi * k * df.hour / 24), np.cos(2 * np.pi * k * df.hour / 24)
    f["T_day"] = df.T_day.astype(float)
    f["l_elapsed"] = np.log(df.elapsed + 5.0)
    f["l_dprev"] = np.log1p(df.d_prev.astype(float))
    f["prev_rem"], f["prev_unk"], f["fW10"] = df.prev_rem.astype(float), df.prev_unk.astype(float), df.fW10.astype(float)
    f["l_nsince"] = np.log1p(df.n_since.astype(float))
    f["l_tsince"] = np.log1p(df.t_since.astype(float))
    f["l_wsince"] = np.log1p(df.w_since.astype(float))
    f["l_rem_pre"] = np.log(df.rem_pre.astype(float)) * df.has_anchor
    f["has_anchor"] = df.has_anchor.astype(float)
    for _, hi in BANDS_MIN:
        for p in ("fR", "fW", "c", "nR", "nW", "nc"):
            f[f"{p}_{hi}"] = df[f"{p}_{hi}"].astype(float)
    for c in ("S_rem3h", "S_c3h"):
        if c in df:
            f[c] = df[c].astype(float)
    return f


# model specs: L1 (current state), L2 ('full' = NREM-time spline + wake since + REM_pre + anchor; 'nrem' / 'wall' =
# one since-REM clock + REM_pre + anchor), bands (how many wall / NREM bands), S (other animals), inter (refractory x REM_pre)
SPECS = {
    "M0": dict(L1=False, L2=None, nb=0),
    "M1": dict(L1=True, L2=None, nb=0),
    "M2": dict(L1=True, L2="full", nb=0),
    "M3_30": dict(L1=True, L2="full", nb=1),
    "M3_90": dict(L1=True, L2="full", nb=2),
    "M3_270": dict(L1=True, L2="full", nb=3),
    "M3_720": dict(L1=True, L2="full", nb=4),
    "Cl_nrem": dict(L1=True, L2="nrem", nb=0),
    "Cl_wall": dict(L1=True, L2="wall", nb=0),
    "M3_720n": dict(L1=True, L2="full", nb=4, band_clock="nrem"),
    "M1S": dict(L1=True, L2=None, nb=0, S=True),
    "M3_720S": dict(L1=True, L2="full", nb=4, S=True),
    "M2i": dict(L1=True, L2="full", nb=0, inter=True),
}


def design_s(f: pd.DataFrame, animals: pd.Series, spec: dict, st: dict | None, levels: list[str]) -> tuple[np.ndarray, dict]:
    from sklearn.preprocessing import SplineTransformer
    fit = st is None
    st = st or {}
    if fit:
        for c in ("l_elapsed", "l_nsince", "l_tsince"):
            st[f"spl_{c}"] = SplineTransformer(n_knots=4, degree=3, include_bias=False).fit(f[[c]])
        zc = [c for c in f.columns if c not in ("sin1", "cos1", "sin2", "cos2", "l_elapsed", "l_nsince", "l_tsince")]
        st["mu"], st["sd"] = f[zc].mean(), f[zc].std().replace(0, 1)
    z = (f[st["mu"].index] - st["mu"]) / st["sd"]
    parts = [st["spl_l_elapsed"].transform(f[["l_elapsed"]]), f[["sin1", "cos1", "sin2", "cos2"]].to_numpy(), z[["T_day"]].to_numpy()]
    if spec.get("L1"):
        parts.append(z[["l_dprev", "prev_rem", "prev_unk", "fW10"]].to_numpy())
    L2 = spec.get("L2")
    if L2 in ("full", "nrem"):
        parts.append(st["spl_l_nsince"].transform(f[["l_nsince"]]))
    if L2 == "wall":
        parts.append(st["spl_l_tsince"].transform(f[["l_tsince"]]))
    if L2 == "full":
        parts.append(z[["l_wsince"]].to_numpy())
    if L2:
        parts.append(z[["l_rem_pre", "has_anchor"]].to_numpy())
    pre = "n" if spec.get("band_clock") == "nrem" else ""
    for _, hi in BANDS_MIN[:spec.get("nb", 0)]:
        parts.append(z[[f"{pre}R_{hi}" if pre else f"fR_{hi}", f"{pre}W_{hi}" if pre else f"fW_{hi}",
                        f"{pre}c_{hi}" if pre else f"c_{hi}"]].to_numpy())
    if spec.get("S"):
        parts.append(z[["S_rem3h", "S_c3h"]].to_numpy())
    if spec.get("inter"):
        B = st["spl_l_nsince"].transform(f[["l_nsince"]])
        parts.append(B * z[["l_rem_pre"]].to_numpy())
    parts.append(pd.get_dummies(pd.Categorical(animals, categories=levels), dtype=float).to_numpy()[:, 1:])
    return np.column_stack(parts), st


def fit_s(train: pd.DataFrame, spec: dict, levels: list[str]):
    from sklearn.linear_model import LogisticRegression
    X, st = design_s(feats(train), train.animal, spec, None, levels)
    m = LogisticRegression(C=1e4, max_iter=3000).fit(X, train.y.to_numpy())
    return m, st


def predict_s(m, st, df: pd.DataFrame, spec: dict, levels: list[str]) -> np.ndarray:
    X, _ = design_s(feats(df), df.animal, spec, st, levels)
    p = np.full((len(df), 3), 1e-12)
    p[:, m.classes_] = m.predict_proba(X)
    return p / p.sum(1, keepdims=True)


def split_scores(p_steps: np.ndarray, j_end: int, typ: int) -> dict:
    """Opportunity / timing split for ONE bout from its per-step class probabilities over the horizon (rows j = 0..),
    observed end at step j_end with type typ (1 REM, 2 Wake). Larson-Dinse: log S(j*-1) h_typ(j*) = log P(typ) + log f(j*|typ)."""
    hR, hW = p_steps[:, 1], p_steps[:, 2]
    S = np.r_[1.0, np.cumprod(1 - hR - hW)[:-1]]
    incR, incW = S * hR, S * hW
    PR, PW = incR.sum(), incW.sum()
    inc = incR if typ == 1 else incW
    P = PR if typ == 1 else PW
    tot = np.log(max(inc[j_end], 1e-300))
    cdf = np.cumsum(incR) / PR if PR > 0 else np.zeros_like(incR)
    q25, q75 = np.searchsorted(cdf, 0.25), np.searchsorted(cdf, 0.75)
    return {"log_total": tot, "log_type": np.log(max(P, 1e-300)), "log_timing": tot - np.log(max(P, 1e-300)),
            "pi_rem": PR, "residual": float(1 - PR - PW), "iqr_rem_s": float(DT * (q75 - q25))}


def phase1(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import statsmodels.api as sm
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_cycles import boot_ci, loglosses
    from sleep_quant import md_table, save_fig
    out = run_dir("sleep_schedule_phase1" + ("_smoke" if a.smoke else ""), "2026c")
    rd, fd = report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes")
    if a.smoke:                                   # synthetic integration test: never touch the real report paths
        rd = fd = out
    rv = included_sessions(Path(a.review), Path(a.states))
    recs = build_records(rv, Path(a.states))
    gc = git_commit()

    # ---------- steps
    parts = []
    for rc in recs:
        df = record_steps_s(rc["state"])
        if df.empty:
            continue
        df = add_time(df, rc["start"])
        df["animal"], df["block"], df["record_id"] = rc["animal"], rc["block"], rc["record_id"]
        df["t_start"] = rc["start"] + pd.to_timedelta(df.bout_start.astype(float), unit="s")
        parts.append(df)
    steps = pd.concat(parts, ignore_index=True)
    # shared component: the other animals' REM share of recorded time in the 3 h before the bout start
    t_min, t_max = min(rc["start"] for rc in recs), max(rc["end"] for rc in recs)
    span = int((t_max - t_min).total_seconds()) + 2
    cum = {}
    for an in sorted({rc["animal"] for rc in recs}):
        arr = np.zeros(span, np.int8)
        for rc in recs:
            if rc["animal"] == an:
                o = int((rc["start"] - t_min).total_seconds())
                arr[o:o + len(rc["state"])] = rc["state"]
        cum[an] = (np.r_[0, np.cumsum(arr == R)], np.r_[0, np.cumsum(arr != 0)])
    i1 = ((steps.t_start - t_min).dt.total_seconds()).astype(int).to_numpy()
    i0 = np.maximum(0, i1 - 3 * 3600)
    S_rem, S_c = np.zeros(len(steps)), np.zeros(len(steps))
    for an in cum:
        oth = steps.animal.to_numpy() != an
        cr_, ck_ = cum[an]
        k = ck_[i1] - ck_[i0]
        S_rem += np.where(oth, np.where(k > 0, (cr_[i1] - cr_[i0]) / np.maximum(k, 1), 0.0), 0.0)
        S_c += np.where(oth, k / (3 * 3600), 0.0)
    n_oth = len(cum) - 1
    steps["S_rem3h"], steps["S_c3h"] = S_rem / n_oth, S_c / n_oth
    steps.to_csv(out / "steps.csv.gz", index=False)
    levels = sorted(steps.animal.unique())
    blocks = sorted(steps.block.unique())
    print(f"steps {len(steps)}, REM events {(steps.y == 1).sum()}, wake events {(steps.y == 2).sum()}, blocks {len(blocks)}", flush=True)

    # ---------- forward chaining (primary) over day-half blocks
    first = 6
    comps = [("M0", "M1"), ("M1", "M2"), ("M2", "M3_30"), ("M3_30", "M3_90"), ("M3_90", "M3_270"), ("M3_270", "M3_720"),
             ("M1", "Cl_nrem"), ("M1", "Cl_wall"), ("Cl_nrem", "Cl_wall"), ("M2", "M3_720"), ("M3_720", "M3_720n"),
             ("M1S", "M3_720S"), ("M1", "M3_720"), ("M3_720", "M3_720S"), ("M2", "M2i")]
    fold_rows, an_rows, split_rows = [], [], []
    for k in range(first, len(blocks)):
        tr = steps[steps.block.isin(blocks[:k])]
        te = steps[(steps.block == blocks[k]) & steps.animal.isin(tr.animal.unique())]
        if (te.y == 1).sum() == 0:
            continue
        lv = sorted(tr.animal.unique())
        r = {"block": blocks[k], "n": len(te), "n_rem": int((te.y == 1).sum()), "n_wake": int((te.y == 2).sum())}
        models, LL = {}, {}
        for name, spec in SPECS.items():
            m, st = fit_s(tr, spec, lv)
            models[name] = (m, st)
            LL[name] = loglosses(predict_s(m, st, te, spec, lv), te.y.to_numpy())["ll"]
            r[f"ll_{name}"] = LL[name].mean()
        fold_rows.append(r)
        for an, g in te.groupby("animal"):
            pos = te.index.get_indexer(g.index)
            an_rows.append({"block": blocks[k], "animal": an, "n": len(g), **{f"ll_{nm}": LL[nm][pos].mean() for nm in SPECS}})
        # opportunity / timing split on bouts with an observed end
        ends = te[te.y > 0]
        bouts_te = ends[["record_id", "bout_start"]].drop_duplicates()
        first_rows = te.drop_duplicates(["record_id", "bout_start"]).set_index(["record_id", "bout_start"])
        ext = []
        for rid, bs in bouts_te.itertuples(index=False):
            row = first_rows.loc[(rid, bs)]
            g = pd.DataFrame([row] * JMAX)
            g["elapsed"] = DT * np.arange(JMAX)
            g["t"] = row.t_start + pd.to_timedelta(g.elapsed, unit="s")
            g["hour"] = g.t.dt.hour + g.t.dt.minute / 60 + g.t.dt.second / 3600
            g["T_day"] = (g.t - RELEASE).dt.total_seconds() / 86400
            g["rid"], g["bs"] = rid, bs
            ext.append(g)
        if ext:
            E = pd.concat(ext, ignore_index=True)
            E["animal"] = E["animal"].astype(str)
            ends_k = ends.set_index(["record_id", "bout_start"])
            for name in ("M0", "M1", "M2", "M3_720", "M3_720S"):
                m, st = models[name]
                P = predict_s(m, st, E, SPECS[name], lv).reshape(len(bouts_te), JMAX, 3)
                for b_i, (rid, bs) in enumerate(bouts_te.itertuples(index=False)):
                    e = ends_k.loc[(rid, bs)]
                    j_end = int(e.elapsed // DT)
                    if j_end >= JMAX:
                        continue
                    sc = split_scores(P[b_i], j_end, int(e.y))
                    split_rows.append({"block": blocks[k], "model": name, "animal": e.animal, "rid": rid, "bs": bs,
                                       "type": int(e.y), **sc})
        print(f"fold {blocks[k]}: n {len(te)}, M0 {r['ll_M0']:.4f}, M2 {r['ll_M2']:.4f}, M3_720 {r['ll_M3_720']:.4f}", flush=True)
    F, A_, SP = pd.DataFrame(fold_rows), pd.DataFrame(an_rows), pd.DataFrame(split_rows)
    F.to_csv(out / "folds.csv", index=False)
    A_.to_csv(out / "folds_by_animal.csv", index=False)
    SP.to_csv(out / "split_by_bout.csv.gz", index=False)

    def compare(lo_m: str, hi_m: str) -> dict:
        F["d"] = F[f"ll_{hi_m}"] - F[f"ll_{lo_m}"]
        est, lo, hi = boot_ci(F, "d")
        base = float(np.sum(F[f"ll_{lo_m}"] * F.n) / F.n.sum())
        pa = A_.assign(d=A_[f"ll_{hi_m}"] - A_[f"ll_{lo_m}"]).groupby("animal").apply(lambda g: np.sum(g.d * g.n) / g.n.sum(), include_groups=False)
        holds = (hi < 0) and int((pa < 0).sum()) >= 5
        return {"comparison": f"{hi_m} vs {lo_m}", "delta_pct": 100 * est / base, "ci_lo_pct": 100 * lo / base,
                "ci_hi_pct": 100 * hi / base, "folds_better": int((F.d < 0).sum()), "folds": len(F),
                "animals_better": int((pa < 0).sum()), "animals": len(pa), "holds": holds}
    C = pd.DataFrame([compare(*c) for c in comps])
    C.to_csv(rd / "ephys_spikes_sleep_schedule_phase1_comparisons_2026c.csv", index=False)
    print(C.round(3).to_string(index=False), flush=True)

    # split summary: per comparison, mean per-bout change of log P(type), log f(t|type), total (nats per bout; + = better)
    srow = []
    for lo_m, hi_m in (("M0", "M1"), ("M1", "M2"), ("M2", "M3_720"), ("M3_720", "M3_720S")):
        A2 = SP[SP.model == lo_m].set_index(["block", "rid", "bs"])
        B2 = SP[SP.model == hi_m].set_index(["block", "rid", "bs"])
        j = A2.join(B2, lsuffix="_a", rsuffix="_b", how="inner")
        for typ, lab in ((None, "all ends"), (1, "ends in REM"), (2, "ends in Wake")):
            jj = j if typ is None else j[j.type_a == typ]
            srow.append({"comparison": f"{hi_m} vs {lo_m}", "bouts": lab, "n": len(jj),
                         "gain_total": float((jj.log_total_b - jj.log_total_a).mean()),
                         "gain_opportunity": float((jj.log_type_b - jj.log_type_a).mean()),
                         "gain_timing": float((jj.log_timing_b - jj.log_timing_a).mean()),
                         "median_iqr_rem_s_a": float(jj.iqr_rem_s_a.median()), "median_iqr_rem_s_b": float(jj.iqr_rem_s_b.median()),
                         "mean_residual_b": float(jj.residual_b.mean())})
    SPS = pd.DataFrame(srow)
    SPS.to_csv(rd / "ephys_spikes_sleep_schedule_phase1_split_2026c.csv", index=False)

    # ---------- A3 cycles ahead (Watson units, m = 40 s, cycles inside one SLEEP)
    cyc = []
    for rc in recs:
        st_ = rc["state"]
        u = episode_units(st_, MA_LIMITS[0])
        ma_set = {(x0, x1) for x0, x1 in u["ma"]}
        bl = bouts(st_)
        for sa, sb in u["sleep"]:
            rem = [(x0, x1) for s, x0, x1 in bl if s == R and sa <= x0 < sb]
            for i in range(len(rem) - 1):
                (r0a, r0b), (r1a, _) = rem[i], rem[i + 1]
                seg_n = sum(min(x1, r1a) - max(x0, r0b) for s, x0, x1 in bl
                            if (s == N or (s == W and (x0, x1) in ma_set)) and x1 > r0b and x0 < r1a)
                tt = rc["start"] + pd.Timedelta(seconds=r0b)
                cyc.append({"animal": rc["animal"], "block": rc["block"], "sleep": (rc["record_id"], sa), "i": i,
                            "rem_s": r0b - r0a, "n_s": seg_n, "hour": tt.hour + tt.minute / 60})
    CY = pd.DataFrame(cyc)
    a3 = []
    for kk in range(1, 6):
        rows = []
        for key, g in CY.groupby("sleep"):
            g = g.sort_values("i").reset_index(drop=True)
            for i in range(len(g) - kk + 1):
                rr = {"animal": g.animal[i], "block": g.block[i], "hour": g.hour[i], "l_rem0": np.log(g.rem_s[i]),
                      "y": np.log(max(g.n_s[i + kk - 1], 1))}
                for j in range(1, kk):
                    rr[f"l_rem{j}"] = np.log(g.rem_s[i + j])
                    rr[f"l_n{j}"] = np.log(max(g.n_s[i + j - 1], 1))
                rows.append(rr)
        D = pd.DataFrame(rows)
        if len(D) < 50:
            continue
        X = D[["l_rem0"] + [c for c in D.columns if c.startswith(("l_rem", "l_n")) and c != "l_rem0"]].copy()
        for kh in (1, 2):
            X[f"sin{kh}"], X[f"cos{kh}"] = np.sin(2 * np.pi * kh * D.hour / 24), np.cos(2 * np.pi * kh * D.hour / 24)
        X = pd.concat([X, pd.get_dummies(D.animal, drop_first=True, dtype=float)], axis=1)
        X = sm.add_constant(X)
        fit = sm.OLS(D.y, X).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(D.block)[0]})
        signs = []
        own = [c for c in X.columns if c == "const" or c.startswith(("l_rem", "l_n", "sin", "cos"))]   # no animal dummies
        for an, g in D.groupby("animal"):
            if len(g) >= 30:
                signs.append(np.sign(sm.OLS(g.y, X.loc[g.index, own]).fit().params["l_rem0"]))
        a3.append({"k_ahead": kk, "n_cycles": len(D), "beta_l_rem0": fit.params["l_rem0"], "se": fit.bse["l_rem0"],
                   "p": fit.pvalues["l_rem0"], "animals_positive": int(np.sum(np.array(signs) > 0)), "animals": len(signs)})
    A3 = pd.DataFrame(a3)
    A3.to_csv(rd / "ephys_spikes_sleep_schedule_phase1_cycles_ahead_2026c.csv", index=False)

    # ---------- C2 refractoriness curve (full fit of M2i; description)
    m_i, st_i = fit_s(steps, SPECS["M2i"], levels)
    med = steps.median(numeric_only=True)
    grid = np.unique(np.r_[0, np.geomspace(10, np.quantile(steps.n_since[steps.has_anchor == 1], 0.95), 60)])
    qs = np.quantile(steps.rem_pre[steps.has_anchor == 1], [0.25, 0.5, 0.75])
    fig, ax = plt.subplots(figsize=(7, 4.5))
    curve_rows = []
    for q, lab in zip(qs, ("REM_pre 25 %", "REM_pre 50 %", "REM_pre 75 %")):
        hz = np.zeros(len(grid))
        for an in levels:
            g = pd.DataFrame({c: med[c] for c in med.index}, index=range(len(grid)))
            g["n_since"], g["rem_pre"], g["has_anchor"], g["animal"] = grid, q, 1, an
            g["t_since"] = grid + med["w_since"]
            hz += predict_s(m_i, st_i, g, SPECS["M2i"], levels)[:, 1] / len(levels)
        ax.plot(grid / 60, hz, label=f"{lab} = {q:.0f} s")
        curve_rows += [{"rem_pre_s": q, "n_since_at_bout_start_min": x / 60, "rem_hazard_per_10s": h} for x, h in zip(grid, hz)]
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("NREM since the last REM at the bout START (min); within-bout time held at its median")
    ax.set_ylabel("P(REM in the next 10 s) (model)")
    ax.set_title(f"Bout-start accumulated NREM vs REM hazard (M2i, full fit; description, not a refractory length)  {gc}", fontsize=8)
    ax.legend(fontsize=8)
    save_fig(fig, fd / "ephys_spikes_sleep_schedule_phase1_refractory_2026c.png")
    pd.DataFrame(curve_rows).to_csv(out / "refractory_curve.csv", index=False)

    # ---------- figures: memory curve + clock
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.5))
    cum = [compare("M2", m) for m in ("M3_30", "M3_90", "M3_270", "M3_720")]
    x = [30, 90, 270, 720]
    axs[0].errorbar(x, [c["delta_pct"] for c in cum], yerr=[[c["delta_pct"] - c["ci_lo_pct"] for c in cum], [c["ci_hi_pct"] - c["delta_pct"] for c in cum]],
                    marker="o", capsize=3)
    axs[0].axhline(0, color="k", lw=0.8)
    axs[0].set_xscale("log")
    axs[0].set_xlabel("history bands up to (min before the NREM bout)")
    axs[0].set_ylabel("held-out log-loss change vs M2 (%)")
    axs[0].set_title("Memory curve beyond the accumulated layer (forward chaining)", fontsize=9)
    lab = ["M1 vs M0", "M2 vs M1", "M3_720 vs M2", "Cl_nrem vs M1", "Cl_wall vs M1", "M3_720n vs M3_720", "M3_720S vs M3_720"]
    cc = C.set_index("comparison").reindex(lab)
    axs[1].barh(range(len(lab)), cc.delta_pct, xerr=[cc.delta_pct - cc.ci_lo_pct, cc.ci_hi_pct - cc.delta_pct], capsize=3)
    axs[1].set_yticks(range(len(lab)), lab, fontsize=8)
    axs[1].axvline(0, color="k", lw=0.8)
    axs[1].set_xlabel("held-out log-loss change (%)")
    axs[1].set_title(f"Layers and clocks  {gc}", fontsize=9)
    fig.tight_layout()
    save_fig(fig, fd / "ephys_spikes_sleep_schedule_phase1_memory_curve_2026c.png")
    MC = pd.DataFrame(cum)
    MC.to_csv(rd / "ephys_spikes_sleep_schedule_phase1_memory_curve_2026c.csv", index=False)

    write_json(rd / "run_manifest_sleep_schedule_phase1_2026c.json",
               {"run_dir": str(out), "git_commit": gc, "states": str(a.states), "review": str(a.review), "cutoff": str(CUTOFF),
                "validation": f"forward chaining over {len(blocks)} day-half blocks, first test block index {first}",
                "n_steps": len(steps), "specs": SPECS})
    # report
    L = [f"# Internal sleep schedule — Phase 1: memory curve, clocks, cycles ahead, refractoriness (cohort 2026c)", "",
         f"Plan: [2026-10-07-sleep-internal-schedule.md](../../../../implementation_plan/2026-10-07-sleep-internal-schedule.md) "
         f"(rev. 2). Phase 0: [counts](ephys_spikes_sleep_schedule_phase0_2026c.md). Driver `ephys/sleep_schedule.py phase1` "
         f"(commit {gc}); bulk `{out}`.", "",
         "**Status: technical ledger; no claim audit yet.**", "",
         "## Definitions", "",
         "- Step: 10 s of an NREM bout; outcome stay / REM / Wake at the bout's end (censored at unknown epochs or record ends). "
         "History at the bout start, fixed during the bout.",
         "- L0 = animal + $(\\sin,\\cos)(2\\pi k h/24)$, $k=1,2$ + linear experiment day + spline of $\\ln(\\text{elapsed}+5)$.",
         "- L1 (current state) = $\\ln(1+d_{prev})$ (the wake before the bout; 0 after REM), after-REM and unknown-before "
         "indicators, wake fraction of the last 10 min.",
         "- L2 (accumulated since the last REM) = spline of $\\ln(1+N_{since})$, $\\ln(1+W_{since})$, $\\ln\\text{REM}_{pre}$, "
         "has-anchor.",
         "- L3 bands $b$ (min before the bout start) 10–30, 30–90, 90–270, 270–720: $f_{R,b}$, $f_{W,b}$ (REM, wake seconds "
         "over recorded seconds), completeness $c_b$; within the record only (Phase 2 extends across gaps).",
         "- Clocks: Cl_nrem / Cl_wall = L0 + L1 + one since-REM clock (NREM time / wall time) + REM_pre + anchor; "
         "M3_720n = the L3 bands on NREM time (REM and wake per NREM second in the last X min of NREM).",
         "- S = the other animals' REM share of recorded time in the 3 h before the bout start (+ completeness).",
         "- M2i = M2 + spline($\\ln(1+N_{since})$) × $\\ln\\text{REM}_{pre}$ (refractoriness that scales with REM_pre).",
         "- Validation: forward chaining over the day-half blocks (train on all earlier blocks, test the next; first test "
         f"block = block {first + 1} of {len(blocks)}). $\\Delta$ = held-out log-loss change in % of the smaller model (negative "
         "= better); 95 % CI by bootstrap over folds; animals better = per-animal pooled change < 0. **Holds** = CI below 0 "
         "and ≥ 5/6 animals better.",
         "- Opportunity / timing split (Larson & Dinse 1985): per held-out bout with an observed end, from the model's step "
         "hazards over a 2-h horizon: $\\pi=\\sum_t S(t-1)h_R(t)$, and $\\log S(t^*-1)h_{type}(t^*) = \\log P(type) + \\log "
         "f(t^*\\mid type)$; gains in nats per bout (positive = better).",
         "- Cycles ahead (A3): REM cycles inside one SLEEP (Watson units, MA < 40 s counted in $|N|$); OLS of "
         "$\\ln|N|_k$ on $\\ln\\text{REM}_0$ with the intervening REM and $|N|$ terms, phase and animal; SEs clustered by block.",
         "", f"Data: {len(steps)} steps, {(steps.y == 1).sum()} NREM → REM, {(steps.y == 2).sum()} NREM → Wake, "
         f"{len(blocks)} blocks, {len(F)} forward folds.", "",
         "## Comparisons (forward chaining)", "", md_table(C.round(3)), "",
         "## Memory curve: L3 bands added on top of L2 (cumulative)", "", md_table(MC.round(3)), "",
         "![](../figures/ephys_spikes_sleep_schedule_phase1_memory_curve_2026c.png)", "",
         "## Opportunity vs timing (nats per held-out bout; positive = the larger model is better)", "", md_table(SPS.round(4)), "",
         "## Cycles ahead (A3)", "", md_table(A3.round(4)), "",
         "## Refractoriness (C2, description)", "", "![](../figures/ephys_spikes_sleep_schedule_phase1_refractory_2026c.png)", ""]
    flat = [ln for x in L for ln in (x if isinstance(x, list) else [x])]
    (rd / "ephys_spikes_sleep_schedule_phase1_2026c.md").write_text("\n".join(flat) + "\n", encoding="utf-8")
    print("written", rd / "ephys_spikes_sleep_schedule_phase1_2026c.md")


def selftest() -> None:
    s = np.array([W] * 30 + [N] * 100 + [W] * 20 + [N] * 100 + [R] * 60 + [W] * 50 + [N] * 900 + [W] * 200 + [N] * 1300
                 + [R] * 90 + [W] * 500 + [N] * 1300, np.int8)
    u40 = episode_units(s, 40)
    u10 = episode_units(s, 10)
    checks = {
        "MA = the 20-s wake between two NREM runs (m 40)": u40["ma"] == [(130, 150)],
        "no MA at m 10": u10["ma"] == [],
        "first NREM episode spans the MA": u40["nrem_episodes"][0] == (30, 250),
        "the 50-s wake after REM is not an MA (REM before it)": all(a != 310 for a, _ in u40["ma"]),
        "SLEEP split by the 200-s wake (> 120 s)": len(u40["sleep"]) >= 2 and u40["sleep"][0] == (30, 1260),
        "SLEEP shorter than 20 min is dropped": all(b - a >= SLEEP_MIN_S for a, b in u40["sleep"]),
        "WAKE-SLEEP: the 500-s wake followed by a SLEEP": u40["wake_sleep"] == [(2850, 3350)],
        "REM cycles never cross a SLEEP boundary (one REM per SLEEP here -> none)": u40["rem_cycles"] == [],
        "a REM cycle inside one SLEEP is found": episode_units(np.r_[s[:250], [R] * 30, [N] * 300, [R] * 30, [N] * 900].astype(np.int8), 40)["rem_cycles"] == [(250, 580)],
    }
    ok = True
    for k, v in checks.items():
        print(("PASS " if v else "FAIL ") + k)
        ok &= bool(v)
    # Phase-1 features: REM 60 s, NREM 600 s, WAKE 30 s, NREM 300 s -> REM
    s1 = np.array([N] * 100 + [R] * 60 + [N] * 600 + [W] * 30 + [N] * 300 + [R] * 40 + [N] * 50, np.int8)
    df = record_steps_s(s1)
    b2 = df[df.bout_start == 790].iloc[0]
    b1 = df[df.bout_start == 160].iloc[0]
    checks2 = {
        "bout after REM: prev_rem = 1, n_since 0, anchor": b1.prev_rem == 1 and b1.n_since == 0 and b1.has_anchor == 1 and b1.rem_pre == 60,
        "bout after the 30-s wake: d_prev 30, n_since 600, w_since 30, t_since 630": (b2.d_prev, b2.n_since, b2.w_since, b2.t_since) == (30, 600, 30, 630),
        "bout ending in REM: last step y = 1, 30 steps": (df[df.bout_start == 790].y.iloc[-1] == 1) and (df.bout_start == 790).sum() == 30,
        "first bout (record start): prev_unk, no anchor": df.iloc[0].prev_unk == 1 and df.iloc[0].has_anchor == 0,
        "band 10-30 min of the 790 bout = s 0-190: c 190/1200, REM 60/190": abs(b2["c_30"] - 190 / 1200) < 1e-9 and abs(b2["fR_30"] - 60 / 190) < 1e-9,
        "NREM-time band 10-30 min of the 790 bout: the 100 NREM s older than the last 600 -> nc 100/1200, no REM": abs(b2["nc_30"] - 100 / 1200) < 1e-9 and b2["nR_30"] == 0.0,
        "fW10 of the 790 bout = 30 / 600": abs(b2.fW10 - 30 / 600) < 1e-9,
    }
    p = np.tile([0.9, 0.05, 0.05], (200, 1))
    sc = split_scores(p, 3, 1)
    S = np.r_[1.0, np.cumprod(1 - p[:, 1] - p[:, 2])[:-1]]
    checks2["split: log P(type) + log f = log S(t-1) h(t)"] = abs(sc["log_type"] + sc["log_timing"] - np.log(S[3] * 0.05)) < 1e-12
    checks2["split: P(REM) = 0.5 with equal hazards"] = abs(sc["pi_rem"] - 0.5) < 1e-6
    for k, v in checks2.items():
        print(("PASS " if v else "FAIL ") + k)
        ok &= bool(v)
    line = "| 09-02 08:21 | SF07 | EVO | 4.06 | 09-02 18:51 | 3.66 | 3.62 | 10.5 | swapped alive |"
    c = CELL_RE.match(line)
    print(("PASS " if c and c.group(3) == "SF07" and c.group(5).strip() == "swapped alive" else "FAIL ") + "battery cell row parsed")
    ok &= bool(c)
    if not ok:
        sys.exit(1)
    print("selftest PASS")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["phase0", "phase1", "phase2", "phase2b", "phase3"])
    ap.add_argument("--parts", nargs="*", default=["c2", "b1", "b1b", "c1", "b2"], help="phase2 parts")
    ap.add_argument("--b3-states", default="D:/3rd_rat_spikes/analysis/sleep_server/states_1s_pass2med",
                    help="phase2: states for the B3 threshold check (fixed per-animal thresholds)")
    ap.add_argument("--states", default=str(STATES))
    ap.add_argument("--review", default=str(REVIEW))
    ap.add_argument("--battery-log", default=None)
    ap.add_argument("--smoke", action="store_true", help="write every output into the run folder (synthetic test data)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == "phase0":
        phase0(a)
    elif a.cmd == "phase1":
        phase1(a)
    elif a.cmd == "phase2":
        from sleep_schedule_phase2 import phase2
        phase2(a)
    elif a.cmd == "phase2b":
        from sleep_schedule_phase2b import phase2b
        phase2b(a)
    elif a.cmd == "phase3":
        from sleep_schedule_phase3 import phase3
        phase3(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
