# Direction 3 — night-time consolidated rest bouts (stay-point) + why

*Candidate / measurement-limited. Rest = low-MOVEMENT proxy (< 12.5 in/s), NOT scored sleep. WISER inch frame UNVERIFIED. Jitter ~7 in. n=5 rats × 11 nights = 55 rat-nights; ambient weather (±5 min unverified); Spearman, uncorrected.*

> A **consolidated rest bout (CRB)** = position clustered within 24 in (a stay-point) + resting (rest ≥ 0.6), sustained **≥ 30 min** (20/40/60 sensitivity), 10-min exit tolerance; `refuge_4` (burrow) + `tunnel` count as enclosed shelter. Rest / grooming / sleep — the in-shelter-for-long is the behavioural signal, NOT validated sleep.

## Detection & duration sensitivity
```
 min_dur_min  n_bouts  ratnights_with_bout  pct_in_shelter  median_dur_min  bouts_per_ratnight
          20      245                   55            78.0            30.0                4.45
          30      137                   55            93.0            50.0                2.49
          40      101                   55            98.0            60.0                1.84
          60       54                   40           100.0            80.0                0.98
```
- **Primary (30 min):** 137 CRBs, **93% in a shelter**, median 50 min, median cluster radius 4 in; **every rat-night has ≥1**. Sites: house_1 84, house_2 25, tunnel 10, refuge_4 9, exposed 5, doorway 4.
- **9 non-shelter consolidated-rest candidates** exported for CH05/CH06 video audit (routed by nearest house; NVR video clock = UTC−5).

## Why (candidate): amount / timing vs familiarity / temperature / humidity

- Mean total consolidated rest **145 min/night** (2.5 bouts).
- **Familiarity (day-in-sequence):** total-rest ρ=-0.20, #bouts ρ=-0.04.
- **Temperature:** total-rest vs night temp — pooled ρ=-0.10, **within-rat ρ=-0.12**.
- **Humidity:** total-rest vs humidity — pooled ρ=+0.34, **within-rat ρ=+0.36**.
  *Disentangle (rain vs humidity vs sequence):* rain within-rat ρ=-0.25; **humidity | rain ρ=+0.46**, rain | humidity ρ=-0.39, humidity | day ρ=+0.44; humidity on **DRY nights only** (n=40) ρ=+0.63.
- **Covariate collinearity:** temp~humid -0.19, temp~day +0.07, humid~day +0.21.
- **Within-night timing:** the longest CRB starts a median **3.9 h** from the night's coldest hour and 2.4 h from the most-humid hour → clock-timed, NOT locked to the within-night weather minimum.
- **Trait vs state:** total-rest η²(rat) = 0.14.

## Evidence status (two levels)

**Supported (descriptive, within the measurement):** night rest is consolidated into ~2–3 in-shelter bouts/rat-night (median 50 min, 4-in cluster radius), universal and house-centred; the longest bout is clock-timed (~midnight), not at the within-night weather minimum.

**Candidate:** any weather / familiarity driver of rest AMOUNT (temperature/humidity, within-rat); that low-movement = sleep. Ambient (not shelter) weather, unverified frame, n=5×11, uncorrected.

## Caveats / deferred
- Rest = proxy (not ephys/CV-validated); non-shelter candidates await video audit (4 lack transferred CH05/06); a firmer weather test needs a shelter thermistor + more nights + a within-night hazard model.
