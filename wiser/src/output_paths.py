"""output_paths.py (wiser shim) — re-exports the canonical cohort-aware helper in ``common/``.

The single source of truth is ``<repo>/common/output_paths.py``. WISER drivers add ``wiser/src`` to
``sys.path`` and ``import output_paths``; this shim keeps that import working while the real, cohort-aware
logic (and the ``FIELD2026_ANALYSIS_OUT_ROOT`` env var) lives in one place. Do not add logic here — edit
``common/output_paths.py``.
"""
from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path as _Path

_common = _Path(__file__).resolve().parents[2] / "common" / "output_paths.py"
_spec = _ilu.spec_from_file_location("_common_output_paths", _common)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

globals().update({k: getattr(_mod, k) for k in _mod.__all__})
__all__ = list(_mod.__all__)
