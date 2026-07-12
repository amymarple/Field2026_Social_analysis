# Phase A — condensation dynamics (C) vs rat detectability (D), weather-controlled

**Scope:** nights 06-29→07-04 (one regime-pure night each: bare · tape · lift · antifog · post-film).
CH05 only for severity/detectability (CH06 has no zones → unusable here). **Native** view quality
(`--conditions ''`, weather-forcing OFF), non-destructive. Detector `rat_feasibility-6`, 5-min bins.
**Measurement context, NOT causal** — n = 1 night/regime, weather confounded with regime.

## Part 1 — fog onset / duration / clearing (variable C, native CH05)
| night | regime | deg frac | deg hours | fog onset | last degraded |
|---|---|---|---|---|---|
| 06-29→30 | **bare** | 0.49 | 8.1 | 21:30 | 06:15 |
| 06-30→01 | tape | 0.02 | 0.2 | — (clear) | — |
| 07-01→02 | lift_1cm | 0.01 | 0.1 | — (clear) | — |
| 07-02→03 | antifog_film | 0.51 | 8.2 | 21:15 | 05:55 |
| 07-03→04 | **bare_seated_post_film** | 0.50 | 8.1 | 21:55 | 05:50 |

- **Three nights foggy (bare, antifog, post-film), two clear (tape, lift).** The foggy nights have
  **nearly identical** dynamics: ~50% of the night degraded, ~8 h, onset ~21:xx, clearing ~06:xx.
- **Post-film ≈ bare** — post-film onset (21:55) is slightly *later* than bare (21:30) and clears
  slightly *earlier* (05:50 vs 06:15). So post-film does **not** fog earlier, longer, or clear later than
  bare — if anything marginally **less**. No support for "coating damage worsens fogging."

## Part 2 — weather-matched condensation (Q2)
| night | regime | min temp °C | min dew-pt depression °C | max RH | rain (Event/Daily, mm) | fog |
|---|---|---|---|---|---|---|
| bare | bare | 16.6 | 1.0 | 94 | **0 (dry)** | **foggy** |
| tape | tape | 23.0 | 0.5 | 97 | ~4 | clear |
| lift | lift_1cm | 19.4 | 0.1 | 99 | **~9.7** | **clear** |
| antifog | antifog_film | 20.7 | 0.6 | 96 | ~9.7 | foggy |
| post-film | bare_seated_post_film | 19.9 | 0.1 | 99 | ~5 | foggy |

- **Fog is not simply weather-driven.** The **bare night was DRY (0 mm) yet foggy**; the **lift night had
  the most rain (~9.7 mm) and lowest dew-point depression (0.1 °C) — most condensation-favorable — yet
  stayed CLEAR.** Dew-point depression does not separate the nights (lift 0.1 clear vs post-film 0.1 foggy).
- **The best-matched pair is lift vs post-film** (both wet, RH 99, dp-dep 0.1, ~20 °C) — **opposite fog
  outcomes.** The difference between them is the **glass state**: a **1 cm airflow lift (clear) vs seated
  glass (foggy)**. This points at the **lift/airflow as the effective fog control**, not the film/coating.
- **Not** weather-matched for the coating question: the bare night (foggy) was **dry**, the post-film
  night (foggy) was **wet (~5 mm)** — post-film was *more* condensation-favorable yet only *equally* foggy,
  which if anything argues post-film is **not worse** than bare.
- **Data caveat:** `fog_risk.py` reads AWN **`Rain Rate (mm/hr)`**, which was **0 at every sample** these
  nights even though **`Event/Daily Rain` accumulated** — so `fog_risk`'s rain signal **understates** rain.
  Use Event/Daily-rain deltas for rain, not the instantaneous rate. (Flagged, not fixed here.)

## Part 3 — WISER-referenced CV detectability under native-degraded bins (Q3a, conservative)
Among native-degraded (foggy) CH05 bins where WISER shows a **stable, high-confidence, ROI-CORE** presence
(a rat definitely in the shelter core), fraction where CV still detects a rat inside:
| night | regime | n degraded | n w/ WISER core-present | **CV det \| WISER-present** | CV det \| no-WISER |
|---|---|---|---|---|---|
| bare | bare | 97 | 57 | **0.51** | 0.15 |
| antifog | antifog_film | 98 | 47 | **0.68** | 0.41 |
| post-film | bare_seated_post_film | 97 | 50 | **0.16** | 0.09 |
| (tape / lift) | — | 3 / 1 | — | n/a (≈no degraded bins) | — |

- **WISER-referenced, NOT ground truth.** A CV miss here is *consistent with* fog but could equally be the
  wall-edge blind zone, doorway occlusion, zone mismatch, rat inside-but-not-visible, or the **unverified
  WISER→camera inch/cm frame** (WISER "core" ≠ guaranteed camera-visible).
- **This does NOT support "rats more visible under fog post-film."** If anything it's the **opposite** —
  post-film detectability under fog (0.16) is **lower** than bare (0.51). But it is **inconclusive**: n=1
  night, and per-night **rat position/behavior** (were they in the visible core or the back/wall-edge that
  night?) is fully confounded with regime, and the WISER→camera frame is unverified. The observer's
  impression is a *human visual* judgment that **only human labeling can test** (→ Part 4).
- Useful sub-result for Q4: on bare, WISER-core-present degraded bins are detected **0.51 vs 0.15**
  otherwise — so **`degraded` view is NOT zero-detectability**; a substantial fraction of degraded bins
  still yield a detected rat. `degraded` **overstates** biological unusability to some degree.

## Part 4 — where human degraded-bin labels are still needed (→ Phase B)
Q3a cannot cleanly separate **D (detectability under fog)** from **geometry/position/frame** confounds, and
the observer's "more visible post-film" is a *visual* claim. The clean test is **human labeling of
DEGRADED clips** in both regimes: for each fogged clip, the observer records *true count* + *could you
count?* This yields (a) gold-standard detectability under fog, post-film vs bare, and (b) the **C≠D
cross-tab**: `P(rat still countable | view = degraded)` per regime — does "degraded" actually mean
biologically unusable? (Phase B command set up separately; target = degraded post-film + degraded bare bins.)

## Synthesis (measurement context, not proof)
- **C (fogging):** post-film ≈ bare (both ~50%, near-identical onset/duration/clearing). **Coating-damage
  hypothesis not supported.** The variable that actually tracked fog was **glass state**: the **1 cm
  airflow lift kept the glass clear even on the wettest, most condensation-favorable night**, while every
  *seated* regime (bare, antifog, post-film) fogged regardless of rain. Removing the lift — not the film —
  is what brought the fog back.
- **D (detectability under fog):** WISER-referenced detectability is **lower** post-film, not higher —
  contradicting the observer's impression — but this is **confounded and inconclusive**; human GT (Phase B)
  is required.
- **C ≠ D confirmed as separate:** `degraded` is an instrument/condensation flag, not a usability verdict
  (degraded bins still detect rats ~half the time on bare). Quantifying `P(countable|degraded)` per regime
  needs Phase B.
- **Confounds:** n=1 night/regime; weather confounded (and not matched for the coating contrast); unverified
  WISER→camera frame; per-night rat position; AWN rain-rate understates rain. **No causal claim.** Accumulate
  more foggy post-film nights (and ideally a lift-on vs lift-off pair at matched weather) before promoting.
