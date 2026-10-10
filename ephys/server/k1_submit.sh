#!/bin/bash
# Submit the Kilosort1 production queue (plan implementation_plan/2026-10-09-k1-block-sorting.md):
#   1. the block list = the blocks of the block table with fm64 == False (FM65), in time order (or BLOCKS=<file>);
#   2. run_k1_queue.sh as one Slurm array, MAXPAR (default 6) at a time = 3 per GPU;
#   3. after the array (afterany): k1_queue_check.py through run_then_store.sh, i.e. the verified copy of part sort_k1
#      to storage runs only when every block of the list has a finished sort.
# Run from the deployed per-commit checkout on the server:  bash ephys/server/k1_submit.sh
set -u
REPO=$(cd "$(dirname "$0")/../.." && pwd)
PY=${PY:-/home/hc997/src/PreprocessPipeline/.venv/bin/python}
Q=/workdir/hc997/ephys_2026c/sort_k1/_queue
mkdir -p "$Q" /workdir/hc997/logs
LIST=${BLOCKS:-$Q/blocks_fm65_$(date +%Y%m%d_%H%M%S).txt}
if [ -z "${BLOCKS:-}" ]; then
  "$PY" - "$REPO/results/2026c/ephys_spikes/reports/ephys_spikes_k1_blocks_2026c.csv" > "$LIST" <<'PYEOF'
import sys
import pandas as pd
bt = pd.read_csv(sys.argv[1], parse_dates=["start"])
bt = bt[bt.fm64.astype(str) != "True"].sort_values("start")
print("\n".join(bt.block))
PYEOF
fi
N=$(grep -c . "$LIST")
echo "blocks: $N  list: $LIST  repo: $REPO"
export K1_REPO=$REPO
A=$(sbatch --parsable --array=0-$((N - 1))%${MAXPAR:-6} "$REPO/ephys/server/run_k1_queue.sh" "$LIST") || exit 1
echo "array job $A"
S=$(sbatch --parsable --dependency=afterany:$A --job-name=k1store --cpus-per-task=8 --mem=16G --time=12:00:00 \
    --output=/workdir/hc997/logs/k1store_%j.log \
    --wrap "PART=sort_k1 bash $REPO/ephys/server/run_then_store.sh $PY $REPO/ephys/server/k1_queue_check.py $LIST") || exit 1
echo "storage job $S (after the array)"
