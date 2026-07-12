# Implementation plan — Direction 3: night-time consolidated rest bouts (stay-point)

**Date:** 2026-07-12 · **Type:** analysis (new driver + self-test + weather/familiarity correlations). Candidate.
**Env:** `C:\Users\Cornell\anaconda3\python.exe` (3.13, np 2.1.3, pd 2.2.3), `KMP_DUPLICATE_LIB_OK=TRUE`.
**Data (read-only):** WISER snapshot `1stcohort_2026_2026-07-09.sqlite` (06-28→07-08, 5 rats, 55 rat-nights);
baseline `tag_reports_2026-06-30.sqlite`; ROIs `wiser_rois.json`; AWN weather `AWN-…20260628-20260709.csv`;
shelter video `…\audio_in\Reolink_record\CH05,CH06` (audit only).

*(Retroactive plan: the detector was refined interactively with the user 2026-07-12 — this records the
agreed design. See `change_log/2026-07-12-night-consolidated-rest.md`.)*

## Question
Within the active night (nocturnal), the animals interrupt activity with a **mid-night rest bout**. (1) Detect
and characterize it properly; (2) ask **why** — environmental familiarity (habituation), temperature, or
humidity/rain (moving costs more / retreat to shelter)?

## Definition refinement (why "lowest minute" was wrong)
A first detector took the single lowest-activity 30-min window; it mis-specified (fired on 2/55) because the
rest proxy over-counts rest (high baseline) and a lowest-point ignores *where* the animal is. Per the user,
a **consolidated rest bout (CRB)** must be **spatially clustered** (a stay-point — the animal stays in one
small area), **ideally in an enclosed shelter**, and a **sustained trunk of time** with a **threshold to be
"out"** (exit hysteresis). Framing: this is a low-**movement** settled bout (**rest / grooming / sleep**),
**NOT validated sleep** — "in a shelter for long" is the behavioural signal.

## Definitions (formula + plain text) — every derived quantity
Night window local `[21:00, 05:00)` (cross-midnight; each fix labelled by its **evening date**). Per (rat,
night), 5-min bins → centroid (median x,y) + rest fraction + coverage; a bin needs **≥ 20 fixes** else it is
`unknown` (dropout never counts as rest).
- **rest** (per fix) = `1` iff smoothed speed `< 12.46 in/s` (p99 stationary; jitter ceiling → over-counts rest).
- **Consolidated rest bout (CRB)** — stay-point: consecutive bins whose centroids stay within **R = 24 in**
  of the running centroid (a real "stays in a ~2 ft area", above the ~7 in jitter / p95 15), tolerating
  **≤ 2** out-of-cluster bins (**10 min hysteresis** — the "threshold to be out"), lasting **≥ min-dur** with
  mean rest **≥ 0.60**. `min-dur = 30 min` PRIMARY + **{20,40,60} sensitivity**. Each bout's centroid →
  `classify_site_state`; the **shelter set counts `house_1/2`, `refuge_1/2/3`, `refuge_4` (burrow),
  `water_1/2`, `tunnel`** as enclosed (per user); `doorway`/`exposed` are **non-shelter candidates**.
- Per rat-night: **n_crb**, **total_crb_min** (Σ bout minutes), **shelter_frac**, **longest_onset/dur**.
- **Night weather** (per evening-night, 21:00–05:00): mean temp, mean humidity, max rain rate,
  `wet = rain>0.2 mm/hr`; within-night **coldest** and **most-humid** local hour.
- **Why (Spearman, pooled + within-rat rat-centred):** total_crb_min vs day-in-sequence (familiarity),
  night temp, humidity. **Disentangle:** rain within-rat; **partial** Spearman humidity|rain, rain|humidity,
  humidity|day (rank residualisation); **humidity on DRY nights only**. **Within-night alignment:**
  |longest-CRB onset − coldest/most-humid hour|. **Trait:** η²(total_crb_min) by rat.

## Identifiability / limits (enforced in wording)
Rest = low-movement **proxy** (not ephys/CV sleep); WISER inch frame **unverified** → site labels relative;
n=5 × 11 nights, **uncorrected**; ambient (not shelter-microclimate) weather, ±5 min unverified; temp /
humidity / rain / day-in-sequence partly **collinear** (hence the partials + dry-night subset). Everything
**candidate/descriptive**. Non-shelter candidates need **video audit** (CH05/CH06; NVR clock **UTC−5**).

## Reuse
`load_wiser_session`, `convert_timestamps`, `trim_last_n_minutes`, `add_speed`, `speed_noise_floor`,
`add_validity_flags`, `apply_tag_cutoffs`, `rest_mask`, `_bin_utc_ns`, `classify_site_state`, `load_rois`,
`load_weather_multi`, `LOCAL_TZ_OFFSET_HOURS`, `write_run_manifest`. Stay-point + partials are new (in the driver).

## New code
- **`scripts/analyze_night_consolidated_rest.py`** — driver: night window → 5-min bins → `_stay_bouts`
  (stay-point CRB) at each duration → `classify_site_state` → sensitivity table + per-rat-night aggregation +
  weather merge + WHY correlations + disentangling; non-shelter candidate export (nearest-house CH05/CH06
  route); report + CSVs (`consolidated_rest_bouts`, `duration_sensitivity`, `nonshelter_rest_candidates`,
  `crb_per_ratnight`, `why_correlations`) + manifest → git-ignored `<FIELD2026_ANALYSIS_OUT_ROOT>/night_consolidated_rest_<ts>/`.
- **`scripts/selftest_night_consolidated_rest.py`** — offline planted: clustered-rest→bout, wanderer→none,
  active→none, 1-bin blip merged, long excursion breaks, short→none, night-weather wet flag + coldest hour. PASS.

## Figures
None in this pass (tabular + report). A per-night hypnogram-style occupancy strip is a possible follow-up.

## Verification
- `python scripts/selftest_night_consolidated_rest.py` → **PASS** (8/8).
- Real run read-only on the snapshot: sensitivity {20,30,40,60}, primary 30-min (137 CRBs, 93 % shelter,
  median 50 min, 4-in radius, 55/55 rat-nights), WHY + disentangling + within-night alignment spot-checked.

## Non-goals
No reward/IRL; no sleep validation (needs ephys / interior CV CH07/CH08); no georeference dependency; the
video audit is best-effort (placeholder camera map → nearest-house route; unverified −5 h NVR clock).
