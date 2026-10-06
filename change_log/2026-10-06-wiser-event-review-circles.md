# WISER event review GUI v2: WISER circles drawn on the clips (static start circle blind, moving circle after the first answer), cohort 2026c — 2026-10-06

- **Request (user, 2026-10-06):** "先用wiser把老鼠圈出来这样我好看" — circle the rat with WISER so the clips are easier to judge.
- **Plan:** [`implementation_plan/2026-10-06-wiser-event-review-circles.md`](../implementation_plan/2026-10-06-wiser-event-review-circles.md)
  (committed 97bf06f before any result) + its **Amendment 1** (implementation choices, written before any circle verdict
  existed). It is a viewing-aid change to Part 2 of
  [`2026-10-05-wiser-i1-return-test-and-video-review.md`](../implementation_plan/2026-10-05-wiser-i1-return-test-and-video-review.md);
  there is no new test. GUI v1 ([change log](2026-10-05-wiser-event-review.md)) is untouched.
- **Bulk (off-repo):** `D:\Field2026_analysis_out\2026c\wiser_event_review_20261006_1637\`
  - `index.html`: the review page.
  - `clips/`: 80 blind clips, each with the static start circle.
  - `clips_reveal/`: 80 reveal clips with the moving WISER circle.
  - `panels/`, `projection_coverage.csv`, `circles_summary.json`, `events.json`, `event_summary.csv`, `selection.csv`.
  - `overlay_ass/`, `overlay_ass_reveal/`, `_fonts/`, `README.md` (with the coverage table and checks), `log.txt`.
  - Size: 12 GB in total (5.6 GB per clip set). Rendering took 30 min, h264_nvenc, with no failures or glyph warnings.
- The agent never opened a clip frame or a rendered image. Every circle comes from WISER plus the projection only; the
  only pixel checks were numeric checks on synthetic self-test frames.

## What changed

- `wiser/scripts/make_wiser_event_review.py`:
  - New flags: `--circles` (GUI v2) and `--map-run` (default: the accepted p0 run
    `cv_field_wiser_assist_p0_20261005_2211`).
  - New code: `CamProjector`, `CircleCtx`, `load_circle_ctx` / `import_p0`, `event_circles`, `write_circle_overlays`
    (ASS `\p3` vector rings), `render_pair` / `ffmpeg_cmd_pair` (one decode, two outputs), `circles_payload`,
    `coverage_rows`, `circle_summary` / `write_circle_readme`.
  - The page is data-driven: second question, map flag, reveal-clip swap, `revealed` status, extra export columns.
  - Self-test extended (`selftest_circles`, plus a node UI-flow test over a DOM stub).
  - **Without `--circles` the driver is GUI v1.** Rebuilt on all 80 events with `--no-clips`, every `overlay_ass/*.ass`,
    `selection.csv` and `events.json` is identical to `wiser_event_review_20261005_2236`. Each v1 blind overlay is also
    an exact byte prefix of the v2 blind overlay. The page template carries the v2 code paths, but they stay inactive
    without `DATA.circles` (the self-test checks that v1 export columns are unchanged).
- Imported unchanged:
  - `cv/cv_field/wiser_assist_p0.py`: `Map`, `Params`, `Support`, `invert_mapper`, `Tracks`.
  - `cv/cv_field/frame_correction.py`: `Corrections("2026c").to_paddock`.
  - The calibration loader (`paddock_map` through `landmark_guides.calib_dir()`).
  - `cv/` is put on `sys.path` only while these import or load.
- [`wiser/configs/wiser_event_review_2026c/README.md`](../wiser/configs/wiser_event_review_2026c/README.md): GUI v2 and
  the new export fields `circle_verdict`, `circle_at`, `map_flag`, `circle_available`, `start_circle_available`,
  `reveal_clip`.
- Plan: Amendment 1 appended.

## Method

- **Same 80 events, W ids and order** (seed 20261005 / order seed 20261006); same clips, cameras by zone, banner and
  panels as v1.
- **WISER → paddock:** the accepted similarity map of WISER-assisted YOLO P0
  ($d = (-272.85, -605.80)$ in, $\theta = 0.114°$, $s = 0.9634$, lag 0 s). It was accepted on **one hour of CH01
  (09-06 21–22 h; test median residual 4.39 in)**. Other nights, CH02 and CH06 are extrapolations. The caveat appears on
  the page in both phases, in the help, in the run README and in the reveal clip's legend.
- **Paddock → pixel:** Newton inverse (`invert_mapper`) of `to_paddock(cam, t, uv, z_mm=60)` at each target's whole
  second. It starts from the nearest mapped 40-px grid centre of p0's `Support`, built at the event onset.
  - The 14-in ring is 48 paddock points, each inverted separately.
  - Cameras `to_paddock` refuses get no circle. These are CH05 (house_1 relocated 09-18, so its correction targets a
    09-04 frame) and the in-box CH07 / CH08 (uncalibrated). The clip says "no projection — use the IR mark" and names
    the reason.
- **Blind clip:** v1's overlay plus a dashed white circle at the start position $P_0$ (I1: the audit reference; I2: the V3
  median over the first second of the window). It is projected once, at the onset, and labelled "start". The blind
  overlay stays free of WISER, IMU and answer words (self-test).
- **Reveal clip** (loaded at the same time position after the first verdict is saved):
  - the start circle;
  - a solid yellow circle for V3 at each 0.25-s step centre, labelled "WISER";
  - a red dot for the raw fix;
  - the legend and the caveat;
  - per-step notes where the circle is missing ("outside this camera's mapped ground", "WISER has no fix").
  - Second question: "Does the WISER circle stay on the rat?" with keys 7 / 8 / 9 → `circle_verdict`. The "start circle
    off" tick (m) → `map_flag`.
- Flagged corrections (`night`: 16 event-cameras) are drawn and named in the clip. Day frames (17 events, 25
  event-cameras) use the nearest night correction and are flagged in the clip as "outside the corrected night hours"
  (Amendment 1.2–1.3).

## Results (projection only — no review has been done)

**68 of 80 events have a circle on at least one camera** (59 have a start circle, 68 a moving circle). In 30 of the 54
open-field events both panoramas carry one.

| camera type | event-cameras | projectable | with start circle | with any moving circle | median share of the clip's steps with a circle | events with a circle on this type |
|---|---:|---:|---:|---:|---:|---:|
| panorama (CH01 + CH02) | 108 | 108 | 61 (CH01 32, CH02 29) | 78 | 0.91 | 48 of 54 |
| top-down (CH06; CH05 refused) | 26 | 20 | 20 | 20 | 1.00 | 20 of 26 |
| in-box (CH07 / CH08) | 26 | 0 | 0 | 0 | — | 0 of 26 |

Over all projectable event-cameras, WISER was located in every 0.25-s step (18,860 steps) and a circle was drawn in
12,558 of them (67 %).

**Events without any circle (12):**

- house_1: W17, W24, W56, W57, W59, W60. CH08 is in-box and uncalibrated; CH05 is refused by `to_paddock`.
- Open field: W02, W04, W27, W30, W33, W51. Here the mapped WISER position lies at a paddock corner, outside both
  panoramas' mapped ground: median paddock (13, −6), (−11, 3), (−8, −5) and (−23, −17) in near pole A0, and (472, 6)
  and (475, 10) in at the far +x corner. All six are I2 events. Several mapped medians fall just outside the 480 × 240
  frame, which reflects the map's extrapolation or WISER at the corner.

**Checks:**

- **Round trip pixel → paddock → pixel** on a 120-px grid at each event's onset (128 projected event-cameras, 80,886
  points):
  - median of the medians 0.025 px; **outside the pano seam band, max 0.25 px (all ≤ 1 px)**;
  - 543 points over 1 px, **all inside the seam band** |u − 3840| < 150 px. There the calibration maps two pixels to one
    ground point, so the round trip can return the twin pixel (worst 136 px; paddock error < 1 in by construction);
  - lowest converged share 0.9956.
- **Inverse convergence** (targets inside a camera's mapped ground): 619,769 of 620,877; per clip-camera median 1.00.
  The one outlier is W46 CH02 at 0.00: its 30 in-support targets were edge ring or raw-dot points while the centre was out of
  view. The largest round-trip error of a drawn point is 0.86 in.
- 82 of the 12,558 drawn steps put the circle centre in the seam band.
- A midpoint-consistency test over all consecutive moving circles of the open-field events found no flip between the
  seam's two pixel branches.
- The median share of ring points drawn is 0.98 (p10 0.74); circles near the support edge are partial.
- **Self-test** (`--selftest`, all PASS), v2 part:
  - synthetic nonlinear camera + similarity map: the inverse recovers known pixels to < 0.05 px; ring points map back
    14.00 in from the centre; round trip ≤ 1 px;
  - start / moving centres land on the track's paddock position (< 0.1 in);
  - static / moving split: one dashed start circle in the blind file, no moving circle or dot there; one moving circle
    per drawn step in the reveal file;
  - the no-projection branch (note on screen, no drawing);
  - a synthetic render through `render_pair`, checked numerically: a source marker lands where the upright → clip
    mapping predicts (0.1 px); the white dashed ring and the yellow moving ring sit at their computed pixels; the blind
    clip is empty at the moving-ring pixels;
  - page logic in node: the second question opens only after the reveal; `revealed` until answered; the `no_circle`
    branch; export fields;
  - a UI flow over a DOM stub: Enter swaps to `clips_reveal/` and waits for the circle answer; the next event loads its
    blind clip; the v1 page keeps the blind clip.

## Caveats

- The circles inherit the map's validity: one CH01 hour; CH02, CH06 and every other night are extrapolated. A start
  circle that misses the rat at the onset indicates a map error for that clip, not a WISER error. `map_flag` records it,
  and those clips should be excluded before `circle_verdict` is read as a statement about WISER.
- Day-frame circles use a night correction and can be tens of pixels off (CAMERA_GEOMETRY_2026c.md: up to ~30 px on CH02
  at noon). They are flagged in the clip.
- `circle_verdict` is a post-reveal judgement and is never the return test's ground truth; `verdict_blind` stays that.
- house_1 events and corner events have no circle. Their review is unchanged from v1 (IR mark).

## Definitions

Units: WISER frame and paddock in **inches** (the WISER frame has an unverified origin; the paddock origin is pole A0,
480 × 240 in); pixels are full-resolution **upright** pixels (pano 7680 × 2160, transpose=2 of the stored frame) unless
noted. $t$ = field-PC time; $\tau^\ast$ = per-animal WISER latency (0.10–0.20 s).

### Aligned WISER position ($\mathbf w(t)$)
$$\mathbf w(t) = \mathbf w_i + \frac{t - t_i}{t_{i+1} - t_i}(\mathbf w_{i+1} - \mathbf w_i), \quad t_i \le t < t_{i+1},\ t_{i+1} - t_i \le 5\ \text{s}$$
where $t_i = t^{\text{WISER}}_i - \tau^\ast$ are the aligned times of the unmasked V3 rows and $\mathbf w_i$ their V3 positions.
**Text:** where WISER (V3 track) puts the animal at time $t$, in inches. The step is "not located" if the bracketing
rows are more than 5 s apart (p0's `Tracks` rule).

### WISER → paddock map ($T$)
$$T(\mathbf w) = s\,R(\theta)(\mathbf w - \mathbf c) + \mathbf c + \mathbf d$$
with $s = 0.9634$, $\theta = 0.114°$, $\mathbf c = (501.68, 761.10)$, $\mathbf d = (-272.85, -605.80)$ in, lag 0 s.
**Text:** the accepted similarity from WISER inches to paddock inches, fitted on CH01 09-06 21–22 h (test median
residual 4.39 in). Outside that hour it is an extrapolation.

### Projected pixel ($\hat{\mathbf u}$)
$$\hat{\mathbf u} = \arg\{\mathbf u : F_{c,\lfloor t \rceil}(\mathbf u) = \mathbf P\}\ \text{by Newton from}\ \mathbf u_0 = \arg\min_{\mathbf g \in G_c}\lVert F_c(\mathbf g) - \mathbf P\rVert, \quad \text{kept iff}\ \lVert F_{c,\lfloor t \rceil}(\hat{\mathbf u}) - \mathbf P\rVert \le 1\ \text{in}$$
where $F_{c,t}$ = `Corrections("2026c").to_paddock(c, t, ·, z_mm=60)` (cohort px → 09-18 px → 09-24 calibration, NaN
outside the verified support), $\lfloor t \rceil$ = the step's whole second, $G_c$ = the mapped 40-px grid centres of
p0's `Support` at the onset, $\mathbf P$ = the paddock target, and the Jacobian is 1-px finite differences.
**Text:** the upright pixel at which camera $c$ sees ground point $\mathbf P$ at a height of 60 mm (a rat's back).

### Circle ($\mathcal C$)
$$\mathcal C = \{\hat{\mathbf u}(\mathbf P + 14(\cos\phi_k, \sin\phi_k))\}_{k=0}^{47}, \quad \phi_k = 2\pi k / 48,\ \mathbf P = T(\mathbf w)$$
**Text:** the 14-in ring around the WISER position as seen by the camera, with each of the 48 points inverted
separately. It is drawn only if its centre $\hat{\mathbf u}(\mathbf P)$ exists. A segment is drawn only if both ends
exist and it is ≤ 3× the median segment length. Start circle: $\mathbf w = P_0$, projected at the onset, dashed. Moving
circle: $\mathbf w(t_k)$ at step centre $t_k = t_{\text{lo}} + (k + \tfrac12)\,0.25$ s, solid.

### Raw dot
$$\mathbf r_k = T(\mathbf x^{\text{raw}}_{j^\ast}),\quad j^\ast = \arg\min_j |t_j - t_k|\ \text{subject to}\ |t_j - t_k| \le 0.5\ \text{s}$$
**Text:** the raw WISER fix nearest the step centre, shown as a dot. There is no dot when no unmasked fix lies within
± 0.5 s.

### Share of steps with a circle ($S_c$)
$$S_c = \frac{\#\{k : \hat{\mathbf u}(T(\mathbf w(t_k)))\ \text{exists}\}}{K}$$
where $K$ = the clip's 0.25-s steps. **Text:** the fraction of the clip during which camera $c$ shows the moving circle.
Range $[0, 1]$. `share_circle_of_located` divides by the located steps instead.

### Inverse convergence rate
$$\rho = \frac{\#\{\text{targets with}\ \hat{\mathbf u}\ \text{kept}\}}{\#\{\text{targets inside the support raster}\}}$$
over the centre, ring and raw-dot targets of all steps plus the start circle. **Text:** how often Newton succeeds where a
solution should exist. Range $[0, 1]$.

### Round-trip error ($e_{\text{rt}}$)
$$e_{\text{rt}}(\mathbf g) = \lVert \hat{\mathbf u}(F_c(\mathbf g)) - \mathbf g\rVert, \quad \mathbf g \in \{(17 + 120i,\ 11 + 120j)\} \cap \text{support}$$
**Text:** the pixel error of forward-then-inverse on a grid at the onset, in px. Criterion: ≤ 1 px outside the pano seam
band.

### Pano seam band (threshold)
Value $|u - 3840| < 150$ px on CH01 / CH02. In the dry run every round-trip miss lay within 137 px of the seam.
**Text:** the stitch overlap, where two pixels map to one ground point (`paddock_map.RayCamera`). There the inverse may
return either pixel.

### Day frame (flag)
$$\text{day} = \big(|\mathcal U| = 1\big) \wedge \big(|t - t_{\mathcal U}| > 30\ \text{min}\big)$$
where $\mathcal U$ is the set of correction samples `frame_correction` used at $t$. **Text:** the frame lies more than
30 min outside its night's sampled correction span (21:00 → 04:20), so it uses the nearest night sample. The flag is
shown in the clip.
