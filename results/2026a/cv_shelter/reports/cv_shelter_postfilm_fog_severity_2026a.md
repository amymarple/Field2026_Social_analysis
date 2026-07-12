# Post-film vs prior-regime pre-dawn fog severity (native view quality)

**Question (task #2):** is `bare_seated_post_film` (07-03 11:00 →) pre-dawn fog *worse* than an
original-`bare` night — i.e. does the observer's "film removal damaged the anti-fog coating" read hold
up in the CV signal?

## Method
The overnight bins in the normal outputs are **weather-forced** to `degraded` (via
`field_conditions.yaml`), which masks native severity (07-04 auditor flagged this). So I recovered the
**native auto-detected** view quality by re-running `shelter_sleep.py --conditions '' --hours 3 4 5 6`
(weather cross-check OFF) over the **pre-dawn 03:00–07:00** window — the common fog window across nights
— for every optical regime. Non-destructive: full-day outputs were backed up and restored; the native
pre-dawn runs were read, not kept. Detector `rat_feasibility-6`, 5-min sampling.

## Native pre-dawn 03:00–07:00 degraded-or-worse fraction (weather-force OFF)
| date | regime | CH05 degraded | CH06 degraded |
|---|---|---|---|
| 2026-06-29 | **bare** | **0.00** (clear) | 0.80 |
| 2026-06-30 | **bare** | **0.83** (foggy) | 0.81 |
| 2026-07-01 | tape | 0.00 (clear) | 0.67 |
| 2026-07-02 | lift_1cm | 0.02 (clear) | 0.76 |
| 2026-07-03 | antifog_film | 0.60 (foggy) | 0.96 |
| 2026-07-04 | **bare_seated_post_film** | **0.73** (foggy) | 0.92 |

(~48–49 native pre-dawn bins/night/camera; `unusable` = 0 everywhere.)

## Finding — the hypothesis is NOT supported (weak, leans against)
Read the **CH05** column (CH06 is unreliable here — see caveats):
- **Fog is night-specific weather, not a function of regime.** The two `bare` nights alone span the
  whole range: 06-29 **0%** degraded vs 06-30 **83%**. Since the regime is identical, that spread is
  purely which night was foggy. Clear pre-dawns (06-29 bare, 07-01 tape, 07-02 lift) vs foggy ones
  (06-30 bare, 07-03 antifog, 07-04 post-film) cut across regimes.
- **Post-film is not the worst — the bare night is.** Among the foggy nights, degraded fraction is
  **bare 06-30 = 0.83 > post-film 07-04 = 0.73 > antifog 07-03 = 0.60.** The original-`bare` night was
  *foggier* than the post-film night — the opposite of what "coating damage worsens fog" predicts.
- → **No CV evidence that `bare_seated_post_film` fogs worse than bare.** The observer's "looks like the
  film destroyed the coating" read is **not confirmed and is mildly contradicted** by this comparison.
  Keep it **tentative / unresolved, leaning against**; do not treat post-film as a proven degraded-coating
  regime.

## Caveats (why this is weak, not a disproof)
- **n = 1 night per regime; weather is fully confounded with regime.** A single foggy post-film night vs
  a single foggy bare night can't isolate the instrument. The definitive test needs several foggy nights
  per regime (the ongoing recording will accumulate them) or a bare-vs-post-film pair on similar-weather
  nights.
- **CH06 is not usable for this comparison** — it has no `CH06_zones.json` (calibration-quad fallback),
  so its `inside` region is degraded across *all* nights (67–96%, even on nights CH05 read 0%). Its high
  post-film number is geometry, not fog. Fix zones (task #4) before trusting CH06 severity.
- `empty_rate` is high pre-dawn everywhere (0.44–1.00) and conflates fog, true absence, and the
  wall-edge blind zone — it is not a clean severity metric; the native `view_quality_inside` degraded
  fraction is the direct measure used here.
- This measures the CV auto-detector's own degraded call, not a calibrated fog quantity.

## Bottom line
Measurement context, **not** a behavior or instrument-damage claim: on the reliable camera (CH05),
post-film pre-dawn fog (0.73) was **less** severe than the original-`bare` foggy night (0.83), and fog
tracks *which night* far more than *which regime*. This **does not support** the coating-damage
hypothesis. Revisit once multiple foggy post-film nights exist.
