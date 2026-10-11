# In-box SAM 3 prompt explorer, cohort 3 (CH07) — the user's notes

This folder holds the **user's** note exports from the interactive prompt explorer built by
`cv/cv_field/inbox_sam3_dino_test.py --phases gui`. It belongs to plan `implementation_plan/2026-10-11-inbox-sam3-dinov3-test.md`,
amendment 4: the exploratory prompt sweep the user asked for on 2026-10-11 ("未必不work，你做成gui我自己看一眼", "it might
work after all; make it a GUI and I'll take a look myself"). Nothing in here is made by a machine; the agent never judges
the images.

## Page

`D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320/prompt_gui/index.html`. Open it from disk; it works
offline. The data sits in `gui_data.js` and `frames/` next to it.

**Content:**
- 10 IR and 10 colour CH07 frames, the sweep frames of amendment 4.
- 10 text prompts × {whole frame, 2 × 2 tiles}.
- Per frame × prompt × variant, the top 60 SAM 3 masks by score, from the cached sweep (no new SAM 3 run). Each is drawn
  as a polygon simplified with approxPolyDP (ε 2 px at full resolution) in its own colour.
- For the tiled variant, the cross-tile duplicates are merged once over all cached masks (mask IoU ≥ 0.5, score order).
- White dots = the user's blind head clicks.

**Controls:**
- IR / colour; frame (← / →) and prompt (↑ / ↓); grid of all 10 prompts (G); whole / tiles (V);
- top-K slider (1–60) and min-score slider (log, 0.005–1);
- fill / outline; head dots; score label on hover;
- zoom (wheel) and pan (drag).

**Live counts** are mask ↔ click counts only, with the earlier rules (a mask covers a click within 15 px):
- masks shown;
- heads covered;
- heads with their own exclusive mask (the earlier test's X);
- empty masks; merged masks.

They are not a verdict.

## How to save the notes

There is one free-text note per frame × prompt. Notes are kept in the browser's localStorage (key
`inbox_sam3_prompt_gui_2026c_v1::<run folder name>`), together with the view at the time of writing (variant, top-K, min score).

1. Press **Export JSON** and **Export CSV**. The browser writes `inbox_sam3_prompt_gui_2026c_<YYYYMMDD_HHMMSS>.json` and
   `.csv` to its download folder.
2. Move both files into this folder, unchanged. Keep every export: the newest is the current state.
3. To continue elsewhere, open the page and press **Import JSON**.

## File contents

**JSON** has these fields:
- `page_version`, `run`, `exported_at`;
- `prompts`: the 10 prompt texts;
- `notes`: one object per frame × prompt with a note, with `frame_id`, `domain` (ir / colour), `prompt`, `note`, `view` and
  `updated_at`.

**CSV:** one row per note, with the same columns.
