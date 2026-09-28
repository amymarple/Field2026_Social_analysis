# WISER measurement audit — `wiser_baseline` (cohort 2026a): fixed-position precision

- **Auditor:** wiser-measurement-auditor (WISER Measurement-Context Auditor)
- **schema:** `wiser_measurement_audit/1.0`
- **Target artifact:** `results/2026a/wiser_baseline/reports/wiser_baseline_fixed_position_summary_2026a.csv`
- **Supporting context:** `wiser/ANALYSIS_STATUS.md` (row "Fixed-position precision" ✅; inventory rows "Stationary baseline", "Fixed-position ground truth"), `wiser/configs/fixed_position_ground_truth.csv`, driver `wiser/scripts/analyze_fixed_position_test.py`, metrics `wiser/src/metrics.py`, narrative `summaries/wiser_baseline.md`, card `analyses/wiser_baseline/fixed_position_precision.md`.
- **Audit run git commit (this audit):** `084d4c2e83fc2e27b1fcba4f05f75ffd1e1142e1`
- **generated_utc:** 2026-07-12 (from environment date; Bash `date`/`git` blocked by a shell profile that touches a disallowed drive — stamp is approximate)
- **Vocabulary:** candidate / confirmed / ⛔ blocker per `wiser/ANALYSIS_STATUS.md`.

---

## 0. Headline verdict

**Partially auditable / weaker provenance than CV.**

- The **precision (jitter) finding is measurement-supported** as a *raw, unfiltered, two-location, 2-D
  precision floor*: stationary RMS jitter ≈ **6.4–7.9 in** (median ≈ 7 in), radial **p50 ≈ 3.4 in**,
  **p95 ≈ 12.5–15.7 in**, consistent across all 6 tags. This is interpretable AS A MEASUREMENT of
  **precision / repeatability** and is frame-invariant as a scalar spread.
- The **accuracy / bias / error columns are a measurement artifact** — they were computed against a
  placeholder ground truth of **(0, 0)**, so they are the *distance of each tag from the frame origin*
  (~843–964 in), **not** accuracy. They must not be read as accuracy.
- **No absolute accuracy is established anywhere in this artifact.** The config "ground truth" is the
  WISER **median of the same data** ("median estimated position", self-derived), the run used
  (0,0) placeholders, and the georeference transform is absent. Precision ≠ accuracy here in the
  strongest sense.
- Provenance is materially weaker than the CV pipeline: **no `run_manifest.json`, no `filtering_log.txt`,
  no `measurement_context` sidecar, no per-row `mc_run_id`, no dedicated change_log**, and the current
  `fixed_position_ground_truth.csv` **does not match the run that produced the CSV** (6 self-derived tags
  now vs 4 zero-placeholder tags then) → the accuracy columns are not reproducible.

---

## 1. Locate — run directory & provenance artifacts

| Artifact | Status | Note |
|---|---|---|
| Off-repo run dir (`D:\Field2026_analysis_out\2026a\`) | **only `cv_field_harvest` present** | The WISER fixed-position run dir is **ABSENT** — audited from the in-repo CSV + configs + tracker rows. Degraded gracefully (no manifest). |
| `run_manifest.json` | **ABSENT** | Cannot verify `git_commit`, `generated_utc`, `units`, `timestamp_method`, `jitter_floor_in`. |
| `filtering_log.txt` | **ABSENT** | No thresholds/exclusions log. |
| Per-driver QC CSV (`*_qc.csv` / `flag_summary`) | **ABSENT** | Summary is aggregate-only; no per-frame validity-flag fractions. |
| In-repo canonical CSV | **present** (2.4 KB, 6 rows) | The audited artifact. |
| Figures | **absent in-repo** | Card §5 says dumps stay off-repo; off-repo dir absent → figures unavailable. |
| `wiser/configs/fixed_position_ground_truth.csv` | present | 6 tags; values labelled **"median estimated position (inches)"** — self-derived, not surveyed. |
| Georeference transform | **unverified** (`confirmed:false` / awaiting survey per `ANALYSIS_STATUS.md`) | Inch frame is an unverified offset origin. |

**Driver note.** `analyze_fixed_position_test.py` predates the cohort-appendable migration: it writes to
`wiser/outputs/` and **does not call `make_output_dir` / `write_run_manifest`**, so even had the off-repo
dir survived, this artifact would carry **no manifest tie-back**. The canonical CSV appears to have been
copied/renamed into `results/2026a/wiser_baseline/reports/` without a `run_manifest.json` pointer.

---

## 2. Provenance completeness

| Required key | Present? | Value / note |
|---|---|---|
| `git_commit` (of the producing run) | **NO** | No manifest. Unknown which commit produced the CSV. |
| `generated_utc` | **NO** | No manifest; CSV carries no timestamp. |
| `units` | inferred only | Inches (config + narrative), **not stamped**. |
| `timestamp_method` | **NO** | Driver trims last N min; **N is ambiguous** — code default `DEFAULT_TRIM_MIN=10`, but the card's rerun command uses `--trim-minutes 5`. Which was used for this CSV is unknown. |
| `jitter_floor_in` | not stamped | Must be read back out of the CSV itself. |
| georeference / bounds status | noted | Unverified inch frame; transform absent. |

**WISER-specific provenance gap (record explicitly):** there is **no per-run `measurement_context`
sidecar and no per-row `mc_run_id` stamp**. Rows cannot be joined back to a config-hash manifest;
provenance is **weaker than the CV pipeline** by construction. Additionally there is **no dedicated
`change_log/` entry** for the fixed-position test (the tracker row links the hourly-occupancy plan/README,
not a fixed-position log).

**Config↔run mismatch (reproducibility blocker).** The CSV's accuracy columns record `true_x=0.0,
true_y=0.0` for 4 tags and are **blank** for 2 tags (12386, 12409) — i.e. the run consumed a **4-tag,
zero-placeholder** ground truth. The **current** `fixed_position_ground_truth.csv` holds **6 tags** with
non-zero **self-derived median** positions. The two disagree; without a manifest the run is **not
reproducible** and the accuracy columns cannot be regenerated as-shipped.

---

## 3. QC assessment

**No `flag_summary` is available** (aggregate-only artifact), so per-frame fractions cannot be reported:

| Flag | Fraction | Note |
|---|---|---|
| `low_anchor_flag` (anchors_used < 4) | **unavailable** | Driver does **not** call `add_validity_flags`. |
| `gap_flag` | **unavailable** | Not applicable to a static bench test, but also not computed. |
| `jump_flag` (raw speed > 200 in/s) | **unavailable** | For a *stationary* tag a "jump" = a position glitch; **unfiltered here**, so glitch frames inflate p90/p95/RMS. |
| `outside_provisional_bounds` | **unavailable** | — |
| `after_tag_cutoff` | n/a | Static test; but note 12409=Sova (cut 2026-06-29) and 12380=Hypnos (cut 2026-07-09) as tag devices, not animals. |
| `valid` (composite) | **unavailable** | — |
| `calculation_error`, `battery_voltage` | **loaded-but-ungated** (general WISER gap) | Not even loaded by this driver. |

**Consequence:** the reported floor is a **RAW, all-frames** jitter (only the last-N-minutes trim is
applied). It includes any low-anchor and glitch frames that downstream analyses filter out
(`anchors_used ≥ 4`, some ≥ 6). So this is a **conservative raw envelope**, likely a slight *over*-estimate
of achievable post-QC precision; downstream drivers that filter harder may sit at or below it. n_frames per
tag (469,688–503,584) are recorded but **no duration** → the **"~3.7–3.9 Hz" sampling-rate claim is not
verifiable from this artifact** (it is sourced from the notebook/reference, not this CSV).

---

## 4. Stratification

The usual regime axes are **not applicable / not available** for a static baseline artifact — and that
absence is itself a scope limiter (the floor was measured **without** the regimes that matter downstream):

- **By validity flags:** not possible (no per-row flags in the artifact).
- **By `night_covariates` (wet_ground / tunnel_present / sova_removed):** N/A — this is a stationary-tag
  bench characterization, not a behavioral night.
- **By weather window:** **unknown** — the weather during the fixed-position test is not recorded. The
  floor is therefore characterized under *unknown* (likely dry/benign) conditions and **does not bound
  precision under rain / wet ground**, which raise UWB noise and dropout.
- **By the wet-hay-wall dropout regime:** N/A here, and **critically not covered** — the floor says nothing
  about precision or dropout at the bottom-right ~1-inch hay-wall refuge.
- **By georeference-confirmed status:** unverified inch frame throughout.
- **Proximity ≥ 1 m:** the floor is what *sets* the ≥1 m rule; sub-1 m spatial differences remain below it.

**Available strata — by tag (shortid→name) and by placement cluster:**

| shortid | name | n_frames | std_x (in) | std_y (in) | rms_jitter (in) | jitter p50 | p95 | error stats? |
|---|---|---|---|---|---|---|---|---|
| 12378 | Siesta | 478,214 | 4.27 | 6.52 | **7.94** | 3.05 | 15.27 | vs (0,0) |
| 12380 | Hypnos | 469,688 | 4.37 | 6.35 | **7.86** | 3.39 | 15.71 | vs (0,0) |
| 12386 | Nox | 501,088 | 4.03 | 5.02 | **6.45** | 3.88 | 12.50 | **BLANK** |
| 12395 | Sen | 474,720 | 4.50 | 5.54 | **7.21** | 3.19 | 15.57 | vs (0,0) |
| 12407 | Dormi | 500,710 | 4.26 | 5.16 | **6.75** | 3.34 | 13.79 | vs (0,0) |
| 12409 | Sova | 503,584 | 4.11 | 5.47 | **6.87** | 4.10 | 13.38 | **BLANK** |

- **Cross-tag precision is homogeneous** (RMS 6.4–7.9 in; no outlier tag) → the floor is a stable device/system
  property, not a per-tag quirk.
- **Two placement clusters** (left ≈ x 421–424, right ≈ x 613–619; all y ≈ 727–737) show **similar precision**
  → floor is consistent across the two tested spots. But **only two nearby locations (both y≈730) were
  characterized** — no coverage of edges, corners, or shelter interiors.
- **Anisotropy:** `std_y` (5.0–6.5) is consistently ~20–50 % larger than `std_x` (4.0–4.5). This is a real
  per-axis pattern **but its physical direction is meaningless until georeferenced** (see §5) — the scalar
  radial floor is what survives.

---

## 5. Classification of each finding, with frame-gating

### Finding A — Stationary jitter / precision floor → **MEASUREMENT-SUPPORTED (precision)**
```
Result:              Stationary UWB position precision (jitter floor), fixed-position test
Tag(s):              6 tags (12378/12380/12386/12395/12407/12409), placed static; shortid ≠ animal
Jitter floor / rate: RMS ~6.4-7.9 in (median ~7); radial p50 ~3.4 in; p95 ~12.5-15.7 in; 2-D only (z=0);
                     rate ~3.7-3.9 Hz NOT verifiable in this artifact
QC filters:          NONE applied (raw, all frames; only last-N-min trim) -> conservative raw envelope
Frame status:        inches, UNVERIFIED offset origin (no georeference)
Spatial claim survives frame?  YES for the SCALAR radial floor (rotation/translation-invariant);
                     NO for the per-axis anisotropy (std_y>std_x direction is frame-orientation-dependent)
Dropout / gap:       N/A (static test); weather during test UNKNOWN -> floor not bounded under rain/dropout
Reliability:         sets the >=1 m proximity rule and ~7 in ROI buffer; sub-floor differences = noise
Behavior vs artifact: precision property of the sensor, not behavior
Category:            (1) behavioral / [X] measurement-supported precision floor / (3) mixed / (4) invalid
```
The `_jitter_stats` reference centre is each tag's **own median**, so RMS/percentiles are genuine
repeatability. This is the load-bearing, downstream-relevant result and it is sound — with the raw/unfiltered,
two-location, weather-unknown, 2-D caveats above. The tracker's "~7 in median" is best stated precisely as
**RMS ≈ 7 in / radial p50 ≈ 3.4 in / p95 ≈ 15 in** (a report-promotion wording fix; the reference doc already
notes "measured p50 ~3.4").

### Finding B — Accuracy / bias / error columns → **MEASUREMENT ARTIFACT (not interpretable)**
The CSV records `true_x=0.0, true_y=0.0`; `_error_stats` then returns `bias = mean − 0 = mean` and
`error = radial distance from (0,0)`. The ~843–964 in "errors"/"bias_mag" are literally each tag's distance
from the frame origin (e.g. 12407: √(424.26²+729.51²) ≈ 843.9 = reported bias_mag). **These columns do not
measure accuracy and must be ignored / relabelled.** They do not survive frame-gating (⛔ georef).

### Finding C — Absolute accuracy / "surveyed ground truth" → **INTERPRETATION-LIMITED / UNSUPPORTED (⛔ georef)**
`summaries/wiser_baseline.md` and the card say "vs **surveyed** ground truth". There is **no survey**: the
config ground truth is the WISER **median of the same data** (self-referential → any correctly-merged bias
would be ≈ mean−median ≈ 0–1.5 in **by construction**, still not accuracy), and the run used (0,0)
placeholders. Absolute accuracy is **entirely unestablished**; no WISER position can be placed physically
until the pole survey confirms the inch→field transform. **The "surveyed ground truth" wording is inaccurate
and should be corrected.**

### Finding D — Ground-truth completeness → **PROVENANCE/QC GAP**
2 of 6 tags (12386 Nox, 12409 Sova) carry **no** error stats (absent from the run-time GT); the run consumed
a 4-tag zero-placeholder GT that mismatches the current 6-tag config → not reproducible without a manifest.

### Finding E — Sampling rate ~3.7–3.9 Hz → **NOT IN ARTIFACT (lower confidence)**
No duration/rate column; the claim is inherited from the notebook/reference, not this CSV.

---

## 6. Frame-gating summary (the #1 spatial blocker)

- **Survives the unverified inch frame:** the **scalar radial precision floor** (RMS, radial percentiles) —
  a spread is invariant to origin and rotation. This is why the floor is usable as a *relative* resolution
  bound (proximity ≥1 m, ROI jitter buffer, speed noise floor).
- **Does NOT survive:** absolute positions (`mean_x/y`, `median_x/y`), the two-cluster geometry, the per-axis
  **anisotropy direction** (rotation-dependent), and **every accuracy/bias/error number** (⛔ blocker until a
  pole survey confirms `wiser_to_field_transform.json`).

---

## 7. What this result DOES and does NOT license

**Licenses (downstream):** treat two WISER positions differing by less than the floor as indistinguishable;
keep proximity/social-distance thresholds **≥ 1 m**; use a **~7 in** ROI jitter buffer; set the speed noise
floor; discount sub-floor spatial "changes" as jitter. As a **raw** floor it is conservative — post-QC data
is at least this good.

**Does NOT license (single most important):** **absolute accuracy or physical/georeferenced placement.**
Precision ≠ accuracy. A stationary tag can report positions that cluster tightly (~7 in) around a point that
is itself offset from the true location by an **unknown, unbounded** amount — nothing here measures that
offset (no survey, self-derived GT, error columns computed vs origin). The ~7 in must **never** be
restated as "±7 in of the true/physical location", and no directional/physical claim (wall-running, "the NE
refuge", cross-frame CV comparison) may lean on this result until the georeference survey passes QC.

Secondary non-licenses: it does not bound precision under **rain / wet-ground / wet-hay-wall dropout**
(untested regimes); it does not characterize **vertical (z)** precision (z=0 throughout); it does not, by
itself, establish the **sampling rate**.

---

## 8. Recommendation — smallest next action (no re-fit/re-tune)

1. **Relabel/scope, don't recompute (wording fix).** Correct `summaries/wiser_baseline.md` + the card:
   drop "surveyed ground truth"; state "**precision floor only; no independent survey; the accuracy/bias/error
   columns are a (0,0)-placeholder artifact and are not accuracy**." State the floor as *RMS ≈ 7 in / p50 ≈
   3.4 in / p95 ≈ 15 in, raw/unfiltered, 2 locations, 2-D*. The precision row stays **✅ confirmed for
   precision**; the **accuracy sub-claim is a ⛔ blocker** pending survey. (These are follow-up doc edits, not
   this audit.)
2. **Close the reproducibility gap.** Re-emit this artifact through `make_output_dir` / `write_run_manifest`
   so it carries `git_commit`, `generated_utc`, `units`, `timestamp_method`, `trim_minutes`, `jitter_floor_in`;
   and reconcile the run-time ground truth with the committed `fixed_position_ground_truth.csv` (or drop the
   accuracy columns entirely, since the GT is self-derived).
3. **Provenance (the real limiter):** **design/build a WISER `measurement_context` sidecar + per-row
   `mc_run_id` stamp mirroring the CV pattern** — a follow-up PR, not part of this audit.
4. **To ever get accuracy:** run the **pole-dwell georeference survey** (`scripts/georeference_wiser.py`) — the
   same P0 ⛔ blocker — which supplies an *independent* surveyed truth **and** the inch→field transform; only
   then can true bias/accuracy and physical placement be computed. Optionally add validity-flag QC to the
   fixed-position driver to report a post-QC floor alongside the raw one.

---

## 9. Sibling handoff (CV)

**No CV handoff needed for this baseline.** This is a static UWB device characterization — nothing here turns
on "is the rat inside the shelter" or "is this a huddle". Handoff to `cv-measurement-auditor` becomes relevant
only when a *downstream* WISER spatial/occupancy claim needs shelter-interior confirmation (the existing
bridge is `wiser/scripts/analyze_sleep_site_cv_crossval.py`; WISER is the fog-immune reference, CV resolves
huddles WISER cannot — the check runs both ways).

---

## Appendix — machine-readable audit record

```json
{
  "schema_version": "wiser_measurement_audit/1.0",
  "auditor": "wiser-measurement-auditor",
  "targets": [
    "results/2026a/wiser_baseline/reports/wiser_baseline_fixed_position_summary_2026a.csv"
  ],
  "generated_utc": "2026-07-12",
  "audit_git_commit": "084d4c2e83fc2e27b1fcba4f05f75ffd1e1142e1",
  "verdict": "partially auditable / weaker provenance than CV",
  "strata": [
    {"name": "precision_floor_all_tags_raw_unfiltered_2D", "n": 2928004,
     "metrics": {"rms_jitter_in_range": [6.45, 7.94], "rms_jitter_in_median": 7.04,
                 "radial_p50_in": 3.4, "radial_p95_in_range": [12.50, 15.71],
                 "std_x_in_range": [4.03, 4.50], "std_y_in_range": [5.02, 6.52],
                 "z_tracked": false, "sampling_hz_in_artifact": false},
     "classification": "measurement-supported (precision)"},
    {"name": "accuracy_bias_error_columns", "n": 4,
     "metrics": {"true_xy_used": [0.0, 0.0], "error_in_range": [843.9, 963.9],
                 "meaning": "radial distance from frame origin, not accuracy"},
     "classification": "likely measurement artifact"},
    {"name": "absolute_accuracy_surveyed_ground_truth", "n": 0,
     "metrics": {"independent_survey": false, "ground_truth_source": "self-derived WISER median",
                 "georeference_confirmed": false},
     "classification": "interpretation-limited / lower-bound only (unsupported)"},
    {"name": "ground_truth_completeness", "n": 6,
     "metrics": {"tags_with_error_stats": 4, "tags_blank": ["12386", "12409"],
                 "config_run_mismatch": true},
     "classification": "provenance/QC gap"}
  ],
  "failure_modes": [
    "accuracy/bias/error computed against a (0,0) placeholder ground truth -> distance-from-origin, not accuracy",
    "config ground truth is self-derived (WISER median 'median estimated position') -> circular; no independent survey",
    "raw/unfiltered jitter (no add_validity_flags) -> p90/p95/RMS inflated by unfiltered glitch frames; a conservative envelope",
    "only 2 nearby locations (both y~730) and unknown weather characterized -> floor not bounded near edges/shelters or under rain/wet-hay-wall dropout",
    "2-D only (z=0 throughout) -> no vertical precision",
    "config/run mismatch (6 self-derived tags now vs 4 zero-placeholder tags then) -> accuracy columns not reproducible",
    "sampling-rate ~3.7-3.9 Hz not verifiable from this artifact"
  ],
  "provenance_gaps": [
    "off-repo WISER run dir ABSENT (only cv_field_harvest present)",
    "no run_manifest.json (git_commit/generated_utc/units/timestamp_method/jitter_floor_in unstamped)",
    "no filtering_log.txt; no per-frame flag_summary (low_anchor/gap/jump/valid unavailable)",
    "no per-run measurement_context sidecar and no per-row mc_run_id stamp (weaker than CV)",
    "driver predates migration: no make_output_dir / write_run_manifest; no manifest tie-back",
    "no dedicated change_log entry for the fixed-position test",
    "trim ambiguity: code default 10 min vs card rerun --trim-minutes 5",
    "calculation_error / battery_voltage loaded-but-ungated (general WISER gap; not loaded here)"
  ],
  "smallest_next_action": "Relabel (drop 'surveyed ground truth'; mark the accuracy/bias/error columns a (0,0)-placeholder artifact; state floor as RMS~7in / p50~3.4in / p95~15in, raw, 2 locations, 2-D). Keep precision ✅ confirmed; accuracy stays ⛔ pending the pole-dwell georeference survey. Follow-up PR: build a WISER measurement_context sidecar + per-row mc_run_id mirroring CV. Do NOT re-fit.",
  "sibling_handoff": "None for this baseline (static UWB characterization). cv-measurement-auditor only for downstream shelter-interior / huddle questions via analyze_sleep_site_cv_crossval.py."
}
```
