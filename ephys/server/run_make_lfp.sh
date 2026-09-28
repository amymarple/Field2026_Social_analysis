#!/bin/bash
# LFP for every selected cohort-2026c session on BioHPC cbsuruiz01 (plan phase L1), written to /workdir first.
# Two concurrent session streams (animal groups balanced by hours, ~640 h vs ~733 h), WORKERS sequential read
# streams each (8 measured best on the storage NFS: 524 MB/s cold per session). Resumable: make_lfp skips sessions
# whose .lfp + .lfp.json already exist. When both groups finish, writes an MD5 manifest used to verify the copy to
# storage (…/3rd_rat/analysis/lfp/).
#
# Launch from this PC over the shared SSH connection:
#   ssh -S ~/.ssh/cm-gpu gpu 'nohup bash ~/src/Field2026_Social_analysis/ephys/server/run_make_lfp.sh \
#       > /workdir/hc997/logs/make_lfp_$(date +%Y%m%d_%H%M%S).log 2>&1 &'
set -u
REPO=${REPO:-$HOME/src/Field2026_Social_analysis}
PY=${PY:-$HOME/src/PreprocessPipeline/.venv/bin/python}
RAW=${RAW:-/fs/cbsuruizfs1/storage/hc997/SocialFieldRat2026/3rd_rat/WILD}
OUT=${OUT:-/workdir/hc997/ephys_2026c/lfp}
LOGDIR=${LOGDIR:-/workdir/hc997/logs}
WORKERS=${WORKERS:-8}
mkdir -p "$OUT" "$LOGDIR"
cd "$REPO" || exit 1
echo "start $(date -Is)  repo $(cat .git_commit 2>/dev/null || echo unknown)  out $OUT  workers $WORKERS"
run_group() {  # $1 = group name, rest = animals
  local name=$1; shift
  "$PY" ephys/make_lfp.py --cohort 2026c --animal "$@" --raw-root "$RAW" --out-root "$OUT" --workers "$WORKERS" \
      > "$LOGDIR/make_lfp_group${name}.log" 2>&1
  echo "group $name ($*) exit $? at $(date -Is)"
}
run_group A SF7 SF9 SF11 &
run_group B SF8 SF10 SF12 &
wait
n=$(find "$OUT" -name '*.lfp.json' | wc -l)
partial=$(find "$OUT" -name '*.partial' | wc -l)
echo "outputs: $n sessions, $(du -sh "$OUT" | cut -f1), partial files left: $partial"
( cd "$OUT" && find . -name '*.lfp' -print0 | sort -z | xargs -0 -n 4 -P 8 md5sum ) > "$OUT/lfp_md5.txt"
echo "md5 manifest: $(wc -l < "$OUT/lfp_md5.txt") files -> $OUT/lfp_md5.txt"
echo "done $(date -Is)"
