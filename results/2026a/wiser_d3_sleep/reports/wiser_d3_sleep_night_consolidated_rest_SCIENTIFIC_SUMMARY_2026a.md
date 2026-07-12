# Night-Time Consolidated Rest in Rats in an Outdoor Field Enclosure

**Direction 3 companion — scientific summary.** Field_2026_Social pilot · 20 × 40 ft outdoor paddock ·
WISER UWB tracking · 5 rats × 11 nights (2026-06-28 → 2026-07-08), 55 rat-nights. **Reading ~5 min.**
Derived from, and never overriding, the technical record (see *Technical references*). "Rest" here is a
low-**movement** proxy (staying put) — **rest / grooming / sleep**, not scored sleep.

## The picture in one paragraph

Although these rats are active through the night, each animal interrupts the active night with a **mid-night
period of consolidated rest**: it settles into one small spot — almost always **inside a shelter** — and
stays there, low-movement, for the better part of an hour. This happens on **every** rat-night, roughly two
to three times, around midnight. What sets **how much** of this night rest an animal takes is **not**
temperature and **not** how familiar it is with the enclosure by that point in the study — it is a candidate
association with **humidity**: on damper nights (independent of whether it actually rained), animals spend
more of the night settled in shelter. Whether that low-movement is true sleep, and why humidity would matter,
is beyond what position data can decide.

## Finding 1 — Night rest is consolidated into a few in-shelter bouts

Detecting rest as a **stay-point** — the animal's position clustered within ~24 in while low-movement, held
≥ 30 min with a short exit tolerance — every rat-night contains **~2.5 such bouts** (137 total), and **every
one of the 55 rat-nights has at least one**. The bouts are **median 50 min** (~**145 min of consolidated
rest per animal-night**), sit at a **median cluster radius of 4 in** (the animal is pinned to a spot, tighter
than the ~7 in tracking-noise floor), and **93 % are inside a shelter** — overwhelmingly the two group
houses the animals also use by day. The result is robust to the duration threshold (a 20 / 30 / 40 / 60-min
sweep moves monotonically: looser → more, shorter, less-sheltered bouts; stricter → fewer, longer, ~100 %
sheltered). So night rest is not scattered stillness — it is a small number of genuine, in-shelter settle-ins.

## Finding 2 — What does *not* explain it: temperature, familiarity, or the clock's weather

Two candidate drivers fail, and one prior claim is withdrawn.

- **Temperature does not drive night rest** — within-animal, total consolidated rest vs night temperature is
  **ρ = −0.12** (nil). Importantly, this **retracts an earlier, cruder result.** A first detector that took
  the single lowest-activity window found "hotter nights → more rest" (ρ ≈ +0.44) — but that counted *any*
  low movement, including a heat-lethargic animal sitting still in the open. Once rest is required to be a
  **clustered in-shelter bout**, the temperature signal **vanishes**. The refinement changed the conclusion.
- **Familiarity does not drive it** — total rest vs day-in-sequence is **ρ = −0.20** (if anything, slightly
  *less* consolidated rest later in the study), so "they rest more once they know the place" is not supported.
- **The timing is set by the clock, not the weather** — the longest bout starts around midnight, a median
  **3.9 h from the night's coldest hour** and **2.4 h from its most-humid hour** (both pre-dawn). So whatever
  modulates night rest sets its **amount**, not its ~midnight **timing**.

Individual animals differ only weakly in how much they rest (between-animal variance ≈ 14 %) — this is
mostly a night-level state, not a stable trait.

> ### Candidate result — humidity, not rain or habituation, tracks the amount of night rest
> Within each animal, total consolidated shelter rest rises on more humid nights: **ρ = +0.36** (n = 55). It
> is not a rain effect, a habituation effect, or a day-in-sequence artifact — the association **strengthens**
> when those are removed: controlling for rain **ρ = +0.46**, controlling for day-in-sequence **ρ = +0.44**,
> and on the **40 dry rat-nights alone ρ = +0.63**, while **rain itself is negative** (within-animal ρ =
> −0.25, and rain-controlling-for-humidity −0.39). So the driver is **atmospheric dampness, not rainfall**,
> consistent with a "damp night → stay settled in shelter" idea. This remains **candidate**: n = 5 animals ×
> 11 nights, ambient (not in-shelter) humidity, an unverified spatial frame, a low-movement proxy, and
> uncorrected comparisons. It is an association, not a demonstrated mechanism.

## What is no longer supported
- **"Hotter nights → more night rest."** An artifact of the loose lowest-minute detector; nil on the proper
  in-shelter metric.
- **A habituation increase in night rest.** No day-in-sequence trend.

## What remains unresolved (ranked)
1. **Is the low-movement bout sleep** (vs grooming or quiet wakefulness)? Gates every biological reading —
   needs interior shelter video (CH07/CH08) or physiology.
2. **Why would humidity matter?** Thermoregulatory cost, coat dampness, comfort — needs an in-shelter
   microclimate measure, not ambient humidity.
3. **Does the rain-negative reflect behaviour or tracking dropout** (rain raises UWB drop-out near shelters)?

## Next steps (highest value first)
1. **Interior shelter video** to test whether the settled bout is rest/sleep and to validate the proxy.
2. **In-shelter humidity/temperature logger** to turn the ambient-humidity correlate into a microclimate test.
3. **More nights** (and a within-night hazard model) to firm the humidity candidate and separate the
   rain-dropout path from behaviour.

## Technical references
- Ledger: `change_log/2026-07-12-night-consolidated-rest.md`; plan
  `implementation_plan/2026-07-12-night-consolidated-rest.md`; `ANALYSIS_STATUS.md` (Direction 3).
- Report / CSVs: `outputs/night_consolidated_rest/night_consolidated_rest_report.md`;
  `crb_per_ratnight.csv`, `why_correlations.csv`, `duration_sensitivity.csv`.
- Driver `analyze_night_consolidated_rest.py` + offline self-test (8/8 PASS — **code checks, not biological
  validation**).

---

## Quantitative appendix — how each finding was quantified

Definitions per `/analysis-definitions`. Night = local `[21:00, 05:00)`, evening-date labelled. Rest per fix
= smoothed speed `< 12.46 in/s` (jitter ceiling). **Consolidated rest bout (CRB)** = stay-point: consecutive
5-min bins whose centroids stay within **24 in** (tolerating ≤ 2 out bins = 10-min hysteresis), ≥ min-dur,
mean rest ≥ 0.60; centroid → `classify_site_state` (shelter set includes houses, refuges 1–4, water, tunnel).
Coverage-guarded (≥ 20 fixes/bin, else `unknown`).

**F1 · Consolidated-rest structure.**
- *Quantity:* n_crb, total_crb_min, shelter fraction, cluster radius per rat-night.
- *Value (30-min primary):* 137 bouts, **55/55 rat-nights ≥1**, **93 % in shelter**, median **50 min**,
  ~**145 min total/night** (2.5 bouts), median radius **4 in**. Sensitivity {20,30,40,60} min → shelter %
  {78,93,98,100}, bouts/night {4.5,2.5,1.8,1.0}.
- *Inference:* a small number of tight, in-shelter settle-ins — not scattered stillness.

**F2 · Not temperature / familiarity; clock-timed.**
- *Quantity:* within-animal (rat-centred) Spearman of total_crb_min vs night temperature and vs
  day-in-sequence; circular hour-gap of the longest-bout onset to the coldest/most-humid hour.
- *Value:* temperature **ρ = −0.12** (crude lowest-minute metric was +0.44 — retracted); familiarity
  **ρ = −0.20**; onset–coldest-hour median **3.9 h**, onset–most-humid-hour **2.4 h**; trait η²(rat)=0.14.
- *Rule:* |ρ| < 0.2 ⇒ no association; hour-gap ≫ 0 ⇒ not weather-timed.

**Candidate · Humidity.**
- *Quantity:* within-animal Spearman(total_crb_min, night humidity); rank-partial controlling rain / day;
  dry-nights-only subset (rain ≤ 0.2 mm/hr).
- *Value:* **ρ = +0.36** (n=55); humidity|rain **+0.46**, humidity|day **+0.44**, **dry-only ρ = +0.63**
  (n=40 dry / 15 wet); rain within-animal **−0.25**, rain|humidity **−0.39**.
- *Decision rule / inference:* the humidity effect survives and strengthens under the rain and day-sequence
  controls while rain itself is non-positive ⇒ a **candidate humidity (dampness) association**, not rain or
  habituation. Limits: ambient humidity, n=5×11, proxy, uncorrected — association, not mechanism.
