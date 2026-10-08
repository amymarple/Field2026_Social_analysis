#!/bin/bash
# Automatic SWR detection for every cohort-3 session on BioHPC cbsuruiz01 (ephys/swr_auto.py: DetectSWR candidates + one
# k-means boundary per animal x probe block from its reference session + DetectSWR check-mode localisation + per-event
# flags / exclusions), from the storage LFP; all animals in parallel; then the verified copy to storage
# 3rd_rat/analysis/swr/ (run_then_store.sh, PART=swr).
# Validated locally first (2026-10-07/08): the Python DetectSWR is identical to the MATLAB on 17 lab sessions; against
# the user's GUI scoring (kept events) F1 0.81-0.91 on SF07 / SF09 / SF10 (change_log/2026-10-07-swr-detection-automation.md).
# Needs on the workdir: $INPUTS/states_1s_final/<SFxx>/<session>.states.npz (the FINAL 1-s sleep states, uploaded from the
# analysis PC D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final) and the channel config of the deployed commit.
#
# Launch from the analysis PC:
#   ssh gpu 'nohup bash ~/src/Field2026_Social_analysis/ephys/server/run_swr.sh \
#       > /workdir/hc997/logs/swr_$(date +%Y%m%d_%H%M%S).log 2>&1 &'
set -u
REPO=${REPO:-$HOME/src/Field2026_Social_analysis}
PY=${PY:-$HOME/src/PreprocessPipeline/.venv/bin/python}
LFP=${LFP:-/fs/cbsuruizfs1/storage/hc997/SocialFieldRat2026/3rd_rat/analysis/lfp}
INPUTS=${INPUTS:-/workdir/hc997/ephys_2026c/swr_inputs}
OUT=${OUT:-/workdir/hc997/ephys_2026c/swr}
WORKERS_PER_ANIMAL=${WORKERS_PER_ANIMAL:-18}   # x 6 animals in parallel = 108 processes (user 2026-10-08: ~100 cores)
ANIMALS=${ANIMALS:-"SF07 SF08 SF09 SF10 SF11 SF12"}
REDO=${REDO:-}
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mkdir -p "$OUT"
cd "$REPO/ephys" || exit 1
echo "start $(date -Is)  repo $(cat ../.git_commit 2>/dev/null || echo unknown)  animals $ANIMALS  workers/animal $WORKERS_PER_ANIMAL  out $OUT"
"$PY" swr_detect.py --selftest || exit 1
cp "$REPO/ephys/configs/swr_channels_2026c.yaml" "$OUT/swr_channels_2026c.yaml"
cat > "$OUT/README_swr.txt" <<TXT
Automatic sharp-wave ripple events, cohort 3 (2026c), one folder per session: <SFxx>/<session>/
  <session>.swr_events.csv/.npz  events: start_s, stop_s, peak_s (session seconds; sample k <-> k/1250 s as in DetectSWR),
                                 duration_ms, amplitude, frequency_hz, SwMax_z / RipMax_z (DetectSWR local z = strength),
                                 state + imu_emg at the peak second (final 1-s sleep states), env_ratio_<noise|shankN>
                                 (80-250 Hz envelope at the peak / session median), n_shanks_ripple (shanks with ratio >= 2),
                                 emg_lfp + theta_delta_log (+-0.5 s), flags x_rem / x_theta / x_moving / x_emg_lfp and
                                 excluded (= the block's exclude_flags: REM + theta everywhere, + movement + LFP-EMG where
                                 the probe has no sharp-wave reversal). USE excluded == False; all rows are kept.
  <session>.SWR.evt              Neuroscope events (ms from the first sample), all events
  <session>.swr_summary.json     channels, boundary (block reference), thresholds, counts, rates per state (all / kept),
                                 own-fit selected fraction and NREM amplitude ratio to the block reference (drift checks)
  <session>.swr_qc.png           candidate scatter + events per 10 min
Method: ephys/swr_auto.py docstring; channels + reference sessions: swr_channels_2026c.yaml (copied here; all blocks
confirmed by the user 2026-10-08; SF12 09-09 18:47 -> 09-10 08:35 skipped). Downstream exclusions still to apply: user
noise sessions, SF12_contact_failing, valid_until, SF11 = cortex (negative control).
Made by ephys/server/run_swr.sh, repo commit $(cat ../.git_commit 2>/dev/null || echo unknown), $(date -Is).
TXT
# all animals at once, then ONE verified copy to storage
export PY LFP INPUTS OUT ANIMALS REDO WORKERS_PER_ANIMAL
PART=swr bash server/run_then_store.sh bash server/swr_all_animals.sh
rc=$?
echo "end $(date -Is)  sessions: $(find "$OUT" -name '*.swr_summary.json' | wc -l)  errors: $(ls "$OUT/_errors" 2>/dev/null | wc -l)"
exit $rc
