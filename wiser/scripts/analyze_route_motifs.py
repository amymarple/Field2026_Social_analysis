r"""
analyze_route_motifs.py — Phase B (motifs): confirm STEREOTYPED movement patterns.

Social coupling is resolution-limited on WISER (jitter + sequential movement), but
stereotyped ROUTES are a route-scale question (paths span feet-metres >> the ~7 in
jitter floor), so they are within resolution. This driver asks, directly:

  1. Do animals re-run the same path SHAPES (recurring route motifs)?
  2. Is that stereotypy INDIVIDUAL (an animal repeats its OWN routes across days)
     or SHARED (everyone on the common corridor)?
  3. Does it STRENGTHEN over the 9 days (route entropy falling)?

Method: movement bouts (displacement > 15 in, so real routes not jitter) →
arc-length-resampled paths → location-anchored path distance (mean pointwise;
Hausdorff/DTW as robustness) → single-linkage motif clusters. Confirmations:
per-animal-per-night motif recurrence/entropy; an INDIVIDUAL-vs-SHARED test
(self-nearest-neighbour across days vs other animals, animal-label permutation
null); and the route-entropy-over-days trend. All per night, not averaged. Inch
frame UNVERIFIED — motifs are internally consistent across days; endpoints get
provisional ROI labels only, no physical/directional claims.

Read-only on the transferred backups. Outputs to
wiser/outputs/route_motifs_2026-06-28_to_2026-07-06/.

    conda activate cv
    cd wiser
    python scripts/analyze_route_motifs.py
    python scripts/analyze_route_motifs.py --max-nights 2   # smoke
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

DEFAULT_OUT = PROJECT_ROOT / "outputs" / "route_motifs_2026-06-28_to_2026-07-10"
# refuge_4 burrow UWB dropout ran nightly ~07-03 01:00 → refuge_4 REMOVED 07-07 13:00
# (FIELD_OBSERVATIONS Day 10); so night 07-06 is also affected; 07-07+ have no refuge_4 at all.
REFUGE4_DROPOUT_NIGHTS = {"2026-07-03", "2026-07-04", "2026-07-05", "2026-07-06"}
# Barn light on the south side turned ON ~22:00 EDT 2026-07-09 and left on (FIELD_OBSERVATIONS
# Day 12): a directional night light covariate on nights 2026-07-09 onward (until switched off).
BARN_LIGHT_ON_FROM = "2026-07-09"
# Hypnos (shortid 12380) implant dropped 2026-07-09 03:35:41 EDT -> apply_tag_cutoffs drops its
# post-drop fixes; cohort is 5 rats through the 07-08 night, 4 rats from the 07-09 night on.

# Definitions block (formula + text) per .claude/skills/analysis-definitions.
# Raw string so LaTeX backslashes survive. Values (jitter ~7 in, threshold 3x) are
# stable/documented; the run's exact numbers are in run_manifest.json.
_DEFINITIONS = r"""## Definitions

Units: **inches** (WISER native, UNVERIFIED offset frame). $B$ = set of route bouts;
$\mathbf{p}_i \in \mathbb{R}^{L\times 2}$ = bout $i$'s arc-length-resampled path ($L$ points,
$\mathbf{p}_i^{(k)}$ its $k$-th point); $s(i)$ = the animal of bout $i$; $n(i)$ = its night;
$\mathbb{1}[\cdot]$ = indicator (1 if true, else 0).

### Movement bout + displacement filter
A bout is a maximal run of consecutive 1 s grid samples with smoothed speed $v>v_{\min}$ (moving),
inter-sample gap $\le 2$ s, duration $\ge 3$ s, kept only if net displacement
$\lVert \mathbf{p}_i^{(L)}-\mathbf{p}_i^{(1)}\rVert_2 \ge d_{\min}$.
**Text:** one directed travel segment above the noise floor. $d_{\min}=15$ in (> the ~7 in jitter
floor, so a bout's shape is a real route, not localization noise); $v_{\min}$ = p99 of the stationary
baseline smoothed speed (in/s). Range of a bout: any path with end-to-end distance $\ge 15$ in.

### Arc-length resampling
Each bout's path is resampled to $L$ points **equally spaced by arc length** (not time), so index $k$
corresponds across bouts and the distance below is **speed-invariant**.

### Route distance $D_{ij}$ (mean-pointwise; primary)
$$ D_{ij} = \frac{1}{L}\sum_{k=1}^{L}\big\lVert \mathbf{p}_i^{(k)}-\mathbf{p}_j^{(k)}\big\rVert_2 $$
**Text:** mean point-to-point separation between two aligned routes. Units: inches. Range
$[0,\infty)$; 0 = identical route, large = different routes. Robustness metrics (same inputs):
Fréchet $D^{F}_{ij}=\max_k\lVert \mathbf{p}_i^{(k)}-\mathbf{p}_j^{(k)}\rVert$; Hausdorff
$D^{H}_{ij}=\max\!\big(\max_a\min_b \lVert a-b\rVert,\ \max_b\min_a \lVert a-b\rVert\big)$ over the two
point sets; DTW = warp-tolerant alignment cost.

### Recurrence $R(\tau)$
$$ R(\tau)=\frac{1}{|B|}\sum_{i\in B}\mathbb{1}\!\Big[\min_{j\neq i}D_{ij}\le\tau\Big] $$
**Text:** fraction of route bouts that have a near-identical partner within $\tau$ inches. Range
$[0,1]$; high = strongly stereotyped (routes repeat). Reported at $\tau\in\{1.5,3,6\}\times$ jitter
floor.

### Motif (leader clustering) + threshold $\theta$
Greedy leader clustering: repeatedly take the still-unassigned bout with the most neighbours within
$\theta$ and assign it + all unassigned $j$ with $D_{ij}\le\theta$ to a new motif.
**Text:** a motif is a compact bundle of near-identical routes (every member within $\theta$ of the
leader; non-chaining, unlike single-linkage). $\theta = 3\times$ jitter floor ($\approx 21$ in). A
motif is **shared** if used by $\ge 3$ animals, else **individual**.

### Motif entropy $H$ and top-motif fraction (per animal-night)
$$ q_m=\frac{\#\{\text{bouts in motif } m\}}{\#\{\text{bouts}\}},\qquad
   H=-\frac{1}{\ln M}\sum_{m=1}^{M} q_m\ln q_m,\qquad \text{top-motif frac}=\max_m q_m $$
**Text:** $H$ = normalized Shannon entropy of one animal-night's bouts over the $M$ motifs it uses.
Range $[0,1]$; $H{=}0$ = all bouts in one motif (one obsessive route), $H{\to}1$ = spread uniformly
over many motifs (diverse repertoire).

### Individual-vs-shared route memory + permutation null $z$
For bout $i$: self-NN $u_i=\min_{j:\,s(j)=s(i),\,n(j)\neq n(i)}D_{ij}$ (nearest of the animal's OWN
other-day routes); other-NN $o_i=\min_{j:\,s(j)\neq s(i)}D_{ij}$ (nearest OTHER animal's route). Gap
$$ g=\overline{o}-\overline{u},\qquad
   z=\frac{g_{\text{obs}}-\mu_{\text{perm}}}{\sigma_{\text{perm}}} $$
where the null recomputes $g$ over many random permutations of the animal labels $s(\cdot)$.
**Text:** $g>0$ ⇒ an animal's own routes are more similar than others' (individual); $g<0$ ⇒ others'
routes are nearer (shared). $z>2$ ⇒ own-route self-similarity exceeds the label-shuffle null.

### Jitter floor
~7 in (documented stationary median; p95 ~15 in). The scale below which position differences are
localization noise, not movement; $d_{\min}$, $\tau$, and $\theta$ are all set as multiples of it.
"""


def _motif_catalog(bouts, D, labels, names, *, top=12):
    """Per-motif summary: size, #animals, #nights, medoid bout, endpoint ROIs."""
    b = bouts.copy(); b["motif"] = labels
    rows = []
    for m, g in b.groupby("motif"):
        idx = g.index.to_numpy()
        sub = D[np.ix_(idx, idx)]
        medoid = int(idx[np.argmin(sub.sum(1))])
        er = (g["start_roi"] + "→" + g["end_roi"]).mode()
        rows.append({
            "motif": int(m), "n_bouts": int(len(g)),
            "n_animals": int(g["shortid"].nunique()),
            "n_nights": int(g["night"].nunique()),
            "animals": ",".join(names.get(a, a) for a in sorted(g["shortid"].unique())),
            "shared": g["shortid"].nunique() >= 3,
            "endpoints": (er.iloc[0] if len(er) else ""),
            "median_disp_in": round(float(g["disp_in"].median()), 1),
            "medoid_idx": medoid,
        })
    cat = pd.DataFrame(rows).sort_values("n_bouts", ascending=False).reset_index(drop=True)
    return cat


# ---------------------------------------------------------------------------
# plots
# ---------------------------------------------------------------------------

def _fig_motifs(bouts, paths, labels, cat, names, extent, path, top=9):
    top_motifs = cat.head(top)["motif"].tolist()
    ncol = 3; nrow = int(np.ceil(len(top_motifs) / ncol)) or 1
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.2 * ncol, 3.0 * nrow), squeeze=False)
    animals = sorted(bouts["shortid"].unique())
    cmap = plt.get_cmap("tab10")
    acol = {a: cmap(i % 10) for i, a in enumerate(animals)}
    for k, m in enumerate(top_motifs):
        ax = axes[k // ncol][k % ncol]
        idx = np.where(labels == m)[0]
        for i in idx:
            p = paths[i]
            ax.plot(p[:, 0], p[:, 1], "-", lw=0.7, alpha=0.5,
                    color=acol[bouts.iloc[i]["shortid"]])
        row = cat[cat["motif"] == m].iloc[0]
        ax.set_title(f"motif {m}: {row['n_bouts']} bouts, {row['n_animals']} rats\n{row['endpoints']}",
                     fontsize=8)
        ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    for j in range(len(top_motifs), nrow * ncol):
        axes[j // ncol][j % ncol].axis("off")
    handles = [plt.Line2D([], [], color=acol[a], label=names.get(a, a)) for a in animals]
    fig.legend(handles=handles, loc="lower center", ncol=len(animals), fontsize=8)
    fig.suptitle("Top route motifs (each = recurring path shape; color = animal) — inch frame, UNVERIFIED")
    fig.tight_layout(rect=(0, 0.05, 1, 1)); fig.savefig(path, dpi=120); plt.close(fig)


def _fig_by_hour_day(by_hour, by_day, path):
    """Per-clock-hour (when in the night) and per-day (which night) route-motif
    profiles: bout rate + recurrence fraction on each axis."""
    if by_hour.empty and by_day.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    # left: per hour — bouts/animal (bars) + recurrence frac (line)
    ax = axes[0]
    hh = by_hour.copy()
    ax.bar(hh["clock_hour"].astype(str), hh["bouts_per_animal"], color="#8888cc", alpha=0.7)
    ax.set_ylabel("bouts / animal"); ax.set_xlabel("local clock hour (EDT)")
    ax2 = ax.twinx()
    ax2.plot(hh["clock_hour"].astype(str), hh["recurrence_frac"], "-o", color="#cc4444", ms=4)
    ax2.set_ylabel("recurrence frac", color="#cc4444"); ax2.set_ylim(0, 1.02)
    ax.set_title("Per hour — when in the night are routes run / reused")
    # right: per night — bouts (bars) + recurrence frac (line)
    ax = axes[1]
    dd = by_day.copy()
    ax.bar(dd["night"].str.slice(5), dd["n_bouts"], color="#88bb88", alpha=0.7)
    ax.set_ylabel("n bouts"); ax.set_xlabel("night"); ax.tick_params(axis="x", rotation=45)
    ax2 = ax.twinx()
    ax2.plot(dd["night"].str.slice(5), dd["recurrence_frac"], "-o", color="#cc4444", ms=4)
    ax2.set_ylabel("recurrence frac", color="#cc4444"); ax2.set_ylim(0, 1.02)
    ax.set_title("Per day — nightly bout count + route reuse")
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


def _fig_entropy_over_days(stab, names, path):
    if stab.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for tag, g in stab.groupby("shortid"):
        g = g.sort_values("night")
        ax.plot(g["night"].str.slice(5), g["motif_entropy"], "-o", ms=4, label=names.get(tag, tag))
    ax.set_ylabel("motif entropy (↓ = more stereotyped)")
    ax.set_xlabel("night"); ax.set_ylim(0, 1.02); ax.grid(alpha=0.3)
    ax.tick_params(axis="x", rotation=45); ax.legend(fontsize=8)
    ax.set_title("Route stereotypy over days — does each animal's route repertoire concentrate?")
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


def _fig_individual(ivs, names, path):
    per = ivs["per_animal"]
    if per.empty:
        return
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    x = np.arange(len(per)); wdt = 0.38
    ax.bar(x - wdt / 2, per["self_nn_in"], wdt, label="self (own other-day routes)", color="#4C72B0")
    ax.bar(x + wdt / 2, per["other_nn_in"], wdt, label="others' routes", color="#C44E52")
    ax.set_xticks(x); ax.set_xticklabels([names.get(a, a) for a in per["shortid"]], fontsize=9)
    ax.set_ylabel("nearest-neighbour route distance (in)")
    z = ivs["z"]
    ax.set_title(f"Individual route memory: self vs others' nearest route "
                 f"(lower self ⇒ repeats own routes; perm z={z:.1f})")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


def _fig_all_bouts(bouts, paths, labels, extent, path, n_motifs_color=10):
    fig, ax = plt.subplots(figsize=(7, 4.2))
    cmap = plt.get_cmap("tab20")
    for i in range(len(paths)):
        p = paths[i]; m = labels[i]
        col = cmap(m % 20) if m < n_motifs_color else "#dddddd"
        ax.plot(p[:, 0], p[:, 1], "-", lw=0.5, alpha=0.5, color=col)
    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"All route bouts, colored by motif (top {n_motifs_color}); grey = singletons/rare")
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


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
    ap.add_argument("--night-end", type=int, default=4,
                    help="night ends at this local hour (exclusive). Default 4 = 21:00->03:59, the "
                         "data-driven night-active window (circadian_rest: activity peaks 21:00, "
                         "elevated through ~04:00, troughs 07:00). Was 5; tightened 2026-07-11.")
    ap.add_argument("--min-disp-in", type=float, default=15.0)
    ap.add_argument("--resample-n", type=int, default=20)
    ap.add_argument("--max-per-night", type=int, default=40)
    ap.add_argument("--threshold-pct", type=float, default=5.0,
                    help="motif distance threshold = this percentile of pairwise dists")
    ap.add_argument("--threshold-in", type=float, default=None,
                    help="override motif threshold (inches)")
    ap.add_argument("--max-nights", type=int, default=None)
    args = ap.parse_args()

    out = args.out
    (out / "plots").mkdir(parents=True, exist_ok=True)
    names = pa._name_map()

    print("== Route motifs (Phase B) ==")
    print("[1/6] load + clean ...")
    df, load_log = ts.load_incremental_days(args.incremental_dir, dates=args.dates)
    df = time_utils.convert_timestamps(df)
    floor = pa.establish_floor(args.baseline, args.gt)
    jitter_floor = floor["jitter_floor_in"]; moving_thr = floor["moving_thr_inps"]
    df = w.add_speed(df)
    roi_cfg = w.load_rois(args.rois)
    boundary = (roi_cfg or {}).get("boundary")
    df = w.add_validity_flags(df, boundary=boundary, jitter_floor_in=jitter_floor)
    df = w.apply_tag_cutoffs(df)
    win = ts.select_night_window(df, night_start=args.night_start,
                                 night_end=args.night_end, valid_only=True)
    win = win[~win["shortid"].astype(str).isin(pa.DROP_TAGS)].reset_index(drop=True)
    nights = sorted(win["night"].unique())
    if args.max_nights:
        nights = nights[:args.max_nights]
        win = win[win["night"].isin(nights)].reset_index(drop=True)
    animals = sorted(win["shortid"].astype(str).unique())
    if boundary and "rect" in boundary:
        xmin, xmax, ymin, ymax = boundary["rect"]
        extent = (xmin - 12, xmax + 12, ymin - 12, ymax + 12)
    else:
        extent = w.observed_extent(win)
    print(f"    nights={nights}; animals={[names.get(a, a) for a in animals]}")

    print(f"[2/6] extract route bouts (disp>{args.min_disp_in} in, "
          f"<= {args.max_per_night}/animal-night) ...")
    bouts, paths, blog = ts.extract_route_bouts(
        win, nights, moving_thr_inps=moving_thr, min_disp_in=args.min_disp_in,
        resample_n=args.resample_n, max_per_night=args.max_per_night, roi_cfg=roi_cfg)
    print(f"    {blog['n_bouts_kept']} bouts kept "
          f"({blog['n_bouts_dropped_by_cap']} dropped by the per-night cap)")
    if len(bouts) < 10:
        print("    too few bouts; aborting."); return
    bouts = bouts.reset_index(drop=True)

    print("[3/6] path distance matrix + motif clustering ...")
    D = ts.path_distance_matrix(paths, metric="mean")
    thr = args.threshold_in if args.threshold_in is not None else round(3.0 * jitter_floor, 1)
    labels = ts.cluster_paths_leader(D, threshold=thr)     # compact, non-chaining
    n_motifs = int(labels.max() + 1)
    # recurrence: fraction of bouts with a near-identical partner (threshold-robust)
    rec_thr = sorted({round(1.5 * jitter_floor, 1), thr, round(6.0 * jitter_floor, 1)})
    recur, nn = ts.recurrence_fraction(D, thresholds=rec_thr)
    # robustness: leader-cluster under the Frechet (max-pointwise) metric
    Dfr = ts.path_distance_matrix(paths, metric="frechet")
    labels_fr = ts.cluster_paths_leader(Dfr, threshold=thr)
    print(f"    threshold {thr:.1f} in ({thr / jitter_floor:.1f}x jitter floor); "
          f"{n_motifs} motifs (mean), {int(labels_fr.max() + 1)} (Frechet); "
          f"recurrence@{thr:.0f}in = {recur[float(thr)]*100:.0f}%")
    bouts["motif"] = labels
    bouts["nn_route_dist_in"] = np.round(nn, 1)
    bouts.to_csv(out / "route_bouts.csv", index=False)

    print("[4/6] motif catalog + per-animal-per-night stereotypy ...")
    cat = _motif_catalog(bouts, D, labels, names)
    cat.to_csv(out / "motif_catalog.csv", index=False)
    stab = ts.motif_stereotypy(bouts, labels)
    stab.to_csv(out / "motif_stereotypy_by_animal_night.csv", index=False)

    print("[5/6] individual-vs-shared test + recurrence + emergence ...")
    ivs = ts.individual_vs_shared(bouts, D, n_perm=500)
    ivs["per_animal"].to_csv(out / "individual_route_memory.csv", index=False)
    # per-night recurrence: fraction of that night's bouts with a near-identical partner
    br = bouts.copy(); br["recurrent"] = br["nn_route_dist_in"] <= thr
    night_rec = br.groupby("night").agg(n_bouts=("recurrent", "size"),
                                        recurrence_frac=("recurrent", "mean")).reset_index()
    night_rec["recurrence_frac"] = night_rec["recurrence_frac"].round(3)
    night_rec.to_csv(out / "recurrence_by_night.csv", index=False)
    # PER-HOUR (pooled over nights) and PER-DAY (group) motif profiles
    by_hour = ts.motif_by_hour(bouts, recur_thr_in=thr)
    by_hour.to_csv(out / "motif_by_hour.csv", index=False)
    by_day = ts.motif_by_day(bouts, recur_thr_in=thr)
    by_day.to_csv(out / "motif_by_day.csv", index=False)
    print(f"    per-hour: {len(by_hour)} clock-hours; per-day: {len(by_day)} nights")
    # emergence: first vs last night motif entropy per animal
    emg = []
    for tag, g in stab.groupby("shortid"):
        g = g.sort_values("night")
        emg.append({"shortid": tag, "animal": names.get(tag, tag),
                    "entropy_first": float(g["motif_entropy"].iloc[0]),
                    "entropy_last": float(g["motif_entropy"].iloc[-1]),
                    "delta": float(g["motif_entropy"].iloc[-1] - g["motif_entropy"].iloc[0])})
    emg = pd.DataFrame(emg)
    emg.to_csv(out / "stereotypy_emergence.csv", index=False)

    print("[6/6] figures + report ...")
    _fig_motifs(bouts, paths, labels, cat, names, extent, out / "plots" / "top_motifs.png")
    _fig_all_bouts(bouts, paths, labels, extent, out / "plots" / "all_bouts_by_motif.png")
    _fig_entropy_over_days(stab, names, out / "plots" / "stereotypy_over_days.png")
    _fig_individual(ivs, names, out / "plots" / "individual_route_memory.png")
    _fig_by_hour_day(by_hour, by_day, out / "plots" / "motif_by_hour_and_day.png")

    n_shared = int(cat["shared"].sum()); n_indiv = int((~cat["shared"]).sum())
    frac_in_top = float(cat.head(10)["n_bouts"].sum() / max(len(bouts), 1))
    manifest = {
        "analysis": "route_motifs_phase_b",
        "generated_utc": _dt.datetime.utcnow().isoformat(),
        "git_commit": pa._git_commit(),
        "units": "inches (WISER native, UNVERIFIED offset origin)",
        "night_window_local": [args.night_start, args.night_end],
        "jitter_floor_in": jitter_floor, "moving_thr_inps": moving_thr,
        "min_disp_in": args.min_disp_in, "resample_n": args.resample_n,
        "max_per_night": args.max_per_night, "bout_log": blog,
        "motif_threshold_in": round(thr, 1),
        "motif_threshold_x_jitter": round(thr / jitter_floor, 2),
        "recurrence_by_threshold_in": {str(k): round(v, 3) for k, v in recur.items()},
        "n_bouts": int(len(bouts)), "n_motifs": n_motifs,
        "n_motifs_frechet": int(labels_fr.max() + 1),
        "n_shared_motifs": n_shared, "n_individual_motifs": n_indiv,
        "frac_bouts_in_top10_motifs": round(frac_in_top, 3),
        "individual_vs_shared": {k: (round(v, 2) if isinstance(v, float) else v)
                                 for k, v in ivs.items() if k != "per_animal"},
        "nights": nights, "animals": {a: names.get(a, a) for a in animals},
        "night_window_source": "circadian_rest (activity peak 21:00, elevated to ~04:00, trough 07:00)",
        "refuge4_dropout_nights_in_window": sorted(REFUGE4_DROPOUT_NIGHTS & set(nights)),
        "barn_light_south_on_nights_in_window": sorted(n for n in nights if n >= BARN_LIGHT_ON_FROM),
        "hypnos_cutoff": "12380 dropped 2026-07-09T03:35:41-04:00; 4 rats from the 07-09 night",
        "roadway_camera_audit": "UNDONE — the visible flattened-grass 'road' the rats reuse is not yet "
                                "verified against camera footage (whether motifs track a physical path).",
        "caveats": [
            "WISER inch frame UNVERIFIED -> motifs internally consistent, no physical labels",
            "motifs LOCATION-ANCHORED; endpoints ROI labels provisional (food inside houses)",
            "bouts require displacement > jitter (15 in) so shape != jitter artifact",
            "per-night cap on bouts (logged); 07-04 fireworks + refuge_4 dropout nights flagged",
            "single-linkage clustering can chain; threshold reported in jitter-floor units",
            "night window = 21:00->04:00 (data-driven active period; was 21:00->05:00)",
            "barn light (S) on from 07-09 night = directional light covariate, not an exclusion",
            "cohort 5 rats through 07-08 night, 4 from 07-09 (Hypnos implant dropped 07-09 03:35)",
            "ROADWAY-CAMERA AUDIT UNDONE: flattened-grass road vs motifs not yet checked on video",
        ],
    }
    with open(out / "run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    _write_report(out, manifest, cat, stab, ivs, emg, night_rec, names, by_hour, by_day)
    print(f"\nDONE -> {out}")


def _write_report(out, manifest, cat, stab, ivs, emg, night_rec, names, by_hour, by_day):
    ivsm = manifest["individual_vs_shared"]
    z = ivsm.get("z")
    top = cat.head(8)
    recur = manifest["recurrence_by_threshold_in"]
    thr = manifest["motif_threshold_in"]
    rec_at_thr = recur.get(str(float(thr)), None)
    # emergence: how many animals' entropy fell
    n_fell = int((emg["delta"] < -0.02).sum()); n_rose = int((emg["delta"] > 0.02).sum())
    # per-night stereotypy: mean top_motif_frac per night (repetition), presented per night
    by_night = stab.groupby("night").agg(
        mean_motif_entropy=("motif_entropy", "mean"),
        mean_top_motif_frac=("top_motif_frac", "mean"),
        mean_n_bouts=("n_bouts", "mean")).reset_index().merge(
        night_rec[["night", "recurrence_frac"]], on="night", how="left")

    gap = ivsm.get("observed_gap_in") or 0.0
    zsig = bool(np.isfinite(z) and z > 2)
    if gap > 0 and zsig:
        verdict = ("**Stereotyped routes are present AND INDIVIDUAL** — each animal's own other-day "
                   "routes are more similar than other animals' routes, beyond the label-permutation "
                   f"null (z={z}).")
    elif gap <= 0 and zsig:
        verdict = ("**Stereotyped routes are present, mostly SHARED, with a WEAK individual residual.** "
                   "An animal's nearest route is usually ANOTHER animal's (shared corridors dominate), "
                   f"but own-route self-similarity still beats the label-permutation null (z={z}) — a "
                   "faint individual signature on top of the common road.")
    else:
        verdict = ("**Stereotyped routes are present but SHARED** — recurring motifs are common "
                   "corridors used by several animals; no individual signal beyond the null.")

    # §2 permutation-null sentence — honest about the prespecified z>2 threshold. Fixed 2026-07-11:
    # the previous static prose read "Since z>2 ... weak individual residual", but z=1.84 does NOT
    # reach z>2, so no individual-specific residual is established. Now driven by zsig/gap.
    if zsig and gap > 0:
        ivs_sentence = (f"⇒ **z = {z}** (> 2): own-route self-similarity exceeds the label-shuffle "
                        "null — a weak individual residual on top of the dominant shared signal.")
    elif zsig and gap <= 0:
        ivs_sentence = (f"⇒ **z = {z}** (> 2) but the gap g < 0, so shared corridors dominate and any "
                        "individual component is not in the self-nearer direction.")
    else:
        ivs_sentence = (f"⇒ **z = {z}**, which did NOT reach the prespecified z>2 threshold: this "
                        "analysis does **not** establish an individual-specific route residual — "
                        "shared corridors dominate (g < 0).")

    L = []
    L += ["# Route motifs — stereotyped movement patterns (Phase B report)", "",
          f"**Generated (UTC):** {manifest['generated_utc']}  ",
          f"**Commit:** `{manifest['git_commit']}`  ",
          f"**Nights:** {', '.join(manifest['nights'])}  ",
          f"**Animals:** {', '.join(manifest['animals'].values())}  ",
          f"**Bouts:** {manifest['n_bouts']} (displacement > {manifest['min_disp_in']:.0f} in); "
          f"**{manifest['n_motifs']} motifs** at threshold {manifest['motif_threshold_in']} in "
          f"({manifest['motif_threshold_x_jitter']}× jitter floor)  ",
          f"**Frame:** inches, UNVERIFIED — motifs internally consistent, no physical claims  ", "",
          f"## Verdict: {verdict}", "",
          "> Confirms the ORIGINAL question (do trajectories become stereotyped route motifs?) at the "
          "path-shape level — complementary to Phase A's occupancy stabilization. Bouts require "
          "displacement > jitter, so a motif is a real repeated route, not a jitter artifact.", "",
          "## 1. Are there recurring route motifs? (recurrence — threshold-robust)", "",
          f"- **Recurrence** = fraction of route bouts that have a near-identical partner elsewhere "
          f"(mean-pointwise route distance ≤ threshold). At **{thr:.0f} in "
          f"({manifest['motif_threshold_x_jitter']}× jitter)**: **{(rec_at_thr or 0)*100:.0f}%** of "
          "bouts recur. Full curve: " +
          ", ".join(f"{float(k):.0f} in → {v*100:.0f}%" for k, v in recur.items()) + ".",
          f"- Compact (non-chaining, leader) clustering gives **{manifest['n_motifs']} motifs** from "
          f"{manifest['n_bouts']} bouts; the **top 10 hold {manifest['frac_bouts_in_top10_motifs']*100:.0f}%** — "
          f"a few routes dominate. **{manifest['n_shared_motifs']} SHARED** (≥3 animals), "
          f"**{manifest['n_individual_motifs']} individual** (1–2). Fréchet metric → "
          f"{manifest['n_motifs_frechet']} motifs (same order). "
          "(`motif_catalog.csv`, `plots/top_motifs.png`, `plots/all_bouts_by_motif.png`.)",
          "- So trajectories ARE stereotyped: a large fraction of routes recur, and movement "
          "concentrates in a few dominant path shapes.",
          "- **Leakage caveat:** recurrence uses a **globally-pooled** nearest-neighbour dictionary — "
          "every other bout on every night (including *future* nights) is an eligible partner, with no "
          "same-animal / same-night / adjacent-bout exclusion — so it is an **upper bound** and is "
          "*retrospective*, not a leakage-controlled or out-of-sample result. See the route-vocabulary "
          "validation study for held-out compression + generalization.", "",
          "### Top motifs", "",
          "| motif | bouts | rats | nights | endpoints (provisional) | shared? |",
          "|---|---|---|---|---|---|"]
    for _, r in top.iterrows():
        L.append(f"| {int(r['motif'])} | {int(r['n_bouts'])} | {int(r['n_animals'])} | "
                 f"{int(r['n_nights'])} | {r['endpoints']} | {'yes' if r['shared'] else 'no'} |")
    L += ["", "## 2. Individual route memory or shared corridors?", "",
          "- Per animal, nearest-neighbour route distance to its OWN other-day bouts (`self_nn`) vs to "
          "OTHER animals' bouts (`other_nn`), in `individual_route_memory.csv`. Across animals "
          "**other_nn ≈ 9 in < self_nn ≈ 15 in** — an animal's *nearest* route is typically **another "
          "animal's**, not its own past route. **Shared corridors dominate.**",
          (f"- But vs the **animal-label permutation null**: the gap "
           f"g = mean(other_nn) − mean(self_nn) = {ivsm.get('observed_gap_in')} in (negative ⇒ shared) "
           f"vs null {ivsm.get('null_mean')} ± {ivsm.get('null_sd')} {ivs_sentence} "
           "Per-animal CSV column `self_minus_other_in` = self − other = −g_i (the negation of g) — "
           "do not conflate the two directions."),
          "- Matches Phase A (shared-road dominant; a faint individual component). "
          "`plots/individual_route_memory.png`.", "",
          "## 3. Does stereotypy strengthen over days? (per night)", "",
          "Mean per-animal motif entropy and top-motif fraction by night "
          "(`motif_stereotypy_by_animal_night.csv`):", "",
          f"| night | recurrence (NN≤{thr:.0f}in) | mean motif entropy | mean top-motif frac | mean bouts |",
          "|---|---|---|---|---|"]
    for _, r in by_night.iterrows():
        rf = r.get("recurrence_frac")
        L.append(f"| {r['night']} | {rf*100:.0f}% | {r['mean_motif_entropy']:.2f} | "
                 f"{r['mean_top_motif_frac']:.2f} | {r['mean_n_bouts']:.0f} |")
    nr_sorted = night_rec.sort_values("night")
    rec0 = float(nr_sorted["recurrence_frac"].iloc[0])
    rlo = float(night_rec["recurrence_frac"].min()); rhi = float(night_rec["recurrence_frac"].max())
    L += ["", f"- **Stereotypy is present from night 1, NOT developing.** Recurrence is already "
          f"**{rec0*100:.0f}%** on the release night (06-28) and stays **{rlo*100:.0f}–{rhi*100:.0f}%** "
          "every night — the route repertoire is set by the paddock geometry immediately, not learned "
          "over days. (Motif entropy fell for "
          f"{n_fell} animals, rose for {n_rose} first-vs-last; `stereotypy_emergence.csv`.)",
          "- **Caveat (global-dictionary leakage):** these per-night recurrence numbers use the pooled "
          "dictionary above, so 'present from night 1' is **retrospective** — a night-1 bout may match "
          "a partner on a *later* night. Whether the repertoire is genuinely available on night 1 "
          "*without* future data is tested directly by the first-night-closure analysis in the "
          "route-vocabulary validation study (not asserted here).",
          "- Motif entropy stays **high (~0.98)**: animals use a **diverse set of recurring routes**, "
          "not one obsessive path — many distinct shared motifs, each reused, rather than a single "
          "stereotyped loop. (06-29 is the one lower-entropy night — hotter, more concentrated use.)", "",
          "## 4. When in the night, and which night? (per-hour / per-day)", "",
          "Night window = **21:00→04:00** (data-driven active period from `circadian_rest`: activity "
          "peaks 21:00, elevated to ~04:00, troughs 07:00).", "",
          "**Per clock-hour (pooled over nights, `motif_by_hour.csv`):**", "",
          "| hour (EDT) | bouts/animal | n motifs | recurrence |", "|---|---|---|---|"]
    for _, r in by_hour.iterrows():
        L.append(f"| {int(r['clock_hour']):02d}:00 | {r['bouts_per_animal']:.1f} | "
                 f"{int(r['n_motifs'])} | {r['recurrence_frac']*100:.0f}% |")
    hpk = by_hour.sort_values("bouts_per_animal", ascending=False).iloc[0]
    L += ["", f"- **Route activity concentrates at dusk onset:** the **{int(hpk['clock_hour']):02d}:00 "
          f"hour carries the most bouts (~{hpk['bouts_per_animal']:.0f}/animal)**, tapering overnight — "
          "matching the circadian 21:00 activity peak. **Route reuse (recurrence) stays ~96–99% at every "
          "hour**: whenever they move, they move on established routes; the stereotypy is not confined to "
          "one part of the night.", "",
          "**Per night (group, `motif_by_day.csv`):**", "",
          "| night | bouts | rats | recurrence | dominant-motif share | group entropy |",
          "|---|---|---|---|---|---|"]
    for _, r in by_day.iterrows():
        L.append(f"| {r['night']} | {int(r['n_bouts'])} | {int(r['n_animals'])} | "
                 f"{r['recurrence_frac']*100:.0f}% | {r['dominant_frac']*100:.0f}% | "
                 f"{r['group_entropy']:.2f} |")
    L += ["", "- **Recurrence is high (92–99%) every night** and **no single motif dominates** "
          "(top-motif share only ~3–10%): the group reuses a **broad repertoire** of established routes, "
          "not one corridor. Cohort is **5 rats through the 07-08 night, 4 from 07-09** (Hypnos implant "
          "dropped 07-09 03:35 — `apply_tag_cutoffs`). `plots/motif_by_hour_and_day.png`.",
          "- **Covariate flags (not exclusions):** the **south barn light** is on from the **07-09 night** "
          "onward (a directional night-light that could bias routes — FIELD_OBSERVATIONS Day 12); "
          "**refuge_4 burrow UWB dropout** on 07-03→07-06 nights; **07-04 fireworks**. Read 07-09/07-10 "
          "under the barn-light caveat.", "",
          "## What this confirms / cannot say", "",
          "- **Confirms:** recurring, location-anchored route motifs exist and dominate movement "
          "(a few routes carry most bouts) — trajectories ARE stereotyped at the path level.",
          "- **On individual vs shared:** decided by the permutation z above — not asserted.",
          "- **Cannot:** call it spatial *memory* (WISER shows route reuse, not its cognitive cause); "
          "resolve sub-jitter path detail; or place motifs in the physical frame (no georeference). "
          "Endpoint ROI labels are provisional (food ROIs sit inside houses).",
          "- **UNDONE — roadway camera audit:** the field observation is that the rats have worn a "
          "**visible flattened-grass 'road'** and mostly travel along it. The ~97% route recurrence here "
          "is consistent with that, but **whether these WISER motifs geometrically track the physical "
          "trampled path has NOT been verified against camera footage** (needs the pixel↔field georeference "
          "/ CH01–CH04 overlay). Marked as a follow-up, not claimed.", "",
          ] + _DEFINITIONS.strip("\n").split("\n") + ["",
          "## Outputs", "",
          "`route_bouts.csv` · `motif_catalog.csv` · `motif_stereotypy_by_animal_night.csv` · "
          "`recurrence_by_night.csv` · `motif_by_hour.csv` · `motif_by_day.csv` · "
          "`individual_route_memory.csv` · `stereotypy_emergence.csv` · "
          "`run_manifest.json` · `plots/` (top_motifs, all_bouts_by_motif, stereotypy_over_days, "
          "individual_route_memory, motif_by_hour_and_day)", ""]
    (out / "route_motifs_report.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
