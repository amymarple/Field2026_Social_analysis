r"""
trajectory_stereotypy.py — helpers for the trajectory-stereotypy / stabilization /
inter-animal-correlation analysis (nights 2026-06-28 → 07-05).

This is a THIN analysis layer on top of :mod:`wiser_analysis_utils` (imported as
``w``). It adds only what that module does not already have:

- a multi-day incremental-backup loader that **dedups on ``(shortid, ts_raw, x, y)``**
  (the daily ``*.csv.gz`` files overlap: ``06-30`` is a cumulative dump, ``07-01…``
  are true increments; ``reportid`` is per report-cycle, shared across tags, so it is
  NOT a per-fix key), preserving the QC columns;
- a **cross-midnight night window** (21:00→05:00) — ``w.select_route_window`` only
  handles a same-day block;
- **Phase A** — per-night per-animal occupancy maps, a **day-to-day stabilization
  curve**, a **pooled shared-corridor map + residual individual maps**, and the
  **control battery** (animal-label permutation, shared-density/residual expectation,
  time-shuffle circular-shift null, day-shuffle null, synchronous time-coupling);
- **Phase B** — a **stable-pairs-vs-herd** layer on top of ``w``'s validated
  ``following_*`` suite: per-night directional follow scores + circular-shift z,
  then pair-specificity (is co-movement concentrated in a subset?), stability (is it
  the same subset across nights?), leadership consistency, and group cohesion.

Everything reuses ``w``'s primitives (``occupancy_hist``, ``corridor_mask``,
``build_following_grid``, ``follow_scores_all``, ``following_null``, …) so the numbers
stay consistent with the rest of the pilot analysis. Units are **inches**; the WISER
frame is the UNVERIFIED offset-origin inch frame (no directional claims). Nothing
here writes to source data.
"""

from __future__ import annotations

from pathlib import Path
import glob
import warnings

import numpy as np
import pandas as pd

try:                                                  # package / flat import
    from . import wiser_analysis_utils as w
    from . import wiser_io
except ImportError:                                   # src on sys.path
    import wiser_analysis_utils as w                  # type: ignore
    import wiser_io                                    # type: ignore


# Raw columns we actually need from the wide (21-col) incremental CSV. Keeping
# usecols small holds memory down across ~12M rows.
_USECOLS = ["reportid", "shortid", "calculation_error", "location_x",
            "location_y", "location_z", "anchors_used", "timestamp",
            "battery_voltage"]


# ---------------------------------------------------------------------------
# 1. Multi-day incremental loader (dedup on reportid)
# ---------------------------------------------------------------------------

_DEDUP_KEY = ["shortid", "ts_raw", "x", "y"]


def load_incremental_days(incremental_dir: Path | str,
                          dates: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """
    Load the daily ``1stcohort_2026_<date>.csv.gz`` incremental backups and
    concatenate them, **deduplicating on ``(shortid, ts_raw, x, y)``**.

    The per-day files overlap (``06-30`` is a cumulative dump that already
    contains 06-28/06-29; ``07-01…`` are true daily increments), so a naive
    concat double-counts. NOTE: ``reportid`` is **NOT** a per-fix key — one report
    cycle covers all tags, so a single ``reportid`` is shared by several animals'
    fixes (verified: 82k reportid groups span different ``shortid``). Deduping on
    ``reportid`` would drop ~94k *distinct* fixes. The composite
    ``(shortid, ts_raw, x, y)`` is unique per fix (every row of a single file is
    distinct on it) and collapses only the exact backfill copies.

    Returns ``(df, log)`` where ``df`` has the canonical rich schema
    (``shortid, ts_raw, x, y[, z]`` + QC cols incl. ``reportid``) and ``log``
    records per-file row counts and how many duplicate rows dedup removed.
    """
    incremental_dir = Path(incremental_dir)
    files = sorted(glob.glob(str(incremental_dir / "1stcohort_2026_*.csv.gz")))
    if dates is not None:
        want = {str(d) for d in dates}
        files = [f for f in files if any(d in Path(f).name for d in want)]
    if not files:
        raise FileNotFoundError(f"No incremental gz files in {incremental_dir}")

    frames: list[pd.DataFrame] = []
    per_file: list[dict] = []
    for f in files:
        name = Path(f).name
        raw = pd.read_csv(f, compression="gzip", usecols=lambda c: c in _USECOLS)
        std = w._standardise_rich(raw, name)
        if std is None:
            per_file.append({"file": name, "rows_raw": int(len(raw)), "rows_kept": 0})
            continue
        frames.append(std)
        per_file.append({"file": name, "rows_raw": int(len(raw)),
                         "rows_kept": int(len(std))})

    combined = pd.concat(frames, ignore_index=True)
    n_before = len(combined)
    combined = combined.drop_duplicates(subset=_DEDUP_KEY).reset_index(drop=True)
    dedup_key = "+".join(_DEDUP_KEY)
    n_after = len(combined)

    log = {"files": per_file, "dedup_key": dedup_key,
           "rows_concatenated": int(n_before), "rows_after_dedup": int(n_after),
           "duplicate_rows_removed": int(n_before - n_after)}
    return combined, log


# ---------------------------------------------------------------------------
# 2. Cross-midnight night window (21:00 -> 05:00 local)
# ---------------------------------------------------------------------------

def add_night_label(df: pd.DataFrame, *, night_start: int = 21, night_end: int = 5,
                    tz_offset_hours: int = w.LOCAL_TZ_OFFSET_HOURS) -> pd.DataFrame:
    """
    Add ``local_dt``, ``clock_hour``, ``in_night`` and a ``night`` label that
    spans midnight: night *N* = local date *D* ``night_start``:00 → *D+1*
    ``night_end``:00. Early-morning fixes (hour < ``night_end``) are attributed to
    the *previous* calendar day's night. Requires ``datetime`` (naive UTC).
    """
    df = df.copy()
    loc = df["datetime"] + pd.Timedelta(hours=tz_offset_hours)
    df["local_dt"] = loc
    hour = loc.dt.hour
    df["clock_hour"] = hour
    df["in_night"] = (hour >= night_start) | (hour < night_end)
    # anchor date: same local day, except pre-dawn hours belong to the prior night
    anchor = loc.dt.normalize()
    early = hour < night_end
    anchor = anchor.mask(early, anchor - pd.Timedelta(days=1))
    df["night"] = anchor.dt.date.astype(str)
    return df


def select_night_window(df: pd.DataFrame, *, night_start: int = 21, night_end: int = 5,
                        tz_offset_hours: int = w.LOCAL_TZ_OFFSET_HOURS,
                        dates: list[str] | None = None,
                        valid_only: bool = True) -> pd.DataFrame:
    """Cleaned fixes inside the cross-midnight night window, tagged with ``night``.
    Mirrors ``w.select_route_window`` but for the 21:00→05:00 block."""
    d = df.dropna(subset=["datetime"]).copy()
    if valid_only and "valid" in d.columns:
        d = d[d["valid"]]
    d = add_night_label(d, night_start=night_start, night_end=night_end,
                        tz_offset_hours=tz_offset_hours)
    d = d[d["in_night"]]
    if dates:
        d = d[d["night"].isin([str(x) for x in dates])]
    return d.reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3. Per-night per-animal occupancy maps
# ---------------------------------------------------------------------------

def night_animal_hists(win: pd.DataFrame, extent, *, bin_in: float = 8.0,
                       moving_thr_inps: float | None = None) -> dict:
    """
    Occupancy histograms per ``(night, shortid)`` on a shared ``extent``/``bin_in``
    (bin ≥ jitter floor). Returns ``{(night, shortid): {"all": H, "moving": Hm,
    "n": n_fixes, "n_moving": m}}``. ``moving`` uses ``speed_inps_smooth`` when
    present and a threshold is given (path-density proxy).
    """
    out: dict = {}
    have_speed = moving_thr_inps is not None and "speed_inps_smooth" in win.columns
    for (night, tag), g in win.groupby(["night", "shortid"]):
        H, _, _ = w.occupancy_hist(g, extent, bin_in=bin_in)
        rec = {"all": H, "n": int(len(g))}
        if have_speed:
            gm = g[g["speed_inps_smooth"] > moving_thr_inps]
            Hm, _, _ = w.occupancy_hist(gm, extent, bin_in=bin_in)
            rec["moving"] = Hm
            rec["n_moving"] = int(len(gm))
        else:
            rec["moving"] = H
            rec["n_moving"] = int(len(g))
        out[(night, str(tag))] = rec
    return out


def sum_hists(hists: list[np.ndarray]) -> np.ndarray:
    """Elementwise sum of a list of same-shaped histograms (0 if empty)."""
    hists = [h for h in hists if h is not None]
    if not hists:
        return None
    acc = np.zeros_like(hists[0], dtype=float)
    for h in hists:
        acc += h
    return acc


# ---------------------------------------------------------------------------
# 4. Map similarity + spatial-use scalars
# ---------------------------------------------------------------------------

def map_cosine(A: np.ndarray, B: np.ndarray, *, blur_passes: int = 1) -> float:
    """Cosine similarity of two (optionally box-blurred) occupancy maps."""
    if A is None or B is None:
        return np.nan
    a = w._box_blur(A, passes=blur_passes).ravel().astype(float)
    b = w._box_blur(B, passes=blur_passes).ravel().astype(float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na > 0 and nb > 0 else np.nan


def map_corr(A: np.ndarray, B: np.ndarray, *, blur_passes: int = 1) -> float:
    """Pearson correlation of two flattened (optionally blurred) maps."""
    if A is None or B is None:
        return np.nan
    a = w._box_blur(A, passes=blur_passes).ravel().astype(float)
    b = w._box_blur(B, passes=blur_passes).ravel().astype(float)
    if a.std() <= 0 or b.std() <= 0:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def occ_entropy(H: np.ndarray) -> float:
    """Normalized Shannon entropy of an occupancy map (0 concentrated .. 1 uniform)."""
    if H is None:
        return np.nan
    c = H[H > 0].astype(float)
    if c.sum() <= 0 or len(c) <= 1:
        return 0.0
    p = c / c.sum()
    return float(-(p * np.log(p)).sum() / np.log(len(c)))


def occupied_area_cells(H: np.ndarray) -> int:
    """Number of occupied cells (a coarse coverage-area proxy)."""
    if H is None:
        return 0
    return int((H > 0).sum())


# ---------------------------------------------------------------------------
# 5. Stabilization curve (per animal, day-to-day)
# ---------------------------------------------------------------------------

def stabilization_table(hists: dict, animals: list[str], nights: list[str], *,
                        which: str = "all", ref_k: int = 2,
                        blur_passes: int = 1) -> pd.DataFrame:
    """
    Per animal × night stabilization metrics on the ``which`` map ("all" or
    "moving"):

    - ``cos_prev`` / ``corr_prev`` — similarity to that animal's *previous*
      populated night (day-to-day reproducibility rising ⇒ stabilizing);
    - ``cos_ref`` / ``corr_ref`` — similarity to a **late-window reference** (mean
      of the animal's last ``ref_k`` populated nights); the reference nights get
      ``cos_ref`` vs the reference itself (≈ upper bound);
    - ``entropy`` and ``area_cells`` per night (spatial-use spread over days).

    ``nights`` must be in chronological order.
    """
    rows = []
    for tag in animals:
        seq = [(n, hists[(n, tag)][which]) for n in nights if (n, tag) in hists]
        if not seq:
            continue
        ref_maps = [H for _, H in seq[-ref_k:]]
        ref = sum_hists(ref_maps)
        for i, (night, H) in enumerate(seq):
            prev_H = seq[i - 1][1] if i > 0 else None
            rows.append({
                "shortid": tag, "night": night, "which": which,
                "n_cells": occupied_area_cells(H),
                "entropy": occ_entropy(H),
                "area_cells": occupied_area_cells(H),
                "cos_prev": map_cosine(H, prev_H, blur_passes=blur_passes),
                "corr_prev": map_corr(H, prev_H, blur_passes=blur_passes),
                "cos_ref": map_cosine(H, ref, blur_passes=blur_passes),
                "corr_ref": map_corr(H, ref, blur_passes=blur_passes),
            })
    return pd.DataFrame(rows)


def stabilization_date(stab: pd.DataFrame, *, metric: str = "cos_ref",
                       plateau_frac: float = 0.9) -> dict:
    """
    Estimate a per-animal stabilization night: the first night whose ``metric``
    (similarity to the late reference) reaches ``plateau_frac`` of that animal's
    own maximum. Returns ``{shortid: night_or_None}``. Descriptive only.
    """
    out: dict = {}
    for tag, g in stab.groupby("shortid"):
        g = g.sort_values("night")
        vals = g[metric].to_numpy()
        nights = g["night"].to_numpy()
        finite = np.isfinite(vals)
        if not finite.any():
            out[tag] = None
            continue
        thr = plateau_frac * np.nanmax(vals)
        hit = np.where(finite & (vals >= thr))[0]
        out[tag] = str(nights[hit[0]]) if hit.size else None
    return out


# ---------------------------------------------------------------------------
# 6. Pooled shared-corridor map + residual individual maps
# ---------------------------------------------------------------------------

def pooled_corridor(all_hists: list[np.ndarray], *, pct: float = 80.0):
    """
    Pooled occupancy over all animals×nights → the paddock "road" map. Returns
    ``(pooled_H, mask, skeleton)`` (mask/skeleton via ``w.corridor_mask`` /
    ``w.skeletonize_mask``). This is the shared environmental-corridor reference.
    """
    pooled = sum_hists(all_hists)
    if pooled is None:
        return None, None, None
    mask, _ = w.corridor_mask(pooled, pct=pct)
    skel = w.skeletonize_mask(mask)
    return pooled, mask, skel


def residual_occupancy(animal_H: np.ndarray, pooled_H: np.ndarray, *,
                       blur_passes: int = 1, eps: float = 1e-9) -> np.ndarray:
    """
    Remove the shared road from an animal's map: return the animal's occupancy
    **divided by the pooled density** (both blurred, each L1-normalized first), so
    a cell where the animal is over-represented *relative to the group's* use of
    that cell stays high, while pure shared-road cells wash out to ~1. Cells the
    group never uses are 0.
    """
    if animal_H is None or pooled_H is None:
        return None
    a = w._box_blur(animal_H, passes=blur_passes).astype(float)
    p = w._box_blur(pooled_H, passes=blur_passes).astype(float)
    a = a / a.sum() if a.sum() > 0 else a
    p = p / p.sum() if p.sum() > 0 else p
    res = np.where(p > eps, a / (p + eps), 0.0)
    return res


def residual_concentration(res: np.ndarray, *, top_frac: float = 0.05) -> float:
    """
    How concentrated is the residual map? Fraction of total residual mass held by
    the top ``top_frac`` of non-zero cells. ~``top_frac`` ⇒ flat (no individual
    preference beyond the road); ≫``top_frac`` ⇒ the animal favours specific
    off-road cells (individual-preference evidence).
    """
    if res is None:
        return np.nan
    v = res[res > 0].astype(float)
    if v.size == 0 or v.sum() <= 0:
        return np.nan
    k = max(1, int(np.ceil(top_frac * v.size)))
    top = np.sort(v)[::-1][:k]
    return float(top.sum() / v.sum())


# ---------------------------------------------------------------------------
# 7. Inter-animal similarity + control battery
# ---------------------------------------------------------------------------

def pairwise_map_similarity(hist_by_animal: dict, *, blur_passes: int = 1,
                            label: str = "raw") -> pd.DataFrame:
    """Pairwise occupancy cosine/corr between animals' pooled maps. ``label`` tags
    the rows (e.g. "raw" or "residual")."""
    tags = sorted(hist_by_animal)
    rows = []
    import itertools
    for a, b in itertools.combinations(tags, 2):
        rows.append({"tag_a": a, "tag_b": b, "kind": label,
                     "cosine": map_cosine(hist_by_animal[a], hist_by_animal[b],
                                          blur_passes=blur_passes),
                     "corr": map_corr(hist_by_animal[a], hist_by_animal[b],
                                      blur_passes=blur_passes)})
    return pd.DataFrame(rows)


def label_permutation_null(night_hists: dict, animals: list[str], nights: list[str], *,
                           which: str = "all", n_perm: int = 200, seed: int = 0,
                           blur_passes: int = 1) -> pd.DataFrame:
    """
    Animal-label permutation null for pairwise map similarity. Each animal's map
    is the sum of its per-night maps; the null shuffles which *(night-map)* belongs
    to which animal (preserving the pool of night-maps and per-animal night counts)
    and recomputes the mean pairwise cosine. Returns one row per permutation stat
    per pair plus the observed value → z / percentile.
    """
    rng = np.random.default_rng(seed)
    # per-animal observed pooled map + list of that animal's night maps
    per_animal_nightmaps = {t: [night_hists[(n, t)][which] for n in nights
                                if (n, t) in night_hists] for t in animals}
    per_animal_nightmaps = {t: v for t, v in per_animal_nightmaps.items() if v}
    tags = sorted(per_animal_nightmaps)
    counts = {t: len(per_animal_nightmaps[t]) for t in tags}
    pool = [H for t in tags for H in per_animal_nightmaps[t]]
    observed = {t: sum_hists(per_animal_nightmaps[t]) for t in tags}

    import itertools
    pairs = list(itertools.combinations(tags, 2))
    obs_cos = {(a, b): map_cosine(observed[a], observed[b], blur_passes=blur_passes)
               for a, b in pairs}

    null = {p: [] for p in pairs}
    for _ in range(n_perm):
        order = rng.permutation(len(pool))
        shuffled = [pool[i] for i in order]
        assigned, k = {}, 0
        for t in tags:
            assigned[t] = sum_hists(shuffled[k:k + counts[t]])
            k += counts[t]
        for a, b in pairs:
            null[(a, b)].append(
                map_cosine(assigned[a], assigned[b], blur_passes=blur_passes))

    rows = []
    for a, b in pairs:
        arr = np.array(null[(a, b)], dtype=float)
        arr = arr[np.isfinite(arr)]
        mu, sd = (float(arr.mean()), float(arr.std())) if arr.size else (np.nan, np.nan)
        obs = obs_cos[(a, b)]
        z = (obs - mu) / sd if sd and np.isfinite(sd) and sd > 0 else np.nan
        pctile = float((arr < obs).mean()) if arr.size else np.nan
        rows.append({"tag_a": a, "tag_b": b, "control": "label_permutation",
                     "observed_cosine": obs, "null_mean": mu, "null_sd": sd,
                     "z": z, "percentile": pctile, "n_perm": int(arr.size)})
    return pd.DataFrame(rows)


# ---- time-resolved coupling (synchronous positions) -----------------------

def sync_grid(win: pd.DataFrame, *, bin_s: float = 2.0) -> pd.DataFrame:
    """
    Synchronous per-tag position grid for time-coupling, built per night so bins
    never bridge a night gap. Reuses ``w.resample_common_grid`` semantics but keys
    the time bin by absolute ``elapsed_s`` so different animals share bins. Adds a
    ``night`` column. Assumes ``win`` already has ``elapsed_s`` and ``night``.
    """
    d = win.dropna(subset=["x", "y", "elapsed_s"]).copy()
    d["tbin"] = np.floor(d["elapsed_s"] / bin_s).astype("int64")
    grid = (d.groupby(["night", "shortid", "tbin"])
              .agg(x=("x", "median"), y=("y", "median"),
                   clock_hour=("clock_hour", "first"))
              .reset_index())
    return grid


def _pair_series(grid: pd.DataFrame, a: str, b: str):
    """Aligned (same tbin) position arrays for two tags across all nights."""
    ga = grid[grid["shortid"].astype(str) == str(a)][["tbin", "x", "y", "clock_hour"]]
    gb = grid[grid["shortid"].astype(str) == str(b)][["tbin", "x", "y"]]
    m = ga.merge(gb, on="tbin", suffixes=("_a", "_b"))
    return m


def pair_time_coupling(m: pd.DataFrame, *, within_r_in: float = 39.37) -> dict:
    """
    Time-coupling scalars for one aligned pair table (from :func:`_pair_series`):

    - ``xy_corr`` — mean of Pearson corr(x_a,x_b) and corr(y_a,y_b) (co-movement);
    - ``mean_dist_in`` — mean synchronous separation;
    - ``frac_within_r`` — fraction of synchronous bins closer than ``within_r_in``
      (default 1 m = 39.37 in, the jitter-floor-safe proximity radius);
    - ``n_bins`` — number of synchronous bins.

    Returns NaNs if too few synchronous bins.
    """
    if len(m) < 10:
        return {"xy_corr": np.nan, "mean_dist_in": np.nan,
                "frac_within_r": np.nan, "n_bins": int(len(m))}
    xa, ya = m["x_a"].to_numpy(), m["y_a"].to_numpy()
    xb, yb = m["x_b"].to_numpy(), m["y_b"].to_numpy()
    cx = np.corrcoef(xa, xb)[0, 1] if xa.std() > 0 and xb.std() > 0 else np.nan
    cy = np.corrcoef(ya, yb)[0, 1] if ya.std() > 0 and yb.std() > 0 else np.nan
    dist = np.hypot(xa - xb, ya - yb)
    return {"xy_corr": float(np.nanmean([cx, cy])),
            "mean_dist_in": float(dist.mean()),
            "frac_within_r": float((dist < within_r_in).mean()),
            "n_bins": int(len(m))}


def circular_shift_null(grid: pd.DataFrame, a: str, b: str, *, n_shuffles: int = 100,
                        min_shift: int = 30, seed: int = 0,
                        within_r_in: float = 39.37) -> dict:
    """
    Time-shuffle (within-animal) null: circularly roll tag ``b``'s time series by a
    random offset (≥ ``min_shift`` bins) and recompute coupling ``n_shuffles``
    times. Real-time coupling should exceed this null; a shared diurnal rhythm or
    shared road (which survives a time shift) should not. Returns observed +
    null summary + z for ``xy_corr`` and ``frac_within_r``.
    """
    rng = np.random.default_rng(seed)
    m = _pair_series(grid, a, b)
    obs = pair_time_coupling(m, within_r_in=within_r_in)
    ga = grid[grid["shortid"].astype(str) == str(a)][["tbin", "x", "y"]].copy()
    gb = grid[grid["shortid"].astype(str) == str(b)][["tbin", "x", "y"]].copy()
    gb = gb.sort_values("tbin").reset_index(drop=True)
    nb = len(gb)
    null_corr, null_prox = [], []
    if nb >= 2 * min_shift and len(m) >= 10:
        for _ in range(n_shuffles):
            k = int(rng.integers(min_shift, nb - min_shift))
            rolled = gb.copy()
            rolled[["x", "y"]] = np.roll(gb[["x", "y"]].to_numpy(), k, axis=0)
            mm = ga.merge(rolled, on="tbin", suffixes=("_a", "_b"))
            c = pair_time_coupling(mm, within_r_in=within_r_in)
            null_corr.append(c["xy_corr"])
            null_prox.append(c["frac_within_r"])
    return _null_pack(a, b, "circular_shift", obs, null_corr, null_prox)


def dayshuffle_null(grid: pd.DataFrame, a: str, b: str, *, seed: int = 0,
                    within_r_in: float = 39.37) -> dict:
    """
    Day-shuffle null: pair tag ``a``'s night with tag ``b``'s **other** nights
    (all mismatched night pairings), breaking real-time synchrony while preserving
    each animal's own spatial/diurnal habits. If observed coupling is real-time it
    exceeds this null; if it is just shared space/rhythm it does not. Uses the
    per-night ``tbin`` offset within each night so mismatched nights still align by
    within-night position.
    """
    # index tbin within each night (position in the night), so nights can be compared.
    # Use groupby.cumcount (not .apply) — robust across pandas versions.
    ga = grid[grid["shortid"].astype(str) == str(a)].sort_values(["night", "tbin"]).copy()
    gb = grid[grid["shortid"].astype(str) == str(b)].sort_values(["night", "tbin"]).copy()
    ga["k"] = ga.groupby("night").cumcount()
    gb["k"] = gb.groupby("night").cumcount()
    nights_a = sorted(ga["night"].unique())
    nights_b = sorted(gb["night"].unique())
    # observed: same night
    obs_corr, obs_prox = [], []
    null_corr, null_prox = [], []
    for na in nights_a:
        sa = ga[ga["night"] == na][["k", "x", "y"]]
        for nb_ in nights_b:
            sb = gb[gb["night"] == nb_][["k", "x", "y"]]
            mm = sa.merge(sb, on="k", suffixes=("_a", "_b"))
            c = pair_time_coupling(mm, within_r_in=within_r_in)
            if not np.isfinite(c["xy_corr"]):
                continue
            if na == nb_:
                obs_corr.append(c["xy_corr"]); obs_prox.append(c["frac_within_r"])
            else:
                null_corr.append(c["xy_corr"]); null_prox.append(c["frac_within_r"])
    obs = {"xy_corr": float(np.nanmean(obs_corr)) if obs_corr else np.nan,
           "frac_within_r": float(np.nanmean(obs_prox)) if obs_prox else np.nan,
           "mean_dist_in": np.nan, "n_bins": len(obs_corr)}
    return _null_pack(a, b, "day_shuffle", obs, null_corr, null_prox)


def _null_pack(a, b, control, obs, null_corr, null_prox) -> dict:
    """Package observed + null (corr & proximity) into a flat record with z-scores."""
    def _stat(obs_v, arr):
        arr = np.array([v for v in arr if np.isfinite(v)], dtype=float)
        if arr.size == 0 or not np.isfinite(obs_v):
            return np.nan, np.nan, np.nan, 0
        mu, sd = float(arr.mean()), float(arr.std())
        z = (obs_v - mu) / sd if sd > 0 else np.nan
        pctile = float((arr < obs_v).mean())
        return mu, sd, z, arr.size
    cmu, csd, cz, cn = _stat(obs["xy_corr"], null_corr)
    pmu, psd, pz, pn = _stat(obs["frac_within_r"], null_prox)
    return {"tag_a": a, "tag_b": b, "control": control,
            "obs_xy_corr": obs["xy_corr"], "null_xy_corr_mean": cmu,
            "null_xy_corr_sd": csd, "z_xy_corr": cz,
            "obs_frac_within_r": obs["frac_within_r"], "null_prox_mean": pmu,
            "null_prox_sd": psd, "z_frac_within_r": pz, "n_null": max(cn, pn)}


# ===========================================================================
# PHASE B — directional following + stable-pairs-vs-herd structure
# ===========================================================================
#
# The question: is co-movement carried by SPECIFIC, STABLE pairs (social dyads) or
# spread across everyone (shared road / herd)? Built entirely on w's validated
# `following_*` suite (lag-aware, heading-aware, jitter-scaled R = 3x floor, with a
# circular-shift null) so no new following math is introduced — this layer only
# aggregates per-pair follow scores into specificity / stability / leadership.


def per_night_following(win: pd.DataFrame, nights: list[str], *,
                        jitter_floor_in: float, grid_moving_thr_inps: float,
                        lags=range(1, 31), cos_thresh: float = 0.5,
                        n_shuffles: int = 100, bin_s: float = 1.0,
                        smooth_s: float = 5.0, min_r_in: float = 24.0,
                        seed: int = 0) -> tuple[pd.DataFrame, float]:
    """
    Run w's following suite **per night** and stack the results.

    For each night: ``build_following_grid`` → ``follow_scores_all`` (lag sweep) →
    ``following_peaks`` (peak score + best lag per ordered pair) → ``following_null``
    (circular-shift z). Returns ``(long_df, R)`` where ``long_df`` has one row per
    ``(night, leader, follower)`` with ``peak_score, best_lag_s, n_valid,
    shuffled_mean, shuffled_p95, shuffled_sd, z_score``. ``R`` = the follow radius
    used (max(3×jitter, min_r_in), inches) — recorded for provenance.
    """
    R = w.follow_radius_in(jitter_floor_in, min_r_in=min_r_in)
    lags = list(lags)
    frames = []
    for night in nights:
        g = win[win["night"] == night]
        if g["shortid"].nunique() < 2:
            continue
        grid = w.build_following_grid(g, bin_s=bin_s, smooth_s=smooth_s,
                                      moving_thr_inps=grid_moving_thr_inps)
        if len(grid["tags"]) < 2:
            continue
        scores = w.follow_scores_all(grid, lags=lags, R=R, cos_thresh=cos_thresh)
        peaks = w.following_peaks(scores)
        null = w.following_null(grid, peaks, lags=lags, R=R, cos_thresh=cos_thresh,
                                n_shuffles=n_shuffles, seed=seed)
        m = peaks.merge(null, on=["leader", "follower"], how="left")
        m["leader"] = m["leader"].astype(str)
        m["follower"] = m["follower"].astype(str)
        m["night"] = night
        frames.append(m)
    if not frames:
        return pd.DataFrame(), R
    return pd.concat(frames, ignore_index=True), R


def undirected_pair_scores(foll: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse ordered follow pairs to an **undirected** per-(night, pair) record:
    the best-direction ``peak_score`` (and its z, best lag, and which animal is the
    leader in that direction). One row per unordered pair per night.
    """
    if foll.empty:
        return pd.DataFrame()
    rows = []
    tmp = foll.copy()
    tmp["pair"] = [tuple(sorted((a, b))) for a, b in zip(tmp["leader"], tmp["follower"])]
    for (night, pair), g in tmp.groupby(["night", "pair"]):
        i = g["peak_score"].astype(float).idxmax()
        best = g.loc[i]
        rows.append({
            "night": night, "pair": f"{pair[0]}-{pair[1]}", "a": pair[0], "b": pair[1],
            "score": float(best["peak_score"]) if pd.notna(best["peak_score"]) else np.nan,
            "z": float(g["z_score"].max()) if g["z_score"].notna().any() else np.nan,
            "leader": str(best["leader"]), "follower": str(best["follower"]),
            "best_lag_s": float(best["best_lag_s"]) if pd.notna(best["best_lag_s"]) else np.nan,
        })
    return pd.DataFrame(rows)


def _gini(x: np.ndarray) -> float:
    """Gini coefficient of non-negative values (0 = all equal, →1 = concentrated)."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return np.nan
    x = np.sort(np.clip(x, 0, None))
    if x.sum() <= 0:
        return np.nan
    n = x.size
    cum = np.cumsum(x)
    return float((n + 1 - 2 * cum.sum() / cum[-1]) / n)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman rank correlation (no scipy): Pearson on ranks."""
    a = pd.Series(a); b = pd.Series(b)
    if a.notna().sum() < 3 or a.std(skipna=True) == 0 or b.std(skipna=True) == 0:
        return np.nan
    ra, rb = a.rank(), b.rank()
    return float(np.corrcoef(ra, rb)[0, 1])


def specificity_summary(undirected: pd.DataFrame, *, z_thresh: float = 2.0) -> pd.DataFrame:
    """
    Per night, is co-movement CONCENTRATED (dyads) or SPREAD (herd)?

    - ``n_sig_pairs`` / ``frac_sig`` — pairs beating their circular-shift null
      (``z > z_thresh``);
    - ``score_gini`` — concentration of undirected follow scores across pairs
      (high ⇒ a few dominant pairs ⇒ candidate dyads; low ⇒ flat ⇒ herd/road);
    - ``top_pair`` / ``top_score`` / ``top_z`` — the strongest pair that night.
    """
    rows = []
    for night, g in undirected.groupby("night"):
        s = g["score"].to_numpy(float)
        z = g["z"].to_numpy(float)
        n = len(g)
        n_sig = int(np.nansum(z > z_thresh))
        top = g.loc[g["score"].astype(float).idxmax()] if g["score"].notna().any() else None
        rows.append({
            "night": night, "n_pairs": n, "n_sig_pairs": n_sig,
            "frac_sig": round(n_sig / n, 4) if n else np.nan,
            "score_gini": round(_gini(s), 4),
            "score_mean": float(np.nanmean(s)) if np.isfinite(s).any() else np.nan,
            "score_max": float(np.nanmax(s)) if np.isfinite(s).any() else np.nan,
            "top_pair": (top["pair"] if top is not None else None),
            "top_z": (float(top["z"]) if top is not None and pd.notna(top["z"]) else np.nan),
        })
    return pd.DataFrame(rows)


def stability_summary(undirected: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Is it the SAME subset of pairs across nights? Returns ``(pair_summary, meta)``:

    - ``pair_summary`` — per unordered pair: mean/median score, n nights present,
      n nights significant (z>2), and how often the pair is that night's top pair;
    - ``meta`` — the pair×night score matrix (as a dict), and the mean
      **consecutive-night Spearman** rank correlation of the pair-score vector
      (high ⇒ stable structure; ~0 ⇒ the "preferred" pair reshuffles nightly).
    """
    if undirected.empty:
        return pd.DataFrame(), {"consecutive_spearman": np.nan, "pair_night_matrix": {}}
    piv = undirected.pivot_table(index="pair", columns="night", values="score")
    nights = list(piv.columns)
    corrs = []
    for i in range(1, len(nights)):
        c = _spearman(piv[nights[i - 1]].to_numpy(), piv[nights[i]].to_numpy())
        if np.isfinite(c):
            corrs.append(c)
    top_by_night = (undirected.loc[undirected.groupby("night")["score"].idxmax()]
                    if undirected["score"].notna().any() else pd.DataFrame())
    top_counts = top_by_night["pair"].value_counts().to_dict() if not top_by_night.empty else {}
    rows = []
    for pair, g in undirected.groupby("pair"):
        rows.append({
            "pair": pair, "n_nights": int(g["score"].notna().sum()),
            "mean_score": float(g["score"].mean()), "median_score": float(g["score"].median()),
            "max_z": float(g["z"].max()) if g["z"].notna().any() else np.nan,
            "n_nights_sig": int(np.nansum(g["z"].to_numpy(float) > 2.0)),
            "n_nights_top": int(top_counts.get(pair, 0)),
        })
    pair_summary = pd.DataFrame(rows).sort_values("mean_score", ascending=False)
    meta = {"consecutive_spearman": float(np.mean(corrs)) if corrs else np.nan,
            "n_night_pairs_compared": len(corrs),
            "pair_night_matrix": piv.round(4).to_dict()}
    return pair_summary, meta


def leadership_consistency(undirected: pd.DataFrame) -> pd.DataFrame:
    """
    For each unordered pair, does the SAME animal lead across nights? Returns per
    pair: ``dominant_leader``, ``leader_consistency`` (fraction of present nights
    that animal led), and ``n_nights``. Consistency ≈1 ⇒ a stable leader
    (dominance-like); ≈0.5 ⇒ mutual / alternating.
    """
    rows = []
    for pair, g in undirected.groupby("pair"):
        g = g.dropna(subset=["score"])
        if g.empty:
            continue
        vc = g["leader"].value_counts()
        rows.append({"pair": pair, "n_nights": int(len(g)),
                     "dominant_leader": str(vc.index[0]),
                     "leader_consistency": round(float(vc.iloc[0] / len(g)), 4),
                     "mean_best_lag_s": round(float(g["best_lag_s"].mean()), 2)})
    return pd.DataFrame(rows).sort_values("leader_consistency", ascending=False)


def per_night_leadership(undirected: pd.DataFrame) -> pd.DataFrame:
    """
    **Per-night** (not averaged) leadership: for each ``(night, animal)``, how many
    of that animal's pairs it led that night (leader = the higher-scoring direction),
    the fraction, and its mean follow score when present. Lets you see whether a
    leader (e.g. Sen) is on top *every* night or only on average, and whether the
    hub changes night to night. One row per animal per night.
    """
    if undirected.empty:
        return pd.DataFrame()
    rows = []
    for night, g in undirected.groupby("night"):
        animals = sorted(set(g["a"].astype(str)) | set(g["b"].astype(str)))
        for an in animals:
            inp = g[(g["a"].astype(str) == an) | (g["b"].astype(str) == an)]
            n = len(inp)
            led = int((inp["leader"].astype(str) == an).sum())
            rows.append({"night": night, "animal": an, "n_pairs": n, "n_led": led,
                         "lead_frac": round(led / n, 3) if n else np.nan,
                         "mean_score": round(float(inp["score"].mean()), 4) if n else np.nan,
                         "n_sig_led": int(((inp["leader"].astype(str) == an) &
                                           (inp["z"].astype(float) > 2)).sum())})
    return pd.DataFrame(rows)


def group_cohesion(win: pd.DataFrame, nights: list[str], *, bin_s: float = 2.0) -> pd.DataFrame:
    """
    Per-night whole-group cohesion (the herd control): mean/median synchronous
    pairwise distance and the fraction of synchronous bins where the *median*
    pairwise distance is under 1 m (a rough "clumped as a group" fraction). If the
    group travels as a herd, pairwise follow scores ride on this — so it is reported
    alongside the specificity result. Uses ``w.resample_common_grid`` /
    ``w.pairwise_distances`` / ``w.clustering_index``.
    """
    rows = []
    for night in nights:
        g = win[win["night"] == night]
        grid = w.resample_common_grid(g, bin_s=bin_s)
        dl = w.pairwise_distances(grid)
        if dl.empty:
            rows.append({"night": night, "mean_pair_dist_in": np.nan,
                         "median_pair_dist_in": np.nan, "frac_clumped_bins": np.nan})
            continue
        ci = w.clustering_index(dl)
        clumped = float((ci["mean_pair_dist_in"] < 39.37).mean()) if not ci.empty else np.nan
        rows.append({"night": night,
                     "mean_pair_dist_in": round(float(dl["dist_in"].mean()), 1),
                     "median_pair_dist_in": round(float(dl["dist_in"].median()), 1),
                     "frac_clumped_bins": round(clumped, 4)})
    return pd.DataFrame(rows)


# ===========================================================================
# PHASE B (motifs) — stereotypical route patterns
# ===========================================================================
#
# Confirm (or refute) STEREOTYPED MOVEMENT: do animals re-run the same path
# SHAPES (route motifs), is that reuse INDIVIDUAL (an animal repeats its own
# routes across days) or SHARED (everyone on the common road), and does it
# STRENGTHEN over days? Route-scale question (paths span feet-metres, >> the ~7 in
# jitter floor), so within resolution. Motifs are LOCATION-ANCHORED (absolute inch
# frame). Path distance is numpy-only (no scipy): mean/max pointwise on
# arc-length-resampled paths (primary) + Hausdorff / DTW (robustness).


def _arc_resample(x: np.ndarray, y: np.ndarray, n: int) -> np.ndarray:
    """Resample a path to ``n`` points equally spaced by ARC LENGTH -> (n, 2).
    Arc-length (not time) resampling makes the comparison speed-invariant."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    seg = np.hypot(np.diff(x), np.diff(y))
    s = np.concatenate([[0.0], np.cumsum(seg)])
    if s[-1] <= 0 or len(x) < 2:
        return np.column_stack([np.full(n, x[0]), np.full(n, y[0])])
    u = np.linspace(0.0, s[-1], n)
    return np.column_stack([np.interp(u, s, x), np.interp(u, s, y)])


def extract_route_bouts(win: pd.DataFrame, nights: list, *,
                        moving_thr_inps: float, min_disp_in: float = 15.0,
                        resample_n: int = 20, max_per_night: int | None = 40,
                        min_bout_s: float = 3.0, max_gap_s: float = 2.0,
                        smooth_window: int = w.DEFAULT_SMOOTH_WINDOW,
                        roi_cfg: dict = None):
    """
    Movement bouts per (night, animal) with their **arc-length-resampled path**
    (jitter-suppressed absolute coords). A bout = a contiguous moving run
    (speed > moving_thr_inps, gaps <= max_gap_s, >= min_bout_s) with net
    displacement >= min_disp_in (a real route, not jitter). When
    ``max_per_night`` is not None, bouts are capped per (night, animal) by
    displacement (logged, never silent). ``None`` retains every detected bout.

    Returns (bouts_df, paths, log); paths is (N, resample_n, 2) aligned to rows.
    Optional roi_cfg labels each bout's start/end ROI (provisional, inch frame).
    """
    recs, paths = [], []
    n_total, n_capped = 0, 0
    for night in nights:
        gn = win[win["night"] == night]
        for tag, g0 in gn.groupby("shortid"):
            g = w.add_speed(g0.sort_values("datetime"),
                            smooth_window=smooth_window).reset_index(drop=True)
            xs = g["x"].rolling(smooth_window, center=True, min_periods=1).median().to_numpy()
            ys = g["y"].rolling(smooth_window, center=True, min_periods=1).median().to_numpy()
            sp = g["speed_inps_smooth"].to_numpy()
            dt = g["dt_s"].to_numpy()
            t = (g["datetime"] - g["datetime"].iloc[0]).dt.total_seconds().to_numpy()
            moving = np.isfinite(sp) & (sp > moving_thr_inps)
            bl, i, n = [], 0, len(g)
            while i < n:
                if not moving[i]:
                    i += 1; continue
                j = i + 1
                while j < n and moving[j] and np.isfinite(dt[j]) and dt[j] <= max_gap_s:
                    j += 1
                if (t[j - 1] - t[i]) >= min_bout_s and (j - i) >= 2:
                    disp = float(np.hypot(xs[j - 1] - xs[i], ys[j - 1] - ys[i]))
                    if disp >= min_disp_in:
                        plen = float(np.nansum(np.hypot(np.diff(xs[i:j]), np.diff(ys[i:j]))))
                        bl.append((i, j - 1, disp, plen, float(t[i])))
                i = j
            n_total += len(bl)
            bl.sort(key=lambda b: -b[2])
            if max_per_night is not None and len(bl) > max_per_night:
                n_capped += len(bl) - max_per_night
                bl = bl[:max_per_night]
            for (i0, i1, disp, plen, ts) in bl:
                p = _arc_resample(xs[i0:i1 + 1], ys[i0:i1 + 1], resample_n)
                start_dt = pd.Timestamp(g.loc[i0, "datetime"])
                end_dt = pd.Timestamp(g.loc[i1, "datetime"])
                if start_dt.tzinfo is None:
                    start_dt = start_dt.tz_localize("UTC")
                    end_dt = end_dt.tz_localize("UTC")
                else:
                    start_dt = start_dt.tz_convert("UTC")
                    end_dt = end_dt.tz_convert("UTC")
                rec = {"night": night, "shortid": str(tag), "disp_in": round(disp, 1),
                       "path_in": round(plen, 1), "t_start_s": ts,
                       "t_start_ms": int(start_dt.value // 1_000_000),
                       "t_end_ms": int(end_dt.value // 1_000_000),
                       "duration_s": round((end_dt - start_dt).total_seconds(), 3),
                       "x0": float(p[0, 0]), "y0": float(p[0, 1]),
                       "x1": float(p[-1, 0]), "y1": float(p[-1, 1])}
                if roi_cfg is not None:
                    ends = w.assign_roi(pd.DataFrame({"x": [p[0, 0], p[-1, 0]],
                                                      "y": [p[0, 1], p[-1, 1]]}), roi_cfg)
                    rec["start_roi"], rec["end_roi"] = ends["roi"].iloc[0], ends["roi"].iloc[1]
                recs.append(rec)
                paths.append(p)
    arr = np.array(paths) if paths else np.zeros((0, resample_n, 2))
    log = {"n_bouts_kept": len(recs), "n_bouts_dropped_by_cap": int(n_capped),
           "n_bouts_total_predisp_cap": int(n_total), "max_per_night": max_per_night,
           "min_disp_in": min_disp_in, "resample_n": resample_n}
    return pd.DataFrame(recs), arr, log


def extract_pause_merged_episodes(win: pd.DataFrame, nights: list, *,
                                  moving_thr_inps: float, pause_merge_s: float = 5.0,
                                  min_bout_s: float = 3.0, min_disp_in: float = 15.0, resample_n: int = 20,
                                  max_per_night: int | None = 40, max_gap_s: float = 2.0,
                                  smooth_window: int = w.DEFAULT_SMOOTH_WINDOW, roi_cfg: dict = None):
    """Pause-merged locomotor EPISODES: the SAME production-bout-scale moving runs as
    ``extract_route_bouts`` (duration >= ``min_bout_s``), **transitively chained across pauses shorter
    than ``pause_merge_s``** (with data continuity across the bridged pause), so an episode can span many
    brief stops. This is the repo-canonical "merged locomotor episode" (transitive pause-bridging of the
    3s bouts; ~99% of bouts fall inside one) — a purely MECHANICAL coarsening. NOT destination-validated
    "trips", and NOT decision-to-decision "legs" (WISER cannot validate decision boundaries — jitter
    dominates pause headings; see ``decision_boundary_validation/``). Each episode's path spans
    first-bout-start → last-bout-end (bridged pauses included), arc-length-resampled. Same schema +
    displacement filter + per-night cap as ``extract_route_bouts``; ``log`` carries ``pause_merge_s``."""
    recs, paths = [], []
    n_total, n_capped = 0, 0
    for night in nights:
        gn = win[win["night"] == night]
        for tag, g0 in gn.groupby("shortid"):
            g = w.add_speed(g0.sort_values("datetime"),
                            smooth_window=smooth_window).reset_index(drop=True)
            xs = g["x"].rolling(smooth_window, center=True, min_periods=1).median().to_numpy()
            ys = g["y"].rolling(smooth_window, center=True, min_periods=1).median().to_numpy()
            sp = g["speed_inps_smooth"].to_numpy()
            dt = g["dt_s"].to_numpy()
            t = (g["datetime"] - g["datetime"].iloc[0]).dt.total_seconds().to_numpy()
            moving = np.isfinite(sp) & (sp > moving_thr_inps)
            n = len(g)
            # (1) production-bout-scale moving runs (contiguous moving, gap <= max_gap_s, duration >=
            #     min_bout_s) — the SAME base units extract_route_bouts keeps, so episodes are a clean
            #     merge of the 3s bouts (isolating the pause-bridging effect), not a finer re-segmentation.
            runs, i = [], 0
            while i < n:
                if not moving[i]:
                    i += 1; continue
                j = i + 1
                while j < n and moving[j] and np.isfinite(dt[j]) and dt[j] <= max_gap_s:
                    j += 1
                if (t[j - 1] - t[i]) >= min_bout_s and (j - i) >= 2:
                    runs.append((i, j - 1))
                i = j
            if not runs:
                continue
            # (2) transitively chain runs where the inter-run pause < pause_merge_s AND the data is
            #     continuous across it (no single gap > max_gap_s — a real dropout is not a bridgeable pause)
            episodes = []
            cs, ce = runs[0]
            for (rs, re) in runs[1:]:
                pause = t[rs] - t[ce]
                gap_ok = bool(np.all(dt[ce + 1:rs + 1] <= max_gap_s)) if rs > ce else True
                if pause < pause_merge_s and gap_ok:
                    ce = re
                else:
                    episodes.append((cs, ce)); cs, ce = rs, re
            episodes.append((cs, ce))
            n_total += len(episodes)
            # (3) displacement filter + per-night cap by displacement, then build records
            kept = []
            for (i0, i1) in episodes:
                if (i1 - i0) < 1:
                    continue
                disp = float(np.hypot(xs[i1] - xs[i0], ys[i1] - ys[i0]))
                if disp < min_disp_in:
                    continue
                plen = float(np.nansum(np.hypot(np.diff(xs[i0:i1 + 1]), np.diff(ys[i0:i1 + 1]))))
                kept.append((i0, i1, disp, plen, float(t[i0])))
            kept.sort(key=lambda b: -b[2])
            if max_per_night is not None and len(kept) > max_per_night:
                n_capped += len(kept) - max_per_night
                kept = kept[:max_per_night]
            for (i0, i1, disp, plen, ts) in kept:
                p = _arc_resample(xs[i0:i1 + 1], ys[i0:i1 + 1], resample_n)
                start_dt = pd.Timestamp(g.loc[i0, "datetime"])
                end_dt = pd.Timestamp(g.loc[i1, "datetime"])
                if start_dt.tzinfo is None:
                    start_dt = start_dt.tz_localize("UTC"); end_dt = end_dt.tz_localize("UTC")
                else:
                    start_dt = start_dt.tz_convert("UTC"); end_dt = end_dt.tz_convert("UTC")
                rec = {"night": night, "shortid": str(tag), "disp_in": round(disp, 1),
                       "path_in": round(plen, 1), "t_start_s": ts,
                       "t_start_ms": int(start_dt.value // 1_000_000),
                       "t_end_ms": int(end_dt.value // 1_000_000),
                       "duration_s": round((end_dt - start_dt).total_seconds(), 3),
                       "x0": float(p[0, 0]), "y0": float(p[0, 1]),
                       "x1": float(p[-1, 0]), "y1": float(p[-1, 1])}
                if roi_cfg is not None:
                    ends = w.assign_roi(pd.DataFrame({"x": [p[0, 0], p[-1, 0]],
                                                      "y": [p[0, 1], p[-1, 1]]}), roi_cfg)
                    rec["start_roi"], rec["end_roi"] = ends["roi"].iloc[0], ends["roi"].iloc[1]
                recs.append(rec); paths.append(p)
    arr = np.array(paths) if paths else np.zeros((0, resample_n, 2))
    log = {"n_bouts_kept": len(recs), "n_bouts_dropped_by_cap": int(n_capped),
           "n_bouts_total_predisp_cap": int(n_total), "max_per_night": max_per_night,
           "min_disp_in": min_disp_in, "resample_n": resample_n, "pause_merge_s": pause_merge_s}
    return pd.DataFrame(recs), arr, log


def path_distance_matrix(paths: np.ndarray, *, metric: str = "mean") -> np.ndarray:
    """
    Pairwise LOCATION-ANCHORED path distance (inches), numpy-only. Paths are
    arc-length-resampled to the same length so point i corresponds across bouts.
    metric="mean" = mean pointwise distance; metric="frechet" = max pointwise
    (discrete-Frechet under fixed correspondence). O(N^2 L), row-vectorized.
    """
    N = len(paths)
    D = np.zeros((N, N), float)
    for i in range(N):
        diff = paths - paths[i]                      # (N, L, 2)
        pt = np.sqrt((diff ** 2).sum(2))             # (N, L)
        D[i] = pt.mean(1) if metric == "mean" else pt.max(1)
    return D


def hausdorff(a: np.ndarray, b: np.ndarray) -> float:
    """Symmetric Hausdorff distance between two point sets (numpy, order-free)."""
    dd = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(2))
    return float(max(dd.min(1).max(), dd.min(0).max()))


def dtw_distance(a: np.ndarray, b: np.ndarray) -> float:
    """DTW distance between two paths (numpy; speed-warp-tolerant robustness check)."""
    na, nb = len(a), len(b)
    D = np.full((na + 1, nb + 1), np.inf)
    D[0, 0] = 0.0
    cost = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(2))
    for i in range(1, na + 1):
        for j in range(1, nb + 1):
            D[i, j] = cost[i - 1, j - 1] + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])
    return float(D[na, nb] / (na + nb))


def cluster_paths(D: np.ndarray, *, threshold: float) -> np.ndarray:
    """
    Motif labels by single-linkage connected components at threshold (union-find,
    numpy). Bouts within threshold (inches) join the same motif. Labels 0..K-1
    ordered by motif size (0 = largest).
    """
    N = len(D)
    parent = list(range(N))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a

    iu, ju = np.where(np.triu(D < threshold, k=1))
    for a, b in zip(iu.tolist(), ju.tolist()):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    roots = np.array([find(i) for i in range(N)])
    uniq, counts = np.unique(roots, return_counts=True)
    order = uniq[np.argsort(-counts)]
    remap = {r: k for k, r in enumerate(order)}
    return np.array([remap[r] for r in roots])


def cluster_paths_leader(D: np.ndarray, *, threshold: float) -> np.ndarray:
    """
    COMPACT motif clustering that does NOT chain (unlike single-linkage): greedy
    "leader" clustering. Repeatedly take the still-unassigned bout with the most
    neighbours within ``threshold`` and make it a motif with all its unassigned
    neighbours. Every member is within ``threshold`` of the leader, so a motif is a
    tight bundle of near-identical routes, not a chained continuum. Labels 0..K-1
    ordered by size (0 = largest). O(N²).
    """
    N = len(D)
    within = D <= threshold
    np.fill_diagonal(within, True)
    order = np.argsort(-within.sum(1))
    labels = -np.ones(N, int)
    lab = 0
    for i in order:
        if labels[i] >= 0:
            continue
        members = np.where(within[i] & (labels < 0))[0]
        labels[members] = lab
        lab += 1
    uniq, cnts = np.unique(labels, return_counts=True)
    remap = {r: k for k, r in enumerate(uniq[np.argsort(-cnts)])}
    return np.array([remap[x] for x in labels])


def recurrence_fraction(D: np.ndarray, *, thresholds) -> tuple[dict, np.ndarray]:
    """
    Threshold-robust "are routes repeated?" measure: the nearest-neighbour route
    distance for each bout (to ANY other bout), and the fraction of bouts whose
    NN is within each threshold (a repeated route). Returns ``(fracs, nn)`` where
    ``fracs[t]`` = fraction recurrent at ``t`` inches and ``nn`` = per-bout NN dist.
    """
    Dw = D.copy()
    np.fill_diagonal(Dw, np.inf)
    nn = Dw.min(1)
    fracs = {float(t): float(np.mean(nn <= t)) for t in thresholds}
    return fracs, nn


def suggest_threshold(D: np.ndarray, *, pct: float = 10.0) -> float:
    """Data-driven motif threshold: the pct-th percentile of off-diagonal pairwise
    distances (bouts closer than most pairs = a recurring motif)."""
    iu = np.triu_indices(len(D), k=1)
    vals = D[iu]
    vals = vals[np.isfinite(vals)]
    return float(np.percentile(vals, pct)) if vals.size else np.nan


def _norm_entropy(counts: np.ndarray) -> float:
    """Normalised Shannon entropy of a count vector (0 concentrated .. 1 uniform)."""
    c = np.asarray(counts, float)
    c = c[c > 0]
    if c.sum() <= 0 or len(c) <= 1:
        return 0.0
    p = c / c.sum()
    return float(-(p * np.log(p)).sum() / np.log(len(c)))


def motif_stereotypy(bouts: pd.DataFrame, labels: np.ndarray) -> pd.DataFrame:
    """
    Per (animal, night) recurrence: n_bouts, n_motifs used, and motif_entropy over
    that animal-night's bouts (low = bouts collapse into few repeated motifs =
    stereotyped; high = every bout different). One row per (animal, night).
    """
    b = bouts.copy(); b["motif"] = labels
    rows = []
    for (tag, night), g in b.groupby(["shortid", "night"]):
        vc = g["motif"].value_counts().to_numpy()
        rows.append({"shortid": tag, "night": night, "n_bouts": int(len(g)),
                     "n_motifs": int((vc > 0).sum()),
                     "motif_entropy": round(_norm_entropy(vc), 4),
                     "top_motif_frac": round(float(vc.max() / vc.sum()), 4) if vc.sum() else np.nan})
    return pd.DataFrame(rows)


def bout_clock_hour(bouts: pd.DataFrame,
                    tz_offset_hours: int = w.LOCAL_TZ_OFFSET_HOURS) -> pd.Series:
    """Local (EDT) clock hour of each bout's START, from its UTC ``t_start_ms``.
    Floor via a Timedelta shift (never int64//ns) to avoid the pandas[ms] hazard."""
    loc = pd.to_datetime(bouts["t_start_ms"], unit="ms", utc=True).dt.tz_convert(None) \
        + pd.Timedelta(hours=tz_offset_hours)
    return loc.dt.hour.astype(int)


def motif_by_hour(bouts: pd.DataFrame, *, recur_thr_in: float,
                  tz_offset_hours: int = w.LOCAL_TZ_OFFSET_HOURS) -> pd.DataFrame:
    """PER LOCAL CLOCK-HOUR (pooled over nights) route-motif profile — 'when in the
    night are the stereotyped routes run'. Needs ``bouts`` with ``motif`` +
    ``nn_route_dist_in``. One row per clock hour present in the night window:
      n_bouts, n_animals, bouts_per_animal, n_motifs (distinct clusters used that
      hour), recurrence_frac (share of bouts whose nearest-route neighbour is
      <= recur_thr_in), median_disp_in.
    """
    b = bouts.copy()
    b["clock_hour"] = bout_clock_hour(b, tz_offset_hours)
    b["recurrent"] = b["nn_route_dist_in"] <= recur_thr_in
    g = b.groupby("clock_hour").agg(
        n_bouts=("recurrent", "size"),
        n_animals=("shortid", "nunique"),
        n_motifs=("motif", "nunique"),
        recurrence_frac=("recurrent", "mean"),
        median_disp_in=("disp_in", "median")).reset_index()
    g["bouts_per_animal"] = (g["n_bouts"] / g["n_animals"]).round(2)
    g["recurrence_frac"] = g["recurrence_frac"].round(3)
    g["median_disp_in"] = g["median_disp_in"].round(1)
    return g.sort_values("clock_hour").reset_index(drop=True)


def motif_by_day(bouts: pd.DataFrame, *, recur_thr_in: float) -> pd.DataFrame:
    """PER NIGHT (=per day) group-level route-motif summary — how stereotyped the
    whole group's routes are each night, and whether one motif dominates. One row
    per night: n_bouts, n_animals, n_motifs, recurrence_frac, dominant_motif +
    dominant_frac (share of that night's bouts in its most-used cluster),
    group_entropy (normalized Shannon over the night's motif usage; low = the group
    reuses a few routes), median_disp_in.
    """
    b = bouts.copy()
    b["recurrent"] = b["nn_route_dist_in"] <= recur_thr_in
    rows = []
    for night, g in b.groupby("night"):
        vc = g["motif"].value_counts()
        rows.append({"night": night, "n_bouts": int(len(g)),
                     "n_animals": int(g["shortid"].nunique()),
                     "n_motifs": int(g["motif"].nunique()),
                     "recurrence_frac": round(float(g["recurrent"].mean()), 3),
                     "dominant_motif": int(vc.index[0]),
                     "dominant_frac": round(float(vc.iloc[0] / len(g)), 3),
                     "group_entropy": round(_norm_entropy(vc.to_numpy()), 4),
                     "median_disp_in": round(float(g["disp_in"].median()), 1)})
    return pd.DataFrame(rows).sort_values("night").reset_index(drop=True)


def individual_vs_shared(bouts: pd.DataFrame, D: np.ndarray, *,
                         n_perm: int = 500, seed: int = 0) -> dict:
    """
    Is route stereotypy INDIVIDUAL or SHARED? For each bout, nearest-neighbour
    distance to (a) the SAME animal's bouts on OTHER nights vs (b) OTHER animals'
    bouts. If routes are individual, self-NN < other-NN. Tested vs an animal-label
    permutation null. Returns observed gap (other-self), null mean/sd, z, per-animal.
    """
    rng = np.random.default_rng(seed)
    sid = bouts["shortid"].to_numpy().astype(str)
    night = bouts["night"].to_numpy().astype(str)
    N = len(bouts)
    Dw = D.copy()
    np.fill_diagonal(Dw, np.inf)

    def gap_for(labels):
        self_nn, other_nn = [], []
        for i in range(N):
            same = (labels == labels[i]) & (night != night[i])
            diff = labels != labels[i]
            if same.any():
                self_nn.append(Dw[i, same].min())
            if diff.any():
                other_nn.append(Dw[i, diff].min())
        if not self_nn or not other_nn:
            return np.nan
        return float(np.mean(other_nn) - np.mean(self_nn))

    obs = gap_for(sid)
    null = np.array([gap_for(rng.permutation(sid)) for _ in range(n_perm)])
    null = null[np.isfinite(null)]
    mu, sd = (float(null.mean()), float(null.std())) if null.size else (np.nan, np.nan)
    z = (obs - mu) / sd if sd and np.isfinite(obs) else np.nan
    per = []
    for tag in sorted(set(sid)):
        idx = np.where(sid == tag)[0]
        s, o = [], []
        for i in idx:
            same = (sid == tag) & (night != night[i])
            diff = sid != tag
            if same.any():
                s.append(Dw[i, same].min())
            if diff.any():
                o.append(Dw[i, diff].min())
        per.append({"shortid": tag,
                    "self_nn_in": round(float(np.mean(s)), 1) if s else np.nan,
                    "other_nn_in": round(float(np.mean(o)), 1) if o else np.nan,
                    "self_minus_other_in": (round(float(np.mean(s) - np.mean(o)), 1)
                                            if s and o else np.nan)})
    return {"observed_gap_in": obs, "null_mean": mu, "null_sd": sd, "z": z,
            "n_perm": int(null.size), "per_animal": pd.DataFrame(per)}
