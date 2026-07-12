r"""
scratch_env_change_audit.py — adversarial audit of the "social effect is small & stationary" claim
under the ENVIRONMENT-CHANGE lens. Read-only; writes nothing but stdout.

PRESERVED AUDIT SCRATCH (migrated 2026-07-12 into wiser/audit/): this is an ad-hoc, agent-driven
adversarial audit record, not pipeline code. Its inputs (leave_decisions.csv, social_habituation_per_night.csv)
are the policy-identifiability BULK run — now off-repo under $FIELD2026_ANALYSIS_OUT_ROOT/2026a/ (the canonical
in-repo reports live under results/2026a/wiser_policy/). Not runnable as-is without that bulk run present.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent   # wiser/ (this file lives in wiser/audit/)
sys.path.insert(0, str(ROOT / "src"))
import choice_models as cm

DWELL = "dwell_elapsed_s"
BASE_NUM = ["dist_to_edge_in", "clock_hour", "moving_frac", "wet", "fireworks", "burrow"]
WEATHER = ["w_temp_c", "w_tempdew_gap_c", "w_rain_log1p", "w_solar_wm2"]
SOCIAL = ["n_within_1m", "mean_others_dist_in"]
CAT = ["roi"]

leave = pd.read_csv(ROOT / "outputs/policy_identifiability_2026-06-28_to_2026-07-08/leave_decisions.csv")
nights = sorted(leave["night"].unique())
idx = {n: i for i, n in enumerate(nights)}
leave["night_index"] = leave["night"].map(idx)
base = [c for c in BASE_NUM + WEATHER if c in leave.columns]
social = [c for c in SOCIAL if c in leave.columns]
print("nights:", nights)
print("n rows:", len(leave), "base feats:", base, "social:", social)


def lono_all(df, num, cat):
    t = cm.lono_bits(df, "left", numeric=num, categorical=cat, dwell_col=DWELL)
    a = t[t.animal == "ALL"]
    return float(a["bits"].mean()), a.set_index("held_night")["bits"]


# ---- reproduce held-out per-night social increment (M5) ----
Hc, bits_c = lono_all(leave, base + social, CAT)
Hb, bits_b = lono_all(leave, base, CAT)
per = pd.DataFrame({"held_night": bits_b.index,
                    "ho_social_dbits": (bits_b - bits_c).reindex(bits_b.index).values})
per["night_index"] = per["held_night"].map(idx)
print("\n== held-out per-night social increment (reproduce M5) ==")
print(per.to_string(index=False))
print("pooled mean held-out social dbits = %.5f" % per["ho_social_dbits"].mean())

# ---- environment-change regressors (per night) ----
# night flags from environment_map + FIELD_OBSERVATIONS
reg = pd.DataFrame({"night": nights})
reg["night_index"] = reg["night"].map(idx)
burrow = {"2026-07-03", "2026-07-04", "2026-07-05", "2026-07-06"}
wet = {"2026-06-30", "2026-07-01", "2026-07-04", "2026-07-06"}
fireworks = {"2026-07-04"}
refuge4_present = set(nights) - {"2026-07-07", "2026-07-08"}
reg["burrow"] = reg["night"].isin(burrow).astype(float)
reg["wet"] = reg["night"].isin(wet).astype(float)
reg["fireworks"] = reg["night"].isin(fireworks).astype(float)
reg["refuge4_present"] = reg["night"].isin(refuge4_present).astype(float)
# perturbation-onset spike: nights AT/just-after an environmental change
onset = {"2026-06-28", "2026-07-03", "2026-07-04", "2026-07-07"}
reg["perturb_onset"] = reg["night"].isin(onset).astype(float)
# days-since-last-change (continuous novelty; resets at change events)
change_days = {"2026-06-28": 0, "2026-06-29": 1, "2026-06-30": 2, "2026-07-01": 3, "2026-07-02": 4,
               "2026-07-03": 0, "2026-07-04": 0, "2026-07-05": 1, "2026-07-06": 2,
               "2026-07-07": 0, "2026-07-08": 1}
reg["days_since_change"] = reg["night"].map(change_days).astype(float)
reg = reg.set_index("night")
print("\n== per-night regressors ==")
print(reg.to_string())


def heldout_interaction(nov_col, center=True):
    """LOno held-out: base+social  vs  base+social+social×nov. Return delta(const-vary), wins."""
    lv = leave.copy()
    z = lv["night"].map(reg[nov_col]).astype(float)
    if center:
        z = z - z.mean()
    inter = []
    for s in social:
        c = f"_x_{s}"
        lv[c] = lv[s].astype(float) * z
        inter.append(c)
    Hv, bits_v = lono_all(lv, base + social + inter, CAT)
    common = bits_c.index.intersection(bits_v.index)
    wins = int((bits_v.loc[common] < bits_c.loc[common]).sum())
    return Hc - Hv, wins, len(common)


print("\n== held-out interaction test: does social×<regressor> beat constant-social? ==")
print("regressor            delta(const-vary)   wins/11   (>0 & majority => non-stationary)")
results = {}
for col in ["night_index", "burrow", "wet", "fireworks", "refuge4_present",
            "perturb_onset", "days_since_change"]:
    d, w, n = heldout_interaction(col)
    results[col] = (d, w)
    print(f"  {col:20s} {d:+.5f}          {w}/{n}")

# ---- permutation calibration: random 11-night regressors (multiple-comparison guard) ----
print("\n== permutation null: random night-regressors (how easily does ANY regressor 'win'?) ==")
rng = np.random.default_rng(0)
N_PERM = 300
null_delta = []
null_wins = []
# match structure to a binary regressor with 4 ones (like burrow), most permissive comparison
for _ in range(N_PERM):
    perm_vals = rng.permutation([1.0]*4 + [0.0]*7)
    rmap = pd.Series(perm_vals, index=nights)
    lv = leave.copy()
    z = lv["night"].map(rmap).astype(float); z = z - z.mean()
    inter = []
    for s in social:
        c = f"_x_{s}"; lv[c] = lv[s].astype(float) * z; inter.append(c)
    Hv, bits_v = lono_all(lv, base + social + inter, CAT)
    common = bits_c.index.intersection(bits_v.index)
    null_delta.append(Hc - Hv)
    null_wins.append(int((bits_v.loc[common] < bits_c.loc[common]).sum()))
null_delta = np.array(null_delta); null_wins = np.array(null_wins)
print(f"  random binary-4 regressor: delta mean={null_delta.mean():+.5f} sd={null_delta.std():.5f}")
print(f"    P(delta>0) among random regressors        = {np.mean(null_delta>0):.3f}")
print(f"    P(wins>=6) among random regressors        = {np.mean(null_wins>=6):.3f}")
for col in ["burrow", "wet", "fireworks", "refuge4_present", "perturb_onset"]:
    d, w = results[col]
    pctl = float(np.mean(null_delta >= d))
    print(f"    {col:16s} delta={d:+.5f} exceeds {(1-pctl)*100:4.0f}% of random regressors; wins={w}")

# ---- Spearman: per-night effect vs env indicators (in-sample AND held-out) ----
insample = pd.read_csv(ROOT / "outputs/policy_identifiability_2026-06-28_to_2026-07-08/social_habituation_per_night.csv")
insample = insample.set_index("night")
merged = per.set_index("held_night").join(insample[["insample_social_dbits"]]).join(reg.drop(columns=["night_index"]))

def perm_spear(x, y, n=20000, seed=1):
    x = np.asarray(x, float); y = np.asarray(y, float)
    rho = stats.spearmanr(x, y).correlation
    rr = np.random.default_rng(seed); c = 0
    for _ in range(n):
        if abs(stats.spearmanr(x, rr.permutation(y)).correlation) >= abs(rho)-1e-12:
            c += 1
    return rho, (c+1)/(n+1)

print("\n== Spearman(per-night effect, env indicator), perm-p ==")
for eff in ["insample_social_dbits", "ho_social_dbits"]:
    print(f"  effect = {eff}")
    for col in ["night_index", "burrow", "wet", "fireworks", "days_since_change", "perturb_onset"]:
        rho, p = perm_spear(merged[eff], merged[col])
        print(f"    vs {col:18s} rho={rho:+.3f} perm-p={p:.3f}")

# ---- is the 07-04 in-sample peak distinguishable from noise? bootstrap per-night dbits ----
print("\n== bootstrap per-night IN-SAMPLE social dbits (is 07-04 peak > noise?) ==")
def insample_dbits(sub):
    y = sub["left"].to_numpy(int)
    Xb, nb, cb, mb = cm.build_design(sub, base, CAT, dwell_col=DWELL)
    m0 = cm._fit_logit(Xb, y); p0 = cm._predict(m0, Xb)
    Xs, ns, cs, ms = cm.build_design(sub, base + social, CAT, dwell_col=DWELL)
    m1 = cm._fit_logit(Xs, y); p1 = cm._predict(m1, Xs)
    return cm.bits_bernoulli(y, p0) - cm.bits_bernoulli(y, p1)

for target in ["2026-07-04", "2026-06-28", "2026-07-06"]:
    sub = leave[leave["night"] == target]
    rr = np.random.default_rng(2)
    boots = []
    for _ in range(200):
        bs = sub.sample(len(sub), replace=True, random_state=int(rr.integers(1e9)))
        boots.append(insample_dbits(bs))
    boots = np.array(boots)
    print(f"  {target}: point={insample_dbits(sub):+.4f}  boot mean={boots.mean():+.4f} "
          f"[2.5,97.5]=[{np.percentile(boots,2.5):+.4f},{np.percentile(boots,97.5):+.4f}] "
          f"P(<=0)={np.mean(boots<=0):.2f}")
# ---- fragility: how concentrated is the pooled 0.003 held-out effect? ----
print("\n== fragility of pooled held-out social dbits (mean=%.5f) ==" % per["ho_social_dbits"].mean())
v = per.set_index("held_night")["ho_social_dbits"]
print("  drop-one-night jackknife of the pooled mean:")
for nn in nights:
    print(f"    drop {nn}: pooled mean -> {v.drop(nn).mean():+.5f}")
top2 = v.sort_values(ascending=False).index[:2].tolist()
print(f"  drop the 2 largest nights {top2}: pooled mean -> {v.drop(top2).mean():+.5f}")
print(f"  those 2 nights: {[ (n, round(float(v[n]),4)) for n in top2 ]}")
print("\ndone")
