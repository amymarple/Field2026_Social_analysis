# Following × weather — fireworks (07-04) & rain cross-check

**Status:** ⚠️ candidate (descriptive; n=1 for fireworks). Tests the FIELD OBSERVATION of increased following on the 07-04 fireworks night, and whether rain increases following, against the Phase-B2 per-night following-incident rates + AWN weather. Movement-normalized rate (`frac_bouts_following`). Generated 2026-07-12T17:34:57.981042.

## Per-night table

| night      | phase   |   frac_bouts_following |   episodes_per_hour | fireworks   | burrow   |   awn_rain_mm | awn_wet   |
|:-----------|:--------|-----------------------:|--------------------:|:------------|:---------|--------------:|:----------|
| 2026-06-28 | release |                0.0234  |              56.75  | False       | False    |          0    | False     |
| 2026-06-29 | early   |                0.01555 |              20.5   | False       | False    |          0    | False     |
| 2026-06-30 | early   |                0.00865 |              16.25  | False       | False    |          0.3  | True      |
| 2026-07-01 | mid     |                0.01045 |              11.875 | False       | False    |          0    | False     |
| 2026-07-02 | mid     |                0.0087  |              16.125 | False       | False    |          0    | False     |
| 2026-07-03 | mid     |                0.01275 |              18.875 | False       | True     |          0    | False     |
| 2026-07-04 | late    |                0.01755 |              23.75  | True        | True     |          0    | False     |
| 2026-07-05 | late    |                0.0121  |              15     | False       | True     |          0.2  | False     |
| 2026-07-06 | late    |                0.01005 |              16     | False       | True     |          2.39 | True      |
| 2026-07-07 | late    |                0.01585 |              29.75  | False       | False    |          0    | False     |
| 2026-07-08 | late    |                0.0201  |              38.007 | False       | False    |          0    | False     |

## Weather cross-check

AWN (rain-rate integrated over the 21:00-05:00 window) is the authoritative rain signal; env-map 'wet' is a coarse ground-wetness flag. 07-04 (fireworks) and 07-01 were env-map-'wet' but AWN-DRY -> the fireworks night carried NO in-window rain. AWN vs env-map 'wet' disagreements: ['2026-07-01', '2026-07-04'] (env-map-wet but AWN-dry). Genuinely rainy in-window nights: 06-30 (0.30 mm), 07-06 (2.39 mm).

## Fireworks (07-04)

07-04 following (frac 0.0175) is ABOVE the dry-normal mean (0.0136); against the CLEANEST match 07-05 (dry+burrow+late, no fireworks) it is 1.45x, and vs 07-06 (wet+burrow+late) 1.75x — highest of the late+burrow nights. The AWN cross-check REMOVES the rain confound (07-04 was dry in-window). Descriptively CONSISTENT with the observed increased following. BUT: n=1; following also rises in the late sequence generally (07-08 dry = 0.0201 > 07-04 with no fireworks), so 07-04 is elevated but not a standout spike; and a fireworks STARTLE (co-flight to shelter) is not the same construct as social following. Suggestive, NOT confirmable from WISER — the B2 video queue for 07-04 is the way to check the mechanism.

- 07-04 0.0175 vs matched DRY+burrow+late 07-05 0.0121 = 1.45x; vs wet+burrow+late 07-06 0.01 = 1.75x.

## Rain

Rain does NOT increase following: wet (no-fireworks) mean frac 0.0094 < dry mean 0.0149 (diff -0.0055). If anything wet nights follow LESS, and this is further confounded by rain->UWB dropout (a mechanical decrease in detectable episodes) and late-sequence habituation — so no evidence for a rain-increases-following effect; a weak wet<dry that is partly a measurement artifact.

## Definitions

- **frac_bouts_following** — fraction of a follower's movement bouts that overlap a strict lagged-following episode (Phase B2); movement-normalized so it separates *more following* from *more moving*. Range [0,1].
- **awn_rain_mm** — Σ(Rain Rate mm/hr × Δt) over the [21:00, next 05:00) local window from AWN.
- **matched contrast** — 07-04 vs 07-05/07-06, holding burrow+late-phase fixed, differing in fireworks (and 07-06 also in rain). n=1 vs n=1; descriptive only.

## Scope

n=1 fireworks night; 07-04 also a burrow night and in the late (higher-following) sequence; fireworks startle-driven co-flight is not the same construct as social following; rain confounded by UWB dropout (mechanical decrease) + habituation. Frame UNVERIFIED. Following 'leader' = temporal order, herd-not-dyad (Phase B). Video (B2 queue) is the way to confirm mechanism.
