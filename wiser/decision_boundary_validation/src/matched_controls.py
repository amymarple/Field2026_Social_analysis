"""Analysis 3 — matched-control reorientation test (H1).

Is heading change larger across pauses than at matched continuous-movement points, after
COARSENED-EXACT-MATCHING on animal, night, clock-hour, ROI, pre-speed, boundary-distance?
Raw 64 vs 16 deg is insufficient (pause locations/states differ). Bootstrap CIs; per-animal/night;
sensitivity to matching set, pause-duration, and heading window. Pure numpy/pandas.
"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve(); ROOT = HERE.parent.parent
TAB = ROOT / "tables"; PLT = ROOT / "plots"; PLT.mkdir(exist_ok=True)
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
rng = np.random.default_rng(0)
cb = pd.read_csv(TAB / "candidate_boundaries.csv")

TURN = "turn_deg_1.0"
cb = cb[cb["head_pre_ok"] & cb["head_post_ok"] & np.isfinite(cb[TURN])].copy()
cb["sp_bin"] = pd.cut(cb["speed_pre"], [0, 15, 20, 25, 30, 40, 200]).astype(str)
cb["db_bin"] = pd.cut(cb["dist_boundary_in"], [-1e9, 12, 30, 60, 120, 1e9]).astype(str)
MATCH = ["shortid", "night", "clock_hour", "roi", "sp_bin", "db_bin"]

def matched_contrast(df, group_col="kind", pos="pause", neg="continuous",
                     match=MATCH, cs=(30, 60, 90, 135)):
    """Vectorized CEM: per covariate stratum containing BOTH pos and neg, weight by
    min(n_pos,n_neg); aggregate mean turn and P(turn>c). No Python per-stratum loop."""
    d = df[df[group_col].isin([pos, neg])].copy()
    d["_s"] = d.groupby(match, sort=False).ngroup()
    ind = {c: (d[TURN].to_numpy() > c).astype(float) for c in cs}
    for c in cs:
        d[f"_i{c}"] = ind[c]
    agg = d.groupby(["_s", group_col]).agg(m=(TURN, "mean"), n=(TURN, "size"),
                                           **{f"p{c}": (f"_i{c}", "mean") for c in cs})
    piv = agg.unstack(group_col)
    both = piv["n"][pos].notna() & piv["n"][neg].notna()
    piv = piv[both]
    if len(piv) == 0:
        return None
    wgt = np.minimum(piv["n"][pos], piv["n"][neg]).to_numpy(); wtot = wgt.sum()
    res = {"n_strata": int(len(piv)), "n_pos": int(d[d[group_col] == pos].shape[0]),
           "n_neg": int(d[d[group_col] == neg].shape[0]),
           "mean_turn_pos": round(float((wgt*piv["m"][pos]).sum()/wtot), 1),
           "mean_turn_neg": round(float((wgt*piv["m"][neg]).sum()/wtot), 1)}
    res["mean_turn_diff"] = round(res["mean_turn_pos"] - res["mean_turn_neg"], 1)
    for c in cs:
        pp = float((wgt*piv[f"p{c}"][pos]).sum()/wtot); qq = float((wgt*piv[f"p{c}"][neg]).sum()/wtot)
        res[f"P>{c}_pos"] = round(pp, 3); res[f"P>{c}_neg"] = round(qq, 3)
        res[f"riskratio>{c}"] = round(pp/max(qq, 1e-6), 2)
    return res

base = matched_contrast(cb)
# bootstrap CI on the matched mean-turn difference (resample events within pos/neg)
def boot_diff(df, n=300):
    d = df[df.kind.isin(["pause", "continuous"])]
    diffs = []
    for _ in range(n):
        s = d.sample(len(d), replace=True, random_state=int(rng.integers(1e9)))
        r = matched_contrast(s)
        if r:
            diffs.append(r["mean_turn_diff"])
    return np.percentile(diffs, [2.5, 50, 97.5]) if diffs else [np.nan]*3
ci = boot_diff(cb)
base["bootstrap_diff_ci95"] = [round(float(x), 1) for x in ci]

# per-animal / per-night
per = []
for k, sub in list(cb.groupby("shortid")) + list(cb.groupby("night")):
    r = matched_contrast(sub)
    if r:
        per.append({"group": str(k), "mean_turn_pos": r["mean_turn_pos"],
                    "mean_turn_neg": r["mean_turn_neg"], "diff": r["mean_turn_diff"],
                    "riskratio>90": r.get("riskratio>90"), "n_pos": r["n_pos"]})
perdf = pd.DataFrame(per)

# sensitivity: matching set, pause-duration floor, heading window
sens = []
sens.append({"variant": "full_match", **{k: base[k] for k in ["mean_turn_diff", "riskratio>90"]}})
for drop in MATCH:
    r = matched_contrast(cb, match=[m for m in MATCH if m != drop])
    sens.append({"variant": f"drop_{drop}", "mean_turn_diff": r["mean_turn_diff"], "riskratio>90": r["riskratio>90"]})
for pdur in [0.5, 1.0, 2.0]:
    sub = cb[(cb.kind != "pause") | (cb.pause_dur_s >= pdur)]
    r = matched_contrast(sub)
    sens.append({"variant": f"pause_dur>={pdur}s", "mean_turn_diff": r["mean_turn_diff"], "riskratio>90": r["riskratio>90"]})
for tw in ["turn_deg_0.5", "turn_deg_2.0"]:
    old = TURN; TURN = tw
    d2 = cb[np.isfinite(cb[tw])]
    r = matched_contrast(d2); TURN = old
    sens.append({"variant": f"window_{tw}", "mean_turn_diff": r["mean_turn_diff"], "riskratio>90": r["riskratio>90"]})
# heading_cp vs continuous too
hcp = matched_contrast(cb, pos="heading_cp")

out = {"pause_vs_continuous_matched": base,
       "heading_cp_vs_continuous_matched": hcp,
       "raw_unmatched": {"mean_turn_pause": round(float(cb[cb.kind=="pause"][TURN].mean()), 1),
                         "mean_turn_continuous": round(float(cb[cb.kind=="continuous"][TURN].mean()), 1)}}
(TAB / "boundary_matched_controls.json").write_text(json.dumps(out, indent=2, default=str))
perdf.to_csv(TAB / "boundary_matched_controls.csv", index=False)
pd.DataFrame(sens).to_csv(TAB / "boundary_matched_sensitivity.csv", index=False)
print(json.dumps(out, indent=2, default=str))
print("\nSENSITIVITY:"); print(pd.DataFrame(sens).to_string(index=False))
print("\nPER GROUP (head):"); print(perdf.head(20).to_string(index=False))

# plot
fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
cs = [30, 60, 90, 135]
ax[0].plot(cs, [base[f"P>{c}_pos"] for c in cs], "-o", label="pause (matched)")
ax[0].plot(cs, [base[f"P>{c}_neg"] for c in cs], "-s", label="continuous (matched)")
ax[0].set_xlabel("turn threshold c (deg)"); ax[0].set_ylabel("P(|Δheading| > c)")
ax[0].set_title(f"Matched reorientation: pause vs continuous\ndiff {base['mean_turn_diff']}° CI{base['bootstrap_diff_ci95']}")
ax[0].legend(fontsize=8)
ax[1].scatter(perdf["mean_turn_neg"], perdf["mean_turn_pos"], s=20)
lim = [0, max(perdf[["mean_turn_pos", "mean_turn_neg"]].max())+10]
ax[1].plot(lim, lim, "k--"); ax[1].set_xlabel("continuous mean turn (deg)"); ax[1].set_ylabel("pause mean turn (deg)")
ax[1].set_title("Per animal/night — pause above the diagonal?")
fig.tight_layout(); fig.savefig(PLT / "boundary_turn_angle_matched.png", dpi=120); plt.close(fig)
print("[done] matched controls")
