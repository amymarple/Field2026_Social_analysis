"""Build the bounded June 30 real Episode Browser integration slice.

The app reads the generated Parquet files; it never opens a complete WISER daily
gzip during normal rendering. Raw inputs are read-only and outputs are refused if
they already exist unless ``--force`` is passed explicitly.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
WISER_ROOT = REPO_ROOT / "wiser"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(WISER_ROOT / "src"))

from utils import episode_io, load_layout  # noqa: E402
from utils.evidence import resolve_recording, route_footprint  # noqa: E402
import trajectory_stereotypy as trajectory  # noqa: E402
import wiser_analysis_utils as wiser  # noqa: E402

WINDOW_START_LOCAL = pd.Timestamp("2026-06-30 21:00:00", tz="America/New_York")
WINDOW_END_LOCAL = pd.Timestamp("2026-06-30 21:15:00", tz="America/New_York")
WINDOW_START_MS = int(WINDOW_START_LOCAL.tz_convert("UTC").value // 1_000_000)
WINDOW_END_MS = int(WINDOW_END_LOCAL.tz_convert("UTC").value // 1_000_000)
STATE_MODEL_ID = "wiser_route_bout_v1"
FOLLOWING_STATE_MODEL_ID = "wiser_lagged_path_reuse_v1"
MOVING_THRESHOLD_INPS = 12.63
MIN_DISPLACEMENT_IN = 15.0
MIN_BOUT_S = 3.0
MAX_GAP_S = 2.0
JITTER_MARGIN_IN = 15.0

DATA_DIR = HERE / "data"
EPISODES_PARQUET = DATA_DIR / "real_episodes_20260630_2100_2115_v2.parquet"
EPISODES_JSONL = DATA_DIR / "real_episodes_20260630_2100_2115_v2.jsonl"
EVIDENCE_PARQUET = DATA_DIR / "real_wiser_evidence_20260630_2100_2115_v2.parquet"
RUN_MANIFEST = DATA_DIR / "real_slice_manifest_20260630_2100_2115_v2.json"
FOLLOWING_DIR = (
    WISER_ROOT / "outputs" / "following_incidents_2026-06-28_to_2026-07-08"
)
FOLLOWING_EPISODES = FOLLOWING_DIR / "strict_following_episodes.csv"
FOLLOWING_RUN_MANIFEST = FOLLOWING_DIR / "run_manifest.json"

RAW_COLS = [
    "reportid", "shortid", "calculation_error", "location_x", "location_y",
    "location_z", "anchors_used", "timestamp", "battery_voltage",
]


def source_files() -> list[Path]:
    root = Path(os.environ.get(
        "EPISODE_BROWSER_WISER_DIR", r"D:\Reolink_record\audio_in\Wiser_backup"
    )) / "incremental"
    return [root / "1stcohort_2026_2026-06-30.csv.gz",
            root / "1stcohort_2026_2026-07-01.csv.gz"]


def read_bounded_raw(paths: list[Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths:
        if not path.exists():
            continue
        for chunk in pd.read_csv(path, compression="gzip", usecols=RAW_COLS,
                                 chunksize=400_000):
            ts = pd.to_numeric(chunk["timestamp"], errors="coerce")
            keep = (ts >= WINDOW_START_MS) & (ts <= WINDOW_END_MS)
            if keep.any():
                frames.append(chunk.loc[keep].copy())
    if not frames:
        raise RuntimeError("No WISER fixes found in the configured real slice.")
    raw = pd.concat(frames, ignore_index=True)
    raw = raw.rename(columns={
        "location_x": "x", "location_y": "y", "location_z": "z",
        "timestamp": "ts_raw", "calculation_error": "calc_err",
    })
    raw["shortid"] = raw["shortid"].astype(str)
    raw = raw.drop_duplicates(subset=["shortid", "ts_raw", "x", "y"])
    raw["datetime"] = pd.to_datetime(raw["ts_raw"], unit="ms", utc=True).dt.tz_localize(None)
    return raw.sort_values(["shortid", "datetime"]).reset_index(drop=True)


def prepare_fixes(raw: pd.DataFrame) -> pd.DataFrame:
    fixes = wiser.add_speed(raw)
    rois = wiser.load_rois(WISER_ROOT / "configs" / "wiser_rois.json")
    fixes = wiser.add_validity_flags(
        fixes,
        boundary=(rois or {}).get("boundary"),
        jitter_floor_in=7.0,
    )
    fixes = wiser.apply_tag_cutoffs(fixes)
    fixes["night"] = "2026-06-30"
    return fixes


def _camera_route_dict(route) -> dict:
    return {
        "candidates": list(route.candidates),
        "coverages": route.coverages,
        "confidence": route.confidence,
        "near_boundary": route.near_boundary,
        "map_confirmed": route.map_confirmed,
        "status": route.status,
        "reason": route.reason,
        "jitter_margin_in": JITTER_MARGIN_IN,
    }


def build_episodes(fixes: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    valid = fixes[fixes["valid"]].copy()
    bouts, paths, bout_log = trajectory.extract_route_bouts(
        valid,
        ["2026-06-30"],
        moving_thr_inps=MOVING_THRESHOLD_INPS,
        min_disp_in=MIN_DISPLACEMENT_IN,
        min_bout_s=MIN_BOUT_S,
        max_gap_s=MAX_GAP_S,
        max_per_night=None,
        roi_cfg=None,
    )
    if bouts.empty:
        raise RuntimeError("The existing route-bout cut found no bouts in the slice.")

    rows: list[dict] = []
    candidates: list[dict] = []
    ordered = bouts.assign(path_index=range(len(bouts))).sort_values(
        ["t_start_ms", "shortid"]
    ).reset_index(drop=True)
    for ordinal, bout in enumerate(ordered.itertuples(), start=1):
        path = paths[int(bout.path_index)]
        route = route_footprint(path, margin_in=JITTER_MARGIN_IN)
        episode_id = f"wiser_route_20260630_{ordinal:04d}_{bout.shortid}"
        in_bout = fixes[
            (fixes["shortid"] == str(bout.shortid))
            & (fixes["ts_raw"] >= int(bout.t_start_ms))
            & (fixes["ts_raw"] <= int(bout.t_end_ms))
        ]
        state_vector = {
            "x": float(np.nanmedian(path[:, 0])),
            "y": float(np.nanmedian(path[:, 1])),
            "speed": float(in_bout["speed_inps_smooth"].median()),
            "displacement": float(bout.disp_in),
            "path_length": float(bout.path_in),
            "calculation_error": float(in_bout["calc_err"].median()),
        }
        qc_flags = ["unverified_wiser_frame"]
        if route.status == "unverified":
            qc_flags.append("unverified_camera_routing")
        elif route.status == "unmapped":
            qc_flags.append("video_unmapped")
        rows.append({
            "episode_id": episode_id,
            "schema_version": 1,
            "state_model_id": STATE_MODEL_ID,
            "level": "per_animal",
            "subject_ids": [str(bout.shortid)],
            "subject_confidence": None,
            "t_start": int(bout.t_start_ms),
            "t_end": int(bout.t_end_ms),
            "state_vector": state_vector,
            "state_before": None,
            "state_after": None,
            "zones": None,
            "source_streams": ["WISER"],
            "boundary_confidence": None,
            "identity_confidence": None,
            "tracking_quality": None,
            "labels": [],
            "lens_scores": None,
            "environment_context": {
                "light_phase": "night",
                "weather_alignment": "wall-clock EDT; unverified across devices",
            },
            "linked_assets": {
                "trajectory_snippet": path.round(3).tolist(),
                "camera_route": _camera_route_dict(route),
                "source_files": [str(p) for p in source_files() if p.exists()],
            },
            "qc_flags": qc_flags,
            "notes": "Uncapped existing WISER route-bout cut; pre-night-rain UI integration slice.",
            "expert_annotations": None,
        })
        if (len(route.candidates) == 1 and route.confidence >= 0.85
                and not route.near_boundary):
            recording = resolve_recording(route.candidates[0], int(bout.t_start_ms))
            if recording is not None:
                candidates.append({"episode_id": episode_id,
                                   "t_start": int(bout.t_start_ms),
                                   "channel": route.candidates[0]})

    candidates.sort(key=lambda row: row["t_start"])
    manifest = {
        "slice_label": "pre-night-rain integration slice",
        "window_local": [WINDOW_START_LOCAL.isoformat(), WINDOW_END_LOCAL.isoformat()],
        "window_utc_ms": [WINDOW_START_MS, WINDOW_END_MS],
        "state_model_id": STATE_MODEL_ID,
        "episode_count": len(rows),
        "bout_log": bout_log,
        "default_episode_id": candidates[0]["episode_id"] if candidates else rows[0]["episode_id"],
        "default_camera_candidate": candidates[0]["channel"] if candidates else None,
        "camera_map_confirmed": False,
    }
    return pd.DataFrame(rows), manifest


def _local_timestamp_ms(value) -> int:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("America/New_York")
    else:
        timestamp = timestamp.tz_convert("America/New_York")
    return int(timestamp.tz_convert("UTC").value // 1_000_000)


def _role_trajectory(fixes: pd.DataFrame, subject: str,
                     t_start: int, t_end: int) -> list[list[float]]:
    rows = fixes[
        (fixes["shortid"].astype(str) == str(subject))
        & (fixes["ts_raw"] >= t_start)
        & (fixes["ts_raw"] < t_end)
        & fixes["valid"]
    ].sort_values("ts_raw")
    return rows[["x", "y"]].dropna().round(3).values.tolist()


def build_following_episodes(fixes: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if not FOLLOWING_EPISODES.exists():
        raise FileNotFoundError(f"Following incident source not found: {FOLLOWING_EPISODES}")
    source = pd.read_csv(FOLLOWING_EPISODES, dtype={"leader": str, "follower": str})
    source.insert(0, "source_event_id", [f"ev{index:04d}" for index in range(len(source))])
    source["t_start_ms"] = source["t_start_local"].map(_local_timestamp_ms)
    source["t_end_inclusive_ms"] = source["t_end_local"].map(_local_timestamp_ms)
    overlapping = source[
        (source["t_start_ms"] < WINDOW_END_MS)
        & (source["t_end_inclusive_ms"] >= WINDOW_START_MS)
    ].sort_values(["t_start_ms", "leader", "follower"]).copy()

    source_manifest = {}
    if FOLLOWING_RUN_MANIFEST.exists():
        source_manifest = json.loads(FOLLOWING_RUN_MANIFEST.read_text(encoding="utf-8"))

    rows: list[dict] = []
    for incident in overlapping.itertuples():
        leader = str(incident.leader)
        follower = str(incident.follower)
        t_start = int(incident.t_start_ms)
        # Phase B2 stores the timestamp of the final inclusive 1 s grid bin.
        t_end = int(incident.t_end_inclusive_ms) + 1000
        leader_path = _role_trajectory(fixes, leader, t_start, t_end)
        follower_path = _role_trajectory(fixes, follower, t_start, t_end)
        footprint = np.asarray(leader_path + follower_path, dtype=float)
        if footprint.size == 0:
            footprint = np.empty((0, 2), dtype=float)
        route = route_footprint(footprint, margin_in=JITTER_MARGIN_IN)
        episode_id = (
            f"wiser_follow_20260630_{incident.source_event_id}_{leader}_{follower}"
        )
        qc_flags = ["unverified_wiser_frame", "candidate_behavior_label"]
        if route.status == "unverified":
            qc_flags.append("unverified_camera_routing")
        elif route.status == "unmapped":
            qc_flags.append("video_unmapped")
        rows.append({
            "episode_id": episode_id,
            "schema_version": 1,
            "state_model_id": FOLLOWING_STATE_MODEL_ID,
            "level": "pair",
            "subject_ids": [leader, follower],
            "subject_confidence": None,
            "t_start": t_start,
            "t_end": t_end,
            "state_vector": {
                "median_lag_s": float(incident.median_lag_s),
                "min_lag_s": float(incident.min_lag_s),
                "max_lag_s": float(incident.max_lag_s),
                "n_lags_fired": float(incident.n_lags_fired),
                "mean_separation_in": float(incident.mean_sep_in),
                "mean_heading_cosine": float(incident.mean_cos),
                "n_follow_bins": float(incident.n_follow_bins),
            },
            "state_before": None,
            "state_after": None,
            "zones": None,
            "source_streams": ["WISER"],
            "boundary_confidence": None,
            "identity_confidence": None,
            "tracking_quality": None,
            "labels": ["following", "strict_trailing_candidate"],
            "lens_scores": None,
            "environment_context": {
                "light_phase": "night",
                "weather_alignment": "wall-clock EDT; unverified across devices",
            },
            "linked_assets": {
                "role_map": {"leader": leader, "follower": follower},
                "trajectory_snippets": {
                    "leader": leader_path,
                    "follower": follower_path,
                },
                "camera_route": _camera_route_dict(route),
                "following_detector": {
                    "source_event_id": incident.source_event_id,
                    "source_file": str(FOLLOWING_EPISODES),
                    "source_run_manifest": str(FOLLOWING_RUN_MANIFEST),
                    "source_generated_utc": source_manifest.get("generated_utc"),
                    "source_git_commit": source_manifest.get("git_commit"),
                    "source_t_end_local_inclusive": str(incident.t_end_local),
                    "canonical_t_end_rule": "source inclusive final 1 s bin + 1000 ms",
                },
            },
            "qc_flags": qc_flags,
            "notes": (
                "Candidate strict trailing from the existing Phase B2 detector. "
                "Leader/follower is temporal order, not dominance; video validation pending."
            ),
            "expert_annotations": None,
        })

    return pd.DataFrame(rows), {
        "following_source": str(FOLLOWING_EPISODES),
        "following_source_manifest": str(FOLLOWING_RUN_MANIFEST),
        "following_source_generated_utc": source_manifest.get("generated_utc"),
        "following_source_git_commit": source_manifest.get("git_commit"),
        "following_source_episode_count": int(len(source)),
        "following_overlap_count": int(len(overlapping)),
        "following_t_end_normalization": "inclusive final 1 s bin converted to half-open end",
    }


def evidence_frame(fixes: pd.DataFrame, names: dict[str, str]) -> pd.DataFrame:
    out = fixes.copy()
    out["shortid"] = out["shortid"].astype(str)
    out["rat"] = out["shortid"].map(lambda value: names.get(value, value))
    out["ts"] = out["ts_raw"].astype("int64")
    columns = [
        "shortid", "rat", "x", "y", "ts", "calc_err", "anchors_used",
        "battery_voltage", "valid", "low_anchor_flag", "gap_flag", "jump_flag",
        "outside_provisional_bounds", "after_tag_cutoff", "speed_inps_smooth",
    ]
    return out[columns].sort_values(["shortid", "ts"]).reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="replace generated derived files; raw inputs are never modified")
    args = parser.parse_args()
    outputs = [EPISODES_PARQUET, EPISODES_JSONL, EVIDENCE_PARQUET, RUN_MANIFEST]
    existing = [path for path in outputs if path.exists()]
    if existing and not args.force:
        print("Refusing to overwrite existing derived files:")
        for path in existing:
            print(f"  {path}")
        return 2

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fixes = prepare_fixes(read_bounded_raw(source_files()))
    route_episodes, manifest = build_episodes(fixes)
    following_episodes, following_manifest = build_following_episodes(fixes)
    episodes = pd.concat([route_episodes, following_episodes], ignore_index=True)
    manifest.update(following_manifest)
    manifest.update({
        "episode_count": int(len(episodes)),
        "route_episode_count": int(len(route_episodes)),
        "following_episode_count": int(len(following_episodes)),
    })
    validation = importlib.import_module("utils.validation")
    report = validation.validate_all(episodes.to_dict("records"))
    if not report.ok:
        raise RuntimeError(report.summary())

    episode_io.write_parquet(episodes, EPISODES_PARQUET)
    episode_io.write_jsonl(episodes, EPISODES_JSONL)
    evidence_frame(fixes, load_layout.subject_name_map()).to_parquet(
        EVIDENCE_PARQUET, index=False
    )
    manifest.update({
        "source_files": [str(path) for path in source_files() if path.exists()],
        "episode_store": str(EPISODES_PARQUET),
        "wiser_evidence": str(EVIDENCE_PARQUET),
        "raw_fix_count": int(len(fixes)),
        "valid_fix_count": int(fixes["valid"].sum()),
        "frame": "WISER native inches; offset origin unverified",
        "jitter_floor_in": 7.0,
        "moving_threshold_inps": MOVING_THRESHOLD_INPS,
        "weather_interpretation": "covariate only; no storm-response label",
    })
    RUN_MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
