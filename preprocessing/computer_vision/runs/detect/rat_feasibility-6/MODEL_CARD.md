# Shelter rat detector — `rat_feasibility-6` (CH05/CH06)

Single-class YOLO11 detector used by the Field_2026_Social shelter-CV pipeline to count rats
**visible inside** the CH05/CH06 shelter (imaged through the IR-filter glass). This card documents
the shipped weights `weights/best.pt`.

## What it is
- **Task:** single-class object detection — class `0 = rat`.
- **Base model:** `yolo11s.pt` (Ultralytics YOLO11-small), fine-tuned.
- **Input size:** `imgsz = 1280`.
- **Shipped weights:** `weights/best.pt` (18.4 MB) — the **best-val-mAP checkpoint (epoch 44)**,
  not the final epoch. `last.pt` is intentionally not shipped.
- **sha256(best.pt):** `03b05d2e07d5e1ec1658fad63556556c87b9cbdd23d4f1c34cd05e94031849e7`

## Training
- **Data:** `dataset/rat/data.yaml` — harvested + hand-labeled shelter frames (empty label files
  are valid negatives). Train/val split held out **by session/video**, not by random frame, to
  avoid near-duplicate leakage.
- **Schedule:** fine-tune `yolo11s.pt`; up to 80 epochs, early-stopping patience 30, auto batch,
  auto optimizer, `lr0 = 0.01`. Best checkpoint at **epoch 44** (val mAP peaked, then overfit).

## Metrics (Ultralytics val, single class `rat`)
| checkpoint | precision | recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| **best.pt (epoch 44, shipped)** | 0.858 | 0.820 | 0.875 | 0.503 |
| last.pt (epoch 74, not shipped) | 0.898 | 0.768 | 0.810 | 0.469 |

- **mAP50** = mean average precision at IoU 0.50; **mAP50-95** = mAP averaged over IoU thresholds
  0.50–0.95 (step 0.05). Range [0, 1]; higher = better localization + classification.
- These are the training run's own final-val metrics (the pipeline convention: `model.val()` is
  not re-run because batched inference at `imgsz ≥ 960` trips a CUDA fault on the analysis-PC GPU).

## Intended use
Drop-in weights for `animal_tracking.py --weights ... --classes 0` and for the shelter pipeline
(`shelter_sleep.py` zone-inside count + `validate_shelter.py`). The code's default weights path is
`preprocessing/computer_vision/runs/detect/rat_feasibility-6/weights/best.pt` (this file).

## Caveats — READ BEFORE INTERPRETING ANY COUNT
This detector is one input to a **conservative, regime-aware** measurement, not a headcount oracle:
- **Visible-inside count is a LOWER BOUND.** CH05/CH06 are near-nadir; a **wall-edge blind zone**
  and **huddle compression** mean the true count ≥ the detected count.
- **Through-glass view quality gates trust.** Fog / condensation / rain / glare on the IR glass
  degrade detection; the pipeline safety rule forbids scoring degraded-view frames as
  `occupied_high_motion`. A detection drop under fog is not evidence of a behavior change.
- **Not validated as a headcount, nor as sleep/rest.** Rest proxies are unvalidated vs ephys;
  the CH07/CH08 interior cameras are the intended fog-free cross-check.
- On IR channels, identify rats by **coband pattern**, never color (monochrome imagery).

## Provenance
Trained in the Field_2026_Social repo (`preprocessing/computer_vision/`: `scan_for_rats.py` →
`label_frames.py` → `train_detector.py`). See the `regime-aware-cv-measurement` skill for the
measurement discipline this detector serves.
