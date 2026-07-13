# ⚠️ Across the biological day, which site does each animal rest at (multi-site, not binary)?

**Direction:** `wiser_d3_sleep` · **id:** `biological_day_sleep`  

## 1. Verdict

⚠️ **candidate.** Rebuilt on a multi-site state space (house_1/house_2/open/...); the earlier binary house_2-fraction test was state-space misspecification.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d3_sleep_biological_day_canonical_results_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_biological_day_canonical_results_2026a.md), [wiser_d3_sleep_biological_day_report_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_biological_day_report_2026a.md), [wiser_d3_sleep_biological_day_scientific_summary_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_biological_day_scientific_summary_2026a.md) | — |

**Evidence:** canonical rebuild 2026-07-11.

## 3. Canonical driver

`wiser/scripts/analyze_biological_day_sleep.py`

## 4. Canonical report

- [wiser_d3_sleep_biological_day_canonical_results_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_biological_day_canonical_results_2026a.md)
- [wiser_d3_sleep_biological_day_report_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_biological_day_report_2026a.md)
- [wiser_d3_sleep_biological_day_scientific_summary_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_biological_day_scientific_summary_2026a.md)

## 5. Figures

- [BD1_emergence_vs_temp.png](../../results/2026a/wiser_d3_sleep/figures/biological_day_sleep/BD1_emergence_vs_temp.png)
- [BD2_morning_vs_day_site.png](../../results/2026a/wiser_d3_sleep/figures/biological_day_sleep/BD2_morning_vs_day_site.png)
- [BD3_emergence_timeline.png](../../results/2026a/wiser_d3_sleep/figures/biological_day_sleep/BD3_emergence_timeline.png)
- [CP1_changepoint_time_hist.png](../../results/2026a/wiser_d3_sleep/figures/biological_day_sleep/CP1_changepoint_time_hist.png)
- [CP2_changepoint_per_ratday.png](../../results/2026a/wiser_d3_sleep/figures/biological_day_sleep/CP2_changepoint_per_ratday.png)
- [E1_shelter_vs_exposed_vs_temp.png](../../results/2026a/wiser_d3_sleep/figures/biological_day_sleep/E1_shelter_vs_exposed_vs_temp.png)
- [fig1_emergence.png](../../results/2026a/wiser_d3_sleep/figures/biological_day_sleep/fig1_emergence.png)
- [fig2_changepoint_timing.png](../../results/2026a/wiser_d3_sleep/figures/biological_day_sleep/fig2_changepoint_timing.png)
- [fig3_dwell_composition.png](../../results/2026a/wiser_d3_sleep/figures/biological_day_sleep/fig3_dwell_composition.png)
- [SS1_state_dwell_and_transitions.png](../../results/2026a/wiser_d3_sleep/figures/biological_day_sleep/SS1_state_dwell_and_transitions.png)

## 6. Blockers

- 'sleep' = low-speed proxy
- frame unverified

## 7. Superseded claims

the binary house_2-fraction test (state-space misspecification)

Change log: [`change_log/2026-07-10-biological-day-sleep.md`](../../change_log/2026-07-10-biological-day-sleep.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_biological_day_sleep.py --cohort 2026a
```

---
*Status source: Biological-day sleep (Direction 3 core rebuild) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
