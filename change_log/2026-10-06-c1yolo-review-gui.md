# 2026-10-06 — Clickable review page for the CH01 YOLO fixed spots and the WISER suspected misses

The user asked where the GUI is ("gui在哪里"): the two review pages were view-only and verdicts had to be typed into CSVs.

## What changed

- **New** `cv/cv_field/c1yolo_review_gui.py` (`--selftest`, 12 checks: payload counts and seek offsets on synthetic rows,
  every media path exists, file:/// URLs only and no network URL, no geometry / occluder / sealed fields in the data, both
  script blocks pass `node --check`, and the verdict logic run in node — Step 2 locked until both spots are saved,
  per-step verdict validation, occluded needs pole / house / grass / other, verdict_first / verdict_final / changed,
  export column order, CSV quoting, import; `--build`). Pattern of `wiser/scripts/make_wiser_event_review.py` (not modified).
- **Page** `D:/Field2026_analysis_out/2026c/cv_field_c1yolo_review_gui_20261006_1614/index.html` (46 kB, + `media_check.csv`,
  `run.json`): one self-contained page, data embedded, works from file:// with no network; media referenced by absolute
  file:/// URLs (22 files: locator, heatmap, 8 crops, 12 clips — all exist; nothing copied or re-rendered).
  - Step 1: locator + heatmap, per spot the 4 crops, its numbers and the per-minute raster; object / rat / unsure + notes;
    a "where are the consistent misses?" note.
  - Step 2 (locked until both spot verdicts are saved — part-B blinding): one player per selected clip (12), keyboard
    play/pause, frame step, 0.5× / 1× / 2×; one row per covered episode (59 clip-episode rows; episode 204 sits in clips 7
    and 8) with time window and a seek button (exact offset from the step-2 frame table); verdicts visible_missed /
    occluded (+ pole / house / grass / other) / not_there_wiser_wrong / box_present / unsure + notes; per-episode save;
    progress n of 59. No geometry class, occluder or sealed number anywhere.
  - Verdicts autosave in localStorage; Export CSV + JSON (one row per item: step, item_id, clip, animal, verdict,
    occluder_kind, notes, saved_at + episode_id, verdict_first, verdict_final, changed, first_saved_at, reviewer, status);
    Import JSON restores; "Save both into folder…" writes both files into a chosen folder where the browser supports it
    (Chrome / Edge File System Access API; not tested in a browser), else download and move.
- **New** `cv/configs/c1yolo_review_2026c/README.md`: where the exports go and what the columns mean.
- Docs: `cv/cv_field/HANDOFF.md`, `cv/cv_field/DATA_MAP_c1yolo_wiser.md` (section C), `CLAUDE.md` (cv_field map), change-log index.

## Not verified

The page was not opened in a browser by the agent (it never views images); the JS was checked with `node --check` and its
pure-logic block run in node. The folder-write button depends on the browser.
