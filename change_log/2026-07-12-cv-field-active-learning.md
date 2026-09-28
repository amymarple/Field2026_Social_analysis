# cv_field — whole-field CV (CH01–CH04) active-learning + YOLO detector (Phase 0)

**Date:** 2026-07-12 · **Status:** Phase 0 landed (code + self-tests). New subsystem `cv/cv_field/` + new
research direction `cv_field`. Infrastructure/tooling — no scientific claim, no data processed. Plan:
[implementation_plan/2026-07-12-cv-field-active-learning.md](../implementation_plan/2026-07-12-cv-field-active-learning.md).

## What changed

New whole-field CV direction that bootstraps a YOLO rat detector for CH01–CH04 (which had none) with an
**unsupervised active-learning labeling loop**. `cv_shelter` (CH05/CH06) is untouched.

- **`cv/cv_field/` subpackage** (all new): cohort re-export shims (`output_paths.py`, `cohorts.py`);
  `field_embed.py` (yolo|gray backends, numpy PCA+L2, `embedding_fingerprint`); `field_cluster.py`
  (numpy k-means++/Lloyd + **silhouette** K-selection + medoids + farthest-point sampling + a
  `pca_competitor_report` falsification guard; sklearn lazy with numpy fallback); `acquire.py`
  (uncertainty + uncertainty-weighted-k-center `greedy_acquire` + `random_baseline`); `select_frames.py`
  (the round-0..k selector driver); `run_field.py` (whole-field inference orchestrator over the existing
  `animal_tracking.py`→`merge_cameras.py`); `field_audit.py` (whole-field milestone audit → `.md`+`.json`);
  `selftest_field_select.py`; `assets_manifest.json`; `FIELD_AUDIT_CHECKLIST.md`; `REMOTE_COMPUTE.md`.
- **`cv/measurement_context.py`** — additive `embedding=`/`active_learning=` kwargs on `build_context`; the
  embedding fingerprint rides in the `detector` block and the active-learning round/params become a
  top-level block that flips `mc_run_id` **only when present**, so shelter runs stay byte-identical.
- **`cv/environment.yml` + `cv/requirements.txt`** — added `scikit-learn` (lazy-imported; numpy fallback).

## Method notes (definitions)

- **Round 0 (cold start, no detector):** pure diversity — embed the harvested pool, choose **K by silhouette**
  (silhouette, not a likelihood BIC, because the embedding is L2-normalized to the unit sphere where BIC
  rewards ever-smaller variance and over-segments; singleton clusters are scored 0 so scattered frames don't
  inflate K), take one **medoid** per cluster, then **farthest-point** coverage of the remaining budget.
- **Rounds ≥1 (seed detector):** **uncertainty × diversity** — `u = max(confidence-margin about τ,
  count-instability under horizontal-flip TTA) ∈ [0,1]`; select by uncertainty-weighted k-center
  `a(f|A) = u^γ · d(f,A)` (d = min Euclidean distance to the labeled/selected set A in the L2-normalized
  embedding), which both spreads the picks and suppresses near-duplicate hard frames; `explore_frac` of the
  budget is pure farthest-point exploration.
- **Falsification discipline (mirrors `wiser/src/route_vocabulary.py`):** clusters are a labeling heuristic,
  never a discreteness claim (`pca_competitor_report` records a single-Gaussian BIC vs the k-means BIC); the
  active-learning claim itself must beat an **equal-budget random-selection control** (`--method random`)
  before "few labels → strong detector" is supported.

## Compute routing

Small batches run on the local GPU; large batches (full-pool embedding, full-cohort retrain at imgsz 1280,
long-video inference) dispatch to Cornell BioHPC via the `gpu-cv` skill at `D:\FastenPC`. Drivers are
env-driven (`FIELD2026_ANALYSIS_OUT_ROOT`, `--device`) so the same code runs local or on the server; the
runbook is `cv/cv_field/REMOTE_COMPUTE.md`. Nothing in Phase 0 depends on the (still-being-wired) skill.

## Constraint / scope

This checkout is source + configs only (no raw video, weights, `dataset/`, or `staging/cv_attempt/`), so
only Phase 0 landed. Phase 1 (harvest→select→label→train), Phase 2 (iterative rounds + random control), and
Phase 3 (whole-field inference) run on the machine with the data / on BioHPC. Whole-field **cross-camera
identity is not built** (`animal_id = <camera>:<track_id>`); WISER×CV alignment stays blocked on georeference.

## Verification

- `python cv/cv_field/selftest_field_select.py` → **PASS** — planted-cluster coverage (incl. a rare 10-point
  blob + outliers), silhouette K recovery (K∈[4,7]), near-duplicate suppression (≤3 of 30 dupes), uncertainty
  targeting + ≥3-cluster spread, determinism under a fixed seed, gray-backend end-to-end on synthetic PNGs,
  and cohort path + `measurement_context` wiring (embedding/active_learning blocks; `mc_run_id` flips per
  round; shelter manifest gains no cv_field keys).
- `python -m py_compile` clean on all new modules + `cv/measurement_context.py`; the three drivers `--help`
  cleanly; a full `select_frames --round 0` (gray) + `field_audit` end-to-end smoke on 25 synthetic frames
  produced the report, coverage figure, provenance, sidecar, run_manifest, and audit `.md`+`.json`, then
  cleaned up.

## Addendum — Phase 1 pilot cold start on real data (2026-07-13)

Ran the round-0 cold start on real footage after raw video (`Q:\hc997\SocialFieldRat2026\<date>\CH0x\`) and
the Cornell BioHPC server were made available.

- **Scope narrowed (user):** cv_field is **night-window 21:00 → 04:20, night-IR only**. CH01/CH02 daytime
  COLOR has a bitrate-overflow → partial corruption, so it is never sampled (night-IR is fine). A "night"
  crosses midnight (hours 21–23 of date *D* + 00–04 of *D+1*, two date folders). `FIELD_AUDIT_CHECKLIST.md`,
  `select_frames.py`, and `field_audit.py` caveats updated from a day/night split to night-IR-only.
- **Local `cv` env built** (anaconda3): torch 2.13.0+cu126 (CUDA on the RTX 3060), ultralytics, cv2, sklearn
  — passes the cv_field selftest. `REMOTE_COMPUTE.md` server recipe corrected to the real BioHPC (no conda:
  `module load python/3.12.7` + venv + cu128; 2× RTX PRO 6000 Blackwell).
- **Bug fixed:** `field_embed._yolo_vecs` did `np.asarray()` on ultralytics `.embed()` outputs, which are
  **CUDA tensors** → would crash. Now moves each to host via `.detach().cpu().numpy()`. The gray-only selftest
  never exercised this; the real yolo run confirms the fix.
- **Pilot run — night of 2026-06-28, CH03/CH04, local 3060:** harvest (`scan_for_rats --no-detector`,
  seek-sample 20 s, dedup 2.0) → **323 pool frames**; round-0 **yolo-backbone** diversity selection
  (`--budget 150`) → 150 frames into the labeling inbox `cv/dataset/rat_field/images` + `round_provenance.csv`.
  Silhouette **K=2** (yolo embedding of homogeneous night-IR mostly separates CH03 vs CH04) → 2 medoids + 148
  farthest-point; channel split 88/62. **Falsification guard honest:** single-Gaussian BIC (−50607) beats
  k-means BIC (−32557) → clusters are *not* discrete, they are a labeling heuristic (coverage/FPS did the
  work). Canonical `results/2026a/cv_field/reports/cv_field_labeling_round0_2026a.md` + coverage figure +
  `run_manifest.json`; bulk + `measurement_context` sidecar off-repo.
- **Milestone audit** (`field_audit` metadata): 150 frames all-night (scope validated); **CH03 calib RMSE
  19.7 cm vs CH04 11.3 cm flagged** (CH03 pixel→field-cm is shakier — matters for `run_field` positioning
  later, not for detection/labeling now). Report `cv_field_audit_2026-06-28_night.{md,json}`.
- **Operational note:** call the env's `python.exe` directly (`C:\Users\Cornell\.conda\envs\cv\python.exe`),
  NOT `conda run` — the base conda 4.10.3 buffers child stdout and crashes re-printing it under cp1252
  (`UnicodeEncodeError` on em-dashes). Python itself ran fine; only the wrapper failed.
- **Handoff / next:** labeling is the human step (`python cv/label_frames.py`), then
  `train_detector.py --data-root cv/dataset/rat_field --name rat_field`. The full multi-night + CH01/CH02
  (4.3 GB fisheye) harvest/train is a large batch → BioHPC, which needs a one-time interactive `ssh gpu` 2FA
  first (non-interactive SSH is currently blocked). Candidate / pilot; no detector trained yet.

### DINOv3 adopted as the selection embedding (2026-07-13)

The initial embedding was the YOLO11 backbone (per the design brief, to avoid a model download). The user
correctly pushed back: the *unsupervised method* combined with YOLO should be **DINO** — and at cold start
(no rat detector yet) a COCO detection backbone is a weak representation, whereas DINO's self-supervised
features are exactly the right one.

- **`field_embed.py` generalized to a pluggable DINO backend.** `backend="dino"` (now the selector default)
  auto-prefers **DINOv3** when its license-gated checkpoint is present (`$DINOV3_WEIGHTS` or the torch-hub
  cache), else falls back to **DINOv2** (free ~85 MB auto-download). The torch.hub entrypoint is inferred from
  the checkpoint filename (`dinov3_vitb16_pretrain_…pth` → `dinov3_vitb16`), so any variant just works;
  `dinov2`/`dinov3` force one. `embedding_fingerprint` records family+variant+weights sha256 into each run's
  `measurement_context`.
- **Empirical access check.** DINOv2 loads free via torch.hub (verified: 384-d, 8 s). DINOv3 code loads after
  `pip install torchmetrics termcolor`, but its weights are **license-gated** (HTTP 403 auto-download). The
  user accepted Meta's DINOv3 license and downloaded **ViT-B/16** (`dinov3_vitb16_pretrain_lvd1689m-73cec8be`,
  343 MB, sha256 `73cec8be7427c865`, embed dim 768) into `~/.cache/torch/hub/checkpoints/`. Verified end-to-end:
  real night frames embed cleanly on the 3060.
- **Round 0 re-run on DINOv3 ViT-B/16**, budget reduced **150 → 40** (feasibility-sized; active learning is
  *few* well-chosen labels, not everything). Silhouette **K=3** (vs YOLO's K=2 — DINOv3 sees more than the
  camera split), channel split 18/22 (balanced), falsification guard still smooth-competitive=True (clusters
  = labeling heuristic). 40 frames in the inbox; audit refreshed. **A labeled frame is embedding-agnostic**, so
  these labels stay valid if a larger DINOv3 is later used for Stage-2 identity/re-ID.
- **Operational:** run the cv env's `python.exe` directly with `PYTHONIOENCODING=utf-8` (the earlier `conda run`
  cp1252 crash is avoided; direct runs print clean).

### First cold-start detector trained — training-divergence fix (2026-07-13)

The user labeled the 40 DINOv3-selected frames (39 usable: 31 with rats / 82 boxes, 8 negatives; 1 skip/huddle)
and trained `rat_field` with the default hyperparameters. It produced a **dead detector** — mAP50 rose to 0.075
at epoch 4 then **collapsed to 0** and stayed there, with `val/cls_loss` exploding to 360. Diagnosis: **training
divergence**, not bad labels (0 corrupt) — `lr0=0.01` + AutoBatch is too hot for a 30-image train set.

- **`train_detector.py` hardening:** added `--lr0` / `--freeze` / `--optimizer` / `--patience` (behavior-preserving
  defaults, so `cv_shelter`'s ~940-image runs are unchanged); a **small-set divergence warning** (`< 100` train
  frames at default lr with no freeze); and a **batch float→int coercion** (a positive `--batch` reached the
  DataLoader as `8.0` and was rejected — `batch` is float to allow `-1`/VRAM-fraction).
- **Retrain, same 40 frames**, `--freeze 10 --lr0 0.002 --batch 8`: trained the full 100 epochs stably →
  **val mAP50 0.822 · mAP50-95 0.405 · P 0.818 · R 0.692** on held-out CH03/CH04 night videos. Weights:
  `cv/runs/detect/rat_field_stab/weights/best.pt` (the diverged `cv/runs/detect/rat_field` is superseded).
- **Lesson (corrects the in-flight "too few labels" worry):** 40 DINOv3-selected frames were *sufficient* for a
  strong first-round whole-field detector — the earlier mAP=0 was a stability artifact, not data starvation.
  Small active-learning batches need freeze-backbone + low lr or YOLO diverges.
- **Status:** candidate, single-night pilot. Recall 0.69 → next: round 1 (uncertainty×diversity on this detector,
  vs random control) + more nights to lift recall; optionally pretrain on the CH05/CH06 shelter labels once located.

### Round 1 (80 labels) + fair head-to-head (2026-07-13)

- **Round 1** selected 40 uncertainty×diversity frames (34 acquisition + 6 exploration, CH03 25 / CH04 15 —
  the model is least sure on CH03), **excluding round-0's 40** (`labeled_idx`). Labeled → 78 usable / 154 boxes;
  retrained `rat_field_r1` with the stabilized recipe.
- **Cross-round headline mAP is NOT comparable:** `train_detector` re-draws the session val split each round
  (round-0 val = 4 sessions / 9 frames; round-1 val = 3 *different* sessions / 17 frames), so round-1's headline
  mAP50 0.70 vs round-0's 0.82 is a **split artifact**, not a regression.
- **Fair head-to-head** on 2 sessions BOTH models held out (15 frames / 29 boxes),
  `model.val(..., workers=0)` (the 3060 needs `workers=0` — Windows multiprocessing bootstrap):
  round0 @40 → mAP50 **0.715** / mAP50-95 0.354 / P 0.656 / R **0.724**; round1 @80 → mAP50 **0.726** /
  mAP50-95 **0.424** / P **0.758** / R 0.655. Doubling labels (same night) **improved precision + localization,
  slightly lowered recall, flat mAP50** — all within noise on 29 boxes.
- **Conclusion:** more frames from the *same* night saturate; the lever for recall is **more nights** (new
  scenes/regimes). For a rigorous label-efficiency curve, pin a **fixed** held-out set across rounds and run the
  equal-budget `--method random` control (both still TODO).

### Frozen held-out test + multi-night round 2 — the generalization gap is real (2026-07-13)

Built the **frozen test set** (07-06 evening, 40 frames time-uniform / **22 GT boxes**, labeled from scratch, in
`cv/dataset/rat_field_test/` — never trained on) and a **round-2 motion-assisted** batch on the 07-05 night
(`select_frames --use-motion`, 40 frames = 26 uncertainty + 4 explore + 10 quiet, editable motion proposals),
retrained `rat_field_r2` on 06-28+07-05 (120 imgs / 205 boxes). Head-to-head on the frozen 07-06 ruler at
matched precision:

| detector | AP50 | R@P0.8 | P@.25 | R@.25 |
|---|---|---|---|---|
| rat_field_stab (40, 06-28) | 0.21 | 0.00 | 0.50 | 0.27 |
| rat_field_r1 (80, 06-28)   | 0.23 | 0.00 | 0.34 | 0.45 |
| rat_field_r2 (120, +07-05) | 0.18 | 0.00 | 0.33 | 0.27 |

- **Held-out generalization is ~0.2 AP, not the ~0.8 the within-night val reported** — the 0.8 was
  near-duplicate-frame leakage; the frozen ruler exposes the true gap (exactly why it was built). No detector
  reaches 0.7 precision at any recall on a genuinely new night.
- **Round 2 (adding the 07-05 night) did NOT improve held-out performance** (r2 ≈ r1 ≈ stab ≈ 0.2). One extra
  *sparse* night is not enough; the "more nights" lever needs SEVERAL diverse (ideally rat-active) nights.
- **Caveat:** 22 GT boxes → the exact AP ranking is within noise; the ~0.2 clustering is the robust signal.
- **Reframe / next:** the night-IR whole-field detector is **data-hungry for night-to-night generalization**.
  Path: harvest **several** more diverse local nights (`E:\<date>`), motion-assisted label + retrain, and enlarge
  the frozen test with a **rat-dense** night for a less-noisy ruler — the natural point to move the bulk
  harvest to **BioHPC**. All nights are local on `E:`; test/train dirs are separate (no leakage).

### Diagnosis of the 0.8→0.2 collapse — it is OVERFITTING to training-night appearance (2026-07-13)

Ran the three-mechanism diagnostic (zero new labels) the user specified:
- **#3 small-object inference — RULED OUT.** Cameras are native **4512×2512** but we train/test at 1280 (rats
  ~25 px vs ~90 px native). Re-extracted the 40 frozen frames at native res (normalized GT transfers) and
  swept inference: native-whole @1280/1920/2560 and overlapping tiled 2×2/3×2. **Every higher-res / tiled
  config was WORSE** (stab AP 0.205 → 0.09 @1920 → 0.06 @2560; tiled 3×2 → 0.007) — the detector is
  **scale-locked** to its 1280 training scale, so more pixels (bigger rats) hurt. Best practical inference =
  the current **whole-frame @1280**.
- **#1 base under-fitting — RULED OUT.** Each detector fits its OWN training frames: rat_field_stab **AP 0.95**
  (recall 0.98) on its round-0 frames; rat_field_r2 **AP 0.84** on all 117. It has fully learned to detect
  these rats.
- **#2 night-appearance shift — CONFIRMED.** 0.84–0.95 on trained nights vs **~0.2** on the held-out 07-06
  night is a textbook generalization gap: with ~120 frames from 2 similar nights the head memorizes each
  night's IR texture/contrast/noise/background and doesn't transfer, though rat size + position match.
  (22-box ruler is noisy, but a 0.95→0.2 gap is far beyond noise.)

**So the lever is appearance DIVERSITY, not more labels of the same nights nor higher-res inference.** Free
test: `train_detector --augment` (strong domain-randomization — heavy brightness/contrast via hsv_v +
scale/translate/rotate + mixup/erasing) on the SAME 120 frames → `rat_field_r2_aug`. On the frozen 07-06 ruler:
**AP50 0.183 → 0.260 (+42% rel)**, P@.25 0.33 → 0.44, R@.25 0.27 → 0.32 — the best detector on the held-out
night, from the same data. **Confirms #2**: the collapse was appearance-overfitting, and domain randomization
partially fixes it for free. Use `--augment` for cv_field experiments (opt-in flag — deliberately NOT a
repo-wide default). BUT the gap is only
partly closed (0.26 held-out vs 0.84 trained; no config reaches P0.7), and the 22-box ruler is too coarse to
trust the exact delta. **Remaining levers (complementary): (1) more DIVERSE nights (data), (2) enlarge the
frozen test with a rat-dense night so small gains are measurable.**

### ROOT CAUSE found by looking at the footage — the field grew over (2026-07-13)

While picking a rat-dense test night, a visual spot-check (CH03/CH04, native res, detector boxes overlaid)
revealed the real driver: **the paddock is heavily OVERGROWN with tall grass on the late nights, and was OPEN
short grass on the training night.** 06-28 (training) = flat matted grass, bare-dirt floor, rats clearly
visible on open ground; 07-08 (test-era) = a tall dense grass jungle, floor fully covered, rats **occluded**
except at edges/clearings/walls. The grass grew dramatically over ~10 days.

This is the **root cause of the 0.9→0.2 collapse and subsumes every earlier symptom**: the detector was trained
on a scene (open short grass) that no longer exists on the test nights (tall grass) — a *scene change +
occlusion*, not subtle appearance shift. It explains why augmentation only half-helped (can't synthesize new
occluding grass), why the field_motion base-rate problem appeared on windy nights (tall grass moving), and why
every late night shows sparse *visible* rats (hidden in grass). The detector's late-night hits are REAL rats —
just the few out in the open.

**Implication — the earlier plan (add nights + retrain) was built on a wrong assumption.** Whole-field night
detection is (a) only tractable in the SHORT-GRASS regime (early cohort), and (b) severely occlusion-limited
once the grass grew — no amount of labels/aug fixes rats being physically hidden. Options to decide with the
user: match training to the target grass regime (label tall-grass nights, accept low yield), restrict to
visible zones (edges/clearings), lean on the shelter cams (CH05/06, rats always visible) + WISER for the
behavioral questions, or flag the overgrowth to the field team (mowing restores CV viability). Test-night
selection and the aug retrain are PAUSED pending this direction call.

### Rigorous re-evaluation — matched precision + embedding homogeneity (2026-07-13, cont.)

Prompted by the user's caution: 15/29 is underpowered, the P/R gap may be *calibration* not quality, and the
selected frames look homogeneous. All three checked out — and the first REVISES the "flat" call above.

- **Annotations (item 4): consistent, no drift.** round0 vs round1 box geometry near-identical (median w
  0.024/0.023, h 0.040/0.040, area frac 0.0011/0.0011; negatives 6/5; all class 0; 78/80 have a label decision,
  2 skip/huddle). Picks are temporally well-spread (median 220 s apart, 3 adjacent) — homogeneity is not temporal.
- **Matched precision (items 2–3) — round 1 IS better; the earlier "flat/lower recall" was calibration.** Own
  IoU-0.5 PR on the common 15-frame/29-box held-out: AP50 0.716 both (coarse at 29 boxes), but **recall at matched
  precision favors round1**: recall@P0.7 0.552→0.724, @P0.8 0.517→**0.690**, @P0.9 0.103→0.310; per-session FN 9→7.
  At the default conf 0.25, round1 merely sits at a higher-recall-lower-precision *operating point*; controlling for
  precision, its detector strictly dominates. So the active-learning loop **is** improving the detector.
- **Homogeneity (user's intuition) confirmed, with mechanism.** Raw DINOv3 (768-d, no PCA) cosine similarity:
  whole-pool mean **0.848** (within-CH03 0.917, within-CH04 0.906, cross 0.783) — one night's frames are
  near-duplicate in content. Selected-80 mean sim **0.853 ≈ random-80 0.850** → whole-frame "diversity" selection
  buys ~nothing over random on a single homogeneous night. **42%** of embedding variance is just CH03-vs-CH04 →
  the whole-frame embedding is dominated by camera/background, not rat content. Frames look alike because they ARE
  alike *and* the embedding measures the wrong axis.
- **Implications / next:** (1) more labels still help (more rat instances + uncertainty-targeted hard cases), but
  scene diversity needs more **nights**, not more same-night frames; (2) make selection **rat-content-aware**
  (detector crops / foreground), not whole-frame, and lean on uncertainty over whole-frame diversity for round≥1;
  (3) eval is underpowered (29 boxes) → **freeze a labeled multi-night test set** (07-04 reserved, untouched)
  before over-reading any number. Harvested the **06-30 night** into `night_2026-06-30/` (separate pool).
