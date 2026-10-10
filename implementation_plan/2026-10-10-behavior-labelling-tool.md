# WISER-assisted behaviour-labelling tool for cohort-3 video (2026c) — ethogram v0 + tool logic

**Status: PLAN, awaiting the user (2026-10-10).** Nothing is built yet.

## 0. Decisions so far (user, 2026-10-10)

- **Who labels:** the undergrads. The tool lives in their repo, `social-field-rat`. Work starts on the local clone
  `D:/Documents/GitHub/social-field-rat-wiser-loop` on a new branch `behavior-label` from `wiser-loop` (1ce4db4, on her
  real 09-14 history), delivered the same way as the label loop.
- **Form:** a browser page plus a local frame server. Frames are read on demand from the hourly video, never pre-rendered.
- **Now:** fix the ethogram (how many labels, which ones) and get the tool's logic to run end to end. Production
  labelling waits for YOLO tracks and animal identity.
- **Ethogram source:** behaviour is the same across cohorts. Cohort 3 simply did not log routine behaviour such as
  nesting, so the ethogram is drawn from all cohorts.

## 1. Inputs (advice collected 2026-10-10)

| Source | What it contributes |
|---|---|
| Maria Aurelio's `labeling/behavior_segmentation.py` | 6 toggle keys (following, nesting, running, playing, grooming, eating). One proxy video per hour, frames → seconds by a typed fps. Master CSV rewritten on every save. Existing rows: `T:/Data/SocialField/labeling/behavior_segmentation/behavior_labels.csv` (4 test rows). |
| Celine's following labels | Same folder, `following_labels.csv`: 176 bouts, cohort-1 CH01 21–22 h, 8 nights. **Two defects found:** in the 06-28 video, `start_time_sec` uses 30 fps for some rows and 20 fps for others; and every `leader_y_*` is negative (−1907…−8), so the clicks are in a rotated display frame, not image pixels. Fix both before any reuse. |
| Cohort-1 field log (`FIELD_OBSERVATIONS.md`) | Exploring, hopping, fast runs with foraging pauses (picking insects), rearing, following, **parallel / side-by-side movement (distinct from following, 07-05)**, fights with a winner, digging / burrowing / tunnelling, bedding carried between houses, self-collected grass nest material, huddling and sleep-group splits, synchronized grouping in the house (possible allogrooming), hiding together, coordinated scanning. |
| Cohort-3 behaviour log (Notion + `behaviour_observations_cohort3.csv`, 9 rows, 09-07…09-10) | Huddle; nesting + following; scattering / activity outside; SF07 motionless in the open; pile arrangements; REM twitching; SF09 carrying nest material. No fights, eating, grooming or play logged. |
| Sleep session | Priorities, all at 1 s:<br>1. The post-release minutes: lying still vs freezing (#62; `ephys_spikes_sleep_explore_H_h4_opening_2026c.csv`, 100 episodes).<br>2. House entry / exit. The user's ongoing check `house_entry_video_check_20261010` must not be duplicated.<br>3. Huddled vs alone.<br>4. Woken by a housemate: Phase-6 tight followers.<br>5. The dawn return. |
| SWR session | Priorities:<br>1. Eating in the house.<br>2. Quiet wake vs drowsy.<br>3. Grooming.<br>4. Huddle and with whom.<br>5. Door pauses.<br>6. Field pauses and rearing.<br>Needs: **exhaustive labels within whole windows** (a rate needs a denominator), per-animal identity, ± 1–2 s, ≥ 20 min per behaviour per animal. |
| Mic session | Add: scratching (separate from grooming), digging / bedding, gnawing, aggressive contact, rearing / climbing, in-place adjustment in the huddle, sleep twitch, jostled by a neighbour, an explicit "nothing visible", and a visibility flag. |
| Camera / calibration session | **Field:** CH01/CH02 cover ~68 % of the paddock each, CH03/CH04 ~12 % each at the two ends. Coverage comes from `paddock_map.load()[cam].sees()` / `in_support()`.<br>**WISER → pixel:** exact via `to_paddock_inv` + `frame_correction.invert(Corrections("2026c").correction(cam, t))`.<br>**Houses:** CH07/CH08 are uncalibrated, so no in-house pixel placement.<br>**Daytime:** the correction table is night-only; use `landmark_track.py`.<br>**Pitfalls:** nightly camera shifts (±20 px), lid jumps, the 09-12 → 09-15 gap, the Sunday 14:00 NVR gap. |
| IMU-video session | Take the camera zone from **before** the window. Pre-rendering is the bottleneck (11 GB, ~1 h for 80 events).<br>**Browser page practice:** inline data, autosave, export / import, first answer locked.<br>**IMU states:** "still" is reliable; locomotion has TPR 0.75 / FPR 0.15; "active" mixes grooming, eating and sniffing, so it is a proposal only. Gyro turn ≠ body turn; V3 speed is inflated in place.<br>**Labels:** proposal vs free provenance, a blind subset, long-format append-only intervals. |
| Field record (recording-inquiry) | **Food boxes** are inside both houses (CH07/CH08); water is not recorded. House 62.55 × 45.72 cm, roof = lid (33 lid events). **IR identity:** coban colours are useless at 850 nm; in-house identity needs a side view of the pattern; WISER separates animals only > 15 in per fix (> 8 in for 1-min means). **Colour inserts** on CH07/CH08: seconds long, 09-09 → 09-11. **Battery rounds:** `BATTERY_LOG_cohort3.md` (the 09-01 ~00:34 round is missing from it and from our handling / lid JSONs). |

## 2. Ethogram v0 (proposal)

### Rules

- **R1. Four layers.** Only layer A is exhaustive: at every moment, each subject in view has exactly one A state.
  Layers B–D are added only when clearly seen.
- **R2. Grounding.** Every label has been observed in some cohort, and has a consumer or a sensor it validates.
- **R3. Nothing is left blank.** "Not visible" and "unsure" are labels.
- **R4. Subject identity.** The subject is an animal (SFxx) when the labeller is sure, else a window-local slot (A, B, …)
  with `id_conf` = sure / probable / unsure and the WISER roster as candidates. Identity is a field, not a precondition,
  so labels made now can be resolved later by YOLO tracks and identity.
- **R5. Time.** Field-PC ms (file-name start + PTS), resolution 1 s. A state lasts ≥ 1 s; same-state gaps < 1 s merge.

### Layer A — state (exhaustive; 7 keys, change-point labelling)

| key | label | definition (short) | seen in | validates / serves |
|---|---|---|---|---|
| 1 | `rest` | lying or curled, body still (alone or in a huddle) | all cohorts | IMU still, sleep scores |
| 2 | `still_alert` | immobile but head up: sitting, crouched, frozen, scanning in place | c1 hiding / scanning, c3 SF07 motionless | sleep #62 (sleep vs freezing) |
| 3 | `in_place` | active without leaving the spot; detail in layer B | all | IMU "active" |
| 4 | `explore` (search) | slow, meandering progression with sniffing, stop-go | c1 explore, stops at rocks | WISER search excursions |
| 5 | `walk` | directed, steady travel | all | WISER / IMU locomotion |
| 6 | `run` | fast travel: dash, gallop, hop | c1 fast runs, hopping | WISER speed |
| 7 | `not_visible` | occluded, out of view, cannot tell | — | required for exhaustive windows |

### Layer B — what the in-place activity is (optional, only when clear; 6 keys)

| label | definition | seen in | consumers |
|---|---|---|---|
| `groom` | self-grooming (face, body; scratching kept as a modifier) | c1 grouped grooming | SWR, Mic, IMU rhythmic |
| `eat` | at the food box, holding or chewing food, gnawing, picking items | c1 insects, c3 food boxes | SWR #1 |
| `dig` | digging soil, burrowing, tunnelling | c1 burrow, tunnel, water hole | WISER below-plane dropout |
| `nest` | carrying or arranging bedding or grass | c1 bedding moved, grass; c3 SF09 | Mic bedding noise |
| `rear` | standing on the hind legs | c1 "more rearing" | SWR field pauses |
| `other` | in-place activity not covered above | — | — |

### Layer C — social (directed subject → partner, may overlap; 5 keys)

| label | definition | seen in | serves |
|---|---|---|---|
| `follow` | the subject travels along the partner's path behind it | all cohorts, Celine's 176 bouts | WISER following incidents |
| `parallel` | moving side by side with the partner, not behind it | c1 07-05 (explicitly not following) | keeps `follow` clean |
| `contact` | nose or body contact with the partner (investigate, approach that ends in contact) | all | WISER < 14 in is unresolvable |
| `huddle` | resting in body contact (group; partners = all in contact) | c1, c3 piles | sleep #38, SWR |
| `play_fight` | chase, wrestle, box, pin; optional flag aggressive + who retreats | c1 fights with winner | dominance, Mic squeaks |

### Layer D — point events (instant; 2 keys)

`enter_house` and `exit_house`, each with the house (and the door, if the house has more than one).

### How many

- v0 has **20 keys**, but each decision is between at most 7 options in one layer. Inter-rater reliability depends on that
  choice size, not on the total key count.
- **Maria's six keys are all kept:**
  - following → `follow`
  - running → `run`
  - playing → `play_fight`
  - grooming → `groom`
  - eating → `eat`
  - nesting → `nest`
- **Kept for later, not in v0:**
  - scratch (as its own key; now a groom modifier)
  - sleep twitch
  - jostled
  - door pause
  - huddle adjustment
  - allogroom
  - carrying food
  - These are added only when a consumer funds them with windows.
- **Reliability:** v0 is tested on overlap windows labelled by two people. Categories that fall below an agreed threshold
  (e.g. Cohen's κ < 0.6) are merged before production. Likely merge candidates: `rest` + `still_alert` in the house,
  `explore` + `walk`, `play_fight` aggressive flag.

## 3. Tool logic

1. **Behaviour kit.** Built on this PC, read-only for the tool, intermediates cached like the WISER pixel kit.
   - **Per second:** WISER default tracks per animal (zone house_1 / house_2 / field with the cohort-3 re-centred
     houses, paddock x, y, speed), IMU seconds state, pairwise distances, house roster.
   - **Per camera and second:** WISER circles where the camera is mapped (`to_paddock_inv` + `frame_correction.invert`).
   - **Exclusion intervals:** handling, lid events, rounds, construction / mowing, colour inserts, NVR gaps, ≥ 09-11
     19:40.
   - **Video index:** file, start, PTS table.
2. **Window list** (`select_windows.py`, fixed seed).
   - `random` windows are exhaustive, stratified by WISER context: house vs field, day vs night, group size.
   - `event` windows are WISER candidates (entry / exit, a following-candidate pair, approach to < 14 in, post-release
     opening) plus the Notion seeds.
   - Cameras are chosen from the zone **before** the window:
     - field → CH01 / CH02 / CH03 / CH04, ranked by `sees` / `in_support`;
     - house → CH07 / CH08 plus the roof view CH05 / CH06.
   - Night 09-05 stays apart, so a later classifier can be tested on it.
3. **Frame server.**
   - stdlib `http.server` + PyAV + Pillow, bound to 127.0.0.1. Read-only on the video.
   - On window open, it decodes each camera's range once, sequentially, into a display-size JPEG cache:
     panoramas upright 1920 × 540, house cams 1280 × 960, optional crop.
   - Frames are keyed by field-PC ms (file-name start + PTS, joined at 1 µs because PTS come in bursts), across hour
     boundaries.
   - Endpoints: window list, window manifest, frame, label POST, export.
4. **Page.**
   - Camera tiles synced on field-PC time; each tile shows its nearest frame ≤ t.
   - A per-animal timeline strip shows zone, speed, IMU state and the label bars.
   - Controls:
     - keys: play / pause, ±1 frame / ±1 s, speed, subject selector;
     - layer A keys 1–7 set a state **from now until the next change**, which makes A exhaustive by construction;
     - B / C keys open and close a bout like Maria's toggles, and C asks for the partner;
     - D keys are instants.
   - Blind windows hide the WISER circles and the timeline until "first pass done".
   - A "window complete" button. Absence of a behaviour counts only in complete windows.
5. **Storage.** Append-only `labels/<labeller>/events.jsonl`: every add / modify / delete is a row with the tool version
   and a timestamp. `build_labels.py` derives the long-format `labels.csv`:
   - label_id, window_id, subject, id_conf, layer, behaviour, partner;
   - t_start_pc_ms, t_end_pc_ms, cameras, visibility;
   - mode (blind / assisted), from_proposal, labeller, tool_version.

   Per-labeller files remove the one-writer problem of a rewritten master CSV.
6. **Progress / QC.** `progress.py`: minutes per behaviour × subject, windows complete, κ on overlap windows. This is
   the same tracking as the label loop.
7. **Proposals** (minimal in v0). WISER entry / exit and following candidates appear as dashed suggestions in assisted
   mode only. An accepted proposal carries `from_proposal`. WISER never creates a label.

## 4. Steps

| step | what | check |
|---|---|---|
| S1 | `ETHOGRAM.md`: definitions, decision rules and cohort examples, from §2 | the user reviews this plan |
| S2 | code + synthetic self-test: generated videos with an hour boundary, PTS bursts and a rotated pano; server endpoints; change-point state logic; exhaustive-coverage check; jsonl round trip; merge | self-test passes; no field data |
| S3 | a demo kit + 6 windows from `F:/3rd_rat`: 2 field night (CH01/CH02), 2 house day (CH07/CH08), 1 entry event, 1 following candidate | **test plan confirmed with the user before running** |
| S4 | the user and an undergrad try it; fixes; package for her machine (drive or Q:) | their feedback |

Production windows and quotas come after YOLO tracks and identity, and after consumers say how many minutes they need.

## 5. Not in scope / do not

- No in-house pixel circles.
- No identity inference by the tool.
- WISER never makes or removes a label.
- Never read the OSD clock.
- No writes to F:, Q: or T:.
- Maria's and Celine's CSVs stay untouched.
- Nothing after 09-11 19:40.
- The 09-05 night is kept out of v0 windows.

## 6. Open questions for the user

1. Ethogram v0: approve the four layers, 7 / 6 / 5 / 2 keys? Should `play_fight` stay one key with an aggressive flag?
2. Window length for random windows: 2 or 5 min?
3. Daytime field windows (needs the `landmark_track` daytime correction) now, or only night field + day house?
