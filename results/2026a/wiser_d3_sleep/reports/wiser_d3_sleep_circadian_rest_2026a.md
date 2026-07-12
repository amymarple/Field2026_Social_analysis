# Direction 3 companion — circadian / diel REST profile

*Candidate / measurement-limited. REST = smoothed WISER speed < 12.5 in/s (stationary p99 floor), a low-speed PROXY for sleep, NOT ephys-validated. Jitter ~7 in. Full 24 h, local EDT, pooled over 12 days; a signal gap is 'unknown', not rest (see coverage).*

Days: 2026-06-28, 2026-06-29, 2026-06-30, 2026-07-01, 2026-07-02, 2026-07-03, 2026-07-04, 2026-07-05, 2026-07-06, 2026-07-07, 2026-07-08, 2026-07-09 · rats: 12378, 12380, 12386, 12395, 12407.

## Definitions (every derived quantity)

- **REST (per fix):** `resting = 1` if `speed_inps_smooth < θ_rest`, else `0`; `NaN` smoothed speed → `0` (not resting). `θ_rest = 12.46 in/s` = the 99th percentile of the stationary fixed-position tag's smoothed-speed distribution (`speed_noise_floor`). Plain: below this the rat is indistinguishable from a stationary tag given jitter.
- **Rest fraction (per rat a, local hour h):** `rest_frac(a,h) = (# resting fixes of a in hour h) / (# valid fixes of a in hour h)`, pooled over all days. Unitless in [0,1]. Denominator is OBSERVED fixes only.
- **Group mean ± SEM (per hour h):** `mean_h = mean_a rest_frac(a,h)`; `SEM_h = SD_a(rest_frac(a,h)) / √n_a` (sample SD, `n_a` = # rats with data in h). Mean/SEM are taken ACROSS RATS, so each rat is weighted equally.
- **Coverage (per rat a, hour h):** `cover_frac(a,h) = observed_minutes / (n_days·60)`, capped at 1 — the fraction of that clock-hour actually sampled. **Dropout ≠ rest:** a low coverage hour means missing data (weather / refuge_4 burrow at night), not stillness.
- **Daytime rest window:** local 05:00–21:00 (the Direction-3 convention); its complement (21:00–05:00) is 'night'. Used only to summarize, not to filter.

## Result (candidate)

- **Nocturnal rest–activity pattern (as expected for rats):** mean REST fraction is **0.92 in the 05:00–21:00 day** vs **0.86 at night** — rats are still/resting through the day and active at night. This **corroborates the Direction-3 choice of 05:00–21:00 as the daytime rest window** (it is data-driven, not assumed).
- **Peak rest** at **07:00** (rest_frac 0.92); **least rest (most active)** at **21:00** (rest_frac 0.81).
- **The rhythm is clearer as ACTIVE fraction (1 − rest):** locomotor activity peaks at **21:00 (0.19)** and bottoms at **07:00 (0.08)** — a **~2.5× evening/day activity ratio**. NOTE the contrast is shallow on the rest axis because θ_rest is the jitter *ceiling* (12.5 in/s): any motion slower than that (sitting, grooming, slow foraging) reads as 'rest', so 'rest fraction' overcounts true sleep and compresses the diel swing. It is an ACTIVITY-onset rhythm, not a sleep depth.
- **Between-rat spread:** the SEM band shows how tightly the 5 rats share the same clock (narrow band = synchronized diel rhythm); per-animal traces show the individual truth behind the mean.
- **Coverage:** all clock-hours ≥ 0.5 mean coverage — the profile is not driven by missing data.

## Do they change their circadian across days? (per-date)

Per date, from the group-mean curve: **activity-peak hour** (phase, argmax of the active fraction) and **diel amplitude** (peak − trough active fraction). Dates with < 16 covered hours (e.g. the 06-28 partial day) are excluded from phase/amplitude:

```
     night  n_hours peak_hour active_peak amplitude  partial
2026-06-28        5     21:00       0.262       n/a     True
2026-06-29       24     01:00       0.204     0.128    False
2026-06-30       24     21:00       0.172     0.097    False
2026-07-01       24     21:00       0.175     0.102    False
2026-07-02       24     21:00       0.186     0.112    False
2026-07-03       24     21:00       0.164     0.091    False
2026-07-04       24     21:00       0.205     0.131    False
2026-07-05       24     21:00       0.164     0.089    False
2026-07-06       24     21:00       0.185     0.113    False
2026-07-07       24     21:00       0.206     0.135    False
2026-07-08       24     21:00       0.200     0.128    False
2026-07-09        4     02:00       0.165       n/a     True
```

- **Phase = STABLE (no drift after the first night):** the activity-onset peak is at **21:00 on 9/10 scored dates** (max circular spread 4 h). Exception(s): 06-29→01:00 — 06-29 is the **first full day after the ~19:25 evening release**, so its overnight (01:00) peak is first-night settling, not a rhythm shift. The dusk activity-onset clock is the robust, stable feature.
- **Amplitude = modestly modulated (NOT a phase change):** diel amplitude (peak−trough active fraction) ranges **0.089–0.135**; highest on **07-07**, lowest on **07-05**. The sharpest activity concentration falls on the first full night (06-29, novelty) and 07-04 (**July-4th fireworks** — an external disturbance; FIELD_OBSERVATIONS Day 7) — candidate disturbance/novelty-linked amplitude modulation (hypotheses, not labels), on top of an otherwise stable rhythm.
- **First night (06-28, release ~19:25):** included as a **partial / 'pseudo' peak** — evening-only coverage (5 h from ~19:30), activity peak at **21:00** (release-driven novelty burst, hollow marker in C3/C5). Reported but not scored for amplitude (coverage too short to define a diel trough).
- **Per-animal (C2 rest / C4 activity):** each rat's by-date lines are tightly stacked → the diel pattern is individually consistent day to day, not a group artifact. **Activity-fraction views (C4 per-animal, C5 group) are the easiest to read per night** (auto-scaled; the 21:00 onset spike is obvious).

## Biological-night alignment — when does the rhythm lock? (figure C6)

The calendar-date cut splits one dusk→dawn night across two date labels (an evening onset and its post-midnight tail land on different dates), which is why 06-29 looked like a 01:00 'peak'. Re-cutting so each biological night is ONE unit — anchored at the **data-driven activity trough (07:00 EDT**, the quietest clock-hour) — removes that artifact.

```
     night  n_hours onset_hour peak_hour hours_active  partial
2026-06-28       12      21:00     21:00            5     True
2026-06-29       24      21:00     21:00            2    False
2026-06-30       24      21:00     21:00            4    False
2026-07-01       24      21:00     21:00            3    False
2026-07-02       24      21:00     21:00            3    False
2026-07-03       24      16:00     21:00            7    False
2026-07-04       24      21:00     21:00            3    False
2026-07-05       24      21:00     21:00            6    False
2026-07-06       24      21:00     21:00            4    False
2026-07-07       24      21:00     21:00            6    False
2026-07-08       21      21:00     21:00            5    False
```

- **Phase is locked from the FIRST biological night.** The activity **peak is at 21:00 on ALL 11 biological nights** — peak spread **0 h**, including the release night. The dusk **onset** (half-max) is ~21:00 on every night except 07-03=16:00 (onset-detection caught an earlier afternoon rise there; the peak is still 21:00 — treat onset as the softer measure). The apparent calendar '06-29 → 01:00' peak was purely the split artifact: that post-midnight activity is the RELEASE night's own overnight tail, which now sits inside biological-night 1 (06-28).
- **Only the overnight DEPTH / lateness varies, not the phase.** In C6 the **release night (06-28) sustains the highest activity latest into the overnight (21:00→~04:00)**, while later nights concentrate near the 21:00 onset and fall off faster; the largest full-night amplitude is 07-04 (fireworks). (The `hours_active` above-half-max count is a threshold-sensitive proxy and is noisy night to night — read the C6 curves, not that single number.) **Net: a fixed dusk-onset (~21:00) phase from night 1; novelty/disturbance modulate how deep and how late the night's activity runs, not when it starts.**

## Caveats

- Rest is a low-speed **proxy**, not ephys/CV-validated sleep (a still-but-awake rat reads as rest; a rat in the refuge_4 burrow reads as dropout, not rest).
- 06-28 is a **partial day** (evening release ~19:25), so only its evening hours contribute; the coverage panel reflects this.
- Weather and the burrow act on BOTH the animal and the UWB-dropout paths; the coverage panel is the guard. No spatial claim is made, so the unverified inch frame does not bite.

*Figure + CSVs: `D:\Field2026_analysis_out\circadian_rest_20260709_1051`.*
