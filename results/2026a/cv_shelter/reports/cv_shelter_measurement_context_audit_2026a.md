# Measurement-Context Audit — Shelter CV Outputs (CH05 / CH06)

**Audit date:** 2026-07-06 · **Scope:** existing outputs in `cv/outputs/`
**Detectors:** `rat_feasibility-6` (current, 2026-07-04, val mAP50 0.876) and `rat_daynight` (original, pre-fine-tune)
**Annotation link:** `mc_run_id = mc_778385804fb9` · sidecar `outputs/audit/measurement_context_audit.measurement_context.json` · git `6c703c5`

> **This is a MEASUREMENT audit only.** It asks *whether detector errors cluster under certain optical /
> view regimes*, so numbers can be stratified before pooling. It makes **no** behavioral or causal claim, and
> **no** weather-causes-behavior claim. All annotation is **additive-only** — detector, view-quality, motion,
> count, state, safety, thresholds, and filtering are untouched.

## 0. What exists to audit — and what does not
- **Sleep bins:** CH05/CH06 for **2026-06-29** (LEGACY 6-column schema → *regime-blind*, no `view_quality`) and
  **2026-06-30** (current 15-column schema).
- **Validation (ground truth):** `validation_2026-06-30.csv` (original detector) + `..._rescored_rat_feasibility-6.csv`
  (current detector). 59 human-labeled samples, detector hidden while labeling.
- **No outputs exist for 2026-07-01 … 07-03.** → The `lift_1cm`, `antifog_film`, and `bare_seated_post_film`
  optical regimes **cannot be audited**. This is the single biggest gap: the `antifog_film` span (07-02 13:00 →
  07-03 11:00) is the one the observer reported made the view *worse than bare glass*, and there is no CV output
  under it.
- The pre-existing **sleep CSVs carry no recorded detector version / config** — precisely the provenance gap
  `measurement_context` now closes for future runs.

## 1. Do the new per-row fields populate correctly? — ✅ YES
| Output | `camera_model` | `shelter_id` | `glass_regime` | `mc_run_id` |
|---|---|---|---|---|
| CH05_sleep_2026-06-29 *(legacy)* | RLC-520A | left | bare ×1700 | mc_778385804fb9 |
| CH05_sleep_2026-06-30 | RLC-520A | left | bare ×240, tape ×80 | mc_778385804fb9 |
| CH06_sleep_2026-06-29 *(legacy)* | RLC-520A | right | bare ×1703 | mc_778385804fb9 |
| CH06_sleep_2026-06-30 | RLC-520A | right | bare ×80 | mc_778385804fb9 |
| validation_2026-06-30 | RLC-520A | left, right | tape ×42, bare ×17 | mc_778385804fb9 |
| validation_2026-06-30_rescored | RLC-520A | left, right | tape ×42, bare ×17 | mc_778385804fb9 |

`camera_model`/`shelter_id` resolve from `field_layout.json` (correct house mapping: CH05→left, CH06→right).
`glass_regime` resolves from `glass_treatments.yaml` (06-30 correctly splits `bare`<09:00 / `tape`≥09:00).
Legacy 06-29 files still get camera + glass + `mc_run_id`, but remain **regime-blind for view** (no `view_quality`).

## 2. Are row counts + existing metric columns unchanged? — ✅ YES (additive only)
Every file: **row count identical**, **every existing column byte-identical**, only **9 covariate columns added**
(`glass_regime, glass_layers, glass_uncertain_layers, glass_time_precision, glass_confounded, glass_regime_note`,
`camera_model, shelter_id, mc_run_id`). Rows: 1700→1700, 1703→1703, 320→320, 80→80, 59→59.

## 3. Where do errors cluster? — stratified (validation ground truth, current detector `rat_feasibility-6`)
**SAFETY invariant (unchanged):** degraded/unusable scored `occupied_high_motion` = **0/14 → PASS**.

**By view quality** — errors concentrate sharply in **degraded** view:
| view | n | presence-recall | count MAE | bias | miss | under | over |
|---|---|---|---|---|---|---|---|
| clear | 45 | **78%** | 0.76 | −0.13 | 8 | 16 | 10 |
| degraded | 14 | **29%** | 0.50 | −0.50 | 5 | 6 | **0** |

**By glass regime** — *confounded with view, do not interpret as a treatment effect:*
| regime | n | presence-recall | degraded-rate | note |
|---|---|---|---|---|
| bare | 17 | 38% | **71%** (12/17) | pre-09:00 window ⇒ contains the 03:00–07:00 pre-dawn fog |
| tape | 42 | 77% | **5%** (2/42) | daytime ⇒ almost all clear |

→ The `bare` vs `tape` recall gap tracks the **fog/time-of-day** split (bare 71% degraded vs tape 5%), **not** the
aluminum-tape treatment. On this single day glass-regime and view-quality are collinear, so no treatment effect is
separable. (This is the textbook sensor-path confound the regime layer exists to expose.)

**By camera / shelter:**
| camera | shelter | n | presence-recall | count MAE | bias |
|---|---|---|---|---|---|
| CH05 | left | 24 | 74% | **1.08** | −0.25 |
| CH06 | right | 35 | 65% | 0.43 | −0.20 |

→ CH05 carries larger count errors (bigger huddles/higher counts on the left house); CH06 lower MAE but lower
recall. **Caveat:** `CH06_zones.json` does not exist → CH06 uses the calibration-quad fallback as its `inside`
zone, itself a measurement-context difference between the two cameras.

**Original detector for context** (`rat_daynight`): clear recall 28%, degraded 14% — uniformly worse; the
fine-tune's gain is concentrated in **clear** view (28%→78%), while **degraded** view stays poor (14%→29%) — a
hard optical floor the detector alone does not fix.

## 4. Interpretation (measurement audit — NOT behavioral)
Per the required regime-aware categories:
- **Degraded-view recall collapse (78%→29%)** → *category 2: measurement artifact.* Missed rats under degraded
  glass are a sensor-path failure, not fewer animals.
- **`bare` vs `tape` recall gap** → *category 3: mixed / ambiguous.* Fully confounded with pre-dawn fog; the glass
  treatment cannot be isolated on one day.
- **All shelter counts** → *category 4: lower bound only.* Wall-edge blind zone; a visible count is not a headcount.
- No weather/glass→behavior claim is made anywhere here.

## 5. Per-run sidecar ↔ row `mc_run_id` — ✅ links cleanly
`outputs/audit/measurement_context_audit.measurement_context.json` exists; its `mc_run_id` (`mc_778385804fb9`)
equals the single value stamped on every annotated row; it records detector `rat_feasibility-6`, git `6c703c5`,
config fingerprints, and the per-camera block. *(This `mc_run_id` is the **audit back-annotation** id — the
original outputs predate the layer; future pipeline runs will each carry their own genuine `mc_run_id`.)*

## 6. Failure modes remaining + targeted next steps (labeling by regime/failure mode)
1. **Degraded/fog-view misses** — the dominant remaining error (recall 29% under degraded). Attack with
   **foggy/degraded-view frames** and, once available, **post-anti-fog-film frames** — see (3).
2. **CH05 huddle undercount** (MAE 1.08, negative bias) — label **huddle-heavy CH05 frames**.
3. **Biggest measurement gap: no CV outputs under the `lift_1cm` / `antifog_film` / `bare_seated_post_film`
   regimes.** Process the 2026-07-01…07-03 CH05/CH06 footage through `shelter_sleep.py` so error-clustering under
   the film regime (reported *worse-than-bare*) can actually be measured. Until then, any film-era claim is unaudited.
4. Redraw **`CH06_zones.json`** so CH06's `inside` zone isn't a calibration-quad fallback.

## Definition of done — met
Every CV-derived shelter number now carries `camera_model` + `shelter_id` (what camera / which house),
`glass_regime` (+layers/precision/confounded), the existing `view_quality`/`weather_logged`/reliability columns,
and `mc_run_id` → its full provenance sidecar. The layer is **additive-only** (row counts and all existing metrics
unchanged), and errors are now stratifiable by camera / shelter / view-quality / glass-regime — which immediately
surfaced the fog-vs-tape confound and the degraded-view floor.
