"""cohorts.py (cv_field shim) — re-exports the canonical cohort registry loader in ``common/``.

Same importlib re-export trick as ``output_paths.py`` beside it. ``common/cohorts.py`` has no ``__all__``,
so the public names are listed explicitly. ``cohort_from_args`` lazily does ``from output_paths import
resolve_cohort`` at call time, which resolves to the sibling ``output_paths.py`` shim once a driver has put
``cv/cv_field`` on ``sys.path``. Do not add logic here — edit ``common/cohorts.py``.
"""
from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path as _Path

_common = _Path(__file__).resolve().parents[2] / "common" / "cohorts.py"
_spec = _ilu.spec_from_file_location("_common_cohorts", _common)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

available_cohorts = _mod.available_cohorts
load_cohort = _mod.load_cohort
add_cohort_arg = _mod.add_cohort_arg
cohort_from_args = _mod.cohort_from_args

__all__ = ["available_cohorts", "load_cohort", "add_cohort_arg", "cohort_from_args"]
