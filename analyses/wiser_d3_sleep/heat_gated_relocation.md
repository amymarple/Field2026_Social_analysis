# ⚠️ Does high temperature drive the animals out of the shelter (a temperature gate)?

**Direction:** `wiser_d3_sleep` · **id:** `heat_gated_relocation`  

## 1. Verdict

⚠️ **candidate.** Within-day heat-gated dispersal: the late-morning shelter aggregation thins/disperses at the 12:00-15:00 heat peak on 9/10 days, a repeated candidate temperature-linked signature.

## 2. Cohort coverage

| Cohort | Canonical report(s) | Superseded (archive) |
|---|---|---|
| `2026a` | [wiser_d3_sleep_heat_gated_relocation_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_heat_gated_relocation_2026a.md), [wiser_d3_sleep_heat_gated_relocation_SCIENTIFIC_SUMMARY_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_heat_gated_relocation_SCIENTIFIC_SUMMARY_2026a.md) | — |

**Evidence:** 66 within-day events, 56 bouts; gate ~32 C; within-day contrast (day is its own control).

## 3. Canonical driver

`wiser/scripts/analyze_heat_gated_relocation.py`

## 4. Canonical report

- [wiser_d3_sleep_heat_gated_relocation_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_heat_gated_relocation_2026a.md)
- [wiser_d3_sleep_heat_gated_relocation_SCIENTIFIC_SUMMARY_2026a.md](../../results/2026a/wiser_d3_sleep/reports/wiser_d3_sleep_heat_gated_relocation_SCIENTIFIC_SUMMARY_2026a.md)

## 5. Figures

- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._

## 6. Blockers

- outside-air temp proxy (no shelter thermistor)
- temp acts on animal AND UWB paths
- house_2 not verified cooler (inch frame)
- thermal vs social vs habit not separable

## 7. Superseded claims

'no detectable temperature effect' (full-day/linear tests missed the ~32 C threshold)

Change log: [`change_log/2026-07-12-heat-gated-relocation.md`](../../change_log/2026-07-12-heat-gated-relocation.md)

## 8. Exact rerun command

```bash
python wiser/scripts/analyze_heat_gated_relocation.py --cohort 2026a
```

---
*Status source: Heat-gated relocation (Direction 3) — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). Generated from `analyses/registry.yaml`; do not hand-edit.*
