# The internal sleep schedule: memory, carry-over across wakes, compensation, night vs day (2026-10-07 → 10-08)

**Plan:** [implementation_plan/2026-10-07-sleep-internal-schedule.md](../implementation_plan/2026-10-07-sleep-internal-schedule.md)
- revision 2, approved by the user ("go for it");
- Amendments 1–5, all after results, from the user's reviews.

**Literature:**
- [docs/methods/sleep_sequence_literature_audit_2026-10-07.md](../docs/methods/sleep_sequence_literature_audit_2026-10-07.md)
  (Fable audit + our checks);
- [docs/methods/sleep_rem_permissive_substates_literature_2026-10-07.md](../docs/methods/sleep_rem_permissive_substates_literature_2026-10-07.md)
  (Opus audit).

**Claims:** [claim audit](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_schedule_claim_audit_2026c.md); it
supersedes the v1 / v2 cycle audits where they differ.

## What changed

- **`ephys/sleep_schedule.py`:**
  - `phase0` — definitions and counts; Watson-2016 episode units; gap table with causes and per-animal evidence;
  - `phase1` — memory curve, clocks, cycles ahead, own vs shared history, opportunity / timing split;
  - dispatch of the later phases;
  - `--selftest`, and `--smoke` for synthetic data.
- **`ephys/sleep_schedule_phase2.py`** — Phase 2:
  - C2: empirical hazards and the running clock;
  - B1: carry-over across natural wakes, the carry-over curve by wake length, the clock test;
  - B1b: a long wake vs the next 3 REMs;
  - C1: compensation (REM minutes, count, duration; NREM) on both scorings;
  - B2 / B3: across battery gaps with a purge.
- **`ephys/sleep_schedule_phase2b.py`** — the user's follow-ups:
  - E1: effect sizes on an interpretable scale;
  - E2: NREM depth (lagged SW) for long wakes and for the hazard;
  - E3: NREM tails, natural vs recording stops;
  - E4: morning vs evening compensation.
- **`ephys/sleep_schedule_phase3.py`:**
  - `phase3` — the 24/7 record: Q1 naps vs day sleep, Q2 recovery trajectories, Q3 fragmentation;
  - `phase3b` — same-events catch-up; 24-h budget robustness.
- **New user decisions:**
  - exclude everything from 09-11 19:40 (the females);
  - forward chaining as primary validation;
  - episode units follow Watson et al. 2016, Neuron 90:839 (the user's reference, `Ref/`): MA < 40 s; 100 s = our
    pipeline's `_states_to_episodes`; 20 s = Park.
- **The in-house microphones** (separate change log:
  [2026-10-07-audio-levels-and-post-run-hook.md](2026-10-07-audio-levels-and-post-run-hook.md)):
  - per-second band levels of MIC01 / MIC02 and the CH01 / CH02 camera audio, on storage;
  - the description-only pilot `ephys/mic_wake_pilot.py`.

## Headline definitions (formulas in the reports' Definitions sections)

- **Step.** 10 s of an NREM bout; the outcome is stay / REM / Wake at the bout's end, as a multinomial logit.
- **Layers.**
  - L0: animal, 2-harmonic time of day, linear experiment day, elapsed spline.
  - L1 (current state): ln(1 + preceding wake), wake share of the last 10 min.
  - L2 (since the last REM): NREM-since spline, wake since, ln REM_pre, anchor.
  - L3: REM / wake shares in bands 10–30 … 270–720 min.
  - M2t: the NREM-since count runs through the bout (bout start + elapsed).
- **Validation.**
  - Forward chaining over 22 day-half blocks (15–16 folds).
  - Δ = held-out log-loss change in % of the smaller model; 95 % CI by bootstrap over folds.
  - **Holds** = CI < 0 and ≥ 5/6 animals.
- **Opportunity / timing (Larson–Dinse).** $\pi=\sum_t S(t-1)h_R(t)$, and
  $\log S(t^*-1)h_{type}(t^*)=\log P(type)+\log f(t^*\mid type)$.
- **Compensation.** $\text{debt}_A=E[\text{REM}_A]-\text{REM}_A$, $\text{payback}_B=\text{REM}_B-E[\text{REM}_B]$ (minutes).
  - E comes from leave-one-block-out GLMs (animal + phase + linear day).
  - A positive slope = catch-up.
- **Recovery trajectories.** Cumulative observed − expected (per-second baseline rates) from the sleep onset after an
  interruption, up to 6 h, censored at record ends.

## Results (statuses in the claim audit)

**Established:**
- History predicts NREM endings. Δ −1.53 % (15/15 folds, 6/6 rats). Bouts rated most vs least likely to end in REM:
  67 % vs 4 % did.
- History is summarised by the current state + quantities since the last REM. Bands up to 12 h add nothing.
- REM propensity builds with accumulated NREM: lowest at 2–3 min, plateau at 8–20 min. A running count beats the
  bout-start value (−0.83 %, 5/6).
- History carries over across wakes < 2 min.
- The night limits REM entry, not REM maintenance:
  - REM share 6.8 vs 17.4 %;
  - 4 vs 11 REM bouts per NREM hour;
  - first REM at 20.5 vs 10 min;
  - REM bout duration 71 vs 74 s (n.s.).
- Within continuous sleep, no REM catch-up over 1–3 h. The FINAL-score "persistence" was a per-session threshold
  artefact; it vanishes with fixed thresholds.

**Candidate:**
- Long wakes push REM back: +0.26 per ln wake (6/6). It is not resumed from pre-wake NREM and not explained by depth.
- Deeper recent NREM → REM; shallow → wake (6/6).
- After morning battery rounds, REM catch-up through more bouts (fixed thresholds +0.39 / +0.72; evening none). NREM
  is made up within the first hour after any round.
- After handling, REM stays ~1 min below expectation for 6 h.
- Night–day sleep trade-off: NREM within-rat −0.54 to −0.91 (p < 0.001); REM weaker, in the same direction.
- REM-entry rules differ slightly at night (−0.13 %).
- Fragmentation is borderline (−0.17 %, 6/6, CI touches 0).
- MIC02 = house_1.

**Unresolved:**
- NREM vs clock time.
- Carry-over across battery gaps (85 REM events).
- Wake length and REM minutes over the following hours: the earlier "delay then catch-up" is withdrawn after the
  same-events check.
- Sound causes of wakes.
- The mechanism.

## Amendments (all in the plan; numbers in the reports are unchanged by wording fixes)

1. **Phase 1 reading corrected** after the user's review:
   - the opportunity / timing split is read by end type;
   - the refractory figure was mislabelled (fixed in the code);
   - cycles ahead are scoped;
   - wake is the clock separator.
2. **C1 reported on both scorings.** The within-record persistence was a scoring artefact.
3. **Phase 2b,** the user's follow-ups: effect size, depth, tails, morning vs evening.
4. **Phase 3,** the 24/7 record: naps vs day, recovery trajectories, fragmentation.
5. **Phase 3b,** before the audit (user review: "be bolder" — met by checking):
   - the same-events catch-up, which withdrew "pure delay";
   - the 24-h budget in minutes, within-rat and on both scorings. NREM is robust; REM is weaker.

## Verification

- `python ephys/sleep_schedule.py --selftest` PASS: Watson units, step features, gap bookkeeping, and the
  opportunity / timing identity.
- **Smoke runs on synthetic semi-Markov data** with no built-in history effect: nothing holds in Phases 1–2.
  - Lesson: per-bin and long-horizon p-values can be spurious (the 6-h horizon gave a false ln d effect), so per-animal
    signs are reported throughout.
  - The synthetic generator happened to produce lower night REM; the Q1 code reported it correctly.
- **Determinism:** the Phase-2 rerun reproduced every number exactly.
- **Fixed-threshold check:** `pass2med_remclean` for the compensation, trajectory and budget analyses.
- The agent judged no figure.

## Bulk and storage

- Run folders: `D:/Field2026_analysis_out/2026c/sleep_schedule_phase{0,1,2,2b,3,3b}_<ts>/`.
- In-repo pointers: `results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_<phase>_2026c.json`.
- No server step for the sleep analyses; local only.

## Phase 4 — ambient temperature (2026-10-08; plan Amendment 6, prediction written before results)

`ephys/sleep_schedule_temp.py`, run by `phase4`.

**Inputs:**
- Outdoor temperature from the on-site console, 08-31 → 09-17, 8.6–28.4 °C.
- The anomaly = temperature minus its 2-harmonic time-of-day fit (SD 3.0 °C).

**Results:**
- **REM entry, held out:** nothing (+0.04 %, 3/6).
- **Hourly REM share of sleep:** +0.040 logit per °C (p 0.002, 5/6) — in the predicted direction, but small. Sleep
  amount: no effect.
- **The night–day NREM trade-off** survives temperature: −0.54 → −0.39, still p < 0.001. Warmer days had less daytime
  NREM.
- **Hazard by temperature tertile:** no consistent order.

**Claims #22–24 in the audit.**

## Mic listening review (2026-10-08)

`ephys/mic_listen_review.py` builds the page → `D:/Field2026_analysis_out/2026c/mic_listen_review_20261008_1238/index.html`.
- **Cards:** 48, blind and shuffled — 40 pilot events (8 per candidate class) and 8 controls (the rat asleep).
- **Media per card:** own-mic audible clip and a ×8 slowed clip for ultrasonic calls; spectrograms of own / other /
  outdoor; outdoor audio.
- **Answers** are exported to `ephys/configs/mic_listen_review_2026c/`. Awaiting the user.
- **Incomplete cards:** L38 (window across a file boundary) and L09 (no outdoor audio).

## Phase 5 — REM synchrony between animals (2026-10-08; plan Amendment 7, written before results)

`ephys/sleep_sync.py`, run by `phase5`.

**Data:** an absolute 1-s timeline per animal, WISER house per second, and the "mate" terms
(co-located; elsewhere as the control).

**Results:**
- **Held out:** housemate REM onset / REM adds nothing (+0.08 %, 0/6 animals; coefficients ≈ 0). The elsewhere-animal
  control is the same.
- **Raw:** REM co-occurs ~1.2× above chance, and the raw entry ratio is larger for animals elsewhere (1.25) than for
  housemates (1.10). So it reflects shared timing, not coupling.

**Claims #25 (Rejected, scoped) and #26 (Established, descriptive).**

