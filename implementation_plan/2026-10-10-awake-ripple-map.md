# Where do the rats make awake ripples at night? A ripple-rate map across the paddock (cohort 2026c) — plan

2026-10-10, written before any map is computed. To be audited (text only) by the Codex reviewer before Phase 1.

## The request

The user, in their words: "夜里面awake ripple的分布，每个animal长什么样，画一个 ripple rate colormap across paddock".
That is: the distribution of awake ripples at night, what each animal's looks like, as a ripple-rate colormap across the
paddock.

The open design problem is the unit: the rats are out for hours. The user's idea: use naps as breaks. When a rat comes
home and naps, the activity before it is one trial. Second question: do the animals' maps relate? The WISER method came
from the WISER session ("IMU-video校准", 2026-10-10).

## Questions

- **Q1.** Is the night-time awake-ripple rate place-dependent in the paddock, per animal?
- **Q2.** Is that map stable across trials (nap-delimited) and across nights?
- **Q3.** Do the animals' maps relate: shared places, proximity to another animal, or coupling in time?

## Data and definitions (fixed now)

**SWR events.**
- Source: the production on storage (`analysis/swr/`), sessions of tier validated / good, before `use_until`.
- Time: field-PC time = session `start_local` + `peak_s`.
- Excluded:
  - SF11 after 09-02 19:08 (not CA1);
  - SF12 from 09-08 07:26 (ripple lost, contact) and SF12 block 3;
  - everything from 09-11 19:40 (females, population 5 → 10, untagged).

**Quiet awake ripple (qSWR)**, all conditions at the same time:
- an event at night (sunset → sunrise);
- final 1-s state WAKE;
- not `x_theta`, not `x_emg_lfp`, not `x_moving`;
- the head IMU `ok` & `still` in that second (`imu_seconds_cache`).

Availability, counts only, no positions (2026-10-10). Night WAKE events per animal:

| | SF07 | SF08 | SF09 | SF10 | SF11 | SF12 |
|---|---:|---:|---:|---:|---:|---:|
| all | 94 k | 161 k | 65 k | 98 k | 12 k | 40 k |
| without theta | 61 k | 96 k | 62 k | 77 k | 11 k | 36 k |
| without theta and LFP-EMG | 6.8 k | 12.6 k | 11.3 k | 12.0 k | 1.6 k | 8.2 k |
| + not moving | 2.7 k | 8.2 k | 8.1 k | 6.1 k | 1.1 k | 5.8 k |

Most awake candidates sit on muscle activity, so qSWR validity is the first gate (Phase 1).

**Occupancy (the denominator).** Night seconds that meet all of the following:
- WAKE;
- head IMU ok & still;
- SWR-covered (as above);
- outside handling (battery rounds ± 30 min, `m_handling`) and lid events (`cv/configs/cohort3_lid_events.json` ± 5 min);
- with a position.

**Position.**
- Track: the V3 default track `load_default_track(label, date)` on `t_al_ms` (WISER lag τ* per animal; SF11 assumed 0.15 s);
  UTC → EDT; 1-s median of the fixes.
- Fixes dropped: `m_handling`, `m_silence`, `m_tag_validity`, `m_off_animal`.
- Low-anchor fixes are kept, and `anchors_used` is reported.
- `qc_i1` seconds are kept in the primary maps and dropped in a sensitivity.
- Positions are never read from V3 speed.

**Space.**
- WISER inch frame, unverified offset: topology only, no compass claims.
- Paddock edges from the WISER→paddock map of `cv/cv_field/wiser_assist_p0.py` (`Map.inv`, accepted on one CH01 hour):
  roughly x 273–753, y 606–846 in.
- Bins of 24 in (≥ the 14-in rule).
- Each house is one bin (house_1 (417.7, 716.9), house_2 (621.2, 732.6); membership by `hysteretic_visits`: 14 in, enter
  10 s / exit 30 s).

**Rate map** per animal:
- rate = qSWR / quiet-wake minutes per bin; bins with < 120 s of occupancy are blank;
- relative rate = rate / the animal × probe-block mean night qSWR rate (detection differs by block);
- display only: Gaussian σ = 1 bin on counts and occupancy separately. Every statistic uses the unsmoothed maps.

**Units:**
- **Trial (the user's idea):** a night's active period from the record start (or sunset) to the main sleep onset, split
  at every home nap. A home nap = a sleep stretch ≥ 5 min with ≥ 3 min NREM, in a house. Trials < 10 min are dropped.
- **Excursion:** a maximal field period between two house visits, ≥ 2 min. Description.

## Phase 0 — counts (no maps)

Per animal-night, trial and excursion:
- qSWR count, quiet-wake minutes (field / houses);
- bins with ≥ 120 s occupancy;
- trials per night;
- the share of occupancy lost to each mask.

Rule: an animal enters Phase 2 with ≥ 300 qSWR in the field and ≥ 20 bins with ≥ 120 s.

## Phase 1 — are the quiet awake ripples ripples? (gate)

- **A blind page** (online, like the short-bout reader). 120 shuffled items:
  - 60 qSWR;
  - 30 NREM SWRs (positives);
  - 30 random quiet-wake moments (negatives).
- **Each item:** ripple-channel LFP raw and 100–250 Hz ± 0.5 s, ± 2 s context, a noise-site trace for EMG.
- **Choices:** ripple / not ripple / unsure. The reader is a person chosen by the user.
- **Gate:**
  - qSWR precision ≥ 0.7 and NREM-positive recall ≥ 0.8 → Phase 2.
  - Else: restrict to the qSWR subset with the best precision (a RipMax_z threshold chosen on this sample) and say so, or
    stop.

## Phase 2 — maps per animal (Q1, Q2)

- **T1, spatial structure.**
  - Statistic: the spatial information of the relative rate map (Skaggs, bits / event), field bins only.
  - Null: circular shift of the qSWR times along each trial's quiet-wake timeline (it keeps each trial's occupancy and
    event count, and breaks the event–place link), 500 times.
  - Holds per animal if p < 0.05. Q1 is answered "place-dependent" if it holds in ≥ n − 1 of the n animals entering
    Phase 2.
- **T2, stability.**
  - Statistic: the Pearson r of the relative maps from odd vs even trials, over bins with ≥ 120 s in both halves.
  - Null: the same shuffles. Stable if r > the 95th percentile.
  - Also: night-to-night r as a description.
- **T3, home vs field.** The relative qSWR rate in the houses vs the field, per animal: description, and an animal-level
  sign count.
- **Secondary (description):**
  - rate vs familiarity: log of the prior quiet-wake visits to the bin that night and over the cohort;
  - rate vs position within an excursion (first / middle / last third).

## Phase 3 — relations between animals (Q3)

- **R1, shared places.** Pairwise r of relative maps (bins with ≥ 120 s for both) vs the shuffle null of either animal.
  Shared if r > the null's 95th percentile. Read against the paddock's resources (pending: food / water / objects from
  the field record).
- **R2, proximity.**
  - Comparison: qSWR rate when another tagged animal is within 14 in (1-s medians on t_al) vs not.
  - Matched within the same bin and trial.
  - Null: partner positions shifted by ± 1 h.
- **R3, coupling in time.** Cross-animal qSWR co-occurrence within ± 0.5 s and ± 5 s vs a time-shift null (one animal's
  events shifted by 2–20 min).
- **Population:** only the 6 implanted animals carry tags; nothing after 09-11 19:40.

## Sensitivities

- qc_i1 seconds dropped;
- rain nights (09-03, 09-09) dropped;
- SF08 before 09-06 19:43 dropped (profile settling);
- the strict qSWR (still runs ≥ 3 s);
- 18-in bins.

## Caveats in reading

- **Frame:** the WISER frame is unverified and the paddock map was accepted on one camera-hour only. Maps show topology,
  not compass directions.
- **qSWR quality:** awake detections are contaminated by muscle activity (the table above); Phase 1 decides.
- **Detection by block:** SF07, SF11 1a and SF12 B3 detect on ripple power only.
- **Interpretation:** a held-out or shuffle-based effect is place dependence, not replay content. Awake ripples are
  known to rise at reward and novel places, so the paddock's resources must be on the map before any reading.

## Amendment 1 — after the Codex (astra) text audit, 2026-10-10 (before any map; supersedes the sections above where they differ)

The reviewer's verdict: Phase 0–1 may proceed. Before Phase 2, fix the validation gate, the match between events and
denominator, and the shuffle. Adopted:

**1. Unit.**
- The **night** is the primary replicate unit; nap-delimited trials stay as a supplement; excursions are description.
- The pooled maps use all eligible time: a trial < 10 min is not dropped from them, only from the per-trial analyses.
- Stability: across nights first (night-to-night and leave-one-night-out); odd vs even trials second.

**2. Phase 1 validation.**
- The 120 items are a **pilot**, and the 60 qSWR are stratified by animal × probe block × house / field × amplitude
  tertile.
- The NREM positives measure the reader, not the detector's recall. Random negatives do not estimate misses. Neither is
  reported as a detector property.
- If a RipMax_z (or other) threshold is chosen on the pilot, it is confirmed on a **second, independent sample** before
  any map.
- Items show the neighbouring channels' raw traces too, to tell a local oscillation from a common-mode artefact.
- Precision is reported per stratum, not only overall.

**3. Null model.**
- **Primary:** swap the event sequences between whole quiet bouts, keeping each bout's internal timing. Swaps happen
  within the same night and probe block, between bouts of similar duration (± 25 %) and time of night (± 1 h).
- **Sensitivity:** the circular shift along the quiet-wake timeline.
- The exchangeability assumption is stated: under H0 a bout's events depend on its duration and time of night, not its
  place.

**4. Events and denominator.**
- Events get exactly the denominator's masks (handling, lid, position, SWR coverage).
- Seconds in which detection is impossible are removed from the occupancy. Those are seconds with LFP-EMG above the
  `x_emg_lfp` threshold, or theta above the `x_theta` threshold, per second, from the same per-session thresholds.
- Per place, the share of candidates rejected by each flag is reported.
- Block: compare places **within** an animal × probe block first, then combine. Dividing by the block mean does not
  remove "different blocks visit different places".
- Smoothing never fills bins without occupancy.

**5. Controls added.**
- Elapsed time within the quiet bout (ripples rise with stillness duration) and time of night enter the bout-swap
  matching, plus a bout-level regression: events ~ place + log bout duration + clock harmonics + night.
- Low-quality localisation sensitivity: anchors_used ≤ 6; qc_i1.
- The paddock edge from the P0 map is a reference line only. No data is cropped by it.

**6. Rules.**
- 300 qSWR / 20 bins is a feasibility screen for inference only. Descriptive maps are shown for every animal.
- The "n − 1 of n" answer to Q1 is dropped. Per animal: is there spatial structure, its effect size (spatial information
  above the null median), and does it repeat across nights.
- Holm correction across animals (T1, T2) and across pairs (R1–R3).

**7. Relations between animals.**
- R1 is reported with each animal's own cross-night stability.
- R2:
  - 14 in is supported for still pairs (B2 still-pair distance p95 3.1 in, WISER session 2026-10-10). Moving pairs are
    not measured, so R2 is restricted to both-still seconds.
  - A partner without a position is unknown, not "far".
- R3:
  - tested only in jointly valid quiet-wake time, with the overlap recomputed after each shift;
  - the shifts keep each animal's local event-rate changes (shifts of 2–20 min within a night);
  - the cross-logger timing error (pc_time fits) is checked before any ± 0.5 s claim. The BLE PC-time path is a
    10–100 ms-class coordinate, so ± 0.5 s is feasible; ± 5 s is the primary window.

**8. What a map can mean.** A hotspot can come from:
- a place-related artefact (Phase 1 per stratum);
- detectability (point 4);
- dwelling behaviour (the bout-duration control);
- missing positions (sensitivity).

Hotspots are interpreted only after the paddock resources are on the map.

**Addendum — the field record (recording-inquiry, 2026-10-10).**
- **Food and water:** no cohort-3 record gives feeder or water positions, how food was given, or refill times. Only the
  cohort-2 reset plan names "feeders, water stations". The two water towers are outside the paddock.
  - **The user, 2026-10-10: the food was in the houses.** So the house bins are home, food site and huddle at once. The
    T3 house-vs-field comparison cannot separate home from food. It is read as "at the home / feeding site", not as
    "home" or "reward" alone.
  - Water: not stated yet.
- **Landmarks:** pole, wall and house positions come from the "Camera_motion_calibration" session (the user's referral),
  as reference marks only.
- **Handling masks to add:**
  - the **09-01 ≈ 00:34 midnight round** (all six stopped / restarted; a catch is likely). It is missing from
    `cv/configs/cohort3_handling_windows.json` and `cohort3_lid_events.json`; mask ± 30 min.
  - the 08-31 11:00–18:00 troubleshooting window (already in the handling windows).
- **Night BLE passes:** the operator may have been at the paddock edge:
  - 09-03 00:16–00:25, 09-06 00:21–00:36, 09-06 23:43–23:57, 09-07 23:14–23:33, 09-09 03:17–03:27;
  - knee passes 09-07 06:41–06:49, 09-10 06:04–06:12.
  - Sensitivity: drop ± 15 min around each.
- **No other refuge** is recorded. Nest material was present (09-08, 09-10), place not stated.

## Amendment 2 — after Phase 0 (counts only), 2026-10-10; still before any map or rate

**What Phase 0 showed, as counts.**
- The pre-registered qSWR (IMU still, no theta / EMG / moving flag, theta- and EMG-detectable) leaves 0.01–0.24 h of field
  time per animal over all nights, and 0–1 field bins ≥ 120 s.
- Causes:
  - 98 % of night wake fails the theta-or-EMG detectability rule;
  - only 3 % of IMU-ok wake is IMU-still.
- **The validation data already in hand argue against two of those exclusions on normal blocks.** In the user's GUI
  clicks:
  - moving-flagged events were ripples in 49 / 87;
  - EMG-flagged events were ripples in 53 / 95;
  - unflagged events were ripples in 388 / 662;
  - theta-flagged events were ripples in only 7 / 40.
  - That is why the production `excluded` drops REM + theta everywhere, and moving + EMG only on blocks without a
    sharp-wave reversal (SF07, SF11, SF12 B3).

**New primary definition** (qSWR stays as a sensitivity):
- **Awake ripple (aSWR):** a production kept event (`excluded == False`) in a WAKE second.
- **Its time:** non-locomotor wake = WAKE & head IMU ok & IMU state still or active (not locomoting), outside handling,
  SWR-covered, with a position, and theta-detectable. On ripple-only blocks it must also be EMG-detectable.

**Phase 0 under this definition** (counts, all nights):
- non-locomotor detectable wake in the field: SF07 0.5 h, SF08 0.9, SF09 2.4, SF10 0.8, SF11 0.0, SF12 0.3;
- aSWR in the field: 35 / 4,897 / 7,633 / 3,618 / 0 / 1,157;
- aSWR in the houses: 1,276 / 12,231 / 17,333 / 15,847 / 300 / 7,568;
- field bins ≥ 120 s (24 in): 2 / 7 / 15 / 4 / 0 / 1;
- no animal passes the screen (≥ 300 events and ≥ 20 bins).
- The binding limit: 93 % of night wake has theta above the session's NREM 95th percentile, i.e. the rats explore in
  theta.

**Options, for the user to choose** (no map has been drawn):
1. A coarse 2-D map (48-in bins, or paddock regions: around each house, the mid-field, the walls, the far ends).
2. A 1-D profile: awake-ripple rate vs distance to the nearest house, in 24-in rings. It needs distances only, which suits
   the unverified frame.
3. The 24-in map at a lower occupancy (≥ 30 s), with shrinkage toward the animal's mean and uncertainty shown.

Whichever is chosen, the Phase 1 validity check runs first, stratified as in Amendment 1. House vs field stays the first
question (food is in the houses).

## Amendment 3 — the user's choice, 2026-10-10 (before any map)

The user chose **both** of the following ("粗格子可以毕竟场地大。一维曲线可以" — the coarse grid is fine since the field is
large, and the 1-D curve is fine). Option 3 is not done.

**Coarse map (display + description).**
- Bins of 48 in on the WISER frame, anchored at the P0 position of pole A0: a 10 × 5 grid over the paddock. Each house is
  its own bin (membership overrides the grid).
- Occupancy ≥ 60 s per bin.
- Rate = aSWR / non-locomotor detectable wake minutes.
- Shown per animal, with the landmark config (`ephys/configs/paddock_landmarks_wiser_2026c.json`) as reference marks.
- T1 / T2 (bout-swap null, Holm) are computed on this grid.

**1-D profile (primary place statistic).**
- Distance from the 1-s position to the nearest house rest-cluster centre (the centres the membership uses).
- Rings:
  - ring 0 = inside a house (membership);
  - field rings 0–24, 24–48, 48–96, 96–144, 144–192 and > 192 in.
- Rate per ring per animal.
- **Statistic:** the slope of log(rate + 0.5 / ring minutes) on log ring-centre distance over the field rings, weighted
  by occupancy. Its null is the bout swap (Amendment 1), within night and block.
- **House vs field:** the ring-0 rate against the pooled field rate, per animal, with the same null. It is read as
  "home / feeding site vs field", since food was in the houses.

**Phase 1, now concrete** (the Amendment 2 definition):
- **Items:** 80 aSWR (40 field, 40 house), stratified by animal and amplitude tertile, with the field oversampled; 30 NREM
  kept SWRs; 30 random non-locomotor detectable wake moments with no event within ± 2 s.
- **Panels:**
  - ± 2 s raw LFP of the ripple site, its two neighbours above and below on the shank, and the noise site;
  - ± 0.5 s raw and 100–250 Hz of the ripple site.
- **Choices:** ripple / not a ripple / unsure. A blind online page, like the short-bout reader.
- **Gate:**
  - the field-stratum aSWR precision (ripple / (ripple + not)) must be ≥ 0.7 for the field rings and map;
  - the house stratum the same for ring 0;
  - a stratum below that is dropped or restricted (a RipMax_z cut chosen here, confirmed on a second sample).

## Amendment 4 — after reader HC's answers, 2026-10-10 (before the second reader is merged; before any map)

**What reader HC said** (the user, 2026-10-10):
- "Unsure" was mostly EMG: the panels cannot be judged without denoising.
- "Not a ripple" was almost always theta at that moment.

**Preliminary precision, HC only** (`ephys/configs/awake_ripple_review_2026c/reader_HC_2026-10-10.csv`):

| set | ripple / not / unsure | precision |
|---|---|---:|
| NREM | 30 / 0 / 0 | 1.00 |
| aSWR house | 36 / 2 / 2 | 0.95 |
| aSWR field | 24 / 6 / 10 | 0.80 |

Both strata pass the 0.7 gate. Final only after the second reader (the user's mentor, scoring the same page).

**Denoised reader (a second page, the same 140 items and key).**
- `awake_ripple_map.py rerender --denoise`. For each CA1 site $x$ and the cortical noise site $r$, both high-passed at 80 Hz:
  $x' = x - \hat\beta\, r_{hp}$, with $\hat\beta = \sum x_{hp} r_{hp} / \sum r_{hp}^2$ fitted on $|t| \ge 0.25$ s only (the
  candidate never enters the fit). Below 80 Hz nothing changes, so the sharp wave and theta are kept.
- Effect (`review_denoise_effect.csv`, ratio of 100–250 Hz RMS after / before, over 0.25–2 s from the candidate):
  - field items 0.59–0.75 by call, NREM 0.96, overall median 0.81;
  - candidate-to-background contrast in the field rises from 1.1–1.4 to 1.4–1.9.
- Page: https://claude.ai/artifact/UEwwMBv697HCny8mRhYZnz (private; answers in its db `reads/<id>`). The first page
  (https://claude.ai/artifact/WMxCByZiKjfcxA5ZxLugpK) stays unchanged while the second reader scores.
- **Use.** A reader may read both pages. The denoised reading is a second, separate reading: it changes the unsure share,
  and so the precision, and is reported as its own row, never merged into the raw reading.

**Theta context (exploratory, chosen on these same items: hypothesis only).**
- HC's ripple vs not-a-ripple calls on aSWR, separated by the ripple-site theta/delta (`swr_emg.theta_delta_log`, relative
  to the session x_theta threshold):

  | window | AUC |
  |---|---:|
  | mean over ± 0.5 s (≈ the detector's window) | 0.57 |
  | mean over ± 2 s | 0.74 |
  | max over ± 2 s | 0.74 |

  So the "not" calls sit in a theta context wider than the detector looks at.
- Pass rates on HC's calls (`review_theta_features_HC.csv`): requiring the ± 2 s mean ≤ threshold − 2 log units raises
  the field precision from 0.80 to 0.94 but keeps only 23 / 40 field items (house 25 / 40, 0.96). The cut values were seen
  on these data, so they are not used as fitted.
- **Pre-registered sensitivity (fixed now, before any map):** *theta-quiet aSWR* = an aSWR whose ripple-site theta/delta,
  averaged over ± 2 s, is at or below the session's **NREM median** of the same ± 2 s average. The NREM median is a level
  chosen from NREM physiology, not from these calls.
- **How the maps use it.** Every map and 1-D profile is computed for aSWR (primary) and for theta-quiet aSWR. A place
  difference is reported only where both agree. It is checked against the second reader and the denoised reading
  (precision with and without the rule); if it fails there, it stays a sensitivity and nothing else changes.

**Still open from HC's reading.**
- **House "random quiet moments".** 13 / 28 house negatives were called ripple. These are possible detector misses at home.
  - If the second reader agrees, the house rate is a lower bound, which favours house > field only conservatively.
  - The field would also need checking for misses: 30 field random moments in a second sample.
- **SF09 field: 1 / 3 / 4.** Report SF09's field rows separately; drop them if the second reader agrees.

### Addendum 4a — the denoised page looked the same (the user, 2026-10-10): state of the art, two numeric checks

**Why it looked the same.**
- Panels 1–2 are dominated by the < 80 Hz part, which the denoising leaves untouched by design.
- The spectrogram is normalised per frequency to its own ± 6 s median, so a uniform drop of the EMG floor cancels out.
- The LFP-EMG panel is computed from the raw sites.
- Only panel 3 shows the change.

**State of the art** (sources in the reply of 2026-10-10):
- Liu et al. 2022, *Nat Commun* (the ripple consensus):
  - artifacts are power increases on all sites, distant ones included;
  - use a local derivation or CSD (the "difference of difference"), ICA, and exclusion of events that coincide with EMG on
    the common average;
  - a true event's spectrum has a narrow peak in the ripple band;
  - compare SPW-R-unit histograms in wake and NREM;
  - immobility.
- van Schalkwijk & Helfrich 2026, *Nat Commun*: 77 % of awake MTL ripples sit inside the 1/f noise floor (23 % in NREM).
  Benchmark every detector against matched coloured-noise surrogates per state.
- Bénar et al. 2010: filtering a sharp transient makes a false ripple; require an isolated blob in the time-frequency plane.
- Whitmore & Lin 2016: ICA removes reference and movement noise, which is 23–77 % of awake LFP variance.
- De Clercq et al. 2006: BSS-CCA for muscle artefacts in EEG.
- Navas-Olive et al. 2024 (rippl-AI): 1 / 3 / 8-channel ML detectors at 1250 Hz, robust to noise, public.

**Check 1: denoisers** (`review_denoise_compare.csv`). All methods act on > 80 Hz only and are fitted outside ± 0.25 s.
Medians, field aSWR / NREM:

| method | background ratio, field | NREM peak kept | field contrast (raw 1.44) |
|---|---:|---:|---:|
| single cortical site (current) | 0.73 | 0.98 | 1.90 |
| 8 ripple-poor sites | 0.57 | 0.93 | 2.06 |
| same-shank ripple-poor site | 0.61 | 0.95 | 1.94 |
| BSS-CCA | 0.97 | 0.99 | 1.47 (removes nothing at the CA1 site) |

- More removal costs real NREM ripple amplitude.
- No method's contrast separates HC's "ripple" from "not a ripple": AUC 0.44–0.55. HC's "not" calls are not about the
  noise level, which matches the user's account (theta).

**Check 2: raw MUA** (`review_mua_items.csv`; common median reference, 600–6000 Hz, −4.5 MAD; rate in ± 50 ms / rate at
0.4–3 s).
- Medians of the pyramidal-site ratio:

  | set | median ratio |
  |---|---:|
  | NREM SWRs | 1.78 |
  | aSWR field, called ripple | 1.85 |
  | aSWR house, called ripple | 2.90 |
  | random quiet moments | 0.16–0.60 |

  So the aSWR candidates carry a hippocampal spike burst like NREM SWRs; the random moments do not.
- Field "not a ripple" (n 6): the burst also appears on the other shanks (4.8) and the cortical sites (1.74). Field
  "ripple" items have cortical 0.00, field "unsure" (n 10) 0.00 with pyramidal 4.0. So the "unsure" (EMG) items look like
  local hippocampal events.
- Exploratory, n 8 "not": the cortical ratio separates the calls with AUC 0.68, the log pyramidal / cortical ratio with
  0.64. Per event, MUA is noisy: only 47 % of NREM SWRs reach a ratio ≥ 2.

**Proposal (not run; the user decides):**
- Reader v3 shows the consensus evidence instead of a cleaner trace:
  - the 100–250 Hz band of the ripple site, a same-shank ripple-poor site, the other shanks' ripple sites and the cortical
    site, on one µV scale;
  - the event spectrum (± 50 ms) against its background at the ripple and cortical sites;
  - the raw MUA raster of the ripple shank and the cortical sites;
  - theta over ± 2 s (kept).
- Automatic criteria, each pre-registered and validated against both readers and then a fresh sample:
  - theta-quiet (above);
  - local, not common: ripple-band and MUA rise on CA1, not on the cortical sites;
  - a narrow event-spectrum peak;
  - and the noise-floor benchmark: the production detector run on per-state, per-zone coloured-noise surrogates.
- Optional: rippl-AI as an independent second detector on the 140 items.

### Addendum 4b — EMG removal by ICA (Weiwei Chen 2023, the user's reference), 2026-10-10

**Source.**
- Chen W. (2023), dissertation, LMU Munich (Sirota lab), chapter 5 "EMG Artifacts Removing" (`Ref/Chen_Weiwei.pdf`).
- Toolbox https://github.com/YY535/EMG_removing, commit 0ee8f0d.

**Method.**
- EMG is volume-conducted from distant muscles, so along a shank its loading is flat or linear; a local event is a dipole.
- Per shank:
  1. high-EMG samples (`EMG_Cluster`);
  2. FastICA on the > 100 Hz data of those samples, then on the AR(1)-whitened wide band;
  3. the component with the highest flatness (1 / residual of an affine fit of its loading against depth) is removed
     above 30 Hz.
- It is removed only if exactly one component has flatness > 10 and one > 50 (with retries).

**Port.** `ephys/emg_ica.py`, with `--selftest`:
- synthetic: flatness 1457, residual EMG 1.4 %, ripple band kept 96 %;
- GPU FastICA in the `cv` env;
- the deviations are listed in its docstring.

**Run.** `awake_ripple_map.py emgica`: the ± 7.5-min chunk around each item, all shanks →
`<run>/emg_ica/<rid>.npz` + `emg_ica_items.csv`.

**Result** (numbers only; 100–250 Hz at the ripple site).
- The toolbox's criteria were met on the ripple's own shank in 106 / 140 items, 419 / 585 shanks. Elsewhere it removes
  nothing.
- Where it cleaned, medians against the single-site regression (Addendum 4a):

  | set | background ratio (regression) | candidate kept | contrast, raw → ICA (regression) |
  |---|---:|---:|---|
  | aSWR field | 0.62 (0.73) | 0.90 | 1.44 → 1.91 (1.90) |
  | aSWR house | 0.78 (0.84) | 0.92 | 1.76 → 2.32 (1.96) |
  | NREM SWRs | 0.87 (0.96) | 0.98 | unchanged |

  So it removes more background than the regression and keeps the NREM ripples.
- HC's "not a ripple", field (n 6): the candidate is kept (0.97) and its contrast rises to 4.1. These are local events
  rather than EMG, which matches the user (theta).
- HC's "not a ripple", house (n 2): the candidate is mostly removed (0.35), i.e. flat EMG.
- Contrast still does not separate HC's calls (AUC 0.46).

**Page.** Panel 6 shows the LFP-EMG *before* cleaning (after cleaning the cross-shank measure is ~0 by design).
https://claude.ai/artifact/UfxAaVKfaYGysubMUskEWr (private; same items and key; answers in its db `reads/<id>`). A third,
separate reading; never merged with the raw or regression pages.

### Addendum 4c — uncleaned panels, Codex review, port check (2026-10-10, before the EMG-ICA reading counts)

**What the user saw.**
- In v1 of the page, 34 / 140 panels had nothing removed on the ripple's shank, yet were titled "denoised".
- In these the noise site's shank had been cleaned while the ripple's shank had not, so the noise trace looked cleaner
  than CA1.
- The user: labelling an uncleaned panel would mislead; wait until all are cleaned; ask Codex if there is a problem.

**Codex (thread 01a112d6, text review)**:
- Do not use `always_rm` as the fallback. Keep uncertain items flagged.
- Hide the acceptance status from readers. A "not cleaned" title is a cue.
- Report accepted and forced items separately.
- Check the port against the original, including seed and retry stability.
- Explain why flatness 45 failed when the retries lower the threshold to 30.

**What was checked.**
- **The trace.** Flatness 45 fails at the first-stage gate: the high-pass ICA has ≥ 2 components > 10 ("no typical EMG").
  - The decision is **seed-dependent** near the thresholds: R007 is accepted with 1 of 3 seeds.
  - R017 is rejected with every seed (two first-stage components > 10).
  - R018 is rejected with every seed (flatness 13, a non-affine gradient).
- **Forced removal (`always_rm`) is harmful.** On those 34 it removes 37 % of the NREM SWRs' own ripple band (candidate
  kept 0.63, against 0.98 under the rule). Kept for the record in `emg_ica/`; never shown.
- **Port error found and fixed.**
  - `EMG_rm_main` passes `numOfIC = max(0.8 n, min(16, n))`, which is n for n ≤ 16.
  - The port had used `EMG_rm_long`'s own default (0.7 n), i.e. 11 instead of 16 components in the first stage.
- **Port vs the MATLAB original** (R2021b, toolbox 0ee8f0d; `matlab_check/` in the run; same EMG_thrd fed to both,
  seeds 0–2):
  - EMG_thrd itself agrees on 99 % of samples (the pair order is random).
  - R002 (SF07, 16 sites): the same decision for every seed; removed loading |cos| = 1.000; removed signal r 0.99–1.00.
  - R018: both reject.
  - R007: seed-dependent in both (MATLAB accepts with 1 of 3 seeds, the port with 0 of 3; the same flatness range 45–62).
  - So the port reproduces the original; the instability belongs to the method.

**v2 rule (fixed before any v2 reading):**
- Clean only the ripple's own shank. The noise site stays raw as the reference, panel 6 shows the raw LFP-EMG, and theta
  is below 30 Hz.
- Run three seeds (0, 1, 2). An item is **cleaned** when the toolbox's rule holds for ≥ 2 of 3; the output is that of the
  first accepting seed.
- Items that are not cleaned are left off the EMG-ICA page (judged on the raw page only) and reported separately (SF09
  above all).
- Output: `emg_ica_v2/`. v1 (`emg_ica/`, with the numOfIC error) is kept for the record.
- The readings to compare per item: raw page first (done by HC), then the cleaned page; record where judgments change.

**v2 result** (`emg_ica_v2/emg_ica_items.csv`, `page_items_accepted.json`):
- 111 / 140 cleaned.
  - Seeds agree on 107 accepted and 27 rejected; 6 borderline.
  - Not cleaned: SF09 21 / 25; every other animal 1–2.
- Shown by set: NREM 24, field 30, house 32, random 25.
- Cleaned items, medians:

  | set | background ratio | candidate kept | contrast, raw → ICA |
  |---|---:|---:|---|
  | NREM SWRs | 0.84 | 0.97 | 2.05 → 2.08 |
  | aSWR field | 0.62 | 0.89 | 1.44 → 1.92 |
  | aSWR house | 0.79 | 0.95 | 1.76 → 2.33 |

- **Page v4** of https://claude.ai/artifact/UfxAaVKfaYGysubMUskEWr shows the 111 items only, saving to `reads_v2/<id>`.
  The 26 answers the user gave on the earlier versions stay in `reads/` and are not used (wrong panels).
- SF09's field items are judged on the raw page only. SF09 needs a verified within-shank order before this method can
  clean it.

### Addendum 4d — reader HC on the cleaned page (2026-10-10; 111 / 111 answered; the user: "the removal works quite well")

Exported to `ephys/configs/awake_ripple_review_2026c/reader_HC_emgica_v2_2026-10-10.{json,csv}`.

**Calls, ripple / not / unsure (precision):**

| set | raw page, all 140 | raw page, the 111 shown | cleaned page, 111 |
|---|---|---|---|
| NREM SWR | 30/0/0 (1.00) | 24/0/0 (1.00) | 23/1/0 (0.96) |
| aSWR field | 24/6/10 (0.80) | 23/2/5 (0.92) | 30/0/0 (1.00) |
| aSWR house | 36/2/2 (0.95) | 31/1/0 (0.97) | 31/1/0 (0.97) |
| random quiet moment | 13/8/9 (0.62) | 12/5/8 | 18/7/0 |

- **Unsure resolved.** All 13 unsure became decided: 9 ripple, 4 not. Raw → cleaned changes on the 111: 87 ripple kept,
  6 not → ripple, 3 ripple → not.
- **Selection.** The 29 items not shown (21 SF09) held most of the field "not" / "unsure" calls: 1/4/5 of the 10 field
  items left out. So the field 1.00 covers SF07, SF08, SF10 and SF12 only, not the field as a whole.
- **Specificity problem.** On the cleaned page HC called **18 / 25 random quiet moments "ripple"** (12 / 25 on the raw
  page). These are moments with no detected event within ± 2 s. They lack the evidence that the detected events carry:

  | | median raw MUA, pyramidal ratio | share with a burst ≥ 2 | ripple-band contrast at the line |
  |---|---:|---:|---:|
  | random moments called "ripple" | 1.06 | 28 % | 0.89 |
  | detected events called ripple | 2.4–3.2 | 52–68 % (NREM 52 %) | 1.9–2.3 |

  So the cleaned panels (or the reading habit) make a ripple call likely wherever there is ripple-band activity. The
  reader's "ripple" is not specific there, and precision on the detected events is inflated by it.
- **Reading.**
  - The pre-registered gate (precision ≥ 0.7) passes on both pages.
  - But the cleaned-page precision is not evidence by itself, because the negatives are also called "ripple" 72 % of the
    time.
  - The independent support is the MUA: detected awake events carry a spike burst as often as NREM SWRs (field 60 %,
    house 68 %, NREM 52 %); random moments do not (14–28 %).

**Proposal (not adopted; the user decides).**
- Use the reader together with the negatives: report the call rate at detected events against the call rate at random
  moments, a likelihood ratio, rather than precision alone.
- Add MUA as the objective co-criterion.
- Wait for the second reader (raw page) before the gate is final.
- Ask the readers what a "ripple" at a random moment referred to (at the line, or near it).
- Checked: only 4 / 30 random moments have any detector candidate (even an excluded one) within 0.5 s. So the "ripple"
  calls at random moments are not explained by excluded candidates.

## Amendment 5 — a strict blind re-read by HC (the user offered, 2026-10-10; fixed before the page is built)

**Items.**
- The 111 cleaned items (EMG-ICA v2), re-rendered with **new ids (T###)** and a **new random order**. No old id appears in
  any panel.
- Plus **30 fresh random quiet moments**: the same draw rule (a non-locomotor, detectable wake second with no kept event
  within [−2, +3) s), a new seed, ≥ 10 s from every old item. Only those the EMG-ICA v2 rule cleans (≥ 2 of 3 seeds),
  drawn until 30.
- Panels are as on the cleaned page, plus a light band marking ± 50 ms around the line in panels 1–3.

**Rule shown to the reader.** "Ripple" only when all of these hold:
1. a burst of ≥ 3 cycles at 100–250 Hz centred within ± 50 ms of the line (panel 3);
2. clearly larger than every other burst in the ± 0.5 s view;
3. on the ripple site and its neighbours, not on the grey noise site;
4. not part of a train repeating with theta.

Otherwise "not a ripple"; "unsure" only when the panel is unreadable.

**Analysis (fixed now).**
- Per set, the strict call rate $p_s$ (ripple / all answered; unsure counted as not).
- **Sensitivity anchor** $s$ = $p$ on the NREM SWRs. **False-call anchor** $\alpha$ = $p$ on the random moments: fresh
  and old pooled; fresh alone as a check.
- Estimated true-ripple share of a set: $\hat\pi = (p - \alpha) / (s - \alpha)$, clipped to [0, 1], with a bootstrap
  over items.
- Reported for aSWR field and aSWR house.
- **The gate becomes:** $\hat\pi \ge 0.7$ in each stratum and $s - \alpha \ge 0.4$, i.e. the reading discriminates. If
  $s - \alpha < 0.4$, the human reading cannot gate and the decision falls to the MUA co-criterion (detected events vs
  random moments, pre-registered as the burst share at ≥ 2).
- Also reported:
  - strict vs the earlier cleaned reading per item;
  - the MUA ratio by strict call;
  - the 29 non-cleanable items (raw page only) and SF09, separately.

**Built (2026-10-10).**
- 141 panels: the 111 cleaned items plus 30 fresh random moments. The fresh ones are the first 30 of 60 draws that the
  rule cleaned (46 / 60 were cleaned; none from SF09).
- By set: field 30, house 32, NREM 24, random old 25, random fresh 30.
- Key `strict/review_key_strict_SEALED.csv` (T### → source item); windows in `strict/emg_ica/`; the draw scripts sit in
  `strict/`.
- Page https://claude.ai/artifact/ERbLn5wQSmZX4M2JB361jT (private; answers at `reads/<id>`).

**Result** (HC, 141 / 141; `ephys/configs/awake_ripple_review_2026c/reader_HC_strict_2026-10-10.{json,csv}`).
- The user: "unsure" and "not" mean almost the same here, i.e. no ripple seen. So unsure counts as not, as fixed above.

  | set | ripple / not / unsure | p |
  |---|---|---:|
  | NREM SWR | 21 / 0 / 3 | 0.88 = s |
  | aSWR field | 25 / 0 / 5 | 0.83 |
  | aSWR house | 29 / 0 / 3 | 0.91 |
  | random, fresh | 5 / 3 / 22 | 0.17 |
  | random, old | 5 / 2 / 18 | 0.20 |

- **Discrimination.** s − α = 0.88 − 0.18 = 0.69 ≥ 0.4, so the strict reading discriminates. The fresh controls alone
  give α 0.17, i.e. no memory effect.
- **Estimated true-ripple share** (bootstrap 95 %):
  - field π̂ = 0.94 [0.69, 1.00];
  - house π̂ = 1.00 [0.83, 1.00].
- **Gate: PASS for both strata** (point estimates ≥ 0.7). The field interval reaches 0.69.
- **Reader and MUA now agree** (old items):

  | strict call | median MUA pyramidal ratio | share with a burst ≥ 2 |
  |---|---:|---:|
  | field, ripple | 3.20 | 68 % |
  | field, unsure | 0.40 | 20 % |
  | house, ripple | 3.22 | 66 % |
  | random, ripple (n 5) | 2.99 | 60 % |
  | random, unsure | 0.00 | 17 % |

  The 5 random moments called ripple carry a spike burst, so they are probably ripples the detector missed (a recall
  question, not precision).
- Per animal, field: SF07 8/8, SF10 7/7, SF12 6/7, **SF08 4/8**.
  - SF09 is not covered: it cannot be cleaned, and on the raw page it reads 1 / 3 / 4.
- Cleaned page → strict, the same 111: 79 ripple kept; 22 ripple → unsure; 7 not → unsure. So the strict rule moved the
  borderline calls out, as intended.

**The user's display point: "maybe the LFP gain is too small".**
- Panel 3 is autoscaled to its own ± 0.5 s maximum. A panel without a ripple therefore shows its noise at full height,
  and a real one does not stand out by absolute size.
- Panel 1 is scaled for the slow waves, so ripples are barely visible there.
- For any later reading: a fixed µV scale per animal (e.g. set by its NREM SWR median ripple amplitude) for panel 3, plus
  a 100–250 Hz stack of the sites on that scale. Not needed for this gate.

**Consequence for Phase 2 (proposal):**
- aSWR valid in the houses, all cleanable animals.
- In the field, valid for SF07, SF10 and SF12. SF08 is flagged (half doubtful). SF09's field is dropped (no reading or
  cleaning supports it).
- Theta-quiet aSWR stays the pre-registered sensitivity.
- The second reader (raw page) is a cross-check (κ) when she finishes.

## Amendment 6 — Phase 2, fixed before any map (2026-10-10; the user: "SF09 用，标注上就可以。做地图吧")

**Animals.**
- All six get descriptive maps. Every map and table carries its animal's note:
  - SF09: field not validated (EMG-ICA could not clean its shank; raw reading 1 / 3 / 4);
  - SF08: strict field reading 4 / 8;
  - SF11: houses only (0.01 h of field time);
  - SF07: field descriptive (35 field events).
- **Inference screen (48-in grid):** ≥ 300 field aSWR and ≥ 10 field bins with ≥ 60 s. It replaces the 24-in screen of
  Phase 0.

**Places.**
- Field bins: 48 in on the WISER frame, anchored at the P0 position of pole A0. No cropping.
- house_1 / house_2: the membership zones, each its own place.
- Seconds of unknown zone are left out.
- 1-D rings: house = ring 0. Field distance to the nearest rest-cluster centre ((417.7, 716.9), (621.2, 732.6)) in rings
  0–24, 24–48, 48–96, 96–144, 144–192 and > 192 in. A ring's centre is the mean distance of its seconds.

**Bout.** A maximal run of consecutive non-locomotor detectable wake seconds within a record.

**Null (primary): the bout swap.**
- Strata: night × probe block × duration class (log classes of ratio 1.25) × clock-hour class.
- Within each stratum, the bouts' event sequences are permuted. An event's offset is rescaled to the recipient's length
  (keeping counts and relative timing).
- 1000 permutations.
- Bouts alone in their stratum keep their own events. The share of bouts that can swap is reported.

**Statistics, per animal, with the same functions on the observed and permuted events.**
- **T1:** Skaggs spatial information of the field map within each block (bins ≥ 60 s), combined across blocks as the
  occupancy-weighted mean. Effect = observed − null median; p one-sided.
- **T2:** leave-one-night-out r. Night n's field rates against the other nights', over bins ≥ 60 s in both, if ≥ 3 such
  bins; the mean over nights weighted by bins. p one-sided.
- **T3:** the house vs field Mantel–Haenszel rate ratio over blocks. p two-sided.
- **1-D:** per ring, O / E against the block's field rate. The slope of log((O + 0.5) / E) on log ring-centre distance
  over the field rings, weighted by occupancy minutes. p two-sided.
- Holm across the animals in inference, separately for T1, T2, T3 and the slope.
- **Bout-level Poisson GLM** (description): units are bout pieces split at house / field.
  - Model: events ~ house + log bout length + clock harmonics + night + block, offset log piece length, cluster SE by
    night.
  - A field-only fit with log distance.

**Sensitivities, same pipeline.**
- Leave out:
  - qc_i1 seconds;
  - anchors ≤ 6;
  - BLE passes ± 15 min;
  - rain nights 09-03 and 09-09;
  - SF08 before 09-06 19:43.
- Theta-quiet aSWR (Amendment 4): a second pass that needs the ± 2 s theta / delta series per session.
- Descriptive maps show events / min per bin (≥ 60 s); unsmoothed; houses drawn as circles; landmarks as reference marks.

## Output

- `ephys/awake_ripple_map.py`: `phase0`, `review`, `phase2`, `phase3`, `--selftest`.
- Bulk: `$OUT_ROOT/2026c/awake_ripple_map_<ts>/`.
- Report: `results/2026c/ephys_spikes/reports/ephys_spikes_awake_ripple_map_2026c.md`.
- Change log: `change_log/2026-10-10-awake-ripple-map.md`.
