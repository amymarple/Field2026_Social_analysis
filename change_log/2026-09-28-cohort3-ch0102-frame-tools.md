# Cohort-3 CH01/CH02 pilot, step 1: frame extraction + WISER-guided frame selection (2026-09-28)

Plan: `implementation_plan/2026-09-28-cohort3-ch0102-yolo-pilot.md`. No frames extracted, no labels, no training yet.

## What was added

- **`cv/cv_field/grab_frames.py`** — single frames at chosen times from the hourly recordings under
  `<root>/<date>/<CH>/` (default the local copy `F:\3rd_rat`): finds the segment (also never-renamed ones, span from
  ffprobe; nights across two date folders), decodes one frame (default CPU, exact; `--mode key` snaps to the keyframe at
  or before, `--decode gpu` uses NVDEC with CPU fallback), returns CH01/CH02 UPRIGHT (90° CCW), writes native JPEGs
  named `<CH>_<video stem>_<pts>s.jpg` (so `train_detector.session_key()` groups by camera+date+hour) and a manifest with
  target vs actual frame time. `--targets camera,time[,tag]`, `--benchmark`, `--selftest` (synthetic HEVC; PASS, CPU and
  GPU paths).
- **`cv/cv_field/select_pano_targets.py`** — per 5-s WISER bin, the number of tagged animals outside the two houses
  (house rectangle + 14 in, the zone rule of the cohort-3 WISER accuracy report), on the on-animal tag epochs of that
  report (`$OUT_ROOT/2026c/wiser_working/c3_bins5.pkl`); candidates = night window 21:00–04:20, outside handling windows
  (± 5 min), before the 09-11 19:40 population change unless `--include-popchange`; stratified draw
  zero / few (1–2) / many (≥ 3) = 20 / 40 / 40 %, nights round-robin, ≥ 10 min apart; one night held out as the test night.
  Every target carries the caveats (tagged count is a lower bound when an animal is untracked). `--stats`, `--selftest`
  (PASS).
- **`cv/configs/cohort3_handling_windows.json`** — operator-in-arena windows, copied from the WISER accuracy run's
  off-repo script so repo code does not depend on it (source cited inside).

## Measured

**Decode benchmark** (night 09-04, 20 random times per camera, four methods in rotating order; bulk
`$OUT_ROOT/2026c/cv_field_grab_benchmark_20260928_2139/`):

| s/frame (median / p90) | CPU exact | CPU key | GPU key | GPU exact |
|---|---|---|---|---|
| CH01 | 0.90 / 0.95 | 0.80 / 3.3 | 0.96 / 3.2 | 1.10 / 5.7 |
| CH02 | 0.91 / 1.19 | 0.79 / 3.3 | 0.95 / 3.2 | 1.18 / 5.6 |

- Exact mode lands 0.03–0.11 s from the target; keyframe snap moves the time by a median 0.9–1.3 s (max 2.0 s).
- GPU and CPU decode give the same frame (20/20) with mean |difference| 0.7 grey levels (colour-conversion rounding).
- **Conclusion:** for single frames the ~0.8 s floor is process start-up, container open, the pano transpose and piping a
  50 MB raw frame — not the decode. GPU decode brings no speed-up for sparse frames (and a slower tail), so the default is
  CPU + exact. The user's "GPU from now on" applies where it pays: continuous decoding for whole-night inference. The
  ~6 s/frame of `camera_review.py` comes from its full-resolution JPEG + thumbnail + overlay writing, not decoding.

**WISER strata per night** (hours of usable night bins; tagged animals outside the houses):

| night | zero | few (1–2) | many (≥ 3) | total |
|---|---|---|---|---|
| 08-30 | 1.28 | 3.32 | 1.82 | 6.42 |
| 08-31 | 0.95 | 2.84 | 3.55 | 7.34 |
| 09-01 | 0.72 | 2.75 | 3.86 | 7.33 |
| 09-02 | 1.48 | 3.44 | 2.42 | 7.34 |
| 09-03 | 0.67 | 2.92 | 3.74 | 7.33 |
| 09-04 | 0.71 | 1.34 | 5.28 | 7.33 |
| 09-05 | 0.44 | 2.75 | 4.14 | 7.33 |
| 09-06 | 0.17 | 2.97 | 4.19 | 7.33 |
| 09-07 | 0.41 | 3.04 | 3.88 | 7.33 |
| 09-08 | 0.11 | 2.30 | 4.92 | 7.33 |
| 09-09 | 0.29 | 1.25 | 5.78 | 7.32 |
| 09-10 | 0.31 | 2.68 | 4.35 | 7.34 |

## Definitions

- **Tagged animals outside** at a 5-s bin $b$: $n_{\text{out}}(b)=\sum_{k}\mathbb 1[\tilde{\mathbf p}_k(b)\notin H_1^{+14}\cup H_2^{+14}]$
  over tags $k$ on an animal at $b$, where $\tilde{\mathbf p}_k(b)$ is the tag's median position in the bin (inches, WISER
  frame) and $H_j^{+14}$ the house rectangle of `wiser/configs/wiser_rois.json` grown by 14 in. Plain text: how many of the
  tracked rats are away from both houses in that 5-s interval. It undercounts whenever a rat is untracked (night 1 SF12;
  SF11 09-02 00:03–08:20 and after 09-07 06:10:45; the untagged females after 09-11 19:40).
- **Stratum**: zero ($n_{\text{out}}=0$), few ($1\le n_{\text{out}}\le2$), many ($n_{\text{out}}\ge3$).
- **Snap** (benchmark): frame time − target time, seconds, field-PC time.

## Not done / next

Test-night and time-scope choice (user), extracting the round-0 pool with these tools, labelling.
