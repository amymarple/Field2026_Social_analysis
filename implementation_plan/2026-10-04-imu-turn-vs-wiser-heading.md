# Phase 0 of turn-aided WISER: does the head gyro's turn track the WISER heading change? (cohort 2026c)

**Status:** PLANNED 2026-10-04, written before any number of this step was computed.
**Approval:** the user asked whether left turns etc. could be extracted from the IMU and given to WISER, and approved this
feasibility step on 2026-10-04 ("做"), with the agreed follow-up: pass → the turn annotation is usable during locomotion
and a turn-rate-aided smoother (V7) is built and tested like V3/V6; fail → head turns stay a head-behaviour signal only.
Operational details are marked **[op]**.
**Direction:** `wiser_baseline`. **Driver:** new `wiser/scripts/analyze_imu_turn_vs_heading.py`. **Config:** new
`wiser/configs/imu_turn_vs_heading_2026c.json` (verdict in `decision`).

## Why (established facts, not re-derived)

- V6 closed the **acceleration**-fusion line: the head's ≤ 2-Hz horizontal acceleration in locomotion is ≈ 4× the body's
  (head sweeps scale with ω²) plus tilt leak, and the absolute heading offset ψ between the IMU and WISER frames is
  unobservable. A **turn rate** is different: the gyro measures rotation directly (no double integration, no gravity leak;
  the vertical projection is insensitive to a ≤ 1.5° tilt error), bias drift ≈ 1.6–2.1 °/min (≈ 0.03 °/s, negligible over
  seconds), and a *relative* heading change needs no ψ.
- make_imu already writes the signed turn rate about the vertical `turn_dps` (50 Hz, **+ = counter-clockwise seen from
  above**) and per-second `turn_net_deg` / `turn_abs_deg` (`D:\3rd_rat_spikes\analysis\imu\<SFxx>\<session>.imu.npz` /
  `.imu_1s.csv`, field-PC time `t_pc_ms`).
- WISER heading at low speed is noise-dominated (spurious turns, cf. GPS telemetry); a turn in place is invisible to WISER.
  Head yaw ≠ body heading during scanning — this step measures how far they agree **during locomotion**.
- Step B's clean seconds (`D:\Field2026_analysis_out\2026c\imu_speed_proxy_20261003_1210`: all fixes ≥ 8 anchors, open
  field, no jumps, ≥ 3 Hz; 6 nights 09-03, 09-05 … 09-09) and its 1-s median estimator: $\mathbf m(t)$ = coordinate-wise
  median of raw fixes in $[t-0.5, t+0.5)$ s; floor of $u_1$ p50 / p95 1.90 / 5.26 in/s. Fix times are aligned by τ*.

## Quantities

- **WISER heading** at centre c: $\theta(c)=\operatorname{atan2}$ of $\mathbf d(c)=\mathbf m(c+0.5)-\mathbf m(c-0.5)$ (1-s
  displacement of raw-fix medians; smoother-independent), defined when $\lVert\mathbf d(c)\rVert/1\,\text{s}\ge$ **10 in/s**
  **[op]** and both medians exist on clean seconds. Secondary: the same from the V3 track.
- **Gyro heading:** $\psi(t)=\int\texttt{turn\_dps}\,dt$ (unwrapped, IMU-QC-ok samples only), and its 1-s mean
  $\bar\psi(c)$ over $[c-0.5, c+0.5)$ — the same averaging window as θ(c).
- **Pairs:** for separations W ∈ {1, 2, 3} s, $\Delta\theta=\operatorname{wrap}(\theta(c+W/2)-\theta(c-W/2))$ and
  $\Delta\psi=\bar\psi(c+W/2)-\bar\psi(c-W/2)$, centres c on a 0.5-s grid, both ends clean, IMU-QC-ok throughout
  **[op]**; $\Delta\psi$ is wrapped the same way for the residual $r=\operatorname{wrap}(\Delta\theta-b\,\Delta\psi)$.
- **Fit:** OLS of $\Delta\theta$ on $\Delta\psi$ through the origin and with intercept (gyro = regressor; it is the less
  noisy one), slope b, $R^2$, residual median |r| and p90 (degrees); circular correlation as a check. Pairs with
  $|\Delta\psi|>150°$ are reported but excluded from the fit (wrap ambiguity) **[op]**. 10-min block bootstrap CIs.
- **Expected heading noise:** $\sigma_\theta\approx\sigma_d/\lVert\mathbf d\rVert$ with $\sigma_d$ from the $u_1$ floor —
  reported per speed band (10–20, > 20 in/s) as the ceiling an ideal gyro could reach.

## Pre-registered gate

On the pooled **calm** nights (09-05, 09-06, 09-07, 09-08), W = 2 s, raw-median heading: **|b| ∈ [0.8, 1.2] and
R² ≥ 0.5** → **PASS**: head yaw is a usable body-turn signal during locomotion. The sign of b fixes the convention
(b ≈ +1: WISER heading increases counter-clockwise like the gyro; b ≈ −1: the WISER plan view is mirrored relative to
"seen from above" — then a left turn is negative in WISER). Otherwise **FAIL**.

**Negative control:** the same with the gyro shifted by + 1 h (expected b ≈ 0, R² ≈ 0); if the control gives R² ≥ 0.1 the
analysis is declared invalid (a pipeline artefact).

## Reported, not part of the gate

- W = 1 and 3 s; rain nights 09-03 and 09-09; per animal; per speed band; V3-track heading instead of raw medians.
- **Turn-sign agreement:** for pairs with |Δψ| ≥ 30°, the share with the same sign in WISER (after the convention from b);
  confusion table for left / right / straight (|Δ| < 15°).
- **Scanning tail:** share of pairs with |r| > 30° (head turned without the path turning).
- **What WISER misses:** gyro turns ≥ 90° within 3 s while the 1-s WISER speed stays below the $u_1$ floor p95
  (turns in place) — count per IMU-ok hour, calm | rain, house | open field.
- Lag check: b and R² for gyro shifts of −0.5 … +0.5 s (peak should be at ≈ 0 after τ*).

## Data

Read-only: make_imu npz (`turn_dps`, QC flags, `t_pc_ms`), step-B clean seconds and the failure-audit `imu_seconds/`
(QC, states), the WISER fix caches, V3 tracks (`D:\Field2026_analysis_out\2026c\wiser_v3_20261003_1425\tracks\`).

## Verification

- `--selftest` (synthetic): a path with known turns and a head yaw = path heading + scanning oscillation (± 25° at 1.5 Hz)
  + gyro bias 2 °/min; WISER-like fixes with anchor noise → the estimator recovers b ≈ 1 within 0.05 and R² close to the
  analytic value; mirrored axes give b ≈ −1; the + 1 h control gives b ≈ 0; wrap handling on a planted 170° turn.

## Outputs

- Bulk `D:\Field2026_analysis_out\2026c\imu_turn_vs_heading_<ts>\`: `tables/` (pairs, fits, bootstrap, sign agreement,
  in-place turns, lag scan), `summary.json`, `input_provenance.json`, `log.txt`.
- Report `results/2026c/wiser_baseline/reports/wiser_baseline_imu_turn_vs_heading_2026c.md` (+ figures), pointer
  `run_manifest_imu_turn_vs_heading_2026c.json`; `change_log/2026-10-04-imu-turn-vs-heading.md`. The main session updates
  CLAUDE.md and both index READMEs and commits.

## Caveats known in advance

Clean seconds are open-field and ≥ 8 anchors: agreement in the houses is not measured. The 10-in/s heading threshold
selects locomotion; slow walking is excluded by construction. Raw-median heading carries WISER noise (attenuates R²
toward 0 — conservative). Head yaw includes scanning; the 1-s averaging removes part of it.

## Amendment 1 (2026-10-04, written while implementing, BEFORE any number of this step was computed)

Operational resolutions of details the plan leaves open; quantities, thresholds and the gate are unchanged.

1. **Scope.** The six step-B nights (21:00–04:20; calm 09-05/06/07/08, rain 09-03/09), animals SF07, SF08, SF09, SF10,
   SF12 (the failure audit's). Fix times $t_{al}=t-\tau^*$ as in step B; medians need ≥ 3 fixes (step B's `min_fix`).
2. **Grid.** Heading centres $h$ and pair centres $c$ lie on the 0.5-s grid of whole field-PC seconds from the night start.
3. **"Both medians exist on clean seconds"** = both medians exist and every field-PC second overlapping the heading's
   support $[h-1,h+1)$ is a step-B clean second (`clean` of the step-B seconds tables: ≥ 8 anchors, valid, unmasked, no
   jump, ≥ 3 Hz over the second's ± 2 s, both u3 medians outside the houses + 14 in, IMU second ok).
4. **"IMU-QC-ok throughout"** = every 50-Hz sample of $[h_1-0.5,\ h_2+0.5)$ ($h_{1,2}=c\mp W/2$) passes the failure
   audit's sample QC (`analyze_wiser_failure_audit.sample_valid`: finite, not saturated / frozen / invalid / unreliable,
   frozen rule, handling ± 5 min, all-tag silences ± 2 min, ADC lane, tag window), with no gap > 1.5 samples and the span
   covered to within 1.5 samples at both ends. $\bar\psi$ = mean of $\psi$ over the 50-Hz samples in the window.
5. **Which fit decides.** The gate uses the fit **through the origin** (the model behind $r$), with
   $R^2=1-\sum(\Delta\theta-b\Delta\psi)^2/\sum(\Delta\theta-\overline{\Delta\theta})^2$ (centred total sum of squares; never
   larger than the intercept fit's $R^2$, so conservative). The fit with intercept (slope $b_1$, intercept $a_1$,
   $R^2_1$ = squared Pearson r) is reported beside it; if the two disagree on the gate the report says so.
6. **Residual statistics** (median |r|, p90, scanning tail |r| > 30°) use all pairs of a subset (including
   $|\Delta\psi|>150°$, wrapped as the plan says) with the subset's own through-origin $b$.
   $\operatorname{wrap}(x)=((x+180)\bmod 360)-180$. **Circular correlation** = Jammalamadaka–SenGupta $\rho_c$ on the fit set.
7. **Turn-sign agreement** over $30°\le|\Delta\psi|\le150°$ (the sign of a > 150° turn is wrap-ambiguous), convention
   $\sigma=\operatorname{sign}$ of the pooled calm W = 2 slope, used for every subset (so a per-animal mirror shows up as
   disagreement). **Confusion table** on the fit set: gyro left $\Delta\psi\ge15°$, right $\le-15°$, straight otherwise;
   WISER the same on $\sigma\,\Delta\theta$.
8. **Bootstrap.** 1000 replicates, blocks = 10 min from the night start per (animal, night), seed 20261004, CI = 2.5–97.5 %;
   every statistic is recomputed per replicate (residual quantiles with the replicate's $b$).
9. **Speed band of a pair** = by the slower of its two end speeds: [10, 20) or ≥ 20 in/s.
10. **Expected heading noise.** $\sigma_d$ (per coordinate) is estimated with this plan's own estimator (1-s medians at
    $h\pm0.5$) on the step-B floor seconds (`floor_ok`: certified still) of the six nights, per set:
    $\sigma_d=\operatorname{median}\lVert\mathbf d\rVert/\sqrt{2\ln2}$ (Rayleigh). Step B's quoted u1 floor used 0.75-s medians, so
    its p50 1.90 in/s (→ $\sigma_d$ 1.61 in) is shown for reference only. Per pair end $\sigma_\theta=\sigma_d/\lVert\mathbf d\rVert$
    (rad); ceiling $R^2_{\max}=1-\overline{\sigma_{\theta,1}^2+\sigma_{\theta,2}^2}/\operatorname{Var}(\Delta\theta)$ per band
    (independent ends assumed; approximate at W = 1, where both headings share $\mathbf m(c)$).
11. **+1 h control.** The gyro input is taken from $t+3600$ s (the V4/V6 convention), with the sample QC at the shifted
    time; calm W = 2 pairs whose shifted span is QC-ok; fitted exactly as the main fit.
12. **Lag scan.** Gyro input from $t+\delta$, $\delta\in\{-0.5,-0.4,\dots,+0.5\}$ s, on one common pair set (calm, W = 2,
    raw; QC-ok at all 11 shifts); peak = the $\delta$ with the largest $R^2$.
13. **Turns WISER misses.** $\psi$ on a 0.1-s grid (linear interpolation of the cumulative 50-Hz integral); a grid point is a
    candidate when $|\psi(t+3)-\psi(t)|\ge90°$ and $[t,t+3)$ is QC-ok (item 4); a turn event = a run of consecutive
    same-sign candidates, window $[t_{first}, t_{last}+3]$. Missed by WISER = every second overlapping the window has
    step-B $u_1<5.26$ in/s (the all-period u1 floor p95 quoted in the plan); "WISER moving" if any $u_1\ge5.26$;
    "no WISER" if any $u_1$ is missing. Zone = the median raw fix of the window (house ROIs + 14 in, the clean rule's
    buffer). Denominator = IMU-ok seconds (audit `ok`) per stratum, zone of a second from the 1-s median of its raw fixes
    (unknown if < 3 fixes).
14. **V3 heading** = the same estimator on the V3 track (`wiser_v3_20261003_1425/tracks`, at the fix times), V3 speed
    ≥ 10 in/s, same clean-second and IMU rules.
15. **Point estimates decide** the gate and the control (as in steps A/B and V3); the bootstrap CIs are reported beside them.

## Amendment 2 (2026-10-04, after a single-job smoke test, BEFORE any pooled number or gate quantity was seen)

The smoke test (SF09, night 09-06: plumbing and runtime only) showed that step B's $u_1$ is missing on 35 % of the IMU-ok
seconds (0.75-s medians need ≥ 3 fixes; almost all missing seconds have < 3 Hz), so the rule of Amendment 1.13 — "no
WISER" if *any* overlapping second lacks $u_1$ — put 60 % of that night's turn events into "no WISER" and left the plan's
quantity (turns WISER misses while its speed stays below the floor) nearly uncountable. Changed, closest to the plan's
wording: an event has **WISER coverage** when $u_1$ exists on at least half of the seconds overlapping its window
($\lceil n/2\rceil$); with coverage, **missed** = every available $u_1<5.26$ in/s, **WISER moving** = some available
$u_1\ge5.26$; without coverage, "no WISER". Nothing else changes; only that night's per-class event counts were seen.

## Amendment 3 (2026-10-04, AFTER the pooled results of the first full run were seen; no gate quantity changes)

First full run `imu_turn_vs_heading_20261004_1007` (superseded by the rerun named in the report):
gate FAIL (b +0.642, R² 0.196, control R² −0.001).

i. **Storage fix.** The bulk CSVs had written unix-second times at 5–6 significant digits, so the stored pair centres and
   event times were rounded. They are now stored as integer ms (`c_ms`, `t0_ms`, `t1_ms`, plus `dur_s`). Every number was
   computed in memory before writing, so nothing changes.
ii. **Zone of a second in the turns-in-place denominators.** Amendment 1.13 took the zone of an IMU-ok second from the 1-s
    median of its fixes. That left 33 h (calm) of seconds "unknown", while event zones come from windows ≥ 3 s, so the
    field/house numerators included events from seconds counted as "unknown" in the denominators. The zone of a second is now
    the median raw fix of $[s-1,s+2)$ (≥ 3 fixes), the shortest event window. First-run values, for the record: calm missed
    per IMU-ok hour 46.1 (field), 24.3 (house), 27.4 (all zones); rain 20.1 (all zones). The all-zone rates, the event
    classification and every gate quantity are unchanged.
iii. **Reading only.** The plan's noise ceiling (σ_d from still seconds) is reported as specified. A declared post-hoc
     caveat is added: the V3-track heading reaches a much higher R² than the raw medians, so heading noise during
     locomotion exceeds the still floor and the ceiling is an upper bound.
