"""field_cluster.py — numpy clustering + K-selection + coverage sampling for cv_field active learning.

Everything the round-0 diversity selector needs, numpy-only and deterministic under a seed:

  * ``kmeans`` — sklearn KMeans when available, else the bundled ``kmeans_numpy`` (k-means++ init + Lloyd).
  * ``bic_xmeans`` / ``choose_k`` — Pelleg-Moore-style BIC to pick K at the knee (capped by the budget).
  * ``medoids`` — the most-central real frame per cluster (typical exemplars).
  * ``farthest_point_sample`` — greedy k-center coverage of rare/edge regimes, seedable by the medoids.
  * ``pca_competitor_report`` — the falsification guard: a single smooth Gaussian's BIC vs the k-means BIC,
    documenting that "any continuous space partitions into clusters, so clustering is not evidence of
    discreteness" (mirrors the discipline in wiser/src/route_vocabulary.py). Clusters here are only a
    labeling heuristic, never a behavioral-type claim.

sklearn is imported LAZILY inside ``kmeans`` / ``pca_competitor_report`` with a numpy fallback, so the
offline self-test passes with only numpy while production still gets sklearn's robustness.
"""
from __future__ import annotations

import numpy as np


# ------------------------------------------------------------------ distances
def _sqdist(X, C) -> np.ndarray:
    """(n, K) squared distances via the dot-product identity — no (n, K, d) intermediate."""
    X = np.asarray(X, np.float64)
    C = np.asarray(C, np.float64)
    return (X ** 2).sum(1)[:, None] - 2.0 * X @ C.T + (C ** 2).sum(1)[None, :]


# ------------------------------------------------------------------ k-means (numpy fallback + sklearn)
def _kmeanspp_init(X, K, rng) -> np.ndarray:
    n = X.shape[0]
    first = int(rng.integers(n))
    idx = [first]
    d2 = ((X - X[first]) ** 2).sum(1)
    for _ in range(1, K):
        s = d2.sum()
        probs = (d2 / s) if s > 0 else np.full(n, 1.0 / n)
        j = int(rng.choice(n, p=probs))
        idx.append(j)
        d2 = np.minimum(d2, ((X - X[j]) ** 2).sum(1))
    return X[idx].astype(np.float64).copy()


def kmeans_numpy(X, K, seed: int = 0, n_init: int = 4, max_iter: int = 100):
    """k-means++ init + Lloyd, best of ``n_init`` restarts. Returns (labels (n,), centers (K, d) float32)."""
    X = np.asarray(X, np.float64)
    n = X.shape[0]
    K = int(max(1, min(K, n)))
    best = None
    for run in range(n_init):
        rng = np.random.default_rng(seed + run)
        C = _kmeanspp_init(X, K, rng)
        labels = np.full(n, -1, dtype=int)
        for it in range(max_iter):
            new = _sqdist(X, C).argmin(1)
            if it > 0 and np.array_equal(new, labels):
                labels = new
                break
            labels = new
            for k in range(K):
                m = labels == k
                C[k] = X[m].mean(0) if m.any() else X[int(rng.integers(n))]
        inertia = float(((X - C[labels]) ** 2).sum())
        if best is None or inertia < best[0]:
            best = (inertia, labels.copy(), C.copy())
    return best[1], best[2].astype(np.float32)


def kmeans(X, K, seed: int = 0, n_init: int = 4):
    """sklearn KMeans if importable (robust), else numpy fallback. Deterministic under ``seed``."""
    try:
        from sklearn.cluster import KMeans
        km = KMeans(n_clusters=int(max(1, min(K, len(X)))), random_state=seed, n_init=n_init)
        labels = km.fit_predict(np.asarray(X, np.float64))
        return labels.astype(int), km.cluster_centers_.astype(np.float32)
    except Exception:  # noqa: BLE001 — sklearn absent or failed: numpy fallback keeps the self-test green
        return kmeans_numpy(X, K, seed=seed, n_init=n_init)


# ------------------------------------------------------------------ model selection (BIC)
def bic_xmeans(X, labels, centers) -> float:
    """Pelleg-Moore x-means BIC (LOWER is better) for a K-means solution with pooled spherical variance."""
    X = np.asarray(X, np.float64)
    N, d = X.shape
    K = int(np.asarray(centers).shape[0])
    rss = float(((X - np.asarray(centers)[labels]) ** 2).sum())
    var = max(rss / max((N - K) * d, 1), 1e-9)
    ll = 0.0
    for k in range(K):
        n_k = int((labels == k).sum())
        if n_k <= 1:
            continue
        ll += (n_k * np.log(n_k) - n_k * np.log(N)
               - 0.5 * n_k * d * np.log(2 * np.pi * var)
               - 0.5 * (n_k - 1) * d)
    p = (K - 1) + K * d + 1                     # mixing + means + one variance
    return float(-2 * ll + p * np.log(max(N, 2)))


def _silhouette(X, labels) -> float:
    """Mean silhouette (higher = better-separated). O(m^2) — call on a subsample for large pools."""
    X = np.asarray(X, np.float64)
    m = len(X)
    uniq = np.unique(labels)
    if len(uniq) < 2 or m < 3:
        return -1.0
    D = np.sqrt(np.maximum(_sqdist(X, X), 0.0))
    sil = np.zeros(m)
    for i in range(m):
        same = labels == labels[i]
        same[i] = False
        if not same.any():          # singleton cluster: silhouette 0 (sklearn convention) — never reward it,
            sil[i] = 0.0            # else scattered outliers each become their own cluster and inflate K
            continue
        a = D[i, same].mean()
        b = np.inf
        for c in uniq:
            if c == labels[i]:
                continue
            mask = labels == c
            if mask.any():
                b = min(b, D[i, mask].mean())
        denom = max(a, b)
        sil[i] = 0.0 if denom == 0 else (b - a) / denom
    return float(sil.mean())


def choose_k(X, k_grid=None, budget=None, seed: int = 0, sample: int = 1500):
    """Pick K maximizing the mean silhouette over ``k_grid`` (capped at ``budget//2`` and 40).

    Silhouette is used instead of a Gaussian BIC because the embedding is L2-normalized (unit sphere), where
    a likelihood-based BIC rewards ever-smaller within-cluster variance and over-segments. Subsamples to
    ``sample`` points so the O(m^2) silhouette stays bounded on large pools. Returns (K, info)."""
    N = len(X)
    Xs = X if N <= sample else np.asarray(X)[np.random.default_rng(seed).choice(N, sample, replace=False)]
    cap = min(len(Xs) - 1, 40)
    if budget:
        cap = min(cap, max(2, budget // 2))
    if k_grid is None:
        k_grid = list(range(2, cap + 1))
    scores, best = {}, None
    for K in k_grid:
        if K < 2 or K > min(len(Xs) - 1, cap):
            continue
        labels, _ = kmeans(Xs, K, seed=seed)
        s = _silhouette(Xs, labels)
        scores[K] = s
        if best is None or s > best[1]:
            best = (K, s)
    return (best[0] if best else max(2, min(2, N))), {"silhouette": scores, "cap": cap}


# ------------------------------------------------------------------ exemplar + coverage selection
def medoids(X, labels):
    """Index of the most-central real point per cluster (label order). One exemplar per cluster."""
    X = np.asarray(X, np.float64)
    out = []
    for k in sorted({int(v) for v in np.asarray(labels).tolist()}):
        idx = np.where(np.asarray(labels) == k)[0]
        if len(idx) == 0:
            continue
        sub = X[idx]
        j = idx[int(np.argmin(((sub - sub.mean(0)) ** 2).sum(1)))]
        out.append(int(j))
    return out


def farthest_point_sample(X, n, init=None, seed: int = 0, exclude=None):
    """Greedy k-center: return ``n`` NEW indices maximizing min-distance to the covered set.

    ``init`` seeds coverage (e.g. the medoids) but is NOT returned; ``exclude`` is also never returned. When
    ``init`` is empty a random first point is chosen (seeded) and counted toward ``n``."""
    X = np.asarray(X, np.float64)
    N = len(X)
    init = list(dict.fromkeys(init or []))
    excl = set(init) | set(exclude or [])
    d = np.full(N, np.inf)
    for c in init:
        d = np.minimum(d, ((X - X[c]) ** 2).sum(1))
    picked = []
    if not init:
        first = int(np.random.default_rng(seed).integers(N))
        picked.append(first)
        excl.add(first)
        d = np.minimum(d, ((X - X[first]) ** 2).sum(1))
    n = int(min(n, N - len(excl) + (1 if (not init) else 0)))
    if excl:
        d[list(excl)] = -np.inf
    while len(picked) < n:
        j = int(np.argmax(d))
        picked.append(j)
        d = np.minimum(d, ((X - X[j]) ** 2).sum(1))
        d[j] = -np.inf
    return picked


# ------------------------------------------------------------------ falsification guard
def pca_competitor_report(X, K, seed: int = 0) -> dict:
    """Compare the K-means BIC against a single full-covariance Gaussian ("smooth model") BIC.

    If the smooth model is competitive, the K clusters are not evidence of discrete structure — they remain
    a labeling heuristic only. This never gates selection; it is recorded for the milestone audit."""
    labels, C = kmeans(X, K, seed=seed)
    bic_km = bic_xmeans(X, labels, C)
    Xd = np.asarray(X, np.float64)
    N, d = Xd.shape
    mean = Xd.mean(0)
    cov = np.cov(Xd.T) + 1e-6 * np.eye(d)
    _, logdet = np.linalg.slogdet(cov)
    diff = Xd - mean
    maha = np.einsum("ij,jk,ik->i", diff, np.linalg.pinv(cov), diff)
    ll = -0.5 * (N * d * np.log(2 * np.pi) + N * logdet + float(maha.sum()))
    p_g = d + d * (d + 1) / 2.0
    bic_g = float(-2 * ll + p_g * np.log(max(N, 2)))
    return {"K": int(K), "bic_kmeans": float(bic_km), "bic_single_gaussian": bic_g,
            "smooth_model_competitive": bool(bic_g <= bic_km),
            "note": "clusters are a labeling heuristic, not evidence of behavioral discreteness"}
