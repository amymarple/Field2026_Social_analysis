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

## Update 2026-10-09 (2): the day split at solar noon; the hottest vs the coldest time (the user's questions)

**Day split at solar noon** (`swr_temperature.py rate --split-day`). Morning = sunrise → solar noon (≈ 13:00 EDT);
afternoon = solar noon → sunset. Report: `…swr_temperature_rate_daysplit_2026c.md`.

| Period | Mean rate (/NREM min) | Slope vs temperature (/NREM min per °C) | Verdict |
|---|---|---|---|
| Morning | 68 | −0.64 [−2.14, 0.85] | No relation |
| Afternoon | 61 | −1.48 [−2.70, −0.26] | Candidate |
| Night | 83 | −1.87 [−2.93, −0.82] | Candidate (unchanged) |

- **Afternoon:** 3/5 animals share the sign, SF12 carries it (r −0.97), and validated blocks give −0.12. Amplitude also
  falls on warm afternoons (−0.6 %/°C), so detection could explain part of it.

**Hottest vs coldest time** (`swr_temperature.py extremes`). Per biological date: ± 1 h around that day's temperature
maximum (sunrise → sunset; usually 14:30–17:30) vs ± 1 h around that night's minimum (usually 05:00–06:30, sometimes
around midnight). Kept NREM events / NREM minutes, ≥ 10 NREM min, paired per animal × date. Report:
`…swr_temperature_extremes_2026c.md`.

- **The coldest time has the higher NREM ripple rate:** +15.2 /NREM min [3.7, 26.7] (date clusters).
  - 24 of 27 pairs; 6 / 6 animals (animal-level t(5) p 0.006).
  - 79.0 vs 63.8 /NREM min, about 11.5 °C colder.
- This is also late rest phase vs the end of the active phase, so it is not separable from time of day / sleep
  pressure.

## Update 2026-10-09 (3): rate figures; day and night rate across days (the user's questions)

**`swr_temperature.py figure`** → `figures/ephys_spikes_swr_rate_day_and_hour_2026c.png`. It shows NREM ripple rate per
NREM time:
- per day: each animal's day and night periods;
- within a day: per animal, and the shared block-demeaned profile ± SEM;
- with outdoor temperature.

The shared profile runs from +16 … +20 /NREM min at 23–02 h to −9 at 16–17 h, the mirror of the temperature.

**`swr_temperature.py trend`** → `figures/ephys_spikes_swr_rate_trend_day_night_2026c.png` +
`…swr_rate_trend_{lines,tests}_2026c.csv`. Day and night rate per biological date, mean ± SEM over animals (one value
per animal per period), absolute and normalised to each animal × block × phase mean. The trend is a WLS slope on days
within animal × block, SEs clustered by date.

| Phase | Trend (/NREM min per day) | Normalised (% per day) | Animal-level mean (/NREM min per day) | Relative amplitude (% per day) |
|---|---|---|---|---|
| Day | +0.79 [−0.35, 1.92] (4/5 animals up) | +1.3 % [−0.4, 3.0] | — | +0.1 % |
| Night | +3.3 [1.4, 5.2], p 0.003 (4/5 up) | +3.8 % [1.4, 6.2] | +0.5 [−7.6, 8.6] | −0.04 % |

- **Day:** about flat, not significant.
- **Night:** rises over the cohort.
  - The animal-level mean is +0.5 per day, so the animals are heterogeneous.
  - Amplitude does not drift, so a detection threshold effect is unlikely.
  - Late nights rest on fewer animals: 3 on 09-06 and 09-08, 1–2 on 09-09 and 09-10.
  - The nights also cooled over the cohort (19–20 °C early, 10–17 °C later), so the night rise and the night
    temperature slope are the same contrast seen twice and cannot be separated.

## Update 2026-10-09 (4): NREM depth (the scorer's spectral slope) and the ripple rate (plan Part 2, written before computing)

New `ephys/swr_depth.py` (`run`, `--selftest`). Report: `results/2026c/ephys_spikes/reports/ephys_spikes_swr_depth_2026c.md`;
figure `figures/ephys_spikes_swr_depth_2026c.png`.

**Depth measure.**
- The sleep scorer's raw slow-wave metric: the negative IRASA spectral slope, 4–90 Hz, per second.
- From the fixed-channel scores `imu_fixch` (`SleepScoreRaw.npz`, before the per-session rescaling; storage, read-only).
- Per bin: averaged over NREM seconds in the same 30-min bins as the ripple analysis, then z-scored within animal ×
  block.

**S1, day vs night.** NREM is deeper at **night**, against the user's expectation:
- day − night = −1.31 SD [−1.48, −1.13];
- 0 of 6 animals and 0 of 35 animal-dates have the day deeper.

**S2, time of day.** Depth is highest around 00–04 h (+1.0 … +1.6 SD) and falls monotonically through the rest phase,
from +1.2 at 07 h to −1.5 … −1.7 at 18–19 h. This is the classic decline of slow-wave activity as sleep pressure is
discharged. The ripple rate follows the same course.

**S3, does depth explain the rate?**
- Ripple rate rises with depth: +6.7 /NREM min per SD [4.8, 8.7]; positive in 6/6 animals (CI excluding 0 in 4).
- **Depth explains only part of it**, by the plan's rule (> 1/2 removed AND the CI then includes 0):

  | Contrast | Without depth | With depth | Share removed |
  |---|---|---|---|
  | Time-of-day profile, peak-to-trough | 26.1 /NREM min | 19.5 | 25 % |
  | Night − day | +16.8 [12.2, 21.4] | +10.8 [6.6, 15.0] | 36 % |
  | Night rise across days | +3.25 /day | +3.31 | none |

- Night depth does not change across days (−0.014 SD/day), so the night rise across days is not deeper NREM.

## 2026-10-10 — the hour profile with a post-round mask (asked by the delta-wave session)

- The check: the 30-min bins overlapping a handling window + 1 h / + 3 h were dropped
  (`cv/configs/cohort3_handling_windows.json`, 32 windows), and panel D of `ephys_spikes_swr_rate_day_and_hour_2026c.png`
  was recomputed. The block-demeaned rate is mean ± SEM over animals, for hours seen in ≥ 3 animals.
- Bins kept: 81 % / 56 %.
- The SWR profile is unchanged: Spearman 0.92 against the unmasked one.

  | mask | peak | night 21–04 h | afternoon 13–18 h |
  |---|---|---:|---:|
  | none | 23 h +19.5 | +14.5 | −6.6 |
  | + 3 h | 23 h +19.0 | +14.2 | −7.8 |

- Only the morning hours move: 07 h +4.1 → +1.0; 08 h +5.9 → −8.5, with 4 animals left.
- So the night peak and the afternoon low are not handling effects. A small part of the post-dawn rate follows the
  morning round.
- Script and table: `hour_profile_post_round_mask.csv` in the swr_temperature run folder (the scratch script was kept
  with it).
