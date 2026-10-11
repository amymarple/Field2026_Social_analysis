# In-box cameras CH07 / CH08, phase 0: colour segments, WISER box events, in-house positions, identity click page (cohort `2026c`)

Plan `implementation_plan/2026-10-10-inbox-ch0708-wiser-identity-p0.md` (pre-registered 2026-10-10, approved by the user; amendments dated there). Run `D:/Field2026_analysis_out/2026c/cv_field_inbox_p0_20261010_1702`; generated 2026-10-10 22:50; code `d743a4adf54625118421e9f698954c9ae3393495+dirty`. Drivers `cv/cv_field/inbox_p0.py` (A, B) and `cv/cv_field/inbox_identity_page.py` (C). The agent never looked at a frame; every number below is computed. Scope 2026-08-30 19:00 → 2026-09-11 19:40 (before the five females).

## Summary

- **A. Colour segments**: threshold thr = **1.179** (largest log-chroma gap 0.5324 → 2.61, 0.69 decades; next largest gap 0.65 decades) over 243630 I-frames; **22 colour segments** CH07 2026-09-09: 1, CH07 2026-09-10: 13, CH07 2026-09-11: 7, CH08 2026-09-10: 1; 17 match a colour-log row, 5 unmatched; 2 log rows with an operator time have no segment. Controls: 0 colour I-frames in 12 control hours.
- **B. 09-05 ground truth: PASS** — WISER entry order SF09, SF07, SF11, SF10, SF12 (operator SF09, SF07, SF11, SF10, SF12); 12 of 12 events matched, |Δt| median 2 s, max 4 s (Δt = WISER − operator from -4 to -1 s). Literal mask rule: FAIL; raw fixes instead of the track: PASS.
- **B. Box events**: 6254 events (primary rule) for SF07–SF12, 391 near a handling mask; 67134 in-house animal-minutes; per second every animal in the paddock was tagged and located 83.8 % of the scope (78.7 % before 09-07 06:10:45, 94.0 % after SF11 was taken out at 08:20; corrected 2026-10-11 — the 10-10 version gave 48.9 % by counting SF11 as present but untagged to the scope end).
- **B. Camera ↔ house** (per-minute frame-difference energy vs per-minute WISER events, 09-09 → 09-11): CH07–house_1 r -0.02; CH07–house_2 r 0.17; CH08–house_1 r 0.29; CH08–house_2 r 0.08 (expected pairing CH07–house_2, CH08–house_1; no decision taken from it).
- **C. Click page**: `D:/Field2026_analysis_out/2026c/cv_field_inbox_p0_20261010_1702/identity_page/index.html` — 22 segments, 66 frames, page check PASS (missing paths 0, network URLs 0, pre-filled identities 0). Exports go to `cv/configs/inbox_identity_2026c/`.

## A. Colour segments (CH07 / CH08, 09-09 → 09-11 19:40)

I-frame chroma histogram: [0,0.0001): 242288, [0.0001,0.001): 1, [0.001,0.01): 0, [0.01,0.1): 3, [0.1,1): 3, [1,3): 1, [3,10): 3, [10,30): 1232, [30,100): 99, [100,1000): 0. CH07: 121821 I-frames, 1052 colour, max IR chroma 0.3564, min colour chroma 2.61; CH08: 121809 I-frames, 283 colour, max IR chroma 0.5324, min colour chroma 18.844.

**Threshold (plan amendment 6, after results).** The pre-registered rule (floor 10⁻⁴) gave thr = 0.003035 (largest gap 0.00081 → 0.01137, 1.15 decades — inside the IR cluster): 1341 colour I-frames, 28 colour runs, 5 colour I-frames in the control hours. The isolated I-frames with 10⁻⁴ ≤ c < thr (IR by the amended rule; rounding-level chroma, two of them on CH08 at 23:00 / 23:39, when colour is impossible):

| camera | time | chroma | grey_mean |
|---|---|---|---|
| CH07 | 2026-09-09 12:53:12.814 | 0.01137 | 121.6 |
| CH07 | 2026-09-10 17:10:14.953 | 0.012 | 99.5 |
| CH07 | 2026-09-11 13:02:08.986 | 0.3564 | 108.5 |
| CH08 | 2026-09-09 06:21:12.915 | 0.5324 | 111.3 |
| CH08 | 2026-09-09 23:00:08.013 | 0.04563 | 111.9 |
| CH08 | 2026-09-10 23:39:07.837 | 0.1412 | 112.1 |
| CH08 | 2026-09-11 08:32:45.919 | 0.00081 | 100.3 |


With the floor at 0.01 the same rule gives thr = 1.179; no I-frame lies in (0.5324, 2.61), so every threshold in that interval gives the identical classification. The pre-registered outputs are kept in the run as `colour_segments_prereg_thr.csv`, `colour_log_rows_prereg_thr.csv`, `control_hours_prereg_thr.csv`, `colour_threshold_prereg.json`.

| segment_id | ON–OFF | duration_s | n_colour_keyframes | median_chroma | log | Δ / Δ_corr (s) | lid | flags |
|---|---|---|---|---|---|---|---|---|
| CH07_20260909_191025 | 09-09 19:10:25.843 – 19:10:39.330 | 13.49 | 7 | 14.69 | 1: test flash (op_on) | -34 / +1 |  | - |
| CH07_20260910_071415 | 09-10 07:14:15.136 – 07:15:17.123 | 61.99 | 30 | 27.46 | 2: AM placement (window) | - | yes | - |
| CH07_20260910_083742 | 09-10 08:37:42.865 – 08:55:39.877 | 1077.01 | 539 | 23.77 | 2: AM placement (window) | - | yes | - |
| CH07_20260910_091147 | 09-10 09:11:47.741 – 09:12:07.850 | 20.11 | 10 | 22.60 | 3: extra colour->IR transition (op_off) | +68 / +103 |  | - |
| CH07_20260910_122703 | 09-10 12:27:03.351 – 12:27:26.331 | 22.98 | 12 | 25.53 | 6: flash (midday) pile #1 (op_on) | +3 / +38 |  | - |
| CH07_20260910_125142 | 09-10 12:51:42.560 – 12:51:55.587 | 13.03 | 7 | 21.94 | 7: flash (midday) pile #2 (op_on) | -17 / +18 |  | - |
| CH07_20260910_135131 | 09-10 13:51:31.693 – 13:51:53.044 | 21.35 | 10 | 24.18 | 8: flash (afternoon) pile #3 (op_on) | -28 / +7 |  | - |
| CH07_20260910_140227 | 09-10 14:02:27.943 – 14:02:39.551 | 11.61 | 6 | 23.57 | **unmatched** | - |  | - |
| CH07_20260910_141613 | 09-10 14:16:13.253 – 14:16:35.329 | 22.08 | 11 | 23.84 | **unmatched** | - |  | - |
| CH07_20260910_143243 | 09-10 14:32:43.385 – 14:32:53.071 | 9.69 | 5 | 22.56 | 10: flash 14:33 pile #5 (op_on) | -17 / +18 |  | - |
| CH07_20260910_152307 | 09-10 15:23:07.475 – 15:23:20.040 | 12.56 | 6 | 19.73 | 11: flash 15:23 pile #6 (op_on) | +7 / +42 |  | - |
| CH07_20260910_163056 | 09-10 16:30:56.635 – 16:31:12.636 | 16.00 | 8 | 22.20 | 12: flash 16:30 pile #7 (op_on) | +57 / +92 |  | - |
| CH07_20260910_175935 | 09-10 17:59:35.098 – 17:59:41.759 | 6.66 | 3 | 22.60 | **unmatched** | - |  | - |
| CH07_20260910_195004 | 09-10 19:50:04.007 – 19:50:11.501 | 7.50 | 4 | 3.11 | 14: PM placement tried, too dark (IR only) (op_on) | +4 / +39 | yes | - |
| CH07_20260911_092822 | 09-11 09:28:22.239 – 09:32:23.949 | 241.71 | 122 | 23.35 | **unmatched** | - | yes | - |
| CH07_20260911_095409 | 09-11 09:54:09.256 – 10:01:02.657 | 413.40 | 208 | 25.29 | 16: colour segment ~10:00 (op_on) | -351 / -316 |  | - |
| CH07_20260911_140955 | 09-11 14:09:55.465 – 14:10:23.053 | 27.59 | 14 | 24.57 | 19: flash 14:10 (op_on) | -5 / +30 |  | - |
| CH07_20260911_141758 | 09-11 14:17:58.864 – 14:18:48.765 | 49.90 | 26 | 24.08 | **unmatched** | - |  | - |
| CH07_20260911_144345 | 09-11 14:43:45.415 – 14:43:56.507 | 11.09 | 5 | 23.12 | 20: flash 14:44 (op_on) | -15 / +20 |  | - |
| CH07_20260911_145024 | 09-11 14:50:24.203 – 14:50:34.350 | 10.15 | 5 | 24.78 | 21: flash 14:50 (op_on) | +24 / +59 |  | - |
| CH07_20260911_182803 | 09-11 18:28:03.610 – 18:28:31.158 | 27.55 | 14 | 22.75 | 23: colour 18:29 (flash or PM placement, tbc) (op_on) | -56 / -21 | yes | - |
| CH08_20260910_084548 | 09-10 08:45:48.761 – 08:55:12.909 | 564.15 | 283 | 21.00 | 2: AM placement (window) | - |  | - |

Unmatched segments and the nearest timed log row of the same date (any camera): CH07_20260910_140227 (11.6 s): nearest row 9 (flash (afternoon) pile #4, CH07/CH08 (tbc), 14:08) 5.3 min away; CH07_20260910_141613 (22.1 s): nearest row 9 (flash (afternoon) pile #4, CH07/CH08 (tbc), 14:08) 8.2 min away; CH07_20260910_175935 (6.7 s): nearest row 12 (flash 16:30 pile #7, CH07, 16:30) 89.6 min away; CH07_20260911_092822 (241.7 s, in a lid event): nearest row 15 (colour segment ~09:40, CH07/CH08 (tbc), 09:40) 7.6 min away; CH07_20260911_141758 (49.9 s): nearest row 19 (flash 14:10, CH07, 14:10) 8.0 min away.


The colour log's rows with the segments they match (this fills the log's empty "video" column here; the recording repo is not edited):

| row | date | kind | cams | op | n_segments | video_on_off | row_without_segment |
|---|---|---|---|---|---|---|---|
| 1 | 2026-09-09 | test flash | CH07 | 19:11 / ~19:11  | 1 | 19:10:25.843-19:10:39.330 (13.5 s) | False |
| 2 | 2026-09-10 | AM placement | CH07+CH08 |  /  07:17-08:40 | 3 | 07:14:15.136-07:15:17.123 (62.0 s); 08:37:42.865-08:55:39.877 (1077.0 s); 08:45:48.761-08:55:12.909 (564.1 s) | False |
| 3 | 2026-09-10 | extra colour->IR transition | CH07/CH08 (tbc) |  / 09:11  | 1 | 09:11:47.741-09:12:07.850 (20.1 s) | False |
| 4 | 2026-09-10 | flash 10:00 (planned, no note) | CH07, CH08 |  /  10:00 | 0 | - | False |
| 5 | 2026-09-10 | flash 11:30 (planned, no note) | CH07, CH08 |  /  11:30 | 0 | - | False |
| 6 | 2026-09-10 | flash (midday) pile #1 | CH07 | 12:27 / ~12:27:20  | 1 | 12:27:03.351-12:27:26.331 (23.0 s) | False |
| 7 | 2026-09-10 | flash (midday) pile #2 | CH07/CH08 (tbc) | 12:52 / ~12:52:08  | 1 | 12:51:42.560-12:51:55.587 (13.0 s) | False |
| 8 | 2026-09-10 | flash (afternoon) pile #3 | CH07/CH08 (tbc) | 13:52 / ~13:52:08  | 1 | 13:51:31.693-13:51:53.044 (21.4 s) | False |
| 9 | 2026-09-10 | flash (afternoon) pile #4 | CH07/CH08 (tbc) | 14:08 / ~14:08:08  | 0 | - | True |
| 10 | 2026-09-10 | flash 14:33 pile #5 | CH07 | 14:33 / ~14:33:08  | 1 | 14:32:43.385-14:32:53.071 (9.7 s) | False |
| 11 | 2026-09-10 | flash 15:23 pile #6 | CH07 | 15:23 / ~15:23:08  | 1 | 15:23:07.475-15:23:20.040 (12.6 s) | False |
| 12 | 2026-09-10 | flash 16:30 pile #7 | CH07 | 16:30 / ~16:30:08  | 1 | 16:30:56.635-16:31:12.636 (16.0 s) | False |
| 13 | 2026-09-10 | flash 17:30 not done | - |  /   | 0 | - | False |
| 14 | 2026-09-10 | PM placement tried, too dark (IR only) | CH07+CH08 | 19:50 /   | 1 | 19:50:04.007-19:50:11.501 (7.5 s) | False |
| 15 | 2026-09-11 | colour segment ~09:40 | CH07/CH08 (tbc) | 09:40 /   | 0 | - | True |
| 16 | 2026-09-11 | colour segment ~10:00 | CH07/CH08 (tbc) | 10:00 /   | 1 | 09:54:09.256-10:01:02.657 (413.4 s) | False |
| 17 | 2026-09-11 | flash 11:30 (planned, no note) | CH07, CH08 |  /  11:30 | 0 | - | False |
| 18 | 2026-09-11 | flash 13:00 (planned, no note) | CH07, CH08 |  /  13:00 | 0 | - | False |
| 19 | 2026-09-11 | flash 14:10 | CH07 | 14:10 / ~14:10:08  | 1 | 14:09:55.465-14:10:23.053 (27.6 s) | False |
| 20 | 2026-09-11 | flash 14:44 | CH07 | 14:44 / ~14:44:08  | 1 | 14:43:45.415-14:43:56.507 (11.1 s) | False |
| 21 | 2026-09-11 | flash 14:50 | CH07 | 14:50 / ~14:50:08  | 1 | 14:50:24.203-14:50:34.350 (10.1 s) | False |
| 22 | 2026-09-11 | flash 16:00 not done | - |  /   | 0 | - | False |
| 23 | 2026-09-11 | colour 18:29 (flash or PM placement, tbc) | CH07/CH08 (tbc) | 18:29 /   | 1 | 18:28:03.610-18:28:31.158 (27.5 s) | False |


Control hours (the threshold applied to hours before any colour insert existed):

| camera | file | n_keyframes | n_colour | max_chroma |
|---|---|---|---|---|
| CH07 | CH07_2026-09-01_08-00-01_to_09-00-00.mp4 | 1800 | 0 | 0.03382 |
| CH07 | CH07_2026-09-01_13-00-01_to_14-00-01.mp4 | 1799 | 0 | 0 |
| CH07 | CH07_2026-09-02_11-00-01_to_12-00-01.mp4 | 1800 | 0 | 0 |
| CH07 | CH07_2026-09-02_16-00-00_to_17-00-00.mp4 | 1800 | 0 | 0 |
| CH07 | CH07_2026-09-06_09-00-01_to_10-00-01.mp4 | 1800 | 0 | 0 |
| CH07 | CH07_2026-09-06_13-00-00.mp4 | 1796 | 0 | 0 |
| CH08 | CH08_2026-09-01_08-00-01_to_09-00-01.mp4 | 1801 | 0 | 0.03181 |
| CH08 | CH08_2026-09-01_12-00-01_to_13-00-00.mp4 | 1800 | 0 | 0 |
| CH08 | CH08_2026-09-02_11-00-00_to_12-00-00.mp4 | 1800 | 0 | 0 |
| CH08 | CH08_2026-09-02_12-00-00_to_13-00-02.mp4 | 1801 | 0 | 0 |
| CH08 | CH08_2026-09-08_08-00-01_to_09-00-01.mp4 | 1800 | 0 | 0 |
| CH08 | CH08_2026-09-08_11-00-00_to_12-00-00.mp4 | 1800 | 0 | 0 |


## B. WISER box events (operator parameters: house rectangle + 15 in, 6-s smoothing, 20-s minimum dwell)

Default tracks (`wiser/src/default_tracks.py`, V3 / B2) of SF07–SF12, 08-30 19:00 → 09-11 19:40. Fix rule: valid & ~m_off_animal & ~m_tag_validity (m_handling, m_silence, m_adc_lane kept, carried as flags; amendment 1). Events per animal × house × kind:

| animal | house | enter | exit |
|---|---|---|---|
| SF07 | house_1 | 165 | 165 |
| SF07 | house_2 | 439 | 439 |
| SF08 | house_1 | 193 | 192 |
| SF08 | house_2 | 292 | 293 |
| SF09 | house_1 | 225 | 224 |
| SF09 | house_2 | 366 | 367 |
| SF10 | house_1 | 217 | 217 |
| SF10 | house_2 | 402 | 401 |
| SF11 | house_1 | 109 | 109 |
| SF11 | house_2 | 218 | 218 |
| SF12 | house_1 | 198 | 198 |
| SF12 | house_2 | 304 | 303 |


5813 of 6254 events fall between 19:00 and 06:00. 49 events cross an unknown stretch (time precision = that stretch). `new_state_run_s` median 192 s (p05 25 s). Sensitivities in `box_events_sensitivity.csv.gz`: literal mask rule 5840 events, raw fixes instead of the track 6256. SF12's second tag (08-31) agrees with SF12's primary tag on 57 % of 4503 jointly known seconds (the second tag was sporadic).

### 09-05 ground-truth check (plan B2 / B5)

| animal | house | kind | gt_time | wiser_time | delta_s | within_30s |
|---|---|---|---|---|---|---|
| SF07 | house_2 | exit | 2026-09-05 08:47:08 | 2026-09-05 08:47:05 | -3 | True |
| SF08 | house_2 | exit | 2026-09-05 08:47:08 | 2026-09-05 08:47:06 | -2 | True |
| SF09 | house_2 | exit | 2026-09-05 08:47:08 | 2026-09-05 08:47:07 | -1 | True |
| SF10 | house_2 | exit | 2026-09-05 08:47:08 | 2026-09-05 08:47:07 | -1 | True |
| SF11 | house_2 | exit | 2026-09-05 08:47:08 | 2026-09-05 08:47:07 | -1 | True |
| SF12 | house_2 | exit | 2026-09-05 08:47:08 | 2026-09-05 08:47:07 | -1 | True |
| SF09 | house_2 | enter | 2026-09-05 09:49:49 | 2026-09-05 09:49:45 | -4 | True |
| SF07 | house_2 | enter | 2026-09-05 09:49:51 | 2026-09-05 09:49:49 | -2 | True |
| SF11 | house_2 | enter | 2026-09-05 09:49:58 | 2026-09-05 09:49:56 | -2 | True |
| SF10 | house_2 | enter | 2026-09-05 09:50:01 | 2026-09-05 09:49:59 | -2 | True |
| SF12 | house_2 | enter | 2026-09-05 09:50:15 | 2026-09-05 09:50:12 | -3 | True |
| SF08 | house_1 | enter | 2026-09-05 09:50:13 | 2026-09-05 09:50:11 | -2 | True |


**Verdict: PASS** (pass if the five house_2 entries come in the operator's order and every one of the 12 events is within 30 s). Sensitivities: literal rule FAIL (2 of 12 matched within ± 30 min — `m_handling` covers the round 08:40:00–09:49:59, so the literal rule drops every fix of that window and the exits and most entries vanish; that is why amendment 1 keeps them), raw fixes PASS (max |Δt| 3 s).

### In-house positions (house frame, inches)

67134 animal-minutes; per house the median minute position (along, across) and the share of minutes whose mean lies in the body footprint:

| animal | house | minutes | along_median | across_median | se_median | still_share_median | in_footprint |
|---|---|---|---|---|---|---|---|
| SF07 | house_1 | 1124 | -5.6 | -2.2 | 0.38 | 0.00 | 0.73 |
| SF07 | house_2 | 11270 | +6.3 | +1.3 | 0.33 | 0.90 | 0.79 |
| SF08 | house_1 | 4571 | -6.6 | -0.8 | 0.35 | 0.92 | 0.75 |
| SF08 | house_2 | 7310 | +7.8 | -0.9 | 0.33 | 0.90 | 0.79 |
| SF09 | house_1 | 1021 | -5.1 | -0.1 | 0.40 | 0.00 | 0.77 |
| SF09 | house_2 | 10669 | +7.8 | +1.6 | 0.33 | 0.94 | 0.75 |
| SF10 | house_1 | 3895 | -11.4 | -4.0 | 0.35 | 0.93 | 0.65 |
| SF10 | house_2 | 8135 | +6.9 | -0.1 | 0.34 | 0.90 | 0.81 |
| SF11 | house_1 | 612 | -6.9 | -1.3 | 0.36 | 0.00 | 0.84 |
| SF11 | house_2 | 6768 | +4.8 | +4.3 | 0.37 | 0.92 | 0.75 |
| SF12 | house_1 | 4961 | -6.8 | -2.5 | 0.33 | 0.95 | 0.73 |
| SF12 | house_2 | 6798 | +5.5 | -0.2 | 0.32 | 0.83 | 0.82 |


### Camera ↔ house check (plan B4; reported, not decided)

| subset | camera | house | expected_pair | n_minutes | n_events | pearson_r | spearman_rho | p_circular_shift | mean_energy_event_min | mean_energy_other_min |
|---|---|---|---|---|---|---|---|---|---|---|
| all minutes | CH07 | house_1 | False | 4032 | 635 | -0.022 | -0.046 | 0.757 | 1.68 | 1.75 |
| all minutes | CH07 | house_2 | True | 4032 | 1045 | +0.175 | +0.164 | 0.000 | 2.21 | 1.65 |
| all minutes | CH08 | house_1 | True | 4051 | 639 | +0.293 | +0.244 | 0.000 | 1.59 | 0.95 |
| all minutes | CH08 | house_2 | False | 4051 | 1054 | +0.078 | -0.023 | 0.001 | 1.18 | 0.99 |
| outside lid events (+-5 min) | CH07 | house_1 | False | 3548 | 632 | -0.016 | -0.044 | 0.636 | 1.67 | 1.71 |
| outside lid events (+-5 min) | CH07 | house_2 | True | 3548 | 975 | +0.180 | +0.185 | 0.000 | 2.14 | 1.60 |
| outside lid events (+-5 min) | CH08 | house_1 | True | 3557 | 634 | +0.294 | +0.248 | 0.000 | 1.55 | 0.97 |
| outside lid events (+-5 min) | CH08 | house_2 | False | 3557 | 977 | +0.051 | -0.034 | 0.060 | 1.16 | 1.01 |


## C. Identity click page

`D:/Field2026_analysis_out/2026c/cv_field_inbox_p0_20261010_1702/identity_page/index.html` (open from disk; self-contained, no network). One entry per colour segment (22): the colour frame at the segment middle and IR frames at +6 s / +15 s after OFF (full resolution, JPEG quality 95, upright as recorded), the WISER roster of the camera's house with the pre-flash minute positions drawn as a top view (SE and SD bars, IMU shares), the identity legend (built from `wiser/configs/rat_identities_2026c.csv`: the user's identifying colour per animal, 2026-10-10, SF09 / SF10 corrected the same day — SF07 green, SF08 red, SF09 black, SF10 blue, SF11 white (looks grey), SF12 yellow; the Notion coban / sticker shown for reference; the first days about 08-30 / 08-31 are uncertain; click markers take the identifying colour) and the six in-hand close-up clips. The user clicks heads, picks SF07–SF12 / unknown and sure / likely, and answers "pile composition complete?"; localStorage autosave; Export CSV / JSON → `cv/configs/inbox_identity_2026c/`; Import JSON. No identity is pre-filled. Each frame carries its lid segment and correction B (recorded, not applied). **Blind first** (plan amendment 8): per segment the WISER roster and arrangement stay hidden until "Save clicks & reveal WISER"; the clicks saved then are the blind record (`before_reveal`, `verdict_first`) the order test uses, later edits are recorded separately; clicks stored by the first page version are flagged `legacy` (that version showed WISER, so they are not blind). Markers can be selected (within 12 screen px), dragged, nudged, relabelled and deleted (Delete, right-click, × in the per-frame list) with undo / redo; all of it checked in headless Chrome (`inbox_identity_page.py --ui-check`). **Top-view orientation** (plan amendment 9): after the reveal the WISER top view is drawn in paddock directions (default = WISER / paddock orientation, +x right, +y up; edges labelled with the paddock walls, the nearest pole B1 / B3 drawn) and can be rotated (0 / 90 / 180 / 270°) and mirrored per house; the choice is stored with a timestamp and exported as `orientation_by_house`. It is a display setting only — not a fit and not the pre-registered camera ↔ WISER mapping (fitted later from the blind clicks); the user's chosen orientation may serve as an independent prior / check for that fit.

| segment_id | house | roster at the flash | untracked | SF11 | lid segment (colour frame) | lid flag | frame checks |
|---|---|---|---|---|---|---|---|
| CH07_20260909_191025 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 26 | ok | ok ok ok |
| CH07_20260910_071415 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 26 | lid+ok | ok ok ok |
| CH07_20260910_083742 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 27 | ok | ok ok ok |
| CH07_20260910_091147 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 27 | ok | ok ok ok |
| CH07_20260910_122703 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 27 | ok | ok ok ok |
| CH07_20260910_125142 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 27 | ok | ok ok ok |
| CH07_20260910_135131 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 27 | ok | ok ok ok |
| CH07_20260910_140227 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 27 | ok | ok ok ok |
| CH07_20260910_141613 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 27 | ok | ok ok ok |
| CH07_20260910_143243 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 27 | ok | ok ok ok |
| CH07_20260910_152307 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 27 | ok | ok ok ok |
| CH07_20260910_163056 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 27 | ok | ok ok ok |
| CH07_20260910_175935 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 27 | ok | ok ok ok |
| CH07_20260910_195004 | house_2 | none |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 27 | lid+ok | ok ok ok |
| CH07_20260911_092822 | house_2 | SF07, SF08, SF09, SF10 | SF12 | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 28 | lid+ok | ok ok ok |
| CH07_20260911_095409 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 29 | ok | ok ok ok |
| CH07_20260911_140955 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 29 | ok | ok ok ok |
| CH07_20260911_141758 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 29 | ok | ok ok ok |
| CH07_20260911_144345 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 29 | ok | ok ok ok |
| CH07_20260911_145024 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 29 | ok | ok ok ok |
| CH07_20260911_182803 | house_2 | SF07, SF08, SF09, SF10, SF12 |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 29 | lid+ok | ok ok ok |
| CH08_20260910_084548 | house_1 | none |  | SF11 out of the paddock (taken out at the 09-07 AM round; the last tag fix 08:20 is its implant); rosters are complete except in tag dropouts | 27 | ok | ok ok ok |


Close-up clips: source `D:/Field2026_analysis_out/2026c/inhand_closeups/SF07.MOV … SF12.MOV` (read-only; every sha256 checked against that folder's `MANIFEST_sha256.csv` before transcoding; sources unchanged afterwards), transcoded once to H.264 MP4 (`identity_page/closeups/`). Per the folder README: SF07, SF08, SF09, SF10, SF12 were filmed 2026-09-10 07:54–08:19 (AM round); SF11 on 2026-08-30 (the user, 2026-10-10: its implant came off early, so an earlier clip is used); the files' `creation_time` tag (2026-10-10 20:3x UTC) is the transfer time, not the filming time. The clips are H.264 720 × 1280 portrait (SF11 1280 × 720), 30 fps.

| animal | src | dst | src_sha256 | manifest_match | src_unchanged | dst_bytes | mp4_duration_s | manifest_duration_s | duration_check | relinked |
|---|---|---|---|---|---|---|---|---|---|---|
| SF07 | D:/Field2026_analysis_out/2026c/inhand_closeups/SF07.MOV | closeups/SF07.mp4 | 6341513832ba3d724b2767316e4c729511ce47bbd0af49c8e8b9c7f811465e36 | True | True | 17533692 | 35.641 | 35.633333 | True | - |
| SF08 | D:/Field2026_analysis_out/2026c/inhand_closeups/SF08.MOV | closeups/SF08.mp4 | 27b83803a62a8d01a46a4ad9ffde8c1153bcf0c45f6e3b44aec5806e7234a7eb | True | True | 23862431 | 48.435 | 48.433333 | True | - |
| SF09 | D:/Field2026_analysis_out/2026c/inhand_closeups/SF09.MOV | closeups/SF09.mp4 | 7b6c0e8f89b8c22cafa370b5817dfbd1b1d4494cba3601889355a8ecfcddb18f | True | True | 26872749 | 51.639 | 51.633333 | True | 2026-10-10 19:40: was closeups/SF10.mp4 (source files renamed: the user had SF09 / SF10 reversed) |
| SF10 | D:/Field2026_analysis_out/2026c/inhand_closeups/SF10.MOV | closeups/SF10.mp4 | 7974d20c8cc46da0cb470bcc9fe130627ddd3ef95829672f1f1581fe5c6e2330 | True | True | 22433871 | 41.446 | 41.433333 | True | 2026-10-10 19:40: was closeups/SF09.mp4 (source files renamed: the user had SF09 / SF10 reversed) |
| SF11 | D:/Field2026_analysis_out/2026c/inhand_closeups/SF11.MOV | closeups/SF11.mp4 | a01df1d6dabc2118e6124e6843bd8d48e4849f2217bef59f0554d3dbdfbfee9a | True | True | 5797546 | 9.844 | 9.833333 | True | - |
| SF12 | D:/Field2026_analysis_out/2026c/inhand_closeups/SF12.MOV | closeups/SF12.mp4 | da5e0808d04a01fac317034fa8a8ddae5ec85e0e6d5ce980a19c352663b4ef6c | True | True | 16920541 | 32.785 | 32.766667 | True | - |


## Definitions (formula and words)

Times are field-PC local (America/New_York, naive). Video frame time t = file-name start + PTS. WISER fix time =
`t_ms` (Unix ms UTC, the field-PC clock) converted to local time. Positions are inches.

**A. Colour segments**
- **Chroma** c = (1/N) Σ_p (|R_p − G_p| + |G_p − B_p|) over the N = 640 × 480 pixels of the frame decimated by 4
  (nearest pixel), 8-bit RGB. A monochrome (IR) frame has R = G = B, so c = 0; a colour frame has c ≫ 0.
- **Threshold** thr = 10^((v_k + v_(k+1)) / 2), where v = the sorted distinct values of log10(max(c, f)) over all
  scanned I-frames of 09-09 00:00 → 09-11 19:40 (both cameras pooled) and k = argmax_j (v_(j+1) − v_j): the geometric
  mid-point of the largest gap in log chroma. A frame is colour if c ≥ thr. Floor f = 0.01 (plan amendment 6, after
  results; the pre-registered f = 10⁻⁴ put the largest gap between two isolated IR I-frames, see section A).
- **Colour run**: a maximal sequence of consecutive colour I-frames of one camera (I-frames are 2 s apart, GOP 2 s).
- **Segment start** = the time of the first frame (every frame decoded in [t_a − 3 s, t_a], t_a = first colour I-frame
  of the run) of the uninterrupted colour stretch that reaches t_a. **Segment end** = the time of the first IR frame
  after the uninterrupted colour stretch that starts at the last colour I-frame t_b (frames in [t_b, t_b + 3 s]); this is
  the OFF instant at frame resolution (0.05 s). Runs whose refined intervals are < 1 s apart are merged.
  **Duration** = end − start (s). **Median chroma** = median of c over the run's colour I-frames.
- **Log match**: a segment matches the colour-log row of the same date whose camera field names the segment's camera
  and whose operator time T (ON, else OFF, else the planned slot) lies within 120 s of the segment interval
  (distance = 0 if T ∈ [start, end], else min(|start − T|, |end − T|)); a round row without a time matches a segment
  inside the round window (−5 / +30 min). Nearest row wins. **Δ** = start − T (ON / slot rows) or end − T (OFF-only rows);
  **Δ_corr** = Δ + 35 s (the operator clock ran ≈ 35 s fast on 09-09). A segment with no row is *unmatched*; a row with an
  operator time and no segment is a *row without segment*.
- **Control count** = number of I-frames with c ≥ thr in each control hour (expected 0).

**B. WISER box events and positions**
- **Fix rule (primary)**: `valid` ∧ ¬`m_off_animal` ∧ ¬`m_tag_validity` (amendment 1; `m_handling`, `m_silence`,
  `m_adc_lane` fixes are kept and the events carry `in_handling`). **Literal rule**: `valid` and no `m_*` flag.
- **Membership** of a fix: (x, y) of the default track inside the house_h rectangle of `wiser_rois.json` grown by 15 in on
  every side (`_rect_membership(..., 15)[1]`).
- **6-s smoothing**: for animal i and second s, f_h(s) = Σ_{u ∈ [s−3, s+3)} n_in,h(u) / Σ_{u ∈ [s−3, s+3)} n_fix(u), where
  n_fix(u) = number of fixes in second u and n_in,h(u) = those inside house_h. Raw state = house_h if f_h(s) ≥ 0.5;
  'out' if the window holds a fix and no f_h ≥ 0.5; 'unknown' if it holds no fix.
- **20-s minimum dwell** (cleaned state): walking through the runs of the raw state, a change is accepted only if the new
  state's run lasts ≥ 20 s; shorter runs keep the current state; unknown runs < 20 s are bridged (state held); a longer
  unknown run makes the state unknown until a known run ≥ 20 s.
- **Event** = a change of the cleaned state at second s: *exit house_h* when leaving h, *enter house_h* when arriving in h
  (1-s resolution). `across_unknown_s` = length of the unknown stretch the change crossed (0 = observed directly);
  `new_state_run_s` = how long the new cleaned state lasts; `in_handling` = any `m_handling` fix of that animal within
  ± 30 s; `fixes_pm10s` = fixes of that animal within ± 10 s; `lid_event` = the house-lid event window (± 5 min) containing it.
- **09-05 check**: for each of the operator's 12 events (six exits from house_2 at 08:47:08; entries into house_2 SF09
  09:49:49, SF07 09:49:51, SF11 09:49:58, SF10 09:50:01, SF12 09:50:15; SF08 into house_1 09:50:13) the nearest WISER
  event of the same animal, house and kind within ± 30 min; Δt = t_WISER − t_operator. **Pass** iff every |Δt| ≤ 30 s and
  the five house_2 entries, sorted by t_WISER, come in the operator's order SF09, SF07, SF11, SF10, SF12.
- **Occupancy (per second)**: roster of house_h = animals whose cleaned state is h; `untracked` = animals present in the
  paddock and tagged whose state is unknown; `sf11_untagged` = SF11 present without a tag on the animal (dropouts 09-02
  00:03 → 08:15, and 09-07 06:10:45 → 08:20 after the implant carrying tag 3058 fell off); `sf11_absent` = SF11 out of the
  paddock (taken out at the 09-07 AM round; the last 3058 fix at 08:20 is the implant in house_2); `all_tracked` = no
  untracked animal and no untagged animal present. Rosters are complete except in tag dropouts (SF11's two; SF12 before its
  tag's first fix 08-31 06:36) and while a tagged animal is untracked (plan amendments 12-13, 2026-10-11).
- **Paddock position** p = s R(θ) (w − c) + c + d (the accepted WISER → paddock similarity: s 0.96340, θ 0.1143°,
  c (501.68, 761.10) in, d (−272.85, −605.80) in). **House frame**: along = (p − C) · (cos φ, sin φ),
  across = (p − C) · (−sin φ, cos φ), with C, φ the house centre and ridge angle (house_2 (342.4, 117.7) in, 92.0°;
  house_1 (142.23, 123.46) in, 88.51°). +along ≈ paddock +y (toward the y = 240 wall), +across ≈ paddock −x.
- **In-house minute** (animal i, house h, minute m): kept if the cleaned state is h for n_s_in ≥ 30 s of the minute; the
  in-house fixes are those whose second has state h AND that lie in h's dilated rectangle. `along_in` / `across_in` =
  mean of the default-track (x, y) of those fixes in the house frame; `along_raw_in` / `across_raw_in` = mean of the raw
  fixes; `sd_*_raw_in` = their standard deviation; **SE** = sd / √n (n = `n_fix`; ignores autocorrelation, so it is a
  lower bound of the true uncertainty); IMU shares = fraction of the minute's distinct IMU-QC-ok aligned seconds in each
  `imu_state` (1 still, 2 active, 3 locomoting); `in_body_footprint` = |along| ≤ 24.63/2 + 3 in and |across| ≤ 18.0/2 + 3 in
  (descriptive only; the dilated rectangle reaches far beyond the body).
- **Frame-difference energy** e_k = (1/M) Σ_q |g_k(q) − g_(k−1)(q)| over the M = 320 × 240 pixels of the area-averaged
  grey image of consecutive I-frames k − 1, k (2 s apart) of one file. **Per-minute energy** E_cam(m) = mean e_k over the
  minute's I-frames, excluding I-frames within ± 10 s of a colour segment of that camera (or whose predecessor is).
  **Per-minute events** N_h(m) = number of enter + exit events (all animals) of house h in minute m.
- **Camera ↔ house correlation**: Pearson r and Spearman ρ between E_cam(m) and N_h(m) over the minutes of 09-09 00:00 →
  09-11 19:40 (all, and outside the lid-event windows ± 5 min). `p_circular_shift` = share of 1 000 circular shifts of
  N_h by ≥ 60 min with r ≥ the observed r (context only; no decision is taken from this check).

**C. Click page**
- **Frames**: colour_mid = the first frame with t ≥ (start + end) / 2; ir_p06 / ir_p15 = the first frames with
  t ≥ end + 6 s / end + 15 s. Each frame's chroma is recomputed; `mode_check` flags a colour frame with c < thr or an IR
  frame with c ≥ thr. Frame index = position in the file counted from the key frame the decoder seeks to.
- **Lid correction** B (2 × 3) = `frame_correction.Corrections("2026c").correction(cam, t)`: maps frame pixels to the
  09-04 12:00 reference pixels of the frame's lid-closed segment (median of that segment's tracked samples); stored per
  frame with the segment index and flag, not applied.
- **Roster at the flash** = the occupancy roster of the camera's house at the segment middle. **Pre-flash position** =
  the in-house minute statistics above over [start − 60 s, start).

## What is not verified

- CH07 = house_2 / CH08 = house_1 rests on the 09-07 evidence (plan facts); the B4 correlation is reported, not used to decide.
- The 09-05 check validates the box events at one round (handled placements); natural night crossings are not validated, and the dilated rectangle (± 28–33 in around the ROI centre) also counts an animal just outside the house as 'in'.
- In-house positions use the accepted P0 WISER → paddock map (one CH01 hour, test median 4.4 in) and the house poses; the WISER tag sits on the head; WISER is a 2-D solve (no z). The arrangement layer is not accepted until the user's clicks pass the operator's rule (≥ 4 of the first 5 flashes with ≥ 3 identified animals; the later, pre-registered step).
- SE = sd / √n ignores autocorrelation of consecutive fixes (a lower bound).
- A colour insert shorter than the 2-s I-frame spacing can fall between I-frames and be missed by the scan.
- Correction 2026-10-11 (plan amendments 12-13, confirmed by the user): tag 3058 rode on SF11's implant; at 09-07 06:10:45 the implant fell off with the tag, the rat stayed in the paddock untagged until it was taken out at the AM round, and the last 3058 fix (08:20) is the implant in house_2 (the default tracks' `m_off_animal` flag on those fixes is correct). From 08:20 to 09-11 19:40 SF11 is absent and the paddock held five animals, all tagged: rosters are complete except in tag dropouts (SF11 09-02 00:03 → 08:15 and 09-07 06:10:45 → 08:20; SF12 night 08-30 / 31). The 10-10 version called every roster after 09-07 06:10 a lower bound; no event, position, segment, roster or check result depended on that; only the `all_tracked` share changed (box_occupancy_1s.csv.gz rebuilt from the unchanged states_1s.npz; earlier versions in `superseded_20261011/` and `superseded_20261011b/`).

## Files

Run `D:/Field2026_analysis_out/2026c/cv_field_inbox_p0_20261010_1702`: `scan/`, `scan_control/` (per-file I-frame tables), `scan_inventory.csv`, `scan_log.jsonl`, `colour_threshold.json`, `colour_segments.csv`, `colour_log_rows.csv`, `control_hours.csv`, `box_events.csv`, `box_events_sensitivity.csv.gz`, `box_occupancy_1s.csv.gz`, `states_1s.npz`, `check_0905.csv`, `check_0905_sensitivity.csv`, `wiser_summary.json`, `inhouse_minutes.csv.gz`, `inhouse_frames.json`, `camera_house_check.csv`, `camera_house_minutes.csv.gz`, `identity_page/` (`index.html`, `frames/`, `closeups/`, `page_data.json`, `page_check.json`), `run.json`. Data map: `cv/cv_field/DATA_MAP_c1yolo_wiser.md` section K.
