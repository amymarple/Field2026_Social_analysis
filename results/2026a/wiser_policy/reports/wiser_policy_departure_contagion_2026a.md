# Departure following / contagion on the leaving decision (11 nights)

**Status:** ⚠️ candidate. Tests the reviewer's ACTUAL mechanism — group FOLLOWING (a neighbour just left, so I leave) — which the static-crowding social features cannot encode, and whether that following is front-loaded on novel early nights. Whole-night blocks. Generated 2026-07-12T16:58:47.927086. Onset is a LOWER bound; association not sampling motivation.

## Definitions (formula + plain text)

- **n_others_departed_W(focal, t)** — number of OTHER tags in the same night whose locomotor-bout ONSET
  (module-3 `bouts.t_start`) falls in $[t-W, t)$ (strictly before the decision). A dynamic "recent group
  departure" / following-pressure covariate; $W$ = 60.0 s.
- **Following effect (T-FOLLOW)** — held-out (leave-one-night-out) Δbits of adding n_others_departed to a
  base that ALREADY has static crowding (n_within_1m, mean_others_dist). >0 ⇒ recent group departure
  predicts the focal leaving beyond how many are merely near. Night-block sign test.
- **Real-time null (T-REAL)** — each other tag's onset times are circularly shifted by a random offset
  within its night (its onset RATE preserved, the fine alignment to the focal's decision destroyed).
  Beating it (z>2) ⇒ genuine real-time coupling, not shared circadian timing (base already holds
  clock_hour + moving_frac).
- **Front-loading (T-FRONT)** — per-night held-out following Δbits, early (nights 0-2, pre-burrow novel
  paddock) vs late, Spearman vs night index, and a held-out contagion×night_index interaction. Front-
  loaded ⇔ early>late and a negative trend — the reviewer's habituation prediction.

## T-FOLLOW — following beyond static crowding

- Held-out Δbits **+0.0010** | sign-test p **0.2265625** (8/11 nights) | pooled coef on
  n_others_departed_300 = **-0.0656** (anti-following).

## T-REAL — real-time following vs shared circadian timing

- Observed Δbits +0.0010 vs circular-shift null **-0.0001 ± 0.0005** → **z = 2.27**
  (real-time following: True).

## T-FRONT — is following front-loaded?

| night | held-out following Δbits |
|---|---|
| 2026-06-28 | -0.007 |
| 2026-06-29 | 0.0028 |
| 2026-06-30 | 0.0031 |
| 2026-07-01 | 0.0017 |
| 2026-07-02 | 0.0022 |
| 2026-07-03 | 0.0001 |
| 2026-07-04 | -0.0034 |
| 2026-07-05 | 0.0021 |
| 2026-07-06 | 0.0067 |
| 2026-07-07 | 0.0039 |
| 2026-07-08 | -0.0016 |

- early (nights 0-2) mean **-0.0004** vs late **0.0015**;
  Spearman ρ = **0.191** (p 0.574); contagion×night_index held-out
  Δ = -0.00096 (wins 4/11). Front-loaded: **False**.

## Verdict

NO robust departure-following on leaving: held-out Δbits=+0.0010 (sign-test p=0.2265625), real-time null z=2.27. The static-crowding picture is not rescued by a temporal-following feature at this resolution. Front-loading is NOT established (early -0.0004 vs late 0.0015, Spearman rho=0.191 p=0.574; n=11 low power).

## Scope

Following is measured as temporal co-departure (others' bout onsets preceding the focal's leave), NOT
spatial go-where-they-went (that is module 8 / destination). Onset is a LOWER bound (sub-jitter in-nest
stirring invisible), so a real following that operates below the jitter floor is under-counted. n = 11
nights is low power for the front-loading trend. Group-level, association not "sampling" motivation.
Frame UNVERIFIED.
