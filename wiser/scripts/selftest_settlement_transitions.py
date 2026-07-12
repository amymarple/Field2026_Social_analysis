r"""
selftest_settlement_transitions.py — offline PASS/FAIL for Phase 2 / Module 6 (destination &
settlement on the unified locomotor-state representation). No DB. Plants one clean scenario per
transition type and asserts the classifier types it correctly, that a destination is defined ONLY
after sustained stable residence, and that the settlement threshold behaves sensibly.

Runs end-to-end: synthetic fixes -> module-3 build_locomotor_tables -> stationary_episodes ->
settlement_transitions. Run under the anaconda3 interpreter (pandas/numpy):
    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\selftest_settlement_transitions.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import locomotor_states as ls               # noqa: E402
import settlement_transitions as st          # noqa: E402
from environment_map import EnvironmentMap   # noqa: E402

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
SK = dict(buffer_in=14.0, bin_s=5.0, roi_enter_s=10.0, roi_exit_s=30.0,
          move_enter_s=10.0, move_exit_s=10.0, flicker_merge_s=30.0, long_gap_s=120.0)


class Builder:
    def __init__(self, night, sid, rng, start_hour=22):
        self.rows = []; self.t = pd.Timestamp(f"{night} {start_hour:02d}:00:00")
        self.night = night; self.sid = sid; self.rng = rng

    def _emit(self, x, y, moving, gap):
        self.rows.append(dict(shortid=self.sid, night=self.night, datetime=self.t, x=float(x),
                              y=float(y), valid=True, gap_flag=bool(gap), moving=bool(moving)))
        self.t += pd.Timedelta(seconds=0.25)

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

    def skip(self, dur_s):
        self.t += pd.Timedelta(seconds=dur_s); return self

    def gapfix(self, c):
        self._emit(c[0], c[1], False, True); return self

    def df(self):
        return pd.DataFrame(self.rows)


def transitions(fx, *, settle_min_s=60.0, conf_frac=0.5):
    _, stat_eps, _, _, _, _ = ls.build_locomotor_tables(fx, roi_cfg, em, add_social=False, state_kwargs=SK)
    typed = st.type_stationary_episodes(stat_eps, em, settle_min_s=settle_min_s, conf_frac=conf_frac)
    return st.build_transitions(typed, em), typed


# ---------------------------------------------------------------------------
print("A. relocation (settle A -> bout -> settle B)")
rng = np.random.default_rng(1)
b = Builder("2026-06-29", "12378", rng)
b.stay(H1, 300, False).travel(H1, W1, 60).stay(W1, 300, False)
tr, typed = transitions(b.df())
rel = tr[tr.origin_roi == "house_1"]
check("A relocation house_1 -> water_1", len(rel) == 1 and rel.iloc[0].transition_type == "relocation"
      and rel.iloc[0].dest_roi == "water_1",
      f"types={list(tr.transition_type)}, dest={list(tr.dest_roi)}")

print("B. same_site_return (settle A -> bout out-and-back -> settle A)")
rng = np.random.default_rng(2)
b = Builder("2026-06-29", "12378", rng)
b.stay(H1, 300, False).travel(H1, OPEN, 40).travel(OPEN, H1, 40).stay(H1, 300, False)
tr, _ = transitions(b.df())
h1 = tr[tr.origin_roi == "house_1"]
check("B same_site_return + genuine intervening bout",
      len(h1) == 1 and h1.iloc[0].transition_type == "same_site_return" and h1.iloc[0].inter_bout_bins >= 1,
      f"type={list(h1.transition_type)}, inter_bout_bins={list(h1.inter_bout_bins)}")

print("C. pass_through (settle A -> bout -> BRIEF named stop -> ...)")
rng = np.random.default_rng(3)
b = Builder("2026-06-29", "12378", rng)
b.stay(H1, 300, False).travel(H1, W1, 40).stay(W1, 25, False).travel(W1, R1, 40).stay(R1, 300, False)
tr, typed = transitions(b.df())          # settle_min 60 -> the 25 s water_1 stop is a pass-through
h1 = tr[tr.origin_roi == "house_1"]
check("C pass_through (brief water_1 stop not settled)",
      len(h1) == 1 and h1.iloc[0].transition_type == "pass_through" and h1.iloc[0].dest_roi == "water_1",
      f"type={list(h1.transition_type)}, dest_type={list(h1.dest_type)}")

print("D. open_field_termination (settle A -> bout -> sustained OPEN stop)")
rng = np.random.default_rng(4)
b = Builder("2026-06-29", "12378", rng)
b.stay(H1, 300, False).travel(H1, OPEN, 40).stay(OPEN, 200, False)
tr, _ = transitions(b.df())
h1 = tr[tr.origin_roi == "house_1"]
check("D open_field_termination", len(h1) == 1 and h1.iloc[0].transition_type == "open_field_termination",
      f"type={list(h1.transition_type)}, dest_type={list(h1.dest_type)}")

print("E. censored (settle A -> departure into a long dropout)")
rng = np.random.default_rng(5)
b = Builder("2026-06-29", "12378", rng)
b.stay(H1, 300, False).travel(H1, OPEN, 30).skip(400).gapfix(OPEN)
tr, _ = transitions(b.df())
h1 = tr[tr.origin_roi == "house_1"]
check("E censored (departure interrupted by dropout / no observed settlement)",
      len(h1) == 1 and h1.iloc[0].transition_type == "censored",
      f"type={list(h1.transition_type) if len(h1) else 'no house_1 origin'}")

print("F. destination defined ONLY after sustained residence (threshold sensitivity)")
# a 40 s named stop is a pass_through at settle_min=60 but a settlement at settle_min=30.
rng = np.random.default_rng(6)
b = Builder("2026-06-29", "12378", rng)
b.stay(H1, 300, False).travel(H1, W1, 40).stay(W1, 40, False).travel(W1, R1, 40).stay(R1, 300, False)
fx = b.df()
tr60, _ = transitions(fx, settle_min_s=60.0)
tr30, _ = transitions(fx, settle_min_s=30.0)
t60 = tr60[tr60.origin_roi == "house_1"].iloc[0].transition_type if len(tr60[tr60.origin_roi == "house_1"]) else None
# at 30 s the water_1 stop becomes a settlement -> the house_1 departure is a relocation to water_1
t30 = tr30[tr30.origin_roi == "house_1"].iloc[0].transition_type if len(tr30[tr30.origin_roi == "house_1"]) else None
check("F 40 s named stop: pass_through @60 s, relocation @30 s (destination = sustained residence)",
      t60 == "pass_through" and t30 == "relocation", f"@60s={t60}, @30s={t30}")

print("G. dropout-region origin/destination excluded (refuge_4 burrow night)")
rng = np.random.default_rng(7)
b = Builder("2026-07-04", "12378", rng)              # burrow night -> refuge_4 is below-plane dropout
b.stay(R4, 300, False).travel(R4, W1, 60).stay(W1, 300, False)
tr, typed = transitions(b.df())
# refuge_4 settle is typed 'dropout', so it is NOT emitted as a settlement origin
r4_origin = int((tr.origin_roi == "refuge_4").sum()) if not tr.empty else 0
r4_type = typed[typed.roi == "refuge_4"]["stype"].tolist()
check("G refuge_4 burrow-night residence typed 'dropout', not a settlement origin",
      r4_origin == 0 and all(t == "dropout" for t in r4_type),
      f"refuge_4 origins={r4_origin}, refuge_4 stypes={r4_type}")

# ---------------------------------------------------------------------------
print()
if FAILS:
    print(f"FAIL — {len(FAILS)} check(s) failed: {FAILS}")
    sys.exit(1)
print("PASS — settlement/transition representation healthy (5 types; destination = sustained residence only)")
sys.exit(0)
