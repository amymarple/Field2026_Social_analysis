# 2026-07-12 — 11-night extension + rest-need / circadian / social separation

**Status:** ⚠️ candidate. Extends the whole behavioral-policy program from 8 nights (06-28→07-05) to
**11 nights (06-28→07-08)** — every night with WISER tags present, up to the point Hypnos was removed —
and adds a rest-need / circadian layer that separates a REST driver from a SOCIAL driver in the leaving,
entering, and approach/avoid decisions. Frame UNVERIFIED throughout (topology + coarse distance only);
rest is a low-speed proxy, not sleep; significance at the whole-night block level.

## Part 1 — extend all modules to 11 nights

- New versioned environment map `configs/environment_map/2026-06-28_to_2026-07-08.yaml` (adds 07-06 wet+
  burrow, 07-07 dry / refuge_4 removed 13:00, 07-08 dry). All module drivers repointed to the `_07-08`
  env-map + output dirs.
- Rebuilt: module 3 (locomotor states/initiation — 1,546 onsets / 270,552 epochs, 1,653 stationary
  episodes, 1,542 bouts), module 5 (leaving hazard — 11,675 leave epochs at the ep15 headline unit),
  module 6 (destination/settlement — 410 transitions: 61 % open-field terminations, 75 relocations,
  48 same-site returns), module 7 (approach/avoid).
- **Module-5 headline changes on the extended data.** The crowding-SUPPRESSES-leaving effect
  **ATTENUATES**: held-out social increment **Δbits ≈ 0.0030 (jitter-safe 0.0027)** vs the 8-night 0.012.
  It still beats every null (time-shift z 3.4, day-shuffle z 3.0, jitter-safe day-shuffle z 2.5) but is
  now **below the 0.003 GO threshold → magnitude NO-GO**. So the social effect on leaving is real
  (direction-consistent) but **small** on the fuller dataset — the 8-night 0.012 overstated it.

## Part 2 — approach/avoid confined to the active-moving period + nap/circadian cross-check

- `scripts/analyze_approach_circadian.py` (+ `src/rest_circadian.py`). The approach/avoid metric is
  already confined to locomotor bouts (active movement) by construction; this stratifies the night-block
  gate by circadian phase, set from the animal-independent **population rest rhythm**.
- **The night is overwhelmingly a rest state:** population stationary-fraction ρ(h) = **0.95–0.99 at every
  night hour** (deepest 23:00–02:00 local); locomotor bouts are sparse active excursions.
- **The distance-dependent social spacing is circadian-robust:** it holds in BOTH the active and the nap
  phases — **avoid at 2–3.8 m** (e_day −0.10 active / −0.13 nap, ~0–1 of 11 nights positive) and
  **approach beyond 3.8 m** (e_day +0.12, 11/11 nights, both phases). So it is a genuine property of
  active movement whenever it occurs, **not a nap artifact**. (The closest 1–2 m bin loses power when
  split by phase but is strong pooled: e_day −0.26, 0/11.)

## Part 3 — rest-need vs social for leaving and entering

- `scripts/analyze_rest_vs_social.py`. Tests whether the leaving-hazard social effect survives a rest-need
  control, on the ep15 headline unit.
- **Rest predicts leaving** (a resting/rest-phase animal leaves less): base→+rest held-out **Δbits 0.0048**.
- **Crowding-suppresses-leaving SURVIVES rest control:** the group-social increment is 0.0027
  uncontrolled → **0.0018 after adding the rest covariates (67 % retained)**, still beating the
  day-shuffle (z 2.3). So the (small) social effect is **not a rest/huddle artifact** — it is a real-time
  social increment beyond both layout and rest-phase. Leave epochs are ~all settled residents
  (focal_in_rest ≈ 1), so a resting-vs-active split is degenerate; the circadian rest-propensity
  covariate carries the rest-need signal instead.
- **Entering/settling is NOT circadian-rest-driven:** settling at a named site (vs terminating a bout in
  the open) has a rest-need held-out increment of **−0.002 bits** over the layout+clock base (n = 391) —
  i.e. no gain. Whether settling tracks OTHER rats at the destination needs the pre-decision group
  configuration there (follow-up).

## Definitions (formula + plain text)

- **Population rest fraction** $\rho(h)$ — at LOCAL hour $h$, fraction of informative locomotor-state
  bins (over all animals) that are stationary (rest∪pause). Animal-independent circadian rest-need proxy.
- **Circadian phase** — nap if $\rho(h)\ge\operatorname{median}_h\rho(h)$, else active (median split of
  the 8 night-window hours).
- **rest_propensity / focal_in_rest / focal_rest_frac_pre** — the decision's circadian rest-propensity;
  the focal's own state at the decision (0/1); its stationary fraction in the 120 s strictly before it.
- **Rest-controlled social increment** — held-out group-social Δbits on the leaving hazard when the base
  ALSO contains the rest covariates. Retained fraction = rest-controlled / uncontrolled.
- **e_dir / e_day** (module 7) — geometry-adjusted approach and same-partner/same-hour/different-night
  social increment; positive e_day = approach, negative = avoid; night-block sign test.

## Verification

- Module builds rebuilt on 11 nights (manifests in each `_2026-06-28_to_2026-07-08/` dir).
- `analyze_approach_circadian.py`, `analyze_rest_vs_social.py` run; reports + JSON persisted to
  `outputs/approach_avoid_2026-06-28_to_2026-07-08/` and `outputs/policy_identifiability_2026-06-28_to_2026-07-08/`.
- Registry modules 5 & 7 status notes updated. Scientific summary regenerated (see
  `outputs/policy_identifiability_2026-06-28_to_2026-07-08/SCIENTIFIC_SUMMARY.md`).

## Scope / caveats

Group-level (herd, not dyads); association not motivation/causation; circadian phase is a population
low-speed rest proxy (not sleep/ephys); frame UNVERIFIED; single 11-night pilot; whole nights (11) are
the outer inference blocks, fewer within each phase/stratum — an under-powered stratum is not evidence of
absence.
