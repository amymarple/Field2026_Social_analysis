# Claim audit — the internal sleep schedule: memory, carry-over across wakes, compensation, night vs day (cohort 2026c, 2026-10-08)

`/scientific-report-promotion` on Phases 0–3b of
[implementation_plan/2026-10-07-sleep-internal-schedule.md](../../../../implementation_plan/2026-10-07-sleep-internal-schedule.md)
(rev. 2 + Amendments 1–5). Change log:
[change_log/2026-10-08-sleep-internal-schedule.md](../../../../change_log/2026-10-08-sleep-internal-schedule.md).

Reports:
- [Phase 0](ephys_spikes_sleep_schedule_phase0_2026c.md)
- [Phase 1](ephys_spikes_sleep_schedule_phase1_2026c.md)
- [Phase 2](ephys_spikes_sleep_schedule_phase2_2026c.md)
- [Phase 2b](ephys_spikes_sleep_schedule_phase2b_2026c.md)
- [Phase 3](ephys_spikes_sleep_schedule_phase3_2026c.md)
- [Phase 3b](ephys_spikes_sleep_schedule_phase3b_2026c.md)
- [mic pilot](ephys_spikes_mic_wake_pilot_2026c.md)

It supersedes the v1 / v2 audits ([v2](ephys_spikes_sleep_cycles_v2_claim_audit_2026c.md)) where they differ.

**The user asked for bold wording where the evidence carries it** (2026-10-08). The rule applied here:
- **Established:** the strongest wording the evidence supports, provided the result holds:
  - held out, forward in time (day-half blocks);
  - in ≥ 5/6 rats;
  - and, where per-session thresholds could matter, under the fixed-threshold scores too.
- **Candidate:** reported plainly, with its main alternative named.
- **Mechanism words** (scheduler, gate, homeostat) stay interpretations.

**Common to all claims:**
- **Measurement.** Automatic 1-s scores: FINAL = `imu_remclean` + one substitution. There is no manual epoch scoring (κ).
- **Data.** 6 rats, outdoor paddock, 08-30 → 09-11 19:40.
- **Units of replication.** Rats (6) and day-half blocks (22).
- **Validation.** Forward chaining unless stated.
- **Δ.** Held-out log-loss per 10-s NREM step. It is a reliability measure; effect sizes are given on interpretable
  scales.

| # | claim | status | main_evidence | allowed_wording | forbidden_wording |
|---|---|---|---|---|---|
| 1 | Recent sleep history predicts how each NREM bout ends, with a large effect on an interpretable scale. | **Established** | Δ −1.53 % [−1.88, −1.12] (15/15 folds, 6/6). Of held-out bouts rated least / most likely to end in REM, 4 % / 67 % did (11 % / 52 % without history). | "Sleep history strongly shapes how NREM ends: among NREM bouts the model rated most likely to end in REM, 67 % did, versus 4 % of those rated least likely." | "History determines REM"; any mechanism. |
| 2 | Within continuous records, history is summarised by the current state plus a few quantities accumulated since the last REM; older windows (10 min–12 h) add nothing. | **Established** (scoped) | Current state −1.0 %, since-last-REM −0.5 % (both hold). Bands +0.12 % (n.s.). | "A few running totals since the last REM capture the predictive history; the sleep system does not need the detailed sequence." | "No long memory"; "memory is cleared at REM" ("since the last REM" can span hours). |
| 3 | The chance of REM rises with NREM accumulated since the last REM: lowest at 2–3 min, plateau at 8–20 min, decline after 20–30 min. Counting continuously, including the current bout, predicts better. | **Established** (shape + held-out) | Empirical hazard per 10 s: 0.006 at 2–3 min, 0.028 at 8–20 min. Running count vs bout-start: −0.83 % [−1.20, −0.38], 5/6. | "REM propensity builds with accumulated NREM, peaking after ~10–20 min of NREM since the last REM, as described in mice and humans (Ginsberg 2024, Akhavan 2026)." | A refractory-period length; "within-stretch decline" (population and stretch effects are not separated); the first-minute peak as a permissive state (likely REM fragmentation). |
| 4 | Deeper recent NREM favours REM; shallow NREM favours waking. | **Candidate** | Lagged depth (z-SW, [t−150, t−30) s) adds −0.22 % [−0.33, −0.10], 6/6. Plateau hazard: REM 0.030 deep vs 0.020 shallow, wake 0.027 vs 0.052. | "REM tended to arise from deeper NREM, while shallow NREM more often ended in waking." | Causal depth gating. SW is the scorer's own NREM criterion (lag mitigates, does not remove). |
| 5 | Sleep history carries over across brief wakes. | **Established** for wakes < 2 min; not detected for ≥ 7 min | Pre-wake history adds −0.40 % (13/15, 5/6). By wake: < 40 s −0.47 %, 40–120 s −0.33 % (both CI < 0); 2–7 min n.s.; ≥ 7 min n.s. (11 / 3 REM events). | "Brief awakenings (under 2 min) did not erase the sleep history: what had accumulated before them still predicted the next transition." | "History survives all wakes"; "long wakes reset history" (not tested with power). |
| 6 | A long wake (≥ 7 min) pushes the next REM back in proportion to its length. NREM accumulated before the wake does not shorten the wait. Post-wake NREM depth does not explain it. | **Candidate** (strong) | NREM before the first REM ~ ln wake: +0.26 (p < 0.001, 6/6); pre-wake NREM −0.02 (n.s.); with depth controlled 0.250 (depth n.s.). 2nd REM +0.22 (n.s.), 3rd 0. | "After a long wake, the rats needed more NREM before REM returned, about 20 % more per doubling of the wake. The NREM accumulated before the wake did not count toward it, so REM progress was not resumed, and deeper NREM did not explain it. The effect lasted about one cycle." | "Reset" as a mechanism; generalising beyond cycles that reached REM before another long wake. |
| 7 | Whether REM propensity counts NREM time or clock time. | **Unresolved** | Tied overall (+0.06 %, n.s.). NREM clock better after 40–120 s wakes (+0.26 % [0.03, 0.47]). Long wakes too few. | "The data do not yet tell whether REM propensity counts NREM or elapsed time." | Either clock as the rule. |
| 8 | Across battery rounds, pre-round history predicts post-round transitions. | **Unresolved** | +0.15 % (worse); 85 REM events; the fixed-threshold check is the same. | "No carry-over across handled interruptions was detected, but the test had little power." | "Handling resets the schedule". |
| 9 | Within continuous sleep, a REM shortfall is neither made up nor carried forward over 1–3 h. The FINAL-score "persistence" was a scoring artefact. | **Established** (scoped negative); persistence **Rejected** | Fixed thresholds: slopes +0.003 / +0.001 (1 h / 3 h). FINAL −0.11 / −0.28 vanish. Q2 debt term at 1–3 h ≈ 0 with fixed thresholds; at 6 h −0.62 (n = 102, 1/5, fragile). | "Within continuous recordings, a REM shortfall was not followed by extra REM over the next 1–3 h." | "REM deficits persist" (artefact); anything about 6 h. |
| 10 | After morning battery rounds, a REM shortfall before the round is followed by extra REM after it, mainly through more REM bouts; NREM is made up in the first hour after morning and evening rounds. | **Candidate** | Fixed thresholds, morning: REM +0.39 / +0.72 per min of debt (1 h / 3 h), REM bouts +0.23 / +0.40. FINAL: +0.18 (p 0.065) / +0.49 (n.s.). Evening REM n.s. NREM 1 h: 0.15–0.30 (both rounds). | "After morning disturbances, rats that had less REM than expected beforehand had more afterwards, mostly through more REM bouts. Lost NREM was partly made up within the hour after any round." | "REM compensation" in general (morning only); "a REM budget" (alternative: a sleep-timing shift at dawn; handling stress). |
| 11 | On average, REM after a battery round stays slightly below expectation for at least 6 h. | **Candidate** | Same 88 events, fixed thresholds: −1.40 / −0.93 / −1.18 min at 1 / 3 / 6 h (6/6, 5/6, 6/6 below 0). FINAL −1.17 / −0.36 / −0.84. | "After handling, REM ran about a minute below expectation and was not fully recovered within 6 h." | "Handling suppresses REM for hours" as a large effect (≈ 1 min). |
| 12 | Wake length changes REM minutes over the following hours (delay then catch-up). | **Unresolved** — withdrawn | A first-hour effect appeared in one sample (n 636, −0.31) but not in the same-events sample followed ≥ 3 h (n 694, −0.08 n.s.; fixed thresholds −0.02), and the 1 → 3 h change ≈ 0. | "Over the hours after a wake, REM minutes did not detectably depend on the wake's length." | "Pure delay, then caught up"; "REM delayed by an hour". |
| 13 | Sleep at night and sleep the next day trade off. | **Candidate** (NREM strong, REM weaker) | Next-day deviation on the night deviation, within-rat, fixed thresholds: NREM −0.54 to −0.91 (p < 0.001, 5/5–6/6). REM −0.41 to −1.11 (4/6–5/5; within-rat CIs mostly include 0). Holds in minutes, not only in rates. | "Nights with more sleep than expected were followed by days with less, clearly for NREM and in the same direction for REM: sleep is balanced over the 24 h." | "A fixed daily REM budget"; "minute-for-minute compensation". Alternatives: day-specific timing shifts, shared weather. |
| 14 | At night the rats enter REM far less often, but each REM bout lasts as long as by day. | **Established** | Naps vs day episodes: REM share 6.8 vs 17.4 % (6/6, −9.8 pp [−10.9, −8.6]); REM bouts per NREM hour 4.0 vs 11.4 (6/6); first REM at 20.5 vs 10 min; entry hazard plateau ~0.008 vs ~0.04 per 10 s. REM bout duration 71 vs 74 s (n.s., 3/6). | "**The night limits REM entry, not REM maintenance:** at night the rats entered REM about three times less often per hour of NREM, yet each REM bout lasted as long as by day." | "REM is the same at night" in physiology; a circadian suppression mechanism (naps follow ~1 h of wake vs ~6 min). |
| 15 | REM-entry rules differ slightly at night. | **Candidate** (small) | History × night −0.13 % [−0.28, −0.02], 13/15, 5/6. Supersedes v2's null history × phase (2-harmonic interaction). | "The history rules for REM entry were modestly different at night." | A large or qualitative change of rules. |
| 16 | REM at night has higher theta, lower slow-wave power and a stiller head. | **Candidate** (measurement-limited) | z within session (6/6): theta 9.9 vs 7.1, SW −5.4 vs −4.6, EMG −0.18 vs +0.16. | "Relative to their own session's NREM, night REM showed more theta and a stiller head." | Absolute theta differences (z is relative to session NREM baselines, which differ between night and day sessions). |
| 17 | How sleep was broken up matters beyond the totals. | **Candidate** (borderline) | frag60 beyond totals −0.17 % [−0.32, +0.01], 6/6 better. | "Fragmentation tended to add information beyond the totals, in every rat, but the effect was at the edge of detection." | "Arrangement matters" as established. |
| 18 | A REM's length influences REMs several cycles later. | **Candidate** (scoped negative) | k = 1–5: no stable association (k = 2 +0.09, p 0.02, 4/6; others n.s.); the classic k = 1 relation is not reproduced (−0.05). | "No stable additional association beyond the next cycle." | "Delayed influence excluded". |
| 19 | MIC01 is in house_2; MIC02 in house_1. | **Established** (MIC01) / **Candidate** (MIC02) | Daily ρ with house movement: MIC01 / house_2 0.52–0.74 (12/12 days); MIC02 / house_1 −0.20 to 0.46. | "MIC01 records house_2." | MIC02 as a reliable house_1 sensor. |
| 20 | Outside sounds trigger wakes. | **Unresolved** | Cues before wakes vs 2 min earlier: housemate 41 vs 31 %, own-house sound 53 vs 44 %, outdoor 59 vs 57 %. Not specific; no validation yet. | "Sounds and housemate movement were somewhat more common just before waking." | Any causal or external attribution. |
| 21 | The brain schedules sleep. | **Unresolved** | Design: natural data, no intervention beyond the rounds. | "The data show history-dependent, interruption-sensitive rules and balancing over the day, consistent with an internal regulation of sleep, not a fixed timetable." | Mechanistic "scheduler" wording. |

**Phase 4, ambient temperature** (2026-10-08; [report](ephys_spikes_sleep_schedule_phase4_2026c.md); prediction written
before results):

| # | claim | status | main_evidence | allowed_wording | forbidden_wording |
|---|---|---|---|---|---|
| 22 | Warmer-than-usual ambient temperature raises the REM share of sleep. | **Candidate** (small, as predicted) | Hourly REM share of sleep: logit +0.040 per °C [0.015, 0.065], p 0.002, 5/6 rats (OR 1.04 per °C; anomaly SD 3 °C). Sleep share of recorded time: no effect (+0.005, n.s.). | "In hours warmer than usual for the time of day, a slightly larger share of sleep was REM (about 4 % higher odds per °C), with no change in how much the rats slept." | "Temperature gates REM"; anything about the houses' interior temperature (only outdoor air was measured). |
| 23 | Temperature predicts the moment of REM entry. | **Rejected** for this range (scoped) | Held out: +0.04 % [−0.07, +0.13] (7/15 folds, 3/6 rats); full-fit REM-vs-stay +0.04 per SD. | "The temperature anomaly added nothing to predicting when NREM turns into REM." | "Temperature has no effect on REM" (see #22). |
| 24 | The night–day NREM trade-off (#13) is explained by temperature. | **Rejected** (partly explained) | Fixed thresholds, within-rat: −0.54 → −0.39 [−0.55, −0.23] with the night and day temperature anomalies (p < 0.001). Warmer days had less day NREM. | "The night–day NREM trade-off remained with temperature controlled; warmer days had less daytime NREM." | "The trade-off is a weather artefact". |

**Synthesis, at the strongest wording the statuses allow** (each part keeps its status):
- **Established.** In the field, sleep follows rules that carry history. REM becomes more likely the more NREM has
  built up since the last REM. Brief awakenings do not erase that build-up. The night limits how often REM starts,
  not how long it lasts.
- **Candidate.** A long wake pushes the next REM back in proportion to its length, without resuming the earlier
  progress. Sleep is balanced between night and day.
- **Not shown.** A fixed timetable, minute-for-minute compensation, and outside causes of awakenings.

**Stop conditions / what would promote the Candidates:**
- **#6:** a test that keeps cycles without REM (hazard or survival with the long wake as a covariate).
- **#10, #13:** a check that separates compensation from timing shifts.
  - One option: total sleep across the full 24 h, where coverage allows.
  - Another: shared conditions (weather) as covariates.
- **#16:** absolute LFP features (theta frequency / power on fixed channels).
- **#20:** the user's listening check.
