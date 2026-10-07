#!/bin/bash
# Per-second band levels of the cohort-3 in-house microphones (MIC01, MIC02) and the CH01 / CH02 camera audio, on
# BioHPC cbsuruiz01, from the storage copy of the raw streams; then the verified copy to storage (run_then_store.sh).
# Validated locally first (2026-10-07): one hour each of MIC01, MIC02, CH01 from F:\3rd_rat (selftest PASS).
# Plan: implementation_plan/2026-10-07-sleep-internal-schedule.md section 4 D. Resumable (finished files are skipped).
#
# Launch from the analysis PC over the shared SSH connection:
#   ssh -S ~/.ssh/cm-gpu gpu 'nohup bash ~/src/Field2026_Social_analysis/ephys/server/run_audio_levels.sh \
#       > /workdir/hc997/logs/audio_levels_$(date +%Y%m%d_%H%M%S).log 2>&1 &'
set -u
REPO=${REPO:-$HOME/src/Field2026_Social_analysis}
PY=${PY:-$HOME/src/PreprocessPipeline/.venv/bin/python}
RAW=${RAW:-/fs/cbsuruizfs1/storage/hc997/SocialFieldRat2026/3rd_rat}
OUT=${OUT:-/workdir/hc997/ephys_2026c/audio_levels}
WORKERS=${WORKERS:-24}
STREAMS=${STREAMS:-"MIC01 MIC02 CH01 CH02"}
DATES=${DATES:-"2026-08-30 2026-08-31 2026-09-01 2026-09-02 2026-09-03 2026-09-04 2026-09-05 2026-09-06 2026-09-07 2026-09-08 2026-09-09 2026-09-10 2026-09-11 2026-09-12 2026-09-16 2026-09-17"}
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 FFMPEG=${FFMPEG:-/usr/bin/ffmpeg}
mkdir -p "$OUT"
cd "$REPO/ephys" || exit 1
echo "start $(date -Is)  repo $(cat ../.git_commit 2>/dev/null || echo unknown)  workers $WORKERS  out $OUT"
"$PY" mic_band_levels.py --selftest || exit 1
cat > "$OUT/README_audio_levels.txt" <<EOF
Per-second band levels (dB re full scale) of the cohort-3 in-house UltraMics (MIC01 384 kHz, MIC02 250 kHz; mounted on
the ceiling inside each house, user 2026-10-07; working assignment MIC01 = house_2, MIC02 = house_1, to be confirmed)
and of the CH01 / CH02 camera audio (AAC 16 kHz). One CSV.gz per raw hourly file: <stream>/<raw file stem>.csv.gz,
columns t_pc (field-PC time, 1 s), n_frames, <band>_mean_db, <band>_max_db. Bands: mics b0 50-500 Hz, b1 0.5-4 kHz,
b2 4-20 kHz, b3 20-40 kHz, b4 40-100 kHz; cameras c0 50-500 Hz, c1 0.5-2 kHz, c2 2-8 kHz. extract_log.csv lists every
file (rate, effective rate, timing = stretched | end_anchored). Definitions: ephys/mic_band_levels.py docstring.
Made by ephys/server/run_audio_levels.sh, repo commit $(cat ../.git_commit 2>/dev/null || echo unknown), $(date -Is).
Raw source: $RAW/<date>/<stream>/. Relative levels only; devices are not calibrated to each other.
EOF
PART=audio_levels bash server/run_then_store.sh "$PY" mic_band_levels.py --root "$RAW" --mics $STREAMS --dates $DATES \
    --out "$OUT" --workers "$WORKERS"
echo "end $(date -Is)  files: $(find "$OUT" -name '*.csv.gz' | wc -l)  errors: $(grep -c ',error' "$OUT/extract_log.csv" 2>/dev/null)"
