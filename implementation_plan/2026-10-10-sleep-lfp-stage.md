# Sleep LFP stage: NREM depth and the count, the opening field NREM, theta before the first REM (cohort 2026c)

**Date:** 2026-10-10. **Status:** written before any of its results. The user: "行干吧", after the Fable plateau audit
([docs/methods/sleep_plateau_audit_2026-10-10.md](../docs/methods/sleep_plateau_audit_2026-10-10.md)) recommended GO.
Part W of the behaviour stage (§14 of [2026-10-08-sleep-behaviour-explore.md](2026-10-08-sleep-behaviour-explore.md))
ran 10-10: the long-wake memory term adds no held-out gain (#64) and leaves pass2med's evening delay → **L2(a) runs**.

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

- **Depth site** (per animal × probe block, proposed before any outcome is computed, confirmed by the user):
  - a site on a shank other than the shanks of the fixed `sw_channel` and of every session's own SW pick in the block,
    not a bad channel;
  - among those, the site with the largest NREM-vs-REM separation of the metric below in the block's reference session
    (`swr_channels_2026c.yaml reference_session`), z over the session's scored NREM and REM seconds.
  - Report the scorer-shank value as a sensitivity only.
- **Depth metric** $d_t$ (per second): the scorer's slow-wave axis computed on the depth site — the negative broadband
  (IRASA) slope 4–90 Hz, using the pipeline's own function. Sensitivity: 1–4 Hz relative power.
  - $z$ within animal × probe block over NREM seconds (unstable windows excluded); per-night $z$ as a sensitivity.
  - Sign: larger = deeper.
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

- **(c) The opening field NREM — required, first** (cheap; claim #62's scorer-validity risk).
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
- **(b) Theta before the first REM** — coordinated with the short-REM-bouts plan
  ([2026-10-09-short-rem-bouts.md](2026-10-09-short-rem-bouts.md)); its measures are reused, not duplicated.
  - In the 10 min before the first REM after evening rounds vs matched natural evening first REMs: the share of NREM
    seconds with REM-like theta / delta on a non-scorer theta site.
  - Pass: Δ CI excludes 0 on both scorings, ≥ n − 1 of n animals.
  - If it holds, #60 is at least partly a scoring lag of early theta (pass2med's fixed thresholds), not a delay.

## 6. Order, gates, outputs

1. **Site proposal** (per animal × block, by the rule of §3) → the user confirms the depth and theta sites. Nothing else
   runs before.
2. **L2(c).**
3. **L1.**
4. **L2(a)** and **L2(b).**

In parallel, outside this stage: the generative long-wake model of the behaviour stage (its own plan, time-boxed).

**Code and outputs:**
- Driver `ephys/sleep_lfp.py` (new; `--selftest` on synthetic signals). Reads LFP from storage, read-only; all
  development local.
- Per-second depth / theta cache in `$OUT_ROOT/2026c/sleep_lfp_features/<SFxx>/<session>.npz`, written once and reused.
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
