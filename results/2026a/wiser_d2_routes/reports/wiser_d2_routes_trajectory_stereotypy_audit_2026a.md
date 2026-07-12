# WISER Measurement-Context Audit — Trajectory Stereotypy (Phase A)

- **Auditor:** wiser-measurement-auditor (read-only)
- **Generated (UTC):** 2026-07-07T16:16:44Z
- **Audit commit:** 9226f0910399c5806c13c1c7ffa41398f0adc4ff
- **Audited run:** `wiser/outputs/trajectory_stereotypy_2026-06-28_to_2026-07-06/`
- **Run manifest present:** yes (`run_manifest.json`, `analysis="trajectory_stereotypy_phase_a"`)
- **Nights:** 2026-06-28 → 2026-07-05 (8) · window 21:00–05:00 EDT (tz −4)
- **Animals:** Siesta 12378 · Hypnos 12380 · Nox 12386 · Sen 12395 · Dormi 12407 (Sova 12409 dropped)

## Verdict

**Partially auditable / weaker provenance than CV — but unusually strong for a WISER run.**
This is one of the more disciplined WISER analyses in the repo: the manifest is nearly complete,
the headline numbers reproduce exactly from the CSVs, weather is treated as a covariate (not
regressed out), the dropout concern is checked rather than assumed, and every spatial claim is
gated on the unverified inch frame. The headline conclusion — *stabilization is real; stabilized
space-use is MOSTLY SHARED (environment/road-driven), not individual memory or specific social
following; only Dormi shows a weak individual signature* — is **supported by the artifacts and does
not over-claim.** Residual conclusions are lower-confidence only because of the structural WISER
provenance gap (no `measurement_context` sidecar, no per-row `mc_run_id`) and two threshold caveats
below, not because any number failed to reproduce.

Using `ANALYSIS_STATUS.md` vocabulary: this remains a **⚠️ candidate** finding. Nothing here promotes
to ✅ confirmed while the **⛔ georeference blocker** stands, but the run is clean enough to keep as a
candidate with the stated caveats.

## 1. Provenance completeness

| Required key | Present? | Value / note |
|---|---|---|
| `git_commit` | yes | 9226f09 (matches audit HEAD) |
| `generated_utc` | yes | 2026-07-07T16:12:54 |
| `units` | yes | "inches (WISER native, UNVERIFIED offset origin)" |
| `timestamp_method` | yes | unix_ms → naive UTC (`time_utils.convert_timestamps`) |
| `jitter_floor_in` | yes | **3.39** (see gap G-2 — differs from documented ~7 in) |
| georeference / bounds status | yes, noted | caveats list "inch frame UNVERIFIED (no georeference)"; transform file **absent** (verified) |
| dedup / double-count control | yes | `dedup_key=shortid+ts_raw+x+y`; 2,235,668 dup rows removed (06-30 cumulative dump overlap) — matches loader contract in CLAUDE.md |
| wet nights flagged | yes | 06-30 / 07-01 / 07-04 |
| fireworks handling | yes | 07-04 excluded from time-coupling |
| tag cutoffs | yes | Sova 12409 dropped; tunnel ROI auto-expires 06-29 07:00 |

Provenance is **more complete than the typical WISER run** — the dedup ledger, per-file row counts,
per-night covariates, and explicit caveat list are all present.

### Provenance gaps (WISER-structural + run-specific)

- **G-1 (structural, expected):** No per-run `measurement_context` sidecar and **no per-row
  `mc_run_id` stamp.** Rows cannot be joined back to a config-hash manifest the way the CV pipeline
  allows. Every stratified fraction below is auditable only at the aggregate/per-night level, not
  re-derivable per row against a frozen config hash. This is the defining reason the verdict stays
  "weaker provenance than CV."
- **G-2 (run-specific, load-bearing):** `jitter_floor_in = 3.39 in` (from `tag_reports_2026-06-30`
  p50) is used, while the documented stationary fixed-position floor is **~7 in median (p95 ~15 in)**.
  The run bins occupancy at 8 in (≥ 3.39 and just above 7), so the occupancy grid itself is defensible.
  But any language that treats 3.39 in as "the jitter floor" understates real precision by ~2×. The
  8-in bin is the number that protects the spatial claims; **3.39 in should not be cited as the
  precision floor.** Report header says "~3.39 in" — recommend it read "occupancy bin 8 in ≥ documented
  ~7 in jitter floor" instead.
- **G-3:** `calculation_error` and `battery_voltage` are loaded-but-**never gated** (repo-wide QC gap,
  per the skill). Not fixable in this run, but the composite `valid` flag does not incorporate them.

## 2. QC / flag fractions (whole dataset, pre-window; from `cleaning_log.md`)

| flag | fraction |
|---|---|
| low_anchor_flag | 0.00445 |
| gap_flag | 0.00442 |
| jump_flag | 0.00619 |
| outside_provisional_bounds | 0.00019 |
| after_tag_cutoff | 0.00119 |
| **valid** | **0.98421** |

Night-window valid fixes retained: 4,231,448. QC is clean; `gap_flag` and `low_anchor_flag` are both
< 0.5% overall. `jump_flag` (0.62%) is the largest, consistent with jitter-driven raw-speed spikes,
and jumps are flagged not interpolated.

## 3. Stratified findings

### 3a. Wet-hay-wall dropout check (the central artifact concern) — **VERIFIED, does NOT concentrate on wet nights**

Recomputed from `coverage_summary.csv`:

| stratum | mean gap_frac | max gap_frac | mean low_anchor | mean valid_frac |
|---|---|---|---|---|
| WET (06-30/07-01/07-04) | **0.0043** | 0.0099 | 0.0040 | 0.9878 |
| DRY (5 nights) | **0.0057** | 0.0143 | 0.0030 | 0.9812 |

The report's claim — *`gap_frac` stays low (<1.5%) on all nights and the aggregate curve is not
dropout-driven* — **holds**. Wet-night gap fraction is actually *lower* than dry, and the single
highest gap night is the **dry** first night (06-28, max 0.0143). The wet-hay-wall dropout regime
does **not** show up in aggregate `gap_frac` for this run. Two caveats on that reassurance:

- Aggregate `gap_frac` is a **whole-arena** measure. Wet-hay-wall dropout is spatially localized to
  one bottom-right low-rank shelter and one (unknown-rank) animal; a per-tag/per-ROI gap check inside
  the candidate hay-wall ROIs (`house_2`/`refuge_2`/`refuge_4`) would be a stronger test than the
  arena-wide fraction. The current check is *necessary but not sufficient* to fully retire the
  concern. It is enough to say the aggregate stabilization curve is not dropout-driven.
- Social rank is not a data column, so "the low-rank animal" cannot be identified in-frame; the
  dropout regime cannot be pinned to a named tag here.

### 3b. Fireworks / QC-dip night 07-04 — handled correctly

07-04 carries the highest QC stress: `low_anchor_frac` up to **0.0219** (Sen) and **0.0108** (Nox),
lowest `valid_frac` (Sen 0.9588), and Nox's `median_dt_s` inflated to 0.267 (vs ~0.228). It is a
**wet + fireworks** night, correctly **excluded from time-coupling**. Its occupancy point still feeds
the stabilization curve — acceptable because valid_frac is still ≥ 0.96, but the point should be read
with the same caution the report gives 07-05.

### 3c. Truncated night 07-05 — flagged, verified

07-05 has ~77k–90k fixes/animal vs ~113k on 07-03 (**~20–25% fewer**), matching the report's "backup
ended ~23:30, ~25% fewer fixes." Report flags it and says "treat its point cautiously." Correct. Its
stabilization values (cos_ref 0.96–0.99) are high, but truncation truncates the *late* window, which
could bias the last-night reference comparison — the caution is warranted, not removable.

### 3d. Stabilization (Claim 1)

`stabilization_metrics.csv`: mean `cos_ref` rises from ~0.14 (06-28) to ~0.96 (07-05). Per-animal
plateau-night estimates reproduce the manifest's `stabilization_date_estimate`. The report's own
**caution is the right one**: a rising similarity-to-late-reference is *consistent with* stabilization
but is also inflated by shared shelter/road use, and cannot by itself distinguish individual route
memory from shared-corridor emergence. The report does not over-claim memory here.

### 3e. Shared-vs-individual (Claim 2) — headline numbers reproduce exactly

- Raw inter-animal occupancy cosine mean ≈ 0.90; edge cosine ≈ 0.95 (`transition_edge_similarity.csv`). ✓
- **Residual Pearson mean = −0.0147** (range −0.141 to +0.101) — reproduces "collapses to −0.01." ✓
  Report correctly warns to read the **correlation**, not the residual cosine (0.86, inflated by
  non-negativity). Good discipline.
- **Label-permutation:** **0/10** pairs above null (z>2); **4/10** below (z<−2), and all four below-null
  pairs contain **Dormi (12407)** — verified: (Siesta,Dormi) z=−2.23, (Hypnos,Dormi) z=−2.07,
  (Nox,Dormi) z=−3.61, (Sen,Dormi) z=−3.00. The "only Dormi shows a weak individual signature" claim
  is exactly what the data say. ✓

### 3f. Real-time coupling (Claim 3) — reproduces, with one small precision note

- **circular-shift null:** 10/10 pairs beat it on both xy_corr and proximity (z>2). ✓
- **day-shuffle null:** on **proximity, 0/10** beat it (max z=1.65). On **xy_corr, 2/10** marginally
  exceed z>2 — Siesta–Nox (z=2.09) and Siesta–Dormi (z=2.05). The report states a flat "0/10 beat the
  day-shuffle null," which is true for proximity but slightly understates the xy_corr result.
  **Over-claim in the conservative direction** (it makes the "no specific following" conclusion look
  marginally stronger than the data): worth a one-line correction to "0/10 on proximity, 2/10 marginal
  on xy-correlation." The day-shuffle null has only **n=42** permutations (vs 100 circular / 200
  label), so those two z≈2.05–2.09 values are borderline and neither survives on proximity — the
  qualitative conclusion (no standout dyad; largely shared diurnal/environmental structure) is intact.

## 4. Frame-gating (the ⛔ georeference blocker)

The `wiser_to_field_transform.json` file is **absent** (verified) → the inch frame is unverified.
Every spatial/directional claim is a **⛔ blocker item** until a pole survey confirms the georeference.
The report gates this correctly: no directional/physical claims, "no wall-following/shelter→food
geometry," and it explicitly relies on within-frame comparisons (residual-correlation collapse,
label-permutation) that are **immune to the missing georeference** because they compare animals in the
same frame. `wiser_rois.json` is `confirmed:true` **in the inch frame**, so ROI *membership* and the
transition edges are valid — but the report also correctly flags that the top edges
(`house↔food`) are **jitter flips between co-located labels**, not travel (`food_*` sits inside
`house_*`). That self-caveat is accurate and important.

## 5. Per-claim classification

| # | Claim | Classification | Basis |
|---|---|---|---|
| 1 | Trajectories stabilize 06-28→07-05 (0.14→0.96) | **mixed (behavioral + shared-structure inflation)** | rising curve real, but inflated by shared shelter/road; not proof of individual memory. gap_frac not dropout-driven (verified). |
| 2a | Stabilized space-use is MOSTLY SHARED (road/environment) | **likely behavioral signal** | residual Pearson −0.01; 0/10 label-perm above null; edge cosine 0.95; within-frame, georef-immune |
| 2b | Only Dormi shows a weak individual signature | **likely behavioral (weak, candidate)** | all 4 below-null pairs are Dormi pairs (z −2.1 to −3.6); consistent internal evidence |
| 3 | Real-time synchrony exists but is common-drive, not specific following | **mixed → lower-bound-only for "specific following"** | beats circular-shift 10/10; day-shuffle 0/10 prox (2/10 marginal xy); no standout dyad. Fine following is Phase B / below jitter floor. |
| — | Any directional/physical route claim | **⛔ not supported (frame unverified)** | correctly withheld by the report |
| — | house↔food top transition edges | **measurement artifact** | co-located labels; jitter flips — correctly self-flagged |
| — | Wet-night similarity dips = behavior | **would be artifact IF claimed** — report correctly declines | gap_frac not concentrated on wet nights |

## 6. Over-claim scan — where the report pushes

1. **`jitter floor: ~3.39 in`** in the report header and manifest (G-2). Understates the documented
   ~7 in precision by ~2×. The 8-in occupancy bin is fine; the *label* is the problem. Lower-confidence
   for any sub-8-in interpretation. **Smallest fix: cite 8-in bin ≥ ~7 in floor, not 3.39 in.**
2. **"day-shuffle null beaten by 0/10 pairs"** (3f) — true on proximity, 2/10 marginal on xy_corr.
   Minor; conclusion holds. Recommend the one-line correction.
3. **Wet-hay-wall reassurance** rests on **arena-wide** gap_frac, not a per-ROI/per-tag check inside
   the candidate hay-wall shelters (3a). The aggregate claim is verified and correct; a per-ROI dropout
   check would fully retire the concern rather than mostly retire it.

None of these overturn the headline. The run does not over-claim behavior, memory, or social bonds.

## 7. Weaker-provenance verdict — what remains auditable vs lower-confidence

- **Auditable now (aggregate/per-night, reproduced from CSVs):** dedup ledger, QC flag fractions,
  wet-vs-dry gap concentration, 07-04 QC dip, 07-05 truncation, residual Pearson, label-permutation
  z-scores and the Dormi result, circular/day-shuffle null-beat counts, frame-gating, ROI-edge artifact.
- **Lower-confidence (missing provenance):** no per-row `mc_run_id` means none of the above can be
  re-joined to a frozen config hash or replayed per row; `calculation_error`/`battery_voltage` never
  gated; the 3.39-vs-7-in floor mismatch; the dropout reassurance is arena-wide not per-ROI.

## 8. Sibling handoff

Claim 1 (stabilization = "sleep/rest site" reuse) and any "is the rat actually *inside* the shelter /
is a co-location cluster a huddle" question is **CV's to answer, not UWB's**. Recommend dispatching
**`cv-measurement-auditor`** on CH05/CH06 for the shelter-occupancy cross-check, via the existing
bridge `scripts/analyze_sleep_site_cv_crossval.py` (WISER = fog-immune reference; CV catches huddles
WISER cannot resolve). The check runs both ways — do not assume they agree.

## 9. Smallest next action

**Relabel the jitter floor in the report/manifest from "~3.39 in" to the documented ~7 in floor
(state the 8-in occupancy bin sits ≥ that floor), and correct "day-shuffle 0/10" to "0/10 proximity,
2/10 marginal xy-correlation."** Both are text/label edits, not a re-fit — no re-tune is warranted;
the numbers already reproduce. The larger structural follow-up (separate PR, not this audit) is to
**design/build a WISER `measurement_context` sidecar + per-row `mc_run_id` stamp mirroring the CV
pattern** so future runs are row-level auditable.
