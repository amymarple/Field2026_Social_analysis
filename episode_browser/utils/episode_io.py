"""
episode_io.py — read/write the episode repository. Data-layer ONLY (no UI imports).

Formats:
  * Parquet  — PRIMARY store. Columnar + fast scalar filtering. Nested fields
    (maps / lists) are stored losslessly as JSON strings in their own columns, so
    the round-trip is exact (unlike CSV). This keeps the writer robust across
    pandas/pyarrow versions while preserving state_vector, probabilistic zones,
    and lens_scores.
  * JSONL    — human-readable alternative. One episode per line, nested fields as
    real JSON. Lossless.
  * CSV      — LOSSY EXPORT ONLY. Nested fields are JSON-stringified into cells;
    never use CSV as the primary store or re-import path.

`duration_s` is DERIVED here at load time (t_end - t_start). It is never persisted,
so the canonical time source (t_start/t_end) cannot drift from a stored copy.

Design note for the UI: nothing in this module renders anything. Streamlit's
full-rerun model means a faster frontend may replace app.py later; all read/query
logic must live here and in the sibling utils so it survives that swap.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

# Fields that hold nested structures (maps / lists / lists-of-maps). Everything
# else is a scalar column. Kept explicit so the on-disk contract is auditable.
NESTED_FIELDS = (
    "subject_ids",
    "subject_confidence",
    "state_vector",
    "state_before",
    "state_after",
    "zones",
    "labels",
    "source_streams",
    "qc_flags",
    "lens_scores",
    "environment_context",
    "linked_assets",
    "expert_annotations",
)

# Canonical time columns (ms since Unix epoch, UTC — matches WISER).
TIME_FIELDS = ("t_start", "t_end")


def _derive_duration(df: pd.DataFrame) -> pd.DataFrame:
    """Add duration_s from the canonical time source. Never stored on disk."""
    if {"t_start", "t_end"}.issubset(df.columns):
        df = df.copy()
        df["duration_s"] = (df["t_end"] - df["t_start"]) / 1000.0
    return df


def _encode_nested(df: pd.DataFrame) -> pd.DataFrame:
    """JSON-encode nested columns to strings for a lossless, version-robust Parquet/CSV write."""
    out = df.copy()
    # duration_s is derived — never write it.
    out = out.drop(columns=[c for c in ("duration_s",) if c in out.columns])
    for col in NESTED_FIELDS:
        if col in out.columns:
            out[col] = out[col].map(lambda v: json.dumps(v) if v is not None else None)
    return out


def _decode_nested(df: pd.DataFrame) -> pd.DataFrame:
    """Reverse of _encode_nested: JSON strings -> Python objects."""
    out = df.copy()
    for col in NESTED_FIELDS:
        if col in out.columns:
            out[col] = out[col].map(lambda v: json.loads(v) if isinstance(v, str) and v else v)
    return out


# --------------------------------------------------------------------------- #
# Parquet (primary)
# --------------------------------------------------------------------------- #
def write_parquet(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _encode_nested(df).to_parquet(path, index=False)
    return path


def read_parquet(path: str | Path, columns: Optional[Iterable[str]] = None,
                 filters=None) -> pd.DataFrame:
    """Load episodes from Parquet.

    `columns` lets the caller pull only the scalar columns it needs (e.g. for a
    lightweight table view) WITHOUT paying to decode every nested blob — the
    'don't load all the data at once' path. When None, everything is loaded and
    decoded.
    """
    df = pd.read_parquet(path, columns=list(columns) if columns else None, filters=filters)
    df = _decode_nested(df)
    return _derive_duration(df)


INDEX_COLUMNS = (
    "episode_id", "schema_version", "state_model_id", "level", "subject_ids",
    "t_start", "t_end", "labels", "source_streams", "boundary_confidence",
    "identity_confidence", "tracking_quality", "qc_flags", "lens_scores",
)


@dataclass(frozen=True)
class EpisodeRepository:
    """Bounded Parquet access for the queue and one selected nested record."""

    path: Path

    def __init__(self, path: str | Path):
        object.__setattr__(self, "path", Path(path))

    def exists(self) -> bool:
        return self.path.exists()

    def available_columns(self) -> set[str]:
        if not self.exists():
            return set()
        try:
            import pyarrow.parquet as pq

            return set(pq.read_schema(self.path).names)
        except ImportError:
            from fastparquet import ParquetFile

            return set(ParquetFile(self.path).columns)

    def record_span(self) -> tuple[int, int] | None:
        if not self.exists():
            return None
        df = read_parquet(self.path, columns=["t_start", "t_end"])
        if df.empty:
            return None
        return int(df["t_start"].min()), int(df["t_end"].max())

    def query_index(self, *, t_start_ms: int | None = None,
                    t_end_ms: int | None = None, limit: int = 50,
                    offset: int = 0) -> pd.DataFrame:
        if not self.exists():
            return pd.DataFrame(columns=INDEX_COLUMNS)
        filters = []
        if t_start_ms is not None:
            filters.append(("t_end", ">=", int(t_start_ms)))
        if t_end_ms is not None:
            filters.append(("t_start", "<=", int(t_end_ms)))
        available = self.available_columns()
        columns = [column for column in INDEX_COLUMNS if column in available]
        df = read_parquet(self.path, columns=columns, filters=filters or None)
        for column in INDEX_COLUMNS:
            if column not in df.columns:
                df[column] = None
        df = df.sort_values(["t_start", "episode_id"]).reset_index(drop=True)
        return df.iloc[int(offset):int(offset) + int(limit)].copy()

    def query_window(self, t_start_ms: int, t_end_ms: int) -> pd.DataFrame:
        return self.query_index(t_start_ms=t_start_ms, t_end_ms=t_end_ms,
                                limit=1_000_000, offset=0)

    def get_episode(self, episode_id: str) -> dict | None:
        if not self.exists() or not episode_id:
            return None
        df = read_parquet(self.path, filters=[("episode_id", "==", str(episode_id))])
        return None if df.empty else df.iloc[0].to_dict()


# --------------------------------------------------------------------------- #
# JSONL (human-readable alternative)
# --------------------------------------------------------------------------- #
def write_jsonl(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = df.drop(columns=[c for c in ("duration_s",) if c in df.columns]).to_dict(orient="records")
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    return path


def read_jsonl(path: str | Path) -> pd.DataFrame:
    rows = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return _derive_duration(pd.DataFrame(rows))


# --------------------------------------------------------------------------- #
# CSV (lossy export only)
# --------------------------------------------------------------------------- #
def export_csv(df: pd.DataFrame, path: str | Path) -> Path:
    """LOSSY export. Nested fields are JSON-stringified into cells. Do not re-import."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _encode_nested(df).to_csv(path, index=False)
    return path
