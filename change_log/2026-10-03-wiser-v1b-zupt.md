# 2026-10-03 — V1b (B2 + guarded head-IMU zero-velocity constraint) passes its own claim; failure-audit table fix

**Plan:** [`implementation_plan/2026-10-03-wiser-v1b-zupt.md`](../implementation_plan/2026-10-03-wiser-v1b-zupt.md) (step A of
A → B → C, approved by the user 2026-10-03, "干吧"); written before any V1b number; amendments 1–5 made before any pooled
V1b number (operational details only), note 6 after (reported diagnostics only).
**Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_v1b_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_v1b_2026c.md)
(E1–E3 table, reported sections, full Definitions, 5 figures `wiser_baseline_v1b_*_2026c.png`).
**Bulk:** `D:\Field2026_analysis_out\2026c\wiser_v1b_20261003_1124\`; pointer
`results/2026c/wiser_baseline/reports/run_manifest_v1b_2026c.json` (the folder's `run_manifest.json` is untouched).

## Decision

**V1b passes E1, E2 and E3 → V1b is the default WISER track for the implanted animals** (SF07–SF12 wherever the head-IMU QC
passes; where it fails, and in the ± 10-min margins, V1b *is* B2 by construction — same filter, no splice). **B2 stays the
universal baseline** (tags without an IMU, e.g. the five females released 09-11, and every IMU-failed stretch). Written into
`wiser/configs/wiser_v1b_2026c.json` → `decision`. No sensitivity variant passes (V1b-noRelease and V1b-raw fail E1b), so
none is proposed.

V1b = B2 (q = 3 in²/s³, anchors_used noise table, χ² gate + 2 Huber IRLS passes, k_H = 2.5, forward KF + RTS) + pseudo-
measurements 0 = v_x, 0 = v_y at every fix inside a ZUPT interval, σ_ZUPT = 1.0 in/s, Huber-weighted in the same IRLS passes;
ZUPT intervals = runs of ≥ 3 IMU-QC-ok still seconds eroded by 1 s at each end; release when the centred 5-s median of the
raw fixes stays ≥ 12 in from the run's first-5-s reference for > 5 s.

## Pre-registered criteria (point estimates decide; 95 % CIs from the 10-min block bootstrap)

| claim | calm | rain | bound | V1b |
|---|---|---|---|---|
| E1a p99 \|V1b − B2\| (IMU-ok non-still mask fixes ≥ 3 s from a ZUPT fix) | 0.020 in [0.018, 0.021] | 0.019 in [0.014, 0.025] | ≤ 0.5 in | pass |
| E1b 1-s speed Δ vs B2, IMU-locomoting p50 / p95 | −0.00 % / +0.00 % | −0.03 % / −0.02 % | ± 5 % | pass |
| E1b 1-s speed Δ vs B2, WISER ≥ 10 in/s p50 / p95 | −0.02 % / +0.00 % | **−2.44 %** [−5.0, −0.9] / +0.00 % | ± 5 % | pass |
| E2 median per-event lag Δ, onset / offset | 0.00 / 0.00 s (n 298 / 275) | 0.00 / 0.00 s (n 106 / 110) | ± 0.5 s | pass |
| E3 jumps, certified ≥ 30-s segments / analysis masks | 0 / 0 | 0 / 0 | 0 | pass |

- **E1a** — the difference is local: p99 0.33 | 0.56 in at 3–4 s from a ZUPT fix, ≤ 0.18 in from 5 s on; 96 % | 97 % of
  the IMU-ok non-still fixes are ≥ 3 s from any ZUPT fix, so the pooled p99 is small (max 2.6 | 3.5 in).
- **E1b** — the only visible change, rain WISER-fast p50 −2.4 %, comes from the 19 % of those seconds that are IMU-still
  (the library speed says ≥ 10 in/s while the head IMU says still); without them the change is −0.02 % / 0.00 %. The CI
  reaches the bound (−5.0 %); the release keeps the point estimate inside it (V1b-noRelease −5.6 %, V1b-raw −6.2 %: both
  fail E1 on this cell).
- **E2** — the median is 0 everywhere, but 16 / 19 % (calm onset / offset) and 25 / 29 % (rain) of the paired events shift,
  onsets later and offsets earlier (mean Δ +0.35 / −1.23 s calm, +0.82 / −2.11 s rain; median Δ of the changed events
  +0.25 / −0.75 s calm); about half of the changed offsets are events where B2's 3-in/s crossing lay inside the IMU-still run.

## Reported (not the decision)

- **Still metrics on the certified ≥ 30-s segments — CIRCULAR** (the IMU stillness drives the ZUPT and certifies the
  segments): fake path B2 38.9 | 50.8 → V1b 12.8 | 20.0 in/min (−67 % | −61 %; V1b-noRelease 12.0 | 13.9, V1b-raw 3.3 | 3.6);
  per-fix RMS 1.60 | 2.65 → 1.25 | 2.29 in; 10-s drift median 1.41 | 1.91 → 1.14 | 1.57 in; jumps 0. σ_ZUPT = 1 in/s is a soft
  constraint (steady-state velocity SD ≈ 0.7 in/s against B2's q), and its Huber weight is < 1 at only 0.0002 % | 0.004 %
  of the ZUPT fixes — in practice the guard that matters is the release, not the Huber weight.
- **ZUPT coverage** of certified still time 98.3 % | 91.3 % (noRelease 99.9 | 99.8 %, V1b-raw 100 %); ZUPT fixes = 43.6 % |
  27.2 % of all window fixes.
- **Releases:** 155 (calm 70, rain 85); 108 inside certified segments (88 in ≥ 30-s segments) — a cost, the head was
  certified still, so the track followed WISER drift — and 47 outside; 0.54 | 2.13 per certified still-hour; 4.4 h released
  (3.4 h inside certification); 95 % in a house. The 09-10 09:48 cluster: 10 releases within ± 5 min (SF07 ×2, SF08 ×2,
  SF09 ×4, SF10, SF12), 7 of them inside certified segments.
- **False-stillness probe:** 19 % of the pilot-still seconds overlap no certified window or segment; their B2 5-s
  displacement is p50 1.6 vs 1.3 in inside certification, ≥ 12 in in 0.48 vs 0.27 % (IMU-locomoting seconds 49 %); 82 % of
  them receive the V1b ZUPT (V1b-raw 100 %).
- **S1 (identity check):** D on moving held-out fixes +0.08 % / +0.02 % (calm, schemes a / s), +0.07 % / −0.01 % (rain).
- **S3:** rain ≥ 12-in excursions raw 6, B2 7, V1b 7 (noRelease 7, V1b-raw 4); V1b − B2 = 0.
- **NIS under B2** (χ²₂: mean 2, 5 % above 5.99): calm mean 4.83 (20.8 % above); at 9 anchors house 3.23 vs outside 7.22
  (rain 3.73 vs 7.90). Mostly a motion effect: at 9 anchors IMU-still house 2.38 vs outside 2.60, active 4.16 vs 5.62,
  locomoting 8.02 vs 10.57 (calm; rain still 3.03 vs 4.65) — the anchors_used table is roughly consistent for a still tag
  and too optimistic in motion (the constant-velocity model is stiff for runs), with a smaller residual house/outside gap
  at equal state; 3–4 anchors are worst (mean 12–22).

## What changed

- **New** `wiser/scripts/analyze_wiser_v1b.py` — new numba kernel `_kf_v1b` (B2 without drift, same operation order as the
  pilot's `_kf_rts`, + an optional ZUPT pseudo-measurement with a Huber weight in the IRLS passes, + per-fix NIS of the final
  forward pass); ZUPT interval / erosion / release logic; per-animal-period compute (process pool, 16 workers, 51 s) and
  aggregation (E1–E3, still metrics, coverage, releases, false-still probe, S1, S3, NIS; ≈ 3.5 min); `--report-only`;
  `--selftest` ALL PASS (18 checks on synthetic data: no-ZUPT kernel = pilot B2 to 0.0 in; V1b = B2 ≥ 3 s from any ZUPT fix
  (p99 0.038 in, max 0.076 in — amendment 1); erosion / minimum run / membership; release fires on a planted 15-in 8-s drift
  at its start and not on a 15-in 3-s excursion, nowhere else, and stays off to the run's end; a planted 2-s false-still run
  gets no ZUPT; V1b's still fake path below B2's; E1a / E1b / E2 / E3 evaluators on planted cases; S5 events through the
  default-smoother code; the failure audit's grouped-vs-pooled quantile check). Imports `analyze_wiser_imu_smoothing.py`,
  `analyze_wiser_failure_audit.py` and `analyze_wiser_default_smoother.py` (none edited except the audit fix below).
- **New** `wiser/configs/wiser_v1b_2026c.json` (candidate, sensitivities, thresholds, bootstrap seed 20261006, cluster window,
  `decision` block).
- **Fixed** `wiser/scripts/analyze_wiser_failure_audit.py`: `group_table` now takes the full segment table (`Sall`) that the
  speed index refers to (it used the grouped subset's row positions); + a selftest check (a single group's speed p95 =
  the pooled one = the direct quantile; the pre-fix call gave 23.9 vs 68.0 on the synthetic case); the report header says
  19 checks and names the fix. `--report-only` re-run on `wiser_failure_audit_20261002_1511` (≈ 2.7 min).
- No cache, raw file, SQLite or other driver was touched; nothing was committed.

## Failure-audit report: every number that changed (old → new)

Only the raw fake-speed column of the "Raw WISER, primary segments ≥ 30 s" table (p50 / p95 / p99, in/s) and the header
line changed; the pooled tables, path, RMS, drift, events, jumps, Q4 and every figure are unchanged.

| set | kind | fake speed p50 / p95 / p99 before | after |
|---|---|---|---|
| calm | day | 3.3 / 12.3 / 23.5 | 3.2 / 11.8 / 22.2 |
| calm | night | 3.5 / 12.2 / 22.0 | 3.2 / 10.9 / 19.3 |
| rain | day | 3.1 / 11.1 / 20.2 | **4.0 / 19.9 / 31.3** |
| rain | night | 4.3 / 14.1 / 22.0 | 4.2 / 17.8 / 28.4 |

Header: "`--selftest` ALL PASS, 18 checks" → "19 checks; the per-group still tables' speed quantiles were corrected on
2026-10-03 …" (and the git string). In the bulk tables only the `speed_p50/p95/p99` columns of `summary_still_{period,
setkind, set, animal, zone, segbin, hour, ge10}.csv` changed; e.g. `summary_still_set` raw p95 calm 12.31 → 11.70 (= the
pooled table), rain 11.93 → 19.38. The bug understated the rain fake speed (rain day p95 11.1 → 19.9 in/s).

## Verification

- New kernel without ZUPT = the pilot's B2 kernel to 0.0 in on every fix of all 50 animal-periods; B2 rebuilt from the
  float64 cache fixes = the audit's saved (float32) B2 to 4.3e-5 in; fix rows / anchors identical; 0 segment fix-count
  mismatches; raw / B2 still metrics of 8,320 segment × method rows identical to the audit's.
- Default-smoother reproduction: S5 events 488 / 428 / 170 / 164 (calm onset / offset, rain onset / offset) identical; B2
  S5 median lags 7.00 / −9.75 / 7.50 / −9.62 s identical; B2 1-s speed p50 / p95 on the same seconds identical to 1e-4 in/s;
  B2 S1 medians identical to 1e-5 in; B2 fake path 38.90 | 50.82 in/min identical.

## Headline definitions (full set in the report)

- **E1a** $Q_{0.99}\{\lVert\hat{\mathbf p}^{V1b}_k-\hat{\mathbf p}^{B2}_k\rVert:\ k\in\mathcal B,\ \tau_k\ge3\,\text{s}\}\le0.5$ in, $\mathcal B$ = analysis-mask
  window fixes whose aligned second is IMU-QC-ok and not still, $\tau_k$ = time to the nearest V1b ZUPT fix. Text: V1b is B2
  wherever the head moves and the constraint is not near.
- **E1b** $\Delta_q=Q_q[v_{V1b}]/Q_q[v_{B2}]-1$, $v(s)=\lVert\tilde{\mathbf p}(s+1)-\tilde{\mathbf p}(s)\rVert/1$ s, q ∈ {0.5, 0.95}, on
  IMU-locomoting seconds and WISER-fast seconds (library 1-s median speed ≥ 10 in/s, analysis mask); pass if all $|\Delta_q|\le0.05$.
- **E2** $\operatorname{med}_e(\lambda^{V1b}_e-\lambda^{B2}_e)$ within ± 0.5 s, $\lambda$ = default-smoother S5 onset / offset lag (first / last
  time the 1-s speed reaches 3 in/s relative to the IMU still-run end / start), events where both are defined.
- **E3** 0 jumps (> 30 in within ≤ 0.35 s) in the certified ≥ 30-s segments and over every period's analysis mask.
- **ZUPT coverage** = (certified ≥ 30-s still time inside a post-release ZUPT interval) / (certified still time).
- **NIS** $\sum_a (z_{k,a}-\hat p^-_{k,a})^2/(P^-_{k,aa}+\sigma^2_a(A_k))$ in the final forward pass with the nominal noise; χ²₂ if consistent.

## Caveats

B2's parameters were tuned on 2026-09-08/09 (a calm audit night). Still metrics are circular and ≥ 95 % of certified
stillness is in the houses. E1 tests identity with B2, not correctness (step B builds an independent speed reference).
E1 and E2 are decided on point estimates: the rain WISER-fast p50 CI reaches −5.0 %, and the E2 median hides a 16–29 %
minority of shifted events. The 1-s pilot still class has an unknown false-still rate (19 % of its still seconds lie
outside certification). The rain set is three weather episodes. Positions stay in the unverified WISER inch frame.
