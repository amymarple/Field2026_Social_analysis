#!/bin/bash
# LFP-EMG for every cohort-3 session (ephys/emg_from_lfp.py) on BioHPC cbsuruiz01, from the storage LFP; then the
# verified copy to storage (run_then_store.sh, part emg_from_lfp). Validated locally first (2026-10-08): SF07
# 15_20260902_082418.755 from D:/3rd_rat_spikes/analysis/lfp (standard = the pipeline's function; fast r 0.994 vs the
# standard on 1-s means; selftest PASS). Resumable: a session with its .EMGFromLFP.json is skipped unless REDO is set.
# Plan: implementation_plan/2026-10-07-sleep-internal-schedule.md, Amendment 10.
#
# Launch from the analysis PC over the shared SSH connection:
#   ssh -S ~/.ssh/cm-gpu gpu 'nohup bash ~/src/Field2026_Social_analysis/ephys/server/run_emg_from_lfp.sh \
#       > /workdir/hc997/logs/emg_from_lfp_$(date +%Y%m%d_%H%M%S).log 2>&1 &'
set -u
REPO=${REPO:-$HOME/src/Field2026_Social_analysis}
PY=${PY:-$HOME/src/PreprocessPipeline/.venv/bin/python}
PP=${PP:-$HOME/src/PreprocessPipeline}
ST=${ST:-/fs/cbsuruizfs1/storage/hc997/SocialFieldRat2026/3rd_rat/analysis}
OUT=${OUT:-/workdir/hc997/ephys_2026c/emg_from_lfp}
WORKERS=${WORKERS:-16}
REDO=${REDO:-}
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mkdir -p "$OUT"
cd "$REPO/ephys" || exit 1
COMMIT=$(cat ../.git_commit 2>/dev/null || echo unknown)
PPC=$(git -C "$PP" rev-parse --short HEAD 2>/dev/null || echo unknown)
echo "start $(date -Is)  repo $COMMIT  pipeline $PPC  workers $WORKERS  out $OUT"
"$PY" emg_from_lfp.py --selftest || exit 1
# README.md is written by emg_from_lfp.py itself (the same text for a local or a server run)
PART=emg_from_lfp bash server/run_then_store.sh "$PY" emg_from_lfp.py --lfp-root "$ST/lfp" --out "$OUT" \
    --pc-time-root "$ST/pc_time" --pipeline-root "$PP" --workers "$WORKERS" ${REDO:+--redo}
echo "end $(date -Is)  sessions: $(ls "$OUT"/SF*/*.EMGFromLFP.json 2>/dev/null | wc -l)  errors: $(ls "$OUT"/_errors 2>/dev/null | wc -l)"
