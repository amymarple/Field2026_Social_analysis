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

## Addendum 2026-10-12 — page v2.1 in place: join several masks into one box (plan amendment B2)

**Why.** The user, while labelling v2: "很多是 这个几个mask一个鼠" ("many of these are one rat split over several masks").

**The user's progress is kept:**
- `inbox_prelabel_edit.py update-v21` updates `prelabel_edit_v2/` in place: the same folder, file names and frames, and
  **the same localStorage key** (`inbox_sam3_prelabel_edit_2026c_v2::<run>`, pinned in `pl_data.js` as `storage_key`).
- The data's `page_version` is now v2.1.
- New fields are added lazily when a v2.0 state loads; no v2.0 value is rewritten.
- Before writing:
  - `index.html`, `pl_data.js`, `page_check.json` and `build_meta.json` were copied to `*.v2_0.bak`;
  - the regenerated payload (frames, order, arms, heads, masks, candidate lists) was verified identical to v2.0, so every
    stored mask id keeps its meaning;
  - the new page was tested from a staged copy and replaced the live files only after the check passed. The backups are
    byte-identical to the v2.0 files (MD5).

**Join:**
- **J** adds the current candidate to the active object's pieces (rat box and implant box). The box becomes the union bbox
  of all pieces.
  - Every piece is outlined in the object's colour; the not-yet-joined candidate is dashed.
  - J on an already-joined mask does nothing (a toast says so).
- **U** undoes the last step, e.g. the last join. **F** refits the box to the union.
- **A** replaces the pieces with one mask, with a toast if pieces existed.
- Edge drags still work; the union box before any drag is recorded.
- M / P on a joined box flag the whole object.
- **Proposed box:** the first candidate of the first body click. Rat boxes made in v2.0 with more than one click keep their
  stored (latest-click) proposal, labelled `prop_rule` = latest_click_v2.0.
- **Help line:** "J join this piece 拼接 (click another part → N → J)".

**Logging and export:**
- source = cand / joined / manual;
- `pieces` (mask, rank, click point, cache index, score), `n_pieces`, `union_box`, `obj_flags`, `prop_rule`;
- the CSV adds n_pieces, pieces_cache_index, union_* and prop_rule.

**`summarize`** (it accepts v2.0 and v2.1 exports), per object type, domain and pile:
- usable@any as a single mask AND with joins; the joined share;
- the n_pieces distribution;
- seconds per box by source (single / joined / manual);
- for joined boxes, the per-edge shift from the union box to the final box.

Tested on synthetic exports only.

**Checks:**
- `--selftest`: 47 / 47 (v1 26 + v2 11 + v2.1 10).
- **Headless Chrome: PASS** (`prelabel_edit_v2/page_check.json`).
  - **Old-state test:** the backed-up v2.0 page saved finished rats:
    - an implant candidate;
    - a rat box from a body click, flagged merged and accepted;
    - a hidden implant with a manual rat box;
    - two manual boxes on a SCRATCH frame;
    - time slices and events.

    The v2.1 page then loaded them under the same key, in the same throwaway profile:
    - the export equals the v2.0 export apart from the new fields;
    - time grew only by the reload's few seconds;
    - the event log is intact, with only `visibility` / `frame_open` from the reload added;
    - 568 objects migrated.
  - **Joins:** join 2 pieces (box = union) → J again = no-op → a 3rd piece from a second click → U back to 2 → an edge drag
    then F → the union → M on the joined box (object level) → A replaces the pieces (toast) → J on an implant (2 pieces).
  - **Export:** v2.1, CSV = 2 × rats + 1, `join` events, pieces with cache indices; no network URL.

## Addendum 2026-10-12 — page v2.2 in place: UX fixes (a click always goes to the rat box)

**Why.** The user: "我click了body 然后显示橘色或者黄色，但按j完全没反应" ("I clicked the body, it showed orange or yellow, but
J did nothing at all").
- The page was still in IMPLANT mode, so the body click was ignored.
- J then acted on an implant candidate that was already joined, and the toast was easy to miss.

**Fixes** (`inbox_prelabel_edit.py update-v22`; same folder, files and storage key):
- **Click:** on a PRELABEL frame, a plain click on the image (not in draw mode, not in show-all) always switches to the
  current rat's RAT box and runs the body click. This is logged as `obj_auto_switch`.
- **Mode banner** above the image, coloured like the box:
  - "NOW: IMPLANT box 植入体框 (orange)" or "NOW: RAT box 整鼠框 (green) — click the body";
  - plus "PRELABEL 预标注" or "SCRATCH 从零画框 — drag to draw, no candidates, A/N/J off".
- **Toasts:** larger and centred near the top. When J, A, N, M or P cannot act, a toast in English and Chinese says why:
  already joined; no candidate here — click the body first; SCRATCH frame — draw by hand; implant hidden; none usable;
  M / P are for the rat box only.
- **Legend:** a collapsible colour legend in the image corner.
- **Help line:** "Each rat: implant (A/N/J, H hidden) → click the body → rat box (A/N/J…) → Enter".

**Safety:**
- `*.v2_1.bak` backups were made first; they are byte-identical to v2.1 (MD5).
- The payload was verified identical to v2.1, and the staged copy was checked before the live files were replaced.
- No data field changed: the page version is v2.2, and `summarize` reads v2.0 / v2.1 / v2.2 exports.

**Checks:**
- `--selftest` 52 / 52.
- **Headless: PASS** (`prelabel_edit_v2/page_check.json`):
  - **Old-state test:** a v2.1 state with a 2-piece joined rat box and an object-level merged flag, an accepted implant, a
    hidden implant with a manual rat box, and SCRATCH boxes loads intact in v2.2. Exports are equal apart from the version
    and the reload's events.
  - A click in IMPLANT mode switches to RAT and gives 5 candidates (`obj_auto_switch` + `body_click`). J joins 1, then N → J
    gives 2 pieces.
  - The four toasts and the banner text for both arms × both boxes; the legend.
  - Export (v2.2, CSV = 2 × rats + 1); no network URL.

## Addendum 2026-10-12 — page v2.3 in place: two explicit sticky modes and rat switching

**Why.** The user found the v2.2 flow too complicated: "太复杂了，按照俩选项，点implant 框只画implant 点rat body只换rat
然后显示我现在到底是啥模式，不然我都不知道我在点啥". Then: "怎么切换鼠" (how do I switch rats).

**Changes** (`inbox_prelabel_edit.py update-v23`; same folder, files and storage key):
- **The v2.2 auto-switch is removed.**
- **Two modes:**
  - buttons "① 植入体 IMPLANT" (orange) and "② 整鼠 RAT" (green) above the image; keys 1 / 2; Tab toggles; each change
    is logged as `mode_set`;
  - the mode never changes on Enter, ←, a new rat or a new frame;
  - every click, key and drawn box acts on the active object only;
  - IMPLANT: a plain click offers the masks under the click (`implant_click`; `cand_src` = click). The head-dot candidates
    stay pre-offered, and the proposed box is still the first head-dot candidate. H works only in this mode.
  - RAT: a click offers rat candidates; M / P work only in this mode.
- **Banner:** "MODE 植入体 IMPLANT · rat i / n · PRELABEL 预标注", or "… · SCRATCH 从零画框 (drag to draw)". Only the
  active object's candidate, pieces and box are bright.
- **Rat switching:**
  - number chips in the banner, with per-object marks (✓ done, H hidden, · not yet);
  - a plain click within 12 screen px of another rat's white dot selects that rat with no candidate lookup (`rat_select`,
    via chip / dot);
  - Enter / → next rat, ← previous rat (`rat_prev`), PageDown / PageUp frames.
- **Kept from v2.2:** the toasts (new ones: H outside IMPLANT mode; a rat added in IMPLANT mode), the legend and the
  logging.
- **Choice of mine:** a click on the current rat's own dot stays an ordinary click for the active box. The implant sits at
  the head, so a dot click there must still give candidates.
- **Summary:** counts implant boxes whose candidates came from a click (`from_click`). Their rank refers to the click's
  candidate list.

**Safety:**
- `*.v2_2.bak` backups were made first.
- The payload was verified identical to v2.2, and the staged copy was checked before the live files were replaced.
- `summarize` reads v2.0–v2.3 exports.

**Checks:**
- `--selftest` 58 / 58.
- **Headless: PASS** (`prelabel_edit_v2/page_check.json`):
  - **Old-state test:** a v2.2 state (accepted implant; 2-piece joined rat box with a merged flag; hidden implant with a
    manual rat box; SCRATCH boxes) loads intact under the same key.
  - **Clicks:** in IMPLANT mode a click gives 5 implant candidates and leaves the rat box untouched; in RAT mode the
    reverse. J works in both modes (implant 1 piece from the click; rat 2 pieces).
  - **Sticky mode:** the mode stays across Enter, ←, PageDown and PageUp.
  - **Keys:** Tab, 1 / 2 and both buttons. H is refused with a toast in RAT mode and works in IMPLANT mode.
  - **Rat switching:** the chips show "1✓✓" and "1H✓" and a chip click selects that rat. A dot click selects another rat in
    both modes, with no candidate change; a click on the own dot gives `implant_click`.
  - The banner texts, the help line and the legend.
  - Export: v2.3; the CSV has `cand_src` and 2 × rats + 1 lines; no `obj_auto_switch` event; no network URL.

## Addendum 2026-10-12 — page v2.4 in place: mask panel, drag handles, clearer status

**Why.** Two requests from the user:
- "不行右侧显示一列 哪些mask被包括进了当前选择这样我可以直接点击删除不是的mask。另外我发现没法更改implant的框": show which
  masks are in the box so wrong ones can be removed; and the implant box could not be changed.
- From a screenshot, "这明明已经画上了为啥没有候选": the status line mixed the box with the last click.

**Cause of "the implant box cannot be changed"** (reproduced headlessly on the v2.3 page, 1185 × 675 canvas, fit zoom
0.35 screen px per image px):
- **Before A there was no box to edit.** Dragging the yellow dashed bbox of the shown candidate only panned the image
  (36 px).
- **The edge grab band was 8 screen px with no visible handle.** A press 12 px inside the edge panned the image (100 px)
  instead of resizing.
- **In RAT mode the implant box was silently not editable.** A drag on its edge panned the image, with no message.
- **A small box collapsed.** At ≤ ~16 screen px the four 8-px bands overlapped, so one drag moved all four edges to the
  cursor. A 9 × 9 px box became a zero-height line.
  - The implant candidates are whole-rat masks (smallest side at fit zoom: median 65 px, q10 50 px). Shrinking one to
    the implant therefore lands in this range.
- **What did work:** after A, in IMPLANT mode, an edge or corner drag on a large box.

**Changes** (`inbox_prelabel_edit.py update-v24`; same folder, files and storage key):
- **Right-side panel for the active object:**
  - the masks in the box (rank, area, score; hover = white highlight; × removes one and the box is refit to the union of
    the rest; the last one clears the box; a hand-drawn box has one row whose × clears it; U undoes);
  - the candidates at the last click or the head dot (a row click shows it, + joins it).
- **Handles:**
  - visible square handles on the active box: corners move two edges; mid-edge handles appear when a side is ≥ 30 px;
  - grab radius 10 screen px; the nearest handle wins over the head dot and over click-for-candidates;
  - an edge is grabbed within 8 px, one edge only; minimum box size 2 px.
- **Candidate box:** a drag on the yellow bbox of an un-accepted candidate (hollow handles) accepts it, then resizes
  (`cand_drag_accept`). A plain click there is still a candidate click.
- **Wrong mode:** a drag on the inactive box shows "switch to ① IMPLANT (press 1) to edit this box 按 1 切到植入体模式再改" (or
  ② RAT) and does not pan (`wrong_mode_edit`).
- **Status per object:** "Box 框: ✓ done — 1 mask (candidate k) / n joined masks / hand-drawn, edge moves" or "— not yet
  未标". Then "Last click 上次点击: k of n candidates / no mask under this point (box unchanged) 这里没有 mask，框没变 / no
  click yet 还没点". The no-mask toast now reads "no mask under this point (box unchanged 框没变)".

**Safety:**
- `*.v2_3.bak` backups were made first.
- The payload was verified identical to v2.3; the staged copy was checked before the live files were replaced.
- The data fields are unchanged, apart from new events and `edge_move.handle` / `via` and `join.via`.

**Checks:**
- `--selftest` 63 / 63.
- **Headless: PASS** (`prelabel_edit_v2/page_check.json`):
  - **Old state:** a v2.3 state (implant click + accept, 2-piece joined rat box with a merged flag, hidden implant +
    manual rat box, SCRATCH boxes) loads intact.
  - **Panel:** 5 candidate rows; a row click makes it current; hover highlights the mask; + joins three (`via` panel).
  - **× and undo:** × removes one piece and the box shrinks to the union of the other two; U restores the 3-piece box. ×
    on a single mask clears the box ("Box 框: — not yet 未标"), and U restores it.
  - **Resizing the implant box:** a mid-edge handle drag of −15 px and a corner drag of +10 / +10 px after A, with the
    other edges unchanged.
  - **Candidate box:** a corner drag on rat 2's un-accepted head candidate gives the events accept → cand_drag_accept →
    edge_move and a resized box.
  - **Wrong mode:** in RAT mode a drag on the implant handle gives the toast, no change and no pan.
  - **Small box:** a 9 × 9 px hand-drawn box at fit zoom has 4 handles and grows by its corner without collapsing; a press
    between handles changes nothing; × clears it (`box_clear`).
  - **Status:** the split status after a no-mask click on a 3-mask rat box ("✓ done — 3 joined masks" + "no mask under
    this point (box unchanged)"), and the toast; the empty status.
  - The help line, the legend and the v2.4 export; no network URL.
