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
| WISER | default tracks V3 (head tag; still error ≈ 3 in; pairwise still-distance p95 ≈ 3 in); WISER → paddock map accepted on one CH01 hour (median 4.4 in, 88.5 % within 14 in vs control 2.9 %); tag ↔ animal identity verified against the head IMU (raw-WISER speed vs IMU activity, diagonal dominant on 09-06 and 09-08); **2-D only (`location_z` = 0)** → never who lies on top; box entry/exit events pass the operator's 09-05 ground truth (12 / 12 within 1–4 s, order exact); every animal in the paddock carries a tag until 09-11 19:40 — SF11 kept tag 3058 after its implant fell off (09-07 ≈ 06:10) and was taken out of the paddock at the 09-07 AM round (last regular fix 08:20), so 09-07 08:20 → 09-11 19:40 = five animals, all tagged (user 2026-10-11; field incident log 09-07); rosters are incomplete only during tag dropouts (SF11's 305a 09-02 00:03 → ≈ 08:00, SF12 night 08-30/31). |
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
  SAM3 point/box prompt → mask/box *proposal* → human accept/fix (SAM3 failed zero-shot on cohort-1 panorama frames —
  rats ≈ 65 px, cause not established, see §9; in-box rats are hundreds of px, so it must be re-tested, not assumed). Training domain = IR; colour
  frames are an identity oracle, not training data (operator, 09-09).

**L2 Tracklets.** A standard tracking-by-detection association (ByteTrack / BoT-SORT / OC-SORT class) cut
conservatively: break a tracklet at every ambiguous occlusion, merge only with high confidence. Short, pure tracklets
beat long, mixed ones; identity is resolved one level up.

**L3 Identity assignment over tracklets** — a joint assignment (per house / per camera window) with hard constraints
(each animal at most once per frame; only animals in the WISER roster of that house or within the camera's view; tag-dropout
windows excepted) and four evidence terms:
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

Report `results/2026c/cv_field/reports/cv_field_inbox_clicks_2026c.md` (commit e679650). **Preliminary**: a browser
snapshot (11 / 22 segments, one labeller, house_2 / CH07 only); blind colour-frame clicks only (135 blind of 141).
- **Composition:** clicked colour-frame set = WISER house_2 roster in 8 / 10 revealed segments, no extras; in the other
  two every roster animal is clicked on some frame of the segment. SF11 never clicked.
- **Colour → IR stability:** median head displacement 27 px (≈ 0.3 in) over < 30 s; **max 44 px when every animal's head
  IMU stayed still** (n 36) vs median 52 / max 387 px when the IMU registered movement (n 24) → the operator's premise
  (a still pile does not move across the switch) holds, and the IMU tells when it does not.
- **Camera fit (house_2):** non-mirrored similarity, rotation 178° in the page's terms (the user's independent 180° by eye,
  Δ −1.8°), 79.3 px / in; leave-one-flash-out RMS **5.96 in** (median 4.29 in); not a calibratable bias (per-flash offset
  → 5.34 in, per-tag offset → 6.35 in).
- **Pre-registered order test: NOT ACCEPTED** — exact along-box order 0 / 5 (Kendall τ median + 0.40); with pairs < 8 in
  treated as ties 4 / 5 (25 / 28 such pairs ordered right) but that variant also fails under the sensitivity checks.
- **WISER as an identity aid:** one-to-one assignment of clicked heads to WISER means 65 % correct (26 / 40; chance 20 %;
  72 % with a free per-flash offset); by separation from the nearest other animal: < 4 in 70 %, 4–8 in 60 %, 8–15 in 50 %,
  ≥ 15 in 4 / 4. Piled animals sit a median 5.7 in apart but only 2.0 in apart along the ridge.
- **Reading:** WISER gives composition and places clearly separated animals; it does **not** resolve the arrangement
  inside a pile. The arrangement layer must come from vision + continuity (+ IMU micro-events), as the audit predicted;
  WISER stays a roster / door / separation prior.

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
- WISER rosters are incomplete only during tag dropouts (SF11's 305a 09-02 00:03 → ≈ 08:00; SF12 night 08-30/31); the first
  days' colours are uncertain (user). (An earlier version of this plan wrongly said SF11 stayed in the paddock untagged after
  09-07; corrected 2026-10-11, see §11.)
- In-box cameras move at lid openings; colour inserts are calibration events, not behaviour (exclude ON −1 s to
  OFF + 5 s from motion measures).
- No claims about who lies on top from WISER; arrangement only after the order test.
- Females (from 09-11 19:40) out of scope.

## 9. Response to the Fable SOTA audit (2026-10-11)

Audit: `results/2026c/cv_field/reports/cv_field_identity_strategy_fable_audit_2026-10-11.md` (Fable 5.1, ~25 sources,
each marked verified / unverified). Verdict: right family (sensor-assisted tracklet identity, as in Bains et al. 2023
RFID + ILP 77 %, Henschel et al. 2019 video + IMU IDF1 91.2 %); no published system reports frame-level identity inside
a tight rodent pile — the realistic deliverable is composition + door identity, arrangement on loose piles propagated
from a visible moment, and an honest "unresolved". Accepted changes (coordinator's assessment; the user decides):
- **Pile-aware state space**: L2 emits group nodes (blob + count); L3 assigns a *set* (composition) to a group node,
  arrangement only optionally.
- **One global formulation**: min-cost flow / ILP per lid-closed segment, animals enter and leave only through door
  tracklets, WISER roster count as a hard count, continuity as pairwise terms — replaces "Hungarian per window or HMM".
- **Clock offsets** (video / WISER / IMU) as an explicit likelihood term; +1 h shifted negative controls kept.
- **Calibrated posteriors** (reliability diagram, ECE) before any "unresolved" threshold; accuracy-vs-coverage curve as
  the headline figure.
- **IMU term = discrete states and turn events vs tracklet motion classes, never continuous speed** (V6: head
  acceleration ≈ 4× body); its information is confined to micro-events → report "distinctness coverage" (share of
  pile-seconds with ≥ 1 roster animal non-still while the rest are still); < 10 % → tie-breaker only. On the panoramas it
  is validated, not deployed.
- **Appearance: a frozen DINOv3 + linear probe** on free crops first; a trained IR re-ID only if the probe beats chance
  on held-out flash episodes.
- **Proofreading loop** (the operator's labeler / the undergrad GUI with a roster panel).
- **In-box detector classes** `rat`, `pile` (count 2–6), optional `head` point; ~150 single + ~60 pile frames; SAM 3 / SAM 2
  point-prompt proposals after a 20-frame test (take the box, drop merged masks); no instance masks, no identity-as-class.
- **Evaluation**: IDF1, HOTA with AssA, per-frame / composition / arrangement accuracy, track purity, per-layer error
  budget; held out by flash **episode and day** (09-11 entirely), two raters on a subset; never score inside the static
  episode the labels came from, never on WISER-selected frames; drop-one-cue, WISER-only / IMU-only / appearance-only,
  degraded-roster ablations.
- **Correction (audit item):** §3 said SAM3 failed on the panoramas because rats are "≈ 10–60 px". The SAM3 test used
  cohort-1 frames with rats ≈ 65 px native; the 2016 → 1008 tiles (rats ≈ 32 px) scored *better* (AP 0.40) than the
  native 1008 tiles (0.23) → not established as a size effect (inference resolution / domain are open).
- **Decisive next experiment (the audit's Q6), proposed:** flash-to-flash identity propagation on CH07 09-10 → 09-11 —
  from flash k, detect + tracklets + global assignment with free cues only (roster count, door events, continuity),
  score at flash k + 1 by the user's clicks; add the IMU term and measure the delta; stratify by whether the pile
  reshuffled. Needs the in-box detector (~100 labels) and the clicks; decides whether the arrangement layer exists
  before any re-ID is built.

## 10. Text review by the Codex session "Yolo_identity" (2026-10-11, read-only, ≤ 500 characters per point)

Thread `01a12853-ba1a-7c93-ab0a-82792f818e2d` (queued with the user's agreement; reply verbatim in its rollout).
1. **Agrees with the architecture but not with WISER roster / count as a HARD constraint** — SF11 untagged, dropouts and
   missed door events need tolerance; keep an unknown-identity slot and group nodes; re-anchor across lid segments; an ILP
   optimum is not a trustworthy posterior. **Conflict with the Fable audit** (which proposed the roster count as a hard
   count). Coordinator's resolution, for the user to confirm: hard only for "one animal, one place per frame"; the roster
   enters as a strong soft term with an "unknown" slot opened only in tag-dropout windows and for unexplained detections;
   posteriors from calibration, not from the ILP optimum.
2. 150 single + 60 pile frames are fine for a pilot if they span independent episodes, before / after lid openings and
   empty houses; `head` needs a keypoint head (not a box class); the pile class does not output a count — label the
   count separately and allow "unknown"; define the single-vs-pile overlap rule so nothing is counted twice; a SAM box
   that merges two rats is never a single-rat box; 20-frame test with manual fixes first.
3. **First experiment = flash-to-flash propagation**, with: initialise at the first flash; **seal the end flash's
   identities** (never inside the global solve); add **blind labels between flashes** to catch "swap then swap back";
   stratify by reshuffle, entries / exits, lid openings; with / without IMU; a failure on a small sample only rejects the
   current scheme.
4. Further risks: DINO learning position / background; selection bias of flash and still samples; double-counting
   correlated evidence; small short-term displacement ≠ long-term identity; CH07 results do not transfer to CH08; the
   literature's 77 % is not this project's ceiling; correct flash endpoints ≠ correct throughout.

## 11. Correction (user, 2026-10-11): SF11 was never in the paddock untagged

The user: "SF11 has tag — Codex said is wrong". The premise came from this plan (and plan 2026-10-10 inbox p0), not from
Codex. Field record (`field2026-sync/from-field/2026-09-21_cohort3-incident-log.md`, 09-07 entries): "Rat SF11 stays in the
group: WISER tag 3058 and video/behavior continue; only the ephys stream ends"; then "tag 3058 (SF11) last regular fix
2026-09-07 08:20 … the animal left the arena at the round"; and the 09-11 19:40 entry "population 5 -> 10". So the tag
stayed on the rat after the implant fell off (≈ 06:10), the rat left the paddock at the 09-07 AM round, and from 08:20 to
09-11 19:40 the paddock held five tagged animals. Consequences: (i) the WISER house roster is complete outside tag-dropout
windows → the Fable proposal (roster count as a hard count) is closer to right than this plan's first resolution; the
remaining tolerance is for dropouts and missed door events (Codex's other two reasons stand); (ii) the click analysis's
caveat "rosters are lower bounds after 09-07" does not apply; (iii) to check separately: the production default tracks
flag SF11's fixes 09-07 06:10:45 → 08:20 as `m_off_animal`, but the field note says 07:40 → 08:20 "is still real position
data for the rat" — the flag may be wrong (positions themselves are unaffected).

**Update from the formal export (2026-10-11, clicks report re-run, export primary):** in 3 of 20 segments the WISER house
roster listed animals the user did not see in the house (09-10 08:37 SF08 + SF09, 09-11 09:28 SF10, 09-11 09:54 SF12);
at the colour frame WISER put three of them 5.1–8.8 in OUTSIDE the house body, inside the 15-in dilation that counts as
"in the house" (the fourth inside). No clicked animal was ever missing from a roster. So the roster **over-counts animals
just outside the door**: the roster constraint must allow a door-zone "maybe outside" state (or use a tighter boundary
at the door) — Codex's call for tolerance stands, for this reason rather than SF11. (My earlier explanation — roster
taken over the minute before the segment — was wrong: the page's roster is the state at the colour frame; only the
positions use the preceding minute.)

## 12. In-box labelling strategy after the user's observation (2026-10-11, proposed)

The user: "虽然是pile 但依然还是能分清谁是谁的。重点确实是分辨头在哪里" — even in a pile the user can tell who is who; the
crux is locating the heads. The audit's and Codex's `pile` class assumed individuals are often unresolvable inside a pile;
that assumption is weaker than thought, so the label unit becomes the **individual, head first**:
- **Per rat:** a **head point** (required; it is where the WISER tag and the head IMU sit and where the identifying marks
  and headstage are), a **body box** of the visible extent (approximate allowed inside a pile), optional tail-base point,
  an occluded flag, optional identity. A `cluster` box with a count only as an escape for the rare truly unresolvable
  case. Frame level: number of rats in the house (pre-filled from the WISER roster, confirmed by the labeller).
- **Easy → hard applies to which frames, not to the label type:** (1) seed — the ≈ 200 IR head clicks already made
  (+ 6 s / + 15 s after the flashes, with identities) get body boxes from SAM 3 point-prompt proposals + correction;
  (2) 1–2 rats in the house (WISER count), apart; (3) loose piles of 3–5, still; (4) tight piles and transitions
  (entries / exits, reshuffles, grooming), lid-segment edges, day and night. A first model after (2)–(3) pre-labels (4).
- **Model:** one class `rat`, YOLO11-pose (box + head keypoint [+ tail base]); head localisation scored as head recall
  within a pixel radius and per-pile head count vs the roster; identity stays separate (head crops for appearance,
  tracking + door events for propagation).
- **Active selection:** frames where the detected head count differs from the WISER roster count (reliable outside tag
  dropouts) are the labelling priority.
- **Who:** the user labels the hard frames and the held-out truth (only the user tells piled individuals apart reliably so
  far); the undergrad the easy / medium frames with pre-labels; a two-rater subset for agreement.
- **Tool:** the undergrad's labeller draws boxes but has no keypoints — a head-point + id layer is needed (the identity click
  page already does points + ids).
- Held-out: day 09-11 and whole flash episodes, as in §9.

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
