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

## Output

- `ephys/awake_ripple_map.py`: `phase0`, `review`, `phase2`, `phase3`, `--selftest`.
- Bulk: `$OUT_ROOT/2026c/awake_ripple_map_<ts>/`.
- Report: `results/2026c/ephys_spikes/reports/ephys_spikes_awake_ripple_map_2026c.md`.
- Change log: `change_log/2026-10-10-awake-ripple-map.md`.
