# V1b — B2 + guarded IMU zero-velocity constraint (cohort 2026c), and the failure-audit table fix

**Status:** PLANNED 2026-10-03, written before any V1b number was computed.
**Approval:** the user approved steps A → B → C on 2026-10-03 ("干吧") after the Fable SOTA audit of the WISER/IMU results
(session scratchpad `sota_audit_wiser_imu_fable.md`). This is step A: V1b with the audit's guards, evaluated **not** by
a B2-referenced superiority rule but as a test of V1b's own claim ("B2 in motion, still in stillness"), plus the fix of
the failure audit's per-group quantile bug. Operational details not fixed by the approval are marked **[op]**.
**Direction:** `wiser_baseline`. **Driver:** new `wiser/scripts/analyze_wiser_v1b.py` (imports, never edits,
`analyze_wiser_imu_smoothing.py`, `analyze_wiser_failure_audit.py`, `analyze_wiser_default_smoother.py`).
**Config:** new `wiser/configs/wiser_v1b_2026c.json` (the run writes its verdict into a `decision` block).

## Why

The default-smoother step (`change_log/2026-10-02-wiser-default-smoother.md`) kept **B2** by a no-survivor fallback. Its
S1/S2/S5 criteria are defined relative to B2, so B2 could not fail them, and B2 still leaves 38.9 | 50.8 in/min of fake
path in certified stillness (calm | rain; ≈ 59 m per still-hour). V1 (B2′ + ZUPT) removed almost all of it but was ≈ 15 %
slower than B2 in locomotion — exactly as slow as B2′ itself (S1 −2.9 % vs −3.7 %, S2 −15 %/−12 % for both), so the
deficit came from B2′'s drift state, not from the ZUPT. V2/V2b changed the process noise in motion (+10 % / +28 % speed)
and spliced to B2 (2–3 boundary jumps). **V1b** = one B2 filter + a zero-velocity constraint only where the head IMU says
still; nothing else changes. Its claim is therefore an *identity* claim in motion, which can be tested against B2 without
pretending B2 is the truth.

## Established facts (not re-derived)

Tag and IMU are on the head. Audit periods, animals, exclusions, certified ≥ 30-s still segments (gate-v2 strict on
09-08, S50 elsewhere; 97 h, 98 % inside the houses) and per-second IMU states (pilot rule: still = 1-s VeDBA < θ_a
(0.31–0.39 m/s²) ∧ 1-s |ω| < 10 °/s; locomoting = VeDBA ≥ 3.93 m/s² ∧ SBF ≥ 0.10; 0 = QC failed) are the failure audit's
(`D:\Field2026_analysis_out\2026c\wiser_failure_audit_20261002_1511`). B2 = the smoothing pilot's tuned B2 (q = 3 in²/s³,
per-fix noise from `anchors_used`, χ² gate + 2 Huber IRLS passes, k_H = 2.5, forward KF + RTS). Fix times are aligned by
τ* = 0.20 / 0.15 / 0.10 / 0.20 / 0.15 s (SF07 / 08 / 09 / 10 / 12). Default-smoother numbers for B2 (calm | rain): fake path
38.9 | 50.8 in/min, per-fix RMS 1.60 | 2.65 in, rain ≥ 12-in excursions 7 (raw 6), 0 jumps, onset lag 7.00 s.

## Candidate

**V1b (primary).** B2 exactly, plus the pseudo-measurements $0=v_x$, $0=v_y$ at every fix inside a ZUPT interval:
- **σ_ZUPT = 1.0 in/s**, **Huber-weighted** (k_H = 2.5 on the normalised pseudo-innovation, inside the same IRLS passes as
  the fixes) **[op: if the existing kernel cannot weight the pseudo-measurement, implement it in a new kernel in the V1b
  driver and verify that with no ZUPT it reproduces B2 to ≤ 1e-6 in]**.
- **ZUPT intervals:** runs of consecutive IMU-QC-ok `still` seconds of length n ≥ 3 s, **eroded by 1 s at each end**
  (n − 2 s of ZUPT; runs < 3 s give none). A fix belongs to an interval when its aligned time lies inside it.
- **Release:** inside each eroded run, reference **r** = coordinate-wise median of the raw fixes in the run's first 5 s
  (if < 10 fixes there, the first 10 fixes of the run). If the centred 5-s rolling median of the raw fixes stays ≥ 12 in
  from r **continuously for > 5 s**, the ZUPT is dropped from the first centre of that stretch to the end of the run.
- Where the IMU QC fails, and in the ± 10-min margins (no saved IMU seconds): no ZUPT, i.e. B2 dynamics **in the same
  filter** — no splice, no second filter.

**Sensitivities (reported, never the decision):** V1b-noRelease (guards 1–2 only); V1b-raw = the original proposal
(no erosion, no minimum run, Gaussian σ_ZUPT = 0.25 in/s, no release). B2 and raw are the references.

## Pre-registered acceptance (V1b's own claim)

- **E1 — identical to B2 in motion.**
  (a) Position: over analysis-mask fixes whose aligned second is IMU-QC-ok and not still and that lie **≥ 3 s from the
  nearest ZUPT fix**, the V1b–B2 distance has **p99 ≤ 0.5 in** (calm and rain separately).
  (b) Speed: the 1-s centred speed (the default-smoother S2 definition) **p50 and p95 within ± 5 % of B2** on
  IMU-locomoting seconds and on WISER-fast seconds (library 1-s median speed ≥ 10 in/s), calm and rain (point estimates;
  paired block-bootstrap CIs reported).
  The V1b–B2 distance profile vs time from the nearest ZUPT fix is reported (0–10 s).
- **E2 — transitions not shifted.** S5 onset and offset events (default-smoother definition, all periods): median
  per-event Δ = lag(V1b) − lag(B2) within **± 0.5 s** for onset and for offset, calm and rain (point estimates; CIs
  reported).
- **E3 — no jumps.** 0 jumps (> 30 in within ≤ 0.35 s) in the primary still segments (calm and rain) and over the analysis
  mask of every period.

**Decision.** V1b passes E1–E3 → **V1b becomes the default WISER track for the implanted animals** (SF07–SF12 wherever the
IMU QC passes; elsewhere it *is* B2 by construction), and **B2 remains the universal baseline** (tags without an IMU, e.g.
the five females released 09-11, and every IMU-failed stretch). V1b fails any of E1–E3 → B2 stays the default; the report
names the failed claim. No sensitivity variant is promoted in this step (a variant that would pass becomes a proposal to
the user).

## Reported, not part of the decision

- **Still metrics on the certified segments** (fake path, per-fix RMS, p99, 10-/60-s drift, ≥ 12-in events, jumps), calm |
  rain, day | night — **labelled circular** (the IMU stillness drives the ZUPT and overlaps the certification); plus the
  **ZUPT coverage** = share of certified still time that actually receives the ZUPT after the guards.
- **Release accounting:** releases inside certified still segments (the head is still → the release followed WISER
  drift: a cost) vs outside them; per still-hour; the 09-10 09:48 four-tag cluster called out.
- **False-stillness probe:** seconds the pilot rule calls still that lie outside every certified segment and window
  (count, share, WISER 5-s displacement there).
- **S1** held-out moving-fix error vs B2 (schemes (a)/(s), as in the default-smoother step) — an identity check (expected
  ≈ 0), not a criterion. **S3** rain ≥ 12-in excursions vs raw (6) and B2 (7), with CIs.
- **NIS diagnostic** (Fable audit, point 4): normalised innovation squared of the fixes under B2 (and V1b), by
  `anchors_used` × zone (house / outside) × IMU state (still / active / locomoting) — mean NIS vs the χ²₂ expectation of 2
  and the share above the 95 % point; tests whether the `anchors_used` noise table is consistent and whether it is
  house-confounded.

## Failure-audit table fix (same step)

`analyze_wiser_failure_audit.py`: the per-group still tables (`summary_still_{period,setkind,set,...}.csv`) take speed
quantiles with row positions of the grouped frame instead of the full segment table (raw calm fake-speed p95 12.31 there
vs 11.70 in/s correct; pooled table, path, RMS, drift, events and jumps unaffected). Fix it, add a selftest check that
the grouped quantile equals the pooled one for a single group, re-run `--report-only` on the audit run, and list every
number that changes in the regenerated report (old → new).

## Data (read-only inputs)

The audit run (`tracks/*.npz` = raw/B1/B2/B2p/B2pb/V1/V2 at every fix, `imu_seconds/`, `tables/segments.csv`,
`still_fixes.csv.gz`), the default-smoother run `D:\Field2026_analysis_out\2026c\wiser_default_smoother_20261002_1626`
(S1 hidden masks/seeds, S2/S5 machinery), the WISER fix caches `D:\Field2026_analysis_out\2026c\wiser_fix_cache\`. No
SQLite and no raw IMU access are needed.

## Verification

- `--selftest` (synthetic, no field data): still periods + OU walking + anchor-dependent noise + outliers + a planted
  15-in WISER drift lasting 8 s inside a long still run + a planted 15-in excursion lasting 3 s + a planted false-still
  2-s run during walking. Checks: no-ZUPT kernel = B2 (≤ 1e-6 in); V1b = B2 ≥ 3 s from any ZUPT fix (≤ 0.05 in); erosion
  and minimum-run logic; release fires on the 8-s drift, not on the 3-s excursion; the 2-s false-still run gets no ZUPT;
  E1–E3 evaluators on planted cases; the grouped-vs-pooled quantile check.
- Reproduction: B2 rebuilt by the V1b driver equals the audit's saved B2 track (max |Δ| ≥ 60 s from the window edges);
  default-smoother S5 event counts reproduced.

## Outputs

- Bulk `D:\Field2026_analysis_out\2026c\wiser_v1b_<ts>\`: `tracks/<SFxx>_<period>.npz` (V1b, V1b-noRelease, V1b-raw,
  ZUPT mask, release mask at every fix), `tables/` (E1 profile and quantiles, E2 events and lags, E3 jumps, still metrics,
  release accounting, false-still probe, S1, S3, NIS), `summary.json`, `input_provenance.json`, `log.txt`.
- Report `results/2026c/wiser_baseline/reports/wiser_baseline_v1b_2026c.md` (+ figures
  `results/2026c/wiser_baseline/figures/wiser_baseline_v1b_*_2026c.png`), pointer `run_manifest_v1b_2026c.json`. Order:
  executive summary (verdict + key numbers), E1–E3 table, reported sections, "do not do", Definitions, caveats.
- `change_log/2026-10-03-wiser-v1b-zupt.md`. The main session updates CLAUDE.md and both index READMEs. No commit.

## Caveats known in advance

The pilot's B2 parameters were tuned on 2026-09-08/09 (a calm audit night). Still metrics are circular. Certified
stillness is ≥ 95 % in the houses. B2 is not the truth in motion: E1 tests that V1b *equals* B2 there, not that either is
right (step B builds an independent speed reference). The 1-s pilot still class has an unknown false-still rate; the
guards and the probe address it only partly.

## Amendments

Amendments 1–5 were made on 2026-10-03 at 11:24 local (file time 11:24:20), **before any pooled V1b number was seen**
(after the synthetic selftest and two single-animal smoke tests only; the field run `wiser_v1b_20261003_1124` was started
right after). None changes a candidate, a threshold or the decision rule. Note 6 was added after the pooled numbers.

1. **Selftest bound "V1b = B2 ≥ 3 s from any ZUPT fix (≤ 0.05 in)" is read on the p99** (the E1a statistic), the max is
   printed. On the synthetic track the V1b − B2 difference decays smoothly with the time from the last ZUPT fix (the
   smoother's impulse response; p99 0.29 → 0.07 → 0.04 → 0.02 in at 2 / 3 / 4 / 6 s, seed 7), so the max over all
   fixes ≥ 3 s sits at 3.0–3.2 s and is ≈ 2 × the p99 (0.076 vs 0.038 in). The bound was ambiguous between max and p99;
   the p99 matches E1a. A second selftest check that was not in this plan ("V1b cuts the still fake path by > 80 %")
   was replaced by a sanity check (V1b below B2): with σ_ZUPT = 1 in/s and B2's q = 3 in²/s³ the steady-state velocity
   SD under the ZUPT is ≈ 0.7 in/s, so V1b removes ≈ 65 % of B2's synthetic fake path, not ≈ 97 % as V1 (σ 0.25, q 1).
2. **Release, operational details [op]:** the reference uses the eroded interval's first 5 s (fewer than 10 fixes
   there → its first 10 fixes; fewer in total → all); centres on a 0.25-s grid inside the eroded interval; the centred
   5-s window [c − 2.5, c + 2.5) uses every raw fix (not only those of the run) and needs ≥ 5 fixes, else the centre is
   undefined and ends a stretch ("continuously"); "for > 5 s" = span (last − first centre) > 5 s, i.e. ≥ 22 centres; an
   interval ≤ 5 s long cannot release. For S1 the release is recomputed from the visible fixes only.
3. **NIS [op]:** from the final forward pass of each smoother, with the predicted state and the nominal (unweighted)
   anchors_used noise, for every visible window fix in the analysis mask; zone of a fix = B2 position inside a house
   ROI grown by 14 in (else outside); strata anchors {≤ 6, 7, 8, 9} × zone × IMU state of the aligned second (still /
   active / locomoting / QC failed), plus marginals by exact anchors_used.
4. **"Certified" for the release accounting and the false-stillness probe [op]:** the primary source of the period
   (gate-v2 strict on 09-08, S50 elsewhere) — segments ≥ 10 s (the ≥ 30-s subset reported) and, for the probe, also
   windows ≥ 1 s. A release is inside when its first centre lies in such a segment. Probe seconds = QC-ok still
   seconds in the analysis mask overlapping no such window or segment; "WISER 5-s displacement" = the B2 displacement
   over the 5 s centred on the second.
5. **Inputs [op]:** the fixes are read as float64 from the WISER fix caches (exactly the audit's inputs; the saved
   tracks hold float32 raw, ≤ 1e-4 in apart) and B2 is rebuilt from them by the new kernel; E1b and E2 reuse the
   default-smoother code paths (S2 subsets: IMU-locomoting = state 3, WISER-fast inside the analysis mask; S5 paired
   events where both lags are defined); the E1a p99 CI uses a 0.001-in histogram inside the block bootstrap
   (seed 20261006).
6. **Note, made after the pooled numbers (2026-10-03 ≈ 11:50; reported diagnostics only, no effect on E1–E3 or the
   decision):** the report adds (a) an E1b subset "WISER-fast without the IMU-still seconds", to show where the rain
   WISER-fast p50 change (−2.4 %) comes from; (b) per-event change counts for E2 (events changed, direction, events whose B2
   crossing lay inside the IMU-still run), because the pre-registered median Δ is 0 while 16–29 % of events shift;
   (c) "Reading" paragraphs. The first full aggregation stopped in a figure (negative error bars where an exact point
   estimate lay outside its histogram-bootstrap CI); the bars are clipped at 0 and the report was regenerated with
   `--report-only` from the same compute outputs.
