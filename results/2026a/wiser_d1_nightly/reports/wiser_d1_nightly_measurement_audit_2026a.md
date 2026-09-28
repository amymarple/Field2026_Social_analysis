# WISER Direction-1 (nightly) — Measurement-Context Audit · cohort 2026a

- **Auditor:** `wiser-measurement-auditor` (WISER Measurement-Context Auditor)
- **Targets:** `wiser_d1_nightly` claims from `wiser/ANALYSIS_STATUS.md` rows *"Nightly movement (habituation vs rain)"* + *"Nightly behavior & social"* + the 11-night consolidation, and their change logs `2026-06-30-nightly-progression.md`, `2026-06-30-nightly-behavior.md`, `2026-07-10-d1-d2-eleven-day-consolidation.md`.
- **Drivers audited (read-only, not run):** `wiser/scripts/analyze_nightly_progression.py`, `wiser/scripts/analyze_nightly_behavior.py`.
- **generated_utc:** 2026-07-13T (see run-time git); **repo HEAD:** `084d4c2` (committed 2026-07-12T22:50:40-04:00).
- **This file is a MEASUREMENT AUDIT, not a promoted canonical scientific result.** It does not upgrade any status or promote any finding. Direction 1 still has **no promoted canonical report** (see status gap below).

> **Verdict (headline): PARTIALLY AUDITABLE / WEAKER PROVENANCE THAN CV — and, for this run, weaker than a normal WISER run.** The per-run QC that the claims depend on (`nightly_qc.csv` `valid_frac`/`gap_frac`, `weather_night_summary`, `night_covariates`, `rain_did`) is **absent on disk**, so the numbers were audited **at the level of the change-log-reported values only**. Their internal QC/flag fractions are currently **un-verifiable**. The *reasoning* in the tracker is measurement-honest; the *evidence chain* cannot be re-walked from artifacts.

---

## 1. Run-directory resolution & provenance completeness

| Item | Expected | Found | Status |
|---|---|---|---|
| In-repo canonical report | `results/2026a/wiser_d1_nightly/reports/*.md` | **empty — no report existed** (only this audit now) | ⛔ **STATUS GAP** — the only direction of 7 with no promoted report (baseline/d2/d3/policy/cv_shelter/crossmodal all have `reports/`) |
| In-repo `run_manifest.json` | provenance manifest | **pointer stub only** — `cohort`, `direction`, `bulk_run_dir_pattern`, `migrated_from_old_repo_runs`, `note` | ⚠️ present but **not a provenance manifest** |
| `git_commit` / `generated_utc` / `units` / `timestamp_method` / `jitter_floor_in` in that manifest | all present | **all ABSENT** | ⛔ provenance keys missing |
| Off-repo bulk run dir | `D:\Field2026_analysis_out\2026a\{nightly_progression,nightly_behavior}_<ts>\` | **ABSENT** (only `cv_field_harvest\` exists under `2026a\`) | ⛔ raw run provenance gone |
| `filtering_log.txt` | thresholds/exclusions | **ABSENT** (off-repo dir gone) | ⛔ |
| Per-driver QC CSVs (`nightly_qc.csv`, `nightly_rates.csv`, `night_split_rates.csv`, `rain_did.csv`, `weather_night_summary.csv`, `wet_vs_dry_by_night.csv`, `nightly_social.csv`, `nightly_graph_*`) | present | **ABSENT** | ⛔ cannot read a single QC/flag fraction |
| Georeference transform `configs/wiser_to_field_transform.json` | present + `confirmed:true` | **ABSENT** | ⛔ frame unverified (active cross-cutting blocker) |
| `configs/rat_identities.csv` | present | present | ✅ 5-rat core resolved (below) |

**Degrade-gracefully note:** No usable run manifest and no QC CSVs were found in any search root (in-repo `results/`, off-repo `$FIELD2026_ANALYSIS_OUT_ROOT/2026a/`). Per protocol this audit **continues on the change-log + tracker + analyses-card claims only** and marks every QC-dependent conclusion **lower-confidence**.

**Tag → animal (paired core, resolved via `rat_identities.csv`; `shortid` ≠ animal):**
Siesta `12378` · Sen `12395` · Dormi `12407` · Nox `12386` · Hypnos `12380`. Sova `12409` removed 2026-06-29 15:00 EDT (excluded from all D1 nights). Hypnos cutoff 2026-07-09 03:35 EDT — **all 11 nights end before it**, so D1 is unaffected. `tunnel_1` ROI present **06-28 only**.

**WISER-specific provenance gap (mandatory record):** the WISER side has **no per-run `measurement_context` sidecar** and **no per-row `mc_run_id` stamp**. Even if the off-repo run existed, rows could not be joined back to a config-hash manifest the way the CV pipeline's can. Provenance is **genuinely weaker than CV** by construction, and here it is further degraded to *absent*.

---

## 2. QC / flag assessment — REQUIRED FRACTIONS UNAVAILABLE

The workflow requires reporting `flag_summary` fractions (`low_anchor_flag / gap_flag / jump_flag / outside_provisional_bounds / after_tag_cutoff / valid`) and per-night `valid_frac`/`gap_frac`. **None can be reported**: `nightly_qc.csv` and the raw run are absent. This is itself a finding — the wet-vs-dry contrast (Claim 2) is explicitly documented as *"must be read against `nightly_qc.csv valid_frac`"*, and **that CSV does not exist on disk**, so the confound-control the authors describe cannot be independently verified.

Generic loaded-but-ungated QC gap (carries here): `calculation_error` and `battery_voltage` are loaded by the read-only loader but **never gated** by `add_validity_flags`. A low-battery / high-error tag-night could pass `valid` today. Unquantifiable without the run.

---

## 3. Per-claim measurement classification

Vocabulary: role 4-way (**behavioral · artifact · mixed/ambiguous · lower-bound**) mapped to the caller's 3-way (**measurement-supported · interpretation-limited · not-separable**). Metric of record for movement is `active_distance_m_per_valid_hour` (active path above the ~7 in / 12.5 in-s noise floor ÷ valid tracked time) — **rate-normalized by valid time** (corrects *random* dropout) but **jitter-inflated in absolute terms** (relative/paired only) and **not corrected for spatially-biased dropout** (the wet-hay-wall regime).

| # | Claim (change-log value) | Role class | Caller class | Basis / limiter |
|---|---|---|---|---|
| C1 | **Habituation decline** 229→152 m/valid-hr (11 n); first **dry→dry** drop 06-28→06-29 **−50%** (229→115), all 5 rats | **mixed/ambiguous — behavioral core** | **measurement-supported (relative, dry→dry step); interpretation-limited (full-sequence magnitude)** | The 06-28→06-29 step is **dry→dry** (both nights), paired, unanimous across 5 rats → the cleanest piece: **not** a rain-dropout artifact. Rate-normalization handles random dropout. **Absolute "m" is jitter-inflated** (not physical). Full 11-night magnitude is *not* dropout-clean: later nights include 5 wet nights whose **hay-wall dropout biases active distance downward**, mimicking further habituation; un-verifiable (no `valid_frac`). |
| C2 | **Wet-vs-dry** 122 (wet) vs 164 (dry) m/valid-hr | **mixed/ambiguous → measurement artifact-suspect** | **NOT-SEPARABLE** | The tracker itself flags confounded. Three stacked confounds: wet nights are **late-sequence** (habituation position), **low-N/uneven** (5 wet nights), and rain **raises UWB dropout** (sensor path) — including **spatially-biased hay-wall dropout** a scalar `valid_frac` cannot remove. Cannot attribute the gap to rain-behavior vs rain-sensor vs sequence. **Not a measurement of a rain effect.** |
| C3 | **Within-night DiD**, 06-30 22:30 rain burst: **+19.9 [95% CI −8.6, +43.4]**, CI spans 0 | **lower-bound (underpowered null)** | **measurement-supported as a null, but interpretation-limited by power** | Best design here (within-night, per-rat, matched-clock controls → removes sequence + time-of-night). Point estimate is **positive** (movement rose) — *opposite* to the direction dropout-suppression would fake, so the non-suppression is **robust to the dropout-suppression artifact**. But CI is wide at **n=5**, and the 22:30 split rides on **±5 min unverified weather↔WISER alignment** blurring pre/post. Licenses *"no evidence of acute rain suppression at n=5,"* **not** *"rain has no effect."* |
| C4 | **Overall: rain vs habituation not separable** | — | **NOT-SEPARABLE (correctly stated)** | A measurement-honest limitation, not a result. Wet nights are structurally confounded with sequence position; the design cannot separate them. Correct as written. |
| C5 | **Settling:** home/shelter 0.07→0.15; **outside movement 246→174** m/valid-hr; active fraction 0.16→0.08 | **mixed/ambiguous — behavioral direction robust** | **measurement-supported (direction); interpretation-limited (magnitude)** | Direction is **robust to the dominant artifact**: hay-wall shelter dropout would *under*-count home and *over*-count outside — i.e. it biases **against** "home↑/outside↓," so the true settling is if anything stronger. Relative paired trend; absolute jitter-inflated. Home-fraction magnitude is occupancy-noisy (jitter buffer on a ~36×27 in footprint; `food_1/2` sit inside `house_1/2` → some "transitions" are jitter flips). |
| C6 | **Graph settles:** distinct edges 37→27 (simplifies); night-to-night **edge-cosine 0.50→0.81** (stabilizes); occupancy similarity 0.84→0.70 | **mixed/ambiguous** | **measurement-supported (edge-cosine stabilization); interpretation-limited (raw edge count)** | Night-to-night self-similarity of the ROI-transition graph works **in the inch frame** (ROI membership confirmed there) — no georeference needed. **Edge-cosine stabilization after night 1** is the robust piece. **Raw edge simplification 37→27 is partly a structural artifact:** `tunnel_1` exists **06-28 only**, so tunnel edges vanish for a **layout** reason, not behavior; plus jitter-flip edges. |
| C7 | **Social proximity** ≤1 m 0.14→0.13 ("reliable; 7 in floor ≪ 1 m"); mean pairwise dist 190→171→184 in | **behavioral, but effectively flat** | **measurement-supported at ≥1 m (null/flat); sub-1 m FORBIDDEN** | 1 m (39.4 in) sits **above** the ~√2×7≈10 in combined two-tag jitter → the ≤1 m bin is legitimately above-floor, and the analysis correctly kept the threshold ≥1 m. Pairwise **distance is metric in inches** (the frame's unknown is origin/orientation, not scale), so distance claims survive the frame. **But the change is ~flat** → licenses *"no detectable proximity change,"* not a social change. **Any ≤0.5 m bin is below floor and must not be interpreted.** |
| C8 | **Geometry:** coverage 0.59→0.54; corridor cells 2481→2131 (space-use narrows) | **mixed/ambiguous → artifact-suspect** | **interpretation-limited (dropout-confounded)** | Grid coverage / corridor-cell counts are **fix-count sensitive** and not obviously per-valid-hour normalized: fewer fixes on later/wet nights (more dropout) shrink visited-cell counts for a **sensor** reason. Cannot separate "settling" from "fewer fixes" without `gap_frac` (absent). |

---

## 4. Frame-gating notes (⛔ georeference blocker)

The georeference transform `wiser_to_field_transform.json` is **absent** → the inch frame stays an **unverified offset origin frame** (`load_field_transform` is a no-op). **None of the D1 claims make a directional or physical-placement claim** (no "north refuge," no wall-running, no "toward water") — they are scalar rates, ROI-occupancy fractions (membership valid in the confirmed inch frame), night-to-night graph similarity, pairwise **distances** (metric in inches), and grid coverage. **Because D1 avoids directional/positional claims, the ⛔ blocker does not by itself invalidate these numbers.** However:

- The moment "home use ↑ / outside ↓" is narrated as a **physical location** ("retreat to the northern shelter," "move toward shade/water"), it becomes **⛔-gated** until a pole survey confirms the georeference.
- "Home" is a **label** on refuge-type ROIs, not a verified biological home; ROI names are provisional pending the survey.
- Absolute "m" and "in" distances are **jitter-inflated / relative-only**; do not report them as physical magnitudes.

---

## 5. Confound / dropout limiters (the separability story)

1. **Weather is a covariate on BOTH paths, not a nuisance to regress out.** Rain/wet ground raises UWB **dropout** (sensor) *and* changes **behavior** (animal). The wet-vs-dry contrast (C2) therefore cannot be cleaned by subtracting weather.
2. **Wet-hay-wall dropout regime (spatially-biased).** The bottom-right ~1-in hay-wall refuge loses UWB when wet/white → the low-rank rat's shelter fixes drop out → occupancy **under**-counts and "time outside" **over**-counts on wet nights. A scalar `valid_frac` normalization does **not** remove this spatial bias. It pushes C1/C2 (active distance) and C8 (coverage) toward *lower* on wet nights, and biases *against* C5 (so C5's direction is safe, its magnitude is not). A signal gap here is **unknown**, never "the rat left."
3. **Sequence–weather collinearity.** Wet nights (06-30, 07-01, 07-03, 07-05, 07-06) sit **late** in the habituation sequence → rain and "days-since-release" are collinear; **not separable at n=5, single cohort**.
4. **Small n.** 5 rats paired; 3 nights (original) / 11 nights (consolidation); only 5 wet / 3 rain-in-window nights. Adequate for a **paired within-subject direction** test (C1, C5), weak for **between-night weather contrasts** (C2, C3).
5. **±5 min weather↔WISER alignment** blurs the 22:30 DiD split (C3) and every `wet_ground`/`rain_in_window` label.
6. **Active distance is a lower bound on locomotion** — the moving-threshold classifier is above the noise floor, so in-nest stirring is invisible; do not read "less active" as "resting/asleep."

---

## 6. What these nightly claims do NOT license

- **NOT** a rain **effect** on nocturnal movement (C2 confounded; C3 an underpowered null). Do not state "rats move less when it rains."
- **NOT** any **physical/directional** statement — no "retreat to shelter X," "move toward water/shade," wall-running, thigmotaxis. ⛔ until georeferenced.
- **NOT** sub-1 m or **dyadic fine** social-distance claims (below the ~7 in / combined ~10 in floor). ≥1 m only.
- **NOT** absolute distances/speeds as **physical** quantities (jitter-inflated; paired/relative only).
- **NOT** "rest/sleep" from low active distance (that is D3's proxy question; active distance is a lower bound).
- **NOT** a **mechanism** for the habituation decline (novelty vs weather vs maturation not separated; only "declines over sequence").
- **NOT** promotion to **confirmed** — n=5, single cohort, stacked confounds, **and** the status/provenance gaps below. The correct status stays **⚠️ candidate**.
- **NOT** an occupancy claim about the **hay-wall shelter on wet nights** without a dropout guard — that reads as a lower bound, not behavior.

---

## 7. Provenance gaps (machine list)

1. **No promoted in-repo canonical report** for `wiser_d1_nightly` (only direction of 7 lacking `reports/`) — status gap; the candidate numbers live only in change logs.
2. **In-repo `run_manifest.json` is a pointer stub** — missing `git_commit`, `generated_utc`, `units`, `timestamp_method`, `jitter_floor_in`.
3. **Off-repo per-run artifacts absent** (`D:\Field2026_analysis_out\2026a\` holds only `cv_field_harvest`) → `filtering_log.txt` + all QC CSVs (`nightly_qc.csv`, `rain_did.csv`, `weather_night_summary.csv`, `wet_vs_dry_by_night.csv`, `nightly_social.csv`, `nightly_graph_*`) unreadable → **QC/flag fractions and per-night `valid_frac`/`gap_frac` un-verifiable**.
4. **No WISER `measurement_context` sidecar and no per-row `mc_run_id` stamp** — weaker provenance than CV by construction; rows can't be joined to a config-hash manifest.
5. **`calculation_error` / `battery_voltage` loaded but never gated** — a QC gap in `add_validity_flags`.
6. **Georeference transform absent** → inch frame unverified (active ⛔ blocker).
7. **Weather↔WISER alignment ±5 min unverified.**

---

## 8. Sibling handoff — `cv-measurement-auditor`

Two D1 conclusions turn on questions **UWB cannot answer**, and should be cross-checked by the CV auditor / the existing bridge `wiser/scripts/analyze_sleep_site_cv_crossval.py` (WISER = fog-immune reference; CV sees inside the shelter when the glass is clear):

- **C5 "home use ↑ / outside ↓":** is this **real shelter residence** or the **wet-hay-wall dropout artifact**? CH05/CH06 shelter cams can confirm occupancy independently of UWB dropout.
- Any move to interpret "settling" as animals being **inside** a specific shelter (vs a jitter-buffer ROI membership).

The check runs both ways — never assume WISER and CV agree.

---

## 9. Smallest next action (reuse candidate/confirmed/⛔ language)

Provenance is the binding limiter, so — **not** a re-fit/re-tune:

1. **Build a WISER `measurement_context` sidecar + per-row `mc_run_id` stamp mirroring the CV pattern** (follow-up PR, not part of this audit) so future D1 rows join to a config-hash manifest.
2. **Regenerate and PROMOTE the D1 canonical report** (`analyze_nightly_progression.py` + `analyze_nightly_behavior.py`, `--cohort 2026a`) so `nightly_qc.csv` (`valid_frac`/`gap_frac` **per night × per tag**, incl. the low-rank hay-wall tag on wet nights) is on disk and the C2 wet-vs-dry confound flag becomes **independently verifiable**. This is provenance restoration, not a re-fit.
3. **Dispatch `cv-measurement-auditor`** on C5 (home↑/outside↓ vs hay-wall dropout).
4. **Science confound (data-collection, out of scope for this audit):** a 2nd cohort with dry/wet nights **balanced across sequence position** is the only thing that breaks the rain-vs-habituation confound — as the tracker already states.

Until 1–2 land, D1 stays **⚠️ candidate** and its numbers are **partially auditable / lower-confidence**.

---

## 10. Machine-readable summary

```json
{
  "schema_version": "wiser_measurement_audit/1.0",
  "auditor": "wiser-measurement-auditor",
  "targets": [
    "wiser_d1_nightly:nightly_habituation_vs_rain (analyze_nightly_progression.py)",
    "wiser_d1_nightly:nightly_settling_social (analyze_nightly_behavior.py)",
    "change_log/2026-06-30-nightly-progression.md",
    "change_log/2026-06-30-nightly-behavior.md",
    "change_log/2026-07-10-d1-d2-eleven-day-consolidation.md"
  ],
  "generated_utc": "2026-07-13",
  "repo_head": "084d4c2",
  "verdict": "partially auditable / weaker provenance than CV (and, this run, weaker than a normal WISER run: per-run QC CSVs and manifest absent)",
  "strata": [
    {"name": "C1 habituation decline (dry->dry -50%, 229->152)", "n": "5 rats x 11 nights", "metrics": {"first_step_dry_drop_pct": -50, "eleven_night_m_per_valid_hr": "229->152"}, "classification": "mixed_behavioral; measurement-supported relative dry->dry, interpretation-limited magnitude"},
    {"name": "C2 wet-vs-dry 122 vs 164", "n": "5 wet / weather-known nights", "metrics": {"wet": 122, "dry": 164}, "classification": "not-separable (habituation-position + dropout confound; valid_frac unverifiable)"},
    {"name": "C3 within-night DiD 06-30 22:30", "n": 5, "metrics": {"did": 19.9, "ci95": [-8.6, 43.4]}, "classification": "measurement-supported null, interpretation-limited by power (+/-5min alignment)"},
    {"name": "C4 rain-vs-habituation separability", "n": "5x11", "metrics": {}, "classification": "not-separable (measurement-honest limitation)"},
    {"name": "C5 settling home-up/outside-down (246->174)", "n": "5x11", "metrics": {"home_frac": "0.07->0.15", "outside_m_per_valid_hr": "246->174"}, "classification": "mixed_behavioral; measurement-supported direction (hay-wall dropout biases against it), interpretation-limited magnitude"},
    {"name": "C6 graph settles (edge-cosine 0.50->0.81)", "n": "5x11", "metrics": {"edge_cosine": "0.50->0.81", "edges": "37->27"}, "classification": "measurement-supported edge-cosine; interpretation-limited raw edge count (tunnel_1 06-28-only artifact)"},
    {"name": "C7 proximity <=1m 0.14->0.13", "n": "5 pairs", "metrics": {"prox_1m": "0.14->0.13", "mean_pair_dist_in": "190->171->184"}, "classification": "measurement-supported at >=1m (flat/null); sub-1m forbidden below floor"},
    {"name": "C8 coverage/corridor narrowing", "n": "5x11", "metrics": {"coverage": "0.59->0.54"}, "classification": "interpretation-limited (fix-count/dropout confounded)"}
  ],
  "failure_modes": [
    "weather drives BOTH UWB dropout and behavior -> wet-vs-dry not regress-out-able",
    "wet-hay-wall spatially-biased dropout not removed by scalar valid_frac; biases active-distance/coverage down and occupancy-outside up on wet nights",
    "sequence-weather collinearity (wet nights late in habituation sequence)",
    "n=5 single cohort; between-night weather contrasts underpowered; DiD CI spans 0",
    "+/-5 min weather<->WISER alignment blurs 22:30 split and wet_ground labels",
    "raw ROI-graph edge count confounded by tunnel_1 present 06-28 only + jitter-flip edges",
    "absolute distances jitter-inflated (relative/paired only); active distance is a locomotion lower bound"
  ],
  "provenance_gaps": [
    "no promoted in-repo canonical report for wiser_d1_nightly (only direction of 7 missing reports/)",
    "in-repo run_manifest.json is a pointer stub: no git_commit/generated_utc/units/timestamp_method/jitter_floor_in",
    "off-repo per-run artifacts absent (D:/Field2026_analysis_out/2026a has only cv_field_harvest) -> nightly_qc.csv/valid_frac/gap_frac/filtering_log unreadable",
    "no WISER measurement_context sidecar and no per-row mc_run_id stamp (weaker than CV)",
    "calculation_error and battery_voltage loaded but never gated",
    "georeference transform wiser_to_field_transform.json absent -> inch frame unverified",
    "weather<->WISER alignment +/-5 min unverified"
  ],
  "smallest_next_action": "Build a WISER measurement_context sidecar + per-row mc_run_id stamp mirroring CV (follow-up PR); regenerate+promote the D1 canonical report so nightly_qc.csv valid_frac/gap_frac per night x tag is on disk and the wet-vs-dry confound flag is verifiable; then dispatch cv-measurement-auditor on C5. Do NOT re-fit before stratifying. 2nd cohort balanced across sequence position breaks the confound (data collection).",
  "sibling_handoff": "cv-measurement-auditor via analyze_sleep_site_cv_crossval.py -> verify C5 'home-up/outside-down' is real shelter residence vs wet-hay-wall UWB dropout (CH05/CH06 see inside; check runs both ways)"
}
```
