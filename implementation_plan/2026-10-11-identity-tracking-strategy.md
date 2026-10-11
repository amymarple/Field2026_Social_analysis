# Identity-aware detection and tracking of the cohort-3 rats (in-box CH07/CH08 and panoramas CH01/CH02): strategy

Date: 2026-10-11. Status: **PROPOSED — for audit, nothing approved or run.** Requested by the user 2026-10-10
("这些彩色label能告诉我们什么 … wiser可以用作辅助identity label … 可以用这个训练YOLO么 … 关于strategy出个方案之后让
fable audit multiple animal/object tracking sota，最后问一下codex Yolo_identity 会话"). Every data location:
`cv/cv_field/DATA_MAP_c1yolo_wiser.md`; camera facts: `cv/cv_field/CAMERA_GEOMETRY_2026c.md`.

## 1. Goal and scope

Per-animal, per-frame identity for the six implanted males SF07–SF12 before the population change (2026-09-11
19:40; the five untagged females are out of scope, user 2026-10-07), in two settings:
- **Houses (CH07 inside house_2, CH08 inside house_1):** who sleeps where, who is in the pile with whom, entries and
  exits — the behaviour that pairs with the sleep scores, SWR events and LFP.
- **Field (CH01/CH02 panoramas, night):** who is where and who follows whom, on top of WISER.

The output is a set of identity tracks with a per-frame confidence, honest "unresolved" states (e.g. "pile of 4,
composition known, arrangement unknown"), and an error budget per layer.

## 2. What already exists (facts)

| Asset | State |
|---|---|
| Panorama detector | YOLO11m `rat_m_v5` (cohort-1 trained, imgsz 1280); centre-match AP 0.83 on its own val (optimistic), 0.47 on a never-trained cohort-1 clip; transfers to cohort-3 night CH01 by the user's eye. Round-1 cohort-3 labels (400 frames + 100-frame frozen blind test on night 09-05) being labelled by the undergrad with a WISER-guided, blind-first loop (`2026-10-06-wiser-label-loop.md`). |
| In-box detector | none; no in-box labels exist (cohort-1 in-box cameras were a different model). |
| WISER | default tracks V3 (head tag; still error ≈ 3 in; pairwise still-distance p95 ≈ 3 in); WISER → paddock map accepted on one CH01 hour (median 4.4 in, 88.5 % within 14 in vs control 2.9 %); tag ↔ animal identity verified against the head IMU (raw-WISER speed vs IMU activity, diagonal dominant on 09-06 and 09-08); **2-D only (`location_z` = 0)** → never who lies on top; box entry/exit events pass the operator's 09-05 ground truth (12 / 12 within 1–4 s, order exact); after 09-07 06:10 SF11 is untagged (house rosters are lower bounds). |
| Head IMU (neurologger, one per animal) | per-second state (still / active / locomoting), turn rate, pitch / roll, sleep scores (imu_remclean); an identity-linked motion signal independent of WISER and of video. |
| Colour flashes | 22 colour segments found in the video (CH07 1 / 13 / 7 on 09-09 / 10 / 11; CH08 only the 09-10 AM placement); the user clicked heads + ids on 11 of them (141 clicks on the colour frame and the IR frames 6 s / 15 s after) — analysis in §5. |
| Identity cues on the animal | identifying colour (user, final): SF07 green, SF08 red, SF09 black, SF10 blue, SF11 white/grey, SF12 yellow (`id_colour`, `wiser/configs/rat_identities_2026c.csv`); IR-visible patterns x / none / star / square-with-cross / circle / two lines; headstages. In-hand close-ups per animal (`$OUT/2026c/inhand_closeups/`). |
| Camera geometry | CH01–CH06 calibrated (frozen rev g) with per-night corrections; CH07/CH08 uncalibrated, move at every lid opening (corrections per lid segment), CH07 image = paddock rotated 180° (user). |
| Code scaffolds | `cv/animal_tracking.py` (cohort-1 stage-0 YOLO + ByteTrack → field cm, old homography; placeholder weights); the WISER-loop tools in the undergrad's repo. |

## 3. Proposed architecture: detect → tracklets → identity by evidence fusion

The operator's own field conclusion (pilot 09-09): in-box IR identity is possible only by **track-then-assign** —
follow an animal until its features show, then carry the identity along the track. The proposal turns that into an
explicit evidence-fusion problem over tracklets.

**L1 Detection (per frame).**
- Panoramas: the undergrad's YOLO loop (unchanged).
- In-box: a new IR detector (box, or instance mask for piles). Seed labels from the user's head clicks: head point →
  SAM3 point/box prompt → mask/box *proposal* → human accept/fix (SAM3 failed zero-shot on the panoramas because rats are
  ≈ 10–60 px there; in-box rats are hundreds of px, so it must be re-tested, not assumed). Training domain = IR; colour
  frames are an identity oracle, not training data (operator, 09-09).

**L2 Tracklets.** A standard tracking-by-detection association (ByteTrack / BoT-SORT / OC-SORT class) cut
conservatively: break a tracklet at every ambiguous occlusion, merge only with high confidence. Short, pure tracklets
beat long, mixed ones; identity is resolved one level up.

**L3 Identity assignment over tracklets** — a joint assignment (per house / per camera window) with hard constraints
(each animal at most once per frame; only animals in the WISER roster of that house or within the camera's view; SF11
untagged after 09-07) and four evidence terms:
- (a) **WISER**: roster (who can be here), field position (panoramas: projected circle, ≈ 4–7 in), in-box arrangement
  along the box (only if the pre-registered order test passes, §5), entry/exit events (identity at the door, ±1–4 s);
- (b) **Head-IMU motion match**: a tracklet's image motion (speed, turning, still vs moving) against each animal's IMU
  state and turn rate per second — the same diagonal-dominance logic that verified the WISER tags, applied to tracklets;
  strongest exactly where WISER is weakest (inside a pile, an animal that shifts or grooms);
- (c) **Appearance (IR re-ID)**: an embedding trained on identity-labelled IR crops harvested for free from (i) IR frames
  next to colour flashes, (ii) door crossings with a WISER box event, (iii) field frames where one WISER circle and one
  box coincide alone; patterns and headstages as the visible features;
- (d) **Temporal continuity**: identity is constant within a tracklet; transitions only at tracklet boundaries.
Solved as a constrained assignment per window (Hungarian / ILP), or as an HMM over tracklet labels; output per frame
the MAP identity and its posterior; low posterior → "unresolved".

**L4 Validation.** Held-out identity truth never used for training or tuning: a share of the colour flashes, the
box-event door frames of held-out days, user spot labels on random IR frames. Metrics: IDF1 / HOTA-style identity
metrics on labelled snippets, per-cue ablations (drop one cue at a time), error budget per layer.

## 4. Answers to the user's direct questions (to be confirmed by §5 numbers)

- **What the colour labels tell us:** (1) whether WISER's house composition is right (roster vs colours); (2) whether
  piles stay still across the colour → IR switch (which is what lets the IR frames inherit identity); (3) whether WISER's
  along-box order is real (pre-registered ≥ 4 / 5 test); (4) how often a WISER-only assignment would label the pile
  correctly (per-click accuracy vs WISER separation).
- **WISER as an identity aid:** yes for composition and door events today; for arrangement only if (3) passes; never for
  stacking (z = 0). Best used as one evidence term with the IMU, not alone.
- **Train YOLO with them?** Not directly: the colour frames are another domain and the clicks are head points, not boxes.
  They become training data indirectly: head points → SAM3 / human boxes on the **IR** neighbours → in-box detector
  labels; and identity-labelled IR crops → the re-ID model. Identity-as-class YOLO (six classes) is **not** proposed:
  few samples, piles, changing appearance — keep detection and identity separate.

## 5. The user's first colour labels (filled in when the analysis lands)

Pending: `results/2026c/cv_field/reports/cv_field_inbox_clicks_2026c.md` (composition agreement, colour → IR head
displacement, the pre-registered house_2 fit and order test, WISER-assignment accuracy). Data = a browser snapshot of
11 / 22 segments (not yet a formal export) → preliminary.

## 6. Next steps if the strategy is accepted (each its own pre-registered plan)

1. In-box detection seed set: IR frames next to every colour flash (both clicked and not) + WISER-stratified IR frames
   (house count × still/active × day/night × lid segment) + door-crossing frames; SAM3 head-prompt proposals; the
   undergrad labels boxes (+ optional id) in the existing blind-first GUI with a roster panel instead of circles.
2. Head-IMU ↔ tracklet motion likelihood: built and validated on panorama tracklets first (where WISER gives truth).
3. IR re-ID from the free identity crops; validated on held-out flashes.
4. The joint assignment; IDF1 / HOTA on held-out snippets; ablations.

## 7. Risks and do-not

- Circularity: WISER (or IMU) used to create identity labels must not also score the identity system on the same
  frames; keep held-out truth (colour flashes, user spot labels) separate.
- WISER rosters are lower bounds after 09-07 06:10 (SF11); the first days' colours are uncertain (user).
- In-box cameras move at lid openings; colour inserts are calibration events, not behaviour (exclude ON −1 s to
  OFF + 5 s from motion measures).
- No claims about who lies on top from WISER; arrangement only after the order test.
- Females (from 09-11 19:40) out of scope.

## 8. Questions for the SOTA audit

1. Is tracklet-level evidence fusion (WISER + head IMU + IR re-ID + continuity) the right architecture against current
   multi-animal / multi-object tracking practice (identity-preserving animal trackers such as idtracker.ai / TRex,
   multi-animal pose-and-identity such as SLEAP / maDeepLabCut, MOT trackers ByteTrack / BoT-SORT / OC-SORT /
   Deep OC-SORT, end-to-end MOT such as MOTR-family, promptable video segmenters such as SAM 2 / SAM 3 tracking, and
   sensor-assisted identity such as RFID + video for group-housed rodents)? What is missing or over-built?
2. What is the realistic identity accuracy in huddles / piles in comparable published systems, and with which sensors?
3. Off-the-shelf vs build: which components to adopt as they are, and with what minimum labels.
4. The evaluation protocol (metrics, held-out truth, ablations) — sound? What would a reviewer demand?
5. The YOLO question: separate detector + re-ID vs identity-as-class vs instance segmentation for piles.
