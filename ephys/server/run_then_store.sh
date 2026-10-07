#!/bin/bash
# Post-run hook for BioHPC jobs: run a command and, ONLY if it exits 0, copy its workdir output to storage with the
# verified copy (copy_to_storage.sh, PARTS=$PART UPDATE=1: rsync, then paths + sizes + MD5 vs an O_DIRECT read-back,
# VERIFY.txt + MD5SUMS on storage). The workdir is scratch (user rule 2026-10-07: derived data lives on storage), so
# every new server job should end through this hook. Nothing is deleted anywhere; the workdir copy is removed only
# after the user has seen VERIFY.txt RESULT PASS.
#
#   PART=<copy_to_storage part> bash run_then_store.sh <command> [args ...]
#   e.g. PART=audio_levels bash run_then_store.sh "$PY" mic_band_levels.py --root ... --out /workdir/hc997/ephys_2026c/audio_levels
set -u
: "${PART:?set PART to a part known to copy_to_storage.sh (lfp, sleep, audio_levels)}"
HERE=$(cd "$(dirname "$0")" && pwd)
echo "[$(date +%F' '%T)] run: $*"
"$@"
rc=$?
echo "[$(date +%F' '%T)] command exit $rc"
if [ $rc -ne 0 ]; then
  echo "[$(date +%F' '%T)] NOT copied to storage (the command failed); fix and rerun - the copy is resumable"
  exit $rc
fi
echo "[$(date +%F' '%T)] copying part '$PART' to storage (verified)"
PARTS="$PART" UPDATE=1 bash "$HERE/copy_to_storage.sh"
