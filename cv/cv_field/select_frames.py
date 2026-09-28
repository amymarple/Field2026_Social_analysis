"""select_frames.py — the cv_field unsupervised active-learning selector (rounds 0..k).

Turns a pool of harvested whole-field frames into a small, maximally-informative set to hand-label, so a
tiny label budget bootstraps a strong YOLO detector for CH01-CH04 (which start with no detector at all).

  round 0  (no detector) : pure DIVERSITY — embed -> choose K by BIC -> one medoid per cluster ->
                           farthest-point coverage of the rest (rare regimes: entrance, on-grass, night-IR).
  round >=1 (seed detector): UNCERTAINTY x DIVERSITY — u = max(conf-margin, count-instability) and
                           a(f|A) = u**gamma * d(f,A) (uncertainty-weighted k-center), so a frame must be both
                           uncertain and far from what is already labeled; ~explore_frac is pure exploration.
  --method random         : the equal-budget control the Phase-2 falsification check compares against.

Selected frames are copied into the dataset's images/ inbox with their pool names, so label_frames.py and
train_detector.py (``--data-root dataset/rat_field --name rat_field``) consume them UNCHANGED. Every round
appends round_provenance.csv and writes a measurement_context sidecar (embedding + active-learning blocks)
plus a short canonical report + a 2-D PCA coverage figure.

Compute: this is CPU/numpy selection work and runs LOCALLY. Embedding the full pool and any detector pass
are the heavy steps that route to BioHPC for large batches (see REMOTE_COMPUTE.md); paths are env-driven
(FIELD2026_ANALYSIS_OUT_ROOT) so the same driver runs local or on the server.

The pure planners ``plan_round0`` / ``plan_roundk`` take an embedding matrix and are exercised numpy-only by
selftest_field_select.py; cv2 / ultralytics / pandas / matplotlib are imported lazily in the IO path only.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent           # cv/cv_field
CV_DIR = HERE.parent                              # cv/
for _p in (str(HERE), str(CV_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                # noqa: E402
import acquire as aq                              # noqa: E402
import field_cluster as fc                        # noqa: E402
import field_embed as fe                          # noqa: E402

IMG_EXTS = (".png", ".jpg", ".jpeg")
PROVENANCE_COLS = ["frame", "round", "method", "cluster_id", "src_pool", "embed_backend", "seed_weights"]


# ------------------------------------------------------------------ pure planners (numpy-only, tested)
def plan_round0(X, budget: int, seed: int = 0, exclude=None) -> dict:
    """Diversity-only selection: K medoids + farthest-point coverage, total <= budget. exclude = pool
    indices already selected in a prior round (kept out of the picks but still seeding coverage)."""
    excl = set(exclude or [])
    K, info = fc.choose_k(X, budget=budget, seed=seed)
    labels, _ = fc.kmeans(X, K, seed=seed)
    med = [i for i in fc.medoids(X, labels) if i not in excl]
    n_cov = max(0, int(budget) - len(med))
    cov = fc.farthest_point_sample(X, n_cov, init=list(med) + list(excl), seed=seed, exclude=excl)
    indices = list(med) + list(cov)
    methods = ["medoid"] * len(med) + ["fps"] * len(cov)
    return {"indices": indices, "methods": methods,
            "cluster_ids": [int(labels[i]) for i in indices], "k": int(K),
            "select_scores": info.get("silhouette", {})}


def plan_roundk(X, u, budget: int, labeled_idx=None, gamma: float = 1.0,
                explore_frac: float = 0.15, seed: int = 0) -> dict:
    """Uncertainty x diversity acquisition against the already-labeled set. Total <= budget."""
    idx = aq.greedy_acquire(X, u, budget, labeled_idx=labeled_idx, gamma=gamma,
                            explore_frac=explore_frac, seed=seed)
    n_acq = int(budget) - int(round(explore_frac * int(budget)))
    methods = ["acq"] * min(n_acq, len(idx)) + ["fps"] * max(0, len(idx) - n_acq)
    return {"indices": idx, "methods": methods, "cluster_ids": [None] * len(idx), "k": None, "select_scores": {}}


# ------------------------------------------------------------------ pool + provenance IO
def load_pool(pool_dir) -> list[Path]:
    """Deterministic, sorted list of candidate frames in the pool directory."""
    d = Path(pool_dir)
    if not d.is_dir():
        raise SystemExit(f"--pool must be a directory of harvested frames: {d}")
    return sorted(p for p in d.iterdir() if p.suffix.lower() in IMG_EXTS)


def load_motion(pool, motion_json):
    """Read the motion sidecar and return (crops, scores) aligned with ``pool`` (a list of frame Paths).

    ``crops[i]`` = padded union box (x1,y1,x2,y2 px) of frame i's motion, or None if the frame has no motion /
    no sidecar entry (embed the whole frame). ``scores[i]`` = motion-pixel fraction (0 if absent)."""
    import json
    import field_motion as fm
    data = json.loads(Path(motion_json).read_text())
    crops, scores = [], []
    for p in pool:
        e = data.get(p.name)
        if e and e.get("boxes"):
            crops.append(fm.union_crop(e["boxes"], e["W"], e["H"]))
            scores.append(float(e.get("score", 0.0)))
        else:
            crops.append(None)
            scores.append(float(e.get("score", 0.0)) if e else 0.0)
    return crops, np.asarray(scores, dtype=np.float32)


def provenance_seen(prov_csv) -> set:
    p = Path(prov_csv)
    if not p.exists():
        return set()
    with p.open(newline="", encoding="utf-8") as fh:
        return {row["frame"] for row in csv.DictReader(fh)}


def append_provenance(prov_csv, rows) -> None:
    p = Path(prov_csv)
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    with p.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=PROVENANCE_COLS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


# ------------------------------------------------------------------ detector uncertainty (run machine)
def pool_uncertainty(paths, weights, device="0", imgsz=1280, conf=0.05, batch=8, tau=0.40):
    """Per-frame uncertainty from the seed detector (max conf, count, flip-TTA count). Lazy heavy imports."""
    import cv2
    from ultralytics import YOLO
    model = YOLO(weights)
    cmax, n, n_flip = [], [], []
    for i in range(0, len(paths), batch):
        chunk = [str(p) for p in paths[i:i + batch]]
        for r in model.predict(chunk, conf=conf, classes=[0], imgsz=imgsz, device=device, verbose=False):
            nb = 0 if r.boxes is None else len(r.boxes)
            cmax.append(float(r.boxes.conf.max()) if nb else 0.0)
            n.append(nb)
        flips = [cv2.flip(cv2.imread(c), 1) for c in chunk]
        for r in model.predict(flips, conf=conf, classes=[0], imgsz=imgsz, device=device, verbose=False):
            n_flip.append(0 if r.boxes is None else len(r.boxes))
    return aq.uncertainty(np.array(cmax), np.array(n), np.array(n_flip), tau=tau)


# ------------------------------------------------------------------ canonical report + figure
def write_coverage_figure(X, indices, path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return False
    basis, mean = fe.fit_pca(X, 2)
    P = fe.apply_pca(X, basis, mean)
    sel = np.zeros(len(X), bool)
    sel[list(indices)] = True
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(P[~sel, 0], P[~sel, 1], s=6, c="#bbbbbb", label="pool", linewidths=0)
    ax.scatter(P[sel, 0], P[sel, 1], s=22, c="#d1495b", label="selected", linewidths=0)
    ax.set_xlabel("PC1"); ax.set_ylabel("PC2")
    ax.set_title("cv_field selection coverage (2-D PCA of the embedding)")
    ax.legend(loc="best", fontsize=8); fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120); plt.close(fig)
    return True


def write_report(report_path, cohort, args, pool_n, plan, comp, fig_rel) -> None:
    method = args.method if args.method == "random" else ("diversity" if args.round == 0 else "uncertainty x diversity")
    lines = [
        f"# cv_field labeling round {args.round} — {cohort}", "",
        f"- **direction:** cv_field (whole-field CH01-CH04)  ·  **channels:** {', '.join(args.channels)}",
        f"- **selection method:** {method}  ·  **budget:** {args.budget}  ·  **selected:** {len(plan['indices'])}",
        f"- **pool size:** {pool_n} candidate frames  ·  **embed backend:** {plan.get('embed_backend')}",
        f"- **K (silhouette):** {plan.get('k')}  ·  **seed weights:** {plan.get('seed_weights') or '(none — cold start)'}",
        (f"- **motion:** embedding the MOTION CROP (rat region), not the whole frame; reserved "
         f"{plan.get('n_quiet', 0)} quiet/random frames so still/resting rats + true negatives stay represented."
         if plan.get("use_motion") else None),
        "",
        "## Definitions", "",
        "- **budget B** — number of frames selected this round for hand-labeling (count).",
        "- **medoid** — the most-central real frame of a k-means cluster (a typical exemplar).",
        "- **farthest-point coverage** — greedy k-center pick maximizing min-distance to the already-covered "
        "set (fills rare/edge regimes).",
        "- **K (silhouette)** — number of k-means clusters chosen by maximizing the mean silhouette (robust on "
        "the L2-normalized embedding, where a likelihood BIC would over-segment).",
        "- **uncertainty u in [0,1]** — max(confidence-margin about tau, count-instability under horizontal-flip "
        "TTA); higher = the detector is less sure.",
        "- **acquisition a(f|A) = u^gamma · d(f,A)** — uncertainty-weighted k-center: selects frames that are "
        "both uncertain and far (min Euclidean distance) from the labeled set A in the L2-normalized embedding.",
        "",
        "## Falsification guard", "",
        f"- single-Gaussian BIC {comp.get('bic_single_gaussian'):.0f} vs k-means BIC "
        f"{comp.get('bic_kmeans'):.0f} (K={comp.get('K')}); smooth model competitive: "
        f"{comp.get('smooth_model_competitive')}.",
        "- Clusters here are a **labeling heuristic only**, never a claim of behavioral discreteness.",
        "",
        f"## Coverage figure", "", f"![coverage]({fig_rel})" if fig_rel else "_(figure unavailable)_", "",
        "## Whole-field measurement caveats (carry on every downstream number)", "",
        "- scope is night-IR only (21:00–04:20); CH01/CH02 daytime color is corrupt and excluded.",
        "- counts are a LOWER BOUND (`visible_count`): wall-edge blind band + huddle occlude animals.",
        "- NO cross-camera identity yet (animal_id = <camera>:<track_id>) — no whole-field per-animal or "
        "cross-camera-headcount claims.",
    ]
    Path(report_path).write_text("\n".join(l for l in lines if l is not None) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ driver
def main(argv=None) -> int:
    import cohorts as co
    ap = argparse.ArgumentParser(description="cv_field active-learning frame selector (rounds 0..k).",
                                 allow_abbrev=False)
    co.add_cohort_arg(ap)
    ap.add_argument("--channels", nargs="+", default=["CH01", "CH02", "CH03", "CH04"])
    ap.add_argument("--round", type=int, required=True, help="0 = cold-start diversity; >=1 = uncertainty x diversity")
    ap.add_argument("--budget", type=int, default=120, help="frames to select this round for labeling")
    ap.add_argument("--pool", required=True, help="directory of harvested candidate frames (scan_for_rats --no-detector out-dir)")
    ap.add_argument("--out-dir", default=str(CV_DIR / "dataset" / "rat_field" / "images"),
                    help="labeling inbox; selected frames are copied here for label_frames.py")
    ap.add_argument("--method", choices=["active", "random"], default="active",
                    help="'random' = equal-budget control for the Phase-2 falsification check")
    ap.add_argument("--embed-backend", default="dino",
                    choices=["dino", "dinov2", "dinov3", "auto", "yolo", "gray"],
                    help="dino (default) = DINO self-supervised ViT, auto-prefers v3 when its gated "
                         "checkpoint is present (DINOV3_WEIGHTS) else v2; force with dinov2/dinov3")
    ap.add_argument("--seed-weights", default=None, help="round>=1 detector weights (uncertainty + embed backbone)")
    ap.add_argument("--pca-dim", type=int, default=50)
    ap.add_argument("--use-motion", action="store_true",
                    help="embed the MOTION CROP (rat region) not the whole frame, so diversity tracks rat "
                         "content; reads a motion sidecar from enrich_motion.py / a motion-aware harvest")
    ap.add_argument("--motion-json", default=None, help="motion sidecar path (default: <pool>/motion.json)")
    ap.add_argument("--quiet-frac", type=float, default=0.25,
                    help="with --use-motion: fraction of the budget RESERVED for low/no-motion + random "
                         "frames, so the detector keeps seeing still/resting rats and true negatives")
    ap.add_argument("--gamma", type=float, default=1.0)
    ap.add_argument("--explore-frac", type=float, default=0.15)
    ap.add_argument("--tau", type=float, default=0.40, help="detector decision boundary for the uncertainty margin")
    ap.add_argument("--device", default="0")
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--conf", type=float, default=0.05, help="low conf floor for the uncertainty pass")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", help="plan + print only; copy/write nothing")
    args = ap.parse_args(argv)

    import output_paths as op
    cohort = op.resolve_cohort(args.cohort)
    if args.round >= 1 and args.method == "active" and not args.seed_weights:
        raise SystemExit("round>=1 active selection needs --seed-weights (the seed detector).")

    pool = load_pool(args.pool)
    if not pool:
        raise SystemExit(f"no frames in pool {args.pool}")
    prov_csv = Path(args.out_dir).parent / "round_provenance.csv"
    seen = provenance_seen(prov_csv)
    already = [i for i, p in enumerate(pool) if p.name in seen]

    crops = scores = None
    if args.use_motion:
        mj = args.motion_json or (Path(args.pool) / "motion.json")
        if not Path(mj).exists():
            raise SystemExit(f"--use-motion needs a motion sidecar; {mj} not found (run enrich_motion.py first)")
        crops, scores = load_motion(pool, mj)

    embed_weights = args.seed_weights if (args.round > 0 and args.embed_backend != "gray") else None
    X, info = fe.embed_frames(pool, backend=args.embed_backend, weights=embed_weights,
                              device=args.device, pca_dim=args.pca_dim, crops=crops)
    backend = info["backend"]

    # Stratified quiet/random reserve (motion mode, active only): hold back part of the budget for LOW-motion
    # + random frames so the detector keeps seeing still/resting rats and true negatives (not just movers).
    quiet_idx, main_budget = [], args.budget
    if args.use_motion and args.method == "active" and args.quiet_frac > 0:
        n_quiet = int(round(args.quiet_frac * args.budget))
        thr = float(np.quantile(scores, 0.33)) if len(scores) else 0.0
        cand = [i for i in range(len(pool)) if scores[i] <= thr and i not in already]
        if n_quiet and cand:
            rngq = np.random.default_rng(args.seed)
            quiet_idx = [int(i) for i in rngq.choice(cand, size=min(n_quiet, len(cand)), replace=False)]
            main_budget = args.budget - len(quiet_idx)

    exclude = list(already) + quiet_idx
    if args.method == "random":
        idx = aq.random_baseline(len(pool), args.budget, exclude=already, seed=args.seed)
        plan = {"indices": idx, "methods": ["random"] * len(idx), "cluster_ids": [None] * len(idx), "k": None}
    elif args.round == 0 or not args.seed_weights:
        plan = plan_round0(X, main_budget, seed=args.seed, exclude=exclude)
    else:
        u = pool_uncertainty([pool[i] for i in range(len(pool))], args.seed_weights, device=args.device,
                             imgsz=args.imgsz, conf=args.conf, tau=args.tau)
        plan = plan_roundk(X, u, main_budget, labeled_idx=exclude, gamma=args.gamma,
                           explore_frac=args.explore_frac, seed=args.seed)
    if quiet_idx:                                  # prepend the reserved quiet/random stream
        plan["indices"] = quiet_idx + list(plan["indices"])
        plan["methods"] = ["quiet"] * len(quiet_idx) + list(plan["methods"])
        plan["cluster_ids"] = [None] * len(quiet_idx) + list(plan["cluster_ids"])
    plan["embed_backend"] = backend
    plan["seed_weights"] = (Path(args.seed_weights).parents[1].name if args.seed_weights else None)
    plan["use_motion"] = bool(args.use_motion)
    plan["n_quiet"] = len(quiet_idx)

    comp = fc.pca_competitor_report(X, plan["k"] or max(2, min(8, len(pool) - 1)), seed=args.seed)
    selected = [pool[i] for i in plan["indices"]]
    print(f"cohort={cohort} round={args.round} method={args.method} backend={backend} "
          f"pool={len(pool)} selected={len(selected)} K={plan.get('k')}")

    if args.dry_run:
        for p, m in zip(selected[:20], plan["methods"]):
            print(f"  [{m}] {p.name}")
        if len(selected) > 20:
            print(f"  ... (+{len(selected) - 20} more)")
        return 0

    # --- write: copy frames, append provenance, bulk selection CSV + sidecar, canonical report + figure
    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    rows, copied = [], 0
    for pos, (i, m) in enumerate(zip(plan["indices"], plan["methods"])):
        src = pool[i]
        dst = out_dir / src.name
        if not dst.exists():
            shutil.copy(src, dst); copied += 1
        rows.append({"frame": src.name, "round": args.round, "method": m,
                     "cluster_id": plan["cluster_ids"][pos],
                     "src_pool": str(src), "embed_backend": backend,
                     "seed_weights": plan["seed_weights"]})
    append_provenance(prov_csv, rows)

    run = op.run_dir("cv_field_select", cohort)
    with (run / f"selection_round{args.round}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=PROVENANCE_COLS); w.writeheader()
        for r in rows:
            w.writerow(r)

    import measurement_context as mc
    embedding = fe.embedding_fingerprint(backend, embed_weights, args.pca_dim)
    active_learning = {"round": args.round, "method": args.method, "budget": args.budget,
                       "k": plan.get("k"), "gamma": args.gamma, "explore_frac": args.explore_frac,
                       "pool_size": len(pool), "n_selected": len(selected),
                       "seed_weights_version": plan["seed_weights"],
                       "use_motion": plan.get("use_motion", False),
                       "quiet_frac": (args.quiet_frac if args.use_motion else None),
                       "n_quiet": plan.get("n_quiet", 0),
                       "falsification": comp}
    ctx = mc.build_context("cv_field/select_frames.py", args, args.channels,
                           embedding=embedding, active_learning=active_learning)
    mc.write_manifest(run / f"select_round{args.round}.measurement_context.json", ctx)

    rep_dir = op.report_dir(cohort, "cv_field")
    fig_dir = op.figure_dir(cohort, "cv_field")
    fig = fig_dir / f"cv_field_round{args.round}_coverage_{cohort}.png"
    have_fig = write_coverage_figure(X, plan["indices"], fig)
    fig_rel = (f"../figures/{fig.name}" if have_fig else None)
    write_report(rep_dir / f"cv_field_labeling_round{args.round}_{cohort}.md", cohort, args, len(pool), plan, comp, fig_rel)
    op.write_run_manifest(rep_dir, run, cohort=cohort, direction="cv_field",
                          analysis=f"labeling_round{args.round}", mc_run_id=ctx["mc_run_id"],
                          embed_backend=backend, method=args.method)

    print(f"copied {copied} new frames to {out_dir}  (provenance -> {prov_csv})")
    print(f"bulk -> {run}   report -> {rep_dir}")
    print("next: label -> python cv/label_frames.py ; train -> "
          "python cv/train_detector.py --data-root cv/dataset/rat_field --name rat_field")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
