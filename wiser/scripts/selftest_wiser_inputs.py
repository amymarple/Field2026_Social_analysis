"""selftest_wiser_inputs.py — offline synthetic check of the WISER raw-input resolver.

No field data / GPU / SQLite needed: the resolver only stats/hashes files, so plain byte files stand in for
snapshots. Exercises: latest selection, canonical pin, pin-fallback, explicit override, checksum (present for
canonical / absent for latest) + sha256 cache round-trip, local-first snapshots_dir selection, the missing-pin
error, the finalize() driver contract against the SHIPPED cohorts/2026a.yaml `wiser:` block, and
write_input_provenance. Run: python wiser/scripts/selftest_wiser_inputs.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]      # <repo>/wiser
sys.path.insert(0, str(PROJECT_ROOT / "src"))
import wiser_inputs as wi   # noqa: E402  (via the wiser/src shim -> common/wiser_inputs.py)

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(f"  [{'ok' if cond else 'FAIL'}] {msg}")
    if not cond:
        FAILS.append(msg)


def _touch(p: Path, payload: bytes) -> None:
    p.write_bytes(payload)


def main() -> int:
    print("=== wiser_inputs resolver self-test ===")
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # synthetic cumulative snapshots (ISO-dated names) + a stationary baseline + a decoy
        for day in ("2026-06-28", "2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02"):
            _touch(d / f"cohort_{day}.sqlite", f"snap-{day}".encode())
        _touch(d / "tag_reports_2026-06-30.sqlite", b"baseline")
        _touch(d / "notes.txt", b"decoy that must not match the glob")
        GLOB = "cohort_*.sqlite"

        # --- latest (exploratory default) ---
        p, prov = wi.resolve_wiser_db(root=d, glob=GLOB, mode="latest")
        check(p.name == "cohort_2026-07-02.sqlite", f"latest picks newest: {p.name}")
        check(prov["mode"] == "latest" and prov["pinned"] is False, "latest provenance flags")
        check("sha256" not in prov, "latest does NOT checksum by default (speed)")
        check(prov["size_bytes"] == len(b"snap-2026-07-02"), "latest records size")

        # --- canonical + explicit pin ---
        p, prov = wi.resolve_wiser_db(root=d, glob=GLOB, mode="canonical", pin="cohort_2026-07-01.sqlite")
        check(p.name == "cohort_2026-07-01.sqlite", f"canonical uses the pin, not latest: {p.name}")
        check(prov["pinned"] is True and prov["pin_fallback"] is False, "canonical pinned flags")
        check("sha256" in prov and len(prov["sha256"]) == 64, "canonical records a sha256 checksum")

        # --- canonical with NO pin declared -> loud fallback to latest ---
        p, prov = wi.resolve_wiser_db(root=d, glob=GLOB, mode="canonical", pin="")
        check(p.name == "cohort_2026-07-02.sqlite", "canonical w/o pin falls back to latest")
        check(prov["pin_fallback"] is True and prov["pinned"] is False, "fallback flagged loudly")

        # --- explicit --db wins over everything ---
        explicit = d / "cohort_2026-06-28.sqlite"
        p, prov = wi.resolve_wiser_db(root=d, glob=GLOB, mode="latest", explicit=explicit)
        check(p == explicit and prov["mode"] == "explicit", "explicit path wins")

        # --- sha256 cache round-trip (a file not hashed by any earlier assertion) ---
        pr1 = wi.db_provenance(d / "cohort_2026-06-29.sqlite", sha256=True)
        pr2 = wi.db_provenance(d / "cohort_2026-06-29.sqlite", sha256=True)
        check(pr1["sha256"] == pr2["sha256"], "sha256 stable across calls")
        check(pr1.get("sha256_from_cache") is False and pr2.get("sha256_from_cache") is True,
              "sha256 second call served from cache")
        check((d / ".sha256cache.json").exists(), "sha256 cache sidecar written")

        # --- missing pinned file errors clearly ---
        try:
            wi.resolve_wiser_db(root=d, glob=GLOB, mode="canonical", pin="cohort_2099-01-01.sqlite")
            check(False, "missing pin should raise")
        except FileNotFoundError:
            check(True, "missing pinned snapshot raises FileNotFoundError")

        # --- snapshots_dir: local (analysis_pc) preferred, network (biohpc) fallback ---
        cfg_net = {"raw_data_roots": {
            "analysis_pc": {"wiser_snapshots": str(d / "does_not_exist")},
            "biohpc": {"wiser_snapshots": str(d)},
        }}
        check(wi.snapshots_dir(cfg_net) == d, "snapshots_dir falls through to an existing block")
        cfg_local = {"raw_data_roots": {"analysis_pc": {"wiser_snapshots": str(d)},
                                        "biohpc": {"wiser_snapshots": str(d / "nope")}}}
        check(wi.snapshots_dir(cfg_local) == d, "snapshots_dir prefers the local block when it exists")

        # --- finalize() against the SHIPPED cohorts/2026a.yaml wiser block, via FIELD2026_WISER_ROOT ---
        real = Path(tempfile.mkdtemp())
        try:
            for day in ("2026-07-11", "2026-07-12"):
                _touch(real / f"1stcohort_2026_{day}.sqlite", f"real-{day}".encode())
            _touch(real / "tag_reports_2026-06-30.sqlite", b"baseline")
            os.environ["FIELD2026_WISER_ROOT"] = str(real)

            a = argparse.Namespace(db=None, fixed=None, canonical=False, cohort=None)
            db, fixed, prov = wi.finalize(a)
            check(db.name == "1stcohort_2026_2026-07-12.sqlite", f"finalize latest = {db.name}")
            check(fixed.name == "tag_reports_2026-06-30.sqlite", "finalize resolves the fixed baseline")

            a.canonical = True
            db, fixed, prov = wi.finalize(a)
            check(db.name == "1stcohort_2026_2026-07-12.sqlite", "finalize canonical uses 2026a pin (…07-12)")
            check(prov["pinned"] is True and "sha256" in prov, "finalize canonical provenance has pin+checksum")

            # write_input_provenance drops the json artifact
            outp = wi.write_input_provenance(real / "run_out", prov)
            check(outp.exists() and json.loads(outp.read_text())["name"] == db.name,
                  "write_input_provenance writes the json artifact")
        finally:
            os.environ.pop("FIELD2026_WISER_ROOT", None)
            import shutil
            shutil.rmtree(real, ignore_errors=True)

    if FAILS:
        print(f"\nFAIL — wiser_inputs self-test ({len(FAILS)} failed)")
        return 1
    print("\nPASS — wiser_inputs self-test (latest / canonical-pin / fallback / explicit / checksum / "
          "local-first / finalize on 2026a.yaml)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
