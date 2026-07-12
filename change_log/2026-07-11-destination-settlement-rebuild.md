# 2026-07-11 — Phase 2 / Module 6: destination & settlement, rebuilt on the unified locomotor state (validation-first)

**Status:** ⚠️ candidate. Rebuilds the destination/settlement unit (module 6) on the **unified
locomotor-state representation** (module-3 stationary episodes), so a **destination is defined only
after SUSTAINED STABLE RESIDENCE** and every departure is typed. **The representation is VALIDATED
before any destination-choice/search model is fit** — per the `decision_boundary_validation` (DBV)
lesson and the user's directive. Cross-check: [`change_log/2026-07-11-dbv-crosscheck-locomotor.md`](2026-07-11-dbv-crosscheck-locomotor.md).
Registry: [`configs/behavioral_policy_modules.yaml`](../wiser/configs/behavioral_policy_modules.yaml) module 6.

## Why rebuild

The old `build_destination_table` (module 5) recorded a "destination" as the next **named** hysteretic
visit's ROI — so it implicitly assumed every departure goes to another named site, and it never checked
whether the animal actually **settled** there. DBV made the rule explicit: **a destination cannot be
read off where a pause-bridged movement episode ends; it must anchor on observed sustained residence.**
This rebuild does exactly that and separates the departure outcomes the old unit conflated.

## What was built

- **`src/settlement_transitions.py`** (numpy/pandas + em): `type_stationary_episodes` (settlement /
  pass_through / open_stop / dropout), `build_transitions` (5-type departure classifier),
  `representation_sensitivity`, `relocation_support`, `validate_representation` (the measurement gate),
  `build_destination_choice_table` (gated).
- **`scripts/build_settlement_transitions.py`** — types + classifies + VALIDATES on the real module-3
  `stationary_episodes.csv`; writes the destination-choice table ONLY if the gate passes.
- **`scripts/analyze_destination_choice.py`** — the gated choice fit; **refuses to run if the gate did
  not pass**.
- **`scripts/selftest_settlement_transitions.py`** — 8 planted PASS/FAIL checks (one per transition
  type + threshold sensitivity + dropout exclusion).

Works entirely from module-3 outputs — **no new WISER load, no fine kinematics** (DBV-compliant).

## Definitions (formula + plain text)

- **Settlement (sustained stable residence)** — a stationary episode with `in_named_roi`, duration
  $\ge$ `settle_min_s` (default 60 s), `frac_in_named_roi` $\ge$ `conf_frac` (default 0.5), data
  coverage `n_data_bins/n_bins` $\ge 0.5$, and not a below-plane dropout ROI. Plain: the animal
  actually stopped and stayed at a named site long enough to call it residence — the only anchor at
  which a destination is measurable.
- **Departure** — a settlement that ended by a locomotor-bout **onset** (module-3). A settlement still
  occupied at nightend or lost to a dropout is **right-censored residence**, NOT a departure (26 such;
  reported separately, never emitted as a transition).
- **Transition type** (one per departure, from the immediately following stationary episode; episodes
  alternate settle/bout so the next episode is the outcome): **relocation** (settled at a *different*
  named site — the destination-choice event) · **same_site_return** (settled back at the same site;
  requires a real intervening bout, so not a jitter flicker) · **pass_through** (next stop is a named
  ROI entered but not sustained) · **open_field_termination** (next low-speed state is in the open) ·
  **censored** (a gap/dropout/nightend interrupts before an outcome is observed).
- **Validation gate** = PASS iff: (a) $\ge 4$ transition types populated; (b) the relocation fraction
  is stable across the **duration** threshold at the operating `conf_frac` (max$-$min $\le 0.10$);
  (c) $\ge 2$ origins have $\ge 3$ relocations to $\ge 2$ destinations; (d) same-site returns have a
  real intervening bout (median inter-episode gap $\ge 1$ bin).
- **Held-out categorical bits** $H=-\frac1N\sum\log_2 p(\text{chosen dest})$ (leave-one-night-out);
  **origin-conditioned** $P(\text{dest}\mid\text{origin})$ vs **global** $P(\text{dest})$ vs
  **uniform** $1/|C(o)|$; **skill** $=1-H/H_{\text{uniform}}$.

## Results (8 nights 06-28→07-05; 1,110 stationary episodes)

**Stationary-episode types:** open_stop **705 (64 %)**, settlement **321 (29 %)**, dropout 45, pass_through 39.
Most low-speed time is in the **open**, not at a named site.

**Departure outcomes (295 departures from settlements):**

| type | n | frac | meaning |
|---|---|---|---|
| **open_field_termination** | **173** | **0.59** | left a shelter, stopped in the OPEN — no named destination |
| relocation | 55 | 0.19 | settled at a different named site (the choice event) |
| same_site_return | 37 | 0.13 | left and returned to the same site (genuine loop) |
| censored | 17 | 0.06 | interrupted before an outcome was observed |
| pass_through | 13 | 0.04 | next stop was a named ROI, not sustained |

**Headline correction:** **~60 % of departures from a settled shelter end in the open, not at another
named site** — robust across every grid cell (0.59–0.63). The old named→named destination unit was
blind to this (it only saw the 19 % relocations + a biased slice), so it over-represented site-to-site
"navigation." Destinations are the minority outcome of a departure.

**Validation gate: PASS.** All types populated; relocation-fraction range across the duration threshold
= **0.065** ($\le 0.10$); 6 origins with real choice; same-site returns are genuine loops.
**Honesty caveat:** across the *full* grid including a strict `conf_frac=0.8`, the relocation fraction
range is 0.181 — a strict confidence threshold reclassifies edge-dwelling settlements as pass-throughs
(a definition change), so `conf_frac=0.5` (majority-in-ROI) is the operating point and both are reported.

**Gated destination-choice fit (EXPLORATORY, n=55 relocations):** the **origin conditions the
destination** — origin-conditioned held-out bits beat the global (origin-ignoring) hub rate by
**Δbits 0.634 (skill 0.139, ~14 %)**. This is the *baseline-independent* result: M0 and M1 share the
same out-of-support floor, so unpredictable held destinations cancel. A uniform-over-supported-set
"chance" reference is **baseline-SENSITIVE at n=55** (skill flips sign depending on how out-of-support
held destinations are floored: −1.1 generous vs +0.57 harsh), so it is reported but not the headline —
the choice model is thin (more nights are the fix, not a better model). The two **houses are the
count-hubs** (top destinations house_1 21, house_2 12; **19/55 relocations are house↔house switches**).
**No stable individual house preference** (0/2 animals) — consistent with the herd-like house-switching
seen in Direction 3.

**Adversarial review (5-dim × 3-verifier workflow) — fixes applied:** (1) removed a data-coverage gate
that would have wrongly demoted long, gap-held residences to pass-throughs (module 3 already holds
episodes through short gaps; no real settlement was affected, but the gate was unsound); (2) a departure
whose connecting bout spans ≥ `long_gap_s` of continuous held-`active` time (a likely WISER dropout) is
now typed **censored**, not a direct relocation (0 real cases, but DBV-consistent); (3) the
uniform-baseline out-of-support handling was made consistent with the models (this is what exposed the
skill-vs-uniform sensitivity above); (4) the stability gate now treats an empty (zero-departure) grid
cell as instability rather than skipping it; (5) a hardcoded directional "refuges feed into houses"
report string was removed (endpoints only). Re-run: gate still PASS, transition mix unchanged.

## Verification

- `selftest_settlement_transitions.py` → **PASS** (8/8: relocation, same_site_return, pass_through,
  open_field_termination, censored, threshold-sensitivity, dropout exclusion).
- Real-data build → GATE **PASS**; the gated fit **ran only because** the gate passed
  (`analyze_destination_choice.py` refuses otherwise).
- Adversarial measurement-bug review (5-dimension × 3-verifier workflow) → 10 candidate findings; the
  real ones fixed (see the review paragraph above); selftest + build + choice re-run green after fixes.

## Scope guard

Endpoints only — **no route/path/direction** (frame UNVERIFIED); a destination is measurable **only at
sustained residence**; same-site return / pass-through / open-field termination / censored are SEPARATE
outcomes, not destination choices. Onset/bout scale is DBV-resolvable; fine kinematics are not claimed.
**Not** "route choice", **not** "goal-directed navigation", **not** "the search strategy". The
destination-choice fit is a thin gated add-on; the validated **representation** (most departures
terminate in the open) is the headline.
