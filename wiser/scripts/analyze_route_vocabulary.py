r"""
analyze_route_vocabulary.py — Stage 1 falsification of the "discrete shared route vocabulary".

Phase B showed route RECURRENCE (~97%) and SHARED corridors, but recurrence is not the stronger
claim that continuous 2-D movement compresses into a finite, shared, OUT-OF-SAMPLE dictionary of
route prototypes. This driver tries to FALSIFY that claim with held-out compression, cross-animal
generalisation, endpoint-vs-shape decomposition, a geometry-preserving null, and first-night closure,
then emits an interim verdict A/B/C/D.

Frame is the WISER native, UNVERIFIED inch frame -> topological / relative language only, never a
metric or directional route claim (Module 11 BLOCKED in configs/behavioral_policy_modules.yaml). The
verdict ceiling is B/C unless every discreteness + generalisation criterion holds.

Read-only on the transferred backups. Reuses the Phase-B load/clean/window/cutoff path and
ts.extract_route_bouts (route_bouts.csv stores only endpoints, so paths are regenerated in-memory).
Runs under anaconda3 python (needs scipy + sklearn):

    KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1 \
      C:/Users/Cornell/anaconda3/python.exe scripts/analyze_route_vocabulary.py
    ... --max-nights 3    # smoke
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import wiser_analysis_utils as w              # noqa: E402
import time_utils                             # noqa: E402
import trajectory_stereotypy as ts            # noqa: E402
import analyze_trajectory_stereotypy as pa    # noqa: E402
import route_vocabulary as rv                 # noqa: E402
import trajectory_units as tu                 # noqa: E402

DEFAULT_OUT = PROJECT_ROOT / "outputs" / "route_vocabulary_validation_2026-06-28_to_2026-07-10"
COV_THR = (10.5, 21.0, 42.0)            # coverage thresholds (in): 1.5x, 3x, 6x jitter floor
KS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]


# ===========================================================================
# analyses (each: pure over paths + aligned bouts metadata; returns table + summary)
# ===========================================================================

def a0_support(bouts: pd.DataFrame, *, theta: float, endpoint_bin: float) -> dict:
    """A0 — decision-table support / kill-gate. Counts that gate whether the cross-night and
    cross-animal comparisons are even estimable."""
    per_an = bouts.groupby("shortid").size()
    per_annight = bouts.groupby(["shortid", "night"]).size()
    return {
        "n_bouts": int(len(bouts)),
        "n_animals": int(bouts["shortid"].nunique()),
        "n_nights": int(bouts["night"].nunique()),
        "median_bouts_per_animal": float(per_an.median()) if len(per_an) else 0.0,
        "median_bouts_per_animal_night": float(per_annight.median()) if len(per_annight) else 0.0,
        "min_bouts_per_animal": int(per_an.min()) if len(per_an) else 0,
    }


def a1_temporal_holdout(paths, bouts, nights, *, theta) -> pd.DataFrame:
    """A1 — cumulative-training temporal held-out dictionary. Learn a leader dictionary on the first
    c nights ONLY, freeze, assign all LATER nights; also the immediately-next night (acquisition)."""
    rows = []
    night_arr = bouts["night"].to_numpy()
    for c in range(1, len(nights)):
        tr = np.isin(night_arr, nights[:c])
        te = np.isin(night_arr, nights[c:])
        if tr.sum() < 3 or te.sum() < 3:
            continue
        protos, info = rv.learn_leader_dictionary(paths[tr], theta=theta)
        _, res = rv.assign(paths[te], protos)
        es = rv.error_summary(res, theta=theta, thresholds=COV_THR)
        # acquisition: novelty on JUST the next night
        nn = night_arr == nights[c]
        _, res_next = rv.assign(paths[nn], protos)
        rows.append({"train_nights": c, "train_last": nights[c - 1], "K": info["K"],
                     "n_train": int(tr.sum()), "n_test": int(te.sum()),
                     "mean_resid_in": round(es["mean_resid_in"], 2),
                     "cov_21in": round(es["cov_21in"], 3), "cov_42in": round(es["cov_42in"], 3),
                     "novelty_frac": round(es["novelty_frac"], 3),
                     "novelty_next_night": round(rv.novelty_frac(res_next, theta), 3)})
    return pd.DataFrame(rows)


def a2_loao(paths, bouts, *, theta, seed=0, n_seeds=5) -> pd.DataFrame:
    """A2 — leave-one-animal-out shared-dictionary test. Held-out set = each animal's LAST night;
    compare a dictionary from OTHER animals (count-matched) vs the animal's OWN earlier nights vs a
    geometry-preserving null dictionary vs endpoint-only. Leader dicts (θ-matched resolution)."""
    night_arr = bouts["night"].to_numpy()
    sid = bouts["shortid"].to_numpy().astype(str)
    rows = []
    for a in sorted(set(sid)):
        a_nights = sorted(bouts.loc[sid == a, "night"].unique())
        if len(a_nights) < 2:
            continue
        hold = a_nights[-1]
        test_m = (sid == a) & (night_arr == hold)                  # held-out night
        own_tr = (sid == a) & np.isin(night_arr, a_nights[:-1])     # own earlier nights
        n_own = int(own_tr.sum())
        if test_m.sum() < 2 or n_own < 3:
            continue
        # EXCLUDE the held-out night from the OTHER-animal pool: same-night social-following routes are
        # near-duplicates and would leak an optimistic bias into E_other (adversarial-review fix).
        other_idx = np.where((sid != a) & (night_arr != hold))[0]
        if len(other_idx) < n_own:
            continue
        p_own, i_own = rv.learn_leader_dictionary(paths[own_tr], theta=theta)
        _, e_own = rv.assign(paths[test_m], p_own)
        # count-matched other-animal + geometry-null dictionaries, averaged over n_seeds subsamples to
        # damp single-draw Monte-Carlo noise (decisive margins are ~1-2 in).
        eo, en, ko = [], [], []
        for s in range(n_seeds):
            rng = np.random.default_rng(seed + s)
            sub = rng.choice(other_idx, size=n_own, replace=False)
            p_o, i_o = rv.learn_leader_dictionary(paths[sub], theta=theta)
            p_n, _ = rv.learn_leader_dictionary(rv.brownian_bridge_null(paths[sub], seed=seed + s), theta=theta)
            eo.append(float(rv.assign(paths[test_m], p_o)[1].mean()))
            en.append(float(rv.assign(paths[test_m], p_n)[1].mean()))
            ko.append(i_o["K"])
        e_end = rv.resid_of(paths[test_m], rv.endpoint_line_paths(paths[test_m]))
        rows.append({"animal": a, "held_out_night": hold, "n_test": int(test_m.sum()),
                     "n_train_matched": n_own, "K_other": int(round(float(np.mean(ko)))), "K_own": i_own["K"],
                     "E_other_in": round(float(np.mean(eo)), 2), "E_other_sd": round(float(np.std(eo)), 2),
                     "E_own_in": round(float(np.mean(e_own)), 2),
                     "E_null_in": round(float(np.mean(en)), 2),
                     "E_endpoint_in": round(float(np.mean(e_end)), 2)})
    return pd.DataFrame(rows)


def a3_compression(paths, bouts, nights, *, sigma_in, bits_per_param, L) -> pd.DataFrame:
    """A3 — compression / model selection. Temporal split (early train / later test). For each K:
    K-means dictionary held-out error + MDL/BIC; PCA continuous competitor at matched budget."""
    night_arr = bouts["night"].to_numpy()
    k0 = max(1, len(nights) // 2)
    tr = np.isin(night_arr, nights[:k0]); te = np.isin(night_arr, nights[k0:])
    rows = []
    n_te = int(te.sum())
    if tr.sum() < 4 or n_te < 4:
        return pd.DataFrame(rows)
    for K in KS:
        if K > tr.sum():
            break
        protos, info = rv.kmeans_dictionary(paths[tr], K=K)
        _, res, sse = rv.assign_full(paths[te], protos)
        mdl = rv.mdl_bits(n_te, info["K"], L, sse, sigma_in=sigma_in, bits_per_param=bits_per_param)
        bic = rv.bic_gaussian(n_te, info["K"] * 2 * L, L, sse)
        # continuous competitor: PCA at M≈K, compared by MDL (per-path coefficient coding), NOT by
        # reconstruction error (K means always span a (K−1)-affine subspace, so PCA ties by construction).
        res_pca, pinfo = rv.pca_reconstruct(paths[tr], paths[te], M=K)
        pmdl = rv.pca_mdl_bits(n_te, pinfo["M"], L, pinfo["sse"], sigma_in=sigma_in,
                               bits_per_param=bits_per_param, bits_per_coef=bits_per_param)
        rows.append({"K": info["K"], "mean_resid_in": round(float(res.mean()), 2),
                     "cov_21in": round(float(np.mean(res <= 21.0)), 3),
                     "mdl_total_bits": round(mdl["total_bits"], 0),
                     "mdl_bits_per_path": round(mdl["bits_per_path"], 1),
                     "bic": round(bic, 0),
                     "pca_M": pinfo["M"], "pca_resid_in": round(float(res_pca.mean()), 2),
                     "pca_mdl_total_bits": round(pmdl["total_bits"], 0)})
    return pd.DataFrame(rows)


def a4_endpoint(paths, bouts, nights, *, theta, endpoint_bin, seed=0) -> dict:
    """A4 — endpoint vs path-shape decomposition. Two questions kept separate:
    (1) absolute-frame ladder (how much do endpoints alone explain?): global mean, the endpoint chord
        (straight line between each route's own endpoints), endpoint-grid-mean, endpoint-multi, route
        dictionary; and
    (2) the FAIR reusable-shape test in the endpoint-registered (pose-normalized) frame — factoring out
        translation+rotation so endpoints are removed and only path SHAPE remains (rv.shape_beyond_
        endpoints_test). This replaces the earlier 42-in-grid absolute-location test, which was biased
        against shape (unseen strata fell back to the chord). Endpoints vs shape are reported as ERROR
        REDUCTIONS (inches), so no quantity is a construction tautology."""
    night_arr = bouts["night"].to_numpy()
    k0 = max(1, len(nights) // 2)
    tr = np.isin(night_arr, nights[:k0]); te = np.isin(night_arr, nights[k0:])
    if tr.sum() < 4 or te.sum() < 4:
        return {}
    ptr, pte = paths[tr], paths[te]
    e_global = float(rv.resid_of(pte, np.repeat(rv.global_mean_prototype(ptr), len(pte), axis=0)).mean())
    e_chord = float(rv.resid_of(pte, rv.endpoint_line_paths(pte)).mean())     # endpoint-only floor
    e_endpt, novel = rv.endpoint_conditioned_recon(ptr, pte, bin_in=endpoint_bin)
    e_endpt = float(e_endpt.mean())
    e_multi, nproto = rv.endpoint_conditioned_multi(ptr, pte, bin_in=endpoint_bin, theta=theta)
    e_multi = float(e_multi.mean())
    p_dict, dinfo = rv.learn_leader_dictionary(ptr, theta=theta)
    _, e_dict = rv.assign(pte, p_dict); e_dict = float(e_dict.mean())
    # FAIR reusable-shape test (endpoint-registered / pose-normalized) — decides shape_beyond_endpoints.
    pn = rv.shape_beyond_endpoints_test(ptr, pte, theta=theta, seed=seed)
    # endpoints vs reusable shape as ERROR REDUCTIONS: endpoints in the absolute frame (global->chord),
    # reusable shape in the pose-normalized frame (straight-segment -> shape dictionary). Non-tautological.
    endpoint_reduction = e_global - e_chord
    shape_reduction = max(0.0, pn["E_pn_straight_in"] - pn["E_pn_shapedict_in"])
    endpoint_share = endpoint_reduction / max(endpoint_reduction + shape_reduction, 1e-9)
    return {"E_global_in": round(e_global, 2), "E_chord_in": round(e_chord, 2),
            "E_endpoint_mean_in": round(e_endpt, 2), "E_endpoint_multi_in": round(e_multi, 2),
            "E_route_dict_in": round(e_dict, 2), "K_dict": dinfo["K"],
            "endpoint_novel_strata": int(novel), "mean_protos_per_stratum": round(nproto, 2),
            "chord_beats_dict": bool(e_chord < e_dict),
            "endpoint_reduction_in": round(float(endpoint_reduction), 2),
            "shape_reduction_in": round(float(shape_reduction), 2),
            "endpoint_share": round(float(endpoint_share), 3),
            **pn}


def a5_geometry_null(paths, bouts, nights, *, theta, seed=0) -> dict:
    """A5 — endpoint-preserving geometry null. Compare held-out compression of the REAL dictionary on
    real routes vs a Brownian-bridge-null dictionary on null routes (same endpoints + wiggle)."""
    night_arr = bouts["night"].to_numpy()
    k0 = max(1, len(nights) // 2)
    tr = np.isin(night_arr, nights[:k0]); te = np.isin(night_arr, nights[k0:])
    if tr.sum() < 4 or te.sum() < 4:
        return {}
    p_real, ir = rv.learn_leader_dictionary(paths[tr], theta=theta)
    _, res_real = rv.assign(paths[te], p_real)
    null_tr = rv.brownian_bridge_null(paths[tr], seed=seed)
    null_te = rv.brownian_bridge_null(paths[te], seed=seed + 1)
    p_null, inl = rv.learn_leader_dictionary(null_tr, theta=theta)
    _, res_null = rv.assign(null_te, p_null)
    sr = rv.error_summary(res_real, theta=theta, thresholds=COV_THR)
    sn = rv.error_summary(res_null, theta=theta, thresholds=COV_THR)
    return {"K_real": ir["K"], "K_null": inl["K"],
            "real_mean_resid_in": round(sr["mean_resid_in"], 2),
            "null_mean_resid_in": round(sn["mean_resid_in"], 2),
            "real_cov_21in": round(sr["cov_21in"], 3), "null_cov_21in": round(sn["cov_21in"], 3),
            "real_novelty": round(sr["novelty_frac"], 3), "null_novelty": round(sn["novelty_frac"], 3)}


def a7_closure(paths, bouts, nights, *, theta) -> pd.DataFrame:
    """A7 — first-night repertoire closure. Forward (night-0-only dict -> later), reverse (later ->
    night 0), and within-night-0 cumulative windows (first 0.5/1/2/4 h -> remainder + later)."""
    night_arr = bouts["night"].to_numpy()
    rows = []
    n0 = nights[0]
    tr0 = night_arr == n0
    later = np.isin(night_arr, nights[1:])
    if tr0.sum() >= 3 and later.sum() >= 3:
        p0, i0 = rv.learn_leader_dictionary(paths[tr0], theta=theta)
        _, r = rv.assign(paths[later], p0)
        es = rv.error_summary(r, theta=theta, thresholds=COV_THR)
        rows.append({"test": "forward: night0 dict -> later nights", "K": i0["K"],
                     "n_train": int(tr0.sum()), "n_test": int(later.sum()),
                     "cov_21in": round(es["cov_21in"], 3), "novelty_frac": round(es["novelty_frac"], 3)})
        # reverse
        pl, il = rv.learn_leader_dictionary(paths[later], theta=theta)
        _, rr = rv.assign(paths[tr0], pl)
        er = rv.error_summary(rr, theta=theta, thresholds=COV_THR)
        rows.append({"test": "reverse: later dict -> night0", "K": il["K"],
                     "n_train": int(later.sum()), "n_test": int(tr0.sum()),
                     "cov_21in": round(er["cov_21in"], 3), "novelty_frac": round(er["novelty_frac"], 3)})
    # within-night-0 cumulative windows
    b0 = bouts[tr0]
    if len(b0) >= 6:
        t0 = b0["t_start_ms"].min()
        rel_h = (b0["t_start_ms"].to_numpy() - t0) / 3_600_000.0
        idx0 = np.where(tr0)[0]
        for h in (0.5, 1.0, 2.0, 4.0):
            m = rel_h <= h
            if m.sum() < 3 or (~m).sum() < 3:
                continue
            tr_idx = idx0[m]
            te_idx = np.concatenate([idx0[~m], np.where(later)[0]])
            pw, iw = rv.learn_leader_dictionary(paths[tr_idx], theta=theta)
            _, rw = rv.assign(paths[te_idx], pw)
            ew = rv.error_summary(rw, theta=theta, thresholds=COV_THR)
            rows.append({"test": f"night0 first {h:g} h -> remainder+later", "K": iw["K"],
                         "n_train": int(m.sum()), "n_test": int(len(te_idx)),
                         "cov_21in": round(ew["cov_21in"], 3), "novelty_frac": round(ew["novelty_frac"], 3)})
    return pd.DataFrame(rows)


# ===========================================================================
# criteria -> verdict
# ===========================================================================

def derive_criteria(a0, a1, a2, a3, a4, a5) -> dict:
    """Turn the held-out tables into the boolean criteria consumed by rv.decide_verdict, at the
    documented thresholds. Conservative / falsification-leaning defaults."""
    c = {k: False for k in rv.VERDICT_CRITERIA}
    # A3 — finite MDL minimum + dictionary beats PCA
    if not a3.empty:
        kmin = int(a3.loc[a3["mdl_total_bits"].idxmin(), "K"])
        kmax = int(a3["K"].max())
        dip = a3["mdl_total_bits"].max() - a3["mdl_total_bits"].min()
        c["mdl_has_finite_min"] = bool(kmin < kmax and dip > 0.02 * a3["mdl_total_bits"].max())
        # discrete beats continuous by MDL (assignment index cheaper than coding M coefficients),
        # NOT by reconstruction error at matched budget.
        c["dict_beats_pca"] = bool(a3["mdl_total_bits"].min() < a3["pca_mdl_total_bits"].min())
    # A1 — novelty saturates (ROBUST tail rule, not a single-step delta): the last 3 splits' next-night
    # novelty are all low AND their spread is small (a knife-edge d_last<0.05 rule was too brittle —
    # adversarial-review fix).
    if not a1.empty and len(a1) >= 3:
        tail = a1["novelty_next_night"].to_numpy()[-3:]
        c["novelty_saturates"] = bool((tail < 0.15).all() and (float(tail.max()) - float(tail.min())) < 0.08)
    # A2 — other-animal dict generalises: ~own AND beats geometry null (majority of animals)
    if not a2.empty:
        gen = (a2["E_other_in"] <= 1.3 * a2["E_own_in"]) & (a2["E_other_in"] < a2["E_null_in"])
        c["loao_generalizes"] = bool(gen.mean() > 0.5)
    # A5 — real beats the endpoint-preserving geometry null
    if a5:
        c["beats_geometry_null"] = bool(a5["real_mean_resid_in"] < a5["null_mean_resid_in"] - 1.0
                                        and a5["real_cov_21in"] > a5["null_cov_21in"] + 0.05)
    # A4 — reusable path shape beyond endpoints (FAIR pose-normalized test) + endpoints explain most of
    # the error reduction (endpoint_reduction vs reusable-shape_reduction; non-tautological).
    if a4:
        c["shape_beyond_endpoints"] = bool(a4.get("shape_beyond_endpoints", False))
        c["endpoint_explains_most"] = bool(a4.get("endpoint_share", 0.0) >= 0.8)
    return c


def run_core_battery(paths, units, nights, cfg) -> dict:
    """Run the Stage-1 verdict-critical core on ONE trajectory-unit table and return all results +
    criteria + verdict. Segmentation-agnostic: the SAME battery runs on original_3s_filtered_bouts,
    validated_locomotor_legs, or pause_merged_episodes, so a future harness can compare which
    segmentation yields the strongest held-out compression / closure / cross-animal generalisation.
    (A0 support + A7 closure are supplementary; the verdict rests on A1-A5.)"""
    a0 = a0_support(units, theta=cfg["theta"], endpoint_bin=cfg["endpoint_bin"])
    a1 = a1_temporal_holdout(paths, units, nights, theta=cfg["theta"])
    a2 = a2_loao(paths, units, theta=cfg["theta"], seed=cfg["seed"])
    a3 = a3_compression(paths, units, nights, sigma_in=cfg["sigma_in"],
                        bits_per_param=cfg["bits_per_param"], L=cfg["L"])
    a4 = a4_endpoint(paths, units, nights, theta=cfg["theta"], endpoint_bin=cfg["endpoint_bin"],
                     seed=cfg["seed"])
    a5 = a5_geometry_null(paths, units, nights, theta=cfg["theta"], seed=cfg["seed"])
    a7 = a7_closure(paths, units, nights, theta=cfg["theta"])          # supplementary (not verdict-critical)
    crit = derive_criteria(a0, a1, a2, a3, a4, a5)
    insufficient = bool(a0["median_bouts_per_animal_night"] < 2 or a0["n_nights"] < 3
                        or a1.empty or a3.empty)
    verdict = rv.decide_verdict(crit, insufficient_support=insufficient)
    return {"a0": a0, "a1": a1, "a2": a2, "a3": a3, "a4": a4, "a5": a5, "a7": a7,
            "crit": crit, "insufficient": insufficient, "verdict": verdict}


# ===========================================================================
# plots
# ===========================================================================

def _p(out, name):
    return out / "plots" / name


def make_plots(out, a1, a3, a4, a5, a7):
    if not a3.empty:
        fig, ax = plt.subplots(figsize=(6.4, 4.2))
        ax.plot(a3["K"], a3["mean_resid_in"], "-o", label="route dictionary (K-means)")
        ax.plot(a3["K"], a3["pca_resid_in"], "-s", label="continuous PCA (M≈K)")
        ax.set_xscale("log", base=2); ax.set_xlabel("dictionary size K / PCA comps M")
        ax.set_ylabel("held-out reconstruction error (in)"); ax.legend(); ax.grid(alpha=0.3)
        ax.set_title("Held-out error vs model size — discrete dict vs continuous manifold")
        fig.tight_layout(); fig.savefig(_p(out, "dictionary_size_vs_test_error.png"), dpi=120); plt.close(fig)

        fig, ax = plt.subplots(figsize=(6.4, 4.2))
        ax.plot(a3["K"], a3["mdl_total_bits"], "-o", color="#8844aa", label="discrete dictionary MDL")
        ax.plot(a3["K"], a3["pca_mdl_total_bits"], "-s", color="#0a8", label="continuous PCA MDL")
        kmin = int(a3.loc[a3["mdl_total_bits"].idxmin(), "K"])
        ax.axvline(kmin, ls="--", color="#cc4444", label=f"dict MDL min K={kmin}")
        ax.set_xscale("log", base=2); ax.set_xlabel("dictionary size K / PCA comps M")
        ax.set_ylabel("total description length (bits)"); ax.legend(); ax.grid(alpha=0.3)
        ax.set_title("MDL: discrete dictionary vs continuous manifold (lower = better)")
        fig.tight_layout(); fig.savefig(_p(out, "mdl_vs_dictionary_size.png"), dpi=120); plt.close(fig)

    if not a1.empty:
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
        axes[0].plot(a1["train_nights"], a1["novelty_next_night"], "-o", color="#cc6600")
        axes[0].set_xlabel("cumulative training nights"); axes[0].set_ylabel("novel-route fraction (next night)")
        axes[0].set_ylim(0, 1.02); axes[0].grid(alpha=0.3)
        axes[0].set_title("Repertoire acquisition — does novelty saturate?")
        axes[1].plot(a1["train_nights"], a1["cov_21in"], "-o", label="cov ≤21in")
        axes[1].plot(a1["train_nights"], a1["cov_42in"], "-s", label="cov ≤42in")
        axes[1].set_xlabel("cumulative training nights"); axes[1].set_ylabel("held-out coverage")
        axes[1].set_ylim(0, 1.02); axes[1].legend(); axes[1].grid(alpha=0.3)
        axes[1].set_title("Temporal held-out coverage")
        fig.tight_layout(); fig.savefig(_p(out, "cumulative_novel_motifs.png"), dpi=120)
        fig.savefig(_p(out, "temporal_holdout_coverage.png"), dpi=120); plt.close(fig)

    if a4:
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
        ax = axes[0]
        labels = ["global\n(K=1)", "route\ndict", "endpt\nmulti", "endpt\nmean", "endpoint\nchord"]
        vals = [a4["E_global_in"], a4["E_route_dict_in"], a4["E_endpoint_multi_in"],
                a4["E_endpoint_mean_in"], a4["E_chord_in"]]
        ax.bar(labels, vals, color=["#999", "#284", "#3a8", "#59c", "#c60"])
        ax.set_ylabel("held-out reconstruction error (in)")
        ax.set_title(f"Absolute frame — endpoints dominate\n(chord {a4['E_chord_in']} < dict "
                     f"{a4['E_route_dict_in']}; endpoint share {a4['endpoint_share']*100:.0f}%)", fontsize=9)
        ax = axes[1]
        pl = ["straight\nsegment", "shape\ndict", "geometry\nnull"]
        pv = [a4["E_pn_straight_in"], a4["E_pn_shapedict_in"], a4["E_pn_null_in"]]
        ax.bar(pl, pv, color=["#c60", "#284", "#a44"])
        ax.set_ylabel("pose-normalized held-out error (in)")
        ax.set_title(f"Endpoint-registered frame — reusable shape?\n"
                     f"shape_beyond_endpoints = {a4['shape_beyond_endpoints']}", fontsize=9)
        fig.tight_layout(); fig.savefig(_p(out, "endpoint_vs_route_model.png"), dpi=120); plt.close(fig)

    if a5:
        fig, ax = plt.subplots(figsize=(6.2, 4.2))
        x = np.arange(2); wdt = 0.35
        ax.bar(x - wdt / 2, [a5["real_mean_resid_in"], a5["null_mean_resid_in"]], wdt, label="mean resid (in)")
        ax.bar(x + wdt / 2, [a5["real_cov_21in"] * 100, a5["null_cov_21in"] * 100], wdt, label="cov ≤21in (%)")
        ax.set_xticks(x); ax.set_xticklabels(["REAL routes", "geometry null"])
        ax.legend(); ax.set_title("Real routes vs endpoint-preserving Brownian-bridge null")
        fig.tight_layout(); fig.savefig(_p(out, "real_vs_geometry_null.png"), dpi=120); plt.close(fig)

    if not a7.empty:
        fig, ax = plt.subplots(figsize=(8.4, 4.2))
        y = np.arange(len(a7))
        ax.barh(y, a7["cov_21in"], color="#3a8")
        ax.set_yticks(y); ax.set_yticklabels(a7["test"], fontsize=7)
        ax.set_xlabel("held-out coverage ≤21in"); ax.set_xlim(0, 1.02)
        ax.set_title("First-night repertoire closure (leakage-controlled)")
        fig.tight_layout(); fig.savefig(_p(out, "first_night_acquisition.png"), dpi=120); plt.close(fig)


# ===========================================================================
# main
# ===========================================================================

def main():
    try:                                   # Windows console is cp1252; report/manifest are UTF-8 files
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--incremental-dir", type=Path, default=pa.DEFAULT_INCR)
    ap.add_argument("--baseline", type=Path, default=pa.DEFAULT_BASELINE)
    ap.add_argument("--rois", type=Path, default=pa.DEFAULT_ROIS)
    ap.add_argument("--gt", type=Path, default=pa.DEFAULT_GT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--segmentation", default="original_3s_filtered_bouts",
                    choices=list(tu.SEGMENTATIONS),
                    help="trajectory-unit table to test (results go to <out>/<segmentation>/). Only "
                         "original_3s_filtered_bouts is implemented (PROVISIONAL baseline); legs/episodes "
                         "await the decision-boundary analysis.")
    ap.add_argument("--dates", nargs="*", default=None)
    ap.add_argument("--night-start", type=int, default=21)
    ap.add_argument("--night-end", type=int, default=4)
    ap.add_argument("--min-disp-in", type=float, default=15.0)
    ap.add_argument("--resample-n", type=int, default=20)
    ap.add_argument("--max-per-night", type=int, default=40)
    ap.add_argument("--threshold-in", type=float, default=None, help="motif/dictionary θ (in); default 3×jitter")
    ap.add_argument("--endpoint-bin-in", type=float, default=42.0, help="endpoint stratum grid (in)")
    ap.add_argument("--sigma-in", type=float, default=None, help="MDL residual std (in); default = jitter floor")
    ap.add_argument("--bits-per-param", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-nights", type=int, default=None)
    args = ap.parse_args()

    out = args.out / args.segmentation                 # per-segmentation subdir (representation comparison)
    (out / "plots").mkdir(parents=True, exist_ok=True)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    names = pa._name_map()

    print(f"== Route-vocabulary validation (Stage 1) — segmentation={args.segmentation} ==")
    print("[1/9] load + clean (mirror Phase B) ...")
    df, load_log = ts.load_incremental_days(args.incremental_dir, dates=args.dates)
    df = time_utils.convert_timestamps(df)
    floor = pa.establish_floor(args.baseline, args.gt)
    jitter_floor = floor["jitter_floor_in"]; moving_thr = floor["moving_thr_inps"]
    df = w.add_speed(df)
    roi_cfg = w.load_rois(args.rois)
    boundary = (roi_cfg or {}).get("boundary")
    df = w.add_validity_flags(df, boundary=boundary, jitter_floor_in=jitter_floor)
    df = w.apply_tag_cutoffs(df)
    win = ts.select_night_window(df, night_start=args.night_start, night_end=args.night_end, valid_only=True)
    win = win[~win["shortid"].astype(str).isin(pa.DROP_TAGS)].reset_index(drop=True)
    nights = sorted(win["night"].unique())
    if args.max_nights:
        nights = nights[:args.max_nights]
        win = win[win["night"].isin(nights)].reset_index(drop=True)
    L = args.resample_n
    theta = args.threshold_in if args.threshold_in is not None else round(3.0 * jitter_floor, 1)
    sigma_in = args.sigma_in if args.sigma_in is not None else float(jitter_floor)
    print(f"    nights={nights}; theta={theta} in; sigma_MDL={sigma_in} in")

    print(f"[2/9] load trajectory units (segmentation={args.segmentation}) ...")
    bouts, paths, umeta = tu.load_units(
        args.segmentation, win=win, nights=nights, moving_thr_inps=moving_thr, roi_cfg=roi_cfg,
        min_disp_in=args.min_disp_in, resample_n=L, max_per_night=args.max_per_night)
    blog = umeta["bout_log"]
    print(f"    {blog['n_bouts_kept']} units  ({umeta['label']})")
    if len(bouts) < 20:
        print("    too few units; aborting."); return

    cfg = {"theta": theta, "sigma_in": sigma_in, "bits_per_param": args.bits_per_param,
           "endpoint_bin": args.endpoint_bin_in, "seed": args.seed, "L": L}
    print("[3-8/9] core battery (A0 support, A1 temporal, A2 LOAO, A3 MDL, A4 endpoint/shape, A5 null, A7 closure) ...")
    res = run_core_battery(paths, bouts, nights, cfg)
    a0, a1, a2, a3, a4, a5, a7 = (res["a0"], res["a1"], res["a2"], res["a3"], res["a4"], res["a5"], res["a7"])
    crit, insufficient, verdict = res["crit"], res["insufficient"], res["verdict"]

    # tables
    a1.to_csv(out / "tables" / "temporal_holdout.csv", index=False)
    a2.to_csv(out / "tables" / "leave_one_animal_out.csv", index=False)
    a3.to_csv(out / "tables" / "compression_model_comparison.csv", index=False)
    pd.DataFrame([a4]).to_csv(out / "tables" / "endpoint_conditioned_results.csv", index=False)
    pd.DataFrame([a5]).to_csv(out / "tables" / "null_model_results.csv", index=False)
    a7.to_csv(out / "tables" / "repertoire_closure.csv", index=False)
    print(f"[9/9] interim verdict: {verdict['verdict']} ({umeta['label']})")

    make_plots(out, a1, a3, a4, a5, a7)

    manifest = {
        "analysis": "route_vocabulary_validation_stage1",
        "generated_utc": _dt.datetime.utcnow().isoformat(),
        "git_commit": pa._git_commit(),
        "segmentation": umeta,
        "provisional": bool(umeta["provisional"]),
        "conditional_label": umeta["label"],
        "units": "inches (WISER native, UNVERIFIED offset origin)",
        "frame_note": "UNVERIFIED inch frame -> topological/relative only; Module 11 blocked; verdict ceiling B/C",
        "night_window_local": [args.night_start, args.night_end],
        "jitter_floor_in": jitter_floor, "theta_in": theta, "sigma_mdl_in": sigma_in,
        "bits_per_param": args.bits_per_param, "endpoint_bin_in": args.endpoint_bin_in,
        "Ks": KS, "seed": args.seed, "n_bouts": int(len(bouts)), "bout_log": blog,
        "nights": nights, "animals": {a: names.get(a, a) for a in sorted(bouts["shortid"].unique())},
        "a0_support": a0, "criteria": crit, "insufficient_support": insufficient,
        "verdict": verdict,
        "provenance": {
            "timestamp_method": ("unix_ms UTC -> local EDT via Timedelta(hours=-4); night window "
                                 f"{args.night_start}:00-{args.night_end:02d}:00; pandas[ms]-safe (.dt.floor)"),
            "hypnos_cutoff": ("12380 implant dropped 2026-07-09T03:35:41-04:00 (apply_tag_cutoffs); "
                              "cohort 5 rats through the 07-08 night, 4 from 07-09"),
            "units_per_night_animal": {f"{n}|{s}": int(c)
                                       for (n, s), c in bouts.groupby(["night", "shortid"]).size().items()},
            "measurement_context_sidecar": ("ABSENT — follow-up (separate PR): build a WISER "
                "measurement_context sidecar + per-bout mc stamp (flag_summary fractions, min_anchors, "
                "per-night x animal counts) mirroring the CV pattern; see "
                "outputs/audit/ROUTE_VOCAB_AUDIT_2026-07-11.md"),
        },
        "phase_b_audit": {
            "z_gt2_error": "Phase-B report said 'Since z>2' for z=1.84 — corrected in place; z<2, no "
                           "individual residual established.",
            "sign_convention": "g = mean(other_nn) − mean(self_nn) = −5.25 consistent across code/def/z; "
                               "report prose relabelled from 'self−other' to 'other−self'; per-animal "
                               "column self_minus_other_in = −g_i flagged.",
            "leakage": "Phase-B recurrence uses a globally-pooled NN dictionary (future nights + no "
                       "same-night/adjacent-bout exclusion) — retrospective upper bound; A1/A7 here are "
                       "leakage-controlled.",
        },
        "caveats": [
            "PROVISIONAL: all conclusions are '" + umeta["label"] + "'. These units are a baseline "
            "imposed by a min-duration/min-displacement filter, NOT validated decision-to-decision "
            "locomotor legs. A positive vocabulary result would NOT be evidence of route tokens until "
            "the identical battery is repeated on validated legs / pause-merged episodes.",
            "held-out only: no dictionary is scored on its own training data",
            "dict-vs-PCA MDL is NOT load-bearing for the verdict (it flips at the bpp=32/sigma=14 "
            "corner); A stays blocked independently by shape_beyond_endpoints and novelty_saturates; "
            "only mdl_has_finite_min (a dip exists) is robust",
            "A4 shape-beyond-endpoints uses a FAIR endpoint-registered (pose-normalized) test + matched "
            "null; endpoint_share compares error REDUCTIONS (not a construction tautology)",
            "A2 E_other excludes same-held-out-night other-animal bouts (social-following near-duplicate "
            "leak) and is averaged over seeds with E_other_sd reported",
            "MEASUREMENT AUDIT (outputs/audit/ROUTE_VOCAB_AUDIT_2026-07-11.md): NOT-A is measurement-sound "
            "as a floor-bounded negative (no discrete vocabulary resolvable above ~7 in); C-vs-B is "
            "UNRESOLVED — the deciding late nights (07-08->07-10) coincide with refuge_4 removal (07-07) + "
            "barn-light onset (07-09) + the 5->4 cohort drop, so closure vs regime-novelty is not "
            "separable; the reusable-shape reduction (~2 in) is sub-jitter-floor",
            "geometry null = endpoint+wiggle-preserving Brownian bridge (Stage-1 single strong null)",
            "roadway-camera audit UNDONE (needs georeference); no physical-road claim",
            "Stage 1 only: bootstrap stability (A6) + full null battery + grammar (A8) + policy "
            "interpretation are GATED on the forthcoming decision-boundary (validated-leg) analysis",
        ],
    }
    with open(out / "run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    _write_report(out, manifest, a0, a1, a2, a3, a4, a5, a7, crit, verdict)
    _write_readme(out, umeta["label"])
    print(f"\nDONE -> {out}\nVERDICT {verdict['verdict']}: {verdict['text']}")


def _write_readme(out, label):
    (out / "README.md").write_text(
        "# Route-vocabulary validation (Stage 1)\n\n"
        f"**PROVISIONAL — {label}.** These units are a baseline whose scale is imposed by a "
        "min-duration + min-displacement filter, NOT validated locomotor legs; a positive result would "
        "NOT be evidence of route tokens until re-tested on validated legs / pause-merged episodes.\n\n"
        "Falsification-first test of whether WISER route bouts form a finite, shared, out-of-sample\n"
        "route vocabulary. See `validation_report.md` for the verdict + claim table, `run_manifest.json`\n"
        "for parameters/provenance, `tables/` for the held-out results, `plots/` for figures.\n\n"
        "Frame is the UNVERIFIED WISER inch frame — topological/relative claims only (Module 11 blocked).\n"
        "Verdict-C robustness + provenance limits: `../../audit/ROUTE_VOCAB_AUDIT_2026-07-11.md`.\n"
        "Generated by `scripts/analyze_route_vocabulary.py` (run under anaconda3; scipy+sklearn).\n",
        encoding="utf-8")


def _write_report(out, m, a0, a1, a2, a3, a4, a5, a7, crit, verdict):
    L = []
    A = L.append
    seg = m["segmentation"]
    A("# Route-vocabulary validation — is movement a discrete shared route vocabulary? (Stage 1)")
    A("")
    A(f"**Generated (UTC):** {m['generated_utc']}  ")
    A(f"**Commit:** `{m['git_commit']}`  ")
    A(f"**Segmentation:** `{seg['segmentation_id']}` — **{seg['label']}**  ")
    A(f"**Nights:** {', '.join(m['nights'])} · **Animals:** {', '.join(m['animals'].values())}  ")
    A(f"**Units:** {m['n_bouts']} · **θ:** {m['theta_in']} in (3× jitter) · **Frame:** inches, "
      "UNVERIFIED — topological/relative only, no metric/physical-road claims  ")
    A("")
    A(f"## Interim verdict: **{verdict['verdict']}** — {verdict['text']}")
    A("")
    A(f"> **CONDITIONAL ON THIS SEGMENTATION — {seg['label']}.** These units are a provisional, "
      "filter/merge-defined baseline — NOT validated decision-to-decision locomotor legs. A positive "
      "vocabulary result on them would NOT be evidence that rats possess route tokens; that requires "
      "repeating the identical battery on validated legs (BLOCKED — needs CV pose/keypoints; see "
      "`decision_boundary_validation/`).")
    A("")
    A(f"> Rationale: {'; '.join(verdict['reasons'])}. Criteria: " +
      ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in verdict["criteria"].items()) + ".")
    A("")
    A("> **Robust vs unresolved (measurement audit, `outputs/audit/ROUTE_VOCAB_AUDIT_2026-07-11.md`):** "
      "the robust result is **NOT-A — no discrete route vocabulary *resolvable above the ~7 in jitter "
      "floor* at this provisional segmentation** (it rests on the continuous low-dim shape + the "
      "non-load-bearing dict_beats_pca, neither of which a regime confound flips). **The C-vs-B "
      "distinction is UNRESOLVED, not merely caveated:** novelty_saturates is decided by the 07-08→07-10 "
      "splits (n_test 270→120), which coincide with refuge_4 removal (07-07), the south barn-light onset "
      "(07-09), and the cohort dropping 5→4 (Hypnos cutoff 07-09) — all of which inflate late-night "
      "novelty, so 'open manifold' cannot be separated from regime-induced novelty. The reusable-shape "
      "differential that nominally tips C over B is itself **sub-jitter-floor** (shape dict 5.81 in < the "
      "~7 in floor; ~2 in reduction) — a matched-null differential only, never a metric size. Read C as "
      "'not-A, and not cleanly a finite closed graph either'; re-evaluate closure on nights ≤ 07-08.")
    A("")
    A("## Segmentation provenance & scope")
    A("")
    A(f"- **Unit table:** `{seg['segmentation_id']}` (status: {seg['status']}). {seg['definition']}")
    A(f"- **Params:** {seg['params']}.")
    A("- The route-vocabulary battery (`run_core_battery`) is segmentation-agnostic and will later "
      "accept `validated_locomotor_legs` + `pause_merged_episodes` (same schema; `src/trajectory_units.py`). "
      "The eventual test is a **representation comparison**: which segmentation gives the strongest "
      "held-out compression, prototype stability, repertoire closure, and cross-animal generalisation.")
    A("- **Gated:** bootstrap stability (A6), the full null battery, route grammar (A8), and any policy "
      "interpretation do NOT run until the decision-boundary analysis provides validated legs.")
    A("")
    A("## 0. Phase-B audit corrections (inherited)")
    A("")
    A(f"- **z>2 error:** {m['phase_b_audit']['z_gt2_error']}")
    A(f"- **Sign convention:** {m['phase_b_audit']['sign_convention']}")
    A(f"- **Leakage:** {m['phase_b_audit']['leakage']}")
    A("")
    A("## A0. Support (kill-gate)")
    A("")
    A(f"- {a0['n_bouts']} bouts, {a0['n_animals']} animals, {a0['n_nights']} nights; median "
      f"{a0['median_bouts_per_animal_night']:.0f} bouts/animal-night (min per animal "
      f"{a0['min_bouts_per_animal']}). Insufficient-support flag: **{m['insufficient_support']}**.")
    A("")
    A("## A1. Temporal held-out dictionary (repertoire acquisition)")
    A("")
    if not a1.empty:
        A("| train nights | K | n_test | mean resid (in) | cov ≤21in | cov ≤42in | novelty (all later) | novelty (next night) |")
        A("|---|---|---|---|---|---|---|---|")
        for _, r in a1.iterrows():
            A(f"| {int(r['train_nights'])} | {int(r['K'])} | {int(r['n_test'])} | {r['mean_resid_in']} | "
              f"{r['cov_21in']} | {r['cov_42in']} | {r['novelty_frac']} | {r['novelty_next_night']} |")
        A("")
        A(f"- Dictionaries are learned on the first *c* nights ONLY and frozen. novelty_saturates = "
          f"**{crit['novelty_saturates']}** (a finite vocabulary should plateau near 0; a growing "
          "novel-route fraction ⇒ open repertoire).")
    else:
        A("- (insufficient nights)")
    A("")
    A("## A2. Leave-one-animal-out (shared-dictionary generalisation)")
    A("")
    if not a2.empty:
        A("| animal | held-out night | n_test | E_other (±sd) | E_own | E_null(geom) | E_endpoint |")
        A("|---|---|---|---|---|---|---|")
        for _, r in a2.iterrows():
            A(f"| {r['animal']} | {r['held_out_night']} | {int(r['n_test'])} | "
              f"{r['E_other_in']} ± {r.get('E_other_sd', 0.0)} | {r['E_own_in']} | {r['E_null_in']} | "
              f"{r['E_endpoint_in']} |")
        A("")
        me = float(a2["E_endpoint_in"].mean()); mo = float(a2["E_other_in"].mean())
        A(f"- A dictionary from OTHER animals is compared to the animal's OWN earlier nights and to a "
          f"geometry-preserving null (count-matched, **same-held-out-night other-animal bouts excluded** "
          "to remove social-following near-duplicates, **averaged over 5 seeds** with E_other_sd shown). "
          f"loao_generalizes = **{crit['loao_generalizes']}** (other-animal ≈ own AND < null ⇒ the "
          "*dictionary* transfers across animals — though decisive margins are close to the seed sd). "
          f"**But the endpoint chord E_endpoint ≈ {me:.0f} in ≪ every dictionary (E_other ≈ {mo:.0f} in): "
          "what generalises across animals is the shared ENDPOINT GRAPH (common locations), not a shared "
          "path-shape vocabulary — consistent with A4.**")
    else:
        A("- (insufficient per-animal nights)")
    A("")
    A("## A3. Compression / model selection (MDL, dictionary vs continuous)")
    A("")
    if not a3.empty:
        A("| K | mean resid (in) | cov ≤21in | dict MDL (bits) | PCA M | PCA resid (in) | PCA MDL (bits) | BIC |")
        A("|---|---|---|---|---|---|---|---|")
        for _, r in a3.iterrows():
            A(f"| {int(r['K'])} | {r['mean_resid_in']} | {r['cov_21in']} | {r['mdl_total_bits']:.0f} | "
              f"{int(r['pca_M'])} | {r['pca_resid_in']} | {r['pca_mdl_total_bits']:.0f} | {r['bic']:.0f} |")
        A("")
        A(f"- mdl_has_finite_min = **{crit['mdl_has_finite_min']}** (a dip exists — robust); "
          f"dict_beats_pca (by MDL) = **{crit['dict_beats_pca']}**. The discrete code pays only log₂K "
          "bits/path for assignment while PCA codes M coefficients/path (reconstruction error alone "
          "can't decide discreteness: K means always span a (K−1)-affine subspace, so PCA ties on error "
          "by construction). **dict_beats_pca is NOT load-bearing for the verdict** — it flips at the "
          "bpp=32/σ=14 corner (≈0.6% margin), and A stays blocked independently by "
          "shape_beyond_endpoints and novelty_saturates regardless. Note **PCA reaches ~4 in at M=4** "
          "(below the endpoint chord), i.e. the route manifold has a small low-dimensional CONTINUOUS "
          "component beyond the straight chord — reusable, but not discrete.")
    else:
        A("- (insufficient bouts for a temporal split)")
    A("")
    A("## A4. Endpoint vs path-shape decomposition")
    A("")
    if a4:
        A(f"- **Absolute-frame ladder** (held-out error, worst→best): global(K=1) **{a4['E_global_in']}** "
          f"· route-dictionary **{a4['E_route_dict_in']}** (K={a4['K_dict']}) · endpoint-grid-mean "
          f"**{a4['E_endpoint_mean_in']}** · endpoint-conditioned-shape **{a4['E_endpoint_multi_in']}** · "
          f"**endpoint-chord {a4['E_chord_in']}** (a straight line between each route's own two "
          f"endpoints). Endpoints alone carry the bulk of the reduction (global {a4['E_global_in']} → "
          f"chord {a4['E_chord_in']}, ≈ **{a4['endpoint_share']*100:.0f}%** of the total; "
          f"endpoint_explains_most = **{crit['endpoint_explains_most']}**).")
        A(f"- **Caveat on 'chord beats the K={a4['K_dict']} dictionary' ({a4['E_chord_in']} < "
          f"{a4['E_route_dict_in']}):** the chord is handed each test route's own two endpoints (4 "
          "per-path parameters) while the frozen dictionary spends none, so this is NOT a param-matched "
          "win — it says endpoints are highly informative, not that shape is useless. The fair "
          "discreteness call is the A3 MDL result.")
        sb = crit['shape_beyond_endpoints']
        A(f"- **Reusable shape beyond endpoints — the FAIR scale-invariant (endpoint-registered) test** "
          "(translate + rotate + SCALE removed so only unit-scale curvature remains; residuals scaled "
          f"back to inches): straight segment **{a4['E_pn_straight_in']}** in · unit-scale SHAPE "
          f"dictionary **{a4['E_pn_shapedict_in']}** in · matched Brownian-bridge null "
          f"**{a4['E_pn_null_in']}** in → shape_beyond_endpoints = **{sb}**.")
        if sb:
            A(f"  There is a small, reusable, *low-dimensional CONTINUOUS* curvature component beyond the "
              f"straight chord (corroborated by A5 beats_geometry_null and A3 PCA-M=4 ≈ 4 in) — but it is "
              f"NOT a discrete vocabulary of distinctive path shapes, and the reduction "
              f"({a4['E_pn_straight_in']}→{a4['E_pn_shapedict_in']} in, ~"
              f"{a4['E_pn_straight_in']-a4['E_pn_shapedict_in']:.0f} in) is **sub-jitter-floor** "
              f"(< ~{m['jitter_floor_in']:.0f} in) — admissible only as a matched-null differential vs "
              "the Brownian null, never a resolvable metric shape size.")
        else:
            A("  No reusable curvature survives the fair scale-invariant test; the small A5/A3 signals "
              "(real < null; PCA-M=4) then reflect route CONSISTENCY / length regularity rather than a "
              "reusable curved-path shape. Either way there is no discrete path-shape vocabulary.")
        A("- Net: movement is dominated by its endpoints (Module 6 endpoint structure — allowed)" +
          (", with a minor reusable continuous curvature refinement on top" if sb else "") +
          "; there is **no discrete path-shape vocabulary** (Module 11 path claims stay blocked; the "
          "frame is unverified, so no metric/directional/physical-road reading).")
    else:
        A("- (insufficient bouts)")
    A("")
    A("## A5. Endpoint-preserving geometry null")
    A("")
    if a5:
        A(f"- REAL dictionary on real routes: mean resid **{a5['real_mean_resid_in']}** in, cov≤21in "
          f"**{a5['real_cov_21in']}**, novelty **{a5['real_novelty']}** (K={a5['K_real']}).")
        A(f"- Brownian-bridge NULL (same endpoints + wiggle, template destroyed): mean resid "
          f"**{a5['null_mean_resid_in']}** in, cov≤21in **{a5['null_cov_21in']}**, novelty "
          f"**{a5['null_novelty']}** (K={a5['K_null']}).")
        A(f"- beats_geometry_null = **{crit['beats_geometry_null']}**. Because the null preserves each "
          "route's endpoints AND wiggle amplitude and only randomises the wiggle SHAPE, real beating "
          "null means real routes are **more consistent / lower-shape-variance** (straighter, more "
          "repeatable) than random wiggle of the same size — i.e. there is *some* reusable continuous "
          "shape regularity. It does NOT imply a rich or discrete path-shape vocabulary; it is the same "
          "small reusable-shape signal quantified fairly in A4 (pose-normalized) and A3 (PCA M=4).")
    else:
        A("- (insufficient bouts)")
    A("")
    A("## A7. First-night repertoire closure (leakage-controlled)")
    A("")
    if not a7.empty:
        A("| test | K | n_train | n_test | cov ≤21in | novelty |")
        A("|---|---|---|---|---|---|")
        for _, r in a7.iterrows():
            A(f"| {r['test']} | {int(r['K'])} | {int(r['n_train'])} | {int(r['n_test'])} | "
              f"{r['cov_21in']} | {r['novelty_frac']} |")
        A("")
        fwd = a7[a7["test"].str.startswith("forward")]
        rev = a7[a7["test"].str.startswith("reverse")]
        fc = float(fwd["cov_21in"].iloc[0]) if len(fwd) else float("nan")
        rc = float(rev["cov_21in"].iloc[0]) if len(rev) else float("nan")
        A(f"- Directly replaces Phase-B's retrospective 'stereotyped from night 1': a **night-0-only** "
          f"frozen dictionary covers only **{fc*100:.0f}%** of later-night routes within 21 in (forward) — "
          f"far below Phase-B's pooled 97% — so the repertoire is **NOT fully present on night 1**; it "
          f"accumulates over nights (consistent with A1's non-saturating novelty). The reverse direction "
          f"(a 13-night dictionary covers **{rc*100:.0f}%** of night 0) is higher, but that is "
          f"**confounded by training-set size** (108 vs 1584 bouts), so read the forward/reverse gap as "
          "size-limited, not purely temporal. Within-night-0 windows (first 0.5–4 h) likewise cover <35% "
          "of the remainder — early routes do not yet span the eventual repertoire.")
    else:
        A("- (insufficient bouts on night 0)")
    A("")
    A("## Claim table")
    A("")
    A("_All statuses are **conditional on the original 3-second-filtered bout segmentation** — a "
      "provisional baseline, not validated locomotor legs._")
    A("")
    A("| proposed claim | required evidence | observed | status |")
    A("|---|---|---|---|")
    A("| Route recurrence exists | near-identical partner routes | Phase B: ~97% (global-dictionary "
      "upper bound) | supported (weakened by leakage) |")
    A(f"| Finite DISCRETE route vocabulary | finite-K MDL win over PCA + novelty saturates + shape "
      f"beyond endpoints | dict_beats_pca={crit['dict_beats_pca']} (not load-bearing), "
      f"saturates={crit['novelty_saturates']} | **rejected** |")
    A(f"| Shared structure across animals | other-animal dict ≈ own, < null | loao_generalizes="
      f"{crit['loao_generalizes']} — a shared ENDPOINT graph, not a shared path vocabulary | "
      "supported (endpoints) |")
    A(f"| Reusable shape beyond endpoints | pose-normalized shape dict beats straight segment + null | "
      f"shape_beyond_endpoints={crit['shape_beyond_endpoints']} | "
      f"{'supported (small, low-dim, CONTINUOUS)' if crit['shape_beyond_endpoints'] else 'not supported'} |")
    A("| Discrete path-shape vocabulary | shape clusters into a finite reused set | no finite-K win; "
      "shape is continuous/low-dim | **rejected** |")
    A(f"| Beyond enclosure geometry | beats endpoint-preserving null | beats_geometry_null="
      f"{crit['beats_geometry_null']} — route consistency, not a vocabulary | supported |")
    A("")
    A("## Cannot say / next")
    A("")
    A("- **Provisional segmentation:** every result is conditional on the 3-second-filtered bouts; the "
      "vocabulary/representation question is only settled once the identical battery runs on validated "
      "decision-to-decision legs and pause-merged episodes and they are compared.")
    A("- **Frame UNVERIFIED:** no metric, directional, or physical-road claim (Module 11 blocked). The "
      "'roadway' the rats wear is NOT verified against camera footage here (needs georeference).")
    A("- **Gated downstream:** bootstrap stability (A6), the full geometry-null battery, route grammar "
      "(A8), and any policy interpretation do NOT run until the decision-boundary analysis provides "
      "validated legs — regardless of this provisional verdict.")
    A("")
    A("## Definitions")
    A("")
    A("Units **inches** (WISER native, UNVERIFIED). Paths are arc-length-resampled to $L$ points; "
      "$D(a,b)=\\frac1L\\sum_k\\lVert a_k-b_k\\rVert$ (mean-pointwise, in).")
    A("- **Dictionary / prototype:** a set of $K$ paths learned from TRAIN data only and frozen; for a "
      "held-out path, residual $r_i=\\min_m D(\\text{path}_i,\\text{proto}_m)$ (nearest-prototype "
      "distance, in). Leader-medoid dict = greedy non-chaining clusters at $\\theta$; K-means dict = "
      "$K$ centroids in $\\mathbb R^{2L}$.")
    A("- **Coverage@$\\tau$** $=\\frac1N\\sum_i \\mathbb 1[r_i\\le\\tau]$ (fraction reconstructed within "
      "$\\tau$ in). **Novelty** $=\\frac1N\\sum_i \\mathbb 1[r_i>\\theta]$ (held-out routes with no near "
      "prototype). **novelty_saturates** (bool) = the last 3 cumulative-training splits' next-night "
      "novelty are all $<0.15$ AND their range $<0.08$ (a robust tail rule, not a single-step delta).")
    A("- **MDL** $L(K)=\\underbrace{K\\,2L\\,b_p}_{\\text{dict}}+\\underbrace{N\\log_2K}_{\\text{assign}}"
      "+\\underbrace{\\text{Gaussian residual bits at }\\sigma}_{\\text{residual}}$; $b_p$ bits/param, "
      "$\\sigma$ residual std (stated a priori = jitter floor). A finite $\\arg\\min_K$ ⇒ a discrete "
      "scale. **PCA MDL** adds $N\\!\\cdot\\!M$ coefficient bits/path instead of $N\\log_2K$ assignment "
      "bits; **dict_beats_pca** = $\\min_K L_{\\text{dict}} < \\min_M L_{\\text{PCA}}$ (reconstruction "
      "error can't decide this: $K$ means span a $(K{-}1)$-affine subspace, so PCA ties on error). "
      "**BIC** $=n\\ln(\\text{SSE}/n)+p\\ln n$.")
    A("- **Endpoint chord:** the straight, constant-speed line between a route's OWN start and end — the "
      "parameter-free ENDPOINT-ONLY reconstruction ($E_{\\text{chord}}$). **endpoint_share** "
      "$=\\Delta_{\\text{endpoint}}/(\\Delta_{\\text{endpoint}}+\\Delta_{\\text{shape}})$ with "
      "$\\Delta_{\\text{endpoint}}=E_{\\text{global}}-E_{\\text{chord}}$ (absolute frame) and "
      "$\\Delta_{\\text{shape}}=\\max(0,E^{pn}_{\\text{straight}}-E^{pn}_{\\text{shapedict}})$ "
      "(pose-normalized frame). Two error REDUCTIONS in inches — non-tautological. "
      "endpoint_explains_most $=$ endpoint_share $\\ge 0.8$.")
    A("- **Scale-invariant (endpoint-registered) shape test** (decides **shape_beyond_endpoints**): each "
      "path is translated so start $=$ origin, rotated so end lies on $+x$, AND divided by its endpoint "
      "distance, removing location, heading, and length — the full endpoint pair — to leave unit-scale "
      "CURVATURE. Clustering uses $\\theta_n=\\theta/\\mathrm{median}(\\text{disp}_{\\text{train}})$; "
      "residuals are scaled BACK by each route's own length so short routes are not noise-amplified. "
      "shape_beyond_endpoints $=$ a frozen unit-scale shape dictionary ($E^{pn}_{\\text{shapedict}}$) "
      "beats BOTH the straight segment ($E^{pn}_{\\text{straight}}$) AND a matched Brownian-bridge null "
      "($E^{pn}_{\\text{null}}$) by $\\ge 0.5$ in. Not the binning-biased absolute-location test.")
    A("- **LOAO:** $E_{\\text{other}}$ = a count-matched OTHER-animals dictionary scored on a held-out "
      "animal's last night, **excluding same-held-out-night other-animal bouts** (social-following "
      "near-duplicate leak) and averaged over 5 seeds ($E$_other_sd shown); $E_{\\text{own}}$ = the "
      "animal's own earlier-night dictionary; $E_{\\text{null}}$ = geometry-preserving (Brownian-bridge) "
      "null dictionary. loao_generalizes needs $E_{\\text{other}}\\lesssim E_{\\text{own}}$ AND "
      "$E_{\\text{other}}<E_{\\text{null}}$ for a majority of animals.")
    A("- **Geometry null:** each path replaced by a 2-D Brownian bridge between its own endpoints, RMS "
      "deviation matched to the real path (endpoints + wiggle amplitude preserved, reused template "
      "destroyed).")
    A("- **Trajectory unit / segmentation:** one candidate locomotor unit (bout/leg/episode) with an "
      "arc-length-resampled path; the battery runs on any unit table with the "
      "`src/trajectory_units.py` schema. This run used `original_3s_filtered_bouts` (provisional; "
      "min-duration $\\ge3$ s + min-displacement $\\ge15$ in impose the scale).")
    A("")
    (out / "validation_report.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
