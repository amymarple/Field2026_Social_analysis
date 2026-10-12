# 2026-10-12 — In-box CH07: SAM 3 "rat" masks as head-anchored pre-labels — part B (dev edit pilot) built

- **Plan:** [`implementation_plan/2026-10-12-inbox-sam3-rat-prelabel.md`](../implementation_plan/2026-10-12-inbox-sam3-rat-prelabel.md),
  approved by the user 2026-10-12 ("行干吧 ABC都来 我给你标注", "OK, go ahead with A, B and C; I'll do the labelling for
  you"). This entry covers **part B only**, as specified by the plan's sections A, Definitions and B. It also includes
  the B-side items of amendments C2 (quality from the user's own corrections) and C3 (box convention vs tight SAM boxes).
- **Part C** (the frozen test on new frames) is not started; no C frame was chosen or processed.
- **The agent never looked at a frame or a mask.**

## What changed

- **New driver** `cv/cv_field/inbox_prelabel_edit.py`, base Python: `build`, `summarize --export <file> [--more-exports …]`,
  and `--selftest` (26 synthetic checks, all passing).
- **`build`** reads the SAM 3 test run `D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320/`. No SAM 3
  run; it uses the cached masks.
  - **Candidates:** all cached "rat" (P1) masks of `sam3_t1/whole/`: score ≥ 0.01, whole frame, no other filter; 5 167
    masks on the 58 frames.
  - **Per blind head click** (284): the masks within 15 px by the T1 coverage rule (the T1 code, reused), ordered by score
    (ties: smaller area, then cache index). Median 2 candidates per head; **50 of 284 heads have none** (IR 34 / 188,
    colour 16 / 96).
  - **Polygons:** outer contours, approxPolyDP ε 2 px at full resolution, plus the exact mask bbox.
  - **Arms** (seed 20261012): stratified by domain × the frame's largest pile size (1 / 2–3 / 4+), PRELABEL =
    round(2n/3) per stratum → **39 PRELABEL / 19 SCRATCH frames**:
    - IR 2–3: 20 / 10; IR 4+: 5 / 3;
    - colour 1: 1 / 0; colour 2–3: 10 / 5; colour 4+: 3 / 1.
  - **Order:** IR first, then colour, shuffled within each domain.
- **Page for the user:** `D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320/prelabel_edit/index.html`.
  It is self-contained and works from file://; the data sit in `pl_data.js`, with no network.
  - **Top:** the plan's definitions, plus an exported "my definition changes" note.
  - **PRELABEL frames:** the current rat's candidate outline and its box, which is exactly the mask bbox with no padding
    (C3). Other rats' boxes are faint; the head dots are numbered.
    - **A** accept · **N** next candidate, then "none usable" (cycles) · **M** / **P** flag merged / partial · **B** draw a
      box by hand.
    - Drag box edges to adjust · **F** fits the box back to the mask (C3).
  - **SCRATCH frames:** dots only; drag one box per rat.
  - **Both arms:** **R** add a rat (head hidden; on PRELABEL the masks covering the clicked point are offered) · **X** delete
    a dot · **U** undo · **Enter / →** next rat, then next frame. "Redo this frame" keeps the earlier labels as a pass (C2
    repeat check).
  - **Show all (S):** every "rat" mask of the frame. Marks cycle garbage / fragment, and the time is logged separately.
  - **Timing and log:** an active clock per frame, paused when the tab is hidden or after 45 s without input. The
    time-stamped event log records source (rank k / manual), flags, edge moves (from / to), next presses, fit-to-mask,
    add / delete / undo and show-all.
  - **Saving:** localStorage autosave and resume, a progress bar. Export JSON (everything, incl. the proposed box = the
    first candidate's bbox, the final box, the event log and the definition note) and CSV (one row per rat and pass) to
    `cv/configs/inbox_sam3_prelabel_edit_2026c/` (new folder, `README.md`).
  - UI in English with short Chinese key hints.
- **`summarize --export`** writes `<run>/prelabel_edit/summary_B.md` + `.json` and regenerates the SAM 3 report. The report
  now includes `summary_B.md` as the section "B — pre-label edit pilot (dev)" whenever it exists: a small hook in
  `inbox_sam3_dino_test.write_report`, with no other change to that driver. Its content:
  - the plan's B summary: usable@1, usable@any, the merged / partial / manual-box rates, seconds per rat PRELABEL vs
    SCRATCH;
  - C2: IoU proposed → final (median, quartiles), the share accepted with no edit, edge-move-only fixes with the median
    edge shift, other candidate, manual box; the optional repeat check (frames labelled twice; rats matched by head point
    within 15 px);
  - C3: the signed per-edge shift (left / right / top / bottom; px and fraction of the mask-bbox width / height; + = the
    final box larger) for kept first candidates, as median and IQR; SCRATCH box sizes next to the accepted mask bboxes;
    the **proposed** padding rule (per-edge median fraction); the uniformity flag;
  - every block split by pile size and domain;
  - the show-all garbage / fragment marks (descriptive).
  - It has been tested on synthetic exports only. It runs on real data after the user exports.
- **Data size:** `pl_data.js` 3.2 MB (5 167 masks, 289 k polygon points), `index.html` 33 kB, `frames/` 97.9 MB (the
  identity page's 58 original JPEGs, copied unchanged).

## Checks

- `--selftest`: 26 / 26. They cover:
  - arms (counts, order, determinism), pile bins, candidate order, polygon offsets, point-in-polygon;
  - the page script (`node --check`), no network URL;
  - the summary on a synthetic export: usable@1 / any, rates, seconds per rat, counts, splits;
  - C2: no edit / edge only / other / manual, IoU, the repeat check incl. head matching, and that a second export of one
    session is not a repeat;
  - C3: per-edge shifts, the padding proposal, the uniform and one-edge-worse flags, sizes;
  - the markdown.
- **Headless Chrome on the real page: PASS** (`prelabel_edit/page_check.json`):
  - accept (box = candidate bbox); N cycles 1 → 2 → none → 1; flag merged; manual box (B + drag); edge move; F restores
    the mask box;
  - add a rat at a point (1 candidate offered), delete, undo; SCRATCH box by drag with no mask drawn; Enter through a
    frame → frame done → next frame;
  - show all (43 / 43 masks drawn, a garbage mark, 2.0 s on the show-all clock and 0 on the edit clock); the idle pause (0
    ms gained while idle, 1.5 s after input);
  - persistence across a reload, the proposed box = the first candidate bbox, redo → pass archived;
  - export: 58 frames, CSV rows = rats + 1, every event kind present; no network URL.
- **JS vs Python candidates:** at the 284 clicked heads, the page's point-in-polygon + 15 px rule on the simplified
  polygons gives the same list as the exact Python mask rule at 261 heads (92 %). The page uses the exact Python lists for
  clicked heads; the JS rule serves only rats the user adds.

## Choices made in building B (not fixed by the plan)

- **X:** deleting a dot does not jump to the next rat; Enter does.
- **A:** accept does not auto-advance, so edges can be adjusted first.
- **Pan:** right-drag or Space + drag.
- **Show all:** the edit keys are inactive while it is on; a click marks the smallest mask under the pointer.
- **Main pass:** a frame's first completed pass carries the B metrics; later passes enter only the repeat check.
- **Proposed box:** also recorded for SCRATCH rats (not shown), for the C2 crossover later.
- **Uniformity flag thresholds** (the agent's proposal, to be confirmed at the freeze):
  - spread = an edge whose IQR > |its median|;
  - one edge much worse = the largest |median| ≥ 2× the median of the other three and ≥ 0.05.

## Definitions (headline; full set in the B section of the report once the export is in)

- **usable@1** = the share of PRELABEL rats whose first candidate was accepted with no flag.
- **usable@any** = the share of PRELABEL rats for which some offered candidate was accepted with no flag on it. A rat with
  no candidate counts as not usable.
- **Merged / partial rate** = the share of PRELABEL rats with ≥ 1 offered candidate flagged so.
- **Manual-box rate** = the share of PRELABEL rats whose final box was drawn by hand.
- **Seconds per rat** = Σ active seconds / Σ boxed rats, over the completed frames of an arm.
- **IoU proposed → final** = |P ∩ F| / |P ∪ F| of the first candidate's bbox and the final box.
- **Edge shift (C3):** left = x0 − X0, right = X1 − x1, top = y0 − Y0, bottom = Y1 − y1 (mask bbox x, final box X; + =
  larger). The fraction divides by the mask-bbox width or height.

## Not done / next

- **Waiting on the user:** labelling on the page, then exporting.
- **After the export:** `python cv/cv_field/inbox_prelabel_edit.py summarize --export cv/configs/inbox_sam3_prelabel_edit_2026c/<file>.json`.
- **Part C freeze** (candidate order, whole vs tiled, filters, the "usable" definition, the padding rule) follows B with
  the user, before any C frame.
- **Index lines** (`implementation_plan/README.md`, `change_log/README.md`, `CLAUDE.md`) are left to the coordinator.

## Addendum 2026-10-12 — page v2: implant box + rat box (plan amendments B1 / B1a)

**Why.** On v1, the first candidate at a head was the implant mask ("这个implant简直完美", "the implant is just perfect").
The 15-px head rule hides body masks that do not reach the head point. The user decided on an implant box (IR marks are on
the implant) plus a rat box (head + body, no tail).

**What changed:**
- **Command:** `inbox_prelabel_edit.py build --v2` → `D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320/prelabel_edit_v2/index.html`.
  - The same frames, arms (39 / 19, identical to v1: checked) and seed.
  - The frames are hard links to v1's copies (58), so no second 98 MB on disk. `pl_data.js` is 3.2 MB.
  - v1's page and files are untouched. v2 has its own page_version / storage key and ignores v1 progress (checked).
- **Per rat:** the implant box, then the rat box, then Enter; an IMPLANT / RAT indicator; the finished implant box dashed
  orange and the rat box solid green.
  - **Implant box:** the exact v1 head lists (15 px, score, then smaller area), plus **H** = implant hidden.
  - **Rat box:** a body click → candidates = the masks containing the point (the page's polygon + 15 px rule), in score
    order. Nothing is shown before the click.
  - **Both:** A / N / edge drag / F / B. M / P flags on the rat box only.
- **SCRATCH:** both boxes by hand; H applies.
- **R / X / U / redo / show-all:** as in v1.
- **Logging:** per object — the proposed box (the first candidate bbox, with the body click for rat boxes), the final box,
  source / rank, flags, edge moves, N presses, and a time slice (the clock runs for the active box only). Events carry the
  object.
- **Exports:** to `cv/configs/inbox_sam3_prelabel_edit_2026c/`, prefix `v2_`; README updated.
- **`summarize`** detects v2 and computes, per object type (implant box, rat box):
  - usable@1, usable@any; the manual (and, for the rat box, merged / partial) rates;
  - the implant-hidden rate;
  - IoU proposed → final; per-edge signed shifts with the proposed padding rule and the uniformity flag;
  - SCRATCH vs accepted mask-bbox sizes; seconds per box PRELABEL vs SCRATCH;
  - all split by domain × pile; the repeat check per object type.

  It writes `prelabel_edit_v2/summary_B.md`, which the SAM 3 report now prefers over the v1 summary. Tested on synthetic
  exports only.

**Checks:**
- `--selftest`: 37 / 37 (v1 26 + v2 11).
- **Headless Chrome on v2: PASS** (`prelabel_edit_v2/page_check.json`):
  - a v1 storage key is ignored;
  - implant: accept = candidate bbox, edge move, F restores;
  - Enter → RAT, nothing drawn before the body click, the click gives 6 candidates and records the first candidate's
    bbox, N → candidate 2, M flag, accept rank 2;
  - Enter → next rat, H → hidden and active = rat, manual rat box;
  - add (implant hidden, 6 rat candidates from the add point), delete, undo;
  - the rat time slice grows (1.5 s) and the implant slice does not; 0 ms while idle;
  - SCRATCH: two manual boxes, no mask drawn;
  - persistence across a reload; export (v2, 58 frames, CSV = 2 × rats + 1, all event kinds); no network URL.

**Choices made in v2 (not fixed by B1 / B1a):**
- **Added rat:** the R click is also its first body click, so rat-box candidates are offered at once; the implant starts
  hidden and B un-hides it.
- **In RAT mode, mouse:** a left press without movement is the body click; a left drag pans.
- **Body clicks:** a new click replaces the candidate list. The proposed rat box is the first candidate of the latest
  click; every click is logged.
- **Navigation:** Tab switches implant / rat; ← steps back.
