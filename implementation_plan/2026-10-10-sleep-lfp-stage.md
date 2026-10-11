# Sleep LFP stage: NREM depth and the count, the opening field NREM, theta before the first REM (cohort 2026c)

**Date:** 2026-10-10. **Status:** written before any of its results. The user: "行干吧", after the Fable plateau audit
([docs/methods/sleep_plateau_audit_2026-10-10.md](../docs/methods/sleep_plateau_audit_2026-10-10.md)) recommended GO.
Part W of the behaviour stage (§14 of [2026-10-08-sleep-behaviour-explore.md](2026-10-08-sleep-behaviour-explore.md))
ran 10-10: the long-wake memory term adds no held-out gain (#64) and leaves pass2med's evening delay → **L2(a) runs**.

**L1 DONE 2026-10-10:** [L1 report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_lfp_L1_2026c.md) — claims #65–#68 (P is not a depth proxy; depth adds nothing beyond P on FINAL; the night gate is not depth; NREM shallower as the count rises). **L1b DONE 2026-10-10** ([report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_lfp_L1b_2026c.md)): naps
and main sleep follow the same count / depth rules (#69); #68 downgraded by the selection check. **L2(b) DONE 2026-10-10**
([report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_lfp_L2b_2026c.md)): the pre-registered share sat at its
floor (uninformative); the NREM before the first post-round REM is theta-richer across the window, partly with head
movement, not a late REM label (#70, Candidate; **paused by the user**, confounds in §10.1). Next: the REM ramp
check (§10), then a targeted L2(a); L2(c) on hold.

**Revision 1 (2026-10-10, before any result; the user):**
- "sw slope 就可以 … delta 不过是 up-down state": depth is the scorer's raw slow-wave slope, already computed. No new
  depth site and no delta-wave density.
- Reuse the existing products of the SWR, theta and delta sessions (no new feature code).
- L2(c), the opening field NREM, is on hold until the manual video labels.
- The site-proposal step is dropped.
- The sleep scores are not recomputed. FINAL and pass2med states are used as they are. The lag and the 1-h control
  only keep the predictor and the scored outcome apart (the depth metric is the scorer's own slow-wave axis).

**Builds on:**
- the behaviour-stage claims #32–#63 in the
  [claim audit](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_schedule_claim_audit_2026c.md), frozen as the
  baseline this stage is scored against;
- the logic map `research_logic/graphs/sleep_2026c.yaml` (to be updated with the behaviour rounds before L1 runs);
- the views collected 2026-10-10: Codex "astra" (depth as an outcome now; the P / depth / P + depth comparison decides),
  the SWRdetection session (the depth metric is the scorer's own axis — use a non-scorer site with a lag), the Fable
  audit.

## 1. Why now

- The behaviour stage has plateaued. Since part F1, four amendments (P, T, L, H) produced one parametric re-description
  (#56), one scoped negative (#58), two corrections and two descriptions (#62, #63).
- Every residual left needs LFP or video:
  - #62: is the opening field NREM sleep or awake immobility?
  - #60: the evening first-REM delay;
  - #4 (parked): is the count P a behavioural proxy for cortical depth?
- Video waits for YOLO and identity tracking.

## 2. Data and regime rules (regime-aware-ephys, sources checked 2026-10-10)

Sources checked: the skill snapshot (2026-09-28); Recording `62eb9a6` and field2026-sync `0af194e` (pulled 2026-10-10,
up to date); `ephys/configs/sleep_channels_2026c.yaml`, `swr_channels_2026c.yaml`, `probes_2026c.yaml`.

**Inputs:**
- LFP: storage `Q:\hc997\SocialFieldRat2026\3rd_rat\analysis\lfp\<SFxx>\<session>.lfp` (1250 Hz, 64 ch; FM64
  de-glitched), read-only.
- States: FINAL (`states_1s_final`) and pass2med (`states_1s_pass2med`).
- Scorer channels: the fixed `sw_channel` / `th_channel` (imu_fixch), and each session's own automatic picks (FINAL is
  per-session; read them from the scorer outputs).

**Usable windows:**
- All animals:
  - never night 1 (08-30 ~18:39 → 08-31 ~04:30), the FM62 day (08-31), the ADC-lane pieces (09-10, quarantined) or
    sessions < 1 min;
  - inference cut 09-11 19:40 (females); paddock end 09-12 10:10;
  - the FINAL exclusions (`noise`, `SF12_contact_failing`, `valid_until`, refused, < 0.5 h).
- SF07–SF10: the whole run.
- SF11: to 09-07 06:10 (implant detached). Cortex, not CA1, after 09-02 19:08 (ripples lost).
- SF12: to 09-10 14:53:45 (contact failing; shanks 1 / 4 degraded from ~14:00).

**Probe advances are hard block boundaries,** and the ~4 h after each post-move session start is unstable: excluded from
the depth normalisation and from fitting.

| animal | post-move session start | unstable until |
|---|---|---|
| SF07 | 09-04 14:00:54 | ~18:00 |
| SF07 | 09-05 13:31:19 | ~17:30 |
| SF07 | 09-06 13:29:42 | ~17:30 |
| SF11 | 09-04 13:56:50 | ~18:00 |
| SF11 | 09-05 15:11:34 | ~19:00 |
| SF11 | 09-06 13:33:38 | ~17:30 |
| SF08 | 09-09 18:50:36 | ~22:30 |
| SF12 | 09-09 18:47:51 | ~22:30 |
| SF12 | 09-10 08:35:07 | ~12:30 |

**Sites:**
- Channel maps: SF07 verified; SF08 / SF10 / SF12 LFP-derived; SF09 reconstructed (5 × 12); SF11 grouping only.
  Features are per-site spectral measures, never anatomical depth claims (except SF07).
- SF07 sits above the CA1 layer (no radiatum site). SF11 is cortex after 09-02.
- Bad channels: the session index `bad_channel_candidates` plus the field record (e.g. SF09 2 4 32 36 54 56 58 62).

## 3. Definitions fixed now

- **Depth** $d_t$ (per second): the raw slow-wave slope `sw` of the fixed-channel rescore `imu_fixch`
  (`Q:/…/3rd_rat/analysis/sleep/imu_fixch/<SFxx>/<s>/<s>.SleepScoreRaw.npz`, on its `t_clus` seconds). It is the
  scorer's negative broadband (IRASA) slope on the per-animal `sw_channel` of `ephys/configs/sleep_channels_2026c.yaml`.
  Larger = deeper.
  - Sessions: the SWR quality guide (`results/2026c/ephys_spikes/reports/ephys_spikes_swr_quality_2026c.csv`), every
    tier except `exclude`. Its `block_from` gives the probe block.
  - Masked: before / after `use_until`, the probe-advance settle windows (`cohorts/2026c.yaml probe_moves`,
    `swr_temperature.settle_windows`), and non-NREM seconds.
  - Read with the SWR session's logic (`ephys/rem_ripple_model.py`: `record_arrays`, `block_tables`, `depth_z`).
  - $z$ within animal × probe block over its NREM seconds.
  - Circularity:
    - pass2med derives from `imu_fixch`, so for pass2med the predictor is the scorer's own axis;
    - FINAL uses per-session channel picks, so it is partly independent;
    - hence the lags and the 1-h control below. A non-scorer site (e.g. the delta-wave channel) is a later sensitivity,
      not a precondition.
- **Past depth** at a 10-s NREM step starting at $t$: the mean $z$ over the NREM seconds in $[t-150, t-30)$ s; missing
  if < 60 NREM seconds there. Lag sensitivity: $[t-180, t-60)$ s.
  - Negative control: the same feature taken 1 h earlier in the record.
- **Future depth** (outcome): the mean $z$ over the NREM seconds in $[t+30, t+150)$ s (≥ 60 NREM s). Not whole-bout
  averages (astra: bout length and termination create associations).
- All comparisons on identical forward-chained held-out steps (`sleep_model.folds_of`, folds 1..). Steps with a missing
  feature leave every model of that comparison. Both scorings. Animal rule: ≥ n − 1 of n with data.

## 4. L1 — depth and the count (the decisive step)

**Models** (multinomial stay / REM / WAKE, B-full base):
- **P-only:** B-full.
- **D-only:** P replaced by a spline of past depth.
- **P + D.**
- **P + D + D × dark.**

Each is evaluated on all transitions and separately on the REM and the WAKE outcomes (the per-outcome binary log-loss
contributions), as astra asked.

**Pass rules (both scorings):**
- (a) "depth adds": P + D vs P — Δ log-loss CI < 0, ≥ n − 1 of n animals, and the 1-h-shifted control ≈ 0 (CI covers 0).
- (b) "P is a proxy": P + D vs D not significant, AND D-only ≤ P-only.
- (c) "two processes": (a) holds AND P + D vs D is significant.
- (d) "night via depth": the dark coefficient falls AND D × dark gives held-out gain. A smaller dark coefficient alone is
  reported as reallocation, not as an explanation of #14b.
- (e) "depth reads the same homeostat": future depth ~ P + clock + prior wake (within block) beats future depth ~ clock
  + prior wake, held out, sign ≥ n − 1 of n.

**Confounds handled:**
- Clock vs time since sleep onset (onset ≈ 06:00 daily). Report naps and post-round onsets, where the two decouple,
  separately.
- Night depth is higher (−1.31 SD by day).

## 5. L2 — the residuals

- **(c) The opening field NREM — ON HOLD (the user, 2026-10-10) until the manual video labels;** then as written:
  - For each opening NREM bout (part H's list; the first 10 s after the logger start dropped), on the depth site and on
    a theta site that is not the scorer's:
    - the depth metric;
    - theta / delta;
    - 10–16 Hz power (cortical sites only: SF11 before 09-07; elsewhere reported, not used).
  - Compared with the same animal's house NREM (length-matched, within ±3 h, outside the 3 h after rounds) and with
    quiet wake (scored WAKE, IMU still, in a house).
  - An episode is "NREM-like" if its depth is within 0.5 SD of the matched house NREM AND its theta / delta is below
    the quiet-wake median.
  - Reading: ≥ 70 % NREM-like → the opening bouts are sleep. Otherwise → "awake immobility scored as NREM": a
    scorer-validity ledger item for #44, #56 and #63, whose first-hour numbers are then recomputed without the opening
    bouts as a sensitivity.
- **(a) #60 — runs (part W did not absorb it, #64).**
  - Does pre-transition past depth improve held-out prediction of the evening post-round steps (after the first NREM in
    the house, before the first REM), beyond B-full (+ the part-W term if it held)?
  - Pass: Δ log-loss CI < 0 on those steps on both scorings, and the evening REM-entry O/E moves toward 1.
  - No generative use without a generated depth (astra).
- **(b) Theta before the first REM** — reuses the theta session's per-second cache
  (`D:/Field2026_analysis_out/2026c/theta_seconds/<SFxx>/<s>.theta_seconds.csv.gz`: `log_td`, `f_peak`, `peak_frac`;
  site = the CA1 pyramidal-layer column, not the scorer's channel except SF10 in 19 sessions, which are flagged) and the
  short-REM-bouts feature code ([2026-10-09-short-rem-bouts.md](2026-10-09-short-rem-bouts.md); cortical `sigma_ctx`
  separates spindles).
  - The last 2 s before a scored REM onset are dropped (the cache's 2-s window).
  - REM-like theta = `log_td` above the session's NREM–REM midpoint AND `f_peak` < 10 Hz. Without the frequency test,
    spindles (≥ 10 Hz) would pass.
  - In the 10 min before the first REM after evening rounds vs matched natural evening first REMs: the share of NREM
    seconds with REM-like theta / delta on a non-scorer theta site.
  - Pass: Δ CI excludes 0 on both scorings, ≥ n − 1 of n animals.
  - If it holds, #60 is at least partly a scoring lag of early theta (pass2med's fixed thresholds), not a delay.

## 6. Order, gates, outputs

1. **L1** (now).
2. **L2(a)**, which uses L1's depth feature, and **L2(b).**
3. **L2(c)** after the manual video labels.

In parallel, outside this stage: the generative long-wake model of the behaviour stage (its own plan, time-boxed).

**Code and outputs:**
- Driver `ephys/sleep_lfp.py` (new; `--selftest` on synthetic data). It reads the existing per-second products, from
  storage read-only; all development local.
- The depth per second is cached once in `$OUT_ROOT/2026c/sleep_lfp_inputs/sw_imu_fixch.pkl`.
- Reports `results/2026c/ephys_spikes/reports/ephys_spikes_sleep_lfp_{L1,L2a,L2b,L2c}_2026c.md`.
- A new "LFP stage" section in the claim audit.

## 7. Do not do

- Depth on the scorer's channel or shank, without the lag sensitivity, or z-scored across a probe move or inside an
  unstable window.
- A REM-repayment or REM-need rule (#43); part Q stays closed.
- Read a smaller dark coefficient at matched depth as "the night effect is depth" without held-out gain.
- Pool SF11 after 09-07 06:10 or SF12 after 09-10 14:53:45; use SF11 ripples after 09-02.
- Call the opening field NREM "sleep" or "freezing" before L2(c), and the user's review where available.
- Gate this stage on the generative long-wake model.

## 8. Revision 2 (2026-10-10, before these results; the user: "做交互项我想看看结果") — L1b: naps vs main sleep, and a selection check of rule (e)

**Labels** (FINAL only; from the SWR session's `ephys/night_sleep_wiser.py`):
- nap = a step inside a night nap $[\text{start}, \text{end})$ of `results/2026c/ephys_spikes/reports/ephys_spikes_night_naps_2026c.csv`
  (235 naps; the 115 `strict` naps as a sensitivity);
- main = a step whose second has `tau_h` defined in `night_sleep_wiser_20261009_1051/seconds_<SF>.csv.gz` (from the
  main-sleep onset to the next long wake);
- other steps are left out.

**Outcome: REM entry only** (binary REM log-loss). The labels look into the future: every nap is followed by a long wake
by construction, so the WAKE exit differs by construction (SWR session).

**Models** on the labelled steps with a past depth (forward chaining, folds 1..):
- M0 = B-full + dep + nap.
- M0 + nap × ln(1 + P).
- M0 + nap × dep.
- M0 + both.

Δ REM log-loss %, fold-bootstrap CI, animals better. Also reported: B-full + dep vs M0 (the nap main effect), the
full-data REM-vs-stay coefficients of the interactions, and the REM entries per label and animal.

**Reading:**
- "P (or depth) predicts REM entry differently in naps and in the main sleep" = Δ CI < 0 and ≥ n − 1 of the n animals
  with nap REM entries.
- Naps are all dark, so a difference reads "label or light", never "label".
- Otherwise "no difference detected": about 100 nap REM entries, low power.

**Rule (e) selection check** (astra):
- Repeat (e) on the steps whose $[t, t+150)$ s is entirely NREM, so the composition of the future window is fixed. Both
  scorings.
- Report the future-window NREM coverage of the main (e) set.

## 9. Revision 3 (2026-10-10, before these results; the user: "做吧 L2(b)") — L2(b) defined

**Question:** is #60 (after evening rounds the first REM needs more NREM than predicted; strong on pass2med) partly a
labelling lag? I.e. does REM-like theta already appear in NREM-scored seconds before the first REM?

**Events** (each scoring):
- **R-evening:** evening round records with a house entry (part H's `house_entries.csv`).
  - t_N' = the first NREM bout start ≥ t_H.
  - t_R = the first REM bout start ≥ t_N', with no WAKE bout ≥ 30 min in between.
- **N-evening:** natural WAKE bouts ≥ 30 min inside records, ending 17:00–23:00 (field-PC time) and not within 3 h of a
  round record start.
  - t_N = the first NREM bout start after the wake.
  - t_R = the first REM bout start ≥ t_N, with no WAKE bout ≥ 30 min in between.
- **N-any:** the same at any clock time (context).

**Window:** the NREM-scored seconds in $[\max(t_R - 600, t_N), t_R - 2)$ s. The last 2 s are dropped (2-s centred
windows). At least 60 such seconds are required.

**Measures per event:**
- **th:** the scorer's theta / delta axis (`imu_fixch` `SleepScoreRaw.npz` `th`).
  - z within animal × probe block over the block's NREM seconds.
  - REM-like = th ≥ the block's 25th percentile of REM-second th.
  - Coverage, blocks and masks as L1.
- **CA1:** the theta session's cache (`theta_seconds`, `log_td`, `theta_on`, `f_peak`).
  - REM-like theta = `theta_on` AND `f_peak` < 10 Hz (not spindles).
  - SF10 sessions whose CA1 site is the scorer's theta channel are flagged.
- **Per-event values:** mean z-th, REM-like share (th), REM-like share (CA1), mean `log_td`.
- **Trajectory:** mean z-th per 60-s bin before t_R (description).

**Comparison:**
- R-evening − N-evening per measure.
- Pooled difference: mean of the per-animal differences, 95 % CI by bootstrap over events within animals (2000).
- The animals with both kinds counted by sign.

**Pass ("a labelling lag of early theta"):**
- R-evening has a higher REM-like share (th) than N-evening, with CI > 0 on both scorings.
- At least n − 1 of the n animals with both kinds go the same way.
- The CA1 share agrees in sign (reported).

**Reading:**
- Holds → #60 is at least partly REM-like theta in NREM-scored seconds before the first REM.
- Not → #60 is not explained by early theta scored as NREM.

**Next, for the user (astra):** a blind review page of the same transitions: LFP ± 60 s around t_R with the states
hidden.

## 10. Revision 4 (2026-10-10, before these results; the user: "写吧计划然后写检验") — L2(b) paused; the REM ramp within sleep episodes

### 10.1 L2(b) paused (the user: too many confounds)

#70 stays Candidate, marked paused. To resolve before any further theta reading:
- **Clock:** the first REM falls at median 18 h after evening rounds vs 22 h after natural evening wakes.
- **Prior wake:** release + handling + time in the field vs a natural wake ≥ 30 min; the windows start at different
  events (house entry vs the end of a natural wake).
- **Movement:** about half of the CA1 excess sits in head-moving seconds; it needs an IMU-matched (or video-labelled)
  comparison.
- **Scorer axis:** th is the scorer's own axis; on pass2med it is the axis that decides REM.
- **Numbers:** 1–3 natural evening events per animal.

### 10.2 Question

Does REM entry follow a time course within a sleep episode (rising after onset, falling before the end) that the
existing model does not produce? Naps hold less REM. Two readings:
- **Short episodes:** naps follow the same rules but end before the REM-rich phase.
- **Episode organisation:** at the same elapsed time, count, clock and wake history, REM entry still changes with the
  time since the episode began.

The count P empties at every REM, so it does not say how far an episode has progressed. Similar local rules (#69) do not
exclude a whole-episode time course.

### 10.3 Episodes (each scoring: FINAL, pass2med; the Step-B records)

- **Onset:** the first NREM second after
  - (i) a WAKE bout ≥ 30 min inside a record ("natural"), or
  - (ii) a record start ("record start": post-round when the record follows a round gap, else "other start").
- **End:** the next WAKE bout ≥ 30 min (an observed end), or censored at an unknown run > 60 s or the record end.
- **Elapsed time** $u$ = seconds since onset, on the wall clock (short wakes and REM included).
- **Classes:**
  - *main* = the last natural onset in [sunset, sunrise + 1 h) of a night;
  - *nap* = earlier natural onsets in [sunset, main onset);
  - *day* = all other natural onsets;
  - *post-round*;
  - *other start* (dropped).
  - Sunset / sunrise come from the night_sleep_wiser night table. On FINAL, main onsets are checked against its `mso`
    (agreement reported).
- **Bins of $u$ (min):** 0–10, 10–20, 20–30, 30–45, 45–60, 60–90, 90–120, 120–180, 180–240, 240–360, ≥ 360.
- **Per bin:** episodes at risk (uncensored at the bin start), NREM steps, observed REM entries $O$, expected $E$.
- Main sleep is usually cut by the morning round within ~0.5 h. The long daytime sleep therefore sits mostly in the
  post-round class, whose first hours carry the known extra waking (#61).

### 10.4 Tests

**(A) Held-out calibration (primary).**
- O/E of REM entry per 10-s NREM step, by bin and class, from the stored held-out B-full predictions
  (`sleep_heldout_steps`, `p_rem`; forward chaining). WAKE O/E is reported alongside.
- 95 % CI from 2000 bootstrap resamples of episodes within animals. O/E is also given per animal.
- Judged bins: $E \ge 20$.
- **Ramp residual in a class:**
  - ≥ 2 adjacent judged bins whose CI excludes 1 in the same direction, on both scorings;
  - per-animal O/E on that side in ≥ n − 1 of the n animals with $E \ge 5$ in the pooled bins.

**(B) Generative overlay.**
- The Step-E simulator (base model, conditional on the observed long wakes ≥ 7 min), 100 replicates per scoring.
- Measure: the REM share of sleep, REM s / (NREM + REM) s, per bin and class, on the observed episode bounds. The
  observed share is compared with the simulated 2.5–97.5 % band.
- **Shape not reproduced in a class:** ≥ 2 adjacent judged bins (≥ 20 episodes at risk) outside the band in the same
  direction, on both scorings.

**(C) Nested held-out test (decides whether a term is needed).**
- Add the episode clock as linear extras to B-full:
  $g(u) = \big(\ln(1+u_m),\ \max(0, \ln(1+u_m) - \ln 31),\ \max(0, \ln(1+u_m) - \ln 121)\big)$, where $u_m$ is $u$ in
  minutes (hinges at 30 and 120 min). Fitted with forward chaining.
- Primary subset: natural episodes (nap + main + day). Post-round is excluded because of #61's arousal. Secondary:
  with post-round included.
- **Holds:** REM log-loss CI < 0 and ≥ n − 1 animals better, on both scorings.

**(D) Description only.**
- End-aligned O/E: minutes before an observed episode-ending wake ≥ 30 min. Selection-prone.
- Sensitivity for (A): a wake threshold of 10 min.

### 10.5 Reading

| (A) / (B) | (C) | Reading |
|---|---|---|
| no residual, reproduced | does not hold | The REM time course within episodes, including the naps' low REM, comes out of the existing rules (count, clock, wake history): the short-episode reading. No episode clock. |
| residual or not reproduced | holds | An episode clock is needed: Candidate claim, then added to the simulator. |
| residual or not reproduced | does not hold | A residual without held-out value: described, not a model term. |
| no residual, reproduced | holds | A small gain: Candidate. |

### 10.6 Code and outputs

- Driver `ephys/sleep_ramp.py run` (`--selftest`: episode builder, censoring, classes, binning, O/E = 1 for a
  calibrated predictor).
- Report `results/2026c/ephys_spikes/reports/ephys_spikes_sleep_ramp_2026c.md` with CSVs and a figure: observed vs
  predicted hazard and REM share by $u$, per class, with episodes at risk.
- Bulk `$OUT_ROOT/2026c/sleep_ramp_<ts>/`.


### 10.7 Amendment 1 (2026-10-10, post hoc: after the first run, before the amended results)

The first run (pre-registered rule) is kept and reported. Its result: no ramp residual (A) in any class; (C) does not
hold; the nap REM-share shape is outside the simulator's band (B). Two problems found before reading it:
- **The pre-registered consistency check failed.** Main onsets matched night_sleep_wiser's MSO on only 10 of 45 nights.
  The plan meant to use night_sleep_wiser's naps / main sleep, but my rule needs one unbroken WAKE bout ≥ 30 min.
  night_sleep_wiser merges wake runs across sleep interruptions < 120 s and ends the night window at sunrise + 2 h.
  → `--episode-rule nsw` takes the long wakes from `night_sleep_wiser.long_wakes` and the window to sunrise + 2 h.
- **Nap vs main uses the future.** Whether an episode is a nap depends on whether a later long wake follows, and naps
  end in one by definition. Per-class WAKE O/E and end-proximal REM are therefore selection-affected.
  → Both rules add the pooled class **natural** (nap + main + day), which uses no future information. The rules of §10.4
  apply to it as to the other classes.

Reading: a claim needs both rules to agree; the nsw run is the one aligned with the repo's definitions. (C) needs no
change: the episode clock is causal and was already fitted on the pooled natural subset.
