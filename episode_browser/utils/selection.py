"""Selected-episode context shared by every evidence view."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectedEpisodeContext:
    episode: dict
    episode_id: str
    subject_ids: tuple[str, ...]
    t_start: int
    t_end: int
    evidence_start: int
    evidence_end: int


def build_context(episode: dict | None, padding_s: float = 5.0) -> SelectedEpisodeContext | None:
    if not episode:
        return None
    t_start, t_end = int(episode["t_start"]), int(episode["t_end"])
    padding_ms = int(float(padding_s) * 1000)
    return SelectedEpisodeContext(
        episode=episode,
        episode_id=str(episode["episode_id"]),
        subject_ids=tuple(str(v) for v in (episode.get("subject_ids") or [])),
        t_start=t_start,
        t_end=t_end,
        evidence_start=t_start - padding_ms,
        evidence_end=t_end + padding_ms,
    )
