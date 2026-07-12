"""output_paths.py — single source of truth for where analysis outputs land, COHORT-AWARE.

Field2026_Social_analysis is cohort-appendable: results are keyed by cohort (``2026a``, ``2026b``, …)
and by research *direction* (``wiser_d3_sleep``, ``cv_shelter``, …). This module is the one place that
knows the layout, so adding a cohort never means restructuring — a driver just passes ``--cohort``.

Two homes for a run's outputs:

* **Off-repo bulk** — CSVs, figures dumps, the full ``run_manifest`` — go OUTSIDE the repo and OUTSIDE
  git, under ``<OUT_ROOT>/<cohort>/<name>_<YYYYMMDD_HHMM>/`` (see :func:`run_dir`). ``OUT_ROOT`` is the
  ``FIELD2026_ANALYSIS_OUT_ROOT`` env var (default ``D:\\Field2026_analysis_out``).  **NOTE:** this
  replaces the old repo's ``WISER_OUT_ROOT`` — that name is intentionally not reused.
* **In-repo canonical** — the human-readable report + its canonical figures, flat, live in the git tree
  under ``results/<cohort>/<direction>/{reports,figures}/`` (see :func:`report_dir`, :func:`figure_dir`).
  A ``run_manifest.json`` beside the report points back at the off-repo bulk run.

Superseded work mirrors the same shape under ``archive/<cohort>/<direction>/`` (:func:`archive_report_dir`).

Every driver should get its roots from here rather than hard-coding paths, so the location is defined
once and can be redirected with the env var (a machine without a D: drive, or a self-test).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
from pathlib import Path

__all__ = [
    "OUT_ROOT",
    "PROJECT_ROOT",
    "DEFAULT_COHORT",
    "out_root",
    "resolve_cohort",
    "run_dir",
    "report_dir",
    "figure_dir",
    "archive_report_dir",
    "archive_figure_dir",
    "assets_dir",
    "write_run_manifest",
    "write_latest_pointer",
    "list_runs",
    "latest_run",
    "prune",
]

# repo root = parent of common/  (this file is common/output_paths.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

_ENV_OUT_ROOT = "FIELD2026_ANALYSIS_OUT_ROOT"
_ENV_COHORT = "FIELD2026_COHORT"
_DEFAULT_OUT_ROOT = Path(r"D:\Field2026_analysis_out")

#: The cohort used when a caller does not pass one. Overridable with ``FIELD2026_COHORT``; the current
#: field season is ``2026a``. New drivers should take ``--cohort`` and pass it explicitly.
DEFAULT_COHORT = os.environ.get(_ENV_COHORT, "2026a")

# a run folder is "<name>_<YYYYMMDD>_<HHMM>"; the name may itself contain underscores, and a
# same-minute collision gets a "_<n>" disambiguator suffix (grouped under the same <name>).
_RUN_RE = re.compile(r"^(?P<name>.+)_(?P<ts>\d{8}_\d{4})(?:_(?P<seq>\d+))?$")


def out_root() -> Path:
    """The root under which timestamped run folders are written (off-repo, off-git).

    ``FIELD2026_ANALYSIS_OUT_ROOT`` overrides the default ``D:\\Field2026_analysis_out`` (used by the
    self-test and by machines without a D: drive)."""
    env = os.environ.get(_ENV_OUT_ROOT)
    return Path(env) if env else _DEFAULT_OUT_ROOT


#: Module-level convenience for scripts that only need the root.
OUT_ROOT = out_root()


def resolve_cohort(cohort: str | None) -> str:
    """Return ``cohort`` or the :data:`DEFAULT_COHORT` when ``None``. Validates the key is filesystem-safe."""
    c = cohort or DEFAULT_COHORT
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", c):
        raise ValueError(f"invalid cohort key {c!r}: use letters/digits/_-. only")
    return c


def _timestamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M")


def run_dir(name: str, cohort: str | None = None, *, make_figures: bool = True, root: Path | None = None) -> Path:
    """Create and return ``<root>/<cohort>/<name>_<YYYYMMDD_HHMM>/`` (root defaults to :func:`out_root`).

    A ``figures/`` subfolder is created too unless ``make_figures=False``. If a folder with the same
    minute-stamp already exists, a ``_2``, ``_3``, … suffix is appended so a run never silently
    overwrites another."""
    base = (root or out_root()) / resolve_cohort(cohort) / f"{name}_{_timestamp()}"
    out = base
    n = 2
    while out.exists():
        out = base.parent / f"{base.name}_{n}"
        n += 1
    (out / "figures").mkdir(parents=True, exist_ok=True) if make_figures else out.mkdir(parents=True, exist_ok=True)
    return out


def report_dir(cohort: str | None, direction: str | None = None) -> Path:
    """Create and return the in-repo canonical report home ``results/<cohort>/<direction>/reports/``.

    Back-compat: called with a single argument (``report_dir("wiser_d3_sleep")``) that argument is the
    *direction* and the cohort falls back to :data:`DEFAULT_COHORT`."""
    if direction is None:  # legacy single-arg call: the arg was the direction
        cohort, direction = None, cohort
    d = PROJECT_ROOT / "results" / resolve_cohort(cohort) / direction / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def figure_dir(cohort: str | None, direction: str | None = None) -> Path:
    """Create and return the in-repo canonical figure home ``results/<cohort>/<direction>/figures/`` (flat).

    Back-compat: a single argument is treated as the *direction* with the default cohort."""
    if direction is None:  # legacy single-arg call
        cohort, direction = None, cohort
    d = PROJECT_ROOT / "results" / resolve_cohort(cohort) / direction / "figures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def archive_report_dir(cohort: str | None, direction: str) -> Path:
    """Create and return ``archive/<cohort>/<direction>/reports/`` (superseded, mirrored shape)."""
    d = PROJECT_ROOT / "archive" / resolve_cohort(cohort) / direction / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def archive_figure_dir(cohort: str | None, direction: str) -> Path:
    """Create and return ``archive/<cohort>/<direction>/figures/`` (superseded, mirrored shape)."""
    d = PROJECT_ROOT / "archive" / resolve_cohort(cohort) / direction / "figures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def assets_dir(cohort: str | None, name: str, *, root: Path | None = None) -> Path:
    """Off-repo home for large / non-regeneratable assets (labeled datasets, model weights):
    ``<root>/<cohort>/assets/<name>/``. The repo keeps only an ``assets_manifest.json`` pointer."""
    d = (root or out_root()) / resolve_cohort(cohort) / "assets" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_run_manifest(report_dir_path: Path | str, run_dir_path: Path | str, **meta) -> Path:
    """Write ``<report_dir>/run_manifest.json`` naming the off-repo bulk run this report summarizes, plus
    any extra ``meta`` (git commit, params, cohort, driver). Keeps the in-repo report tied to its full run."""
    p = Path(report_dir_path) / "run_manifest.json"
    payload = {"run_dir": str(Path(run_dir_path).resolve()), **meta}
    p.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return p


def write_latest_pointer(report_dir_path: Path | str, run_dir_path: Path | str) -> Path:
    """Back-compat alias of :func:`write_run_manifest` (old name ``LATEST_RUN.txt`` retired)."""
    return write_run_manifest(report_dir_path, run_dir_path)


def list_runs(cohort: str | None = None, root: Path | None = None) -> dict[str, list[Path]]:
    """Group existing ``<name>_<ts>`` run folders under ``<root>/<cohort>/`` by analysis name, newest first.

    ``cohort=None`` scans every cohort subdir under ``root``."""
    root = root or out_root()
    scan_roots = [root / resolve_cohort(cohort)] if cohort else (
        [p for p in root.iterdir() if p.is_dir()] if root.exists() else []
    )
    groups: dict[str, list[Path]] = {}
    for sr in scan_roots:
        if not sr.exists():
            continue
        for child in sr.iterdir():
            if not child.is_dir() or child.name == "assets":
                continue
            m = _RUN_RE.match(child.name)
            if not m:
                continue
            groups.setdefault(m.group("name"), []).append(child)
    for name in groups:
        groups[name].sort(key=lambda p: p.name, reverse=True)  # ts sorts lexically
    return groups


def latest_run(name: str, cohort: str | None = None, root: Path | None = None) -> Path | None:
    """Newest run folder for one analysis ``name`` (exact prefix) in ``cohort``, or None."""
    return (list_runs(cohort, root).get(name) or [None])[0]


def prune(name: str, keep: int = 3, *, apply: bool = False, cohort: str | None = None, root: Path | None = None) -> list[Path]:
    """Return the run folders of ``name`` (in ``cohort``) older than the newest ``keep``; delete them only
    when ``apply=True`` (dry-run otherwise)."""
    if keep < 0:
        raise ValueError("keep must be >= 0")
    runs = list_runs(cohort, root).get(name, [])
    doomed = runs[keep:]
    if apply:
        for p in doomed:
            shutil.rmtree(p, ignore_errors=True)
    return doomed
