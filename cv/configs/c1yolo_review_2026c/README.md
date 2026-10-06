# c1yolo review verdicts (cohort 2026c)

Exports of the clickable review page `cv_field_c1yolo_review_gui_<ts>/index.html` (made by
`cv/cv_field/c1yolo_review_gui.py --build`). Put both exported files here:
`cv-configs-c1yolo_review_2026c__review_<reviewer>_<stamp>.csv` and `.json`.

- **Step 1** (rows `spot_1`, `spot_2`): the two YOLO fixed spots, verdict object / rat / unsure; row `fn_notes` = where the
  consistent misses are (free text). These replace `fixed_spots/fixed_spots_review.csv` and `fn_notes.txt` of the step-2 run.
- **Step 2** (rows `c<clip>_ep<episode>`, 59): the WISER suspected-miss episodes of the 12 review clips, verdict
  visible_missed / occluded (+ `occluder_kind` pole / house / grass / other) / not_there_wiser_wrong / box_present / unsure.
  These replace `review_clips/review_template.csv` of the phase-0 run.
- Columns: step, item_id, clip, animal, verdict, occluder_kind, notes, saved_at, episode_id, verdict_first, verdict_final,
  changed, first_saved_at, reviewer, status. `verdict` = the last saved verdict; `verdict_first` = the first saved one;
  `changed` = they differ; `status` = saved / draft (changed but not saved) / todo.

The agreement of these verdicts with WISER (part B) and with the CH01 occlusion geometry is a later, separate step.
