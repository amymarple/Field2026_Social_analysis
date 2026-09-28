# WISER measurement-context audit — `wiser_policy` direction (cohort 2026a)

- **Auditor:** `wiser-measurement-auditor` (read-only measurement-context audit; no tracker/config/DB/output changes)
- **Targets:** the 14 in-repo `results/2026a/wiser_policy/reports/*.md` covering the 14-module hierarchical
  semi-Markov behavioral policy (modules 3, 5, 6, 7, 9, 10 + temporal + social-extension), plus the
  `wiser/ANALYSIS_STATUS.md` rows (Agent-policy identifiability; Approach/avoid; Destination & settlement;
  Locomotor-bout initiation) and their linked `change_log/` entries.
- **Repo git commit at audit:** `084d4c2e83fc2e27b1fcba4f05f75ffd1e1142e1`
- **generated_utc:** ~2026-07-13T03:00Z (derived from HEAD commit time 2026-07-12T22:50:40-04:00; the `date`
  and `python` binaries are sandbox-blocked, `git` and `echo`/`pwd` are not — noted as a tooling constraint,
  not a data limiter).
- **Scope note:** this audits whether each derived number is interpretable **as a measurement**. It is NOT a
  re-fit, re-tune, or re-analysis. Per instruction, off-repo raw run artifacts were treated as a limiter and
  the identifiability audit was **verified**, not redone.

## Overall verdict

**Partially auditable / weaker provenance than CV — and, for this run, MORE weakly provenanced than the
identifiability audit itself was**, because the off-repo run directories are absent (see §1). The
**measurement-supported statistical/state results are sound and frame-gated**; the **candidate biological/causal
readings are correctly quarantined** in every report; and the two load-bearing measurement corrections
(hysteretic-flicker fix; pseudoreplication → night-block) are **verified sound** (§3). The dominant limiters are
(a) **pseudoreplication-corrected but low outer-N** (~8–11 nights), (b) **jitter floor ~4–7 in** forcing
lower-bound onsets/leaves and ≥1 m proximity, (c) the **⛔ unverified inch frame**, and (d) **weaker provenance**
(no run_manifest/QC CSVs for this run, no WISER `measurement_context` sidecar, no per-row `mc_run_id`, `--fast`
permutations). Nothing in this direction licenses IRL/reward, individual-identity policy, dyadic social, attraction/
motivation, or route/navigation claims (§7).

---

## 1. Provenance completeness — and the run-artifact gap

| Item | Status | Note |
|---|---|---|
| Off-repo run dirs `D:\Field2026_analysis_out\2026a\` | ⛔ **ABSENT** | Only `cv_field_harvest/` present. **No `run_manifest.json`, no `filtering_log.txt`, no per-driver QC CSVs** (`nightly_qc.csv`, `A0_support*.csv`, `M5_social_increment.csv`, `approach_model_table.csv`, …) were available for THIS audit. |
| In-repo reports | ✅ present | 14 `.md` reports + 1 figure (`policy_identifiability__temporal_effects.png`); each carries provenance strings, definitions, formulas, scope guards. |
| `change_log/` ledgers | ✅ present | All 10 referenced entries exist and were cross-checked against the reports (§3). |
| Per-report provenance strings | ✅ partial | Decision-unit id, generated timestamps, `n_perm`, `min_disp`, `settle_min_s/conf_frac`, jitter floor, frame status are embedded in the report bodies. `git_commit`, `units`, `timestamp_method` are NOT restamped per report. |

**Graceful degradation:** no `run_manifest.json` was found under either default search root, so per the workflow this
audit is conducted **from the in-repo reports + change logs only**. Thresholds and exclusions are recoverable from
the report bodies, so the substance degrades gracefully — but the **row-level and CSV-level cross-checks the
identifiability audit performed (edge-strata fixe-counts, refuge_4 leave-row = 0, dedup accounting) cannot be
independently re-run here.** They are inherited from that audit, not re-verified against fresh CSVs.

**WISER-specific provenance gap (the defining weaker-than-CV item, unchanged):** there is **no per-run
`measurement_context` sidecar and no per-row `mc_run_id` stamp.** The leave/departure/bout/approach rows cannot be
joined back to a config-hash manifest the way the CV pipeline's rows can. Provenance here is *report-level*, not
*row-level*. A concrete symptom: the reports quote mutually different decision counts for the "same" object across
windows/configs (e.g. leaving epochs: identifiability audit **21,443** vs identifiability report **43,273** vs
social-extension **11,675**; settlements **452** vs **295** vs **321** across reports) with **no join key** to
reconcile them. Each is internally consistent, but the lack of a stamp means a reader cannot mechanically verify
which run produced which number.

**Loaded-but-ungated QC:** `calculation_error` and `battery_voltage` are loaded by the read-only loaders but
**never gated** — validity rests on anchors/gap/jump/bounds/cutoff only. Standing WISER QC gap, not specific to
this direction.

---

## 2. QC / flag context (inherited; no fresh CSVs)

No `nightly_qc.csv` / `*_qc.csv` was available for this run, so `flag_summary` fractions
(`low_anchor_flag / gap_flag / jump_flag / outside_provisional_bounds / after_tag_cutoff / valid`) **cannot be
recomputed here.** The best available QC stratification is the one the identifiability audit already performed on the
8-night policy build (carried forward as context, NOT re-verified):

- n-weighted **valid_frac ≈ 0.984, gap_frac ≈ 0.005**; per-night valid_frac 0.958–0.993, gap_frac 0.003–0.011.
- **All 21 strata with valid_frac < 0.7 are the `edge` (open-field) pseudo-ROI** (0.12% of fixes) and **`edge`
  never enters the decision tables** — leave/destination decisions are counted only for resident-in-named-ROI
  epochs (houses valid_frac ~0.98–1.0). This is the single most important reason the negative verdicts are not a
  degradation artifact.
- **refuge_4 burrow** nights show depressed valid_frac (0.85–0.94) and elevated gap_frac (up to 0.052 on 07-04),
  handled by exclusion (§3).

For the newly-audited modules (which extend to 11 nights, 06-28→07-08), **no QC table is available at all** — the
07-06/07/08 nights and the full burrow window/removal (07-03→07-07) are audited from report text only. This is a
real limiter on the 11-night modules.

---

## 3. Re-confirmation of the identifiability audit + two load-bearing corrections

### 3a. Does the identifiability audit's verdict still hold? — YES for the measurement verdict; STALE on one arm.

The audit's **measurement-context verdict is run-agnostic and holds:** "Partially auditable / weaker provenance than
CV"; degraded strata = `edge` (never enter decision tables); refuge_4 burrow leave-rows = 0; Sova (12409) cut
06-29 (06-28 = 6 rats, later = 5); dedup double-count guard working; every *headline* frame-gated (topological
outcomes; only metric feature `dist_to_edge_in` stays ≥16 in / coarse). **Confirmed — no reason to disturb it.**

**One material staleness finding the parent should know:** the audit was generated **2026-07-10** against a run with
**~21,443 leave rows** in which **BOTH** the individual arm (M4 median **−0.0005**, z **−0.72**) **and the social
arm (M5 Δbits ≈ 0, time-shift z 0.92)** were **NO-GO**. The current canonical `identifiability_report_2026a.md`
(**2026-07-11**, 43,273 leave epochs) has **M5 social REVERSED to a robust GO** (Δbits **0.0117**, time-shift z
**15.1**, day-shuffle z **30.4**, jitter-safe Δbits 0.0118, day-shuffle z 25.6) and **M4 net-positive but still
negligible** (median **+0.00053**, z **+2.32**). So:

- The audit's §4/§5/§6 reasoning that "the social arm is NO-GO, therefore including the sub-floor `nn_dist_in`
  feature is *conservative*" **no longer describes the canonical run** — social is now a GO. That does **not**
  invalidate the frame-gating conclusion, because the current GO is **independently shown jitter-floor-safe**:
  dropping the sub-floor `nn_dist_in` and keeping only `n_within_1m` (≥1 m) + mean-distance gives the **same Δbits
  with a HIGHER z**. The measurement safeguard is intact, but via a *different argument* than the audit gave. **A
  future re-audit of the canonical GO run should re-point §4 accordingly.**
- Net effect on the parent's stated ground truth: **CONFIRMED.** Individual = detectable but NEGLIGIBLE (~0.001
  bits, lower bound on power, not exact zero); group-social leaving = ROBUST GO (~0.012 bits at 8 nights,
  jitter-floor-safe, survives day-shuffle), **group-level and identity-agnostic (herd, not dyads).**

### 3b. Flicker/jitter correction (hysteretic ROI-state unit) — VERIFIED SOUND.

The raw point-in-ROI decision unit was **flicker-contaminated at the jitter floor**: 88% self-return departures,
45% of visits <5 s, 50% one-epoch visits, house_1 alone 5,267 "visits"/16.6 h, only 10% of the night attributed to
any shelter — i.e. "departures" manufactured by a rat wobbling across a house edge at the ~7 in floor (this is
exactly the sensor-path/animal-path confusion the skill warns against, and it correctly **invalidated** M4/M5, not
merely weakened them). The hysteretic unit (`hyst buf14 exit30`, buffer = 2× jitter) removes it: shelter dwell 5.8 s
→ 55 s, self-return 0.88 → 0.33, **frac <5 s → 0.00** (even at the finest 5 s epoch, so the hazard bin stays fine),
occupancy 10% → 56%; food folded into its house (food_i ⊂ house_i jitter flips suppressed); flicker self-returns
merged only when short AND near-boundary AND no other ROI established, genuine loops preserved; selftest **13/13
PASS** including planted flicker→one-visit and genuine-loop→preserved. **This is a correct, principled measurement
fix, not a tuning knob** — and it is the reason every downstream module (3, 6, 7, 9, 10) is built on a behavioral,
not a jitter-flicker, state.

### 3c. Pseudoreplication correction (approach/avoid → night-block) — VERIFIED SOUND.

The first approach/avoid gate used a **per-pair z** over 3,936 (bout, partner) pairs. Those pairs are heavily
pseudoreplicated (each bout emits ~4 partner rows sharing ONE displacement; bouts within a night share layout;
consecutive bouts serially correlated), so z ≈ 27 scaled with √n_pairs, **not effect size**. The gate was rebuilt at
the **night-block level** (per-night geometry-adjusted effect + real-time social increment, then a two-sided
binomial **sign test over the ~8/11 nights** = the true replicate N). The finding **survived** (a
pseudoreplication artifact would have collapsed; instead night-level sign-test p = 0.008). Two further adversarial
fixes (day-shuffle subpopulation mask; `net_sign` vs geometry-null) were applied. **The night-block gate is now the
correct significance unit across all the social modules** (approach/avoid, rest-vs-social, departure-contagion,
search, social-habituation) — and it is the reason the outer-N (~8–11) is the binding power limiter (§4).

---

## 4. Cross-cutting measurement limiters

| Limiter | Where it bites | Measurement status |
|---|---|---|
| **Pseudoreplication / low outer-N** | every social + trend claim | Corrected to night-block sign tests, but the real replicate count is only **~8–11 nights**. This chronically **under-powers small effects and trends** (front-loading ~0.27 power; spacing-dissociation CI includes 0; 2-night fragility of the crowding-on-leaving 0.0027). NO-GO/NULL verdicts are **upper bounds on effect size**, not proofs of zero. |
| **Jitter floor ~4–7 in** (p50 ~7 in, p95 ~15 in) | onsets, leaves, proximity, distances | Enforced: proximity ≥1 m (39.37 in), `min_disp` 14 in, coarse distances ≥14 in, search radius ≥3× floor. **Onset = speed-onset above the floor = a LOWER bound** (in-nest sub-jitter stirring / ~18:00 arousal invisible → NOT "wake"). Same for "leave." The one sub-floor feature (`nn_dist_in`, 52% <14 in) appears only in the identifiability social set and the GO is shown robust to dropping it (§3a). |
| **⛔ Inch frame UNVERIFIED** | every spatial claim | `wiser_to_field_transform.json` absent → `load/apply_field_transform` are no-ops. **Topology + coarse distance ONLY.** No route/path/direction/heading/navigation/compass/physical placement. Module 11 ⛔ blocked. Gates ALL geometry claims until a pole survey passes QC. |
| **Weaker provenance** | traceability | No run_manifest/QC CSVs for this run; no `measurement_context` sidecar; no per-row `mc_run_id`; `--fast` permutations (20/15/25–30) → **z-scores are smoke-level (direction safe, magnitudes not publication-grade)**; reports are code-verified (selftests PASS) but **code verification ≠ biological validation.** |
| **Proxy outcomes** | rest, sleep, onset | "rest"/"nap" = low-speed proxy (NOT sleep/ephys/CV-validated); "settled" ≠ "decided to rest"; onset = lower bound. Every quantity is a coarse proxy stated as association, not cause. |
| **refuge_4 burrow dropout** (weather-INDEPENDENT hole/burrow, 07-03→07-07, removed 07-07 13:00) | 11-night modules | Handled by excluding below-plane dropout ROIs from settlements and refuge_4 burrow-night leave-rows (= 0). But the 11-night social modules span the burrow window + removal; the **search-excursions spacing-dissociation late-night rise is explicitly confounded with burrow onset 07-03 / refuge_4 removal 07-07** (correctly flagged). refuge_4 occupancy is a lower bound (dropout ≠ "left"). *(Note: the SKILL.md supersedes the reference-file "wet-hay-wall" story — the dropout is a HOLE/burrow, weather-INDEPENDENT.)* |
| **Weather double-path** | wet nights 06-30, 07-01, 07-04 | Rain/wet attenuates UWB (dropout ↑) AND changes behavior; wet nights sit late in the sequence → confounded with habituation. Not to be regressed out as nuisance. |
| **Tag ≠ animal cutoffs** | cohort size | Sova (12409) cut 06-29 (6→5 rats); Hypnos (12380) removed 07-09 03:35 — all windows end ≤07-08, unaffected. `shortid` resolved via `rat_identities.csv`. |

---

## 5. Per-module classification (newly-audited modules)

Classification vocabulary: **behavioral signal · measurement artifact · mixed/ambiguous · lower-bound only**.
"Measurement-supported" = the state/statistical result; "candidate reading" = the biological/causal gloss, kept
separate. All statuses are ⚠️ **candidate** in ANALYSIS_STATUS terms; none is confirmed.

| Module | Measurement-supported result | Classification | Candidate reading (quarantined) | Key limiter |
|---|---|---|---|---|
| **3 Locomotor initiation** | Initiation hazard predictable from residence state (M1 held-out 0.0462→0.0434, skill 6.2%); D1 initiation≠departure 26×; hazard 3.3× higher from open low-speed than settled shelter. Social increment Δbits **0.0002** (NO-GO), individual 7.5e-5 (NO-GO). | **Behavioral signal (state-predictability) + LOWER-BOUND (onset ≥ floor)**; social/individual = true-negative on magnitude (lower-bound power). | "the entry decision" — NOT "wake", NOT "decided to forage". Group-social does **not** drive initiation (asymmetry vs leaving). | Onset lower bound (sub-jitter stirring invisible); ~8-block power; frame topology-only. |
| **6 Destination validation** | Transition-type mix from sustained settlements: **open_field_termination 0.61**, relocation 0.18, same-site return 0.12 — grid-stable (0.61–0.63); gate PASS (relocation-fraction range 0.057 over duration threshold; the 0.150 range is a conf_frac=0.8 definition change, flagged). Below-plane dropout ROIs excluded. | **Behavioral signal — measurement-supported, frame-safe topology.** This is the real headline of Module 6. | "~60% of departures end in the OPEN" — endpoints only, NOT navigation. | Frame unverified (endpoints only); settlement measurable only at sustained residence. |
| **6 Destination choice** | Origin conditions destination: held-out **Δbits 0.56 / skill 15%** over global hub (baseline-independent); uniform comparison baseline-SENSITIVE at n=55 (reported, not headline); house↔house switching dominant (30/75); 0/3 individual house preference. | **Mixed / candidate — EXPLORATORY, lower-bound power (n=55–75 relocations).** | "origin predicts where it settles" — NOT route choice, NOT goal-directed navigation. | Thin per-origin support; endpoints only; frame unverified. |
| **7 Approach/avoid** | Distance-dependent **social spacing**: e_dir positive at all bins (above geometry); e_day **approach far** (>3.8 m +0.12, 8/8 & 11/11 nights, p 0.001–0.008), **avoid near** (1–3.8 m, 0/N nights, p 0.008–0.016). Night-block sign test (pseudoreplication-corrected). Distances ≥1 m, min_disp 14 in — jitter-floor-safe. | **Behavioral signal — social SPACING / ASSOCIATION (strongest social result; measurement-sound).** | "maintains a preferred inter-individual distance" — **NOT** attraction/motivation, NOT "chooses to approach", NOT fine steering (heading-free/DBV), NOT dyadic (group-level). Approach is to the partner's **START**. | Active-steering vs passive-co-location **UNRESOLVED** (needs CV orientation/contact); 1–2 m "avoid" small-N/threshold-fragile in phase-splits; frame unverified. |
| **7 Approach circadian (Part 2)** | Spacing holds in **both active and nap** population-rest phases → not a circadian-nap artifact. | **Behavioral signal (corroborating); phase-splits under-powered.** | property of active movement whenever it occurs. | Rest phase = low-speed population proxy; few informative nights per phase. |
| **Departure contagion** | Group **following** (co-departure) on leaving: held-out Δbits **+0.0010** (NO-GO, p 0.23), pooled coef anti-following; T-REAL z 2.27 (a whisper of real-time coupling). Front-loading FALSE (early −0.0004 < late 0.0015, ρ 0.191 p 0.57). | **Lower-bound / true-negative** — no robust following at this resolution; magnitude negligible. | reviewer's "a neighbour left, so I leave" mechanism **not supported**. | Sub-floor following invisible → under-counted; n=11 low power. |
| **Rest vs social (Part 3)** | Rest predicts leaving (Δbits 0.0048); crowding-suppresses-leaving **survives rest control** 0.0027→0.0018 (67% retained), day-shuffle z 2.3 → NOT a rest/huddle confound. | **Behavioral signal (real, rest-independent) BUT sub-threshold magnitude** (<0.003) → candidate. | "crowding keeps residents home" — group-level, association. | Magnitude below promotion threshold; 2-night fragile; rest = proxy. |
| **9 Return-vs-explore** | 123 named-dest excursions, raw return 0.76 but **NOT above layout base rate** (sign-test p 0.55) and **NOT recency-specific** (history-shuffle p 0.45). | **Behavioral NULL (true-negative) — no return-bias beyond layout.** | NOT curiosity/novelty drive; a few sites are simply popular. | Frame unverified; ROI set in inch frame; n=11. |
| **10 Search geometry** | Coarse only (DBV-capped): in_place radius 100 < relocating 124 < open 142 in; uniformly tortuous (straightness 0.17–0.21); 100% ≥3× floor. | **Behavioral/geometry signal, COARSE only.** | a geometry statistic, **NOT** an ARS-vs-global "search strategy" / optimal foraging. | Fine turn/ARS structure jitter-unresolvable; frame unverified. |
| **Temporal** | Leaving RULE **time-invariant**: hour-varying held-out Δbits −0.0004 (hour-label null z 0.73); night-slope z 0.51; structured context ≈0. Method validated (planted hour-rule detected at Δbits 0.018, z 159). Crowding suppresses leaving, constant across the night (coef −0.56/−1.01/−1.17, no flip). | **Behavioral signal — trustworthy time-invariance null (method-certified) + candidate direction.** | "the leaving rule doesn't change with time; crowding suppresses leaving" — hour/night differences are **state occupancy**, not policy change. | 8 nights, `--fast` perms, movement proxy, 3-block hour resolution. |
| **Social habituation (non-stationarity)** | Is the 8→11-night attenuation a front-loaded effect averaged flat? **UNRESOLVED at n=11**: held-out trend ρ −0.19 (perm-p 0.57), pooled night-permuted social×novelty interaction **null** (perm-p 0.17/0.95), power only ~0.27–0.29. Weak non-significant lean toward front-loaded (early 0.0046 > late 0.0020). | **Mixed / ambiguous — honest UNRESOLVED; underpowered null is not stationarity.** Leads with held-out estimator (in-sample reverses 06-28 = overfitting artifact). | neither refuted nor confirmed; spacing-dissociation candidate confounded with burrow/refuge_4 regime (flagged). | ~0.27 power; 2-night fragile; needs more nights / co-departure feature / CV. |

---

## 6. Frame-gating (every spatial/directional claim)

- **No headline in any of the 14 reports rests on absolute direction, heading, bearing, route, or physical
  placement.** Outcomes are topological (which ROI is left/entered) or coarse metric (proximity ≥1 m, distance
  bins ≥1 m, displacement ≥14 in, radius ≥3× floor). This respects the ⛔ blocker.
- The one sub-floor continuous feature (`nn_dist_in`) is confined to the identifiability social set; the GO is
  shown robust to dropping it. **No `nn_dist_in` coefficient may ever be read as behavioral.**
- **⛔ Blocker unchanged:** every spatial/directional promotion remains gated on a pole-survey georeference
  (`configs/wiser_to_field_transform.json` absent). Do not upgrade any claim to physical placement or absolute
  direction until the survey passes QC. **Module 11 (route/corridor selection) stays ⛔ blocked (georef).**
- **⛔ Module 14 (latent motivation/reward) stays blocked (capstone).** Note the reward-feasibility *gate*
  mechanically passes now (preconditions met: policy-stationary-transfer, state-coverage, observed-state-Markov,
  action-space-adequate) — but **forward predictability ≠ reward identifiability**. In a multi-agent, non-stationary,
  partially-observed, measurement-degraded system, unobserved odor/temperature/food/habituation/social yield
  **observationally-equivalent rewards**; the endpoint is the interpretable semi-Markov choice model. **No IRL,
  no utility, no goal.**

---

## 7. What this direction does NOT license

- **NOT IRL / reward / utility / goal.** Reward is ⛔ blocked; the feasibility gate passing is not identification.
- **NOT an individual/identity policy.** Individual is **detectable but NEGLIGIBLE (~0.001 bits)**; "no LARGE
  transferable individual policy" is a **lower bound on effect size**, not exact zero (power-limited, ~8–11 blocks).
- **NOT dyadic / pairwise social.** All social effects are **GROUP-level, identity-agnostic (herd, not dyads)**.
  Pair-resolved is Module 13 (planned, late challenger, NOT run, NOT the framework).
- **NOT attraction / motivation.** Approach/avoid is social **SPACING / ASSOCIATION**; approach is to the partner's
  START, coarse ≥1 m, heading-free. Never "chooses to approach."
- **NOT route / navigation / direction / path.** Destination = endpoints only; search geometry = coarse only.
- **NOT "wake" / "decided to forage" / "sleep".** Onset = lower bound; rest/nap = low-speed proxy.
- **NOT "the rat policy" / "search strategy".** This is 14 modules (the exit/entry sides of one locomotor loop),
  a hierarchical semi-Markov state machine — not a single global policy, not IRL, not a graph-transformer framework.
- **NOT physical/compass placement.** Inch frame unverified.

---

## 8. Weaker-provenance verdict

**Partially auditable / weaker provenance than CV.**

- **Auditable and robust (report + change-log level):** the flicker→hysteretic decision-unit fix (§3b), the
  pseudoreplication→night-block correction (§3c), the frame-gating of every headline, the refuge_4/Sova/dedup
  handling (inherited from the identifiability audit), and the clean separation of measurement-supported results
  from candidate biological readings in every report.
- **Lower-confidence because of missing/weaker provenance:** (a) **off-repo run dirs absent** → no
  run_manifest/QC CSVs/row-level artifacts for THIS audit; row/CSV cross-checks are inherited, not re-run; (b)
  **no `measurement_context` sidecar / `mc_run_id`** → decision rows cannot be joined to a config-hash manifest,
  and the divergent leave/settlement counts across reports cannot be mechanically reconciled; (c) **`--fast`
  permutations** → z-scores are smoke-level (direction safe, magnitudes not publication-grade); (d) the
  identifiability audit is **stale on the M5 arm** (audited a NO-GO run; canonical is now GO — §3a); (e) 11-night
  modules have **no QC table at all**. Do not force this to CV-level confidence.

---

## 9. Smallest next action (do NOT re-fit/re-tune)

Keep all rows ⚠️ **candidate**. In order:

1. **Design/build a WISER `measurement_context` sidecar + per-row `mc_run_id` stamp mirroring the CV pattern**
   (follow-up PR, not part of this audit). This is the standing provenance limiter — it would let leave/departure/
   bout/approach rows be joined to a config-hash manifest and reconcile the divergent counts across reports.
2. **Restore/regenerate the off-repo run dirs** (or point this audit at them) so the row/CSV cross-checks
   (edge-strata, refuge_4 leave-rows = 0, dedup, flag_summary fractions) can be **independently re-verified** for
   the newly-audited 11-night modules — currently inherited from the 8-night identifiability audit only.
3. **Re-run the modeling stages WITHOUT `--fast`** (default perm budget) before quoting any z toward confirmed.
4. **Re-audit the canonical (GO) identifiability run** and re-point the frame-gating argument (§3a): the social GO,
   not the old NO-GO, is now the object; confirm the jitter-floor-safe robustness at full perm budget.
5. **Dispatch the sibling `cv-measurement-auditor`** (§10) for the questions UWB cannot answer.

⛔ Blockers unchanged: georeference survey gates all spatial promotion (Module 11); reward capstone (Module 14)
stays blocked.

## 10. Sibling handoff — `cv-measurement-auditor`

Dispatch `cv-measurement-auditor` (shelter cameras; sees inside the shelter when the glass is clear) for the
findings UWB cannot resolve — never assume the two agree:

1. **Approach/avoid spacing: active steering vs passive co-location** — WISER is heading-free (DBV); CV
   orientation/contact can separate them.
2. **Huddle vs solo occupancy** and the **Nox (12386) house_1-vs-house_2 preference** (from the identifiability
   run) — WISER sees ROI membership, not inside-shelter huddles.
3. **Destination-side social pull** — whether relocation/settlement is drawn to conspecifics already present (the
   untested arm of Finding 3), and **true-sleep validation** of the rest/nap low-speed proxy.

WISER is the fog-immune reference for near-shelter occupancy; CV resolves inside/huddle. Bridge:
`wiser/scripts/analyze_sleep_site_cv_crossval.py` (asymmetric reconciliation).

---

## 11. Machine-readable verdict (embedded; per parent instruction only this single `.md` file was written)

```json
{
  "schema_version": "wiser_measurement_audit/1.0",
  "auditor": "wiser-measurement-auditor",
  "targets": [
    "results/2026a/wiser_policy/reports/wiser_policy_identifiability_audit_2026a.md",
    "results/2026a/wiser_policy/reports/wiser_policy_identifiability_report_2026a.md",
    "results/2026a/wiser_policy/reports/wiser_policy_locomotor_initiation_2026a.md",
    "results/2026a/wiser_policy/reports/wiser_policy_destination_choice_2026a.md",
    "results/2026a/wiser_policy/reports/wiser_policy_destination_validation_2026a.md",
    "results/2026a/wiser_policy/reports/wiser_policy_approach_avoid_2026a.md",
    "results/2026a/wiser_policy/reports/wiser_policy_approach_circadian_2026a.md",
    "results/2026a/wiser_policy/reports/wiser_policy_departure_contagion_2026a.md",
    "results/2026a/wiser_policy/reports/wiser_policy_rest_vs_social_2026a.md",
    "results/2026a/wiser_policy/reports/wiser_policy_search_excursions_2026a.md",
    "results/2026a/wiser_policy/reports/wiser_policy_social_habituation_2026a.md",
    "results/2026a/wiser_policy/reports/wiser_policy_temporal_SUMMARY_2026a.md",
    "results/2026a/wiser_policy/reports/wiser_policy_social_extension_SCIENTIFIC_SUMMARY_2026a.md"
  ],
  "generated_utc": "2026-07-13T03:00Z (approx; derived from git HEAD commit 2026-07-12T22:50:40-04:00; date/python sandbox-blocked)",
  "repo_git_commit": "084d4c2e83fc2e27b1fcba4f05f75ffd1e1142e1",
  "verdict": "partially auditable / weaker provenance than CV",
  "identifiability_audit_reconfirmed": "measurement verdict HOLDS (run-agnostic); STALE on the M5 arm (audited a NO-GO run; canonical is now a jitter-floor-safe GO)",
  "corrections_verified": {
    "hysteretic_flicker_fix": "sound (raw point-in-ROI flicker-contaminated; hysteretic buf14/exit30 removes it; selftest 13/13)",
    "pseudoreplication_to_night_block": "sound (per-pair z was sqrt(n_pairs) inflation; night-block sign test survived at p=0.008)"
  },
  "strata": [
    {"name": "module3_locomotor_initiation", "n": "1016 onsets / 198735 at-risk epochs", "metrics": {"state_skill": 0.062, "social_dbits": 0.0002, "individual_dbits": 7.5e-5}, "classification": "behavioral signal (state-predictability) + lower-bound (onset >= jitter floor); social/individual true-negative on magnitude"},
    {"name": "module6_destination_validation", "n": "410-452 departures", "metrics": {"open_field_termination_frac": 0.61, "relocation_frac": 0.18, "same_site_return_frac": 0.12, "gate": "PASS"}, "classification": "behavioral signal (measurement-supported, frame-safe topology)"},
    {"name": "module6_destination_choice", "n": "55-75 relocations", "metrics": {"origin_over_global_dbits": 0.56, "skill": 0.15, "individual_house_pref": "0/3"}, "classification": "mixed/candidate - exploratory, lower-bound power"},
    {"name": "module7_approach_avoid", "n": "3936-5717 bout-partner pairs, 8-11 nights", "metrics": {"e_day_far_gt3p8m": 0.12, "e_day_near_1to3p8m": -0.11, "night_sign_p": 0.008}, "classification": "behavioral signal - social spacing/association (jitter-floor-safe, pseudoreplication-corrected)"},
    {"name": "module7_approach_circadian", "n": "active 3605 / nap 2112 pairs", "metrics": {"spacing_present_active": true, "spacing_present_nap": true}, "classification": "behavioral signal (corroborating); phase-splits under-powered"},
    {"name": "departure_contagion", "n": "11 nights", "metrics": {"following_dbits": 0.0010, "sign_p": 0.23, "t_real_z": 2.27, "front_loaded": false}, "classification": "lower-bound/true-negative - no robust following at this resolution"},
    {"name": "rest_vs_social", "n": "11 nights", "metrics": {"rest_dbits_on_leaving": 0.0048, "social_dbits_uncontrolled": 0.0027, "social_dbits_rest_controlled": 0.0018, "retained": 0.67}, "classification": "behavioral signal (real, rest-independent) but sub-threshold magnitude - candidate"},
    {"name": "module9_return_vs_explore", "n": "123 excursions, 11 nights", "metrics": {"raw_return_rate": 0.76, "vs_layout_sign_p": 0.55, "vs_history_shuffle_p": 0.45}, "classification": "behavioral NULL (true-negative) - no return-bias beyond layout"},
    {"name": "module10_search_geometry", "n": "1541 bouts", "metrics": {"radius_in_place": 100, "radius_relocating": 124, "radius_open": 142, "straightness": 0.19, "frac_ge_3floors": 1.0}, "classification": "behavioral/geometry signal, coarse only (DBV-capped)"},
    {"name": "temporal_leaving_rule", "n": "43273 leave epochs, 8 nights", "metrics": {"hour_varying_dbits": -0.0004, "hour_label_null_z": 0.73, "night_slope_z": 0.51}, "classification": "behavioral signal - trustworthy time-invariance null (method-certified) + candidate direction"},
    {"name": "social_habituation_nonstationarity", "n": "11 nights", "metrics": {"held_out_trend_rho": -0.19, "trend_perm_p": 0.57, "interaction_perm_p": 0.17, "power": 0.28}, "classification": "mixed/ambiguous - UNRESOLVED (underpowered null is not stationarity)"}
  ],
  "failure_modes": [
    "jitter-floor lower bounds (onset/leave = speed-onset above ~7 in; in-nest sub-jitter stirring invisible -> NOT wake)",
    "pseudoreplication (corrected to night-block sign tests; true outer-N only ~8-11 nights -> chronic low power)",
    "unverified inch frame (topology + coarse >=1m distance only; no route/direction/navigation/physical placement)",
    "refuge_4 burrow dropout (weather-INDEPENDENT hole/burrow 07-03->07-07; occupancy lower bound; spacing-dissociation confounded with burrow onset/removal)",
    "weather double-path (dropout AND behavior; wet nights late-sequence, confounded with habituation)",
    "movement-proxy outcomes (rest/nap/sleep not ephys/CV-validated)",
    "identifiability audit stale on M5 (audited NO-GO run; canonical now jitter-floor-safe GO)"
  ],
  "provenance_gaps": [
    "off-repo run dirs ABSENT (D:/Field2026_analysis_out/2026a has only cv_field_harvest) -> no run_manifest.json, no filtering_log.txt, no per-driver QC CSVs for this audit",
    "no WISER measurement_context sidecar and no per-row mc_run_id -> decision rows cannot be joined to a config-hash manifest",
    "divergent leave/settlement counts across reports cannot be mechanically reconciled (no join key)",
    "--fast permutations (20/15/25-30) -> smoke-level z (direction safe, magnitudes not publication-grade)",
    "calculation_error and battery_voltage loaded but never gated",
    "11-night modules have no QC table available at all"
  ],
  "does_not_license": [
    "IRL / reward / utility / goal (Module 14 blocked; feasibility gate passing != identification)",
    "individual/identity policy (detectable but negligible ~0.001 bits; lower bound, not exact zero)",
    "dyadic/pairwise social (all effects group-level, identity-agnostic herd; Module 13 not run)",
    "attraction/motivation (approach/avoid is social spacing/association; approach to partner START, heading-free)",
    "route/navigation/direction/path (endpoints + coarse geometry only)",
    "wake/decided-to-forage/sleep (onset lower bound; rest low-speed proxy)",
    "'the rat policy'/search strategy (14 modules, exit/entry of one locomotor loop)"
  ],
  "smallest_next_action": "Design/build a WISER measurement_context sidecar + per-row mc_run_id stamp mirroring the CV pattern (follow-up PR); restore off-repo run dirs so row/CSV cross-checks can be re-verified for the 11-night modules; re-run modeling without --fast before quoting z; re-audit the canonical GO identifiability run. Do NOT re-fit/re-tune.",
  "sibling_handoff": "cv-measurement-auditor: (1) approach/avoid active-steering vs passive-co-location (orientation/contact); (2) huddle-vs-solo + Nox house preference inside shelter; (3) destination-side social pull + true-sleep validation. Bridge: wiser/scripts/analyze_sleep_site_cv_crossval.py."
}
```
