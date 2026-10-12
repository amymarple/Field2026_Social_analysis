# In-box CH07 / CH08: SAM 3 "rat" masks as pre-labels — a dev edit pilot (B) and a frozen test on new frames (C)

Date: 2026-10-12. Status: **approved by the user** ("行干吧 ABC都来 我给你标注", 2026-10-12). Part B runs now on frames already
seen. Part C is written before any C frame is chosen or processed. Its settings are frozen in an amendment after B,
committed before SAM 3 sees a C frame. The Codex session *Yolo_identity* reviews C as text before the C frames are
drawn.

Related: test plan [2026-10-11-inbox-sam3-dinov3-test.md](2026-10-11-inbox-sam3-dinov3-test.md) (Amendment 5 = the
correction below), report [cv_field_inbox_sam3_dino_2026c.md](../results/2026c/cv_field/reports/cv_field_inbox_sam3_dino_2026c.md),
identity strategy [2026-10-11-identity-tracking-strategy.md](2026-10-11-identity-tracking-strategy.md) §12 (head-first
labelling).

## A — why: the T1 reading was too strong (correction, 2026-10-12)

- **Old reading.** "SAM 3 text prompts do not find the in-box rats zero-shot."
- **What the test actually checked.** The pre-registered rule chose the prompt and τ by pooled F1 over **all** masks. A
  mask on no head point counted as a false positive. That rule picked "hooded rat" at τ 0.01, a prompt that returns few
  masks, and gave head-point exclusivity X = 8 % on test IR.
- **What the same cache shows for "rat".**
  - Test IR, at its own dev-best τ 0.03: X 50.7 %, recall 52 %, 88 % of 906 masks on no head.
  - 10 exploratory IR frames at τ 0.01: 38 / 49 heads with their own mask, 5 missed, 684 / 783 masks on no head point.
  - The same 10 frames at τ 0.25: 47 / 49 heads missed.
  - So the rat masks score low (mostly 0.01–0.25), and **no global score threshold separates them from the rest; recall
    itself is high**.
- **The user's verdict** (prompt GUI, 2026-10-12): with "rat", the rats are labelled, and the extra masks are mostly
  garbage.
- **Codex *Yolo_identity* (2026-10-12), corrected wording:** "The pre-registered prompt-and-threshold selection did not
  meet the bar for a stand-alone detector. Low-τ 'rat' covered most head points on the exploratory frames and may serve
  as a candidate generator; the quality of whole-rat masks is not yet verified." Its cautions:
  - a mask on no head point is not automatically garbage — it may be a fragment of a rat;
  - the blind 40-mask review used "hooded rat" for its text-prompt items and cannot stand in for "rat".

## The question for B and C

Can SAM 3 "rat" masks, anchored on the labeller's head clicks, make the in-box body labels faster without lowering
their quality? The body label is a head point plus a body box per rat, i.e. the YOLO-pose label of strategy §12.

Head anchoring removes the garbage problem: a candidate is offered only where a head was clicked. A mask that covers
no head is never shown in the default view.

## Definitions (fixed now; Codex item 4 — the user may revise them before starting B, and the revision is recorded)

- **Final label per rat:** the head point plus the body box. The chosen mask is kept when one was used.
- **Body box:** the visible body without the tail. Occluded parts are not inferred.
- **Usable mask:** covers the visible body of exactly ONE rat (head when visible, plus trunk) and no part of another
  rat; its box may still need small edge moves.
- **Merged:** covers parts of ≥ 2 rats.
- **Partial:** clearly misses a large part of that rat's visible body (e.g. only the head, only the hindquarters).
- **Garbage:** on no rat. **Fragment:** on part of a rat but not offered for it (judged only in the optional "show all"
  view).

## B — dev edit pilot on frames already seen (no claims; everything here is dev)

- **Frames:** the 58 frames of run `cv_field_inbox_sam3_dino_20261010_2320` (38 IR, 20 colour; CH07, 09-09…09-11). All
  are now dev, because the user and the agent have seen them.
  - Order: IR first, then colour, shuffled within each domain (seed 20261012).
  - The user may stop at any time; whatever is done is the pilot.
- **Candidates:** prompt "rat" (P1), whole frame, every cached mask (score ≥ 0.01, the cache floor). No other filter;
  tiled masks are not used.
- **Anchoring:** the user's blind head clicks (`heads.csv`, 284) are shown as dots.
  - For each head the page first offers the highest-score candidate whose mask lies within 15 px of the point (the T1
    coverage rule).
  - "Next" cycles through the other candidates covering the point, in score order, and then "none usable".
  - The user can add a rat whose head is hidden (click the body; candidates covering that point are offered), and can
    delete a dot that is not a rat.
- **Arms** (seeded, stratified by domain and by the frame's largest pile size: 1 / 2–3 / 4+):
  - PRELABEL (2/3 of frames): accept / next / flag merged / flag partial / move box edges / draw a box by hand.
  - SCRATCH (1/3): dots shown, no masks; the user drags one box per rat.
  - In B this is dev: the frames were seen before, so the timing contrast is indicative only.
- **Logged:**
  - per frame: active time (the clock pauses when the tab is hidden or after 45 s without input) and the arm;
  - per rat: source (candidate rank k, or manual), flags, edge moves, "next" presses;
  - an optional "show all candidates" view, with its time logged separately; there the user may mark masks as garbage
    or fragment (descriptive only).
- **Outputs:**
  - page `<run>/prelabel_edit/index.html` (self-contained, file://);
  - exports → `cv/configs/inbox_sam3_prelabel_edit_2026c/`;
  - a descriptive summary in the SAM 3 report, section "B — pre-label edit pilot (dev)". It gives:
    - usable@1 (first candidate accepted with no flag) and usable@any;
    - the merged, partial and manual-box rates;
    - seconds per rat, PRELABEL vs SCRATCH;
    - everything also split by pile size and domain.
- **What B decides, before C** (frozen in an amendment to this plan): the candidate order (score / area / …); whole vs
  tiled (consider tiled with the T1 cross-tile merge if usable@any on whole IR < 80 %); whether any filter is needed;
  the final "usable" definition.

## C — frozen test on new frames

1. **Frame pool.** In-box IR frames (colour inserts excluded) from CH07 (house_2) and CH08 (house_1).
   - Window: release (08-30) to before 09-11 19:40 (the females are out of scope).
   - Excluded:
     - 09-05 (the project's frozen test day);
     - lid events ± 10 min (`cv/configs/cohort3_lid_events.json`) and handling windows;
     - anything within ± 1 h of a frame the user or the agent has already seen in-box (identity page, SAM 3 test, prompt
       sweep and GUI, mask review, B).
2. **Strata** from the WISER house roster at the frame time (`box_occupancy_1s.csv.gz` of the in-box phase-0 run; WISER
   is used only to sample and is never shown):
   - 1 animal in the house: 12 frames;
   - 2–3: 18;
   - 4–5: 18;
   - door (a box event within ± 20 s): 6;
   - empty (0): 6 (they test only whether rats are present where WISER says none).
   - Total 60 frames, CH07 36 / CH08 24, day and night both drawn (light phase reported).
3. **Independence.** Within a camera, frames are ≥ 30 min apart; at most 2 frames per day × camera × stratum; ≥ 6
   different days. The list is drawn by a script with a fixed seed **before any image is viewed**, and committed.
4. **Order of work.**
   1. Commit the frame list.
   2. The user clicks heads blind on all 60 frames: no masks, no WISER, identity optional → truth heads.
   3. The B-amendment freeze is committed; SAM 3 then runs the frozen pipeline on the 60 frames.
   4. Randomisation PRELABEL / SCRATCH 1:1, stratified by camera × stratum (seed 20261013).
   5. The edit session runs on the frozen B page.
   6. After the timed session, every truth rat on the SCRATCH frames gets the candidate verdict without timing, so
      usable@any covers all rats.
   7. Quality re-read: a random 25 % of the final rats from each arm, shown as box-on-crop and blind to the arm. The
      reader is a second person (the undergrad) if available, otherwise the user ≥ 1 day later. Verdict: good / too
      big / too small / wrong or two rats.
5. **Primary metrics** (pooled CH07 + CH08; CIs by bootstrap over day × camera clusters):
   - **P1 usable@any:** share of truth rats with a usable candidate among those offered at their head.
   - **P2 time:** seconds per rat, PRELABEL / SCRATCH ratio.
   - **P3 quality:** re-read "good" share, PRELABEL − SCRATCH.
6. **Decision rule.** Adopt "rat" pre-labels for in-box body labels if and only if:
   - P1 ≥ 0.80 with a lower CI ≥ 0.70;
   - the P2 upper CI < 1.0;
   - the P3 lower CI > −0.10.

   Otherwise label heads + boxes from scratch. Per camera, adoption needs its own P1 ≥ 0.80 (secondary).
7. **Secondary (descriptive):**
   - usable@1; the merged, partial and manual-box rates;
   - everything by stratum, camera and light phase;
   - masks per frame that cover no truth head (reported, never a criterion);
   - the empty-house strata: rats seen where WISER says none.
8. **Cost to the user:** about 300 head clicks (~30–40 min), the edit session (~1 h), the re-read (~15 min).

## Rules

The agent never judges an image. Truth = the user's clicks and verdicts. Nothing is tuned on C frames. Local only (the
cv env, RTX 5070 Ti); intermediates stay in the run folder and are never re-extracted; commits are local.

## Amendment C1 — 2026-10-12, Codex *Yolo_identity* review of C (before any C frame is drawn or seen); supersedes C items 1–7 where they differ

1. **Order (most important).** The freeze comes first:
   1. B ends.
   2. The freeze amendment is committed: candidate order, whole / tiled, filter, the cap K on candidates offered per
      rat, the usable definition, all metric code.
   3. Only then is the frame list drawn and committed (from the script, no image viewed).
   4. Then the user's blind truth clicks.
   5. Then SAM 3 on the frames, the timed session, the verdict pass and the re-read.

   Nothing seen in a C image or click may change a frozen setting; a sample is never added after a result is seen.
2. **Independence.**
   - The sampling unit is a still episode, not a 30-min spacing: a still pile can last hours. The unit is formed by
     the roster + head-IMU join rule of the 2026-10-11 test (Amendment 2 there), and at most one frame is drawn per still
     episode.
   - Clusters for the CIs are day × camera.
   - An extra **"uncertain" stratum** covers WISER dropout, untagged-animal windows or a roster that disagrees with the
     box events. Strata are assigned in priority order: door > uncertain > empty > roster count. Per-stratum quotas
     replace weights, and the pooled estimates are unweighted over rats, with per-stratum results reported.
   - 60 frames is a pilot. Per-camera results are descriptive unless a camera has ≥ 20 frames with ≥ 60 truth rats.
3. **Truth denominator.**
   - The user's blind truth step marks every visible rat: a head point where the head is visible, else a body point
     ("head hidden").
   - The P1 denominator is all such rats. Head-hidden rats get candidates at the body point and are reported separately.
   - The claim is limited to "candidate usability after a human has located the rat".
4. **P1 judged independently of the accept button.** After the timed session there is an untimed verdict pass for every
   truth rat in both arms: each offered candidate up to rank K is judged usable / merged / partial / garbage, with the
   full frame visible. P1 = share of rats with ≥ 1 usable candidate within K. A second person re-judges a random 30 %
   of the rats, and their agreement is reported.
5. **Timing.**
   - Frames are presented in a random order with the two arms interleaved (seed 20261013).
   - Time counts everything in the arm: cycling, deleting, edge moves and "show all".
   - Empty frames (no truth rat) are excluded from the time ratio and reported separately.
   - The comparison is of the body-box step after the heads are placed, not end to end; that is stated with the result.
6. **Quality re-read.**
   - **All** final rats are re-read, not 25 %. With ~300 rats and a good-rate near 0.9, the 95 % CI half-width of the
     difference is ≈ 0.07; at 25 % it is ≈ 0.14, which cannot settle a −0.10 margin.
   - Each rat is shown in full-frame context with its box highlighted, blind to the arm.
   - The reader is a second person (the undergrad) by default. The user's next-day re-read is used only if no second
     reader exists, and is labelled "self, non-independent".
7. **Statistics.**
   - Pooled over rats; 95 % percentile CIs from 2000 cluster-bootstrap resamples (day × camera).
   - Decision outcomes: adopt / do not adopt / **insufficient evidence** (any CI crosses its threshold).
   - Per-camera adoption needs P1, P2 and P3 for that camera, not P1 alone.
8. **Other rules, fixed now.**
   - **Unreadable or wrong frames:** a drawn frame that is unreadable, a colour insert or inside a lid window is replaced
     by the next frame of the same stratum from the seeded backup list, which is drawn with the main list.
   - **Cycling cap:** K is fixed in the freeze, from B's rank distribution.
   - **Rats appearing only in "show all":** reported, not counted in P1.
9. **Open for the user (needed before the freeze):**
   - (a) Is a quality loss of up to 10 points (P3 lower CI > −0.10) acceptable in exchange for faster labelling, or is a
     smaller margin required?
   - (b) Who is the second reader (the undergrad?).
