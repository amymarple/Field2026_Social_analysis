# In-box SAM 3 "rat" pre-label edit pilot (part B, dev) — the user's labels

This folder holds the **user's** exports from the pre-label edit page built by
`cv/cv_field/inbox_prelabel_edit.py build`. It belongs to plan `implementation_plan/2026-10-12-inbox-sam3-rat-prelabel.md`,
part B, with amendment C2's record of the proposed vs final box. Nothing in here is made by a machine; the agent never
judges the images.

## Page

`D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320/prelabel_edit/index.html`. Open it from disk; it
works offline. Its data sit in `pl_data.js` and `frames/` next to it.

**Frames:** the 58 CH07 frames of the SAM 3 test (38 IR, 20 colour). All are dev, because they were seen before. The work
order is IR first, then colour, shuffled within each domain (seed 20261012).

**Arms,** stratified by domain × the frame's largest pile size:
- PRELABEL, 39 frames. Every blind head click is a numbered dot.
  - The page offers the highest-score SAM 3 "rat" mask within 15 px of the dot (cyan outline, dashed yellow box).
  - **A** accepts it. **N** shows the next candidate, then "none usable".
  - **M** / **P** flag the shown candidate as merged / partial. **B** draws a box by hand.
  - Green box edges can be dragged.
- SCRATCH, 19 frames: dots only; drag one box per rat.
- Both arms:
  - **R** adds a rat whose head is hidden (click its body). On a PRELABEL frame the masks covering that point are offered.
  - **X** deletes a dot that is not a rat. **U** undoes.
  - **Enter / →** goes to the next rat, then the next frame.
- **Show all (S):** every "rat" mask of the frame. Clicking a mask marks it garbage → fragment → clear. Its time is kept
  apart from the edit time.
- **Redo this frame** keeps the earlier labels as a pass. The first completed pass is the main one; later passes feed only
  the repeat check.

**Saving and timing:**
- Labels are autosaved in this browser's localStorage (key `inbox_sam3_prelabel_edit_2026c_v1::<run folder name>`), so you
  can stop and resume at any time.
- The active clock per frame pauses when the tab is hidden or after 45 s without input.

## How to save

1. Press **Export JSON** and **Export CSV**. The browser writes `inbox_sam3_prelabel_edit_2026c_<YYYYMMDD_HHMMSS>.json`
   and `.csv` to its download folder.
2. Move both files into this folder, unchanged. Keep every export: the newest is the current state.
3. To continue elsewhere, open the page and press **Import JSON**.

## File contents

**JSON** has these fields:
- `page_version`, `run`, `plan`, `seed`, `exported_at`, `started_at`;
- `definitions` (the plan's terms), `definition_note` (your "my definition changes" text), `idle_ms`;
- `frames`: one object per frame (`frame_id`, `domain`, `arm`, `pile_bin`, `order`, `active_s`, `showall_s`, `visited`,
  `completed`, `rats`, `showall_marks`, `passes`).
- Each rat:
  - `id`, `num`, `origin` (click / added), `click_id`, `u`, `v` (head point);
  - `cand` (candidate ids in score order) and `cand_cache_index` / `cand_scores`;
  - `prop`, the proposed box: the box of the first offered candidate;
  - `box`, the final box; `source` (cand / manual) and `rank`;
  - `mask` / `mask_cache_index` / `mask_score`;
  - `cand_flags` (per rank: merged / partial), `edge_moves`, `next_presses`, `deleted`.
- `events`: the time-stamped log, including accept, next, flag, manual_box, edge_move (from / to), add_rat, delete_dot,
  undo, show_all, showall_mark, frame_open / frame_done and redo_frame.

**CSV:** one row per rat and pass, with the boxes, the proposed box, the flags, the edit counts and the frame times.

**Coordinates:** full-resolution pixels of the 2560 × 1920 frame, origin top-left; box = [x0, y0, x1, y1].

## What uses it

After an export:

```
python cv/cv_field/inbox_prelabel_edit.py summarize --export cv/configs/inbox_sam3_prelabel_edit_2026c/<file>.json
```

It writes the section "B — pre-label edit pilot (dev)" of `results/2026c/cv_field/reports/cv_field_inbox_sam3_dino_2026c.md`.
The section holds usable@1 and usable@any; the merged, partial and manual-box rates; seconds per rat in PRELABEL vs
SCRATCH; the C2 quality from your own corrections; and the repeat check. All of it is split by pile size and domain.

## v2 page — implant box + rat box (plan amendments B1 / B1a, 2026-10-12) — use this one

After a first look at v1, the user changed the labels per rat.

**Labels per rat:**
- the **head point**: your click, kept as the keypoint;
- an **implant box**: the implant only, which carries the IR marks;
- a **rat box**: head + body, without the tail, visible parts only.

**Page:** `D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320/prelabel_edit_v2/index.html`. It has the
same frames, arms (39 PRELABEL / 19 SCRATCH) and order as v1, and its own storage key
(`inbox_sam3_prelabel_edit_2026c_v2::<run>`). v1 progress is ignored, and v1's page and files are kept unchanged.

**Flow per rat:** the implant box, Enter, the rat box, Enter.
- **Implant box:** candidates are the masks within 15 px of the head dot (cyan), as in v1.
  - **H** = implant hidden: no implant box for this rat.
- **Rat box:** click on the rat's body first. The masks containing that point (or within 15 px) are offered (pink).
  - No rat-box candidate is shown before the click; a new click replaces the candidate list.
- **Keys on both boxes:**
  - A accept (the box = the mask bbox, no padding) · N next candidate · F fit back to the mask · B draw by hand · drag
    edges to adjust;
  - M / P (merged / partial) apply to the rat box only;
  - Tab switches between implant and rat; ← goes back.
- **SCRATCH frames:** drag both boxes by hand; H applies there too.
- **Added rats:** R places a rat; its click is also the first body click, and its implant starts hidden (you can still
  draw one).
- **Timing:** a clock per frame, plus a time slice for the active box only.

**Exports:** `v2_inbox_sam3_prelabel_edit_2026c_<YYYYMMDD_HHMMSS>.json` / `.csv`, into this folder.
- **JSON:** as in v1, but each rat has `implant` and `rat` objects. Each object holds `cand`, `k`, `prop` (the first
  candidate's bbox; for the rat box, of the latest body click), `box`, `source`, `rank`, `mask`, `cand_flags`,
  `edge_moves`, `next_presses`, `time_ms`, `hidden` (implant), and `click` / `clicks` (rat-box body clicks).
- **CSV:** one row per rat × object × pass.

**Summary:** `python cv/cv_field/inbox_prelabel_edit.py summarize --export cv/configs/inbox_sam3_prelabel_edit_2026c/v2_<file>.json`
writes the per-object B section of the SAM 3 report. A v2 summary takes precedence over a v1 one.
