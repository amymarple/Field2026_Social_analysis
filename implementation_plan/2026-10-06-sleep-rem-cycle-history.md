# NREM → REM transitions and recent sleep history (cohort 2026c) — plan (2026-10-06)

**Question** (the PI's hypothesis, as a test). Does the timing of the next REM depend on recent sleep history, and does
that dependence change with time of day? The "scheduling" idea is treated as a hypothesis. The analysis does not assume
"one longer → the other shorter" and does not read correlations as a mechanism. No ripples.

**User decisions** (2026-10-06):
- states = `imu_remclean`;
- no merging of REM bouts;
- fit on the **light phase**, use the dark-phase naps as a **held-out transfer test**;
- exclude SF07 `2_20260905_093310` (unresolved SW threshold).

**Literature** (read 2026-10-06; definitions borrowed, thresholds not):
- **Vivaldi, Ocampo-Garcés & Villegas 2005, *Sleep* 28:931** (rat, 15-s epochs, 12:12 LD). The longer the REM episode,
  the longer the following interval (Gompertz sigmoid). The relation is strongest 1–4 h after lights-on and weakest at
  lights-off, and persists after excluding intervals with substantial wake. → a prior for M2: the history effect is
  stronger early in the light phase.
- **Park et al. 2021, *PLoS Comput Biol* 17:e1009316** (mouse, 2.5-s epochs).
  - $\text{REM}_\text{pre}$ predicts the NREM in the interval, $|N|$, better than the interval or $|W|$.
  - Refractory period ≈ 2 × $\text{REM}_\text{pre}$.
  - Wake ≤ 20 s (micro-arousals) is counted into $|N|$.
  - Sequential vs single cycles: a 2-component Gaussian mixture on $\ln|N|$, split at the Gaussians' intersection.
  - The link from $|N|$ to the next REM duration is very weak ($R^2 \approx 10^{-3}$).

## Data (reuse, no rescoring)

- **States:** `D:/3rd_rat_spikes/analysis/sleep_server/states_1s/<SFxx>/<session>.states.npz` (`sleep_quant.py export`,
  1-s epochs). Time = session start (logger RTC) + k s, EDT. Light / dark = NOAA sunrise / sunset (`sleep_quant.sun_times`).
- **Inclusion:** as `sleep_quant.load_epochs`, i.e. excluding
  - user `noise`;
  - the `SF12_contact_failing` tag;
  - sessions < 0.5 h;
  - sessions not scored;
  - **+ SF07 `2_20260905_093310`**.

  Epochs after `valid_until` and after the paddock end are dropped.
- **Flags kept for sensitivity** (not excluded in the main analysis):
  - the first 4 h after each probe advance (`ephys.probe_moves` settle_h);
  - `SF12_shank1_degraded`;
  - after the 09-11 19:40 female release;
  - the user's `bad` (SF07 suspect REM).
- **No stitching across sessions** (battery rounds, quarantines, refusals). A gap is never wake.
- **SF11:** the implant came off on 09-07 at 06:10 (not a death); its data simply end.

## Part 1 — cycles (`ephys/sleep_cycles.py`)

Inside one session, REM bouts = maximal runs of state REM (as scored, after the `imu_remclean` rules). Cycle $k$ runs
from the end of REM bout $k$ to the start of REM bout $k+1$:

- $\text{REM}_\text{pre}$ (s): length of REM bout $k$. Missing if the bout touches the session start (truncated).
- $I$ (s): the inter-REM interval. $N$ / $W$ (s): NREM / Wake seconds in it, so $N + W = I$.
- $\text{REM}_\text{next}$ (s): length of REM bout $k+1$. Censored if it touches the session end.
- Animal, date, local start time, light / dark, flags, and the day's weather (secondary).
- **Complete cycle:** both anchors inside one session. The interval after a session's last REM is **right-censored**.

**Main definition:** as scored.

**Sensitivity** (fixed now, before any result):
- (S1) the Park convention: wake runs ≤ 20 s inside the interval are counted into $N$;
- (S2) the sequential / single split from a 2-Gaussian mixture on $\ln N$ (light phase), with the relations repeated on
  single cycles;
- (S3) the scorer's states before the REM post-rules (`imu_nremgate`, exported once on the server).

Known structural limits to state:
- the scorer's 15-s smoothing and 6-s minimum bouts;
- `imu_remclean` forbids REM after > 10 s of wake by construction, so wake → REM is not testable.

## Part 2 — descriptive (complete cycles; light vs dark shown, dark is sparse: ~230 cycles)

Three relations, per animal and pooled:
- **R1:** $\text{REM}_\text{pre}$ vs $N$;
- **R2:** $\text{REM}_\text{pre}$ vs $I$;
- **R3:** $N$ vs $\text{REM}_\text{next}$.

Statistics:
- Spearman $\rho$ per animal, plus the sign count across animals;
- a pooled log-log regression with animal intercepts and SEs cluster-robust by date;
- binned medians for the figures.

The cycles are defined by REM anchors, not a fixed window, so no fixed-total constraint creates a trade-off.

## Part 3 — transition model (discrete time, Δ = 10 s; competing risks)

**Risk set.** Every 10-s step $j$ of an NREM bout that starts after a session's first complete REM bout (history known),
as person-period rows. The outcome at the step:

| Outcome | Meaning |
|---|---|
| 0 | stays NREM |
| 1 | the bout ends into REM |
| 2 | the bout ends into Wake |

A bout cut by the session end is censored.

**Model.** Multinomial logit. The covariates are known at the step (no future information):
- **M0:** animal intercepts + time of day $(\sin, \cos)(2\pi h/24)$ + day index (REM declines over days) + a natural
  spline in $\ln$(elapsed time in the current NREM bout).
- **M1:** M0 + $\ln \text{REM}_\text{pre}$ + $\ln(1 + N_\text{prior})$ + $\ln(1 + W_\text{cum})$, where
  $N_\text{prior}$ = NREM since the last REM before the current bout and $W_\text{cum}$ = wake since the last REM. The
  time since the last REM is **not** added: it equals $N_\text{prior}$ + elapsed + $W_\text{cum}$.
- **M2:** M1 + (the two history terms) × $(\sin, \cos)$.

**Validation, light phase.**
- Leave one date out: all animals of that date are held out together. Light-phase steps never cross midnight.
- Metrics: held-out mean log-loss per step (3-class) and for the REM outcome; ΔLL M1−M0 and M2−M1 per fold.
- 95 % CI by bootstrap over dates. Calibration in deciles of the predicted REM probability.

**Across animals.**
- Per-animal M1 fits: the sign consistency of the history coefficients.
- Leave one animal out: a pooled intercept, the same ΔLL.

**Night transfer (user idea).** Train on all light steps, test on dark-phase naps. For the transfer, M0′ / M1′ drop time
of day: it is fitted on light hours only and would extrapolate.

**Inference.** Full-data fits with SEs cluster-robust by date, for direction and size only. The predictive claim rests
on held-out ΔLL.

**Scope.** 6 animals, ~11 days → no random slopes, no per-animal splines. The dark-phase "time of day × history"
question is declared **not answerable** (too few cycles).

**Secondary, only after the core.** Does the day's weather add held-out information to M1? Weather is a day-level
variable, shared by all animals and confounded with day order (r(humidity, day) = −0.87), so no causal reading.

## Revision 2 (2026-10-07, user review of v1 + the session-boundary quantification; approved "上吧")

**Why.**
- v1 predicted only daytime transitions.
- It reset history at every session boundary. That dropped the NREM before a session's first REM: 57.9 h = 11.6 % of
  NREM, 1296 bout endings, 142 REM entries. The loss is concentrated in the evening sessions, after a long wake (median
  3.6 h to the first REM): exactly "sleep after long wake".
- Of the 162 boundaries between consecutive sessions, 41 are ≤ 1 min (median 12 s); the rest are real gaps ≥ 30 min,
  mostly battery rounds with handling.

**Design changes**
- **States.** `pass2_remclean` (fixed per-animal channels / rescaling / thresholds,
  `2026-10-07-sleep-fixed-thresholds.md`), so that history across sessions uses one state definition.
- **Main analysis over the full 24 h.** Light / dark is a stratum for display. The v1 light-only fit is kept as a
  sensitivity check, and the night-transfer test is kept.
- **Continuous records.** Consecutive sessions separated by ≤ 60 s are joined: the gap epochs are marked unknown and are
  not counted as any state. A real gap (> 60 s) ends the record. Nothing is ever assumed about a gap's state.
- **History** at each step:
  - (a) since the last REM, when that REM lies in the same continuous record: $\text{REM}_\text{pre}$, $N_\text{prior}$,
    $W_\text{cum}$, as in v1;
  - (b) rolling windows that need no REM anchor: Wake and NREM seconds in the last 10 min, 60 min and 180 min, each with
    its completeness $c_w$ = the recorded share of the window;
  - (c) indicators: "no REM yet in this record" and "window incomplete".
  - Steps without a REM anchor enter the model through (b) and (c), so the post-gap NREM is no longer dropped.
- **Time.** Circadian phase = 2 harmonics of the clock hour ($\sin, \cos$ of $2\pi h/24$ and $4\pi h/24$), plus
  experiment time = hours since release (a natural spline). This replaces the integer day index.
- **Models.**
  - **M0:** animal + phase + experiment time + the elapsed-bout spline.
  - **M1:** M0 + history (a) + (b) + (c).
  - **M2:** M1 + history × phase (first harmonic), including **Wake × phase**.
- **Validation.**
  - **Main:** leave out one block, where blocks are the continuous records grouped by the battery-round gap that ends them
    (all animals sharing that day-half go together), so no cycle and no history crosses a fold boundary. In practice, one
    block per day-half.
  - **Secondary:** forward chaining (train on earlier blocks, test on the next). REM declines over days, so this tests
    extrapolation and is reported as such.
- **Support masks** on every time-of-day × history figure. Night interactions will be weakly supported (183 → REM in v1).

## Outputs (cohort-parameterised)

- Bulk (cycle table, person-period table, fold predictions): `$OUT_ROOT/2026c/sleep_cycles_<ts>/` + run manifest.
- In-repo:
  - `results/2026c/ephys_spikes/reports/ephys_spikes_sleep_cycles_2026c.md` and small CSVs;
  - figures:
    - (1) coverage, animal × date;
    - (2) $\text{REM}_\text{pre}$ vs $N$, per animal, light / dark;
    - (3) $P(\to\text{REM})$ map over time of day × $N_\text{prior}$ at stated fixed covariates, masked where < 50 steps
      support a cell;
    - (4) M0 / M1 / M2 held-out comparison + calibration;
    - (5) night transfer.
- A self-test on synthetic sequences (cycle extraction, censoring, person-period expansion, no leakage).
- Then the change log, the index READMEs and CLAUDE.md, and `/scientific-report-promotion` on the conclusions.
