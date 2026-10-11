# SOTA audit: identity-aware detection and tracking strategy (cohort 3, SF07–SF12)

Auditor: Fable 5.1, 2026-10-10. Scope: `implementation_plan/2026-10-11-identity-tracking-strategy.md` (commit 5c696dd), the operator's `EXPERIMENT_ir_identity_color_sampling.md`, and the in-box section of `CAMERA_GEOMETRY_2026c.md`. Read-only; no code or data read. Every external number is marked **[V]** verified by reading the source today or **[U]** from memory / not retrievable.

## Executive summary

1. The architecture (detect → conservative tracklets → identity by evidence fusion with hard constraints) **is current practice** for visually similar animals with a non-visual tag: it is literally the design of Bains et al. 2023 (RFID + ILP over tracklets, mice), Henschel et al. 2019 (IMU + graph labelling, people, IDF1 91.2) and the 2025 DIPLOMAT / 2026 new-idtracker.ai line (identity over fragments). Pure-vision ID trackers (idtracker.ai, TRex) and end-to-end MOT (MOTRv2, MOTIP) are not the right comparators here.
2. No published system reports frame-level identity inside a tight rodent pile. The one directly comparable number (RFID + IR video, cluttered home cage) is **77 % identification accuracy**. Every system bounds the pile by *composition* + *propagation from the last visible moment* — exactly the operator's verdict. Plan for that ceiling.
3. The head-IMU motion-match term is **supported by prior work in humans** (video↔IMU assignment), **novel in rodents**. Its gain is concentrated at *micro-events* (one animal shifts while the others are still); in a static pile all IMUs read "still" and the term is uninformative. Budget it accordingly.
4. Missing: a pile-aware state space (group nodes with cardinality), flow conservation through the door, calibrated posteriors, explicit clock-offset uncertainty, and a proofreading tool. Over-built: a trained IR re-ID embedding at this label budget, and running both an HMM and an ILP.
5. Keep detection and identity separate (correct); do not use identity-as-class YOLO; do not label instance masks for piles — a pile class with a count and head points is enough. SAM 3/SAM 2 as a point-prompt *proposal* labeller for in-box frames: yes, after a 20-frame test.
6. The decisive experiment is the **flash-to-flash propagation test** on 09-10/09-11: propagate identity from flash k through the IR footage with free cues only, score at flash k+1, then add the IMU term and measure the delta. It costs ~100 detector labels and no new truth, and it decides whether the arrangement layer exists before any re-ID is built.

---

## Q1. Architecture vs current practice

**Verdict: right family, two structural gaps, two over-builds.**

What the comparators actually are:

| Family | What it assumes | Fit here |
|---|---|---|
| idtracker.ai / TRex | animals frequently segmentable alone; identity learned from "individual fragments" | 99+ % only on fish/insects: TRex Table 2 [V] 100 zebrafish 99.07 %, 59 flies 99.68 %, 15 locusts 95.1 %; idtracker.ai 98.95–99.94 % on the same. Nothing on piles. New idtracker.ai 2026 [V] drops the "all visible" requirement (contrastive fragments, 700× faster, mice included) — a candidate *fragment-identity* engine, no huddle numbers. |
| SLEAP ID / maDLC | SLEAP docs [V]: ID models only for "distinct, consistent appearances"; maDLC [V]: marmoset ID > 0.99 at head keypoints, stitching cuts switches 63 %, appearance a further 26 % | maDLC's stitching over tracklets + ReID is the L2/L3 pattern. Pose is not needed here. |
| MOT trackers | ByteTrack MOT17 HOTA 63.1 / IDF1 77.3 [V]; BoT-SORT 65.0 / 80.2 [V]; DanceTrack: ByteTrack 47.3, OC-SORT 54.6–55.1, Deep OC-SORT 61.3 [V]; AnimalTrack best QDTrack 47.0, ByteTrack 40.1 [V] | Produce *tracklets*, not identity over hours. DanceTrack (uniform appearance, non-linear motion) is the honest proxy: ~55 HOTA motion-only → tracklets will break; "cut conservatively" is right. |
| End-to-end MOT | MOTRv2 DanceTrack 73.4 [V]; MOTIP (CVPR 2025) 69.6 without extra data [V], 73.7 with [V, leaderboard] | Thousands of labelled frames per domain; clip-local association. Not applicable. |
| SAM 2 / SAM 3 | SAM 3 [V]: SA-Co/Gold cgF1 54.1 vs human 72.8; video pHOTA 58.0 vs human 70.5. SAMURAI [V] +7.1 AUC LaSOT_ext | Labelling and short-horizon tracklet growth, not identity. The plan uses them that way — correct. |
| Sensor-assisted identity | Bains 2023 [V]: RFID + IR video, ILP over tracklets, **77 %**; LMT 2019 [V]: depth + RFID, ≤ 4 mice (accuracy [U]); Henschel 2019 [V]: IMU ↔ detections, graph labelling, **IDF1 91.2 %**; Masullo 2019 [V]: silhouette ↔ accelerometer, AUC 76.3 % | **The plan's family.** It adds what the literature lacks together: a positional roster (WISER) and a per-animal IMU. |

**Missing (add):**
1. **A pile-aware state space.** L2 emits *group tracklets* (blob + count estimate) as nodes; L3 assigns a *set* of identities to a group node (composition), arrangement only optionally. Otherwise piles yield phantom single tracklets or nothing.
2. **Flow conservation through the door.** Replace per-window assignment with a min-cost-flow / ILP over the whole lid-closed segment: animals enter and leave only via door tracklets; the WISER roster count is a hard count. This is what lets Bains-style systems reject spurious detections [V].
3. **Clock-offset uncertainty as a likelihood term.** Video = field-PC time, WISER = Unix-ms, IMU = pc_time chain; model the offsets (door events already give ±1–4 s) and keep the +1 h shifted negative control.
4. **Calibrated posteriors.** "Low posterior → unresolved" needs a reliability diagram on held-out truth.
5. **A proofreading loop.** Every shipping identity tracker (DIPLOMAT 2025 [V]: whole-body swaps 1.8 → 0.29 with Viterbi + editing) assumes a human fixes residual swaps; the operator's `ir_identity_labeler.html` is the seed.
6. **Head-vs-body motion model in term (b).** The repo's V6 finding (head acceleration ≈ 4× body) makes continuous speed matching noisy; use discrete IMU states and turn *events* against tracklet motion classes.

**Over-built (cut or defer):**
- A trained IR re-ID embedding "harvested for free". Six animals, monochrome IR, headstage-dominated appearance, most frames asleep: a metric-learning model will mostly learn position and pose. Start with a frozen DINOv3 + linear probe per animal (which the repo already runs for the gate), escalate only if it beats chance on held-out flashes.
- Both an HMM and an ILP. One global formulation (ILP / min-cost flow with unary + pairwise terms) is enough.
- Panorama IMU–tracklet matching as a *production* cue: there WISER already gives identity within 4.4 in median [plan §2]; use the panoramas to validate the IMU term, not to deploy it.

**Expected gain / cost:** the structural changes are days of design, no labels; they convert "unresolved" from a threshold into a stated state. The over-builds would cost weeks and the most label-hungry component.

## Q2. Identity accuracy in huddles: what is published

**Verdict: no system publishes frame-level identity inside a tight rodent pile; the realistic target is composition ≈ roster accuracy, door identity exact, arrangement ≈ 75–90 % on loose piles propagated from a visible moment, and an honest "unresolved" for buried reshuffles.**

- RFID + IR video, cluttered home cage, tracklet ILP: **77 %** identification accuracy; rejects spurious detections when animals are hidden (Bains et al., MVA 2023) [V]. The closest published setting.
- Depth + RFID, ≤ 4 mice, days (LMT 2019) [V]; identity numbers [U]. RFID reads correcting video identity at readers = the door-event analogue.
- maDLC marmosets: ID > 0.99 at head keypoints; switches remain (−63 % stitching, −26 % appearance) [V]; no huddle number [U].
- DIPLOMAT 2025 (mice): identity recall 0.98, 0.29 full-body swaps per configuration [V], with proofreading as the workflow.
- Unmarked mice with implants, 3D, darkness, ~2 mm at 60 fps (Ebbesen & Froemke 2022) [V]: dyads only; the headstage as a trackable feature is the precedent for your animals.
- Fish/insect ID trackers: 95–99.9 % [V], no pile regime.

**IMU motion matching — supported or novel?** Supported in humans: Henschel et al. 2019 assign detections to body-worn IMUs via a learned detection↔orientation affinity and a global graph labelling, IDF1 91.2 %, beating appearance where appearance is uninformative [V]; Masullo et al. 2019 match 3-s silhouette clips to accelerometer signals, AUC 76.3 % [V]. In animals I found accelerometer↔video work only for *behaviour labelling* (cattle, sheep), not identity assignment [V, absence]. **Closest prior work: Henschel et al. 2019 (method) and Bains et al. 2023 (problem).** The rodent-pile application is novel.

**Expected gain, honestly:** the repo's diagonal (Spearman 0.46–0.55 vs 0.23–0.44 off-diagonal) is a modest margin per animal-night; at tracklet scale the term is decisive only when IMU states *differ* across the roster. In a sleeping pile every IMU says "still" — zero information. The gain is at transitions (a shift, a groom, a head turn, an exit), exactly where the operator says labels are won or lost. Quantify it by *distinctness coverage*: the fraction of pile-seconds with ≥ 1 roster animal non-still while the rest are still; if < 10 %, the IMU term is a tie-breaker, not a backbone. Cost: no labels, moderate engineering.

## Q3. Adopt vs build, in order, with minimum labels

1. **In-box detector — adopt** YOLO11 (box) fine-tuned on IR. Classes `rat`, `pile` (count 2–6), optional `head` keypoint. Labels: ~150 single-animal + ~60 pile frames stratified by roster count × still/active × lid segment; stop when held-out AP plateaus. Seed with SAM 3 / SAM 2 point prompts from the head clicks as *proposals* (Q5).
2. **Tracklets — adopt** BoT-SORT or OC-SORT (Ultralytics); zero labels. Tune for purity (strict match, short max-age); break at every merge with a pile node.
3. **Door identity — build (small)**: WISER box events (12/12 within 1–4 s, order exact) ↔ door-crossing tracklets. Labels: none beyond the 09-05 truth; add the 09-10 colour placement as a second truth day.
4. **Global assignment — build**: min-cost flow / ILP per lid-closed segment with roster count, door events and continuity; this alone yields composition and door-anchored arrangement. Labels: none; validated on flashes.
5. **IMU term — build**, validate on panorama tracklets first (WISER = truth), then as an additional unary in step 4. Labels: none.
6. **Appearance — adopt frozen DINOv3 + linear probe** on identity-labelled crops from door events and flash-adjacent IR frames; hold out whole flash episodes. Escalate to a trained re-ID only if the probe beats chance by a clear margin. Labels: free crops + the flashes.
7. **Proofreading — adopt** the operator's labeler / the undergrad GUI with a roster panel; this is where residual swaps get fixed and where additional truth comes from cheaply.

Not worth adopting here: idtracker.ai/TRex as the identity engine (they assume separability), MOTR/MOTIP (label cost, clip-local), SIPEC (primate/mouse ID by appearance; numbers not retrievable [U]).

## Q4. Evaluation protocol

**Sound in outline; a reviewer will demand the following additions.**

Metrics, reported separately:
- **IDF1** and **HOTA** with **AssA** broken out [V, definitions]; **per-frame identity accuracy per animal**, **composition accuracy** per house-segment, **arrangement accuracy** on loose piles, **track purity**.
- The key figure: **accuracy vs coverage** as the posterior threshold moves. An "unresolved" state is only honest on that curve.
- **Calibration** (reliability diagram, ECE); **error budget per layer** (detector misses, tracklet breaks, wrong assignments, by cue).

Held-out truth: split by **flash episode and by day**, never by frame (a static pile is one sample per flash); hold out 09-11 entirely and whole episodes within 09-10; door frames of held-out days; user spot labels on random IR frames stratified by pile state; **two raters on a subset** for agreement.

Ablations: drop each cue; WISER-only; IMU-only; appearance-only; no continuity; degraded roster (an SF11-style missing tag); **+1 h time-shifted IMU and WISER** as negative controls.

Circularity traps specific to this plan:
1. WISER selects the frames to label *and* scores the result → the score inherits WISER's blind spots (piles). Score on flash/spot labels only.
2. Flash-adjacent IR frames used to train appearance *and* to test it within the same static episode.
3. Propagating from flash k and scoring inside the *same* static episode inflates accuracy to ~100 %; score after a reshuffle or at the next independent flash.
4. The operator's "track-then-assign" verdict treated as truth for the system it motivated.
5. Tuning the "unresolved" threshold on the test split.
6. The strategy says SAM 3 failed on panoramas because rats are "≈ 10–60 px"; §2 says 70–160 px native — reconcile before calling it a size effect (it may be an inference-resolution effect).

## Q5. The YOLO question

- **Separate detector + identity: correct.** Identity-as-class needs "distinct, consistent appearances" (SLEAP docs [V]); the one lab case that works well is face-level marmoset ID (YOLOv8, precision > 82.9 %, recall > 91.5 % [V]). Six IR-monochrome rats with changing tape, a shared headstage look, and mostly sleeping poses are the opposite case; a six-class YOLO would memorise house position and lid segment.
- **Instance segmentation for piles: no.** Masks do not resolve who is who; they cost 5–10× the labels (MouseSIS, up to seven mice, exists precisely because this is hard [V]). What L3 needs from a pile is a node with a count and, when visible, head points. Add masks only if a later contact-topology question needs them.
- **SAM 3 as a point-prompt labeller for in-box frames: yes, as proposals.** In-box rats are hundreds of px, the regime SAM 2/3 handles; human accept/fix is already in the plan. Test on 20 frames (10 single, 10 pile) before committing; expect merged masks in piles → take the box, discard the mask.

## Q6. The single most decisive next experiment

**Flash-to-flash identity propagation (CH07, 09-10 → 09-11).** Use consecutive flashes of the same house (≈ 90-min spacing, 7 on 09-10, more on 09-11) as oracle pairs. From flash k, run L1 + L2 on the intervening IR footage and the global assignment with *free cues only* (roster count, door events, continuity); score identity at flash k+1 by the user's clicks. Then add the IMU term and re-score. Report: survival rate to the next flash, by whether the pile reshuffled in between (from the motion trace), and the IMU delta.

Why decisive: it measures the one quantity the arrangement layer rests on — how far identity survives tracking through a pile — on existing truth, with ~100 detector labels and no re-ID. Survival near chance after a reshuffle and no IMU lift → the arrangement layer is closed; the deliverable is composition + door identity (already near-complete from WISER). Survival → re-ID and the full ILP are justified. The plan's panorama IMU–tracklet validation is useful but not decisive.

## Do not do

- No identity-as-class YOLO; no instance masks for piles.
- No metric-learning IR re-ID before the linear probe beats chance on held-out flashes.
- No scoring inside the static episode the labels came from, or on WISER-selected frames.
- No posteriors as confidence until calibrated; no tuning the "unresolved" threshold on test data.
- No continuous IMU speed vs tracklet speed (head ≠ body); states and events only.
- No claims about who lies on top or arrangement inside a reshuffled buried pile.
- No HMM *and* ILP; one global formulation.
- No end-to-end MOT or pure-vision ID tracker as the identity engine.

## References

- Romero-Ferrero et al., idtracker.ai, Nat Methods 2019 — [V] "high identification accuracy for collectives of up to 100 individuals"; 99.96 % (60 zebrafish), 99.99 % (100), 99.99 % (38 flies), 99.95 % (72) [V, press coverage]. https://www.doi.org/10.1038/s41592-018-0295-5
- Torrents, Costa, de Polavieja, New idtracker.ai, eLife 2026 (reviewed preprint 107602) — [V] contrastive fragments, up to 700× faster, no all-visible segments. https://elifesciences.org/reviewed-preprints/107602
- Walter & Couzin, TRex, eLife 2021, Table 2 — [V] 99.07 % (100 zebrafish), 99.68 % (59 flies), 95.1 % (15 locusts), 99.7 % (10 termites). https://elifesciences.org/articles/64000
- Lauer et al., maDLC, Nat Methods 2022 — [V] marmoset ID > 0.99 (head keypoints); switches −63 % (stitching), −26 % (appearance). https://pmc.ncbi.nlm.nih.gov/articles/PMC9007739/
- Pereira et al., SLEAP, Nat Methods 2022; SLEAP-NN docs "Supervised ID models" — [V] use only for distinct, consistent appearances. https://nn.sleap.ai/dev/guides/supervised-id/
- DIPLOMAT, bioRxiv Aug 2025 — [V] whole-body swaps 1.8 → 0.29 (DLC), identity recall 0.98. https://pmc.ncbi.nlm.nih.gov/articles/PMC12407788/
- Zhang et al., ByteTrack, ECCV 2022 — [V] MOT17 MOTA 80.3 / IDF1 77.3 / HOTA 63.1. https://arxiv.org/abs/2110.06864
- Aharon et al., BoT-SORT 2022 — [V] MOT17 80.5 / 80.2 / 65.0. https://arxiv.org/abs/2206.14651
- Cao et al., OC-SORT, CVPR 2023 — [V] MOT17 HOTA 63.2; DanceTrack 54.6 (vs ByteTrack 47.3). https://arxiv.org/abs/2203.14360
- Maggiolino et al., Deep OC-SORT 2023 — [V] DanceTrack HOTA 61.3 (OC-SORT 55.1, ByteTrack 47.3); MOT17 64.9. https://arxiv.org/abs/2302.11813
- Zhang et al., MOTRv2, CVPR 2023 — [V] DanceTrack HOTA 73.4. https://arxiv.org/abs/2211.09791
- Gao et al., MOTIP, CVPR 2025 — [V] DanceTrack HOTA 69.6 (no extra data, model zoo); 73.7 with val + CrowdHuman [V, leaderboard mirror]. https://github.com/MCG-NJU/MOTIP
- Zhang et al., AnimalTrack, IJCV 2023 — [V] QDTrack HOTA 47.0 best; ByteTrack 40.1. https://arxiv.org/abs/2205.00158
- Ravi et al., SAM 2, 2024 — [V] memory-based promptable video segmentation. https://docs.ultralytics.com/models/sam-2/
- Meta, SAM 3: Segment Anything with Concepts, Nov 2025 — [V] SA-Co/Gold cgF1 54.1 (human 72.8); SA-Co/VEval pHOTA 58.0 (human 70.5). https://github.com/facebookresearch/sam3
- Yang et al., SAMURAI, 2024 — [V] +7.1 AUC LaSOT_ext, +3.5 AO GOT-10k over SAM 2. https://arxiv.org/abs/2411.11922
- Bains et al., Persistent animal identification leveraging non-visual markers, Machine Vision and Applications 2023 — [V] RFID + IR video, ILP, 77 % identification accuracy. https://arxiv.org/abs/2112.06809
- de Chaumont et al., Live Mouse Tracker, Nat Biomed Eng 2019 — [V] depth IR + RFID, up to 4 mice, days; identity-accuracy figure [U]. https://www.nature.com/articles/s41551-019-0396-1
- Peleh et al., RFID-supported video tracking, J Neurosci Methods 2019 — [V] system description; no accuracy in abstract [U]. DOI 10.1016/j.jneumeth.2019.108323
- Henschel, von Marcard, Rosenhahn, Simultaneous identification and tracking of multiple people using video and IMUs, CVPRW 2019 — [V] IDF1 91.2 %. https://openaccess.thecvf.com/content_CVPRW_2019/html/BMTT/Henschel_Simultaneous_Identification_and_Tracking_of_Multiple_People_Using_Video_and_CVPRW_2019_paper.html
- Masullo et al., Who goes there?, ICCVW 2019 — [V] silhouette ↔ accelerometer, AUC 76.3 %, 3-s clips. https://openaccess.thecvf.com/content_ICCVW_2019/papers/CVPM/Masullo_Who_Goes_There_Exploiting_Silhouettes_and_Wearable_Signals_for_Subject_ICCVW_2019_paper.pdf
- Ebbesen & Froemke, Nat Commun 2022 — [V] unmarked mice with implants, 3D, darkness, ~2 mm at 60 fps. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8807631/
- Marks et al., SIPEC, Nat Mach Intell 2022 — [V] IdNet outperforms idtracker.ai within/across sessions; exact accuracy [U]. https://pmc.ncbi.nlm.nih.gov/articles/PMC7612650
- MouseSIS, 2024 — [V] space-time instance segmentation of up to 7 mice with occlusion. https://arxiv.org/abs/2409.03358
- Marmoset YOLOv8 identity (eLife reviewed preprint 110932) — [V] precision > 82.9 %, recall > 91.5 %, face-level. https://elifesciences.org/reviewed-preprints/110932
- Luiten et al., HOTA, IJCV 2021; Ristani et al., IDF1, ECCVW 2016 — [V] definitions. https://arxiv.org/abs/2009.07736
- Koger et al., J Anim Ecol 2023 (drones + CV, ungulates/geladas) — [V] exists; GPS↔video assignment numbers [U].
