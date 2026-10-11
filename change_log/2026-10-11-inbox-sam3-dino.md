# 2026-10-11 — In-box CH07: SAM 3 text-prompt detection, SAM 3 point-prompt masks, frozen DINOv3 identity probe

- **Plan:** [`implementation_plan/2026-10-11-inbox-sam3-dinov3-test.md`](../implementation_plan/2026-10-11-inbox-sam3-dinov3-test.md),
  approved by the user 2026-10-11.
  - Amendment 1 = the Codex review *Yolo_identity*, folded in before results.
  - Amendments 2 and 3 = implementation details and a grouping sensitivity, written by the agent before any T1–T3 result.
  - A disclosure note was added after results.
- **Report:** [`results/2026c/cv_field/reports/cv_field_inbox_sam3_dino_2026c.md`](../results/2026c/cv_field/reports/cv_field_inbox_sam3_dino_2026c.md).
  Every derived quantity is defined there as a formula and in words. The pointer is `run_manifest_inbox_sam3_dino_2026c.json`.
- **Data map:** [`cv/cv_field/DATA_MAP_c1yolo_wiser.md`](../cv/cv_field/DATA_MAP_c1yolo_wiser.md) section L.
- **Truth:** the user's blind head clicks (`before_reveal`, `first_*`) in
  `cv/configs/inbox_identity_2026c/inbox_identity_2026c_20261010_220725.csv`.
  - 284 clicks on 58 CH07 frames: 38 IR, 20 colour.
  - The composition statement says every clicked frame is complete.
- **The agent never looked at a frame or a mask.**

## What changed

- **New driver** `cv/cv_field/inbox_sam3_dino_test.py`:
  - GPU phases `data t1gpu t2gpu dino` run in the cv env.
  - Phases `score review report` run in base Python, because scipy's L-BFGS-B crashes natively in the cv env
    (0xc06d007f). The pre-registered lbfgs solver is kept.
  - `--selftest` (synthetic, 34 checks) covers: RLE cache, coverage distance, T1 matching rules, tiled merge, the join
    rule incl. missing IMU, group chains and dev split, grouped bootstrap, crops and head disc, pile size, classifiers,
    the decision rule, the review sampler, page blindness, `node --check` of the page script, and the blind-record reader.
    It passes in base Python; the cv env skips the logistic checks.
- **SAM 3 point prompts:** ultralytics 8.4.93 exposes points / labels for SAM 3 through `SAM3Predictor`, the interactive
  predictor. So the SAM 2.1 fallback was not triggered.
  - Its builder passes `compile=False`, which the ViT trunk treats as a compile mode; that fails without Triton.
  - The model is built with `build_interactive_sam3(..., compile=None)` instead.
- **New folder** `cv/configs/inbox_sam3_mask_review_2026c/` (`README.md`) for the user's review exports.
- **Run** `D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320/`. It caches the raw SAM 3 masks
  (RLE in bbox crops) and the DINOv3 embeddings. The first GPU job stopped after 8 frames when its session ended; it was
  resumed from the atomic per-frame caches, and nothing was recomputed.
- **Docs updated:** plan status + amendments 2–3 + disclosure note, `implementation_plan/README.md`, `CLAUDE.md` (cv_field
  map), `cv/cv_field/HANDOFF.md`, `cv/cv_field/DATA_MAP_c1yolo_wiser.md` section L. `change_log/README.md` was left to the
  coordinator.

## Results

### Groups (amendment 1 item 2)

- **Primary rule:** no consecutive pair met the join rule (roster unchanged + every roster animal IMU-still ≥ 90 % of the
  seconds), so there are 20 groups: dev G01–G05, test G06–G20.
- **Sensitivity `group_alt` (amendment 3):** animals without any ok IMU second are not counted. It joins 09-11
  14:09 → 14:17 → 14:43 (SF12 has no IMU that afternoon), giving 18 groups. No conclusion changes.

### T1 — SAM 3 text prompt (primary = the dev-chosen prompt on test IR)

- **Dev choice:** P4 "hooded rat", τ = 0.01, which is the grid floor and the cache's score floor; dev IR F1 0.25.
- **Test IR** (28 frames, 138 heads):
  - head-point exclusivity X = **8.0 % [2.1, 16.7]**; F1 0.11 [0.04, 0.19];
  - empty-mask rate 82 %; count error −1.4 masks per frame.
- **Other prompts at their own dev τ** (descriptive): P1 "rat" X 50.7 % but 906 masks for 138 heads (F1 0.14); P2 "Long
  Evans rat" X 4.3 %; P3 "rat with a colorful rectangular implant on its head" X 29.0 % (F1 0.23).
- **Tiled sensitivity:** X 48.6 % [40.0, 57.4] with about 10 surplus masks per frame.
- **Colour frames** (separate): X 5.6 %.
- **Reading:** zero-shot text prompts do not find the in-box rats on whole IR frames.

### T2 — SAM 3 point prompt from the head click (primary = positive point, test IR, 138 heads)

- **Positive point:** exclusivity **95.7 % [90.3, 100]**, merge 4.3 %, own head never missed.
- **With negative points at the other heads:** 99.3 % [97.8, 100]. This variant is partly self-validating.
- **Size:** the boxes are numerically head-sized, with median long side 189 px (p95 309 px). An 8-in body is about 600 px
  at the house-fit scale.
- **Reading:** whether the masks are whole single rats waits for the user's blind mask review.

### T3 — frozen DINOv3 head crop, IR (amended decision rule)

| | accuracy [95 % CI] | best control | Δ vs best control [CI] | carries identity | ≥ 15 pp established |
|---|---|---|---|---|---|
| **Primary**: CLS + logistic, 4-in crop, leave-one-group-out (187 clicks, 20 groups) | 50.3 % [42.1, 58.0] | head-masked 26.7 % | +23.5 pp [15.6, 31.1] | **YES** | **YES** (lower bound 15.6) |
| Cross-day: leave-one-day-out, 09-11 held out (68 clicks) | 30.9 % [17.1, 45.6] | head-masked 19.1 % | +11.8 pp [−4.3, 25.7] | **NO** | no |
| `group_alt` sensitivity (18 groups) | 46.5 % [38.9, 53.8] | head-masked 24.1 % | +22.5 pp [15.0, 31.0] | YES | YES (at the edge) |

The other configurations are descriptive:
- mean-patch + logistic: 60.4 %;
- nearest centroid: 36–43 %;
- 16-in body crops: 25–31 %, no identity;
- shuffled labels: 18.1 % (range 11–26 %);
- without the duplicate-label clicks: 54.6 %;
- colour crops, CLS + logistic LOGO: 60.0 %.

**Reading:** an identity signal in IR head crops within the click days; not shown across days.

### Blind mask review page (amendment 1 item 1) — for the user

- **Page:** `D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320/mask_review/index.html`.
- **Sample:** 40 masks from test IR frames: 14 T1, 13 T2 positive, 13 T2 negative, stratified by pile size.
  - Method, score and head point are hidden; the items are shuffled as M01–M40.
  - Choices: one whole rat / part of a rat / two or more rats / not a rat, plus notes.
- **Saving:** localStorage, with Export CSV / JSON to `cv/configs/inbox_sam3_mask_review_2026c/`.
- **Key:** `mask_key.csv` in the run folder, not linked from the page.
- **Headless Chrome check: PASS.** It covered 40 cards, 80 / 80 images, persistence across a reload, export of 40 rows,
  no method or score words and no network URL. Not scored.

## Definitions (headline quantities; full set in the report)

- **Coverage** $c_{ij}=\mathbb 1[d_{ij}\le 15\,\text{px}]$, where $d_{ij}$ = 0 if the clicked pixel is in mask $j$,
  else the distance to the nearest mask-pixel centre. A mask covers a head point.
- **Head-point exclusivity (T1)**
  $X=\#\{i: i=k(a(i)),\ \sum_{i'}c_{i'a(i)}=1\}/\sum_f n_f$. $a(i)$ = the covering mask with the highest score (then the
  smaller area); $k(j)$ = the head a mask keeps (the nearest). This is the share of head points that have their own mask
  covering no other head point. Range 0–1.
- **$F_1$ (T1, dev selection)** $=2TP/(\sum_f|K_\tau|+\sum_f n_f)$, where TP = masks that keep a head point and
  $K_\tau$ = the masks with score ≥ τ.
- **T2 exclusivity** = the share of heads whose point-prompted mask covers its own head point and no other.
- **T3 accuracy** $=\frac1N\sum_n\mathbb 1[\hat y_n=y_n]$, with click $n$'s group (LOGO) or day (LODO) held out.
  Chance = 1/5.
- **T3 decision:** $\Delta_{ch}=\text{acc}-0.2$ and $\Delta_{ct}=\text{acc}-\text{acc}_{best}$.
  - Carries identity if both are ≥ 0.15 and both paired grouped-bootstrap CIs (2 000 draws of groups) exclude 0.
  - Established if both CI lower bounds are ≥ 0.15.
- **Still-episode join** = a constant WISER house_2 roster over [last frame of segment $i$, colour frame of $i+1$], with
  every roster animal ok and still in ≥ 90 % of those seconds.

## Not verified

- The usable-box claim for T1 / T2 is limited to head-point exclusivity until the user's mask review is in.
- T3 rests on one house, one labeller, 20 groups and one held-out day.
- The logistic C chosen by inner CV varies 0.01–100 across folds.
- The low end of the T1 τ grid was set after an API probe (disclosure note in the plan).

## Addendum 2026-10-11 — exploratory prompt sweep (plan amendment 4; user request, after results)

**Exploratory and descriptive only:** no gate, no choice, no claim beyond these frames, and no change to T1–T3.

- **Code:** `inbox_sam3_dino_test.py` gained the phases `sweep_gpu` (cv env) and `sweep` (base Python).
- **Frames:** 10 daytime IR frames (`ir_p06`, ≥ 3 blind heads), 5 per day on 09-10 and 09-11, one per still episode (rule
  fixed before running), plus their 10 colour mid-frames as a separate block:
  - 09-10: 07:14, 12:27, 14:02, 14:32, 17:59;
  - 09-11: 09:28, 09:54, 14:17, 14:50, 18:28.
- **Prompts:** 10 (3 reused from the T1 cache, 7 new). Whole frame and 2 × 2 tiles; T1 matching against the blind
  clicks at τ = 0.01 and 0.25.
- **Determinism:** re-running "rat" on one frame reproduced all 100 cached masks pixel-identically.
- **IR, whole frame, τ = 0.01** (49 heads):
  - "black striped rat" and "black and white rat" give X 88 %;
  - "rat" 78 %; "rat with a black head and a white body" 73 %;
  - but these come with 482–1 433 masks for 49 heads, mostly empty;
  - "Long Evans rat" 8 %, "hooded rat" 24 %, "sleeping rats" 6 %.
- **IR, τ = 0.25:** every prompt misses ≥ 46 of 49 heads, except "pile of rats" (9 missed, 14 merged masks).
- **Colour** gives the same picture (separate tables in the report).
- **Page for the user:** `D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320/prompt_sweep/index.html`.
  It has mask outlines per prompt, click dots and a τ switch; the headless check passed (20 sections, 420 / 420 images at
  both τ).
- **Tables:** `prompt_sweep/sweep_summary.csv` and `sweep_frame_metrics.csv`; the report has a section "Exploratory prompt
  sweep".
- **The agent did not look at the panels.**

## Addendum 2026-10-11 — interactive prompt explorer (user request: "未必不work，你做成gui我自己看一眼")

The user wanted to judge the prompt sweep themselves ("it might work after all; make it a GUI and I'll take a look
myself"), so the sweep now has an interactive explorer. It is descriptive only and changes no result.

- **Code:** `inbox_sam3_dino_test.py --phases gui`, run in base Python from the cached sweep masks. **No SAM 3 run.**
- **Page:** `D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320/prompt_gui/index.html`. It is
  self-contained and works from file://; the data sits in `gui_data.js`, with no fetch and no network.
- **Content:** the 10 IR + 10 colour sweep frames, downscaled to 1600 × 1200.
  - Per frame × prompt × variant, the top 60 masks by score as polygons (approxPolyDP, ε 2 px at full resolution), each
    with its score.
  - Tiled = cross-tile clusters formed once over all cached masks. This can differ slightly from the per-τ merge of the
    report's tiled counts.
- **Controls:** IR / colour, frame ← / →, prompt ↑ / ↓, grid of all 10 prompts, whole / tiles, top-K slider 1–60, log
  min-score slider 0.005–1, fill / outline, head dots, hover score, zoom and pan.
- **Live counts:** masks shown, heads covered, heads with their own exclusive mask, empty, merged (the T1 rules).
- **Notes:** one per frame × prompt, in localStorage, with Export CSV / JSON to `cv/configs/inbox_sam3_prompt_gui_2026c/`
  (new folder with a `README.md`).
- **Data size:** `gui_data.js` 13.1 MB (16 750 masks, 1.27 M polygon points), frames 7.7 MB, `index.html` 17 kB.
- **Headless Chrome check: PASS** (`prompt_gui/page_check.json`):
  - the page loads;
  - ← / ↑ / V switch frame, prompt and variant;
  - top-K 60 → 5 drawn masks; the min-score slider at 0.20 → 11 of 60;
  - the grid shows 10 panels;
  - a note survives a reload;
  - the live counts equal the Python sweep counts in 200 / 200 frame × prompt cases (whole frame, min score 0.25);
  - no network URL.
