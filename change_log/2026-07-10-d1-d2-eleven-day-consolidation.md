# Change log — Directions 1 & 2 consolidated to the full 11-day / 5-rat window

**Date:** 2026-07-10
**Type:** analysis (re-run existing drivers on 11 days; D1 progression rain-logic generalized). Candidate.
**Env:** `C:\Users\Cornell\anaconda3\python.exe` (3.13.5, numpy 2.1.3, pandas 2.2.3), `KMP_DUPLICATE_LIB_OK=TRUE`.
**Data (read-only):** WISER snapshot `1stcohort_2026_2026-07-09.sqlite` (route-structure + D1) and the
`…\Wiser_backup\incremental\*.csv.gz` set through 07-09 (trajectory/following); baseline
`tag_reports_2026-06-30.sqlite`; weather `AWN-…-20260628-20260709.csv`.

## What / why

Direction 3 was already at the full **11-day / 5-rat** window (06-28 → 07-08); D1 was still at 3 nights and
D2's route-structure at ~1 pooled session. The **5-rat window has now closed** (Hypnos/12380 dropped its
implant **2026-07-09 03:35 EDT** → cohort 5→4; cutoff is data-driven in `configs/rat_identities.csv`, so
every driver auto-trims it and all 11 nights end **before** the drop). This brings D1 & D2 onto D3's
window so the whole pilot sits on one consistent dataset.

## Definitions (new derived quantities; formula + plain text)

- **`wet_ground(night)`** `= (max rain_rate over 15:00–24:00 EDT) > θ_r`, `θ_r = 0.2 mm/hr`. Plain: the
  night's afternoon/evening had meaningful rain, so the ground/paddock is wet during the active window.
- **`rain_in_window(night)`** `= (max rain_rate over 21:00–24:00 EDT) > θ_r`. Plain: rain fell *inside*
  the 9 pm–12 am movement window (an acute event, candidate for the within-night DiD).
- **wet-vs-dry rate contrast** `= mean_{n ∈ wet} rate(n) − mean_{n ∈ dry} rate(n)`, where
  `rate(n) = active_distance_m_per_valid_hour` (already defined in
  `change_log/2026-06-30-nightly-progression.md`) and `dry` = weather-known nights that are not `wet_ground`.
  Plain: does movement differ on wet vs dry nights? **Must be read against per-night `valid_frac`**
  (`= mean(valid fix flag)`) because rain raises UWB dropout (wet nights are **not** missing-at-random)
  **and** wet nights sit later in the habituation sequence — so the gap is confounded, not causal.
- (`active_distance_m_per_valid_hour`, `rain_did` difference-in-differences, bootstrap `did_ci`, jitter
  floor, follow radius, circular-shift/label-permutation nulls are defined in the D1/D2 change logs of
  2026-06-29/30 and 2026-07-07 — unchanged here.)

## Results (candidate; all findings HOLD and mostly sharpen over 11 nights)

### Direction 1 — rain vs habituation
- **`analyze_nightly_behavior.py` (11 nights):** the settling/habituation trend **strengthens** —
  home/shelter use 0.07→0.15, outside movement **246→174 m/valid-hr**, exploration-graph edges 37→27 and
  **night-to-night edge cosine 0.50→0.81** (stabilizes), occupancy similarity 0.84→0.70. Night 1 (06-28)
  → night 11 (07-08). *(Cosmetic 3-night wording removed; dead `(wet)` label deleted.)*
- **`analyze_nightly_progression.py` (11 nights, rain logic generalized):** habituation
  **229→152 m/valid-hr**, first dry-night drop 06-28→06-29 **50%** (reproduces the original). Rain is now
  classified **per night** (5 `wet_ground` nights: 06-30, 07-01, 07-03, 07-05, 07-06; 3 `rain_in_window`:
  06-30, 07-05, 07-06) instead of "the last night = wet". **Wet-vs-dry** rate 122 vs 164 m/valid-hr —
  **confounded** (habituation position + UWB dropout; read vs `nightly_qc.csv valid_frac`), not causal.
  Within-night DiD on 06-30's 22:30 burst **+19.9 [95% CI −8.6,+43.4]** / +18.7 [−8.4,+48.0] — **CI spans 0**,
  no acute rain suppression beyond time-of-night. Rain vs habituation **still not separable** (wet nights
  are late-sequence and low-N).

### Direction 2 — route structure & social following
- **`analyze_route_structure.py` (11 nights):** rats share high-occupancy **interior corridors** robust to
  QC; straightness is real locomotion; **cross-rat edge similarity 0.90 > within-rat night-to-night 0.35**
  → shared-environment-driven, little individual route memory; corridors only ~27% consistent night-to-night.
- **`analyze_trajectory_stereotypy.py` (Phase A, 11 nights):** space-use **stabilizes 0.15→0.89** but
  residual Pearson (after dividing out the shared road) **collapses to −0.01**; label-permutation **0/10**
  pairs above the shared-pool null (only **Dormi** weakly individual). → **mostly SHARED / road-driven**,
  present from night 1. (gap_frac <1.5% all nights; 07-05 backup truncated ~25% → cautious.)
- **`analyze_following_structure.py` (Phase B, 10 nights; 07-04 fireworks excluded):** **herd / promiscuous,
  NOT stable dyads** — a majority of pairs beat their circular-shift null on **9/10** nights, and the **top
  pair reshuffles almost every night (5 distinct top pairs / 10 nights)**; **Sen** the most frequent leader.
- **`analyze_following_incidents.py` (Phase B2, 11 nights):** **2046 strict-following episodes** (median 3 s,
  p95 9 s), up from 1429/8 nights — trailing is frequent but brief. **All four top ordered pairs are
  Sen → X** (Sen→Siesta 1.82/hr · Sen→Hypnos 1.70 · Sen→Dormi 1.47 · Sen→Nox 1.41): Sen is the dominant
  lead. 2046/2046 episodes routed to a camera channel (1545 near a boundary → ≥2 channels); video queue
  `strict_following_video_queue.csv` rebuilt (recall still not claimed — camera map is a placeholder).

## Changes
- **`scripts/analyze_nightly_progression.py`** — rewrote the rain machinery: per-night `wet_ground` /
  `rain_in_window` classification from the full AWN export (new `weather_night_summary.csv` +
  `wet_vs_dry_by_night.csv`), wet-vs-dry contrast read against `nightly_qc.csv valid_frac`, within-night
  22:30 DiD run **only** on in-window-rain nights, data-driven verdict + covariates. `WEATHER_FILES`
  extended to `AWN-…-20260628-20260709.csv`.
- **`scripts/analyze_nightly_behavior.py`** — removed 3-night cosmetic wording (argparse desc, dead `(wet)`
  label, hardcoded "6/30 WET" verdict → generic night-1→night-N + rain-covariate note).
- **`scripts/analyze_{trajectory_stereotypy,following_structure,following_incidents}.py`** — refreshed the
  cosmetic `DEFAULT_OUT` (+ B2 `DEFAULT_PHASEB`) date strings `…_to_2026-07-06` → `…_to_2026-07-08`.
- Outputs → `D:\Field2026_analysis_out\{nightly_progression,nightly_behavior,route_structure}_<ts>\` and
  `outputs/{trajectory_stereotypy,following_structure,following_incidents}_2026-06-28_to_2026-07-08\`.

## Verification
- All six drivers ran on the analysis PC → **11 nights discovered**, all 5 rats/night (Phase B = 10 nights,
  07-04 excluded by design). Per-night `valid_frac`/`gap_frac` checked before reading any rain effect
  (progression `nightly_qc.csv`; stereotypy `coverage_summary.csv` gap <1.5%). Spot-checked verdicts +
  manifests. Read-only on DB + weather; git-ignored data outputs; no source-DB writes.
- **Not done (deferred):** Hypnos-specific handling needs **no** code (auto-cut); georeference/ROI-confirm
  and the D3 biological-day `sleep_end` rebuild remain the open items (see the plan file + Direction-3 flag).
