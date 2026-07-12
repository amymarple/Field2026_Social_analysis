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

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

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
