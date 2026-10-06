# 2026-10-05 — IMU–WISER consistency audit: residual "WISER moves / turns while the head IMU says it cannot" → NOT MATERIAL, V3 stays; per-fix QC flags delivered

**Plan:** [`implementation_plan/2026-10-05-wiser-imu-consistency-audit.md`](../implementation_plan/2026-10-05-wiser-imu-consistency-audit.md)
(approved by the user 2026-10-05, "搞"; committed ff3c75c before any result). Amendment 1 (operational resolutions: B2 build,
Δψ from the 50-Hz npz, masks, I1 / I2 windows, strata, controls, enrichment, flags) was written before any number. Amendment 2
was written after the first run's pooled numbers. It fixes a CSV time-precision bug that changed only the event-list times
(rates, enrichment, flags and the decision were reproduced exactly) and adds a declared post-hoc sensitivity. No definition,
threshold or rule changed.
**Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_imu_consistency_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_imu_consistency_2026c.md)
(verdict, reading, 8 sections, event lists, full Definitions; figures `wiser_baseline_imu_consistency_{rates,enrichment,sizes}_2026c.png`).
**Driver / config:** `wiser/scripts/analyze_wiser_imu_consistency.py` (`--selftest` 14 checks ALL PASS; `--report-only <run> [--reuse]`;
`--install-flags <run>`); `wiser/configs/wiser_imu_consistency_2026c.json` (verdict in `decision`).
**Bulk:** `D:\Field2026_analysis_out\2026c\wiser_imu_consistency_20261005_2038\` (tables, `summary.json`, `input_provenance.json`,
`log.txt`, `selftest.txt`, staged flags). The first run `…_1721` is superseded: its event times were rounded, otherwise identical.
Pointer `results/2026c/wiser_baseline/reports/run_manifest_imu_consistency_2026c.json`.
**New caches:** B2 tracks for SF07–SF12 `D:\Field2026_analysis_out\2026c\wiser_tracks_B2\` (`build_wiser_default_tracks.py --method B2
--stages tracks`, run `wiser_default_tracks_run_20261005_1704`; the verify / report stages were skipped so the V3 report is
untouched). **QC flags** `D:\Field2026_analysis_out\2026c\wiser_default_tracks_qc\<label>\<YYYYMMDD>.csv.gz` (78 files, every
production day of SF07–SF12, + README + `index_2026c.csv`).

## Decision

**NOT MATERIAL** (pre-registered: V3, pooled over 1,277.6 IMU-ok hours). **V3 stays the default track for the implanted
animals, B2 the universal baseline; the per-fix QC flags are the deliverable.** No correction test is proposed. Nothing was tuned.

| quantity | value [95 % CI] | rule | met |
|---|---|---|---|
| I1 + I2 rate per IMU-ok hour | **4.33** [4.18, 4.49] | ≥ 1 | yes |
| ≤ 6-anchor share ratio, event / matched control (I1 + I2) | **1.43** [1.23, 1.64] (17.4 % vs 12.2 %) | ≥ 2 | **no** |
| CI lower bound | 1.23 | > 1 | yes |

## Reported (not the decision)

- **V3 rates per IMU-ok hour:** I1 4.24 (5,411), I2 0.098 (125), I3 0.063 (80). B2: 4.50 / 0.012 / 0.27. Raw 1-s medians:
  6.72 / 21.9 / 0.27. The filters remove almost all raw turn inconsistencies (I2 21.9 → 0.10).
- **V3 I1 by stratum:** night 6.8, day 1.8, twilight 4.5; house 3.2, field 7.4; rain 6.7, wet 4.7, dry 3.5 (unknown 6.2: station gap
  09-02 21:15 → 09-03 15:05). V3 I2: night 0.18, day 0, field 0.33, house 0.02. Per animal I1 3.3–4.9.
- **V3 vs B2 (I1, matched by run):** 405 B2 events are absent in V3 and 73 appear only in V3. No V3 I1 event falls in an
  all-still run: V3's ZUPT already removes the still-run part, and every residual I1 sits in a run with at least one IMU-active
  second. I1 grows with run length: the share of runs with an event goes from 1.5 % (≤ 10 s) to 63 % (> 30 min).
- **Enrichment (V3):** I1 1.43 [1.24, 1.63] (house 1.46, field 1.21); I2 1.07 [0.72, 1.54] (not enriched). Raw-fix dispersion ratio
  I1 1.19 [1.11, 1.23]. B2 I1 1.69, raw I1 2.09. Part of the residual I1 is bad geometry, but most events are not explained by it;
  they fit loco-detector misses and real slow movement as well as WISER errors. Post hoc (Amendment 2): with both windows
  restricted to seconds with ≥ 2 fixes the share ratio stays 1.44 and the fix-rate ratio falls from 1.15 to 0.99, so that
  excess is a window-construction artefact.
- **Sizes (V3):** I1 median 16.9 in (p90 29.7, max 120), duration median 7 s (p90 65 s, p99 ≈ 570 s); I2 |Δθ| median 126°. The largest
  I1 are 70–120-in displacements over tens of seconds at 8–9 anchors (loco-detector-miss candidates); the largest I2 are path
  reversals (≈ 180°) just above 10 in/s.
- **Event lists** for the user's video check: the 30 largest I1 and the 30 largest I2 (V3), with the hourly `F:\3rd_rat` file and
  offset by file-name time (report §5; `tables/event_list_I{1,2}_V3.csv`). The agent looked at no frame.
- **QC flags:** `qc_i1` on 880,843 of 21,151,858 V3 fixes (4.16 %; long I1 windows), `qc_i2` on 2,420 (0.011 %). Verified: rows
  aligned with the production files; I2 flags = event windows exactly; I1 flags inside their event windows (12 random files).
- **Reproduction:** all 1,374 Phase-0 W = 2 s pairs reproduced from the production caches. The largest difference is 0.005° for
  Δθ raw, Δθ V3 and Δψ alike (CSV rounding) → PASS (≤ 0.1°). A per-second `turn_net_deg` approximation of Δψ would be off by a
  median of 6.3° (p95 22.6°), which is why Δψ comes from the 50-Hz npz (Amendment 1.2). An independent pandas recomputation of 5
  I1 events (the 2 largest + 3 random) matched size and duration exactly.

## Definitions (headline quantities; full set in the report)

- **Included second** $\mathrm{inc}(s) = \mathrm{ok}(s) \wedge$ no masked fix in $s$ $\wedge\ s <$ SF11's implant loss; IMU-ok hours
  $H = \sum_s \mathrm{inc}(s)/3600$ (the denominator of every rate). $\mathrm{ok}$ = the IMU-seconds cache's QC.
- **1-s median** $\tilde{\mathbf p}(s) = \operatorname{med}_{\rm coord}\{\mathbf z_k : t^{\rm al}_k \in [s, s+1)\}$ (≥ 2 fixes), per track (raw, V3, B2); inches.
- **I1:** run = maximal stretch of included seconds with IMU state still/active, ≥ 5 s, trimmed 2 s at both ends; reference
  $\mathbf r$ = median of $\tilde{\mathbf p}$ over the first 2 trimmed seconds; event ⇔ $\lVert\tilde{\mathbf p}(s) - \mathbf r\rVert \ge 12$ in for ≥ 2
  consecutive seconds; size = max displacement (in), duration = seconds ≥ 12 in, window = those seconds.
- **I2 / I3** (0.5-s grid, Phase-0 estimators): $\Delta\theta(c) = \mathrm{wrap}(\theta(c+1) - \theta(c-1))$ with
  $\theta(h) = \operatorname{atan2}(m(h+0.5) - m(h-0.5))$, $m$ = 1-s coordinate-wise median (≥ 3 fixes);
  $\Delta\psi(c) = \bar\psi(c+1) - \bar\psi(c-1)$, $\bar\psi$ = 1-s mean of the integrated 50-Hz head turn (+ = CCW from above). Candidate:
  1-s speed ≥ 10 in/s at $c \pm 1$, support $[c-2, c+2)$ included, gyro span valid. I2 ⇔ $|\Delta\theta| \ge 90° \wedge |\Delta\psi| < 20°$;
  I3 ⇔ $|\Delta\psi| \ge 90° \wedge |\Delta\theta| < 20°$; centres < 2 s apart merge; window $[c_{\rm first} - 2, c_{\rm last} + 2)$.
- **Rate** = events with onset in a stratum / IMU-ok hours of that stratum; CI = 10-min block bootstrap.
- **≤ 6-anchor share ratio** $\rho_S = S_{\rm ev}/S_{\rm ct}$, $S = \sum_w \omega_w n^{\le 6}_w / \sum_w \omega_w n_w$ (raw fixes; control weight
  $1/k_e$). Controls: same animal, noon-to-noon bio-day and track, ≤ 5 per event at random (I1: event-free runs of 0.5–2× the
  trimmed length, a window of the same duration at the same offset; I2: non-event candidate pairs outside I2 windows). CI: 10-min
  block bootstrap (animal × 10-min bin of the window onset), 1,000 replicates.
- **Decision:** MATERIAL ⇔ V3 I1 + I2 rate ≥ 1 h⁻¹ ∧ $\rho_S \ge 2$ ∧ CI_lo($\rho_S$) > 1.

## Caveats

No ground truth: an event can be a WISER error, a loco-detector miss (TPR 0.75 / FPR 0.15) or a real movement the IMU state misses.
Enrichment is circumstantial; the video check decides individual cases. I1's reference is the run start, so slow repositioning
inside long rests counts. Weather "unknown" covers the station gap of the 09-03 rain night, and the hours just after it may be
classed dry. Positions are in the unverified WISER inch frame.

## For the main session (not done here, by boundary)

CLAUDE.md `wiser_baseline` row: add `analyze_wiser_imu_consistency --cohort 2026c` (+ `--selftest`), the B2 cache
`wiser_tracks_B2/`, the QC-flag cache `wiser_default_tracks_qc/` and the verdict. Also update both index READMEs
(`change_log/README.md`, `implementation_plan/README.md`), then commit.
