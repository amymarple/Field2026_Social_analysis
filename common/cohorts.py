"""cohorts.py — load the cohort registry (``cohorts/<key>.yaml``).

The registry is the appendability mechanism: one YAML per cohort holds its date range, per-machine raw-data
roots, identity file, and caveats. Drivers call :func:`load_cohort` (or :func:`add_cohort_arg` +
:func:`cohort_from_args`) so a new cohort is *data + one YAML + a re-run*, never a code change.
"""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    import yaml  # PyYAML
except Exception as e:  # pragma: no cover
    raise ImportError("cohorts.py needs PyYAML (pip install pyyaml)") from e

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COHORTS_DIR = PROJECT_ROOT / "cohorts"


def available_cohorts() -> list[str]:
    """Registered cohort keys (basenames of ``cohorts/*.yaml``), sorted."""
    return sorted(p.stem for p in COHORTS_DIR.glob("*.yaml"))


def load_cohort(cohort: str) -> dict:
    """Return the parsed cohort descriptor for ``cohort``. Fails loudly if the YAML is missing."""
    p = COHORTS_DIR / f"{cohort}.yaml"
    if not p.exists():
        have = ", ".join(available_cohorts()) or "(none)"
        raise FileNotFoundError(f"no cohort registered for {cohort!r} at {p}. Registered: {have}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    data.setdefault("cohort", cohort)
    return data


def add_cohort_arg(ap: argparse.ArgumentParser, *, default: str | None = None) -> argparse.ArgumentParser:
    """Add a standard ``--cohort`` argument to a driver's parser."""
    ap.add_argument(
        "--cohort",
        default=default,
        help="cohort key (a cohorts/<key>.yaml must exist); default from FIELD2026_COHORT or 2026a",
    )
    return ap


def cohort_from_args(args: argparse.Namespace) -> str:
    """Resolve the cohort key from parsed args (falls back to output_paths.DEFAULT_COHORT)."""
    from output_paths import resolve_cohort  # shim or common, whichever is on sys.path
    return resolve_cohort(getattr(args, "cohort", None))
