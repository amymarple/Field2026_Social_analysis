#!/bin/bash
# Copy the cohort-2026c derived ephys (LFP, sleep scores) from the BioHPC workdir to storage, then reconcile byte by byte.
# Storage = /fs/cbsuruizfs1/storage/hc997 = Q:\hc997 on the analysis PC. Never deletes anything (the workdir copies stay
# until the user decides); never writes into an existing destination folder it did not create (marker file).
#
#   part   source (workdir)                           -> destination (storage, $DST = .../3rd_rat/analysis)
#   lfp    $SRC/lfp/                                  -> $DST/lfp/                    all files (incl. lfp_md5.txt)
#          $LOGS/make_lfp*.log                        -> $DST/lfp/logs/
#   sleep  $SRC/sleep/                                -> $DST/sleep/                  all files EXCEPT *.lfp (hard links to lfp/)
#          $SRC/sleep_states_1s/                      -> $DST/sleep/states_1s/
#          $SRC/imu_sleep_bundle/                     -> $DST/sleep/imu_sleep_bundle/ (the scorer's IMU input)
#          $LOGS/score_sleep*.log                     -> $DST/sleep/logs/
#
# Verification per part (written to $DST/<part>/VERIFY.txt; PASS only if all hold):
#   V1 the destination holds exactly the expected relative paths, with identical byte sizes;
#   V2 MD5 of every source file (local workdir disk) == MD5 of the destination file read with O_DIRECT, i.e. bypassing
#      this host's NFS page cache so the bytes come back from the storage server, not from the copy still in RAM;
#   V3 (lfp) every .lfp also matches lfp_md5.txt, the manifest written when the LFP was made (the source is unchanged).
# $DST/<part>/MD5SUMS = the destination checksums (md5sum -c format). Re-running resumes: rsync re-copies differing
# files, then everything is verified again. UPDATE=1 does the same on a folder already verified (adds files the
# workdir gained since; nothing on storage is deleted, so a file removed on the workdir makes V1 fail - by design).
#
# Launch from the analysis PC over the shared SSH connection:
#   ssh -S ~/.ssh/cm-gpu gpu 'nohup bash ~/src/Field2026_Social_analysis/ephys/server/copy_to_storage.sh \
#       > /workdir/hc997/logs/copy_to_storage_$(date +%Y%m%d_%H%M%S).log 2>&1 &'
set -u
SRC=${SRC:-/workdir/hc997/ephys_2026c}
LOGS=${LOGS:-/workdir/hc997/logs}
DST=${DST:-/fs/cbsuruizfs1/storage/hc997/SocialFieldRat2026/3rd_rat/analysis}
JOBS=${JOBS:-8}
PARTS=${PARTS:-"lfp sleep"}
MARK=.copy_to_storage_in_progress
COMMIT=$(cat "$HOME/src/Field2026_Social_analysis/.git_commit" 2>/dev/null || echo unknown)
WORK=$(mktemp -d "$LOGS/copy_to_storage_work_XXXX")
say() { echo "[$(date +%F' '%T)] $*"; }

md5_direct() {   # MD5 read with O_DIRECT (no client page cache); prints "<md5>  <path>"
  local f h
  for f in "$@"; do
    h=$( set -o pipefail; dd if="$f" iflag=direct bs=8M status=none | md5sum | cut -d' ' -f1 ) || h=READ_ERROR
    echo "$h  $f"
  done
}
md5_plain() { md5sum "$@"; }
export -f md5_direct md5_plain

units() {        # one line per copy unit: <source dir>|<destination dir relative to $DST/part>|<exclude glob or ->
  case $1 in
    lfp)   echo "$SRC/lfp||-" ;;
    sleep) echo "$SRC/sleep||*.lfp"; echo "$SRC/sleep_states_1s|states_1s|-"; echo "$SRC/imu_sleep_bundle|imu_sleep_bundle|-"
           for d in "$SRC"/sleep_states_1s_*; do [ -d "$d" ] && echo "$d|states_1s_${d##*/sleep_states_1s_}|-"; done ;;   # e.g. _pass2, _pass2med, _nremgate
  esac
}
log_glob() { case $1 in lfp) echo "make_lfp*.log" ;; sleep) echo "score_sleep*.log" ;; esac; }

list_src() {     # expected destination-relative paths + sizes, sorted
  local part=$1 src rel ex
  while IFS='|' read -r src rel ex; do
    [ -d "$src" ] || { echo "MISSING_SOURCE $src" >&2; continue; }
    ( cd "$src" && if [ "$ex" = "-" ]; then find . -type f -printf '%P\t%s\n'; else find . -type f ! -name "$ex" -printf '%P\t%s\n'; fi ) \
      | awk -v p="$rel" -F'\t' '{ print (p == "" ? $1 : p "/" $1) "\t" $2 }'
  done < <(units "$part")
  ( cd "$LOGS" && find . -maxdepth 1 -type f -name "$(log_glob "$part")" -printf 'logs/%P\t%s\n' )
}
src_path() {     # destination-relative path -> absolute source path
  local part=$1 rel=$2 src urel ex
  case $rel in logs/*) echo "$LOGS/${rel#logs/}"; return ;; esac
  while IFS='|' read -r src urel ex; do
    if [ -n "$urel" ] && [ "${rel%%/*}" = "$urel" ]; then echo "$src/${rel#*/}"; return; fi
  done < <(units "$part")
  while IFS='|' read -r src urel ex; do [ -z "$urel" ] && { echo "$src/$rel"; return; }; done < <(units "$part")
}

ok_all=1
ls "$DST" > /dev/null || { say "storage not reachable: $DST"; exit 1; }
say "start  commit $COMMIT  jobs $JOBS  parts: $PARTS"
df -h "$SRC" "$DST" | sed 's/^/    /'
for part in $PARTS; do
  D="$DST/$part"
  if [ -d "$D" ] && [ ! -e "$D/$MARK" ]; then
    if [ -e "$D/VERIFY.txt" ] && grep -q '^RESULT PASS' "$D/VERIFY.txt"; then
      if [ -z "${UPDATE:-}" ]; then say "$part: already copied and verified - skipped (UPDATE=1 adds new / changed files)"; continue; fi
      say "$part: UPDATE - adding new and changed files to the verified copy, then verifying everything again"
      mv "$D/VERIFY.txt" "$D/VERIFY_previous.txt"
    else
      say "$part: $D exists and was not created by this script - refusing to write into it"; ok_all=0; continue
    fi
  fi
  mkdir -p "$D" && touch "$D/$MARK"
  list_src "$part" | LC_ALL=C sort > "$WORK/$part.expected"
  n=$(wc -l < "$WORK/$part.expected"); bytes=$(awk -F'\t' '{s += $2} END {printf "%.0f", s}' "$WORK/$part.expected")
  say "$part: $n files, $(numfmt --to=iec "$bytes") to copy"
  avail=$(df --output=avail -B1 "$DST" | tail -1)
  if [ "$bytes" -gt "$avail" ]; then say "$part: needs $(numfmt --to=iec "$bytes"), storage has $(numfmt --to=iec "$avail") free - refusing"; ok_all=0; continue; fi

  # ---- copy (one rsync per top-level subfolder of each unit, $JOBS at a time)
  t0=$(date +%s)
  while IFS='|' read -r src rel ex; do
    dst="$D${rel:+/$rel}"; mkdir -p "$dst"
    exopt=(); [ "$ex" != "-" ] && exopt=(--exclude="$ex")
    ( cd "$src" && find . -mindepth 1 -maxdepth 1 -type f -printf '%P\n' ) > "$WORK/top.files"
    [ -s "$WORK/top.files" ] && rsync -rt "${exopt[@]}" --files-from="$WORK/top.files" "$src/" "$dst/" < /dev/null
    for sub in $(cd "$src" && find . -mindepth 1 -maxdepth 1 -type d -printf '%P\n'); do
      while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do wait -n; done
      rsync -rt "${exopt[@]}" "$src/$sub/" "$dst/$sub/" < /dev/null &
    done
  done < <(units "$part")
  mkdir -p "$D/logs"
  ( cd "$LOGS" && find . -maxdepth 1 -type f -name "$(log_glob "$part")" -printf '%P\n' ) > "$WORK/logs.files"
  [ -s "$WORK/logs.files" ] && rsync -rt --files-from="$WORK/logs.files" "$LOGS/" "$D/logs/"
  wait
  t1=$(date +%s); say "$part: copy done in $((t1 - t0)) s"

  # ---- V1: paths + sizes
  ( cd "$D" && find . -type f ! -name "$MARK" ! -name MD5SUMS ! -name VERIFY.txt ! -name VERIFY_previous.txt ! -name README.md -printf '%P\t%s\n' ) \
    | LC_ALL=C sort > "$WORK/$part.found"
  if diff -q "$WORK/$part.expected" "$WORK/$part.found" > /dev/null; then v1=PASS; else v1=FAIL; fi
  diff "$WORK/$part.expected" "$WORK/$part.found" | head -20 > "$WORK/$part.v1diff"

  # ---- V2: source MD5 (local disk) vs destination MD5 read with O_DIRECT
  cut -f1 "$WORK/$part.expected" > "$WORK/$part.rel"
  while read -r rel; do echo "$(src_path "$part" "$rel")"; done < "$WORK/$part.rel" > "$WORK/$part.srcabs"
  xargs -d '\n' -n 16 -P "$JOBS" bash -c 'md5_plain "$@"' _ < "$WORK/$part.srcabs" > "$WORK/$part.srcmd5.raw"
  paste -d'\t' "$WORK/$part.srcabs" "$WORK/$part.rel" > "$WORK/$part.map"
  awk 'NR == FNR { split($0, m, "\t"); rel[m[1]] = m[2]; next } { print substr($0, 1, 32) "  " rel[substr($0, 35)] }' \
    "$WORK/$part.map" "$WORK/$part.srcmd5.raw" | LC_ALL=C sort -k2 > "$WORK/$part.srcmd5"
  ( cd "$D" && xargs -d '\n' -n 16 -P "$JOBS" bash -c 'md5_direct "$@"' _ < "$WORK/$part.rel" ) | LC_ALL=C sort -k2 > "$WORK/$part.dstmd5"
  if diff -q "$WORK/$part.srcmd5" "$WORK/$part.dstmd5" > /dev/null && ! grep -q READ_ERROR "$WORK/$part.dstmd5"; then v2=PASS; else v2=FAIL; fi
  diff "$WORK/$part.srcmd5" "$WORK/$part.dstmd5" | head -20 > "$WORK/$part.v2diff"
  t2=$(date +%s); say "$part: checksums done in $((t2 - t1)) s"

  # ---- V3 (lfp): vs the manifest written when the LFP was made
  v3=n/a
  if [ "$part" = lfp ] && [ -f "$SRC/lfp/lfp_md5.txt" ]; then
    sed 's#  \./#  #' "$SRC/lfp/lfp_md5.txt" | LC_ALL=C sort -k2 > "$WORK/lfp.manifest"
    grep '\.lfp$' "$WORK/lfp.dstmd5" | LC_ALL=C sort -k2 > "$WORK/lfp.dstlfp"
    if diff -q "$WORK/lfp.manifest" "$WORK/lfp.dstlfp" > /dev/null; then v3=PASS; else v3=FAIL; fi
    v3="$v3 ($(wc -l < "$WORK/lfp.manifest") in manifest, $(wc -l < "$WORK/lfp.dstlfp") .lfp copied)"
  fi

  result=PASS; [ "$v1" = PASS ] && [ "$v2" = PASS ] && [ "${v3%% *}" != FAIL ] || { result=FAIL; ok_all=0; }
  cp "$WORK/$part.dstmd5" "$D/MD5SUMS"
  {
    echo "RESULT $result"
    echo "part $part   copied $(date -Is)   by ephys/server/copy_to_storage.sh (commit $COMMIT) on $(hostname)"
    echo "sources: $(units "$part" | cut -d'|' -f1 | tr '\n' ' ') $LOGS/$(log_glob "$part")"
    echo "files $n   bytes $bytes ($(numfmt --to=iec "$bytes"))   copy $((t1 - t0)) s   verify $((t2 - t1)) s"
    echo "V1 paths + sizes identical: $v1"
    echo "V2 MD5 source (local disk) == destination (O_DIRECT read from storage): $v2"
    echo "V3 .lfp == manifest made with the LFP (lfp_md5.txt): $v3"
    [ "$v1" = PASS ] || { echo "--- V1 diff (expected < > found), first 20 lines"; cat "$WORK/$part.v1diff"; }
    [ "$v2" = PASS ] || { echo "--- V2 diff (source < > destination), first 20 lines"; cat "$WORK/$part.v2diff"; }
  } > "$D/VERIFY.txt"
  [ "$result" = PASS ] && rm -f "$D/$MARK"
  say "$part: $result"; sed 's/^/    /' "$D/VERIFY.txt"
done
say "work files: $WORK"
[ $ok_all = 1 ] && say "ALL PASS" || say "NOT ALL PASS"
