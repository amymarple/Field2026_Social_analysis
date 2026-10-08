# In-house microphones: house assignment and sounds around wakes — PILOT (cohort 2026c)

Plan: implementation_plan/2026-10-07-sleep-internal-schedule.md §4 D. Driver `ephys/mic_wake_pilot.py` (commit 4f83871+dirty); bulk `D:\Field2026_analysis_out\2026c\mic_wake_pilot_20261007_2316`; audio levels: storage `3rd_rat/analysis/audio_levels/` (VERIFY PASS).

**Description only; nothing here labels a sound as external or animal-made. The user's listening check is the validation.**

## D2 Which mic is in which house

Spearman correlation of the 20–40 kHz level with the summed head-IMU movement of the animals in each house, per date.

| ('date', '') | ('MIC01', 'house_1') | ('MIC01', 'house_2') | ('MIC02', 'house_1') | ('MIC02', 'house_2') |
|---|---|---|---|---|
| 20260831 | 0.06 | 0.54 | 0.43 | 0.22 |
| 20260901 | 0.01 | 0.52 | -0.11 | -0.17 |
| 20260902 | 0.31 | 0.58 | 0.18 | -0.12 |
| 20260903 | 0.2 | 0.73 | -0.15 | -0.21 |
| 20260904 | 0.01 | 0.63 | -0.2 | -0.27 |
| 20260905 | 0.11 | 0.68 | 0.21 | -0.07 |
| 20260906 | -0.11 | 0.68 | 0.46 | 0.1 |
| 20260907 | 0.16 | 0.74 | 0.16 | -0.12 |
| 20260908 | 0.1 | 0.7 | 0.07 | -0.21 |
| 20260909 | 0.03 | 0.73 | 0.38 | 0.14 |
| 20260910 | -0.06 | 0.62 | 0.3 | -0.4 |
| 20260911 | -0.03 | 0.66 | 0.33 | 0.19 |

Reading: MIC01 follows house_2 every day (0.52–0.74) → MIC01 = house_2. MIC02 follows house_1 only on some days (0.33–0.46 on 08-31, 09-06, 09-09, 09-11; negative on 09-01, 09-03, 09-04) and is flat above 4 kHz → MIC02 = house_1 is plausible, but MIC02 is a weak sensor.

## D3 Cues before wakes from NREM

Event = the animal's own head-IMU movement onset; chance = the same check 120 s earlier.

| cue | before_movement_onset | chance_reference_m_minus_120s | n |
|---|---|---|---|
| housemate moved in the 30 s before | 0.408 | 0.311 | 2980 |
| own-house mic transient >= 10 dB (b0-b2) in the 10 s before | 0.529 | 0.44 | 2978 |
| transient on both house mics | 0.206 | 0.161 | 2978 |
| own-house transient + outdoor (CH01/CH02) transient | 0.312 | 0.266 | 2978 |
| outdoor transient alone (either camera) | 0.59 | 0.573 | 2966 |

Candidate classes (first match wins):

| house | housemate_first | none_observed | sound_first_common | sound_first_outdoor | sound_first_own_only |
|---|---|---|---|---|---|
| house_1 | 208 | 266 | 25 | 131 | 29 |
| house_2 | 1007 | 718 | 71 | 324 | 201 |

Reading: every cue is somewhat more frequent before a wake than 2 min earlier, but the 10-dB transient rule fires in 44 % of sleeping 10-s windows (house mic) and 57 % (outdoor cameras: birds, wind, rain), so it is not specific. A stricter, validated rule needs the user's listening check of sampled events (`d3_listening_sample.csv` in the run folder).
