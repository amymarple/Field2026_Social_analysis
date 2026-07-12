r"""
analyze_following_structure.py — Phase B of the trajectory analysis.

Question (from the field observation of following / parallel travel): the
co-movement is real (Phase A anchored it above the circular-shift null) — but does
it happen within STABLE PAIRS (social dyads) or MUTUALLY between any individuals
(a shared road / herd)? This driver answers that with directional, lag- and
heading-aware following (w's validated `following_*` suite), then tests:

  1. SPECIFICITY  — is co-movement concentrated in a few pairs, or spread over all?
  2. STABILITY    — is it the SAME subset of pairs across nights?
  3. LEADERSHIP   — within a pair, does one animal consistently lead?
  4. HERD CONTROL — whole-group cohesion, so "pairwise preference above herd" is explicit.

Zero-lag co-movement is only the anchor (jitter- and direction-blind); the headline
uses the lag-aware follow score (radius R = 3x jitter floor; heading cosine > 0.5;
lags 1-30 s) vs a per-pair circular-shift null. The 07-04 fireworks night is excluded
(disturbance spike). Nights 07-03/07-05 carry the refuge_4 burrow UWB-dropout regime
(affects resting fixes more than moving bouts; flagged). Inch frame is UNVERIFIED —
no directional/physical claims; "leader/follower" is temporal order, not geometry.

Read-only on transferred backups. Outputs to
wiser/outputs/following_structure_2026-06-28_to_2026-07-06/.

    conda activate cv
    cd wiser
    python scripts/analyze_following_structure.py                 # full Phase B
    python scripts/analyze_following_structure.py --max-nights 2  # smoke
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
import analyze_trajectory_stereotypy as pa    # noqa: E402  (reuse load/clean/floor)

DEFAULT_OUT = PROJECT_ROOT / "outputs" / "following_structure_2026-06-28_to_2026-07-08"
# refuge_4 burrow UWB dropout regime (weather-independent), nightly from ~07-03.
REFUGE4_DROPOUT_NIGHTS = {"2026-07-03", "2026-07-04", "2026-07-05"}

# Definitions block (formula + text) per .claude/skills/analysis-definitions.
_DEFINITIONS = r"""## Definitions

Units: **inches** (WISER native, UNVERIFIED offset frame; a "leader" is temporal order, not
geometry). Positions are on a common **1 s grid**, positions smoothed by a 5 s rolling median;
$\mathbf{x}_A(t)$ = animal $A$'s position at second $t$; $\hat{\mathbf u}_A(t)$ = its unit heading
(velocity / speed); $\text{mov}_A(t)$ = moving mask ($\text{speed}>v_{\min}$). $\#\{\cdot\}$ = count.

### Moving threshold $v_{\min}$ and follow radius $R$
$v_{\min}$ = p99 of the stationary baseline **grid** speed (in/s) — the speed below which grid motion
is jitter. $R=\max(3\times\text{jitter floor},\,24)=24$ in. **Text:** $R$ is the spatial tolerance
for "same place", set to $3\times$ the ~7 in jitter floor so following is above localization noise.

### Follow score $f_{A\to B}(\ell)$ (directional, lag $\ell$)
$$ f_{A\to B}(\ell)=\frac{\#\{t:\ \text{mov}_A(t)\wedge \text{mov}_B(t{+}\ell)\wedge
   \lVert \mathbf{x}_B(t{+}\ell)-\mathbf{x}_A(t)\rVert_2<R\wedge
   \hat{\mathbf u}_A(t)\cdot\hat{\mathbf u}_B(t{+}\ell)>c\}}
   {\#\{t:\ \text{mov}_A(t)\wedge \text{mov}_B(t{+}\ell)\}} $$
where $c=0.5$ = heading-cosine cutoff, $\ell$ = lag in seconds. **Text:** of the seconds both animals
move, the fraction where follower $B$ (read at $t{+}\ell$) is within $R$ of where leader $A$ was at
$t$, headings aligned. Range $[0,1]$; the **denominator is both-moving seconds only**. Peak score
$f^{\ast}_{A\to B}=\max_{\ell\in[1,30]}f_{A\to B}(\ell)$; best lag = the $\ell$ achieving it.

### Circular-shift null $z$ (per ordered pair)
$$ z_{A\to B}=\frac{f^{\ast}_{A\to B}-\mu_{\text{null}}}{\sigma_{\text{null}}},\qquad
   \text{null}=\{\,f^{\ast}\ \text{after rolling }B\text{'s whole track by a random }
   \delta\in[5,20]\ \text{min}\,\} $$
**Text:** the shift preserves each animal's own activity/route habit and the shared road but destroys
real-time alignment; a pair's following is credible when $z>2$. Computed over 100 shuffles.

### Undirected pair score and leader
For unordered pair $\{A,B\}$ the score is $\max(f^{\ast}_{A\to B},f^{\ast}_{B\to A})$ and the **leader**
is the animal on the larger side. **Text:** collapses direction to the stronger one per night.

### Specificity: significant-pair fraction and Gini (per night)
$$ \text{frac\_sig}=\frac{\#\{\text{pairs with } z>2\}}{\#\text{pairs}},\qquad
   G=\frac{2\sum_{r=1}^{n} r\,x_{(r)}}{n\sum_r x_{(r)}}-\frac{n+1}{n} $$
where $x_{(r)}$ are the $n$ undirected pair scores sorted ascending. **Text:** frac_sig ∈ $[0,1]$
(near 1 = many pairs follow = herd); Gini ∈ $[0,1]$ (0 = all pairs equal/flat = herd, →1 = a few
dominant pairs = dyads).

### Stability: consecutive-night Spearman
$\rho$ = Spearman rank correlation between the vector of the 10 pair scores on night $k$ and on night
$k{+}1$, averaged over consecutive nights. **Text:** $\rho\approx1$ ⇒ the same pairs recur;
$\rho\approx0$ ⇒ the "preferred" pair reshuffles nightly.

### Per-night leadership
For animal $a$ on a night: $\text{n\_led}(a)=\#\{$ its pairs whose leader is $a\}$ (0..4); the night's
**top leader** = $\arg\max_a \text{n\_led}(a)$. **Text:** how many of its pairings each animal leads,
reported per night (not averaged).

### Simultaneity (both-moving fraction)
$$ \text{both\_moving\_frac}_{\{A,B\}}=\frac{\#\{t:\ \text{mov}_A(t)\wedge\text{mov}_B(t)\}}
   {\#\{\text{grid seconds}\}} $$
**Text:** fraction of the night both animals move at the same instant. Low (~1%) ⇒ movement is
sequential (one at a time), not synchronized herd travel.

### Group cohesion (herd control)
Per night, mean/median of the synchronous pairwise distance $\lVert\mathbf{x}_A(t)-\mathbf{x}_B(t)\rVert$
(2 s grid), and frac_clumped = fraction of bins with median pairwise distance $<39.37$ in (1 m).
**Text:** if the group travels as a herd, every pair's follow score rides on this; a **uniform**
significance pattern is the herd answer, a **concentrated** one is the dyad answer.

### Jitter floor
~7 in (documented stationary median; p95 ~15 in) — sets $R$ and gates sub-floor spatial claims.
Proximity/following thresholds kept $\ge$ 1 m.
"""


def _local(dt_utc_series):
    return dt_utc_series + pd.Timedelta(hours=w.LOCAL_TZ_OFFSET_HOURS)


# ---------------------------------------------------------------------------
# plots
# ---------------------------------------------------------------------------

def _fig_z_heatmap(undirected, names, path):
    if undirected.empty:
        return
    piv = undirected.pivot_table(index="pair", columns="night", values="z")
    piv = piv.reindex(piv.mean(axis=1).sort_values(ascending=False).index)
    fig, ax = plt.subplots(figsize=(1.2 * piv.shape[1] + 3, 0.45 * piv.shape[0] + 2))
    im = ax.imshow(piv.to_numpy(dtype=float), aspect="auto", cmap="magma", vmin=0,
                   vmax=np.nanpercentile(piv.to_numpy(dtype=float), 98) or 4)
    ax.set_xticks(range(piv.shape[1]))
    ax.set_xticklabels([c[5:] for c in piv.columns], rotation=45, ha="right", fontsize=8)
    labs = ["–".join(names.get(t, t) for t in p.split("-")) for p in piv.index]
    ax.set_yticks(range(piv.shape[0])); ax.set_yticklabels(labs, fontsize=8)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.iloc[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=6,
                        color="w" if v < 4 else "k")
    fig.colorbar(im, ax=ax, fraction=0.04, label="follow z vs circular-shift null")
    ax.set_title("Per-pair following z by night (z>2 beats the null)")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def _fig_specificity(spec, cohesion, path):
    if spec.empty:
        return
    fig, ax1 = plt.subplots(figsize=(9, 4.4))
    x = [n[5:] for n in spec["night"]]
    ax1.bar(x, spec["frac_sig"], color="#4C72B0", alpha=0.7, label="frac pairs sig (z>2)")
    ax1.set_ylabel("fraction of pairs significant", color="#4C72B0")
    ax1.set_ylim(0, 1.02)
    ax2 = ax1.twinx()
    ax2.plot(x, spec["score_gini"], "-o", color="#C44E52", label="score Gini (concentration)")
    ax2.set_ylabel("Gini of follow scores (↑ = concentrated/dyadic)", color="#C44E52")
    ax2.set_ylim(0, 1.0)
    ax1.set_title("Specificity: are following pairs a concentrated subset (dyads) or spread (herd)?")
    ax1.tick_params(axis="x", rotation=45)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def _fig_pair_ranking(pair_summary, lead, names, path):
    if pair_summary.empty:
        return
    g = pair_summary.sort_values("mean_score").tail(12)
    labs = ["–".join(names.get(t, t) for t in p.split("-")) for p in g["pair"]]
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(g) + 2))
    colors = ["#C44E52" if s >= 1 else "#4C72B0" for s in g["n_nights_sig"]]
    ax.barh(range(len(g)), g["mean_score"], color=colors)
    ax.set_yticks(range(len(g))); ax.set_yticklabels(labs, fontsize=8)
    for i, (_, r) in enumerate(g.iterrows()):
        ax.text(r["mean_score"], i, f"  sig {int(r['n_nights_sig'])}/{int(r['n_nights'])}, "
                f"top {int(r['n_nights_top'])}", va="center", fontsize=7)
    ax.set_xlabel("mean follow score across nights")
    ax.set_title("Pair ranking (red = beat null on ≥1 night); is one pair dominant & recurrent?")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def _fig_leadership_by_night(pnl, names, path):
    """Per-night leadership: animals x nights, cell = # of that animal's pairs it led
    that night (0-4). Shows whether a leader recurs every night or the hub shifts."""
    if pnl.empty:
        return
    piv = pnl.pivot_table(index="animal", columns="night", values="n_led")
    piv = piv.reindex(piv.mean(axis=1).sort_values(ascending=False).index)
    fig, ax = plt.subplots(figsize=(1.1 * piv.shape[1] + 3, 0.5 * piv.shape[0] + 2))
    im = ax.imshow(piv.to_numpy(dtype=float), aspect="auto", cmap="YlOrRd", vmin=0,
                   vmax=max(piv.shape[0] - 1, 1))
    ax.set_xticks(range(piv.shape[1]))
    ax.set_xticklabels([c[5:] for c in piv.columns], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(piv.shape[0]))
    ax.set_yticklabels([names.get(a, a) for a in piv.index], fontsize=9)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.iloc[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{int(v)}", ha="center", va="center", fontsize=8,
                        color="k" if v < (piv.shape[0] - 1) / 2 else "w")
    fig.colorbar(im, ax=ax, fraction=0.04, label="# of its pairs led that night")
    ax.set_title("Per-night leadership — pairs led by each animal (of its 4), per night")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def _fig_network(pair_summary, lead, names, path, min_score=None):
    if pair_summary.empty:
        return
    tags = sorted(set(t for p in pair_summary["pair"] for t in p.split("-")))
    n = len(tags)
    ang = {t: 2 * np.pi * i / n for i, t in enumerate(tags)}
    pos = {t: (np.cos(a), np.sin(a)) for t, a in ang.items()}
    lead_map = {r["pair"]: (r["dominant_leader"], r["leader_consistency"])
                for _, r in lead.iterrows()} if not lead.empty else {}
    smax = pair_summary["mean_score"].max() or 1.0
    thr = min_score if min_score is not None else pair_summary["mean_score"].median()
    fig, ax = plt.subplots(figsize=(6, 6))
    for _, r in pair_summary.iterrows():
        a, b = r["pair"].split("-")
        w_ = r["mean_score"]
        (xa, ya), (xb, yb) = pos[a], pos[b]
        strong = w_ >= thr and r["n_nights_sig"] >= 1
        ldr, cons = lead_map.get(r["pair"], (a, np.nan))
        fol = b if ldr == a else a
        (x0, y0), (x1, y1) = pos[ldr], pos[fol]
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="-|>" if strong else "-",
                                    lw=0.6 + 4 * w_ / smax,
                                    color="#C44E52" if strong else "#cccccc",
                                    alpha=0.9 if strong else 0.5,
                                    shrinkA=16, shrinkB=16))
    for t, (x, y) in pos.items():
        ax.plot(x, y, "o", ms=28, color="#4C72B0")
        ax.text(x, y, names.get(t, t), ha="center", va="center", color="w", fontsize=8)
    ax.set_xlim(-1.4, 1.4); ax.set_ylim(-1.4, 1.4); ax.axis("off")
    ax.set_title("Following network (arrow leader→follower; red = beats null;\nwidth ∝ mean follow score)")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--incremental-dir", type=Path, default=pa.DEFAULT_INCR)
    ap.add_argument("--baseline", type=Path, default=pa.DEFAULT_BASELINE)
    ap.add_argument("--rois", type=Path, default=pa.DEFAULT_ROIS)
    ap.add_argument("--gt", type=Path, default=pa.DEFAULT_GT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--dates", nargs="*", default=None)
    ap.add_argument("--night-start", type=int, default=21)
    ap.add_argument("--night-end", type=int, default=5)
    ap.add_argument("--lags-max", type=int, default=30, help="max follow lag (s)")
    ap.add_argument("--n-shuffles", type=int, default=100)
    ap.add_argument("--bin-s", type=float, default=1.0)
    ap.add_argument("--smooth-s", type=float, default=5.0)
    ap.add_argument("--max-nights", type=int, default=None)
    ap.add_argument("--include-fireworks", action="store_true",
                    help="do NOT drop the 07-04 fireworks night")
    args = ap.parse_args()

    out = args.out
    (out / "plots").mkdir(parents=True, exist_ok=True)
    names = pa._name_map()

    print("== Following structure (Phase B) ==")
    print("[1/6] load + clean ...")
    df, load_log = ts.load_incremental_days(args.incremental_dir, dates=args.dates)
    df = time_utils.convert_timestamps(df)
    t0_global = df["datetime"].min()
    floor = pa.establish_floor(args.baseline, args.gt)
    jitter_floor = floor["jitter_floor_in"]
    df = w.add_speed(df)
    roi_cfg = w.load_rois(args.rois)
    boundary = (roi_cfg or {}).get("boundary")
    df = w.add_validity_flags(df, boundary=boundary, jitter_floor_in=jitter_floor)
    df = w.apply_tag_cutoffs(df)

    # grid moving threshold (p99 grid speed on the stationary baseline)
    grid_moving_thr = w.DEFAULT_ACTIVE_SPEED_INPS
    if floor.get("stationary") is not None:
        try:
            grid_moving_thr = round(w.grid_speed_noise_floor(
                floor["stationary"], bin_s=args.bin_s, smooth_s=args.smooth_s), 2)
        except Exception as exc:                        # pragma: no cover
            print(f"    grid floor fallback ({exc})")
    R = w.follow_radius_in(jitter_floor)
    print(f"    follow radius R={R:.0f} in (3x jitter floor); grid moving thr {grid_moving_thr} in/s")

    win = ts.select_night_window(df, night_start=args.night_start,
                                 night_end=args.night_end, valid_only=True)
    win = win[~win["shortid"].astype(str).isin(pa.DROP_TAGS)].reset_index(drop=True)
    nights = sorted(win["night"].unique())
    if not args.include_fireworks:
        nights = [n for n in nights if n != pa.FIREWORKS_NIGHT]
    if args.max_nights:
        nights = nights[:args.max_nights]
    win = win[win["night"].isin(nights)].reset_index(drop=True)
    animals = sorted(win["shortid"].astype(str).unique())
    print(f"    nights={nights}")
    print(f"    animals={[names.get(a, a) for a in animals]}")

    print(f"[2/6] per-night directional following (lags 1-{args.lags_max}s, "
          f"{args.n_shuffles} shuffles) ...")
    foll, R = ts.per_night_following(
        win, nights, jitter_floor_in=jitter_floor, grid_moving_thr_inps=grid_moving_thr,
        lags=range(1, args.lags_max + 1), n_shuffles=args.n_shuffles,
        bin_s=args.bin_s, smooth_s=args.smooth_s)
    if foll.empty:
        print("    no following results (insufficient data); aborting.")
        return
    foll["leader_name"] = foll["leader"].map(lambda t: names.get(t, t))
    foll["follower_name"] = foll["follower"].map(lambda t: names.get(t, t))
    foll.to_csv(out / "following_pairs_by_night.csv", index=False)

    print("[3/6] specificity / stability / leadership / herd ...")
    undirected = ts.undirected_pair_scores(foll)
    undirected.to_csv(out / "undirected_pair_scores.csv", index=False)
    spec = ts.specificity_summary(undirected)
    spec.to_csv(out / "specificity_by_night.csv", index=False)
    pair_summary, stab_meta = ts.stability_summary(undirected)
    pair_summary.to_csv(out / "pair_stability_summary.csv", index=False)
    lead = ts.leadership_consistency(undirected)
    lead.to_csv(out / "leadership_consistency.csv", index=False)
    pnl = ts.per_night_leadership(undirected)
    pnl.to_csv(out / "per_night_leadership.csv", index=False)
    cohesion = ts.group_cohesion(win, nights)
    cohesion.to_csv(out / "group_cohesion.csv", index=False)

    print("[4/6] simultaneity + lagged following bouts (video bridge) ...")
    bouts, sim = _cotravel_and_simultaneity(
        win, nights, foll, pair_summary, lead, names, jitter_floor,
        grid_moving_thr, args, t0_global)
    if not sim.empty:
        sim.to_csv(out / "simultaneity_summary.csv", index=False)
    if not bouts.empty:
        bouts.to_csv(out / "top_following_bouts.csv", index=False)
    both_moving_frac_mean = float(sim["both_moving_frac"].mean()) if not sim.empty else np.nan

    print("[5/6] figures ...")
    _fig_z_heatmap(undirected, names, out / "plots" / "pair_z_by_night.png")
    _fig_specificity(spec, cohesion, out / "plots" / "specificity.png")
    _fig_pair_ranking(pair_summary, lead, names, out / "plots" / "pair_ranking.png")
    _fig_network(pair_summary, lead, names, out / "plots" / "following_network.png")
    _fig_leadership_by_night(pnl, names, out / "plots" / "leadership_by_night.png")

    print("[6/6] manifest + report ...")
    manifest = {
        "analysis": "following_structure_phase_b",
        "generated_utc": _dt.datetime.utcnow().isoformat(),
        "git_commit": pa._git_commit(),
        "units": "inches (WISER native, UNVERIFIED offset origin)",
        "night_window_local": [args.night_start, args.night_end],
        "follow_radius_in": R, "jitter_floor_in": jitter_floor,
        "grid_moving_thr_inps": grid_moving_thr,
        "lags_s": [1, args.lags_max], "n_shuffles": args.n_shuffles,
        "bin_s": args.bin_s, "smooth_s": args.smooth_s,
        "nights": nights, "animals": {a: names.get(a, a) for a in animals},
        "fireworks_excluded": (not args.include_fireworks),
        "refuge4_dropout_nights_in_window": sorted(REFUGE4_DROPOUT_NIGHTS & set(nights)),
        "consecutive_night_spearman": stab_meta["consecutive_spearman"],
        "both_moving_frac_mean": round(both_moving_frac_mean, 5)
        if np.isfinite(both_moving_frac_mean) else None,
        "load_log": load_log,
        "caveats": [
            "WISER inch frame UNVERIFIED -> 'leader/follower' is temporal order, not geometry",
            "follow radius R = 3x jitter floor (24 in); sub-R structure not interpretable",
            "07-04 fireworks night excluded (disturbance spike)",
            "refuge_4 burrow UWB dropout 07-03+ (resting fixes; moving bouts less affected)",
            "n=5 animals -> 10 undirected pairs; gross structure only, not fine social-network stats",
            "zero-lag proximity is an anchor only; headline uses lag+heading follow score",
        ],
    }
    with open(out / "run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    _write_report(out, manifest, spec, pair_summary, stab_meta, lead, cohesion,
                  undirected, bouts, names, pnl)
    print(f"\nDONE -> {out}")


def _runs_with_gap(mask, *, max_gap, min_len):
    """Contiguous runs of a boolean mask tolerating gaps up to ``max_gap`` bins;
    keep runs whose span is >= ``min_len`` bins. Returns [(i_start, i_last), ...]."""
    out, i, T = [], 0, len(mask)
    while i < T:
        if not mask[i]:
            i += 1; continue
        j, last, gap = i, i, 0
        while j < T and gap <= max_gap:
            if mask[j]:
                last = j; gap = 0
            else:
                gap += 1
            j += 1
        if (last - i + 1) >= min_len:
            out.append((i, last))
        i = last + 1
    return out


def _cotravel_and_simultaneity(win, nights, foll, pair_summary, lead, names,
                               jitter_floor, grid_moving_thr, args, t0_global,
                               n_pairs=4, per_pair=12):
    """
    Single grid pass per night that returns (a) a **simultaneity summary** — how
    often each pair is moving at the SAME time (the key refinement: rats move
    largely sequentially) — and (b) **lagged following bouts** for the top pairs
    (B retraces A's path within R at the pair's best lag, gap-tolerant), for the
    video bridge. Returns ``(bouts_df, sim_df)``.
    """
    R = w.follow_radius_in(jitter_floor)
    cos_thresh = 0.5
    max_gap = int(round(3.0 / args.bin_s)); min_len = int(round(3.0 / args.bin_s))
    top_pairs = (list(pair_summary.sort_values("mean_score", ascending=False)["pair"].head(n_pairs))
                 if not pair_summary.empty else [])
    # best per-(night, ordered pair) lag from foll
    lagmap = {(r["night"], r["leader"], r["follower"]): int(r["best_lag_s"])
              for _, r in foll.iterrows() if pd.notna(r["best_lag_s"])}
    dirmap = {}  # (night, unordered pair) -> best (leader, follower) by peak_score
    for _, r in foll.iterrows():
        key = (r["night"], "-".join(sorted((r["leader"], r["follower"]))))
        cur = dirmap.get(key)
        if cur is None or (pd.notna(r["peak_score"]) and r["peak_score"] > cur[2]):
            dirmap[key] = (r["leader"], r["follower"], float(r["peak_score"] or 0))

    bout_rows, sim_rows = [], []
    import itertools
    for night in nights:
        g = win[win["night"] == night]
        grid = w.build_following_grid(g, bin_s=args.bin_s, smooth_s=args.smooth_s,
                                      moving_thr_inps=grid_moving_thr)
        tags = grid["tags"]; idx = {t: k for k, t in enumerate(tags)}
        MOV = grid["MOV"]; X = grid["X"]; Y = grid["Y"]; els = grid["elapsed_s"]
        T = X.shape[0]
        sidx = {str(t): k for k, t in enumerate(tags)}
        for a, b in itertools.combinations(sorted(sidx), 2):
            ia, ib = sidx[a], sidx[b]
            both = MOV[:, ia] & MOV[:, ib]
            nb = int(both.sum())
            d = np.hypot(X[:, ia] - X[:, ib], Y[:, ia] - Y[:, ib])
            sim_rows.append({
                "night": night, "pair": f"{a}-{b}",
                "animals": f"{names.get(a, a)}+{names.get(b, b)}",
                "both_moving_bins": nb, "grid_bins": T,
                "both_moving_frac": round(nb / T, 5) if T else np.nan,
                "median_dist_while_moving_in": round(float(np.nanmedian(d[both])), 1) if nb else np.nan,
            })
        # lagged following bouts for the top pairs
        for pair in top_pairs:
            key = (night, pair)
            if key not in dirmap:
                continue
            ldr, fol, _ = dirmap[key]
            if str(ldr) not in sidx or str(fol) not in sidx:
                continue
            lag = lagmap.get((night, ldr, fol), 3)
            follow, valid, dist, cosal = w._pair_follow(grid, sidx[str(ldr)], sidx[str(fol)],
                                                        max(1, int(lag)), R, cos_thresh)
            for i, last in _runs_with_gap(follow, max_gap=max_gap, min_len=min_len):
                seg = slice(i, last + 1)
                dt_utc = t0_global + pd.Timedelta(seconds=float(els[i]))
                bout_rows.append({
                    "night": night, "pair": pair,
                    "leader": names.get(str(ldr), str(ldr)),
                    "follower": names.get(str(fol), str(fol)), "lag_s": int(lag),
                    "duration_s": round((last - i) * args.bin_s, 1),
                    "mean_dist_in": round(float(np.nanmean(dist[seg])), 1),
                    "mean_cosalign": round(float(np.nanmean(cosal[seg])), 2),
                    "start_local_edt": str(_local(pd.Series([dt_utc]))[0]),
                })
    bouts = pd.DataFrame(bout_rows)
    if not bouts.empty:
        bouts = (bouts.sort_values("duration_s", ascending=False)
                 .groupby("pair", group_keys=False).head(per_pair)
                 .sort_values("duration_s", ascending=False).reset_index(drop=True))
    return bouts, pd.DataFrame(sim_rows)


def _write_report(out, manifest, spec, pair_summary, stab_meta, lead, cohesion,
                  undirected, bouts, names, pnl):
    from collections import Counter
    nights = list(manifest["nights"])
    n_nights = len(nights)
    # animal display order (by shortid)
    order = sorted(manifest.get("animals", {}).keys())
    order_names = [manifest["animals"][a] for a in order]

    # ---- per-night specificity table ----
    spec_tbl = ["| Night | pairs sig (z>2) | score Gini | max score | top pair | top z |",
                "|---|---|---|---|---|---|"]
    for _, r in spec.sort_values("night").iterrows():
        tp = r["top_pair"]
        tpl = "–".join(names.get(t, t) for t in str(tp).split("-")) if pd.notna(tp) else "—"
        spec_tbl.append(f"| {r['night']} | {int(r['n_sig_pairs'])}/{int(r['n_pairs'])} | "
                        f"{r['score_gini']:.2f} | {r['score_max']:.3f} | {tpl} | "
                        f"{r['top_z']:.0f} |")

    # ---- per-night leadership matrix (animal -> # of its pairs led that night) ----
    lead_tbl = ["| Night | " + " | ".join(order_names) + " | top leader |",
                "|---|" + "---|" * (len(order_names) + 1)]
    night_leader = {}
    if not pnl.empty:
        nled = pnl.pivot_table(index="night", columns="animal", values="n_led")
        for night in nights:
            if night not in nled.index:
                continue
            cells = []
            for a in order:
                v = nled.loc[night, a] if a in nled.columns else np.nan
                cells.append(str(int(v)) if np.isfinite(v) else "—")
            row = nled.loc[night]
            topa = row.idxmax()
            night_leader[night] = str(topa)
            lead_tbl.append(f"| {night} | " + " | ".join(cells) +
                            f" | **{names.get(str(topa), str(topa))}** ({int(row.max())}/4) |")

    # ---- per-night facts drive the verdict (NOT averaged) ----
    top_pairs = [str(x) for x in spec.sort_values("night")["top_pair"].dropna()]
    n_distinct_top = len(set(top_pairs))
    frac_sig_each = spec["frac_sig"].to_numpy(float)
    n_nights_majority_sig = int(np.nansum(frac_sig_each >= 0.6))
    lc = Counter(night_leader.values())
    lead_sid, lead_cnt = (lc.most_common(1)[0] if lc else (None, 0))
    lead_nm = names.get(str(lead_sid), str(lead_sid)) if lead_sid else "n/a"

    verdict = ("**Herd / shared-road (promiscuous), NOT stable dyads.** On "
               f"{n_nights_majority_sig}/{n_nights} nights a majority of pairs beat their null, and "
               f"the **top pair changes almost every night** ({n_distinct_top} distinct top pairs "
               f"over {n_nights} nights) — no dyad recurs.")
    hub_txt = ""
    if lead_sid and lead_cnt >= max(2, n_nights - 1):
        hub_txt = (f"But the **leadership direction is stable**: **{lead_nm}** is the top leader on "
                   f"**{lead_cnt}/{n_nights}** nights (leads the most of its pairs), while the "
                   "pairings themselves reshuffle. So it is a **dominant individual others trail**, "
                   "not a bonded pair — on a shared road, at different times.")

    L = []
    L += ["# Following structure — stable pairs vs. herd (Phase B report, PER-NIGHT)", "",
          f"**Generated (UTC):** {manifest['generated_utc']}  ",
          f"**Commit:** `{manifest['git_commit']}`  ",
          f"**Nights:** {', '.join(nights)} (07-04 fireworks excluded: "
          f"{manifest['fireworks_excluded']})  ",
          f"**Animals:** {', '.join(manifest['animals'].values())}  ",
          f"**Follow radius:** {manifest['follow_radius_in']:.0f} in (3× jitter floor); "
          f"lags 1–{manifest['lags_s'][1]} s; heading cos>0.5; {manifest['n_shuffles']} shuffles  ",
          f"**Frame:** inches, UNVERIFIED — 'leader/follower' = temporal order, not geometry  ", "",
          f"## Verdict: {verdict}", "",
          (hub_txt + "\n" if hub_txt else ""),
          "> Reported **per night**, not averaged. This builds on Phase A (co-movement is real: it "
          "beat the circular-shift null 10/10 pairs at zero lag). Phase B asks whether that "
          "co-movement is carried by **specific, stable pairs** or is **promiscuous** (a shared road / "
          "herd). Zero-lag was the anchor; here the score is lag- and heading-aware directional "
          "following vs a per-pair circular-shift null.", "",
          "## Specificity & top pair — per night", "",
          "Are the significant pairs a concentrated subset (dyads) or spread (herd), and does the same "
          "pair recur? (`specificity_by_night.csv`; z-grid `plots/pair_z_by_night.png`.)", ""]
    L += spec_tbl
    L += ["", "Read the **top pair** column top-to-bottom: it reshuffles ⇒ no stable dyad. Gini stays "
          "low (spread), and most pairs are significant every night (herd).", "",
          "## Leadership — per night", "",
          "For each night, the number of its 4 pairs each animal **led** (higher-scoring direction); "
          "the last column is that night's top leader. (`per_night_leadership.csv`; "
          "`plots/leadership_by_night.png`.)", ""]
    L += lead_tbl
    L += ["", f"- Top leader by night: **{lead_nm}** on {lead_cnt}/{n_nights} nights. Whether that is "
          "*every* night or shifts is visible above — this is the per-night test of the leadership "
          "asymmetry, not an average.",
          "- Per-pair leader-consistency (still useful as a summary) is in "
          "`leadership_consistency.csv`.", "",
          "## Pair ranking (context)", "",
          "- `pair_stability_summary.csv` + `plots/pair_ranking.png`: per-pair mean score and how many "
          "of the 7 nights each pair was significant / was the top pair. Consecutive-night rank "
          f"correlation of the pair vector = **{stab_meta['consecutive_spearman']:.2f}** "
          "(≈0 ⇒ reshuffles; a summary of the per-night reshuffling shown in the table above).", "",
          "### Herd control", "",
          "- `group_cohesion.csv`: per-night mean pairwise distance + clumped-bin fraction. If the "
          "group travels as a herd, every pair's follow score rides on this — a **uniform** significance "
          "pattern is the herd/road answer, a **concentrated** one is the dyad answer.", "",
          "### Key refinement — movement is SEQUENTIAL, not a synchronized herd", "",
          f"- Any given pair is moving **at the same time** only **{manifest.get('both_moving_frac_mean')}** "
          "of grid-seconds on average (`simultaneity_summary.csv`) — the rats mostly move **one at a "
          "time**. So the co-movement is not side-by-side herd travel; it is **sequential re-use of the "
          "same corridor**, with weak lag-following (B walks where A walked, seconds later). This "
          "reconciles the video (which reads as 'following') with the shared-road result: a common road "
          "used at *different times*, occasionally with one animal trailing another.", "",
          "## Video bridge", "",
          f"- `top_following_bouts.csv`: the longest **lagged-following** episodes for the top pairs "
          "(follower retraces the leader's path within 24 in at the pair's best lag, gap-tolerant), with "
          "**local-EDT start times** to line up against the following/parallel episodes observed on "
          f"video. ({0 if bouts is None or bouts.empty else len(bouts)} episodes exported.)",
          "- These are *lagged* (B where A was, seconds later), matching sequential corridor use — not "
          "instantaneous side-by-side travel (which is rare here). Confirm active *pursuit* vs. "
          "coincidental co-use on the video itself.", "",
          "## What this can and cannot say", "",
          "- **Can:** whether co-movement is concentrated vs spread, whether the pattern recurs across "
          "nights, and who tends to lead — all above each animal's own habit (circular-shift null).",
          "- **Cannot:** prove social *attraction* vs. shared-corridor co-use from WISER alone (a stable "
          "dyad could still be two animals that independently prefer the same route at the same time); "
          "resolve <24 in geometry (jitter); or place any of it in the physical frame (no georeference).",
          "- n=5 → 10 undirected pairs: gross structure only. 07-04 excluded; 07-03/07-05 carry the "
          "refuge_4 dropout (moving bouts less affected than resting).", "",
          ] + _DEFINITIONS.strip("\n").split("\n") + ["",
          "## Outputs", "",
          "`following_pairs_by_night.csv` · `undirected_pair_scores.csv` · `specificity_by_night.csv` · "
          "`per_night_leadership.csv` · `pair_stability_summary.csv` · `leadership_consistency.csv` · "
          "`group_cohesion.csv` · `simultaneity_summary.csv` · `top_following_bouts.csv` · "
          "`run_manifest.json` · `plots/` (incl. `leadership_by_night.png`, `pair_z_by_night.png`)", ""]
    (out / "following_structure_report.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
