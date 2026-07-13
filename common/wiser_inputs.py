"""wiser_inputs.py — resolve the raw WISER snapshot DB for a cohort, two modes, provenance-recording.

This is the **input** side of the cohort-appendable pipeline; ``common/output_paths.py`` is the output side.
It reads the cohort registry (``cohorts/<key>.yaml``): the per-machine ``raw_data_roots`` **and** a per-cohort
``wiser:`` block (``snapshot_glob``, ``pinned_snapshot``, ``fixed_baseline``). Because the snapshot pattern
and pin live in the cohort YAML, adding a cohort stays *data + one YAML + a re-run* — no code change.

Two resolution modes (see :func:`resolve_wiser_db`):

* ``"latest"``    — exploratory / default convenience. The newest file matching ``snapshot_glob`` in the
  resolved snapshots dir. WISER snapshots are **cumulative** (each day's file is a superset of earlier ones),
  so newest = superset, and the default never goes stale as snapshots rotate.
* ``"canonical"`` — reproducible. The cohort's ``pinned_snapshot`` **exactly**; if no pin is declared, it
  **falls back to latest** and flags ``pin_fallback: true`` (loud, never silent).

An explicit ``--db`` path always wins over both. Every resolution returns a provenance dict (path, size,
mtime, mode, pin flags; plus a chunked **sha256** for canonical runs) suitable for the run manifest.

The **live-DB tools** (georeference, ROI/exclude placement, hourly occupancy, Direction-1 nightly) read the
*growing field DB*, not these cumulative snapshots, and deliberately do NOT use this resolver.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import importlib.util as _ilu
import json
import os
from pathlib import Path

__all__ = [
    "resolve_wiser_db",
    "resolve_fixed_db",
    "db_provenance",
    "finalize",
    "add_snapshot_flags",
    "write_input_provenance",
    "snapshots_dir",
    "MACHINE_PREFERENCE",
]

# --- load the sibling common modules by file path (sys.path-independent, like the shim) --------------
_HERE = Path(__file__).resolve().parent


def _load_sibling(modname: str):
    spec = _ilu.spec_from_file_location(f"_wi_{modname}", _HERE / f"{modname}.py")
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_cohorts = _load_sibling("cohorts")
_op = _load_sibling("output_paths")
load_cohort = _cohorts.load_cohort
resolve_cohort = _op.resolve_cohort

#: Local disk first, network master last (SQLite must not be analyzed over the network SMB mount).
MACHINE_PREFERENCE = ("analysis_pc", "biohpc", "field_pc")

_ENV_WISER_ROOT = "FIELD2026_WISER_ROOT"   # direct override of the snapshots dir
_ENV_MACHINE = "FIELD2026_MACHINE"          # force a raw_data_roots block


# --- snapshots dir + snapshot selection --------------------------------------------------------------

def snapshots_dir(cohort_cfg: dict, *, machine: str | None = None) -> Path:
    """Resolve the WISER *snapshots* directory for a cohort, preferring a local block over the network master.

    ``FIELD2026_WISER_ROOT`` overrides with a direct path; ``FIELD2026_MACHINE`` (or ``machine=``) forces a
    ``raw_data_roots`` block. Otherwise the first block in :data:`MACHINE_PREFERENCE` whose ``wiser_snapshots``
    directory exists wins. Raises with the tried candidates if none exist.
    """
    env = os.environ.get(_ENV_WISER_ROOT)
    if env:
        return Path(env)
    roots = cohort_cfg.get("raw_data_roots") or {}
    forced = machine or os.environ.get(_ENV_MACHINE)
    order = ([forced] if forced else []) + [m for m in MACHINE_PREFERENCE if m != forced]
    tried: list[Path] = []
    for m in order:
        blk = roots.get(m) if m else None
        if not blk:
            continue
        d = blk.get("wiser_snapshots")
        if not d:
            continue
        p = Path(d)
        tried.append(p)
        if p.exists():
            return p
    if tried:
        raise FileNotFoundError(
            "no WISER snapshots dir exists among "
            + ", ".join(str(t) for t in tried)
            + f". Copy the snapshots to a local drive or set {_ENV_WISER_ROOT}."
        )
    raise KeyError("cohort YAML declares no raw_data_roots.<machine>.wiser_snapshots")


def _wiser_cfg(cohort_cfg: dict) -> dict:
    w = cohort_cfg.get("wiser")
    if not w:
        raise KeyError(
            f"cohort {cohort_cfg.get('cohort')!r} YAML has no `wiser:` block "
            "(need snapshot_glob / pinned_snapshot / fixed_baseline)"
        )
    return w


def _latest_matching(directory: Path, glob: str) -> Path:
    """Newest file matching ``glob`` in ``directory``. Snapshot names are ISO-dated so a name sort is
    chronological; ties (or non-dated names) fall back to mtime."""
    hits = sorted(directory.glob(glob), key=lambda p: (p.name, p.stat().st_mtime))
    if not hits:
        raise FileNotFoundError(f"no snapshot matching {glob!r} in {directory}")
    return hits[-1]


# --- provenance / checksum ---------------------------------------------------------------------------

def _sha256(path: Path, *, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _cached_sha256(path: Path) -> tuple[str, bool]:
    """sha256 of ``path``, cached in ``<dir>/.sha256cache.json`` keyed by (name, size, mtime). Returns
    (digest, from_cache). Cache writes are best-effort and skipped on a read-only (network) location."""
    st = path.stat()
    key = path.name
    cache_file = path.parent / ".sha256cache.json"
    cache: dict = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    ent = cache.get(key)
    if ent and ent.get("size_bytes") == st.st_size and ent.get("mtime") == st.st_mtime:
        return ent["sha256"], True
    digest = _sha256(path)
    cache[key] = {"sha256": digest, "size_bytes": st.st_size, "mtime": st.st_mtime}
    try:  # best-effort; never write onto a read-only network master
        if os.access(path.parent, os.W_OK):
            cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        pass
    return digest, False


def db_provenance(path: Path | str, *, sha256: bool = False, **extra) -> dict:
    """Provenance record for a resolved DB file: path, size, mtime, and (optionally) a sha256 checksum.
    Extra keyword fields (mode, pinned, machine, …) are merged in."""
    path = Path(path)
    prov: dict = {"path": str(path), "name": path.name, "exists": path.exists()}
    if path.exists():
        st = path.stat()
        prov["size_bytes"] = st.st_size
        prov["mtime_iso"] = _dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
        if sha256:
            digest, cached = _cached_sha256(path)
            prov["sha256"] = digest
            prov["sha256_from_cache"] = cached
    prov.update(extra)
    return prov


# --- the resolver ------------------------------------------------------------------------------------

def resolve_wiser_db(
    cohort: str | None = None,
    *,
    mode: str = "latest",
    explicit: Path | str | None = None,
    machine: str | None = None,
    root: Path | str | None = None,
    glob: str | None = None,
    pin: str | None = None,
) -> tuple[Path, dict]:
    """Resolve the WISER snapshot DB for ``cohort`` and return ``(path, provenance)``.

    Precedence: ``explicit`` (``--db``) > ``mode`` selection. ``mode="canonical"`` uses the cohort's pinned
    snapshot (falling back to latest with ``pin_fallback=True`` when no pin is declared); ``mode="latest"``
    uses the newest snapshot. ``root``/``glob``/``pin`` override the cohort YAML (used by the self-test).
    A sha256 checksum is recorded for canonical resolutions.
    """
    if mode not in ("latest", "canonical"):
        raise ValueError(f"mode must be 'latest' or 'canonical', got {mode!r}")

    if explicit is not None:
        p = Path(explicit)
        return p, db_provenance(p, sha256=(mode == "canonical"), mode="explicit", cohort=cohort)

    if root is not None:
        directory = Path(root)
        if glob is None or (mode == "canonical" and pin is None):
            cfg = _wiser_cfg(load_cohort(resolve_cohort(cohort)))
            glob = glob or cfg["snapshot_glob"]
            pin = pin if pin is not None else cfg.get("pinned_snapshot")
    else:
        cohort = resolve_cohort(cohort)
        cfg_all = load_cohort(cohort)
        cfg = _wiser_cfg(cfg_all)
        directory = snapshots_dir(cfg_all, machine=machine)
        glob = glob or cfg["snapshot_glob"]
        pin = pin if pin is not None else cfg.get("pinned_snapshot")

    pin_fallback = False
    if mode == "canonical" and pin:
        p = directory / pin
        if not p.exists():
            raise FileNotFoundError(
                f"pinned snapshot {pin!r} not found in {directory}. "
                "Fix cohort YAML `wiser.pinned_snapshot`, or copy the pinned file locally, "
                "or run without --canonical to use the latest snapshot."
            )
    else:
        if mode == "canonical":  # canonical requested but no pin declared -> loud fallback
            pin_fallback = True
        p = _latest_matching(directory, glob)

    prov = db_provenance(
        p,
        sha256=(mode == "canonical"),
        mode=mode,
        pinned=bool(mode == "canonical" and not pin_fallback),
        pin_fallback=pin_fallback,
        snapshots_dir=str(directory),
        cohort=cohort,
    )
    return p, prov


def resolve_fixed_db(
    cohort: str | None = None,
    *,
    explicit: Path | str | None = None,
    machine: str | None = None,
    root: Path | str | None = None,
    name: str | None = None,
) -> Path:
    """Resolve the stationary-baseline (``tag_reports``) DB — the jitter-floor source. Explicit wins;
    otherwise ``wiser.fixed_baseline`` inside the resolved snapshots dir."""
    if explicit is not None:
        return Path(explicit)
    if root is not None and name is not None:
        return Path(root) / name
    cohort = resolve_cohort(cohort)
    cfg_all = load_cohort(cohort)
    cfg = _wiser_cfg(cfg_all)
    directory = Path(root) if root is not None else snapshots_dir(cfg_all, machine=machine)
    return directory / (name or cfg["fixed_baseline"])


# --- driver conveniences -----------------------------------------------------------------------------

def add_snapshot_flags(ap) -> None:
    """Add the ``--canonical`` flag to a driver's argparse parser (``--db``/``--fixed`` stay driver-defined,
    defaulting to ``None`` so :func:`finalize` resolves them)."""
    ap.add_argument(
        "--canonical",
        action="store_true",
        help="use the cohort-pinned snapshot for a reproducible run (default: latest local snapshot)",
    )


def finalize(args) -> tuple[Path, Path, dict]:
    """Resolve ``(db, fixed, provenance)`` from a driver's parsed args.

    Reads ``args.db`` / ``args.fixed`` / ``args.canonical`` / ``args.cohort`` (all optional). Mode is
    ``canonical`` when ``--canonical`` is set, else ``latest``. Explicit ``--db`` / ``--fixed`` win.
    """
    cohort = resolve_cohort(getattr(args, "cohort", None))
    mode = "canonical" if getattr(args, "canonical", False) else "latest"
    db, prov = resolve_wiser_db(cohort, mode=mode, explicit=getattr(args, "db", None))
    fixed = resolve_fixed_db(cohort, explicit=getattr(args, "fixed", None))
    prov["fixed_baseline"] = str(fixed)
    return db, fixed, prov


def write_input_provenance(out_dir: Path | str, prov: dict) -> Path:
    """Write ``<out_dir>/wiser_input_provenance.json`` next to the run manifest (off-repo bulk run dir)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "wiser_input_provenance.json"
    dest.write_text(json.dumps(prov, indent=2), encoding="utf-8")
    return dest
