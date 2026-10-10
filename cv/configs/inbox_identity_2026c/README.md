# In-box identity clicks, cohort 3 (CH07 / CH08 colour segments)

This folder holds the **user's** exports from the identity click page built by `cv/cv_field/inbox_identity_page.py`
(plan `implementation_plan/2026-10-10-inbox-ch0708-wiser-identity-p0.md`, part C, amendments 7–8). Nothing in here is made
by a machine: the page carries no pre-filled identity, and the agent never judges the frames.

Page: `D:/Field2026_analysis_out/2026c/cv_field_inbox_p0_<ts>/identity_page/index.html` (the current run is named in
`results/2026c/cv_field/reports/run_manifest_inbox_p0_2026c.json`, key `identity_page`). Open it from disk in a browser;
it works offline. Clicks are autosaved in that browser (localStorage, key `inbox_identity_2026c_v1::<run>`); export them to
keep them.

## Blind first (2026-10-10)

Per segment the WISER roster and the top-view arrangement are **hidden** until **Save clicks & reveal WISER** is pressed
for that segment. The reveal cannot be undone. The clicks saved at that moment are the blind record the pre-registered order
test uses: each of them gets `before_reveal: true` and a frozen copy `verdict_first`. Edits made after the reveal change the
live fields (= final) and set `edited_after_reveal`; a blind click deleted after the reveal is kept with
`deleted_after_reveal: true`; a click added after the reveal has `before_reveal: false`.

Clicks stored by the first page version (before 2026-10-10 evening) carry no reveal flag: on the first load of the new
version they become `before_reveal: true, legacy: true`. **That first version showed the WISER panel all the time, so
legacy clicks were not made blind.**

## How to save

1. On the page press **Export JSON** and **Export CSV**. The browser writes `inbox_identity_2026c_<YYYYMMDD_HHMMSS>.json`
   and `.csv` to its download folder.
2. Move both files into this folder, unchanged. Keep every export (later ones do not overwrite earlier ones; the newest
   is the current state).
3. To continue on another browser or machine, open the page and press **Import JSON** with the newest export.

## What the files contain

JSON: `page_version`, `state_version` (2), `run` (the run folder the page belongs to), `exported_at`, `legend_source`,
`legacy_migrated_at`, `clicks` (one object per click, including blind clicks deleted after the reveal), `segments` (one object
per colour segment: `complete` / `complete_first` = the answer to "pile composition complete?" now / at the reveal — `yes`,
`no` or empty —, `note`, `revealed_at`, `saved_at`, counts `n_clicks`, `n_before_reveal`, `n_after_reveal`, `n_legacy`,
`n_deleted_after_reveal`).

Each click: `click_id`, `segment_id` (`<camera>_<YYYYMMDD>_<HHMMSS>` of the colour ON), `camera`, `house` (CH07 = house_2,
CH08 = house_1), `frame_kind` (`colour_mid` = colour frame at the segment middle; `ir_p06` / `ir_p15` = IR frames 6 s /
15 s after the colour OFF), `frame_file`, `frame_idx` (frame index in that hourly file), `frame_time` (field-PC local =
file-name start + PTS), `u_px`, `v_px` (full-resolution pixel of the clicked head, origin top-left, image as recorded),
`animal` (SF07–SF12 or `unknown`; empty if never picked), `confidence` (`sure` / `likely`), `before_reveal`, `legacy`,
`verdict_first` (`animal`, `confidence`, `u_px`, `v_px`, `frame_kind` at the reveal), `edited_after_reveal`,
`deleted_after_reveal`, `clicked_at`, and the frame's lid-closed segment with its correction: `lid_segment`, `lid_flag`,
`lid_target_frame`, `B_frame_to_ref` (2 × 3 matrix: frame pixel → the 09-04 12:00 reference pixel of that segment; from
`cv/cv_field/frame_correction.py`; recorded only).

CSV: one row per click (`record = click`; `first_frame_kind`, `first_u_px`, `first_v_px`, `first_animal`,
`first_confidence` = `verdict_first`; matrix as `b11 … b23`) plus one row per segment (`record = segment`,
`pile_complete`, `pile_complete_first`, `revealed_at`, `note`).

Identity legend on the page: the user's identifying colour per animal (2026-10-10; `id_colour` in
`wiser/configs/rat_identities_2026c.csv`: SF07 green, SF08 red, SF09 blue, SF10 black, SF11 white (looks grey), SF12
yellow; the first days about 08-30 / 08-31 are uncertain), with the Notion coban / sticker shown for reference.

## What uses it (later, pre-registered, not run yet)

Per house: the image ↔ house-frame mapping (2-D similarity of the clicked heads, corrected to the lid-segment reference
frame, vs the WISER minute means of the same animals) and the WISER bias, with leave-one-flash-out residuals. The
arrangement layer is accepted if the left-to-right order along the box from WISER matches the clicked order in
**≥ 4 of the first 5** flashes with ≥ 3 identified animals (the operator's rule), on the clicks saved **before the reveal**
(`verdict_first`).
