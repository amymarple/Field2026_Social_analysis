# Behavioral policy (14-module)

Direction key: `wiser_policy`. Regenerated from `analyses/registry.yaml` — **do not hand-edit**; a
new cohort appends coverage, it does not rewrite prose. Each finding: one sentence + evidence + source
+ status (ACTIVE / SUPERSEDED / CONTESTED).

## Cohort coverage

| Question | `2026a` |
|---|---|
| Beyond a shared layout + weather baseline, does identity or social state predict leaving/destination? | ✓ |
| Does the leaving rule change over the night, or is it time-invariant? | ✓ |
| What predicts the START of a locomotor bout (the entry side of the loop)? | ✓ |
| When an animal leaves a shelter, where does it go, and is destination conditioned on origin? | ✓ |
| Do animals actively maintain a preferred inter-individual distance (social spacing)? | ✓ |
| Do animals return to known sites vs explore, and is movement area-restricted or global? | ✓ |
| Is the social-on-leaving effect stable across the season, or does it habituate? | ✓ |

## Findings

### Beyond a shared layout + weather baseline, does identity or social state predict leaving/destination?
- **Claim:** Environment+dwell explains leaving hazard (skill 0.13-0.26); INDIVIDUAL is detectable but NEGLIGIBLE (~0.001 bits); real-time GROUP social state is a ROBUST predictor of leaving (~0.012 bits, +on all 8 nights, jitter-floor-safe). Endpoint = environment+dwell+group-social semi-Markov choice model; no IRL.
- **Evidence:** 8 nights, hysteretic ROI-state decision unit; social survives day-shuffle z~30.
- **Source:** [`results/2026a/wiser_policy/reports/wiser_policy_identifiability_audit_2026a.md`](../results/2026a/wiser_policy/reports/wiser_policy_identifiability_audit_2026a.md)
- **Status:** ACTIVE (candidate).
- **Superseded:** the contaminated raw point-in-ROI decision unit (M4/M5 invalidated; social flipped NO-GO->GO)
- **Card:** [`analyses/wiser_policy/policy_identifiability.md`](../analyses/wiser_policy/policy_identifiability.md)

### Does the leaving rule change over the night, or is it time-invariant?
- **Claim:** The conditional leaving RULE is time-invariant (held-out hour-varying Delta-bits -0.0004; night-slope z 0.51); hour/night differences are state occupancy under ONE shared rule; crowding suppresses leaving, constant across the night.
- **Evidence:** hour-label null z 0.73.
- **Source:** [`results/2026a/wiser_policy/reports/wiser_policy_temporal_SUMMARY_2026a.md`](../results/2026a/wiser_policy/reports/wiser_policy_temporal_SUMMARY_2026a.md)
- **Status:** ACTIVE (candidate).

- **Card:** [`analyses/wiser_policy/temporal_policy.md`](../analyses/wiser_policy/temporal_policy.md)

### What predicts the START of a locomotor bout (the entry side of the loop)?
- **Claim:** Bout-initiation hazard is 3.3x higher from open low-speed (0.85%) than settled shelter-rest (0.25%); initiation != ROI departure (26x); weather ~0, group-social NO-GO for initiation (asymmetry with leaving).
- **Evidence:** 8 nights; 1,016 onsets / 198,735 at-risk epochs; state skill 6.2%.
- **Source:** [`results/2026a/wiser_policy/reports/wiser_policy_locomotor_initiation_2026a.md`](../results/2026a/wiser_policy/reports/wiser_policy_locomotor_initiation_2026a.md)
- **Status:** ACTIVE (candidate).
- **Superseded:** a first per-bin-rest decision unit that over-fragmented rest and violated D1
- **Card:** [`analyses/wiser_policy/locomotor_initiation.md`](../analyses/wiser_policy/locomotor_initiation.md)

### When an animal leaves a shelter, where does it go, and is destination conditioned on origin?
- **Claim:** ~60% of shelter departures END IN THE OPEN (open_field_termination); only 19% relocate to a named site, 13% same-site return. Gated choice fit: origin conditions destination (Delta-bits 0.63 / skill 14%).
- **Evidence:** 8 nights; 1,110 stationary episodes -> 321 settlements, 295 departures; choice fit n=55 (exploratory).
- **Source:** [`results/2026a/wiser_policy/reports/wiser_policy_destination_choice_2026a.md`](../results/2026a/wiser_policy/reports/wiser_policy_destination_choice_2026a.md)
- **Status:** ACTIVE (candidate).
- **Superseded:** the old named->named `build_destination_table` (blind to 60% open-field terminations)
- **Card:** [`analyses/wiser_policy/destination_settlement.md`](../analyses/wiser_policy/destination_settlement.md)

### Do animals actively maintain a preferred inter-individual distance (social spacing)?
- **Claim:** Distance-dependent social spacing: real-time APPROACH to far conspecifics (>3.8m, 8/8 nights, p=0.008) and AVOIDANCE of near ones (1-3.8m, p<=0.016) — active maintenance of a preferred distance; the first robustly night-validated social signal.
- **Evidence:** 8 nights, 3,936 bout-partner pairs; night-level binomial sign test (survived pseudoreplication correction).
- **Source:** [`results/2026a/wiser_policy/reports/wiser_policy_approach_avoid_2026a.md`](../results/2026a/wiser_policy/reports/wiser_policy_approach_avoid_2026a.md)
- **Status:** ACTIVE (candidate).
- **Superseded:** a per-pair z test (pseudoreplicated -> corrected to a night-block test)
- **Card:** [`analyses/wiser_policy/approach_avoid.md`](../analyses/wiser_policy/approach_avoid.md)

### Do animals return to known sites vs explore, and is movement area-restricted or global?
- **Claim:** Return vs explore shows NO return-bias beyond layout (null); area-restricted vs global search is geometry-only and DBV-capped (coarse).
- **Evidence:** 11 nights (Phase 4).
- **Source:** [`results/2026a/wiser_policy/reports/wiser_policy_search_excursions_2026a.md`](../results/2026a/wiser_policy/reports/wiser_policy_search_excursions_2026a.md)
- **Status:** ACTIVE (candidate).

- **Card:** [`analyses/wiser_policy/search_excursions.md`](../analyses/wiser_policy/search_excursions.md)

### Is the social-on-leaving effect stable across the season, or does it habituate?
- **Claim:** Social-on-leaving is non-stationary across the 11 nights; rest-need vs social is disambiguated and co-departure/following contagion is negligible.
- **Evidence:** 11-night social extension.
- **Source:** [`results/2026a/wiser_policy/reports/wiser_policy_social_habituation_2026a.md`](../results/2026a/wiser_policy/reports/wiser_policy_social_habituation_2026a.md)
- **Status:** ACTIVE (candidate).

- **Card:** [`analyses/wiser_policy/social_nonstationarity.md`](../analyses/wiser_policy/social_nonstationarity.md)

---
*Generated by `summaries/_generate_summaries.py`. Verdict marks trace to `wiser/ANALYSIS_STATUS.md` and the linked change logs.*
