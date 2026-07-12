# WISER Analysis — Status Tracker

> **Migration note (2026-07-12).** This detailed WISER row tracker was carried over from the old
> `Field_2026_Social` repo. For **navigation**, prefer the new layers: [`../analyses/README.md`](../analyses/README.md)
> (per-question cards) · [`../summaries/`](../summaries/) (per-direction narrative) · [`../STATUS.md`](../STATUS.md)
> (cohort × direction board). Reports now live under **`results/<cohort>/<direction>/reports/`** (cohort `2026a`),
> not the old in-repo `outputs/<direction>/`; some inline `outputs/…` links below still name the old layout and
> are kept for historical detail. `../change_log/` links resolve in the new tree.

Living status of the WISER UWB tracking analysis: what is done, what is still a
**candidate** finding, what is a placeholder, and — the main point — **what it takes to
promote the candidate findings to confirmed / publishable results**.

> **Keep this current.** Every row's status must match the verdict in that analysis's
> [`change_log/`](../change_log/) entry. When a candidate is promoted, a placeholder is
> implemented, or a blocker is resolved, update the row here in the same change. This file is
> the single index; the change logs remain the authoritative record of each result.

## Legend

| Mark | Meaning |
|---|---|
| ✅ | done / validated |
| ⚠️ | candidate — exploratory, interpret only with the stated caveat |
| ◻️ | placeholder / stub — not yet implemented |
| ⛔ | blocker — gates scientific interpretation until resolved |

## Data & config inventory

| Item | Path | Status | Caveat that matters |
|---|---|---|---|
| Live tracking DB | `D:\Wiser\data\1stcohort_2026.sqlite` | ✅ live | WAL writer — reads must stay strictly read-only (`mode=ro`, `PRAGMA query_only=ON`) |
| Stationary baseline | `D:\Wiser\data\tag_reports.sqlite` | ✅ validated | Fixed-position test; source of the jitter floor |
| Weather (AWN) | `D:\weather_data\AWN-*.csv` | ⚠️ partial | 6/29 evening sparse; aligned wall-clock UTC only, **±5 min unverified** |
| Rat identities | `configs/rat_identities.csv` | ✅ complete | Two `valid_until` cutoffs (applied by `apply_tag_cutoffs`): **Sova (12409)** removed 2026-06-29 15:00; **Hypnos (12380)** implant dropped **2026-07-09 03:35:41 EDT** (removed 12:15, sac'd) → its WISER data invalid after the drop. Cohort 6→5 (06-29) →4 (07-09). All current results end before 07-09 so are unaffected; only analyses past 07-09 03:35 must exclude 12380. See `FIELD_OBSERVATIONS.md` Day 12 |
| Fixed-position ground truth | `configs/fixed_position_ground_truth.csv` | ✅ validated | Inches; used only for the precision floor |
| ROI definitions | `configs/wiser_rois.json` | ⚠️ placed | ROIs + boundary now `confirmed:true` **in the inch frame** (membership works); still NOT georeferenced to the physical paddock, so directional claims remain unverified. Note `food_1/2` sit inside `house_1/2` → house↔food "transitions" are jitter flips, not travel. **`refuge_4` ("shelter 4") is a BURROW ENTRANCE** (>1 rat, nightly dig ~07-03 01:00; REMOVED 07-07 13:00 → `valid_until` set): its occupancy is a burrow-dropout lower bound (weather-independent), not sleep — but the 06-28→06-30 data **predates** it, so current results are unaffected. `refuge_1/2/3` normal. See `change_log/2026-07-07-shelter4-burrow-removed.md` |
| Exclude regions | `configs/wiser_exclude.json` | ◻️ optional | Absent → 12-in boundary band fallback for thigmotaxis |
| Georeference transform | `configs/wiser_to_field_transform.json` | ◻️ awaiting survey | Tooling ready + self-tested; written `confirmed:true` once a pole survey passes QC (see next steps P0) |

## Pipeline stages

Ordered per the `AGENTS.md` field-data workflow.

| Stage | Component(s) | Status |
|---|---|---|
| Raw registration | `src/wiser_io.py` (CSV/TSV/SQLite, fuzzy columns) | ✅ |
| Schema validation | `wiser_io.py` → canonical `shortid, ts_raw, x, y, z` | ✅ |
| Timestamp normalization | `src/time_utils.py` (Unix-ms/s, ISO auto-detect) | ✅ |
| Sync / alignment | weather↔WISER wall-clock UTC merge (`wiser_analysis_utils.load_weather*`) | ⚠️ unverified ±5 min |
| QC | jitter floor, validity flags (`metrics.py`, `add_validity_flags`) | ✅ |
| Derived data | `wiser_analysis_utils.py` (~3000 L: speed, ROI, social, route, follow, nightly) | ✅ built |
| Analysis notebook | `notebooks/wiser_pilot_analysis.ipynb` (§A–J) | ✅ |
| Figures / reports | `src/plotting.py` + per-script figure sets | ✅ |
| Change log | seven entries in [`change_log/`](../change_log/) | ✅ |

## Analysis inventory

| Analysis | Driver | Status | Key finding | Gating caveat | Records |
|---|---|---|---|---|---|
| Fixed-position precision | `scripts/analyze_fixed_position_test.py` | ✅ | Jitter floor ~7 in (18 cm); ~3.7–3.9 Hz | Precision only; not absolute accuracy | [plan](../implementation_plan/2026-06-28-hourly-occupancy-maps.md) · README |
| Hourly occupancy maps | `scripts/plot_hourly_occupancy.py` | ✅ | Live-DB-safe per-hour scatter/heatmaps | In-progress hour never plotted | [plan](../implementation_plan/2026-06-28-hourly-occupancy-maps.md) · [log](../change_log/2026-06-28-hourly-occupancy-maps.md) |
| Daily backup | `scripts/backup_wiser_daily.py` | ✅ | Snapshot + gz incremental to E: | One live-DB read/run (~0.74 s) | (recording DB backup — excluded; see [`PARKED_ITEMS.md`](../PARKED_ITEMS.md)) |
| Pilot analysis (QC-first) | `notebooks/wiser_pilot_analysis.ipynb` | ✅ | ~1.03M fixes, 96.7% valid; §A–J | Exploratory sections labeled in-notebook | [plan](../implementation_plan/2026-06-29-wiser-pilot-analysis.md) · [log](../change_log/2026-06-29-wiser-pilot-analysis.md) |
| Route structure | `scripts/analyze_route_structure.py` | ⚠️ | Corridors robust to QC; straightness real vs displacement-matched null. **11 nights (2026-07-10):** cross-rat edge sim 0.90 > within-rat 0.35 → shared-environment | Night-to-night IoU only ~27%; **WISER frame unverified** | [plan](../implementation_plan/2026-06-29-route-structure-analysis.md) · [log](../change_log/2026-06-29-route-structure-analysis.md) · [11-day](../change_log/2026-07-10-d1-d2-eleven-day-consolidation.md) |
| Leader-follower / route-following | `wiser_analysis_utils` + notebook §J | ⚠️ | 22/30 pairs above circular-shift null. **Fireworks (07-04, 2026-07-12):** following bursts (21:30 z=2.4, 22:20 z=5.2 vs matched-clock controls) are acoustically TIME-LOCKED to the fireworks (CH01/CH02 mics, r≈0.35 lag0); rain does NOT raise following (07-04 dry per AWN; wet nights follow less). Following-vs-startle-co-flight unresolved → 96-episode video watch-list staged | Weak short-lag/asymmetry; single session → candidate. Fireworks: n=1 night, clock unverified, construct needs video | [plan](../implementation_plan/2026-06-29-leader-follower-analysis.md) · [log](../change_log/2026-06-29-leader-follower-analysis.md) · [fireworks](../change_log/2026-07-12-fireworks-following-audio.md) · [report](outputs/following_incidents_2026-06-28_to_2026-07-08/FIREWORKS_FOLLOWING_REPORT.md) |
| Nightly movement (habituation vs rain) | `scripts/analyze_nightly_progression.py` | ⚠️ | −50% active distance 6/28→6/29 (both dry). **11 nights (2026-07-10):** habituation 229→152 m/valid-hr; per-night `wet_ground`/`rain_in_window` classification; wet-vs-dry 122 vs 164 **confounded** (read vs `valid_frac`); 6/30 DiD CI spans 0 | Rain vs habituation **not separable** — wet nights late-sequence + low-N + raise dropout; n=5 | [plan](../implementation_plan/2026-06-30-nightly-progression.md) · [log](../change_log/2026-06-30-nightly-progression.md) · [11-day](../change_log/2026-07-10-d1-d2-eleven-day-consolidation.md) |
| Nightly behavior & social | `scripts/analyze_nightly_behavior.py` | ⚠️ | Home↑, outside↓, exploration graph simplifies/stabilizes. **11 nights (2026-07-10):** settling strengthens — edge-cosine 0.50→0.81, outside 246→174 m/valid-hr | n=5 paired, 11 nights; tunnel present 6/28 only; sub-1 m proximity below jitter floor | [plan](../implementation_plan/2026-06-30-nightly-behavior.md) · [log](../change_log/2026-06-30-nightly-behavior.md) · [11-day](../change_log/2026-07-10-d1-d2-eleven-day-consolidation.md) |
| Daytime sleep-site + tiered relocation (Direction 3) | `scripts/analyze_daytime_sleep_site.py` | ⚠️ | Per-animal daytime (05:00–21:00) rest site + within-day drift + across-day stability with **tiered relocation labels**. **Extended 2026-07-09 to 11 days (06-28→07-08):** tiers {stable 31, major-switch 19} over 50 day-pairs — **ALL 5 animals** switch house_1↔house_2 ≥1×, heterogeneous by **rate** (12395 5/10 · 12407 5/10 · 12378/12380/12386 3/10). Corrects both the old "8/10 relocated" (jitter) **and** the 3-day "only 2 animals" (small-sample). Primary site is always house_1/house_2/open → refuge_4 burrow does NOT contaminate | Sleep = low-speed proxy (not ephys-validated); site precision gated by ~7 in jitter; frame unverified | [plan](../implementation_plan/2026-07-02-daytime-sleep-site.md) · [log](../change_log/2026-07-02-daytime-sleep-site.md) · [tiering + 11-day](../change_log/2026-07-07-direction3-temperature-relocation.md) |
| Within-day rest-site & temperature (Direction 3, Stage B) | `scripts/analyze_daytime_rest_temperature.py` | ⚠️ | Within-day rest-site **sequence** + relocation events + weather + dropout guard. **Extended 2026-07-09 to 11 days (06-28→07-08), weather now full coverage:** heat-peak dispersal — the late-morning shelter aggregation thins/disperses at the 12:00–15:00 heat peak (to house_2 and/or open) on **9/10 days** (all but 07-05), a repeated **candidate temperature-linked** signature (66 within-day events, 56 bouts). AWN weather refreshed through 07-09 → temperature aligns for all 11 days (07-06/07/08 milder ~24–25 °C); driver auto-discovers `AWN-*.csv`. **refuge_4 BURROW caveat** flags refuge_4-dominant rest windows (07-03→07-07 pre-removal, 11 windows) = burrow + UWB lower bound, **not sleep**. Dropout ≈0 full days → reads real | Outside-air temp **proxy** (no shelter thermistor); temp a covariate on both animal + UWB paths; house_2 **not** verified cooler (inch frame); thermal vs social vs habit not separable; refuge_4 burrow removed 07-07 13:00 | [plan](../implementation_plan/2026-07-07-direction3-temperature-relocation.md) · [log](../change_log/2026-07-07-direction3-temperature-relocation.md) · report `outputs/direction3_temperature_relocation/` |
| Circadian / diel REST profile (Direction 3 companion) | `scripts/analyze_circadian_rest.py` | ⚠️ | Per-local-clock-hour REST fraction (group **mean ± SEM** across rats + per-animal traces), full 24 h, 5 rats × **11 days (06-28→07-08)**. Clear **nocturnal/crepuscular** rhythm — REST 0.92 day vs 0.86 night, i.e. a **~2.5× ACTIVE-fraction swing** peaking sharply at **21:00** (~0.19) and bottoming midday (~0.08); rats **highly synchronized** (narrow SEM). **Corroborates the 05:00–21:00 daytime rest window as data-driven.** **Per-day (C2/C3 REST + C4/C5 auto-scaled ACTIVITY per night): rhythm does NOT drift** — daytime plateau stable; only **amplitude/overnight-depth** modulates (sharpest 06-28 release & 07-04 fireworks). **Biological-night alignment (C6, anchored at the 07:00 activity trough): activity peak = 21:00 on ALL 11 dusk→dawn nights incl. release → dusk-onset phase FIXED from night 1** (the calendar '06-29 01:00 peak' was a night-splitting artifact; the release night just sustains activity latest into the overnight). Coverage panel guards dropout≠rest | Rest = low-speed **proxy** at the jitter *ceiling* (θ=12.5 in/s) → overcounts true sleep, compresses the swing (activity-onset rhythm, **not** sleep depth); not ephys/CV-validated; refuge_4 burrow + wet nights raise night dropout (guarded); 06-28 partial | [log](../change_log/2026-07-08-circadian-rest-profile.md) · report `outputs/circadian_rest/` |
| Sleep-site WISER↔CV cross-val (Direction 3) | `scripts/analyze_sleep_site_cv_crossval.py` | ⚠️ | Shelter-occupancy agreement vs CV (CH05/CH06). **Binning bug fixed + alignment checked 2026-07-06**; 07-02 rerun yields 960 bins / 42 episodes (19 hc). Read **CV precision≈1.0 / recall≈0.49–0.64 (lower bound)** per-shelter — **not** the joint κ | Only the 2 shelters; **alignment adequate** (±1 h fine sweep flat, best lag ~0 s): low joint κ=0.20 is a base-rate (kappa-paradox) + definition mismatch, **not** misalignment and **not** biological disagreement; CH05 recall gap is on *clear* glass ⇒ wall-edge blind-zone lower bound, not optical failure; older 6/29–6/30 κ (0.66 / 0.68–0.82) predate the binning fix (`[ns]` pandas) → re-confirm (see `outputs/audit/ALIGNMENT_DIAGNOSIS_2026-07-02.md`) | [plan](../implementation_plan/2026-07-02-sleep-site-cv-crossval.md) · [log](../change_log/2026-07-02-sleep-site-cv-crossval.md) · [binning fix](../change_log/2026-07-06-wiser-binning-resolution-fix.md) |
| Trajectory stereotypy, inter-animal correlation, following & route motifs (Phase A+B) | `scripts/analyze_trajectory_stereotypy.py` · `scripts/analyze_following_structure.py` · `scripts/analyze_route_motifs.py` | ⚠️ | **A:** space-use **stabilizes** 06-28→07-05 (0.14→0.96) but **mostly SHARED / road-driven** (residual Pearson ~−0.01; label-perm 0/10 above null). **B-follow (per-night):** **HERD / promiscuous, not stable dyads** (7–10/10 pairs beat circular-shift null nightly, top pair reshuffles, Spearman 0.11); movement **sequential** (~1.25% co-moving); **Sen top leader 5/7 nights**, Siesta 2/7. **B-motifs:** trajectories **strongly stereotyped** — **95% of route bouts recur** (≤3× jitter), 208 compact motifs, top-10 hold 27%, top motifs used by all 5 rats all 8 nights; **SHARED-dominant + weak individual residual (perm z=3.1)**; **present from night 1, not developing**. **11 nights (2026-07-10, A+B re-run):** A stabilizes 0.15→0.89, residual Pearson −0.01, label-perm 0/10 (only Dormi individual); B (10 nights, 07-04 excl.) herd — top pair reshuffles (5 distinct/10), **Sen** dominant leader. **13 nights (2026-07-11, motifs re-run 06-28→07-10, window tightened 21:00→04:00 data-driven):** recurrence **97%** (92–99%/night, from night 1), broad repertoire (top-motif share only 3–10%/night, no single road); **per-hour** — activity concentrates at **21:00 (~90 bouts/animal)**, recurrence 96–99% all hours; **per-day** cohort 5→4 at 07-09 (Hypnos cutoff); barn-light (S) covariate from 07-09. **Bout-scale VALIDATION (2026-07-11):** the "~4 s / ~100 in bout capacity" (bout_length_report) is a **SEGMENTATION ARTIFACT** — scale moves 1:1 with the 3 s min-bout filter (disp slope = median speed 25 in/s), un-truncated median run is **sub-second at the jitter floor** (0.54 s no-filter), hazard **non-monotone lognormal, no 4 s breakpoint** (only inflection at the 1 s speed-window; "memoryless" retracted), and 99% of bouts sit inside longer transitively pause-merged episodes. **Decision-boundary VALIDATION (Stage 1, 2026-07-11):** the "reorientation-punctuated" reading also FAILS — pause heading-change is **not separable from WISER jitter** (matched +18° but jitter-only null +20°; reverses to −3° when headings well-resolved ≥30 in flanks; changepoint detector 30–77% false-positive, 4–24% sensitivity; pause "predictability" a speed confound). **No reliable boundary class at WISER resolution → decision-to-decision legs NOT validatable without CV pose/keypoints; stopped at boundary verdict per staging gate** | Inch frame unverified (no physical/leader-geometry claims); jitter floor documented **~7 in** (measured p50 ~3.4); wet/fireworks/07-05-truncation + refuge_4 dropout (07-03→06) + barn-light-07-09+ flagged; motif endpoints mostly open→open (corridor segments); "stereotyped" ≠ memory; **roadway-vs-camera audit UNDONE** (motifs not yet verified against the physical trampled path — needs georeference) | [plan](../implementation_plan/2026-07-07-trajectory-stereotypy.md) · [log](../change_log/2026-07-07-trajectory-stereotypy.md) · [11-day](../change_log/2026-07-10-d1-d2-eleven-day-consolidation.md) · [motif-rerun](../change_log/2026-07-11-motif-rerun-per-hour-day.md) · [bout-seg-validation](../change_log/2026-07-11-bout-segmentation-validation.md) · [decision-boundary-validation](../change_log/2026-07-11-decision-boundary-validation.md) |
| Route-vocabulary validation (Stage 1, **PROVISIONAL**) | `scripts/analyze_route_vocabulary.py` · `src/route_vocabulary.py` · `src/trajectory_units.py` | ⚠️ | **Falsifies the "discrete shared route vocabulary" claim — *conditional on the original 3-second-filtered bout segmentation*** (a provisional baseline whose scale is imposed by the min-bout/min-disp filter, NOT validated legs). 1692 units, 13 nights (06-28→07-10). **Verdict C = continuous route manifold, NOT a discrete vocabulary.** Endpoints DOMINATE (endpoint chord 7.88 in ≈ jitter, beats the K=176 route dict 15.72; A3 PCA M=4→4.17 in ⇒ manifold ≈ the 4-D endpoint space); a **small reusable low-dim CONTINUOUS curvature** exists (FAIR scale-invariant shape dict 5.81 < straight 7.88 < null 7.58; beats the endpoint-preserving geometry null) **but no finite-K discrete scale** (dict MDL min K=128 > PCA MDL; `dict_beats_pca=F`, NOT load-bearing); **shared across animals = the endpoint GRAPH, not a path vocabulary** (LOAO E_endpoint≈9 ≪ dicts≈20); **repertoire does NOT close** (held-out coverage 0.39→0.88 but next-night novelty ~0.12, not→0; supplementary A7 night-0 dict covers only 39% of later routes ⇒ not fully present night 1). **C-vs-B UNRESOLVED** (measurement-audited) — the closure axis is regime-confounded (deciding late nights 07-08→07-10 coincide with refuge_4 removal 07-07 + barn-light 07-09 + 5→4 cohort), and the reusable-shape reduction (~2 in) is **sub-jitter-floor**; **NOT-A ("no discrete vocabulary resolvable above ~7 in") is the robust, floor-bounded result**. **Adversarially verified** (5-lens skeptic workflow reproduced the numbers, confirmed NOT-A robust; fixed a tautological metric, a biased shape test, a same-night LOAO leak) **+ wiser-measurement-auditor** (NOT-A + endpoint-dominance measurement-sound; provenance limiter = no WISER `measurement_context` sidecar yet). **Representation comparison DONE** (`compare_route_segmentations.py`, after cross-checking `decision_boundary_validation/`): the identical battery on **pause-merged episodes** (1609 units; 5s transitive pause-bridging of the 3s bouts) gives an **identical verdict C + all criteria** → the "no discrete vocabulary / endpoints dominate" reading is **robust to unit scale** (bouts↔episodes; endpoint share 0.99↔0.98, chord<dict at both). `validated_locomotor_legs` BLOCKED (`blocked_needs_cv` — WISER can't validate decision boundaries: matched pause-turn +17.9° ≤ jitter-null +20.4°, reverses to −3.1° well-resolved; needs CV). **Also corrects Phase-B**: "Since z>2" for z=1.84 was FALSE (no individual residual); Phase-B recurrence = a globally-pooled retrospective upper bound | Frame UNVERIFIED → no metric/directional/**physical-road** claim (Module 11 blocked); **PROVISIONAL** — the vocabulary question is only settled by re-running the identical battery on validated decision-to-decision legs / pause-merged episodes, which the decision-boundary analysis found **NOT validatable from WISER alone** (needs CV pose/keypoints); A6 stability / A8 grammar / policy **GATED & not run**; roadway-camera audit UNDONE | [plan](../implementation_plan/2026-07-11-route-vocabulary-validation.md) · [log](../change_log/2026-07-11-route-vocabulary-validation.md) · report `outputs/route_vocabulary_validation_2026-06-28_to_2026-07-10/original_3s_filtered_bouts/` · [audit](outputs/audit/ROUTE_VOCAB_AUDIT_2026-07-11.md) · [**sci-summary**](outputs/route_vocabulary_validation_2026-06-28_to_2026-07-10/SCIENTIFIC_SUMMARY.md) |
| Following **incidents** + video audit + camera router (Phase B2) | `scripts/analyze_following_incidents.py` · `scripts/audit_following_video.py` · `src/camera_router.py` | ⚠️ | **Additive** to Phase B (peak-score layer untouched). Incident-level frequency: **11 nights (2026-07-10): 2046 strict-following episodes, median 3 s** (was 1429/8 nights) — trailing is **frequent but brief**, which the Phase-B peak score compressed. **All 4 top ordered pairs are Sen→X** (Sen→Siesta 1.82/hr, →Hypnos 1.70, →Dormi 1.47, →Nox 1.41) → Sen the dominant lead. Adds a WISER→camera **router** (ranked channels) → `strict_following_video_queue.csv` (2046/2046 routed, 1545 near a boundary), and a **video-audit** classifier (detected vs lag/heading/radius/moving/dropout/alignment/not-strict) for detector recall | Camera map is a **PLACEHOLDER** (`meta.confirmed:false`) — routing provisional until calibrated; **video recall not yet claimed** (needs marked events); inch frame unverified; leader=temporal order | [plan](../implementation_plan/2026-07-08-following-incidents-b2.md) · [log](../change_log/2026-07-08-following-incidents-b2.md) · [11-day](../change_log/2026-07-10-d1-d2-eleven-day-consolidation.md) |
| Agent-policy identifiability (hierarchical semi-Markov) | `scripts/build_decision_tables.py` (cv) · `scripts/analyze_policy_identifiability.py` (anaconda3) | ⚠️ | Identifiability-FIRST (NOT IRL): does identity/social state improve **out-of-night** prediction of **leaving hazard** + **destination choice** beyond an **explicit-layout + weather** baseline? 8 nights (06-28→07-05), whole nights the outer blocks, bits/decision. **RE-RUN 2026-07-10 on a jitter-tolerant HYSTERETIC ROI-state decision unit** (the raw point-in-ROI unit was flicker-contaminated → M4/M5 invalidated), across a preregistered buffer{7,14,21}×exit{30,60}×epoch{5,15,30} grid. Robust across all 8 configs: environment+dwell skill **0.13–0.26**; weather≈0, shared-use≈0, Markov-sufficient. **Individual = statistically detectable but NEGLIGIBLE** (cond-perm z 2–9, magnitude ~0.001 bits). **Social = ROBUST GO (reversed from the contaminated NO-GO):** real-time **group** social state predicts leaving — Δbits ~0.012 (~4% skill), +on all 8 nights, GO in all 8 configs, time-shift z 11–32, **survives day-shuffle z ~30 AND jitter-floor-safe features** (not a sub-floor artifact, not shared arousal); identity-agnostic group coupling (herd, not dyads). Endpoint = environment+dwell+group-social semi-Markov choice model; no IRL | Inch frame unverified (topology + coarse ≥14 in distances only); social is **group-level, identity-agnostic** (pair-resolved is a follow-up), effect modest (~4% skill); `--fast` perms (re-run full for publication z); refuge_4 burrow-night excluded; Sova cut 06-29; extend to 11 nights | [plan](../implementation_plan/2026-07-09-agent-policy-identifiability.md) · [log](../change_log/2026-07-09-agent-policy-identifiability.md) · [redo+social](../change_log/2026-07-10-decision-unit-hysteretic-social.md) · [temporal+fix](../change_log/2026-07-11-temporal-policy.md) · report `outputs/policy_identifiability_2026-06-28_to_2026-07-06/` (regenerated clean, provenance=`hysteretic_buf14_exit30_ep15`; raw run preserved under `superseded_raw_pointinroi/`). **Temporal (2026-07-11):** the conditional leaving RULE is **time-invariant** — hour-varying held-out Δbits −0.0004 (hour-label null z 0.73), night-slope variance z 0.51, structured context ≈0; hour/night differences are state occupancy under ONE shared rule; crowding **suppresses leaving** (huddle cohesion), constant across the night. Reward-gate now mechanically GO (preconditions met) but endpoint stays the interpretable time-invariant hazard model |
| Approach/avoid — social spacing (Module 7, Phase 3) | `scripts/build_approach_avoid.py` (`src/approach_avoid.py`) | ⚠️ | **In-bout approach/avoid, coarse + HEADING-FREE (DBV), NIGHT-BLOCK gate.** Within validated active bouts, per (bout, ≥1m partner): toward-ness = net distance closed on the partner / bout displacement. 8 nights, **3,936 bout-partner pairs**. **Significance is night-level** (per-night effect + binomial sign test over 8 nights — NOT a per-pair z, which the adversarial review showed is pseudoreplicated). **Headline — DISTANCE-DEPENDENT SOCIAL SPACING:** beyond shared layout, the focal shows real-time **APPROACH to far conspecifics (>3.8m: e_day +0.117, 8/8 nights, p=0.008)** and **AVOIDANCE of near ones (1–3.8m: e_day −0.11 to −0.24, 0/8 nights, p≤0.016)** — active maintenance of a preferred inter-individual distance, night-consistent. Above chance geometry at all distances (e_dir p 0.008–0.016). First robustly night-validated social signal; **survived** the pseudoreplication correction. Adversarial review fixed 3 confirmed findings (pseudoreplication→night-block, day-shuffle subpop mask, net_sign vs geometry) | Coarse net proximity ≥1m, heading-free (no fine steering — DBV); approach to partner's START (partner also moves); **association NOT motivation** (not "chooses to approach"/"attraction"); group-level (dyadic only if module 13); frame UNVERIFIED; ~8-night pilot | [plan](../implementation_plan/2026-07-12-approach-avoid.md) · [log](../change_log/2026-07-12-approach-avoid.md) · report `outputs/approach_avoid_2026-06-28_to_2026-07-05/` |
| Destination & settlement (Module 6, Phase 2) | `scripts/build_settlement_transitions.py` · `scripts/analyze_destination_choice.py` (`src/settlement_transitions.py`) | ⚠️ | **Destination rebuilt on the unified locomotor state; VALIDATION-FIRST.** A destination is defined only after **sustained stable residence**; each departure typed {relocation, same_site_return, pass_through, open_field_termination, censored}; representation **VALIDATED (gate PASS)** before any choice fit. 8 nights, 1,110 stationary episodes → 321 settlements, 295 departures. **Headline: ~60% of shelter departures END IN THE OPEN (open_field_termination); only 19% relocate to a named site, 13% same-site return** — the old named→named `build_destination_table` was blind to this. Gated choice fit (n=55, exploratory): **origin conditions destination — Δbits 0.63 / skill 14% over the global hub rate (baseline-independent)**; the uniform-chance comparison is baseline-sensitive at n=55; house↔house switching dominant (19/55); 0/2 stable individual house preference. Adversarial review (5-dim workflow) fixed 5 issues (coverage-gate demotion, dropout-spanning-bout censor, uniform-baseline consistency, empty-grid-cell stability, a hardcoded directional string). Cross-checked vs `decision_boundary_validation` | Endpoints only (frame UNVERIFIED — no route/path/direction/"navigation"); destination measurable only at sustained residence; choice fit thin (n=55, more nights needed); DBV: fine kinematics/legs NOT resolvable, not claimed | [DBV cross-check](../change_log/2026-07-11-dbv-crosscheck-locomotor.md) · [log](../change_log/2026-07-11-destination-settlement-rebuild.md) · report `outputs/destination_settlement_2026-06-28_to_2026-07-05/` |
| Locomotor-bout initiation (Module 3, Phase 1) | `scripts/build_locomotor_states.py` · `scripts/analyze_locomotor_initiation.py` (`src/locomotor_states.py`) | ⚠️ | **Entry-side twin of the leaving hazard.** Unified locomotor state machine (rest/local_active/transit/pause, jitter+gap-tolerant) + the **bout-INITIATION hazard**: given a low-speed state, per-epoch hazard of starting a locomotor bout. 8 nights (06-28→07-05). **Decision unit REDESIGNED to gap-holding stationary episodes** (a first per-bin-rest unit over-fragmented rest 10,825→1,110, median 30 s→6.6 min, and VIOLATED D1). Clean unit: **1,016 onsets / 198,735 at-risk epochs**; the four distinctions hold — **initiation ≠ ROI departure (D1 onsets 1,051 vs 40 departures, 26×)**, in-place ≠ leaving, pause ≠ settlement, arrival ≠ settled. Hazard **3.3× higher from open low-speed (0.85%) than settled shelter-rest (0.25%)**. **Predictive gate PASSES** (state skill 6.2%, H 0.0462→0.0434 bits). **Weather ≈0; group-social NO-GO (Δbits ~0.0002, below threshold)** — a striking asymmetry: crowding suppresses *leaving* (module 5, ~0.012 bits) but does **not** predict *initiation*. Individual negligible. Adversarial review (15-agent workflow) confirmed + fixed a bout gap-merge bug | Onset = speed-onset above ~7 in jitter = a **LOWER bound** (in-nest stirring, ~18:00 arousal invisible → not "wake"); rest = low-speed proxy (not sleep); frame UNVERIFIED (topology only); single 8-night pilot; not "the policy"/"search"/"decided to forage" | [plan](../implementation_plan/2026-07-11-locomotor-bout-initiation.md) · [log](../change_log/2026-07-11-locomotor-bout-initiation.md) · report `outputs/locomotor_initiation_2026-06-28_to_2026-07-05/` |
| Formal-session analysis | `scripts/analyze_formal_recording.py` | ◻️ | Loads + cleans only | No smoothing / gap detection / session QC yet | — |

## Behavioral-policy module map (the agent is more than one process)

> The **Agent-policy identifiability** row above is **modules 5 + 6** (site-residence termination +
> destination/settlement) of a **14-module** behavioral policy — the *exit side of one locomotor loop*,
> **not** "the rat policy" and **not** "search strategy". The full decision/search space, its dependency
> DAG, and the language each module is allowed are specified in three companion files:
> **map** [`docs/behavioral_policy_map.md`](../docs/behavioral_policy_map.md) ·
> **registry (18 fields/module)** [`configs/behavioral_policy_modules.yaml`](configs/behavioral_policy_modules.yaml) ·
> **phased plan + gates** [`implementation_plan/behavioral_policy_roadmap.md`](../implementation_plan/behavioral_policy_roadmap.md).
> The organizing framework is a **hierarchical semi-Markov state machine**; a **graph transformer is a
> LATE CHALLENGER for module 13 only**, never the framework. Downstream modules stay **BLOCKED** until
> every upstream module clears all four gates (measurement / support / predictive / interpretation).

| # | Module | Status | Phase | Scope guard (what it is NOT) |
|---|---|---|---|---|
| 1 | Behavioral state segmentation | ⚠️ **candidate (BUILT)** | substrate | not a validated ethogram; not "sleep" |
| 2 | Stable residence / rest | ⚠️ **candidate (BUILT)** | Phase 1 | settled ≠ "decided to rest"; not "sleep" |
| 3 | **Locomotor-bout initiation** | ⚠️ **candidate (BUILT)** | **Phase 1 ✓** | onset ≠ "decided to forage"; not "wake" |
| 4 | Active locomotor bout | ⚠️ partial (bouts built) | Phase 1 | endpoints yes; fine steering no |
| 5 | **Site-residence termination** | ⚠️ **candidate (BUILT)** | done | not "the policy" / "search strategy" |
| 6 | **Destination & settlement** | ⚠️ **candidate (REBUILT)** | **Phase 2 ✓** | not "route choice" / "navigation" |
| 7 | Approach / avoid (group, partners) | ⚠️ **candidate (BUILT)** | **Phase 3 ✓** | association, not attraction/motivation; social SPACING not "attraction" |
| 8 | Following / leading | ⚠️ candidate | (built, additive) | temporal order ≠ pursuit / "leader" intent |
| 9 | Return vs explore | ⚠️ **candidate (BUILT)** | **Phase 4 ✓** | not "curiosity / novelty drive"; NULL: no return-bias beyond layout |
| 10 | Area-restricted vs global search | ⚠️ **candidate (BUILT, coarse)** | **Phase 4 ✓** | geometry, not "foraging strategy / optimal"; DBV-capped |
| 11 | Route / corridor selection | ⛔ blocked (georef) | Phase 4 | no directional / metric route claims |
| 12 | Short-term social history | ◻️ planned | Phase 5 | predictive, not "memory" / causal |
| 13 | Long-term pairwise social graph | ◻️ planned (**late challenger**) | Phase 5 | not "social network / bonds"; not the framework |
| 14 | Latent motivation / reward | ⛔ blocked (capstone) | capstone | not "the goal / utility"; likely NO-GO |

**Phase 1 (module 3) is BUILT** (2026-07-11, ⚠️ candidate — the unified locomotor-state machine +
bout-initiation hazard; the entry-side twin of the leaving hazard). Decision unit = gap-holding
stationary episodes; initiation ≠ ROI departure (D1 26×); hazard ~3.3× higher from open low-speed than
settled shelter. See [change log](../change_log/2026-07-11-locomotor-bout-initiation.md) +
`outputs/locomotor_initiation_2026-06-28_to_2026-07-05/`.

**Phase 2 (module 6) is BUILT** (2026-07-11, ⚠️ candidate — destination & settlement rebuilt on the
unified locomotor state; **validation-first**). A destination is defined only after sustained stable
residence; every departure typed {relocation, same_site_return, pass_through, open_field_termination,
censored}; representation **VALIDATED (gate PASS)** before any choice fit. **Headline: ~60 % of shelter
departures end in the open (open_field_termination), only 19 % are relocations to a named site** — the
old named→named unit missed this. Gated choice fit: origin conditions destination (Δbits 0.63 / skill
14% over the global hub rate, baseline-independent); the uniform-chance comparison is baseline-sensitive
at n=55; house↔house switching dominant; no stable individual house preference. Cross-checked against `decision_boundary_validation` (coarse scale only; no
fine kinematics). See [change log](../change_log/2026-07-11-destination-settlement-rebuild.md) +
[DBV cross-check](../change_log/2026-07-11-dbv-crosscheck-locomotor.md) +
`outputs/destination_settlement_2026-06-28_to_2026-07-05/`.

**Phase 3 (module 7) is BUILT** (2026-07-12, ⚠️ candidate — in-bout approach/avoid, coarse + heading-free
per DBV, **night-block** significance). **Headline: DISTANCE-DEPENDENT SOCIAL SPACING** — beyond shared
layout, the focal shows real-time approach to *far* conspecifics (>3.8m, 8/8 nights) and avoidance of
*near* ones (1–3.8m, 0/8 nights), a night-consistent preferred-spacing tendency (sign-test p≤0.016);
above chance geometry at all distances. The first robustly night-validated social signal — and it
**survived** the adversarial review's decisive pseudoreplication finding (per-pair z was invalid; the
whole gate was redone at the night-block level). See [change log](../change_log/2026-07-12-approach-avoid.md)
+ `outputs/approach_avoid_2026-06-28_to_2026-07-05/`.

**Phase 4 (modules 9 & 10) is BUILT** (2026-07-12, ⚠️ candidate, gate-first, on the extended 11 nights).
**Module 9 (return-vs-explore) is a NULL:** 123 named-destination excursions, raw return rate 0.76 but
**NOT distinguishable from the layout base rate** (site popularity), night-block sign-test p=0.55 — no
return-vs-explore *preference* beyond "a few sites are popular"; 39 % of named-dest moves are same-site
returns. **Module 10 (search geometry) is coarse-only (DBV):** 1,541 bouts, uniformly tortuous
(straightness ~0.17–0.21) with a modest radius gradient (in_place 100 < relocating 124 < open 142 in) —
no clean ARS-vs-global bimodality; geometry, not a strategy. See
[change log](../change_log/2026-07-12-phase4-search-excursions.md) +
`outputs/search_excursions_2026-06-28_to_2026-07-08/`.

**All modules extended to 11 nights (06-28→07-08)** on 2026-07-12 (through Hypnos removal). Key update:
the **module-5 crowding-suppresses-leaving effect ATTENUATES** to Δbits ~0.003 (jitter-safe 0.0027,
magnitude NO-GO though still beating the nulls, z 2.5–3.4) vs the 8-night 0.012; it **survives rest-need
control** (67 % retained). The **module-7 distance-dependent spacing strengthens and is circadian-robust**
(holds in both active and nap population-rest phases). See
[change log](../change_log/2026-07-12-11night-rest-social-circadian.md). **Whether the module-5
attenuation is a front-loaded/habituating effect averaged flat (a reviewer's group-sampling hypothesis)
is UNRESOLVED at n=11** — held-out early(0-2) 0.0046 > late 0.0020 (weak, n.s., ρ=−0.19), pooled
night-permuted interaction null, ~0.27 power, 2-night fragile (0.0027→0.0007 w/o 06-28+07-06); a direct
FOLLOWING (co-departure) test is negligible (≤0.001) and not front-loaded; adversarially verified
(5-agent workflow). See [change log](../change_log/2026-07-12-social-nonstationarity-and-following.md).
Route/corridor (module 11) stays ⛔ georef-blocked; the social-graph transformer remains a late-Phase-5
challenger, not the framework.

## Cross-cutting blockers

| ⛔ Blocker | Impact | Resolve by |
|---|---|---|
| WISER frame not georeferenced to the 20×40 ft paddock (tooling ready; awaiting survey) | Every spatial claim (wall-running, thigmotaxis, route-vs-boundary) may be a coordinate artifact | Run the pole-dwell survey → `scripts/georeference_wiser.py` fits the WISER-inch→field-cm transform. See [georeferencing plan](../implementation_plan/2026-07-01-wiser-georeferencing.md) |
| `wiser_rois.json` unconfirmed (`confirmed=false`) | Refuge/home/resource behavioral claims rest on inferred, not real, locations | Run `place_wiser_rois.py`, set `confirmed=true` |
| Weather↔WISER alignment wall-clock only (±5 min) | Weakens any weather-correlated activity claim | Independent clock check / sync verification |
| Sub-1 m proximity below the ~7 in jitter floor | Fine-grained social-distance claims unreliable | Keep proximity thresholds ≥1 m |

## Three research directions — status & path to publishable

The WISER analysis is organized around three directions. Cross-cutting prerequisites (the
georeference survey and ROI confirmation) gate the spatial directions (D2, D3); both are tooled
and awaiting field input.

### Direction 1 — Rain-influenced behavior  ⚠️ candidate *(extended to 11 nights 2026-07-10)*
- **Drivers:** `analyze_nightly_progression.py` + `analyze_nightly_behavior.py`, now over **06-28→07-08
  (11 nights, 5 rats)**. Habituation **229→152 m/valid-hr** (first dry drop 06-28→06-29 **50%**); behavior
  driver's settling **strengthens** (edge-cosine 0.50→0.81, outside movement 246→174, home use up). Rain is
  now classified **per night** (`wet_ground`/`rain_in_window` from AWN) not "last night = wet": wet-vs-dry
  122 vs 164 m/valid-hr but **confounded** (habituation position + UWB dropout, read vs `nightly_qc.csv
  valid_frac`); 06-30 within-night DiD +19.9 [95% CI −8.6,+43.4] → **CI spans 0**, no acute suppression.
- **Blocker:** rain vs habituation **still not separable** — wet nights sit late in the sequence + low-N +
  raise dropout; n=5, single cohort.
- **Next:** a 2nd cohort / dry-vs-wet nights balanced across sequence position to break the confound;
  see `change_log/2026-07-10-d1-d2-eleven-day-consolidation.md`.

### Direction 2 — Social-influenced trace (route following)  ⚠️ candidate *(extended to 11 nights 2026-07-10)*
- **Drivers:** `analyze_route_structure.py` (11 nights) + the trajectory/following suite
  `analyze_trajectory_stereotypy.py` (A, 11 nights) · `analyze_following_structure.py` (B, 10 nights, 07-04
  excluded) · `analyze_following_incidents.py` (B2, 11 nights). Space-use **stabilizes 0.15→0.89** but
  residual Pearson **−0.01** (shared-road; only Dormi weakly individual); corridors cross-rat 0.90 >
  within-rat 0.35, ~27% night-to-night. Following is **herd/promiscuous, NOT stable dyads** (top pair
  reshuffles nightly, 5 distinct/10 nights); **Sen the dominant leader** (all 4 top ordered incident pairs
  are Sen→X). **2046 strict-following episodes** / 11 nights (median 3 s).
- **Blocker:** **WISER frame unverified** (no leader-geometry); ~7 in jitter; video-audit camera map is a
  placeholder (recall not claimed).
- **Next:** run the **georeference survey** (route driver adopts `verified_boundary_in_wiser` + `x_field_cm`
  once confirmed); mark video events → `audit_following_video.py` for detector recall; 2nd-cohort replication.

### Direction 3 — Sleep-location change (05:00–21:00)  ⚠️ candidate *(new 2026-07-02)*
- **Drivers:** `analyze_daytime_sleep_site.py` (per-animal primary rest site + within-day drift +
  across-day stability, now with **tiered relocation labels**) and `analyze_daytime_rest_temperature.py`
  (Stage B: within-day rest-site sequence vs temperature); `analyze_evening_morning_sleep.py` splits the
  day into an EVENING baseline (17:00 → a per-day **temperature-calibrated** end) vs a MORNING window
  (05:00–11:00) and tests morning departures against weather. CV cross-check is
  `analyze_sleep_site_cv_crossval.py` (reconciled 2026-07-06). Companion
  `analyze_circadian_rest.py` gives the diel rest/activity profile (validates the 05:00–21:00 window).
- **Candidate findings (11 days, 06-28→07-08, extended 2026-07-09):** across-day, **all 5 animals**
  switch house_1↔house_2 at least once — the signal is the switch **rate** (12395 5/10 · 12407 5/10 ·
  12378/12380/12386 3/10), not a stable/relocator dichotomy. This corrects *both* the old "8/10
  relocated" (jitter-scale) *and* the 3-day "only 12386 & 12407" (small-sample) reads. **Within-day**,
  the late-morning shelter aggregation **thins/disperses at the 12:00–15:00 heat peak on 9/10 days**
  (rats move to house_2 and/or open field) — a repeated **candidate temperature-linked** signature
  (66 events). AWN weather refreshed through 07-09 → temperature aligns for all 11 days (07-06/07/08
  milder). Daytime dropout ≈0 on every full day, so the reads (incl. wet days) are real, not a UWB
  artifact. **Circadian companion (11 biological nights): dusk-onset activity peak locked at 21:00 from
  night 1** (fixed phase; only overnight depth habituates). **refuge_4 burrow caveat** flags
  refuge_4-dominant rest windows (07-03→07-07 pre-removal) as burrow-entrance + UWB lower bound,
  **not sleep** (house reads and the full-day primary-site analysis unaffected).
- **📄 Circadian scientific summary (2026-07-12):** `outputs/circadian_rest/SCIENTIFIC_SUMMARY.md` —
  promotion-gate-audited narrative of the diel rhythm + day-by-day active-portion change + weather.
  **Phase fixed (21:00 peak, all 11 nights, all 5 rats, weather-independent);** the day-to-day *amount*
  varies — release-night novelty burst (active-frac 0.150) then a **temperature-associated** pattern
  (nightly active-frac vs midday temp **ρ=−0.53**, candidate/confounded with day-in-sequence); **no
  separable rain effect** (wet 0.069 vs dry 0.096 confounded; acute rain DiD CI −8.6…+43.4 spans 0);
  **no monotonic activity-habituation** — settling is spatial (edge-cosine 0.50→0.81), not an activity
  decline. Rest = movement proxy (not sleep depth).
- **Night consolidated rest (2026-07-12, `analyze_night_consolidated_rest.py`):** ⚠️ refined mid-night
  "nap" → a **consolidated rest bout (CRB)** = position **clustered (stay-point, radius 4 in observed)** in
  a shelter + resting, sustained **≥30 min** (20/40/60 sweep), 10-min exit tolerance; refuge_4/tunnel count
  as shelter. **137 CRBs, every rat-night ≥1, 93% in a shelter**, median 50 min, ~145 min total/night (2.5
  bouts), house-centred. **Why (candidate):** familiarity **NO** (ρ=−0.20); **temperature NO — retracts the
  crude "hot→rest"** (loose-metric artifact; within-rat −0.12 on the in-shelter metric); **humidity CANDIDATE,
  ROBUST** (within-rat +0.36; **humidity|rain +0.46, humidity|day +0.44, DRY-nights-only +0.63**; rain itself
  −0.25 → dampness NOT rainfall/habituation); bout is **clock-timed (~midnight), not at the within-night
  weather minimum**; trait η²=0.14 (night-level state). Rest = low-movement proxy, NOT sleep. **9 non-shelter
  candidates** exported for CH05/CH06 audit (5 cropped; NVR clock **UTC−5**). Self-test PASS (8/8); plan +
  **promotion-gate-audited `outputs/night_consolidated_rest/SCIENTIFIC_SUMMARY.md`** written. Deferred:
  within-night hazard model + shelter humidity logger; 4 missing video crops. See
  `change_log/2026-07-12-night-consolidated-rest.md`.
- **Evening-vs-morning split (2026-07-08, extended to 11 days 06-28→07-08 on 2026-07-09 with the full
  06-28→07-09 AWN weather, `analyze_evening_morning_sleep.py`):** the EVENING window (17:00 → the
  temperature-calibrated **sleep-period end**, θ\*=22.65 °C, **all 11 days thermally calibrated**) is a
  **stable individual baseline for 4/5 rats** (MAD 6.5–18.5 in; 12378/12380→house_1, 12395/12407→house_2).
  **12386 is bimodal (MAD 90)** — it splits evenings between the houses, so its median baseline sits
  between them and its ~90-in "borderline" morning reads are a **baseline artifact, not a relocation**
  (flagged). *(The earlier 8-day "5/5 stable" was small-sample.)* ⛔ **`sleep_end` is RETIRED (2026-07-10)
  → replaced by `wake_hour` in `analyze_biological_day_sleep.py`** (see the biological-day row below): it
  ran **past midnight on hot nights** (07-02 ≈02:20) and **conflated the midnight nap with trunk-sleep
  end**, wrongly making emergence temperature-driven. The evening-baseline SITE + morning comparison +
  activity curves are unaffected. A **per-night
  activity-fraction figure (A1), co-plotted with outside temperature + rain**, shows each night's
  emergence (6/28's release pseudo-peak ~19:30 annotated; emergence ~21:00 = the circadian peak; 07-01's
  ~45 mm/h downpour ↔ activity spike visible). The MORNING site (05:00–10:00, before the ~10:00 switch)
  shows 13/50 nearest-house switches, but they **do NOT track temperature** (ρ=−0.02). **Rain now weakly
  testable** — 2 wet mornings (07-01, 07-07 2.37 mm); Spearman(move, overnight_rain) = **−0.20**
  (near-zero/negative → rain does not increase the morning move; if anything more site fidelity when wet)
  → **suggestive, not conclusive** (tiny wet-N + 12386 confound). Morning divergences read individual/diurnal.
- **Biological-day sleep model — CORE rebuild (2026-07-10, `analyze_biological_day_sleep.py`):** re-cuts
  sleep on the biological day (**trunk ~05:00 → trunk-end**), **RETIRING the temperature `sleep_end`**. New
  util `locomotor_emergence`: **`locomotor_emergence_hour`** = onset of sustained locomotion / sleep-site
  departure, clusters **~20.8 h** (≤21:00, none past midnight), **Spearman(emergence, afternoon temp) =
  −0.02** → circadian-clustered, **not temperature-driven** (the direct evidence the past-midnight
  `sleep_end` was an artifact). **Sensor-limited** (not "not an error"): ~20:00 site departure LAGS the
  field-observed ~18:00 in-nest wake — *consistent with* WISER's invisibility to in-nest stirring (below the
  jitter floor) but *not proven* to be entirely that (needs ephys / interior CV). **The "~10:00 switch" is
  NOT supported (corrected):** the fixed morning/day windows only show site assignments **differ on 15/50
  rat-days** (10:00 was the imposed boundary). An **independent within-trunk change-point** (`detect_site_
  changepoint`, no fixed 10:00) finds relocation is common + large but **SPREAD across the trunk** — 44/55
  rat-days supported (median conf 0.96, disp 203 in ≈ house↔house), change-point **times median 13.5 h, only
  11% within ±1 h of 10:00** (`CP1`; robust to smoothing + dropout). Morning-window site stable for
  12378/12380/12386 (MAD ~4 in), bimodal for 12395/12407. **MULTI-SITE rebuild (2026-07-11 — the earlier
  binary house_2-fraction test was a state-space misspecification, SUPERSEDED):** `classify_site_state` +
  `trunk_state_dwell_transitions` over the FULL ROI set (house_1/2, refuge_1/2/3, refuge_4 [date-gated
  burrow], water_1/2, doorway, exposed). Sleep is genuinely multi-site — **unconditional** dwell (sums to 1)
  house_1 0.51 · house_2 0.33 (~85% together) · refuge_4 0.05 [burrow] · doorway 0.04 · refuge_1 0.02 ·
  exposed 0.02 · tunnel/water_2 ~0.01; **~3.1 relocations/rat-day (median 3, 170 total)** — **68% (116/170)**
  involve a non-house state, **51% (56/110)** of the interpretable ones (excl. refuge_4/tunnel); the
  displacement-only "house_1→house_2" labels were wrong. Temperature (multi-site, within-rat): any-shelter
  dwell ρ=**−0.44** (incl. burrow/tunnel), **doorway ρ=+0.58** / water_2 +0.38 (↑ with heat), houses go
  **opposite** ways (house_1 +0.17, house_2 −0.19) → a **candidate** increase in doorway/near-water use on
  hot days (NOT a uniform "leave the houses"); candidate only (n=11, uncorrected, ambient temp,
  jitter-adjacent; the "no temperature effect" claim is retracted). **Reconciled 2026-07-11** (single change-
  point vs state-sequence separated; unconditional dwell) → canonical
  `outputs/direction3_biological_day_sleep/direction3_biological_day_sleep_canonical_results.md`.
  **Deferred:** nap detection; a firmer temperature test needs a shelter thermistor. See
  `change_log/2026-07-10-biological-day-sleep.md`.
- **Landmark hierarchy — state role in the decision (2026-07-11, `analyze_sleep_site_hierarchy.py`):** are
  the rest-site landmarks the **same status** or **ranked**? Descriptive semi-Markov (role identifiable,
  physical cause NOT; **no reward/IRL**), 55 rat-days, 2000× permutation nulls. **The landmarks are NOT the
  same status:** the **anchor role is non-exchangeable** (KL 0.33, **p<0.001**); **houses = net sinks /
  home-bases** (house_1 leads: anchor 0.51 + terminal 0.60, H=0.55) vs **periphery = sources** (exposed
  φ=−1.0, water_2 −0.5, tunnel −0.39); a **reproducible diurnal ordering** (house_1 12.0 h → house_2 13.9 h
  → doorway 15.0 h, label-perm **p=0.001**); a **cohort-shared ranking** (Kendall **W=0.79, p<0.001**; the
  two house_2-dwellers still anchor house_1 on 32% of days). **The user's ordered chain is REVISED by honest
  nulls:** house↔house 54 direct vs 7 via-doorway (doorway not an intermediate); round-trip common (R=0.78)
  but **NOT beyond a memoryless null (p=0.14)**; terminal only borderline (p=0.053); excursion-vs-temp
  ρ=+0.18 → **no detectable** (candidate; ambient temp). New pure primitives + driver + `H1–H4` + self-test
  (PASS). See `change_log/2026-07-11-sleep-site-hierarchy.md` + `outputs/direction3_sleep_site_hierarchy/`.
- **Heat-GATED house-leaving (2026-07-12, `analyze_heat_gated_relocation.py`):** daytime temperature is a
  **GATE, not a linear dial** — P(out of enclosed house) flat ~4–6% below ~30 °C → **0.27 at 32–34 °C**, gate
  ≈**32 °C**. **Within-day** design (each hot rat-day its own control → removes the hot-days-were-early
  confound): P(out) **0.04→0.31**, **ΔP(out)=+0.27, 95% CI [+0.22,+0.32], frac>0=1.0** across all **4**
  gate-crossing days (day-clustered bootstrap); exodus timed to the **14–15:00** heat peak; exits **0.40→0.66**
  cooling-directed; **4/5 rats** respond (sedentary 12378 the exception). **Circadian control** (matched
  clock-hour, HOT vs COLD day): midday P(out) **0.32 (HOT) vs 0.03 (COLD)**, cold days ~0 all day → not a
  circadian rhythm; within-day removes sequence + matched-hour removes circadian → the pair triangulates temperature. **Supersedes** the earlier "no
  detectable temperature effect" (full-day/linear tests can't see a threshold) and explains why the
  house-vs-floater "trait" dissolved (shared **gate**, ICC≈0). Candidate/descriptive — **ambient** (not
  in-shelter) temp, **unverified frame**, low-movement proxy, threshold rests on 4 hot days → **NOT
  thermoregulation** (needs shelter thermistor + interior CV + georeference). New primitives
  (`logistic_fit_1d`/`logistic_threshold`/`cluster_bootstrap`) + driver + self-test (PASS) + `HG1–3`. See
  `change_log/2026-07-12-heat-gated-relocation.md` + `outputs/direction3_heat_gated_relocation/`.
- **📄 Consolidated human-readable summary (current, whole-direction):**
  `outputs/direction3_sleep_site/SCIENTIFIC_SUMMARY.md` — promotion-gate-audited narrative of the
  biological-day model, the landmark hierarchy, **and the heat-gate finding**; supersedes the
  biological-day-only summary for whole-direction reading. Field/hardware blockers below gate promotion.
- **Blocker:** sleep = low-speed proxy (not ephys/CV-validated); site precision gated by ~7 in jitter;
  inch frame unverified (house_2 **not** verified cooler); ROI names provisional; temperature is an
  outside-air **proxy** (no shelter thermistor) and a covariate on both the animal and UWB paths;
  thermal vs social vs individual-habit not separable even over the 8 days (needs a shelter thermistor
  or ephys).
- **Next:** more rest days + a shelter-temperature logger (or ephys) to move "sleep" and "microclimate
  preference" from proxy to validated; georeference + ROI confirmation to place sites physically and
  test a real shade/cool-side hypothesis; CV corroborates only visible shelter-resident periods
  (lower bound).

### Cross-cutting prerequisites (unblock D2 & D3)
- **Georeference the WISER frame** — tooling built & self-tested (2026-07-01); awaiting the
  ≥6-pole dwell survey (`configs/wiser_georef_survey.csv` → `scripts/georeference_wiser.py`).
  [plan](../implementation_plan/2026-07-01-wiser-georeferencing.md)
- **Confirm the ROIs** — run `place_wiser_rois.py`, set `confirmed=true` (names sleep sites +
  refuge/home claims).
- Weather↔WISER alignment (±5 min) and the ≥1 m proximity floor remain as noted above; implement
  the `analyze_formal_recording.py` stub (gap detection / smoothing / session QC) for real sessions.

## Deferred (not on the publishability path)

Cross-modal integration, tracked in their own change logs, not required to publish the WISER
behavioral findings: environmental-audio Phase-2 (WISER/weather/audio merge, diurnal figures) —
see [`change_log/2026-06-29-environmental-audio-pipeline.md`](../change_log/2026-06-29-environmental-audio-pipeline.md);
and WISER×CV shelter-occupancy integration — see the CV shelter change log.
