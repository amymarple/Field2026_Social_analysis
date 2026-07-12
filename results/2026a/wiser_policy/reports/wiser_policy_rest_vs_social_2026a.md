# Rest-need vs social — leaving & entering (Part 3, 11 nights)

**Status:** ⚠️ candidate. Separates a REST-NEED (circadian / nap) driver from a SOCIAL (other-rats) driver in the movement decisions, on the extended 06-28→07-08 window. Generated 2026-07-12T06:54:28.771050. Rest is a low-speed proxy, not sleep; night-block bits.

## Definitions (formula + plain text)

- **rest_propensity(t)** — the POPULATION fraction of informative bins that are stationary (rest∪pause)
  at t's LOCAL clock-hour (the diel rest rhythm). Animal-INDEPENDENT, so it is a pure circadian
  rest-need covariate that cannot leak the focal's own outcome. **focal_in_rest** = the focal's own
  state at the decision is stationary (0/1); **focal_rest_frac_pre** = its stationary fraction in the
  120 s strictly before the decision.
- **Rest-controlled social increment** — the held-out group-social Δbits on the leaving hazard when the
  base ALSO contains the rest covariates. If it ≈ the uncontrolled increment, crowding-suppresses-
  leaving is NOT a rest artifact; if it collapses toward 0, it was rest-confounded.
- All Δbits are leave-one-night-out (whole nights = the outer blocks).

## Result — LEAVING

- **Rest predicts leaving** (a resting/rest-phase animal leaves less): base→+rest held-out Δbits =
  **0.0048**.
- **Crowding-suppresses-leaving SURVIVES rest control:** the group-social increment is
  **0.0027** uncontrolled → **0.0018** after
  adding the rest covariates (**67% retained**), and the
  rest-controlled social still beats the day-shuffle (z = 2.3046157409606614).
  So the social effect is NOT explained by rest/huddle-need — it is a genuine real-time social increment beyond both layout and rest-phase.
- **By the focal's rest-state:** {'resting_focal': {'n': 11302, 'leave_rate': 0.617, 'social_dbits': 0.002033895310456966, 'frac_positive_nights': 0.8181818181818182}, 'active_focal': {'n': 8, 'note': 'too few'}}. The effect concentrates in one rest-state (see values).

## Result — ENTERING / SETTLING

Settling at a named site (vs terminating a bout in the open) has a rest-need (circadian) held-out increment of **-0.0020** bits over the layout+clock base (n=391, settle-rate 0.315). Whether the destination tracks OTHER rats specifically needs the pre-decision group configuration at the destination (follow-up).

## Scope

Circadian rest-need is a population-rhythm proxy (a low-speed state, not sleep); the focal rest-state
is contemporaneous conditioning, not an outcome. Social remains group-level (herd, not dyads),
association not causation. Frame UNVERIFIED. Single 11-night pilot.
