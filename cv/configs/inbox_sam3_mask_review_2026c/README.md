# In-box SAM 3 mask review, cohort 3 (CH07) — the user's blind judgments

This folder holds the **user's** exports from the blind mask review page built by `cv/cv_field/inbox_sam3_dino_test.py`
(plan `implementation_plan/2026-10-11-inbox-sam3-dinov3-test.md`, amendment 1 item 1). Nothing in here is made by a
machine. The agent never judges the masks.

## What is being judged

The page shows 40 masks that SAM 3 made on test-group IR frames of the in-box camera CH07 (house_2).
- **Methods:** the text-prompt detector (T1, the dev-chosen prompt and threshold) and the head-point prompts (T2, with
  and without negative points at the other heads).
- **Strata:** the masks are stratified by pile size.
- **Blinding:** the method, the score and the head point are hidden; the items are shuffled and named M01…M40.

For each mask, the user picks what the tinted region is:
- `one_whole_rat`: one whole rat;
- `part_of_a_rat`: part of a rat, e.g. only the head or half the body;
- `two_or_more_rats`: two or more rats;
- `not_a_rat`: not a rat.

Optional notes can be added. These judgments decide whether SAM 3 gives usable single-rat masks / boxes. Until they are
in, the T1 / T2 results are limited to head-point exclusivity.

## Page

`D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_<ts>/mask_review/index.html`
- **Which run:** the current one is named in `results/2026c/cv_field/reports/run_manifest_inbox_sam3_dino_2026c.json`,
  key `mask_review_page`.
- **Use:** open it from disk in a browser; it works offline.
- **Storage:** the answers are kept in that browser's localStorage (key `inbox_sam3_mask_review_2026c_v1::<run folder
  name>`). Export them to keep them.

## How to save

1. On the page, press **Export JSON** and **Export CSV**. The browser writes `inbox_sam3_mask_review_2026c_<YYYYMMDD_HHMMSS>.json`
   and `.csv` to its download folder.
2. Move both files into this folder, unchanged. Keep every export: the newest is the current state.
3. To continue in another browser, open the page and press **Import JSON** with the newest export.

## File contents

**JSON** has these fields:
- `page_version`, `run` (the run folder name), `exported_at`, `n_items`;
- `choices`: the four options, as [value, label];
- `judgments`: one object per item, with `item_id`, `choice` (empty if not judged), `choice_label`, `note` and
  `judged_at`.

**CSV:** one row per item, with the same columns as `judgments`.

**Key:** the item → method / prompt / threshold / score / frame / head key is `mask_key.csv` in the run folder. The page
does not link to it. Scoring joins the export to that key by `item_id`.
