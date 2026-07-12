# Daytime Low-Movement and Rest-Site Use in Rats Living in an Outdoor Field Enclosure

> **Note (2026-07-11):** this is the biological-day sub-summary. For the **whole-direction** read (this
> plus the landmark-hierarchy result), see the consolidated
> [`wiser_d3_sleep_SCIENTIFIC_SUMMARY_2026a.md`](wiser_d3_sleep_SCIENTIFIC_SUMMARY_2026a.md).

**Study:** Field_2026_Social pilot · 20 × 40 ft outdoor paddock · WISER UWB position tracking
**Cohort / window:** 5 implanted rats, 11 consecutive days (2026-06-28 → 2026-07-08), 55 rat-days
**Reading time:** ~6 min · **Audience:** behavioral neuroscience · **Status:** candidate / measurement-limited

This summary presents the current picture only. It is **derived from** — and never overrides — the
technical record. The authority order is: **code + generated CSVs → canonical results
(`…_canonical_results.md`/`.json`) → technical report (`…_report.md`) → this summary**; superseded
interpretations live in the change log. No claim here is validated against physiology or video.

---

## The biological picture in one paragraph

These rats are nocturnal. From position data alone we can see that each animal spends the day in a long
**low-movement rest bout** ("the daytime trunk") lasting from roughly 05:00 until it leaves its resting
spot in the evening, bracketing an active night. Where an animal rests during the day is **not a single
fixed burrow**: two large group houses dominate, but every animal also, on some days, rests in secondary
refuges, at house entrances, near the water tower, or in the open, and animals **move between resting
spots within a single day** — about three moves per animal-day. These moves are **spread across the
daytime**, not locked to any one clock hour. Individuals differ in which house they favor and in how
often they move. Whether any of this reflects true sleep, specific physical refuges, or thermoregulation
cannot be settled with position data alone.

## What was measured, and the limits that shape every number

WISER reports each tagged animal's position at ~4 Hz. **Everything below is derived from position and
speed only** — there is no pose, no direct sleep measurement, and no view inside a shelter. "Rest" is a
**low-movement proxy** (a putative sleep period), not an EEG- or video-scored state. The positional
noise floor is ~7 in; every threshold used sits well above it. Critically, **the coordinate frame is
unverified** (unknown origin and orientation, not georeferenced to the paddock), so **no directional or
absolute-location claim is made** and no site is asserted to be physically warmer or cooler than another.
Site names are **ROI memberships**, not identified structures: `house_1`/`house_2` are the two dominant
group houses; others are secondary refuges, a `doorway` band just outside a house, `water`-labelled and
open (`exposed`) ROIs. Two states are **interpretation-limited** and set aside: a **burrow entrance**
(`refuge_4`, dug ~07-03, removed 07-07 — its signal is a UWB drop-out artifact, not rest) and a transient
`tunnel`. The cohort is 5 animals over 11 days — a pilot; ambient (not in-shelter) temperature is a coarse
covariate; repeated days of the same animals are not independent draws.

## Finding 1 — The daytime rest bout ends at an evening boundary, with no detectable temperature link

Scored from ~05:00, the trunk ends when the animal begins sustained locomotion and leaves its resting
spot. This **locomotor-emergence time** is concentrated in the evening: on the **7 of 11 days** where the
detector produced an interior value it fell between **19.7 and 20.9 h** (median across all days 20.8 h;
the detector crossed threshold on 10/11 days). It showed **no detectable monotonic association with that
day's afternoon temperature** (within-day rank correlation ≈ 0, n = 11). Three days sit at the 21:00
detector ceiling (one of them never crossed threshold at all) and one at the 16:00 floor (a fog day) —
these are **censored boundary outputs, not exact event times** (Figure 1).

Two cautions. First, this is **locomotor emergence — the time the animal leaves its resting site — not
true waking.** WISER cannot see an animal stirring inside a shelter, so this ~20:00 value is *later* than
the ~18:00 in-nest arousal noted by observers; the gap is **consistent with** the sensor being blind to
in-nest movement but is not proven to be only that. Second, evening clustering is an **observational
pattern**, not a demonstrated circadian mechanism. What it does establish is that the end of the daytime
rest bout is not set by daily temperature.

## Finding 2 — Within-day relocations occur, but are not locked to a fixed ~10:00 switch

An earlier reading compared each animal's resting site in a fixed 05:00–10:00 window against a fixed
10:00–evening window and, seeing them differ on 15 of 50 animal-days, suggested a mid-morning switch.
Because 10:00 was **imposed** as the boundary, that comparison cannot locate *when* a change happens. An
independent analysis that estimates the single largest within-day position change with **no fixed hour**
finds such a change on **44 of 55 animal-days** — real and large (typically a full house-to-house-scale
step) — but its timing is **spread across the daytime**: median 13.5 h, and **only 11%** of these changes
fall within an hour of 10:00 (Figure 2). The result is robust to smoothing (36 of 44 stable). The full set of
within-day relocations (Finding 3) agrees independently — their times are likewise spread (median 13.4 h;
8% within an hour of 10:00). **Neither analysis supports a stereotyped ~10:00 relocation** — but note this
rejects *time-locking to 10:00*, not the existence of within-day reorganization, which is common.

## Finding 3 — Daytime rest is dominated by two house-labelled ROIs but embedded in a multi-state network

Assigning every 5-minute rest position to the full ROI set (rather than forcing a two-house choice) gives
two distinct measures that should not be conflated:

- **Dwell dominance.** Across all 55 animal-days, the two group houses hold **~85%** of classified
  low-movement dwell (house_1 ≈ 0.51, house_2 ≈ 0.33, unconditional fractions that sum to 1). The
  remaining ~15% is spread over the burrow, doorways, a secondary refuge, open ground, and a near-water
  ROI — small individually, but not captured by a two-house model (Figure 3).
- **Transition participation.** Animals relocate **~3.1 times per animal-day** (median 3, range 0–8; 6 of
  55 days with none) — **170 relocations** in total. These are **not** predominantly house-to-house:
  **116 of 170 (68%)** involve at least one non-house state, and even after removing every move that
  touches the interpretation-limited burrow or tunnel, **56 of 110 (51%)** of the remaining relocations
  still involve a non-house state. House↔refuge, house↔doorway, house↔near-water, and house↔open moves are
  all present.

Dwell time can be dominated by two houses while transitions routinely visit other states; both are true.
Note that the non-house ROIs are **not verified physical refuges** — they are position-defined regions in
an unverified frame.

**Individual differences.** Two animals are strongly anchored to house_1 and move least (12378: house_1
≈ 0.64, 2.0 moves/day; 12380: ≈ 0.66, 2.6/day); two favor house_2 or split between houses and move most
(12407: house_2 ≈ 0.57, 3.7/day; 12395: **no single primary house**, house_2 ≈ 0.42 vs house_1 ≈ 0.40,
3.9/day); 12386 is intermediate. Identity is a real source of variation and is removed before any
temperature test.

> ### Candidate result — a temperature association, not confirmed
> This is exploratory: 11 temperature days, ambient (not in-shelter) temperature, an unverified frame,
> and uncorrected comparisons across states. Using within-animal rank correlations (each animal centered
> on its own mean occupancy), time spent **fully enclosed in any shelter falls on hotter days** (ρ ≈
> −0.44) — but that aggregate **includes** the burrow and tunnel, so read it cautiously. Per state, the
> most consistent descriptive signal is **more doorway-classified dwell on warmer days** (ρ ≈ +0.58),
> with a weaker increase near water (ρ ≈ +0.38). The two houses move in **opposite** directions (house_1
> ρ ≈ +0.17, house_2 ρ ≈ −0.19), so this is **not** a simple "leave the houses" effect. The honest
> reading: **a candidate association, most clearly increased entrance use on warm days, consistent with
> behavioral thermoregulation but not confirmed.** Rat-centering removes each animal's mean occupancy
> only — it does **not** fit animal-specific temperature slopes, model the shared day-level weather, or
> adjust for day-since-release. The earlier binary claim that "temperature does not affect sleep-site
> behavior" is withdrawn; a two-house outcome simply could not represent where the change appears.

## Evidence status

**Supported within the current WISER measurement (descriptive):** rest-site changes are not concentrated
near 10:00; two house-labelled ROIs hold ~85% of low-movement daytime dwell; the state sequence detects
multiple qualifying relocations per animal-day, about half of interpretable ones touching a non-house
state; locomotor emergence is evening-clustered with no detectable temperature association over 11 days;
individual differences in primary house and mobility are stable.

**Candidate biological interpretation (not established):** that low-movement rest is physiological sleep;
that ROIs correspond to specific physical refuges; that warm-day entrance use is thermoregulation; that
evening emergence reflects a circadian mechanism; that the near-water ROI reflects use of the water tower.

## What would move the candidates forward (priority order)

1. **Interior video cross-check** — the in-house cameras installed 2026-07-07 image the house interiors
   directly; use them to test whether the low-movement proxy tracks animals actually at rest, and to
   recover the true in-nest arousal time WISER cannot see.
2. **Georeference the frame** (a pole-dwell survey) — turns ROI labels into verified physical locations
   and lets the multi-site/temperature patterns be interpreted directionally.
3. **In-shelter temperature** (a thermistor) — turns the ambient-air correlate into a test of microclimate
   choice.
4. **A firmer temperature model** — animal-specific slopes, day-clustered uncertainty, leave-one-day-out
   and day-since-release sensitivity, and correction for multiple comparisons — deferred to a later pass.

*A brief mid-night low-activity bout ("nap") is suggested by the activity profiles and field observation
but is **not analyzed here** — nap scoring is deferred.*

---

### Appendix — sources
- **Canonical results (single source of truth):** `direction3_biological_day_sleep_canonical_results.md` / `.json`
- **Technical report (methods, all sections, sensitivity):** `direction3_biological_day_sleep_report.md`
- **Provenance / revision history:** `change_log/2026-07-10-biological-day-sleep.md`; status index `ANALYSIS_STATUS.md`
- **Figures:** `summary_figures/fig1_emergence.png` (Finding 1), `fig2_changepoint_timing.png` (Finding 2), `fig3_dwell_composition.png` (Finding 3)
- Run outputs (CSVs, all figures incl. transition matrix and temperature panels): `D:\Field2026_analysis_out\biological_day_sleep_20260711_1515`
