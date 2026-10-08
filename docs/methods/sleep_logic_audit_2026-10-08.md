# Logic audit of the internal-sleep-schedule phases 0–6 (Fable, 2026-10-08), with the main session's checks

**What this is:**
- A read-only audit by a Fable 5.1 subagent of the main session's draft logic chain (all phases 0–6, cohort 2026c),
  launched on the user's request ("synthesize all phases, have Fable audit it, don't be too conservative").
- Questions 6 (day vs night) and 7 (a model of the implicit scheduler) were added by the user during the run.
- The scope rule (the "sleep behaviour explore": sequence + time / light + IMU + WISER + temperature + handling, no
  LFP features) applies throughout.

**Files** (off-repo: `D:/Field2026_analysis_out/2026c/sleep_logic_audit_20261008/`):
- the draft;
- Fable's check scripts `fable_checks*.py`;
- the main session's `check_drift.py` and its output.

**Consequences:**
- the plan [implementation_plan/2026-10-08-sleep-behaviour-explore.md](../../implementation_plan/2026-10-08-sleep-behaviour-explore.md);
- the claim-audit update of 2026-10-08 (#6, #10, #13, #14b, #30–#31) in
  [results/2026c/ephys_spikes/reports/ephys_spikes_sleep_schedule_claim_audit_2026c.md](../../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_schedule_claim_audit_2026c.md).

## The main session's checks (read these first; they override the report where they differ)

1. **#13 is a drift, not a night–day balance: confirmed independently** (`check_drift.py`, Phase 3b's per-animal-day
   deviation tables, coverage ≥ 0.5, SEs clustered by day). On `pass2med_remclean`:
   - The NREM night → day slope is −0.56 [−0.85, −0.28] within rat. It falls to −0.06 [−0.29, +0.16] with a linear day
     term, and −0.12 [−0.32, +0.09] with day fixed effects.
   - Over the cohort the night NREM deviation falls −0.95 and the day deviation rises +0.77 min per recorded hour per
     day (both p < 1e-4). This holds per animal: night slope negative 6/6, day slope positive 6/6, on both scorings.
   - The REM version: −0.41 (n.s.) within rat; with day fixed effects −0.20 (n.s.).
   - FINAL scores give the same picture.
2. **The NREM rebound is NOT proportional to wake length once the night is accounted for**, so it is not added as an
   Established claim.
   - Fable's numbers reproduce (`fable_checks_q2.py`): NREM excess in the first hour +3.6 / +4.0–5.1 / +9.0–9.5 /
     +15.7–16.4 min after 2–7 / 7–30 / 30–120 / ≥ 120-min wakes, positive in 6/6 animals in every class, both scorings.
   - But Phase 3's own Q2 regression (`…phase3_q2_regression_2026c.csv`, excess ~ ln d + dark + debt + animal, 60 min)
     gives:
     - ln d +0.47 [−0.31, +1.24] (FINAL) and +0.90 [−0.23, +2.02] (pass2med), both n.s.;
     - dark +9.5 / +8.0 min, p < 0.001.
   - Long wakes are almost all nocturnal, and the clock starts at a sleep onset while the expected rate is the
     time-of-day average including wake. The excess is therefore largely "an episode under way at night vs a mostly
     awake night baseline", partly by construction.
   - Kept as **Candidate (#31)**, worded descriptively. This also weakens THE LOGIC point 5 and the day-vs-night
     point 3 below ("the NREM rebound after long wakes").
3. **Not re-checked by the main session.** Fable verified these on our data with its scripts; the plan's first steps
   reproduce them before any status rises:
   - the censored Cox for #6 (ln d −0.286, 6/6; N_pre ≈ 0);
   - the dark-only grading of #6;
   - the matched night gain (5.0 vs 11.7 REM bouts per NREM h after 2–7-min wakes; FINAL only);
   - the day-demeaned / NREM-partialled morning payback (#10).

---

# Fable logic audit — the internal sleep schedule, Phases 0–6 (cohort 2026c), 2026-10-08

Read-only audit of `scratchpad/draft_logic_chain.md` against the claim audit (#1–#29), the phase reports, the code, and
the saved tables / 1-s states. Scope rule applied (user): the chain, the model and every proposed analysis use only the
scored state sequence, time / light, the head IMU (Phase-6 library), WISER, outdoor temperature and the handling gaps.
LFP-feature claims (#4 depth, #16 night-REM theta, #29c LFP-EMG) are marked **next stage (LFP)** and nothing below
builds on them.

**What I verified myself** (scripts `fable_checks*.py` in this scratchpad, all read-only; "V" in the text):
the B1b cycles table split by phase and by wake-length bin; a censored survival version of #6 built from the 1-s states
(episodes without REM kept); the day-vs-night REM-entry comparison at matched prior wake (Phase-3 episode table);
the night→day trade-off (#13) on Phase 3b's own deviation tables with and without a day term; the across-round
compensation (#10) with a day term, day-demeaned, and with NREM debt partialled; per-animal signs of the NREM rebound
after wakes (Phase-3 Q2 table); the scorer's gate rules in `score_sleep.py` and the B1b / Phase-6 code paths.
Everything else ("R") is taken from the reports as the claim audit states it.

---

## Executive summary

1. The draft's chain is right in its first step (a state variable: the NREM count since the last REM) and in its
   conclusion (regulation acts on REM entry, not REM duration). It is **stitched** in the middle: "graded robustness"
   mixes three unrelated measurements, and "two time constants" rests on the night→day balance (#13), which my check
   shows is **not a day-to-day balance at all** — it is a cohort-wide drift of sleep from night into day over the 12
   days (night NREM 10 → 6 min/h, day NREM 34 → 41; both p < 1e-4; the within-animal slope goes from −0.54 to −0.03 once
   a day term is allowed; between animals within a day −0.15, n.s.). (V)
2. What replaces it is stronger, not weaker: **(a)** any wake ≥ 7 min is *not resumed* — the pre-wake NREM count has a
   zero coefficient where resumption predicts ≈ −0.3, in both phases, and this survives keeping the 211 post-wake
   sleeps that never reached REM (Cox, 6/6 animals) (V); **(b)** the *graded* "longer wake → REM later" effect exists
   only in the dark (light: −0.10 ± 0.10; dark: +0.26 ± 0.07) and is therefore inseparable from "night" for wakes
   > 30 min (V); **(c)** independent of the preceding wake, **the night halves the REM-entry rate** (5.0 vs 11.7 REM
   bouts per NREM hour after the same 2–7-min wakes; first REM 15 vs 9 min; Cox HR 0.37 with prior wake in the model)
   (V); **(d)** NREM has an hour-scale homeostat the audit never claimed: NREM in the first hour after a wake rises with
   the wake's length (+4 → +16 min), positive in 6/6 animals on both scorings (V); **(e)** the morning-round REM payback
   (#10) is REM-specific (NREM debt partialled: +0.37 / +0.71 per min at 1 / 3 h) and survives day-demeaning
   (+0.31 / +0.85, p < 0.001, fixed thresholds) (V) — the one place a slow REM deficit shows, and the hinge claim.
3. Statuses to change: raise #6 (not-resumed part) and #10; add the NREM rebound and the matched night gain as new
   claims; **downgrade #13**; re-scope #14; move #4 / #16 / #29c to "next stage (LFP)".
4. The best organising idea is not "two time constants of one regulation" but **"only REM entry is regulated, by
   three inputs at three scales"** (a minutes-scale count restarted by long wakes, a slow REM deficit that outlasts
   wakes and handling, a day/night gate), with NREM regulated by its own rebound and REM duration by nothing.
5. The decisive next step is one held-out hazard model with explicit accumulators (Q5 / Q7): it tests reset-vs-discount
   (τ_w), the night gain vs the prior wake, and whether the morning payback needs a REM-deficit variable at all.

**THE LOGIC** (plain words, the chain I endorse):
1. Within sleep, when REM starts is set by how much NREM has accumulated since the last REM — a count, not a clock; it
   predicts NREM endings held out in every rat (67 % vs 4 %).
2. Brief wakes (< 2 min) leave that information intact. Any wake of 7 min or more is not resumed: the NREM before it no
   longer counts, by day as by night, whether or not the next sleep reaches REM.
3. At night — and only there — longer wakes push REM further back (9 → 25 min of NREM from 10-min to 4-h wakes) and more
   than half of the sleeps after a long wake end before any REM.
4. Independently of the preceding wake, the night halves the rate at which REM is entered and delays the first REM,
   while each REM bout lasts the same: the night is a gain on REM entry, not a change of the count.
5. NREM has its own hour-scale homeostat: the first hour of sleep after a wake carries extra NREM in proportion to the
   wake, and NREM lost at a morning round is partly made up within the hour.
6. REM has a slower deficit that outlasts a handling wake: REM missing before a morning round is repaid in the next
   1–3 h, specifically REM, independent of anything all animals shared that day. Within continuous day sleep no such
   repayment appears — the deficit shows only where the night or the handling built it and the day's gate releases it.
7. There is no day-to-day 24-h balance in these 12 days: the night→day "trade-off" is a shared drift of sleep from
   night into day. Daily totals are regular because the inputs are regular, not because a budget is enforced.
8. Housemates perturb (movements coupled within 0.1 s, mostly absorbed without a state change) but do not drive REM;
   temperature nudges REM share, not entry timing.

**THE LOGIC — day vs night** (5–8 lines):
1. Night sleep is the same machinery under a low REM-entry gain: after the same short wake, REM is entered ~0.45× as
   often, the first REM comes ~6 min later, and REM bouts last the same (71 vs 74 s).
2. On top of the gain, the night's long wakes (median 78 min) delay the first REM further, graded with wake length, and
   56–58 % of those sleeps end in another long wake before any REM. The 24/7 record separates the two effects: 55 dark
   episodes follow 2–7-min wakes, 101 light episodes follow 7–30-min wakes.
3. Night sleep is NREM-dense (the rebound after long wakes, +10–16 min in the first hour) and REM-poor (6.8 vs 17.4 %).
4. The day does not repay the night day by day; it is where the gate opens, so deficits built at night or by the morning
   round express there (the morning payback).
5. Across the cohort the animals moved sleep from night into day (a shared slow change; adaptation and/or weather) —
   to be explained with WISER activity and weather, not read as regulation.
6. Untested on the sequence alone: where and with whom they sleep (WISER house, group size) and cold nights. The LFP
   differences of night REM are next stage.

**THE MODEL** (≤ 8 lines):
- A discrete-time competing-risks hazard per 10 s (NREM → stay / REM / wake; REM → stay / NREM / wake; WAKE → stay /
  NREM) with latent variables computed deterministically from the observed sequence: **P** = REM-entry count (+1 per
  NREM s, multiplied by exp(−d/τ_w) over any wake of length d, discharged at each REM by a fraction that grows with the
  REM's length); **S** = NREM homeostat (up in wake with τ_r, down in sleep with τ_d); **D** = slow REM deficit (rises in
  all non-REM time at a gate-dependent rate, falls in REM); **G** = 2-harmonic phase + a dark step on REM entry; plus
  post-handling hours, and optional housemate / temperature covariates.
- Fit by profiling τ_w, the discharge fraction and τ_r / τ_d over grids with an inner multinomial GLM; animal
  intercepts and gains, shared time constants; forward chaining over the 22 day-half blocks.
- It must not lose to M2t held out, must beat a hard-reset, a no-discount, a momentum (2nd-order semi-Markov), a
  gate-only and a "night = prior wake only" variant, and in simulation (conditional on the observed long wakes) must
  reproduce the daily REM regularity, the carry-over curve, 4 vs 11 REM bouts per NREM h and the morning payback slope.
  Whether the morning payback is reproduced without D is the one simulation that decides if a REM deficit exists.
- Build P + G first (≈ 2 days), S and D next (≈ 3 days); no HMM, no per-animal time constants.

---

## Question 1 — Is the draft's chain a valid inference?

**Verdict: Step 1 valid; Step 2 half-stitched; Step 3's "two time constants" rests on a claim (#13) that does not hold
as stated; the conclusion "regulation on REM entry" is right and can be said more strongly.**

Where it is a real chain:
- #1 → #2 → #3 are the same quantity measured three ways (held-out gain; summary by since-last-REM terms; the shape of
  the hazard against the running count). "An accumulator read out as a REM-entry hazard" is a fair reading. (R)
- #14 (night limits entry, not duration) + #10 (payback through entry) + #22/#23 (temperature changes share, not entry
  timing) converge on "entry is the regulated knob". (R; #10's "through more bouts" is weaker, see Q2.)

Where it is stitched:
- The robustness table (Step 2) puts micro-movements (#28b/#29a), short wakes (#5) and long wakes (#6) on one axis as if
  they were one measurement. They are three: (i) Phase 6 measures whether the *scored state* changes after a movement —
  it says nothing about the accumulator (the accumulator is defined on the state sequence, so "filtered before it
  reaches the state" is true by construction); (ii) #5 is a held-out log-loss gain of pre-wake history on post-wake
  bouts; (iii) #6 is an OLS of NREM-before-first-REM on cycles that reached REM. The one test that would have put (ii)
  and (iii) on a single axis — the update model U (history × ln d) — did **not** hold (−0.18 % [−0.51, +0.03]). So the
  data show "information survives at < 2 min" and "the count is not resumed at ≥ 7 min", with the 2–7-min range
  undetermined (91 REM events, −0.28 % n.s.). A step (reset) and an exponential discount with τ of a few minutes both
  fit; nothing in Phases 0–6 distinguishes them. That is the τ_w question for the model.
- "Long interruptions restart the accumulator" is **two findings**, and the draft conflates them. (V)
  - *Not resumed*: the pre-wake count has a zero effect on the NREM needed before the next REM, in every wake bin
    (7–30 min −0.017 ± 0.019; 30–120 min −0.010 ± 0.031; ≥ 2 h −0.006 ± 0.010), where full resumption would give about
    −0.3 (N_pre median 3 min, IQR 0.3–9.2, against a needed 13 min). It holds by day and by night and in the censored
    survival version (−0.019 ± 0.030). This is solid.
  - *Graded with wake length*: the +0.26 per ln d is **dark-only** (light −0.10 ± 0.10, n 181, wakes 7–30 min; dark
    +0.26 ± 0.07, n 132, wakes 7 min–4 h). Categorical bins show a monotone ramp (0, +0.2, +0.5, +0.75, +0.93 log units
    for 15–30 / 30–60 / 60–120 / 120–240 / ≥ 240 min vs 7–15 min; AIC tied with ln d). A ramp over hours is **not a
    reset**; it says the wake adds something that grows with its length. Because wakes > 30 min are 85–100 % nocturnal,
    "graded" and "night" cannot be separated with these data (3 light episodes after ≥ 30-min wakes).
- Step 3's "slow day-scale balance" (#13) is the part that fails. On Phase 3b's own tables (fixed thresholds) the
  within-animal NREM slope −0.54 becomes −0.03 with a linear day term, and −0.15 [−0.33, +0.03] when each day is
  demeaned across animals; at ≥ 80 % coverage −0.91 → −0.28 [−0.69, +0.13]. The mean deviations run from +30 (night) /
  −14 (day) min on day 1 to −84 / +65 min on day 10; raw: night NREM 10–11 → 5–7 min per recorded h, day 33–35 → 40–41.
  The Phase-3b baseline had one common linear day term, which cannot remove opposite trends in the two phases. Also,
  windows moved away from dawn (21:00–03:00 vs 10:00–16:00 next day) give +0.43 [−0.02, +0.89]. The "one-way night → day
  coupling" (Q1d: day → night −0.02) is what a monotone drift produces, not a sign of regulation. (V)

**Is "two time constants" the best organising idea?** No. Three things carry the evidence, and they are three
quantities, not two speeds of one:
1. a minutes-scale **REM-entry count** (NREM since the last REM), restarted by any wake ≥ 7 min;
2. an hour-scale **NREM homeostat** — unclaimed in the audit but the most replicated number in Phase 3: NREM excess in
   the first hour after a wake +3.6 / +4.0–5.1 / +9.0–9.5 / +15.7–16.4 min for 2–7 / 7–30 / 30–120 / ≥ 120-min wakes,
   positive in 6/6 animals on both scorings (V); plus NREM made up after morning rounds (+0.17 / +0.23 per min,
   day-demeaned, p ≤ 0.009) (V);
3. a **slow REM deficit** that survives the handling wake: the morning payback is REM-specific (REM debt +0.37 / +0.71
   with NREM debt in the model; NREM debt ≈ 0, n.s.; r = 0.76 between the two debts) and not a shared-day effect
   (day-demeaned +0.31 / +0.85, p < 0.001) (V). It is seen only across the morning round; within continuous day sleep
   there is nothing (#9). Reading: a deficit builds where entry is gated (night, handling) and is released where the
   gate is open (day). Whether this needs a separate variable or falls out of the count + gate is exactly what the
   model's simulation decides (Q7).
   plus a **day/night gain** on REM entry that is not the prior wake (Q6).

"REM entry is the only regulated knob" is the simpler and stronger statement for REM; it must be paired with "NREM has
its own rebound", because the two are what the night's long wakes drive together.

**Best version (≤ 12 lines):** the THE LOGIC box above.

---

## Question 2 — The draft's weak points, plus mine

| # | weak point | changes a conclusion? | single test that settles it |
|---|---|---|---|
| 1 | **#6 survivor selection** (cycles that reached REM only; 211 of 524 post-wake sleeps dropped) | **No.** Cox with censoring: ln d −0.286 (se 0.073; HR 0.75 per e-fold; negative in 6/6: −0.13 … −0.44); N_pre −0.019 ± 0.030. Share reaching REM: 0.73 / 0.70 after 7–30-min wakes vs 0.42–0.44 after 30–240 min (V). | Done; the remaining step for "Established" is a forward-chained version (train earlier blocks, predict the next). Cost: hours. |
| 1b | **#6 confounded with night** (my finding) | **Yes, wording.** The graded part is dark-only; by day (7–30-min range) no dose effect. "Long wakes push REM back in proportion" → "at night, …". | None possible for > 30-min wakes by day (3 cases). Test the ramp *within the night* against time-of-night and WISER activity during the wake (Q5 #1, Hyp. 7). |
| 2 | **IMU shared by events and scorer** (#29a / #28b) | **Partly.** Verified in `score_sleep.py`: `imu_nremgate` = "moving + slow wave = WAKE"; `imu_remclean` rule 2 = REM with ≥ 3 of 5 s head motion → WAKE. So any movement longer than the scorer's reach (15-s EMG smoothing; 3 s in REM) is WAKE by definition: "movement raises waking" is partly definitional; "REM twitches stay REM" means "movements < 3 s" by construction. Not circular: the control contrast (71 vs 80.5 %), wakes starting > 15 s after the onset, group-event rates vs time-shift chance (#29b), and the non-mover partner outcome (#29d: no IMU onset by definition). | Recompute woke60 of first movers on the `imu` variant (`useEMG_NREM=False`: NREM = slow wave regardless of movement): if 71 % → ~80 %, the excess was the gate. Also report woke60 excluding wakes that begin < 15 s after the onset. Cost: hours if the `imu` 1-s states are on storage. |
| 3 | **#13 budget vs timing shift** | **Yes — bigger than the draft's worry.** Not a timing shift across dawn: a cohort-wide drift (night → day) shared by all animals; the individual day-to-day balance is −0.15 [−0.33, +0.03] (V). | Day fixed effects (done: n.s.) — only more days could restore it. Instead explain the drift: nightly sleep share ~ day index + nightly rain / temperature + WISER time outside the house (Hyp. 13). |
| 4 | **Handling vs time of day** (#10) | **No** for shared-day causes (day-demeaned slope +0.31 / +0.85). The remaining alternative is individual sleep-onset timing; but if an animal merely started sleeping later, its NREM debt would predict the payback too — it does not (+0.01 / +0.03). So the onset-timing reading is already weakened (V). | Natural dawn wakes ≥ 30 min ending 05:00–09:00 without a round, same debt / payback regression, fixed thresholds; and the main-sleep onset time as a covariate. Pass: REM-debt slope stays > 0.2, p < 0.05. Cost: half a day. |
| 5 | **Opposite phase trends in any before/after window that straddles dawn or dusk** (mine) | Yes for #13 (above) and for the **evening NREM payback** (+0.42 → +0.08 day-demeaned, n.s.) (V). Morning REM and NREM paybacks survive. | Add a phase × day interaction (or day fixed effects) to every C1 / Q1d baseline; report both. Cost: hours. |
| 6 | **"Via more REM bouts"** (#10) | Yes, wording: the bout-count slope is +0.14 (p 0.09) / +0.16 (n.s.) after day-demeaning; minutes survive, the mechanism does not (V). | Decompose payback into bouts × mean duration on the day-demeaned windows. |
| 7 | **Per-session thresholds in every night-vs-day contrast** | Potentially: night and day are different sessions, so FINAL thresholds differ between them; Phase 3 Q1 was not rerun on pass2med. | Rerun Q1a–b (and my matched comparison) on `pass2med_remclean`. Cost: hours. |
| 8 | **Hazard decline after 20–30 min of NREM since REM** (#3) | No (the audit already forbids "within-stretch decline"); it is the night mixture (long since-REM counts are nocturnal). | Hazard vs count within phase (Phase 3 Q1b figure) — already shows it; keep the wording. |
| 9 | **#7 clock question is partly answered** | Wording: a wall-clock REM pressure (time since REM including the wake) predicts the opposite of #6 at entry (longer wake → sooner REM); the data say longer wake → later REM. Keep Unresolved for the tie in continuous sleep, but say that at entry the wake does not count as NREM time. | The τ_w profile in the model. |

How `imu_remclean` could force outcomes (checked in `change_log/2026-10-05-sleep-rem-clean.md` and the code): rule 1
(no REM after > 10-s wake) cannot create "movement → wake"; rule 2 can only convert REM to WAKE where the head moves ≥ 3
of 5 s, so "REM movers stay REM 82–85 % at 10 s" is the share of REM movements shorter than ~3 s — a true statement
about the scored data, but "twitch-like" is then a definition, not a finding. The gate in `imu_nremgate` acts on NREM
through the 15-s-smoothed VeDBA: single 1–2-s movements do not cross it; sustained ones do.

---

## Question 3 — Consistency across phases

| pair | as written | resolution |
|---|---|---|
| #9 (no REM payback within sleep, 1–3 h) vs #10 (payback after morning rounds) | looks contradictory | Different regimes, one reading: a REM deficit is repaid only where it was built under a closed gate (night / handling) and released under an open one (day). Within continuous day sleep the gate is open and no deficit builds. The deficit is REM-specific (NREM debt partialled ≈ 0) (V). Decides: Q5 #3. |
| #6 (first REM delayed after long wakes) vs #12 (REM minutes over hours do not depend on wake length; withdrawn) | consistent | The delay costs < 1 REM bout per hour, and the hour after a long wake also carries +10–16 min extra NREM (more sleep), so REM minutes vs the time-of-day expectation are not lower. No conflict; #12 stays withdrawn. |
| #3 (accumulator) vs #2 (nothing beyond since-last-REM) | not a conflict | #2 *is* the accumulator: the since-last-REM terms are the summary; the 10 min–12 h bands add nothing beyond it. |
| #5 (history survives < 2 min) vs #6 (not resumed ≥ 7 min) | a gap, not a conflict | 2–7 min untested (91 REM events). Step vs discount undecided → τ_w. |
| #14 (night limits REM entry) vs #6 (long wakes delay REM) + the 4044 s vs 386 s prior wake | the draft treats them as independent; the user's confound | Both are real and separable (V): at matched 2–7-min prior wakes the night still halves the entry rate (5.0 vs 11.7 / h); within the night, longer prior wakes lower it further (2–7 min 5.0; 30–120 min 3.2; ≥ 120 min 2.3 / h). The night effect is a gain; the wake effect is on top. |
| #13 (night → day balance) vs #9 (no fast REM payback) | the draft reconciles them as two time scales | #13 is a drift, so there is no slow REM balance to reconcile; the "one-way coupling" is what a monotone shift produces. Drop the pairing. |
| #11 (REM ~1 min below for 6 h after rounds) vs #10 (payback after morning rounds) | compatible | A level (handling suppression) and a slope (those with more debt are less below). Keep both. |
| #22 (warmth raises REM share) vs #23 (not entry timing) | compatible, mechanism open | Share can rise through REM maintenance or fewer wake exits; test REM-bout duration and REM → wake exits vs temperature (Hyp. 14). Sequence-only. |
| #28c (partner 1.5× more likely to wake) vs #29d (non-movers barely wake more) | resolved by #29d | Keep #29d's reading; #28c's baseline pooled movers with non-movers. |
| #25 (no REM coupling to housemates) vs #26 (REM co-occurs 1.2×) | compatible | Shared timing, not coupling; the elsewhere control (1.25) settles it. |

No two claims contradict each other once #13 is re-read as a drift and #6 is split into "not resumed" and "graded in
the dark".

---

## Question 4 — Status changes (only changes)

| claim | now | proposed | why |
|---|---|---|---|
| #6a "a wake ≥ 7 min is not resumed: the NREM before it does not shorten the wait for REM" | Candidate (strong) | **Established (scoped)** after one forward-chained rerun (hours) | zero coefficient vs ≈ −0.3 under resumption, in every wake bin, both phases, censoring-robust (Cox), 6/6 (V) |
| #6b "longer wakes push REM back in proportion to their length" | Candidate (strong) | **Candidate, night only**; by day no dose effect in the 7–30-min range | light −0.10 ± 0.10; dark +0.26 ± 0.07; ramp over hours; confounded with night above 30 min (V) |
| #10 morning-round REM payback | Candidate | **Candidate (strong), REM-specific**; drop "mainly through more bouts" | survives day-demeaning (+0.31 / +0.85, p < 0.001) and NREM-debt partialling (+0.37 / +0.71); bout count n.s. after demeaning (V). Promote with the natural-dawn-wake contrast + a forward-chained baseline |
| #13 night–day trade-off | Candidate (NREM strong) | **Not shown as a day-to-day balance**; new descriptive claim: "sleep moved from night into day over the cohort (night NREM 10 → 6, day 34 → 41 min/h), shared by all animals" | within-animal slope −0.54 → −0.03 with a day term; day-demeaned −0.15 n.s.; non-adjacent windows +0.43 (V) |
| #24 (temperature partly explains #13) | Rejected (partly explained) | fold into the drift claim: temperature is one of the shared-day causes | consistent with the drift reading |
| #14 night limits REM entry | Established | Established + **new 14b (Candidate until rerun on pass2med)**: "at matched prior wake, the night's REM-entry rate is ~0.45× the day's and the first REM comes ~6 min later" | 5.0 vs 11.7 bouts per NREM h after 2–7-min wakes (n 55 / 294), latency 899 vs 530 s; Cox HR 0.37 with prior wake (V); per-animal signs not yet counted |
| new: NREM rebound after wakes | unclaimed | **Established (descriptive)**: "NREM in the first hour after a wake rises with the wake's length (+4 → +16 min)" | 6/6 animals in every wake class, both scorings (V); the 3-h value for ≥ 2-h wakes also 6/6 |
| new: evening NREM payback | part of #10 ("after any round") | drop "after any round" → morning only | +0.42 → +0.08 day-demeaned (V) |
| #5 | Established | unchanged; wording "the information survives", not "the count is unchanged" | U model n.s. |
| #29a / #28b | Established (descriptive) | unchanged + the scorer-definition caveat in allowed wording ("movements short enough to stay below the scorer's movement gate") | code check (V) |
| #4, #16, #29c | Candidate | **next stage (LFP)**; not in the chain | user scope rule |
| #9 | Established (scoped negative) | unchanged, scope made explicit: "within continuous, mostly daytime sleep" | reconciliation with #10 |
| #7 | Unresolved | Unresolved, add: "at entry a wake does not count as NREM time (longer wake → later REM, not sooner)" | #6 + the Cox |

---

## Question 5 — The decisive next analyses (sequence + allowed covariates only)

1. **One held-out hazard model with explicit accumulators (= the minimal build of Q7).**
   Inputs: 1-s FINAL states (pass2med as check), time, light, handling gaps. Model: per-10-s NREM step, multinomial
   stay / REM / wake with P(τ_w) = Σ NREM s since the last REM, each wake of length d multiplying P by exp(−d/τ_w)
   (τ_w ∈ {0, 15 s, 30 s, 1, 2, 5, 10, 30, ∞ min}), REM discharge fraction φ(REM length), the L0 clock terms, a dark
   step, animal intercepts. Comparison: forward chaining over the 22 blocks against M2t, against τ_w = 0 (hard reset)
   and τ_w = ∞ (pause), and against the same model without the dark step. Pass: held-out Δ vs M2t within +0.1 %;
   beats hard reset and pause with CI < 0 and ≥ 5/6 rats; the τ_w profile minimum is interior (30 s–10 min) and stable
   leave-one-animal-out. Gain: turns #5 / #6 into one parameter and settles reset vs discount. Cost: 2 days, CPU minutes.
2. **Prior-wake-matched day/night REM entry** (also Q6's first analysis). Inputs: the same + WISER house and number of
   co-located housemates per second. Model: the model of (1) plus ln d, dark × ln d, house / group covariates; or the
   simpler Cox of first-REM latency after every wake ≥ 2 min (animal strata). Pass: dark coefficient on REM-vs-stay
   ≤ ln 0.6 with ln d and P in the model, ≥ 5/6 rats, same sign on pass2med; dark × ln d reported as the night-only
   ramp. Gain: separates the gate from the wake once and for all. Cost: 1 day.
3. **The origin of the morning payback.** (a) natural dawn wakes ≥ 30 min ending 05:00–09:00 without a round, same
   debt / payback regression on fixed thresholds, with NREM debt and the main-sleep onset time as covariates;
   (b) the simulation of model (1) without any deficit variable, conditional on the observed wakes and gaps: does it
   reproduce the +0.3–0.8 slope? Pass for "a slow REM deficit exists": (a) slope > 0.2, p < 0.05, ≥ 4/4 rats with
   windows, and (b) the P + gate simulation gives a slope < 0.1. If (b) reproduces it, the deficit is the count seen
   through the gate and D is dropped. Gain: decides the third input of THE LOGIC. Cost: 1 day + the model.

(Cheap, already done here: #13 with day fixed effects → n.s.; close it as a drift and model the drift instead.)

---

## Question 6 — Day vs night sleep

**(a) Strongest framing.** "Night sleep is the same regulation in a low-gain regime." The evidence for a *gain* (not a
different rule set): at matched short prior wakes the REM-entry rate is 0.45× (5.0 vs 11.7 per NREM h), first REM 15 vs
9 min, REM bout length unchanged (71 vs 74 s), and the history × dark interaction is small (−0.13 %). The night's
*inputs* then differ: long prior wakes (median 78 min vs 14 min) delay REM further (the ramp) and cut the share of
sleeps that reach REM to 42–44 %; the NREM rebound after those wakes makes night sleep NREM-dense. Connection to the
schedule theme: the count (P) is the same; the night multiplies its read-out by ~0.45; the morning payback is the
night-built REM deficit released at the day's gain. The "one-way budget" is not a mechanism: it is the cohort drift
(night → day over 12 days), and the day is simply where REM is made (17 % of sleep vs 7 %).

**(b) Confounds and how the 24/7 design breaks each.**
- *Prior wake*: matched bins exist in both phases — 55 dark episodes after 2–7-min wakes vs 294 light; 101 light episodes
  after 7–30-min wakes vs 14 dark. Broken for wakes ≤ 30 min (V). Not breakable above 30 min by day (3 episodes).
- *Sleep location and group size*: WISER house per second gives night and day sleep in both houses, alone / with mates /
  in the field. Test the night gain within "house with ≥ 1 mate" only, and the group-size effect within phase.
  Caveat: house = ROI + 14 in, not body contact; field sleep is rare and WISER-noisy at night.
- *Temperature*: nights are always colder, so raw temperature is collinear with phase; the anomaly (within phase) adds
  nothing to entry (#23). Partial break: compare the warmest nights with the coldest days in the overlapping 15–18 °C
  band at matched prior wake.
- *Per-session thresholds*: night and day are different sessions, so every night/day number must be reproduced on
  `pass2med_remclean` (not yet done for Phase 3 Q1 or for my matched comparison).
- *Episode length and censoring*: night episodes are shorter (2406 vs 3974 s); rates per NREM hour and Kaplan–Meier /
  Cox on latency handle it (used).
- *Handling at dawn and dusk*: night episodes near rounds are post-handling; exclude the 3 h after a round from the
  matched comparison (not yet done).
- *Session-relative z-scores* (REM theta / SW / IMU): next stage (LFP); the IMU-EMG z is usable now but is relative to
  the session's NREM, so night and day sessions have different baselines — use the raw 50-Hz VeDBA on the field-PC
  clock instead (Phase-6 library).

**(c) Decisive analyses (concrete).**
1. **Prior-wake-matched REM-entry hazard** (Q5 #2) — first. Add: exclude 3 h after rounds; rerun on pass2med; per-animal
   signs; report the dark coefficient at d < 7 min and at 7–30 min separately. Pass as in Q5 #2.
2. **Light step vs circadian curve vs prior wake at the transitions.** Inputs: episodes starting within ±2 h of sunset
   and of sunrise, matched prior wake (< 7 min), P at onset. Model: REM-entry hazard with a 2-harmonic clock vs the same
   + a step at the light transition vs the same + ln d only. Pass: the step improves held-out log-loss on the
   transition hours with CI < 0 and ≥ 5/6 rats → the gain is light-driven; otherwise circadian. Cost: 1 day.
3. **Where and with whom.** WISER house and co-located housemates per second (Phase-5 base terms): REM-entry hazard and
   NREM → wake hazard with group size × phase; and the night gain within house-with-mates sleep only. Pass: the dark
   coefficient is unchanged (within ±0.1) when restricted to house-with-mates; group size reported with sign counts.
   Cost: 1 day (needs no new data). Needs video for body contact / huddling — state as such.
4. **The night → day drift.** Per animal-day: night sleep share, time outside the house (WISER), nightly temperature /
   rain, day index. Model: sleep share ~ day + weather + activity, animal FE. Pass: R² > 0.5 from weather + activity
   with the day term n.s. → the drift is environmental; else adaptation. Cost: half a day.

---

## Question 7 — A model for the implicit scheduler

**(a) Specification.** Per animal, per 10-s step (1-s states aggregated; 10 s matches the current hazard model).
State variables, all deterministic functions of the observed history given the parameters:
- **P** (REM-entry count, minutes): P ← P + 1/6 per NREM step; during a wake of length d (any length, MAs included):
  P ← P·exp(−d/τ_w); at the end of a REM bout of length r: P ← P·(1 − φ(r)), φ(r) = 1 − exp(−r/κ) (Park's refractory
  ∝ REM_pre lives in κ); unknown epochs: P frozen, then a flag "unknown since" enters the hazard.
- **S** (NREM homeostat, 0–1): dS = (1 − S)/τ_r per wake step, −S/τ_d per sleep step; starts at the animal's mean.
- **D** (slow REM deficit, minutes): dD = +ρ·g(t) per non-REM step (ρ = the day's REM need per minute; g(t) ≥ 0 so the
  deficit grows faster where the gate is closed — or simply constant), −1/6 per REM step; D is clipped at 0 below.
- **G**: gate on REM entry = β_c·[sin, cos]_{k=1,2}(t) + β_dark·dark(t); the same two terms, separately, on wake entry.
- **Inputs**: post-handling hours (a decaying term after each gap, as #11), optional housemate terms (n_mates,
  mates_asleep, a housemate movement in the last 10 s), optional temperature anomaly.
Observation model: the scored states, with the per-step multinomial hazards
h_R = softmax(α_R + f(P) + γ_S·S + δ·D + G + inputs + animal), h_W = softmax(α_W + γ_W·S + G_W + …) from NREM;
from REM: exit hazards to NREM / wake (constant + phase; no history, per #14); from WAKE: sleep-onset hazard on S +
phase + housemates (needed only for the full simulation). Scoring rules are part of the observation: simulated 1-s
sequences get the scorer's minimum-duration rules (6 s), REM ≥ 7 s, no REM after > 10-s wake, before any comparison;
unknown epochs are censored in the likelihood (as now).

**(b) Estimation.** Because P, S, D are deterministic given (τ_w, κ, τ_r, τ_d), the likelihood is the current
multinomial GLM's likelihood with transformed features: profile the time constants over small grids (τ_w 9 values,
κ 4, τ_r / τ_d 3 × 3) and fit the linear part by IRLS inside — minutes per fit on 126 k NREM steps, so the full grid is
< 1 h on CPU. Animal-specific intercepts and gate amplitudes; time constants shared (6 rats cannot identify per-animal
τ's; show per-animal profile curves as a check). A true latent-state model (stochastic P, particle filter / HSMM) is not
needed for the claim — "P is a function of the observed history" *is* the hypothesis, and the plan's HMM gate was never
triggered (bands add nothing). Identifiable: τ_w (from the 2–7-min wakes; expect a wide but interior CI), κ (from
REM_pre), β_dark vs ln d (only because matched episodes exist), ρ·δ (from the morning windows). Weakly or not
identifiable: τ_r / τ_d without deprivation (fix to the rat literature range or profile and report flatness); D vs P
within the day (collinear) — D is identified only across gaps and nights. Not identifiable: anything neural.

**(c) Tests.** Held out by forward chaining over the 22 blocks, Δ as now, "holds" = CI < 0 and ≥ 5/6 rats:
- vs **M2t** (the feature model; the mechanistic model has fewer parameters): pass = not worse by more than 0.1 %;
- vs **hard reset** (τ_w = 0 for d ≥ 7 min, pause below) and **pause** (τ_w = ∞): pass = beats both;
- vs **momentum** (Stephenson 2025: a 2nd-order semi-Markov — hazards on the previous two bouts' types and log
  durations, no accumulator): pass = beats it, especially on bouts after wakes;
- vs **gate-only** (no P: clock + elapsed + dark): pass = beats it by ≥ the #2 margin (−0.5 %);
- vs **"night = prior wake only"** (no β_dark; S and τ_w free): pass = the dark-step model wins on the dark steps after
  wakes < 7 min, ≥ 5/6 rats.
Generative checks, simulating conditional on the observed long wakes (≥ 7 min) and gaps (so the activity pattern is
real and only sleep's interior is generated), 100 replicates: (i) daily REM total mean and SD across days within
±25 % of 1.8 ± 0.1 h and NREM within ±10 % of 9.7 ± 0.2 h; (ii) the carry-over curve: held-out gain of pre-wake history
by wake bin reproduced in sign and order; (iii) REM share 6.8 vs 17.4 % and 4 vs 11 bouts per NREM h within ±20 %;
(iv) first-REM latency medians by wake bin and phase within ±25 %; (v) the morning payback slope on the simulated data
(fixed-threshold definitions): with D, within [0.2, 1.0]; without D, report — if < 0.1, D is needed; (vi) the night → day
correlation of deviations ≈ 0 after a day term (the model has no budget; the data agree). Fail on (i)–(iv) means the
specification is wrong, not the data; fail on (v) decides D.

**(d) Claims it could support if it passes.** "In the field, REM timing follows one count of NREM since the last REM,
discounted by any wake with a time constant of τ_w, read out through a gain that is ~0.45× at night, with [or without]
a slow REM deficit; the daily REM total emerges from these rules without a daily budget." And: "the same rules
reproduce the carry-over across wakes, the night's REM poverty and the morning payback." Never: a neural scheduler or a
circuit; causality of light vs activity (the gate could be either); that REM *must* occur; anything the scorer's rules
built in (brief REM attempts deleted, REM ≥ 7 s); anything about REM function.

**(e) Cost.** Minimal version (P with τ_w and κ, G, animal intercepts, held out vs M2t / reset / pause / gate-only):
≈ 2 days coding on top of `sleep_schedule.py`'s feature and fold machinery; compute < 1 h per grid. Add S and the
wake / REM exit hazards for simulation, the momentum alternative and the generative checks: ≈ 3 days. D and the
morning-payback simulation: 1 day. Leave out: HMM / particle filters, per-animal time constants, housemate and
temperature terms (add as covariates at the end only if the base passes), video.

---

## HYPOTHESES FOR THE SLEEP-BEHAVIOUR EXPLORE (sequence + time / light + IMU + WISER + temperature + gaps)

Ranked by expected information. Themes: S = schedule, DN = day vs night, M = scheduler model. Costs: h = hours, d = days.

1. **The wake discount has a time constant of minutes (not a step).** Profile τ_w in the P model, held out. 2 d. S, M.
2. **The night REM-entry gain is independent of the prior wake.** Matched-wake hazard with dark × ln d. 1 d. DN, S.
3. **The morning REM payback is a REM-specific deficit that survives wakes.** Natural dawn wakes + NREM-debt partial +
   the P-only simulation. 1 d + model. S, M.
4. **NREM rebound scales with wake length and with the wake's activity** (WISER distance / time in the field during the
   wake): active wakes vs quiet wakes of equal length — if activity, not duration, drives the rebound and the REM delay,
   the "wake" variable is sleep pressure built by behaviour. 1 d. S, DN.
5. **The night ramp (longer wake → REM later) is time-of-night, not wake length**: within the dark, ln d vs hours since
   sunset at matched P. h. DN.
6. **REM discharge scales with the REM bout's length** (refractory ∝ REM_pre, Park): φ(r) in the model vs a constant.
   h within the model. S, M.
7. **REM bout duration is unregulated**: ln REM duration on P at onset, dark, prior wake, temperature, group size — the
   planned C3 that was never run. h. S, DN.
8. **REM exits differ by phase**: the share of REM bouts ending in wake vs NREM at night vs day at matched duration. h. DN.
9. **A daily REM quota does not exist**: add "REM minutes since sunrise" (and since the last long wake) to the hazard;
   held out. h. S, M.
10. **Sequential cycles are rarer at night because of the gain, not because of interruptions**: second-REM-within-135-s
    rate vs MA count in the interval, by phase. h. DN.
11. **Microarousal rate rises as P rises** (pre-REM fragility; Benington–Heller "REM attempts"): MAs per NREM minute vs
    the running count, by phase. h. S.
12. **Arousability tracks the state variables**: P(wake | movement) from the Phase-6 library as a function of P, time
    since sleep onset, phase, group size; the `imu` control scoring to de-circularise. 1 d. S, DN.
13. **The night → day drift is environmental**: nightly sleep share ~ day + rain + temperature + WISER time in the field.
    h. DN.
14. **Warmth raises REM share through maintenance, not entry**: REM bout duration and REM → wake exits vs the
    temperature anomaly. h. DN.
15. **Group size changes sleep maintenance, not REM entry**: NREM → wake hazard and sleep-onset latency vs co-located
    housemates (Phase-5 base terms), by phase. h. DN.
16. **Housemates' long wakes (foraging departures) end the partner's sleep**: partner's wake hazard in the 2 min after
    a housemate leaves the house (WISER), vs chance. h. DN, S.
17. **Sleep-site change after a long wake delays REM** (vigilance at a new site): first-REM latency when the sleep site
    (WISER house / zone) differs from the pre-wake site, matched wake length. h. S. (Body contact / huddling: video.)
18. **Handling suppresses REM beyond the wake it causes**: post-round first-REM latency vs natural wakes of matched
    length and clock time (sequence-only version of E3). h. S.
19. **Post-REM refractoriness is a wall-clock phenomenon while accumulation is NREM-time**: separate clocks for the
    refractory dip and the rise in the hazard. h. S, M.
20. **Inter-REM intervals shorten within a SLEEP episode** (ultradian progression): k-th interval vs k at matched P and
    phase. h. S.
21. **The light-dark transition is a step, not a smooth curve** (light-driven vs circadian gain): Q6 (c) 2. 1 d. DN.
22. **Weather as a shared disturbance**: REM entry and wake exits on rainy vs dry nights at matched prior wake. h. DN.
23. **The 2–7-min wakes are two kinds** (MA-like vs active): split by WISER displacement / IMU activity during the wake;
    does the carry-over differ? h. S.
24. **Fragmentation beyond totals (#17) is the P-reset in disguise**: frag60 loses its gain once τ_w is in the model.
    h within the model. S, M.
25. **Five females (09-11 19:40 →) change the gate or the arousability**: descriptive only, after-cut data. h. DN.
Needs video (state as such): huddle / body contact vs REM entry; who initiates group movements; identity of the
housemate that leaves.

---

## Do not do

- Do not report #13 as "sleep is balanced over 24 h" or as a one-way budget; report the night → day drift and model it.
- Do not present "two time constants" as the organising idea; present three inputs on REM entry + the NREM rebound.
- Do not build any chain step on #4, #16 or #29c (LFP) at this stage; do not use z-SW depth as the mediator of #6.
- Do not say "long wakes reset the accumulator" without the split: *not resumed* (both phases) vs *graded* (night only).
- Do not read "movement leaves the rat asleep / wakes the rat" without the scorer-gate caveat; do not count ≤ 1-s
  followers as group events (half are chance).
- Do not use per-session thresholds (FINAL) for any contrast whose two sides are different sessions (night vs day,
  before vs after a round) without the pass2med check; do not use a common linear day term for windows that straddle
  dawn or dusk.
- Do not fit per-animal time constants, an HMM / HSMM, or a stochastic latent P before the deterministic P model has
  been tested; do not add housemate / temperature terms before the base passes.
- Do not read the hazard decline after 20–30 min of NREM-since-REM as refractoriness (night mixture).
- Do not make body-contact or huddling claims from WISER house membership; wait for video.

---

## Verification ledger (what was verified vs taken from reports)

Verified in data / code (V): A1–A7 (B1b by phase, bins, N_pre by bin), B (Cox with censoring, per animal), C1–C4
(matched prior-wake day/night), D and D2 (#13 with day term, day-demeaned, non-adjacent windows, raw drift), C1-trend
(morning / evening payback with day term, day-demeaned, NREM-debt partial), Q2 per-animal signs (NREM rebound 6/6 both
scorings; REM excess after ≥ 2-h wakes 4/6 FINAL, 6/6 pass2med), the scorer gates (`score_sleep.py` VARIANTS; rem-clean
rules), B1b code (2-harmonic hour; cycles reaching REM only), Phase-6 outcome definitions. Scripts: `fable_checks.py`,
`fable_checks_d2.py`, `fable_checks_c1.py`, `fable_checks_last.py`, `fable_checks_q2.py` (scratchpad).
Taken from reports (R): all held-out Δ values (#1–#3, #5, #15, #17, #23, #25), the Phase-5/5b/5c/6 coupling numbers,
#11, #22, the Phase-0 counts, the literature audit.
Limits of my checks: the light / dark split in A used clock hours 06:36–19:24 (B and C used NOAA sun times); my #13
windows used raw within-animal deviations, not the GLM baseline (the D2 check on Phase 3b's own tables is the one to
cite); the matched comparison C is on FINAL only (needs pass2med); per-animal signs for C2 not counted.
