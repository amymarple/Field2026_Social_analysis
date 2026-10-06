#!/bin/bash
# Sleep scoring for every cohort-2026c session with an LFP, on BioHPC cbsuruiz01: variant imu_nremgate (scored) and the
# derived imu_remclean (REM post-rules), the pair validated locally on 4 sessions (change_log 2026-09-29, 2026-10-05).
# Inputs: the LFP from run_make_lfp.sh, and the compact IMU inputs exported on the analysis PC
# (score_sleep.py --export-imu-bundle, uploaded to $IMU). Resumable: finished (session, variant) pairs are skipped;
# failures land in $OUT/_errors/. Reports: $REPO/results/2026c/ephys_spikes/reports/ephys_spikes_sleep_scores*_2026c.csv.
#
# Launch from the analysis PC over the shared SSH connection:
#   ssh -S ~/.ssh/cm-gpu gpu 'nohup bash ~/src/Field2026_Social_analysis/ephys/server/run_score_sleep.sh \
#       > /workdir/hc997/logs/score_sleep_$(date +%Y%m%d_%H%M%S).log 2>&1 &'
set -u
REPO=${REPO:-$HOME/src/Field2026_Social_analysis}
PY=${PY:-$HOME/src/PreprocessPipeline/.venv/bin/python}
PIPE=${PIPE:-$HOME/src/PreprocessPipeline}
LFP=${LFP:-/workdir/hc997/ephys_2026c/lfp}
IMU=${IMU:-/workdir/hc997/ephys_2026c/imu_sleep_bundle}
OUT=${OUT:-/workdir/hc997/ephys_2026c/sleep}
WORKERS=${WORKERS:-32}
SESSIONS=${SESSIONS:-}            # empty = --all; else "SF10:<session> SF07:<session> ..."
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mkdir -p "$OUT"
cd "$REPO/ephys" || exit 1
echo "start $(date -Is)  repo $(cat ../.git_commit 2>/dev/null || echo unknown)  workers $WORKERS  out $OUT"
if [ -z "$SESSIONS" ]; then SEL="--all"; else SEL="--sessions $SESSIONS"; fi
"$PY" score_sleep.py --cohort 2026c $SEL --variants imu_nremgate imu_remclean --lfp-root "$LFP" --imu-root "$IMU" \
    --out-root "$OUT" --pipeline-root "$PIPE" --workers "$WORKERS" --report-name sleep_scores
echo "exit $? at $(date -Is)"
echo "scored: $(find "$OUT/imu_remclean" -name score_sleep.json | wc -l) sessions; errors: $(ls "$OUT/_errors" 2>/dev/null | wc -l); $(du -sh "$OUT" | cut -f1)"
