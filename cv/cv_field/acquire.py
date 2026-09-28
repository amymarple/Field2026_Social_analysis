"""acquire.py — uncertainty + diversity acquisition scoring for cv_field active-learning rounds >= 1.

Pure numpy, deterministic under a seed, unit-tested in the self-test. Once a seed detector exists, each
unlabeled frame gets an uncertainty ``u`` and is selected by **uncertainty-weighted k-center (farthest-first)**
so that it is BOTH uncertain AND far from what is already labeled — the product score both spreads the picks
across the embedding and kills near-duplicate hard frames instead of re-labeling them.

  uncertainty(cmax, n, n_flip) = max( confidence-margin , count-instability-under-flip-TTA )   in [0, 1]
  acquisition a(f | A)         = u(f) ** gamma  *  d(f, A)

where ``d(f, A)`` is the min Euclidean distance from frame ``f`` to the covered set ``A`` (labeled ∪ already
picked) in the L2-normalized embedding, so it shrinks to ~0 for near-duplicates and is large for unexplored
regions. A fraction ``explore_frac`` of the budget is spent on pure farthest-point exploration (``u`` ignored)
to cover the detector's confident blind spots. ``random_baseline`` provides the equal-budget control the
Phase-2 falsification check compares against.
"""
from __future__ import annotations

import numpy as np


def uncertainty(cmax, n, n_flip, tau: float = 0.40) -> np.ndarray:
    """Per-frame uncertainty in [0, 1].

    ``cmax`` = the detector's max box confidence on the frame; ``n`` = box count; ``n_flip`` = box count on a
    horizontal-flip TTA pass. ``margin`` peaks when ``cmax`` sits on the decision boundary ``tau`` (most
    ambiguous); ``count_instability`` fires when the flip changes the count. The max keeps a frame that is
    uncertain by EITHER signal."""
    cmax = np.asarray(cmax, np.float64)
    n = np.asarray(n, np.float64)
    n_flip = np.asarray(n_flip, np.float64)
    margin = 1.0 - np.clip(np.abs(cmax - tau) / max(tau, 1e-6), 0.0, 1.0)
    instab = np.minimum(1.0, np.abs(n - n_flip) / np.maximum(n, 1.0))
    return np.maximum(margin, instab)


def greedy_acquire(X, u, k, labeled_idx=None, gamma: float = 1.0,
                   explore_frac: float = 0.15, seed: int = 0, exclude=None):
    """Greedily select ``k`` indices by uncertainty-weighted k-center ``a(f|A) = u**gamma * d(f,A)``,
    recomputing the min-distance to the covered set ``A`` (labeled ∪ already-picked) after each pick.

    When ``A`` is empty the first pick maximizes ``u`` alone (all distances are infinite). Reserves
    ``explore_frac`` of ``k`` for pure farthest-point exploration (``u`` ignored). Returns a list of indices."""
    X = np.asarray(X, np.float64)
    N = len(X)
    u = np.asarray(u, np.float64)
    labeled = list(dict.fromkeys(labeled_idx or []))
    excl = set(labeled) | set(exclude or [])
    k = int(min(k, N - len(excl)))
    if k <= 0:
        return []

    d = np.full(N, np.inf)
    for c in labeled:
        d = np.minimum(d, np.sqrt(((X - X[c]) ** 2).sum(1)))

    def _pick(score):
        s = score.copy()
        if excl:
            s[list(excl)] = -np.inf
        return int(np.argmax(s))

    picked = []
    n_explore = int(round(explore_frac * k))
    n_acq = k - n_explore

    for _ in range(n_acq):
        score = u.copy() if np.isinf(d).all() else (u ** gamma) * d   # empty A -> max-u seed
        j = _pick(score)
        picked.append(j)
        excl.add(j)
        d = np.minimum(d, np.sqrt(((X - X[j]) ** 2).sum(1)))

    for _ in range(n_explore):
        j = _pick(d)
        picked.append(j)
        excl.add(j)
        d = np.minimum(d, np.sqrt(((X - X[j]) ** 2).sum(1)))

    return picked


def random_baseline(N, k, exclude=None, seed: int = 0):
    """Equal-budget random selection (the Phase-2 falsification control). Returns ``k`` indices."""
    excl = set(exclude or [])
    pool = np.array([i for i in range(int(N)) if i not in excl])
    k = int(min(k, len(pool)))
    return np.random.default_rng(seed).choice(pool, k, replace=False).tolist()
