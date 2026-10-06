# CH01 occlusion geometry for the WISER-flagged suspected misses (poles, houses) — 2026c

Driver `cv/cv_field/ch01_occlusion.py`; plan `implementation_plan/2026-10-06-ch01-occlusion-geometry.md` (pre-registered, approved 2026-10-06 "行上吧"; amendment 1 before results, amendment 2 after results = descriptive only); run `D:/Field2026_analysis_out/2026c/cv_field_ch01_occlusion_20261006_1445`; generated 2026-10-06 14:53; code `17cbcb42498de827366c5a14fe0eb023013948ff+dirty`; calibration `D:/Documents/GitHub/Field_2026_Social_Recording/calibration_qc` at recording-repo commit `a667cfe2a5d325e3f650ba6dcce1724946d84e3c` (frozen rev g; files identical to phase 0's: True). Hour: CH01 2026-09-06 21:00–22:00, the phase-0 suspected misses. The agent did not look at any frame or figure. Geometry says *hidden*; it never makes a label — a hidden animal gets no box and a *clear* suspected miss is still only a proposal.

**Blinding.** The user is filling `review_template.csv` of the phase-0 review clips. Per-episode and per-second classes are sealed in the run folder (`episodes.csv`, `seconds.csv.gz`); this report shows only pooled numbers over all episodes and the visibility mask. The phase-0 `wiser_spots.csv` stays unopened.

## Pooled result

Suspected-miss episodes (n 300) by geometry class: **hidden 31 (10.3 %)**, **partly 14 (4.7 %)**, **clear 154 (51.3 %)**, **ambiguous 101 (33.7 %)**.
Suspected-miss seconds (n 3482) by category: hidden 409 (11.7 %), partly 318 (9.1 %), clear 1705 (49.0 %), ambiguous 1050 (30.2 %); at the nominal WISER position alone: hidden 25.3 %, partly 9.1 %, clear 65.6 %.

By occluder (episodes whose class is not *clear*; occluder = the most frequent occluder of their non-clear seconds; *landmark check* = the object's own check below — results of a flagged object carry the flag):

| occluder | source | landmark check | hidden | partly | ambiguous | total |
|---|---|---|---:|---:|---:|---:|
| pole_B3 | measured line | ok (3 px) | 0 | 9 | 37 | 46 |
| pole_B2 | measured line | **flagged** (46 px) | 13 | 2 | 17 | 32 |
| house_2 | calibration house check (rev g) | ok (10 px) | 13 | 3 | 14 | 30 |
| pole_C2 | design grid | not checked (no CH01 labels) | 0 | 0 | 19 | 19 |
| house_1 | WISER ROI house_1 centre through the accepted map | **flagged** (125 px) | 5 | 0 | 1 | 6 |
| pole_B4 | design grid | not checked (no CH01 labels) | 0 | 0 | 4 | 4 |
| pole_C1 | design grid | **flagged** (58 px) | 0 | 0 | 4 | 4 |
| pole_B1 | measured line | ok (3 px) | 0 | 0 | 3 | 3 |
| pole_B0 | design grid | **flagged** (41 px) | 0 | 0 | 2 | 2 |

Seconds by occluder (non-clear seconds; last column = share of them whose 7-in WISER ring crosses a paddock wall, amendment 2):

| occluder | hidden | partly | ambiguous | total | ring crosses a wall |
|---|---:|---:|---:|---:|---:|
| pole_B3 | 0 | 245 | 489 | 734 | 6.5 % |
| house_2 | 162 | 27 | 166 | 355 | 0.0 % |
| pole_B2 | 118 | 37 | 148 | 303 | 76.6 % |
| house_1 | 129 | 0 | 16 | 145 | 0.0 % |
| pole_C2 | 0 | 3 | 135 | 138 | 93.5 % |
| pole_C1 | 0 | 0 | 38 | 38 | 94.7 % |
| pole_B1 | 0 | 5 | 26 | 31 | 0.0 % |
| pole_B4 | 0 | 0 | 21 | 21 | 42.9 % |
| pole_B0 | 0 | 0 | 9 | 9 | 0.0 % |
| pole_C3 | 0 | 1 | 2 | 3 | 66.7 % |

Reading guide (amendment 2, descriptive): the 8 perturbed positions are not clipped to the paddock, so along a wall a 7-in move can put the animal outside, behind a wall-line pole; such seconds count as *ambiguous* (30.0 % of all ambiguous seconds have a ring crossing a wall). A thin pole a few metres from CH01 throws a shadow narrower than the 7-in WISER uncertainty at the animal's distance, so it yields *partly* / *ambiguous*, almost never robustly *hidden*; the houses and the near pole B2 can hide robustly.

Visibility mask: 18976 2-in cells in CH01's support; a rat is hidden (h ≥ 0.8) in 8.9 % of them and partly hidden in 4.3 %. Hidden share by object: pole_B2 2.6 %, house_1 2.4 %, house_2 2.3 %, pole_B1 1.0 %, pole_B3 0.9 %, pole_B0 0.0 %, pole_B4 0.0 %, pole_C1 0.0 %. Figure [`visibility_mask.png`](../figures/ch01_occlusion/visibility_mask.png); pooled classes [`class_shares.png`](../figures/ch01_occlusion/class_shares.png); array `visibility_mask.npz` in the run folder.

## Inputs and the rebuilt per-second table

The phase-0 per-second suspected-miss table had not been saved; it was rebuilt with the unchanged phase-0 code (`wiser_assist_p0.prepare_boxes` + `part_c`, accepted map d (-272.85, -605.80) in, θ 0.114°, s 0.9634, L +0.0 s): 3482 suspected-miss seconds of 8925 eligible animal-seconds; the regenerated `fn_episodes.csv` is **byte-identical** to phase 0's: True (`fn_grid.csv` too: True). Saved as `miss_seconds_rebuilt.csv.gz`.

## Occluders

Camera CH01 centre (240.6, 87.6) in, 2292 mm (`RayCamera.centre`). Poles: capsules of the surveyed radius from the local ground to 2.4 m. Houses: the house check's rigid model (body box to the eave height + gable-roof prism with the 66-cm ridge and the roof overhang).

| object | position (in) | source | size | lean |
|---|---|---|---|---|
| pole A0 | (0.0, 0.0) at the ground | design grid (field_layout.json): 1 clean heights (< 2) | r 71 mm (mean of the surveyed poles) | 0.0° |
| pole A1 | (120.0, 0.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | r 71 mm (mean of the surveyed poles) | 0.0° |
| pole A2 | (240.0, 0.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | r 71 mm (mean of the surveyed poles) | 0.0° |
| pole A3 | (360.0, 0.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | r 71 mm (mean of the surveyed poles) | 0.0° |
| pole A4 | (480.0, 0.0) at the ground | design grid (field_layout.json): fitted lean 23 deg > 15 (not credible) | r 71 mm (mean of the surveyed poles) | 0.0° |
| pole B0 | (0.0, 120.0) at the ground | design grid (field_layout.json): 1 clean heights (< 2) | r 71 mm (mean of the surveyed poles) | 0.0° |
| pole B1 | (131.2, 125.2) at the ground | measured (pole-check method on rev g, 01+02) | r 75 mm (survey perimeter / 2 pi) | 9.5° |
| pole B2 | (242.2, 115.1) at the ground | measured (pole-check method on rev g, 01+02) | r 67 mm (survey perimeter / 2 pi) | 3.6° |
| pole B3 | (357.3, 119.5) at the ground | measured (pole-check method on rev g, 01+02) | r 71 mm (survey perimeter / 2 pi) | 6.4° |
| pole B4 | (480.0, 120.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | r 71 mm (mean of the surveyed poles) | 0.0° |
| pole C0 | (0.0, 240.0) at the ground | design grid (field_layout.json): 1 clean heights (< 2) | r 71 mm (mean of the surveyed poles) | 0.0° |
| pole C1 | (120.0, 240.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | r 71 mm (mean of the surveyed poles) | 0.0° |
| pole C2 | (240.0, 240.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | r 71 mm (mean of the surveyed poles) | 0.0° |
| pole C3 | (360.0, 240.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | r 71 mm (mean of the surveyed poles) | 0.0° |
| pole C4 | (480.0, 240.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | r 71 mm (mean of the surveyed poles) | 0.0° |
| house_1 | (142.0, 114.2), ridge 90.1° | WISER ROI house_1 centre through the accepted map | 62.55 × 45.72 cm, eaves 59.0 cm, ridge 88.2 cm, soil at z -58 mm | – |
| house_2 | (342.4, 117.7), ridge 92.0° | calibration house check (rev g) | 62.55 × 45.72 cm, eaves 60.8 cm, ridge 87.8 cm, soil at z -93 mm | – |

house_1 (moved on 09-18) is placed from the WISER ROI `house_1` (411.5, 718.6) through the accepted map → (142.0, 114.2) in, 9.3 in from the calibration's post-move position (147.5, 121.7) — not used. Map check on house_2: its WISER ROI through the same map lands at (336.7, 113.4) in, **7.2 in** from the calibration's (342.4, 117.7): the ROI rectangles are hand-placed, so house_1's WISER placement carries an error of that order.

### Pole re-measurement (amendment 1)

The pole check (`calibration_qc/pole_check.py`, `session_2026-09-18_pole_check.txt`, 2026-10-01) ran on a fit before revisions e–g, so its method was re-run read-only on the frozen rev g cameras with the operator's 09-18 pole-edge labels (CH01–CH04): per camera and height the axis offset across the line of sight, then per height the least-squares crossing of the cameras' lines. Clean rule (fixed before any occlusion result): ≥ 2 heights each seen by ≥ 2 cameras crossing at ≥ 10° (camera residual ≤ 50 mm with ≥ 3 cameras), a straight line in height through them with residuals ≤ 50 mm, its 1.05-m point ≤ 400 mm from the design grid, and a lean ≤ 15° (this bound was added after the pole table, before any occlusion result; it removes only A4, whose two-height line leaned 23°); else the vertical design-grid line. Per-height triangulations: `pole_triangulation_revg.csv`. Check against the operator's tape (survey, centre to centre at ≈ 1.05 m), measured lines at 1.05 m above the ground: B1–B2 120.9 in (tape 120 in); B2–B3 117.4 in (tape 116 in).

## Landmark checks (model projected into CH01 vs the user's labels)

Median pixel distance from the labelled edges to the projected model edges (poles: left / right silhouette; houses: each label piece to its nearest allowed rigid edge, house_check's classes). Flag > 20 px (results then flagged, not refitted). 09-18 labels compared in 09-18 px (+ the IR → colour offset (0.68, −0.39) px, as house_check); the 09-04 cohort house_1 labels mapped to 09-18 px with `Corrections.to_09_18` at the label time (2026-09-04 12:00:02; correction sample ['2026-09-04 21:00:00'], flag night; its shift at the frame centre (-13.4, -5.8) px; the daily 12:00 track of that frame gives (−10.1, −2.0) px — the night sample is used as instructed, the difference is stated).

| object | labels | model | label points | median px | p90 px | flagged |
|---|---|---|---:|---:|---:|---|
| pole_A0 | 09-18 | design grid | 56 | 57.4 | 77.7 | **yes** |
| pole_B0 | 09-18 | design grid | 67 | 40.6 | 76.1 | **yes** |
| pole_B1 | 09-18 | measured | 184 | 3.0 | 9.5 | no |
| pole_B2 | 09-18 | measured | 245 | 45.5 | 119.9 | **yes** |
| pole_B3 | 09-18 | measured | 85 | 3.0 | 6.6 | no |
| pole_C0 | 09-18 | design grid | 44 | 24.6 | 34.7 | **yes** |
| pole_C1 | 09-18 | design grid | 14 | 58.2 | 71.9 | **yes** |
| house_2 | 09-18 | house check rev g pose | 169 | 9.8 | 148.3 | no |
| house_1 | 09-04 cohort (-> 09-18 px) | WISER ROI through the map | 161 | 124.8 | 188.8 | **yes** |
| house_1 (09-18 post-move pose; code check only) | 09-18 | house check rev g pose | 169 | 19.5 | 27.6 | no |

Flagged: pole_A0, pole_B0, pole_B2, pole_C0, pole_C1, house_1. The occlusion results involving a flagged object carry that flag (the pooled by-occluder rows above name the object).

Why (descriptive, amendment 2): the design-grid poles A0, B0, C0, C1 miss their labels by 25–58 px, i.e. ≈ 0.6–1.4° or ≈ 8–15 cm across the line of sight at 4.9–8.2 m — the 10-ft grid is not control (the calibration says so). B2 stands 0.82 m from CH01, and CH01 and CH02 see it from nearly opposite sides (17° from collinear), so its position along that line is poorly constrained; its 45 px are ≈ 1° ≈ 15 mm across CH01's line of sight (a diagnostic exact-ray triangulation, not used, is far less stable). house_1's 125 px is the WISER-ROI placement error (house_2's ROI through the same map lands 7.2 in from its calibrated position). The code check (the calibration's own post-move house_1 against the 09-18 labels, 19.5 px; house_2 9.8 px) matches the calibration's reported fit (rays miss by a median 24 / 11 mm), so the projection itself is sound. The 3-px agreement of B1 and B3 is not an independent test: CH01's own pole-edge labels entered their triangulation. The 09-04 label correction (night sample) and the daily 12:00 track differ by ≈ 5 px at the frame centre, immaterial next to house_1's miss.

## Definitions

Units: paddock mm / inches (origin pole A0); z = the calibration's absolute height datum (camera centre, terrain, house soil levels). $\mathbf C$ = CH01's centre; $\mathbf p$ = an animal's paddock position (WISER through the accepted map); $g(\mathbf p)$ = local ground height (terrain).

### Rat sample points
$$ \mathbf q_{kl}=\big(\mathbf p+o_l\,\hat{\mathbf n},\ g(\mathbf p)+z_k\big),\quad z_k\in\{30,60,90\}\,\mathrm{mm},\ o_l\in\{-40,0,40\}\,\mathrm{mm} $$ **Text:** a rat's body as 9 points; $\hat{\mathbf n}$ = horizontal unit normal to the line of sight from CH01.

### Hidden share $h$
$$ h(\mathbf p)=\frac{1}{9}\sum_{k,l}\mathbb 1\big[\exists\,O:\ [\mathbf C,\mathbf q_{kl}]\cap O\neq\emptyset\big] $$ **Text:** share of the body points whose line of sight to the camera passes through a pole capsule (segment–axis distance ≤ radius) or a house part (Cyrus–Beck clipping of the segment by the convex part). Range [0, 1].

### Classes
nominal: hidden $h\ge0.8$, partly $0<h<0.8$, clear $h=0$. Robust over the nominal position and 8 positions 7 in away (WISER uncertainty): robustly hidden = hidden at all 9, robustly clear = $h=0$ at all 9. **Category** (amendment 1): hidden = robustly hidden; clear = robustly clear; partly = nominal $0<h<0.8$; ambiguous = otherwise. **Episode class** = the unique majority category of its seconds (ties → ambiguous). **Occluder** of a second = the object blocking the most sample points summed over the 9 positions; of an episode = the most frequent occluder of its non-clear seconds.

### Landmark distance
$$ d_i=\min_{\mathbf s\in\pi(E)}\lVert \mathbf u_i-\mathbf s\rVert $$ **Text:** pixel distance from a densified label point $\mathbf u_i$ (every ≈ 15 px) to the projected model edge $\pi(E)$ (3-D edge points projected with the calibration's own inverse, each verified to 0.02°); median per object.

## Caveats

- Grass, other rats, the animal's posture and objects not surveyed (water dish, feeders, cables) are not modelled: they can hide a *clear* animal. One hour, one camera.
- house_1's cohort position comes from a hand-placed WISER ROI through the map (house_2's ROI lands 7.2 in from its calibrated position); its landmark check says how far off the box is.
- Poles not measured cleanly stand vertical at the design grid; the survey shows the B row 11 in short (B0 / B4 inside the line).
- The 7-in perturbation is the WISER error scale; WISER's own error is larger in some seconds.

## Outputs

Run folder `D:/Field2026_analysis_out/2026c/cv_field_ch01_occlusion_20261006_1445`: `occluders.json`, `checks.csv`, `visibility_mask.npz`, `miss_seconds_rebuilt.csv.gz`, `pole_edges_revg.csv`, `pole_triangulation_revg.csv`, `run.json`, `run_log.txt`; **sealed**: `episodes.csv`, `seconds.csv.gz` (`SEALED_README.txt`). Figures `results/2026c/cv_field/figures/ch01_occlusion/`. Pointer `run_manifest_ch01_occlusion_2026c.json`.

## Rerun

```
C:/Python313/python.exe cv/cv_field/ch01_occlusion.py --run
```
