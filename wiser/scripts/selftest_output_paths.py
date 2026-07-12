"""selftest_output_paths.py — offline PASS/FAIL check for the cohort-aware output_paths helper.

Runs entirely in a temp FIELD2026_ANALYSIS_OUT_ROOT; no WISER DB, no D: drive needed. Exit 0 = PASS.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

COH = "_selftest_cohort"


def main() -> int:
    fails: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["FIELD2026_ANALYSIS_OUT_ROOT"] = tmp
        import importlib
        import output_paths as op
        importlib.reload(op)  # pick up the env override in OUT_ROOT / out_root()

        root = Path(tmp)
        if op.out_root() != root:
            fails.append(f"out_root() honoured env: {op.out_root()} != {root}")

        # run_dir creates <root>/<cohort>/<name>_<ts>/figures
        d1 = op.run_dir("demo_analysis", COH)
        if not (d1 / "figures").is_dir():
            fails.append("run_dir did not create figures/")
        if d1.parent != root / COH:
            fails.append(f"run_dir wrote outside <root>/<cohort>: {d1}")

        # a same-minute second run must not collide with the first
        d2 = op.run_dir("demo_analysis", COH)
        if d2 == d1 or d2.exists() is False:
            fails.append("second same-minute run_dir collided or missing")

        # a different analysis name is grouped separately, within the cohort
        op.run_dir("other_analysis", COH)

        groups = op.list_runs(COH)
        if set(groups) != {"demo_analysis", "other_analysis"}:
            fails.append(f"list_runs grouping wrong: {sorted(groups)}")
        if len(groups.get("demo_analysis", [])) != 2:
            fails.append(f"expected 2 demo runs, got {len(groups.get('demo_analysis', []))}")

        # a different cohort is isolated
        op.run_dir("demo_analysis", "_other_cohort")
        if op.list_runs(COH).get("demo_analysis") and len(op.list_runs(COH)["demo_analysis"]) != 2:
            fails.append("cohorts not isolated in list_runs")

        # latest_run resolves the newest of the two demo runs in the cohort
        latest = op.latest_run("demo_analysis", COH)
        if latest is None or latest not in groups["demo_analysis"]:
            fails.append("latest_run did not resolve a demo run")

        # prune dry-run reports the older demo run but does NOT delete it
        doomed = op.prune("demo_analysis", keep=1, apply=False, cohort=COH)
        if len(doomed) != 1:
            fails.append(f"prune dry-run should flag 1, flagged {len(doomed)}")
        if not doomed[0].exists():
            fails.append("prune dry-run deleted a folder (should not)")

        # prune apply removes it, keeping the newest
        op.prune("demo_analysis", keep=1, apply=True, cohort=COH)
        remaining = op.list_runs(COH).get("demo_analysis", [])
        if len(remaining) != 1 or remaining[0] != latest:
            fails.append(f"prune apply left {len(remaining)} runs, expected newest only")

        # report_dir + run_manifest land in the repo tree and name the run folder
        rd = op.report_dir(COH, "_selftest_direction")
        if rd != PROJECT_ROOT.parent / "results" / COH / "_selftest_direction" / "reports":
            fails.append(f"report_dir wrong location: {rd}")
        ptr = op.write_run_manifest(rd, latest, cohort=COH, direction="_selftest_direction")
        if ptr.name != "run_manifest.json":
            fails.append(f"pointer not run_manifest.json: {ptr.name}")
        if json.loads(ptr.read_text())["run_dir"] != str(Path(latest).resolve()):
            fails.append("run_manifest.json did not name the run folder")

        # back-compat: single-arg report_dir treats the arg as the direction
        rd_legacy = op.report_dir("_selftest_direction")   # -> results/<default cohort>/_selftest_direction/reports
        if rd_legacy.parent.name != "_selftest_direction":
            fails.append("legacy single-arg report_dir did not use the arg as direction")

        # clean the throwaway repo results dirs
        shutil.rmtree(PROJECT_ROOT.parent / "results" / COH, ignore_errors=True)
        shutil.rmtree(PROJECT_ROOT.parent / "results" / op.DEFAULT_COHORT / "_selftest_direction", ignore_errors=True)

    if fails:
        print("FAIL — output_paths self-test")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("PASS — output_paths self-test (cohort run_dir / list_runs / latest_run / prune / manifest)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
