# ⚠️ Does within-day rest-site sequence track temperature?

**Direction:** `wiser_d3_sleep` · **id:** `rest_temperature`  

## 1. Verdict

⚠️ **candidate.** Within-day rest-site sequence + relocation events align with the heat peak (candidate temperature-linked), weather now full coverage across 11 days.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d3_sleep_temperature_relocation_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_temperature_relocation_2026a.md) | — |

**Evidence:** 66 within-day events, 56 bouts; refuge_4 burrow windows flagged as UWB lower bound, not sleep.

## 3. Canonical driver

`wiser/scripts/analyze_daytime_rest_temperature.py`

## 4. Canonical report

- [wiser_d3_sleep_temperature_relocation_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_temperature_relocation_2026a.md)

## 5. Figures

- [T1_rest_site_timeline.png](../../results/2026a/wiser_d3_sleep/figures/rest_temperature/T1_rest_site_timeline.png)
- [T2_convergence_by_window.png](../../results/2026a/wiser_d3_sleep/figures/rest_temperature/T2_convergence_by_window.png)

## 6. Blockers

- outside-air temp proxy
- temp a covariate on both animal + UWB paths
- refuge_4 burrow removed 07-07

## 7. Superseded claims

_None._

Change log: [`change_log/2026-07-07-direction3-temperature-relocation.md`](../../change_log/2026-07-07-direction3-temperature-relocation.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_daytime_rest_temperature.py --cohort 2026a
```

---
*Status source: Within-day rest-site & temperature (Direction 3, Stage B) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
