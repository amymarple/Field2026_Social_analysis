# Circadian Activity Rhythm and Its Day-to-Day Modulation by Weather

**Direction 3 companion — scientific summary.** Field_2026_Social pilot · outdoor 20 × 40 ft paddock ·
WISER UWB tracking · 5 rats × 11 days/nights (2026-06-28 → 2026-07-08). **Reading time ~5 min.**
Derived from, and never overriding, the technical record (see *Technical references*). "Activity" here is
a **movement proxy** (speed above the tag's jitter floor), **not** measured sleep; no claim is
physiologically validated.

## The picture in one paragraph

These rats keep a **fixed nocturnal clock**: locomotor activity peaks sharply at dusk (~21:00) every
single night, from the first night on, and the five animals are tightly synchronized to it. That *timing*
is remarkably rigid — it does not drift across the 11 days and does not move with temperature or rain.
What **does** change night to night is the **amount** of activity, not its timing: the release night is
the most active (a novelty burst), and thereafter the nightly active portion is **lower on hotter days**.
Rain looks suppressive at first glance but cannot be separated from temperature and day-in-sequence, and
there is **no** steady multi-day "wind-down" in activity level — the animals' *settling* over the first
week shows up as their **space use stabilizing**, not as a declining amount of movement.

## Finding 1 — A fixed, synchronized dusk-onset nocturnal rhythm

Scored as the fraction of time moving above the jitter floor per clock hour, the animals are **nocturnal
with a sharp dusk onset**: mean rest is 0.92 during 05:00–21:00 versus 0.86 overnight — small on the rest
axis, but a **~2.5× swing in *active* fraction**, which peaks at **21:00** and bottoms mid-morning
(~07:00). The dusk peak sits at **21:00 on all 11 biological nights** (peak-hour spread 0 h), and the five
rats share it with a narrow between-animal band — one clock, not an average of five different ones. Hourly
coverage is ≥0.5 everywhere, so this is not a dropout artifact.

The key measurement caveat: the rest threshold is a jitter *ceiling* (~1 ft/s), so anything slower —
sitting, grooming, slow foraging — counts as "rest." This is therefore an **activity-onset rhythm, not
sleep depth**, and it over-counts true sleep. With one cohort and one settling event, a genuine circadian
clock cannot be separated from novelty-driven habituation — but the *observable* rhythm is fixed from
night 1.

## Finding 2 — Night-to-night it is the *amount* of activity that changes, and it falls on hotter days

The nightly active portion (21:00–24:00) is **not** constant and **not** a smooth habituation decline.
The **release night (06-28) is the most active** of all (active fraction 0.150), then activity settles to
a fluctuating baseline of ~0.06–0.10 — a first-night novelty burst, not the start of a downward trend
(active portion vs day-in-sequence ρ = +0.15; move rate ρ = +0.25, i.e. no monotonic decline; the highest
post-release night is 07-07, late in the record).

Instead, the clearest day-to-day structure is **thermal**: the nightly active portion is **negatively
associated with that day's midday temperature — Spearman ρ = −0.53** (active fraction) and **−0.48**
(active distance per valid hour), n = 11. Rats are **less** active at night on the hottest days (the
36 °C days 07-01/02 sit low; the cool 25–28 °C late nights run higher). Note this is the **opposite
direction** to the *daytime* result (where heat nudged animals toward the near-house/water margin) — heat
is associated with **less** nocturnal locomotion but **more** daytime repositioning; different windows,
different behaviors. This temperature association is **candidate**: with n = 11 and the hot days falling
early in the record, temperature is confounded with day-in-sequence, so "less active when hot" and "less
active later" cannot be fully separated (though both point the same way — cooler → more active).

## Finding 3 — Rain and habituation are not separable drivers of the activity level

Wet nights are less active on their face (active fraction 0.069 vs 0.096 dry; 122 vs 164 m per valid hour)
— but this is **not** a clean rain effect. Wet nights are entangled with both temperature and
day-in-sequence, and an acute within-night test (movement before vs after a rain burst on 06-30) gives a
difference-in-differences of **+19.9 with a 95% CI of −8.6 to +43.4 — spanning zero**, i.e. no detectable
suppression beyond time-of-night. So there is **no separable rain effect** on activity in this dataset.

What the first week *does* show is **spatial settling**: night-to-night space-use similarity rises
(edge-cosine 0.50 → 0.81), home/shelter use climbs (0.07 → 0.15), and outside movement falls
(246 → 174 m/valid-hr). The animals converge on a stable set of routes and refuges — the real
"habituation" signal is this **stabilization of *where* they go**, not a decline in *how much* they move.

## What is no longer supported
- **A multi-day habituation decline in activity level** — after the release-night burst, nightly activity
  fluctuates (day-index ρ ≈ +0.15); the "229 → 152" endpoints hide a non-monotonic middle. Settling is
  spatial, not a wind-down in amount.
- **Rain suppresses nocturnal activity** — the wet/dry gap is confounded, and the acute rain DiD CI spans 0.

## What remains unresolved (ranked)
1. **Is "rest" sleep, and is amplitude sleep depth?** The proxy over-counts rest; needs ephys / interior CV.
2. **Is the fixed 21:00 phase an endogenous circadian clock or entrained/novelty-driven?** One cohort, one
   settling event — not separable here.
3. **Does night activity fall because of heat itself, or because hot days were early?** Needs more days that
   break the temperature × sequence confound (or a within-day thermal test).

## Next steps (highest value first)
1. **A within-day / within-night thermal test** (activity vs *instantaneous* temperature, day as its own
   control) to separate heat from day-in-sequence — the same design that would settle the daytime story.
2. **A lower speed threshold or mean-speed/active-distance metric** to sharpen "true sleep" vs slow movement.
3. **Interior shelter video (CH07/CH08)** to validate the rest proxy and the dusk-onset arousal.

## Technical references
- Ledger: `change_log/2026-07-08-circadian-rest-profile.md` (+ 2026-07-09 11-day update);
  `change_log/2026-07-10-d1-d2-eleven-day-consolidation.md`; `change_log/2026-06-30-nightly-progression.md`.
- Reports/CSVs: `outputs/circadian_rest/circadian_rest_report.md`; run CSVs
  `circadian_phase_amplitude_by_date.csv`, `circadian_bio_night_onset_peak.csv`, and D1
  `nightly_rates.csv` / `weather_night_summary.csv` / `rain_did_confidence.csv`.
- Drivers: `analyze_circadian_rest.py`, `analyze_nightly_progression.py` (offline self-tests are **code
  checks, not biological validation**).

---

## Quantitative appendix — how each finding was quantified

Definitions per `/analysis-definitions` (formula + text). Rest per fix: `resting = 1` iff smoothed UWB
speed `< θ_rest`, `θ_rest = 12.46 in/s` (p99 of the stationary tag). Active fraction `= 1 − rest`.
Night window = 21:00–24:00 EDT. Temperature = that day's midday-peak ambient (°C). `wet_ground` = max rain
rate 15:00–24:00 > 0.2 mm/hr.

**F1 · Diel rhythm & phase.**
- *Quantity:* rest fraction per (rat, clock-hour), pooled over days ∈ [0,1]; group mean ± SEM across rats.
- *Value:* rest 0.92 day vs 0.86 night (~2.5× active-fraction swing); **peak hour = 21:00 on 11/11
  biological nights**, spread 0 h; coverage ≥ 0.5 every hour.
- *Rule/inference:* peak-hour invariant across nights and across 25–36 °C ⇒ phase is fixed and
  weather-independent. *Caveat:* θ_rest is a jitter ceiling ⇒ activity-onset rhythm, not sleep depth.

**F2 · Night activity level vs temperature.**
- *Quantity:* nightly active fraction (mean over rats) and active-distance-per-valid-hour; vs midday-peak temp.
- *Formula:* Spearman rank correlation over the 11 nights.
- *Value:* active-frac vs temp **ρ = −0.53**; move-rate vs temp **ρ = −0.48**; vs day-index +0.15 / +0.25
  (no monotonic decline); release-night active-frac 0.150 (max) vs ~0.06–0.10 baseline.
- *Decision rule:* |ρ| > 0.5 with a consistent second metric ⇒ a **candidate** association; day-index
  confound (hot days early) ⇒ not causal. *Inference:* cooler nights → more activity, candidate-thermal.

**F3 · Rain (no separable effect) + spatial settling.**
- *Quantity:* active level on wet vs dry nights; within-night difference-in-differences around a rain burst;
  night-to-night space-use edge-cosine.
- *Value:* wet 0.069 vs dry 0.096 (active-frac), 122 vs 164 (rate), n = 5 wet / 6 dry; acute rain **DiD
  = +19.9, 95% CI [−8.6, +43.4]** (spans 0); edge-cosine **0.50 → 0.81** over 11 nights.
- *Decision rule/inference:* wet/dry gap confounded (temp + sequence) and DiD CI includes 0 ⇒ **no
  separable rain effect**; rising edge-cosine ⇒ settling is spatial stabilization, not an activity decline.
