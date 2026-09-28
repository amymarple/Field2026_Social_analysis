---
name: regime-aware-ephys
description: >-
  This skill should be used before choosing, staging, sorting, matching or interpreting any cohort-3 (2026c) WILD
  neurologger data (SF07–SF12): selecting sessions or blocks for Kilosort, defining sorting blocks, deciding what to
  exclude, reading unit yield, matching units across sessions, LFP / SWR / theta / sleep-state work, the field-PC
  time chain, or any ephys claim tied to a date, animal, shank or behaviour. The recording is regime-confounded: firmware
  defects, probe advances (the first ~4 h after each is unstable), loosening contacts and implant losses, battery
  deaths and unanchored ends, the ADC-lane contamination, clock steps, handling rounds, disturbance windows and the
  09-11 population change all look like neural effects if ignored. It carries the per-logger issue record, the rules,
  and where the current record lives (Notion cohort page, field2026-sync incident log + per-offload QC requests,
  recording repo BATTERY_LOG). Trigger phrases: "kilosort", "spike sort", "which sessions", "blocks", "stage",
  "unit yield", "match units", "track units across days", "SWR", "ripple", "theta", "sleep state", "LFP", "pc_time",
  "probe move", "SF07".."SF12", "cohort 3", "2026c", "neurologger", "WILD".
version: 0.1.0
---

# Regime-aware ephys (cohort 3, WILD CE64)

## Core principle

**A change in an ephys number has two possible causes, and the recording path is the likelier one until ruled out.**
- *Recording path:* firmware defects, a probe advance, a loosening contact or detaching implant, a battery death or
  auto-stop, the ADC lane, a PC clock step, handling at a battery round, a noise or light window.
- *Brain / behaviour path:* the effect you are looking for.

Before picking blocks to sort or making any claim, check the record for the animal and time window involved. Say in
the deliverable which sources were checked, with their dates or commits.

The record below is a **snapshot compiled 2026-09-28**. It covers the Notion page as edited 2026-09-24,
field2026-sync `c19ed6c`/`1d409fe` and the recording repo `be3193e`. It tells you what to look for; the sources below
are the current truth.

## Procedure (every time)

1. **Pull both sibling repos.** Every offload/QC cycle and every field answer adds material:
   `git -C ../Field_2026_Social_Recording pull --ff-only` and `git -C ../field2026-sync pull --ff-only`.
2. **Read the current record for the window at hand.** For a cited answer, dispatch the `recording-inquiry` subagent
   instead of reading these yourself; it reads all three sources.
   - the newest `field2026-sync/from-field/*_cohort3-incident-log.md` (newest entry at the bottom);
   - the per-offload QC requests in `field2026-sync/tasks/done/` (see *Where the QC lives*);
   - the **Notion cohort page** "4-Rat 3rd cohort — full (SF07–SF12)"
     (https://app.notion.com/p/3c23b0530d4a8152a204cce3afa11671): the animal table (probe advances with exact
     session times, "kilosort: unstable" windows, implant losses), the dated observation log, and the behaviour log
     with session + rec-seconds;
   - `BATTERY_LOG_cohort3.md` in the recording repo (per round: Stop/Start, gaps, anchors, cards).
3. **Look up each session** in `results/2026c/ephys_spikes/reports/ephys_spikes_session_index_2026c.csv`:
   `firmware`, `measured_verdict`, `regime`, `bad_channel_candidates`, `field_flag`, `valid_until`, `adc_lane`. Also
   check its `pc_time_chain` verdict (`…pc_time_chain_2026c.md`).
4. **Local first.** Develop and validate every new step on this PC against the local raw copy `E:\3rd_rat_spikes`
   (read-only). Only then deploy the same commit to BioHPC, and spot-check the server output against the local result.
5. **Apply the rules below.**
   - When the record has a fact that `cohorts/2026c.yaml` lacks, add it to the YAML with its source (the YAML is
     what the code reads). Never hard-code it in a script. See *Known gaps*.
   - When sources disagree, report both versions. Prefer the one backed by video, card or telemetry evidence.

## Hard rules for sorting and matching

| Issue | Rule |
|---|---|
| **Firmware** | FM65 (sessions after the 09-01 ~19:30 round) is clean. FM64 needs the de-glitched copy (`stage_session.py`); after sorting, reject units with template neighbour/peak ratio < 0.4 (`ephys/template_width_check.py`). FM62 (08-31 day) is written off: a wide-impulse regime de-glitching cannot fix, and corrupt sync lanes, so no PC time. 08-31 11:00–18:00 is a troubleshooting window with blank LFP. Night 1 (08-30 ~18:39 → 08-31 ~04:30) is lost on all six (only `recovery.bin`). |
| **Probe advances** | Each is a hard block boundary: never merge or match units across one (table below). The first ~4 h after the post-move session start is **unstable**: sort it, but flag it, keep it out of stability or drift claims, and do not use it as a matching anchor. |
| **Implant / contact** | SF11 ends at `valid_until` 09-07 06:10 (video: detached 06:10:45, passive, inside a sleeping six-rat huddle; open circuit to the 08:12:41 Stop; logger retired). SF12 shanks 1 and 4 have a loosening contact from the 09-10 afternoon (half amplitude), with whole-shank intermittent opens on the 09-10 night. Treat SF12 shanks 1/4 as degraded from 09-10 ~14:00 (shanks 2/3 clean). The SF12 09-11 09:47:47 session had its connector open to ~17:50 (field-flagged). SF12 is valid to 09-11 23:30. |
| **ADC lane** | 09-10, all five loggers: day pieces ~14:42–15:09 → 18:39–18:51 and night pieces ~19:33–19:47 → 20:41–20:53 (`ephys.adc_lane.on_windows`; `field2026-sync/from-field/2026-09-10_adc-lane-contamination-boundaries.csv`). A 312.5 Hz pulse train on all 64 channels, and no temperature. Quarantined (moved to `_quarantine_adc_lane_on/`); never sort. |
| **Gaps and unanchored ends** | Check the `pc_time_chain` verdict for every session that ends in one of these:<ul><li>09-01 night early battery stops: SF10 03:07, SF11 03:22, SF08 03:32, SF09 03:34, SF12 04:57.</li><li>SF08 09-01 ~13:45 → 15:30 (FM64 era).</li><li>SF07 auto-stop 09-03 04:17 → no data to ~08:06; SF09 auto-stop 09-03 16:39; SF08 auto-stop 09-03 afternoon.</li><li>09-04 AM deaths: SF12 07:01, SF09 07:16, SF10 07:26, SF08 07:36, SF11 07:41, gaps 40–88 min. BATTERY_LOG disagrees (says SF08/SF09 were swapped alive); the card lengths decide.</li><li>SF10 09-05 auto-stop 06:56 + zombie restarts (field-flagged); SF10 09-06 stop 04:03 → restart 05:58 (holder contact).</li><li>SF09 09-11 auto-stop ~17:32–17:34; final auto-stops 09-12 09:53–10:28.</li></ul>Every swap round leaves a 40–66 min fleet gap. |
| **Channels** | The session index's `bad_channel_candidates` is the machine source; the field record adds:<ul><li>SF08 ch 32 dead; SF09 2 4 32 36 54 56 58 62 (plus 0, 48 from the 09-06 night); SF10 32 34 dead, 63 from 09-09; SF11 32 56 60; SF12 ch 63 weak from 09-09, 48 from 09-10.</li><li>Impulse (donor/victim) pairs from the QC requests: SF08 34/1; SF09 54/8, 34/1; SF10 1/55, 1/38, 44/11; SF12 2/29, 34/32, 47/0, 10/39.</li></ul> |
| **IMU heading** | The headstage carries a magnet (user, 2026-09-28), so the magnetometer is unusable. Lane 7 (x) is saturated in 100 % of samples on all six loggers, and lanes 8–9 are dominated by the magnet's offset. There is no magnetic heading: roll and pitch come from accelerometer + gyroscope only, yaw from the gyro drifts and needs a video/WISER heading reference (`ephys/read_imu.py`, `docs/methods/wild_ce64_imu.md`). |
| **Channel maps** | SF07 is verified. SF08/SF10/SF12 are LFP-derived, SF09 (5×12) is reconstructed/unresolved, SF11 has grouping only. No shank or depth claims unless `verified: true` in `ephys/configs/probes_2026c.yaml`. |
| **Not paddock** | Paddock data ends **09-12 10:10**. The final sessions run on to their auto-stops (10:24–10:28), so clip them at 10:10 (not yet in the YAML). The home-cage sessions of 09-12 from ~10:30 (other laptop, no anchors) are field-flagged `pc_time: false`. The 09-16/17 temperature run is a different dataset (1250 Hz LFP only; SF12's implant came off ≈03:16 on 09-17 per the lab note, while the auto-stop CSV puts the counter freeze at 09-16 22:15:41). |
| **Blips and tests** | Sessions under 1 min (Resync/guard/trial records), the 09-06 probe-position test cards (another PC's console and clock), and SF10's 09-05 zombie restarts are not data. |

### Probe advances (Notion animal table + incident log)

| Logger | Pre-move session ends | Post-move session from | Unstable until | In `cohorts/2026c.yaml`? |
|---|---|---|---|---|
| SF07 | 09-04 13:40:27 | 09-04 14:00:54 | ~18:00 | yes |
| SF11 | 09-04 13:41:26 | 09-04 13:56:50 | ~18:00 | yes |
| SF07 | 09-05 13:15:40 | 09-05 13:31:19 | ~17:30 | yes |
| SF11 | 09-05 15:02:10 | 09-05 15:11:34 | ~19:00 (spans the evening swap) | yes |
| SF07 | 09-06 12:31:20 | 09-06 13:29:42 | ~17:30 | yes |
| SF11 | 09-06 12:32:32 | 09-06 13:33:38 | ~17:30 | yes |
| SF08 | 09-09 17:57:34 | 09-09 18:50:36 | ~22:30 | yes — but `time` is the operator's 18:10; start the settle window at 18:50:36 |
| SF12 | 09-09 18:46:34 (the 18:40:28 stub is pre-move) | 09-09 18:47:51 | ~22:30 | yes (`time` 18:47) |
| SF12 | 09-10 07:43:01 | 09-10 08:35:07 | ~12:30 | yes (added 2026-09-28) |

Evidence to weigh (not a licence to merge):
- The lab found no displacement across the SF07 advances (fingerprint r 0.95–1.00). The operator saw little signal
  change on SF07/SF11, which points to a slipping drive (SF07) or a loosening implant (SF11).
- Unit identity may therefore survive some advances. Test it with the matching step; never assume it.

## Interpretation windows (fleet-wide)

- **PC clock.**
  - Steps (`ephys.field_pc_clock_steps`): 08-30 13:23:19 +2.31 s, 08-31 09:00:19 +2.42 s, 09-01 13:09:12 +2.55 s
    (w32time), 09-03 13:56:01 +1.28 s (reboot). W32Time was disabled 09-01 19:00; after that the PC free-runs about
    25 ppm slow.
  - `COHORT3_DATA_GUIDE.md` speaks of five jumps; the YAML has four. Reconcile before a sub-second claim.
  - Drift-log sign: `offset_ms` = NTP − PC, positive = PC slow. The rig script's docstring says the opposite.
  - The BLE PC-time path is a 10–100 ms-class coordinate; sub-ms work must use the 1 Hz LED edges.
- **PC / recording outages** (field PC side; logger cards unaffected):
  - BSOD 09-01 04:19:56: recorders back ~04:25, WISER down to 05:24, console anchors to ~05:30.
  - BSOD 09-03 13:56: back by ~14:01.
  - Video CH01–08 blank 08-31 ~13:00 → 19:01.
  - BLE ad-feed outage 09-08 00:01–05:04.
  - The weekly NVR reboot on Sunday 14:00 fell on 09-06 (unverified).
- **Handling.** Battery rounds (whole fleet caught) twice daily, ≈06:00–09:30 and ≈17:00–20:00; exact times per round
  are in BATTERY_LOG / Notion. Probe advances are handled too. Keep handling ± settle time out of sleep, state and rate
  baselines.
- **Disturbance** (`field_events`): storm 09-02 ~10:30; construction from 09-08 ~07:50 (end never logged); mowing
  09-09 09:41–14:00; the 09-09 evening round was early because of rain; in-box colour light 09-09 19:10 and colour
  sampling 09-10..12.
- **09-11 19:40: five females released, population 5 → 10** — a regime boundary for every behaviour/sleep/social-state
  metric; the 09-11/12 night is the first with them.
- **Behaviour anchors** (Notion behaviour log / `from-field/behaviour_observations_cohort3.csv`, with session +
  rec-seconds): 09-07 ~05:00–06:15 six-rat huddle; SF08 09-10 14:37 probable REM (leg twitches); SF07 09-09 22:33–23:06
  motionless at a paddock corner (out of BLE range but recorded through); SF09 09-10 21:30 nesting. Use them as seeds
  or validation, not ground truth.

## Where the QC lives

- **The full offload QC is regenerated here.** `bash ephys/run_qc.sh 2026c` writes, under
  `results/2026c/ephys_spikes/reports/`: the session index, the PC-time chain (`…pc_time_chain_2026c.md`), the offload
  QC (`…offload_qc_2026c.md`) and coverage.
- **The per-sync QC is in field2026-sync, inside the field requests.**
  - After each offload's QC, `/offload-field-request` (`ephys/field_request.py --push`) writes
    `tasks/<date>_lab-request-after-offload[-evening|-final-nights].md`, with these sections:
    - §1 routine files to refresh;
    - §2 sessions whose end cannot be anchored;
    - §3 automatic findings (impulse pairs, PC-time verdicts);
    - §3a the lab's notes (card verification, fits, flags).
  - The field appends `## Response`, and the file moves to `tasks/done/`.
  - Ten exist, all answered: 09-05, 09-05-evening, 09-07, 09-07-evening, 09-09, 09-10, 09-10-evening, 09-11, 09-12,
    09-12-final-nights.
  - Read the §3/§3a sections and the Responses for the sessions you use.
- **Other QC files in field2026-sync.**
  - The only standalone QC report: `from-lab/2026-09-03_cohort3-offload-qc{,-full-report}.md` + `-timeline.csv`.
  - Closure: `from-lab/2026-09-17_cohort3-ephys-offload-complete.md` (final inventory, boundaries, exclusions).
  - No request covered the temperature run or the home-cage offload.
- **Open tasks.** Check `tasks/` before assuming a question is unanswered (e.g. 2026-09-28
  `lab-request-cohort3-weather-and-sync-logs`).

## Known gaps between the field record and `cohorts/2026c.yaml` (2026-09-28)

The YAML is what the code reads, so each of these is a place where the code currently ignores the record:
1. `field_flags` names only SF08's four 09-10 lane-ON day pieces. The quarantine removed the pieces from the index,
   but the flag is missing for SF07, SF09, SF10, SF12 and SF08's night piece.
2. No `valid_until` at 09-12 10:10 on the SF07–SF10 final sessions (paddock end).
3. The 08-31 11:00–18:00 exclusion and the FM62 corrupt-sync sessions exist only as free-text notes.
4. `field_pc_outages` gives the 09-01 start as 04:20:14 (Windows event 6008: 04:19:56); its ends are boot/LED times
   (recorders back ~04:25 / ~14:01). The 08-31 video gap, the 09-01 WISER/console outage and the 09-08 feed outage are
   missing.
5. `field_events`: construction end is null; the 09-02 storm and 09-09 rain are absent; `field_events` has no code
   reader yet.
6. SF12 shank-1/4 degradation from 09-10 ~14:00 is not encoded per shank; only the final night is clipped.
7. The temperature run (09-16/17) and SF12's implant loss there are not registered (the lab note asks for it).
8. Line ~82 still calls FM65 "UNEVALUATED" while line ~86 says "VERIFIED".
9. The Notion animal table still says SF11 fell off "~07:40"; the observation log and the video say 06:10:45, which is
   what the YAML uses.
