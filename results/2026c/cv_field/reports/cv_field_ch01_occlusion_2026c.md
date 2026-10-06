# CH01 occlusion geometry for the WISER-flagged suspected misses (poles, houses) — 2026c, v2

Driver `cv/cv_field/ch01_occlusion.py`; plan `implementation_plan/2026-10-06-ch01-occlusion-geometry.md` (pre-registered, approved 2026-10-06 "行上吧"; amendment 1 before results; amendment 2 after results, descriptive; **amendment 3 after results = v2**: house_1 at its fitted cohort pose, CH01-labelled poles hide by CH01's own edge planes, the 7-in perturbations clamped to the paddock); run `D:/Field2026_analysis_out/2026c/cv_field_ch01_occlusion_20261006_1555`; v1 run `D:/Field2026_analysis_out/2026c/cv_field_ch01_occlusion_20261006_1445` (superseded, `SUPERSEDED.txt`); generated 2026-10-06 15:59; code `97bf06f20c061c806a7ee652c802625e584b97a9+dirty`; calibration `D:/Documents/GitHub/Field_2026_Social_Recording/calibration_qc` at recording-repo commit `20e6c9bf768a6f793248da712145f8d307d344f1` (the calibration files are byte-identical to phase 0's and v1's: True). Hour: CH01 2026-09-06 21:00–22:00, the phase-0 suspected misses. The agent did not look at any frame or figure. Geometry says *hidden*; it never makes a label — a hidden animal gets no box and a *clear* suspected miss is still only a proposal.

**Blinding.** The user is filling `review_template.csv` of the phase-0 review clips. Per-episode and per-second classes are sealed in the run folder (`episodes.csv`, `seconds.csv.gz`); this report shows only pooled numbers over all episodes and the visibility mask. The phase-0 `wiser_spots.csv` stays unopened.

## Pooled result (v2)

| | n | hidden | partly | clear | ambiguous |
|---|---:|---:|---:|---:|---:|
| episodes, v1 | 300 | 10.3 % | 4.7 % | 51.3 % | 33.7 % |
| **episodes, v2** | 300 | **5.0 %** | **5.0 %** | **50.7 %** | **39.3 %** |
| seconds, v1 | 3482 | 11.7 % | 9.1 % | 49.0 % | 30.2 % |
| **seconds, v2** | 3482 | **5.2 %** | **10.6 %** | **48.8 %** | **35.5 %** |

Episode counts v2: hidden 15, partly 15, clear 152, ambiguous 118. Seconds at the nominal WISER position alone (v2): hidden 23.5 %, partly 10.6 %, clear 66.0 %. Perturbed positions clamped to the paddock (inset 1 in): **2283 of 27856** (8.2 %).

By occluder (episodes whose class is not *clear*; occluder = the most frequent occluder of their non-clear seconds; *model* = how that object hides in v2; *check* = its landmark check below):

| occluder | v2 model | check | hidden | partly | ambiguous | total | v1 total |
|---|---|---|---:|---:|---:|---:|---:|
| pole_B2 | CH01 L/R label planes | fit residual 3.7 px | 2 | 4 | 37 | 43 | 32 |
| pole_B3 | CH01 L/R label planes | fit residual 2.1 px | 0 | 7 | 36 | 43 | 46 |
| house_2 | house check rev g pose | check 9.8 px | 13 | 4 | 16 | 33 | 30 |
| pole_C2 | cylinder (capsule), design grid | not checked (no CH01 labels) | 0 | 0 | 14 | 14 | 19 |
| house_1 | fitted cohort pose | fit residual 7.6 px | 0 | 0 | 8 | 8 | 6 |
| pole_B4 | cylinder (capsule), design grid | not checked (no CH01 labels) | 0 | 0 | 4 | 4 | 4 |
| pole_B1 | CH01 L/R label planes | fit residual 2.4 px | 0 | 0 | 3 | 3 | 3 |
| pole_B0 | CH01 L/R label planes | fit residual 0.8 px | 0 | 0 | 0 | 0 | 2 |
| pole_C1 | CH01 L/R label planes | fit residual 0.3 px | 0 | 0 | 0 | 0 | 4 |

Seconds by occluder (non-clear seconds):

| occluder | hidden | partly | ambiguous | total | v1 total |
|---|---:|---:|---:|---:|---:|
| pole_B3 | 0 | 242 | 479 | 721 | 734 |
| house_2 | 162 | 31 | 171 | 364 | 355 |
| pole_B2 | 11 | 51 | 290 | 352 | 303 |
| house_1 | 7 | 34 | 125 | 166 | 145 |
| pole_C2 | 0 | 3 | 121 | 124 | 138 |
| pole_B1 | 0 | 6 | 26 | 32 | 31 |
| pole_B4 | 0 | 0 | 21 | 21 | 21 |
| pole_C3 | 0 | 1 | 2 | 3 | 3 |
| pole_B0 | 0 | 0 | 0 | 0 | 9 |
| pole_C1 | 0 | 0 | 0 | 0 | 38 |

Visibility mask (v2): 18976 2-in cells in CH01's support; a rat is hidden (h ≥ 0.8) in 8.2 % and partly hidden in 4.2 %. Hidden share by object: house_1 2.6 %, house_2 2.3 %, pole_B2 1.8 %, pole_B1 0.8 %, pole_B3 0.7 %, pole_B4 0.0 %. Figure [`visibility_mask.png`](../figures/ch01_occlusion/visibility_mask.png); pooled classes [`class_shares.png`](../figures/ch01_occlusion/class_shares.png); array `visibility_mask.npz` in the run folder.

## house_1 cohort pose (v2 fix 1)

Fitted with `calibration_qc/house_check.py`'s rigid model and fit (its functions reused read-only; file sha256 `92cea7e781a9…`) on the user's 09-04 12:00:02 house_1 edge labels of CH01 and CH02 (7 + 7 pieces: ROOF_X, ROOF_Y, BASE_Z; the number plate LABEL excluded), converted to 09-18 px with the inverse **noon** affines (CH01 held-out 1.27 px, CH02 1.74 px; not the night-only table) + the IR → colour offset; 4 free parameters (x, y, ridge angle, soil offset), house_check's start grid. Written to `cv/configs/house1_cohort_pose_2026c.json` (pointer added to `cv/cv_field/CAMERA_GEOMETRY_2026c.md` §4).

- **Centre (142.23, 123.46) in, ridge 88.5° from x, soil 45 mm below the calibration's z = 0.**
- Rays miss the rigid house by: CH01 median 10.6 mm, p90 17.7 mm (n 161); CH02 median 4.6 mm, p90 9.9 mm (n 158).
- Each camera alone (soil fixed at the joint value): CH01 (142.11, 123.58) in, 88.7°; CH02 (142.15, 123.35) in, 88.5° → spread 2.9 mm from their mean, CH01–CH02 5.9 mm.
- Soil sensitivity: soil fixed at 58 mm → centre (141.65, 123.48) in, shift 14 mm; at 93 mm → (140.03, 123.56) in, shift 56 mm (with two cameras the soil level and the centre trade along the viewing rays).
- Lid (the roof is lifted at every round): roof-only fit (8 pieces) (142.38, 123.45) in vs BASE_Z-only (6 pieces) (141.57, 123.47) in, soil fixed at the joint value: **21 mm apart**, ridge +0.05° — below the 30-mm 09-18 per-camera spread, so by the note's rule the lid offset does not matter here.
- Distance from the calibration's 09-18 post-move position (147.5, 121.7) in: **5.56 in** (the move on 09-18, "farther from its pole"); from v1's WISER-ROI placement (142.0, 114.2) in: **9.27 in**.

## Poles (v2 fix 2)

Poles labelled in CH01's 09-18 reference (A0, B0, B1, B2, B3, C0, C1) hide by **CH01's own L / R edge labels**: each edge's rays (09-18 px + IR → colour offset, rev g rays) define a plane through CH01's centre; a sample point is hidden if its ray lies between the two planes, within the labelled vertical span (the heights where the labelled rays pass the pole's horizontal distance; the grass-hidden foot is not labelled, so not included), and it is farther from the camera than the pole. The pole's distance comes from the measured line (B1–B3) or the design grid; only the front / behind decision uses it. The planes are fixed in the world (camera centre + pole edges), so the cohort hour needs no pixel correction for them. Poles CH01 did not label keep the v1 capsule.

| pole | v2 model | distance source | distance (m) | angular width | labelled span (m, at the pole) | label planarity median / max |
|---|---|---|---:|---:|---|---|
| A0 | label planes | design grid | 6.50 | 0.79° | 1.08–2.12 | 0.069° / 0.177° |
| B0 | label planes | design grid | 6.17 | 1.29° | 1.00–2.29 | 0.020° / 0.094° |
| B1 | label planes | measured | 3.11 | 2.66° | 0.40–2.43 | 0.063° / 0.233° |
| B2 | label planes | measured | 0.68 | 9.36° | 0.41–2.00 | 0.097° / 0.424° |
| B3 | label planes | measured | 3.18 | 2.46° | 0.50–1.43 | 0.048° / 0.170° |
| C0 | label planes | design grid | 7.23 | 1.22° | 1.06–2.20 | 0.039° / 0.123° |
| C1 | label planes | design grid | 4.94 | 1.26° | 1.01–1.36 | 0.008° / 0.037° |

Capsule (v1 model): A1 (design grid), A2 (design grid), A3 (design grid), A4 (design grid), B4 (design grid), C2 (design grid), C3 (design grid), C4 (design grid).

## Inputs and the rebuilt per-second table

The phase-0 per-second suspected-miss table, rebuilt with the unchanged phase-0 code (`wiser_assist_p0.prepare_boxes` + `part_c`, accepted map d (-272.85, -605.80) in, θ 0.114°, s 0.9634, L +0.0 s): 3482 suspected-miss seconds of 8925 eligible animal-seconds; the regenerated `fn_episodes.csv` is byte-identical to phase 0's: True (`fn_grid.csv`: True).

## Occluders

Camera CH01 centre (240.6, 87.6) in, 2292 mm (`RayCamera.centre`). Houses: the house check's rigid model (body box to the eave height + gable-roof prism with the 66-cm ridge and the roof overhang).

| object | position (in) | source | size / model |
|---|---|---|---|
| pole A0 | (0.0, 0.0) at the ground | design grid (field_layout.json): 1 clean heights (< 2) | CH01 L/R label planes; r 71 mm; lean 0.0° |
| pole A1 | (120.0, 0.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | cylinder (capsule); r 71 mm; lean 0.0° |
| pole A2 | (240.0, 0.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | cylinder (capsule); r 71 mm; lean 0.0° |
| pole A3 | (360.0, 0.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | cylinder (capsule); r 71 mm; lean 0.0° |
| pole A4 | (480.0, 0.0) at the ground | design grid (field_layout.json): fitted lean 23 deg > 15 (not credible) | cylinder (capsule); r 71 mm; lean 0.0° |
| pole B0 | (0.0, 120.0) at the ground | design grid (field_layout.json): 1 clean heights (< 2) | CH01 L/R label planes; r 71 mm; lean 0.0° |
| pole B1 | (131.2, 125.2) at the ground | measured (pole-check method on rev g, 01+02) | CH01 L/R label planes; r 75 mm; lean 9.5° |
| pole B2 | (242.2, 115.1) at the ground | measured (pole-check method on rev g, 01+02) | CH01 L/R label planes; r 67 mm; lean 3.6° |
| pole B3 | (357.3, 119.5) at the ground | measured (pole-check method on rev g, 01+02) | CH01 L/R label planes; r 71 mm; lean 6.4° |
| pole B4 | (480.0, 120.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | cylinder (capsule); r 71 mm; lean 0.0° |
| pole C0 | (0.0, 240.0) at the ground | design grid (field_layout.json): 1 clean heights (< 2) | CH01 L/R label planes; r 71 mm; lean 0.0° |
| pole C1 | (120.0, 240.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | CH01 L/R label planes; r 71 mm; lean 0.0° |
| pole C2 | (240.0, 240.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | cylinder (capsule); r 71 mm; lean 0.0° |
| pole C3 | (360.0, 240.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | cylinder (capsule); r 71 mm; lean 0.0° |
| pole C4 | (480.0, 240.0) at the ground | design grid (field_layout.json): 0 clean heights (< 2) | cylinder (capsule); r 71 mm; lean 0.0° |
| house_1 | (142.2, 123.5), ridge 88.5° | fitted cohort pose (house_check on the CH01 + CH02 09-04 noon labels; house1_cohort_pose_2026c.json) | 62.55 × 45.72 cm, eaves 59.0 cm, ridge 88.2 cm, soil at z -45 mm |
| house_2 | (342.4, 117.7), ridge 92.0° | calibration house check (rev g) | 62.55 × 45.72 cm, eaves 60.8 cm, ridge 87.8 cm, soil at z -93 mm |

Map check on house_2 (unchanged): its WISER ROI through the accepted map lands 7.2 in from its calibrated position — the hand-placed ROI rectangles carry errors of that order, which is why v1's house_1 was off.

Pole re-measurement (amendment 1, unchanged): the pole-check method re-run read-only on the rev g cameras; B1, B2, B3 measured (CH01 + CH02), the other 12 at the design grid; per-height triangulations in `pole_triangulation_revg.csv`; tape check at 1.05 m: B1–B2 120.9 in (tape 120 in); B2–B3 117.4 in (tape 116 in).

## Landmark checks (v2)

Median pixel distance from the user's labels to the model (flag > 20 px on checks and fit residuals; results of a flagged object carry the flag). *kind*: **check** = labels not used to build the object; **fit residual** = the labels built the object (the 09-04 house_1 labels are now the house_1 fit's data, so their row is no longer an independent check; the label-plane poles reproduce their own labels up to the edges' straightness); **reference** = a model v2 does not use for hiding; **code check** = projection sanity check.

| object | labels | model | kind | label points | median px | p90 px | flagged |
|---|---|---|---|---:|---:|---:|---|
| pole_A0 | 09-18 | CH01 L/R label planes (v2; built from these labels) | fit residual (not independent) | 56 | 3.6 | 6.3 | no |
| pole_A0 (capsule, v1 model; v2 uses it only for the distance) | 09-18 | cylinder, design grid | reference | 56 | 57.4 | 77.7 | no |
| pole_B0 | 09-18 | CH01 L/R label planes (v2; built from these labels) | fit residual (not independent) | 67 | 0.8 | 2.6 | no |
| pole_B0 (capsule, v1 model; v2 uses it only for the distance) | 09-18 | cylinder, design grid | reference | 67 | 40.6 | 76.1 | no |
| pole_B1 | 09-18 | CH01 L/R label planes (v2; built from these labels) | fit residual (not independent) | 184 | 2.4 | 5.9 | no |
| pole_B1 (capsule, v1 model; v2 uses it only for the distance) | 09-18 | cylinder, measured | reference | 184 | 3.0 | 9.5 | no |
| pole_B2 | 09-18 | CH01 L/R label planes (v2; built from these labels) | fit residual (not independent) | 245 | 3.7 | 6.4 | no |
| pole_B2 (capsule, v1 model; v2 uses it only for the distance) | 09-18 | cylinder, measured | reference | 245 | 45.5 | 119.9 | no |
| pole_B3 | 09-18 | CH01 L/R label planes (v2; built from these labels) | fit residual (not independent) | 85 | 2.1 | 3.8 | no |
| pole_B3 (capsule, v1 model; v2 uses it only for the distance) | 09-18 | cylinder, measured | reference | 85 | 3.0 | 6.6 | no |
| pole_C0 | 09-18 | CH01 L/R label planes (v2; built from these labels) | fit residual (not independent) | 44 | 1.5 | 2.8 | no |
| pole_C0 (capsule, v1 model; v2 uses it only for the distance) | 09-18 | cylinder, design grid | reference | 44 | 24.6 | 34.7 | no |
| pole_C1 | 09-18 | CH01 L/R label planes (v2; built from these labels) | fit residual (not independent) | 14 | 0.3 | 1.1 | no |
| pole_C1 (capsule, v1 model; v2 uses it only for the distance) | 09-18 | cylinder, design grid | reference | 14 | 58.2 | 71.9 | no |
| house_2 | 09-18 | house check rev g pose | check | 169 | 9.8 | 148.3 | no |
| house_1 (CH01 09-04 labels) | 09-04 cohort (noon affine -> 09-18 px) | fitted cohort pose | fit residual (labels are the fit data) | 161 | 7.6 | 13.7 | no |
| house_1 (CH02 09-04 labels) | 09-04 cohort (noon affine -> 09-18 px) | fitted cohort pose | fit residual (labels are the fit data) | 158 | 3.8 | 7.8 | no |
| house_1 WISER-ROI placement (v1 model) | 09-04 cohort (noon affine -> 09-18 px) | WISER ROI through the map | reference | 161 | 125.0 | 189.0 | no |
| house_1 (09-18 post-move pose; code check only) | 09-18 | house check rev g pose | code check | 169 | 19.5 | 27.6 | no |

Nothing is flagged in v2. The capsule rows of the label-plane poles show how far v1's cylinders were from CH01's labels (v2 keeps them only for the front / behind distance).

## Definitions

Units: paddock mm / inches (origin pole A0); z = the calibration's absolute height datum (camera centre, terrain, house soil levels). $\mathbf C$ = CH01's centre; $\mathbf p$ = an animal's paddock position (WISER through the accepted map); $g(\mathbf p)$ = local ground height (terrain).

### Rat sample points
$$ \mathbf q_{kl}=\big(\mathbf p+o_l\,\hat{\mathbf n},\ g(\mathbf p)+z_k\big),\quad z_k\in\{30,60,90\}\,\mathrm{mm},\ o_l\in\{-40,0,40\}\,\mathrm{mm} $$ **Text:** a rat's body as 9 points; $\hat{\mathbf n}$ = horizontal unit normal to the line of sight from CH01.

### Hidden share $h$
$$ h(\mathbf p)=\frac{1}{9}\sum_{k,l}\mathbb 1\big[\exists\,O:\ \mathbf q_{kl}\ \text{hidden by}\ O\big] $$ **Text:** share of the body points hidden from CH01. Range [0, 1]. *Hidden by a house*: the segment $[\mathbf C,\mathbf q]$ passes through a convex house part (Cyrus–Beck). *Hidden by a capsule pole*: segment–axis distance ≤ radius. *Hidden by a label-plane pole*: $\mathbf n_L\cdot\mathbf d\ge0\ \wedge\ \mathbf n_R\cdot\mathbf d\ge0\ \wedge\ z_\rho\in[z_{lo},z_{hi}]\ \wedge\ \lVert\mathbf d_{xy}\rVert>\rho$ with $\mathbf d=\mathbf q-\mathbf C$, $\mathbf n_{L,R}$ = the edge planes' normals (least squares of the labelled rays, oriented towards the other edge), $\rho$ = the pole's horizontal distance, $z_\rho=C_z+\rho\,d_z/\lVert\mathbf d_{xy}\rVert$ = the ray's height at the pole, $[z_{lo},z_{hi}]$ = the same for the labelled rays.

### Classes
nominal: hidden $h\ge0.8$, partly $0<h<0.8$, clear $h=0$. Robust over the nominal position and 8 positions 7 in away (v2: each clamped to $[1,479]\times[1,239]$ in): robustly hidden = hidden at all 9, robustly clear = $h=0$ at all 9. **Category**: hidden = robustly hidden; clear = robustly clear; partly = nominal $0<h<0.8$; ambiguous = otherwise. **Episode class** = the unique majority category of its seconds (ties → ambiguous). **Occluder** of a second = the object blocking the most sample points summed over the 9 positions; of an episode = the most frequent occluder of its non-clear seconds.

### house_1 fit
$$ \hat{\mathbf x}=\arg\min_{x,y,\theta,dz}\sum_{\text{label rays}}\rho_{\text{soft-}\ell_1}\big(\min_{e\in E(\text{class})}\mathrm{dist}(\text{ray},\,e(x,y,\theta,dz))\big) $$ **Text:** house_check's fit: the rigid edges $E$ of the surveyed house posed at centre $(x,y)$, ridge angle $\theta$, soil $dz$ below z = 0; each label piece is matched to the nearest allowed edge (roof labels → roof edges, BASE_Z → vertical corners). Ray miss = the 3-D distance between a label ray and its edge (mm).

### Landmark distance
$$ d_i=\min_{\mathbf s\in\pi(E)}\lVert \mathbf u_i-\mathbf s\rVert $$ **Text:** pixel distance from a densified label point $\mathbf u_i$ (every ≈ 15 px) to the projected model edge $\pi(E)$ (3-D points projected with the calibration's own inverse, verified to 0.02°); for a label-plane pole, the angle of each label ray from its plane converted to px with the local pixel scale. Median per object.

## Caveats

- Grass, other rats, the animal's posture and objects not surveyed (water dish, feeders, cables) are not modelled: they can hide a *clear* animal. One hour, one camera.
- house_1's pose rests on two cameras about 40° apart: the soil level and the centre trade along the rays (sensitivity above); the roof is the lid, set back after each round.
- Label-plane poles hide only within the labelled span; the grass-hidden pole foot is not modelled (grass hides an animal there anyway). Poles CH01 did not label stay capsules (vertical at the design grid unless measured).
- The 7-in perturbation is the WISER error scale; WISER's own error is larger in some seconds.

## Outputs

Run folder `D:/Field2026_analysis_out/2026c/cv_field_ch01_occlusion_20261006_1555`: `occluders.json`, `checks.csv`, `visibility_mask.npz`, `miss_seconds_rebuilt.csv.gz`, `pole_edges_revg.csv`, `pole_triangulation_revg.csv`, `run.json`, `run_log.txt`; **sealed**: `episodes.csv`, `seconds.csv.gz` (`SEALED_README.txt`). house_1 pose `cv/configs/house1_cohort_pose_2026c.json`. Figures `results/2026c/cv_field/figures/ch01_occlusion/`. Pointer `run_manifest_ch01_occlusion_2026c.json`.

## Rerun

```
C:/Python313/python.exe cv/cv_field/ch01_occlusion.py --house1-fit   # the house_1 pose JSON
C:/Python313/python.exe cv/cv_field/ch01_occlusion.py --run          # v2 (--v1 reproduces v1)
```
