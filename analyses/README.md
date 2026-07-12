# Analyses — navigate the science by question

Every scientific question, its verdict, and which cohorts it is answered over. Click a question to
open its card (canonical driver, report, figures, blockers, superseded claims, exact rerun command).
**Generated from [`registry.yaml`](registry.yaml) — do not hand-edit.**

Cohorts present: `2026a`

## `audio_soundscape`

| Verdict | Question | Cohorts | Card |
|---|---|---|---|
| ✅ | What is the environmental soundscape at the paddock over time (relative level + indices)? | `2026a` | [soundscape_features](audio_soundscape/soundscape_features.md) |

## `crossmodal`

| Verdict | Question | Cohorts | Card |
|---|---|---|---|
| ⚠️ | Do CV shelter occupancy (CH05/CH06) and WISER near-shelter occupancy agree? | `2026a` | [cv_wiser_sleep_reconciliation](crossmodal/cv_wiser_sleep_reconciliation.md) |
| ⚠️ | Do fireworks (a loud acoustic startle) trigger following/co-flight? | `2026a` | [fireworks_following](crossmodal/fireworks_following.md) |

## `cv_shelter`

| Verdict | Question | Cohorts | Card |
|---|---|---|---|
| ⚠️ | How many animals are inside each shelter, and are they resting or active (through-glass CV)? | `2026a` | [shelter_occupancy](cv_shelter/shelter_occupancy.md) |
| ⚠️ | How accurate is the shelter detector, stratified by view quality? | `2026a` | [detector_validation](cv_shelter/detector_validation.md) |
| ⚠️ | Does post-film glass fog degrade detectability, and how severe is it? | `2026a` | [fog_dynamics_vs_detectability](cv_shelter/fog_dynamics_vs_detectability.md) |

## `wiser_baseline`

| Verdict | Question | Cohorts | Card |
|---|---|---|---|
| ✅ | What is WISER's static position precision (the jitter floor that bounds every spatial claim)? | `2026a` | [fixed_position_precision](wiser_baseline/fixed_position_precision.md) |
| ✅ | Where do the animals spend time, hour by hour (live-DB-safe occupancy maps)? | `2026a` | [hourly_occupancy](wiser_baseline/hourly_occupancy.md) |

## `wiser_d1_nightly`

| Verdict | Question | Cohorts | Card |
|---|---|---|---|
| ⚠️ | Do the rats move less on later/rainy nights, and is that habituation or rain? | `2026a` | [nightly_habituation_vs_rain](wiser_d1_nightly/nightly_habituation_vs_rain.md) |
| ⚠️ | Does the group's use of space settle/stabilize across nights? | `2026a` | [nightly_settling_social](wiser_d1_nightly/nightly_settling_social.md) |

## `wiser_d2_routes`

| Verdict | Question | Cohorts | Card |
|---|---|---|---|
| ⚠️ | Do the animals reuse spatial corridors, and are the corridors shared or individual? | `2026a` | [route_corridor_structure](wiser_d2_routes/route_corridor_structure.md) |
| ⚠️ | Does each animal have an individually stereotyped trajectory, or is stereotypy shared? | `2026a` | [trajectory_stereotypy](wiser_d2_routes/trajectory_stereotypy.md) |
| ⚠️ | Are there stable leader-follower dyads, or is following a promiscuous herd effect? | `2026a` | [following_structure](wiser_d2_routes/following_structure.md) |
| ⚠️ | Do route bouts recur as a small set of reused motifs, and does the repertoire develop over time? | `2026a` | [route_motifs](wiser_d2_routes/route_motifs.md) |
| ❌ | Is there a discrete, shared route 'vocabulary' the animals draw from? | `2026a` | [route_vocabulary](wiser_d2_routes/route_vocabulary.md) |
| ⚠️ | How frequent is strict trailing, and who leads (incident-level)? | `2026a` | [following_incidents](wiser_d2_routes/following_incidents.md) |
| ❌ | Is the ~4 s / ~100 in 'bout capacity' a real behavioral unit? | `2026a` | [bout_segmentation_validation](wiser_d2_routes/bout_segmentation_validation.md) |
| ⛔ | Can decision-to-decision legs (a 'reorientation-punctuated' structure) be resolved from WISER? | `2026a` | [decision_boundary_validation](wiser_d2_routes/decision_boundary_validation.md) |

## `wiser_d3_sleep`

| Verdict | Question | Cohorts | Card |
|---|---|---|---|
| ⚠️ | Does each animal have a stable daytime rest site, and how often does it relocate? | `2026a` | [daytime_sleep_site](wiser_d3_sleep/daytime_sleep_site.md) |
| ⚠️ | Does high temperature drive the animals out of the shelter (a temperature gate)? | `2026a` | [heat_gated_relocation](wiser_d3_sleep/heat_gated_relocation.md) |
| ⚠️ | Do the animals show a circadian/diel rest-activity rhythm, and is it stable across nights? | `2026a` | [circadian_rest](wiser_d3_sleep/circadian_rest.md) |
| ⚠️ | Across the biological day, which site does each animal rest at (multi-site, not binary)? | `2026a` | [biological_day_sleep](wiser_d3_sleep/biological_day_sleep.md) |
| ⚠️ | Do rest onset (evening) and wake (morning) times differ by site? | `2026a` | [evening_morning_sleep](wiser_d3_sleep/evening_morning_sleep.md) |
| ⚠️ | Is there a ranked hierarchy of preferred rest landmarks? | `2026a` | [sleep_site_hierarchy](wiser_d3_sleep/sleep_site_hierarchy.md) |
| ⚠️ | Is overnight rest consolidated into a single bout (a consolidated rest block)? | `2026a` | [night_consolidated_rest](wiser_d3_sleep/night_consolidated_rest.md) |
| ⚠️ | Does within-day rest-site sequence track temperature? | `2026a` | [rest_temperature](wiser_d3_sleep/rest_temperature.md) |

## `wiser_policy`

| Verdict | Question | Cohorts | Card |
|---|---|---|---|
| ⚠️ | Beyond a shared layout + weather baseline, does identity or social state predict leaving/destination? | `2026a` | [policy_identifiability](wiser_policy/policy_identifiability.md) |
| ⚠️ | Does the leaving rule change over the night, or is it time-invariant? | `2026a` | [temporal_policy](wiser_policy/temporal_policy.md) |
| ⚠️ | What predicts the START of a locomotor bout (the entry side of the loop)? | `2026a` | [locomotor_initiation](wiser_policy/locomotor_initiation.md) |
| ⚠️ | When an animal leaves a shelter, where does it go, and is destination conditioned on origin? | `2026a` | [destination_settlement](wiser_policy/destination_settlement.md) |
| ⚠️ | Do animals actively maintain a preferred inter-individual distance (social spacing)? | `2026a` | [approach_avoid](wiser_policy/approach_avoid.md) |
| ⚠️ | Do animals return to known sites vs explore, and is movement area-restricted or global? | `2026a` | [search_excursions](wiser_policy/search_excursions.md) |
| ⚠️ | Is the social-on-leaving effect stable across the season, or does it habituate? | `2026a` | [social_nonstationarity](wiser_policy/social_nonstationarity.md) |

---
*Legend: ✅ confirmed · ⚠️ candidate · ⛔ blocked · ❌ retracted. Detail per WISER row in [`wiser/ANALYSIS_STATUS.md`](../wiser/ANALYSIS_STATUS.md).*
