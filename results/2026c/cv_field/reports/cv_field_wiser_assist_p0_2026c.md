# WISER-assisted YOLO, phase 0 — WISER → CH01 mapping, fixed-spot presence (sealed), suspected YOLO misses (2026c)

Driver `cv/cv_field/wiser_assist_p0.py`; plan `implementation_plan/2026-10-05-wiser-assisted-yolo-p0.md` (pre-registered, approved 2026-10-05; amendment 1 before results, amendments 2–3 after results, all dated in the plan); run `D:/Field2026_analysis_out/2026c/cv_field_wiser_assist_p0_20261005_2211`; generated 2026-10-05 22:13; code `da6666bef01f3e710a656ae141838fbebb9ef446+dirty`. Hour: CH01, field-PC 2026-09-06 21:00–22:00 (the step-2 hour; YOLO v5 detections from `cv_field_c1yolo_video_20261005_1848`). The agent did not look at any frame, video or figure; WISER positions are proposals, never boxes or labels; no training. This hour is now **WISER-touched** and cannot later serve as an independent CV-vs-WISER validation.

## Verdict

- Mapping **ACCEPTED**. Rule fixed in the plan, judged once on the test blocks (2, 4, …, 12): the chosen model's test median residual ≤ 14 in **and** the negative control's within-14-in share ≤ half the chosen model's. Test median **4.39 in** (criterion 1 met); within-14-in share **88.5 %** vs control **2.9 %** (criterion 2 met).
- Model and lag chosen on the fit blocks only (amendment 2: inner fit 1, 5, 9, inner validation 3, 7, 11): inner-validation median residual translation 6.03 in vs similarity 4.17 in, gain 30.9 % → **similarity** (≥ 10 % needed). Refitted on the six fit blocks: **d = (-272.85, -605.80) in**, θ = 0.114°, s = 0.9634 about c = (501.7, 761.1) in (WISER frame); lag **L = +0.0 s** (cost +10 % / +9 % at L − 0.5 / + 0.5 s). L is reported only, never written into a clock configuration (separate plan `2026-10-05-video-clock-sync.md`).

- Before amendment 2 (run `D:/Field2026_analysis_out/2026c/cv_field_wiser_assist_p0_20261005_2158`, superseded) the model was picked on the **test** blocks: test median translation 5.54 in vs similarity 4.39 in (gain 20.8 %) → similarity; acceptance was judged on the translation's test median (5.54 in; within-14 87.1 % vs control 2.9 %) → accepted. New selection: similarity; verdict **unchanged**; the final map and L equal the superseded run's; B file byte-identical: yes; C episodes identical (apart from the new `kind` column): yes.
- C: **300 suspected-miss episodes** (≥ 3 consecutive seconds), **2885 s** in episodes; all suspected-miss seconds 3482 of 8925 eligible animal-seconds. Proposals for the user's eyes only — never boxes or labels.
- B: produced and **sealed** (see B).

## Inputs and exclusions

- Frames: 3600 sampled (one per whole second; the sampled PTS is at most 0.090 s from the second) of 72000.
- A detections (sampled frames, conf ≥ 0.5): 6099; dropped 881 with the centre in a fixed-spot cell (40-px cells with occupancy ≥ 5 %: 3 cells), 0 for a correction flag ≠ ok, 609 outside CH01's verified calibration support; **used 4609**.
- Camera chain: `Corrections("2026c").to_paddock("CH01", t, uv, z_mm=60, units="in")`; night 2026-09-06, flag `ok`, samples ['2026-09-06 21:00:00', '2026-09-06 22:00:00'], night quality dawn closure 1.65 px, rain 21:00–04:20 0.0 mm.
- WISER: default tracks SF07–SF12 of 2026-09-06 (V3 where the head IMU passes QC, B2 elsewhere), rows with `valid` and no `m_*` mask; no handling window falls in 20:58–23:02; fixes used per animal: SF07 29230, SF08 29124, SF09 29307, SF10 29393, SF11 29306, SF12 29605.

## A. Mapping WISER → paddock

Blocks of 5 min: odd = fit (1, 3, …, 11), even = test (2, 4, …, 12). The test blocks are used once, for the verdict and the reported test numbers.

### A1. Model and lag selection — fit blocks only (inner fit 1, 5, 9, inner validation 3, 7, 11)

| quantity | translation (d) | similarity (θ, s, d) |
|---|---:|---:|
| d (in), inner fit | (-272.39, -605.68) | (-272.23, -606.04) |
| θ (°), s | 0, 1 (fixed) | 0.162, 0.9639 |
| lag L (s) | +0.0 | +0.0 |
| iterations (converged) | 3 (True) | 3 (True) |
| inner-fit pairs | 1129 | 1130 |
| inner-validation detections | 908 | 908 |
| inner-validation matched pairs (share) | 789 (86.9 %) | 789 (86.9 %) |
| **inner-validation residual median / p90 (in)** | **6.03 / 12.06** | **4.17 / 7.90** |
| inner-validation within-14-in share | 83.5 % | 86.2 % |
| gain of the similarity (rule ≥ 10 %) | – | **30.9 % → similarity** |

### A2–A4. Chosen model refitted on the six fit blocks; negative control; test blocks

| quantity | chosen: similarity (fit blocks 1–11 odd) | negative control: WISER + 1 h, translation |
|---|---:|---:|
| d (in) | (-272.85, -605.80) | (-270.77, -605.83) |
| θ (°), s | 0.114, 0.9634 | 0, 1 (fixed) |
| lag L (s) | +0.0 | +90.0 (relative to + 3600 s) |
| iterations (converged) | 3 (True) | 4 (True) |
| translation start: coarse best d (score) → refined d, L | (-276.5, -609.5) (90.4 %) → (-273.25, -605.40), +0.0 s | (-258.1, -617.3) (9.2 %) |
| fit pairs | 1919 | 302 |
| test detections | 2472 | 2472 |
| test matched pairs (share of detections) | 2203 (89.1 %) | 198 (8.0 %) |
| **test residual median / p90 (in)** | **4.39 / 9.83** | 16.82 / 27.04 |
| **within-14-in share (all test detections)** | **88.5 %** | **2.9 %** |
| within-14-in share, animals in the houses also counted | 98.1 % | 3.7 % |

The control's lag sits where its cost is flat (within 5 % of its minimum from 21.5 to 90.0 s), as expected without correspondence.

By the WISER animal's head-IMU state (test blocks, chosen model; residuals by the matched animal's state, within-14 by the nearest animal's state):

| subset | pairs | residual median (in) | residual p90 (in) | detections (nearest in this state) | within-14-in share |
|---|---:|---:|---:|---:|---:|
| still | 12 | 10.13 | 21.34 | 13 | 76.9 % |
| moving (active + locomoting) | 2066 | 4.44 | 9.83 | 2308 | 88.8 % |
| active | 1250 | 4.61 | 10.47 | 1415 | 86.9 % |
| locomoting | 816 | 4.24 | 8.74 | 893 | 91.9 % |
| IMU unusable | 125 | 3.87 | 8.79 | 151 | 84.1 % |

Only 12 test pairs involve an IMU-still animal: at night the animals outside the houses were almost never IMU-still, so the still subset (free of timing error) is too small to separate timing error from spatial error here.

Per animal (test blocks; pairs by the matched animal, within-14 by the nearest animal):

| animal | pairs | residual median (in) | residual p90 (in) | detections nearest to it | within-14-in share |
|---|---:|---:|---:|---:|---:|
| SF07 | 540 | 3.91 | 8.64 | 562 | 95.0 % |
| SF08 | 371 | 4.39 | 9.68 | 455 | 80.9 % |
| SF09 | 490 | 3.82 | 8.88 | 579 | 86.4 % |
| SF10 | 400 | 5.50 | 11.03 | 427 | 92.5 % |
| SF11 | 0 | – | – | 5 | 0.0 % |
| SF12 | 402 | 5.03 | 11.72 | 444 | 87.8 % |

Descriptive diagnostics (amendment 3, after results; nothing is decided on them):

- Of the 2472 test detections, 285 have no animal outside the houses within 14 in; 239 of those have an animal that WISER places inside a house zone (house rectangle + 14 in) within 14 in — boxes of animals at the house edges, which the plan's outside-the-houses rule leaves unmatched.
- Similarity scale s = 0.9634: a WISER displacement maps to a paddock displacement about 3.7 % shorter within CH01's view. Whether WISER's inch scale or the exploratory calibration is off is not determined here.
- Test residuals by 80-in paddock x band (chosen model; signed = detection − mapped animal; a local mapping offset would show as a non-zero signed median):

| x band (in) | detections | pairs | residual median / p90 (in) | signed dx / dy median (in) | within-14 | within-14 incl. houses |
|---|---:|---:|---|---|---:|---:|
| -80–0 | 2 | 2 | 18.02 / 22.45 | -17.46 / 2.82 | 50.0 % | 50.0 % |
| 0–80 | 152 | 150 | 5.75 / 10.43 | -1.92 / 4.14 | 96.7 % | 96.7 % |
| 80–160 | 369 | 221 | 4.55 / 10.02 | -1.84 / 2.46 | 57.7 % | 98.1 % |
| 160–240 | 728 | 708 | 5.18 / 11.53 | -3.08 / -2.00 | 95.9 % | 96.3 % |
| 240–320 | 560 | 515 | 2.83 / 6.40 | 0.60 / 0.60 | 93.9 % | 100.0 % |
| 320–400 | 241 | 187 | 4.27 / 6.94 | -0.07 / -1.34 | 78.0 % | 100.0 % |
| 400–480 | 384 | 384 | 4.95 / 8.44 | 1.17 / -2.76 | 100.0 % | 100.0 % |
| 480–560 | 36 | 36 | 10.16 / 16.55 | 9.05 / -1.47 | 83.3 % | 83.3 % |

- Reference only (not a criterion): house_2, which never moved, sits at paddock (347.0, 119.1) in in `cv/configs/field_layout.json` and at WISER (613.6, 717.3) in in `wiser_rois.json`, implying d ≈ (-266.5, -598.3) in; the fitted translation d differs from it by 9.8 in (both reference positions are hand-placed rectangles, ± several inches).

Figures (made by the driver; the agent did not look at them): [`coarse_grid.png`](../figures/wiser_assist_p0/coarse_grid.png), [`lag_profile.png`](../figures/wiser_assist_p0/lag_profile.png), [`test_distances.png`](../figures/wiser_assist_p0/test_distances.png).

## B. WISER presence at the fixed spots — sealed

**Sealed until the user's verdicts in `fixed_spots_review.csv` are in.** The table was written only to the run folder (`wiser_spots.csv`); no B number appears in this report, the run log, the run's other files or the agent's messages. Method (plan B): each spot's median pano centre (from `fixed_spots/fixed_spots.csv`) is mapped to paddock inches with `to_paddock` at the time of the spot's middle frame (z = 60 mm), then into the WISER frame by the inverse of the accepted map. Per minute of the hour: the spot is *on* if it has a box (conf ≥ 0.25) in ≥ 50 % of the minute's frames (the step-2 per-minute occupancy); per second, the distance from the spot to the nearest located tagged animal (all six, in or out of the houses) at second + L; the minute's distance is the median of those seconds; the minute's nearest animal is the most frequent per-second nearest one, with its share of `imu_state = still` seconds. Per spot: minutes on and off, of each those with the animal within 14 in and within 30 in, and with a *still* animal within 14 in (minute distance ≤ 14 in and still share ≥ 50 %); Spearman ρ between per-minute occupancy and the within-14-in indicator. A spot outside CH01's calibrated support gets NaN. **WISER can only add presence:** a minute with no tagged animal near a spot is not evidence that no rat is there (dropout, a failed tag, an untagged animal). The agreement table (user verdict vs WISER) is a separate later step, run only after the user's verdicts.

## C. Suspected YOLO misses (for the user's labelling; not a metric, never boxes)

- CH01 ground support: 6294 of the 40-px pixel cells map with all four corners (to_paddock at 2026-09-06 21:30:00, z = 60 mm); area 78681 in², **66.6 % of the 480 × 240-in paddock** (outline in `support_polygon.json`).
- Animal-seconds located outside the houses: 14903; of those inside the support: 8925; suspected-miss seconds (no box ≥ 0.25 within 20 in in the sampled frame): **3482 (39.0 %)**; episodes ≥ 3 s: **300**, 2885 s. (Step 2 found the YOLO count below the WISER outside-count in 69 % of 5-s bins.)
- Per animal: SF07 58 episodes / 405 s (suspected miss 541 of 1722 s); SF08 50 episodes / 802 s (suspected miss 926 of 1721 s); SF09 59 episodes / 566 s (suspected miss 704 of 1866 s); SF10 79 episodes / 686 s (suspected miss 803 of 1782 s); SF11 4 episodes / 41 s (suspected miss 45 of 150 s); SF12 50 episodes / 385 s (suspected miss 463 of 1684 s).
- Where (descriptive, amendment 3): the 40-in cell x 440–480, y 120–160 in holds 725 suspected-miss seconds (20.8 % of all; 80.9 % of its 896 eligible animal-seconds). The 106 part-A detections that do fall in that cell match a WISER animal with median residual 5.01 in, so the mapping there is not off; what hides or fails to box the animals there is for the user to judge. Top cells:

| cell x, y (in) | eligible animal-s | suspected-miss s | share | in episodes (s) |
|---|---:|---:|---:|---:|
| 440–480, 120–160 | 896 | 725 | 80.9 % | 706 |
| 240–280, 200–240 | 671 | 390 | 58.1 % | 297 |
| 200–240, 200–240 | 691 | 312 | 45.2 % | 276 |
| 360–400, 80–120 | 371 | 198 | 53.4 % | 185 |
| 320–360, 200–240 | 372 | 185 | 49.7 % | 147 |

Ten longest episodes (all in `fn_episodes.csv`; pano pixel = the nearest 40-px grid centre to the episode's median paddock position — a pointer for the user's eyes, not a box; *box frames* = share of the frames within ± 0.5 s of each second that hold a box within 20 in — a flicker indicator):

| # | start (field-PC, video nominal) | s | animal | paddock x, y (in) | pano u, v (px) | IMU state (still share) | box frames |
|---:|---|---:|---|---|---|---|---:|
| 206 | 21:41:41 | 156 | SF08 | 445, 136 | 6820, 1180 | active (0.0 %) | 0.1 % |
| 22 | 21:03:12 | 108 | SF10 | 455, 140 | 6820, 1100 | active (0.0 %) | 1.2 % |
| 296 | 21:58:20 | 99 | SF08 | 106, 120 | 1940, 1660 | active (0.0 %) | 0.0 % |
| 63 | 21:16:04 | 90 | SF09 | 431, 48 | 7380, 2020 | active (0.0 %) | 0.0 % |
| 165 | 21:33:51 | 76 | SF08 | 223, 232 | 4020, 220 | active (0.0 %) | 0.3 % |
| 236 | 21:47:56 | 72 | SF10 | 449, 131 | 6860, 1220 | active (0.0 %) | 0.5 % |
| 205 | 21:40:41 | 49 | SF08 | 376, 117 | 6540, 1500 | active (0.0 %) | 0.0 % |
| 201 | 21:39:34 | 41 | SF08 | 365, 116 | 6420, 1540 | active (0.0 %) | 0.0 % |
| 250 | 21:49:32 | 36 | SF12 | 451, 135 | 6860, 1180 | active (0.0 %) | 3.9 % |
| 258 | 21:51:19 | 35 | SF10 | 273, 235 | 4660, 220 | active (0.0 %) | 0.0 % |

A suspected miss can also be occlusion (grass, a house roof), WISER error (≈ 3 in still, 4–7 in raw jitter) plus mapping error, an animal out of view near the support edge, or a box displaced > 20 in from the tag. Episodes are proposals for the user's eyes only: **never a box or a label — an occluded animal must not get a box.** Map: [`fn_map.png`](../figures/wiser_assist_p0/fn_map.png).

## Definitions

Units: paddock and WISER positions in **inches** (paddock = the 09-24 calibration frame, origin pole A0, 480 × 240 in; WISER = the unverified native inch frame); pixels = upright pano pixels (7680 × 2160); times in seconds. $s \in \{0,\dots,3599\}$ = second of the hour after the file-name start; $k(s)$ = the frame with PTS nearest $s$; $i$ = a detection; $j$ = an animal; $\mathbf p_i$ = paddock position of detection $i$; $\mathbf w_j(t)$ = WISER position of animal $j$ at WISER time $t$; blocks $b(s)=\lfloor s/300\rfloor+1$.

### Detection position ($\mathbf p_i$)
$$ \mathbf p_i = \mathrm{to\_paddock}_{CH01}\big(t_s,\ ((x_1+x_2)/2,\ (y_1+y_2)/2),\ z=60\,\mathrm{mm}\big) $$ **Text:** the YOLO box centre mapped through the per-night frame correction and the 09-24 calibration at the assumed height of a rat's back, evaluated at the whole second $t_s$ nearest the frame (the correction drifts by a fraction of a pixel per hour). Undefined outside CH01's verified support. Units: in.

### WISER position at a query time ($\mathbf w_j(t)$)
$$ \mathbf w_j(t) = \mathbf w_{j,a} + \frac{t-t_a}{t_b-t_a}(\mathbf w_{j,b}-\mathbf w_{j,a}),\quad t_a\le t<t_b,\ t_b-t_a\le 5\,\mathrm s $$ **Text:** linear interpolation of the default track between the two bracketing clean fixes (valid, no mask); not located if they are more than 5 s apart. IMU state = that of the nearer fix (0 unusable, 1 still, 2 active, 3 locomoting). *Outside the houses* = not inside either house rectangle of `wiser_rois.json` grown by 14 in. Units: in. A not-located animal is unknown, never absent.

### Map and lag ($T$, $\mathbf d$, $L$)
$$ T(\mathbf w) = s\,R(\theta)(\mathbf w-\mathbf c)+\mathbf c+\mathbf d,\qquad \text{translation: } \theta=0,\ s=1 \Rightarrow T(\mathbf w)=\mathbf w+\mathbf d $$ Detection $i$ in second $s$ is compared with $T(\mathbf w_j(s+L))$. **Text:** $\mathbf d$ (in) moves the WISER frame onto the paddock frame (the axes are known to align); $L$ (s) is the clock lag: $L>0$ means the video's nominal time (file-name start + PTS) runs $L$ s behind the WISER/field-PC clock (it also absorbs WISER's ≈ 0.1–0.2 s fix latency). $\mathbf c$ = the mean WISER position of the pairs of the translation fit the similarity starts from, so the similarity's $\mathbf d$ is comparable with the translation's.

### Coarse score ($G(\mathbf d)$)
$$ G(\mathbf d)=\frac{1}{|I_{fit}|}\sum_{i\in I_{fit}}\mathbb 1\Big[\min_{j\in J_{out}(s_i)}\lVert \mathbf p_i-\mathbf w_j(s_i)-\mathbf d\rVert\le 20\Big] $$ on $\mathbf d\in\bar{\mathbf p}-\bar{\mathbf w}+\{-100,-98,\dots,100\}^2$ **Text:** share of the fit's detections with an animal (outside the houses, at $L=0$) within 20 in; $\bar{\mathbf p}$ = mean of those detections, $\bar{\mathbf w}$ = mean WISER position of the outside animals over the fit's seconds. Only the starting point of the refinement. Range [0, 1].

### Hungarian assignment and residual ($r_i$)
$$ \pi_s=\arg\min_{\pi}\sum_{(i,j)\in\pi}\min(D_{ij},30),\quad D_{ij}=\lVert\mathbf p_i-T(\mathbf w_j(s+L))\rVert,\quad r_i=D_{i\pi(i)}\ \text{if}\ D_{i\pi(i)}\le 30 $$ **Text:** per second, the one-to-one matching of detections to animals outside the houses with the smallest total gated distance; pairs beyond the 30-in gate are dropped (the detection is unmatched). $r_i$ = matched-pair residual (in), truncated at 30 in by construction — read the median / p90 together with the matched share.

### Lag cost ($C(L)$) and the fit
$$ C(L)=\frac{1}{|I_{fit}|}\sum_{i\in I_{fit}}\rho_6\big(\min(r_i,30)\big),\quad \rho_k(r)=\begin{cases}r^2/2 & r\le k\\ k(r-k/2) & r>k\end{cases} $$ (unmatched $r_i=\infty$ costs $\rho_6(30)$), $$ \hat{\mathbf d}=\arg\min_{\mathbf d}\sum_{(i,j)}\rho_6\big(\lVert\mathbf p_i-\mathbf w_j-\mathbf d\rVert\big)\ \text{(IRLS)} $$ **Text:** from the coarse best $\mathbf d$: choose $L$ on the 0.5-s grid in [−90, 90] s minimising $C(L)$ (ties → smallest $|L|$), match, re-fit $\mathbf d$ by Huber least squares (k = 6 in ≈ the raw jitter, so jittery pairs count fully and outliers linearly), repeat until $\mathbf d$ moves < 0.1 in; $L$ is re-chosen once at the final $\mathbf d$. The similarity fit does the same with a weighted Umeyama similarity under Huber weights, starting from the translation fit on the same blocks. $I_{fit}$ = the detections of the blocks the fit may use. Units: $C$ in in².

### Model selection (amendment 2)
$$ g=\frac{\tilde r^{val}_{transl}-\tilde r^{val}_{sim}}{\tilde r^{val}_{transl}},\qquad \text{similarity chosen}\iff g\ge 0.10 $$ **Text:** both models (and their $L$) fitted on fit blocks 1, 5, 9; $\tilde r^{val}$ = median matched residual on fit blocks 3, 7, 11. The chosen model is then refitted (with its $L$) on all six fit blocks. The test blocks play no part in the choice.

### Test statistics
$$ \tilde r=\operatorname{median}_{i\in I_{test},\,matched} r_i,\quad r_{90}=P_{90}(r_i),\quad f_{14}=\frac{1}{|I_{test}|}\sum_{i\in I_{test}}\mathbb 1\Big[\min_{j\in J_{out}(s_i)}\lVert\mathbf p_i-T(\mathbf w_j(s_i+L))\rVert\le 14\Big] $$ **Text:** on the even blocks, once, with the chosen model: the median and 90th percentile of matched residuals (in) and the share of ALL test detections (denominator includes unmatched ones and seconds without any outside animal) with an animal within 14 in (nearest animal, no one-to-one constraint). By IMU state: residuals grouped by the matched animal's state, $f_{14}$ by the nearest animal's state (denominator = detections whose nearest animal is in that state). Signed residual by x band = $\operatorname{median}(\mathbf p_i-T(\mathbf w_{\pi(i)}))$ per axis. 14 in = twice the ≈ 7-in WISER jitter and the repo's minimum resolvable distance.

### Negative control
$$ \mathbf w^{ctrl}_j(t)=\mathbf w_j(t+3600\,\mathrm s) $$ **Text:** WISER from 22:00–23:00 placed on the 21:00–22:00 frames and refitted identically (translation, six fit blocks, own coarse grid, $L$ grid relative to +3600 s). It keeps where the animals tend to be (the spatial density) but breaks the frame-by-frame correspondence; $f^{ctrl}_{14}$ measures how often a detection lands within 14 in of *some* animal by chance after a free fit.

### Acceptance
$$ \text{accepted}\iff \tilde r_{chosen}\le 14\ \wedge\ f^{ctrl}_{14}\le \tfrac12 f_{14,chosen} $$ **Text:** fixed in the plan before any result; judged once on the test blocks.

### B quantities (definitions only; values sealed)
$$ \mathrm{on}_m=\mathbb 1[O_m\ge 0.5],\quad \delta_m=\operatorname{median}_{s\in m}\min_j\lVert \mathbf w^{spot}-\mathbf w_j(s+L)\rVert,\quad \mathrm{near}_{14,m}=\mathbb 1[\delta_m\le 14],\quad \rho=\mathrm{Spearman}(O_m,\mathrm{near}_{14,m}) $$ **Text:** $O_m$ = the spot's step-2 occupancy in minute $m$ (share of the minute's frames with a box centre ≥ 0.25 in the spot's cells); $\mathbf w^{spot}=T^{-1}(\mathbf p^{spot})$; the minimum runs over all located animals (in or out of houses); the still variant also needs the nearest animal's still share in the minute ≥ 0.5. Units: in; $\rho\in[-1,1]$. $\mathrm{near}_{14,m}=0$ means no *tagged* animal is near, not no rat.

### C quantities
$$ \mathrm{miss}_{j,s}=\mathbb 1\big[j\notin\text{houses}\ \wedge\ T(\mathbf w_j(s+L))\in\mathcal S\ \wedge\ \min_{b\in B_{k(s)}}\lVert\mathbf p_b-T(\mathbf w_j(s+L))\rVert>20\big] $$ **Text:** a suspected miss: $\mathcal S$ = CH01 ground support (union of the 40-px pixel cells whose four corners map, rasterised at 1 in); $B_{k(s)}$ = the sampled frame's boxes with conf ≥ 0.25 (fixed-spot boxes included). An episode = ≥ 3 consecutive suspected-miss seconds of one animal; its position = the median of $T(\mathbf w_j)$ over its seconds; *box frames* = mean over its seconds of the share of frames within ± 0.5 s with a box within 20 in (0 = no frame of those seconds had one). Grid: suspected-miss seconds and eligible animal-seconds per 40-in paddock cell. Only tagged animals WISER locates can raise a suspected miss; WISER's silence never marks a frame or place as empty.

## Caveats

- One calm hour (rain 0.0 mm on night 09-06 per the correction table), one camera, six tagged animals; all numbers carry the WISER error (V3 still error ≈ 3 in, raw jitter 4–7 in), the calibration's exploratory error (cross-camera median 76 mm, p90 137 mm), the 60-mm height assumption (a box centre on a rat's flank or head is not at 60 mm) and the offset between a box centre and the tag on the animal.
- WISER never creates a negative: a missing WISER animal (dropout, failed tag, untagged animal — e.g. the females from 09-11) does not mean no rat, so nothing here marks a frame, minute or place as empty.
- The residual is truncated at the 30-in gate; the within-14-in share has no gate. YOLO false positives and duplicate boxes stay in the denominators (only fixed-spot cells are removed).
- WISER positions are proposals (never boxes or labels). The lag $L$ is a fitted nuisance parameter here, not a clock measurement.

## Outputs

Run folder `D:/Field2026_analysis_out/2026c/cv_field_wiser_assist_p0_20261005_2211`: `mapping.json` (selection, accepted map, d, L, θ, s, acceptance, fit histories, house_2 reference), `model_selection.csv` (inner validation), `pairs.csv.gz` (one row per A detection, all blocks with their role, chosen model: match, residual, nearest animal, IMU state), `residuals_test.csv` (test summaries of the chosen model and the control: all / IMU state / animal), `residuals_test_by_x.csv`, `control.json`, `lag_profiles.csv`, `run.json`, `run_log.txt`, `support_polygon.json`, `fn_episodes.csv`, `fn_grid.csv`, `wiser_spots.csv` (**sealed**). Figures in `results/2026c/cv_field/figures/wiser_assist_p0/`. Pointer `run_manifest_wiser_assist_p0_2026c.json`.

## Rerun

```
C:/Python313/python.exe cv/cv_field/wiser_assist_p0.py --run
```
