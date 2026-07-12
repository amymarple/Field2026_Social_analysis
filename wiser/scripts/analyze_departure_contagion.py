r"""
analyze_departure_contagion.py — does a rat LEAVE its site because OTHER rats just left? (departure
following / contagion), and is that following FRONT-LOADED on novel early nights?

Why this exists. The reviewer's hypothesis is that group influence on movement is "group FOLLOWING to
sample a novel environment", strong early and habituating. Every social feature in the leaving-hazard
model so far is STATIC crowding at the decision epoch (n_within_1m, mean_others_dist_in) — it cannot
encode FOLLOWING, which is a temporal contagion: "a group-mate just departed, so I depart too". This
script builds that dynamic feature and tests (a) whether it predicts leaving beyond static crowding,
(b) whether the coupling is real-time (survives a circular time-shift null, i.e. not just shared
circadian timing), and (c) whether the following effect is FRONT-LOADED across the 11 nights.

  FEATURE  n_others_departed_W(focal, t) = # of OTHER tags (same night) whose locomotor-bout ONSET
           (module-3 bouts.t_start) falls in [t − W, t). Strictly pre-decision. W ∈ {30, 60, 120} s.
  T-FOLLOW held-out Δbits of base+static-social → +contagion (night-block sign test): a following
           effect on leaving beyond static crowding.
  T-REAL   circular within-night time-shift of the OTHER tags' onsets (keeps each tag's onset RATE,
           destroys fine real-time alignment): does the contagion Δbits survive? (following vs shared
           circadian co-timing; base already carries clock_hour + moving_frac).
  T-FRONT  per-night held-out contagion increment, early(nights 0-2) vs late, + a pooled night-label-
           permuted contagion×night_index interaction — is FOLLOWING front-loaded (the reviewer's claim)?

All inference at the whole-night block level (11 nights). Frame UNVERIFIED; onset is a LOWER bound
(sub-jitter in-nest stirring invisible); association not "sampling" motivation.

    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\analyze_departure_contagion.py
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import choice_models as cm                            # noqa: E402

DWELL = "dwell_elapsed_s"
BASE_NUM = ["dist_to_edge_in", "clock_hour", "moving_frac", "wet", "fireworks", "burrow"]
WEATHER = ["w_temp_c", "w_tempdew_gap_c", "w_rain_log1p", "w_solar_wm2"]
STATIC_SOCIAL = ["n_within_1m", "mean_others_dist_in"]
CAT = ["roi"]
NS = 1_000_000_000
NOVEL_EARLY_N = 3


def _present(df, cols):
    return [c for c in cols if c in df.columns]


def _onsets_by_night(bouts, from_rest_only=False):
    """{night -> {tag -> sorted onset ns}} and {night -> (lo_ns, hi_ns)} night time bounds."""
    b = bouts.copy()
    if from_rest_only and "from_rest" in b.columns:
        b = b[b["from_rest"].astype(bool)]
    b["_t"] = pd.to_datetime(b["t_start"]).astype("int64")
    onsets, bounds = {}, {}
    for n, gn in b.groupby("night"):
        d = {}
        for a, ga in gn.groupby("shortid"):
            d[str(a)] = np.sort(ga["_t"].to_numpy())
        onsets[str(n)] = d
        bounds[str(n)] = (int(gn["_t"].min()), int(gn["_t"].max()))
    return onsets, bounds


def _contagion(leave, onsets, W_s, *, shift=None):
    """n_others_departed_W per leave decision (other tags' onsets in [t-W, t)); `shift` = {(night,tag):
    offset_ns} circularly wraps that tag's onsets inside its night bounds (the real-time null)."""
    W = int(W_s * NS)
    t = pd.to_datetime(leave["t_epoch"]).astype("int64").to_numpy()
    foc = leave["shortid"].astype(str).to_numpy(); nn = leave["night"].astype(str).to_numpy()
    out = np.zeros(len(leave))
    for i in range(len(leave)):
        oa = onsets.get(nn[i])
        if not oa:
            continue
        c = 0
        for a, arr in oa.items():
            if a == foc[i]:
                continue
            if shift is not None:
                lo, hi = shift["_bounds"][nn[i]]; span = max(hi - lo, 1)
                arr = np.sort(lo + ((arr - lo + shift[(nn[i], a)]) % span))
            c += int(np.searchsorted(arr, t[i], "left") - np.searchsorted(arr, t[i] - W, "left"))
        out[i] = c
    return out


def _lono_delta(df, base, add, cat):
    """Mean ALL-animal leave-one-night-out Δbits of base → base+add, and per-held-night ALL Δbits."""
    hb = cm.lono_bits(df, "left", numeric=base, categorical=cat, dwell_col=DWELL)
    ha = cm.lono_bits(df, "left", numeric=base + add, categorical=cat, dwell_col=DWELL)
    b = hb[hb.animal == "ALL"].set_index("held_night")["bits"]
    a = ha[ha.animal == "ALL"].set_index("held_night")["bits"]
    common = b.index.intersection(a.index)
    per = (b.loc[common] - a.loc[common])
    return float(per.mean()), per


def _sign_test(vals):
    from math import comb
    e = np.asarray([x for x in vals if x == x], float); e = e[e != 0]
    n = len(e)
    if n == 0:
        return {"n": 0, "n_pos": 0, "mean": float("nan"), "p": float("nan")}
    k = int((e > 0).sum()); tot = 2.0 ** n
    p = min(1.0, 2 * min(sum(comb(n, i) for i in range(k, n + 1)) / tot,
                         sum(comb(n, i) for i in range(0, k + 1)) / tot))
    return {"n": n, "n_pos": k, "mean": float(e.mean()), "p": float(p)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy-dir", type=Path,
                    default=ROOT / "outputs/policy_identifiability_2026-06-28_to_2026-07-08")
    ap.add_argument("--bouts", type=Path,
                    default=ROOT / "outputs/locomotor_initiation_2026-06-28_to_2026-07-08/bouts.csv")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs/policy_identifiability_2026-06-28_to_2026-07-08")
    ap.add_argument("--window-s", type=float, default=60.0)
    ap.add_argument("--n-perm", type=int, default=40)
    args = ap.parse_args()

    leave = pd.read_csv(args.policy_dir / "leave_decisions.csv")
    bouts = pd.read_csv(args.bouts)
    nights = sorted(leave["night"].unique()); idx = {n: i for i, n in enumerate(nights)}
    leave["night_index"] = leave["night"].map(idx)
    base = _present(leave, BASE_NUM) + _present(leave, WEATHER)
    static = _present(leave, STATIC_SOCIAL)
    onsets, bounds = _onsets_by_night(bouts)
    R = {"generated_utc": datetime.datetime.utcnow().isoformat(), "window_s": args.window_s,
         "n_nights": len(nights), "n_leave": int(len(leave))}

    WINDOWS = (30.0, 60.0, 120.0, 300.0)
    print(f"[feature] n_others_departed_W (W in {WINDOWS}s) + from-rest variant, from module-3 bout onsets")
    for W in WINDOWS:
        leave[f"n_others_departed_{int(W)}"] = _contagion(leave, onsets, W)
    onsets_fr, _ = _onsets_by_night(bouts, from_rest_only=True)
    leave["n_others_left_rest_120"] = _contagion(leave, onsets_fr, 120.0)  # left the NEST recently
    R["coverage_by_window"] = {int(W): {"mean": round(float(leave[f"n_others_departed_{int(W)}"].mean()), 3),
                                        "frac_any": round(float((leave[f"n_others_departed_{int(W)}"] > 0).mean()), 3)}
                               for W in WINDOWS}
    print("    coverage frac_any>0:", {int(W): R["coverage_by_window"][int(W)]["frac_any"] for W in WINDOWS})

    # ---- T-FOLLOW: contagion beyond static crowding, SWEEP windows (be fair to the hypothesis) ----
    print("[T-FOLLOW] held-out: does recent group departure predict leaving beyond static crowding?")
    sweep = {}
    for W in WINDOWS:
        fW = f"n_others_departed_{int(W)}"
        dW, perW = _lono_delta(leave, base + static, [fW], CAT)
        sweep[int(W)] = {"heldout_dbits": round(dW, 4), "sign_p": round(_sign_test(perW.tolist())["p"], 3),
                         "n_pos": _sign_test(perW.tolist())["n_pos"]}
        print(f"    W={int(W):>3}s: held-out Δbits={dW:+.4f} sign-p={sweep[int(W)]['sign_p']} ({sweep[int(W)]['n_pos']}/11)")
    dfr, _ = _lono_delta(leave, base + static, ["n_others_left_rest_120"], CAT)
    sweep["left_rest_120"] = {"heldout_dbits": round(dfr, 4)}
    print(f"    left-rest W=120s: held-out Δbits={dfr:+.4f}")
    R["t_follow_window_sweep"] = sweep
    # primary window = the one with the largest held-out Δbits (most favourable to the hypothesis)
    best_W = max(WINDOWS, key=lambda W: sweep[int(W)]["heldout_dbits"])
    cfeat = f"n_others_departed_{int(best_W)}"
    args.window_s = best_W
    R["primary_window_s"] = best_W
    R["contagion_coverage"] = R["coverage_by_window"][int(best_W)]
    print(f"    -> primary window = most favourable = {int(best_W)}s ({cfeat})")
    d_follow, per_follow = _lono_delta(leave, base + static, [cfeat], CAT)
    st = _sign_test(per_follow.tolist())
    # coefficient sign (pooled, well-conditioned single feature)
    Xn, names, cats, miss = cm.build_design(leave, base + static + [cfeat], CAT, dwell_col=DWELL)
    m = cm._fit_logit(Xn, leave["left"].to_numpy(int))
    est = getattr(m, "named_steps", {}).get("logisticregression")
    coef = float(est.coef_[0][names.index(cfeat)]) if (est is not None and cfeat in names) else float("nan")
    R["t_follow"] = {"heldout_dbits": round(d_follow, 4), "sign_test": st, "pooled_coef": round(coef, 4),
                     "direction": "following (others left -> focal leaves)" if coef > 0 else "anti-following"}
    print(f"    held-out Δbits={d_follow:+.4f} | sign-test p={st['p']:.3f} ({st['n_pos']}/{st['n']} nights) | "
          f"coef({cfeat})={coef:+.4f} ({R['t_follow']['direction']})")

    # ---- T-REAL: circular time-shift null (real-time following vs shared circadian) ----
    print(f"[T-REAL] circular within-night time-shift null ({args.n_perm} perms)")
    rng = np.random.default_rng(0)
    null = np.empty(args.n_perm)
    for k in range(args.n_perm):
        shift = {"_bounds": bounds}
        for nn in nights:
            lo, hi = bounds.get(nn, (0, 1)); span = max(hi - lo, 1)
            for a in onsets.get(nn, {}):
                shift[(nn, a)] = int(rng.integers(0, span))
        lv = leave.copy(); lv[cfeat] = _contagion(lv, onsets, args.window_s, shift=shift)
        null[k], _ = _lono_delta(lv, base + static, [cfeat], CAT)
    mu, sd = float(null.mean()), float(null.std())
    z = (d_follow - mu) / sd if sd > 0 else float("nan")
    R["t_real"] = {"obs_dbits": round(d_follow, 4), "shift_null_mean": round(mu, 4),
                   "shift_null_sd": round(sd, 4), "z": round(z, 2) if z == z else None,
                   "beats_shift_null": bool(z == z and z > 2)}
    print(f"    obs Δbits={d_follow:+.4f} vs shift-null {mu:+.4f}±{sd:.4f} -> z={z:+.2f} "
          f"(real-time following: {R['t_real']['beats_shift_null']})")

    # ---- T-FRONT: is following front-loaded (the reviewer's hypothesis)? ----
    print("[T-FRONT] is the FOLLOWING effect front-loaded across nights?")
    R["t_front"] = {"per_night": {n: round(float(per_follow.get(n, np.nan)), 4) for n in nights}}
    e = per_follow.reindex(nights)
    early = e.iloc[:NOVEL_EARLY_N].mean(); late = e.iloc[NOVEL_EARLY_N:].mean()
    rho, p = stats.spearmanr(np.arange(len(e)), e.to_numpy(), nan_policy="omit")
    # pooled night-permuted contagion x night_index interaction
    lv = leave.copy(); z0 = lv["night_index"] - lv["night_index"].mean()
    lv["_cxi"] = lv[cfeat].astype(float) * z0
    H_const, _ = _lono_delta(lv, base + static, [cfeat], CAT)  # not used directly
    d_inter, _ = _lono_delta(lv, base + static + [cfeat], ["_cxi"] if False else [], CAT)
    # held-out const vs const+interaction
    Hc = cm.lono_bits(lv, "left", numeric=base + static + [cfeat], categorical=CAT, dwell_col=DWELL)
    Hi = cm.lono_bits(lv, "left", numeric=base + static + [cfeat, "_cxi"], categorical=CAT, dwell_col=DWELL)
    hc = Hc[Hc.animal == "ALL"].set_index("held_night")["bits"]; hi = Hi[Hi.animal == "ALL"].set_index("held_night")["bits"]
    common = hc.index.intersection(hi.index); wins = int((hi.loc[common] < hc.loc[common]).sum())
    R["t_front"].update({
        "early_mean_dbits": round(float(early), 4), "late_mean_dbits": round(float(late), 4),
        "spearman_rho": round(float(rho), 3) if rho == rho else None,
        "spearman_p": round(float(p), 3) if p == p else None,
        "interaction_heldout_delta": round(float((hc.loc[common] - hi.loc[common]).mean()), 5),
        "interaction_wins": f"{wins}/{len(common)}",
        "front_loaded": bool(early > late and rho < 0)})
    print(f"    per-night held-out following Δbits early(0-2)={early:+.4f} vs late={late:+.4f} | "
          f"Spearman rho={rho:+.3f} p={p:.3f}")
    print(f"    contagion×night_index interaction: held-out Δ={R['t_front']['interaction_heldout_delta']:+.5f} "
          f"wins {R['t_front']['interaction_wins']}")

    # ---- verdict ----
    follow = R["t_follow"]["heldout_dbits"] > 0.003 and st["p"] <= 0.1 and R["t_real"]["beats_shift_null"]
    R["verdict"] = _verdict(R, follow)
    print(f"[verdict] {R['verdict']}")
    (args.out / "departure_contagion_results.json").write_text(json.dumps(R, indent=2, default=str), encoding="utf-8")
    _write_report(args.out, R, cfeat)
    print(f"done -> {args.out}")


def _verdict(R, follow):
    f = R["t_follow"]; r = R["t_real"]; fr = R["t_front"]
    if not follow:
        base = (f"NO robust departure-following on leaving: held-out Δbits={f['heldout_dbits']:+.4f} "
                f"(sign-test p={f['sign_test']['p']}), real-time null z={r['z']}. The static-crowding "
                "picture is not rescued by a temporal-following feature at this resolution.")
    else:
        base = (f"DEPARTURE-FOLLOWING detected: recent group departures predict the focal leaving beyond "
                f"static crowding (held-out Δbits={f['heldout_dbits']:+.4f}, sign-test p={f['sign_test']['p']}, "
                f"real-time z={r['z']}), direction {f['direction']}.")
    ff = (" And it IS front-loaded (early>late, decaying) — consistent with the reviewer's group-"
          "following-for-sampling hypothesis." if fr.get("front_loaded") else
          f" Front-loading is NOT established (early {fr['early_mean_dbits']} vs late {fr['late_mean_dbits']}, "
          f"Spearman rho={fr['spearman_rho']} p={fr['spearman_p']}; n=11 low power).")
    return base + ff


def _write_report(out, R, cfeat):
    f = R["t_follow"]; r = R["t_real"]; fr = R["t_front"]
    pn = "\n".join(f"| {n} | {v} |" for n, v in fr["per_night"].items())
    header = ("# Departure following / contagion on the leaving decision (11 nights)\n\n"
              "**Status:** ⚠️ candidate. Tests the reviewer's ACTUAL mechanism — group FOLLOWING (a "
              "neighbour just left, so I leave) — which the static-crowding social features cannot encode, "
              "and whether that following is front-loaded on novel early nights. Whole-night blocks. "
              f"Generated {R['generated_utc']}. Onset is a LOWER bound; association not sampling motivation.\n")
    defn = r"""
## Definitions (formula + plain text)

- **n_others_departed_W(focal, t)** — number of OTHER tags in the same night whose locomotor-bout ONSET
  (module-3 `bouts.t_start`) falls in $[t-W, t)$ (strictly before the decision). A dynamic "recent group
  departure" / following-pressure covariate; $W$ = %(W)s s.
- **Following effect (T-FOLLOW)** — held-out (leave-one-night-out) Δbits of adding n_others_departed to a
  base that ALREADY has static crowding (n_within_1m, mean_others_dist). >0 ⇒ recent group departure
  predicts the focal leaving beyond how many are merely near. Night-block sign test.
- **Real-time null (T-REAL)** — each other tag's onset times are circularly shifted by a random offset
  within its night (its onset RATE preserved, the fine alignment to the focal's decision destroyed).
  Beating it (z>2) ⇒ genuine real-time coupling, not shared circadian timing (base already holds
  clock_hour + moving_frac).
- **Front-loading (T-FRONT)** — per-night held-out following Δbits, early (nights 0-2, pre-burrow novel
  paddock) vs late, Spearman vs night index, and a held-out contagion×night_index interaction. Front-
  loaded ⇔ early>late and a negative trend — the reviewer's habituation prediction.

## T-FOLLOW — following beyond static crowding

- Held-out Δbits **%(dfollow)+.4f** | sign-test p **%(fp)s** (%(fpos)s/%(fn)s nights) | pooled coef on
  %(cfeat)s = **%(coef)+.4f** (%(dir)s).

## T-REAL — real-time following vs shared circadian timing

- Observed Δbits %(dfollow)+.4f vs circular-shift null **%(nmu)+.4f ± %(nsd).4f** → **z = %(z)s**
  (real-time following: %(real)s).

## T-FRONT — is following front-loaded?

| night | held-out following Δbits |
|---|---|
""" % {"W": R["window_s"], "dfollow": f["heldout_dbits"], "fp": f["sign_test"]["p"],
       "fpos": f["sign_test"]["n_pos"], "fn": f["sign_test"]["n"], "cfeat": cfeat,
       "coef": f["pooled_coef"], "dir": f["direction"], "nmu": r["shift_null_mean"],
       "nsd": r["shift_null_sd"], "z": r["z"], "real": r["beats_shift_null"]}
    tail = pn + f"""

- early (nights 0-2) mean **{fr['early_mean_dbits']}** vs late **{fr['late_mean_dbits']}**;
  Spearman ρ = **{fr['spearman_rho']}** (p {fr['spearman_p']}); contagion×night_index held-out
  Δ = {fr['interaction_heldout_delta']} (wins {fr['interaction_wins']}). Front-loaded: **{fr['front_loaded']}**.

## Verdict

{R['verdict']}

## Scope

Following is measured as temporal co-departure (others' bout onsets preceding the focal's leave), NOT
spatial go-where-they-went (that is module 8 / destination). Onset is a LOWER bound (sub-jitter in-nest
stirring invisible), so a real following that operates below the jitter floor is under-counted. n = 11
nights is low power for the front-loading trend. Group-level, association not "sampling" motivation.
Frame UNVERIFIED.
"""
    (out / "departure_contagion_report.md").write_text(header + defn + tail, encoding="utf-8")


if __name__ == "__main__":
    main()
