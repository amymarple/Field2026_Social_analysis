# Change log — Direction 3: night-time consolidated rest bouts (stay-point) + non-shelter video audit

**Date:** 2026-07-12
**Type:** analysis (new driver; refined rest-bout detector + weather/familiarity correlations). Candidate / measurement-limited.
**Env:** `C:\Users\Cornell\anaconda3\python.exe` (3.13, np 2.1.3, pd 2.2.3), `KMP_DUPLICATE_LIB_OK=TRUE`.
**Data (read-only):** WISER snapshot `1stcohort_2026_2026-07-09.sqlite` (06-28→07-08, 5 rats, 55 rat-nights);
baseline `tag_reports_2026-06-30.sqlite`; ROIs `wiser_rois.json`; shelter video `…\audio_in\Reolink_record\CH05,CH06`.

## What / why
The night activity trough (a "nap") was first detected by a naive lowest-activity minute (fired on 2/55,
mis-specified). Per user (2026-07-12) it is refined to a **consolidated rest bout (CRB)**: the animal's
**position clusters in a small area** (a stay-point) while **low-movement**, held for a sustained **trunk
of time**, with an **exit tolerance** so brief blips don't end it — tagged by whether that spot is an
**enclosed shelter**. Framing is measurement-honest: this is a low-**movement** settled bout
(rest / grooming / sleep), **NOT validated sleep**; "in a shelter for long" is the behavioural signal.

## Definition (formula + plain text) — `scripts/analyze_night_consolidated_rest.py`
Night window local `[21:00, 05:00)` (cross-midnight, labelled by evening date). Per (rat, night), 5-min
bins → centroid (median x,y) + rest fraction + coverage; a bin needs ≥ 20 fixes else it is `unknown`
(dropout never counts as rest). **Stay-point CRB** = consecutive bins whose centroids stay within
**R = 24 in** of the running centroid (tolerating ≤ **2** out-of-cluster bins = 10 min hysteresis, the
"threshold to be out"), lasting **≥ the minimum duration**, with mean rest ≥ **0.60**. Each bout's centroid
→ `classify_site_state`; **shelter set counts `house_1/2`, `refuge_1/2/3`, `refuge_4` (burrow), `water_1/2`,
`tunnel` as enclosed** (per user); `doorway`/`exposed` are non-shelter. `rest = speed < 12.46 in/s`
(jitter-ceiling proxy). WISER inch frame UNVERIFIED → position/site are relative, not physical.

## Results (validation only — NO weather/familiarity correlation yet, by request)
- **Duration sensitivity** (primary 30 min + 20/40/60 sweep), 55 rat-nights:

  | min dur | bouts | rat-nights w/ ≥1 | % in shelter | median dur | bouts/night |
  |--:|--:|--:|--:|--:|--:|
  | 20 | 245 | 55/55 | 78 % | 30 min | 4.5 |
  | **30 (primary)** | **137** | **55/55** | **93 %** | 50 min | 2.5 |
  | 40 | 101 | 55/55 | 98 % | 60 min | 1.8 |
  | 60 | 54 | 40/55 | 100 % | 80 min | 1.0 |

- **Primary (30 min):** 137 CRBs, **every rat-night has ≥1**, **93 % in a shelter**, median 50 min,
  **median cluster radius 4 in** (they are pinned to a spot, tighter than the ~7 in jitter floor). Sites:
  house_1 84 · house_2 25 · tunnel 10 (06-28 only) · refuge_4 9 (12395, burrow window) · exposed 5 · doorway 4.
  Onset clusters ~22:00–02:00. So night rest is universal, house-centred, individually consistent.
- **9 non-shelter consolidated-rest candidates** (5 exposed, 4 doorway) exported
  (`nonshelter_rest_candidates.csv`) with WISER position + nearest-house camera route (house_1→CH05,
  house_2→CH06) for manual audit.

## Why (correlations on the REFINED metric, 2026-07-12) — candidate
Per rat-night: **total consolidated rest 145 min (2.5 bouts)**. Spearman (pooled + within-rat), n=5×11, uncorrected:
- **Familiarity (day-in-sequence): NO** — total-rest ρ=−0.20, #bouts −0.04 (they do not rest more as they settle).
- **Temperature: NO — and this RETRACTS the crude "hot→more rest".** total-rest vs night temp pooled −0.10,
  **within-rat −0.12**. The earlier lowest-minute metric gave +0.44, but that counted **any** low-movement
  (heat lethargy anywhere); requiring a **clustered in-shelter bout** removes it. **Refining the detector
  before correlating changed the conclusion.**
- **Humidity: CANDIDATE YES, and ROBUST to the obvious confounds** — total-rest vs humidity pooled +0.34,
  **within-rat +0.36**. Disentangled (rank-partial + subset): **humidity | rain +0.46**, **humidity | day-idx
  +0.44**, and on the **40 dry rat-nights only +0.63** — while **rain itself is non-positive** (within-rat
  **−0.25**, rain | humidity −0.39). So the driver is **atmospheric dampness, NOT rainfall or habituation**
  ("damp night → stay settled in shelter"). Candidate: ambient (not shelter) humidity, n=5×11, proxy,
  unverified frame, uncorrected; the rain-negative may partly be UWB dropout near shelters, not pure behaviour.
- **Timing is clock-locked, not weather-locked:** the longest CRB starts a median **3.9 h from the coldest
  hour** and **2.4 h from the most-humid hour** (both ~pre-dawn) → humidity modulates the *amount* of night
  shelter-rest, not its ~midnight timing.
- **Trait vs state:** total-rest η²(rat)=**0.14** — mostly a night-level state, weak individual consistency.

New outputs: `crb_per_ratnight.csv`, `why_correlations.csv`, report `night_consolidated_rest_report.md`.

## Non-shelter video audit + a cross-modal CLOCK finding
- Cropped CH05/CH06 IR frames (+2/+15/+28 min into each bout) →
  `outputs/night_consolidated_rest/nonshelter_audit_frames/` (**15 frames for 5 of 9 candidates**). The
  other 4 (06-28 release night, 07-04, 07-07, 07-08) have **no transferred CH05/CH06 file** on the analysis PC.
- ⚠️ **NVR video clock ≈ UTC−5 (EST), not UTC−4.** A spot-check frame timed from WISER (UTC + `−4`) landed
  **exactly 1 h late** vs the on-screen NVR stamp (WISER→local 01:10 showed 00:10; the shelter was wet,
  matching the rainy 07-03 night). Re-cropping at **UTC−5** lands frames inside the bout. So for
  **WISER→shelter-video** alignment the offset is **−5 h** (the NVR appears to run EST year-round), whereas
  `LOCAL_TZ_OFFSET_HOURS=−4` (WISER→AWN-weather local EDT) is unchanged. **Spot-check evidence (one event);
  verify across more events before trusting to the minute.** See [[wiser-nvr-video-clock-offset]].

## Changes
- **NEW `scripts/analyze_night_consolidated_rest.py`** — stay-point CRB detector + duration sensitivity
  sweep + non-shelter candidate export + nearest-house camera route. Outputs `consolidated_rest_bouts.csv`,
  `duration_sensitivity.csv`, `nonshelter_rest_candidates.csv`, `run_manifest.json` → git-ignored
  `<FIELD2026_ANALYSIS_OUT_ROOT>/night_consolidated_rest_<ts>/`.
- Superseded the scratch "lowest-minute nap" exploration (never committed).

## Verification
- Compile OK; real run read-only on the snapshot → 55 rat-nights, sensitivity table + candidate queue
  spot-checked; 15 audit frames extracted (cv-env ffmpeg). Coverage-guarded (≥20 fix/bin); refuge_4 burrow
  counted as shelter per user; frame is a valid CH05 top-down IR shelter view.
- Detector signed off (30-min primary + shelter rules incl. refuge_4/tunnel); **why correlations + humidity
  disentangling built into the driver** (weather via `load_weather_multi`); report + `crb_per_ratnight.csv` +
  `why_correlations.csv`.
- `python scripts/selftest_night_consolidated_rest.py` → **PASS (8/8)** (clustered-rest / wanderer / active /
  hysteresis-merge / long-excursion-break / short / night-weather). Plan: `implementation_plan/2026-07-12-
  night-consolidated-rest.md`. Scientific summary: `outputs/night_consolidated_rest/SCIENTIFIC_SUMMARY.md`
  (promotion-gate audited: humidity Candidate, temperature retracted, familiarity No).
- **DEFERRED:** firm the humidity candidate further (within-night hazard model + a shelter humidity logger to
  turn ambient→microclimate); the 4 missing non-shelter video crops (re-transfer 06-28/07-04/07/08 CH05/06).

## Caveats
Rest = low-movement proxy (not scored sleep); n=5 × 11 nights; WISER frame unverified (site labels relative);
video routing uses the nearest-house guess (the `camera_visibility_map.yaml` is a placeholder) + the −5 h
NVR clock, both approximate; non-shelter candidates await visual audit.
