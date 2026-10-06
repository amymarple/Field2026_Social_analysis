# NREM → REM transitions and recent sleep history (cohort 2026c) — first run (2026-10-06)

Plan: [implementation_plan/2026-10-06-sleep-rem-cycle-history.md](../implementation_plan/2026-10-06-sleep-rem-cycle-history.md).
Report (all tables, definitions): [results/2026c/ephys_spikes/reports/ephys_spikes_sleep_cycles_2026c.md](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_cycles_2026c.md).

## What changed

- **New `ephys/sleep_cycles.py`.** REM-anchored cycles, descriptive relations, and a discrete-time competing-risks model of
  NREM → REM / Wake (Δ = 10 s).
  - Validation: leave one date out on the light phase, leave one animal out, and a night-transfer test.
  - Checks: ablations, sensitivity S1–S3, secondary weather.
  - `--selftest` (12 checks, synthetic): cycles, censoring, the Park micro-arousal rule, truncated REM, the per-step
    expansion, the events, no future information, and model recovery. PASS.
- **Bulk:** `D:/Field2026_analysis_out/2026c/sleep_cycles_<ts>/` (cycles, steps, held-out predictions). Pointer:
  `results/2026c/ephys_spikes/reports/run_manifest_sleep_cycles_2026c.json`.
- **For S3:** `imu_nremgate` 1-s states exported on the server (`sleep_quant.py export --variant imu_nremgate`); local
  copy in `D:/3rd_rat_spikes/analysis/sleep_server/sleep_states_1s_nremgate/`.

## Data

- `imu_remclean`, 1-s epochs, REM bouts as scored (no merging, user decision).
- 168 sessions / 1281 h included. Excluded:
  - SF07 `2_20260905_093310` (user decision);
  - 7 noise sessions;
  - 5 not scored;
  - 21 short sessions;
  - 1 contact-failing stub.
- No stitching across sessions.
- 4437 complete cycles (4204 light, 233 dark) and 158 censored intervals.
- Model steps: 139 500 light (3588 → REM, 4980 → Wake) and 23 919 dark (183 → REM, 1514 → Wake).

## Definitions (headline; full set in the module docstring)

- **Cycle quantities.** $\text{REM}_\text{pre}$ = REM bout length (s); $I$ = the next REM's start − this REM's end (s);
  $N$, $W$ = NREM, Wake seconds inside $I$; $\text{REM}_\text{next}$ = the next REM bout's length.
- **Step outcome.** For a 10-s step $j$ of an NREM bout, $y \in \{0\ \text{stay}, 1 \to \text{REM}, 2 \to \text{Wake}\}$.
- **Model.** Multinomial logit over the outcome, with covariates known at the step:
  - **M0:** animal + $(\sin, \cos)(2\pi h/24)$ + day + a spline in $\ln(\text{elapsed}+5)$;
  - **M1:** M0 + $\ln \text{REM}_\text{pre}$ + $\ln(1+N_\text{prior})$ + $\ln(1+W_\text{cum})$, where $N_\text{prior}$ / $W_\text{cum}$
    = NREM / Wake since the last REM, before the current bout;
  - **M2:** M1 + (the $\text{REM}_\text{pre}$ and $N_\text{prior}$ terms) × $(\sin, \cos)$.
- **Held-out comparison.** $\Delta LL$ = the mean held-out $-\ln p(y)$ per step, larger model minus smaller; < 0 = better.
  95 % CI by bootstrap over dates.
- **Relative change** = $\Delta LL$ / M0's held-out log-loss (0.2661 nats / step).

## Results

### Prediction, held out (light phase, leave one date out, 12 dates)

| Comparison | Relative to M0 | Dates better |
|---|---|---|
| M1 vs M0 | −0.99 % | 11/12 |
| — wake since the last REM, alone | −0.88 % | 11/12 |
| — NREM since the last REM, alone | −0.17 % (CI excludes 0) | 10/12 |
| — previous REM length, alone | −0.03 % (CI includes 0) | 8/12 |
| M2 vs M1 | +0.01 % | 6/12 |

- **Robustness:**
  - leave one animal out: M1 better for all 6 (−1.2 to −4.7 millinats / step);
  - single-cycle regime: −0.64 %;
  - pre-post-rule states (S3): −1.02 %.
- **Night transfer** (trained on light, tested on dark-phase naps, 13 nights, without time of day; relative to M0′'s night
  log-loss of 0.292):
  - full M1′: −4.9 %;
  - without the wake term: −1.1 %, 13/13 nights.
  - The first report had −5.4 / −1.2 % because it used the light baseline; fixed in the driver, report regenerated.
- **Weather** (secondary): adds nothing (+0.07 %).

### Direction of the history terms

Full light fit, log-odds of REM vs staying, per SD:

| Term | Coefficient (SE cluster by date) | Per-animal M1 |
|---|---|---|
| Wake since the last REM | −0.48 (0.03) | negative in 6/6 |
| NREM since the last REM | +0.13 (0.03) | positive in 5/6 (SF07 −0.03) |
| Previous REM length | −0.001 (0.02) | 3+ / 3− |

### Descriptive (complete light cycles; pooled log-log slope with animal intercepts, cluster CI)

- **R1, $\text{REM}_\text{pre}$ → $N$:** 0.01 [−0.09, 0.11], 4/6 animals ρ > 0. **Not robust to the cycle definition:**
  - single cycles (S2: 2-Gaussian threshold $N$ = 135 s; 48 % of the light cycles are sequential): +0.07 [0.05, 0.10], 6/6 positive;
  - pre-post-rule states (S3): −0.12 [−0.19, −0.06];
  - Park micro-arousal rule: +0.06 (n.s.).
- **R2, $\text{REM}_\text{pre}$ → $I$:** +0.09 [0.001, 0.17], 5/6.
- **R3, $N$ → $\text{REM}_\text{next}$:** +0.10 [0.08, 0.13], 6/6.
- **Dark phase** (233 cycles): R1 +0.31 [0.004, 0.62], 6/6.

## Reading (technical; claims are audited separately)

**Claim audit** (`/scientific-report-promotion`, status + allowed wording per claim): [ephys_spikes_sleep_cycles_claim_audit_2026c.md](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_cycles_claim_audit_2026c.md).

- **History adds a small, consistent amount of held-out information** about when the next REM starts. Almost all of it is
  the **wake accumulated since the last REM**, which lowers the REM probability and raises the Wake probability. NREM
  accumulated since the last REM adds a little, and raises the REM probability. The **previous REM's length adds
  nothing**.
- **No evidence that the history effect varies with time of day within the light phase** (M2 adds nothing held out). The
  dark phase cannot be judged.
- **No sign of a trade-off** ("one longer → the other shorter") in the descriptive relations:
  - a longer previous REM is not followed by less NREM;
  - in single cycles, it is followed by more;
  - more NREM before a REM goes with a longer REM.
- **Open alternatives:**
  - wake since REM may index an arousal-prone period (state persistence) rather than an accounting of sleep;
  - R3 may reflect consolidated vs fragmented sleep periods;
  - the scorer's 15-s smoothing, 6-s minimum bouts and per-session thresholds;
  - `imu_remclean` forbids wake → REM after > 10 s by design, though the S3 states give the same predictive gain;
  - semi-natural light rather than a 12:12 lab cycle.

## Verification

- `python ephys/sleep_cycles.py --selftest`: 12 checks PASS.
- No future information: covariates are computed from the bout start and earlier, and the selftest alters the session
  after a step without changing that step's covariates.
- The folds hold out whole dates (all animals together); light-phase steps never cross midnight.
- Not judged by the agent: the figures (coverage, R1 per animal, the hazard map, model comparison and calibration).
