#!/bin/bash
# All animals of cohort 2026c in parallel (called by run_swr.sh through run_then_store.sh): one ephys/swr_auto.py per
# animal (its block references run first), $WORKERS_PER_ANIMAL processes each; per-animal logs in $LOGS/swr_<animal>_<ts>.log.
# Exits non-zero if any animal failed, so run_then_store.sh copies nothing.
set -u
: "${PY:?}" "${LFP:?}" "${INPUTS:?}" "${OUT:?}"
LOGS=${LOGS:-/workdir/hc997/logs}
WORKERS_PER_ANIMAL=${WORKERS_PER_ANIMAL:-18}
ANIMALS=${ANIMALS:-"SF07 SF08 SF09 SF10 SF11 SF12"}
ts=$(date +%Y%m%d_%H%M%S)
pids=()
for A in $ANIMALS; do
  "$PY" swr_auto.py --animal "$A" --all --min-minutes 10 --lfp-root "$LFP" --states-root "$INPUTS/states_1s_final" \
      --out "$OUT" --workers "$WORKERS_PER_ANIMAL" ${REDO:+--redo} > "$LOGS/swr_${A}_${ts}.log" 2>&1 &
  pids+=($!)
  echo "[$(date +%F' '%T)] started $A (pid $!, log $LOGS/swr_${A}_${ts}.log)"
done
rc=0
for i in "${!pids[@]}"; do
  if wait "${pids[$i]}"; then echo "[$(date +%F' '%T)] done ${pids[$i]}"; else echo "[$(date +%F' '%T)] FAILED ${pids[$i]}"; rc=1; fi
done
exit $rc
