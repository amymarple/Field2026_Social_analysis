# Sleep-state scoring for cohort 3 with the IMU as the EMG: audit of Sleep_dynamics and integration plan (2026-09-28)

**Status.** PLAN, 2026-09-28. Audit done; nothing run yet.

**Inputs already in place:**
- per-second IMU movement for all 203 sessions, with the per-animal immobility threshold (VeDBA valley 0.31–0.39 m/s²);
- IMU-vs-LFP check: moving seconds are theta-dominated;
- LFP for all sessions: BioHPC, running; locally for 4 sessions.

## Audit: `D:\Documents\ayalab\Sleep_dynamics` (user's earlier pipeline)

**What it is.** A Python port of the Buzsaki-lab / neurocode `SleepScoreMaster`, MATLAB-exact by design
(`preprocess/state_scoring.py`, entry `run_state_scoring`):
- **LFP-EMG:** 300–600 Hz correlation across spike-group channels.
- **Channel selection:** automatic slow-wave and theta channels (power-spectrum-slope bimodality; theta above a 1/f
  background).
- **Features:** `broadbandSlowWave`, `thratio`, EMG.
- **Thresholds:** histogram-dip.
- **States:** NREM = slow wave above threshold; REM = not NREM, low movement, high theta; WAKE = the rest.
- **Post-processing:** a 6-s minimum state length; an optional recheck of low-margin epochs.
- **Outputs:** buzcode `.mat` files (`SleepState.states.mat`, episodes, EMGFromLFP) plus figures in
  `complex_system/`.

Around it:
- `preprocess/imu_movement.py` (IMU refinement);
- `sleep_refine/` (XGBoost / BiLSTM refinement trained on manually curated sessions);
- `state_editor.py` (a port of TheStateEditor for manual editing);
- fragmentation analyses.

**Findings.**
1. **Two diverged copies of the scorer.**
   - Sleep_dynamics: 4,027 lines, with recheck, manual bad channels, ignore intervals and the IMU hooks.
   - PreprocessPipeline `src/preprocess/state_scoring.py`: 2,714 lines, with the 2026-09-09 memory-efficient changes
     and few IMU hooks.
   - Line similarity is 0.65; 50 functions are shared. Neither is the documented master.
2. **The Sleep_dynamics code in use is uncommitted.** `state_scoring.py`, `metafile.py` and the notebook are
   modified after the last commit (2026-03-17), and CLAUDE.md plus several scripts are untracked. Results cannot be
   pinned to a version until it is committed.
3. **Tests.** One unit test (interval masking), which passes. The scoring logic itself has no automated test.
4. **The LFP-EMG band vs our LFP.** The scorer uses 300–600 Hz at srLfp 1250. Our `.lfp` (like the pipeline's and
   neurocode's) is low-passed at 450 Hz (−6 dB at 450, −29 dB at 625), so the EMG surrogate effectively uses
   300–450 Hz: weaker but usable. The IMU is the better movement signal here.
5. **The IMU hooks were built for the lab's IMU CSVs** (`<epoch>/IMU.csv` from `process_IMU_from_basepath.m`) and do
   not fit our data:
   - The default metric `composite` = 0.4 × high-passed acceleration + 0.4 × "speed" + 0.2 × \|d(roll, yaw, pitch)/dt\|.
     The "speed" is integrated, high-passed acceleration (not speed), and yaw comes from the 9-axis fusion, which the
     headstage magnet invalidates. Only the `dynamic_acc` component is clean.
   - The movement is rescaled per session to its own 5–95 % range, so the same physical movement scores differently
     in a sleep-heavy and an active session.
   - The IMU only co-signs:
     - `imu_for_rem` makes the IMU the REM low-movement gate;
     - `use_imu_movement` flips NREM → WAKE only when the IMU **and** the LFP-EMG both say "moving";
     - NREM itself is decided from slow-wave power alone.
   - **Silent fallback:** if loading the IMU fails, it only warns and scores LFP-only.
   - Alignment is correct: each epoch's IMU is placed by its own relative time, so the 4-h `unix_ms` error of the
     MATLAB script cancels.
6. **Thresholds are set per session** from histogram dips. Our sessions are either sleep-rich days (~80 % still) or
   wake-rich nights. On a night the slow-wave distribution may not be bimodal, which makes thresholds unstable. The
   scorer already supports fixed overrides (`state_sw_threshold_override`, `state_theta_threshold_override`).
7. **`sleep_refine` is trained on other animals' manual labels.** It uses the auto scorer's labels as a feature (the
   leakage bug is documented and fixed). It will not transfer to the WILD logger / probe without our own labels; out
   of scope for the first pass.
8. **Inputs it needs:** `<basepath>/<basename>.lfp` plus a session dict with `extracellular.nChannels`,
   `extracellular.srLfp`, `extracellular.spikeGroups` and `channelTags.Bad.channels`. Dependencies: numpy, scipy,
   matplotlib; standalone.

## The two copies compared (2026-09-28; subagent review, key claims re-verified)

**A** = Sleep_dynamics working tree (uncommitted). **B** = PreprocessPipeline `eb3dad4` (committed).

- **Same core.** Of 50 shared functions, **35 are AST-identical**: power-spectrum-slope/IRASA spectra, the theta
  metric, the dip statistic, histogram-dip thresholds, MATLAB-style downsample/smooth. The features and thresholds
  therefore behave the same.
- **LFP-EMG.** Both compute it **from `.lfp` only**. MATLAB `getEMGFromLFP` has a `fromDat` option (default off) that
  neither port implements. Both use 300–600 Hz, a 3rd-order Butterworth, 0.5-s windows and a 2 Hz output. Channel
  choice differs: A the middle channel of each shank, B the first. A adds window-energy QC that preferentially drops
  the quietest (sleep) windows. That is a risk, and it is not MATLAB.
- **Memory on a 12-h, 64-ch session.**
  - A loads every candidate channel as float64 before downsampling (~35 GB).
  - **B streams one channel at a time** (~86 MB per channel, ≤ 4 threads).
- **Excluded time.**
  - **B labels it.** `_intervals_from_mask` ignores timestamp gaps and `_fill_unassigned_states` fills every 0 from its
    neighbours. In a synthetic test all 349 ignored seconds got labels, and one NREM interval bridged the gap.
  - A splits at gaps (as MATLAB does). But A's default "recheck" (not in MATLAB) leaks labels back into ignored
    windows: 190/349 in the same test; 0 with recheck off.
- **Extras only in A:** scoring windows and ignore intervals, threshold overrides and scales, a manual bad-channel
  file, the IMU hooks (unusable for WILD, see above), provenance text files.
- **Extras only in B:** atomic writes, a v7.3 fallback above 2 GB, outputs in the buzcode layout (A defaults to
  `complex_system/`).
- **Shared deviations from MATLAB:**
  - minimum-duration step 5 only converts short WAKE next to NREM (MATLAB converts every short WAKE);
  - the sticky trigger is stored but never applied;
  - `dt_spec = window − 1` equals MATLAB's 1-s step only at the default 2-s window (we use the default);
  - **neither preserves TheStateEditor manual edits on overwrite.**

**Recommendation: B as the base, with runtime shims from our driver; neither repo modified.**
1. **Gap-aware intervals** (A's `_intervals_from_mask`), and **no filling of excluded bins**. Excluded cohort-3
   windows — rounds, probe-advance settle time, ADC lane, connector-open — stay unlabelled.
2. **Exclusions via B's existing `pulses.intsPeriods` (ignoretime).** No port needed.
3. **The IMU in B's EMG slot:** our per-second VeDBA at 2 Hz on the LFP timeline, used for the REM gate and for
   NREM → WAKE. The LFP-EMG is kept alongside for comparison. An IMU loading failure is fatal.
4. **Threshold overrides** (A's `_resolve_threshold`) only for pass 2 (fixed per-animal thresholds).
5. **Off:** A's recheck and A's EMG-energy QC. Not MATLAB, not validated.
6. **Protect manual scoring:** automatic output goes to its own folder; the user's edits in `state_editor.py` are
   saved separately and never overwritten.

## Integration plan (our driver `ephys/score_sleep.py`; their repo stays unmodified)

1. **Pin the scorer.** The user commits Sleep_dynamics; we record its commit in every output sidecar. Use the
   Sleep_dynamics copy (it has the IMU hooks and ignore intervals); PreprocessPipeline's copy is the fallback.
2. **Per-session basepath without copying:**
   - `<analysis_root>/sleep/<SFxx>/<session>/` holding `<session>.lfp` as a **hard link** to
     `<analysis_root>/lfp/<SFxx>/<session>.lfp` (same volume);
   - a session dict built from our XML / `probes_2026c.yaml` (spike groups = shanks; bad = skip channels). Nothing
     is written into raw folders.
3. **The IMU as the movement signal.**
   - Replace their loader at call time (a shim in our driver, like the sort shims) with our per-second VeDBA,
     smoothed over 2 s.
   - Map it so that their fixed threshold 0.5 equals our physical per-animal threshold:
     $$ M(t) = \operatorname{clip}\!\Bigl(0.5 + \tfrac{1}{2}\log_{10}\frac{\text{VeDBA}_{2s}(t)}{\theta_a},\ 0,\ 1\Bigr), \qquad M > 0.5 \iff \text{VeDBA}_{2s} > \theta_a $$
     **Text:** movement on their [0, 1] scale, anchored to the physical, per-animal still/active valley $\theta_a$ (m/s²)
     instead of per-session percentiles; 0.5 means exactly at the threshold.
   - Set `imu_for_rem=True`, `use_imu_movement=True`, `imu_movement_threshold=0.5`.
   - Loading failures **raise** in our driver instead of silently falling back.
4. **Ignore intervals from the field record** (`/regime-aware-ephys`): battery rounds (handling), probe advances,
   and connector-open / ADC-lane pieces are passed as `state_ignore_intervals`.
5. **Threshold strategy.**
   - Pass 1: per-session thresholds on the sleep-rich day sessions only; check their stability per animal.
   - Pass 2: fix per-animal slow-wave / theta thresholds (overrides) from pass 1 and apply them to every session,
     night sessions included.
6. **A stricter NREM variant to compare** (driver post-rule, not in their code): NREM seconds where the IMU is moving
   for ≥ 5 consecutive seconds → WAKE. It is reported next to their "both agree" rule, not substituted silently.

## Validation (local first)

- **Pilot:** the 4 local LFP sessions (SF08 09-10 day, SF07 / SF10 09-02 day, SF07 09-01 night).
- **Anchors:**
  - SF08 09-10 14:37 REM (leg twitches) must score REM;
  - SF07 09-09 22:33 motionless outdoors must not score REM without theta;
  - moving seconds must be ≥ 95 % WAKE.
- **Manual check by the user:** 2 h per animal in `state_editor.py` (the TheStateEditor port). Agreement (Cohen's κ)
  with the automatic score is the acceptance number. I do not judge spectrograms myself.
- **Plausibility:** the REM share of sleep is ~5–20 %; NREM bouts have a sensible duration distribution; states
  follow the light–dark pattern.
- Then the server: the same commit on the BioHPC LFP, one session compared with the local output.

## Questions for the user

1. Commit the Sleep_dynamics working tree so the scorer can be pinned? And is its copy the one to use, or should
   PreprocessPipeline's be the master?
2. OK to make the IMU the primary movement signal: REM gate plus the NREM → WAKE veto, with the stricter variant for
   comparison?
3. Do you have manually scored sessions of this cohort, or should 2 h per animal be scored in `state_editor.py`?
