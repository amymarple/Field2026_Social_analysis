# Fog-Risk Measurement-Context Audit — Shelter CV (CH05 / CH06)

**Audit date:** 2026-07-06 · **New covariate:** `fog_risk.py` (weather-lite condensation risk) · **Detector:** `rat_feasibility-6`

> **Measurement audit only.** Weather is used solely to estimate **camera fog-RISK**; it is **not** a behavioral
> feature and makes **no** claim about rat behavior. The **direct** measure of view degradation stays the
> video-derived `view_quality_inside`. Fog-risk **explains / stratifies** view degradation and detector misses —
> it never changes thresholds, view-quality/safety logic, or excludes bins. All annotation is **additive-only**.
> Note: `fog_risk` and `view_quality` are **correlated by construction** (both track condensation) — this asks
> whether errors *track the covariate*, not that weather *caused* anything.

## Fog-risk covariate (`fog_risk.py`)
From AWN weather: `dewpoint_gap = air_temp − dew_point`, plus RH / rain / pre-dawn → `fog_risk_level`
(low/med/high) + `fog_risk_reason`. Thresholds (gap ≤1.5→high / ≤3→med; RH ≥97/≥92) are **documented
heuristics, not a calibrated fog model**. **Independent validation:** the weather-only risk flags the
*observed* fog windows — 06‑30 & 07‑03 04:00–06:00 both read **high** (gap ~1.2°C, RH ~93%) with no knowledge
of the video.

## What was processed
- **New shelter runs:** 2026-07-01 + 2026-07-02, CH05+CH06 (`--batch 1`, 5-min sampling — audit-grade), so the
  `tape`→`lift_1cm` (07-01) and `lift_1cm`→`antifog_film` (07-02) regimes finally have CV outputs.
- **Data gaps (themselves measurement context):** AWN **down almost all of 07‑01** (4 rows) → fog-risk NaN for
  07‑01; **no 07‑03 footage** on this PC → no CV, weather-only timeline shown.
- All existing outputs (06‑29 legacy/regime-blind, 06‑30) re-annotated. Every file **additive** (row counts
  unchanged, only `fog_*` columns added). Annotated copies in `outputs/audit/`.

## CORE — does degraded view cluster in HIGH fog-risk windows? (sleep outputs, % degraded by fog-risk)
| camera-day | low | medium | high | n | reading |
|---|---|---|---|---|---|
| CH05 2026-06-30 | 1% | **100%** | **100%** | 320 | degraded view tracks fog-risk cleanly |
| CH06 2026-07-02 | 22% | 0% | **78%** | 292 | high-risk pre-dawn ⇒ 73/93 degraded |
| CH05 2026-07-02 | **18%** | 0% | 1% | 294 | degraded in **low**-risk `antifog_film` hours — non-weather regime artifact, see below |
| CH06 2026-07-01 | — | — | 40% | 15* | *weather-gap: only 15 bins matched |
| CH06 2026-06-30 | — | 0% | 0% | 80 | partial output, all clear |

## The payoff — two sensor-path causes, now separable
Carrying **fog-risk (weather) + glass_regime (instrument) + view_quality (video)** together separates *why* the
view degraded:

**(a) Weather-condensation path** — degraded view + detector misses concentrate in **high fog-risk pre-dawn**
windows. On the 06‑30 validation (ground truth, current detector), detector presence-recall **collapses** with
rising fog-risk:
| fog-risk | n | presence-recall | count MAE | misses | view degraded |
|---|---|---|---|---|---|
| low | 29 | **86%** | 0.72 | 3 | 3% |
| medium | 18 | 77% | 0.67 | 3 | 17% |
| high | 10 | **17%** | 0.60 | 5 | **90%** |

**(b) Non-weather optical-regime artifact (`antifog_film` regime)** — on 07‑02, CH05's degraded bins sit in
the **`antifog_film` regime at LOW fog-risk** (afternoon), not in high-risk hours:
| CH05 07-02 glass_regime | clear | degraded |
|---|---|---|
| `lift_1cm` (00:00–13:00) | 158 | 1 |
| `antifog_film` (13:00–24:00) | 101 | **34** |

→ Those 34 degraded bins are afternoon / low-condensation-risk, so the degradation is a **non-weather optical
artifact of the `antifog_film` optical regime**, not weather-condensation. That regime **confounds three
coincident 07‑02 13:00 changes — anti-fog film applied + ~1 cm lift removed + glass reseated** — so the effect
is **regime-attributable, not film-attributable**: the audit cannot isolate which change caused it. It is
**consistent with, but does not prove**, the observer's "film made the view worse" note. (CH06 shows both a
weather path — `lift_1cm` 48% degraded, pre-dawn fog under the lift — and the regime artifact — `antifog_film`
30%.)

## Camera-specific context
CH06 is consistently more degraded than CH05 (06-30…07-02). CH06 uses the **calibration-quad fallback** as its
`inside` zone (no `CH06_zones.json`) and may fog differently — a per-camera measurement-context difference, not
a behavioral one.

## Fog-risk timeline 07-01…07-03 (weather only; context even where video is absent)
15 high-risk hours, concentrated **overnight/pre-dawn**: **07‑02 00:00–07:00 all high** (gap 0.2–0.7°C, RH
96–99%) — and we *do* have 07‑02 footage there; **07‑03 05:00–06:00** high (no footage). This is the window
where any "empty / low-motion" shelter reading is **fog-obscured, not true absence**.

## Interpretation (categories; no behavioral claim)
- High-fog-risk / degraded-view detector misses → **category 2: measurement artifact** (weather-condensation
  sensor path). A visible "empty"/low count there is a **lower bound** (also category 4, wall-edge).
- CH05 07‑02 degradation at low fog-risk *within* the `antifog_film` regime → **category 2: measurement
  artifact** (non-weather **optical-regime** path). The regime confounds film + lift-removal + reseating, so it
  is **regime-attributable, not film-attributable** — separable from weather, but not decomposable into which
  change caused it.
- **No weather→behavior claim** is made. Fog-risk is a weather **estimate**, not proof the view was foggy;
  `view_quality` remains the direct measurement (and the film case shows view can degrade with *low* fog-risk).

## Definition of done — met
Every shelter number now carries camera / shelter / glass-regime / view-quality **and** fog-risk, so we can and
did ask: **do degraded view and detector errors occur in high fog-risk windows?** Yes (06‑30 recall 86%→17%
low→high fog-risk; CH06 07‑02 high-risk 78% degraded) — while keeping weather strictly as measurement context.
And carrying glass-regime alongside fog-risk let us **separate the weather-condensation artifact from a
non-weather optical-regime artifact** (during the confounded `antifog_film` regime — regime-attributable, not
film-attributable). Remaining gaps: no 07‑03 footage (post-film); 07‑01 weather gap; `CH06_zones.json`
missing; fog-risk thresholds are heuristic and uncalibrated.

## Recommended next step
**Transfer + process the 2026-07-03 footage** through `shelter_sleep.py`, then re-run this audit. It is the
highest-value missing measurement because it captures **both**:
- **(a) the `bare_seated_post_film` regime** (07‑03 11:00 onward) — the only way to see whether view quality
  recovers once the `antifog_film` regime ends. Recovery vs. no-recovery is what would let us start attributing
  the 07‑02 regime artifact (film-on vs. lift-off) instead of leaving it regime-level.
- **(b) the 07‑03 04:00–06:00 pre-dawn high-fog-risk window** — the weather-only risk already flags it high
  (gap ~0.8–1.3°C, RH ~93%), and 07‑03 has full AWN coverage, so fog-risk will populate; this tests the
  weather-condensation path on a fresh day.
