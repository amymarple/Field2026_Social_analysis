# Sleep quantification (per day, circadian) + SF07 REM check + SF12 shank-1 finding (2026-10-06)

Follows [2026-10-06-sleep-review-sf12-contact-tag.md](2026-10-06-sleep-review-sf12-contact-tag.md).

## What changed

- **`ephys/sleep_quant.py`.**
  - `export` runs where the scorer outputs are (the server). It writes one compact file per session, holding the 1-s
    states plus the slow-wave, theta and EMG metrics and the thresholds: 198 sessions, 56 MB, in
    `D:/3rd_rat_spikes/analysis/sleep_server/states_1s/`.
  - `quantify` (local) writes the per-animal-day and hour-of-day tables, two figures and a report:
    `results/2026c/ephys_spikes/reports/ephys_spikes_sleep_quant_2026c.md`, `_days`, `_hourly`, `_sessions`,
    `_window_per_animal` CSVs; `figures/ephys_spikes_sleep_quant_{per_day,circadian}_2026c.png`.
  - The export was validated locally on the 4 pilot sessions: identical states.
- **`ephys/sf12_shank1_check.py`.** A one-off raw-data check of SF12's shank-1 integrity.
- **`cohorts/2026c.yaml` `ephys.quality_flags`.** New tag `SF12_shank1_degraded` from 2026-09-07 18:00:03 (below).

## Definitions (full set in the `sleep_quant.py` docstring)

- **Epoch time.** $t(k)$ = session start (logger RTC at Record Start, the folder name) + $k$ s. Hours are EDT.
- **Inclusion.** All scored sessions count except:
  - those the user marked `noise`;
  - those tagged `SF12_contact_failing`;
  - sessions < 0.5 h (per-session thresholds rest on too little data);
  - epochs after `valid_until` or after the paddock end (09-12 10:10).

  The user's `bad` marks stay in; a sensitivity number drops them.
- **Phases.** Light = $[\text{sunrise}, \text{sunset})$ at 42.45 °N, 76.47 °W from the NOAA solar equations
  (09-01: 06:29–19:42; 09-12: 06:41–19:23 EDT). Dark = the rest of the calendar day.
- **Minutes per 24 h:**
  $$M_X(a,d) = \sum_{p \in \{\text{light}, \text{dark}\}} f_{X,p}(a,d)\, L_p(d)$$
  - $f_{X,p}$ = the share of included seconds of animal $a$, day $d$, phase $p$ spent in state $X$;
  - $L_p$ = the phase length in minutes;
  - weighting each phase by its true length keeps uneven coverage of day and night from biasing the total.

  An animal-day counts if both phases are ≥ 50 % recorded.
- **Window and N.** The window is 08-31 to 09-06, the last days with all 6 animals (SF11's implant came off on 09-07 at
  06:10). Each animal contributes one value, its mean over included days. Reported as mean ± SEM, with
  SEM = sd / √N, N = 6.
- **Hourly profile.** $f_X(a,h)$ = seconds of $X$ / included seconds, over all window epochs whose local hour is $h$.

## Results (window, mean ± SEM, N = 6)

| Quantity | Value |
|---|---|
| NREM, h per 24 h | 9.8 ± 0.2 |
| REM, h per 24 h | 1.8 ± 0.1 |
| WAKE, h per 24 h | 12.4 ± 0.3 |
| REM share of sleep | 15.7 ± 0.8 % |
| NREM, light / dark phase | 60.4 ± 1.4 % / 17.1 ± 1.6 % |
| REM, light / dark phase | 13.0 ± 0.7 % / 1.1 ± 0.3 % |

- Dropping the 3 SF07 sessions the user flagged `bad` leaves NREM and REM unchanged (9.8 ± 0.3 and 1.8 ± 0.1 h).
- Included: 1284 h. Excluded:
  - 7 noise sessions (38.5 h);
  - 5 not scored (46.8 h);
  - 21 sessions < 0.5 h (1.6 h);
  - 1 contact-failing stub.

## SF07 REM check (the 3 sessions flagged "Is REM right?")

Within-session contrasts (metrics are normalised per session), compared with SF07's other day sessions ≥ 2 h. The
flagged sessions do not stand out:

| | Flagged sessions | Other SF07 day sessions |
|---|---|---|
| theta, REM − NREM | 0.49–0.56 | 0.46–0.57 |
| theta, REM − WAKE | 0.27–0.29 | 0.24–0.35 |
| EMG, REM − NREM | 0.013–0.025 | 0.02–0.04 |
| REM seconds with head moving | 0.3–1.2 % | 0.4–1.3 % |
| REM share of sleep | 18.4, 25.3, 14.0 % | 13–20 % |

- `6_20260901_125442` has the highest REM share of SF07 (25.3 %), and 20 % of its REM bouts follow WAKE (micro-arousals of
  ≤ 10 s; other sessions: 4–15 %).
- Two of the three are the first day's FM64 (de-glitched) sessions.
- Nothing here says they are wrong; the user's visual check stands.

## SF12 shank-1 finding (`ephys/sf12_shank1_check.py`, raw, 1-min windows every 30 min)

Why: the user marked SF12's **09-07 night** (`2_20260907_180003`) as logger noise, and no recorded problem explained it.

| | 09-07 day `2_20260907_090439` (marked ok) | 09-07 night (marked noise) |
|---|---|---|
| Shank-1 LFP correlation with the shank-2/3 median | 0.77–0.98 | 0.12–0.6 from ~18:30, all 16 shank-1 columns |
| Shank-1 broadband level (MAD) | ~half of shanks 2/3, steady | bursts up to 1475 ADC (shanks 2/3 ~500) |
| Columns 58 and 60 | 300–640 | intermittently open (60–125) from ~23:00 |
| Shanks 2/3 | clean (0.98–0.99) | clean (0.98–0.99) |
| 60-Hz signature | none | none |

- The scorer numbers channels from 1; in 0-based columns its slow-wave channel in this session was **column 58**, so the
  figure was built on a degraded channel. In SF12's normal sessions it uses column 42 or 11 (shanks 2/3).
- The other noise-marked stubs also used shank-1 columns 58 and 60.
- This is the earliest SF12 problem found. It precedes the restored 09-09 note (dead columns 48 58 60 63 in the 09-08 night)
  and the 09-10 connector failure.
- It is tagged `SF12_shank1_degraded` from 2026-09-07 18:00:03 (descriptive; the tag excludes nothing).
- **Possible rescue (user decision):** rescore SF12 with the scorer's channel candidates limited to shanks 2/3. Those
  shanks stay clean through the 09-07 night and, per the lab note, through the 09-10 night as well.

## Update: weather GLM and the REM trend across animals (same day)

**What was added**
- `sleep_quant.py` now loads the cohort-3 weather from field2026-sync (`load_weather`):
  - the on-site console's cloud export through 09-10 21:50;
  - the field PC's listener after that;
  - the NWS airport series only inside the console's 09-02 21:10 – 09-03 15:16 uplink hole.
- It aggregates the weather per day (`daily_weather`) and adds a weather row to the per-day figure.
- It fits the models in `weather_and_trend_stats`.
- New CSVs: `ephys_spikes_sleep_quant_{weather_daily,glm,slopes}_2026c.csv`.
- Definitions are in the report's GLM section and the function docstrings:
  - quasi-binomial logit GLM on the share of the 24 h, one intercept per animal;
  - weather z-scored across days;
  - SEs cluster-robust by day with $t(G-1)$, $G = 11$ days, because weather is a day-level variable.

**REM decreases over days in every animal.** Slope of REM (% of the 24 h) per day:
- **all analysed days** (56 animal-days, 09-01..09-11):
  - per-animal slopes −0.12 to −0.57 pp/day, 6/6 negative;
  - mean −0.24 pp/day ≈ −3.5 min of REM per day;
  - $t(5) = -3.53$, p = 0.017; Wilcoxon p = 0.031, the minimum possible for N = 6;
  - pooled GLM p = 0.0005;
- **window only** (09-01..09-06, all 6 animals, no drop-outs): −0.44 pp/day, 6/6 negative, p = 0.02.

The decline is not confined to the animals whose probes moved: SF10 (no listed advance) has the clearest within-animal
slope (p = 0.003).

**NREM** shows no consistent trend over all days (2/6 negative, p = 0.19). Over the window only, NREM rises in all 6
(+1.1 pp/day, p = 0.011).

**Weather.** NREM is lower on warmer and on rainier days:
- **univariable GLM:** −1.7 pp per SD of temperature (p = 0.010) and −1.4 pp per SD of rain (p = 0.009);
- **joint model:** temperature p = 0.04, rain p = 0.007;
- **day-mean cross-check** (N = 11): temperature r = −0.65 (p = 0.03), rain r = −0.59 (p = 0.055).

REM goes with humidity, rain and temperature univariably, but:
- with day order in the model, humidity drops out (p = 0.83) while the day trend stays (p = 0.006);
- in the joint weather model no term is significant.

**Not separable here.** The rain falls on the first four days (and 09-09), and humidity tracks day order (r = −0.87). So the
weather associations and the over-days trend (habituation after the 08-30 release, recovery, or measurement drift) cannot be
told apart with 11 days. The weather numbers are associations, not effects.

## Update: SF07 slow-wave channel re-picked for two sessions (user decision)

The user's SF07 per-day line dropped to ~0 REM on 09-10. A scan of all 63 day sessions ≥ 2 h for NREM epochs that meet
REM's theta + EMG criteria (median 1.5 %, p90 5.8 %) found two SF07 outliers:

| Session | Automatic SW channel | SW threshold | REM | NREM epochs meeting REM criteria |
|---|---|---|---|---|
| `5_20260910_082351` | 2 | 0.29 | 0.0 % | 21.6 % |
| `2_20260905_093310` | 45 | 0.29 | 0.2 % | 11.4 % |

The user had marked both `ok`.
- **Mechanism.** The scorer decides NREM first ($\text{SW} > \theta_{SW}$), so a low threshold swallows REM.
- **The IMU was fine:** SF07 is still 86 % of the time.

**What changed**
- **`ephys/configs/sleep_channel_overrides_2026c.yaml`.** Per-session channels, 1-based. `score_one` passes them to the
  scorer's `sw_channels` / `theta_channels` (0-based) and records `sw_channel_forced` in `score_sleep.json`.
- **Fixed channel:** SF07 slow wave = channel 23, its most frequent automatic pick in the sessions the user marked ok.
- **`--redo`** (and `REDO=1` in `run_score_sleep.sh`):
  - clears the scorer's reused products but never the EMG file;
  - replaces the review copy only if the user has not edited it.
- **Local test** (SF07 `15_20260902`): forced channel used, IMU EMG kept, unedited copy reseeded, edited copy kept.
- `sleep_quant.py` now saves figures next to a locked file instead of failing.

**Result** (server, commit 636c8c5)
- **`5_20260910_082351`: fixed.** SW threshold 0.54, REM 13.7 % of the session (16 % of sleep). SF07's 09-10 goes from 4.5 to
  99.9 min REM per 24 h.
- **`2_20260905_093310`: not fixed by the channel.** With channel 23 the SW threshold is again 0.29 and REM 0.3 %.
  - The SW histogram has its wake peak near 0.15 and its NREM peak near 0.85.
  - With 25 % wake in 3.7 h, the dip finder settles next to the wake peak whatever the channel.
  - SF07's usual threshold (0.54) would make 18 min (8 %) REM-eligible.
  - It needs a fixed threshold, which the unmodified scorer cannot take: user decision pending.

**Trend after the fix** (all days)
- REM falls in 6/6 animals: −0.18 pp of the 24 h per day, $t(5) = -7.67$, p = 0.0006; pooled day term p = 0.015.
- NREM shows no consistent trend: 2/6 negative, p = 0.24.
- The window (09-01..09-06) results are unchanged.
