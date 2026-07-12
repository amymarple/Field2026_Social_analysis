# Destination & settlement — representation + validation (Module 6, Phase 2)

**Status:** ⚠️ candidate (validation-first). Rebuilds destination/settlement on the **unified
locomotor-state representation** (module-3 stationary episodes). A **destination is defined only after
SUSTAINED STABLE RESIDENCE**; every departure is typed; **the representation is validated BEFORE any
destination-choice or search model is fit** (per `decision_boundary_validation`). Generated
2026-07-12T06:31:43.570188; settle_min_s=60.0, conf_frac=0.5.

## Definitions (formula + plain text)

- **Settlement (sustained stable residence)** — a stationary episode with `in_named_roi`, duration
  $\ge$ `settle_min_s`, `frac_in_named_roi` $\ge$ `conf_frac`, data coverage
  `n_data_bins/n_bins` $\ge 0.5$, and not a below-plane dropout ROI. Plain: the animal actually
  stopped and stayed at a named site long enough to call it residence — the only anchor at which a
  destination is measurable.
- **Departure** — a settlement that ended by a locomotor-bout **onset** (module-3). Right-censored
  residences (still settled at nightend / lost to a dropout) are NOT departures (42 of them, reported separately).
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

|              |    n |
|:-------------|-----:|
| open_stop    | 1073 |
| settlement   |  452 |
| dropout      |   74 |
| pass_through |   54 |

## Transition-type mix (departures from settlements)

| transition_type        |   n |      frac |
|:-----------------------|----:|----------:|
| open_field_termination | 251 | 0.612195  |
| relocation             |  75 | 0.182927  |
| same_site_return       |  48 | 0.117073  |
| censored               |  19 | 0.0463415 |
| pass_through           |  17 | 0.0414634 |

## Settlement-threshold sensitivity

|   settle_min_s |   conf_frac |   n_settlements |   n_departures |   n_relocation |   frac_relocation |   frac_pass_through |   frac_open_field_termination |   frac_censored |
|---------------:|------------:|----------------:|---------------:|---------------:|------------------:|--------------------:|------------------------------:|----------------:|
|             30 |         0.5 |             473 |            430 |             84 |         0.195349  |           0.0348837 |                      0.609302 |       0.0465116 |
|             30 |         0.8 |             167 |            154 |              9 |         0.0584416 |           0.188312  |                      0.623377 |       0.0649351 |
|             60 |         0.5 |             452 |            410 |             75 |         0.182927  |           0.0414634 |                      0.612195 |       0.0463415 |
|             60 |         0.8 |             156 |            144 |              8 |         0.0555556 |           0.180556  |                      0.625    |       0.0694444 |
|            120 |         0.5 |             419 |            377 |             52 |         0.137931  |           0.0689655 |                      0.62069  |       0.0477454 |
|            120 |         0.8 |             145 |            133 |              6 |         0.0451128 |           0.18797   |                      0.616541 |       0.075188  |

## Validation gate

- all types populated: **True**
- relocation-fraction range across the DURATION threshold (at the operating conf_frac): **0.057** (stable if $\le 0.10$: True)
- (caveat) relocation-fraction range across the FULL grid incl. conf_frac=0.8: **0.150** — a strict confidence threshold reclassifies edge-dwelling settlements as pass-throughs (definition change, not instability); conf_frac=0.5 is the operating point.
- per-origin choice support ($\ge 2$ origins): **True** (6 origins; 75 relocations)
- same-site returns are real loops: **True**

### GATE: PASS — the destination-choice model may be fit (analyze_destination_choice.py)

## Scope guard

Endpoints only (no route/path — frame UNVERIFIED); a destination is measurable only at sustained
residence; same-site return / pass-through / open-field termination / censored are SEPARATE outcomes,
not destination choices. Not "route choice", not "goal-directed navigation".
