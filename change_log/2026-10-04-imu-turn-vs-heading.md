# 2026-10-04 — Phase 0 of turn-aided WISER: the head gyro's turn does not track the WISER path turn well enough → FAIL, no V7

**Plan:** [`implementation_plan/2026-10-04-imu-turn-vs-wiser-heading.md`](../implementation_plan/2026-10-04-imu-turn-vs-wiser-heading.md)
(approved by the user 2026-10-04, "做"; committed 5281fc6 before any result). Amendment 1 (operational resolutions) was
written before any number. Amendment 2 (turns-in-place coverage rule) came after a single-job smoke test, before any pooled
number. Amendment 3 came after the first full run's pooled numbers; no gate quantity changed: (i) a CSV time-precision fix,
(ii) the zone window of the in-place denominators, (iii) a declared post-hoc caveat on the noise ceiling.
**Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_imu_turn_vs_heading_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_imu_turn_vs_heading_2026c.md)
(gate table, reading, 11 sections, full Definitions; figures `wiser_baseline_imu_turn_vs_heading_{scatter,animals,lag,ceiling}_2026c.png`).
**Driver / config:** `wiser/scripts/analyze_imu_turn_vs_heading.py` (`--selftest` ALL PASS, `--report-only <run_dir>`);
`wiser/configs/imu_turn_vs_heading_2026c.json` (verdict in `decision`).
**Bulk:** `D:\Field2026_analysis_out\2026c\imu_turn_vs_heading_20261004_1010\` (the first run `…_1007` has identical gate
numbers and is superseded by Amendment 3); pointer `results/2026c/wiser_baseline/reports/run_manifest_imu_turn_vs_heading_2026c.json`.

## Decision

**FAIL** (pre-registered gate: calm nights 09-05…09-08, W = 2 s, raw-median WISER heading, fit through the origin;
point estimates decide). Per the plan, head turns stay a **head-behaviour signal only**: no turn-rate-aided smoother (V7)
is built. **V3 stays the default WISER track for the implanted animals, B2 the universal baseline.** Nothing was tuned.

| quantity | value [95 % CI] | rule | met |
|---|---|---|---|
| slope b | **+0.642** [+0.485, +0.767] | \|b\| ∈ [0.8, 1.2] | no |
| R² (centred) | **0.196** [0.109, 0.291] | ≥ 0.5 | no |
| +1 h control | b +0.004, R² −0.001 [−0.009, 0.005] | R² < 0.1 | yes (valid) |
| pairs | 996 in the fit (291 ten-minute blocks, 20 animal-nights) | | |

The intercept fit agrees (b₁ +0.643, a₁ −1.6°, R²₁ 0.197 → FAIL).

## Reported (not the decision)

- **W = 1 / 3 s (calm):** b +0.71 / +0.50, R² 0.11 / 0.15. **Rain W = 2 s:** b +0.55, R² 0.08 (W = 3: b −0.03 on 102 pairs).
- **Sign / handedness:** b > 0 on 5/5 animals (calm), CI excluding 0 on 4/5 (SF07 +0.57 [−0.10, +1.17] on 83 pairs).
  Turn-sign agreement under the pooled convention has its CI above 50 % on 5/5 (SF07 82 % [65, 96]). So all five animals share
  the normal relation: WISER heading increases counter-clockwise like the gyro, i.e. the WISER plan view is right-handed,
  given make_imu's gyro sign convention. V6's "SF07 mirrored" (noise-level LLR) is not supported. Absolute left/right still
  rests on the undocumented chip convention; one video event with a known turn would close it.
- **Turn-sign agreement** (30° ≤ |Δψ| ≤ 150°, calm W = 2 s): 82.8 % [77.7, 86.9] (n 355); rain 75.0 %. Confusion table
  (gyro rows → WISER): left 62 % left / 21 % straight / 17 % right; straight 24 / 48 / 28 %; right 13 / 21 / 66 %.
- **Scanning tail** |r| > 30°: 34.8 % [29.4, 39.4] (calm W = 2 s); median |r| 19.7°, p90 70.7°; rain 42 %.
- **Speed bands** (calm W = 2 s): 10–20 in/s b +0.64, R² 0.19 (870 pairs); ≥ 20 in/s b +0.64, R² 0.36 [0.00, 0.82] (126 pairs).
- **V3-track heading** (calm W = 2 s): b +0.72 [+0.58, +0.83], R² 0.49 [0.30, 0.66], sign agreement 89.6 %. The gate's bars
  would not be met with it either.
- **Noise ceiling** (plan's model, σ_d from certified-still seconds: calm 1.50 in, rain 1.63 in): R²_max ≈ 0.98. **Post hoc
  (declared):** the V3 gain (R² 0.20 → 0.49, median |r| 19.7° → 11.6°) cannot come from still-floor noise. Raw-median heading
  noise during locomotion is therefore well above the still floor, and the ceiling is an upper bound. The slope shortfall,
  which Δθ noise does not cause, points to head-turn variance that is not path turn (scanning, head–body decoupling, head
  leading the path).
- **Lag scan** (calm W = 2 s, 1,002 common pairs): R² peaks at δ = −0.2 s (0.229 vs 0.196 at 0; gyro read earlier = the
  WISER path turn lags the head turn). This could be a heading-specific lag (head first) or a residual clock offset; the step
  cannot separate them. Reported, not acted on; the gate is not met at the peak either.
- **Per animal:** only SF12 meets both bars alone (calm b +0.96, R² 0.65, 61 pairs); SF08 b +0.48 / R² 0.07, SF09 +0.58 /
  0.18, SF10 +0.72 / 0.24, SF07 +0.57 / 0.13.
- **Turns WISER misses** (gyro ≥ 90° within 3 s while every available step-B u1 < 5.26 in/s, u1 on ≥ half of the event's
  seconds): calm **27.4 per IMU-ok hour** (open field 35.6, house 18.6), rain 20.1. That is 14 % of the calm turn events with
  WISER coverage (13 % overall); 18,113 of 58,969 events lack WISER coverage. Event windows overlap: 52 % of events start
  before the previous one ends (back-and-forth sweeps count once per direction), so these are events per hour under the
  rule, not counts of separate behaviours.

## Definitions (headline quantities; full set in the report)

Units: WISER inches (unverified offset origin), degrees, field-PC seconds (fix times − τ*).

- **1-s median** $\mathbf m(t)=\operatorname{med}\{\mathbf z_i: t_i\in[t-0.5,t+0.5)\}$ (≥ 3 fixes) — the smoother-independent position.
- **WISER heading** $\theta(h)=\operatorname{atan2}(\mathbf d)$, $\mathbf d=\mathbf m(h+0.5)-\mathbf m(h-0.5)$, defined when $\lVert\mathbf d\rVert/1\,\mathrm s\ge10$ in/s
  and every second overlapping $[h-1,h+1)$ is a step-B clean second — the direction of travel over 2 s (deg).
- **Gyro heading** $\psi(u_k)=\sum_{j\le k}\omega_jq_j\Delta$ (make_imu `turn_dps`, + = CCW from above, QC flag $q$, $\Delta$ = 0.02 s);
  $\bar\psi(h)$ = mean of $\psi$ over $[h-0.5,h+0.5)$ — the head's integrated yaw; only differences enter.
- **Pairs** $\Delta\theta=\operatorname{wrap}(\theta(c+\frac W2)-\theta(c-\frac W2))$, $\Delta\psi=\bar\psi(c+\frac W2)-\bar\psi(c-\frac W2)$, $\operatorname{wrap}(x)=((x+180)\bmod360)-180$;
  IMU QC-ok on $[c-\frac W2-0.5,c+\frac W2+0.5)$.
- **Slope / R² (gate)** $b=\sum\Delta\psi\Delta\theta/\sum\Delta\psi^2$, $R^2=1-\sum(\Delta\theta-b\Delta\psi)^2/\sum(\Delta\theta-\overline{\Delta\theta})^2$ over
  $|\Delta\psi|\le150°$ — degrees of path turn per degree of head turn, and the share of path-turn variance explained.
- **Residual / scanning tail** $r=\operatorname{wrap}(\Delta\theta-b\operatorname{wrap}(\Delta\psi))$; tail = share with |r| > 30°.
- **Turn-sign agreement** $A$ = share of $30°\le|\Delta\psi|\le150°$ pairs with $\operatorname{sgn}\Delta\theta=\sigma\operatorname{sgn}\Delta\psi$, $\sigma$ = sign of the pooled calm slope (chance 0.5).
- **Noise ceiling** $R^2_{\max}=1-\overline{\sigma_{\theta,1}^2+\sigma_{\theta,2}^2}/\operatorname{Var}(\Delta\theta)$, $\sigma_\theta=\sigma_d/\lVert\mathbf d\rVert$,
  $\sigma_d=\operatorname{med}\lVert\mathbf d\rVert_{\text{still}}/\sqrt{2\ln2}$ — the R² a perfect body-heading gyro could reach under the still-noise model.
- **+1 h control** — the same fit with the gyro read at $t+3600$ s; $R^2\ge0.1$ would have declared the analysis invalid.
- **Turn missed by WISER** — a run of 0.1-s grid points with $|\psi(t+3)-\psi(t)|\ge90°$ (QC-ok), window $[t_{first},t_{last}+3]$,
  during which every available step-B $u_1$ (≥ half of the seconds) is below 5.26 in/s; rate per IMU-ok hour.
- **Bootstrap** — 1000 resamples of 10-min blocks per (animal, night), seed 20261004, CI 2.5–97.5 %.

## Caveats

Clean seconds are open-field only (≥ 8 anchors). Slow walking (< 10 in/s) is excluded by construction. The gyro measures the
head and the tag is on the head, so the comparison is head travel direction vs head yaw. The M4 test of the calibration
pilot (ρ 0.17–0.32) used a different estimator without the clean filter and is not superseded.

## Files

New: `wiser/scripts/analyze_imu_turn_vs_heading.py`, `wiser/configs/imu_turn_vs_heading_2026c.json`, the report and 4
figures under `results/2026c/wiser_baseline/`, the pointer `run_manifest_imu_turn_vs_heading_2026c.json`, this entry.
Edited: the plan (Amendments 1–3). Not edited (for the main session): `CLAUDE.md` (code-map row `wiser_baseline`),
`implementation_plan/README.md`, `change_log/README.md`.
