#!/bin/bash
# Kilosort1 production queue for cohort 2026c (plan implementation_plan/2026-10-09-k1-block-sorting.md).
# One Slurm array task per block of the block table (ephys/plan_blocks.py). Each task:
#   1. builds <block>.dat from the staged sessions (or read-only from storage) with build_block_dat.py;
#   2. sorts it with run_k1_block.py (lab settings + our patches; the block's failing shanks via --disconnect);
#   3. deletes the block .dat and the staged session copies it used (copies of storage), only after success.
# Output: $OUT/<SFxx>/<block>/ (chanMap.mat, XML, k1_config_used.yaml, k1_run.json incl. cross-shank QC,
# <block>.segments.json, kilosort1/ = Phy). Logs: $LOGS/k1_<block>_<job>.log (the storage part sort_k1 copies k1_*.log).
# GPUs: both (user, 2026-10-10), pinned by array index parity; Slurm does not isolate GPUs (ConstrainDevices=no).
# Storage: after the array, PART=sort_k1 bash run_then_store.sh ... (separate job, see submit below).
#
# Submit with ephys/server/k1_submit.sh (writes the block list, submits this array 6 at a time, then the storage copy).
#SBATCH --job-name=k1q
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=12:00:00
#SBATCH --output=/workdir/hc997/logs/k1q_%A_%a.log
set -u
LIST=$1                                    # one block name per line (the queue order)
REPO=${K1_REPO:?set by k1_submit.sh (under Slurm $0 is the spooled copy)}
PY=${PY:-/home/hc997/src/PreprocessPipeline/.venv/bin/python}
PP=${PP:-/home/hc997/src/PreprocessPipeline_7819d39}
TOOLS=${TOOLS:-/local/workdir/hc997/tools}
MATLAB=${MATLAB:-/local/workdir/hc997/MATLAB/bin/matlab}
BLK=${BLK:-/workdir/hc997/ephys_2026c/k1_blocks}
STAGE=${STAGE:-/workdir/hc997/ephys_2026c/k1_stage}
RAW=${RAW:-/fs/cbsuruizfs1/storage/hc997/SocialFieldRat2026/3rd_rat/WILD}
OUT=${OUT:-/workdir/hc997/ephys_2026c/sort_k1}
LOGS=${LOGS:-/workdir/hc997/logs}
TABLE=$REPO/results/2026c/ephys_spikes/reports/ephys_spikes_k1_blocks_2026c.csv
i=${SLURM_ARRAY_TASK_ID:?run as a Slurm array}
BLOCK=$(sed -n "$((i + 1))p" "$LIST")
[ -n "$BLOCK" ] || { echo "no block for index $i"; exit 1; }
ANIMAL=${BLOCK%%_*}
export CUDA_VISIBLE_DEVICES=$((i % 2))
export MW_CUDA_FORWARD_COMPATIBILITY=1 CUDA_CACHE_MAXSIZE=4294967296 PREPROCESS_RUNTIME_DIR=/local/workdir/hc997/preprocess_runtime
LOG=$LOGS/k1_${BLOCK}_${SLURM_ARRAY_JOB_ID}.log
exec > >(tee -a "$LOG") 2>&1
echo "[$(date +%F' '%T)] block $BLOCK animal $ANIMAL gpu $CUDA_VISIBLE_DEVICES host $(hostname) repo $REPO"
DEST=$OUT/$ANIMAL/$BLOCK
if [ -f "$DEST/k1_run.json" ] && [ -f "$DEST/kilosort1/spike_times.npy" ]; then echo "already sorted - skip"; exit 0; fi
DISC=$("$PY" - "$TABLE" "$BLOCK" <<'EOF'
import csv, sys
r = next(r for r in csv.DictReader(open(sys.argv[1], newline="")) if r["block"] == sys.argv[2])
print(r["disconnect"])
EOF
)
cd "$REPO" || exit 1
"$PY" ephys/server/build_block_dat.py --blocks "$TABLE" --block "$BLOCK" --out-root "$BLK" --stage-root "$STAGE" --raw-root "$RAW" || exit 2
"$PY" ephys/run_k1_block.py --animal "$ANIMAL" --dat "$BLK/$BLOCK/$BLOCK.dat" --out "$DEST" \
    --pipeline-root "$PP" --tools-root "$TOOLS" --matlab "$MATLAB" ${DISC:+--disconnect $DISC}
rc=$?
cp "$BLK/$BLOCK/$BLOCK.segments.json" "$DEST/" 2>/dev/null
if [ $rc -eq 0 ] && [ -f "$DEST/kilosort1/spike_times.npy" ]; then
  # free the working disk: the block .dat and the staged copies of its sessions (all are copies of storage)
  for s in $("$PY" -c "import json,sys; print(' '.join(x['session'] for x in json.load(open(sys.argv[1]))['segments']))" "$DEST/$BLOCK.segments.json"); do
    rm -f "$STAGE/$ANIMAL/$s/amplifier.dat"
  done
  rm -f "$BLK/$BLOCK/$BLOCK.dat"
  echo "[$(date +%F' '%T)] done $BLOCK; freed block .dat + staged sessions; /workdir free $(df -h --output=avail /workdir | tail -1)"
else
  echo "[$(date +%F' '%T)] FAILED $BLOCK (exit $rc); block .dat kept for a rerun"
fi
exit $rc
