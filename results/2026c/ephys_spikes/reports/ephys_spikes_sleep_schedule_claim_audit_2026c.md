# Claim audit — the internal sleep schedule: memory, carry-over across wakes, compensation, night vs day (cohort 2026c, 2026-10-08)

`/scientific-report-promotion` on Phases 0–6 (updated 2026-10-08 from the logic audit: #6a/#6b, #10, #13, #14b, #24, #28b, #29a, #30, #31; LFP-feature claims moved to the next stage) of
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
| 4 | Deeper recent NREM favours REM; shallow NREM favours waking. | **Candidate** → **next stage (LFP)**, not in the chain (scope rule 2026-10-08) | Lagged depth (z-SW, [t−150, t−30) s) adds −0.22 % [−0.33, −0.10], 6/6. Plateau hazard: REM 0.030 deep vs 0.020 shallow, wake 0.027 vs 0.052. | "REM tended to arise from deeper NREM, while shallow NREM more often ended in waking." | Causal depth gating. SW is the scorer's own NREM criterion (lag mitigates, does not remove). |
| 5 | Sleep history carries over across brief wakes. | **Established** for wakes < 2 min; not detected for ≥ 7 min | Pre-wake history adds −0.40 % (13/15, 5/6). By wake: < 40 s −0.47 %, 40–120 s −0.33 % (both CI < 0); 2–7 min n.s.; ≥ 7 min n.s. (11 / 3 REM events). | "Brief awakenings (under 2 min) did not erase the sleep history: what had accumulated before them still predicted the next transition." (Wording, 2026-10-08: "the information survives", not "the count is unchanged"; the 2–7-min range is untested.) | "History survives all wakes"; "long wakes reset history" (not tested with power). |
| 6a | A wake ≥ 7 min is not resumed: the NREM accumulated before it does not shorten the wait for the next REM, by day and by night. | **Candidate** (strong) → Established after step A1 of the [sleep-behaviour plan](../../../../implementation_plan/2026-10-08-sleep-behaviour-explore.md) | Pre-wake NREM coefficient ≈ 0 in every wake bin (7–30 min −0.017 ± 0.019; 30–120 min −0.010 ± 0.031; ≥ 2 h −0.006 ± 0.010) where resumption predicts ≈ −0.3. A censored Cox model that keeps the 211 of 524 post-wake sleeps that never reached REM: N_pre −0.019 ± 0.030 (Fable's check, 2026-10-08, to be reproduced). Original OLS: pre-wake NREM −0.02 (n.s.), 6/6. | "After a wake of 7 min or more, the NREM accumulated before the wake no longer counted toward the next REM." | "Reset" as a mechanism (a fast discount with τ of minutes fits as well; step B's τ_w); claims for 2–7-min wakes (untested). |
| 6b | At night, longer wakes push the next REM further back, graded over hours. | **Candidate** (night only) | NREM before the first REM ~ ln wake: dark +0.26 ± 0.07 (n 132, 7 min–4 h); light −0.10 ± 0.10 (n 181, 7–30 min). Categorical ramp 0 / +0.2 / +0.5 / +0.75 / +0.93 log units for 15–30 … ≥ 240 min vs 7–15 min. Censored Cox (both phases) ln d −0.286 (HR 0.75 per e-fold, 6/6). Wakes > 30 min are 85–100 % nocturnal (Fable's check, to be reproduced in step A2). The original pooled estimate was +0.26 (p < 0.001, 6/6). | "At night, the longer the wake, the more NREM the rats needed before REM returned." | Any day-time dose effect; separating "long wake" from "night" above 30 min (3 day episodes); depth as the mediator (#4 is LFP, next stage). |
| 7 | Whether REM propensity counts NREM time or clock time. | **Unresolved** | Tied overall (+0.06 %, n.s.). NREM clock better after 40–120 s wakes (+0.26 % [0.03, 0.47]). Long wakes too few. Added 2026-10-08: at REM entry a wake does not count as NREM time — a longer wake gives a later REM, not a sooner one (#6a/#6b); the tie concerns continuous sleep. | "The data do not yet tell whether REM propensity counts NREM or elapsed time." | Either clock as the rule. |
| 8 | Across battery rounds, pre-round history predicts post-round transitions. | **Unresolved** | +0.15 % (worse); 85 REM events; the fixed-threshold check is the same. | "No carry-over across handled interruptions was detected, but the test had little power." | "Handling resets the schedule". |
| 9 | Within continuous sleep, a REM shortfall is neither made up nor carried forward over 1–3 h. The FINAL-score "persistence" was a scoring artefact. | **Established** (scoped negative); persistence **Rejected** | Fixed thresholds: slopes +0.003 / +0.001 (1 h / 3 h). FINAL −0.11 / −0.28 vanish. Q2 debt term at 1–3 h ≈ 0 with fixed thresholds; at 6 h −0.62 (n = 102, 1/5, fragile). | "Within continuous recordings, a REM shortfall was not followed by extra REM over the next 1–3 h." Scope (2026-10-08): "within continuous, mostly daytime sleep" — see #10 for repayment across a morning round. | "REM deficits persist" (artefact); anything about 6 h. |
| 10 | A REM shortfall before a morning battery round is followed by extra REM in the next 1–3 h, specifically REM; NREM lost at a morning round is partly made up within the hour. | **Candidate** (strong; fixed thresholds only) | Fixed thresholds, morning: REM +0.39 / +0.72 per min of debt (1 h / 3 h); day-demeaned +0.31 / +0.85 (p < 0.001); with NREM debt partialled +0.37 / +0.71 (NREM debt +0.01 / +0.03 n.s.; r = 0.76 between the debts). NREM made up after morning rounds +0.17 / +0.23 per min (day-demeaned, p ≤ 0.009). FINAL: +0.06 (n.s.) after day-demeaning. Evening: REM n.s.; NREM +0.42 → +0.08 after day-demeaning (n.s.). (2026-10-08 checks by Fable; reproduced in step A4.) | "After morning rounds, rats that had less REM than expected beforehand had more REM afterwards — specifically REM, not explained by anything all rats shared that day." | "Mainly through more REM bouts" (bout count n.s. after day-demeaning); "after any round" (evening n.s.); "a REM budget" (whether a separate deficit is needed is step D of the plan); handling-stress and dawn-timing alternatives remain. |
| 11 | On average, REM after a battery round stays slightly below expectation for at least 6 h. | **Candidate** | Same 88 events, fixed thresholds: −1.40 / −0.93 / −1.18 min at 1 / 3 / 6 h (6/6, 5/6, 6/6 below 0). FINAL −1.17 / −0.36 / −0.84. | "After handling, REM ran about a minute below expectation and was not fully recovered within 6 h." | "Handling suppresses REM for hours" as a large effect (≈ 1 min). |
| 12 | Wake length changes REM minutes over the following hours (delay then catch-up). | **Unresolved** — withdrawn | A first-hour effect appeared in one sample (n 636, −0.31) but not in the same-events sample followed ≥ 3 h (n 694, −0.08 n.s.; fixed thresholds −0.02), and the 1 → 3 h change ≈ 0. | "Over the hours after a wake, REM minutes did not detectably depend on the wake's length." | "Pure delay, then caught up"; "REM delayed by an hour". |
| 13 | Sleep at night and sleep the next day trade off. | **Withdrawn as a balance** (2026-10-08) → see #30 | Next-day deviation on the night deviation, within-rat, fixed thresholds: NREM −0.54 to −0.91 (p < 0.001, 5/5–6/6). REM −0.41 to −1.11 (4/6–5/5; within-rat CIs mostly include 0). Holds in minutes, not only in rates. **Re-read 2026-10-08:** with a linear day term the within-rat NREM slope is −0.06 [−0.29, +0.16]; with day fixed effects −0.12 [−0.32, +0.09] (pass2med). The pattern is a cohort-wide drift (#30). | "Nights with more sleep than expected were followed by days with less, clearly for NREM and in the same direction for REM: sleep is balanced over the 24 h." | "A fixed daily REM budget"; "minute-for-minute compensation". Alternatives: day-specific timing shifts, shared weather. |
| 14 | At night the rats enter REM far less often, but each REM bout lasts as long as by day. | **Established** | Naps vs day episodes: REM share 6.8 vs 17.4 % (6/6, −9.8 pp [−10.9, −8.6]); REM bouts per NREM hour 4.0 vs 11.4 (6/6); first REM at 20.5 vs 10 min; entry hazard plateau ~0.008 vs ~0.04 per 10 s. REM bout duration 71 vs 74 s (n.s., 3/6). At matched prior wake see #14b. | "**The night limits REM entry, not REM maintenance:** at night the rats entered REM about three times less often per hour of NREM, yet each REM bout lasted as long as by day." | "REM is the same at night" in physiology; a circadian suppression mechanism (naps follow ~1 h of wake vs ~6 min). |
| 14b | Independently of the preceding wake, the night lowers the REM-entry rate to about half and delays the first REM. | **Candidate** (FINAL only; rerun on pass2med + per-animal signs = step A3) | After the same 2–7-min wakes: 5.0 vs 11.7 REM bouts per NREM h (n 55 dark / 294 light episodes); first REM 899 vs 530 s. Night effect on REM/h −6.85 → −5.34 with ln(prior wake) in the model; Cox latency HR for dark 0.27 → 0.37 with prior wake (Fable's check, 2026-10-08). Within the night, longer prior wakes lower it further (2–7 min 5.0; 30–120 min 3.2; ≥ 2 h 2.3 per NREM h). | "Even after equally short wakes, the rats entered REM only about half as often at night." | "Light suppresses REM" (light step vs circadian curve vs activity = step C2); claims for post-handling hours (not excluded yet). |
| 15 | REM-entry rules differ slightly at night. | **Candidate** (small) | History × night −0.13 % [−0.28, −0.02], 13/15, 5/6. Supersedes v2's null history × phase (2-harmonic interaction). | "The history rules for REM entry were modestly different at night." | A large or qualitative change of rules. |
| 16 | REM at night has higher theta, lower slow-wave power and a stiller head. | **Candidate** (measurement-limited) → **next stage (LFP)** | z within session (6/6): theta 9.9 vs 7.1, SW −5.4 vs −4.6, EMG −0.18 vs +0.16. | "Relative to their own session's NREM, night REM showed more theta and a stiller head." | Absolute theta differences (z is relative to session NREM baselines, which differ between night and day sessions). |
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
| 24 | The night–day NREM trade-off (#13) is explained by temperature. | **Superseded** (2026-10-08) by #30 | Fixed thresholds, within-rat: −0.54 → −0.39 [−0.55, −0.23] with the night and day temperature anomalies (p < 0.001). Warmer days had less day NREM. | "The night–day NREM trade-off remained with temperature controlled; warmer days had less daytime NREM." | "The trade-off is a weather artefact". |

**Phase 5, REM synchrony between animals** (2026-10-08; [report](ephys_spikes_sleep_schedule_phase5_2026c.md); test
written before results):

| # | claim | status | main_evidence | allowed_wording | forbidden_wording |
|---|---|---|---|---|---|
| 25 | A housemate's REM onset (or ongoing REM) raises an animal's own REM-entry hazard. | **Rejected** (scoped) | Held out, with the animal's own clock, time of day, and housemates present and asleep in the base: +0.08 % (worse), 2/15 folds, 0/6 animals; coefficients ≈ 0 (−0.002, +0.005). | "REM entry was not coupled to housemates' REM: once each rat's own sleep history and the time of day were known, a housemate entering REM did not make it more likely to enter REM." | "Rats never synchronise sleep" (shared timing exists, #26); claims beyond the 60-s window, WISER house membership (14-in buffer, not body contact) and ~1-s clock offsets. |
| 26 | REM co-occurs across animals more than chance through shared timing. | **Established** (descriptive) | P(mate in REM given this rat in REM vs in NREM): median ≈ 1.2× across pairs. The raw REM-entry ratio after a REM onset is 1.10 for housemates but 1.25 for animals elsewhere, so it is not specific to housemates. | "Rats tended to be in REM at the same times, as expected from a shared daily rhythm and conditions, not because one animal's REM triggered another's." | "Social REM synchrony". |

**Phase 5b, local fast coupling of movements during sleep** (2026-10-08; the user's video observation;
[report](ephys_spikes_sleep_schedule_phase5b_2026c.md); test written before results):

| # | claim | status | main_evidence | allowed_wording | forbidden_wording |
|---|---|---|---|---|---|
| 27 | Head-movement onsets of sleeping rats in the same house coincide within ~1–3 s, far above chance; animals in different places barely do. | **Candidate** (strong) | Same house: B onsets at lag 0 / ±1 / ±2 s = 13.8 / ~5 / ~2× the local baseline (REM twitches 15×), 30/30 ordered pairs. Elsewhere: 1.24× at lag 0. Cascade: a housemate moves within 5 s after 43 % (NREM) / 33 % (REM) of events vs ~11 % at 30–35 s. | "Movements of sleeping housemates were tightly coupled in time: when one rat moved, a housemate started moving within a few seconds about three times more often than chance; this coupling was local to the house." | "Twitches propagate from rat to rat" (order not resolved at 1 s; pooled ordered pairs are symmetric by construction); "rats wake each other" (state consequences not tested); active vs passive (mechanical jostling of the neighbour's head) not separated. |

**Phase 5c, the coupling at 20 ms with the IMU-as-EMG; twitch or awakening** (2026-10-08;
[report](ephys_spikes_sleep_schedule_phase5c_2026c.md); before results):

| # | claim | status | main_evidence | allowed_wording | forbidden_wording |
|---|---|---|---|---|---|
| 28a | The coupling between sleeping housemates is near-simultaneous (within ~0.1 s), with a smaller delayed component. | **Candidate** (strong) | 15 / 15 pairs: peak lag 0.00–0.07 s, peak 9–17× baseline. Excess within ±0.1 s 6–10×; at 0.1–1 s 1.6–2.1×. | "Housemates' head movements during sleep coincided within about a tenth of a second, as expected if one rat's movement jostles its neighbours or both respond to the same trigger; a smaller excess extended to ~1 s." | "Twitches propagate" (no delay structure of a reaction); a leader (SF07 moves first in 58 % of coupled pairs, but its 30–70-ms lead is within plausible clock offsets). |
| 28b | Movements during sleep are mostly not awakenings. | **Established** (descriptive; scorer-gate caveat 2026-10-08) | Ten seconds after a movement: NREM movements still asleep in ~92 %; REM movements still REM in 82–85 % (twitch-like). Movements that follow a housemate's woke the mover no more often (6.6 % vs 7.9 % awake at 10 s). | "Most sleep movements, including those coupled to a housemate's, were brief: the rat stayed asleep, and in REM they behaved like twitches." Caveat (2026-10-08): the scorer turns REM with ≥ 3 of 5 s of head movement and sustained NREM movement into WAKE, so "stays asleep" means "short enough to stay below the scorer's movement gate" (de-circularising test: step A5). | "Rats wake each other with every movement". |
| 28c | A housemate's movement raises the partner's chance of waking within 30 s. | **Candidate** | P(partner scored awake within 30 s) after vs in a window 60 s before: 1.2–1.9× in 30 / 30 ordered pairs (median ~1.5). | "After a housemate moved, its sleeping partner was about 1.5 times more likely to wake within half a minute." | Causal wording. Alternatives: shared drifts toward lighter sleep; passive IMU jostling of the partner without its own muscle activity (the LFP-EMG would separate). |

**Phase 6, the sleep-perturbation event library + LFP-EMG** (2026-10-08;
[report](ephys_spikes_sleep_events_2026c.md); plan Amendment 10 + two addenda, all before results):

| # | claim | status | main_evidence | allowed_wording | forbidden_wording |
|---|---|---|---|---|---|
| 29a | During shared sleep, most movements leave the mover asleep. Movement does raise the chance of waking, mostly through brief arousals. | **Established** (descriptive; scorer-gate caveat 2026-10-08) | 60 631 movement events in 145 co-sleep hours. After the first mover's onset in NREM: 71 % no WAKE within 60 s (random co-sleep seconds: 80.5 %). The wakes are MA < 40 s 19 %, ≥ 40 s 10 % (control 14 % / 5 %). woke60 above control in 6 / 6 rats. In REM, mover vs control 54 % vs 50 % (most REM bouts end within a minute anyway). | "Most movements during shared sleep did not wake the rat; when one did, the arousal was usually brief." Caveat: as #28b; the mover-vs-control excess is partly definitional until step A5. | "Movement wakes the rat"; any claim from the onset rate itself (the onset rule is sensitive and counts micro-movements: 90–220 per co-sleep hour). |
| 29b | Group movements (a sleeping housemate starts moving within 0.1 s of another) occur well above chance, a few to ~15 times per co-sleep hour. | **Established** (descriptive) | Share of seeds with a follower ≤ 0.1 s: 5.6–8.4 % vs a time-shift chance of 0.6–1.2 % (×6.7–9.3, both houses, NREM and REM). That is 5.0–15.3 above-chance group events per co-sleep hour (≤ 1 s: ×2.4–3.4, 7.5–33.5 per hour). | "Near-simultaneous group movements of sleeping housemates were 7–9 times more common than chance, roughly 5–15 per hour of shared sleep." | Group events counted with the 1-s window as all real (about half of the 0.1–1 s followers are chance). |
| 29c | Tight followers move their own muscles; they are not just jostled. | **Candidate** → **next stage (LFP)** | The LFP-EMG (300–450 Hz cross-channel correlation, 50 Hz) rises in tight followers: median Δcorr 0.018 NREM / 0.033 REM, vs −0.002 / −0.001 in non-movers, above non-movers in 12 / 12 animal × state. It rises with or slightly before their head acceleration (mean-trace half-maximum 0.00 vs +0.02 s). At matched head acceleration it is ~45–90 % of the first mover's across the six size × state cells (e.g. NREM mid / high tercile 0.017 / 0.030 vs 0.024 / 0.049). First movers' EMG leads their acceleration (−0.04 s). | "Rats that started moving within 0.1 s of a housemate showed their own muscle activity, beginning together with or just before their head movement, so the coupled movements are at least partly active responses." | "Purely passive", or "purely active" (the follower EMG is smaller than the first mover's at matched size, so the group may mix both). Reflex vs arousal-driven. |
| 29d | A housemate's movement barely changes the waking of partners who do not move themselves. The extra waking after a housemate moves lies in partners who also move. | **Candidate** (refines #28c) | woke60 in NREM: non-movers 20.3 % vs random co-sleep seconds 19.5 % (per rat: SF08 and SF11 above by 1.7 / 2.3 points, SF07 / SF10 / SF12 within 0.2 points, SF09 0.9 below); tight / loose followers 24.4 / 23.4 %; first movers 28.9 %. Event level (group events, NREM): all asleep participants stay asleep 47 %, some wake 44 %, all wake 9 %; control 55 / 36 / 9 %. | "A housemate's movement hardly woke partners that stayed still. The partners that moved with it woke somewhat more often." | "Rats wake each other" (#28c's 1.5× used a within-pair 60-s-earlier baseline and pooled followers with non-movers). |
| 29e | Loud in-house sound transients during sleep. | **Unresolved** | 657 candidates (mic jump ≥ 20 dB, all members asleep, no movement 5 s before): non-mover woke60 22.9 % vs 19.5 % control. Not listened to. | none beyond the counts | any claim of an external sound waking the rats before the listening check |

The **library itself** ($OUT_ROOT/2026c/sleep_events_20261008_1721/, README) is the deliverable for later use. It separates
the user's two scenarios per participant (`scenario` = woke / not_woken within 60 s), and carries pointers to the IMU,
LFP (storage), LFP-EMG (storage `analysis/emg_from_lfp`), house videos (CH05–CH08), house mic and CH01. It also holds
94 battery-round handling events as pre / post.

**Logic audit, 2026-10-08** ([docs/methods/sleep_logic_audit_2026-10-08.md](../../../../docs/methods/sleep_logic_audit_2026-10-08.md):
Fable's audit of the whole chain plus the main session's checks; the plan for the next stage is
[implementation_plan/2026-10-08-sleep-behaviour-explore.md](../../../../implementation_plan/2026-10-08-sleep-behaviour-explore.md)).

Changes above:
- #6 split into #6a / #6b;
- #10 re-worded;
- #13 withdrawn as a balance, #24 superseded;
- #14b added;
- the scorer-gate caveat on #28b / #29a;
- #4 / #16 / #29c moved to the LFP stage.

New claims:

| # | claim | status | main_evidence | allowed_wording | forbidden_wording |
|---|---|---|---|---|---|
| 30 | Over the 12 days the cohort moved sleep from night into day. | **Established** (descriptive) | Per-animal-day NREM deviations, coverage ≥ 0.5, pass2med: the night deviation falls −0.95 and the day deviation rises +0.77 min per recorded hour per day (both p < 1e-4, SEs clustered by day). Per animal: night slope negative 6/6, day slope positive 6/6, on both scorings. Raw: night NREM ~10–11 → 5–7, day ~33–35 → 40–41 min per recorded h. (Main session, check_drift.py.) | "Over the 12 days all six rats shifted sleep from the night into the day." | A night–day balance or budget (#13); a cause (adaptation, weather and activity are step C4). |
| 31 | Sleep that follows a wake carries more NREM than the time-of-day expectation, much more at night. | **Candidate** (descriptive; mechanism not separable) | NREM excess in the first hour +3.6 / +4.0–5.1 / +9.0–9.5 / +15.7–16.4 min after 2–7 / 7–30 / 30–120 / ≥ 2-h wakes, positive in 6/6 rats in every class, both scorings. But with night in the model (Phase-3 Q2 regression, 60 min): ln d +0.47 [−0.31, +1.24] (FINAL), +0.90 [−0.23, +2.02] (pass2med), n.s.; dark +9.5 / +8.0 min (p < 0.001). The clock starts at a sleep onset, so some excess is by construction. | "Sleep after a wake was NREM-dense, especially at night." | "An NREM rebound proportional to wake length" / "NREM homeostat" (night and the onset conditioning not separated; hypothesis H4 of the plan). |

**Synthesis, at the strongest wording the statuses allow** (rewritten 2026-10-08 after the logic audit; each part keeps
its status):
- **Established.**
  - In the field, when REM starts is set by the NREM accumulated since the last REM — a count that brief awakenings do
    not erase.
  - The night limits how often REM starts, not how long it lasts.
  - Over the 12 days the rats shifted sleep from night into day.
- **Candidate (strong).**
  - A wake of 7 min or more is not resumed: the earlier NREM no longer counts.
  - At night, longer wakes push REM back further.
  - Even after equally short wakes the night halves the REM-entry rate.
  - REM missed before a morning round is repaid within hours, specifically REM.
- **Organising idea (interpretation).** Only REM entry is regulated, by a count restarted by long wakes, a day/night
  gate, and possibly a slow REM deficit. Daily totals may be regular because the inputs are regular, not because a
  budget is enforced. This is tested by the scheduler model of the plan.
- **Not shown.** A day-to-day 24-h balance (#13 withdrawn), a fixed timetable, an NREM rebound proportional to wake
  length, and outside causes of awakenings.

**What promotes the Candidates:** steps A–E of
[implementation_plan/2026-10-08-sleep-behaviour-explore.md](../../../../implementation_plan/2026-10-08-sleep-behaviour-explore.md):
- A: the reproduction gate;
- B: the count model with τ_w;
- C: the matched day/night contrast;
- D: whether the morning payback needs a REM deficit;
- E: the generative checks.

The user's listening check still applies to #20 and #29e.
