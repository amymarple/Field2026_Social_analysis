# Head-IMU speed reference, independent of the WISER smoother (cohort 2026c)

**Status:** PLANNED 2026-10-03, written before any number of this step was computed. Runs after step A (V1b) so that V1b
is among the re-scored tracks.
**Approval:** step B of the A → B → C sequence the user approved on 2026-10-03 ("干吧") after the Fable SOTA audit (Q2,
Q5: the speed criterion S2 had no truth — it was defined relative to B2; a VeDBA / stride-band speed proxy is the
standard telemetry answer and also gives ephys a high-rate speed signal). Operational details are marked **[op]**.
**Direction:** `wiser_baseline`. **Driver:** new `wiser/scripts/analyze_imu_speed_proxy.py`. **Config:** new
`wiser/configs/imu_speed_proxy_2026c.json` (fitted models summarised in a `fitted` block).

## Why

The default-smoother step could not say whether B2 under-follows real movement or V2b over-follows it (S2: B2′/V1
−15 %, V2 +10 %, V2b +28 % at the 1-s p50 on IMU-locomoting seconds, where B2's median is only 3.0 in/s). Two
smoother-independent references exist: (i) on **clean** WISER stretches (many anchors, open field, no jumps), speed over
a 3-s baseline from medians of raw fixes is nearly model-free; (ii) the head IMU, once calibrated against (i), predicts
speed everywhere (houses, low anchors, rain), independently of WISER.

## Established facts (not re-derived)

make_imu 50-Hz npz per session (`D:\3rd_rat_spikes\analysis\imu\<SFxx>\<session>.imu.npz`: `t_pc_ms`, `vedba_ms2`,
`omega_dps`, `turn_dps`, `pitch_deg`, `roll_deg`, `quat_wxyz`, `lin_acc_earth_ms2`, QC flags `saturated`, `unreliable`,
`frozen`, `invalid`); the failure audit's per-second IMU QC/states (`imu_seconds/`) and exclusions; WISER fix caches
(`wiser_fix_cache/<period>/<SFxx>.csv.gz`: `t_ms`, `x`, `y`, `anchors_used`, `anchors_list`, `valid`,
`speed_inps_smooth`, masks); fix times aligned by τ* (0.10–0.20 s). Raw WISER per-axis static SD for 8–9 anchors ≈ 1.6–3.7
in. 90 % of head horizontal-acceleration variance is > 2 Hz; the pilot's locomotion class (VeDBA ≥ 3.93 m/s², 4–7 Hz
stride-band fraction ≥ 0.10) has TPR 0.75 / FPR 0.15 against WISER speed. House ROIs: `wiser/configs/wiser_rois.json`
(+ 14 in).

## Reference 1 — clean WISER speed (target)

For integer second s: $\mathbf m(t)$ = coordinate-wise median of the raw fixes with aligned time in $[t-0.5, t+0.5)$ s
(≥ 3 fixes); $u_3(s)=\lVert\mathbf m(s+1.5)-\mathbf m(s-1.5)\rVert/3$ s (in/s). **Clean** second **[op]**: every fix in
$[s-2, s+2]$ has `anchors_used` ≥ 8 and is `valid`, no jump (> 30 in within ≤ 0.35 s) in that span, fix rate ≥ 3 Hz,
both medians ≥ 14 in outside the house ROIs, the second IMU-QC-ok, not in an exclusion. A 1-s variant $u_1$ uses
medians over $[t-0.375, t+0.375)$ (≥ 3 fixes) at $s\pm0.5$. **Noise floor:** the same estimators on certified still
segments with ≥ 8 anchors (true speed 0) give the floor distribution at each scale (reported; note the still segments are
in the houses).

## Reference 2 — IMU speed proxy

**Features [op]** per second, from the 50-Hz npz over centred windows of 1 s and 3 s: VeDBA mean and p90; horizontal
earth-frame dynamic acceleration RMS (0.5–8 Hz); vertical earth-frame acceleration power in 2–8 Hz, its peak frequency
and its share of 1–20 Hz (stride band); |ω| mean; |turn rate| mean; pitch SD; QC share. Features are cached once
(**`<OUT>/2026c/imu_speed_features/<SFxx>/<period>.csv.gz`** + README) so later models never re-read the npz.

**Models (pre-registered):** M1 = per-animal ordinary least squares of $u_3$ on [VeDBA mean, stride-band power, stride
peak frequency, |ω| mean] (transparent); M2 = pooled `HistGradientBoostingRegressor` (absolute-error loss) on all
features + animal one-hot, hyper-parameters chosen on the tuning night from a fixed grid (learning rate {0.05, 0.1} ×
max depth {3, 5} × min leaf {50, 200}). The model with the lower tuning-night median absolute error is used **[op]**.
**Split:** train calm nights 09-05 and 09-06, tune 09-07, **test 09-08 (calm)**; rain nights 09-03 and 09-09 are a
robustness test. Days are excluded (few clean open-field seconds; rats rest in the houses).

**Validity rule (pre-registered), test night, clean seconds:** for $u_3$ ≥ 5 in/s — median absolute relative error
≤ 25 % **and** Spearman ρ ≥ 0.7; and on clean IMU-locomoting seconds the proxy's p50 and p95 within ± 10 % of $u_3$'s.
Pass → "valid at the 3-s scale"; the same rule with $u_1$ decides "valid at the 1-s scale" (reported; expected harder).
Fail → the proxy is reported as not valid and is **not** used to judge smoothers.

## Re-scoring the smoothers' speed (the purpose)

Tracks: raw, B1, B2, B2′, V1, V2 (audit), V2b (default-smoother run), V1b (step A run) — all audit periods' nights
**[op: nights only, where clean open-field movement exists]**. For each track, speeds at the 1-s and 3-s scales computed
the same way as the references (from the track instead of raw-fix medians).

- **R1 — against clean WISER speed (direct, smoother-independent):** on clean seconds, per track: bias of p50 and p95
  (ratio − 1), median absolute error vs $u_3$ / $u_1$, by speed band (< 5, 5–15, > 15 in/s); paired 10-min block-bootstrap
  CIs.
- **R2 — against the IMU proxy (only if valid at that scale):** on all IMU-QC-ok non-still seconds (houses, low anchors,
  rain included) and on the IMU-locomoting subset: per track, p50/p95 ratio to the proxy's, with CIs.

**Reading (pre-registered):** the track whose p50 and p95 are closest to the reference (both R1 and, if valid, R2) is
called **least biased in speed**; a track whose ratio CI excludes ± 10 % in R1 is called **biased**. No change of the
default is made in this step: if the least-biased track is not the current default, that is a proposal to the user.

## Deliverable for ephys (only if valid at the 1-s or 3-s scale)

The chosen model applied to every QC-ok second of the audit nights → `<OUT>/2026c/imu_speed_proxy/<SFxx>/<period>.csv.gz`
(second, speed_hat, scale, QC) + README. Whole-cohort application is a later step on request.

## Verification

- `--selftest` (synthetic): a planted walking/still/in-place-activity sequence with a known IMU → speed law and WISER-like
  noise → the clean filter selects the right seconds, $u_3$ recovers the planted speed within the floor, M1 recovers the
  planted coefficients, the validity rule passes/fails on planted good/bad proxies, R1 detects a planted ×0.85 speed-damped
  track as biased.
- Reproduction: the per-second IMU QC/state of the audit's `imu_seconds` is reproduced from the npz for a sample.

## Outputs

- Bulk `D:\Field2026_analysis_out\2026c\imu_speed_proxy_<ts>\`: `tables/` (clean seconds, references, model fits, test
  metrics, R1/R2 tables, bootstrap), `models/` (pickled fits + feature list), `summary.json`, `input_provenance.json`,
  `log.txt`; caches above.
- Report `results/2026c/wiser_baseline/reports/wiser_baseline_imu_speed_proxy_2026c.md` (+ figures), pointer
  `run_manifest_imu_speed_proxy_2026c.json`. `change_log/2026-10-03-imu-speed-proxy.md`. The main session updates CLAUDE.md
  and both index READMEs. No commit.

## Caveats known in advance

The proxy is calibrated on open-field clean WISER and then applied in the houses and in the rain, where the head's motion
mix differs (more in-place activity); its validity there is assumed, not shown. The clean filter selects good conditions,
so R1 says nothing about speed under poor anchors. Head speed ≠ body speed (head scanning adds path); the 3-s scale
partly averages it out. The locomotion class used for subsets was itself fitted against WISER speed.

## Amendments

### Amendment 1 (2026-10-03, written before any number of this step was computed) — operational details

Ambiguities resolved by the closest faithful option; no definition, split, threshold or reading rule is changed.

1. **Time label.** "Second $s$" is the field-PC second $[s, s+1)$ of the audit's `imu_seconds` (the unit of the IMU QC
   and states). The plan's formulas are applied with their time origin at its centre $c = s + 0.5$:
   $u_3(s)=\lVert\mathbf m(c+1.5)-\mathbf m(c-1.5)\rVert/3$ with medians over $[s-1.5, s-0.5)$ and $[s+1.5, s+2.5)$;
   $u_1(s)$ from medians over $[s-0.375, s+0.375)$ and $[s+0.625, s+1.375)$; clean span $[c-2, c+2] = [s-1.5, s+2.5]$;
   IMU feature windows $[s, s+1)$ (1 s) and $[s-1, s+2)$ (3 s). This aligns the reference, the IMU QC second, the
   feature windows and the default smoother's 1-s speeds (centred at $s + 0.5$).
2. **Clean second.** "Not in an exclusion" = the audit's per-second `ok` of second $s$ (IMU QC, handling ± 5 min,
   all-tag silences ± 2 min, tag validity, ADC lane) **and** no fix in the span carrying a fix-cache mask (`m_handling`,
   `m_silence`, `m_tag_validity`, `m_adc_lane`); "no jump in that span" = no consecutive raw-fix pair > 30 in apart within
   ≤ 0.35 s with at least one of its two fixes in the span; "fix rate ≥ 3 Hz" = ≥ 12 fixes in the 4-s span; "≥ 14 in
   outside the house ROIs" = outside `house_1` and `house_2` grown by 14 in on every side (the library's buffered
   membership, `wiser_analysis_utils._rect_membership`). Fix times are the aligned times ($t - \tau^*$). $u_1$ uses the same
   clean seconds and additionally needs its two medians.
3. **Noise floor.** Certified still segments = the audit's primary, scored segments ≥ 30 s (`tables/segments.csv`),
   trimmed by 1 s at both ends; a floor second's 4-s span lies inside the trimmed segment and meets every clean-second
   condition except the outside-house one; all ten audit periods (days and nights), reported pooled and by kind × set.
4. **Features.** Valid 50-Hz samples = the audit's sample QC (`analyze_wiser_failure_audit.sample_valid`: finite,
   not saturated / frozen / invalid / unreliable, no frozen-rule run, outside handling, silences, ADC lane and the tag
   window). Time-domain features use the valid samples of the window and need ≥ 50 % of them, else NaN. Spectral
   features need an ungapped window of exactly $50w$ samples with ≥ 90 % valid (invalid samples set to the window mean),
   demeaned, Hann taper, one-sided periodogram $P_k = 2\lvert X_k\rvert^2 / (N\sum w_n^2)$ ((m/s²)² per bin); power in
   2–8 Hz = $\sum P_k$ over bins in $[2, 8]$ Hz, share = that / the sum over $[1, 20]$ Hz, peak frequency = the bin of the
   largest $P_k$ in $[2, 8]$ Hz (1-Hz resolution at 1 s, 1/3 Hz at 3 s). Horizontal RMS = RMS over the valid samples of
   $\lVert(a_x, a_y)\rVert$ after a zero-phase order-4 Butterworth band-pass 0.5–8 Hz on each contiguous run (invalid
   samples zeroed before filtering). QC share = valid samples / $50w$.
5. **Models.** M1 has an intercept, needs its four features finite, is fitted on the training nights only. M2: other
   hyper-parameters at scikit-learn 1.7.2 defaults (`max_iter` 100, `early_stopping` 'auto'), `random_state` 0, animal
   one-hot, fitted on the training nights only (no refit after tuning). Both predictions are clipped at 0 in/s. The
   tuning-night comparison uses the clean tuning seconds where both models predict. **1-s scale:** the same two model forms
   fitted to $u_1$ — M1 on the 1-s-window versions of its four features, M2 on all features — and chosen separately by the
   tuning-night median absolute error at that scale (the plan states the models for $u_3$ only).
6. **Validity.** Point estimates decide; 10-min block-bootstrap CIs are reported.
7. **Re-scoring.** A track's speed uses the reference's median estimator on the track's positions at the fix times
   (≥ 3 fixes per median window). V1 and V2 are the audit's saved forms, V2b the default-smoother deployable form (B2 at
   IMU-failed fixes), V1b step A's. On clean seconds `raw` *is* the R1 reference (identity check, ratio 1 by
   construction), so "least biased" is chosen among the seven smoothed tracks; raw stays in R2. R1 primary cell = all six
   nights pooled, 3-s scale, all clean seconds; speed bands use the reference speed of that scale; calm / rain and the
   1-s scale are secondary cells. "Closest" = smallest $\max(\lvert d_{50}\rvert, \lvert d_{95}\rvert)$. "Biased" = the
   95 % CI of $d_{50}$ or $d_{95}$ lies entirely above +10 % or entirely below −10 % (decided on the primary cell,
   reported for every cell). R2 (nights only) uses the seconds where every track's speed and the proxy are defined. If R1
   and R2 name different tracks, both are reported and no single track is called least biased.
8. **Deliverable.** Long format: one row per QC-ok second and valid scale (`sec`, `speed_hat`, `scale`, `qc`, `ok`).

### Note 2 (2026-10-03, after the results; reporting only)

Run `D:\Field2026_analysis_out\2026c\imu_speed_proxy_20261003_1210`: compute 12:10, models frozen by the fit stage at 12:11
(tuning night only), first test-night / rain-night numbers at 12:12. After the results the report gained (a) a reading-aid
section explaining that the R1 primary cell is decided by p50 while the reference p50 (1.68 in/s at 3 s) sits at the noise
floor's p95 (1.64 in/s), so every smoother's negative p50 Δ mixes noise removal with under-following, plus a table of the
already-computed p95 and speed-band cells; (b) the note that B1 is closest partly by construction (a raw-fix median like the
reference); (c) figure layout fixes (histogram weights, hexbin range). No definition, threshold, split, model, verdict or
label was changed; the report was regenerated with `--report-only` from the same frozen models.
