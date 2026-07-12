# Cleaning log — trajectory stereotypy (Phase A)

Generated (UTC): 2026-07-10T03:54:50.502613

## Load & dedup (double-count control)

- dedup key: `shortid+ts_raw+x+y`
- rows concatenated across files: 19,598,282
- unique rows after dedup: 17,362,614
- **duplicate rows removed: 2,235,668** (the 06-30 cumulative dump overlaps 06-28/06-29 — dedup makes the load exact)

### Per-file

| file | rows_raw | rows_kept |
|---|---|---|
| 1stcohort_2026_2026-06-28.csv.gz | 381,109 | 381,109 |
| 1stcohort_2026_2026-06-29.csv.gz | 1,854,559 | 1,854,559 |
| 1stcohort_2026_2026-06-30.csv.gz | 3,690,784 | 3,690,784 |
| 1stcohort_2026_2026-07-01.csv.gz | 488,760 | 488,760 |
| 1stcohort_2026_2026-07-02.csv.gz | 1,644,073 | 1,644,073 |
| 1stcohort_2026_2026-07-03.csv.gz | 1,700,110 | 1,700,110 |
| 1stcohort_2026_2026-07-04.csv.gz | 1,695,592 | 1,695,592 |
| 1stcohort_2026_2026-07-05.csv.gz | 1,679,145 | 1,679,145 |
| 1stcohort_2026_2026-07-06.csv.gz | 1,561,212 | 1,561,212 |
| 1stcohort_2026_2026-07-07.csv.gz | 1,591,246 | 1,591,246 |
| 1stcohort_2026_2026-07-08.csv.gz | 1,620,381 | 1,620,381 |
| 1stcohort_2026_2026-07-09.csv.gz | 1,691,311 | 1,691,311 |

## Jitter floor / thresholds

- jitter floor: **7.0 in** (tag_reports_2026-06-30.sqlite: working floor = documented ~7 in median (p95 ~15 in); measured stationary jitter p50 3.39 in / p95 14.71 in; moving thr = speed p99)
- moving threshold (locomotion): **12.63 in/s** (stationary p99 speed floor)
- occupancy bin: **8.0 in** (>= jitter floor)
- jump threshold: 200.0 in/s; gap factor: 5.0x median dt; min anchors: 4; smooth window: 7

## Validity flags (whole dataset, before night window)

| flag | count | fraction |
|---|---|---|
| low_anchor_flag | 68,275 | 0.00393 |
| gap_flag | 73,948 | 0.00426 |
| jump_flag | 101,566 | 0.00585 |
| outside_provisional_bounds | 2,912 | 0.00017 |
| after_tag_cutoff | 14,871 | 0.00086 |
| valid | 17,110,978 | 0.98551 |

- night-window valid fixes retained: **5,829,415**
- gaps are flagged, never interpolated across; a gap is 'unknown', not 'left'.
- Sova (12409) dropped entirely (removed 2026-06-29 15:00); tunnel ROI auto-expires 2026-06-29 07:00 via its `valid_until`.
