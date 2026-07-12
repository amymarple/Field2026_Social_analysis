"""Coverage computations kept outside the UI.

``compute_separate_coverage`` is the real selected-episode contract. It keeps
source-data availability (valid one-second WISER bins) separate from exact
imported-episode interval coverage. Time not represented by this importer is not
a source-data or QC gap.

``compute_coverage`` remains for the synthetic fixture's legacy subject-by-level
tiling view. New real-data code should use the separate summary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

GAP_REASONS = ("tracking_lost", "occlusion", "no_data")


@dataclass
class Interval:
    t_start: int          # Unix ms
    t_end: int
    kind: str             # available/gap or episode/not_represented
    reason: Optional[str] = None      # gap reason, or None for episodes
    episode_id: Optional[str] = None

    @property
    def duration_s(self) -> float:
        return (self.t_end - self.t_start) / 1000.0


@dataclass(frozen=True)
class CoverageLane:
    subject_id: str
    intervals: list[Interval]
    covered_s: float
    span_s: float
    pct: float


@dataclass(frozen=True)
class CoverageSummary:
    """Source-data availability and importer coverage with separate meanings."""

    data_availability: dict[str, CoverageLane]
    episode_coverage: dict[str, CoverageLane]
    span: tuple[int, int]


def _bool_runs(mask, start_ms: int, bin_ms: int, true_kind: str,
               false_kind: str, false_reasons=None) -> list[Interval]:
    intervals: list[Interval] = []
    if len(mask) == 0:
        return intervals
    run_start = 0
    current = bool(mask[0])
    for i in range(1, len(mask) + 1):
        changed = i == len(mask) or bool(mask[i]) != current
        if not changed:
            continue
        start = start_ms + run_start * bin_ms
        end = start_ms + i * bin_ms
        if current:
            intervals.append(Interval(start, end, true_kind))
        else:
            reason = None
            if false_reasons is not None:
                values = false_reasons[run_start:i]
                reason = "tracking_lost" if "tracking_lost" in values else "no_data"
            intervals.append(Interval(start, end, false_kind, reason=reason))
        if i < len(mask):
            run_start, current = i, bool(mask[i])
    return intervals


def compute_separate_coverage(episodes: pd.DataFrame, fixes: pd.DataFrame,
                              span: tuple[int, int], *, bin_s: int = 1,
                              state_model_id: str = "wiser_route_bout_v1") -> CoverageSummary:
    """Compute source availability and imported-episode coverage independently.

    Availability uses one-second bins with at least one valid WISER fix. Episode
    coverage is the union of real route-bout intervals. Its complement is
    ``not_represented`` and never receives a data/QC gap reason.
    """
    s0, s1 = map(int, span)
    bin_ms = int(bin_s * 1000)
    n_bins = max(1, int((s1 - s0 + bin_ms - 1) // bin_ms))
    fix_subjects = set(fixes.get("shortid", pd.Series(dtype=str)).astype(str))
    episode_subjects = {
        str(subject)
        for values in episodes.get("subject_ids", [])
        if isinstance(values, list)
        for subject in values
    }
    subjects = sorted(fix_subjects | episode_subjects)
    data_lanes: dict[str, CoverageLane] = {}
    episode_lanes: dict[str, CoverageLane] = {}

    for subject in subjects:
        subject_fixes = (fixes[fixes["shortid"].astype(str) == subject]
                         if not fixes.empty else fixes)
        valid_mask = [False] * n_bins
        any_mask = [False] * n_bins
        for row in subject_fixes.itertuples():
            index = int((int(row.ts) - s0) // bin_ms)
            if 0 <= index < n_bins:
                any_mask[index] = True
                valid_mask[index] = valid_mask[index] or bool(getattr(row, "valid", True))
        reasons = ["tracking_lost" if any_mask[i] and not valid_mask[i] else "no_data"
                   for i in range(n_bins)]
        data_intervals = _bool_runs(valid_mask, s0, bin_ms, "available", "gap", reasons)
        available_s = sum(iv.duration_s for iv in data_intervals if iv.kind == "available")
        span_s = n_bins * bin_s
        data_lanes[subject] = CoverageLane(
            subject, data_intervals, available_s, span_s,
            100.0 * available_s / span_s,
        )

        episode_spans: list[tuple[int, int]] = []
        for row in episodes.itertuples():
            if getattr(row, "state_model_id", None) != state_model_id:
                continue
            ids = getattr(row, "subject_ids", [])
            if not isinstance(ids, list) or subject not in {str(v) for v in ids}:
                continue
            start = max(s0, int(row.t_start))
            end = min(s1, int(row.t_end))
            if end > start:
                episode_spans.append((start, end))
        merged_spans = _merge_intervals(episode_spans)
        episode_intervals: list[Interval] = []
        cursor = s0
        for start, end in merged_spans:
            if start > cursor:
                episode_intervals.append(Interval(cursor, start, "not_represented"))
            episode_intervals.append(Interval(start, end, "episode"))
            cursor = max(cursor, end)
        if cursor < s1:
            episode_intervals.append(Interval(cursor, s1, "not_represented"))
        episode_span_s = max(0.0, (s1 - s0) / 1000.0)
        covered_s = sum((end - start) / 1000.0 for start, end in merged_spans)
        episode_lanes[subject] = CoverageLane(
            subject, episode_intervals, covered_s, episode_span_s,
            100.0 * covered_s / episode_span_s if episode_span_s else 0.0,
        )

    return CoverageSummary(data_lanes, episode_lanes, (s0, s1))


def _merge_intervals(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping/touching [start, end] spans."""
    if not spans:
        return []
    spans = sorted(spans)
    merged = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _explode_subjects(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (subject_id, episode). subject_ids is a list; 'unknown' is kept."""
    if "subject_ids" not in df.columns:
        return df.assign(subject_id="unknown")
    rows = df.copy()
    rows["subject_id"] = rows["subject_ids"].map(
        lambda v: v if isinstance(v, list) and v else ["unknown"]
    )
    return rows.explode("subject_id", ignore_index=True)


def record_span(df: pd.DataFrame) -> tuple[int, int]:
    """Overall [min t_start, max t_end] across all episodes (Unix ms)."""
    if df.empty:
        return (0, 0)
    return (int(df["t_start"].min()), int(df["t_end"].max()))


def compute_coverage(df: pd.DataFrame,
                     gaps_df: Optional[pd.DataFrame] = None,
                     span: Optional[tuple[int, int]] = None) -> dict:
    """Compute per-(subject, level) tiling.

    Returns {(subject_id, level): {"intervals": [Interval...],
                                   "tiled_s": float, "span_s": float,
                                   "pct_tiled": float}}.

    `gaps_df` (optional) columns: subject_id, level, t_start, t_end, reason —
    lets the caller attribute WHY a gap exists. Reasons only annotate; they never
    create or remove coverage. Where a computed gap overlaps a reason row, it takes
    that reason; otherwise 'no_data'.
    """
    if df.empty:
        return {}
    span = span or record_span(df)
    s0, s1 = span
    ex = _explode_subjects(df)

    result: dict = {}
    for (subj, level), grp in ex.groupby(["subject_id", "level"]):
        eps = _merge_intervals([(int(r.t_start), int(r.t_end)) for r in grp.itertuples()])

        intervals: list[Interval] = []
        # Episode intervals (keep episode_id where a single episode maps 1:1).
        for r in grp.itertuples():
            intervals.append(Interval(int(r.t_start), int(r.t_end), "episode",
                                      episode_id=getattr(r, "episode_id", None)))

        # Gaps = complement of merged episode spans within [s0, s1].
        cursor = s0
        gap_spans: list[tuple[int, int]] = []
        for gs, ge in eps:
            if gs > cursor:
                gap_spans.append((cursor, gs))
            cursor = max(cursor, ge)
        if cursor < s1:
            gap_spans.append((cursor, s1))

        for gs, ge in gap_spans:
            intervals.append(Interval(gs, ge, "gap",
                                      reason=_gap_reason(gaps_df, subj, level, gs, ge)))

        tiled_s = sum((e - s) for s, e in eps) / 1000.0
        span_s = max(0.0, (s1 - s0) / 1000.0)
        result[(subj, level)] = {
            "intervals": sorted(intervals, key=lambda iv: iv.t_start),
            "tiled_s": tiled_s,
            "span_s": span_s,
            "pct_tiled": (100.0 * tiled_s / span_s) if span_s > 0 else 0.0,
        }
    return result


def _gap_reason(gaps_df: Optional[pd.DataFrame], subj: str, level: str,
                gs: int, ge: int) -> str:
    """Attribute a reason to a gap by overlap with the companion gaps table."""
    if gaps_df is None or gaps_df.empty:
        return "no_data"
    m = gaps_df[
        (gaps_df["subject_id"] == subj)
        & (gaps_df["level"] == level)
        & (gaps_df["t_start"] < ge)
        & (gaps_df["t_end"] > gs)
    ]
    if m.empty:
        return "no_data"
    # Pick the reason covering the largest overlap.
    best, best_ov = "no_data", -1
    for r in m.itertuples():
        ov = min(ge, int(r.t_end)) - max(gs, int(r.t_start))
        if ov > best_ov:
            best, best_ov = str(r.reason), ov
    return best if best in GAP_REASONS else "no_data"


def overall_completeness(coverage: dict) -> float:
    """Record-wide '% of record tiled', pooled across all (subject, level) lanes."""
    tiled = sum(v["tiled_s"] for v in coverage.values())
    span = sum(v["span_s"] for v in coverage.values())
    return (100.0 * tiled / span) if span > 0 else 0.0
