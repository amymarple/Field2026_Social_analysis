r"""
route_vocabulary.py — out-of-sample validation of the "discrete shared route vocabulary"
hypothesis for WISER route bouts.

Phase B established route RECURRENCE (near-identical partner routes exist) and that recurring
routes are SHARED. Recurrence is NOT the stronger claim that continuous 2-D movement compresses
into a finite, shared, *out-of-sample* dictionary of route prototypes
(``trajectory_i ≈ prototype_{m_i} + small residual``). Any continuous space partitions into
clusters, so clustering output is not evidence of discreteness. This module supplies the
falsification-first primitives: held-out compression, cross-animal generalisation, endpoint-vs-shape
decomposition, geometry-preserving nulls, first-night closure.

HARD RULE (frame). All distances are INCHES in the WISER native, UNVERIFIED offset frame, so every
result is TOPOLOGICAL / RELATIVE only — never a metric or directional route claim. This is
``route_corridor_selection`` (Module 11, status BLOCKED) in
``configs/behavioral_policy_modules.yaml``; the expected verdict ceiling is B/C, not A.

Primitives only (numpy + scipy + sklearn — run under anaconda3). Orchestration + nulls-as-analyses
live in ``scripts/analyze_route_vocabulary.py``. Paths are arc-length-resampled ``(N, L, 2)`` arrays
(L points, absolute inch coords) exactly as produced by ``trajectory_stereotypy.extract_route_bouts``.

DEFINITIONS (formula + text) — see the analysis report for the full block; kept short here.
  - route distance D(a,b) = (1/L) Σ_k ||a_k − b_k||   (mean-pointwise, inches). frechet = max_k.
  - dictionary = a frozen set of K prototype paths learned from TRAIN data only.
  - residual r_i = min_m D(path_i, proto_m)  (nearest-prototype distance, inches).
  - coverage@τ = fraction of held-out paths with r_i ≤ τ.  novelty = fraction with r_i > θ.
  - MDL bits L(K) = dict_bits + assignment_bits + residual_bits  (explicit coding model below).
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

import trajectory_stereotypy as ts   # path_distance_matrix, cluster_paths_leader (src on sys.path)


# ---------------------------------------------------------------------------
# distances / assignment
# ---------------------------------------------------------------------------

def cross_distance(protos: np.ndarray, paths: np.ndarray, *, metric: str = "mean") -> np.ndarray:
    r"""(K, N) location-anchored path distance between K prototype paths and N paths.

    Both are arc-length-resampled to the same L, so index k corresponds. ``metric="mean"`` =
    mean-pointwise D(a,b)=(1/L)Σ_k||a_k−b_k||; ``metric="frechet"`` = max-pointwise. Inches.
    """
    protos = np.asarray(protos, float)
    paths = np.asarray(paths, float)
    if len(protos) == 0 or len(paths) == 0:
        return np.zeros((len(protos), len(paths)), float)
    D = np.zeros((len(protos), len(paths)), float)
    for k in range(len(protos)):
        pt = np.sqrt(((paths - protos[k]) ** 2).sum(2))     # (N, L)
        D[k] = pt.mean(1) if metric == "mean" else pt.max(1)
    return D


def assign(paths: np.ndarray, protos: np.ndarray, *, metric: str = "mean"):
    """Nearest-prototype index + residual (in) per path. Empty dictionary -> idx=-1, residual=inf."""
    paths = np.asarray(paths, float)
    if len(protos) == 0:
        return np.full(len(paths), -1, int), np.full(len(paths), np.inf)
    D = cross_distance(protos, paths, metric=metric)         # (K, N)
    return D.argmin(0), D.min(0)


def assign_full(paths: np.ndarray, protos: np.ndarray, *, metric: str = "mean"):
    """As ``assign`` but also returns the total sum-of-squared residual scalars (SSE) needed for
    the MDL residual-coding term. reconstruction = the assigned prototype path."""
    idx, res = assign(paths, protos, metric=metric)
    if len(protos) == 0:
        recon = np.zeros_like(paths)
    else:
        recon = np.asarray(protos, float)[idx]
    sse = float(((np.asarray(paths, float) - recon) ** 2).sum())
    return idx, res, sse


def resid_of(paths: np.ndarray, recon: np.ndarray) -> np.ndarray:
    """Per-path mean-pointwise residual (in) between paths and their reconstructions."""
    return np.sqrt(((np.asarray(paths, float) - np.asarray(recon, float)) ** 2).sum(2)).mean(1)


# ---------------------------------------------------------------------------
# dictionaries (learned on TRAIN only, then frozen)
# ---------------------------------------------------------------------------

def learn_leader_dictionary(paths_train: np.ndarray, *, theta: float, metric: str = "mean"):
    """Leader-medoid dictionary: greedy leader clustering of TRAIN paths at threshold ``theta``
    (``ts.cluster_paths_leader``, non-chaining), each cluster's MEDOID path frozen as a prototype.

    Returns (protos ``(K, L, 2)``, info). Prototypes are real training routes.
    """
    paths_train = np.asarray(paths_train, float)
    if len(paths_train) == 0:
        return paths_train.reshape(0, *paths_train.shape[1:]), {"K": 0, "theta": theta}
    D = ts.path_distance_matrix(paths_train, metric=metric)
    labels = ts.cluster_paths_leader(D, threshold=theta)
    protos = []
    for m in range(int(labels.max()) + 1):
        idx = np.where(labels == m)[0]
        sub = D[np.ix_(idx, idx)]
        protos.append(paths_train[idx[int(sub.sum(1).argmin())]])
    return np.asarray(protos, float), {"K": len(protos), "theta": float(theta)}


def kmeans_dictionary(paths_train: np.ndarray, *, K: int, seed: int = 0):
    """K-means dictionary in flattened path space R^(2L); prototypes = centroids reshaped to
    ``(K, L, 2)`` (pointwise-mean paths). ``K`` clamped to n_train. Deterministic (fixed seed).

    Centroids are continuous prototypes (not real routes) — appropriate for the compression sweep.
    """
    from sklearn.cluster import KMeans
    paths_train = np.asarray(paths_train, float)
    n, L, _ = paths_train.shape
    if n == 0:
        return paths_train.reshape(0, L, 2), {"K": 0, "seed": seed}
    K = int(max(1, min(K, n)))
    X = paths_train.reshape(n, -1)
    km = KMeans(n_clusters=K, n_init=4, random_state=seed).fit(X)
    return km.cluster_centers_.reshape(K, L, 2), {"K": K, "seed": int(seed)}


def global_mean_prototype(paths_train: np.ndarray) -> np.ndarray:
    """Single global prototype (K=1) = pointwise mean path. The most-compressed baseline."""
    paths_train = np.asarray(paths_train, float)
    if len(paths_train) == 0:
        return paths_train.reshape(0, *paths_train.shape[1:])
    return paths_train.mean(0)[None]


# ---------------------------------------------------------------------------
# endpoint models (Analysis 4 — is a "motif" just a repeated start/end pair?)
# ---------------------------------------------------------------------------

def endpoint_line_paths(paths: np.ndarray) -> np.ndarray:
    """ENDPOINT-ONLY reconstruction: constant-speed straight line between each path's OWN start and
    end -> ``(N, L, 2)``. Discards all shape; keeps only the two endpoints. Residual vs this line =
    how much route shape exists beyond the straight endpoint chord."""
    paths = np.asarray(paths, float)
    N, L, _ = paths.shape
    t = np.linspace(0.0, 1.0, L)[None, :, None]
    return paths[:, :1, :] * (1 - t) + paths[:, -1:, :] * t


def endpoint_key(paths: np.ndarray, *, bin_in: float):
    """Coarse, DIRECTION-PRESERVING endpoint stratum key (start_bin_x, start_bin_y, end_bin_x,
    end_bin_y) by gridding the start and end at ``bin_in`` inches. Two bouts share a key iff they
    start and end in the same coarse cell in the same order."""
    paths = np.asarray(paths, float)
    s = np.floor(paths[:, 0, :] / bin_in).astype(int)
    e = np.floor(paths[:, -1, :] / bin_in).astype(int)
    return [(int(s[i, 0]), int(s[i, 1]), int(e[i, 0]), int(e[i, 1])) for i in range(len(paths))]


def endpoint_conditioned_recon(paths_train: np.ndarray, paths_test: np.ndarray, *, bin_in: float):
    """One TRAIN mean path per endpoint stratum; reconstruct each test path with its stratum's mean.
    Unseen stratum -> fall back to the test path's OWN straight chord (NOT the global mean: a
    global-mean fallback contaminates the endpoint model with the between-location variance it is
    meant to control for, spuriously inflating the error and under-crediting endpoints). Returns
    (res (in), n_novel_endpoint)."""
    paths_train = np.asarray(paths_train, float)
    paths_test = np.asarray(paths_test, float)
    ktr, kte = endpoint_key(paths_train, bin_in=bin_in), endpoint_key(paths_test, bin_in=bin_in)
    chords = endpoint_line_paths(paths_test)
    groups = defaultdict(list)
    for i, k in enumerate(ktr):
        groups[k].append(i)
    means = {k: paths_train[idx].mean(0) for k, idx in groups.items()}
    recon = np.zeros_like(paths_test)
    novel = 0
    for i, k in enumerate(kte):
        if k in means:
            recon[i] = means[k]
        else:
            recon[i] = chords[i]
            novel += 1
    return resid_of(paths_test, recon), int(novel)


def endpoint_conditioned_multi(paths_train, paths_test, *, bin_in, theta, metric="mean"):
    """Within each endpoint stratum, learn a leader dictionary (θ) from TRAIN and reconstruct each
    test path by its stratum's NEAREST prototype (fallback: global train mean). Captures path-shape
    structure BEYOND endpoints. Returns (res (in), mean_protos_per_seen_stratum)."""
    paths_train = np.asarray(paths_train, float)
    paths_test = np.asarray(paths_test, float)
    ktr, kte = endpoint_key(paths_train, bin_in=bin_in), endpoint_key(paths_test, bin_in=bin_in)
    groups = defaultdict(list)
    for i, k in enumerate(ktr):
        groups[k].append(i)
    protos, nproto = {}, []
    for k, idx in groups.items():
        pr, info = learn_leader_dictionary(paths_train[idx], theta=theta, metric=metric)
        protos[k] = pr
        nproto.append(info["K"])
    chords = endpoint_line_paths(paths_test)
    recon = np.zeros_like(paths_test)
    for i, k in enumerate(kte):
        pr = protos.get(k)
        if pr is not None and len(pr):
            j = int(cross_distance(pr, paths_test[i:i + 1], metric=metric).argmin())
            recon[i] = pr[j]
        else:
            recon[i] = chords[i]        # unseen stratum -> own chord, not global mean
    return resid_of(paths_test, recon), (float(np.mean(nproto)) if nproto else 0.0)


# ---------------------------------------------------------------------------
# continuous competitor (Analysis 3 — does a discrete dictionary beat a smooth low-dim model?)
# ---------------------------------------------------------------------------

def pca_reconstruct(paths_train: np.ndarray, paths_test: np.ndarray, *, M: int, seed: int = 0):
    """Functional-PCA competitor: fit PCA on TRAIN flattened paths, keep M components, reconstruct
    TEST. Returns (res (in), info{M, n_params}). n_params = M*(2L) basis + 2L mean."""
    from sklearn.decomposition import PCA
    paths_train = np.asarray(paths_train, float)
    paths_test = np.asarray(paths_test, float)
    n, L, _ = paths_train.shape
    M = int(max(1, min(M, n, 2 * L)))
    p = PCA(n_components=M, random_state=seed).fit(paths_train.reshape(n, -1))
    rec = p.inverse_transform(p.transform(paths_test.reshape(len(paths_test), -1))).reshape(len(paths_test), L, 2)
    res = resid_of(paths_test, rec)
    sse = float(((paths_test - rec) ** 2).sum())
    return res, {"M": M, "n_params": int(M * 2 * L + 2 * L), "sse": sse}


# ---------------------------------------------------------------------------
# coverage / compression scores
# ---------------------------------------------------------------------------

def coverage(res, thresholds=(10.5, 21.0, 42.0)) -> dict:
    res = np.asarray(res, float)
    return {float(t): float(np.mean(res <= t)) if res.size else float("nan") for t in thresholds}


def novelty_frac(res, theta: float) -> float:
    res = np.asarray(res, float)
    return float(np.mean(res > theta)) if res.size else float("nan")


def error_summary(res, *, theta: float, thresholds=(10.5, 21.0, 42.0)) -> dict:
    res = np.asarray(res, float)
    out = {"n": int(res.size),
           "mean_resid_in": float(np.mean(res)) if res.size else float("nan"),
           "median_resid_in": float(np.median(res)) if res.size else float("nan"),
           "p90_resid_in": float(np.percentile(res, 90)) if res.size else float("nan"),
           "novelty_frac": novelty_frac(res, theta)}
    for t, v in coverage(res, thresholds).items():
        out[f"cov_{int(round(t))}in"] = v
    return out


def mdl_bits(N: int, K: int, L: int, sse: float, *, sigma_in: float, bits_per_param: int = 16) -> dict:
    r"""Explicit minimum-description-length code length (bits) for encoding N held-out paths as
    (prototype id + Gaussian residual). STATED coding model:

      dict_bits      = K · (2L) · bits_per_param          # prototype coordinates
      assignment_bits= N · log2(K)                        # which prototype per path (0 if K=1)
      residual_bits  = n_scalars · ½log2(2πe σ²) + SSE / (2 σ² ln2)   # Gaussian NLL in bits

    with n_scalars = N·L·2 and σ = ``sigma_in`` the assumed residual std (state it; default = jitter
    floor). As K grows dict_bits rises linearly and residual_bits falls; a genuine discrete scale
    shows a REPRODUCIBLE MINIMUM in ``total_bits``, a continuous manifold shows a monotone/plateau.
    """
    K = max(int(K), 1)
    n_scalars = N * L * 2
    sigma2 = float(sigma_in) ** 2
    dict_bits = K * (2 * L) * bits_per_param
    assign_bits = N * math.log2(K) if K > 1 else 0.0
    resid_bits = n_scalars * 0.5 * math.log2(2 * math.pi * math.e * sigma2) + sse / (2 * sigma2 * math.log(2))
    total = dict_bits + assign_bits + resid_bits
    return {"dict_bits": float(dict_bits), "assign_bits": float(assign_bits),
            "resid_bits": float(resid_bits), "total_bits": float(total),
            "bits_per_path": float(total / max(N, 1))}


def pca_mdl_bits(N: int, M: int, L: int, sse: float, *, sigma_in: float,
                 bits_per_param: int = 16, bits_per_coef: int = 16) -> dict:
    r"""Description length (bits) of a CONTINUOUS PCA code, for a fair discrete-vs-continuous
    comparison against ``mdl_bits``. A discrete dictionary spends only ``log2(K)`` bits/path on
    assignment; a continuous model must code ``M`` real coefficients/path. STATED model:

      mean_bits  = 2L · bits_per_param
      basis_bits = M · 2L · bits_per_param
      coef_bits  = N · M · bits_per_coef              # per-path continuous coordinates
      resid_bits = Gaussian NLL bits at σ (as in mdl_bits)

    If the data is genuinely CLUSTERED, coding M coefficients/path is dearer than a log2(K) index, so
    the discrete MDL wins; on a continuous manifold the PCA MDL wins. This — not reconstruction error
    at matched param count (K means always span a (K−1)-affine subspace, so PCA ties by construction)
    — is the correct discreteness test.
    """
    n_scalars = N * L * 2
    sigma2 = float(sigma_in) ** 2
    mean_bits = 2 * L * bits_per_param
    basis_bits = M * 2 * L * bits_per_param
    coef_bits = N * M * bits_per_coef
    resid_bits = n_scalars * 0.5 * math.log2(2 * math.pi * math.e * sigma2) + sse / (2 * sigma2 * math.log(2))
    total = mean_bits + basis_bits + coef_bits + resid_bits
    return {"mean_bits": float(mean_bits), "basis_bits": float(basis_bits),
            "coef_bits": float(coef_bits), "resid_bits": float(resid_bits),
            "total_bits": float(total), "bits_per_path": float(total / max(N, 1))}


def bic_gaussian(N: int, n_params: int, L: int, sse: float) -> float:
    """Gaussian BIC for a reconstruction with ``n_params`` free parameters:
    BIC = n·ln(SSE/n) + n_params·ln(n), n = N·L·2 residual scalars. Lower = better."""
    n = N * L * 2
    if n == 0 or sse <= 0:
        return float("nan")
    return float(n * math.log(sse / n) + n_params * math.log(n))


# ---------------------------------------------------------------------------
# geometry-preserving null (Analysis 5) — endpoints + wiggle preserved, template removed
# ---------------------------------------------------------------------------

def _bbridge(L: int, rng) -> np.ndarray:
    """Standard 1-D Brownian bridge on k=0..L-1, pinned to 0 at both ends."""
    incr = rng.standard_normal(max(L - 1, 1))
    bm = np.concatenate([[0.0], np.cumsum(incr)])[:L]
    t = np.arange(L) / max(L - 1, 1)
    return bm - t * bm[-1]


def brownian_bridge_null(paths: np.ndarray, *, seed: int = 0) -> np.ndarray:
    """Endpoint-preserving geometry null: replace each path's SHAPE with an independent 2-D Brownian
    bridge between its own endpoints, scaled so the surrogate's RMS deviation from the chord matches
    the real path's. Keeps endpoints + enclosure geometry + per-bout wiggle amplitude, but destroys
    any REUSED template (each surrogate is random). A real route vocabulary must beat this on
    recurrence, coverage, and compression; if it does not, apparent motifs are explained by
    endpoints + bounded wiggle. Returns surrogate paths ``(N, L, 2)``."""
    paths = np.asarray(paths, float)
    N, L, _ = paths.shape
    rng = np.random.default_rng(seed)
    chord = endpoint_line_paths(paths)                       # (N, L, 2)
    dev = paths - chord                                      # real transverse deviation
    real_rms = np.sqrt((dev ** 2).sum(2).mean(1))            # (N,) per-path wiggle scale
    out = np.empty_like(paths)
    for i in range(N):
        b = np.column_stack([_bbridge(L, rng), _bbridge(L, rng)])   # (L, 2)
        b_rms = math.sqrt((b ** 2).sum(1).mean()) or 1.0
        out[i] = chord[i] + b * (real_rms[i] / b_rms)
    return out


# ---------------------------------------------------------------------------
# endpoint-registered (pose-normalized) shape test — the FAIR "does path shape
# carry reusable info BEYOND the endpoints?" test (A4). Factoring out translation
# + rotation removes the endpoints, so what remains is pure shape (curvature).
# ---------------------------------------------------------------------------

def pose_normalize(paths: np.ndarray):
    """Translate + rotate each path so its start is at the origin and its end lies on the +x axis.
    Removes location and heading, leaving pure SHAPE (the curvature between the two endpoints). Two
    routes with the same bend at different places/headings map to the SAME normalized shape. Returns
    (normed (N, L, 2), disp (N,) endpoint distances). Scale is KEPT (inches), so residuals stay in in."""
    paths = np.asarray(paths, float)
    start = paths[:, :1, :]
    v = paths - start                                  # start -> origin
    end = v[:, -1, :]
    ang = np.arctan2(end[:, 1], end[:, 0])
    c, s = np.cos(-ang), np.sin(-ang)
    R = np.stack([np.stack([c, -s], -1), np.stack([s, c], -1)], -2)   # (N, 2, 2)
    normed = np.einsum('nij,nlj->nli', R, v)
    return normed, np.hypot(end[:, 0], end[:, 1])


def shape_beyond_endpoints_test(paths_train, paths_test, *, theta, seed=0, margin_in=0.5):
    """FAIR test of reusable path shape beyond endpoints. Factor out the FULL endpoint pair
    (translation + rotation + SCALE) so only unit-scale CURVATURE remains — the endpoint pair fixes
    location, heading AND length, so a proper 'beyond endpoints' test must remove scale too (else
    length variation across routes swamps the shape clustering). Cluster in the unit-scale frame with
    the threshold tied to the physical θ via the training median length, but report every residual
    SCALED BACK to each route's own size (inches), so short routes are not noise-amplified in the
    metric. Compares held-out reconstruction by (a) the straight segment [no shape], (b) a frozen
    unit-scale SHAPE dictionary [reusable curvature], (c) a matched Brownian-bridge null [shape
    destroyed]. Reusable shape exists iff (b) beats BOTH (a) and (c) by ``margin_in``."""
    ntr, dtr = pose_normalize(paths_train)
    nte, dte = pose_normalize(paths_test)
    dtr = np.maximum(dtr, 1e-6); dte = np.maximum(dte, 1e-6)
    utr = ntr / dtr[:, None, None]                       # unit-scale shapes (endpoints at 0 and (1,0))
    ute = nte / dte[:, None, None]
    theta_n = float(theta / max(np.median(dtr), 1e-6))   # same physical tolerance, normalized units
    e_straight = float((resid_of(ute, endpoint_line_paths(ute)) * dte).mean())   # back to inches
    protos, info = learn_leader_dictionary(utr, theta=theta_n)
    _, rd = assign(ute, protos); e_dict = float((rd * dte).mean())
    pn, _ = learn_leader_dictionary(brownian_bridge_null(utr, seed=seed), theta=theta_n)
    _, rn = assign(brownian_bridge_null(ute, seed=seed + 1), pn); e_null = float((rn * dte).mean())
    reusable = bool(e_dict < e_straight - margin_in and e_dict < e_null - margin_in)
    return {"E_pn_straight_in": round(e_straight, 2), "E_pn_shapedict_in": round(e_dict, 2),
            "E_pn_null_in": round(e_null, 2), "K_shape": info["K"], "theta_norm": round(theta_n, 3),
            "shape_beyond_endpoints": reusable}


# ---------------------------------------------------------------------------
# interim verdict (A/B/C/D) — the single decision the study exists to make
# ---------------------------------------------------------------------------

# Explicit criteria booleans consumed by decide_verdict (all computed in the driver from the
# held-out tables at documented thresholds). Kept in the module so the A/B/C/D boundaries are
# unit-tested by selftest_route_vocabulary.py on planted scenarios.
VERDICT_CRITERIA = (
    "mdl_has_finite_min",       # MDL total minimised at K < K_max (a discrete scale exists)
    "dict_beats_pca",           # dictionary held-out error < PCA (continuous) at matched #params
    "novelty_saturates",        # held-out novel-route fraction plateaus as training grows
    "loao_generalizes",         # other-animal dictionary ~ own-animal, and << random-null dictionary
    "beats_geometry_null",      # real coverage/compression exceeds the endpoint-preserving null
    "shape_beyond_endpoints",   # motif identity reduces error beyond endpoints (path shape matters)
    "endpoint_explains_most",   # endpoints alone explain most apparent structure
)

_VERDICT_TEXT = {
    "A": ("A. Strong shared discrete route vocabulary — a finite prototype dictionary gives superior "
          "complexity-adjusted held-out compression, novelty saturates, prototypes generalise across "
          "animals, and it beats endpoint-only and geometry-preserving nulls."),
    "B": ("B. Shared spatial corridor / transition graph, NOT a discrete path vocabulary — repeated "
          "start/end locations (endpoints) explain most apparent motifs; path shape adds little beyond "
          "the endpoint pair."),
    "C": ("C. Continuous route manifold with useful quantisation — reconstruction improves smoothly "
          "with K (no stable finite scale) and/or a discrete dictionary does not beat a continuous "
          "low-dim model, but clustering remains pragmatically useful."),
    "D": ("D. Insufficient evidence — results depend on thresholds, leakage, global clustering, jitter "
          "scale, or unverified coordinates, or the real data does not beat the geometry-preserving "
          "null; the vocabulary claim is not supported and cannot be cleanly rejected either."),
}


_A_KEYS = ("mdl_has_finite_min", "dict_beats_pca", "novelty_saturates", "loao_generalizes",
           "beats_geometry_null", "shape_beyond_endpoints")


def decide_verdict(c: dict, *, insufficient_support: bool = False) -> dict:
    """Map the criteria booleans to an interim verdict A/B/C/D (falsification-first precedence).

    NB the geometry null is ENDPOINT-preserving, so ``beats_geometry_null`` measures path-shape
    structure *beyond* endpoints — a spatial-graph (endpoint) story CANNOT beat it, and should not
    (that failure is diagnostic, not 'insufficient'). Precedence:

      D  if support is too thin.
      A  discrete shared PATH vocabulary — every discreteness + generalisation criterion holds
         (incl. shape beyond endpoints surviving the endpoint-preserving null).
      B  spatial corridor / transition graph — a finite, reused set of endpoint pairs explains the
         motifs (endpoints explain most, no shape beyond endpoints, and a finite endpoint repertoire
         exists: novelty saturates or a finite-K MDL minimum). Not beating the endpoint null is
         EXPECTED here.
      C  continuous route manifold — path shape beyond endpoints exists but shows no stable finite-K
         scale / no discrete-vs-continuous MDL win; quantisation is still useful.
      D  otherwise — no finite reused structure in shape or endpoints; indistinguishable from null.

    The frame is UNVERIFIED, so even 'A' is reported with topological/relative language only.
    """
    g = lambda k: bool(c.get(k, False))   # noqa: E731
    reasons = []
    if insufficient_support:
        letter, r = "D", "insufficient comparable-state support"
    elif all(g(k) for k in _A_KEYS):
        letter, r = "A", ("finite-K MDL minimum + shorter code than continuous PCA + novelty "
                          "saturates + cross-animal generalisation + shape beyond endpoints (survives "
                          "the endpoint-preserving null)")
    elif g("endpoint_explains_most") and not g("shape_beyond_endpoints"):
        # endpoints (locations), not path shape, carry the structure. Finite reused endpoint set
        # (repertoire closes) => spatial graph (B); open/continuous endpoint set => manifold (C).
        if g("novelty_saturates"):
            letter, r = "B", ("a finite, reused set of endpoint pairs (spatial graph / corridors) "
                              "explains the motifs — the endpoint chord beats the shape dictionary and "
                              "the held-out repertoire closes; path shape adds ~nothing beyond the "
                              "endpoint pair, so the endpoint-preserving null is — correctly — not beaten")
        else:
            letter, r = "C", ("movement is point-to-point travel on a continuous ENDPOINT manifold — the "
                              "endpoint chord beats the shape dictionary (no path-shape vocabulary), but "
                              "the held-out endpoint-pair repertoire does not close (novelty does not "
                              "saturate); quantising into motifs is useful, but there is no finite "
                              "discrete vocabulary")
    elif g("shape_beyond_endpoints") or g("beats_geometry_null"):
        letter, r = "C", ("path shape beyond endpoints exists but shows no stable finite-K scale / no "
                          "discrete-vs-continuous MDL win; quantisation is useful but the repertoire is "
                          "a continuous manifold")
    else:
        letter, r = "D", ("no finite reused structure in shape or endpoints; not distinguishable from "
                          "the geometry null")
    reasons.append(r)
    return {"verdict": letter, "text": _VERDICT_TEXT[letter], "reasons": reasons,
            "criteria": {k: g(k) for k in VERDICT_CRITERIA}}
