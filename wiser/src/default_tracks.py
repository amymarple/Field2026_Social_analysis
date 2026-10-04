r"""Reader for the cohort default WISER tracks written by ``wiser/scripts/build_wiser_default_tracks.py``.

Plan: implementation_plan/2026-10-04-wiser-default-tracks-2026c.md. Report (coverage, reproduction, definitions):
results/<cohort>/wiser_baseline/reports/wiser_baseline_default_tracks_<cohort>.md

Layout (off-repo, under ``$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/wiser_default_tracks/``):

    <label>/<YYYYMMDD>.csv.gz   one row per deduplicated WISER fix of that field-PC calendar day (00:00-24:00, by t_ms)
    index_<cohort>.csv          one row per (label, date): fixes, hours, method share, IMU-ok share, ...
    README.md                   column definitions and caveats

Labels: ``SF07`` ... ``SF12`` (the animal inside a tag's validity window of ``wiser/configs/rat_identities_<cohort>.csv``),
``<animal>_tag<shortid>`` (a second tag worn by an animal at the same time as its primary tag), ``tag_<shortid>`` (a
shortid outside the identity table; no identity claim).

Columns (positions and velocities in inches / inches per second in the UNVERIFIED WISER frame):
  t_ms (WISER clock, Unix ms UTC = field-PC clock), t_al_ms (t_ms - tau*, implanted animals only, else empty), shortid,
  x_raw, y_raw (the fix), anchors_used, valid, m_handling, m_silence, m_tag_validity, m_adc_lane, m_off_animal (masks;
  flags, never removed), x, y, vx, vy (the default track at the fix), method (V3 / B2 per fix), imu_ok, imu_state
  (0 unusable / 1 still / 2 active / 3 locomoting), zupt, loco_boost.

Caveat (carry it into every use): V3's 1-s speed and summed path during in-place activity that the head IMU labels
"locomoting" are +62-69 % above B2's (V3 report) - do not read them as translation.

Usage:
    import sys; sys.path.insert(0, "<repo>/wiser/src")
    from default_tracks import load_default_track, list_default_tracks
    idx = list_default_tracks("2026c")
    df = load_default_track("SF09", "2026-09-08")
"""
from __future__ import annotations

import os
from datetime import date as _date, datetime as _datetime
from pathlib import Path

import pandas as pd

TRACK_DIRNAME = "wiser_default_tracks"
BOOL_COLS = ("valid", "m_handling", "m_silence", "m_tag_validity", "m_adc_lane", "m_off_animal", "imu_ok", "zupt", "loco_boost")


def _out_root() -> Path:
    try:
        import output_paths  # wiser/src shim -> common/output_paths.py
        return Path(output_paths.out_root())
    except Exception:  # noqa: BLE001 - the reader must work without the repo layout on sys.path
        env = os.environ.get("FIELD2026_ANALYSIS_OUT_ROOT")
        return Path(env) if env else Path(r"D:\Field2026_analysis_out")


def track_root(cohort: str = "2026c", root: str | Path | None = None) -> Path:
    """``<OUT_ROOT>/<cohort>/wiser_default_tracks`` (or ``root`` when given)."""
    return Path(root) if root is not None else _out_root() / cohort / TRACK_DIRNAME


def date_key(date) -> str:
    """'2026-09-08' / '20260908' / date / datetime / Timestamp -> '20260908'."""
    if isinstance(date, (_datetime, _date, pd.Timestamp)):
        return pd.Timestamp(date).strftime("%Y%m%d")
    s = str(date).strip().replace("-", "").replace("/", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"unrecognised date {date!r}; use 'YYYY-MM-DD' or 'YYYYMMDD'")
    return s


def track_path(label: str, date, cohort: str = "2026c", root: str | Path | None = None) -> Path:
    return track_root(cohort, root) / label / f"{date_key(date)}.csv.gz"


def load_default_track(label: str, date, cohort: str = "2026c", root: str | Path | None = None,
                       columns: list | None = None) -> pd.DataFrame:
    """The default WISER track of one label and one field-PC calendar day (rows sorted by t_ms).

    Boolean columns come back as bool, t_al_ms as nullable Int64 (empty for labels without an IMU). Raises
    FileNotFoundError (listing what exists for the label) when there is no track for that label and day."""
    p = track_path(label, date, cohort, root)
    if not p.exists():
        d = p.parent
        have = sorted(f.name[:8] for f in d.glob("*.csv.gz")) if d.exists() else []
        labels = sorted(x.name for x in track_root(cohort, root).iterdir() if x.is_dir()) if track_root(cohort, root).exists() else []
        raise FileNotFoundError(f"no default track {p}; dates for {label}: {have or 'none'}; labels: {labels or 'none'}")
    df = pd.read_csv(p, usecols=columns)
    for c in BOOL_COLS:
        if c in df.columns:
            df[c] = df[c].astype(bool)
    if "t_al_ms" in df.columns:
        df["t_al_ms"] = df["t_al_ms"].astype("Int64")
    if "imu_state" in df.columns:
        df["imu_state"] = df["imu_state"].astype("int8")
    df.attrs["path"] = str(p)
    return df


def list_default_tracks(cohort: str = "2026c", root: str | Path | None = None) -> pd.DataFrame:
    """The index (one row per label and day). Falls back to a directory listing when the index is missing."""
    r = track_root(cohort, root)
    idx = r / f"index_{cohort}.csv"
    if idx.exists():
        return pd.read_csv(idx, dtype={"date": str})
    rows = [{"label": f.parent.name, "date": f.name[:8], "path": str(f)} for f in sorted(r.glob("*/*.csv.gz"))]
    return pd.DataFrame(rows, columns=["label", "date", "path"])
