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

## Phase 5b — local, fast coupling of movements during sleep (2026-10-08; plan Amendment 8, written before results)

`sleep_sync.py` `phase5b`.

**Data:** head-movement onsets during sleep from the head-IMU seconds cache (field-PC clock).

**Results:**
- **Same-house pairs:** 13.8× at lag 0, ~5× at ±1 s; REM twitches 15×; 30/30 pairs.
- **Elsewhere:** 1.24×.
- **Cascades:** 3–3.6× above baseline.

**Claim #27 (Candidate).** Open: who moves first (needs the 50-Hz IMU), and active vs passive coupling.

## Phase 5c — the coupling at 20 ms with the IMU-as-EMG; twitch or awakening (2026-10-08; plan Amendment 9, before results)

`sleep_sync.py` `phase5c`.

**Signal:** VeDBA at 50 Hz from `make_imu` on the field-PC clock; θ = median + 8·MAD of NREM.

**Results:**
- **Timing:** peaks at 0.00–0.07 s (15 / 15 pairs); 6–10× within ±0.1 s; 1.6–2.1× at 0.1–1 s.
- **Most sleep movements are brief:** ~92 % of NREM movements stay asleep, and 82–85 % of REM movements stay in REM.
- **Partner's waking within 30 s:** ×1.2–1.9 (30 / 30 pairs).
- **Leader:** SF07 moves first in 58 % of coupled pairs (likely within clock tolerance).

**Claims #28a–c.** The decisive next check would be the LFP-EMG of the partner (passive jostle vs active movement).


## LFP-EMG product for every session (2026-10-08; the user: "save it like PPP7 day8"; plan Amendment 10)

`ephys/emg_from_lfp.py` (`--selftest`) writes per session:
- `<s>.EMGFromLFP.LFP.mat` — the lab's standard. It is the pipeline's own `_compute_emg_from_lfp` (= neurocode
  `getEMGFromLFP`): 2 Hz, ±0.5-s windows, one channel per shank.
- `<s>.EMGFromLFP50Hz.npz` — fast, for the user's time-resolution concern. 50.4-ms windows every 20 ms on the make_imu
  50-Hz grid, two channels per shank, `t_pc_ms`, `corr`, `log_rms`.

Storage: `3rd_rat/analysis/emg_from_lfp/` (203 sessions, VERIFY PASS, `copy_to_storage.sh` part `emg_from_lfp`).

- **Pipeline quirk found.** For every A4x16 animal, the scorer's earlier `lfpemg` pilot files used all 64 channels:
  the pipeline turns a Python list of equal-length spike groups into 64 one-channel groups. The new files use one
  channel per shank. The sleep scores are unaffected: only EMG channel selection uses that parser, and FINAL uses
  the IMU.
- **Route.** BioHPC was ~200× slower than this PC that afternoon. The run was done here (6 workers, 36 min), reading
  storage read-only, then uploaded and stored with the verified copy. The LFP is read once, sequentially; outputs
  are array-MD5-identical to the validated memmap run.
- **Checks.**
  - The standard file reproduces the scorer's own pilot file exactly (Δ 0.0) when given the same channels.
  - The fast product's 1-s means correlate 0.994 with the standard.
  - SF07 09-02 is identical from the D: copy and from storage.
- **Copy-script fixes found on the way** (`copy_to_storage.sh`):
  - the commit lookup is now on one line;
  - V1 now checks a README that comes with the source.

## Phase 6 — the sleep-perturbation event library (2026-10-08; plan Amendment 10 + two addenda, all before results)

`ephys/sleep_events.py`, run by `sleep_schedule.py phase6 --emg-root …`. Library
`D:/Field2026_analysis_out/2026c/sleep_events_20261008_1721/` (README); report
`results/2026c/ephys_spikes/reports/ephys_spikes_sleep_events_2026c.md`.

**Definitions** (full text in the module docstring and the report):
- **Movement events.** A sleeping rat's 50-Hz VeDBA onset (θ = median + 8 MAD of NREM), after 2 s without any onset in
  its house. Followers are housemates' asleep onsets within 0.1 s (tight) or 0.1–1 s (loose).
- **Chance.** The same follower test at −47 / −31 / +31 / +47 s.
- **Outcomes per participant.** State at +10 / 30 / 60 s, the first change within 30 s, woke within 60 s
  (`scenario` = woke / not_woken), wake length (MA < 40 s), composition +1…+10 min.
- **Controls.** Random co-sleep seconds.
- **Other sources.** Sound candidates (house-mic jump ≥ 20 dB; unvalidated). Battery-round handling (94, pre / post).
- **LFP-EMG.** Δcorr = [−0.1, +0.5] s minus [−2, −1] s. A burst is Δcorr above the 95th percentile of 200 random asleep
  times of the same session. Controls: matched head-acceleration terciles and mean-trace timing.

**Results** (claims #29a–e):
- **Most movements leave the mover asleep.** In NREM, 71 % stay asleep for 60 s (control 80.5 %, 6 / 6 rats); the wakes
  are mostly MA.
- **Group movements are real.** Tight group movements run at ×6.7–9.3 chance, ≈ 5–15 above-chance events per co-sleep
  hour.
- **Tight followers show their own muscle activity** (Candidate): Δcorr 0.018 / 0.033 vs ≈ 0 in non-movers, 12 / 12.
  It rises together with or just before their head acceleration, and reaches ~45–90 % of the first mover's at matched
  size.
- **Partners that stay still barely wake more** (20.3 % vs 19.5 %). The extra waking lies in partners that move too,
  which refines #28c.

**Verification:**
- Two smoke runs: the code path, and the EMG path on partial data.
- The final run, commit ccc979c.
- The agent judged no figure or sound.

## Logic audit of Phases 0–6, and the claim-audit corrections (2026-10-08, the user's request)

**What was done.**
- The main session drafted a logic chain over all phases.
- A Fable 5.1 subagent audited it read-only against the reports, the code and the saved tables, with the user's
  instruction "don't be too conservative". The user added two questions during the run: day vs night sleep, and a
  model of the implicit scheduler.
- The scope rule (the "sleep behaviour explore"): the sequence + IMU + WISER + temperature + handling, no LFP features.
- Record: [docs/methods/sleep_logic_audit_2026-10-08.md](../docs/methods/sleep_logic_audit_2026-10-08.md) — the main
  session's checks in the header, then the full report.
- Scripts: `D:/Field2026_analysis_out/2026c/sleep_logic_audit_20261008/`.

**Main-session checks:**
- **#13 confirmed as a drift** (`check_drift.py`, pass2med, per-animal-day tables).
  - Night → day NREM slope −0.56 within rat; with a linear day term −0.06 (n.s.); with day fixed effects −0.12 (n.s.).
  - Night NREM −0.95, day +0.77 min per recorded h per day; 6/6 rats each way, both scorings.
- **Fable's proposed new Established claim "NREM rebound ∝ wake length" was NOT adopted.**
  - With night in the Phase-3 Q2 regression, ln d is +0.47 / +0.90 (n.s.); dark +9.5 / +8.0 min (p < 0.001).
  - Kept as #31, Candidate, descriptive.

**Claim-audit changes:**
- #6 split into #6a (not resumed; Candidate strong, to Established after step A1 of the new plan) and #6b (graded, night
  only).
- #10 re-worded: REM-specific, morning only, not "via more bouts".
- #13 withdrawn as a balance; #24 superseded by #30 (the drift, Established descriptive).
- #14b added (the night gain at matched prior wake; Candidate).
- Scorer-gate caveat on #28b / #29a.
- #4 / #16 / #29c moved to the LFP stage.
- Wording notes on #5, #7, #9.
- Synthesis rewritten.

**Not re-checked by the main session** (Fable's own checks on our data; the new plan's step A reproduces them in repo
code first):
- the censored Cox for #6;
- the dark-only grading;
- the matched night gain;
- the day-demeaned morning payback.

**Next stage:** [implementation_plan/2026-10-08-sleep-behaviour-explore.md](../implementation_plan/2026-10-08-sleep-behaviour-explore.md).

## Sleep-behaviour explore, Steps A and B (2026-10-08 → 10-09; plan [2026-10-08-sleep-behaviour-explore.md](../implementation_plan/2026-10-08-sleep-behaviour-explore.md))

**Step A, the reproduction gate** — `ephys/sleep_explore.py stepA`.
- Written and run by an Opus subagent, reviewed by the main session (selftest rerun).
- Report: [ephys_spikes_sleep_explore_A_2026c.md](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_A_2026c.md).
- Verdicts against the pre-registered rules:

| part | claim | verdict |
|---|---|---|
| A1 | #6a | **PASS** → Established. |
| A2 | #6b | PASS by the letter; the pass2med Cox does not confirm it. |
| A3 | #14b | PARTIAL: night ratio 0.41 / 0.52 after 2–7-min wakes, 6/6 rats; the 7–30-min bin has too few night episodes. |
| A4 | #10 | PASS on fixed thresholds, with the new phase × day baselines; FINAL n.s. |
| A5 | movement → waking | PASS: 63 % of the mover excess survives excluding wakes < 15 s after the onset; 90 % under the ungated scoring. |

- Deviations are listed in the report: 4 ungated pilot sessions (not 7); a simulated resumption benchmark; block-clustered
  Cox SEs computed in the module.

**Step B, the minimal scheduler model** — `ephys/sleep_model.py stepB`.
- The model: one counter P = NREM since the last REM, emptied at REM by exp(−r/κ), discounted over a wake by
  exp(−d/τ_w), read out by a spline in a multinomial hazard per 10-s NREM step. It is compared with M2t, a hard reset,
  a pause, every-wake erasure and gate-only.
- Validation: nested forward chaining over day-half blocks.
- Selftest: synthetic data generated with τ_w = 2 min → the profile picks 2 min.
- Results (claims #32–#36):
  - **The counter beats M2t:** −1.07 % FINAL, −0.51 % pass2med, 6/6.
  - **REM empties it fully.**
  - **τ_w ≈ 5–10 min,** interior and leave-one-animal-out stable.
  - **Pre-registered "beats reset and pause": FAIL on FINAL;** pause rejected on pass2med.
  - **Post-hoc split** (`ephys/sleep_model_diag.py`):
    - after wakes ≥ 7 min, reset ≫ pause (6/6, both scorings);
    - after 2–7-min wakes, the discount wins on FINAL only.
  - **No dark step** is needed beyond the smooth clock.
  - **Wall-clock time since REM adds** (−0.36 %, 6/6).
  - **Fragmentation is absorbed** (#17 superseded).

**Runtime.** Step B took ~3.5 h on 6 workers. The PC was shared: another session's local SWR run used ~100 GB, so the
first 14-worker attempt died with a MemoryError and was rerun.
