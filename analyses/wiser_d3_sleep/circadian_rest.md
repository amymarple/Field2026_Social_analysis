# ⚠️ Do the animals show a circadian/diel rest-activity rhythm, and is it stable across nights?

**Direction:** `wiser_d3_sleep` · **id:** `circadian_rest`  

## 1. Verdict

⚠️ **candidate.** Clear nocturnal/crepuscular rhythm (REST 0.92 day vs 0.86 night, ~2.5x activity swing peaking sharply at 21:00); dusk-onset phase FIXED from night 1; rhythm does not drift, only amplitude modulates.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d3_sleep_circadian_rest_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_circadian_rest_2026a.md), [wiser_d3_sleep_circadian_rest_SCIENTIFIC_SUMMARY_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_circadian_rest_SCIENTIFIC_SUMMARY_2026a.md) | — |

**Evidence:** 5 rats x 11 days; activity peak = 21:00 on all 11 nights; narrow SEM (synchronized).

## 3. Canonical driver

`wiser/scripts/analyze_circadian_rest.py`

## 4. Canonical report

- [wiser_d3_sleep_circadian_rest_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_circadian_rest_2026a.md)
- [wiser_d3_sleep_circadian_rest_SCIENTIFIC_SUMMARY_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_circadian_rest_SCIENTIFIC_SUMMARY_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- rest = low-speed proxy at the jitter ceiling (overcounts sleep, compresses swing)
- not ephys/CV-validated

## 7. Superseded claims

the calendar '06-29 01:00 peak' (a night-splitting artifact; bio-night alignment corrects it)

Change log: [`change_log/2026-07-08-circadian-rest-profile.md`](../../change_log/2026-07-08-circadian-rest-profile.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_circadian_rest.py --cohort 2026a
```

---
*Status source: Circadian / diel REST profile — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
