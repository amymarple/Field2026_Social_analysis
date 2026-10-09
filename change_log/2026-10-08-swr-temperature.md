# NREM ripples vs ambient temperature, day vs night: time of day, not temperature (2026-10-08)

Plan: [implementation_plan/2026-10-08-swr-temperature.md](../implementation_plan/2026-10-08-swr-temperature.md).
- The original tests were fixed before any result.
- Amendment 1 was written after the first result and a Fable audit.

The user asked: "next, ripples vs temperature — split them into day ripples and night ripples, NREM only".

## What changed

- **New `ephys/swr_temperature.py`** (`run`, `--selftest`: synthetic slopes recovered; an hour-only confound is removed by
  model H; phases at sunrise / sunset).
- **Report:** `results/2026c/ephys_spikes/reports/ephys_spikes_swr_temperature_2026c.md`.
  - CSVs: `_tests`, `_per_animal`, `_verdict`, `_day_night`, `_sensitivity`, `_loao`, `_hour_profile`.
  - Figures: `figures/ephys_spikes_swr_temperature_{scatter,timeline,hour_profile}_2026c.png`.
  - Pointer: `run_manifest_swr_temperature_2026c.json`.
- **Run folder** `D:/Field2026_analysis_out/2026c/swr_temperature_<ts>/`: the NREM event table with time / phase /
  temperature, the 30-min bins, the weather anomaly (cached).
- **`ephys/swr_quality.py`:** first blocks are written as `start`. The string `None` was read back as NaN, and `groupby`
  silently dropped every first block. That bug hid 5/6 of the data in the first temperature run; it was caught before
  any reporting. The storage quality CSV was updated (VERIFY PASS).

## Definitions (headline)

Per animal × channel block × 30-min clock bin $k$, with $N_k$ = NREM minutes and $E_k$ = kept NREM SWR events (tier
validated / good, `excluded == False`):

- **Rate:** $r_k = |E_k|/N_k$ (/NREM min).
- **Frequency:** $f_k = \operatorname{median}_{E_k} f_e$ (Hz).
  - $f_e$ = DetectSWR's Hilbert phase-derivative frequency of the 80–250 Hz ripple signal at the event's peak trough.
  - Single values are unbounded (≈ 10 % < 100 Hz), hence the median.
- **Duration:** $d_k$ = median ms.
- **Relative amplitude:** $A_k$ = median amplitude / the block reference's NREM median.
- **Temperature:**
  - $T_k$ = mean outdoor `temp_C` (on-site console, 5 min);
  - $T^{anom}_k$ = temp_C minus its cohort-wide 24-h harmonic fit (k = 1, 2), i.e. warmer / colder than usual for the
    hour.
- **Phase:** day = the bin centre in [sunrise, sunset); bins containing sunrise / sunset dropped.
- **Model P** (pre-registered):
  - $y_k = \alpha_{a,b} + \beta_T T_k + \beta_N\,\mathrm{night}_k + \beta_{TN} T_k\,\mathrm{night}_k + \gamma\,\mathrm{day}_k$;
  - WLS with weights $N_k$; SEs clustered by date (CR1), $t(G-1)$, $G$ = 12.
- **Model H** (Amendment 1): model P + hour-of-day harmonics $\sum_{k=1,2}[a_k \sin + b_k \cos](2\pi k h/24)$, i.e. the
  temperature slope at a fixed time of day.
- **Verdict:**
  - **Established** = all of:
    - the model H pooled CI excludes 0;
    - the animal-level CI (mean of per-animal slopes, $t(n-1)$) excludes 0;
    - ≥ 4 animals share the sign;
    - validated blocks only give the same sign with a CI excluding 0.
  - **Candidate** = the pooled CI excludes 0 but another criterion fails.
- **Exclusions:**
  - after use_until, and after 09-11 19:40 (females);
  - the first 30 min of each session file (handling);
  - probe-advance settle windows;
  - bins with < 5 min NREM.

## Results

**Data:** 134 sessions, 6 animals, 12 dates (08-31 → 09-11), 1,152 bins, 1,422,586 NREM events in bins. Outdoor
temperature 9–28 °C.

**First run, model P, as pre-registered:**
- Frequency fell with outdoor temperature: day −0.43 Hz/°C (6/6 animals), night −0.30 Hz/°C (5/6).
- At night, frequency also fell with the anomaly: −0.24 Hz/°C.
- These passed the original rule.

**Fable audit, ranked findings:**
1. **Time of day (severe).** Within animal × block, frequency and rate fall steadily across the rest phase. Outdoor
   temperature rises over the same hours (r = 0.57 with hour in day bins), and model P has no hour term. With hour
   harmonics, the day slope shrinks to −0.25 Hz/°C (−0.14 in validated blocks).
2. **The night and anomaly slopes rest on SF08 and SF12** (non-validated blocks). They vanish in validated blocks and
   without SF12. With animals as the unit, only the hour-confounded day slope survives.
3. **Event composition** (amplitude ↔ frequency estimator) explains ≤ 0.3 Hz.
4. **Two wording errors:** the "100–250 Hz by construction" definition, and the event count.

The date-clustered inference itself agreed with a Webb wild-cluster bootstrap.

**After Amendment 1:**
- **Time of day dominates:**
  - frequency runs from +4.5 Hz around 04 h to −3.2 Hz around 19 h around each block's mean;
  - rate runs from +18 to −8.5 /NREM min.
- **No effect of ambient temperature on NREM ripples is Established.**
  - Frequency vs outdoor T and vs the anomaly (day and night) is **Candidate**: pooled model-H slopes −0.24 … −0.26
    Hz/°C, but every one fails animal-level inference (the per-animal slopes disagree).
  - The night ones also fail on validated blocks (they disappear without SF12).
  - Rate slopes are Candidate, failing the animal-level, sign and validated criteria.
  - Duration at night is Candidate (+0.16 … +0.19 ms/°C).
  - Amplitude: no.
- **Night vs day (descriptive):**
  - Night NREM ripples are faster (paired by date: +1.6 to +6.3 Hz, 6/6 animals) and more frequent (6/6).
  - The night is colder, so this is opposite to a direct ambient → brain → faster-ripple effect.
  - A brain temperature set by the activity cycle, or sleep pressure, fits better. Neither is measured here: no
    head / brain temperature exists.

## Not done / next

- A specific temperature test would need:
  - hour-matched comparisons across days of different temperature anomaly;
  - validated blocks only;
  - ideally a head / skin temperature measurement.
- The time-of-day profile could be related to sleep history (time since the active phase, NREM depth / delta) with the
  sleep-schedule tools.

## Update 2026-10-09: day and night ripple RATE vs temperature (the user's question; plan Amendment 2)

**The outcome is now the NREM ripple rate per period.** One value per animal × block × period: the day period is
sunrise → sunset of date D, the night period is sunset D → sunrise D+1.

- $R_p$ = kept NREM events / NREM minutes, with ≥ 30 NREM min.
- $T_p$ = NREM-minute-weighted outdoor temperature.
- Model per phase: WLS with animal × block intercepts + a day trend, SEs clustered by date.
- Each day period covers the same hours on every date, so the time-of-day confound of the bin-level analysis does not
  arise. A hour-adjusted rate is run as a check.
- Source: `swr_temperature.py rate`, from the saved bins (no re-extraction). Report:
  `results/2026c/ephys_spikes/reports/ephys_spikes_swr_temperature_rate_2026c.md`.

**Day ripple rate vs temperature: no relation.**
- −0.90 /NREM min per °C [−2.70, 0.89], 50 animal-days.
- 3 of 5 animals share that sign. Validated blocks give +0.80.
- Day temperatures span only 15.5–24.6 °C.

**Night ripple rate vs temperature: colder nights → more ripples per NREM minute. Verdict Candidate.**
- −1.87 /NREM min per °C [−2.93, −0.82], p 0.003, 41 animal-nights, night temperatures 10.1–20.8 °C.
- Hour-adjusted −1.73 [−2.76, −0.71]; vs the temperature anomaly −1.87 [−3.06, −0.68].
- 4 of 5 animals negative: Pearson r SF08 −0.86, SF12 −0.85, SF10 −0.63, SF09 −0.45; SF07 +0.04.
- Not Established:
  - the animal-level CI [−4.2, 0.5] includes 0 (n = 5);
  - validated blocks give −1.33 [−2.93, 0.26].
- **Amplitude check:** night amplitude also rises slightly on cold nights (−0.5 % per °C, CI just excluding 0). With
  a fixed detection boundary, part of the rate change could be detection.

**The night contrast is mostly between:**
- warm nights: 08-31 → 09-03 and 09-09, 19–21 °C;
- cold nights: 09-06 and 09-07, 10.5–11.6 °C.

The cold nights sit in the middle of the cohort, around the probe advances, the 09-07 six-rat huddle and SF11's
implant loss. A linear day trend cannot separate them.
