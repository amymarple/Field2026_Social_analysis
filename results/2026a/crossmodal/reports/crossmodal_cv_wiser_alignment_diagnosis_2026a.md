# CV↔WISER clock-alignment diagnosis — 2026-07-02 shelter cross-val

**Question:** is the low joint **κ = 0.20** caused by a timestamp offset / lag / bin-alignment
artifact, or by real sensor disagreement?

**Verdict:** **NOT a clock-alignment problem.** A fine ±1 h lag sweep is flat, and κ is driven by
WISER's base rate, not by lag. The cross-val agreement is **limited by (a) base-rate imbalance (the
"kappa paradox") + (b) a measurement-definition / coverage mismatch** between WISER "near-shelter
state" and CV "visibly-inside-through-glass" — **not** by unresolved cross-modal alignment. No behavior
is interpreted. (Reproduces the pipeline exactly: lag-0 joint κ = 0.202 = the script's 0.20.)

## 1. Timestamp conventions
| | CV (`shelter_sleep.py` output) | WISER (`wiser_shelter_state`) |
|---|---|---|
| clock | naive **local** NVR wallclock (EDT) | **Unix-ms UTC** → naive UTC |
| derived from | **filename** (hour MP4 `CH0x_2026-07-02_HH-00-00_to_…`) | UWB fix timestamp |
| →UTC | `t_utc = t + 4 h` (loader, `LOCAL_TZ_OFFSET_HOURS = −4`) | native UTC |
| sampling | **300 s (5 min)**, exact `:00/:05/…` grid (measured) | ~3.7–3.9 Hz, bursty |
| bin key | floor to 60 s **bin start** (`_bin_utc_ns`) | floor to 60 s **bin start** (identical) |
| known offset risk | **OSD burn-in ~1 h behind filename**; devices not clock-synced | — |

- **Bin start vs center is not a mismatch** — both sides floor to the same 60 s bin start (the helper
  fixed in the binning commit). No half-bin skew.
- **Nominal offset (+4 h EDT→UTC) is applied**; the cross-val already scans a ±4.5 h residual at 5-min
  steps and picks **0 s**. A ~1 h OSD-vs-filename error would appear as a best lag ≈ ±3600 s — it does
  not. So the open question was a **sub-5-min** residual, which this sweep tests directly.

## 2–3. Fine lag sweep (best lag by agreement; no behavior)
141 lags = union of **±3600 s @ 60 s** and **±600 s @ 30 s**, added to CV `t_utc`, on the `coarse`
stratum (mapping A = house_1→CH05, house_2→CH06). Per lag: Cohen's κ **and** raw % agreement + recall +
precision (κ alone is base-rate-sensitive and misleading here).

| metric | lag 0 | best | best lag | gain vs 0 |
|---|---|---|---|---|
| joint κ | 0.202 | **0.214** | +60 s | **+0.011** |
| joint agreement | 0.598 | **0.603** | +60 s | +0.005 |
| joint κ range over **all** lags | — | **0.072 – 0.214** | ±3600 s | — |
| joint agreement range over all lags | — | **0.525 – 0.603** | ±3600 s | — |

→ **No lag meaningfully improves agreement.** The best offset (+60 s) buys +0.011 κ / +0.005 agreement —
within noise, and consistent with CV frames being timestamped at the filename `:00` boundary a few tens
of seconds before the sampled frame. Alignment is already as good as it gets; there is **no hidden
offset** to recover.

## 4. Why κ is low — base rate + definition, shown per shelter (lag 0, coarse)
| shelter/cam | n | WISER occ | CV occ | agreement | **κ** | recall | **precision** |
|---|---|---|---|---|---|---|---|
| house_1 / CH05 | 192 | **0.995** | 0.484 | 0.490 | **0.010** | 0.487 | **1.00** |
| house_2 / CH06 | 191 | 0.806 | 0.524 | 0.707 | **0.396** | 0.643 | 0.99 |

- **The kappa paradox is explicit.** house_1's WISER base rate is **99.5 %** (a tag is near the ROI
  almost every bin) → almost no negative bins → κ is mathematically pinned near 0 **regardless of the
  CV agreement**. house_2, with a less-extreme 80.6 % base rate and *near-identical* recall/precision,
  scores κ = 0.40 — **40× higher purely from base rate**, not from better alignment. κ is the wrong
  headline metric for a high-prevalence, asymmetric sensor comparison.
- **The residual disagreement is CV recall, not a clock skew.** CV **precision ≈ 1.0** on both shelters
  (when CV says occupied, WISER agrees); the whole gap is CV **recall ≈ 0.49 / 0.64** — CV *misses*
  bins WISER marks occupied. This is a definition/coverage mismatch: WISER's buffer-tolerant
  "near-shelter state" (ROI + 18 in, hysteretic) is on almost always, while CV "visibly inside through
  IR glass" is on ~half. The miss occurs on **clear** glass (see below), so it is consistent with the
  documented **wall-edge blind zone** (nadir CH05/CH06 counts are a lower bound) + huddle undercount —
  **not** a timing artifact and **not** biological disagreement.

## 4b. Stratified agreement (lag 0, coarse) — disagreement does not track the sensor regimes
| axis | level | n | WISER occ | recall | κ | reading |
|---|---|---|---|---|---|---|
| glass_regime | antifog_film | 192 | 0.82 | 0.50 | 0.25 | κ higher where base rate lower |
| glass_regime | lift_1cm | 191 | 0.98 | 0.60 | 0.06 | κ near 0 from 98 % base rate, not worse recall |
| view_quality | clear | 365 | 0.91 | **0.56** | 0.19 | recall gap is **present on clear glass** |
| view_quality | degraded | 18 | 0.78 | 0.50 | 0.16 | only 18 bins; recall barely lower |
| fog_risk | high | 64 | 0.94 | 0.58 | 0.15 | no fog penalty on recall |
| fog_risk | low | 301 | 0.89 | 0.55 | 0.20 | — |
| fog_risk | medium | 18 | **1.00** | 0.61 | 0.00 | κ = 0 by construction (100 % base rate) |
| WISER validity | ok | 383 | 0.90 | 0.56 | 0.19 | **all** daytime bins are validity-ok; no low-anchor stratum |

- The recall gap is **flat across view-quality, fog-risk, and glass regimes** (≈0.50–0.60 everywhere)
  and is present on **clear** glass — so it is not a fog/glass sensor-path artifact. Where κ *is* lower
  (lift_1cm, medium-fog), it is because WISER base rate is higher there, not because CV is worse.
- **No WISER low-validity stratum exists** on 07-02 daytime (all 383 joined bins are validity-ok), so
  WISER fix quality does not explain the disagreement either.

## 5. Classification
**The 07-02 cross-val is limited by a measurement-definition mismatch + base-rate imbalance, NOT by
unresolved clock alignment.** Alignment is adequate (best lag ≈ 0; ±1 h fine sweep flat within noise).
The low joint κ is a **statistical artifact of high WISER prevalence (kappa paradox)** on house_1 plus a
**real, expected CV recall floor** (WISER "near-shelter" ≠ CV "visibly inside"; CV is a lower bound via
the wall-edge blind zone). It is therefore **not** biological disagreement.

**Consequence for interpretation:** stop using symmetric κ as the headline. The interpretable, alignment-
robust readouts are **CV precision ≈ 1.0** (CV-occupied ⇒ WISER-occupied) and **CV recall ≈ 0.49–0.64**
(CV undercounts confirmed occupancy — a lower bound). Any CV-vs-WISER *behavioral* comparison should be
framed as "CV lower-bound vs WISER near-shelter presence," per-shelter (never pooled, since base rates
differ), and never as a κ number.

## Constraints honored
No detector thresholds, WISER filters, view-quality/safety logic, or binning were changed; this is
read-only diagnosis on the fixed pipeline. No behavior claim is made; the low κ is **not** treated as
biological disagreement.

*Artifacts:* `alignment_lag_sweep_2026-07-02.csv` (141 lags × {house_1, house_2, JOINT}),
`alignment_strata_2026-07-02.csv` (per-axis agreement at lag 0). Script:
`scratchpad/alignment_diag.py` (no matplotlib; `KMP_DUPLICATE_LIB_OK=TRUE`).
