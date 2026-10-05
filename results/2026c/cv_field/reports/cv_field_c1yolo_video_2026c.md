# Cohort-1 YOLO v5 panorama detector on one cohort-3 CH01 night hour (2026c)

Driver `cv/cv_field/c1_yolo_video_test.py` (plan `implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md`, steps 2-3); run `D:/Field2026_analysis_out/2026c/cv_field_c1yolo_video_20261005_1848`; generated 2026-10-05 19:39. **No ground truth here**: the YOLO-vs-WISER numbers are a plausibility check for the user, not an accuracy number. Machine boxes are proposals, never labels. The agent did not look at any frame or video.

## Hour

Rule (plan): complete CH01 files of night 09-06 (21:00-04:00 starts), no handling overlap, highest mean number of WISER-tagged animals outside the houses per 5-s bin; ties → earlier. Chosen: **CH01_2026-09-06_21-00-00_to_22-00-00.mp4** (1.29 GB, ffprobe 3600.5 s).

| rank | file | mean WISER outside | mean tagged | bins (coverage) | handling overlap | complete | chosen |
|---:|---|---:|---:|---|---|---|---|
| 1 | CH01_2026-09-06_21-00-00_to_22-00-00.mp4 | 4.136 | 6.00 | 720 / 720 (100.0%) | – | True | **yes** |
| 2 | CH01_2026-09-06_23-00-01_to_00-00-01.mp4 | 3.242 | 6.00 | 720 / 720 (100.0%) | – | True |  |
| 3 | CH01_2026-09-07_01-00-01_to_02-00-00.mp4 | 3.240 | 6.00 | 720 / 720 (100.0%) | – | True |  |
| 4 | CH01_2026-09-07_03-00-00_to_04-00-01.mp4 | 2.660 | 6.00 | 720 / 720 (100.0%) | – | True |  |
| 5 | CH01_2026-09-07_02-00-00_to_03-00-00.mp4 | 2.561 | 6.00 | 720 / 720 (100.0%) | – | True |  |
| 6 | CH01_2026-09-07_00-00-01_to_01-00-01.mp4 | 2.237 | 6.00 | 720 / 720 (100.0%) | – | True |  |
| 7 | CH01_2026-09-06_22-00-00_to_23-00-01.mp4 | 1.814 | 6.00 | 720 / 720 (100.0%) | – | True |  |

## Decode, detection, runtime

- Decode benchmark (no inference): ffmpeg-cli gpu pipe 8.57 fps over 150 frames; ffmpeg-cli cpu pipe 8.09 fps over 150 frames; pyav in-process, 8 conversion threads 42.56 fps over 300 frames. Path used: **in-process PyAV** (libavcodec frame threads, swscale bgr24 + 90° ccw rotation in 8 threads; plan amendment — the ffmpeg CLI → pipe path of grab_frames is pipe-bound for 50-MB frames, NVDEC does not help it, and PyAV is pixel-identical to it).
- Pass: 72000 frames decoded from 72001 demuxed packets (incl. PyAV's final empty flush packet; the fragmented MP4 stores no frame count); 0 packets failed to decode; PTS monotone True, 0 without PTS), wall 1701.7 s = 42.31 fps, of which YOLO inference 1614.6 s. YOLO v5 `rat_m_v5/best.pt` (backup copy, sha256 `2d7294f3e29da845c8c6c26a39d427ffbe374274524e2cfd922c0edd51b63360`), imgsz 1280, conf ≥ 0.05, fp32, batch 8; ultralytics 8.4.93.
- Pixel identity (frame 26200, PTS 1310.1771777777778): vs `grab_frames.grab` cpu exact (offset 1310.176994 s = midpoint to the previous frame): grab PTS 1310.177178, same frame True, identical True, max |diff| 0, mean |diff| 0.0000, pixels differing 0.00%. A first attempt with offset PTS − 1 ms landed on the previous frame (PTS 1310.176811, 0.37 ms earlier; mean |diff| 3.22) — the stream has frames < 1 ms apart, see below.
- PTS spacing: 1825 of 72000 consecutive frame pairs are < 1 ms apart (median 41.5 ms, max 188.5 ms): Reolink PTS are arrival times in bursts, so the renderer joins detections to frames by PTS at 1 µs.

## Detections

- 423882 boxes at conf ≥ 0.05, 211043 at ≥ 0.25; frames with ≥ 1 box at 0.25: 70094 / 72000 (97.4%).
- Per-frame count at 0.25: 0: 1906, 1: 9892, 2: 18272, 3: 18557, 4: 13219, 5: 6663, 6: 2279, 7: 827, 8: 251, 9: 90, 10: 27, 11: 12, 12: 3, 13: 2.
- Tables: `per_second.csv` (median count at 0.25 / 0.5 over the second's frames, max conf), `per_5s.csv`.

## YOLO count vs WISER outside-count per 5-s bin (plausibility, not accuracy)

Bins with both: 721 (0 bins without any located tag excluded). Mean WISER outside 4.13, mean YOLO count 2.90; YOLO − WISER mean -1.23, median -1.00, mean |·| 1.69; Spearman ρ 0.097; bins with YOLO = 0 while WISER ≥ 1: 1.1%; YOLO > WISER: 16.2%; YOLO = WISER: 14.6%; YOLO < WISER: 69.2%.

| YOLO − WISER | bins |
|---:|---:|
| -6.0 | 3 |
| -5.0 | 6 |
| -4.0 | 40 |
| -3.5 | 1 |
| -3.0 | 105 |
| -2.5 | 1 |
| -2.0 | 184 |
| -1.0 | 156 |
| -0.5 | 3 |
| 0.0 | 105 |
| 1.0 | 85 |
| 2.0 | 19 |
| 3.0 | 10 |
| 4.0 | 2 |
| 5.0 | 1 |

| WISER outside | bins | mean YOLO count | share of bins with YOLO = 0 |
|---:|---:|---:|---:|
| 1 | 12 | 2.25 | 0.0% |
| 2 | 63 | 2.76 | 0.0% |
| 3 | 124 | 3.21 | 0.8% |
| 4 | 213 | 2.53 | 1.4% |
| 5 | 237 | 2.95 | 0.4% |
| 6 | 72 | 3.54 | 4.2% |

Reading guide: WISER counts tagged animals outside the two houses anywhere in the paddock (all six animals were tagged on night 09-06; the untagged females arrived 09-11). CH01 covers ≈ 68 % of the paddock and an animal in view can be hidden by grass, so WISER is not ground truth for CH01: YOLO below WISER can be correct (animal out of view or occluded) or a miss; YOLO above WISER can only be false or duplicate boxes, or an animal WISER places inside the 14-in house buffer. WISER positions carry ~4–7 in jitter. The 5-s median smooths single-frame flicker.

## Review video and clips (for the user; the agent did not look at them)

- `review_10min.mp4`: 2026-09-06 21:21:50 → 2026-09-06 21:31:50 (field-PC), the 10-min window of the hour with the highest mean WISER outside-count (5.23); 11998 / 11998 frames written (0 without a PTS match), 159 MB, 3840 × 1080 H.264 20 fps, render 285.0 s.
- Step-3 clips (`review_clips/`, index `review_clips/index.html`, verdict sheet `review_clips/review_template.csv`), chosen by rule on the 5-s bins (plan amendment); a category without a qualifying window is listed as such:

| file | category | start → end (field-PC) | frames | mean WISER | mean YOLO | rule | rule value |
|---|---|---|---|---:|---:|---|---|
| 1_agree-many_21-41-35.mp4 | agree-many | 2026-09-06 21:41:35 → 2026-09-06 21:42:35 | 49894-51094 | 5.0 | 5.0 | max mean WISER, given mean abs(YOLO - WISER) <= 1 | 5.0 |
| 2_agree-many_21-46-35.mp4 | agree-many | 2026-09-06 21:46:35 → 2026-09-06 21:47:35 | 55895-57093 | 5.0 | 4.583 | max mean WISER, given mean abs(YOLO - WISER) <= 1 | 5.0 |
| – | wiser-zero |  →  |  |  |  | max mean YOLO, given WISER = 0 in all 12 bins | no qualifying window |
| 4_yolo-miss_21-00-35.mp4 | yolo-miss | 2026-09-06 21:00:35 → 2026-09-06 21:01:35 | 701-1900 | 4.0 | 1.0 | max number of bins with YOLO = 0 and WISER >= 2 | 2.0 |
| 5_yolo-excess_21-57-30.mp4 | yolo-excess | 2026-09-06 21:57:30 → 2026-09-06 21:58:30 | 68993-70191 | 3.083 | 6.0 | max number of bins with YOLO > WISER + 1 | 12.0 |
| 6_random_21-51-05.mp4 | random | 2026-09-06 21:51:05 → 2026-09-06 21:52:05 | 61294-62493 | 5.0 | 1.458 | uniform, default_rng(0) | 417.0 |

## Definitions

Units: upright pano pixels (7680 × 2160); times field-PC local (EDT). $k$ = frame, $b$ = 5-s WISER bin.

### Frame time
$$ t_k = t_{file\,start} + PTS_k $$ **Text:** file-name start plus the frame's presentation time (ffmpeg `-copyts`, showinfo); the stream's own start may be offset ≤ ~1 min from the name, as for every stream.

### Per-frame count at cut $c$
$$ n_k(c)=\#\{\text{boxes in frame }k:\ conf\ge c\} $$ **Text:** YOLO boxes kept at $c$ (0.25 or 0.5).

### YOLO count per 5-s bin
$$ Y_b=\operatorname{median}_{k\in b} n_k(0.25) $$ **Text:** typical number of boxes over the ~100 frames of the bin; robust to single-frame flicker. $b=\lfloor (t_k + 4\,h)_{UTC\ epoch}/5\rfloor$.

### WISER outside-count
$$ W_b=\#\{\text{tags located in }b\text{ with median position outside both house rectangles grown by 14 in}\} $$ **Text:** tagged animals outside the houses (`select_pano_targets.bin_table` on `c3_bins5.pkl`); missing when no tag is located in $b$.

### Plausibility summaries
$$ D_b = Y_b - W_b,\quad \rho = \mathrm{Spearman}(Y_b, W_b),\quad f_{miss}=\frac{\#\{b: Y_b=0,\,W_b\ge1\}}{\#b},\quad f_{over}=\frac{\#\{b: Y_b>W_b\}}{\#b} $$ over the bins with both values. **Text:** agreement of the two counts; not accuracy (no ground truth).

### Clip rules
Window = 12 consecutive bins (60 s), all with ≥ 1 frame and a WISER count; mean over its bins. agree-many: max $\bar W$ s.t. $\overline{|D|}\le1$; wiser-zero: $W_b=0\ \forall b$, max $\bar Y$; yolo-miss: max $\#\{b: Y_b=0, W_b\ge2\}$; yolo-excess: max $\#\{b: Y_b>W_b+1\}$; random: uniform, seed 0. No overlap; ties → earlier.

## Rerun

```
C:/Users/Cornell/.conda/envs/cv/python.exe cv/cv_field/c1_yolo_video_test.py --run D:/Field2026_analysis_out/2026c/cv_field_c1yolo_video_20261005_1848 --steps tables media report
```
