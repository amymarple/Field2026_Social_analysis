# ⚠️ Is overnight rest consolidated into a single bout (a consolidated rest block)?

**Direction:** `wiser_d3_sleep` · **id:** `night_consolidated_rest`  

## 1. Verdict

⚠️ **candidate.** Overnight rest forms a consolidated rest block (CRB) per animal per night.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d3_sleep_night_consolidated_rest_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_night_consolidated_rest_2026a.md), [wiser_d3_sleep_night_consolidated_rest_SCIENTIFIC_SUMMARY_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_night_consolidated_rest_SCIENTIFIC_SUMMARY_2026a.md) | — |

**Evidence:** see report.

## 3. Canonical driver

`wiser/scripts/analyze_night_consolidated_rest.py`

## 4. Canonical report

- [wiser_d3_sleep_night_consolidated_rest_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_night_consolidated_rest_2026a.md)
- [wiser_d3_sleep_night_consolidated_rest_SCIENTIFIC_SUMMARY_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_night_consolidated_rest_SCIENTIFIC_SUMMARY_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- 'rest' = low-speed proxy
- night dropout guarded

## 7. Superseded claims

_None._

Change log: [`change_log/2026-07-12-night-consolidated-rest.md`](../../change_log/2026-07-12-night-consolidated-rest.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_night_consolidated_rest.py --cohort 2026a
```

---
*Status source: Night consolidated rest (Direction 3) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
