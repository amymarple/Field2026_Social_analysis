# Direction 3 — daytime sleep / rest site

Direction key: `wiser_d3_sleep`. Regenerated from `analyses/registry.yaml` — **do not hand-edit**; a
new cohort appends coverage, it does not rewrite prose. Each finding: one sentence + evidence + source
+ status (ACTIVE / SUPERSEDED / CONTESTED).

## Cohort coverage

| Question | `2026a` |
|---|---|
| Does each animal have a stable daytime rest site, and how often does it relocate? | ✓ |
| Does high temperature drive the animals out of the shelter (a temperature gate)? | ✓ |
| Do the animals show a circadian/diel rest-activity rhythm, and is it stable across nights? | ✓ |
| Across the biological day, which site does each animal rest at (multi-site, not binary)? | ✓ |
| Do rest onset (evening) and wake (morning) times differ by site? | ✓ |
| Is there a ranked hierarchy of preferred rest landmarks? | ✓ |
| Is overnight rest consolidated into a single bout (a consolidated rest block)? | ✓ |
| Does within-day rest-site sequence track temperature? | ✓ |

## Findings

### Does each animal have a stable daytime rest site, and how often does it relocate?
- **Claim:** Per-animal daytime (05:00-21:00) rest site with tiered relocation: over 50 day-pairs {stable 31, major-switch 19}; ALL 5 animals switch house_1<->house_2 at least once, heterogeneous by rate.
- **Evidence:** 11 days (06-28..07-08); rates 12395 5/10, 12407 5/10, others 3/10.
- **Source:** [`results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_SCIENTIFIC_SUMMARY_2026a.md`](../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_SCIENTIFIC_SUMMARY_2026a.md)
- **Status:** ACTIVE (candidate).
- **Superseded:** the old '8/10 relocated' (jitter) and 3-day 'only 2 animals' (small-sample) readings
- **Card:** [`analyses/wiser_d3_sleep/daytime_sleep_site.md`](../analyses/wiser_d3_sleep/daytime_sleep_site.md)

### Does high temperature drive the animals out of the shelter (a temperature gate)?
- **Claim:** Within-day heat-gated dispersal: the late-morning shelter aggregation thins/disperses at the 12:00-15:00 heat peak on 9/10 days, a repeated candidate temperature-linked signature.
- **Evidence:** 66 within-day events, 56 bouts; gate ~32 C; within-day contrast (day is its own control).
- **Source:** [`results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_heat_gated_relocation_2026a.md`](../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_heat_gated_relocation_2026a.md)
- **Status:** ACTIVE (candidate).
- **Superseded:** 'no detectable temperature effect' (full-day/linear tests missed the ~32 C threshold)
- **Card:** [`analyses/wiser_d3_sleep/heat_gated_relocation.md`](../analyses/wiser_d3_sleep/heat_gated_relocation.md)

### Do the animals show a circadian/diel rest-activity rhythm, and is it stable across nights?
- **Claim:** Clear nocturnal/crepuscular rhythm (REST 0.92 day vs 0.86 night, ~2.5x activity swing peaking sharply at 21:00); dusk-onset phase FIXED from night 1; rhythm does not drift, only amplitude modulates.
- **Evidence:** 5 rats x 11 days; activity peak = 21:00 on all 11 nights; narrow SEM (synchronized).
- **Source:** [`results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_circadian_rest_2026a.md`](../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_circadian_rest_2026a.md)
- **Status:** ACTIVE (candidate).
- **Superseded:** the calendar '06-29 01:00 peak' (a night-splitting artifact; bio-night alignment corrects it)
- **Card:** [`analyses/wiser_d3_sleep/circadian_rest.md`](../analyses/wiser_d3_sleep/circadian_rest.md)

### Across the biological day, which site does each animal rest at (multi-site, not binary)?
- **Claim:** Rebuilt on a multi-site state space (house_1/house_2/open/...); the earlier binary house_2-fraction test was state-space misspecification.
- **Evidence:** canonical rebuild 2026-07-11.
- **Source:** [`results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_biological_day_canonical_results_2026a.md`](../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_biological_day_canonical_results_2026a.md)
- **Status:** ACTIVE (candidate).
- **Superseded:** the binary house_2-fraction test (state-space misspecification)
- **Card:** [`analyses/wiser_d3_sleep/biological_day_sleep.md`](../analyses/wiser_d3_sleep/biological_day_sleep.md)

### Do rest onset (evening) and wake (morning) times differ by site?
- **Claim:** Site + morning structure hold; the `sleep_end` metric was RETIRED and replaced by `wake_hour` (the earlier evening/morning endpoint was unreliable).
- **Evidence:** 11 nights.
- **Source:** [`results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_evening_morning_2026a.md`](../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_evening_morning_2026a.md)
- **Status:** ACTIVE (candidate).
- **Superseded:** the `sleep_end` metric (retired -> `wake_hour`)
- **Card:** [`analyses/wiser_d3_sleep/evening_morning_sleep.md`](../analyses/wiser_d3_sleep/evening_morning_sleep.md)

### Is there a ranked hierarchy of preferred rest landmarks?
- **Claim:** Landmark rest sites rank into a hierarchy (H1-H4) by occupancy.
- **Evidence:** 11 days.
- **Source:** [`results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_site_hierarchy_2026a.md`](../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_site_hierarchy_2026a.md)
- **Status:** ACTIVE (candidate).

- **Card:** [`analyses/wiser_d3_sleep/sleep_site_hierarchy.md`](../analyses/wiser_d3_sleep/sleep_site_hierarchy.md)

### Is overnight rest consolidated into a single bout (a consolidated rest block)?
- **Claim:** Overnight rest forms a consolidated rest block (CRB) per animal per night.
- **Evidence:** see report.
- **Source:** [`results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_night_consolidated_rest_2026a.md`](../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_night_consolidated_rest_2026a.md)
- **Status:** ACTIVE (candidate).

- **Card:** [`analyses/wiser_d3_sleep/night_consolidated_rest.md`](../analyses/wiser_d3_sleep/night_consolidated_rest.md)

### Does within-day rest-site sequence track temperature?
- **Claim:** Within-day rest-site sequence + relocation events align with the heat peak (candidate temperature-linked), weather now full coverage across 11 days.
- **Evidence:** 66 within-day events, 56 bouts; refuge_4 burrow windows flagged as UWB lower bound, not sleep.
- **Source:** [`results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_temperature_relocation_2026a.md`](../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_temperature_relocation_2026a.md)
- **Status:** ACTIVE (candidate).

- **Card:** [`analyses/wiser_d3_sleep/rest_temperature.md`](../analyses/wiser_d3_sleep/rest_temperature.md)

---
*Generated by `summaries/_generate_summaries.py`. Verdict marks trace to `wiser/ANALYSIS_STATUS.md` and the linked change logs.*
