# NREM ripples vs ambient temperature, day vs night (cohort 2026c) — plan, written before any result (2026-10-08)

## Question and request

The user asked: "next, ripples vs temperature — split the ripples into day ripples and night ripples, NREM only".

Do NREM sharp-wave ripples change with ambient temperature, and does that differ between the light phase (day, the rats'
rest phase) and the dark phase (night)?

- **What would count as a result:**
  - a temperature slope of ripple frequency, rate, duration or amplitude;
  - its confidence interval excludes 0, with clustering by date;
  - at least 4 of the 6 animals (or every animal if fewer) share its sign.
- **Why frequency is the primary outcome:**
  - Ripple frequency is the property known to follow brain temperature.
  - Whether outdoor temperature reaches the brain of a huddling rat in an insulated house is unknown, so no direction is
    predicted.
  - Rate, duration and amplitude are secondary.

## Data

- **Events:** `swr_auto.py` production, storage `3rd_rat/analysis/swr/` (VERIFY PASS 2026-10-08), with the quality guide
  `results/2026c/ephys_spikes/reports/ephys_spikes_swr_quality_2026c.{md,csv}`.
  - Primary sessions: tier `validated` + `good`. Sensitivity: `+ check`. Never `low_contrast` / `exclude`.
  - An event is used when `excluded == False` and `state == "NREM"` at its peak second.
- **Sleep states:** the final 1-s states, `D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final/` (the same ones
  the detection used); NREM = state 3.
- **Clock:** $t = \text{start\_local} + \text{peak\_s}$ (session start from the sleep review table, as `sleep_quant`).
  The seconds-level logger / PC offset is irrelevant at 5-min weather resolution.
- **Weather:** `sleep_quant.load_weather` gives outdoor `temp_C` every 5 min from the on-site console, 08-31 → 09-12;
  NWS Ithaca airport inside the 09-02 21:10 → 09-03 15:16 uplink hole.
  - The anomaly `temp_anom` is exactly `sleep_schedule_temp.weather_anomaly` (temp_C minus its fit on
    (sin, cos)(2πkh/24), k = 1, 2, over the cohort).
  - Joined by the nearest sample within 15 min.
- **Phase:** day = [sunrise, sunset) of the calendar date at the paddock (`sleep_quant.sun_times`); night = the rest.

## Exclusions (fixed now)

- **Time limits:**
  - after the session's `use_until` (valid_until / paddock end 09-12 10:10 / SF12 contact failure);
  - after 09-11 19:40 (the five females; population 5 → 10) in the primary analysis. The sensitivity analysis runs to
    the paddock end.
- **Handling:** the first 30 min of every session (sessions start at battery rounds).
- **Probe advances:** events inside the settle window of a probe advance (`cohorts/2026c.yaml ephys.probe_moves`:
  `time` → `time + settle_h`).
- **Sparse bins:** bins with < 5 min of NREM.

## Units, definitions

Per animal $a$, block $b$ (the channel block of `swr_channels_2026c.yaml`) and 30-min clock bin $k$ (bins aligned to
:00 / :30), with $N_k$ = NREM minutes in the bin (1-s states, after the exclusions) and $E_k$ = the bin's NREM events:

- **NREM ripple rate.** $r_k = |E_k| / N_k$ (events per NREM minute).
  - Text: how often ripples occur during NREM. Validated sessions run 36–79/min.
- **Ripple frequency.** $f_k = \operatorname{median}_{e \in E_k} f_e$ (Hz).
  - $f_e$ is DetectSWR's trough-to-trough frequency at the event's peak trough.
  - Text: the oscillation's frequency, 100–250 Hz by construction. Single events are noisy, so the per-bin median is
    used.
- **Duration.** $d_k = \operatorname{median}_{e \in E_k} \text{duration\_ms}_e$ (ms).
- **Relative amplitude.** $A_k = \operatorname{median}_{e \in E_k} \text{amp}_e / \operatorname{median}_{e \in \text{NREM}(\text{ref}_b)} \text{amp}_e$.
  - Text: amplitude relative to the block's reference session. The raw µV depend on channel and probe, so only
    within-block changes are interpretable.
- **Bin temperature.** $T_k$ = mean `temp_C` of the weather samples in the bin (°C); $T^{anom}_k$ = mean `temp_anom`.
- **Phase of a bin.** `night` = the bin centre is outside [sunrise, sunset). The bins straddling sunrise / sunset are
  dropped.

## Tests (fixed now)

For each outcome $y \in \{f, r, d, A\}$, bins weighted by $N_k$:

$$ y_k = \alpha_{a,b} + \beta_T T_k + \beta_N \,\text{night}_k + \beta_{TN}\, T_k\,\text{night}_k + \gamma\, \text{day}_k + \varepsilon_k $$

- **Terms:**
  - $\alpha_{a,b}$ = one intercept per animal × block;
  - $\text{day}_k$ = days since 08-31, a linear trend absorbing slow drift (probe, contact, habituation, the
    September cooling);
  - SEs clustered by calendar date, with a small-sample correction and $t(G-1)$ inference ($G$ dates). The weather is
    shared by all animals on a date.
- **What is reported:**
  - the day slope $\beta_T$ and the night slope $\beta_T + \beta_{TN}$, per °C, with 95 % CIs;
  - the night − day difference at the mean temperature;
  - the same model per animal (sign agreement).
- **T1 (primary):** $f$ ~ temp_C, day and night slopes.
- **T2:** $f$ ~ temp_anom: temperature beyond the usual daily cycle, so not just "night is colder".
- **T3:** $r$, $d$, $A$ ~ temp_C and temp_anom (secondary).
- **D (descriptive):** day vs night per animal — mean $f$, $r$, $d$, $A$ over bins, and the per-day paired difference
  (night of date D − day of date D).
- **Sensitivities:**
  - `check` sessions included;
  - no day trend;
  - to the paddock end (with the females);
  - validated tier only;
  - 1-h bins;
  - the event-level mixed model for $f$ (events nested in bins) as a cross-check.

**Interpretation rules:** day and night differ in temperature by construction, so a phase difference alone is not a
temperature effect. Only T2 and the within-phase slopes speak to temperature.

## Outputs

- `ephys/swr_temperature.py` (`--selftest`: a synthetic slope is recovered).
- Off-repo run folder `$OUT_ROOT/2026c/swr_temperature_<ts>/`:
  - the NREM event table with time / phase / temperature (cached for reuse);
  - the bin table.
- `results/2026c/ephys_spikes/reports/ephys_spikes_swr_temperature_2026c.md` + CSVs + figures, pointer
  `run_manifest_swr_temperature_2026c.json`.
- Change log `change_log/2026-10-08-swr-temperature.md`; index READMEs.

## Amendment 1 (2026-10-08, written AFTER the first result and a Fable audit; the original tests above are kept and reported)

**What the audit found:**
- The model has no time-of-day term. Within animal × block, ripple frequency and rate fall steadily across the rats' rest
  phase: f ≈ +4.5 Hz at 06 h → −3.8 Hz at 19 h, and still falling after the afternoon temperature peak.
- Outdoor temperature rises over the same hours (r = 0.57 with hour in day bins), so the "temperature" slopes are largely
  time of day.
- The night and anomaly slopes rest on SF08 / SF12, the two non-validated blocks. They vanish in validated blocks and
  without SF12.
- With animals as the unit, only the hour-confounded day slope survives.

**Added (the original model P stays as reported):**
- **Model H** = model P + $\sum_{k=1,2} [a_k \sin(2\pi k h/24) + b_k \cos(2\pi k h/24)]$.
  - $h$ = clock hour of the bin centre.
  - Text: the temperature slope at a fixed time of day. With $T^{anom}$ it compares hours of warmer vs colder days.
  - The night − day difference is not read from model H: phase is nearly a function of hour there.
- **Animal-level inference:** the same model fitted within each animal; the mean of the per-animal slopes with a $t(n-1)$
  95 % CI.
- **Leave-one-animal-out:** the pooled model refitted without each animal in turn.
- **Hour profile (descriptive):** bin outcomes minus their animal × block mean (NREM-minute weighted), averaged per clock
  hour.
- **Verdict (amended rule), per outcome × temperature × phase:**
  - **Established** = all of:
    - the model H CI excludes 0;
    - the animal-level CI excludes 0;
    - ≥ 4 animals share the sign;
    - model H on validated blocks only has the same sign with a CI excluding 0.
  - **Candidate** = the model H CI excludes 0 but another criterion fails.
  - **No** = otherwise.
- **Corrections:**
  - $f_e$ is the Hilbert phase-derivative frequency at the peak trough of the 80–250 Hz signal. Single values are
    unbounded (≈ 10 % read below 100 Hz), so the bin median is used.
  - The event count reported is the one that enters the bins.

## Amendment 2 (2026-10-09, the user's correction: "day / night ripple RATE vs temperature"; bin-level rate slopes already seen)

The user's outcome is the NREM ripple rate, by day and by night. The cleanest form is one value per period:

- **Periods.** For biological day $D$, the day period is $[\text{sunrise}_D, \text{sunset}_D)$ and the night period is
  $[\text{sunset}_D, \text{sunrise}_{D+1})$.
- **Period rate.** Per animal × block × period $p$ (the 30-min bins of Amendment 1's table, no re-extraction):
  $$R_p = \frac{\sum_{k\in p} n_k}{\sum_{k\in p} N_k} \quad (\text{events per NREM minute})$$
  - The period needs ≥ 30 NREM minutes.
  - Text: the NREM ripple rate of that day or night.
- **Period temperature.** $T_p = \sum_{k\in p} N_k T_k / \sum_{k\in p} N_k$: the outdoor temperature while the animal was in
  NREM, in °C.
- **Hour-adjusted rate** (sensitivity). The same ratio after subtracting the cohort hour profile (Amendment 1) from each
  bin's rate, so a period with more NREM at "high-rate hours" is not favoured.
- **Tests, per phase separately** (day periods; night periods):
  - WLS $R_p = \alpha_{a,b} + \beta T_p + \gamma\,\mathrm{day}_p$, weights = NREM minutes, SEs clustered by date, $t(G-1)$.
  - Animal-level: per-animal slope across dates, mean with a $t(n-1)$ CI.
  - Per-animal Pearson / Spearman correlations.
  - Validated blocks only.
  - The same for the relative amplitude, as a check that detection drift does not create the rate slope.
- **Verdict:** the Amendment 1 rule (pooled CI, animal-level CI, ≥ 4 animals same sign, validated blocks).
