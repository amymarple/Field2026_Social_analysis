# WISER Measurement-Context Audit — Route-vocabulary validation (Stage 1, PROVISIONAL)

- **Auditor:** `wiser-measurement-auditor` (read-only measurement-context audit; no analysis code/threshold/config/DB touched)
- **Audited run:** `wiser/outputs/route_vocabulary_validation_2026-06-28_to_2026-07-10/original_3s_filtered_bouts/`
- **Run artifacts:** `run_manifest.json`, `validation_report.md`, `README.md`, `tables/*.csv`, `plots/*.png`
- **Run commit:** `62222ccdb78b805f13bf88be6a0127850e505624` (audit run at the SAME commit)
- **Audit generated (UTC):** 2026-07-12T00:42:04Z
- **Segmentation audited:** `original_3s_filtered_bouts` — `implemented_provisional`, `provisional:true`
- **Frame status:** inches, **UNVERIFIED offset origin** (`configs/wiser_to_field_transform.json` absent → transform helpers are no-ops). Module 11 (route/corridor selection) = ⛔ blocked in `configs/behavioral_policy_modules.yaml`.

## Verdict of THIS audit

**Partially auditable — provenance richer than a bare WISER run but still weaker than the CV pipeline.**
The manifest carries the provisional/segmentation label, git commit, θ/σ/seed/night-window/animals/criteria
and a strong caveat block — better than most WISER outputs. But it has **no CV-style
`measurement_context` sidecar, no per-row (per-bout) `mc_run_id` stamp, and no fix-level `flag_summary`
QC fractions**, so bouts cannot be joined back to a config-hash manifest and the dropout/anchor burden
behind the 1692 bouts is not recorded. Conclusions below are split into **auditable** vs **lower-confidence**.

**On the science as labelled:** the **NOT-A rejection (no discrete route vocabulary resolvable above the
jitter floor at this segmentation)** is measurement-sound as stated. The **C-vs-B sub-call ("repertoire not
closing")** is **regime-confounded on small n_test** and should be downgraded further than the report does.
Every claim remains correctly gated to topological/relative on the unverified inch frame.

---

## 1. Provenance completeness

Reusing `ANALYSIS_STATUS.md` vocabulary (✅ present / ⚠️ present-but-thin / ⛔ blocker / ◻️ missing).

| Required field | Status | Note |
|---|---|---|
| `git_commit` | ✅ | `62222cc…`, matches report + this audit run |
| `generated_utc` | ✅ | 2026-07-12T00:40:39 |
| `units` | ✅ | `inches (WISER native, UNVERIFIED offset origin)` |
| `segmentation_id` + params + `provisional` flag | ✅ | id, `min_bout_s=3`, `min_disp_in=15`, `max_gap_s=2`, `resample_n=20`, `max_per_night=40`; `provisional:true` at 3 levels + explicit `label` + caveat #1 |
| `jitter_floor_in` | ✅ | 7.0 (matches the ~7 in median floor in `wiser_artifacts.md`) |
| `theta_in` / `sigma_mdl_in` / `endpoint_bin_in` | ✅ | θ=21 (3×floor), σ=7 (floor a priori), bin=42 (6×floor) — all correctly floor-anchored |
| `seed` | ⚠️ | base `seed:0` recorded; A2 states "averaged over 5 seeds" but the seed set/derivation is not in the manifest |
| `night_window_local` | ✅ | `[21,4]` |
| `animals` / cutoffs | ⚠️ | 5 tags listed (Sova `12409` correctly ABSENT). **But Hypnos `12380` is listed as an animal with no record that `apply_tag_cutoffs` dropped its fixes after `2026-07-09T03:35:41-04:00`** (see §2). |
| georeference / frame status | ✅ | `frame_note` states unverified inches → topological/relative only, Module 11 blocked, verdict ceiling B/C |
| `criteria` / `verdict` / `caveats` | ✅ | 7 criteria, verdict C with reasons, 8 caveats incl. the provisional + barn-light/4-rat caveat |
| `timestamp_method` | ◻️ **GAP** | absent. WISER is Unix ms UTC; the night-window binning method / DST handling is not recorded. Given the known **pandas `[ms]` datetime binning hazard** (MEMORY), the binning method is load-bearing and should be stamped. |
| fix-level QC (`flag_summary`) | ◻️ **GAP** | **No** `low_anchor_flag` / `gap_flag` / `jump_flag` / `outside_provisional_bounds` / `after_tag_cutoff` / `valid` fractions, and **no `min_anchors` / `anchors_used` threshold**. Only the *bout-level* filter is recorded, not the *fix-level* QC that fed it. `calculation_error` / `battery_voltage` are loaded-but-ungated repo-wide and their status is not recorded here either. |
| per-row provenance | ⛔ **WISER weaker-provenance gap** | No `measurement_context` sidecar, no per-bout `mc_run_id`. `tables/*.csv` rows can't be joined back to a config-hash manifest — provenance is genuinely weaker than the CV pipeline. |
| per-night × animal bout support | ◻️ **GAP** | `a0_support` gives medians + min only; there is **no per-night bout count**, so the reader cannot see how bouts distribute across the three regime windows in §2 (needed to audit the regime confounds). |

**Bottom line:** provenance is strong on parameters/scope but thin on **measurement QC** (no timestamp
method, no flag fractions, no per-night support, no per-row stamp). A downstream consumer cannot, from
these artifacts alone, quantify the dropout/low-anchor burden or verify the Hypnos cutoff.

---

## 2. Regime stratification — could the held-out results be sensor/regime rather than behavior?

The 13 nights are **not one regime**. Three windows (from `FIELD_OBSERVATIONS.md` Days 6/9/10/13 and
`rat_identities.csv`) partition the run, and they line up with exactly the parts of the curve that decide
the verdict. **A dropout/gap is "unknown," never "the rat left."**

**Stratum A — clean early nights (06-28 → 07-02, 5 nights).** Pre-burrow, pre-barn-light, 5-rat cohort
(Sova present only on the 06-28 night but ABSENT from the analysis `animals` — so night0 is missing one
animal that was in the paddock). This is the cleanest window and anchors the big endpoint-dominance signal.

**Stratum B — refuge_4 burrow dropout (07-03 → 07-07).** A **structural, weather-INDEPENDENT** UWB dropout:
>1 rat dug a burrow under shelter 4 (`refuge_4`) from ~07-03 01:00; the tag drops below the anchor plane →
`refuge_4` fixes vanish. Bouts that would originate/terminate at that endpoint are **under-sampled or
split** (the `max_gap_s=2` s rule breaks a bout at any >2 s dropout, and short remnants fail `min_disp=15`
in). Consequence: the **bout population itself is regime-conditioned** in this window — the `refuge_4`
endpoint is under-represented and surviving bouts skew shorter/straighter. This window is exactly where
A1's temporal-holdout curve flattens (train-last 07-03…07-07, novelty falling 0.19→0.11).

**Stratum C — refuge_4 removed + late regime (07-07 13:00 → 07-10).** Three compounded changes: (i)
`refuge_4` **physically removed** 07-07 13:00 → that endpoint disappears from the graph for all later nights;
(ii) **cohort 5→4** — Hypnos `12380` cutoff 07-09 03:35 (implant detaching → expect stationary/jittery/gap
fixes near the cutoff, a sensor artifact, not behavior); (iii) **south barn light ON** ~22:00 07-09,
inside the 21:00–04:00 active window → a novel directional cue that can reshape route/shelter choice on the
animal path. **All of A2's LOAO held-out nights live here** (four on 07-10, Hypnos on 07-08), and **the two
nights that decide B-vs-C (07-09/07-10) are in this stratum on small n_test** (270 then 120).

### 2a. The B-vs-C hinge (`novelty_saturates=False`) is regime-confounded
`novelty_saturates` = the last-3 cumulative splits' next-night novelty all <0.15 AND range <0.08. Observed
last-3 `novelty_next_night` = **0.114 (last 07-07) / 0.18 (last 07-08) / 0.117 (last 07-09)** → fails only
because of the **0.18 at the 07-08 split (n_test=270)**, with the tail resting on the 07-09 split
(n_test=120). Those late splits sit in Stratum C, where refuge_4 removal, the barn light, and the 4-rat
cohort would each **inflate apparent novelty** (new light-avoidance paths, a lost endpoint, a differently
sampling cohort). So the "repertoire is still open" reading **cannot be separated from regime-induced
novelty on the deciding nights**. The report's caveat #6 flags the coincidence; this audit's judgement is
that it should be a **downgrade, not just a caveat**: the C-vs-B call is **mixed/ambiguous**, not a clean C.

**Crucially, this does NOT touch the A-rejection.** NOT-A rests on `dict_beats_pca=False` (explicitly
non-load-bearing — flips at the bpp=32/σ=14 corner) and on shape being **continuous** (no finite-K MDL win),
neither of which depends on the late-night novelty. So the barn-light/4-rat/refuge_4 confounds degrade the
**C-vs-B sub-distinction only**, not the headline that there is no discrete vocabulary. That separation is
correct and is the run's main measurement-sound result.

### 2b. LOAO and geometry-null are not dropout/frame artifacts, but are thin
- **LOAO (A2):** `loao_generalizes=True`, but the decisive margins `E_other − E_null` are ≈0.8–1.7 in — on
  the order of the **seed sd** (±1.3–5.3). One animal (Nox `12386`) has **n_test=4, sd 5.3** → essentially
  uninformative. Hypnos `12380` is tested on 07-08 (n_test=16) near its implant-failure cutoff, and is the
  only animal with `E_other < E_own` (own dictionary worse). **All held-out nights are the late, regime-
  shocked Stratum-C nights** — generalization is never tested on the clean early nights. Verdict: a **weak
  pass**, dominated by the shared **endpoint chord** (`E_endpoint`≈6–13 in ≪ every dictionary ≈20 in).
- **Geometry-null (A5):** real dict (15.72 in) beats the endpoint+wiggle-matched Brownian-bridge null
  (18.7 in). Because the null inherits each real path's endpoints and RMS amplitude, this is a **matched
  differential**, not an absolute-frame claim — it is robust to the unverified frame and not created by
  dropout. It says real routes are *more shape-consistent than matched noise*, nothing about a rich or
  discrete vocabulary. Sound as a relative claim.
- **Shared-across-animals = endpoint graph, stated as measurement not biology:** the report says the thing
  that transfers across animals is the **shared endpoint graph (common locations)**, not a path vocabulary
  (A2 prose + claim table "supported (endpoints)"). This is correctly a **measurement claim.** Audit adds:
  shared endpoints most parsimoniously reflect **shared LAYOUT affordances** (all rats use the same
  houses/refuges/water/food), consistent with Module 6 and the standing finding that leaving/destination
  is governed by shared layout+dwell — it is **not** evidence of a shared cognitive route map. Keep it a
  layout/endpoint claim.

### 2c. Jitter-floor check on the shape signal
θ=21 in, σ=7 in and the endpoint grid (42 in) are all safely ≥ the 7 in floor. **But the "reusable shape
beyond endpoints" signal operates at/below the floor:** `E_chord`=7.88 in ≈ floor; `E_pn_shapedict`=**5.81
in < 7 in floor**; the reduction is only **~2.07 in**; and A3 PCA reaches ~4.17 in at M=4 (also sub-floor).
These survive only as **matched-null / model-comparison differentials** (null and real carry the same
jitter), so they are admissible as *relative* structure — but the **absolute magnitude of the reusable-shape
signal is sub-jitter-floor and must never be given a metric size or an above-floor geometric reading.** The
report never assigns it a physical size (good) but does **not explicitly flag that its magnitude is below
the floor** — recommend adding that.

---

## 3. Headline classification (measurement-supported vs needs more evidence)

Each headline classified as **likely behavioral signal · likely measurement artifact · mixed/ambiguous ·
lower-bound only**, gated on the provisional segmentation and the unverified frame.

| # | Headline (as reported) | Classification | Audit judgement |
|---|---|---|---|
| 1 | **Endpoints dominate** (`endpoint_explains_most=True`, share 0.988; global 177.89 → chord 7.88 in ≈ 99%) | **likely behavioral signal (endpoint/location structure)** — measurement-supported | Robust to frame (relative decomposition) and to dropout (population-level); the span (177→7.88 in) is far above the floor. It is an **endpoint-graph / Module-6 location claim, not a route claim.** The residual after endpoints (~7.9 in) sits at the floor, which *reinforces* "endpoints explain nearly all the resolvable variance." Auditable. |
| 2 | **Small reusable continuous curvature** (`shape_beyond_endpoints=True`, `beats_geometry_null=True`) | **mixed / lower-confidence** | Real as a **matched-null differential**, but its absolute scale (5.81 vs 7.88 in; ~2 in) is **sub-jitter-floor**, and the provisional filter + Stratum-B dropout bias toward short, near-straight, trivially self-similar bouts could inflate apparent "reusability." Keep it "small, low-dim, CONTINUOUS, relative-only"; add the sub-floor caveat; do not upgrade. |
| 3 | **No discrete vocabulary** (verdict NOT-A; `dict_beats_pca=False`) | **measurement-supported as a BOUNDED negative** | Sound, but bound it: "no discrete route vocabulary **resolvable above the ~7 in jitter floor at this provisional segmentation**." Jitter would smear any sub-floor discrete tokens into a continuous smear, so the negative cannot be unconditional. As labelled (provisional + falsification-first), acceptable; make the floor-bound explicit. |
| 4 | **Repertoire not closing** (`novelty_saturates=False`) | **mixed / ambiguous — regime-confounded** | The weakest headline. Decided by 07-08/07-09/07-10 splits (n_test 270→120) that coincide with refuge_4 removal + barn light + 4-rat cohort, all of which inflate novelty. Cannot separate open-repertoire from regime-induced novelty. **Downgrade from a caveat to "cannot resolve open vs closing on the deciding nights."** This is what tips B→C, so the **C-vs-B call inherits this ambiguity.** |

**Net:** the *falsification* result (rejecting a finite discrete shared route vocabulary) and the
*endpoint-dominance* result are measurement-supported as labelled; the *positive continuous-shape* and
*non-closure* results are floor-limited and/or regime-confounded and should stay explicitly lower-confidence.

---

## 4. Over-reads to fix (small, wording-level — no code/threshold change)

1. **`README.md` omits the provisional-segmentation label.** It carries the frame caveat but not
   "conditional on the original 3-second-filtered bout segmentation." A consumer reading only the README
   could over-read the verdict. Add the conditional line to README (the report + manifest already have it).
2. **Add the sub-jitter-floor flag to the reusable-shape result** (`E_pn_shapedict`=5.81 in < 7 in floor;
   ~2 in reduction) — admissible as a matched-null differential only; never a metric size.
3. **Bound the NOT-A negative to the jitter floor + segmentation:** "no discrete vocabulary *resolvable
   above ~7 in at this provisional segmentation*," not an unconditional absence of route tokens.
4. **Downgrade the C-vs-B call from "caveated" to "unresolved":** state plainly that the deciding late
   nights are regime-shocked (refuge_4 removal + barn light + 4-rat cohort) on small n_test, so B vs C is
   **not resolvable from this run** — only NOT-A is.
5. **Record the Hypnos cutoff in the manifest** (`after_tag_cutoff` for 07-09/07-10) so a consumer can
   verify `12380` was dropped after 07-09 03:35 rather than pooled as a live animal.

None of these change a number; they tighten wording/provenance so the verdict is not over-read.

---

## 5. Provenance gaps (summary, for the promotion gate)

1. ⛔ **No `measurement_context` sidecar + no per-row/per-bout `mc_run_id`** — the standing WISER weaker-
   provenance gap; `tables/*.csv` rows can't be joined to a config-hash manifest. Weaker than CV.
2. ◻️ **No `timestamp_method`** — night-window binning / DST handling unrecorded (pandas `[ms]` binning
   hazard makes this load-bearing).
3. ◻️ **No fix-level `flag_summary`** — `low_anchor_flag` / `gap_flag` / `jump_flag` /
   `outside_provisional_bounds` / `after_tag_cutoff` / `valid` fractions and the `min_anchors` threshold are
   absent; `calculation_error` / `battery_voltage` loaded-but-ungated status unrecorded. Dropout burden
   behind the 1692 bouts is not quantifiable from the artifacts.
4. ◻️ **No per-night × animal bout support** — regime-window contributions (Strata A/B/C) can't be read off.
5. ⚠️ **Hypnos cutoff not stamped** — `12380` listed as an animal with no `after_tag_cutoff` record.
6. ⚠️ **Only base seed recorded**; A6 bootstrap/prototype stability explicitly GATED (not run) — cluster
   stability is unestablished (report is honest about this).

---

## 6. Smallest next action

Reusing `ANALYSIS_STATUS.md` language, the finding stays **⚠️ candidate — PROVISIONAL**, and this is the
correct status; do **not** promote toward confirmed on this run, and do **not** re-fit/re-tune before
stratifying (already stratified above). The provenance limiter here is standard for WISER, so the specific
follow-up (a separate PR, not part of this read-only audit) is:

> **Design/build a WISER `measurement_context` sidecar + per-row (per-bout) stamp mirroring the CV pattern**
> — carrying `timestamp_method`, the `flag_summary` fractions (`low_anchor/gap/jump/outside_bounds/
> after_tag_cutoff/valid`), the `min_anchors` threshold, per-night × animal bout counts, and an explicit
> tag-cutoff record — so future route-vocabulary runs (and the forthcoming validated-leg / pause-merged
> re-run) are joinable to a config-hash and their dropout/regime burden is auditable per bout.

Alongside that, the science-side next step is the one the report already names: **re-run the identical
battery on `validated_locomotor_legs` + `pause_merged_episodes`** (Stage-1 gates A6/A8/full-null are
correctly held until then), and — for the C-vs-B question specifically — **re-evaluate `novelty_saturates`
on nights ≤ 07-08 only** (excluding the refuge_4-removal + barn-light + 4-rat Stratum-C shocks) to see
whether non-closure survives outside the regime window.

## 7. Sibling handoff

Not required for this run. The route-vocabulary question is intra-WISER (segmentation + geometry), and the
frame/floor limits are WISER's own. **If** the follow-up wants to validate that endpoint clusters are
real shelter/site *residence* (e.g., "is a route-endpoint cluster actually the rat inside a shelter/huddle
that UWB can't resolve"), dispatch **`cv-measurement-auditor`** on the CH05/CH06 (and now CH07/CH08
fog-free interior) shelter occupancy via the existing bridge
`scripts/analyze_sleep_site_cv_crossval.py` — CV is a lower bound on near-shelter occupancy (wall-edge
blind zone), WISER is the fog-immune reference. The check runs both ways; never assume they agree.
