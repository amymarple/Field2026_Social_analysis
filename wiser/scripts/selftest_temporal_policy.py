r"""
selftest_temporal_policy.py — offline PASS/FAIL for the time-varying-rule tests. Asserts the
pipeline CERTIFIES a genuinely hour-varying conditional rule (that transfers across nights) and
REJECTS a marginal-only difference (same rule, different state occupancy across hours).

    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\selftest_temporal_policy.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import temporal_policy as tp                          # noqa: E402

FAILS = []
def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)

def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))

# UTC clock hours that map (via add_hour_block, -4h) to each local block
BLOCK_UTC = {"early": [1, 2, 3], "mid": [4, 5, 6], "late": [7, 8]}
NIGHTS = [f"2026-06-{d:02d}" for d in range(28, 28 + 6)]


def gen(rng, *, social_coef_by_block, crowd_mean_by_block, n_per_cell=1400):
    """Leave-table rows. `left ~ sigmoid(intercept + coef(block)*crowd + 0.2*dwell_epoch)`.
    social_coef_by_block sets the CONDITIONAL rule per block; crowd_mean_by_block sets the STATE
    (marginal crowding) per block. Both are controllable independently."""
    rows = []
    for night in NIGHTS:
        for blk, utcs in BLOCK_UTC.items():
            for _ in range(n_per_cell):
                ch = rng.choice(utcs)
                crowd = max(0, rng.poisson(crowd_mean_by_block[blk]))
                dwell_e = rng.integers(0, 8)
                p = sigmoid(-2.0 + social_coef_by_block[blk] * crowd + 0.2 * dwell_e)
                rows.append({"shortid": f"A{rng.integers(0,5)}", "night": night, "clock_hour": int(ch),
                             "roi": rng.choice(["house_1", "refuge_1"]), "dwell_elapsed_s": dwell_e * 5.0,
                             "is_house": 1, "is_refuge": 0, "dist_to_edge_in": 100.0, "moving_frac": 0.0,
                             "wet": 0, "fireworks": 0, "burrow": 0, "w_temp_c": 22.0, "w_tempdew_gap_c": 3.0,
                             "w_rain_log1p": 0.0, "w_solar_wm2": 0.0, "n_within_1m": float(crowd),
                             "mean_others_dist_in": 60.0, "left": int(rng.random() < p)})
    return pd.DataFrame(rows)


print("Temporal-rule selftest")
rng = np.random.default_rng(0)

# Scenario T1 — GENUINE hour-varying rule (social coef differs by block, same every night)
df1 = gen(rng, social_coef_by_block={"early": -0.2, "mid": -0.9, "late": -1.8},
          crowd_mean_by_block={"early": 1.5, "mid": 1.5, "late": 1.5})     # SAME state dist
g1 = tp.hour_varying_gain(df1)
h1 = tp.hour_label_permutation_null(df1, n_perm=20)
check("T1 genuine hour-varying rule -> certified (held-out gain + hour-label null z>2)",
      g1["dbits"] > 0.003 and h1["z"] is not None and h1["z"] > 2,
      f"held-out dbits={g1['dbits']:.4f}, hour-label z={h1['z']}")

# Scenario T2 — MARGINAL-ONLY difference (same rule everywhere, different crowding by block)
df2 = gen(rng, social_coef_by_block={"early": -1.0, "mid": -1.0, "late": -1.0},   # SAME rule
          crowd_mean_by_block={"early": 0.3, "mid": 1.5, "late": 3.0})            # DIFFERENT state
g2 = tp.hour_varying_gain(df2)
# marginal state genuinely differs by block (the confound)...
sc = tp.state_vs_conditional(df2)
marg_differs = sc["median_crowd_within1m"].nunique() > 1
check("T2 marginal-only state difference -> NOT called a policy change (near-zero held-out gain)",
      g2["dbits"] < 0.003 and marg_differs,
      f"held-out dbits={g2['dbits']:.4f} (state crowd varies by block: {marg_differs})")

print()
if FAILS:
    print(f"FAIL — {FAILS}"); sys.exit(1)
print("PASS — temporal-rule test certifies genuine hour-varying rules, rejects marginal-only differences")
sys.exit(0)
