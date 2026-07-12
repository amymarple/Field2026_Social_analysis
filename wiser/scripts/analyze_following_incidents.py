r"""
analyze_following_incidents.py — Phase B2: strict-following INCIDENT frequency
+ camera routing (video queue). Additive; leaves Phase B outputs intact.

Framing: the original Phase B score detects significant lagged path reuse but
COMPRESSES event frequency into pair/night PEAK scores. Phase B2 estimates incident
frequency DIRECTLY — strict-following episodes extracted across ALL lags 1-30 s and
merged per ordered pair — and routes each episode to the camera channel(s) to inspect,
producing a human-readable queue and per-hour rates. Detector recall vs video-observed
trailing is validated separately by scripts/audit_following_video.py.

Read-only on the transferred backups. Outputs to
wiser/outputs/following_incidents_2026-06-28_to_2026-07-06/.

    conda activate cv
    cd wiser
    python scripts/analyze_following_incidents.py
    python scripts/analyze_following_incidents.py --max-nights 2   # smoke
"""

from __future__ import annotations

import argparse
import datetime as _dt
import itertools
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
import following_incidents as fi              # noqa: E402
import camera_router as cr                    # noqa: E402
import analyze_trajectory_stereotypy as pa    # noqa: E402

DEFAULT_OUT = PROJECT_ROOT / "outputs" / "following_incidents_2026-06-28_to_2026-07-08"
DEFAULT_VIS = PROJECT_ROOT / "configs" / "camera_visibility_map.yaml"
DEFAULT_PHASEB = PROJECT_ROOT / "outputs" / "following_structure_2026-06-28_to_2026-07-08"
FIREWORKS_NIGHT = "2026-07-04"

_DEFINITIONS = r"""## Definitions

Units: **inches**; time on a 1 s grid, positions 5 s-median smoothed; "leader/follower" is temporal
order, not geometry (inch frame UNVERIFIED). $\text{mov}_A(t)$ = moving mask; $R$ = follow radius;
$c$ = heading-cosine cutoff; $\ell$ = lag (s).

### Strict-following episode (merged across all lags)
For lag $\ell$, bin $t$ is a follow-bin iff
$\text{mov}_A(t)\wedge\text{mov}_B(t{+}\ell)\wedge\lVert\mathbf{x}_B(t{+}\ell)-\mathbf{x}_A(t)\rVert<R
\wedge \hat{\mathbf u}_A(t)\cdot\hat{\mathbf u}_B(t{+}\ell)>c$. Per lag, follow-bins are grouped into
gap-tolerant runs $\ge$ `min_bout_s`; an **episode** is a connected union over **all** $\ell\in[1,30]$
of those runs. **Text:** a sustained leader→follower trail; unlike Phase B it does not fix one best
lag, so a trail whose lag drifts is one episode (its `lag_hist` records which lags fired). Range: a
time interval $\ge$ `min_bout_s` seconds.

### Incident rates (per night, ordered pair)
$$ \text{episodes\_per\_hour}=\frac{n_{\text{ep}}}{H},\quad
   \text{duration\_per\_hour}=\frac{\sum_e \Delta_e}{H},\quad
   \text{episodes\_per\_active\_hour}=\frac{n_{\text{ep}}}{H^{\text{mov}}_B} $$
where $H$ = window hours, $\Delta_e$ = episode duration (s), $H^{\text{mov}}_B$ = follower moving-hours
($\#\text{moving bins}\times\text{bin\_s}/3600$). **Text:** how often / how long strict trailing
occurs; denominators are explicit. Range $[0,\infty)$.

### Fraction of movement bouts that are following
$$ \text{frac\_bouts\_following}=\frac{\#\{\text{follower movement bouts overlapping any episode}\}}
   {\#\{\text{follower movement bouts}\}} $$
**Text:** of the times the follower travels, the share that coincides with trailing the leader. Range
$[0,1]$. `median/p95_episode_duration_s` are the episode-duration order statistics.

### Peak score $f^{\ast}$ and null $z$ (Phase B, carried alongside)
$f^{\ast}_{A\to B}=\max_\ell f_{A\to B}(\ell)$ and its circular-shift $z$ (see the Phase B report).
**Text:** the conservative structure/null layer; reported next to the incident rates, never as the
sole reader-facing statistic.

### Camera routing (per episode)
Footprint = leader+follower positions during the episode. For channel $k$ with visibility polygon
$P_k$: coverage $=\frac1{|F|}\sum_{p\in F}\mathbb{1}[p\in P_k]$; score $=$ coverage $\times$
priority$_k$; channels ranked by score. **Text:** which video channel(s) to inspect; confidence = best
coverage (discounted if the footprint straddles a boundary). Polygons are calibrated empirically in
WISER inches (`configs/camera_visibility_map.yaml`) — no georeference needed.
"""


def _episodes_for_grid(grid, animals, R, args, t0_utc):
    rows = []
    for a, b in itertools.permutations([str(t) for t in grid["tags"]], 2):
        eps = fi.strict_following_episodes(
            grid, a, b, lags=range(1, args.lags_max + 1), R=R, cos_thresh=args.cos_thresh,
            min_bout_s=args.min_bout_s, max_gap_s=args.max_gap_s, t0_utc=t0_utc)
        rows.extend(eps)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--incremental-dir", type=Path, default=pa.DEFAULT_INCR)
    ap.add_argument("--baseline", type=Path, default=pa.DEFAULT_BASELINE)
    ap.add_argument("--rois", type=Path, default=pa.DEFAULT_ROIS)
    ap.add_argument("--gt", type=Path, default=pa.DEFAULT_GT)
    ap.add_argument("--vis-map", type=Path, default=DEFAULT_VIS)
    ap.add_argument("--phaseb-dir", type=Path, default=DEFAULT_PHASEB)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--dates", nargs="*", default=None)
    ap.add_argument("--night-start", type=int, default=21)
    ap.add_argument("--night-end", type=int, default=5)
    ap.add_argument("--lags-max", type=int, default=30)
    ap.add_argument("--cos-thresh", type=float, default=0.5)
    ap.add_argument("--min-bout-s", type=float, default=3.0)
    ap.add_argument("--max-gap-s", type=float, default=2.0)
    ap.add_argument("--bin-s", type=float, default=1.0)
    ap.add_argument("--smooth-s", type=float, default=5.0)
    ap.add_argument("--route-margin-in", type=float, default=6.0)
    ap.add_argument("--max-nights", type=int, default=None)
    args = ap.parse_args()

    out = args.out
    (out / "plots").mkdir(parents=True, exist_ok=True)
    names = pa._name_map()

    print("== Following incidents (Phase B2) ==")
    print("[1/6] load + clean ...")
    df, load_log = ts.load_incremental_days(args.incremental_dir, dates=args.dates)
    df = time_utils.convert_timestamps(df)
    t0_utc = df["datetime"].min()
    floor = pa.establish_floor(args.baseline, args.gt)
    jitter_floor = floor["jitter_floor_in"]
    df = w.add_speed(df)
    roi_cfg = w.load_rois(args.rois)
    df = w.add_validity_flags(df, boundary=(roi_cfg or {}).get("boundary"), jitter_floor_in=jitter_floor)
    df = w.apply_tag_cutoffs(df)
    grid_moving_thr = w.DEFAULT_ACTIVE_SPEED_INPS
    if floor.get("stationary") is not None:
        try:
            grid_moving_thr = round(w.grid_speed_noise_floor(
                floor["stationary"], bin_s=args.bin_s, smooth_s=args.smooth_s), 2)
        except Exception:
            pass
    R = w.follow_radius_in(jitter_floor)
    win = ts.select_night_window(df, night_start=args.night_start,
                                 night_end=args.night_end, valid_only=True)
    win = win[~win["shortid"].astype(str).isin(pa.DROP_TAGS)].reset_index(drop=True)
    nights = sorted(win["night"].unique())
    if args.max_nights:
        nights = nights[:args.max_nights]
        win = win[win["night"].isin(nights)].reset_index(drop=True)
    animals = sorted(win["shortid"].astype(str).unique())
    print(f"    nights={nights}; animals={[names.get(a, a) for a in animals]}; R={R:.0f} in")

    # camera visibility map (may be an uncalibrated template)
    vis_map, vis_ok = None, False
    try:
        vis_map = cr.load_visibility_map(args.vis_map)
        vis_ok = True
    except Exception as exc:
        print(f"    [router] no visibility map ({exc}); queue will have no channels")

    print(f"[2/6] extract strict-following episodes (all lags 1-{args.lags_max}s) ...")
    metric_rows, episode_rows = [], []
    for night in nights:
        g = win[win["night"] == night]
        grid = w.build_following_grid(g, bin_s=args.bin_s, smooth_s=args.smooth_s,
                                      moving_thr_inps=grid_moving_thr)
        if len(grid["tags"]) < 2:
            continue
        window_s = grid["X"].shape[0] * args.bin_s
        sidx = {str(t): k for k, t in enumerate(grid["tags"])}
        for a, b in itertools.permutations([str(t) for t in grid["tags"]], 2):
            eps = fi.strict_following_episodes(
                grid, a, b, lags=range(1, args.lags_max + 1), R=R, cos_thresh=args.cos_thresh,
                min_bout_s=args.min_bout_s, max_gap_s=args.max_gap_s, t0_utc=t0_utc)
            m = fi.pair_incident_metrics(eps, grid, sidx[b], window_s=window_s)
            m.update({"night": night, "leader": a, "follower": b,
                      "leader_name": names.get(a, a), "follower_name": names.get(b, b),
                      "fireworks_night": night == FIREWORKS_NIGHT})
            metric_rows.append(m)
            for e in eps:
                fp = fi.episode_footprint(grid, a, b, e["i_start"], e["i_end"])
                rec = {"night": night, **{k: e[k] for k in
                       ("leader", "follower", "duration_s", "n_follow_bins", "mean_sep_in",
                        "mean_cos", "median_lag_s", "min_lag_s", "max_lag_s", "n_lags_fired")},
                       "leader_name": names.get(a, a), "follower_name": names.get(b, b),
                       "t_start_local": e.get("t_start_local"), "t_end_local": e.get("t_end_local"),
                       "x_med": float(np.median(fp[:, 0])) if len(fp) else np.nan,
                       "y_med": float(np.median(fp[:, 1])) if len(fp) else np.nan,
                       "lag_hist": json.dumps(e["lag_hist"])}
                if vis_ok and len(fp):
                    r = cr.route_event(fp, vis_map, margin_in=args.route_margin_in)
                    rec.update({"channel_rank_1": r["channel_rank_1"],
                                "channel_rank_2": r["channel_rank_2"],
                                "route_confidence": r["confidence"],
                                "route_reason": r["reason"], "near_boundary": r["near_boundary"]})
                episode_rows.append(rec)

    metrics = pd.DataFrame(metric_rows)
    episodes = pd.DataFrame(episode_rows)
    if episodes.empty:
        print("    no episodes found; aborting."); return

    # join Phase-B peak_score / z (structure/null layer) if available
    pb = args.phaseb_dir / "following_pairs_by_night.csv"
    if pb.exists():
        pbf = pd.read_csv(pb)
        pbf["leader"] = pbf["leader"].astype(str); pbf["follower"] = pbf["follower"].astype(str)
        keep = ["night", "leader", "follower", "peak_score", "best_lag_s", "z_score"]
        keep = [c for c in keep if c in pbf.columns]
        metrics = metrics.merge(pbf[keep], on=["night", "leader", "follower"], how="left")
    metrics.to_csv(out / "incident_metrics_by_pair_night.csv", index=False)

    print("[3/6] per-night / per-animal aggregates ...")
    by_night = metrics.groupby("night").agg(
        n_episodes=("n_episodes", "sum"),
        episodes_per_hour=("strict_follow_episode_count_per_hour", "sum"),
        mean_frac_bouts_following=("fraction_of_movement_bouts_that_are_following", "mean"),
    ).reset_index()
    by_night.to_csv(out / "incident_summary_by_night.csv", index=False)
    # per animal as follower and as leader
    as_follower = metrics.groupby("follower_name").agg(
        n_episodes_as_follower=("n_episodes", "sum"),
        mean_frac_bouts_following=("fraction_of_movement_bouts_that_are_following", "mean")).reset_index()
    as_leader = metrics.groupby("leader_name").agg(
        n_episodes_as_leader=("n_episodes", "sum")).reset_index()
    by_animal = as_follower.merge(as_leader, left_on="follower_name", right_on="leader_name",
                                  how="outer").drop(columns=["leader_name"])
    by_animal.to_csv(out / "incident_by_animal.csv", index=False)

    print("[4/6] camera routing -> strict_following_video_queue.csv ...")
    queue_cols = ["night", "t_start_local", "duration_s", "leader_name", "follower_name",
                  "median_lag_s", "mean_sep_in", "mean_cos", "x_med", "y_med",
                  "channel_rank_1", "channel_rank_2", "route_confidence", "route_reason",
                  "near_boundary"]
    queue = episodes.copy()
    queue.insert(0, "event_id", ["ev%04d" % i for i in range(len(queue))])
    for c in queue_cols:
        if c not in queue.columns:
            queue[c] = None
    queue = queue.sort_values(["route_confidence", "duration_s"], ascending=False, na_position="last")
    queue[["event_id"] + queue_cols].to_csv(out / "strict_following_video_queue.csv", index=False)
    episodes.to_csv(out / "strict_following_episodes.csv", index=False)

    print("[5/6] figures ...")
    _fig_rate_heatmap(metrics, names, out / "plots" / "episodes_per_hour_by_pair.png")
    _fig_duration_hist(episodes, out / "plots" / "episode_duration_hist.png")
    _fig_by_night(by_night, out / "plots" / "episodes_by_night.png")

    print("[6/6] manifest + report ...")
    manifest = {
        "analysis": "following_incidents_phase_b2",
        "generated_utc": _dt.datetime.utcnow().isoformat(),
        "git_commit": pa._git_commit(),
        "units": "inches (WISER native, UNVERIFIED offset origin)",
        "night_window_local": [args.night_start, args.night_end],
        "follow_radius_in": R, "jitter_floor_in": jitter_floor,
        "grid_moving_thr_inps": grid_moving_thr, "cos_thresh": args.cos_thresh,
        "lags_s": [1, args.lags_max], "min_bout_s": args.min_bout_s, "max_gap_s": args.max_gap_s,
        "route_margin_in": args.route_margin_in,
        "n_episodes": int(len(episodes)), "n_pairs_nights": int(len(metrics)),
        "nights": nights, "animals": {a: names.get(a, a) for a in animals},
        "camera_map": str(args.vis_map), "camera_map_confirmed": bool(vis_map and vis_map.get("confirmed")),
        "phaseb_joined": pb.exists(), "load_log": load_log,
        "caveats": [
            "additive layer — Phase B (analyze_following_structure) outputs untouched",
            "episodes extracted across ALL lags 1-30s and merged, not one best lag",
            "camera routing uses an editable WISER-inch visibility map; PLACEHOLDER polygons "
            "until configs/camera_visibility_map.yaml is calibrated (meta.confirmed=false -> low trust)",
            "inch frame UNVERIFIED; leader/follower = temporal order, not geometry",
            "video recall is validated separately by scripts/audit_following_video.py",
        ],
    }
    with open(out / "run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    _write_report(out, manifest, metrics, by_night, by_animal, episodes, queue, names,
                  vis_map)
    print(f"\nDONE -> {out}")


# ---------------------------------------------------------------------------
# plots
# ---------------------------------------------------------------------------

def _fig_rate_heatmap(metrics, names, path):
    if metrics.empty:
        return
    piv = metrics.pivot_table(index=["leader_name", "follower_name"],
                              values="strict_follow_episode_count_per_hour", aggfunc="mean")
    piv = piv.sort_values("strict_follow_episode_count_per_hour", ascending=False).head(20)
    fig, ax = plt.subplots(figsize=(6, 0.35 * len(piv) + 2))
    labs = [f"{l}→{f}" for l, f in piv.index]
    ax.barh(range(len(piv)), piv["strict_follow_episode_count_per_hour"], color="#4C72B0")
    ax.set_yticks(range(len(piv))); ax.set_yticklabels(labs, fontsize=8); ax.invert_yaxis()
    ax.set_xlabel("strict-following episodes per hour (mean over nights)")
    ax.set_title("Incident frequency by ordered pair (top 20)")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def _fig_duration_hist(episodes, path):
    if episodes.empty:
        return
    fig, ax = plt.subplots(figsize=(7, 4))
    d = episodes["duration_s"].to_numpy()
    ax.hist(d, bins=40, color="#4C72B0")
    ax.set_xlabel("episode duration (s)"); ax.set_ylabel("count")
    ax.set_title(f"Strict-following episode durations (n={len(d)}, "
                 f"median {np.median(d):.0f}s, p95 {np.percentile(d,95):.0f}s)")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def _fig_by_night(by_night, path):
    if by_night.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar([n[5:] for n in by_night["night"]], by_night["n_episodes"], color="#4C72B0")
    ax.set_ylabel("total strict-following episodes"); ax.set_xlabel("night")
    ax.set_title("Strict-following episodes per night (all ordered pairs)")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def _write_report(out, manifest, metrics, by_night, by_animal, episodes, queue, names, vis_map):
    tot_ep = int(len(episodes))
    med_dur = float(episodes["duration_s"].median())
    p95_dur = float(episodes["duration_s"].quantile(0.95))
    # top pairs by episodes/hr
    top = (metrics.groupby(["leader_name", "follower_name"])
           .agg(ep_per_hr=("strict_follow_episode_count_per_hour", "mean"),
                frac=("fraction_of_movement_bouts_that_are_following", "mean"),
                n_ep=("n_episodes", "sum")).reset_index()
           .sort_values("ep_per_hr", ascending=False).head(10))
    routed = int(queue["channel_rank_1"].notna().sum()) if "channel_rank_1" in queue else 0
    cam_conf = bool(manifest.get("camera_map_confirmed"))
    nb = int(queue["near_boundary"].fillna(False).sum()) if "near_boundary" in queue else 0

    L = []
    L += ["# Following incidents & video audit — Phase B2 report", "",
          f"**Generated (UTC):** {manifest['generated_utc']}  ",
          f"**Commit:** `{manifest['git_commit']}`  ",
          f"**Nights:** {', '.join(manifest['nights'])}  ",
          f"**Follow radius:** {manifest['follow_radius_in']:.0f} in; lags 1–{manifest['lags_s'][1]} s; "
          f"heading cos>{manifest['cos_thresh']}; min episode {manifest['min_bout_s']:.0f} s  ",
          f"**Frame:** inches, UNVERIFIED — 'leader/follower' = temporal order, not geometry  ", "",
          "> **Why B2 exists.** The original Phase B score detects significant lagged path reuse but "
          "**compresses event frequency into pair/night peak scores**. Phase B2 estimates incident "
          "frequency **directly** (episodes extracted across all lags 1–30 s and merged) and validates "
          "detector recall against video-observed strict trailing. Phase B is unchanged and remains the "
          "conservative structure/null layer.", "",
          "## (a) Pair/night structure — herd vs stable dyads", "",
          "- Unchanged from Phase B (see `following_structure_.../following_structure_report.md`): "
          "co-movement is **promiscuous/herd, not stable dyads** (top pair reshuffles nightly), with "
          "**Sen** the most frequent leader. B2 does not re-litigate this; it adds frequency + recall.", "",
          "## (b) Incident frequency — how often does strict trailing happen?", "",
          f"- **{tot_ep} strict-following episodes** across {len(manifest['nights'])} nights "
          f"(median {med_dur:.0f} s, p95 {p95_dur:.0f} s). Per-night counts in "
          "`incident_summary_by_night.csv`; per (night, ordered pair) rates in "
          "`incident_metrics_by_pair_night.csv`.",
          "- These are **incident-level** rates (episodes/hour, duration/hour, fraction-of-movement-"
          "bouts-that-are-following) — the reader-facing frequency the Phase-B peak score compressed.", "",
          "### Top ordered pairs by episodes/hour", "",
          "| leader → follower | episodes/hr | frac of follower bouts | total episodes |",
          "|---|---|---|---|"]
    for _, r in top.iterrows():
        L.append(f"| {r['leader_name']} → {r['follower_name']} | {r['ep_per_hr']:.2f} | "
                 f"{r['frac']:.2f} | {int(r['n_ep'])} |")
    L += ["", "- Per-animal totals (as follower / as leader) in `incident_by_animal.csv`. Phase-B "
          "`peak_score`/`z` are carried in `incident_metrics_by_pair_night.csv` but are **not** the "
          "reader-facing frequency statistic.", "",
          "## (c) Video calibration — does WISER catch human-observed trailing?", "",
          "- Run `scripts/audit_following_video.py` after marking events in "
          "`configs/video_audit_manual.csv`. It pulls WISER ±60 s per marked trail and classifies "
          "detected vs missed (lag / heading / radius / moving-mask / tag-dropout / clock-alignment / "
          "not-geometrically-strict), writing `video_audit_events.csv`, "
          "`video_audit_detection_summary.csv`, `video_audit_failure_modes.csv`.",
          "- **Until that audit is run, no recall/false-negative claim is made here.**", "",
          "## (d) Camera-routing confidence", "",
          f"- **{routed}/{tot_ep}** episodes routed to a channel; **{nb}** flagged near a channel "
          f"boundary (pull ≥2 channels). Queue: `strict_following_video_queue.csv` (sorted by routing "
          "confidence then duration).",
          f"- Camera map **confirmed: {cam_conf}**. "
          + ("Routing is trustworthy." if cam_conf else
             "**PLACEHOLDER polygons** — routing confidences are provisional until "
             "`configs/camera_visibility_map.yaml` is calibrated (add `examples`, draw real polygons, "
             "set `meta.confirmed: true`)."), "",
          "## How to use the queue", "",
          "`strict_following_video_queue.csv` gives, per episode: local-EDT start, duration, leader, "
          "follower, median lag, mean separation, heading cosine, and recommended channel(s). Sort/"
          "filter it, open the channel at the start time, and confirm strict trailing on video.", "",
          ] + _DEFINITIONS.strip("\n").split("\n") + ["",
          "## Outputs", "",
          "`incident_metrics_by_pair_night.csv` · `incident_summary_by_night.csv` · "
          "`incident_by_animal.csv` · `strict_following_episodes.csv` · "
          "`strict_following_video_queue.csv` · `run_manifest.json` · `plots/`", ""]
    (out / "following_structure_phaseB2_incident_audit.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
