# Claim-audit gate — checks, scope rule, stop conditions, output schema

Apply per **atomic claim** (decompose first). Each check sets the claim's `status` and constrains its
`allowed_wording`. The output is the claim-audit table at the bottom — not a workflow report.

## The six checks

### 1 — Measurement validity
- [ ] Stated as **what the sensor/analysis measured**, not an inferred construct.
- [ ] If a biological construct is invoked, the gap to the measured variable is explicit.
  *Fail:* WISER `locomotor_emergence_hour` called "wake" (it is site-departure above the ~7 in jitter
  floor; in-nest arousal is invisible). *Pass:* "locomotor emergence (site departure); true wake needs
  interior CV / ephys."

### 2 — Outcome/state-space validity
- [ ] The outcome can represent **every** biologically relevant state.
- [ ] The claim does **not** lean on rat-centering / normalization / a richer model to cover an
      incomplete state space.
  *Fail:* `house_2_fraction` as "sleep-site choice" when refuges/water-tower/doorway/exposed exist.

### 3 — Design validity
- [ ] **Imposed vs discovered:** a transition/boundary claim comes from an estimator that could have
      located it elsewhere (change-point), not from a fixed analysis window.
- [ ] **Exploratory vs pre-specified:** data-tuned thresholds labeled exploratory.
- [ ] **Repeated vs independent:** same-animal repeats not counted as independent; shared day-level
      covariates (weather) not treated as per-rat-day independent.

### 4 — Internal consistency
- [ ] Exclusive state fractions **sum to ≈1** (state it).
- [ ] Counts reconcile with the transition matrix and denominators.
- [ ] Conditional-on-use mean **not** reported as population composition.
- [ ] Date-gated/invalid states carry explicit denominators + exclusions (e.g. `refuge_4` burrow
      07-03→07-07 excluded from the sleep denominator).

### 5 — Evidence status
- [ ] Exactly one of Established / Candidate / Rejected-Superseded / Unresolved.
- [ ] Synthetic self-tests cited as **code-behavior verification only**, never biological validation.

### 6 — Sensitivity & alternatives
Record dependence on: smoothing/thresholds/ROI buffers · missingness/dropout (missing-not-at-random?
UWB drops under rain) · individual heterogeneity vs shared exposure · time trend/habituation ·
whether video/another sensor is required to validate. Flips under a reasonable alternative → Candidate
at best; disappears → not promotable.

## Scope-limited promotion rule

> A claim may be promoted **only within the validated scope of its measurement and state space, and its
> wording must not imply coverage beyond that scope.**

An incomplete state space blocks claims about the **complete** distribution, but not a narrower claim
fully covered by the measured states. Set `scope` explicitly and make `allowed_wording` honor it.

## Stop conditions (any one blocks THIS claim's promotion — not necessarily its inclusion)

- [ ] measured variable mislabeled as a stronger construct;
- [ ] a key denominator/composition does not reconcile;
- [ ] the result disappears under reasonable alternative classifier/ROI definitions;
- [ ] shared exposures treated as fully independent without qualification;
- [ ] a candidate association described causally;
- [ ] a new result contradicts the current summary but the summary has not been rebuilt;
- [ ] the claim's **wording exceeds its validated scope** (an incomplete state space blocks only the
      whole-distribution wording — rescope rather than reject a within-scope claim).

A blocked claim keeps a status (Candidate / Unresolved / Rejected-Superseded) and stays in the ledger; it
may still appear in the summary if correctly labeled and scoped (status ≠ inclusion).

## Output schema — the atomic claim audit

One row per minimal claim:

| `claim` | `measurement` | `scope` | `status` | `main_evidence` | `main_limitation` | `allowed_wording` | `forbidden_wording` | `required_validation` | `ledger_reference` |
|---|---|---|---|---|---|---|---|---|---|

**Filled example row (measurement interpretation → Established):**

- `claim`: WISER trunk-end marks locomotor site-departure, not true wake.
- `measurement`: first sustained afternoon locomotion above the ~7 in jitter floor (`locomotor_emergence_hour`).
- `scope`: 5 rats, 06-28→07-08, daytime trunk; WISER only.
- `status`: **Established** (measurement interpretation).
- `main_evidence`: emergence clusters ~20.8 h, ρ(emergence, afternoon temp) = −0.02; below-floor stirring is unobservable by construction.
- `main_limitation`: cannot see in-nest arousal, so the ~20:00 departure lags the field ~18:00 wake.
- `allowed_wording`: "WISER locomotor emergence (site departure)".
- `forbidden_wording`: "wake time" / "arousal time".
- `required_validation`: interior CV (CH07/CH08) or ephys to time true wake.
- `ledger_reference`: `change_log/2026-07-10-biological-day-sleep.md`; report §A.

Keep rows terse, but `main_evidence` must carry the **load-bearing statistic** (effect size + n + the
null/threshold it is judged against) — the summary states it inline and its quantitative appendix expands
it into definition (formula + text) → value → decision rule → inference. The
`human-readable-scientific-summary` skill turns this table into prose — do not write the narrative here.
