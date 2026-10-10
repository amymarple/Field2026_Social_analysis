# Electrode movement from the LFP (cohort 2026c): per-session laminar profiles and within-session ripple trends

Plan (before computing): [2026-10-09-swr-session-drift.md](../../../../implementation_plan/2026-10-09-swr-session-drift.md). Driver `ephys/swr_session_drift.py`; run `D:\Field2026_analysis_out\2026c\swr_session_drift_20261009_1942`. Requested by the spike-sorting session.

## (a) Laminar profile vs the block reference

161 non-reference sessions scanned (1-h most-NREM window).
- **Movement candidates vs the block reference:** 40.
- **vs the previous session of the block** (the battery-round step): 5.

Per block (sessions in time order; 'stable from' = the first session after the last candidate):

| animal | block | sessions | candidates | first candidate | last candidate | stable from | min r SPW | min r ratio |
|---|---|---:|---:|---|---|---|---:|---:|
| SF07 | block 1 | 16 | 0 | – | – | 2026-08-31 18:59:04 | 0.96 | -0.84 |
| SF08 | block 1 | 25 | 18 | 2026-08-31 19:02:29 | 2026-09-06 07:59:27 | 2026-09-06 19:43:33 | 0.03 | 0.59 |
| SF09 | block 1 | 29 | 0 | – | – | 2026-08-31 19:08:34 | 0.96 | 0.65 |
| SF10 | block 1 | 31 | 0 | – | – | 2026-08-31 19:10:45 | 0.67 | 0.84 |
| SF11 | block 1a | 9 | 3 | 2026-09-01 00:29:06 | 2026-09-01 23:24:54 | 2026-09-02 06:34:58 | 0.78 | 0.95 |
| SF12 | block 1 | 22 | 16 | 2026-08-31 19:16:13 | 2026-09-05 19:02:40 | 2026-09-06 19:55:02 | -0.58 | 0.43 |
| SF11 | block 1b | 5 | 0 | – | – | 2026-09-02 19:08:52 | 0.97 | 0.91 |
| SF11 | block 2 | 2 | 0 | – | – | 2026-09-04 13:56:50 | 0.97 | 0.78 |
| SF07 | block 2 | 1 | 0 | – | – | 2026-09-05 09:33:10 | 0.97 | 0.90 |
| SF07 | block 3 | 2 | 0 | – | – | 2026-09-05 13:31:18 | 0.99 | 0.94 |
| SF11 | block 3 | 2 | 1 | 2026-09-05 18:59:31 | 2026-09-05 18:59:31 | – | 0.75 | 0.52 |
| SF07 | block 4 | 10 | 0 | – | – | 2026-09-06 13:29:42 | 0.85 | 0.83 |
| SF12 | block 2 | 1 | 0 | – | – | 2026-09-09 18:47:50 | nan | nan |
| SF08 | block 2 | 4 | 0 | – | – | 2026-09-09 18:50:36 | 0.92 | 0.85 |
| SF12 | block 3 | 2 | 2 | 2026-09-10 21:05:18 | 2026-09-11 19:24:28 | – | 0.19 | 0.46 |

All sessions:

| animal | block | session | tier | r ratio | r SPW | shift ratio (median, sites) | shift SPW | candidate | vs previous: r ratio / r SPW | candidate (prev) |
|---|---|---|---|---:|---:|---:|---:|:---:|---|:---:|
| SF07 | block 1 | 1_20260831_185904.795 | validated | 0.94 | 0.99 | +0.0 | -1.0 | no | – | no |
| SF07 | block 1 | 2_20260901_002100.939 | validated | 0.95 | 1.00 | +0.0 | +0.0 | no | 1.00 / 0.99 | no |
| SF07 | block 1 | 3_20260901_054126.846 | validated | -0.84 | 1.00 | -3.0 | +0.0 | no | -0.92 / 1.00 | no |
| SF07 | block 1 | 5_20260901_075052.875 | validated | 0.94 | 1.00 | +0.5 | +0.0 | no | -0.88 / 1.00 | no |
| SF07 | block 1 | 6_20260901_125442.165 | validated | 0.92 | 1.00 | +1.5 | +0.0 | no | 0.95 / 1.00 | no |
| SF07 | block 1 | 7_20260901_171210.814 | validated | 0.93 | 1.00 | +2.0 | +0.0 | no | 0.96 / 1.00 | no |
| SF07 | block 1 | 9_20260901_192912.215 | validated | 0.92 | 0.98 | +0.0 | +0.0 | no | 0.94 / 0.97 | no |
| SF07 | block 1 | 10_20260901_234332.691 | validated | 0.91 | 1.00 | +0.5 | +0.0 | no | 0.86 / 0.98 | no |
| SF07 | block 1 | 11_20260902_062241.295 | validated | 0.96 | 1.00 | +0.0 | +0.0 | no | 0.95 / 1.00 | no |
| SF07 | block 1 | 16_20260902_165524.033 | validated | 0.94 | 1.00 | +0.0 | +0.0 | no | 0.94 / 1.00 | no |
| SF07 | block 1 | 3_20260902_190047.109 | validated | 0.93 | 1.00 | +0.0 | +0.0 | no | 0.92 / 1.00 | no |
| SF07 | block 1 | 4_20260903_001558.656 | validated | 0.91 | 1.00 | +1.0 | +0.0 | no | 0.97 / 1.00 | no |
| SF07 | block 1 | 2_20260903_075114.355 | validated | 0.94 | 1.00 | +1.0 | +0.0 | no | 0.95 / 1.00 | no |
| SF07 | block 1 | 3_20260903_164808.815 | validated | 0.94 | 1.00 | +1.0 | +0.0 | no | 0.98 / 1.00 | no |
| SF07 | block 1 | 6_20260903_175144.375 | validated | 0.86 | 0.96 | +0.0 | -1.0 | no | 0.91 / 0.96 | no |
| SF07 | block 1 | 8_20260904_080936.435 | check | 0.87 | 0.99 | +1.0 | +0.0 | no | 0.96 / 0.97 | no |
| SF08 | block 1 | 1_20260831_190229.919 | check | 0.78 | 0.08 | -2.5 | -2.0 | **yes** | – | no |
| SF08 | block 1 | 2_20260901_002327.839 | check | 0.77 | 0.05 | -3.0 | -2.0 | **yes** | 0.98 / 1.00 | no |
| SF08 | block 1 | 1_20260901_075304.063 | check | 0.76 | 0.09 | -3.0 | -2.0 | **yes** | 0.98 / 1.00 | no |
| SF08 | block 1 | 2_20260901_125621.840 | check | 0.77 | 0.06 | -3.0 | -2.0 | **yes** | 1.00 / 1.00 | no |
| SF08 | block 1 | 4_20260901_152951.697 | check | 0.76 | 0.08 | -3.0 | -2.0 | **yes** | 0.98 / 1.00 | no |
| SF08 | block 1 | 5_20260901_171339.094 | good | 0.79 | 0.07 | -3.0 | -2.0 | **yes** | 0.99 / 1.00 | no |
| SF08 | block 1 | 7_20260901_193109.475 | check | 0.83 | 0.03 | -2.5 | -2.0 | **yes** | 0.98 / 1.00 | no |
| SF08 | block 1 | 8_20260901_233239.239 | check | 0.79 | 0.07 | -3.0 | -2.0 | **yes** | 0.98 / 1.00 | no |
| SF08 | block 1 | 9_20260902_062432.012 | check | 0.79 | 0.11 | -2.5 | -2.0 | **yes** | 0.99 / 0.99 | no |
| SF08 | block 1 | 13_20260902_082748.094 | check | 0.78 | 0.08 | -2.5 | -2.0 | **yes** | 0.98 / 1.00 | no |
| SF08 | block 1 | 17_20260902_190241.916 | check | 0.83 | 0.15 | -3.0 | -2.0 | **yes** | 0.97 / 0.99 | no |
| SF08 | block 1 | 18_20260903_060030.122 | check | 0.83 | 0.31 | -1.5 | -2.0 | **yes** | 0.98 / 0.97 | no |
| SF08 | block 1 | 2_20260903_075352.907 | check | 0.83 | 0.29 | -3.0 | -2.0 | **yes** | 0.99 / 0.99 | no |
| SF08 | block 1 | 3_20260903_160306.510 | good | 0.87 | 0.26 | -2.5 | -2.0 | **yes** | 0.97 / 1.00 | no |
| SF08 | block 1 | 2_20260903_175453.625 | good | 0.90 | 0.37 | -1.5 | -1.5 | **yes** | 0.98 / 0.97 | no |
| SF08 | block 1 | 4_20260904_081205.535 | good | 0.90 | 0.33 | -2.0 | -1.5 | **yes** | 0.99 / 0.99 | no |
| SF08 | block 1 | 7_20260904_202056.765 | good | 0.94 | 0.59 | -0.5 | -1.5 | **yes** | 0.97 / 0.94 | no |
| SF08 | block 1 | 2_20260905_093534.819 | good | 0.92 | 0.57 | +0.0 | -1.5 | no | 0.98 / 0.99 | no |
| SF08 | block 1 | 2_20260905_185104.563 | good | 0.94 | 0.73 | +0.0 | -1.5 | no | 0.96 / 0.96 | no |
| SF08 | block 1 | 6_20260906_075927.555 | good | 0.59 | 0.65 | -1.5 | -1.5 | **yes** | 0.60 / 0.85 | no |
| SF08 | block 1 | 9_20260906_194333.465 | good | 0.98 | 0.94 | +0.0 | +0.0 | no | 0.61 / 0.77 | **yes** |
| SF08 | block 1 | 2_20260907_085534.719 | good | 0.97 | 0.95 | +0.0 | -0.5 | no | 0.97 / 0.99 | no |
| SF08 | block 1 | 2_20260907_175113.385 | good | 0.98 | 0.94 | +0.0 | -0.5 | no | 0.98 / 0.98 | no |
| SF08 | block 1 | 8_20260908_193958.035 | good | 0.97 | 0.93 | +0.0 | +0.0 | no | 0.97 / 0.93 | no |
| SF08 | block 1 | 2_20260909_090608.006 | good | 0.96 | 0.95 | +0.0 | +0.0 | no | 0.97 / 0.99 | no |
| SF09 | block 1 | 3_20260831_190834.640 | validated | 0.65 | 0.96 | +0.0 | +0.0 | no | – | no |
| SF09 | block 1 | 4_20260901_002514.385 | validated | 0.82 | 0.98 | +0.0 | +0.0 | no | 0.95 / 1.00 | no |
| SF09 | block 1 | 1_20260901_075532.964 | validated | 0.88 | 0.98 | +0.0 | +0.0 | no | 0.98 / 1.00 | no |
| SF09 | block 1 | 2_20260901_125743.131 | validated | 0.93 | 0.99 | +0.0 | +0.0 | no | 0.99 / 1.00 | no |
| SF09 | block 1 | 3_20260901_171502.588 | validated | 0.92 | 0.98 | +0.0 | +0.0 | no | 0.99 / 1.00 | no |
| SF09 | block 1 | 5_20260901_193330.365 | validated | 0.91 | 0.99 | +0.0 | +0.0 | no | 0.98 / 1.00 | no |
| SF09 | block 1 | 6_20260901_232245.983 | validated | 0.87 | 0.98 | +0.0 | +0.0 | no | 0.99 / 1.00 | no |
| SF09 | block 1 | 7_20260902_062601.722 | validated | 0.85 | 0.97 | +0.0 | +0.0 | no | 0.99 / 1.00 | no |
| SF09 | block 1 | 10_20260902_083015.335 | validated | 0.88 | 0.98 | +0.0 | +0.0 | no | 0.99 / 0.99 | no |
| SF09 | block 1 | 11_20260902_165826.634 | validated | 0.91 | 0.99 | +0.0 | +0.0 | no | 0.99 / 1.00 | no |
| SF09 | block 1 | 15_20260902_190508.575 | validated | 0.86 | 0.99 | +0.0 | +0.0 | no | 0.99 / 1.00 | no |
| SF09 | block 1 | 16_20260903_001828.515 | validated | 0.96 | 0.99 | +0.0 | +0.0 | no | 0.92 / 1.00 | no |
| SF09 | block 1 | 2_20260903_075655.297 | validated | 0.92 | 0.99 | +0.0 | +0.0 | no | 0.96 / 1.00 | no |
| SF09 | block 1 | 3_20260903_175840.384 | validated | 0.94 | 0.98 | +0.0 | +0.0 | no | 0.94 / 0.99 | no |
| SF09 | block 1 | 5_20260904_081426.496 | validated | 0.94 | 1.00 | +0.0 | +0.0 | no | 0.95 / 0.99 | no |
| SF09 | block 1 | 8_20260904_202324.405 | validated | 0.93 | 0.98 | +0.0 | +0.0 | no | 0.95 / 0.98 | no |
| SF09 | block 1 | 3_20260905_094705.608 | validated | 0.94 | 0.99 | +0.0 | +0.0 | no | 0.95 / 0.99 | no |
| SF09 | block 1 | 3_20260905_185422.206 | validated | 0.95 | 0.98 | +0.0 | +1.0 | no | 0.88 / 0.98 | no |
| SF09 | block 1 | 7_20260906_080216.656 | validated | 0.96 | 0.99 | +0.0 | +0.0 | no | 0.95 / 0.99 | no |
| SF09 | block 1 | 11_20260906_194634.836 | check | 0.86 | 0.97 | +0.0 | +0.0 | no | 0.82 / 0.98 | no |
| SF09 | block 1 | 2_20260907_085841.028 | validated | 0.97 | 0.99 | +0.0 | +0.0 | no | 0.86 / 0.99 | no |
| SF09 | block 1 | 3_20260907_175435.676 | validated | 0.96 | 1.00 | +0.0 | +0.0 | no | 0.98 / 0.99 | no |
| SF09 | block 1 | 9_20260908_194312.545 | validated | 0.99 | 1.00 | +0.0 | +0.0 | no | 0.99 / 1.00 | no |
| SF09 | block 1 | 2_20260909_090835.027 | validated | 0.96 | 1.00 | +0.0 | +0.0 | no | 0.95 / 1.00 | no |
| SF09 | block 1 | 2_20260909_184248.375 | check | 0.96 | 0.99 | +0.0 | +0.0 | no | 0.97 / 0.99 | no |
| SF09 | block 1 | 6_20260910_082858.156 | validated | 0.95 | 1.00 | +0.0 | +0.0 | no | 0.92 / 1.00 | no |
| SF09 | block 1 | 15_20260910_204912.017 | validated | 0.94 | 1.00 | +0.0 | +0.0 | no | 0.88 / 1.00 | no |
| SF09 | block 1 | 2_20260911_092224.167 | validated | 0.96 | 1.00 | +0.0 | +0.0 | no | 0.99 / 1.00 | no |
| SF09 | block 1 | 17_20260911_191947.524 | validated | 0.88 | 0.99 | +0.0 | +0.0 | no | 0.96 / 0.99 | no |
| SF10 | block 1 | 1_20260831_191045.259 | validated | 0.93 | 0.95 | +0.0 | +0.0 | no | – | no |
| SF10 | block 1 | 2_20260831_195630.973 | validated | 0.96 | 0.95 | +0.0 | +0.0 | no | 0.97 / 1.00 | no |
| SF10 | block 1 | 4_20260901_002730.117 | validated | 0.98 | 0.99 | +0.0 | +0.0 | no | 0.99 / 0.98 | no |
| SF10 | block 1 | 1_20260901_080143.036 | validated | 0.95 | 0.95 | +0.0 | +0.0 | no | 0.98 / 0.98 | no |
| SF10 | block 1 | 2_20260901_125856.163 | validated | 0.98 | 0.99 | +0.0 | +0.0 | no | 0.98 / 0.97 | no |
| SF10 | block 1 | 3_20260901_171620.845 | validated | 0.98 | 0.99 | +0.0 | +0.0 | no | 1.00 / 1.00 | no |
| SF10 | block 1 | 5_20260901_193554.435 | validated | 0.96 | 0.97 | +0.0 | +0.0 | no | 0.97 / 0.98 | no |
| SF10 | block 1 | 6_20260901_233920.182 | validated | 0.95 | 0.92 | +0.0 | +0.0 | no | 0.98 / 0.99 | no |
| SF10 | block 1 | 9_20260902_083247.835 | validated | 0.91 | 0.94 | +0.0 | +0.0 | no | 0.97 / 0.99 | no |
| SF10 | block 1 | 10_20260902_170101.421 | validated | 0.98 | 0.99 | +0.0 | +0.0 | no | 0.92 / 0.95 | no |
| SF10 | block 1 | 13_20260902_190711.525 | validated | 0.96 | 0.97 | +0.0 | +0.0 | no | 0.97 / 0.97 | no |
| SF10 | block 1 | 14_20260903_002530.902 | validated | 0.94 | 0.94 | +0.0 | +0.0 | no | 0.99 / 0.99 | no |
| SF10 | block 1 | 15_20260903_055614.833 | check | 0.92 | 0.92 | +0.0 | +0.0 | no | 0.98 / 0.98 | no |
| SF10 | block 1 | 2_20260903_075920.109 | validated | 0.97 | 0.99 | +0.0 | +0.0 | no | 0.97 / 0.95 | no |
| SF10 | block 1 | 2_20260903_180222.843 | validated | 0.95 | 0.95 | +0.0 | +0.0 | no | 0.97 / 0.98 | no |
| SF10 | block 1 | 5_20260904_081730.895 | validated | 0.98 | 0.99 | +0.0 | +0.0 | no | 0.98 / 0.97 | no |
| SF10 | block 1 | 9_20260904_202620.386 | validated | 0.98 | 0.99 | +0.0 | +0.0 | no | 0.99 / 1.00 | no |
| SF10 | block 1 | 7_20260905_093927.479 | validated | 0.98 | 0.99 | +0.0 | +0.0 | no | 0.98 / 0.99 | no |
| SF10 | block 1 | 2_20260905_185709.365 | validated | 0.96 | 0.91 | +0.0 | +0.0 | no | 0.96 / 0.93 | no |
| SF10 | block 1 | 3_20260906_055804.599 | check | 0.96 | 0.93 | +0.0 | +0.0 | no | 0.97 / 0.99 | no |
| SF10 | block 1 | 9_20260906_194921.983 | validated | 0.97 | 0.98 | +0.0 | +0.0 | no | 0.97 / 0.98 | no |
| SF10 | block 1 | 4_20260907_090135.869 | validated | 0.99 | 0.99 | +0.0 | +0.0 | no | 0.98 / 0.99 | no |
| SF10 | block 1 | 5_20260907_175744.885 | validated | 0.97 | 0.98 | +0.0 | +0.0 | no | 0.97 / 0.96 | no |
| SF10 | block 1 | 8_20260908_072352.245 | validated | 0.98 | 0.98 | +0.0 | +0.0 | no | 0.94 / 0.94 | no |
| SF10 | block 1 | 12_20260908_194550.363 | check | 0.98 | 0.98 | +0.0 | +0.0 | no | 0.99 / 0.99 | no |
| SF10 | block 1 | 2_20260909_091105.736 | validated | 0.96 | 0.97 | +0.0 | +0.0 | no | 0.95 / 0.97 | no |
| SF10 | block 1 | 2_20260909_184517.395 | validated | 0.90 | 0.91 | +0.0 | +1.0 | no | 0.90 / 0.92 | no |
| SF10 | block 1 | 5_20260910_083157.853 | validated | 0.94 | 0.96 | +0.0 | +0.0 | no | 0.94 / 0.96 | no |
| SF10 | block 1 | 9_20260910_205611.775 | validated | 0.85 | 0.86 | +0.0 | +1.0 | no | 0.93 / 0.95 | no |
| SF10 | block 1 | 2_20260911_092441.104 | validated | 0.94 | 0.95 | +0.0 | +1.0 | no | 0.88 / 0.94 | no |
| SF10 | block 1 | 11_20260911_192207.153 | validated | 0.84 | 0.67 | +0.0 | +2.0 | no | 0.95 / 0.85 | no |
| SF11 | block 1a | 1_20260831_191341.611 | good | 0.95 | 0.89 | -1.5 | -1.5 | no | – | no |
| SF11 | block 1a | 2_20260901_002906.850 | good | 0.98 | 0.97 | -1.5 | -0.5 | **yes** | 0.98 / 0.97 | no |
| SF11 | block 1a | 2_20260901_075919.035 | good | 0.98 | 0.94 | +0.0 | -0.5 | no | 0.99 / 0.99 | no |
| SF11 | block 1a | 3_20260901_130404.084 | good | 0.99 | 0.97 | -0.5 | -0.5 | **yes** | 0.99 / 0.99 | no |
| SF11 | block 1a | 4_20260901_171752.763 | good | 0.99 | 0.98 | +0.0 | -0.5 | no | 1.00 / 1.00 | no |
| SF11 | block 1a | 7_20260901_193749.076 | good | 0.95 | 0.78 | -1.5 | +0.0 | no | 0.97 / 0.80 | no |
| SF11 | block 1a | 8_20260901_232454.815 | good | 0.98 | 0.97 | -1.0 | -2.0 | **yes** | 0.98 / 0.88 | no |
| SF11 | block 1a | 9_20260902_063458.913 | good | 0.99 | 0.99 | +0.0 | -0.5 | no | 1.00 / 0.99 | no |
| SF11 | block 1a | 13_20260902_170443.451 | check | 0.96 | 0.98 | -1.5 | +0.0 | no | 0.96 / 0.98 | no |
| SF12 | block 1 | 2_20260831_191613.417 | good | 0.59 | 0.56 | +0.0 | +0.0 | **yes** | – | no |
| SF12 | block 1 | 3_20260901_003050.862 | good | 0.59 | 0.64 | +0.0 | +0.0 | **yes** | 0.98 / 0.98 | no |
| SF12 | block 1 | 0_20260901_080334.683 | good | 0.61 | 0.66 | +0.0 | +0.0 | **yes** | 0.99 / 0.99 | no |
| SF12 | block 1 | 1_20260901_131223.398 | good | 0.43 | 0.59 | +0.0 | +0.0 | **yes** | 0.93 / 0.98 | no |
| SF12 | block 1 | 2_20260901_171924.960 | good | 0.53 | 0.59 | -0.5 | +0.0 | **yes** | 0.99 / 1.00 | no |
| SF12 | block 1 | 6_20260901_195621.144 | good | 0.55 | 0.60 | +0.0 | +0.0 | **yes** | 0.99 / 1.00 | no |
| SF12 | block 1 | 7_20260901_232651.122 | good | 0.60 | 0.61 | +0.0 | +0.0 | **yes** | 0.98 / 1.00 | no |
| SF12 | block 1 | 8_20260902_063032.282 | good | 0.61 | 0.60 | +0.0 | +0.0 | **yes** | 1.00 / 1.00 | no |
| SF12 | block 1 | 11_20260902_083748.804 | good | 0.59 | 0.60 | +0.0 | +0.0 | **yes** | 0.98 / 1.00 | no |
| SF12 | block 1 | 15_20260903_002228.142 | good | 0.47 | 0.54 | -0.5 | +0.0 | **yes** | 0.97 / 0.99 | no |
| SF12 | block 1 | 3_20260903_080924.473 | good | 0.61 | 0.63 | +0.0 | +0.0 | **yes** | 0.95 / 0.98 | no |
| SF12 | block 1 | 3_20260903_180935.835 | good | 0.64 | 0.66 | +0.0 | +0.0 | **yes** | 0.99 / 0.99 | no |
| SF12 | block 1 | 5_20260904_082836.973 | good | 0.66 | 0.69 | -0.5 | +0.0 | **yes** | 0.99 / 0.99 | no |
| SF12 | block 1 | 8_20260904_203130.725 | good | 0.68 | 0.75 | +0.0 | +0.0 | **yes** | 0.97 / 0.98 | no |
| SF12 | block 1 | 2_20260905_094454.579 | good | 0.57 | 0.78 | +0.0 | +0.0 | **yes** | 0.97 / 0.99 | no |
| SF12 | block 1 | 4_20260905_190240.835 | good | 0.70 | 0.74 | +0.0 | +0.0 | **yes** | 0.93 / 0.99 | no |
| SF12 | block 1 | 10_20260906_195502.355 | good | 0.97 | 0.92 | +0.0 | +0.0 | no | 0.97 / 0.92 | no |
| SF12 | block 1 | 2_20260907_090439.409 | good | 0.95 | 0.89 | +0.0 | +0.0 | no | 0.99 / 0.99 | no |
| SF12 | block 1 | 2_20260907_180003.285 | exclude | 0.91 | 0.79 | +0.0 | +0.5 | no | 0.99 / 0.92 | no |
| SF12 | block 1 | 5_20260908_072624.615 | check | 0.85 | -0.58 | +0.0 | +1.5 | no | 0.84 / -0.22 | no |
| SF12 | block 1 | 8_20260908_194824.915 | check | 0.87 | -0.55 | +0.0 | +1.5 | no | 0.92 / 0.88 | no |
| SF12 | block 1 | 2_20260909_091353.804 | check | 0.86 | -0.46 | +0.0 | +1.5 | no | 0.99 / 0.99 | no |
| SF11 | block 1b | 17_20260902_190852.526 | low_contrast | 0.97 | 0.99 | +1.0 | +0.0 | no | – | no |
| SF11 | block 1b | 18_20260903_055348.084 | low_contrast | 0.99 | 0.98 | +0.0 | +1.0 | no | 0.95 / 0.99 | no |
| SF11 | block 1b | 4_20260903_155503.475 | low_contrast | 0.96 | 0.99 | +0.0 | +0.0 | no | 0.96 / 0.99 | no |
| SF11 | block 1b | 4_20260903_180700.416 | low_contrast | 0.91 | 0.97 | +0.0 | +0.5 | no | 0.96 / 0.97 | **yes** |
| SF11 | block 1b | 7_20260904_082050.456 | low_contrast | 0.91 | 0.97 | -0.5 | -2.5 | no | 0.99 / 0.96 | **yes** |
| SF11 | block 2 | 9_20260904_135650.425 | low_contrast | 0.78 | 0.97 | +0.0 | +0.0 | no | – | no |
| SF11 | block 2 | 12_20260904_202856.246 | low_contrast | 0.96 | 0.99 | +0.0 | +0.0 | no | 0.89 / 0.97 | no |
| SF07 | block 2 | 2_20260905_093310.289 | check | 0.90 | 0.97 | +0.0 | +0.0 | no | 0.90 / 0.97 | no |
| SF07 | block 3 | 6_20260905_133118.469 | good | 0.94 | 0.99 | +0.5 | +0.0 | no | – | no |
| SF07 | block 3 | 2_20260905_184732.855 | good | 0.96 | 1.00 | +0.0 | +0.0 | no | 0.97 / 0.99 | no |
| SF11 | block 3 | 7_20260905_151133.499 | low_contrast | 0.73 | 0.81 | +0.0 | +0.0 | no | – | no |
| SF11 | block 3 | 2_20260905_185931.246 | low_contrast | 0.52 | 0.75 | -3.0 | +3.0 | **yes** | 0.72 / 0.97 | no |
| SF07 | block 4 | 6_20260906_132942.035 | validated | 0.89 | 0.96 | +0.0 | +0.0 | no | – | no |
| SF07 | block 4 | 2_20260907_085247.979 | validated | 0.95 | 0.99 | +1.5 | +0.0 | no | 0.88 / 0.98 | no |
| SF07 | block 4 | 4_20260907_091511.369 | validated | 0.96 | 0.99 | +0.0 | +0.0 | no | 0.95 / 1.00 | no |
| SF07 | block 4 | 2_20260907_174841.816 | validated | 0.95 | 0.99 | +0.0 | +0.0 | no | 0.97 / 1.00 | no |
| SF07 | block 4 | 8_20260908_193733.435 | validated | 0.94 | 0.99 | +0.0 | +0.0 | no | 0.94 / 0.99 | no |
| SF07 | block 4 | 3_20260909_090331.016 | validated | 0.96 | 1.00 | +0.0 | +0.0 | no | 0.95 / 0.99 | no |
| SF07 | block 4 | 2_20260909_183802.795 | validated | 0.89 | 0.85 | +1.0 | -0.5 | no | 0.92 / 0.85 | no |
| SF07 | block 4 | 5_20260910_082351.495 | validated | 0.90 | 0.96 | -0.5 | -0.5 | no | 0.96 / 0.95 | no |
| SF07 | block 4 | 2_20260911_091615.116 | validated | 0.90 | 0.99 | +0.0 | +0.0 | no | 0.91 / 0.97 | no |
| SF07 | block 4 | 14_20260911_191449.075 | validated | 0.83 | 0.96 | +0.5 | +0.0 | no | 0.81 / 0.99 | no |
| SF08 | block 2 | 3_20260909_185036.554 | good | 0.88 | 0.92 | +1.0 | +0.0 | no | – | no |
| SF08 | block 2 | 6_20260910_082629.685 | good | 0.89 | 0.98 | +0.0 | +0.0 | no | 0.97 / 0.86 | no |
| SF08 | block 2 | 2_20260910_210245.604 | check | 0.85 | 0.97 | +0.0 | +0.0 | no | 0.96 / 0.94 | no |
| SF08 | block 2 | 5_20260911_191715.923 | good | 0.89 | 0.97 | +0.0 | +0.0 | no | 0.89 / 0.97 | no |
| SF12 | block 3 | 15_20260910_210518.445 | exclude | 0.65 | 0.19 | +0.0 | +0.0 | **yes** | 0.65 / 0.19 | **yes** |
| SF12 | block 3 | 17_20260911_192428.023 | exclude | 0.46 | 0.31 | +0.0 | +0.0 | **yes** | 0.47 / 0.78 | **yes** |

## (b) Within-session hourly trend (kept NREM events; session fixed effects + 2-harmonic clock)

| animal | block | feature | sessions | slope % / h | 95 % CI | trend | beyond ±2 %/h |
|---|---|---|---:|---:|---|:---:|:---:|
| SF07 | block 1 | amplitude | 16 | -0.65 | [-0.95, -0.35] | yes | no |
| SF07 | block 1 | env_ratio_noise | 16 | +0.39 | [-0.09, +0.88] | no | no |
| SF07 | block 1 | env_ratio_shank1 | 16 | -0.58 | [-0.83, -0.34] | yes | no |
| SF07 | block 1 | env_ratio_shank2 | 16 | -1.13 | [-2.45, +0.20] | no | no |
| SF07 | block 1 | env_ratio_shank3 | 16 | -0.27 | [-0.62, +0.08] | no | no |
| SF07 | block 1 | env_ratio_shank4 | 16 | +0.77 | [+0.05, +1.49] | yes | no |
| SF07 | block 2 | amplitude | 2 | -2.53 | [-52.65, +100.62] | no | no |
| SF07 | block 2 | env_ratio_noise | 2 | -4.99 | [-56.09, +105.58] | no | no |
| SF07 | block 2 | env_ratio_shank1 | 2 | +0.12 | [-42.70, +74.92] | no | no |
| SF07 | block 2 | env_ratio_shank2 | 2 | -2.01 | [-26.72, +31.04] | no | no |
| SF07 | block 2 | env_ratio_shank3 | 2 | -3.40 | [-41.59, +59.75] | no | no |
| SF07 | block 2 | env_ratio_shank4 | 2 | -2.61 | [-34.28, +44.32] | no | no |
| SF07 | block 3 | amplitude | 3 | -0.17 | [-1.17, +0.83] | no | no |
| SF07 | block 3 | env_ratio_noise | 3 | +0.19 | [-0.41, +0.80] | no | no |
| SF07 | block 3 | env_ratio_shank1 | 3 | -0.20 | [-0.65, +0.25] | no | no |
| SF07 | block 3 | env_ratio_shank2 | 3 | +0.05 | [-0.82, +0.92] | no | no |
| SF07 | block 3 | env_ratio_shank3 | 3 | +0.55 | [-0.04, +1.15] | no | no |
| SF07 | block 3 | env_ratio_shank4 | 3 | +0.32 | [-0.28, +0.92] | no | no |
| SF07 | block 4 | amplitude | 10 | +0.15 | [-0.46, +0.76] | no | no |
| SF07 | block 4 | env_ratio_noise | 10 | +0.02 | [-0.51, +0.56] | no | no |
| SF07 | block 4 | env_ratio_shank1 | 10 | -0.02 | [-1.55, +1.53] | no | no |
| SF07 | block 4 | env_ratio_shank2 | 10 | +0.10 | [-0.59, +0.80] | no | no |
| SF07 | block 4 | env_ratio_shank3 | 10 | +0.10 | [-0.32, +0.51] | no | no |
| SF07 | block 4 | env_ratio_shank4 | 10 | +0.21 | [-0.42, +0.84] | no | no |
| SF08 | block 1 | amplitude | 25 | -0.26 | [-0.49, -0.02] | yes | no |
| SF08 | block 1 | env_ratio_noise | 25 | -0.10 | [-0.56, +0.36] | no | no |
| SF08 | block 1 | env_ratio_shank1 | 25 | -0.21 | [-0.58, +0.15] | no | no |
| SF08 | block 1 | env_ratio_shank2 | 25 | -0.12 | [-0.34, +0.10] | no | no |
| SF08 | block 1 | env_ratio_shank3 | 25 | -0.18 | [-0.77, +0.41] | no | no |
| SF08 | block 1 | env_ratio_shank4 | 25 | -0.49 | [-0.94, -0.03] | yes | no |
| SF08 | block 2 | amplitude | 5 | -1.47 | [-3.57, +0.69] | no | no |
| SF08 | block 2 | env_ratio_noise | 5 | -0.64 | [-1.88, +0.61] | no | no |
| SF08 | block 2 | env_ratio_shank1 | 5 | -0.48 | [-1.95, +1.01] | no | no |
| SF08 | block 2 | env_ratio_shank2 | 5 | -0.04 | [-2.39, +2.37] | no | no |
| SF08 | block 2 | env_ratio_shank3 | 5 | +0.29 | [-1.48, +2.08] | no | no |
| SF08 | block 2 | env_ratio_shank4 | 5 | -1.17 | [-3.03, +0.73] | no | no |
| SF09 | block 1 | amplitude | 29 | -0.19 | [-1.10, +0.74] | no | no |
| SF09 | block 1 | env_ratio_noise | 29 | -0.30 | [-0.70, +0.11] | no | no |
| SF09 | block 1 | env_ratio_shank1 | 29 | +0.18 | [-0.33, +0.70] | no | no |
| SF09 | block 1 | env_ratio_shank2 | 29 | -0.98 | [-2.44, +0.50] | no | no |
| SF09 | block 1 | env_ratio_shank3 | 29 | +0.66 | [-0.03, +1.35] | no | no |
| SF09 | block 1 | env_ratio_shank4 | 29 | -0.40 | [-1.46, +0.68] | no | no |
| SF09 | block 1 | env_ratio_shank5 | 29 | +0.50 | [-0.11, +1.11] | no | no |
| SF10 | block 1 | amplitude | 32 | -0.16 | [-0.37, +0.06] | no | no |
| SF10 | block 1 | env_ratio_noise | 32 | -0.28 | [-0.47, -0.08] | yes | no |
| SF10 | block 1 | env_ratio_shank2 | 32 | -0.25 | [-0.48, -0.01] | yes | no |
| SF10 | block 1 | env_ratio_shank3 | 32 | +0.45 | [+0.02, +0.88] | yes | no |
| SF10 | block 1 | env_ratio_shank4 | 32 | +0.70 | [-1.65, +3.11] | no | no |
| SF11 | block 1a | amplitude | 9 | +0.42 | [-1.30, +2.18] | no | no |
| SF11 | block 1a | env_ratio_noise | 9 | +0.53 | [+0.27, +0.79] | yes | no |
| SF11 | block 1a | env_ratio_shank1 | 9 | +0.86 | [-0.98, +2.74] | no | no |
| SF11 | block 1a | env_ratio_shank2 | 9 | +0.52 | [-1.67, +2.75] | no | no |
| SF11 | block 1a | env_ratio_shank3 | 9 | +0.07 | [-2.31, +2.50] | no | no |
| SF11 | block 1a | env_ratio_shank4 | 9 | -0.87 | [-4.13, +2.49] | no | no |
| SF12 | block 1 | amplitude | 19 | -0.27 | [-1.27, +0.74] | no | no |
| SF12 | block 1 | env_ratio_noise | 19 | -0.48 | [-0.72, -0.23] | yes | no |
| SF12 | block 1 | env_ratio_shank1 | 19 | -2.60 | [-4.62, -0.53] | yes | **yes** |
| SF12 | block 1 | env_ratio_shank2 | 19 | -0.25 | [-1.37, +0.88] | no | no |
| SF12 | block 1 | env_ratio_shank3 | 19 | -0.96 | [-1.79, -0.14] | yes | no |
| SF12 | block 1 | env_ratio_shank4 | 19 | -0.11 | [-0.85, +0.64] | no | no |

Per session, amplitude last 2 h / first 2 h: median 0.977, IQR 0.939–1.029, 5 below 0.8 and 2 above 1.25 of 119.

## Definitions

- **Profiles:** `swr_channel_scan.py`. `ratio` = NREM ripple-envelope ratio per column; `spw_ref_uV` = the sharp wave at the session's own ripple events (± 15 ms 1–50 Hz minus a ± 150–250 ms baseline).
- **Shift:** the integer $s \in [-4,4]$ maximising $\mathrm{corr}(\mathrm{ref}_i, \mathrm{ses}_{i+s})$ along a shank (≥ 8 live sites). $s > 0$ = the profile sits $s$ sites deeper than in the reference.
- **Candidate:** |s| ≥ 1 with one sign on ≥ half of the eligible shanks in both profiles, or whole-probe r < 0.8 in both.
- **Hourly:** y = log(bin median / session median), 1-h bins since the session start (≥ 30 events). Model: WLS on session fixed effects + elapsed hours + clock harmonics; weights = events; SEs clustered by session.

## Limits

- A shift is in channel steps of the final order. The site pitch is not converted.
- Ripple amplitude follows state and depth as well as position.
- Low-contrast blocks (SF11 after 09-02 19:08, SF12 block 3) have no SWR-specific profile.

