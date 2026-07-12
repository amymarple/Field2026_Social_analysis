r"""
selftest_locomotor_states.py — offline PASS/FAIL for Phase 1 / Module 3 (locomotor state machine
+ bout-initiation). No DB. Plants scenarios that assert the state machine keeps the FOUR
distinctions and honours the WISER 'unknown'/dropout discipline:

  D1  movement INITIATION  != ROI DEPARTURE   (3 in-place bouts + 1 relocating -> 3 onsets, 1 leave)
  D2  activity IN PLACE    != leaving          (in_place vs relocating bout labels)
  D3  brief PAUSE          != settlement        (a short blip in a bout neither splits it nor rests;
                                                 a sustained stop in an ROI does create a rest episode)
  D4  ENTRY into an ROI    != settled residence (a moving pass-through visit has no rest bin)
  +   below-plane DROPOUT ROI  -> never an onset (excluded, like build_leave_table)
  +   a GAP                    -> 'unknown', never an onset (gap-ended rest episode is censored)
  +   the initiation table is well-formed for the choice_models hazard ladder

Run under the anaconda3 interpreter (pandas/numpy; sklearn not required here):
    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\selftest_locomotor_states.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import locomotor_states as ls              # noqa: E402
import semimarkov_decisions as smd         # noqa: E402
from environment_map import EnvironmentMap  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


em = EnvironmentMap.from_paths(str(ROOT / "configs/environment_map/2026-06-28_to_2026-07-05.yaml"),
                              str(ROOT / "configs/wiser_rois.json"))
roi_cfg = json.loads((ROOT / "configs/wiser_rois.json").read_text(encoding="utf-8"))

H1 = em.center("house_1"); W1 = em.center("water_1"); R1 = em.center("refuge_1")
R4 = em.center("refuge_4"); OPEN = (float(em.boundary[0]) + 30, float(em.boundary[2]) + 30)

# state-machine params (also the driver defaults)
SK = dict(buffer_in=14.0, bin_s=5.0, roi_enter_s=10.0, roi_exit_s=30.0,
          move_enter_s=10.0, move_exit_s=10.0, flicker_merge_s=30.0, long_gap_s=120.0)


class Builder:
    """4 Hz synthetic fix stream for one animal-night with a running clock."""
    def __init__(self, night, sid, rng, start_hour=22):
        self.rows = []
        self.t = pd.Timestamp(f"{night} {start_hour:02d}:00:00")
        self.night = night; self.sid = sid; self.rng = rng

    def _emit(self, x, y, moving, gap):
        self.rows.append(dict(shortid=self.sid, night=self.night, datetime=self.t,
                              x=float(x), y=float(y), valid=True, gap_flag=bool(gap),
                              moving=bool(moving)))
        self.t = self.t + pd.Timedelta(seconds=0.25)

    def stay(self, c, dur_s, moving, jit=6.0):
        for _ in range(int(dur_s * 4)):
            self._emit(c[0] + self.rng.normal(0, jit), c[1] + self.rng.normal(0, jit), moving, False)
        return self

    def travel(self, p0, p1, dur_s, jit=6.0):
        n = int(dur_s * 4)
        for k in range(n):
            f = k / max(1, n - 1)
            self._emit(p0[0] + f * (p1[0] - p0[0]) + self.rng.normal(0, jit),
                       p0[1] + f * (p1[1] - p0[1]) + self.rng.normal(0, jit), True, False)
        return self

    def skip(self, dur_s):                      # advance the clock without emitting (creates empty bins)
        self.t = self.t + pd.Timedelta(seconds=dur_s); return self

    def gapfix(self, c):                        # a single gap-flagged fix (the 'unknown' marker)
        self._emit(c[0], c[1], False, True); return self

    def df(self):
        return pd.DataFrame(self.rows)


def tables(fx, **kw):
    return ls.build_locomotor_tables(fx, roi_cfg, em, add_social=False, state_kwargs=SK, **kw)


# ---------------------------------------------------------------------------
print("A. D1 initiation != departure  &  D2 in-place != relocating")
rng = np.random.default_rng(1)
b = Builder("2026-06-29", "12378", rng)
b.stay(H1, 300, False)                 # settle: rest in house_1
b.stay(H1, 30, True)                   # in-place bout #1 (stays inside house_1)
b.stay(H1, 150, False)                 # rest again
b.stay(H1, 30, True)                   # in-place bout #2
b.stay(H1, 150, False)                 # rest again
b.travel(H1, W1, 60)                   # relocating bout: house_1 -> water_1
b.stay(W1, 200, False)                 # settle: rest in water_1
fx1 = b.df()
stream, rest_eps, bouts, init, diag, occ = tables(fx1)
n_onset = int((rest_eps.ended_by == "onset").sum())
n_reloc = int(bouts.relocating.sum())
n_inplace = int(bouts.in_place.sum())
# module-5's own view of the same stream: how many named-ROI DEPARTURES?
vis5 = smd.hysteretic_visits(fx1, roi_cfg, em, buffer_in=14.0, bin_s=5.0, enter_s=10, exit_s=30)
n_dep5 = int((vis5.ended_by == "leave").sum())
check("D1 onsets (3) exceed module-5 departures (1)",
      n_onset == 3 and n_dep5 == 1 and n_onset > n_dep5,
      f"onsets={n_onset}, module5 departures={n_dep5}, ratio={diag['D1_initiation_vs_departure']['onset_to_departure_ratio']}")
check("D2 bout labels: 2 in-place, 1 relocating",
      n_inplace == 2 and n_reloc == 1, f"in_place={n_inplace}, relocating={n_reloc}, n_bouts={len(bouts)}")

# ---------------------------------------------------------------------------
print("B. D3 brief pause != settlement (no fragmentation / no spurious rest)")
rng = np.random.default_rng(2)
MID = ((H1[0] + W1[0]) / 2, (H1[1] + W1[1]) / 2)   # a point on the house_1 -> water_1 path (open)
b = Builder("2026-06-29", "12378", rng)
b.stay(H1, 200, False)                 # rest house_1
b.travel(H1, MID, 30)                  # bout part 1 (house_1 -> midpoint)
b.stay(MID, 6, False)                  # BRIEF 6 s pause mid-path (< move_exit_s = 10 s)
b.travel(MID, W1, 30)                  # bout part 2 (midpoint -> water_1)
b.stay(W1, 200, False)                 # rest water_1
fx3 = b.df()
stream3, rest3, bouts3, init3, diag3, _ = tables(fx3)
# exactly ONE bout between the two rests (the pause did not split it); no rest episode in the middle
mid_rest = rest3[rest3.roi.isin(["refuge_1"])]           # nothing should settle mid-transit
check("D3a brief pause -> single unfragmented bout, no mid rest",
      len(bouts3) == 1 and len(rest3) == 2 and len(mid_rest) == 0,
      f"n_bouts={len(bouts3)}, n_rest={len(rest3)}")

rng = np.random.default_rng(3)
b = Builder("2026-06-29", "12378", rng)
b.stay(H1, 200, False)                 # rest house_1
b.travel(H1, R1, 20)                   # bout to refuge_1
b.stay(R1, 90, False)                  # GENUINE sustained stop in refuge_1 (> settle threshold)
b.travel(R1, W1, 20)                   # bout to water_1
b.stay(W1, 200, False)                 # rest water_1
fx3b = b.df()
_, rest3b, bouts3b, _, _, _ = tables(fx3b)
check("D3b sustained stop in an ROI -> a rest episode is created (refuge_1)",
      (rest3b.roi == "refuge_1").sum() == 1 and len(bouts3b) == 2,
      f"rest ROIs={list(rest3b.roi)}, n_bouts={len(bouts3b)}")

# ---------------------------------------------------------------------------
print("C. D4 arrival != settled (a moving pass-through has no rest bin)")
rng = np.random.default_rng(4)
b = Builder("2026-06-29", "12378", rng)
b.stay(W1, 200, False)                 # rest water_1
b.travel(W1, H1, 20)                   # approach house_1
b.stay(H1, 30, True)                   # PASS THROUGH house_1 while still moving (never settles)
b.travel(H1, R1, 20)                   # leave to refuge_1
b.stay(R1, 200, False)                 # rest refuge_1
fx4 = b.df()
stream4, rest4, bouts4, init4, diag4, _ = tables(fx4)
# module-5 sees a house_1 visit (entry), but the stream has ZERO 'rest' bins in house_1
h1_rest_bins = int(((stream4.state == "rest") & (stream4.roi_state == "house_1")).sum())
vis4 = smd.hysteretic_visits(fx4, roi_cfg, em, buffer_in=14.0, bin_s=5.0, enter_s=10, exit_s=30)
h1_visit = int((vis4.roi == "house_1").sum())
check("D4 house_1 entered as a visit but NOT settled (0 rest bins there)",
      h1_visit >= 1 and h1_rest_bins == 0 and (rest4.roi == "house_1").sum() == 0,
      f"house_1 visits={h1_visit}, house_1 rest bins={h1_rest_bins}, "
      f"frac_visits_no_rest={diag4['D4_arrival_vs_settled']['frac_visits_no_rest']}")

# ---------------------------------------------------------------------------
print("D. Dropout & gap discipline (never an onset)")
# refuge_4 on a burrow night (07-04) is a below-plane dropout -> excluded entirely
rng = np.random.default_rng(5)
b = Builder("2026-07-04", "12378", rng)
b.stay(R4, 300, False)                 # rest in refuge_4 (burrow night)
b.stay(R4, 30, True)                   # would-be in-place onset
b.stay(R4, 150, False)
fx5 = b.df()
_, rest5, _, init5, _, _ = tables(fx5)
r4_init_rows = 0 if init5.empty else int((init5.roi == "refuge_4").sum())
check("dropout: refuge_4 burrow-night rest -> excluded from the initiation table (no rows, no onset)",
      r4_init_rows == 0 and (init5.empty or int(init5.initiated.sum()) == 0),
      f"refuge_4 init rows={r4_init_rows}, total init rows={0 if init5.empty else len(init5)}")

# a gap-ended rest episode is 'unknown', never an onset
rng = np.random.default_rng(6)
b = Builder("2026-06-29", "12378", rng)
b.stay(H1, 300, False)                 # rest house_1
b.skip(400)                            # long signal dropout (empty bins -> unknown)
b.gapfix(H1)                           # a single gap-flagged fix, then nothing
fx6 = b.df()
_, rest6, _, init6, _, _ = tables(fx6)
ended = list(rest6.ended_by)
n_init_1 = 0 if init6.empty else int(init6.initiated.sum())
check("gap: rest episode ended by a long dropout is censored_gap, never initiated=1",
      ended == ["censored_gap"] and n_init_1 == 0, f"ended_by={ended}, initiated_sum={n_init_1}")

# ---------------------------------------------------------------------------
print("E. Initiation table is well-formed for the hazard ladder")
# many rest->onset episodes; the table must expose initiated in {0,1}, monotone rest_elapsed within
# an episode, censored flag, layout + clock columns.
rng = np.random.default_rng(7)
b = Builder("2026-06-29", "12378", rng)
for _ in range(12):
    b.stay(H1, int(rng.uniform(60, 240)), False)   # variable rest durations
    b.stay(H1, 30, True)                            # in-place onset
b.stay(H1, 120, False)
fx7 = b.df()
_, rest7, _, init7, _, occ7 = tables(fx7)
ok_cols = set(["shortid", "night", "visit_id", "roi", "epoch", "t_epoch", "rest_elapsed_s",
               "initiated", "censored", "clock_hour"]).issubset(init7.columns)
# per-episode rest_elapsed_s must be monotone non-decreasing
mono = all(g["rest_elapsed_s"].is_monotonic_increasing
           for _, g in init7.sort_values(["visit_id", "epoch"]).groupby("visit_id"))
has_both = init7.initiated.nunique() == 2
# state occupancy has all four core states represented across the run (rest + local_active at least)
check("initiation table well-formed (schema, monotone dwell, both classes)",
      ok_cols and mono and has_both,
      f"cols_ok={ok_cols}, monotone={mono}, initiated_values={sorted(init7.initiated.unique())}, "
      f"n_rows={len(init7)}, onsets={int((rest7.ended_by=='onset').sum())}")

# ---------------------------------------------------------------------------
print("F. Bout gap-handling (a dropout must not inflate dur_s or merge two bouts)")
# A bout spanning a LONG (180 s) signal dropout must SPLIT — the movement hysteresis holds active
# across the empty bins, but unobserved time is not locomotion.
rng = np.random.default_rng(12)
MIDw = ((H1[0] + W1[0]) / 2, (H1[1] + W1[1]) / 2)
b = Builder("2026-06-29", "12378", rng)
b.stay(H1, 200, False)                 # rest house_1
b.travel(H1, MIDw, 30)                 # bout part 1
b.skip(180)                            # LONG signal dropout (empty bins; active held True)
b.travel(MIDw, W1, 30)                 # bout part 2 (after the blackout)
b.stay(W1, 200, False)                 # rest water_1
fxg = b.df()
_, _, boutsg, _, _, _ = tables(fxg)
check("F1 long dropout splits the bout (no merge, dur_s not inflated)",
      len(boutsg) == 2 and float(boutsg.dur_s.max()) < 120 and bool(boutsg.spans_dropout.all()),
      f"n_bouts={len(boutsg)}, max_dur_s={float(boutsg.dur_s.max()) if len(boutsg) else 'n/a'}, "
      f"spans_dropout={list(boutsg.spans_dropout)}")

# A SHORT (10 s < long_gap_s) gap is absorbed -> ONE bout (span includes the brief gap, flagged).
rng = np.random.default_rng(13)
b = Builder("2026-06-29", "12378", rng)
b.stay(H1, 200, False)
b.travel(H1, MIDw, 30)
b.skip(10)                             # brief dropout
b.travel(MIDw, W1, 30)
b.stay(W1, 200, False)
fxs = b.df()
_, _, boutss, _, _, _ = tables(fxs)
check("F2 short dropout absorbed -> one bout (has_gap flagged, not split)",
      len(boutss) == 1 and bool(boutss.has_gap.iloc[0]) and not bool(boutss.spans_dropout.iloc[0]),
      f"n_bouts={len(boutss)}, has_gap={list(boutss.has_gap)}, spans_dropout={list(boutss.spans_dropout)}")

# ---------------------------------------------------------------------------
print()
if FAILS:
    print(f"FAIL — {len(FAILS)} check(s) failed: {FAILS}")
    sys.exit(1)
print("PASS — locomotor state machine healthy (4 distinctions hold; dropout/gap kept 'unknown')")
sys.exit(0)
