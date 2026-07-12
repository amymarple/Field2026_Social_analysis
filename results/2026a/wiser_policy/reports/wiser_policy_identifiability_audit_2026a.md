# WISER measurement-context audit — policy-identifiability Phase 1

- **Auditor:** `wiser-measurement-auditor` (read-only measurement-context audit)
- **Audited run:** `wiser/outputs/policy_identifiability_2026-06-28_to_2026-07-06/`
- **Run type:** FORWARD-prediction identifiability ladder (hierarchical semi-Markov: leaving hazard +
  destination choice). NOT reward inference.
- **Generated (UTC):** 2026-07-10T06:28:48Z
- **Repo git commit at audit:** 384d1d019d914c19daa3411b2397adeca5e29812
- **Run git commit (manifest):** 384d1d019d914c19daa3411b2397adeca5e29812 (build stage)
- **Verdict:** **Partially auditable / weaker provenance than CV.** Provenance is unusually complete
  for the WISER side, but carries the structural WISER gap (no `measurement_context` sidecar, no
  per-row `mc_run_id`). The five negative/positive headlines are **NOT artifacts of measurement
  regime** — they survive stratification by validity/gap/jitter and by night regime — but the
  individual arm is **power-limited** and one social feature is **sub-jitter-floor**, so several
  verdicts are correctly read as candidate + lower-bound, not confirmed.

---

## 1. Provenance completeness (run_manifest.json)

Required keys — status:

| Key | Present | Value / note |
|---|---|---|
| `git_commit` | ✅ | 384d1d0… (build stage) |
| `generated_utc` | ⛔ **MISSING** | No generation timestamp stamped in the manifest (only filesystem mtime). |
| `units` | ✅ | "inches (WISER native, UNVERIFIED offset origin)" |
| `timestamp_method` | ✅ | "Unix ms UTC -> naive UTC (time_utils.convert_timestamps)" |
| `jitter_floor_in` | ✅ | 7.0 (in `params` and `registration`) |
| `night_window` | ✅ | 21:00→05:00, tz_offset −4 |
| thresholds | ✅ | `params`: epoch_s 5.0, min_dwell_s 3.0, social_window_s 10.0, moving_thr_inps 12.0, gap_factor 5.0, social_radius_in 39.37 (=1 m) |
| exclusions / caveats | ✅ | 5 caveats (Sova cutoff, refuge_4 burrow under-count, gaps = unknown, weather non-causal, whole-night blocks) |
| georeference / bounds | ✅ | `registration`: status UNVERIFIED, physical_transform absent, roi_placement_confirmed true, min_resolvable_distance_in 14.0 |
| dedup accounting | ✅ | `load_log`: 14,695,344 concatenated → 12,459,676 after dedup (2,235,668 dup rows removed); key `shortid+ts_raw+x+y` — the CSV/SQLite double-count guard is working |

`filtering_log.txt` is **absent**; its role is served by `run_manifest.params` +
`configs/environment_map/2026-06-28_to_2026-07-05.yaml` + `_progress.log` (6-stage pipeline log).
Thresholds are recoverable, so this degrades gracefully. I confirmed
`configs/wiser_to_field_transform.json` is **absent** → georeference genuinely UNVERIFIED.

**WISER-specific provenance gap (the defining weaker-than-CV item):** there is **no per-run
`measurement_context` sidecar and no per-row `mc_run_id` stamp**. The 21,443 leave rows and 6,715
destination rows cannot be joined back to a config-hash manifest the way the CV pipeline's rows can.
Provenance here is *manifest-level*, not *row-level*.

**Additional provenance notes**
- This run was produced with the **reduced (`--fast`) permutation budget**: `results.json` shows M4
  conditional-permutation `n_perm=20` and M5 time-shift `n_perm=15` (report footer: "Permutations:
  20"), not the default 60. `n_perm` is recorded in `results.json` but not in `run_manifest.json`.
- The modeling stage (`analyze_policy_identifiability.py`, Stages A0–M5) is a **separate interpreter
  run** whose git commit / UTC are not separately stamped; the manifest captures the build stage only.
- `calculation_error` and `battery_voltage` are loaded but **never gated** (per the QC helpers) —
  validity rests on anchors/gap/jump/bounds/cutoff only. Standing WISER QC gap, not specific to this run.

---

## 2. QC / measurement-process audit (404 strata)

n-weighted over all in-night fixes: **valid_frac ≈ 0.984, gap_frac ≈ 0.005.** Ranges: valid_frac
[0.489, 1.0], gap_frac [0.0, 0.052], jitter_proxy [12.5, 178.8 in/s].

Per-night (n-weighted):

| Night | n fixes | valid_frac | gap_frac | median jitter (in/s) | regime |
|---|---|---|---|---|---|
| 06-28 | 612,169 | 0.958 | 0.0112 | 30.5 | release, 6 rats (Sova present) |
| 06-29 | 559,603 | 0.986 | 0.0042 | 21.2 | early |
| 06-30 | 567,254 | 0.993 | 0.0033 | 19.2 | **wet** |
| 07-01 | 569,433 | 0.993 | 0.0033 | 20.3 | **wet** |
| 07-02 | 566,483 | 0.987 | 0.0036 | 19.4 | clean, highest support |
| 07-03 | 567,679 | 0.992 | 0.0034 | 18.4 | **burrow** |
| 07-04 | 535,398 | 0.977 | 0.0064 | 18.8 | **wet + fireworks + burrow** |
| 07-05 | 431,820 | 0.986 | 0.0045 | 21.3 | **truncated + burrow** |

**Where the degraded strata actually live:** all 21 strata with valid_frac < 0.7 are the **`edge`
(open-field) pseudo-ROI** — jitter_proxy 95–179 in/s, far from anchors — and they total only **0.12%
of fixes**. Critically, **`edge` never enters the decision tables**: leave/destination decisions are
counted only for resident-in-named-ROI epochs (houses valid_frac ~0.98–1.0). So the low-validity
strata do **not** contaminate the leaving-hazard or destination-choice numbers. This is the single
most important reason the negative verdicts are not a degradation artifact.

**refuge_4 dropout regime is visible and handled:** on burrow nights the refuge_4 occupancy strata
show depressed valid_frac (0.85–0.94 vs 0.94–1.0 off-burrow) and elevated gap_frac (up to 0.052 on
07-04). The audit still measures those fixes (under-count), but the decision tables exclude them (see
§3).

---

## 3. refuge_4 burrow exclusion + Sova removal (verification)

- **refuge_4 leave rows on burrow nights (07-03/04/05): 0.** All 457 refuge_4 leave rows fall on
  non-burrow nights (06-28..07-02). `leave_decisions[roi==refuge_4 & burrow==1]` = **0 rows**.
  `is_dropout_region` = 0 across all leave rows. Correct — a below-plane dropout is never manufactured
  into a "departure."
- **Sova (12409):** present only on night 06-28 (252 leave epochs); 0 rows on every later night.
  06-28 = 6 rats, all later nights = 5. Matches the tag cutoff (`valid_until` 2026-06-29 15:00 EDT)
  and the manifest caveat.
- **Destination action space = 9 ROIs** (houses, refuges 1–4, foods, tunnel) → reward gate
  `action_space_adequate` legitimately true.

---

## 4. Frame-gating (unverified inch frame)

No absolute direction / heading / bearing appears anywhere in the feature sets (grep-confirmed).
Outcomes are topological (which ROI is left / entered next). Metric features audited:

| Feature | Used in | Realized range | Floor-safe? |
|---|---|---|---|
| `dist_to_edge_in` | M1/M2 layout | min 16.3 in, median 164 in, **0% < 14 in** | ✅ all values ≥ 16 in (coarse; above the 14-in resolvability limit in practice) |
| `n_within_1m` | M5 social | count at 39.37 in = 1 m radius | ✅ ≥ 1 m, respects the floor |
| `mean_others_dist_in` | M5 social | 1.2% < 14 in, min 4 in | ⚠️ mostly coarse, small sub-floor tail |
| `nn_dist_in` | M5 social | **52% < 14 in, 23% < 7 in, min 0.1 in** | ⛔ sub-floor: most values are below the min-resolvable distance and a quarter below the jitter floor |

**Finding:** the layout arm is frame-safe (its only metric feature stays coarse). The **social arm
mixes a floor-safe count (`n_within_1m`) with a sub-jitter-floor continuous distance (`nn_dist_in`)**.
Two tags at ~7 in jitter each give a nearest-neighbour separation with ~10 in compound uncertainty; a
`nn_dist_in` of 0.1–14 in is not physically resolvable. Because the social arm is **NO-GO**, including
an unreliable fine feature is **conservative** (a noise feature cannot manufacture a transferable
increment, and the time-shift null confirms z=0.92). But it means: **no `nn_dist_in` coefficient may
ever be read as behavioral**, and any future social *claim* must be gated on `n_within_1m` (≥1 m). No
headline rests on absolute direction or fine (<14 in) metric distance — the frame blocker is respected
for every reported conclusion.

---

## 5. Are the NEGATIVE verdicts an artifact of measurement regime? (per-stratum)

**Individual arm (M4).** Personalization Δbits, joined to night regime:

| Night | indiv Δbits | regime | support (leave epochs) |
|---|---|---|---|
| 07-02 | **−0.0251** (most negative) | **clean** | highest (3,328) |
| 07-01 | −0.0029 | wet | 2,578 |
| 07-04 | −0.0016 | wet+fireworks+burrow | 2,117 |
| 06-29 | −0.0012 | early | 3,248 |
| 07-03 | −0.0002 | burrow | 2,795 |
| 06-28 | −0.0002 | release/6-rat | 2,995 |
| 07-05 | **+0.0018** | truncated+burrow | 1,865 |
| 06-30 | **+0.0025** | **wet** | 2,517 |

The negativity is driven by the **cleanest, highest-support night (07-02)**; the two *positive* nights
are a wet night (06-30) and a truncated+burrow night (07-05). Degraded-vs-clean median Δbits are
essentially identical (−0.0005 vs −0.0002), both centred on zero. **If measurement degradation were
masking a real individual policy, clean nights would show the strongest positive gain — the opposite
is observed** (the clean high-support night shows the strongest anti-personalization = held-out
over-fit). This is the signature of genuine absence of a transferable individual policy, not a
sensor-path artifact. No animal has a robustly positive median (12395 median +0.0023 but mean −0.010,
dragged by −0.099 on 07-02). **Not a measurement artifact.**

**Power caveat:** `A0.individual_arm_supported = true` measures *state coverage* (43 multi-animal
comparable strata), **not statistical power**. With only ~8 outer night-blocks, whole-night holdout,
per-animal min 112 leave epochs (12395/07-05), and a 20-permutation null, power to detect a *small*
(<0.003 bits) personalization gain is limited. Read M4 as **"no LARGE / transferable individual
policy" — a lower bound on effect size — not proof of exact zero.**

**Social arm (M5).** Δbits ≈ 0 on both regimes; time-shift z = 0.92. The negative verdict does not
concentrate in degraded strata and survives the sub-floor-feature caveat (§4). Robust NO-GO for any
≥1 m-resolvable social increment.

---

## 6. Classification of each headline

| # | Headline | Classification | Basis |
|---|---|---|---|
| 1 | **Individual arm NO-GO** (median −0.0005; frac+ nights 0.25; z −0.72) | **Behavioral (true negative) + lower-bound on power** | Negativity in clean/high-support strata, not degraded; decisions from high-validity ROIs; but 8 night-blocks + 20 perms = under-powered for a small effect |
| 2 | **Social arm NO-GO** (Δbits ≈ 0; z 0.92) | **Behavioral (true negative) for the ≥1 m-safe part; sub-floor `nn_dist_in` is a gating caveat, not a threat** | Verdict robust to the conservative inclusion of a sub-floor feature; time-shift null flat |
| 3 | **Matched-choice 1/9 — 12386 (Nox) stable house preference** | **Behavioral (candidate) — frame-safe** | Topological house_1-vs-house_2 choice (no metric/direction); transfer error 0.054 < 0.15 across 8 nights; departs indifference by 0.43; not concentrated in a degraded night; Nox's refuge_4 dropout is on the *excluded* burrow nights, not houses |
| 4 | **Reward feasibility NO-GO** | **Structurally correct feasibility verdict (not a measurement question)** | Gate false because M4/M5 both NO-GO + stated identifiability logic (unobserved odor/temp/food/habituation → observationally-equivalent rewards) |
| 5 | **Nested ladder** 0.878→0.859 (layout skill +0.021)→+weather ≈0→+shared-use ≈0 | **Layout skill = behavioral (small, real, frame-safe); weather & shared-use = null; observed-state Markov-sufficient (history Δbits −0.0012)** | Layout skill from ROI topology + dwell; weather Δbits −0.0009 at the *decision* level (distinct from weather's measurement-quality role); shared-use ≈0 even under optimistic global leave-focal-out |

Shortid → animal (from `configs/rat_identities.csv`): 12378 Siesta, 12380 Hypnos, 12386 Nox, 12395
Sen, 12407 Dormi, 12409 Sova (removed 06-29 15:00 EDT). `shortid` ≠ animal — resolved here.

---

## 7. Weaker-provenance verdict

**Partially auditable / weaker provenance than CV.**

- **Auditable at manifest level and robust:** the refuge_4 burrow exclusion, Sova cutoff, dedup
  double-count guard, night window, thresholds, the frame-gating of every *headline* claim, and the
  measurement-process stratification that shows the negative verdicts are behavioral (degraded strata
  = `edge`, which never enters the decision tables).
- **Lower-confidence because of missing/weaker provenance:** (a) no per-row `measurement_context` /
  `mc_run_id` → the 21,443 + 6,715 decision rows cannot be re-joined to a config-hash manifest; (b)
  the run used the reduced `--fast` permutation budget (20/15), so the exact z-scores are smoke-level
  — the *direction* is safe (point estimates fail every GO gate regardless) but the calibrated
  z-values are not publication-grade; (c) M4 power is coverage-adequate but statistically thin (8
  night-blocks); (d) `generated_utc` and modeling-stage provenance are not stamped.

This is genuinely weaker than the CV pipeline's row-level `measurement_context`; do not force it to
CV-level confidence.

---

## 8. Recommendation — smallest next actions (ANALYSIS_STATUS vocabulary)

Keep the run **⚠️ candidate**; do **not** re-fit or re-tune (nothing here is a fit problem). In order:

1. **Re-run the modeling stage WITHOUT `--fast`** (default 60 perms) before quoting any z-score toward
   confirmed. Cheap; the verdict direction is already safe. *(Smallest action that lifts the two
   NO-GO z-scores out of smoke territory.)*
2. **Design/build a WISER `measurement_context` sidecar + per-row stamp mirroring the CV pattern** —
   the standing provenance limiter (follow-up PR, not part of this audit). Would let leave/destination
   rows be joined back to a config-hash manifest and close the row-level gap.
3. **Add `generated_utc` to `write_run_manifest`** and stamp the modeling-stage commit/UTC in
   `results.json` (one-line manifest fixes).
4. **Relabel M4 `individual_arm_supported` as `state_coverage_ok`** (or add an explicit power note):
   "supported" reads as "well-powered," which A0 does not establish.
5. **Gate the surviving positive finding** (Nox house preference) explicitly as topology-only and
   dispatch the sibling **`cv-measurement-auditor`** on CH05/CH06 (and the new fog-free CH07/CH08
   interior cams) to check whether Nox's house_1-vs-house_2 preference is corroborated inside the
   shelter — WISER cannot see *inside* the house, only ROI membership, and cannot tell a solo
   occupant from a huddle.

⛔ **Blocker unchanged:** every spatial/directional promotion remains gated on a pole-survey
georeference (`configs/wiser_to_field_transform.json` absent → UNVERIFIED inch frame). The current run
respects this (topology + coarse ≥14 in distances only); do not upgrade any claim to physical
placement or absolute direction until the survey passes QC.

---

## 9. Sibling handoff

Dispatch **`cv-measurement-auditor`** for the Nox house-preference cross-check (huddle vs solo,
inside-shelter occupancy through CH05/CH06 glass + fog-free CH07/CH08 interior cams). WISER is the
fog-immune reference for *near-shelter* occupancy; CV resolves *inside/huddle* that UWB cannot. The
bridge is `scripts/analyze_sleep_site_cv_crossval.py` (asymmetric reconciliation — never assume the
two agree).
