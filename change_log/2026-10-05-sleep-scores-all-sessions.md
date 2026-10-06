# Sleep scores for every cohort-3 session on BioHPC + review page (2026-10-05)

Follows [2026-10-05-sleep-rem-clean.md](2026-10-05-sleep-rem-clean.md). The user reviewed the pilot figures (SW, theta
and EMG look plausible, REM has high theta and low EMG) and asked for all sessions on the server, plus a page to step
through every `<session>_SSResults.jpg`.

## What changed

- **`ephys/score_sleep.py` batch mode.**
  - `--all --workers N`: resumable, and a failure is written to `<out>/_errors/` without stopping the batch.
  - `--lfp-root / --imu-root / --out-root` and `--report-name`.
  - `--export-imu-bundle`: the compact IMU inputs, 861 MB instead of the 15 GB `make_imu` output. A single loader reads
    either layout.
  - A loop variable that shadowed the report name in `write_summary` is fixed.
- **`ephys/server/run_score_sleep.sh`.** The BioHPC launcher: `imu_nremgate` plus the derived `imu_remclean`, 32 workers,
  BLAS pinned to 1 thread.
- **`ephys/sleep_review.py`.** A local HTML page, one SSResults figure at a time, ordered by animal then start time.
  - Header: start, duration, firmware, state fractions, channels, thresholds, and how much sustained movement is WAKE.
  - Keys: 1 ok / 2 logger noise / 3 bad, plus a note.
  - Marks autosave in the browser and export / import as CSV.
  - The agent does not judge the figures.

## Verification (local first)

- **The server code path, run on this PC** (IMU bundles, 2 workers; SF10 and SF07 night, both variants): states, EMG and
  thresholds are identical to the pilot.
- **Server = PC on SF10** (`9_20260902_083247.835`, both variants):
  - states, thresholds and channels are identical;
  - the SW and theta metrics differ ≤ 2.3e-15 (scipy 1.16.3 vs 1.16.2; same numpy 1.26.4).
  - The server's PreprocessPipeline files are byte-identical to the committed `eb3dad4` (the PC copy differs only in line
    endings).
- **The IMU bundle upload:** MD5 identical for all 203 files.

## Run

- `/workdir/hc997/ephys_2026c/sleep/` on cbsuruiz01. Log: `/workdir/hc997/logs/score_sleep_20261005_224253.log`.
- 38 min with 32 workers.
- **198 of 203 sessions scored (1325 h).** The 5 refusals are the known frozen / invalid IMU sessions: SF07 `11_20260904`,
  `12_20260910` and `9_20260906`, SF11 `13_20260906`, SF12 `14_20260902`. Excluded time is not supported yet.
- Server disk use: ~140 GB beyond the hard-linked LFP.
- **Copied to this PC** (`D:\3rd_rat_spikes\analysis\sleep_server\`, 55 MB): `score_sleep.json` for both variants, the
  `imu_remclean` SSResults figures, `_errors/`. The `.mat` state files stay on the server; fetch them per session to open
  one in `state_editor.py`.
- **Reports:** `results/2026c/ephys_spikes/reports/ephys_spikes_sleep_scores{,_agreement,_errors}_2026c.csv`.
- **Review page:** `D:\3rd_rat_spikes\analysis\sleep_server\review_imu_remclean.html`.

## Descriptive summary (`imu_remclean`; not a quality verdict — that is the user's review)

- **Session lengths:** 26 sessions are < 30 min and 23 are 0.5–2 h. Their per-session thresholds rest on little data.
- **Sustained movement** (runs ≥ 30 s) scored WAKE: median 99.98 %. Three sessions fall below 90 %, all with no REM and a
  low EMG threshold (0.21–0.29):
  - SF07 `4_20260901_074925.529`: 81 %;
  - SF09 `1_20260907_085726.079`: 85 %;
  - SF12 `2_20260909_184027.605`: 64 %.

  Review these first.
- **REM share of sleep** in sessions ≥ 2 h: median 11 % (IQR 6–18 %).
- **Median NREM fraction** in sessions ≥ 2 h, by start time:
  - sessions starting 06–12 h: 0.65;
  - 12–18 h: 0.53;
  - 18–24 h: 0.19;
  - 00–06 h: 0.18.

  This is the expected light / dark pattern.
