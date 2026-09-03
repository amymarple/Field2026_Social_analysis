"""Shared helpers for the ephys (WILD neurologger) scripts: cohort registry, output roots, git commit, hashing.

Everything here is cohort-agnostic; per-cohort facts come from ``cohorts/<key>.yaml`` (its ``ephys:`` block).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _p in (PROJECT_ROOT / "common", PROJECT_ROOT, PROJECT_ROOT / "ephys"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from cohorts import load_cohort  # noqa: E402  (common/cohorts.py)
from output_paths import out_root, resolve_cohort  # noqa: E402  (common/output_paths.py)

DEFAULT_DIRECTION = "ephys_spikes"
SESSION_RE = re.compile(r"^(?P<slot>\d+)_(?P<date>\d{8})_(?P<time>\d{6})(?:\.(?P<ms>\d+))?$")
MAC_RE = re.compile(r"^[0-9A-Fa-f]{12}$")


def ephys_block(cohort: str) -> dict:
    """The ``ephys:`` block of the cohort YAML (fails loudly when the cohort has no ephys modality)."""
    data = load_cohort(cohort)
    block = data.get("ephys")
    if not block:
        raise KeyError(f"cohorts/{cohort}.yaml has no 'ephys:' block: this cohort has no neurologger data registered")
    block = dict(block)
    block["_cohort_yaml"] = data
    return block


def raw_ephys_root(cohort: str, override: str | os.PathLike | None = None, machine: str = "analysis_pc") -> Path:
    """Raw offload root for this machine (``raw_data_roots.<machine>.ephys``), or an explicit override."""
    if override:
        return Path(override)
    data = load_cohort(cohort)
    root = ((data.get("raw_data_roots") or {}).get(machine) or {}).get("ephys")
    if not root:
        raise KeyError(f"cohorts/{cohort}.yaml: raw_data_roots.{machine}.ephys is not set (pass --raw-root)")
    return Path(root)


def analysis_root(cohort: str) -> Path | None:
    """Per-cohort derived-data root (``ephys.analysis_root`` in the cohort YAML), e.g. E:/3rd_rat_spikes/analysis; None if unset."""
    root = (load_cohort(cohort).get("ephys") or {}).get("analysis_root")
    return Path(root) if root else None


def stage_root(cohort: str, override: str | os.PathLike | None = None) -> Path:
    """Staging root for cleaned working copies: <analysis_root>/stage/ when the cohort declares one, else <OUT_ROOT>/<cohort>/ephys_stage/."""
    if override:
        return Path(override)
    ar = analysis_root(cohort)
    return ar / "stage" if ar else out_root() / resolve_cohort(cohort) / "ephys_stage"


def sort_root(cohort: str, override: str | os.PathLike | None = None) -> Path:
    """Sorting root (PreprocessPipeline local working dir): <analysis_root>/sort/ when declared, else <OUT_ROOT>/<cohort>/ephys_sort/."""
    if override:
        return Path(override)
    ar = analysis_root(cohort)
    return ar / "sort" if ar else out_root() / resolve_cohort(cohort) / "ephys_sort"


def tools_root(cohort: str) -> Path:
    """Where patched tool copies (e.g. Kilosort4) live: <analysis_root>/tools/ when declared, else <OUT_ROOT>/ephys_tools/."""
    ar = analysis_root(cohort)
    return ar / "tools" if ar else out_root() / "ephys_tools"


def report_dir(cohort: str, direction: str = DEFAULT_DIRECTION) -> Path:
    d = PROJECT_ROOT / "results" / resolve_cohort(cohort) / direction / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def figure_dir(cohort: str, direction: str = DEFAULT_DIRECTION) -> Path:
    d = PROJECT_ROOT / "results" / resolve_cohort(cohort) / direction / "figures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def git_commit(root: Path = PROJECT_ROOT) -> str:
    try:
        out = subprocess.check_output(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], text=True).strip()
        dirty = subprocess.call(["git", "-C", str(root), "diff", "--quiet"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0
        return out + ("+dirty" if dirty else "")
    except Exception:
        return "unknown"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_head_tail(path: Path, n_bytes: int = 64 * 1024 * 1024) -> str:
    """SHA-256 over the first and last ``n_bytes`` of a (possibly huge) file, a cheap identity fingerprint."""
    h = hashlib.sha256()
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        h.update(f.read(min(n_bytes, size)))
        if size > n_bytes:
            f.seek(max(size - n_bytes, n_bytes))
            h.update(f.read())
    return h.hexdigest()


def write_json(path: Path, payload: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def parse_session_name(name: str) -> dict | None:
    """``<slot>_<YYYYMMDD>_<HHMMSS>[.<ms>]`` -> {slot, start (datetime, wallclock), ms}. None if not a session folder."""
    m = SESSION_RE.match(name)
    if not m:
        return None
    ms = int((m.group("ms") or "0")[:3].ljust(3, "0"))
    start = datetime.strptime(m.group("date") + m.group("time"), "%Y%m%d%H%M%S").replace(microsecond=ms * 1000)
    return {"slot": int(m.group("slot")), "start": start, "ms": ms}


def iter_raw_sessions(raw_root: Path, session_glob: str = "*"):
    """Yield (animal, logger_mac_or_None, session_dir) for every session folder under <raw_root>/<animal>[/<mac>]/."""
    raw_root = Path(raw_root)
    for animal_dir in sorted(p for p in raw_root.iterdir() if p.is_dir() and not p.name.startswith(("$", "."))):
        for child in sorted(animal_dir.iterdir()):
            if not child.is_dir():
                continue
            if parse_session_name(child.name):
                yield animal_dir.name, None, child
            elif MAC_RE.match(child.name):
                for s in sorted(child.iterdir()):
                    if s.is_dir() and parse_session_name(s.name):
                        yield animal_dir.name, child.name.upper(), s


def find_session_dir(raw_root: Path, animal: str, session: str) -> Path:
    """Locate <raw_root>/<animal>/<any logger MAC>/<session>; the MAC level is discovered, not assumed."""
    animal_dir = Path(raw_root) / animal
    if not animal_dir.is_dir():
        raise FileNotFoundError(f"no animal folder {animal_dir}")
    direct = animal_dir / session
    if direct.is_dir():
        return direct
    hits = [p for p in animal_dir.glob(f"*/{session}") if p.is_dir()]
    if len(hits) != 1:
        raise FileNotFoundError(f"expected exactly one {session} under {animal_dir}/<logger>/, found {len(hits)}: {hits}")
    return hits[0]
