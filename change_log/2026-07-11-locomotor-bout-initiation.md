# 2026-07-11 — Phase 1 / Module 3: unified locomotor state machine + bout-initiation hazard

**Status:** ⚠️ candidate. First module of the [behavioral-policy roadmap](../implementation_plan/behavioral_policy_roadmap.md)
Phase 1 — the **entry-side twin** of the built site-residence-termination (leaving) hazard (module 5).
Plan: [`implementation_plan/2026-07-11-locomotor-bout-initiation.md`](../implementation_plan/2026-07-11-locomotor-bout-initiation.md).
Registry: [`configs/behavioral_policy_modules.yaml`](../wiser/configs/behavioral_policy_modules.yaml) modules 1–4.

## What this adds and why

The built policy model is the **exit side** of one loop: *when does residence in a named ROI end*
(leave) and *where next* (destination). It never modeled **when a settled animal starts moving**, nor
kept **initiation distinct from ROI departure**. Module 3 builds the **unified locomotor state machine**
(the modules-1/2 substrate + a movement hysteresis) and, on it, the **locomotor-bout-initiation
hazard**: given the animal is in a low-speed (stationary) state, the per-epoch hazard of initiating a
locomotor bout, conditional on elapsed rest, settled-vs-open, layout, weather/regime, and strictly
pre-decision group-social state.

Organizing framework stays the hierarchical semi-Markov state machine. No IRL, no reward inference.
Onset is **speed-onset above the ~7 in jitter floor — a LOWER bound** (in-nest sub-jitter stirring and
the ~18:00 arousal are invisible → **never "wake"**).

## Files

- **`src/locomotor_states.py`** (new): `locomotor_state_stream` (per-bin unified state
  rest/local_active/transit/pause/unknown — ROI-state from module-5 `hysteretic_visits`, movement-state
  from a speed hysteresis over `_hysteresis_state`); `stationary_episodes` (+ `_data_segments`);
  `bouts_table` (+ in_place/relocating); `build_initiation_table`; `distinction_diagnostics`;
  `state_occupancy`; `build_locomotor_tables`.
- **`scripts/build_locomotor_states.py`** (new, cv/anaconda3): load→clean→state machine→CSVs+manifest.
- **`scripts/analyze_locomotor_initiation.py`** (new, anaconda3): held-out initiation-hazard ladder +
  nulls + effect curve + support audit + report.
- **`scripts/selftest_locomotor_states.py`** (new): offline PASS/FAIL, 10 planted checks.
- **`scripts/build_decision_tables.py`** (touched): extracted the shared `load_clean_stream()` loader
  (module 3 and module 5 now start from an identical cleaned stream); fixed a pre-existing
  `n_fixes_deduped` mislabel (was the post-night-filter count).
- Outputs → `outputs/locomotor_initiation_2026-06-28_to_2026-07-05/` (git-ignored).

## The four distinctions (measurement gate — operationalized AND selftested)

The state machine keeps four things separate; each is a planted PASS/FAIL check in
`selftest_locomotor_states.py`, and each is quantified on the real data:

| # | Distinction | Real-data evidence |
|---|---|---|
| D1 | **initiation ≠ ROI departure** | 1,051 onsets vs **40** relocating (named-ROI) departures → **ratio 26×**. Initiation is a far more frequent event than departure. |
| D2 | **activity-in-place ≠ leaving** | of bouts with named origin+dest: 144 in-place vs 40 relocating (frac_in_place 0.14) — bouts occur without an ROI transition. |
| D3 | **brief pause ≠ settlement** | a stationary blip < movement-exit debounce holds the bout (selftest F/D3a); only a sustained in-ROI stop creates a rest episode (D3b). |
| D4 | **entry ≠ settled** | 1.1% of named-ROI visits contain no rest bin (moving pass-throughs) — arrival is not settlement. |

## Decision-unit redesign (the module-5 lesson, re-learned)

The **first** implementation segmented the at-risk unit on the per-bin `rest` label. Diagnostics
exposed the same jitter/dropout contamination that had corrupted module 5's raw point-in-ROI unit: rest
was shattered into **10,825 episodes (median 30 s)**, of which **8,182 were spurious `censored_nightend`**
(really `rest → short-gap → rest`) and 2,323 `to_pause` (ROI-edge jitter while stationary); only 319
ended by a real onset and **D1 was VIOLATED (onsets 319 < departures 502, ratio 0.64)**.

Root cause: forcing empty/gap bins to `unknown` in the unified state and segmenting on that label, so
every brief signal dropout and ROI-edge flicker split a continuous stationary period. The movement
`active` flag already **holds** through gaps (hysteresis), so the fix is to define the decision unit as
**stationary episodes = contiguous `active==False`, held through short gaps, split only by a long
(≥120 s) internal dropout** (`_data_segments`), with `in_named_roi` a **covariate** (most low-speed time
is in the open — discarding it both thins and biases). After the fix: **1,110 stationary episodes
(median 6.6 min), 94.7% ending by a real onset**, 40 `censored_nightend` (≈ one per animal-night), 19
`censored_gap`; **D1 ratio 26×**. The fragmented per-bin-rest unit is **superseded**.

## Adversarial measurement-bug review

A 6-dimension × 3-verifier workflow (15 agents) hunted the bug classes that bit module 5. Outcome:
- **CONFIRMED (3/3), fixed:** `bouts_table` run-length-encoded the held `active` flag, which the
  movement hysteresis holds `True` across signal-dropout bins (no long-gap cutoff), so a bout spanning
  a dropout merged across the gap — inflating `dur_s`, under-counting `n_bouts`, carrying `has_gap=False`
  — corrupting `bouts.csv` and the D1/D2/D3 diagnostics (the initiation hazard was unaffected, being
  built from the gap-guarded `stationary_episodes`). Fix: split bouts on long internal dropout like
  `stationary_episodes`; guarded by selftest F1/F2. Post-fix: `spans_dropout=0`, bout `dur_s` max 105 s.
- **Low, pre-existing, fixed:** `n_fixes_deduped` manifest field (module-5 loader) measured after the
  night filter → now the true deduped total.
- **High, stale:** an "event on an unknown bin" concern targeted the first `build_initiation_table`
  (which delegated to `build_leave_table`); resolved by the redesign (the current builder places
  `initiated=1` on the terminal *data* bin and drops unknown epochs).

## Results (8 nights 2026-06-28→07-05, 5 rats; whole nights = outer blocks)

**State occupancy** (230,737 5 s bins): rest 51.4%, pause (open low-speed) 37.3%, transit 1.3%,
local_active 0.5%, unknown 9.6%. The animal is stationary ~89% of the night; most stationary time is
**in the open**, not in a named shelter.

**Bouts** (1,048): median 15 s, p90 35 s. **Initiation table:** 198,735 at-risk epochs, **1,016 onsets
(0.51%/epoch)**. **Hazard by stratum:** open low-speed **0.85%** (730/85,971) vs settled shelter-rest
**0.25%** (286/112,764) — a resting animal initiates a bout ~**3.3×** more often from the open than from
a named shelter (the `in_named_roi` covariate effect).

**Predictive-gate ladder (held-out-night bits/decision, whole-night blocks):**
- **State PASSES the predictive gate:** marginal **0.0462** → M1 state **0.0434** bits, **skill 0.062**
  (6.2%). The initiation hazard is genuinely predictable from residence state — dominated by elapsed
  rest (the f(τ) basis) + `in_named_roi` (the 3.3× settled-vs-open effect) + ROI/layout + clock.
- **Weather adds nothing:** M2 0.0435 (Δbits **−0.0002**, held-out worse).
- **Social — detectable but NEGLIGIBLE → NO-GO:** M3 0.0433; the strictly pre-decision jitter-safe
  group-social increment is **mean Δbits ≈ +0.0002** (positive on 6/8 nights). It *survives* the nulls
  (circular time-shift z ≈ 4.3, day-shuffle z ≈ 4.2 — so it is not random), but the **magnitude is ~0.5%
  of the base hazard entropy, far below the 0.003-bit GO threshold**, so the verdict is **NO-GO on
  magnitude** — statistically detectable, practically negligible (exactly the pattern of module-5's
  individual arm). Nulls were run at a **screening** permutation count (n_perm 6) for provenance; the
  verdict rests on magnitude, so the exact z is not decisive — re-run with a large n_perm for a
  publication z (as the module-5 row notes). **Key asymmetry:** in the *leaving* hazard (module 5)
  group-crowding robustly predicted (suppressed) departure (~0.012 bits, ~4% skill, herd cohesion);
  here crowding does **not** meaningfully predict when a rester starts moving. Crowding governs *when a
  resident leaves*, not *when a low-speed animal initiates a bout*.
- **Individual (secondary):** same-animal cross-night personalization is likewise detectable-but-
  negligible (cond-perm z ≈ 2.3, median Δbits ≈ 7·10⁻⁵ bits) → NO-GO (as in module 5).

**Endpoint:** an interpretable state + dwell(+in_named_roi) semi-Markov initiation hazard. No IRL. Full
metrics + effect curve in `outputs/locomotor_initiation_2026-06-28_to_2026-07-05/locomotor_initiation_report.md`.

## Definitions (formula + plain text)

- **Movement-state hysteresis:** per 5 s bin, $\text{frac\_moving}$ = fraction of the bin's fixes with
  `speed_inps_smooth` > 12 in/s (the jitter ceiling); evidence MOVING ($\ge0.5$) / STATIONARY
  ($\le0.2$) / UNCERTAIN; `active` = `_hysteresis_state` (enter after 10 s MOVING, exit after 10 s
  STATIONARY; UNCERTAIN/empty HOLD). Plain: a debounced moving/stationary flag that ignores jitter
  speckle and brief pauses. Onset = the ACTIVE onset that ends a stationary episode — a **lower bound**.
- **Unified state** ∈ {rest, local_active, transit, pause, unknown} = (in-named-ROI? × active?),
  `unknown` if empty/gap. **Stationary episode** = contiguous `active==False`, held through short gaps,
  split by a ≥120 s dropout; **onset** if followed by an ACTIVE run, else `censored_gap`/`censored_nightend`.
- **Bout-initiation hazard** $h_i(t)=P(\text{initiate a bout in }[t,t{+}\Delta)\mid\text{low-speed at }t,z_t)$,
  $\operatorname{logit}h_i=\beta z_t+f_r(\tau)$; $\tau$ = elapsed low-speed time (mandatory basis),
  $\Delta$ = epoch. **initiated** = 1 on the terminal epoch of an onset-ended episode; epochs spanning a
  gap dropped; below-plane dropout ROIs (refuge_4 burrow nights) excluded.
- **Held-out bits** $H=-\frac1N\sum\log_2 p(\text{initiated}\mid z)$; **skill** $=1-H/H_{\text{marginal}}$;
  **Δbits** $=H_{\text{base}}-H_{\text{model}}$. **in_named_roi** = 1 iff the epoch's held ROI-state is a
  named ROI (settled residence vs open low-speed).
- **Nulls:** social increment gated by within-night **circular time-shift** and **day-shuffle** (same
  animal×ROI×clock-hour, different night); individual arm by env-matched **conditional identity
  permutation**. Excluded predictors: `moving_frac` (leaks the onset), `nn_dist_in` (sub-jitter).

## Verification

- `selftest_locomotor_states.py` → **PASS** (10/10: D1–D4 distinctions, dropout/gap discipline,
  bout gap-handling F1/F2, well-formed table).
- `selftest_policy_identifiability.py` (module-5 regression, `semimarkov_decisions` reused unchanged) →
  **PASS** (no regression).
- Module-5 1-night build smoke after the `load_clean_stream` extraction → identical counts
  (leave 2,995, dest 1,067, visits 1,913 for 06-28).

## Scope guard

This is the **locomotor-bout-initiation** module (module 3) — one of 14. Onset is a lower bound; rest is
a low-speed proxy (not sleep); the frame is UNVERIFIED (topology + coarse distances only); the pilot is a
single 8-night window. **Not** "the rat's policy", **not** "search strategy", **not** "wake", **not**
"decided to forage". Downstream modules (approach/avoid, search, social memory) stay BLOCKED until this
layer's four gates pass.

**Resolution limit (cross-checked 2026-07-11 vs `decision_boundary_validation`).** This module lives at
the **coarse** scale — bout existence, onset timing, and endpoint ROI — which WISER (~7 in jitter,
~4.4 Hz) can resolve. It makes **no claim about within-bout kinematics** (turns, sub-second pauses, path
shape, "decision legs"): the DBV suite independently falsified any fine kinematic-boundary interpretation
at this resolution (pause reorientation not separable from a straight-path jitter null; heading-changepoint
detector 30–77 % false-positive). A "trip" is a **merged locomotor episode**, not a destination-coherent
trip. See [`change_log/2026-07-11-dbv-crosscheck-locomotor.md`](2026-07-11-dbv-crosscheck-locomotor.md).
