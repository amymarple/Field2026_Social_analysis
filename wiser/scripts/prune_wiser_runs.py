"""prune_wiser_runs.py — keep only the newest N run folders per analysis under the artifact root.

Drivers write a fresh ``<OUT_ROOT>/<cohort>/<name>_<YYYYMMDD_HHMM>/`` every run, so the root accumulates
old runs indefinitely. This trims them, per cohort. DRY-RUN by default — nothing is deleted until --apply.

    python scripts/prune_wiser_runs.py                        # list what --apply would delete (all cohorts, keep 3)
    python scripts/prune_wiser_runs.py --cohort 2026a --keep 5
    python scripts/prune_wiser_runs.py --cohort 2026a --name route_structure --apply
    FIELD2026_ANALYSIS_OUT_ROOT=E:\\somewhere python scripts/prune_wiser_runs.py --apply

The in-repo canonical reports under results/<cohort>/<direction>/ are never touched.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
import output_paths as op   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", type=int, default=3, help="run folders to keep per analysis (default 3)")
    ap.add_argument("--name", default=None, help="only prune this analysis name (default: all)")
    ap.add_argument("--cohort", default=None, help="only prune this cohort (default: all cohorts)")
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry-run)")
    args = ap.parse_args()

    root = op.out_root()
    groups = op.list_runs(args.cohort)
    if args.name:
        groups = {args.name: groups.get(args.name, [])}

    scope = args.cohort or "ALL cohorts"
    print(f"[prune] root={root}  cohort={scope}  keep={args.keep}  mode={'APPLY' if args.apply else 'dry-run'}")
    if not any(groups.values()):
        print("[prune] no run folders found.")
        return 0

    total = 0
    for name in sorted(groups):
        runs = groups[name]
        if not runs:
            continue
        doomed = op.prune(name, keep=args.keep, apply=args.apply, cohort=args.cohort)
        kept = len(runs) - len(doomed)
        tag = "deleted" if args.apply else "would delete"
        print(f"  {name}: {len(runs)} runs -> keep {kept}, {tag} {len(doomed)}")
        for p in doomed:
            print(f"      {tag}: {p.name}")
        total += len(doomed)

    verb = "deleted" if args.apply else "would delete"
    print(f"[prune] {verb} {total} folder(s).", end="")
    print("" if args.apply else "  Re-run with --apply to remove them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
