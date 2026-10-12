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

## v2.1 (plan amendment B2, 2026-10-12) — the same page, updated in place

Many rats come as several SAM 3 masks, so v2.1 lets you build one box from several of them.
- **J** joins the shown candidate as a piece; the box becomes the union of all pieces. To add the next piece, click another
  part → N → J.
- **U** undoes the last step, **F** refits the box to the union, and **A** replaces the pieces with one mask.

**Same page, same progress:**
- The page path and the storage key are unchanged, so v2 progress is kept: new fields are added when an old state loads.
- The v2.0 files are kept as `*.v2_0.bak` next to the page.

**Export changes** (still prefix `v2_`):
- `page_version` is `inbox_sam3_prelabel_edit_2026c_v2.1`, with `schema` "2.1".
- Each object adds:
  - `pieces` ({mask, rank, click} + `mask_cache_index` / `mask_score`) and `n_pieces`;
  - `union_box`: the union box before any edge drag;
  - `obj_flags`: M / P on a joined box;
  - `prop_rule`.
- `source` is cand / joined / manual. The proposed box is the first candidate of the first click (`prop_rule` first_click;
  `latest_click_v2.0` for rat boxes made in v2.0 with more than one body click).
- The CSV adds `n_pieces`, `pieces_cache_index`, `union_*` and `prop_rule`.

## v2.3 (2026-10-12) — the same page, updated in place: two modes, rat switching

v2.2 (UX fixes: a click switched to the rat box, banner, toasts, legend) is replaced by two explicit modes. The page path,
the storage key and your progress are unchanged; the v2.2 files are kept as `*.v2_2.bak`.

**Two modes, sticky:**
- Buttons above the image: **① 植入体 IMPLANT** (orange) and **② 整鼠 RAT** (green); keys **1** / **2**; **Tab** toggles.
- The mode changes only through these. Enter, ←, a new rat and a new frame keep it.
- In IMPLANT mode every click, key and drawn box acts on the current rat's implant box only:
  - a click offers the masks under the click (cyan);
  - the head-dot candidates are offered until you click;
  - A / N / J / F / B work as before, and **H** (implant hidden) works only here.
- In RAT mode, the same on the rat box: a click offers the masks under the click (pink); M / P apply here.
- The banner reads e.g. "MODE 植入体 IMPLANT · rat 3 / 5 · PRELABEL 预标注". Only the active box is drawn bright.

**Switching rats** ("怎么切换鼠"):
- **Chips** in the banner, one per rat (◆ = added with R). Click one to select that rat. Each chip shows two marks, implant
  and rat box: ✓ done, H hidden, · not yet.
- **White dot:** a plain click within ~12 screen px of another rat's white head dot selects that rat, with no candidate
  lookup. A click on the current rat's own dot is an ordinary click for the active box. To click a body part near another
  rat's dot, zoom in first.
- **Enter / →** next rat, **←** previous rat, **PageDown / PageUp** next / previous frame.

**Export changes:**
- `page_version` is `inbox_sam3_prelabel_edit_2026c_v2.3`; the schema is unchanged.
- An implant click is stored in the implant object's `click` / `clicks`. The CSV columns `body_click_u/v` and
  `n_body_clicks` then hold the implant click.
- New `cand_src` field: `click` when the candidates came from a click, else `head` for the implant (the CSV always fills
  it). Pieces carry `src`.
- New events: `mode_set`, `implant_click`, `rat_select`, `rat_prev`.

## v2.4 (2026-10-12) — the same page, updated in place: mask panel, drag handles, clearer status

The page path, the storage key and your progress are unchanged; the v2.3 files are kept as `*.v2_3.bak`.

**Right-side panel** (the active box only: implant in IMPLANT mode, rat box in RAT mode):
- **"In this box 当前框包含的 mask":** one row per mask in the box (rank, area px, score).
  - Hover a row to highlight that mask in white on the image.
  - **×** removes the mask; the box is refit to the union of the rest (edge drags are dropped; U undoes).
  - Removing the last mask clears the box. A hand-drawn box shows one row "hand-drawn 手画" whose × clears it.
- **"Candidates at your click / the head dot":** one row per candidate. A click on a row shows that candidate, **+** joins
  it (= J), and hover highlights it.

**Resizing:**
- The active box has square **handles**: corners move two edges, and mid-edge handles appear when a side is ≥ 30 screen
  px. A handle is grabbed within 10 screen px and wins over the head dot and over click-for-candidates; an edge is grabbed
  within 8 px. Only one handle or one edge moves at a time, and a box never gets smaller than 2 px.
- Dragging the yellow box of a candidate you have not accepted (hollow yellow handles) accepts it, then resizes.
- Dragging the other mode's box shows "switch to ① IMPLANT (press 1) to edit this box 按 1 切到植入体模式再改" (or ② RAT)
  and no longer pans the image.

**Status per object** is split into two parts:
- **"Box 框:"** — "✓ done — 1 mask (candidate k)", "n joined masks" or "hand-drawn", plus the edge moves; or "— not yet
  未标".
- **"Last click 上次点击:"** — "k of n candidates", "no mask under this point (box unchanged) 这里没有 mask，框没变", or "no
  click yet 还没点".

**New events:** `piece_remove`, `box_clear`, `cand_pick`, `cand_drag_accept`, `wrong_mode_edit`. `edge_move` gains
`handle` and `via`, and `join` gains `via` (key / panel). The data fields are unchanged.
