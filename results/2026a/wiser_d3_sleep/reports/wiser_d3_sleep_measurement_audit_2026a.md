# WISER Measurement-Context Audit — `wiser_d3_sleep` (cohort 2026a)

**Auditor:** `wiser-measurement-auditor` (WISER Measurement-Context Auditor)
**Target direction:** `wiser_d3_sleep` — Direction 3, daytime/diel rest-site organization
**Cohort / window:** 2026a · 5 tags {12378 Siesta, 12380 Hypnos, 12386 Nox, 12395 Sen, 12407 Dormi} · 2026-06-28 → 2026-07-08 (11 days, 55 rat-days/nights)
**Audit git commit:** `084d4c2` (repo state 2026-07-12) · **generated_utc:** 2026-07-12 (live `date`/`python` blocked by an env-drive hook; timestamp taken from `git`)
**Schema:** `wiser_measurement_audit/1.0`
**Scope:** read-only. This audit changes no tracker, config, DB, or pipeline output. It rules on **whether each derived number is interpretable as a measurement**, and where it is not.

> **Vocabulary** (reused from `wiser/ANALYSIS_STATUS.md`): ✅ confirmed · ⚠️ candidate · ⛔ blocker. **Per-finding measurement classes:** `measurement-supported` (state/topology, survives the current WISER measurement) · `candidate-biological` (an interpretation not yet established) · `not-separable` (confound the design cannot break) · `lower-bound-only` (dropout/censoring means the number is a floor, not a value).

---

## 0. Overall verdict

**Partially auditable / weaker provenance than CV.** This is the largest and most measurement-disciplined block in the WISER tree: the 11 in-repo reports already carry the correct caveats — rest = low-speed proxy at the jitter ceiling, unverified inch frame, ambient-temperature proxy, burrow/dropout lower bounds, and dropout guards. The **measurement statements the reports make are sound and their gating is, on the whole, correctly applied.** What keeps the verdict below CV-level confidence is **provenance**, not misinterpretation:

- The off-repo bulk run dirs (`D:\Field2026_analysis_out\2026a\<name>_<ts>\`) that hold the per-run `run_manifest.json`, `filtering_log.txt`, and the per-driver QC CSVs (`nightly_qc.csv`, `daytime_qc.csv`, `site_dwell_vs_temperature.csv`, `within_trunk_changepoints.csv`, …) are **ABSENT** (only `cv_field_harvest` remains under `2026a\`). The in-repo `run_manifest.json` is a **pointer** manifest (cohort/direction/artifact-root), **not** the per-run provenance manifest. So `git_commit`, `generated_utc`, `timestamp_method`, and the numeric `flag_summary` fractions **cannot be re-verified** from the tracked artifacts.
- The WISER side has **no `measurement_context` sidecar and no per-row `mc_run_id` stamp** (unlike the CV pipeline). Rows cannot be joined back to a config-hash manifest. This is the structural reason the whole direction is weaker-provenance than CV.

Net: **the state/topology results are measurement-supported and auditable from report prose + canonical CSVs quoted therein; the biological labels (sleep, thermoregulation, circadian mechanism, physical refuges) are candidate; the run-level provenance is not independently reconstructable and is the binding limiter.**

---

## 1. Run-directory resolution

- **Supplied / resolved run root:** in-repo canonical reports at `results/2026a/wiser_d3_sleep/reports/` (13 report files) + one pointer `results/2026a/wiser_d3_sleep/run_manifest.json`.
- **Off-repo bulk runs:** the pointer manifest names 8 source run folders (`biological_day_sleep_20260711_1515`, `direction3_heat_gated_relocation_*`, `sleep_site_hierarchy_20260711_2004`, `circadian_rest_20260709_1051`, `direction3_temperature_relocation_20260709_1143`, `direction3_evening_morning_sleep_20260709_2338`, `night_consolidated_rest`, `sleep_site_cv_crossval_*`). **All ABSENT** under `D:\Field2026_analysis_out\2026a\` (verified: only `cv_field_harvest` present).
- **Degraded-gracefully statement:** *No per-run `run_manifest.json` / `filtering_log.txt` / QC CSV was found for any D3 driver. This audit is based on the in-repo canonical reports + the canonical-results MD/JSON prose + the linked `change_log/` entries + `ANALYSIS_STATUS.md`.* The reports do embed their own definitions, thresholds, and dropout guards, so the measurement context is recoverable from prose even though the machine-readable per-run provenance is not.
- **Data source (read-only, compliant):** the canonical-results file names the static snapshot `1stcohort_2026_2026-07-09.sqlite` ("a snapshot file, not the live WAL writer") and the cross-val used `1stcohort_2026_2026-07-01.sqlite`. No live-WAL access is implied. ✅ read-only discipline honored.

---

## 2. Provenance completeness

| Provenance key | Present / verifiable from in-repo artifacts? | Note |
|---|---|---|
| `git_commit` (per run) | **NO** | lives in off-repo per-run manifest (absent) |
| `generated_utc` (per run) | **NO** | off-repo; reports carry only human dates |
| `units` (inches) | ✅ yes | stated in every report + canonical results |
| `timestamp_method` | **partial** | weather↔WISER = "wall-clock UTC, unverified ±5 min"; NVR clock = UTC−5; no per-run `timestamp_method` key recoverable |
| `jitter_floor_in` (~7 in, p95 ~15) | ✅ yes | stated in every report; θ_rest = **12.46 in/s** consistent across all 11 files |
| georeference / bounds status | ✅ noted, and **⛔ unverified** | `wiser/configs/wiser_to_field_transform.json` **ABSENT** (verified) → frame stays unverified inches |
| `measurement_context` sidecar (per run) | **NO — WISER has none** | structural gap; no CV-style sidecar exists |
| per-row `mc_run_id` stamp | **NO — WISER has none** | rows cannot be joined to a config-hash manifest |

**Provenance verdict:** units, jitter floor, and frame status are fully documented; per-run `git_commit`/`generated_utc`/`timestamp_method` and the numeric QC fractions are **not independently reconstructable** because the off-repo runs are gone and there is no WISER measurement-context sidecar. **This is the weaker-provenance-than-CV finding, and it is first-class, not a footnote.**

---

## 3. QC assessment (`flag_summary`)

The per-row validity vocabulary (`low_anchor_flag`, `gap_flag`, `jump_flag`, `outside_provisional_bounds`, `after_tag_cutoff`, composite `valid`) is produced by `add_validity_flags`/`flag_summary`, but the **CSVs carrying those fractions are off-repo and absent**, so numeric flag fractions **cannot be reported for this run**. What is auditable:

- **Dropout guards ARE embedded in the reports** (the QC that matters most for D3):
  - `temperature_relocation`: per-animal daytime dropout table — **≈0.0 on every full day**; the only >25% animal-days are the five 06-28 partial-day (release ~19:25) rows, correctly flagged "expected, not signal loss."
  - `evening_morning`: **0** morning animal-days >25% dropout; a gap is treated as "unknown, never a relocation."
  - `biological_day`: 5 rat-days >25% trunk dropout flagged lower-confidence; change-point median 13.4 h (≤25% dropout) vs 13.5 h (all) — timing survives the dropout filter.
  - `night_consolidated_rest`: coverage-guarded (≥20 fixes/bin else `unknown`).
- **`gap_flag`/`jump_flag`/`low_anchor_flag`/`valid` fractions: NOT AVAILABLE** (off-repo). Lower-confidence on the QC axis by absence, not by evidence of a problem.
- **QC gap (loaded-but-ungated):** `calculation_error` and `battery_voltage` are loaded by the read-only loader but **never gated** in any driver. Neither appears in any D3 report's QC. Flag as a standing provenance/QC gap — a low-battery or high-`calculation_error` fix passes into the rest/site/emergence statistics unflagged.

---

## 4. Stratification (the finding kept separable from the sensor path)

| Stratum axis | Status for D3 |
|---|---|
| **tag (shortid→name)** | {12378 Siesta, 12380 Hypnos, 12386 Nox, 12395 Sen, 12407 Dormi}. **Sova (12409) is NOT in the D3 cohort** and its 06-29 15:00 cutoff is irrelevant here. **Hypnos (12380) cutoff 2026-07-09 03:35 is AFTER the 07-08 window end → D3 unaffected by `after_tag_cutoff`.** ✅ tag-cutoff exposure is clean. |
| **validity flags** | fractions unavailable (off-repo); dropout guards embedded and clean (§3). |
| **night_covariates** (`wet_ground`/`tunnel_present`/`sova_removed`) | `tunnel_1` valid only through 06-29 07:00 (present 06-28 only); `sova_removed` from 06-29 15:00 (not a D3 tag); `wet_ground` handled per-night as a covariate on **both** the animal and UWB-dropout paths (not regressed out). ✅ |
| **georeference-confirmed status** | ⛔ **UNVERIFIED** — transform file absent. ROIs are confirmed **in the inch frame only** (membership works); physical/directional placement does not. |
| **jitter floor (proximity ≥1 m)** | No sub-floor proximity/social-distance claim is made in D3. Displacement thresholds used (100 in change-point ≈14×, 203 in median step ≈29×, 36 in relocation ≈5×, 30 in "stable" ≈4× jitter) all sit **above** the ~7 in floor. ✅ |
| **weather windows** | AWN ambient, wall-clock UTC ±5 min unverified; treated as a covariate, never an aligned trigger. ✅ |
| **wet-hay-wall → burrow dropout regime** | **Superseded/clarified:** `change_log/2026-07-07-shelter4-burrow-removed.md` establishes `refuge_4` dropout is the **burrow** (tag below the anchor plane) — **structural, weather-INDEPENDENT, persistent within the 07-03→07-07 dig window** — which *supersedes* the earlier "wet hay-wall attenuates UWB" framing carried in the skill reference. D3's dropout regime is the burrow, not a wet-wall. |

---

## 5. Per-finding classification

Each finding maps to the enforced measurement statement it must respect. "State/topology" = ROI-membership + relative displacement in the confirmed inch-frame ROIs (survives). "Physical/directional/thermal/sleep" = gated by the unverified frame and/or the missing physiology.

### F1 — REST is a low-speed proxy at the jitter CEILING → the central limiter *(measurement statement (a))*
- **Enforced statement — CONFIRMED in the reports.** θ_rest = **12.46 in/s** is the p99 of the stationary tag's smoothed speed, i.e. the jitter **ceiling**: anything slower than ~1 ft/s (sitting, grooming, slow foraging) reads as "rest." The circadian report states this verbatim ("overcounts true sleep and compresses the diel swing... an ACTIVITY-onset rhythm, not a sleep depth"). Every report labels rest a low-**movement** proxy, NOT ephys/CV-scored sleep.
- **Classification:** the REST metric is **measurement-supported as a low-speed / activity proxy** (and, for absolute levels, a **lower-bound-on-activity / over-count-of-sleep**). The **"sleep" label is candidate-biological, NOT established** (no ephys, no interior CV). Absolute rest levels (0.92 day / 0.86 night) are **not** interpretable as sleep amount; only the relative shape is.
- **Ruling:** PASS. This is the direction's central risk and it is correctly and repeatedly gated. Do not let any downstream reader upgrade "rest" to "sleep" or read "amplitude" as "sleep depth."

### F2 — Circadian / diel rhythm SHAPE *(measurement statement (b))*
- **Is the SHAPE measurement-supported even though the "sleep" label is not? — YES.** The **phase** (activity-fraction peak at **21:00 on all 11 biological nights**, spread 0 h, anchored at the 07:00 trough) and the **diel shape** (dusk peak, midday trough, narrow between-rat SEM) are a within-animal speed-threshold-crossing rhythm with **coverage ≥0.5 every hour** (dropout-guarded), and **no spatial claim is made**, so the unverified frame does not bite. These are **measurement-supported**.
- The **~2.5× active-fraction swing** is measurement-supported **as a ratio/shape but is a compressed LOWER BOUND** on the true swing (the ceiling flattens it).
- **Candidate / not-separable:** (i) the "sleep"/"sleep depth" reading of amplitude — candidate-biological; (ii) endogenous circadian clock vs entrained/novelty habituation — **not separable** (one cohort, one release event); (iii) day-to-day active-amount vs midday temperature (ρ=−0.53/−0.48) — **candidate + not-separable** (hot days fell early → temperature confounded with day-in-sequence; reports say exactly this); (iv) rain suppression — **not-separable / null** (wet-dry gap confounded, acute DiD CI −8.6…+43.4 spans 0).
- **Ruling:** PASS. Shape/phase measurement-supported; absolute label and mechanism candidate; amount-vs-weather not separable.

### F3 — Site precision, multi-site topology, home-base hierarchy *(measurement statement (c))*
- **Measurement-supported (state/topology):** multi-site dwell composition (house_1 0.512, house_2 0.334, **~85% two houses**, unconditional, sums to 1); relocations mean **3.1/rat-day**, **spread across the day — NOT a ~10:00 switch** (change-point median 13.5 h, 11% within ±1 h; state-sequence 13.4 h, 8%); the change-point steps are 100–203 in ≈14–29× jitter (clean, not noise); the **home-base hierarchy** (house_1 top anchor+terminal, KL=0.33 **p<0.001**; net sinks vs peripheral sources; diurnal ordering std 1.9 h **p=0.001**; **Kendall W=0.79 p<0.001**); stable **individual** primary-house and mobility. These are ROI-membership + relative-displacement claims in the inch-frame-confirmed ROIs and survive the current measurement.
- **⛔ frame-gated / NOT licensed:** any statement that **house_2 is physically cooler**, that "out" destinations are cooler/shaded, or any compass/physical placement ("northeast refuge", "wall side"). The reports **explicitly do not** make these — house_2 "not verified cooler" is stated repeatedly. ✅
- **Candidate / not-separable:** the within-rat temperature correlations (doorway ρ=+0.58, water_2 +0.38, exposed −0.31, house_1 +0.17, house_2 −0.19, any-shelter −0.44). **Candidate-biological**: ambient (not in-shelter) temp, uncorrected multiple comparisons, rat-centering only (does not model shared day-level exposure or day-since-release), doorway/exposed jitter-adjacent, and weather drives **both** the animal and the UWB-dropout paths. The any-shelter −0.44 is partly driven by the interpretation-limited refuge_4/tunnel (reports flag this).
- **Ruling:** PASS. Topology measurement-supported; "house_2 cooler" correctly **not claimed**; temperature association candidate.
- **Note (stale internal inconsistency, not a report defect):** `ANALYSIS_STATUS.md` still lists a ⛔ row "`wiser_rois.json` unconfirmed (`confirmed=false`)". Per the skill reference and `change_log`, the ROIs + boundary have since been placed `confirmed:true` **in the inch frame** (membership works); the **georeference transform** is the part still missing. The D3 reports rely only on inch-frame ROI membership, which is legitimate; the tracker row is out of date and could mislead a reader into thinking ROI membership itself is unconfirmed.

### F4 — refuge_4 burrow = UWB-dropout LOWER BOUND *(measurement statement (d))*
- **Do the reports flag the refuge_4-dominant windows? — YES, thoroughly.** `temperature_relocation` names all **11 refuge_4-dominant animal-windows** (07-03→07-07) and rules them "burrow-entrance behaviour + a UWB-dropout lower bound... never daytime sleep." `evening_morning` excludes 2 via `burrow_flag`. `biological_day`/canonical mark refuge_4 (dwell 0.054) interpretation-limited, exclude it from the **110 interpretable** relocations, and discount the burrow-window transition-matrix rows. `heat_gated` excludes refuge_4+tunnel from both enclosed and out. `circadian` notes "a rat in the refuge_4 burrow reads as dropout, not rest."
- **Classification:** refuge_4-dominant windows = **lower-bound-only / measurement artifact (dropout)**, correctly isolated. All house_1/house_2 headline reads are burrow-independent.
- **One residual gap to flag:** `night_consolidated_rest` **counts refuge_4 (and tunnel) as "enclosed shelter"** and reports 9 CRBs in refuge_4. Because the burrow is weather-independent dropout, a mid-night "consolidated rest bout" whose centroid classifies to refuge_4 inside 07-03→07-07 can be a **dropout artifact counted as rest**, and it feeds the "93% in a shelter" headline. Small in magnitude (≈9/137 bouts) but it is the one place in the direction where the burrow is treated as a rest site rather than a lower bound. **Recommend** the CRB analysis apply the same refuge_4 burrow-window exclusion the daytime analyses use.

### F5 — Heat-peak dispersal / heat-gated house-leaving *(measurement statement (e))*
- **Measurement-supported (descriptive gate):** P(out of enclosed-house ROI) is flat ~4–6% below ~30 °C and steps to ~0.27–0.34 above ~32 °C; the **within-day** contrast (each hot rat-day its own control) gives ΔP(out) = **+0.27, day-clustered 95% CI [+0.22, +0.32]**, positive on all 4 gate-crossing days; the **matched clock-hour** control gives midday P(out) 0.32 (hot) vs 0.03 (cold). Because this is ROI-membership + a within-day/matched-hour design that removes day-in-sequence AND circadian confounds, with thresholds above the jitter floor, the **descriptive gate is measurement-supported.** This is genuinely stronger than the older `temperature_relocation` "9/10-day dispersal, not separable" framing, which it supersedes for the descriptive claim.
- **Candidate / not-separable (mechanism):** that the gate is **thermoregulation** is candidate — **ambient** (not in-shelter) temp, "out" destinations **unverified** (not shown cooler), threshold rests on only **4 hot days**, the per-bin instantaneous *trigger* was the weakest piece. The design removes *sequence* and *circadian* confounds but does **not** separate "leaves because hot" from a social or habit co-driver at the destination, nor confirm the destinations are cooler. **Thermal vs social vs habit is not fully separable** — as required by statement (e).
- **Ruling:** PASS. Descriptive gate measurement-supported; thermoregulation mechanism candidate; the ~32 °C location is approximate (4 hot days); day-clustered bootstrap (not per-rat sign test) is the honest inference — reports state this.

### F6 — WISER↔CV sleep-site cross-validation *(measurement statement (f))*
- **Enforced reading — CONFIRMED against the change log.** Mapping A confirmed (joint κ 0.66 on 6/29–6/30 pre-binning-fix), best joint lag **~0 s** on the ±4.5 h scan, **alignment adequate** (±1 h fine sweep flat). The correct read is **CV precision ≈ 1.0 / recall ≈ 0.49–0.64 per shelter = a LOWER BOUND** (wall-edge blind zone; the CH05 recall gap is on **clear** glass, so it is a geometric blind zone, not optical failure). The **joint κ = 0.20** (07-02 rerun) must **NOT** be read as sensor disagreement: it is a **base-rate / kappa-paradox artifact + a WISER-ROI-vs-CV-inside definition mismatch**, **not** misalignment and **not** biological disagreement. WISER is the fog-immune reference; CV catches huddles WISER cannot resolve. The check runs both ways — never assume agreement.
- **Classification:** the **alignment** result is **measurement-supported**; **CV occupancy is a per-shelter lower bound**; the κ=0.20 is **not a valid disagreement metric** and licenses no "the sensors disagree" claim.
- **⚠️ Documentation/provenance gap:** unlike the other seven D3 findings, the cross-val has **no in-repo canonical report** under `results/2026a/wiser_d3_sleep/reports/`. Its numbers live only in `ANALYSIS_STATUS.md`, `change_log/2026-07-02-sleep-site-cv-crossval.md`, and the off-repo (absent) `outputs/audit/ALIGNMENT_DIAGNOSIS_2026-07-02.md`. The one cross-modal check that could partially validate "in shelter" is the **least-promoted** artifact in the tree. Also note the older 6/29–6/30 κ (0.66/0.68–0.82) **predate the `[ns]` pandas binning fix** and are flagged for re-confirmation — so even the "confirmed mapping" number is provisional pending a clean-glass rerun.

---

## 6. Frame-gating summary (the ⛔ blocker)

⛔ **Every spatial/directional/physical claim in D3 is gated on the unverified inch frame** (`wiser_to_field_transform.json` absent; `confirmed:false` by absence) until a pole survey passes QC (`scripts/georeference_wiser.py`). What survives vs what does not:

- **Survives (inch-frame ROI membership + relative displacement):** which ROI an animal rests in; dwell composition; relocation counts/timing; home-base sink/source ordering; within-day house-leaving gate; individual house preference; the diel activity rhythm (no spatial claim). These are measurement-supported.
- **Blocked until georeference:** house_2 (or any "out" ROI) being physically **cooler/shaded**; any compass/physical placement; any "toward-cool" directional gradient; turning the temperature correlates into a microclimate-choice claim. The reports **do not** cross this line. ✅

---

## 7. Failure modes catalogued

1. **Off-repo run provenance absent** → per-run `git_commit`/`generated_utc`/`timestamp_method` and numeric `flag_summary` fractions not reconstructable; QC auditable only via the dropout guards embedded in prose.
2. **No WISER `measurement_context` sidecar / no per-row `mc_run_id`** → rows cannot be joined to a config-hash manifest; provenance structurally weaker than CV.
3. **REST = jitter-ceiling low-speed proxy** → over-counts true sleep, compresses the diel swing; absolute rest levels are not sleep amount; "sleep" is a candidate label throughout.
4. **refuge_4 burrow = weather-independent UWB dropout** (07-03→07-07) → lower-bound, never sleep; correctly excluded in the daytime analyses, but **included as "shelter" in `night_consolidated_rest`** (9/137 CRBs) — a residual over-count.
5. **Ambient-temperature proxy, no shelter thermistor** → all thermal readings (heat gate, doorway/water dwell, night-rest humidity) are candidate; weather acts on **both** the animal and the UWB-dropout paths, so it cannot be regressed out.
6. **Unverified inch frame** → no physical/directional/"cooler" claim; the georeference ⛔ blocker binds the microclimate mechanism.
7. **Small-N / confounded thermal designs** → heat gate rests on 4 hot days (threshold approximate); circadian amount-vs-temp confounded with day-in-sequence; night-rest humidity candidate is uncorrected, ambient, n=5×11.
8. **`calculation_error` / `battery_voltage` loaded-but-ungated** → low-quality fixes can enter rest/site/emergence stats unflagged.
9. **CV cross-val under-promoted + partly pre-binning-fix** → the one cross-modal validator has no in-repo report and its confirmed-mapping κ predates the binning fix (re-confirm needed).
10. **Stale ⛔ ROI-unconfirmed tracker row** → `ANALYSIS_STATUS.md` still says `wiser_rois.json confirmed=false` though ROIs are placed `confirmed:true` in the inch frame; risks a reader under-trusting legitimate ROI-membership results (or conflating them with the still-missing georeference).

---

## 8. What this direction does NOT license

- ❌ Any claim of **sleep** (state or depth) — only low-movement rest; not ephys/CV-validated.
- ❌ Reading the diel **amplitude** as **sleep depth**, or the absolute rest fractions (0.92/0.86) as sleep amount — only the **phase/shape** (21:00 activity peak, dusk-onset, midday trough) is measurement-supported.
- ❌ **house_2 (or any ROI) being physically cooler/shaded**, or any directional/physical placement — ⛔ frame unverified.
- ❌ **Thermoregulation** as an established mechanism — the heat gate is a measurement-supported *descriptive* gate; the *cause* is candidate (ambient temp, unverified/unmeasured destinations, 4 hot days).
- ❌ Counting **refuge_4-dominant (07-03→07-07)** windows as rest/sleep or as "relocation to a refuge" — burrow + dropout **lower bound only**.
- ❌ Reading **κ = 0.20** as WISER↔CV disagreement — it is a base-rate/definition-mismatch artifact; alignment is adequate and CV occupancy is a per-shelter **lower bound**.
- ❌ A **~10:00 site switch**, a **binary house_1/house_2** state space, a stable **"house-rat vs floater"** trait, a structured **there-and-back** excursion, or a **rain** effect on activity/morning-site — each is explicitly withdrawn or shown not-separable in the reports.
- ❌ Any **weather-as-nuisance** regression — weather drives dropout *and* behavior; it stays a covariate on both paths.

---

## 9. Recommendation (smallest next action)

**Provenance is the binding limiter, so the primary recommendation is the standard one:** design/build a WISER **`measurement_context` sidecar + per-row `mc_run_id` stamp** mirroring the CV pattern (a follow-up PR, not part of this audit), so future D3 runs are joinable to a config-hash manifest and QC fractions survive off-repo pruning. **No re-fit / re-tune is recommended** — the findings are already correctly stratified and the numbers are not the problem.

Secondary, cheap, in-scope-for-a-follow-up:
1. **Promote the WISER↔CV cross-val into `results/2026a/wiser_d3_sleep/reports/`** as a canonical report (it is currently only in the tracker + change log), and re-run it on clean-glass days to replace the pre-binning-fix κ.
2. **Apply the refuge_4 burrow-window exclusion in `night_consolidated_rest`** (align it with the daytime analyses) so the burrow is a lower bound there too.
3. **Update the stale `ANALYSIS_STATUS.md` ⛔ "`wiser_rois.json confirmed=false`" row** to reflect inch-frame ROI confirmation (georeference transform is the remaining ⛔).
4. **Gate `calculation_error` / `battery_voltage`** in the D3 drivers, or document why they are safely ungated.

To move the **candidate biological labels** to confirmed (out of this audit's scope): interior shelter video (CH07/CH08, installed 07-07) to validate the rest proxy and recover the true ~18:00 in-nest arousal; a shelter thermistor to turn ambient temperature into microclimate; and the pole survey to lift the ⛔ frame blocker.

---

## 10. Sibling handoff → `cv-measurement-auditor`

Three D3 sub-questions turn on things **UWB cannot answer** and should be routed to `cv-measurement-auditor` (shelter cameras see inside when the glass is clear):
- **Is the low-movement animal actually *inside* the shelter (vs a jitter-adjacent doorway/exposed classification)?** — a CV interior-view question; the existing bridge is `wiser/scripts/analyze_sleep_site_cv_crossval.py` (WISER = fog-immune reference, CV = interior view).
- **Is a "consolidated rest bout" / a shelter dwell cluster a HUDDLE?** — WISER cannot resolve co-location into a huddle; CV can (and WISER head-counts already read as a lower bound vs CV `n_inside`).
- **Is the low-movement proxy actually rest/sleep vs quiet wakefulness/grooming?** — interior CV (CH07/CH08) is the validator WISER lacks.

The check runs **both ways**: on wet/foggy days WISER is the more reliable sensor (CV false-empties through degraded glass + the wall-edge blind zone), so `cv-measurement-auditor` should treat WISER shelter presence as the fog-immune reference there. Never assume the two agree.

---

## Appendix — machine-readable audit record

```json
{
  "schema_version": "wiser_measurement_audit/1.0",
  "auditor": "wiser-measurement-auditor",
  "targets": [
    "results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_SCIENTIFIC_SUMMARY_2026a.md",
    "results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_biological_day_canonical_results_2026a.md",
    "results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_biological_day_report_2026a.md",
    "results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_biological_day_scientific_summary_2026a.md",
    "results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_circadian_rest_2026a.md",
    "results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_circadian_rest_SCIENTIFIC_SUMMARY_2026a.md",
    "results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_night_consolidated_rest_2026a.md",
    "results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_night_consolidated_rest_SCIENTIFIC_SUMMARY_2026a.md",
    "results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_evening_morning_2026a.md",
    "results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_heat_gated_relocation_2026a.md",
    "results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_heat_gated_relocation_SCIENTIFIC_SUMMARY_2026a.md",
    "results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_site_hierarchy_2026a.md",
    "results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_temperature_relocation_2026a.md"
  ],
  "generated_utc": "2026-07-12",
  "audit_git_commit": "084d4c2",
  "verdict": "partially auditable / weaker provenance than CV",
  "strata": [
    {"name": "F1_rest_proxy_jitter_ceiling", "n": "55 rat-days x ~4Hz", "metrics": {"theta_rest_inps": 12.46, "threshold_type": "p99_stationary_jitter_ceiling"}, "classification": "measurement-supported (as low-speed/activity proxy; lower-bound-on-activity); 'sleep' label candidate-biological"},
    {"name": "F2_circadian_shape_phase", "n": "5 rats x 11 biological nights", "metrics": {"activity_peak_hour": 21, "peak_spread_h": 0, "rest_day": 0.92, "rest_night": 0.86, "active_swing_x": 2.5, "coverage_min": 0.5}, "classification": "shape/phase measurement-supported (swing is a compressed lower bound); sleep-depth candidate; amount-vs-temp not-separable"},
    {"name": "F3_site_topology_hierarchy", "n": 55, "metrics": {"house1_dwell": 0.512, "house2_dwell": 0.334, "two_house_share": 0.847, "relocs_per_ratday": 3.1, "changepoint_median_h": 13.5, "within_1h_of_10": 0.11, "anchor_KL": 0.33, "kendall_W": 0.79}, "classification": "measurement-supported (topology); 'house_2 cooler'/physical placement blocked (unverified frame); temp-correlates candidate-biological"},
    {"name": "F4_refuge4_burrow_lower_bound", "n": "11 daytime windows + 9 CRBs", "metrics": {"refuge4_dwell": 0.054, "burrow_window": "2026-07-03..2026-07-07", "interpretable_relocations": 110}, "classification": "lower-bound-only (weather-independent burrow dropout); correctly excluded in daytime analyses; included-as-shelter in night_consolidated_rest = residual gap"},
    {"name": "F5_heat_gated_relocation", "n": "4 gate-crossing days / 10 analyzed", "metrics": {"gate_C": 32, "dP_out_withinday": 0.27, "ci_low": 0.22, "ci_high": 0.32, "midday_Pout_hot": 0.32, "midday_Pout_cold": 0.03, "rats_responding": "4/5"}, "classification": "descriptive gate measurement-supported (within-day + matched-hour design); thermoregulation candidate-biological; thermal-vs-social-vs-habit not-separable"},
    {"name": "F6_wiser_cv_crossval", "n": "2 shelters, 6/29-6/30 + 07-02 rerun", "metrics": {"cv_precision": 1.0, "cv_recall_low": 0.49, "cv_recall_high": 0.64, "best_lag_s": 0, "joint_kappa_2sensor": 0.20, "confirmed_mapping_kappa": 0.66}, "classification": "alignment measurement-supported; CV occupancy per-shelter lower-bound; kappa=0.20 NOT disagreement (base-rate/definition-mismatch); under-promoted + pre-binning-fix numbers need re-confirm"}
  ],
  "failure_modes": [
    "off-repo run provenance absent (no per-run manifest/QC CSVs; only cv_field_harvest present)",
    "no WISER measurement_context sidecar and no per-row mc_run_id stamp -> weaker than CV; rows unjoinable to config-hash manifest",
    "REST is a jitter-ceiling (12.46 in/s) low-speed proxy -> over-counts sleep, compresses diel swing; 'sleep' unvalidated",
    "refuge_4 burrow = weather-independent UWB dropout lower bound; included as shelter in night_consolidated_rest (9/137 CRBs)",
    "ambient-temperature proxy (no shelter thermistor); weather drives both animal and UWB-dropout paths",
    "unverified inch frame -> no physical/directional/'cooler' claim (georeference transform absent)",
    "thermal designs thin/confounded (heat gate 4 hot days; circadian amount-vs-temp confounded with day-in-sequence)",
    "calculation_error and battery_voltage loaded-but-ungated",
    "CV cross-val under-promoted (no in-repo report) and confirmed-mapping kappa predates the [ns] binning fix",
    "stale ANALYSIS_STATUS row still marks wiser_rois.json confirmed=false though ROIs are placed in the inch frame"
  ],
  "provenance_gaps": [
    "per-run git_commit / generated_utc / timestamp_method not reconstructable (off-repo runs absent)",
    "flag_summary fractions (low_anchor_flag/gap_flag/jump_flag/outside_provisional_bounds/after_tag_cutoff/valid) unavailable in-repo",
    "no measurement_context sidecar; no per-row mc_run_id",
    "in-repo run_manifest.json is a pointer, not the per-run provenance manifest",
    "weather->WISER alignment wall-clock UTC unverified (+/-5 min); NVR clock UTC-5 (cross-val)"
  ],
  "smallest_next_action": "Build a WISER measurement_context sidecar + per-row mc_run_id stamp mirroring the CV pattern (follow-up PR). No re-fit/re-tune. Secondary: promote+rerun CV cross-val into results/reports; apply refuge_4 burrow exclusion in night_consolidated_rest; refresh stale ROI-confirmed tracker row; gate calculation_error/battery_voltage.",
  "sibling_handoff": "cv-measurement-auditor for: (1) is the animal actually INSIDE the shelter vs jitter-adjacent doorway/exposed; (2) is a rest cluster a HUDDLE; (3) is the low-movement proxy rest/sleep vs quiet wake (interior CV CH07/CH08). Bridge = analyze_sleep_site_cv_crossval.py; WISER is the fog-immune reference, check runs both ways."
}
```
