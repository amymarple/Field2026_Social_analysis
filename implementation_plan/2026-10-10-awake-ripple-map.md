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
  - This is a records gap. The positions are asked from the user before any hotspot is read.
- **Handling masks to add:**
  - the **09-01 ≈ 00:34 midnight round** (all six stopped / restarted; a catch is likely). It is missing from
    `cv/configs/cohort3_handling_windows.json` and `cohort3_lid_events.json`; mask ± 30 min.
  - the 08-31 11:00–18:00 troubleshooting window (already in the handling windows).
- **Night BLE passes:** the operator may have been at the paddock edge:
  - 09-03 00:16–00:25, 09-06 00:21–00:36, 09-06 23:43–23:57, 09-07 23:14–23:33, 09-09 03:17–03:27;
  - knee passes 09-07 06:41–06:49, 09-10 06:04–06:12.
  - Sensitivity: drop ± 15 min around each.
- **No other refuge** is recorded. Nest material was present (09-08, 09-10), place not stated.

## Output

- `ephys/awake_ripple_map.py`: `phase0`, `review`, `phase2`, `phase3`, `--selftest`.
- Bulk: `$OUT_ROOT/2026c/awake_ripple_map_<ts>/`.
- Report: `results/2026c/ephys_spikes/reports/ephys_spikes_awake_ripple_map_2026c.md`.
- Change log: `change_log/2026-10-10-awake-ripple-map.md`.
