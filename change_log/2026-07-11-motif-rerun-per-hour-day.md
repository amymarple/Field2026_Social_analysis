# Change log — Route-motif rerun on new data + per-hour / per-day breakdowns + tightened night window

**Date:** 2026-07-11
**Status:** ⚠️ candidate. Rerun of the Phase-B route-motif analysis on all data through the **07-10
night** (13 nights, 06-28→07-10), with per-hour and per-day motif profiles added and the night window
tightened to the data-driven active period. Additive — Phase A / following outputs untouched.
**Driver:** `wiser/scripts/analyze_route_motifs.py`
**Output:** `outputs/route_motifs_2026-06-28_to_2026-07-10/` (renamed from the old `_to_07-06` folder).

## Why

New WISER data landed (incrementals through 2026-07-10, snapshot 07-11). The field observation is that
the rats now run a **pretty uniform set of trajectories** and mostly travel a **visible flattened-grass
"road"** they have worn in. This rerun (a) extends the motif analysis to the new nights, (b) adds the
requested **per-hour** ("when in the night") and **per-day** ("which night") views, and (c) restricts to
the **night-active period only**.

## What changed

- **Night window 21:00→05:00 → 21:00→04:00 (data-driven).** Audited against `circadian_rest`: group
  locomotor activity peaks at **21:00 on every night**, stays elevated through **~04:00**, and troughs
  at **07:00**. So the active period is 21:00→~04:00 (matches the user's "21:00 until 3–4 am"); the
  04:00–05:00 tail is low-activity and now trimmed. `--night-end` default 5→4 (CLI-overridable).
- **`src/trajectory_stereotypy.py`** — three new functions (+ definitions in docstrings):
  - `bout_clock_hour(bouts)` — local EDT start-hour of each bout from its UTC `t_start_ms`
    (Timedelta shift, not int64//ns — pandas[ms] safe).
  - `motif_by_hour(bouts, recur_thr_in)` — per local clock-hour (pooled over nights): n_bouts,
    n_animals, bouts_per_animal, n_motifs, recurrence_frac, median_disp_in.
  - `motif_by_day(bouts, recur_thr_in)` — per night (group): n_bouts, n_animals, n_motifs,
    recurrence_frac, dominant_motif + dominant_frac, group_entropy, median_disp_in.
- **Driver** writes `motif_by_hour.csv` + `motif_by_day.csv` + `plots/motif_by_hour_and_day.png`;
  report gains a **§4 "When in the night, and which night?"**; manifest gains the night-window source,
  barn-light nights, Hypnos cutoff, and the roadway-audit-undone flag.
- **Covariates carried (flags, not exclusions):** `REFUGE4_DROPOUT_NIGHTS` extended to include **07-06**
  (burrow present until refuge_4 removed 07-07 13:00); **barn light (south)** on from the **07-09 night**
  (FIELD_OBSERVATIONS Day 12); **Hypnos (12380)** implant-drop cutoff (07-09 03:35) → cohort **5 rats
  through 07-08, 4 from 07-09** (`apply_tag_cutoffs`, confirmed in the per-day `rats` column).

## Key results (candidate)

- **Trajectories are highly stereotyped from night 1 and stay so.** Route **recurrence = 97%** overall
  (each bout has a near-identical partner route ≤ 21 in = 3× jitter), **92–99% every night** including
  the release night — set by paddock geometry immediately, not learned. This is the quantitative form of
  the "uniform trajectories / worn road" observation.
- **But a repertoire, not one corridor.** ~253 motif clusters; **no single motif dominates any night**
  (top-motif share only **3–10%**, group entropy ~0.93–0.97). The rats reuse *many* established routes,
  not one obsessive path.
- **Per hour:** route activity concentrates at **dusk onset — 21:00 carries ~90 bouts/animal**, tapering
  overnight; **recurrence stays 96–99% at every hour** (stereotypy isn't confined to one part of night).
- **Per day:** stable recurrence across all 13 nights; `n_animals` correctly 5→4 at 07-09.
- **Individual vs shared:** unchanged from before — shared corridors dominate (an animal's nearest route
  is usually another animal's), with a weak individual residual per the label-permutation z.

## Verification

- `python scripts/selftest_trajectory_stereotypy.py` → **PASS** (Phase-A + motif core).
- New `motif_by_hour`/`motif_by_day` unit-checked on synthetic bouts (clock-hour derivation 21:00/02:00
  EDT correct; per-day grouping correct).
- Full run: 1692 bouts / 13 nights, 7 clock-hours × 13 nights; report §4 + figure rendered.

## Follow-ups (UNDONE — explicitly marked, per request)

- **Roadway camera audit — NOT DONE.** Whether these WISER motifs geometrically track the **physical
  trampled-grass road** is unverified against camera footage. Needs the pixel↔field georeference
  (CH01–CH04 overlay of the motif corridors onto the visible path). Flagged in the report "cannot say"
  section, the manifest (`roadway_camera_audit: UNDONE`), and spun off as a background task.
- Barn-light effect on 07-09+ night routes not yet tested (stratify once the light-off date is known).
