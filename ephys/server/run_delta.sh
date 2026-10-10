#!/bin/bash
# Delta waves (cortical DOWN states) for every SF07-SF12 session on BioHPC cbsuruiz01 (ephys/delta_auto.py: exact port of
# the lab's detect_delta_waves.m on the configured top column + per-event DOWN-state check with raw multi-unit
# crossings), from the storage LFP + raw WILD cards; animals in parallel; then the verified copy to storage
# 3rd_rat/analysis/delta/ (run_then_store.sh, PART=delta).
# Validated locally first (2026-10-08/09): replay of 9 lab sessions (recall 1.000 at +-10 ms, <= 2 extras); six local
# SF07 / SF11 sessions = the reference for the server spot check (D:/Field2026_analysis_out/2026c/delta_auto_local).
# Needs on the workdir: $INPUTS/states_1s_final/<SFxx>/<session>.states.npz (the FINAL 1-s sleep states; the SWR run's
# inputs are reused).
#
# Launch from the analysis PC:
#   ssh gpu 'REPO=~/src/Field2026_Social_analysis_<commit> nohup bash ~/src/Field2026_Social_analysis_<commit>/ephys/server/run_delta.sh \
#       > /workdir/hc997/logs/delta_$(date +%Y%m%d_%H%M%S).log 2>&1 &'
set -u
REPO=${REPO:-$HOME/src/Field2026_Social_analysis}
PY=${PY:-$HOME/src/PreprocessPipeline/.venv/bin/python}
LFP=${LFP:-/fs/cbsuruizfs1/storage/hc997/SocialFieldRat2026/3rd_rat/analysis/lfp}
RAW=${RAW:-/fs/cbsuruizfs1/storage/hc997/SocialFieldRat2026/3rd_rat/WILD}
INPUTS=${INPUTS:-/workdir/hc997/ephys_2026c/swr_inputs}
OUT=${OUT:-/workdir/hc997/ephys_2026c/delta}
LOGS=${LOGS:-/workdir/hc997/logs}
MUA_WORKERS=${MUA_WORKERS:-24}   # per animal; animals run in parallel
ANIMALS=${ANIMALS:-"SF07 SF11"}
REDO=${REDO:-}
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mkdir -p "$OUT" "$LOGS"
cd "$REPO/ephys" || exit 1
echo "start $(date -Is)  repo $(cat ../.git_commit 2>/dev/null || echo unknown)  animals $ANIMALS  mua workers/animal $MUA_WORKERS  out $OUT"
"$PY" delta_detect.py --selftest || exit 1
cp "$REPO/ephys/configs/delta_channels_2026c.yaml" "$OUT/delta_channels_2026c.yaml"
cat > "$OUT/README_delta.txt" <<TXT
Delta waves (cortical DOWN states), cohort 3 (2026c), SF07-SF12, one folder per session: <SFxx>/<session>/
  <session>.deltaWaves.events.mat  the lab's struct (as detect_delta_waves.m writes it): timestamps [start stop] (s),
                                   peaks, amplitude (z peak - z end), amplitudeUnits, values [z start peak end],
                                   detectorinfo; plus verified (1 = multi-unit firing at the peak <= 0.5 x the -1..-0.4 s
                                   baseline), testable, mua_ratio, mua_p, mua_k_peak, mua_k_pre, after_use_until.
                                   ALL detected events are kept: USE verified == 1 AND after_use_until == 0.
  <session>.delta_events.csv       the same, one row per event (session seconds; LFP sample k <-> k/1250 s)
  <session>.DEL.evt                Neuroscope events: "delta start/peak/stop" = verified, "delta? ..." = not verified
  <session>.delta_summary.json     channel, NREM minutes, counts, rates per NREM minute (all / verified), MUA sites and
                                   their rates / delta-peak ratios, session context (use_until, info, sleep verdict)
  <session>.mua_nrem.npz           multi-unit threshold crossings of all 64 channels over all NREM (reusable;
                                   ephys/mua_nrem.py docstring)
Method: ephys/delta_auto.py docstring. Detection = exact Python port of neurocode FindDeltaWaves.m + detect_delta_waves.m
(NREM from the final 1-s states, CleanLFP [6 10], z peak-end > 3, no EMG gate), validated by replay on 9 lab sessions.
Channels (delta_channels_2026c.yaml, copied here; top sites, user 2026-10-08/09/10): SF07 col 55, SF11 col 11 (run 2026-10-09);
SF08 col 20, SF09 col 21, SF10 col 9, SF12 col 11 (run 2026-10-10).
The DOWN-state check replaces verify_firing's sorted units (no sorting): spikes within +-50 ms of the peak vs -1..-0.4 s
over the live sites with >= 1 Hz whose firing does not rise at the delta peaks; verified = ratio <= 0.5 (user 2026-10-09).
SF07's and SF12's top sites carry no units: their check uses deeper spiking sites (weaker); SF09 sits low (user: may not
yield much); SF10's top sites have few units. Read results/2026c/ephys_spikes/reports/ephys_spikes_delta_sessions_2026c.md. FM64 sessions (before the 09-01 evening round) have no MUA check (testable = 0).
Downstream: user 'noise' sleep sessions, SF11 valid_until 09-07 06:10 (after_use_until), probe-advance settle windows (info).
Made by ephys/server/run_delta.sh, repo commit $(cat ../.git_commit 2>/dev/null || echo unknown), $(date -Is).
TXT
RUNNER="$LOGS/delta_run_animals_$$.sh"   # helper outside OUT (not copied to storage)
cat > "$RUNNER" <<'SH'
#!/bin/bash
set -u
ts=$(date +%Y%m%d_%H%M%S); pids=(); rc=0
for A in $ANIMALS; do
  "$PY" delta_auto.py --animal "$A" --all --min-minutes 10 --lfp-root "$LFP" --raw-root "$RAW" \
      --states-root "$INPUTS/states_1s_final" --out "$OUT" --mua-workers "$MUA_WORKERS" ${REDO:+--redo} \
      > "$LOGS/delta_${A}_${ts}.log" 2>&1 &
  pids+=($!); echo "[$(date +%F' '%T)] started $A (pid $!, log $LOGS/delta_${A}_${ts}.log)"
done
for p in "${pids[@]}"; do if wait "$p"; then echo "[$(date +%F' '%T)] done $p"; else echo "[$(date +%F' '%T)] FAILED $p"; rc=1; fi; done
exit $rc
SH
export PY LFP RAW INPUTS OUT LOGS ANIMALS REDO MUA_WORKERS
PART=delta bash server/run_then_store.sh bash "$RUNNER"
rc=$?
echo "end $(date -Is)  sessions: $(find "$OUT" -name '*.delta_summary.json' | wc -l)  errors: $(ls "$OUT/_errors" 2>/dev/null | wc -l)"
exit $rc
