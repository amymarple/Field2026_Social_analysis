"""wiser_inputs.py (wiser shim) — re-exports the canonical raw-input resolver in ``common/``.

The single source of truth is ``<repo>/common/wiser_inputs.py``. WISER drivers add ``wiser/src`` to
``sys.path`` and ``import wiser_inputs``; this shim keeps that import working while the real, cohort-aware
logic lives in one place. Do not add logic here — edit ``common/wiser_inputs.py``.
"""
from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path as _Path

_common = _Path(__file__).resolve().parents[2] / "common" / "wiser_inputs.py"
_spec = _ilu.spec_from_file_location("_common_wiser_inputs", _common)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

globals().update({k: getattr(_mod, k) for k in _mod.__all__})
__all__ = list(_mod.__all__)
