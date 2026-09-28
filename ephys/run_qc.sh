#!/bin/bash
# Full post-offload QC for one cohort: index -> field-PC-time chain (+ pc_time.dat) -> QC report -> coverage tables -> mirror.
# Usage: bash ephys/run_qc.sh [cohort] [workers]      (defaults: 2026c, 8). Run from anywhere; ~1.5-2.5 h for 240 sessions.
COHORT="${1:-2026c}"; WORKERS="${2:-8}"
cd "$(dirname "$0")/.." || exit 1
ROOT=$(python -c "import sys; sys.path.insert(0,'ephys'); from _common import analysis_root; print(analysis_root('$COHORT') or '')")
echo "start $(date)  cohort=$COHORT analysis_root=$ROOT"
python ephys/build_session_index.py --cohort "$COHORT" --workers "$WORKERS" || { echo "INDEX FAILED"; exit 1; }
echo "index ok $(date)"
if [ -n "$ROOT" ]; then
  python ephys/pc_time_chain.py --cohort "$COHORT" --write-pc-time "$ROOT/pc_time" || { echo "CHAIN FAILED"; exit 1; }
else
  python ephys/pc_time_chain.py --cohort "$COHORT" || { echo "CHAIN FAILED"; exit 1; }
fi
echo "chain ok $(date)"
python ephys/offload_qc_report.py --cohort "$COHORT" || { echo "REPORT FAILED"; exit 1; }
python ephys/coverage_tables.py --cohort "$COHORT" || { echo "COVERAGE FAILED"; exit 1; }
if [ -n "$ROOT" ]; then
  mkdir -p "$ROOT/index"
  cp results/"$COHORT"/ephys_spikes/reports/ephys_spikes_*"$COHORT"* "$ROOT/index/" 2>/dev/null
  cp results/"$COHORT"/ephys_spikes/figures/ephys_spikes_coverage_raster_"$COHORT".png "$ROOT/index/" 2>/dev/null
fi
echo "ALL DONE $(date)"
