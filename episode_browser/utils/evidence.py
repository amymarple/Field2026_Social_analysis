"""Camera routing, video lookup, and explicit evidence availability states."""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
WISER_SRC = REPO_ROOT / "wiser" / "src"
VISIBILITY_MAP = REPO_ROOT / "wiser" / "configs" / "camera_visibility_map.yaml"
DEFAULT_VIDEO_ROOT = Path(r"D:\Reolink_record\audio_in\Reolink_record")
_VIDEO_RE = re.compile(
    r"^(CH\d{2})_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})_to_(\d{2}-\d{2}-\d{2})\.mp4$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EvidenceStatus:
    status: str
    source: str
    reason: str


@dataclass(frozen=True)
class CameraRoute:
    candidates: tuple[str, ...]
    coverages: dict[str, float]
    confidence: float
    near_boundary: bool
    map_confirmed: bool
    status: str
    reason: str


def route_footprint(points_xy, map_path: str | Path = VISIBILITY_MAP,
                    margin_in: float = 15.0) -> CameraRoute:
    if str(WISER_SRC) not in sys.path:
        sys.path.insert(0, str(WISER_SRC))
    import camera_router  # noqa: PLC0415

    visibility = camera_router.load_visibility_map(map_path)
    result = camera_router.route_event(points_xy, visibility, margin_in=margin_in)
    candidates = tuple(c for c in (result.get("channel_rank_1"),
                                    result.get("channel_rank_2")) if c)
    confirmed = bool(visibility.get("confirmed", False))
    status = "unmapped" if not candidates else ("available" if confirmed else "unverified")
    return CameraRoute(
        candidates=candidates,
        coverages={str(k): float(v) for k, v in (result.get("coverages") or {}).items()},
        confidence=float(result.get("confidence") or 0.0),
        near_boundary=bool(result.get("near_boundary", False)),
        map_confirmed=confirmed,
        status=status,
        reason=str(result.get("reason") or "no camera coverage result"),
    )


def route_from_episode(episode: dict) -> CameraRoute:
    route = ((episode.get("linked_assets") or {}).get("camera_route") or {})
    return CameraRoute(
        candidates=tuple(route.get("candidates") or []),
        coverages={str(k): float(v) for k, v in (route.get("coverages") or {}).items()},
        confidence=float(route.get("confidence") or 0.0),
        near_boundary=bool(route.get("near_boundary", False)),
        map_confirmed=bool(route.get("map_confirmed", False)),
        status=str(route.get("status") or "unmapped"),
        reason=str(route.get("reason") or "no camera candidate"),
    )


def video_root() -> Path:
    return Path(os.environ.get("EPISODE_BROWSER_VIDEO_ROOT", DEFAULT_VIDEO_ROOT))


def resolve_recording(channel: str, t_start_ms: int,
                      root: str | Path | None = None) -> dict | None:
    root = Path(root) if root else video_root()
    local = pd.to_datetime(int(t_start_ms), unit="ms", utc=True).tz_convert("America/New_York")
    directory = root / str(channel).upper()
    if not directory.exists():
        return None
    prefix = f"{channel.upper()}_{local:%Y-%m-%d}_{local:%H}"
    for path in sorted(directory.glob(f"{prefix}*.mp4")):
        match = _VIDEO_RE.match(path.name)
        if not match:
            continue
        date, start_text, end_text = match.group(2), match.group(3), match.group(4)
        start = pd.Timestamp(f"{date} {start_text.replace('-', ':')}", tz="America/New_York")
        end = pd.Timestamp(f"{date} {end_text.replace('-', ':')}", tz="America/New_York")
        if end < start:
            end += pd.Timedelta(days=1)
        if start <= local <= end:
            return {
                "path": path,
                "channel": channel.upper(),
                "offset_s": max(0.0, (local - start).total_seconds()),
                "recording_start": start,
                "recording_end": end,
            }
    return None
