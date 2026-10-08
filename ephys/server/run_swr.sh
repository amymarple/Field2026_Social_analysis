#!/bin/bash
# Automatic SWR detection for every cohort-3 session on BioHPC cbsuruiz01 (ephys/swr_auto.py: DetectSWR candidates +
# NREM-fitted standardized k-means + DetectSWR check-mode localisation + per-event flags), from the storage LFP, then the
# verified copy to storage 3rd_rat/analysis/swr/ (run_then_store.sh, PART=swr).
# Validated locally first (2026-10-07): the Python DetectSWR is identical to the MATLAB on 18 lab sessions; on the two
# cohort-3 sessions the user scored, automatic vs user event F1 0.92 (SF10) / 0.87 (SF09); NREM-fitted boundary stable
# on wake-heavy nights (see change_log/2026-10-07-swr-detection-automation.md).
# Needs on the workdir: $INPUTS/states_1s_final/<SFxx>/<session>.states.npz (the FINAL 1-s sleep states, uploaded from the
# analysis PC D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final) and the channel config of the deployed commit.
#
# Launch from the analysis PC over the shared SSH connection:
#   ssh -S ~/.ssh/cm-gpu gpu 'nohup bash ~/src/Field2026_Social_analysis/ephys/server/run_swr.sh \
#       > /workdir/hc997/logs/swr_$(date +%Y%m%d_%H%M%S).log 2>&1 &'
set -u
REPO=${REPO:-$HOME/src/Field2026_Social_analysis}
PY=${PY:-$HOME/src/PreprocessPipeline/.venv/bin/python}
LFP=${LFP:-/fs/cbsuruizfs1/storage/hc997/SocialFieldRat2026/3rd_rat/analysis/lfp}
INPUTS=${INPUTS:-/workdir/hc997/ephys_2026c/swr_inputs}
OUT=${OUT:-/workdir/hc997/ephys_2026c/swr}
WORKERS=${WORKERS:-12}
ANIMALS=${ANIMALS:-"SF07 SF08 SF09 SF10 SF11 SF12"}
REDO=${REDO:-}
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mkdir -p "$OUT"
cd "$REPO/ephys" || exit 1
echo "start $(date -Is)  repo $(cat ../.git_commit 2>/dev/null || echo unknown)  workers $WORKERS  out $OUT"
"$PY" swr_detect.py --selftest || exit 1
cp "$REPO/ephys/configs/swr_channels_2026c.yaml" "$OUT/swr_channels_2026c.yaml"
cat > "$OUT/README_swr.txt" <<TXT
Automatic sharp-wave ripple events, cohort 3 (2026c), one folder per session: <SFxx>/<session>/
  <session>.swr_events.csv/.npz  events: start_s, stop_s, peak_s (session seconds; sample k <-> k/1250 s as in DetectSWR),
                                 duration_ms, amplitude, frequency_hz, SwMax_z / RipMax_z (DetectSWR local z = strength),
                                 state + imu_emg at the peak second (final 1-s sleep states), env_ratio_<noise|shankN>
                                 (80-250 Hz envelope at the peak / session median), n_shanks_ripple (shanks with ratio >= 2)
  <session>.SWR.evt              Neuroscope events (ms from the first sample)
  <session>.swr_summary.json     channels, k-means centres, counts, rates per state
  <session>.swr_qc.png           candidate scatter + events per 10 min
Method: ephys/swr_auto.py docstring; channels: swr_channels_2026c.yaml (copied here). Flags only - nothing is deleted;
exclusions (user noise sessions, SF12_contact_failing, valid_until, SF11 = cortex) are applied downstream.
Made by ephys/server/run_swr.sh, repo commit $(cat ../.git_commit 2>/dev/null || echo unknown), $(date -Is).
TXT
rc=0
for A in $ANIMALS; do
  PART=swr bash server/run_then_store.sh "$PY" swr_auto.py --animal "$A" --all --min-minutes 10 \
      --lfp-root "$LFP" --states-root "$INPUTS/states_1s_final" --out "$OUT" --workers "$WORKERS" ${REDO:+--redo} || rc=1
done
echo "end $(date -Is)  sessions: $(find "$OUT" -name '*.swr_summary.json' | wc -l)  errors: $(ls "$OUT/_errors" 2>/dev/null | wc -l)"
exit $rc
