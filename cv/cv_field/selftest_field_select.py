"""selftest_field_select.py — offline PASS/FAIL for the cv_field active-learning selector + path wiring.

No GPU, no field data, no ultralytics needed (the embed backend falls back to gray/numpy). Exit 0 = PASS.
Mirrors wiser/scripts/selftest_output_paths.py (temp FIELD2026_ANALYSIS_OUT_ROOT, fail list) and the
view_quality --selftest check() style.

Section A — selector correctness on planted clusters (pure numpy):
  A1 choose_k recovers K near the planted count.
  A2 round-0 selection covers every planted cluster, incl. a rare 10-point blob and the outliers.
  A3 medoids: one valid, distinct exemplar per cluster.
  A4 near-duplicate high-uncertainty blob is suppressed to <=3 picks (diversity kills re-labeling dupes).
  A5 uncertainty targeting: acquisition mean-u beats the random control and spreads across >=3 clusters.
  A6 determinism: same seed -> identical selections.
  A7 gray backend end-to-end on synthetic PNGs (skipped gracefully if cv2 is unavailable).

Section B — cohort path + measurement_context wiring (temp out-root):
  run_dir/report_dir/figure_dir/assets_dir resolve correctly; write_run_manifest emits valid JSON;
  build_context carries the embedding + active_learning blocks; mc_run_id flips when the round changes;
  and omitting them leaves the shelter manifest shape untouched (byte-identity guard).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

HERE = Path(__file__).resolve().parent
CV_DIR = HERE.parent
for _p in (str(HERE), str(CV_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import acquire as aq  # noqa: E402
import field_cluster as fc  # noqa: E402
import field_embed as fe  # noqa: E402
import select_frames as sf  # noqa: E402

COH = "_selftest_cvfield"


def planted():
    """5 well-separated Gaussian blobs (imbalanced, incl. a rare 10-point one) + scattered outliers in R^32.
    Returns (X float32, y labels; blobs 0..4, outliers = 5)."""
    rng = np.random.default_rng(0)
    centers = rng.normal(0, 15, size=(5, 32))
    sizes = [200, 120, 80, 40, 10]
    parts, y = [], []
    for k, (c, s) in enumerate(zip(centers, sizes)):
        parts.append(c + rng.normal(0, 0.4, size=(s, 32)))
        y += [k] * s
    parts.append(rng.normal(0, 45, size=(5, 32)))
    y += [5] * 5
    return np.vstack(parts).astype(np.float32), np.array(y)


def section_a(fails):
    Xraw, y = planted()
    X, _ = fe.embed_matrix(Xraw, pca_dim=16)          # the real pipeline path: PCA + L2

    # A1 K recovery
    K, _info = fc.choose_k(X, budget=48, seed=0)
    if not (4 <= K <= 7):
        fails.append(f"A1 choose_k={K} not in [4,7]")

    # A2 coverage
    plan = sf.plan_round0(X, budget=48, seed=0)
    sel = np.array(plan["indices"])
    labs = set(y[sel].tolist())
    if not {0, 1, 2, 3, 4}.issubset(labs):
        fails.append(f"A2 round-0 missed a blob; covered labels={sorted(labs)}")
    if 5 not in labs:
        fails.append("A2 round-0 did not select any outlier")

    # A3 medoids
    labels, _ = fc.kmeans(X, K, seed=0)
    med = fc.medoids(X, labels)
    if len(med) != len(set(med)) or any(not (0 <= i < len(X)) for i in med):
        fails.append(f"A3 medoids not distinct/valid: {med}")

    # A4 near-duplicate high-u blob suppression. NB: the dups share a non-zero base direction so they stay
    # near-identical AFTER L2-normalization (normalizing near-zero vectors would amplify noise onto the sphere).
    rng = np.random.default_rng(1)
    base = rng.normal(0, 1, size=8).astype(np.float32)
    dup = base[None, :] + rng.normal(0, 1e-3, size=(30, 8)).astype(np.float32)
    spread = rng.normal(0, 5, size=(100, 8)).astype(np.float32)
    X2 = fe.l2_normalize(np.vstack([dup, spread]))
    u2 = np.concatenate([np.ones(30), np.full(100, 0.1)])
    picks = aq.greedy_acquire(X2, u2, k=20, gamma=1.0, explore_frac=0.0, seed=0)
    from_dup = sum(1 for p in picks if p < 30)
    if from_dup > 3:
        fails.append(f"A4 duplicate blob not suppressed: took {from_dup} of 30 near-identical")

    # A5 uncertainty targeting (high u on clusters 0,1,2 only)
    u = np.where(np.isin(y, [0, 1, 2]), 1.0, 0.0)
    acq = aq.greedy_acquire(X, u, k=30, gamma=1.0, explore_frac=0.0, seed=0)
    rnd = aq.random_baseline(len(X), 30, seed=0)
    if u[acq].mean() <= u[rnd].mean():
        fails.append(f"A5 acquisition mean-u {u[acq].mean():.2f} !> random {u[rnd].mean():.2f}")
    if len(set(y[acq].tolist()) & {0, 1, 2}) < 3:
        fails.append("A5 acquisition did not spread across >=3 high-u clusters")

    # A6 determinism
    if sf.plan_round0(X, 48, seed=0)["indices"] != sf.plan_round0(X, 48, seed=0)["indices"]:
        fails.append("A6 plan_round0 not deterministic under a fixed seed")
    if aq.greedy_acquire(X, u, 30, seed=0) != aq.greedy_acquire(X, u, 30, seed=0):
        fails.append("A6 greedy_acquire not deterministic under a fixed seed")

    # A7 gray backend end-to-end (needs cv2 + an image writer)
    try:
        import cv2
        with tempfile.TemporaryDirectory() as tmp:
            rng = np.random.default_rng(2)
            paths = []
            for i in range(30):
                img = (rng.integers(0, 255, size=(48, 48, 3))).astype(np.uint8)
                p = Path(tmp) / f"CH01_CH01_2026-06-28_19-00-00_to_20-00-00_{i}s.png"
                cv2.imwrite(str(p), img)
                paths.append(p)
            Xg, info = fe.embed_frames(paths, backend="gray", pca_dim=8)
            if Xg.shape[0] != 30 or not np.isfinite(Xg).all():
                fails.append(f"A7 gray embed shape/finite wrong: {Xg.shape}")
            if not np.allclose(np.linalg.norm(Xg, axis=1), 1.0, atol=1e-4):
                fails.append("A7 gray embed not L2-normalized")
            g = sf.plan_round0(Xg, budget=10, seed=0)
            if not g["indices"]:
                fails.append("A7 plan_round0 returned nothing on gray embeddings")
    except ImportError:
        print("  A7 SKIP (cv2 unavailable)")


def section_b(fails):
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["FIELD2026_ANALYSIS_OUT_ROOT"] = tmp
        import importlib
        import output_paths as op
        importlib.reload(op)
        root = Path(tmp)

        run = op.run_dir("cv_field_select", COH)
        if run.parent != root / COH or not (run / "figures").is_dir():
            fails.append(f"B run_dir wrong: {run}")
        rep = op.report_dir(COH, "cv_field")
        fig = op.figure_dir(COH, "cv_field")
        if rep != op.PROJECT_ROOT / "results" / COH / "cv_field" / "reports":
            fails.append(f"B report_dir wrong: {rep}")
        if fig.parent != rep.parent:
            fails.append("B figure_dir not a sibling of reports")
        assets = op.assets_dir(COH, "cv_field")
        if assets.parent.parent != root / COH:
            fails.append(f"B assets_dir wrong: {assets}")
        ptr = op.write_run_manifest(rep, run, cohort=COH, direction="cv_field")
        if json.loads(ptr.read_text())["run_dir"] != str(run.resolve()):
            fails.append("B run_manifest did not name the run dir")

        # measurement_context embedding + active_learning blocks (+ round flips the id; omission is clean)
        try:
            import measurement_context as mc
            emb = fe.embedding_fingerprint("gray", None, 50)
            base_args = dict(date="2026-06-28", weights=None, conf=None, imgsz=None, batch=None, device="cpu")
            c0 = mc.build_context("cv_field/select_frames.py", Namespace(**base_args), ["CH01"],
                                  embedding=emb, active_learning={"round": 0, "budget": 48})
            c1 = mc.build_context("cv_field/select_frames.py", Namespace(**base_args), ["CH01"],
                                  embedding=emb, active_learning={"round": 1, "budget": 48})
            if c0["detector"].get("embedding") != emb:
                fails.append("B embedding block not attached to detector")
            if "active_learning" not in c0:
                fails.append("B active_learning block missing")
            if c0["mc_run_id"] == c1["mc_run_id"]:
                fails.append("B mc_run_id did not flip when the round changed")
            shelter = mc.build_context("shelter_sleep.py", Namespace(**base_args), ["CH05"])
            if "active_learning" in shelter or "embedding" in shelter["detector"]:
                fails.append("B shelter manifest gained cv_field keys (byte-identity broken)")
        except ImportError:
            print("  B measurement_context SKIP (pandas unavailable)")

        shutil.rmtree(op.PROJECT_ROOT / "results" / COH, ignore_errors=True)


def main() -> int:
    fails: list[str] = []
    section_a(fails)
    section_b(fails)
    if fails:
        print("FAIL — cv_field selector self-test")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("PASS — cv_field selector self-test (planted-cluster coverage / uncertainty / determinism / paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
