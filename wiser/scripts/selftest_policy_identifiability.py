r"""
selftest_policy_identifiability.py — offline PASS/FAIL for the agent-policy identifiability
ladder. No DB. Plants nine scenarios and asserts the pipeline CERTIFIES real cross-night
individual / social decision structure and REJECTS the confounds & leakage traps.

Run under the anaconda3 interpreter (needs sklearn):
    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\selftest_policy_identifiability.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import choice_models as cm                    # noqa: E402
import semimarkov_decisions as smd            # noqa: E402
from environment_map import EnvironmentMap    # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


# ---------------------------------------------------------------------------
# synthetic leave-table generator with a controllable per-epoch hazard
# ---------------------------------------------------------------------------

def gen_leave(nights, animals, hazard_fn, rng, *, visits_per=40, max_epochs=12,
              rois=("house", "refuge", "water"), visit_p=None, weather=None, social_fn=None):
    """Emit at-risk epochs. hazard_fn(animal, night, dwell_epoch, roi, w, soc) -> p(left)."""
    rows = []
    weather = weather or {n: 0.0 for n in nights}
    for night in nights:
        w = weather[night]
        for a in animals:
            vp = (visit_p or {}).get(a)
            for _v in range(visits_per):
                roi = rng.choice(rois, p=vp) if vp is not None else rng.choice(rois)
                for e in range(max_epochs):
                    soc = social_fn(a, night, roi, e, rng) if social_fn else np.nan
                    p = hazard_fn(a, night, e, roi, w, soc)
                    left = int(rng.random() < p)
                    rows.append({"shortid": a, "night": night, "roi": roi, "dwell_elapsed_s": e * 5.0,
                                 "is_house": int(roi == "house"), "is_refuge": int(roi == "refuge"),
                                 "is_water": int(roi == "water"), "w_temp_c": w, "nn_dist_in": soc,
                                 "left": left})
                    if left:
                        break
    return pd.DataFrame(rows)


NIGHTS = [f"2026-06-{d:02d}" for d in range(28, 28 + 6)]           # 6 nights
ANIMALS = ["A1", "A2", "A3", "A4", "A5"]
BASE_CAT = ["roi"]


def base_hazard(a, night, e, roi, w, soc):
    """Shared law: leave-rate rises with dwell; house 'stickier' than water. No identity."""
    intercept = {"house": -2.2, "refuge": -1.8, "water": -1.2}[roi]
    return sigmoid(intercept + 0.18 * e)


# ---------------------------------------------------------------------------
print("A. Individual arm (personalization = cross-night transfer)")

rng = np.random.default_rng(1)
# Scenario 1 — pure shared-use: everyone identical -> no individual gain
df1 = gen_leave(NIGHTS, ANIMALS, base_hazard, rng)
g1 = cm.summarize_gain(cm.personalization_gain(df1, "left", base_categorical=BASE_CAT,
                                               id_features=("is_house", "is_refuge")))
check("1 pure shared-use -> ~no individual gain", (g1["median"] < 0.02), f"median Dbits={g1['median']:.4f}")

# Scenario 2 — stable individual bias in house, present every night -> certified & transfers
def haz_indiv(a, night, e, roi, w, soc):
    bump = 1.6 if (a == "A1" and roi == "house") else 0.0
    return sigmoid({"house": -2.2, "refuge": -1.8, "water": -1.2}[roi] + 0.18 * e + bump)
df2 = gen_leave(NIGHTS, ANIMALS, haz_indiv, rng)
pg2 = cm.personalization_gain(df2, "left", base_categorical=BASE_CAT, id_features=("is_house", "is_refuge"))
a1 = pg2[pg2.animal == "A1"]
others2 = pg2[pg2.animal != "A1"]
# the individual signal is PER ANIMAL: A1's gain is reliably positive across held nights and
# exceeds the (null) other animals'. The overall median is diluted by the 4 null animals.
check("2 stable individual bias -> A1 gain positive, transfers, exceeds null animals",
      (a1["delta_bits"] > 0).mean() >= 0.8 and a1["delta_bits"].median() > 0.003
      and a1["delta_bits"].median() > others2["delta_bits"].median(),
      f"A1 median={float(a1['delta_bits'].median()):.4f} frac+={float((a1['delta_bits']>0).mean()):.2f} "
      f"others median={float(others2['delta_bits'].median()):.4f}")

# Scenario 3 — visitation-only pseudo-difference: same law, A2 visits refuge more -> rejected
vp = {a: np.array([1/3, 1/3, 1/3]) for a in ANIMALS}
vp["A2"] = np.array([0.15, 0.70, 0.15])
df3 = gen_leave(NIGHTS, ANIMALS, base_hazard, rng, visit_p=vp)
perm3 = cm.conditional_permutation_null(df3, "left", strata_cols=("roi",), base_categorical=BASE_CAT,
                                        id_features=("is_house", "is_refuge"), n_perm=40, seed=3)
g3 = cm.summarize_gain(cm.personalization_gain(df3, "left", base_categorical=BASE_CAT,
                                               id_features=("is_house", "is_refuge")))
check("3 visitation-only pseudo-difference -> rejected (small gain, low z)",
      (g3["median"] < 0.02) and (not (perm3["z"] and perm3["z"] > 2)),
      f"median={g3['median']:.4f}, cond-perm z={perm3['z']}")

# Scenario 6 — nonstationary bias: A3's house bump differs each night -> no cross-night transfer
def haz_nonstat(a, night, e, roi, w, soc):
    bump = 0.0
    if a == "A3" and roi == "house":
        bump = 2.0 * (hash((night,)) % 2) - 1.0        # +1 or -1 depending on night, deterministic
    return sigmoid({"house": -2.2, "refuge": -1.8, "water": -1.2}[roi] + 0.18 * e + bump)
df6 = gen_leave(NIGHTS, ANIMALS, haz_nonstat, rng)
pg6 = cm.personalization_gain(df6, "left", base_categorical=BASE_CAT, id_features=("is_house", "is_refuge"))
a3 = pg6[pg6.animal == "A3"]
check("6 nonstationary within-night-only bias -> not certified (no transfer)",
      (a3["delta_bits"].median() < 0.02),
      f"A3 median Dbits={float(a3['delta_bits'].median()):.4f}")

# ---------------------------------------------------------------------------
print("B. Weather confounding")

# Scenario 7 — apparent A4 individual effect is really weather: A4 only on wet nights,
# and wet nights raise the leave rate for EVERYONE. Base without weather -> false gain;
# base with weather -> gain vanishes.
wetmap = {n: (1.0 if i < 3 else 0.0) for i, n in enumerate(NIGHTS)}       # first 3 nights wet
def haz_weather(a, night, e, roi, w, soc):
    return sigmoid({"house": -2.2, "refuge": -1.8, "water": -1.2}[roi] + 0.18 * e + 1.4 * w)
df7 = gen_leave(NIGHTS, ANIMALS, haz_weather, rng, weather=wetmap)
# A4 is observed ONLY on wet nights -> its high leave-rate is really the wet main effect.
df7 = df7.drop(index=df7[(df7.shortid == "A4") & (df7.w_temp_c == 0.0)].index).reset_index(drop=True)
pg7_no = cm.personalization_gain(df7, "left", base_categorical=BASE_CAT, id_features=("is_house",))
pg7_w = cm.personalization_gain(df7, "left", base_numeric=("w_temp_c",), base_categorical=BASE_CAT,
                                id_features=("is_house",))
a4_no = float(pg7_no[pg7_no.animal == "A4"]["delta_bits"].median())
a4_w = float(pg7_w[pg7_w.animal == "A4"]["delta_bits"].median())
# without weather A4 looks individual; WITH weather the apparent effect shrinks toward zero
check("7 weather-confounded pseudo-individual (A4) -> shrinks after weather adjustment",
      (a4_no > 0.005) and (a4_w < a4_no) and (a4_w < 0.02),
      f"A4 no-weather={a4_no:.4f} -> with-weather={a4_w:.4f}")

# Scenario 7b — differential missingness across nights: a numeric feature NaN on ALL of one night
# and present on others (like social/weather dropping out on burrow nights) must NOT crash or
# silently mis-align train/test design columns. (Regression guard for build_design alignment.)
df7b = gen_leave(NIGHTS, ANIMALS, base_hazard, rng)
df7b["featA"] = 1.0 + rng.normal(0, 0.1, len(df7b))
df7b.loc[df7b.night == NIGHTS[0], "featA"] = np.nan          # missing on night 0 only
df7b["featB"] = 2.0 + rng.normal(0, 0.1, len(df7b))
df7b.loc[df7b.night == NIGHTS[1], "featB"] = np.nan          # missing on a DIFFERENT night
si7b = cm.social_increment(df7b, "left", base_numeric=("featA", "featB"), base_categorical=BASE_CAT,
                           social_features=("featA",))
pg7b = cm.personalization_gain(df7b, "left", base_numeric=("featA", "featB"), base_categorical=BASE_CAT,
                               id_features=("is_house",))
ok7b = bool(np.isfinite(si7b["delta_bits"]).all() and np.isfinite(pg7b["delta_bits"]).all())
check("7b differential cross-night missingness -> aligned design, finite bits (no crash)",
      ok7b, f"social finite={np.isfinite(si7b['delta_bits']).all()} pers finite={np.isfinite(pg7b['delta_bits']).all()}")

# ---------------------------------------------------------------------------
print("C. Social arm (strictly pre-decision)")

# Scenario 4 — genuine pre-decision social effect: near neighbour (small nn_dist) -> leave faster.
def soc_near(a, night, roi, e, rng):
    return float(rng.uniform(5, 80))                  # pre-decision nn distance (in)
def haz_social(a, night, e, roi, w, soc):
    near = 1.0 if (soc == soc and soc < 40) else 0.0
    return sigmoid({"house": -2.2, "refuge": -1.8, "water": -1.2}[roi] + 0.18 * e + 1.3 * near)
df4 = gen_leave(NIGHTS, ANIMALS, haz_social, rng, social_fn=soc_near)
si4 = cm.social_increment(df4, "left", base_categorical=BASE_CAT, social_features=("nn_dist_in",))
ts4 = cm.time_shift_social_null(df4, "left", ("nn_dist_in",), base_categorical=BASE_CAT, n_perm=25, seed=4)
check("4 genuine pre-decision social -> positive Dbits, beats time-shift",
      (si4["delta_bits"].mean() > 0.003) and (ts4["z"] and ts4["z"] > 2),
      f"social Dbits={si4['delta_bits'].mean():.4f}, time-shift z={ts4['z']}")

# Scenario 5 — post-decision leakage: the recorded pre-decision nn_dist is RANDOM (uninformative);
# the 'true' driver would be post-decision. Pre-decision social must show ~no gain.
def soc_rand(a, night, roi, e, rng):
    return float(rng.uniform(5, 200))
df5 = gen_leave(NIGHTS, ANIMALS, base_hazard, rng, social_fn=soc_rand)   # hazard ignores soc
si5 = cm.social_increment(df5, "left", base_categorical=BASE_CAT, social_features=("nn_dist_in",))
check("5 post-decision-leakage / uninformative pre-decision social -> ~no gain",
      (si5["delta_bits"].mean() < 0.01), f"social Dbits={si5['delta_bits'].mean():.4f}")

# ---------------------------------------------------------------------------
print("D. Dropout-as-departure trap (builder honours 'unknown')")

em = EnvironmentMap.from_paths(str(ROOT / "configs/environment_map/2026-06-28_to_2026-07-05.yaml"),
                               str(ROOT / "configs/wiser_rois.json"))
# animal sits in refuge_4 on a BURROW night (07-04) then the tag drops out (gap) -> vanishes.
base = pd.Timestamp("2026-07-04 23:00:00")
rows = []
c = em.center("refuge_4")
for k in range(160):                                  # ~40 s in refuge_4 at 4 Hz
    rows.append(dict(shortid="A1", night="2026-07-04", datetime=base + pd.Timedelta(seconds=0.25 * k),
                     x=c[0] + np.random.normal(0, 3), y=c[1] + np.random.normal(0, 3),
                     roi="refuge_4", valid=True, gap_flag=False, moving=False))
# then a long gap (dropout) and no more fixes this night -> vanish (unknown, NOT a leave)
gap_fix = dict(shortid="A1", night="2026-07-04", datetime=base + pd.Timedelta(seconds=400),
               x=c[0], y=c[1], roi="refuge_4", valid=True, gap_flag=True, moving=False)
fx8 = pd.DataFrame(rows + [gap_fix])
visits8 = smd.segment_visits(fx8, min_dwell_s=3.0)
leave8 = smd.build_leave_table(visits8, fx8, em, epoch_s=5.0)
n_left = int(leave8["left"].sum()) if not leave8.empty else 0
check("8 refuge_4 burrow-night dropout -> NO left=1 (kept unknown)", n_left == 0,
      f"left=1 count={n_left}, leave rows={len(leave8)}")

# Scenario 8b — SHALLOW dropout-region visit that ends by a tracked move (NO gap): a burrow-night
# refuge_4 visit whose tag stays tracked and walks out to food_1 continuously. is_dropout is a
# whole-night/whole-ROI flag, so build_leave_table must DROP it entirely (never emit left=1), even
# though ended_by='leave'. (Regression guard for the compound-guard bug.)
rows = []
c4, cf = em.center("refuge_4"), em.center("food_1")
b2 = pd.Timestamp("2026-07-04 23:30:00")
for k in range(160):                                  # 40 s tracked in refuge_4
    rows.append(dict(shortid="A1", night="2026-07-04", datetime=b2 + pd.Timedelta(seconds=0.25 * k),
                     x=c4[0] + np.random.normal(0, 3), y=c4[1] + np.random.normal(0, 3),
                     roi="refuge_4", valid=True, gap_flag=False, moving=False))
for k in range(80):                                   # continuous move to food_1 (no gap)
    rows.append(dict(shortid="A1", night="2026-07-04", datetime=b2 + pd.Timedelta(seconds=40 + 0.25 * k),
                     x=cf[0] + np.random.normal(0, 3), y=cf[1] + np.random.normal(0, 3),
                     roi="food_1", valid=True, gap_flag=False, moving=(k < 40)))
fx8b = pd.DataFrame(rows)
v8b = smd.segment_visits(fx8b, min_dwell_s=3.0)
l8b = smd.build_leave_table(v8b, fx8b, em, epoch_s=5.0)
r4_rows = int((l8b["roi"] == "refuge_4").sum()) if not l8b.empty else 0
check("8b shallow tracked leave OUT of a dropout region -> refuge_4 dropped (no left=1)",
      r4_rows == 0, f"refuge_4 leave rows={r4_rows} (visit ended_by='leave')")

# ---------------------------------------------------------------------------
print("E. Matched-choice for symmetric resources")

rng = np.random.default_rng(9)
rows = []
for n in NIGHTS:
    for _ in range(30):
        rows.append(dict(shortid="P", night=n, origin="open", dest=("house_1" if rng.random() < 0.85 else "house_2")))
        rows.append(dict(shortid="Q", night=n, origin="open", dest=("house_1" if rng.random() < 0.5 else "house_2")))
dest9 = pd.DataFrame(rows)
mc = cm.matched_choice_stability(dest9, ["house_1", "house_2"])
p_stable = bool(mc[mc.animal == "P"]["stable_pref"].iloc[0]) if len(mc[mc.animal == "P"]) else False
q_stable = bool(mc[mc.animal == "Q"]["stable_pref"].iloc[0]) if len(mc[mc.animal == "Q"]) else False
check("9 matched-choice: stable-preference animal certified, coin-flip animal not",
      p_stable and (not q_stable), f"P stable={p_stable}, Q stable={q_stable}")

# ---------------------------------------------------------------------------
print("F. Hysteretic ROI-state segmentation (jitter-tolerant decision unit)")

import json as _json
roi_cfg = _json.loads((ROOT / "configs/wiser_rois.json").read_text())
h1 = em.center("house_1"); w1c = em.center("water_1")
rng = np.random.default_rng(11)

def _fixstream(segs):
    """segs = list of (cx, cy, dur_s, jitter). Returns a fix DataFrame at 4 Hz."""
    rows = []; t = [pd.Timestamp("2026-06-29 22:00:00")]
    for cx, cy, dur, jit in segs:
        for _ in range(int(dur * 4)):
            rows.append(dict(shortid="12378", night="2026-06-29", datetime=t[0],
                             x=cx + rng.normal(0, jit), y=cy + rng.normal(0, jit),
                             valid=True, gap_flag=False, moving=(jit > 15)))
            t[0] = t[0] + pd.Timedelta(seconds=0.25)
    return pd.DataFrame(rows)

# Scenario 10 — boundary FLICKER: rest in house_1, a brief 15 s hop just outside the buffer
# (near the boundary, no other ROI), back to house_1. Must collapse to ONE house_1 visit
# (hysteresis holds / flicker-merge), NOT a self-return leave.
flick = _fixstream([(h1[0], h1[1], 300, 10), (h1[0] + 38, h1[1], 15, 3), (h1[0], h1[1], 120, 10)])
vf = smd.hysteretic_visits(flick, roi_cfg, em, buffer_in=14.0, bin_s=5.0, enter_s=10, exit_s=10,
                           flicker_merge_s=30.0)
n_h1 = int((vf.roi == "house_1").sum())
n_selfret = int(((vf.roi == "house_1") & (vf.next_roi == "house_1")).sum())
check("10 boundary flicker -> ONE house_1 visit (no jitter self-return)",
      n_h1 == 1 and n_selfret == 0, f"house_1 visits={n_h1}, self-returns={n_selfret}, total={len(vf)}")

# Scenario 11 — GENUINE leave-and-return loop: rest house_1, 40 s at water_1 (far, establishes
# another ROI), back to house_1. Must be PRESERVED as house_1 -> water_1 -> house_1 (not erased).
loop = _fixstream([(h1[0], h1[1], 300, 10), (w1c[0], w1c[1], 40, 4), (h1[0], h1[1], 120, 10)])
vl = smd.hysteretic_visits(loop, roi_cfg, em, buffer_in=14.0, bin_s=5.0, enter_s=10, exit_s=30,
                           flicker_merge_s=30.0)
seq = list(vl.roi)
check("11 genuine leave-return loop -> preserved (house_1 -> water_1 -> house_1)",
      seq == ["house_1", "water_1", "house_1"], f"sequence={seq}")

# ---------------------------------------------------------------------------
print()
if FAILS:
    print(f"FAIL — {len(FAILS)} check(s) failed: {FAILS}")
    sys.exit(1)
print("PASS — policy-identifiability ladder core healthy (certifies real structure, rejects traps)")
sys.exit(0)
