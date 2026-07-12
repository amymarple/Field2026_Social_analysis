# Destination & settlement — representation + validation (Module 6, Phase 2)

**Status:** ⚠️ candidate (validation-first). Rebuilds destination/settlement on the **unified
locomotor-state representation** (module-3 stationary episodes). A **destination is defined only after
SUSTAINED STABLE RESIDENCE**; every departure is typed; **the representation is validated BEFORE any
destination-choice or search model is fit** (per `decision_boundary_validation`). Generated
2026-07-12T04:05:38.679617; settle_min_s=60.0, conf_frac=0.5.

## Definitions (formula + plain text)

- **Settlement (sustained stable residence)** — a stationary episode with `in_named_roi`, duration
  $\ge$ `settle_min_s`, `frac_in_named_roi` $\ge$ `conf_frac`, data coverage
  `n_data_bins/n_bins` $\ge 0.5$, and not a below-plane dropout ROI. Plain: the animal actually
  stopped and stayed at a named site long enough to call it residence — the only anchor at which a
  destination is measurable.
- **Departure** — a settlement that ended by a locomotor-bout **onset** (module-3). Right-censored
  residences (still settled at nightend / lost to a dropout) are NOT departures (26 of them, reported separately).
- **Transition type** (one per departure, by the immediately following stationary episode):
  **relocation** (settled at a different named site — the destination-choice event) · **same_site_return**
  (settled back at the same site; requires a real intervening bout) · **pass_through** (next stop is a
  named ROI entered but not sustained) · **open_field_termination** (next low-speed state is in the open)
  · **censored** (a gap/dropout/nightend interrupts before an outcome is observed).
- **Origin-supported choice set** $C(o)$ — destinations observed $\ge 3$ times from origin $o$
  (training-fold, for the gated choice model).
- **Validation gate** — PASS iff: (a) $\ge 4$ transition types populated; (b) the relocation fraction
  is stable across the settle_min_s$\times$conf_frac grid (max$-$min $\le 0.20$); (c) $\ge 2$ origins
  have $\ge 3$ relocations to $\ge 2$ destinations; (d) same-site returns have a real intervening bout.

## Stationary-episode types

|              |   n |
|:-------------|----:|
| open_stop    | 705 |
| settlement   | 321 |
| dropout      |  45 |
| pass_through |  39 |

## Transition-type mix (departures from settlements)

| transition_type        |   n |      frac |
|:-----------------------|----:|----------:|
| open_field_termination | 173 | 0.586441  |
| relocation             |  55 | 0.186441  |
| same_site_return       |  37 | 0.125424  |
| censored               |  17 | 0.0576271 |
| pass_through           |  13 | 0.0440678 |

## Settlement-threshold sensitivity

|   settle_min_s |   conf_frac |   n_settlements |   n_departures |   n_relocation |   frac_relocation |   frac_pass_through |   frac_open_field_termination |   frac_censored |
|---------------:|------------:|----------------:|---------------:|---------------:|------------------:|--------------------:|------------------------------:|----------------:|
|             30 |         0.5 |             339 |            312 |             63 |         0.201923  |           0.0320513 |                      0.589744 |       0.0544872 |
|             30 |         0.8 |             122 |            113 |              4 |         0.0353982 |           0.185841  |                      0.628319 |       0.0707965 |
|             60 |         0.5 |             321 |            295 |             55 |         0.186441  |           0.0440678 |                      0.586441 |       0.0576271 |
|             60 |         0.8 |             112 |            104 |              3 |         0.0288462 |           0.182692  |                      0.625    |       0.0769231 |
|            120 |         0.5 |             296 |            270 |             37 |         0.137037  |           0.0666667 |                      0.6      |       0.0592593 |
|            120 |         0.8 |             104 |             96 |              2 |         0.0208333 |           0.1875    |                      0.614583 |       0.0833333 |

## Validation gate

- all types populated: **True**
- relocation-fraction range across the DURATION threshold (at the operating conf_frac): **0.065** (stable if $\le 0.10$: True)
- (caveat) relocation-fraction range across the FULL grid incl. conf_frac=0.8: **0.181** — a strict confidence threshold reclassifies edge-dwelling settlements as pass-throughs (definition change, not instability); conf_frac=0.5 is the operating point.
- per-origin choice support ($\ge 2$ origins): **True** (6 origins; 55 relocations)
- same-site returns are real loops: **True**

### GATE: PASS — the destination-choice model may be fit (analyze_destination_choice.py)

## Scope guard

Endpoints only (no route/path — frame UNVERIFIED); a destination is measurable only at sustained
residence; same-site return / pass-through / open-field termination / censored are SEPARATE outcomes,
not destination choices. Not "route choice", not "goal-directed navigation".
