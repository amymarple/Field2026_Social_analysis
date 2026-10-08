# Does sleep follow an internal schedule that survives interruptions? Memory, carry-over across wakes, and compensation in sleep history (cohort 2026c)

**Status: DONE 2026-10-08 (Phases 0–6; rev. 2 + Amendments 1–10; the logic audit and the next stage: §20).** History: approved 2026-10-07 ("go for it"). Phase 0 DONE
([report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_schedule_phase0_2026c.md)); **Phase 1 DONE**
([report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_schedule_phase1_2026c.md); technical ledger, no claim
audit yet); Phase 2 waits for the user. Audio levels: first run on storage (verified); the timestamp-fixed rerun pending.
- Nothing in §4 has been run on real data. The only numbers below are event counts (§3), not outcomes.
- Revision 2 (2026-10-07, before any outcome) applies the user's review of revision 1 (see §9) and adds the in-house
  microphones (§4 D).

**Builds on:**
- v1 and v2 of the REM-history analysis:
  - plan [2026-10-06-sleep-rem-cycle-history.md](2026-10-06-sleep-rem-cycle-history.md);
  - change logs [v1](../change_log/2026-10-06-sleep-rem-cycle-history.md) and
    [v2](../change_log/2026-10-07-sleep-rem-cycle-history-v2.md);
  - claim audit [v2](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_cycles_v2_claim_audit_2026c.md).
- The FINAL sleep scores ([change log](../change_log/2026-10-07-sleep-fixed-thresholds.md)).

**Literature:** [docs/methods/sleep_sequence_literature_audit_2026-10-07.md](../docs/methods/sleep_sequence_literature_audit_2026-10-07.md)
(the full audit, with the main session's checks at the top).

## 1. The question (agreed with the user, 2026-10-07)

**Hypothesis (the PI's, as reframed by the user).**
- The brain organises sleep by an **internal schedule**: an internal rule that organises sleep states, carries history,
  and is updated during wakes. It is not a fixed timetable.
- The schedule has to **survive interruptions**, and its reach may be **long** (hours, many cycles), so models of the
  adjacent state or the next cycle alone are not enough.

**Why the field data can test it.**
- Sleep here is interrupted all the time:
  - 82 % of REM-to-REM intervals contain some wake;
  - the median wake bout lasts 23 s;
  - 447 wakes last ≥ 10 min with sleep before and after.
- Yet the daily amounts are regular: NREM 9.7 ± 0.2 h and REM 1.8 ± 0.1 h per 24 h (N = 6).
- A system can be robust to interruption in two ways:
  - it stores where it is and resumes from there;
  - it keeps the organisation in slowly changing quantities, so a wake changes little.
- The two ways differ in **what happens after an interruption**. That is where the analysis looks.

**Round 1 delivers three curves:**
1. **Memory curve.** How far back does history still improve the prediction of the next sleep transition?
2. **Carry-over curve across wakes.** After a wake of a given length, how much does the history from before the wake
   still predict? How does that change with the length of the wake?
3. **Compensation curve.** When REM was below its expected amount, is it later above its expected amount?

The carry-over curve is closest to the core hypothesis. Compensation is closest to the functional meaning of
"scheduling".

**Wording rule, set now.**
- A result that holds held out, forward in time, and with the same sign in ≥ 5/6 animals may be reported as
  "**supports a sleep regulation that carries history across wakes**" (curve 2) or "**… that compensates REM**"
  (curve 3).
- Mechanistic wording ("the brain schedules", a circuit) stays out.
- The claim audit (`/scientific-report-promotion`) sets the final status.

**What these data cannot show:**
- the mechanism;
- that a given wake had no outside cause (the microphones, §4 D, narrow this later);
- that REM *must* happen, which needs an intervention.

The battery rounds come closest to an intervention: imposed by the operator, all rats at once, with handling.

**Wording fixed now:** v1/v2 were fitted within **continuously observed records**. A record contains wakes; it is not
"uninterrupted sleep".

## 2. What the literature gives us (summary of the audit, with our checks)

**Findings that replicate** (rats and mice, several labs):
1. **REM length predicts the NREM content of the following interval, not the preceding one** (Vivaldi 1994; Benington &
   Heller 1994; Park 2021).
2. **REM duration is a separate research object, not "unpredictable".**
   - The near-zero R² (Park 2021, R² ≈ 0.001) is for one relation only: the preceding NREM content → the next REM
     duration.
   - REM propensity *at REM onset* does predict REM bout duration:
     - "REMS propensity at REMS onset was positively correlated with REMS bout duration" (Akhavan et al. 2026, *Front
       Neurosci*, doi 10.3389/fnins.2026.1844209; checked, published version of the arXiv preprint in the audit);
     - Park 2021 relates the propensity to REMpost.
   - → When REM starts and how long it lasts are modelled separately (§4 C3).
3. **A refractory period after REM** (mice ≈ 2 × REMpre, verified in Park 2021; rats: the hazard dips to its lowest about
   2.5 min after REM, Bassi 2009).
4. **Sequential and single cycles** exist in rats, mice and humans.
   - The fraction depends on how brief wakes are counted: Park counts wakes ≤ 20 s inside NREM and finds 19.3 %
     (verified).
   - Our 48 % (no merging) is not comparable until the same convention is used.
5. **Stability is separable from amount and timing.** Orexin-knockout mice have normal amounts and timing but fragmented
   bouts (Mochizuki 2004). NREM fragility comes in ~30–50-s waves and depends on depth and on the time since REM.
   - Merging brief wakes into NREM is an *analysis convention* for counting cycles. It does not say that brief wakes
     leave the process unchanged; that is part of what curve 2 measures.
6. **Time of day is part of the model, not a control** (Kemp & Kamphuisen 1986; Pohle 2017).

**Unresolved in the literature, and directly our question:**
7. **What happens to REM "pressure" during a wake: conflicting.**
   - Neural marker (vlPAG, Weber 2018): it declines in NREM, not in wake.
   - Behaviour (Park 2021, checked by us): more wake within an inter-REM interval goes with more NREM before the next
     REM. That matches our v2: wake since the last REM lowers the REM odds.
   - Long-term: a REM debt after deprivation is repaid (Franken 2002; Ocampo-Garcés 2020), quickly only beyond ~22 % of
     the daily need (Amici 2008).
   - **Nobody has tested whether REM history survives spontaneous long wakes in undisturbed animals.**
8. **Homeostasis or carried-over transition probability?** A 2nd-order semi-Markov "momentum" model reproduces the
   REM → interval relation (Stephenson 2025, abstract only). Natural data can separate the views only partly, by which
   clock the memory runs on (NREM time vs wall-clock time vs neither).
9. **No rodent study has measured memory beyond two steps** (humans: 2nd-order, Yetton 2018).
10. **A budget has been shown only after deprivation**, never in undisturbed data.
    - Handling suppresses REM and NREM for 1–3 h (Cano 2008; Tang 2005; Febinger 2014).
    - → Across battery rounds, read slopes, not levels.

**Corrections from our checks** (details at the top of the literature file):
- Our scorer's 6-s rules turn REM attempts of ≤ 6 s inside NREM into NREM, not into wake.
- Park 2021's "wake does not matter" concerns REM duration, not REM timing.
- The audit's "own history survives the other animals → the memory is internal" is a leap; see §4 A4 for what that
  comparison can say.
- REM duration is not "unpredictable" (item 2).

**What this changes in our earlier reading of v2:** records start mostly right after a battery round. So `has_anchor`
("REM unlikely before a record's first REM") may be post-handling suppression, not only "no REM at the start of sleep".
Curve 2 across gaps (§4 B2) separates the two.

## 3. Data and definitions (fixed before any outcome is looked at)

**States.**
- The FINAL 1-s scores: `D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final/`, with the exclusions of the
  `regime-aware-ephys` skill (§ Sleep scores).
- **New exclusion:** everything from 2026-09-11 19:40 (the five females, population 5 → 10). It is kept for description
  only.
- The 1-s scores are never edited.

**Timeline.**
- One time axis per animal over all included sessions.
- Recorded time keeps its state. Unrecorded time is **unknown** and is never imputed.
- v2's records (sessions joined across splits ≤ 60 s) are the "within-record" unit.

**Wake events stay as observed.**
- Every wake bout keeps its true duration $d$. The main analyses use $d$ as a **continuous** variable, from the
  scorer's minimum (≥ 7 s; shorter wakes next to NREM are already NREM, see §2) to hours.

**Episode units.** Derived units, following Watson et al. 2016, *Neuron* 90:839 (`Ref/nihms776601.pdf`, the user's
reference, p. 3–4 and Fig. 1):
- **NREM packet:** uninterrupted NREM.
- **Microarousal (MA):** a wake < $m$ between two NREM periods. The paper uses $m = 40$ s: "shorter epochs (< 40 sec)
  … typically embedded between nonREM epochs".
- **NREM episode:** "a stream of nonREM packets and MAs without REM".
- **SLEEP:** "alternating nonREM and REM episodes, lasting a minimum of 20 minutes and terminated by prolonged
  (> 120 sec) WAKE".
- **WAKE–SLEEP cycle:** a WAKE ≥ 7 min followed by a SLEEP ≥ 20 min. The 7-min cutoff "yield[s] WAKE epochs highly
  correlated with ambulation".

Where they are used:
- the cycle counts and the cycles-ahead regression (A3);
- the comparison with Park 2021 ($m = 20$ s);
- reference marks on the wake-length axis of curve 2: 40 s, 120 s, 7 min.

$m$ values:
- **Primary $m = 40$ s** (the paper).
- $m = 100$ s is reported for the cycle numbers only. It is our pipeline's own episode code
  (`state_scoring._states_to_episodes`, the buzcode port; also packets ≥ 30 s, episodes ≥ 20 s), and it wrote each
  session's `SleepStateEpisodes.states.mat`.
- $m = 20$ s is used only next to Park's 19.3 %.

The 1-s scores are never edited.

**Interruptions** (counted on 2026-10-07; feasibility only):

| Kind | Definition | Count |
|---|---|---|
| Any wake inside a record, with sleep before and NREM after | all durations, used in curve 2 as a continuous $d$ | 11 199 wake bouts in total (median 23 s, 90th percentile 148 s, 99th 1.9 h) |
| Natural long wake | the same, ≥ 10 min | **447** (161 between 07:00 and 19:00, 286 outside; 50–90 per animal) |
| Natural very long wake | the same, ≥ 30 min | 236 (8 between 07:00 and 19:00 → wake length is confounded with phase) |
| Battery-round gap | gap between two records ≤ 180 min, with ≥ 1 h recorded on each side | **108** (51 morning, median 60 min; 50 evening, median 52 min; 7 other) |

**Battery-round gaps.**
- A gap is a **handled interruption whose state is unknown**. Per animal, record:
  - the last recorded second before the gap and the first after it;
  - the battery-swap time from the logger telemetry (5-min resolution; `BATTERY_LOG_cohort3.md`, table per cell);
  - any auto-stop before the round: unobserved and undisturbed;
  - WISER movement during the gap from the default tracks, **as description only**.
- Movement in part of a gap does not show that the animal was awake for the whole gap.
- Wording: "history carried across a handled interruption".
- **Gap causes (Phase 0, from the field record):**
  - 94 usable battery rounds (82 with a logged swap, 12 inferred on 08-31 / 09-01, where the cell table is partial);
  - 8 probe moves, which are handling plus an electrode change and are kept apart;
  - 2 with no handling recorded.
- **SF10 09-06 04:02 → 05:58 is the only undisturbed unobserved gap** (`recording-inquiry`, 2026-10-07).
  - The logger stopped by itself at 3.74 V, flat. That is far above the ~3.40 V auto-stop, and the cell had run only
    9.1 h of its 12–14 h, so the numbers argue against battery drain.
  - The operator suspected a loose battery contact. Never confirmed: no stop reason was read, the cell was never
    measured at rest, and the holder was never inspected.
  - The restart at 05:58:13 was BLE only: clock writes + Rec Start on the same cell, with no guard file and no swap.
  - SF10 was caught at the AM round, 07:00 → 08:04.
  - "Not handled" is inferred from how the restart was recorded; no source states it explicitly.
  - It serves as a single descriptive contrast (unobserved but undisturbed) next to the handled gaps.

**Clocks:**
- **wall time** since an event;
- **NREM time** = NREM seconds since the event;
- **cycle count** = REM onsets since the event.

**Model layers.** Each is the previous one plus new terms. The model is a per-10-s-step multinomial logit
stay / REM / Wake from NREM, as v2.
- **L0 (clock):**
  - animal;
  - $(\sin,\cos)(2\pi k h/24)$, $k = 1, 2$;
  - experiment day as a **linear** term (the REM decline is linear, −0.18 pp/day in 6/6 animals; a spline cannot be
    extrapolated one block forward);
  - a spline of $\ln(\text{elapsed}+5)$ in the current NREM bout.
- **L1 (current state):**
  - the length of the wake that preceded this NREM bout, $\ln d$;
  - the wake fraction in the last 10 min.
- **L2 (accumulated since the last REM).** These can reach back hours, so this is *not* a local layer:
  - a spline of $\ln(1+N_{\text{since}})$, the NREM time since the last REM;
  - $\ln(1+W_{\text{since}})$, the wake time since the last REM;
  - $\ln \text{REM}_{\text{pre}}$;
  - has-anchor.
- **L3 (distant windows).** For each lag band $b \in \{10\text{–}30, 30\text{–}90, 90\text{–}270, 270\text{–}720\}$ min
  before the bout start:
  - $f_{R,b}$ and $f_{W,b}$ = REM and wake seconds over recorded seconds in the band;
  - completeness $c_b$ = recorded seconds over band length.

  The bands are added one by one.
- **S (shared):** the other animals' REM fraction over recorded time in the last 3 h, with its completeness.

The order L1 → L2 → L3 separates three statements:
- a **local** rule (the current state);
- an **accumulated** internal quantity (since the last REM);
- **more distant** history.

If L3 adds nothing beyond L2, the result is not "no long memory". It is: **long history is summarised by one
accumulated quantity**, which is itself a finding.

**Validation.**
- **Primary: forward chaining over the 22 day-half blocks.** Train on all earlier blocks, predict the next. History
  features may use any *past* observed state, including earlier test blocks; no test outcome ever enters a fit.
- **Secondary: leave one block out with a purge.** Training rows whose history window (up to 12 h, also across gaps)
  overlaps the left-out block are dropped from that fold.
- Score: held-out log-loss per step. $\Delta$ = larger model minus smaller, as a % of the smaller; negative = better.
  95 % CI by bootstrap over blocks.
- **"Holds"** = CI below 0, and the same sign in ≥ 5/6 animals.

**Opportunity vs timing** (the split of every gain; Larson & Dinse 1985). Within an NREM bout with covariates $x$, let
$h_R(t)$ and $h_W(t)$ be the per-step hazards and $S(t)=\prod_{u\le t}(1-h_R(u)-h_W(u))$.
$$\pi(x)=\sum_t S(t-1)\,h_R(t),\qquad f(t\mid\text{REM},x)=\frac{S(t-1)\,h_R(t)}{\pi(x)}$$
- $\pi$ = **opportunity**: the probability that this NREM bout ends in REM rather than wake (range 0–1).
- $f$ = **timing**: when REM starts, given that it does.
- The log-score of a bout ending in REM at $t$ is exactly $\log\pi+\log f(t\mid\text{REM})$, so every gain splits into
  "whether" and "when".
- $\pi$ is a forward loop over the fitted model's steps; no second model is fitted. Censored bouts enter only the total.
- Timing sharpness is also reported as the interquartile width of $f$.

**Expected REM (for compensation).** The hazard model cannot give expected REM minutes, so a **separate baseline**
is used:
- a quasi-binomial GLM of the REM share of recorded time in 10-min bins, on animal + $(\sin,\cos)(2\pi k h/24)$ +
  linear experiment day;
- fitted on the training blocks only (forward chaining);
- expected REM minutes in a window = $\sum_{\text{bins}} \hat p \times$ recorded minutes;
- the same model for NREM.

## 4. Analyses

### A. Range — curve 1 (Phase 1)

- **A1 Memory curve.**
  - Held-out $\Delta$ for L0 → +L1 → +L2 → +L3 bands up to 30, 90, 270, 720 min.
  - Range = the longest band whose addition still holds.
  - Within records alone, the long bands are limited by the record length; they are extended across gaps in Phase 2
    (B2).
- **A2 Clock.**
  - The L2 terms on NREM time vs wall-clock time vs cycle count, and the L3 bands on wall vs NREM time.
  - The best held-out score wins; overlapping CIs = "undetermined".
- **A3 Cycles ahead.**
  - Model: $\ln|N|_k$ (NREM content of the $k$-th interval after a REM) regressed on $\ln\text{REM}_0$, with the
    intervening REM and NREM terms, phase and animal, for $k=1\ldots5$.
  - Units: complete cycles, merged convention.
- **A4 Own history beyond the shared component.**
  - Add S to the best model; report how much the animal's own L2/L3 history still adds.
  - **What it can say:** "the animal's own history carries information the other animals' concurrent sleep does not
    explain".
  - **What it cannot say:** whether a component is internal or external. Internal rhythms can synchronise animals, and a
    shared environment can affect animals differently.

### B. Carry-over across wakes — curve 2 (Phase 2)

- **B1 Carry-over curve across natural wakes** (all wakes, $d$ continuous).
  - Outcome: the NREM bouts after a wake.
  - Three nested models, held out:
    - **Reset:** current state + $\ln d$ + L0; no pre-wake history.
    - **Carry-over:** + the pre-wake accumulated history (L2 frozen at the wake's start, and the L3 bands before the
      wake).
    - **Update:** + the pre-wake history × a spline in $\ln d$, so its effect can change with the wake's length.
  - Steps:
    - **First establish carry-over** (carry-over vs reset).
    - Then the **carry-over curve** = the effect, and the held-out gain, of pre-wake history as a function of $d$.
    - Its shape says whether the history is kept, fades, or keeps building. These labels are read from the fitted
      curve, not assigned by a sign rule.
  - Wake length is confounded with phase (long wakes are at night): phase stays in, and the curve is reported for light
    and dark separately.
- **B2 Across battery-round gaps (108).**
  - The same three models, with the gap as the interruption; morning and evening separate.
  - Gap length (and the animal's own handling time) enter in place of $d$.
  - Also extends the A1 bands across gaps.
  - **Key sentence if carry-over holds:** "history from before the handled interruption still predicts after
    controlling for the post-resume state, so the post-resume local information does not explain later sleep".
- **B3 Threshold check:** B2 repeated on `pass2med_remclean`, whose thresholds are fixed per animal (the gap lies
  between separately scored sessions).

### C. Compensation and form — curve 3 (Phase 2)

- **C1 Compensation curve.** For a window $A$ (the past) and a later window $B$ (the future), with the baseline of §3:
  $$\text{debt}_A = E[\text{REM}_A]-\text{REM}_A,\qquad \text{payback}_B = \text{REM}_B - E[\text{REM}_B]\quad(\text{minutes})$$
  - Positive slope of payback on debt = the more REM was owed, the more is later made up.
  - $A$ and $B$ do not overlap. The expectation is fitted on training blocks only. Debt and payback never come from one
    fixed total, so regression to the mean is not built in.
  - Settings:
    - **within records:** consecutive windows $A$ = 3 h, $B$ = 1 h and 3 h;
    - **across battery-round gaps:** $A$ = the last 3 h before, $B$ = the first 1 h and 3 h after. Read the slope, not
      the level: handling suppresses REM.
  - The same for NREM. If NREM is also made up in parallel, the effect is general sleep catch-up, not REM-specific.
    This is part of the result, not a control.
- **C2 Refractoriness.** The fitted REM hazard as a function of NREM time since the last REM, and how it scales with
  REM_pre. No preset window.
- **C3 REM duration.**
  - A separate held-out model of $\ln$ REM bout duration on L0–L3 and on the estimated propensity at onset (Akhavan
    2026).
  - Does the history that sets *when* REM starts also set *how long* it lasts?
  - Does REM after a debt last longer? (Franken 2002: after deprivation, REM is entered more successfully.)
- **C4 Opportunity vs timing.** The §3 split for A1, B1 and B2.

### D. Environmental disturbance from the in-house microphones (written now; validated later; pilot if quick)

**Hardware** (recording repo `README_ultramic.md`, `change_log/2026-08-16-second-mic-prep-exact-device-match.md`).
- MIC01 = UltraMic384K, 384 kHz. MIC02 = UltraMic 250K, 250 kHz, from 08-16 16:29.
- Mono 16-bit, hourly WAVs on the field-PC clock: `<date>/MIC0x/MIC0x_<date>_<HH-MM-SS>_to_<HH-MM-SS>.wav` on Q: and on
  the local copy `F:\3rd_rat\`.
- Per the user, both were **inside the houses where the rats sleep**.

**Placement, as far as it is known (2026-10-07).**
- **The user (2026-10-07):** MIC01 and MIC02 sit **on the ceiling inside each house**, one mic per house. So movement
  and calls in a mic's own house should dominate it, and the other house and the outdoors reach it only through the
  walls.
- **The record.** No written source says which mic was in which house during cohort 3, or how either was mounted
  (checked by the `recording-inquiry` agent: the Notion pages, the recording repo, field2026-sync). The only placement
  note is from cohort 2, 08-16: "installed 2nd microphone in left house" (that is MIC02). In the cohort-1 layout file,
  "left" is the house_1 position.
- **First data check** (09-06, 10:00–11:00; WISER put all six animals in house_2):
  - MIC01's per-second level follows these animals' head-IMU movement: Spearman 0.60 at 20–100 kHz, 0.48 at
    0.5–4 kHz.
  - MIC02 does not (|ρ| ≤ 0.13), and its bands above 4 kHz are flat (SD ≤ 0.2 dB).
- **Working assignment:** **MIC01 = house_2, MIC02 = house_1**. It still has to be confirmed on hours with animals in
  house_1, and by the user.
- **Recording gaps** (field record): 09-01 04:19:56 → ~04:25 and 09-03 13:56 → ~13:59/14:01 (PC crashes). Both mics
  then ran continuously to 09-12 11:19:24; 10:10–11:19 that day is the empty arena. The 09-08 construction end is
  still open and is to be dated from these files.

**The problem.** A rise in sound around a wake can be an outside disturbance that woke the animal, or the noise the
animal (or a housemate) makes after waking: movement, scratching, vocalisation.

**Cues that separate the two** (each a candidate, validated later):
1. **Order in time.** Sound that starts before any animal in that house moves (head IMU, 1 s; sleep score) = candidate
   external. Sound that starts after the animal's own movement onset = candidate animal-made.
2. **Common across microphones.** The same rise on both house mics and on the outdoor camera audio (CH01/CH02 tracks) =
   candidate environmental (rain, machinery, aircraft, people). A rise on one house's mic only = local.
3. **Spectrum.**
   - Machinery < 500 Hz (the 09-08 construction and 09-09 mowing windows, with known times).
   - Rat ultrasonic calls 20–80 kHz = animal.
   - Rain broadband and sustained.
   - Handling at the battery rounds.
4. **Known events.** Construction 09-08 from ~07:50, mowing 09-09 09:41–14:00, the battery rounds, the females 09-11
   19:40.

**Outdoor reference: CH01 / CH02 camera audio.**
- The two mid-field panorama cameras record an audio track with the video. Their positions are in the 09-24
  calibration.
- Per-second band levels of these tracks (audible range only; the camera mics are not ultrasonic) are the outside
  reference for cue 2: a sound heard outdoors and in both houses at the same second is a candidate environmental
  event.
- Extracted from the MP4s on the field-PC clock (file names). Heavy I/O (the whole video file is read), so it runs on
  the BioHPC CPU if local reading is too slow.

**Steps:**
- **D1 Extractor.** Per-second band levels (dB re full scale) per mic, in five bands: 20–500 Hz, 0.5–4 kHz, 4–20 kHz,
  20–40 kHz, 40–100 kHz. Cut on the PC clock from the file names, with the sample count checked against 3600 s.
  - Tested locally on one hour from `F:\3rd_rat\`, then run on the BioHPC CPU over 08-30 → 09-12 (~1.4 TB; the user
    approved server CPU).
  - Output (small): `<OUT>/2026c/mic_band_levels/MIC0x/<date>.csv.gz` + README. Server output goes to the workdir, then
    to storage (`ephys/server/copy_to_storage.sh`).
- **D2 House assignment.** If not documented: the correlation of each mic's 0.5–20 kHz level with the IMU movement of
  the animals that WISER places in each house.
- **D3 Pilot (description only).** Mic levels around every NREM → wake transition of an animal in a house:
  - the median level in each band from −60 s to +60 s, on its own house's mic, the other house's mic and the outdoor
    track;
  - split by whether the rise starts before or after the animal's movement onset.
  - Output: a few figures and a table for the user.
  - **The user's listening and spectrogram check on sampled events is the validation.** The agent does not judge sounds
    or images.
- **Later use, after validation.** "External-candidate" events become covariates:
  - does an external sound wake the animal (state stability);
  - does history carry over differently after an externally caused wake (curve 2 split by cause);
  - stimuli that did *not* wake the animal are kept.

### E. Round 2 (not in round 1)

**Hidden-state model** (bout-level explicit-duration hidden semi-Markov model, phase on the transitions, $K$ by held-out
likelihood). Run only if A1 or B1 find history beyond L2.
- Reading: a finite set of hidden states does **not** mean a finite-memory observed sequence. So "the long-history model
  beats the HMM" (or the reverse) compares *summaries of the past*. It does not decide scheduling vs mode.

## 5. Controls: the complete list

1. **S** (other animals' REM) for A4.
2. **`pass2med_remclean`** for the gap tests (B3).
3. **Merge convention** $m$ = 10 / 60 s, for the cycle numbers (A3) only.

Nothing else is planned: no weather covariates (A4 and D cover shared conditions), and no rerun on the states before
the REM rules, unless a headline depends on REM entries the rules changed.

## 6. Outputs

- **New driver:** `ephys/sleep_schedule.py` (reuses `sleep_cycles_v2` / `sleep_cycles` functions), `--selftest` on
  synthetic sequences:
  - a planted reset / carry-over / update rule is recovered by B1;
  - a planted debt → payback slope is recovered by C1;
  - the opportunity / timing split adds up to the total.
- **Mic extractor:** `ephys/mic_band_levels.py` (`--selftest` on synthetic tones and noise), plus the server wrapper
  `ephys/server/run_mic_band_levels.sh`.
- **Bulk:** `$FIELD2026_ANALYSIS_OUT_ROOT/2026c/sleep_schedule_<ts>/`.
- **Report:** `results/2026c/ephys_spikes/reports/ephys_spikes_sleep_schedule_2026c.md` with a Definitions section,
  CSVs, and figures:
  - the three curves;
  - the clock comparison;
  - the opportunity / timing split.
- **Pointer:** `run_manifest_sleep_schedule_2026c.json`.
- **Afterwards:** a claim audit, a change log, the CLAUDE.md rows, and the plan index.

## 7. Order and gates

- **Phase 0 (no outcomes).** Timeline, wake table, gap table with per-animal gap evidence, baseline windows, counts →
  shown to the user. In parallel: the mic extraction (D1, D2).
- **Phase 1.** Curve 1 (A1–A4) + C2 + C4.
- **Phase 2.** Curve 2 (B1–B3) + curve 3 (C1) + C3 + the mic pilot D3.
- **Round 2.** E, and the mic covariates after the user's validation.
- The user sees each phase's result before the next one starts. Any definition change after Phase 0 is an amendment
  here, marked "after results" where it applies.

## 8. Decisions (the user, 2026-10-07: "go for it")

1. **Episode units: Watson et al. 2016** (the user's reference), MA < 40 s; 100 s (our pipeline's code) and 20 s
   (Park) only for the cycle numbers. See §3.
2. **Exclude everything from 09-11 19:40** (the females) from inference: yes.
3. **Forward chaining as the primary validation:** yes.
4. **The hidden-state model (E) only if** history beyond the accumulated quantity turns up: yes.
5. **Mic assignment:** the user does not know which is which. The user agrees with the working assignment (MIC02 flat →
   house_1; MIC01 → house_2, where the animals usually sleep together). D2 checks it per day.
6. **Outdoor reference:** add the CH01/CH02 camera audio (the cameras' positions are in the calibration); server CPU
   if needed. See §4 D.

## 9. Revision 2: what changed from revision 1 (the user's review, 2026-10-07, before any outcome)

1. **Compensation sign and expectation fixed.**
   - Debt = expected − observed, payback = observed − expected, both in minutes; positive slope = compensation.
   - The expected minutes come from a separate REM-share baseline fitted on training data (the hazard model cannot give
     them).
2. **REM duration kept as a research object** (C3). The audit's "unpredictable" overgeneralised one relation. Akhavan
   2026 is published and is cited in its published form.
3. **Layers split.** "Since the last REM" can span hours, so it is its own accumulated layer (L2), between the current
   state (L1) and the distant windows (L3). L3 adding nothing now means "summarised by an accumulated quantity", not
   "no long memory".
4. **Wake events kept as observed.** $d$ is continuous in the main analysis. Merging is a derived convention for cycle
   counts only. The claim "brief wakes are not interruptions" is removed: that is what curve 2 measures.
5. **Reset / carry-over / update by model comparison.**
   - Carry-over is established first, then its dependence on $d$.
   - The pause / reset / running sign rules are removed.
   - The WISER rule that upgraded a gap to "wake" is removed; a gap is a handled interruption of unknown state.
6. **The shared-component comparison states only what it can.** No internal / external verdict.
7. **Validation:**
   - forward chaining is primary; leave-one-block-out with a purge is secondary;
   - experiment time is linear;
   - the hidden-state model moves to round 2, with the finite-states ≠ finite-memory caveat.
8. **New:** the in-house microphones (§4 D), on the user's suggestion: written in now, validated later, pilot if quick.

## 10. Amendment 1 (2026-10-07, AFTER the Phase 1 results; the user's review relayed, "行做")

**Phase 1 reading, corrected.** The report numbers are unchanged.
- **Wording.** "Among the models tested, the current state and the quantities accumulated since the last REM capture
  the main predictive gain of history; the distant windows (10 min–12 h, within records) add nothing."
  - It does not mean the brain clears its memory at REM: "since the last REM" can itself span hours.
  - A regulator keeping a few accumulated quantities is compatible with the scheduling hypothesis. That is an
    interpretation to test, not a finding.
- **Opportunity vs timing must be read by how the bout ends.**
  - For bouts ending in REM, the accumulated layer adds about equally to "whether" (0.0156) and "when" (0.0132)
    nats/bout.
  - For bouts ending in wake, almost all of it is "when" (0.0185 of 0.0188).
  - The overall "mostly when" therefore comes from wake: it concerns the maintenance of, and exit from, NREM, not a
    REM timer.
  - "Whether" here means "this NREM bout ends in REM rather than wake", not "REM occurs in the next hours".
- **The refractory figure is mislabelled.**
  - N_since is fixed at the bout start, and the within-bout time is a separate term. The curve therefore compares
    bouts that start at different accumulated NREM; it does not trace recovery within one NREM stretch after REM. The
    30-s low point is not a refractory length.
  - The y axis is the 10-s hazard × 6, a rate scale, not a true per-minute probability.
  - "Unlike mice" is withdrawn: no detected REM_pre gain is not a species difference.
  - Phase 2 C2 replaces the figure (below); the code label is fixed.
- **Cycles ahead.** The test was: previous REM length → the NREM content k intervals later, with the intervening
  cycles controlled. Allowed: "no stable additional cross-cycle association". Not allowed: "delayed influence
  excluded". Effects carried through the intervening cycles are removed by the control.
- **The clock tie (NREM vs wall time) is expected in continuous sleep.** A wake separates the two clocks (wall time
  runs, NREM time stops), so Phase 2 B1 is the decisive comparison.

**Phase 2 additions and changes:**
- **B1, wake as the separator.** Analysed on NREM bouts that follow a wake, with the wake length d continuous.
  - Models:
    - reset = L0 + current conditions + ln d;
    - carry-over = + pre-wake accumulated history: NREM since the last REM (stops during wake), wake since the last
      REM before this wake, REM_pre, anchor;
    - update = + pre-wake history × ln d.
  - Clocks: NREM since REM (pre-wake) vs wall time since REM (includes d), on the same bouts.
  - Carry-over curve: the held-out gain per wake-length bin (< 40 s, 40–120 s, 2–7 min, 7–30 min, ≥ 30 min).
  - Natural wakes first; the battery gaps after.
- **B1b, new: the user's original question, does a long wake affect the next REMs?** For every wake ≥ 7 min followed
  by NREM in the record:
  - the NREM content before the 1st, 2nd and 3rd REM after it (Watson units), regressed on ln d and the pre-wake NREM
    since REM, with phase and animal;
  - only cycles that reach REM before another wake ≥ 7 min are used. The conditioning is reported.
- **B2, purge.** In the post-gap analysis, a left-out block's states are the history of the next block's post-gap
  bouts, so those rows are dropped from that fold's training. The post-gap set is small (bouts before the first REM
  after ~94 gaps), so it uses a lean model (linear pre-gap terms only).
- **C1, compensation decomposed.** REM minutes, REM count and mean REM bout duration, each against its own baseline
  (fitted leave-one-block-out on animal + phase + linear day): does catch-up come through more REM bouts or longer
  ones? NREM is reported alongside.
- **C2, replaced.** An empirical, model-free hazard per 10-s NREM step (REM and wake), against the TOTAL NREM since
  the last REM at that step (bout-start value + elapsed), per animal then averaged.
  - One held-out comparison: the step-level since-REM clock vs the bout-start clock.

## 11. Amendment 2 (2026-10-07, AFTER the Phase 2 results)

**C1 is reported on both scorings,** FINAL and `pass2med_remclean` (fixed per-animal thresholds).
- Why: under FINAL, the within-record REM slope was negative (a shortfall persisted: −0.11 per min at 1 h, −0.28 at
  3 h, 5/6 rats negative). Under fixed thresholds it was zero (+0.003, +0.001).
- A per-session threshold error lasts a whole session, so it produces exactly this persistence.
- The persistence reading is withdrawn as a likely scoring artefact.
- The across-gap comparison is not affected this way: windows A and B lie in different sessions, and independent
  session errors cannot produce a positive slope.
- No other part changed. The rerun reproduces the other Phase 2 numbers, as the fits are deterministic.

## 12. Amendment 3 (2026-10-07, AFTER the Phase 2 results; the user's follow-up questions) — Phase 2b

Driver `ephys/sleep_schedule.py phase2b` → `ephys/sleep_schedule_phase2b.py`; definitions are in its docstring.

- **E1, effect size on an interpretable scale** (the user: "are such small gains biologically meaningful?").
  - Measure: the share of held-out NREM bouts ending in REM, among those the model rates least vs most likely
    (deciles of π). Reported without and with history.
  - The %-log-loss per 10-s step is diluted by the near-certain "stay" steps; it is a reliability measure, not an
    effect size.
- **E2, NREM depth** (the user: "is a long wake followed by more NREM simply because NREM is deeper?").
  - Depth = the scorer's SW metric, z-scored per session on NREM seconds.
  - (a) After wakes ≥ 7 min: depth over the first 120 s of post-wake NREM. Is it ~ ln d? Does the ln d effect on the
    NREM before the first REM survive with depth controlled?
  - (b) REM hazard: lagged depth [t−150, t−30) s. It is lagged because the scorer defines NREM by SW (15-s smoothing),
    so a contemporaneous SW is partly circular. Held-out comparison M2t vs M2t + depth, and the hazard curve per depth
    tertile.
- **E3, NREM tails** (the user: "compare the tail of natural NREM transitions with NREM cut by the battery change").
  - z-SW, z-theta and z-EMG over the 180 s before: natural NREM → WAKE, natural NREM → REM, and the end of the last
    session before each usable gap, split by cause and by how the cell ended.
  - The state in the last second and the NREM share of the last 60 s.
- **E4, circadian confound of compensation** (the user: "rounds happen morning and evening — test it"): the
  across-gap compensation slopes split by morning vs evening rounds, on both scorings.
- **Literature:** an Opus subagent audit on REM-permissive substates (requested by the user);
  report `scratchpad/lit_rem_permissive_substates.md`, to be copied into `docs/methods/` when it is done.

## 13. Amendment 4 — PROPOSED Phase 3: use the 24/7 record (2026-10-07; the user)

**The user's direction:**
- The LFP-feature tests (spindles / sigma, ripples, heart rate from the accelerometer, temperature as a slow gate;
  [literature](../docs/methods/sleep_rem_permissive_substates_literature_2026-10-07.md)) go on the candidate list.
- First, dig into what the continuous 24-h record allows:
  - night naps vs day sleep ("is nap REM the same as main-sleep REM?");
  - how sleep reorganises over hours after an interruption (relayed review).

**Counts (Phase-0 units, MA < 40 s):**
- SLEEP episodes ≥ 20 min: 411 in the light phase (median 47 min) vs 144 in the dark phase (naps; median 34 min).
- Wakes followed by sleep: 30–120 min = 17 light / 128 dark; ≥ 2 h = 18 light / 76 dark.

**Q1. Night naps vs day sleep: is REM the same?** Units: SLEEP episodes (dark vs light; plus short naps of 5–20 min).
Per rat: 6/6 signs, and an animal random effect.
- (a) **Structure.** REM share of sleep, REM bouts per hour of NREM, REM bout duration, inter-REM interval, sequential
  fraction. Latency from episode onset to the first REM as a survival curve; episodes without REM are kept.
- (b) **Entry rules.** The empirical REM hazard against the NREM since the last REM, naps vs day. Held out: does a
  dark × history interaction add prediction to the Phase-1/2 model?
- (c) **REM itself.** z-theta, z-SW and z-EMG (head stillness) during REM, and the REM-onset tail, naps vs day.
- (d) **24-h budget.** Is the night REM deviation (vs expectation) followed by an opposite deviation the next day?
  About 10 days per rat, so this is descriptive.

**Q2 (main). Recovery trajectories after interruptions.**
- **Events.** Every natural wake ≥ 2 min followed by sleep; battery rounds as their own class.
- **Follow-up.** Up to 6 h along the joined timeline, across midnight, censored at real gaps:
  - cumulative NREM min, REM min, REM count;
  - the fraction still without a first REM (Kaplan–Meier).
- **Expected.** Each is shown as observed − expected (the C1 baseline: animal + time of day + day, fitted leave one
  block out), giving excess curves.
- **Compared** by wake length (2–7, 7–30, 30–120 min, ≥ 2 h) and day vs night, with the REM debt of the previous 3 h
  as a second axis.
- **Reading.**
  - A pure delay = curves parallel to the expectation that later converge.
  - A re-allocation = NREM first, then REM catches up.
  - A lasting loss = curves that never return.
- Episodes that never reach REM are kept: they are part of the result.

**Q3. Arrangement.** Does fragmentation matter, beyond the totals? Fragmentation index = wake bouts ≥ 40 s per hour
of the previous 1–2 h. One held-out comparison added to the Phase-2 model with the totals held, and the Q2
trajectories split by fragmentation.

**Control:** every trajectory and compensation result is repeated on the fixed-threshold scores, because per-session
thresholds produced an artefact before.

## 14. Amendment 5 (2026-10-08, AFTER the Phase 3 results; the user's review: "be bolder") — Phase 3b

Two checks, run before the claim audit so the summary could be as strong as the data allow.
Driver: `ephys/sleep_schedule.py phase3b`.

1. **Same-events catch-up.** Natural wakes followed for ≥ 3 h (and ≥ 6 h), with the REM excess at 1 / 3 (/ 6) h
   computed on the same events, plus the paired change; battery rounds likewise.
   - Result: no wake-length effect at 1 h in this sample (−0.08, n.s.; fixed thresholds −0.02), and no 1 → 3 h change.
   - "Delay then catch-up" is **withdrawn**. The Phase-3 first-hour effect was sample-dependent.
   - Battery rounds: REM stays ~1–1.4 min below expectation at 1, 3 and 6 h under fixed thresholds.
2. **24-h budget robustness.**
   - Run on both scorings, in minutes and in rates, at ≥ 50 % and ≥ 80 % recorded, with animal fixed effects and
     per-animal slopes, for REM and NREM.
   - Result: the night → next-day trade-off is robust for NREM (fixed thresholds, within-rat −0.54 to −0.91,
     p < 0.001). For REM it goes the same way but is weaker (within-rat CIs mostly include 0).
   - So it is not a REM-specific budget.

**Status: DONE 2026-10-08.**
- [Claim audit](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_schedule_claim_audit_2026c.md)
- [Change log](../change_log/2026-10-08-sleep-internal-schedule.md)

Candidates for the next round (the user's list): spindles / sigma, ripples, temperature as a slow gate, heart rate from
the accelerometer, and the mic listening check.

## 15. Amendment 6 — Phase 4: ambient temperature as a slow REM gate (2026-10-08; the user: "mic, then temperature")

Written **before any temperature result**. Literature
([substates audit](../docs/methods/sleep_rem_permissive_substates_literature_2026-10-07.md)): ambient temperature is the
only slow REM gate with causal rodent evidence (cold suppresses REM in rats; warmth raises it in mice).

**Prediction (directional):** warmer than usual for the hour → REM entry more likely, and REM share of sleep higher.

**Data.** `sleep_quant.load_weather`: the on-site console at 5 min, 08-31 → 09-12, with NWS KITH only inside the
console's 09-02 / 03 uplink hole.

**Analyses:**
- **Temperature anomaly** = temperature minus its 2-harmonic time-of-day fit over the cohort. Raw temperature is
  collinear with phase, which every model already holds.
- **T1.** Held out, forward chaining: M2t vs M2t + anomaly. Also reported: the full-fit REM-vs-stay and Wake-vs-stay
  coefficients per SD, and per-animal signs.
- **T2.** Hourly REM share of sleep, and sleep share of recorded time, regressed on the anomaly + phase + day + animal.
  Binomial GLM, SEs clustered by day.
- **T3.** The night–day trade-off (claim #13) with the night and day mean anomalies as covariates. Does the slope
  survive? It is run on both scorings.
- **T4.** The empirical REM hazard against the NREM since REM, per anomaly tertile (description).

The ambient temperature is outdoors; the houses buffer it, and no in-house temperature exists.

## 16. Amendment 7 — Phase 5: do the animals enter REM in sync? (2026-10-08; the user; written before results)

**Question:** does a housemate's REM onset raise a sleeping animal's own REM-entry hazard, beyond its own clock and
beyond simply sleeping together?

**Data:**
- One absolute 1-s timeline per animal (FINAL states, records, cut at 09-11 19:40). The session clocks differ by
  ~1 s, which is negligible at 10 s.
- WISER zone per second (house_1 / house_2 / field). Mates = the other implanted animals in the same house at that
  second.

**Per NREM step of animal B, at the step time:**
- `n_mates` = co-located mates with a known state, and `mates_asleep` = their share asleep. These are the social
  context and go into the BASE model.
- `mate_on60` = a co-located mate entered REM (after ≥ 60 s of NREM) within the previous 60 s.
- `mate_rem` = a co-located mate is in REM now.
- The same two terms for animals in the OTHER house or in the field (`far_on60`, `far_rem`): the natural control.

**Test (forward chaining, as Phase 2):**
- base = M2t + `n_mates` + `mates_asleep`;
- + `mate_on60` + `mate_rem`: the held-out gain, the full-fit REM-vs-stay coefficients, and per-animal signs;
- separately, + `far_on60` + `far_rem`.

**Descriptive:** P(REM in the next 10 s) with vs without a mate's REM onset in the last 60 s, within strata of B's own
NREM since its last REM.

**Reading:**
- Coupling only with co-located mates → social / sensory coupling.
- Coupling also with far animals → a shared outside driver.
- Neither → no REM synchrony beyond co-sleeping.

## 17. Amendment 8 — Phase 5b: local, fast coupling of movements during sleep (2026-10-08; the user; written before results)

**The user's observation (video):** groups of sleeping rats twitch their legs in sequence; one starts and it
propagates. Phase 5 tested REM entry averaged over all house co-location within 60 s, which would miss fast, local
coupling.

**Events.** Per animal, a head-movement onset during sleep:
- the head-IMU seconds cache (field-PC clock, 1 s) shows state ≥ 2 (active) after ≥ 5 s of state 1 (still);
- the FINAL sleep score is NREM or REM at that second;
- typed by the score: REM (≈ twitches) or NREM.

**Pairs.** A and B both asleep at A's event; same house (WISER, as Phase 5) vs different places (the control).

**Cross-correlogram.**
- B's event onsets at lags −10 … +10 s around each A event (1-s bins);
- baseline = B's mean rate per bin at |lag| 30–60 s (a local baseline, so time of day cancels);
- excess = observed / baseline at lags 0, ±1–3 s;
- direction = the count at +1…+3 vs −1…−3 s.

**Cascade.** After an A event with ≥ 2 asleep housemates: the number of housemates with an event within +5 s, vs the
same at +30…+60 s.

**Reading:**
- A short-lag excess only for same-house pairs → local coupling.
- Asymmetric lags → propagation.
- A zero-lag excess in all pairs → a shared trigger (e.g. a sound; to be cross-checked with the mics).
- None → no fast coupling at the 1-s resolution of the IMU seconds cache.

## 18. Amendment 9 — Phase 5c: the coupling at 20 ms with the IMU-as-EMG signal; REM twitch or awakening? (2026-10-08; the user; before results)

**The user:**
- "does this move as REM or just awake?"
- The seconds-cache state is processed, so use the EMG-IMU (or EMG-LFP) version.

**Signal.** The 50-Hz `make_imu` output (`D:/3rd_rat_spikes/analysis/imu/<SFxx>/<session>.imu.npz`):
- VeDBA = the IMU-as-EMG the sleep scorer uses (before its 1-s binning and 15-s smoothing), and head angular speed;
- on the field-PC clock (`t_pc_ms`, pc_time chain), so cross-animal timing is good to ms.

The LFP-EMG version is the cross-check if needed (heavier; our LFP is low-passed at 450 Hz).

**Events.** Per animal: θ = median + 8·MAD of its VeDBA during scored-NREM seconds. Event = the first sample ≥ θ after
≥ 1 s below θ, while the score is NREM or REM. Typed by the score (REM vs NREM).

**Coupling.**
- Same-house pairs (WISER), B asleep; cross-correlogram of B's events at ±3 s in 20-ms bins vs the rate at |lag| 30–60 s.
- The peak position and width per unordered pair:
  - ≈ 0 ± 40 ms = passive or common;
  - a shifted peak at 100–1000 ms = a response.
- Per animal, a "leader" share: of coupled pairs within ±1 s, how often this animal moved first by ≥ 60 ms.

**Outcome — the user's question.** Each event is classed by what follows:
- A's score 10 s and 30 s later: asleep (a twitch or brief movement) vs wake (an awakening);
- the same for B's coupled responses (B within 0–1 s after A) vs B's other events;
- P(B wakes within 30 s | A's event, B asleep) vs the same 60 s before A's event.

## 19. Amendment 10 — Phase 6: a library of sleep-perturbation events, and the LFP-EMG check (2026-10-08; the user + relayed review; before results)

**The user:** a movement that does not wake the animal is a special window, in REM and in NREM. Keep such windows
for later use, under two scenarios:
- a disruption after which the animal wakes (outside noise, battery change);
- a disruption after which it does not.

**6a. Event library.** Built locally: `ephys/sleep_events.py` → `$OUT_ROOT/2026c/sleep_events_<ts>/`, plus a README.

**Sources:**
- **group movement:** ≥ 2 co-located sleeping animals start moving within 1 s of the first. Same 50-Hz IMU-as-EMG
  onsets as Phase 5c.
- **solo movement:** one animal moves and ≥ 1 co-located housemate sleeps; nobody else moves within 1 s.
- **sound candidate:** a house-mic transient ≥ 20 dB (b0–b2, vs the 60–20 s median) while ≥ 1 animal sleeps in that
  house, with no housemate movement onset in the 2 s before. Unvalidated until the listening check.
- **handling:** usable battery-round gaps; the state before the stop and after the restart. The gap itself is
  unobserved.

**Per event:** id, source, house, t0 (field-PC), initiator, participants.

**Per participant (every co-located animal):**
- role: first mover / follower within 1 s / non-mover;
- state at t0 and the state composition over −60…0 s;
- outcome:
  - the state at +10 / +30 / +60 s;
  - the first wake within 60 s, its latency and duration;
  - a 30-s class: after NREM, stays NREM / to REM / wake; after REM, stays REM / to NREM / wake;
- completeness flags (score known −60…+60 s, IMU valid, zone known);
- pointers:
  - IMU: session, 50-Hz index;
  - LFP: storage path, LFP sample = amplifier sample / 16;
  - video: the CH05–CH08 files covering t0 and their offsets;
  - house mic file and offset; CH01 file and offset.

**Rates:** events per hour of co-sleep (≥ 2 animals asleep in the same house), by the initiator's state. Per event:
all asleep participants stay asleep / some wake / all wake.

**6b. LFP-EMG for every participant.**
- **Signal:** 300–440 Hz band (our LFP is low-passed at 450 Hz) on 8 channels spread across the probe.
- **EMG proxy:** the mean pairwise correlation (Buzsáki EMGFromLFP logic) and the band RMS, in 100-ms windows.
- **ΔEMG** = the event window (−0.2…+0.5 s) minus the baseline (−2…−1 s).
- **Question:** do followers show their own muscle burst like first movers (active), or not (passive jostle)?
  Non-movers serve as the reference.
- **Route:** validated locally on the sessions with a local LFP copy, then run on BioHPC over storage through the
  post-run hook (new part `sleep_events`).

**Addendum, 2026-10-08.** Added after a first test run of the library, before the real run and before any LFP-EMG.
That run counted ~22 % of the seeds as "group" with a 1-s window, and Phase 5c puts the excess at 0.1-1 s at only
~2x, so much of that share is chance. Two additions follow:
- followers are split at 0.1 s (tight / loose);
- every event carries a time-shift chance level (the same follower test at -47 / -31 / +31 / +47 s), and rates are
  reported as observed vs chance.

**Route change, the same day:** the LFP-EMG runs on the analysis PC, reading the storage LFP read-only.
- Why: BioHPC was overloaded (1 h of LFP: read 230 s and filter 87 s, vs 0.4 s each here).
- Commits: the outputs are byte-identical to the validated local run (array MD5).
- Storage: the results are uploaded to the workdir and copied through copy_to_storage.sh, part emg_from_lfp.

**Addendum 2, 2026-10-08.** Also before the real run. The test run's partial EMG (SF07 / SF08 only) suggested that tight
followers' EMG rises like first movers'. Because a jolt could put motion artefact into the LFP, two controls are fixed now:
- the same comparison at matched movement size (terciles of the peak head VeDBA over 0..0.5 s);
- the half-maximum / peak timing of the mean VeDBA vs mean EMG traces per role.
"Active" is claimed only if both point the same way.

## 20. Amendment 11 → the next stage: the "sleep behaviour explore" (2026-10-08; the user)

Phases 0–6 are closed here. The user asked for a logic synthesis of all phases, audited by Fable ("don't be too
conservative"). Result: [docs/methods/sleep_logic_audit_2026-10-08.md](../docs/methods/sleep_logic_audit_2026-10-08.md)
(read the main session's checks in its header first). It changed the claim audit on 2026-10-08:
- #13 withdrawn as a balance (a cohort-wide drift, #30);
- #6 split into #6a / #6b;
- #10 re-worded; #14b and #31 added;
- the LFP-feature claims moved to the next stage.

The next stage is planned separately: [2026-10-08-sleep-behaviour-explore.md](2026-10-08-sleep-behaviour-explore.md).
It has three themes (the schedule; day vs night sleep; the scheduler as the implicit theme, with a model), uses the
sleep sequence + IMU + WISER + temperature + handling only (no LFP features), and contains 25 hypotheses.
